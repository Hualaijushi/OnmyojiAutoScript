# This Python file uses the following encoding: utf-8
"""KekkaiUtilize Scheduler v1：静默窗口归一化。纯 `datetime`/`time` 输入输出，无设备 /
screenshot / OCR / task config object 依赖，可脱离任务对象独立测试。

设计约束（`docs/` 相关 Inventory 报告已论证，这里只落地）：
- 业务侧（`ScriptTask`）先各自算出 `candidate_next_run`（保留寄养剩余时间 / 短期 retry
  cooldown 等既有语义，本模块完全不关心 candidate 是怎么来的）。
- `candidate` 统一经过本模块的 `normalize_for_quiet_window` 归一化一次，避免出现
  「cooldown + quiet jitter」两次抖动叠加。
- 窗口判定 `is_in_quiet_window` 与「下一个窗口结束时刻」`next_quiet_window_end` 算法
  思想与 `script.py::Script._in_sleep_window` / `_next_time_point`（AntiBan 全局睡眠窗）
  一致——都是「跨午夜安全」的纯时间函数——但本模块**独立实现**，不 import `script.py`，
  避免把一个 task-local 需求绑死到顶层 orchestrator。
- 随机抖动秒数由调用方算好、以 `jitter_seconds` 传入：本模块本身不碰随机源，保持
  100% 确定性、无需 mock 即可测试。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta


def is_in_quiet_window(t: time, start: time, end: time) -> bool:
    """判定时刻 `t` 是否落在 `[start, end)` 静默窗口内。

    - `start < end`：普通区间（例如 00:00~07:00），`start <= t < end`。
    - `start >= end`：跨午夜区间（例如 23:00~06:00），`t >= start or t < end`。
    - `start == end`：视为空窗口（永不静默），返回 `False`。
    """
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def next_quiet_window_end(now: datetime, end: time) -> datetime:
    """从 `now` 起，下一个 `end` 时刻——`now` 当天的 `end` 尚未到达就用当天，否则顺延到明天。"""
    candidate = now.replace(hour=end.hour, minute=end.minute, second=end.second, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def normalize_for_quiet_window(
    candidate: datetime,
    *,
    enable: bool,
    quiet_start: time,
    quiet_end: time,
    jitter_seconds: int,
) -> datetime:
    """`candidate` → 静默窗口归一化后的最终 next_run。

    - `enable=False` → `candidate` 原样返回（不做任何窗口判断）。
    - `candidate` 不落在 `[quiet_start, quiet_end)` → 原样返回。
    - `candidate` 落在窗内 → 顺延到窗口结束（`next_quiet_window_end`）之后再加
      `jitter_seconds` 秒的恢复抖动。

    `jitter_seconds` 由调用方预先从项目统一随机源采样好传入，本函数不产生随机数。
    """
    if not enable:
        return candidate
    if not is_in_quiet_window(candidate.time(), quiet_start, quiet_end):
        return candidate
    resume = next_quiet_window_end(candidate, quiet_end)
    return (resume + timedelta(seconds=jitter_seconds)).replace(microsecond=0)
