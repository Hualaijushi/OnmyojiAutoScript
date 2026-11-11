import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import ScriptError
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.EvoZone.config import EvoZone, UserStatus
from tasks.GameUi.default_pages import page_battle, page_reward
from tasks.MultiAccountEvo.script_task import ScriptTask


class MultiAccountEvoSettlementTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.clock = 0.0
        self.frames = []
        self.index = -1
        self.task = object.__new__(ScriptTask)
        self.task._embedded_evo_zone = EvoZone()
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.LEADER
        self.task.current_count = 1
        self.task.limit_count = 20
        self.task.device = SimpleNamespace(image=object())
        self.task._check_embedded_abort = Mock()
        self.task.screenshot = self._screenshot
        self.task.appear = self._appear
        self.task.click = Mock()
        self.task.appear_then_click = Mock(side_effect=self._click_if_visible)
        self.task._multi_account_settlement_click = Mock(return_value='settlement')
        module = 'tasks.MultiAccountEvo.script_task'
        self.stack.enter_context(patch(f'{module}.time.monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch(f'{module}.time.sleep', side_effect=self._sleep))
        self.stack.enter_context(patch(
            f'{module}.GameUi.detect_page_in', side_effect=lambda *args, **kwargs: self.frame.get('page'),
        ))
        self.execute_click = self.stack.enter_context(patch(f'{module}.execute_single_click'))

    @property
    def frame(self):
        return self.frames[min(self.index, len(self.frames) - 1)]

    def _screenshot(self):
        self.index += 1
        self.clock += 0.05

    def _sleep(self, seconds):
        self.clock += seconds

    def _appear(self, marker, **kwargs):
        return any(marker is getattr(self.task, name) for name in self.frame.get('markers', ()))

    def _click_if_visible(self, marker, **kwargs):
        return self._appear(marker)

    def test_loading_longer_than_old_fallback_waits_for_two_fresh_room_frames(self):
        self.frames = [{}] * 12 + [{'markers': ('I_GI_IN_ROOM',)}] * 2
        self.assertEqual('room', self.task._wait_post_battle_state())
        self.assertEqual(13, self.index)
        self.assertGreater(self.clock, 2.5)
        self.task.click.assert_not_called()
        self.task.appear_then_click.assert_not_called()

    def test_one_false_exploration_frame_does_not_destroy_room(self):
        self.frames = [{'markers': ('I_CHECK_EXPLORATION',)}, {},
                       {'markers': ('I_GI_EMOJI_1',)}, {'markers': ('I_GI_EMOJI_1',)}]
        self.assertEqual('room', self.task._wait_post_battle_state())
        self.assertEqual(3, self.index)

    def test_reward_overlay_blocks_background_room_and_exploration(self):
        self.frames = [
            {'page': page_reward, 'markers': ('I_GI_IN_ROOM', 'I_CHECK_EXPLORATION')},
            {'markers': ('I_GI_IN_ROOM',)}, {'markers': ('I_GI_IN_ROOM',)},
        ]
        self.assertEqual('room', self.task._wait_post_battle_state())
        self.task.click.assert_called_once_with('settlement', interval=0.8)
        self.assertEqual(2, self.index)

    def test_reward_between_room_frames_resets_confirmation(self):
        self.frames = [{'markers': ('I_GI_IN_ROOM',)}, {'page': page_reward},
                       {'markers': ('I_GI_IN_ROOM',)}, {'markers': ('I_GI_IN_ROOM',)}]
        self.assertEqual('room', self.task._wait_post_battle_state())
        self.assertEqual(3, self.index)

    def test_invite_confirmation_requires_fresh_room_evidence(self):
        self.frames = [
            {'markers': ('I_GI_SURE', 'I_GI_IN_ROOM')},
            {'markers': ('I_GI_IN_ROOM',)}, {'markers': ('I_GI_IN_ROOM',)},
        ]
        self.assertEqual('room', self.task._wait_post_battle_state())
        self.assertEqual(2, self.index)
        self.task.appear_then_click.assert_any_call(self.task.I_GI_SURE, interval=0.8)

    def test_default_invite_checkbox_and_confirmation_use_separate_frames(self):
        self.task._embedded_evo_zone.invite_config.default_invite = True
        self.frames = [
            {'markers': ('I_GI_SURE', 'I_I_NO_DEFAULT')},
            {'markers': ('I_GI_SURE',)},
            {'markers': ('I_GI_IN_ROOM',)}, {'markers': ('I_GI_IN_ROOM',)},
        ]
        self.assertEqual('room', self.task._wait_post_battle_state())
        accepted = [call.args[0] for call in self.task.appear_then_click.call_args_list
                    if call.args[0] is self.task.I_GI_SURE]
        self.assertEqual([self.task.I_GI_SURE], accepted)
        self.assertEqual(3, self.index)

    def test_reward_handler_invite_step_does_not_enter_an_unbounded_inner_loop(self):
        self.frames = [{'markers': ('I_GI_SURE',)}]
        self.task.screenshot()
        self.task.check_and_invite = Mock(side_effect=AssertionError('unbounded invite'))
        self.assertEqual(BattleAction.CONTINUE, self.task._handle_reward(SimpleNamespace(), object()))
        self.task.check_and_invite.assert_not_called()
        self.task.click.assert_not_called()
        self.assertEqual(0, self.index)

    def test_same_outside_state_on_two_fresh_frames_fails_without_back_click(self):
        for marker, reason in (('I_MATCHING', 'matching'),
                               ('I_CHECK_EXPLORATION', 'exploration'), ('I_CHECK_MAIN', 'main')):
            with self.subTest(reason=reason):
                self.index = -1
                self.frames = [{'markers': (marker,)}] * 2
                with self.assertRaisesRegex(ScriptError, f'room lost: {reason}'):
                    self.task._wait_post_battle_state()
                self.assertEqual(1, self.index)
        self.task.click.assert_not_called()
        self.task.appear_then_click.assert_not_called()

    def test_different_outside_frames_do_not_count_as_stable_failure(self):
        self.frames = [{'markers': ('I_MATCHING',)}, {'markers': ('I_CHECK_EXPLORATION',)},
                       {'markers': ('I_GI_IN_ROOM',)}, {'markers': ('I_GI_IN_ROOM',)}]
        self.assertEqual('room', self.task._wait_post_battle_state())

    def test_persistent_unknown_times_out_without_clicking(self):
        self.task.post_battle_timeout = 1.0
        self.frames = [{}]
        with self.assertRaisesRegex(ScriptError, 'timeout: last_state=unknown'):
            self.task._wait_post_battle_state()
        self.assertLessEqual(self.clock, 1.4)
        self.task.click.assert_not_called()
        self.task.appear_then_click.assert_not_called()

    def test_reappearing_reward_does_not_restart_deadline(self):
        self.task.post_battle_timeout = 1.0
        self.frames = [{}, {'page': page_reward}, {}, {'page': page_reward}]
        with self.assertRaisesRegex(ScriptError, 'confirmation timeout'):
            self.task._wait_post_battle_state()
        self.assertLessEqual(self.clock, 1.4)

    def test_slow_screenshot_cannot_start_a_click_after_deadline(self):
        self.task.post_battle_timeout = 1.0
        self.frames = [{'page': page_reward}]
        self.task.screenshot = lambda: self._sleep(2.0)
        with self.assertRaisesRegex(ScriptError, 'confirmation timeout'):
            self.task._wait_post_battle_state()
        self.task.click.assert_not_called()

    def test_abort_check_preserves_original_failure_and_prevents_clicks(self):
        self.frames = [{'page': page_reward}]
        self.task._check_embedded_abort.side_effect = RuntimeError('peer failed')
        with self.assertRaisesRegex(RuntimeError, 'peer failed'):
            self.task._wait_post_battle_state()
        self.assertEqual(-1, self.index)
        self.task.click.assert_not_called()

    def test_member_can_hand_off_confirmed_next_battle(self):
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.MEMBER
        self.frames = [{'page': page_battle}] * 2
        self.assertEqual('battle', self.task._wait_post_battle_state())
        self.task.click.assert_not_called()

    def test_member_accepts_invitation_at_existing_safe_centre_then_confirms_room(self):
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.MEMBER
        self.frames = [{'markers': ('I_I_ACCEPT',)}, {'markers': ('I_GI_IN_ROOM',)},
                       {'markers': ('I_GI_IN_ROOM',)}]
        self.assertEqual('room', self.task._wait_post_battle_state())
        x, y, width, height = self.task.I_I_ACCEPT.roi_front
        point = self.execute_click.call_args.args[1]
        self.assertEqual((x + width // 2, y + height // 2), (point.x, point.y))

    def test_finished_member_can_confirm_leader_already_closed_room(self):
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.MEMBER
        self.task.current_count = self.task.limit_count
        self.frames = [{'markers': ('I_CHECK_EXPLORATION',)}] * 2
        self.assertEqual('exploration', self.task._wait_post_battle_state())

    def test_unfinished_member_outside_room_returns_to_invite_wait(self):
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.MEMBER
        for marker, state in (('I_CHECK_MAIN', 'main'),
                              ('I_CHECK_EXPLORATION', 'exploration'), ('I_MATCHING', 'matching')):
            with self.subTest(state=state):
                self.index = -1
                self.frames = [{'markers': (marker,)}] * 2
                self.assertEqual(state, self.task._wait_post_battle_state())
                self.assertEqual(1, self.index)
                self.assertLess(self.task.current_count, self.task.limit_count)
        self.task.click.assert_not_called()
        self.task.appear_then_click.assert_not_called()

    def test_courtyard_after_battle_does_not_complete_unfinished_group(self):
        self.frames = [{'markers': ('I_CHECK_MAIN',)}] * 2
        self.task.config = SimpleNamespace(evo_zone=EvoZone())
        # 模拟第一场结束；嵌入式调用仍必须核对整组目标场数。
        def run_one_round():
            self.task.current_count = 1
            return self.task.run_general_battle(config='config')
        self.task._run_core = run_one_round
        self.task._embedded_evo_zone = None
        with patch.object(GeneralBattle, 'run_general_battle', return_value=True):
            self.assertFalse(self.task.run_embedded(user_status=UserStatus.MEMBER, limit_count=20))
        self.assertEqual(1, self.task.current_count)

    def test_member_in_courtyard_keeps_checking_invites_without_exiting(self):
        self.task._embedded_evo_zone.evo_zone_config.user_status = UserStatus.MEMBER
        self.frames = [{'markers': ('I_CHECK_MAIN',)}] * 2
        self.assertEqual('main', self.task._wait_post_battle_state())
        self.task.start_time = datetime.now()
        self.task.limit_time = timedelta(minutes=30)
        self.task.device.stuck_record_add = Mock()
        self.task._check_embedded_abort = Mock(side_effect=[None, RuntimeError('stop after one wait')])
        self.task.check_then_accept = Mock(return_value=False)
        self.task.is_in_battle = Mock(return_value=False)
        self.task.exit_room = Mock()
        with self.assertRaisesRegex(RuntimeError, 'stop after one wait'):
            self.task.run_member()
        self.task.check_then_accept.assert_called_once_with()
        self.task.exit_room.assert_not_called()
        self.assertEqual(1, self.task.current_count)

    def test_confirmation_failure_prevents_battle_result_from_returning_to_caller(self):
        self.frames = [{'markers': ('I_MATCHING',)}] * 2
        with patch.object(GeneralBattle, 'run_general_battle', return_value=True):
            with self.assertRaisesRegex(ScriptError, 'room lost'):
                self.task.run_general_battle(config=object())

    def test_successful_confirmation_preserves_original_battle_result(self):
        self.frames = [{'markers': ('I_GI_IN_ROOM',)}] * 2
        with patch.object(GeneralBattle, 'run_general_battle', return_value=False) as battle:
            self.assertFalse(self.task.run_general_battle(config='config'))
        battle.assert_called_once_with(config='config')

    def test_generic_room_detection_remains_unchanged_and_legacy_lower_marker_is_ignored(self):
        self.frames = [{'markers': ('I_GI_IN_ROOM',)}]
        self.task.screenshot()
        self.assertTrue(self.task.is_in_room(False))
        self.assertFalse(GeneralInvite.is_in_room(self.task, False))
        self.frames = [{'markers': ('I_GI_EMOJI_2',)}]
        self.assertFalse(self.task.is_in_room(False))


if __name__ == '__main__':
    unittest.main()
