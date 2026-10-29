# This Python file uses the following encoding: utf-8
"""双实例同步协调器：把账本、状态机和业务适配器串成「一次任务运行内的一整轮同步」。

`SyncCoordinator.run()` 返回 `SyncResult`，**不为同步本身的失败抛业务异常**：
- 账本问题（损坏 / 缺失 / 锁超时 / 写失败）→ `ledger_*` 失败结果，当天不再自动重来；
- 适配器 / 设备抛出的异常**不吞**：先尽力把整轮写成 failed（让对端在一个轮询周期内退出），再原样上抛；
- 协作式取消（对端失败 / 本进程被更新会话取代）→ 失败结果。

D015 分层：等待（轮询）、重试（30 秒间隔 + 总预算）、恢复（prepared 意图）各自只有一个 owner，都在本文件；
时间由注入的 clock / sleep 提供，核心不读系统时钟以外的任何东西，也不碰设备。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from module.instance_sync import state_machine as sm
from module.instance_sync.adapter import EV_DONE, EV_NOT_DONE, Evidence, SyncAdapter, SyncContext
from module.instance_sync.errors import (
    InvariantViolation, LedgerCorruptError, LedgerError, LedgerLostError, LedgerWriteError, SyncCancelled, SyncError,
)
from module.instance_sync.journal import Journal
from module.instance_sync.ledger import Ledger
from module.logger import logger

# 纯等待超过这个时长后通知适配器（让它重置设备的卡死计时；设备守卫只在截图时检查，但等待后的第一批截图会带着旧计时）
LONG_WAIT_SECONDS = 30.0
# 兜底：等待循环正常都被账本里的截止时间（会合 600 秒 / 预算 180 秒）终止，最长也就几百次轮询；
# 只有注入了不推进的 clock、或截止时间逻辑被改坏时才会走到这里，避免无界空转地反复锁账本
_MAX_POLLS = 20_000
_MAX_STEPS = 10_000

# SyncResult.status
S_COMPLETED = 'completed'
S_ALREADY = 'already_completed'
S_FAILED = 'failed'

# SyncResult.next_action：任务据此决定 set_next_run
NEXT_DONE = 'done'
NEXT_RETRY = 'retry_later'
NEXT_DEFER = 'defer_next_day'

# 失败结果里的原因（账本之外产生的）
REASON_UNSAFE_PRIOR = 'unsafe_prior_round'
REASON_ROUND_CAP = 'round_cap'
REASON_LEDGER_CORRUPT = 'ledger_corrupt'
REASON_LEDGER_LOST = 'ledger_lost'
REASON_LEDGER_UNAVAILABLE = 'ledger_unavailable'
REASON_LEDGER_WRITE = 'ledger_write_failed'
REASON_INTERNAL = 'internal_error'

# 这些原因重试没有意义（配置不一致 / 需人工 / 账本不可用），直接排到下一个业务日
_DEFER_REASONS = frozenset({
    sm.R_HANDSHAKE, REASON_UNSAFE_PRIOR, REASON_ROUND_CAP, REASON_LEDGER_CORRUPT, REASON_LEDGER_LOST,
    REASON_LEDGER_UNAVAILABLE, REASON_LEDGER_WRITE, REASON_INTERNAL,
})


@dataclass(frozen=True)
class SyncResult:
    status: str
    reason: str
    next_action: str
    round_id: Optional[str] = None
    seq: Optional[int] = None
    detail: str = ''

    @property
    def ok(self) -> bool:
        return self.status in (S_COMPLETED, S_ALREADY)


@dataclass(frozen=True)
class AckResult:
    """`acknowledge_unsafe` 的结果。acknowledged=False 时 reason 说明为什么没有可确认的 / 为什么没确认成。"""
    acknowledged: bool
    reason: str
    round_id: Optional[str] = None
    seq: Optional[int] = None


class SyncCoordinator:
    def __init__(self, adapter: SyncAdapter, *, instance: str, members: Iterable[tuple[str, str]],
                 rendezvous_timeout: float = 600.0, root=None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 poll_interval: float = 1.0, lock_timeout: float = 10.0,
                 new_id: Optional[Callable[[], str]] = None, session_id: Optional[str] = None):
        self.adapter = adapter
        self.instance = instance
        self.members = sm.canonical_members(members)
        if instance not in {m['instance'] for m in self.members}:
            raise ValueError(f'instance {instance!r} is not one of the two members')
        if rendezvous_timeout <= 0 or poll_interval <= 0:
            raise ValueError('rendezvous_timeout and poll_interval must be positive')
        self.protocol = sm.make_protocol(adapter.protocol_params())
        self.rendezvous_timeout = float(rendezvous_timeout)
        self.root = Path(root) if root is not None else Path.cwd() / 'log' / 'instance_sync'
        self.clock = clock
        self.sleep = sleep
        self.poll_interval = poll_interval
        self.lock_timeout = lock_timeout
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._actor = sm.Actor(instance, session_id or uuid.uuid4().hex)
        self.round_id: Optional[str] = None
        self.rendezvous_deadline_at: Optional[float] = None
        self.deadline_at: Optional[float] = None
        self._ledger: Optional[Ledger] = None
        self._journal: Optional[Journal] = None
        self._resumed = False
        self._ctx = SyncContext(self)

    # ------------------------------------------------------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------------------------------------------------------
    def run(self) -> SyncResult:
        try:
            return self._run()
        except SyncCancelled as exc:
            return self._cancelled_result(exc)
        except LedgerError as exc:
            return self._ledger_result(exc)
        except SyncError as exc:
            # 不变式被违反 = 同步核心 / 调用方的缺陷。如实记录并安全失败，不让它把整个实例带崩
            logger.exception(f'Instance sync internal error: {exc}')
            self._best_effort_fail(REASON_INTERNAL)
            return SyncResult(S_FAILED, REASON_INTERNAL, NEXT_DEFER, self.round_id, detail=str(exc))
        except BaseException as exc:
            # 适配器 / 设备异常：先让对端尽快知道，再原样上抛（D015：异常透传）
            self._best_effort_fail(f'{sm.R_EXCEPTION}:{type(exc).__name__}')
            raise

    def _open_ledger(self) -> None:
        adapter = self.adapter
        day = adapter.business_day(self.clock())
        key = sm.make_key(day, adapter.business_id, self.members)
        self._journal = Journal(self.root / f'{self.instance}.journal.jsonl', clock=self.clock)
        self._ledger = Ledger(self.root, key, self._journal, clock=self.clock, sleep=self.sleep,
                              lock_timeout=self.lock_timeout)

    def acknowledge_unsafe(self, reason: str = '') -> 'AckResult':
        """人工确认：当天最后一轮可能已发出的请求我核对过了，下次 `run()` 可以再开新轮。

        调用方（任务）负责「一次性」语义：读到开关就调用一次，不管结果如何都把开关关回去，
        否则残留的开关会在之后某次新的 unsafe 出现时绕过人工检查。不绕过每天的轮次上限。
        账本问题同样转成结果对象，不抛。
        """
        try:
            self._open_ledger()
            result, _ = self._ledger.transact(
                lambda doc, now: sm.op_acknowledge_unsafe(doc, now, self._actor, reason=reason),
                create_if_missing=True)
        except LedgerError as exc:
            return AckResult(False, self._ledger_result(exc).reason)
        except InvariantViolation as exc:
            logger.exception(f'Instance sync internal error: {exc}')
            return AckResult(False, REASON_INTERNAL)
        info = result.value or {}
        if not result.ok:
            logger.info(f'Instance sync [{self.instance}] nothing to acknowledge: {result.reason}')
            return AckResult(False, result.reason, info.get('round_id'), info.get('seq'))
        self._journal.append(self._ledger.name, info['round_id'], 'acknowledge_unsafe')
        logger.warning(f'Instance sync [{self.instance}] round {info["seq"]} acknowledged by the operator: '
                       f'{reason or "no reason given"}')
        return AckResult(True, 'acknowledged', info['round_id'], info['seq'])

    def _run(self) -> SyncResult:
        self._open_ledger()
        result, changed = self._ledger.transact(
            lambda doc, now: sm.op_enter(doc, now, self._actor, members=self.members, protocol=self.protocol,
                                          rendezvous_timeout=self.rendezvous_timeout, new_round_id=self._new_id()),
            create_if_missing=True)
        info = result.value
        outcome = info['outcome']
        self.round_id = info['round_id']
        if changed:
            self._journal.append(self._ledger.name, self.round_id, f'enter:{outcome}')
        logger.info(f'Instance sync [{self.instance}] ledger={self._ledger.name} round={info["seq"]} outcome={outcome}')
        if outcome == sm.OUT_COMPLETED:
            return SyncResult(S_ALREADY, sm.G_COMPLETED, NEXT_DONE, self.round_id, info['seq'])
        if outcome == sm.OUT_MANUAL:
            return SyncResult(S_FAILED, REASON_UNSAFE_PRIOR, NEXT_DEFER, self.round_id, info['seq'],
                              'a previous round may already have sent the request; check the game, '
                              'then call acknowledge_unsafe() before the next run')
        if outcome == sm.OUT_CAP:
            return SyncResult(S_FAILED, REASON_ROUND_CAP, NEXT_DEFER, self.round_id, info['seq'])
        if outcome == sm.OUT_REJECTED:
            return SyncResult(S_FAILED, sm.R_HANDSHAKE, NEXT_DEFER, self.round_id, info['seq'],
                              'pair declaration or protocol params differ between the two instances')
        self._resumed = outcome == sm.OUT_RESUMED
        return self._drive()

    # ------------------------------------------------------------------------------------------------------------------
    # 账本访问
    # ------------------------------------------------------------------------------------------------------------------
    def view(self) -> sm.RoundView:
        """最新快照（顺带推进会合 / 预算超时）。"""
        def fn(doc, now):
            sm.op_poll(doc, now)
            return sm.build_view(doc, self.instance)

        view, _ = self._ledger.transact(fn)
        if view.round_id != self.round_id:
            raise SyncCancelled('round_replaced')
        self.rendezvous_deadline_at = view.rendezvous_deadline_at
        self.deadline_at = view.deadline_at
        return view

    def check_alive(self) -> sm.RoundView:
        view = self.view()
        if view.global_state == sm.G_FAILED:
            raise SyncCancelled(view.global_reason or sm.G_FAILED)
        return view

    def _op(self, name: str, op, **kwargs) -> sm.OpResult:
        result, changed = self._ledger.transact(
            lambda doc, now: op(doc, now, self._actor, round_id=self.round_id, **kwargs))
        if changed:
            self._journal.append(self._ledger.name, self.round_id, name)
        if not result.ok and result.reason in ('session_superseded', 'round_mismatch', 'no_round'):
            raise SyncCancelled(result.reason)
        return result

    def _expect(self, name: str, result: sm.OpResult) -> bool:
        """被拒绝的操作只有一种正常原因：整轮刚刚进入终态（由外层循环处理）。其余都是调用缺陷。"""
        if result.ok:
            return True
        if result.reason == 'terminal':
            return False
        raise InvariantViolation([f'{name} was rejected: {result.reason}'])

    # ------------------------------------------------------------------------------------------------------------------
    # 等待（唯一的等待 owner）
    # ------------------------------------------------------------------------------------------------------------------
    def _after_wait(self, started: float) -> None:
        elapsed = self.clock() - started
        if elapsed >= LONG_WAIT_SECONDS:
            self.adapter.after_wait(elapsed)

    def _poll_until(self, predicate: Callable[[sm.RoundView], bool], timeout: Optional[float] = None):
        started = self.clock()
        try:
            for _ in range(_MAX_POLLS):
                view = self.check_alive()
                satisfied = predicate(view)
                if view.terminal or satisfied:
                    return view, satisfied
                if timeout is not None and self.clock() - started >= timeout:
                    return view, False
                self.sleep(self.poll_interval)
            raise SyncError('poll did not converge')
        finally:
            # 取消 / 超时 / 正常结束都要通知：失败后适配器紧接着还要回主界面，同样会带着旧的卡死计时去截图
            self._after_wait(started)

    def _sleep_until(self, target: float) -> None:
        started = self.clock()
        try:
            for _ in range(_MAX_POLLS):
                view = self.check_alive()
                remaining = target - self.clock()
                if view.terminal or remaining <= 0:
                    return
                self.sleep(min(self.poll_interval, remaining))
            raise SyncError('sleep did not converge')
        finally:
            self._after_wait(started)

    def wait_until(self, predicate, timeout: Optional[float] = None) -> bool:
        _, satisfied = self._poll_until(predicate, timeout)
        return satisfied

    # ------------------------------------------------------------------------------------------------------------------
    # 主循环：按账本里的本地状态推进，重启后从当前状态继续
    # ------------------------------------------------------------------------------------------------------------------
    def _drive(self) -> SyncResult:
        if self._resumed:
            self._recover()
        for _ in range(_MAX_STEPS):
            view = self.view()
            if view.terminal:
                return self._result_for(view)
            state = view.me_state
            if state == sm.P_JOINED:
                self._phase_prepare()
            elif state == sm.P_READY:
                self._phase_wait_start()
            elif state == sm.P_EXECUTING:
                self._phase_execute()
            elif state == sm.P_VERIFIED:
                self._poll_until(lambda v: False)
            else:
                raise InvariantViolation([f'unexpected participant state: {state!r}'])
        raise SyncError('drive loop did not converge')

    def _phase_prepare(self) -> None:
        result = self.adapter.prepare(self._ctx)
        if not result.ok:
            logger.warning(f'Instance sync [{self.instance}] prepare failed: {result.reason}')
            self._fail(sm.R_PREPARE_FAILED, result.reason)
            return
        self._expect('ready', self._op('ready', sm.op_ready))

    def _phase_wait_start(self) -> None:
        view, _ = self._poll_until(lambda v: v.deadline_at is not None)
        if view.terminal:
            return
        self._expect('start', self._op('start', sm.op_start))

    def _phase_execute(self) -> None:
        kind = self.adapter.business_id
        while True:
            view = self.view()
            if view.terminal:
                return
            if any(a.status == sm.A_DONE for a in view.my_attempts):
                break
            if view.my_attempts and view.my_attempts[-1].status == sm.A_PREPARED:
                raise InvariantViolation(['a prepared attempt is still pending in the execute phase'])
            if not self.adapter.await_turn(self._ctx):
                logger.warning(f'Instance sync [{self.instance}] await_turn gave up')
                self._fail(sm.R_PREPARE_FAILED, 'await_turn')
                return
            attempt = self._begin_attempt(kind)
            if attempt is None:
                return
            self._run_attempt(attempt)
        self.check_alive()
        if not self.adapter.verify(self._ctx):
            self._fail(sm.R_VERIFY_FAILED)
            return
        self._expect('verify', self._op('verify', sm.op_verify))

    def _begin_attempt(self, kind: str) -> Optional[sm.AttemptView]:
        """等到允许重试（30 秒间隔）→ 写 prepared 意图。预算不够就立即失败，不白等。"""
        while True:
            attempt_id = self._new_id()
            result = self._op('prepare_attempt', sm.op_begin_attempt, kind=kind, attempt_id=attempt_id)
            if result.ok:
                view = self.view()
                return next(a for a in view.my_attempts if a.attempt_id == attempt_id)
            if result.reason == 'too_early':
                self._sleep_until(result.value['earliest_at'])
                continue
            if result.reason == 'no_budget':
                self._fail(sm.R_NO_BUDGET)
                return None
            self._expect('begin_attempt', result)
            return None

    def _run_attempt(self, attempt: sm.AttemptView) -> None:
        adapter, ctx = self.adapter, self._ctx
        try:
            self.check_alive()
        except SyncCancelled:
            # prepared 写下之后、点击之前被取消：确定没点过
            self._resolve_quietly(attempt.attempt_id, sm.A_ABORTED, 'cancelled before dispatch')
            raise
        try:
            adapter.dispatch(ctx, attempt)
            evidence = adapter.judge(ctx, attempt)
        except BaseException as exc:
            # 点击之后（或点击中）出任何异常都不能证明没发出去：记 unknown，绝不重发
            self._resolve_quietly(attempt.attempt_id, sm.A_UNKNOWN, f'{type(exc).__name__}: {exc}')
            raise
        if isinstance(evidence, Evidence) and evidence.kind == EV_DONE:
            status = sm.A_DONE
        elif isinstance(evidence, Evidence) and evidence.kind == EV_NOT_DONE:
            status = sm.A_NOT_DONE
        else:
            status = sm.A_UNKNOWN
        detail = evidence.detail if isinstance(evidence, Evidence) else f'bad evidence: {evidence!r}'
        self._op('resolve_attempt', sm.op_resolve_attempt, attempt_id=attempt.attempt_id, status=status,
                 evidence=detail)

    def _resolve_quietly(self, attempt_id: str, status: str, detail: str) -> None:
        try:
            self._op('resolve_attempt', sm.op_resolve_attempt, attempt_id=attempt_id, status=status, evidence=detail)
        except Exception as exc:
            logger.warning(f'Instance sync could not record attempt result ({status}): {exc}')

    def _fail(self, reason: str, detail: str = '') -> None:
        self._op('fail', sm.op_fail, reason=reason, detail=detail)

    def _best_effort_fail(self, reason: str) -> None:
        if self._ledger is None or self.round_id is None:
            return
        try:
            self._fail(reason)
        except Exception as exc:
            logger.warning(f'Instance sync could not record failure ({reason}): {exc}')

    # ------------------------------------------------------------------------------------------------------------------
    # 崩溃恢复
    # ------------------------------------------------------------------------------------------------------------------
    def _recover(self) -> None:
        """重启后账本里还留着本实例的 prepared：先看游戏现状，拿到明确证据才结算；整轮已终态则不碰游戏。"""
        view = self.view()
        if view.terminal:
            return
        for attempt in [a for a in view.my_attempts if a.status == sm.A_PREPARED]:
            self.check_alive()
            try:
                evidence = self.adapter.inspect_attempt(self._ctx, attempt)
            except BaseException as exc:
                self._resolve_quietly(attempt.attempt_id, sm.A_UNKNOWN, f'inspect failed: {type(exc).__name__}: {exc}')
                raise
            if isinstance(evidence, Evidence) and evidence.kind == EV_DONE:
                status = sm.A_DONE
            elif isinstance(evidence, Evidence) and evidence.kind == EV_NOT_DONE:
                status = sm.A_NOT_DONE
            else:
                status = sm.A_UNKNOWN
            logger.info(f'Instance sync [{self.instance}] recovered attempt {attempt.attempt_id[:8]} -> {status}')
            self._op('resolve_attempt', sm.op_resolve_attempt, attempt_id=attempt.attempt_id, status=status,
                     evidence='recovered: ' + (evidence.detail if isinstance(evidence, Evidence) else ''))

    # ------------------------------------------------------------------------------------------------------------------
    # 结果
    # ------------------------------------------------------------------------------------------------------------------
    def _result_for(self, view: sm.RoundView) -> SyncResult:
        if view.global_state == sm.G_COMPLETED:
            logger.info(f'Instance sync [{self.instance}] round {view.seq} completed')
            return SyncResult(S_COMPLETED, sm.G_COMPLETED, NEXT_DONE, view.round_id, view.seq)
        reason = view.global_reason or sm.G_FAILED
        retry = (reason not in _DEFER_REASONS and view.classification == sm.SAFE
                 and view.rounds_count < view.params['max_rounds'])
        logger.warning(f'Instance sync [{self.instance}] round {view.seq} failed: {reason} '
                       f'({view.classification}) -> {NEXT_RETRY if retry else NEXT_DEFER}')
        return SyncResult(S_FAILED, reason, NEXT_RETRY if retry else NEXT_DEFER, view.round_id, view.seq)

    def _cancelled_result(self, exc: SyncCancelled) -> SyncResult:
        try:
            view = self.view()
            if view.terminal:
                return self._result_for(view)
        except SyncError:
            pass
        return SyncResult(S_FAILED, exc.reason, NEXT_DEFER, self.round_id)

    def _ledger_result(self, exc: LedgerError) -> SyncResult:
        if isinstance(exc, LedgerCorruptError):
            reason = REASON_LEDGER_CORRUPT
        elif isinstance(exc, LedgerLostError):
            reason = REASON_LEDGER_LOST
        elif isinstance(exc, LedgerWriteError):
            reason = REASON_LEDGER_WRITE
        else:  # 含 LedgerLockTimeout
            reason = REASON_LEDGER_UNAVAILABLE
        logger.error(f'Instance sync [{self.instance}] ledger problem: {reason}: {exc}')
        return SyncResult(S_FAILED, reason, NEXT_DEFER, self.round_id, detail=str(exc))
