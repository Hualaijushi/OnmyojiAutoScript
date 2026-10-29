# This Python file uses the following encoding: utf-8
"""御魂在「御魂 → 个人突破」循环里的行为：可信计数、队员跟随队长、角色校验、普通模式不变。

只替换截图 / 识别 / 邀请 / 战斗这些外部边界，驱动真实的 `_leader_fight_once` / `run_leader` /
`_member_count_reached` / `run` 和 `GeneralInvite.click_fire`。离线通过不等于真机通过。
"""

import shutil
import tempfile
import unittest
from datetime import datetime, time, timedelta
from random import Random
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from module.instance_sync.team import PresenceBoard
from module.script import loop_controller as lc
from module.script.loop_controller import LoopController, LoopParams, set_controller
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Orochi import script_task as orochi
from tasks.Orochi.config import UserStatus
from tasks.Orochi.script_task import ScriptTask


class _Clock:
    now = datetime(2026, 10, 24, 12, 0, 0)

    def __call__(self):
        return self.now


class LoopFixture(unittest.TestCase):
    """一对真实的控制器（A 队长 / B 队员）已经 ACTIVE，且 A 的御魂步骤已经开始。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_orochi_loop_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        patch.object(orochi, 'logger').start()
        self.addCleanup(patch.stopall)
        clock = _Clock()
        self.board_a = PresenceBoard(self.tmp, 'A', 'B', clock=clock)
        self.board_b = PresenceBoard(self.tmp, 'B', 'A', clock=clock)
        self.a = LoopController('oas_a', rng=Random(1))
        self.b = LoopController('oas_b', rng=Random(2))
        self.a.bind_board(self.board_a)
        self.b.bind_board(self.board_b)
        self.a.request_start(LoopParams('leader', 1, 3, 3), self.board_a)
        self.b.request_start(LoopParams('member', 1, 3, 3), self.board_b)
        for _ in range(3):
            self.b.tick()
            self.a.tick()
        for _ in range(3):
            self.a.barrier()
            self.b.barrier()
        self.a.begin_run()
        self.b.begin_run()
        set_controller('oas_a', self.a)
        set_controller('oas_b', self.b)

    def task(self, ctrl, status=UserStatus.LEADER, name='oas_a'):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(
            config_name=name,
            orochi=SimpleNamespace(
                orochi_config=SimpleNamespace(user_status=status, layer='十一层', limit_count=100,
                                              limit_time=time(hour=1), soul_buff_enable=False,
                                              check_true_orochi_enable=False),
                invite_config=SimpleNamespace(wait_time=time(minute=2), default_invite=False),
                general_battle_config=GeneralBattleConfig(continuous_battle=True, max_continuous=5),
                fire_reaction=None))
        task.loop = ctrl
        task.current_count = 0
        task._orochi_battle_key = lambda: 'orochi_test'
        task._team_report = Mock()
        return task


class LeaderTrustedCountTest(LoopFixture):
    """可信计数：驱动真实的 Orochi 处理器（_handle_prepare / _handle_in_battle / _handle_result / _handle_reward）
    和真实的 _leader_fight_once / run_leader；只替换基类里依赖截图识别的部分。"""

    def setUp(self):
        super().setUp()
        for name in ('_handle_prepare', '_handle_in_battle', '_handle_result', '_handle_reward'):
            patch.object(GeneralBattle, name, return_value=BattleAction.CONTINUE).start()

    def drive(self, task, *, click=True, prepare=True, battle=True, results=1, invited=True, residual_first=0):
        """让 run_invite / run_general_battle 按证据顺序调用真实处理器。"""
        context, config = SimpleNamespace(), GeneralBattleConfig()
        task.appear_then_click = Mock(return_value=False)
        task.check_and_invite = Mock(return_value=False)

        def invite(**kwargs):
            task.fire_click_issued = click
            return invited

        def run_battle(**kwargs):
            for _ in range(residual_first):                  # 进入战斗流程时先看到的是上一场残留的结算页
                task._handle_result(context, config)
                task._handle_reward(context, config)
            if prepare:
                task._handle_prepare(context, config)
            if battle:
                task._handle_in_battle(context, config)
            for _ in range(results):                         # 结算 / 奖励页会连续出现很多帧
                task._handle_result(context, config)
                task._handle_reward(context, config)
            return True

        task.run_invite = Mock(side_effect=invite)
        task.run_general_battle = Mock(side_effect=run_battle)

    def test_battle_then_settlement_counts_exactly_once_even_with_repeated_frames(self):
        task = self.task(self.a)
        self.drive(task, results=5)
        self.assertTrue(task._leader_fight_once(is_first=True))
        self.assertEqual(self.a.counts[0], 1)
        self.assertFalse(self.a.attempt_possible)
        self.assertEqual(self.a.state, 'ACTIVE')

    def test_settlement_page_alone_is_residual_and_is_not_counted(self):
        # 上一场留下的结算页：没点挑战、没见到准备 / 战斗页，只有结算页——不计数，也不算失败
        task = self.task(self.a)
        self.drive(task, click=False, prepare=False, battle=False, results=3)
        self.assertTrue(task._leader_fight_once(is_first=False))
        self.assertEqual(self.a.counts.get(0, 0), 0)
        self.assertEqual(self.a.state, 'ACTIVE')
        self.assertFalse(self.a.attempt_possible)

    def test_residual_result_never_becomes_evidence_for_the_next_attempt(self):
        task = self.task(self.a)
        self.drive(task, click=False, prepare=False, battle=False, results=2)
        task._leader_fight_once(is_first=False)
        self.drive(task, results=1)                              # 下一次是真正的战斗
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.counts[0], 1)

    def test_residual_result_frames_before_the_new_battle_are_not_the_settlement_of_this_battle(self):
        # 先是残留的结算页，之后才是新战斗的准备 / 战斗页，而新战斗的结算没有被观察到：不能拿残留的结算当证据
        task = self.task(self.a)
        self.drive(task, residual_first=3, results=0)
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.state, 'FAILED')
        self.assertEqual(self.a.counts.get(0, 0), 0)

    def test_residual_result_frames_then_a_fully_observed_battle_count_once(self):
        task = self.task(self.a)
        self.drive(task, residual_first=3, results=2)
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.state, 'ACTIVE')
        self.assertEqual(self.a.counts[0], 1)

    def test_clicked_but_no_battle_page_was_seen_stops_the_loop(self):
        task = self.task(self.a)
        self.drive(task, prepare=False, battle=False)
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.state, 'FAILED')
        self.assertEqual(self.a.loop['reason'], 'count_uncertain')

    def test_battle_seen_without_any_settlement_stops_the_loop(self):
        task = self.task(self.a)
        self.drive(task, results=0)
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.state, 'FAILED')
        self.assertEqual(self.a.counts.get(0, 0), 0)

    def test_battle_pages_without_our_click_cannot_be_confirmed(self):
        task = self.task(self.a)
        self.drive(task, click=False)
        task._leader_fight_once(is_first=False)
        self.assertEqual(self.a.state, 'FAILED')

    def test_invite_failed_without_clicking_fire_leaves_the_count_alone(self):
        task = self.task(self.a)
        self.drive(task, click=False, invited=False)
        self.assertFalse(task._leader_fight_once(is_first=False))
        task.run_general_battle.assert_not_called()
        self.assertEqual(self.a.counts.get(0, 0), 0)
        self.assertEqual(self.a.state, 'ACTIVE')

    def test_invite_failed_after_clicking_fire_stops_the_loop(self):
        task = self.task(self.a)
        self.drive(task, click=True, invited=False)
        self.assertFalse(task._leader_fight_once(is_first=False))
        self.assertEqual(self.a.state, 'FAILED')
        self.assertEqual(self.a.loop['reason'], 'count_uncertain')

    def test_flags_are_reset_for_every_attempt(self):
        task = self.task(self.a)
        task.fire_click_issued = True
        task._battle_seen = True
        task._result_seen = True
        self.drive(task, click=False, prepare=False, battle=False, results=0, invited=False)
        task._leader_fight_once(is_first=False)                  # 上一次的证据不能带到这一次
        self.assertEqual(self.a.state, 'ACTIVE')
        self.assertFalse(task._battle_seen or task._result_seen)

    def test_internal_continuous_battle_is_switched_off_only_in_the_loop(self):
        task = self.task(self.a)
        battle_config = task._battle_config()
        self.assertFalse(battle_config.continuous_battle)
        self.assertTrue(task.config.orochi.general_battle_config.continuous_battle)   # 用户配置不动
        plain = self.task(None)
        self.assertTrue(plain._battle_config().continuous_battle)                      # 普通模式不变

    def leader_task(self):
        task = self.task(self.a)
        task.limit_count = 1 << 30
        task.limit_time = timedelta(days=3650)
        task.start_time = datetime.now()
        for name in ('goto_page', 'check_layer', 'check_lock', 'screenshot', 'create_room', 'ensure_private',
                     'create_ensure'):
            setattr(task, name, Mock())
        task.appear = Mock(return_value=True)                    # 立刻认为已经创建好队伍
        task.is_in_room = Mock(return_value=True)
        task.exit_room = Mock(return_value=False)
        task.exit_team = Mock(return_value=False)
        return task

    def test_run_leader_stops_exactly_at_the_target_and_reports_the_batch(self):
        task = self.leader_task()
        self.drive(task)
        with patch.object(orochi, 'sleep'):
            self.assertTrue(task.run_leader())
        self.assertEqual(task.run_general_battle.call_count, 3)       # 目标 3 场，不多不少
        self.assertEqual(self.a.counts[0], 3)
        batch = self.a.loop['batch']
        self.assertTrue(batch['done'] and batch['ok'])
        task._team_report.assert_any_call(done=True)

    def test_run_leader_does_not_start_another_battle_after_cancel(self):
        task = self.leader_task()
        self.drive(task)
        inner = task.run_general_battle.side_effect

        def battle(**kwargs):
            result = inner(**kwargs)
            self.a.cancel_by_command({'boot_id': self.board_a.boot_id, 'loop_id': self.a.loop['id']})
            return result

        task.run_general_battle = Mock(side_effect=battle)
        task.run_leader()
        self.assertEqual(task.run_general_battle.call_count, 1)      # 当前这场打完，之后不开下一场
        self.assertEqual(task.run_invite.call_count, 1)
        self.assertEqual(self.a.state, 'CANCELLED')

    def test_cancel_during_the_long_invite_wait_prevents_the_fire_click(self):
        # 外层检查之后 run_invite 等了很久，期间被取消：真正点挑战之前再确认，不点
        task = self.task(self.a)
        self.assertTrue(task._may_fire())
        self.a.cancel_by_command({'boot_id': self.board_a.boot_id, 'loop_id': self.a.loop['id']})
        self.assertFalse(task._may_fire())
        self.assertTrue(self.task(None)._may_fire())                 # 普通运行不受影响


class MemberFollowsLeaderTest(LoopFixture):
    def test_member_leaves_only_when_the_leader_reports_the_batch_done(self):
        task = self.task(self.b, UserStatus.MEMBER, 'oas_b')
        self.assertFalse(task._member_count_reached())
        for _ in range(3):
            self.a.attempt_begin()
            self.a.battle_settled(True)
        self.assertFalse(task._member_count_reached())                # 次数到了但队长还没上报
        self.a.report_batch(True)
        self.assertTrue(task._member_count_reached())
        self.assertEqual(self.b.completed_idx, 0)

    def test_member_does_not_use_its_own_count(self):
        task = self.task(self.b, UserStatus.MEMBER, 'oas_b')
        task.current_count = 10 ** 6
        task.limit_count = 1
        self.assertFalse(task._member_count_reached())

    def test_member_stops_when_the_loop_is_cancelled(self):
        task = self.task(self.b, UserStatus.MEMBER, 'oas_b')
        self.a.cancel_by_command({'boot_id': self.board_a.boot_id, 'loop_id': self.a.loop['id']})
        self.assertTrue(task._member_count_reached())

    def test_plain_member_behaviour_is_unchanged_without_a_loop(self):
        task = self.task(None, UserStatus.MEMBER, 'oas_b')
        task.team_session = None
        task.current_count = 5
        task.limit_count = 5
        self.assertTrue(task._member_count_reached())


class RunEntryTest(LoopFixture):
    def make_run(self, ctrl, status, name):
        task = self.task(None, status, name)
        task.config.orochi.switch_soul = SimpleNamespace(enable=False, enable_switch_by_name=False,
                                                         auto_switch_soul=False)
        task.switch_orochi_souls = Mock()
        task.is_in_battle = Mock(return_value=True)
        task.run_leader = Mock(return_value=True)
        task.run_member = Mock(return_value=True)
        task.run_alone = Mock()
        task.goto_page = Mock()
        task.set_next_run = Mock()
        task.screenshot = Mock()
        task.start_time = datetime.now()
        return task

    def test_loop_replaces_the_ordinary_count_and_time_limits(self):
        task = self.make_run(self.a, UserStatus.LEADER, 'oas_a')
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertGreater(task.limit_count, 10 ** 6)
        self.assertGreater(task.limit_time, timedelta(days=365))
        self.assertIs(task.loop, self.a)
        task.run_leader.assert_called_once()

    def test_role_changed_during_the_loop_stops_it_instead_of_running_ordinary_orochi(self):
        task = self.make_run(self.a, UserStatus.ALONE, 'oas_a')
        with self.assertRaises(TaskEnd):
            task.run()
        task.run_alone.assert_not_called()
        self.assertEqual(self.a.state, 'FAILED')
        self.assertEqual(self.a.loop['reason'], 'role_changed')

    def test_ordinary_run_without_a_loop_keeps_its_limits(self):
        task = self.make_run(None, UserStatus.LEADER, 'plain')
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertIsNone(task.loop)
        self.assertEqual(task.limit_count, 100)
        self.assertEqual(task.limit_time, timedelta(hours=1))


class ClickFireFlagTest(unittest.TestCase):
    def make(self, states):
        task = GeneralInvite.__new__(GeneralInvite)
        task.screenshot = Mock()
        seq = iter(states)
        task._classify_room_entry_state = Mock(side_effect=lambda: next(seq))
        task._wait_room_entry_state = Mock(side_effect=lambda *a, **k: next(seq))
        task.appear = Mock(return_value=True)
        task.appear_then_click = Mock(return_value=True)
        return task

    def test_flag_is_set_only_when_the_fire_button_is_actually_clicked(self):
        task = self.make(['retryable', 'retryable', 'battle'])
        self.assertFalse(task.fire_click_issued)
        with patch('tasks.Component.GeneralInvite.general_invite.sleep'):
            self.assertEqual(task.click_fire(), 'battle')
        self.assertTrue(task.fire_click_issued)

    def test_flag_stays_false_when_the_battle_was_already_there(self):
        task = self.make(['battle'])
        self.assertEqual(task.click_fire(), 'battle')
        self.assertFalse(task.fire_click_issued)
        task.appear_then_click.assert_not_called()

    def test_blocked_start_does_not_click_and_leaves_the_flag_alone(self):
        task = self.make(['retryable', 'retryable', 'battle'])
        task._may_fire = Mock(return_value=False)
        with patch('tasks.Component.GeneralInvite.general_invite.sleep'):
            self.assertEqual(task.click_fire(), 'timeout')
        task.appear_then_click.assert_not_called()
        self.assertFalse(task.fire_click_issued)

    def test_invite_wait_stops_without_waiting_for_the_member_when_start_is_blocked(self):
        task = GeneralInvite.__new__(GeneralInvite)
        task.ensure_enter = Mock(return_value=True)
        task.screenshot = Mock()
        task.appear = Mock(return_value=False)
        task._may_fire = Mock(return_value=False)
        task.is_in_room = Mock(side_effect=AssertionError('should have stopped before looking at the room'))
        config = SimpleNamespace(wait_time=time(minute=2))
        self.assertFalse(task.run_invite(config))

    def test_flag_stays_false_when_the_room_is_gone_before_any_click(self):
        task = self.make(['room_failed'])
        self.assertEqual(task.click_fire(), 'room_failed')
        self.assertFalse(task.fire_click_issued)


if __name__ == '__main__':
    unittest.main()
