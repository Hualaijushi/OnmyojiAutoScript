# This Python file uses the following encoding: utf-8
"""L1 Stage 2：剩余 9 个生产直接单击迁到 `execute_single_click`（坐标 / 采样 / 次数 / 等待与迁移前完全等价）。

迁移原则：**采样仍在原位置、用原采样函数与原参数**，已确定的坐标以 `FinalPoint` 交给执行器（执行器对它零采样）；
只有 `_sample_settlement_click` 用 `ClickRegion`——它的解析恰好就是同一个 `ClickSampler.sample_region(roi, name)`。

等价性证明方式（不是「当前实现对比当前实现」）：
1. **固定随机源对照**：把 `module.click_sampler._rng` 与 `module.base.utils.random._rng` 换成同一个 `random.Random(seed)`；
   「参考」直接调用**迁移前代码的采样表达式**（例如 `ClickSampler.sample_target(select_area, rule.name)`、
   `rule.coord()` ×2、`ClickSampler.sample_point(roi, wide_card)`），迁移后的真实函数在同一个 seed 下驱动，
   后端收到的坐标必须逐个相等。
2. **调用契约**：包装采样器记录每次调用的（种类, ROI, 身份 / profile），断言次数、参数与迁移前一致，且没有多出的
   其它采样函数调用；断言执行器收到的是 `FinalPoint`（区域点击是 `ClickRegion`）、`control_name` 与迁移前一致。
3. **副作用**：截图 / 识别 / 等待次数与迁移前一致；BehaviorTrace 记录的坐标 = 后端实际收到的坐标。
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

import numpy as np

from module import behavior_trace
from module.atom.click import RuleClick
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import ClickRegion, FinalPoint, execute_single_click
from module.click_profile import DEFAULT_PROFILES
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.exception import GamePageUnknownError

_REPO = Path(__file__).resolve().parents[1]
SEED = 20260921
EXECUTOR_MODULES = (
    'tasks.Chess.runtime.round_state',
    'tasks.Component.GeneralBattle.general_battle',
    'tasks.Component.GeneralInvite.general_invite',
    'tasks.GameUi.navigator',
    'tasks.KekkaiUtilize.script_task',
    'tasks.RyouToppa.script_task',
    'tasks.Secret.script_task',
    'tasks.SixRealms.peacock_kingdom.base_peacock_kingdom',
)


@contextmanager
def seeded(seed=SEED):
    """所有空间采样共用同一个可复现的随机源（`click_sampler` 与 `random_point_in_roi` / `random_normal` 各持有一份引用）。"""
    rng = random.Random(seed)
    with patch('module.click_sampler._rng', rng), patch('module.base.utils.random._rng', rng):
        yield


class Stage2Harness(TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.addCleanup(self._restore)
        self.addCleanup(reset_behavior_traces)
        self.events = []
        self.backend = Mock(name='backend', side_effect=lambda x, y: self.events.append(('backend', x, y)))
        configure_behavior_trace('stage2', enabled=True)

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    def control(self):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(
            config_name='stage2', script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        c.click_methods = {'minitouch': self.backend}
        c.image = np.zeros((720, 1280, 3), dtype=np.uint8)
        c.image_frame_id = 'frame'
        return c

    def run_wrapped(self, fn, seed=SEED):
        """固定随机源下运行 `fn()`；包装 3 个采样入口与 8 个模块里的执行器，记录调用。"""
        originals = {name: getattr(ClickSampler, name) for name in ('sample_target', 'sample_region', 'sample_point')}

        def wrap(name):
            def recorder(roi, arg=None, *a, **k):
                shown = arg.name if name == 'sample_point' else arg
                self.events.append((name, tuple(roi), shown))
                return originals[name](roi, arg, *a, **k)
            return recorder

        def executor(device, target, control_name=None, backend=None):
            self.events.append(('execute', target, control_name))
            return execute_single_click(device, target, control_name=control_name, backend=backend)

        patches = [patch.object(ClickSampler, name, side_effect=wrap(name)) for name in originals]
        patches += [patch(f'{m}.execute_single_click', side_effect=executor) for m in EXECUTOR_MODULES]
        for p in patches:
            p.start()
        try:
            with seeded(seed):
                return fn()
        finally:
            for p in reversed(patches):
                p.stop()

    # ---- 断言辅助 ----
    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def backend_points(self):
        return [(e[1], e[2]) for e in self.of('backend')]

    def executed(self):
        return [(e[1], e[2]) for e in self.of('execute')]

    def trace_points(self):
        files = list(behavior_trace._LOG_DIR.glob('stage2_*.jsonl'))
        rows = [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []
        return [(r['target'], r['extra']['x'], r['extra']['y']) for r in rows]

    def assert_trace_matches_backend(self, names):
        self.assertEqual(self.trace_points(), [(n, x, y) for n, (x, y) in zip(names, self.backend_points())])


def _reference(fn, seed=SEED):
    """迁移前的采样表达式在同一个 seed 下的结果。"""
    with seeded(seed):
        return fn()


# ======================================================================================
# 1. Chess：两次点击各自独立采样
# ======================================================================================

class ChessRefreshTest(Stage2Harness):
    def test_two_clicks_sample_independently_like_before(self):
        from tasks.Chess.runtime.round_state import ChessRoundStateMixin
        rule = RuleClick((820, 420, 90, 60), (820, 420, 90, 60), 'grigri_refresh_1')
        fake = SimpleNamespace(_grigri_refresh_remaining=[2, 2, 2], C_GRIGRI_REFRESH_1=rule, FAST_OPERATION_INTERVAL=0.1,
                               ACTION_SETTLE_INTERVAL=0.2, device=self.control(), screenshot=Mock())
        expected = _reference(lambda: [rule.coord(), rule.coord()])          # 原写法：每次点击各自 coord()
        with patch('tasks.Chess.runtime.round_state.time.sleep') as sleep:
            ok = self.run_wrapped(lambda: ChessRoundStateMixin._refresh_grigri_option(fake, {'index': 1, 'score': 1.5}))
        self.assertTrue(ok)
        self.assertEqual(self.backend_points(), expected)
        self.assertEqual(self.of('sample_target'), [('sample_target', (820, 420, 90, 60), 'grigri_refresh_1')] * 2)
        self.assertEqual(len(self.of('sample_region')) + len(self.of('sample_point')), 0)
        self.assertTrue(all(isinstance(t, FinalPoint) for t, _ in self.executed()))
        self.assertEqual([n for _, n in self.executed()], ['grigri_refresh_1_1', 'grigri_refresh_1_2'])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.1, 0.1, 0.2])      # 等待次数与顺序不变
        self.assertEqual(fake.screenshot.call_count, 1)
        self.assertEqual(fake._grigri_refresh_remaining, [1, 2, 2])
        self.assert_trace_matches_backend(['grigri_refresh_1_1', 'grigri_refresh_1_2'])


# ======================================================================================
# 2 / 3. GeneralBattle Settlement：区域点击 = 一次 sample_region；锚点点击 = 零采样、burst 内复用
# ======================================================================================

class SettlementTest(Stage2Harness):
    def _gb(self):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        return GeneralBattle

    def test_sample_settlement_click_is_one_region_sample_and_one_click(self):
        GB = self._gb()
        rule = GB.C_RANDOM_DEFAULT
        fake = SimpleNamespace(device=self.control())
        expected = _reference(lambda: ClickSampler.sample_region(rule.roi_front, rule.name))   # 原写法
        self.run_wrapped(lambda: GB._sample_settlement_click(fake, rule))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_region'), [('sample_region', tuple(rule.roi_front), rule.name)])
        self.assertEqual(len(self.of('sample_target')) + len(self.of('sample_point')), 0)   # 不是 Point 模型
        (target, name), = self.executed()
        self.assertEqual(target, ClickRegion(rule.roi_front, rule.name))                    # Region 语义显式声明
        self.assertEqual(name, rule.name)
        self.assert_trace_matches_backend([rule.name])

    def test_click_settlement_point_never_samples(self):
        GB = self._gb()
        fake = SimpleNamespace(device=self.control())
        self.run_wrapped(lambda: GB._click_settlement_point(fake, (812, 511), 'random_default'))
        for kind in ('sample_target', 'sample_region', 'sample_point'):
            self.assertEqual(self.of(kind), [])                              # 已定锚点：任何采样入口都没被调用
        self.assertEqual(self.backend_points(), [(812, 511)])
        self.assertEqual(self.executed(), [(FinalPoint(812, 511), 'random_default')])
        self.assert_trace_matches_backend(['random_default'])

    def test_burst_samples_one_anchor_and_reuses_it(self):
        GB = self._gb()
        rule = GB.C_RANDOM_SAVE_RIGHT
        fake = SimpleNamespace(device=self.control())

        def burst():
            anchor = GB._sample_settlement_point(fake, rule)             # 采样一次锚点
            GB._click_settlement_point(fake, anchor, rule.name)          # 首击
            GB._click_settlement_point(fake, anchor, rule.name)          # burst 内复用：同一个点，不重新采样
            return anchor
        expected = _reference(lambda: ClickSampler.sample_region(rule.roi_front, rule.name))
        anchor = self.run_wrapped(burst)
        self.assertEqual(anchor, expected)
        self.assertEqual(len(self.of('sample_region')), 1)               # 一个 burst 只采样一次
        self.assertEqual(self.backend_points(), [anchor, anchor])         # 点击两次、坐标完全相同
        self.assertEqual(self.executed(), [(FinalPoint(*anchor), rule.name)] * 2)
        self.assert_trace_matches_backend([rule.name, rule.name])


# ======================================================================================
# 4. GeneralInvite._detect_select：sample_target(OCR 框, rule.name) 原样保留
# ======================================================================================

class DetectSelectTest(Stage2Harness):
    AREA = (300, 200, 120, 40)

    def _fake(self, area, wait_result=True):
        rule1 = SimpleNamespace(name='O_FRIEND_NAME_1')
        rule2 = SimpleNamespace(name='O_FRIEND_NAME_2')
        finder = Mock(side_effect=lambda rule, name: area)
        return SimpleNamespace(
            screenshot=Mock(), I_SELECTED=SimpleNamespace(match_all_any=Mock(return_value=[])), device=self.control(),
            O_FRIEND_NAME_1=rule1, O_FRIEND_NAME_2=rule2, _find_exact_friend_area=finder,
            _wait_selected_appear=Mock(return_value=wait_result)), rule1

    def test_click_uses_the_original_sample_target_on_the_ocr_box(self):
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        fake, rule = self._fake(self.AREA)
        expected = _reference(lambda: ClickSampler.sample_target(self.AREA, rule.name))
        self.assertTrue(self.run_wrapped(lambda: GeneralInvite._detect_select(fake, '好友')))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_target'), [('sample_target', self.AREA, 'O_FRIEND_NAME_1')])
        (target, name), = self.executed()
        self.assertIsInstance(target, FinalPoint)                          # 没有改成 ClickBounds（退化框 / 浮点框处理不同）
        self.assertEqual(name, 'O_FRIEND_NAME_1')
        fake._wait_selected_appear.assert_called_once_with(0)
        self.assert_trace_matches_backend(['O_FRIEND_NAME_1'])

    def test_no_exact_friend_means_zero_samples_and_zero_clicks(self):
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        fake, _ = self._fake(None)
        self.assertFalse(self.run_wrapped(lambda: GeneralInvite._detect_select(fake, '好友')))
        self.assertEqual(self.events, [])

    def test_failed_selection_retries_with_an_independent_sample_each_time(self):
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        fake, rule = self._fake(self.AREA, wait_result=False)
        expected = _reference(lambda: [ClickSampler.sample_target(self.AREA, rule.name) for _ in range(3)])
        self.assertFalse(self.run_wrapped(lambda: GeneralInvite._detect_select(fake, '好友')))
        self.assertEqual(self.backend_points(), expected)                   # max_retry=3：3 次各自独立采样、点击
        self.assertEqual(len(self.of('sample_target')), 3)


# ======================================================================================
# 5. Navigator._execute_action：RuleClick 即时点击，不新增等待 / 截图
# ======================================================================================

class NavigatorActionTest(Stage2Harness):
    def test_rule_click_without_interval_is_one_sample_one_click_no_wait(self):
        from tasks.GameUi.navigator import GameUi
        rule = RuleClick((100, 600, 80, 50), (100, 600, 80, 50), 'nav_click')
        fake = SimpleNamespace(maybe_screenshot=Mock(), device=self.control())
        expected = _reference(lambda: rule.coord())
        with patch('time.sleep') as sleep:
            self.assertTrue(self.run_wrapped(lambda: GameUi._execute_action(fake, rule, skip_first_screenshot=True)))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_target'), [('sample_target', (100, 600, 80, 50), 'nav_click')])
        self.assertEqual(self.executed(), [(FinalPoint(*expected), 'nav_click')])
        sleep.assert_not_called()                                           # 导航不新增等待
        fake.maybe_screenshot.assert_called_once_with(True)                 # 只有原来的那一次（复用当前截图）
        self.assert_trace_matches_backend(['nav_click'])


# ======================================================================================
# 6. KekkaiUtilize.switch_friend_list：目标图片未出现时沿用资产 ROI，不新增识别 / 重试
# ======================================================================================

class _FakeTimer:
    """点击计时器（limit == 1）每次放行；总超时计时器按 `timeout_after` 次 `reached()` 后触发。"""
    timeout_after = 10 ** 9

    def __init__(self, limit=0, *a, **k):
        self.limit = limit
        self.calls = 0

    def start(self):
        return self

    def reset(self):
        return self

    def reached(self):
        if self.limit == 1:
            return True
        self.calls += 1
        return self.calls > type(self).timeout_after


class KekkaiFriendListTest(Stage2Harness):
    def _fake(self, appear_results):
        from tasks.KekkaiUtilize.script_task import ScriptTask as KU
        results = iter(appear_results)
        appear = Mock(side_effect=lambda target, *a, **k: next(results))
        fake = SimpleNamespace(screenshot=Mock(), appear=appear, device=self.control(),
                               I_UTILIZE_FRIEND_GROUP=KU.I_UTILIZE_FRIEND_GROUP, I_UTILIZE_ZONES_GROUP=KU.I_UTILIZE_ZONES_GROUP,
                               SWITCH_FRIEND_LIST_TIMEOUT=KU.SWITCH_FRIEND_LIST_TIMEOUT)
        return KU, fake

    def test_click_uses_the_asset_roi_once_and_adds_no_recognition(self):
        from tasks.KekkaiUtilize.config import SelectFriendList
        KU, fake = self._fake([False, True])
        asset = KU.I_UTILIZE_FRIEND_GROUP
        roi = tuple(asset.roi_front)
        expected = _reference(lambda: asset.coord())
        _FakeTimer.timeout_after = 10 ** 9
        with patch('tasks.KekkaiUtilize.script_task.Timer', _FakeTimer), patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            self.run_wrapped(lambda: KU.switch_friend_list(fake, SelectFriendList.SAME_SERVER))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_target'), [('sample_target', roi, asset.name)])
        self.assertEqual(self.executed(), [(FinalPoint(*expected), asset.name)])
        self.assertEqual(fake.screenshot.call_count, 2)                     # 与迁移前一致：未出现 → 点 → 再截图确认
        self.assertEqual(fake.appear.call_count, 2)                         # 没有额外识别
        self.assertTrue(all(c.args[0] is asset for c in fake.appear.call_args_list))
        self.assert_trace_matches_backend([asset.name])

    def test_timeout_still_raises_and_clicks_once_per_loop_before_it(self):
        from tasks.KekkaiUtilize.config import SelectFriendList
        KU, fake = self._fake([False] * 10)
        _FakeTimer.timeout_after = 2
        with patch('tasks.KekkaiUtilize.script_task.Timer', _FakeTimer), patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            with self.assertRaises(GamePageUnknownError):
                self.run_wrapped(lambda: KU.switch_friend_list(fake, SelectFriendList.SAME_SERVER))
        self.assertEqual(len(self.of('sample_target')), 2)                  # 超时前每圈一次点击，超时不再点
        self.assertEqual(len(self.backend_points()), 2)


# ======================================================================================
# 7. RyouToppa._click_toppa_area：保留 sample_point(roi, wide_card) 显式 opt-in
# ======================================================================================

class RyouToppaAreaTest(Stage2Harness):
    def test_area_1_keeps_sample_point_with_wide_card(self):
        from tasks.RyouToppa.script_task import ScriptTask, area_map
        rule = area_map[0]['rule_click']
        fake = ScriptTask.__new__(ScriptTask)
        fake.device = self.control()
        expected = _reference(lambda: ClickSampler.sample_point(rule.roi_front, DEFAULT_PROFILES['wide_card']))
        self.run_wrapped(lambda: fake._click_toppa_area(0))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_point'), [('sample_point', tuple(rule.roi_front), 'wide_card')])   # wide_card 没有丢
        self.assertEqual(len(self.of('sample_target')) + len(self.of('sample_region')), 0)
        self.assertEqual(self.executed(), [(FinalPoint(*expected), 'area_1')])
        self.assert_trace_matches_backend(['area_1'])

    def test_other_areas_keep_the_default_rule_click_path(self):
        from tasks.RyouToppa.script_task import ScriptTask, area_map
        rule = area_map[1]['rule_click']
        fake = ScriptTask.__new__(ScriptTask)
        fake.device = self.control()
        fake.interval_timer = {}
        expected = _reference(lambda: rule.coord())
        self.run_wrapped(lambda: fake._click_toppa_area(1))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(len(self.of('sample_point')), 0)                   # 区域 2~8 仍不走显式 opt-in


# ======================================================================================
# 8. Secret.find_battle：人工划定的 click_roi 不变，两次点击各自独立采样
# ======================================================================================

class _FakeStatusOcr:
    def __init__(self, *a, **k):
        pass

    def ocr(self, image):
        return '未通关'


class SecretFindBattleTest(Stage2Harness):
    def test_two_clicks_sample_the_hand_carved_roi_independently(self):
        from tasks.Secret.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.device = self.control()
        task.screenshot = Mock()
        task.appear = Mock(return_value=False)
        result = SimpleNamespace(ocr_text='壹·标题', box=np.array([[10, 100], [80, 100], [80, 130], [10, 130]]))
        task.layer_title_ocr = SimpleNamespace(detect_and_ocr=lambda image: [result])
        # 卡片几何（独立于被测代码，由常量推出）：title_top = 132 + 100 = 232 → card_top = 222；click_roi = (194+12, 222+8, 216, 121-16)
        click_roi = (206, 230, 216, 105)
        name = 'secret_layer_1_card'
        expected = _reference(lambda: [RuleClick(click_roi, click_roi, name).coord() for _ in range(2)])
        with patch('tasks.Secret.script_task.RuleOcr', _FakeStatusOcr), patch('tasks.Secret.script_task.time.sleep') as sleep:
            layer = self.run_wrapped(lambda: task.find_battle())
        self.assertEqual(layer, 1)
        self.assertEqual(self.backend_points(), expected)
        self.assertEqual(self.of('sample_target'), [('sample_target', click_roi, name)] * 2)   # ROI 没有被扩大 / 改成整卡
        self.assertTrue(all(isinstance(t, FinalPoint) for t, _ in self.executed()))
        self.assertEqual([n for _, n in self.executed()], ['SECRET_LAYER_1_SELECT_1', 'SECRET_LAYER_1_SELECT_2'])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.4, 0.4])         # 点击间隔不变
        self.assert_trace_matches_backend(['SECRET_LAYER_1_SELECT_1', 'SECRET_LAYER_1_SELECT_2'])


# ======================================================================================
# 9. 孔雀国 _mark_peacock_boss：固定 ROI，一次 coord()
# ======================================================================================

class PeacockMarkTest(Stage2Harness):
    def _fake(self, local_clicked):
        from tasks.SixRealms.peacock_kingdom.base_peacock_kingdom import BasePeacockKingdom
        fake = SimpleNamespace(screenshot=Mock(), appear=Mock(return_value=False),
                               appear_then_click=Mock(return_value=local_clicked), I_PREPARE_HIGHLIGHT=object(),
                               I_LOCAL=object(), C_PK_GREEN_MAIN=BasePeacockKingdom.C_PK_GREEN_MAIN, device=self.control())
        return BasePeacockKingdom, fake

    def test_green_main_is_sampled_once_and_clicked_once(self):
        cls, fake = self._fake(local_clicked=True)
        rule = cls.C_PK_GREEN_MAIN
        expected = _reference(lambda: rule.coord())
        with patch('tasks.SixRealms.peacock_kingdom.base_peacock_kingdom.time.sleep') as sleep:
            self.run_wrapped(lambda: cls._mark_peacock_boss(fake))
        self.assertEqual(self.backend_points(), [expected])
        self.assertEqual(self.of('sample_target'), [('sample_target', tuple(rule.roi_front), rule.name)])
        self.assertEqual(self.executed(), [(FinalPoint(*expected), rule.name)])
        sleep.assert_called_once_with(0.3)                                  # I_LOCAL 点到后的 0.3s 等待不变
        self.assertEqual(fake.screenshot.call_count, 1)
        self.assert_trace_matches_backend([rule.name])

    def test_without_local_click_no_wait(self):
        cls, fake = self._fake(local_clicked=False)
        with patch('tasks.SixRealms.peacock_kingdom.base_peacock_kingdom.time.sleep') as sleep:
            self.run_wrapped(lambda: cls._mark_peacock_boss(fake))
        sleep.assert_not_called()
        self.assertEqual(len(self.backend_points()), 1)


# ======================================================================================
# 静态守卫（AST）：9 个函数没有裸 device.click；采样函数与参数保持；无新增等待
# ======================================================================================

def _func(rel, qual):
    text = (_REPO / rel).read_text(encoding='utf-8')
    tree = ast.parse(text)
    cls_name, _, name = qual.rpartition('.')
    for node in ast.walk(tree):
        if cls_name and isinstance(node, ast.ClassDef) and node.name == cls_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
        if not cls_name and isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f'{rel}::{qual}')


def _calls(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _name(call):
    f = call.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return '.'.join(reversed(parts))


SITES = (
    # (文件, 类.函数, 执行器调用次数, 第一个实参构造器)
    ('tasks/Chess/runtime/round_state.py', 'ChessRoundStateMixin._refresh_grigri_option', 1, 'FinalPoint'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'GeneralBattle._sample_settlement_click', 1, 'ClickRegion'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'GeneralBattle._click_settlement_point', 1, 'FinalPoint'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'GeneralInvite._detect_select', 1, 'FinalPoint'),
    ('tasks/GameUi/navigator.py', 'GameUi._execute_action', 1, 'FinalPoint'),
    ('tasks/KekkaiUtilize/script_task.py', 'ScriptTask.switch_friend_list', 1, 'FinalPoint'),
    ('tasks/RyouToppa/script_task.py', 'ScriptTask._click_toppa_area', 1, 'FinalPoint'),
    ('tasks/Secret/script_task.py', 'ScriptTask.find_battle', 1, 'FinalPoint'),
    ('tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py', 'BasePeacockKingdom._mark_peacock_boss', 1, 'FinalPoint'),
)


class StaticGuardTest(TestCase):
    def test_no_direct_device_click_and_one_executor_call_with_the_right_target(self):
        for rel, qual, count, ctor in SITES:
            with self.subTest(site=f'{rel}::{qual}'):
                fn = _func(rel, qual)
                calls = _calls(fn)
                self.assertEqual([c.lineno for c in calls if _name(c).endswith('device.click')], [])
                execs = [c for c in calls if _name(c) == 'execute_single_click']
                self.assertEqual(len(execs), count)
                for call in execs:
                    self.assertEqual(_name(call.args[1]) if isinstance(call.args[1], ast.Call) else None, ctor)
                    self.assertTrue(any(kw.arg == 'control_name' for kw in call.keywords))

    def test_original_sampling_calls_are_kept_in_place(self):
        expected = {
            ('tasks/Component/GeneralInvite/general_invite.py', 'GeneralInvite._detect_select'): ['ClickSampler.sample_target'],
            ('tasks/RyouToppa/script_task.py', 'ScriptTask._click_toppa_area'): ['ClickSampler.sample_point'],
            ('tasks/Chess/runtime/round_state.py', 'ChessRoundStateMixin._refresh_grigri_option'): ['refresh_rule.coord'],
            ('tasks/Secret/script_task.py', 'ScriptTask.find_battle'): ['click_rule.coord'],
            ('tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py', 'BasePeacockKingdom._mark_peacock_boss'): ['self.C_PK_GREEN_MAIN.coord'],
            ('tasks/KekkaiUtilize/script_task.py', 'ScriptTask.switch_friend_list'): ['check_image.coord'],
            ('tasks/GameUi/navigator.py', 'GameUi._execute_action'): ['action.coord'],
        }
        for (rel, qual), names in expected.items():
            with self.subTest(site=qual):
                got = [_name(c) for c in _calls(_func(rel, qual)) if _name(c).endswith(('sample_target', 'sample_point', '.coord'))]
                self.assertEqual(got, names)
        # GeneralInvite 没有改成 ClickBounds；结算区域点击不含 sample_target
        self.assertNotIn('ClickBounds', ast.dump(_func('tasks/Component/GeneralInvite/general_invite.py', 'GeneralInvite._detect_select')))
        settle = _func('tasks/Component/GeneralBattle/general_battle.py', 'GeneralBattle._click_settlement_point')
        self.assertEqual([_name(c) for c in _calls(settle) if 'sample' in _name(c)], [])      # 锚点点击零采样

    def test_navigator_and_kekkai_click_paths_add_no_new_waits(self):
        nav = _func('tasks/GameUi/navigator.py', 'GameUi._execute_action')
        self.assertEqual([c.lineno for c in _calls(nav) if _name(c).endswith('sleep')], [])
        kekkai = _func('tasks/KekkaiUtilize/script_task.py', 'ScriptTask.switch_friend_list')
        appear_calls = [c for c in _calls(kekkai) if _name(c) == 'self.appear']
        self.assertEqual(len(appear_calls), 1)                                                # 仍只有循环里那一次识别
