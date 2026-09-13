# This Python file uses the following encoding: utf-8
"""第一批业务 Reaction Timing / `confirm_delay` 迁移的回归护栏（2026-09-08）。

背景：把 RealmRaid / Orochi / EvoZone / RyouToppa / Exploration 里「识别到稳定 Point
Target → 立即点击」的一批调用，正式改成经 `BaseTask.appear_then_click(..., confirm_delay=)`
的「识别 → reaction delay → fresh screenshot → 二次确认 → 重新 coord → click」。

复用现有 primitive（`appear_then_click` 本体行为已由 `tests/test_base_task_confirm_click.py`
锁定，本轮**未改** primitive）。本文件只锁：
- 公共 reaction profile 常量（`module/reaction_profile.py`）的具体值与 provisional 身份；
- 每个迁移调用点确实带上了正确的 `confirm_delay=REACTION_*`；
- 明确排除项（各任务的 `*_FIRE` / RealmRaid `fire()` / GeneralBattle Settlement /
  `I_PREPARE_HIGHLIGHT` / 瞬态弹窗 / 动态 / polling / OCR）**没有**被顺手加 `confirm_delay`；
- 没有把 reaction 叠在已有同语义 timing（RyouToppa `random_delay(0.2,0.6)` 手搓 confirm /
  `random_delay(1.0,3.0)` 区域 pacing、GeneralBattle `prepare_click_timer` /
  `settlement_click_timer`）之上。

见 `docs/DECISIONS.md` D001 补记、`docs/AI_CONTEXT.md`、`docs/DEVELOP_LOG.md` 2026-09-08。
"""

import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.RealmRaid.script_task import ScriptTask as RealmRaid
from tasks.Orochi.script_task import ScriptTask as Orochi
from tasks.EvoZone.script_task import ScriptTask as EvoZone
from tasks.RyouToppa.script_task import ScriptTask as RyouToppa
from tasks.Exploration.base import BaseExploration
from tasks.Exploration.script_task import ScriptTask as Exploration


def _src(func) -> str:
    return inspect.getsource(func)


class ReactionProfileConstantsTest(TestCase):
    def test_exact_values(self):
        self.assertEqual(rp.REACTION_FAST, (0.18, 0.35))
        self.assertEqual(rp.REACTION_NORMAL, (0.45, 0.85))
        self.assertEqual(rp.REACTION_NORMAL_HIGH, (0.60, 1.00))
        self.assertEqual(rp.REACTION_CONFIRM, (0.55, 1.20))
        self.assertEqual(rp.REACTION_NAVIGATION, (0.55, 1.10))
        self.assertEqual(rp.REACTION_DELIBERATE, (0.90, 1.60))

    def test_all_are_ascending_two_tuples(self):
        for name, value in rp.REACTION_PROFILES.items():
            self.assertIsInstance(value, tuple, name)
            self.assertEqual(len(value), 2, name)
            lo, hi = value
            self.assertGreater(lo, 0.0, name)
            self.assertLess(lo, hi, name)

    def test_registry_matches_named_constants(self):
        self.assertEqual(rp.REACTION_PROFILES, {
            'FAST': rp.REACTION_FAST,
            'NORMAL': rp.REACTION_NORMAL,
            'NORMAL_HIGH': rp.REACTION_NORMAL_HIGH,
            'CONFIRM': rp.REACTION_CONFIRM,
            'NAVIGATION': rp.REACTION_NAVIGATION,
            'DELIBERATE': rp.REACTION_DELIBERATE,
            'FIRE': rp.REACTION_FIRE,
        })

    def test_marked_provisional(self):
        self.assertIs(rp.REACTION_PROFILES_PROVISIONAL, True)

    def test_module_has_no_logic(self):
        # 只看模块 docstring 之后的代码正文，不误伤 docstring 里对 sleep 语义的说明
        body = inspect.getsource(rp).split('"""', 2)[-1]
        for token in ('def ', 'sleep(', 'random_delay', 'import time', 'class '):
            self.assertNotIn(token, body, token)
        # 不依赖 task / device / config
        self.assertNotIn('import tasks', body)
        self.assertNotIn('from tasks', body)
        self.assertNotIn('module.device', body)


class RealmRaidReactionTest(TestCase):
    def test_ensure_lock_uses_fast_on_all_four_toggles(self):
        src = _src(RealmRaid.ensure_lock)
        for tgt in ('I_UNLOCK', 'I_UNLOCK_2', 'I_LOCK', 'I_LOCK_2'):
            self.assertIn(
                f'appear_then_click(self.{tgt}, interval=1, confirm_delay=REACTION_FAST)', src, tgt)

    def test_check_refresh_fresh_normal_ensure_confirm(self):
        src = _src(RealmRaid.check_refresh)
        self.assertIn('appear_then_click(self.I_FRESH, interval=1, confirm_delay=REACTION_NORMAL)', src)
        self.assertIn('appear_then_click(self.I_FRESH_ENSURE, interval=1, confirm_delay=REACTION_CONFIRM)', src)

    def test_fire_and_fire_again_confirm_timing_owners_are_separate(self):
        fire_src = _src(RealmRaid.fire)
        again_src = _src(RealmRaid._fire_again)
        self.assertNotIn('confirm_delay', fire_src)
        self.assertIn('random_delay(*REACTION_FIRE)', again_src)
        self.assertIn('I_FRESH_ENSURE, interval=2,\n                                      confirm_delay=RR_AGAIN_CONFIRM_DELAY)', again_src)
        self.assertNotIn('I_FIRE_AGAIN, interval=0, threshold=0.8, confirm_delay', again_src)

    def test_frog_and_soul_raid_untouched(self):
        run_src = _src(RealmRaid.run)
        self.assertIn('appear_then_click(self.I_FROG_RAID, interval=1)', run_src)
        self.assertNotIn('I_FROG_RAID, interval=1, confirm_delay', run_src)
        self.assertNotIn('confirm_delay', _src(RealmRaid.reward_detect_click))


class OrochiReactionTest(TestCase):
    def test_check_lock_calls_pass_fast(self):
        for func in (Orochi.run_leader, Orochi.run_alone, Orochi.run_wild):
            src = _src(func)
            if 'check_lock(' in src:
                self.assertIn('confirm_delay=REACTION_FAST', src, func.__name__)

    def test_form_team_uses_normal_in_leader_and_wild(self):
        for func in (Orochi.run_leader, Orochi.run_wild):
            self.assertIn(
                'appear_then_click(self.I_FORM_TEAM, interval=1, confirm_delay=REACTION_NORMAL)',
                _src(func), func.__name__)

    def test_orochi_fire_targets_have_no_confirm_delay(self):
        for func in (Orochi.run_alone, Orochi.run_member, Orochi.run_wild):
            src = _src(func)
            for token in ('I_OROCHI_FIRE', 'I_OROCHI_WILD_FIRE', 'I_PET_PRESENT', 'I_GB_CLOSE_RED'):
                if token in src:
                    self.assertNotIn(f'{token}, interval=1, confirm_delay', src, token)
        self.assertNotIn('confirm_delay', _src(Orochi.check_layer))
        self.assertNotIn('confirm_delay', _src(Orochi._close_orochi_soul_choice_popup))


class EvoZoneReactionTest(TestCase):
    def test_check_lock_calls_pass_fast(self):
        for func in (EvoZone.run_leader, EvoZone.run_alone):
            self.assertIn('confirm_delay=REACTION_FAST', _src(func), func.__name__)

    def test_kirin_type_selection_uses_deliberate_single_site(self):
        src = _src(EvoZone.evozone_enter)
        self.assertIn('appear_then_click(kirintype, interval=1, confirm_delay=REACTION_DELIBERATE)', src)
        # 只有一个点击点，不重复给 5 个具体类型各加一次
        self.assertEqual(src.count('confirm_delay='), 1)

    def test_form_team_uses_normal(self):
        self.assertIn(
            'appear_then_click(self.I_FORM_TEAM, interval=1, confirm_delay=REACTION_NORMAL)',
            _src(EvoZone.run_leader))

    def test_evozone_fire_and_layer_untouched(self):
        self.assertNotIn('confirm_delay', _src(EvoZone.check_layer))
        for func in (EvoZone.run_alone, EvoZone.run_member):
            src = _src(func)
            if 'I_EVOZONE_FIRE' in src:
                self.assertNotIn('I_EVOZONE_FIRE, interval=1, confirm_delay', src)


class RyouToppaReactionTest(TestCase):
    def test_lock_toggle_uses_fast_action_none_form(self):
        src = _src(RyouToppa._ensure_team_lock_state)
        # source（当前状态图，无 action=）+ FAST
        self.assertIn('appear_then_click(source, interval=0, confirm_delay=REACTION_FAST)', src)

    def test_admin_buttons_use_fast(self):
        src = _src(RyouToppa.start_ryou_toppa)
        self.assertIn(
            'appear_then_click(self.I_SELECT_RYOU_BUTTON, interval=1, confirm_delay=REACTION_FAST)', src)
        self.assertIn(
            'appear_then_click(self.I_START_TOPPA_BUTTON, interval=1, confirm_delay=REACTION_FAST)', src)
        # #26 排除：I_GUILD_ORDERS_REWARDS 带 action= 的调用不加
        self.assertIn('appear_then_click(self.I_GUILD_ORDERS_REWARDS, action=self.C_SELECT_FIRST_RYOU, interval=1)', src)
        self.assertNotIn('I_GUILD_ORDERS_REWARDS, action=self.C_SELECT_FIRST_RYOU, interval=1, confirm_delay', src)

    def test_attack_area_i_fire_still_hand_rolled_not_stacked(self):
        src = _src(RyouToppa.attack_area)
        # 保留区域业务 pacing 与 I_FIRE 手搓 reaction（2026-09-08 起 FIRE 统一 REACTION_FIRE）
        self.assertIn('random_delay(1.0, 3.0)', src)
        self.assertIn('random_delay(*REACTION_FIRE)', src)
        self.assertNotIn('random_delay(0.2, 0.6)', src)
        # I_FIRE 的点击点没有再叠 confirm_delay
        self.assertIn("appear_then_click(RealmRaidAssets.I_FIRE, interval=0, threshold=0.8)", src)
        self.assertNotIn('confirm_delay', src)

    def test_click_toppa_area_not_touched(self):
        self.assertNotIn('confirm_delay', _src(RyouToppa._click_toppa_area))


class ExplorationReactionTest(TestCase):
    def test_auto_rotate_toggle_uses_fast(self):
        # 2026-09-08 Level C hotfix：switch_rotate 的 AutoRotate.no 分支不再点 I_E_AUTO_ROTATE_ON
        # 去取消用户轮换（轮换归用户所有）。仅剩 run_on_exp_settings 的 yes 分支开轮换 + 填充候补。
        body = _src(BaseExploration.switch_rotate).split('"""')[-1]   # 去 docstring 只扫代码体
        self.assertNotIn('I_E_AUTO_ROTATE_ON', body)
        self.assertIn(
            'appear_then_click(self.I_E_AUTO_ROTATE_OFF, interval=0.8, confirm_delay=REACTION_FAST)',
            _src(Exploration.run_on_exp_settings))

    def test_exit_dialog_confirm_and_navigation(self):
        src = _src(Exploration.run_on_exp_exit)
        self.assertIn(
            'appear_then_click(self.I_E_EXIT_CANCEL, interval=0.8, confirm_delay=REACTION_NAVIGATION)', src)
        self.assertIn(
            'appear_then_click(self.I_E_EXIT_CONFIRM, interval=0.8, confirm_delay=REACTION_CONFIRM)', src)

    def test_back_yellow_uses_navigation(self):
        self.assertIn(
            'appear_then_click(self.I_UI_BACK_YELLOW, interval=0.8, confirm_delay=REACTION_NAVIGATION)',
            _src(BaseExploration.quit_exp_main))

    def test_chapter_confirm_uses_normal_all_four_sites(self):
        src = _src(BaseExploration.open_expect_level)
        self.assertEqual(
            src.count('appear_then_click(self.I_UI_CONFIRM, interval=1, confirm_delay=REACTION_NORMAL)'), 2)
        self.assertEqual(
            src.count('appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1, confirm_delay=REACTION_NORMAL)'), 2)
        # 明确不动 OCR 目标与 swipe→sleep(1) settle 段
        self.assertIn('ocr_appear_click(self.O_E_EXPLORATION_LEVEL_NUMBER)', src)
        self.assertNotIn('O_E_EXPLORATION_LEVEL_NUMBER, confirm_delay', src)
        self.assertIn('time.sleep(1)', src)

    def test_dynamic_and_polling_targets_untouched(self):
        self.assertNotIn('confirm_delay', _src(BaseExploration.fire))
        self.assertNotIn('confirm_delay', _src(BaseExploration.collect_treasure_box))
        # 队长邀请弹窗 I_UI_CANCEL、page_reward random_click 在 script_task 里，不加
        st_src = inspect.getsource(inspect.getmodule(Exploration))
        self.assertIn('appear_then_click(self.I_UI_CANCEL, interval=0.8)', st_src)
        self.assertNotIn('I_UI_CANCEL, interval=0.8, confirm_delay', st_src)
        self.assertNotIn('random_click(), interval=0.8, confirm_delay', st_src)


class GeneralBattleExclusionTest(TestCase):
    def test_check_lock_param_defaults_none_and_threaded(self):
        sig = inspect.signature(GeneralBattle.check_lock)
        self.assertIn('confirm_delay', sig.parameters)
        self.assertIsNone(sig.parameters['confirm_delay'].default)
        src = _src(GeneralBattle.check_lock)
        # 两个分支都把 confirm_delay 透传给 appear_then_click
        self.assertEqual(src.count('confirm_delay=confirm_delay'), 2)

    def test_check_lock_default_call_keeps_old_behavior(self):
        """不传 confirm_delay 时，check_lock 内 appear_then_click 收到 None（= 原行为）。"""
        gb = GeneralBattle.__new__(GeneralBattle)
        calls = []
        gb.screenshot = Mock()
        gb.appear = Mock(side_effect=[False, True])  # 先未到位、点一次后到位
        gb.appear_then_click = Mock(side_effect=lambda *a, **kw: calls.append(kw.get('confirm_delay', 'MISSING')) or True)
        gb.check_lock(True, lock_image='L', unlock_image='U')
        self.assertEqual(calls, [None])

    def test_check_lock_forwards_profile_tuple(self):
        gb = GeneralBattle.__new__(GeneralBattle)
        calls = []
        gb.screenshot = Mock()
        gb.appear = Mock(side_effect=[False, True])
        gb.appear_then_click = Mock(side_effect=lambda *a, **kw: calls.append(kw.get('confirm_delay')) or True)
        gb.check_lock(True, 'L', 'U', confirm_delay=rp.REACTION_FAST)
        self.assertEqual(calls, [(0.18, 0.35)])

    def test_prepare_highlight_has_no_confirm_delay(self):
        src = _src(GeneralBattle._handle_prepare)
        self.assertIn('appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=0.8)', src)
        self.assertNotIn('I_PREPARE_HIGHLIGHT, interval=0.8, confirm_delay', src)
        # prepare_click_timer 仍是它的 timing owner
        self.assertIn('_prepare_click_ready', src)

    def test_settlement_v3_has_no_confirm_delay(self):
        # Settlement Micro-Burst v1（2026-09-12）：旧 `_advance_generic_result`（固定两次）
        # 已被 session/burst 模型取代，改查新的 burst 相关方法。
        for func in (GeneralBattle._settlement_burst_step,
                     GeneralBattle._fire_settlement_burst,
                     GeneralBattle._settlement_click,
                     GeneralBattle._sample_settlement_click,
                     GeneralBattle._handle_result,
                     GeneralBattle._handle_reward):
            src = _src(func)
            self.assertNotIn('confirm_delay', src, func.__name__)
        # settlement timer 仍是跨 burst 节流 owner；burst 内部间隔改用 _sample_interval
        # （Micro-Burst 专属 SETTLEMENT_BURST_CLICK_INTERVAL_RANGE，不是 confirm_delay）。
        self.assertIn('settlement_click_timer', _src(GeneralBattle._settlement_click))
        self.assertIn('self._sample_interval(self.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)',
                      _src(GeneralBattle._fire_settlement_burst))

    def test_transient_battle_targets_untouched(self):
        prep = _src(GeneralBattle._handle_prepare)
        for tgt in ('I_DISABLE_7DAYS_DIFF_SOUL', 'I_CONFIRM_CLOSE_DIFF_SOUL'):
            self.assertIn(f'appear_then_click(self.{tgt}, interval=0.6)', prep)
            self.assertNotIn(f'{tgt}, interval=0.6, confirm_delay', prep)
        rew = _src(GeneralBattle._handle_reward)
        for tgt in ('I_OVER_GHOST', 'I_GB_SKIN_CONFIRM'):
            self.assertIn(f'appear_then_click(self.{tgt}, interval=0.8)', rew)
            self.assertNotIn(f'{tgt}, interval=0.8, confirm_delay', rew)
        self.assertNotIn('confirm_delay', _src(GeneralBattle.random_click_swipt))


class TimingOwnerNoStackTest(TestCase):
    """确认没有出现 reaction + 已有同语义 random_delay / timer 的重复叠加。"""

    def test_ryoutoppa_i_fire_owner_is_hand_rolled_random_delay_only(self):
        src = _src(RyouToppa.attack_area)
        # 同一段里既没有 confirm_delay，又保留了手搓 fire_delay（2026-09-08 起统一 REACTION_FIRE）
        self.assertIn('fire_delay = random_delay(*REACTION_FIRE)', src)
        self.assertNotIn('confirm_delay', src)

    def test_generalbattle_prepare_and_settlement_owners_intact(self):
        self.assertIn('PREPARE_CLICK_DELAY_RANGE', inspect.getsource(inspect.getmodule(GeneralBattle)))
        self.assertIn('SETTLEMENT_CLICK_INTERVAL_RANGE', inspect.getsource(inspect.getmodule(GeneralBattle)))

    def test_no_reaction_profile_import_in_asset_modules(self):
        # reaction 属业务 consumer，不在 asset / RuleImage 层
        for mod_name in ('tasks.RealmRaid.assets', 'tasks.Orochi.assets',
                         'tasks.EvoZone.assets', 'tasks.RyouToppa.assets',
                         'tasks.Exploration.assets', 'tasks.Component.GeneralBattle.assets'):
            mod = __import__(mod_name, fromlist=['x'])
            self.assertNotIn('reaction_profile', inspect.getsource(mod), mod_name)
            self.assertNotIn('confirm_delay', inspect.getsource(mod), mod_name)
