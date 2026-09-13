# This Python file uses the following encoding: utf-8
"""静态点击 ROI 尺寸普查（只读、不启动任何设备 / 服务 / 任务）。

用 AST 扫描仓库源码里所有 `RuleClick` / `RuleImage` / `RuleOcr` / `RuleGif` /
`RuleLongClick` 的**静态构造**，抽出会最终用于 `.coord()` → 点击的那个矩形
（RuleClick / RuleImage / RuleLongClick 取 `roi_front`；RuleOcr 取 `area` 当
`mode` 为 Full 否则取 `roi`；RuleGif 的 `roi_front` 运行时才填，静态视为 unknown），
统计 `width` / `height` / `short_side` / `long_side` / `area` / `aspect_ratio` 的分布，
再据此判断 Tiny / Small / Normal / Large 的尺寸边界。

限制：
- 纯 AST，不 import 任何 Task、不启动 Device / MuMu / OCR、无网络。
- 只认字面量四元组 ROI；表达式 / 变量 / 计算得到的 ROI 标 `unknown`，不猜。
- `RuleImage.roi_front` 的位置会被 `_update_roi_front` 在 match 后改写（标
  `dynamic_template`），但静态 `w/h`（≈模板尺寸）仍是点击目标尺寸的合理近似。
- `RuleOcr` 绝大多数是**读取**用途、并不点击；本工具照实抽出其静态尺寸，但主分布
  结论以 `RuleClick + RuleImage` 为准，`RuleOcr` 单独报告。
- 不做 consumer 出现次数统计（跨仓 `appear_then_click(Asset)` 的可靠归属需要类型推断，
  超出静态范围）；主结论基于 **unique ROI 定义**。

运行：``toolkit/python.exe dev_tools/click_roi_inventory.py``
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_ROOTS = ("tasks", "module/atom")
DEFAULT_OUT_DIR = _PROJECT_ROOT / "log" / "click_roi_analysis"

# 参与普查的 Rule 类型（会 .coord() → 点击）。RuleSwipe / RuleList / RuleAnimate 不算。
_CLICK_RULES = {"RuleClick", "RuleImage", "RuleOcr", "RuleGif", "RuleLongClick"}
_INHERITS_CLICK = {"RuleLongClick"}  # 继承 RuleClick.coord

# short_side 直方图固定桶（左闭右闭）。分布不适合时可 --buckets 调整。
_DEFAULT_BUCKETS = [
    (1, 8), (9, 16), (17, 24), (25, 32), (33, 40), (41, 48),
    (49, 64), (65, 80), (81, 96), (97, 128), (129, 192), (193, 10 ** 9),
]


# --------------------------------------------------------------------------------------
# AST 抽取
# --------------------------------------------------------------------------------------

@dataclass
class RoiRecord:
    file: str
    line: int
    symbol: str
    rule_type: str
    scope: str                      # 所属 task / module 目录名
    roi: list | None                # [x, y, w, h] 或 None（非字面量）
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    short_side: int | None = None
    long_side: int | None = None
    area: int | None = None
    aspect_ratio: float | None = None
    clickable_reason: str = ""       # RuleClick.coord / RuleImage.coord / RuleOcr.coord(area|roi) / ...
    roi_semantics: str = "unknown"   # fixed / dynamic_template / large_safe_area / private_area / unknown
    size_flag: str = "unknown"       # degenerate / very_thin / very_large / normal / unknown
    asset_file: str | None = None    # RuleImage 的 file= 模板图路径（原样字符串），其它 Rule 为 None
    has_click_consumer: bool = False  # 全仓有 appear_then_click / ui_click / .click(SYM) 引用（按符号名，近似）
    has_detect_consumer: bool = False  # 全仓有 appear / wait_until_appear 等引用


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _literal_roi(node: ast.AST):
    """把 AST 节点解析成 [x, y, w, h] 整数列表；不是 4 个整数字面量则返回 None。"""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    if len(node.elts) != 4:
        return None
    out = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, int) and not isinstance(elt.value, bool):
            out.append(int(elt.value))
        elif (isinstance(elt, ast.UnaryOp) and isinstance(elt.op, ast.USub)
              and isinstance(elt.operand, ast.Constant) and isinstance(elt.operand.value, int)):
            out.append(-int(elt.operand.value))
        else:
            return None
    return out


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _str_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scope_of(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if parts and parts[0] == "tasks" and len(parts) >= 2:
        return parts[1]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else "?"


def _classify_size(w, h) -> tuple[int | None, int | None, int | None, float | None, str]:
    if w is None or h is None:
        return None, None, None, None, "unknown"
    if w <= 0 or h <= 0:
        return min(w, h), max(w, h), w * h, None, "degenerate"
    short, long = min(w, h), max(w, h)
    area = w * h
    ar = round(long / short, 3)
    if short >= 300 or area >= 300000:
        flag = "very_large"
    elif ar >= 5.0:
        flag = "very_thin"
    else:
        flag = "normal"
    return short, long, area, ar, flag


def _rule_click_rect(rule_type: str, call: ast.Call):
    """返回 (roi_node_or_None, clickable_reason)。挑会进 .coord() 的那个矩形。"""
    if rule_type in ("RuleClick", "RuleLongClick", "RuleImage", "RuleGif"):
        node = _kw(call, "roi_front")
        return node, f"{rule_type}.coord(roi_front)"
    if rule_type == "RuleOcr":
        mode = _str_const(_kw(call, "mode")) or ""
        area_node = _kw(call, "roi")  # 默认非 Full → coord 用 self.roi
        reason = "RuleOcr.coord(roi)"
        if mode in ("Full", "FULL"):
            a = _kw(call, "area")
            if _literal_roi(a) is not None:
                area_node = a
                reason = "RuleOcr.coord(area, mode=Full)"
        return area_node, reason
    return None, rule_type


def extract_records_from_source(src: str, rel_path: str) -> list[RoiRecord]:
    """从一段源码抽取所有点击 Rule 的静态 ROI 记录。"""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    scope = _scope_of(rel_path)
    records: list[RoiRecord] = []

    # 先收集「NAME = RuleX(...)」/「NAME: T = RuleX(...)」的符号名
    call_symbols: dict[int, str] = {}
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        if target is not None and isinstance(getattr(node, "value", None), ast.Call):
            call_symbols[id(node.value)] = target

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        rule_type = _call_name(node.func)
        if rule_type not in _CLICK_RULES:
            continue
        symbol = call_symbols.get(id(node), "<inline>")
        roi_node, reason = _rule_click_rect(rule_type, node)
        roi = _literal_roi(roi_node) if roi_node is not None else None

        rec = RoiRecord(
            file=rel_path, line=node.lineno, symbol=symbol, rule_type=rule_type,
            scope=scope, roi=roi, clickable_reason=reason,
            asset_file=_str_const(_kw(node, "file")),
        )
        if roi is not None:
            rec.x, rec.y, rec.width, rec.height = roi
            rec.short_side, rec.long_side, rec.area, rec.aspect_ratio, rec.size_flag = \
                _classify_size(rec.width, rec.height)

        # roi_semantics
        if symbol and "RANDOM" in symbol and rule_type in ("RuleClick", "RuleLongClick"):
            rec.roi_semantics = "large_safe_area"
        elif roi is None:
            rec.roi_semantics = "private_area" if symbol == "<inline>" else "unknown"
        elif rule_type in ("RuleImage", "RuleGif"):
            rec.roi_semantics = "dynamic_template"
        else:
            rec.roi_semantics = "fixed"
        records.append(rec)
    return records


# 会「点击」某个 Rule 符号的调用（近似——同名跨文件符号会被一并算上，方向偏保守：
# 宁可多算「可能被点」，不漏）。
_CLICK_VERBS = (
    "appear_then_click", "wait_until_appear_then_click", "list_appear_click",
    "ui_click_until_disappear", "ui_click_until_appear_or_timeout",
    "ui_click_until_smt_disappear", "ui_clicks", "ui_click",
)
_CLICK_RE = re.compile(
    r"(?:%s)\s*\(\s*(?:[A-Za-z_][\w]*\.)*([A-Z][A-Z0-9_]+)\b" % "|".join(_CLICK_VERBS)
)
_DOTCLICK_RE = re.compile(r"\.click\s*\(\s*(?:[A-Za-z_][\w]*\.)*([A-Z][A-Z0-9_]+)\b")
_DETECT_RE = re.compile(
    r"(?:appear|wait_until_appear|wait_until_disappear|ocr_appear)\s*\(\s*"
    r"(?:[A-Za-z_][\w]*\.)*([A-Z][A-Z0-9_]+)\b"
)


def scan_consumers(roots: list[str]) -> tuple[set[str], set[str]]:
    """粗扫全仓 `.py`，返回 (被点击调用引用过的符号名集合, 被 appear 类调用引用过的符号名集合)。

    只按符号名匹配（不做类型推断），同名跨文件会合并——用于「这个尺寸的目标**是否可能**
    出现在点击链上」，方向偏保守。
    """
    clicked: set[str] = set()
    detected: set[str] = set()
    extra = ["tasks", "module", "script.py"]
    seen_files: set[Path] = set()
    for root in list(dict.fromkeys(list(roots) + extra)):
        base = _PROJECT_ROOT / root
        paths = [base] if base.is_file() else (base.rglob("*.py") if base.exists() else [])
        for py in paths:
            if py in seen_files or "__pycache__" in py.parts:
                continue
            seen_files.add(py)
            try:
                txt = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in _CLICK_RE.finditer(txt):
                clicked.add(m.group(1))
            for m in _DOTCLICK_RE.finditer(txt):
                clicked.add(m.group(1))
            for m in _DETECT_RE.finditer(txt):
                detected.add(m.group(1))
    return clicked, detected


def scan_repo(roots: list[str]) -> list[RoiRecord]:
    records: list[RoiRecord] = []
    for root in roots:
        base = _PROJECT_ROOT / root
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            rel = py.relative_to(_PROJECT_ROOT).as_posix()
            try:
                src = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            records.extend(extract_records_from_source(src, rel))
    return records


# --------------------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------------------

def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


_PCTS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def dist_stats(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    s = sorted(values)
    n = len(s)
    out = {
        "count": n,
        "min": s[0],
        "max": s[-1],
        "mean": round(sum(s) / n, 2),
        "median": round(_percentile(s, 0.5), 2),
    }
    for p in _PCTS:
        out[f"p{int(p * 100):02d}"] = round(_percentile(s, p), 2)
    return out


def histogram(values: list[int], buckets: list[tuple[int, int]]) -> list[dict]:
    out = []
    for lo, hi in buckets:
        c = sum(1 for v in values if lo <= v <= hi)
        label = f"{lo}-{hi}" if hi < 10 ** 8 else f"{lo}+"
        out.append({"bucket": label, "lo": lo, "hi": hi, "count": c})
    return out


def aspect_buckets(records: list[RoiRecord]) -> list[dict]:
    edges = [(0.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 5.0), (5.0, 10 ** 9)]
    out = []
    for lo, hi in edges:
        got = [r for r in records if r.aspect_ratio is not None and lo <= r.aspect_ratio < hi]
        label = f"{lo}-{hi}" if hi < 10 ** 8 else f">{lo}"
        out.append({
            "range": label, "count": len(got),
            "examples": [f"{r.symbol}({r.width}x{r.height})" for r in
                         sorted(got, key=lambda r: -r.aspect_ratio)[:4]],
        })
    return out


def _sized(records: list[RoiRecord]) -> list[RoiRecord]:
    """有有效正尺寸、可参与数值统计的记录。"""
    return [r for r in records if r.short_side is not None and r.short_side > 0]


def _row(r: RoiRecord) -> dict:
    return {
        "symbol": r.symbol, "rule_type": r.rule_type, "loc": f"{r.file}:{r.line}",
        "scope": r.scope, "roi": r.roi, "wxh": f"{r.width}x{r.height}",
        "short_side": r.short_side, "long_side": r.long_side, "area": r.area,
        "aspect_ratio": r.aspect_ratio, "semantics": r.roi_semantics, "flag": r.size_flag,
        "reason": r.clickable_reason,
    }


def build_summary(records: list[RoiRecord], buckets: list[tuple[int, int]]) -> dict:
    # 大安全区 / 私有动态 / OCR 单独分组
    large_safe = [r for r in records if r.roi_semantics == "large_safe_area"]
    ocr = [r for r in records if r.rule_type == "RuleOcr"]
    gif = [r for r in records if r.rule_type == "RuleGif"]
    # 主分布：RuleClick + RuleImage + RuleLongClick，排除大安全区，仅有效尺寸
    primary = _sized([
        r for r in records
        if r.rule_type in ("RuleClick", "RuleImage", "RuleLongClick")
        and r.roi_semantics != "large_safe_area"
    ])
    ss = [r.short_side for r in primary]

    # 「确认可点」子集：RuleClick / RuleLongClick 本身就是点击用；RuleImage 需全仓有点击调用方。
    confirmed = _sized([
        r for r in records
        if r.roi_semantics != "large_safe_area" and (
            r.rule_type in ("RuleClick", "RuleLongClick")
            or (r.rule_type == "RuleImage" and r.has_click_consumer)
        )
    ])
    css = [r.short_side for r in confirmed]

    by_type: dict = {}
    for rt in ("RuleClick", "RuleImage", "RuleOcr", "RuleGif", "RuleLongClick"):
        grp = _sized([r for r in records if r.rule_type == rt and r.roi_semantics != "large_safe_area"])
        by_type[rt] = {
            "unique_defs": sum(1 for r in records if r.rule_type == rt),
            "with_static_size": len(grp),
            "short_side": dist_stats([r.short_side for r in grp]),
        }

    summary = {
        "roots_scanned": None,  # 由 main 填
        "total_records": len(records),
        "unique_clickable_roi_defs": len(records),
        "by_rule_type_defs": {rt: sum(1 for r in records if r.rule_type == rt)
                              for rt in sorted({r.rule_type for r in records})},
        "semantics_breakdown": {sem: sum(1 for r in records if r.roi_semantics == sem)
                                for sem in sorted({r.roi_semantics for r in records})},
        "non_literal_roi_count": sum(1 for r in records if r.roi is None),
        "primary_distribution_note": (
            "主分布 = RuleClick + RuleImage + RuleLongClick，排除 C_*RANDOM* 大安全区、"
            "排除非字面量 ROI。RuleOcr 绝大多数是读取用途，单独统计。"
        ),
        "primary_count": len(primary),
        "short_side": dist_stats(ss),
        "short_side_histogram": histogram(ss, buckets),
        "confirmed_clickable": {
            "note": (
                "RuleClick / RuleLongClick（本身就是点击用）+ RuleImage 且全仓存在 "
                "appear_then_click / ui_click / .click(符号) 调用方；按符号名近似，方向偏保守。"
                "consumer 扫描未运行时该块只含 RuleClick / RuleLongClick。"
            ),
            "count": len(confirmed),
            "short_side": dist_stats(css),
            "short_side_histogram": histogram(css, buckets),
            "width": dist_stats([r.width for r in confirmed]),
            "height": dist_stats([r.height for r in confirmed]),
            "area": dist_stats([r.area for r in confirmed]),
            "aspect_ratio_buckets": aspect_buckets(confirmed),
            "smallest_30": [_row(r) for r in sorted(confirmed, key=lambda r: (r.short_side, r.area))[:30]],
        },
        "width": dist_stats([r.width for r in primary]),
        "height": dist_stats([r.height for r in primary]),
        "long_side": dist_stats([r.long_side for r in primary]),
        "area": dist_stats([r.area for r in primary]),
        "aspect_ratio_buckets": aspect_buckets(primary),
        "by_rule_type": by_type,
        "large_safe_area": {
            "count": len(large_safe),
            "short_side": dist_stats([r.short_side for r in _sized(large_safe)]),
            "items": [_row(r) for r in sorted(_sized(large_safe), key=lambda r: -(r.area or 0))],
        },
        "ocr_readonly_mostly": {
            "count": len(ocr),
            "with_static_size": len(_sized(ocr)),
            "short_side": dist_stats([r.short_side for r in _sized(ocr)]),
            "note": "RuleOcr 主要供 .ocr()/.ocr_appear() 读取，少量经 ocr_appear_click 点击；此处只是照实抽尺寸",
        },
        "gif": {"count": len(gif), "note": "RuleGif.roi_front 运行时才填，静态无尺寸"},
        "smallest_30": [_row(r) for r in sorted(primary, key=lambda r: (r.short_side, r.area))[:30]],
        "largest_20": [_row(r) for r in sorted(primary, key=lambda r: (-(r.area or 0), -(r.short_side or 0)))[:20]],
        "degenerate_or_extreme": [_row(r) for r in records
                                  if r.size_flag in ("degenerate", "very_thin", "very_large")],
    }

    # p25 / p50 / p75 附近样本
    if ss:
        s_sorted = sorted(primary, key=lambda r: r.short_side)
        for tag, p in (("p25", 0.25), ("p50", 0.50), ("p75", 0.75)):
            target = _percentile(sorted(ss), p)
            near = sorted(s_sorted, key=lambda r: abs(r.short_side - target))[:10]
            summary[f"near_{tag}_examples"] = {
                "target_short_side": round(target, 1),
                "items": [_row(r) for r in sorted(near, key=lambda r: r.short_side)],
            }
    return summary


# --------------------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------------------

def render_markdown(summary: dict) -> str:
    L = []
    a = L.append
    a("# 点击 ROI 尺寸普查\n")
    a(f"- 扫描根目录：`{summary['roots_scanned']}`")
    a(f"- unique 可点击 ROI 定义总数：**{summary['unique_clickable_roi_defs']}**")
    a(f"- 按 Rule 类型（定义数）：{summary['by_rule_type_defs']}")
    a(f"- ROI 语义分布：{summary['semantics_breakdown']}")
    a(f"- 非字面量 / 运行时 ROI：{summary['non_literal_roi_count']}")
    a(f"\n> {summary['primary_distribution_note']}")
    a(f"> 主分布参与统计的记录数：**{summary['primary_count']}**\n")

    a("## short_side 总体分布（主分布）\n")
    ss = summary["short_side"]
    a("| 指标 | 值 |\n|---|---|")
    for k in ("count", "min", "p05", "p10", "p25", "median", "p75", "p90", "p95", "p99", "max", "mean"):
        a(f"| {k} | {ss.get(k)} |")

    a("\n## short_side 直方图\n")
    a("| 桶(px) | 数量 |\n|---|---|")
    for b in summary["short_side_histogram"]:
        a(f"| {b['bucket']} | {b['count']} |")

    cc = summary.get("confirmed_clickable")
    if cc:
        a("\n## confirmed_clickable 子集（RuleClick/LongClick + 有点击调用方的 RuleImage）\n")
        a(f"> {cc['note']}")
        a(f"\n参与统计：**{cc['count']}**\n")
        s = cc["short_side"]
        a("| 指标 | short_side | width | height | area |\n|---|---|---|---|---|")
        for k in ("count", "min", "p05", "p25", "median", "p75", "p90", "p95", "max"):
            a(f"| {k} | {s.get(k)} | {cc['width'].get(k)} | {cc['height'].get(k)} | {cc['area'].get(k)} |")
        a("\n| 桶(px) | 数量 |\n|---|---|")
        for b in cc["short_side_histogram"]:
            a(f"| {b['bucket']} | {b['count']} |")

    a("\n## width / height / long_side / area（主分布）\n")
    a("| 指标 | count | p05 | p25 | median | p75 | p90 | p95 | max |\n|---|---|---|---|---|---|---|---|---|")
    for key in ("width", "height", "long_side", "area"):
        d = summary[key]
        a(f"| {key} | {d.get('count')} | {d.get('p05')} | {d.get('p25')} | {d.get('median')} "
          f"| {d.get('p75')} | {d.get('p90')} | {d.get('p95')} | {d.get('max')} |")

    a("\n## aspect_ratio 分布（long/short，主分布）\n")
    a("| 区间 | 数量 | 典型 |\n|---|---|---|")
    for r in summary["aspect_ratio_buckets"]:
        a(f"| {r['range']} | {r['count']} | {', '.join(r['examples'])} |")

    a("\n## 按 Rule 类型的 short_side\n")
    a("| type | 定义数 | 有静态尺寸 | p25 | median | p75 | p90 |\n|---|---|---|---|---|---|---|")
    for rt, d in summary["by_rule_type"].items():
        s = d["short_side"]
        a(f"| {rt} | {d['unique_defs']} | {d['with_static_size']} | {s.get('p25')} "
          f"| {s.get('median')} | {s.get('p75')} | {s.get('p90')} |")

    a("\n## C_*RANDOM* 大安全区（单独）\n")
    ls = summary["large_safe_area"]
    a(f"数量 {ls['count']}；short_side {ls['short_side']}\n")
    a("| symbol | scope | wxh | short | area |\n|---|---|---|---|---|")
    for it in ls["items"][:30]:
        a(f"| {it['symbol']} | {it['scope']} | {it['wxh']} | {it['short_side']} | {it['area']} |")

    a("\n## RuleOcr（读取为主，单独）\n")
    o = summary["ocr_readonly_mostly"]
    a(f"定义 {o['count']}，有静态尺寸 {o['with_static_size']}；short_side {o['short_side']}")
    a(f"\n> {o['note']}")

    def _table(title, items):
        a(f"\n## {title}\n")
        a("| symbol | type | wxh | short | long | area | AR | semantics | loc |\n|---|---|---|---|---|---|---|---|---|")
        for it in items:
            a(f"| {it['symbol']} | {it['rule_type']} | {it['wxh']} | {it['short_side']} "
              f"| {it['long_side']} | {it['area']} | {it['aspect_ratio']} | {it['semantics']} | {it['loc']} |")

    _table("short_side 最小 30 个（主分布）", summary["smallest_30"])
    if summary.get("confirmed_clickable"):
        _table("short_side 最小 30 个（confirmed_clickable 子集）",
               summary["confirmed_clickable"]["smallest_30"])
    for tag in ("p25", "p50", "p75"):
        blk = summary.get(f"near_{tag}_examples")
        if blk:
            _table(f"{tag} 附近（target short_side ≈ {blk['target_short_side']}）", blk["items"])
    _table("面积最大 20 个", summary["largest_20"])
    _table(f"异常 / 极端 ROI（{len(summary['degenerate_or_extreme'])} 个）",
           summary["degenerate_or_extreme"][:60])

    a("\n_本文件由 dev_tools/click_roi_inventory.py 生成；只读分析，未改任何 Asset / 生产代码。_")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="click_roi_inventory",
        description="静态普查仓库里所有可能用于点击的 Rule ROI 尺寸分布（只读）。",
    )
    p.add_argument("--roots", nargs="*", default=list(DEFAULT_ROOTS),
                   help=f"扫描的仓库子目录（默认 {list(DEFAULT_ROOTS)}）")
    p.add_argument("--out-dir", default=None, help=f"输出目录（默认 {DEFAULT_OUT_DIR}）")
    p.add_argument("--no-consumer-scan", action="store_true",
                   help="跳过全仓 consumer 粗扫（confirmed_clickable 将只含 RuleClick / RuleLongClick）")
    args = p.parse_args(argv)

    records = scan_repo(args.roots)

    clicked: set[str] = set()
    detected: set[str] = set()
    if not args.no_consumer_scan:
        clicked, detected = scan_consumers(list(args.roots))
        for r in records:
            if r.symbol and r.symbol != "<inline>":
                r.has_click_consumer = r.symbol in clicked
                r.has_detect_consumer = r.symbol in detected

    summary = build_summary(records, _DEFAULT_BUCKETS)
    summary["roots_scanned"] = args.roots
    summary["consumer_scan"] = {
        "ran": not args.no_consumer_scan,
        "clicked_symbols": len(clicked),
        "detected_symbols": len(detected),
        "note": "按符号名粗扫 tasks/ module/ script.py 的 appear_then_click / ui_click / .click(SYM) 与 appear(SYM)。",
    }

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "click_roi_inventory.json"
    md_path = out_dir / "click_roi_summary.md"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "records": [asdict(r) for r in records]},
                  fh, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(summary))

    ss = summary["short_side"]
    print("click ROI inventory")
    print(f"  unique clickable ROI defs: {summary['unique_clickable_roi_defs']}")
    print(f"  by type: {summary['by_rule_type_defs']}")
    print(f"  primary distribution n={summary['primary_count']}")
    print(f"  short_side  min={ss.get('min')} p05={ss.get('p05')} p10={ss.get('p10')} "
          f"p25={ss.get('p25')} median={ss.get('median')} p75={ss.get('p75')} "
          f"p90={ss.get('p90')} p95={ss.get('p95')} max={ss.get('max')}")
    print(f"  histogram: " + "  ".join(f"{b['bucket']}:{b['count']}" for b in summary["short_side_histogram"]))
    cc = summary.get("confirmed_clickable") or {}
    ccs = cc.get("short_side", {})
    print(f"  confirmed_clickable n={cc.get('count')}  "
          f"short_side p25={ccs.get('p25')} median={ccs.get('median')} p75={ccs.get('p75')} "
          f"p90={ccs.get('p90')} max={ccs.get('max')}")
    cs = summary.get("consumer_scan", {})
    print(f"  consumer_scan ran={cs.get('ran')} clicked_symbols={cs.get('clicked_symbols')} "
          f"detected_symbols={cs.get('detected_symbols')}")
    print(f"  large_safe_area: {summary['large_safe_area']['count']}   "
          f"RuleOcr: {summary['ocr_readonly_mostly']['count']}   "
          f"non-literal ROI: {summary['non_literal_roi_count']}")
    print(f"  output: {json_path}")
    print(f"          {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
