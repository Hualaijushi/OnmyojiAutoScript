# This Python file uses the following encoding: utf-8
"""大尺寸点击 ROI 人工审查目录生成器（只读，不改任何生产代码 / Asset）。

在 `dev_tools/click_roi_inventory.py` 的普查结果之上：

1. 按 `short_side >= LARGE_SHORT_SIDE`（默认 96px，仅几何标签，**不是生产分类逻辑**）筛出大 ROI；
2. 用 AST 建「符号 → 真实消费者」索引（点击调用 / 检测调用 / 裸引用），据此剔除纯检测 ROI、
   标出零消费者的死资产；
3. 给每条大 ROI 一个**初步**语义猜测（large_button / wide_card / large_safe_region /
   settlement_region / random_region / fullscreen_dismiss / fixed_business_area /
   dynamic_template / unknown）、Point vs Region 目标类型、P0/P1/P2 优先级、人工检查重点；
4. 输出 `log/click_roi_analysis/large_click_roi_review.{md,json}` 供用户按编号逐项确认。

所有 `semantic_guess` / `priority` / `target_kind` 都是**启发式初判**，`review_status` 一律
`pending`，等用户人工看图后确认；本工具不替用户做最终视觉判断，也不写任何生产默认值。

运行：``toolkit/python.exe dev_tools/large_click_roi_review.py``
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dev_tools import click_roi_inventory as cri  # noqa: E402

# 「Large」的几何门槛。只是本轮人工审查的取样线，**不写进任何生产分类逻辑**。
LARGE_SHORT_SIDE = 96

DEFAULT_OUT_DIR = _PROJECT_ROOT / "log" / "click_roi_analysis"
CONSUMER_ROOTS = ("tasks", "module", "script.py")

# --------------------------------------------------------------------------------------
# 消费者索引（AST，能跨行；比 inventory 里的正则粗扫准）
# --------------------------------------------------------------------------------------

# 会真正产生点击坐标的调用
_CLICK_VERBS = {
    "click", "long_click", "appear_then_click", "wait_until_appear_then_click",
    "list_appear_click", "ocr_appear_click", "ui_click", "ui_clicks",
    "ui_click_until_disappear", "ui_click_until_appear_or_timeout",
    "ui_click_until_smt_disappear", "click_until_disappear",
}
# 只读取 / 判断，不点击
_DETECT_VERBS = {
    "appear", "wait_until_appear", "wait_until_disappear", "wait_until_stable",
    "ocr", "ocr_appear", "list_find", "image_color_count", "appear_color",
}
# 直接取坐标（等价点击意图）
_COORD_ATTRS = {"coord", "coord_more"}
# 间接点击：`random.choice([C_A, C_B, ...])` 选一个安全区再 click——本仓库里这类
# choice/choices/sample 只用于挑点击区域（`GameUi/default_pages.py` 的 `random_click`
# 与 `handle_activity_overlay` 都是这个形状），所以按「可能被点」计入。
_INDIRECT_CLICK_VERBS = {"choice", "choices", "sample"}
# 算「有点击消费者」的 Usage.kind
_CLICK_KINDS = ("click", "coord", "indirect_click")


def _is_symbol_name(name: str) -> bool:
    """Asset 符号命名约定：全大写 + 下划线 + 数字，且至少 2 个字符。"""
    return bool(name) and len(name) >= 2 and name.upper() == name and name[0].isalpha() \
        and all(c.isalnum() or c == "_" for c in name)


def _symbols_in(node: ast.AST) -> list[tuple[str, str | None]]:
    """收集表达式里的 Asset 符号，返回 `(符号名, 限定前缀或 None)`。

    `GeneralBattleAssets.C_RANDOM_LEFT` → `("C_RANDOM_LEFT", "GeneralBattleAssets")`；
    `self.C_X` → `("C_X", "self")`；裸 `C_X` → `("C_X", None)`。限定前缀用来把同名符号
    精确归属到定义它的那个 Assets 类（见 `build_assets_class_map`）。
    """
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and _is_symbol_name(sub.attr):
            qual = sub.value.id if isinstance(sub.value, ast.Name) else None
            out.append((sub.attr, qual))
        elif isinstance(sub, ast.Name) and _is_symbol_name(sub.id):
            out.append((sub.id, None))
    return out


def build_assets_class_map(roots=("tasks", "module")) -> dict[str, str]:
    """`{Assets 类名: 定义它的 assets.py 相对路径}`，用于按限定前缀精确归属消费者。"""
    out: dict[str, str] = {}
    for root in roots:
        base = _PROJECT_ROOT / root
        if not base.exists():
            continue
        for py in sorted(base.rglob("assets.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, SyntaxError):
                continue
            rel = py.relative_to(_PROJECT_ROOT).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    out[node.name] = rel
    return out


@dataclass
class Usage:
    file: str
    line: int
    func: str          # 所在函数 / 方法（近似：最内层 def）
    verb: str          # 调用名
    kind: str          # click / indirect_click / detect / coord
    qualifier: str | None = None   # 限定前缀：XxxAssets / self / None


class _ConsumerVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, index: dict):
        self.rel = rel_path
        self.index = index
        self.stack: list[str] = []

    # --- 作用域 ---
    def _scoped(self, node):
        self.stack.append(getattr(node, "name", "?"))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _scoped
    visit_AsyncFunctionDef = _scoped
    visit_ClassDef = _scoped

    def _add(self, symbol: str, qual: str | None, line: int, verb: str, kind: str):
        self.index.setdefault(symbol, []).append(
            Usage(file=self.rel, line=line, func=self.stack[-1] if self.stack else "<module>",
                  verb=verb, kind=kind, qualifier=qual)
        )

    def visit_Call(self, node: ast.Call):
        verb = cri._call_name(node.func)
        # `SYM.coord()` / `self.C_X.coord()`
        if verb in _COORD_ATTRS and isinstance(node.func, ast.Attribute):
            for s, q in _symbols_in(node.func.value):
                self._add(s, q, node.lineno, verb, "coord")
        elif verb in _CLICK_VERBS or verb in _DETECT_VERBS or verb in _INDIRECT_CLICK_VERBS:
            if verb in _CLICK_VERBS:
                kind = "click"
            elif verb in _INDIRECT_CLICK_VERBS:
                kind = "indirect_click"
            else:
                kind = "detect"
            seen = set()
            for arg in list(node.args) + [k.value for k in node.keywords]:
                for s, q in _symbols_in(arg):
                    if (s, q) not in seen:
                        seen.add((s, q))
                        self._add(s, q, node.lineno, verb, kind)
        self.generic_visit(node)


def index_source(src: str, rel_path: str, index: dict | None = None) -> dict[str, list[Usage]]:
    """把一段源码的消费者用法并入 `index`（不给就新建）。供单测与 `build_consumer_index` 复用。"""
    if index is None:
        index = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return index
    _ConsumerVisitor(rel_path, index).visit(tree)
    return index


def build_consumer_index(roots=CONSUMER_ROOTS, skip_assets=True) -> dict[str, list[Usage]]:
    """扫全仓 `.py`，返回 `{符号名: [Usage, ...]}`。

    `skip_assets` 跳过自动生成的 `assets.py`（那里只有定义，没有消费）。同名符号跨 task 会
    合并——本工具用它做「是否有人点它」的近似判断，方向偏保守（宁可多算「可能被点」）。
    """
    index: dict[str, list[Usage]] = {}
    seen: set[Path] = set()
    for root in roots:
        base = _PROJECT_ROOT / root
        paths = [base] if base.is_file() else (sorted(base.rglob("*.py")) if base.exists() else [])
        for py in paths:
            if py in seen or "__pycache__" in py.parts:
                continue
            if skip_assets and py.name == "assets.py":
                continue
            seen.add(py)
            try:
                src = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            index_source(src, py.relative_to(_PROJECT_ROOT).as_posix(), index)
    return index


def build_reference_index(roots=CONSUMER_ROOTS, skip_assets=True) -> dict[str, int]:
    """`{符号名: 在非 assets.py 源码中被提及的次数}`——用来识别「零消费者死资产」。"""
    counts: dict[str, int] = {}
    seen: set[Path] = set()
    for root in roots:
        base = _PROJECT_ROOT / root
        paths = [base] if base.is_file() else (sorted(base.rglob("*.py")) if base.exists() else [])
        for py in paths:
            if py in seen or "__pycache__" in py.parts:
                continue
            if skip_assets and py.name == "assets.py":
                continue
            seen.add(py)
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, SyntaxError):
                continue
            for s, _q in _symbols_in(tree):
                counts[s] = counts.get(s, 0) + 1
    return counts


# --------------------------------------------------------------------------------------
# 语义初判 / 优先级
# --------------------------------------------------------------------------------------

_SEM_LABELS = {
    "large_button": "A. 大按钮",
    "wide_card": "B. 卡片 / 大条目",
    "large_safe_region": "C. 页面大安全区",
    "settlement_region": "D. 战斗结算 / 奖励推进区",
    "random_region": "E. 设计为随机散点的区域",
    "fullscreen_dismiss": "F. 整屏 / 大面板任意点关闭",
    "fixed_business_area": "G. 业务要求固定的大区域",
    "dynamic_template": "H. RuleImage 动态 roi_front",
    "unknown": "I. 源码不足以判断，需人工查看",
}

_SETTLEMENT_HINTS = ("REWARD", "SETTLE", "VICTORY", "DEFEAT", "WIN", "RESULT",
                     "CONTINUE", "AWARD", "HARVEST", "GET_REWARD", "_RD")
_FIXED_BUSINESS_HINTS = ("LOGIN", "SVR", "SERVER", "ACCOUNT", "BIND_PHONE", "USER_CENTER")
_CARD_HINTS = ("CARD", "SELECT", "SHIKIGAMI", "SCROLL", "PARTITION", "CHOICE",
               "PRESET_TEAM", "AREA_", "ITEM", "RUN_", "GR_C_", "HSELECT", "LEFT_", "D_")


def _guess_semantics(rec: dict, usages: list[Usage]) -> str:
    sym = rec["symbol"] or ""
    w, h = rec["width"], rec["height"]
    if "RANDOM" in sym:
        return "random_region"
    if w >= 1200 and h >= 640:
        return "fullscreen_dismiss"
    if any(k in sym for k in _SETTLEMENT_HINTS):
        return "settlement_region"
    if any(k in sym for k in _FIXED_BUSINESS_HINTS):
        return "fixed_business_area"
    if rec["rule_type"] == "RuleImage":
        return "dynamic_template"
    if "SAFE" in sym or "MARK_AREA" in sym or sym.endswith("_AREA"):
        return "large_safe_region"
    if any(k in sym for k in _CARD_HINTS):
        return "wide_card"
    if rec["rule_type"] in ("RuleClick", "RuleLongClick"):
        # 近方形且不算特别大 → 更像一个实体大按钮
        if (rec["aspect_ratio"] or 9) < 2.0 and (rec["area"] or 0) < 40000:
            return "large_button"
        return "unknown"
    return "unknown"


# Region Target = 「一片可推进的区域」；Point Target = 「一个实体控件」
_REGION_SEMANTICS = {"large_safe_region", "settlement_region", "random_region",
                     "fullscreen_dismiss", "fixed_business_area"}


def _target_kind(semantics: str) -> str:
    return "region" if semantics in _REGION_SEMANTICS else "point"


# P0 优先看的 scope（战后 / 奖励 / 高频日常大区）
_P0_SCOPES = {"Component", "GlobalGame", "Dokan", "Exploration", "MetaDemon",
              "ActivityShikigami", "SixRealms", "GameUi"}


def _priority(rec: dict, semantics: str, has_click: bool) -> str:
    sym = rec["symbol"] or ""
    if semantics in ("random_region", "settlement_region", "fullscreen_dismiss"):
        return "P0"
    if semantics == "large_safe_region":
        return "P0" if rec["scope"] in _P0_SCOPES else "P1"
    if semantics == "fixed_business_area":
        return "P1"
    if semantics in ("large_button", "wide_card"):
        return "P1"
    if semantics == "dynamic_template":
        # 大模板一般是检测面板，除非确有点击消费者
        return "P1" if has_click and (rec["short_side"] or 0) >= 120 else "P2"
    return "P2" if not has_click else "P1"


_BASE_QUESTIONS = {
    "random_region": [
        "这个区域是真的要「全区域均匀散点」，还是只是历史命名？",
        "整块 ROI 都能安全点击吗？有没有按钮 / 奖励内容侵入？",
        "如果只有一部分安全，应该缩小到哪一块？",
        "保持 Uniform，还是允许个人热点（右下偏好）？",
    ],
    "settlement_region": [
        "结算 / 奖励页面里，这块区域每一处都能安全点击推进吗？",
        "是否有「再次挑战 / 分享 / 领取」等误触风险控件落在 ROI 内？",
        "是否应该只用右半部分 / 下半部分？",
        "适合套个人热点（preferred center），还是必须保持 Uniform？",
        "是否需要重新截图重新框 ROI？",
    ],
    "fullscreen_dismiss": [
        "真的整屏任意点都能关闭 / 推进吗？",
        "这个 ROI 是「点击用」还是其实只是「检测整屏」？",
        "如果确实要点，应该限制到哪个安全子区？",
    ],
    "large_safe_region": [
        "整个 ROI 都可安全点击吗？",
        "是否有内容 / 按钮侵入需要避开？",
        "可以扩大吗？应该缩小吗？",
        "适合 preferred center 还是保持 Uniform？",
    ],
    "fixed_business_area": [
        "业务上是否要求固定点某个位置（不能个性化）？",
        "ROI 是否偏大、实际只应点其中一小块？",
    ],
    "large_button": [
        "这是明确的实体大按钮吗？",
        "ROI 是否比按钮实际可视范围大 / 小？",
        "适合 preferred center（个人热点）吗？",
    ],
    "wide_card": [
        "这是卡片 / 条目整体，还是卡片里的某个控件？",
        "点击卡片的任意位置都有效吗？",
        "是否有「已选中 / 锁定」角标需要避开？",
        "适合 preferred center 吗？",
    ],
    "dynamic_template": [
        "`roi_front` 在 match 后会被改写——这个尺寸是模板本身大，还是检测面板大？",
        "实际消费者是点它还是只 appear() 检测它？",
        "如果确实点击，命中后的动态 ROI 尺寸是多少（需真机 runtime_roi_probe 确认）？",
    ],
    "unknown": [
        "这个 ROI 对应哪个页面 / 控件？",
        "是按钮还是区域？",
        "当前 ROI 是否合理，是否需要重新截图框选？",
    ],
}


def _review_questions(semantics: str, rec: dict, has_click: bool, has_any_ref: bool) -> list[str]:
    qs = list(_BASE_QUESTIONS.get(semantics, _BASE_QUESTIONS["unknown"]))
    if not has_any_ref:
        qs.insert(0, "全仓无任何引用——这是死资产吗？可以直接跳过 / 删除吗？")
    elif not has_click:
        qs.insert(0, "只有检测（appear 类）消费者、没有点击消费者——确认它其实不点吗？")
    if (rec["aspect_ratio"] or 0) >= 4:
        qs.append(f"宽高比 {rec['aspect_ratio']}，是窄长条——短边方向是否足够安全？")
    return qs


# --------------------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------------------

@dataclass
class ReviewItem:
    id: str
    symbol: str
    rule_type: str
    file: str
    line: int
    scope: str
    roi: list
    width: int
    height: int
    short_side: int
    long_side: int
    area: int
    aspect_ratio: float
    roi_semantics: str            # 来自 inventory（fixed / dynamic_template / large_safe_area ...）
    dynamic_roi_front: bool
    semantic_guess: str
    semantic_label: str
    target_kind: str              # point / region
    priority: str
    consumers: list = field(default_factory=list)      # [{file,line,func,verb,kind}]
    click_consumer_count: int = 0
    detect_consumer_count: int = 0
    consumer_status: str = ""     # HAS_CLICK_CONSUMER / DETECT_ONLY / UNUSED
    consumer_attribution: str = "exact"   # exact / ambiguous（同名符号在多个 scope 重复定义）
    defined_in_scopes: list = field(default_factory=list)
    goes_through_click_sampler: bool = True
    current_strategy: str = "LEGACY_UNIFORM"
    resource_path: str | None = None
    resource_exists: bool | None = None
    review_questions: list = field(default_factory=list)
    review_status: str = "pending"


def _res_path(asset_file: str | None):
    if not asset_file:
        return None, None
    rel = asset_file.lstrip("./").replace("\\", "/")
    return rel, (_PROJECT_ROOT / rel).is_file()


def attribute_usages(usages: list[Usage], rec: dict, class_map: dict[str, str],
                     ambiguous: bool) -> tuple[list[Usage], str]:
    """把按符号名取到的 usages 归属到**这一条**定义。

    消费者写 `GeneralBattleAssets.C_RANDOM_LEFT` 时，限定前缀能精确指向定义它的 assets.py；
    写 `self.C_X`（mixin 继承）或裸名时无法区分，只能保留。返回 `(usages, attribution)`。
    """
    if not ambiguous:
        return usages, "exact"
    kept, saw_qualified_other = [], False
    for u in usages:
        target = class_map.get(u.qualifier or "")
        if target is None:                       # self. / 裸名 / 未知前缀 → 无法区分，保留
            kept.append(u)
        elif target == rec["file"]:              # 限定前缀正好指向本条所在的 assets.py
            kept.append(u)
        else:
            saw_qualified_other = True
    # 全部 usage 都能被限定前缀解析掉 → 归属其实是精确的
    if kept and all(class_map.get(u.qualifier or "") == rec["file"] for u in kept):
        return kept, "exact_by_qualifier"
    if not kept and saw_qualified_other:
        return [], "exact_by_qualifier"
    return kept, "ambiguous"


def build_items(records: list[dict], index: dict[str, list[Usage]],
                refs: dict[str, int], threshold=LARGE_SHORT_SIDE,
                class_map: dict[str, str] | None = None) -> list[ReviewItem]:
    """筛出大 ROI 并组装审查条目。纯检测 RuleImage / RuleOcr 不进主清单（见 `excluded`）。"""
    # 同名符号在多个 scope 重复定义时（如 C_RANDOM_LEFT 在 Component / GameUi / MartialArts
    # 各有一份），消费者索引按名字合并、无法区分是哪一份——标 ambiguous 提醒人工核对。
    scopes_of: dict[str, set] = {}
    for rec in records:
        if rec.get("symbol"):
            scopes_of.setdefault(rec["symbol"], set()).add(rec["scope"])

    items: list[ReviewItem] = []
    for rec in records:
        ss = rec.get("short_side")
        if ss is None or ss < threshold:
            continue
        if rec["rule_type"] == "RuleOcr":       # 读取用途，单独排除项
            continue
        usages, attribution = attribute_usages(
            index.get(rec["symbol"], []), rec, class_map or {},
            len(scopes_of.get(rec["symbol"], ())) > 1)
        clicks = [u for u in usages if u.kind in _CLICK_KINDS]
        detects = [u for u in usages if u.kind == "detect"]
        has_click = bool(clicks)
        # RuleImage 必须确认有点击消费者才进主清单；RuleClick/RuleLongClick 天生是点击用
        if rec["rule_type"] == "RuleImage" and not has_click:
            continue
        semantics = _guess_semantics(rec, usages)
        res, exists = _res_path(rec.get("asset_file"))
        items.append(ReviewItem(
            id="",  # 排序后再编号
            symbol=rec["symbol"], rule_type=rec["rule_type"], file=rec["file"], line=rec["line"],
            scope=rec["scope"], roi=rec["roi"], width=rec["width"], height=rec["height"],
            short_side=rec["short_side"], long_side=rec["long_side"], area=rec["area"],
            aspect_ratio=rec["aspect_ratio"], roi_semantics=rec["roi_semantics"],
            dynamic_roi_front=(rec["rule_type"] in ("RuleImage", "RuleGif")),
            semantic_guess=semantics, semantic_label=_SEM_LABELS[semantics],
            target_kind=_target_kind(semantics),
            priority=_priority(rec, semantics, has_click),
            consumers=[asdict(u) for u in usages[:12]],
            click_consumer_count=len(clicks), detect_consumer_count=len(detects),
            consumer_status=("HAS_CLICK_CONSUMER" if has_click
                             else ("DETECT_ONLY" if detects else
                                   ("REFERENCED_NO_VERB" if refs.get(rec["symbol"]) else
                                    "UNUSED / NO PRODUCTION CONSUMER"))),
            consumer_attribution=attribution,
            defined_in_scopes=sorted(scopes_of.get(rec["symbol"], ())),
            resource_path=res, resource_exists=exists,
            review_questions=_review_questions(semantics, rec, has_click,
                                               bool(refs.get(rec["symbol"]))),
        ))

    # 排序：优先级 → 面积降序 → symbol
    order = {"P0": 0, "P1": 1, "P2": 2}
    items.sort(key=lambda it: (order[it.priority], -it.area, it.symbol))
    for i, it in enumerate(items, 1):
        it.id = f"{i:03d}"
    return items


def build_all_random(records: list[dict], index: dict[str, list[Usage]]) -> list[dict]:
    """**所有**名字含 RANDOM 的可点击 Rule——不受 short_side 门槛限制，供逐个人工确认。

    命名有 RANDOM 不等于未来一定要 UNIFORM，这里只是把它们全部摊开。
    """
    out = []
    for rec in records:
        if "RANDOM" not in (rec["symbol"] or "") or rec["rule_type"] == "RuleOcr":
            continue
        usages = index.get(rec["symbol"], [])
        clicks = [u for u in usages if u.kind in _CLICK_KINDS]
        detects = [u for u in usages if u.kind == "detect"]
        out.append({
            "symbol": rec["symbol"], "rule_type": rec["rule_type"], "scope": rec["scope"],
            "loc": f"{rec['file']}:{rec['line']}", "roi": rec["roi"],
            "wxh": f"{rec['width']}x{rec['height']}", "short_side": rec["short_side"],
            "area": rec["area"], "aspect_ratio": rec["aspect_ratio"],
            "click_consumers": [f"{u.file}:{u.line} {u.func}() {u.verb}()" for u in clicks[:6]],
            "detect_consumers": len(detects),
            "consumer_status": ("HAS_CLICK_CONSUMER" if clicks
                                else ("DETECT_ONLY" if detects
                                      else "UNUSED / NO PRODUCTION CONSUMER")),
            "review_status": "pending",
        })
    out.sort(key=lambda r: (r["scope"], -(r["area"] or 0), r["symbol"]))
    return out


# 「超大」审查表门槛：短边 ≥ 该值就特别容易混淆「检测面板」和「点击区」
VERY_LARGE_SHORT_SIDE = 300


def build_very_large(items: list[ReviewItem], records: list[dict],
                     index: dict[str, list[Usage]]) -> list[dict]:
    """整屏 / 超大区域审查表：短边 ≥300 或面积 ≥15 万，**含被排除的纯检测项**——
    因为这类尺寸最容易把「检测整屏」误当成「点击整屏」。"""
    out = []
    seen = set()
    for rec in records:
        ss, area = rec.get("short_side"), rec.get("area") or 0
        if ss is None or (ss < VERY_LARGE_SHORT_SIDE and area < 150000):
            continue
        key = (rec["file"], rec["line"])
        if key in seen:
            continue
        seen.add(key)
        usages = index.get(rec["symbol"], [])
        clicks = [u for u in usages if u.kind in _CLICK_KINDS]
        detects = [u for u in usages if u.kind == "detect"]
        in_main = any(it.file == rec["file"] and it.line == rec["line"] for it in items)
        out.append({
            "symbol": rec["symbol"], "rule_type": rec["rule_type"], "scope": rec["scope"],
            "loc": f"{rec['file']}:{rec['line']}", "roi": rec["roi"],
            "wxh": f"{rec['width']}x{rec['height']}", "short_side": rec["short_side"],
            "area": area,
            "in_main_list": in_main,
            "click_consumers": [f"{u.file}:{u.line} {u.func}() {u.verb}()" for u in clicks[:6]],
            "detect_consumer_count": len(detects),
            "verdict": ("确认有点击消费者 —— 需人工确认是否真的点整块"
                        if clicks else
                        ("只有检测消费者 —— 大概率是检测面板不是点击区" if detects
                         else "全仓无消费者 —— 疑似死资产")),
            "review_status": "pending",
        })
    out.sort(key=lambda r: -r["area"])
    return out


def build_excluded(records: list[dict], index: dict[str, list[Usage]],
                   threshold=LARGE_SHORT_SIDE) -> list[dict]:
    """大尺寸但不进主清单的：纯检测 RuleImage、RuleOcr。"""
    out = []
    for rec in records:
        ss = rec.get("short_side")
        if ss is None or ss < threshold:
            continue
        usages = index.get(rec["symbol"], [])
        clicks = [u for u in usages if u.kind in _CLICK_KINDS]
        if rec["rule_type"] == "RuleOcr":
            reason = "RuleOcr：读取用途（ocr / ocr_appear），不产生点击坐标"
        elif rec["rule_type"] == "RuleImage" and not clicks:
            reason = ("纯检测 RuleImage：只有 appear 类消费者" if usages
                      else "纯检测 RuleImage：全仓无消费者")
        else:
            continue
        out.append({
            "symbol": rec["symbol"], "rule_type": rec["rule_type"],
            "loc": f"{rec['file']}:{rec['line']}", "scope": rec["scope"],
            "wxh": f"{rec['width']}x{rec['height']}", "short_side": rec["short_side"],
            "reason": reason, "detect_consumer_count": len([u for u in usages if u.kind == "detect"]),
        })
    out.sort(key=lambda r: (-r["short_side"], r["symbol"]))
    return out


# --------------------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------------------

_SETTLEMENT_KEYS = ("RANDOM", "REWARD", "SETTLE", "VICTORY", "DEFEAT", "WIN",
                    "RESULT", "CONTINUE", "AWARD", "_RD")


def is_settlement_group(it: ReviewItem) -> bool:
    """GeneralBattle / 结算 / 奖励一组（本轮必须排最前）。"""
    return (it.scope in ("Component", "GlobalGame")
            and any(k in it.symbol for k in _SETTLEMENT_KEYS)) \
        or it.semantic_guess in ("settlement_region", "random_region")


def _why_first(it: ReviewItem) -> str:
    if it.consumer_status.startswith("UNUSED"):
        return "尺寸很大但**全仓无消费者**——先确认是死资产还是待接入的新规划"
    if it.semantic_guess == "random_region":
        return "战后 / 覆盖层安全散点区，直接决定新点击模型走 UNIFORM 还是个人热点"
    if it.semantic_guess == "settlement_region":
        return "结算 / 奖励推进区，高频且最容易误触"
    if it.semantic_guess == "fullscreen_dismiss":
        return "整屏尺寸——必须先确认是「点整屏」还是只是「检测整屏」"
    if it.semantic_guess == "large_safe_region":
        return "页面级安全区，影响该页所有推进点击"
    if it.semantic_guess == "fixed_business_area":
        return "登录 / 账号类固定区，误点代价高"
    return "大尺寸点击目标，影响 profile 选择"


# 前 20 优先看的顺序权重：结算/随机 → 整屏 → 死资产 → 其它
_TOP20_WEIGHT = {"random_region": 0, "settlement_region": 0, "fullscreen_dismiss": 1,
                 "large_safe_region": 2, "fixed_business_area": 3,
                 "large_button": 4, "wide_card": 4, "dynamic_template": 5, "unknown": 5}
# 高频日常任务优先于低频活动
_HOT_SCOPES = ("Component", "GlobalGame", "GameUi", "Dokan", "Exploration", "RealmRaid")


def top20(items: list[ReviewItem], n: int = 20) -> list[ReviewItem]:
    """建议人工优先查看的前 N 条：通用结算 → 全局奖励关闭 → 高频日常大随机区 →
    整屏关闭 → 大按钮 / 卡片 → 低频活动。"""
    def key(it: ReviewItem):
        return (
            _TOP20_WEIGHT.get(it.semantic_guess, 6),
            0 if it.scope in _HOT_SCOPES else 1,
            0 if it.consumer_status == "HAS_CLICK_CONSUMER" else 1,
            -it.area,
        )
    return sorted(items, key=key)[:n]


def render_markdown(items: list[ReviewItem], excluded: list[dict], stats: dict,
                    all_random: list[dict], very_large: list[dict]) -> str:
    L = []
    a = L.append
    a("# Large Click ROI Review\n")
    a(f"筛选门槛：`short_side >= {LARGE_SHORT_SIDE}px`（**仅几何标签，未写入任何生产分类逻辑**）。")
    a("所有 `semantic_guess` / `priority` 均为启发式初判，`review_status` 一律 `pending`，等人工看图确认。\n")
    a("## 概览\n")
    a("| 项 | 值 |\n|---|---|")
    for k, v in stats.items():
        a(f"| {k} | {v} |")

    a("\n---\n")
    a("## 建议优先查看的前 20 个\n")
    a("| # | id | symbol | 页面 / 用途 | ROI | 为什么优先 |")
    a("|---|---|---|---|---|---|")
    for n, it in enumerate(top20(items), 1):
        a(f"| {n} | {it.id} | `{it.symbol}` | {it.scope} · {it.semantic_guess} "
          f"| {it.width}×{it.height} | {_why_first(it)} |")

    def _item_block(it: ReviewItem):
        a(f"\n### {it.id} `{it.symbol}`  —— {it.semantic_label}\n")
        a(f"- **ROI**：`{it.roi}`　{it.width}×{it.height}　short={it.short_side} "
          f"long={it.long_side} area={it.area} AR={it.aspect_ratio}")
        a(f"- **定义**：`{it.file}:{it.line}`　({it.rule_type}, scope `{it.scope}`)")
        a(f"- **目标类型**：{it.target_kind}　|　**优先级**：{it.priority}　|　"
          f"**dynamic roi_front**：{'是' if it.dynamic_roi_front else '否'}")
        a(f"- **消费者**：{it.consumer_status}（click {it.click_consumer_count} / "
          f"detect {it.detect_consumer_count}）")
        if it.consumer_attribution == "ambiguous":
            a(f"    - ⚠ 同名符号在 {it.defined_in_scopes} 都有定义，下面的调用方按**符号名**合并，"
              f"可能不全属于本条——需人工核对")
        for c in it.consumers[:6]:
            a(f"    - `{c['file']}:{c['line']}` `{c['func']}()` → `{c['verb']}(...)` [{c['kind']}]")
        if not it.consumers:
            a("    - （无）")
        if it.resource_path:
            a(f"- **模板图**：`{it.resource_path}`"
              f"{'' if it.resource_exists else ' ⚠ 文件不存在'}")
        a(f"- **采样链路**：`{it.rule_type}.coord()` → `ClickSampler.sample()`，"
          f"当前 strategy **{it.current_strategy}**")
        a("- **人工检查重点**：")
        for q in it.review_questions:
            a(f"    - [ ] {q}")
        a(f"- `review_status = {it.review_status}`")

    settle = [it for it in items if is_settlement_group(it)]
    a("\n---\n")
    a(f"## P0 — GeneralBattle / Settlement / Reward / Random（{len(settle)} 项，最优先）\n")
    a("> 用户正在重新规划「默认 settlement primary ROI」，这一组必须先看。")
    for it in settle:
        _item_block(it)

    rest_p0 = [it for it in items if it.priority == "P0" and not is_settlement_group(it)]
    a("\n---\n")
    a(f"## P0 — 其它大安全区 / 整屏关闭（{len(rest_p0)} 项）\n")
    for it in rest_p0:
        _item_block(it)

    for pri, title in (("P1", "P1 — 大按钮 / 大卡片 / 固定业务区"),
                       ("P2", "P2 — 语义已明确或不适合个性化")):
        grp = [it for it in items if it.priority == pri and not is_settlement_group(it)]
        a("\n---\n")
        a(f"## {title}（{len(grp)} 项，按 task 分组；完整字段见 JSON）\n")
        by_scope: dict[str, list[ReviewItem]] = {}
        for it in grp:
            by_scope.setdefault(it.scope, []).append(it)
        for scope in sorted(by_scope):
            a(f"\n### {scope}\n")
            a("| id | symbol | 类型 | w×h | short | AR | 语义初判 | 消费者 | 定义 |")
            a("|---|---|---|---|---|---|---|---|---|")
            for it in by_scope[scope]:
                a(f"| {it.id} | `{it.symbol}` | {it.rule_type} | {it.width}×{it.height} "
                  f"| {it.short_side} | {it.aspect_ratio} | {it.semantic_guess} "
                  f"| {it.consumer_status} | `{it.file}:{it.line}` |")

    a("\n---\n")
    a(f"## 全部 `*RANDOM*` 命名的可点击 Rule（{len(all_random)} 项，不受 96px 门槛限制）\n")
    a("> 命名里有 RANDOM **不等于**未来一定要 UNIFORM，请逐个确认「是真的需要全区域均匀」"
      "还是只是历史命名。")
    a("\n| symbol | scope | w×h | short | ROI | 消费者 | 主要调用方 |")
    a("|---|---|---|---|---|---|---|")
    for r in all_random:
        cs = "<br>".join(f"`{c}`" for c in r["click_consumers"]) or "—"
        a(f"| `{r['symbol']}` | {r['scope']} | {r['wxh']} | {r['short_side']} | `{r['roi']}` "
          f"| {r['consumer_status']} | {cs} |")

    a("\n---\n")
    a(f"## 超大区域审查表（short_side ≥ {VERY_LARGE_SHORT_SIDE} 或 area ≥ 15 万，"
      f"{len(very_large)} 项）\n")
    a("> 这类尺寸最容易把「检测整屏」误当成「点击整屏」，每一条都要明确**是否真的点击整块区域**。")
    a("\n| symbol | 类型 | scope | w×h | 在主清单 | 判定 | 主要点击调用方 | 定义 |")
    a("|---|---|---|---|---|---|---|---|")
    for r in very_large:
        cs = "<br>".join(f"`{c}`" for c in r["click_consumers"]) or "—"
        a(f"| `{r['symbol']}` | {r['rule_type']} | {r['scope']} | {r['wxh']} "
          f"| {'是' if r['in_main_list'] else '否'} | {r['verdict']} | {cs} | `{r['loc']}` |")

    a("\n---\n")
    a(f"## 排除项 —— 大尺寸但不进主清单（{len(excluded)} 项）\n")
    a("| symbol | 类型 | w×h | short | 排除原因 | 定义 |")
    a("|---|---|---|---|---|---|")
    for r in excluded:
        a(f"| `{r['symbol']}` | {r['rule_type']} | {r['wxh']} | {r['short_side']} "
          f"| {r['reason']} | `{r['loc']}` |")

    a("\n_本文件由 dev_tools/large_click_roi_review.py 生成；只读分析，未改任何 Asset / 生产代码。_")
    return "\n".join(L) + "\n"


def compute_stats(items: list[ReviewItem], excluded: list[dict], all_large: int) -> dict:
    from collections import Counter
    types = Counter(it.rule_type for it in items)
    pri = Counter(it.priority for it in items)
    sem = Counter(it.semantic_guess for it in items)
    return {
        f"short_side >= {LARGE_SHORT_SIDE} 的 ROI 定义（含 RuleOcr / 纯检测）": all_large,
        "进入主审查清单": len(items),
        "  RuleClick": types.get("RuleClick", 0),
        "  RuleImage（确认有点击消费者）": types.get("RuleImage", 0),
        "  RuleLongClick": types.get("RuleLongClick", 0),
        "排除（纯检测 RuleImage + RuleOcr）": len(excluded),
        "P0": pri.get("P0", 0),
        "P1": pri.get("P1", 0),
        "P2": pri.get("P2", 0),
        "settlement / reward / random 组": sum(1 for it in items if is_settlement_group(it)),
        "C_*RANDOM*": sum(1 for it in items if "RANDOM" in it.symbol),
        "整屏 / 超大（short>=300）": sum(1 for it in items if it.short_side >= 300),
        "无生产 consumer": sum(1 for it in items if it.consumer_status.startswith("UNUSED")),
        "region target": sum(1 for it in items if it.target_kind == "region"),
        "point target": sum(1 for it in items if it.target_kind == "point"),
        "语义初判分布": dict(sem),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="large_click_roi_review",
        description="从 click ROI inventory 生成大尺寸点击 ROI 的人工审查目录（只读）。",
    )
    p.add_argument("--threshold", type=int, default=LARGE_SHORT_SIDE,
                   help=f"short_side 门槛（默认 {LARGE_SHORT_SIDE}）")
    p.add_argument("--roots", nargs="*", default=list(cri.DEFAULT_ROOTS))
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)

    records = [asdict(r) for r in cri.scan_repo(args.roots)]
    index = build_consumer_index()
    refs = build_reference_index()
    class_map = build_assets_class_map()
    items = build_items(records, index, refs, threshold=args.threshold,
                        class_map=class_map)
    excluded = build_excluded(records, index, threshold=args.threshold)
    all_random = build_all_random(records, index)
    very_large = build_very_large(items, records, index)
    all_large = sum(1 for r in records
                    if r["short_side"] is not None and r["short_side"] >= args.threshold)
    stats = compute_stats(items, excluded, all_large)
    stats["全部 *RANDOM* 命名（不限尺寸）"] = len(all_random)
    stats[f"超大区域审查表（short>={VERY_LARGE_SHORT_SIDE} 或 area>=15万）"] = len(very_large)

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "large_click_roi_review.json"
    md_path = out_dir / "large_click_roi_review.md"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"threshold": args.threshold, "stats": stats,
                   "items": [asdict(it) for it in items], "excluded": excluded,
                   "all_random": all_random, "very_large": very_large,
                   "suggested_first_20": [{"id": it.id, "symbol": it.symbol,
                                           "scope": it.scope, "wxh": f"{it.width}x{it.height}",
                                           "semantic_guess": it.semantic_guess,
                                           "why": _why_first(it)} for it in top20(items)]},
                  fh, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(items, excluded, stats, all_random, very_large))

    print("large click ROI review")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  output: {json_path}")
    print(f"          {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
