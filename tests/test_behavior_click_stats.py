"""BehaviorTrace 点击坐标记录 + 点击统计 Reader 测试。

- `Control.click` / `Control.long_click` 正常返回后，ACTION 事件的 `extra` 带真实最终坐标 x / y。
- 底层动作抛异常时不生成 ACTION（保持 BehaviorTrace v1 契约）。
- `module.server.behavior_stats.read_behavior_clicks` 按需逐行读取当天 JSONL，
  只返回 click / long_click 坐标点，兼容旧格式 / 坏行 / 缺文件，防路径穿越。
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

from module import behavior_trace
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.device.control import Control
from module.server import behavior_stats
from module.server.behavior_stats import BehaviorStatsError, read_behavior_clicks
from module.server.config_manager import ConfigManager, ConfigNameError
from module.server.stats_router import _parse_target_date


class ControlClickCoordTraceTest(unittest.TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._orig_dir = behavior_trace._LOG_DIR
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmpdir.name) / "behavior"
        behavior_trace._LOG_DIR = self.log_dir

    def tearDown(self):
        reset_behavior_traces()
        behavior_trace._LOG_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def _make_control(self, config_name="clicktest", click_method=None, long_click_method=None):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(
            config_name=config_name,
            script=SimpleNamespace(device=SimpleNamespace(control_method="minitouch")),
        )
        c.click_methods = {"minitouch": click_method or Mock(name="click_minitouch")}
        c.long_click_methods = {"minitouch": long_click_method or Mock(name="long_click_minitouch")}
        return c

    def _lines(self, config_name):
        files = list(self.log_dir.glob(f"{config_name}_*.jsonl"))
        if not files:
            return []
        return [json.loads(ln) for ln in files[0].read_text(encoding="utf-8").splitlines() if ln]

    def test_click_records_final_coordinates(self):
        method = Mock(name="click_minitouch")
        c = self._make_control(click_method=method)
        configure_behavior_trace("clicktest", enabled=True)

        c.click(842, 512, control_name="I_FIRE")

        # 记录的坐标必须与真正传给后端的一致
        self.assertEqual(method.call_args.args, (842, 512))
        rows = self._lines("clicktest")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event"], "ACTION")
        self.assertEqual(row["action"], "click")
        self.assertEqual(row["target"], "I_FIRE")
        self.assertEqual(row["result"], "ok")
        self.assertIn("elapsed_ms", row)
        self.assertEqual(row["extra"], {"x": 842, "y": 512})

    def test_long_click_records_final_coordinates(self):
        method = Mock(name="long_click_minitouch")
        c = self._make_control(long_click_method=method)
        configure_behavior_trace("clicktest", enabled=True)

        c.long_click(920, 608, control_name="I_PREPARE")

        self.assertEqual(method.call_args.args[:2], (920, 608))
        rows = self._lines("clicktest")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["action"], "long_click")
        self.assertEqual(row["target"], "I_PREPARE")
        self.assertEqual(row["result"], "ok")
        self.assertEqual(row["extra"], {"x": 920, "y": 608})

    def test_coordinates_are_ints_even_if_caller_passes_float(self):
        method = Mock()
        c = self._make_control(click_method=method)
        configure_behavior_trace("clicktest", enabled=True)

        c.click(100.7, 200.2, control_name="X")

        row = self._lines("clicktest")[0]
        self.assertEqual(row["extra"], {"x": 100, "y": 200})
        self.assertIsInstance(row["extra"]["x"], int)

    def test_backend_exception_writes_no_action(self):
        method = Mock(side_effect=RuntimeError("device gone"))
        c = self._make_control(click_method=method)
        configure_behavior_trace("clicktest", enabled=True)

        with self.assertRaises(RuntimeError):
            c.click(10, 20, control_name="I_FIRE")

        self.assertEqual(self._lines("clicktest"), [])

    def test_disabled_trace_writes_nothing(self):
        c = self._make_control()
        configure_behavior_trace("clicktest", enabled=False)
        c.click(1, 2, control_name="X")
        self.assertFalse(self.log_dir.exists())


class ReadBehaviorClicksTest(unittest.TestCase):
    def setUp(self):
        self._orig_root = behavior_stats.BEHAVIOR_LOG_ROOT
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name).resolve()
        behavior_stats.BEHAVIOR_LOG_ROOT = self.root
        self.day = date(2026, 9, 1)

    def tearDown(self):
        behavior_stats.BEHAVIOR_LOG_ROOT = self._orig_root
        self._tmpdir.cleanup()

    def _write(self, config, lines, day=None):
        day = day or self.day
        path = self.root / f"{config}_{day.isoformat()}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _action(action="click", task="RealmRaid", target="I_FIRE", x=100, y=200, ts="2026-09-01T14:20:11.421+08:00", elapsed_ms=112):
        obj = {
            "ts": ts, "config": "oas1", "task": task, "event": "ACTION",
            "action": action, "target": target, "result": "ok",
        }
        if elapsed_ms is not None:
            obj["elapsed_ms"] = elapsed_ms
        if x is not None and y is not None:
            obj["extra"] = {"x": x, "y": y}
        return json.dumps(obj, ensure_ascii=False)

    # 1. 正常文件：混有 TASK / swipe，只回 click / long_click
    def test_only_click_and_long_click_returned(self):
        self._write("oas1", [
            json.dumps({"event": "TASK", "action": "run", "target": "RealmRaid", "result": "ok"}),
            self._action(action="click", x=10, y=20),
            self._action(action="swipe", x=1, y=2),  # 非点击动作
            self._action(action="long_click", target="I_PREPARE", x=30, y=40),
        ])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual([(p["x"], p["y"], p["action"]) for p in result["points"]],
                         [(10, 20, "click"), (30, 40, "long_click")])
        self.assertEqual(result["summary"]["click_count"], 1)
        self.assertEqual(result["summary"]["long_click_count"], 1)
        self.assertEqual(result["summary"]["total"], 2)

    # 2. 旧格式 click 无 x/y -> 跳过
    def test_legacy_action_without_coords_is_skipped(self):
        self._write("oas1", [
            self._action(action="click", x=None, y=None),          # 无 extra
            json.dumps({"event": "ACTION", "action": "click", "task": "T", "extra": {}}),  # extra 空
            json.dumps({"event": "ACTION", "action": "click", "task": "T", "extra": {"x": 5}}),  # 缺 y
            self._action(action="click", x=7, y=8),
        ])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(len(result["points"]), 1)
        self.assertEqual((result["points"][0]["x"], result["points"][0]["y"]), (7, 8))

    # 3. 多任务：tasks 按首次出现顺序，point 保留 task
    def test_multi_task_ordering(self):
        self._write("oas1", [
            self._action(task="RealmRaid", x=1, y=1),
            self._action(task="RyouToppa", x=2, y=2),
            self._action(task="RealmRaid", x=3, y=3),
            self._action(task="KekkaiActivation", x=4, y=4),
        ])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(result["tasks"], ["RealmRaid", "RyouToppa", "KekkaiActivation"])
        self.assertEqual(result["summary"]["task_count"], 3)
        self.assertEqual([p["task"] for p in result["points"]],
                         ["RealmRaid", "RyouToppa", "RealmRaid", "KekkaiActivation"])

    # 4. 空文件
    def test_empty_file_returns_empty(self):
        (self.root / f"oas1_{self.day.isoformat()}.jsonl").write_text("", encoding="utf-8")
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(result["points"], [])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["summary"]["total"], 0)

    # 5. 文件不存在
    def test_missing_file_returns_empty_not_error(self):
        result = read_behavior_clicks("oas1", date(2020, 1, 1))
        self.assertEqual(result["points"], [])
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(result["config"], "oas1")
        self.assertEqual(result["date"], "2020-01-01")

    # 6. 单行坏 JSON -> 跳过，后续行继续
    def test_broken_line_is_skipped(self):
        self._write("oas1", [
            self._action(x=1, y=1),
            "{ this is not json",
            self._action(x=2, y=2),
            '{"event": "ACTION", "action": "click"',  # 截断
            self._action(x=3, y=3),
        ])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual([(p["x"], p["y"]) for p in result["points"]], [(1, 1), (2, 2), (3, 3)])
        self.assertEqual(result["summary"]["skipped_lines"], 2)

    # 7. 缺字段 / 类型错误 -> 安全跳过
    def test_malformed_records_are_skipped(self):
        self._write("oas1", [
            json.dumps([1, 2, 3]),                                       # 不是 dict
            json.dumps({"event": "ACTION", "action": "click", "extra": "nope"}),  # extra 非 dict
            json.dumps({"event": "ACTION", "action": "click", "extra": {"x": "a", "y": "b"}}),  # 坐标非数值
            json.dumps({"event": "ACTION", "action": "click", "extra": {"x": True, "y": 1}}),  # bool 不算坐标
            json.dumps({"action": "click", "extra": {"x": 1, "y": 2}}),  # 缺 event
            self._action(x=9, y=9),
        ])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(len(result["points"]), 1)
        self.assertEqual((result["points"][0]["x"], result["points"][0]["y"]), (9, 9))
        # 只有「不是 dict」的那行计入 skipped_lines，其余是被过滤的合法 JSON
        self.assertEqual(result["summary"]["skipped_lines"], 1)

    # 8. 非法 config —— reader 层守卫 + 项目 config 校验都拒绝
    def test_illegal_config_is_rejected(self):
        # Reader 用项目统一的 ConfigManager.validate_config_name 校验：
        # 拒空 / template / `.` / 路径字符 / 控制字符；允许 `_` `-`。
        for bad in ["../secret", "a/b", "..\\..", "x\x00y", "", "  ", ".", "..", "a.b",
                    "a?b", "a*b", "a|b", 'a"b', "template"]:
            with self.assertRaises(BehaviorStatsError):
                read_behavior_clicks(bad, self.day)
        for bad in ["../secret", "a/b", "..\\..", "x\x00y", "a.b", "a?b"]:
            with self.assertRaises(ConfigNameError):
                ConfigManager.validate_config_name(bad, allow_template=False)

    # 9. 非法 date（router 层的 _parse_target_date）
    def test_illegal_date_is_rejected(self):
        for bad in ["2026-13-40", "not-a-date", "2026/09/01", "20260901", ""]:
            with self.assertRaises(HTTPException) as ctx:
                _parse_target_date(bad)
            self.assertEqual(ctx.exception.status_code, 422)

    # 10. 路径穿越无法读取 behavior 目录之外的文件
    def test_path_traversal_blocked(self):
        outside = self.root.parent / "oas1_evil.jsonl"
        outside.write_text(self._action(x=1, y=1) + "\n", encoding="utf-8")
        for evil in ["../oas1", "../../oas1", "..", "a/../../oas1", "/etc/passwd", "..%2f..%2foas1"]:
            with self.assertRaises(BehaviorStatsError):
                read_behavior_clicks(evil, self.day)
        # 合法名不受影响
        self.assertEqual(read_behavior_clicks("oas1", self.day)["points"], [])

    # 11. point 顺序与 JSONL 有效事件顺序一致
    def test_point_order_matches_file_order(self):
        self._write("oas1", [self._action(x=i, y=i) for i in range(20)])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual([p["x"] for p in result["points"]], list(range(20)))

    # 12. summary 正确
    def test_summary_counts(self):
        self._write("oas1", [
            self._action(action="click", task="A", x=1, y=1),
            self._action(action="click", task="A", x=2, y=2),
            self._action(action="long_click", task="B", x=3, y=3),
            self._action(action="click", task="C", x=4, y=4),
            json.dumps({"event": "TASK", "action": "run"}),
        ])
        s = read_behavior_clicks("oas1", self.day)["summary"]
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["click_count"], 3)
        self.assertEqual(s["long_click_count"], 1)
        self.assertEqual(s["task_count"], 3)
        self.assertEqual(s["skipped_lines"], 0)

    # response 顶层结构（additive：旧键保留、新增 swipes / filter / available_* / 新 summary 计数）
    def test_response_shape(self):
        self._write("oas1", [self._action(x=1, y=2)])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(set(result), {
            "config", "date", "screen", "filter", "summary",
            "tasks", "available_tasks", "available_targets", "points", "swipes",
        })
        self.assertEqual(result["screen"], {"width": 1280, "height": 720})
        self.assertEqual(result["config"], "oas1")
        self.assertEqual(result["swipes"], [])
        self.assertEqual(result["filter"],
                         {"task": "", "interaction_type": "all", "target": ""})
        # 旧 summary 键语义不变，新增键并存
        s = result["summary"]
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["click_count"], 1)
        self.assertEqual(s["long_click_count"], 0)
        self.assertEqual(s["task_count"], 1)
        self.assertEqual(s["skipped_lines"], 0)
        self.assertEqual(s["swipe_count"], 0)
        self.assertEqual(s["filtered_count"], 1)
        self.assertEqual(s["malformed_trajectories"], 0)
        p = result["points"][0]
        self.assertEqual(set(p), {"x", "y", "task", "action", "target", "ts", "elapsed_ms"})
        self.assertNotIn("event", p)
        self.assertNotIn("result", p)
        self.assertNotIn("config", p)

    # config_name 含下划线：{script_name} 是完整 config_name，不做 "_" 截断
    def test_underscore_config_name_reads_own_file(self):
        for name in ["account_group_1", "test_01", "my_oas", "oas_1"]:
            with self.subTest(name=name):
                self._write(name, [self._action(x=7, y=8, task="T")])
                result = read_behavior_clicks(name, self.day)
                self.assertEqual(result["config"], name)
                self.assertEqual(len(result["points"]), 1)
                self.assertEqual((result["points"][0]["x"], result["points"][0]["y"]), (7, 8))

    # 不能被截断后误读到别的 config 的文件
    def test_underscore_config_does_not_misread_truncated_file(self):
        self._write("account", [self._action(x=1, y=1, task="WRONG")])
        self._write("account_group_1", [self._action(x=2, y=2, task="RIGHT")])
        result = read_behavior_clicks("account_group_1", self.day)
        self.assertEqual(result["config"], "account_group_1")
        self.assertEqual([p["task"] for p in result["points"]], ["RIGHT"])
        self.assertEqual((result["points"][0]["x"], result["points"][0]["y"]), (2, 2))

    # 前面截断段本身作为 config 时读自己的文件，互不串
    def test_prefix_segment_config_reads_its_own_file(self):
        self._write("account", [self._action(x=1, y=1, task="A")])
        self._write("account_group_1", [self._action(x=2, y=2, task="B")])
        self.assertEqual(
            [p["task"] for p in read_behavior_clicks("account", self.day)["points"]], ["A"])

    # 普通 config 不受影响
    def test_plain_config_unaffected(self):
        self._write("oas1", [self._action(x=5, y=6)])
        self._write("oas2", [self._action(x=9, y=9)])
        self.assertEqual(len(read_behavior_clicks("oas1", self.day)["points"]), 1)
        self.assertEqual(read_behavior_clicks("oas1", self.day)["points"][0]["x"], 5)
        self.assertEqual(read_behavior_clicks("oas2", self.day)["points"][0]["x"], 9)

    # ConfigManager 契约：带下划线的合法 config 通过校验
    def test_configmanager_accepts_underscore_names(self):
        for name in ["test_01", "account_group_1", "my_oas", "oas_1"]:
            self.assertEqual(
                ConfigManager.validate_config_name(name, allow_template=False), name)

    def test_elapsed_ms_is_int(self):
        self._write("oas1", [self._action(x=1, y=2, elapsed_ms=112.9)])
        result = read_behavior_clicks("oas1", self.day)
        self.assertEqual(result["points"][0]["elapsed_ms"], 113)
        self.assertIsInstance(result["points"][0]["elapsed_ms"], int)


class _SwipeFixtureMixin:
    """swipe / click JSONL 行构造器（reader 测试共用）。"""

    @staticmethod
    def _click(action="click", task="A", target="X", x=10, y=20, ts="2026-09-01T10:00:00.000+08:00"):
        return json.dumps({
            "ts": ts, "config": "oas1", "task": task, "event": "ACTION",
            "action": action, "target": target, "result": "ok",
            "elapsed_ms": 12, "extra": {"x": x, "y": y},
        }, ensure_ascii=False)

    @staticmethod
    def _swipe(task="A", target="KEKKAI_UTILIZE_SWIPE", trajectory=((400, 540, 0), (400, 320, 9)),
               start=None, end=None, point_count=None, ts="2026-09-01T10:00:01.000+08:00",
               elapsed_ms=210, extra_override=None):
        traj = None if trajectory is None else [list(p) for p in trajectory]
        extra = {}
        if traj is not None:
            extra["trajectory"] = traj
            first, last = traj[0], traj[-1]
            extra["start_x"], extra["start_y"] = (start or first[:2])
            extra["end_x"], extra["end_y"] = (end or last[:2])
            extra["point_count"] = point_count if point_count is not None else len(traj)
        if start is not None and "start_x" not in extra:
            extra["start_x"], extra["start_y"] = start
        if end is not None and "end_x" not in extra:
            extra["end_x"], extra["end_y"] = end
        if extra_override is not None:
            extra = extra_override
        obj = {
            "ts": ts, "config": "oas1", "task": task, "event": "ACTION",
            "action": "swipe", "target": target, "result": "ok",
        }
        if elapsed_ms is not None:
            obj["elapsed_ms"] = elapsed_ms
        if extra:
            obj["extra"] = extra
        return json.dumps(obj, ensure_ascii=False)


class ReadBehaviorSwipesTest(_SwipeFixtureMixin, unittest.TestCase):
    """reader 解析 swipe 轨迹条目 + 向后兼容旧 JSONL（section 三十五）。"""

    def setUp(self):
        self._orig_root = behavior_stats.BEHAVIOR_LOG_ROOT
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name).resolve()
        behavior_stats.BEHAVIOR_LOG_ROOT = self.root
        self.day = date(2026, 9, 1)

    def tearDown(self):
        behavior_stats.BEHAVIOR_LOG_ROOT = self._orig_root
        self._tmpdir.cleanup()

    def _write(self, config, lines):
        (self.root / f"{config}_{self.day.isoformat()}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    # 1/2. 新 swipe 记录：正确 parse，trajectory 的 x/y/dt 完整
    def test_swipe_record_parsed_with_full_trajectory(self):
        self._write("oas1", [self._swipe(
            task="KekkaiUtilize", target="KEKKAI_UTILIZE_SWIPE",
            trajectory=[(400, 540, 0), (400, 430, 9), (400, 320, 12)])])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(len(r["swipes"]), 1)
        sw = r["swipes"][0]
        self.assertEqual(sw["action"], "swipe")
        self.assertEqual(sw["task"], "KekkaiUtilize")
        self.assertEqual(sw["target"], "KEKKAI_UTILIZE_SWIPE")
        self.assertEqual(sw["trajectory"], [[400, 540, 0], [400, 430, 9], [400, 320, 12]])
        self.assertEqual(sw["start"], [400, 540])
        self.assertEqual(sw["end"], [400, 320])
        self.assertEqual(sw["point_count"], 3)
        self.assertEqual(sw["elapsed_ms"], 210)
        self.assertEqual(r["summary"]["swipe_count"], 1)

    # 3. 旧 swipe：无 trajectory（legacy 端点滑动或旧日志）-> 仍作为 swipe 返回，trajectory=[]
    def test_legacy_swipe_without_trajectory_still_returned(self):
        self._write("oas1", [self._swipe(trajectory=None, start=(100, 200), end=(100, 600))])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(len(r["swipes"]), 1)
        sw = r["swipes"][0]
        self.assertEqual(sw["trajectory"], [])
        self.assertEqual(sw["start"], [100, 200])
        self.assertEqual(sw["end"], [100, 600])
        self.assertEqual(sw["point_count"], 0)          # 没有轨迹点
        self.assertEqual(r["summary"]["swipe_count"], 1)
        self.assertEqual(r["summary"]["malformed_trajectories"], 0)

    def test_legacy_swipe_with_no_extra_at_all(self):
        self._write("oas1", [json.dumps(
            {"event": "ACTION", "action": "swipe", "task": "T", "target": "S", "result": "ok"})])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(len(r["swipes"]), 1)
        self.assertEqual(r["swipes"][0]["trajectory"], [])
        self.assertIsNone(r["swipes"][0]["start"])
        self.assertIsNone(r["swipes"][0]["end"])

    # 4. 旧 click-only JSONL 完全兼容
    def test_old_click_only_log_unaffected(self):
        self._write("oas1", [self._click(x=1, y=2), self._click(action="long_click", x=3, y=4)])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual([(p["x"], p["y"]) for p in r["points"]], [(1, 2), (3, 4)])
        self.assertEqual(r["swipes"], [])
        self.assertEqual(r["summary"]["swipe_count"], 0)
        self.assertEqual(r["summary"]["total"], 2)

    # 5. malformed trajectory：单条降级 / skip，不导致整个 API 失败
    def test_malformed_trajectory_degrades_single_record_only(self):
        good = self._swipe(task="A", target="S1", trajectory=[(1, 2, 0), (1, 9, 5)])
        bad_points = json.dumps({
            "event": "ACTION", "action": "swipe", "task": "A", "target": "S2",
            "extra": {"trajectory": [[1, 2, 0], "nope", [3, None, 4], [5, 6, 7]],
                      "start_x": 1, "start_y": 2, "end_x": 5, "end_y": 6, "point_count": 4},
        })
        bad_type = json.dumps({
            "event": "ACTION", "action": "swipe", "task": "A", "target": "S3",
            "extra": {"trajectory": "not-a-list", "start_x": 9, "start_y": 9,
                      "end_x": 9, "end_y": 40},
        })
        self._write("oas1", [good, bad_points, bad_type, self._click(x=7, y=7)])
        r = read_behavior_clicks("oas1", self.day)
        # 三条 swipe 都返回，坏的两条被降级计数，不抛
        self.assertEqual(len(r["swipes"]), 3)
        self.assertEqual(r["summary"]["malformed_trajectories"], 2)
        self.assertEqual(r["summary"]["skipped_lines"], 0)
        by_target = {s["target"]: s for s in r["swipes"]}
        self.assertEqual(by_target["S1"]["trajectory"], [[1, 2, 0], [1, 9, 5]])
        self.assertEqual(by_target["S2"]["trajectory"], [[1, 2, 0], [5, 6, 7]])  # 只剩可解析点
        self.assertEqual(by_target["S2"]["start"], [1, 2])                       # 端点用 extra 显式值
        self.assertEqual(by_target["S3"]["trajectory"], [])                      # 结构完全坏 -> []
        self.assertEqual(by_target["S3"]["start"], [9, 9])
        self.assertEqual(len(r["points"]), 1)                                    # click 不受影响

    # 6. 一条 swipe 60 个点 -> swipe_count 只 +1
    def test_one_swipe_with_many_points_counts_as_one(self):
        traj = [(100, 500 - i, 0 if i == 0 else 8) for i in range(60)]
        self._write("oas1", [self._swipe(task="A", target="S", trajectory=traj)])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(r["summary"]["swipe_count"], 1)
        self.assertEqual(len(r["swipes"][0]["trajectory"]), 60)
        self.assertEqual(r["swipes"][0]["point_count"], 60)
        self.assertEqual(r["summary"]["filtered_count"], 1)

    def test_broken_json_line_still_skipped_with_swipes_present(self):
        self._write("oas1", [self._swipe(task="A", target="S"), "{bad json", self._click(x=1, y=1)])
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(r["summary"]["skipped_lines"], 1)
        self.assertEqual(len(r["swipes"]), 1)
        self.assertEqual(len(r["points"]), 1)


class BehaviorStatsFilterTest(_SwipeFixtureMixin, unittest.TestCase):
    """date / task / interaction_type / target 四层等值 AND 过滤（section 三十六 + Case A~D）。"""

    def setUp(self):
        self._orig_root = behavior_stats.BEHAVIOR_LOG_ROOT
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name).resolve()
        behavior_stats.BEHAVIOR_LOG_ROOT = self.root
        self.day = date(2026, 9, 1)
        # 数据：A/click/X, A/long_click/Y, A/swipe/S1, B/swipe/S2, B/click/Z
        self._write("oas1", [
            self._click(action="click", task="A", target="X", x=1, y=1),
            self._click(action="long_click", task="A", target="Y", x=2, y=2),
            self._swipe(task="A", target="S1", trajectory=[(3, 3, 0), (3, 30, 9)]),
            self._swipe(task="B", target="S2", trajectory=[(4, 4, 0), (4, 40, 9)]),
            self._click(action="click", task="B", target="Z", x=5, y=5),
        ])

    def tearDown(self):
        behavior_stats.BEHAVIOR_LOG_ROOT = self._orig_root
        self._tmpdir.cleanup()

    def _write(self, config, lines):
        (self.root / f"{config}_{self.day.isoformat()}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _targets(self, **kw):
        r = read_behavior_clicks("oas1", self.day, **kw)
        return ([p["target"] for p in r["points"]], [s["target"] for s in r["swipes"]], r)

    def test_default_all_returns_clicks_and_swipes(self):
        clicks, swipes, r = self._targets()
        self.assertEqual(clicks, ["X", "Y", "Z"])
        self.assertEqual(swipes, ["S1", "S2"])
        self.assertEqual(r["summary"]["click_count"], 2)
        self.assertEqual(r["summary"]["long_click_count"], 1)
        self.assertEqual(r["summary"]["swipe_count"], 2)
        self.assertEqual(r["summary"]["total"], 3)          # 旧语义：click 点数
        self.assertEqual(r["summary"]["filtered_count"], 5)

    def test_interaction_type_click_only(self):
        clicks, swipes, r = self._targets(interaction_type="click")
        self.assertEqual(clicks, ["X", "Y", "Z"])
        self.assertEqual(swipes, [])
        self.assertEqual(r["summary"]["swipe_count"], 0)
        self.assertEqual(r["summary"]["filtered_count"], 3)

    def test_interaction_type_swipe_only(self):
        clicks, swipes, r = self._targets(interaction_type="swipe")
        self.assertEqual(clicks, [])
        self.assertEqual(swipes, ["S1", "S2"])
        self.assertEqual(r["summary"]["total"], 0)          # 无 click 点
        self.assertEqual(r["summary"]["click_count"], 0)
        self.assertEqual(r["summary"]["swipe_count"], 2)
        self.assertEqual(r["summary"]["filtered_count"], 2)

    def test_interaction_type_is_case_insensitive(self):
        _, swipes, r = self._targets(interaction_type="SWIPE")
        self.assertEqual(swipes, ["S1", "S2"])
        self.assertEqual(r["filter"]["interaction_type"], "swipe")

    def test_invalid_interaction_type_raises_400(self):
        with self.assertRaises(BehaviorStatsError) as ctx:
            read_behavior_clicks("oas1", self.day, interaction_type="drag")
        self.assertEqual(ctx.exception.status_code, 400)

    # Case A: task=KekkaiUtilize(here A) + SWIPE -> swipes 有数据，clicks 空
    def test_case_a_task_and_swipe(self):
        clicks, swipes, r = self._targets(task="A", interaction_type="swipe")
        self.assertEqual(clicks, [])
        self.assertEqual(swipes, ["S1"])
        self.assertEqual(r["summary"]["swipe_count"], 1)

    # Case B: task=A + CLICK -> clicks 有数据，swipes 空
    def test_case_b_task_and_click(self):
        clicks, swipes, _ = self._targets(task="A", interaction_type="click")
        self.assertEqual(clicks, ["X", "Y"])
        self.assertEqual(swipes, [])

    # Case C: 全任务 + SWIPE -> 当天所有 swipe
    def test_case_c_all_tasks_swipe(self):
        clicks, swipes, _ = self._targets(interaction_type="swipe")
        self.assertEqual((clicks, swipes), ([], ["S1", "S2"]))

    # Case D: task=A + SWIPE + target=S1 -> 只该 target，1 条
    def test_case_d_task_swipe_target(self):
        clicks, swipes, r = self._targets(task="A", interaction_type="swipe", target="S1")
        self.assertEqual((clicks, swipes), ([], ["S1"]))
        self.assertEqual(r["summary"]["filtered_count"], 1)
        self.assertEqual(r["filter"], {"task": "A", "interaction_type": "swipe", "target": "S1"})

    def test_target_filter_same_semantic_for_click_and_swipe(self):
        # target=X -> 只 click X；target=S2 -> 只 swipe S2；同一个 target 参数
        c1, s1, _ = self._targets(target="X")
        self.assertEqual((c1, s1), (["X"], []))
        c2, s2, _ = self._targets(target="S2")
        self.assertEqual((c2, s2), ([], ["S2"]))

    def test_task_b_click_only_target_z(self):
        c, s, _ = self._targets(task="B", interaction_type="click")
        self.assertEqual((c, s), (["Z"], []))

    def test_available_tasks_excludes_task_dimension(self):
        # 选定 task=A 后，available_tasks 仍反映当前 type/target 下的所有任务
        r = read_behavior_clicks("oas1", self.day, task="A")
        self.assertEqual(r["available_tasks"], ["A", "B"])
        # type=swipe 时 available_tasks 只含有 swipe 的任务
        r2 = read_behavior_clicks("oas1", self.day, interaction_type="swipe")
        self.assertEqual(r2["available_tasks"], ["A", "B"])

    def test_available_targets_excludes_target_dimension(self):
        r = read_behavior_clicks("oas1", self.day, task="A", interaction_type="swipe", target="S1")
        # target 维不参与 available_targets：task=A + swipe 下只有 S1
        self.assertEqual(r["available_targets"], ["S1"])
        r2 = read_behavior_clicks("oas1", self.day, task="A")
        self.assertEqual(r2["available_targets"], ["X", "Y", "S1"])

    def test_tasks_legacy_field_is_click_derived(self):
        # 旧 `tasks` 字段：命中过滤的 click 点里的任务，首次出现顺序
        r = read_behavior_clicks("oas1", self.day)
        self.assertEqual(r["tasks"], ["A", "B"])
        r2 = read_behavior_clicks("oas1", self.day, interaction_type="swipe")
        self.assertEqual(r2["tasks"], [])          # 无 click 点


if __name__ == "__main__":
    unittest.main()
