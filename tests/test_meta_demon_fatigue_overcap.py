"""轮换疲劳超过上限时仍服从喝茶开关，保留无效读数保护。"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.MetaDemon.config import MetaDemonConfig
from tasks.MetaDemonRotation.driver import RotationDriver
from tasks.MetaDemonRotation.engine import run_account
from tasks.MetaDemonRotation.progress import RotationProgress, account_identity


class FatigueOvercapTest(TestCase):
    def task(self, reading, tea):
        task = Mock()
        task.conf.meta_demon_config = MetaDemonConfig(auto_tea=tea, limit_time='00:00:00')
        task.O_MD_FATIGUE.ocr_digit_counter.return_value = reading
        return task

    def test_overcap_and_full_follow_tea_switch(self):
        for reading in ((103, -3, 100), (100, 0, 100)):
            for tea, expected in ((True, 'ready'), (False, 'unavailable')):
                with self.subTest(reading=reading, tea=tea):
                    task = self.task(reading, tea)
                    self.assertEqual(expected, RotationDriver.fatigue_status(task))
                    task.screenshot.assert_called_once()

    def test_below_full_remains_ready(self):
        for tea in (False, True):
            self.assertEqual('ready', RotationDriver.fatigue_status(self.task((99, 1, 100), tea)))

    def test_invalid_readings_remain_unknown(self):
        for reading in ((0, 0, 0), (-1, 101, 100), (103, 0, 100), (50, 49, 100), (1, -1, 0)):
            with self.subTest(reading=reading):
                self.assertEqual('unknown', RotationDriver.fatigue_status(self.task(reading, True)))

    def test_account_time_limit_still_precedes_ocr(self):
        task = self.task((103, -3, 100), True)
        task.conf.meta_demon_config = MetaDemonConfig(auto_tea=True, limit_time='00:00:01')
        task.rotation_started = 0
        with patch('tasks.MetaDemonRotation.driver.time.monotonic', return_value=2):
            self.assertEqual('time_limit', RotationDriver.fatigue_status(task))
        task.screenshot.assert_not_called()

    def test_disabled_overcap_stops_without_entry_or_count_change(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = RotationProgress(Path(directory), 'oas5')
            identity = account_identity('oas5', 11, 'test', 'server', 'role')
            driver = self.task((103, -3, 100), False)
            driver.deploy_rental.return_value = 'ready'
            driver.fatigue_status.side_effect = lambda: RotationDriver.fatigue_status(driver)
            result = run_account(driver, progress, account_id='C11', identity=identity,
                                 rental_team=1, battle_limit=30)
            self.assertEqual(('疲劳不足', 0), (result.reason, result.entered))
            driver.challenge.assert_not_called()
            self.assertEqual('idle', progress.update('C11', identity, 'read', target=30)['phase'])

    def test_enabled_overcap_reaches_challenge_without_adding_tea_count(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = RotationProgress(Path(directory), 'oas5')
            identity = account_identity('oas5', 11, 'test', 'server', 'role')
            driver = self.task((103, -3, 100), True)
            driver.deploy_rental.return_value = 'ready'
            driver.fatigue_status.side_effect = lambda: RotationDriver.fatigue_status(driver)
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: entered() or True
            result = run_account(driver, progress, account_id='C11', identity=identity,
                                 rental_team=1, battle_limit=1)
            self.assertTrue(result.completed)
            self.assertEqual(1, result.entered)
            driver.challenge.assert_called_once()
