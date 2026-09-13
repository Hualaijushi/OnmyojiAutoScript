"""`wait_until_appear_then_click` 参数绑定回归测试。

历史缺陷：`wait_until_appear_then_click` 曾以位置参数调用
`self.wait_until_appear(target, wait_time)`，而 `wait_until_appear` 的第二个
位置参数是 `skip_first_screenshot`，第三个才是 `wait_time`。后果有两个：

1. 等待时长被绑成 `skip_first_screenshot`，任何非零 `wait_time` 都会让首轮
   跳过截图，直接拿调用前的旧帧做判断；
2. `wait_time` 在 `wait_until_appear` 内恒为 `None`，超时计时器根本不会建立，
   循环永远不会因超时返回 `False`，只能靠 `stuck_record_check` 抛
   `GameStuckError` 兜底。

下列用例分别锁住这两条后果，以及默认 `wait_time=None` 时的原有行为。
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.atom.image import RuleImage
from tasks.base_task import BaseTask


class _LoopNotBounded(Exception):
    """哨兵异常：缺陷未修复时循环不会退出，用它把死循环转成可断言的失败。"""


class _TimerStub:
    """最小 Timer 替身，只实现 `wait_until_appear` 用到的 start / reached。"""

    def __init__(self, limit):
        self.limit = limit
        self.started = False
        self.reached_calls = 0
        self.reached_result = True

    def start(self):
        self.started = True
        return self

    def reached(self):
        self.reached_calls += 1
        return self.reached_result


def _make_target(name: str = 'target') -> RuleImage:
    """构造一个真实 RuleImage，使 `wait_until_appear` 的 isinstance 分支生效。"""
    target = RuleImage(
        roi_front=(0, 0, 10, 10),
        roi_back=(0, 0, 10, 10),
        method='Template matching',
        threshold=0.8,
        file=f'./tests/{name}.png',
    )
    target.coord = Mock(return_value=(10, 20))
    return target


class WaitUntilAppearThenClickBindingTest(TestCase):
    def setUp(self):
        self.task = BaseTask.__new__(BaseTask)
        self.task.interval_timer = {}
        self.task.device = SimpleNamespace(click=Mock(), long_click=Mock())
        self.screenshot_calls = 0

    def _bounded_screenshot(self, limit: int = 8):
        """截图替身：超过 limit 次即抛哨兵异常，避免缺陷复现时测试挂死。"""

        def screenshot():
            self.screenshot_calls += 1
            if self.screenshot_calls > limit:
                raise _LoopNotBounded(
                    f'wait_until_appear 未在 {limit} 次截图内退出，超时计时器可能未生效'
                )

        return screenshot

    def test_wait_time_is_passed_as_keyword(self):
        """回归护栏：wait_time 必须以关键字传入，不能落到 skip_first_screenshot。"""
        target = _make_target()
        self.task.wait_until_appear = Mock(return_value=True)

        result = self.task.wait_until_appear_then_click(target, wait_time=5)

        self.assertTrue(result)
        self.task.wait_until_appear.assert_called_once_with(target, wait_time=5)

    def test_default_wait_time_is_passed_as_keyword(self):
        """未显式传 wait_time 时同样走关键字，保持默认 None 语义。"""
        target = _make_target()
        self.task.wait_until_appear = Mock(return_value=True)

        result = self.task.wait_until_appear_then_click(target)

        self.assertTrue(result)
        self.task.wait_until_appear.assert_called_once_with(target, wait_time=None)

    @patch('tasks.base_task.Timer')
    def test_timeout_returns_false_and_does_not_click(self, timer_cls):
        """wait_time 到点必须返回 False 并且不点击，而不是无限等待。"""
        timer = _TimerStub(limit=1)
        timer.reached_result = True
        timer_cls.return_value = timer

        target = _make_target()
        self.task.screenshot = Mock(side_effect=self._bounded_screenshot())
        self.task.appear = Mock(return_value=False)

        result = self.task.wait_until_appear_then_click(target, wait_time=1)

        self.assertFalse(result)
        timer_cls.assert_called_once_with(1)
        self.assertTrue(timer.started)
        target.coord.assert_not_called()
        self.task.device.click.assert_not_called()
        self.task.device.long_click.assert_not_called()

    @patch('tasks.base_task.Timer')
    def test_first_screenshot_is_not_skipped(self, timer_cls):
        """wait_time 不得被当成 skip_first_screenshot，首轮必须重新截图。"""
        timer = _TimerStub(limit=5)
        timer.reached_result = False
        timer_cls.return_value = timer

        target = _make_target()
        self.task.screenshot = Mock(side_effect=self._bounded_screenshot())
        self.task.appear = Mock(return_value=True)

        result = self.task.wait_until_appear_then_click(target, wait_time=5)

        self.assertTrue(result)
        # 缺陷版本这里为 0：首轮被 skip_first_screenshot=5 跳过，用的是旧帧。
        self.assertEqual(self.screenshot_calls, 1)
        self.task.device.click.assert_called_once_with(10, 20, control_name=target.name)

    @patch('tasks.base_task.Timer')
    def test_no_timer_is_created_when_wait_time_is_none(self, timer_cls):
        """wait_time 为 None 时保持旧行为：不建计时器，出现即点击。"""
        target = _make_target()
        self.task.screenshot = Mock(side_effect=self._bounded_screenshot())
        self.task.appear = Mock(return_value=True)

        result = self.task.wait_until_appear_then_click(target)

        self.assertTrue(result)
        timer_cls.assert_not_called()
        self.assertEqual(self.screenshot_calls, 1)
        self.task.device.click.assert_called_once_with(10, 20, control_name=target.name)
