import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.EvoZone.config import EvoZone
from tasks.EvoZone.script_task import ScriptTask as EvoTask
from tasks.MultiAccountEvo.script_task import ScriptTask


class MultiAccountEvoFrameReuseTest(unittest.TestCase):
    def make_task(self, cls=ScriptTask):
        task = object.__new__(cls)
        task.config = SimpleNamespace(evo_zone=EvoZone())
        task.current_count = 0
        task.limit_count = 1
        task.start_time = datetime.now()
        task.limit_time = timedelta(minutes=30)
        task.screenshot = Mock()
        task.appear = Mock(return_value=False)
        task._check_embedded_abort = Mock()
        for name in ('goto_page', 'evozone_enter', 'check_layer', 'check_lock',
                     'create_room', 'ensure_private', 'create_ensure', 'exit_room', 'exit_team'):
            setattr(task, name, Mock(return_value=True))
        return task

    def test_leader_reuses_frame_but_captures_again_after_battle(self):
        task = self.make_task()
        task.appear.side_effect = lambda marker, **kw: any(
            marker is item for item in (task.I_CHECK_TEAM, task.I_GI_IN_ROOM))
        task.run_invite = Mock(return_value=True)
        task.run_general_battle = Mock(side_effect=lambda **kw: setattr(task, 'current_count', 1))
        self.assertTrue(task.run_leader())
        # 建房确认一帧、首场循环一帧、战斗后达标检查仍取新帧。
        self.assertEqual(3, task.screenshot.call_count)
        self.assertEqual(2, sum(call.args[0] is task.I_GI_IN_ROOM
                                for call in task.appear.call_args_list))
        task.run_invite.assert_called_once()
        task.run_general_battle.assert_called_once()

    def test_same_frame_negative_room_result_is_shared_by_all_limit_checks(self):
        task = self.make_task()
        task.current_count = 1
        task.limit_time = timedelta(0)
        task.appear.side_effect = lambda marker, **kw: marker is task.I_CHECK_TEAM
        task._check_embedded_abort.side_effect = [None, None, RuntimeError('下一轮')]
        with patch('tasks.EvoZone.script_task.sleep'), self.assertRaisesRegex(RuntimeError, '下一轮'):
            task.run_leader()
        self.assertEqual(2, task.screenshot.call_count)
        for marker in (task.I_GI_IN_ROOM, task.I_GI_EMOJI_1):
            self.assertEqual(1, sum(call.args[0] is marker for call in task.appear.call_args_list))

    def test_normal_evo_leader_keeps_original_screenshot_checks(self):
        task = self.make_task(EvoTask)
        task.appear.side_effect = lambda marker, **kw: any(
            marker is item for item in (task.I_CHECK_TEAM, task.I_GI_EMOJI_1))
        task.run_invite = Mock(return_value=True)
        task.run_general_battle = Mock(side_effect=lambda **kw: setattr(task, 'current_count', 1))
        self.assertTrue(task.run_leader())
        self.assertEqual(5, task.screenshot.call_count)

    def test_invite_loop_refreshes_between_frames_and_keeps_fire_confirmation(self):
        task = self.make_task()
        task.ensure_enter = Mock(return_value=True)
        task.appear.side_effect = lambda marker, **kw: (
            marker is task.I_GI_IN_ROOM and task.screenshot.call_count == 2)
        task.room_check_can_fire = Mock(return_value=True)
        task.click_fire = Mock(return_value='battle')
        self.assertTrue(task.run_invite(task.config.evo_zone.invite_config))
        self.assertEqual(2, task.screenshot.call_count)
        task.room_check_can_fire.assert_called_once()
        task.click_fire.assert_called_once_with(fire_reaction=None)

    def test_explicit_room_checks_still_take_new_screenshots(self):
        task = self.make_task()
        task.appear.return_value = True
        self.assertTrue(task.is_in_room())
        self.assertTrue(task.is_in_room())
        self.assertEqual(2, task.screenshot.call_count)

    def test_snapshot_is_not_reused_across_calls(self):
        task = self.make_task()
        task.appear.side_effect = [True, False, False]
        self.assertTrue(task._room_snapshot_after_screenshot())
        self.assertFalse(task._room_snapshot_after_screenshot())
        task.screenshot.assert_not_called()

    def test_default_tasks_keep_legacy_room_checks(self):
        for cls in (GeneralInvite, EvoTask):
            with self.subTest(cls=cls.__name__):
                task = object.__new__(cls)
                task.is_in_room = Mock(return_value=True)
                self.assertIsNone(task._room_snapshot_after_screenshot())
                task.is_in_room.assert_not_called()


if __name__ == '__main__':
    unittest.main()
