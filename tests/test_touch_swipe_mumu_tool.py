# This Python file uses the following encoding: utf-8
"""`dev_tools/test_touch_swipe_mumu.py` 的纯逻辑单元测试。

只覆盖不接设备的部分：坐标解析、test_id、轨迹统计、record 组装、JSON 落盘、
PNG 生成、`--curve` 的 dev 随机源。**不连 MuMu、不构造 Device、不发任何输入。**
"""

import json
import math
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import cv2

from dev_tools.test_touch_swipe_mumu import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    ForcedCurveRng,
    build_record,
    draw_trajectory_png,
    fit_screen_rect,
    make_test_id,
    parse_point,
    save_json,
    screen_to_panel,
    trajectory_bbox,
    trajectory_segments,
    trajectory_stats,
    zoom_transform,
)
from module.device.touch_swipe_model import TouchSwipeModel, TouchSwipeParams


class ParsePointTest(unittest.TestCase):
    def test_valid_with_spaces(self):
        self.assertEqual(parse_point("520, 560"), (520, 560))
        self.assertEqual(parse_point("0,0"), (0, 0))
        self.assertEqual(parse_point("-3,7"), (-3, 7))

    def test_invalid(self):
        for bad in ("520", "520,560,1", "a,b", "520,", "", "5.5,6"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_point(bad)


class MakeTestIdTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(make_test_id(datetime(2026, 9, 4, 10, 15, 23)), "20260904_101523")
        self.assertRegex(make_test_id(datetime.now()), r"^\d{8}_\d{6}$")


class TrajectorySegmentsTest(unittest.TestCase):
    """executor 时间对齐的核心防回归用例（任务规格 §5 / §13 / §14 / §15）。

    executor 命令流：DOWN(p0) | MOVE(p1) WAIT(dt1) MOVE(p2) WAIT(dt2) ... MOVE(p_{n-1})
    WAIT(dt_{n-1}) | UP。所以 dt_i 是「到达 p_i 后、移动到 p_{i+1} 前的停留」，
    段 p_i→p_{i+1} 的时间就是 dt_i，i 取 1..n-2。
    """

    MANUAL = [(0, 0, 0), (20, 0, 5), (25, 0, 20), (35, 0, 10)]

    def test_manual_sample_exact_alignment(self):
        segs = trajectory_segments(self.MANUAL)
        self.assertEqual(len(segs), 2)                      # p0→p1 与 dt_last 都不成段
        self.assertEqual(segs[0], {
            "from_index": 1, "to_index": 2,
            "distance_px": 5.0, "dt_ms": 5, "speed_px_per_ms": 1.0,
        })
        self.assertEqual(segs[1], {
            "from_index": 2, "to_index": 3,
            "distance_px": 10.0, "dt_ms": 20, "speed_px_per_ms": 0.5,
        })

    def test_first_segment_p0_to_p1_excluded(self):
        # p0 是 DOWN，p0→p1 没有 trajectory 显式 dt 描述，不给它伪造 speed（§15）
        segs = trajectory_segments(self.MANUAL)
        self.assertTrue(all(s["from_index"] >= 1 for s in segs))
        self.assertFalse(any(s["from_index"] == 0 for s in segs))
        # p0→p1 的 20px 位移不出现在任何 segment 的 distance 里
        self.assertNotIn(20.0, [s["distance_px"] for s in segs])

    def test_last_dt_not_used_as_segment_time(self):
        # dt_{n-1}（本例 dt3=10）是「最后 MOVE → UP 前的停留」，不能配给前一段（§14）
        segs = trajectory_segments(self.MANUAL)
        seg_dts = [s["dt_ms"] for s in segs]
        self.assertEqual(seg_dts, [5, 20])                  # 恰好 dt_1 .. dt_{n-2}
        self.assertNotIn(10, seg_dts)                       # dt_last 缺席
        # 若错配（p2→p3 用 dt3=10）会得到 speed=1.0；正确是 10/20=0.5
        self.assertEqual(segs[-1]["speed_px_per_ms"], 0.5)

    def test_two_and_three_point_edges(self):
        # 2 点（DOWN + 1 MOVE + UP）：唯一 dt 是 pre-UP dwell → 0 个 MOVE→MOVE 段
        self.assertEqual(trajectory_segments([(0, 0, 0), (10, 10, 9)]), [])
        # 3 点：恰好 1 段（p1→p2 用 dt_1）
        segs = trajectory_segments([(0, 0, 0), (5, 0, 7), (10, 0, 12)])
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["from_index"], 1)
        self.assertEqual(segs[0]["dt_ms"], 7)
        self.assertAlmostEqual(segs[0]["speed_px_per_ms"], round(5 / 7, 4))

    def test_segment_count_is_point_count_minus_two(self):
        traj = TouchSwipeModel(rng=ForcedCurveRng("left")).generate((520, 560), (520, 300))
        segs = trajectory_segments(traj)
        self.assertEqual(len(segs), len(traj) - 2)
        # 连续覆盖 p1..p_{n-1}，无缝、无重叠
        self.assertEqual([s["from_index"] for s in segs], list(range(1, len(traj) - 1)))
        self.assertEqual([s["to_index"] for s in segs], list(range(2, len(traj))))


class TrajectoryStatsTest(unittest.TestCase):
    def test_known_small_trajectory(self):
        traj = [(0, 0, 0), (0, 10, 5), (0, 25, 10), (3, 40, 5)]
        st = trajectory_stats(traj)
        self.assertEqual(st["point_count"], 4)
        # total_dt_ms 不变：所有显式 WAIT 之和（0+5+10+5，含 pre-UP dwell）
        self.assertEqual(st["total_dt_ms"], 20)
        self.assertAlmostEqual(st["straight_distance_px"], math.hypot(3, 40), places=2)
        # actual_path_length_px 不变：全路径（含 p0→p1）
        expect_path = 10 + 15 + math.hypot(3, 15)
        self.assertAlmostEqual(st["actual_path_length_px"], round(expect_path, 2), places=2)
        self.assertEqual(st["min_y"], 0)
        self.assertEqual(st["max_y"], 40)
        self.assertEqual(st["max_dx_px"], 3)
        # speed 走 executor 对齐的段：4 点 → 2 段（p1→p2 用 dt=5，p2→p3 用 dt=10）
        self.assertEqual(st["segment_count"], 2)
        self.assertEqual(len(st["segment_speeds_px_per_ms"]), 2)
        seg1_speed = 15 / 5          # dist(p1,p2)=15 / dt_1=5
        seg2_speed = math.hypot(3, 15) / 10   # dist(p2,p3) / dt_2=10
        self.assertAlmostEqual(st["segment_speeds_px_per_ms"][0], round(seg1_speed, 4))
        self.assertAlmostEqual(st["segment_speeds_px_per_ms"][1], round(seg2_speed, 4))
        # avg = Σseg_dist / Σseg_dt（只统计有效段），max = 段速度最大值
        self.assertAlmostEqual(st["avg_speed_px_per_ms"],
                               round((15 + math.hypot(3, 15)) / (5 + 10), 4))
        self.assertAlmostEqual(st["max_speed_px_per_ms"],
                               round(max(seg1_speed, seg2_speed), 4))

    def test_unrelated_stats_unchanged(self):
        traj = [(0, 0, 0), (0, 10, 5), (0, 25, 10), (3, 40, 5)]
        st = trajectory_stats(traj)
        # 与本问题无关的统计保持原定义
        self.assertEqual(st["point_count"], 4)
        self.assertEqual(st["total_dt_ms"], 20)
        self.assertEqual(st["min_dt_ms"], 5)          # min(dt_1..dt_{n-1}) = min(5,10,5)
        self.assertEqual(st["max_dt_ms"], 10)         # max(dt_1..dt_{n-1}) = max(5,10,5)
        self.assertEqual(st["min_x"], 0)
        self.assertEqual(st["max_x"], 3)

    def test_rejects_too_short(self):
        with self.assertRaises(ValueError):
            trajectory_stats([(0, 0, 0)])

    def test_real_model_trajectory_shape(self):
        traj = TouchSwipeModel(rng=ForcedCurveRng("left")).generate((520, 560), (520, 300))
        st = trajectory_stats(traj)
        self.assertGreaterEqual(st["point_count"], 8)
        self.assertAlmostEqual(st["straight_distance_px"], 260.0, places=1)
        # ForcedCurveRng('left') 把曲率钉到 -max_curve_px=16
        self.assertAlmostEqual(st["max_lateral_offset_px"], 16.0, delta=1.5)
        # minimum-jerk：中段段速度明显高于两端（executor 对齐后仍成立）
        speeds = st["segment_speeds_px_per_ms"]
        self.assertEqual(len(speeds), len(traj) - 2)
        n = len(speeds)
        third = max(1, n // 3)
        mid = sum(speeds[third:2 * third]) / third
        first = sum(speeds[:third]) / third
        last = sum(speeds[2 * third:]) / (n - 2 * third)
        self.assertGreater(mid, first)
        self.assertGreater(mid, last)


class BuildRecordTest(unittest.TestCase):
    def _traj(self):
        return TouchSwipeModel().generate((520, 560), (520, 300))

    def test_record_has_required_keys(self):
        traj = self._traj()
        rec = build_record(
            test_id="20260904_101523", config_name="oas1", start=(520, 560), end=(520, 300),
            curve_mode="auto", trajectory=traj, params=TouchSwipeParams(),
            generated_at=datetime(2026, 9, 4, 10, 15, 23),
        )
        for key in ("test_id", "config", "control_name", "curve_mode", "start", "end",
                    "point_count", "total_dt_ms", "max_dx_px", "min_x", "max_x",
                    "min_y", "max_y", "params", "trajectory", "executed"):
            self.assertIn(key, rec)
        self.assertEqual(rec["start"], [520, 560])
        self.assertEqual(rec["end"], [520, 300])
        self.assertEqual(rec["control_name"], "TOUCH_SWIPE_LEVEL_C")
        self.assertEqual(rec["point_count"], len(traj))
        self.assertFalse(rec["executed"])

    def test_trajectory_entries_indexed(self):
        traj = self._traj()
        rec = build_record(
            test_id="T", config_name="oas1", start=(520, 560), end=(520, 300),
            curve_mode="auto", trajectory=traj, params=TouchSwipeParams(),
            generated_at=datetime.now(),
        )
        self.assertEqual(len(rec["trajectory"]), len(traj))
        for i, e in enumerate(rec["trajectory"]):
            self.assertEqual(e["index"], i)
            self.assertEqual((e["x"], e["y"], e["dt_ms"]), tuple(traj[i]))
        self.assertEqual(rec["trajectory"][0]["dt_ms"], 0)

    def test_params_read_from_real_object(self):
        params = TouchSwipeParams()
        rec = build_record(
            test_id="T", config_name="oas1", start=(520, 560), end=(520, 300),
            curve_mode="auto", trajectory=self._traj(), params=params,
            generated_at=datetime.now(),
        )
        for field in ("avg_step_px", "min_points", "max_points", "base_dt_ms",
                      "end_slow_ratio", "dt_jitter_ms", "min_dt_ms", "max_dt_ms",
                      "max_curve_px", "curve_px_ratio", "tail_correction_enable",
                      "tail_correction_pct", "tail_correction_max_px"):
            self.assertIn(field, rec["params"])
        self.assertEqual(rec["params"]["max_curve_px"], params.max_curve_px)
        self.assertEqual(rec["params"]["tail_correction_enable"], params.tail_correction_enable)


class SaveJsonAndPngTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.model = TouchSwipeModel()
        self.traj = self.model.generate((520, 620), (520, 180))
        self.rec = build_record(
            test_id="20260904_101523", config_name="oas1", start=(520, 620), end=(520, 180),
            curve_mode="auto", trajectory=self.traj, params=self.model.params,
            generated_at=datetime.now(),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_json_roundtrips(self):
        p = self.dir / "sub" / "touch_swipe_20260904_101523.json"
        save_json(p, self.rec)
        self.assertTrue(p.exists())
        loaded = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(loaded["point_count"], len(self.traj))
        self.assertEqual(loaded["trajectory"][-1]["x"], self.traj[-1][0])
        self.assertEqual(loaded["trajectory"][-1]["y"], self.traj[-1][1])

    def test_draw_png_creates_readable_image_new_layout(self):
        p = self.dir / "touch_swipe_20260904_101523.png"
        draw_trajectory_png(p, self.rec)
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 1000)
        img = cv2.imread(str(p))
        self.assertIsNotNone(img)
        # 新布局 1400x900（A1 Screen View + A2 Zoomed View + B/C/D）
        self.assertEqual(img.shape, (900, 1400, 3))

    def test_draw_png_default_size_is_1400x900(self):
        import inspect

        from dev_tools import test_touch_swipe_mumu as tool

        sig = inspect.signature(tool.draw_trajectory_png)
        self.assertEqual(sig.parameters["size"].default, (1400, 900))

    def test_png_all_curve_modes_render(self):
        for mode in ("left", "straight", "right"):
            model = TouchSwipeModel(rng=ForcedCurveRng(mode))
            traj = model.generate((520, 560), (520, 300))
            rec = build_record(
                test_id="T_" + mode, config_name="oas1", start=(520, 560), end=(520, 300),
                curve_mode=mode, trajectory=traj, params=model.params,
                generated_at=datetime.now(),
            )
            p = self.dir / f"curve_{mode}.png"
            draw_trajectory_png(p, rec)
            img = cv2.imread(str(p))
            self.assertEqual(img.shape, (900, 1400, 3))

    def test_png_from_same_trajectory_as_json(self):
        # PNG 与 JSON 用同一 record（同一条 trajectory）
        jp = self.dir / "x.json"
        pp = self.dir / "x.png"
        save_json(jp, self.rec)
        draw_trajectory_png(pp, self.rec)
        loaded = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual([(e["x"], e["y"], e["dt_ms"]) for e in loaded["trajectory"]],
                         [tuple(p) for p in self.traj])

    def test_stats_fields_unchanged_by_new_layout(self):
        # 布局改动不碰统计：build_record 的统计键与旧版一致
        for key in ("point_count", "total_dt_ms", "straight_distance_px",
                    "actual_path_length_px", "max_dx_px", "max_lateral_offset_px",
                    "min_x", "max_x", "min_y", "max_y", "min_dt_ms", "max_dt_ms",
                    "avg_speed_px_per_ms", "max_speed_px_per_ms"):
            self.assertIn(key, self.rec)
        self.assertEqual(self.rec["straight_distance_px"], 440.0)


class ScreenViewGeometryTest(unittest.TestCase):
    """A1 Screen View / A2 Zoomed View 的坐标变换纯函数（§3 / §5 / §9）。"""

    def test_screen_constants(self):
        self.assertEqual((SCREEN_WIDTH, SCREEN_HEIGHT), (1280, 720))

    def test_fit_screen_rect_keeps_16_9_and_centers(self):
        fr = fit_screen_rect((0, 0, 1600, 900))
        self.assertAlmostEqual((fr[2] - fr[0]) / (fr[3] - fr[1]), 1280 / 720, places=6)
        self.assertEqual(fr, (0.0, 0.0, 1600.0, 900.0))
        # 宽受限：高度方向留白且居中
        fr = fit_screen_rect((0, 0, 1000, 900))
        self.assertAlmostEqual((fr[2] - fr[0]) / (fr[3] - fr[1]), 1280 / 720, places=6)
        self.assertAlmostEqual(fr[0], 0.0)
        self.assertAlmostEqual(fr[2], 1000.0)
        self.assertAlmostEqual(fr[1] + fr[3], 900.0)          # 上下留白对称

    def test_screen_to_panel_uses_fixed_domain_not_trajectory_span(self):
        fr = fit_screen_rect((64, 56, 688, 528))
        # 定义域固定为 [0,1280]x[0,720]
        self.assertEqual(screen_to_panel(0, 0, fr), (int(round(fr[0])), int(round(fr[1]))))
        self.assertEqual(screen_to_panel(SCREEN_WIDTH, SCREEN_HEIGHT, fr),
                         (int(round(fr[2])), int(round(fr[3]))))
        # 中心 -> fit 矩形中心
        cx, cy = screen_to_panel(640, 360, fr)
        self.assertAlmostEqual(cx, (fr[0] + fr[2]) / 2, delta=1)
        self.assertAlmostEqual(cy, (fr[1] + fr[3]) / 2, delta=1)

    def test_screen_to_panel_is_1_to_1_aspect(self):
        fr = fit_screen_rect((64, 56, 688, 528))
        x_scale = (fr[2] - fr[0]) / SCREEN_WIDTH
        y_scale = (fr[3] - fr[1]) / SCREEN_HEIGHT
        self.assertAlmostEqual(x_scale, y_scale, places=9)     # 1px X 与 1px Y 同比例

    def test_screen_to_panel_ignores_which_trajectory(self):
        fr = fit_screen_rect((64, 56, 688, 528))
        # 不管这次轨迹 x_span 是 2 还是 200，同一屏幕点映射结果都一样（不自适应）
        p1 = screen_to_panel(520, 400, fr)
        p2 = screen_to_panel(520, 400, fr)
        self.assertEqual(p1, p2)
        # Y 向下：y 越大越靠下
        self.assertLess(screen_to_panel(520, 100, fr)[1], screen_to_panel(520, 700, fr)[1])

    def test_trajectory_bbox_from_dicts_and_tuples(self):
        dicts = [{"x": 520, "y": 560}, {"x": 504, "y": 430}, {"x": 522, "y": 300}]
        tuples = [(520, 560, 0), (504, 430, 9), (522, 300, 9)]
        self.assertEqual(trajectory_bbox(dicts), (504, 300, 522, 560))
        self.assertEqual(trajectory_bbox(tuples), (504, 300, 522, 560))

    def test_zoom_transform_fits_bbox_into_panel(self):
        traj = TouchSwipeModel(rng=ForcedCurveRng("left")).generate((520, 560), (520, 300))
        panel = (100, 100, 500, 400)
        tf, bbox = zoom_transform(traj, panel)
        self.assertEqual(bbox, trajectory_bbox(traj))
        # bbox 四角映射后都落在 panel 内（含 margin 收缩后仍在内）
        for x in (bbox[0], bbox[2]):
            for y in (bbox[1], bbox[3]):
                px, py = tf(x, y)
                self.assertGreaterEqual(px, panel[0])
                self.assertLessEqual(px, panel[2])
                self.assertGreaterEqual(py, panel[1])
                self.assertLessEqual(py, panel[3])
        # 起点在下、终点在上（screen Y down）
        self.assertGreater(tf(*traj[0][:2])[1], tf(*traj[-1][:2])[1])

    def test_zoom_transform_is_bbox_adaptive_not_screen_scale(self):
        # 小 x_span 的轨迹在 zoom view 里仍会横向铺开（自适应），与 screen_to_panel 不同
        traj = TouchSwipeModel(rng=ForcedCurveRng("right")).generate((520, 560), (520, 300))
        panel = (0, 0, 400, 400)
        tf, bbox = zoom_transform(traj, panel)
        xs = [tf(x, y)[0] for x, y, _ in traj]
        # 16px 的真实横向跨度在 400px 宽 panel 里被放大到几十 px 以上
        self.assertGreater(max(xs) - min(xs), 40)


class ForcedCurveRngTest(unittest.TestCase):
    def test_left_pins_first_call_to_low(self):
        rng = ForcedCurveRng("left")
        self.assertEqual(rng.randint(-16, 16), -16)

    def test_right_pins_first_call_to_high(self):
        rng = ForcedCurveRng("right")
        self.assertEqual(rng.randint(-16, 16), 16)

    def test_straight_pins_first_call_to_zero(self):
        rng = ForcedCurveRng("straight")
        self.assertEqual(rng.randint(-16, 16), 0)

    def test_subsequent_calls_delegate_and_stay_in_range(self):
        rng = ForcedCurveRng("left")
        rng.randint(-16, 16)                      # 吃掉第一次
        for _ in range(20):
            v = rng.randint(-3, 3)
            self.assertTrue(-3 <= v <= 3)

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            ForcedCurveRng("wiggle")

    def test_model_with_left_bulges_left_and_hits_exact_end(self):
        traj = TouchSwipeModel(rng=ForcedCurveRng("left")).generate((520, 560), (520, 300))
        self.assertEqual(traj[0][:2], (520, 560))
        self.assertEqual(traj[-1][:2], (520, 300))
        self.assertLess(min(x for x, _, _ in traj), 520 - 3)

    def test_model_with_right_bulges_right(self):
        traj = TouchSwipeModel(rng=ForcedCurveRng("right")).generate((520, 560), (520, 300))
        self.assertGreater(max(x for x, _, _ in traj), 520 + 3)
        self.assertEqual(traj[-1][:2], (520, 300))


class ModuleSafetyTest(unittest.TestCase):
    def test_import_does_not_construct_device(self):
        # 导入模块本身不能拉起设备 / 模拟器：Device 只在 init_device() 内惰性 import
        import dev_tools.test_touch_swipe_mumu as tool
        src = Path(tool.__file__).read_text(encoding="utf-8")
        self.assertNotIn("\nfrom module.device.device import Device", src.split("def init_device")[0])
        self.assertIn("TOUCH_SWIPE_LEVEL_C", src)


if __name__ == "__main__":
    unittest.main()
