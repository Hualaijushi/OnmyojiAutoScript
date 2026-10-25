# This Python file uses the following encoding: utf-8
"""百鬼棋局：上游选择性合入后的行为验证。

被测代码来自上游 xylolit-mu/OnmyojiAutoScript（逐提交记录见 docs/AI_CONTEXT.md §4.134）：
- 631968c6ecee7e992350b3c3713bdf3f7a3bed3f 中 `_buy_shop_slot` / `ui_click_until_disappear` /
  `emergency_cleanup_hand` / `_free_one_hand_slot_for_purchase` 四个函数的改动（购买前置）
- 0501cb195c1b403bd4eec4230c075bd239c10701 清理无腾位时直接卖一张阵容卡
- d944d411bd8fe3932b45f43e80358d28b019c8ba 每次点击循环最多 3 次点击
- 47a3a3bc6173e6560ab8cc3658d3e55bc2c80287 购买成功 / 换卡后清对应格点击记录
- 90a03025cc6af474f013e1a995a1002df254af1c 棋局红叉浮窗 + 鼬乐币 OCR（资产名适配为 I_CHESS_CLOSE_RED）

测试不含实现逻辑：驱动真实的 `_buy_shop_slot`、`BaseTask.ui_click_until_disappear`、
`_free_one_hand_slot_for_purchase`、`sell_one_lineup_hand_card`、
`_click_shop_refresh_and_confirm_slots`、`Device.click_record_remove` 与棋局 `ScriptTask._burst`，
只替换点击、截图、识别、阶段 OCR 和时钟这些外部边界。
"""

import inspect
import json
from collections import deque
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch

from tasks.base_task import BaseTask
from tasks.Chess.runtime.economy import ChessEconomyMixin
from tasks.Chess.runtime.hand_operations import ChessHandOperationsMixin
from tasks.Chess.runtime.settings import ChessRuntimeSettings
from tasks.Chess.strategy.shikigami_catalog import SHIKIGAMI_BY_ROMAJI

TARGET = next(iter(SHIKIGAMI_BY_ROMAJI))
MATCH = {'name': TARGET, 'source': 'name', 'score': 1.0}
FRAME = 0.1
HAS_POLICY = 'policy' in inspect.signature(BaseTask.ui_click_until_disappear).parameters


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Rule:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    __str__ = __repr__


class ClockCase(TestCase):
    def setUp(self):
        self.clock = FakeClock()
        for target in ('time.monotonic', 'time.sleep'):
            fn = self.clock.monotonic if target.endswith('monotonic') else self.clock.sleep
            patcher = patch(target, fn)
            patcher.start()
            self.addCleanup(patcher.stop)


class Harness(ChessEconomyMixin, ChessHandOperationsMixin, ChessRuntimeSettings):
    """只给外部边界替身；ui_click_until_disappear 用 BaseTask 的真实实现。"""

    ui_click_until_disappear = BaseTask.ui_click_until_disappear
    shikigami_deploy_positions = {TARGET: 1, 'lineup_other': 2}

    def __init__(self, clock):
        self.clock = clock
        self.device = MagicMock()
        for index in range(1, 6):
            setattr(self, f'C_SHIKIGAMI_{index}', Rule(f'shikigami_{index}'))
        self.I_REFRESH = Rule('refresh')
        self.I_REFRESH_NOT_GOLD = Rule('refresh_not_gold')
        self.I_EXPERIENCE = Rule('experience')
        self.I_SELECT_GRIGRI = Rule('select_grigri')
        self.mode = '备'
        self.grigri = False
        self.present = lambda h: MATCH
        self.clicks = 0
        self.click_kwargs = []
        self._last_click = {}
        self.frames = 0
        self.cleanup_results = []
        self.cleanup_calls = 0
        self.close_modes = []
        self.shop_reopen_ok = True
        self.reopen_calls = 0
        self.hand = []
        self.sold = []
        self.sale_fails = False

    # ---- 设备 / 识别 ----
    def screenshot(self):
        self.frames += 1
        self.clock.now += FRAME

    def click(self, rule, interval=None, **kwargs):
        # 与 BaseTask.click 一致：给了 interval 时返回值表示是否真的点出去。
        self.click_kwargs.append(kwargs)
        if interval:
            last = self._last_click.get(rule.name)
            if last is not None and self.clock.now - last < interval:
                return False
            self._last_click[rule.name] = self.clock.now
        self.clicks += 1
        return bool(interval)

    def appear(self, rule, *args, **kwargs):
        if rule is self.I_SELECT_GRIGRI:
            return self.grigri
        if rule is self.I_REFRESH:
            return True
        return False

    def _read_chess_mode(self):
        return self.mode

    def _recognize_shop_slot(self, slot_index, click_rule, expected_name=None,
                             fallback_rules=None):
        return self.present(self)

    def _can_afford_shop_shikigami(self, slot_index, known_price=None):
        return True

    def _shikigami_display_name(self, name):
        return str(name)

    # ---- 手牌恢复 ----
    def emergency_cleanup_hand(self):
        self.cleanup_calls += 1
        return self.cleanup_results.pop(0) if self.cleanup_results else None

    def _ensure_shop_open(self):
        self.reopen_calls += 1
        return self.shop_reopen_ok

    def _ensure_shop_closed(self, allowed_modes=('备',)):
        self.close_modes.append(allowed_modes)
        return self.mode in allowed_modes

    def _hand_card_detections(self):
        return [{'roi': card['roi']} for card in self.hand]

    def classify_hand_card(self, roi):
        card = next(item for item in self.hand if item['roi'] == roi)
        return {'type': card['type'], 'name': card['name'],
                'position': card['position']}

    def _hand_card_identity_count(self, card_type, name):
        return sum(1 for card in self.hand
                   if (card['type'], card['name']) == (card_type, name))

    def sell_hand_card(self, position):
        self.sold.append(position)
        if not self.sale_fails:
            self.hand = [c for c in self.hand if c['position'] != position]

    def close_shikigami_specifics_if_open(self):
        return False


def make_hand(*cards):
    return [
        {'roi': (index * 10, 0, 9, 9), 'type': card_type, 'name': name,
         'position': (index * 10 + 4, 4)}
        for index, (card_type, name) in enumerate(cards, start=1)
    ]


NOOP = {'type': 'emergency_cleanup', 'equipped': [], 'sold_non_lineup': []}
FREED = {'type': 'emergency_cleanup', 'equipped': [], 'sold_non_lineup': [(1, 1)]}


class HarnessCase(ClockCase):
    def setUp(self):
        super().setUp()
        self.h = Harness(self.clock)
        self.rule = self.h.C_SHIKIGAMI_3

    def buy(self):
        return self.h._buy_shop_slot(3, self.rule, TARGET)

    def removed_slot_records(self):
        slots = {getattr(self.h, f'C_SHIKIGAMI_{i}') for i in range(1, 6)}
        return [c.args[0] for c in self.h.device.click_record_remove.call_args_list
                if c.args[0] in slots]


class UiClickUntilDisappearTest(ClockCase):
    """公共接口：新增仅关键字参数，默认调用与旧行为一致。"""

    def fake(self, frames, appear_then_click=None):
        seq = iter(frames)
        owner = SimpleNamespace(screenshot=lambda: None,
                                appear=lambda click: next(seq))
        owner.appear_then_click = appear_then_click or MagicMock(return_value=True)
        owner.click = MagicMock(return_value=True)
        return owner

    def test_default_call_matches_old_behavior(self):
        # 旧签名替身：appear_then_click 不接受 policy，默认调用不能多传参数。
        calls = []

        def old_appear_then_click(click, interval=None):
            calls.append(interval)
            return True

        owner = self.fake([True, True, False], old_appear_then_click)
        self.assertTrue(BaseTask.ui_click_until_disappear(owner, Rule('x'), 1))
        self.assertEqual(calls, [1, 1])
        owner = self.fake([False])
        self.assertFalse(BaseTask.ui_click_until_disappear(owner, Rule('x')))
        owner.appear_then_click.assert_not_called()

    def test_guard_failure_returns_false_without_click(self):
        owner = self.fake([True])
        self.assertFalse(BaseTask.ui_click_until_disappear(
            owner, Rule('x'), guard=lambda: False))
        owner.appear_then_click.assert_not_called()

    def test_timeout_returns_false(self):
        owner = SimpleNamespace(appear=lambda c: True,
                                appear_then_click=MagicMock(return_value=False))
        owner.screenshot = lambda: setattr(self.clock, 'now', self.clock.now + FRAME)
        self.assertFalse(BaseTask.ui_click_until_disappear(
            owner, Rule('x'), timeout=1.0))

    def test_single_missing_frame_is_not_disappearance(self):
        owner = self.fake([True, False, True, False, False])
        self.assertTrue(BaseTask.ui_click_until_disappear(
            owner, Rule('x'), confirm_frames=2))
        self.assertEqual(owner.appear_then_click.call_count, 2)

    def test_max_clicks_counts_only_issued_clicks(self):
        issued = iter([False, True, True, False, True, True])
        owner = SimpleNamespace(screenshot=lambda: None, appear=lambda c: True)
        owner.click = MagicMock(side_effect=lambda *a, **k: next(issued))
        self.assertFalse(BaseTask.ui_click_until_disappear(
            owner, Rule('x'), click_target=Rule('t'), max_clicks=3))
        self.assertEqual(owner.click.call_count, 5)

    @skipUnless(HAS_POLICY, '本地 L2 policy 参数只在合入了它的工作区版本中存在')
    def test_policy_is_forwarded_and_absent_by_default(self):
        policy = object()
        owner = self.fake([True, False])
        BaseTask.ui_click_until_disappear(owner, Rule('x'), 1, policy=policy)
        self.assertIs(owner.appear_then_click.call_args.kwargs['policy'], policy)
        owner = self.fake([True, False])
        BaseTask.ui_click_until_disappear(owner, Rule('x'), 1, policy)
        self.assertIs(owner.appear_then_click.call_args.kwargs['policy'], policy)
        owner = self.fake([True, False])
        BaseTask.ui_click_until_disappear(owner, Rule('x'), click_target=Rule('t'),
                                          policy=policy)
        self.assertIs(owner.click.call_args.kwargs['policy'], policy)
        owner = self.fake([True, False])
        BaseTask.ui_click_until_disappear(owner, Rule('x'), click_target=Rule('t'))
        self.assertNotIn('policy', owner.click.call_args.kwargs)


class BuyShopSlotTest(HarnessCase):
    def test_target_missing_before_click_is_not_success(self):
        self.h.present = lambda h: None
        self.assertFalse(self.buy())
        self.assertEqual(self.h.clicks, 0)
        self.h.device.click_record_remove.assert_not_called()

    def test_click_then_two_missing_frames_is_success_and_clears_that_slot(self):
        self.h.present = lambda h: None if h.clicks >= 1 else MATCH
        self.assertTrue(self.buy())
        self.assertEqual(self.h.clicks, 1)
        self.h.device.click_record_remove.assert_called_once_with(self.rule)

    def test_success_needs_retry_after_cleanup(self):
        self.h.cleanup_results = [FREED]
        self.h.present = lambda h: None if h.cleanup_calls >= 1 and h.clicks >= 4 else MATCH
        self.assertTrue(self.buy())
        self.assertEqual(self.h.clicks, 4)
        self.assertEqual(self.h.cleanup_calls, 1)
        self.h.device.click_record_remove.assert_called_once_with(self.rule)

    def test_single_frame_loss_then_reappear_is_not_success(self):
        # 第一次点击后只缺一帧又出现：不能当作买到，继续点。
        seq = iter([MATCH, MATCH, None, MATCH] + [MATCH] * 200)
        self.h.present = lambda h: next(seq)
        self.h.cleanup_results = [NOOP]
        self.h.hand = make_hand(('shikigami', TARGET))
        self.assertFalse(self.buy())
        self.h.device.click_record_remove.assert_not_called()

    def test_each_click_loop_is_capped_at_three_and_purchase_cancels(self):
        # 上游语义：每次 ui_click_until_disappear 最多 3 次点击；初始 + 清理 + 卖阵容卡
        # 三轮仍买不到就取消，合计最多 9 次点击。
        self.h.cleanup_results = [FREED]
        self.h.hand = make_hand(('shikigami', TARGET), ('shikigami', 'lineup_other'))
        self.assertFalse(self.buy())
        self.assertEqual(self.h.clicks, 9)
        self.assertEqual(self.h.cleanup_calls, 1)
        self.assertEqual(len(self.h.sold), 1)
        self.h.device.click_record_remove.assert_not_called()

    def test_noop_cleanup_sells_once_and_cancels_after_second_round(self):
        self.h.cleanup_results = [NOOP]
        self.h.hand = make_hand(('shikigami', TARGET), ('shikigami', 'lineup_other'))
        self.assertFalse(self.buy())
        self.assertEqual(self.h.clicks, 6)
        self.assertEqual(len(self.h.sold), 1)
        self.assertEqual(self.h.cleanup_calls, 1)

    def test_hyakki_mode_stops_purchase(self):
        def present(h):
            if h.clicks:
                h.mode = '鬼'
            return MATCH
        self.h.present = present
        self.assertFalse(self.buy())
        self.assertEqual(self.h.clicks, 1)
        self.assertEqual(self.h.cleanup_calls, 0)

    def test_grigri_popup_stops_purchase(self):
        def present(h):
            if h.clicks:
                h.grigri = True
            return MATCH
        self.h.present = present
        self.assertFalse(self.buy())
        self.assertEqual(self.h.cleanup_calls, 0)
        self.h.device.click_record_remove.assert_not_called()

    def test_recognition_exception_propagates(self):
        def present(h):
            if h.clicks:
                raise RuntimeError('ocr boom')
            return MATCH
        self.h.present = present
        with self.assertRaises(RuntimeError):
            self.buy()
        self.h.device.click_record_remove.assert_not_called()

    def test_shop_reopen_failure_stops_without_more_clicks(self):
        self.h.cleanup_results = [FREED]
        self.h.shop_reopen_ok = False
        self.assertFalse(self.buy())
        self.assertEqual(self.h.clicks, 3)


class HandRecoveryTest(HarnessCase):
    def free(self, sell_lineup=False):
        return self.h._free_one_hand_slot_for_purchase(sell_lineup=sell_lineup)

    def test_cleanup_that_frees_space_does_not_sell_lineup(self):
        self.h.cleanup_results = [FREED]
        self.h.hand = make_hand(('shikigami', TARGET))
        self.assertEqual(self.free()['type'], 'emergency_cleanup')
        self.assertEqual(self.h.sold, [])

    def test_equip_counts_as_freeing_space(self):
        self.h.cleanup_results = [dict(NOOP, equipped=['soul'])]
        self.h.hand = make_hand(('shikigami', TARGET))
        self.assertEqual(self.free()['type'], 'emergency_cleanup')
        self.assertEqual(self.h.sold, [])

    def test_noop_cleanup_sells_rightmost_recognized_lineup_card_only(self):
        self.h.cleanup_results = [NOOP]
        self.h.hand = make_hand(
            ('shikigami', TARGET), ('shikigami', 'not_in_lineup'),
            ('shikigami', 'lineup_other'), ('soul', 'some_soul'), ('unknown', None))
        result = self.free()
        self.assertEqual((result['type'], result['name']), ('lineup', 'lineup_other'))
        self.assertEqual(self.h.sold, [(34, 4)])
        self.assertEqual(self.h.reopen_calls, 1)

    def test_no_safe_sale_target_stops_without_reopening(self):
        self.h.cleanup_results = [NOOP]
        self.h.hand = make_hand(('shikigami', 'not_in_lineup'), ('soul', 's'))
        self.assertIsNone(self.free())
        self.assertEqual((self.h.sold, self.h.reopen_calls), ([], 0))

    def test_unconfirmed_sale_is_not_freed(self):
        self.h.cleanup_results = [NOOP]
        self.h.hand = make_hand(('shikigami', TARGET))
        self.h.sale_fails = True
        self.assertIsNone(self.free())
        self.assertEqual(self.h.reopen_calls, 0)

    def test_phase_change_stops_before_selling(self):
        self.h.hand = make_hand(('shikigami', TARGET))

        def cleanup():
            self.h.mode = '鬼'
            return dict(NOOP)
        self.h.emergency_cleanup_hand = cleanup
        self.assertIsNone(self.free())
        self.assertEqual(self.h.sold, [])

    def test_battle_phase_is_allowed_for_the_lineup_sale_path(self):
        self.h.mode = '战'
        self.h.hand = make_hand(('shikigami', TARGET))
        self.assertEqual(self.free(sell_lineup=True)['type'], 'lineup')
        self.assertEqual(self.h.close_modes, [('备', '战')])
        self.assertEqual(self.h.cleanup_calls, 0)


class ShopRefreshRecordTest(HarnessCase):
    @staticmethod
    def snap(names):
        return {i: {'name': n, 'image': None} for i, n in zip(range(1, 6), names)}

    def refresh(self, snapshots):
        queue = list(snapshots)
        self.h._shop_slot_refresh_snapshot = lambda: queue.pop(0)
        return self.h._click_shop_refresh_and_confirm_slots(allow_hidden=True)

    def test_only_changed_slots_are_cleared_on_confirmed_refresh(self):
        result = self.refresh([self.snap('abcde'), self.snap('axydz')])
        self.assertEqual(result, 'success')
        self.assertEqual({r.name for r in self.removed_slot_records()},
                         {'shikigami_2', 'shikigami_3', 'shikigami_5'})

    def test_unconfirmed_refresh_clears_nothing(self):
        result = self.refresh([self.snap('abcde'), self.snap('axyde'), self.snap('axyde')])
        self.assertEqual(result, 'no_progress')
        self.assertEqual(self.removed_slot_records(), [])

    def test_real_record_removal_keeps_other_buttons(self):
        from module.device.device import Device
        device = SimpleNamespace(click_record=deque(
            ['shikigami_3', 'market', 'shikigami_3', 'shikigami_2', 'other_task'],
            maxlen=15))
        self.assertEqual(Device.click_record_remove(device, Rule('shikigami_3')), 2)
        self.assertEqual(list(device.click_record), ['market', 'shikigami_2', 'other_task'])


class ChessRedCrossAndCoinTest(TestCase):
    def test_burst_closes_red_cross_after_base_checks(self):
        from tasks.Chess.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        with patch.object(BaseTask, '_burst', return_value=False), \
                patch.object(ScriptTask, 'appear_then_click', return_value=True) as click:
            self.assertTrue(task._burst())
        click.assert_called_once_with(ScriptTask.I_CHESS_CLOSE_RED, interval=0.8)
        with patch.object(BaseTask, '_burst', return_value=False), \
                patch.object(ScriptTask, 'appear_then_click', return_value=False):
            self.assertFalse(task._burst())
        with patch.object(BaseTask, '_burst', return_value=True), \
                patch.object(ScriptTask, 'appear_then_click') as click:
            self.assertTrue(task._burst())
        click.assert_not_called()

    def test_red_cross_asset_matches_json_and_does_not_shadow_buff_switch(self):
        import cv2
        from tasks.Chess.script_task import ScriptTask
        from tasks.Component.GeneralBuff.assets import GeneralBuffAssets
        from tasks.GameUi.assets import GameUiAssets
        rule = GameUiAssets.I_CHESS_CLOSE_RED
        entry = next(e for e in json.load(open('tasks/GameUi/page/image_chess.json', encoding='utf-8'))
                     if e['itemName'] == 'chess_close_red')
        self.assertEqual(tuple(rule.roi_front), tuple(map(int, entry['roiFront'].split(','))))
        self.assertEqual(tuple(rule.roi_back), tuple(map(int, entry['roiBack'].split(','))))
        self.assertEqual(rule.file, './tasks/GameUi/page/' + entry['imageName'])
        self.assertIsNotNone(cv2.imread(rule.file))
        self.assertNotIn('I_CLOSE_RED', vars(GameUiAssets))
        self.assertIs(ScriptTask.I_CLOSE_RED, GeneralBuffAssets.I_CLOSE_RED)

    def test_coin_ocr_roi_matches_json(self):
        from tasks.Chess.assets import ChessAssets
        entry = next(e for e in json.load(open('tasks/Chess/c/ocr.json', encoding='utf-8'))
                     if e['itemName'] == 'coin')
        self.assertEqual(tuple(ChessAssets.O_COIN.roi), (406, 660, 87, 25))
        self.assertEqual(entry['roiFront'], '406,660,87,25')
        self.assertEqual(entry['roiBack'], '406,660,87,25')

    def test_local_lineups_and_default_are_kept(self):
        self.assertEqual(ChessRuntimeSettings.DEFAULT_LINEUP_KEY, 'arakawa')
        self.assertEqual(
            set(ChessRuntimeSettings.LINEUP_REGISTRY),
            {'qijiaoshan', 'haiguo', 'dajiangshan', 'huyao', 'mingfu', 'liuhuo', 'arakawa'})
