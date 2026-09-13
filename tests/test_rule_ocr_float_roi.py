"""`RuleOcr` 浮点 OCR bbox → 整数点击 ROI 的兼容回归。

背景：`Full.ocr_full()` 会把 OCR / OpenCV 检测框（numpy 浮点多边形）写进 `self.area`，
格式是 `(x, y, width, height)`。自 D007 起底层 `random_point_in_roi()` 强制整数 ROI 契约，
`RuleOcr.coord()` FULL 模式把这个浮点 area 直接传下去就会 `TypeError: ROI必须由整数组成`。

本轮修复只在 `RuleOcr` 专属边界 `_normalize_ocr_click_area()` 做 floor/ceil 规范化：
不放宽 `ClickSampler` / `random_point_in_roi` 的整数契约，不改点击分布算法，
`RuleClick` / `RuleImage` 的静态整数 ROI 语义保持不变。
"""

import unittest
from unittest.mock import patch

import numpy as np

from module.atom.ocr import RuleOcr, _normalize_ocr_click_area
from module.ocr.base_ocr import OcrMode
from module.base.utils.random import random_point_in_roi


REAL_MACHINE_AREA = (595.0, 293.0, 34.0, 101.0)   # Codex 真机日志里触发 TypeError 的值


def _contains(norm, area):
    """规范化后的整数 ROI（半开区间）是否完整包住原浮点框。"""
    nx, ny, nw, nh = norm
    x, y, w, h = area
    return (
        nx <= x
        and ny <= y
        and nx + nw >= x + w
        and ny + nh >= y + h
    )


class NormalizeOcrClickAreaTest(unittest.TestCase):
    """`_normalize_ocr_click_area` 本身的规范化规则。"""

    def test_case1_real_machine_value_becomes_all_int(self):
        norm = _normalize_ocr_click_area(REAL_MACHINE_AREA)
        self.assertEqual(norm, (595, 293, 34, 101))
        for v in norm:
            self.assertIsInstance(v, int)
        # 关键：规范化后交给底层不再抛 TypeError
        x, y = random_point_in_roi(norm)
        self.assertTrue(595 <= x < 629)
        self.assertTrue(293 <= y < 394)

    def test_case2_fractional_bbox_is_geometrically_contained_not_shrunk(self):
        area = (595.4, 293.6, 34.2, 101.7)
        norm = _normalize_ocr_click_area(area)
        for v in norm:
            self.assertIsInstance(v, int)
        # floor 左上 / ceil 右下：(595, 293, 35, 103)
        self.assertEqual(norm, (595, 293, 35, 103))
        self.assertTrue(_contains(norm, area), (norm, area))
        # 不缩小：整数框宽 / 高都不小于原浮点框
        self.assertGreaterEqual(norm[2], area[2])
        self.assertGreaterEqual(norm[3], area[3])

    def test_case3_already_int_roi_semantics_unchanged(self):
        area = (595, 293, 34, 101)
        self.assertEqual(_normalize_ocr_click_area(area), area)
        # list 形态（base_ocr 里 self.roi / self.area 实际是 list）也等价
        self.assertEqual(_normalize_ocr_click_area([595, 293, 34, 101]), (595, 293, 34, 101))
        # float 但取值是整数的情况（595.0 ...）也回到同一个整数框
        self.assertEqual(_normalize_ocr_click_area(REAL_MACHINE_AREA), area)

    def test_case4_tiny_subpixel_bbox_stays_valid_nonzero_region(self):
        area = (10.8, 20.2, 0.4, 0.6)
        norm = _normalize_ocr_click_area(area)
        nx, ny, nw, nh = norm
        self.assertGreaterEqual(nw, 1)
        self.assertGreaterEqual(nh, 1)
        self.assertTrue(_contains(norm, area), (norm, area))
        # 不抛异常，落点在框内
        x, y = random_point_in_roi(norm)
        self.assertTrue(nx <= x < nx + nw)
        self.assertTrue(ny <= y < ny + nh)

    def test_case5_edge_bbox_is_clipped_to_screen(self):
        # 贴右下角，ceil 后本会得到 1281 / 721
        area = (1279.6, 719.6, 1.0, 1.0)
        norm = _normalize_ocr_click_area(area)
        nx, ny, nw, nh = norm
        self.assertLessEqual(nx + nw, 1280)   # 右边界裁到屏幕宽
        self.assertLessEqual(ny + nh, 720)    # 下边界裁到屏幕高
        self.assertGreaterEqual(nw, 1)
        self.assertGreaterEqual(nh, 1)
        # 落点仍在屏幕内（0..1279 / 0..719）
        for _ in range(50):
            x, y = random_point_in_roi(norm)
            self.assertTrue(0 <= x <= 1279, x)
            self.assertTrue(0 <= y <= 719, y)

    def test_zero_size_bbox_is_defended_to_min_1px(self):
        norm = _normalize_ocr_click_area((100.0, 200.0, 0.0, 0.0))
        self.assertEqual(norm, (100, 200, 1, 1))
        self.assertEqual(random_point_in_roi(norm), (100, 200))

    def test_numpy_float_input_returns_plain_python_int(self):
        area = tuple(np.float64(v) for v in (595.4, 293.6, 34.2, 101.7))
        norm = _normalize_ocr_click_area(area)
        for v in norm:
            self.assertIs(type(v), int)

    def test_containment_property_over_many_fractional_boxes(self):
        rng = np.random.RandomState(20260904)
        for _ in range(400):
            x = float(rng.uniform(0, 1200))
            y = float(rng.uniform(0, 640))
            w = float(rng.uniform(0.2, 60))
            h = float(rng.uniform(0.2, 60))
            area = (x, y, w, h)
            norm = _normalize_ocr_click_area(area)
            self.assertTrue(all(isinstance(v, int) for v in norm), norm)
            self.assertGreaterEqual(norm[2], 1)
            self.assertGreaterEqual(norm[3], 1)
            # 未贴边时必须完整包住原框、且不缩小
            if x + w <= 1280 and y + h <= 720:
                self.assertTrue(_contains(norm, area), (norm, area))

    def test_none_or_bad_shape_passthrough(self):
        self.assertIsNone(_normalize_ocr_click_area(None))
        self.assertEqual(_normalize_ocr_click_area((1, 2, 3)), (1, 2, 3))


class RuleOcrCoordFloatRoiTest(unittest.TestCase):
    """`RuleOcr.coord()` 在把 area 交给 ClickSampler 之前完成规范化。"""

    @staticmethod
    def _ocr(mode):
        o = RuleOcr.__new__(RuleOcr)
        o.mode = mode
        return o

    def test_full_mode_float_area_normalized_before_click_sampler(self):
        o = self._ocr(OcrMode.FULL)
        o.area = REAL_MACHINE_AREA
        o.roi = (0, 0, 1280, 720)
        with patch("module.atom.ocr.ClickSampler.sample", return_value=(5, 5)) as m:
            o.coord()
        # §10：ClickSampler 收到的已经是整数 ROI，不是靠采样器内部兜底
        (called_roi,), _ = m.call_args
        self.assertEqual(called_roi, (595, 293, 34, 101))
        for v in called_roi:
            self.assertIsInstance(v, int)

    def test_full_mode_fractional_area_sampler_gets_containing_int_roi(self):
        o = self._ocr(OcrMode.FULL)
        o.area = (595.4, 293.6, 34.2, 101.7)
        o.roi = (0, 0, 1280, 720)
        with patch("module.atom.ocr.ClickSampler.sample", return_value=(5, 5)) as m:
            o.coord()
        (called_roi,), _ = m.call_args
        self.assertTrue(all(isinstance(v, int) for v in called_roi), called_roi)
        self.assertTrue(_contains(called_roi, o.area), (called_roi, o.area))

    def test_single_mode_static_int_roi_passes_through_unchanged(self):
        o = self._ocr(OcrMode.SINGLE)
        o.roi = (595, 293, 34, 101)
        with patch("module.atom.ocr.ClickSampler.sample", return_value=(6, 6)) as m:
            o.coord()
        (called_roi,), _ = m.call_args
        self.assertEqual(called_roi, (595, 293, 34, 101))

    def test_full_mode_real_legacy_uniform_no_typeerror_and_in_bounds(self):
        # 不 mock ClickSampler：走真实 LEGACY_UNIFORM → random_point_in_roi
        o = self._ocr(OcrMode.FULL)
        o.area = REAL_MACHINE_AREA
        o.roi = (0, 0, 1280, 720)
        for _ in range(200):
            x, y = o.coord()
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)
            self.assertTrue(595 <= x < 629, x)
            self.assertTrue(293 <= y < 394, y)


class RuleOcrEndToEndOcrFullChainTest(unittest.TestCase):
    """贴近真机链路：Full.ocr_full 写入浮点 self.area → coord() → 真实 ClickSampler。"""

    def _make_full_ocr(self, box_corners):
        o = RuleOcr.__new__(RuleOcr)
        o.mode = OcrMode.FULL
        o.name = "O_R_SHIKIGAMI"
        o.keyword = "式神育成"
        o.roi = (0, 0, 1280, 720)

        fake = type("BoxedResult", (), {})()
        fake.box = np.array(box_corners, dtype=np.float64)
        o.detect_and_ocr = lambda image, **kw: [fake]
        o.filter = lambda boxed_results, keyword=None: [0]
        return o

    def test_ocr_full_float_box_then_coord_yields_valid_on_screen_click(self):
        # 角点顺序：左上, 右上, 右下, 左下（ocr_full 只用 box[0], box[1,0], box[2,1]）
        o = self._make_full_ocr([
            [595.4, 293.6],
            [629.6, 293.6],
            [629.6, 395.3],
            [595.4, 395.3],
        ])
        area = o.ocr(image=None)
        # ocr_full 确实产出浮点 area
        self.assertTrue(any(not float(v).is_integer() for v in area), area)

        for _ in range(200):
            x, y = o.coord()
            self.assertIsInstance(x, int)
            self.assertIsInstance(y, int)
            # 落点必须落在「完整包住浮点框」的整数区域内
            self.assertTrue(595 <= x <= 629, x)
            self.assertTrue(293 <= y <= 395, y)
            self.assertTrue(0 <= x <= 1279 and 0 <= y <= 719)


class RuleClickRuleImageUnaffectedTest(unittest.TestCase):
    """§13：确认 RuleClick / RuleImage 不受本次 OCR 边界修复影响。"""

    def test_rule_click_coord_does_not_touch_ocr_normalizer(self):
        import inspect
        from module.atom import click as click_atom
        src = inspect.getsource(click_atom.RuleClick.coord)
        self.assertNotIn("_normalize_ocr_click_area", src)

    def test_rule_image_coord_does_not_touch_ocr_normalizer(self):
        import inspect
        from module.atom import image as image_atom
        src = inspect.getsource(image_atom.RuleImage.coord)
        self.assertNotIn("_normalize_ocr_click_area", src)

    def test_rule_click_static_roi_bounds_unchanged(self):
        from module.atom.click import RuleClick
        c = RuleClick(roi_front=(200, 300, 40, 60), roi_back=(0, 0, 1, 1))
        for _ in range(300):
            x, y = c.coord()
            self.assertTrue(200 <= x < 240)
            self.assertTrue(300 <= y < 360)

    def test_normalizer_is_noop_on_static_integer_rois(self):
        # RuleClick / RuleImage 用的那种静态整数 ROI，即使流经规范化也不变
        for roi in [(200, 300, 40, 60), (0, 0, 1, 1), (1276, 716, 4, 4)]:
            self.assertEqual(_normalize_ocr_click_area(roi), roi)


if __name__ == "__main__":
    unittest.main()
