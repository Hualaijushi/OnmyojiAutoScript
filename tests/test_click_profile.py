"""ClickProfile / Safe ROI / HABIT / STRICT / UNIFORM 的单元测试（T7-1 第 2 阶段）。

核心命题：**新策略能力已实现，但默认生产点击仍完全是 LEGACY_UNIFORM**——
`Rule*.coord()` 不传 strategy，`ClickSampler.sample(roi)` 默认 `LEGACY_UNIFORM`，
与 `random_point_in_roi` 逐字等价（等价性由 tests/test_click_sampler.py 锁）。

确定性优先：patch `_choose_component` 与 `random_normal` 注入固定分支 / 样本，
大样本统计只作辅助 sanity、阈值宽松。
"""

import unittest
from statistics import mean
from unittest.mock import patch

from module import click_sampler
from module.click_sampler import ClickSampler, LEGACY_UNIFORM
from module.click_profile import (
    DEFAULT_PROFILES,
    POINT_MIN_CORE_SIGMA_U,
    POINT_MIN_CORE_SIGMA_V,
    POINT_MIN_MEDIUM_SIGMA_U,
    POINT_MIN_MEDIUM_SIGMA_V,
    POINT_SIZE_FULL_PX,
    POINT_SIZE_MIN_PX,
    STRICT_MAX_CORE_SIGMA,
    ClickProfile,
    ClickProfileManager,
    adapt_point_profile,
    adapt_preferred_by_size,
    point_size_factor,
    resolve_profile,
)


# --------------------------------------------------------------------------------------
# ClickProfile 数据结构
# --------------------------------------------------------------------------------------

class ClickProfileTest(unittest.TestCase):
    def test_frozen_and_defaults(self):
        p = ClickProfile(name="x")
        self.assertEqual((p.preferred_u, p.preferred_v), (0.5, 0.5))
        with self.assertRaises(Exception):
            p.preferred_u = 0.9  # frozen

    def test_normalized_weights_sum_to_one(self):
        p = ClickProfile(name="x", core_weight=3, medium_weight=1, tail_weight=1)
        c, m, t = p.normalized_weights()
        self.assertAlmostEqual(c + m + t, 1.0)
        self.assertAlmostEqual(c, 0.6)

    def test_without_tail(self):
        p = DEFAULT_PROFILES["normal_button"].without_tail()
        self.assertEqual(p.tail_weight, 0.0)
        self.assertEqual(p.name, "normal_button")

    def test_invalid_preferred_fails_fast(self):
        for kw in ({"preferred_u": 1.5}, {"preferred_v": -0.1}):
            with self.assertRaises(ValueError):
                ClickProfile(name="bad", **kw)

    def test_invalid_sigma_and_weight_fail_fast(self):
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", core_sigma_u=-0.01)
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", core_weight=-1)
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", core_weight=0, medium_weight=0, tail_weight=0)

    def test_margin_must_keep_safe_roi_alive(self):
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", safe_margin_u=0.5)
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", safe_margin_v=0.6)

    def test_max_attempts_at_least_one(self):
        with self.assertRaises(ValueError):
            ClickProfile(name="bad", max_attempts=0)

    def test_builtin_profiles_all_valid_and_category_differences_kept(self):
        # 每个内置 profile 构造即校验；类别之间纵向热点确有差异（不是一个 global center）
        vs = {k: DEFAULT_PROFILES[k].preferred_v for k in
              ("tiny", "small", "normal_button", "wide_card", "large_area")}
        self.assertLess(vs["tiny"], vs["normal_button"])
        self.assertLess(vs["wide_card"], vs["normal_button"])
        self.assertNotEqual(len(set(round(v, 2) for v in vs.values())), 1)
        # T7-3.1：所有非 default 的内置 profile 都是个人 / 保守 provisional——
        # wide_card / normal_button / large_area 也补上（之前漏标）。
        for name in ("tiny", "small", "strict", "default",
                     "wide_card", "normal_button", "large_area"):
            self.assertTrue(DEFAULT_PROFILES[name].provisional, name)

    def test_spread_ordering_tiny_narrowest_large_area_widest(self):
        s = {k: DEFAULT_PROFILES[k].core_sigma_u for k in
             ("tiny", "small", "normal_button", "wide_card", "large_area")}
        self.assertLess(s["tiny"], s["small"])
        self.assertLess(s["small"], s["normal_button"])
        self.assertLessEqual(s["normal_button"], s["wide_card"])
        self.assertLess(s["wide_card"], s["large_area"])

    def test_wide_card_normal_button_large_area_are_provisional(self):
        # T7-3.1 收口：这三类是个人实验 / 未用真实 runtime ROI-relative 数据验证的值，
        # 明确标 provisional（provisional 只是文档标记，不改任何采样行为）。
        self.assertTrue(DEFAULT_PROFILES["wide_card"].provisional)
        self.assertTrue(DEFAULT_PROFILES["normal_button"].provisional)
        self.assertTrue(DEFAULT_PROFILES["large_area"].provisional)

    def test_every_default_profile_is_provisional(self):
        # v1 默认集整体是「第一版个人先验 / 保守默认」，没有一个是通用真值。
        for name, prof in DEFAULT_PROFILES.items():
            self.assertTrue(prof.provisional, name)


class ResolveProfileTest(unittest.TestCase):
    def test_none_is_default(self):
        self.assertEqual(resolve_profile(None).name, "default")

    def test_str_name(self):
        self.assertEqual(resolve_profile("wide_card").name, "wide_card")

    def test_unknown_name_falls_back_to_default(self):
        self.assertEqual(resolve_profile("no_such_profile").name, "default")

    def test_instance_passthrough(self):
        p = ClickProfile(name="custom", preferred_u=0.3)
        self.assertIs(resolve_profile(p), p)

    def test_bad_type_raises(self):
        with self.assertRaises(TypeError):
            resolve_profile(123)

    def test_manager_get_and_names(self):
        mgr = ClickProfileManager()
        self.assertEqual(mgr.get("tiny").name, "tiny")
        self.assertEqual(mgr.get("whatever").name, "default")
        self.assertIn("large_area", mgr.names())


# --------------------------------------------------------------------------------------
# Safe ROI
# --------------------------------------------------------------------------------------

class SafeRoiTest(unittest.TestCase):
    def test_margin_zero_returns_original(self):
        p = ClickProfile(name="m0", safe_margin_u=0.0, safe_margin_v=0.0)
        self.assertEqual(click_sampler._safe_roi((10, 20, 100, 80), p), (10, 20, 100, 80))

    def test_normal_shrink(self):
        p = ClickProfile(name="m", safe_margin_u=0.10, safe_margin_v=0.25)
        # dx=round(0.10*100)=10, dy=round(0.25*80)=20 -> (20,40, 80,40)
        self.assertEqual(click_sampler._safe_roi((10, 20, 100, 80), p), (20, 40, 80, 40))

    def test_tiny_roi_still_ok_when_margin_small_enough(self):
        p = ClickProfile(name="t", safe_margin_u=0.1, safe_margin_v=0.1)
        sx, sy, sw, sh = click_sampler._safe_roi((0, 0, 10, 10), p)
        self.assertGreaterEqual(sw, 1)
        self.assertGreaterEqual(sh, 1)

    def test_margin_too_large_degenerate_raises(self):
        p = ClickProfile(name="big", safe_margin_u=0.49, safe_margin_v=0.1)
        with self.assertRaises(ValueError):
            click_sampler._safe_roi((0, 0, 4, 100), p)  # 4*0.49*2 -> 收成 0 宽

    def test_does_not_mutate_input(self):
        p = DEFAULT_PROFILES["normal_button"]
        roi = [10, 20, 100, 80]
        click_sampler._safe_roi(roi, p)
        self.assertEqual(roi, [10, 20, 100, 80])

    def test_non_int_roi_raises_type_error(self):
        p = DEFAULT_PROFILES["default"]
        with self.assertRaises(TypeError):
            click_sampler._safe_roi((0, 0, 10.5, 10), p)


# --------------------------------------------------------------------------------------
# HABIT
# --------------------------------------------------------------------------------------

class HabitStrategyTest(unittest.TestCase):
    ROI = (0, 0, 100, 100)

    def _prof(self, **kw):
        base = dict(name="p", preferred_u=0.6, preferred_v=0.4,
                    core_sigma_u=0.05, core_sigma_v=0.05,
                    medium_sigma_u=0.20, medium_sigma_v=0.20,
                    core_weight=0.7, medium_weight=0.2, tail_weight=0.1,
                    safe_margin_u=0.1, safe_margin_v=0.1, max_attempts=8)
        base.update(kw)
        return ClickProfile(**base)

    def test_preferred_center_passed_into_normal(self):
        p = self._prof()
        calls = []

        def fake_normal(mu, sigma):
            calls.append((mu, sigma))
            return mu  # 直接落热点

        with patch.object(click_sampler, "_choose_component", return_value="core"), \
             patch.object(click_sampler, "random_normal", side_effect=fake_normal):
            x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
        self.assertEqual(calls[0], (0.6, 0.05))   # core_sigma_u
        self.assertEqual(calls[1], (0.4, 0.05))   # core_sigma_v
        self.assertEqual((x, y), (60, 40))        # 0.6*100, 0.4*100

    def test_core_uses_core_sigma_medium_uses_medium_sigma(self):
        p = self._prof()
        for comp, exp_su, exp_sv in [("core", 0.05, 0.05), ("medium", 0.20, 0.20)]:
            seen = []
            with patch.object(click_sampler, "_choose_component", return_value=comp), \
                 patch.object(click_sampler, "random_normal",
                              side_effect=lambda mu, s, seen=seen: (seen.append(s), mu)[1]):
                ClickSampler.sample(self.ROI, strategy="habit", profile=p)
            self.assertEqual(seen, [exp_su, exp_sv])

    def test_only_one_component_per_click(self):
        p = self._prof()
        with patch.object(click_sampler, "_choose_component", return_value="core") as chooser, \
             patch.object(click_sampler, "random_normal", side_effect=lambda mu, s: mu):
            ClickSampler.sample(self.ROI, strategy="habit", profile=p)
        chooser.assert_called_once()

    def test_tail_samples_uniform_in_safe_roi(self):
        p = self._prof()
        with patch.object(click_sampler, "_choose_component", return_value="tail"):
            for _ in range(200):
                x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
                # safe = (10,10,80,80)
                self.assertTrue(10 <= x < 90)
                self.assertTrue(10 <= y < 90)

    def test_component_chosen_by_weight(self):
        # _choose_component 按累计权重划分 [0,1)
        weights = (0.7, 0.2, 0.1)
        with patch.object(click_sampler._rng, "random", return_value=0.5):
            self.assertEqual(click_sampler._choose_component(weights), "core")
        with patch.object(click_sampler._rng, "random", return_value=0.8):
            self.assertEqual(click_sampler._choose_component(weights), "medium")
        with patch.object(click_sampler._rng, "random", return_value=0.95):
            self.assertEqual(click_sampler._choose_component(weights), "tail")

    def test_out_of_bounds_candidate_is_rejected_then_resampled(self):
        p = self._prof(max_attempts=5)
        # 前两次 normal 给出远超界的 u/v，第三次回到热点
        seq = iter([9.0, 9.0,   # attempt1 越界
                    -9.0, -9.0,  # attempt2 越界
                    0.6, 0.4])   # attempt3 命中
        with patch.object(click_sampler, "_choose_component", return_value="core"), \
             patch.object(click_sampler, "random_normal", side_effect=lambda mu, s: next(seq)):
            x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
        self.assertEqual((x, y), (60, 40))

    def test_rejection_capped_then_fallback_inside_safe_roi_not_edge_clamp(self):
        p = self._prof(max_attempts=3, preferred_u=0.6, preferred_v=0.4)
        # 每次 normal 都越界 -> 用尽 attempts -> fallback
        with patch.object(click_sampler, "_choose_component", return_value="core"), \
             patch.object(click_sampler, "random_normal", side_effect=lambda mu, s: 5.0):
            x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
        # fallback = 热点投影到 safe (10,10,80,80)，preferred 0.6/0.4 在内边距范围内 -> (60,40)
        self.assertEqual((x, y), (60, 40))
        self.assertTrue(10 <= x < 90 and 10 <= y < 90)

    def test_fallback_projects_extreme_preferred_into_margin(self):
        # preferred 贴边（0.98）-> fallback 应夹到 (1 - margin) 而不是 ROI 边
        p = self._prof(max_attempts=2, preferred_u=0.98, preferred_v=0.02,
                       safe_margin_u=0.1, safe_margin_v=0.1)
        with patch.object(click_sampler, "_choose_component", return_value="core"), \
             patch.object(click_sampler, "random_normal", side_effect=lambda mu, s: 5.0):
            x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
        # u 夹到 0.9 -> x=90 -> 再夹进 safe [10, 89] -> 89 ; v 夹到 0.1 -> y=10
        self.assertEqual((x, y), (89, 10))

    def test_habit_result_always_inside_safe_roi_statistical(self):
        p = DEFAULT_PROFILES["wide_card"]
        roi = (300, 200, 160, 90)
        sx, sy, sw, sh = click_sampler._safe_roi(roi, p)
        for _ in range(400):
            x, y = ClickSampler.sample(roi, strategy="habit", profile=p)
            self.assertTrue(sx <= x < sx + sw)
            self.assertTrue(sy <= y < sy + sh)

    def test_habit_mean_near_preferred_sanity(self):
        # 辅助 sanity，阈值宽松：关掉 tail、只用 core，均值应大致靠近热点
        p = self._prof(core_weight=1, medium_weight=0, tail_weight=0,
                       core_sigma_u=0.05, core_sigma_v=0.05, max_attempts=20)
        xs, ys = [], []
        for _ in range(600):
            x, y = ClickSampler.sample(self.ROI, strategy="habit", profile=p)
            xs.append(x)
            ys.append(y)
        self.assertAlmostEqual(mean(xs) / 100, 0.6, delta=0.05)
        self.assertAlmostEqual(mean(ys) / 100, 0.4, delta=0.05)

    def test_habit_default_profile_when_none(self):
        with patch.object(click_sampler, "resolve_profile", wraps=resolve_profile) as m:
            ClickSampler.sample(self.ROI, strategy="habit", profile=None)
        m.assert_called_once_with(None)


# --------------------------------------------------------------------------------------
# STRICT
# --------------------------------------------------------------------------------------

class StrictStrategyTest(unittest.TestCase):
    ROI = (0, 0, 100, 100)

    def test_default_strict_profile_is_narrow_and_centered(self):
        # 硬保证：始终落在 strict 的 Safe ROI 内（居中收边 12%）。
        p = DEFAULT_PROFILES["strict"]
        sx, sy, sw, sh = click_sampler._safe_roi(self.ROI, p)
        near = 0
        n = 400
        for _ in range(n):
            x, y = ClickSampler.sample(self.ROI, strategy="strict")
            self.assertTrue(sx <= x < sx + sw and sy <= y < sy + sh)
            if abs(x - 50) <= 20 and abs(y - 50) <= 20:
                near += 1
        # 分布很窄：绝大多数落在中心 ±20px（阈值宽松，避免 flaky）
        self.assertGreater(near / n, 0.9)

    def test_strict_drops_tail(self):
        # 即使传入带 tail 的窄 profile，STRICT 也强制去掉 tail
        p = ClickProfile(name="narrow_with_tail", core_sigma_u=0.05, core_sigma_v=0.05,
                         medium_sigma_u=0.08, medium_sigma_v=0.08,
                         core_weight=0.5, medium_weight=0.3, tail_weight=0.2)
        with patch.object(click_sampler, "_choose_component") as chooser:
            chooser.side_effect = lambda w: (self.assertAlmostEqual(w[2], 0.0), "core")[1]
            ClickSampler.sample(self.ROI, strategy="strict", profile=p)

    def test_strict_rejects_wide_profile(self):
        with self.assertRaises(ValueError):
            ClickSampler.sample(self.ROI, strategy="strict", profile="large_area")
        with self.assertRaises(ValueError):
            ClickSampler.sample(self.ROI, strategy="strict", profile="wide_card")

    def test_strict_accepts_tiny_and_small(self):
        for name in ("tiny", "small"):
            x, y = ClickSampler.sample(self.ROI, strategy="strict", profile=name)
            self.assertTrue(0 <= x < 100 and 0 <= y < 100)

    def test_strict_spread_much_narrower_than_habit_wide(self):
        n = 500
        strict_xs = [ClickSampler.sample(self.ROI, strategy="strict")[0] for _ in range(n)]
        habit_xs = [ClickSampler.sample(self.ROI, strategy="habit",
                                        profile="large_area")[0] for _ in range(n)]
        self.assertLess(_pstdev(strict_xs), _pstdev(habit_xs))

    def test_strict_always_in_safe_roi(self):
        p = DEFAULT_PROFILES["tiny"]
        roi = (500, 400, 40, 40)
        sx, sy, sw, sh = click_sampler._safe_roi(roi, p)
        for _ in range(300):
            x, y = ClickSampler.sample(roi, strategy="strict", profile=p)
            self.assertTrue(sx <= x < sx + sw and sy <= y < sy + sh)


# --------------------------------------------------------------------------------------
# UNIFORM vs LEGACY_UNIFORM
# --------------------------------------------------------------------------------------

class UniformStrategyTest(unittest.TestCase):
    def test_uniform_stays_in_safe_roi(self):
        # default profile margin 0.06 -> uniform 在收边后的 ROI 内
        roi = (0, 0, 100, 100)
        p = DEFAULT_PROFILES["default"]
        sx, sy, sw, sh = click_sampler._safe_roi(roi, p)
        for _ in range(300):
            x, y = ClickSampler.sample(roi, strategy="uniform")
            self.assertTrue(sx <= x < sx + sw)
            self.assertTrue(sy <= y < sy + sh)

    def test_uniform_with_zero_margin_profile_equals_full_roi(self):
        p = ClickProfile(name="m0", safe_margin_u=0.0, safe_margin_v=0.0)
        roi = (10, 10, 50, 50)
        for _ in range(200):
            x, y = ClickSampler.sample(roi, strategy="uniform", profile=p)
            self.assertTrue(10 <= x < 60 and 10 <= y < 60)

    def test_uniform_and_legacy_uniform_are_distinct_names_same_family(self):
        # 两者第一版数学同族（均匀），但语义不同：LEGACY = 兼容旧行为的默认 fallback；
        # UNIFORM = 显式声明「该目标就是全区域均匀」，且会经过 Safe ROI。
        self.assertNotEqual(click_sampler.LEGACY_UNIFORM, click_sampler.STRATEGY_UNIFORM)
        # LEGACY 不收边：整 ROI；UNIFORM 收 default margin
        roi = (0, 0, 100, 100)
        legacy_hits_edge = any(
            ClickSampler.sample(roi, strategy=LEGACY_UNIFORM)[0] < 6 for _ in range(500)
        )
        self.assertTrue(legacy_hits_edge)  # 能取到 <6（default margin 收掉的区域）


# --------------------------------------------------------------------------------------
# LEGACY 路径不受新代码影响
# --------------------------------------------------------------------------------------

class LegacyUntouchedTest(unittest.TestCase):
    def test_legacy_uniform_still_delegates_directly_no_profile(self):
        roi = (5, 5, 20, 20)
        with patch("module.click_sampler.random_point_in_roi", return_value=(9, 9)) as m, \
             patch("module.click_sampler.resolve_profile") as rp:
            out = ClickSampler.sample(roi)  # 默认策略
        m.assert_called_once_with(roi)
        rp.assert_not_called()              # LEGACY 路径不碰 profile
        self.assertEqual(out, (9, 9))

    def test_legacy_uniform_semantic_equivalence_same_rng(self):
        from module.base.utils.random import random_point_in_roi
        roi = (11, 22, 33, 44)
        seq = [17, 5, 30, 40, 0, 0]
        with patch.object(click_sampler._rng, "randrange", side_effect=list(seq)):
            via = [ClickSampler.sample(roi) for _ in range(3)]
        with patch.object(random_point_in_roi.__globals__["_rng"], "randrange", side_effect=list(seq)):
            direct = [random_point_in_roi(roi) for _ in range(3)]
        self.assertEqual(via, direct)


def _pstdev(values):
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5


# --------------------------------------------------------------------------------------
# T7-2：Point Target 连续尺寸适配（adapt_point_profile / point_size_factor）
#
# 纯计算：size_factor smoothstep + preferred 连续插值；零生产消费者。
# --------------------------------------------------------------------------------------

class PointSizeFactorTest(unittest.TestCase):
    def test_anchors(self):
        self.assertEqual((POINT_SIZE_MIN_PX, POINT_SIZE_FULL_PX), (24, 96))

    def test_short_side_at_or_below_min_is_zero(self):
        for ss in (0.5, 8, 20, 23.9, 24):
            self.assertEqual(point_size_factor(ss), 0.0, ss)

    def test_short_side_at_or_above_full_is_one(self):
        for ss in (96, 100, 120, 300, 5000):
            self.assertEqual(point_size_factor(ss), 1.0, ss)

    def test_midpoint_60px_is_half(self):
        # t = (60 - 24) / (96 - 24) = 0.5 ; smoothstep(0.5) = 3*0.25 - 2*0.125 = 0.5
        self.assertAlmostEqual(point_size_factor(60), 0.5, places=12)

    def test_smoothstep_formula_exact(self):
        span = POINT_SIZE_FULL_PX - POINT_SIZE_MIN_PX
        for ss in (25, 32, 40, 48, 55, 72, 80, 95):
            t = (ss - POINT_SIZE_MIN_PX) / span
            self.assertAlmostEqual(point_size_factor(ss), 3 * t * t - 2 * t ** 3, places=12)

    def test_range_is_unit_interval_and_monotonic(self):
        prev = -1.0
        for ss in range(0, 200):
            f = point_size_factor(ss)
            self.assertGreaterEqual(f, 0.0)
            self.assertLessEqual(f, 1.0)
            self.assertGreaterEqual(f, prev)  # 单调不减
            prev = f

    def test_no_linear_kink_flat_derivative_at_ends(self):
        # smoothstep 两端一阶导为 0：靠近锚点处增量远小于中段
        eps = 0.5
        near_min = point_size_factor(POINT_SIZE_MIN_PX + eps) - point_size_factor(POINT_SIZE_MIN_PX)
        near_full = point_size_factor(POINT_SIZE_FULL_PX) - point_size_factor(POINT_SIZE_FULL_PX - eps)
        mid = point_size_factor(60 + eps) - point_size_factor(60)
        self.assertLess(near_min, mid)
        self.assertLess(near_full, mid)


class AdaptPreferredBySizeTest(unittest.TestCase):
    BASE = (0.58, 0.59)

    def test_rule_anchor_representative_sizes_follow_exact_formula(self):
        for short_side in (1, 24, 32, 40, 48, 60, 72, 80, 96, 200):
            t = max(0.0, min(1.0, (short_side - 24) / (96 - 24)))
            factor = t * t * (3.0 - 2.0 * t)
            expected = (
                0.5 + (self.BASE[0] - 0.5) * factor,
                0.5 + (self.BASE[1] - 0.5) * factor,
            )
            actual = adapt_preferred_by_size(*self.BASE, (0, 0, 300, short_side))
            self.assertAlmostEqual(actual[0], expected[0], places=12, msg=short_side)
            self.assertAlmostEqual(actual[1], expected[1], places=12, msg=short_side)

    def test_short_side_uses_min_width_height(self):
        horizontal = adapt_preferred_by_size(*self.BASE, (0, 0, 320, 60))
        vertical = adapt_preferred_by_size(*self.BASE, (0, 0, 60, 320))
        self.assertEqual(horizontal, vertical)
        self.assertAlmostEqual(horizontal[0], 0.54, places=12)
        self.assertAlmostEqual(horizontal[1], 0.545, places=12)

    def test_endpoints_are_exact(self):
        self.assertEqual(adapt_preferred_by_size(*self.BASE, (0, 0, 24, 999)), (0.5, 0.5))
        self.assertEqual(adapt_preferred_by_size(*self.BASE, (0, 0, 96, 999)), self.BASE)

    def test_invalid_preferred_and_roi_fail_fast(self):
        for bad in (-0.1, 1.1):
            with self.assertRaises(ValueError):
                adapt_preferred_by_size(bad, 0.5, (0, 0, 40, 40))
        for bad in (None, True, "0.5"):
            with self.assertRaises(TypeError):
                adapt_preferred_by_size(bad, 0.5, (0, 0, 40, 40))
        with self.assertRaises(ValueError):
            adapt_preferred_by_size(*self.BASE, (0, 0, 0, 40))


class AdaptPointProfileTest(unittest.TestCase):
    NB = DEFAULT_PROFILES["normal_button"]   # base (0.62, 0.70)  (provisional, 未 runtime 验证)
    WC = DEFAULT_PROFILES["wide_card"]       # base (0.58, 0.59)  (T7-3.1 依 C_AREA_1 WIP ROI 收口)

    def _uv(self, prof, w, h=None):
        e = adapt_point_profile(prof, (0, 0, w, w if h is None else h))
        return (e.preferred_u, e.preferred_v)

    def test_short_side_is_min_of_wh(self):
        # 320x60 长条：short_side=60 → factor 0.5，不是按 320 完全释放
        e = adapt_point_profile(self.NB, (0, 0, 320, 60))
        self.assertAlmostEqual(e.preferred_u, 0.5 + (0.62 - 0.5) * 0.5, places=10)
        self.assertAlmostEqual(e.preferred_v, 0.5 + (0.70 - 0.5) * 0.5, places=10)
        # 60x320 同理
        e2 = adapt_point_profile(self.NB, (0, 0, 60, 320))
        self.assertEqual((e2.preferred_u, e2.preferred_v), (e.preferred_u, e.preferred_v))

    def test_normal_button_representative_sizes(self):
        self.assertEqual(self._uv(self.NB, 8), (0.5, 0.5))
        self.assertEqual(self._uv(self.NB, 24), (0.5, 0.5))
        u, v = self._uv(self.NB, 60)
        self.assertAlmostEqual(u, 0.56, places=6)
        self.assertAlmostEqual(v, 0.60, places=6)
        u, v = self._uv(self.NB, 96)
        self.assertAlmostEqual(u, 0.62, places=6)
        self.assertAlmostEqual(v, 0.70, places=6)
        self.assertEqual(self._uv(self.NB, 160), (0.62, 0.70))   # clamp

    def test_wide_card_representative_sizes(self):
        # T7-3.1：wide_card base 从 (0.68,0.53) 修正为 (0.58,0.59)（对当前 C_AREA_1 WIP ROI
        # 的 inside-only ROI-relative；来源见 module/click_profile.py 注释）。du=0.08 dv=0.09。
        self.assertEqual((self.WC.preferred_u, self.WC.preferred_v), (0.58, 0.59))
        self.assertEqual(self._uv(self.WC, 24), (0.5, 0.5))
        u, v = self._uv(self.WC, 60)                # factor 0.5
        self.assertAlmostEqual(u, 0.54, places=6)
        self.assertAlmostEqual(v, 0.545, places=6)
        u, v = self._uv(self.WC, 96)               # factor 1
        self.assertAlmostEqual(u, 0.58, places=6)
        self.assertAlmostEqual(v, 0.59, places=6)
        self.assertEqual(self._uv(self.WC, 200), (0.58, 0.59))   # clamp

    def test_wide_card_c_area_1_wip_roi_lands_at_base_hotspot(self):
        # C_AREA_1 WIP ROI short_side = 116 >= 96 → factor 1 → effective == base
        e = adapt_point_profile(self.WC, (514, 141, 223, 116))
        self.assertEqual((e.preferred_u, e.preferred_v), (0.58, 0.59))

    def test_large_roi_never_exceeds_base_hotspot(self):
        for ss in (96, 128, 400, 2000):
            u, v = self._uv(self.NB, ss)
            self.assertLessEqual(u, self.NB.preferred_u + 1e-12)
            self.assertLessEqual(v, self.NB.preferred_v + 1e-12)
            self.assertAlmostEqual(u, self.NB.preferred_u, places=9)
            self.assertAlmostEqual(v, self.NB.preferred_v, places=9)

    def test_small_roi_does_not_drift_past_center_away_from_base(self):
        # base_u/v > 0.5 → effective 落在 [0.5, base]，不会 < 0.5
        for ss in (1, 8, 16, 24, 32, 48, 72, 95):
            u, v = self._uv(self.NB, ss)
            self.assertGreaterEqual(u, 0.5 - 1e-12)
            self.assertLessEqual(u, self.NB.preferred_u + 1e-12)
            self.assertGreaterEqual(v, 0.5 - 1e-12)
            self.assertLessEqual(v, self.NB.preferred_v + 1e-12)

    def test_monotone_toward_base_as_short_side_grows(self):
        prev_u = prev_v = -1.0
        for ss in range(1, 160):
            u, v = self._uv(self.NB, ss)
            self.assertGreaterEqual(u, prev_u - 1e-12)   # base_u > 0.5 → 单调不减
            self.assertGreaterEqual(v, prev_v - 1e-12)
            prev_u, prev_v = u, v

    def test_left_biased_base_releases_left(self):
        lp = ClickProfile(name="left", preferred_u=0.30, preferred_v=0.50)
        self.assertEqual(self._uv(lp, 24), (0.5, 0.5))
        u, v = self._uv(lp, 60)
        self.assertAlmostEqual(u, 0.5 + (0.30 - 0.5) * 0.5, places=10)  # = 0.40，向左
        self.assertEqual(v, 0.5)
        u, v = self._uv(lp, 96)
        self.assertAlmostEqual(u, 0.30, places=9)

    def test_base_profile_not_mutated(self):
        before = (self.NB.preferred_u, self.NB.preferred_v)
        adapt_point_profile(self.NB, (0, 0, 40, 40))
        self.assertEqual((self.NB.preferred_u, self.NB.preferred_v), before)
        self.assertEqual(before, (0.62, 0.70))

    def test_returns_new_frozen_profile(self):
        e = adapt_point_profile(self.NB, (0, 0, 50, 50))
        self.assertIsInstance(e, ClickProfile)
        self.assertIsNot(e, self.NB)
        with self.assertRaises(Exception):
            e.preferred_u = 0.9

    def test_safe_margin_and_metadata_pass_through_unchanged(self):
        # T7-4：sigma / weights / tail 会随尺寸适配（另见 PointSpreadAdaptationTest）；
        # 但 Safe ROI 硬边界 + 纯 metadata 一律原样透传，任意尺寸都不变。
        for ss in (8, 24, 40, 60, 96, 200):
            e = adapt_point_profile(self.NB, (0, 0, ss, ss))
            for attr in ("safe_margin_u", "safe_margin_v", "max_attempts",
                         "provisional", "name"):
                self.assertEqual(getattr(e, attr), getattr(self.NB, attr), (attr, ss))
        for ss in (8, 24, 40, 60, 96, 200):
            e = adapt_point_profile(self.WC, (0, 0, ss, ss))
            for attr in ("safe_margin_u", "safe_margin_v", "max_attempts",
                         "provisional", "name"):
                self.assertEqual(getattr(e, attr), getattr(self.WC, attr), (attr, ss))

    def test_medium_weight_never_changes(self):
        # T7-4 设计：只削 tail、削掉的回补 core；medium_weight 不参与尺寸曲线。
        for base in (self.NB, self.WC, DEFAULT_PROFILES["default"], DEFAULT_PROFILES["large_area"]):
            for ss in (1, 8, 24, 30, 48, 60, 80, 96, 150):
                e = adapt_point_profile(base, (0, 0, ss, ss))
                self.assertEqual(e.medium_weight, base.medium_weight, (base.name, ss))

    def test_malformed_roi_raises_project_style(self):
        for bad in ((0, 0, 0, 40), (0, 0, 40, 0), (0, 0, -5, 40), (0, 0, 40, -1)):
            with self.assertRaises(ValueError):
                adapt_point_profile(self.NB, bad)
        for bad in ((0, 0, 40), (1, 2), "roi"):
            with self.assertRaises(ValueError):
                adapt_point_profile(self.NB, bad)
        for bad in ((0, 0, "40", 40), (0, 0, 40, None), (0, 0, True, 40)):
            with self.assertRaises(TypeError):
                adapt_point_profile(self.NB, bad)

    def test_no_rng_no_device(self):
        with patch("module.click_sampler._rng") as rng, \
             patch("module.click_sampler.random_point_in_roi") as rpi:
            adapt_point_profile(self.NB, (0, 0, 55, 55))
            point_size_factor(55)
        rng.assert_not_called()
        rpi.assert_not_called()

    def test_clicksampler_default_behavior_untouched(self):
        roi = (5, 5, 20, 20)
        with patch("module.click_sampler.random_point_in_roi", return_value=(7, 7)) as m, \
             patch("module.click_sampler.resolve_profile") as rp:
            out = ClickSampler.sample(roi)
        m.assert_called_once_with(roi)
        rp.assert_not_called()
        self.assertEqual(out, (7, 7))


class TinySmallNotUsedByAdaptationTest(unittest.TestCase):
    def test_adapt_point_profile_source_has_no_discrete_size_branch(self):
        import inspect
        src = inspect.getsource(adapt_point_profile)
        for token in ("tiny", "small", "DEFAULT_PROFILES", "if short", "elif"):
            self.assertNotIn(token, src, token)

    def test_tiny_small_profiles_still_registered(self):
        # 本轮不删除，仍可用于测试 / 历史兼容 / 显式 profile
        self.assertIn("tiny", DEFAULT_PROFILES)
        self.assertIn("small", DEFAULT_PROFILES)


# --------------------------------------------------------------------------------------
# T7-4：Point Target spread 连续尺寸适配（core/medium sigma + tail 随同一 size_factor 收敛）
# --------------------------------------------------------------------------------------

def fieldnames(profile):
    from dataclasses import fields
    return [f.name for f in fields(profile)]


class PointSpreadAnchorTest(unittest.TestCase):
    def test_point_min_spread_anchor_matches_tiny_profile(self):
        # T7-4 锚点 = `tiny` 的 σ（审计结论，见 module/click_profile.py 常量注释）。
        t = DEFAULT_PROFILES["tiny"]
        self.assertEqual(POINT_MIN_CORE_SIGMA_U, t.core_sigma_u)
        self.assertEqual(POINT_MIN_CORE_SIGMA_V, t.core_sigma_v)
        self.assertEqual(POINT_MIN_MEDIUM_SIGMA_U, t.medium_sigma_u)
        self.assertEqual(POINT_MIN_MEDIUM_SIGMA_V, t.medium_sigma_v)
        self.assertEqual(t.tail_weight, 0.0)  # 锚点档 tail 本就为 0，与 factor=0→tail=0 一致

    def test_anchor_is_conservative_but_not_degenerate(self):
        # 比 normal_button / wide_card base 都窄，但不趋近 0（最终安全仍靠 Safe ROI）。
        for name in ("normal_button", "wide_card", "large_area", "default"):
            base = DEFAULT_PROFILES[name]
            self.assertLess(POINT_MIN_CORE_SIGMA_U, base.core_sigma_u, name)
            self.assertLess(POINT_MIN_MEDIUM_SIGMA_U, base.medium_sigma_u, name)
        self.assertGreater(POINT_MIN_CORE_SIGMA_U, 0.0)
        self.assertGreater(POINT_MIN_MEDIUM_SIGMA_U, 0.0)


class PointSpreadAdaptationTest(unittest.TestCase):
    NB = DEFAULT_PROFILES["normal_button"]   # base coreσ (0.13,0.13) medσ (0.22,0.22) w (0.78,0.18,0.04)
    WC = DEFAULT_PROFILES["wide_card"]       # base coreσ (0.16,0.16) medσ (0.26,0.24) w (0.75,0.20,0.05)

    def _eff(self, base, ss):
        return adapt_point_profile(base, (0, 0, ss, ss))

    # ---- 端点：factor = 0 ----
    def test_factor_zero_sigma_is_min_anchor(self):
        for base in (self.NB, self.WC):
            e = self._eff(base, POINT_SIZE_MIN_PX)          # short_side 24 → f = 0
            self.assertEqual(e.core_sigma_u, POINT_MIN_CORE_SIGMA_U)
            self.assertEqual(e.core_sigma_v, POINT_MIN_CORE_SIGMA_V)
            self.assertEqual(e.medium_sigma_u, POINT_MIN_MEDIUM_SIGMA_U)
            self.assertEqual(e.medium_sigma_v, POINT_MIN_MEDIUM_SIGMA_V)

    def test_factor_zero_tail_is_exactly_zero(self):
        for base in (self.NB, self.WC, DEFAULT_PROFILES["large_area"]):
            e = self._eff(base, 10)
            self.assertEqual(e.tail_weight, 0.0)

    def test_factor_zero_preferred_is_center(self):
        for base in (self.NB, self.WC):
            e = self._eff(base, 8)
            self.assertEqual((e.preferred_u, e.preferred_v), (0.5, 0.5))

    def test_factor_zero_removed_tail_goes_to_core(self):
        e = self._eff(self.WC, 24)
        # core += base_tail（medium 不变），三成分和不变
        self.assertAlmostEqual(e.core_weight, self.WC.core_weight + self.WC.tail_weight, places=12)
        self.assertEqual(e.medium_weight, self.WC.medium_weight)

    # ---- 端点：factor = 1 逐字段等于 base ----
    def test_factor_one_is_byte_for_byte_base(self):
        for base in (self.NB, self.WC, DEFAULT_PROFILES["default"],
                     DEFAULT_PROFILES["large_area"], DEFAULT_PROFILES["small"]):
            e = self._eff(base, POINT_SIZE_FULL_PX)          # short_side 96 → f = 1.0
            for f in fieldnames(base):
                self.assertEqual(getattr(e, f), getattr(base, f), (base.name, f))
            self.assertIsNot(e, base)

    def test_large_roi_clamps_to_base(self):
        for ss in (96, 116, 128, 400, 5000):
            e = self._eff(self.WC, ss)
            for f in fieldnames(self.WC):
                self.assertEqual(getattr(e, f), getattr(self.WC, f), (ss, f))

    # ---- 连续 / 单调 ----
    def test_sigma_monotone_non_decreasing_toward_base(self):
        prev_c = prev_m = -1.0
        for ss in range(1, 160):
            e = self._eff(self.NB, ss)
            self.assertGreaterEqual(e.core_sigma_u, prev_c - 1e-12, ss)
            self.assertGreaterEqual(e.medium_sigma_u, prev_m - 1e-12, ss)
            prev_c, prev_m = e.core_sigma_u, e.medium_sigma_u
        # 两端
        self.assertAlmostEqual(self._eff(self.NB, 1).core_sigma_u, POINT_MIN_CORE_SIGMA_U, places=12)
        self.assertAlmostEqual(self._eff(self.NB, 300).core_sigma_u, self.NB.core_sigma_u, places=12)

    def test_tail_weight_monotone_non_decreasing_toward_base_tail(self):
        prev = -1.0
        for ss in range(1, 160):
            e = self._eff(self.WC, ss)
            self.assertGreaterEqual(e.tail_weight, prev - 1e-12, ss)
            self.assertLessEqual(e.tail_weight, self.WC.tail_weight + 1e-12, ss)
            prev = e.tail_weight

    def test_sigma_within_anchor_and_base_bracket(self):
        for ss in range(1, 160):
            e = self._eff(self.NB, ss)
            self.assertGreaterEqual(e.core_sigma_u, POINT_MIN_CORE_SIGMA_U - 1e-12, ss)
            self.assertLessEqual(e.core_sigma_u, self.NB.core_sigma_u + 1e-12, ss)

    def test_no_step_jump_around_anchors(self):
        # 24→25、40→41、95→96 相邻尺寸增量都很小（smoothstep 连续，无折点）
        for lo in (24, 25, 40, 41, 60, 80, 95):
            a = self._eff(self.NB, lo)
            b = self._eff(self.NB, lo + 1)
            self.assertLess(abs(b.core_sigma_u - a.core_sigma_u), 0.01, lo)
            self.assertLess(abs(b.tail_weight - a.tail_weight), 0.01, lo)

    # ---- 权重不变量 ----
    def test_weights_sum_preserved_and_nonnegative(self):
        for base in (self.NB, self.WC, DEFAULT_PROFILES["default"], DEFAULT_PROFILES["large_area"]):
            base_sum = base.core_weight + base.medium_weight + base.tail_weight
            for ss in (1, 8, 24, 30, 48, 60, 80, 96, 200):
                e = self._eff(base, ss)
                self.assertGreaterEqual(e.core_weight, 0.0)
                self.assertGreaterEqual(e.medium_weight, 0.0)
                self.assertGreaterEqual(e.tail_weight, 0.0)
                self.assertAlmostEqual(
                    e.core_weight + e.medium_weight + e.tail_weight, base_sum, places=12, msg=(base.name, ss))

    # ---- 代表尺寸表（含 sigma / weights / tail）----
    def test_representative_size_table_normal_button(self):
        rows = {ss: self._eff(self.NB, ss) for ss in
                (8, 24, 32, 40, 48, 60, 72, 80, 96, 116, 128)}
        self.assertEqual((rows[8].core_sigma_u, rows[8].tail_weight), (0.06, 0.0))
        self.assertAlmostEqual(rows[60].core_sigma_u, 0.095, places=6)     # lerp(0.06,0.13,0.5)
        self.assertAlmostEqual(rows[60].medium_sigma_u, 0.16, places=6)    # lerp(0.10,0.22,0.5)
        self.assertAlmostEqual(rows[60].tail_weight, 0.02, places=6)       # 0.04*0.5
        self.assertEqual((rows[96].core_sigma_u, rows[96].core_sigma_v), (0.13, 0.13))
        self.assertEqual((rows[116].core_sigma_u, rows[116].tail_weight), (0.13, 0.04))
        self.assertEqual((rows[128].core_sigma_u, rows[128].tail_weight), (0.13, 0.04))

    def test_representative_size_table_wide_card(self):
        rows = {ss: self._eff(self.WC, ss) for ss in
                (8, 24, 32, 40, 48, 60, 72, 80, 96, 116, 128)}
        self.assertEqual((rows[24].core_sigma_u, rows[24].tail_weight), (0.06, 0.0))
        self.assertAlmostEqual(rows[60].core_sigma_u, 0.11, places=6)      # lerp(0.06,0.16,0.5)
        self.assertAlmostEqual(rows[60].medium_sigma_v, 0.17, places=6)    # lerp(0.10,0.24,0.5)
        self.assertAlmostEqual(rows[60].tail_weight, 0.025, places=6)      # 0.05*0.5
        self.assertEqual((rows[96].medium_sigma_u, rows[96].medium_sigma_v), (0.26, 0.24))
        self.assertEqual(rows[128].tail_weight, 0.05)

    # ---- 极小按钮示例（40×30 → short_side 30，如 C_DOKAN_REFRESH 形状；不接生产）----
    def test_tiny_button_shape_much_more_conservative(self):
        e = adapt_point_profile(self.NB, (0, 0, 40, 30))     # short_side 30
        self.assertLess(e.core_sigma_u, self.NB.core_sigma_u * 0.6)   # 明显收窄（<60% base）
        self.assertLess(e.tail_weight, 0.005)                         # tail 接近 0
        self.assertLess(e.preferred_u, 0.53)                          # 热点接近中心
        self.assertLess(e.preferred_v, 0.53)

    # ---- 不 mutate base、返回 frozen ----
    def test_base_not_mutated_and_result_frozen(self):
        snap = {f: getattr(self.WC, f) for f in fieldnames(self.WC)}
        e = adapt_point_profile(self.WC, (0, 0, 30, 30))
        for f in fieldnames(self.WC):
            self.assertEqual(getattr(self.WC, f), snap[f], f)
        with self.assertRaises(Exception):
            e.core_sigma_u = 0.99

    # ---- C_AREA_1 生产护栏 ----
    def test_c_area_1_effective_profile_identical_to_wide_card_base(self):
        # RyouToppa.C_AREA_1 ROI (514,141,223,116) → short_side 116 → factor 1.0。
        # T7-4 后，首个生产 Point 消费者的 EffectiveProfile 必须逐字段等于 wide_card base。
        e = adapt_point_profile(self.WC, (514, 141, 223, 116))
        for f in fieldnames(self.WC):
            self.assertEqual(getattr(e, f), getattr(self.WC, f), f)


if __name__ == "__main__":
    unittest.main()
