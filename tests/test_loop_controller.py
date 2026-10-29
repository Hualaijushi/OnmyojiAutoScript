# This Python file uses the following encoding: utf-8
"""御魂 → 个人突破 循环控制器：用真实的 PresenceBoard 写临时目录，两个控制器模拟两个实例。

不连设备、不启动游戏。离线通过只说明协议和状态机正确，不等于真机通过。
"""

import json
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from types import SimpleNamespace
from unittest.mock import patch

from module.instance_sync.team import PresenceBoard, GO, WAIT, POSTPONE, STALE, decide, IDLE, WAITING
from module.script import loop_controller as lc
from module.script.loop_controller import (
    ACTIVE, CANCELLED, COMPLETED, FAILED, FORMING, JOINED, LoopController, LoopParams,
)


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 24, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class LoopTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.clock = FakeClock()
        # 测试里不节流检查，状态变化立即可见
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        self.addCleanup(patch.stopall)
        self.notices = {'A': [], 'B': []}
        self.board_a = PresenceBoard(self.tmp, 'A', 'B', clock=self.clock)
        self.board_b = PresenceBoard(self.tmp, 'B', 'A', clock=self.clock)
        self.a = LoopController('A', rng=Random(7), notify=self.notices['A'].append)
        self.b = LoopController('B', rng=Random(9), notify=self.notices['B'].append)
        self.a.bind_board(self.board_a)
        self.b.bind_board(self.board_b)

    def params(self, role, rounds=2, tmin=3, tmax=5):
        return LoopParams(role, rounds, tmin, tmax)

    def start_both(self, rounds=2, tmin=3, tmax=5):
        """A 是队长、B 是队员，一直走到双方 ACTIVE。"""
        self.assertEqual(self.a.request_start(self.params('leader', rounds, tmin, tmax), self.board_a), 'started')
        self.assertEqual(self.b.request_start(self.params('member', rounds, tmin, tmax), self.board_b), 'started')
        for _ in range(3):
            self.b.tick()
            self.a.tick()
        self.assertEqual((self.a.state, self.b.state), (ACTIVE, ACTIVE))

    def go_both(self):
        """两边都经过 barrier 直到 go（先到的先发布 ready）。"""
        verdicts = []
        for _ in range(4):
            verdicts = [self.a.barrier(), self.b.barrier()]
            if verdicts == ['go', 'go']:
                break
        return verdicts

    def leader_batch(self, n=None):
        """队长打完当前这一批：每场邀请前记录、结算后计一场，最后上报。"""
        target = n if n is not None else self.a.step_target()
        for _ in range(target):
            self.a.attempt_begin()
            self.a.battle_settled(True)
        self.a.report_batch(True)

    def finish_step(self, ctrl, command, **kwargs):
        kwargs.setdefault('ended', True)
        kwargs.setdefault('delay_success', True)
        # Script 总是先 begin_run 再运行步骤；测试里没调用过的补上，免得把步骤当成插入任务
        if command == ctrl.current_step() and not ctrl.in_step:
            ctrl.begin_run()
        ctrl.after_run(command, **kwargs)


class JoinTest(LoopTestBase):
    def test_leader_first_then_member_get_same_loop_id(self):
        self.a.request_start(self.params('leader'), self.board_a)
        self.assertEqual(self.a.state, FORMING)
        self.a.tick()
        self.assertEqual(self.a.state, FORMING)            # 对方还没来：只等待
        self.b.request_start(self.params('member'), self.board_b)
        self.b.tick()
        self.assertEqual(self.b.state, JOINED)
        self.assertEqual(self.b.loop['id'], self.a.loop['id'])
        self.a.tick()
        self.b.tick()
        self.assertEqual((self.a.state, self.b.state), (ACTIVE, ACTIVE))

    def test_member_first_waits_without_loss_even_after_hours(self):
        self.b.request_start(self.params('member'), self.board_b)
        for _ in range(3):
            self.clock.advance(hours=1)
            self.board_b.heartbeat()
            self.b.tick()
        self.assertEqual(self.b.state, FORMING)            # 没绑定任何参与者：不是失联
        self.assertIsNone(self.b.loop['id'])
        self.a.request_start(self.params('leader'), self.board_a)
        self.b.tick()
        self.a.tick()
        self.b.tick()
        self.assertEqual((self.a.state, self.b.state), (ACTIVE, ACTIVE))

    def test_leader_waits_forever_when_peer_never_comes(self):
        self.a.request_start(self.params('leader'), self.board_a)
        for _ in range(5):
            self.clock.advance(hours=2)
            self.a.tick()
        self.assertEqual(self.a.state, FORMING)
        self.assertEqual(self.a.barrier(), 'wait')

    def test_config_mismatch_stops_both_before_any_battle(self):
        self.a.request_start(self.params('leader', rounds=2), self.board_a)
        self.b.request_start(self.params('member', rounds=3), self.board_b)
        self.b.tick()
        self.assertEqual(self.b.state, FAILED)
        self.assertEqual(self.b.loop['reason'], 'config_mismatch')
        self.a.tick()
        self.assertEqual(self.a.state, FAILED)
        self.assertEqual(self.a.barrier(), 'failed')
        self.assertEqual(self.b.barrier(), 'failed')

    def test_target_range_mismatch_is_rejected_too(self):
        self.a.request_start(self.params('leader', tmin=3, tmax=5), self.board_a)
        self.b.request_start(self.params('member', tmin=3, tmax=6), self.board_b)
        self.b.tick()
        self.a.tick()
        self.assertEqual((self.a.state, self.b.state), (FAILED, FAILED))

    def test_two_leaders_or_two_members_are_a_role_conflict(self):
        self.a.request_start(self.params('leader'), self.board_a)
        self.b.request_start(self.params('leader'), self.board_b)
        self.a.tick()
        self.b.tick()
        self.assertEqual((self.a.state, self.b.state), (FAILED, FAILED))
        self.assertEqual(self.a.loop['reason'], 'role_conflict')

    def test_two_members_conflict(self):
        self.a.request_start(self.params('member'), self.board_a)
        self.b.request_start(self.params('member'), self.board_b)
        self.a.tick()
        self.b.tick()
        self.assertEqual((self.a.state, self.b.state), (FAILED, FAILED))

    def test_invalid_requests_are_rejected_and_reported(self):
        self.assertEqual(self.a.request_start(self.params('alone'), self.board_a), 'invalid:role_invalid')
        self.assertEqual(self.a.request_start(self.params('leader', rounds=0), self.board_a), 'invalid:rounds_invalid')
        self.assertEqual(self.a.request_start(self.params('leader', tmin=9, tmax=3), self.board_a),
                         'invalid:target_range_invalid')
        self.assertEqual(self.a.request_start(self.params('leader'), None), 'invalid:team_sync_unavailable')
        self.assertIsNone(self.a.loop)
        self.assertEqual(len(self.notices['A']), 4)

    def test_duplicate_request_does_not_make_a_second_loop(self):
        self.a.request_start(self.params('leader'), self.board_a)
        first = self.a.loop['id']
        self.assertEqual(self.a.request_start(self.params('leader'), self.board_a), 'ignored')
        self.assertEqual(self.a.loop['id'], first)


class JoinFailureTest(LoopTestBase):
    def test_bound_member_stops_when_leader_restarts_before_active(self):
        self.a.request_start(self.params('leader'), self.board_a)
        self.b.request_start(self.params('member'), self.board_b)
        self.b.tick()
        self.assertEqual(self.b.state, JOINED)
        # 队长进程重启：新的板子（新 boot_id）、没有循环
        new_board = PresenceBoard(self.tmp, 'A', 'B', clock=self.clock)
        new_board.publish(IDLE, {})
        self.b.tick()
        self.assertEqual(self.b.state, FAILED)
        self.assertIn(self.b.loop['reason'], ('peer_restarted', 'peer_left'))

    def test_bound_member_stops_when_leader_goes_silent(self):
        self.a.request_start(self.params('leader'), self.board_a)
        self.b.request_start(self.params('member'), self.board_b)
        self.b.tick()
        self.clock.advance(seconds=STALE.seconds + 5)
        self.board_b.heartbeat()
        self.b.tick()
        self.assertEqual(self.b.state, FAILED)
        self.assertEqual(self.b.loop['reason'], 'peer_lost')

    def test_bound_peer_cancel_during_join_is_mirrored(self):
        self.a.request_start(self.params('leader'), self.board_a)
        self.b.request_start(self.params('member'), self.board_b)
        self.b.tick()
        self.a.cancel_by_command({'boot_id': self.board_a.boot_id, 'loop_id': self.a.loop['id'], 'reason': 'ui_stop'})
        self.b.tick()
        self.assertEqual(self.b.state, CANCELLED)

    def test_failure_propagates_with_the_same_loop_id(self):
        self.start_both()
        self.a.fail('count_uncertain')
        self.b.tick()
        self.assertEqual(self.b.state, FAILED)
        self.assertIn('count_uncertain', self.b.loop['reason'])

    def test_peer_restart_after_active_stops_loop(self):
        self.start_both()
        PresenceBoard(self.tmp, 'A', 'B', clock=self.clock).publish(IDLE, {})
        self.b.tick()
        self.assertEqual(self.b.state, FAILED)

    def test_old_loop_state_of_the_peer_is_not_joinable(self):
        self.start_both(rounds=1)
        self.a.fail('x')
        self.b.tick()
        # 新的一次：队员重新请求时，队长文件里是旧循环的终态，不能被当成可加入
        self.b.request_start(self.params('member', rounds=1), self.board_b)
        self.b.tick()
        self.assertEqual(self.b.state, FORMING)


class FullLoopTest(LoopTestBase):
    def run_orochi_step(self):
        self.assertEqual(self.go_both(), ['go', 'go'])
        self.assertTrue(self.a.begin_run())
        self.assertTrue(self.b.begin_run())
        self.leader_batch()
        self.b.member_batch_state()
        self.assertEqual(self.b.member_batch_state(), 'done')
        self.finish_step(self.a, 'Orochi')
        self.finish_step(self.b, 'Orochi')

    def run_raid_step(self, first, second):
        self.assertEqual(self.go_both(), ['go', 'go'])
        self.assertTrue(self.a.begin_run())
        self.assertTrue(self.b.begin_run())
        first.after_run('RealmRaid', ended=True, delay_success=True)

    def test_two_rounds_alternate_and_earlier_finisher_waits(self):
        self.start_both(rounds=2)
        targets = []
        for rnd in range(2):
            self.run_orochi_step()
            targets.append(self.a.targets[rnd * 2])
            self.assertEqual(self.b.targets[rnd * 2], self.a.targets[rnd * 2])      # 队员用同一个目标
            self.assertEqual(self.a.counts[rnd * 2], targets[-1])
            # 个人突破：A 先完成 → 等 B，B 完成后才进入下一批
            self.assertEqual(self.go_both(), ['go', 'go'])
            self.a.begin_run()
            self.b.begin_run()
            self.finish_step(self.a, 'RealmRaid', delay_success=None)
            self.assertEqual(self.a.loop['done_idx'], rnd * 2 + 1)
            self.assertEqual(self.b.loop['done_idx'], rnd * 2)
            if rnd == 0:
                self.assertEqual(self.a.barrier(), 'wait')          # 下一批要等 B 的突破完成
            self.finish_step(self.b, 'RealmRaid', delay_success=None)
        self.a.tick()
        self.b.tick()
        self.assertEqual((self.a.state, self.b.state), (COMPLETED, COMPLETED))
        self.assertEqual(self.a.barrier(), 'idle')
        self.assertTrue(all(3 <= t <= 5 for t in targets))

    def test_target_is_random_once_per_batch_and_kept_on_retry(self):
        self.start_both(rounds=1, tmin=1, tmax=999)
        self.assertEqual(self.go_both(), ['go', 'go'])
        first = self.a.step_target()
        self.a.begin_run()
        self.finish_step(self.a, 'Orochi', ended=True)               # 没有完成事实：同一步重来
        self.a.barrier()
        self.assertEqual(self.a.step_target(), first)               # 恢复 / 重来不重新随机
        self.assertEqual(self.a.loop['target'], {'idx': 0, 'n': first})

    def test_terminal_state_survives_publish_heartbeat_and_task_switch(self):
        self.start_both(rounds=1)
        self.run_orochi_step()
        self.go_both()
        self.finish_step(self.a, 'RealmRaid', delay_success=None)
        self.finish_step(self.b, 'RealmRaid', delay_success=None)
        self.a.tick()
        self.assertEqual(self.a.state, COMPLETED)
        self.board_a.publish(IDLE, {}, task='Orochi')               # 普通 publish
        self.board_a.heartbeat()
        self.board_a.report_progress(1)
        doc = self.board_b.read_peer()
        self.assertEqual(doc['loop']['state'], COMPLETED)
        self.assertEqual(doc['loop']['final']['done_idx'], 1)

    def test_late_reader_sees_completion_even_after_peer_starts_a_new_loop(self):
        self.start_both(rounds=1)
        self.run_orochi_step()
        self.go_both()
        self.finish_step(self.a, 'RealmRaid', delay_success=None)
        self.a.tick()
        self.assertEqual(self.a.state, ACTIVE)                       # A 最先完成，等 B
        self.finish_step(self.b, 'RealmRaid', delay_success=None)    # B 完成时读到 A 完成 → 自己 COMPLETED
        self.assertEqual(self.b.state, COMPLETED)
        old_id = self.b.loop['id']
        # B 之后又手动开始了新的一次循环，旧终态进入 prev
        self.b.request_start(self.params('member', rounds=1), self.board_b)
        self.assertEqual(self.board_b.read_peer() is None, False)
        peer = self.board_a.read_peer()
        self.assertEqual(peer['prev']['id'], old_id)
        self.assertEqual(peer['prev']['state'], COMPLETED)
        self.a.tick()                                                # A 晚读：在 prev 里找到旧编号的完成
        self.assertEqual(self.a.state, COMPLETED)

    def test_completed_peer_that_exited_is_not_treated_as_a_loss(self):
        self.start_both(rounds=1)
        self.run_orochi_step()
        self.go_both()
        self.finish_step(self.b, 'RealmRaid', delay_success=None)
        self.finish_step(self.a, 'RealmRaid', delay_success=None)
        self.assertEqual(self.a.state, COMPLETED)
        # B 的进程退出、文件过期，之后才读的一方仍然按完成处理
        self.clock.advance(hours=3)
        self.b.tick()
        self.assertEqual(self.b.state, COMPLETED)

    def test_ordinary_scheduling_resumes_after_completion_without_new_loop(self):
        self.start_both(rounds=1)
        self.run_orochi_step()
        self.go_both()
        self.finish_step(self.a, 'RealmRaid', delay_success=None)
        self.finish_step(self.b, 'RealmRaid', delay_success=None)
        self.a.tick()
        self.assertFalse(self.a.live)
        self.assertFalse(self.a.is_step('Orochi'))
        self.assertIsNone(self.a.current_step())


class SingleSideCatchUpTest(LoopTestBase):
    def test_member_that_was_away_skips_a_batch_the_leader_already_finished(self):
        self.start_both(rounds=1)
        self.assertEqual(self.a.barrier(), 'wait')                   # 队长先就绪，等队员
        self.assertEqual(self.b.barrier(), 'go')
        self.assertEqual(self.a.barrier(), 'go')
        self.a.begin_run()
        self.leader_batch()
        self.finish_step(self.a, 'Orochi')
        self.assertEqual(self.a.loop['done_idx'], 0)
        # 队员这边一直没跑成（比如在恢复游戏），之后只补自己没完成的：看到队长已完成这批就直接推进
        self.assertEqual(self.b.barrier(), 'skip')
        self.b.accept_skip()
        self.assertEqual(self.b.loop['done_idx'], 0)
        self.assertEqual(self.b.counts.get(0, 0), 0)                 # 没有重复战斗

    def test_peer_that_already_finished_a_raid_is_not_asked_to_repeat_it(self):
        self.start_both(rounds=1)
        self.go_both()
        self.a.begin_run()
        self.b.begin_run()
        self.leader_batch()
        self.b.member_batch_state()
        self.finish_step(self.a, 'Orochi')
        self.finish_step(self.b, 'Orochi')
        self.a.barrier()
        self.b.barrier()
        self.a.begin_run()
        self.finish_step(self.a, 'RealmRaid', delay_success=None)    # A 的个人突破先完成
        self.assertEqual(self.b.barrier(), 'go')                     # B 补跑自己的，不需要 A 再来一次
        self.assertEqual(self.a.loop['done_idx'], 1)


class TrustedCountTest(LoopTestBase):
    def setUp(self):
        super().setUp()
        self.start_both(rounds=1, tmin=3, tmax=3)
        self.go_both()
        self.a.begin_run()

    def test_counts_only_after_battle_and_settlement(self):
        self.a.attempt_begin()
        self.assertEqual(self.a.counts.get(0, 0), 0)                 # 邀请前只是「可能开战」
        self.a.battle_settled(True)
        self.assertEqual(self.a.counts[0], 1)
        self.assertEqual(self.a.remaining(), 2)

    def test_invite_without_clicking_fire_is_revocable(self):
        self.a.attempt_begin()
        self.a.attempt_cancelled(fire_clicked=False)
        self.assertEqual(self.a.state, ACTIVE)
        self.assertFalse(self.a.attempt_possible)
        self.assertEqual(self.a.counts.get(0, 0), 0)

    def test_failed_invite_after_clicking_fire_cannot_be_confirmed(self):
        self.a.attempt_begin()
        self.a.attempt_cancelled(fire_clicked=True)
        self.assertEqual(self.a.state, FAILED)
        self.assertEqual(self.a.loop['reason'], 'count_uncertain')

    def test_battle_without_a_settlement_page_stops_the_loop(self):
        self.a.attempt_begin()
        self.a.battle_settled(False)
        self.assertEqual(self.a.state, FAILED)

    def test_recovery_with_a_possible_battle_stops_instead_of_guessing(self):
        self.a.attempt_begin()                                       # 战斗中游戏卡死 → 恢复后同一步重来
        self.a.note_recovery(True)
        self.finish_step(self.a, 'Orochi', ended=False, delay_success=None)
        self.a.after_run('Restart', ended=True, delay_success=None, restart_status='recovered')
        self.assertFalse(self.a.begin_run())
        self.assertEqual(self.a.loop['reason'], 'count_uncertain')

    def test_batch_is_not_ok_when_target_not_reached(self):
        for _ in range(2):
            self.a.attempt_begin()
            self.a.battle_settled(True)
        self.a.report_batch(True)
        self.assertFalse(self.a.loop['batch']['ok'])
        self.assertIsNone(self.a.completed_idx)

    def test_batch_is_not_ok_when_invite_failed(self):
        for _ in range(3):
            self.a.attempt_begin()
            self.a.battle_settled(True)
        self.a.report_batch(False)
        self.assertFalse(self.a.loop['batch']['ok'])


class RecoveryTest(LoopTestBase):
    def setUp(self):
        super().setUp()
        self.start_both(rounds=2)

    def into_raid(self):
        self.go_both()
        for ctrl in (self.a, self.b):
            ctrl.begin_run()
        self.leader_batch()
        self.b.member_batch_state()
        self.finish_step(self.a, 'Orochi')
        self.finish_step(self.b, 'Orochi')
        self.go_both()
        self.a.begin_run()

    def test_completion_then_restart_keeps_the_fact_but_waits_for_recovery(self):
        self.into_raid()
        self.a.note_recovery(True)
        self.finish_step(self.a, 'RealmRaid', delay_success=None)    # 完成了，随后异常触发 Restart
        self.assertEqual(self.a.loop['done_idx'], 0)                 # 恢复结束前不推进
        self.assertEqual(self.a.completed_idx, 1)
        self.a.after_run('Restart', ended=True, delay_success=None, restart_status='server_update_delayed')
        self.assertEqual(self.a.loop['done_idx'], 0)                 # 游戏恢复未完成
        self.a.after_run('Restart', ended=True, delay_success=None, restart_status='recovered')
        self.assertEqual(self.a.loop['done_idx'], 1)                 # 凭保留的完成事实推进，不重跑
        self.assertEqual(self.a.idx, 2)

    def test_restart_before_completion_reruns_the_step(self):
        self.into_raid()
        self.a.note_recovery(True)
        self.finish_step(self.a, 'RealmRaid', ended=False, delay_success=None)
        self.a.after_run('Restart', ended=True, delay_success=None, restart_status='recovered')
        self.assertEqual(self.a.loop['done_idx'], 0)
        self.assertEqual(self.a.idx, 1)                              # 恢复只代表游戏恢复，步骤仍待补跑

    def test_unknown_step_result_stops_the_loop(self):
        self.into_raid()
        self.finish_step(self.a, 'RealmRaid', ended=False, delay_success=None)
        self.assertEqual(self.a.state, FAILED)
        self.assertEqual(self.a.loop['reason'], 'unknown_result')

    def test_step_retry_limit(self):
        self.go_both()
        self.a.begin_run()
        for _ in range(lc.MAX_STEP_RETRIES + 1):
            self.finish_step(self.a, 'Orochi', ended=True)
            self.a.barrier()
            self.a.in_step = True
        self.assertEqual(self.a.state, FAILED)
        self.assertEqual(self.a.loop['reason'], 'step_retry_exceeded')

    def test_restart_disabled_cannot_recover_so_loop_stops(self):
        self.into_raid()
        self.a.note_recovery(False)
        self.assertEqual(self.a.state, FAILED)
        self.assertEqual(self.a.loop['reason'], 'restart_disabled')


class InsertedTaskTest(LoopTestBase):
    def setUp(self):
        super().setUp()
        self.start_both(rounds=1)

    def run_inserted(self, command, **kwargs):
        self.a.in_step = False
        self.a.after_run(command, **kwargs)

    def test_two_failed_tasks_block_until_each_recovers(self):
        self.run_inserted('KekkaiUtilize', ended=True, delay_success=False)     # X 先失败
        self.assertEqual(self.a.unrecovered, {'KekkaiUtilize'})
        self.assertFalse(self.a.is_step('Orochi'))
        self.a.note_recovery(True)
        self.run_inserted('DailyTrifles', ended=False, delay_success=None)       # Y 抛异常并触发 Restart
        self.assertEqual(self.a.unrecovered, {'KekkaiUtilize', 'DailyTrifles'})
        self.assertTrue(self.a.recovery_pending)
        self.run_inserted('Restart', ended=True, delay_success=None, restart_status='recovered')
        self.assertFalse(self.a.recovery_pending)
        self.run_inserted('DailyTrifles', ended=True, delay_success=True)        # Y 先恢复：只清除自己
        self.assertEqual(self.a.unrecovered, {'KekkaiUtilize'})
        self.assertFalse(self.a.is_step('Orochi'))                               # X 还没恢复，不能继续
        self.run_inserted('KekkaiUtilize', ended=True, delay_success=True)
        self.assertEqual(self.a.unrecovered, set())
        self.assertTrue(self.a.is_step('Orochi'))                                # 都恢复了：重新走疲劳和会合

    def test_rescheduling_into_the_future_is_not_a_success(self):
        self.run_inserted('KekkaiUtilize', ended=True, delay_success=None)
        self.assertEqual(self.a.state, FAILED)
        self.assertIn('unknown_task_result', self.a.loop['reason'])

    def test_inserted_task_completion_then_exception_waits_for_recovery(self):
        self.a.note_recovery(True)
        self.run_inserted('DailyTrifles', ended=False, delay_success=True)       # 已报告成功，随后异常
        self.assertEqual(self.a.unrecovered, set())
        self.assertFalse(self.a.is_step('Orochi'))                               # 恢复结束前仍然不继续
        self.run_inserted('Restart', ended=True, delay_success=None, restart_status='recovered')
        self.assertTrue(self.a.is_step('Orochi'))


class CancelTest(LoopTestBase):
    def setUp(self):
        super().setUp()
        self.start_both()

    def command(self, **override):
        command = {'command': 'loop_cancel', 'boot_id': self.board_a.boot_id, 'loop_id': self.a.loop['id'],
                   'reason': 'ui_stop'}
        command.update(override)
        return command

    def test_cancel_writes_terminal_state_and_peer_mirrors_it(self):
        self.assertTrue(self.a.cancel_by_command(self.command()))
        self.assertEqual(self.board_a.read_peer() is None, False)
        self.assertEqual(self.board_b.read_peer()['loop']['state'], CANCELLED)
        self.b.tick()
        self.assertEqual(self.b.state, CANCELLED)

    def test_stale_cancel_for_an_old_process_or_loop_is_ignored(self):
        self.assertFalse(self.a.cancel_by_command(self.command(boot_id='old-process')))
        self.assertFalse(self.a.cancel_by_command(self.command(loop_id='old-loop')))
        self.assertEqual(self.a.state, ACTIVE)

    def test_terminal_state_is_never_reverted_by_late_progress(self):
        self.a.cancel_by_command(self.command())
        self.go_both()
        self.a.attempt_begin()
        self.a.battle_settled(True)
        self.a.report_batch(True)
        self.a.after_run('Orochi', ended=True, delay_success=True)
        self.a.tick()
        self.assertEqual(self.a.state, CANCELLED)
        self.assertEqual(self.board_b.read_peer()['loop']['state'], CANCELLED)

    def test_a_second_terminal_event_never_overwrites_the_first(self):
        self.a.cancel_by_command(self.command())
        self.a.fail('process_exit')                       # 取消之后进程退出前的失败标记
        self.assertEqual(self.a.state, CANCELLED)
        self.assertEqual(self.a.loop['reason'], 'ui_stop')
        self.assertEqual(self.board_b.read_peer()['loop']['reason'], 'ui_stop')

    def test_cancel_after_a_new_loop_started_does_not_touch_the_new_loop(self):
        old = self.command()
        self.a.cancel_by_command(old)
        self.a.request_start(self.params('leader'), self.board_a)
        self.assertEqual(self.a.state, FORMING)
        self.assertFalse(self.a.cancel_by_command(old))
        self.assertEqual(self.a.state, FORMING)

    def test_cancel_and_heartbeat_interleaving_never_loses_the_terminal_state(self):
        stop = threading.Event()

        def beat():
            while not stop.is_set():
                self.board_a.heartbeat()

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        try:
            for _ in range(20):
                self.a.cancel_by_command(self.command())
                self.board_a.heartbeat()
        finally:
            stop.set()
            thread.join(timeout=5)
        self.assertEqual(self.board_b.read_peer()['loop']['state'], CANCELLED)


class StopNoticeTest(LoopTestBase):
    """父进程一侧：只读确认，不替脚本进程写文件。"""

    def setUp(self):
        super().setUp()
        self.start_both()
        self.root = self.tmp

    def test_command_needs_matching_pid_and_a_live_loop(self):
        command = lc.build_cancel_command(self.root, 'A', self.board_a.pid)
        self.assertEqual(command['boot_id'], self.board_a.boot_id)
        self.assertEqual(command['loop_id'], self.a.loop['id'])
        self.assertIsNone(lc.build_cancel_command(self.root, 'A', self.board_a.pid + 1))
        self.assertIsNone(lc.build_cancel_command(self.root, 'missing', 1))
        self.a.fail('x')
        self.assertIsNone(lc.build_cancel_command(self.root, 'A', self.board_a.pid))

    def test_ack_requires_the_same_boot_loop_and_cancelled_state(self):
        command = lc.build_cancel_command(self.root, 'A', self.board_a.pid)
        self.assertFalse(lc.cancel_acknowledged(self.root, 'A', command))
        self.a.cancel_by_command(command)
        self.assertTrue(lc.cancel_acknowledged(self.root, 'A', command))
        self.assertFalse(lc.cancel_acknowledged(self.root, 'A', dict(command, loop_id='other')))

    def test_notify_acked_timeout_and_none(self):
        import asyncio

        async def run(queue):
            return await lc.notify_cancel(self.root, 'A', self.board_a.pid, queue, sleep=asyncio.sleep,
                                          timeout=0.6, poll=0.05)

        class ChildQueue:
            """放进命令就等于子进程的命令线程收到了。"""
            def __init__(inner, handler):
                inner.handler = handler

            def put(inner, command):
                inner.handler(command)

        self.assertEqual(asyncio.run(run(ChildQueue(self.a.cancel_by_command))), 'acked')
        self.assertEqual(asyncio.run(run(ChildQueue(lambda command: None))), 'none')    # 已是终态：没有活动循环

    def test_notify_timeout_when_child_does_not_react(self):
        import asyncio
        queue = SimpleNamespace(put=lambda command: None)
        result = asyncio.run(lc.notify_cancel(self.root, 'A', self.board_a.pid, queue, sleep=asyncio.sleep,
                                              timeout=0.3, poll=0.05))
        self.assertEqual(result, 'timeout')


class DecideLoopDoorTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 12, 0, 0)

    def me(self, loop=None):
        return {'instance': 'A', 'task': 'Orochi', 'role': 'leader', 'token': 'ta', 'since': self.now,
                'team_tasks': {'Orochi': {'role': 'leader', 'enable': True, 'next_run': self.now}},
                'started_at': None, 'loop': loop}

    def peer(self, loop=None, state=WAITING, token='tb', partner=None):
        return {'instance': 'B', 'peer': 'A', 'state': state, 'task': 'Orochi', 'role': 'member', 'token': token,
                'partner_token': partner, 'since': self.now, 'until': None, 'rest_until': None, 'progress': None,
                'updated_at': self.now, 'loop': loop, 'prev': None,
                'team_tasks': {'Orochi': {'role': 'member', 'enable': True, 'next_run': self.now}}}

    def test_ordinary_orochi_never_meets_a_peer_that_is_in_a_loop(self):
        loop = {'id': 'L', 'state': 'ACTIVE', 'step_task': 'Orochi', 'idx': 0}
        # 对方在同一任务门口等：以前会 met，现在普通御魂被推迟
        result = decide(self.me(), self.peer(loop), self.now)
        self.assertEqual((result.action, result.reason), (POSTPONE, 'peer_in_loop'))
        # 对方已经在跑同一任务且搭档就是我：以前直接 GO，现在同样不行
        running = self.peer(loop, state='running', partner='ta')
        result = decide(self.me(), running, self.now)
        self.assertEqual((result.action, result.reason), (POSTPONE, 'peer_in_loop'))

    def test_loop_step_meets_only_the_same_loop_and_step(self):
        loop = {'id': 'L', 'state': 'ACTIVE', 'step_task': 'Orochi', 'idx': 2}
        ok = decide(self.me({'id': 'L', 'step': 2}), self.peer(loop), self.now)
        self.assertEqual((ok.action, ok.reason), (GO, 'met'))
        for mine in ({'id': 'L', 'step': 0}, {'id': 'other', 'step': 2}):
            result = decide(self.me(mine), self.peer(loop), self.now)
            self.assertEqual((result.action, result.reason), (WAIT, 'peer_loop_pending'))
        result = decide(self.me({'id': 'L', 'step': 2}), self.peer(None), self.now)
        self.assertEqual((result.action, result.reason), (WAIT, 'peer_loop_pending'))

    def test_loop_step_covers_the_early_go_path_of_a_running_peer(self):
        loop = {'id': 'L', 'state': 'ACTIVE', 'step_task': 'Orochi', 'idx': 2}
        running = self.peer(loop, state='running', partner='ta')
        self.assertEqual(decide(self.me({'id': 'L', 'step': 2}), running, self.now).reason, 'peer_started_with_me')
        stale_loop = dict(loop, id='old')
        result = decide(self.me({'id': 'L', 'step': 2}), self.peer(stale_loop, state='running', partner='ta'), self.now)
        self.assertEqual(result.action, WAIT)

    def test_terminal_loop_of_the_peer_does_not_block_ordinary_orochi(self):
        loop = {'id': 'L', 'state': 'COMPLETED', 'step_task': 'Orochi', 'idx': 1}
        self.assertEqual(decide(self.me(), self.peer(loop), self.now).reason, 'met')

    def test_other_tasks_are_not_affected_by_a_peer_loop(self):
        loop = {'id': 'L', 'state': 'ACTIVE', 'step_task': 'Orochi', 'idx': 0}
        me = self.me()
        me['task'] = 'BondlingFairyland'
        peer = self.peer(loop)
        peer['task'] = 'BondlingFairyland'
        peer['team_tasks'] = {'BondlingFairyland': {'role': 'member', 'enable': True, 'next_run': self.now}}
        me['team_tasks'] = {'BondlingFairyland': {'role': 'leader', 'enable': True, 'next_run': self.now}}
        self.assertEqual(decide(me, peer, self.now).reason, 'met')

    def test_no_loop_anywhere_behaves_as_before(self):
        self.assertEqual(decide(self.me(), self.peer(None), self.now).reason, 'met')


if __name__ == '__main__':
    unittest.main()
