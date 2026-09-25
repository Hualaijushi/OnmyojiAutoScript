# This Python file uses the following encoding: utf-8
"""生产点击入口登记册：AST 静态盘点全仓 `tasks/` + `module/` 的点击调用点，并按 L2 分类术语归类。

用法（在仓库根）：
    toolkit\\python.exe -m dev_tools.click_callsite_register            # 只打印汇总
    toolkit\\python.exe -m dev_tools.click_callsite_register --write    # 重新生成 docs/L2_CALLSITE_REGISTER.md

分类沿用 `docs/L2_INTERACTION_POLICY_MAP.md` 的既有术语：MIGRATE / ALREADY_L2 / KEEP_IMMEDIATE / KEEP_SPECIAL /
NEEDS_C；另有两个「不在 L2 迁移范围」的范围标签：PRIMITIVE（点击 primitive 自身的实现层）与 EXCLUDED（项目决定 /
分支归属明确排除）。

分类来源（basis）两种，**不混为一谈**：
- `human`：L2-2 逐点人工审计过的 18 个文件（`tests/test_l2_policy_migration.py::INVENTORY`），沿用当时的结论；
- `rule`：其余模块由下面的**保守规则**归类（默认保持立即点击，不因规则判定就加 reaction）。规则分类不是逐点人工审计，
  只能证明「每个点击调用点都有归属，且默认不改变原有 timing」。

本模块只读源码，不 import 任何业务模块，不触碰设备 / 配置。
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

HELPERS = {
    'appear_then_click', 'wait_until_appear_then_click', 'ocr_appear_click', 'list_appear_click',
    'ui_click', 'ui_clicks', 'ui_click_until_disappear', 'ui_click_until_appear_or_timeout',
    'ui_click_until_smt_disappear', 'ui_get_reward', 'ui_reward_appear_click',
}
BACKENDS = {
    'click_minitouch', 'click_window_message', 'click_adb', 'click_scrcpy', 'click_uiautomator2',
    'click_maatouch', 'click_nemu_ipc', 'click_ldopengl', 'click_droidcast', 'click_with_backend',
}
WAIT_NAMES = {
    'sleep': 'sleep', 'random_delay': 'random_delay', 'Timer': 'Timer', 'wait_until_appear': 'wait_until',
    'wait_until_disappear': 'wait_until', 'wait_until_stable': 'wait_until',
    'wait_for_changed_and_stable': 'frame_wait',
}
SCAN_TOP = ('tasks', 'module')

# 项目决定 / 分支归属：整体排除 L2 reaction / 业务迁移。L1 点击执行入口不豁免（Stage 3B 起，见 click_entry_guard）
EXCLUDED_MODULES = {
    'WeeklyPurchase': 'WeeklyPurchase 按项目决定排除（不做 Reaction Policy / FIRE 改造；L1 执行入口不豁免）',
    'DailyTrifles': 'synevo 小号轮换业务，不做 L2 迁移（L1 执行入口不豁免）',
    'AccountRotation': 'synevo 小号轮换业务，不做 L2 迁移（L1 执行入口不豁免）',
    'MultiAccountEvo': 'synevo 小号轮换业务，不做 L2 迁移（L1 执行入口不豁免）',
    'tasks/Component/SwitchAccount': 'synevo 小号轮换业务，不做 L2 迁移（L1 执行入口不豁免）',
    'tasks/Component/Login': '登录 / 换号流程属小号轮换业务，不做 L2 迁移（L1 执行入口不豁免）',
}
# 已有独立 timing owner 的受保护业务（状态机 / FIRE / 调度 / 高频小游戏）
PROTECTED_MODULES = {
    'KekkaiUtilize': '受保护路径：Scheduler v1 / 收敛保护 / 分类切换边界已有时间预算，不叠加反应延迟',
    'tasks/Component/GeneralBattle': '战斗 / Settlement 状态机自有 timing',
    'tasks/Component/GeneralInvite': '组队房间状态机自有 timing',
    'RealmRaid': 'FIRE / 突破状态机', 'Orochi': 'FIRE 状态机', 'EvoZone': 'FIRE 状态机', 'RyouToppa': 'FIRE 状态机',
    'EternitySea': 'FIRE 状态机（Batch A）', 'FallenSun': 'FIRE 状态机（Batch A）', 'Sougenbi': 'FIRE 状态机（Batch A）',
    'Hyakkiyakou': '高频小游戏，独立后端分派与节奏',
    'Chess': '棋类状态机，自有 Timer / 节奏',
}
SPECIAL_FUNC_HINTS = (
    'exit', 'recover', 'clear', 'handle_', 'reward', 'settle', 'close', 'dismiss', 'restart', 'login', 'back',
    'emoji', 'afk', 'random_click', 'kick', 'cleanup', 'teardown', 'harvest', 'skill_wait',
)
# L2-2 人工审计范围（与 tests/test_l2_policy_migration.py::AUDIT_SCOPE 一致）
AUDITED_FILES = (
    'tasks/Component/GeneralInvite/general_invite.py', 'tasks/Component/GeneralBattle/general_battle.py',
    'tasks/GameUi/navigator.py', 'tasks/GameUi/default_pages.py', 'tasks/GameUi/chess_battle.py',
    'tasks/EvoZone/script_task.py', 'tasks/Orochi/script_task.py', 'tasks/RealmRaid/script_task.py',
    'tasks/RyouToppa/script_task.py', 'tasks/Exploration/base.py', 'tasks/Exploration/script_task.py',
    'tasks/ActivityShikigami/page.py', 'tasks/ActivityShikigami/base_act.py',
    'tasks/ActivityShikigami/activities/normal.py', 'tasks/ActivityShikigami/activities/fake_god.py',
    'tasks/ActivityShikigami/activities/rich_man.py', 'tasks/KekkaiUtilize/script_task.py',
    'tasks/KekkaiUtilize/page.py',
)
# L2-2 审计当时统计的调用名（与其 scan_scope 一致）；登记册用它把人工结论对齐到具体调用点
AUDIT_CALL_NAMES = {
    'appear_then_click', 'ui_click', 'ui_click_until_disappear', 'ui_click_until_smt_disappear',
    'ui_click_until_appear_or_timeout', 'click', 'ocr_appear_click', 'list_appear_click',
}

# L2 Stage C0 复核后已实际迁移到显式 policy 的调用点（C1-A1）：(文件, 函数, 目标, policy)。
# 必须真的在源码里声明了这个 policy——对不上就直接抛错，不静默兜底；其余 C0 复核点位在真正迁移前保持原分类。
C1_MIGRATED = (
    ('tasks/Dokan/page.py', 'priority_enter_dokan', 'target_priority', 'InteractionPolicy.NORMAL'),
    ('tasks/Pets/script_task.py', '_feed', 'self.I_UI_BACK_CIRCLE', 'InteractionPolicy.NAVIGATION'),
    ('tasks/SixRealms/common.py', 'refresh_store', 'refresh_rule', 'InteractionPolicy.CONFIRM'),
    ('tasks/SixRealms/common.py', 'choose_and_enter_island', 'target_land', 'InteractionPolicy.NORMAL'),
)
# L2 Stage C0 对其余 20 点的逐点归档（C1_MIGRATED 的 4 点之外）。两个维度分开记录，不可混成一个概念：
#   decision   = 技术分类（互斥、可加总）：KEEP_IMMEDIATE / KEEP_SPECIAL / NEEDS_C / DEFERRED
#   dev_status = 开发排期：COMPLETED（已实施）/ DEFERRED（用户主动暂缓）/ NOT_APPLICABLE（无需开发）
# 其中 decision=DEFERRED 只用于「C0 技术建议为 MIGRATE、但用户决定暂缓」的 6 点，原建议保存在 advice 里；
# 「技术上需要真机依据且用户暂缓」的 7 点仍是 decision=NEEDS_C，用 dev_status=DEFERRED 表达。
# 这 20 点在源码里必须仍是立即点击（不带 policy / confirm_delay），对不上直接抛错。
# (文件, 函数, 目标, 同一函数内该目标第几次出现, decision, dev_status, C0 建议, 说明)
C0_TRIAGE = (
    # ---- 用户暂缓迁移（C0 建议 MIGRATE）：Duel 2 ----
    ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / NORMAL',
     '练习入口：保持即时点击，不改 `or` 短路逻辑与原 2 秒页面等待'),
    ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN2', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / NORMAL',
     '练习入口：保持即时点击，不改 `or` 短路逻辑与原 2 秒页面等待'),
    # ---- 用户暂缓迁移（C0 建议 MIGRATE）：SixRealms 商店 4 ----
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_summon_store', 'self.I_M_STORE_ACTIVITY', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / NORMAL',
     '商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout'),
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_summon_store', 'self.I_UI_CONFIRM', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / CONFIRM',
     '商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout'),
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_use_breath', 'self.I_M_STORE_ACTIVITY', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / NORMAL',
     '商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout'),
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_confirm_store_entry', 'self.I_PK_STORE_STILLIN', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / CONFIRM',
     '商店事务：不实施 reaction，不改 coin 更新条件与 readiness timeout'),
    # ---- 保持即时（已有明确结论，不是迁移积压）----
    ('tasks/DemonRetreat/script_task.py', 'run', 'self.I_DEMON_BACK_CHECK', 1, 'KEEP_IMMEDIATE', 'NOT_APPLICABLE', '-', '失败恢复路径，保持即时'),
    ('tasks/Quiz/script_task.py', '_deal_quiz', 'self.I_ALONE_ENSURE', 1, 'KEEP_IMMEDIATE', 'NOT_APPLICABLE', '-', '答题倒计时敏感，保持即时'),
    ('tasks/SixRealms/common.py', 'open_shop', 'self.I_UI_CANCEL', 1, 'KEEP_IMMEDIATE', 'NOT_APPLICABLE', '-', '超时恢复路径，保持即时'),
    # ---- 保持专用时序（已有独立 timing owner）----
    ('tasks/Component/Buy/buy.py', 'buy_more', 'self.I_BUY_PLUS', 1, 'KEEP_SPECIAL', 'NOT_APPLICABLE', '-', '连续加量节奏：第一次点击；两次之间原有 0.5 秒等待保留'),
    ('tasks/Component/Buy/buy.py', 'buy_more', 'self.I_BUY_PLUS', 2, 'KEEP_SPECIAL', 'NOT_APPLICABLE', '-', '连续加量节奏：与第一次共享业务节奏，不拆成两次 NORMAL'),
    ('tasks/SixRealms/page.py', 'switch_moon_sea_shikigami', 'SixRealmsAssets.I_MSHOUZU_SELECT', 1, 'KEEP_SPECIAL', 'NOT_APPLICABLE', '-',
     'Navigator 单次进入 hook，不改 hook 语义'),
    ('tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py', '_mark_peacock_boss', 'self.I_LOCAL', 1, 'KEEP_SPECIAL', 'NOT_APPLICABLE', '-',
     '首领标记专用事务，原有 0.3 秒 settle 保留'),
    # ---- 技术上需要真机依据，且用户暂缓（decision 仍是 NEEDS_C，来源沿用 L2-2 人工审计）----
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_NO_DEFAULT', 1, 'NEEDS_C', 'DEFERRED', '-',
     '接受邀请事务：五个候选共享同一事务，逐按钮加 reaction 会重复等待；队长秒开有时效风险；接受循环缺少明确墙钟上限。重启前应先设计事务级 reaction 与有界状态确认'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_GI_SURE', 1, 'NEEDS_C', 'DEFERRED', '-', '同上（接受邀请事务）'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT_DEFAULT', 1, 'NEEDS_C', 'DEFERRED', '-', '同上（接受邀请事务）'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT', 1, 'NEEDS_C', 'DEFERRED', '-', '同上（接受邀请事务）'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT_APPRENTICE', 1, 'NEEDS_C', 'DEFERRED', '-', '同上（接受邀请事务）'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'self.I_DISABLE_7DAYS_DIFF_SOUL', 1, 'NEEDS_C', 'DEFERRED', '-',
     '准备页 FSM：可能受准备倒计时影响，不能直接套普通 CONFIRM，不得干扰组队就绪 / 进入战斗；与 Settlement 独立'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'self.I_CONFIRM_CLOSE_DIFF_SOUL', 1, 'NEEDS_C', 'DEFERRED', '-', '同上（准备页 FSM）'),
)
C0_REVIEWED_TOTAL = len(C1_MIGRATED) + len(C0_TRIAGE)      # C0 复核的原 NEEDS_C 调用点数
assert C0_REVIEWED_TOTAL == 24, C0_REVIEWED_TOTAL
DEV_STATUSES = ('COMPLETED', 'DEFERRED', 'NOT_APPLICABLE')

REASONS = {
    'R0': '点击 primitive / Device 管线层自身的实现',
    'R1': '项目决定 / 分支归属明确排除（仅限 L2 reaction 迁移；L1 点击执行入口不豁免）',
    'R2': '已显式声明 policy / confirm_delay（单一 reaction owner）',
    'R3': '受保护业务：已有独立 timing owner（状态机 / FIRE / 调度 / 小游戏）',
    'R4': '函数语义属恢复 / 关闭 / 奖励 / 退出 / 收取 / 防挂机 / 页面状态处理，由所在流程拥有 timing',
    'R5': '裸坐标 / 后端点击：没有可重新识别的目标，不能做 fresh confirm',
    'R6': '`self.click(<RuleClick>)` 固定区域点击：无 appear 目标，primitive 无 policy 参数',
    'R7': 'ui_click 系 / 其它 helper 自带点击循环且无 policy 参数，本轮不扩公共 API',
    'R8': '轮询循环内的探测式点击（interval / 超时预算），reaction 会吃掉循环预算；无真机证据不加',
    'R9': '非循环内的单次 appear_then_click：可能适合 reaction，页面时效 / 节奏无法静态判断 → 等真机',
    'R10': 'L1 管线点击（FinalPoint / Bounds / Region）：坐标语义已显式声明，无 reaction 语义',
    'H': 'L2-2 逐点人工审计结论（见 docs/L2_INTERACTION_POLICY_MAP.md）',
    'C1': 'L2 Stage C0 复核后已迁移到显式 policy（C1-A1，见 docs/L2_INTERACTION_POLICY_MAP.md）',
    'C0K': 'L2 Stage C0 复核结论：保持即时点击（失败恢复 / 倒计时敏感 / 超时恢复），不是迁移积压',
    'C0S': 'L2 Stage C0 复核结论：已有专用 timing owner（业务节奏 / Navigator hook / 专用事务），不加普通 policy',
    'C0D': 'L2 Stage C0 建议迁移，但用户决定暂缓（开发排期，不是技术完成；原建议保存在 C0 表）',
}


def _chain(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


def _kwarg(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return ast.unparse(kw.value)
    return None


def module_of(rel: str) -> str:
    parts = rel.split('/')
    if parts[0] == 'tasks':
        return '/'.join(parts[:3]) if parts[1] == 'Component' else parts[1]
    return parts[0]


class _Scan(ast.NodeVisitor):
    def __init__(self, rel: str, source: str):
        self.rel, self.source = rel, source
        self.scope, self.out = [], []
        self.loop_depth = 0
        self.func_waits = []

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _func(self, node):
        waits = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
                if name in WAIT_NAMES:
                    waits.add(WAIT_NAMES[name])
        self.scope.append(node.name)
        self.func_waits.append(waits)
        saved, self.loop_depth = self.loop_depth, 0
        self.generic_visit(node)
        self.loop_depth = saved
        self.func_waits.pop()
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _func

    def _loop(self, node):
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    visit_While = visit_For = _loop

    def visit_Call(self, node):
        kind, full = None, ''
        if isinstance(node.func, ast.Attribute):
            name, full = node.func.attr, _chain(node.func)
            if name == 'click' and (full.endswith('device.click') or full == 'device.click'):
                kind = 'raw_device_click'
            elif name in BACKENDS:
                kind = 'raw_backend'
            elif name in HELPERS:
                kind = name
            elif name == 'click' and full in ('self.click', 'task.click'):
                kind = 'click'
        elif isinstance(node.func, ast.Name) and node.func.id == 'execute_single_click':
            kind = 'execute_single_click'
        if kind:
            target = ' '.join((ast.get_source_segment(self.source, node.args[0]) or '?').split()) if node.args else '?'
            self.out.append({
                'file': self.rel, 'func': self.scope[-1] if self.scope else '<module>',
                'qual': '.'.join(self.scope) or '<module>', 'line': node.lineno, 'kind': kind, 'target': target,
                'chain': full, 'in_loop': self.loop_depth > 0,
                'waits': sorted(self.func_waits[-1]) if self.func_waits else [],
                'policy': _kwarg(node, 'policy'), 'confirm_delay': _kwarg(node, 'confirm_delay'),
                'interval': _kwarg(node, 'interval'),
            })
        self.generic_visit(node)


def scan_sites(repo: Path = REPO) -> list[dict]:
    """全仓生产点击调用点（源码顺序，按文件排序）。"""
    sites = []
    for top in SCAN_TOP:
        for path in sorted((repo / top).rglob('*.py')):
            rel = path.relative_to(repo).as_posix()
            if '__pycache__' in rel:
                continue
            source = path.read_text(encoding='utf-8')
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            scan = _Scan(rel, source)
            scan.visit(tree)
            sites.extend(scan.out)
    seen: Counter = Counter()
    for site in sites:
        site['module'] = module_of(site['file'])
        key = (site['file'], site['qual'])
        seen[key] += 1
        site['ordinal'] = seen[key]
    return sites


def scan_long_click_sites(repo: Path = REPO) -> list[dict]:
    """生产代码里的长按入口（单独一张表，不并入单击 sites，避免改变单击登记册的口径）。

    kind：`execute_long_click`（L1 长按执行器调用）/ `raw_long_click`（直调 `*.long_click(...)`）/
    `raw_long_backend`（直调 `long_click_<后端>`）。area：executor（执行器自身）/ primitive（BaseTask）/
    device_internal（`module/device/` 内部）/ consumer（其余生产代码）。
    """
    out = []
    for top in SCAN_TOP:
        for path in sorted((repo / top).rglob('*.py')):
            rel = path.relative_to(repo).as_posix()
            if '__pycache__' in rel:
                continue
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
                if name == 'execute_long_click':
                    kind = 'execute_long_click'
                elif name == 'long_click' and isinstance(func, ast.Attribute):
                    kind = 'raw_long_click'
                elif name.startswith('long_click_'):
                    kind = 'raw_long_backend'
                else:
                    continue
                if rel == 'module/click_pipeline.py':
                    area = 'executor'
                elif rel == 'tasks/base_task.py':
                    area = 'primitive'
                elif rel.startswith('module/device/'):
                    area = 'device_internal'
                else:
                    area = 'consumer'
                out.append({'file': rel, 'line': node.lineno, 'kind': kind, 'area': area})
    out.sort(key=lambda r: (r['file'], r['line']))
    return out


def _timing_of(site: dict) -> str:
    if site['policy']:
        return site['policy'].replace('InteractionPolicy.', '')
    if site['confirm_delay']:
        return 'confirm_delay'
    return 'IMMEDIATE'


def _rule_classify(site: dict) -> tuple[str, str]:
    module, func = site['module'], site['func'].lower()
    if site['file'] == 'tasks/base_task.py' or site['file'].startswith('module/'):
        return 'PRIMITIVE', 'R0'
    if module in EXCLUDED_MODULES:
        return 'EXCLUDED', 'R1'
    if site['policy'] or site['confirm_delay']:
        return 'ALREADY_L2', 'R2'
    if module in PROTECTED_MODULES:
        # 受保护业务里的点击（含已迁到 L1 执行器的）仍由所在状态机拥有 timing：先按 R3 归类，再看是否走执行器
        return 'KEEP_SPECIAL', 'R3'
    if site['kind'] == 'execute_single_click':
        return 'KEEP_IMMEDIATE', 'R10'
    if any(h in func for h in SPECIAL_FUNC_HINTS) or func.startswith('run_on_'):
        return 'KEEP_SPECIAL', 'R4'
    if site['kind'] in ('raw_device_click', 'raw_backend'):
        return 'KEEP_IMMEDIATE', 'R5'
    if site['kind'] == 'click':
        return 'KEEP_IMMEDIATE', 'R6'
    if site['kind'] != 'appear_then_click':
        return 'KEEP_IMMEDIATE', 'R7'
    if not site['in_loop']:
        return 'NEEDS_C', 'R9'
    return 'KEEP_IMMEDIATE', 'R8'


def classify_all(sites: list[dict], audited_rows: list[tuple] | None = None) -> list[dict]:
    """给每个调用点填 decision / basis / reason。`audited_rows` 是 L2-2 的 INVENTORY（文件, 函数, 调用, 目标, timing, 分类），
    按文件、按源码顺序与「审计调用名」的调用点一一对齐；对不上（数量 / 顺序漂移）时**不静默兜底**，直接抛错。"""
    human: dict[str, list[tuple]] = {}
    for row in audited_rows or ():
        human.setdefault(row[0], []).append(row)
    cursor = {file: 0 for file in human}
    for site in sites:
        site['timing'] = _timing_of(site)
        site['basis'], site['decision'], site['reason'] = 'rule', *_rule_classify(site)
        file = site['file']
        # L2-2 的 `click` 只统计 `self.click(...)`（`task.click` 这类别的接收者不在其审计口径内，走规则分类）
        aligned = site['kind'] in AUDIT_CALL_NAMES and not (site['kind'] == 'click' and site['chain'] != 'self.click')
        if file in human and aligned:
            rows = human[file]
            idx = cursor[file]
            if idx >= len(rows):
                raise AssertionError(f'{file} 的点击调用点多于 L2-2 审计清单（第 {idx + 1} 个）')
            _, func, call, target, timing, decision = rows[idx]
            if (site['func'], site['kind'], site['target'], site['timing']) != (func, call, target, timing):
                raise AssertionError(f'{file}:{site["line"]} 与 L2-2 审计清单第 {idx + 1} 行不一致：'
                                     f'{(site["func"], site["kind"], site["target"], site["timing"])} != {(func, call, target, timing)}')
            cursor[file] += 1
            site['basis'], site['decision'], site['reason'] = 'human', decision, 'H'
    for file, func, target, policy in C1_MIGRATED:
        hits = [s for s in sites if (s['file'], s['func'], s['kind'], s['target']) == (file, func, 'appear_then_click', target)]
        if len(hits) != 1 or hits[0]['policy'] != policy:
            raise AssertionError(f'C1 已迁移清单与源码不一致：{file}::{func} {target} 应恰有一处 policy={policy}，实际 {[h["policy"] for h in hits]}')
        hits[0]['basis'], hits[0]['decision'], hits[0]['reason'] = 'c0', 'ALREADY_L2', 'C1'
    for site in sites:
        site.setdefault('dev_status', '-')
        site.setdefault('c0_reviewed', False)
        site.setdefault('c0_advice', '-')
        site.setdefault('c0_note', '')
    for site in sites:
        if site['reason'] == 'C1':
            site['dev_status'], site['c0_reviewed'] = 'COMPLETED', True
            site['c0_advice'] = site['policy'].removeprefix('InteractionPolicy.')
            site['c0_note'] = 'C1-A1 已实施'
    seen_keys = set()
    for file, func, target, occurrence, decision, dev_status, advice, note in C0_TRIAGE:
        hits = [s for s in sites if (s['file'], s['func'], s['kind'], s['target']) == (file, func, 'appear_then_click', target)]
        if len(hits) < occurrence:
            raise AssertionError(f'C0 归档与源码不一致：{file}::{func} {target} 第 {occurrence} 处不存在（共 {len(hits)} 处）')
        site = hits[occurrence - 1]
        key = (file, func, target, occurrence)
        if key in seen_keys:
            raise AssertionError(f'C0 归档重复：{key}')
        seen_keys.add(key)
        if site['policy'] or site['confirm_delay']:
            raise AssertionError(f'C0 归档点位应仍是立即点击，但已声明 reaction：{key} {site["policy"]} {site["confirm_delay"]}')
        if decision == 'NEEDS_C':
            # 技术分类不变（来源沿用 L2-2 人工审计），只补开发排期
            if (site['decision'], site['basis']) != ('NEEDS_C', 'human'):
                raise AssertionError(f'C0 归档应指向 L2-2 的 NEEDS_C 点位：{key} 实际 {(site["decision"], site["basis"])}')
        else:
            site['basis'], site['decision'] = 'c0', decision
            site['reason'] = {'KEEP_IMMEDIATE': 'C0K', 'KEEP_SPECIAL': 'C0S', 'DEFERRED': 'C0D'}[decision]
        site['dev_status'], site['c0_reviewed'], site['c0_advice'], site['c0_note'] = dev_status, True, advice, note
    for file, idx in cursor.items():
        if idx != len(human[file]):
            raise AssertionError(f'{file} 的点击调用点少于 L2-2 审计清单（{idx}/{len(human[file])}）')
    return sites


DECISIONS = ('MIGRATE', 'ALREADY_L2', 'KEEP_IMMEDIATE', 'KEEP_SPECIAL', 'NEEDS_C', 'DEFERRED', 'PRIMITIVE', 'EXCLUDED')


def summarize(sites: list[dict]) -> dict:
    by_decision = Counter(s['decision'] for s in sites)
    by_basis = Counter(s['basis'] for s in sites)
    by_module: dict[str, Counter] = {}
    for s in sites:
        by_module.setdefault(s['module'], Counter())[s['decision']] += 1
    return {
        'total': len(sites), 'by_decision': by_decision, 'by_basis': by_basis, 'by_module': by_module,
        'by_kind': Counter(s['kind'] for s in sites),
        'policy_sites': sum(1 for s in sites if s['policy']),
        'c1_done': sum(1 for s in sites if s['reason'] == 'C1'),
        'c0_reviewed': sum(1 for s in sites if s.get('c0_reviewed')),
        'c0_dev_status': Counter(s['dev_status'] for s in sites if s.get('c0_reviewed')),
        'c0_decisions': Counter(s['decision'] for s in sites if s.get('c0_reviewed')),
        'confirm_delay_sites': sum(1 for s in sites if s['confirm_delay']),
        'l1_pipeline_sites': sum(1 for s in sites if s['kind'] == 'execute_single_click'),
        'raw_click_sites': sum(1 for s in sites if s['kind'] in ('raw_device_click', 'raw_backend')),
        # 裸点击的构成：底层 / 非点击（`module/`）、BaseTask primitive 自身、生产消费点、项目排除
        'raw_module': sum(1 for s in sites if s['kind'] in ('raw_device_click', 'raw_backend') and s['file'].startswith('module/')),
        'raw_primitive': sum(1 for s in sites if s['kind'] in ('raw_device_click', 'raw_backend') and s['file'] == 'tasks/base_task.py'),
        'raw_excluded': sum(1 for s in sites if s['kind'] in ('raw_device_click', 'raw_backend') and s['decision'] == 'EXCLUDED'),
        'executor_in_primitive': sum(1 for s in sites if s['kind'] == 'execute_single_click' and s['file'] == 'tasks/base_task.py'),
    }


def render_markdown(sites: list[dict]) -> str:
    s = summarize(sites)
    lines = [
        '# L2 Callsite Register（全仓生产点击入口登记册）',
        '',
        '> 由 `dev_tools/click_callsite_register.py --write` 生成，**不要手改**；`tests/test_click_callsite_register.py` 把本表的汇总数字与',
        '> 当前源码扫描逐项对账，新增 / 删除点击调用点会让测试失败，必须重新分类并重新生成。',
        '> 分类术语沿用 `docs/L2_INTERACTION_POLICY_MAP.md`；逐点人工审计的 18 个文件见该文档，本表对它们沿用人工结论（basis=`human`）。',
        '',
        '## 1. 口径与分类来源',
        '',
        '- 统计范围：`tasks/` + `module/` 下所有生产代码里的点击入口调用（`device.click` 裸点、后端直调、`execute_single_click`、',
        '  `self.click(<Rule>)` 与 BaseTask 的 `appear_then_click` / `ui_click*` / `ocr_appear_click` / `list_appear_click` 等 helper）；不含 tests / dev_tools。',
        '- **basis=human**：L2-2 人工逐点审计；**basis=c0**：决定来源是 L2 Stage C0 复核的点位（已迁移的 4 点在 `C1_MIGRATED`，其余在 `C0_TRIAGE` 逐点归档，'
        '对不上源码直接报错）；**basis=rule**：其余模块的**保守规则分类**（默认保持立即点击，不因规则判定加 reaction），',
        '  只能证明「每个点击调用点都有归属且默认不改变原有 timing」，**不是**逐点人工审计。',
        '- 分类互斥：每个调用点恰属于下表 7 个 decision 之一（可加总）。「已迁移 L1」「已接入 L2 policy」是另一个维度（见 §2 覆盖统计），',
        '  与 decision 有交叉，不能与 decision 相加。',
        '',
        '## 2. 汇总',
        '',
        f'- 调用点总数：**{s["total"]}**',
        f'- 按 basis：human **{s["by_basis"].get("human", 0)}** / c0 **{s["by_basis"].get("c0", 0)}** / rule **{s["by_basis"].get("rule", 0)}**',
        f'- 显式调用 `execute_single_click` 的调用点：**{s["l1_pipeline_sites"]}**（其中 BaseTask primitive **{s["executor_in_primitive"]}**）。**这不是「享受 ROI 采样的点击数」**：'
        '  Rule / helper 点击（约 900 处）早在 `Rule*.coord()` 内按 ROI 采样一次，并经 BaseTask primitive 汇入统一执行器。',
        f'- 仍是裸 `device.click` / 后端直调：**{s["raw_click_sites"]}** = 底层与非点击 {s["raw_module"]} + BaseTask primitive {s["raw_primitive"]} + '
        f'生产消费点 {s["raw_click_sites"] - s["raw_module"] - s["raw_primitive"] - s["raw_excluded"]} + 项目排除 {s["raw_excluded"]}。',
        f'- 已显式声明 L2 `policy=`：**{s["policy_sites"]}**；仍用 legacy `confirm_delay=`：**{s["confirm_delay_sites"]}**',
        '',
        '| decision | 数量 |',
        '| --- | ---: |',
    ]
    for d in DECISIONS:
        lines.append(f'| {d} | {s["by_decision"].get(d, 0)} |')
    lines += ['| **合计** | **%d** |' % s['total'], '', '### 2.1 按调用种类', '', '| kind | 数量 |', '| --- | ---: |']
    for kind, n in s['by_kind'].most_common():
        lines.append(f'| {kind} | {n} |')
    long_sites = scan_long_click_sites()
    long_counter = Counter((r['kind'], r['area']) for r in long_sites)
    lines += ['', '### 2.2 长按入口（L1 Stage 3A）', '',
              '长按是独立的物理动作，走 `execute_long_click`，不并入上面的单击统计。生产消费点（consumer）里出现的任何直调都是绕过 L1 的长按。',
              '', '| kind | area | 数量 |', '| --- | --- | ---: |']
    for (kind, area), n in sorted(long_counter.items()):
        lines.append(f'| {kind} | {area} | {n} |')
    from dev_tools import click_entry_guard as guard
    guard_result = guard.check_repo()
    lines += ['', '### 2.3 全局入口守卫（L1 Stage 3B，`dev_tools/click_entry_guard.py`）', '',
              f'- 扫描范围：生产根目录 rglob + 仓库根 `*.py`（新增文件自动纳入，文件数不写进登记册以免无关改动使其失效）；'
              f'未登记的直接点击 / 长按违规：**{len(guard_result.unallowed)}**；过期白名单 / 缺失必需出口 / 无法静态确定：'
              f'**{len(guard_result.stale)} / {len(guard_result.missing_required)} / {len(guard_result.unresolved)}**。',
              '- 白名单出口（精确到 文件 / 函数 / 调用形式 / 次数，不按文件或目录豁免；Login / DailyTrifles / WeeklyPurchase 没有豁免）：',
              '  ' + '，'.join(f'{layer} {n}' for layer, n in sorted(guard_result.allowed_by_layer.items())) + '。',
              '- 守卫只证明「没有绕过执行器的直接调用」；业务点击是否执行成功 / 坐标分布由运行期测试负责。滑动 / 拖动不在守卫范围。']
    needs_c_deferred = sum(1 for x in sites if x.get('c0_reviewed') and x['decision'] == 'NEEDS_C')
    lines += ['', '### 2.4 C0 复核批次（L2 Stage C0 → C1-A1）与开发状态', '',
              '- **两个维度，不可相加**：`decision` = 技术分类（互斥、可加总，见 §2 表）；`dev_status` = 开发排期（只对 C0 复核的点位有意义：COMPLETED / DEFERRED / NOT_APPLICABLE）。'
              '`NEEDS_C` + `DEFERRED` = 技术上需要真机依据、且用户决定暂缓；`decision=DEFERRED` = C0 技术建议为 MIGRATE、但用户决定暂缓（原建议保留在下表「C0 建议」列）。'
              '**DEFERRED 是用户排期决策，不是技术完成，也不是永久禁止。**',
              f'- **口径区分**：全仓点击调用点 **{s["total"]}**（本表）；最初 L2-2 人工审计 **{s["by_basis"].get("human", 0)}**（basis=human，历史结论不改写）；'
              f'C0 复核的原 NEEDS_C **{s["c0_reviewed"]}**（`c0_reviewed`，与 basis 不是互斥维度：其中 GeneralInvite / GeneralBattle 7 点的决定来源仍是 human）；'
              f'C1-A1 已实际迁移 **{s["c1_done"]}**。',
              f'- **basis 统计**（互斥、可加总）：human **{s["by_basis"].get("human", 0)}** / c0 **{s["by_basis"].get("c0", 0)}** / rule **{s["by_basis"].get("rule", 0)}**。',
              f'- **C0 24 点的开发状态**：COMPLETED **{s["c0_dev_status"].get("COMPLETED", 0)}** / DEFERRED **{s["c0_dev_status"].get("DEFERRED", 0)}**'
              f'（decision=DEFERRED {s["c0_decisions"].get("DEFERRED", 0)} + decision=NEEDS_C {needs_c_deferred}）'
              f' / NOT_APPLICABLE **{s["c0_dev_status"].get("NOT_APPLICABLE", 0)}**'
              f'（KEEP_IMMEDIATE {s["c0_decisions"].get("KEEP_IMMEDIATE", 0)} + KEEP_SPECIAL {s["c0_decisions"].get("KEEP_SPECIAL", 0)}，已有明确决策，不属于迁移积压）。',
              '', '| # | 文件 | 函数 | 目标 | C0 建议 | decision | dev_status | 说明 |', '| ---: | --- | --- | --- | --- | --- | --- | --- |']
    order = {'COMPLETED': 0, 'DEFERRED': 1, 'NOT_APPLICABLE': 2}
    c0_rows = sorted((x for x in sites if x.get('c0_reviewed')),
                     key=lambda x: (order[x['dev_status']], DECISIONS.index(x['decision']), x['file'], x['line']))
    for n, x in enumerate(c0_rows, 1):
        lines.append(f'| {n} | `{x["file"].removeprefix("tasks/")}` | `{x["func"]}` | `{x["target"]}` | {x["c0_advice"]} | '
                     f'{x["decision"]} | {x["dev_status"]} | {x["c0_note"]} |')
    lines += ['', '## 3. 按模块', '', '| module | 合计 | ' + ' | '.join(DECISIONS) + ' |', '| --- | ---: | ' + ' | '.join(['---:'] * len(DECISIONS)) + ' |']
    for module, counter in sorted(s['by_module'].items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        lines.append(f'| {module} | {sum(counter.values())} | ' + ' | '.join(str(counter.get(d, 0)) for d in DECISIONS) + ' |')
    lines += ['', '## 4. 理由代码', '', '| 代码 | 含义 |', '| --- | --- |']
    for code, text in REASONS.items():
        lines.append(f'| {code} | {text} |')
    lines += ['', '## 5. 逐点清单', '',
              '列：`#` 序号 / 文件 / 函数#函数内第几个点击调用点（不写行号，避免无关改动让登记册失效）/ 调用 / 目标 / timing（当前延迟来源）/ 循环内 / 函数内已有等待 / decision / 依据。',
              '「状态机」列不单独给出：由 decision=KEEP_SPECIAL 与理由 R3 / R4 表达。', '']
    current = None
    for i, site in enumerate(sites, 1):
        if site['module'] != current:
            current = site['module']
            lines += ['', f'### {current}', '', '| # | 位置 | 函数 | 调用 | 目标 | timing | 循环 | 已有等待 | decision | 依据 |',
                      '| ---: | --- | --- | --- | --- | --- | :-: | --- | --- | --- |']
        waits = ','.join(site['waits']) or '-'
        target = site['target'].replace('|', '\\|')
        lines.append(f'| {i} | `{site["file"].removeprefix("tasks/")}` | `{site["qual"]}#{site["ordinal"]}` | {site["kind"]} | `{target}` | '
                     f'{site["timing"]} | {"Y" if site["in_loop"] else "-"} | {waits} | {site["decision"]} | {site["basis"]}/{site["reason"]} |')
    return '\n'.join(lines) + '\n'


def load_audited_rows() -> list[tuple]:
    sys.path.insert(0, str(REPO))
    from tests.test_l2_policy_migration import INVENTORY
    return [tuple(row) for row in INVENTORY]


def main(argv: list[str]) -> int:
    sites = classify_all(scan_sites(), load_audited_rows())
    summary = summarize(sites)
    print(f'total={summary["total"]} basis={dict(summary["by_basis"])} decisions={dict(summary["by_decision"])}')
    print(f'policy={summary["policy_sites"]} confirm_delay={summary["confirm_delay_sites"]} '
          f'l1_pipeline={summary["l1_pipeline_sites"]} raw={summary["raw_click_sites"]}')
    if '--write' in argv:
        target = REPO / 'docs' / 'L2_CALLSITE_REGISTER.md'
        target.write_text(render_markdown(sites), encoding='utf-8')
        print(f'wrote {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
