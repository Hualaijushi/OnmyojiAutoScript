# This Python file uses the following encoding: utf-8
"""SixRealms `buy_skill`：购买成功后才计数（孔雀国六道轰雷漏买 P0）。

事故（2026-10-06 oas1 13:11:54，BehaviorTrace + 文本日志）：商店第 3 行识别到 `PK_PK_STORE_SKILL_THUNDER` 并点了一下，
之后 1.38s 内购买确认弹窗没有出现、金币仍是 500；旧代码在点击当刻 `buy_cnt += 1`，孔雀国传 `buy_num=1`，
立刻 `Buy done` 退出，`run_on_pk_store` 把 `skill_roaring_thunder` 置 1，此后同一轮商店全部 `skip shopping`。
同一天月之海 oas2 13:07:45 也有一次同样的「点了没弹窗」，旧代码因此把 2 次真实购买记成 times: 3。

新契约：点击只是尝试。`_confirm_skill_purchase` 要求 ① 购买确认弹窗在 `BUY_CONFIRM_TIMEOUT` 内出现并被点掉，
② 之后 `BUY_COIN_TIMEOUT` 内金币 OCR 严格小于点击前，两者都满足才 `buy_cnt += 1`；失败不消耗 `buy_num` 配额，
下一轮重新截图 / 识别 / 点击（不复用旧坐标），连续失败达到 `BUY_MAX_FAILED_ATTEMPTS` 才收口。

测试用**真实 `buy_skill` / `_confirm_skill_purchase` / `BaseTask.appear_then_click` / `execute_single_click` /
`ClickSampler`**，只替换截图、识别和最底层 `device.click`；商店是**时间驱动**的虚拟世界（弹窗在点击后延迟出现、
金币 HUD 在扣费后滞后更新），`Timer` 读同一个虚拟时钟，所以「等多久、有没有超时」是确定的。
"""

import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.atom.image import RuleImage
from tasks.SixRealms import common
from tasks.SixRealms.common import SixRealmsCommon

SKILL_ROI = (880, 600, 41, 38)
MOVED_SKILL_ROI = (1080, 130, 41, 38)
CONFIRM_ROI = (700, 400, 140, 60)
SHOT = 0.3
CLICK_COST = 0.12


def _image(name, roi):
    return RuleImage(roi, roi, 'Template matching', 0.8, f'./{name}.png')


class _VTimer:
    """虚拟计时器：读 Sandbox 的虚拟时钟；未启动时 `reached()` 恒为真（与真实 `Timer` 一致）。"""
    clock = None

    def __init__(self, limit, count=0):
        self.limit = limit
        self.count = count
        self._t0 = None

    def start(self):
        self._t0 = _VTimer.clock()
        return self

    def reached(self):
        return self._t0 is None or _VTimer.clock() - self._t0 > self.limit

    def reset(self):
        self._t0 = _VTimer.clock()
        return self


class Shop:
    """时间驱动的虚拟商店。

    `attempts[i]` 描述第 i+1 次点击商品的后果（超出长度沿用最后一项）：
    `dialog=False` 点击落空、弹窗不会出现；`delay` 弹窗出现的延迟；`pay=False` 弹窗点掉后没有扣费。
    金币 HUD 在扣费后 `coin_lag` 秒才显示新值（真机 HUD 滞后）。`skill_rois[k]` 是点了 k 次商品后商品所在位置（None = 不可见）。
    """

    def __init__(self, sandbox, coin, price, attempts, skill_rois, coin_lag):
        self.sb = sandbox
        self.coin = coin
        self.prev_coin = coin
        self.price = price
        self.attempts = attempts
        self.skill_rois = skill_rois
        self.coin_lag = coin_lag
        self.skill_clicks = 0
        self.dialog_at = None
        self.pay = False
        self.hud_at = None

    def skill_roi(self):
        return self.skill_rois[min(self.skill_clicks, len(self.skill_rois) - 1)]

    def dialog_visible(self):
        return self.dialog_at is not None and self.sb.now >= self.dialog_at

    def coin_shown(self):
        if self.hud_at is not None and self.sb.now < self.hud_at:
            return self.prev_coin
        return self.coin

    def on_skill_click(self):
        attempt = self.attempts[min(self.skill_clicks, len(self.attempts) - 1)]
        self.skill_clicks += 1
        self.pay = attempt.get('pay', True)
        self.dialog_at = self.sb.now + attempt.get('delay', 0.5) if attempt.get('dialog', True) else None

    def on_confirm_click(self):
        if not self.dialog_visible():
            return
        self.dialog_at = None
        if self.pay:
            self.prev_coin, self.coin = self.coin, self.coin - self.price
            self.hud_at = self.sb.now + self.coin_lag


class Sandbox(TestCase):
    def setUp(self):
        self.events = []
        self.now = 1000.0
        self.n = 0
        _VTimer.clock = lambda: self.now

    # ---- 构造 ----
    def make(self, cls=SixRealmsCommon, *, coin=500, price=200, attempts=({},), skill_rois=(SKILL_ROI,), coin_lag=0.6,
             **attrs):
        """真实业务类实例（不跑 `__init__`），只接管截图 / 识别 / 设备 / 金币 OCR 四个外部边界。"""
        self.shop = Shop(self, coin, price, list(attempts), list(skill_rois), coin_lag)
        shop, events = self.shop, self.events
        self.skill = _image('sr_skill', SKILL_ROI)
        self.confirm = _image('sr_confirm', CONFIRM_ROI)
        self.coin_rule = SimpleNamespace(ocr=Mock(side_effect=lambda image: shop.coin_shown()), name='coin')

        def screenshot():
            self.n += 1
            self.now += SHOT
            if self.n > 400:
                raise AssertionError('截图次数失控：购买事务出现了无界循环')
            events.append(('screenshot', self.n))

        def appear(target, interval=None, threshold=None):
            if target is self.skill:
                roi = shop.skill_roi()
                if roi is None:
                    return False
                target.roi_front = list(roi)
                return True
            if target is self.confirm:
                return shop.dialog_visible()
            return False

        def click(x, y, control_name=None):
            events.append(('click', control_name, x, y, self.now))
            self.now += CLICK_COST
            if control_name == self.skill.name:
                shop.on_skill_click()
            elif control_name == self.confirm.name:
                shop.on_confirm_click()

        task = cls.__new__(cls)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.appear = appear
        task.device = SimpleNamespace(image='F', click=click)
        task.I_UI_CONFIRM = self.confirm
        task.refresh_store = Mock(return_value=False)
        for key, value in attrs.items():
            setattr(task, key, value)
        return task

    def run_task(self, fn):
        with patch.object(common, 'Timer', _VTimer), patch('tasks.base_task.Timer', _VTimer), \
                patch.object(common, 'logger') as logger:
            self.logger = logger
            return fn()

    def buy(self, task, *, price_param=300, buy_num=1):
        return self.run_task(lambda: task.buy_skill(self.skill, price_param, self.coin_rule, object(), object(), buy_num))

    # ---- 断言辅助 ----
    def clicks(self, name=None):
        return [e for e in self.events if e[0] == 'click' and (name is None or e[1] == name)]

    def messages(self, level='info'):
        return [call.args[0] for call in getattr(self.logger, level).call_args_list]

    def has_message(self, text, level='info'):
        return any(text in message for message in self.messages(level))


# ======================================================================================
# 一、今天的事故：识别到、点了，但没有弹窗、金币没变
# ======================================================================================

class AccidentRegressionTest(Sandbox):
    def test_click_without_confirm_is_not_counted(self):
        task = self.make(coin=500, attempts=({'dialog': False},))
        coin, bought = self.buy(task)
        self.assertEqual(bought, 0)                                        # 13:11:54 的回归：点了不等于买成
        self.assertEqual(coin, 500)                                        # 金币没变，返回值如实反映
        self.assertEqual(len(self.clicks(self.confirm.name)), 0)
        self.assertTrue(self.has_message('Purchase confirm not appeared', 'warning'))
        self.assertFalse(self.has_message(f'Buy {self.skill.name} done'))             # 不会再走「Buy done」假出口

    def test_failed_attempts_stop_after_the_cap_without_unbounded_retry(self):
        task = self.make(coin=500, attempts=({'dialog': False},))
        self.assertEqual(self.buy(task)[1], 0)
        self.assertEqual(len(self.clicks(self.skill.name)), SixRealmsCommon.BUY_MAX_FAILED_ATTEMPTS)
        self.assertTrue(self.has_message('not verified', 'warning'))
        self.assertLess(self.n, 120)

    def test_retry_waits_for_the_confirm_window_before_clicking_again(self):
        task = self.make(coin=500, attempts=({'dialog': False},))
        self.buy(task)
        times = [e[4] for e in self.clicks(self.skill.name)]
        for first, second in zip(times, times[1:]):
            self.assertGreaterEqual(second - first, SixRealmsCommon.BUY_CONFIRM_TIMEOUT)    # 不会 0.1s 内连点同一个商品

    def test_peacock_state_stays_zero_after_the_accident(self):
        from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom
        task = self.make(PeacockKingdom, coin=500, attempts=({'dialog': False},), coin_num=0, skill_roaring_thunder=0,
                         goto_page=Mock())
        task.I_PK_STORE_SKILL_THUNDER = self.skill
        task.O_COIN_NUM = self.coin_rule
        task.I_PK_STORE_REFRESH = object()
        task.O_PK_STORE_REFRESH_TIME = object()
        self.run_task(task.run_on_pk_store)
        self.assertEqual(task.skill_roaring_thunder, 0)                    # 旧代码这里是 1
        self.assertEqual(task.coin_num, 500)
        task.goto_page.assert_called_once()


# ======================================================================================
# 二、成功判据：弹窗被处理 + 金币下降
# ======================================================================================

class VerifiedPurchaseTest(Sandbox):
    def test_confirm_then_coin_drop_counts_once(self):
        task = self.make(coin=500, price=200, attempts=({},))
        coin, bought = self.buy(task)
        self.assertEqual(bought, 1)
        self.assertEqual(coin, 300)                                        # 返回的是买完之后的新金币
        self.assertEqual(len(self.clicks(self.skill.name)), 1)
        self.assertEqual(len(self.clicks(self.confirm.name)), 1)
        self.assertTrue(self.has_message('Purchase verified, coin 500 -> 300'))

    def test_any_positive_price_is_accepted_not_a_fixed_amount(self):
        for price in (100, 200, 300, 450):
            with self.subTest(price=price):
                self.events.clear()
                self.n = 0
                task = self.make(coin=500, price=price, attempts=({},))
                self.assertEqual(self.buy(task)[1], 1)

    def test_confirm_without_coin_change_is_not_counted(self):
        task = self.make(coin=500, attempts=({'dialog': True, 'pay': False},))
        coin, bought = self.buy(task)
        self.assertEqual(bought, 0)
        self.assertEqual(coin, 500)
        self.assertGreaterEqual(len(self.clicks(self.confirm.name)), 1)         # 弹窗点掉了，但没有后验证据
        self.assertTrue(self.has_message('Purchase not verified', 'warning'))

    def test_delayed_coin_hud_still_counts_inside_the_window(self):
        task = self.make(coin=500, price=200, attempts=({},), coin_lag=1.2)
        self.assertEqual(self.buy(task)[1], 1)
        self.assertGreaterEqual(self.coin_rule.ocr.call_count, 3)          # 先读到旧值，轮询后读到新值

    def test_coin_hud_slower_than_the_window_is_bounded_not_counted(self):
        # 第一次真扣费但 HUD 滞后超过窗口；之后的尝试都落空，隔离出「单次事务有界」这一件事
        task = self.make(coin=500, price=200, attempts=({}, {'dialog': False}),
                         coin_lag=SixRealmsCommon.BUY_COIN_TIMEOUT + 1.5)
        self.assertEqual(self.buy(task)[1], 0)                             # 宁可少记也不误记；有界，不无限轮询
        self.assertLess(self.n, 120)

    def test_late_confirm_inside_the_window_is_still_handled(self):
        task = self.make(coin=500, price=200, attempts=({'delay': 1.9},))
        self.assertEqual(self.buy(task)[1], 1)                             # 真机弹窗最慢 0.86s，窗口 2.5s 有余量


# ======================================================================================
# 三、配额：失败不消耗 buy_num（月之海 buy_num=99 / 多次购买）
# ======================================================================================

class QuotaTest(Sandbox):
    def test_failed_attempt_does_not_consume_the_quota(self):
        task = self.make(coin=1000, price=300, attempts=({}, {'dialog': False}, {}))
        coin, bought = self.buy(task, buy_num=2)
        self.assertEqual(bought, 2)                                        # 成功 → 失败 → 成功，配额 2 靠真实成功凑满
        self.assertEqual(len(self.clicks(self.skill.name)), 3)
        self.assertEqual(coin, 400)

    def test_single_quota_is_filled_by_the_retry_after_a_miss(self):
        task = self.make(coin=500, price=200, attempts=({'dialog': False}, {}))
        coin, bought = self.buy(task, buy_num=1)
        self.assertEqual(bought, 1)                                        # 事故场景的理想结局：第二次重新点击买成
        self.assertEqual(len(self.clicks(self.skill.name)), 2)

    def test_unbounded_quota_counts_only_verified_purchases(self):
        # 复现月之海 oas2 13:07：点击、没弹窗、重试买成，再买一次后金币不足；旧代码记 3 次，真实 2 次
        task = self.make(coin=700, price=300, attempts=({'dialog': False}, {}, {}))
        coin, bought = self.buy(task, buy_num=99)
        self.assertEqual(bought, 2)
        self.assertEqual(coin, 100)
        self.assertTrue(self.has_message(f'Not enough coin to buy {self.skill.name}'))

    def test_failure_counter_resets_after_a_success(self):
        miss = {'dialog': False}
        task = self.make(coin=2000, price=300, attempts=(miss, miss, {}, miss, miss, {}))
        coin, bought = self.buy(task, buy_num=2)
        self.assertEqual(bought, 2)                                        # 每段只失败 2 次 < 上限 3，成功后计数清零
        self.assertEqual(len(self.clicks(self.skill.name)), 6)


# ======================================================================================
# 四、失败后的业务循环：重新识别 / 刷新 / 不复用旧坐标
# ======================================================================================

class AfterFailureTest(Sandbox):
    def test_skill_gone_after_a_miss_falls_through_to_refresh(self):
        task = self.make(coin=700, attempts=({'dialog': False},), skill_rois=(SKILL_ROI, None))
        coin, bought = self.buy(task)
        self.assertEqual(bought, 0)
        task.refresh_store.assert_called_once()                            # 失败后现有的「没商品就刷新」照常接管
        self.assertEqual(len(self.clicks(self.skill.name)), 1)

    def test_retry_uses_a_fresh_recognition_not_the_old_coordinates(self):
        task = self.make(coin=500, price=200, attempts=({'dialog': False}, {}), skill_rois=(SKILL_ROI, MOVED_SKILL_ROI))
        self.assertEqual(self.buy(task)[1], 1)
        first, second = self.clicks(self.skill.name)
        x0, y0, w0, h0 = SKILL_ROI
        x1, y1, w1, h1 = MOVED_SKILL_ROI
        self.assertTrue(x0 + w0 // 2 - 60 <= first[2] < x0 + w0 // 2 - 34)
        self.assertTrue(x1 + w1 // 2 - 60 <= second[2] < x1 + w1 // 2 - 34)   # 第二次点在新位置左侧安全区
        self.assertFalse(x0 + w0 // 2 - 60 <= second[2] < x0 + w0 // 2 - 34)

    def test_not_enough_coin_gate_is_unchanged(self):
        task = self.make(coin=200, attempts=({},))
        coin, bought = self.buy(task)
        self.assertEqual((coin, bought), (200, 0))
        self.assertEqual(self.clicks(), [])                                # 金币闸门仍在识别之前，本轮不改


# ======================================================================================
# 五、孔雀国 / 月之海的状态更新只信真实成功次数
# ======================================================================================

class StateUpdateTest(TestCase):
    def setUp(self):
        # 业务 logger 会写真实日志文件，这里只验状态，不往真机日志目录里落测试行
        for target in ('tasks.SixRealms.peacock_kingdom.peacock_kingdom.logger', 'tasks.SixRealms.moon_sea.moon_sea.logger'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _peacock(self, results):
        from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom
        task = PeacockKingdom.__new__(PeacockKingdom)
        task.coin_num = 0
        task.skill_roaring_thunder = 0
        task.goto_page = Mock()
        task.buy_skill = Mock(side_effect=results)
        return task

    def test_zero_verified_purchases_keep_the_state_and_the_next_visit_still_shops(self):
        task = self._peacock([(500, 0), (500, 0)])
        task.run_on_pk_store()
        self.assertEqual(task.skill_roaring_thunder, 0)
        task.run_on_pk_store()
        self.assertEqual(task.buy_skill.call_count, 2)                     # 没有 skip shopping：下一次进店继续找轰雷

    def test_verified_purchase_sets_the_state_and_later_visits_skip(self):
        task = self._peacock([(300, 1)])
        task.run_on_pk_store()
        self.assertEqual(task.skill_roaring_thunder, 1)
        self.assertEqual(task.coin_num, 300)
        task.run_on_pk_store()
        self.assertEqual(task.buy_skill.call_count, 1)                     # 真买成之后原业务语义保持：skip shopping
        self.assertEqual(task.goto_page.call_count, 2)

    def test_buy_quota_stays_one_for_peacock(self):
        task = self._peacock([(300, 1)])
        task.run_on_pk_store()
        args = task.buy_skill.call_args.args
        self.assertEqual(args[-1], 1)

    def test_moon_sea_adds_the_verified_count_to_its_level(self):
        from tasks.SixRealms.moon_sea.moon_sea import MoonSea
        task = MoonSea.__new__(MoonSea)
        task.cnt_skill101 = 3
        task.coin_num = 0
        task.goto_page = Mock()
        task.buy_skill = Mock(return_value=(150, 2))
        task.run_on_ms_store()
        self.assertEqual(task.cnt_skill101, 5)
        self.assertEqual(task.coin_num, 150)
        self.assertNotIn('buy_num', task.buy_skill.call_args.kwargs)       # 月之海继续用默认 buy_num=99


# ======================================================================================
# 六、结构守卫：计数只在验证分支里；事务有界
# ======================================================================================

class StructureGuardTest(TestCase):
    @staticmethod
    def _tree(func):
        return ast.parse(textwrap.dedent(inspect.getsource(func)))

    def test_buy_cnt_increments_only_inside_the_verified_branch(self):
        tree = self._tree(SixRealmsCommon.buy_skill)
        increments = [node for node in ast.walk(tree)
                      if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == 'buy_cnt']
        self.assertEqual(len(increments), 1)
        guarded = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                   and 'self._confirm_skill_purchase(' in ast.unparse(node.test)
                   and any(child is increments[0] for child in node.body)]
        self.assertEqual(len(guarded), 1, '`buy_cnt += 1` 必须直接放在 `if self._confirm_skill_purchase(...)` 的成功分支里')

    def test_click_is_not_followed_by_a_bare_increment(self):
        source = inspect.getsource(SixRealmsCommon.buy_skill)
        click_at = source.index('execute_single_click(')
        between = source[click_at:source.index('self._confirm_skill_purchase(')]
        self.assertNotIn('buy_cnt += 1', between)

    def test_every_wait_loop_in_the_transaction_has_a_timeout(self):
        tree = self._tree(SixRealmsCommon._confirm_skill_purchase)
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.While)]
        self.assertEqual(len(loops), 2)
        for loop in loops:
            calls = [ast.unparse(node.func) for node in ast.walk(loop) if isinstance(node, ast.Call)]
            self.assertTrue(any(call.endswith('.reached') for call in calls), '每个等待循环都必须检查上限')
            self.assertTrue(any(call == 'self.screenshot' for call in calls), '每轮都要重新截图，不复用旧帧')

    def test_transaction_sends_no_extra_click_besides_the_confirm(self):
        tree = self._tree(SixRealmsCommon._confirm_skill_purchase)
        clicks = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and ast.unparse(node.func) in ('self.appear_then_click', 'self.click', 'self.device.click',
                                                 'execute_single_click')]
        self.assertEqual(clicks, ['self.appear_then_click'])

    def test_buy_skill_keeps_its_one_head_confirm_and_one_skill_click(self):
        tree = self._tree(SixRealmsCommon.buy_skill)
        names = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertEqual(names.count('self.appear_then_click'), 1)
        self.assertEqual(names.count('execute_single_click'), 1)
        self.assertIn('Timer', names)                                      # 1.5s 节流保持不动
