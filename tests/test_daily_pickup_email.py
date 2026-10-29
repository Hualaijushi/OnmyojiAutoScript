# This Python file uses the following encoding: utf-8
"""DailyTrifles 领取邮件：已经在邮箱里就不再点「打开邮箱」按钮，邮箱标志 = 「邮箱」标题 / 「系统邮件」标签打开状态任一出现。

背景（10-29 oas2 09:49）：邮箱已打开，顶栏信封（`DT_HARVEST_MAIL_COPY2`）仍露在边框上方、照样匹配，循环每 1.2 秒又点它，
和「一键领取」来回各点 6 次触发 `GameTooManyClickError`。标志模板已按当前界面重新标注，在现场截图上匹配度 1.0（其它页面截图最高约 0.45，
阈值 0.8）。这里用假画面驱动真实 `run_pickup_email`（真实 Timer，常量缩小），验证点击行为和收尾记录；真实模板识别与动画时序待真机。
"""

import time
import unittest

from module.interaction_policy import InteractionPolicy as P
from tasks.DailyTrifles.script_task import ScriptTask as T
from tasks.GameUi.page import page_main
from tasks.Restart.assets import RestartAssets
from tests.test_daily_trifles import FakeUi, is_today, make_task, record

TITLE = RestartAssets.I_HARVEST_MAIL_TITLE
SYSTEM_OPEN = RestartAssets.I_SYSTEM_MAIL_OPEN
SMALL = dict(PICKUP_IDLE=0.3, PICKUP_OPEN_GAP=0.3, PICKUP_TIMEOUT=5, PICKUP_EXIT_TIMEOUT=0.3, PICKUP_LOST_TIMEOUT=0.5)
OPEN_BUTTONS = (T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL, T.I_HARVEST_MAIL_COPY)


def make(ui, **consts):
    return make_task(ui, **{**SMALL, **consts})


def claim_flow(ui, marker=(TITLE, SYSTEM_OPEN)):
    """一键领取 → 出现确认弹窗（盖住邮箱标志）→ 点确认 → 弹窗消失、一键领取灰掉。"""
    def on_all():
        ui.hide(T.I_HARVEST_MAIL_ALL, *marker)
        ui.show(T.I_HARVEST_MAIL_CONFIRM)

    def on_confirm():
        ui.hide(T.I_HARVEST_MAIL_CONFIRM)
        ui.show(*marker)
    ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
    ui.on_click[id(T.I_HARVEST_MAIL_CONFIRM)] = on_confirm


class AlreadyInMailboxTest(unittest.TestCase):
    def test_an_open_mailbox_never_gets_an_open_button_click_even_though_the_top_bar_envelope_still_matches(self):
        ui = FakeUi([TITLE, SYSTEM_OPEN, T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL_ALL])      # 现场情形：信封仍可见
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        for rule in OPEN_BUTTONS:
            self.assertEqual(ui.clicked(rule), 0)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_CONFIRM), 1)
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_either_marker_alone_means_in_the_mailbox(self):
        for marker in (TITLE, SYSTEM_OPEN):
            with self.subTest(marker=marker.name):
                ui = FakeUi([marker, T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL_ALL])
                claim_flow(ui, marker=(marker,))
                t = make(ui)
                t.run_pickup_email()
                self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
                self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)
                self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_a_confirm_popup_that_hides_the_markers_is_handled_without_clicking_open_buttons(self):
        ui = FakeUi([TITLE, SYSTEM_OPEN, T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL_ALL])
        claim_flow(ui)                                                       # 弹窗期间两个标志都被盖住
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_CONFIRM), 1)

    def test_a_permanently_visible_read_all_button_does_not_keep_the_loop_alive(self):
        ui = FakeUi([TITLE, T.I_READ_ALL_MAIL])                              # 没有可领取的邮件：一键领取不出现
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 0)
        self.assertTrue(is_today(record(t).pickup_email_dt))                # 邮箱里确实没东西可领：算完成


class OpeningTheMailboxTest(unittest.TestCase):
    def test_a_closed_mailbox_is_opened_once_and_the_envelope_is_not_clicked_again(self):
        ui = FakeUi([T.I_DT_HARVEST_MAIL_COPY2])                              # 信封一直可见
        ui.on_click[id(T.I_DT_HARVEST_MAIL_COPY2)] = lambda: ui.later(
            0.05, lambda: ui.show(TITLE, SYSTEM_OPEN, T.I_HARVEST_MAIL_ALL))
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 1)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_a_mailbox_that_never_opens_is_retried_a_bounded_number_of_times_and_not_marked_done(self):
        ui = FakeUi([T.I_DT_HARVEST_MAIL_COPY2])
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), T.PICKUP_OPEN_TRIES)
        self.assertFalse(is_today(record(t).pickup_email_dt))                        # 没进过邮箱：下次运行再试，不假装完成
        self.assertIs(ui.pages[-1], page_main)

    def test_open_clicks_are_spaced_by_the_open_gap(self):
        ui = FakeUi([T.I_DT_HARVEST_MAIL_COPY2])
        stamps = []
        ui.on_click[id(T.I_DT_HARVEST_MAIL_COPY2)] = lambda: stamps.append(time.monotonic())
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(len(stamps), T.PICKUP_OPEN_TRIES)
        self.assertTrue(all(b - a >= 0.29 for a, b in zip(stamps, stamps[1:])), stamps)


class ClaimTest(unittest.TestCase):
    def test_a_one_key_claim_that_never_produces_a_popup_gives_up_after_a_bounded_number_of_clicks(self):
        ui = FakeUi([TITLE, T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL_ALL])      # 点了一键领取毫无反应
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), T.PICKUP_ALL_TRIES + 1)
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_two_confirm_popups_in_a_row_are_both_clicked(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        state = {'confirms': 0}

        def on_all():
            ui.hide(T.I_HARVEST_MAIL_ALL)
            ui.show(T.I_HARVEST_MAIL_CONFIRM)

        def on_confirm():
            state['confirms'] += 1
            if state['confirms'] >= 2:
                ui.hide(T.I_HARVEST_MAIL_CONFIRM)                          # 第二个弹窗（奖励）关掉后结束
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
        ui.on_click[id(T.I_HARVEST_MAIL_CONFIRM)] = on_confirm
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(state['confirms'], 2)
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_policies_and_constants_are_the_agreed_ones(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.policies_of(T.I_HARVEST_MAIL_ALL), {P.NORMAL})
        self.assertEqual(ui.policies_of(T.I_HARVEST_MAIL_CONFIRM), {P.CONFIRM})
        self.assertEqual((T.PICKUP_IDLE, T.PICKUP_OPEN_GAP, T.PICKUP_OPEN_TRIES, T.PICKUP_ALL_TRIES, T.PICKUP_TIMEOUT),
                         (3, 3, 3, 6, 60))

    def test_a_second_run_the_same_day_is_skipped(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        ui.clicks.clear()
        ui.pages.clear()
        t.run_pickup_email()
        self.assertEqual((ui.clicks, ui.pages), ([], []))


class StickyMailboxAndPopupsTest(unittest.TestCase):
    """进过邮箱就一直算在邮箱流程里，直到自己点了退出；领取后的弹窗 / 全屏页会盖住邮箱标志，不能当成离开了邮箱。"""

    def test_markers_hidden_by_a_popup_never_lead_to_open_button_clicks_and_the_claim_continues_afterwards(self):
        ui = FakeUi([TITLE, T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL_ALL])
        # 点一键领取 → 标志被弹窗盖住一阵（没有任何已知按钮）→ 弹窗自己消失、标志回来、一键领取灰掉
        def on_all():
            ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)
            ui.later(0.15, lambda: ui.show(TITLE))
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
        t = make(ui, PICKUP_LOST_TIMEOUT=2)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_the_two_button_enable_popup_is_cancelled_never_confirmed(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])

        def on_all():
            ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)
            ui.show(T.I_UI_CANCEL, T.I_UI_CONFIRM)                          # 「是否立即启用…？」取消 / 确定
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
        ui.on_click[id(T.I_UI_CANCEL)] = lambda: (ui.hide(T.I_UI_CANCEL, T.I_UI_CONFIRM), ui.show(TITLE))
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_UI_CANCEL), 1)
        self.assertEqual(ui.clicked(T.I_UI_CONFIRM), 0)                      # 从不替用户点确定
        self.assertEqual(ui.policies_of(T.I_UI_CANCEL), {P.CONFIRM})
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_a_single_confirm_button_is_not_mistaken_for_the_two_button_popup(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        claim_flow(ui)
        ui.show(T.I_UI_CONFIRM)                                              # 只有大号「确定」没有「取消」
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_UI_CANCEL), 0)

    def test_a_full_screen_page_with_a_red_close_cross_is_closed_when_the_mailbox_markers_are_not_visible(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])

        def on_all():
            ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)
            ui.show(T.I_UI_BACK_RED)                                         # 获得头像框之类的全屏页
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
        ui.on_click[id(T.I_UI_BACK_RED)] = lambda: (ui.hide(T.I_UI_BACK_RED), ui.show(TITLE)) if not ui.visible & {id(TITLE)} else None
        t = make(ui)
        t.run_pickup_email()
        self.assertGreaterEqual(ui.clicked(T.I_UI_BACK_RED), 1)
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertEqual(ui.policies_of(T.I_UI_BACK_RED), {P.NAVIGATION})

    def test_the_mailbox_own_close_cross_is_clicked_only_after_everything_is_claimed(self):
        ui = FakeUi([TITLE, T.I_UI_BACK_RED, T.I_HARVEST_MAIL_ALL])           # 邮箱自己的关闭叉一直在
        claim_flow(ui, marker=(TITLE,))
        ui.on_click[id(T.I_UI_BACK_RED)] = lambda: ui.hide(TITLE, T.I_UI_BACK_RED)
        t = make(ui)
        t.run_pickup_email()
        order = [r.name for r in ui.clicks]
        self.assertEqual(ui.clicked(T.I_UI_BACK_RED), 1)
        self.assertGreater(order.index(T.I_UI_BACK_RED.name), order.index(T.I_HARVEST_MAIL_CONFIRM.name))   # 领完（确认弹窗处理完）才退出
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_an_unknown_popup_that_never_goes_away_leaves_through_the_fallback_after_a_bounded_wait(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL, T.I_DT_HARVEST_MAIL_COPY2])
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = lambda: ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)      # 之后什么都认不出
        t = make(ui)
        start = time.monotonic()
        t.run_pickup_email()
        self.assertLess(time.monotonic() - start, 2.0)
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertIs(ui.pages[-1], page_main)                              # 由 goto_page 兜底
        self.assertTrue(is_today(record(t).pickup_email_dt))                # 已经点过一键领取

    def test_an_unknown_state_right_after_opening_without_any_claim_is_not_recorded_as_done(self):
        ui = FakeUi([T.I_UI_BACK_RED])
        t = make(ui, PICKUP_TIMEOUT=1)
        t.run_pickup_email()                                                # 从没进过邮箱 / 没领取
        self.assertFalse(is_today(record(t).pickup_email_dt))


    def test_a_lone_cancel_button_is_not_treated_as_the_enable_popup(self):
        ui = FakeUi([TITLE, T.I_UI_CANCEL, T.I_HARVEST_MAIL_ALL])           # 只有「取消」没有「确定」：不是启用确认弹窗，不点
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_UI_CANCEL), 0)

    def test_losing_the_markers_before_any_claim_is_not_recorded_as_done(self):
        ui = FakeUi([TITLE])
        ui.later(0.05, lambda: ui.hide(TITLE))                              # 看到过邮箱标志，随后什么都认不出，没点过一键领取 / 确认
        t = make(ui)
        t.run_pickup_email()
        self.assertFalse(is_today(record(t).pickup_email_dt))
        self.assertIs(ui.pages[-1], page_main)


class IllustrationAndBoundsTest(unittest.TestCase):
    """获得插画（标题模板 `I_GET_PICTURE`，用户已标注）与各种「卡住」场景的有界性。"""

    def test_the_get_illustration_popup_is_closed_by_a_safe_blank_click(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])

        def on_all():
            ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)
            ui.show(T.I_GET_PICTURE)
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
        # 点空白处（random_click 返回的 SAFE_RANDOM_CLICK）后插画消失、邮箱标志回来
        ui.on_click[id(T.I_GET_PICTURE)] = lambda: None
        original = ui.click

        def click(rule, interval=None, policy=None):
            result = original(rule, interval=interval, policy=policy)
            if getattr(rule, 'name', '') == 'SAFE_RANDOM_CLICK':
                ui.hide(T.I_GET_PICTURE)
                ui.show(TITLE)
            return result
        ui.click = click
        t = make(ui)
        t.run_pickup_email()
        names = [getattr(r, 'name', '') for r in ui.clicks]
        self.assertEqual(names.count('SAFE_RANDOM_CLICK'), 1)
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)
        self.assertEqual(ui.policies_of(ui.clicks[names.index('SAFE_RANDOM_CLICK')]), {P.NORMAL})
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_a_popup_that_never_goes_away_is_clicked_a_bounded_number_of_times_then_given_up(self):
        for rule, extra in ((T.I_UI_CANCEL, (T.I_UI_CONFIRM,)), (T.I_HARVEST_MAIL_CONFIRM, ()), (T.I_GET_PICTURE, ())):
            with self.subTest(popup=rule.name):
                ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
                ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = lambda ui=ui, rule=rule, extra=extra: (
                    ui.hide(T.I_HARVEST_MAIL_ALL, TITLE), ui.show(rule, *extra))                  # 弹窗点了不消失
                t = make(ui)
                t.run_pickup_email()
                popup_clicks = sum(1 for r in ui.clicks if r in (rule,) or (rule is T.I_GET_PICTURE and getattr(r, 'name', '') == 'SAFE_RANDOM_CLICK'))
                self.assertEqual(popup_clicks, T.PICKUP_POPUP_TRIES + 1)
                self.assertLess(popup_clicks, 10)                                    # 低于点击守卫的 10 次
                self.assertFalse(is_today(record(t).pickup_email_dt))                # 放弃：不记完成
                self.assertIs(ui.pages[-1], page_main)

    def test_a_close_cross_that_does_nothing_is_also_bounded(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = lambda: (ui.hide(T.I_HARVEST_MAIL_ALL, TITLE), ui.show(T.I_UI_BACK_RED))
        t = make(ui, PICKUP_LOST_TIMEOUT=30)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(T.I_UI_BACK_RED), T.PICKUP_POPUP_TRIES + 1)
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_the_mailbox_closing_by_itself_is_left_immediately_instead_of_waiting_for_the_lost_timeout(self):
        ui = FakeUi([TITLE, T.I_HARVEST_MAIL_ALL])
        main = __import__('tasks.GameUi.assets', fromlist=['GameUiAssets']).GameUiAssets.I_CHECK_MAIN
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = lambda: (ui.hide(T.I_HARVEST_MAIL_ALL, TITLE), ui.show(main))   # 邮箱被关掉，回到主界面
        t = make(ui, PICKUP_LOST_TIMEOUT=30)
        start = time.monotonic()
        t.run_pickup_email()
        self.assertLess(time.monotonic() - start, 2.0)                       # 没有等 30 秒
        self.assertTrue(is_today(record(t).pickup_email_dt))                # 一键领取已点过

    def test_a_confirm_button_seen_before_the_mailbox_is_open_does_not_count_as_opened_or_claimed(self):
        ui = FakeUi([T.I_HARVEST_MAIL_CONFIRM])                              # 主界面上别的对话框碰巧也有「确定」
        ui.on_click[id(T.I_HARVEST_MAIL_CONFIRM)] = lambda: ui.hide(T.I_HARVEST_MAIL_CONFIRM)
        t = make(ui, PICKUP_TIMEOUT=1)
        t.run_pickup_email()
        self.assertFalse(is_today(record(t).pickup_email_dt))                # 没进过邮箱：不记完成
        self.assertEqual(ui.clicked(T.I_DT_HARVEST_MAIL_COPY2), 0)


if __name__ == '__main__':
    unittest.main()
