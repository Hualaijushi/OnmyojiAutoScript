# This Python file uses the following encoding: utf-8
"""DailyTrifles 领取邮件：已经在邮箱里就不再点「打开邮箱」按钮，邮箱标志 = 「邮箱」标题 / 「系统邮件」标签打开状态任一出现。

背景（10-29 oas2 09:49）：邮箱已打开，顶栏信封（`DT_HARVEST_MAIL_COPY2`）仍露在边框上方、照样匹配，循环每 1.2 秒又点它，
和「一键领取」来回各点 6 次触发 `GameTooManyClickError`。标志模板已按当前界面重新标注，在现场截图上匹配度 1.0（其它页面截图最高约 0.45，
阈值 0.8）。这里用假画面驱动真实 `run_pickup_email`（真实 Timer，常量缩小），验证点击行为和收尾记录；真实模板识别与动画时序待真机。

2026-11-01 oas1 / oas2：庭院信封没有红点，三个旧入口都认不出（`COPY2` 约 0.56），没有任何点击，约 60 秒后公共卡死保护抛 `GameStuckError` 并重启。
新增无红点入口 `I_DT_HARVEST_MAIL_COPY3`，并给「尚未确认打开邮箱」阶段加独立的有界时限（`PICKUP_OPEN_TIMEOUT`），见文件后半部分。
本文件的循环都带独立的截图 / 点击次数哨兵（`PickupCase` + `guard`）：没有退出条件时抛带用例名的 `AssertionError`，不会高速空转积累内存。
"""

import json
import os
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from dev_tools.assets_extract import AssetsExtractor
from module.exception import GameStuckError
from module.image.runtime import ImageRuntime
from module.interaction_policy import InteractionPolicy as P
from tasks.DailyTrifles.script_task import ScriptTask as T
from tasks.GameUi.page import page_main
from tasks.Restart.assets import RestartAssets
from tests.test_daily_trifles import FakeUi, is_today, make_task, record

TITLE = RestartAssets.I_HARVEST_MAIL_TITLE
SYSTEM_OPEN = RestartAssets.I_SYSTEM_MAIL_OPEN
SMALL = dict(PICKUP_IDLE=0.3, PICKUP_OPEN_GAP=0.3, PICKUP_TIMEOUT=5, PICKUP_EXIT_TIMEOUT=0.3, PICKUP_LOST_TIMEOUT=0.5,
             PICKUP_OPEN_TIMEOUT=2.0)
OPEN_BUTTONS = (T.I_DT_HARVEST_MAIL_COPY2, T.I_HARVEST_MAIL, T.I_HARVEST_MAIL_COPY, T.I_DT_HARVEST_MAIL_COPY3)

# 独立于被测代码里任何计时 / 卡死保护的次数哨兵，只防「没有退出条件的空转」：
# 假画面不模拟 appear_then_click 的 interval 节流，空邮箱等待 0.3 秒就会点一百多次「全部已读」，所以点击上限放宽
SHOT_LIMIT = 4000
ACTION_LIMIT = 400
CASE = {'id': 'test_daily_pickup_email'}


class PickupCase(unittest.TestCase):
    def setUp(self):
        CASE['id'] = self.id()


def phase_info(ui):
    clicks = Counter(getattr(r, 'name', str(r)) for r in ui.clicks)
    return f'截图 {ui.shots} 次，点击 {len(ui.clicks)} 次 {dict(clicks)}，goto_page {len(ui.pages)} 次'


def guard(ui):
    """给假画面加截图 / 点击次数上限；超限抛带用例名和阶段信息的 AssertionError。"""
    case, screenshot, click = CASE['id'], ui.screenshot, ui.click

    def guarded_screenshot():
        if ui.shots >= SHOT_LIMIT:
            raise AssertionError(f'{case}: run_pickup_email 超过 {SHOT_LIMIT} 次截图仍未结束（{phase_info(ui)}）')
        return screenshot()

    def guarded_click(rule, interval=None, policy=None):
        if len(ui.clicks) >= ACTION_LIMIT:
            raise AssertionError(f'{case}: run_pickup_email 超过 {ACTION_LIMIT} 次点击仍未结束（{phase_info(ui)}）')
        return click(rule, interval=interval, policy=policy)

    ui.screenshot, ui.click = guarded_screenshot, guarded_click
    return ui


def with_public_stuck(ui, limit_s):
    """模拟公共卡死保护：距上一次点击（或开始）超过 limit_s 就在截图时抛 GameStuckError（真实保护约 60 秒，这里按比例缩小）。"""
    last = {'t': time.monotonic()}
    screenshot, click = ui.screenshot, ui.click

    def shot():
        if time.monotonic() - last['t'] > limit_s:
            raise GameStuckError('Wait too long')
        return screenshot()

    def clk(rule, interval=None, policy=None):
        last['t'] = time.monotonic()
        return click(rule, interval=interval, policy=policy)

    ui.screenshot, ui.click = shot, clk
    return ui


def make(ui, **consts):
    return make_task(guard(ui), **{**SMALL, **consts})


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


class AlreadyInMailboxTest(PickupCase):
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


class OpeningTheMailboxTest(PickupCase):
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


class ClaimTest(PickupCase):
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


class StickyMailboxAndPopupsTest(PickupCase):
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


class IllustrationAndBoundsTest(PickupCase):
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


# --------------------------------------------------------------------------------------
# 无红点入口（COPY3）与「尚未打开邮箱」阶段的有界性
# 2026-11-01 oas1 / oas2：庭院信封没有红点，三个旧入口都认不出，没有任何点击，约 60 秒后公共卡死保护抛 GameStuckError 并重启
# --------------------------------------------------------------------------------------

COPY2, COPY3 = T.I_DT_HARVEST_MAIL_COPY2, T.I_DT_HARVEST_MAIL_COPY3


def open_when_clicked(ui, rule, delay=0.05, markers=(TITLE, SYSTEM_OPEN, T.I_HARVEST_MAIL_ALL)):
    ui.on_click[id(rule)] = lambda: ui.later(delay, lambda: ui.show(*markers))


class NoRedDotEntranceTest(PickupCase):
    def test_only_copy3_visible_opens_claims_closes_and_records(self):
        ui = FakeUi([COPY3])                                                  # 信封没有红点：只有 COPY3 能认出
        open_when_clicked(ui, COPY3)
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(COPY3), 1)                                # 打开后信封仍然可见，也没有再点
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)                 # 无红点但邮箱里有可领内容：照常领取
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_CONFIRM), 1)
        self.assertEqual(ui.policies_of(COPY3), {P.NORMAL})
        self.assertTrue(is_today(record(t).pickup_email_dt))
        self.assertEqual(ui.pages, [page_main, page_main])

    def test_no_red_dot_and_an_empty_mailbox_is_completed_only_after_actually_entering_it(self):
        ui = FakeUi([COPY3])
        open_when_clicked(ui, COPY3, markers=(TITLE, T.I_READ_ALL_MAIL))     # 邮箱里没有可一键领取的内容
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(COPY3), 1)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 0)
        self.assertTrue(is_today(record(t).pickup_email_dt))                  # 确认进过邮箱、没有东西可领：沿用空邮箱完成逻辑

    def test_seeing_the_entrance_without_a_red_dot_alone_never_completes_anything(self):
        ui = FakeUi([COPY3])                                                  # 点了也打不开
        t = make(ui)
        t.run_pickup_email()
        self.assertFalse(is_today(record(t).pickup_email_dt))                 # 没有红点 ≠ 没有邮件 ≠ 今日完成

    def test_the_old_red_dot_entrance_still_works_and_copy3_is_not_involved(self):
        ui = FakeUi([COPY2])
        open_when_clicked(ui, COPY2)
        claim_flow(ui)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual((ui.clicked(COPY2), ui.clicked(COPY3)), (1, 0))
        self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_both_entrances_visible_send_at_most_one_open_click_per_round(self):
        ui = FakeUi([COPY2, COPY3])                                           # 红点信封两个模板都能认出（见真实帧测试）
        stamps = []
        for rule in (COPY2, COPY3, T.I_HARVEST_MAIL, T.I_HARVEST_MAIL_COPY):
            ui.on_click[id(rule)] = lambda: stamps.append(ui.shots)
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(len(stamps), T.PICKUP_OPEN_TRIES)                    # 总次数仍受上限约束
        self.assertEqual(len(set(stamps)), len(stamps), f'同一轮（同一次截图）发出了多次打开动作: {stamps}')
        self.assertEqual((ui.clicked(COPY2), ui.clicked(COPY3)), (T.PICKUP_OPEN_TRIES, 0))   # 旧入口优先
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_an_open_mailbox_is_never_re_opened_even_if_copy3_still_matches(self):
        for markers in ((TITLE, SYSTEM_OPEN), (TITLE,), (SYSTEM_OPEN,)):
            with self.subTest(markers=[m.name for m in markers]):
                ui = FakeUi([*markers, COPY3, COPY2, T.I_HARVEST_MAIL_ALL])
                claim_flow(ui, marker=markers)
                t = make(ui)
                t.run_pickup_email()
                self.assertEqual((ui.clicked(COPY3), ui.clicked(COPY2)), (0, 0))
                self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_a_reward_cover_hiding_the_markers_never_leads_back_to_the_entrance(self):
        # 领取后：奖励 / 全屏页盖住邮箱标志，顶栏信封仍然匹配
        for cover in ('unknown', 'red_cross'):
            with self.subTest(cover=cover):
                ui = FakeUi([TITLE, COPY3, T.I_HARVEST_MAIL_ALL])

                def on_all(ui=ui, cover=cover):
                    ui.hide(T.I_HARVEST_MAIL_ALL, TITLE)
                    if cover == 'red_cross':
                        ui.show(T.I_UI_BACK_RED)
                    else:
                        ui.later(0.15, lambda: ui.show(TITLE))
                ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = on_all
                ui.on_click[id(T.I_UI_BACK_RED)] = lambda ui=ui: (ui.hide(T.I_UI_BACK_RED), ui.show(TITLE))
                t = make(ui, PICKUP_LOST_TIMEOUT=2)
                t.run_pickup_email()
                self.assertEqual(ui.clicked(COPY3), 0)
                self.assertTrue(is_today(record(t).pickup_email_dt))

    def test_open_clicks_keep_the_gap_and_the_click_limit(self):
        ui = FakeUi([COPY3])
        stamps = []
        ui.on_click[id(COPY3)] = lambda: stamps.append(time.monotonic())
        t = make(ui)
        t.run_pickup_email()
        self.assertEqual(len(stamps), T.PICKUP_OPEN_TRIES)
        self.assertTrue(all(b - a >= 0.29 for a, b in zip(stamps, stamps[1:])), stamps)
        self.assertFalse(is_today(record(t).pickup_email_dt))
        self.assertIs(ui.pages[-1], page_main)

    def test_a_mailbox_that_opens_late_but_within_the_budget_is_still_used(self):
        ui = FakeUi([COPY3])
        ui.on_click[id(COPY3)] = lambda: None
        ui.later(0.45, lambda: ui.show(TITLE, SYSTEM_OPEN, T.I_HARVEST_MAIL_ALL))   # 第二次点击之后、第三次之前才打开
        claim_flow(ui)
        t = make(ui, PICKUP_OPEN_TIMEOUT=1.0)
        t.run_pickup_email()
        self.assertLessEqual(ui.clicked(COPY3), T.PICKUP_OPEN_TRIES)
        self.assertEqual(ui.clicked(T.I_HARVEST_MAIL_ALL), 1)
        self.assertTrue(is_today(record(t).pickup_email_dt))


class OpenPhaseBoundTest(PickupCase):
    """所有入口都认不出 / 点击没发出 / 点击后不开：本地阶段时限先结束，不靠公共 GameStuckError。

    时间按比例缩小：公共卡死保护约 60 秒 → 1.5 秒；本地打开阶段 20 秒 → 0.5 秒。
    """
    PUBLIC_STUCK = 1.5
    LOCAL = 0.5

    def run_bounded(self, ui, **consts):
        with_public_stuck(ui, self.PUBLIC_STUCK)
        t = make(ui, **{'PICKUP_OPEN_TIMEOUT': self.LOCAL, 'PICKUP_TIMEOUT': 5, **consts})
        start = time.monotonic()
        t.run_pickup_email()                                                    # 不得抛 GameStuckError
        return t, time.monotonic() - start

    def test_no_entrance_recognised_ends_by_the_local_phase_limit_and_is_not_recorded(self):
        ui = FakeUi([])
        t, elapsed = self.run_bounded(ui)
        self.assertEqual(ui.clicks, [])
        self.assertGreaterEqual(elapsed, self.LOCAL - 0.05)
        self.assertLess(elapsed, self.PUBLIC_STUCK - 0.3)                       # 明显早于公共保护，也远早于 PICKUP_TIMEOUT
        self.assertFalse(is_today(record(t).pickup_email_dt))                   # 不记完成，不伪装成空邮箱
        self.assertEqual(ui.pages, [page_main, page_main])                      # 交回流程（goto_page 兜底），不重启

    def test_an_entrance_that_flickers_does_not_restart_the_phase_timer(self):
        ui = FakeUi([])
        orig = ui.screenshot
        ui.screenshot = lambda: (orig(), ui.show(COPY3) if ui.shots % 2 else ui.hide(COPY3))[0]   # 一帧有一帧无
        ui.appear_then_click = lambda rule, **_: False                          # 点击从未实际发出
        t, elapsed = self.run_bounded(ui)
        self.assertLess(elapsed, self.PUBLIC_STUCK - 0.3)
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_a_visible_entrance_whose_click_is_never_sent_neither_inflates_the_counter_nor_loops_forever(self):
        ui = FakeUi([COPY3])
        ui.appear_then_click = lambda rule, **_: False                          # 间隔节流 / 点击被拒：没有实际点击
        with_public_stuck(ui, 3.0)
        t = make(ui, PICKUP_OPEN_TIMEOUT=1.2, PICKUP_TIMEOUT=5)
        start = time.monotonic()
        t.run_pickup_email()
        elapsed = time.monotonic() - start
        self.assertEqual(ui.clicks, [])
        # 如果把「没点出去」也算一次点击，3 次上限会在约 0.9 秒就先触发；这里要靠阶段时限（1.2 秒）结束
        self.assertGreaterEqual(elapsed, 1.1)
        self.assertLess(elapsed, 2.5)
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_clicked_but_never_opened_stays_within_the_click_limit(self):
        ui = FakeUi([COPY3])
        t, _ = self.run_bounded(ui, PICKUP_OPEN_TIMEOUT=5)                      # 阶段时限放宽：由点击次数上限结束
        self.assertEqual(ui.clicked(COPY3), T.PICKUP_OPEN_TRIES)
        self.assertFalse(is_today(record(t).pickup_email_dt))

    def test_the_phase_limit_does_not_apply_once_the_mailbox_has_been_seen(self):
        ui = FakeUi([COPY3])
        open_when_clicked(ui, COPY3)
        ui.on_click[id(T.I_HARVEST_MAIL_ALL)] = lambda: ui.hide(T.I_HARVEST_MAIL_ALL, TITLE, SYSTEM_OPEN)   # 领取后标志被盖住
        ui.later(0.9, lambda: ui.show(TITLE, SYSTEM_OPEN))                      # 比阶段时限（0.5 秒）更晚才回来
        t = make(ui, PICKUP_OPEN_TIMEOUT=0.5, PICKUP_LOST_TIMEOUT=3)
        t.run_pickup_email()
        self.assertEqual(ui.clicked(COPY3), 1)
        self.assertTrue(is_today(record(t).pickup_email_dt))                    # 进过邮箱后由原来的领取 / 退出逻辑负责

    def test_the_constant_is_well_before_the_public_protection_and_above_the_normal_worst_case(self):
        normal_worst = T.PICKUP_OPEN_TRIES * T.PICKUP_OPEN_GAP
        self.assertGreater(T.PICKUP_OPEN_TIMEOUT, normal_worst)                 # 3 次点击 + 最后一次之后再等一个间隔 ≈ 9 秒
        self.assertLessEqual(T.PICKUP_OPEN_TIMEOUT, 30)                         # 公共保护约 60 秒，留出一半以上余量
        self.assertLess(T.PICKUP_OPEN_TIMEOUT, T.PICKUP_TIMEOUT)


class PropagationTest(PickupCase):
    """设备 / 截图异常、公共卡死保护、停止信号一律原样传播，不为了避免重启被吞掉；也不记完成。"""

    ERRORS = (RuntimeError('device broke'), GameStuckError('Wait too long'), KeyboardInterrupt(), SystemExit(3))

    def test_exceptions_raised_by_screenshot_propagate_unchanged(self):
        for exc in self.ERRORS:
            with self.subTest(exc=type(exc).__name__):
                ui = FakeUi([COPY3])
                orig = ui.screenshot

                def shot(ui=ui, orig=orig, exc=exc):
                    if ui.shots >= 2:
                        raise exc
                    return orig()
                ui.screenshot = shot
                t = make(ui)
                with self.assertRaises(type(exc)) as caught:
                    t.run_pickup_email()
                self.assertIs(caught.exception, exc)
                self.assertFalse(is_today(record(t).pickup_email_dt))
                self.assertEqual(ui.pages, [page_main])                         # 没有为了「善后」再去 goto_page

    def test_exceptions_raised_by_the_open_click_propagate_unchanged(self):
        for exc in self.ERRORS:
            with self.subTest(exc=type(exc).__name__):
                ui = FakeUi([COPY3])

                def boom(exc=exc):
                    raise exc
                ui.on_click[id(COPY3)] = boom
                t = make(ui)
                with self.assertRaises(type(exc)) as caught:
                    t.run_pickup_email()
                self.assertIs(caught.exception, exc)
                self.assertFalse(is_today(record(t).pickup_email_dt))


# --------------------------------------------------------------------------------------
# 资源与真实画面：COPY3 的 PNG / 规则 / 生成资产配套，以及在真实事故帧上的离线匹配
# --------------------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / 'tests' / 'fixtures' / 'daily_pickup_email'
NO_DOT = FIX / 'courtyard_no_red_dot_oas1_20261101.png'        # 2026-11-01 15:02 事故帧：庭院，信封没有红点
RED_DOT = FIX / 'courtyard_red_dot_oas2_20261031.png'          # 2026-10-31 17:31：庭院，信封有红点
MAILBOX = FIX / 'mailbox_open_oas2_20261029.png'               # 2026-10-29 09:49：邮箱已打开


class _InProcessImageClient:
    """生产匹配入口（RuleImage.match → 图像服务）的进程内替身：直接调 ImageRuntime，不经 RPC。"""

    def __init__(self, runtime):
        self.runtime = runtime

    def match_rule(self, rule_data, image, frame_id=None, threshold=None):
        return self.runtime._match_rule_payload(image=image, rule_data=rule_data, threshold=threshold)


class NoRedDotAssetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = ImageRuntime()
        cls.patcher = patch('module.atom.image.get_image_client', return_value=_InProcessImageClient(cls.runtime))
        cls.patcher.start()
        cls.frames = {p: cv2.cvtColor(cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), -1)[:, :, :3], cv2.COLOR_BGR2RGB)
                      for p in (NO_DOT, RED_DOT, MAILBOX)}

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.runtime.shutdown()

    def score(self, rule, frame):
        return self.runtime._match_rule_payload(image=self.frames[frame], rule_data=rule.to_service_payload())

    def test_rule_png_json_and_generated_assets_are_consistent(self):
        rule = T.I_DT_HARVEST_MAIL_COPY3
        entries = {e['itemName']: e for e in json.loads(
            (REPO / 'tasks/DailyTrifles/dt/image_pickup_email.json').read_text(encoding='utf-8'))}
        entry = entries['dt_harvest_mail_copy3']                                 # 规则 itemName
        self.assertEqual(rule.name, 'DT_DT_HARVEST_MAIL_COPY3')                  # 生成后的属性名 I_DT_HARVEST_MAIL_COPY3
        self.assertEqual(entry['imageName'], 'dt_dt_harvest_mail_copy3.png')
        self.assertTrue(rule.file.replace('\\', '/').endswith('tasks/DailyTrifles/dt/' + entry['imageName']))
        self.assertEqual(','.join(str(v) for v in rule.roi_front), entry['roiFront'])
        self.assertEqual(','.join(str(v) for v in rule.roi_back), entry['roiBack'])
        self.assertEqual(rule.threshold, entry['threshold'])
        self.assertEqual(rule.threshold, 0.8)
        self.assertEqual(rule.method, 'Template matching')
        template = cv2.imdecode(np.fromfile(str(REPO / rule.file), dtype=np.uint8), -1)
        self.assertEqual(template.shape[:2][::-1], tuple(rule.roi_front[2:]))     # PNG 尺寸 = roi_front 的宽高
        fx, fy, fw, fh = rule.roi_front
        bx, by, bw, bh = rule.roi_back
        self.assertTrue(bx <= fx and by <= fy and bx + bw >= fx + fw and by + bh >= fy + fh)

    def test_other_pickup_assets_were_not_touched_by_the_new_resource(self):
        for rule, roi_front, threshold in ((T.I_DT_HARVEST_MAIL_COPY2, [1158, 18, 22, 20], 0.9),
                                           (T.I_HARVEST_MAIL, [337, 505, 37, 25], 0.8),
                                           (T.I_HARVEST_MAIL_COPY, [257, 509, 29, 21], 0.8)):
            with self.subTest(rule=rule.name):
                self.assertEqual((list(rule.roi_front), rule.threshold), (roi_front, threshold))

    def test_assets_py_is_exactly_what_the_generator_produces(self):
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            extractor = AssetsExtractor(str(REPO / 'tasks/DailyTrifles'))
            extractor.write_file = lambda: None
            extractor.extract()
            self.assertEqual(extractor._result, (REPO / 'tasks/DailyTrifles/assets.py').read_bytes().decode('utf-8'))
        finally:
            os.chdir(cwd)

    def test_the_no_red_dot_accident_frame_matches_copy3_but_none_of_the_old_entrances(self):
        self.assertTrue(self.score(COPY3, NO_DOT)['matched'])
        self.assertGreater(self.score(COPY3, NO_DOT)['score'], 0.95)
        for rule in (COPY2, T.I_HARVEST_MAIL, T.I_HARVEST_MAIL_COPY):
            with self.subTest(rule=rule.name):
                self.assertFalse(self.score(rule, NO_DOT)['matched'])           # 与事故报告一致：旧入口约 0.56 / 0.5 / 0.4

    def test_the_red_dot_frame_matches_both_so_the_old_entrance_must_keep_priority(self):
        self.assertTrue(self.score(COPY2, RED_DOT)['matched'])
        self.assertTrue(self.score(COPY3, RED_DOT)['matched'])

    def test_the_click_point_lies_on_the_envelope(self):
        rule = T.I_DT_HARVEST_MAIL_COPY3
        saved = list(rule.roi_front)
        try:
            self.assertTrue(rule.match(self.frames[NO_DOT]))                    # 生产匹配入口：命中后 roi_front = 模板尺寸框 @ 匹配位置
            x, y, w, h = rule.roi_front
            for _ in range(200):
                px, py = rule.coord()
                self.assertTrue(x <= px < x + w and y <= py < y + h, (px, py, rule.roi_front))
            self.assertTrue(1128 <= x and x + w <= 1182 and 5 <= y and y + h <= 60)   # 右上角三个按钮里中间的信封
        finally:
            rule.roi_front = saved

    def test_mailbox_markers_are_decided_before_the_entrances_on_real_frames(self):
        task = T.__new__(T)
        saved = {id(r): (r, list(r.roi_front)) for r in (TITLE, SYSTEM_OPEN)}      # match() 会改 roi_front，用完还原
        try:
            for frame, expected in ((MAILBOX, True), (NO_DOT, False), (RED_DOT, False)):
                with self.subTest(frame=frame.name):
                    image = self.frames[frame]
                    task.appear = lambda rule, image=image: rule.match(image)
                    self.assertEqual(task._in_mailbox(), expected)
        finally:
            for rule, roi_front in saved.values():
                rule.roi_front = roi_front
        # 已打开的邮箱画面里顶栏信封（旧入口）照样能匹配——所以 `_in_mailbox` 必须先于任何入口判断
        self.assertTrue(self.score(COPY2, MAILBOX)['matched'])


if __name__ == '__main__':
    unittest.main()
