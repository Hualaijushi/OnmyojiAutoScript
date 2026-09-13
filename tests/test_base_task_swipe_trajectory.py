"""`BaseTask.swipe_trajectory` 公共 helper + `BaseTask.swipe` 迁移到 TouchSwipeModel 的护栏。

全仓 Swipe Consumer 迁移（2026-09-07）：普通页面滑动 / 列表滚动统一走
`BaseTask.swipe_trajectory`——minitouch 下 `TouchSwipeModel().generate` + `Control.swipe_trajectory`，
其它控制后端回退旧 `Control.swipe` 端点滑动。helper 只负责「怎么滑一次」：不截图 /
不 FrameWait / 不 sleep / 不重试 / 不加随机延迟；滑多远、滑完等什么由业务层负责。
起终点自 2026-09-08（D022）来自 `RuleSwipe.sample_endpoints()`（v2 端点采样器），不再是
`coord()` 的窄中心偏置——方向 / 有效距离 / interval / control_name 语义不变。

源码：`tasks/base_task.py` `swipe_trajectory` / `swipe`；`tasks/Component/GeneralBuff/general_buff.py`
`exp_50` / `exp_100`。
"""

import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.base_task import BaseTask


def _task(control_method: str) -> BaseTask:
    t = BaseTask.__new__(BaseTask)
    t.config = SimpleNamespace(
        script=SimpleNamespace(device=SimpleNamespace(control_method=control_method))
    )
    t.device = SimpleNamespace(swipe=Mock(name='swipe'), swipe_trajectory=Mock(name='swipe_trajectory'))
    return t


class SwipeTrajectoryMinitouchTest(TestCase):
    def setUp(self):
        self.gen = Mock(return_value=[(10, 400, 0), (10, 300, 8), (10, 200, 8)])
        self.model = Mock(generate=self.gen)
        self.model_cls = patch('tasks.base_task.TouchSwipeModel', return_value=self.model).start()
        self.addCleanup(patch.stopall)

    def test_minitouch_uses_touch_swipe_model_trajectory(self):
        t = _task('minitouch')
        t.swipe_trajectory((10, 400), (10, 200), control_name='LIST_UP')

        self.gen.assert_called_once_with((10, 400), (10, 200))
        t.device.swipe_trajectory.assert_called_once_with(
            [(10, 400, 0), (10, 300, 8), (10, 200, 8)], control_name='LIST_UP')
        t.device.swipe.assert_not_called()

    def test_trajectory_generated_exactly_once(self):
        t = _task('minitouch')
        t.swipe_trajectory((100, 500), (100, 150))
        self.assertEqual(self.model_cls.call_count, 1)
        self.assertEqual(self.gen.call_count, 1)

    def test_control_name_passthrough_minitouch(self):
        t = _task('minitouch')
        t.swipe_trajectory((0, 0), (0, 300), control_name='CUSTOM_NAME')
        _, kwargs = t.device.swipe_trajectory.call_args
        self.assertEqual(kwargs['control_name'], 'CUSTOM_NAME')

    def test_coords_are_int_cast_before_model(self):
        t = _task('minitouch')
        t.swipe_trajectory((10.7, 400.2), (10.1, 199.9))
        self.gen.assert_called_once_with((10, 400), (10, 199))

    def test_short_distance_falls_back_to_endpoint_swipe_even_on_minitouch(self):
        # < 10px：交给旧 Control.swipe（它自带「太短当点击」的 +1 / 丢弃逻辑），不进轨迹模型
        t = _task('minitouch')
        t.swipe_trajectory((100, 100), (105, 104), control_name='TINY')
        self.gen.assert_not_called()
        t.device.swipe_trajectory.assert_not_called()
        t.device.swipe.assert_called_once_with(p1=(100, 100), p2=(105, 104), control_name='TINY')

    def test_no_screenshot_sleep_retry_in_helper_body(self):
        src = inspect.getsource(BaseTask.swipe_trajectory)
        body = src.split('"""', 2)[-1]
        for token in ('screenshot', 'sleep(', 'wait_for_changed_and_stable',
                      'frame_wait', 'random_delay', 'for _ in range', 'while '):
            self.assertNotIn(token, body, token)

    def test_model_generate_exception_propagates(self):
        self.gen.side_effect = ValueError('起终点距离过小')
        t = _task('minitouch')
        with self.assertRaises(ValueError):
            t.swipe_trajectory((10, 400), (10, 200))
        t.device.swipe_trajectory.assert_not_called()

    def test_executor_exception_propagates(self):
        t = _task('minitouch')
        t.device.swipe_trajectory.side_effect = RuntimeError('minitouch socket lost')
        with self.assertRaises(RuntimeError):
            t.swipe_trajectory((10, 400), (10, 200))


class SwipeTrajectoryFallbackTest(TestCase):
    def setUp(self):
        self.model_cls = patch('tasks.base_task.TouchSwipeModel').start()
        self.addCleanup(patch.stopall)

    def test_non_minitouch_uses_legacy_endpoint_swipe(self):
        t = _task('adb')
        t.swipe_trajectory((10, 400), (10, 200), control_name='LIST_UP')
        t.device.swipe.assert_called_once_with(p1=(10, 400), p2=(10, 200), control_name='LIST_UP')
        t.device.swipe_trajectory.assert_not_called()
        self.model_cls.assert_not_called()

    def test_uiautomator2_uses_legacy_endpoint_swipe(self):
        t = _task('uiautomator2')
        t.swipe_trajectory((500, 600), (500, 200))
        t.device.swipe.assert_called_once()
        self.model_cls.assert_not_called()

    def test_fallback_false_raises_on_non_minitouch(self):
        t = _task('scrcpy')
        with self.assertRaises(NotImplementedError):
            t.swipe_trajectory((10, 400), (10, 200), fallback=False)
        t.device.swipe.assert_not_called()

    def test_control_name_passthrough_fallback(self):
        t = _task('adb')
        t.swipe_trajectory((0, 0), (0, 300), control_name='CUSTOM_NAME')
        _, kwargs = t.device.swipe.call_args
        self.assertEqual(kwargs['control_name'], 'CUSTOM_NAME')


class BaseTaskSwipeRoutesThroughHelperTest(TestCase):
    """`BaseTask.swipe(RuleSwipe)` 走 swipe_trajectory，起终点来自 swipe.sample_endpoints()（D022）。"""

    def _rule_swipe(self):
        from module.atom.swipe import RuleSwipe
        return RuleSwipe(roi_front=(100, 500, 4, 4), roi_back=(100, 150, 4, 4),
                         mode='default', name='S_TEST_UP')

    def test_swipe_delegates_to_swipe_trajectory_with_sampled_endpoints_and_name(self):
        t = BaseTask.__new__(BaseTask)
        t.interval_timer = {}
        rule = self._rule_swipe()
        with patch.object(rule, 'sample_endpoints', return_value=(101, 501, 102, 151)):
            t.swipe_trajectory = Mock()
            ret = t.swipe(rule)
        self.assertIs(ret, True)
        t.swipe_trajectory.assert_called_once_with((101, 501), (102, 151), control_name='S_TEST_UP')

    def test_swipe_non_ruleswipe_returns_false_without_calling_helper(self):
        t = BaseTask.__new__(BaseTask)
        t.swipe_trajectory = Mock()
        self.assertIs(t.swipe('not a rule'), False)
        t.swipe_trajectory.assert_not_called()

    def test_swipe_source_no_longer_calls_device_swipe_directly(self):
        src = inspect.getsource(BaseTask.swipe)
        self.assertNotIn('self.device.swipe(', src)
        self.assertIn('self.swipe_trajectory(', src)


class GeneralBuffScrollMigratedTest(TestCase):
    def test_exp_buff_scroll_uses_swipe_trajectory_not_device_swipe(self):
        from tasks.Component.GeneralBuff.general_buff import GeneralBuff
        for fn in (GeneralBuff.exp_50, GeneralBuff.exp_100):
            src = inspect.getsource(fn)
            self.assertNotIn('self.device.swipe(', src, fn.__name__)
            self.assertIn("self.swipe_trajectory((580, 320), (530, 240)", src)
