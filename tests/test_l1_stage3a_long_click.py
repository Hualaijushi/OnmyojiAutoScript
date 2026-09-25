# This Python file uses the following encoding: utf-8
"""L1 Stage 3A：长按执行入口统一到独立的 `execute_long_click`。

长按不是单击：它走 `Control.long_click`（各后端自己的 DOWN → 持续 duration → UP），与 `execute_single_click`
互不替代——单击执行器拒绝 `RuleLongClick`，长按执行器不降级成单击、不叠加单击 dwell、不重新随机时长。

本轮只换执行入口，**不改采样、不改时长、不改后端分发、不加等待**：坐标仍由 `target.coord()` 在原时机采样一次，
再以 `FinalPoint` 交给长按执行器；`RuleLongClick.duration`（毫秒）仍由调用方 `/ 1000` 成秒后原样透传。

- 契约测试：真实执行器 + 假设备（只暴露 `long_click`，执行器多碰任何别的属性都会 AttributeError）。
- 链路测试：真实执行器 + 真实 `Control.long_click`（假后端表）+ 真实 BehaviorTrace。
- BaseTask 链路：真实 `BaseTask` 方法驱动 6 个迁移点位，包装采样器 / 执行器 / L2 等待记录事件顺序；
  与同一流程里的单击版本逐事件对照（长按流程 = 单击流程，仅最后一个动作从 backend 变成 long）。
- 静态守卫（AST）：BaseTask 不再直调 `device.long_click`；6 个点位都以 `FinalPoint` + `/ 1000` 的秒数交给执行器；
  生产代码里长按只有执行器一个出口，拖拽 / 滑动不会误入长按执行器。
"""

import ast
import json
import random
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from dev_tools import click_callsite_register as reg
from module import behavior_trace
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.long_click import RuleLongClick
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import (ClickBounds, ClickRegion, FinalPoint, execute_long_click, execute_single_click,
                                   resolve_click_point)
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.exception import GameTooManyClickError
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask

_REPO = Path(__file__).resolve().parents[1]
SEED = 20260921
ROI = (400, 300, 200, 90)
ACTION_ROI = (900, 500, 120, 60)


def _inside(point, roi):
    x, y, w, h = roi
    return x <= point[0] < x + w and y <= point[1] < y + h


@contextmanager
def seeded(seed=SEED):
    """所有空间采样共用同一个可复现的随机源（`click_sampler` 与 `random_point_in_roi` 各持有一份引用）。"""
    rng = random.Random(seed)
    with patch('module.click_sampler._rng', rng), patch('module.base.utils.random._rng', rng):
        yield


class _AlwaysReached:
    """`Timer` 替身：`click(interval=)` 的节流一律放行。"""

    def __init__(self, *a, **k):
        self.limit = a[0] if a else 0

    def reached(self):
        return True

    def reset(self):
        return self

    def start(self):
        return self


def _long_device():
    """只暴露 long_click 的假设备：执行器多碰 click / screenshot / sleep 相关属性都会当场 AttributeError。"""
    return SimpleNamespace(long_click=Mock(name='long_click'))


# ======================================================================================
# 一、执行器契约（假设备）
# ======================================================================================

class ExecutorContractTest(TestCase):
    def test_final_point_is_executed_once_with_zero_sampling(self):
        dev = _long_device()
        with patch.object(ClickSampler, 'sample_target', side_effect=AssertionError('不应采样')), \
                patch.object(ClickSampler, 'sample_region', side_effect=AssertionError('不应采样')), \
                patch.object(ClickSampler, 'sample_point', side_effect=AssertionError('不应采样')):
            result = execute_long_click(dev, FinalPoint(123, 456), 1.5, control_name='hold')
        self.assertEqual(result, (123, 456))
        dev.long_click.assert_called_once_with(x=123, y=456, duration=1.5, control_name='hold')

    def test_rule_target_is_sampled_exactly_once_and_matches_the_coord_reference(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_rule')
        reference_rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_rule')
        with seeded():
            expected = reference_rule.coord()                          # 迁移前的采样表达式
        dev = _long_device()
        original = ClickSampler.sample_target
        calls = []

        def counted(roi, name=None, *a, **k):
            calls.append((tuple(roi), name))
            return original(roi, name, *a, **k)

        with seeded(), patch.object(ClickSampler, 'sample_target', side_effect=counted):
            result = execute_long_click(dev, rule, 1.5)
        self.assertEqual(calls, [(ROI, 'stage3a_rule')])
        self.assertEqual(result, expected)
        self.assertTrue(_inside(result, ROI))
        dev.long_click.assert_called_once_with(x=expected[0], y=expected[1], duration=1.5, control_name='stage3a_rule')

    def test_region_and_bounds_targets_reuse_the_single_click_resolution(self):
        for target in (ClickRegion(ROI, 'region_name'), ClickBounds(ROI, 'bounds_name')):
            with self.subTest(target=type(target).__name__):
                dev = _long_device()
                with seeded():
                    expected = resolve_click_point(target)
                with seeded():
                    result = execute_long_click(dev, target, 1.0)
                self.assertEqual(result, expected)
                self.assertEqual(dev.long_click.call_count, 1)

    def test_duration_is_passed_through_untouched(self):
        # 执行器不换算单位、不随机、不夹取：`RuleLongClick.duration` 的毫秒 → 秒由调用方负责
        for duration in (1.5, 0.8, 0, 1500, 0.045, (0.5, 2), None):
            with self.subTest(duration=duration):
                dev = _long_device()
                execute_long_click(dev, FinalPoint(1, 2), duration, control_name='n')
                self.assertIs(dev.long_click.call_args.kwargs['duration'], duration)

    def test_control_name_defaults_and_explicit_values_are_passed_through_verbatim(self):
        dev = _long_device()
        execute_long_click(dev, FinalPoint(1, 2), 1.0)
        self.assertEqual(dev.long_click.call_args.kwargs['control_name'], 'LongClick')     # 与 Control.long_click 的默认一致
        dev = _long_device()
        execute_long_click(dev, RuleLongClick(ROI, ROI, 1000, 'named'), 1.0)
        self.assertEqual(dev.long_click.call_args.kwargs['control_name'], 'named')
        for explicit in ('other', '', None):                          # 显式传入一律原样，不做空值回退
            with self.subTest(control_name=explicit):
                dev = _long_device()
                execute_long_click(dev, RuleLongClick(ROI, ROI, 1000, 'named'), 1.0, control_name=explicit)
                self.assertIs(dev.long_click.call_args.kwargs['control_name'], explicit)

    def test_no_sleep_no_screenshot_no_click(self):
        dev = _long_device()                                          # 没有 click / screenshot 属性
        with patch('time.sleep', side_effect=AssertionError('执行器不得等待')) as sleep:
            execute_long_click(dev, FinalPoint(5, 6), 1.5, control_name='n')
        sleep.assert_not_called()
        self.assertEqual(dev.long_click.call_count, 1)

    def test_backend_exception_propagates_as_the_same_object(self):
        boom = OSError('device gone')
        dev = _long_device()
        dev.long_click.side_effect = boom
        with self.assertRaises(OSError) as ctx:
            execute_long_click(dev, FinalPoint(1, 2), 1.0)
        self.assertIs(ctx.exception, boom)
        self.assertEqual(dev.long_click.call_count, 1)                # 不重试

    def test_invalid_targets_follow_the_single_click_error_contract(self):
        for bad in ((10, 20), None, 'x', [1, 2]):
            with self.subTest(target=bad):
                dev = _long_device()
                with self.assertRaises(TypeError) as long_ctx:
                    execute_long_click(dev, bad, 1.0)
                with self.assertRaises(TypeError) as single_ctx:
                    execute_single_click(SimpleNamespace(click=Mock()), bad)
                self.assertEqual(str(long_ctx.exception), str(single_ctx.exception))
                dev.long_click.assert_not_called()

    def test_single_click_executor_still_rejects_long_targets_and_stays_a_click(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_no_downgrade')
        dev = SimpleNamespace(click=Mock(), long_click=Mock())
        with self.assertRaises(TypeError):
            execute_single_click(dev, rule)
        dev.click.assert_not_called()
        dev.long_click.assert_not_called()
        execute_single_click(dev, FinalPoint(7, 8), control_name='tap')
        dev.click.assert_called_once_with(x=7, y=8, control_name='tap')
        dev.long_click.assert_not_called()


# ======================================================================================
# 二、真实 Control.long_click 链路（假后端表 + 真实 BehaviorTrace）
# ======================================================================================

class ControlHarness(TestCase):
    METHODS = ('minitouch', 'ADB', 'uiautomator2', 'scrcpy', 'window_message')

    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.addCleanup(self._restore)                             # cleanup 后进先出：先 reset（关文件句柄）再删目录
        self.addCleanup(reset_behavior_traces)
        configure_behavior_trace('stage3a', enabled=True)

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    def control(self, method='minitouch'):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(config_name='stage3a', script=SimpleNamespace(device=SimpleNamespace(control_method=method)))
        self.long_backends = {m: Mock(name=f'long_{m}') for m in self.METHODS}
        self.click_backends = {m: Mock(name=f'click_{m}') for m in self.METHODS}
        c.long_click_methods = self.long_backends
        c.click_methods = self.click_backends
        c.long_click_adb = Mock(name='long_click_adb')             # 未配置的 control_method 的兜底后端
        c.click_adb = Mock(name='click_adb')
        return c

    def trace_rows(self):
        files = list(behavior_trace._LOG_DIR.glob('stage3a_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []


class ControlChainTest(ControlHarness):
    def test_each_supported_backend_receives_one_long_press_with_the_same_arguments(self):
        for method in self.METHODS:
            with self.subTest(method=method):
                c = self.control(method)
                execute_long_click(c, FinalPoint(300, 400), 1.5, control_name='hold')
                self.long_backends[method].assert_called_once_with(300, 400, 1.5)
                for other, backend in self.long_backends.items():
                    if other != method:
                        backend.assert_not_called()
                c.long_click_adb.assert_not_called()

    def test_unconfigured_control_method_falls_back_to_adb_like_control_does(self):
        c = self.control('nemu_ipc')                                # 不在 long_click_methods 里
        execute_long_click(c, FinalPoint(30, 40), 1.5, control_name='hold')
        c.long_click_adb.assert_called_once_with(30, 40, 1.5)
        for backend in self.long_backends.values():
            backend.assert_not_called()

    def test_control_long_click_runs_once_and_control_click_never(self):
        c = self.control()
        original = Control.long_click
        with patch.object(Control, 'long_click', autospec=True, side_effect=original) as long_spy, \
                patch.object(Control, 'click', autospec=True) as click_spy, \
                patch.object(Control, 'click_with_backend', autospec=True) as click_backend_spy:
            execute_long_click(c, RuleLongClick(ROI, ROI, 1500, 'lc'), 1.5)
        self.assertEqual(long_spy.call_count, 1)
        click_spy.assert_not_called()
        click_backend_spy.assert_not_called()
        for backend in list(self.click_backends.values()) + [c.click_adb]:
            backend.assert_not_called()                            # 没有降级成单击
        self.assertEqual(sum(b.call_count for b in self.long_backends.values()), 1)

    def test_duration_none_uses_the_control_default_and_ranges_go_through_control(self):
        c = self.control()
        execute_long_click(c, FinalPoint(1, 2), None)
        self.long_backends['minitouch'].assert_called_with(1, 2, 0.8)          # Control.long_click 的 None 语义未变
        execute_long_click(c, FinalPoint(1, 2), 1.5)
        self.long_backends['minitouch'].assert_called_with(1, 2, 1.5)
        execute_long_click(c, FinalPoint(1, 2), (0.5, 2))
        self.assertTrue(0.5 <= self.long_backends['minitouch'].call_args.args[2] <= 2)

    def test_behavior_trace_records_one_long_click_with_the_final_coordinates_and_no_click(self):
        c = self.control()
        execute_long_click(c, FinalPoint(310, 420), 1.5, control_name='trace_me')
        rows = self.trace_rows()
        self.assertEqual([(r['action'], r['target'], r['extra']) for r in rows],
                         [('long_click', 'trace_me', {'x': 310, 'y': 420})])
        self.assertNotIn('click', [r['action'] for r in rows])

    def test_backend_failure_propagates_and_leaves_no_trace_row(self):
        c = self.control()
        boom = OSError('minitouch down')
        self.long_backends['minitouch'].side_effect = boom
        with self.assertRaises(OSError) as ctx:
            execute_long_click(c, FinalPoint(1, 2), 1.5, control_name='fail')
        self.assertIs(ctx.exception, boom)
        self.assertEqual(self.long_backends['minitouch'].call_count, 1)
        self.assertEqual(self.trace_rows(), [])                    # 观测只记录正常返回的动作（与迁移前一致）

    def test_control_check_error_propagates_before_any_backend(self):
        c = self.control()
        c.handle_control_check = Mock(side_effect=GameTooManyClickError('too many'))
        with self.assertRaises(GameTooManyClickError):
            execute_long_click(c, FinalPoint(1, 2), 1.5, control_name='guard')
        c.handle_control_check.assert_called_once_with('guard')
        for backend in self.long_backends.values():
            backend.assert_not_called()


# ======================================================================================
# 三、BaseTask 三个 primitive 的 6 个迁移点位
# ======================================================================================

class PrimitiveHarness(ControlHarness):
    """帧序列驱动的真实 BaseTask 方法；`events` 按发生顺序记录 sample / execute / 等待 / 后端。"""

    def setUp(self):
        super().setUp()
        self.events = []

    def task(self, frames, method='minitouch'):
        state = {'frame': 0}
        events = self.events

        def screenshot():
            state['frame'] += 1
            events.append(('screenshot', state['frame']))

        def appear(target, interval=None, threshold=None):
            visible = frames[min(state['frame'], len(frames) - 1)].get(target.name)
            if visible is not None:
                target.roi_front = list(visible) if isinstance(target, RuleImage) else tuple(visible)
            return visible is not None

        c = self.control(method)
        for name, backend in self.long_backends.items():
            backend.side_effect = lambda x, y, d, _n=name: events.append(('long', x, y, d))
        for name, backend in self.click_backends.items():
            backend.side_effect = lambda x, y, _n=name: events.append(('backend', x, y))
        task = BaseTask.__new__(BaseTask)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.appear = appear
        task.device = c
        task.device.image = 'F'
        return task

    @staticmethod
    def image(name='stage3a_img', roi=ROI):
        return RuleImage(roi, roi, 'Template matching', 0.8, f'./{name}.png')

    def run_task(self, fn):
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            self.events.append(('sample', tuple(roi), name))
            return original(roi, name, *a, **k)

        def long_executor(device, target, duration, control_name=None):
            self.events.append(('execute_long', target, duration, control_name))
            return execute_long_click(device, target, duration, control_name=control_name)

        def single_executor(device, target, control_name=None, backend=None):
            self.events.append(('execute', target, control_name))
            return execute_single_click(device, target, control_name=control_name, backend=backend)

        with patch.object(ClickSampler, 'sample_target', side_effect=counted), \
                patch('tasks.base_task.execute_long_click', side_effect=long_executor), \
                patch('tasks.base_task.execute_single_click', side_effect=single_executor), \
                patch('tasks.base_task.random_delay', side_effect=lambda lo, hi: self.events.append(('reaction', lo, hi)) or lo), \
                patch('tasks.base_task.sleep', side_effect=lambda s: self.events.append(('sleep', s))):
            return fn()

    def kinds(self):
        return [e[0] for e in self.events]

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def assert_one_long_chain(self, roi, duration, control_name, sampled_name=None):
        """一次长按 = 采样一次 = 长按执行器一次（FinalPoint）= 后端长按一次；落点在 roi 内；从未走过单击。"""
        self.assertEqual(len(self.of('sample')), 1)
        self.assertEqual(len(self.of('execute_long')), 1)
        self.assertEqual(len(self.of('long')), 1)
        self.assertEqual((self.of('execute'), self.of('backend')), ([], []))
        _, target, dur, name = self.of('execute_long')[0]
        self.assertIsInstance(target, FinalPoint)                  # 已采样的坐标以 FinalPoint 传递，执行器零采样
        self.assertEqual(dur, duration)
        self.assertEqual(name, control_name)
        _, x, y, d = self.of('long')[0]
        self.assertEqual((x, y), (target.x, target.y))
        self.assertEqual(d, duration)                              # 后端收到的秒数 = 调用方换算后的秒数，未被二次加工
        self.assertTrue(_inside((x, y), roi))
        if sampled_name is not None:
            self.assertEqual(self.of('sample')[0][2], sampled_name)
        self.assertEqual([(r['action'], r['target'], r['extra']['x'], r['extra']['y']) for r in self.trace_rows()],
                         [('long_click', control_name, x, y)])


class PrimitiveLongClickTest(PrimitiveHarness):
    def test_click_with_a_long_rule(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_long')
        task = self.task([{}])
        self.run_task(lambda: task.click(rule))
        self.assert_one_long_chain(ROI, 1.5, 'stage3a_long', sampled_name='stage3a_long')   # 毫秒 → 秒；control_name = click.name
        self.assertEqual(self.kinds(), ['sample', 'execute_long', 'long'])

    def test_click_long_rule_interval_not_reached_is_zero_sampling_and_zero_press(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_interval')
        task = self.task([{}])
        task.interval_timer[rule.name] = SimpleNamespace(limit=5, reached=lambda: False, reset=lambda: None)
        self.assertFalse(self.run_task(lambda: task.click(rule, interval=5)))
        self.assertEqual(self.events, [])

    def test_click_return_value_semantics_unchanged(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_ret')
        task = self.task([{}])
        with patch('tasks.base_task.Timer', _AlwaysReached):
            self.assertFalse(self.run_task(lambda: task.click(rule)))              # 无 interval：按了也返回 False
            self.assertTrue(self.run_task(lambda: task.click(rule, interval=1)))   # 设置并到达 interval：返回 True

    def test_appear_then_click_long_action_uses_action_roi_and_target_name(self):
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_action')
        task = self.task([{img.name: ROI}])
        self.assertTrue(self.run_task(lambda: task.appear_then_click(img, action=action)))
        self.assert_one_long_chain(ACTION_ROI, 1.5, img.name, sampled_name='stage3a_action')   # 落点在 action ROI，名字仍是 target.name
        self.assertEqual(self.kinds(), ['sample', 'execute_long', 'long'])                     # 无 reaction / 无额外截图

    def test_appear_then_click_explicit_duration_is_milliseconds_too(self):
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_action')
        task = self.task([{img.name: ROI}])
        self.assertTrue(self.run_task(lambda: task.appear_then_click(img, action=action, duration=800)))
        self.assert_one_long_chain(ACTION_ROI, 0.8, img.name)      # 显式 duration 覆盖 action.duration，仍是毫秒 / 1000

    def test_appear_then_click_long_action_with_reaction_matches_the_single_click_flow(self):
        img = self.image()
        moved = (700, 450, 120, 60)
        long_action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_action')
        click_action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage3a_action')
        flows = {}
        for label, action in (('long', long_action), ('click', click_action)):
            self.events.clear()
            task = self.task([{img.name: ROI}, {img.name: moved}])
            self.assertTrue(self.run_task(lambda: task.appear_then_click(img, action=action, policy=InteractionPolicy.NORMAL)))
            flows[label] = list(self.kinds())
        # reaction → sleep → fresh 截图 → 新一次采样 → 动作：长按流程与单击流程逐事件一致，只有最后的动作不同
        self.assertEqual(flows['long'], ['reaction', 'sleep', 'screenshot', 'sample', 'execute_long', 'long'])
        self.assertEqual(flows['click'], ['reaction', 'sleep', 'screenshot', 'sample', 'execute', 'backend'])

    def test_legacy_confirm_delay_long_action_samples_once_after_reconfirm(self):
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_action')
        task = self.task([{img.name: ROI}, {img.name: ROI}])
        self.assertTrue(self.run_task(lambda: task.appear_then_click(img, action=action, confirm_delay=(0.1, 0.2))))
        self.assert_one_long_chain(ACTION_ROI, 1.5, img.name)

    def test_target_gone_after_reaction_is_zero_press(self):
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_action')
        task = self.task([{img.name: ROI}, {}])
        self.assertFalse(self.run_task(lambda: task.appear_then_click(img, action=action, policy=InteractionPolicy.CONFIRM)))
        for kind in ('sample', 'execute_long', 'long'):
            self.assertEqual(self.of(kind), [])

    def test_wait_until_appear_then_click_long_action_samples_the_target_like_before(self):
        # 原写法：长按点位取 `target.coord()`（不是 action 的 ROI），时长取 action.duration；迁移保持不变
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_wait_action')
        task = self.task([{img.name: ROI}])
        task.wait_until_appear = Mock(return_value=True)
        self.assertTrue(self.run_task(lambda: task.wait_until_appear_then_click(img, action=action)))
        self.assert_one_long_chain(ROI, 1.5, img.name, sampled_name=img.name)

    def test_long_press_never_touches_the_single_click_path(self):
        img = self.image()
        long_rule = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage3a_no_click')
        task = self.task([{img.name: ROI}])
        task.wait_until_appear = Mock(return_value=True)
        with patch.object(Control, 'click', autospec=True) as click_spy, \
                patch.object(Control, 'click_with_backend', autospec=True) as backend_spy:
            self.run_task(lambda: (task.click(long_rule), task.appear_then_click(img, action=long_rule),
                                   task.wait_until_appear_then_click(img, action=long_rule)))
        click_spy.assert_not_called()
        backend_spy.assert_not_called()
        self.assertEqual((self.of('execute'), self.of('backend')), ([], []))
        self.assertEqual((len(self.of('sample')), len(self.of('execute_long')), len(self.of('long'))), (3, 3, 3))

    def test_backend_exception_propagates_without_a_second_press(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'stage3a_fail')
        task = self.task([{}])
        self.long_backends['minitouch'].side_effect = OSError('device gone')
        with self.assertRaises(OSError):
            self.run_task(lambda: task.click(rule))
        self.assertEqual((len(self.of('sample')), len(self.of('execute_long'))), (1, 1))
        self.assertEqual(self.long_backends['minitouch'].call_count, 1)


class SeededEquivalenceTest(PrimitiveHarness):
    """迁移前 / 迁移后等价：参考值是迁移前写法的表达式（`rule.coord()` + `duration / 1000` + `rule.name`），
    在同一个 seed 下由**未经执行器的独立计算**得出；迁移后的真实 primitive 必须逐值相等。"""

    def _expected(self, rule):
        with seeded():
            x, y = rule.coord()
        return int(x), int(y)

    def test_click_matches_the_original_expressions(self):
        for duration in (1000, 1500, 2300):
            with self.subTest(duration=duration):
                self.events.clear()
                rule = RuleLongClick(ROI, ROI, duration, 'eq_click')
                expected = self._expected(RuleLongClick(ROI, ROI, duration, 'eq_click'))
                task = self.task([{}])
                with seeded():
                    self.run_task(lambda: task.click(rule))
                self.assertEqual(self.of('long'), [('long', expected[0], expected[1], duration / 1000)])

    def test_appear_then_click_matches_the_original_expressions(self):
        img = self.image()
        for explicit in (None, 800):
            with self.subTest(explicit=explicit):
                self.events.clear()
                action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'eq_action')
                expected = self._expected(RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'eq_action'))
                task = self.task([{img.name: ROI}])
                with seeded():
                    self.run_task(lambda: task.appear_then_click(img, action=action, duration=explicit))
                want = (explicit if explicit is not None else 1500) / 1000
                self.assertEqual(self.of('long'), [('long', expected[0], expected[1], want)])

    def test_wait_until_appear_then_click_matches_the_original_expressions(self):
        img = self.image()
        action = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'eq_wait_action')
        with seeded():
            x, y = self.image().coord()                                                # 原写法：target.coord()
        task = self.task([{img.name: ROI}])
        task.wait_until_appear = Mock(return_value=True)
        with seeded():
            self.run_task(lambda: task.wait_until_appear_then_click(img, action=action))
        self.assertEqual(self.of('long'), [('long', int(x), int(y), 1.5)])

    def test_execution_counts_and_waits_equal_for_repeated_calls(self):
        rule = RuleLongClick(ROI, ROI, 1500, 'eq_repeat')
        task = self.task([{}])
        with seeded():
            self.run_task(lambda: [task.click(rule) for _ in range(3)])
        self.assertEqual((len(self.of('sample')), len(self.of('long'))), (3, 3))       # 每次长按各自采样，互不复用
        self.assertEqual((self.of('sleep'), self.of('reaction'), self.of('screenshot')), ([], [], []))


class ProductionLongClickAssetsTest(PrimitiveHarness):
    """生产里真实存在的 `RuleLongClick` 资产（都经 `BaseTask.click` 长按）：时长、名字、落点区域逐个不变。"""

    @staticmethod
    def _assets():
        from tasks.CollectiveMissions.assets import CollectiveMissionsAssets
        from tasks.Exploration.assets import ExplorationAssets
        from tasks.SoulsTidy.assets import SoulsTidyAssets
        rules = []
        for cls in (CollectiveMissionsAssets, ExplorationAssets, SoulsTidyAssets):
            rules.extend((f'{cls.__name__}.{k}', v) for k, v in vars(cls).items() if isinstance(v, RuleLongClick))
        return rules

    def test_every_production_long_click_asset_goes_through_the_long_executor(self):
        rules = self._assets()
        self.assertEqual(len(rules), 10)                            # L_FEED_CLICK_1~4 / L_SL_LONG / L_ROTATE_1~4 / L_ONE
        for label, rule in rules:
            with self.subTest(asset=label):
                self.events.clear()
                reset_behavior_traces()
                for f in behavior_trace._LOG_DIR.glob('stage3a_*.jsonl'):
                    f.unlink()
                configure_behavior_trace('stage3a', enabled=True)
                task = self.task([{}])
                self.run_task(lambda: task.click(rule))
                self.assert_one_long_chain(tuple(rule.roi_front), rule.duration / 1000, rule.name)
                self.assertEqual(rule.duration, 1500)                # 资产声明的毫秒时长未被改动


# ======================================================================================
# 四、静态守卫（AST）：长按只有一个出口；拖拽 / 滑动不会误入
# ======================================================================================

def _base_task_functions():
    tree = ast.parse((_REPO / 'tasks' / 'base_task.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BaseTask')
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _module_function(path, name):
    tree = ast.parse((_REPO / path).read_text(encoding='utf-8'))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _chain(func):
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return '.'.join(reversed(parts))


def _calls_named(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and _chain(c.func).split('.')[-1] == name]


class StaticGuardTest(TestCase):
    EXPECTED = {'appear_then_click': 4, 'wait_until_appear_then_click': 1, 'click': 1}

    def test_base_task_has_no_direct_long_click_left(self):
        for name, fn in _base_task_functions().items():
            with self.subTest(func=name):
                self.assertEqual([c.lineno for c in _calls_named(fn, 'long_click')], [])

    def test_the_six_execution_points_pass_a_final_point_and_a_seconds_duration(self):
        funcs = _base_task_functions()
        total = 0
        for name, count in self.EXPECTED.items():
            calls = [c for c in _calls_named(funcs[name], 'execute_long_click') if isinstance(c.func, ast.Name)]
            total += len(calls)
            with self.subTest(func=name):
                self.assertEqual(len(calls), count)
                for call in calls:
                    self.assertEqual(getattr(call.args[1], 'func', None) and call.args[1].func.id, 'FinalPoint')   # 不是把 Rule 直接交进去
                    duration = call.args[2]
                    self.assertIsInstance(duration, ast.BinOp)                                                      # `<ms> / 1000`
                    self.assertIsInstance(duration.op, ast.Div)
                    self.assertEqual(duration.right.value, 1000)
                    self.assertTrue(any(kw.arg == 'control_name' for kw in call.keywords))
        self.assertEqual(total, 6)

    def test_only_the_three_long_press_primitives_use_the_long_executor(self):
        users = {name for name, fn in _base_task_functions().items() if _calls_named(fn, 'execute_long_click')}
        self.assertEqual(users, set(self.EXPECTED))               # swipe / swipe_trajectory / ui_click* 等都不在其中

    def test_long_executor_body_only_resolves_and_calls_device_long_click(self):
        fn = _module_function('module/click_pipeline.py', 'execute_long_click')
        names = {_chain(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        self.assertEqual(names, {'resolve_click_point', 'getattr', 'device.long_click'})
        self.assertEqual(len(_calls_named(fn, 'long_click')), 1)  # 一次调用 = 一次长按

    def test_single_click_executor_never_calls_long_click(self):
        fn = _module_function('module/click_pipeline.py', 'execute_single_click')
        self.assertEqual(_calls_named(fn, 'long_click'), [])
        self.assertEqual(_calls_named(fn, 'execute_long_click'), [])

    def test_production_long_click_has_a_single_exit(self):
        sites = reg.scan_long_click_sites()
        by = {}
        for s in sites:
            by.setdefault((s['kind'], s['area']), []).append(s['file'])
        self.assertEqual(by.get(('raw_long_click', 'consumer'), []), [])          # 消费代码没有直调 long_click
        self.assertEqual(by.get(('raw_long_click', 'primitive'), []), [])         # BaseTask 也没有
        self.assertEqual(by.get(('raw_long_backend', 'consumer'), []), [])
        self.assertEqual(by.get(('raw_long_backend', 'primitive'), []), [])
        self.assertEqual(by.get(('execute_long_click', 'consumer'), []), [])      # 业务不直接拿执行器，只经 BaseTask primitive
        self.assertEqual(len(by[('execute_long_click', 'primitive')]), 6)
        self.assertEqual(by[('raw_long_click', 'executor')], ['module/click_pipeline.py'])   # 唯一的直调出口
        self.assertEqual({f for (k, a), fs in by.items() if a == 'device_internal' for f in fs},
                         {'module/device/method/uiautomator_2.py', 'module/device/method/windows_impl.py'})

    def test_drag_swipe_and_special_touch_modules_never_use_the_long_executor(self):
        for rel in ('tasks/Chess/runtime/press_and_drag.py', 'tasks/Hyakkiyakou/slave/hya_device.py',
                    'tasks/GameUi/navigator.py', 'tasks/Component/GeneralBattle/general_battle.py',
                    'tasks/KekkaiUtilize/script_task.py', 'tasks/Component/GeneralInvite/general_invite.py'):
            with self.subTest(file=rel):
                text = (_REPO / rel).read_text(encoding='utf-8')
                self.assertNotIn('execute_long_click', text)
                self.assertNotIn('long_click', text)

    def test_swipe_and_drag_primitives_do_not_call_control_long_click(self):
        funcs = _base_task_functions()
        for name in ('swipe', 'swipe_trajectory'):
            with self.subTest(func=name):
                self.assertEqual(_calls_named(funcs[name], 'long_click'), [])
                self.assertEqual(_calls_named(funcs[name], 'execute_long_click'), [])
