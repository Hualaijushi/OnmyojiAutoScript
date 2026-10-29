# This Python file uses the following encoding: utf-8
"""调度器和组队会合之间的胶水（D030）。

哪些任务算组队任务：任务配置里某个分组有 `user_status`，且值是组队身份（队长 / 队员 / 契灵的交替身份）。
组队同步没开时什么文件都不写，调度器行为和以前完全一样。
这里任何异常都只记日志并放行：组队同步出错不能卡住调度器。
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from module.config.config_model import ConfigModel
from module.instance_sync.team import (
    COMPLEMENT, GO, HEARTBEAT_INTERVAL, IDLE, LOOP_LIVE, PAIR, POSTPONE, RUNNING, ROLES, STALE, WAITING, Decision,
    PresenceBoard, TeamSession, clear_session, decide, rendezvous, set_session,
)
from module.logger import logger

# 自己就要两边同时到场的任务（D029）。放进快照，让在组队门口等的对方知道该让路。
PAIRED_TASKS = frozenset({'XinLan'})

# 这些原因说明对方根本不会来，只靠日志没人会发现，每天每种原因推送一次
_NOTICES = {
    'peer_offline': '对方实例 {peer} 不在线（脚本没开、没开组队同步，或两边不在同一个安装目录），{task} 推迟',
    'peer_not_paired': '对方实例 {peer} 没有把本实例填成对方，{task} 推迟',
    'peer_task_off': '{peer} 没开 {task}，或它那边不是组队身份，{task} 推迟',
    'role_conflict': '两边 {task} 的身份不互补（要一队长一队员，或交替 1 配交替 2），{task} 推迟',
}


def task_role(task_data: dict) -> Optional[str]:
    for group in task_data.values():
        if isinstance(group, dict) and 'user_status' in group:
            status = getattr(group['user_status'], 'value', group['user_status'])
            return status if status in ROLES else None
    return None


def team_tasks(model) -> dict:
    """本实例所有组队任务（和 PAIRED_TASKS）的快照 {任务名: {role, enable, next_run}}，任务名和调度器里的一致（大驼峰）。"""
    result = {}
    for key, value in model.model_dump().items():
        if not isinstance(value, dict) or not isinstance(value.get('scheduler'), dict):
            continue
        name = ConfigModel.type(key)
        role = PAIR if name in PAIRED_TASKS else task_role(value)
        if role is None:
            continue
        next_run = value['scheduler'].get('next_run')
        if isinstance(next_run, str):
            next_run = datetime.strptime(next_run, '%Y-%m-%d %H:%M:%S')
        result[name] = {'role': role, 'enable': bool(value['scheduler'].get('enable')), 'next_run': next_run}
    return result


class TeamSync:
    def __init__(self, config_name: str, root=None, *, clock: Callable[[], datetime] = datetime.now,
                 sleep: Callable[[float], None] = time.sleep, started_at: Optional[datetime] = None):
        self.config_name = config_name
        # 本进程启动时刻：启动后一小段时间内对方不在线也先等，不推迟。None 表示没有启动宽限
        self.started_at = started_at
        self.root = Path(root) if root is not None else Path.cwd() / 'log' / 'instance_sync'
        self.clock = clock
        self.sleep = sleep
        self.board: Optional[PresenceBoard] = None
        self._warned: Optional[str] = None
        self._notified: set[tuple[date, str]] = set()
        self._heartbeat: Optional[threading.Thread] = None
        # 已经回应过的对方等待（token）：一次等待只拉一次、只打断一次空闲等待
        self._answered_token: Optional[str] = None
        # 循环控制器登记的当前步骤任务和位次函数：循环里的步骤不看任务自己的启用开关，快照里也带上位次
        self.loop_step_task: Optional[str] = None
        self.rank_of: Optional[Callable[[str], Optional[float]]] = None
        # 循环进行时，某个任务按本实例自己的位次是否严格高于当前步骤；不高于的任务不能被对方「拉」进来
        self.loop_allows: Optional[Callable[[str], bool]] = None

    def _tasks(self, config) -> dict:
        """组队任务快照；循环进行时把当前步骤算作已启用（它不受普通排期开关约束），并带上位次。"""
        tasks = team_tasks(config.model)
        if self.loop_step_task is not None:
            entry = tasks.get(self.loop_step_task)
            if entry is not None:
                entry['enable'] = True
            if self.rank_of is not None:
                for name, item in tasks.items():
                    item['rank'] = self.rank_of(name)
        return tasks

    def _board(self, config) -> Optional[PresenceBoard]:
        conf = config.model.script.team_sync
        peer = conf.peer_instance.strip()
        if not conf.enable:
            self.board = None
            return None
        if not peer or peer == self.config_name:
            if self._warned != peer:
                logger.warning(f'Team sync is enabled but peer instance {peer!r} is invalid, ignore it')
                self._warned = peer
            self.board = None
            return None
        if self.board is None or self.board.peer != peer:
            self.board = PresenceBoard(self.root, self.config_name, peer, clock=self.clock)
        return self.board

    def on_schedule(self, config, next_task: str, next_run: datetime, rest_until: datetime = None) -> None:
        """调度器选出下一个任务时写 idle：until 已过说明马上要跑，对方会继续等。

        rest_until：本实例在休息时段（休息时间窗 / 长休息）里的醒来时间，对方据此推迟到那时再会合。
        """
        try:
            board = self._board(config)
            if board is not None:
                board.publish(IDLE, self._tasks(config), task=next_task, until=next_run, rest_until=rest_until)
        except Exception as exc:
            logger.warning(f'Team sync publish failed: {exc}')

    def _peer_waiting(self, config) -> Optional[tuple[str, str]]:
        """对方正在某个组队任务门口等我、而这个任务在我这边还没到点时，返回 (任务名, 对方 token)。"""
        board = self._board(config)
        if board is None:
            return None
        peer = board.read_peer()
        if not isinstance(peer, dict):
            return None
        now = self.clock()
        if peer['updated_at'] is None or now - peer['updated_at'] > STALE:
            return None
        if peer.get('peer') != board.instance or peer['state'] != WAITING:
            return None
        task, token = peer.get('task'), peer.get('token')
        if not task or not token or token == self._answered_token:
            return None
        # 循环的步骤由两边的循环控制器各自安排，不靠「拉过来」
        peer_loop = peer.get('loop')
        if isinstance(peer_loop, dict) and peer_loop.get('state') in LOOP_LIVE and peer_loop.get('step_task') == task:
            return None
        if self.loop_allows is not None and not self.loop_allows(task):
            return None
        entry = team_tasks(config.model).get(task)
        if entry is None or not entry['enable'] or entry['role'] == PAIR:
            return None
        if COMPLEMENT.get(entry['role']) != peer.get('role'):
            return None
        if entry['next_run'] is not None and entry['next_run'] <= now:
            return None
        return task, token

    def peer_request(self, config) -> Optional[str]:
        """只读：对方在等我进入哪个任务（还没回应过的），没有返回 None。空闲等待每轮看一眼，有就打断。"""
        try:
            found = self._peer_waiting(config)
            return found[0] if found else None
        except Exception as exc:
            logger.warning(f'Team sync peer request check failed: {exc}')
            return None

    def answer(self, config) -> Optional[str]:
        """对方在门口等我时，把我这边的同一任务改成现在运行（按原来的调度顺序排，不插队）。"""
        try:
            found = self._peer_waiting(config)
            if found is None:
                return None
            task, token = found
            # 先记下 token：task_call 出错也不会每轮重试、反复打断空闲等待
            self._answered_token = token
            logger.info(f'Team sync: {self.board.peer} is waiting at {task}, call it now')
            config.task_call(task, force_call=False)
            return task
        except Exception as exc:
            logger.warning(f'Team sync answer failed: {exc}')
            return None

    def precheck(self, config, task: str, loop: Optional[dict] = None) -> Optional[Decision]:
        """唤醒模拟器 / 游戏之前只读看一眼对方：确定不会来就返回推迟，否则 None（照常准备再进门口）。

        不加锁、不写文件，只用来省掉「每 10 分钟拉起一次游戏又推迟」；真正的会合判断仍在 gate()。
        """
        try:
            board = self._board(config)
            if board is None:
                return None
            tasks = self._tasks(config)
            entry = tasks.get(task)
            if entry is None or entry['role'] == PAIR:
                return None
            me = {'instance': board.instance, 'task': task, 'role': entry['role'], 'token': '',
                  'since': self.clock(), 'team_tasks': tasks, 'started_at': self.started_at, 'loop': loop}
            decision = decide(me, board.read_peer(), self.clock())
            if decision.action != POSTPONE:
                return None
            logger.info(f'Team sync: {task} -> postpone before preparing ({decision.reason})')
            return decision
        except Exception as exc:
            logger.warning(f'Team sync precheck failed before {task}: {exc}')
            return None

    def gate(self, config, task: str, should_abort: Callable[[], bool] = lambda: False,
             loop: Optional[dict] = None) -> Decision:
        """任务开始前调用。组队任务在这里等对方；其它任务只写一下 running 就放行。

        loop：循环里的步骤带 {'id', 'step'}，门口只和同一次循环同一步骤的对方会合。
        """
        clear_session(self.config_name)
        try:
            board = self._board(config)
            if board is None:
                return Decision(GO, 'disabled')
            tasks = self._tasks(config)
            entry = tasks.get(task)
            if entry is None or entry['role'] == PAIR:
                board.publish(RUNNING, tasks, task=task)
                return Decision(GO, 'not_team_task')
            def notify(text: str) -> None:
                config.notifier.push(title=f'组队同步 {task}', content=f'<{self.config_name}> {text}')

            decision = rendezvous(board, task, entry['role'], tasks, should_abort=should_abort, sleep=self.sleep,
                                  notify=notify, started_at=self.started_at, loop=loop)
            if decision.action == GO and decision.reason in ('met', 'peer_started_with_me'):
                # 双方的 token 此刻已互相写在在场文件里，任务中途靠它们确认「对方还在这一次组队里」
                doc = board.snapshot() or {}
                if doc.get('token') and doc.get('partner_token'):
                    set_session(self.config_name, TeamSession(board, task, entry['role'], doc['token'],
                                                              doc['partner_token']))
            return decision
        except Exception as exc:
            logger.exception(f'Team sync failed before {task}, run it without waiting: {exc}')
            return Decision(GO, 'team_sync_error')

    def end_task(self) -> None:
        """任务结束（无论成败）后清掉这一次组队，免得下一个任务读到旧的。"""
        clear_session(self.config_name)

    def notice(self, task: str, decision: Decision) -> Optional[str]:
        """对方根本不会来的推迟原因，每天每种只返回一次提醒文字，其余返回 None。"""
        template = _NOTICES.get(decision.reason)
        if template is None or self.board is None:
            return None
        key = (self.clock().date(), decision.reason)
        if key in self._notified:
            return None
        self._notified.add(key)
        return '组队同步：' + template.format(peer=self.board.peer, task=task)

    def start_heartbeat(self, interval: float = HEARTBEAT_INTERVAL) -> None:
        """后台刷新心跳，任务执行中对方也能知道这边还在线。"""
        if self._heartbeat is not None:
            return

        def beat():
            while True:
                self.sleep(interval)
                board = self.board
                if board is not None:
                    board.heartbeat()

        self._heartbeat = threading.Thread(target=beat, name=f'team-sync-{self.config_name}', daemon=True)
        self._heartbeat.start()
