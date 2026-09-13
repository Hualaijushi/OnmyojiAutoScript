# This Python file uses the following encoding: utf-8
"""K4-B：一帧对一帧（上一稳定屏 → 当前稳定屏）的候选投影去重。纯几何，无状态、无设备依赖。

上一屏 `find_everyone` 的每个候选 bbox 按**实际测得**的 `actual_scroll_dy`（= selected anchor
before_y − after_y，**不是** commanded 位移 `SWIPE_DISTANCE_RANGE`）向上投影到当前屏；与当前屏
`find_everyone` 结果做「同模板类型 + bbox 真实几何交集」的一对一贪心匹配（按 IoU 降序）。匹配上
的当前候选 = 上一屏已处理过的重复项、跳过；剩下的才是真正新进入、需按 D017 业务逻辑点开的候选。

设计约束：
- 只 previous↔current 一帧对一帧，**无持久历史 / 全局 candidate database / 好友身份**。
- 不新增 ±px magic tolerance——只用真实 overlap（IoU > 0），竞争时取 max IoU 决定唯一配对。
- 投影后中心出当前可见 Y 范围的上一屏候选 = 已滚出屏，直接忽略。
- 类型不一致绝不去重（位置重叠也不行）。
"""

from __future__ import annotations

from dataclasses import dataclass

from tasks.KekkaiUtilize.selected_anchor import SelectedAnchorResult


def actual_scroll_dy_px(
    before: SelectedAnchorResult,
    after: SelectedAnchorResult,
    *,
    max_dy: float,
) -> float | None:
    """selected anchor before/after → 实际列表向上滚动的**连续像素值**。不可靠时返回 None。

    - before / after 任一 `available=False` → None（首屏无选中 / 边界裁切都属正常）。
    - 当前是向上 swipe → `dy` 必 > 0；`dy <= 0`（after 不在 before 上方）→ None。
    - `dy >= max_dy`（两锚点同在 selected `roi_back` 高度内，合理位移不应超出整个搜索高度）→ None。
    - **保留连续像素**（173px 不四舍五入成整数格）——K4 的价值就是支持 sub-row displacement。
    """
    if not (before.available and after.available):
        return None
    if before.center_y is None or after.center_y is None:
        return None
    dy = before.center_y - after.center_y
    if dy <= 0:
        return None
    if dy >= max_dy:
        return None
    return dy


def project_bbox(bbox: tuple, actual_scroll_dy: float) -> tuple:
    """列表向上滚 `dy` → 上一屏 bbox 在当前屏的位置：y 减 dy，x/w/h 不变。"""
    x, y, w, h = bbox
    return (x, y - actual_scroll_dy, w, h)


def bbox_iou(a: tuple, b: tuple) -> float:
    """两个 `(x, y, w, h)` 框的 IoU。无交集返回 0.0。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = ix2 - ix1, iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class ProjectionDedupResult:
    """`dedup_by_projection` 的结果。"""

    new_detections: list          # 当前屏真正新进入的候选（保持 find_everyone 原顺序）
    duplicate_indices: frozenset  # 当前屏被判为重复的下标
    matched_pairs: tuple          # ((prev_idx, cur_idx, iou), ...) 供诊断日志


def _det_type(det) -> str:
    """detection = `(image, score, (x, y, w, h))`；类型身份 = `image.name`（稳定，不重新 OCR）。"""
    return det[0].name


def _det_bbox(det) -> tuple:
    return det[2]


def dedup_by_projection(
    previous_detections: list,
    current_detections: list,
    actual_scroll_dy: float,
    *,
    visible_y: tuple,
) -> ProjectionDedupResult:
    """`previous` / `current` 均为 `find_everyone` 结构 `list[(image, score, (x,y,w,h))]`。

    调用方保证 `actual_scroll_dy` 已由 `actual_scroll_dy_px` 校验（> 0 且 < roi_back 高度）。
    """
    top, bottom = visible_y

    projected = []  # (prev_idx, type_name, projected_bbox)
    for pi, det in enumerate(previous_detections):
        pj = project_bbox(_det_bbox(det), actual_scroll_dy)
        cy = pj[1] + pj[3] / 2.0
        if cy < top or cy > bottom:
            continue  # 已滚出当前可见范围，不参与
        projected.append((pi, _det_type(det), pj))

    candidates = []  # (iou, proj_local_idx, cur_idx)
    for k, (_pi, pname, pj) in enumerate(projected):
        for ci, cdet in enumerate(current_detections):
            if _det_type(cdet) != pname:      # 类型必须一致
                continue
            v = bbox_iou(pj, _det_bbox(cdet))
            if v > 0.0:                        # 只需真实几何交集
                candidates.append((v, k, ci))

    candidates.sort(key=lambda t: t[0], reverse=True)
    used_proj: set = set()
    used_cur: set = set()
    pairs = []
    for v, k, ci in candidates:
        if k in used_proj or ci in used_cur:
            continue
        used_proj.add(k)
        used_cur.add(ci)
        pairs.append((projected[k][0], ci, v))

    dup_idx = frozenset(ci for _pi, ci, _v in pairs)
    new_detections = [d for i, d in enumerate(current_detections) if i not in dup_idx]
    return ProjectionDedupResult(
        new_detections=new_detections,
        duplicate_indices=dup_idx,
        matched_pairs=tuple(pairs),
    )
