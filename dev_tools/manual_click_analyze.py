# This Python file uses the following encoding: utf-8
"""人工点击日志的离线分析：连续点击去重（burst collapse）+ 重新统计。

背景：`ManualClickRecorder` 采到的原始日志里，用户常在鼠标基本不动的情况下对同一
位置连点 3~6 次。这些不是独立的「瞄准落点」，直接拿 raw click 算 preferred center /
spread 会重复加权高频连点位置、压小方差。本工具把「时空连续」的相邻点击链式合并成
一个 burst，用 burst 的**第一个点**作为该次独立落点，再重新统计。

硬约束：
- **只读离线分析**，不启动任何设备 / 游戏 / 服务，不修改任何生产代码。
- **原始 JSONL 永不修改**。派生结果写到 `log/manual_click_analysis/`。
- 不拟合 Gaussian / Student-t / AR(1) / EMA，不建 ClickSampler / ClickProfileManager。
  本工具只回答「人工数据清洗后真实长什么样」，模型设计是后续独立任务。
- 所有阈值都做敏感性分析并报告；不把某一组阈值写成项目长期标准。

运行：``toolkit/python.exe dev_tools/manual_click_analyze.py log/manual_click/<file>.jsonl``
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720

DEFAULT_OUT_DIR = Path(_PROJECT_ROOT) / "log" / "manual_click_analysis"

# 敏感性分析固定跑这几组（time_ms, dist_px）；参考分析参数取 500/5（仅本轮参考，非长期标准）。
SENSITIVITY_GRID = [(300, 3), (500, 5), (800, 5), (500, 8)]
REFERENCE_THRESHOLD = (500, 5)

# burst 合并要求标签兼容：这些字段在相邻两条都存在且不同 → 强制断开。
_LABEL_KEYS = ("scene", "target", "roi")


# --------------------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------------------

def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def load_jsonl(path) -> tuple[list[dict], int]:
    """逐行读 JSONL，返回 (records, skipped_lines)。空行 / 坏 JSON / 非 dict 跳过并计数。"""
    rows: list[dict] = []
    skipped = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                skipped += 1
                continue
            if not isinstance(obj, dict) or "x" not in obj or "y" not in obj or "ts" not in obj:
                skipped += 1
                continue
            rows.append(obj)
    return rows, skipped


def sort_by_ts(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: parse_ts(r["ts"]))


# --------------------------------------------------------------------------------------
# Burst 合并（链式：current vs previous）
# --------------------------------------------------------------------------------------

def _labels_compatible(a: dict, b: dict) -> bool:
    """两条记录若都带某个标签且不同 → 不兼容，不能并入同一 burst。缺标签视为兼容。"""
    for key in _LABEL_KEYS:
        if key in a and key in b and a[key] != b[key]:
            return False
    return True


def collapse_bursts(
    rows: list[dict], *, time_threshold_ms: float, distance_threshold_px: float
) -> list[list[int]]:
    """把时间顺序里「时空连续」的相邻点击链式合并成 burst。

    判据基于 **current vs previous**（不是 current vs burst 第一点）：相邻两点满足
    ``dt <= time_threshold_ms`` 且 ``distance <= distance_threshold_px`` 且标签兼容，
    就继续同一个 burst；否则开新 burst。因此一串小幅漂移（每步都在阈值内）会整体
    归为一个 burst，即使首尾点距离已超过阈值。

    Args:
        rows: 已按时间排序的记录列表。
    Returns:
        每个 burst 一个「原始下标列表」，顺序与输入一致，覆盖全部行且不重叠。
    """
    if not rows:
        return []
    ts = [parse_ts(r["ts"]) for r in rows]
    bursts: list[list[int]] = []
    current = [0]
    for i in range(1, len(rows)):
        dt_ms = (ts[i] - ts[i - 1]).total_seconds() * 1000.0
        step = math.hypot(rows[i]["x"] - rows[i - 1]["x"], rows[i]["y"] - rows[i - 1]["y"])
        if (
            dt_ms <= time_threshold_ms
            and step <= distance_threshold_px
            and _labels_compatible(rows[i], rows[i - 1])
        ):
            current.append(i)
        else:
            bursts.append(current)
            current = [i]
    bursts.append(current)
    return bursts


def burst_record(rows: list[dict], indices: list[int], burst_id: int) -> dict:
    """把一个 burst 折叠成一条派生记录。代表坐标默认取 **第一个点**（用户移动到位后
    的首次按下，后续连点通常没有重新瞄准）；同时给出 centroid 供对照。"""
    members = [rows[k] for k in indices]
    first = members[0]
    xs = [m["x"] for m in members]
    ys = [m["y"] for m in members]
    ts = [parse_ts(m["ts"]) for m in members]
    max_step = 0.0
    for a, b in zip(members, members[1:]):
        max_step = max(max_step, math.hypot(a["x"] - b["x"], a["y"] - b["y"]))

    rec: dict = {
        "burst_id": burst_id,
        "start_ts": first["ts"],
        "end_ts": members[-1]["ts"],
        "click_count": len(members),
        "duration_ms": round((ts[-1] - ts[0]).total_seconds() * 1000.0, 1),
        "x": first["x"],
        "y": first["y"],
        "centroid_x": round(sum(xs) / len(xs), 2),
        "centroid_y": round(sum(ys) / len(ys), 2),
        "max_step_distance": round(max_step, 2),
        "source": first.get("source", "manual"),
    }
    for key in ("config", "scene", "target", "roi", "u", "v"):
        if key in first:
            rec[key] = first[key]
    return rec


# --------------------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------------------

def _percentile(sorted_values: list[float], p: float) -> float:
    """线性插值分位数，p ∈ [0, 1]。空列表返回 nan。"""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * p
    lo = math.floor(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _pstdev(values: list[float], mean_value: float) -> float:
    if len(values) < 1:
        return float("nan")
    return math.sqrt(sum((v - mean_value) ** 2 for v in values) / len(values))


def _relative_uv(x: float, y: float, roi):
    rx, ry, rw, rh = roi
    return (x - rx) / rw, (y - ry) / rh


def _landing_stats_core(points: list[tuple[float, float]], *,
                        logical_w: int = LOGICAL_WIDTH, logical_h: int = LOGICAL_HEIGHT) -> dict:
    """不涉及 ROI 的纯落点统计（mean/std/median/percentile/归一化中心/径向分位）。"""
    n = len(points)
    out: dict = {"count": n}
    if n == 0:
        return out
    xs = sorted(p[0] for p in points)
    ys = sorted(p[1] for p in points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    out.update(
        mean_x=round(mean_x, 2), mean_y=round(mean_y, 2),
        std_x=round(_pstdev([p[0] for p in points], mean_x), 2),
        std_y=round(_pstdev([p[1] for p in points], mean_y), 2),
        median_x=round(_percentile(xs, 0.5), 2),
        median_y=round(_percentile(ys, 0.5), 2),
        p05_x=round(_percentile(xs, 0.05), 2), p25_x=round(_percentile(xs, 0.25), 2),
        p75_x=round(_percentile(xs, 0.75), 2), p95_x=round(_percentile(xs, 0.95), 2),
        p05_y=round(_percentile(ys, 0.05), 2), p25_y=round(_percentile(ys, 0.25), 2),
        p75_y=round(_percentile(ys, 0.75), 2), p95_y=round(_percentile(ys, 0.95), 2),
        normalized_mean_x=round(mean_x / logical_w, 4),
        normalized_mean_y=round(mean_y / logical_h, 4),
    )
    # 径向分布：以 normalized mean 为基准的归一化距离分位数。
    nmx, nmy = mean_x / logical_w, mean_y / logical_h
    radii = sorted(
        math.hypot(p[0] / logical_w - nmx, p[1] / logical_h - nmy) for p in points
    )
    out.update(
        r50=round(_percentile(radii, 0.50), 4),
        r75=round(_percentile(radii, 0.75), 4),
        r90=round(_percentile(radii, 0.90), 4),
        r95=round(_percentile(radii, 0.95), 4),
    )
    return out


def landing_stats(points: list[tuple[float, float]], *, roi=None,
                  logical_w: int = LOGICAL_WIDTH, logical_h: int = LOGICAL_HEIGHT) -> dict:
    """一组独立落点（逻辑像素坐标）的统计。

    ``roi=None``：对全部 ``points`` 计算，不过滤、不 clamp。

    ``roi=(x, y, w, h)``：**ROI-relative 统计默认只用 ``inside_roi`` 的子集**计算——
    包括 ``mean_x/y``、``std_x/y``、``median``、percentile、径向 ``r50..r95``，以及
    ``mean_u/v`` 等 ROI 相对量，避免少量 ROI 外点（聚类边缘误分 / 其它控件 / ROI 定义
    不完整）拉偏 preferred center 和 spread。ROI 外样本**不删除、不 clamp**，单独通过
    ``outside_count`` / ``outside_ratio`` / ``outside_points``（原始 (x, y) 坐标）报告，
    供人工判断这些点的性质。``count`` 字段是参与上述统计的 inside 样本数；
    ``total_count`` 是传入的全部样本数。
    """
    if roi is None:
        return _landing_stats_core(points, logical_w=logical_w, logical_h=logical_h)

    inside_pts: list[tuple[float, float]] = []
    outside_pts: list[tuple[float, float]] = []
    for p in points:
        u, v = _relative_uv(p[0], p[1], roi)
        (inside_pts if (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0) else outside_pts).append(p)

    out = _landing_stats_core(inside_pts, logical_w=logical_w, logical_h=logical_h)
    out["total_count"] = len(points)
    out["outside_count"] = len(outside_pts)
    out["outside_ratio"] = round(len(outside_pts) / len(points), 4) if points else 0.0
    out["outside_points"] = [[p[0], p[1]] for p in outside_pts]
    if inside_pts:
        n = len(inside_pts)
        us = sorted(_relative_uv(p[0], p[1], roi)[0] for p in inside_pts)
        vs = sorted(_relative_uv(p[0], p[1], roi)[1] for p in inside_pts)
        mean_u = sum(us) / n
        mean_v = sum(vs) / n
        out.update(
            roi=list(roi),
            mean_u=round(mean_u, 4), mean_v=round(mean_v, 4),
            std_u=round(_pstdev(us, mean_u), 4), std_v=round(_pstdev(vs, mean_v), 4),
            median_u=round(_percentile(us, 0.5), 4), median_v=round(_percentile(vs, 0.5), 4),
            p05_u=round(_percentile(us, 0.05), 4), p25_u=round(_percentile(us, 0.25), 4),
            p75_u=round(_percentile(us, 0.75), 4), p95_u=round(_percentile(us, 0.95), 4),
            p05_v=round(_percentile(vs, 0.05), 4), p25_v=round(_percentile(vs, 0.25), 4),
            p75_v=round(_percentile(vs, 0.75), 4), p95_v=round(_percentile(vs, 0.95), 4),
        )
    return out


def burst_size_histogram(bursts: list[list[int]]) -> dict:
    buckets = {"1": 0, "2": 0, "3": 0, "4-5": 0, "6+": 0}
    for b in bursts:
        c = len(b)
        if c == 1:
            buckets["1"] += 1
        elif c == 2:
            buckets["2"] += 1
        elif c == 3:
            buckets["3"] += 1
        elif c <= 5:
            buckets["4-5"] += 1
        else:
            buckets["6+"] += 1
    return buckets


def value_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    s = sorted(values)
    mean_v = sum(values) / len(values)
    return {
        "count": len(values),
        "mean": round(mean_v, 2),
        "median": round(_percentile(s, 0.5), 2),
        "p90": round(_percentile(s, 0.9), 2),
        "max": round(s[-1], 2),
    }


def region_split(points: list[tuple[float, float]], y_cut: float):
    """按水平线 y_cut 粗分上 / 下两区。**纯几何切分，不代表任何游戏页面**——
    2026-09-01 曾把这一刀的「上区」直接标成「进攻按钮」、「下区」标成「Large Area」，
    经与真实资产 ROI 核对后确认是错误标签（上区其实是 `C_AREA_1` 目标卡片，真正的
    进攻按钮在上下区之间的第三个簇里）。之后不要再给这个二分结果附加页面语义，
    需要页面级结论请用 `kmeans_clusters` 先验证簇数与位置。
    """
    upper = [p for p in points if p[1] < y_cut]
    lower = [p for p in points if p[1] >= y_cut]
    return upper, lower


def detect_calibration_prefix(
    rows: list[dict], *, edge_margin_px: float = 40.0, min_gap_s: float = 8.0,
    logical_w: int = LOGICAL_WIDTH, logical_h: int = LOGICAL_HEIGHT,
) -> int:
    """识别日志开头一段「窗口映射校准点击」（左上 / 中心 / 右下…）的前缀长度。

    规则：从第一条起找相邻间隔首次 `>= min_gap_s` 的位置 k；若 `rows[:k]` 里至少
    一条落在屏幕边缘 `edge_margin_px` 以内，判定该前缀是校准点击、返回 k；否则
    （包括全程都没有一次够大的间隔）返回 0，不强行剔除任何数据。

    **这是一条只在 `yys1_2026-09-01.jsonl` 这份日志上验证过的启发式，不是可靠的
    通用「窗口映射校准」协议**——换一份日志（不同用户的采样习惯、不同的 session
    结构）时，这条「首次大间隔 + 边缘点」的规则不一定成立，可能漏判也可能误判。
    调用方（`analyze()`）会把探测结果连同判定依据、被排除的时间范围一起写进
    `summary["calibration"]`，使用前应该人工核对该范围是否合理；不放心时用
    `analyze(calibration_count=...)` / CLI `--calibration-count` 显式指定，跳过
    这条启发式。

    Args:
        rows: 已按时间排序的原始记录（未去重）。
    """
    if not rows:
        return 0
    ts = [parse_ts(r["ts"]) for r in rows]
    k = None
    for i in range(1, len(rows)):
        if (ts[i] - ts[i - 1]).total_seconds() >= min_gap_s:
            k = i
            break
    if k is None:
        return 0
    prefix = rows[:k]
    has_edge = any(
        r["x"] <= edge_margin_px or r["x"] >= logical_w - edge_margin_px
        or r["y"] <= edge_margin_px or r["y"] >= logical_h - edge_margin_px
        for r in prefix
    )
    return k if has_edge else 0


def kmeans_clusters(
    points: list[tuple[float, float]], *, seeds: list[tuple[float, float]], max_iters: int = 50
) -> tuple[list[int], list[tuple[float, float]]]:
    """确定性 k-means（固定种子、无随机初始化）。

    种子应来自对数据分布的直接观察（例如密度网格 / 人工标注的大致范围），
    结果的可信度由簇内距离分布（`p90` 是否明显小于簇间距离）判断，不应该
    直接把种子当成最终边界；调用方应报告簇内 `median` / `p90` 距离。

    Returns:
        `(labels, centroids)`：`labels[i]` 是 `points[i]` 所属簇的下标（`0..len(seeds)-1`），
        `centroids` 是收敛后的簇质心。空簇保留上一轮质心，不产生除零。
    """
    if not seeds:
        raise ValueError("seeds 不能为空")
    k = len(seeds)
    centroids = [tuple(s) for s in seeds]
    labels: list[int] = []
    for _ in range(max_iters):
        new_labels = []
        for p in points:
            dists = [math.hypot(p[0] - c[0], p[1] - c[1]) for c in centroids]
            new_labels.append(dists.index(min(dists)))
        stable = new_labels == labels
        labels = new_labels
        new_centroids = []
        for ci in range(k):
            members = [points[i] for i in range(len(points)) if labels[i] == ci]
            if members:
                new_centroids.append(
                    (sum(p[0] for p in members) / len(members),
                     sum(p[1] for p in members) / len(members))
                )
            else:
                new_centroids.append(centroids[ci])
        centroids = new_centroids
        if stable:
            break
    return labels, centroids


def transition_counts(labels: list[int]) -> dict[tuple[int, int], int]:
    """按时间顺序统计相邻簇标签的转移次数 `{(from, to): count}`。"""
    counts: dict[tuple[int, int], int] = {}
    for a, b in zip(labels, labels[1:]):
        counts[(a, b)] = counts.get((a, b), 0) + 1
    return counts


# --------------------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------------------

def _threshold_row(rows: list[dict], t_ms: float, d_px: float) -> dict:
    bursts = collapse_bursts(rows, time_threshold_ms=t_ms, distance_threshold_px=d_px)
    reps = [(rows[b[0]]["x"], rows[b[0]]["y"]) for b in bursts]
    st = landing_stats(reps)
    return {
        "time_threshold_ms": t_ms,
        "distance_threshold_px": d_px,
        "raw_click_count": len(rows),
        "burst_count": len(bursts),
        "collapse_ratio": round(1 - len(bursts) / len(rows), 4) if rows else 0.0,
        "center_x": st.get("mean_x"),
        "center_y": st.get("mean_y"),
        "normalized_center_x": st.get("normalized_mean_x"),
        "normalized_center_y": st.get("normalized_mean_y"),
        "std_x": st.get("std_x"),
        "std_y": st.get("std_y"),
    }


def analyze(path, *, roi=None, y_split: float | None = None,
            cluster_seeds: list[tuple[float, float]] | None = None,
            cluster_labels: list[str] | None = None,
            cluster_roi: dict[int, tuple[int, int, int, int]] | None = None,
            exclude_calibration: bool = True,
            calibration_count: int | None = None,
            ref_threshold=REFERENCE_THRESHOLD, out_dir: Path | None = None) -> dict:
    rows_raw, skipped = load_jsonl(path)
    rows = sort_by_ts(rows_raw)
    out_dir = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    stem = Path(path).stem

    summary: dict = {
        "source_file": str(path),
        "raw_click_count": len(rows),
        "skipped_lines": skipped,
        "reference_threshold": {"time_ms": ref_threshold[0], "distance_px": ref_threshold[1],
                                "note": "仅本轮参考分析参数，非项目长期标准"},
        "logical_width": LOGICAL_WIDTH,
        "logical_height": LOGICAL_HEIGHT,
    }
    if not rows:
        summary["error"] = "no usable rows"
        return summary

    # 敏感性分析
    grid = list(SENSITIVITY_GRID)
    if tuple(ref_threshold) not in grid:
        grid.append(tuple(ref_threshold))
    summary["threshold_sensitivity"] = [_threshold_row(rows, t, d) for t, d in grid]

    # 参考阈值下的 burst 折叠
    ref_bursts = collapse_bursts(
        rows, time_threshold_ms=ref_threshold[0], distance_threshold_px=ref_threshold[1]
    )
    dedup_records = [burst_record(rows, b, i + 1) for i, b in enumerate(ref_bursts)]
    reps = [(r["x"], r["y"]) for r in dedup_records]
    centroids = [(r["centroid_x"], r["centroid_y"]) for r in dedup_records]

    summary["reference_result"] = {
        "burst_count": len(ref_bursts),
        "collapse_ratio": round(1 - len(ref_bursts) / len(rows), 4),
        "repeat_click_share": round(1 - len(ref_bursts) / len(rows), 4),
        "raw_all_landing_stats": landing_stats([(r["x"], r["y"]) for r in rows], roi=roi),
        "dedup_all_landing_stats_firstpoint": landing_stats(reps, roi=roi),
        "dedup_all_landing_stats_centroid": landing_stats(centroids, roi=roi),
    }

    # 连续点击行为
    durations = [r["duration_ms"] for r in dedup_records if r["click_count"] > 1]
    max_steps = [r["max_step_distance"] for r in dedup_records if r["click_count"] > 1]
    summary["burst_behavior"] = {
        "click_count_histogram": burst_size_histogram(ref_bursts),
        "multi_click_burst_count": sum(1 for b in ref_bursts if len(b) > 1),
        "single_click_burst_count": sum(1 for b in ref_bursts if len(b) == 1),
        "raw_clicks_in_multi_bursts": sum(len(b) for b in ref_bursts if len(b) > 1),
        "duration_ms_stats_multi": value_stats(durations),
        "max_step_distance_stats_multi": value_stats(max_steps),
    }

    # 校准点击识别：只从「行为统计」口径剔除，ALL / raw 统计不受影响，原始记录不删除。
    # calibration_count 显式给出时优先于自动探测——自动规则只是本数据集验证过的启发式，
    # 不是可靠的通用「窗口映射校准」协议，换一份日志前应先看 detected_by 是不是 auto。
    if calibration_count is not None:
        calibration_n = max(0, int(calibration_count))
        calibration_detected_by = "override"
    elif exclude_calibration:
        calibration_n = detect_calibration_prefix(rows)
        calibration_detected_by = "auto_heuristic"
    else:
        calibration_n = 0
        calibration_detected_by = "disabled"
    behavior_bursts = [b for b in ref_bursts if b[0] >= calibration_n]
    behavior_reps = [(rows[b[0]]["x"], rows[b[0]]["y"]) for b in behavior_bursts]
    summary["calibration"] = {
        "excluded_leading_count": calibration_n,
        "detected_by": calibration_detected_by,
        "excluded_range_ts": (
            [rows[0]["ts"], rows[calibration_n - 1]["ts"]] if calibration_n > 0 else []
        ),
        "note": "⚠️ 启发式，不是可靠的通用「窗口映射校准」协议：规则是「首次相邻间隔 >= 8s 且"
                "前缀含屏幕边缘点」，只在本数据集上验证过。换一份日志前请先看 excluded_range_ts "
                "是否合理，必要时用 analyze(calibration_count=...) / --calibration-count 手动覆盖。"
                "仅从下方 behavior_only 统计剔除，ALL / raw 统计与原始 JSONL 均不受影响",
    }
    summary["reference_result"]["behavior_only_count"] = len(behavior_reps)
    summary["reference_result"]["behavior_only_landing_stats"] = landing_stats(behavior_reps, roi=roi)

    # 粗分区（纯几何切分，非页面识别——语义结论必须用下面的 kmeans 簇核实）
    if y_split is not None:
        raw_pts = [(r["x"], r["y"]) for r in rows]
        raw_up, raw_lo = region_split(raw_pts, y_split)
        dd_up, dd_lo = region_split(reps, y_split)
        summary["region_split"] = {
            "y_cut": y_split,
            "note": "按水平线粗分上/下两区，纯几何、不代表任何游戏页面语义",
            "region_upper": {
                "raw_count": len(raw_up),
                "raw_stats": landing_stats(raw_up, roi=roi),
                "dedup_count": len(dd_up),
                "dedup_stats": landing_stats(dd_up, roi=roi),
            },
            "region_lower": {
                "raw_count": len(raw_lo),
                "raw_stats": landing_stats(raw_lo, roi=roi),
                "dedup_count": len(dd_lo),
                "dedup_stats": landing_stats(dd_lo, roi=roi),
            },
        }

    # 三簇分析（k-means，seed 需来自对数据的观察；用于验证/核实页面语义假设）
    if cluster_seeds:
        k = len(cluster_seeds)
        names = cluster_labels or [f"cluster_{i}" for i in range(k)]
        labels, centroids = kmeans_clusters(behavior_reps, seeds=cluster_seeds)
        raw_behavior_pts = [(r["x"], r["y"]) for r in rows[calibration_n:]]
        raw_labels, _ = kmeans_clusters(raw_behavior_pts, seeds=centroids, max_iters=1)

        clusters_block: dict = {}
        for ci in range(k):
            dd_pts = [behavior_reps[i] for i in range(len(behavior_reps)) if labels[i] == ci]
            raw_pts_c = [raw_behavior_pts[i] for i in range(len(raw_behavior_pts)) if raw_labels[i] == ci]
            dists = sorted(math.hypot(p[0] - centroids[ci][0], p[1] - centroids[ci][1]) for p in dd_pts)
            entry = {
                "centroid": [round(centroids[ci][0], 1), round(centroids[ci][1], 1)],
                "dedup_count": len(dd_pts),
                "raw_count": len(raw_pts_c),
                "dedup_stats": landing_stats(dd_pts, roi=roi),
                "raw_stats": landing_stats(raw_pts_c, roi=roi),
                "intra_cluster_distance_px": {
                    "median": round(_percentile(dists, 0.5), 1) if dists else None,
                    "p90": round(_percentile(dists, 0.9), 1) if dists else None,
                    "max": round(dists[-1], 1) if dists else None,
                },
            }
            if cluster_roi and ci in cluster_roi:
                entry["asset_roi_stats"] = landing_stats(dd_pts, roi=cluster_roi[ci])
            clusters_block[names[ci]] = entry

        trans = transition_counts(labels)
        cluster_sensitivity = {name: [] for name in names}
        for t, d in SENSITIVITY_GRID:
            b2 = collapse_bursts(rows, time_threshold_ms=t, distance_threshold_px=d)
            b2_behavior = [b for b in b2 if b[0] >= calibration_n]
            pts2 = [(rows[b[0]]["x"], rows[b[0]]["y"]) for b in b2_behavior]
            labels2, _ = kmeans_clusters(pts2, seeds=cluster_seeds)
            for ci, name in enumerate(names):
                members = [pts2[i] for i in range(len(pts2)) if labels2[i] == ci]
                st = landing_stats(members)
                cluster_sensitivity[name].append({
                    "time_threshold_ms": t, "distance_threshold_px": d,
                    "count": len(members),
                    "normalized_center_x": st.get("normalized_mean_x"),
                    "normalized_center_y": st.get("normalized_mean_y"),
                })

        summary["three_cluster"] = {
            "seeds": [list(s) for s in cluster_seeds],
            "labels": names,
            "note": "k-means(3)，种子来自对本会话数据的探索性观察，仅作为分析起点；"
                    "是否可信看 intra_cluster_distance_px 是否明显小于簇间距离，不要把种子当最终边界",
            "clusters": clusters_block,
            "transitions": {f"{names[a]}->{names[b]}": n for (a, b), n in trans.items()},
            "threshold_sensitivity": cluster_sensitivity,
        }

    # 写派生文件（原始文件永不改）
    out_dir.mkdir(parents=True, exist_ok=True)
    dedup_path = out_dir / f"{stem}_dedup.jsonl"
    summary_path = out_dir / f"{stem}_summary.json"
    with open(dedup_path, "w", encoding="utf-8") as fh:
        for rec in dedup_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    summary["_output"] = {"dedup_jsonl": str(dedup_path), "summary_json": str(summary_path)}
    return summary


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _parse_point(text: str) -> tuple[float, float]:
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 2:
        raise ValueError(f"种子需要 2 个逗号分隔数值 x,y：{text!r}")
    return (float(parts[0]), float(parts[1]))


def _parse_roi(text: str):
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 4:
        raise ValueError(f"ROI 需要 4 个逗号分隔整数 x,y,w,h：{text!r}")
    x, y, w, h = (int(p) for p in parts)
    if w <= 0 or h <= 0:
        raise ValueError(f"ROI 宽高必须为正：{text!r}")
    return (x, y, w, h)


def _fmt(v):
    return "n/a" if v is None else v


def _print_report(s: dict) -> None:
    print("# Manual Click Burst Analysis")
    print()
    print(f"source: {s['source_file']}")
    print(f"raw clicks: {s['raw_click_count']}   skipped lines: {s['skipped_lines']}")
    ref = s["reference_threshold"]
    print(f"reference threshold: {ref['time_ms']}ms / {ref['distance_px']}px  ({ref['note']})")
    if "error" in s:
        print(f"\n[!] {s['error']}")
        return
    print()
    print("## Threshold sensitivity")
    print(f"{'time_ms':>8} {'dist_px':>8} {'raw':>6} {'dedup':>6} {'collapse%':>10} "
          f"{'center_x':>9} {'center_y':>9} {'ncx':>7} {'ncy':>7} {'std_x':>7} {'std_y':>7}")
    for r in s["threshold_sensitivity"]:
        print(f"{r['time_threshold_ms']:>8} {r['distance_threshold_px']:>8} "
              f"{r['raw_click_count']:>6} {r['burst_count']:>6} "
              f"{r['collapse_ratio'] * 100:>9.1f}% {_fmt(r['center_x']):>9} {_fmt(r['center_y']):>9} "
              f"{_fmt(r['normalized_center_x']):>7} {_fmt(r['normalized_center_y']):>7} "
              f"{_fmt(r['std_x']):>7} {_fmt(r['std_y']):>7}")
    rr = s["reference_result"]
    print()
    print(f"## Reference ({ref['time_ms']}ms/{ref['distance_px']}px)")
    print(f"independent landings: {rr['burst_count']}   "
          f"repeat-click share: {rr['repeat_click_share'] * 100:.1f}%")
    raw = rr["raw_all_landing_stats"]
    dd = rr["dedup_all_landing_stats_firstpoint"]
    cen = rr["dedup_all_landing_stats_centroid"]
    print(f"  ALL raw   : center=({raw['mean_x']},{raw['mean_y']}) "
          f"norm=({raw['normalized_mean_x']},{raw['normalized_mean_y']}) "
          f"std=({raw['std_x']},{raw['std_y']}) r50/r90/r95={raw['r50']}/{raw['r90']}/{raw['r95']}")
    print(f"  ALL dedup : center=({dd['mean_x']},{dd['mean_y']}) "
          f"norm=({dd['normalized_mean_x']},{dd['normalized_mean_y']}) "
          f"std=({dd['std_x']},{dd['std_y']}) r50/r90/r95={dd['r50']}/{dd['r90']}/{dd['r95']}")
    print(f"  ALL dedup (centroid rep): center=({cen['mean_x']},{cen['mean_y']}) "
          f"std=({cen['std_x']},{cen['std_y']})")
    if "calibration" in s:
        cal = s["calibration"]
        beh = rr.get("behavior_only_landing_stats", {})
        print(f"  calibration prefix excluded: {cal['excluded_leading_count']} clicks "
              f"(by={cal['detected_by']}, range={cal['excluded_range_ts']})")
        if beh.get("count"):
            print(f"  behavior-only dedup ({rr.get('behavior_only_count')}): "
                  f"center=({beh.get('mean_x')},{beh.get('mean_y')}) "
                  f"norm=({beh.get('normalized_mean_x')},{beh.get('normalized_mean_y')}) "
                  f"std=({beh.get('std_x')},{beh.get('std_y')})")
    bb = s["burst_behavior"]
    print()
    print("## Burst behavior")
    print(f"  click_count histogram: {bb['click_count_histogram']}")
    print(f"  multi-click bursts: {bb['multi_click_burst_count']} "
          f"(raw clicks inside them: {bb['raw_clicks_in_multi_bursts']})")
    print(f"  multi-burst duration ms: {bb['duration_ms_stats_multi']}")
    print(f"  multi-burst max step px: {bb['max_step_distance_stats_multi']}")
    if "region_split" in s:
        rs = s["region_split"]
        print()
        print(f"## Region split (y_cut={rs['y_cut']}, 纯几何非页面识别)")
        for name, blk in (("region_upper", rs["region_upper"]), ("region_lower", rs["region_lower"])):
            r_ = blk["raw_stats"]
            d_ = blk["dedup_stats"]
            print(f"  {name}: raw n={blk['raw_count']} "
                  f"center=({r_.get('mean_x')},{r_.get('mean_y')}) "
                  f"norm=({r_.get('normalized_mean_x')},{r_.get('normalized_mean_y')})")
            print(f"  {' ' * len(name)}  dedup n={blk['dedup_count']} "
                  f"center=({d_.get('mean_x')},{d_.get('mean_y')}) "
                  f"norm=({d_.get('normalized_mean_x')},{d_.get('normalized_mean_y')}) "
                  f"std=({d_.get('std_x')},{d_.get('std_y')}) "
                  f"r50/r90/r95={d_.get('r50')}/{d_.get('r90')}/{d_.get('r95')}")
    if "three_cluster" in s:
        tc = s["three_cluster"]
        print()
        print(f"## Three-cluster (k-means, seeds={tc['seeds']})")
        for name in tc["labels"]:
            c = tc["clusters"][name]
            d_ = c["dedup_stats"]
            icd = c["intra_cluster_distance_px"]
            print(f"  {name}: centroid={c['centroid']} dedup n={c['dedup_count']} raw n={c['raw_count']} "
                  f"norm=({d_.get('normalized_mean_x')},{d_.get('normalized_mean_y')}) "
                  f"std=({d_.get('std_x')},{d_.get('std_y')}) "
                  f"intra_dist(median/p90/max)=({icd['median']},{icd['p90']},{icd['max']})")
        print(f"  transitions: {tc['transitions']}")
    if "_output" in s:
        print()
        print(f"output: {s['_output']['dedup_jsonl']}")
        print(f"        {s['_output']['summary_json']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="manual_click_analyze",
        description="人工点击日志的 burst collapse + 重新统计（离线，不改原始日志）。",
    )
    p.add_argument("logfile", help="log/manual_click/<config>_<日期>.jsonl")
    p.add_argument("--time-threshold-ms", type=float, default=REFERENCE_THRESHOLD[0],
                   help=f"参考阈值：burst 内相邻点最大时间间隔 ms（默认 {REFERENCE_THRESHOLD[0]}）")
    p.add_argument("--distance-threshold-px", type=float, default=REFERENCE_THRESHOLD[1],
                   help=f"参考阈值：burst 内相邻点最大距离 px（默认 {REFERENCE_THRESHOLD[1]}）")
    p.add_argument("--roi", default=None, help="可选 ROI x,y,w,h（1280x720 逻辑空间），给了则输出 u/v 统计")
    p.add_argument("--y-split", type=float, default=None,
                   help="粗分上/下两区的水平线 y（默认关闭；纯几何切分，不代表页面语义，见 --three-cluster）")
    p.add_argument("--three-cluster", action="store_true",
                   help="用 k-means(3) 做三簇分析（验证空间簇假设），种子默认取 --seed-a/b/c")
    p.add_argument("--seed-a", default="650,205", help="簇 A 起始种子 x,y（默认 650,205）")
    p.add_argument("--seed-b", default="675,390", help="簇 B 起始种子 x,y（默认 675,390）")
    p.add_argument("--seed-c", default="950,485", help="簇 C 起始种子 x,y（默认 950,485）")
    p.add_argument("--cluster-labels", default="cluster_A,cluster_B,cluster_C",
                   help="三簇的展示名，逗号分隔（默认 cluster_A,cluster_B,cluster_C）")
    p.add_argument("--no-exclude-calibration", action="store_true",
                   help="不识别 / 不剔除开头的窗口映射校准点击（默认会用启发式自动识别并单独标记）")
    p.add_argument("--calibration-count", type=int, default=None,
                   help="手动指定开头要排除的校准点击数，跳过自动启发式识别（人工核对后覆盖用）")
    p.add_argument("--out-dir", default=None, help=f"派生结果目录（默认 {DEFAULT_OUT_DIR}）")
    args = p.parse_args(argv)

    if not Path(args.logfile).is_file():
        print(f"日志文件不存在：{args.logfile}", file=sys.stderr)
        return 2
    roi = None
    if args.roi:
        try:
            roi = _parse_roi(args.roi)
        except ValueError as exc:
            print(f"--roi 非法：{exc}", file=sys.stderr)
            return 2
    y_split = None if args.y_split is not None and args.y_split < 0 else args.y_split

    cluster_seeds = None
    cluster_labels = None
    if args.three_cluster:
        try:
            cluster_seeds = [_parse_point(s) for s in (args.seed_a, args.seed_b, args.seed_c)]
        except ValueError as exc:
            print(f"--seed-* 非法：{exc}", file=sys.stderr)
            return 2
        cluster_labels = [x.strip() for x in args.cluster_labels.split(",")]
        if len(cluster_labels) != 3:
            print("--cluster-labels 必须恰好 3 个逗号分隔的名字", file=sys.stderr)
            return 2

    summary = analyze(
        args.logfile, roi=roi, y_split=y_split,
        cluster_seeds=cluster_seeds, cluster_labels=cluster_labels,
        exclude_calibration=not args.no_exclude_calibration,
        calibration_count=args.calibration_count,
        ref_threshold=(args.time_threshold_ms, args.distance_threshold_px),
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    _print_report(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
