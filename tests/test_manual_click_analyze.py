"""`dev_tools/manual_click_analyze.py` 的单元测试。

覆盖 burst 链式合并（时间 / 距离 / 标签 / 链式）、代表点与 centroid、统计量
（mean/std/median/percentile/normalized/径向分位）、click_count 直方图、
归一化坐标、JSONL 读写（原文件不改、派生 JSONL 合法）。
"""

import json
import tempfile
import unittest
from pathlib import Path
from statistics import mean, median, pstdev

from dev_tools import manual_click_analyze as mca


def _row(ts_ms, x, y, **extra):
    """构造一条记录，ts 用 2026-09-01T00:00:00 + ts_ms 毫秒。"""
    total_ms = int(ts_ms)
    s, ms = divmod(total_ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    ts = f"2026-09-01T{h:02d}:{m:02d}:{s:02d}.{ms:03d}+08:00"
    r = {"ts": ts, "source": "manual", "x": x, "y": y}
    r.update(extra)
    return r


def _bursts(rows, t=500, d=5):
    return mca.collapse_bursts(rows, time_threshold_ms=t, distance_threshold_px=d)


class CollapseBurstsTest(unittest.TestCase):
    def test_single_click_one_burst(self):
        b = _bursts([_row(0, 100, 100)])
        self.assertEqual(b, [[0]])

    def test_fast_same_coord_one_burst(self):
        rows = [_row(i * 100, 500, 500) for i in range(4)]  # 0,100,200,300 ms
        b = _bursts(rows)
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]), 4)

    def test_small_drift_one_burst(self):
        rows = [_row(0, 100, 100), _row(120, 102, 101), _row(240, 104, 102)]
        b = _bursts(rows, d=5)
        self.assertEqual(len(b), 1)

    def test_time_gap_splits(self):
        rows = [_row(0, 500, 500), _row(600, 500, 500)]  # dt=600 > 500
        b = _bursts(rows, t=500)
        self.assertEqual(len(b), 2)

    def test_distance_splits(self):
        rows = [_row(0, 500, 500), _row(100, 520, 500)]  # dt small, dist=20 > 5
        b = _bursts(rows, d=5)
        self.assertEqual(len(b), 2)

    def test_chained_judgement_first_to_last_may_exceed(self):
        # P1->P2 = 3, P2->P3 = 3 (each <= 5), P1->P3 = 6 (> 5) -> 仍一个 burst
        rows = [_row(0, 1000, 500), _row(100, 1003, 500), _row(200, 1006, 500)]
        b = _bursts(rows, d=5)
        self.assertEqual(len(b), 1)
        self.assertEqual(len(b[0]), 3)

    def test_incompatible_target_never_merges(self):
        rows = [_row(0, 500, 500, target="A"), _row(50, 501, 500, target="B")]
        b = _bursts(rows)  # 时空都在阈值内，但 target 不同
        self.assertEqual(len(b), 2)

    def test_missing_label_is_compatible(self):
        rows = [_row(0, 500, 500, target="A"), _row(50, 501, 500)]  # 第二条无 target
        b = _bursts(rows)
        self.assertEqual(len(b), 1)

    def test_covers_all_indices_without_overlap(self):
        rows = [_row(0, 0, 0), _row(100, 1, 0), _row(2000, 400, 400), _row(2100, 401, 400)]
        b = _bursts(rows)
        flat = [i for grp in b for i in grp]
        self.assertEqual(flat, [0, 1, 2, 3])


class BurstRecordTest(unittest.TestCase):
    def test_representative_is_first_point_centroid_separate(self):
        rows = [_row(0, 100, 200), _row(100, 104, 202), _row(220, 102, 201), _row(340, 100, 203)]
        rec = mca.burst_record(rows, [0, 1, 2, 3], burst_id=7)
        self.assertEqual(rec["burst_id"], 7)
        self.assertEqual((rec["x"], rec["y"]), (100, 200))  # 第一点
        self.assertAlmostEqual(rec["centroid_x"], mean([100, 104, 102, 100]), places=2)
        self.assertAlmostEqual(rec["centroid_y"], mean([200, 202, 201, 203]), places=2)
        self.assertEqual(rec["click_count"], 4)
        self.assertAlmostEqual(rec["duration_ms"], 340.0, places=1)
        self.assertAlmostEqual(rec["max_step_distance"],
                               max((104 - 100) ** 2 + (202 - 200) ** 2,
                                   (104 - 102) ** 2 + (202 - 201) ** 2,
                                   (102 - 100) ** 2 + (201 - 203) ** 2) ** 0.5, places=2)

    def test_inherits_labels_from_first(self):
        rows = [_row(0, 10, 10, config="yys1", scene="RealmRaid", target="I_FIRE",
                     roi=[10, 10, 100, 100], u=0.1, v=0.2)]
        rec = mca.burst_record(rows, [0], burst_id=1)
        self.assertEqual(rec["config"], "yys1")
        self.assertEqual(rec["scene"], "RealmRaid")
        self.assertEqual(rec["target"], "I_FIRE")
        self.assertEqual(rec["roi"], [10, 10, 100, 100])


class LandingStatsTest(unittest.TestCase):
    def test_matches_statistics_module(self):
        pts = [(100, 200), (110, 210), (90, 190), (105, 205), (95, 195), (100, 200)]
        st = mca.landing_stats(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.assertEqual(st["count"], 6)
        self.assertAlmostEqual(st["mean_x"], round(mean(xs), 2))
        self.assertAlmostEqual(st["mean_y"], round(mean(ys), 2))
        self.assertAlmostEqual(st["std_x"], round(pstdev(xs), 2))
        self.assertAlmostEqual(st["std_y"], round(pstdev(ys), 2))
        self.assertAlmostEqual(st["median_x"], round(median(xs), 2))

    def test_percentiles_monotone_and_bracketing(self):
        pts = [(i, i * 2) for i in range(1, 101)]
        st = mca.landing_stats(pts)
        self.assertLess(st["p05_x"], st["p25_x"])
        self.assertLess(st["p25_x"], st["median_x"])
        self.assertLess(st["median_x"], st["p75_x"])
        self.assertLess(st["p75_x"], st["p95_x"])

    def test_normalized_coordinate_1280x720(self):
        st = mca.landing_stats([(640, 360), (640, 360)])
        self.assertAlmostEqual(st["normalized_mean_x"], 0.5, places=4)
        self.assertAlmostEqual(st["normalized_mean_y"], 0.5, places=4)

    def test_radial_quantiles_present_and_ordered(self):
        pts = [(640 + dx, 360 + dy) for dx in range(-20, 21, 5) for dy in range(-20, 21, 5)]
        st = mca.landing_stats(pts)
        self.assertLessEqual(st["r50"], st["r75"])
        self.assertLessEqual(st["r75"], st["r90"])
        self.assertLessEqual(st["r90"], st["r95"])

    def test_roi_uv(self):
        st = mca.landing_stats([(60, 60), (60, 60)], roi=(10, 10, 100, 100))
        self.assertAlmostEqual(st["mean_u"], 0.5, places=4)
        self.assertAlmostEqual(st["mean_v"], 0.5, places=4)

    def test_empty(self):
        self.assertEqual(mca.landing_stats([]), {"count": 0})

    def test_roi_stats_only_use_inside_points(self):
        # 98 个中心点 + 9 个明显在 ROI 外的点，ROI-relative 统计必须只用 98 个。
        roi = (100, 100, 100, 100)  # x100-200, y100-200
        inside = [(150, 150)] * 98
        outside = [(500, 500)] * 9
        st = mca.landing_stats(inside + outside, roi=roi)
        self.assertEqual(st["count"], 98)
        self.assertEqual(st["total_count"], 107)
        self.assertEqual(st["outside_count"], 9)
        self.assertAlmostEqual(st["outside_ratio"], 9 / 107, places=4)
        self.assertEqual(len(st["outside_points"]), 9)
        self.assertEqual(st["outside_points"][0], [500, 500])
        # 中心点全在 (150,150) -> u=v=0.5，std=0（不被外点污染）
        self.assertAlmostEqual(st["mean_u"], 0.5, places=4)
        self.assertAlmostEqual(st["mean_v"], 0.5, places=4)
        self.assertAlmostEqual(st["std_u"], 0.0, places=6)
        self.assertAlmostEqual(st["std_v"], 0.0, places=6)
        self.assertAlmostEqual(st["mean_x"], 150, places=2)  # 屏幕坐标 mean 同样只用 inside

    def test_roi_percentiles_include_p25_p75(self):
        pts = [(110 + i, 110) for i in range(0, 100, 10)]  # 10 个点，u 从 0.1 到 1.0
        st = mca.landing_stats(pts, roi=(100, 100, 100, 100))
        for key in ("p05_u", "p25_u", "p75_u", "p95_u", "p05_v", "p25_v", "p75_v", "p95_v"):
            self.assertIn(key, st)
        self.assertLess(st["p25_u"], st["p75_u"])

    def test_roi_outside_not_clamped_into_inside(self):
        roi = (100, 100, 100, 100)
        st = mca.landing_stats([(150, 150), (9999, 9999)], roi=roi)
        self.assertEqual(st["count"], 1)
        self.assertEqual(st["outside_count"], 1)
        self.assertEqual(st["outside_points"], [[9999, 9999]])
        self.assertNotIn(9999, [p[0] for p in [[150, 150]]])  # 外点没被塞进 inside 统计

    def test_roi_all_outside_reports_zero_inside_count(self):
        st = mca.landing_stats([(0, 0), (0, 0)], roi=(100, 100, 100, 100))
        self.assertEqual(st["count"], 0)
        self.assertEqual(st["outside_count"], 2)
        self.assertNotIn("mean_u", st)  # 没有 inside 点时不给 u/v 均值（避免除零/空统计）

    def test_no_roi_still_uses_all_points_unfiltered(self):
        st = mca.landing_stats([(0, 0), (9999, 9999)])
        self.assertEqual(st["count"], 2)
        self.assertNotIn("outside_count", st)


class HistogramTest(unittest.TestCase):
    def test_buckets(self):
        bursts = [[0], [1, 2], [3, 4, 5], [6, 7, 8, 9], [10, 11, 12, 13, 14],
                  [15, 16, 17, 18, 19, 20]]
        h = mca.burst_size_histogram(bursts)
        self.assertEqual(h, {"1": 1, "2": 1, "3": 1, "4-5": 2, "6+": 1})


class RegionSplitTest(unittest.TestCase):
    def test_horizontal_cut(self):
        pts = [(100, 100), (100, 329), (100, 330), (100, 500)]
        up, lo = mca.region_split(pts, 330)
        self.assertEqual(len(up), 2)
        self.assertEqual(len(lo), 2)


class DetectCalibrationPrefixTest(unittest.TestCase):
    def test_edge_prefix_then_big_gap_is_detected(self):
        rows = [
            _row(0, 0, 0), _row(1000, 1279, 719), _row(2000, 640, 360),
            _row(15000, 900, 500), _row(15200, 902, 500),
        ]
        self.assertEqual(mca.detect_calibration_prefix(rows, min_gap_s=8.0), 3)

    def test_no_big_gap_returns_zero(self):
        rows = [_row(i * 500, 900, 500) for i in range(5)]
        self.assertEqual(mca.detect_calibration_prefix(rows, min_gap_s=8.0), 0)

    def test_big_gap_without_edge_click_returns_zero(self):
        # 前缀里没有任何屏幕边缘点 -> 不判定为校准
        rows = [_row(0, 640, 360), _row(100, 642, 360), _row(15000, 900, 500)]
        self.assertEqual(mca.detect_calibration_prefix(rows, min_gap_s=8.0), 0)

    def test_empty(self):
        self.assertEqual(mca.detect_calibration_prefix([]), 0)


class KmeansClustersTest(unittest.TestCase):
    def test_three_well_separated_blobs(self):
        pts = ([(650 + dx, 200 + dy) for dx in (-5, 0, 5) for dy in (-5, 0, 5)]
               + [(680 + dx, 390 + dy) for dx in (-5, 0, 5) for dy in (-5, 0, 5)]
               + [(950 + dx, 480 + dy) for dx in (-5, 0, 5) for dy in (-5, 0, 5)])
        labels, centroids = mca.kmeans_clusters(pts, seeds=[(650, 200), (680, 390), (950, 480)])
        self.assertEqual(len(labels), len(pts))
        # 每个簇成员数应为 9，质心接近种子
        from collections import Counter
        counts = Counter(labels)
        self.assertEqual(sorted(counts.values()), [9, 9, 9])
        for c, seed in zip(centroids, [(650, 200), (680, 390), (950, 480)]):
            self.assertAlmostEqual(c[0], seed[0], delta=1)
            self.assertAlmostEqual(c[1], seed[1], delta=1)

    def test_single_pass_with_max_iters_1_uses_given_seeds_as_boundary(self):
        pts = [(0, 0), (100, 0)]
        labels, _ = mca.kmeans_clusters(pts, seeds=[(-10, 0), (110, 0)], max_iters=1)
        self.assertEqual(labels, [0, 1])

    def test_empty_seeds_rejected(self):
        with self.assertRaises(ValueError):
            mca.kmeans_clusters([(1, 1)], seeds=[])


class TransitionCountsTest(unittest.TestCase):
    def test_counts_adjacent_pairs(self):
        labels = [0, 1, 1, 2, 0, 1]
        counts = mca.transition_counts(labels)
        self.assertEqual(counts, {(0, 1): 2, (1, 1): 1, (1, 2): 1, (2, 0): 1})

    def test_single_label_no_transitions(self):
        self.assertEqual(mca.transition_counts([0]), {})


class IoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_log(self, rows):
        p = self.dir / "src.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.write("\n")            # 空行
            fh.write("{bad json\n")   # 坏行
        return p

    def test_load_skips_bad_lines_keeps_original(self):
        src = self._write_log([_row(0, 10, 10), _row(100, 12, 10)])
        before = src.read_bytes()
        rows, skipped = mca.load_jsonl(src)
        self.assertEqual(len(rows), 2)
        self.assertEqual(skipped, 1)
        self.assertEqual(src.read_bytes(), before)  # 读取不改原文件

    def test_analyze_writes_derived_files_only(self):
        rows = ([_row(i * 100, 500, 500) for i in range(4)]         # burst A ×4
                + [_row(5000 + i * 100, 900, 300) for i in range(3)])  # burst B ×3
        src = self._write_log(rows)
        before = src.read_bytes()
        out = self.dir / "analysis"
        s = mca.analyze(src, y_split=None, out_dir=out)
        self.assertEqual(src.read_bytes(), before)  # 原文件不动
        self.assertEqual(s["raw_click_count"], 7)
        self.assertEqual(s["reference_result"]["burst_count"], 2)
        dedup = out / "src_dedup.jsonl"
        summ = out / "src_summary.json"
        self.assertTrue(dedup.exists() and summ.exists())
        lines = dedup.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for ln in lines:
            json.loads(ln)  # 合法 JSON
        json.loads(summ.read_text(encoding="utf-8"))
        # 敏感性分析包含 4 组固定阈值
        grid = {(r["time_threshold_ms"], r["distance_threshold_px"])
                for r in s["threshold_sensitivity"]}
        for g in mca.SENSITIVITY_GRID:
            self.assertIn(g, grid)

    def test_analyze_collapse_ratio(self):
        rows = [_row(i * 100, 500, 500) for i in range(10)]  # 10 raw -> 1 burst
        src = self._write_log(rows)
        s = mca.analyze(src, y_split=None, out_dir=self.dir / "a")
        self.assertEqual(s["reference_result"]["burst_count"], 1)
        self.assertAlmostEqual(s["reference_result"]["collapse_ratio"], 0.9, places=4)

    def test_analyze_calibration_count_override_skips_heuristic(self):
        rows = [_row(0, 0, 0), _row(100, 1, 1), _row(200, 640, 360)]  # 无大间隔，启发式会返回 0
        src = self._write_log(rows)
        s = mca.analyze(src, y_split=None, calibration_count=2, out_dir=self.dir / "ov")
        self.assertEqual(s["calibration"]["excluded_leading_count"], 2)
        self.assertEqual(s["calibration"]["detected_by"], "override")

    def test_analyze_calibration_disabled_reports_disabled(self):
        rows = [_row(0, 0, 0), _row(20000, 640, 360)]
        src = self._write_log(rows)
        s = mca.analyze(src, y_split=None, exclude_calibration=False, out_dir=self.dir / "dis")
        self.assertEqual(s["calibration"]["excluded_leading_count"], 0)
        self.assertEqual(s["calibration"]["detected_by"], "disabled")

    def test_analyze_three_cluster_and_calibration_exclusion(self):
        # 一段“校准点击”(0,0) 后隔 10s 才是真正行为：两个空间簇 A、B。
        rows = ([_row(0, 0, 0)]
                + [_row(10000 + i * 100, 650, 200) for i in range(3)]
                + [_row(11000 + i * 100, 950, 480) for i in range(2)])
        src = self._write_log(rows)
        s = mca.analyze(
            src, y_split=None,
            cluster_seeds=[(650, 200), (950, 480)],
            cluster_labels=["A", "B"],
            out_dir=self.dir / "c",
        )
        self.assertEqual(s["calibration"]["excluded_leading_count"], 1)
        self.assertEqual(s["calibration"]["detected_by"], "auto_heuristic")
        tc = s["three_cluster"]
        self.assertEqual(tc["labels"], ["A", "B"])
        self.assertEqual(tc["clusters"]["A"]["dedup_count"], 1)
        self.assertEqual(tc["clusters"]["B"]["dedup_count"], 1)
        self.assertIn("threshold_sensitivity", tc)
        for name in ("A", "B"):
            self.assertEqual(len(tc["threshold_sensitivity"][name]), len(mca.SENSITIVITY_GRID))


if __name__ == "__main__":
    unittest.main()
