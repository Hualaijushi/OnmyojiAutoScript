# This Python file uses the following encoding: utf-8
"""T7-3.2：`RyouToppa.C_AREA_1` —— 首个普通 Point Target 的显式生产 opt-in（纯静态测试）。

契约：

- `C_AREA_1`（`area_map[0]`）点击经 `RyouToppa.ScriptTask._click_toppa_area` →
  `ClickSampler.sample_point(C_AREA_1.roi_front, DEFAULT_PROFILES["wide_card"])` →
  `adapt_point_profile`（按当前 `roi_front` 尺寸）→ `ClickSampler` HABIT → `self.device.click`。
- `C_AREA_1.roi_front` 当前 `(514,141,223,116)`，`short_side = 116 ≥ 96` → `size_factor = 1.0`
  → effective profile **逐字段等于 `wide_card` base**（preferred / sigma / weights / tail /
  margin / max_attempts / provisional / name 全等，仅对象 identity 是新实例）。T7-4 给
  `adapt_point_profile` 加了 spread / tail 的尺寸适配，但 `factor` 恰为 `1.0` 时是恒等映射，
  所以 C_AREA_1 生产行为不受 T7-4 影响（这是 T7-4 的核心生产护栏）。
- `C_AREA_2..8` 保持 `self.click()` → `RuleClick.coord()` → `LEGACY_UNIFORM`，本轮不迁移。
- `C_AREA_2..8` 保持 `self.click()` → `RuleClick.coord()` → `LEGACY_UNIFORM`，本轮不迁移。
- `RuleClick.coord` / `ClickSampler` 默认策略 / `normal_button` / `I_FIRE` / GeneralBattle
  Settlement 全部未改。Point Target 生产消费者数量恰好为 1。
"""

import inspect
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.RyouToppa import script_task as ryou_mod
from tasks.RyouToppa.script_task import ScriptTask, area_map
from tasks.RyouToppa.assets import RyouToppaAssets
from tasks.RealmRaid.assets import RealmRaidAssets
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.click_profile import DEFAULT_PROFILES, adapt_point_profile, point_size_factor
from module.click_sampler import ClickSampler, LEGACY_UNIFORM, STRATEGY_HABIT

_REPO = Path(__file__).resolve().parent.parent
_C_AREA_1_ROI = (514, 141, 223, 116)


def _make_task():
    task = ScriptTask.__new__(ScriptTask)
    task.device = SimpleNamespace(click=Mock())
    return task


class CArea1CallChainTest(unittest.TestCase):
    def test_c_area_1_uses_sample_point_with_wide_card(self):
        task = _make_task()
        with patch.object(ClickSampler, "sample_point", return_value=(640, 205)) as sp:
            task._click_toppa_area(0)
        sp.assert_called_once_with(RyouToppaAssets.C_AREA_1.roi_front,
                                   DEFAULT_PROFILES["wide_card"])
        task.device.click.assert_called_once_with(x=640, y=205, control_name="area_1")

    def test_c_area_1_final_click_goes_through_device_click(self):
        # 只改「坐标如何产生」，不改「点击如何发送」——仍是 self.device.click。
        task = _make_task()
        with patch.object(ClickSampler, "sample_point", return_value=(1, 2)):
            task._click_toppa_area(0)
        self.assertEqual(task.device.click.call_count, 1)
        _args, kwargs = task.device.click.call_args
        self.assertEqual(set(kwargs), {"x", "y", "control_name"})

    def test_behavior_trace_target_is_rule_name_not_helper_name(self):
        task = _make_task()
        with patch.object(ClickSampler, "sample_point", return_value=(3, 4)):
            task._click_toppa_area(0)
        control_name = task.device.click.call_args.kwargs["control_name"]
        self.assertEqual(control_name, RyouToppaAssets.C_AREA_1.name)
        self.assertEqual(control_name, "area_1")
        for polluted in ("wide_card", "point_click", "habit", "sample_point"):
            self.assertNotEqual(control_name, polluted)

    def test_each_click_resamples_coordinates(self):
        # 不打桩，用真实 sampler：多次点击坐标不复用，且都落在 wide_card Safe ROI 内。
        task = _make_task()
        seen = set()
        for _ in range(400):
            task._click_toppa_area(0)
            seen.add(task.device.click.call_args.kwargs["x"] * 10000
                     + task.device.click.call_args.kwargs["y"])
        self.assertGreater(len(seen), 50)
        x, y, w, h = _C_AREA_1_ROI
        dx, dy = round(0.05 * w), round(0.05 * h)
        sx, sy, sw, sh = x + dx, y + dy, w - 2 * dx, h - 2 * dy
        for call in task.device.click.call_args_list:
            cx, cy = call.kwargs["x"], call.kwargs["y"]
            self.assertTrue(sx <= cx < sx + sw and sy <= cy < sy + sh, (cx, cy))


class CArea1SizeAdaptationTest(unittest.TestCase):
    def test_roi_front_is_current_wip_value(self):
        self.assertEqual(RyouToppaAssets.C_AREA_1.roi_front, _C_AREA_1_ROI)
        self.assertEqual(RyouToppaAssets.C_AREA_1.roi_back, _C_AREA_1_ROI)

    def test_short_side_is_116(self):
        _x, _y, w, h = RyouToppaAssets.C_AREA_1.roi_front
        self.assertEqual(min(w, h), 116)

    def test_size_factor_is_one(self):
        _x, _y, w, h = RyouToppaAssets.C_AREA_1.roi_front
        self.assertEqual(point_size_factor(min(w, h)), 1.0)

    def test_effective_preferred_equals_wide_card_base_hotspot(self):
        eff = adapt_point_profile(DEFAULT_PROFILES["wide_card"],
                                  RyouToppaAssets.C_AREA_1.roi_front)
        self.assertEqual((eff.preferred_u, eff.preferred_v), (0.58, 0.59))

    def test_effective_profile_is_byte_for_byte_wide_card_base(self):
        # T7-4 生产护栏：C_AREA_1 short_side 116 → factor 1.0 → EffectiveProfile 每个字段
        # 都逐字等于 wide_card base（含 T7-4 之后仍会随尺寸变的 sigma / tail）。
        from dataclasses import fields
        base = DEFAULT_PROFILES["wide_card"]
        eff = adapt_point_profile(base, RyouToppaAssets.C_AREA_1.roi_front)
        for f in fields(base):
            self.assertEqual(getattr(eff, f.name), getattr(base, f.name), f.name)
        self.assertIsNot(eff, base)

    def test_sample_point_feeds_habit_and_effective_profile_into_sample(self):
        roi = RyouToppaAssets.C_AREA_1.roi_front
        with patch.object(ClickSampler, "sample", return_value=(9, 9)) as s:
            ClickSampler.sample_point(roi, DEFAULT_PROFILES["wide_card"])
        _args, kwargs = s.call_args
        passed_roi = s.call_args.args[0] if s.call_args.args else kwargs["roi"]
        self.assertEqual(passed_roi, roi)
        self.assertEqual(kwargs["strategy"], STRATEGY_HABIT)
        self.assertEqual(kwargs["strategy"], "habit")
        prof = kwargs["profile"]
        self.assertEqual(prof.name, "wide_card")
        self.assertEqual((prof.preferred_u, prof.preferred_v), (0.58, 0.59))
        self.assertTrue(prof.provisional)


class WideCardProfileFrozenTest(unittest.TestCase):
    def test_wide_card_params_unchanged_from_t7_3_1(self):
        p = DEFAULT_PROFILES["wide_card"]
        self.assertEqual((p.preferred_u, p.preferred_v), (0.58, 0.59))
        self.assertEqual((p.core_sigma_u, p.core_sigma_v), (0.16, 0.16))
        self.assertEqual((p.medium_sigma_u, p.medium_sigma_v), (0.26, 0.24))
        self.assertEqual((p.core_weight, p.medium_weight, p.tail_weight), (0.75, 0.20, 0.05))
        self.assertEqual((p.safe_margin_u, p.safe_margin_v), (0.05, 0.05))
        self.assertEqual(p.max_attempts, 12)
        self.assertTrue(p.provisional)


class OtherAreasStayLegacyTest(unittest.TestCase):
    def test_c_area_2_uses_default_target_path_not_explicit_opt_in(self):
        # T7-5：C_AREA_2 不走 _click_toppa_area 的显式 sample_point（那仍是 C_AREA_1 身份守卫
        # 专属），而是 RuleClick.coord() 的默认 sample_target(roi, name) —— 未登记 → RULE_FALLBACK。
        task = _make_task()
        with patch.object(ClickSampler, "sample_point") as sp, \
             patch.object(ClickSampler, "sample_target", return_value=(7, 7)) as st:
            task._click_toppa_area(1)
        sp.assert_not_called()
        st.assert_called_once_with(RyouToppaAssets.C_AREA_2.roi_front, "area_2")
        task.device.click.assert_called_once_with(x=7, y=7, control_name="area_2")

    def test_areas_2_to_8_never_take_explicit_opt_in_path(self):
        for index in range(1, 8):
            task = _make_task()
            with patch.object(ClickSampler, "sample_point") as sp, \
                 patch.object(ClickSampler, "sample_target", return_value=(5, 5)):
                task._click_toppa_area(index)
            sp.assert_not_called()
            self.assertIsNot(area_map[index]["rule_click"], RyouToppaAssets.C_AREA_1)
            expected = area_map[index]["rule_click"].name
            self.assertEqual(task.device.click.call_args.kwargs["control_name"], expected)

    def test_all_c_area_assets_are_plain_ruleclick(self):
        for i in range(1, 9):
            rule = getattr(RyouToppaAssets, f"C_AREA_{i}")
            self.assertIsInstance(rule, RuleClick)


class OptInIsSingleAndScopedTest(unittest.TestCase):
    def test_click_toppa_area_guards_point_path_on_c_area_1_identity(self):
        src = inspect.getsource(ScriptTask._click_toppa_area)
        self.assertIn("sample_point", src)
        self.assertIn("self.C_AREA_1", src)
        # Point 路径受 `rule is self.C_AREA_1` 守卫，其它区域落到 else 分支的 self.click
        self.assertRegex(src, r"if\s+rule\s+is\s+self\.C_AREA_1\s*:")
        self.assertIn("self.click(rule)", src)

    def test_script_task_has_exactly_one_sample_point_call_site(self):
        src = Path(ryou_mod.__file__).read_text(encoding="utf-8")
        self.assertEqual(src.count(".sample_point("), 1)

    def test_no_other_task_module_consumes_sample_point(self):
        hits = []
        for path in (_REPO / "tasks").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ".sample_point(" in text:
                hits.append(path.relative_to(_REPO).as_posix())
        self.assertEqual(hits, ["tasks/RyouToppa/script_task.py"])

    def test_point_target_production_consumer_count_is_one(self):
        # 唯一入口 `_click_toppa_area` 内唯一 `sample_point` 调用点，且被 C_AREA_1 身份守卫。
        module_src = Path(ryou_mod.__file__).read_text(encoding="utf-8")
        self.assertEqual(module_src.count(".sample_point("), 1)
        helper_src = inspect.getsource(ScriptTask._click_toppa_area)
        self.assertEqual(helper_src.count("sample_point"), 1)


class RuleAndSamplerUntouchedTest(unittest.TestCase):
    def test_rule_click_coord_routes_via_sample_target(self):
        # T7-5：RuleClick.coord 默认改走 sample_target(roi, name)。策略切换封装在 sample_target
        # 内，coord 本身不带 strategy / profile，也不是 RyouToppa 专属的 sample_point opt-in。
        src = inspect.getsource(RuleClick.coord)
        self.assertIn("ClickSampler.sample_target(self.roi_front, self.name)", src)
        for token in ("strategy", "HABIT", "habit", "sample_point", "profile"):
            self.assertNotIn(token, src)

    def test_clicksampler_default_strategy_is_legacy_uniform(self):
        sig = inspect.signature(ClickSampler.sample)
        self.assertEqual(sig.parameters["strategy"].default, LEGACY_UNIFORM)
        with patch("module.click_sampler.random_point_in_roi", return_value=(1, 1)) as rp, \
             patch("module.click_sampler.resolve_profile") as rprof:
            out = ClickSampler.sample((0, 0, 20, 20))
        rp.assert_called_once_with((0, 0, 20, 20))
        rprof.assert_not_called()
        self.assertEqual(out, (1, 1))

    def test_sample_point_is_thin_wrapper_only(self):
        src = inspect.getsource(ClickSampler.sample_point)
        self.assertIn("adapt_point_profile", src)
        self.assertIn("STRATEGY_HABIT", src)
        # 不自己写死热点 / spread / 尺寸分档
        for token in ("if short", "elif", "tiny", "small", "preferred_u ="):
            self.assertNotIn(token, src)


class NormalButtonAndIFireUntouchedTest(unittest.TestCase):
    def test_normal_button_still_provisional_zero_consumers(self):
        self.assertTrue(DEFAULT_PROFILES["normal_button"].provisional)
        hits = []
        # 只找「把 `normal_button` 当 click profile / TargetPreference 名字用」的地方：
        # 这类消费一律以字符串字面量出现（`resolve_profile("normal_button")` /
        # `DEFAULT_PROFILES["normal_button"]` / `sample_target(roi, "normal_button")`）。
        # 裸标识符不算——业务代码里可以有同名局部变量（例如 DailyTrifles 协作适配里
        # `normal_button = getattr(self, f"I_WQ_INVITE_{index}")` 指的是邀请按钮图像规则，
        # 与点击 profile 无关），旧的整词子串扫描会把它误报成消费者。
        profile_key = re.compile(r"""['"]normal_button['"]""")
        for sub in ("tasks", "module"):
            for path in (_REPO / sub).rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if profile_key.search(text) and path.name != "click_profile.py":
                    hits.append(path.relative_to(_REPO).as_posix())
        # 只允许出现在测试 / 文档，不允许出现在生产 task / module 代码
        self.assertEqual(hits, [], hits)

    def test_i_fire_is_untouched_image_rule(self):
        self.assertIsInstance(RealmRaidAssets.I_FIRE, RuleImage)

    def test_ryoutoppa_never_wires_i_fire_into_point_sampling(self):
        src = Path(ryou_mod.__file__).read_text(encoding="utf-8")
        for line in src.splitlines():
            if "I_FIRE" in line:
                self.assertNotIn("sample_point", line)
                self.assertNotIn("HABIT", line)
                self.assertNotIn("adapt_point_profile", line)


class SettlementUntouchedTest(unittest.TestCase):
    def test_settlement_stays_off_the_t7_point_sampling_path(self):
        """RyouToppa 的 C_AREA_1 Point opt-in 不得渗进 GeneralBattle 结算点击。

        结算迁移到 Contract v3（`C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_*` 整 ROI 均匀）后，
        结算相关方法**仍然**不碰 `ClickSampler.sample_point` / `adapt_point_profile` /
        HABIT —— 结算是 Large Safe Region，不是 Point Target。
        """
        from tasks.Component.GeneralBattle import general_battle as gb
        self.assertEqual(gb.GeneralBattle.SETTLEMENT_CLICK_INTERVAL_RANGE, (0.7, 1.0))
        for name in ("_settlement_click", "_sample_settlement_click", "_select_reward_region",
                     "_sample_settlement_point", "_click_settlement_point",
                     "_start_settlement_session", "_advance_settlement_anchor",
                     "_fire_settlement_burst", "_settlement_burst_step"):
            src = inspect.getsource(getattr(gb.GeneralBattle, name))
            self.assertNotIn("sample_point", src, name)
            self.assertNotIn("adapt_point_profile", src, name)
            self.assertNotIn("STRATEGY_HABIT", src, name)


if __name__ == "__main__":
    unittest.main()
