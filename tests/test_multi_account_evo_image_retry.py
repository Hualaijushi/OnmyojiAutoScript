"""验证图像暂时超时只重取画面，不重放点击或战斗。"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from zerorpc.exceptions import LostRemote, TimeoutExpired
from tasks.base_task import BaseTask
from tasks.MultiAccountEvo.script_task import ScriptTask
from tasks.MultiAccountEvo.sync import RunChangedError


class ImageReadRetryTest(unittest.TestCase):
    def make_task(self):
        task = object.__new__(ScriptTask)
        task.screenshot = Mock()
        task.click = Mock()
        return task

    def test_batch_retry_uses_new_frame_and_preserves_confirmed_count(self):
        task = self.make_task()
        task.device = SimpleNamespace(image_frame_id='old')
        task.current_count = 104
        frames = []
        def prepare(targets):
            frames.append(task.device.image_frame_id)
            if len(frames) == 1:
                raise TimeoutExpired(10, 'calling remote method match_many')
        task.screenshot.side_effect = lambda: setattr(task.device, 'image_frame_id', 'new')
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=prepare):
            task.prepare_appear_cache(iter([task.I_GI_IN_ROOM]))
        self.assertEqual(['old', 'new'], frames)
        self.assertEqual(104, task.current_count)
        task.click.assert_not_called()

    def test_batch_disconnect_can_recover_without_extra_click(self):
        task = self.make_task()
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=[LostRemote('断开'), None]) as match:
            task.prepare_appear_cache([task.I_GI_IN_ROOM])
        self.assertEqual(2, match.call_count)
        task.screenshot.assert_called_once_with()
        task.click.assert_not_called()

    def test_second_failure_is_not_recursively_retried(self):
        task = self.make_task()
        error = TimeoutExpired(10)
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=error) as match:
            with self.assertRaises(TimeoutExpired):
                task.prepare_appear_cache([])
        self.assertEqual(2, match.call_count)
        task.screenshot.assert_called_once_with()

    def test_per_group_budget_limits_separate_transient_failures(self):
        task = self.make_task()
        error = TimeoutExpired(10)
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=[error, None, error, None, error]) as match:
            task.prepare_appear_cache([])
            task.prepare_appear_cache([])
            with self.assertRaises(TimeoutExpired):
                task.prepare_appear_cache([])
        self.assertEqual(5, match.call_count)
        self.assertEqual(2, task.screenshot.call_count)

    def test_peer_stop_during_new_screenshot_forbids_retry(self):
        task = self.make_task()
        task.screenshot.side_effect = RunChangedError('旧任务停止')
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=TimeoutExpired(10)) as match:
            with self.assertRaises(RunChangedError):
                task.prepare_appear_cache([])
        self.assertEqual(1, match.call_count)

    def test_configuration_and_ocr_errors_do_not_enter_image_retry(self):
        task = self.make_task()
        with patch.object(BaseTask, 'prepare_appear_cache', side_effect=ValueError('配置错误')) as match:
            with self.assertRaises(ValueError):
                task.prepare_appear_cache([])
        self.assertEqual(1, match.call_count)
        with patch.object(BaseTask, 'appear', side_effect=TimeoutExpired(10)) as match:
            with self.assertRaises(TimeoutExpired):
                task.appear(task.O_EVENT_PROGRESS_50)
        self.assertEqual(1, match.call_count)
        task.screenshot.assert_not_called()

    def test_normal_matching_does_not_take_more_screenshots(self):
        task = self.make_task()
        with patch.object(BaseTask, 'prepare_appear_cache', return_value=None) as batch, patch.object(
            BaseTask, 'appear', return_value=True,
        ) as match:
            task.prepare_appear_cache([])
            self.assertTrue(task.appear(task.I_GI_IN_ROOM))
        self.assertEqual(1, batch.call_count)
        self.assertEqual(1, match.call_count)
        task.screenshot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
