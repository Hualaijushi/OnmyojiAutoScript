# This Python file uses the following encoding: utf-8
"""ActivityShikigami 当期普通爬塔线适配的护栏测试。

覆盖本轮落地的 5 块契约（见 `docs/DECISIONS.md` D001 FIRE 分节 / Fatigue Safe Point 补记、
`docs/AI_CONTEXT.md`）：

1. 庭院活动入口改用本期 `I_MAIN_GOTO_ACT_2`（旧 `I_MAIN_GOTO_ACT` 保留作跨周期回退）。
2. `_is_active_battle_entry()` 窄 detector —— 不再用宽 `is_in_battle()` 判「新战斗已开始」。
3. `_enter_climb_battle()` bounded battle-entry transaction —— REACTION_FIRE + fresh 二次确认
   + 有限 attempt / 墙钟 / post-click 三态轮询，取代旧 `while True` + `is_in_battle(False)`。
4. `_activity_challenge_safe_break()` —— 「稳定挑战页 + Challenge Ready」= Fatigue 安全节点；
   旧 `random_sleep` 在爬塔线让位给 Fatigue（`_fatigue_owns_macro_idle`），无 macro-idle stack。
5. `_drain_activity_settlement()` —— 本期活动结算弹窗复用 GeneralBattle `C_RANDOM_DEFAULT`
   （`random_default`）大安全区推进，有界，正向确认回到挑战页才算 cycle complete。

大富翁 / 伪神降临线本轮不改，`RichManFakeGodUntouchedTest` 守卫。
"""

import ast
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.atom.image import RuleImage
from tasks.Component.config_fire_reaction import FireReactionConfig
from module.reaction_profile import REACTION_FIRE, REACTION_NAVIGATION
from tasks.ActivityShikigami import page as as_page
from tasks.ActivityShikigami.activities import normal as normal_mod
from tasks.ActivityShikigami.activities.normal import (
    ACTIVITY_FIRE_MAX_TRIES,
    ACTIVITY_FIRE_POST_CLICK_TIMEOUT,
    ACTIVITY_FIRE_TIMEOUT,
    ACTIVITY_SETTLEMENT_MAX_CLICKS,
    ACTIVITY_SETTLEMENT_TIMEOUT,
    NormalClimbAct,
)
from tasks.ActivityShikigami.activities.fake_god import FakeGodAct
from tasks.ActivityShikigami.activities.rich_man import RichManAct
from tasks.ActivityShikigami.base_act import ActivityResourceNotEnough, BaseAct
from tasks.ActivityShikigami.script_task import ScriptTask


def _src(func):
    return inspect.getsource(func)


def _body(func):
    """去掉首个 docstring 只留代码体。"""
    return _src(func).split('"""')[-1]


def _img(name):
    # RuleImage.name 由 file 的 stem.upper() 推导；测试直接给 stem 即可
    return RuleImage(roi_front=(1, 2, 3, 4), roi_back=(1, 2, 3, 4),
                     method='Template matching', threshold=0.8,
                     file=f'./tests/_fake/{name.lower()}.png')


def _tail(values):
    values = list(values) or [False]
    for v in values:
        yield v
    while True:
        yield values[-1]


class _FakeTimer:
    """确定性 Timer 替身：reached() 超过 budget 次即到期。"""

    budget = 6

    def __init__(self, limit, *a, **kw):
        self.limit = limit
        self._n = 0

    def start(self):
        return self

    def reached(self):
        self._n += 1
        return self._n > _FakeTimer.budget


# --------------------------------------------------------------------------------------
# 1. 庭院活动入口 main_goto_act_2
# --------------------------------------------------------------------------------------


class EntrySourceTest(TestCase):
    def test_asset_has_new_and_legacy_entry(self):
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
        self.assertTrue(hasattr(ActivityShikigamiAssets, 'I_MAIN_GOTO_ACT_2'))
        # 旧入口不机械删除（跨活动周期兼容 / 其它引用）
        self.assertTrue(hasattr(ActivityShikigamiAssets, 'I_MAIN_GOTO_ACT'))
        self.assertIn('page_main_goto_act_2.png',
                      ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.file)

    def test_goto_activity_entry_prefers_new_then_legacy_with_navigation_reaction(self):
        src = _src(as_page.goto_activity_entry)
        # 先当期入口、后旧入口
        i_new = src.index('I_MAIN_GOTO_ACT_2')
        i_old = src.index('I_MAIN_GOTO_ACT,')
        self.assertLess(i_new, i_old)
        # 有 navigation reaction（fresh 二次确认再点）
        self.assertIn('policy=InteractionPolicy.NAVIGATION', src)

    def test_page_main_edge_uses_callable_not_bare_legacy_image(self):
        src = _src(as_page)
        self.assertIn("page_main.connect(page_act, goto_activity_entry, key='main->activity')", src)
        self.assertNotIn("page_main.connect(page_act, ActivityShikigamiAssets.I_MAIN_GOTO_ACT,", src)

    def test_find_activity_entry_accepts_either_icon(self):
        body = _body(as_page.find_activity_entry)
        self.assertIn('_activity_entry_visible(task)', body)
        vis = _src(as_page._activity_entry_visible)
        self.assertIn('I_MAIN_GOTO_ACT_2', vis)
        self.assertIn('I_MAIN_GOTO_ACT', vis)


class SecondLayerClimbEntryTest(TestCase):
    """本期普通爬塔是「二层入口」：page_act --I_TO_BATTLE_MAIN--> page_climb_main
    --I_TO_BATTLE_MAIN_2--> page_climb_ap/pass；真正爬塔页标题横幅换 I_CHECK_BATTLE_PASS_2
    （旧 I_CHECK_BATTLE_PASS 作 legacy fallback）。中间页 positive marker = 该页稳定按钮
    I_TO_BATTLE_MAIN_2，不是「上一页按钮消失」。business（Fatigue/FIRE/Settlement）只在
    真正 page_climb_ap/pass positive 之后开始。"""

    def _markers(self, page):
        from tasks.GameUi.matcher import collect_rule_images
        return {t.name for t in collect_rule_images(page.recognizer)}

    # ---- 新资产 ----
    def test_new_assets_present(self):
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets as A
        self.assertTrue(hasattr(A, 'I_TO_BATTLE_MAIN_2'))
        self.assertTrue(hasattr(A, 'I_CHECK_BATTLE_PASS_2'))
        self.assertIn('climb_to_battle_main_2.png', A.I_TO_BATTLE_MAIN_2.file)
        self.assertIn('climb_check_battle_pass_2.png', A.I_CHECK_BATTLE_PASS_2.file)
        # 旧 marker 不删（跨活动周期兼容）
        self.assertTrue(hasattr(A, 'I_CHECK_BATTLE_PASS'))
        self.assertTrue(hasattr(A, 'I_TO_BATTLE_MAIN'))

    # ---- 中间页 page_climb_main ----
    def test_page_climb_main_exists_with_own_positive_marker(self):
        self.assertTrue(hasattr(as_page, 'page_climb_main'))
        self.assertEqual(self._markers(as_page.page_climb_main), {'CLIMB_TO_BATTLE_MAIN_2'})

    def test_page_climb_main_marker_is_not_previous_or_challenge_marker(self):
        m = self._markers(as_page.page_climb_main)
        # 不靠「上一页按钮消失」，也不含真正爬塔页 / Challenge Ready marker
        for forbidden in ('CLIMB_CHECK_BATTLE_PASS_2', 'AS_CHECK_BATTLE_PASS',
                          'AS_CLIMB_MODE_AP', 'AS_CLIMB_MODE_PASS',
                          'AS_ACT_FIRE', 'AS_AS_BOSS_FIRE', 'AS_CHECK_BATTLE_MAIN'):
            self.assertNotIn(forbidden, m, forbidden)

    def test_page_climb_main_has_recovery_back_edge(self):
        src = _src(as_page)
        self.assertIn("page_climb_main.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW", src)

    # ---- 真正爬塔页 recognizer：新 primary + legacy fallback + 必须带 mode ----
    def test_climb_ap_recognizer_new_primary_legacy_fallback_and_mode(self):
        m = self._markers(as_page.page_climb_ap)
        self.assertIn('CLIMB_CHECK_BATTLE_PASS_2', m)   # 本期新 marker primary
        self.assertIn('AS_CHECK_BATTLE_PASS', m)        # 旧 marker legacy fallback
        self.assertIn('AS_CLIMB_MODE_AP', m)            # 仍必须带 mode（all_of）
        src = _src(as_page)
        i2 = src.index('I_CHECK_BATTLE_PASS_2')
        i1 = src.index('I_CHECK_BATTLE_PASS,')
        self.assertLess(i2, i1)                         # 新 marker 在前

    def test_climb_pass_recognizer_new_primary_legacy_fallback_and_mode(self):
        m = self._markers(as_page.page_climb_pass)
        self.assertIn('CLIMB_CHECK_BATTLE_PASS_2', m)
        self.assertIn('AS_CHECK_BATTLE_PASS', m)
        self.assertIn('AS_CLIMB_MODE_PASS', m)

    # ---- 中间页 vs 真正爬塔页互斥（不靠 priority） ----
    def test_middle_and_climb_pages_mutually_exclusive(self):
        class _T:
            def __init__(self, present):
                self.present = present

            def appear(self, r, **kw):
                return r.name in self.present

        mid_only = _T({'CLIMB_TO_BATTLE_MAIN_2'})
        self.assertTrue(as_page.page_climb_main.recognizer.evaluate(mid_only))
        self.assertFalse(as_page.page_climb_ap.recognizer.evaluate(mid_only))
        self.assertFalse(as_page.page_climb_pass.recognizer.evaluate(mid_only))

        real_ap = _T({'CLIMB_CHECK_BATTLE_PASS_2', 'AS_CLIMB_MODE_AP'})
        self.assertFalse(as_page.page_climb_main.recognizer.evaluate(real_ap))
        self.assertTrue(as_page.page_climb_ap.recognizer.evaluate(real_ap))

        legacy_pass = _T({'AS_CHECK_BATTLE_PASS', 'AS_CLIMB_MODE_PASS'})
        self.assertTrue(as_page.page_climb_pass.recognizer.evaluate(legacy_pass))

    def test_no_priority_hack_on_page_act_or_climb_pages(self):
        # 本轮不改 page_act recognizer / priority，也不给 climb 页拍脑袋加 priority
        self.assertEqual(as_page.page_act.priority, 70)
        self.assertEqual(self._markers(as_page.page_act),
                         {'AS_CHECK_BATTLE_MAIN', 'AS_ACTIVITY_AWARD', 'AS_ACTIVITY_SIGNIN_CLOSE'})
        self.assertNotIn('AS_TO_BATTLE_MAIN', self._markers(as_page.page_act))
        self.assertEqual(as_page.page_climb_main.priority, 50)
        self.assertEqual(as_page.page_climb_ap.priority, 50)
        self.assertEqual(as_page.page_climb_pass.priority, 50)

    # ---- setup_climb_pages 的 page graph 边 ----
    def test_setup_climb_pages_two_layer_edges(self):
        src = _src(NormalClimbAct.setup_climb_pages)
        # 第一层：page_act -> page_climb_main via I_TO_BATTLE_MAIN
        self.assertIn("page_act.connect(page_mid, ActivityShikigamiAssets.I_TO_BATTLE_MAIN, "
                      "key='activity->climb_main')", src)
        # 第二层：page_climb_main -> ap/pass via I_TO_BATTLE_MAIN_2
        self.assertIn("page_mid.connect(page_ap, ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2, "
                      "key='climb_main->climb_ap')", src)
        self.assertIn("page_mid.connect(page_pass, ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2, "
                      "key='climb_main->climb_pass')", src)
        # 旧的 page_act 直连 climb 页已移除
        self.assertNotIn("key='activity->climb_ap'", src)
        self.assertNotIn("key='activity->climb_pass'", src)
        # mode 切换保留
        self.assertIn("key='climb_pass->climb_ap'", src)
        self.assertIn("key='climb_ap->climb_pass'", src)

    def test_setup_resolves_page_climb_main(self):
        src = _src(NormalClimbAct.setup_climb_pages)
        self.assertIn('self.navigator.resolve_page(pages.page_climb_main)', src)

    # ---- business boundary：中间页不触发 Fatigue / FIRE ----
    def test_business_loop_only_runs_on_real_climb_page(self):
        # _run_climb_type 的业务分支只在 current_page == destination（= page_climb_ap/pass）时进；
        # destination recognizer 要求 I_CHECK_BATTLE_PASS_2/PASS + mode，中间页（只有
        # I_TO_BATTLE_MAIN_2）不满足 → 不会进 _sync_climb_penta_pass / safe_break / _run_climb_action。
        src = _src(NormalClimbAct._run_climb_type)
        self.assertIn('if current_page == destination:', src)
        self.assertIn('self._activity_challenge_safe_break(', src)
        # safe break / FIRE 都在 `== destination` 分支体内
        i_branch = src.index('if current_page == destination:')
        i_safe = src.index('self._activity_challenge_safe_break(')
        i_action = src.index('self._run_climb_action(action_type, destination)')
        self.assertLess(i_branch, i_safe)
        self.assertLess(i_branch, i_action)

    def test_challenge_ready_marker_is_fire_rule_not_second_layer_button(self):
        # Challenge Ready = _climb_fire_rule（I_ACT_FIRE / I_AS_BOSS_FIRE），与 I_TO_BATTLE_MAIN_2 无关
        src = _src(NormalClimbAct._climb_fire_rule)
        self.assertIn('I_AS_BOSS_FIRE', src)
        self.assertIn('I_ACT_FIRE', src)
        self.assertNotIn('I_TO_BATTLE_MAIN_2', src)
        safe = _src(NormalClimbAct._activity_challenge_safe_break)
        self.assertIn('self._climb_fire_rule(action_type)', safe)
        self.assertNotIn('I_TO_BATTLE_MAIN_2', safe)


class EntryBehaviorTest(TestCase):
    def _task(self, present):
        t = SimpleNamespace()
        clicked = []

        def _atc(target, **kw):
            if target.name in present:
                clicked.append(target.name)
                return True
            return False

        t.appear_then_click = Mock(side_effect=_atc)
        t.appear = Mock(side_effect=lambda target, **kw: target.name in present)
        return t, clicked

    def test_new_icon_present_clicks_new_only(self):
        t, clicked = self._task({'RES_MAIN_GOTO_ACT_2', 'I_MAIN_GOTO_ACT_2'})
        # goto_activity_entry 用 assets 常量，其 .name 由资产生成；用真实资产对象
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
        present = {ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.name}
        t.appear_then_click = Mock(side_effect=lambda target, **kw: target.name in present)
        self.assertIs(as_page.goto_activity_entry(t), True)
        names = [c.args[0].name for c in t.appear_then_click.call_args_list]
        self.assertEqual(names[0], ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.name)
        self.assertEqual(len(names), 1)  # 命中当期入口后不再试旧入口

    def test_only_legacy_present_falls_back(self):
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
        present = {ActivityShikigamiAssets.I_MAIN_GOTO_ACT.name}
        t = SimpleNamespace(appear_then_click=Mock(
            side_effect=lambda target, **kw: target.name in present))
        self.assertIs(as_page.goto_activity_entry(t), True)
        names = [c.args[0].name for c in t.appear_then_click.call_args_list]
        self.assertEqual(names, [ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.name,
                                 ActivityShikigamiAssets.I_MAIN_GOTO_ACT.name])

    def test_neither_present_returns_false(self):
        t = SimpleNamespace(appear_then_click=Mock(return_value=False))
        self.assertIs(as_page.goto_activity_entry(t), False)

    def test_entry_visible_true_if_either(self):
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
        new_name = ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.name
        old_name = ActivityShikigamiAssets.I_MAIN_GOTO_ACT.name
        for present in ({new_name}, {old_name}, {new_name, old_name}):
            t = SimpleNamespace(appear=Mock(side_effect=lambda tg, **kw: tg.name in present))
            self.assertTrue(as_page._activity_entry_visible(t))
        t = SimpleNamespace(appear=Mock(return_value=False))
        self.assertFalse(as_page._activity_entry_visible(t))


# --------------------------------------------------------------------------------------
# 2. 窄 New Battle Entry Detector
# --------------------------------------------------------------------------------------


class NarrowBattleEntryTest(TestCase):
    RESULT_REWARD = ('I_FALSE', 'I_WIN', 'I_DE_WIN', 'I_REWARD', 'I_REWARD_GOLD', 'I_FRIENDS')

    def test_helper_source_is_narrow(self):
        body = _body(BaseAct._is_active_battle_entry)
        self.assertIn('self.is_in_prepare(False)', body)
        self.assertIn('self.is_in_real_battle(False)', body)
        self.assertNotIn('is_in_battle(', body)
        for m in self.RESULT_REWARD:
            self.assertNotIn(m, body, m)
        for tok in ('screenshot(', '.click(', 'appear_then_click', 'sleep(', 'Timer('):
            self.assertNotIn(tok, body, tok)

    def _mk(self, *, prepare=False, real=False):
        t = ScriptTask.__new__(ScriptTask)
        t.is_in_prepare = Mock(return_value=prepare)
        t.is_in_real_battle = Mock(return_value=real)
        t.is_in_battle = Mock(return_value=True)  # 宽 detector 即使 True 也不该被采用
        return t

    def test_result_reward_frame_not_active_battle(self):
        t = self._mk(prepare=False, real=False)
        self.assertIs(t._is_active_battle_entry(), False)
        t.is_in_battle.assert_not_called()

    def test_prepare_frame_is_active(self):
        self.assertIs(self._mk(prepare=True)._is_active_battle_entry(), True)

    def test_real_battle_frame_is_active(self):
        self.assertIs(self._mk(real=True)._is_active_battle_entry(), True)

    def test_enter_climb_battle_body_has_no_wide_detector_no_while_true(self):
        body = _body(NormalClimbAct._enter_climb_battle)
        self.assertNotIn('while True', body)
        self.assertNotIn('is_in_battle(', body)
        self.assertIn('_is_active_battle_entry()', _body(NormalClimbAct._classify_climb_fire_state))


# --------------------------------------------------------------------------------------
# 3. FIRE 状态分类 + bounded transaction
# --------------------------------------------------------------------------------------


class ClimbFireStateTest(TestCase):
    def _t(self, *, active=False, fire=False):
        t = ScriptTask.__new__(ScriptTask)
        t._is_active_battle_entry = Mock(return_value=active)
        t.appear = Mock(return_value=fire)
        return t

    def test_battle(self):
        self.assertEqual(self._t(active=True)._classify_climb_fire_state(_img('f')), 'battle')

    def test_ready(self):
        self.assertEqual(self._t(active=False, fire=True)._classify_climb_fire_state(_img('f')),
                         'ready')

    def test_unknown(self):
        self.assertEqual(self._t(active=False, fire=False)._classify_climb_fire_state(_img('f')),
                         'unknown')

    def test_wait_times_out_when_always_unknown(self):
        t = self._t(active=False, fire=False)
        t.screenshot = Mock()
        with patch.object(normal_mod, 'Timer', _FakeTimer):
            self.assertEqual(t._wait_climb_fire_state(_img('f')), 'timeout')
        self.assertLessEqual(t.screenshot.call_count, _FakeTimer.budget + 1)


class EnterClimbBattleTest(TestCase):
    def _mk(self, *, active_seq, fire_seq, action_type='ap'):
        for tgt, repl in (('Timer', _FakeTimer),
                          ('random_delay', Mock(return_value=0.5))):
            p = patch.object(normal_mod, tgt, repl)
            p.start()
        self.addCleanup(patch.stopall)
        p = patch.object(normal_mod.time, 'sleep', Mock())
        p.start()

        t = ScriptTask.__new__(ScriptTask)
        events = []
        t.device = SimpleNamespace(image='F', click_record_clear=Mock())
        t.conf = SimpleNamespace(fire_reaction=FireReactionConfig())
        t.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        t.I_ACT_FIRE = _img('I_ACT_FIRE')
        t.I_AS_BOSS_FIRE = _img('I_AS_BOSS_FIRE')
        t.I_UI_CONFIRM = _img('I_UI_CONFIRM')
        t.I_UI_CONFIRM_SAMLL = _img('I_UI_CONFIRM_SAMLL')
        active_it = _tail(active_seq)
        fire_it = _tail(fire_seq)
        t._is_active_battle_entry = Mock(side_effect=lambda: next(active_it))

        def _appear(target, **kw):
            if target.name in ('I_ACT_FIRE', 'I_AS_BOSS_FIRE'):
                return next(fire_it)
            return False  # confirm 弹窗一律不出现

        t.appear = Mock(side_effect=_appear)

        def _atc(target, **kw):
            events.append(('atc', target.name))
            return False if target.name in ('I_UI_CONFIRM', 'I_UI_CONFIRM_SAMLL') else True

        t.appear_then_click = Mock(side_effect=_atc)
        return t, events

    def _fire_clicks(self, events):
        return [e for e in events if e[0] == 'atc' and e[1] in ('I_ACT_FIRE', 'I_AS_BOSS_FIRE')]

    def test_ready_reaction_click_battle_returns_true(self):
        t, events = self._mk(active_seq=[False, False, True], fire_seq=[True])
        self.assertIs(t._enter_climb_battle('ap'), True)
        self.assertEqual(normal_mod.random_delay.call_count, 1)
        self.assertEqual(normal_mod.random_delay.call_args.args, tuple(REACTION_FIRE))
        self.assertEqual(len(self._fire_clicks(events)), 1)

    def test_already_battle_first_frame_no_reaction_no_click(self):
        t, events = self._mk(active_seq=[True], fire_seq=[False])
        self.assertIs(t._enter_climb_battle('ap'), True)
        self.assertEqual(normal_mod.random_delay.call_count, 0)
        self.assertEqual(self._fire_clicks(events), [])

    def test_fire_gone_during_reaction_no_stale_click(self):
        # classify1 = ready（fire True）→ reaction → classify2 fire False → 不点
        t, events = self._mk(active_seq=[False] * 30, fire_seq=[True, False])
        self.assertIs(t._enter_climb_battle('ap'), False)
        self.assertEqual(self._fire_clicks(events), [])

    def test_fire_never_appears_bounded_false(self):
        t, events = self._mk(active_seq=[False] * 80, fire_seq=[False] * 80)
        self.assertIs(t._enter_climb_battle('ap'), False)
        self.assertEqual(self._fire_clicks(events), [])
        # 有界：screenshot 不会无限增长
        self.assertLess(t.screenshot.call_count, 200)

    def test_post_click_always_unknown_bounded_false(self):
        # 每 attempt: ready → reaction(ready) → click → wait 全 unknown → timeout
        t, events = self._mk(active_seq=[False] * 200,
                             fire_seq=[True, True] * 200)
        self.assertIs(t._enter_climb_battle('ap'), False)
        self.assertLessEqual(len(self._fire_clicks(events)), ACTIVITY_FIRE_MAX_TRIES)

    def test_source_bounded_constants(self):
        src = _src(NormalClimbAct._enter_climb_battle)
        self.assertIn('Timer(ACTIVITY_FIRE_TIMEOUT)', src)
        self.assertIn('range(1, ACTIVITY_FIRE_MAX_TRIES + 1)', src)
        self.assertIn('random_delay(*fire_reaction_range(self.conf.fire_reaction))', src)
        self.assertEqual((ACTIVITY_FIRE_MAX_TRIES, ACTIVITY_FIRE_TIMEOUT,
                          ACTIVITY_FIRE_POST_CLICK_TIMEOUT), (4, 12, 4))


# --------------------------------------------------------------------------------------
# 4. Challenge Ready = Fatigue Safe Point
# --------------------------------------------------------------------------------------


class ChallengeSafeBreakTest(TestCase):
    def _t(self):
        t = ScriptTask.__new__(ScriptTask)
        t.screenshot = Mock()
        t.I_ACT_FIRE = _img('I_ACT_FIRE')
        t.I_AS_BOSS_FIRE = _img('I_AS_BOSS_FIRE')
        t.start_time = datetime.now()
        t.conf = SimpleNamespace(general_config=SimpleNamespace(limit_time_v=timedelta(hours=1)))
        t.try_fatigue_break = Mock(return_value=None)
        t._climb_resource_available = Mock(return_value=True)
        t.get_current_page = Mock(return_value='DEST')
        t.appear = Mock(return_value=True)
        return t

    def test_not_on_destination_no_fatigue(self):
        t = self._t()
        t.get_current_page = Mock(return_value='OTHER')
        self.assertIs(t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=False), False)
        t.try_fatigue_break.assert_not_called()

    def test_fire_not_ready_no_fatigue(self):
        t = self._t()
        t.appear = Mock(return_value=False)
        self.assertIs(t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=True), False)
        t.try_fatigue_break.assert_not_called()

    def test_ready_no_break_returns_true_and_forwards_repeat_flag(self):
        t = self._t()
        self.assertIs(t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=False), True)
        self.assertEqual(t.try_fatigue_break.call_args.kwargs['repeat_completed'], False)
        t = self._t()
        self.assertIs(t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=True), True)
        self.assertEqual(t.try_fatigue_break.call_args.kwargs['repeat_completed'], True)
        self.assertEqual(t.try_fatigue_break.call_args.kwargs['safe'], True)

    def test_break_then_fire_gone_returns_false(self):
        t = self._t()
        t.try_fatigue_break = Mock(return_value=SimpleNamespace(kind='rest'))
        # 休息后 fresh screenshot：页面还在，但挑战键消失
        t.appear = Mock(side_effect=_tail([True, False]))
        self.assertIs(t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=True), False)

    def test_break_then_resource_empty_raises(self):
        t = self._t()
        t.try_fatigue_break = Mock(return_value=SimpleNamespace(kind='rest'))
        t._climb_resource_available = Mock(return_value=False)
        with self.assertRaises(ActivityResourceNotEnough):
            t._activity_challenge_safe_break('ap', 'DEST', repeat_completed=True)

    def test_single_fatigue_break_call_site_in_climb(self):
        # try_fatigue_break 在爬塔线只出现在 _activity_challenge_safe_break 一处
        src = _src(NormalClimbAct)
        self.assertEqual(src.count('self.try_fatigue_break('), 1)
        self.assertIn('deadline=self.start_time + self.conf.general_config.limit_time_v',
                      _src(NormalClimbAct._activity_challenge_safe_break))


# --------------------------------------------------------------------------------------
# 5. Macro idle ownership —— 无 random_sleep + Fatigue stack
# --------------------------------------------------------------------------------------


class MacroIdleOwnershipTest(TestCase):
    def test_run_climb_claims_macro_idle_and_begins_fatigue(self):
        src = _src(NormalClimbAct.run_climb)
        self.assertIn('self._fatigue_owns_macro_idle = True', src)
        self.assertIn("self.begin_fatigue_task('ActivityShikigami')", src)

    def test_prepare_next_action_gates_random_sleep_on_flag(self):
        src = _src(BaseAct.prepare_next_action)
        self.assertIn('and not self._fatigue_owns_macro_idle', src)

    def test_flag_true_skips_random_sleep(self):
        t = ScriptTask.__new__(ScriptTask)
        t._fatigue_owns_macro_idle = True
        t.action_count = {'ap': 0}
        t.action_limit = Mock(return_value=10)
        t.time_limit_reached = Mock(return_value=False)
        t.conf = SimpleNamespace(general_config=SimpleNamespace(random_sleep=True))
        with patch.object(normal_mod, 'random_delay', Mock(return_value=0.5)), \
                patch('tasks.ActivityShikigami.base_act.random_sleep') as rs:
            self.assertIs(BaseAct.prepare_next_action(t, 'ap'), True)
        rs.assert_not_called()

    def test_flag_false_still_random_sleeps(self):
        t = ScriptTask.__new__(ScriptTask)
        t._fatigue_owns_macro_idle = False
        t.action_count = {'rich_man': 0}
        t.action_limit = Mock(return_value=10)
        t.time_limit_reached = Mock(return_value=False)
        t.conf = SimpleNamespace(general_config=SimpleNamespace(random_sleep=True))
        with patch('tasks.ActivityShikigami.base_act.random_sleep') as rs:
            BaseAct.prepare_next_action(t, 'rich_man')
        rs.assert_called_once()


# --------------------------------------------------------------------------------------
# 5.1 Macro Idle ownership 生命周期 —— 同一实例连跑多条玩法线不得残留上一条线的 owner
#
# 背景（pre-push review BLOCKER）：`ScriptTask.run()` 会在**同一个实例**上按 `task_sequence_v`
# 顺序调用 `run_climb` / `run_rich_man` / `run_fakegod`。`run_climb` 曾经只把
# `_fatigue_owns_macro_idle` 置 True 而没有任何线切换时的恢复，于是「爬塔 → 伪神降临」
# 会让伪神线既拿不到 Fatigue 安全节点（climb-only），又被这个残留 flag 跳过 `random_sleep`
# —— 出现零 macro-idle owner。
#
# 下面的用例**一律不手工写 `_fatigue_owns_macro_idle`**：ownership 迁移必须完全由真实的
# `run_*` 入口调用链产生，断言落在真实 `prepare_next_action` 的 `random_sleep` 消费点上；
# 只 mock 页面图 / 导航 / 截图 / 识别 / 具体动作这些业务叶节点。
# --------------------------------------------------------------------------------------


class MacroIdleOwnershipLifecycleTest(TestCase):
    def _task(self, *, climb_sequence=()):
        """构造一个能真实跑三个 `run_*` 入口的最小实例（不预设 ownership flag）。"""
        t = ScriptTask.__new__(ScriptTask)
        t.conf = SimpleNamespace(general_config=SimpleNamespace(
            random_sleep=True,
            climb_sequence_v=tuple(climb_sequence),
        ))
        t.action_count = {'ap': 0, 'pass': 0, 'boss': 0, 'ap100': 0,
                          'fakegod': 0, 'rich_man': 0}
        t.current_action_type = ''
        t.activity_time_reached = False
        t.action_limit = Mock(return_value=10)
        t.time_limit_reached = Mock(return_value=False)
        # 业务叶节点：页面图 / 导航 / 截图 / 识别 / 具体动作
        t.setup_climb_pages = Mock()
        t.setup_fakegod_pages = Mock()
        t.setup_rich_man_pages = Mock()
        t.begin_fatigue_task = Mock()
        t.goto_page = Mock()
        t.screenshot = Mock()
        t.switch_soul_for_from_courtyard = Mock()
        t._sync_fakegod_team_lock = Mock()
        t._sync_climb_team_lock = Mock()
        t._sync_climb_penta_pass = Mock()
        t._sync_rich_man_team_lock = Mock(return_value=False)
        t.ui_reward_appear_click = Mock(return_value=False)
        t.appear_then_click = Mock(return_value=False)
        t.appear = Mock(return_value=True)
        t._boss_should_enter = Mock(return_value=False)
        t.device = SimpleNamespace(image='FRAME', stuck_record_clear=Mock(),
                                   stuck_record_add=Mock())
        t.O_CINQUE_COUNT = SimpleNamespace(ocr_digit=Mock(return_value=3))
        # 每条线跑到真实 `prepare_next_action` 之后就用既有的资源耗尽出口收尾，
        # 不需要真的执行一轮活动业务。
        t._run_fakegod_action = Mock(side_effect=ActivityResourceNotEnough)
        t._activity_challenge_safe_break = Mock(side_effect=ActivityResourceNotEnough)
        t._normalize_rich_man_dice_count = Mock(side_effect=ActivityResourceNotEnough)
        return t

    @staticmethod
    def _run_line(t, method_name, current_page):
        """真实调用某条玩法线入口，返回该线内 `random_sleep` 的调用次数。"""
        t.get_current_page = Mock(return_value=current_page)
        with patch('tasks.ActivityShikigami.base_act.random_sleep') as rs, \
                patch.object(normal_mod.time, 'sleep', Mock()), \
                patch('tasks.ActivityShikigami.activities.fake_god.time.sleep', Mock()), \
                patch('tasks.ActivityShikigami.activities.rich_man.time.sleep', Mock()):
            getattr(t, method_name)()
        return rs.call_count

    def test_case1_climb_then_fakegod_restores_random_sleep_owner(self):
        # CASE 1：同一实例 run_climb → run_fakegod，伪神线必须重新拿回 random_sleep owner。
        t = self._task()
        self._run_line(t, 'run_climb', as_page.page_climb_ap)
        calls = self._run_line(t, 'run_fakegod', as_page.page_fakegod_action)
        self.assertEqual(calls, 1)                       # 真实 prepare_next_action 里确实 idle 了
        self.assertFalse(t._fatigue_owns_macro_idle)     # 且 ownership 已由伪神线自己声明

    def test_case2_climb_then_rich_man_restores_random_sleep_owner(self):
        # CASE 2：同一实例 run_climb → run_rich_man，大富翁线同样必须拿回 random_sleep owner。
        t = self._task()
        self._run_line(t, 'run_climb', as_page.page_climb_ap)
        calls = self._run_line(t, 'run_rich_man', as_page.page_rich_man)
        self.assertEqual(calls, 1)
        self.assertFalse(t._fatigue_owns_macro_idle)

    def test_case3_climb_alone_keeps_fatigue_owner_without_random_sleep(self):
        # CASE 3：单独 run_climb —— Fatigue 持有 macro idle，真实 prepare_next_action
        # 绝不能再叠一层 random_sleep（两个 owner）。
        t = self._task(climb_sequence=('ap',))
        calls = self._run_line(t, 'run_climb', as_page.page_climb_ap)
        self.assertEqual(calls, 0)
        self.assertTrue(t._fatigue_owns_macro_idle)
        t.begin_fatigue_task.assert_called_once_with('ActivityShikigami')

    def test_case4_ownership_is_not_sticky_across_three_lines(self):
        # CASE 4：fakegod → climb → fakegod，ownership 必须能 False → True → False 往返，
        # 不是一旦被 climb 置 True 就粘住。
        t = self._task()
        first = self._run_line(t, 'run_fakegod', as_page.page_fakegod_action)
        self.assertEqual(first, 1)
        self.assertFalse(t._fatigue_owns_macro_idle)

        self._run_line(t, 'run_climb', as_page.page_climb_ap)
        self.assertTrue(t._fatigue_owns_macro_idle)

        third = self._run_line(t, 'run_fakegod', as_page.page_fakegod_action)
        self.assertEqual(third, 1)
        self.assertFalse(t._fatigue_owns_macro_idle)

    def test_every_activity_line_entry_declares_ownership(self):
        # 源码级护栏：三条线的入口都必须显式声明 owner，新增玩法线不得漏声明而继承残留值。
        self.assertIn('self._fatigue_owns_macro_idle = True', _src(NormalClimbAct.run_climb))
        for func in (RichManAct.run_rich_man, FakeGodAct.run_fakegod):
            self.assertIn('self._fatigue_owns_macro_idle = False', _src(func), func.__name__)


# --------------------------------------------------------------------------------------
# 6. 活动结算弹窗 drain —— 复用 random_default，有界，正向确认回挑战页
# --------------------------------------------------------------------------------------


class SettlementDrainTest(TestCase):
    def _t(self, *, page_seq, fire_seq, active_seq=None):
        p = patch.object(normal_mod, 'Timer', _FakeTimer)
        p.start()
        self.addCleanup(patch.stopall)
        patch.object(normal_mod.time, 'sleep', Mock()).start()
        patch.object(normal_mod, 'random_delay', Mock(return_value=0.4)).start()

        t = ScriptTask.__new__(ScriptTask)
        events = []
        t.I_ACT_FIRE = _img('I_ACT_FIRE')
        t.I_AS_BOSS_FIRE = _img('I_AS_BOSS_FIRE')
        t.SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)
        t.C_RANDOM_DEFAULT = SimpleNamespace(name='random_default', roi_front=(1, 2, 3, 4))
        t.screenshot = Mock()
        page_it = _tail(page_seq)
        fire_it = _tail(fire_seq)
        active_it = _tail(active_seq or [False])
        t.get_current_page = Mock(side_effect=lambda: next(page_it))
        t.appear = Mock(side_effect=lambda tg, **kw: next(fire_it))
        t._is_active_battle_entry = Mock(side_effect=lambda: next(active_it))
        t._sample_settlement_click = Mock(side_effect=lambda rule: events.append(('sample', rule.name)))
        return t, events

    def test_already_on_challenge_page_zero_clicks(self):
        t, events = self._t(page_seq=['DEST'], fire_seq=[True])
        self.assertIs(t._drain_activity_settlement('ap', 'DEST'), True)
        self.assertEqual(events, [])

    def test_popup_persists_bounded_and_uses_random_default(self):
        t, events = self._t(page_seq=[None], fire_seq=[False])
        self.assertIs(t._drain_activity_settlement('ap', 'DEST'), False)
        samples = [e for e in events if e[0] == 'sample']
        self.assertGreaterEqual(len(samples), 1)
        self.assertLessEqual(len(samples), ACTIVITY_SETTLEMENT_MAX_CLICKS)
        self.assertTrue(all(name == 'random_default' for _, name in samples))

    def test_popup_gone_but_not_on_challenge_page_not_immediate_true(self):
        # get_current_page None（弹窗消失但没回挑战页），fire 不可见 → 不算成功
        t, events = self._t(page_seq=[None, None], fire_seq=[False])
        self.assertIs(t._drain_activity_settlement('ap', 'DEST'), False)

    def test_battle_entry_re_detected_defers_without_random_default(self):
        t, events = self._t(page_seq=[None], fire_seq=[False], active_seq=[True])
        self.assertIs(t._drain_activity_settlement('ap', 'DEST'), False)
        self.assertEqual([e for e in events if e[0] == 'sample'], [])

    def test_reaches_challenge_page_after_a_few_clicks(self):
        t, events = self._t(page_seq=[None, None, 'DEST'], fire_seq=[False, False, True])
        self.assertIs(t._drain_activity_settlement('ap', 'DEST'), True)
        self.assertGreaterEqual(len([e for e in events if e[0] == 'sample']), 1)

    def test_source_reuses_settlement_owner_no_new_region(self):
        src = _src(NormalClimbAct._drain_activity_settlement)
        self.assertIn('self._sample_settlement_click(self.C_RANDOM_DEFAULT)', src)
        self.assertNotIn('random.randint', src)
        self.assertNotIn('RuleClick(', src)
        self.assertEqual((ACTIVITY_SETTLEMENT_MAX_CLICKS, ACTIVITY_SETTLEMENT_TIMEOUT), (6, 15))


# --------------------------------------------------------------------------------------
# 7. Cycle complete 边界 + repeat_completed 传递
# --------------------------------------------------------------------------------------


class CycleCompleteTest(TestCase):
    def test_run_climb_type_tracks_cycle_completed(self):
        src = _src(NormalClimbAct._run_climb_type)
        self.assertIn('cycle_completed = False', src)
        self.assertIn('repeat_completed=cycle_completed', src)
        # battle+settlement 或 一次完整 action 之后才置 True
        self.assertGreaterEqual(src.count('cycle_completed = True'), 2)
        # settlement drain 在 GeneralBattle 交接之后
        i_gb = src.index('run_general_battle(')
        i_drain = src.index('_drain_activity_settlement(')
        self.assertLess(i_gb, i_drain)

    def test_run_climb_action_drains_settlement_after_battle(self):
        src = _src(NormalClimbAct._run_climb_action)
        i_gb = src.index('run_general_battle(')
        i_drain = src.index('_drain_activity_settlement(')
        self.assertLess(i_gb, i_drain)


# --------------------------------------------------------------------------------------
# 8. 大富翁 / 伪神降临 + GeneralBattle 未改
# --------------------------------------------------------------------------------------


class RichManFakeGodUntouchedTest(TestCase):
    def test_rich_man_no_fire_or_fatigue_changes(self):
        from tasks.ActivityShikigami.activities import rich_man as rm
        src = _src(rm)
        self.assertNotIn('try_fatigue_break', src)
        self.assertNotIn('_is_active_battle_entry', src)
        self.assertNotIn('REACTION_FIRE', src)
        self.assertNotIn('_drain_activity_settlement', src)

    def test_fake_god_no_fire_or_fatigue_changes(self):
        from tasks.ActivityShikigami.activities import fake_god as fg
        src = _src(fg)
        self.assertNotIn('try_fatigue_break', src)
        self.assertNotIn('REACTION_FIRE', src)
        self.assertNotIn('_drain_activity_settlement', src)
        # 伪神降临自己的保底点击器仍是原样（本轮明确不动）
        self.assertIn('def _enter_fakegod_battle', src)
        self.assertIn('while True', src)

    def test_general_battle_settlement_v3_core_untouched(self):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        src = _src(GeneralBattle._settlement_click)
        self.assertIn('self.C_RANDOM_DEFAULT', src)
        # ActivityShikigami 只是复用，没有改 GeneralBattle 的 region 选择 / 采样
        self.assertIn('ClickSampler.sample_region', _src(GeneralBattle._sample_settlement_click))

    def test_base_act_handle_result_still_calls_super(self):
        self.assertIn('super()._handle_result(context, config)', _src(BaseAct._handle_result))


# --------------------------------------------------------------------------------------
# AST 冒烟：3 个改动文件可解析
# --------------------------------------------------------------------------------------


class ParseSmokeTest(TestCase):
    def test_modules_parse(self):
        for mod in (normal_mod, as_page):
            ast.parse(inspect.getsource(mod))
        import tasks.ActivityShikigami.base_act as ba
        ast.parse(inspect.getsource(ba))
