# This Python file uses the following encoding: utf-8
"""TouchSwipeModel 的 MuMu Level C 专用测试工具（一次性、非循环、只测输入层）。

用途只有一个：**在 MuMu 的 Android 设置长列表页面上，执行一条 `TouchSwipeModel` 轨迹，
并把「本次实际发送的同一条轨迹」存成 PNG 轨迹图 + JSON。**

硬边界（本工具**不**做）：
- 不修改 `TouchSwipeModel` / minitouch trajectory executor / `Control.swipe_trajectory` 生产逻辑；
- 不启动阴阳师 / 不做页面导航 / 不点击设置页条目 / 不调 OCR / FrameWait / KekkaiUtilize；
- 不自动循环——单次执行后退出；
- 不根据结果自动改 `TouchSwipeParams` 默认值、不自动开 `tail_correction`。

设备初始化沿用项目标准路径（`module.device.device.Device(config=...)`），不自造 adb /
socket / minitouch / config parser；config 名校验复用 `dev_tools/manual_click_recorder.py`
的 `resolve_config_name`（= `ConfigManager.validate_config_name`）。

运行（Windows / PowerShell 或 cmd）：

    toolkit\\python.exe dev_tools\\test_touch_swipe_mumu.py --config oas1

可选：

    toolkit\\python.exe dev_tools\\test_touch_swipe_mumu.py --config oas1 ^
        --start 520,560 --end 520,300 --output-dir log/touch_swipe_test --verbose

PNG / JSON / MuMu 实际执行三者对应**完全同一条 trajectory**（`model.generate` 只调一次）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from module.base.utils.random import random_int  # noqa: E402
from module.device.touch_swipe_model import TouchSwipeModel, TouchSwipeParams  # noqa: E402

# 一次性开发测试默认坐标：适合 1280x720 MuMu 的 Android 设置类长列表，纵向向上滑约 260px。
# **仅开发测试用**，不进任何生产配置、不写进 TouchSwipeModel 默认参数。
_DEV_DEFAULT_START = (520, 560)
_DEV_DEFAULT_END = (520, 300)

_DEFAULT_OUTPUT_DIR = "log/touch_swipe_test"
_CONTROL_NAME = "TOUCH_SWIPE_LEVEL_C"

# --curve 需要曲率采样落在 model.generate 的第一次 randint 上，这要求 curve_cap>=1，
# 即 straight distance 大致 >= 9px（min(max_curve_px, dist*curve_px_ratio) >= 1）。
_FORCED_CURVE_MIN_DISTANCE = 10.0


# ======================================================================================
# 纯逻辑部分（无设备 / 无 cv2 窗口依赖，单元测试直接覆盖）
# ======================================================================================

def parse_point(text: str) -> tuple[int, int]:
    """把 ``"520,560"`` 解析成 ``(520, 560)``。非法格式抛 ``ValueError``（argparse 会显示）。"""
    parts = str(text).replace(" ", "").split(",")
    if len(parts) != 2:
        raise ValueError(f"坐标必须形如 X,Y：{text!r}")
    try:
        x, y = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"坐标必须是两个整数：{text!r}")
    return x, y


def make_test_id(now: datetime) -> str:
    """生成本次运行的唯一 id，如 ``20260904_101523``。"""
    return now.strftime("%Y%m%d_%H%M%S")


def trajectory_segments(trajectory: list) -> list:
    """把 trajectory 拆成「有确定 executor 时间的 MOVE→MOVE 段」，一次性对齐
    from/to point、dt、distance、speed —— 其它统计与 PNG C 都复用它。

    executor（`Minitouch._swipe_minitouch_trajectory_run`）真实命令流：

        DOWN(p0) COMMIT | SEND
        MOVE(p1) COMMIT WAIT(dt1)  MOVE(p2) COMMIT WAIT(dt2)  ...
        MOVE(p_{n-1}) COMMIT WAIT(dt_{n-1}) | SEND
        UP COMMIT | SEND

    ``WAIT(dt_i)`` 夹在「MOVE 到 p_i」与「MOVE 到 p_{i+1}」之间 ——
    即 ``dt_i`` 是「到达 p_i 之后、移动到 p_{i+1} 之前的停留」（与 D018 一致）。
    因此 **段 ``p_i → p_{i+1}`` 的时间就是 ``dt_i``**，``speed = 距离 / dt_i``，
    ``i`` 取 ``1 .. n-2``（共 ``n-2`` 段）。

    **排除**：
    - ``p0 → p1``（DOWN → 第一次 MOVE）：``p0.dt = 0`` 被执行层忽略，两 batch 之间只有
      ``minitouch_send`` 的协议等待 ``DEFAULT_DELAY``，**不属于 trajectory dt 契约**，
      不给它伪造 segment speed。
    - ``dt_{n-1}``（最后一个 dt）：是「最后一次 MOVE → UP 前的停留」，没有「下一个
      MOVE」，不构成 MOVE→MOVE 段，**不拿来算前一段速度**。
    """
    pts = [(int(x), int(y), int(dt)) for x, y, dt in trajectory]
    segs = []
    for i in range(1, len(pts) - 1):
        x0, y0, dt_i = pts[i]
        x1, y1, _dt_next = pts[i + 1]
        dist = math.hypot(x1 - x0, y1 - y0)
        segs.append({
            "from_index": i,
            "to_index": i + 1,
            "distance_px": round(dist, 4),
            "dt_ms": dt_i,                      # 到达 p_i 后、移动到 p_{i+1} 前的 WAIT
            "speed_px_per_ms": round(dist / dt_i, 4) if dt_i > 0 else 0.0,
        })
    return segs


def trajectory_stats(trajectory: list) -> dict:
    """从**同一条**已生成 trajectory 算统计量（不重新生成、不改动 trajectory）。

    trajectory: ``[(x, y, dt_ms), ...]``，首点 dt 为 0（落点），其余 dt > 0。
    speed 相关全部走 `trajectory_segments`（executor 时间对齐）；``total_dt_ms`` 仍是
    「trajectory 内所有显式 WAIT 之和」（含最后一个 pre-UP dwell），不是物理墙钟总时长。
    """
    pts = [(int(x), int(y), int(dt)) for x, y, dt in trajectory]
    if len(pts) < 2:
        raise ValueError("trajectory 至少要 2 个点")

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    start_x, start_y = pts[0][0], pts[0][1]
    end_x, end_y = pts[-1][0], pts[-1][1]

    straight = math.hypot(end_x - start_x, end_y - start_y)
    adj_dist = [
        math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        for i in range(1, len(pts))
    ]
    trajectory_dts = [pts[i][2] for i in range(1, len(pts))]     # dt_1 .. dt_{n-1}（含末段）
    path_len = float(sum(adj_dist))                              # 全路径（含 p0→p1）
    total_dt = int(sum(dt for _, _, dt in pts))                  # 所有显式 WAIT 之和

    segs = trajectory_segments(pts)
    seg_speeds = [s["speed_px_per_ms"] for s in segs]
    seg_dist_sum = sum(s["distance_px"] for s in segs)
    seg_dt_sum = sum(s["dt_ms"] for s in segs)

    # 到 start->end 基准直线的垂直偏移（曲率幅度）
    if straight > 1e-9:
        ux, uy = (end_x - start_x) / straight, (end_y - start_y) / straight
        lateral = [abs((x - start_x) * (-uy) + (y - start_y) * ux) for x, y in zip(xs, ys)]
    else:
        lateral = [0.0 for _ in pts]

    return {
        "point_count": len(pts),
        "segment_count": len(segs),
        "total_dt_ms": total_dt,
        "straight_distance_px": round(straight, 2),
        "actual_path_length_px": round(path_len, 2),
        "max_dx_px": max(abs(x - start_x) for x in xs),
        "max_lateral_offset_px": round(max(lateral), 2),
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "min_dt_ms": min(trajectory_dts),
        "max_dt_ms": max(trajectory_dts),
        # speed 走 executor 对齐的段（段 p_i→p_{i+1} 用 dt_i）；排除 p0→p1 与 dt_last
        "avg_speed_px_per_ms": round(seg_dist_sum / seg_dt_sum, 4) if seg_dt_sum else 0.0,
        "max_speed_px_per_ms": round(max(seg_speeds), 4) if seg_speeds else 0.0,
        "segment_speeds_px_per_ms": seg_speeds,
    }


def build_record(
    *,
    test_id: str,
    config_name: str,
    start: tuple[int, int],
    end: tuple[int, int],
    curve_mode: str,
    trajectory: list,
    params: TouchSwipeParams,
    generated_at: datetime,
    executed: bool = False,
) -> dict:
    """组装写盘 JSON：本次完整原始 trajectory + 从真实对象读到的参数 + 统计量。"""
    stats = trajectory_stats(trajectory)
    return {
        "test_id": test_id,
        "config": config_name,
        "control_name": _CONTROL_NAME,
        "curve_mode": curve_mode,
        "start": [int(start[0]), int(start[1])],
        "end": [int(end[0]), int(end[1])],
        "generated_at": generated_at.astimezone().isoformat(timespec="seconds"),
        "executed": bool(executed),
        # 统计
        "point_count": stats["point_count"],
        "total_dt_ms": stats["total_dt_ms"],
        "straight_distance_px": stats["straight_distance_px"],
        "actual_path_length_px": stats["actual_path_length_px"],
        "max_dx_px": stats["max_dx_px"],
        "max_lateral_offset_px": stats["max_lateral_offset_px"],
        "min_x": stats["min_x"],
        "max_x": stats["max_x"],
        "min_y": stats["min_y"],
        "max_y": stats["max_y"],
        "min_dt_ms": stats["min_dt_ms"],
        "max_dt_ms": stats["max_dt_ms"],
        "avg_speed_px_per_ms": stats["avg_speed_px_per_ms"],
        "max_speed_px_per_ms": stats["max_speed_px_per_ms"],
        # 本次实际使用的参数（从 model.params 真实对象读，不复制硬编码）
        "params": asdict(params),
        # 原始 trajectory（与 PNG / 实际发送完全同一份）
        "trajectory": [
            {"index": i, "x": int(x), "y": int(y), "dt_ms": int(dt)}
            for i, (x, y, dt) in enumerate(trajectory)
        ],
    }


def save_json(path: Path, record: dict) -> None:
    """把一次测试记录写成 JSON（建目录、UTF-8、不覆盖靠 test_id 唯一）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)


# ---------------------------------- PNG 绘制 -------------------------------------------

# MuMu 逻辑屏幕尺寸（**仅本 dev tool 的可视化参数**，不进 TouchSwipeParams / 生产）
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

_BG = (255, 255, 255)
_FG = (40, 40, 40)
_GRID = (210, 210, 210)
_SCREEN_EDGE = (120, 120, 120)
_BBOX = (170, 200, 170)     # BGR：轨迹 bounding box（淡绿灰）
_BASELINE = (150, 150, 150)
_CURVE = (200, 90, 40)      # BGR：实际轨迹（偏蓝）
_DOWN = (60, 160, 60)       # 起点绿
_UP = (60, 60, 210)         # 终点红
_ACCENT = (180, 120, 40)


def _lin(v, v0, v1, p0, p1):
    if v1 - v0 == 0:
        return (p0 + p1) / 2.0
    return p0 + (v - v0) * (p1 - p0) / (v1 - v0)


def _text(img, s, org, scale=0.5, color=_FG, thick=1):
    cv2.putText(img, s, (int(org[0]), int(org[1])), cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thick, cv2.LINE_AA)


def _panel(img, x0, y0, x1, y1, title):
    cv2.rectangle(img, (x0, y0), (x1, y1), _GRID, 1)
    _text(img, title, (x0 + 6, y0 + 18), 0.5, _FG, 1)


def _dash(img, a, b, color, seg=8, gap=6):
    total = math.hypot(b[0] - a[0], b[1] - a[1])
    if total < 1:
        return
    ux, uy = (b[0] - a[0]) / total, (b[1] - a[1]) / total
    d = 0.0
    while d < total:
        p = (int(a[0] + ux * d), int(a[1] + uy * d))
        q = (int(a[0] + ux * min(d + seg, total)), int(a[1] + uy * min(d + seg, total)))
        cv2.line(img, p, q, color, 1, cv2.LINE_AA)
        d += seg + gap


def trajectory_bbox(trajectory) -> tuple[int, int, int, int]:
    """轨迹（含起终点）的整数包围盒 ``(min_x, min_y, max_x, max_y)``。"""
    xs = [int(p["x"]) if isinstance(p, dict) else int(p[0]) for p in trajectory]
    ys = [int(p["y"]) if isinstance(p, dict) else int(p[1]) for p in trajectory]
    return min(xs), min(ys), max(xs), max(ys)


def fit_screen_rect(panel_rect) -> tuple[float, float, float, float]:
    """在 ``panel_rect=(x0,y0,x1,y1)`` 内取一块**保持 1280:720 (16:9) 比例、居中**的
    子矩形，用作 Screen View 的绘图区。返回 ``(fx0, fy0, fx1, fy1)``（float）。

    因为返回的子矩形本身就是 16:9，``screen_to_panel`` 里 x / y 用的像素比例天然相等
    —— 不做任何按轨迹跨度的独立自适应缩放。
    """
    px0, py0, px1, py1 = panel_rect
    avail_w = float(px1 - px0)
    avail_h = float(py1 - py0)
    scale = min(avail_w / SCREEN_WIDTH, avail_h / SCREEN_HEIGHT)
    w = SCREEN_WIDTH * scale
    h = SCREEN_HEIGHT * scale
    fx0 = px0 + (avail_w - w) / 2.0
    fy0 = py0 + (avail_h - h) / 2.0
    return (fx0, fy0, fx0 + w, fy0 + h)


def screen_to_panel(x, y, fit_rect) -> tuple[int, int]:
    """屏幕坐标 (x∈[0,1280], y∈[0,720], Y 向下为正) → ``fit_rect`` 内像素点。

    固定用 ``[0, SCREEN_WIDTH] × [0, SCREEN_HEIGHT]`` 作为定义域，**与本次轨迹的
    x_span / y_span 无关**；``fit_rect`` 已是 16:9，故 x、y 比例相同（1:1 视觉）。
    """
    fx0, fy0, fx1, fy1 = fit_rect
    px = fx0 + (float(x) / SCREEN_WIDTH) * (fx1 - fx0)
    py = fy0 + (float(y) / SCREEN_HEIGHT) * (fy1 - fy0)   # Y 向下：screen y=0 → 顶部
    return (int(round(px)), int(round(py)))


def zoom_transform(trajectory, panel_rect, *, margin_frac=0.16):
    """按轨迹 bbox **自适应**（x / y 各自缩放，用于放大细节）映射到 ``panel_rect``。

    返回 ``(transform, bbox)``：``transform(x, y) -> (px, py)``，``bbox`` 是未加 margin
    的原始 ``(min_x, min_y, max_x, max_y)``。这是「放大细节」视图，**不是屏幕比例**。
    """
    bx0, by0, bx1, by1 = trajectory_bbox(trajectory)
    px0, py0, px1, py1 = panel_rect
    xspan = max(bx1 - bx0, 1)
    yspan = max(by1 - by0, 1)
    mx = xspan * margin_frac
    my = yspan * margin_frac
    dx0, dx1 = bx0 - mx, bx1 + mx
    dy0, dy1 = by0 - my, by1 + my

    def transform(x, y):
        rx = _lin(x, dx0, dx1, px0, px1)
        ry = _lin(y, dy0, dy1, py0, py1)
        return (int(round(rx)), int(round(ry)))

    return transform, (bx0, by0, bx1, by1)


def _plot_series(img, region, values, title, x_label="index"):
    """在 region=(x0,y0,x1,y1) 内画一条「x_label vs value」折线 + 轴。title 自带单位。"""
    x0, y0, x1, y1 = region
    _panel(img, x0, y0, x1, y1, title)
    pad_l, pad_r, pad_t, pad_b = 52, 14, 40, 26
    ax0, ay0, ax1, ay1 = x0 + pad_l, y0 + pad_t, x1 - pad_r, y1 - pad_b
    cv2.rectangle(img, (ax0, ay0), (ax1, ay1), _GRID, 1)
    if not values:
        _text(img, "(no data)", (ax0 + 8, (ay0 + ay1) // 2))
        return
    vmax = max(values)
    vmin = min(values)
    if vmax == vmin:
        vmax += 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        px = _lin(i, 0, max(1, n - 1), ax0, ax1)
        py = _lin(v, vmin, vmax, ay1, ay0)
        pts.append((int(px), int(py)))
    for a, b in zip(pts, pts[1:]):
        cv2.line(img, a, b, _CURVE, 1, cv2.LINE_AA)
    for p in pts:
        cv2.circle(img, p, 2, _ACCENT, -1, cv2.LINE_AA)
    _text(img, f"{vmax:.2f}", (x0 + 4, ay0 + 4), 0.4)
    _text(img, f"{vmin:.2f}", (x0 + 4, ay1 + 4), 0.4)
    _text(img, x_label, ((ax0 + ax1) // 2 - 4 * len(x_label), y1 - 8), 0.4)


def _draw_screen_view(img, panel_rect, traj, record):
    """A1：1280x720 真实屏幕坐标，1:1 视觉比例，Y 向下为正，不做按轨迹跨度的独立缩放。"""
    x0, y0, x1, y1 = panel_rect
    _panel(img, x0, y0, x1, y1,
           "A1. Screen View  1280x720  (1:1 aspect, real screen scale, Y down)")
    inner = (x0 + 48, y0 + 36, x1 - 16, y1 - 30)
    fit = fit_screen_rect(inner)
    fx0, fy0, fx1, fy1 = (int(round(v)) for v in fit)

    # 淡灰网格 + 刻度（screen x=0/320/640/960/1280，y=0/180/360/540/720）
    for gx in range(0, SCREEN_WIDTH + 1, 320):
        px, _ = screen_to_panel(gx, 0, fit)
        cv2.line(img, (px, fy0), (px, fy1), _GRID, 1, cv2.LINE_AA)
        _text(img, str(gx), (px - 12, fy1 + 16), 0.38, _FG, 1)
    for gy in range(0, SCREEN_HEIGHT + 1, 180):
        _, py = screen_to_panel(0, gy, fit)
        cv2.line(img, (fx0, py), (fx1, py), _GRID, 1, cv2.LINE_AA)
        _text(img, str(gy), (fx0 - 34, py + 4), 0.38, _FG, 1)
    # 屏幕边框
    cv2.rectangle(img, (fx0, fy0), (fx1, fy1), _SCREEN_EDGE, 1)

    # 轨迹 bbox（淡色矩形，仅参考，不据此缩放）
    bx0, by0, bx1, by1 = trajectory_bbox(traj)
    q0 = screen_to_panel(bx0, by0, fit)
    q1 = screen_to_panel(bx1, by1, fit)
    cv2.rectangle(img, q0, q1, _BBOX, 1)

    sx, sy, ex, ey = traj[0][0], traj[0][1], traj[-1][0], traj[-1][1]
    a = screen_to_panel(sx, sy, fit)
    b = screen_to_panel(ex, ey, fit)
    _dash(img, a, b, _BASELINE)
    pts = [screen_to_panel(x, y, fit) for x, y, _ in traj]
    for p, qq in zip(pts, pts[1:]):
        cv2.line(img, p, qq, _CURVE, 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(img, p, 2, _ACCENT, -1, cv2.LINE_AA)
    cv2.circle(img, pts[0], 5, _DOWN, -1, cv2.LINE_AA)
    _text(img, "DOWN", (pts[0][0] + 8, pts[0][1] + 4), 0.42, _DOWN, 1)
    cv2.circle(img, pts[-1], 5, _UP, -1, cv2.LINE_AA)
    _text(img, "UP", (pts[-1][0] + 8, pts[-1][1] + 4), 0.42, _UP, 1)
    mid_a = (int((a[0] + b[0]) / 2 - (b[0] - a[0]) * 0.14),
             int((a[1] + b[1]) / 2 - (b[1] - a[1]) * 0.14))
    mid_b = (int((a[0] + b[0]) / 2 + (b[0] - a[0]) * 0.14),
             int((a[1] + b[1]) / 2 + (b[1] - a[1]) * 0.14))
    cv2.arrowedLine(img, mid_a, mid_b, _BASELINE, 2, cv2.LINE_AA, tipLength=0.4)


def _draw_zoom_view(img, panel_rect, traj, record):
    """A2：按轨迹 bbox 自适应放大（x/y 各自缩放），仅用于看曲率 / MOVE 细节。"""
    x0, y0, x1, y1 = panel_rect
    _panel(img, x0, y0, x1, y1,
           "A2. ZOOMED VIEW  (auto-fit to trajectory bbox -- NOT screen scale)")
    inner = (x0 + 16, y0 + 34, x1 - 16, y1 - 34)
    cv2.rectangle(img, (inner[0], inner[1], inner[2], inner[3]), _GRID, 1)

    tf, (bx0, by0, bx1, by1) = zoom_transform(traj, inner)
    a, b = tf(traj[0][0], traj[0][1]), tf(traj[-1][0], traj[-1][1])
    _dash(img, a, b, _BASELINE)
    pts = [tf(x, y) for x, y, _ in traj]
    for p, q in zip(pts, pts[1:]):
        cv2.line(img, p, q, _CURVE, 2, cv2.LINE_AA)
    step = max(1, len(pts) // 8)
    for i, p in enumerate(pts):
        cv2.circle(img, p, 3, _ACCENT, -1, cv2.LINE_AA)
        if i % step == 0 and 0 < i < len(pts) - 1:
            _text(img, str(i), (p[0] + 5, p[1] - 4), 0.36, _FG, 1)
    cv2.circle(img, pts[0], 6, _DOWN, -1, cv2.LINE_AA)
    _text(img, "DOWN", (pts[0][0] + 8, pts[0][1] + 4), 0.42, _DOWN, 1)
    cv2.circle(img, pts[-1], 6, _UP, -1, cv2.LINE_AA)
    _text(img, "UP", (pts[-1][0] + 8, pts[-1][1] + 4), 0.42, _UP, 1)
    _text(img, f"x span={bx1 - bx0}px   y span={by1 - by0}px   "
               f"max lateral offset={record['max_lateral_offset_px']}px   "
               f"max |dx|={record['max_dx_px']}px",
          (inner[0] + 4, inner[3] + 22), 0.4)


def draw_trajectory_png(path: Path, record: dict, *, size=(1400, 900)) -> None:
    """按**同一份** record["trajectory"] 画一张轨迹检查图（不重新生成轨迹）。

    A1. Screen View 1280x720（真实屏幕坐标 + 1:1 视觉比例 + Y 向下为正）；
    A2. Zoomed View（按 bbox 自适应放大，仅看曲率 / MOVE 细节）；
    B. 每段 dt；C. 每段速度；D. 文本统计。
    """
    w, h = size
    img = np.full((h, w, 3), _BG, dtype=np.uint8)

    traj = [(int(p["x"]), int(p["y"]), int(p["dt_ms"])) for p in record["trajectory"]]

    _draw_screen_view(img, (16, 16, 704, 476), traj, record)
    _draw_zoom_view(img, (16, 492, 704, 884), traj, record)

    # B：每个 MOVE 点（i>=1）到达后、下一次移动前的 WAIT（= trajectory dt_i，含末点 pre-UP dwell）
    move_dt = [p[2] for p in traj[1:]]
    _plot_series(img, (720, 16, 1384, 284), move_dt,
                 "B. WAIT after MOVE  (trajectory dt_ms, point i>=1)",
                 x_label="point index (i>=1)")
    # C：段 p_i -> p_{i+1} 的速度 = distance / dt_i（executor 时间对齐；排除 p0->p1 与 dt_last）
    speeds = [s["speed_px_per_ms"] for s in trajectory_segments(traj)]
    _plot_series(img, (720, 300, 1384, 568), speeds,
                 "C. speed per SEGMENT  (p_i->p_i+1 = dist / dt_i, px/ms)",
                 x_label="segment index (i = from-point)")

    dx0, dy0, dx1, dy1 = 720, 584, 1384, 884
    _panel(img, dx0, dy0, dx1, dy1, "D. stats")
    lines = [
        f"test_id: {record['test_id']}",
        f"config: {record['config']}    curve_mode: {record['curve_mode']}",
        f"start: {tuple(record['start'])}    end: {tuple(record['end'])}",
        f"point_count: {record['point_count']}    total_dt_ms: {record['total_dt_ms']}",
        f"straight_distance_px: {record['straight_distance_px']}",
        f"actual_path_length_px: {record['actual_path_length_px']}",
        f"max_lateral_offset_px: {record['max_lateral_offset_px']}    max_dx_px: {record['max_dx_px']}",
        f"min_dt_ms: {record['min_dt_ms']}    max_dt_ms: {record['max_dt_ms']}",
        f"avg_speed: {record['avg_speed_px_per_ms']} px/ms    max_speed: {record['max_speed_px_per_ms']} px/ms",
        f"tail_correction_enable: {record['params']['tail_correction_enable']}",
        "NOTE: screen Y downward-positive; an up-swipe goes upward in A1 / A2",
    ]
    for i, s in enumerate(lines):
        _text(img, s, (dx0 + 10, dy0 + 30 + i * 20), 0.45, _FG, 1)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), img):
        raise RuntimeError(f"cv2.imwrite 失败：{path}")


# ---------------------------- --curve 的 dev 专用随机源 -------------------------------

class ForcedCurveRng:
    """dev 专用：把 `TouchSwipeModel.generate` 的**第一次** ``randint``（曲率幅度采样）
    钉成固定值 —— left→最小值、right→最大值、straight→0；其余（逐段 dt 抖动）交给项目
    公共 `random_int`。

    只通过 `TouchSwipeModel(rng=...)` 已有的注入点工作，**不改任何生产代码**。前提：
    straight distance 足够大使曲率采样确实是第一次 ``randint``（`main` 里已按
    ``_FORCED_CURVE_MIN_DISTANCE`` 拦截过小距离），且默认参数下 ``tail_correction`` 关闭。
    """

    def __init__(self, mode: str):
        if mode not in ("left", "straight", "right"):
            raise ValueError(f"curve mode 必须是 left/straight/right：{mode!r}")
        self.mode = mode
        self._used = False

    def randint(self, lo: int, hi: int) -> int:
        if not self._used:
            self._used = True
            if self.mode == "left":
                return int(lo)
            if self.mode == "right":
                return int(hi)
            return 0
        return random_int(int(lo), int(hi))


# ======================================================================================
# 设备胶水 + CLI（不做单元测试；设备 import 惰性化）
# ======================================================================================

def _resolve_config_name(name: str) -> str:
    from dev_tools.manual_click_recorder import resolve_config_name

    return resolve_config_name(name)


def init_device(config_name: str):
    """沿用项目标准路径构造设备：`Device(config=<name>)`。

    连接一个**已在运行**的 MuMu 实例（`Device.__init__` 在模拟器未运行时会尝试
    `emulator_start()`，本工具不主动启动游戏，但连接已运行的模拟器是标准行为）。
    """
    from module.device.device import Device

    return Device(config=config_name)


def _build_model(curve_mode: str) -> TouchSwipeModel:
    if curve_mode == "auto":
        return TouchSwipeModel()                     # 生产随机路径
    return TouchSwipeModel(rng=ForcedCurveRng(curve_mode))


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="test_touch_swipe_mumu",
        description=(
            "TouchSwipeModel MuMu Level C 一次性测试工具：在 Android 设置长列表页面上"
            "执行一条自定义 minitouch 轨迹，并把同一条轨迹存成 PNG + JSON。不循环、不进游戏。"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--config", required=True, help="完整 config 名（如 oas1）")
    p.add_argument(
        "--start", default=None,
        help=f"起点 X,Y（默认 {_DEV_DEFAULT_START[0]},{_DEV_DEFAULT_START[1]}，"
             f"**仅开发测试坐标**，不进生产配置）",
    )
    p.add_argument(
        "--end", default=None,
        help=f"终点 X,Y（默认 {_DEV_DEFAULT_END[0]},{_DEV_DEFAULT_END[1]}，同上）",
    )
    p.add_argument("--output-dir", default=_DEFAULT_OUTPUT_DIR,
                   help=f"输出目录（默认 {_DEFAULT_OUTPUT_DIR}）")
    p.add_argument(
        "--curve", choices=("left", "straight", "right"), default=None,
        help="可选 dev：钉住本次曲率方向（经 TouchSwipeModel 已有的 rng= 注入点，不改生产代码）。\n"
             "不传则走生产随机路径，多跑几次自然覆盖 左弯/近直线/右弯。",
    )
    p.add_argument("--verbose", action="store_true", help="打印完整 trajectory")
    return p.parse_args(argv)


def _print_preview(record: dict, png_path: Path, json_path: Path, verbose: bool) -> None:
    print("=" * 70)
    print("TouchSwipe Level C Test")
    print("=" * 70)
    print(f"  config:              {record['config']}")
    print(f"  start:               {tuple(record['start'])}")
    print(f"  end:                 {tuple(record['end'])}")
    print(f"  curve_mode:          {record['curve_mode']}")
    print(f"  point_count:         {record['point_count']}")
    print(f"  total_dt_ms:         {record['total_dt_ms']}")
    print(f"  straight_distance:   {record['straight_distance_px']} px")
    print(f"  actual_path_length:  {record['actual_path_length_px']} px")
    print(f"  max_dx:              {record['max_dx_px']} px")
    print(f"  max_lateral_offset:  {record['max_lateral_offset_px']} px")
    print(f"  min_dt / max_dt:     {record['min_dt_ms']} / {record['max_dt_ms']} ms")
    print(f"  avg_speed:           {record['avg_speed_px_per_ms']} px/ms")
    print(f"  max_speed:           {record['max_speed_px_per_ms']} px/ms")
    print(f"  tail_correction:     {record['params']['tail_correction_enable']}")
    print()
    print(f"  trajectory image:    {png_path}")
    print(f"  trajectory json:     {json_path}")
    if verbose:
        print()
        for e in record["trajectory"]:
            print(f"    #{e['index']:>3}  x={e['x']:>4}  y={e['y']:>4}  dt_ms={e['dt_ms']:>3}")
    print()
    print("  请先在 MuMu 中打开：Android 设置 -> 应用 / 应用管理 / 其它可上下滚动的长列表，")
    print("  把列表停在中间、页面停稳。")
    print("  查看上面的 trajectory PNG 确认轨迹形状无误。")
    print()


def main(argv=None) -> int:
    if sys.platform != "win32":
        print("test_touch_swipe_mumu 仅支持 Windows（MuMu）。", file=sys.stderr)
        return 2

    args = _parse_args(argv)

    try:
        config_name = _resolve_config_name(args.config)
    except Exception as exc:
        print(f"config 名非法：{exc}", file=sys.stderr)
        return 2

    try:
        start = parse_point(args.start) if args.start else _DEV_DEFAULT_START
        end = parse_point(args.end) if args.end else _DEV_DEFAULT_END
    except ValueError as exc:
        print(f"坐标非法：{exc}", file=sys.stderr)
        return 2

    curve_mode = args.curve or "auto"
    if curve_mode != "auto":
        if math.hypot(end[0] - start[0], end[1] - start[1]) < _FORCED_CURVE_MIN_DISTANCE:
            print(f"--curve 需要起终点距离 >= {_FORCED_CURVE_MIN_DISTANCE:.0f}px，"
                  f"当前太小；去掉 --curve 走随机路径。", file=sys.stderr)
            return 2

    # 1) 先连设备（失败就早退，不生成任何文件）
    try:
        device = init_device(config_name)
    except Exception as exc:
        print(f"[!] 设备不可用：{type(exc).__name__}: {exc}", file=sys.stderr)
        print("    请确认对应 MuMu 实例已启动、config 正确。本工具不会自动启动游戏。",
              file=sys.stderr)
        return 3

    method = device.config.script.device.control_method
    if method != "minitouch":
        print(f"[!] 当前 control_method = {method!r}，swipe_trajectory 只支持 minitouch。",
              file=sys.stderr)
        return 3

    # 2) 生成**唯一一条** trajectory（之后 PNG / JSON / 实际发送都用它，不再重新生成）
    now = datetime.now()
    test_id = make_test_id(now)
    model = _build_model(curve_mode)
    try:
        trajectory = model.generate(start, end)
    except ValueError as exc:
        print(f"[!] 轨迹生成失败：{exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = Path(_PROJECT_ROOT) / out_dir
    png_path = out_dir / f"touch_swipe_{test_id}.png"
    json_path = out_dir / f"touch_swipe_{test_id}.json"

    record = build_record(
        test_id=test_id, config_name=config_name, start=start, end=end,
        curve_mode=curve_mode, trajectory=trajectory, params=model.params,
        generated_at=now, executed=False,
    )
    save_json(json_path, record)
    draw_trajectory_png(png_path, record)

    _print_preview(record, png_path, json_path, args.verbose)

    # 3) 人工确认后执行一次（不循环）
    try:
        answer = input("  按 Enter 开始执行一次 swipe，输入 q 退出： ").strip().lower()
    except EOFError:
        answer = "q"
    if answer == "q":
        print("已退出，未执行 swipe（PNG / JSON 已保留）。")
        return 0

    print()
    print(f"  执行：device.swipe_trajectory(<{record['point_count']} pts>, "
          f"control_name={_CONTROL_NAME!r}) ...")
    try:
        device.swipe_trajectory(trajectory, control_name=_CONTROL_NAME)
    except Exception as exc:
        print(f"[!] swipe_trajectory 执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    # 回写 executed 标记（仍是同一条 trajectory）
    record["executed"] = True
    save_json(json_path, record)

    print()
    print("  测试完成（单次执行，已退出，不再重复）")
    print(f"  PNG:  {png_path}")
    print(f"  JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
