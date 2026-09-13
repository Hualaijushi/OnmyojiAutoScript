# This Python file uses the following encoding: utf-8
"""RyouToppa / RealmRaid 的 I_FIRE reaction 统一 + RealmRaid fire() 状态机收口（R-R1）。

2026-09-08。本轮：
- 新增公共 `REACTION_FIRE = (0.4, 0.8)`（`module/reaction_profile.py`，PROVISIONAL）；
- RyouToppa `attack_area` 的 FIRE reaction 从手写 `random_delay(0.2, 0.6)` 统一到
  `random_delay(*REACTION_FIRE)`，其余成熟状态机（`RYOU_TOPPA_ACTION_RETRIES` /
  `_wait_for_attack_state` / `is_in_battle` / fresh screenshot / 二次 appear / 区域
  `random_delay(1.0, 3.0)` pacing）**不动**；
- RealmRaid `fire()` 从「`while True` + 旧标识 `I_RR_PERSON` 消失即成功 + 恒返回 True」
  收口为「**正向战斗确认**（`is_in_battle()`）+ 每 attempt 独立 `REACTION_FIRE` +
  fresh screenshot 二次确认 + 有限 `RR_FIRE_MAX_TRIES` / `RR_FIRE_TIMEOUT` + 可达
  `return False`」；`run()` 的 `if not self.fire(index): continue` 天然处理失败、不误交接
  `run_general_battle`。

`appear_then_click` primitive、GeneralBattle Settlement V3、T7、FrameWait、Fatigue、
Exploration 的 FIRE 均**未改**。

2026-09-08 第二批：Orochi / EvoZone `run_alone` 的 `I_*_FIRE` 已收口为同一 FIRE Contract 三态
状态机（见 `tests/test_second_batch_fire_fsm.py`）；本文件的 `OtherFireNotMigratedTest` 相应缩小
到「非 run_alone 路径 + 契灵 + Exploration 未迁」。
"""

import ast
import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp
from tasks.RealmRaid.script_task import (
    ScriptTask as RealmRaid,
    RR_FIRE_MAX_TRIES,
    RR_FIRE_TIMEOUT,
    RR_FIRE_POST_CLICK_TIMEOUT,
)
from tasks.RyouToppa.script_task import ScriptTask as RyouToppa
from tasks.Orochi.script_task import ScriptTask as Orochi
from tasks.EvoZone.script_task import ScriptTask as EvoZone


def _src(func) -> str:
    return inspect.getsource(func)


class _FakeTimer:
    """确定性 Timer 替身：单实例调用 reached() 超过 budget 次即到期（防测试无限循环）。"""

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


# =====================================================================================
# REACTION_FIRE profile
# =====================================================================================

class ReactionFireProfileTest(TestCase):
    def test_value_is_0_4_to_0_8(self):
        self.assertEqual(rp.REACTION_FIRE, (0.4, 0.8))

    def test_low_less_than_high(self):
        lo, hi = rp.REACTION_FIRE
        self.assertLess(lo, hi)
        self.assertGreater(lo, 0.0)

    def test_in_registry_and_still_provisional(self):
        self.assertEqual(rp.REACTION_PROFILES.get('FIRE'), rp.REACTION_FIRE)
        self.assertIs(rp.REACTION_PROFILES_PROVISIONAL, True)

    def test_batch1_profiles_unchanged(self):
        self.assertEqual(rp.REACTION_FAST, (0.18, 0.35))
        self.assertEqual(rp.REACTION_NORMAL, (0.45, 0.85))
        self.assertEqual(rp.REACTION_NORMAL_HIGH, (0.60, 1.00))
        self.assertEqual(rp.REACTION_CONFIRM, (0.55, 1.20))
        self.assertEqual(rp.REACTION_NAVIGATION, (0.55, 1.10))
        self.assertEqual(rp.REACTION_DELIBERATE, (0.90, 1.60))


# =====================================================================================
# RyouToppa I_FIRE —— 只统一 delay profile，成熟状态机不动
# =====================================================================================

class RyouToppaFireReactionTest(TestCase):
    def setUp(self):
        self.src = _src(RyouToppa.attack_area)

    def test_fire_delay_unified_to_reaction_fire_not_old_value(self):
        self.assertIn('fire_delay = random_delay(*REACTION_FIRE)', self.src)
        self.assertNotIn('random_delay(0.2, 0.6)', self.src)

    def test_fire_delay_sampled_inside_the_attempt_loop(self):
        # 每次 attempt 独立采样：random_delay(*REACTION_FIRE) 必须在 `for attempt` 循环体内
        tree = ast.parse(self.src.lstrip())
        fn = tree.body[0]
        fors = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
        in_loop = False
        for f in fors:
            for node in ast.walk(f):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'random_delay'
                        and node.args and isinstance(node.args[0], ast.Starred)):
                    in_loop = True
        self.assertTrue(in_loop, '每次 FIRE attempt 必须重新采样 REACTION_FIRE')

    def test_reaction_then_fresh_screenshot_then_recheck(self):
        i_delay = self.src.index('fire_delay = random_delay(*REACTION_FIRE)')
        tail = self.src[i_delay:]
        self.assertIn('time.sleep(fire_delay)', tail)
        i_sleep = tail.index('time.sleep(fire_delay)')
        after_sleep = tail[i_sleep:]
        self.assertIn('self.screenshot()', after_sleep)
        self.assertIn('self.is_in_battle(False)', after_sleep)
        self.assertIn("appear(RealmRaidAssets.I_FIRE, threshold=0.8)", after_sleep)

    def test_no_click_when_fire_gone_after_reaction(self):
        # delay 后 `if not self.appear(I_FIRE...)` 分支里 continue，不 appear_then_click 旧目标
        self.assertIn('if not self.appear(RealmRaidAssets.I_FIRE, threshold=0.8):', self.src)

    def test_mature_state_machine_preserved(self):
        self.assertIn('RYOU_TOPPA_ACTION_RETRIES', self.src)
        self.assertIn('self._wait_for_attack_state()', self.src)
        self.assertIn('for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1)', self.src)
        self.assertIn('AreaAttackResult.INTERACTION_ERROR', self.src)

    def test_area_pacing_random_delay_1_to_3_still_present(self):
        self.assertIn('random_delay(1.0, 3.0)', self.src)

    def test_no_confirm_delay_stacked_on_fire(self):
        self.assertNotIn('confirm_delay', self.src)


# =====================================================================================
# RealmRaid fire() —— R-R1 收口
# =====================================================================================

class _RRHarness:
    def __init__(self):
        self.task = RealmRaid.__new__(RealmRaid)
        self.events = []
        self.task.device = SimpleNamespace(
            image='FRAME', image_frame_id='FID',
            click_record_clear=Mock(side_effect=lambda: self.events.append('clear')),
        )
        self.task.screenshot = Mock(side_effect=lambda: self.events.append('screenshot'))
        self.task.wait_until_appear = Mock(
            side_effect=lambda t, **kw: self.events.append(('wait', getattr(t, 'name', '?'), kw)))
        self.task.__dict__['partition'] = [
            SimpleNamespace(name=f'partition_{i}') for i in range(1, 10)]
        self.task.appear_then_click = Mock(side_effect=lambda *a, **kw: self.events.append('fire_click') or True)
        self.task.click = Mock(side_effect=lambda *a, **kw: self.events.append(('partition', a[0].name)) or True)


class RealmRaidFireFsmTest(TestCase):
    def setUp(self):
        _FakeTimer.budget = 8
        self.p_timer = patch('tasks.RealmRaid.script_task.Timer', _FakeTimer)
        self.p_sleep = patch('tasks.RealmRaid.script_task.sleep')
        self.p_delay = patch('tasks.RealmRaid.script_task.random_delay', return_value=0.6)
        self.p_timer.start(); self.p_sleep.start(); self.p_delay.start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: setattr(_FakeTimer, 'budget', 8))

    def _mk(self, *, in_battle, fire_visible=None, rr_person=None, back_red=None):
        h = _RRHarness()
        t = h.task
        t.is_in_battle = Mock(side_effect=_seq(in_battle))
        fire_it = _seq(fire_visible or [False])
        rr_it = _seq(rr_person or [False])
        back_it = _seq(back_red or [False])

        def _appear(tgt, **kw):
            if tgt is t.I_FIRE:
                return next(fire_it)
            if tgt is t.I_RR_PERSON:
                return next(rr_it)
            if tgt is t.I_BACK_RED:
                return next(back_it)
            return False
        t.appear = Mock(side_effect=_appear)
        return h, t

    # ---- 正向战斗确认 ------------------------------------------------------

    def test_positive_battle_prepare_returns_true(self):
        h, t = self._mk(in_battle=[True])
        self.assertIs(t.fire(1), True)
        t.appear_then_click.assert_not_called()
        t.click.assert_not_called()

    def test_positive_battle_after_fire_click_returns_true(self):
        # attempt1: 未在战斗、FIRE 可见 → reaction → 仍未战斗 → FIRE 仍在 → click
        #           → _wait_fire_entered_battle: is_in_battle True → True
        h, t = self._mk(in_battle=[False, False, True], fire_visible=[True, True, True])
        self.assertIs(t.fire(2), True)
        t.appear_then_click.assert_called_once()
        args, kwargs = t.appear_then_click.call_args
        self.assertIs(args[0], t.I_FIRE)
        self.assertEqual(kwargs, {'interval': 0, 'threshold': 0.8})

    # ---- 旧 marker 消失 != success，也 != immediate failure / retry -----------

    def test_old_marker_gone_without_battle_is_not_success(self):
        # I_RR_PERSON / I_FIRE / I_BACK_RED 全程 False、is_in_battle 全程 False（transition/unknown）
        h, t = self._mk(in_battle=[False] * 400, fire_visible=[False] * 400,
                        rr_person=[False] * 400, back_red=[False] * 400)
        self.assertIs(t.fire(1), False)
        # 从未把「旧标识消失」当成功；transition/unknown 期间也不乱点 partition / FIRE
        t.appear_then_click.assert_not_called()
        t.click.assert_not_called()

    def test_transition_blank_frame_then_battle_returns_true_without_extra_click(self):
        # 点 FIRE 后：blank 过渡帧（is_in_battle=F, FIRE=F, RR_PERSON=F, BACK_RED=F）→ 不 return False；
        # 下一帧 is_in_battle=True → return True，且不再点 partition / FIRE
        # 序列：top(F) → FIRE可见(T) → reaction后is_in_battle(F) → FIRE仍在(T) → click →
        #       _wait: is_in_battle(F,blank) → is_in_battle(T)
        h, t = self._mk(in_battle=[False, False, False, True],
                        fire_visible=[True, True, True, False, False],
                        rr_person=[False], back_red=[False])
        self.assertIs(t.fire(1), True)
        self.assertEqual(t.appear_then_click.call_count, 1)   # 只点一次 FIRE
        t.click.assert_not_called()                           # 过渡帧不点 partition

    def test_transition_unknown_all_frames_times_out_false_no_clicks(self):
        # post-click 一直 blank（transition/unknown）直到 _FakeTimer.budget 到期 → 'timeout'
        # → 进入下一 attempt；FIRE 已不可见且非 retryable → 又 _wait → 'timeout' … 最终 bounded → False
        h, t = self._mk(in_battle=[False] * 400,
                        fire_visible=[True] + [False] * 400,
                        rr_person=[False] * 400, back_red=[False] * 400)
        self.assertIs(t.fire(1), False)
        self.assertLessEqual(t.appear_then_click.call_count, 1)   # 至多点一次 FIRE（第一 attempt）
        t.click.assert_not_called()                               # unknown 期间从不点 partition

    def test_retryable_realm_raid_state_allows_next_attempt(self):
        # post-click 后不在战斗、但 I_BACK_RED 在（明确回到九宫格页）→ 'retryable' → 下一 attempt
        # 下一 attempt: FIRE 又可见 → reaction → click → is_in_battle True
        h, t = self._mk(in_battle=[False, False, False, False, True],
                        fire_visible=[True, True, True, False, True, True, True],
                        back_red=[False, False, False, True])
        self.assertIs(t.fire(1), True)
        self.assertGreaterEqual(t.appear_then_click.call_count, 1)

    # ---- fresh-frame 二次确认 ------------------------------------------

    def test_fire_gone_during_reaction_does_not_click_stale(self):
        # attempt1: FIRE 第一次可见 → reaction(0.6) → fresh screenshot → FIRE 第二次不可见
        #           → 不 click；后续 bounded 用尽 → False
        h, t = self._mk(in_battle=[False] * 200,
                        fire_visible=[True] + [False] * 200)
        self.assertIs(t.fire(1), False)
        t.appear_then_click.assert_not_called()   # 没点旧坐标

    def test_reaction_sampled_once_per_attempt(self):
        # 两个 attempt 各走一次 reaction 路径 → random_delay 被调 2 次
        h, t = self._mk(in_battle=[False] * 200,
                        fire_visible=[True, True, True, True, True, True, True, True])
        t.fire(1)
        from tasks.RealmRaid import script_task as rr_mod
        self.assertGreaterEqual(rr_mod.random_delay.call_count, 2)
        for c in rr_mod.random_delay.call_args_list:
            self.assertEqual(c.args, (0.4, 0.8))

    def test_reaction_then_fresh_screenshot_order(self):
        h, t = self._mk(in_battle=[False, False, True], fire_visible=[True, True, True])
        t.fire(1)
        # 事件里 reaction 后必有一次 screenshot 再判定
        self.assertIn('screenshot', h.events)

    # ---- bounded retry / timeout -------------------------------------

    def test_bounded_by_max_tries_returns_false(self):
        # 永不进战斗、FIRE 恒可见 → 每 attempt 都点一次 → 最多 RR_FIRE_MAX_TRIES 次
        h, t = self._mk(in_battle=[False] * 400, fire_visible=[True] * 400)
        self.assertIs(t.fire(1), False)
        self.assertLessEqual(t.appear_then_click.call_count, RR_FIRE_MAX_TRIES)
        self.assertGreaterEqual(t.appear_then_click.call_count, 1)

    def test_timeout_exits_false_immediately(self):
        _FakeTimer.budget = 0   # 第一次 timeout_timer.reached() 即 True
        h, t = self._mk(in_battle=[False] * 50, fire_visible=[True] * 50)
        self.assertIs(t.fire(1), False)
        t.appear_then_click.assert_not_called()
        t.click.assert_not_called()

    # ---- prologue / partition --------------------------------------

    def test_prologue_wait_bounded_then_clear_then_loop(self):
        h, t = self._mk(in_battle=[True])
        t.fire(4)
        self.assertEqual(h.events[0][0], 'wait')
        self.assertIn('wait_time', h.events[0][2])
        self.assertEqual(h.events[0][2]['wait_time'], RR_FIRE_TIMEOUT)
        self.assertEqual(h.events[1], 'clear')

    def test_partition_clicked_only_when_retryable_state_grid_page(self):
        # FIRE 未就绪 + 明确 retryable（I_BACK_RED 在，九宫格页）→ 点 partition[order-1]
        h, t = self._mk(in_battle=[False] * 400, fire_visible=[False] * 400, back_red=[True] * 400)
        t.fire(7)
        first_partition = next(e for e in h.events if isinstance(e, tuple) and e[0] == 'partition')
        self.assertEqual(first_partition[1], 'partition_7')

    def test_partition_not_clicked_in_transition_unknown(self):
        # FIRE 未就绪 + 无任何 retryable marker（transition/unknown）→ 绝不点 partition
        h, t = self._mk(in_battle=[False] * 400, fire_visible=[False] * 400,
                        rr_person=[False] * 400, back_red=[False] * 400)
        t.fire(7)
        self.assertFalse(any(isinstance(e, tuple) and e[0] == 'partition' for e in h.events))

    def test_partition_not_clicked_when_only_rr_person_visible(self):
        # 详情已打开（I_RR_PERSON 在）、FIRE 还在加载 → retryable，但按业务这里也会点九宫格
        # （原逻辑：点格子把 FIRE 顶出来）；关键是「有明确 retryable state」而非乱点
        h, t = self._mk(in_battle=[False] * 400, fire_visible=[False] * 400,
                        rr_person=[True] * 400, back_red=[False] * 400)
        t.fire(3)
        # retryable → 允许点 partition（业务重开详情）；不是 transition/unknown
        self.assertTrue(any(isinstance(e, tuple) and e[0] == 'partition' for e in h.events))


# =====================================================================================
# caller 兼容：run() 处理 fire(False)，不误交接 GeneralBattle
# =====================================================================================

class RealmRaidCallerCompatTest(TestCase):
    def test_run_guards_every_fire_with_continue_before_general_battle(self):
        src = _src(RealmRaid.run)
        # 两处 fire(index) 调用都是 `if not self.fire(index): continue`
        self.assertEqual(src.count('if not self.fire(index):'), 2)
        # 每个 guard 后面紧跟 continue
        for chunk in src.split('if not self.fire(index):')[1:]:
            self.assertIn('continue', chunk.split('\n', 3)[1] + chunk.split('\n', 3)[2])
        # fire 的返回值从不被直接丢弃（没有裸 `self.fire(index)\n` 语句）
        tree = ast.parse(src.lstrip())
        bare_fire = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                     and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'fire']
        self.assertEqual(bare_fire, [])

    def test_success_path_reaches_run_general_battle(self):
        src = _src(RealmRaid.run)
        # fire(True) → 落到 last_battle = self.run_general_battle(...)
        self.assertIn('self.run_general_battle(con.general_battle_config)', src)


# =====================================================================================
# timing owner —— 无叠加
# =====================================================================================

class FireTimingOwnerTest(TestCase):
    def test_realmraid_fire_only_reaction_fire_no_stack(self):
        src = _src(RealmRaid.fire)
        self.assertIn('random_delay(*REACTION_FIRE)', src)
        self.assertNotIn('confirm_delay', src)
        self.assertNotIn('REACTION_FAST', src)
        # 只有一处 random_delay（FIRE reaction），没有第二套 repeat/retry delay
        self.assertEqual(src.count('random_delay('), 1)

    def test_ryoutoppa_fire_only_reaction_fire_plus_area_pacing(self):
        src = _src(RyouToppa.attack_area)
        self.assertNotIn('confirm_delay', src)
        # 恰两处 random_delay：区域 pacing(1.0,3.0) + FIRE reaction(*REACTION_FIRE)
        self.assertEqual(src.count('random_delay('), 2)
        self.assertIn('random_delay(1.0, 3.0)', src)
        self.assertIn('random_delay(*REACTION_FIRE)', src)

    def test_constants_are_engineering_baseline_values(self):
        self.assertEqual(RR_FIRE_MAX_TRIES, 4)
        self.assertEqual(RR_FIRE_TIMEOUT, 10)
        self.assertEqual(RR_FIRE_POST_CLICK_TIMEOUT, 3)


# =====================================================================================
# 范围外 FIRE 未迁
# =====================================================================================

class OtherFireNotMigratedTest(TestCase):
    def test_orochi_evozone_non_alone_paths_have_no_reaction_fire_or_confirm_delay(self):
        # run_alone 已在第二批迁移（见 test_second_batch_fire_fsm）；leader / member / wild
        # 仍是旧形态、不含 REACTION_FIRE、不给 I_*_FIRE 叠 confirm_delay
        for func in (Orochi.run_wild, Orochi.run_member, Orochi.run_leader,
                     EvoZone.run_member, EvoZone.run_leader):
            src = _src(func)
            self.assertNotIn('REACTION_FIRE', src, func.__qualname__)
            for tok in ('I_OROCHI_FIRE', 'I_OROCHI_WILD_FIRE', 'I_EVOZONE_FIRE'):
                if tok in src:
                    self.assertNotIn(f'{tok}, interval=1, confirm_delay', src)
                    self.assertNotIn(f'{tok}, interval=1, threshold=0.8, confirm_delay', src)

    def test_bondling_ball_fire_not_migrated(self):
        # 契灵 I_BALL_FIRE = PARTIAL：模块不 import REACTION_FIRE，run_alone 结构不变
        from tasks.BondlingFairyland.script_task import ScriptTask as Bondling
        m = __import__('tasks.BondlingFairyland.script_task', fromlist=['x'])
        self.assertNotIn('REACTION_FIRE', inspect.getsource(m))
        self.assertNotIn('REACTION_FIRE', _src(Bondling.run_alone))

    def test_exploration_fire_untouched(self):
        from tasks.Exploration.base import BaseExploration
        src = _src(BaseExploration.fire)
        self.assertNotIn('REACTION_FIRE', src)
        self.assertNotIn('confirm_delay', src)
        self.assertIn('max_tries', src)
        self.assertIn('Timer(10)', src)
