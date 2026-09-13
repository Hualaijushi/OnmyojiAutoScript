"""`dev_tools/runtime_roi_probe.py` 的纯函数单元测试。

不启动真实设备 / MuMu / 图像识别服务，只覆盖记录组装、路径计算、JSONL 追加、
多次探测汇总（matched/unmatched 计数、unique ROI、min/max）、target 注册表。
"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from dev_tools import runtime_roi_probe as rrp


class BuildProbeRecordTest(unittest.TestCase):
    def _now(self):
        return datetime(2026, 9, 2, 10, 0, 0)

    def test_matched_record_has_roi_and_center(self):
        rec = rrp.build_probe_record(
            now=self._now, config_name="yys1", target_name="I_FIRE",
            matched=True, roi_front=(982, 494, 136, 63), viewport_hwnd=12345,
        )
        self.assertTrue(rec["matched"])
        self.assertEqual(rec["config"], "yys1")
        self.assertEqual(rec["target"], "I_FIRE")
        self.assertEqual(rec["roi_front"], [982, 494, 136, 63])
        self.assertEqual(rec["center"], [1050.0, 525.5])
        self.assertEqual(rec["template_width"], 136)
        self.assertEqual(rec["template_height"], 63)
        self.assertEqual(rec["viewport_hwnd"], 12345)
        self.assertNotIn("error", rec)

    def test_unmatched_record_has_no_roi_fields(self):
        rec = rrp.build_probe_record(
            now=self._now, config_name="yys1", target_name="I_FIRE",
            matched=False, roi_front=None, viewport_hwnd=12345,
        )
        self.assertFalse(rec["matched"])
        self.assertNotIn("roi_front", rec)
        self.assertNotIn("center", rec)
        self.assertNotIn("template_width", rec)

    def test_json_serialisable(self):
        rec = rrp.build_probe_record(
            now=self._now, config_name="yys1", target_name="I_FIRE",
            matched=True, roi_front=(1, 2, 3, 4), viewport_hwnd=1,
        )
        json.loads(json.dumps(rec))


class ProbeRecordPathTest(unittest.TestCase):
    def test_path_uses_target_and_date(self):
        p = rrp.probe_record_path("I_FIRE", date(2026, 9, 2), root=Path("X"))
        self.assertEqual(p, Path("X") / "I_FIRE_2026-09-02.jsonl")


class AppendProbeRecordTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_appends_valid_jsonl_lines(self):
        path = self.dir / "sub" / "I_FIRE_2026-09-02.jsonl"
        rrp.append_probe_record(path, {"i": 1})
        rrp.append_probe_record(path, {"i": 2})
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["i"] for x in lines], [1, 2])


class SummarizeRoiSamplesTest(unittest.TestCase):
    def test_all_matched_same_roi_is_stable(self):
        recs = [
            {"matched": True, "roi_front": [982, 494, 136, 63]},
            {"matched": True, "roi_front": [982, 494, 136, 63]},
            {"matched": True, "roi_front": [982, 494, 136, 63]},
        ]
        s = rrp.summarize_roi_samples(recs)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["matched_count"], 3)
        self.assertEqual(s["unmatched_count"], 0)
        self.assertEqual(s["unique_roi_count"], 1)
        self.assertTrue(s["stable"])
        self.assertEqual((s["x_min"], s["x_max"]), (982, 982))
        self.assertEqual((s["w_min"], s["w_max"]), (136, 136))

    def test_varying_roi_reports_range_not_stable(self):
        recs = [
            {"matched": True, "roi_front": [980, 494, 136, 63]},
            {"matched": True, "roi_front": [984, 496, 136, 63]},
            {"matched": False},
        ]
        s = rrp.summarize_roi_samples(recs)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["matched_count"], 2)
        self.assertEqual(s["unmatched_count"], 1)
        self.assertEqual(s["unique_roi_count"], 2)
        self.assertFalse(s["stable"])
        self.assertEqual((s["x_min"], s["x_max"]), (980, 984))
        self.assertEqual((s["y_min"], s["y_max"]), (494, 496))

    def test_all_unmatched(self):
        recs = [{"matched": False}, {"matched": False}]
        s = rrp.summarize_roi_samples(recs)
        self.assertEqual(s["matched_count"], 0)
        self.assertEqual(s["unique_roi_count"], 0)
        self.assertFalse(s["stable"])
        self.assertNotIn("x_min", s)

    def test_empty(self):
        s = rrp.summarize_roi_samples([])
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["matched_count"], 0)
        self.assertFalse(s["stable"])  # 没有任何匹配样本，谈不上“稳定”


class ResolveTargetTest(unittest.TestCase):
    def test_i_fire_resolves_to_a_ruleimage(self):
        target = rrp.resolve_target("I_FIRE")
        self.assertTrue(hasattr(target, "match"))
        self.assertTrue(hasattr(target, "roi_front"))

    def test_unknown_target_raises_clear_error(self):
        with self.assertRaises(ValueError):
            rrp.resolve_target("NOT_A_TARGET")


if __name__ == "__main__":
    unittest.main()
