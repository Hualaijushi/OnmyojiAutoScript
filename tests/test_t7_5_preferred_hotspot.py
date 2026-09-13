# This Python file uses the following encoding: utf-8
"""T7-5：全局 Preferred Hotspot 点击策略 —— 契约回归。

本轮把普通生产 Point 点击的**默认**从「整 ROI `LEGACY_UNIFORM`」改成「该 target 的
preferred 热点 + 现有 core/medium/tail 偏移模型 + Safe ROI」。没有经验热点的 target 不退回
Uniform，而是 `RULE_FALLBACK` 基础锚点 `(0.58, 0.59)` + `default_point` profile，并按
ROI 短边用 24/96 smoothstep 得到当前有效热点。

锁的命题（对应任务书 §26~§32）：

- 默认路径 = `ClickSampler.sample_target`，不再是 `random_point_in_roi` 主分布；
- 未登记 target 的落点中心明显更密集，但**不是**整 ROI 均匀、**也不是**固定中心；
- Tiny（<=24px）仍随机（多个不同坐标 / 均值靠中心 / 绝对散布小于大目标 / tail=0）；
- 尺寸适配连续（23/24/25、95/96/97 附近无突跳）；
- `wide_card` empirical 热点 `(0.58, 0.59)` 不被全局化冲掉；
- 一次点击只做一次空间采样（无 double jitter）；
- RuleOcr 浮点 bbox 修复保留，且默认也走 preferred 采样。

统计断言用大样本 + 宽裕阈值（`SystemRandom` 不便播种），不写「某一次随机点必须等于某坐标」。
"""

import statistics
import unittest
from unittest.mock import patch

from module import click_sampler
from module.click_sampler import ClickSampler, STRATEGY_HABIT
from module.click_profile import (
    DEFAULT_PROFILES,
    adapt_point_profile,
    point_size_factor,
    resolve_profile,
)
from module.click_preference import (
    Provenance,
    RULE_BASE_PREFERRED,
    RULE_FALLBACK_PROFILE,
    TARGET_PREFERENCES,
    TargetPreference,
    provenance_counts,
    resolve_target_preference,
)


def _samples(roi, target_name, n):
    return [ClickSampler.sample_target(roi, target_name) for _ in range(n)]


# --------------------------------------------------------------------------------------
# §5 / §22：Target Preference Registry 结构
# --------------------------------------------------------------------------------------
class TargetPreferenceRegistryTest(unittest.TestCase):
    def test_provenance_has_the_four_documented_levels(self):
        self.assertEqual(
            {p.value for p in Provenance},
            {"empirical", "semantic_transfer", "provisional", "rule_fallback"},
        )

    def test_target_preference_is_frozen_and_validated(self):
        tp = TargetPreference("x", 0.58, 0.59, "default_point", Provenance.RULE_FALLBACK)
        with self.assertRaises(Exception):
            tp.preferred_u = 0.7  # frozen
        with self.assertRaises(ValueError):
            TargetPreference("x", 1.4, 0.5, "default_point", Provenance.RULE_FALLBACK)
        with self.assertRaises(ValueError):
            TargetPreference("x", 0.58, 0.59, "", Provenance.RULE_FALLBACK)
        with self.assertRaises(ValueError):
            TargetPreference("x", 0.5, 0.5, "p", Provenance.EMPIRICAL, confidence=2.0)

    def test_unknown_and_empty_target_resolve_to_rule_fallback(self):
        for name in ("NOPE_BTN", "", None, "I_DOES_NOT_EXIST"):
            pref = resolve_target_preference(name)
            self.assertEqual(pref.provenance, Provenance.RULE_FALLBACK)
            self.assertEqual((pref.preferred_u, pref.preferred_v), RULE_BASE_PREFERRED)
            self.assertEqual(pref.profile_name, RULE_FALLBACK_PROFILE)
            self.assertEqual(pref.confidence, 0.0)

    def test_registry_only_contains_evidence_backed_or_region_entries(self):
        # 每个显式登记项要么有真实来源（EMPIRICAL / SEMANTIC_TRANSFER / PROVISIONAL），
        # 要么是「有独立 shape profile 需求」的 Region 规则兜底条目。规则值与人工值即使
        # 相同，provenance 也必须保持可区分。
        for name, pref in TARGET_PREFERENCES.items():
            self.assertEqual(pref.target_name, name)
            self.assertTrue(pref.note, name)   # 每个显式登记项必须写来源 / 理由
            if pref.provenance is Provenance.RULE_FALLBACK:
                self.assertEqual((pref.preferred_u, pref.preferred_v), RULE_BASE_PREFERRED, name)
                self.assertEqual(pref.profile_name, "default_region", name)
                self.assertEqual(pref.confidence, 0.0, name)
            else:
                self.assertIn(pref.provenance, (
                    Provenance.EMPIRICAL, Provenance.SEMANTIC_TRANSFER, Provenance.PROVISIONAL,
                ))
        # 人工来源不得被规则来源淹没——至少 EMPIRICAL 有 1 个。
        self.assertGreaterEqual(provenance_counts()["empirical"], 1)
        self.assertGreaterEqual(provenance_counts()["rule_fallback"], 1)


# --------------------------------------------------------------------------------------
# §11：default_point profile
# --------------------------------------------------------------------------------------
class DefaultPointProfileTest(unittest.TestCase):
    def test_default_point_exists_center_and_no_personal_hotspot(self):
        p = DEFAULT_PROFILES["default_point"]
        self.assertEqual((p.preferred_u, p.preferred_v), (0.5, 0.5))
        self.assertTrue(p.provisional)
        self.assertGreater(p.core_weight, p.medium_weight)
        self.assertGreater(p.medium_weight, p.tail_weight)

    def test_rule_fallback_resolves_to_default_point(self):
        self.assertEqual(resolve_target_preference("whatever").profile_name, "default_point")
        self.assertEqual(resolve_profile("default_point").name, "default_point")


# --------------------------------------------------------------------------------------
# §10 / §26：默认路径 = sample_target，不再是 LEGACY_UNIFORM 主分布
# --------------------------------------------------------------------------------------
class DefaultIsNoLongerUniformTest(unittest.TestCase):
    def test_sample_target_does_not_call_random_point_in_roi_as_main_path(self):
        # 未登记 target：主分布走 HABIT mixture（core/medium 正态），不是 random_point_in_roi。
        with patch("module.click_sampler.random_point_in_roi") as rp:
            with patch.object(click_sampler, "_choose_component", return_value="core"):
                ClickSampler.sample_target((0, 0, 200, 120), "UNREGISTERED")
        rp.assert_not_called()

    def test_sample_target_delegates_once_to_sample_habit(self):
        # 一次点击 = 一次空间采样（无 double jitter）：sample_target 恰好调用 ClickSampler.sample 一次，
        # 且 strategy=HABIT + 一个 effective profile。
        with patch.object(ClickSampler, "sample", return_value=(1, 2)) as s:
            out = ClickSampler.sample_target((10, 10, 40, 40), "UNREG")
        self.assertEqual(out, (1, 2))
        s.assert_called_once()
        args, kwargs = s.call_args
        self.assertEqual(args[0], (10, 10, 40, 40))
        self.assertEqual(kwargs["strategy"], STRATEGY_HABIT)
        factor = point_size_factor(40)
        self.assertAlmostEqual(kwargs["profile"].preferred_u, 0.5 + 0.08 * factor)
        self.assertAlmostEqual(kwargs["profile"].preferred_v, 0.5 + 0.09 * factor)

    def test_unknown_large_target_rule_anchor_dense_not_uniform_not_fixed(self):
        roi = (0, 0, 200, 200)          # short_side >= 96，完整释放规则锚点
        pts = _samples(roi, "UNKNOWN_TARGET", 6000)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 不是固定中心：大量不同坐标
        self.assertGreater(len(set(pts)), 500)
        # 不是整 ROI 均匀：中央 50%×50% 方框（占面积 25%）应聚集 > 40% 样本
        central = sum(1 for x, y in pts if 50 <= x < 150 and 50 <= y < 150)
        self.assertGreater(central / len(pts), 0.40)
        # 均值贴近规则热点，而不是旧的几何中心 fallback。
        self.assertAlmostEqual(statistics.fmean(xs), 200 * 0.58, delta=8)
        self.assertAlmostEqual(statistics.fmean(ys), 200 * 0.59, delta=8)
        # 全部落在 ROI 内
        self.assertTrue(all(0 <= x < 200 and 0 <= y < 200 for x, y in pts))

    def test_every_rule_type_coord_uses_sample_target(self):
        import inspect
        from module.atom.click import RuleClick
        from module.atom.image import RuleImage
        from module.atom.gif import RuleGif
        from module.atom.ocr import RuleOcr
        for fn in (RuleClick.coord, RuleImage.coord, RuleGif.coord, RuleOcr.coord):
            self.assertIn("sample_target", inspect.getsource(fn))


# --------------------------------------------------------------------------------------
# §9 / §27：Tiny 仍随机
# --------------------------------------------------------------------------------------
class TinyStillRandomTest(unittest.TestCase):
    def test_tiny_roi_is_random_centered_and_narrow(self):
        tiny = (1000, 500, 20, 20)     # 中心 (1010, 510)
        big = (0, 0, 200, 200)
        tp = _samples(tiny, "T", 400)
        bp = _samples(big, "B", 400)
        # 不是固定坐标
        self.assertGreater(len(set(tp)), 8)
        # 落在 Safe ROI 内（default_point margin 0.06 → 20px 上 dx=round(1.2)=1 → [1001,1019)）
        for x, y in tp:
            self.assertTrue(1000 <= x < 1020 and 500 <= y < 520, (x, y))
        # 均值靠中心
        self.assertAlmostEqual(statistics.fmean([p[0] for p in tp]), 1010, delta=2.0)
        self.assertAlmostEqual(statistics.fmean([p[1] for p in tp]), 510, delta=2.0)
        # 绝对散布明显小于大目标
        self.assertLess(statistics.pstdev([p[0] for p in tp]),
                        statistics.pstdev([p[0] for p in bp]) / 3)

    def test_tiny_effective_profile_has_no_tail(self):
        eff = adapt_point_profile(resolve_profile("default_point"), (0, 0, 20, 20))
        self.assertEqual(eff.tail_weight, 0.0)          # f=0 → tail 归零（T7-4 规则）
        self.assertLess(eff.core_sigma_u, DEFAULT_PROFILES["default_point"].core_sigma_u)

    def test_one_pixel_safe_roi_is_the_documented_deterministic_exception(self):
        # Safe ROI 只剩一个整数像素时，允许每次相同坐标（§9 明确的例外）。
        pts = set(_samples((640, 360, 1, 1), "PX", 40))
        self.assertEqual(len(pts), 1)


# --------------------------------------------------------------------------------------
# §8 / §28：尺寸适配连续，无硬分档
# --------------------------------------------------------------------------------------
class SizeContinuityTest(unittest.TestCase):
    def test_size_factor_is_continuous_near_both_anchors(self):
        for a, b in ((23, 25), (95, 97)):
            self.assertLess(abs(point_size_factor(b) - point_size_factor(a)), 0.06)
        self.assertEqual(point_size_factor(24), 0.0)
        self.assertEqual(point_size_factor(96), 1.0)

    def test_effective_profile_changes_smoothly_across_anchor(self):
        base = resolve_profile("default_point")
        def eff(ss):
            return adapt_point_profile(base, (0, 0, ss, ss))
        for lo, hi in ((23, 25), (95, 97)):
            a, b = eff(lo), eff(hi)
            self.assertLess(abs(a.core_sigma_u - b.core_sigma_u), 0.01)
            self.assertLess(abs(a.tail_weight - b.tail_weight), 0.01)

    def test_no_discrete_tier_branching_in_sample_target(self):
        import inspect
        src = inspect.getsource(ClickSampler.sample_target)
        for token in ("if short", "elif", "tiny", "small", "< 24", "< 96"):
            self.assertNotIn(token, src)


# --------------------------------------------------------------------------------------
# §7 / §29：wide_card empirical 热点保留
# --------------------------------------------------------------------------------------
class WideCardEmpiricalPreservedTest(unittest.TestCase):
    def test_area_1_preference_is_empirical_058_059_wide_card(self):
        pref = resolve_target_preference("area_1")
        self.assertEqual(pref.provenance, Provenance.EMPIRICAL)
        self.assertEqual((pref.preferred_u, pref.preferred_v), (0.58, 0.59))
        self.assertEqual(pref.profile_name, "wide_card")
        self.assertNotEqual((pref.preferred_u, pref.preferred_v), (0.68, 0.53))  # 旧 ROI basis

    def test_area_1_full_size_effective_profile_equals_wide_card_base(self):
        # C_AREA_1 真实 ROI short_side 116 ≥ 96 → f=1 → effective 逐字段等于 wide_card base，
        # 全局化后 C_AREA_1 生产落点分布不变。
        from dataclasses import replace, fields
        base = replace(resolve_profile("wide_card"), preferred_u=0.58, preferred_v=0.59)
        eff = adapt_point_profile(base, (514, 141, 223, 116))
        for f in fields(eff):
            self.assertEqual(getattr(eff, f.name), getattr(base, f.name), f.name)

    def test_area_1_sampled_hotspot_biases_toward_058_059(self):
        roi = (514, 141, 223, 116)
        pts = _samples(roi, "area_1", 4000)
        mu = statistics.fmean((x - 514) / 223 for x, _ in pts)
        mv = statistics.fmean((y - 141) / 116 for _, y in pts)
        self.assertGreater(mu, 0.53)   # 偏右于中心
        self.assertGreater(mv, 0.54)   # 偏下于中心


# --------------------------------------------------------------------------------------
# §15 / §31：RuleOcr —— 浮点 bbox 修复保留 + 默认 preferred 采样
# --------------------------------------------------------------------------------------
class RuleOcrDefaultPreferredTest(unittest.TestCase):
    def _ocr_full(self, area, name="O_X"):
        from module.atom.ocr import RuleOcr
        from module.ocr.base_ocr import OcrMode
        o = RuleOcr.__new__(RuleOcr)
        o.name = name
        o.mode = OcrMode.FULL
        o.area = area
        o.roi = (0, 0, 1280, 720)
        return o

    def test_float_bbox_normalizes_then_center_samples_without_typeerror(self):
        o = self._ocr_full((595.4, 293.6, 34.2, 101.7))
        for _ in range(200):
            x, y = o.coord()
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)
            # 落在「完整包住浮点框」的整数 ROI (595,293,35,103) 内
            self.assertTrue(595 <= x <= 630, x)
            self.assertTrue(293 <= y <= 396, y)

    def test_ocr_coord_does_one_spatial_sample_only(self):
        o = self._ocr_full((595.0, 293.0, 34.0, 101.0))
        with patch.object(ClickSampler, "sample", return_value=(600, 300)) as s:
            o.coord()
        s.assert_called_once()   # normalize → sample_target → 恰一次 sample(HABIT)

    def test_unregistered_ocr_text_is_rule_fallback_not_uniform(self):
        pref = resolve_target_preference("O_SOME_TEXT")
        self.assertEqual(pref.provenance, Provenance.RULE_FALLBACK)


if __name__ == "__main__":
    unittest.main()
