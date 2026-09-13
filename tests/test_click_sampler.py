"""`module/click_sampler.py`（ClickSampler v1）+ Rule*.coord 接入的行为等价测试。

本轮核心命题：**引入 ClickSampler 只是加了一层抽象，不改变现有生产点击分布**。
所以测试重点是「LEGACY_UNIFORM 与既有 random_point_in_roi 语义等价」和「4 个
Rule.coord 都改成经 ClickSampler、返回值结构不变」。不写「跑 100 次必须覆盖每个
像素」这类概率脆弱断言。
"""

import unittest
from unittest.mock import patch

from module import click_sampler
from module.click_sampler import (
    LEGACY_UNIFORM,
    STRATEGY_HABIT,
    STRATEGY_STRICT,
    STRATEGY_UNIFORM,
    ClickSampler,
)
from module.base.utils.random import random_point_in_roi


class ClickSamplerBoundsTest(unittest.TestCase):
    def test_output_inside_roi_half_open(self):
        roi = (100, 200, 30, 40)
        for _ in range(500):
            x, y = ClickSampler.sample(roi)
            self.assertTrue(100 <= x < 130, x)
            self.assertTrue(200 <= y < 240, y)

    def test_output_is_int_tuple(self):
        x, y = ClickSampler.sample((0, 0, 10, 10))
        self.assertIsInstance(x, int)
        self.assertIsInstance(y, int)

    def test_does_not_mutate_input_roi(self):
        roi = [5, 6, 7, 8]
        before = list(roi)
        ClickSampler.sample(tuple(roi))
        ClickSampler.sample(roi)
        self.assertEqual(roi, before)

    def test_uses_current_roi_each_call_no_caching(self):
        seen = []
        for roi in [(0, 0, 5, 5), (1000, 1000, 3, 3), (50, 60, 2, 2)]:
            x, y = ClickSampler.sample(roi)
            seen.append((roi, x, y))
        for (rx, ry, rw, rh), x, y in seen:
            self.assertTrue(rx <= x < rx + rw)
            self.assertTrue(ry <= y < ry + rh)

    def test_1x1_roi_is_deterministic(self):
        for _ in range(50):
            self.assertEqual(ClickSampler.sample((42, 99, 1, 1)), (42, 99))

    def test_normal_rect_can_reach_both_edges(self):
        # 非概率脆弱：注入固定 RNG，验证能取到下界和上界-1，且没有中心强制偏置。
        roi = (10, 20, 100, 50)
        with patch.object(click_sampler.random_point_in_roi.__globals__["_rng"],
                          "randrange", side_effect=lambda a, b: a):
            self.assertEqual(ClickSampler.sample(roi), (10, 20))
        with patch.object(click_sampler.random_point_in_roi.__globals__["_rng"],
                          "randrange", side_effect=lambda a, b: b - 1):
            self.assertEqual(ClickSampler.sample(roi), (109, 69))

    def test_propagates_helper_errors(self):
        with self.assertRaises(ValueError):
            ClickSampler.sample((0, 0, 0, 10))       # 宽 0
        with self.assertRaises(TypeError):
            ClickSampler.sample((0, 0, 10.5, 10))    # 非整数


class ClickSamplerStrategyTest(unittest.TestCase):
    def test_legacy_uniform_delegates_to_random_point_in_roi(self):
        roi = (7, 8, 9, 10)
        sentinel = (123, 456)
        with patch("module.click_sampler.random_point_in_roi", return_value=sentinel) as m:
            out = ClickSampler.sample(roi)
        m.assert_called_once_with(roi)
        self.assertEqual(out, sentinel)

    def test_legacy_uniform_semantic_equivalence_same_rng_state(self):
        # 同一段 RNG 序列下，ClickSampler.sample 与直接 random_point_in_roi 结果一致。
        roi = (11, 22, 33, 44)
        seq = [17, 5, 30, 40, 0, 0]
        with patch.object(click_sampler.random_point_in_roi.__globals__["_rng"],
                          "randrange", side_effect=list(seq)):
            via_sampler = [ClickSampler.sample(roi) for _ in range(3)]
        with patch.object(random_point_in_roi.__globals__["_rng"],
                          "randrange", side_effect=list(seq)):
            direct = [random_point_in_roi(roi) for _ in range(3)]
        self.assertEqual(via_sampler, direct)

    def test_habit_strict_uniform_are_implemented_and_stay_in_bounds(self):
        # T7-1 第 2 阶段：这三个策略已实现（详见 tests/test_click_profile.py），
        # 这里只快速确认它们不再抛 NotImplementedError、结果落在 ROI 内。
        roi = (100, 100, 200, 160)
        for s in (STRATEGY_HABIT, STRATEGY_STRICT, STRATEGY_UNIFORM):
            for _ in range(50):
                x, y = ClickSampler.sample(roi, strategy=s)
                self.assertTrue(100 <= x < 300, (s, x))
                self.assertTrue(100 <= y < 260, (s, y))

    def test_unknown_strategy_raises_value_error(self):
        with self.assertRaises(ValueError):
            ClickSampler.sample((0, 0, 10, 10), strategy="gaussian")

    def test_rule_default_path_is_sample_target_not_legacy_uniform(self):
        # T7-5：生产 Rule 默认路径改为按目标 preferred 热点采样（ClickSampler.sample_target），
        # 不再是整 ROI LEGACY_UNIFORM。策略切换封装在 sample_target 内，coord 本身不带 strategy。
        import inspect

        from module.atom import click as click_atom
        src = inspect.getsource(click_atom.RuleClick.coord)
        self.assertIn("ClickSampler.sample_target(self.roi_front, self.name)", src)
        self.assertNotIn("ClickSampler.sample(self.roi_front)", src)
        self.assertNotIn("strategy", src)

    def test_default_strategy_is_legacy_uniform(self):
        with patch("module.click_sampler.random_point_in_roi", return_value=(1, 1)) as m:
            ClickSampler.sample((0, 0, 2, 2))
        m.assert_called_once()


class RuleCoordRoutingTest(unittest.TestCase):
    """T7-5：5 个正常点击 coord 入口都走 ClickSampler.sample_target（roi + 目标身份），
    返回值结构不变，OCR 仍先做浮点 → 整数规范化。"""

    def test_rule_click_coord_routes_to_sample_target(self):
        from module.atom.click import RuleClick

        c = RuleClick(roi_front=(10, 20, 30, 40), roi_back=(0, 0, 5, 5), name="t")
        with patch("module.atom.click.ClickSampler.sample_target", return_value=(1, 2)) as m:
            out = c.coord()
        m.assert_called_once_with((10, 20, 30, 40), "t")
        self.assertEqual(out, (1, 2))

    def test_rule_long_click_inherits_click_coord(self):
        from module.atom.long_click import RuleLongClick

        lc = RuleLongClick(roi_front=(1, 2, 3, 4), roi_back=(0, 0, 1, 1), name="lc")
        with patch("module.atom.click.ClickSampler.sample_target", return_value=(9, 9)) as m:
            out = lc.coord()
        m.assert_called_once_with((1, 2, 3, 4), "lc")
        self.assertEqual(out, (9, 9))

    def test_rule_image_coord_uses_current_roi_front_after_update(self):
        from module.atom.image import RuleImage

        img = RuleImage(roi_front=(100, 100, 50, 50), roi_back=(0, 0, 1, 1),
                        method="Template matching", threshold=0.8, file="./x.png")
        img.roi_front = [500, 510, 20, 30]  # 模拟 match 后 _update_roi_front
        with patch("module.atom.image.ClickSampler.sample_target", return_value=(7, 7)) as m:
            out = img.coord()
        m.assert_called_once_with([500, 510, 20, 30], "X")  # name = 文件名 stem 大写
        self.assertEqual(out, (7, 7))

    def test_rule_gif_coord_routes(self):
        from module.atom.gif import RuleGif
        from module.atom.image import RuleImage

        g = RuleGif.__new__(RuleGif)
        g.roi_front = [1, 2, 3, 4]
        g.appear_target = RuleImage(roi_front=(0, 0, 1, 1), roi_back=(0, 0, 1, 1),
                                    method="Template matching", threshold=0.8, file="./gif_t.png")
        with patch("module.atom.gif.ClickSampler.sample_target", return_value=(3, 4)) as m:
            out = g.coord()
        m.assert_called_once_with([1, 2, 3, 4], "GIF_T")
        self.assertEqual(out, (3, 4))

    def test_rule_ocr_coord_routes_full_and_single(self):
        from module.atom.ocr import RuleOcr
        from module.ocr.base_ocr import OcrMode

        o = RuleOcr.__new__(RuleOcr)
        o.name = "O_T"
        o.mode = OcrMode.FULL
        o.area = (7, 8, 9, 10)
        o.roi = (1, 1, 2, 2)
        with patch("module.atom.ocr.ClickSampler.sample_target", return_value=(5, 5)) as m:
            o.coord()
        m.assert_called_once_with((7, 8, 9, 10), "O_T")   # 已整数 → 规范化后不变

        o.mode = OcrMode.SINGLE
        with patch("module.atom.ocr.ClickSampler.sample_target", return_value=(6, 6)) as m:
            o.coord()
        m.assert_called_once_with((1, 1, 2, 2), "O_T")

    def test_rule_click_coord_end_to_end_stays_in_bounds(self):
        # T7-5：分布从整 ROI 均匀改成中心偏置，但落点仍严格落在 ROI 内（Safe ROI ⊂ ROI）。
        from module.atom.click import RuleClick

        c = RuleClick(roi_front=(200, 300, 40, 60), roi_back=(0, 0, 1, 1), name="b")
        for _ in range(300):
            x, y = c.coord()
            self.assertTrue(200 <= x < 240)
            self.assertTrue(300 <= y < 360)


if __name__ == "__main__":
    unittest.main()
