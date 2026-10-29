# This Python file uses the following encoding: utf-8
"""御魂 → 个人突破 的轻量循环控制器（脚本进程内，一个实例一个）。

只补业务衔接，不新建同步通道：配对、心跳、在场文件、原子写入都复用 D030（module.instance_sync.team）。
循环信息放在自己在场文件的 `loop` 字段（上一次的终态摘要放 `prev`），对方只读。

状态：FORMING（已提交请求、等对方加入）→ JOINED（队员已采用队长的 loop_id）→ ACTIVE（双方校验通过）
→ COMPLETED / FAILED / CANCELLED（终态，保留到下一次循环开始才移进 prev）。

步骤编号 idx：偶数是第 idx/2 批御魂，奇数是同一轮的个人突破。每一步的开始与恢复都由 Script.loop
先走现有的准备、疲劳，再经过本控制器的 barrier（双方都准备好才开始），御魂再经过 D030 的门口。
这里只在内存里保存状态：失败、取消或进程重启后循环不自动续跑，重新开始需要双方新的手动请求。
"""

from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, NamedTuple, Optional

from module.instance_sync.team import LOOP_LIVE, STALE, UNREADABLE, PresenceBoard, parse_presence
from module.logger import logger

FORMING, JOINED, ACTIVE = 'FORMING', 'JOINED', 'ACTIVE'
COMPLETED, FAILED, CANCELLED = 'COMPLETED', 'FAILED', 'CANCELLED'
TERMINAL = (COMPLETED, FAILED, CANCELLED)

OROCHI, REALM_RAID = 'Orochi', 'RealmRaid'
STEP_TASKS = (OROCHI, REALM_RAID)
# 恢复游戏的任务：循环期间不受「严格更高优先级」限制，否则 Restart 排在步骤后面就永远恢复不了
RECOVERY_TASKS = ('Restart',)

# 同一步骤没有正常完成就重跑的次数上限，防止对方一直没就绪时无限重来
MAX_STEP_RETRIES = 3
CHECK_INTERVAL = 2.0
STOP_ACK_TIMEOUT = 3.0
STOP_ACK_POLL = 0.2
WITHDRAW_PUBLISH_TRIES = 8
WITHDRAW_PUBLISH_BACKOFF = 0.05


class LoopParams(NamedTuple):
    role: str
    rounds: int
    target_min: int
    target_max: int


def step_task(idx: int) -> str:
    return OROCHI if idx % 2 == 0 else REALM_RAID


# 请求被拒绝时给用户看的中文说明（原因码仍是返回值 / 日志里的稳定标识）
REJECT_TEXT = {
    'team_sync_unavailable': '没有可用的组队同步：请在脚本设置的「组队同步」里开启并填对方实例名',
    'role_invalid': '八岐大蛇设置里的身份必须是队长或队员（单独刷不能开循环）',
    'rounds_invalid': '循环轮数不能小于 1',
    'target_range_invalid': '每批御魂的场数范围不对：最少场数要在 1 以上，且不能大于最多场数',
}


def reject_message(reason: str, params: Optional[LoopParams] = None) -> str:
    text = REJECT_TEXT.get(reason, reason)
    if reason == 'target_range_invalid' and params is not None:
        text += f'（当前最少 {params.target_min}、最多 {params.target_max}）'
    return f'循环请求被拒绝：{text}。请在八岐大蛇设置里改好后，重新打开「开始循环」（它是一次性开关，已自动关回）。'


def validate_params(params: LoopParams) -> Optional[str]:
    """参数有问题返回原因，没问题返回 None。"""
    if params.role not in ('leader', 'member'):
        return 'role_invalid'
    if params.rounds < 1:
        return 'rounds_invalid'
    if params.target_min < 1 or params.target_min > params.target_max:
        return 'target_range_invalid'
    return None


class LoopController:
    def __init__(self, identity: str, *, rng=None, notify: Optional[Callable[[str], None]] = None):
        self.identity = identity
        self.rng = rng if rng is not None else random
        self.notify = notify
        self.board: Optional[PresenceBoard] = None
        # 状态修改和落盘都在这把锁里做；锁里会取 PresenceBoard 的互斥锁，反过来板子不会调用控制器
        self._lock = threading.RLock()
        self.loop: Optional[dict] = None
        self.prev: Optional[dict] = None
        self._reset_runtime()

    def _reset_runtime(self) -> None:
        self.targets: dict[int, int] = {}
        self.counts: dict[int, int] = {}
        self.batch_seen: dict[int, bool] = {}
        self.retries: dict[int, int] = {}
        self.completed_idx: Optional[int] = None
        self.unrecovered: set[str] = set()
        self.recovery_pending = False
        self.run_recovery = False
        self.in_step = False
        self.attempt_possible = False
        self.bound = False
        self.peer_boot: Optional[str] = None
        self.deferred: list[str] = []
        self._last_check = 0.0
        self._member_checked = 0.0
        self._member_state = 'running'

    # ---------- 基本状态 ----------
    @property
    def live(self) -> bool:
        return self.loop is not None and self.loop['state'] in LOOP_LIVE

    @property
    def state(self) -> Optional[str]:
        return self.loop['state'] if self.loop else None

    @property
    def idx(self) -> int:
        return self.loop['idx']

    @property
    def last_idx(self) -> int:
        return self.loop['rounds'] * 2 - 1

    @property
    def awaiting_completion(self) -> bool:
        """最后一步已完成，只等对方也完成。"""
        return self.live and self.loop['done_idx'] >= self.last_idx

    @property
    def blocked(self) -> bool:
        return self.recovery_pending or bool(self.unrecovered)

    def current_step(self) -> Optional[str]:
        if not self.live or self.awaiting_completion:
            return None
        return step_task(self.idx)

    def is_step(self, task: str) -> bool:
        """调度器选出的这个任务是不是循环当前要跑的步骤。"""
        with self._lock:
            return self.current_step() == task and not self.blocked

    def bind_board(self, board: Optional[PresenceBoard]) -> None:
        with self._lock:
            self.board = board

    def _now(self) -> datetime:
        return self.board.clock() if self.board is not None else datetime.now()

    def loop_door(self) -> Optional[dict]:
        """给 D030 门口用的 {'id', 'step'}；不在循环步骤里返回 None。"""
        with self._lock:
            if not self.live or self.loop['state'] != ACTIVE or self.current_step() != OROCHI:
                return None
            return {'id': self.loop['id'], 'step': self.idx}

    # ---------- 发布 ----------
    def _publish(self) -> bool:
        if self.board is None:
            return False
        try:
            return bool(self.board.set_loop(self.loop, self.prev))
        except Exception as exc:
            logger.warning(f'Loop publish failed: {exc}')
            return False

    def _say(self, text: str) -> None:
        if self.notify is not None:
            try:
                self.notify(text)
            except Exception as exc:
                logger.warning(f'Loop notice failed: {exc}')

    def _finish(self, state: str, reason: Optional[str]) -> None:
        """进入终态。终态不会再被迟到的推进改回活动状态。"""
        if self.loop is None or self.loop['state'] in TERMINAL:
            return
        self.loop['state'] = state
        self.loop['reason'] = reason
        self.loop['ready'] = False
        self.loop['final'] = {'done_idx': self.loop['done_idx'], 'rounds': self.loop['rounds'],
                              'at': self._now().strftime('%Y-%m-%d %H:%M:%S')}
        self.recovery_pending = False
        self.in_step = False
        logger.info(f'Loop {self.loop["id"]}: {state} ({reason}), done_idx={self.loop["done_idx"]}')
        self._publish()
        if state == FAILED:
            self._say(f'御魂→个人突破循环已停止：{reason}')
        elif state == CANCELLED:
            self._say(f'御魂→个人突破循环已取消：{reason}')
        else:
            self._say('御魂→个人突破循环全部完成')

    # ---------- 开始 ----------
    def request_start(self, params: LoopParams, board: Optional[PresenceBoard]) -> str:
        """消费一次性开关后调用。返回 'started' / 'ignored' / 'invalid:<原因>'。"""
        with self._lock:
            if self.live:
                logger.info('Loop request ignored: a loop is already active')
                return 'ignored'
            if board is None:
                return self._invalid('team_sync_unavailable', params)
            problem = validate_params(params)
            if problem is not None:
                return self._invalid(problem, params)
            self.board = board
            if self.loop is not None:
                # 上一次的终态摘要保留给还没读到的对方，更早的丢弃
                self.prev = {k: self.loop.get(k) for k in ('id', 'state', 'reason', 'done_idx', 'rounds', 'final')}
            self._reset_runtime()
            leader = params.role == 'leader'
            self.loop = {
                'id': uuid_hex() if leader else None, 'state': FORMING, 'role': params.role,
                'rounds': params.rounds, 'tmin': params.target_min, 'tmax': params.target_max,
                'idx': 0, 'ready': False, 'done_idx': -1, 'step_task': OROCHI, 'step_rank': None,
                'target': None, 'batch': None, 'reason': None, 'final': None,
            }
            logger.info(f'Loop requested: role={params.role} rounds={params.rounds} '
                        f'target={params.target_min}-{params.target_max} id={self.loop["id"]}')
            self._publish()
            return 'started'

    def _invalid(self, reason: str, params: Optional[LoopParams] = None) -> str:
        logger.warning(f'Loop request rejected: {reason}')
        self._say(reject_message(reason, params))
        return f'invalid:{reason}'

    # ---------- 读对方 ----------
    def _peer(self):
        """返回 (kind, peer)。kind: ok / stale / absent / unpaired / unreadable。

        stale 也带上文件内容：对方已经写下的终态摘要不会因为它之后退出而作废。
        """
        board = self.board
        if board is None:
            return 'absent', None
        peer = board.read_peer()
        if peer is UNREADABLE:
            return 'unreadable', None
        if peer is None:
            return 'absent', None
        if peer.get('peer') != board.instance:
            return 'unpaired', peer
        if peer.get('updated_at') is None or board.clock() - peer['updated_at'] > STALE:
            return 'stale', peer
        return 'ok', peer

    def _match(self, peer: Optional[dict]) -> Optional[dict]:
        """对方发布的、属于我这次循环的那份信息（当前的或上一次的终态摘要）。"""
        my_id = self.loop['id'] if self.loop else None
        if peer is None or not my_id:
            return None
        for key in ('loop', 'prev'):
            doc = peer.get(key)
            if isinstance(doc, dict) and doc.get('id') == my_id:
                return doc
        return None

    def _same_params(self, doc: dict) -> bool:
        return all(doc.get(k) == self.loop[k] for k in ('rounds', 'tmin', 'tmax'))

    def tick(self) -> None:
        """推进加入流程、识别对方的取消 / 失败 / 离开 / 失联 / 完成。每个检查点都可以调用。"""
        with self._lock:
            if self.loop is None or self.loop['state'] in TERMINAL:
                return
            kind, peer = self._peer()
            if kind == 'unreadable':
                return
            match = self._match(peer)
            state = self.loop['state']

            if match is not None and match.get('state') in TERMINAL:
                self._mirror_terminal(match)
                return
            if state == FORMING and kind == 'ok':
                if self.loop['role'] == 'leader':
                    self._leader_forming(match, peer)
                else:
                    self._member_forming(peer)
                if self.loop['state'] in TERMINAL:
                    return
                state = self.loop['state']
                # 队员刚采用了队长的编号：用新编号重新找对方发布的那份信息
                match = self._match(peer)
            if state == JOINED and match is not None and match.get('state') == ACTIVE:
                self.loop['state'] = ACTIVE
                self._publish()
                state = ACTIVE
            if self.bound:
                self._check_bound(kind, peer, match)
            if self.loop['state'] == ACTIVE and self.awaiting_completion:
                if match is not None and match.get('done_idx', -1) >= self.last_idx:
                    self._finish(COMPLETED, None)

    def _mirror_terminal(self, match: dict) -> None:
        state, reason = match.get('state'), match.get('reason')
        if state == COMPLETED:
            if self.loop['done_idx'] >= self.last_idx:
                self._finish(COMPLETED, None)
            else:
                self._finish(FAILED, 'peer_inconsistent')
        elif state == CANCELLED:
            self._finish(CANCELLED, 'peer_cancelled')
        else:
            self._finish(FAILED, f'peer_failed:{reason}')

    def _leader_forming(self, match: Optional[dict], peer: dict) -> None:
        if match is not None:
            if match.get('state') in (JOINED, ACTIVE):
                if not self._same_params(match):
                    self._finish(FAILED, 'config_mismatch')
                    return
                self._bind(peer)
                self.loop['state'] = ACTIVE
                self._publish()
            return
        if self._role_conflict(peer.get('loop')):
            self._finish(FAILED, 'role_conflict')

    def _role_conflict(self, other) -> bool:
        """对方的循环和我是同一个身份（两个队长或两个队员）。

        先发现冲突的一边会把循环写成失败，另一边读到的已经是终态，所以最近刚因 role_conflict 失败的
        同身份循环也算冲突；时间过了很久的旧失败记录不算，免得挡住改正配置后的新请求。
        """
        if not isinstance(other, dict) or other.get('role') != self.loop['role']:
            return False
        if other.get('state') in LOOP_LIVE:
            return True
        final = other.get('final')
        if other.get('state') == FAILED and other.get('reason') == 'role_conflict' and isinstance(final, dict):
            try:
                at = datetime.strptime(final.get('at'), '%Y-%m-%d %H:%M:%S')
            except (TypeError, ValueError):
                return False
            return abs(self._now() - at) <= STALE
        return False

    def _member_forming(self, peer: dict) -> None:
        other = peer.get('loop')
        if self._role_conflict(other):
            self._finish(FAILED, 'role_conflict')
            return
        if not isinstance(other, dict) or other.get('state') not in LOOP_LIVE:
            return
        if other.get('role') != 'leader' or other.get('state') != FORMING or not other.get('id'):
            return
        # 先采用队长的编号再校验：参数不一致时队长按编号能读到这边的失败原因
        self.loop['id'] = other['id']
        self._bind(peer)
        if not self._same_params(other):
            self._finish(FAILED, 'config_mismatch')
            return
        self.loop['state'] = JOINED
        self._publish()

    def _bind(self, peer: dict) -> None:
        self.bound = True
        self.peer_boot = peer.get('boot_id')

    def _check_bound(self, kind: str, peer: Optional[dict], match: Optional[dict]) -> None:
        """已经绑定本次参与者之后，对方退出、重启、失联都要停止；绑定之前只是还没来，继续等。"""
        if kind in ('absent', 'unpaired'):
            self._finish(FAILED, 'peer_left')
        elif kind == 'stale':
            self._finish(FAILED, 'peer_lost')
        elif self.peer_boot and peer.get('boot_id') and peer['boot_id'] != self.peer_boot:
            self._finish(FAILED, 'peer_restarted')
        elif match is None:
            self._finish(FAILED, 'peer_left')

    # ---------- 步骤会合 ----------
    def barrier(self) -> str:
        """当前步骤的会合，非阻塞，调用方每隔几秒再调。

        返回 'go'（双方都准备好）/ 'wait' / 'skip'（队长已完成这批，队员不用再跑）/ 'failed' / 'cancelled' / 'idle'（没有步骤）。
        """
        with self._lock:
            self.tick()
            if self.loop is None:
                return 'idle'
            state = self.loop['state']
            if state == FAILED:
                return 'failed'
            if state == CANCELLED:
                return 'cancelled'
            if state == COMPLETED or self.awaiting_completion:
                return 'idle'
            if state != ACTIVE:
                return 'wait'
            idx = self.idx
            leader_batch = idx % 2 == 0 and self.loop['role'] == 'leader'
            if not self.loop['ready']:
                if leader_batch:
                    self._ensure_target(idx)
                    self.loop['batch'] = None
                self.loop['step_task'] = step_task(idx)
                self.loop['ready'] = True
                self._publish()
            kind, peer = self._peer()
            match = self._match(peer) if kind == 'ok' else None
            if match is None or match.get('state') not in LOOP_LIVE:
                return 'wait'
            if match.get('done_idx', -1) < idx - 1:
                return 'wait'
            if idx % 2 == 0 and self.loop['role'] == 'member':
                batch = match.get('batch')
                if isinstance(batch, dict) and batch.get('idx') == idx and batch.get('done') and batch.get('ok'):
                    self.batch_seen[idx] = True
                    self.completed_idx = idx
                    return 'skip'
                target = match.get('target')
                if not isinstance(target, dict) or target.get('idx') != idx:
                    return 'wait'
                self.targets.setdefault(idx, int(target['n']))
            peer_idx = match.get('idx', -1)
            if peer_idx > idx or (peer_idx == idx and match.get('ready')):
                return 'go'
            return 'wait'

    def _ensure_target(self, idx: int) -> None:
        if idx not in self.targets:
            self.targets[idx] = self.rng.randint(self.loop['tmin'], self.loop['tmax'])
            logger.info(f'Loop batch {idx // 2 + 1}: target {self.targets[idx]}')
        self.loop['target'] = {'idx': idx, 'n': self.targets[idx]}

    def step_target(self) -> Optional[int]:
        with self._lock:
            return self.targets.get(self.idx) if self.live else None

    def begin_run(self) -> bool:
        """步骤真正开始。返回 False 表示不能开始（上一次开战尝试留下了无法确认的计数）。"""
        with self._lock:
            if not self.live:
                return False
            self.in_step = True
            self.run_recovery = False
            if self.attempt_possible:
                self._finish(FAILED, 'count_uncertain')
                return False
            return True

    def accept_skip(self) -> None:
        """队长已经完成这一批（有完成记录），队员不用再跑：直接按完成事实推进。"""
        with self._lock:
            self._advance_if_completed()

    def abandon_run(self) -> None:
        """准备阶段让出（被更高优先级任务插队、配置变化等）：步骤没有开始，撤回已发布的就绪。"""
        with self._lock:
            self.in_step = False
            self.withdraw_ready()

    def withdraw_ready(self) -> None:
        """撤回本步骤的就绪：让出 / 重载 / 准备退出时调用，对端不能再凭旧的 ready 放行。

        已经开始的步骤（in_step）不撤回，也不会因为后来出现高优先级任务而被中途抢占。
        恢复后重新经过疲劳和会合，会再次发布就绪。
        """
        with self._lock:
            if not self.live or self.in_step or not self.loop.get('ready'):
                return
            self.loop['ready'] = False
            # 对方正好在读文件时 Windows 的替换会被拒，写盘失败就文件里还是旧的 ready：多试几次，
            # 否则对端会凭旧的就绪放行
            for _ in range(WITHDRAW_PUBLISH_TRIES):
                if self._publish():
                    break
                time.sleep(WITHDRAW_PUBLISH_BACKOFF)

    # ---------- 任务里的检查点 ----------
    def check(self, force: bool = False) -> bool:
        """任务在每一场开始前调用：循环还有效返回 True，失败 / 取消返回 False（当前这场允许打完）。"""
        with self._lock:
            now = time.monotonic()
            if force or now - self._last_check >= CHECK_INTERVAL:
                self._last_check = now
                self.tick()
            return self.live

    # 队长的可信计数：每次邀请前记下可能开战，确认战斗并且看到结算才算一场
    def remaining(self) -> int:
        with self._lock:
            return max(self.targets.get(self.idx, 0) - self.counts.get(self.idx, 0), 0)

    def attempt_begin(self) -> None:
        with self._lock:
            self.attempt_possible = True

    def attempt_cancelled(self, fire_clicked: bool) -> None:
        """邀请没有进入战斗。没点过挑战按钮可以撤销记录；点过就无法确认战斗有没有开始。"""
        with self._lock:
            if fire_clicked:
                self._finish(FAILED, 'count_uncertain')
            else:
                self.attempt_possible = False

    def attempt_resolved(self, *, fire_clicked: bool, battle_seen: bool, result_seen: bool) -> str:
        """一次邀请进入战斗流程之后，按证据顺序决定这一场怎么算。返回 'counted' / 'ignored' / 'uncertain'。

        证据链：本机点过挑战按钮 → 看到准备 / 战斗页（确认是新战斗）→ 再看到结算 / 奖励页，才计一场。
        既没点过挑战按钮、也没看到准备 / 战斗页，只见到结算页：是上一场残留的结算页，不计数也不算失败。
        其余（点过却没确认战斗、确认战斗却没看到结算、没点过却见到战斗）都无法确认，保守停止。
        """
        with self._lock:
            if not fire_clicked and not battle_seen:
                self.attempt_possible = False
                return 'ignored'
            if fire_clicked and battle_seen and result_seen:
                self.battle_settled(True)
                return 'counted'
            self.battle_settled(False)
            return 'uncertain'

    def battle_settled(self, result_seen: bool) -> None:
        with self._lock:
            if not self.live:
                return
            if not result_seen:
                self._finish(FAILED, 'count_uncertain')
                return
            self.attempt_possible = False
            idx = self.idx
            self.counts[idx] = self.counts.get(idx, 0) + 1
            self.loop['batch'] = self._batch(idx, done=False, ok=False)
            self._publish()

    def _batch(self, idx: int, done: bool, ok: bool) -> dict:
        return {'idx': idx, 'count': self.counts.get(idx, 0), 'target': self.targets.get(idx),
                'done': done, 'ok': ok}

    def report_batch(self, ok_if_reached: bool) -> None:
        """队长这一批结束。只有可信计数达到目标、并且没有别的失败，才算这一批完成。"""
        with self._lock:
            if not self.live or self.loop['role'] != 'leader':
                return
            idx = self.idx
            ok = ok_if_reached and not self.attempt_possible and \
                self.counts.get(idx, 0) >= self.targets.get(idx, 1 << 30)
            self.batch_seen[idx] = ok
            if ok:
                self.completed_idx = idx
            self.loop['batch'] = self._batch(idx, done=True, ok=ok)
            # 这一批结束后不再是「准备好了」：没完成时队员据此等队长重新就绪，不会拿旧状态当会合
            self.loop['ready'] = False
            self._publish()

    def member_batch_state(self) -> str:
        """队员问：这一批结束了吗。返回 'running' / 'done' / 'stop'（循环已失败或取消）。"""
        with self._lock:
            if not self.check():
                return 'stop'
            now = time.monotonic()
            if now - self._member_checked < CHECK_INTERVAL:
                return self._member_state
            self._member_checked = now
            kind, peer = self._peer()
            match = self._match(peer) if kind == 'ok' else None
            batch = match.get('batch') if match else None
            state = 'running'
            if isinstance(batch, dict) and batch.get('idx') == self.idx and batch.get('done'):
                ok = bool(batch.get('ok'))
                self.batch_seen[self.idx] = ok
                if ok:
                    self.completed_idx = self.idx
                state = 'done'
            self._member_state = state
            return state

    # ---------- 一步结束之后 ----------
    def note_recovery(self, restart_enabled: bool) -> bool:
        """异常处理里安排了 Restart：恢复结束之前不推进步骤、不解除阻塞。返回是否登记成功。"""
        with self._lock:
            if not self.live:
                return False
            if not restart_enabled:
                self._finish(FAILED, 'restart_disabled')
                return False
            self.recovery_pending = True
            self.run_recovery = True
            return True

    def after_run(self, command: str, *, ended: bool, delay_success: Optional[bool],
                  restart_status: Optional[str] = None) -> None:
        """每个任务跑完后由 Script.loop 调用。

        ended：任务正常走到自己的结束出口（TaskEnd）；delay_success：任务自己通过 task_delay 记下的
        success（None 表示没有记）。Script.run 的布尔返回值和「下次运行时间排到了未来」都不算业务成功。
        """
        with self._lock:
            needs_recovery, self.run_recovery = self.run_recovery, False
            was_step, self.in_step = self.in_step, False
            if not self.live:
                return
            if command in RECOVERY_TASKS:
                if restart_status == 'recovered':
                    self.recovery_pending = False
                    self._advance_if_completed()
                return
            if was_step and command == self.current_step():
                self._settle_step(command, ended, needs_recovery)
            else:
                self._settle_inserted(command, ended, delay_success, needs_recovery)

    def _settle_step(self, command: str, ended: bool, needs_recovery: bool) -> None:
        idx = self.idx
        if command == REALM_RAID and ended:
            # 个人突破正常走到自己的结束出口就算完成；先完成后触发恢复时完成事实也保留，恢复结束后才推进
            self.completed_idx = idx
        if self.recovery_pending:
            return
        if self.completed_idx == idx:
            self._advance()
            return
        if not ended:
            self._finish(FAILED, 'unknown_result')
            return
        self.retries[idx] = self.retries.get(idx, 0) + 1
        if self.retries[idx] > MAX_STEP_RETRIES:
            self._finish(FAILED, 'step_retry_exceeded')
        else:
            logger.info(f'Loop step {idx} ended without completion, retry {self.retries[idx]}')
            self.loop['ready'] = False
            self._publish()

    def _settle_inserted(self, command: str, ended: bool, delay_success: Optional[bool], needs_recovery: bool) -> None:
        if needs_recovery:
            if delay_success is True:
                self.unrecovered.discard(command)
            else:
                self.unrecovered.add(command)
            return
        if not ended or delay_success is None:
            self._finish(FAILED, f'unknown_task_result:{command}')
        elif delay_success:
            self.unrecovered.discard(command)
        else:
            self.unrecovered.add(command)
            logger.info(f'Loop blocked by unrecovered task: {sorted(self.unrecovered)}')

    def _advance_if_completed(self) -> None:
        if self.live and self.completed_idx == self.idx and not self.blocked:
            self._advance()

    def _advance(self) -> None:
        idx = self.idx
        self.loop['done_idx'] = idx
        self.completed_idx = None
        self.attempt_possible = False
        self._member_state = 'running'
        if idx < self.last_idx:
            self.loop['idx'] = idx + 1
            self.loop['ready'] = False
            self.loop['step_task'] = step_task(idx + 1)
        logger.info(f'Loop step {idx} done')
        self._publish()
        self.tick()

    # ---------- 调度器钩子 ----------
    def schedule_hook(self, config, pending: list, waiting: list):
        """Config.update_scheduler 的末尾调用：循环期间暂停普通御魂 / 个人突破，只在步骤边界插入严格更高优先级的任务。"""
        with self._lock:
            if not self.live:
                return pending, waiting
            kept_pending = [f for f in pending if f.command not in STEP_TASKS]
            kept_waiting = [f for f in waiting if f.command not in STEP_TASKS]
            # 等对方完成最后一步时 current_step 为空，但循环仍然活动：位次参照最后一步，不放开低优先级任务
            task = self.current_step() or step_task(self.idx)
            now = datetime.now()
            step_fn = self._step_function(config, task, now)
            if step_fn is None:
                return pending, waiting
            no_step = self.blocked or self.current_step() is None
            from module.config.scheduler import TaskScheduler
            from tasks.Script.config_optimization import ScheduleRule
            rule = config.model.script.optimization.schedule_rule
            ordered = TaskScheduler.schedule(rule, kept_pending + [step_fn])
            pos = next((i for i, f in enumerate(ordered) if f is step_fn), len(ordered))
            higher = ordered[:pos]
            if rule == ScheduleRule.PRIORITY:
                higher = [f for f in higher if f.priority < step_fn.priority or f.command in RECOVERY_TASKS]
            elif rule == ScheduleRule.FIFO:
                higher = [f for f in higher if f.command in RECOVERY_TASKS]
            # 恢复游戏的任务不受位次限制，且排在最前（它排在步骤后面会永远恢复不了）
            recovery = [f for f in kept_pending if f.command in RECOVERY_TASKS]
            higher = recovery + [f for f in self._drop_deferred(config, higher) if f not in recovery]
            result = higher if no_step else higher + [step_fn]
            if self.blocked:
                # 被未恢复的任务挡住时，只等能解除阻塞的任务（恢复游戏 / 未恢复的任务自己）
                new_waiting = [f for f in kept_waiting if f.command in RECOVERY_TASKS or f.command in self.unrecovered]
            elif no_step:
                # 等对方完成最后一步：只等位次严格更高的任务
                new_waiting = [f for f in kept_waiting if self._outranks(config, f.command, task)]
            else:
                new_waiting = kept_waiting
            if not result and not new_waiting:
                # 没有任何可运行或可等待的任务：给调度器一个远在未来的占位项，进入明确的等待路径
                # （调度器没有任务可选会当成「没有启用任何任务」报错；占位项永远不会到点）
                return [], [self._step_function(config, OROCHI, now + timedelta(hours=1))]
            return result, new_waiting

    def _step_function(self, config, task: str, now: datetime):
        from module.config.config import Function
        from module.config.utils import convert_to_underscore
        key = convert_to_underscore(task)
        group = getattr(config.model, key, None)
        scheduler = getattr(group, 'scheduler', None)
        if scheduler is None:
            return None
        data = {'scheduler': {'enable': True, 'next_run': now - timedelta(seconds=1), 'priority': scheduler.priority}}
        return Function(key, data)

    def _drop_deferred(self, config, higher: list) -> list:
        """组队任务只有两边各自都认为它严格更高才插入；对方不这么认为就推迟它，不强行插入。"""
        board = self.board
        if board is None or not higher:
            return higher
        kind, peer = self._peer()
        theirs = peer.get('loop') if kind == 'ok' else None
        peer_step_rank = theirs.get('step_rank') if isinstance(theirs, dict) else None
        kept = []
        for func in higher:
            entry = peer['team_tasks'].get(func.command) if kind == 'ok' else None
            if entry and entry['enable'] and entry.get('rank') is not None and peer_step_rank is not None \
                    and not entry['rank'] < peer_step_rank:
                self.deferred.append(func.command)
                continue
            kept.append(func)
        return kept

    def pop_deferred(self) -> list[str]:
        with self._lock:
            names, self.deferred = list(dict.fromkeys(self.deferred)), []
            return names

    def _outranks(self, config, name: str, step: str) -> bool:
        """任务按本实例的位次是否严格高于步骤（先来先服务规则下没有位次，一律不高于，恢复任务除外）。"""
        if name in RECOVERY_TASKS:
            return True
        rank = self.rank_of(config)
        mine, theirs = rank(name), rank(step)
        return mine is not None and theirs is not None and mine < theirs

    def outranks_current_step(self, config, name: str) -> bool:
        """给门口的「拉人」用：循环进行时，只有严格高于当前步骤的任务才能被对方拉进来。"""
        with self._lock:
            if not self.live:
                return True
            return self._outranks(config, name, self.current_step() or step_task(self.idx))

    def rank_of(self, config) -> Callable[[str], Optional[float]]:
        """任务在本实例调度顺序里的位次（越小越靠前）；先来先服务模式没有位次。"""
        from module.config.scheduler import TaskScheduler
        from tasks.Script.config_optimization import ScheduleRule
        rule = config.model.script.optimization.schedule_rule
        order = {str(item[0]).lower(): i for i, item in enumerate(TaskScheduler.filter.filter) if item and item[0]}

        def rank(name: str) -> Optional[float]:
            if rule == ScheduleRule.FILTER:
                return order.get(name.lower())
            if rule == ScheduleRule.PRIORITY:
                from module.config.utils import convert_to_underscore
                scheduler = getattr(getattr(config.model, convert_to_underscore(name), None), 'scheduler', None)
                return getattr(scheduler, 'priority', None)
            return None

        return rank

    def publish_step_rank(self, rank: Optional[float]) -> None:
        with self._lock:
            if self.live and self.loop.get('step_rank') != rank:
                self.loop['step_rank'] = rank
                self._publish()

    # ---------- 取消 ----------
    def cancel_by_command(self, command: dict) -> bool:
        """界面停止时父进程发来的取消命令。boot_id / loop_id 对不上（比如残留的旧命令）一律忽略。"""
        with self._lock:
            if self.board is None or self.loop is None or self.loop['state'] in TERMINAL:
                return False
            if command.get('boot_id') != self.board.boot_id or command.get('loop_id') != self.loop['id']:
                logger.info('Loop cancel command ignored: target does not match this loop')
                return False
            self._finish(CANCELLED, command.get('reason') or 'ui_stop')
            return True

    def fail(self, reason: str) -> None:
        with self._lock:
            self._finish(FAILED, reason)

    def snapshot(self) -> Optional[dict]:
        with self._lock:
            return json.loads(json.dumps(self.loop)) if self.loop is not None else None


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex


# ---------- 登记：任务按实例名取当前的循环控制器 ----------
_controllers: dict[str, LoopController] = {}
_controllers_lock = threading.Lock()


def set_controller(identity: str, controller: LoopController) -> None:
    with _controllers_lock:
        _controllers[identity] = controller


def get_step_controller(identity: str, task: str) -> Optional[LoopController]:
    """任务只在自己正是循环当前步骤、并且步骤已开始时拿到控制器；普通运行拿到 None，走原来的逻辑。"""
    with _controllers_lock:
        controller = _controllers.get(identity)
    if controller is None:
        return None
    with controller._lock:
        if controller.in_step and controller.live and controller.current_step() == task:
            return controller
    return None


# ---------- 界面停止：先尽力通知对端取消 ----------
def read_own_presence(root, instance: str) -> Optional[dict]:
    """父进程只读自己实例的在场文件，读不到或格式不对返回 None。"""
    path = Path(root) / 'team' / f'{instance}.json'
    try:
        return parse_presence(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return None


def build_cancel_command(root, instance: str, pid: Optional[int]) -> Optional[dict]:
    """在场文件里有未结束的循环、并且是这个进程写的，才返回取消命令（带上 boot_id / loop_id / pid）。"""
    doc = read_own_presence(root, instance)
    if doc is None or pid is None or doc.get('pid') != pid:
        return None
    loop = doc.get('loop')
    if not isinstance(loop, dict) or loop.get('state') not in LOOP_LIVE:
        return None
    return {'command': 'loop_cancel', 'boot_id': doc.get('boot_id'), 'loop_id': loop.get('id'), 'pid': pid,
            'reason': 'ui_stop'}


def cancel_acknowledged(root, instance: str, command: dict) -> bool:
    doc = read_own_presence(root, instance)
    if doc is None or doc.get('boot_id') != command['boot_id'] or doc.get('pid') != command['pid']:
        return False
    loop = doc.get('loop')
    return isinstance(loop, dict) and loop.get('id') == command['loop_id'] and loop.get('state') == CANCELLED


async def notify_cancel(root, instance: str, pid: Optional[int], command_queue, *, sleep,
                        timeout: float = STOP_ACK_TIMEOUT, poll: float = STOP_ACK_POLL) -> str:
    """发取消命令并有限等待确认。没有活动循环时立刻返回，保持原来的停止行为。

    返回 'none'（没有活动循环）/ 'acked' / 'timeout'。超时也由调用方照常终止进程，对端按失联规则处理。
    sleep 必须是协程版的睡眠，不能阻塞服务端事件循环。
    """
    command = build_cancel_command(root, instance, pid)
    if command is None:
        return 'none'
    try:
        command_queue.put(command)
    except Exception as exc:
        logger.warning(f'Loop cancel command not sent: {exc}')
        return 'timeout'
    waited = 0.0
    while waited < timeout:
        await sleep(poll)
        waited += poll
        if cancel_acknowledged(root, instance, command):
            return 'acked'
    return 'timeout'
