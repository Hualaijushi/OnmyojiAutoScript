"""两种喝茶图标共用自动喝茶开关，保留原入战和疲劳处理。"""

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

import cv2
import numpy as np

from module.exception import TaskEnd
from tasks.MetaDemon.assets import MetaDemonAssets
from tasks.MetaDemon.script_task import ScriptTask


class DualTeaPopupTest(TestCase):
    def task(self, button, enabled):
        task = Mock()
        task.I_MD_DRINK_TEA = MetaDemonAssets.I_MD_DRINK_TEA
        task.I_MD_DRINK_FREETEA = MetaDemonAssets.I_MD_DRINK_FREETEA
        task.I_CHECK_BOSS_PAGE = object()
        task.I_MD_CLOSE_POPUP = object()
        task.I_MD_FIRE = object()
        task.conf.meta_demon_config.auto_tea = enabled
        task._meta_battle_started.return_value = False
        task.is_in_battle.return_value = False
        task.appear.side_effect = lambda rule, **kwargs: rule is button or rule is task.I_CHECK_BOSS_PAGE
        task.total_count = 0
        task.finish_task.side_effect = TaskEnd
        return task

    def test_both_buttons_enabled_click_matching_button_then_count_battle_once(self):
        for button in (MetaDemonAssets.I_MD_DRINK_TEA, MetaDemonAssets.I_MD_DRINK_FREETEA):
            for rotation in (False, True):
                with self.subTest(button=button.file, rotation=rotation):
                    task = self.task(button, True)
                    task._meta_battle_started.side_effect = [False, True]
                    entered = Mock()
                    result = ScriptTask.start_battle(task, on_entered=entered, rotation_mode=rotation)
                    self.assertEqual('finished' if rotation else None, result)
                    task.click.assert_called_once_with(button)
                    entered.assert_called_once_with()
                    self.assertEqual(1, task.total_count)
                    task.run_general_battle.assert_called_once()
                    task.appear_then_click.assert_not_called()
                    task._schedule_fatigue_recovery.assert_not_called()

    def test_both_buttons_disabled_ordinary_task_closes_and_schedules(self):
        for button in (MetaDemonAssets.I_MD_DRINK_TEA, MetaDemonAssets.I_MD_DRINK_FREETEA):
            with self.subTest(button=button.file):
                task = self.task(button, False)
                with self.assertRaises(TaskEnd):
                    ScriptTask.start_battle(task)
                task.click.assert_not_called()
                task.ui_click_until_disappear.assert_called_once_with(task.I_MD_CLOSE_POPUP, interval=.6)
                task._schedule_fatigue_recovery.assert_called_once_with()
                self.assertEqual(0, task.total_count)

    def test_both_buttons_disabled_rotation_returns_fatigue_without_ordinary_schedule(self):
        for button in (MetaDemonAssets.I_MD_DRINK_TEA, MetaDemonAssets.I_MD_DRINK_FREETEA):
            with self.subTest(button=button.file):
                task = self.task(button, False)
                self.assertEqual('fatigue', ScriptTask.start_battle(task, rotation_mode=True))
                task.click.assert_not_called()
                task._schedule_fatigue_recovery.assert_not_called()
                task.finish_task.assert_not_called()
                self.assertEqual(0, task.total_count)

    def test_no_tea_keeps_original_fire_and_rental_prompt_path(self):
        task = self.task(None, True)
        task.appear.return_value = False
        task.appear.side_effect = None
        task._meta_battle_started.side_effect = [False, True]
        prompt = Mock(return_value='absent')
        self.assertEqual('finished', ScriptTask.start_battle(task, rotation_mode=True, popup_handler=prompt))
        task.click.assert_not_called()
        prompt.assert_called_once_with()
        task.appear_then_click.assert_called_once_with(task.I_MD_FIRE, interval=.8)

    def test_expired_rotation_deadline_does_not_click_tea(self):
        task = self.task(MetaDemonAssets.I_MD_DRINK_FREETEA, True)
        self.assertEqual('unknown', ScriptTask.start_battle(task, rotation_mode=True, deadline=0))
        task.click.assert_not_called()
        task.screenshot.assert_not_called()

    def test_user_templates_decode_and_match_asset_metadata(self):
        metadata = json.loads(Path('tasks/MetaDemon/md/image.json').read_text(encoding='utf-8'))
        for rule in (MetaDemonAssets.I_MD_DRINK_TEA, MetaDemonAssets.I_MD_DRINK_FREETEA):
            with self.subTest(template=rule.file):
                frame = cv2.imdecode(np.fromfile(rule.file, dtype=np.uint8), cv2.IMREAD_COLOR)
                self.assertIsNotNone(frame)
                height, width = frame.shape[:2]
                self.assertEqual(tuple(rule.roi_front[2:]), (width, height))
                item = next(item for item in metadata if item['imageName'] == Path(rule.file).name)
                self.assertEqual(tuple(rule.roi_front), tuple(map(int, item['roiFront'].split(','))))
                self.assertEqual(tuple(rule.roi_back), tuple(map(int, item['roiBack'].split(','))))
                self.assertEqual(rule.threshold, item['threshold'])
