# This Python file uses the following encoding: utf-8
"""KekkaiUtilize Scheduler v1：`tasks/KekkaiUtilize/scheduling.py` 纯函数单元测试。

`is_in_quiet_window` / `next_quiet_window_end` / `normalize_for_quiet_window` 全部只吃
`datetime`/`time`/`int`/`bool`，不依赖设备 / OCR / task config object，Level A 覆盖。

覆盖 CASE A~H（正式实施报告 §13 列出的边界场景）：
- A：quiet disabled → candidate 原样返回。
- B：candidate 不落窗（14:20，窗口 00:00~07:00）→ 原样返回。
- C：candidate=00:15 落窗，jitter=20min → 07:20。
- D：candidate=06:59 落窗（边界内侧），jitter=5min → 07:05。
- E：candidate=07:00 → 不属于 quiet（`[start, end)` 半开区间）→ 原样返回。
- F：跨午夜窗口 23:00~06:00，candidate=01:00 落窗 → 06:00 + jitter（同一天）。
- G：跨午夜窗口 23:00~06:00，candidate=22:00 不落窗 → 原样返回。
- H：跨午夜窗口 23:00~06:00，candidate=23:30 落窗 → 次日 06:00 + jitter。

不给既有 `script.py::_in_sleep_window` / `tasks/Restart/server_update.py` 补测试——
本模块是独立实现，不 import 它们，按 Inventory 报告 §15 的要求不扩大范围。
"""

from datetime import datetime, time
from unittest import TestCase

from tasks.KekkaiUtilize.scheduling import (
    is_in_quiet_window,
    next_quiet_window_end,
    normalize_for_quiet_window,
)

QUIET_00_07 = (time(0, 0, 0), time(7, 0, 0))
QUIET_23_06 = (time(23, 0, 0), time(6, 0, 0))


def _dt(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 1 + (day - 1), hour, minute, second)


class IsInQuietWindowTest(TestCase):
    def test_normal_window_boundaries(self):
        start, end = QUIET_00_07
        self.assertTrue(is_in_quiet_window(time(0, 0, 0), start, end))    # 左闭
        self.assertTrue(is_in_quiet_window(time(6, 59, 59), start, end))
        self.assertFalse(is_in_quiet_window(time(7, 0, 0), start, end))   # 右开
        self.assertFalse(is_in_quiet_window(time(14, 20, 0), start, end))

    def test_cross_midnight_window(self):
        start, end = QUIET_23_06
        self.assertTrue(is_in_quiet_window(time(1, 0, 0), start, end))    # 跨午夜后半段
        self.assertTrue(is_in_quiet_window(time(23, 30, 0), start, end))  # 跨午夜前半段
        self.assertFalse(is_in_quiet_window(time(22, 0, 0), start, end))
        self.assertFalse(is_in_quiet_window(time(6, 0, 0), start, end))   # 右开边界

    def test_empty_window_when_start_equals_end(self):
        self.assertFalse(is_in_quiet_window(time(3, 0, 0), time(5, 0, 0), time(5, 0, 0)))


class NextQuietWindowEndTest(TestCase):
    def test_end_later_today_stays_same_day(self):
        now = _dt(1, 0, 15)
        self.assertEqual(next_quiet_window_end(now, time(7, 0, 0)), _dt(1, 7, 0))

    def test_end_already_passed_rolls_to_tomorrow(self):
        now = _dt(1, 23, 30)
        self.assertEqual(next_quiet_window_end(now, time(6, 0, 0)), _dt(2, 6, 0))

    def test_end_equal_to_now_rolls_to_tomorrow(self):
        now = _dt(1, 7, 0)
        self.assertEqual(next_quiet_window_end(now, time(7, 0, 0)), _dt(2, 7, 0))


class NormalizeForQuietWindowTest(TestCase):
    def _normalize(self, candidate, *, enable=True, window=QUIET_00_07, jitter_min=0):
        start, end = window
        return normalize_for_quiet_window(
            candidate,
            enable=enable,
            quiet_start=start,
            quiet_end=end,
            jitter_seconds=jitter_min * 60,
        )

    def test_case_a_quiet_disabled_returns_candidate_unchanged(self):
        candidate = _dt(1, 3, 0)
        final = self._normalize(candidate, enable=False, jitter_min=20)
        self.assertEqual(final, candidate)

    def test_case_b_candidate_outside_window_returns_unchanged(self):
        candidate = _dt(1, 14, 20)
        final = self._normalize(candidate, jitter_min=20)
        self.assertEqual(final, candidate)

    def test_case_c_candidate_inside_window_resumes_at_end_plus_jitter(self):
        candidate = _dt(1, 0, 15)
        final = self._normalize(candidate, jitter_min=20)
        self.assertEqual(final, _dt(1, 7, 20))

    def test_case_d_candidate_at_window_inner_boundary(self):
        candidate = _dt(1, 6, 59)
        final = self._normalize(candidate, jitter_min=5)
        self.assertEqual(final, _dt(1, 7, 5))

    def test_case_e_candidate_at_window_end_is_not_quiet(self):
        candidate = _dt(1, 7, 0)
        final = self._normalize(candidate, jitter_min=20)
        self.assertEqual(final, candidate)

    def test_case_f_cross_midnight_second_half_resumes_same_day(self):
        candidate = _dt(1, 1, 0)
        final = self._normalize(candidate, window=QUIET_23_06, jitter_min=0)
        self.assertEqual(final, _dt(1, 6, 0))

    def test_case_g_cross_midnight_outside_window_unchanged(self):
        candidate = _dt(1, 22, 0)
        final = self._normalize(candidate, window=QUIET_23_06, jitter_min=20)
        self.assertEqual(final, candidate)

    def test_case_h_cross_midnight_first_half_resumes_next_day(self):
        candidate = _dt(1, 23, 30)
        final = self._normalize(candidate, window=QUIET_23_06, jitter_min=0)
        self.assertEqual(final, _dt(2, 6, 0))

    def test_jitter_is_added_after_resume_point_not_before(self):
        candidate = _dt(1, 0, 0)
        final = normalize_for_quiet_window(
            candidate, enable=True, quiet_start=time(0, 0, 0), quiet_end=time(7, 0, 0),
            jitter_seconds=90,
        )
        self.assertEqual(final, _dt(1, 7, 1, 30))

    def test_microseconds_are_dropped_from_final(self):
        candidate = datetime(2026, 9, 1, 0, 15, 0, 123456)
        final = normalize_for_quiet_window(
            candidate, enable=True, quiet_start=time(0, 0, 0), quiet_end=time(7, 0, 0),
            jitter_seconds=0,
        )
        self.assertEqual(final.microsecond, 0)
