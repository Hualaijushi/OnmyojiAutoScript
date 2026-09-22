# This Python file uses the following encoding: utf-8
"""L1 全局单击管线（`module/click_pipeline.py`，`docs/DECISIONS.md` D026）回归护栏。

L1 只回答「最终点在哪」「这一击怎么落下去」：

    Target → resolve_click_point → FinalPoint → execute_single_click
           → Control.click → minitouch（DOWN → dwell → UP）→ BehaviorTrace

CASE 编号对应 L1 实施任务单。minitouch 的 DOWN/WAIT/UP 事件序列与 dwell
`random_triangular(45, 130, 65)` 已由 `tests/test_minitouch_randomization.py` 精确锁定，
这里只做「L1 执行器确实接到这条后端」的端到端串联，不重复其断言。
"""

import ast
import inspect
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import numpy as np

from module import behavior_trace
from module import click_pipeline as cp
from module import click_sampler as cs
from module.atom.click import RuleClick
from module.atom.long_click import RuleLongClick
from module.atom.swipe import RuleSwipe
from module.behavior_trace import BehaviorTrace, configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import (
    ClickBounds,
    ClickRegion,
    FinalPoint,
    execute_single_click,
    resolve_click_point,
)
from module.click_preference import RULE_BASE_PREFERRED, TARGET_PREFERENCES, Provenance, TargetPreference
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.device.method.minitouch import Minitouch
from tasks.base_task import BaseTask
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.config_general_battle import GreenMarkType
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.EvoZone.script_task import ScriptTask as EvoZoneScriptTask

_REPO = Path(__file__).resolve().parents[1]


def _inside(point, roi) -> bool:
    x, y, w, h = roi
    px, py = point
    return x <= px < x + w and y <= py < y + h


def _forbid_sampling():
    """任何空间采样都算失败：用于证明 FinalPoint / 业务已给定落点的路径零采样。"""
    boom = AssertionError('此路径不允许任何空间采样')
    return patch.multiple(
        ClickSampler,
        sample=Mock(side_effect=boom),
        sample_point=Mock(side_effect=boom),
        sample_target=Mock(side_effect=boom),
        sample_region=Mock(side_effect=boom),
    )


def _make_control(click_method):
    """与 `test_behavior_click_stats` 同一套最小 Control 夹具：真实 `Control.click`，假后端。"""
    c = Control.__new__(Control)
    c.config = SimpleNamespace(
        config_name='l1test',
        script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')),
    )
    c.click_methods = {'minitouch': click_method}
    return c


class _BuilderStub:
    """记录 minitouch CommandBuilder 链式调用，只用于证明 L1 执行器落到一次 DOWN / UP。"""

    def __init__(self):
        self.events = []
        self.delay = 0

    def down(self, x, y, pressure=100):
        self.events.append(('down', x, y, pressure))
        return self

    def up(self):
        self.events.append(('up',))
        return self

    def commit(self):
        self.events.append(('commit',))
        return self

    def wait(self, ms):
        self.events.append(('wait', ms))
        return self


# --------------------------------------------------------------------------------------
# 坐标解析：Image / Rule 目标
# --------------------------------------------------------------------------------------

class ImageTargetResolverTest(unittest.TestCase):
    def test_case1_rule_click_resolves_through_coord_sample_target(self):
        rule = RuleClick(roi_front=(100, 200, 80, 40), roi_back=(0, 0, 1, 1), name='l1_btn')
        with patch.object(ClickSampler, 'sample_target', return_value=(111, 222)) as st:
            self.assertEqual(resolve_click_point(rule), (111, 222))
        st.assert_called_once_with((100, 200, 80, 40), 'l1_btn')

    def test_case1_image_asset_resolves_through_its_current_roi(self):
        rule = GeneralBattleAssets.I_EXIT   # 真实 RuleImage 资源
        with patch.object(ClickSampler, 'sample_target', return_value=(5, 6)) as st:
            self.assertEqual(resolve_click_point(rule), (5, 6))
        st.assert_called_once_with(rule.roi_front, rule.name)

    def test_case2_empirical_hotspot_wins_over_rule_fallback(self):
        # 注入一个热点明显不同于 RULE_FALLBACK 的 EMPIRICAL 条目，跑真实查表 + 真实采样链，
        # 捕获最终交给 HABIT 的 effective profile（大 ROI 尺寸因子 = 1，热点不收缩）。
        emp = TargetPreference(
            target_name='l1_emp', preferred_u=0.20, preferred_v=0.30,
            profile_name='default_point', provenance=Provenance.EMPIRICAL, confidence=0.5,
        )
        roi = (0, 0, 400, 400)
        with patch.dict(TARGET_PREFERENCES, {'l1_emp': emp}), \
                patch.object(ClickSampler, 'sample', wraps=ClickSampler.sample) as sample:
            resolve_click_point(RuleClick(roi_front=roi, roi_back=roi, name='l1_emp'))
        profile = sample.call_args.kwargs['profile']
        self.assertEqual((profile.preferred_u, profile.preferred_v), (0.20, 0.30))

    def test_case3_unregistered_target_uses_rule_fallback(self):
        roi = (0, 0, 400, 400)
        with patch.object(ClickSampler, 'sample', wraps=ClickSampler.sample) as sample:
            resolve_click_point(RuleClick(roi_front=roi, roi_back=roi, name='l1_not_registered'))
        profile = sample.call_args.kwargs['profile']
        self.assertEqual((profile.preferred_u, profile.preferred_v), RULE_BASE_PREFERRED)
        self.assertEqual(profile.name, 'default_point')

    def test_case4_resolved_point_always_inside_roi_including_tiny(self):
        for roi in ((100, 200, 300, 120), (50, 60, 20, 18), (10, 10, 3, 3), (10, 10, 1, 1)):
            rule = RuleClick(roi_front=roi, roi_back=roi, name='l1_safe')
            with self.subTest(roi=roi):
                for _ in range(400):
                    self.assertTrue(_inside(resolve_click_point(rule), roi))


# --------------------------------------------------------------------------------------
# 坐标解析：动态矩形 / 原生控件 / 业务区域 / 最终落点
# --------------------------------------------------------------------------------------

class DynamicAndNativeBoundsTest(unittest.TestCase):
    def test_case5_dynamic_bounds_use_point_model_by_target_identity(self):
        bounds = (300, 400, 120, 36)
        with patch.object(ClickSampler, 'sample_target', wraps=ClickSampler.sample_target) as st:
            for _ in range(200):
                self.assertTrue(_inside(resolve_click_point(ClickBounds(bounds, 'O_FRIEND_NAME_1')), bounds))
        st.assert_called_with(bounds, 'O_FRIEND_NAME_1')

    def test_case8_native_bounds_never_look_up_image_hotspot(self):
        # 故意用一个真实登记为 EMPIRICAL 的图片目标名：原生控件也不能借用它的热点。
        self.assertEqual(TARGET_PREFERENCES['area_1'].provenance, Provenance.EMPIRICAL)
        bounds = (100, 200, 200, 60)
        with patch.object(cs, 'resolve_target_preference', wraps=cs.resolve_target_preference) as rtp, \
                patch.object(ClickSampler, 'sample_target', side_effect=AssertionError('原生控件不能走 Point 热点')):
            for _ in range(200):
                self.assertTrue(_inside(resolve_click_point(ClickBounds(bounds, 'area_1', native=True)), bounds))
        self.assertTrue(rtp.called)
        for call in rtp.call_args_list:
            self.assertIsNone(call.args[0])

    def test_case8_degenerate_native_bounds_fall_back_to_center_without_sampling(self):
        with _forbid_sampling():
            self.assertEqual(resolve_click_point(ClickBounds((10, 20, 0, 6), 'n', native=True)), (10, 23))
            self.assertEqual(resolve_click_point(ClickBounds((10, 20, 8, 0), 'n', native=True)), (14, 20))


class FinalPointAndRegionTest(unittest.TestCase):
    def test_case6_final_point_is_never_resampled(self):
        with _forbid_sampling():
            self.assertEqual(resolve_click_point(FinalPoint(123, 456)), (123, 456))

    def test_case6_final_point_truncates_like_control_ensure_int(self):
        # 业务把 numpy 浮点 OCR 坐标包成 FinalPoint 后，落点必须与旧的 `device.click(float)` →
        # `ensure_int`（int 截断）逐像素一致。
        self.assertEqual(resolve_click_point(FinalPoint(np.float32(12.9), np.float64(30.99))), (12, 30))
        with self.assertRaises(TypeError):
            FinalPoint(True, 5)

    def test_case7_settlement_anchor_point_is_executed_verbatim(self):
        # Settlement 自己的 FinalPoint 原语（anchor 复用）：L1 边界之下只执行、绝不重采。
        fake = SimpleNamespace(device=SimpleNamespace(click=Mock()))
        with _forbid_sampling():
            GeneralBattle._click_settlement_point(fake, (321, 654), 'random_save_right')
        fake.device.click.assert_called_once_with(x=321, y=654, control_name='random_save_right')

    def test_case7_settlement_region_policy_uses_region_model_not_point(self):
        fake = SimpleNamespace(device=SimpleNamespace(click=Mock()))
        rule = GeneralBattleAssets.C_RANDOM_SAVE_RIGHT
        with patch.object(ClickSampler, 'sample_region', return_value=(1200, 400)) as sr, \
                patch.object(ClickSampler, 'sample_target', side_effect=AssertionError('Settlement 不走 Point 模型')):
            GeneralBattle._sample_settlement_click(fake, rule)
        sr.assert_called_once_with(rule.roi_front, rule.name)
        fake.device.click.assert_called_once_with(x=1200, y=400, control_name=rule.name)

    def test_click_region_delegates_to_region_sampler(self):
        with patch.object(ClickSampler, 'sample_region', return_value=(9, 9)) as sr:
            self.assertEqual(resolve_click_point(ClickRegion((0, 0, 50, 50), 'random_default')), (9, 9))
        sr.assert_called_once_with((0, 0, 50, 50), 'random_default')


class ResolverContractTest(unittest.TestCase):
    def test_bare_coordinates_and_non_click_rules_are_rejected(self):
        for bad in ((5, 6), [5, 6], None, RuleSwipe((0, 0, 1, 1), (0, 0, 1, 1), 'default')):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                resolve_click_point(bad)

    def test_long_click_is_never_downgraded_to_tap(self):
        device = SimpleNamespace(click=Mock())
        long_rule = RuleLongClick((0, 0, 10, 10), (0, 0, 10, 10), 'lc', 800)
        with self.assertRaises(TypeError):
            execute_single_click(device, long_rule)
        device.click.assert_not_called()

    def test_control_name_precedence(self):
        device = SimpleNamespace(click=Mock())
        execute_single_click(device, FinalPoint(1, 2), control_name='explicit')
        self.assertEqual(device.click.call_args.kwargs['control_name'], 'explicit')
        execute_single_click(device, ClickRegion((0, 0, 40, 40), 'region_name'))
        self.assertEqual(device.click.call_args.kwargs['control_name'], 'region_name')
        execute_single_click(device, FinalPoint(1, 2))
        self.assertEqual(device.click.call_args.kwargs['control_name'], 'Click')


# --------------------------------------------------------------------------------------
# 单击执行器 + BehaviorTrace
# --------------------------------------------------------------------------------------

class SingleClickExecutorTest(unittest.TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._orig_dir = behavior_trace._LOG_DIR
        self._tmpdir = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmpdir.name) / 'behavior'

    def tearDown(self):
        reset_behavior_traces()
        behavior_trace._LOG_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def _rows(self):
        files = list(behavior_trace._LOG_DIR.glob('l1test_*.jsonl'))
        if not files:
            return []
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln]

    def test_case9_and_case11_executor_reaches_real_minitouch_one_down_one_up(self):
        builder = _BuilderStub()
        backend = Minitouch.__new__(Minitouch)
        backend.__dict__['minitouch_builder'] = builder
        backend.minitouch_send = Mock()
        backend._humanized_pressure = Mock(return_value=50)
        control = _make_control(backend.click_minitouch)
        with patch('module.device.method.minitouch.random_triangular', return_value=80.0) as tri:
            self.assertEqual(execute_single_click(control, FinalPoint(100, 200), 'l1_btn'), (100, 200))
        self.assertEqual(builder.events, [
            ('down', 100, 200, 50), ('commit',), ('wait', 80), ('up',), ('commit',),
        ])
        tri.assert_called_once_with(45, 130, 65)   # dwell 契约未被 L1 改动
        backend.minitouch_send.assert_called_once_with()

    def test_case9_execute_single_click_issues_exactly_one_device_click(self):
        device = SimpleNamespace(click=Mock())
        execute_single_click(device, RuleClick((0, 0, 60, 60), (0, 0, 60, 60), 'once'))
        device.click.assert_called_once()

    def test_case12_trace_coordinates_equal_executed_coordinates(self):
        backend = Mock(name='click_minitouch')
        control = _make_control(backend)
        configure_behavior_trace('l1test', enabled=True)
        roi = (400, 300, 200, 90)
        x, y = execute_single_click(control, RuleClick(roi, roi, 'l1_trace_btn'))
        self.assertTrue(_inside((x, y), roi))
        self.assertEqual(backend.call_args.args, (x, y))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['target'], 'l1_trace_btn')
        self.assertEqual(rows[0]['extra'], {'x': x, 'y': y})

    def test_case13_trace_disabled_click_still_executes(self):
        backend = Mock(name='click_minitouch')
        configure_behavior_trace('l1test', enabled=False)
        execute_single_click(_make_control(backend), FinalPoint(10, 20))
        backend.assert_called_once_with(10, 20)
        self.assertEqual(self._rows(), [])

    def test_case14_trace_writer_failure_does_not_block_click(self):
        backend = Mock(name='click_minitouch')
        configure_behavior_trace('l1test', enabled=True)
        with patch.object(BehaviorTrace, '_write_line', side_effect=OSError('disk full')):
            self.assertEqual(execute_single_click(_make_control(backend), FinalPoint(7, 8)), (7, 8))
        backend.assert_called_once_with(7, 8)


# --------------------------------------------------------------------------------------
# 旧路径不回归 + 显式最终坐标不 double randomization
# --------------------------------------------------------------------------------------

class LegacyPathAndNoDoubleRandomizationTest(unittest.TestCase):
    def test_case15_base_task_click_still_samples_once_and_clicks(self):
        task = BaseTask.__new__(BaseTask)
        task.interval_timer = {}
        task.device = SimpleNamespace(click=Mock(), long_click=Mock())
        roi = (500, 500, 100, 50)
        # BaseTask.click 的返回值语义是「是否设置并到达 interval」，不是「是否点击」；
        # 无 interval 时点击后仍返回 False，这里只断言真实点击行为。
        task.click(RuleClick(roi, roi, 'legacy_btn'))
        task.device.click.assert_called_once()
        kwargs = task.device.click.call_args.kwargs
        self.assertEqual(kwargs['control_name'], 'legacy_btn')
        self.assertTrue(_inside((kwargs['x'], kwargs['y']), roi))

    def test_case16_list_appear_click_executes_presampled_point_verbatim(self):
        task = BaseTask.__new__(BaseTask)
        task.interval_timer = {}
        task.device = SimpleNamespace(click=Mock())
        task.list_find = Mock(return_value=(641, 222))   # 图片列表：coord() 已采样过的点
        with _forbid_sampling():
            self.assertTrue(task.list_appear_click(SimpleNamespace(name='L_X', array=['a']), interval=1))
        task.device.click.assert_called_once_with(x=641, y=222, control_name='L_X')

    def test_case16_evozone_layer_ocr_center_is_not_resampled(self):
        fake = SimpleNamespace(
            L_LAYER_LIST=object(),
            list_find=Mock(return_value=(162, 330)),
            device=SimpleNamespace(click=Mock()),
        )
        with _forbid_sampling():
            self.assertTrue(EvoZoneScriptTask.check_layer(fake, '十层'))
        fake.device.click.assert_called_once_with(x=162, y=330, control_name='EVOZONE_LAYER_十层')

    def test_case16_green_mark_name_business_offset_is_preserved_exactly(self):
        # 落点 = 名字框左上角 +(5, 30)，在文字框之外：必须逐像素保持，不能被采样回框内。
        box = np.array([[10.0, 20.0], [50.0, 20.0], [50.0, 40.0], [10.0, 40.0]], dtype=np.float32)
        fake = SimpleNamespace(
            screenshot=Mock(),
            device=SimpleNamespace(image='FRAME', click=Mock()),
            O_GREEN_MARK_AREA=SimpleNamespace(
                roi=(100, 200, 400, 200),
                detect_and_ocr=Mock(return_value=[SimpleNamespace(ocr_text='茨木童子', box=box)]),
            ),
        )
        with _forbid_sampling():
            GeneralBattle.green_mark_name(fake, '茨木童子')
        fake.device.click.assert_called_once_with(x=115, y=250, control_name='茨木童子')

    def test_green_mark_choose_resolves_rule_at_click_time_with_identity(self):
        rule = GeneralBattleAssets.C_GREEN_MAIN
        fake = SimpleNamespace(
            C_GREEN_MAIN=rule, I_PREPARE_HIGHLIGHT=object(), I_LOCAL=object(),
            screenshot=Mock(), appear=Mock(return_value=False), appear_then_click=Mock(return_value=False),
            device=SimpleNamespace(click=Mock()),
        )
        GeneralBattle.green_mark_choose(fake, GreenMarkType.GREEN_MAIN)
        fake.device.click.assert_called_once()
        kwargs = fake.device.click.call_args.kwargs
        self.assertEqual(kwargs['control_name'], rule.name)
        self.assertTrue(_inside((kwargs['x'], kwargs['y']), rule.roi_front))


# --------------------------------------------------------------------------------------
# L1 边界：不含 L2 / L3 职责
# --------------------------------------------------------------------------------------

class L1BoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = inspect.getsource(cp)
        tree = ast.parse(cls.src)
        cls.imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                cls.imported.add(node.module)
            elif isinstance(node, ast.Import):
                cls.imported.update(alias.name for alias in node.names)
        # 只看可执行代码，排除 docstring / 注释里用来说明边界的词。
        cls.code_names = {
            n.id if isinstance(n, ast.Name) else n.attr
            for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Attribute))
        }

    def test_case10_no_production_multi_click_consumer(self):
        hits = []
        for sub in ('tasks', 'module'):
            for path in (_REPO / sub).rglob('*.py'):
                for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                    if 'multi_click(' in line and 'def multi_click' not in line:
                        hits.append(path.relative_to(_REPO).as_posix())
        script = (_REPO / 'script.py').read_text(encoding='utf-8', errors='ignore')
        if 'multi_click(' in script:
            hits.append('script.py')
        self.assertEqual(hits, [])
        self.assertNotIn('multi_click', self.code_names)

    def test_case17_no_reaction_or_sleep_in_l1(self):
        for name in ('sleep', 'random_delay', 'confirm_delay', 'REACTION_FIRE', 'REACTION_FAST', 'Timer'):
            self.assertNotIn(name, self.code_names, name)
        with patch.object(time, 'sleep', side_effect=AssertionError('L1 不许 sleep')):
            execute_single_click(SimpleNamespace(click=Mock()), FinalPoint(1, 1))

    def test_case18_no_fresh_screenshot_in_l1(self):
        self.assertNotIn('screenshot', self.code_names)
        execute_single_click(SimpleNamespace(click=Mock()), FinalPoint(1, 1))   # 设备没有 screenshot 也能点

    def test_case19_no_business_retry_single_attempt(self):
        device = SimpleNamespace(click=Mock(side_effect=RuntimeError('backend down')))
        with self.assertRaises(RuntimeError):
            execute_single_click(device, FinalPoint(1, 1))
        self.assertEqual(device.click.call_count, 1)
        self.assertFalse(any(isinstance(n, (ast.While, ast.For)) for n in ast.walk(ast.parse(self.src))))

    def test_case20_l1_does_not_own_settlement_fire_fatigue_framewait_timing(self):
        for forbidden in ('module.reaction_profile', 'module.fatigue', 'module.base.frame_wait',
                          'module.base.timer', 'tasks.Component.GeneralBattle.general_battle'):
            self.assertNotIn(forbidden, self.imported, forbidden)
        self.assertLessEqual(
            self.imported,
            {'__future__', 'dataclasses', 'numbers', 'module.atom.click', 'module.atom.gif',
             'module.atom.image', 'module.atom.long_click', 'module.atom.ocr', 'module.click_sampler'},
        )
        # Settlement 观察间隔 / FIRE reaction 仍留在各自业务里
        self.assertTrue(hasattr(GeneralBattle, 'SETTLEMENT_BURST_CLICK_INTERVAL_RANGE'))
        rr_src = (_REPO / 'tasks' / 'RealmRaid' / 'script_task.py').read_text(encoding='utf-8')
        self.assertIn('fire_reaction_range', rr_src)


class ConvertedSitesGuardTest(unittest.TestCase):
    """本轮收口的生产点位不能退回裸 `device.click`（坐标语义含糊 = double randomization 风险）。"""

    SITES = (
        ('tasks/base_task.py', 'list_appear_click'),
        # L1 Stage 1：BaseTask 公共 primitive 的 8 个单击执行点（坐标仍由 coord() 采样一次，以 FinalPoint 交给执行器）
        ('tasks/base_task.py', 'appear_then_click'),
        ('tasks/base_task.py', 'wait_until_appear_then_click'),
        ('tasks/base_task.py', 'click'),
        ('tasks/base_task.py', 'ocr_appear_click'),
        # L1 Stage 2：剩余 9 个生产直接点击（采样仍在原位置，已定坐标以 FinalPoint / ClickRegion 交给执行器）
        ('tasks/Chess/runtime/round_state.py', '_refresh_grigri_option'),
        ('tasks/Component/GeneralBattle/general_battle.py', '_sample_settlement_click'),
        ('tasks/Component/GeneralBattle/general_battle.py', '_click_settlement_point'),
        ('tasks/Component/GeneralInvite/general_invite.py', '_detect_select'),
        ('tasks/GameUi/navigator.py', '_execute_action'),
        ('tasks/KekkaiUtilize/script_task.py', 'switch_friend_list'),
        ('tasks/RyouToppa/script_task.py', '_click_toppa_area'),
        ('tasks/Secret/script_task.py', 'find_battle'),
        ('tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py', '_mark_peacock_boss'),
        ('tasks/Component/GeneralBattle/general_battle.py', 'green_mark_choose'),
        ('tasks/Component/GeneralBattle/general_battle.py', 'green_mark_name'),
        ('tasks/EvoZone/script_task.py', 'check_layer'),
        ('tasks/ActivityShikigami/activities/rich_man.py', '_enter_boss_fight_by_anchor'),
        # L1.2
        ('tasks/Chess/runtime/hand_operations.py', 'discover_souls_from_hand'),
        ('tasks/Component/QuickLoadout/quick_loadout.py', '_select_group'),
        ('tasks/Component/QuickLoadout/quick_loadout.py', '_equip_quick_loadout_souls'),
        ('tasks/Component/QuickLoadout/quick_loadout.py', '_deploy_quick_loadout'),
        ('tasks/Component/SwitchSoul/switch_soul.py', 'ocr_appear_click_by_rule'),
        ('tasks/Dokan/page.py', 'map_enter_dokan'),
        ('tasks/Dokan/script_task.py', 'find_challengeable'),
        ('tasks/EternitySea/script_task.py', 'check_layer'),
        ('tasks/FallenSun/script_task.py', 'check_layer'),
        ('tasks/Orochi/script_task.py', 'check_layer'),
        ('tasks/SixRealms/common.py', 'buy_skill'),
        ('tasks/WantedQuests/script_task.py', 'trace_one'),
        ('tasks/WeeklyTrifles/script_task.py', '_broken_amulet'),
        ('tasks/Component/GeneralRoom/general_room.py', 'check_zones'),
        ('tasks/Hyakkiyakou/slave/hya_device.py', 'fast_click'),
    )

    @staticmethod
    def _function_source(rel_path: str, func_name: str) -> str:
        text = (_REPO / rel_path).read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                return ast.get_source_segment(text, node)
        raise AssertionError(f'{rel_path}::{func_name} 不存在')

    def test_converted_sites_route_through_l1_executor(self):
        for rel_path, func_name in self.SITES:
            with self.subTest(site=f'{rel_path}::{func_name}'):
                body = self._function_source(rel_path, func_name)
                self.assertIn('execute_single_click(', body)
                self.assertNotIn('self.device.click(', body)

    def test_town_fallback_click_routes_through_l1_as_final_point(self):
        body = self._function_source('tasks/GameUi/navigator.py', '_execute_transition')
        fallback = body[body.index('Town target was not recognized'):]
        fallback = fallback[:fallback.index('action_done = True')]
        self.assertIn('execute_single_click(', fallback)
        self.assertIn('FinalPoint(click_x, click_y)', fallback)
        self.assertNotIn('self.device.click(', fallback)


# ======================================================================================
# L1.2 Global Click Migration（CASE 21–45）
# ======================================================================================

def _ocr_hit_list(text='柒层', roi_back=(127, 95, 106, 603), box=((10, 20), (40, 20), (40, 60), (10, 60))):
    """真实 RuleList.ocr_appear 命中一次（只替换 OCR 检测结果），返回 (列表, list_find 会拿到的 pos)。"""
    from module.atom.list import RuleList
    from module.atom.ocr import RuleOcr
    rule_list = RuleList(folder='./tests', direction='vertical', mode='ocr', roi_back=roi_back,
                         size=(106, 101), array=[text])
    item = SimpleNamespace(ocr_text=text, score=0.99, box=np.array(box, dtype=np.float32))
    with patch.object(RuleOcr, 'detect_and_ocr', return_value=[item]):
        pos = rule_list.ocr_appear(None, text)
    return rule_list, pos


def _image_list():
    from module.atom.list import RuleList
    return RuleList(folder='./tests', direction='vertical', mode='image', roi_back=(1178, 88, 60, 531),
                    size=(45, 76), array=['special'])


class ListHitTargetTest(unittest.TestCase):
    """RuleList 命中 → 显式点击目标（CASE 38 / 39 的列表部分）。"""

    def test_ocr_hit_records_screen_bounds_and_keeps_return_contract(self):
        rule_list, pos = _ocr_hit_list()
        self.assertEqual((int(pos[0]), int(pos[1])), (127 + 10 + 15, 95 + 20 + 20))   # 返回值契约不变
        self.assertEqual(rule_list.last_ocr_hit, ((152, 135), (137, 115, 30, 40)))

    def test_ocr_hit_becomes_bounds_sampled_by_target_identity(self):
        rule_list, pos = _ocr_hit_list()
        target = cp.list_click_target(rule_list, pos, 'LAYER_柒层')
        self.assertEqual(target, ClickBounds((137, 115, 30, 40), 'LAYER_柒层'))
        with patch.object(ClickSampler, 'sample_target', return_value=(150, 130)) as st:
            self.assertEqual(resolve_click_point(target), (150, 130))
        st.assert_called_once_with((137, 115, 30, 40), 'LAYER_柒层')

    def test_stale_or_missing_ocr_hit_falls_back_to_final_point(self):
        rule_list, _ = _ocr_hit_list()
        with _forbid_sampling():
            self.assertEqual(cp.list_click_target(rule_list, (10, 10), 'n'), FinalPoint(10, 10))   # pos 不对应
        from module.atom.ocr import RuleOcr
        with patch.object(RuleOcr, 'detect_and_ocr', return_value=[]):
            miss = rule_list.ocr_appear(None, '柒层')
        self.assertIsNone(rule_list.last_ocr_hit)                     # 新一轮识别清掉旧命中
        self.assertEqual(cp.list_click_target(rule_list, miss, 'n'), FinalPoint(0, 0))   # 旧 (0,0) 行为原样保留

    def test_case38_image_list_point_is_already_sampled_and_never_resampled(self):
        with _forbid_sampling():
            self.assertEqual(cp.list_click_target(_image_list(), (1201, 300), 'RM'), FinalPoint(1201, 300))


class MigratedSitesBehaviourTest(unittest.TestCase):
    """CASE 21–33：逐个驱动真实业务函数到点击点。"""

    def test_case21_chess_discover_card_samples_inside_card_name_ocr_box(self):
        from tasks.Chess.runtime.hand_operations import ChessHandOperationsMixin as Chess
        ocr_owner = SimpleNamespace(
            O_BADGE_AREA=SimpleNamespace(roi=(300, 500, 600, 100), detect_and_ocr=Mock(return_value=[
                SimpleNamespace(ocr_text='发现纹章', score=0.9, box=[[10, 20], [70, 20], [70, 44], [10, 44]]),
            ])),
            device=SimpleNamespace(image='F'),
            _normalize_ocr_text=lambda text: text,
        )
        card = Chess._discover_named_hand_cards(ocr_owner, '发现纹章', allow_fuzzy=False)[0]
        self.assertEqual(card['position'], (340, 532))
        self.assertEqual(card['bounds'], (310, 520, 60, 24))

        fake = SimpleNamespace(
            DISCOVER_SOUL_SAFETY_LIMIT=1, DISCOVER_SOUL_UI_TIMEOUT=5, SCREENSHOT_INTERVAL=0,
            _is_preparation_mode=Mock(side_effect=[True, False]),
            _discover_badge_hand_cards=Mock(return_value=[card]), _discover_soul_hand_cards=Mock(return_value=[]),
            screenshot=Mock(), device=SimpleNamespace(click=Mock()),
        )
        with patch.object(ClickSampler, 'sample_target', return_value=(333, 530)) as st:
            Chess.discover_souls_from_hand(fake)
        st.assert_called_once_with((310, 520, 60, 24), 'CHESS_DISCOVER_CARD')
        fake.device.click.assert_called_once_with(x=333, y=530, control_name='CHESS_DISCOVER_CARD')

    def test_case21_chess_refresh_stays_one_coord_per_click(self):
        # 刷新按钮本来就是 coord() 紧邻具名 click（每次点击独立采样一次），属已合规路径，不改。
        body = ConvertedSitesGuardTest._function_source('tasks/Chess/runtime/round_state.py', '_refresh_grigri_option')
        loop = body[body.index('for click_index in range(1, 3):'):]
        self.assertEqual(loop.count('refresh_rule.coord()'), 1)
        self.assertNotIn('self.device.click(', loop)
        self.assertLess(loop.index('refresh_rule.coord()'), loop.index('execute_single_click('))   # 每次点击独立采样后再交执行器
        self.assertIn('FinalPoint(click_x, click_y)', loop)

    def test_case22_quick_loadout_layout_points_are_final_points(self):
        from tasks.Component.QuickLoadout import quick_loadout as ql
        from tasks.Component.QuickLoadout.config import QuickLoadoutMode
        layout = SimpleNamespace(panel=(100, 50, 551, 386), group_ocr=object(), group_swipe_to_top=object())
        consts = {k: getattr(ql.QuickLoadout, k) for k in (
            'MAX_GROUP_SWIPES', 'GROUP_FIRST_Y', 'GROUP_ROW_HEIGHT', 'GROUP_CLICK_X', 'PRESET_EQUIP_X',
            'PRESET_SELECT_X', 'CONFIRM_TIMEOUT', 'PANEL_CLOSE_TIMEOUT')}
        fake = SimpleNamespace(**consts, _rewind_list=Mock(), screenshot=Mock(), appear=Mock(return_value=True),
                               click=Mock(), _dismiss_quick_loadout=Mock(), device=SimpleNamespace(click=Mock()))
        reached = Mock()
        reached.return_value.start.return_value.reached.return_value = True
        with _forbid_sampling(), patch.object(ql, 'sleep'), patch.object(ql, 'Timer', reached):
            ql.QuickLoadout._select_group(fake, layout, SimpleNamespace(mode=QuickLoadoutMode.NUMBER, group_number=2))
            ql.QuickLoadout._equip_quick_loadout_souls(fake, layout, 222)
            ql.QuickLoadout._deploy_quick_loadout(fake, layout, object(), object(), 222)
        self.assertEqual(fake.device.click.call_args_list[0].kwargs, dict(x=161, y=132, control_name='QUICK_LOADOUT_GROUP'))
        self.assertEqual(fake.device.click.call_args_list[1].kwargs, dict(x=582, y=222, control_name='QUICK_LOADOUT_EQUIP_SOUL'))
        self.assertEqual(fake.device.click.call_args_list[2].kwargs, dict(x=400, y=222, control_name='QUICK_LOADOUT_PRESET'))

    def test_case23_switch_soul_combines_two_sampled_axes_without_resampling(self):
        from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
        fake = SimpleNamespace(ocr_appear=Mock(return_value=True), device=SimpleNamespace(click=Mock()))
        target = SimpleNamespace(coord=Mock(return_value=(10, 222)), name='O_SS_TEAM_NAME')
        action = SimpleNamespace(coord=Mock(return_value=(640, 5)))
        with _forbid_sampling():
            self.assertTrue(SwitchSoul.ocr_appear_click_by_rule(fake, target, action, interval=1.5))
        target.coord.assert_called_once_with()
        action.coord.assert_called_once_with()
        fake.device.click.assert_called_once_with(x=640, y=222, control_name='O_SS_TEAM_NAME')

    def test_case24_dokan_map_offset_point_is_preserved(self):
        from tasks.Dokan.page import map_enter_dokan
        task = SimpleNamespace(
            screenshot=Mock(), appear=Mock(side_effect=[False, True]), I_RYOU_DOKAN_CHECK=object(),
            O_DOKAN_MAP=SimpleNamespace(ocr_full=Mock(return_value=(100.0, 200.0, 41.0, 20.0))),
            device=SimpleNamespace(image='F', click=Mock()),
        )
        with _forbid_sampling():
            self.assertTrue(map_enter_dokan(task))
        # 旧值 x=120.5 经 Control.ensure_int 截断为 120；FinalPoint 同口径。
        task.device.click.assert_called_once_with(x=120, y=180, control_name='dokan_map_goto_dokan')

    def test_case24_dokan_bounty_icon_uses_match_bounds_with_rule_identity(self):
        body = ConvertedSitesGuardTest._function_source('tasks/Dokan/script_task.py', 'find_challengeable')
        self.assertIn('ClickBounds(tuple(bounty_list[idx_selected]), self.I_RIGHTPAD_POINT_BOUNTY.name)', body)
        self.assertIn('execute_single_click(self.device, bounty_bounds)', body)
        with patch.object(ClickSampler, 'sample_target', return_value=(1111, 222)) as st:
            self.assertEqual(resolve_click_point(ClickBounds((1100, 210, 30, 30), 'rightpad_point_bounty')), (1111, 222))
        st.assert_called_once_with((1100, 210, 30, 30), 'rightpad_point_bounty')

    def _drive_check_layer(self, task_cls, layer, control_name):
        rule_list, pos = _ocr_hit_list(text=layer)
        fake = SimpleNamespace(L_LAYER_LIST=rule_list, list_find=Mock(return_value=pos),
                               device=SimpleNamespace(click=Mock()))
        with patch.object(ClickSampler, 'sample_target', return_value=(150, 130)) as st:
            self.assertTrue(task_cls.check_layer(fake, layer))
        st.assert_called_once_with((137, 115, 30, 40), control_name)
        fake.device.click.assert_called_once_with(x=150, y=130, control_name=control_name)

    def test_case25_eternity_sea_layer_samples_inside_ocr_box(self):
        from tasks.EternitySea.script_task import ScriptTask
        self._drive_check_layer(ScriptTask, '叁层', 'ETERNITY_SEA_LAYER_叁层')

    def test_case26_fallen_sun_layer_samples_inside_ocr_box(self):
        from tasks.FallenSun.script_task import ScriptTask
        self._drive_check_layer(ScriptTask, '贰层', 'FALLEN_SUN_LAYER_贰层')

    def test_case27_orochi_layer_samples_inside_ocr_box(self):
        from tasks.Orochi.script_task import ScriptTask
        self._drive_check_layer(ScriptTask, '拾层', 'LAYER_拾层')

    def test_evozone_layer_samples_inside_ocr_box(self):
        self._drive_check_layer(EvoZoneScriptTask, '十层', 'EVOZONE_LAYER_十层')

    def test_case28_secret_constructed_rule_click_is_already_l1_compliant(self):
        body = ConvertedSitesGuardTest._function_source('tasks/Secret/script_task.py', 'find_battle')
        loop = body[body.index('for click_index in range(1, 3):'):]
        self.assertEqual(loop.count('click_rule.coord()'), 1)
        self.assertNotIn('self.device.click(', loop)
        self.assertLess(loop.index('click_rule.coord()'), loop.index('execute_single_click('))
        self.assertNotIn(('tasks/Secret/script_task.py', 'find_battle'), StaticMigrationGuardTest.CANONICAL_DIRECT_CLICKS)

    def test_case29_six_realms_buy_region_matches_old_randint_support(self):
        from tasks.SixRealms import common
        skill = SimpleNamespace(name='I_SKILL', roi_front=(500, 300, 40, 30), front_center=lambda: (520, 315))
        fake = SimpleNamespace(I_UI_CONFIRM=object(), screenshot=Mock(), appear_then_click=Mock(return_value=False),
                               appear=Mock(return_value=True), device=SimpleNamespace(image='F', click=Mock()))
        timer = Mock()
        timer.return_value.reached.return_value = True
        with patch.object(common, 'Timer', timer), \
                patch.object(ClickSampler, 'sample_region', return_value=(470, 305)) as sr:
            common.SixRealmsCommon.buy_skill(fake, skill, 100, SimpleNamespace(ocr=Mock(return_value=1000)),
                                             object(), object(), buy_num=1)
        region = sr.call_args.args[0]
        # 旧支撑集：x = 520 - randint(35, 60) ∈ [460, 485]；y = 315 + randint(-30 // 2, 30 // 2) ∈ [300, 330]
        self.assertEqual(region, (460, 300, 26, 31))
        self.assertEqual(sr.call_args.args[1], 'I_SKILL_buy_left')     # 区域身份与图标 rule 分开
        fake.device.click.assert_called_once_with(x=470, y=305, control_name='I_SKILL')
        for _ in range(300):
            self.assertTrue(_inside(resolve_click_point(ClickRegion(region, 'I_SKILL_buy_left')), region))

    def test_case30_wanted_quests_offset_above_button_is_preserved(self):
        from tasks.WantedQuests import script_task as wq
        btn = SimpleNamespace(roi_front=(300, 400, 50, 30))
        fake = SimpleNamespace(
            screenshot=Mock(), appear=Mock(side_effect=[True, False, False, False, True]),
            I_WQ_TRACE_ONE_ENABLE=object(), I_WQ_TRACE_ONE_REALWORLD=object(), I_WQ_TRACE_ONE_DISABLE=object(),
            C_WQ_TRACE_ONE_CLOSE=object(), I_WQ_TRACE_ONE_CHECK_OPENED=object(), click=Mock(),
            ui_click_until_smt_disappear=Mock(), device=SimpleNamespace(click=Mock()),
        )
        with _forbid_sampling(), patch.object(wq, 'sleep'):
            wq.ScriptTask.trace_one(fake, btn)
        fake.device.click.assert_called_once_with(x=300, y=360, control_name=str(btn) + ' y-40')

    def test_case32_weekly_trifles_inferred_checkbox_centres_are_final_points(self):
        body = ConvertedSitesGuardTest._function_source('tasks/WeeklyTrifles/script_task.py', '_broken_amulet')
        self.assertIn('FinalPoint(x_50 - width_check // 2, y_check + height_check // 2)', body)
        self.assertIn('FinalPoint(x_10 - width_check // 2, y_check + height_check // 2)', body)
        self.assertEqual(body.count('execute_single_click('), 2)

    def _drive_general_room(self, rule_list, pos):
        from tasks.Component.GeneralRoom import general_room as gr
        fake = SimpleNamespace(
            L_TEAM_LIST=rule_list, list_find=Mock(return_value=pos), screenshot=Mock(),
            O_GR_ZONES_NAME=SimpleNamespace(keyword='', ocr=Mock(return_value='')),
            ocr_appear=Mock(side_effect=[False, True]), device=SimpleNamespace(image='F', click=Mock()),
        )
        timer = Mock()
        timer.return_value.reached.return_value = True
        with patch.object(gr, 'Timer', timer):
            self.assertTrue(gr.GeneralRoom.check_zones(fake, '金币妖怪'))
        return fake

    def test_general_room_keeps_synevo_center_plus_jitter_through_l1(self):
        """synevo 分支决定保留组队列表原有的「list_find 命中点 + randint(±5)」落点语义，
        整合只把执行入口收口到 L1：抖动仍在业务里现取，L1 只负责把该点打下去。"""
        from tasks.Component.GeneralRoom import general_room as gr
        rule_list, pos = _ocr_hit_list(text='金币妖怪', roi_back=(26, 106, 360, 549))
        with _forbid_sampling(), patch.object(gr, 'randint', side_effect=[3, -4]) as rnd:
            fake = self._drive_general_room(rule_list, pos)
        # 每次点击各取一次 x / y 抖动，且不经过任何 ClickSampler 空间采样。
        self.assertEqual(rnd.call_args_list, [call(-5, 5), call(-5, 5)])
        fake.device.click.assert_called_once_with(x=pos[0] + 3, y=pos[1] - 4, control_name='Click')

    def test_general_room_never_double_randomizes(self):
        """图片列表模式下 pos 已是 coord() 采样点：业务只叠一次 ±5 抖动，L1 不再二次采样。"""
        from tasks.Component.GeneralRoom import general_room as gr
        with _forbid_sampling(), patch.object(gr, 'randint', return_value=0):
            fake = self._drive_general_room(_image_list(), (200, 300))
        fake.device.click.assert_called_once_with(x=200, y=300, control_name='Click')

    def test_general_room_click_goes_through_the_l1_executor(self):
        body = ConvertedSitesGuardTest._function_source(
            'tasks/Component/GeneralRoom/general_room.py', 'check_zones')
        self.assertIn('execute_single_click(', body)
        self.assertIn('FinalPoint(pos[0] + randint(-5, 5), pos[1] + randint(-5, 5))', body)
        self.assertNotIn('self.device.click(', body)


class HyakkiyakouBackendTest(unittest.TestCase):
    """CASE 34 / 35 / 41：原直调后端的高速点击收口到 Control 级分发。"""

    def setUp(self):
        reset_behavior_traces()
        self._orig_dir = behavior_trace._LOG_DIR
        self._tmpdir = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmpdir.name) / 'behavior'

    def tearDown(self):
        reset_behavior_traces()
        behavior_trace._LOG_DIR = self._orig_dir
        self._tmpdir.cleanup()

    @staticmethod
    def _control(control_method='ADB'):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(config_name='l1test',
                                   script=SimpleNamespace(device=SimpleNamespace(control_method=control_method)))
        c.click_adb = Mock(name='click_adb')
        c.click_methods = {'ADB': c.click_adb}
        c.click_minitouch = Mock(name='click_minitouch')
        c.click_window_message = Mock(name='click_window_message')
        c.handle_control_check = Mock(name='handle_control_check')
        return c

    def _rows(self):
        files = list(behavior_trace._LOG_DIR.glob('l1test_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []

    def test_case34_hyakkiyakou_fast_click_is_traced_with_final_coordinates(self):
        from tasks.Hyakkiyakou.config import ControlMethod
        from tasks.Hyakkiyakou.slave.hya_device import HYA_CLICK_NAME, HyaDevice
        control = self._control()
        control.root_node = object()
        configure_behavior_trace('l1test', enabled=True)
        with _forbid_sampling():
            HyaDevice.fast_click(SimpleNamespace(_ensure_root_node=Mock(), device=control), 640.9, 360.2,
                                 control_method=ControlMethod.WINDOW_MESSAGE)
        control.click_window_message.assert_called_once_with(640, 360, fast=True)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['action'], rows[0]['target']), ('click', HYA_CLICK_NAME))
        self.assertEqual(rows[0]['extra'], {'x': 640, 'y': 360})

    def test_case35_backend_behaviour_is_unchanged(self):
        from tasks.Hyakkiyakou.config import ControlMethod
        from tasks.Hyakkiyakou.slave.hya_device import HyaDevice
        control = self._control()
        control.root_node = object()
        HyaDevice.fast_click(SimpleNamespace(_ensure_root_node=Mock(), device=control), 5, 6,
                             control_method=ControlMethod.MINITOUCH)
        control.click_minitouch.assert_called_once_with(5, 6)
        control.click_window_message.assert_not_called()
        control.click_adb.assert_not_called()                      # 不读 control_method 配置
        control.handle_control_check.assert_not_called()           # 原高速路径就不进 click_record
        # 枚举成员与字符串都能分发；未知后端在点击前拒绝。
        control.click_with_backend(7, 8, ControlMethod.WINDOW_MESSAGE)
        control.click_window_message.assert_called_once_with(7, 8, fast=True)
        with self.assertRaises(ValueError):
            control.click_with_backend(1, 1, 'ADB')
        self.assertEqual(control.click_minitouch.call_count + control.click_window_message.call_count, 2)

    def test_case35_fallbacks_keep_original_standard_click(self):
        from tasks.Hyakkiyakou.slave.hya_device import HYA_CLICK_NAME, HyaDevice
        no_root = SimpleNamespace(click=Mock(), click_with_backend=Mock())
        HyaDevice.fast_click(SimpleNamespace(_ensure_root_node=Mock(), device=no_root), 3, 4)
        no_root.click.assert_called_once_with(x=3, y=4, control_name=HYA_CLICK_NAME)
        no_root.click_with_backend.assert_not_called()
        broken = SimpleNamespace(root_node=object(), click=Mock(), click_with_backend=Mock(side_effect=AttributeError))
        HyaDevice.fast_click(SimpleNamespace(_ensure_root_node=Mock(), device=broken), 3, 4)
        broken.click_with_backend.assert_called_once_with(x=3, y=4, backend='window_message', control_name=HYA_CLICK_NAME)
        broken.click.assert_called_once_with(x=3, y=4, control_name=HYA_CLICK_NAME)

    def test_case41_backend_override_is_still_exactly_one_physical_click(self):
        device = Mock(spec=['click', 'click_with_backend'])
        self.assertEqual(execute_single_click(device, FinalPoint(9, 9), backend='minitouch'), (9, 9))
        device.click_with_backend.assert_called_once_with(x=9, y=9, backend='minitouch', control_name='Click')
        device.click.assert_not_called()
        control = self._control()
        control.click(1, 2, control_name='N')
        control.click_adb.assert_called_once_with(1, 2)
        control.handle_control_check.assert_called_once_with('N')   # 默认路径行为不变


class BoundsPolicyTest(unittest.TestCase):
    """CASE 39 / 40：各坐标语义的采样策略。"""

    def test_case39_policies(self):
        with patch.object(ClickSampler, 'sample_target', return_value=(1, 1)) as st, \
                patch.object(ClickSampler, 'sample_region', return_value=(2, 2)) as sr:
            resolve_click_point(ClickBounds((10, 10, 40, 20), 'ocr_box'))
            resolve_click_point(ClickBounds((10, 10, 40, 20), 'area_1', native=True))
            resolve_click_point(ClickRegion((10, 10, 40, 20), 'region'))
        st.assert_called_once_with((10, 10, 40, 20), 'ocr_box')
        self.assertEqual(sr.call_args_list[0].args, ((10, 10, 40, 20), None))
        self.assertEqual(sr.call_args_list[1].args, ((10, 10, 40, 20), 'region'))

    def test_case39_degenerate_game_bounds_fall_back_to_centre(self):
        with _forbid_sampling():
            self.assertEqual(resolve_click_point(ClickBounds((10, 20, 0, 6), 'ocr')), (10, 23))

    def test_case40_final_point_is_identity_for_every_value_shape(self):
        with _forbid_sampling():
            for raw, expected in (((5, 6), (5, 6)), ((5.9, 6.1), (5, 6)), ((np.int64(7), np.float32(8.8)), (7, 8))):
                self.assertEqual(resolve_click_point(FinalPoint(*raw)), expected)


class StaticMigrationGuardTest(unittest.TestCase):
    """CASE 36 / 37 / 42–45：全仓静态守卫（按「文件 + 函数」而非行号）。"""

    # 仍直接调用 device.click 的函数。Stage 3B（2026-09-21）之后生产直接单击只剩执行器自身：
    # Login / DailyTrifles / WeeklyPurchase 的原项目排除豁免已取消（点击架构不因业务排除而豁免）。
    # 全局规则见 `dev_tools/click_entry_guard.py` 与 `tests/test_l1_stage3b_global_guard.py`。
    # synevo 分支唯一的业务豁免：原有账号切换控件点击（原生 bounds 取中心直点），用户决定保留原
    # 实现，不接入 L1 / L2。与 `dev_tools/click_entry_guard.BUSINESS_EXEMPTIONS` 一一对应，同样
    # 精确到函数与次数：该函数多出任何一处裸点击都会让本守卫失败。
    CANONICAL_DIRECT_CLICKS = {
        ('module/click_pipeline.py', 'execute_single_click'): 1,
        ('tasks/Component/SwitchAccount/netease_account_ui.py', '_click_bounds'): 1,
    }
    _RANDOM_CALLS = {'randint', 'uniform', 'random_point_in_roi', 'random_rectangle_point', 'random_normal_distribution'}
    # 点击旁边仍保留业务自带随机偏移的函数（精确到 文件 + 函数 + 随机调用序列）。
    # synevo 分支决定保留组队列表原有的 ±5 抖动落点语义，整合只把执行入口收口到 L1，
    # 不改分布；该函数多出或少掉任何一次随机调用都会让本守卫失败。
    RANDOM_OFFSET_EXEMPTIONS = [
        ('tasks/Component/GeneralRoom/general_room.py', 'check_zones', ['randint', 'randint']),
    ]

    @classmethod
    def setUpClass(cls):
        cls.direct_clicks = {}
        cls.backend_calls = []
        cls.click_with_random = []
        for sub in ('module', 'tasks'):
            for path in sorted((_REPO / sub).rglob('*.py')):
                rel = path.relative_to(_REPO).as_posix()
                cls._scan(rel, ast.parse(path.read_text(encoding='utf-8', errors='ignore')))

    @staticmethod
    def _call_name(node):
        func = node.func
        return func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')

    @staticmethod
    def _is_device_click(node):
        func = node.func
        return (isinstance(func, ast.Attribute) and func.attr == 'click' and (
            (isinstance(func.value, ast.Attribute) and func.value.attr == 'device')
            or (isinstance(func.value, ast.Name) and func.value.id == 'device')))

    @classmethod
    def _scan(cls, rel, tree):
        def visit(node, owner):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls = [n for n in ast.walk(child) if isinstance(n, ast.Call)]
                    clicks = any(cls._is_device_click(n) or cls._call_name(n) == 'execute_single_click' for n in calls)
                    randoms = [cls._call_name(n) for n in calls if cls._call_name(n) in cls._RANDOM_CALLS]
                    if clicks and randoms:
                        cls.click_with_random.append((rel, child.name, randoms))
                    visit(child, child.name)
                    continue
                if isinstance(child, ast.Call):
                    if cls._is_device_click(child):
                        key = (rel, owner)
                        cls.direct_clicks[key] = cls.direct_clicks.get(key, 0) + 1
                    if cls._call_name(child) in ('click_minitouch', 'click_window_message') \
                            and not rel.startswith('module/device/'):
                        cls.backend_calls.append((rel, owner))
                visit(child, owner)
        visit(tree, '<module>')

    def test_case36_no_direct_backend_bypass_outside_device_layer(self):
        self.assertEqual(self.backend_calls, [])

    def test_case36_direct_device_click_only_in_canonical_allowlist(self):
        self.assertEqual(self.direct_clicks, self.CANONICAL_DIRECT_CLICKS)

    def test_case37_no_local_random_offset_next_to_a_click(self):
        self.assertEqual(self.click_with_random, self.RANDOM_OFFSET_EXEMPTIONS)

    def test_case42_to_44_new_dispatch_code_has_no_timing_screenshot_or_retry(self):
        from tasks.Hyakkiyakou.slave.hya_device import HyaDevice
        for fn in (Control.click_with_backend, Control._dispatch_click, cp.list_click_target, HyaDevice.fast_click):
            with self.subTest(fn=fn.__qualname__):
                tree = ast.parse(inspect.getsource(fn).strip())
                names = {n.id if isinstance(n, ast.Name) else n.attr
                         for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Attribute))}
                for forbidden in ('sleep', 'random_delay', 'confirm_delay', 'Timer', 'screenshot',
                                  'REACTION_FAST', 'REACTION_FIRE'):
                    self.assertNotIn(forbidden, names)
                self.assertFalse(any(isinstance(n, (ast.While, ast.For)) for n in ast.walk(tree)))

    def test_case45_no_multi_click_consumer_anywhere(self):
        hits = []
        for sub in ('module', 'tasks'):
            for path in (_REPO / sub).rglob('*.py'):
                tree = ast.parse(path.read_text(encoding='utf-8', errors='ignore'))
                if any(isinstance(n, ast.Call) and self._call_name(n) == 'multi_click' for n in ast.walk(tree)):
                    hits.append(path.relative_to(_REPO).as_posix())
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
