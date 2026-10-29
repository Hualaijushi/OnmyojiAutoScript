# This Python file uses the following encoding: utf-8
"""通用战败页的结算点击规则：明确识别到失败横幅 `I_FALSE` 后改点右侧 / 底部安全区。

背景：用户观察到寮突破失败后被点了「再次挑战」。核对（源码 + 日志）：寮突破没有任何代码调用个人突破的
`_fire_again()` / `I_FIRE_AGAIN`；通用结算的默认随机区 `C_RANDOM_DEFAULT`（742,430,362,230）整个包住
`I_FIRE_AGAIN.roi_front`（830,506,61,36），结算点击落在它上面就会点中。日志里寮突破 `random_default` 点击
约 3%（42/1,481 次）落进该矩形，全在胜利页；日志里没有寮突破失败页，没有复现用户当次事件，所以这里只验证
修复后的行为，不宣称证明了当次事件的唯一根因。用户随后确认所有使用通用战败页的任务失败页布局相同，
规则收敛到通用入口：不再有逐任务开关。

规则（`GeneralBattle._handle_result`）：
- 明确失败 = 失败横幅 `I_FALSE`（`context.is_win` 为假），不是「没识别到胜利」；同一帧只判一次，失败一定走
  通用 burst；改用 `_pick_save_region()`（80% 右侧 / 20% 底部）；会话里已有默认区旧锚点则重采坐标。
- 胜利、普通奖励页、没有胜负横幅的单次节流点击保持原规则；个人突破退四中间的 quick_exit 直接返回结果；
  六道 / 契灵 / 爬塔等专用结果处理不委托给通用结算，不受影响。

这些测试驱动真实的 `run_general_battle` / `_handle_result` / `_handle_reward`，只替换截图、页面识别、设备点击和
掷骰；区域选择的分支用 patch 掉 `random_int` 的 (1, 100) 掷骰来确定，不靠随机碰巧命中。离线模拟，不是真机验证。
"""

import copy
import inspect
import unittest
from itertools import chain, repeat
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.click_sampler import ClickSampler
from tasks.BondlingFairyland import script_task as bondling
from tasks.BondlingFairyland.config import BondlingMode
from tasks.Component.Costume.config import BattleType
from tasks.Component.Costume.costume_base import CostumeBase
from tasks.Component.CostumeBattle.assets import CostumeBattleAssets
from tasks.Component.GeneralBattle import general_battle as gb
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.EvoZone import script_task as evo
from tasks.Exploration import script_task as exploration
from tasks.HeroTest import script_task as herotest
from tasks.Orochi import script_task as orochi
from tasks.RealmRaid import script_task as raid
from tasks.RealmRaid.assets import RealmRaidAssets
from tasks.RyouToppa import script_task as ryou
from tasks.RyouToppa.script_task import AreaAttackResult, ScriptTask as RyouToppa
from tasks.SixRealms.moon_sea.base_moon_sea import BaseMoonSea

AGAIN = RealmRaidAssets.I_FIRE_AGAIN.roi_front            # 830,506,61,36
INSIDE_AGAIN = (860, 524)                                  # 按钮正中
DEFAULT = GeneralBattle.C_RANDOM_DEFAULT
RIGHT = GeneralBattle.C_RANDOM_SAVE_RIGHT
BOTTOM = GeneralBattle.C_RANDOM_SAVE_BOTTOM

_real_random_int = gb.random_int

# 走通用 `_handle_result` 的代表性任务（不是按继承关系推断，每个都驱动真实处理器）
GENERIC_TASKS = (
    GeneralBattle, RyouToppa, raid.ScriptTask, orochi.ScriptTask, herotest.ScriptTask,
    exploration.ScriptTask, evo.ScriptTask,
)


def _inside(point, roi):
    x, y = point
    rx, ry, rw, rh = roi
    return rx <= x < rx + rw and ry <= y < ry + rh


def _forced_samples(first_points):
    """默认区的采样先吐出指定的点（模拟锚点恰好落在按钮上），之后恢复真实采样；其它区域始终真实采样。"""
    real = ClickSampler.sample_region
    feed = chain(first_points, repeat(None))

    def sample(roi, target_name):
        if tuple(roi) != DEFAULT.roi_front:
            return real(roi, target_name)
        point = next(feed)
        return point if point is not None else real(roi, target_name)
    return sample


class _Rolls:
    """确定性的掷骰：区域选择 (1, 100) 固定为 `region_roll`，段预算固定 4，burst 固定 1 次（不触发中途观察）。"""

    def __init__(self, region_roll):
        self.region_roll = region_roll
        self.region_calls = 0

    def __call__(self, low, high):
        if (low, high) == (1, 100):
            self.region_calls += 1
            return self.region_roll
        if (low, high) == (1, 10):
            return 10          # 段预算 4
        if (low, high) == (1, 2):
            return 1           # burst 1 次：每个主循环帧恰好一次点击、一次页面识别
        return _real_random_int(low, high)


def _battle_task(cls, *, visible):
    """真实任务类（只绕过构造）+ 真实 run_general_battle 需要的最小外部边界。

    `visible(task)`：当前帧里「看得见」的识别资源（按对象身份），可读 `task._frame`（从 1 起）。
    """
    task = cls.__new__(cls)
    task._frame = 0
    task.current_count = 0
    task.config = SimpleNamespace(global_game=SimpleNamespace(battle=SimpleNamespace(battle_timeout=420)))
    task._battle_shared_state = {}
    task._get_battle_behavior_scopes = Mock(return_value={})
    task._build_timed_battle_inspections = Mock(return_value={})
    task._custom_pages_registered = True
    task.current_action_type = 'dice'            # 只有活动玩法的 BaseAct 会读，其它任务忽略
    task.conf = SimpleNamespace(herotest=SimpleNamespace(layer=None))   # 只有 HeroTest 的 _exit_matcher 会读
    task.device = SimpleNamespace(
        click=Mock(), click_record_clear=Mock(), stuck_record_add=Mock(), stuck_record_clear=Mock(),
        detect_record=set(), screenshot_interval_set=Mock(),
    )
    task.screenshot = Mock()
    task.appear = Mock(side_effect=lambda rule, **kw: any(rule is v for v in visible(task)))
    task.appear_then_click = Mock(return_value=False)
    task._sample_interval = Mock(return_value=0)
    task._next_settlement_click_interval = Mock(return_value=0)
    return task


def _settle(task, frames, *, page=gb.page_battle_result, region_roll=1, forced_points=(), config=None):
    """在结算页停留 `frames` 帧（每帧一次点击），然后进入准备页结束。返回 [(x, y, control_name)] 和掷骰器。"""
    def detect_page(*args, **kwargs):
        task._frame += 1
        return page if task._frame <= frames else gb.page_battle_prepare

    original_build_context = task._build_context

    def build_context(*a, **kw):
        ctx = original_build_context(*a, **kw)
        ctx.settlement_click_timer.reached = Mock(return_value=True)   # 不等真实时钟
        return ctx
    task._build_context = build_context
    rolls = _Rolls(region_roll)
    with patch.object(gb.GameUi, 'detect_page_in', side_effect=detect_page), \
         patch.object(gb, 'random_int', side_effect=rolls), \
         patch.object(ClickSampler, 'sample_region', side_effect=_forced_samples(list(forced_points))):
        task.run_general_battle(config=config or gb.GeneralBattleConfig())
    clicks = [(c.kwargs['x'], c.kwargs['y'], c.kwargs['control_name']) for c in task.device.click.call_args_list]
    return clicks, rolls


def _failure_page(task):
    return (task.I_FALSE, RealmRaidAssets.I_FIRE_AGAIN)         # 失败横幅 + 突破失败页的「再次挑战」按钮


def _handler_context(**kw):
    base = dict(reward_no_battle_ts=1, is_win=True, last_page=gb.page_battle_result,
                settlement_session_active=False, settlement_region_name=None, settlement_anchor=None)
    base.update(kw)
    return SimpleNamespace(**base)


class GenericFailureSettlementTest(unittest.TestCase):
    def test_every_generic_task_clicks_right_or_bottom_on_a_failure_page(self):
        for cls in GENERIC_TASKS:
            for roll, roi, name in ((1, RIGHT.roi_front, 'random_save_right'),
                                    (100, BOTTOM.roi_front, 'random_save_bottom')):
                with self.subTest(task=cls.__module__, roll=roll):
                    task = _battle_task(cls, visible=_failure_page)
                    clicks, rolls = _settle(task, 6, region_roll=roll, forced_points=[INSIDE_AGAIN] * 3)
                    self.assertEqual(len(clicks), 6)
                    for x, y, control in clicks:
                        self.assertTrue(_inside((x, y), roi), (x, y))
                        self.assertEqual(control, name)
                        self.assertFalse(_inside((x, y), AGAIN))
                    self.assertEqual(rolls.region_calls, 1)                # 一个会话只选一次区域，不是每帧重掷

    def test_the_80_20_boundary_is_decided_by_the_roll_through_the_real_handler(self):
        for roll, name in ((1, 'random_save_right'), (80, 'random_save_right'),
                           (81, 'random_save_bottom'), (100, 'random_save_bottom')):
            task = _battle_task(GeneralBattle, visible=_failure_page)
            clicks, _ = _settle(task, 2, region_roll=roll)
            self.assertEqual({c for *_, c in clicks}, {name}, roll)

    def test_stale_default_region_anchor_is_replaced_and_never_reused_on_the_failure_page(self):
        # 前 3 帧只识别到胜利类横幅（会话在默认区建立了锚点），第 4 帧起明确识别到失败横幅
        for cls in (GeneralBattle, RyouToppa, raid.ScriptTask):
            task = _battle_task(cls, visible=lambda t: (t.I_DE_WIN,) if t._frame <= 3 else _failure_page(t))
            clicks, _ = _settle(task, 8, region_roll=100, forced_points=[INSIDE_AGAIN])
            before, after = clicks[:3], clicks[3:]
            self.assertEqual([(x, y) for x, y, _ in before], [INSIDE_AGAIN] * 3)      # 旧锚点在默认区、在按钮上
            self.assertEqual({name for *_, name in before}, {'random_default'})
            self.assertTrue(after)
            for x, y, name in after:
                self.assertNotEqual((x, y), INSIDE_AGAIN)                             # 不能继续用旧坐标
                self.assertTrue(_inside((x, y), BOTTOM.roi_front), (x, y))
                self.assertEqual(name, 'random_save_bottom')

    def test_multi_frame_failure_keeps_the_session_budget_and_safety_cap(self):
        # 失败持续 12 帧：沿用同一个会话（一个锚点、段预算 4 续段、总点击不超过安全帽 9），不另写循环
        task = _battle_task(GeneralBattle, visible=_failure_page)
        clicks, rolls = _settle(task, 12, region_roll=1)
        self.assertEqual(len(clicks), GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS)
        self.assertEqual(len({(x, y) for x, y, _ in clicks}), 1)
        self.assertEqual(rolls.region_calls, 1)

    def test_rebase_helper_only_acts_on_an_active_session_with_a_non_save_anchor(self):
        task = GeneralBattle.__new__(GeneralBattle)

        def context(**kw):
            base = dict(settlement_session_active=True, settlement_region_name='random_default',
                        settlement_anchor=INSIDE_AGAIN)
            base.update(kw)
            return SimpleNamespace(**base)

        stale = context()
        with patch.object(gb, 'random_int', return_value=1), \
             patch.object(ClickSampler, 'sample_region', return_value=(1200, 300)) as sampler:
            task._rebase_anchor_for_failure(stale)
        self.assertEqual((stale.settlement_anchor, stale.settlement_region_name), ((1200, 300), 'random_save_right'))
        sampler.assert_called_once()
        for already in (context(settlement_region_name='random_save_right', settlement_anchor=(1200, 300)),
                        context(settlement_region_name='random_save_bottom', settlement_anchor=(900, 650)),
                        context(settlement_session_active=False, settlement_anchor=None,
                                settlement_region_name=None)):
            snapshot = (already.settlement_anchor, already.settlement_region_name)
            with patch.object(ClickSampler, 'sample_region') as sampler:
                task._rebase_anchor_for_failure(already)
            self.assertEqual((already.settlement_anchor, already.settlement_region_name), snapshot)
            sampler.assert_not_called()

    def test_failure_does_not_borrow_the_reward_region_decision(self):
        # 失败页上即便同时看得见奖励宝袋标志，也不能走 `_select_reward_region`（它会返回默认区）
        task = _battle_task(GeneralBattle, visible=lambda t: _failure_page(t) + (t.I_GET_BATTLE_REWARD,))
        clicks, _ = _settle(task, 4, region_roll=1)
        self.assertEqual({name for *_, name in clicks}, {'random_save_right'})

    def test_confirmed_failure_always_takes_the_generic_burst_even_if_the_generic_check_disagrees(self):
        # `_is_generic_result_context` 另按资产阈值判一次；已确认失败的帧不能因为它不一致而落回单次节流默认点击
        task = _battle_task(GeneralBattle, visible=_failure_page)
        task._is_generic_result_context = Mock(return_value=False)
        task._settlement_click = Mock(wraps=task._settlement_click)
        clicks, _ = _settle(task, 4, region_roll=1)
        task._settlement_click.assert_not_called()
        self.assertEqual({name for *_, name in clicks}, {'random_save_right'})

    def test_region_choice_keeps_the_existing_80_20_split(self):
        task = GeneralBattle.__new__(GeneralBattle)
        for roll, expected in ((1, RIGHT), (80, RIGHT), (81, BOTTOM), (100, BOTTOM)):
            with patch.object(gb, 'random_int', return_value=roll):
                self.assertIs(task._pick_save_region(), expected, roll)

    def test_no_per_task_switch_or_old_avoid_scheme_remains(self):
        for owner in (GeneralBattle, RyouToppa):
            for name in ('SETTLEMENT_FAILURE_USES_SAVE_REGIONS', '_settlement_avoid_rois', '_sample_settlement_anchor',
                         '_point_in_any_roi', '_push_point_out_of_rois', 'SETTLEMENT_AVOID_MAX_RESAMPLE',
                         'SETTLEMENT_AVOID_MARGIN'):
                self.assertFalse(hasattr(owner, name), name)
        self.assertNotIn('SETTLEMENT_FAILURE', inspect.getsource(ryou))


class VictoryAndOtherPagesKeepTheOriginalRulesTest(unittest.TestCase):
    def test_win_settlement_stays_in_the_default_region_and_never_rolls_a_region(self):
        for cls in (GeneralBattle, RyouToppa, raid.ScriptTask, orochi.ScriptTask):
            for banner in (lambda t: (t.I_WIN,), lambda t: (t.I_DE_WIN,)):
                with self.subTest(task=cls.__module__):
                    task = _battle_task(cls, visible=banner)
                    clicks, rolls = _settle(task, 6, region_roll=100, forced_points=[INSIDE_AGAIN])
                    self.assertEqual(len(clicks), 6)
                    for x, y, name in clicks:
                        self.assertTrue(_inside((x, y), DEFAULT.roi_front))
                        self.assertEqual(name, 'random_default')
                    self.assertEqual(clicks[0][:2], INSIDE_AGAIN)          # 锚点沿用原采样，没有被挪走
                    self.assertEqual(rolls.region_calls, 0)                # 胜利不参与右侧 / 底部选择

    def test_unrecognised_result_page_is_not_treated_as_failure(self):
        # 没有识别到胜利也没有识别到失败：不能当失败；走原来的单次节流点击，区域仍是默认区
        for cls in (GeneralBattle, RyouToppa, raid.ScriptTask):
            task = _battle_task(cls, visible=lambda t: ())
            task._settlement_click = Mock(wraps=task._settlement_click)
            clicks, rolls = _settle(task, 6, region_roll=100)
            self.assertTrue(clicks)
            self.assertTrue(task._settlement_click.called)
            self.assertEqual({name for *_, name in clicks}, {'random_default'})
            self.assertEqual(rolls.region_calls, 0)

    def test_reward_page_rules_are_unchanged(self):
        # 有奖励宝袋标志 → 默认区；没有 → 80% 右侧 / 20% 底部（原 `_select_reward_region`）
        for cls in (GeneralBattle, RyouToppa, raid.ScriptTask):
            with_marker = _battle_task(cls, visible=lambda t: (t.I_GET_BATTLE_REWARD,))
            clicks, rolls = _settle(with_marker, 4, page=gb.page_reward, region_roll=100)
            self.assertEqual({name for *_, name in clicks}, {'random_default'})
            self.assertEqual(rolls.region_calls, 0)
            for roll, roi, name in ((1, RIGHT.roi_front, 'random_save_right'),
                                    (100, BOTTOM.roi_front, 'random_save_bottom')):
                bare = _battle_task(cls, visible=lambda t: ())
                clicks, _ = _settle(bare, 4, page=gb.page_reward, region_roll=roll)
                self.assertEqual({n for *_, n in clicks}, {name})
                self.assertTrue(all(_inside((x, y), roi) for x, y, _ in clicks))

    def test_select_reward_region_matches_the_original_decision_tree(self):
        task = GeneralBattle.__new__(GeneralBattle)
        task.appear = Mock(return_value=True)
        self.assertIs(task._select_reward_region(), DEFAULT)
        task.appear = Mock(return_value=False)
        with patch.object(gb, 'random_int', return_value=80) as roll:
            self.assertIs(task._select_reward_region(), RIGHT)
        roll.assert_called_once_with(1, 100)
        with patch.object(gb, 'random_int', return_value=81):
            self.assertIs(task._select_reward_region(), BOTTOM)


class PersonalRaidTest(unittest.TestCase):
    def test_ordinary_failure_and_exit_four_final_battle_use_the_failure_rule(self):
        # 普通战斗失败和退四最后一战（`run()` 里 is_final 用的是用户的完整 general_battle_config）都走完整结算
        task = _battle_task(raid.ScriptTask, visible=_failure_page)
        clicks, _ = _settle(task, 4, region_roll=100, config=gb.GeneralBattleConfig())
        self.assertEqual({name for *_, name in clicks}, {'random_save_bottom'})

    def test_exit_four_final_battle_uses_the_full_config_and_the_middle_ones_use_quick_exit(self):
        source = inspect.getsource(raid.ScriptTask.run)
        self.assertIn('cfg = con.general_battle_config if is_final else '
                      'self.build_quick_exit_config(con.general_battle_config)', source)
        quick = raid.ScriptTask.__new__(raid.ScriptTask).build_quick_exit_config(gb.GeneralBattleConfig())
        self.assertTrue(quick.quick_exit)
        self.assertFalse(gb.GeneralBattleConfig().quick_exit)

    def test_quick_exit_result_returns_directly_without_any_settlement_click(self):
        task = _battle_task(raid.ScriptTask, visible=_failure_page)
        task._pick_save_region = Mock()
        quick = raid.ScriptTask.__new__(raid.ScriptTask).build_quick_exit_config(gb.GeneralBattleConfig())
        context = _handler_context()
        self.assertEqual(task._handle_result(context, quick), BattleAction.EXIT_LOSE)
        self.assertFalse(context.is_win)
        task.device.click.assert_not_called()
        task._pick_save_region.assert_not_called()
        # 整场 run_general_battle（quick_exit 配置）同样直接得到失败结果，不点任何结算坐标
        full = _battle_task(raid.ScriptTask, visible=_failure_page)
        clicks, _ = _settle(full, 3, config=quick)
        self.assertEqual(clicks, [])

    def test_fire_again_and_confirm_popup_flow_is_untouched_by_the_settlement_rule(self):
        source = inspect.getsource(raid.ScriptTask._fire_again)
        for needle in ('I_FIRE_AGAIN', 'I_FRESH_ENSURE', '_battle_allowed', '_wait_again_entered_battle'):
            self.assertIn(needle, source)
        # 失败页上的再次挑战 / 确认弹窗由 `_fire_again` 按资产点击；通用结算只点安全区坐标
        task = _battle_task(raid.ScriptTask, visible=_failure_page)
        clicks, _ = _settle(task, 4, region_roll=1)
        clicked_assets = [c.args[0] for c in task.appear_then_click.call_args_list if c.args]
        self.assertNotIn(RealmRaidAssets.I_FIRE_AGAIN, clicked_assets)
        self.assertTrue(all(_inside((x, y), RIGHT.roi_front) for x, y, _ in clicks))


class SkinTemplateTest(unittest.TestCase):
    def test_skin_failure_template_goes_through_the_same_rule(self):
        # 皮肤适配（`CostumeBase.check_costume_battle`）在原地替换 `I_FALSE` 资产对象的模板 / ROI / 阈值，
        # 通用结算读的仍是 `self.I_FALSE`。在一个副本上跑真实映射，再用它驱动真实处理器。
        for battle_type, skin in ((BattleType.COSTUME_BATTLE_8, CostumeBattleAssets.I_FALSE_8),
                                  (BattleType.COSTUME_BATTLE_12, CostumeBattleAssets.I_FALSE_12),
                                  (BattleType.COSTUME_BATTLE_13, CostumeBattleAssets.I_FALSE_13),
                                  (BattleType.COSTUME_BATTLE_14, CostumeBattleAssets.I_FALSE_14)):
            with self.subTest(theme=battle_type):
                probe = type('SkinProbe', (CostumeBase,), {})()
                probe.I_FALSE = copy.copy(GeneralBattleAssets.I_FALSE)
                default_file = probe.I_FALSE.file
                probe.check_costume_battle(battle_type)
                mapped = probe.I_FALSE
                self.assertEqual(mapped.file, skin.file)                      # 模板确实换成了皮肤的
                self.assertNotEqual(mapped.file, default_file)
                self.assertEqual(mapped.roi_front, skin.roi_front)
                self.assertEqual(mapped.threshold, skin.threshold)

                task = _battle_task(GeneralBattle, visible=lambda t: (t.I_FALSE,))
                task.I_FALSE = mapped                                          # 只有皮肤模板「看得见」
                self.assertIsNot(task.I_FALSE, GeneralBattleAssets.I_FALSE)
                clicks, _ = _settle(task, 4, region_roll=100)
                self.assertEqual({name for *_, name in clicks}, {'random_save_bottom'})
                called_with = [c.args[0] for c in task.appear.call_args_list if c.args]
                self.assertIn(mapped, called_with)                            # 判定读的就是映射后的对象
                self.assertTrue(all(c.kwargs.get('threshold') == 0.8 for c in task.appear.call_args_list
                                    if c.args and c.args[0] is mapped and 'threshold' in c.kwargs))

    def test_skin_thresholds_match_the_handler_threshold(self):
        # 处理器按 0.8 判失败；当前所有皮肤失败模板的阈值也是 0.8，不会出现页面识别通过、处理器却判成胜利
        for skin in (CostumeBattleAssets.I_FALSE_8, CostumeBattleAssets.I_FALSE_12,
                     CostumeBattleAssets.I_FALSE_13, CostumeBattleAssets.I_FALSE_14):
            self.assertEqual(skin.threshold, 0.8)
        self.assertEqual(GeneralBattleAssets.I_FALSE.threshold, 0.8)


class SpecialFailureHandlersAreNotRerouted(unittest.TestCase):
    def test_six_realms_moon_sea_keeps_its_own_failure_handling(self):
        task = _battle_task(BaseMoonSea, visible=lambda t: (t.I_FALSE,))
        task._pick_save_region = Mock()
        task.click = Mock()
        context = _handler_context()
        self.assertEqual(task._handle_result(context, gb.GeneralBattleConfig()), BattleAction.CONTINUE)
        task._pick_save_region.assert_not_called()
        task.device.click.assert_not_called()                                 # 没有通用结算点击
        # 放弃按钮可见时按它自己的流程点放弃
        giveup = _battle_task(BaseMoonSea, visible=lambda t: (t.I_FALSE, t.I_BOSS_BATTLE_GIVEUP))
        giveup.click = Mock()
        giveup._pick_save_region = Mock()
        context = _handler_context()
        giveup._handle_result(context, gb.GeneralBattleConfig())
        self.assertFalse(context.is_win)
        self.assertIs(giveup.click.call_args.args[0], giveup.I_BOSS_BATTLE_GIVEUP)
        giveup._pick_save_region.assert_not_called()

    def test_bondling_keeps_its_own_result_handling(self):
        task = _battle_task(bondling.ScriptTask, visible=lambda t: (t.I_FALSE,))
        task.config = SimpleNamespace(bondling_fairyland=SimpleNamespace(
            bondling_config=SimpleNamespace(bondling_mode=BondlingMode.MODE1)))
        task._pick_save_region = Mock()
        task.click = Mock()
        self.assertEqual(task._handle_result(_handler_context(), gb.GeneralBattleConfig()), BattleAction.CONTINUE)
        task._pick_save_region.assert_not_called()
        task.device.click.assert_not_called()
        task.click.assert_called_once()                                       # 自己的 random_click 兜底

    def test_activity_climb_single_click_settlement_is_not_rerouted(self):
        from tasks.ActivityShikigami.activities.normal import NormalClimbAct
        from tasks.ActivityShikigami.base_act import BaseAct
        probe = type('ClimbProbe', (NormalClimbAct, BaseAct), {})
        task = _battle_task(probe, visible=lambda t: (t.I_FALSE,))
        task._climb_owns_settlement_single_click = True
        task._activity_settlement_single_click = Mock()
        task._pick_save_region = Mock()
        self.assertEqual(task._handle_result(_handler_context(), gb.GeneralBattleConfig()), BattleAction.CONTINUE)
        task._activity_settlement_single_click.assert_called_once()
        task._pick_save_region.assert_not_called()
        task.device.click.assert_not_called()


class RyouToppaKeepsItsOwnFailureFlowTest(unittest.TestCase):
    def test_task_has_no_personal_raid_fire_again_entry(self):
        self.assertFalse(hasattr(RyouToppa, '_fire_again'))
        self.assertFalse(hasattr(RyouToppa, '_wait_again_entered_battle'))
        source = inspect.getsource(ryou)
        self.assertNotIn('_fire_again', source)
        self.assertNotIn('appear_then_click(RealmRaidAssets.I_FIRE_AGAIN', source)

    def test_failed_battle_still_ends_through_the_task_own_failure_path(self):
        task = RyouToppa.__new__(RyouToppa)
        task.config = SimpleNamespace(ryou_toppa=SimpleNamespace(general_battle_config=gb.GeneralBattleConfig()))
        task.run_general_battle = Mock(return_value=False)              # 失败结算收尾
        task._wait_for_ryou_toppa_page = Mock(return_value=True)
        task.screenshot = Mock()
        task._area_has_failure_mark = Mock(return_value=True)
        task._area_content_recognizable = Mock(return_value=True)
        task.appear_then_click = Mock()
        task.click = Mock()
        self.assertEqual(task._finish_area_battle(0), AreaAttackResult.FAILED_MARKED)   # 照旧交给寮突破自己的失败策略
        task.appear_then_click.assert_not_called()
        task.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
