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
from module.click_pipeline import FinalPoint
from module.exception import GamePageUnknownError
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from module.reaction_profile import REACTION_FIRE, REACTION_NAVIGATION
from tasks.ActivityShikigami import page as as_page
from tasks.ActivityShikigami.activities import normal as normal_mod
from tasks.ActivityShikigami.activities.normal import (
    ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT,
    ACTIVITY_SETTLEMENT_REACTION,
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
# 1.1 find_activity_entry 旧栏目切换回退：真实驱动（2026-09-22 导航停滞事故收尾）
# --------------------------------------------------------------------------------------


class _EntryFallbackTask:
    """驱动 `find_activity_entry` 的最小假体：只有调用 `screenshot()` 才会前进到脚本里的
    下一帧，`appear()` / `appear_then_click()` 都读「当前帧」——不使用真实设备，帧序列由测试
    显式给出，用来精确验证「点击后复用同一帧、不额外截图」这条语义。"""

    def __init__(self, frames, screenshot_side_effect=None):
        # frames: 每帧一个 dict，键 'main' / 'toggle' / 'entry' 分别对应
        # I_CHECK_MAIN / I_TOGGLE_BUTTON / 新旧入口图标任一，缺省为 False（main 缺省 True）。
        self.frames = frames
        self.frame_index = -1  # 尚未截过图；第一次 screenshot() 才推进到 frames[0]
        self.screenshot_calls = 0
        self.click_calls = 0
        from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
        self.I_CHECK_MAIN = _img('I_CHECK_MAIN')
        self._entry_names = {ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2.name,
                             ActivityShikigamiAssets.I_MAIN_GOTO_ACT.name}
        from tasks.Component.RightActivity.assets import RightActivityAssets
        self._toggle_name = RightActivityAssets.I_TOGGLE_BUTTON.name
        self._screenshot_side_effect = screenshot_side_effect

    def _frame(self):
        idx = max(0, min(self.frame_index, len(self.frames) - 1))
        return self.frames[idx]

    def screenshot(self):
        self.screenshot_calls += 1
        if self._screenshot_side_effect is not None:
            self._screenshot_side_effect(self.screenshot_calls)
        if self.frame_index < len(self.frames) - 1:
            self.frame_index += 1

    def appear(self, target, **kw):
        frame = self._frame()
        if target is self.I_CHECK_MAIN:
            return frame.get('main', True)
        if target.name == self._toggle_name:
            return frame.get('toggle', False)
        if target.name in self._entry_names:
            return frame.get('entry', False)
        return False

    def appear_then_click(self, target, **kw):
        if self.appear(target, **kw):
            self.click_calls += 1
            return True
        return False


def _drive_find_activity_entry(frames, screenshot_side_effect=None, timeout_budget=None):
    """在打了 `time.sleep` / `Timer` 补丁的环境下驱动一次 `find_activity_entry`，
    返回 (结果或异常, task 假体)。`_FakeTimer.budget` 是跨测试共享的类属性（其它测试类，
    如 `SettlementDrainTest`，也复用同一个假体并依赖默认值 6），这里必须显式保存 / 还原，
    不能只改不还，否则会污染同一进程里其它测试的结果。"""
    task = _EntryFallbackTask(frames, screenshot_side_effect)
    original_budget = _FakeTimer.budget
    _FakeTimer.budget = timeout_budget if timeout_budget is not None else 10_000  # 默认不触发墙钟
    try:
        with patch.object(as_page, 'time') as fake_time, patch.object(as_page, 'Timer', _FakeTimer):
            fake_time.sleep = Mock()
            try:
                result = as_page.find_activity_entry(task)
            except Exception as exc:  # noqa: BLE001 —— 测试需要拿到异常本身
                return exc, task
            return result, task
    finally:
        _FakeTimer.budget = original_budget


class FindActivityEntryFallbackDriverTest(TestCase):
    """真实驱动 `find_activity_entry`（不是只读源码字符串），覆盖切换成功 / 始终找不到 /
    墙钟超时 / 截图异常 / 二次确认失败 / 截图次数这几类场景。"""

    def test_toggle_appears_and_entry_shows_up_immediately_after_click(self):
        # 第 1 帧：main 可见、entry 不可见、toggle 可见；点击后取的新帧（第 2 帧）entry 已出现。
        frames = [
            {'main': True, 'toggle': True, 'entry': False},
            {'main': True, 'toggle': True, 'entry': True},
        ]
        result, task = _drive_find_activity_entry(frames)
        self.assertIs(result, True)
        self.assertEqual(task.click_calls, 1)
        # 截图次数：循环顶 1 次 + settle 前置确认 1 次 + 点击后新帧 1 次 = 3 次，
        # 不会再等下一轮循环顶部又截一次图。
        self.assertEqual(task.screenshot_calls, 3)

    def test_entry_never_appears_raises_after_max_tries(self):
        frames = [{'main': True, 'toggle': True, 'entry': False}]
        result, task = _drive_find_activity_entry(frames)
        self.assertIsInstance(result, as_page.GamePageUnknownError)
        # 8 次循环上限，每次都点一次（toggle 一直可见、点击一直成功）
        self.assertEqual(task.click_calls, as_page.ACTIVITY_COLUMN_SWITCH_MAX_TRIES)

    def test_toggle_never_visible_still_bounded_and_raises(self):
        frames = [{'main': True, 'toggle': False, 'entry': False}]
        result, task = _drive_find_activity_entry(frames)
        self.assertIsInstance(result, as_page.GamePageUnknownError)
        self.assertEqual(task.click_calls, 0)

    def test_wall_clock_budget_exhausted_exits_without_reaching_max_tries(self):
        # 墙钟只给 2 次「reached() 检查」的预算（第 3 次调用即到期），
        # 循环上限是 8 次——必须是墙钟先生效，而不是等到数第 8 次。
        frames = [{'main': True, 'toggle': True, 'entry': False}]
        result, task = _drive_find_activity_entry(frames, timeout_budget=2)
        self.assertIsInstance(result, as_page.GamePageUnknownError)
        self.assertIn('fallback timeout', str(result))
        self.assertLess(task.click_calls, as_page.ACTIVITY_COLUMN_SWITCH_MAX_TRIES)

    def test_screenshot_exception_propagates_not_swallowed(self):
        # 截图本身抛异常：不得被吞掉伪装成「未找到」，也不能在这里被重试成死循环。
        def boom(n):
            if n == 1:
                raise RuntimeError('device screenshot failed')

        frames = [{'main': True, 'toggle': True, 'entry': False}]
        result, task = _drive_find_activity_entry(frames, screenshot_side_effect=boom)
        self.assertIsInstance(result, RuntimeError)
        self.assertEqual(task.screenshot_calls, 1)

    def test_toggle_disappears_during_settle_no_click_no_false_success(self):
        # 第 1 帧 toggle 可见触发 settle；settle 内部会再截一次图，那张帧（第 2 帧）toggle 已消失，
        # `appear_then_click` 因此返回 False——不能点旧坐标，也不能把这一轮算成切换成功。
        frames = [
            {'main': True, 'toggle': True, 'entry': False},
            {'main': True, 'toggle': False, 'entry': False},
        ]
        result, task = _drive_find_activity_entry(frames, timeout_budget=3)
        self.assertIsInstance(result, as_page.GamePageUnknownError)
        self.assertEqual(task.click_calls, 0)

    def test_no_click_path_does_not_take_the_post_click_screenshot(self):
        # toggle 全程不可见：每轮只在循环顶截一次图，没有 settle、也没有点击后的额外截图。
        # `_FakeTimer(budget=3)` 前 3 次 reached() 为 False、第 4 次才 True，
        # 对应恰好跑满 3 轮循环顶截图后墙钟生效。
        frames = [{'main': True, 'toggle': False, 'entry': False}]
        result, task = _drive_find_activity_entry(frames, timeout_budget=3)
        self.assertIsInstance(result, as_page.GamePageUnknownError)
        self.assertEqual(task.screenshot_calls, 3)
        self.assertEqual(task.click_calls, 0)

    def test_click_still_goes_through_appear_then_click_not_bare_device_click(self):
        body = _body(as_page.find_activity_entry)
        self.assertIn('appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON', body)
        self.assertNotIn('device.click(', body)


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

    # ------------------------------------------------------------------------------------
    # 2026-09-22 真机事故复现：page_climb_pass（真实挑战页）持续被识别到，但挑战键还没渲染
    # 出来——旧代码把这当成「还有残留弹窗」连点 6 次 random_default；新代码必须改为有界等待，
    # 不盲点。
    # ------------------------------------------------------------------------------------

    def test_incident_destination_recognized_but_fire_never_ready_zero_blind_clicks(self):
        """复现真机日志：`[UI] page_climb_pass` 连续出现、`I_ACT_FIRE` 全程不可见。
        修复前会产生 6 次 `random_default` 点击；修复后必须是 0 次——因为一旦确认已经在
        `destination` 结构页面上，就不再进入盲点分支，只反复有界等待挑战键。"""
        t, events = self._t(page_seq=['DEST'], fire_seq=[False])  # 全程即 destination，fire 恒 False
        result = t._drain_activity_settlement('ap', 'DEST')
        samples = [e for e in events if e[0] == 'sample']
        self.assertEqual(samples, [])  # 事故复现的核心断言：零次盲点
        self.assertIs(result, False)   # 有界超时后仍未 ready，如实返回 False（不伪造成功）

    def test_destination_recognized_fire_not_ready_waits_not_clicks_immediately(self):
        """`page_climb_pass` 已经命中但挑战键第一帧还没出来：必须先等（`_wait_climb_fire_state`），
        不能立即当成弹窗点 random_default。"""
        t, events = self._t(page_seq=['DEST'], fire_seq=[False, False, True])
        result = t._drain_activity_settlement('ap', 'DEST')
        self.assertIs(result, True)
        self.assertEqual([e for e in events if e[0] == 'sample'], [])

    def test_battle_re_entered_while_waiting_for_fire_defers_without_click(self):
        """在「已到 destination、等挑战键」期间又被判定成重新进入战斗：按既有约定交回外层，
        不在这里点 random_default。"""
        t, events = self._t(page_seq=['DEST'], fire_seq=[False],
                            active_seq=[False, False, True])
        result = t._drain_activity_settlement('ap', 'DEST')
        self.assertIs(result, False)
        self.assertEqual([e for e in events if e[0] == 'sample'], [])

    def test_genuine_lingering_popup_still_uses_bounded_blind_click(self):
        """真正的残留弹窗场景（未到 destination）行为不变：仍然有界盲点，不因本轮修复被误伤。"""
        t, events = self._t(page_seq=[None, None, 'DEST'], fire_seq=[False, False, True])
        result = t._drain_activity_settlement('ap', 'DEST')
        self.assertIs(result, True)
        samples = [e for e in events if e[0] == 'sample']
        self.assertGreaterEqual(len(samples), 1)
        self.assertLessEqual(len(samples), ACTIVITY_SETTLEMENT_MAX_CLICKS)

    def test_screenshot_exception_during_drain_propagates(self):
        """截图异常不能被吞掉、也不能触发无限重试。"""
        t, events = self._t(page_seq=['DEST'], fire_seq=[False])
        t.screenshot = Mock(side_effect=RuntimeError('device screenshot failed'))
        with self.assertRaises(RuntimeError):
            t._drain_activity_settlement('ap', 'DEST')

    def test_wait_branch_reuses_existing_fire_state_helper_not_new_click_path(self):
        """源码级护栏：等待分支必须复用既有的 `_wait_climb_fire_state`，不引入新的点击方式、
        不新增裸 `device.click`。"""
        src = _src(NormalClimbAct._drain_activity_settlement)
        self.assertIn('self._wait_climb_fire_state(fire_rule)', src)
        self.assertNotIn('device.click(', src)
        # 盲点分支只有一处 _sample_settlement_click 调用，等待分支不额外叠加点击
        self.assertEqual(src.count('self._sample_settlement_click('), 1)


# --------------------------------------------------------------------------------------
# 6.1 `_run_climb_type` 主循环：持续无法识别页面时的有界退出（2026-09-22 真机事故）
#
# 事故复现里 `_drain_activity_settlement` 的兜底点击耗尽后返回 False，外层 `_run_climb_type`
# 忽略返回值、回到循环顶部重新截图判页；若页面此后持续无法归类（`get_current_page()` 一直
# None），旧代码在这里只有 `sleep(0.5); continue`，没有任何上限——真机日志显示这之后进程
# 静默运行了数十分钟没有一行输出，直至被外部重启。
# --------------------------------------------------------------------------------------


class ClimbTypeUnknownPageTest(TestCase):
    def _t(self, *, page_seq, timeout_budget=None):
        original_budget = _FakeTimer.budget
        _FakeTimer.budget = timeout_budget if timeout_budget is not None else 10_000
        self.addCleanup(lambda: setattr(_FakeTimer, 'budget', original_budget))
        patch.object(normal_mod, 'Timer', _FakeTimer).start()
        self.addCleanup(patch.stopall)
        patch.object(normal_mod.time, 'sleep', Mock()).start()

        t = ScriptTask.__new__(ScriptTask)
        page_it = _tail(page_seq)
        t.get_current_page = Mock(side_effect=lambda: next(page_it))
        t.screenshot = Mock()
        t.current_action_type = ''
        t.goto_page = Mock()
        t._sync_climb_team_lock = Mock()
        t.click = Mock()
        return t

    def test_persistent_unknown_page_raises_after_bounded_wait(self):
        """事故复现：页面持续无法识别，必须有界抛出 `GamePageUnknownError`，
        不能静默空转。"""
        t = self._t(page_seq=[None], timeout_budget=3)
        with self.assertRaises(GamePageUnknownError):
            t._run_climb_type('pass')
        # 有界：截图次数不会无限增长
        self.assertLess(t.screenshot.call_count, 20)

    def test_recovery_resets_the_unknown_page_budget(self):
        """每次 None 后紧跟着识别到已知页面（这里用 page_reward 作最轻量的已知页分支），
        未知页计时必须被清空——不能把多次分散的短暂 None 累加成一次超时。"""
        t = self._t(page_seq=[None, as_page.page_reward] * 20, timeout_budget=1)
        calls = {'n': 0}

        def _click(*a, **kw):
            calls['n'] += 1
            if calls['n'] >= 5:
                raise StopIteration('probe stop: reached here without GamePageUnknownError')

        t.click = Mock(side_effect=_click)
        with self.assertRaises(StopIteration):
            t._run_climb_type('pass')

    def test_brief_single_unknown_frame_does_not_raise_immediately(self):
        """只出现一次 None 就立即恢复：不能因为一帧过渡就误判超时。"""
        t = self._t(page_seq=[None, as_page.page_reward], timeout_budget=1)
        calls = {'n': 0}

        def _click(*a, **kw):
            calls['n'] += 1
            raise StopIteration('probe stop: single None frame did not raise')

        t.click = Mock(side_effect=_click)
        with self.assertRaises(StopIteration):
            t._run_climb_type('pass')

    def test_screenshot_exception_in_climb_type_propagates(self):
        t = self._t(page_seq=[None])
        t.screenshot = Mock(side_effect=RuntimeError('device screenshot failed'))
        with self.assertRaises(RuntimeError):
            t._run_climb_type('pass')

    def test_source_uses_bounded_timer_not_bare_sleep_loop(self):
        src = _src(NormalClimbAct._run_climb_type)
        self.assertIn('Timer(ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT)', src)
        self.assertIn('raise GamePageUnknownError', src)
        self.assertEqual(ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT, 20)


# --------------------------------------------------------------------------------------
# 6.2 爬塔线专用结算单击（2026-09-23）：取消 Micro-Burst 连击，70/30 activity region，
# reaction + fresh confirm + 单击，不预授权第二击、不复用上一击 anchor。
# --------------------------------------------------------------------------------------


class ActivitySettlementSingleClickTest(TestCase):
    def _t(self, *, owns=True, action_type='pass', generic_result=True,
           classify_seq=None, current_page_seq=None, fire_seq=None,
           over_ghost=False, skin_confirm=False, is_false=False):
        patch.object(normal_mod.time, 'sleep', Mock()).start()
        self.addCleanup(patch.stopall)

        t = ScriptTask.__new__(ScriptTask)
        events = []
        t._climb_owns_settlement_single_click = owns
        t.current_action_type = action_type
        t.device = SimpleNamespace(image='F', click_record_clear=Mock(side_effect=lambda: events.append('clear')))
        t.I_FALSE = _img('I_FALSE')
        t.I_OVER_GHOST = _img('I_OVER_GHOST')
        t.I_GB_SKIN_CONFIRM = _img('I_GB_SKIN_CONFIRM')
        t.I_ACT_FIRE = _img('I_ACT_FIRE')
        t.I_AS_BOSS_FIRE = _img('I_AS_BOSS_FIRE')
        t.I_UI_BACK_RED = _img('I_UI_BACK_RED')
        t.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        t.appear = Mock(side_effect=lambda tg, **kw: {
            'I_FALSE': is_false,
        }.get(tg.name, next(_tail(fire_seq or [False]))
              if tg.name in ('I_ACT_FIRE', 'I_AS_BOSS_FIRE') else False))
        t.appear_then_click = Mock(side_effect=lambda tg, **kw: {
            'I_OVER_GHOST': over_ghost, 'I_GB_SKIN_CONFIRM': skin_confirm,
        }.get(tg.name, False))
        t._is_generic_result_context = Mock(return_value=generic_result)
        classify_it = _tail(classify_seq if classify_seq is not None else [as_page.page_reward])
        t._classify_general_battle_page = Mock(side_effect=lambda: next(classify_it))
        page_it = _tail(current_page_seq if current_page_seq is not None else [None])
        t.get_current_page = Mock(side_effect=lambda: next(page_it))
        t._sample_settlement_point = Mock(
            side_effect=lambda region: (events.append(('sample', region.name)), (321, 654))[1])
        t.events = events
        return t

    # ---- 70/30 region 选择 ----

    def test_seventy_percent_branch_picks_activity_1(self):
        from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
        t = self._t()
        with patch.object(normal_mod, 'random_int', return_value=70):  # <=70 命中
            region = t._select_activity_settlement_region()
        self.assertIs(region, GeneralBattleAssets.C_RANDOM_ACTIVITY_1)

    def test_thirty_percent_branch_picks_activity_2(self):
        from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
        t = self._t()
        with patch.object(normal_mod, 'random_int', return_value=71):  # >70 命中
            region = t._select_activity_settlement_region()
        self.assertIs(region, GeneralBattleAssets.C_RANDOM_ACTIVITY_2)

    def test_never_falls_back_to_default_or_save_regions(self):
        from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
        t = self._t()
        seen = set()
        for roll in (1, 50, 70, 71, 99, 100):
            with patch.object(normal_mod, 'random_int', return_value=roll):
                seen.add(t._select_activity_settlement_region().name)
        self.assertEqual(seen, {'random_activity_1', 'random_activity_2'})
        forbidden = {GeneralBattleAssets.C_RANDOM_DEFAULT.name,
                    GeneralBattleAssets.C_RANDOM_SAVE_RIGHT.name,
                    GeneralBattleAssets.C_RANDOM_SAVE_BOTTOM.name}
        self.assertFalse(seen & forbidden)

    def test_region_selection_uses_project_system_random_not_new_rng(self):
        src = _src(NormalClimbAct._select_activity_settlement_region)
        self.assertIn('random_int(1, 100)', src)
        self.assertNotIn('random.Random(', src)
        self.assertNotIn('import random', src)

    # ---- reaction owner：本线独立常量，不借用 Micro-Burst 的 observe 间隔 ----

    def test_reaction_range_is_task_local_and_exactly_0_45_to_0_85(self):
        self.assertEqual(ACTIVITY_SETTLEMENT_REACTION, (0.45, 0.85))

    def test_transaction_reads_task_local_reaction_not_general_battle_burst_interval(self):
        body = _body(NormalClimbAct._activity_settlement_single_click)
        self.assertIn('random_delay(*ACTIVITY_SETTLEMENT_REACTION)', body)
        # 代码体（不含解释用的 docstring）里不得再引用 Micro-Burst 的 observe 间隔
        self.assertNotIn('SETTLEMENT_BURST_CLICK_INTERVAL_RANGE', body)

    def test_reaction_is_sampled_from_the_task_local_range_at_runtime(self):
        t = self._t(classify_seq=[as_page.page_reward])
        with patch.object(normal_mod, 'execute_single_click'), \
                patch.object(normal_mod, 'random_delay', return_value=0.5) as delay:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        delay.assert_called_once_with(*ACTIVITY_SETTLEMENT_REACTION)

    def test_call_order_is_reaction_sleep_screenshot_confirm_then_sample_then_click(self):
        """顺序必须是 reaction → sleep → fresh screenshot → 确认 → 选区采样 → 单击；
        绝不能先采样坐标再跨等待复用（那样等于回到 anchor 预授权的老毛病）。"""
        t = self._t(classify_seq=[as_page.page_reward])
        ev = t.events
        with patch.object(normal_mod, 'random_delay',
                          side_effect=lambda *a: ev.append(('random_delay', a)) or 0.5), \
                patch.object(normal_mod.time, 'sleep',
                             side_effect=lambda s: ev.append(('sleep', s))), \
                patch.object(normal_mod, 'execute_single_click',
                             side_effect=lambda *a, **kw: ev.append('click')):
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        kinds = [e[0] if isinstance(e, tuple) else e for e in ev]
        self.assertEqual(kinds, ['random_delay', 'sleep', 'screenshot', 'sample', 'click'])
        # sleep 睡的就是本层 reaction 采样出来的值，不是另一个来源
        self.assertEqual([e for e in ev if e[0] == 'sleep'], [('sleep', 0.5)])
        self.assertEqual([e[1] for e in ev if e[0] == 'random_delay'],
                         [ACTIVITY_SETTLEMENT_REACTION])

    def test_single_reaction_layer_no_policy_no_confirm_delay(self):
        t = self._t(classify_seq=[as_page.page_reward])
        with patch.object(normal_mod, 'execute_single_click'), \
                patch.object(normal_mod, 'random_delay', return_value=0.5) as delay, \
                patch.object(normal_mod.time, 'sleep') as slept:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        self.assertEqual(delay.call_count, 1)   # 整条链路只有一层 reaction
        self.assertEqual(slept.call_count, 1)
        body = _body(NormalClimbAct._activity_settlement_single_click)
        for forbidden in ('policy=', 'InteractionPolicy', 'confirm_delay', 'appear_then_click'):
            self.assertNotIn(forbidden, body)

    def test_general_battle_micro_burst_interval_is_independent_of_this_line(self):
        """两套 timing 完全独立：GeneralBattle 的 burst observe 间隔（2026-09-23 起
        `(0.30, 0.60)`）与本线专用 reaction `(0.45, 0.85)` 各调各的，互不牵连。"""
        self.assertEqual(GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE, (0.30, 0.60))
        self.assertNotEqual(GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE,
                            ACTIVITY_SETTLEMENT_REACTION)
        self.assertIn('self._sample_interval(self.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)',
                      _src(GeneralBattle._fire_settlement_burst))

    # ---- 单次事务：至多 1 次 execute_single_click ----

    def test_transaction_executes_at_most_one_click(self):
        t = self._t(classify_seq=[as_page.page_reward])
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        self.assertEqual(click.call_count, 1)
        self.assertEqual(len([e for e in t.events if e == 'screenshot']), 1)

    def test_click_uses_final_point_from_fresh_sample_not_bare_coords(self):
        t = self._t(classify_seq=[as_page.page_reward])
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        args, kwargs = click.call_args
        self.assertEqual(args[0], t.device)
        self.assertIsInstance(args[1], FinalPoint)
        self.assertEqual((args[1].x, args[1].y), (321, 654))

    def test_second_click_requires_a_brand_new_transaction_not_reused_anchor(self):
        """两次独立调用（模拟仍需处理结算的下一帧）必须各自重新 reaction + fresh confirm +
        70/30 选择 + 重新采样，不得复用上一次的 anchor / region 选择。"""
        t = self._t(classify_seq=[as_page.page_reward, as_page.page_reward])
        rolls = iter([10, 90])  # 第一次 <=70 命中 activity_1，第二次 >70 命中 activity_2
        with patch.object(normal_mod, 'execute_single_click') as click, \
                patch.object(normal_mod, 'random_int', side_effect=lambda *a: next(rolls)):
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        self.assertEqual(click.call_count, 2)
        samples = [e for e in t.events if e[0] == 'sample']
        self.assertEqual([n for _, n in samples], ['random_activity_1', 'random_activity_2'])
        # 两次各自独立截图确认，不是一次截图服务两次点击
        self.assertEqual(len([e for e in t.events if e == 'screenshot']), 2)

    # ---- 状态门控：page_climb_pass / I_ACT_FIRE 出现即停止 ----

    def test_climb_destination_page_appeared_zero_clicks(self):
        t = self._t(action_type='pass', current_page_seq=[as_page.page_climb_pass])
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        click.assert_not_called()
        self.assertEqual([e for e in t.events if e[0] == 'sample'], [])

    def test_fire_button_appeared_zero_clicks(self):
        t = self._t(action_type='pass', current_page_seq=[None], fire_seq=[True])
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        click.assert_not_called()

    def test_state_unclear_waits_no_click(self):
        """既未到挑战页/挑战键，结算页分类又已经变化（既非原来的 current_page 也非明确的
        新结算态）：视为状态不明确，不点。"""
        t = self._t(current_page_seq=[None], fire_seq=[False],
                    classify_seq=[None])  # 分类不再等于 current_page=page_reward
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        click.assert_not_called()

    def test_climb_settlement_should_stop_ignored_for_non_climb_action_type(self):
        """防御性判断：非爬塔 action_type 不应该被 `_climb_settlement_should_stop` 拦下
        （正常情况下大富翁/伪神降临不会走到这个函数，由 owns 门控保证）。"""
        t = self._t(action_type='rich_man')
        self.assertFalse(t._climb_settlement_should_stop())

    # ---- _handle_result / _handle_reward 门控 + 事故复现 ----

    def test_owns_false_falls_back_to_generalbattle_micro_burst(self):
        """大富翁/伪神降临（owns=False）：必须原样回落到 GeneralBattle 的 Micro-Burst，
        不受本轮改造影响。"""
        t = self._t(owns=False)
        with patch.object(GeneralBattle, '_handle_result', return_value='super_result') as sup:
            result = NormalClimbAct._handle_result(t, SimpleNamespace(), SimpleNamespace())
        self.assertEqual(result, 'super_result')
        sup.assert_called_once()

    def test_owns_true_reward_page_uses_single_click_not_burst(self):
        t = self._t(owns=True, classify_seq=[as_page.page_reward])
        context = SimpleNamespace(last_page=None, is_win=None, reward_no_battle_ts=1.0)
        with patch.object(normal_mod, 'execute_single_click') as click:
            action = t._handle_reward(context, SimpleNamespace())
        self.assertEqual(action, BattleAction.CONTINUE)
        self.assertTrue(context.is_win)
        self.assertIsNone(context.reward_no_battle_ts)
        self.assertEqual(click.call_count, 1)

    def test_owns_true_boss_result_still_clicks_back_red_popup(self):
        """回归防护：迁移到单击结算后，boss 结算前的专属附属弹窗点击不能丢。"""
        t = self._t(owns=True, action_type='boss', classify_seq=[as_page.page_battle_result])
        context = SimpleNamespace(last_page=None, is_win=None, reward_no_battle_ts=1.0)
        with patch.object(normal_mod, 'execute_single_click'):
            t._handle_result(context, SimpleNamespace())
        clicks = [c for c in t.appear_then_click.call_args_list if c.args[0].name == 'I_UI_BACK_RED']
        self.assertEqual(len(clicks), 1)

    def test_over_ghost_popup_still_short_circuits_before_settlement_click(self):
        t = self._t(owns=True, over_ghost=True)
        context = SimpleNamespace(last_page=None, is_win=None, reward_no_battle_ts=1.0)
        with patch.object(normal_mod, 'execute_single_click') as click:
            action = t._handle_reward(context, SimpleNamespace())
        self.assertEqual(action, BattleAction.CONTINUE)
        click.assert_not_called()

    def test_incident_reward_click_dismisses_immediately_then_second_click_gets_fresh_transaction(self):
        """复现用户描述的「Reward → 点击 → 弹窗瞬间消失 → 第二击穿透到底层活动页面」：
        第一次调用点击后，若结算已经消失（分类不再是 page_reward），第二次独立调用
        必须先重新 reaction + fresh confirm，发现真实挑战页已出现就直接放弃，不再点。"""
        t = self._t(action_type='pass', classify_seq=[as_page.page_reward],
                    current_page_seq=[None, as_page.page_climb_pass])
        with patch.object(normal_mod, 'execute_single_click') as click:
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
            t._activity_settlement_single_click(SimpleNamespace(), current_page=as_page.page_reward)
        self.assertEqual(click.call_count, 1)  # 只有第一次真正点了

    def test_source_no_bare_device_click_no_micro_burst_call(self):
        for func in (NormalClimbAct._handle_result, NormalClimbAct._handle_reward,
                    NormalClimbAct._activity_settlement_single_click):
            src = _src(func)
            self.assertNotIn('device.click(', src)
            self.assertNotIn('_settlement_burst_step(', src)
            self.assertNotIn('_fire_settlement_burst(', src)


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
