"""`module/instance_sync/coordinator.py` 的单进程行为测试。

没有真实时钟、没有设备：
- `VClock`：虚拟时钟；`sleep` 推进时间，并按时间顺序触发预先安排好的「对端动作」。
  这样「A 在等待时，B 在第 N 秒做了某事」可以确定性地复现，而不需要线程。
- `Side`：直接用状态机 op 扮演对端（或崩溃前的旧会话）。
- `FakeAdapter`：记录被调用的方法，按脚本给证据。

锁住：完整链路；会合超时是安全失败；重试 30 秒间隔且不重置预算；预算不够时立即失败不白等；
unknown / 异常之后绝不重发；点击前被取消记 aborted；对端失败时一个轮询周期内退出；
崩溃恢复（done / not_done / unknown / 已过期）；当天已完成直接短路；每天最多 3 轮；
账本损坏 / 丢失 / 锁超时 / 写失败 → 失败结果且不再自动重来；设备异常先写 failed 再原样上抛。
"""

import heapq
import itertools
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filelock import FileLock

from module.instance_sync import state_machine as sm
from module.instance_sync.adapter import Evidence, PrepareResult, SyncAdapter
from module.instance_sync.coordinator import (
    NEXT_DEFER, NEXT_DONE, NEXT_RETRY, S_ALREADY, S_COMPLETED, S_FAILED, SyncCoordinator,
)
from module.instance_sync.ledger import Ledger

DAY = '2026-10-21'
PARAMS = {'retry_wait': 30, 'budget': 180, 'min_attempt_cost': 10, 'max_rounds': 4}
MEMBERS = [('oas1', 'A01'), ('oas2', 'A02')]
T0 = 1_000_000.0


class VClock:
    def __init__(self):
        self.t = T0
        self.sleeps = []
        self._events = []
        self._n = itertools.count()

    def __call__(self):
        return self.t

    def at(self, offset, fn):
        heapq.heappush(self._events, (T0 + offset, next(self._n), fn))

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        target = self.t + seconds
        # 硬上限哨兵：任何合法场景都远小于一天；超过说明某个等待循环没有被账本里的截止时间终止
        if target - T0 > 86400:
            raise AssertionError('virtual clock ran past one day: a wait loop did not terminate')
        while self._events and self._events[0][0] <= target:
            when, _, fn = heapq.heappop(self._events)
            self.t = max(self.t, when)
            fn()
        self.t = target


class Side:
    """用状态机 op 扮演对端 / 崩溃前的旧会话。"""

    def __init__(self, root, clock, instance, session, *, day=DAY, params=PARAMS, members=MEMBERS):
        self.members = sm.canonical_members(members)
        self.protocol = sm.make_protocol(params)
        self.ledger = Ledger(root, sm.make_key(day, 'xinlan', self.members), None, clock=clock)
        self.actor = sm.Actor(instance, session)
        self.round_id = None
        self.attempt_id = None
        self._n = itertools.count(1)

    def enter(self, rendezvous_timeout=600):
        result, _ = self.ledger.transact(
            lambda doc, now: sm.op_enter(doc, now, self.actor, members=self.members, protocol=self.protocol,
                                          rendezvous_timeout=rendezvous_timeout,
                                          new_round_id=f'{self.actor.instance}-round'),
            create_if_missing=True)
        self.round_id = result.value['round_id']
        return result

    def op(self, fn, expect_ok=True, **kwargs):
        result, _ = self.ledger.transact(lambda doc, now: fn(doc, now, self.actor, round_id=self.round_id, **kwargs))
        if expect_ok:
            assert result.ok, (fn.__name__, result)
        return result

    def ready(self):
        return self.op(sm.op_ready)

    def start(self):
        return self.op(sm.op_start)

    def begin(self):
        self.attempt_id = f'{self.actor.instance}-att{next(self._n)}'
        return self.op(sm.op_begin_attempt, kind='xinlan', attempt_id=self.attempt_id)

    def resolve(self, status):
        return self.op(sm.op_resolve_attempt, attempt_id=self.attempt_id, status=status)

    def verify(self):
        return self.op(sm.op_verify)

    def fail(self, reason='boom'):
        return self.op(sm.op_fail, reason=reason)

    def finish(self):
        """start → 发一次并确认成功 → verify。"""
        self.start()
        self.begin()
        self.resolve(sm.A_DONE)
        return self.verify()


class FakeAdapter(SyncAdapter):
    business_id = 'xinlan'

    def __init__(self, *, day=DAY, params=PARAMS, judge=(), verify_ok=True, prepare=PrepareResult(True),
                 inspect=Evidence.unknown('no clue'), dispatch_cost=1.0, dispatch_error=None, verify_error=None):
        self.day = day
        self.params = dict(params)
        self.judge_script = list(judge)
        self.verify_ok = verify_ok
        self.prepare_result = prepare
        self.inspect_result = inspect
        self.dispatch_cost = dispatch_cost
        self.dispatch_error = dispatch_error
        self.verify_error = verify_error
        self.calls = []
        self.dispatch_times = []
        self.after_waits = []
        self.prepare_view = None

    def protocol_params(self):
        return self.params

    def business_day(self, now):
        return self.day

    def prepare(self, ctx):
        self.calls.append('prepare')
        self.prepare_view = ctx.view()
        return self.prepare_result

    def dispatch(self, ctx, attempt):
        self.calls.append('dispatch')
        self.dispatch_times.append(ctx.now())
        ctx.sleep(self.dispatch_cost)
        if self.dispatch_error:
            raise self.dispatch_error

    def judge(self, ctx, attempt):
        self.calls.append('judge')
        return self.judge_script.pop(0) if self.judge_script else Evidence.done()

    def verify(self, ctx):
        self.calls.append('verify')
        if self.verify_error:
            raise self.verify_error
        return self.verify_ok

    def inspect_attempt(self, ctx, attempt):
        self.calls.append('inspect')
        return self.inspect_result

    def after_wait(self, seconds):
        self.after_waits.append(seconds)


class TurnAdapter(FakeAdapter):
    """`await_turn` 按脚本走（True / False / 异常 / 可调用对象，脚本用完后放行）；`wait_for_peer` 模拟「等对端先发」。

    单独一个子类，不让 `await_turn` 出现在 `FakeAdapter.calls` 里，免得改动既有用例对调用顺序的断言。
    """

    def __init__(self, *, turns=(), wait_for_peer=False, **kwargs):
        super().__init__(**kwargs)
        self.turn_script = list(turns)
        self.wait_for_peer = wait_for_peer
        self.turn_calls = 0

    def await_turn(self, ctx):
        self.calls.append('await_turn')
        self.turn_calls += 1
        if self.wait_for_peer:
            return ctx.wait_until(lambda view: bool(view.peer_attempts), timeout=ctx.remaining())
        step = self.turn_script.pop(0) if self.turn_script else True
        if isinstance(step, BaseException):
            raise step
        return step(ctx) if callable(step) else step


class CoordinatorTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.clock = VClock()
        self._ids = itertools.count(1)

    def coordinator(self, adapter, instance='oas1', session='sess-new', **kwargs):
        kwargs.setdefault('poll_interval', 1.0)
        kwargs.setdefault('lock_timeout', 5.0)
        return SyncCoordinator(adapter, instance=instance, members=MEMBERS, rendezvous_timeout=600, root=self.root,
                               clock=self.clock, sleep=self.clock.sleep, session_id=session,
                               new_id=lambda: f'id{next(self._ids)}', **kwargs)

    def side(self, instance='oas2', session='sess-peer', **kwargs):
        return Side(self.root, self.clock, instance, session, **kwargs)

    def ledger_path(self, day=DAY) -> Path:
        key = sm.make_key(day, 'xinlan', sm.canonical_members(MEMBERS))
        return self.root / sm.ledger_filename(key)

    def doc(self, day=DAY) -> dict:
        return json.loads(self.ledger_path(day).read_text(encoding='utf-8'))

    def last_round(self, day=DAY) -> dict:
        return self.doc(day)['rounds'][-1]

    def schedule_peer_script(self, peer, *, enter=10, ready=12, start=14, finish=20):
        self.clock.at(enter, peer.enter)
        self.clock.at(ready, peer.ready)
        self.clock.at(start, peer.start)
        self.clock.at(finish, lambda: (peer.begin(), peer.resolve(sm.A_DONE), peer.verify()))

    def run_completed_round(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.schedule_peer_script(peer)
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        return result


class FullFlowTest(CoordinatorTestCase):
    def test_both_instances_complete_one_round(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.schedule_peer_script(peer)
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action), (S_COMPLETED, 'completed', NEXT_DONE))
        self.assertTrue(result.ok)
        self.assertEqual(adapter.calls, ['prepare', 'dispatch', 'judge', 'verify'])
        rnd = self.last_round()
        self.assertEqual(rnd['global']['state'], sm.G_COMPLETED)
        self.assertEqual({p['state'] for p in rnd['participants'].values()}, {sm.P_VERIFIED})
        self.assertEqual(rnd['deadline_at'] - rnd['ready_at'], 180)
        journal = (self.root / 'oas1.journal.jsonl').read_text(encoding='utf-8')
        self.assertIn('enter:created', journal)

    def test_second_instance_joins_the_round_the_first_created(self):
        adapter = FakeAdapter()
        creator = self.side()
        creator.enter()
        creator.ready()
        self.clock.at(2, creator.start)
        self.clock.at(5, lambda: (creator.begin(), creator.resolve(sm.A_DONE), creator.verify()))
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(len(self.doc()['rounds']), 1)
        self.assertEqual(self.last_round()['created_by'], 'oas2')

    def test_adapter_only_gets_read_only_snapshots(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.schedule_peer_script(peer)
        self.coordinator(adapter).run()
        view = adapter.prepare_view
        with self.assertRaises(Exception):
            view.global_state = 'completed'
        with self.assertRaises(TypeError):
            view.params['budget'] = 1

    def test_completed_round_short_circuits_the_whole_day(self):
        self.run_completed_round()
        again = FakeAdapter()
        result = self.coordinator(again, session='sess-2').run()
        self.assertEqual((result.status, result.next_action), (S_ALREADY, NEXT_DONE))
        self.assertTrue(result.ok)
        self.assertEqual(again.calls, [])  # 不进游戏、不重发
        self.assertEqual(len(self.doc()['rounds']), 1)

    def test_a_new_business_day_uses_a_new_ledger(self):
        self.run_completed_round()
        tomorrow = FakeAdapter(day='2026-10-22', prepare=PrepareResult(False, 'x'))
        result = self.coordinator(tomorrow, session='sess-2').run()
        self.assertEqual(result.seq, 1)
        self.assertTrue(self.ledger_path('2026-10-22').exists())
        self.assertEqual(len(self.doc(DAY)['rounds']), 1)

    def test_long_pure_waits_notify_the_adapter(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.schedule_peer_script(peer, enter=40, ready=50, start=52, finish=60)
        self.coordinator(adapter).run()
        self.assertTrue(adapter.after_waits)
        self.assertTrue(all(w >= 30 for w in adapter.after_waits))

    def test_short_waits_do_not_notify_the_adapter(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.schedule_peer_script(peer)
        self.coordinator(adapter).run()
        self.assertEqual(adapter.after_waits, [])


class SafeFailureTest(CoordinatorTestCase):
    def test_rendezvous_timeout_is_a_safe_failure_and_retries_later(self):
        adapter = FakeAdapter()
        result = self.coordinator(adapter, poll_interval=5.0).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_RENDEZVOUS_TIMEOUT, NEXT_RETRY))
        self.assertEqual(adapter.calls, ['prepare'])
        self.assertGreaterEqual(self.clock.t - T0, 600)
        self.assertLess(self.clock.t - T0, 606)
        self.assertTrue(adapter.after_waits)

    def test_prepare_failure_is_safe(self):
        adapter = FakeAdapter(prepare=PrepareResult(False, 'friend not found'))
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action), (S_FAILED, sm.R_PREPARE_FAILED, NEXT_RETRY))
        self.assertEqual(adapter.calls, ['prepare'])
        self.assertEqual(self.last_round()['global']['detail'], 'friend not found')

    def test_peer_failure_cancels_the_wait_within_one_poll(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.clock.at(10, peer.enter)
        self.clock.at(30, peer.fail)
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action), (S_FAILED, 'boom', NEXT_RETRY))
        self.assertLessEqual(self.clock.t - T0, 31)
        self.assertEqual(adapter.calls, ['prepare'])

    def test_failure_by_the_peer_before_our_dispatch_aborts_the_prepared_attempt(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        coord = self.coordinator(adapter)
        original = coord._op

        def op(name, fn, **kwargs):
            result = original(name, fn, **kwargs)
            if name == 'prepare_attempt':
                peer.fail('boom')  # 恰好落在「写下意图」和「点击」之间
            return result

        coord._op = op
        result = coord.run()
        self.assertEqual((result.status, result.reason), (S_FAILED, 'boom'))
        self.assertNotIn('dispatch', adapter.calls)
        attempts = self.last_round()['attempts']
        self.assertEqual([a['status'] for a in attempts], [sm.A_ABORTED])
        self.assertEqual(result.next_action, NEXT_RETRY)  # 确定没点过 → 安全，可以重来


class RetryAndBudgetTest(CoordinatorTestCase):
    def test_retry_waits_thirty_seconds_and_keeps_the_original_deadline(self):
        adapter = FakeAdapter(judge=[Evidence.not_done('toast: busy'), Evidence.done()])
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        self.clock.at(100, lambda: (peer.finish(),))
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.calls.count('dispatch'), 2)
        first, second = adapter.dispatch_times
        self.assertGreaterEqual(second - first, 30 + adapter.dispatch_cost)
        rnd = self.last_round()
        self.assertEqual(rnd['deadline_at'] - rnd['ready_at'], 180)
        mine = [a for a in rnd['attempts'] if a['instance'] == 'oas1']
        self.assertEqual([a['status'] for a in mine], [sm.A_NOT_DONE, sm.A_DONE])
        self.assertGreaterEqual(mine[1]['prepared_at'] - mine[0]['resolved_at'], 30)

    def test_waiting_for_the_retry_uses_polls_not_one_long_sleep(self):
        adapter = FakeAdapter(judge=[Evidence.not_done(), Evidence.done()])
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        self.clock.at(100, lambda: (peer.finish(),))
        self.coordinator(adapter).run()
        self.assertLessEqual(max(self.clock.sleeps), 1.0)

    def test_retry_is_refused_at_once_when_the_budget_cannot_cover_wait_plus_attempt(self):
        params = {**PARAMS, 'budget': 60, 'min_attempt_cost': 15}
        adapter = FakeAdapter(params=params, judge=[Evidence.not_done()], dispatch_cost=20)
        peer = self.side(params=params)
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_NO_BUDGET, NEXT_RETRY))
        self.assertEqual(adapter.calls.count('dispatch'), 1)
        self.assertLess(self.clock.t - T0, 30)  # 没有白等 30 秒

    def test_budget_timeout_while_waiting_for_the_peer_to_verify(self):
        adapter = FakeAdapter()
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        self.clock.at(2, peer.start)  # 对端从此不再动作
        result = self.coordinator(adapter, poll_interval=5.0).run()
        self.assertEqual((result.status, result.reason), (S_FAILED, sm.R_BUDGET_TIMEOUT))
        self.assertEqual(result.next_action, NEXT_DEFER)  # 我方已确认发出，对端状态不明 → 不再自动重来
        self.assertLess(self.clock.t - T0, 190)


class UnknownResultTest(CoordinatorTestCase):
    def _join_ready_peer(self):
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        return peer

    def test_unknown_evidence_fails_the_round_and_is_never_resent(self):
        adapter = FakeAdapter(judge=[Evidence.unknown('no toast seen')])
        self._join_ready_peer()
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_ATTEMPT_UNKNOWN, NEXT_DEFER))
        self.assertEqual(adapter.calls.count('dispatch'), 1)
        # 同一天再次启动：被「上一轮可能已发出」拦住，连 prepare 都不进
        again = FakeAdapter()
        later = self.coordinator(again, session='sess-2').run()
        self.assertEqual((later.reason, later.next_action), ('unsafe_prior_round', NEXT_DEFER))
        self.assertEqual(again.calls, [])
        self.assertEqual(len(self.doc()['rounds']), 1)

    def test_dispatch_exception_is_recorded_as_unknown_and_reraised(self):
        error = RuntimeError('device died')
        adapter = FakeAdapter(dispatch_error=error)
        self._join_ready_peer()
        with self.assertRaises(RuntimeError) as ctx:
            self.coordinator(adapter).run()
        self.assertIs(ctx.exception, error)
        rnd = self.last_round()
        self.assertEqual((rnd['global']['state'], rnd['global']['reason']), (sm.G_FAILED, sm.R_ATTEMPT_UNKNOWN))
        self.assertEqual([a['status'] for a in rnd['attempts']], [sm.A_UNKNOWN])
        self.assertEqual([e['op'] for e in rnd['late_events']], ['fail'])  # 之后的 exception 报告只追加，不改终态

    def test_verify_exception_fails_the_round_first_then_propagates_the_same_object(self):
        error = ValueError('game stuck')
        adapter = FakeAdapter(verify_error=error)
        self._join_ready_peer()
        with self.assertRaises(ValueError) as ctx:
            self.coordinator(adapter).run()
        self.assertIs(ctx.exception, error)
        rnd = self.last_round()
        self.assertEqual(rnd['global']['state'], sm.G_FAILED)
        self.assertEqual(rnd['global']['reason'], 'exception:ValueError')

    def test_verification_failure_fails_the_round_and_blocks_a_resend(self):
        adapter = FakeAdapter(verify_ok=False)
        self._join_ready_peer()
        result = self.coordinator(adapter).run()
        self.assertEqual((result.reason, result.next_action), (sm.R_VERIFY_FAILED, NEXT_DEFER))
        self.assertEqual(adapter.calls.count('dispatch'), 1)

    def test_garbage_evidence_is_treated_as_unknown(self):
        adapter = FakeAdapter(judge=['yes'])
        self._join_ready_peer()
        result = self.coordinator(adapter).run()
        self.assertEqual(result.reason, sm.R_ATTEMPT_UNKNOWN)


class RecoveryTest(CoordinatorTestCase):
    def _crashed_with_prepared_attempt(self):
        """旧会话把意图写进账本后崩溃：A 已 executing，账本里留着 A 的 prepared。"""
        self.old = self.side('oas1', 'sess-old')
        self.peer = self.side()
        self.old.enter()
        self.peer.enter()
        self.old.ready()
        self.clock.t = T0 + 2
        self.peer.ready()
        self.old.start()
        self.peer.start()
        self.clock.t = T0 + 4
        self.old.begin()
        self.clock.t = T0 + 10

    def _peer_finishes_at(self, offset):
        self.clock.at(offset, lambda: (self.peer.begin(), self.peer.resolve(sm.A_DONE), self.peer.verify()))

    def test_confirmed_sent_by_inspection_is_not_sent_again(self):
        self._crashed_with_prepared_attempt()
        adapter = FakeAdapter(inspect=Evidence.done('friend page shows the gift'))
        self._peer_finishes_at(20)
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.calls, ['inspect', 'verify'])
        mine = [a for a in self.last_round()['attempts'] if a['instance'] == 'oas1']
        self.assertEqual([a['status'] for a in mine], [sm.A_DONE])
        self.assertEqual(self.last_round()['participants']['oas1']['session_id'], 'sess-new')

    def test_confirmed_not_sent_by_inspection_retries_after_the_wait(self):
        self._crashed_with_prepared_attempt()
        adapter = FakeAdapter(inspect=Evidence.not_done('button still available'))
        self._peer_finishes_at(60)
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.calls, ['inspect', 'dispatch', 'judge', 'verify'])
        self.assertGreaterEqual(adapter.dispatch_times[0] - (T0 + 10), 30)

    def test_unclear_inspection_fails_without_touching_the_game(self):
        self._crashed_with_prepared_attempt()
        adapter = FakeAdapter(inspect=Evidence.unknown())
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_ATTEMPT_UNKNOWN, NEXT_DEFER))
        self.assertEqual(adapter.calls, ['inspect'])

    def test_recovery_after_the_deadline_does_not_touch_the_game_at_all(self):
        self._crashed_with_prepared_attempt()
        self.clock.t = T0 + 400  # deadline = ready_at(2) + 180
        adapter = FakeAdapter(inspect=Evidence.done())
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, 'unsafe_prior_round', NEXT_DEFER))
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.last_round()['global']['reason'], sm.R_BUDGET_TIMEOUT)

    def test_old_session_is_cancelled_when_a_newer_one_takes_over(self):
        old_adapter = FakeAdapter()
        peer = self.side()
        takeover = self.side('oas1', 'sess-takeover')
        self.clock.at(5, peer.enter)
        self.clock.at(6, takeover.enter)  # 同一实例被新进程接管 → RESUMED
        self.clock.at(10, peer.ready)
        result = self.coordinator(old_adapter, session='sess-old').run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, 'session_superseded', NEXT_DEFER))
        self.assertNotIn('dispatch', old_adapter.calls)


class RoundCapAndHandshakeTest(CoordinatorTestCase):
    def test_first_round_plus_three_retries_per_day(self):
        results = []
        for index in range(5):  # max_rounds=4：第一轮 + 最多 3 次自动重来，第 5 次启动被上限拦住
            self.clock.t = T0 + 1800 * (index + 1)
            adapter = FakeAdapter(prepare=PrepareResult(False, 'no entry'))
            results.append((self.coordinator(adapter, session=f's{index}').run(), adapter))
        self.assertEqual([r.next_action for r, _ in results],
                         [NEXT_RETRY, NEXT_RETRY, NEXT_RETRY, NEXT_DEFER, NEXT_DEFER])
        self.assertEqual([r.reason for r, _ in results][:4], [sm.R_PREPARE_FAILED] * 4)
        self.assertEqual(results[4][0].reason, 'round_cap')
        self.assertEqual(results[4][1].calls, [])
        self.assertEqual([r['seq'] for r in self.doc()['rounds']], [1, 2, 3, 4])

    def test_mismatched_protocol_params_are_rejected_without_entering_the_game(self):
        creator = self.side()
        creator.enter()
        adapter = FakeAdapter(params={**PARAMS, 'budget': 120})
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action), (S_FAILED, sm.R_HANDSHAKE, NEXT_DEFER))
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.last_round()['global']['reason'], sm.R_HANDSHAKE)
        self.assertEqual(list(self.last_round()['participants']), ['oas2'])

    def test_creator_sees_the_handshake_failure_at_once(self):
        adapter = FakeAdapter()
        intruder = self.side(params={**PARAMS, 'retry_wait': 5})
        self.clock.at(10, intruder.enter)
        result = self.coordinator(adapter).run()
        self.assertEqual((result.reason, result.next_action), (sm.R_HANDSHAKE, NEXT_DEFER))
        self.assertLessEqual(self.clock.t - T0, 11)


class AcknowledgeUnsafeFlowTest(CoordinatorTestCase):
    """人工确认并重置：核对过游戏之后，当天才能在 unsafe 之后再开新轮（重启 / 崩溃都不会自动放行）。"""

    def _unsafe_run(self, session='sess-1'):
        """对端已 ready，我方 judge 给 unknown → 整轮失败，归 unsafe。"""
        adapter = FakeAdapter(judge=[Evidence.unknown('no toast seen')])
        peer = self.side(session=f'peer-{session}')
        base = self.clock.t - T0
        self.clock.at(base + 0.5, peer.enter)
        self.clock.at(base + 1, peer.ready)
        result = self.coordinator(adapter, session=session).run()
        self.assertEqual(result.reason, sm.R_ATTEMPT_UNKNOWN)
        return result

    def test_acknowledge_then_run_opens_a_new_round_and_completes(self):
        self._unsafe_run()
        blocked_adapter = FakeAdapter()
        blocked = self.coordinator(blocked_adapter, session='sess-2').run()
        self.assertEqual((blocked.reason, blocked.next_action), ('unsafe_prior_round', NEXT_DEFER))
        self.assertIn('acknowledge_unsafe', blocked.detail)  # 拦截时就告诉用户怎么解除
        self.assertEqual(blocked_adapter.calls, [])

        ack = self.coordinator(FakeAdapter(), session='sess-3').acknowledge_unsafe('checked by hand')
        self.assertEqual((ack.acknowledged, ack.reason, ack.seq), (True, 'acknowledged', 1))

        adapter = FakeAdapter()
        peer = self.side(session='peer-round2')
        base = self.clock.t - T0
        self.schedule_peer_script(peer, enter=base + 10, ready=base + 12, start=base + 14, finish=base + 20)
        result = self.coordinator(adapter, session='sess-4').run()
        self.assertEqual((result.status, result.seq), (S_COMPLETED, 2))
        rounds = self.doc()['rounds']
        self.assertEqual(len(rounds), 2)
        first = rounds[0]
        self.assertEqual((first['global']['state'], first['global']['reason']), (sm.G_FAILED, sm.R_ATTEMPT_UNKNOWN))
        self.assertEqual([(e['op'], e['instance'], e['detail']) for e in first['late_events']],
                         [(sm.LATE_ACK, 'oas1', 'checked by hand')])
        self.assertEqual([a['status'] for a in first['attempts']], [sm.A_UNKNOWN])  # 旧证据原样保留
        self.assertIn('acknowledge_unsafe', (self.root / 'oas1.journal.jsonl').read_text(encoding='utf-8'))

    def test_either_instance_can_acknowledge_and_it_is_recorded_who(self):
        self._unsafe_run()
        ack = self.coordinator(FakeAdapter(), instance='oas2', session='sess-b').acknowledge_unsafe('peer checked')
        self.assertTrue(ack.acknowledged)
        self.assertEqual(self.last_round()['late_events'][0]['instance'], 'oas2')

    def test_acknowledging_twice_changes_nothing_the_second_time(self):
        self._unsafe_run()
        first = self.coordinator(FakeAdapter(), session='a').acknowledge_unsafe('x')
        second = self.coordinator(FakeAdapter(), instance='oas2', session='b').acknowledge_unsafe('y')
        self.assertTrue(first.acknowledged)
        self.assertEqual((second.acknowledged, second.reason), (False, 'not_unsafe'))
        self.assertEqual(len(self.last_round()['late_events']), 1)

    def test_nothing_to_acknowledge_without_a_ledger(self):
        ack = self.coordinator(FakeAdapter()).acknowledge_unsafe()
        self.assertEqual((ack.acknowledged, ack.reason), (False, 'no_round'))
        self.assertFalse(self.ledger_path().exists())

    def test_a_round_still_in_progress_cannot_be_acknowledged(self):
        self.side().enter()
        before = self.ledger_path().read_bytes()
        ack = self.coordinator(FakeAdapter()).acknowledge_unsafe()
        self.assertEqual((ack.acknowledged, ack.reason, ack.seq), (False, 'round_open', 1))
        self.assertEqual(self.ledger_path().read_bytes(), before)

    def test_corrupt_ledger_is_reported_not_raised_and_left_alone(self):
        raw = b'{"schema_version": 1, "rounds": ['
        self.ledger_path().write_bytes(raw)
        ack = self.coordinator(FakeAdapter()).acknowledge_unsafe()
        self.assertEqual((ack.acknowledged, ack.reason), (False, 'ledger_corrupt'))
        self.assertEqual(self.ledger_path().read_bytes(), raw)

    def test_acknowledging_does_not_lift_the_daily_round_cap(self):
        for index in range(3):  # max_rounds=4：先用掉 3 个 safe 失败轮，第 4 轮以 unknown 结束
            self.clock.t = T0 + 1800 * (index + 1)
            self.coordinator(FakeAdapter(prepare=PrepareResult(False, 'x')), session=f's{index}').run()
        self.clock.t = T0 + 1800 * 4
        self._unsafe_run('s-unsafe')
        self.assertTrue(self.coordinator(FakeAdapter(), session='s-ack').acknowledge_unsafe('checked').acknowledged)
        again = FakeAdapter()
        result = self.coordinator(again, session='s-last').run()
        self.assertEqual((result.reason, result.next_action), ('round_cap', NEXT_DEFER))
        self.assertEqual(again.calls, [])
        self.assertEqual(len(self.doc()['rounds']), 4)


class LedgerProblemTest(CoordinatorTestCase):
    def test_corrupt_ledger_stops_without_touching_the_file_or_the_game(self):
        self.ledger_path().parent.mkdir(parents=True, exist_ok=True)
        raw = b'{"schema_version": 1, "rounds": ['
        self.ledger_path().write_bytes(raw)
        adapter = FakeAdapter()
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action), (S_FAILED, 'ledger_corrupt', NEXT_DEFER))
        self.assertEqual(self.ledger_path().read_bytes(), raw)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(len(list(self.root.glob('*.corrupt-*'))), 1)

    def test_ledger_deleted_mid_round_is_detected_not_rebuilt(self):
        adapter = FakeAdapter()
        self.clock.at(20, lambda: os.remove(self.ledger_path()))
        result = self.coordinator(adapter).run()
        self.assertEqual((result.reason, result.next_action), ('ledger_lost', NEXT_DEFER))
        self.assertFalse(self.ledger_path().exists())

    def test_ledger_deleted_between_runs_is_detected_by_the_journal(self):
        self.run_completed_round()
        os.remove(self.ledger_path())
        again = FakeAdapter()
        result = self.coordinator(again, session='sess-2').run()
        self.assertEqual((result.reason, result.next_action), ('ledger_lost', NEXT_DEFER))
        self.assertEqual(again.calls, [])
        self.assertFalse(self.ledger_path().exists())

    def test_lock_timeout_is_reported_as_unavailable(self):
        lock = FileLock(str(self.root / f'{self.ledger_path().name}.lock'))
        self.root.mkdir(parents=True, exist_ok=True)
        lock.acquire()
        try:
            adapter = FakeAdapter()
            result = self.coordinator(adapter, lock_timeout=0.2).run()
        finally:
            lock.release()
        self.assertEqual((result.reason, result.next_action), ('ledger_unavailable', NEXT_DEFER))
        self.assertEqual(adapter.calls, [])

    def test_write_failure_is_reported_and_creates_nothing(self):
        adapter = FakeAdapter()
        with patch('module.instance_sync.ledger.atomic_write', side_effect=OSError('disk full')):
            result = self.coordinator(adapter).run()
        self.assertEqual((result.reason, result.next_action), ('ledger_write_failed', NEXT_DEFER))
        self.assertFalse(self.ledger_path().exists())
        self.assertEqual(adapter.calls, [])


class AwaitTurnTest(CoordinatorTestCase):
    """两端有先后顺序的业务（同心之兰：A 先送、B 后回赠）：`await_turn` 在每次写下发送意图之前调用。"""

    def _join_ready_peer(self):
        peer = self.side()
        self.clock.at(0.5, peer.enter)
        self.clock.at(1, peer.ready)
        return peer

    def test_default_adapter_does_not_wait(self):
        self.assertTrue(FakeAdapter().await_turn(None))

    def test_the_hook_runs_after_prepare_and_before_the_first_dispatch(self):
        adapter = TurnAdapter()
        peer = self._join_ready_peer()
        self.clock.at(100, lambda: (peer.finish(),))
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.calls, ['prepare', 'await_turn', 'dispatch', 'judge', 'verify'])

    def test_giving_up_with_nothing_sent_is_a_safe_failure_and_never_dispatches(self):
        adapter = TurnAdapter(turns=[False])
        self._join_ready_peer()
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_PREPARE_FAILED, NEXT_RETRY))
        self.assertEqual(adapter.calls, ['prepare', 'await_turn'])
        rnd = self.last_round()
        self.assertEqual((rnd['global']['state'], rnd['global']['detail']), (sm.G_FAILED, 'await_turn'))
        self.assertEqual({p['state'] for p in rnd['participants'].values()}, {sm.P_FAILED})
        self.assertEqual(rnd['attempts'], [])

    def test_giving_up_after_the_peer_already_sent_is_unsafe_and_not_retried(self):
        peer = self._join_ready_peer()

        def peer_sends_then_we_give_up(ctx):
            peer.start()
            peer.begin()  # 对端写下了发送意图：它的点击可能已经发出
            return False

        adapter = TurnAdapter(turns=[peer_sends_then_we_give_up])
        result = self.coordinator(adapter).run()
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_PREPARE_FAILED, NEXT_DEFER))
        self.assertNotIn('dispatch', adapter.calls)

    def test_an_exception_from_the_hook_fails_the_round_first_then_propagates_the_same_object(self):
        error = RuntimeError('popup never closed')
        adapter = TurnAdapter(turns=[error])
        self._join_ready_peer()
        with self.assertRaises(RuntimeError) as ctx:
            self.coordinator(adapter).run()
        self.assertIs(ctx.exception, error)
        rnd = self.last_round()
        self.assertEqual((rnd['global']['state'], rnd['global']['reason']), (sm.G_FAILED, 'exception:RuntimeError'))
        self.assertNotIn('dispatch', adapter.calls)

    def test_a_retry_asks_again_before_the_second_attempt(self):
        adapter = TurnAdapter(judge=[Evidence.not_done('toast: busy'), Evidence.done()])
        peer = self._join_ready_peer()
        self.clock.at(100, lambda: (peer.finish(),))
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.turn_calls, 2)
        self.assertEqual(adapter.calls, ['prepare', 'await_turn', 'dispatch', 'judge',
                                         'await_turn', 'dispatch', 'judge', 'verify'])

    def test_waiting_for_the_peers_attempt_delays_our_dispatch_until_it_exists(self):
        adapter = TurnAdapter(wait_for_peer=True)
        peer = self._join_ready_peer()
        self.clock.at(2, peer.start)
        self.clock.at(20, peer.begin)  # 对端 20 秒时才写下发送意图（prepared 就够，不必等它 done）
        self.clock.at(22, lambda: (peer.resolve(sm.A_DONE), peer.verify()))
        result = self.coordinator(adapter).run()
        self.assertEqual(result.status, S_COMPLETED)
        self.assertEqual(adapter.turn_calls, 1)
        self.assertGreaterEqual(adapter.dispatch_times[0], T0 + 20)
        self.assertLess(adapter.dispatch_times[0], T0 + 22)  # 没有等到对端 done 才发

    def test_waiting_for_a_peer_that_never_sends_gives_up_within_the_budget(self):
        adapter = TurnAdapter(wait_for_peer=True)
        peer = self._join_ready_peer()
        self.clock.at(2, peer.start)  # 对端从此不再动作
        result = self.coordinator(adapter).run()
        # 等待上限取 ctx.remaining()：到点放弃（prepare_failed），双方都没发过，所以安全、可以重来
        self.assertEqual((result.status, result.reason, result.next_action),
                         (S_FAILED, sm.R_PREPARE_FAILED, NEXT_RETRY))
        self.assertEqual(self.last_round()['global']['detail'], 'await_turn')
        self.assertNotIn('dispatch', adapter.calls)
        self.assertLess(self.clock.t - T0, 190)


class ConstructionTest(CoordinatorTestCase):
    def test_instance_must_be_one_of_the_two_members(self):
        with self.assertRaises(ValueError):
            self.coordinator(FakeAdapter(), instance='oas9')

    def test_bad_timeouts_are_refused(self):
        with self.assertRaises(ValueError):
            SyncCoordinator(FakeAdapter(), instance='oas1', members=MEMBERS, rendezvous_timeout=0, root=self.root)

    def test_bad_protocol_params_are_refused(self):
        with self.assertRaises(ValueError):
            self.coordinator(FakeAdapter(params={'retry_wait': 30}))


if __name__ == '__main__':
    unittest.main()
