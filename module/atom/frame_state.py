# This Python file uses the following encoding: utf-8
"""连续帧的视觉状态判定：`changed` 与 `stable`。

- `changed`：自上一次 `reset()` / 首帧以来，是否出现过「相对基线的差异 >= changed_threshold」。
  一旦为 True 就锁存，直到下一次 `reset()`；即使画面又回到基线也不会退回 False。
- `stable`：最近是否已连续 `stable_frames` 帧满足「相邻帧之间的差异 <= stable_threshold」。
  任何一次相邻帧明显变化都会把连续计数清零。`changed` 与 `stable` 相互独立。

这是一个纯图像组件：只处理调用方传入的帧，**不截图、不 sleep、不做超时轮询**，
不依赖 Device / BaseTask / ScriptTask / Timer / OCR / BehaviorTrace。
设备层的截图轮询与 timeout 留给上层（未来的 WaitPolicy）。

差异算法只算「两帧有多不一样」，不含任何业务阈值。所有判定阈值由调用方显式传入。
"""

from dataclasses import dataclass

import numpy as np

from module.base.utils import area_limit, image_size

# 判定单个像素是否「变化」的通道绝对差阈值。
# 仅为通用保守默认值，方便通用调用 / 测试，**不代表任何游戏页面的最佳参数**。
DEFAULT_PIXEL_THRESHOLD = 15


def _validate_frame(frame, name: str) -> None:
    if frame is None:
        raise ValueError(f'{name} 不能为 None')
    if not isinstance(frame, np.ndarray):
        raise ValueError(f'{name} 必须是 numpy.ndarray，当前为 {type(frame)!r}')
    if frame.ndim not in (2, 3):
        raise ValueError(f'{name} 维度必须是 2（灰度）或 3（多通道），当前为 {frame.ndim}')
    if frame.size == 0:
        raise ValueError(f'{name} 是空帧')


def _resolve_roi(roi, width: int, height: int):
    """校验并归一化 ROI。

    roi 为 None 表示全图。否则必须是 `(x1, y1, x2, y2)`（左上、右下，与
    `module.base.utils.crop` / `area_*` 系列一致）。宽高必须为正；越界部分按项目
    既有约定 clamp 到图像范围（复用 `area_limit`）；与图像完全无重叠时报错。
    """
    if roi is None:
        return None
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in roi)
    except (TypeError, ValueError):
        raise ValueError(f'ROI 必须是 (x1, y1, x2, y2) 数值四元组：{roi!r}')
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f'ROI 宽高必须为正（要求 x2 > x1 且 y2 > y1）：{roi!r}')
    cx1, cy1, cx2, cy2 = area_limit((x1, y1, x2, y2), (0, 0, width, height))
    cx1, cy1, cx2, cy2 = int(cx1), int(cy1), int(cx2), int(cy2)
    if cx2 <= cx1 or cy2 <= cy1:
        raise ValueError(f'ROI 与图像 {width}x{height} 无重叠：{roi!r}')
    return cx1, cy1, cx2, cy2


def frame_difference(frame_a, frame_b, roi=None,
                     pixel_threshold: int = DEFAULT_PIXEL_THRESHOLD) -> float:
    """计算两帧在 ROI 内的视觉差异，返回 `[0.0, 1.0]`。

    算法：逐像素取各通道绝对差的最大值，超过 `pixel_threshold` 记为「变化像素」，
    返回变化像素占 ROI 像素总数的比例。`0.0` 表示完全相同，越接近 `1.0` 差异越大。

    Args:
        frame_a / frame_b: `numpy.ndarray`，形状必须一致（灰度 2 维或多通道 3 维，uint8）。
        roi: `None`（全图）或 `(x1, y1, x2, y2)`。
        pixel_threshold: 单像素通道差阈值，纯算法参数（默认见 `DEFAULT_PIXEL_THRESHOLD`）。

    Raises:
        ValueError: 帧为 None / 非 ndarray / 维度非法 / 两帧形状不一致 / ROI 非法。
    """
    _validate_frame(frame_a, 'frame_a')
    _validate_frame(frame_b, 'frame_b')
    if frame_a.shape != frame_b.shape:
        raise ValueError(f'两帧形状不一致：{frame_a.shape} vs {frame_b.shape}')

    width, height = image_size(frame_a)
    box = _resolve_roi(roi, width, height)
    if box is not None:
        x1, y1, x2, y2 = box
        region_a = frame_a[y1:y2, x1:x2]
        region_b = frame_b[y1:y2, x1:x2]
    else:
        region_a = frame_a
        region_b = frame_b

    threshold = max(0, int(pixel_threshold))
    diff = np.abs(region_a.astype(np.int16) - region_b.astype(np.int16))
    per_pixel = diff.max(axis=2) if diff.ndim == 3 else diff
    changed_pixels = per_pixel > threshold
    return float(changed_pixels.mean())


@dataclass(frozen=True)
class FrameStateResult:
    """一次 `FrameStateDetector.update()` 的结果快照。"""

    # 自 reset / 首帧以来是否出现过明显变化（锁存）。
    changed: bool
    # 是否已连续 stable_frames 帧相邻差异不超过 stable_threshold。
    stable: bool
    # 当前帧相对基线的差异分数 [0.0, 1.0]。
    difference: float
    # 当前连续「相邻帧安静」的帧数。
    stable_count: int


class FrameStateDetector:
    """在一条连续帧序列上维护 `changed` / `stable` 状态。

    典型用法：

        detector = FrameStateDetector(changed_threshold=..., stable_threshold=...,
                                      stable_frames=..., roi=...)
        detector.reset(baseline_frame)      # 可选；不调则首个 update 帧作为基线
        result = detector.update(frame)     # 每来一帧调一次
        result.changed / result.stable / result.difference / result.stable_count

    不做任何设备轮询 / sleep / 超时；这些留给未来的设备等待层。
    """

    def __init__(self, changed_threshold: float, stable_threshold: float,
                 stable_frames: int, roi=None,
                 pixel_threshold: int = DEFAULT_PIXEL_THRESHOLD) -> None:
        if int(stable_frames) < 1:
            raise ValueError(f'stable_frames 必须 >= 1：{stable_frames}')
        if float(changed_threshold) < 0.0:
            raise ValueError(f'changed_threshold 不能为负：{changed_threshold}')
        if float(stable_threshold) < 0.0:
            raise ValueError(f'stable_threshold 不能为负：{stable_threshold}')
        self._changed_threshold = float(changed_threshold)
        self._stable_threshold = float(stable_threshold)
        self._stable_frames = int(stable_frames)
        self._roi = roi
        self._pixel_threshold = max(0, int(pixel_threshold))
        self._baseline = None
        self._prev = None
        self._changed = False
        self._stable_count = 0
        self._last_difference = 0.0

    def reset(self, baseline) -> None:
        """把 `baseline` 设为新的参考帧，并清空 changed / stable 状态。"""
        _validate_frame(baseline, 'baseline')
        # 立即校验 ROI，让非法 ROI 在 reset 阶段就报错，而不是拖到第一次 update。
        _resolve_roi(self._roi, *image_size(baseline))
        self._baseline = baseline
        self._prev = baseline
        self._changed = False
        self._stable_count = 0
        self._last_difference = 0.0

    def update(self, frame) -> FrameStateResult:
        """喂入一帧，推进 changed / stable 状态并返回结果快照。"""
        _validate_frame(frame, 'frame')

        if self._baseline is None:
            # 首帧直接作为基线，不计入 stable 连续计数。
            _resolve_roi(self._roi, *image_size(frame))
            self._baseline = frame
            self._prev = frame
            self._last_difference = 0.0
            return FrameStateResult(changed=False, stable=False,
                                    difference=0.0, stable_count=0)

        baseline_diff = frame_difference(
            self._baseline, frame, roi=self._roi, pixel_threshold=self._pixel_threshold
        )
        self._last_difference = baseline_diff
        if not self._changed and baseline_diff >= self._changed_threshold:
            self._changed = True

        prev_diff = frame_difference(
            self._prev, frame, roi=self._roi, pixel_threshold=self._pixel_threshold
        )
        if prev_diff <= self._stable_threshold:
            self._stable_count += 1
        else:
            self._stable_count = 0
        self._prev = frame

        return FrameStateResult(
            changed=self._changed,
            stable=self._stable_count >= self._stable_frames,
            difference=baseline_diff,
            stable_count=self._stable_count,
        )

    @property
    def changed(self) -> bool:
        return self._changed

    @property
    def stable(self) -> bool:
        return self._stable_count >= self._stable_frames

    @property
    def stable_count(self) -> int:
        return self._stable_count

    @property
    def last_difference(self) -> float:
        return self._last_difference
