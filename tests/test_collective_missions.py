# This Python file uses the following encoding: utf-8
"""集体任务：只做指定的任务（「远远不够」第一个任务槽），一直换到出现为止，换不到就什么都不捐、1 小时后再试。

以前换 12–15 次没换到、或判定换不动时，会照着最后读到的那个任务去捐（捐到不是指定的材料）。
用 `tests/test_daily_trifles.py` 的假界面；任务名用替身，每点一次「换一个」前进一格；捐材料 / 御魂 / N 卡换成替身。
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from tasks.CollectiveMissions.config import MC, CollectiveMissions
from tasks.CollectiveMissions.script_task import ScriptTask as T
from tests.test_daily_trifles import FakeUi


class FakeSlot:
    """第一个任务槽显示的任务名。cycle=False 时用完停在最后一个（像是换不动了）。"""

    def __init__(self, names, cycle=False):
        self.names = [n.value if isinstance(n, MC) else n for n in names]
        self.cycle = cycle
        self.i = 0
        self.switches = 0

    def ocr(self, image):
        return self.names[self.i]

    def switch(self):
        self.switches += 1
        self.i = (self.i + 1) % len(self.names) if self.cycle else min(self.i + 1, len(self.names) - 1)


class CollectiveMissionsTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('tasks.CollectiveMissions.script_task.sleep')
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, slot, target=MC.GR1, finished=False, switch_button=True, **consts):
        ui = FakeUi([T.I_CM_SWITCH] if switch_button else [])
        ui.on_click[id(T.I_CM_SWITCH)] = slot.switch
        t = T.__new__(T)
        t.config = SimpleNamespace(collective_missions=CollectiveMissions())
        t.config.collective_missions.missions_config.missions_select = target
        t.screenshot = ui.screenshot
        t.appear = ui.appear
        t.appear_then_click = ui.appear_then_click
        t.goto_page = ui.goto_page
        t.device = SimpleNamespace(image=None, click_record_clear=Mock(name='click_record_clear'))
        t.set_next_run = Mock(name='set_next_run')
        t.get_task_reward = Mock(name='get_task_reward')
        t.is_finish = Mock(name='is_finish', return_value=finished)
        t._donate, t._soul, t._feed = Mock(name='_donate'), Mock(name='_soul'), Mock(name='_feed')
        for k, v in consts.items():
            setattr(t, k, v)
        patcher = patch.object(T, 'O_CM_2', slot)
        patcher.start()
        self.addCleanup(patcher.stop)
        return t

    def run_task(self, t):
        with self.assertRaises(TaskEnd):
            t.run()

    def assert_nothing_done(self, t):
        t._donate.assert_not_called()
        t._soul.assert_not_called()
        t._feed.assert_not_called()

    def assert_retry_in_an_hour(self, t, before):
        t.set_next_run.assert_called_once()
        kwargs = t.set_next_run.call_args.kwargs
        self.assertEqual((kwargs['task'], kwargs['server']), ('CollectiveMissions', False))
        self.assertTrue(before + timedelta(hours=1) <= kwargs['target'] <= datetime.now() + timedelta(hours=1))

    def test_target_after_twenty_switches_is_still_selected(self):
        # 以前最多换 12–15 次就放弃
        slot = FakeSlot([MC.AW1, MC.AW2] * 10 + [MC.GR1])
        t = self.make(slot)
        self.run_task(t)
        self.assertEqual(slot.switches, 20)
        self.assertIs(t.current_mission, MC.GR1)
        t._donate.assert_called_once()
        t.set_next_run.assert_called_once_with(task='CollectiveMissions', success=True)

    def test_same_mission_three_times_in_a_row_is_not_taken_as_stuck(self):
        # 刷新是随机的，连着几次出现同一个任务很正常，不能当成换不动
        slot = FakeSlot([MC.SO1, MC.SO1, MC.SO1, MC.GR1])
        t = self.make(slot)
        self.run_task(t)
        t._donate.assert_called_once()

    def test_cannot_switch_does_nothing_and_retries_in_an_hour(self):
        slot = FakeSlot([MC.SO1])             # 点「换一个」没反应
        t = self.make(slot)
        before = datetime.now()
        self.run_task(t)
        self.assert_nothing_done(t)
        self.assertIsNone(t.current_mission)
        self.assert_retry_in_an_hour(t, before)

    def test_target_never_appears_is_bounded_by_time(self):
        slot = FakeSlot([MC.AW1, MC.AW2, MC.SO2, MC.FEED], cycle=True)
        t = self.make(slot, SELECT_TIMEOUT=0.3)
        before = datetime.now()
        self.run_task(t)
        self.assertGreater(slot.switches, 4)              # 一直在换，不是换不动
        self.assert_nothing_done(t)                       # 回归：以前会去做最后读到的那个任务
        self.assert_retry_in_an_hour(t, before)

    def test_missing_switch_button_ends_like_cannot_switch(self):
        slot = FakeSlot([MC.AW3])
        t = self.make(slot, switch_button=False)
        self.run_task(t)
        self.assertEqual(slot.switches, 0)
        self.assert_nothing_done(t)

    def test_unknown_mission_text_keeps_switching(self):
        slot = FakeSlot(['看不清', MC.GR1])
        t = self.make(slot)
        self.run_task(t)
        t._donate.assert_called_once()

    def test_other_mission_types_go_to_their_own_flow(self):
        for target, flow in ((MC.SO2, '_soul'), (MC.FEED, '_feed'), (MC.AW3, '_donate')):
            with self.subTest(target=target):
                t = self.make(FakeSlot([MC.GR2, target]), target=target)
                self.run_task(t)
                getattr(t, flow).assert_called_once()

    def test_finished_today_does_not_touch_the_missions(self):
        slot = FakeSlot([MC.AW1])
        t = self.make(slot, finished=True)
        self.run_task(t)
        self.assertEqual(slot.switches, 0)
        self.assert_nothing_done(t)
        t.set_next_run.assert_called_once_with(task='CollectiveMissions', success=True)


if __name__ == '__main__':
    unittest.main()
