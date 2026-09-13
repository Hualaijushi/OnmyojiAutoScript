"""BehaviorTrace v1 测试。

覆盖：关闭时零 IO、开启时写合法 JSONL、append 不覆盖、extra 安全序列化、
写入失败隔离与自禁用、跨天轮转、set_task 复用、以及一个非严格的吞吐冒烟。
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from module import behavior_trace
from module.behavior_trace import (
    BehaviorTrace,
    configure_behavior_trace,
    get_behavior_trace,
    reset_behavior_traces,
)


class BehaviorTraceTest(unittest.TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._orig_dir = behavior_trace._LOG_DIR
        self._orig_now = behavior_trace._now
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmpdir.name) / "behavior"
        behavior_trace._LOG_DIR = self.log_dir

    def tearDown(self):
        reset_behavior_traces()
        behavior_trace._LOG_DIR = self._orig_dir
        behavior_trace._now = self._orig_now
        self._tmpdir.cleanup()

    # -- 工具 ---------------------------------------------------------------
    def _files(self):
        return sorted(self.log_dir.glob("*.jsonl")) if self.log_dir.exists() else []

    def _lines(self, path: Path):
        return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]

    def _only_file(self) -> Path:
        files = self._files()
        self.assertEqual(len(files), 1, files)
        return files[0]

    # -- 1. 关闭时不做任何 IO --------------------------------------------------
    def test_disabled_does_no_io(self):
        trace = configure_behavior_trace("oas1", enabled=False)
        for _ in range(5):
            trace.record("ACTION", action="click", target="I_FIRE", elapsed_ms=12)
        self.assertFalse(self.log_dir.exists())
        self.assertIsNone(trace._fh)

    def test_is_recording_reflects_enabled_and_broken(self):
        trace = configure_behavior_trace("oas1", enabled=False)
        self.assertFalse(trace.is_recording())
        trace.set_enabled(True)
        self.assertTrue(trace.is_recording())
        trace._broken = True                       # 自禁用后不再落盘
        self.assertFalse(trace.is_recording())

    def test_disabled_never_touches_filesystem(self):
        trace = configure_behavior_trace("oas1", enabled=False)
        # 任何进入写入路径的迹象都让测试失败
        with patch.object(
            BehaviorTrace, "_write_line", autospec=True,
            side_effect=AssertionError("_write_line called while disabled"),
        ):
            for _ in range(1000):
                trace.record("ACTION", action="click", target="X", elapsed_ms=1)
        self.assertFalse(self.log_dir.exists())
        self.assertFalse(trace._broken)

    # -- 2. 开启时写合法 JSONL ----------------------------------------------
    def test_enabled_writes_valid_jsonl(self):
        trace = configure_behavior_trace("oas1", enabled=True)
        trace.set_task("RealmRaid")
        n = 20
        for i in range(n):
            trace.record("ACTION", action="click", target=f"I_{i}", elapsed_ms=100 + i)
        lines = self._lines(self._only_file())
        self.assertEqual(len(lines), n)
        for i, ln in enumerate(lines):
            obj = json.loads(ln)
            self.assertEqual(obj["config"], "oas1")
            self.assertEqual(obj["task"], "RealmRaid")
            self.assertEqual(obj["event"], "ACTION")
            self.assertEqual(obj["action"], "click")
            self.assertEqual(obj["target"], f"I_{i}")
            self.assertEqual(obj["result"], "ok")
            self.assertEqual(obj["elapsed_ms"], 100 + i)
            # ts 可被解析为带时区的时间
            datetime.fromisoformat(obj["ts"])

    def test_task_event_shape(self):
        trace = configure_behavior_trace("oas1", enabled=True)
        trace.record("TASK", action="run", target="RealmRaid", result="ok", elapsed_ms=190587)
        obj = json.loads(self._lines(self._only_file())[0])
        self.assertEqual(obj["event"], "TASK")
        self.assertEqual(obj["action"], "run")
        self.assertEqual(obj["target"], "RealmRaid")
        self.assertEqual(obj["result"], "ok")
        self.assertEqual(obj["elapsed_ms"], 190587)

    def test_set_task_is_used_as_default(self):
        trace = configure_behavior_trace("oas1", enabled=True)
        trace.set_task("RyouToppa")
        trace.record("ACTION", action="swipe", target="SWIPE", elapsed_ms=1340)
        obj = json.loads(self._lines(self._only_file())[0])
        self.assertEqual(obj["task"], "RyouToppa")
        # 显式传入的 task 覆盖默认
        trace.record("ACTION", action="click", target="X", task="Other")
        obj2 = json.loads(self._lines(self._only_file())[1])
        self.assertEqual(obj2["task"], "Other")

    def test_get_without_configure_is_disabled(self):
        trace = get_behavior_trace("never_configured")
        trace.record("ACTION", action="click", target="X")
        self.assertFalse(self.log_dir.exists())

    # -- 3. append 不覆盖 --------------------------------------------------
    def test_append_does_not_truncate(self):
        configure_behavior_trace("oas1", enabled=True)
        get_behavior_trace("oas1").record("ACTION", action="click", target="A")
        get_behavior_trace("oas1").record("ACTION", action="click", target="B")
        get_behavior_trace("oas1").record("ACTION", action="click", target="C")
        lines = self._lines(self._only_file())
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["target"], "A")
        self.assertEqual(json.loads(lines[2])["target"], "C")

    # -- 4. extra 安全序列化 --------------------------------------------------
    def test_extra_is_safely_serialized(self):
        trace = configure_behavior_trace("oas1", enabled=True)

        class _Weird:
            def __repr__(self):
                return "<weird>"

        trace.record(
            "ACTION",
            action="click",
            target="X",
            extra={
                "when": datetime(2026, 9, 1, 2, 30, 1),
                "exc": ValueError("boom"),
                "obj": _Weird(),
            },
        )
        obj = json.loads(self._lines(self._only_file())[0])
        self.assertIsInstance(obj["extra"]["when"], str)
        self.assertIsInstance(obj["extra"]["exc"], str)
        self.assertIn("boom", obj["extra"]["exc"])
        self.assertEqual(obj["extra"]["obj"], "<weird>")

    # -- 5. 写入失败隔离 + 自禁用 -------------------------------------------
    def test_write_failure_is_isolated_and_self_disables(self):
        trace = configure_behavior_trace("oas1", enabled=True)
        with patch.object(
            BehaviorTrace, "_open_handle", autospec=True, side_effect=OSError("disk full")
        ) as open_mock:
            # 不得抛出
            trace.record("ACTION", action="click", target="X", elapsed_ms=1)
            self.assertTrue(trace._broken)
            # 后续调用安全 return，不再尝试打开
            trace.record("ACTION", action="click", target="Y", elapsed_ms=1)
            trace.record("TASK", action="run", target="RealmRaid", result="ok")
        self.assertEqual(open_mock.call_count, 1)
        self.assertFalse(self._files())

    def test_serialization_failure_is_isolated(self):
        trace = configure_behavior_trace("oas1", enabled=True)
        with patch("module.behavior_trace.json.dumps", side_effect=TypeError("nope")):
            trace.record("ACTION", action="click", target="X")
        self.assertTrue(trace._broken)
        # 业务方视角：调用返回 None、无异常
        self.assertIsNone(trace.record("ACTION", action="click", target="X"))

    # -- 6. 跨天轮转 -----------------------------------------------------
    def test_cross_day_rotation(self):
        day1 = datetime(2026, 9, 1, 23, 59, 30)
        day2 = day1 + timedelta(hours=1)  # 2026-09-02 00:59:30
        trace = configure_behavior_trace("oas1", enabled=True)

        behavior_trace._now = lambda: day1
        trace.record("ACTION", action="click", target="A", elapsed_ms=1)
        behavior_trace._now = lambda: day2
        trace.record("ACTION", action="click", target="B", elapsed_ms=1)

        files = self._files()
        self.assertEqual(len(files), 2, files)
        by_name = {p.name: p for p in files}
        self.assertIn("oas1_2026-09-01.jsonl", by_name)
        self.assertIn("oas1_2026-09-02.jsonl", by_name)
        self.assertEqual(len(self._lines(by_name["oas1_2026-09-01.jsonl"])), 1)
        self.assertEqual(len(self._lines(by_name["oas1_2026-09-02.jsonl"])), 1)
        self.assertEqual(
            json.loads(self._lines(by_name["oas1_2026-09-01.jsonl"])[0])["target"], "A"
        )

    # -- 7. 多实例隔离 --------------------------------------------------
    def test_configs_write_separate_files(self):
        configure_behavior_trace("oas1", enabled=True)
        configure_behavior_trace("oas2", enabled=True)
        get_behavior_trace("oas1").record("ACTION", action="click", target="A")
        get_behavior_trace("oas2").record("ACTION", action="click", target="B")
        names = {p.name.split("_")[0] for p in self._files()}
        self.assertEqual(names, {"oas1", "oas2"})

    # -- 8. 吞吐冒烟（非严格）------------------------------------------------
    def test_record_throughput_smoke(self):
        trace = configure_behavior_trace("perf", enabled=True)
        n = 10000
        t0 = perf_counter()
        for _ in range(n):
            trace.record("ACTION", action="click", target="I_FIRE", elapsed_ms=112)
        dt = perf_counter() - t0
        # 仅供数量级参考，打印到测试输出
        print(
            f"\n[BehaviorTrace] enabled: {n} records in {dt * 1000:.1f} ms "
            f"({dt / n * 1e6:.2f} us/record)"
        )
        self.assertEqual(len(self._lines(self._only_file())), n)
        # 极宽松上限，只防数量级异常 / 死循环，不做机器相关的严格断言
        self.assertLess(dt, 10.0)

    def test_disabled_throughput_smoke(self):
        trace = configure_behavior_trace("perf", enabled=False)
        n = 100000
        t0 = perf_counter()
        for _ in range(n):
            trace.record("ACTION", action="click", target="I_FIRE", elapsed_ms=112)
        dt = perf_counter() - t0
        print(
            f"\n[BehaviorTrace] disabled: {n} records in {dt * 1000:.1f} ms "
            f"({dt / n * 1e6:.3f} us/record)"
        )
        self.assertFalse(self.log_dir.exists())
        self.assertLess(dt, 5.0)


if __name__ == "__main__":
    unittest.main()
