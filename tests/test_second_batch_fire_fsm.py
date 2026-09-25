# This Python file uses the following encoding: utf-8
"""常驻刷本 FIRE FSM 第二批 + Fatigue 安全节点第一批（2026-09-08）。

本轮：
- Orochi `run_alone` / EvoZone `run_alone` 的内层「点 `I_*_FIRE` → `not appear(I_*_FIRE)` →
  直接 `run_general_battle`」反模式，收口为与 RealmRaid `fire()` 同一 FIRE Contract 的三态
  状态机：`_fire_orochi_alone` / `_fire_evozone_alone`（正向 `is_in_battle()` 确认 / 每 attempt
  独立 `REACTION_FIRE` / fresh reconfirm / bounded `*_FIRE_MAX_TRIES=4` + `Timer(*_FIRE_TIMEOUT=10)`
  + `*_FIRE_POST_CLICK_TIMEOUT=3` / 可达 `return False`）+ `_wait_*_fire_state`（三态、不点坐标）
  + `_is_*_challenge_retryable`（纯只读）。caller 用 `if self._fire_*_alone():` 守卫
  `run_general_battle`，不误交接。
- Orochi / EvoZone `run_alone` 接入 Fatigue 安全节点：`begin_fatigue_task` + 一场战斗完整结束、
  `run_general_battle` 回到稳定挑战页后 `try_fatigue_break(safe=True, repeat_completed=True,
  deadline=)`；leader / member / wild 路径**不接**（邀请 / 房间 / 队友同步，idle 会破坏组队）。
- 契灵（BondlingFairyland）`I_BALL_FIRE` = **PARTIAL 未迁**：结构是「连点直到消失 +
  `BondlingNumberMax` 资源耗尽耦合 + 两条独立语句 caller」，不是单次稳定 Point FIRE →
  GeneralBattle，套模板需业务级重构（写入 ROADMAP）。

`REACTION_FIRE=(0.4,0.8)` / `appear_then_click` primitive / RealmRaid `fire()` / RyouToppa
`attack_area` / GeneralBattle Settlement / T7 / FrameWait / Exploration FIRE 均**未改**。
"""

import ast
import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.Orochi.script_task import (
    ScriptTask as Orochi,
    OROCHI_FIRE_MAX_TRIES,
    OROCHI_FIRE_TIMEOUT,
    OROCHI_FIRE_POST_CLICK_TIMEOUT,
)
from tasks.EvoZone.script_task import (
    ScriptTask as EvoZone,
    EVOZONE_FIRE_MAX_TRIES,
    EVOZONE_FIRE_TIMEOUT,
    EVOZONE_FIRE_POST_CLICK_TIMEOUT,
)
from tasks.BondlingFairyland.script_task import ScriptTask as Bondling


def _src(func) -> str:
    return inspect.getsource(func)


class _FakeTimer:
    """确定性 Timer 替身：单实例 reached() 超过 budget 次即到期（防测试无限循环）。"""

    budget = 8

    def __init__(self, limit, *a, **kw):
        self.limit = limit
        self._n = 0

    def start(self):
        return self

    def reached(self):
        self._n += 1
        return self._n > _FakeTimer.budget

    def reset(self):
        self._n = 0


def _seq(values):
    """把有限序列变成「跑完后无限重复最后一个值」的迭代器，避免 mock side_effect 耗尽。"""
    values = list(values) or [False]
    for v in values:
        yield v
    while True:
        yield values[-1]


# 每个 task 的 (显示名, 类, fire 方法名, wait 方法名, retryable 方法名, FIRE asset 属性,
#                MAX_TRIES, TIMEOUT, POST_CLICK_TIMEOUT, 模块路径)
_TASKS = [
    ('Orochi', Orochi, '_fire_orochi_alone', '_wait_orochi_fire_state',
     '_is_orochi_challenge_retryable', 'I_OROCHI_FIRE',
     OROCHI_FIRE_MAX_TRIES, OROCHI_FIRE_TIMEOUT, OROCHI_FIRE_POST_CLICK_TIMEOUT,
     'tasks.Orochi.script_task'),
    ('EvoZone', EvoZone, '_fire_evozone_alone', '_wait_evozone_fire_state',
     '_is_evozone_challenge_retryable', 'I_EVOZONE_FIRE',
     EVOZONE_FIRE_MAX_TRIES, EVOZONE_FIRE_TIMEOUT, EVOZONE_FIRE_POST_CLICK_TIMEOUT,
     'tasks.EvoZone.script_task'),
]


def _mk(task_cls, fire_method, fire_attr, *, in_battle, fire_visible=None):
    """构造一个能驱动 `_fire_*_alone` 的替身，返回 (events, task, bound_fire_method)。"""
    events = []
    t = task_cls.__new__(task_cls)
    t.config = SimpleNamespace(orochi=SimpleNamespace(fire_reaction=FireReactionConfig()),
                               evo_zone=SimpleNamespace(fire_reaction=FireReactionConfig()))
    fire_asset = getattr(task_cls, fire_attr)
    t.device = SimpleNamespace(
        image='FRAME',
        click_record_clear=Mock(side_effect=lambda: events.append('clear')),
    )
    t.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
    t.appear_then_click = Mock(
        side_effect=lambda *a, **kw: events.append(('fire_click', a, kw)) or True)
    t.is_in_battle = Mock(side_effect=_seq(in_battle))
    fire_it = _seq(fire_visible or [False])

    def _appear(tgt, **kw):
        if tgt is fire_asset:
            return next(fire_it)
        return False

    t.appear = Mock(side_effect=_appear)
    return events, t, getattr(t, fire_method)


# =====================================================================================
# REACTION_FIRE profile —— 本轮不改值
# =====================================================================================

class ReactionFireUnchangedTest(TestCase):
    def test_reaction_fire_still_0_4_to_0_8(self):
        self.assertEqual(rp.REACTION_FIRE, (0.4, 0.8))
        self.assertEqual(rp.REACTION_PROFILES.get('FIRE'), (0.4, 0.8))
        self.assertIs(rp.REACTION_PROFILES_PROVISIONAL, True)

    def test_batch1_profiles_unchanged(self):
        self.assertEqual(rp.REACTION_FAST, (0.18, 0.35))
        self.assertEqual(rp.REACTION_NORMAL, (0.45, 0.85))
        self.assertEqual(rp.REACTION_NORMAL_HIGH, (0.60, 1.00))
        self.assertEqual(rp.REACTION_CONFIRM, (0.55, 1.20))
        self.assertEqual(rp.REACTION_NAVIGATION, (0.55, 1.10))
        self.assertEqual(rp.REACTION_DELIBERATE, (0.90, 1.60))

    def test_second_batch_constants_are_engineering_baseline(self):
        for name, *_rest in _TASKS:
            mt, to, pct = _rest[5], _rest[6], _rest[7]
            with self.subTest(task=name):
                self.assertEqual(mt, 4)
                self.assertEqual(to, 10)
                self.assertEqual(pct, 3)


# =====================================================================================
# Orochi / EvoZone `_fire_*_alone` —— 三态 FIRE 状态机行为
# =====================================================================================

class OrochiEvoZoneFireFsmTest(TestCase):
    def setUp(self):
        _FakeTimer.budget = 8
        self._patchers = []
        for _name, _cls, _fm, _wm, _rm, _attr, _mt, _to, _pct, mod in _TASKS:
            for sym in ('Timer', 'sleep', 'random_delay'):
                p = patch(f'{mod}.{sym}', _FakeTimer if sym == 'Timer'
                          else (Mock(return_value=0.6) if sym == 'random_delay' else Mock()))
                p.start()
                self._patchers.append(p)
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_FakeTimer, 'budget', 8))

    def _each(self):
        for name, cls, fm, wm, rm, attr, mt, to, pct, mod in _TASKS:
            yield name, cls, fm, wm, rm, attr, mt, to, pct, mod

    def test_positive_battle_at_top_returns_true_without_click(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                events, t, fire = _mk(cls, fm, attr, in_battle=[True])
                self.assertIs(fire(), True)
                t.appear_then_click.assert_not_called()

    def test_positive_battle_after_click_returns_true(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                # top 未战斗 + FIRE 可见 → reaction → 仍未战斗 → FIRE 仍在 → click
                # → _wait: is_in_battle True → True
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False, False, True],
                                      fire_visible=[True, True, True])
                self.assertIs(fire(), True)
                t.appear_then_click.assert_called_once()
                args, kwargs = t.appear_then_click.call_args
                self.assertIs(args[0], getattr(cls, attr))
                self.assertEqual(kwargs, {'interval': 0})
                # 没有 confirm_delay 叠加
                self.assertNotIn('confirm_delay', kwargs)

    def test_fire_gone_during_reaction_does_not_click_stale(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                # FIRE 第一次可见 → reaction → fresh frame FIRE 消失 → 不 click；bounded 用尽 → False
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 200,
                                      fire_visible=[True] + [False] * 200)
                self.assertIs(fire(), False)
                t.appear_then_click.assert_not_called()

    def test_transition_blank_then_battle_returns_true_without_extra_click(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                # click 后：blank 过渡帧（is_in_battle=F, FIRE=F）→ 不 return False；
                # 下一帧 is_in_battle=True → return True
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False, False, False, True],
                                      fire_visible=[True, True, True, False, False])
                self.assertIs(fire(), True)
                self.assertEqual(t.appear_then_click.call_count, 1)

    def test_transition_unknown_all_frames_bounded_false_no_click(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                # 点 FIRE 后一直 blank（transition/unknown）→ 'timeout' → 下一 attempt
                # FIRE 已不可见且非 retryable → 又 _wait → 'timeout' … bounded → False
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 400,
                                      fire_visible=[True] + [False] * 400)
                self.assertIs(fire(), False)
                self.assertLessEqual(t.appear_then_click.call_count, 1)

    def test_retryable_state_allows_next_attempt_then_battle(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                # a1: top(F) + FIRE(T) → reaction → recheck(F) + FIRE(T) → click#1
                #     → _wait: is_in_battle(F) + retryable FIRE(T) → 'retryable' → 下一 attempt
                # a2: top(F) + FIRE(T) → reaction → recheck(F) + FIRE(T) → click#2
                #     → _wait: is_in_battle(T) → 'battle' → True
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 5 + [True],
                                      fire_visible=[True] * 12)
                self.assertIs(fire(), True)
                self.assertGreaterEqual(t.appear_then_click.call_count, 2)

    def test_bounded_by_max_tries_returns_false(self):
        for name, cls, fm, wm, rm, attr, mt, *_ in self._each():
            with self.subTest(task=name):
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 400,
                                      fire_visible=[True] * 400)
                self.assertIs(fire(), False)
                self.assertLessEqual(t.appear_then_click.call_count, mt)
                self.assertGreaterEqual(t.appear_then_click.call_count, 1)

    def test_timeout_timer_exits_false_immediately(self):
        _FakeTimer.budget = 0
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 50,
                                      fire_visible=[True] * 50)
                self.assertIs(fire(), False)
                t.appear_then_click.assert_not_called()

    def test_prologue_clears_click_record(self):
        for name, cls, fm, wm, rm, attr, *_ in self._each():
            with self.subTest(task=name):
                events, t, fire = _mk(cls, fm, attr, in_battle=[True])
                fire()
                self.assertIn('clear', events)

    def test_reaction_sampled_once_per_attempt(self):
        for name, cls, fm, wm, rm, attr, *_rest in self._each():
            mod = _rest[-1]
            with self.subTest(task=name):
                events, t, fire = _mk(cls, fm, attr,
                                      in_battle=[False] * 200,
                                      fire_visible=[True] * 12)
                fire()
                m = __import__(mod, fromlist=['random_delay'])
                self.assertGreaterEqual(m.random_delay.call_count, 2)
                for c in m.random_delay.call_args_list:
                    self.assertEqual(c.args, (0.4, 0.8))


# =====================================================================================
# 源码形态护栏：三态 / bounded / 无叠加 / 纯只读 helper
# =====================================================================================

class FireFsmSourceShapeTest(TestCase):
    def test_fire_method_shape(self):
        for name, cls, fm, wm, rm, attr, mt, to, pct, mod in _TASKS:
            src = _src(getattr(cls, fm))
            with self.subTest(task=name):
                # 每 attempt 独立 REACTION_FIRE，恰一次，无 confirm_delay / 第二套 delay
                self.assertRegex(src, r'random_delay\(\*fire_reaction_range\(self\.config\.\w+\.fire_reaction\)\)')
                self.assertEqual(src.count('random_delay('), 1)
                self.assertNotIn('confirm_delay', src)
                self.assertNotIn('REACTION_FAST', src)
                # bounded：有限 attempt + 墙钟 Timer，无 while True
                self.assertNotIn('while True', src)
                self.assertNotIn('while 1', src)
                self.assertRegex(src, r'range\(1,\s*\w+_FIRE_MAX_TRIES \+ 1\)')
                self.assertRegex(src, r'Timer\(\w+_FIRE_TIMEOUT\)')
                # 正向战斗确认 + 可达失败返回
                self.assertIn('self.is_in_battle(False)', src)
                self.assertIn('return False', src)
                # post-click 走三态 wait
                self.assertIn(f'self.{wm}()', src)

    def test_wait_state_is_three_way_and_clickless(self):
        for name, cls, fm, wm, rm, attr, *_ in _TASKS:
            src = _src(getattr(cls, wm))
            with self.subTest(task=name):
                self.assertIn("'battle'", src)
                self.assertIn("'retryable'", src)
                self.assertIn("'timeout'", src)
                self.assertIn('is_in_battle(False)', src)
                self.assertIn(f'self.{rm}()', src)
                # 期间不点任何坐标、不 sleep / 不采样 reaction
                self.assertNotIn('.click(', src)
                self.assertNotIn('appear_then_click', src)
                self.assertNotIn('sleep(', src)
                self.assertNotIn('random_delay', src)

    def test_retryable_helper_is_read_only(self):
        for name, cls, fm, wm, rm, attr, *_ in _TASKS:
            src = _src(getattr(cls, rm))
            with self.subTest(task=name):
                self.assertIn(f'self.appear(self.{attr})', src)
                for forbidden in ('screenshot', '.click(', 'appear_then_click',
                                  'sleep(', 'random_delay', 'Timer('):
                    self.assertNotIn(forbidden, src)

    def test_caller_guards_run_general_battle_behind_fire(self):
        for name, cls, fm, wm, rm, attr, *_ in _TASKS:
            src = _src(cls.run_alone)
            with self.subTest(task=name):
                self.assertIn(f'if self.{fm}():', src)
                tree = ast.parse(src.lstrip())
                fn = tree.body[0]
                # 找到 `if self._fire_*_alone():` 节点，run_general_battle 必须在其体内
                guarded = False
                for node in ast.walk(fn):
                    if (isinstance(node, ast.If)
                            and isinstance(node.test, ast.Call)
                            and isinstance(node.test.func, ast.Attribute)
                            and node.test.func.attr == fm):
                        body_src = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                        self.assertIn('run_general_battle', body_src)
                        self.assertIn('try_fatigue_break', body_src)
                        guarded = True
                self.assertTrue(guarded)
                # run_general_battle 从不在 if 外裸调用
                bare = [n for n in ast.walk(fn)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == 'run_general_battle']
                self.assertEqual(len(bare), 1)


# =====================================================================================
# Fatigue 安全节点第一批：只在 run_alone，且在完整 cycle 之后
# =====================================================================================

class FatigueSafePointPlacementTest(TestCase):
    def test_alone_paths_begin_and_break_fatigue(self):
        for name, cls, *_ in _TASKS:
            src = _src(cls.run_alone)
            with self.subTest(task=name):
                self.assertIn(f"self.begin_fatigue_task('{name}')", src)
                self.assertIn('self.try_fatigue_break(safe=True, repeat_completed=True, deadline=deadline)', src)

    def test_fatigue_break_after_run_general_battle_not_before_fire(self):
        for name, cls, fm, *_ in _TASKS:
            src = _src(cls.run_alone)
            with self.subTest(task=name):
                i_fire = src.index(f'if self.{fm}():')
                i_gb = src.index('run_general_battle', i_fire)
                i_break = src.index('try_fatigue_break', i_fire)
                # try_fatigue_break 在 fire() 守卫之后、且在 run_general_battle 之后
                self.assertLess(i_gb, i_break)
                # begin_fatigue_task 在 fire() 循环之前
                self.assertLess(src.index('begin_fatigue_task'), i_fire)

    def test_fire_fsm_methods_have_no_fatigue(self):
        for name, cls, fm, wm, rm, *_ in _TASKS:
            for mname in (fm, wm, rm):
                src = _src(getattr(cls, mname))
                with self.subTest(task=name, method=mname):
                    self.assertNotIn('fatigue', src.lower())

    def test_leader_member_wild_paths_do_not_touch_fatigue(self):
        paths = [
            (Orochi, 'run_leader'), (Orochi, 'run_member'), (Orochi, 'run_wild'),
            (EvoZone, 'run_leader'), (EvoZone, 'run_member'), (EvoZone, 'run_wild'),
        ]
        for cls, mname in paths:
            src = _src(getattr(cls, mname))
            with self.subTest(cls=cls.__module__, method=mname):
                self.assertNotIn('begin_fatigue_task', src)
                self.assertNotIn('try_fatigue_break', src)


# =====================================================================================
# 契灵（BondlingFairyland）= PARTIAL，本轮未迁 FIRE / 未接 Fatigue
# =====================================================================================

class BondlingFairylandPartialTest(TestCase):
    def test_module_does_not_import_or_use_reaction_fire(self):
        m = __import__('tasks.BondlingFairyland.script_task', fromlist=['x'])
        self.assertNotIn('REACTION_FIRE', inspect.getsource(m))

    def test_run_alone_still_plain_click_until_gone(self):
        src = _src(Bondling.run_alone)
        # 结构未变：连点 I_BALL_FIRE 直到消失 + BondlingNumberMax 资源耗尽路径
        self.assertIn('self.appear_then_click(self.I_BALL_FIRE, interval=1)', src)
        self.assertIn('BondlingNumberMax', src)
        # 没有套 FIRE 三态模板
        for tok in ('_wait_ball_fire_state', '_is_bondling', '_fire_bondling',
                    'REACTION_FIRE', 'random_delay(*REACTION_FIRE)'):
            self.assertNotIn(tok, src)

    def test_no_fatigue_in_bondling(self):
        for mname in ('run', 'run_alone', 'run_catch', 'run_leader', 'run_member', 'switch_ball'):
            src = _src(getattr(Bondling, mname))
            with self.subTest(method=mname):
                self.assertNotIn('begin_fatigue_task', src)
                self.assertNotIn('try_fatigue_break', src)


# =====================================================================================
# 范围外 FIRE / timing 未改
# =====================================================================================

class OutOfScopeUnchangedTest(TestCase):
    def test_realm_raid_and_ryoutoppa_fire_untouched_this_round(self):
        from tasks.RealmRaid.script_task import ScriptTask as RealmRaid
        from tasks.RyouToppa.script_task import ScriptTask as RyouToppa
        rr = _src(RealmRaid.fire)
        self.assertIn('random_delay(*fire_reaction_range(self.config.realm_raid.fire_reaction))', rr)
        self.assertEqual(rr.count('random_delay('), 1)
        rt = _src(RyouToppa.attack_area)
        self.assertIn('random_delay(*fire_reaction_range(self.config.ryou_toppa.fire_reaction))', rt)
        self.assertIn('random_delay(1.0, 3.0)', rt)

    def test_exploration_fire_untouched(self):
        from tasks.Exploration.base import BaseExploration
        src = _src(BaseExploration.fire)
        self.assertNotIn('REACTION_FIRE', src)
        self.assertNotIn('confirm_delay', src)
        self.assertIn('max_tries', src)
        self.assertIn('Timer(10)', src)

    def test_orochi_evozone_non_alone_fire_paths_not_migrated(self):
        for func in (Orochi.run_wild, Orochi.run_member, Orochi.run_leader,
                     EvoZone.run_member, EvoZone.run_leader):
            src = _src(func)
            with self.subTest(func=func.__qualname__):
                self.assertNotIn('REACTION_FIRE', src)
                for tok in ('I_OROCHI_FIRE', 'I_OROCHI_WILD_FIRE', 'I_EVOZONE_FIRE'):
                    if f'{tok}, interval=1' in src:
                        self.assertNotIn(f'{tok}, interval=1, confirm_delay', src)
