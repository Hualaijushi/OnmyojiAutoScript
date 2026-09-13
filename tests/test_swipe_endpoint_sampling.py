"""Swipe Endpoint Sampling v2（`module/atom/swipe_endpoint.py`，D022）回归护栏。

普通滑动的起点 / 终点从旧 `RuleSwipe.coord()` 的窄中心偏置（tiny ROI 里有效 σ≈3~6px、
同类滑动挤成一簇）改为：起终点各自独立采样、主成分集中 + 少量更宽尾部、夹到安全范围，
并联合保证方向 / 有效距离不被破坏；两端两轴 ROI 都足够大时逐字保持旧 `_center_biased_int`。

不改 `TouchSwipeModel` 中间轨迹算法；不改 `RuleSwipe.coord()`（保留给兼容 / 测试）。
参数 `SwipeEndpointParams` 全部 provisional，等 Level C 标定。
"""

import inspect
import math
import statistics
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.atom.swipe import RuleSwipe
from module.atom import swipe_endpoint as se
from module.atom.swipe_endpoint import (
    SwipeEndpointParams,
    sample_swipe_endpoints,
)

# 代表性真实资产（roi_front, roi_back）
A_LEVEL_UP = ((1142, 328, 21, 21), (1143, 444, 21, 21))       # 向下 ~116
A_BG_RIGHT = ((1093, 148, 21, 21), (397, 140, 21, 21))        # 向左 ~696
A_SHIKI_ONE = ((977, 582, 21, 21), (889, 584, 21, 22))        # 向左 ~88
A_BUFF_UP = ((397, 124, 456, 35), (447, 457, 386, 37))        # x 宽 / y 窄
A_BATTLE_L = ((122, 155, 480, 426), (667, 147, 461, 427))     # 两端两轴都宽
A_SUMMON_3 = ((401, 123, 100, 440), (762, 122, 100, 434))     # 两端两轴都宽
A_AB_CORNER = ((0, 0, 10, 10), (570, 270, 10, 10))            # 起点贴角
A_WQ_LIST = ((60, 250, 2, 4), (65, 200, 2, 4))                # 极小 ROI

ALL_ASSETS = [A_LEVEL_UP, A_BG_RIGHT, A_SHIKI_ONE, A_BUFF_UP,
              A_BATTLE_L, A_SUMMON_3, A_AB_CORNER, A_WQ_LIST]


def _center(roi):
    x, y, w, h = roi
    return x + (w - 1) / 2.0, y + (h - 1) / 2.0


def _base_vec(rf, rb):
    cfx, cfy = _center(rf)
    cbx, cby = _center(rb)
    return cbx - cfx, cby - cfy


# --------------------------------------------------------------------------------------
# 参数校验
# --------------------------------------------------------------------------------------
class SwipeEndpointParamsTest(TestCase):
    def test_defaults_construct_and_are_frozen(self):
        p = SwipeEndpointParams()
        self.assertGreater(p.wide_axis_px, 2)
        with self.assertRaises(Exception):
            p.core_weight = 0.5  # frozen

    def test_rejects_illegal_values(self):
        bad = [
            dict(wide_axis_px=1),
            dict(offset_min_px=0),
            dict(offset_min_px=30, offset_max_px=10),
            dict(offset_dist_ratio=0),
            dict(core_weight=0.0),
            dict(core_weight=1.5),
            dict(min_cos=1.0),
            dict(min_cos=-0.1),
            dict(min_dist_ratio=0.0),
            dict(min_dist_ratio=1.2),          # > 1
            dict(max_dist_ratio=0.9),          # < 1
            dict(abs_min_dist_px=-1),
            dict(axis_max_attempts=0),
            dict(joint_max_attempts=0),
            dict(screen_x_hi=1, screen_x_lo=2),
        ]
        for kw in bad:
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    SwipeEndpointParams(**kw)

    def test_roi_type_and_shape_validation(self):
        with self.assertRaises(TypeError):
            sample_swipe_endpoints((1.0, 2, 3, 4), (5, 6, 7, 8))
        with self.assertRaises(ValueError):
            sample_swipe_endpoints((1, 2, 0, 4), (5, 6, 7, 8))
        with self.assertRaises(ValueError):
            sample_swipe_endpoints((1, 2, 3, 4), (5, 6, 7, -1))


# --------------------------------------------------------------------------------------
# 输出形状 / 边界
# --------------------------------------------------------------------------------------
class OutputShapeTest(TestCase):
    def test_returns_four_ints(self):
        for rf, rb in ALL_ASSETS:
            for _ in range(200):
                out = sample_swipe_endpoints(rf, rb)
                self.assertEqual(len(out), 4)
                self.assertTrue(all(isinstance(v, int) for v in out), out)

    def test_never_leaves_screen_safe_box(self):
        p = SwipeEndpointParams()
        for rf, rb in ALL_ASSETS:
            for _ in range(3000):
                sx, sy, ex, ey = sample_swipe_endpoints(rf, rb)
                for x in (sx, ex):
                    self.assertGreaterEqual(x, p.screen_x_lo)
                    self.assertLessEqual(x, p.screen_x_hi)
                for y in (sy, ey):
                    self.assertGreaterEqual(y, p.screen_y_lo)
                    self.assertLessEqual(y, p.screen_y_hi)

    def test_corner_roi_never_negative(self):
        # 起点 ROI (0,0,10,10)：高斯在角上会大量越界，必须夹到 screen_lo，不出负坐标
        for _ in range(5000):
            sx, sy, ex, ey = sample_swipe_endpoints(*A_AB_CORNER)
            self.assertGreaterEqual(sx, 2)
            self.assertGreaterEqual(sy, 2)


# --------------------------------------------------------------------------------------
# 起点 / 终点各自独立建模（不是给整条线加共同平移 → 平行线）
# --------------------------------------------------------------------------------------
class StartEndModeledSeparatelyTest(TestCase):
    def test_endpoint_vector_length_and_angle_vary(self):
        # 若为「共同平移」，(end-start) 向量恒定 → 长度方差、角度方差都 ≈ 0
        S = [sample_swipe_endpoints(*A_LEVEL_UP) for _ in range(8000)]
        lengths = [math.hypot(s[2] - s[0], s[3] - s[1]) for s in S]
        angles = [math.atan2(s[3] - s[1], s[2] - s[0]) for s in S]
        self.assertGreater(statistics.pstdev(lengths), 3.0)   # 长度真的在变
        self.assertGreater(statistics.pstdev(angles), 0.01)   # 角度也在变

    def test_start_and_end_each_have_spread(self):
        S = [sample_swipe_endpoints(*A_SHIKI_ONE) for _ in range(8000)]
        self.assertGreater(statistics.pstdev([s[0] for s in S]), 2.0)
        self.assertGreater(statistics.pstdev([s[1] for s in S]), 2.0)
        self.assertGreater(statistics.pstdev([s[2] for s in S]), 2.0)
        self.assertGreater(statistics.pstdev([s[3] for s in S]), 2.0)

    def test_start_and_end_are_statistically_independent(self):
        # 共同平移会让 start_x 与 end_x 完全相关（corr≈1）。独立采样下相关性应很低。
        S = [sample_swipe_endpoints(*A_LEVEL_UP) for _ in range(12000)]
        sx = [s[0] for s in S]
        ex = [s[2] for s in S]
        mx, mex = statistics.mean(sx), statistics.mean(ex)
        cov = sum((a - mx) * (b - mex) for a, b in zip(sx, ex)) / len(S)
        corr = cov / (statistics.pstdev(sx) * statistics.pstdev(ex))
        self.assertLess(abs(corr), 0.2)


# --------------------------------------------------------------------------------------
# 比旧窄中心偏置更散（解决「起终点过度固定」）
# --------------------------------------------------------------------------------------
class WiderThanLegacyTest(TestCase):
    def test_tiny_roi_spread_increases_vs_center_biased(self):
        rf, rb = A_LEVEL_UP
        rule = RuleSwipe(roi_front=rf, roi_back=rb, mode='default', name='x')
        legacy = [rule.coord() for _ in range(8000)]
        v2 = [sample_swipe_endpoints(rf, rb) for _ in range(8000)]
        legacy_sd = statistics.pstdev([c[0] for c in legacy])
        v2_sd = statistics.pstdev([s[0] for s in v2])
        self.assertGreater(v2_sd, legacy_sd * 1.5)   # 明显更散

    def test_spread_still_bounded_not_uniform(self):
        # 更散不等于整框均匀：主成分仍集中在中心附近
        rf, rb = A_LEVEL_UP
        cfx, _ = _center(rf)
        S = [sample_swipe_endpoints(rf, rb) for _ in range(8000)]
        within_15 = sum(1 for s in S if abs(s[0] - cfx) <= 15) / len(S)
        self.assertGreater(within_15, 0.75)          # 大部分仍靠近中心


# --------------------------------------------------------------------------------------
# 方向 / 有效距离不变量（所有代表资产、5000 样本，逐个校验）
# --------------------------------------------------------------------------------------
class DirectionDistanceInvariantTest(TestCase):
    def _check(self, rf, rb, n=5000):
        p = SwipeEndpointParams()
        dx0, dy0 = _base_vec(rf, rb)
        base = math.hypot(dx0, dy0)
        for _ in range(n):
            sx, sy, ex, ey = sample_swipe_endpoints(rf, rb)
            dx, dy = ex - sx, ey - sy
            dist = math.hypot(dx, dy)
            self.assertGreaterEqual(dist, p.abs_min_dist_px - 1e-6)
            self.assertGreaterEqual(dist, p.min_dist_ratio * base - 1e-6)
            self.assertLessEqual(dist, p.max_dist_ratio * base + 1e-6)
            cos_theta = (dx * dx0 + dy * dy0) / (dist * base)
            self.assertGreaterEqual(cos_theta, p.min_cos - 1e-9)
            # 主轴符号
            if abs(dx0) >= abs(dy0):
                self.assertEqual((dx > 0) - (dx < 0), (dx0 > 0) - (dx0 < 0))
            else:
                self.assertEqual((dy > 0) - (dy < 0), (dy0 > 0) - (dy0 < 0))

    def test_level_up_down_direction(self):
        self._check(*A_LEVEL_UP)

    def test_background_left_direction(self):
        self._check(*A_BG_RIGHT)

    def test_short_horizontal_direction(self):
        self._check(*A_SHIKI_ONE)

    def test_mixed_wide_narrow_direction(self):
        self._check(*A_BUFF_UP)

    def test_corner_start_direction(self):
        self._check(*A_AB_CORNER)

    def test_tiny_roi_direction(self):
        self._check(*A_WQ_LIST)

    def test_exploration_chapter_swipes_keep_vertical_sense(self):
        # 章节列表：LEVEL_UP 手指向下、LEVEL_DOWN 手指向上，方向不能被采反
        up = ((1142, 328, 21, 21), (1143, 444, 21, 21))
        down = ((1143, 486, 21, 21), (1143, 367, 21, 23))
        for _ in range(3000):
            s = sample_swipe_endpoints(*up)
            self.assertGreater(s[3], s[1])       # 手指向下
            s = sample_swipe_endpoints(*down)
            self.assertLess(s[3], s[1])          # 手指向上


# --------------------------------------------------------------------------------------
# 宽 ROI：逐字保持旧 `_center_biased_int`（不回归 Summon / GeneralBattle 随机大区滑动）
# --------------------------------------------------------------------------------------
class WideRoiPassthroughTest(TestCase):
    def test_both_wide_calls_only_center_biased(self):
        with patch.object(se, '_center_biased_int', wraps=se._center_biased_int) as cb, \
                patch.object(se, 'random_normal', side_effect=AssertionError('宽 ROI 不应走高斯')):
            for _ in range(500):
                sample_swipe_endpoints(*A_BATTLE_L)
                sample_swipe_endpoints(*A_SUMMON_3)
        self.assertEqual(cb.call_count, 500 * 2 * 4)   # 每次 4 个轴都走中心偏置

    def test_both_wide_output_distribution_matches_legacy_coord(self):
        rf, rb = A_BATTLE_L
        rule = RuleSwipe(roi_front=rf, roi_back=rb, mode='default', name='x')
        legacy = [rule.coord() for _ in range(15000)]
        v2 = [sample_swipe_endpoints(rf, rb) for _ in range(15000)]
        for idx in range(4):
            lm = statistics.mean([c[idx] for c in legacy])
            vm = statistics.mean([s[idx] for s in v2])
            ls = statistics.pstdev([c[idx] for c in legacy])
            vs = statistics.pstdev([s[idx] for s in v2])
            self.assertAlmostEqual(lm, vm, delta=3.0)     # 同均值
            self.assertAlmostEqual(ls, vs, delta=3.0)     # 同散布

    def test_mixed_wide_axis_uses_center_biased_narrow_axis_uses_gaussian(self):
        # BUFF_UP：x 宽（456）→ 该轴走 _center_biased_int；y 窄（35）→ 该轴走高斯
        with patch.object(se, '_center_biased_int', wraps=se._center_biased_int) as cb, \
                patch.object(se, 'random_normal', wraps=se.random_normal) as rn:
            for _ in range(400):
                sample_swipe_endpoints(*A_BUFF_UP)
        self.assertGreater(cb.call_count, 0)      # 宽 x 轴走中心偏置
        self.assertGreater(rn.call_count, 0)      # 窄 y 轴走高斯

    def test_mixed_wide_narrow_widens_narrow_axis_not_wide_axis(self):
        # BUFF_UP：y 窄轴明显放宽；x 宽轴不被 v2 放大（联合 guard 只会收窄不会放大）
        rf, rb = A_BUFF_UP
        rule = RuleSwipe(roi_front=rf, roi_back=rb, mode='default', name='x')
        legacy = [rule.coord() for _ in range(12000)]
        v2 = [sample_swipe_endpoints(rf, rb) for _ in range(12000)]
        lx = statistics.pstdev([c[0] for c in legacy])
        vx = statistics.pstdev([s[0] for s in v2])
        ly = statistics.pstdev([c[1] for c in legacy])
        vy = statistics.pstdev([s[1] for s in v2])
        self.assertGreater(vy, ly * 1.5)              # y 窄轴明显放宽
        self.assertLessEqual(vx, lx + 2.0)           # x 宽轴不被放大


# --------------------------------------------------------------------------------------
# 有界 + 确定性回退（不 while True）
# --------------------------------------------------------------------------------------
class BoundedResampleTest(TestCase):
    def test_falls_back_to_preferred_centers_when_gaussian_pathological(self):
        # random_normal 永远吐一个荒谬值 → 单轴 rejection 用尽回退轴中心，
        # 联合 guard 也会失败用尽 → 最终回退 (preferred_start, preferred_end)
        rf, rb = A_LEVEL_UP
        cfx, cfy = _center(rf)
        cbx, cby = _center(rb)
        with patch.object(se, 'random_normal', return_value=10 ** 9):
            out = sample_swipe_endpoints(rf, rb)
        self.assertEqual(out, (round(cfx), round(cfy), round(cbx), round(cby)))

    def test_no_unbounded_loop_tokens_in_source(self):
        src = inspect.getsource(se)
        body = src.split('"""', 2)[-1]
        self.assertNotIn('while True', body)
        self.assertNotIn('while 1', body)

    def test_bounded_by_joint_max_attempts(self):
        # random_normal 计数：joint_max_attempts 次 × 每次 2 端点 × 每端点最多
        # axis_max_attempts 次 × 2 窄轴 —— 必须有限
        p = SwipeEndpointParams()
        calls = []
        real = se.random_normal

        def counting(mu, sigma):
            calls.append(1)
            return 10 ** 9    # 逼到 rejection 上限

        with patch.object(se, 'random_normal', side_effect=counting):
            sample_swipe_endpoints(*A_LEVEL_UP)
        self.assertLessEqual(len(calls),
                             p.joint_max_attempts * 2 * p.axis_max_attempts * 2)


# --------------------------------------------------------------------------------------
# RuleSwipe / BaseTask 接线
# --------------------------------------------------------------------------------------
class RuleSwipeWiringTest(TestCase):
    def test_sample_endpoints_delegates_to_module_function(self):
        rule = RuleSwipe(roi_front=(10, 20, 30, 40), roi_back=(200, 20, 30, 40),
                         mode='default', name='s')
        with patch('module.atom.swipe.sample_swipe_endpoints',
                   return_value=(1, 2, 3, 4)) as m:
            self.assertEqual(rule.sample_endpoints(), (1, 2, 3, 4))
        m.assert_called_once_with((10, 20, 30, 40), (200, 20, 30, 40))

    def test_coord_unchanged_still_strictly_in_roi(self):
        rule = RuleSwipe(roi_front=(100, 200, 20, 30), roi_back=(400, 500, 40, 50),
                         mode='default')
        for _ in range(500):
            x1, y1, x2, y2 = rule.coord()
            self.assertTrue(100 <= x1 < 120 and 200 <= y1 < 230)
            self.assertTrue(400 <= x2 < 440 and 500 <= y2 < 550)

    def test_base_task_swipe_uses_sample_endpoints(self):
        src = inspect.getsource(_base_task_swipe_source())
        self.assertIn('swipe.sample_endpoints()', src)
        self.assertNotIn('swipe.coord()', src)


def _base_task_swipe_source():
    from tasks.base_task import BaseTask
    return BaseTask.swipe


# --------------------------------------------------------------------------------------
# BehaviorTrace 记录的是真实采样端点（经 TouchSwipeModel 精确端点）
# --------------------------------------------------------------------------------------
class RealEndpointsReachTrajectoryTest(TestCase):
    def test_sampled_endpoints_are_what_touchswipemodel_gets(self):
        from tasks.base_task import BaseTask
        t = BaseTask.__new__(BaseTask)
        t.interval_timer = {}
        t.config = SimpleNamespace(
            script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        captured = {}

        def fake_traj(start, end, *, control_name='SWIPE', fallback=True):
            captured['start'] = start
            captured['end'] = end

        t.swipe_trajectory = fake_traj
        rule = RuleSwipe(roi_front=(1142, 328, 21, 21), roi_back=(1143, 444, 21, 21),
                         mode='default', name='S_SWIPE_LEVEL_UP')
        with patch.object(rule, 'sample_endpoints', return_value=(1150, 400, 1160, 460)):
            t.swipe(rule)
        self.assertEqual(captured['start'], (1150, 400))
        self.assertEqual(captured['end'], (1160, 460))

    def test_touchswipemodel_generate_pins_exact_endpoints(self):
        from module.device.touch_swipe_model import TouchSwipeModel
        traj = TouchSwipeModel().generate((1150, 405), (1161, 459))
        self.assertEqual(traj[0][0], 1150)
        self.assertEqual(traj[0][1], 405)
        self.assertEqual(traj[-1][0], 1161)
        self.assertEqual(traj[-1][1], 459)


# --------------------------------------------------------------------------------------
# 不误伤别的 swipe 路径（K1~K4 / list_find / drag / press_and_drag）
# --------------------------------------------------------------------------------------
class OtherSwipePathsUntouchedTest(TestCase):
    def test_kekkai_perform_search_swipe_does_not_use_endpoint_sampler(self):
        from tasks.KekkaiUtilize.script_task import ScriptTask as KU
        src = inspect.getsource(KU._perform_search_swipe)
        self.assertNotIn('sample_swipe_endpoints', src)
        self.assertNotIn('sample_endpoints', src)
        # K2 自己的位移采样仍在
        self.assertIn('SWIPE_DISTANCE_RANGE', src)

    def test_list_find_pagination_not_routed_through_endpoint_sampler(self):
        from tasks.base_task import BaseTask
        src = inspect.getsource(BaseTask.list_find)
        self.assertNotIn('sample_endpoints', src)
        self.assertIn('self.device.swipe(', src)   # 仍是旧翻页端点滑动（D013）

    def test_drag_and_press_and_drag_untouched(self):
        from module.device import control
        self.assertNotIn('swipe_endpoint', inspect.getsource(control.Control.drag))
        import tasks.Chess.runtime.press_and_drag as pad
        self.assertNotIn('sample_swipe_endpoints', inspect.getsource(pad))

    def test_endpoint_sampler_module_has_no_touchswipemodel_or_device_import(self):
        # 只看 import 段（docstring 里为解释分层会提到 TouchSwipeModel，不算依赖）
        src = inspect.getsource(se)
        import_lines = [ln for ln in src.splitlines()
                        if ln.startswith('import ') or ln.startswith('from ')]
        joined = '\n'.join(import_lines)
        self.assertNotIn('touch_swipe_model', joined)
        self.assertNotIn('module.device', joined)
        self.assertNotIn('TouchSwipeModel', joined)


# --------------------------------------------------------------------------------------
# 全仓 swipe 资产静态普查：任意一对 ROI 都不让采样器崩（含 1px / 2px / 贴角 ROI）
# --------------------------------------------------------------------------------------
class AllRepoSwipeAssetsSmokeTest(TestCase):
    _RE = None

    def _iter_asset_rois(self):
        import pathlib
        import re
        if AllRepoSwipeAssetsSmokeTest._RE is None:
            AllRepoSwipeAssetsSmokeTest._RE = re.compile(
                r'RuleSwipe\(\s*roi_front=\((\d+),(\d+),(\d+),(\d+)\)\s*,\s*'
                r'roi_back=\((\d+),(\d+),(\d+),(\d+)\)')
        root = pathlib.Path(__file__).resolve().parent.parent / 'tasks'
        for path in root.rglob('assets.py'):
            for m in AllRepoSwipeAssetsSmokeTest._RE.finditer(
                    path.read_text(encoding='utf-8')):
                nums = [int(g) for g in m.groups()]
                yield tuple(nums[:4]), tuple(nums[4:])

    def test_every_ruleswipe_asset_samples_without_error(self):
        seen = 0
        for rf, rb in self._iter_asset_rois():
            seen += 1
            for _ in range(80):
                out = sample_swipe_endpoints(rf, rb)
                self.assertEqual(len(out), 4, (rf, rb))
                self.assertTrue(all(isinstance(c, int) for c in out), (rf, rb, out))
        self.assertGreater(seen, 25)   # 确实扫到了一批资产

    def test_every_ruleswipe_asset_preserves_dominant_axis_direction(self):
        for rf, rb in self._iter_asset_rois():
            dx0, dy0 = _base_vec(rf, rb)
            if math.hypot(dx0, dy0) < 10:
                continue
            for _ in range(200):
                sx, sy, ex, ey = sample_swipe_endpoints(rf, rb)
                dx, dy = ex - sx, ey - sy
                if abs(dx0) >= abs(dy0) and dx0 != 0:
                    self.assertEqual((dx > 0) - (dx < 0), (dx0 > 0) - (dx0 < 0),
                                     (rf, rb))
                elif dy0 != 0:
                    self.assertEqual((dy > 0) - (dy < 0), (dy0 > 0) - (dy0 < 0),
                                     (rf, rb))
