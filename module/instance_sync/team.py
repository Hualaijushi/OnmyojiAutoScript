# This Python file uses the following encoding: utf-8
"""组队会合（D030）：组队任务开始前，两个实例先在门口会合，再一起开始。

和 coordinator 的账本是两回事：组队没有「点了收不回」的操作，只要两边同时到场，所以不用账本。
每个实例只写自己的在场文件 `team/<实例名>.json`，对方只读。
「读对方 → 判断 → 写自己」放在一把配对锁里做：一边判了「开始」并写下 running，
另一边下一次在锁里读到的一定是这条 running，于是也判「开始」，不会一边开始、一边推迟。
不 import tasks.*，不碰设备。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from filelock import FileLock, Timeout

from module.config.atomicwrites import atomic_write
from module.logger import logger

# 组队身份和它的互补身份；契灵的 handoff1 / handoff2 是「先队长后队员」与反过来，两者互补
COMPLEMENT = {'leader': 'member', 'member': 'leader', 'handoff1': 'handoff2', 'handoff2': 'handoff1'}
ROLES = tuple(COMPLEMENT)
# 要两边同时到场、但不按队长 / 队员组队的任务（同心之兰）：不进会合门口，只出现在快照里供对方让路
PAIR = 'pair'
TIME_FMT = '%Y-%m-%d %H:%M:%S'

STALE = timedelta(seconds=60)
# 对方文件过期不到这么久多半是在重启（两边一起重启时先起来的一边必然读到旧文件），进门等它，不推迟不提醒
OFFLINE_GRACE = timedelta(minutes=5)
# 本进程刚启动时对方文件过期很久也先等：两边一起启动时先起来的一边读到的是对方几十分钟前的旧文件（10-23 11:23）
STARTUP_GRACE = timedelta(minutes=3)
HEARTBEAT_INTERVAL = 10.0
POLL_INTERVAL = 2.0
# 两边调度时间差几秒很常见（同一个任务 next_run 差 2 秒），一分钟内都当作「到点了」，免得来回推迟
DUE_GRACE = timedelta(seconds=60)
RETRY_OFFLINE = timedelta(minutes=10)
RETRY_MISCONFIG = timedelta(minutes=30)
YIELD_DELAY = timedelta(minutes=3)
WAIT_LOG_EVERY = timedelta(minutes=5)
# 等这么久对方还没进同一任务就推送一次提醒（不放弃等待，用户 2026-10-23 决定）
WAIT_NOTIFY = timedelta(minutes=30)

GO, WAIT, POSTPONE, ABORT = 'go', 'wait', 'postpone', 'abort'
IDLE, RUNNING, WAITING = 'idle', 'running', 'waiting'
# 循环（御魂 → 个人突破）在在场文件里的状态；LIVE 表示还在进行，其余是终态
LOOP_LIVE = ('FORMING', 'JOINED', 'ACTIVE')


class Decision(NamedTuple):
    action: str
    reason: str
    until: Optional[datetime] = None


class _Unreadable:
    """对方文件正在被替换等短暂读不到的情况：这一轮不下结论，下一轮再看。"""


UNREADABLE = _Unreadable()


def _fmt(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(TIME_FMT) if dt is not None else None


def _parse(text) -> Optional[datetime]:
    return datetime.strptime(text, TIME_FMT) if text else None


def dump_team_tasks(team_tasks: dict) -> dict:
    result = {}
    for name, e in team_tasks.items():
        item = {'role': e['role'], 'enable': bool(e['enable']), 'next_run': _fmt(e['next_run'])}
        # 循环期间才有：该任务在本实例调度顺序里的位次，对方据此判断「是否都认为它更高」
        if e.get('rank') is not None:
            item['rank'] = e['rank']
        result[name] = item
    return result


def parse_presence(raw) -> dict:
    """把在场文件转成判断用的结构；格式不对抛 ValueError。"""
    if not isinstance(raw, dict) or raw.get('version') != 1:
        raise ValueError('unknown presence version')
    if raw.get('state') not in (IDLE, RUNNING, WAITING):
        raise ValueError(f'unknown state {raw.get("state")!r}')
    tasks = raw.get('team_tasks')
    if not isinstance(tasks, dict):
        raise ValueError('team_tasks is not a dict')
    try:
        return {
            **raw,
            'since': _parse(raw.get('since')),
            'until': _parse(raw.get('until')),
            # 可选字段：旧版本写的文件没有，当作不在休息
            'rest_until': _parse(raw.get('rest_until')),
            'progress': _parse_progress(raw.get('progress')),
            # 循环信息是可选字段：格式不对当作没有，旧版本的文件也没有
            'loop': raw.get('loop') if isinstance(raw.get('loop'), dict) else None,
            'prev': raw.get('prev') if isinstance(raw.get('prev'), dict) else None,
            'updated_at': _parse(raw['updated_at']),
            'team_tasks': {name: _parse_task_entry(e) for name, e in tasks.items()},
        }
    except (KeyError, TypeError) as exc:
        raise ValueError(f'bad presence field: {exc}') from exc


def _parse_task_entry(e: dict) -> dict:
    entry = {'role': e['role'], 'enable': bool(e['enable']), 'next_run': _parse(e['next_run'])}
    # 可选字段：只有循环期间的对方才带位次，旧文件没有
    if isinstance(e.get('rank'), (int, float)) and not isinstance(e.get('rank'), bool):
        entry['rank'] = e['rank']
    return entry


def _parse_progress(raw) -> Optional[dict]:
    # 可选字段：格式不对当作没有进度，不让整个在场文件作废
    if not isinstance(raw, dict) or isinstance(raw.get('count'), bool) or not isinstance(raw.get('count'), int):
        return None
    return {'count': raw['count'], 'done': bool(raw.get('done'))}


def _due(entry: Optional[dict], now: datetime) -> bool:
    return bool(entry) and entry['enable'] and entry['next_run'] is not None and entry['next_run'] <= now + DUE_GRACE


def _loop_door(me: dict, peer: dict, task: str):
    """循环相关的门口判断。返回 None 表示不涉及循环；否则返回 (动作, 原因)。

    me['loop'] 是 {'id', 'step'}，只有循环里的步骤才带；peer['loop'] 是对方发布的循环信息。
    """
    mine = me.get('loop')
    theirs = peer.get('loop')
    live = isinstance(theirs, dict) and theirs.get('state') in LOOP_LIVE
    if mine is None:
        # 对方正在循环、且它当前的步骤就是这个任务：普通排期的同名任务不能和它会合
        if live and theirs.get('step_task') == task:
            return POSTPONE, 'peer_in_loop'
        return None
    if live and theirs.get('id') == mine.get('id') and theirs.get('idx') == mine.get('step'):
        return None
    return WAIT, 'peer_loop_pending'


def _peer_ranks_task_lower(peer: dict, task: str) -> bool:
    """对方正在循环里，且按它自己的位次，这个任务并不严格高于它当前的步骤。

    位次信息缺失（对方没开循环 / 旧版本文件）一律不下结论；对方已经和我在同一任务里（门口等 / 在跑）也不管。
    """
    theirs = peer.get('loop')
    if not (isinstance(theirs, dict) and theirs.get('state') in LOOP_LIVE):
        return False
    if theirs.get('step_task') == task:
        return False
    if peer.get('task') == task and peer.get('state') in (WAITING, RUNNING):
        return False
    step_rank = theirs.get('step_rank')
    entry = peer['team_tasks'].get(task)
    if step_rank is None or not entry or not entry['enable'] or entry.get('rank') is None:
        return False
    return not entry['rank'] < step_rank


def decide(me: dict, peer, now: datetime) -> Decision:
    """我在组队任务 me['task'] 门口，看对方的在场状态决定开始 / 继续等 / 推迟。纯函数。

    原则：到点就在门口等，不设固定超时；对方这个任务没到点也等——对方会看到我在等，把它拉到现在
    （TeamSync.answer）。以前按对方的计划时间推迟自己，两边被推到同一个较晚时间后，
    任何一边提前都会被拉回去（10-23 两边 Orochi 互推）。
    只有能确定对方不会来（不在线 / 没配对 / 没开 / 身份不互补）或对方在休息时才推迟。
    """
    task, role = me['task'], me['role']
    if peer is UNREADABLE:
        return Decision(WAIT, 'peer_unreadable')
    if peer is None or peer['updated_at'] is None or now - peer['updated_at'] > OFFLINE_GRACE:
        started_at = me.get('started_at')
        if started_at is not None and now - started_at < STARTUP_GRACE:
            return Decision(WAIT, 'peer_starting')
        return Decision(POSTPONE, 'peer_offline', now + RETRY_OFFLINE)
    # 刚过期：旧文件里的状态不可信（可能写着在同一门口等），不能当成会合，只等它重新写
    if now - peer['updated_at'] > STALE:
        return Decision(WAIT, 'peer_reconnecting')
    if peer.get('peer') != me['instance']:
        return Decision(POSTPONE, 'peer_not_paired', now + RETRY_OFFLINE)

    # 循环门口和普通门口不能互相会合：下面「对方在同一任务」的几条提前返回 GO 的路径都在这条之后。
    # 普通御魂不能和正在循环里的对方会合；循环里的步骤要对方也在同一次循环的同一步骤上才继续
    blocked = _loop_door(me, peer, task)
    if blocked is not None:
        if blocked[0] == POSTPONE:
            return Decision(POSTPONE, blocked[1], now + RETRY_MISCONFIG)
        return Decision(WAIT, blocked[1])
    # 我已经在这个组队任务的门口，对方后来才进循环 / 才发布步骤位次：对方不认为它严格高于自己的步骤，
    # 它就不会在步骤边界插入这个任务，我不能无限等它，按既有的让路间隔推迟
    if _peer_ranks_task_lower(peer, task):
        return Decision(POSTPONE, 'peer_ranks_lower', now + YIELD_DELAY)

    state, peer_task = peer['state'], peer.get('task')
    if state == RUNNING and peer_task == task:
        if peer.get('partner_token') == me['token']:
            return Decision(GO, 'peer_started_with_me')
        # 对方还在和我的旧进程那一次组队里（我刚重启）：它要么也在重启、新进程会进门，
        # 要么打完 / 发现我已离开后回到空闲，看到我在门口等会把同一任务拉过来（10-23 11:25 推迟后 7 秒又被拉回）
        return Decision(WAIT, 'peer_running_alone')
    if state == WAITING and peer_task == task:
        if COMPLEMENT.get(peer.get('role')) == role:
            return Decision(GO, 'met')
        return Decision(POSTPONE, 'role_conflict', now + RETRY_MISCONFIG)

    entry = peer['team_tasks'].get(task)
    if not entry or not entry['enable'] or entry['role'] == PAIR:
        return Decision(POSTPONE, 'peer_task_off', now + RETRY_MISCONFIG)
    if COMPLEMENT.get(entry['role']) != role:
        return Decision(POSTPONE, 'role_conflict', now + RETRY_MISCONFIG)
    # 对方在休息时段（休息时间窗 / 每日活跃上限后的长休息）：被拉过来的任务也会被推到休息结束，
    # 我先去跑别的，到点两边再会合
    if state != WAITING and peer.get('rest_until') is not None and peer['rest_until'] > now + DUE_GRACE:
        return Decision(POSTPONE, 'peer_resting', peer['rest_until'])

    # 对方正在跑（或马上要跑）一个要两边同时到场的任务，而它在我这边也到点了：
    # 我在这里等，对方在那边等我进场，谁也等不到。我先让开，调度器会选到那个任务。
    mine = me['team_tasks'].get(peer_task)
    if state in (RUNNING, IDLE) and mine and mine['role'] == PAIR and _due(mine, now):
        return Decision(POSTPONE, 'yield_to_paired_task', now + YIELD_DELAY)

    if state == WAITING:
        # 对方在另一个组队任务门口：后到的让（since 晚的；同时到按实例名），两边按同一个顺序比，
        # 不会都让或都不让。让的一方回到调度器后会被对方拉进它等的那个任务
        if (peer['since'] or now, peer['instance']) < (me['since'], me['instance']):
            return Decision(POSTPONE, 'yield_to_peer', now + YIELD_DELAY)
        return Decision(WAIT, 'peer_will_yield')
    if state == RUNNING:
        return Decision(WAIT, 'peer_busy')
    # 对方空闲：这个任务在它那边没到点也等，它看到我在等会把任务拉到现在
    return Decision(WAIT, 'pull_peer')


class PresenceBoard:
    """本实例的在场文件（只有自己写）+ 读对方的在场文件。主线程和心跳线程共用。"""

    def __init__(self, root, instance: str, peer: str, *, clock: Callable[[], datetime] = datetime.now,
                 lock_timeout: float = 10.0, write_retries: int = 3, write_backoff: float = 0.05):
        self.dir = Path(root) / 'team'
        self.instance = instance
        self.peer = peer
        self.clock = clock
        self.path = self.dir / f'{instance}.json'
        self.peer_path = self.dir / f'{peer}.json'
        self.pair_lock_path = self.dir / ('__'.join(sorted((instance, peer))) + '.lock')
        self.lock_timeout = lock_timeout
        self.write_retries = write_retries
        self.write_backoff = write_backoff
        self._doc: Optional[dict] = None
        self._mutex = threading.Lock()
        # 进程身份：对方和父进程（界面停止）据此确认读到的是同一个进程写的，重启后会换
        self.pid = os.getpid()
        self.boot_id = uuid.uuid4().hex
        # 循环信息由 _write 统一放进每一次写盘：publish 每次重建整个文件，不能靠各个调用方记得带上
        self._loop: Optional[dict] = None
        self._prev: Optional[dict] = None

    def publish(self, state: str, team_tasks: dict, *, task: str = None, role: str = None, token: str = None,
                since: datetime = None, until: datetime = None, partner_token: str = None,
                rest_until: datetime = None) -> bool:
        doc = {
            'version': 1, 'instance': self.instance, 'peer': self.peer, 'state': state,
            'task': task, 'role': role, 'token': token, 'since': _fmt(since), 'until': _fmt(until),
            'rest_until': _fmt(rest_until),
            'partner_token': partner_token, 'team_tasks': dump_team_tasks(team_tasks),
        }
        with self._mutex:
            self._doc = doc
            return self._write()

    def heartbeat(self) -> bool:
        with self._mutex:
            if self._doc is None:
                return False
            return self._write()

    def report_progress(self, count: int, done: bool = False) -> bool:
        """任务进行中写进当前状态（publish 换状态时清掉）；心跳会带着它一起刷新。"""
        with self._mutex:
            if self._doc is None:
                return False
            self._doc['progress'] = {'count': int(count), 'done': bool(done)}
            return self._write()

    def snapshot(self) -> Optional[dict]:
        with self._mutex:
            return dict(self._doc) if self._doc is not None else None

    def set_loop(self, loop: Optional[dict], prev: Optional[dict] = None) -> bool:
        """换掉要随在场文件发布的循环信息并立刻写盘。传进来的字典会被拷贝。"""
        with self._mutex:
            self._loop = json.loads(json.dumps(loop)) if loop is not None else None
            self._prev = json.loads(json.dumps(prev)) if prev is not None else None
            if self._doc is None:
                # 还没发布过状态（测试或最早的一次写）：先写一份空闲状态，免得循环信息没地方放
                self._doc = {'version': 1, 'instance': self.instance, 'peer': self.peer, 'state': IDLE,
                             'task': None, 'role': None, 'token': None, 'since': None, 'until': None,
                             'rest_until': None, 'partner_token': None, 'team_tasks': {}}
            return self._write()

    def _write(self) -> bool:
        self._doc['updated_at'] = _fmt(self.clock())
        self._doc['pid'] = self.pid
        self._doc['boot_id'] = self.boot_id
        for key, value in (('loop', self._loop), ('prev', self._prev)):
            if value is None:
                self._doc.pop(key, None)
            else:
                self._doc[key] = value
        data = json.dumps(self._doc, ensure_ascii=False, indent=2)
        for attempt in range(self.write_retries + 1):
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                with atomic_write(str(self.path), overwrite=True, encoding='utf-8', newline='') as f:
                    f.write(data)
                return True
            except PermissionError as exc:
                # 对方正好在读这个文件时 Windows 的替换会被拒，退避重试一下
                if attempt == self.write_retries:
                    logger.warning(f'Team sync cannot write presence: {exc}')
                    return False
                time.sleep(self.write_backoff * (2 ** attempt))
            except OSError as exc:
                logger.warning(f'Team sync cannot write presence: {exc}')
                return False
        return False

    def read_peer(self):
        """返回解析好的对方状态；文件不存在或损坏返回 None（当作不在线），短暂读不到返回 UNREADABLE。"""
        try:
            raw = self.peer_path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            return UNREADABLE
        try:
            return parse_presence(json.loads(raw.decode('utf-8')))
        except (UnicodeDecodeError, ValueError) as exc:
            logger.warning(f'Team sync presence of {self.peer} is invalid: {exc}')
            return None

    def step(self, me: dict, abort: bool = False) -> Decision:
        """在配对锁里读对方、判断、写下自己的新状态。拿不到锁就这一轮先等。"""
        lock = FileLock(str(self.pair_lock_path), timeout=self.lock_timeout)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            lock.acquire()
        except (Timeout, OSError):
            return Decision(WAIT, 'pair_lock_busy')
        try:
            peer = self.read_peer()
            decision = decide(me, peer, self.clock())
            if abort and decision.action != GO:
                decision = Decision(ABORT, 'config_changed')
            if decision.action == GO:
                self.publish(RUNNING, me['team_tasks'], task=me['task'], role=me['role'], token=me['token'],
                             since=me['since'], partner_token=peer.get('token'))
            elif decision.action == WAIT:
                self.publish(WAITING, me['team_tasks'], task=me['task'], role=me['role'], token=me['token'],
                             since=me['since'])
            else:
                self.publish(IDLE, me['team_tasks'], task=me['task'], until=decision.until)
            return decision
        finally:
            lock.release()


class Progress(NamedTuple):
    count: Optional[int]
    finished: bool


class TeamSession:
    """会合成功后的这一次组队：队长上报打了几次，队员据此决定什么时候走。

    任务只拿到这个对象，不碰在场文件格式。所有方法吞异常、读不到按「没结束」处理，
    任务原有的超时仍是兜底，组队同步出错不能让任务提前退出。
    """

    def __init__(self, board: PresenceBoard, task: str, role: str, token: str, peer_token: str):
        self.board = board
        self.task = task
        self.role = role
        self.token = token
        self.peer_token = peer_token
        self._last_count: Optional[int] = None

    def report(self, count: int, done: bool = False) -> None:
        try:
            self.board.report_progress(count, done)
        except Exception as exc:
            logger.warning(f'Team sync report progress failed: {exc}')

    def peer_progress(self) -> Progress:
        """对方这一次组队的进度。对方已经离开这次会合（换了任务 / 换了 token / 掉线）算结束。"""
        try:
            peer = self.board.read_peer()
            if peer is UNREADABLE:
                return Progress(self._last_count, False)
            if peer is None or peer['updated_at'] is None or self.board.clock() - peer['updated_at'] > STALE:
                return Progress(self._last_count, True)
            if peer.get('task') != self.task or peer.get('token') != self.peer_token:
                return Progress(self._last_count, True)
            if peer['state'] == WAITING:
                # 还在交接：对方比我晚一轮才把状态写成 running
                return Progress(self._last_count, False)
            if peer['state'] != RUNNING or peer.get('partner_token') != self.token:
                return Progress(self._last_count, True)
            progress = peer.get('progress')
            if progress is None:
                return Progress(self._last_count, False)
            self._last_count = progress['count']
            return Progress(progress['count'], progress['done'])
        except Exception as exc:
            logger.warning(f'Team sync read peer progress failed: {exc}')
            return Progress(self._last_count, False)


# 按实例名登记当前这次组队，任务从这里取（和 module.fatigue 的 manager 登记同一个做法）
_sessions: dict[str, TeamSession] = {}
_sessions_lock = threading.Lock()


def set_session(identity: str, session: TeamSession) -> None:
    with _sessions_lock:
        _sessions[identity] = session


def get_session(identity: str, task: str) -> Optional[TeamSession]:
    with _sessions_lock:
        session = _sessions.get(identity)
    return session if session is not None and session.task == task else None


def clear_session(identity: str) -> None:
    with _sessions_lock:
        _sessions.pop(identity, None)


def rendezvous(board: PresenceBoard, task: str, role: str, team_tasks: dict, *,
               should_abort: Callable[[], bool] = lambda: False, sleep: Callable[[float], None] = time.sleep,
               poll: float = POLL_INTERVAL, notify: Optional[Callable[[str], None]] = None,
               started_at: Optional[datetime] = None, loop: Optional[dict] = None) -> Decision:
    """在组队任务门口等对方，直到开始 / 推迟 / 配置变了中断。没有固定超时，等满 WAIT_NOTIFY 推送一次。

    started_at：本进程启动时刻，启动后 STARTUP_GRACE 内对方不在线也先等。
    loop：循环里的步骤带 {'id', 'step'}，门口要求对方在同一次循环的同一步骤上。
    """
    started = board.clock()
    me = {'instance': board.instance, 'task': task, 'role': role, 'token': uuid.uuid4().hex,
          'since': started, 'team_tasks': team_tasks, 'started_at': started_at, 'loop': loop}
    logger.info(f'Team sync: wait for {board.peer} before {task} ({role})')
    last_reason, last_log = None, started
    first = True
    notified = False
    while True:
        decision = board.step(me, abort=not first and should_abort())
        first = False
        if decision.action != WAIT:
            logger.info(f'Team sync: {task} -> {decision.action} ({decision.reason})'
                        + (f', until {_fmt(decision.until)}' if decision.until else ''))
            return decision
        now = board.clock()
        if decision.reason != last_reason or now - last_log >= WAIT_LOG_EVERY:
            logger.info(f'Team sync: waiting for {board.peer} before {task} ({decision.reason}, '
                        f'{int((now - started).total_seconds())}s)')
            last_reason, last_log = decision.reason, now
        if not notified and notify is not None and now - started >= WAIT_NOTIFY:
            notified = True
            minutes = int(WAIT_NOTIFY.total_seconds() // 60)
            try:
                notify(f'组队同步：{task} 已等待 {board.peer} {minutes} 分钟，对方还没进入同一任务，仍在继续等待')
            except Exception as exc:
                # 推送失败不能打断等待
                logger.warning(f'Team sync wait notice failed: {exc}')
        sleep(poll)
