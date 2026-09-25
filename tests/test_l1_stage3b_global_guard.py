# This Python file uses the following encoding: utf-8
"""L1 Stage 3B：原项目排除模块的最后 3 处直接单击迁入 L1，并建立全局静态守卫。

一、三个调用点的运行期等价（真实业务方法 + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace）
   - WeeklyPurchase `MallNavbar.click_and_check`：`pos` 是 `list_find` 已采样的最终坐标 → `FinalPoint`，
     不重新识别 / 采样；重复点击同一个坐标（原逻辑就是同一个 `pos` 最多点 6 次）。
   - DailyTrifles `ScriptTask.summon_recall`：`RuleOcr.coord()` 每次点击恰采样一次 → `FinalPoint`；
     原写法没传 control_name（Control 默认 'Click'），迁移后保持不传。
   - Login `LoginService._app_handle_login`：固定坐标 (106, 535) → `FinalPoint`，不随机、不猜 ROI、不新增截图。
   参考值是「迁移前的表达式」（`coord()` 的固定随机源结果、原坐标字面量、原 control_name），不是迁移后代码自己算的。
二、全局静态守卫（`dev_tools/click_entry_guard.py`）：默认禁止生产直接点击 / 长按；白名单精确到（文件, 函数,
   调用形式, 次数）；过期白名单与缺失的必需出口同样失败；对真实生产文件做 rglob，新增文件天然被扫描。
   静态守卫只证明「没有绕过执行器的直接调用」，不证明业务点击一定成功，也不证明坐标分布——
   后者由本文件的运行期用例与 Stage 1 / 2 / 3A 的等价性测试负责。
"""

import json
import random
import tempfile
import textwrap
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np

from dev_tools import click_callsite_register as reg
from dev_tools import click_entry_guard as guard
from module import behavior_trace
from module.atom.long_click import RuleLongClick
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import FinalPoint, execute_long_click, execute_single_click
from module.click_sampler import ClickSampler
from module.device.control import Control

_REPO = Path(__file__).resolve().parents[1]
SEED = 20260921
METHODS = ('minitouch', 'ADB', 'uiautomator2', 'window_message')


@contextmanager
def seeded(seed=SEED):
    rng = random.Random(seed)
    with patch('module.click_sampler._rng', rng), patch('module.base.utils.random._rng', rng):
        yield


class _Stop(Exception):
    """截断被测流程的哨兵：测试只关心点击发生之前 / 之时的行为。"""


# ======================================================================================
# 一、三个调用点的运行期等价
# ======================================================================================

class SiteHarness(TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.addCleanup(self._restore)                             # cleanup 后进先出：先 reset（关文件句柄）再删目录
        self.addCleanup(reset_behavior_traces)
        configure_behavior_trace('stage3b', enabled=True)
        self.events = []

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    def control(self, method='minitouch'):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(config_name='stage3b', script=SimpleNamespace(device=SimpleNamespace(control_method=method)))
        self.click_backends = {m: Mock(name=f'click_{m}', side_effect=lambda x, y, _m=m: self.events.append(('backend', _m, x, y)))
                               for m in METHODS}
        self.long_backends = {m: Mock(name=f'long_{m}') for m in METHODS}
        c.click_methods = self.click_backends
        c.long_click_methods = self.long_backends
        c.click_adb = Mock(name='click_adb', side_effect=lambda x, y: self.events.append(('backend', 'adb-fallback', x, y)))
        c.image = 'F'
        return c

    def trace_rows(self):
        files = list(behavior_trace._LOG_DIR.glob('stage3b_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []

    def backend_calls(self):
        return [e for e in self.events if e[0] == 'backend']

    def no_sampling(self):
        """把所有空间采样函数换成「一调用就失败」：已采样坐标的点位不得再采样。"""
        return [patch.object(ClickSampler, name, side_effect=AssertionError(f'不应再采样：{name}'))
                for name in ('sample_target', 'sample_region', 'sample_point')]


class _AlwaysReached:
    """`Timer` 替身：`started()` 恒 False → 每次循环都放行点击，避免真等时间。"""

    def __init__(self, *a, **k):
        pass

    def started(self):
        return False

    def reached(self):
        return True

    def reset(self):
        return self

    def start(self):
        return self


# ---- WeeklyPurchase ----------------------------------------------------------------

class WeeklyPurchaseNavbarTest(SiteHarness):
    def _fake(self, appear_after, method='minitouch'):
        """`appear_after`：第几次截图之后目标出现（None = 一直不出现）。"""
        state = {'shots': 0}
        events = self.events

        def screenshot():
            state['shots'] += 1
            events.append(('screenshot', state['shots']))

        def appear(rule):
            events.append(('appear', rule))
            return appear_after is not None and state['shots'] >= appear_after

        return SimpleNamespace(screenshot=screenshot, appear=appear, device=self.control(method))

    def _run(self, fake, pos, name='RM_NAVBAR_MEDAL'):
        from tasks.WeeklyPurchase.mall.navbar import MallNavbar
        with patch('tasks.WeeklyPurchase.mall.navbar.Timer', _AlwaysReached):
            return MallNavbar.click_and_check(fake, pos, name, 'CHECK')

    def test_found_click_uses_the_list_find_point_verbatim_without_resampling(self):
        pos = (1213, 344)                                          # list_find 已采样的最终坐标
        fake = self._fake(appear_after=2)
        patches = self.no_sampling()
        for p in patches:
            p.start()
        try:
            result = self._run(fake, pos)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result)
        self.assertEqual(self.backend_calls(), [('backend', 'minitouch', 1213, 344)])       # 迁移前：点一次 (pos[0], pos[1])
        self.assertEqual([e for e in self.events if e[0] == 'screenshot'], [('screenshot', 1), ('screenshot', 2)])
        self.assertEqual([(r['action'], r['target'], r['extra']) for r in self.trace_rows()],
                         [('click', 'RM_NAVBAR_MEDAL', {'x': 1213, 'y': 344})])              # control_name 逐值保留

    def test_already_visible_means_zero_clicks(self):
        fake = self._fake(appear_after=1)
        self.assertTrue(self._run(fake, (1213, 344)))
        self.assertEqual(self.backend_calls(), [])

    def test_never_appearing_clicks_the_same_point_six_times_then_returns_false(self):
        fake = self._fake(appear_after=None)
        self.assertFalse(self._run(fake, (1213, 344)))
        # 原逻辑：max_click_cnt 从 5 减到 -1，同一个 pos 最多点 6 次；坐标不重新采样，也不换点
        self.assertEqual(self.backend_calls(), [('backend', 'minitouch', 1213, 344)] * 6)
        self.assertEqual(len([e for e in self.events if e[0] == 'screenshot']), 6)
        self.assertEqual(len(self.trace_rows()), 6)

    def test_list_find_miss_returns_false_without_any_click_or_screenshot(self):
        for pos in (False, None, ()):
            with self.subTest(pos=pos):
                self.events.clear()
                fake = self._fake(appear_after=1)
                self.assertFalse(self._run(fake, pos))
                self.assertEqual(self.events, [])

    def test_enter_special_with_a_list_find_miss_does_not_click(self):
        from tasks.WeeklyPurchase.mall.navbar import MallNavbar
        fake = self._fake(appear_after=1)
        fake.L_RM_NAVBAR = object()
        fake.I_SIDE_CHECK_SPECIAL = 'CHECK'
        fake._enter_sundry = Mock()
        fake.list_find = Mock(return_value=False)
        fake.click_and_check = lambda *a: MallNavbar.click_and_check(fake, *a)
        self.assertFalse(MallNavbar._enter_special(fake))
        self.assertEqual(self.backend_calls(), [])
        fake.list_find.assert_called_once()

    def test_numpy_and_float_coordinates_are_truncated_like_control_did(self):
        for pos in ((np.int64(1213), np.int64(344)), (1213.9, 344.4), [1213, 344]):
            with self.subTest(pos=pos):
                self.events.clear()
                fake = self._fake(appear_after=2)
                self.assertTrue(self._run(fake, pos))
                self.assertEqual(self.backend_calls(), [('backend', 'minitouch', 1213, 344)])

    def test_backend_exception_propagates_without_a_second_attempt(self):
        fake = self._fake(appear_after=None)
        fake.device.click_methods['minitouch'].side_effect = OSError('device gone')
        with self.assertRaises(OSError):
            self._run(fake, (1213, 344))
        self.assertEqual(fake.device.click_methods['minitouch'].call_count, 1)

    def test_every_backend_receives_the_same_point(self):
        for method in METHODS:
            with self.subTest(method=method):
                self.events.clear()
                fake = self._fake(appear_after=2, method=method)
                self._run(fake, (1213, 344))
                self.assertEqual(self.backend_calls(), [('backend', method, 1213, 344)])


# ---- DailyTrifles ------------------------------------------------------------------

class DailyTriflesSummonRecallTest(SiteHarness):
    def _fake(self, appear_from_click=None):
        """`appear_from_click`：第 N 次点击之后 `I_RECALL_TICKET` 出现（None = 一直不出现）。"""
        from tasks.DailyTrifles.assets import DailyTriflesAssets as A
        events = self.events
        fake = SimpleNamespace(
            O_SELECT_SM2=A.O_SELECT_SM2, O_SELECT_SM3=A.O_SELECT_SM3, O_SELECT_SM4=A.O_SELECT_SM4,
            I_UI_BACK_RED='BACK', I_RECALL_TICKET='TICKET',
            goto_page=Mock(side_effect=lambda page: events.append(('goto', page))),
            appear_then_click=Mock(side_effect=lambda *a, **k: events.append(('atc',)) or False),
            screenshot=Mock(side_effect=lambda: events.append(('screenshot',))),
            config=SimpleNamespace(notifier=SimpleNamespace(push=Mock(side_effect=lambda **k: events.append(('push', k['title']))))),
            device=self.control())
        fake.appear = Mock(side_effect=lambda rule: (
            appear_from_click is not None and len(self.backend_calls()) >= appear_from_click))
        fake.wait_until_appear = Mock(side_effect=_Stop)           # 点击阶段之后的流程不在本测试范围
        return fake

    def _reference(self, count):
        """迁移前的表达式：三个 OCR 目标各自 `coord()` 采样一次，按 2 → 3 → 4 循环。"""
        from tasks.DailyTrifles.assets import DailyTriflesAssets as A
        rules = [A.O_SELECT_SM2, A.O_SELECT_SM3, A.O_SELECT_SM4]
        with seeded():
            return [tuple(int(v) for v in rules[i % 3].coord()) for i in range(count)]

    def _run(self, fake):
        from tasks.DailyTrifles import script_task
        with seeded(), patch.object(script_task, 'sleep', side_effect=lambda s: self.events.append(('sleep', s))):
            try:
                return script_task.ScriptTask.summon_recall(fake)
            except _Stop:
                return 'stopped'

    def test_ocr_hit_after_first_click_clicks_once_with_the_coord_sample(self):
        fake = self._fake(appear_from_click=1)
        self.assertEqual(self._run(fake), 'stopped')
        expected = self._reference(1)
        self.assertEqual([(x, y) for _, _, x, y in self.backend_calls()], expected)
        self.assertEqual([(r['action'], r['target']) for r in self.trace_rows()], [('click', 'Click')])   # 原写法未传 control_name
        self.assertEqual((self.trace_rows()[0]['extra']['x'], self.trace_rows()[0]['extra']['y']), expected[0])

    def test_never_hit_clicks_three_presets_per_round_for_three_rounds(self):
        fake = self._fake(appear_from_click=None)
        self.assertIsNone(self._run(fake))
        self.assertEqual([(x, y) for _, _, x, y in self.backend_calls()], self._reference(9))
        # 采样 / 点击 / 等待 / 截图次数：9 次点击各 sleep 两次、截图一次，每轮末尾再截图一次
        self.assertEqual(len([e for e in self.events if e[0] == 'sleep']), 18)
        self.assertEqual(len([e for e in self.events if e[0] == 'screenshot']), 12)
        self.assertEqual([e for e in self.events if e[0] == 'push'], [('push', '今忆召唤抽卡失败')])
        self.assertTrue(all(r['target'] == 'Click' for r in self.trace_rows()))

    def test_each_click_samples_the_ocr_target_exactly_once_and_never_again(self):
        fake = self._fake(appear_from_click=None)
        calls = []
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            calls.append(name)
            return original(roi, name, *a, **k)

        with patch.object(ClickSampler, 'sample_target', side_effect=counted):
            self._run(fake)
        self.assertEqual(calls, ['SELECT_SM2', 'SELECT_SM3', 'SELECT_SM4'] * 3)        # 9 次点击 = 9 次采样，无多余

    def test_ocr_module_is_not_invoked_by_the_click_migration(self):
        fake = self._fake(appear_from_click=None)
        with patch('module.atom.ocr.RuleOcr.ocr', side_effect=AssertionError('点击不应触发 OCR 识别')):
            self._run(fake)

    def test_no_click_at_origin(self):
        fake = self._fake(appear_from_click=None)
        self._run(fake)
        self.assertNotIn((0, 0), [(x, y) for _, _, x, y in self.backend_calls()])

    def test_backend_exception_propagates_without_retry(self):
        fake = self._fake(appear_from_click=None)
        fake.device.click_methods['minitouch'].side_effect = OSError('device gone')
        with self.assertRaises(OSError):
            self._run(fake)
        self.assertEqual(fake.device.click_methods['minitouch'].call_count, 1)


# ---- Login -------------------------------------------------------------------------

class _LoginFake:
    """`LoginService._app_handle_login` 的最小替身：第 1 轮只有 I_CHARACTARS 出现（误入区服设置），第 2 轮 Chess 大厅出现即返回。"""

    def __init__(self, control, events):
        self.device = control
        self.device.stuck_record_add = Mock()
        self.device.get_orientation = Mock()
        self.events = events
        self.round = 0
        self.screenshots = 0

    def __getattr__(self, name):
        if name[:2] in ('I_', 'O_', 'C_'):
            return SimpleNamespace(name=name)
        raise AttributeError(name)

    def screenshot(self):
        self.round += 1
        self.screenshots += 1
        self.events.append(('screenshot', self.round))

    def appear(self, target, interval=None, threshold=None):
        name = target.name
        if self.round == 1:
            return name == 'I_CHARACTARS'
        return name == 'I_CHECK_CHESS'

    def appear_then_click(self, *a, **k):
        return False

    def ocr_appear_click(self, *a, **k):
        return False

    def click(self, *a, **k):
        raise AssertionError('本场景不应走到 BaseTask.click')

    def chess_result_flow_visible(self):
        return False


class LoginFixedClickTest(SiteHarness):
    def _run(self, fake):
        from tasks.Component.Login import service
        with patch.object(service, 'Timer', _AlwaysReached), patch.object(service, 'logger'):
            return service.LoginService._app_handle_login(fake)

    def test_wrong_server_setting_clicks_the_fixed_point_verbatim(self):
        fake = _LoginFake(self.control(), self.events)
        patches = self.no_sampling()
        for p in patches:
            p.start()
        try:
            result = self._run(fake)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result)                                    # 返回值语义不变：Chess 大厅出现即 True
        self.assertEqual(self.backend_calls(), [('backend', 'minitouch', 106, 535)])   # 固定坐标，不随机、不猜 ROI
        self.assertEqual([(r['action'], r['target'], r['extra']) for r in self.trace_rows()],
                         [('click', 'Click', {'x': 106, 'y': 535})])                   # 原写法未传 control_name
        self.assertEqual(fake.screenshots, 2)                      # 没有新增截图

    def test_the_fixed_point_is_identical_on_every_backend(self):
        for method in METHODS:
            with self.subTest(method=method):
                self.events.clear()
                self._run(_LoginFake(self.control(method), self.events))
                self.assertEqual(self.backend_calls(), [('backend', method, 106, 535)])

    def test_backend_exception_propagates_out_of_the_login_flow(self):
        fake = _LoginFake(self.control(), self.events)
        fake.device.click_methods['minitouch'].side_effect = OSError('device gone')
        with self.assertRaises(OSError):
            self._run(fake)
        self.assertEqual(fake.device.click_methods['minitouch'].call_count, 1)
        self.assertEqual(fake.screenshots, 1)

    def test_no_real_login_or_device_is_touched(self):
        fake = _LoginFake(self.control(), self.events)
        self._run(fake)
        self.assertFalse(hasattr(fake.device, 'app_start') and getattr(fake.device, 'app_start').called)


# ======================================================================================
# 二、全局不变量总检（运行期，不依赖静态扫描）
# ======================================================================================

class GlobalInvariantTest(SiteHarness):
    def test_control_layer_never_samples_or_jitters(self):
        c = self.control()
        with patch.object(ClickSampler, 'sample_target', side_effect=AssertionError), \
                patch.object(ClickSampler, 'sample_region', side_effect=AssertionError), \
                patch.object(ClickSampler, 'sample_point', side_effect=AssertionError):
            execute_single_click(c, FinalPoint(10, 20), control_name='a')
            execute_long_click(c, FinalPoint(30, 40), 1.5, control_name='b')
        self.assertEqual(self.backend_calls(), [('backend', 'minitouch', 10, 20)])
        c.long_click_methods['minitouch'].assert_called_once_with(30, 40, 1.5)

    def test_single_and_long_executors_do_not_cross(self):
        long_rule = RuleLongClick((0, 0, 10, 10), (0, 0, 10, 10), 800, 'lc')
        with self.assertRaises(TypeError):
            execute_single_click(SimpleNamespace(click=Mock()), long_rule)
        dev = SimpleNamespace(click=Mock(), long_click=Mock())
        execute_long_click(dev, FinalPoint(1, 2), 1.0)
        dev.click.assert_not_called()
        execute_single_click(dev, FinalPoint(1, 2))
        self.assertEqual(dev.long_click.call_count, 1)

    def test_rule_target_is_sampled_once_and_final_point_zero_times(self):
        from module.atom.click import RuleClick
        calls = []
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            calls.append(name)
            return original(roi, name, *a, **k)

        dev = SimpleNamespace(click=Mock())
        with patch.object(ClickSampler, 'sample_target', side_effect=counted):
            execute_single_click(dev, RuleClick((100, 100, 50, 50), (100, 100, 50, 50), 'r'))
            execute_single_click(dev, FinalPoint(5, 6))
        self.assertEqual(calls, ['r'])


# ======================================================================================
# 三、静态守卫
# ======================================================================================

_REAL_SCAN = []


def real_scan():
    """真实仓库只扫描一次（每次约 1 秒），各用例共享；evaluate 是纯函数，不会污染缓存。"""
    if not _REAL_SCAN:
        _REAL_SCAN.append(guard.scan_repo())
    return _REAL_SCAN[0]


def _scan(rel, source):
    violations, unresolved = guard.scan_source(rel, textwrap.dedent(source))
    return guard.evaluate(violations, unresolved, allowed=(), required=())


class GuardOnTheRealRepositoryTest(TestCase):
    def test_current_master_has_no_unregistered_direct_click_or_long_click(self):
        result = guard.evaluate(*real_scan())
        self.assertTrue(result.ok, '生产代码出现绕过 L1 执行器的直接点击 / 长按（必须迁移，不得靠加白名单消除）：\n' + result.render())
        self.assertEqual(result.unresolved, [])

    def test_the_three_former_exclusions_have_no_exemption_and_no_direct_click(self):
        violations, _ = real_scan()
        for rel in ('tasks/Component/Login/service.py', 'tasks/DailyTrifles/script_task.py',
                    'tasks/WeeklyPurchase/mall/navbar.py'):
            with self.subTest(file=rel):
                self.assertEqual([v for v in violations if v.file == rel], [])
                self.assertFalse([e for e in guard.ALLOWED_EXITS if e.file == rel])
        for prefix in ('tasks/Component/Login', 'tasks/DailyTrifles', 'tasks/WeeklyPurchase'):
            self.assertFalse([e for e in guard.ALLOWED_EXITS if e.file.startswith(prefix)])

    def test_every_allowed_exit_is_specific_and_explained(self):
        allowed_files = {e.file for e in guard.ALLOWED_EXITS}
        self.assertEqual(allowed_files, {'module/click_pipeline.py', 'module/device/control.py',
                                         'module/device/method/uiautomator_2.py', 'module/device/method/windows_impl.py',
                                         'module/device/method/minitouch.py'})
        for e in guard.ALLOWED_EXITS:
            with self.subTest(exit=(e.file, e.func, e.form)):
                self.assertTrue(e.reason and e.layer and e.func and e.form)
                self.assertNotIn('*', e.file + e.func + e.form)
                self.assertGreaterEqual(e.count, 1)
        self.assertEqual({e.layer for e in guard.ALLOWED_EXITS}, {'executor', 'control', 'backend', 'demo', 'dead'})

    def test_executor_exits_are_pinned_to_their_functions(self):
        executor_exits = {(e.func, e.form) for e in guard.ALLOWED_EXITS if e.layer == 'executor'}
        self.assertEqual(executor_exits, {('execute_single_click', 'device.click'),
                                          ('execute_single_click', 'device.click_with_backend'),
                                          ('execute_long_click', 'device.long_click')})

    def test_scan_covers_real_files_not_a_register(self):
        files = guard.production_files()
        for rel in ('tasks/base_task.py', 'module/click_pipeline.py', 'tasks/Component/Login/service.py',
                    'tasks/WeeklyPurchase/mall/navbar.py', 'script.py', 'server.py'):
            self.assertIn(rel, files)
        self.assertGreater(len(files), 400)
        self.assertFalse([f for f in files if f.startswith(('tests/', 'dev_tools/', 'toolkit/'))])

    def test_every_top_level_directory_with_python_is_classified(self):
        self.assertEqual(guard.unclassified_roots(), [])

    def test_drag_and_swipe_code_is_not_mistaken_for_a_click(self):
        for rel in ('tasks/Chess/runtime/press_and_drag.py', 'tasks/Hyakkiyakou/slave/hya_device.py'):
            with self.subTest(file=rel):
                v, u = guard.scan_source(rel, (_REPO / rel).read_text(encoding='utf-8'))
                self.assertEqual((v, u), ([], []))

    def test_real_control_and_backend_dispatch_are_not_reported(self):
        for rel in ('module/device/control.py', 'module/device/method/uiautomator_2.py', 'module/device/method/windows_impl.py',
                    'module/device/method/minitouch.py', 'module/click_pipeline.py'):
            with self.subTest(file=rel):
                v, u = guard.scan_source(rel, (_REPO / rel).read_text(encoding='utf-8'))
                result = guard.evaluate(v, u, allowed=tuple(e for e in guard.ALLOWED_EXITS if e.file == rel), required=())
                self.assertEqual(result.unallowed, [])
                self.assertEqual(result.stale, [])


class GuardDetectsViolationsTest(TestCase):
    def assertViolates(self, rel, source, form=None):
        result = _scan(rel, source)
        self.assertTrue(result.unallowed, f'守卫没有发现违规：{rel}')
        if form:
            self.assertIn(form, [v.form for v in result.unallowed])
        return result

    def test_direct_device_click_in_an_ordinary_task(self):
        r = self.assertViolates('tasks/NewTask/script_task.py', """
            class NewTask:
                def run(self):
                    self.device.click(x=1, y=2, control_name='x')
        """, 'self.device.click')
        v = r.unallowed[0]
        self.assertEqual((v.file, v.func, v.kind), ('tasks/NewTask/script_task.py', 'NewTask.run', 'call'))
        self.assertIn('execute_single_click', v.suggestion)
        text = r.render()
        self.assertIn('tasks/NewTask/script_task.py:', text)
        self.assertIn('NewTask.run', text)
        self.assertIn('self.device.click', text)

    def test_direct_device_long_click_in_an_ordinary_task(self):
        r = self.assertViolates('tasks/NewTask/script_task.py', """
            class NewTask:
                def run(self):
                    self.device.long_click(1, 2, 1.5, 'x')
        """, 'self.device.long_click')
        self.assertIn('execute_long_click', r.unallowed[0].suggestion)

    def test_component_calling_control_directly(self):
        self.assertViolates('tasks/Component/Foo/foo.py', """
            from module.device.control import Control
            class Foo:
                def run(self):
                    Control.click(self.device, 1, 2)
        """, 'Control.click')

    def test_device_alias_is_followed(self):
        self.assertViolates('tasks/NewTask/script_task.py', """
            class NewTask:
                def run(self):
                    dev = self.device
                    other = dev
                    other.click(1, 2)
        """, 'other.click')

    def test_device_parameter_is_a_device(self):
        self.assertViolates('tasks/NewTask/helpers.py', """
            def tap(device, x, y):
                device.click(x, y)
        """, 'device.click')

    def test_click_with_backend_outside_the_executor(self):
        self.assertViolates('tasks/Hyakkiyakou/slave/x.py', """
            def fast(self):
                self.device.click_with_backend(x=1, y=2, backend='minitouch')
        """, 'self.device.click_with_backend')

    def test_backend_method_called_directly_from_a_task(self):
        for name in ('click_minitouch', 'click_window_message', 'click_adb', 'long_click_minitouch', 'click_uiautomator2'):
            with self.subTest(name=name):
                self.assertViolates('tasks/NewTask/script_task.py', f"""
                    class T:
                        def run(self):
                            self.{name}(1, 2)
                """, f'self.{name}')

    def test_reference_without_a_call_is_an_alias_of_the_entry(self):
        self.assertViolates('tasks/NewTask/script_task.py', """
            from functools import partial
            class T:
                def run(self):
                    tap = self.device.click
                    later = partial(self.device.long_click, 1, 2)
        """)

    def test_getattr_with_a_literal_name(self):
        self.assertViolates('tasks/NewTask/script_task.py', """
            class T:
                def run(self):
                    getattr(self.device, 'click')(1, 2)
        """)

    def test_dynamic_getattr_is_reported_as_unresolved_not_ignored(self):
        result = _scan('tasks/NewTask/script_task.py', """
            class T:
                def run(self, name):
                    getattr(self.device, name)(1, 2)
        """)
        self.assertEqual([u.kind for u in result.unresolved], ['dynamic'])
        self.assertFalse(result.ok)

    def test_former_exclusions_are_not_exempt_by_path(self):
        cases = {
            'tasks/Component/Login/service.py': "class LoginService:\n    def _app_handle_login(self):\n        self.device.click(x=106, y=535)\n",
            'tasks/DailyTrifles/script_task.py': "class ScriptTask:\n    def summon_recall(self):\n        x, y = self.O.coord()\n        self.device.click(x, y)\n",
            'tasks/WeeklyPurchase/mall/navbar.py': "class MallNavbar:\n    def click_and_check(self, pos):\n        self.device.click(x=pos[0], y=pos[1])\n",
        }
        for rel, source in cases.items():
            with self.subTest(file=rel):
                real = (_REPO / rel).read_text(encoding='utf-8')
                # 直接用真实文件对照：真实文件是干净的；恢复裸点的版本必须失败
                clean, _ = guard.scan_source(rel, real)
                self.assertEqual(clean, [])
                self.assertViolates(rel, source, 'self.device.click')

    def test_legitimate_l1_calls_and_business_methods_are_not_flagged(self):
        result = _scan('tasks/NewTask/script_task.py', """
            from module.click_pipeline import FinalPoint, execute_single_click, execute_long_click
            class T:
                def run(self, button):
                    execute_single_click(self.device, FinalPoint(1, 2), control_name='a')
                    execute_long_click(self.device, FinalPoint(1, 2), 1.5, control_name='b')
                    self.click(self.C_X)
                    self.click_and_check((1, 2), 'n', None)
                    self.click_battle()
                    self.device.click_record_clear()
                    self.device.click_record_remove('x')
                    self.device.screenshot()
                    self.device.swipe((1, 2), (3, 4))
                    self.device.minitouch_builder.down(1, 2)
                    button.click()                       # 与设备无关的对象
                    self.appear_then_click(self.I_A)
        """)
        self.assertEqual(result.unallowed, [])
        self.assertEqual(result.unresolved, [])

    def test_click_inside_a_string_or_comment_is_not_flagged(self):
        result = _scan('tasks/NewTask/script_task.py', """
            class T:
                def run(self):
                    '''self.device.click(1, 2)'''
                    # self.device.long_click(1, 2)
                    text = "self.device.click(x=1, y=2)"
        """)
        self.assertEqual(result.unallowed, [])

    def test_whitelist_is_function_scoped_not_file_scoped(self):
        rel = 'module/click_pipeline.py'
        source = (_REPO / rel).read_text(encoding='utf-8') + textwrap.dedent("""

            def sneaky(device):
                device.click(x=1, y=2)
        """)
        v, u = guard.scan_source(rel, source)
        result = guard.evaluate(v, u, allowed=tuple(e for e in guard.ALLOWED_EXITS if e.file == rel), required=())
        self.assertEqual([x.func for x in result.unallowed], ['sneaky'])

    def test_whitelist_count_is_exact(self):
        rel = 'module/click_pipeline.py'
        source = (_REPO / rel).read_text(encoding='utf-8').replace(
            "        device.click(x=x, y=y, control_name=name)\n",
            "        device.click(x=x, y=y, control_name=name)\n        device.click(x=x, y=y, control_name=name)\n")
        self.assertNotEqual(source, (_REPO / rel).read_text(encoding='utf-8'))
        v, u = guard.scan_source(rel, source)
        result = guard.evaluate(v, u, allowed=tuple(e for e in guard.ALLOWED_EXITS if e.file == rel), required=())
        self.assertEqual([x.func for x in result.unallowed], ['execute_single_click'])

    def test_test_code_and_fake_devices_are_not_production(self):
        files = guard.production_files()
        self.assertNotIn('tests/test_l1_stage3b_global_guard.py', files)
        self.assertNotIn('dev_tools/click_entry_guard.py', files)

    def test_long_and_single_suggestions_are_not_confused(self):
        single = _scan('tasks/A/a.py', "class A:\n    def f(self):\n        self.device.click(1, 2)\n").unallowed[0]
        long_ = _scan('tasks/A/a.py', "class A:\n    def f(self):\n        self.device.long_click(1, 2)\n").unallowed[0]
        self.assertIn('execute_single_click', single.suggestion)
        self.assertNotIn('execute_long_click', single.suggestion)
        self.assertIn('execute_long_click', long_.suggestion)


class GuardDiscoveryAndCompletenessTest(TestCase):
    def _fake_repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'tasks' / 'BrandNew').mkdir(parents=True)
        (root / 'tasks' / 'BrandNew' / 'script_task.py').write_text(
            'class T:\n    def run(self):\n        self.device.click(x=1, y=2)\n', encoding='utf-8')
        (root / 'module').mkdir()
        (root / 'module' / 'ok.py').write_text('x = 1\n', encoding='utf-8')
        return root

    def test_a_brand_new_unregistered_production_file_is_scanned(self):
        root = self._fake_repo()
        violations, _ = guard.scan_repo(root)
        self.assertEqual([(v.file, v.func) for v in violations], [('tasks/BrandNew/script_task.py', 'T.run')])
        result = guard.evaluate(violations, (), allowed=guard.ALLOWED_EXITS, required=())
        self.assertEqual([v.file for v in result.unallowed], ['tasks/BrandNew/script_task.py'])

    def test_a_new_top_level_python_directory_must_be_classified(self):
        root = self._fake_repo()
        (root / 'newprod').mkdir()
        (root / 'newprod' / 'run.py').write_text('x = 1\n', encoding='utf-8')
        self.assertEqual(guard.unclassified_roots(root), ['newprod'])

    def test_a_new_root_level_script_is_scanned(self):
        root = self._fake_repo()
        (root / 'newscript.py').write_text('def f(device):\n    device.click(1, 2)\n', encoding='utf-8')
        violations, _ = guard.scan_repo(root)
        self.assertIn('newscript.py', {v.file for v in violations})

    def test_removing_a_legitimate_executor_exit_is_not_reported_as_complete(self):
        violations, unresolved = real_scan()
        without = [v for v in violations if not (v.func == 'execute_long_click' and v.form == 'device.long_click')]
        result = guard.evaluate(without, unresolved)
        self.assertFalse(result.ok)
        self.assertTrue([e for e in result.stale if e.func == 'execute_long_click'])
        self.assertIn(('module/click_pipeline.py', 'execute_long_click', 'device.long_click'), result.missing_required)

    def test_a_stale_whitelist_entry_fails(self):
        violations, unresolved = real_scan()
        stale_entry = guard.AllowedExit('tasks/Gone/gone.py', 'Gone.run', 'self.device.click', 'call', 1, 'dead', '不存在')
        result = guard.evaluate(violations, unresolved, allowed=guard.ALLOWED_EXITS + (stale_entry,))
        self.assertEqual(result.stale, [stale_entry])
        self.assertFalse(result.ok)

    def test_static_guard_does_not_prove_execution_so_the_runtime_chain_is_tested_separately(self):
        # 静态守卫通过 ≠ 点击一定执行：执行器出口存在时，真实 Control 链路仍要由运行期用例验证
        self.assertTrue(guard.evaluate(*real_scan()).ok)
        c = Control.__new__(Control)
        c.config = SimpleNamespace(config_name='stage3b_unused', script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        backend = Mock()
        c.click_methods = {'minitouch': backend}
        execute_single_click(c, FinalPoint(3, 4), control_name='chain')
        backend.assert_called_once_with(3, 4)


class RegisterCoverageTest(TestCase):
    def test_stage_3b_coverage_numbers(self):
        sites = reg.classify_all(reg.scan_sites(), reg.load_audited_rows())
        summary = reg.summarize(sites)
        # 45 + 2026-09-23 爬塔线专用结算单击改造新增 1 处 execute_single_click
        self.assertEqual(summary['l1_pipeline_sites'], 46)
        self.assertEqual((summary['raw_module'], summary['raw_primitive'], summary['raw_excluded']), (4, 0, 0))
        self.assertEqual(summary['raw_click_sites'], summary['raw_module'])
        long_sites = reg.scan_long_click_sites()
        by = {}
        for s in long_sites:
            by.setdefault((s['kind'], s['area']), 0)
            by[(s['kind'], s['area'])] += 1
        self.assertEqual(by[('execute_long_click', 'primitive')], 6)
        self.assertNotIn(('raw_long_click', 'consumer'), by)
        self.assertNotIn(('raw_long_click', 'primitive'), by)

    def test_former_exclusions_now_reach_the_executor_via_l1(self):
        sites = reg.classify_all(reg.scan_sites(), reg.load_audited_rows())
        executor_files = {s['file'] for s in sites if s['kind'] == 'execute_single_click'}
        for rel in ('tasks/Component/Login/service.py', 'tasks/DailyTrifles/script_task.py',
                    'tasks/WeeklyPurchase/mall/navbar.py'):
            self.assertIn(rel, executor_files)
