# This Python file uses the following encoding: utf-8
"""FrameState Wait Layer：把 `FrameStateDetector` + 连续取帧 + 有限 timeout 组合成
一次「等页面相对 baseline 发生变化并稳定下来」的有限等待。

职责边界：

- `FrameStateDetector`（`module/atom/frame_state.py`）：只做帧差算法与 changed/stable 状态。
- 本层：按调用方注入的 `frame_provider` 反复取帧喂给 detector，直到「changed 且 stable」
  成功、或到达 timeout；返回结构化结果，**超时不抛异常**。
- 调用方（未来的 Task）：决定 baseline / ROI / 阈值 / stable_frames / timeout，以及失败后的
  retry / recovery。
- `Control`：只做输入动作。

本层不依赖 Device / BaseTask / ScriptTask / screenshot / Timer / BehaviorTrace。
`frame_provider` 是注入的 callable：生产层以后传 `self.device.screenshot`（它自带
`_screenshot_interval` 节流），测试传 fake。`clock` 同理可注入以做确定性 timeout 测试。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from module.atom.frame_state import DEFAULT_PIXEL_THRESHOLD, FrameStateDetector

# clock 必须单调递增（生产用 time.monotonic）。这个上限只是防「注入了不推进的 clock」
# 造成死循环的兜底；正常 timeout 远早于此触发（真实场景每次等待通常只轮询几百帧）。
_MAX_POLLS = 1_000_000


@dataclass(frozen=True)
class FrameWaitResult:
    """一次 `wait_for_changed_and_stable()` 的结果。"""

    # 是否观察到相对 baseline 的有效变化（锁存语义，见 frame_state DECISIONS D010）。
    changed: bool
    # 是否已连续 stable_frames 帧相邻安静。
    stable: bool
    # 是否因到达 timeout 才返回（即 changed and stable 未同时满足）。
    timed_out: bool
    # 最后一帧相对 baseline 的差异分 [0.0, 1.0]。
    last_difference: float
    # 最后一次相邻安静连续计数。
    stable_count: int
    # 调用 frame_provider 的次数（不含 baseline）。
    frames_checked: int
    # 从进入等待到返回经过的时间（按注入 clock 计），秒。
    elapsed: float

    @property
    def success(self) -> bool:
        """成功 == 页面发生过变化且随后稳定。`stable` 单独为 True 不算成功（见 D010）。"""
        return self.changed and self.stable and not self.timed_out


def wait_for_changed_and_stable(
    baseline,
    frame_provider: Callable[[], "np.ndarray"],
    *,
    changed_threshold: float,
    stable_threshold: float,
    stable_frames: int,
    timeout: float,
    roi=None,
    pixel_threshold: int = DEFAULT_PIXEL_THRESHOLD,
    poll_interval: float = 0.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> FrameWaitResult:
    """反复取帧，等到「相对 baseline 发生变化并稳定」，或到达 timeout。

    Args:
        baseline: 动作执行**前**的参考帧（调用方在动作前截好传入，本层不自截）。
        frame_provider: 无参 callable，每次轮询调用一次返回当前帧。其异常向上传播。
        changed_threshold / stable_threshold / stable_frames: 判定阈值，**必须显式传**，
            无业务默认；数值校验交给 `FrameStateDetector`（不重复两套校验）。
        timeout: 有限超时秒数，**必须为正数**。到达时返回 `timed_out=True` 的结果，不抛异常。
        roi: `None` 或 `(x1, y1, x2, y2)`，透传给 `FrameStateDetector`。
        pixel_threshold: 纯图像层参数，沿用 `frame_state.DEFAULT_PIXEL_THRESHOLD`。
        poll_interval: 两次轮询之间额外 sleep 的秒数。**默认 0**——生产层的 frame_provider
            （`device.screenshot`）已有 `_screenshot_interval` 节流，不要再叠固定 sleep。
        clock: 单调递增的取时 callable（测试注入 fake 以做确定性 timeout）。
        sleeper: `poll_interval > 0` 时的 sleep callable（测试注入 fake）。

    Returns:
        `FrameWaitResult`。`.success` 为 `True` 当且仅当 `changed and stable and not timed_out`。

    Raises:
        ValueError: `timeout` 非正数 / `poll_interval` 为负 / baseline·frame·roi·阈值非法
            （后者由 `FrameStateDetector` 抛出）。
        `frame_provider` 或 detector 内部抛出的异常原样向上传播（不伪装成 timeout）。
        RuntimeError: 轮询帧数超过 `_MAX_POLLS`（几乎只会因注入了不推进的 clock）。
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f'timeout 必须是正数：{timeout!r}')
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or poll_interval < 0:
        raise ValueError(f'poll_interval 不能为负：{poll_interval!r}')

    detector = FrameStateDetector(
        changed_threshold=changed_threshold,
        stable_threshold=stable_threshold,
        stable_frames=stable_frames,
        roi=roi,
        pixel_threshold=pixel_threshold,
    )
    detector.reset(baseline)  # 立即校验 baseline 形状 + ROI，非法直接抛

    start = clock()
    frames_checked = 0
    last = None  # 最近一次 FrameStateResult

    while True:
        elapsed = clock() - start
        if elapsed >= timeout:
            if last is None:
                return FrameWaitResult(
                    changed=False, stable=False, timed_out=True,
                    last_difference=0.0, stable_count=0,
                    frames_checked=0, elapsed=elapsed,
                )
            return FrameWaitResult(
                changed=last.changed, stable=last.stable, timed_out=True,
                last_difference=last.difference, stable_count=last.stable_count,
                frames_checked=frames_checked, elapsed=elapsed,
            )

        if frames_checked >= _MAX_POLLS:
            raise RuntimeError(
                f'frame_wait 轮询超过 {_MAX_POLLS} 帧仍未到 timeout，'
                f'注入的 clock 可能未推进'
            )

        frame = frame_provider()
        last = detector.update(frame)
        frames_checked += 1

        if last.changed and last.stable:
            return FrameWaitResult(
                changed=True, stable=True, timed_out=False,
                last_difference=last.difference, stable_count=last.stable_count,
                frames_checked=frames_checked, elapsed=elapsed,
            )

        if poll_interval > 0:
            sleeper(poll_interval)
