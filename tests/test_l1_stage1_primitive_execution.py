# This Python file uses the following encoding: utf-8
"""L1 Stage 1：BaseTask 公共单击 primitive 的执行入口统一到 `execute_single_click`。

范围：`appear_then_click`（4 处）/ `wait_until_appear_then_click`（2 处）/ `click`（1 处）/ `ocr_appear_click`（1 处）
共 8 个原来直接 `device.click` 的执行点。本轮只换执行入口，**不改采样**：坐标仍由目标的 `coord()`
（→ `ClickSampler.sample_target`）在原时机采样一次，再以 `FinalPoint` 交给执行器——执行器对 `FinalPoint` 零采样。
同时修复 `ocr_appear_click` 的 action 分支里「`action.coord()` 采样后丢弃、`self.click(action)` 再采一次」的无效重复采样。

- 链路测试：真实 `BaseTask` 方法 + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace + 包装采样器与执行器计数；
  断言的是「一次点击 = sample_target 一次 = execute_single_click 一次 = 后端一次」，不是源码里出现某个字符串。
- 静态守卫（AST）：BaseTask 不再有 `device.click`；每个新执行点的第一个实参都是 `FinalPoint(...)`（防止「先 coord() 再把
  Rule 交给执行器」的双采样写法）。长按在 Stage 1 时仍是 `device.long_click`，Stage 3A 起统一到独立的
  `execute_long_click`（见 `tests/test_l1_stage3a_long_click.py`），单击执行器依旧拒绝长按。
"""

import ast
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import behavior_trace
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import FinalPoint, execute_single_click
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask

_REPO = Path(__file__).resolve().parents[1]
ROI = (400, 300, 200, 90)
ACTION_ROI = (900, 500, 120, 60)


def _inside(point, roi):
    x, y, w, h = roi
    return x <= point[0] < x + w and y <= point[1] < y + h


class _AlwaysReached:
    """`Timer` 替身：`click(interval=)` 的节流一律放行，避免测试里真等时间。"""

    def __init__(self, *a, **k):
        self.limit = a[0] if a else 0

    def reached(self):
        return True

    def reset(self):
        return self

    def start(self):
        return self


class ChainHarness(TestCase):
    """帧序列驱动的真实 primitive 链路：`frames[n]` = 第 n 次 screenshot 之后可见目标的 roi 映射（frames[0] = 截图前）。"""

    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.addCleanup(self._restore)                             # cleanup 后进先出：先 reset（关文件句柄）再删目录
        self.addCleanup(reset_behavior_traces)
        self.events = []
        self.backend = Mock(name='backend', side_effect=lambda x, y: self.events.append(('backend', x, y)))
        configure_behavior_trace('stage1', enabled=True)

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    # ---- 构造 ----
    def _control(self):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(
            config_name='stage1', script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        c.click_methods = {'minitouch': self.backend}
        c.long_click_methods = {'minitouch': Mock(name='long_backend')}
        self.long_backend = c.long_click_methods['minitouch']
        return c

    def _task(self, frames):
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

        task = BaseTask.__new__(BaseTask)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.appear = appear
        task.device = self._control()
        task.device.image = 'F'
        return task

    @staticmethod
    def _image(name='stage1_img', roi=ROI):
        return RuleImage(roi, roi, 'Template matching', 0.8, f'./{name}.png')

    def _run(self, fn):
        """在采样器 / 执行器 / L2 等待包装下运行 `fn()`，返回它的返回值。"""
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            self.events.append(('sample', tuple(roi), name))
            return original(roi, name, *a, **k)

        def executor(device, target, control_name=None, backend=None):
            self.events.append(('execute', target, control_name))
            return execute_single_click(device, target, control_name=control_name, backend=backend)

        with patch.object(ClickSampler, 'sample_target', side_effect=counted), \
                patch('tasks.base_task.execute_single_click', side_effect=executor), \
                patch('tasks.base_task.random_delay', side_effect=lambda lo, hi: self.events.append(('reaction', lo, hi)) or lo), \
                patch('tasks.base_task.sleep', side_effect=lambda s: self.events.append(('sleep', s))):
            return fn()

    def fresh(self):
        """子用例之间清空事件与 trace 文件（同一天的 trace 文件会累积）。"""
        self.events.clear()
        reset_behavior_traces()
        for f in behavior_trace._LOG_DIR.glob('stage1_*.jsonl'):
            f.unlink()
        configure_behavior_trace('stage1', enabled=True)

    def kinds(self):
        return [e[0] for e in self.events]

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def trace_rows(self):
        files = list(behavior_trace._LOG_DIR.glob('stage1_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []

    def assert_one_click_chain(self, roi, control_name):
        """一次点击 = 采样一次 = 执行器一次（第一个实参是 FinalPoint）= 后端一次，落点在 roi 内，trace 记录同一坐标。"""
        self.assertEqual(len(self.of('sample')), 1)
        self.assertEqual(len(self.of('execute')), 1)
        self.assertEqual(len(self.of('backend')), 1)
        _, target, name = self.of('execute')[0]
        self.assertIsInstance(target, FinalPoint)                     # 已采样的坐标以 FinalPoint 传递，执行器零采样
        self.assertEqual(name, control_name)
        _, x, y = self.of('backend')[0]
        self.assertEqual((x, y), (target.x, target.y))
        self.assertTrue(_inside((x, y), roi))
        self.assertEqual([(r['target'], r['extra']['x'], r['extra']['y']) for r in self.trace_rows()],
                         [(control_name, x, y)])                      # BehaviorTrace 记录的是实际执行的最终坐标


# ======================================================================================
# 一、appear_then_click / click：一次点击 = 一次采样 = 一次执行
# ======================================================================================

class PrimitiveChainTest(ChainHarness):
    def test_appear_then_click_image_immediate(self):
        img = self._image()
        task = self._task([{img.name: ROI}])
        self.assertTrue(self._run(lambda: task.appear_then_click(img)))
        self.assert_one_click_chain(ROI, img.name)
        self.assertEqual(self.kinds(), ['sample', 'execute', 'backend'])   # 无 reaction / 无额外截图

    def test_appear_then_click_returns_false_and_clicks_nothing_when_absent(self):
        img = self._image()
        task = self._task([{}])
        self.assertFalse(self._run(lambda: task.appear_then_click(img)))
        self.assertEqual(self.events, [])

    def test_action_click_uses_action_roi_but_target_name_for_control_name(self):
        img = self._image()
        action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage1_action')
        task = self._task([{img.name: ROI}])
        self.assertTrue(self._run(lambda: task.appear_then_click(img, action=action)))
        self.assert_one_click_chain(ACTION_ROI, img.name)             # 落点在 action 的 ROI，control_name 仍是 target.name
        self.assertEqual(self.of('sample')[0][2], 'stage1_action')     # 采样身份是 action

    def test_action_click_with_reaction_uses_target_name_too(self):
        img = self._image()
        action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage1_action')
        task = self._task([{img.name: ROI}, {img.name: ROI}])
        self.assertTrue(self._run(lambda: task.appear_then_click(img, action=action, policy=InteractionPolicy.FAST)))
        self.assert_one_click_chain(ACTION_ROI, img.name)

    def test_click_rule_click_and_image_and_ocr(self):
        rule = RuleClick(ROI, ROI, 'stage1_rule')
        ocr = RuleOcr(name='stage1_ocr', mode='Single', method='Default', roi=ACTION_ROI, area=ACTION_ROI, keyword='')
        img = self._image('stage1_click_img')
        for target, roi in ((rule, ROI), (img, ROI), (ocr, ACTION_ROI)):
            with self.subTest(target=target.name):
                self.fresh()
                task = self._task([{}])
                self._run(lambda: task.click(target))
                self.assert_one_click_chain(roi, target.name)

    def test_click_interval_not_reached_means_zero_sampling_and_zero_click(self):
        rule = RuleClick(ROI, ROI, 'stage1_interval')
        task = self._task([{}])
        task.interval_timer[rule.name] = SimpleNamespace(limit=5, reached=lambda: False, reset=lambda: None)
        self.assertFalse(self._run(lambda: task.click(rule, interval=5)))
        self.assertEqual(self.events, [])

    def test_click_return_value_semantics_unchanged(self):
        rule = RuleClick(ROI, ROI, 'stage1_ret')
        task = self._task([{}])
        with patch('tasks.base_task.Timer', _AlwaysReached):
            self.assertFalse(self._run(lambda: task.click(rule)))            # 无 interval：点了也返回 False
            self.assertTrue(self._run(lambda: task.click(rule, interval=1)))  # 设置并到达 interval：返回 True

    def test_two_consecutive_clicks_sample_independently(self):
        img = self._image()
        task = self._task([{img.name: ROI}])
        self._run(lambda: (task.appear_then_click(img), task.appear_then_click(img)))
        self.assertEqual((len(self.of('sample')), len(self.of('execute')), len(self.of('backend'))), (2, 2, 2))

    def test_backend_exception_propagates_without_a_second_attempt(self):
        img = self._image()
        task = self._task([{img.name: ROI}])
        self.backend.side_effect = OSError('device gone')
        with self.assertRaises(OSError):
            self._run(lambda: task.appear_then_click(img))
        self.assertEqual((len(self.of('sample')), len(self.of('execute'))), (1, 1))
        self.assertEqual(self.backend.call_count, 1)


# ======================================================================================
# 二、L2：reaction 之后才在新帧采样；目标消失零点击；策略校验不变
# ======================================================================================

class L2CompatibilityTest(ChainHarness):
    def test_normal_policy_samples_after_reaction_on_the_fresh_frame(self):
        img = self._image()
        moved = (700, 450, 120, 60)
        task = self._task([{img.name: ROI}, {img.name: moved}])
        self.assertTrue(self._run(lambda: task.appear_then_click(img, policy=InteractionPolicy.NORMAL)))
        self.assertEqual(self.kinds(), ['reaction', 'sleep', 'screenshot', 'sample', 'execute', 'backend'])
        self.assertEqual(self.of('sample')[0][1], moved)                # 旧框从未被采样，落点来自新帧
        self.assert_one_click_chain(moved, img.name)

    def test_target_gone_after_reaction_is_zero_click(self):
        img = self._image()
        task = self._task([{img.name: ROI}, {}])
        self.assertFalse(self._run(lambda: task.appear_then_click(img, policy=InteractionPolicy.CONFIRM)))
        for kind in ('sample', 'execute', 'backend'):
            self.assertEqual(self.of(kind), [])
        self.assertEqual(len(self.of('reaction')), 1)                    # reaction 只采样一次

    def test_immediate_policy_equals_legacy_call(self):
        for kwargs in ({}, {'policy': InteractionPolicy.IMMEDIATE}):
            with self.subTest(kwargs=kwargs):
                self.events.clear()
                img = self._image()
                task = self._task([{img.name: ROI}])
                self._run(lambda: task.appear_then_click(img, **kwargs))
                self.assertEqual(self.kinds(), ['sample', 'execute', 'backend'])

    def test_legacy_confirm_delay_still_samples_once(self):
        img = self._image()
        task = self._task([{img.name: ROI}, {img.name: ROI}])
        self._run(lambda: task.appear_then_click(img, confirm_delay=(0.2, 0.3)))
        self.assertEqual((len(self.of('reaction')), len(self.of('sample')), len(self.of('execute'))), (1, 1, 1))

    def test_policy_conflicts_are_rejected_before_any_side_effect(self):
        img = self._image()
        task = self._task([{img.name: ROI}])
        with self.assertRaises(ValueError):
            self._run(lambda: task.appear_then_click(img, policy=InteractionPolicy.NORMAL, confirm_delay=(0.1, 0.2)))
        for policy in (InteractionPolicy.FIRE_SPECIAL, InteractionPolicy.SPECIAL):
            with self.assertRaises(ValueError):
                self._run(lambda: task.appear_then_click(img, policy=policy))
        self.assertEqual(self.events, [])


# ======================================================================================
# 三、ocr_appear_click：无效重复采样已修复
# ======================================================================================

class OcrAppearClickTest(ChainHarness):
    def _ocr(self):
        return RuleOcr(name='stage1_ocr_click', mode='Single', method='Default', roi=ROI, area=ROI, keyword='')

    def test_without_action_one_sample_one_execute(self):
        ocr = self._ocr()
        task = self._task([{}])
        task.ocr_appear = Mock(return_value=True)
        self.assertTrue(self._run(lambda: task.ocr_appear_click(ocr)))
        self.assert_one_click_chain(ROI, ocr.name)

    def test_with_action_samples_exactly_once(self):
        ocr = self._ocr()
        action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage1_ocr_action')
        task = self._task([{}])
        task.ocr_appear = Mock(return_value=True)
        self.assertTrue(self._run(lambda: task.ocr_appear_click(action=action, target=ocr)))
        # 旧实现：`action.coord()` 采样后丢弃，`self.click(action)` 再采一次 = 2 次；现在只采一次
        self.assertEqual(len(self.of('sample')), 1)
        self.assert_one_click_chain(ACTION_ROI, action.name)          # 经 `self.click(action)`，control_name = action.name

    def test_with_action_and_interval_still_one_sample(self):
        ocr = self._ocr()
        action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage1_ocr_action2')
        task = self._task([{}])
        task.ocr_appear = Mock(return_value=True)
        with patch('tasks.base_task.Timer', _AlwaysReached):
            self.assertTrue(self._run(lambda: task.ocr_appear_click(ocr, action=action, interval=1)))
        self.assertEqual(len(self.of('sample')), 1)
        self.assertEqual(len(self.of('backend')), 1)

    def test_ocr_miss_never_clicks_and_never_samples(self):
        ocr = self._ocr()
        task = self._task([{}])
        task.ocr_appear = Mock(return_value=False)
        self.assertFalse(self._run(lambda: task.ocr_appear_click(ocr, action=RuleClick(ROI, ROI, 'x'))))
        self.assertFalse(self._run(lambda: task.ocr_appear_click(ocr)))
        self.assertEqual(self.events, [])


# ======================================================================================
# 四、wait_until_appear_then_click / 长按 / ui_* helper
# ======================================================================================

class OtherPrimitivesTest(ChainHarness):
    def test_wait_until_appear_then_click_keeps_its_legacy_semantics(self):
        # 无生产调用方；保持原语义：无论有无 RuleClick action，落点都来自 target.coord()，control_name = target.name
        img = self._image()
        action = RuleClick(ACTION_ROI, ACTION_ROI, 'stage1_wait_action')
        for act in (None, action):
            with self.subTest(action=act):
                self.fresh()
                task = self._task([{img.name: ROI}])
                task.wait_until_appear = Mock(return_value=True)
                self.assertTrue(self._run(lambda: task.wait_until_appear_then_click(img, action=act)))
                self.assert_one_click_chain(ROI, img.name)

    def test_long_click_paths_are_untouched(self):
        long_rule = RuleLongClick(ACTION_ROI, ACTION_ROI, 1500, 'stage1_long')
        img = self._image()
        task = self._task([{img.name: ROI}])
        self._run(lambda: task.click(long_rule))
        self._run(lambda: task.appear_then_click(img, action=long_rule))
        self.assertEqual(self.of('execute'), [])                        # 长按永远不进单击执行器（走独立的长按执行器）
        self.assertEqual(self.long_backend.call_count, 2)
        self.assertEqual(self.backend.call_count, 0)

    def test_ui_click_until_disappear_goes_through_the_executor_once_per_click(self):
        img = self._image()
        task = self._task([{}, {img.name: ROI}, {}])
        self._run(lambda: task.ui_click_until_disappear(img, interval=0.01))
        self.assert_one_click_chain(ROI, img.name)

    def test_ui_click_with_a_rule_click_goes_through_the_executor(self):
        rule = RuleClick(ROI, ROI, 'stage1_ui_click')
        stop = self._image('stage1_stop', ACTION_ROI)
        task = self._task([{}, {}, {stop.name: ACTION_ROI}])
        with patch('tasks.base_task.Timer', _AlwaysReached):
            self._run(lambda: task.ui_click(rule, stop, interval=1))
        self.assert_one_click_chain(ROI, rule.name)


# ======================================================================================
# 五、静态守卫：BaseTask 不再有直接 device.click；新执行点都以 FinalPoint 交给执行器
# ======================================================================================

def _base_task_functions():
    text = (_REPO / 'tasks' / 'base_task.py').read_text(encoding='utf-8')
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BaseTask')
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _calls(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            yield n


def _is_attr_call(call, chain_suffix):
    func = call.func
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return '.'.join(reversed(parts)).endswith(chain_suffix)


class BaseTaskStaticGuardTest(TestCase):
    PRIMITIVES = ('appear_then_click', 'wait_until_appear_then_click', 'click', 'ocr_appear_click')

    def test_no_direct_device_click_left_in_base_task(self):
        for name, fn in _base_task_functions().items():
            with self.subTest(func=name):
                self.assertEqual([c.lineno for c in _calls(fn) if _is_attr_call(c, 'device.click')], [])

    def test_the_eight_execution_points_pass_a_final_point(self):
        expected = {'appear_then_click': 4, 'wait_until_appear_then_click': 2, 'click': 1, 'ocr_appear_click': 1}
        funcs = _base_task_functions()
        for name, count in expected.items():
            calls = [c for c in _calls(funcs[name]) if isinstance(c.func, ast.Name) and c.func.id == 'execute_single_click']
            with self.subTest(func=name):
                self.assertEqual(len(calls), count)
                for call in calls:
                    first = call.args[1]                                 # (device, target, ...)
                    self.assertIsInstance(first, ast.Call)
                    self.assertEqual(getattr(first.func, 'id', None), 'FinalPoint')   # 不是「把 Rule 直接交给执行器」
                    self.assertTrue(any(kw.arg == 'control_name' for kw in call.keywords))

    def test_list_appear_click_keeps_its_existing_executor_call(self):
        calls = [c for c in _calls(_base_task_functions()['list_appear_click'])
                 if isinstance(c.func, ast.Name) and c.func.id == 'execute_single_click']
        self.assertEqual(len(calls), 1)

    def test_long_click_execution_points_moved_to_the_long_click_executor(self):
        # Stage 3A：6 个长按点位不再直调 device.long_click，全部经 execute_long_click（详细守卫见 stage3a 测试）
        funcs = _base_task_functions()
        direct = sum(1 for fn in funcs.values() for c in _calls(fn) if _is_attr_call(c, 'device.long_click'))
        via_executor = sum(1 for fn in funcs.values() for c in _calls(fn)
                           if isinstance(c.func, ast.Name) and c.func.id == 'execute_long_click')
        self.assertEqual((direct, via_executor), (0, 6))

    def test_ocr_appear_click_has_exactly_one_coord_call(self):
        fn = _base_task_functions()['ocr_appear_click']
        self.assertEqual([c for c in _calls(fn) if isinstance(c.func, ast.Attribute) and c.func.attr == 'coord'].__len__(), 1)
