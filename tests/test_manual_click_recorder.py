"""`dev_tools/manual_click_recorder.py` 的纯函数单元测试。

不安装真实 Windows 钩子；只覆盖坐标转换、窗口移动 / resize 不变量、视口外过滤、
ROI u/v、config 名安全、JSONL 追加 / 跨天轮转、日统计、injected 过滤、非法几何。
"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from statistics import mean, pstdev

from dev_tools import manual_click_recorder as mcr


class ScreenToLogicalTest(unittest.TestCase):
    def test_basic_1to1_viewport(self):
        # 视口原点 (1000,200)，1280x720，鼠标 (1640,560) -> client (640,360) -> logical (640,360)
        cx, cy, lx, ly, inside = mcr.screen_to_logical(1640, 560, (1000, 200, 2280, 920))
        self.assertEqual((cx, cy), (640, 360))
        self.assertEqual((round(lx), round(ly)), (640, 360))
        self.assertTrue(inside)

    def test_scaled_viewport_keeps_ratio(self):
        # 视口被缩小到 640x360，点在正中 -> logical 仍是 (640,360)
        _, _, lx, ly, inside = mcr.screen_to_logical(320 + 100, 180 + 100, (100, 100, 740, 460))
        self.assertAlmostEqual(lx, 640.0)
        self.assertAlmostEqual(ly, 360.0)
        self.assertTrue(inside)

    def test_window_move_same_client_point_same_logical(self):
        # 同一个 client 偏移 (300,150)，窗口原点从 (0,0) 移到 (1573,88) -> logical 不变
        r1 = mcr.screen_to_logical(0 + 300, 0 + 150, (0, 0, 1280, 720))
        r2 = mcr.screen_to_logical(1573 + 300, 88 + 150, (1573, 88, 1573 + 1280, 88 + 720))
        self.assertEqual(r1[2:4], r2[2:4])
        self.assertTrue(r1[4] and r2[4])

    def test_resize_keeps_relative_ratio(self):
        # 不同分辨率的视口，点都在 25% / 75% 处 -> logical 比例一致
        _, _, lx_a, ly_a, _ = mcr.screen_to_logical(0 + 250, 0 + 540, (0, 0, 1000, 720))
        _, _, lx_b, ly_b, _ = mcr.screen_to_logical(0 + 500, 0 + 1080, (0, 0, 2000, 1440))
        self.assertAlmostEqual(lx_a, lx_b)
        self.assertAlmostEqual(ly_a, ly_b)
        self.assertAlmostEqual(lx_a, 0.25 * 1280)
        self.assertAlmostEqual(ly_a, 0.75 * 720)

    def test_point_outside_viewport_is_flagged_not_clamped(self):
        # 标题栏 / 边框：client 为负或超界 -> inside=False，坐标照实（可为负 / 超 1280）
        cx, cy, lx, ly, inside = mcr.screen_to_logical(1000 - 5, 200 - 30, (1000, 200, 2280, 920))
        self.assertFalse(inside)
        self.assertEqual((cx, cy), (-5, -30))
        self.assertLess(lx, 0)
        self.assertLess(ly, 0)

        _, _, lx2, ly2, inside2 = mcr.screen_to_logical(2280 + 50, 920 + 50, (1000, 200, 2280, 920))
        self.assertFalse(inside2)
        self.assertGreater(lx2, 1280)
        self.assertGreater(ly2, 720)

    def test_invalid_geometry_raises(self):
        with self.assertRaises(ValueError):
            mcr.screen_to_logical(10, 10, (100, 100, 100, 200))  # 宽 0
        with self.assertRaises(ValueError):
            mcr.screen_to_logical(10, 10, (100, 100, 90, 200))  # 宽 负


class RelativeUvTest(unittest.TestCase):
    def test_center_of_roi(self):
        u, v, inside = mcr.relative_uv(790 + 65, 470 + 45, (790, 470, 130, 90))
        self.assertAlmostEqual(u, 0.5)
        self.assertAlmostEqual(v, 0.5)
        self.assertTrue(inside)

    def test_known_fraction(self):
        u, v, inside = mcr.relative_uv(862, 521, (790, 470, 130, 90))
        self.assertAlmostEqual(u, (862 - 790) / 130, places=6)
        self.assertAlmostEqual(v, (521 - 470) / 90, places=6)
        self.assertTrue(inside)

    def test_outside_roi_not_clamped(self):
        u, v, inside = mcr.relative_uv(700, 400, (790, 470, 130, 90))
        self.assertFalse(inside)
        self.assertLess(u, 0.0)
        self.assertLess(v, 0.0)
        u2, v2, inside2 = mcr.relative_uv(1000, 600, (790, 470, 130, 90))
        self.assertFalse(inside2)
        self.assertGreater(u2, 1.0)
        self.assertGreater(v2, 1.0)


class ParseRoiTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(mcr.parse_roi("790,470,130,90"), (790, 470, 130, 90))
        self.assertEqual(mcr.parse_roi(" 0 , 0 , 1280 , 720 "), (0, 0, 1280, 720))

    def test_rejects_bad(self):
        for bad in ["790,470,130", "a,b,c,d", "790,470,0,90", "790,470,130,-5",
                    "-1,0,10,10", "1200,0,200,10", "0,700,10,50", "1,2,3,4,5"]:
            with self.assertRaises(ValueError, msg=bad):
                mcr.parse_roi(bad)


class IsInjectedTest(unittest.TestCase):
    def test_flag_bit(self):
        self.assertFalse(mcr.is_injected_event(0))
        self.assertTrue(mcr.is_injected_event(mcr.LLMHF_INJECTED))
        self.assertTrue(mcr.is_injected_event(mcr.LLMHF_INJECTED | mcr.LLMHF_LOWER_IL_INJECTED))
        self.assertFalse(mcr.is_injected_event(mcr.LLMHF_LOWER_IL_INJECTED))  # 只有 lower-IL 位不算


class MatchTitleTest(unittest.TestCase):
    def test_matches_mumu_titles(self):
        for t in ["MuMu模拟器12", "MuMu安卓设备", "MuMuPlayer", "NemuPlayer"]:
            self.assertTrue(mcr.match_mumu_toplevel_title(t), t)

    def test_rejects_non_mumu(self):
        for t in ["", "Visual Studio Code", "雷电模拟器", "Nox", None]:
            self.assertFalse(mcr.match_mumu_toplevel_title(t or ""), repr(t))


class ViewportSanityTest(unittest.TestCase):
    def test_accepts_1280x720_no_scale(self):
        ok, _ = mcr.viewport_sanity((0, 0, 1280, 720), 1.0)
        self.assertTrue(ok)

    def test_accepts_1024x576_at_125_scale(self):
        ok, _ = mcr.viewport_sanity((100, 100, 100 + 1024, 100 + 576), 1.25)
        self.assertTrue(ok)

    def test_rejects_wrong_window(self):
        ok, why = mcr.viewport_sanity((0, 0, 900, 500), 1.0)
        self.assertFalse(ok)
        self.assertIn("--hwnd", why)

    def test_rejects_degenerate(self):
        ok, _ = mcr.viewport_sanity((0, 0, 0, 0), 1.0)
        self.assertFalse(ok)


class BuildSampleTest(unittest.TestCase):
    def _now(self):
        return datetime(2026, 9, 1, 12, 30, 15)

    def test_schema_and_logical_coord(self):
        s = mcr.build_sample(
            now=self._now, config_name="oas1",
            screen_x=1000 + 640, screen_y=200 + 360, win_rect=(1000, 200, 2280, 920),
            injected=False,
        )
        self.assertEqual(s["source"], "manual")
        self.assertEqual(s["config"], "oas1")
        self.assertEqual((s["x"], s["y"]), (640, 360))
        self.assertEqual((s["client_x"], s["client_y"]), (640, 360))
        self.assertEqual((s["window_width"], s["window_height"]), (1280, 720))
        self.assertEqual((s["logical_width"], s["logical_height"]), (1280, 720))
        self.assertTrue(s["inside_viewport"])
        self.assertFalse(s["injected"])
        self.assertNotIn("u", s)
        self.assertNotIn("scene", s)

    def test_roi_adds_uv_and_inside(self):
        s = mcr.build_sample(
            now=self._now, config_name="oas1",
            screen_x=790 + 65, screen_y=470 + 45, win_rect=(0, 0, 1280, 720),
            injected=False, roi=(790, 470, 130, 90), scene="RealmRaid", target="I_FIRE",
        )
        self.assertEqual(s["roi"], [790, 470, 130, 90])
        self.assertAlmostEqual(s["u"], 0.5, places=3)
        self.assertAlmostEqual(s["v"], 0.5, places=3)
        self.assertTrue(s["inside_roi"])
        self.assertEqual(s["scene"], "RealmRaid")
        self.assertEqual(s["target"], "I_FIRE")

    def test_roi_outside_not_clamped(self):
        s = mcr.build_sample(
            now=self._now, config_name="oas1",
            screen_x=10, screen_y=10, win_rect=(0, 0, 1280, 720),
            injected=False, roi=(790, 470, 130, 90),
        )
        self.assertFalse(s["inside_roi"])
        self.assertLess(s["u"], 0.0)

    def test_json_serialisable(self):
        s = mcr.build_sample(
            now=self._now, config_name="oas1", screen_x=100, screen_y=100,
            win_rect=(0, 0, 1280, 720), injected=False, roi=(0, 0, 100, 100),
        )
        json.loads(json.dumps(s))  # 不抛即可


class ManualClickStatsTest(unittest.TestCase):
    def test_counts_without_roi(self):
        st = mcr.ManualClickStats()
        for _ in range(5):
            st.add(None, None, None)
        self.assertEqual(st.total, 5)
        self.assertEqual(st.roi_inside, 0)
        self.assertFalse(st.has_uv)
        self.assertIsNone(st.mean_u)

    def test_mean_and_pstdev_match_statistics(self):
        us = [0.50, 0.55, 0.60, 0.48, 0.52, 0.57]
        vs = [0.50, 0.62, 0.44, 0.51, 0.58, 0.49]
        st = mcr.ManualClickStats()
        for u, v in zip(us, vs):
            st.add(u, v, True)
        st.add(9.9, 9.9, False)  # ROI 外样本不进 u/v 统计
        self.assertEqual(st.total, 7)
        self.assertEqual(st.roi_inside, 6)
        self.assertEqual(st.roi_outside, 1)
        self.assertAlmostEqual(st.mean_u, mean(us), places=9)
        self.assertAlmostEqual(st.mean_v, mean(vs), places=9)
        self.assertAlmostEqual(st.std_u, pstdev(us), places=9)
        self.assertAlmostEqual(st.std_v, pstdev(vs), places=9)


class ManualClickWriterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_append_multiple_valid_jsonl(self):
        w = mcr.ManualClickWriter("oas1", root=self.root, now=lambda: datetime(2026, 9, 1, 10))
        for i in range(3):
            w.write({"i": i, "source": "manual"})
        w.close()
        path = self.root / "oas1_2026-09-01.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(x)["i"] for x in lines], [0, 1, 2])

    def test_reopen_appends_not_truncates(self):
        for _ in range(2):
            w = mcr.ManualClickWriter("oas1", root=self.root, now=lambda: datetime(2026, 9, 1, 10))
            w.write({"source": "manual"})
            w.close()
        path = self.root / "oas1_2026-09-01.jsonl"
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_daily_rotation(self):
        clock = {"d": datetime(2026, 9, 1, 23, 59)}
        w = mcr.ManualClickWriter("oas1", root=self.root, now=lambda: clock["d"])
        w.write({"day": 1})
        clock["d"] = datetime(2026, 9, 2, 0, 1)
        w.write({"day": 2})
        w.close()
        self.assertEqual(len((self.root / "oas1_2026-09-01.jsonl").read_text("utf-8").splitlines()), 1)
        self.assertEqual(len((self.root / "oas1_2026-09-02.jsonl").read_text("utf-8").splitlines()), 1)

    def test_underscore_config_name_kept_whole(self):
        w = mcr.ManualClickWriter("account_group_1", root=self.root, now=lambda: datetime(2026, 9, 1))
        w.write({"source": "manual"})
        w.close()
        self.assertTrue((self.root / "account_group_1_2026-09-01.jsonl").exists())

    def test_path_traversal_config_rejected_by_writer(self):
        w = mcr.ManualClickWriter("../evil", root=self.root, now=lambda: datetime(2026, 9, 1))
        with self.assertRaises(ValueError):
            w.write({"source": "manual"})


class ResolveConfigNameTest(unittest.TestCase):
    def test_valid_names_kept(self):
        self.assertEqual(mcr.resolve_config_name("oas1"), "oas1")
        self.assertEqual(mcr.resolve_config_name("account_group_1"), "account_group_1")
        self.assertEqual(mcr.resolve_config_name("  oas2 "), "oas2")

    def test_illegal_names_rejected(self):
        for bad in ["../oas1", "a/b", "a\\b", "a.b", "", "template", "a\x00b"]:
            with self.assertRaises(Exception, msg=bad):
                mcr.resolve_config_name(bad)


if __name__ == "__main__":
    unittest.main()
