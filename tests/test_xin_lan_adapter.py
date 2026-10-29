# This Python file uses the following encoding: utf-8
"""XinLan 适配器（P4）：用假游戏跑完整流程，不碰设备 / OCR / 真实时钟以外的东西。

锁住：
- 每次进好友列表都先复位（最近 → 好友 → 展开 → 置顶好友），名字对不上不进福袋页；
- A 的 judge：小字提示或 B 的尝试任一成立算 done，都没有算 unknown；
- B 的 await_turn：A 没发就不碰屏幕，只认对得上的邀请人，亲眼看到回赠按钮才放行；
- 购买 / 回赠各只点一次；verify 只看分母是 20；
- 两个真实协调器（两个线程共用一份临时账本）：正常完成、同一天再跑直接 already、A 没送到则整轮 unsafe 停一天。
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from module.instance_sync import (
    NEXT_DEFER, NEXT_DONE, S_ALREADY, S_COMPLETED, S_FAILED, SyncCancelled, SyncCoordinator,
)
from module.instance_sync import state_machine as sm
from tasks.GameUi.assets import GameUiAssets as A
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.XinLan.adapter import ReceiverAdapter, SenderAdapter, XinLanAdapter, make_adapter
from tasks.XinLan.config import SyncConfig

MEMBERS = [('oas1', 'A01'), ('oas2', 'A02')]
DAY = '2026-10-22'
PARAMS = {'retry_wait': 0.2, 'budget': 20, 'min_attempt_cost': 0.05, 'max_rounds': 4}

TIMINGS = dict(POLL=0.005, CLICK_GAP=0.005, NAV_TIMEOUT=0.5, ACCEPT_WAIT=0.3, REPUR_WAIT=0.3, NUM_WAIT=0.3,
               JUDGE_WAIT=3.0, TOAST_WINDOW=0.05)


class Device:
    """一端的假界面：页面、标签、列表是否在顶端、弹窗、福袋页状态、图标上的分母。"""

    def __init__(self, role, alias, at_top=True):
        self.role, self.alias = role, alias          # alias = 本端被对端称呼的名字（弹窗里的邀请人）
        self.page = 'courtyard'
        self.tab = 'list'
        self.expanded = False
        self.at_top = at_top                         # False = 有通知，列表不在顶端
        self.detail = ''
        self.popup = None                            # 弹窗里的邀请人
        self.toast = 0
        self.repur = False                           # 福袋页上有没有回赠按钮
        self.total = None


class FakeGame:
    def __init__(self, notify=False, send_works=True, toast_visible=True, stranger_on_top=False):
        self.lock = threading.RLock()
        self.dev = {'a': Device('a', 'A01', at_top=not notify), 'b': Device('b', 'A02', at_top=not notify)}
        self.send_works, self.toast_visible, self.stranger_on_top = send_works, toast_visible, stranger_on_top
        self.log = []

    def count(self, role, what):
        return sum(1 for r, w in self.log if (r, w) == (role, what))


def label(rule):
    """日志里用的短名：图片资产的 name 是 PAGE_XXX / GI_XXX，换成好读的。"""
    for known, name in ((A.I_FRIEND_CUR_UNSEL, 'friend_cur_unsel'), (A.I_FRIEND_LIST_UNSEL, 'friend_list_unsel'),
                        (A.I_PURCHASE_TONGXIN, 'purchase_tongxin'), (A.I_REPUR_TONGXIN, 'repur_tongxin'),
                        (GeneralInviteAssets.I_I_ACCEPT, 'i_accept')):
        if rule is known:
            return name
    return rule.name


class FakeIO:
    """把适配器的设备缝隙接到 FakeGame 上。"""
    POLL, CLICK_GAP = TIMINGS['POLL'], TIMINGS['CLICK_GAP']
    NAV_TIMEOUT, ACCEPT_WAIT, REPUR_WAIT = TIMINGS['NAV_TIMEOUT'], TIMINGS['ACCEPT_WAIT'], TIMINGS['REPUR_WAIT']
    NUM_WAIT, JUDGE_WAIT, TOAST_WINDOW = TIMINGS['NUM_WAIT'], TIMINGS['JUDGE_WAIT'], TIMINGS['TOAST_WINDOW']

    def _setup(self, game, role):
        self.game, self.role, self.me = game, role, game.dev[role]
        self.peer = game.dev['b' if role == 'a' else 'a']
        self.keepalives = 0

    def protocol_params(self):
        return PARAMS

    def business_day(self, now):
        return DAY

    def _keepalive(self):
        self.keepalives += 1

    def _pause(self, seconds):
        time.sleep(0.001)

    def _shot(self):
        self._keepalive()
        with self.game.lock:
            if self.me.toast > 0:
                self.me.toast -= 1

    def _goto_friends(self):
        with self.game.lock:
            self.game.log.append((self.role, 'goto_friends'))
            self.me.page, self.me.detail = 'friends', ''
        return True

    def _seen(self, rule):
        d = self.me
        with self.game.lock:
            on_friends = d.page in ('friends', 'detail')
            table = {
                A.I_FRIEND_CUR_SEL: on_friends and d.tab == 'cur',
                A.I_FRIEND_CUR_UNSEL: on_friends and d.tab == 'list',
                A.I_FRIEND_LIST_SEL: on_friends and d.tab == 'list',
                A.I_FRIEND_LIST_UNSEL: on_friends and d.tab == 'cur',
                A.I_FRIEND_SAME_OPEN: on_friends and d.expanded,
                A.I_FRIEND_SAME_CLOSE: on_friends and not d.expanded,
                A.I_INVITE_TONGXIN: d.page == 'gift',
                A.I_PURCHASE_TONGXIN: d.page == 'gift' and d.role == 'a',
                A.I_REPUR_TONGXIN: d.page == 'gift' and d.repur,
                A.I_ACC_TONGXIN: d.popup is not None,
            }
            return table[rule]

    def _ocr(self, rule):
        d = self.me
        with self.game.lock:
            if rule is A.O_NAME_TONGXIN_FRIEND:
                return d.detail if d.page == 'detail' else ''
            if rule is A.O_NAME_TONGXIN_INVITER:
                return d.popup or ''
            if rule is A.O_TOAST_TONGXIN:
                return '邀请已发送。' if d.toast > 0 and self.game.toast_visible else ''
            if rule is A.O_NUM_TONGXIN:
                if d.page == 'detail' and d.total:
                    return (3, d.total - 3, d.total)
                return (0, 0, 0)
        raise AssertionError(rule)

    def _tap(self, rule):
        g, d = self.game, self.me
        with g.lock:
            g.log.append((self.role, label(rule)))
            if rule is A.I_FRIEND_CUR_UNSEL and d.tab == 'list':
                d.tab = 'cur'
            elif rule is A.I_FRIEND_LIST_UNSEL and d.tab == 'cur':
                d.tab, d.at_top = 'list', True
            elif rule is A.C_FRIEND_SAME:
                d.expanded = not d.expanded
            elif rule is A.C_THE_TOP_FRIEND and d.page in ('friends', 'detail') and d.expanded:
                d.page = 'detail'
                top_is_peer = d.at_top and not g.stranger_on_top
                d.detail = self.peer_alias if top_is_peer else 'Stranger'
            elif rule is A.C_TONGXIN_ICON and d.page == 'detail':
                d.page = 'gift'
            elif rule is A.C_RANDOM_LEFT and d.page == 'gift':
                d.page = 'detail'
            elif rule is A.I_PURCHASE_TONGXIN and d.role == 'a' and d.page == 'gift':
                if g.send_works:
                    self.peer.popup = d.alias
                    d.toast = 3
            elif rule is A.I_REPUR_TONGXIN and d.role == 'b' and d.page == 'gift' and d.repur:
                self.peer.popup = d.alias
            elif rule is GeneralInviteAssets.I_I_ACCEPT and d.popup:
                d.popup = None
                if d.role == 'b':
                    d.repur, d.total = True, 10
                else:
                    d.total = self.peer.total = 20


class FakeSender(FakeIO, SenderAdapter):
    def __init__(self, game, peer_alias='A02'):
        SenderAdapter.__init__(self, None, peer_alias)
        self._setup(game, 'a')


class FakeReceiver(FakeIO, ReceiverAdapter):
    def __init__(self, game, peer_alias='A01'):
        ReceiverAdapter.__init__(self, None, peer_alias)
        self._setup(game, 'b')


class FakeCtx:
    """单元测试用的上下文：账本快照由测试直接给。"""

    def __init__(self, peer_attempts=(), peer_state=None, my_attempts=(), remaining=5.0, on_wait=None):
        self.v = SimpleNamespace(peer_attempts=peer_attempts, peer_state=peer_state, my_attempts=my_attempts)
        self._remaining, self.on_wait, self.cancelled = remaining, on_wait, False

    def view(self):
        return self.v

    def check_alive(self):
        if self.cancelled:
            raise SyncCancelled('round failed')
        return self.v

    def remaining(self):
        return self._remaining

    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(0.001)

    def wait_until(self, predicate, timeout=None):
        if self.on_wait:
            self.on_wait(self.v)
        return bool(predicate(self.v))


ATTEMPT = SimpleNamespace(attempt_id='x', kind='xinlan', seq=1, status='prepared')


def open_to_gift(adapter, game, role):
    """直接把一端摆到「好友详情 / 福袋页」，用于单测某个动作。"""
    d = game.dev[role]
    d.page, d.expanded, d.detail = 'detail', True, adapter.peer_alias


class PeerDetailTest(unittest.TestCase):
    def test_reset_runs_before_the_fixed_click_even_without_notification(self):
        game = FakeGame()
        a = FakeSender(game)
        self.assertTrue(a._open_peer_detail())
        names = [w for r, w in game.log]
        self.assertEqual(names, ['goto_friends', 'friend_cur_unsel', 'friend_list_unsel', 'friend_same', 'the_top_friend'])

    def test_notification_does_not_make_us_click_the_wrong_row(self):
        game = FakeGame(notify=True)
        a = FakeSender(game)
        self.assertTrue(a._open_peer_detail())
        self.assertEqual(game.dev['a'].detail, 'A02')
        self.assertEqual(game.dev['a'].page, 'detail')

    def test_already_expanded_list_is_not_collapsed(self):
        game = FakeGame()
        game.dev['a'].expanded = True
        a = FakeSender(game)
        self.assertTrue(a._open_peer_detail())
        self.assertEqual(game.count('a', 'friend_same'), 0)
        self.assertTrue(game.dev['a'].expanded)

    def test_tabs_are_clicked_unconditionally_whatever_the_templates_say(self):
        """2026-10-24 oas1：选中 / 未选中模板互相得分 0.94，「看到已选中就跳过」把复位跳过了。
        不管模板怎么认，最近 → 好友各点一次；假界面里把「已选中」说成永远看得见，也照点。"""
        game = FakeGame(notify=True)
        game.dev['a'].tab = 'cur'
        a = FakeSender(game)
        a._seen_orig = a._seen
        a._seen = lambda rule: True if rule in (A.I_FRIEND_CUR_SEL, A.I_FRIEND_LIST_SEL) else a._seen_orig(rule)
        self.assertTrue(a._open_peer_detail())
        self.assertEqual(game.count('a', 'friend_cur_unsel'), 1)
        self.assertEqual(game.count('a', 'friend_list_unsel'), 1)
        self.assertEqual(game.dev['a'].detail, 'A02')

    def test_same_list_collapsed_arrow_seen_clicks_the_header_once(self):
        game = FakeGame()
        game.dev['a'].page, game.dev['a'].expanded = 'friends', False
        a = FakeSender(game)
        self.assertTrue(a._expand_same_list())
        self.assertTrue(game.dev['a'].expanded)
        self.assertEqual(game.count('a', 'friend_same'), 1)

    def test_same_list_only_clicks_when_the_collapsed_arrow_is_seen(self):
        """标题行是开关，展开时点会收起：没看到 ▶ 就一次也不点（▼ 看不看得见都无所谓）。"""
        game = FakeGame()
        game.dev['a'].page, game.dev['a'].expanded = 'friends', True
        a = FakeSender(game)
        a._seen_orig = a._seen
        a._seen = lambda rule: False if rule is A.I_FRIEND_SAME_OPEN else a._seen_orig(rule)
        self.assertTrue(a._expand_same_list())
        self.assertEqual(game.count('a', 'friend_same'), 0)
        self.assertTrue(game.dev['a'].expanded)

    def test_same_list_toggles_are_bounded_below_the_click_limit(self):
        game = FakeGame()
        game.dev['a'].page, game.dev['a'].expanded = 'friends', False
        a = FakeSender(game)
        a._seen_orig = a._seen
        a._seen = lambda rule: True if rule is A.I_FRIEND_SAME_CLOSE else a._seen_orig(rule)   # 点了也一直是 ▶
        self.assertFalse(a._expand_same_list())
        self.assertEqual(game.count('a', 'friend_same'), a.SAME_TOGGLES)
        self.assertLess(a.SAME_TOGGLES, 10)

    def test_missed_collapsed_arrow_falls_through_to_the_name_check_and_never_enters_the_gift_page(self):
        """▶ 漏识别（实际收起）：不点标题行，往下点置顶好友点不到人，名字核对不过，整套重做用尽才失败。"""
        game = FakeGame()
        game.dev['a'].expanded = False
        a = FakeSender(game)
        a._seen_orig = a._seen
        a._seen = lambda rule: False if rule is A.I_FRIEND_SAME_CLOSE else a._seen_orig(rule)
        result = a.prepare(FakeCtx())
        self.assertFalse(result.ok)
        self.assertEqual(game.count('a', 'friend_same'), 0)
        self.assertEqual(game.count('a', 'tongxin_icon'), 0)

    def test_wrong_top_friend_redoes_the_reset_a_bounded_number_of_times(self):
        """名字对不上不在原地连点（单按钮 10 次会触发 GameTooManyClickError），而是整套重做，次数有限。"""
        game = FakeGame(stranger_on_top=True)
        a = FakeSender(game)
        self.assertFalse(a._open_peer_detail())
        self.assertEqual(game.count('a', 'the_top_friend'), a.OPEN_TRIES)
        self.assertEqual(game.count('a', 'friend_cur_unsel'), a.OPEN_TRIES)
        self.assertLess(a.OPEN_TRIES, 10)

    def test_wrong_top_friend_fails_and_never_reaches_the_gift_page(self):
        game = FakeGame(stranger_on_top=True)
        a = FakeSender(game)
        result = a.prepare(FakeCtx())
        self.assertFalse(result.ok)
        self.assertEqual(game.count('a', 'tongxin_icon'), 0)
        self.assertEqual(game.count('a', 'purchase_tongxin'), 0)


class SenderTest(unittest.TestCase):
    def test_prepare_stops_on_the_gift_page_with_the_purchase_button(self):
        game = FakeGame()
        a = FakeSender(game)
        self.assertTrue(a.prepare(FakeCtx()).ok)
        self.assertEqual(game.dev['a'].page, 'gift')
        self.assertEqual(game.count('a', 'purchase_tongxin'), 0)

    def test_prepare_fails_when_the_purchase_button_is_missing(self):
        game = FakeGame()
        a = FakeSender(game)
        a._seen_orig = a._seen
        a._seen = lambda rule: False if rule is A.I_PURCHASE_TONGXIN else a._seen_orig(rule)
        result = a.prepare(FakeCtx())
        self.assertEqual((result.ok, result.reason), (False, 'purchase button missing'))

    def test_await_turn_is_free_when_the_button_is_there(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        game.log.clear()
        self.assertTrue(a.await_turn(FakeCtx()))
        self.assertEqual(game.log, [])

    def test_await_turn_navigates_again_when_not_on_the_gift_page(self):
        game = FakeGame()
        a = FakeSender(game)
        game.dev['a'].page = 'courtyard'
        self.assertTrue(a.await_turn(FakeCtx()))
        self.assertEqual(game.dev['a'].page, 'gift')

    def test_dispatch_clicks_purchase_exactly_once(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        a.dispatch(FakeCtx(), ATTEMPT)
        self.assertEqual(game.count('a', 'purchase_tongxin'), 1)
        self.assertEqual(game.dev['b'].popup, 'A01')

    def test_dispatch_after_cancel_does_not_click(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        ctx = FakeCtx()
        ctx.cancelled = True
        with self.assertRaises(SyncCancelled):
            a.dispatch(ctx, ATTEMPT)
        self.assertEqual(game.count('a', 'purchase_tongxin'), 0)

    def test_judge_done_on_toast_alone(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        a.dispatch(FakeCtx(), ATTEMPT)
        self.assertEqual(a.judge(FakeCtx(), ATTEMPT).kind, 'done')

    def test_judge_done_on_peer_attempt_alone(self):
        game = FakeGame(toast_visible=False)
        a = FakeSender(game)
        a.prepare(FakeCtx())
        a.dispatch(FakeCtx(), ATTEMPT)
        a.JUDGE_WAIT = 0.05
        self.assertEqual(a.judge(FakeCtx(), ATTEMPT).kind, 'unknown')
        self.assertEqual(a.judge(FakeCtx(peer_attempts=(ATTEMPT,)), ATTEMPT).kind, 'done')

    def test_judge_unknown_when_nothing_shows_up_never_not_done(self):
        game = FakeGame(toast_visible=False)
        a = FakeSender(game)
        a.JUDGE_WAIT = 0.05
        a.prepare(FakeCtx())
        a.dispatch(FakeCtx(), ATTEMPT)
        self.assertEqual(a.judge(FakeCtx(), ATTEMPT).kind, 'unknown')

    def test_judge_is_bounded_by_the_remaining_budget(self):
        game = FakeGame(toast_visible=False)
        a = FakeSender(game)
        a.prepare(FakeCtx())
        started = time.monotonic()
        self.assertEqual(a.judge(FakeCtx(remaining=0.05), ATTEMPT).kind, 'unknown')
        self.assertLess(time.monotonic() - started, 1.0)

    def test_toast_is_only_read_in_the_first_seconds(self):
        game = FakeGame()
        a = FakeSender(game)
        a.TOAST_WINDOW, a.JUDGE_WAIT = 0.0, 0.05
        a.prepare(FakeCtx())
        a.dispatch(FakeCtx(), ATTEMPT)
        self.assertEqual(a.judge(FakeCtx(), ATTEMPT).kind, 'unknown')

    def test_verify_accepts_the_return_invite_then_reads_denominator_20(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        game.dev['b'].total = 10
        game.dev['a'].popup = 'A02'
        self.assertTrue(a.verify(FakeCtx()))
        self.assertEqual(game.dev['a'].total, 20)

    def test_verify_ignores_an_invite_from_someone_else(self):
        game = FakeGame()
        a = FakeSender(game)
        a.JUDGE_WAIT = 0.05
        a.prepare(FakeCtx())
        game.dev['a'].popup = 'Stranger'
        self.assertFalse(a.verify(FakeCtx()))
        self.assertEqual(game.count('a', 'i_accept'), 0)

    def test_verify_false_when_denominator_is_not_20(self):
        game = FakeGame()
        a = FakeSender(game)
        a.prepare(FakeCtx())
        game.dev['a'].popup = 'A02'
        a._tap_orig = a._tap

        def tap(rule):
            a._tap_orig(rule)
            if rule is GeneralInviteAssets.I_I_ACCEPT:
                game.dev['a'].total = 10
        a._tap = tap
        self.assertFalse(a.verify(FakeCtx()))

    def test_numerator_is_not_part_of_the_criterion(self):
        game = FakeGame()
        a = FakeSender(game)
        game.dev['a'].page, game.dev['a'].total = 'detail', 20
        self.assertTrue(a._wait_total(20))

    def test_inspect_attempt(self):
        a = FakeSender(FakeGame())
        self.assertEqual(a.inspect_attempt(FakeCtx(peer_attempts=(ATTEMPT,)), ATTEMPT).kind, 'done')
        self.assertEqual(a.inspect_attempt(FakeCtx(), ATTEMPT).kind, 'unknown')


class ReceiverTest(unittest.TestCase):
    def test_prepare_stops_on_the_peer_detail(self):
        game = FakeGame()
        b = FakeReceiver(game)
        self.assertTrue(b.prepare(FakeCtx()).ok)
        self.assertEqual(game.dev['b'].page, 'detail')

    def test_await_turn_does_not_touch_the_screen_when_peer_has_not_started(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.log.clear()
        self.assertFalse(b.await_turn(FakeCtx(remaining=0.05)))
        self.assertEqual(game.log, [])

    def test_await_turn_accepts_then_waits_for_the_return_button(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'A01'
        self.assertTrue(b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,))))
        self.assertEqual(game.dev['b'].page, 'gift')
        self.assertEqual(game.count('b', 'i_accept'), 1)

    def test_await_turn_refuses_a_foreign_invite_and_returns_false(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'Stranger'
        self.assertFalse(b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,))))
        self.assertEqual(game.count('b', 'i_accept'), 0)
        self.assertEqual(game.count('b', 'repur_tongxin'), 0)

    def test_await_turn_is_false_when_the_peer_send_did_not_land(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        self.assertFalse(b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,))))
        self.assertEqual(game.count('b', 'repur_tongxin'), 0)

    def test_await_turn_is_idempotent_after_the_invite_was_accepted(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'A01'
        self.assertTrue(b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,))))
        self.assertTrue(b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,))))
        self.assertEqual(game.count('b', 'i_accept'), 1)

    def test_await_turn_waits_for_the_peer_via_the_ledger(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'A01'

        def peer_starts(view):
            view.peer_attempts = (ATTEMPT,)
        self.assertTrue(b.await_turn(FakeCtx(on_wait=peer_starts)))

    def test_dispatch_clicks_the_return_button_once_without_any_confirm(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'A01'
        b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,)))
        b.dispatch(FakeCtx(), ATTEMPT)
        self.assertEqual(game.count('b', 'repur_tongxin'), 1)
        self.assertEqual(game.dev['a'].popup, 'A02')
        self.assertEqual(game.log[-1], ('b', 'repur_tongxin'))

    def test_judge_waits_for_the_peer_to_verify(self):
        b = FakeReceiver(FakeGame())
        self.assertEqual(b.judge(FakeCtx(peer_state=sm.P_VERIFIED), ATTEMPT).kind, 'done')
        self.assertEqual(b.judge(FakeCtx(peer_state=sm.P_EXECUTING), ATTEMPT).kind, 'unknown')

    def test_verify_closes_the_gift_page_and_reads_20(self):
        game = FakeGame()
        b = FakeReceiver(game)
        b.prepare(FakeCtx())
        game.dev['b'].popup = 'A01'
        b.await_turn(FakeCtx(peer_attempts=(ATTEMPT,)))
        game.dev['b'].total = 10
        self.assertFalse(b.verify(FakeCtx()))
        self.assertEqual(game.dev['b'].page, 'detail')
        b.me.total = 20
        self.assertTrue(b.verify(FakeCtx()))

    def test_inspect_attempt(self):
        b = FakeReceiver(FakeGame())
        self.assertEqual(b.inspect_attempt(FakeCtx(peer_state=sm.P_VERIFIED), ATTEMPT).kind, 'done')
        self.assertEqual(b.inspect_attempt(FakeCtx(peer_state=sm.P_EXECUTING), ATTEMPT).kind, 'unknown')


class CommonTest(unittest.TestCase):
    def test_after_wait_resets_the_stuck_timer(self):
        a = FakeSender(FakeGame())
        a.after_wait(45)
        self.assertEqual(a.keepalives, 1)

    def test_roles_follow_the_config_name(self):
        sync = SyncConfig(instance_a=' oas1 ', alias_a='A01', instance_b='oas2', alias_b='A02')
        a = make_adapter(object(), sync, 'oas1')
        b = make_adapter(object(), sync, 'oas2')
        self.assertIsInstance(a, SenderAdapter)
        self.assertIsInstance(b, ReceiverAdapter)
        self.assertIsInstance(a, XinLanAdapter)
        self.assertEqual((a.peer_alias, b.peer_alias), ('A02', 'A01'))

    def test_protocol_and_business_day_come_from_business(self):
        a = SenderAdapter(None, 'A02')
        self.assertEqual(a.protocol_params()['max_rounds'], 4)
        self.assertEqual(a.business_day(time.mktime((2026, 10, 22, 0, 0, 1, 0, 0, -1))), '2026-10-22')
        self.assertEqual(a.business_day(time.mktime((2026, 10, 21, 23, 59, 59, 0, 0, -1))), '2026-10-21')


class TwoCoordinatorsTest(unittest.TestCase):
    """两个真实协调器（两个线程）共用一份临时账本，假游戏替它们接上界面。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # B 的 await_turn 会在 A 写下 prepared 之后、真正点击之前就开始等弹窗，线程调度慢时要留足余量
        saved = FakeIO.ACCEPT_WAIT
        FakeIO.ACCEPT_WAIT = 2.0
        self.addCleanup(setattr, FakeIO, 'ACCEPT_WAIT', saved)

    def run_pair(self, game):
        results, errors = {}, []
        adapters = {'oas1': FakeSender(game), 'oas2': FakeReceiver(game)}

        def work(instance):
            try:
                coordinator = SyncCoordinator(adapters[instance], instance=instance, members=MEMBERS,
                                              rendezvous_timeout=20, root=self.root, poll_interval=0.02,
                                              lock_timeout=10)
                results[instance] = coordinator.run()
            except BaseException as exc:  # 线程里的异常要带回主线程
                errors.append((instance, exc))

        threads = [threading.Thread(target=work, args=(i,), daemon=True) for i in adapters]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), 'sync did not finish')
        self.assertEqual(errors, [])
        return results

    def test_full_exchange_completes_and_each_side_clicks_once(self):
        game = FakeGame(notify=True)
        results = self.run_pair(game)
        self.assertEqual({k: (v.status, v.next_action) for k, v in results.items()},
                         {'oas1': (S_COMPLETED, NEXT_DONE), 'oas2': (S_COMPLETED, NEXT_DONE)})
        self.assertEqual(game.count('a', 'purchase_tongxin'), 1)
        self.assertEqual(game.count('b', 'repur_tongxin'), 1)
        self.assertEqual((game.dev['a'].total, game.dev['b'].total), (20, 20))

    def test_same_day_second_run_is_already_done_and_touches_nothing(self):
        self.run_pair(FakeGame())
        game = FakeGame()
        results = self.run_pair(game)
        self.assertEqual({k: (v.status, v.next_action) for k, v in results.items()},
                         {'oas1': (S_ALREADY, NEXT_DONE), 'oas2': (S_ALREADY, NEXT_DONE)})
        self.assertEqual(game.log, [])

    def test_missed_toast_is_covered_by_the_peers_return_button(self):
        game = FakeGame(toast_visible=False)
        results = self.run_pair(game)
        self.assertEqual({v.status for v in results.values()}, {S_COMPLETED})

    def test_send_that_did_not_land_stops_for_the_day_without_a_second_purchase(self):
        game = FakeGame(send_works=False)
        results = self.run_pair(game)
        self.assertEqual({v.status for v in results.values()}, {S_FAILED})
        self.assertEqual({v.next_action for v in results.values()}, {NEXT_DEFER})
        self.assertEqual(game.count('a', 'purchase_tongxin'), 1)
        self.assertEqual(game.count('b', 'repur_tongxin'), 0)


if __name__ == '__main__':
    unittest.main()
