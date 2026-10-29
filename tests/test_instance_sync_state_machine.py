"""`module/instance_sync/state_machine.py` + `invariants.py` 的纯单元测试。

没有文件、没有真实时钟、没有设备：全部对账本文档（dict）做 op，时间由测试显式给定。
`Sim.step` 每执行一个 op 就用校验器交叉检查一次——op 函数和校验器必须一致，
所以「op 写错」和「校验器写错」都会在这里露出来。

锁住：正常链路在最后一次 verify 的同一事务里 completed；终态不可逆；失败优先（同一事务内整轮 failed）；
ready_at / deadline_at 只写一次；会合 / 预算超时；点击前意图（prepared）；
done / unknown / aborted 之后不重发；重试间隔 30 秒与预算不足立即失败；新轮次决策（含上限 3 轮、unsafe 需人工）。
"""

import copy
import unittest

from module.instance_sync import state_machine as sm
from module.instance_sync.invariants import validate_document, validate_transition

PARAMS = {'retry_wait': 30, 'budget': 180, 'min_attempt_cost': 10, 'max_rounds': 4}
MEMBERS = sm.canonical_members([('oas1', 'A01'), ('oas2', 'A02')])
PROTOCOL = sm.make_protocol(PARAMS)
KEY = sm.make_key('2026-10-21', 'xinlan', MEMBERS)
T0 = 1_000_000.0


class Sim:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.doc = sm.new_document(KEY)
        self.now = T0
        self.a = sm.Actor('oas1', 'sess-a')
        self.b = sm.Actor('oas2', 'sess-b')
        self._ids = 0

    def at(self, offset: float) -> 'Sim':
        self.now = T0 + offset
        return self

    def step(self, op, *args, **kwargs):
        old = copy.deepcopy(self.doc)
        result = op(self.doc, self.now, *args, **kwargs)
        self.test.assertEqual(validate_transition(old, self.doc), [], f'{op.__name__} produced an invalid transition')
        return result

    def enter(self, actor, round_id='r1', members=MEMBERS, protocol=PROTOCOL, rendezvous_timeout=600):
        return self.step(sm.op_enter, actor, members=members, protocol=protocol,
                         rendezvous_timeout=rendezvous_timeout, new_round_id=round_id)

    def do(self, op, actor, round_id='r1', **kwargs):
        return self.step(op, actor, round_id=round_id, **kwargs)

    def next_id(self) -> str:
        self._ids += 1
        return f'att{self._ids}'

    @property
    def round(self) -> dict:
        return self.doc['rounds'][-1]

    def to_executing(self, round_id='r1'):
        """A 0s 创建，B 10s 加入，A 12s ready，B 20s ready（deadline = 200s），双方 start。"""
        self.at(0).enter(self.a, round_id)
        self.at(10).enter(self.b, round_id)
        self.at(12).do(sm.op_ready, self.a, round_id)
        self.at(20).do(sm.op_ready, self.b, round_id)
        self.at(21).do(sm.op_start, self.a, round_id)
        self.at(21).do(sm.op_start, self.b, round_id)
        return self

    def attempt(self, actor, at, status, round_id='r1', resolve_at=None):
        """begin + resolve 一次尝试，返回 attempt_id。"""
        attempt_id = self.next_id()
        began = self.at(at).do(sm.op_begin_attempt, actor, round_id, kind='xinlan', attempt_id=attempt_id)
        self.test.assertTrue(began.ok, began)
        if status is not None:
            self.at(at if resolve_at is None else resolve_at).do(
                sm.op_resolve_attempt, actor, round_id, attempt_id=attempt_id, status=status)
        return attempt_id


class EnterAndHandshakeTest(unittest.TestCase):
    def test_first_instance_creates_round_and_peer_joins(self):
        sim = Sim(self)
        created = sim.at(0).enter(sim.a)
        self.assertEqual(created.value['outcome'], sm.OUT_CREATED)
        self.assertEqual(sim.round['rendezvous_deadline_at'], T0 + 600)
        joined = sim.at(10).enter(sim.b)
        self.assertEqual(joined.value['outcome'], sm.OUT_JOINED)
        self.assertEqual(sorted(sim.round['participants']), ['oas1', 'oas2'])
        self.assertEqual(len(sim.doc['rounds']), 1)

    def test_members_are_canonical_regardless_of_who_declares(self):
        flipped = sm.canonical_members([('oas2', 'A02'), ('oas1', 'A01')])
        self.assertEqual(flipped, MEMBERS)
        self.assertEqual(sm.make_key('2026-10-21', 'xinlan', flipped), KEY)

    def test_invalid_pair_declarations_are_refused_up_front(self):
        for bad in ([('oas1', 'A01')], [('oas1', 'A01'), ('oas1', 'A02')], [('oas1', 'A01'), ('oas2', 'A01')],
                    [('oas1', ''), ('oas2', 'A02')]):
            with self.assertRaises(ValueError):
                sm.canonical_members(bad)

    def test_mismatched_declaration_fails_the_round_and_adds_nobody(self):
        for members, protocol in (
                (sm.canonical_members([('oas1', 'A01'), ('oas3', 'A02')]), PROTOCOL),
                (MEMBERS, sm.make_protocol({**PARAMS, 'budget': 120})),
        ):
            sim = Sim(self)
            sim.at(0).enter(sim.a)
            rejected = sim.at(10).enter(sim.b, members=members, protocol=protocol)
            self.assertFalse(rejected.ok)
            self.assertEqual(rejected.value['outcome'], sm.OUT_REJECTED)
            self.assertEqual(sim.round['global']['reason'], sm.R_HANDSHAKE)
            self.assertEqual(list(sim.round['participants']), ['oas1'])

    def test_reentering_the_same_instance_resumes_and_takes_over_the_session(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        again = sim.at(5).enter(sm.Actor('oas1', 'sess-a2'))
        self.assertEqual(again.value['outcome'], sm.OUT_RESUMED)
        self.assertEqual(sim.round['participants']['oas1']['session_id'], 'sess-a2')
        # 旧会话的进程再发操作会被拒绝
        stale = sim.at(6).do(sm.op_ready, sim.a)
        self.assertEqual((stale.ok, stale.reason), (False, 'session_superseded'))

    def test_operations_on_an_old_round_id_are_rejected_and_change_nothing(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a, 'r1')
        sim.at(1).do(sm.op_fail, sim.a, 'r1', reason=sm.R_PREPARE_FAILED)
        sim.at(2).enter(sim.a, 'r2')
        before = copy.deepcopy(sim.doc)
        for op in (sm.op_ready, sm.op_start, sm.op_verify):
            result = sim.at(3).do(op, sim.a, 'r1')
            self.assertEqual((result.ok, result.reason), (False, 'round_mismatch'))
        self.assertEqual(sim.doc, before)


class StateMachineTest(unittest.TestCase):
    def test_normal_flow_completes_in_the_transaction_of_the_last_verify(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        sim.attempt(sim.b, 31, sm.A_DONE)
        first = sim.at(40).do(sm.op_verify, sim.a)
        self.assertEqual(first.value, {'completed': False})
        self.assertEqual(sim.round['global']['state'], sm.G_OPEN)
        last = sim.at(41).do(sm.op_verify, sim.b)
        self.assertEqual(last.value, {'completed': True})
        self.assertEqual(sim.round['global']['state'], sm.G_COMPLETED)
        self.assertEqual(sim.round['global']['at'], T0 + 41)

    def test_ready_at_and_deadline_are_written_once_by_the_second_ready(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        sim.at(12).do(sm.op_ready, sim.a)
        self.assertIsNone(sim.round['deadline_at'])
        sim.at(20).do(sm.op_ready, sim.b)
        self.assertEqual((sim.round['ready_at'], sim.round['deadline_at']), (T0 + 20, T0 + 200))
        # 重复 ready 被拒绝，且不会改动时间戳
        again = sim.at(50).do(sm.op_ready, sim.b)
        self.assertEqual((again.ok, again.reason), (False, 'bad_state'))
        self.assertEqual((sim.round['ready_at'], sim.round['deadline_at']), (T0 + 20, T0 + 200))

    def test_start_requires_both_ready(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        sim.at(12).do(sm.op_ready, sim.a)
        early = sim.at(13).do(sm.op_start, sim.a)
        self.assertEqual((early.ok, early.reason), (False, 'peer_not_ready'))

    def test_illegal_participant_transitions_are_rejected_without_changes(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        sim.at(12).do(sm.op_ready, sim.a)
        before = copy.deepcopy(sim.doc)
        for op, actor in ((sm.op_verify, sim.a), (sm.op_start, sim.b), (sm.op_ready, sim.a)):
            result = sim.at(13).do(op, actor)
            self.assertFalse(result.ok)
        begin = sim.at(13).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='x')
        self.assertEqual((begin.ok, begin.reason), (False, 'bad_state'))
        self.assertEqual(sim.doc, before)

    def test_participant_failure_fails_the_whole_round_in_the_same_transaction(self):
        sim = Sim(self).to_executing()
        sim.at(30).do(sm.op_fail, sim.b, reason='boom')
        self.assertEqual(sim.round['global']['state'], sm.G_FAILED)
        self.assertEqual({p['state'] for p in sim.round['participants'].values()}, {sm.P_FAILED})

    def test_terminal_participant_cannot_fail_afterwards(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        sim.at(31).do(sm.op_verify, sim.a)
        late = sim.at(32).do(sm.op_fail, sim.a, reason='too late')
        self.assertEqual((late.ok, late.reason), (False, 'terminal'))
        self.assertEqual(sim.round['participants']['oas1']['state'], sm.P_VERIFIED)
        self.assertEqual(sim.round['global']['state'], sm.G_OPEN)
        self.assertEqual(len(sim.round['late_events']), 1)

    def test_failure_after_completion_is_only_recorded(self):
        sim = Sim(self).to_executing()
        for actor, at in ((sim.a, 30), (sim.b, 31)):
            sim.attempt(actor, at, sm.A_DONE)
        sim.at(40).do(sm.op_verify, sim.a)
        sim.at(41).do(sm.op_verify, sim.b)
        late = sim.at(42).do(sm.op_fail, sim.a, reason='boom')
        self.assertFalse(late.ok)
        self.assertEqual(sim.round['global']['state'], sm.G_COMPLETED)
        self.assertEqual([e['op'] for e in sim.round['late_events']], ['fail'])

    def test_completion_after_failure_is_refused(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        sim.at(31).do(sm.op_verify, sim.a)
        sim.at(32).do(sm.op_fail, sim.b, reason='boom')
        late = sim.at(33).do(sm.op_verify, sim.b)
        self.assertEqual((late.ok, late.reason), (False, 'terminal'))
        self.assertEqual(sim.round['global']['state'], sm.G_FAILED)
        self.assertEqual(sim.round['global']['reason'], 'boom')

    def test_pending_attempt_blocks_completion(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        sim.attempt(sim.b, 31, sm.A_DONE)
        sim.at(40).do(sm.op_verify, sim.a)
        sim.at(41).do(sm.op_verify, sim.b)
        self.assertEqual(sim.round['global']['state'], sm.G_COMPLETED)
        # 手工构造「两边都 verified 但还有 prepared」：_try_complete 不会完成，校验器也不会放行
        doc = copy.deepcopy(sim.doc)
        r = doc['rounds'][-1]
        r['global'].update(state=sm.G_OPEN, reason=None, at=None)
        r['attempts'].append({'attempt_id': 'p', 'instance': 'oas1', 'kind': 'xinlan', 'seq': 2, 'prepared_at': T0 + 50,
                              'status': sm.A_PREPARED, 'resolved_at': None, 'evidence': None})
        sm._try_complete(r, T0 + 51)
        self.assertEqual(r['global']['state'], sm.G_OPEN)
        r['global'].update(state=sm.G_COMPLETED, reason='completed', at=T0 + 51)
        self.assertTrue(validate_document(doc))

    def test_verify_needs_a_confirmed_done_attempt_and_no_pending_one(self):
        sim = Sim(self).to_executing()
        none = sim.at(30).do(sm.op_verify, sim.a)
        self.assertEqual((none.ok, none.reason), (False, 'no_done_attempt'))
        sim.attempt(sim.a, 31, None)
        pending = sim.at(32).do(sm.op_verify, sim.a)
        self.assertEqual((pending.ok, pending.reason), (False, 'attempt_unresolved'))


class TimeoutTest(unittest.TestCase):
    def test_rendezvous_window_runs_from_creation_until_both_are_ready(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        sim.at(599).step(sm.op_poll)
        self.assertEqual(sim.round['global']['state'], sm.G_OPEN)
        sim.at(600).step(sm.op_poll)
        self.assertEqual((sim.round['global']['state'], sim.round['global']['reason']),
                         (sm.G_FAILED, sm.R_RENDEZVOUS_TIMEOUT))
        self.assertEqual({p['state'] for p in sim.round['participants'].values()}, {sm.P_FAILED})

    def test_one_side_ready_does_not_stop_the_rendezvous_clock(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        sim.at(12).do(sm.op_ready, sim.a)
        sim.at(700).step(sm.op_poll)
        self.assertEqual(sim.round['global']['reason'], sm.R_RENDEZVOUS_TIMEOUT)

    def test_late_ready_after_the_window_is_refused(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(10).enter(sim.b)
        late = sim.at(601).do(sm.op_ready, sim.b)
        self.assertEqual((late.ok, late.reason), (False, 'terminal'))
        self.assertEqual(sim.round['global']['reason'], sm.R_RENDEZVOUS_TIMEOUT)

    def test_budget_expires_after_the_shared_deadline(self):
        sim = Sim(self).to_executing()
        sim.at(200).step(sm.op_poll)
        self.assertEqual(sim.round['global']['state'], sm.G_OPEN)
        sim.at(200.5).step(sm.op_poll)
        self.assertEqual((sim.round['global']['state'], sim.round['global']['reason']),
                         (sm.G_FAILED, sm.R_BUDGET_TIMEOUT))

    def test_verify_after_the_deadline_is_not_accepted(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        late = sim.at(201).do(sm.op_verify, sim.a)
        self.assertEqual((late.ok, late.reason), (False, 'terminal'))
        self.assertEqual(sim.round['global']['reason'], sm.R_BUDGET_TIMEOUT)
        self.assertEqual(sim.round['participants']['oas1']['state'], sm.P_FAILED)

    def test_evidence_that_arrives_after_the_deadline_is_recorded_but_cannot_complete(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, None)
        sim.at(205).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_DONE)
        self.assertEqual(sim.round['global']['reason'], sm.R_BUDGET_TIMEOUT)
        self.assertEqual(sim.round['attempts'][0]['status'], sm.A_DONE)
        self.assertEqual(len(sim.round['late_events']), 1)


class AttemptRulesTest(unittest.TestCase):
    def test_intent_is_persisted_before_the_action(self):
        sim = Sim(self).to_executing()
        began = sim.at(30).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a1')
        self.assertTrue(began.ok)
        attempt = sim.round['attempts'][0]
        self.assertEqual((attempt['status'], attempt['prepared_at'], attempt['resolved_at']),
                         (sm.A_PREPARED, T0 + 30, None))

    def test_only_one_pending_attempt_per_instance(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, None)
        second = sim.at(31).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertEqual((second.ok, second.reason), (False, 'attempt_pending'))

    def test_retry_waits_thirty_seconds_after_a_confirmed_failure(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_NOT_DONE, resolve_at=33)
        early = sim.at(62).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertEqual((early.ok, early.reason, early.value), (False, 'too_early', {'earliest_at': T0 + 63}))
        ok = sim.at(63).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertTrue(ok.ok)
        self.assertEqual(sim.round['deadline_at'], T0 + 200)  # 重试不重置预算

    def test_retry_is_refused_when_the_budget_cannot_cover_wait_plus_attempt(self):
        sim = Sim(self).to_executing()
        # 剩余 40 秒：30 秒等待之后只剩 10 秒，正好够 min_attempt_cost=10 → 允许
        sim.attempt(sim.a, 150, sm.A_NOT_DONE, resolve_at=160)
        ok = sim.at(190).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertTrue(ok.ok)
        # 再晚一点：等待结束时剩余不足 min_attempt_cost → 立即 no_budget（不是等 30 秒后才发现）
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 150, sm.A_NOT_DONE, resolve_at=165)
        refused = sim.at(166).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertEqual((refused.ok, refused.reason), (False, 'no_budget'))

    def test_first_attempt_needs_min_cost_left(self):
        sim = Sim(self).to_executing()
        refused = sim.at(195).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a1')
        self.assertEqual((refused.ok, refused.reason), (False, 'no_budget'))

    def test_never_resend_after_done(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        again = sim.at(100).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertEqual((again.ok, again.reason), (False, 'no_resend'))

    def test_unknown_result_fails_the_round_and_nothing_can_be_resent(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, None)
        sim.at(40).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_UNKNOWN, evidence='no toast')
        self.assertEqual((sim.round['global']['state'], sim.round['global']['reason']),
                         (sm.G_FAILED, sm.R_ATTEMPT_UNKNOWN))
        again = sim.at(100).do(sm.op_begin_attempt, sim.a, kind='xinlan', attempt_id='a2')
        self.assertEqual((again.ok, again.reason), (False, 'terminal'))

    def test_aborted_before_dispatch_also_fails_the_round(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, None)
        sim.at(31).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_ABORTED)
        self.assertEqual(sim.round['global']['reason'], sm.R_ATTEMPT_ABORTED)

    def test_resolution_is_recorded_even_when_the_round_already_failed(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, None)
        sim.at(31).do(sm.op_fail, sim.b, reason='boom')
        sim.at(32).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_UNKNOWN)
        self.assertEqual(sim.round['attempts'][0]['status'], sm.A_UNKNOWN)
        self.assertEqual(sim.round['global']['reason'], 'boom')  # 终态原因不被覆盖
        self.assertEqual([e['op'] for e in sim.round['late_events']], ['resolve_attempt'])

    def test_an_attempt_cannot_be_resolved_twice_or_by_the_peer(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, sm.A_NOT_DONE)
        twice = sim.at(31).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_DONE)
        self.assertEqual((twice.ok, twice.reason), (False, 'already_resolved'))
        other = sim.at(31).do(sm.op_resolve_attempt, sim.b, attempt_id=attempt_id, status=sm.A_DONE)
        self.assertEqual((other.ok, other.reason), (False, 'no_attempt'))


class EnterDecisionTest(unittest.TestCase):
    def _failed_safe_round(self, sim, round_id, at):
        sim.at(at).enter(sim.a, round_id)
        sim.at(at + 1).do(sm.op_fail, sim.a, round_id, reason=sm.R_PREPARE_FAILED)

    def test_completed_round_means_nothing_more_to_do_today(self):
        sim = Sim(self).to_executing()
        for actor, at in ((sim.a, 30), (sim.b, 31)):
            sim.attempt(actor, at, sm.A_DONE)
        sim.at(40).do(sm.op_verify, sim.a)
        sim.at(41).do(sm.op_verify, sim.b)
        result = sim.at(5000).enter(sim.a, 'r2')
        self.assertEqual((result.ok, result.value['outcome']), (True, sm.OUT_COMPLETED))
        self.assertEqual(len(sim.doc['rounds']), 1)

    def test_safe_failure_opens_a_new_round_and_keeps_the_old_one(self):
        sim = Sim(self)
        self._failed_safe_round(sim, 'r1', 0)
        old = copy.deepcopy(sim.round)
        result = sim.at(1800).enter(sim.a, 'r2')
        self.assertEqual(result.value['outcome'], sm.OUT_CREATED)
        self.assertEqual([r['round_id'] for r in sim.doc['rounds']], ['r1', 'r2'])
        self.assertEqual(sim.doc['rounds'][0], old)
        self.assertEqual(sim.doc['rounds'][1]['seq'], 2)

    def test_rendezvous_timeout_is_a_safe_failure(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a, 'r1')
        result = sim.at(1800).enter(sim.a, 'r2')  # 进入时顺带把过期的 r1 判 failed，再开 r2
        self.assertEqual(result.value['outcome'], sm.OUT_CREATED)
        self.assertEqual(sim.doc['rounds'][0]['global']['reason'], sm.R_RENDEZVOUS_TIMEOUT)

    def test_round_cap_is_the_first_round_plus_three_retries(self):
        sim = Sim(self)
        for index in range(4):  # max_rounds=4：第一轮 + 最多 3 次自动重来
            self._failed_safe_round(sim, f'r{index + 1}', index * 1800)
        capped = sim.at(9000).enter(sim.a, 'r5')
        self.assertEqual((capped.ok, capped.reason, capped.value['outcome']), (False, 'round_cap', sm.OUT_CAP))
        self.assertEqual(len(sim.doc['rounds']), 4)

    def test_unknown_result_blocks_new_rounds_for_the_day(self):
        sim = Sim(self).to_executing()
        attempt_id = sim.attempt(sim.a, 30, None)
        sim.at(31).do(sm.op_resolve_attempt, sim.a, attempt_id=attempt_id, status=sm.A_UNKNOWN)
        result = sim.at(5000).enter(sim.a, 'r2')
        self.assertEqual((result.ok, result.value['outcome']), (False, sm.OUT_MANUAL))
        self.assertEqual(len(sim.doc['rounds']), 1)

    def test_confirmed_but_unverified_send_blocks_new_rounds(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_DONE)
        sim.at(31).do(sm.op_fail, sim.b, reason='boom')
        result = sim.at(5000).enter(sim.a, 'r2')
        self.assertEqual(result.value['outcome'], sm.OUT_MANUAL)

    def test_classification(self):
        safe = {'attempts': [{'status': sm.A_NOT_DONE}, {'status': sm.A_ABORTED}]}
        self.assertEqual(sm.classify_failed_round(safe), sm.SAFE)
        self.assertEqual(sm.classify_failed_round({'attempts': []}), sm.SAFE)
        for status in (sm.A_PREPARED, sm.A_UNKNOWN, sm.A_DONE):
            self.assertEqual(sm.classify_failed_round({'attempts': [{'status': status}]}), sm.UNSAFE)


class AcknowledgeUnsafeTest(unittest.TestCase):
    """人工确认 unsafe：只在最后一轮的 late_events 里追加一条，之后当天才能再开新轮。"""

    def _unsafe_round(self, round_id='r1') -> Sim:
        sim = Sim(self).to_executing(round_id)
        attempt_id = sim.attempt(sim.a, 30, None, round_id)
        sim.at(31).do(sm.op_resolve_attempt, sim.a, round_id, attempt_id=attempt_id, status=sm.A_UNKNOWN)
        self.assertEqual(sim.round['global']['state'], sm.G_FAILED)
        return sim

    def test_acknowledging_unblocks_a_new_round_and_keeps_the_evidence(self):
        sim = self._unsafe_round()
        blocked = sim.at(5000).enter(sim.a, 'r2')
        self.assertEqual(blocked.value['outcome'], sm.OUT_MANUAL)
        before = copy.deepcopy(sim.round)
        acked = sim.at(5001).step(sm.op_acknowledge_unsafe, sim.a, reason='checked the game by hand')
        self.assertTrue(acked.ok)
        self.assertEqual(acked.value['seq'], 1)
        # 除 late_events 追加了一条以外，旧轮次原样保留：状态、原因、attempts 都不变
        after = copy.deepcopy(sim.round)
        self.assertEqual([e['op'] for e in after.pop('late_events')], [sm.LATE_ACK])
        before.pop('late_events')
        self.assertEqual(after, before)
        self.assertEqual(sim.round['late_events'][0]['instance'], 'oas1')
        self.assertEqual(sim.round['late_events'][0]['detail'], 'checked the game by hand')
        # 分类仍然是 unsafe（事实没变），只是不再拦截
        self.assertEqual(sm.classify_failed_round(sim.round), sm.UNSAFE)
        self.assertTrue(sm.is_acknowledged(sim.round))
        created = sim.at(5002).enter(sim.a, 'r2')
        self.assertEqual(created.value['outcome'], sm.OUT_CREATED)
        self.assertEqual([r['round_id'] for r in sim.doc['rounds']], ['r1', 'r2'])
        self.assertEqual(sim.doc['rounds'][0]['global']['reason'], sm.R_ATTEMPT_UNKNOWN)

    def test_a_new_unsafe_round_needs_a_new_acknowledgement(self):
        sim = self._unsafe_round()
        sim.at(5000).step(sm.op_acknowledge_unsafe, sim.a)
        sim.at(5001).enter(sim.a, 'r2')
        sim.at(5002).enter(sim.b, 'r2')
        sim.at(5003).do(sm.op_ready, sim.a, 'r2')
        sim.at(5004).do(sm.op_ready, sim.b, 'r2')
        sim.at(5005).do(sm.op_start, sim.a, 'r2')
        attempt_id = sim.attempt(sim.a, 5010, None, 'r2')
        sim.at(5011).do(sm.op_resolve_attempt, sim.a, 'r2', attempt_id=attempt_id, status=sm.A_UNKNOWN)
        blocked = sim.at(9000).enter(sim.a, 'r3')
        self.assertEqual(blocked.value['outcome'], sm.OUT_MANUAL)

    def test_an_open_round_cannot_be_acknowledged(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, None)  # 带着 prepared 的 open 轮次：看上去像 unsafe，但还在进行
        before = copy.deepcopy(sim.doc)
        refused = sim.at(40).step(sm.op_acknowledge_unsafe, sim.a)
        self.assertEqual((refused.ok, refused.reason), (False, 'round_open'))
        self.assertEqual(sim.doc, before)

    def test_an_expired_open_round_is_failed_first_and_then_acknowledged(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, None)  # 崩溃后留着 prepared，已经过了 deadline（200 秒）
        result = sim.at(300).step(sm.op_acknowledge_unsafe, sim.a)
        self.assertTrue(result.ok)
        self.assertEqual(sim.round['global']['reason'], sm.R_BUDGET_TIMEOUT)
        self.assertEqual([e['op'] for e in sim.round['late_events']], [sm.LATE_ACK])

    def test_nothing_to_acknowledge_changes_nothing(self):
        none = Sim(self)
        self.assertEqual(none.at(1).step(sm.op_acknowledge_unsafe, none.a).reason, 'no_round')

        done = Sim(self).to_executing()
        for actor, at in ((done.a, 30), (done.b, 31)):
            done.attempt(actor, at, sm.A_DONE)
        done.at(40).do(sm.op_verify, done.a)
        done.at(41).do(sm.op_verify, done.b)
        before = copy.deepcopy(done.doc)
        self.assertEqual(done.at(50).step(sm.op_acknowledge_unsafe, done.a).reason, 'already_completed')
        self.assertEqual(done.doc, before)

        safe = Sim(self)
        safe.at(0).enter(safe.a)
        safe.at(1).do(sm.op_fail, safe.a, reason=sm.R_PREPARE_FAILED)
        before = copy.deepcopy(safe.doc)
        self.assertEqual(safe.at(50).step(sm.op_acknowledge_unsafe, safe.a).reason, 'not_unsafe')
        self.assertEqual(safe.doc, before)

    def test_acknowledging_twice_is_a_no_op(self):
        sim = self._unsafe_round()
        self.assertTrue(sim.at(100).step(sm.op_acknowledge_unsafe, sim.a).ok)
        second = sim.at(101).step(sm.op_acknowledge_unsafe, sim.b)
        self.assertEqual((second.ok, second.reason), (False, 'not_unsafe'))
        self.assertEqual(len(sim.round['late_events']), 1)

    def test_acknowledging_does_not_lift_the_daily_round_cap(self):
        sim = Sim(self)
        for index in range(3):  # PARAMS['max_rounds'] = 4：先用掉 3 个 safe 失败轮
            sim.at(index * 1800).enter(sim.a, f'r{index + 1}')
            sim.at(index * 1800 + 1).do(sm.op_fail, sim.a, f'r{index + 1}', reason=sm.R_PREPARE_FAILED)
        base = 6000  # 第 4 轮以 unknown 结束
        sim.at(base).enter(sim.a, 'r4')
        sim.at(base + 10).enter(sim.b, 'r4')
        sim.at(base + 12).do(sm.op_ready, sim.a, 'r4')
        sim.at(base + 20).do(sm.op_ready, sim.b, 'r4')
        sim.at(base + 21).do(sm.op_start, sim.a, 'r4')
        attempt_id = sim.attempt(sim.a, base + 30, None, 'r4')
        sim.at(base + 31).do(sm.op_resolve_attempt, sim.a, 'r4', attempt_id=attempt_id, status=sm.A_UNKNOWN)
        self.assertTrue(sim.at(base + 100).step(sm.op_acknowledge_unsafe, sim.a).ok)
        capped = sim.at(base + 101).enter(sim.a, 'r5')
        self.assertEqual((capped.ok, capped.value['outcome']), (False, sm.OUT_CAP))
        self.assertEqual(len(sim.doc['rounds']), 4)

    def test_only_a_member_can_acknowledge(self):
        sim = self._unsafe_round()
        before = copy.deepcopy(sim.doc)
        stranger = sm.Actor('oas9', 'sess-x')
        refused = sim.at(100).step(sm.op_acknowledge_unsafe, stranger)
        self.assertEqual((refused.ok, refused.reason), (False, 'not_member'))
        self.assertEqual(sim.doc, before)

    def test_validator_refuses_an_acknowledgement_on_a_round_that_is_not_failed(self):
        sim = Sim(self).to_executing()
        old = copy.deepcopy(sim.doc)
        new = copy.deepcopy(old)
        new['rounds'][-1]['late_events'].append(
            {'at': T0 + 50, 'instance': 'oas1', 'op': sm.LATE_ACK, 'detail': 'forged'})
        problems = validate_transition(old, new)
        self.assertTrue(any('acknowledge_unsafe' in p for p in problems), problems)

    def test_validator_refuses_to_remove_an_acknowledgement(self):
        sim = self._unsafe_round()
        sim.at(100).step(sm.op_acknowledge_unsafe, sim.a)
        new = copy.deepcopy(sim.doc)
        new['rounds'][-1]['late_events'].clear()
        self.assertTrue(validate_transition(sim.doc, new))


class ViewTest(unittest.TestCase):
    def test_view_is_a_read_only_snapshot(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_NOT_DONE)
        view = sm.build_view(sim.doc, 'oas1')
        self.assertEqual((view.me_state, view.peer_state, view.deadline_at), (sm.P_EXECUTING, sm.P_EXECUTING, T0 + 200))
        self.assertEqual([a.status for a in view.my_attempts], [sm.A_NOT_DONE])
        self.assertEqual(view.peer_attempts, ())
        with self.assertRaises(Exception):
            view.global_state = 'completed'
        with self.assertRaises(TypeError):
            view.params['budget'] = 1


class InvariantValidatorTest(unittest.TestCase):
    """校验器不信任 op：手工把合法账本改坏，必须被拦下。"""

    def setUp(self):
        sim = Sim(self).to_executing()
        sim.attempt(sim.a, 30, sm.A_NOT_DONE, resolve_at=33)
        sim.attempt(sim.b, 31, None)
        self.sim = sim
        self.old = copy.deepcopy(sim.doc)

    def _problems(self, mutate) -> list:
        new = copy.deepcopy(self.old)
        mutate(new['rounds'][-1])
        return validate_transition(self.old, new)

    def _terminal(self, reason='boom'):
        sim = self.sim
        sim.at(40).do(sm.op_fail, sim.a, reason=reason)
        return copy.deepcopy(sim.doc)

    def test_the_untouched_ledger_is_valid(self):
        self.assertEqual(validate_document(self.old, KEY), [])
        self.assertEqual(validate_transition(self.old, copy.deepcopy(self.old)), [])

    def test_terminal_global_cannot_change(self):
        old = self._terminal()
        new = copy.deepcopy(old)
        new['rounds'][-1]['global'].update(state=sm.G_COMPLETED, reason='completed')
        self.assertTrue(validate_transition(old, new))
        new = copy.deepcopy(old)
        new['rounds'][-1]['global']['reason'] = 'other'
        self.assertTrue(validate_transition(old, new))

    def test_failure_first_open_round_cannot_hold_a_failed_participant(self):
        def mutate(r):
            r['participants']['oas1']['state'] = sm.P_FAILED
        self.assertTrue(self._problems(mutate))

    def test_deadline_and_ready_at_cannot_be_rewritten(self):
        for field in ('ready_at', 'deadline_at'):
            self.assertTrue(self._problems(lambda r, f=field: r.update({f: r[f] + 1})), field)

    def test_attempts_are_append_only_and_resolved_ones_immutable(self):
        self.assertTrue(self._problems(lambda r: r['attempts'].pop(0)))
        self.assertTrue(self._problems(lambda r: r['attempts'][0].update(status=sm.A_DONE)))
        self.assertTrue(self._problems(lambda r: r['attempts'][0].update(attempt_id='forged')))

    def test_no_resend_after_done(self):
        old = copy.deepcopy(self.old)
        old['rounds'][-1]['attempts'][0]['status'] = sm.A_DONE
        new = copy.deepcopy(old)
        new['rounds'][-1]['attempts'].append({
            'attempt_id': 'x', 'instance': 'oas1', 'kind': 'xinlan', 'seq': 2, 'prepared_at': T0 + 100,
            'status': sm.A_PREPARED, 'resolved_at': None, 'evidence': None})
        problems = validate_transition(old, new)
        self.assertTrue(any('resent' in p for p in problems), problems)

    def test_unknown_or_aborted_attempt_cannot_coexist_with_an_open_round(self):
        # op 在记录 unknown / aborted 的同一事务里把整轮置 failed；只改状态不失败整轮的变更必须被拒
        for status in (sm.A_UNKNOWN, sm.A_ABORTED):
            def mutate(r, status=status):
                r['attempts'][0]['status'] = status
            self.assertTrue(self._problems(mutate), status)

    def test_retry_before_retry_wait_is_rejected(self):
        def mutate(r):
            r['attempts'].append({'attempt_id': 'x', 'instance': 'oas1', 'kind': 'xinlan', 'seq': 2,
                                  'prepared_at': T0 + 50, 'status': sm.A_PREPARED, 'resolved_at': None,
                                  'evidence': None})
        problems = self._problems(mutate)
        self.assertTrue(any('retry_wait' in p for p in problems), problems)

    def test_retry_after_retry_wait_is_accepted(self):
        def mutate(r):
            r['attempts'].append({'attempt_id': 'x', 'instance': 'oas1', 'kind': 'xinlan', 'seq': 2,
                                  'prepared_at': T0 + 63, 'status': sm.A_PREPARED, 'resolved_at': None,
                                  'evidence': None})
        self.assertEqual(self._problems(mutate), [])

    def test_second_pending_attempt_for_the_same_instance_is_rejected(self):
        def mutate(r):
            r['attempts'].append({'attempt_id': 'x', 'instance': 'oas2', 'kind': 'xinlan', 'seq': 2,
                                  'prepared_at': T0 + 100, 'status': sm.A_PREPARED, 'resolved_at': None,
                                  'evidence': None})
        self.assertTrue(self._problems(mutate))

    def test_attempt_cannot_be_added_to_a_terminal_round(self):
        old = self._terminal()
        new = copy.deepcopy(old)
        new['rounds'][-1]['attempts'].append({
            'attempt_id': 'x', 'instance': 'oas1', 'kind': 'xinlan', 'seq': 2, 'prepared_at': T0 + 100,
            'status': sm.A_PREPARED, 'resolved_at': None, 'evidence': None})
        self.assertTrue(validate_transition(old, new))

    def test_participant_cannot_skip_states_or_leave_a_terminal_state(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(1).enter(sim.b)
        old = copy.deepcopy(sim.doc)
        new = copy.deepcopy(old)
        new['rounds'][-1]['participants']['oas1']['state'] = sm.P_VERIFIED
        self.assertTrue(validate_transition(old, new))
        terminal = self._terminal()
        new = copy.deepcopy(terminal)
        new['rounds'][-1]['participants']['oas1']['state'] = sm.P_EXECUTING
        self.assertTrue(validate_transition(terminal, new))

    def test_completed_requires_both_verified_and_no_failure(self):
        def mutate(r):
            r['global'].update(state=sm.G_COMPLETED, reason='completed', at=T0 + 60)
        self.assertTrue(self._problems(mutate))

    def test_late_events_are_append_only(self):
        self._terminal()
        sim = self.sim
        sim.at(41).do(sm.op_fail, sim.b, reason='again')  # 终态之后的报告只追加 late_events
        self.assertEqual(len(sim.round['late_events']), 1)
        new = copy.deepcopy(sim.doc)
        new['rounds'][-1]['late_events'].clear()
        self.assertTrue(validate_transition(sim.doc, new))

    def test_nobody_can_join_a_terminal_round(self):
        sim = Sim(self)
        sim.at(0).enter(sim.a)
        sim.at(1).do(sm.op_fail, sim.a, reason='boom')
        old = copy.deepcopy(sim.doc)
        new = copy.deepcopy(old)
        new['rounds'][-1]['participants']['oas2'] = {'alias': 'A02', 'session_id': 's', 'state': sm.P_JOINED,
                                                       'state_at': T0 + 2, 'failure': None}
        self.assertTrue(validate_transition(old, new))

    def test_only_a_fresh_round_can_be_appended_after_a_terminal_one(self):
        old = self._terminal()
        sim = Sim(self)
        sim.doc = copy.deepcopy(old)
        sim.at(5000).enter(sim.a, 'r2')
        self.assertEqual(validate_transition(old, sim.doc), [])
        # 上一轮还是 open 就追加新轮：非法
        open_old = copy.deepcopy(self.old)
        bad = copy.deepcopy(open_old)
        bad['rounds'].append(copy.deepcopy(sim.doc['rounds'][-1]))
        self.assertTrue(validate_transition(open_old, bad))

    def test_malformed_documents_are_reported_not_raised(self):
        good = copy.deepcopy(self.old)
        cases = [None, [], {}, {**good, 'schema_version': 99}, {**good, 'key': 1}, {**good, 'rounds': 'x'}]
        broken = copy.deepcopy(good)
        broken['rounds'][0]['participants']['oas1']['state'] = ['x']
        cases.append(broken)
        broken = copy.deepcopy(good)
        del broken['rounds'][0]['global']
        cases.append(broken)
        for doc in cases:
            self.assertTrue(validate_document(doc), doc)

    def test_wrong_key_is_reported(self):
        other = sm.make_key('2026-10-22', 'xinlan', MEMBERS)
        self.assertTrue(validate_document(self.old, other))


class KeyAndParamsTest(unittest.TestCase):
    def test_filename_is_safe_and_stable(self):
        members = sm.canonical_members([('oas1', 'a/b:c*?'), ('oas2', '同心')])
        key = sm.make_key('2026-10-21', 'xinlan', members)
        name = sm.ledger_filename(key)
        self.assertRegex(name, r'^2026-10-21_xinlan_[0-9a-f]{8}\.json$')
        self.assertEqual(name, sm.ledger_filename(sm.make_key('2026-10-21', 'xinlan', list(reversed(members)))))

    def test_invalid_business_day_or_id_is_refused(self):
        for day, business in (('2026/10/21', 'xinlan'), ('2026-10-21', 'a b'), ('2026-10-21', ''), ('', 'xinlan')):
            with self.assertRaises(ValueError):
                sm.make_key(day, business, MEMBERS)

    def test_protocol_params_are_validated(self):
        with self.assertRaises(ValueError):
            sm.make_protocol({'retry_wait': 30})
        with self.assertRaises(ValueError):
            sm.make_protocol({**PARAMS, 'budget': 0})
        with self.assertRaises(ValueError):
            sm.make_protocol({**PARAMS, 'max_rounds': 0})
        with self.assertRaises(ValueError):
            sm.make_protocol({**PARAMS, 'retry_wait': True})


if __name__ == '__main__':
    unittest.main()
