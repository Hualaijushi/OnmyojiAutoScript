# This Python file uses the following encoding: utf-8
"""T7-5 Stage 2：剩余点击入口收口 —— 契约回归。

Stage 1 把普通 Point Rule（`RuleClick`/`RuleImage`/`RuleGif`/`RuleOcr`/`RuleLongClick`）的
默认从 `LEGACY_UNIFORM` 换成 preferred-hotspot 模型。Stage 2 处理仍绕过该默认路径的生产点击：

- **Region Target**（`ClickSampler.sample_region` + `default_region` profile）：GeneralBattle
  Settlement V3 的 `C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`
  的**选定 region 内采样**从整 ROI 均匀改为中心偏置（业务 region 选择不变）。
- **业务私有 random Point**：`GeneralInvite._random_point_in_area`（整框均匀）→ `sample_target`。
- **`RuleLongClick`**：确认它经 `RuleClick.coord` 继承已在 Stage 1 preferred 模型上，长按时长
  属时间模型、与空间模型分离。

锁的命题：Region 热点偏置≠整区均匀、≠固定点；一次点击只做一次空间采样（无 double jitter）；
Region profile 比 Point 宽且**不做** Point 的 sigma/tail 尺寸适配；无人工数据的 Region =
RULE_FALLBACK 基础锚点 `(0.58,0.59)` + preferred-only 尺寸适配 + default_region。
"""

import inspect
import statistics
import unittest
from unittest.mock import Mock, patch

from module import click_sampler
from module.click_sampler import ClickSampler, STRATEGY_HABIT
from module.click_profile import DEFAULT_PROFILES, adapt_preferred_by_size, resolve_profile
from module.click_preference import (
    REGION_FALLBACK_PROFILE,
    Provenance,
    RULE_BASE_PREFERRED,
    TARGET_PREFERENCES,
    resolve_target_preference,
)


# GeneralBattle Settlement V3 三个大安全区（业务已选定后交给 sample_region）
_REGIONS = {
    "random_default": (742, 430, 362, 230),
    "random_save_right": (1185, 209, 87, 441),
    "random_save_bottom": (819, 639, 425, 69),
}


def _region_samples(roi, name, n):
    return [ClickSampler.sample_region(roi, name) for _ in range(n)]


# --------------------------------------------------------------------------------------
# default_region profile
# --------------------------------------------------------------------------------------
class DefaultRegionProfileTest(unittest.TestCase):
    def test_exists_with_neutral_placeholder_and_no_embedded_target_hotspot(self):
        p = DEFAULT_PROFILES["default_region"]
        self.assertEqual((p.preferred_u, p.preferred_v), (0.5, 0.5))
        self.assertTrue(p.provisional)

    def test_wider_spread_than_default_point(self):
        r = DEFAULT_PROFILES["default_region"]
        p = DEFAULT_PROFILES["default_point"]
        self.assertGreater(r.core_sigma_u, p.core_sigma_u)
        self.assertGreater(r.medium_sigma_u, p.medium_sigma_u)
        self.assertGreater(r.medium_weight + r.tail_weight, p.medium_weight + p.tail_weight)

    def test_still_core_dominant_not_uniform_shape(self):
        r = DEFAULT_PROFILES["default_region"]
        self.assertGreater(r.core_weight, r.medium_weight)
        self.assertGreater(r.core_weight, 0.5)     # 仍以窄核为主 → 中心集中

    def test_region_fallback_profile_constant_points_here(self):
        self.assertEqual(REGION_FALLBACK_PROFILE, "default_region")
        self.assertEqual(resolve_profile(REGION_FALLBACK_PROFILE).name, "default_region")


# --------------------------------------------------------------------------------------
# ClickSampler.sample_region
# --------------------------------------------------------------------------------------
class SampleRegionTest(unittest.TestCase):
    def test_registered_regions_resolve_rule_fallback_default_region(self):
        for name in _REGIONS:
            pref = resolve_target_preference(name)
            self.assertEqual(pref.provenance, Provenance.RULE_FALLBACK)
            self.assertEqual((pref.preferred_u, pref.preferred_v), RULE_BASE_PREFERRED)
            self.assertEqual(pref.profile_name, "default_region")
            self.assertTrue(pref.note)

    def test_unregistered_region_name_also_gets_default_region_not_default_point(self):
        with patch.object(ClickSampler, "sample", return_value=(1, 2)) as s:
            ClickSampler.sample_region((0, 0, 400, 200), "SOME_UNREGISTERED_REGION")
        prof = s.call_args.kwargs["profile"]
        self.assertEqual(prof.name, "default_region")      # Region 兜底 ≠ Point 兜底
        self.assertEqual((prof.preferred_u, prof.preferred_v), RULE_BASE_PREFERRED)

    def test_one_spatial_sample_only_no_double_jitter(self):
        with patch.object(ClickSampler, "sample", return_value=(5, 6)) as s:
            out = ClickSampler.sample_region((742, 430, 362, 230), "random_default")
        self.assertEqual(out, (5, 6))
        s.assert_called_once()
        args, kwargs = s.call_args
        self.assertEqual(args[0], (742, 430, 362, 230))
        self.assertEqual(kwargs["strategy"], STRATEGY_HABIT)
        self.assertEqual(
            (kwargs["profile"].preferred_u, kwargs["profile"].preferred_v),
            RULE_BASE_PREFERRED,
        )

    def test_does_not_apply_point_size_factor_to_thin_region(self):
        # sample_target 会对 short_side < 96 的目标缩 σ（adapt_point_profile）；
        # sample_region 只适配 preferred，不应缩 shape——细长条 SAVE_BOTTOM (425x69) 的 σ 必须仍是
        # default_region 的 σ，而不是被 Point 尺寸适配拉到 tiny 锚点。
        with patch.object(ClickSampler, "sample", return_value=(0, 0)) as s:
            ClickSampler.sample_region((819, 639, 425, 69), "random_save_bottom")
        prof = s.call_args.kwargs["profile"]
        base = DEFAULT_PROFILES["default_region"]
        self.assertEqual(prof.core_sigma_u, base.core_sigma_u)
        self.assertEqual(prof.medium_sigma_u, base.medium_sigma_u)
        self.assertEqual(prof.tail_weight, base.tail_weight)
        self.assertEqual(
            (prof.preferred_u, prof.preferred_v),
            adapt_preferred_by_size(*RULE_BASE_PREFERRED, (819, 639, 425, 69)),
        )

    def test_sample_region_does_not_call_adapt_point_profile(self):
        src = inspect.getsource(ClickSampler.sample_region)
        self.assertNotIn("adapt_point_profile(", src)   # 不调用（docstring 里可解释为何不用）
        self.assertIn("adapt_preferred_by_size(", src)
        self.assertIn("strategy=STRATEGY_HABIT", src)

    def test_center_biased_inside_safe_roi_not_uniform_not_fixed(self):
        for name, roi in _REGIONS.items():
            rx, ry, rw, rh = roi
            pts = _region_samples(roi, name, 4000)
            # 全在 region 内
            self.assertTrue(all(rx <= x < rx + rw and ry <= y < ry + rh for x, y in pts), name)
            # 非固定坐标
            self.assertGreater(len(set(pts)), 100, name)
            # 中心明显更密（中央 25% 面积 > 40% 样本；整区均匀只有 ~25%）
            cx, cy = rx + rw / 2, ry + rh / 2
            central = sum(1 for x, y in pts if abs(x - cx) < rw / 4 and abs(y - cy) < rh / 4)
            self.assertGreater(central / len(pts), 0.40, name)
            # 均值贴规则尺寸适配后的热点；不是旧的恒定几何中心 fallback。
            eu, ev = adapt_preferred_by_size(*RULE_BASE_PREFERRED, roi)
            self.assertAlmostEqual(statistics.fmean(x for x, _ in pts), rx + rw * eu,
                                   delta=rw * 0.06, msg=name)
            self.assertAlmostEqual(statistics.fmean(y for _, y in pts), ry + rh * ev,
                                   delta=rh * 0.06, msg=name)

    def test_never_bleeds_into_sibling_region(self):
        # 每个 region 的落点不得越进另外两个 region 的 ROI（大 margin 检查：只要在自身内即可）
        for name, roi in _REGIONS.items():
            rx, ry, rw, rh = roi
            for x, y in _region_samples(roi, name, 1500):
                self.assertTrue(rx <= x < rx + rw and ry <= y < ry + rh, (name, x, y))


# --------------------------------------------------------------------------------------
# RuleLongClick —— 继承 RuleClick.coord，已在 Stage 1 preferred 模型上
# --------------------------------------------------------------------------------------
class RuleLongClickTest(unittest.TestCase):
    def test_longclick_inherits_ruleclick_coord_no_override(self):
        from module.atom.long_click import RuleLongClick
        from module.atom.click import RuleClick
        self.assertIs(RuleLongClick.coord, RuleClick.coord)   # 无独立 override

    def test_longclick_coord_routes_to_sample_target(self):
        from module.atom.long_click import RuleLongClick
        lc = RuleLongClick(roi_front=(100, 200, 60, 40), roi_back=(0, 0, 1, 1), name="lc1")
        with patch("module.atom.click.ClickSampler.sample_target", return_value=(7, 8)) as m:
            out = lc.coord()
        m.assert_called_once_with((100, 200, 60, 40), "lc1")
        self.assertEqual(out, (7, 8))

    def test_longclick_coord_end_to_end_center_biased_in_bounds(self):
        from module.atom.long_click import RuleLongClick
        lc = RuleLongClick(roi_front=(300, 300, 120, 120), roi_back=(0, 0, 1, 1), name="lc2")
        pts = [lc.coord() for _ in range(1500)]
        for x, y in pts:
            self.assertTrue(300 <= x < 420 and 300 <= y < 420)
        cx = cy = 360
        central = sum(1 for x, y in pts if abs(x - cx) < 30 and abs(y - cy) < 30)
        self.assertGreater(central / len(pts), 0.40)   # 不是整 ROI 均匀
        self.assertGreater(len(set(pts)), 50)          # 不是固定中心


# --------------------------------------------------------------------------------------
# GeneralInvite._random_point_in_area → sample_target
# --------------------------------------------------------------------------------------
class GeneralInviteMigrationTest(unittest.TestCase):
    def test_private_random_point_helper_removed(self):
        from tasks.Component.GeneralInvite import general_invite as gi
        self.assertFalse(hasattr(gi.GeneralInvite, "_random_point_in_area"))   # staticmethod 已删
        src = inspect.getsource(gi)
        self.assertNotIn("def _random_point_in_area", src)
        self.assertNotIn("random_point_in_roi(", src)          # 该调用 + import 都移除
        self.assertNotIn("from module.base.utils.random import random_point_in_roi", src)

    def test_friend_select_uses_sample_target_once(self):
        from tasks.Component.GeneralInvite import general_invite as gi
        src = inspect.getsource(gi)
        self.assertIn("ClickSampler.sample_target(select_area, rule.name)", src)
        self.assertEqual(src.count("ClickSampler.sample_target(select_area"), 1)

    def test_no_double_sampling_in_friend_select(self):
        # sample_target 一次 → device.click，中间不夹 random offset / randint。
        from tasks.Component.GeneralInvite import general_invite as gi
        src = inspect.getsource(gi)
        i = src.index("ClickSampler.sample_target(select_area, rule.name)")
        j = src.index("self.device.click(x=click_x, y=click_y", i)
        between = src[i:j]
        for tok in ("randint", "random_int", "np.random", "random.", "+ random"):
            self.assertNotIn(tok, between)


# --------------------------------------------------------------------------------------
# Secret 关卡卡片点击：固定几何中心 (.center) → 每次独立 RuleClick.coord() → sample_target
# --------------------------------------------------------------------------------------
class SecretLayerCardMigrationTest(unittest.TestCase):
    def test_find_battle_click_uses_coord_inside_loop_not_center(self):
        # 源码契约，范围仅限 find_battle 这一个函数（避免全文件 brittle grep）
        from tasks.Secret.script_task import ScriptTask
        src = inspect.getsource(ScriptTask.find_battle)
        self.assertNotIn("click_rule.center", src)                 # 不再取几何中心
        self.assertEqual(src.count("click_rule.coord()"), 1)
        loop_at = src.index("for click_index in range(1, 3):")
        coord_at = src.index("click_rule.coord()")
        self.assertLess(loop_at, coord_at)                         # coord() 在循环体内 → range(1,3) 两次独立采样
        click_at = src.index("self.device.click(", coord_at)
        self.assertLess(coord_at, click_at)                        # 该次 coord() → 该次 click
        # 安全 ROI 原样保留（§3：不扩大、不改 card_x/card_y/LAYER_CARD_HEIGHT/右侧状态文字避让）
        self.assertIn("click_rule = RuleClick(", src)
        self.assertIn("card_x + 12", src)
        self.assertIn("card_y + 8", src)
        self.assertIn("216,", src)
        self.assertIn("self.LAYER_CARD_HEIGHT - 16", src)

    def test_constructed_ruleclick_routes_to_sample_target(self):
        # §6：构造的安全 RuleClick 确实走 RuleClick.coord() → ClickSampler.sample_target()
        from module.atom.click import RuleClick
        roi = (194 + 12, 300 + 8, 216, 121 - 16)
        rc = RuleClick(roi_front=roi, roi_back=roi, name="secret_layer_1_card")
        with patch("module.atom.click.ClickSampler.sample_target", return_value=(5, 5)) as m:
            out = rc.coord()
        m.assert_called_once_with(roi, "secret_layer_1_card")      # 未标定 → RULE_FALLBACK
        self.assertEqual(out, (5, 5))

    def test_two_clicks_use_two_independent_coord_samples(self):
        # §5：驱动真实 find_battle 到点击块 —— coord() 调 2 次、device.click 调 2 次、
        # 两次 click 分别用两次 coord 返回值（不复用同一个 (x,y)）
        from types import SimpleNamespace
        from tasks.Secret.script_task import ScriptTask

        t = ScriptTask.__new__(ScriptTask)
        t.appear = Mock(return_value=False)                        # 无聊天关闭按钮
        t.match_layer = {"一": 1}
        t.layer_title_ocr = SimpleNamespace(detect_and_ocr=Mock(return_value=[
            SimpleNamespace(ocr_text="第一层", box=[[10, 20], [50, 20], [50, 40], [10, 40]]),
        ]))
        t.device = Mock()
        t.device.image = SimpleNamespace(shape=(720, 1280, 3))

        with patch("tasks.Secret.script_task.logger"), \
             patch("tasks.Secret.script_task.time"), \
             patch("tasks.Secret.script_task.RuleOcr") as OcrMock, \
             patch("tasks.Secret.script_task.RuleClick") as ClickMock:
            OcrMock.return_value.ocr.return_value = "未通关"        # 状态 = 未通关 → 进点击块
            ClickMock.return_value.coord.side_effect = [(11, 22), (33, 44)]
            ret = t.find_battle(screenshot=False)

        self.assertEqual(ret, 1)
        self.assertEqual(ClickMock.return_value.coord.call_count, 2)     # 两次独立采样
        self.assertEqual(t.device.click.call_count, 2)
        xy = [(c.kwargs["x"], c.kwargs["y"]) for c in t.device.click.call_args_list]
        self.assertEqual(xy, [(11, 22), (33, 44)])                       # click#1→sample#1, click#2→sample#2
        self.assertEqual(len(set(xy)), 2)                                # 不复用同一个 (x,y)

    def test_secret_click_roi_geometry_unchanged(self):
        from tasks.Secret.script_task import ScriptTask
        self.assertEqual(ScriptTask.LAYER_CARD_HEIGHT, 121)
        self.assertEqual(ScriptTask.LAYER_CARD_LEFT, 194)
        self.assertEqual(ScriptTask.LAYER_STATUS_OFFSET, (240, 40, 100, 50))


# --------------------------------------------------------------------------------------
# Double-sampling 审计：迁移后的入口每次点击只一次空间采样
# --------------------------------------------------------------------------------------
class DoubleSamplingAuditTest(unittest.TestCase):
    def test_sample_target_calls_sample_exactly_once(self):
        with patch.object(ClickSampler, "sample", return_value=(1, 1)) as s:
            ClickSampler.sample_target((10, 10, 80, 80), "X")
        s.assert_called_once()

    def test_sample_region_calls_sample_exactly_once(self):
        with patch.object(ClickSampler, "sample", return_value=(1, 1)) as s:
            ClickSampler.sample_region((10, 10, 400, 200), "random_default")
        s.assert_called_once()

    def test_general_battle_sample_settlement_click_single_sample(self):
        from tasks.Component.GeneralBattle import general_battle as gb
        src = inspect.getsource(gb.GeneralBattle._sample_settlement_click)
        self.assertEqual(src.count("ClickSampler.sample_region("), 1)
        self.assertNotIn("random_int", src)
        self.assertNotIn("+ random", src)


if __name__ == "__main__":
    unittest.main()
