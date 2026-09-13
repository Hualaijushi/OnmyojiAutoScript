# This Python file uses the following encoding: utf-8
"""通用组队挑战入口 `GeneralInvite.click_fire()`：Reaction Timing（2026-09-08 §4.54）
+ Battle Entry post-click 状态机 / bounded FSM 收口（2026-09-08 §4.55）。

`click_fire()` 是 Orochi / EvoZone 等 11 个副本组队 / 房主点「挑战 / 开始战斗」的唯一公共实现
（7 个经 `run_invite` 的 `room_check_can_fire` 门槛调用；ExperienceYoukai / GoldYoukai / Hunt /
Tako 直接调用）。

§4.54（reaction）：识别 `I_FIRE` / `I_FIRE_SEA` → 每 attempt 独立 `random_delay(*REACTION_FIRE)`
（0.4~0.8s）→ `sleep` → fresh `screenshot` → 二次确认 → click。

§4.55（本轮，state / bounded）：`click_fire()` 从「`while 1` + `not is_in_room(False)` 即成功」
收口为 **bounded 四态 transaction**，返回 `str`：
- `'battle'`：`_battle_entry_positive()`（优先复用 `is_in_battle()`）—— 唯一 success；
- `'room_failed'`：`_room_entry_failed()`（`I_MATCHING` / `I_CHECK_MAIN` / `I_CHECK_EXPLORATION`）
  —— 明确房间失效；
- `'timeout'`：有限 `GI_FIRE_MAX_TRIES` / 墙钟 `GI_FIRE_TIMEOUT` 用尽仍未确认。
四态 = BATTLE / ROOM_FAILED / RETRYABLE_ROOM / TRANSITION_UNKNOWN。**「不在房间」单独发生 ≠
success**——归 UNKNOWN、有界 polling、不点坐标。`run_invite` 只在 `'battle'` 才 `return True`；
4 个直接 caller 加 `if self.click_fire() == 'battle':` guard。

不变：`REACTION_FIRE`=(0.4,0.8) / 每 attempt 独立采样 / fresh reconfirm / no stale click / 无
timing stack / 不接 Fatigue / member·passive 无 reaction / Orochi·EvoZone `_fire_*_alone` /
邀请 cadence（`Timer(20/30)` / `timer_wait` / emoji）/ `room_check_can_fire`。
"""

import ast
import inspect
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp
from tasks.Component.GeneralInvite import general_invite as gi
from tasks.Component.GeneralInvite.general_invite import (
    GeneralInvite,
    GI_FIRE_MAX_TRIES,
    GI_FIRE_TIMEOUT,
    GI_FIRE_POST_CLICK_TIMEOUT,
)
from tasks.GameUi.assets import GameUiAssets
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets


def _src(obj) -> str:
    return inspect.getsource(obj)


def _body(func) -> str:
    """函数源码去掉首个 docstring —— 只扫代码体，避免命中 docstring 说明用词。"""
    parts = _src(func).split('"""')
    return parts[2] if len(parts) >= 3 else parts[0]


def _seq(values):
    """有限序列 → 跑完后无限重复最后一个值。"""
    values = list(values) or [False]
    for v in values:
        yield v
    while True:
        yield values[-1]


class _FakeTimer:
    """确定性 Timer 替身：单实例 reached() 超过 budget 次即到期。"""

    budget = 6

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


class _CF:
    """驱动 `GeneralInvite.click_fire` 的替身，按帧序列喂状态。"""

    def __init__(self, *, battle=None, matching=None, main=None, expl=None,
                 in_room=None, fire=None, fire_sea=None, with_is_in_battle=True):
        self.task = GeneralInvite.__new__(GeneralInvite)
        self.events = []
        self.task.screenshot = Mock(side_effect=lambda: self.events.append('screenshot'))
        if with_is_in_battle:
            b_it = _seq(battle if battle is not None else [False])
            self.task.is_in_battle = Mock(side_effect=lambda *a, **kw: next(b_it))
        room_it = _seq(in_room if in_room is not None else [True])
        self.task.is_in_room = Mock(side_effect=lambda *a, **kw: next(room_it))
        m_it = _seq(matching if matching is not None else [False])
        main_it = _seq(main if main is not None else [False])
        e_it = _seq(expl if expl is not None else [False])
        f_it = _seq(fire if fire is not None else [True])
        fs_it = _seq(fire_sea if fire_sea is not None else [False])

        def _appear(tgt, **kw):
            if tgt is self.task.I_MATCHING:
                return next(m_it)
            if tgt is GameUiAssets.I_CHECK_MAIN:
                return next(main_it)
            if tgt is GameUiAssets.I_CHECK_EXPLORATION:
                return next(e_it)
            if tgt is self.task.I_FIRE:
                return next(f_it)
            if tgt is self.task.I_FIRE_SEA:
                return next(fs_it)
            return False

        self.task.appear = Mock(side_effect=_appear)
        self.task.appear_then_click = Mock(
            side_effect=lambda *a, **kw: self.events.append(('click', a, kw)) or True)

    @property
    def clicks(self):
        return [e for e in self.events if isinstance(e, tuple) and e[0] == 'click']

    def run(self) -> str:
        return GeneralInvite.click_fire(self.task)


# =====================================================================================
# REACTION_FIRE profile + bounded 常量
# =====================================================================================

class ProfileAndConstantsTest(TestCase):
    def test_reaction_fire_unchanged(self):
        self.assertEqual(rp.REACTION_FIRE, (0.4, 0.8))
        self.assertEqual(rp.REACTION_PROFILES.get('FIRE'), (0.4, 0.8))
        self.assertIs(rp.REACTION_PROFILES_PROVISIONAL, True)

    def test_click_fire_imports_and_uses_reaction_fire(self):
        src = _src(gi)
        self.assertIn('from module.reaction_profile import REACTION_FIRE', src)
        self.assertIn('random_delay(*REACTION_FIRE)', _src(GeneralInvite.click_fire))

    def test_bounded_constants_present_and_finite(self):
        self.assertEqual(GI_FIRE_MAX_TRIES, 4)
        self.assertIsInstance(GI_FIRE_TIMEOUT, (int, float))
        self.assertGreater(GI_FIRE_TIMEOUT, 0)
        self.assertIsInstance(GI_FIRE_POST_CLICK_TIMEOUT, (int, float))
        self.assertGreater(GI_FIRE_POST_CLICK_TIMEOUT, 0)


# =====================================================================================
# 源码形态：bounded（无 while 1）、四态、无 timing stack
# =====================================================================================

class ClickFireSourceShapeTest(TestCase):
    def setUp(self):
        self.src = _src(GeneralInvite.click_fire)
        self.body = _body(GeneralInvite.click_fire)

    def test_no_unbounded_loop(self):
        self.assertNotIn('while 1', self.body)
        self.assertNotIn('while True', self.body)
        self.assertRegex(self.body, r'for attempt in range\(1,\s*GI_FIRE_MAX_TRIES \+ 1\)')
        self.assertIn('Timer(GI_FIRE_TIMEOUT)', self.body)

    def test_returns_str_states(self):
        tree = ast.parse(self.src.lstrip())
        fn = tree.body[0]
        returned = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant):
                returned.add(n.value.value)
        self.assertEqual(returned, {'battle', 'room_failed', 'timeout'})

    def test_four_way_state_helpers(self):
        cls_src = _src(GeneralInvite)
        for name in ('_battle_entry_positive', '_room_entry_failed',
                     '_classify_room_entry_state', '_wait_room_entry_state'):
            self.assertIn(f'def {name}(', cls_src)
        classify = _body(GeneralInvite._classify_room_entry_state)
        for st in ("'battle'", "'room_failed'", "'retryable'", "'unknown'"):
            self.assertIn(st, classify)

    def test_old_marker_not_success_in_source(self):
        # 不再有「not is_in_room(...) -> break（隐含 success）」的裸模式
        self.assertNotIn('if not self.is_in_room(False):\n            break', self.body)

    def test_timing_owner_no_stack(self):
        self.assertEqual(self.body.count('random_delay('), 1)
        self.assertIn('random_delay(*REACTION_FIRE)', self.body)
        self.assertEqual(self.body.count('sleep('), 1)
        self.assertIn('sleep(fire_delay)', self.body)
        for tok in ('confirm_delay', 'reaction_delay', 'CLICK_REACTION_DELAY'):
            self.assertNotIn(tok, self.body)
        self.assertIn('self.appear_then_click(target, interval=1, threshold=0.7)', self.body)

    def test_reaction_then_fresh_screenshot_then_reconfirm_order(self):
        i = self.body.index('random_delay(*REACTION_FIRE)')
        tail = self.body[i:]
        self.assertIn('sleep(fire_delay)', tail)
        j = tail.index('sleep(fire_delay)')
        after = tail[j:]
        self.assertIn('self.screenshot()', after)
        self.assertIn('self._classify_room_entry_state()', after)
        self.assertIn('self.appear(target, threshold=0.7)', after)

    def test_wait_state_helper_is_clickless(self):
        body = _body(GeneralInvite._wait_room_entry_state)
        self.assertIn("'timeout'", body)
        for tok in ('.click(', 'appear_then_click', 'random_delay', 'sleep('):
            self.assertNotIn(tok, body)

    def test_state_helpers_are_read_only(self):
        for name in ('_battle_entry_positive', '_room_entry_failed', '_classify_room_entry_state'):
            body = _body(getattr(GeneralInvite, name))
            for tok in ('screenshot', '.click(', 'appear_then_click', 'sleep(', 'random_delay', 'Timer('):
                self.assertNotIn(tok, body, f'{name}: {tok}')

    def test_room_failed_reuses_existing_markers_no_new_detector(self):
        body = _body(GeneralInvite._room_entry_failed)
        self.assertIn('self.I_MATCHING', body)
        self.assertIn('GameUiAssets.I_CHECK_MAIN', body)
        self.assertIn('GameUiAssets.I_CHECK_EXPLORATION', body)

    def test_battle_positive_prefers_is_in_battle_with_fallback(self):
        body = _body(GeneralInvite._battle_entry_positive)
        self.assertIn("getattr(self, 'is_in_battle', None)", body)
        # fallback 是 is_in_battle 的严格子集：只 I_BATTLE_INFO / I_PREPARE_HIGHLIGHT
        self.assertIn('GeneralBattleAssets.I_BATTLE_INFO', body)
        self.assertIn('GeneralBattleAssets.I_PREPARE_HIGHLIGHT', body)
        # 不再引入 is_in_battle 未采用的更宽 heuristic marker（I_EXIT）
        self.assertNotIn('I_EXIT', body)
        self.assertNotIn('I_FRIENDS', body)
        self.assertNotIn('I_WIN', body)
        self.assertNotIn('I_REWARD', body)

    def test_battle_positive_fallback_is_strict_subset_of_is_in_battle(self):
        # fallback 里的每个 marker 都必须出现在 GeneralBattle.is_in_battle() 源码里
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        fb = _body(GeneralInvite._battle_entry_positive)
        iib = inspect.getsource(GeneralBattle.is_in_battle)
        import re as _re
        for m in _re.findall(r'GeneralBattleAssets\.(I_\w+)', fb):
            self.assertIn(m, iib, f'fallback marker {m} 不在 is_in_battle()')


# =====================================================================================
# 行为：四态分类 + bounded
# =====================================================================================

class ClickFireFsmBehaviorTest(TestCase):
    def setUp(self):
        _FakeTimer.budget = 6
        patch.object(gi, 'Timer', _FakeTimer).start()
        patch.object(gi, 'sleep').start()
        self.m_delay = patch.object(gi, 'random_delay', return_value=0.6).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_FakeTimer, 'budget', 6))

    # ---- BATTLE ----
    def test_positive_battle_at_top_returns_battle_no_click(self):
        h = _CF(battle=[True], in_room=[True], fire=[True])
        self.assertEqual(h.run(), 'battle')
        h.task.appear_then_click.assert_not_called()

    def test_reaction_then_click_then_battle_returns_battle(self):
        # retryable → reaction → 仍 retryable → click → _wait: battle
        h = _CF(battle=[False, False, False, True], in_room=[True], fire=[True])
        self.assertEqual(h.run(), 'battle')
        self.assertEqual(len(h.clicks), 1)
        a, kw = h.clicks[0][1], h.clicks[0][2]
        self.assertIs(a[0], h.task.I_FIRE)
        self.assertEqual(kw, {'interval': 1, 'threshold': 0.7})

    # ---- 「不在房间」单独发生 != success（本轮最重要护栏）----
    def test_left_room_without_battle_marker_is_not_success(self):
        # 不在房间、无 battle marker、无 failure marker → 全程 UNKNOWN → bounded → 'timeout'
        h = _CF(battle=[False], in_room=[False], fire=[True])
        self.assertEqual(h.run(), 'timeout')
        h.task.appear_then_click.assert_not_called()

    # ---- TRANSITION_UNKNOWN → BATTLE ----
    def test_transition_unknown_then_battle_returns_battle_no_click(self):
        # frame1 UNKNOWN（不在房间/无 battle/无 failure）→ _wait poll → 出 battle
        h = _CF(battle=[False, False, True], in_room=[False], fire=[True])
        self.assertEqual(h.run(), 'battle')
        h.task.appear_then_click.assert_not_called()

    # ---- ROOM_FAILED ----
    def test_room_failed_courtyard_returns_room_failed_no_click(self):
        h = _CF(in_room=[True], main=[True], fire=[True])
        self.assertEqual(h.run(), 'room_failed')
        h.task.appear_then_click.assert_not_called()

    def test_room_failed_matching_returns_room_failed(self):
        h = _CF(in_room=[True], matching=[True], fire=[True])
        self.assertEqual(h.run(), 'room_failed')

    def test_room_failed_exploration_returns_room_failed(self):
        h = _CF(in_room=[True], expl=[True], fire=[True])
        self.assertEqual(h.run(), 'room_failed')

    # ---- RETRYABLE + per-attempt reaction ----
    def test_retryable_room_allows_next_attempt_reaction_per_attempt(self):
        # 一直 retryable、battle 迟迟不来 → 多次 attempt，每次独立采样 REACTION_FIRE
        h = _CF(battle=[False] * 8 + [True], in_room=[True], fire=[True])
        h.run()
        self.assertGreaterEqual(self.m_delay.call_count, 2)
        for c in self.m_delay.call_args_list:
            self.assertEqual(c.args, (0.4, 0.8))

    # ---- stale coordinate protection ----
    def test_button_gone_during_reaction_no_stale_click(self):
        # target 选中(fire#1=T) → reaction → 二次 appear(target)=F（仍在房间）→ 不 click
        h = _CF(battle=[False], in_room=[True], fire=[True, False])
        self.assertEqual(h.run(), 'timeout')
        h.task.appear_then_click.assert_not_called()

    def test_left_retryable_during_reaction_no_stale_click(self):
        # reaction 后（第 2 次 classify）变 room_failed → 立即失败、不点旧坐标
        h = _CF(battle=[False], in_room=[True], main=[False, True], fire=[True])
        self.assertEqual(h.run(), 'room_failed')
        h.task.appear_then_click.assert_not_called()

    # ---- bounded ----
    def test_bounded_by_max_tries_returns_timeout(self):
        h = _CF(battle=[False], in_room=[True], fire=[True])
        self.assertEqual(h.run(), 'timeout')
        self.assertLessEqual(h.task.appear_then_click.call_count, GI_FIRE_MAX_TRIES)

    def test_overall_timer_exits_immediately(self):
        _FakeTimer.budget = 0
        h = _CF(battle=[False], in_room=[True], fire=[True])
        self.assertEqual(h.run(), 'timeout')
        h.task.appear_then_click.assert_not_called()
        h.task.screenshot.assert_not_called()

    # ---- I_FIRE_SEA 变体 ----
    def test_fire_sea_variant_also_reaction_and_click(self):
        h = _CF(battle=[False, False, False, True], in_room=[True],
                fire=[False], fire_sea=[True])
        self.assertEqual(h.run(), 'battle')
        self.assertEqual(len(h.clicks), 1)
        self.assertIs(h.clicks[0][1][0], h.task.I_FIRE_SEA)

    # ---- _battle_entry_positive 兜底路径 ----
    def test_battle_positive_fallback_without_is_in_battle(self):
        t = GeneralInvite.__new__(GeneralInvite)
        # 无 is_in_battle → 兜底只看 I_BATTLE_INFO / I_PREPARE_HIGHLIGHT
        for marker in (GeneralBattleAssets.I_BATTLE_INFO, GeneralBattleAssets.I_PREPARE_HIGHLIGHT):
            t.appear = Mock(side_effect=lambda tgt, _m=marker, **kw: tgt is _m)
            self.assertTrue(GeneralInvite._battle_entry_positive(t))
        # I_EXIT 已从 fallback 移除：只有 I_EXIT 可见时 fallback 不再判 battle
        t.appear = Mock(side_effect=lambda tgt, **kw: tgt is GeneralBattleAssets.I_EXIT)
        self.assertFalse(GeneralInvite._battle_entry_positive(t))
        t.appear = Mock(return_value=False)
        self.assertFalse(GeneralInvite._battle_entry_positive(t))


# =====================================================================================
# caller guard：run_invite 只在 'battle' 才 True
# =====================================================================================

class RunInviteGuardTest(TestCase):
    def test_run_invite_only_true_on_battle(self):
        src = _src(GeneralInvite.run_invite)
        self.assertIn('fire_result = self.click_fire()', src)
        self.assertIn("if fire_result == 'battle':", src)
        # 找到 `if self.room_check_can_fire(config):` 块，里面 return True 只在 == 'battle' 分支
        i = src.index('if self.room_check_can_fire(config):')
        block = src[i:i + 500]
        self.assertIn("if fire_result == 'battle':\n                    return True", block)
        self.assertIn('return False', block)

    def test_run_invite_no_bare_return_true_after_click_fire(self):
        src = _src(GeneralInvite.run_invite)
        # 旧形态 `self.click_fire()\n ... return True` 无条件已删
        self.assertNotIn('self.click_fire()\n                return True', src)


class DirectCallerGuardTest(TestCase):
    def test_experience_gold_tako_guard_run_general_battle(self):
        for mod in ('tasks.ExperienceYoukai.script_task', 'tasks.GoldYoukai.script_task',
                    'tasks.Tako.script_task'):
            src = inspect.getsource(__import__(mod, fromlist=['x']))
            with self.subTest(mod=mod):
                self.assertIn("if self.click_fire() == 'battle':", src)
                # run_general_battle 不再无条件跟在 click_fire 后
                self.assertNotIn('self.click_fire()\n                    count += 1', src)
                self.assertNotIn('self.click_fire()\n                self.run_general_battle()', src)

    def test_hunt_guards_with_battle_entered_flag(self):
        src = inspect.getsource(__import__('tasks.Hunt.script_task', fromlist=['x']))
        self.assertIn("battle_entered = self.click_fire() == 'battle'", src)
        self.assertIn('if not battle_entered:', src)
        # run_general_battle 在 flag 之后
        i = src.index("battle_entered = self.click_fire() == 'battle'")
        j = src.index('self.run_general_battle(', i)
        self.assertIn('if not battle_entered:', src[i:j])


# =====================================================================================
# Action Owner：member / passive path 无 challenge reaction
# =====================================================================================

class ChallengeActionOwnerTest(TestCase):
    def test_passive_paths_no_click_fire_no_reaction(self):
        for fn in (GeneralInvite.wait_battle, GeneralInvite.check_then_accept,
                   GeneralInvite.check_and_invite, GeneralInvite.invite_again):
            src = _src(fn)
            self.assertNotIn('click_fire', src)
            self.assertNotIn('REACTION_FIRE', src)
            self.assertNotIn('random_delay(*REACTION_FIRE)', src)

    def test_wait_battle_room_markers_unchanged(self):
        # ROOM_FAILED 复用的 marker 与 wait_battle 一致（未改 wait_battle）
        src = _src(GeneralInvite.wait_battle)
        self.assertIn('GameUiAssets.I_CHECK_MAIN', src)
        self.assertIn('GameUiAssets.I_CHECK_EXPLORATION', src)


# =====================================================================================
# Orochi / EvoZone 兼容
# =====================================================================================

class OrochiEvoZoneCompatTest(TestCase):
    def test_run_alone_fire_fsm_unchanged_and_not_via_click_fire(self):
        from tasks.Orochi.script_task import ScriptTask as Orochi
        from tasks.EvoZone.script_task import ScriptTask as EvoZone
        for cls, fm in ((Orochi, '_fire_orochi_alone'), (EvoZone, '_fire_evozone_alone')):
            alone = _src(cls.run_alone)
            self.assertIn(f'if self.{fm}():', alone)
            self.assertNotIn('click_fire', alone)
            fire = _src(getattr(cls, fm))
            self.assertEqual(fire.count('random_delay('), 1)
            self.assertIn('random_delay(*REACTION_FIRE)', fire)
            self.assertNotIn('click_fire', fire)

    def test_leader_paths_reach_public_owner_not_own_reaction(self):
        from tasks.Orochi.script_task import ScriptTask as Orochi
        from tasks.EvoZone.script_task import ScriptTask as EvoZone
        for cls in (Orochi, EvoZone):
            src = _src(cls.run_leader)
            self.assertIn('self.run_invite(', src)
            self.assertNotIn('random_delay(*REACTION_FIRE)', src)
            self.assertNotIn('click_fire', src)

    def test_member_paths_have_no_challenge_reaction(self):
        from tasks.Orochi.script_task import ScriptTask as Orochi
        from tasks.EvoZone.script_task import ScriptTask as EvoZone
        for cls in (Orochi, EvoZone):
            src = _src(cls.run_member)
            self.assertNotIn('REACTION_FIRE', src)
            self.assertNotIn('click_fire', src)


# =====================================================================================
# Fatigue 不扩散
# =====================================================================================

class FatigueDoesNotSpreadToInviteTest(TestCase):
    def test_general_invite_module_has_no_fatigue(self):
        src = _src(gi)
        for tok in ('begin_fatigue_task', 'try_fatigue_break', 'FatigueManager', 'fatigue_manager'):
            self.assertNotIn(tok, src)

    def test_challenge_and_wait_paths_have_no_fatigue(self):
        for fn in (GeneralInvite.click_fire, GeneralInvite._classify_room_entry_state,
                   GeneralInvite._wait_room_entry_state, GeneralInvite.run_invite,
                   GeneralInvite.wait_battle, GeneralInvite.check_then_accept):
            body = _body(fn)
            self.assertNotIn('fatigue', body.lower())
            self.assertNotIn('begin_fatigue_task', body)
            self.assertNotIn('try_fatigue_break', body)


# =====================================================================================
# 11 个 consumer 继承 / 直接 caller 未被顺手改业务
# =====================================================================================

class ConsumerCompatibilityTest(TestCase):
    RUN_INVITE_TASKS = (
        'tasks.BondlingFairyland.script_task', 'tasks.EternitySea.script_task',
        'tasks.EvoZone.script_task', 'tasks.Exploration.script_task',
        'tasks.FallenSun.script_task', 'tasks.Orochi.script_task',
        'tasks.OtherWorldTwilight.script_task',
    )
    DIRECT_CLICK_FIRE_TASKS = (
        'tasks.ExperienceYoukai.script_task', 'tasks.GoldYoukai.script_task',
        'tasks.Hunt.script_task', 'tasks.Tako.script_task',
    )

    def test_run_invite_consumers_do_not_reimplement_or_override(self):
        # 不覆写公共 click_fire。（Orochi / EvoZone 的 `random_delay(*REACTION_FIRE)` 在
        # `_fire_*_alone` 单人 FSM 里，是 §4.53 合法用法，不在此断言。）
        for mod in self.RUN_INVITE_TASKS:
            src = inspect.getsource(__import__(mod, fromlist=['x']))
            with self.subTest(mod=mod):
                self.assertNotIn('def click_fire', src)

    def test_direct_callers_use_public_impl_and_only_guard_added(self):
        for mod in self.DIRECT_CLICK_FIRE_TASKS:
            src = inspect.getsource(__import__(mod, fromlist=['x']))
            with self.subTest(mod=mod):
                self.assertIn('self.click_fire()', src)
                self.assertNotIn('def click_fire', src)
                self.assertNotIn('random_delay(*REACTION_FIRE)', src)
                # 只加了 == 'battle' guard，没有引入 REACTION_FIRE / 新循环
                self.assertIn("self.click_fire() == 'battle'", src)

    def test_all_click_fire_consumers_have_general_battle_in_mro(self):
        # click_fire 内 _battle_entry_positive 优先用 is_in_battle —— 所有真实 consumer 必须有它
        import importlib
        for mod in self.RUN_INVITE_TASKS + self.DIRECT_CLICK_FIRE_TASKS:
            cls = importlib.import_module(mod).ScriptTask
            with self.subTest(mod=mod):
                self.assertTrue(callable(getattr(cls, 'is_in_battle', None)), mod)

    def test_mysteryshop_mixes_generalinvite_but_never_calls_click_fire(self):
        # MysteryShop 混入 GeneralInvite 但无 GeneralBattle、不调 click_fire / run_invite
        # —— fallback 收窄不影响它
        m = __import__('tasks.MysteryShop.script_task', fromlist=['x'])
        src = inspect.getsource(m)
        self.assertIn('GeneralInvite', src)
        self.assertNotIn('self.click_fire(', src)
        self.assertNotIn('self.run_invite(', src)
        cls = m.ScriptTask
        self.assertFalse(callable(getattr(cls, 'is_in_battle', None)))


# =====================================================================================
# I_EXIT 其它 consumer 不被误删（静态复核后最小收尾护栏）
# =====================================================================================

class IExitOtherConsumersPreservedTest(TestCase):
    def test_i_exit_asset_still_defined_once(self):
        from tasks.Component.GeneralBattle import assets as gb_assets
        src = inspect.getsource(gb_assets)
        self.assertIn('I_EXIT = RuleImage(', src)
        self.assertIn('gb_exit.png', src)

    def test_battle_entry_positive_no_longer_references_i_exit(self):
        self.assertNotIn('I_EXIT', _src(GeneralInvite._battle_entry_positive))

    def test_other_i_exit_consumers_unchanged(self):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        # exit_battle 仍以 I_EXIT 作为「可退出战斗页」判据 + 点击目标
        eb = inspect.getsource(GeneralBattle.exit_battle)
        self.assertIn('self.I_EXIT', eb)
        # check_then_accept 仍以 I_EXIT 判「被秒开」
        cta = _src(GeneralInvite.check_then_accept)
        self.assertIn('GeneralBattleAssets.I_EXIT', cta)
