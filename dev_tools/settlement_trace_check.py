# This Python file uses the following encoding: utf-8
"""GeneralBattle 结算点击 Level C 验收分析器（只读，不接设备）—— Settlement Contract v3。

读 `log/behavior/<config>_<date>.jsonl`（BehaviorTrace v1），抽出三个结算安全区
`random_default` / `random_save_right` / `random_save_bottom` 的点击，做验收所需的
**静态 sanity**：

- 每个区域点击的 count / mean x·y / min·max / 分位 / ROI-relative (u, v) / 是否落在 ROI 内；
- 连续 settlement 点击的时间间隔分布（默认间隔 0.7~1.0s，因 polling / 调度 / 截图 实际会
  略大于配置值——只检查**不会明显早于**合理下限，不检查上限）；
- 是否存在明显 < 合理阈值的高速重复点击、多次点击坐标是否每次重新采样。

Contract v3 下采样是整 ROI 均匀（`LEGACY_UNIFORM`），无 HABIT profile / safe-margin——
「Safe ROI」即区域 ROI 本身。**本工具不校验**「通用结果强制两次点击」的时序结构与
「奖励布局 80/20」的分流比例——那属于新契约的 Level C 验收设计，另行处理。

不训练 / 不拟合任何 profile（见 `docs/DECISIONS.md` D014）。

运行：``toolkit/python.exe dev_tools/settlement_trace_check.py log/behavior/oas1_2026-09-03.jsonl``
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 三个结算安全区 ROI 与默认间隔范围，从生产源码取（导入不接设备）。
# Contract v3 采样整 ROI 均匀，无 safe-margin —— Safe ROI == ROI（margin 全 0）。
try:
    from tasks.Component.GeneralBattle.general_battle import GeneralBattle  # noqa: E402

    _REGION_ROI = {
        "random_default": tuple(GeneralBattle.C_RANDOM_DEFAULT.roi_front),
        "random_save_right": tuple(GeneralBattle.C_RANDOM_SAVE_RIGHT.roi_front),
        "random_save_bottom": tuple(GeneralBattle.C_RANDOM_SAVE_BOTTOM.roi_front),
    }
    _INTERVAL_RANGE = tuple(GeneralBattle.SETTLEMENT_CLICK_INTERVAL_RANGE)
except Exception:  # 源码结构变了也要能跑（用当前已知常量兜底）
    _REGION_ROI = {
        "random_default": (742, 430, 362, 230),
        "random_save_right": (1185, 209, 87, 441),
        "random_save_bottom": (819, 639, 425, 69),
    }
    _INTERVAL_RANGE = (0.7, 1.0)

_SETTLEMENT_TARGETS = ("random_default", "random_save_right", "random_save_bottom")
_NO_MARGIN = (0.0, 0.0)
_SHAPE_LETTER = {"random_default": "D", "random_save_right": "R", "random_save_bottom": "B"}
# 连续结算点击间隔明显小于该值即视为「高速重复」——取默认下限的一半留足 polling / 调度裕度。
_MIN_REASONABLE_GAP = round(_INTERVAL_RANGE[0] * 0.5, 3)
# 相邻结算点击间隔超过该值就当作跨了一段（页面已推进 / 新战斗）。
_SEGMENT_SPLIT_GAP = 12.0


@dataclass
class Click:
    ts: datetime
    target: str
    x: int
    y: int
    task: str
    elapsed_ms: float | None


def _parse_line(line: str) -> Click | None:
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if obj.get("event") != "ACTION" or obj.get("action") != "click":
        return None
    target = obj.get("target", "")
    if target not in _SETTLEMENT_TARGETS:
        return None
    extra = obj.get("extra") or {}
    if "x" not in extra or "y" not in extra:
        return None
    try:
        ts = datetime.fromisoformat(obj["ts"])
    except (KeyError, ValueError):
        return None
    return Click(ts=ts, target=target, x=int(extra["x"]), y=int(extra["y"]),
                 task=obj.get("task", ""), elapsed_ms=obj.get("elapsed_ms"))


def load_clicks(path: Path) -> list[Click]:
    out: list[Click] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            c = _parse_line(line)
            if c is not None:
                out.append(c)
    out.sort(key=lambda c: c.ts)
    return out


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _safe_roi(roi, margin) -> tuple[int, int, int, int]:
    x, y, w, h = roi
    dx, dy = round(margin[0] * w), round(margin[1] * h)
    return x + dx, y + dy, w - 2 * dx, h - 2 * dy


def coord_stats(clicks: list[Click], roi, margin) -> dict:
    if not clicks:
        return {"count": 0}
    xs = sorted(c.x for c in clicks)
    ys = sorted(c.y for c in clicks)
    rx, ry, rw, rh = roi
    sx, sy, sw, sh = _safe_roi(roi, margin)
    inside_roi = sum(1 for c in clicks if rx <= c.x < rx + rw and ry <= c.y < ry + rh)
    inside_safe = sum(1 for c in clicks if sx <= c.x < sx + sw and sy <= c.y < sy + sh)
    distinct_xy = len({(c.x, c.y) for c in clicks})
    us = [(c.x - rx) / rw for c in clicks]
    vs = [(c.y - ry) / rh for c in clicks]
    n = len(clicks)

    def _d(vals):
        s = sorted(vals)
        return {
            "min": round(s[0], 2), "max": round(s[-1], 2),
            "mean": round(sum(s) / n, 2),
            "p05": round(_pct(s, 0.05), 2), "p25": round(_pct(s, 0.25), 2),
            "p50": round(_pct(s, 0.50), 2), "p75": round(_pct(s, 0.75), 2),
            "p95": round(_pct(s, 0.95), 2),
        }

    return {
        "count": n,
        "roi": list(roi),
        "safe_roi": [sx, sy, sw, sh],
        "x": _d(xs), "y": _d(ys),
        "u_mean": round(sum(us) / n, 4), "v_mean": round(sum(vs) / n, 4),
        "u_range": [round(min(us), 4), round(max(us), 4)],
        "v_range": [round(min(vs), 4), round(max(vs), 4)],
        "inside_roi": inside_roi, "outside_roi": n - inside_roi,
        "inside_safe_roi": inside_safe, "outside_safe_roi": n - inside_safe,
        # 每次到点都重新采样 → 多次点击应有多个不同坐标（n>=3 时若全同一点是可疑的）。
        "distinct_xy": distinct_xy,
    }


def segment_clicks(clicks: list[Click]) -> list[list[Click]]:
    """按相邻间隔把结算点击切成「结算段」（间隔过大 = 页面已推进 / 新战斗）。"""
    segments: list[list[Click]] = []
    cur: list[Click] = []
    for c in clicks:
        if cur and (c.ts - cur[-1].ts).total_seconds() > _SEGMENT_SPLIT_GAP:
            segments.append(cur)
            cur = []
        cur.append(c)
    if cur:
        segments.append(cur)
    return segments


def click_intervals(segments: list[list[Click]]) -> dict:
    """每段内相邻结算点击的时间间隔（同一段 = 未跨页 / 未新战斗）。"""
    gaps: list[float] = []
    fast: list[dict] = []
    for si, seg in enumerate(segments):
        for a, b in zip(seg, seg[1:]):
            g = round((b.ts - a.ts).total_seconds(), 3)
            gaps.append(g)
            if g < _MIN_REASONABLE_GAP:
                fast.append({"segment": si, "gap_s": g,
                             "ts": b.ts.isoformat(timespec="milliseconds"),
                             "targets": f"{a.target}->{b.target}"})
    gaps_sorted = sorted(gaps)
    summary = {}
    if gaps_sorted:
        summary = {
            "count": len(gaps_sorted),
            "min": gaps_sorted[0], "max": gaps_sorted[-1],
            "mean": round(sum(gaps_sorted) / len(gaps_sorted), 3),
            "p05": round(_pct(gaps_sorted, 0.05), 3),
            "p50": round(_pct(gaps_sorted, 0.50), 3),
            "p95": round(_pct(gaps_sorted, 0.95), 3),
        }
    return {
        "expected_min_interval_s": _INTERVAL_RANGE[0],
        "expected_max_interval_s": _INTERVAL_RANGE[1],
        "min_reasonable_gap_s": _MIN_REASONABLE_GAP,
        "gap_summary": summary,
        "fast_repeat_gaps": fast,
        "note": ("实际间隔因 polling / 调度 / 截图 一般会略大于配置的 "
                 f"{_INTERVAL_RANGE[0]}~{_INTERVAL_RANGE[1]}s，不检查上限；"
                 f"只标出明显 < {_MIN_REASONABLE_GAP}s 的高速重复。"),
    }


def build_report(path: Path) -> dict:
    clicks = load_clicks(path)
    segments = segment_clicks(clicks)
    tasks = sorted({c.task for c in clicks if c.task})
    span = None
    if clicks:
        span = [clicks[0].ts.isoformat(timespec="milliseconds"),
                clicks[-1].ts.isoformat(timespec="milliseconds")]
    rep = {
        "source": str(path),
        "tasks_seen": tasks,
        "time_span": span,
        "total_settlement_clicks": len(clicks),
        "segments": len(segments),
        "intervals": click_intervals(segments),
        "segment_shapes": ["".join(_SHAPE_LETTER.get(c.target, "?") for c in seg)
                           for seg in segments],
    }
    for tgt in _SETTLEMENT_TARGETS:
        rep[tgt] = coord_stats([c for c in clicks if c.target == tgt], _REGION_ROI[tgt], _NO_MARGIN)
    verdict, problems = _verdict(rep)
    rep["auto_verdict"] = verdict
    rep["auto_problems"] = problems
    return rep


def _verdict(rep: dict) -> tuple[str, list[str]]:
    problems = []
    if rep["total_settlement_clicks"] == 0:
        return "NO_DATA", ["未在该 trace 里找到任何结算安全区点击"]
    if rep["intervals"]["fast_repeat_gaps"]:
        problems.append(
            f"存在明显 < {rep['intervals']['min_reasonable_gap_s']}s 的高速重复结算点击："
            f"{len(rep['intervals']['fast_repeat_gaps'])} 处")
    for tgt in _SETTLEMENT_TARGETS:
        st = rep[tgt]
        if st.get("count") and st.get("outside_roi"):
            problems.append(f"{tgt} 有 {st['outside_roi']}/{st['count']} 个点落在 ROI 外")
        if st.get("count", 0) >= 3 and st.get("distinct_xy") == 1:
            problems.append(f"{tgt} 点了 {st['count']} 次但坐标完全相同（应每次重新采样）")
    return ("FAIL" if problems else "OK"), problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="settlement_trace_check",
        description="GeneralBattle 结算点击 Level C 验收分析（只读 BehaviorTrace jsonl，Contract v2）。",
    )
    p.add_argument("trace", help="log/behavior/<config>_<date>.jsonl 路径")
    p.add_argument("--json", action="store_true", help="只输出 JSON")
    args = p.parse_args(argv)

    path = Path(args.trace)
    if not path.is_file():
        print(f"trace 文件不存在：{path}", file=sys.stderr)
        return 2

    rep = build_report(path)
    verdict, problems = rep["auto_verdict"], rep["auto_problems"]

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    print(f"settlement trace check  ({rep['source']})")
    print(f"  tasks: {rep['tasks_seen']}   span: {rep['time_span']}")
    print(f"  settlement clicks: {rep['total_settlement_clicks']}  segments: {rep['segments']}")
    for tgt in _SETTLEMENT_TARGETS:
        st = rep[tgt]
        if not st.get("count"):
            print(f"  {tgt}: (none)")
            continue
        print(f"  {tgt}: n={st['count']}  distinct_xy={st['distinct_xy']}  "
              f"x[{st['x']['min']},{st['x']['max']}] mean {st['x']['mean']}  "
              f"y[{st['y']['min']},{st['y']['max']}] mean {st['y']['mean']}")
        print(f"      ROI-relative mean (u,v)=({st['u_mean']},{st['v_mean']})  "
              f"inside_roi {st['inside_roi']}/{st['count']}")
    iv = rep["intervals"]
    print(f"  click intervals: expected {iv['expected_min_interval_s']}~{iv['expected_max_interval_s']}s  "
          f"summary={iv['gap_summary']}")
    if iv["fast_repeat_gaps"]:
        print(f"  fast repeat gaps (< {iv['min_reasonable_gap_s']}s): {len(iv['fast_repeat_gaps'])}")
        for g in iv["fast_repeat_gaps"]:
            print(f"    - {g['ts']}  {g['gap_s']}s  {g['targets']}")
    print(f"  segment shapes: {rep['segment_shapes']}")
    print(f"  AUTO VERDICT: {verdict}")
    for pr in problems:
        print(f"    - {pr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
