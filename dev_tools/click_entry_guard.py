# This Python file uses the following encoding: utf-8
"""L1 全局执行入口静态守卫：生产代码里的物理点击 / 长按只允许经统一执行器。

    单击：任务 / BaseTask / 组件 → execute_single_click → Control.click / click_with_backend → 设备后端
    长按：任务 / BaseTask / 组件 → execute_long_click   → Control.long_click                 → 设备后端

本模块只做**静态**扫描（AST），回答「有没有绕过执行器的生产直接点击 / 长按」。它不证明业务点击一定执行成功、
也不证明坐标分布——那是运行期测试的职责（`tests/test_l1_stage3b_global_guard.py` 及各 Stage 等价性测试）。
滑动 / 拖动 / 连续触摸手势不属于单击或长按，本守卫不约束它们。

设计要点：
- **扫描实际文件，不是登记册**：对生产根目录 `rglob('*.py')`，新建的任务文件天然被覆盖；测试另外校验「仓库里
  出现的每个含 Python 的顶层目录，要么被扫描、要么在显式的非生产清单里」，防止新增生产目录漏扫。
- **默认禁止，白名单精确到（文件, 函数, 调用形式, 次数）**，并写明原因与所属层；不按文件名 / 目录整体豁免，
  Login / DailyTrifles / WeeklyPurchase 也没有任何豁免。白名单出现「过期条目」（源码里已找不到）同样失败，
  避免删除了合法出口却仍报告完整；另外强制校验必需的合法出口确实存在。
- 白名单分两张表：`_INTERNAL_EXITS` 是执行器 / Control / 后端 / 演示 / 死代码这些**架构内部出口**；
  `BUSINESS_EXEMPTIONS` 是用户明确决定保留原实现的**业务点击豁免**（层名 `exempt`），性质不同故分开登记，
  便于审查它到底放行了哪几处、以及随时收回。两张表的精确度与过期检测完全一致。
- **识别的违规形式**（不是单一正则）：设备类接收者上的 `click` / `long_click` 调用、`click_with_backend` /
  `multi_click` / `click_<后端>` / `long_click_<后端>`（后端名取自 `module/device/method` 的实际定义，任何接收者）、
  `Control.click` 这类类限定调用、对上述方法的**非调用引用**（赋给变量 / 传给 partial / 塞进字典）、
  `getattr(x, 'click')` 字面量取属性；设备别名（`dev = self.device`）在函数内做简单传播。
- **无法静态确定的动态调用**（`getattr(设备, 变量)`）不武断放行也不武断判违规，单独列入 `unresolved`。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 生产扫描根：目录整体 rglob；仓库根目录的顶层 *.py（script.py / server.py / gui.py 等）也算生产。
PRODUCTION_ROOTS = ('tasks', 'module', 'deploy')
# 明确不是生产点击代码的顶层目录（含 Python 也不扫描）。新增顶层含 Python 的目录若不在此表也不在
# PRODUCTION_ROOTS，测试会失败并要求显式归类。
NON_PRODUCTION_ROOTS = ('tests', 'dev_tools', 'toolkit', 'docs', 'log', 'config', 'bin', 'fluentui', 'assets',
                        'OASX', '__pycache__')

DEVICE_LAYER_PREFIX = 'module/device/'
EXECUTOR_FILE = 'module/click_pipeline.py'

# 方法名本身就足以判定为「设备点击入口」的集合之外，`click` / `long_click` 只在设备类接收者上才算。
_ALWAYS_FORBIDDEN = frozenset({'click_with_backend', 'multi_click'})
_RECEIVER_SENSITIVE = frozenset({'click', 'long_click'})
_DEVICE_CLASS_NAMES = frozenset({'Control', 'Device'})

SUGGESTION = {
    'click': '单击请用 `execute_single_click(self.device, FinalPoint(x, y) / 目标, control_name=...)`',
    'long_click': '长按请用 `execute_long_click(self.device, FinalPoint(x, y) / 目标, 秒数, control_name=...)`',
}


def _backend_names(repo: Path) -> frozenset[str]:
    """`click_<后端>` / `long_click_<后端>` 的真实名字：取自 `module/device/method` 里的函数定义。"""
    names = set()
    method_dir = repo / 'module' / 'device' / 'method'
    for path in method_dir.rglob('*.py') if method_dir.is_dir() else ():
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    node.name.startswith('click_') or node.name.startswith('long_click_')):
                if not node.name.startswith('click_record'):
                    names.add(node.name)
    # 兜底：即便后端文件被误删，这些名字仍按后端直调处理
    names |= {'click_adb', 'click_uiautomator2', 'click_minitouch', 'click_scrcpy', 'click_window_message', 'click_nemu_ipc',
              'long_click_adb', 'long_click_uiautomator2', 'long_click_minitouch', 'long_click_scrcpy',
              'long_click_window_message', 'long_click_nemu_ipc'}
    return frozenset(names)


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    func: str
    form: str          # 违规调用形式（源码里的调用链，例如 self.device.click）
    kind: str          # call / reference / getattr / dynamic
    attr: str

    @property
    def suggestion(self) -> str:
        if 'long' in self.attr:
            return SUGGESTION['long_click']
        return SUGGESTION['click']

    def render(self) -> str:
        return f'{self.file}:{self.line} 函数 {self.func}：违规 {self.kind} `{self.form}` → {self.suggestion}'


@dataclass(frozen=True)
class AllowedExit:
    """一个明确登记的内部出口。`count` 是该函数内这种调用形式允许出现的**精确**次数。"""
    file: str
    func: str
    form: str
    kind: str          # call / reference（与 Violation.kind 对应）
    count: int
    layer: str         # executor / control / backend / demo / dead
    reason: str


def _chain(node) -> tuple[str, ...] | None:
    """`a.b.c` → ('a', 'b', 'c')；根不是 Name（如调用结果）时返回 None。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return None


@dataclass
class _Scope:
    name: str
    aliases: set = field(default_factory=set)


class _Scanner(ast.NodeVisitor):
    def __init__(self, rel: str, backend_names: frozenset[str]):
        self.rel = rel
        self.backends = backend_names
        self.device_layer = rel.startswith(DEVICE_LAYER_PREFIX)
        self.scopes: list[_Scope] = [_Scope('<module>')]
        self.violations: list[Violation] = []
        self.unresolved: list[Violation] = []
        self._call_funcs: set[int] = set()

    # ---- 作用域 ----
    def _qual(self) -> str:
        return '.'.join(s.name for s in self.scopes[1:]) or '<module>'

    def _enter(self, node, name):
        scope = _Scope(name)
        # 参数名叫 device 视为设备
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                if arg.arg == 'device':
                    scope.aliases.add(arg.arg)
            self._collect_aliases(node, scope)
        self.scopes.append(scope)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_ClassDef(self, node):
        self._enter(node, node.name)

    def visit_FunctionDef(self, node):
        self._enter(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _collect_aliases(self, fn, scope: _Scope) -> None:
        """函数内的简单别名传播：`dev = self.device` / `d = dev`。迭代到不动点，顺序无关。"""
        assigns = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                assigns.append((n.targets[0].id, n.value))
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
                assigns.append((n.target.id, n.value))
        changed = True
        while changed:
            changed = False
            for name, value in assigns:
                if name not in scope.aliases and self._is_device_expr(value, scope.aliases):
                    scope.aliases.add(name)
                    changed = True

    # ---- 判定 ----
    def _is_device_expr(self, node, aliases) -> bool:
        chain = _chain(node)
        if chain is None:
            return False
        if chain[0] in aliases or (len(chain) == 1 and chain[0] in _DEVICE_CLASS_NAMES):
            return True
        return 'device' in chain

    def _aliases(self) -> set:
        merged = set()
        for scope in self.scopes:
            merged |= scope.aliases
        return merged

    def _flag(self, node, chain, attr, kind):
        self.violations.append(Violation(self.rel, node.lineno, self._qual(), '.'.join(chain), kind, attr))

    def _classify_attribute(self, node: ast.Attribute, is_call: bool) -> None:
        attr = node.attr
        chain = _chain(node)
        if chain is None:
            return
        receiver = node.value
        kind = 'call' if is_call else 'reference'
        if attr in _ALWAYS_FORBIDDEN or attr in self.backends:
            self._flag(node, chain, attr, kind)
            return
        if attr in _RECEIVER_SENSITIVE:
            root = chain[0]
            class_qualified = root in _DEVICE_CLASS_NAMES and len(chain) == 2
            if class_qualified or self._is_device_expr(receiver, self._aliases()):
                self._flag(node, chain, attr, kind)
            elif self.device_layer:
                # 设备层里任何接收者的 click / long_click（self.click、self.u2.long_click、demo 里的实例）都要显式登记
                self._flag(node, chain, attr, kind)

    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            self._call_funcs.add(id(func))
            self._classify_attribute(func, is_call=True)
        elif isinstance(func, ast.Name) and func.id == 'getattr' and len(node.args) >= 2:
            target, name = node.args[0], node.args[1]
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                attr = name.value
                if attr in _ALWAYS_FORBIDDEN or attr in self.backends or (
                        attr in _RECEIVER_SENSITIVE and (self._is_device_expr(target, self._aliases()) or self.device_layer)):
                    self.violations.append(Violation(self.rel, node.lineno, self._qual(), f'getattr(..., {attr!r})', 'getattr', attr))
            elif self._is_device_expr(target, self._aliases()):
                self.unresolved.append(Violation(self.rel, node.lineno, self._qual(), 'getattr(<设备>, <动态名字>)', 'dynamic', '?'))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if id(node) not in self._call_funcs:
            self._classify_attribute(node, is_call=False)
        self.generic_visit(node)


def scan_source(rel: str, source: str, backend_names: frozenset[str] | None = None) -> tuple[list[Violation], list[Violation]]:
    """扫描一段源码，返回 (违规候选, 无法静态确定)。`rel` 是相对仓库根的 posix 路径（决定是否设备层）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    scanner = _Scanner(rel, backend_names if backend_names is not None else _backend_names(REPO))
    scanner.visit(tree)
    return scanner.violations, scanner.unresolved


def production_files(repo: Path = REPO) -> list[str]:
    """生产 Python 文件（相对路径）：生产根目录 rglob + 仓库根目录顶层 *.py。"""
    files = []
    for top in PRODUCTION_ROOTS:
        base = repo / top
        if base.is_dir():
            files.extend(p.relative_to(repo).as_posix() for p in base.rglob('*.py'))
    files.extend(p.name for p in repo.glob('*.py'))
    return sorted(f for f in set(files) if '__pycache__' not in f)


def unclassified_roots(repo: Path = REPO) -> list[str]:
    """含 Python 文件、却既不是生产根也不在非生产清单里的顶层目录（应为空）。"""
    known = set(PRODUCTION_ROOTS) | set(NON_PRODUCTION_ROOTS)
    out = []
    for child in sorted(repo.iterdir()):
        if child.is_dir() and not child.name.startswith('.') and child.name not in known and next(child.rglob('*.py'), None):
            out.append(child.name)
    return out


def scan_repo(repo: Path = REPO) -> tuple[list[Violation], list[Violation]]:
    backends = _backend_names(repo)
    violations, unresolved = [], []
    for rel in production_files(repo):
        source = (repo / rel).read_text(encoding='utf-8')
        v, u = scan_source(rel, source, backends)
        violations.extend(v)
        unresolved.extend(u)
    return violations, unresolved


# ======================================================================================
# 白名单：默认禁止，只允许下列明确登记的内部出口（精确到 文件 / 函数 / 调用形式 / 次数）
# ======================================================================================
_CTRL = 'module/device/control.py'
_U2 = 'module/device/method/uiautomator_2.py'
_WIN = 'module/device/method/windows_impl.py'
_MT = 'module/device/method/minitouch.py'


def _refs(file, func, forms, layer, reason):
    return tuple(AllowedExit(file, func, form, 'reference', 1, layer, reason) for form in forms)


_INTERNAL_EXITS: tuple[AllowedExit, ...] = (
    # ---- L1 执行器：唯一允许业务侧「落到设备」的出口 ----
    AllowedExit(EXECUTOR_FILE, 'execute_single_click', 'device.click', 'call', 1, 'executor', '单击执行器：默认后端经 Control.click'),
    AllowedExit(EXECUTOR_FILE, 'execute_single_click', 'device.click_with_backend', 'call', 1, 'executor',
                '单击执行器：显式后端经 Control.click_with_backend（百鬼夜行）'),
    AllowedExit(EXECUTOR_FILE, 'execute_long_click', 'device.long_click', 'call', 1, 'executor', '长按执行器：经 Control.long_click'),
    # ---- Control：按 control_method 向已注册后端分派（后端表 / 兜底后端的引用）----
    *_refs(_CTRL, 'Control.click_methods', ('self.click_adb', 'self.click_uiautomator2', 'self.click_minitouch',
                                           'self.click_window_message'), 'control', '单击后端注册表'),
    *_refs(_CTRL, 'Control.long_click_methods', ('self.long_click_adb', 'self.long_click_uiautomator2', 'self.long_click_minitouch',
                                                'self.long_click_scrcpy', 'self.long_click_window_message'), 'control', '长按后端注册表'),
    *_refs(_CTRL, 'Control.click_backend_methods', ('self.click_minitouch', 'self.click_window_message'), 'control',
           '显式指定单击后端的注册表（click_with_backend）'),
    *_refs(_CTRL, 'Control.click', ('self.click_adb',), 'control', '未配置 control_method 时回退 ADB 单击'),
    *_refs(_CTRL, 'Control.long_click', ('self.long_click_adb',), 'control', '未配置 control_method 时回退 ADB 长按'),
    AllowedExit(_CTRL, 'Control.multi_click', 'self.click', 'call', 1, 'dead',
                '无生产消费者的死代码（此前审查发现其实现有误）；本轮只登记，不顺手修改'),
    # ---- 设备后端内部：真实驱动自己的点击 / 按住实现 ----
    AllowedExit(_U2, 'Uiautomator2.click_uiautomator2', 'self.u2.click', 'call', 1, 'backend', 'uiautomator2 后端的单击实现'),
    AllowedExit(_U2, 'Uiautomator2.long_click_uiautomator2', 'self.u2.long_click', 'call', 1, 'backend', 'uiautomator2 后端的长按实现'),
    AllowedExit(_WIN, 'Window.scroll_window_message', 'self.click_window_message', 'call', 1, 'backend',
                'window_message 后端内部：滚动前的聚焦点击，属驱动实现细节'),
    # ---- 演示入口（`if __name__ == "__main__"`），不属于业务生产路径 ----
    AllowedExit(_MT, '<module>', 'mm.click_minitouch', 'call', 1, 'demo', 'minitouch 后端的手动演示入口'),
    AllowedExit(_WIN, '<module>', 'w.long_click_window_message', 'call', 1, 'demo', 'window_message 后端的手动演示入口'),
)

# ---- 业务豁免：与上面的「内部出口」性质不同，单独成表，方便审查和随时收回 ----
# 只有用户明确决定保留原实现的生产点击才可进入本表，且同样精确到（文件, 函数, 调用形式, 次数）：
# 该函数里多出任何一处裸点击都会超预算报违规，原调用点消失则报过期。不按文件 / 模块整体豁免。
BUSINESS_EXEMPTIONS: tuple[AllowedExit, ...] = (
    AllowedExit('tasks/Component/SwitchAccount/netease_account_ui.py', 'NeteaseAccountUi._click_bounds',
                'self.device.click', 'call', 1, 'exempt',
                'synevo 原有账号切换控件点击（原生 Android bounds 取中心直点）：用户决定保留现状，'
                '不接入 L1 / L2，不改坐标、采样、等待、重试与执行后端'),
)

ALLOWED_EXITS: tuple[AllowedExit, ...] = _INTERNAL_EXITS + BUSINESS_EXEMPTIONS

REQUIRED_EXITS = (
    (EXECUTOR_FILE, 'execute_single_click', 'device.click'),
    (EXECUTOR_FILE, 'execute_single_click', 'device.click_with_backend'),
    (EXECUTOR_FILE, 'execute_long_click', 'device.long_click'),
    (_CTRL, 'Control.long_click_methods', 'self.long_click_minitouch'),
    (_CTRL, 'Control.click_methods', 'self.click_minitouch'),
)


@dataclass
class GuardResult:
    unallowed: list      # 未登记的违规（默认禁止）：必须迁到 L1 执行器，不得靠加白名单消除
    stale: list          # 白名单里有、源码里已找不到 / 次数对不上的条目
    missing_required: list
    unresolved: list     # 无法静态确定的动态调用（单独报告）
    allowed_by_layer: dict

    @property
    def ok(self) -> bool:
        return not (self.unallowed or self.stale or self.missing_required or self.unresolved)

    def render(self) -> str:
        lines = [v.render() for v in self.unallowed]
        lines += [f'白名单过期或次数不符：{e.file} {e.func} {e.form}（登记 {e.count} 次）' for e in self.stale]
        lines += [f'缺少必需的合法出口：{f} {fn} {form}' for f, fn, form in self.missing_required]
        lines += [f'无法静态确定：{v.file}:{v.line} {v.func} {v.form}' for v in self.unresolved]
        return '\n'.join(lines)


def evaluate(violations, unresolved=(), allowed: tuple = ALLOWED_EXITS, required: tuple = REQUIRED_EXITS) -> GuardResult:
    """把扫描结果与白名单对账。未登记 → 违规；登记但找不到 / 次数不符 → 过期；必需出口缺失 → 失败。"""
    budget = {(e.file, e.func, e.form, e.kind): e.count for e in allowed}
    seen: dict = {}
    unallowed = []
    for v in sorted(violations, key=lambda v: (v.file, v.line)):
        key = (v.file, v.func, v.form, v.kind)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > budget.get(key, 0):
            unallowed.append(v)
    stale = [e for e in allowed if seen.get((e.file, e.func, e.form, e.kind), 0) != e.count]
    present = {(v.file, v.func, v.form) for v in violations}
    missing = [r for r in required if r not in present]
    by_layer: dict = {}
    for e in allowed:
        by_layer[e.layer] = by_layer.get(e.layer, 0) + seen.get((e.file, e.func, e.form, e.kind), 0)
    return GuardResult(unallowed, stale, missing, list(unresolved), by_layer)


def check_repo(repo: Path = REPO) -> GuardResult:
    violations, unresolved = scan_repo(repo)
    return evaluate(violations, unresolved)
