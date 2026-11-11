"""奖励袋确认、奖励页关闭顺序及OCR失败现场，全程隔离真实设备/识别。"""
import json
from pathlib import Path
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from tasks.EvoZone.config import EvoZone
from tasks.Component.GeneralBattle.general_battle import BattleAction
from tasks.GameUi.default_pages import page_battle_result
from tasks.MultiAccountEvo.event import EventGoalError
from tasks.MultiAccountEvo.script_task import ScriptTask


class RewardGateTest(unittest.TestCase):
    def task(self):
        task=object.__new__(ScriptTask)
        task.config=SimpleNamespace(config_name='oas3',evo_zone=EvoZone())
        task.device=SimpleNamespace(image=np.zeros((720,1280,3),dtype=np.uint8),click_record_clear=Mock())
        task._event_segment=dict(completed=199,floor=0,remaining=250,start=200,interval=10,
                                 pending=False,reached=False,group=2,epoch=0,role='leader',run_id='run',sync=Mock())
        task._event_sample_token=None
        task.appear=Mock(return_value=False)
        task.appear_then_click=Mock(return_value=False)
        task.click=Mock()
        task.screenshot=Mock()
        return task

    def test_result_page_does_not_read_ticket(self):
        task=self.task()
        with patch.object(task.O_EVENT_PROGRESS_50,'ocr') as ocr:
            task._handle_result(SimpleNamespace(last_page=page_battle_result),None)
        ocr.assert_not_called()

    def test_generic_reward_without_bag_waits_without_ocr_or_click(self):
        task=self.task()
        with patch.object(task.O_EVENT_PROGRESS_50,'ocr') as ocr:
            action=task._handle_reward(SimpleNamespace(last_page=None),None)
        self.assertEqual(BattleAction.CONTINUE,action)
        ocr.assert_not_called()
        task.click.assert_not_called()

    def test_skin_confirm_is_dismissed_before_ticket_read_and_without_extra_click(self):
        task=self.task()
        task.appear_then_click.return_value=True
        task._read_event_sample=Mock()
        task._handle_reward(SimpleNamespace(last_page=None),None)
        task._read_event_sample.assert_not_called()
        task.click.assert_not_called()

    def test_visible_reward_bag_reads_before_screen_is_closed(self):
        task=self.task()
        task.appear.side_effect=lambda marker: marker is task.I_GET_BATTLE_REWARD
        calls=[]
        task.click.side_effect=lambda *a,**kw:calls.append('close')
        with patch.object(task.O_EVENT_PROGRESS_50,'ocr',side_effect=lambda frame:calls.append('ocr') or '49/50'):
            task._handle_reward(SimpleNamespace(last_page=None),None)
        self.assertEqual(['ocr','close'],calls)
        task._event_segment['sync'].record_event_sample.assert_called_once()

    def test_missing_reward_bag_has_bounded_wait(self):
        task=self.task()
        task._save_event_ocr_evidence=Mock()
        with patch('tasks.MultiAccountEvo.script_task.time.monotonic',side_effect=[1,7]):
            self.assertFalse(task._read_event_sample())
            with self.assertRaises(EventGoalError):task._read_event_sample()
        task._save_event_ocr_evidence.assert_called_once()

    def test_bad_ocr_saves_exact_frame_roi_and_readings_without_progress(self):
        task=self.task()
        task.appear.side_effect=lambda marker:marker is task.I_GET_BATTLE_REWARD
        task.device.image[10:34,1128:1232]=137
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.object(task.O_EVENT_PROGRESS_50,'ocr',return_value='invalid'):
                    with self.assertRaises(EventGoalError):task._read_event_sample()
                folder=next((Path(directory)/'log/dailytask/ticket_ocr_debug').iterdir())
                crop=cv2.imread(str(folder/'roi.png'))
                self.assertEqual((24,104,3),crop.shape)
                self.assertTrue(np.all(crop==137))
                self.assertTrue((folder/'frame.png').exists())
                self.assertEqual(['invalid']*3,json.loads((folder/'sample.json').read_text(encoding='utf-8'))['readings'])
            finally:os.chdir(previous)
        task._event_segment['sync'].record_event_sample.assert_not_called()
        task.click.assert_not_called()


if __name__=='__main__':unittest.main()
