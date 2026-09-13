"""`dev_tools/click_roi_inventory.py` 的纯单元测试。

只测 AST 抽取 + 纯统计函数，不 import 任何 Task、不启动 Device / MuMu / OCR、
不读真实仓库（除少量断言「工具能在本仓库跑通且计数 > 0」的冒烟用例）。
"""

import unittest

from dev_tools import click_roi_inventory as cri


def _recs(src: str, rel="tasks/Demo/assets.py"):
    return cri.extract_records_from_source(src, rel)


def _by_symbol(records):
    return {r.symbol: r for r in records}


class ExtractRuleClickTest(unittest.TestCase):
    def test_rule_click_roi_front_tuple_extracted(self):
        recs = _recs("C_OK = RuleClick(roi_front=(10, 20, 40, 30), roi_back=(1, 2, 3, 4), name='OK')")
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r.symbol, "C_OK")
        self.assertEqual(r.rule_type, "RuleClick")
        self.assertEqual(r.roi, [10, 20, 40, 30])
        self.assertEqual((r.x, r.y, r.width, r.height), (10, 20, 40, 30))
        self.assertEqual(r.roi_semantics, "fixed")
        self.assertIn("roi_front", r.clickable_reason)

    def test_rule_long_click_counted_and_inherits_click_rect(self):
        recs = _recs("L_ROT = RuleLongClick(roi_front=(5, 5, 21, 21), roi_back=(0, 0, 1, 1), name='r')")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].rule_type, "RuleLongClick")
        self.assertEqual(recs[0].short_side, 21)

    def test_rule_image_roi_front_is_dynamic_template(self):
        recs = _recs("I_FIRE = RuleImage(roi_front=(982, 494, 136, 63), roi_back=(900, 400, 300, 200), "
                     "method='Template matching', threshold=0.8, file='./x.png')")
        r = recs[0]
        self.assertEqual(r.rule_type, "RuleImage")
        self.assertEqual(r.roi, [982, 494, 136, 63])
        self.assertEqual(r.roi_semantics, "dynamic_template")
        self.assertEqual(r.width, 136)
        self.assertEqual(r.height, 63)

    def test_rule_image_captures_template_asset_file(self):
        recs = _recs("I_X = RuleImage(roi_front=(1,2,3,4), roi_back=(1,2,3,4), method='m', "
                     "threshold=0.9, file='./tasks/Demo/demo/x.png')")
        self.assertEqual(recs[0].asset_file, "./tasks/Demo/demo/x.png")

    def test_rule_click_has_no_asset_file(self):
        recs = _recs("C = RuleClick(roi_front=(1,2,30,40), roi_back=(1,2,3,4), name='c')")
        self.assertIsNone(recs[0].asset_file)

    def test_rule_ocr_default_mode_uses_roi(self):
        recs = _recs("O_X = RuleOcr(roi=(10, 10, 100, 40), area=(0, 0, 200, 80), mode='Single', "
                     "method='Default', keyword='k', name='x')")
        r = recs[0]
        self.assertEqual(r.rule_type, "RuleOcr")
        self.assertEqual(r.roi, [10, 10, 100, 40])           # 非 Full → 取 roi
        self.assertIn("roi", r.clickable_reason)

    def test_rule_ocr_full_mode_uses_area(self):
        recs = _recs("O_X = RuleOcr(roi=(10, 10, 100, 40), area=(0, 0, 200, 80), mode='Full', "
                     "method='Default', keyword='k', name='x')")
        r = recs[0]
        self.assertEqual(r.roi, [0, 0, 200, 80])             # Full → 取 area
        self.assertIn("area", r.clickable_reason)

    def test_rule_gif_counted(self):
        recs = _recs("G = RuleGif(targets=[RuleImage(roi_front=(1,2,3,4), roi_back=(1,2,3,4), "
                     "method='m', threshold=0.9, file='a.png')])")
        types = sorted(r.rule_type for r in recs)
        self.assertEqual(types, ["RuleGif", "RuleImage"])

    def test_rule_swipe_and_rule_list_not_counted(self):
        recs = _recs("S = RuleSwipe(roi_front=(1,2,3,4), roi_back=(5,6,7,8), mode='default', name='s')\n"
                     "LI = RuleList(roi_front=(1,2,3,4), roi_back=(5,6,7,8), name='li')")
        self.assertEqual(recs, [])

    def test_non_literal_roi_marked_unknown(self):
        recs = _recs("BASE = (10, 20, 30, 40)\nC = RuleClick(roi_front=BASE, roi_back=(1,2,3,4), name='c')")
        r = _by_symbol(recs)["C"]
        self.assertIsNone(r.roi)
        self.assertIsNone(r.short_side)
        self.assertEqual(r.roi_semantics, "unknown")

    def test_computed_roi_expression_not_guessed(self):
        recs = _recs("C = RuleClick(roi_front=(10, 20, 30 + 5, 40), roi_back=(1,2,3,4), name='c')")
        self.assertIsNone(recs[0].roi)

    def test_negative_int_literal_allowed(self):
        recs = _recs("C = RuleClick(roi_front=(-5, 0, 20, 20), roi_back=(1,2,3,4), name='c')")
        self.assertEqual(recs[0].roi, [-5, 0, 20, 20])

    def test_random_symbol_is_large_safe_area(self):
        recs = _recs("C_RANDOM_ALL = RuleClick(roi_front=(36, 88, 1207, 543), roi_back=(1,2,3,4), name='r')")
        r = recs[0]
        self.assertEqual(r.roi_semantics, "large_safe_area")
        self.assertEqual(r.size_flag, "very_large")

    def test_inline_call_gets_placeholder_symbol(self):
        recs = _recs("x = foo(RuleClick(roi_front=(1, 2, 30, 40), roi_back=(1,2,3,4), name='c'))")
        self.assertEqual(recs[0].symbol, "<inline>")


class ClassifySizeTest(unittest.TestCase):
    def test_short_long_area_aspect(self):
        short, long, area, ar, flag = cri._classify_size(120, 40)
        self.assertEqual((short, long, area), (40, 120, 4800))
        self.assertEqual(ar, 3.0)
        self.assertEqual(flag, "normal")

    def test_degenerate_zero(self):
        short, long, area, ar, flag = cri._classify_size(0, 0)
        self.assertEqual(flag, "degenerate")
        self.assertIsNone(ar)

    def test_very_thin_flag(self):
        _, _, _, ar, flag = cri._classify_size(500, 50)
        self.assertEqual(ar, 10.0)
        self.assertEqual(flag, "very_thin")

    def test_very_large_by_short_side(self):
        _, _, _, _, flag = cri._classify_size(400, 400)
        self.assertEqual(flag, "very_large")

    def test_very_large_by_area(self):
        _, _, _, _, flag = cri._classify_size(200, 1600)
        self.assertEqual(flag, "very_large")

    def test_none_input(self):
        self.assertEqual(cri._classify_size(None, 10)[4], "unknown")


class StatsTest(unittest.TestCase):
    def test_percentile_interpolates(self):
        vals = [10, 20, 30, 40]
        self.assertAlmostEqual(cri._percentile(vals, 0.5), 25.0)
        self.assertAlmostEqual(cri._percentile(vals, 0.0), 10.0)
        self.assertAlmostEqual(cri._percentile(vals, 1.0), 40.0)

    def test_percentile_empty_is_nan(self):
        self.assertNotEqual(cri._percentile([], 0.5), cri._percentile([], 0.5))

    def test_dist_stats_basic(self):
        d = cri.dist_stats([1, 2, 3, 4, 5])
        self.assertEqual(d["count"], 5)
        self.assertEqual(d["min"], 1)
        self.assertEqual(d["max"], 5)
        self.assertEqual(d["median"], 3.0)

    def test_dist_stats_empty(self):
        self.assertEqual(cri.dist_stats([]), {"count": 0})

    def test_histogram_left_right_closed(self):
        buckets = [(1, 8), (9, 16), (17, 24)]
        h = cri.histogram([8, 9, 16, 17, 24, 25], buckets)
        self.assertEqual([b["count"] for b in h], [1, 2, 2])

    def test_dedup_unique_roi_defs_via_scan_repo_shape(self):
        # 同一符号在两段源码重复定义时，scan_repo 会各记一次；
        # 但 build_summary 的计数是「记录条数」——确认逻辑一致、不抛错。
        recs = _recs("A = RuleClick(roi_front=(1,2,30,40), roi_back=(0,0,1,1), name='a')\n"
                     "B = RuleClick(roi_front=(1,2,30,40), roi_back=(0,0,1,1), name='b')")
        summary = cri.build_summary(recs, cri._DEFAULT_BUCKETS)
        self.assertEqual(summary["unique_clickable_roi_defs"], 2)
        self.assertEqual(summary["primary_count"], 2)

    def test_build_summary_confirmed_clickable_contains_rule_click(self):
        recs = _recs("A = RuleClick(roi_front=(1,2,30,40), roi_back=(0,0,1,1), name='a')\n"
                     "I_X = RuleImage(roi_front=(1,2,30,40), roi_back=(0,0,9,9), method='m', "
                     "threshold=0.9, file='x.png')")
        summary = cri.build_summary(recs, cri._DEFAULT_BUCKETS)
        cc = summary["confirmed_clickable"]
        # RuleClick 无条件计入；RuleImage 未标 has_click_consumer → 不计入
        self.assertEqual(cc["count"], 1)

    def test_build_summary_confirmed_clickable_includes_image_with_consumer(self):
        recs = _recs("I_X = RuleImage(roi_front=(1,2,30,40), roi_back=(0,0,9,9), method='m', "
                     "threshold=0.9, file='x.png')")
        recs[0].has_click_consumer = True
        summary = cri.build_summary(recs, cri._DEFAULT_BUCKETS)
        self.assertEqual(summary["confirmed_clickable"]["count"], 1)


class RepoSmokeTest(unittest.TestCase):
    """在真实仓库跑一次，确认工具不炸且量级合理（不锁定精确数字）。"""

    def test_scan_repo_returns_many_records(self):
        recs = cri.scan_repo(list(cri.DEFAULT_ROOTS))
        self.assertGreater(len(recs), 500)
        summary = cri.build_summary(recs, cri._DEFAULT_BUCKETS)
        self.assertIn("short_side", summary)
        self.assertGreater(summary["primary_count"], 300)
        self.assertIn("RuleClick", summary["by_rule_type_defs"])
        # RuleSwipe 绝不出现在类型分布里
        self.assertNotIn("RuleSwipe", summary["by_rule_type_defs"])


if __name__ == "__main__":
    unittest.main()
