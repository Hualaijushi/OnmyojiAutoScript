# This Python file uses the following encoding: utf-8
"""L2 Stage C0 逐点归档的登记册对账：技术分类（decision）与开发排期（dev_status）是两个维度，不能混成一个概念。

C0 复核了原 24 个 NEEDS_C，结论 + 用户排期决策后的实际状态（期望值在本文件里**独立写死**，不从生成器的归档表推导）：

| 状态 | 数量 | decision | dev_status |
|---|---:|---|---|
| 已完成迁移（C1-A1） | 4 | ALREADY_L2 | COMPLETED |
| C0 建议 MIGRATE、用户暂缓 | 6 | DEFERRED | DEFERRED |
| 保持即时 | 3 | KEEP_IMMEDIATE | NOT_APPLICABLE |
| 保持专用时序 | 4 | KEEP_SPECIAL | NOT_APPLICABLE |
| 需要 Level C 依据、用户暂缓 | 7 | NEEDS_C（沿用 L2-2 人工审计来源） | DEFERRED |

本测试只读登记册与源码，不改任何业务行为；「已完成」与「暂缓」不能混淆——暂缓的点位必须仍是立即点击。
"""

import copy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from dev_tools import click_callsite_register as reg

_REPO = Path(__file__).resolve().parents[1]
REGISTER_DOC = _REPO / 'docs' / 'L2_CALLSITE_REGISTER.md'

DONE = {
    ('tasks/Dokan/page.py', 'priority_enter_dokan', 'target_priority'): 'InteractionPolicy.NORMAL',
    ('tasks/Pets/script_task.py', '_feed', 'self.I_UI_BACK_CIRCLE'): 'InteractionPolicy.NAVIGATION',
    ('tasks/SixRealms/common.py', 'refresh_store', 'refresh_rule'): 'InteractionPolicy.CONFIRM',
    ('tasks/SixRealms/common.py', 'choose_and_enter_island', 'target_land'): 'InteractionPolicy.NORMAL',
}
DEFERRED_MIGRATE = {                                    # (文件, 函数, 目标): C0 建议
    ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN'): 'MIGRATE / NORMAL',
    ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN2'): 'MIGRATE / NORMAL',
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_summon_store', 'self.I_M_STORE_ACTIVITY'): 'MIGRATE / NORMAL',
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_summon_store', 'self.I_UI_CONFIRM'): 'MIGRATE / CONFIRM',
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_use_breath', 'self.I_M_STORE_ACTIVITY'): 'MIGRATE / NORMAL',
    ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_confirm_store_entry', 'self.I_PK_STORE_STILLIN'): 'MIGRATE / CONFIRM',
}
KEEP_IMMEDIATE = {
    ('tasks/DemonRetreat/script_task.py', 'run', 'self.I_DEMON_BACK_CHECK'),
    ('tasks/Quiz/script_task.py', '_deal_quiz', 'self.I_ALONE_ENSURE'),
    ('tasks/SixRealms/common.py', 'open_shop', 'self.I_UI_CANCEL'),
}
KEEP_SPECIAL = {
    ('tasks/Component/Buy/buy.py', 'buy_more', 'self.I_BUY_PLUS'),                      # 两处
    ('tasks/SixRealms/page.py', 'switch_moon_sea_shikigami', 'SixRealmsAssets.I_MSHOUZU_SELECT'),
    ('tasks/SixRealms/peacock_kingdom/base_peacock_kingdom.py', '_mark_peacock_boss', 'self.I_LOCAL'),
}
NEEDS_C_DEFERRED = {
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_NO_DEFAULT'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_GI_SURE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT_DEFAULT'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'self.I_I_ACCEPT_APPRENTICE'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'self.I_DISABLE_7DAYS_DIFF_SOUL'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'self.I_CONFIRM_CLOSE_DIFF_SOUL'),
}


_RAW_SCAN = []


def fresh_sites():
    """AST 扫描全仓约 1 秒，只做一次；每个用例拿深拷贝（classify_all 会就地改写 site 字典）。"""
    if not _RAW_SCAN:
        _RAW_SCAN.append(reg.scan_sites())
    return copy.deepcopy(_RAW_SCAN[0])


def _key(site):
    return site['file'], site['func'], site['target']


class C0RegistryTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = reg.classify_all(fresh_sites(), reg.load_audited_rows())
        cls.summary = reg.summarize(cls.sites)
        cls.c0 = [s for s in cls.sites if s['c0_reviewed']]

    def by_key(self, decision=None, dev_status=None):
        return [s for s in self.c0 if (decision is None or s['decision'] == decision)
                and (dev_status is None or s['dev_status'] == dev_status)]

    # ---- 24 点逐项对账 ----
    def test_exactly_24_points_are_c0_reviewed_and_each_matches_one_source_site(self):
        self.assertEqual(len(self.c0), 24)
        self.assertEqual(len({(s['file'], s['func'], s['target'], s['ordinal']) for s in self.c0}), 24)   # 没有重复登记

    def test_four_completed_points_keep_their_declared_policy(self):
        done = self.by_key('ALREADY_L2', 'COMPLETED')
        self.assertEqual({_key(s): s['policy'] for s in done}, DONE)
        for s in done:
            self.assertEqual((s['basis'], s['reason']), ('c0', 'C1'))

    def test_six_deferred_migrations_are_still_immediate_and_keep_the_c0_advice(self):
        deferred = self.by_key('DEFERRED')
        self.assertEqual({_key(s): s['c0_advice'] for s in deferred}, DEFERRED_MIGRATE)
        for s in deferred:
            with self.subTest(site=_key(s)):
                self.assertEqual((s['dev_status'], s['basis'], s['reason']), ('DEFERRED', 'c0', 'C0D'))
                self.assertEqual((s['policy'], s['confirm_delay'], s['timing']), (None, None, 'IMMEDIATE'))   # 暂缓 = 代码里没有 reaction

    def test_three_keep_immediate_points_are_not_migration_backlog(self):
        keep = self.by_key('KEEP_IMMEDIATE')
        self.assertEqual({_key(s) for s in keep}, KEEP_IMMEDIATE)
        self.assertEqual(len(keep), 3)
        for s in keep:
            self.assertEqual((s['dev_status'], s['reason'], s['timing']), ('NOT_APPLICABLE', 'C0K', 'IMMEDIATE'))

    def test_four_keep_special_points_keep_their_own_timing_owner(self):
        keep = self.by_key('KEEP_SPECIAL')
        self.assertEqual({_key(s) for s in keep}, KEEP_SPECIAL)
        self.assertEqual(len(keep), 4)                                                    # Buy.buy_more 两处 + 两处
        self.assertEqual(sum(1 for s in keep if s['func'] == 'buy_more'), 2)
        for s in keep:
            self.assertEqual((s['dev_status'], s['reason'], s['timing']), ('NOT_APPLICABLE', 'C0S', 'IMMEDIATE'))

    def test_seven_needs_c_points_stay_needs_c_with_deferred_schedule(self):
        needs = self.by_key('NEEDS_C')
        self.assertEqual({_key(s) for s in needs}, NEEDS_C_DEFERRED)
        self.assertEqual(len(needs), 7)
        for s in needs:
            with self.subTest(site=_key(s)):
                self.assertEqual(s['dev_status'], 'DEFERRED')                             # 排期是暂缓，技术分类不变
                self.assertEqual((s['basis'], s['reason']), ('human', 'H'))               # 技术结论来源仍是 L2-2 人工审计
                self.assertEqual((s['policy'], s['confirm_delay']), (None, None))

    def test_dev_status_and_decision_are_never_conflated(self):
        # NEEDS_C + DEFERRED 与 decision=DEFERRED 是两种不同的东西：前者需要证据，后者是已有技术建议但用户暂缓
        self.assertEqual(len(self.by_key('NEEDS_C', 'DEFERRED')), 7)
        self.assertEqual(len(self.by_key('DEFERRED', 'DEFERRED')), 6)
        self.assertEqual(self.by_key('ALREADY_L2', 'DEFERRED'), [])
        self.assertEqual(self.by_key('DEFERRED', 'COMPLETED'), [])
        self.assertEqual(self.summary['c0_dev_status'], {'COMPLETED': 4, 'DEFERRED': 13, 'NOT_APPLICABLE': 7})

    # ---- 全仓统计口径 ----
    def test_decisions_are_mutually_exclusive_and_sum_to_the_total(self):
        d = self.summary['by_decision']
        self.assertEqual(sum(d.values()), self.summary['total'])
        # 本分支（synevo）的真实全仓数字，不沿用 master 的 1092：synevo 多出 AccountRotation /
        # MultiAccountEvo / SwitchAccount 等轮换业务调用点（大部分落进 EXCLUDED），并多 1 个 EvoZone 收尾点。
        self.assertEqual(self.summary['total'], 1127)
        self.assertEqual({k: d[k] for k in ('MIGRATE', 'ALREADY_L2', 'KEEP_IMMEDIATE', 'KEEP_SPECIAL', 'NEEDS_C', 'DEFERRED', 'PRIMITIVE', 'EXCLUDED')},
                         {'MIGRATE': 7, 'ALREADY_L2': 37, 'KEEP_IMMEDIATE': 631, 'KEEP_SPECIAL': 232, 'NEEDS_C': 7,
                          'DEFERRED': 6, 'PRIMITIVE': 35, 'EXCLUDED': 172})

    def test_basis_counts_are_reconciled_and_c0_reviewed_is_a_separate_dimension(self):
        basis = self.summary['by_basis']
        self.assertEqual(sum(basis.values()), 1127)
        # basis = 决定来源（互斥）：GeneralInvite / GeneralBattle 的 7 点沿用 L2-2 人工结论，所以 c0 basis = 4 + 6 + 3 + 4 = 17，
        # human 仍是 179；c0_reviewed = 24 是另一个维度（不与 basis 相加）
        # human 180 = master 的 179 + synevo 独有的 EvoZone `_return_to_main_after_run`（按既有 R7/R4 规则归 KEEP_IMMEDIATE）
        self.assertEqual((basis['human'], basis['c0'], basis['rule']), (180, 17, 930))
        self.assertEqual(self.summary['c0_reviewed'], 24)
        self.assertEqual(sum(1 for s in self.c0 if s['basis'] == 'human'), 7)

    def test_only_the_four_completed_points_gained_a_policy_in_c1(self):
        self.assertEqual(self.summary['policy_sites'], 36)
        self.assertEqual(self.summary['c1_done'], 4)
        c0_with_policy = {_key(s) for s in self.c0 if s['policy']}
        self.assertEqual(c0_with_policy, set(DONE))

    def test_l2_2_historical_audit_is_not_rewritten(self):
        human = [s for s in self.sites if s['basis'] == 'human']
        self.assertEqual(len(human), 180)                                                # 179（master L2-2）+ 1（synevo EvoZone 收尾点）
        self.assertEqual(sum(1 for s in human if s['decision'] == 'MIGRATE'), 7)         # L2-2 的 7 个迁移结论原样保留
        self.assertEqual(sum(1 for s in human if s['decision'] == 'NEEDS_C'), 7)

    # ---- 生成器一致性 / 防漂移 ----
    def test_generation_is_repeatable_and_matches_the_committed_markdown(self):
        first = reg.render_markdown(self.sites)
        second = reg.render_markdown(reg.classify_all(fresh_sites(), reg.load_audited_rows()))
        self.assertEqual(first, second)
        self.assertEqual(REGISTER_DOC.read_text(encoding='utf-8'), first,
                         '登记册与生成器不一致：运行 `toolkit\\python.exe -m dev_tools.click_callsite_register --write`')

    def test_markdown_lists_every_c0_point_with_both_dimensions(self):
        text = REGISTER_DOC.read_text(encoding='utf-8')
        start = text.index('### 2.4')
        section = text[start:text.index('## 3. 按模块')]
        for s in self.c0:
            self.assertIn(f'`{s["func"]}` | `{s["target"]}`', section)
        for word in ('COMPLETED', 'DEFERRED', 'NOT_APPLICABLE', 'NEEDS_C', 'KEEP_IMMEDIATE', 'KEEP_SPECIAL', '不是技术完成'):
            self.assertIn(word, section)

    def test_a_triage_entry_that_no_longer_matches_the_source_fails_loudly(self):
        bogus = ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_NOT_THERE', 1, 'DEFERRED', 'DEFERRED', 'MIGRATE / NORMAL', 'x')
        with patch.object(reg, 'C0_TRIAGE', reg.C0_TRIAGE + (bogus,)):
            with self.assertRaises(AssertionError):
                reg.classify_all(fresh_sites(), reg.load_audited_rows())

    def test_a_deferred_point_that_gained_a_reaction_is_rejected(self):
        sites = fresh_sites()
        target = next(s for s in sites if (s['file'], s['func'], s['target']) == ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN'))
        target['policy'] = 'InteractionPolicy.NORMAL'                                     # 模拟有人偷偷给暂缓点位加了 policy
        with self.assertRaises(AssertionError):
            reg.classify_all(sites, reg.load_audited_rows())

    def test_a_needs_c_entry_must_point_at_the_l2_2_needs_c_site(self):
        wrong = ('tasks/Duel/script_task.py', 'enter_practice_ban_mode', 'self.I_BATTLE_WITH_TRAIN', 1, 'NEEDS_C', 'DEFERRED', '-', 'x')
        replaced = tuple(e for e in reg.C0_TRIAGE if e[2] != 'self.I_BATTLE_WITH_TRAIN') + (wrong,)
        with patch.object(reg, 'C0_TRIAGE', replaced):
            with self.assertRaises(AssertionError):
                reg.classify_all(fresh_sites(), reg.load_audited_rows())
