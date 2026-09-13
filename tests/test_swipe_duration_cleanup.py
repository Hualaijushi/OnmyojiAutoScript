"""锁住 Control.swipe 的 duration 跨后端契约，以及 RyouToppa 列表滑动仍按原逻辑传 duration。

`Control.swipe(..., duration=...)` 的形参对不同后端语义不同：uiautomator2 / adb 真正
消费 duration，minitouch / scrcpy / window_message 忽略它（滑动时序由各自实现内部决定）。
RyouToppa.flush_area_cache 保留原有的 `random_delay(...)` 采样与 `duration=duration` 传参，
因为它在 adb / uiautomator2 后端具有真实行为语义；在默认 minitouch 环境下该参数不影响
真实滑动时序。本轮只澄清接口契约，不改任何后端实现、不改调用方原行为。
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from module.behavior_trace import reset_behavior_traces
from module.device.control import Control
from tasks.RyouToppa.script_task import ScriptTask as RyouToppaTask


class ControlSwipeDurationContractTest(TestCase):
    def setUp(self):
        reset_behavior_traces()

    def tearDown(self):
        reset_behavior_traces()

    def _make_control(self, method: str) -> Control:
        c = Control.__new__(Control)
        c.config = SimpleNamespace(
            config_name="test",
            script=SimpleNamespace(device=SimpleNamespace(control_method=method)),
        )
        c.swipe_minitouch = Mock()
        c.swipe_uiautomator2 = Mock()
        c.swipe_adb = Mock()
        c.swipe_scrcpy = Mock()
        c.swipe_window_message = Mock()
        return c

    def test_minitouch_swipe_does_not_receive_duration(self):
        c = self._make_control("minitouch")
        c.swipe((10, 10), (10, 400), duration=0.35)
        c.swipe_minitouch.assert_called_once()
        args, kwargs = c.swipe_minitouch.call_args
        self.assertEqual(len(args), 2)  # 只有 p1 / p2
        self.assertNotIn("duration", kwargs)
        c.swipe_uiautomator2.assert_not_called()
        c.swipe_adb.assert_not_called()

    def test_scrcpy_swipe_does_not_receive_duration(self):
        c = self._make_control("scrcpy")
        c.swipe((10, 10), (10, 400), duration=0.35)
        c.swipe_scrcpy.assert_called_once()
        _, kwargs = c.swipe_scrcpy.call_args
        self.assertNotIn("duration", kwargs)

    def test_window_message_swipe_does_not_receive_duration(self):
        c = self._make_control("window_message")
        c.swipe((10, 10), (10, 400), duration=0.35)
        c.swipe_window_message.assert_called_once()
        _, kwargs = c.swipe_window_message.call_args
        self.assertNotIn("duration", kwargs)

    def test_uiautomator2_swipe_receives_duration(self):
        c = self._make_control("uiautomator2")
        c.swipe((10, 10), (10, 400), duration=0.35)
        c.swipe_uiautomator2.assert_called_once()
        _, kwargs = c.swipe_uiautomator2.call_args
        self.assertIn("duration", kwargs)

    def test_adb_swipe_receives_duration(self):
        c = self._make_control("adb")  # 落入 else 分支
        c.swipe((10, 10), (10, 400), duration=0.35)
        c.swipe_adb.assert_called_once()
        _, kwargs = c.swipe_adb.call_args
        self.assertIn("duration", kwargs)


class RyouToppaFlushAreaCacheSwipeTest(TestCase):
    """RyouToppa.flush_area_cache 仍按原逻辑生成并传入 duration（T3-1 收口后恢复）。"""

    def setUp(self):
        reset_behavior_traces()

    def tearDown(self):
        reset_behavior_traces()

    def _make_task(self):
        task = RyouToppaTask.__new__(RyouToppaTask)
        task.device = SimpleNamespace(swipe=Mock())
        task.screenshot = Mock()
        return task

    @patch.object(RyouToppaTask, "_area_content_recognizable", return_value=True)
    @patch.object(RyouToppaTask, "_wait_for_ryou_toppa_page", return_value=True)
    @patch("tasks.RyouToppa.script_task.random_delay", return_value=0.35)
    @patch("tasks.RyouToppa.script_task.random.randint", return_value=3)
    def test_flush_area_cache_first_attempt_passes_duration(
        self, randint_mock, random_delay_mock, _wait, _rec
    ):
        task = self._make_task()

        # 首次即识别成功 -> 只滑一次（attempt == 1 分支）
        self.assertIsNone(task.flush_area_cache())

        task.device.swipe.assert_called_once()
        _, kwargs = task.device.swipe.call_args
        # 原逻辑：仍然生成并传入 duration
        self.assertEqual(kwargs["duration"], 0.35)
        self.assertEqual(set(kwargs), {"p1", "p2", "duration", "control_name"})
        self.assertEqual(kwargs["control_name"], "寮突破列表滑动")
        # attempt == 1 区间
        random_delay_mock.assert_called_once_with(0.342, 0.362)
        # 起点 / 终点 / distance 抖动逻辑不变
        start_x, start_y = kwargs["p1"]
        end_x, end_y = kwargs["p2"]
        self.assertEqual(start_x, 850 + 3)      # 850 + randint(-12, 12)
        self.assertEqual(start_y, 520 + 3)      # 520 + randint(-8, 8)
        self.assertEqual(end_x, start_x + 3)    # start_x + randint(-3, 3)
        self.assertEqual(start_y - end_y, 3)    # distance = randint(97, 105)

    @patch.object(RyouToppaTask, "_area_content_recognizable", side_effect=[False, True])
    @patch.object(RyouToppaTask, "_wait_for_ryou_toppa_page", return_value=True)
    @patch("tasks.RyouToppa.script_task.random_delay", return_value=0.35)
    @patch("tasks.RyouToppa.script_task.random.randint", return_value=1)
    def test_flush_area_cache_retry_attempt_uses_narrower_interval(
        self, randint_mock, random_delay_mock, _wait, _rec
    ):
        task = self._make_task()

        # 第 1 次识别失败、第 2 次成功 -> 两次滑动，第 2 次走 else 分支
        self.assertIsNone(task.flush_area_cache())

        self.assertEqual(task.device.swipe.call_count, 2)
        for _, kwargs in task.device.swipe.call_args_list:
            self.assertEqual(kwargs["duration"], 0.35)
            self.assertIn("duration", kwargs)
        self.assertEqual(
            random_delay_mock.call_args_list,
            [call(0.342, 0.362), call(0.349, 0.355)],
        )
