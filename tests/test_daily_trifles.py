# This Python file uses the following encoding: utf-8
"""每日琐事（DailyTrifles）：吉闻领奖与关闭位置、庭院事务多轮领取（照 synevo）、各子项的完成记录与循环上限。

用假界面驱动真实的 `ScriptTask` 方法：画面上有哪些资产按身份记在集合里，每次点击按场景规则改变画面；
`goto_page` 是替身，配置用真实的 `DailyTrifles()` 模型，计时常量在实例上调小。所有循环都有上限，挂死会变成超时失败。
"""

import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from module.interaction_policy import InteractionPolicy as P
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.DailyTrifles.config import DailyTrifles
from tasks.DailyTrifles.page import page_friends_luck, page_store_gift_room
from tasks.DailyTrifles.script_task import ScriptTask
from tasks.GameUi.page import page_courtyard_affairs, page_main, page_mall
from tasks.Restart.assets import RestartAssets
from tasks.WeeklyPurchase.assets import WeeklyPurchaseAssets

T = ScriptTask
BOTTOM = GeneralBattleAssets.C_RANDOM_BOTTOM


class FakeUi:
    """画面 = 当前可见资产的集合；`on_click[rule]` 决定点击后画面怎么变；`events` 是按时间出现的画面变化。"""

    def __init__(self, visible=()):
        self.visible = {id(r) for r in visible}
        self.on_click = {}
        self.on_page = {}
        self.events = []        # [(到期时间, 回调)]
        self.clicks = []
        self.policies = []      # [(点击的规则, L2 档位)]
        self.pages = []
        self.shots = 0

    def show(self, *rules):
        self.visible |= {id(r) for r in rules}

    def hide(self, *rules):
        self.visible -= {id(r) for r in rules}

    def later(self, delay, fn):
        self.events.append((time.monotonic() + delay, fn))

    def screenshot(self):
        self.shots += 1
        assert self.shots < 20000, 'too many screenshots, loop is not bounded'
        now = time.monotonic()
        due = [e for e in self.events if e[0] <= now]
        self.events = [e for e in self.events if e[0] > now]
        for _, fn in due:
            fn()
        time.sleep(0.002)

    def appear(self, rule, interval=None, threshold=None):
        return id(rule) in self.visible

    def click(self, rule, interval=None, policy=None):
        self.clicks.append(rule)
        self.policies.append((rule, policy))
        fn = self.on_click.get(id(rule))
        if fn:
            fn()
        return True

    def appear_then_click(self, rule, action=None, interval=None, threshold=None, policy=None, **_):
        if id(rule) not in self.visible:
            return False
        self.click(action or rule, policy=policy)
        return True

    def goto_page(self, page, **_):
        self.pages.append(page)
        fn = self.on_page.get(id(page))
        if fn:
            fn()
        return True

    def clicked(self, rule):
        return sum(1 for r in self.clicks if r is rule)

    def policies_of(self, rule):
        return {p for r, p in self.policies if r is rule}


def make_task(ui: FakeUi, **consts):
    t = T.__new__(T)
    t.config = SimpleNamespace(daily_trifles=DailyTrifles(), save=Mock(), notifier=Mock())
    t.screenshot = ui.screenshot
    t.appear = ui.appear
    t.click = ui.click
    t.appear_then_click = ui.appear_then_click
    t.goto_page = ui.goto_page
    t.swipe = Mock(name='swipe')
    t.interval_timer = {}
    small = dict(LUCK_IDLE=1.0, LUCK_TIMEOUT=5, LUCK_REWARD_CLOSE_TIMEOUT=1, COURTYARD_ENTRY_WAIT=0.5,
                 COURTYARD_TAB_TIMEOUT=0.5, COURTYARD_REWARD_TIMEOUT=0.5, COURTYARD_COMPLETE_WAIT=0.2,
                 COURTYARD_BUTTON_WAIT=1.5,
                 SWITCH_TIMEOUT=0.3, STORE_SIGN_WAIT=0.3, SUSHI_ENTER_TIMEOUT=0.3, SUSHI_BUY_TIMEOUT=0.3,
                 RECALL_STEP_TIMEOUT=0.3, SUSHI_FIND_WAIT=0.3)
    small.update(consts)
    for k, v in small.items():
        setattr(t, k, v)
    return t


def record(t):
    return t.config.daily_trifles.done_record


def is_today(dt):
    return dt.date() == datetime.today().date()


class LuckMsgTest(unittest.TestCase):
    def world(self, reward_delay=0.7, button_delay=0.6):
        """一键祝福 → 点击祝福 → 奖励晚一点出来；点下方空白关掉奖励，点 C_UI_REWARD 会点到道具（奖励不关）。"""
        ui = FakeUi()
        ui.later(button_delay, lambda: ui.show(T.I_ONE_CLICK_BLESS))

        def one_click():
            ui.hide(T.I_ONE_CLICK_BLESS)
            ui.show(T.I_CLICK_BLESS)

        def bless():
            ui.hide(T.I_CLICK_BLESS)
            ui.later(reward_delay, lambda: ui.show(T.I_UI_REWARD))

        ui.on_click[id(T.I_ONE_CLICK_BLESS)] = one_click
        ui.on_click[id(T.I_CLICK_BLESS)] = bless
        ui.on_click[id(BOTTOM)] = lambda: ui.hide(T.I_UI_REWARD)
        return ui

    def test_reward_that_comes_after_the_last_click_is_still_collected(self):
        # 按钮 0.6 秒才出来、奖励在最后一次点击后 0.7 秒才出来：旧写法从开始计 2 秒（这里 1 秒）就走了
        ui = self.world()
        t = make_task(ui)
        t.run_luck_msg()
        self.assertTrue(is_today(record(t).luck_msg_dt))
        self.assertEqual(ui.clicked(BOTTOM), 1)
        self.assertEqual(ui.clicked(T.C_UI_REWARD), 0)       # 公共关闭区域会点到奖励里的道具
        self.assertNotIn(id(T.I_UI_REWARD), ui.visible)      # 离开前奖励框已经关掉

    def test_no_luck_msg_after_a_normal_check_is_recorded_and_ends_quickly(self):
        # 2026-10-26 业务口径：正常检查后没有可领取内容，也记当天已处理（旧口径是留待重试）
        ui = FakeUi()
        t = make_task(ui)
        started = time.monotonic()
        with self.assertLogs('', level='INFO') as logs:
            t.run_luck_msg()
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(is_today(record(t).luck_msg_dt))
        text = '\n'.join(logs.output)
        self.assertIn('未发现可领取吉闻，今日检查完成。', text)
        self.assertNotIn('吉闻已领取', text)

    def test_reward_never_shows_is_recorded_as_checked_and_bounded(self):
        ui = self.world(reward_delay=999)
        t = make_task(ui, LUCK_TIMEOUT=3)
        started = time.monotonic()
        t.run_luck_msg()
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(is_today(record(t).luck_msg_dt))

    def test_collected_logs_the_collected_message(self):
        ui = self.world()
        t = make_task(ui)
        with self.assertLogs('', level='INFO') as logs:
            t.run_luck_msg()
        text = '\n'.join(logs.output)
        self.assertIn('吉闻已领取，今日处理完成。', text)
        self.assertNotIn('未发现可领取吉闻', text)

    def test_page_not_entered_is_not_recorded_and_clicks_nothing(self):
        ui = FakeUi()
        t = make_task(ui)
        t.goto_page = Mock(return_value=False)
        t.run_luck_msg()
        self.assertEqual(record(t).luck_msg_dt.year, 2023)
        self.assertEqual(ui.clicks, [])

    def test_exception_in_the_flow_is_not_recorded(self):
        ui = FakeUi()
        t = make_task(ui)
        t.screenshot = Mock(side_effect=RuntimeError('device lost'))
        with self.assertRaises(RuntimeError):
            t.run_luck_msg()
        self.assertEqual(record(t).luck_msg_dt.year, 2023)

    def test_reward_seen_but_popup_never_closes_is_not_recorded(self):
        ui = self.world()
        ui.on_click[id(BOTTOM)] = lambda: None          # 点了关不掉
        t = make_task(ui)
        t.run_luck_msg()
        self.assertEqual(record(t).luck_msg_dt.year, 2023)

    def test_next_day_checks_again(self):
        ui = self.world()
        t = make_task(ui)
        record(t).luck_msg_dt = datetime.now() - timedelta(days=1)
        t.run_luck_msg()
        self.assertGreater(len(ui.clicks), 0)
        self.assertTrue(is_today(record(t).luck_msg_dt))

    def test_friendship_popup_is_closed(self):
        ui = self.world()
        ui.later(0.1, lambda: ui.show(T.I_FRIENDSHIP_UP))
        ui.on_click[id(T.I_FRIENDSHIP_UP)] = lambda: ui.hide(T.I_FRIENDSHIP_UP)
        t = make_task(ui)
        t.run_luck_msg()
        self.assertEqual(ui.clicked(T.I_FRIENDSHIP_UP), 1)
        self.assertTrue(is_today(record(t).luck_msg_dt))

    def test_friendship_template_that_never_goes_away_is_clicked_at_most_three_times(self):
        # 小模板万一在固定位置误匹配：最多点 3 次，也不重新计时，循环照常按空闲计时结束
        ui = FakeUi([T.I_FRIENDSHIP_UP])
        t = make_task(ui)
        started = time.monotonic()
        t.run_luck_msg()
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(ui.clicked(T.I_FRIENDSHIP_UP), 3)
        self.assertTrue(is_today(record(t).luck_msg_dt))

    def test_done_today_skips(self):
        ui = self.world()
        t = make_task(ui)
        record(t).luck_msg_dt = datetime.now()
        t.run_luck_msg()
        self.assertEqual(ui.clicks, [])


class CourtyardAffairsTest(unittest.TestCase):
    def world(self, rounds_needed=1, already_complete=False, has_entry=True, tab_works=True, button_delay=0.0,
              has_button=True, max_level_popup=False):
        """一键完成 → 奖励页 → 点同一位置关掉回到事务页；出现现世首领时要再来一轮。

        max_level_popup：第一次一键完成先弹「式神已满级，是否提取（取消 / 确认）」，事务页和一键完成按钮还在后面
        认得出来；点取消后游戏接着一键完成、出奖励页（用户实测）。
        """
        ui = FakeUi([T.I_ENTER_COURTYARD_AFFAIRS] if has_entry else [])
        state = {'rounds': 0, 'popup': max_level_popup, 'extracted': False}

        def cancel_popup():
            ui.hide(T.I_UI_CANCEL_SAMLL, T.I_UI_CONFIRM_SAMLL)
            ui.hide(T.I_CHECK_COURTYARD_AFFAIRS, T.I_ONE_COMPLETE)
            ui.show(T.I_DAILYFFAIR_REWARD)

        def confirm_popup():
            state['extracted'] = True
            cancel_popup()

        ui.on_click[id(T.I_UI_CANCEL_SAMLL)] = cancel_popup
        ui.on_click[id(T.I_UI_CONFIRM_SAMLL)] = confirm_popup

        def enter_page():
            ui.hide(T.I_ENTER_COURTYARD_AFFAIRS)
            ui.show(T.I_CHECK_COURTYARD_AFFAIRS, T.I_ENTER_DAILY)
            if has_button and button_delay:
                ui.later(button_delay, lambda: ui.show(T.I_ONE_COMPLETE))
            elif has_button:
                ui.show(T.I_ONE_COMPLETE)
            if already_complete:
                ui.show(T.I_IS_COMPLETE)

        def enter_daily():
            if tab_works:
                ui.hide(T.I_ENTER_DAILY)
                ui.show(T.I_CHECK_IN_DAILY)

        def one_complete():
            if id(T.I_DAILYFFAIR_REWARD) in ui.visible:
                ui.hide(T.I_DAILYFFAIR_REWARD)
                ui.show(T.I_CHECK_COURTYARD_AFFAIRS, T.I_ONE_COMPLETE)
                if state['rounds'] >= rounds_needed:
                    ui.show(T.I_IS_COMPLETE)
                return
            state['rounds'] += 1
            if state['popup']:
                state['popup'] = False
                ui.show(T.I_UI_CANCEL_SAMLL, T.I_UI_CONFIRM_SAMLL)
                return
            ui.hide(T.I_CHECK_COURTYARD_AFFAIRS, T.I_ONE_COMPLETE)
            ui.show(T.I_DAILYFFAIR_REWARD)

        ui.on_page[id(page_courtyard_affairs)] = enter_page
        ui.on_click[id(T.I_ENTER_DAILY)] = enter_daily
        ui.on_click[id(T.I_ONE_COMPLETE)] = one_complete
        return ui, state

    def test_period_boundaries(self):
        p = T._current_courtyard_period
        self.assertIsNone(p(datetime(2026, 10, 22, 4, 59)))
        self.assertEqual(p(datetime(2026, 10, 22, 5, 0)), 'morning')
        self.assertEqual(p(datetime(2026, 10, 22, 17, 59)), 'morning')
        self.assertEqual(p(datetime(2026, 10, 22, 18, 0)), 'evening')
        self.assertEqual(p(datetime(2026, 10, 22, 23, 59)), 'evening')

    def test_two_boss_appearances_need_three_rounds(self):
        ui, state = self.world(rounds_needed=3)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(state['rounds'], 3)
        self.assertIn(id(T.I_IS_COMPLETE), ui.visible)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))
        self.assertTrue(is_today(record(t).courtyard_affairs_dt))
        self.assertEqual(record(t).courtyard_evening_dt.year, 2023)

    def test_single_round(self):
        ui, state = self.world(rounds_needed=1)
        t = make_task(ui)
        t.run_courtyard_affairs('evening')
        self.assertEqual(state['rounds'], 1)
        self.assertTrue(is_today(record(t).courtyard_evening_dt))

    def test_never_completes_stops_after_three_rounds_and_marks_done(self):
        ui, state = self.world(rounds_needed=99)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(state['rounds'], 3)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_button_that_shows_up_late_is_still_clicked(self):
        # 切到日常标签后列表晚 0.6 秒才出来：不能在按钮出来之前就把 3 轮用完
        ui, state = self.world(rounds_needed=1, button_delay=0.6)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(state['rounds'], 1)
        self.assertIn(id(T.I_IS_COMPLETE), ui.visible)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_button_that_never_shows_waits_each_round_then_marks_done(self):
        ui, state = self.world(has_button=False)
        t = make_task(ui, COURTYARD_BUTTON_WAIT=0.2)
        started = time.monotonic()
        t.run_courtyard_affairs('morning')
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.6)            # 3 轮各等过一次
        self.assertLess(elapsed, 3)
        self.assertEqual(state['rounds'], 0)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_already_complete_clicks_nothing(self):
        ui, state = self.world(already_complete=True)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(state['rounds'], 0)
        self.assertEqual(ui.clicked(T.I_ONE_COMPLETE), 0)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_no_entry_marks_done(self):
        ui, state = self.world(has_entry=False)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(ui.clicks, [])
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_daily_tab_that_never_opens_is_bounded(self):
        ui, state = self.world(tab_works=False)
        t = make_task(ui)
        started = time.monotonic()
        t.run_courtyard_affairs('morning')
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(state['rounds'], 0)

    def test_period_done_today_skips(self):
        ui, state = self.world()
        t = make_task(ui)
        record(t).courtyard_morning_dt = datetime.now()
        t.run_courtyard_affairs('morning')
        self.assertEqual(ui.clicks, [])
        t.run_courtyard_affairs('evening')            # 另一个时段照常做
        self.assertEqual(state['rounds'], 1)

    def test_invalid_period(self):
        with self.assertRaises(ValueError):
            make_task(FakeUi()).run_courtyard_affairs('noon')

    def test_max_level_popup_is_cancelled_then_reward_is_collected(self):
        # 10-23 实测：一键完成后弹满级提取框，原来只认奖励页，6 秒后记完成、回庭院时乱点
        ui, state = self.world(rounds_needed=1, max_level_popup=True)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(ui.clicked(T.I_UI_CANCEL_SAMLL), 1)
        self.assertEqual(ui.clicked(T.I_UI_CONFIRM_SAMLL), 0)
        self.assertFalse(state['extracted'])
        self.assertNotIn(id(T.I_DAILYFFAIR_REWARD), ui.visible)    # 奖励页关掉了
        self.assertIn(id(T.I_IS_COMPLETE), ui.visible)
        self.assertEqual(state['rounds'], 1)
        self.assertTrue(is_today(record(t).courtyard_morning_dt))

    def test_one_complete_is_not_clicked_while_the_popup_is_open(self):
        # 弹窗开着时后面的一键完成照样认得出来，先关弹窗
        ui, state = self.world(rounds_needed=1)

        def enter_with_popup():
            ui.hide(T.I_ENTER_COURTYARD_AFFAIRS)
            ui.show(T.I_CHECK_COURTYARD_AFFAIRS, T.I_CHECK_IN_DAILY, T.I_ONE_COMPLETE,
                    T.I_UI_CANCEL_SAMLL, T.I_UI_CONFIRM_SAMLL)

        ui.on_page[id(page_courtyard_affairs)] = enter_with_popup
        ui.on_click[id(T.I_UI_CANCEL_SAMLL)] = lambda: ui.hide(T.I_UI_CANCEL_SAMLL, T.I_UI_CONFIRM_SAMLL)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertIs(ui.clicks[0], T.I_UI_CANCEL_SAMLL)
        self.assertEqual(ui.clicked(T.I_UI_CONFIRM_SAMLL), 0)
        self.assertIn(id(T.I_IS_COMPLETE), ui.visible)

    def test_a_lone_cancel_button_is_not_taken_as_the_popup(self):
        ui, state = self.world(rounds_needed=1)
        ui.show(T.I_UI_CANCEL_SAMLL)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(ui.clicked(T.I_UI_CANCEL_SAMLL), 0)
        self.assertIn(id(T.I_IS_COMPLETE), ui.visible)

    def test_clicks_use_the_click_model(self):
        ui, state = self.world(rounds_needed=1, max_level_popup=True)
        t = make_task(ui)
        t.run_courtyard_affairs('morning')
        self.assertEqual(ui.policies_of(T.I_ENTER_DAILY), {P.FAST})
        self.assertEqual(ui.policies_of(T.I_UI_CANCEL_SAMLL), {P.CONFIRM})
        # 一键完成按钮本身是 NORMAL；关奖励页复用同一位置，用 NAVIGATION
        self.assertEqual(ui.policies_of(T.I_ONE_COMPLETE), {P.NORMAL, P.NAVIGATION})
        self.assertNotIn(None, {p for _, p in ui.policies})


class GuildDonateTest(unittest.TestCase):
    def test_finish_records_the_date_so_the_same_day_is_skipped(self):
        ui = FakeUi([T.I_UI_BACK_RED])
        t = make_task(ui)
        t.config.daily_trifles.guild_donate.enable = True
        t.run_guild_donate()
        self.assertTrue(is_today(record(t).guild_donate_dt))
        self.assertTrue(record(t).guild_donate_finish)
        self.assertTrue(t.config.daily_trifles.today_is_done('guild_donate'))
        visits = []
        ui.on_page[id(page_main)] = lambda: visits.append(1)
        t.run_guild_donate()
        self.assertEqual(visits, [])

    def test_friend_list_still_runs_after_the_guild_member_list_fails(self):
        # 写成 all_done and self.donate(...) 时，寮友名单失败会短路，好友名单就不执行了
        ui = FakeUi([T.I_UI_BACK_RED])
        t = make_task(ui)
        t.donate = Mock(side_effect=[False, True])
        t.run_guild_donate()
        self.assertEqual(t.donate.call_count, 2)
        self.assertFalse(record(t).guild_donate_finish)
        self.assertFalse(t.config.daily_trifles.today_is_done('guild_donate'))   # 没全部成功，下次运行再试

    def test_switch_select_is_bounded(self):
        t = make_task(FakeUi())
        started = time.monotonic()
        self.assertFalse(t.switch_select(T.I_DT_GW_FRIEND_SELECTED, T.I_DT_GW_GUILD_MEMBER_SELECTED,
                                         T.I_DT_GW_SELECT_FRIEND))
        self.assertLess(time.monotonic() - started, 2)

    def test_donate_stops_when_the_tab_cannot_be_switched(self):
        t = make_task(FakeUi())
        self.assertFalse(t.donate(['A', 'B'], lambda: False, False))
        t.swipe.assert_not_called()


class StoreSignTest(unittest.TestCase):
    def world(self, sign_stays=False, has_sign=True):
        ui = FakeUi([T.I_GIFT_RECOMMEND])
        if has_sign:
            ui.on_click[id(T.I_GIFT_RECOMMEND)] = lambda: ui.show(T.I_GIFT_SIGN)
        ui.on_click[id(T.I_GIFT_SIGN)] = lambda: ui.show(T.I_UI_REWARD)

        def close_reward():
            ui.hide(T.I_UI_REWARD)
            if not sign_stays:
                ui.hide(T.I_GIFT_SIGN)
        ui.on_click[id(T.C_UI_REWARD)] = close_reward
        return ui

    def test_signed_and_button_gone_is_recorded(self):
        t = make_task(self.world())
        t.run_store_sign()
        self.assertTrue(is_today(record(t).store_sign_dt))

    def test_button_still_there_is_not_recorded(self):
        t = make_task(self.world(sign_stays=True))
        t.run_store_sign()
        self.assertEqual(record(t).store_sign_dt.year, 2023)

    def test_no_button_counts_as_signed(self):
        t = make_task(self.world(has_sign=False))
        t.run_store_sign()
        self.assertTrue(is_today(record(t).store_sign_dt))


class SushiTest(unittest.TestCase):
    def test_cannot_enter_special_page_is_bounded_and_not_recorded(self):
        t = make_task(FakeUi())
        t.config.daily_trifles.trifles_config.buy_sushi_count = 2
        started = time.monotonic()
        t.run_buy_sushi()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(record(t).sushi_dt.year, 2023)

    def test_special_page_without_the_sushi_item_is_bounded_and_not_recorded(self):
        # 进了 Special 但一直认不出体力商品（列表没加载 / 换了样子）：有界放弃，不记完成
        t = make_task(FakeUi([WeeklyPurchaseAssets.I_SIDE_CHECK_SPECIAL]))
        t.config.daily_trifles.trifles_config.buy_sushi_count = 2
        started = time.monotonic()
        t.run_buy_sushi()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(record(t).sushi_dt.year, 2023)


class BuySushiTest(unittest.TestCase):
    """假商城：价格 = 60 + 20 × 已买次数；点体力 → 购买框；点勾玉 → 「获得奖励」盖住列表；关掉奖励 → 已买 +1。"""

    def setUp(self):
        self.reads = None     # 价格识别注入：None = 读到真实价格；列表 = 依次返回（用完后重复最后一个）
        self.ocr = SimpleNamespace(roi=None, detect_text=self._read)
        patcher = patch.object(T, 'O_STORE_SUSHI_PRICE', self.ocr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _read(self, image):
        if self.reads is None:
            return str(60 + 20 * self.state['bought'])
        value = self.reads[0] if len(self.reads) == 1 else self.reads.pop(0)
        return value

    def world(self, bought=0, dialog_opens=True):
        ui = FakeUi([WeeklyPurchaseAssets.I_MALL_SUNDRY])
        self.state = {'bought': bought}
        listing = (WeeklyPurchaseAssets.I_SIDE_CHECK_SPECIAL, T.I_SPECIAL_SUSHI)

        def open_sundry():
            ui.show(*listing)

        def open_dialog():
            if dialog_opens:
                ui.hide(T.I_SPECIAL_SUSHI)
                ui.show(T.I_STORE_COST_TYPE_JADE)

        def buy():
            ui.hide(T.I_STORE_COST_TYPE_JADE, *listing)       # 奖励框盖住列表
            ui.show(T.I_UI_REWARD)

        def close_reward():
            ui.hide(T.I_UI_REWARD)
            self.state['bought'] += 1
            ui.show(*listing)

        ui.on_click[id(WeeklyPurchaseAssets.I_MALL_SUNDRY)] = open_sundry
        ui.on_click[id(T.I_SPECIAL_SUSHI)] = open_dialog
        ui.on_click[id(T.I_STORE_COST_TYPE_JADE)] = buy
        ui.on_click[id(T.C_UI_REWARD)] = close_reward
        return ui

    def task(self, ui, target=2, **consts):
        consts.setdefault('SUSHI_BUY_TIMEOUT', 6)        # 每买一次，ui_get_reward 关奖励时会 sleep 0.5 秒
        t = make_task(ui, **consts)
        t.device = SimpleNamespace(image=None)
        t.config.daily_trifles.trifles_config.buy_sushi_count = target
        return t

    def test_buys_exactly_up_to_the_target_and_records(self):
        ui = self.world()
        t = self.task(ui)
        t.run_buy_sushi()
        self.assertEqual(self.state['bought'], 2)
        self.assertEqual(ui.clicked(T.I_STORE_COST_TYPE_JADE), 2)
        self.assertTrue(is_today(record(t).sushi_dt))

    def test_goes_back_to_the_mall_page_before_the_sundry_tab(self):
        # 签到结束停在礼包屋子页时，要先回商城主页才点得到底栏「杂货」
        ui = self.world()
        t = self.task(ui)
        t.run_buy_sushi()
        self.assertIs(ui.pages[0], page_mall)
        self.assertGreaterEqual(ui.clicked(WeeklyPurchaseAssets.I_MALL_SUNDRY), 1)

    def test_already_reached_buys_nothing_and_records(self):
        ui = self.world(bought=2)
        t = self.task(ui)
        t.run_buy_sushi()
        self.assertEqual(ui.clicked(T.I_STORE_COST_TYPE_JADE), 0)
        self.assertTrue(is_today(record(t).sushi_dt))

    def test_price_read_one_digit_short_buys_nothing(self):
        # 80 读成 8：以前当作「还没买」继续买；现在读数不是 60 + 20k 就停
        self.reads = ['8']
        ui = self.world(bought=1)
        t = self.task(ui)
        t.run_buy_sushi()
        self.assertEqual(ui.clicked(T.I_STORE_COST_TYPE_JADE), 0)
        self.assertEqual(record(t).sushi_dt.year, 2023)

    def test_price_stuck_at_the_first_price_never_buys_more_than_planned(self):
        # 价格一直读成 60（像是一次都没买）：本次最多买「目标 − 0」次就停，不记完成，不会一直买下去
        self.reads = ['60']
        ui = self.world()
        t = self.task(ui)
        t.run_buy_sushi()
        self.assertEqual(self.state['bought'], 2)
        self.assertEqual(ui.clicked(T.I_STORE_COST_TYPE_JADE), 2)
        self.assertEqual(record(t).sushi_dt.year, 2023)

    def test_purchase_dialog_that_never_opens_is_bounded(self):
        ui = self.world(dialog_opens=False)
        t = self.task(ui, SUSHI_DIALOG_WAIT=0.3)
        started = time.monotonic()
        t.run_buy_sushi()
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(ui.clicked(T.I_STORE_COST_TYPE_JADE), 0)
        self.assertEqual(record(t).sushi_dt.year, 2023)

    def test_read_sushi_bought(self):
        t = make_task(FakeUi())
        t.device = SimpleNamespace(image=None)
        rule = SimpleNamespace(roi_front=[100, 200, 40, 40])
        for text, expected in (('60', (0, 60)), ('80', (1, 80)), ('140', (4, 140)), ('8', (None, 8)),
                               ('70', (None, 70)), ('', (None, None)), ('abc', (None, None))):
            with self.subTest(text=text):
                self.reads = [text]
                self.assertEqual(t._read_sushi_bought(rule), expected)
        self.assertEqual(self.ocr.roi, [140, 195, 75, 45])     # 价格框在右侧 75×45


class CourtyardSushiTest(unittest.TestCase):
    def world(self, sushi=True, sushi_stays=False):
        """点寿司 → 弹「获得奖励」→ 公共关闭区域关掉，寿司随之消失（或领完还在）。"""
        ui = FakeUi([T.I_COURTYARD_SUSHI] if sushi else [])
        ui.on_click[id(T.I_COURTYARD_SUSHI)] = lambda: ui.show(T.I_UI_REWARD)

        def close():
            ui.hide(T.I_UI_REWARD)
            if not sushi_stays:
                ui.hide(T.I_COURTYARD_SUSHI)
        ui.on_click[id(T.C_UI_REWARD)] = close
        return ui

    def test_period_boundaries(self):
        p = T._current_sushi_period
        cases = {(11, 59): None, (12, 0): 'noon', (13, 59): 'noon', (14, 0): None,
                 (19, 59): None, (20, 0): 'evening', (21, 59): 'evening', (22, 0): None}
        for (h, m), expected in cases.items():
            with self.subTest(time=f'{h}:{m:02d}'):
                self.assertEqual(p(datetime(2026, 10, 23, h, m)), expected)

    def test_collected_and_gone_is_recorded(self):
        ui = self.world()
        t = make_task(ui)
        t.run_courtyard_sushi('noon')
        self.assertEqual(ui.clicked(T.I_COURTYARD_SUSHI), 1)
        self.assertEqual(ui.clicked(T.C_UI_REWARD), 1)
        self.assertTrue(is_today(record(t).courtyard_sushi_noon_dt))
        self.assertEqual(record(t).courtyard_sushi_evening_dt.year, 2023)
        self.assertEqual(record(t).sushi_dt.year, 2023)            # 商店买体力的记录不受影响

    def test_not_found_after_a_normal_check_records_only_this_period(self):
        ui = self.world(sushi=False)
        t = make_task(ui)
        started = time.monotonic()
        t.run_courtyard_sushi('evening')
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(ui.clicks, [])
        self.assertTrue(is_today(record(t).courtyard_sushi_evening_dt))
        self.assertEqual(record(t).courtyard_sushi_noon_dt.year, 2023)

    def test_noon_not_found_does_not_affect_evening(self):
        ui = self.world(sushi=False)
        t = make_task(ui)
        t.run_courtyard_sushi('noon')
        self.assertTrue(is_today(record(t).courtyard_sushi_noon_dt))
        ui.show(T.I_COURTYARD_SUSHI)
        t.run_courtyard_sushi('evening')
        self.assertEqual(ui.clicked(T.I_COURTYARD_SUSHI), 1)
        self.assertTrue(is_today(record(t).courtyard_sushi_evening_dt))

    def test_collected_and_not_found_log_differently(self):
        with self.assertLogs('', level='INFO') as logs:
            make_task(self.world(sushi=False)).run_courtyard_sushi('noon')
        self.assertIn('未发现可领取寿司', '\n'.join(logs.output))
        with self.assertLogs('', level='INFO') as logs:
            make_task(self.world()).run_courtyard_sushi('noon')
        self.assertIn('庭院寿司已领取', '\n'.join(logs.output))

    def test_second_run_in_the_same_period_skips_even_when_nothing_was_found(self):
        ui = self.world(sushi=False)
        t = make_task(ui)
        t.run_courtyard_sushi('noon')
        shots = ui.shots
        ui.show(T.I_COURTYARD_SUSHI)
        t.run_courtyard_sushi('noon')
        self.assertEqual(ui.clicks, [])
        self.assertEqual(ui.shots, shots)

    def test_next_day_checks_again(self):
        ui = self.world()
        t = make_task(ui)
        record(t).courtyard_sushi_noon_dt = datetime.now() - timedelta(days=1)
        t.run_courtyard_sushi('noon')
        self.assertEqual(ui.clicked(T.I_COURTYARD_SUSHI), 1)
        self.assertTrue(is_today(record(t).courtyard_sushi_noon_dt))

    def test_page_not_entered_is_not_recorded(self):
        ui = self.world()
        t = make_task(ui)
        t.goto_page = Mock(return_value=False)
        t.run_courtyard_sushi('noon')
        self.assertEqual(record(t).courtyard_sushi_noon_dt.year, 2023)
        self.assertEqual(ui.clicks, [])

    def test_exception_is_not_recorded(self):
        ui = self.world()
        t = make_task(ui)
        t.goto_page = Mock(side_effect=RuntimeError('device lost'))
        with self.assertRaises(RuntimeError):
            t.run_courtyard_sushi('noon')
        self.assertEqual(record(t).courtyard_sushi_noon_dt.year, 2023)

    def test_still_there_after_reward_is_not_recorded(self):
        t = make_task(self.world(sushi_stays=True))
        t.run_courtyard_sushi('noon')
        self.assertEqual(record(t).courtyard_sushi_noon_dt.year, 2023)

    def test_done_period_skips(self):
        ui = self.world()
        t = make_task(ui)
        record(t).courtyard_sushi_noon_dt = datetime.now()
        t.run_courtyard_sushi('noon')
        self.assertEqual(ui.clicks, [])

    def test_run_collects_only_in_a_period_with_the_switch_on(self):
        def run_with(switch, period):
            t = make_task(FakeUi())
            con = t.config.daily_trifles.trifles_config
            con.courtyard_affairs = con.pickup_email = con.luck_msg = con.store_sign = False
            con.courtyard_sushi = switch
            t.run_courtyard_sushi = Mock(name='run_courtyard_sushi')
            t.plan_next_dt = Mock(name='plan_next_dt')
            with patch.object(T, '_current_sushi_period', return_value=period), self.assertRaises(TaskEnd):
                t.run()
            return t.run_courtyard_sushi
        run_with(True, 'noon').assert_called_once_with('noon')
        run_with(True, None).assert_not_called()
        run_with(False, 'evening').assert_not_called()

    def test_ten_minute_sushi_retry_is_gone(self):
        self.assertFalse(hasattr(T, '_sushi_retry_at'))
        self.assertFalse(hasattr(T, 'SUSHI_RETRY'))

    def test_plan_next_dt_follows_the_normal_schedule_even_when_sushi_unrecorded(self):
        """真实 plan_next_dt：不再因为寿司没记完成而 +10 分钟；下次 = 下一个服务器刷新（09:00）与下一个 12 / 20 点时段点中较早的一个。"""
        cases = {(7, 0): (26, 9, 0), (9, 0): (26, 12, 0), (12, 5): (26, 20, 0), (13, 50): (26, 20, 0),
                 (20, 30): (27, 9, 0), (23, 59): (27, 9, 0)}
        for (h, m), (day, eh, em) in cases.items():
            with self.subTest(now=f'{h}:{m:02d}'):
                t = make_task(FakeUi())
                t.config.daily_trifles.trifles_config.courtyard_sushi = True      # 寿司开着、本时段没记录
                t.set_next_run = Mock(name='set_next_run')
                t.custom_next_run = Mock(name='custom_next_run')
                with patch('tasks.DailyTrifles.script_task.datetime') as dt:
                    dt.now.return_value = datetime(2026, 10, 26, h, m)
                    t.plan_next_dt()
                t.custom_next_run.assert_not_called()
                self.assertEqual(t.set_next_run.call_count, 1)
                kwargs = t.set_next_run.call_args.kwargs
                self.assertEqual(kwargs['task'], 'DailyTrifles')
                self.assertEqual(kwargs['target'], datetime(2026, 10, day, eh, em))      # float_time 默认 0：不加延迟
                self.assertIs(kwargs['server'], False)


class PickupEmailTest(unittest.TestCase):
    def world(self):
        # 点「打开邮箱」按钮后进入邮箱（标题出现）；邮箱里没有可操作按钮，空闲一小段时间就算领完
        ui = FakeUi([T.I_HARVEST_MAIL])
        ui.on_click[id(T.I_HARVEST_MAIL)] = lambda: (ui.hide(T.I_HARVEST_MAIL), ui.show(RestartAssets.I_HARVEST_MAIL_TITLE))
        return ui

    def test_second_run_the_same_day_is_skipped(self):
        ui = self.world()
        t = make_task(ui, PICKUP_IDLE=0.3, PICKUP_OPEN_GAP=0.3, PICKUP_EXIT_TIMEOUT=0.3, PICKUP_LOST_TIMEOUT=0.5)
        t.run_pickup_email()
        self.assertTrue(is_today(record(t).pickup_email_dt))
        self.assertGreater(len(ui.clicks), 0)
        ui.clicks.clear()
        ui.pages.clear()
        ui.show(T.I_HARVEST_MAIL)
        t.run_pickup_email()
        self.assertEqual(ui.clicks, [])
        self.assertEqual(ui.pages, [])

    def test_next_day_picks_up_again(self):
        ui = self.world()
        t = make_task(ui, PICKUP_IDLE=0.3, PICKUP_OPEN_GAP=0.3, PICKUP_EXIT_TIMEOUT=0.3, PICKUP_LOST_TIMEOUT=0.5)
        record(t).pickup_email_dt = datetime.now() - timedelta(days=1)
        t.run_pickup_email()
        self.assertGreater(len(ui.clicks), 0)
        self.assertTrue(is_today(record(t).pickup_email_dt))


class PagesAreTheOnesTheTaskUses(unittest.TestCase):
    def test_imports(self):
        # 替身按页面对象身份分派，这里钉住测试里用的就是任务里用的那几个页面
        import tasks.DailyTrifles.script_task as mod
        self.assertIs(mod.page_friends_luck, page_friends_luck)
        self.assertIs(mod.page_store_gift_room, page_store_gift_room)
        self.assertIs(mod.page_courtyard_affairs, page_courtyard_affairs)


if __name__ == '__main__':
    unittest.main()
