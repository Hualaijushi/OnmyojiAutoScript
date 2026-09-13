# This Python file uses the following encoding: utf-8
"""K4-A：好友结界卡列表「当前选中项」发光竖线的动态锚点检测。

职责单一——给一帧截图 + `I_IS_SELECTED` 资产（`roi_back` = 好友卡列表右缘、纵向覆盖整个可见
滚动高度的窄条），在 `roi_back` 内**动态定位**当前 selected glow，返回**干净的视觉 bbox /
center_y**，供 K4 计算实际列表滚动位移 `actual_scroll_dy`。

不做：swipe / FrameWait / 改 PASS 状态 / projection / dedup。
不用 `RuleImage.coord()`——那是 T7 点击位置采样（叠 preferred 热点），测量需要干净几何中心。
不依赖 `SWIPE_DISTANCE_RANGE` / commanded 位移——K4 的价值就是「实际 ≠ 指令」（Level C 已确认）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型提示，运行时不 import，保持本模块轻依赖
    import numpy as np
    from module.atom.image import RuleImage


@dataclass(frozen=True)
class SelectedAnchorResult:
    """一次 selected glow 检测结果。`available=False` 时其余字段无意义。"""

    available: bool
    center_y: float | None = None      # 匹配框中心 Y（绝对屏幕坐标）= y + h / 2
    bbox: tuple | None = None          # (x, y, w, h) 绝对坐标
    score: float | None = None         # 本次匹配相似度
    match_count: int = 0               # NMS 去重后的候选数（收敛判定 / 诊断用）


def detect_selected_anchor(
    frame: "np.ndarray",
    rule: "RuleImage",
    *,
    threshold: float | None = None,
    nms_threshold: float = 0.3,
    frame_id: str | None = None,
) -> SelectedAnchorResult:
    """在 `rule.roi_back` 内找 selected glow，返回可靠锚点或 `available=False`。

    走 `RuleImage.match_all_any()`（`roi_back` 内 `cv2.matchTemplate` 全量命中 + NMS 去重，
    返回 `(score, x, y, w, h)` 绝对坐标），用资产自带阈值（`I_IS_SELECTED` = 0.8）——
    **不在这里改资产阈值**。

    收敛规则（第一版，保守）：NMS 之后——
      - 0 个候选 → unavailable（首屏没点过卡 / 本屏无选中 / glow 滚出搜索区被裁切）。
      - 恰 1 个候选 → available，用该候选的 score / bbox / center_y。
      - >1 个候选 → unavailable（宁可测不到，也不选错 glow；多候选收敛策略等 Level C 再定，
        第一版不拍脑袋加 score_gap）。
    """
    matches = rule.match_all_any(
        frame, threshold=threshold, nms_threshold=nms_threshold, frame_id=frame_id
    )
    count = len(matches)
    if count != 1:
        return SelectedAnchorResult(available=False, match_count=count)
    score, x, y, w, h = matches[0]
    return SelectedAnchorResult(
        available=True,
        center_y=float(y) + float(h) / 2.0,
        bbox=(int(x), int(y), int(w), int(h)),
        score=float(score),
        match_count=1,
    )
