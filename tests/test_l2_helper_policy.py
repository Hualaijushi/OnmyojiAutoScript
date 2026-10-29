# This Python file uses the following encoding: utf-8
"""BaseTask 点击类公共方法的可选 L2 `policy`，以及每日琐事 / 狩猎战 / 集体任务「所有点击都带档位」的静态守卫。

2026-10-23 用户决定这三个任务里任何点击都要接入通用延迟点击模型：
- `click(policy)`：点固定区域，没有能在新截图里再确认的目标，只在点击前加反应时间；
- `ui_click` / `ui_click_until_disappear` / `ui_click_until_appear_or_timeout` / `ui_reward_appear_click` /
  `ui_get_reward(policy, close_policy)`：把档位透传给 `appear_then_click` / `click`；
- 不传 policy 时调用形状与原来完全一样（不往下传 `policy` 这个参数，子类 / 替身的旧签名照常可用）。
"""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.atom.click import RuleClick
from module.atom.long_click import RuleLongClick
from module.interaction_policy import InteractionPolicy as P, resolve_reaction_range
from tasks.base_task import BaseTask
from tasks.GlobalGame.assets import GlobalGameAssets

_REPO = Path(__file__).resolve().parents[1]
IMAGE = GlobalGameAssets.I_UI_CANCEL_SAMLL
STOP = GlobalGameAssets.I_UI_CONFIRM_SAMLL


class _Helpers:
    """只借 BaseTask 的这几个方法，画面与底层点击都换成替身。"""
    click = BaseTask.click
    ui_click = BaseTask.ui_click
    ui_click_until_disappear = BaseTask.ui_click_until_disappear
    ui_click_until_appear_or_timeout = BaseTask.ui_click_until_appear_or_timeout
    ui_reward_appear_click = BaseTask.ui_reward_appear_click
    ui_get_reward = BaseTask.ui_get_reward


class ClickReactionTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.t = _Helpers()
        self.t.interval_timer = {}
        self.t.device = SimpleNamespace()
        for name, target in (('sleep', lambda s: self.events.append(('sleep', s))),
                             ('random_delay', lambda lo, hi: self.events.append(('reaction', lo, hi)) or lo),
                             ('execute_single_click', lambda *a, **k: self.events.append(('click',))),
                             ('execute_long_click', lambda *a, **k: self.events.append(('long',)))):
            patcher = patch(f'tasks.base_task.{name}', side_effect=target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.rule = RuleClick(roi_front=(100, 100, 20, 20), roi_back=(100, 100, 20, 20), name='C_TEST')

    def test_without_policy_clicks_immediately(self):
        self.t.click(self.rule)
        self.assertEqual(self.events, [('click',)])

    def test_immediate_is_the_same_as_no_policy(self):
        self.t.click(self.rule, policy=P.IMMEDIATE)
        self.assertEqual(self.events, [('click',)])

    def test_policy_waits_a_reaction_before_the_click(self):
        self.t.click(self.rule, policy=P.NAVIGATION)
        lo, hi = resolve_reaction_range(P.NAVIGATION)
        self.assertEqual(self.events, [('reaction', lo, hi), ('sleep', lo), ('click',)])

    def test_long_click_also_waits(self):
        long = RuleLongClick(roi_front=(100, 100, 20, 20), roi_back=(100, 100, 20, 20), duration=500, name='L_TEST')
        self.t.click(long, policy=P.NORMAL)
        self.assertEqual([e[0] for e in self.events], ['reaction', 'sleep', 'long'])

    def test_interval_not_reached_neither_waits_nor_clicks(self):
        self.assertTrue(self.t.click(self.rule, interval=10, policy=P.NORMAL))
        self.events.clear()
        self.assertFalse(self.t.click(self.rule, interval=10, policy=P.NORMAL))
        self.assertEqual(self.events, [])

    def test_fsm_owned_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            self.t.click(self.rule, policy=P.FIRE_SPECIAL)
        self.assertEqual(self.events, [])


class HelperPassThroughTest(unittest.TestCase):
    def make(self, appear=False):
        t = _Helpers()
        t.screenshot = Mock()
        t.appear = Mock(return_value=appear)
        t.appear_then_click = Mock(return_value=False)
        t.click = Mock(return_value=False)
        t.I_UI_REWARD = 'I_UI_REWARD'
        t.C_UI_REWARD = 'C_UI_REWARD'
        return t

    def test_ui_click_passes_policy_to_both_branches(self):
        t = self.make()
        t.appear.side_effect = [False, True]
        t.ui_click(IMAGE, STOP, policy=P.NORMAL)
        self.assertEqual(t.appear_then_click.call_args.kwargs['policy'], P.NORMAL)
        t = self.make()
        t.appear.side_effect = [False, True]
        rule = RuleClick(roi_front=(1, 1, 2, 2), roi_back=(1, 1, 2, 2), name='C')
        t.ui_click(rule, STOP, policy=P.FAST)
        self.assertEqual(t.click.call_args.kwargs['policy'], P.FAST)

    def test_ui_click_until_disappear_passes_policy(self):
        t = self.make()
        t.appear.side_effect = [True, False]
        t.ui_click_until_disappear(IMAGE, policy=P.CONFIRM)
        self.assertEqual(t.appear_then_click.call_args.kwargs['policy'], P.CONFIRM)

    def test_ui_click_until_appear_or_timeout_passes_policy(self):
        t = self.make()
        t.appear.side_effect = [False, True]
        self.assertTrue(t.ui_click_until_appear_or_timeout(IMAGE, stop=STOP, policy=P.NORMAL))
        self.assertEqual(t.appear_then_click.call_args.kwargs['policy'], P.NORMAL)

    def test_ui_reward_appear_click_passes_policy(self):
        t = self.make()
        t.ui_reward_appear_click(policy=P.NAVIGATION)
        self.assertEqual(t.appear_then_click.call_args.kwargs['policy'], P.NAVIGATION)

    def test_ui_get_reward_uses_policy_for_the_target_and_close_policy_for_the_reward(self):
        t = self.make()
        shown = {'reward': False}

        def atc(target, **kw):
            if target == 'I_UI_REWARD':
                if shown['reward']:
                    shown['reward'] = False
                    return True
                return False
            shown['reward'] = True
            return True

        t.appear_then_click.side_effect = atc
        t.appear.side_effect = lambda rule, **kw: rule == 'I_UI_REWARD' and shown['reward']
        with patch('tasks.base_task.sleep'):
            t.ui_get_reward(IMAGE, policy=P.NORMAL, close_policy=P.NAVIGATION)
        used = {(c.args[0], c.kwargs.get('policy')) for c in t.appear_then_click.call_args_list}
        self.assertIn((IMAGE, P.NORMAL), used)
        self.assertIn(('I_UI_REWARD', P.NAVIGATION), used)
        self.assertNotIn(('I_UI_REWARD', P.NORMAL), used)

    def test_without_policy_the_policy_argument_is_not_passed_down(self):
        # 子类 / 测试替身里 click、appear_then_click 的旧签名没有 policy
        t = self.make()
        t.appear.side_effect = [False, True, True, False, False, True]
        t.ui_click(IMAGE, STOP)
        t.ui_click_until_disappear(IMAGE)
        t.ui_click_until_appear_or_timeout(IMAGE, stop=STOP)
        t.ui_reward_appear_click()
        for c in t.appear_then_click.call_args_list:
            self.assertNotIn('policy', c.kwargs)


# 三个任务里会产生点击的调用：除了下面这些都必须带 `policy=`；ui_get_reward 还要带 `close_policy=`
CLICK_CALLS = {'appear_then_click', 'click', 'ui_click', 'ui_click_until_disappear', 'ui_click_until_appear_or_timeout',
               'ui_click_until_smt_disappear', 'ui_clicks', 'ui_get_reward', 'ui_reward_appear_click',
               'ocr_appear_click', 'list_appear_click', 'long_click'}
COVERED_FILES = ('tasks/DailyTrifles/script_task.py', 'tasks/Hunt/script_task.py',
                 'tasks/CollectiveMissions/script_task.py')


def _click_calls(rel):
    tree = ast.parse((_REPO / rel).read_text(encoding='utf-8'))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'self' \
                and node.func.attr in CLICK_CALLS:
            out.append(node)
    return tree, out


class AllClicksUseTheClickModelTest(unittest.TestCase):
    def test_every_click_call_has_a_policy(self):
        for rel in COVERED_FILES:
            _, calls = _click_calls(rel)
            self.assertTrue(calls, rel)
            for call in calls:
                kws = {k.arg: k.value for k in call.keywords}
                with self.subTest(file=rel, line=call.lineno, call=call.func.attr):
                    self.assertIn('policy', kws)
                    self.assertIsInstance(kws['policy'], ast.Attribute)
                    self.assertEqual(getattr(kws['policy'].value, 'id', ''), 'InteractionPolicy')
                    if call.func.attr == 'ui_get_reward':
                        self.assertIn('close_policy', kws)

    def test_direct_executor_calls_are_preceded_by_a_reaction(self):
        # 今忆召唤的预设点击直接调 execute_single_click：同一代码块里紧挨的上一句必须是反应时间
        tree, _ = _click_calls('tasks/DailyTrifles/script_task.py')
        found = 0
        for node in ast.walk(tree):
            for field in ('body', 'orelse'):
                stmts = getattr(node, field, None)
                if not isinstance(stmts, list):
                    continue
                for i, stmt in enumerate(stmts):
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) \
                            and getattr(stmt.value.func, 'id', '') == 'execute_single_click':
                        found += 1
                        self.assertGreater(i, 0)
                        self.assertIn('resolve_reaction_range', ast.unparse(stmts[i - 1]))
        self.assertEqual(found, 1)
        for rel in COVERED_FILES[1:]:
            self.assertNotIn('execute_single_click', (_REPO / rel).read_text(encoding='utf-8'))
            self.assertNotIn('device.click(', (_REPO / rel).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
