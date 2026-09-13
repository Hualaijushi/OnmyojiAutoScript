# This Python file uses the following encoding: utf-8
"""`RealmRaid` 状态机迁移前的 characterization（现状锁定）测试。

目的：在把个人突破流程迁移到「状态 → 动作 → 期望状态 → 显式验证」结构 **之前**，用纯
mock 锁住当前真实的动作序列、进入战斗的判定语义、循环边界、GeneralBattle 交接方式，
作为未来迁移的回归基线。

这些测试只描述「现在是什么样」，包括几处既有瑕疵（`fire()` 只靠「旧页面标识
`I_RR_PERSON` 消失」推断已进入战斗、永远不会返回 False 导致 `run()` 里
`if not self.fire(index)` 是不可达分支、多处 `while True` / `wait_until_appear` 无超时）
也照实锁定——这些**与 Level C 状态迁移耦合，本轮不修**。
2026-09-02 cleanup 批次 1 已删除的零调用方死代码（`medal_fire` / `is_ticket` /
`medal_grid` / `RealmRaid`·`AttackNumber` 死 import / `import time`）由
`DeadCodeAndStructureTest` 守卫「不被重新引入」。详见 `docs/RealmRaid状态机静态收口.md`
与 `docs/状态验证与重试模式归纳.md` §16。

源码：`tasks/RealmRaid/script_task.py`。
"""

import ast
import inspect
import itertools
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

import numpy as np

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.RealmRaid.script_task import ScriptTask as RR


def _src(func):
    return inspect.getsource(func)


def _fake_click(name, roi):
    return RuleClick(roi_front=roi, roi_back=roi, name=name)


class _Harness:
    """只挂载被测方法需要的成员，不构造真实 Device / Config。"""

    def __init__(self):
        self.task = RR.__new__(RR)
        self.events = []
        self.task.device = SimpleNamespace(
            image='FRAME',
            image_frame_id='FID',
            click_record_clear=Mock(side_effect=lambda: self.events.append('click_record_clear')),
        )
        self.task.screenshot = Mock(side_effect=lambda: self.events.append('screenshot'))
        self.task.wait_until_appear = Mock(
            side_effect=lambda t, **kw: self.events.append(('wait_until_appear', t.name, kw)))


# --------------------------------------------------------------------------------------
# fire() —— R-R1 收口后：正向战斗确认 + FIRE reaction + 有限 attempt / timeout
# （2026-09-08 起，见 tests/test_fire_reaction_fsm.py 的完整行为测试；本处只锁 RealmRaid
#  侧的结构事实：不再「旧标识消失即成功」、可返回 False、bounded）
# --------------------------------------------------------------------------------------

class _RRFakeTimer:
    """确定性 Timer 替身：单实例 reached() 超过 budget 次即到期（防真实 wall-clock 等待）。"""
    budget = 6

    def __init__(self, limit, *a, **kw):
        self.limit = limit
        self._n = 0

    def start(self):
        return self

    def reached(self):
        self._n += 1
        return self._n > _RRFakeTimer.budget


def _tail_seq(values):
    values = list(values) or [False]
    for v in values:
        yield v
    while True:
        yield values[-1]


class FireCharacterizationTest(TestCase):
    def setUp(self):
        _RRFakeTimer.budget = 6
        for tgt in ('Timer', 'sleep', 'random_delay'):
            p = patch(f'tasks.RealmRaid.script_task.{tgt}',
                      _RRFakeTimer if tgt == 'Timer' else Mock(return_value=0.5))
            p.start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_RRFakeTimer, 'budget', 6))

    def _mk(self, *, in_battle=None, fire_visible=None, rr_person=None, back_red=None):
        h = _Harness()
        t = h.task
        t.__dict__['partition'] = [_fake_click(f'partition_{i}', (i * 10, 0, 9, 9)) for i in range(1, 10)]
        t.is_in_battle = Mock(side_effect=_tail_seq(in_battle or [False]))
        fire_it = _tail_seq(fire_visible or [False])
        rr_it = _tail_seq(rr_person or [False])
        back_it = _tail_seq(back_red or [False])

        def _appear(tgt, **kw):
            if tgt.name == t.I_FIRE.name:
                return next(fire_it)
            if tgt.name == t.I_RR_PERSON.name:
                return next(rr_it)
            if tgt.name == t.I_BACK_RED.name:
                return next(back_it)
            return False

        t.appear = Mock(side_effect=_appear)
        t.appear_then_click = Mock(return_value=True)
        t.click = Mock(return_value=True)
        return h, t

    def test_prologue_order_wait_then_clear_record_then_loop(self):
        h, t = self._mk(in_battle=[True])
        t.fire(3)
        self.assertEqual(h.events[0][0], 'wait_until_appear')
        self.assertEqual(h.events[0][1], t.I_RR_PERSON.name)
        self.assertEqual(h.events[1], 'click_record_clear')
        self.assertEqual(h.events[2], 'screenshot')

    def test_entry_wait_is_bounded_by_wait_time(self):
        h, t = self._mk(in_battle=[True])
        t.fire(1)
        self.assertIn('wait_time', h.events[0][2])
        self.assertGreater(h.events[0][2]['wait_time'], 0)

    def test_positive_battle_confirmation_returns_true_without_click(self):
        h, t = self._mk(in_battle=[True])
        self.assertIs(t.fire(1), True)
        t.appear_then_click.assert_not_called()
        t.click.assert_not_called()

    def test_old_marker_gone_but_not_battle_is_not_success(self):
        # I_RR_PERSON / I_FIRE / I_BACK_RED 都不在、is_in_battle 始终 False（transition/unknown）
        # → 不能立即 return True，也不立即 retry；bounded 用尽后 return False；期间不点 partition
        h, t = self._mk(in_battle=[False], fire_visible=[False], rr_person=[False], back_red=[False])
        self.assertIs(t.fire(1), False)
        t.click.assert_not_called()
        t.appear_then_click.assert_not_called()

    def test_partition_clicked_only_when_retryable_state(self):
        # FIRE 未就绪 + 明确 retryable（I_BACK_RED 在）→ 点 partition[order-1]，interval=2
        h, t = self._mk(in_battle=[False], fire_visible=[False], back_red=[True])
        t.fire(9)
        self.assertEqual(t.click.call_args_list[0].args[0].name, 'partition_9')
        self.assertEqual(t.click.call_args_list[0].kwargs, {'interval': 2})

    def test_source_uses_three_way_state_and_is_bounded(self):
        src = _src(RR.fire)
        self.assertIn('self.is_in_battle(', src)
        self.assertNotIn('if not self.appear(self.I_RR_PERSON):\n            return True', src)
        self.assertIn('Timer(RR_FIRE_TIMEOUT)', src)
        self.assertIn('range(1, RR_FIRE_MAX_TRIES + 1)', src)
        self.assertNotIn('while True', src)
        self.assertIn('random_delay(*REACTION_FIRE)', src)
        self.assertNotIn('confirm_delay', src)
        # 三态：battle / retryable / (timeout=transition-unknown)
        self.assertIn("state = self._wait_fire_entered_battle()", src)
        self.assertIn("if state == 'battle':", src)
        self.assertIn("if state == 'retryable':", src)
        # partition 点击（interval=2）恰 1 处，且落在 retryable 分支内（AST 校验）
        self.assertEqual(src.count('self.click(click, interval=2)'), 1)
        fn = ast.parse(src.lstrip()).body[0]
        retryable_if = None
        for node in ast.walk(fn):
            if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                    and getattr(node.test.left, 'id', None) == 'state'
                    and getattr(node.test.comparators[0], 'value', None) == 'retryable'):
                retryable_if = node
        self.assertIsNotNone(retryable_if)
        clicks_in_retryable = [
            n for n in ast.walk(retryable_if)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'click']
        self.assertEqual(len(clicks_in_retryable), 1)

    def test_helpers_are_read_only(self):
        wait_src = _src(RR._wait_fire_entered_battle)
        state_src = _src(RR._is_realm_raid_retryable_state)
        # _wait_fire_entered_battle 三态、不点击
        for tok in ("return 'battle'", "return 'retryable'", "return 'timeout'"):
            self.assertIn(tok, wait_src)
        self.assertNotIn('.click(', wait_src)
        self.assertNotIn('appear_then_click', wait_src)
        # _is_realm_raid_retryable_state 纯只读：无 screenshot / click / sleep
        for tok in ('screenshot', '.click(', 'sleep(', 'random_delay', 'Timer('):
            self.assertNotIn(tok, state_src, tok)
        self.assertIn('I_BACK_RED', state_src)

    def test_fire_can_return_false_reachably(self):
        tree = ast.parse(inspect.getsource(RR.fire).lstrip())
        fn = tree.body[0]
        # 尾部 return False 现在可达（for 循环正常结束 / break 后）
        self.assertIsInstance(fn.body[-1], ast.Return)
        self.assertIs(fn.body[-1].value.value, False)
        # 循环是 for（bounded），不是 while True
        loops = [n for n in fn.body if isinstance(n, (ast.While, ast.For))]
        self.assertTrue(any(isinstance(n, ast.For) for n in loops))
        self.assertFalse(any(isinstance(n, ast.While) for n in loops))


# --------------------------------------------------------------------------------------
# _fire_again() —— 退四内部「再次挑战」（2026-09-09：bounded + REACTION_FIRE + 三态）
# --------------------------------------------------------------------------------------

class FireAgainThreeStateTest(TestCase):
    def setUp(self):
        _RRFakeTimer.budget = 6
        for tgt in ('Timer', 'sleep', 'random_delay'):
            p = patch(f'tasks.RealmRaid.script_task.{tgt}',
                      _RRFakeTimer if tgt == 'Timer' else Mock(return_value=0.5))
            p.start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_RRFakeTimer, 'budget', 6))

    def _mk(self, *, in_battle=None, again=None, fresh_ensure=None,
            atc_show_again=None, atc_fresh_ensure=None):
        h = _Harness()
        t = h.task
        # 2026-09-08 Level C hotfix：_fire_again / _wait_again 的 positive success 判据从
        # is_in_battle(False)（含 I_FALSE / 奖励 marker）换成窄 _is_active_battle_entry()。
        # kwarg 名保留 in_battle，语义 = 「窄 active-battle-entry 判据」。
        t._is_active_battle_entry = Mock(side_effect=_tail_seq(in_battle or [False]))
        again_it = _tail_seq(again or [False])
        fe_it = _tail_seq(fresh_ensure or [False])       # appear(I_FRESH_ENSURE) —— _wait_again 用

        def _appear(tgt, **kw):
            if tgt.name == t.I_FIRE_AGAIN.name:
                return next(again_it)
            if tgt.name == t.I_FRESH_ENSURE.name:
                return next(fe_it)
            return False

        t.appear = Mock(side_effect=_appear)
        sa_atc = _tail_seq(atc_show_again or [False])
        fe_atc = _tail_seq(atc_fresh_ensure or [False])

        def _atc(tgt, **kw):
            h.events.append(('atc', tgt.name, kw))
            if tgt.name == t.I_SHOW_AGAIN.name:
                return next(sa_atc)
            if tgt.name == t.I_FRESH_ENSURE.name:
                return next(fe_atc)
            return True     # I_FIRE_AGAIN 点击：_fire_again 不检查返回值

        t.appear_then_click = Mock(side_effect=_atc)
        return h, t

    def _clicks(self, h):
        return [e for e in h.events if isinstance(e, tuple) and e[0] == 'atc']

    def test_positive_battle_returns_true_no_click(self):
        h, t = self._mk(in_battle=[True])
        self.assertIs(t._fire_again(), True)
        self.assertEqual(self._clicks(h), [])

    def test_reaction_then_click_i_fire_again_then_battle(self):
        h, t = self._mk(in_battle=[False, False, True], again=[True, True, True])
        self.assertIs(t._fire_again(), True)
        again_clicks = [e for e in self._clicks(h) if e[1] == t.I_FIRE_AGAIN.name]
        self.assertEqual(len(again_clicks), 1)
        self.assertEqual(again_clicks[0][2], {'interval': 0, 'threshold': 0.8})
        from tasks.RealmRaid import script_task as rr_mod
        self.assertGreaterEqual(rr_mod.random_delay.call_count, 1)
        for c in rr_mod.random_delay.call_args_list:
            self.assertEqual(c.args, (0.4, 0.8))

    def test_button_gone_during_reaction_no_stale_click(self):
        h, t = self._mk(in_battle=[False] * 40, again=[True] + [False] * 40)
        self.assertIs(t._fire_again(), False)
        again_clicks = [e for e in self._clicks(h) if e[1] == t.I_FIRE_AGAIN.name]
        self.assertEqual(again_clicks, [])

    def test_transition_unknown_then_battle_returns_true_no_click(self):
        # 按钮不在 + 不在失败页 → _wait_again polling → 出 battle
        h, t = self._mk(in_battle=[False, False, True], again=[False], fresh_ensure=[False])
        self.assertIs(t._fire_again(), True)
        again_clicks = [e for e in self._clicks(h) if e[1] == t.I_FIRE_AGAIN.name]
        self.assertEqual(again_clicks, [])

    def test_bounded_by_max_tries_returns_false(self):
        h, t = self._mk(in_battle=[False] * 40, again=[True] * 40)
        self.assertIs(t._fire_again(), False)
        again_clicks = [e for e in self._clicks(h) if e[1] == t.I_FIRE_AGAIN.name]
        from tasks.RealmRaid.script_task import RR_AGAIN_MAX_TRIES
        self.assertLessEqual(len(again_clicks), RR_AGAIN_MAX_TRIES)
        self.assertGreaterEqual(len(again_clicks), 1)

    def test_timeout_exits_false_immediately(self):
        _RRFakeTimer.budget = 0
        h, t = self._mk(in_battle=[False] * 10, again=[True] * 10)
        self.assertIs(t._fire_again(), False)
        self.assertEqual(self._clicks(h), [])

    def test_dialogs_dismissed_before_fire_again(self):
        # I_SHOW_AGAIN 先被点掉、然后 I_FRESH_ENSURE、最后才 I_FIRE_AGAIN
        h, t = self._mk(in_battle=[False] * 40,
                        atc_show_again=[True, False], atc_fresh_ensure=[False, True, False],
                        again=[False, False, True, True])
        t._fire_again()
        names = [e[1] for e in self._clicks(h)]
        self.assertIn(t.I_SHOW_AGAIN.name, names)
        self.assertIn(t.I_FRESH_ENSURE.name, names)
        if t.I_FIRE_AGAIN.name in names:
            self.assertLess(names.index(t.I_SHOW_AGAIN.name), names.index(t.I_FIRE_AGAIN.name))

    def test_wait_until_appear_is_bounded(self):
        src = _src(RR._fire_again)
        self.assertIn('wait_until_appear(self.I_FIRE_AGAIN, wait_time=RR_AGAIN_TIMEOUT)', src)
        self.assertIn('Timer(RR_AGAIN_TIMEOUT)', src)
        self.assertIn('range(1, RR_AGAIN_MAX_TRIES + 1)', src)
        self.assertNotIn('while True', src)

    def test_only_reaction_fire_no_stack(self):
        src = _src(RR._fire_again)
        self.assertEqual(src.count('random_delay('), 1)
        self.assertIn('random_delay(*REACTION_FIRE)', src)
        self.assertIn('I_FRESH_ENSURE, interval=2,\n                                      confirm_delay=RR_AGAIN_CONFIRM_DELAY)', src)
        self.assertNotIn('I_FIRE_AGAIN, interval=0, threshold=0.8, confirm_delay', src)

    def test_again_confirm_uses_its_own_delay_profile(self):
        from tasks.RealmRaid import script_task as rr_mod
        h, t = self._mk(in_battle=[False] * 40,
                        atc_fresh_ensure=[True, False], again=[False] * 40)
        t._fire_again()
        confirms = [e for e in self._clicks(h) if e[1] == t.I_FRESH_ENSURE.name]
        self.assertGreaterEqual(len(confirms), 1)
        self.assertEqual(confirms[0][2], {
            'interval': 2,
            'confirm_delay': rr_mod.RR_AGAIN_CONFIRM_DELAY,
        })
        self.assertEqual(rr_mod.RR_AGAIN_CONFIRM_DELAY, (0.3, 0.6))

    def test_wait_again_helper_is_clickless_three_state(self):
        src = _src(RR._wait_again_entered_battle)
        for st in ("'battle'", "'failure_page'", "'timeout'"):
            self.assertIn(st, src)
        for tok in ('.click(', 'appear_then_click', 'sleep(', 'random_delay'):
            self.assertNotIn(tok, src)

    def test_fire_again_can_return_false_reachably(self):
        tree = ast.parse(_src(RR._fire_again).lstrip())
        fn = tree.body[0]
        self.assertIsInstance(fn.body[-1], ast.Return)
        self.assertIs(fn.body[-1].value.value, False)


# --------------------------------------------------------------------------------------
# 2026-09-11 Level C 回归：`_fire_again()` 最后一次 attempt「reaction 后 I_FIRE_AGAIN 消失」
# 分支必须先有界确认 `_wait_again_entered_battle()`，不能裸 continue。
#
# 真机事实：RES_FIRE_AGAIN → RES_SHOW_AGAIN → RES_FRESH_ENSURE 后游戏已实际进入
# page_battle_prepare（右下角「准备」按钮正常出现），但日志停在
# `Fire again: attempt 4, reaction 0.77s` → `Fire again: button gone during reaction,
# re-evaluate` → `WARNING | Fire again: bounded retry / timeout without entering battle`，
# 任务异常遗留在 page_battle_prepare。
#
# 根因：此分支此前是裸 `continue`；非最后一次 attempt 靠下一轮循环顶部的
# `_is_active_battle_entry()` 隐式补一次确认掩盖了问题，但 attempt == RR_AGAIN_MAX_TRIES
# （最后一次）没有下一轮，`for` 循环直接耗尽退出，缺失了本该有的有界轮询窗口。
# --------------------------------------------------------------------------------------

class FireAgainLastAttemptReactionGoneTest(TestCase):
    def setUp(self):
        _RRFakeTimer.budget = 6
        for tgt in ('Timer', 'sleep', 'random_delay'):
            p = patch(f'tasks.RealmRaid.script_task.{tgt}',
                      _RRFakeTimer if tgt == 'Timer' else Mock(return_value=0.5))
            p.start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_RRFakeTimer, 'budget', 6))

    def _mk(self, *, wait_again_results):
        """真实 `_fire_again()`；`_wait_again_entered_battle()` 直接 mock 成给定结果序列，
        隔离外层 attempt / reaction 控制流与内部有界轮询实现，只测「gone 分支是否调用了它、
        是否认可它的 'battle' 返回」。`I_FIRE_AGAIN` 按 [点击前可见, reaction 后消失] 逐
        attempt 循环，复现「每次都刚好在 reaction 期间消失」的真机场景。
        """
        h = _Harness()
        t = h.task
        t._is_active_battle_entry = Mock(return_value=False)
        t._wait_again_entered_battle = Mock(side_effect=wait_again_results)
        again_visible = itertools.cycle([True, False])   # 点击前(C)可见 → reaction 后(F)消失

        def _appear(tgt, **kw):
            if tgt.name == t.I_FIRE_AGAIN.name:
                return next(again_visible)
            return False
        t.appear = Mock(side_effect=_appear)

        def _atc(tgt, **kw):
            if tgt.name in (t.I_SHOW_AGAIN.name, t.I_FRESH_ENSURE.name):
                return False
            return True     # I_FIRE_AGAIN 点击：_fire_again 不检查返回值
        t.appear_then_click = Mock(side_effect=_atc)
        return h, t

    def test_last_attempt_button_gone_during_reaction_polls_before_giving_up(self):
        """CASE 1（核心回归）：attempt 1~3 的 gone 分支 wait 都判 'timeout'（继续下一
        attempt），attempt 4（`RR_AGAIN_MAX_TRIES`，最后一次）gone 分支 wait 判 'battle'。
        期望：`_fire_again()` == True，且不落到 bounded timeout warning（若裸 continue
        未修复，attempt 4 的 'battle' 结果根本不会被读取，函数会耗尽 attempt 直接 False）。
        """
        from tasks.RealmRaid.script_task import RR_AGAIN_MAX_TRIES
        self.assertEqual(RR_AGAIN_MAX_TRIES, 4)   # 真机日志 "attempt 4" 对应最后一次
        h, t = self._mk(wait_again_results=['timeout', 'timeout', 'timeout', 'battle'])
        self.assertIs(t._fire_again(), True)
        self.assertEqual(t._wait_again_entered_battle.call_count, RR_AGAIN_MAX_TRIES)

    def test_last_attempt_button_gone_without_battle_confirmation_stays_bounded_false(self):
        """CASE 2：`_wait_again_entered_battle()` 一直不给 'battle'（'timeout' /
        'failure_page' 都算未确认）→ 仍遵守 bounded retry，最终 False，且调用次数恰好
        = `RR_AGAIN_MAX_TRIES`，不多不少、不形成无界循环。"""
        from tasks.RealmRaid.script_task import RR_AGAIN_MAX_TRIES
        h, t = self._mk(wait_again_results=['timeout', 'failure_page', 'timeout', 'timeout'])
        self.assertIs(t._fire_again(), False)
        self.assertEqual(t._wait_again_entered_battle.call_count, RR_AGAIN_MAX_TRIES)

    def test_button_gone_during_reaction_branch_calls_wait_helper_source_shape(self):
        """源码形态锁定：「reaction 后按钮消失」分支必须调用 `_wait_again_entered_battle()`
        并认可它的 'battle' 返回，不能再退化回裸 `continue`（防止本修复被静默回退）。"""
        src = _src(RR._fire_again)
        marker = "'Fire again: button gone during reaction, re-evaluate'"
        self.assertIn(marker, src)
        gone_branch = src.split(marker)[-1]
        gone_branch = gone_branch.split('self.appear_then_click(self.I_FIRE_AGAIN, interval=0')[0]
        self.assertIn('self._wait_again_entered_battle()', gone_branch)
        self.assertIn("if state == 'battle':", gone_branch)
        self.assertIn('return True', gone_branch)
        self.assertIn('continue', gone_branch)


# --------------------------------------------------------------------------------------
# 2026-09-08 Level C hotfix：`_fire_again()` 的 positive success 判据
# —— 失败结果页（is_in_battle() 因 I_FALSE 恒 True）不得被当成「已进入下一场战斗」
# --------------------------------------------------------------------------------------

class ActiveBattleEntryContractTest(TestCase):
    RESULT_REWARD_MARKERS = ('I_FALSE', 'I_WIN', 'I_DE_WIN', 'I_REWARD', 'I_REWARD_GOLD', 'I_FRIENDS')

    # ---- 源码形态（去 docstring 只扫代码体）----
    def test_helper_uses_narrow_prepare_or_real_battle_only(self):
        src = _src(RR._is_active_battle_entry)
        body = src.split('"""')[-1]
        self.assertIn('self.is_in_prepare(False)', body)
        self.assertIn('self.is_in_real_battle(False)', body)
        # 代码体不复用宽生命周期 detector、不直接引 result / reward marker
        self.assertNotIn('is_in_battle(', body)
        for m in self.RESULT_REWARD_MARKERS:
            self.assertNotIn(m, body, m)
        # 纯只读
        for tok in ('self.screenshot(', '.click(', 'appear_then_click', 'sleep(',
                    'random_delay', 'Timer('):
            self.assertNotIn(tok, body, tok)

    def test_fire_again_and_wait_helper_no_longer_call_is_in_battle(self):
        for func in (RR._fire_again, RR._wait_again_entered_battle):
            body = _src(func).split('"""')[-1]
            self.assertNotIn('is_in_battle(', body, func.__name__)
            self.assertIn('self._is_active_battle_entry()', body, func.__name__)

    def test_general_battle_is_in_battle_still_wide_and_untouched(self):
        # 不改 GeneralBattle.is_in_battle()：它仍是「准备+战斗+结果+奖励」宽 detector
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        wide = _src(GeneralBattle.is_in_battle)
        for m in ('I_BATTLE_INFO', 'I_PREPARE_HIGHLIGHT', 'I_WIN', 'I_DE_WIN', 'I_FALSE',
                  'I_REWARD', 'I_REWARD_GOLD'):
            self.assertIn(m, wide, m)
        # 窄 detector 复用的两个 GeneralBattle helper 确实是窄的
        prepare = _src(GeneralBattle.is_in_prepare)
        real = _src(GeneralBattle.is_in_real_battle)
        for m in ('I_WIN', 'I_DE_WIN', 'I_FALSE', 'I_REWARD', 'I_REWARD_GOLD'):
            self.assertNotIn(m, prepare, m)
            self.assertNotIn(m, real, m)
        self.assertIn('I_BATTLE_INFO', real)

    # ---- 行为：窄 detector 语义 ----
    def _mk_helper(self, *, prepare=False, real=False):
        t = RR.__new__(RR)
        t.is_in_prepare = Mock(return_value=prepare)
        t.is_in_real_battle = Mock(return_value=real)
        # 就算宽 detector 会因 I_FALSE 返回 True，也不该被窄判据采用
        t.is_in_battle = Mock(return_value=True)
        return t

    def test_result_reward_only_frame_is_not_active_battle(self):
        # 失败横幅 / 胜负横幅 / 奖励页：is_in_prepare = is_in_real_battle = False
        t = self._mk_helper(prepare=False, real=False)
        self.assertIs(t._is_active_battle_entry(), False)
        t.is_in_battle.assert_not_called()   # 窄判据根本不问宽 detector

    def test_prepare_frame_is_active_battle(self):
        self.assertIs(self._mk_helper(prepare=True, real=False)._is_active_battle_entry(), True)

    def test_real_battle_frame_is_active_battle(self):
        self.assertIs(self._mk_helper(prepare=False, real=True)._is_active_battle_entry(), True)

    # ---- 行为：_fire_again 在失败结果页 ----
    def _mk_fire_again(self, *, active_seq, again_visible=True, show_again=None, fresh_ensure=None):
        """真实 _fire_again，只 mock 视觉原语。active_seq 驱动 _is_active_battle_entry。"""
        for tgt in ('Timer', 'sleep', 'random_delay'):
            p = patch(f'tasks.RealmRaid.script_task.{tgt}',
                      _RRFakeTimer if tgt == 'Timer' else Mock(return_value=0.5))
            p.start()
        self.addCleanup(patch.stopall)
        _RRFakeTimer.budget = 20
        self.addCleanup(lambda: setattr(_RRFakeTimer, 'budget', 6))

        t = RR.__new__(RR)
        events = []
        t.device = SimpleNamespace(image='F', click_record_clear=Mock())
        t.wait_until_appear = Mock()
        t.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        t._is_active_battle_entry = Mock(side_effect=_tail_seq(active_seq))
        again_it = _tail_seq([again_visible] if isinstance(again_visible, bool) else again_visible)
        fe_it = _tail_seq(fresh_ensure or [False])

        def _appear(target, **kw):
            if target.name == t.I_FIRE_AGAIN.name:
                return next(again_it)
            if target.name == t.I_FRESH_ENSURE.name:
                return next(fe_it)
            return False
        t.appear = Mock(side_effect=_appear)
        sa_it = _tail_seq(show_again or [False])

        def _atc(target, **kw):
            events.append(('atc', target.name, kw))
            if target.name == t.I_SHOW_AGAIN.name:
                return next(sa_it)
            if target.name == t.I_FRESH_ENSURE.name:
                return False
            return True
        t.appear_then_click = Mock(side_effect=_atc)
        return t, events

    def _again_clicks(self, events):
        return [e for e in events if isinstance(e, tuple) and e[0] == 'atc'
                and e[1] == RR.I_FIRE_AGAIN.name]

    def test_i_false_frame_does_not_short_circuit_to_success(self):
        # 关键回归：失败结果页（宽 is_in_battle 会 True）+ I_FIRE_AGAIN 可见
        # → 不得立即 return True；必须走 reaction + 真实 I_FIRE_AGAIN click。
        from tasks.RealmRaid import script_task as rr_mod
        # active 前几帧 False（仍在失败页），点击后才 True
        t, events = self._mk_fire_again(active_seq=[False, False, False, True])
        self.assertIs(t._fire_again(), True)
        again_clicks = self._again_clicks(events)
        self.assertGreaterEqual(len(again_clicks), 1, '必须真实点过「再次挑战」')
        self.assertEqual(again_clicks[0][2], {'interval': 0, 'threshold': 0.8})
        self.assertGreaterEqual(rr_mod.random_delay.call_count, 1)   # reaction 发生过
        for c in rr_mod.random_delay.call_args_list:
            self.assertEqual(c.args, (0.4, 0.8))
        # reaction 日志顺序：screenshot 在 click 之前有 ≥2 次（top + reaction 后）
        self.assertGreaterEqual(events.count('screenshot'), 2)

    def test_active_battle_first_frame_returns_true_no_click(self):
        # 真的已经在准备 / 战斗页 → 直接成功、不点
        t, events = self._mk_fire_again(active_seq=[True])
        self.assertIs(t._fire_again(), True)
        self.assertEqual(self._again_clicks(events), [])

    def test_button_gone_then_active_battle_no_stale_click(self):
        # click 后按钮消失 + active 暂未出现（unknown）→ 之后 active 出现 → True
        t, events = self._mk_fire_again(
            active_seq=[False, False, False, False, True],
            again_visible=[True, True, False, False, False])
        self.assertIs(t._fire_again(), True)
        # unknown 阶段没有对旧坐标乱点：I_FIRE_AGAIN click 次数 ≤ 1
        self.assertLessEqual(len(self._again_clicks(events)), 1)

    def test_failure_page_persists_bounded_false(self):
        # I_FIRE_AGAIN 一直在、active 永不出现 → bounded → False
        from tasks.RealmRaid.script_task import RR_AGAIN_MAX_TRIES
        t, events = self._mk_fire_again(active_seq=[False] * 60, again_visible=[True] * 60)
        self.assertIs(t._fire_again(), False)
        clicks = self._again_clicks(events)
        self.assertGreaterEqual(len(clicks), 1)
        self.assertLessEqual(len(clicks), RR_AGAIN_MAX_TRIES)


# --------------------------------------------------------------------------------------
# find_one() / _grid_targets() —— 固定 1→9、取消勋章排序、副本涂黑、只剩最后目标
# --------------------------------------------------------------------------------------

class FindOneFixedOrderTest(TestCase):
    def _mk(self):
        h = _Harness()
        t = h.task
        t.device.image = np.full((720, 1280, 3), 255, dtype=np.uint8)
        # 3 个 100x100 格子，roi_front 用于中心点映射，roi_back 用于涂黑
        t.__dict__['partition'] = [
            _fake_click('p1', (0, 0, 100, 100)),
            _fake_click('p2', (200, 0, 100, 100)),
            _fake_click('p3', (400, 0, 100, 100)),
        ]
        t.__dict__['false_roi'] = [[0, 0, 10, 10], [200, 0, 10, 10], [400, 0, 10, 10]]
        t.__dict__['false_image'] = SimpleNamespace(roi_back=None, name='false')
        return h, t

    @staticmethod
    def _medal(name='m'):
        return RuleImage(roi_front=(0, 0, 1, 1), roi_back=(0, 0, 1, 1),
                         threshold=0.8, method='Template matching', file=name)

    def _grid(self, matches):
        # matches: list of (medal, (x,y,w,h)) —— 已按 y 排序传入
        return SimpleNamespace(find_everyone=Mock(return_value=[(m, 0.9, box) for m, box in matches]))

    def test_fixed_1_to_9_returns_lowest_index(self):
        h, t = self._mk()
        t.appear = Mock(return_value=False)                       # 无失败格
        m1, m3 = self._medal('m1'), self._medal('m3')
        # 匹配在 p3 (x=440) 和 p1 (x=40) —— 返回最小 index=1
        t.__dict__['order_medal'] = self._grid([(m3, (440, 40, 20, 20)), (m1, (40, 40, 20, 20))])
        target, order = t.find_one(screenshot=False)
        self.assertEqual(order, 1)
        self.assertIs(target, m1)

    def test_grid_1_broken_then_returns_2(self):
        h, t = self._mk()
        # false_image 在第 1 个 roi 命中 → order 1 broken
        t.appear = Mock(side_effect=[True, False, False])
        m2 = self._medal('m2')
        t.__dict__['order_medal'] = self._grid([(m2, (240, 40, 20, 20))])
        target, order = t.find_one(screenshot=False)
        self.assertEqual(order, 2)
        self.assertIs(target, m2)

    def test_returns_none_none_when_no_attackable(self):
        h, t = self._mk()
        t.appear = Mock(return_value=False)
        t.__dict__['order_medal'] = SimpleNamespace(find_everyone=Mock(return_value=None))
        self.assertEqual(t.find_one(screenshot=False), (None, None))

    def test_only_last_target_when_single_attackable(self):
        h, t = self._mk()
        t.appear = Mock(return_value=False)
        m = self._medal()
        t.__dict__['order_medal'] = self._grid([(m, (440, 40, 20, 20))])   # 只有 p3
        targets = t._grid_targets()
        self.assertEqual(list(targets), [3])                                # last_target = 3（不是 9）
        self.assertEqual(len(targets), 1)

    def test_medal_type_does_not_affect_selection_order(self):
        h, t = self._mk()
        t.appear = Mock(return_value=False)
        strong, weak = self._medal('strong'), self._medal('weak')
        # 强勋章在 p3、弱勋章在 p1 —— 位置决定，返回 p1（弱）
        t.__dict__['order_medal'] = self._grid([(strong, (440, 40, 20, 20)), (weak, (40, 40, 20, 20))])
        target, order = t.find_one(screenshot=False)
        self.assertEqual(order, 1)
        self.assertIs(target, weak)

    def test_shared_frame_not_mutated_broken_blacked_on_copy(self):
        h, t = self._mk()
        t.appear = Mock(side_effect=[True, False, False])          # order 1 broken
        t.__dict__['order_medal'] = SimpleNamespace(find_everyone=Mock(return_value=None))
        before = t.device.image
        t._grid_targets()
        self.assertIs(t.device.image, before)
        self.assertTrue((t.device.image == 255).all())            # 共享帧未被涂黑
        work = t.order_medal.find_everyone.call_args.args[0]
        self.assertIsNot(work, t.device.image)                    # 传入的是副本
        self.assertTrue((work[0:100, 0:100] == 0).all())          # 副本上 order 1 已涂黑

    def test_find_everyone_called_without_frame_id(self):
        h, t = self._mk()
        t.appear = Mock(return_value=False)                       # 无 broken → 不复制
        grid = SimpleNamespace(find_everyone=Mock(return_value=None))
        t.__dict__['order_medal'] = grid
        t._grid_targets()
        self.assertEqual(grid.find_everyone.call_args.kwargs, {})
        self.assertEqual(len(grid.find_everyone.call_args.args), 1)


# --------------------------------------------------------------------------------------
# check_ticket / check_refresh
# --------------------------------------------------------------------------------------

class TicketAndRefreshTest(TestCase):
    def _mk(self, ocr, *, number_attack=30):
        h = _Harness()
        t = h.task
        t.O_NUMBER = SimpleNamespace(ocr=Mock(side_effect=ocr if isinstance(ocr, list) else [ocr] * 5),
                                     name='number')
        t.reward_detect_click = Mock(return_value=False)
        t.config = SimpleNamespace(realm_raid=SimpleNamespace(
            raid_config=SimpleNamespace(number_attack=number_attack)))
        t.init_tickets = -1
        return h, t

    def test_invalid_base_is_clamped_to_zero(self):
        h, t = self._mk((5, 0, 5))
        self.assertTrue(t.check_ticket(-1))
        self.assertTrue(t.check_ticket(31))

    def test_waits_for_back_red_then_screenshots_then_ocr(self):
        h, t = self._mk((5, 0, 5))
        t.check_ticket(0)
        self.assertEqual(h.events[0], ('wait_until_appear', t.I_BACK_RED.name, {}))
        self.assertEqual(h.events[1], 'screenshot')

    def test_total_zero_triggers_reward_detect_then_reocr(self):
        h, t = self._mk([(0, 0, 0), (5, 0, 5)])
        self.assertTrue(t.check_ticket(0))
        t.reward_detect_click.assert_called_once_with(True)
        self.assertEqual(t.O_NUMBER.ocr.call_count, 2)

    def test_no_ticket_returns_false(self):
        h, t = self._mk((0, 5, 5))
        self.assertFalse(t.check_ticket(0))

    def test_not_enough_ticket_versus_base_returns_false(self):
        h, t = self._mk((2, 3, 5))
        self.assertFalse(t.check_ticket(3))

    def test_init_tickets_latches_once_and_caps_attack_count(self):
        h, t = self._mk([(9, 0, 9), (5, 0, 9)], number_attack=3)
        self.assertTrue(t.check_ticket(0))
        self.assertEqual(t.init_tickets, 9)
        # 已打 9-5=4 >= number_attack 3 → 停止
        self.assertFalse(t.check_ticket(0))
        self.assertEqual(t.init_tickets, 9)

    def test_check_refresh_returns_false_immediately_when_button_absent(self):
        h = _Harness()
        t = h.task
        t.appear = Mock(return_value=False)
        t.appear_then_click = Mock(return_value=False)
        self.assertFalse(t.check_refresh(screenshot=True))
        self.assertEqual(t.screenshot.call_count, 1)
        t.appear_then_click.assert_not_called()

    def test_check_refresh_tail_return_false_is_unreachable(self):
        tree = ast.parse(inspect.getsource(RR.check_refresh).lstrip())
        fn = tree.body[0]
        self.assertIsInstance(fn.body[-1], ast.Return)
        self.assertIs(fn.body[-1].value.value, False)


# --------------------------------------------------------------------------------------
# GeneralBattle 交接
# --------------------------------------------------------------------------------------

class GeneralBattleHandoffTest(TestCase):
    def test_exit_matcher_is_back_red(self):
        t = RR.__new__(RR)
        self.assertIs(t._exit_matcher(), t.I_BACK_RED)

    def test_quick_exit_result_returns_win_or_lose_without_settlement_click(self):
        t = RR.__new__(RR)
        t._settlement_click = Mock()
        ctx = SimpleNamespace(reward_no_battle_ts='X', is_win=None)
        cfg = SimpleNamespace(quick_exit=True)

        t.appear = Mock(return_value=False)               # 没有 I_FALSE → 胜
        self.assertIs(t._handle_result(ctx, cfg), BattleAction.EXIT_WIN)
        self.assertIsNone(ctx.reward_no_battle_ts)
        self.assertIs(ctx.is_win, True)

        t.appear = Mock(return_value=True)                # 有 I_FALSE → 负
        self.assertIs(t._handle_result(ctx, cfg), BattleAction.EXIT_LOSE)
        self.assertIs(ctx.is_win, False)
        t._settlement_click.assert_not_called()           # quick_exit 分支不点结算

    def test_quick_exit_uses_i_false_without_explicit_threshold(self):
        # 现状：RealmRaid 覆写用 `self.appear(self.I_FALSE)`（走批量缓存），
        # 基类用 `self.appear(self.I_FALSE, threshold=0.8)`（强制重新匹配）。
        self.assertIn('self.appear(self.I_FALSE)', _src(RR._handle_result))
        self.assertIn('threshold=0.8', _src(GeneralBattle._handle_result))

    def test_non_quick_exit_delegates_to_super(self):
        t = RR.__new__(RR)
        ctx = SimpleNamespace(reward_no_battle_ts='X', is_win=None)
        cfg = SimpleNamespace(quick_exit=False)
        with patch.object(GeneralBattle, '_handle_result',
                          return_value=BattleAction.CONTINUE) as sup:
            self.assertIs(t._handle_result(ctx, cfg), BattleAction.CONTINUE)
        sup.assert_called_once_with(ctx, cfg)

    def test_realm_raid_overrides_battle_timing_constants(self):
        self.assertEqual(RR.PREPARE_CLICK_DELAY_RANGE, (2.5, 3.5))
        self.assertEqual(GeneralBattle.PREPARE_CLICK_DELAY_RANGE, (3.0, 3.0))
        # RealmRaid 间接消费 T7 Settlement opt-in（C_RANDOM_RD + HABIT），但用自己的间隔
        self.assertEqual(RR.SETTLEMENT_CLICK_INTERVAL_RANGE, (0.65, 0.95))
        self.assertEqual(GeneralBattle.SETTLEMENT_CLICK_INTERVAL_RANGE, (0.7, 1.0))

    def test_run_hands_battle_to_run_general_battle_only(self):
        src = _src(RR.run)
        self.assertIn('self.run_general_battle(', src)
        # 2026-09-09：退四改成「只剩最后 1 个可攻打目标」+ 循环，run() 里
        # run_general_battle 3 处（退四首战 quick + 退四循环内 1 + 普通目标 1）、
        # _fire_again 循环 1 处、退四次数常量 RR_EXIT_FOUR_SURRENDERS = 4（沿用旧硬编码 4 次）
        self.assertEqual(src.count('self.run_general_battle('), 3)
        self.assertEqual(src.count('self._fire_again()'), 1)
        self.assertIn('for i in range(RR_EXIT_FOUR_SURRENDERS)', src)
        from tasks.RealmRaid.script_task import RR_EXIT_FOUR_SURRENDERS
        self.assertEqual(RR_EXIT_FOUR_SURRENDERS, 4)
        self.assertIn('self.build_quick_exit_config(', src)


# --------------------------------------------------------------------------------------
# 循环 / 等待边界（源码级）
# --------------------------------------------------------------------------------------

class LoopAndWaitBoundsTest(TestCase):
    # `medal_fire` 曾在此列表——已于 2026-09-02 作为零调用方死代码删除（见 §16 cleanup 批次 1）
    # `fire` 2026-09-08 R-R1、`_fire_again` 2026-09-09 退四改造，均收口为 bounded，移出本列表
    UNBOUNDED = ('ensure_lock', 'check_refresh', 'reward_detect_click')

    def test_task_local_loops_have_no_timer_or_iteration_cap(self):
        for name in self.UNBOUNDED:
            src = _src(getattr(RR, name))
            self.assertTrue('while' in src, name)
            self.assertNotIn('Timer(', src, name)
            self.assertNotIn('range(', src, name)

    def test_fire_is_bounded_after_r_r1(self):
        src = _src(RR.fire)
        self.assertIn('Timer(RR_FIRE_TIMEOUT)', src)
        self.assertIn('range(1, RR_FIRE_MAX_TRIES + 1)', src)
        self.assertNotIn('while True', src)

    def test_fire_again_is_bounded_after_exit_four_refactor(self):
        src = _src(RR._fire_again)
        self.assertIn('Timer(RR_AGAIN_TIMEOUT)', src)
        self.assertIn('range(1, RR_AGAIN_MAX_TRIES + 1)', src)
        self.assertNotIn('while True', src)

    def test_wait_until_appear_calls_bounded_ones_are_fire_fire_again_and_cycle_break(self):
        # 带 wait_time 的 3 处：`fire()` 的 I_RR_PERSON、`_fire_again()` 的 I_FIRE_AGAIN、
        # `_realm_raid_cycle_safe_break()` 的 I_BACK_RED（refresh / 结算动画收尾确认，2026-09-08）。
        # 其余（check_ticket / reward_detect_click）仍不传。
        src = inspect.getsource(inspect.getmodule(RR))
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'wait_until_appear']
        self.assertGreaterEqual(len(calls), 5)
        with_wait_time = [ast.unparse(c) for c in calls
                          if any(kw.arg == 'wait_time' for kw in c.keywords)]
        without = [c for c in calls if not any(kw.arg == 'wait_time' for kw in c.keywords)]
        self.assertEqual(len(with_wait_time), 3, with_wait_time)
        self.assertTrue(any('I_RR_PERSON' in s for s in with_wait_time))
        self.assertTrue(any('I_FIRE_AGAIN' in s for s in with_wait_time))
        self.assertTrue(any('I_BACK_RED' in s and 'RR_CYCLE_STABLE_TIMEOUT' in s for s in with_wait_time))
        self.assertGreaterEqual(len(without), 2)

    def test_run_main_loop_is_state_bounded_with_break_paths(self):
        src = _src(RR.run)
        self.assertIn('while 1:', src)
        self.assertNotIn('Timer(', src)
        self.assertGreaterEqual(src.count('break'), 5)
        self.assertIn('raise TaskEnd', src)

    def test_run_ends_with_exploration_then_set_next_run_then_taskend(self):
        src = _src(RR.run)
        # 主循环退出后固定收尾：回探索页 → set_next_run(success=...) → raise TaskEnd
        tail = src[src.rindex('self.goto_page(page_exploration)'):]
        self.assertLess(tail.index('self.goto_page(page_exploration)'),
                        tail.index("self.set_next_run(task='RealmRaid'"))
        self.assertLess(tail.index("self.set_next_run(task='RealmRaid'"),
                        tail.index('raise TaskEnd'))
        # 另有一条早退路径：票数不足时直接 goto_page(page_exploration) + success=False
        self.assertEqual(src.count('self.goto_page(page_exploration)'), 2)


# --------------------------------------------------------------------------------------
# 死代码 / 结构事实
# --------------------------------------------------------------------------------------

class DeadCodeAndStructureTest(TestCase):
    def test_removed_dead_code_stays_removed(self):
        # 2026-09-02 cleanup 批次 1：`medal_fire()` / `is_ticket()` / `medal_grid` 类属性
        # 是零调用方的 legacy 死路径（`medal_grid=None` 使 `medal_fire` 一旦被调用即
        # `AttributeError`），已删除。这里守卫它们不被重新引入。
        self.assertFalse(hasattr(RR, 'medal_fire'))
        self.assertFalse(hasattr(RR, 'is_ticket'))
        self.assertFalse(hasattr(RR, 'medal_grid'))
        src = inspect.getsource(inspect.getmodule(RR))
        for token in ('def medal_fire', 'def is_ticket', 'medal_grid'):
            self.assertNotIn(token, src, token)

    def test_no_dead_imports_from_realm_raid_config_or_time(self):
        # 同批次：`RealmRaid`（config 类）/ `AttackNumber` 从 import 删除（模块内零引用，
        # `config_model.py` 另有独立 import）；`import time` 随 `medal_fire` 删除后变死也一并删。
        src = inspect.getsource(inspect.getmodule(RR))
        self.assertNotIn('AttackNumber', src)
        self.assertIn('from tasks.RealmRaid.config import WhenAttackFail', src)
        self.assertNotIn('import time', src)
        # 仍在用的没被误删
        self.assertIn('WhenAttackFail.', src)          # 分支判断
        self.assertIn('import re', src)                # order_medal 用 re.split
        self.assertIn('from module.atom.image_grid import ImageGrid', src)  # order_medal 用 ImageGrid

    def test_all_input_goes_through_control_no_direct_backend(self):
        src = inspect.getsource(inspect.getmodule(RR))
        for token in ('swipe_adb', 'click_adb', 'adb_shell', 'swipe_minitouch',
                      'click_minitouch', 'device.swipe('):
            self.assertNotIn(token, src, token)

    def test_no_frame_wait_consumer_in_realm_raid(self):
        src = inspect.getsource(inspect.getmodule(RR))
        for token in ('wait_for_changed_and_stable', 'frame_wait', 'FrameStateDetector',
                      'changed_threshold', 'stable_threshold', 'stable_frames'):
            self.assertNotIn(token, src, token)

    def test_false_image_reuses_ryoutoppa_loser_sign(self):
        t = RR.__new__(RR)
        self.assertIn('RyouToppa', t.false_image.file)
        self.assertEqual(len(t.false_roi), 9)


# --------------------------------------------------------------------------------------
# 2026-09-09 主流程改造：固定 1→9 / 取消勋章排序 / 目标 pacing / 退四入口 / 最终失败刷新 / Fatigue
# --------------------------------------------------------------------------------------

class MainFlowRefactorTest(TestCase):
    def test_target_selection_no_longer_uses_medal_sorting(self):
        # run() / find_one / _grid_targets 不再靠 order_medal.find_anyone（优先级排序），
        # 改用 find_everyone（扫全格）+ min(order)（位置）
        run_src = _src(RR.run)
        fo_src = _src(RR.find_one)
        gt_src = _src(RR._grid_targets)
        self.assertNotIn('find_anyone', run_src)
        self.assertNotIn('find_anyone', fo_src)
        self.assertIn('find_everyone', gt_src)
        self.assertIn('min(targets)', fo_src + run_src)
        # order_medal cached_property 仍在（作「这一格有没有对手」的过滤器），未被误删
        self.assertTrue(hasattr(RR, 'order_medal'))

    def test_exit_four_entry_is_last_attackable_target_not_index_1(self):
        run_src = _src(RR.run)
        # 退四入口 = only_last（len(targets) == 1）+ exit_four，不再是 index == 1
        self.assertIn('only_last = len(targets) == 1', run_src)
        self.assertIn('if only_last and con.raid_config.exit_four:', run_src)
        self.assertNotIn('if index == 1:', run_src)
        self.assertNotIn("logger.info('Now is the first one')", run_src)

    def test_exit_four_unlocks_before_last_target_and_restores(self):
        run_src = _src(RR.run)
        i_entry = run_src.index('if only_last and con.raid_config.exit_four:')
        i_else = run_src.index('# ---- 普通目标 ----')
        block = run_src[i_entry:i_else]
        self.assertIn('self.ensure_lock(False)', block)           # 退四前解锁
        self.assertIn('self.ensure_lock(lock_default)', block)    # 退四后恢复
        # 普通目标分支不做这个 unlock 特殊流程
        normal = run_src[i_else:]
        self.assertNotIn('self.ensure_lock(False)', normal)

    def test_exit_four_surrender_count_constant_and_loop(self):
        from tasks.RealmRaid.script_task import RR_EXIT_FOUR_SURRENDERS
        self.assertEqual(RR_EXIT_FOUR_SURRENDERS, 4)              # 沿用旧硬编码 4 次
        run_src = _src(RR.run)
        self.assertIn('for i in range(RR_EXIT_FOUR_SURRENDERS):', run_src)
        self.assertIn('self._fire_again()', run_src)

    def test_exit_four_final_failure_refreshes_no_more_fire_again(self):
        run_src = _src(RR.run)
        i_entry = run_src.index('if only_last and con.raid_config.exit_four:')
        i_else = run_src.index('# ---- 普通目标 ----')
        block = run_src[i_entry:i_else]
        # 退四中断 / 最终失败 → check_refresh（不再 _fire_again）
        self.assertIn('if aborted or not last_battle:', block)
        i_fail = block.index('if aborted or not last_battle:')
        self.assertIn('self.check_refresh()', block[i_fail:])
        self.assertNotIn('_fire_again', block[i_fail:])          # 失败分支里不再 fire again

    def test_fire_again_only_called_inside_exit_four_block(self):
        run_src = _src(RR.run)
        i_entry = run_src.index('if only_last and con.raid_config.exit_four:')
        i_else = run_src.index('# ---- 普通目标 ----')
        # run() 里 _fire_again 只出现在退四块内
        self.assertEqual(run_src[:i_entry].count('_fire_again'), 0)
        self.assertEqual(run_src[i_else:].count('_fire_again'), 0)
        self.assertGreaterEqual(run_src[i_entry:i_else].count('self._fire_again()'), 1)

    def test_target_pacing_constant_and_placement(self):
        from tasks.RealmRaid.script_task import RR_TARGET_PACING
        self.assertEqual(RR_TARGET_PACING, (1.0, 2.5))
        et_full = _src(RR._enter_target)
        et = et_full.split('"""')[-1]                            # 去 docstring，只扫代码体
        # pacing：识别 target 仍可打 → random_delay(*RR_TARGET_PACING) → sleep → fresh screenshot
        # → 再确认（可操作页 + 仍可打）→ 点 partition
        self.assertIn('random_delay(*RR_TARGET_PACING)', et)
        self.assertEqual(et.count('random_delay('), 1)            # 恰一次，不叠加
        i_delay = et.index('random_delay(*RR_TARGET_PACING)')
        tail = et[i_delay:]
        self.assertIn('sleep(pacing)', tail)
        i_sleep = tail.index('sleep(pacing)')
        after = tail[i_sleep:]
        self.assertIn('self.screenshot()', after)
        self.assertIn('_is_realm_raid_retryable_state()', after)
        self.assertIn('_target_still_attackable(order)', after)
        self.assertIn('self.click(self.partition[order - 1]', after)
        self.assertNotIn('confirm_delay', et)
        # run() 每个目标（退四 / 普通）点开详情前都过 _enter_target（退四带
        # require_only_remaining=True）
        run_src = _src(RR.run)
        self.assertEqual(run_src.count('self._enter_target(index'), 2)
        self.assertIn('self._enter_target(index, require_only_remaining=True)', run_src)

    def test_enter_target_no_stale_click_when_target_becomes_unattackable(self):
        _RRFakeTimer.budget = 6
        for tgt in ('sleep', 'random_delay'):
            p = patch(f'tasks.RealmRaid.script_task.{tgt}', Mock(return_value=1.5))
            p.start()
            self.addCleanup(p.stop)
        h = _Harness()
        t = h.task
        t.__dict__['partition'] = [_fake_click(f'partition_{i}', (i * 10, 0, 9, 9)) for i in range(1, 10)]
        t.click = Mock()
        # 第 1 次 _target_still_attackable True，pacing 后第 2 次 False → 不点 partition
        t._target_still_attackable = Mock(side_effect=[True, False])
        t._is_realm_raid_retryable_state = Mock(return_value=True)
        self.assertIs(t._enter_target(3), False)
        t.click.assert_not_called()

    def test_target_pacing_is_not_ryoutoppa_1_to_3(self):
        # RealmRaid 用自己的 (1.0, 2.5)；不得出现 RyouToppa 的 (1.0, 3.0)
        src = inspect.getsource(inspect.getmodule(RR))
        self.assertNotIn('random_delay(1.0, 3.0)', src)
        self.assertIn('RR_TARGET_PACING = (1.0, 2.5)', src)

    def test_fatigue_wired_at_cycle_safe_point_only(self):
        run_src = _src(RR.run)
        self.assertIn("self.begin_fatigue_task('RealmRaid')", run_src)
        # begin_fatigue_task 在主循环之前（run() 里有 2 个 while 1:——呱太弹窗循环 + 主循环）
        self.assertLess(run_src.index('begin_fatigue_task'), run_src.rindex('while 1:'))
        self.assertLess(run_src.index('begin_fatigue_task'), run_src.index('targets = self._grid_targets()'))
        sb = _src(RR._realm_raid_cycle_safe_break)
        self.assertIn('try_fatigue_break(safe=True, repeat_completed=True, deadline=None)', sb)
        # safe break helper 里先 screenshot + 确认可操作页
        self.assertIn('self.screenshot()', sb)
        self.assertIn('_is_realm_raid_retryable_state()', sb)
        # try_fatigue_break 只在 _realm_raid_cycle_safe_break 里；不在 fire / _fire_again / _enter_target 里
        for m in ('fire', '_fire_again', '_enter_target', '_wait_fire_entered_battle',
                  '_wait_again_entered_battle', '_grid_targets'):
            self.assertNotIn('fatigue', _src(getattr(RR, m)).lower(), m)

    def test_fatigue_after_failure_recovery_not_before_refresh(self):
        # 2026-09-08 correctness follow-up：疲劳安全节点后移——普通失败 REFRESH 时
        # 「battle → check_refresh → 稳定确认 → fatigue」，不得「battle → fatigue → refresh」。
        run_src = _src(RR.run)
        # 普通目标 battle 之后**不再**紧跟 _realm_raid_cycle_safe_break（那处已删）
        i_normal_gb = run_src.rindex('self.run_general_battle(con.general_battle_config)')
        after_gb = run_src[i_normal_gb:i_normal_gb + 160]
        self.assertNotIn('_realm_raid_cycle_safe_break', after_gb)
        # 每一处 check_refresh() 成功分支：先 failed_orders.clear() 再 _realm_raid_cycle_safe_break()
        for m in re.finditer(r'if self\.check_refresh\(\):', run_src):
            seg = run_src[m.end():m.end() + 220]
            self.assertIn('failed_orders.clear()', seg)
            self.assertLess(seg.index('failed_orders.clear()'),
                            seg.index('self._realm_raid_cycle_safe_break()'))
        # when_attack_fail REFRESH 分支里 check_refresh 在 _realm_raid_cycle_safe_break 之前
        i_ref = run_src.index('when_attack_fail == WhenAttackFail.REFRESH')
        refresh_block = run_src[i_ref:i_ref + 320]
        self.assertLess(refresh_block.index('self.check_refresh()'),
                        refresh_block.index('self._realm_raid_cycle_safe_break()'))

    def test_cycle_safe_break_confirms_stable_grid_before_fatigue(self):
        # helper 先有界等 I_BACK_RED（refresh / 结算收尾）确认回到稳定九宫格，再 try_fatigue_break
        sb = _src(RR._realm_raid_cycle_safe_break)
        self.assertIn('wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)', sb)
        self.assertLess(sb.index('wait_until_appear(self.I_BACK_RED'),
                        sb.index('try_fatigue_break('))
        from tasks.RealmRaid.script_task import RR_CYCLE_STABLE_TIMEOUT
        self.assertGreater(RR_CYCLE_STABLE_TIMEOUT, 0)
        self.assertNotIn('sleep(', sb)

    def test_ordinary_failure_still_follows_when_attack_fail_config(self):
        run_src = _src(RR.run)
        # 普通失败仍按 when_attack_fail：REFRESH → check_refresh；EXIT → break
        self.assertIn('when_attack_fail == WhenAttackFail.REFRESH', run_src)
        self.assertIn('when_attack_fail == WhenAttackFail.EXIT', run_src)
        self.assertIn('when_attack_fail == WhenAttackFail.CONTINUE', run_src)
        # broken 格涂黑不再只限 CONTINUE 模式（_broken_orders 代码体无模式判断）
        bo_body = _src(RR._broken_orders).split('"""')[-1]       # 去 docstring
        self.assertNotIn('WhenAttackFail', bo_body)
        self.assertNotIn('when_attack_fail', bo_body)


# --------------------------------------------------------------------------------------
# 2026-09-08 主循环 correctness follow-up：CONTINUE 跳过 / Fatigue 后移 /
# Last Target fresh revalidate / Unlock try/finally —— 源码形态
# --------------------------------------------------------------------------------------

class CorrectnessFollowupSourceTest(TestCase):
    def setUp(self):
        self.run_src = _src(RR.run)

    def test_failed_orders_is_local_set_not_frame_mutation(self):
        # CONTINUE 跳过用纯局部 set，不污染截图 / 不改 asset / 不伪造 broken marker
        self.assertIn('failed_orders: set = set()', self.run_src)
        self.assertIn('failed_orders.add(index)', self.run_src)
        self.assertIn('failed_orders.clear()', self.run_src)
        # run() 里不出现对 self.device.image 的切片涂黑（那只在 _grid_targets 的副本上做）
        self.assertNotIn('self.device.image[', self.run_src)
        self.assertNotIn('] = 0', self.run_src)

    def test_available_excludes_failed_orders_for_normal_selection(self):
        self.assertIn(
            'available = {order: m for order, m in targets.items() if order not in failed_orders}',
            self.run_src)
        self.assertIn('index = min(available)', self.run_src)
        self.assertIn('if not available:', self.run_src)

    def test_only_last_uses_raw_targets_not_filtered(self):
        # 退四判据始终用真实 UI 可攻打数 len(targets)，不是 skip 过滤后的 available
        self.assertIn('only_last = len(targets) == 1', self.run_src)
        self.assertNotIn('len(available) == 1', self.run_src)

    def test_retreat_entry_fresh_revalidates_sole_target_before_unlock(self):
        i_entry = self.run_src.index('if only_last and con.raid_config.exit_four:')
        i_else = self.run_src.index('# ---- 普通目标 ----')
        block = self.run_src[i_entry:i_else]
        # 入口：fresh screenshot → _is_only_remaining_target → 不满足则 continue，且发生在 unlock 之前
        i_screenshot = block.index('self.screenshot()')
        i_only = block.index('self._is_only_remaining_target(index)')
        i_unlock = block.index('self.ensure_lock(False)')
        self.assertLess(i_screenshot, i_only)
        self.assertLess(i_only, i_unlock)
        seg = block[i_only:i_unlock]
        self.assertIn('continue', seg)

    def test_is_only_remaining_target_helper_is_read_only(self):
        src = _src(RR._is_only_remaining_target)
        for tok in ('self.screenshot(', '.click(', 'appear_then_click', 'sleep(',
                    'random_delay', 'Timer('):
            self.assertNotIn(tok, src, tok)
        self.assertIn('self._grid_targets()', src)
        self.assertIn('len(targets) == 1', src)
        self.assertIn('order in targets', src)
        self.assertIn('_is_realm_raid_retryable_state()', src)

    def test_enter_target_require_only_remaining_param_and_post_pacing_recheck(self):
        src = _src(RR._enter_target)
        self.assertIn('def _enter_target(self, order: int, require_only_remaining: bool = False)', src)
        body = src.split('"""')[-1]
        i_sleep = body.index('sleep(pacing)')
        after = body[i_sleep:]
        # pacing 之后：退四目标再确认「仍是唯一目标」
        self.assertIn('self._is_only_remaining_target(order)', after)

    def test_retreat_unlock_uses_try_finally_no_except(self):
        i_entry = self.run_src.index('if only_last and con.raid_config.exit_four:')
        i_else = self.run_src.index('# ---- 普通目标 ----')
        block = self.run_src[i_entry:i_else]
        self.assertIn('self.ensure_lock(False)', block)
        self.assertIn('try:', block)
        self.assertIn('finally:', block)
        # finally 里恢复 lock_default（不写死 True / False）
        i_finally = block.index('finally:')
        self.assertIn('self.ensure_lock(lock_default)', block[i_finally:])
        self.assertNotIn('self.ensure_lock(True)', block)
        # AST：退四块里的 Try 节点无 except handler，且 body 覆盖 _enter_target / fire /
        # run_general_battle / _fire_again
        fn = ast.parse(self.run_src.lstrip()).body[0]
        tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
        self.assertEqual(len(tries), 1)
        tnode = tries[0]
        self.assertEqual(tnode_handlers := tnode.handlers, [])
        body_src = '\n'.join(ast.unparse(s) for s in tnode.body)
        for tok in ('_enter_target', 'self.fire(index)', 'run_general_battle', '_fire_again'):
            self.assertIn(tok, body_src, tok)
        fin_src = '\n'.join(ast.unparse(s) for s in tnode.finalbody)
        self.assertIn('ensure_lock(lock_default)', fin_src)

    def test_lock_default_captured_from_config(self):
        self.assertIn('lock_default = con.general_battle_config.lock_team_enable', self.run_src)

    def test_refresh_success_always_clears_failed_orders_then_fatigue(self):
        for m in re.finditer(r'if self\.check_refresh\(\):', self.run_src):
            seg = self.run_src[m.end():m.end() + 240]
            self.assertIn('failed_orders.clear()', seg, seg)
            self.assertIn('self._realm_raid_cycle_safe_break()', seg, seg)
            self.assertLess(seg.index('failed_orders.clear()'),
                            seg.index('self._realm_raid_cycle_safe_break()'))

    def test_normal_battle_not_immediately_followed_by_fatigue(self):
        i_gb = self.run_src.rindex('self.run_general_battle(con.general_battle_config)')
        after = self.run_src[i_gb:i_gb + 160]
        self.assertNotIn('_realm_raid_cycle_safe_break', after)

    def test_continue_branch_records_skip_then_fatigue_then_continue(self):
        # 共享尾部里的 CONTINUE 分支（含 failed_orders.add）——不是 `if not available:` 那个
        i = self.run_src.index('failed_orders.add(index)')
        seg = self.run_src[i:i + 240]
        self.assertLess(seg.index('failed_orders.add(index)'),
                        seg.index('self._realm_raid_cycle_safe_break()'))
        self.assertLess(seg.index('self._realm_raid_cycle_safe_break()'), seg.index('continue'))
        # 这个分支的判据是 CONTINUE（往前找最近的 when_attack_fail 判据）
        self.assertIn('WhenAttackFail.CONTINUE', self.run_src[i - 300:i])

    def test_exit_mode_no_skip_no_refresh_no_fatigue(self):
        # 共享尾部的 EXIT 分支（在 `if not last_battle:` 内、REFRESH 之后、CONTINUE 之前）
        i_ref = self.run_src.index('when_attack_fail == WhenAttackFail.REFRESH')
        i_exit = self.run_src.index('when_attack_fail == WhenAttackFail.EXIT', i_ref)
        i_cont = self.run_src.index('when_attack_fail == WhenAttackFail.CONTINUE', i_exit)
        seg = self.run_src[i_exit:i_cont]
        self.assertIn('break', seg)
        self.assertNotIn('failed_orders.add', seg)
        self.assertNotIn('check_refresh', seg)
        self.assertNotIn('_realm_raid_cycle_safe_break', seg)


# --------------------------------------------------------------------------------------
# 2026-09-08 主循环 correctness follow-up —— run() 主循环行为（最小 harness 驱动）
# --------------------------------------------------------------------------------------

from tasks.RealmRaid.config import WhenAttackFail
from module.exception import TaskEnd


class _RunHarness:
    """驱动 RealmRaid.run() 主循环：除 run() 本体外全部 mock，按 iteration 供给
    _grid_targets / fire / run_general_battle 等，并按序记录关键事件。"""

    def __init__(self, *, when_attack_fail, grid_seq, exit_four=True, three_refresh=False,
                 lock_default=True, enter_ok=True, fire_ok=True, battle_seq=None,
                 fire_again_seq=None, refresh_seq=None, only_remaining_seq=None,
                 battle_raises=False):
        self.grid_seq = [dict(g) for g in grid_seq]
        self.events = []
        t = RR.__new__(RR)
        self.t = t
        gb_cfg = SimpleNamespace(lock_team_enable=lock_default)
        self.con = SimpleNamespace(
            raid_config=SimpleNamespace(number_base=0, number_attack=30, exit_four=exit_four,
                                        three_refresh=three_refresh, when_attack_fail=when_attack_fail),
            general_battle_config=gb_cfg,
            switch_soul_config=SimpleNamespace(enable=False, enable_switch_by_name=False),
        )
        t.config = SimpleNamespace(realm_raid=self.con)

        tick = {'n': 0}

        def _check_ticket(base):
            # 调用 0 = 主循环前的 prologue gate；调用 1..N = 每轮循环顶（对应 grid_seq[0..N-1]）；
            # 调用 N+1 起返回 False 退出主循环。
            i = tick['n']
            tick['n'] += 1
            ok = i <= len(self.grid_seq)
            self.events.append(('check_ticket', ok))
            return ok
        t.check_ticket = Mock(side_effect=_check_ticket)

        gi = {'n': 0}

        def _grid_targets():
            i = gi['n']
            gi['n'] += 1
            g = dict(self.grid_seq[i]) if i < len(self.grid_seq) else {}
            self.events.append(('grid', dict(g)))
            return g
        t._grid_targets = Mock(side_effect=_grid_targets)

        battle_it = _tail_seq(battle_seq if battle_seq is not None else [True])

        def _rgb(*a, **kw):
            if battle_raises:
                self.events.append(('run_general_battle', 'RAISE'))
                raise RuntimeError('boom')
            r = next(battle_it)
            self.events.append(('run_general_battle', r))
            return r
        t.run_general_battle = Mock(side_effect=_rgb)

        again_it = _tail_seq(fire_again_seq if fire_again_seq is not None else [True])

        def _again():
            r = next(again_it)
            self.events.append(('fire_again', r))
            return r
        t._fire_again = Mock(side_effect=_again)

        refresh_it = _tail_seq(refresh_seq if refresh_seq is not None else [True])

        def _refresh(*a, **kw):
            r = next(refresh_it)
            self.events.append(('check_refresh', r))
            return r
        t.check_refresh = Mock(side_effect=_refresh)

        only_it = _tail_seq(only_remaining_seq if only_remaining_seq is not None else [True])

        def _only(order):
            r = next(only_it)
            self.events.append(('is_only_remaining', order, r))
            return r
        t._is_only_remaining_target = Mock(side_effect=_only)

        def _enter(order, require_only_remaining=False):
            self.events.append(('enter_target', order, require_only_remaining))
            return enter_ok
        t._enter_target = Mock(side_effect=_enter)

        def _fire(order):
            self.events.append(('fire', order))
            return fire_ok
        t.fire = Mock(side_effect=_fire)

        t._realm_raid_cycle_safe_break = Mock(
            side_effect=lambda: self.events.append('cycle_safe_break'))
        t.ensure_lock = Mock(side_effect=lambda v: self.events.append(('ensure_lock', v)))
        t.build_quick_exit_config = Mock(side_effect=lambda c: c)
        t.check_medal_is_frog = Mock(return_value=False)
        t.reward_detect_click = Mock(return_value=False)
        t.begin_fatigue_task = Mock(
            side_effect=lambda name: self.events.append(('begin_fatigue', name)))
        t.goto_page = Mock()
        t.set_next_run = Mock()
        t.screenshot = Mock()
        t.is_frog = Mock(return_value=False)
        t.appear = Mock(return_value=False)

    def run(self):
        try:
            self.t.run()
        except TaskEnd:
            pass
        return self.events

    def fires(self):
        return [e[1] for e in self.events if isinstance(e, tuple) and e[0] == 'fire']

    def locks(self):
        return [e[1] for e in self.events if isinstance(e, tuple) and e[0] == 'ensure_lock']

    def kinds(self):
        return [e if isinstance(e, str) else e[0] for e in self.events]


class RunLoopBehaviorTest(TestCase):
    # ---- A. CONTINUE 跳过刚失败目标 ----
    def test_continue_failure_skips_failed_order_next_iteration(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=False,
                        grid_seq=[{1: 'm', 2: 'm', 3: 'm'}] * 3,
                        battle_seq=[False, False, True])
        h.run()
        self.assertEqual(h.fires(), [1, 2, 3])          # 1 失败→跳过→2；2 失败→跳过→3
        self.assertNotIn('check_refresh', h.kinds())    # CONTINUE 不刷新

    def test_continue_two_failures_then_third_order(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=False,
                        grid_seq=[{1: 'm', 2: 'm', 3: 'm'}] * 3,
                        battle_seq=[False, False, True])
        h.run()
        self.assertEqual(h.fires(), [1, 2, 3])

    def test_continue_failed_target_still_ui_attackable_is_still_skipped(self):
        # 失败目标 UI 仍 attackable（grid 一直含它）→ 仍必须 skip（不靠 broken marker）
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=False,
                        grid_seq=[{2: 'm', 5: 'm'}, {2: 'm', 5: 'm'}],
                        battle_seq=[False, True])
        h.run()
        self.assertEqual(h.fires(), [2, 5])             # 2 失败后不再选 2（尽管 grid 仍含 2）

    def test_continue_all_skipped_refreshes_and_clears(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=False,
                        grid_seq=[{5: 'm', 8: 'm'}] * 4,
                        battle_seq=[False, False, True], refresh_seq=[True])
        ev = h.run()
        # 5 失败、8 失败 → available 空 → refresh + clear → 下一轮 5 又可选
        self.assertEqual(h.fires(), [5, 8, 5])
        self.assertEqual(h.kinds().count('check_refresh'), 1)
        i_ref = ev.index(('check_refresh', True))
        # refresh 之后才有 fatigue（recovery 完成后）
        self.assertIn('cycle_safe_break', h.kinds()[i_ref:])

    # ---- B. Fatigue Safe Point 后移 ----
    def test_normal_refresh_failure_fatigue_after_refresh(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=False,
                        grid_seq=[{1: 'm'}, {1: 'm'}],
                        battle_seq=[False, True], refresh_seq=[True])
        ev = h.run()
        i_battle = ev.index(('run_general_battle', False))
        i_refresh = ev.index(('check_refresh', True))
        i_sb = ev.index('cycle_safe_break')
        self.assertLess(i_battle, i_refresh)
        self.assertLess(i_refresh, i_sb)
        # battle 失败与 refresh 之间没有 fatigue
        self.assertNotIn('cycle_safe_break', h.kinds()[i_battle:i_refresh])

    def test_normal_continue_failure_fatigue_after_skip_recorded(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=False,
                        grid_seq=[{1: 'm', 2: 'm'}, {2: 'm'}],
                        battle_seq=[False, True])
        ev = h.run()
        i_battle = ev.index(('run_general_battle', False))
        i_sb = ev.index('cycle_safe_break')
        self.assertLess(i_battle, i_sb)
        self.assertNotIn('check_refresh', h.kinds())      # CONTINUE 不刷新
        self.assertEqual(h.fires(), [1, 2])              # 下一轮跳过 1

    def test_retreat_final_failure_refresh_before_fatigue(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{5: 'm'}],
                        only_remaining_seq=[True],
                        battle_seq=[True, True, True, True, False],   # 首战 + 4；最后真打输
                        fire_again_seq=[True, True, True, True],
                        refresh_seq=[True])
        ev = h.run()
        i_lock_restore = ev.index(('ensure_lock', True))          # finally 恢复
        i_refresh = ev.index(('check_refresh', True))
        i_sb = ev.index('cycle_safe_break')
        self.assertLess(i_lock_restore, i_refresh)                # 先恢复锁
        self.assertLess(i_refresh, i_sb)                          # 刷新完成后才 fatigue

    # ---- C. Last Target fresh revalidate ----
    def test_retreat_aborts_when_not_sole_target_on_fresh_frame(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=True,
                        grid_seq=[{5: 'm'}, {1: 'm', 2: 'm'}],
                        only_remaining_seq=[False],               # fresh 帧显示不止 1 个
                        battle_seq=[True])
        h.run()
        # 退四被中止：没有 unlock / enter_target / fire
        self.assertNotIn(('ensure_lock', False), h.events)
        self.assertEqual([e for e in h.events if isinstance(e, tuple) and e[0] == 'enter_target'
                          and e[2] is True], [])
        # 重扫后进入普通分支打 1
        self.assertEqual(h.fires(), [1])

    def test_only_last_uses_raw_grid_not_skip_filtered_count(self):
        # raw grid = {5,8}，failed={5} → available={8} 只 1 个，但 raw 是 2 → 不进退四
        h = _RunHarness(when_attack_fail=WhenAttackFail.CONTINUE, exit_four=True,
                        grid_seq=[{5: 'm', 8: 'm'}, {5: 'm', 8: 'm'}],
                        battle_seq=[False, True])
        h.run()
        self.assertEqual([e for e in h.events if isinstance(e, tuple)
                          and e[0] == 'is_only_remaining'], [])   # 退四从未被评估
        self.assertEqual(h.fires(), [5, 8])

    def test_true_sole_target_enters_retreat_not_requiring_index_9(self):
        # 目标是 order 5（不是 9）也能进退四——退四靠「只剩最后 1 个」不靠 index == 9
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{5: 'm'}],
                        only_remaining_seq=[True],
                        battle_seq=[True, True, True, True, True],
                        fire_again_seq=[True, True, True, True])
        h.run()
        self.assertIn(('is_only_remaining', 5, True), h.events)
        self.assertIn(('ensure_lock', False), h.events)           # 退四解锁
        self.assertIn(('enter_target', 5, True), h.events)        # require_only_remaining=True
        self.assertEqual(h.events.count(('fire_again', True)), 4)

    # ---- D. Unlock try/finally ----
    def test_retreat_finally_restores_lock_on_enter_target_false(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{5: 'm'}], only_remaining_seq=[True], enter_ok=False)
        ev = h.run()
        # 退四 unlock(False) → enter_target False → finally unlock(lock_default=True)
        i_unlock = ev.index(('ensure_lock', False))
        i_restore = ev.index(('ensure_lock', True), i_unlock + 1)
        self.assertLess(i_unlock, i_restore)
        self.assertNotIn('fire', h.kinds())
        self.assertNotIn('run_general_battle', h.kinds())

    def test_retreat_finally_restores_lock_on_fire_false(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{5: 'm'}], only_remaining_seq=[True], fire_ok=False)
        ev = h.run()
        self.assertIn(('fire', 5), ev)
        i_unlock = ev.index(('ensure_lock', False))
        self.assertIn(('ensure_lock', True), ev[i_unlock + 1:])
        self.assertNotIn('run_general_battle', h.kinds())

    def test_retreat_finally_restores_lock_and_propagates_exception(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{5: 'm'}], only_remaining_seq=[True], battle_raises=True)
        with self.assertRaises(RuntimeError):
            h.t.run()
        # 原异常传播（不是 TaskEnd）、且 finally 恢复了锁
        i_unlock = h.events.index(('ensure_lock', False))
        self.assertIn(('ensure_lock', True), h.events[i_unlock + 1:])

    def test_retreat_lock_default_false_restores_false_not_true(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True, lock_default=False,
                        grid_seq=[{5: 'm'}], only_remaining_seq=[True],
                        battle_seq=[True, True, True, True, True],
                        fire_again_seq=[True, True, True, True])
        h.run()
        # 用户原本不锁 → 退四结束恢复「不锁」，从不出现 ensure_lock(True)
        self.assertNotIn(('ensure_lock', True), h.events)
        self.assertIn(('ensure_lock', False), h.events)

    # ---- E. EXIT ----
    def test_exit_mode_failure_breaks_no_skip_no_refresh_no_fatigue(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.EXIT, exit_four=False,
                        grid_seq=[{1: 'm', 2: 'm'}], battle_seq=[False])
        h.run()
        self.assertEqual(h.fires(), [1])
        self.assertNotIn('check_refresh', h.kinds())
        self.assertNotIn('cycle_safe_break', h.kinds())

    # ---- F. 现有胜利路径回归 ----
    def test_normal_win_triggers_fatigue_at_cycle_end(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=False,
                        grid_seq=[{1: 'm', 2: 'm'}], battle_seq=[True])
        ev = h.run()
        i_battle = ev.index(('run_general_battle', True))
        self.assertIn('cycle_safe_break', h.kinds()[i_battle:])
        self.assertNotIn('check_refresh', h.kinds())

    def test_retreat_win_triggers_fatigue_via_shared_tail(self):
        h = _RunHarness(when_attack_fail=WhenAttackFail.REFRESH, exit_four=True,
                        grid_seq=[{7: 'm'}], only_remaining_seq=[True],
                        battle_seq=[True, True, True, True, True],
                        fire_again_seq=[True, True, True, True])
        ev = h.run()
        self.assertEqual(h.events.count(('run_general_battle', True)), 5)   # 首战 + 4
        self.assertEqual(h.events.count(('fire_again', True)), 4)
        self.assertIn('cycle_safe_break', h.kinds())
        # 退四胜利后恢复锁
        self.assertEqual(h.locks()[-1], True)


if __name__ == '__main__':
    import unittest
    unittest.main()
