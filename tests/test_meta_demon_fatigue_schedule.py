"""超鬼王疲劳等待：复用真实任务方法，设备和OCR用替身。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import ScriptError, TaskEnd
from tasks.MetaDemon.script_task import ScriptTask
from tasks.MetaDemon.config import MetaDemon


class FatigueScheduleTest(TestCase):
    def setUp(self):
        self.task = ScriptTask.__new__(ScriptTask)
        self.task.conf = MetaDemon()
        self.task.device = SimpleNamespace(image='frame')
        self.task.set_next_run = Mock()
        self.task.finish_task = Mock(side_effect=TaskEnd)
        self.now = datetime(2026, 11, 12, 10, 0, 0)
        self.clock = patch('tasks.MetaDemon.script_task.datetime')
        self.mock_clock = self.clock.start()
        self.mock_clock.now.return_value = self.now
        self.addCleanup(self.clock.stop)

    def test_fatigue_wait_calculation_and_invalid_fallback(self):
        cases = [((100, 0, 100), 41), ((85, 15, 100), 26),
                 ((61, 39, 100), 2), ((0, 0, 0), 100),
                 ((101, -1, 100), 100), ((60, 40, 100), 100)]
        for reading, minutes in cases:
            with self.subTest(reading=reading):
                self.task._schedule_fatigue_recovery(reading)
                self.task.set_next_run.assert_called_with('MetaDemon', target=self.now + timedelta(minutes=minutes))

    def test_full_stops_when_tea_disabled_but_not_before_full_or_when_enabled(self):
        for reading, tea, stopped in [((100, 0, 100), False, True),
                                       ((85, 15, 100), False, False),
                                       ((100, 0, 100), True, False)]:
            with self.subTest(reading=reading, tea=tea):
                self.task.conf.meta_demon_config.auto_tea = tea
                self.task.O_MD_FATIGUE = SimpleNamespace(ocr_digit_counter=Mock(return_value=reading))
                self.task.set_next_run.reset_mock()
                if stopped:
                    with self.assertRaises(TaskEnd):
                        self.task.check_fatigue()
                    self.task.set_next_run.assert_called_once_with('MetaDemon', target=self.now + timedelta(minutes=41))
                else:
                    self.assertTrue(self.task.check_fatigue())
                    self.task.set_next_run.assert_not_called()

    def test_tea_popup_closes_then_reads_fresh_frame_or_falls_back(self):
        for result, expected in [((85, 15, 100), 26), (ScriptError('OCR不可用'), 100)]:
            with self.subTest(result=result):
                events = []
                self.task.conf.meta_demon_config.auto_tea = False
                self.task.screenshot = Mock(side_effect=lambda: events.append('截图'))
                self.task.is_in_battle = Mock(return_value=False)
                self.task._meta_battle_started = Mock(return_value=False)
                self.task.appear = Mock(return_value=True)
                self.task.ui_click_until_disappear = Mock(side_effect=lambda *a, **k: events.append('关闭'))
                def read(_):
                    events.append('识别')
                    if isinstance(result, Exception):
                        raise result
                    return result
                self.task.O_MD_FATIGUE = SimpleNamespace(ocr_digit_counter=read)
                with self.assertRaises(TaskEnd):
                    self.task.start_battle()
                self.assertEqual(events, ['截图', '关闭', '截图', '识别'])
                self.task.set_next_run.assert_called_with('MetaDemon', target=self.now + timedelta(minutes=expected))
