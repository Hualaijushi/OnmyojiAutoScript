# This Python file uses the following encoding: utf-8
"""`dev_tools/settlement_trace_check.py` 的纯单元测试（不接设备、不读真实 trace）。

Settlement Contract v3：只做静态 sanity —— 三个结算安全区
（`random_default` / `random_save_right` / `random_save_bottom`）的计数、坐标、ROI 内外、
连续点击间隔、高速重复检测、坐标是否每次重新采样。采样是整 ROI 均匀，无 safe-margin。
不校验「通用结果强制两次点击」时序与「奖励布局 80/20」分流（另属新契约 Level C 设计）。
"""

import json
import tempfile
import unittest
from pathlib import Path

from dev_tools import settlement_trace_check as stc

_DEFAULT_ROI = stc._REGION_ROI["random_default"]
_RIGHT_ROI = stc._REGION_ROI["random_save_right"]


def _line(ts, target, x, y, task="RyouToppa", event="ACTION", action="click"):
    obj = {
        "ts": ts, "config": "oas1", "task": task, "event": event,
        "action": action, "target": target, "result": "ok",
        "elapsed_ms": 5, "extra": {"x": x, "y": y},
    }
    return json.dumps(obj, ensure_ascii=False)


def _write(lines):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    fh.write("\n".join(lines) + "\n")
    fh.close()
    return Path(fh.name)


class ParseTest(unittest.TestCase):
    def test_only_settlement_clicks_kept(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:01.000+08:00", "random_save_right", 1220, 400),
            _line("2026-09-03T12:00:02.000+08:00", "I_FIRE", 640, 360),        # 非结算
            _line("2026-09-03T12:00:03.000+08:00", "random_left", 100, 300),   # legacy 边区
            json.dumps({"ts": "2026-09-03T12:00:04.000+08:00", "event": "TASK"}),
        ])
        clicks = stc.load_clicks(p)
        self.assertEqual([c.target for c in clicks], ["random_default", "random_save_right"])

    def test_missing_xy_skipped(self):
        bad = json.dumps({"ts": "2026-09-03T12:00:00.000+08:00", "event": "ACTION",
                          "action": "click", "target": "random_default", "extra": {}})
        self.assertEqual(stc.load_clicks(_write([bad])), [])

    def test_sorted_by_ts(self):
        p = _write([
            _line("2026-09-03T12:00:05.000+08:00", "random_save_right", 1220, 400),
            _line("2026-09-03T12:00:01.000+08:00", "random_default", 923, 545),
        ])
        clicks = stc.load_clicks(p)
        self.assertEqual([c.target for c in clicks], ["random_default", "random_save_right"])


class CoordStatsTest(unittest.TestCase):
    def test_roi_relative_and_inside(self):
        clicks = stc.load_clicks(_write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:01.000+08:00", "random_default", 900, 540),
        ]))
        rx, ry, rw, rh = _DEFAULT_ROI
        st = stc.coord_stats(clicks, _DEFAULT_ROI, stc._NO_MARGIN)
        self.assertEqual(st["count"], 2)
        self.assertAlmostEqual(st["u_mean"], ((923 - rx) / rw + (900 - rx) / rw) / 2, places=3)
        self.assertEqual(st["inside_roi"], 2)
        self.assertEqual(st["distinct_xy"], 2)

    def test_out_of_roi_flagged(self):
        clicks = stc.load_clicks(_write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 1270, 545),  # x > ROI 右界
        ]))
        st = stc.coord_stats(clicks, _DEFAULT_ROI, stc._NO_MARGIN)
        self.assertEqual(st["inside_roi"], 0)
        self.assertEqual(st["outside_roi"], 1)

    def test_distinct_xy_counts_unique_points(self):
        clicks = stc.load_clicks(_write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 900, 540),
            _line("2026-09-03T12:00:01.000+08:00", "random_default", 900, 540),
            _line("2026-09-03T12:00:02.000+08:00", "random_default", 900, 540),
        ]))
        st = stc.coord_stats(clicks, _DEFAULT_ROI, stc._NO_MARGIN)
        self.assertEqual(st["distinct_xy"], 1)

    def test_empty(self):
        self.assertEqual(stc.coord_stats([], _DEFAULT_ROI, stc._NO_MARGIN), {"count": 0})


class ReportTest(unittest.TestCase):
    def test_healthy_repeated_default_is_ok(self):
        """同一语义 Page 连续多帧点 DEFAULT（间隔 ~0.9s）是正常结算推进，判 OK。"""
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:00.900+08:00", "random_default", 915, 549),
            _line("2026-09-03T12:00:01.830+08:00", "random_default", 940, 520),
            _line("2026-09-03T12:00:02.760+08:00", "random_default", 902, 558),
        ])
        rep = stc.build_report(p)
        self.assertEqual(rep["random_default"]["count"], 4)
        self.assertEqual(rep["random_default"]["distinct_xy"], 4)
        self.assertEqual(rep["intervals"]["fast_repeat_gaps"], [])
        self.assertEqual(rep["segment_shapes"], ["DDDD"])
        self.assertEqual(rep["auto_verdict"], "OK")

    def test_short_gap_above_half_min_not_flagged(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:00.500+08:00", "random_default", 900, 540),
        ])
        self.assertEqual(stc.build_report(p)["auto_verdict"], "OK")

    def test_fast_repeat_gap_detected(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:00.100+08:00", "random_default", 900, 540),   # 0.1s 明显过快
        ])
        rep = stc.build_report(p)
        self.assertEqual(len(rep["intervals"]["fast_repeat_gaps"]), 1)
        self.assertEqual(rep["intervals"]["fast_repeat_gaps"][0]["targets"],
                         "random_default->random_default")
        self.assertEqual(rep["auto_verdict"], "FAIL")

    def test_min_reasonable_gap_is_half_of_configured_min(self):
        self.assertAlmostEqual(stc._MIN_REASONABLE_GAP, stc._INTERVAL_RANGE[0] * 0.5, places=3)
        self.assertEqual(stc._INTERVAL_RANGE, (0.7, 1.0))

    def test_out_of_roi_makes_fail(self):
        p = _write([_line("2026-09-03T12:00:00.000+08:00", "random_default", 1270, 545)])
        rep = stc.build_report(p)
        self.assertEqual(rep["auto_verdict"], "FAIL")
        self.assertTrue(any("ROI 外" in x for x in rep["auto_problems"]))

    def test_all_same_xy_over_many_clicks_flagged(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 900, 540),
            _line("2026-09-03T12:00:00.900+08:00", "random_default", 900, 540),
            _line("2026-09-03T12:00:01.800+08:00", "random_default", 900, 540),
        ])
        rep = stc.build_report(p)
        self.assertEqual(rep["auto_verdict"], "FAIL")
        self.assertTrue(any("坐标完全相同" in x for x in rep["auto_problems"]))

    def test_segments_split_on_large_gap_and_mixed_shape(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:00.900+08:00", "random_save_right", 1220, 400),
            _line("2026-09-03T12:00:30.000+08:00", "random_save_bottom", 1000, 655),  # 30s > 12s → 新段
        ])
        rep = stc.build_report(p)
        self.assertEqual(rep["segments"], 2)
        self.assertEqual(rep["segment_shapes"], ["DR", "B"])

    def test_interval_summary_reported(self):
        p = _write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
            _line("2026-09-03T12:00:00.850+08:00", "random_default", 915, 549),
            _line("2026-09-03T12:00:01.780+08:00", "random_default", 940, 520),
        ])
        s = stc.build_report(p)["intervals"]["gap_summary"]
        self.assertEqual(s["count"], 2)
        self.assertGreaterEqual(s["min"], 0.7)

    def test_no_data_verdict(self):
        rep = stc.build_report(_write([_line("2026-09-03T12:00:00.000+08:00", "I_FIRE", 1, 1)]))
        self.assertEqual(rep["auto_verdict"], "NO_DATA")

    def test_all_three_regions_present_in_report(self):
        rep = stc.build_report(_write([
            _line("2026-09-03T12:00:00.000+08:00", "random_default", 923, 545),
        ]))
        for tgt in ("random_default", "random_save_right", "random_save_bottom"):
            self.assertIn(tgt, rep)


if __name__ == "__main__":
    unittest.main()
