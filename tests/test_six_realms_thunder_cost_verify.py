# This Python file uses the following encoding: utf-8
"""孔雀国轰雷购买：扣费核对（D028 补记）。

事故（2026-10-12 oas1 17:46:38）：第二次刷新后识别到 `PK_PK_STORE_SKILL_THUNDER` 并点击，确认弹窗出现并点掉，
0.2s 后金币读到 500（HUD 递减动画的中间帧），D028 的「金币下降即买成」立刻通过、`skill_roaring_thunder` 置 1；
再过 0.3s 金币稳定在 200，实际扣费 ≥300，不是轰雷的 200。之后孔雀国所有商店都 `skip shopping`。

新契约（只对传了 `expected_cost` 的调用生效，目前只有孔雀国轰雷传 200）：
- 购买前取稳定金币（连续两次 OCR 相同），刷新确认后的滞后旧值不当起点；
- 购买后金币连续两次 OCR 相同才比较扣费，等于 `expected_cost` 才计数；
- 扣费对不上或一直不稳定：不计数，结束本次购买（不在同一家店里再点），下一次进店重新尝试；
- 弹窗没出现 / 金币没降：仍按 D028 失败重试，不受影响。
不传 `expected_cost`（月之海）时行为与 D028 完全一致：任何下降都算买成。

测试复用 `test_six_realms_buy_verify` 的时间驱动虚拟商店，只给金币 HUD 加「递减动画」和「刷新后滞后」。
"""

import ast
import inspect
import itertools
import textwrap
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.SixRealms.common import SixRealmsCommon
from tests import test_six_realms_buy_verify as buy_verify
from tests.test_six_realms_buy_verify import SHOT, Sandbox, Shop

THUNDER_COST = 200


class AnimatedShop(Shop):
    """在 `Shop` 上加金币 HUD 动画：扣费后先显示旧值 `coin_lag` 秒，再依次显示 `frames`（每帧 `step` 秒），最后停在新值。

    `hidden_until_refresh=True` 时商品要刷新一次才出现；`refresh(lag)` 扣 100，HUD 在 `lag` 秒后才显示新值。
    """

    def __init__(self, *args, frames=(), step=SHOT, hidden_until_refresh=False):
        super().__init__(*args)
        self.frames = list(frames)
        self.step = step
        self.anim = []
        self.hidden_until_refresh = hidden_until_refresh
        self.refreshed = 0

    def skill_roi(self):
        if self.hidden_until_refresh and not self.refreshed:
            return None
        return super().skill_roi()

    def coin_shown(self):
        if self.hud_at is None:
            return self.coin
        if self.sb.now < self.hud_at:
            return self.prev_coin
        index = int((self.sb.now - self.hud_at) // self.step)
        return self.anim[index] if index < len(self.anim) else self.coin

    def on_confirm_click(self):
        paid = self.dialog_visible() and self.pay
        super().on_confirm_click()
        if paid:
            self.anim = list(self.frames)

    def refresh(self, lag):
        self.refreshed += 1
        self.prev_coin, self.coin = self.coin_shown(), self.coin - 100
        self.hud_at = self.sb.now + lag
        self.anim = []


class ThunderSandbox(Sandbox):
    def setUp(self):
        super().setUp()
        # 业务 logger 会写真实日志文件；这里只验状态
        for target in ('tasks.SixRealms.peacock_kingdom.peacock_kingdom.logger', 'tasks.SixRealms.moon_sea.moon_sea.logger'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_shop(self, cls=SixRealmsCommon, *, frames=(), hidden_until_refresh=False, **kwargs):
        factory = lambda *args: AnimatedShop(*args, frames=frames, hidden_until_refresh=hidden_until_refresh)
        with patch.object(buy_verify, 'Shop', factory):
            task = self.make(cls, **kwargs)
        shop = self.shop
        self.seen = []                                                     # (已刷新次数, HUD 读数)

        def ocr(image):
            value = shop.coin_shown()
            self.seen.append((shop.refreshed, value))
            return value

        self.coin_rule.ocr = Mock(side_effect=ocr)
        return task

    def buy_thunder(self, task, *, expected_cost=THUNDER_COST, buy_num=1):
        return self.run_task(lambda: task.buy_skill(self.skill, 300, self.coin_rule, object(), object(), buy_num,
                                                    expected_cost=expected_cost))

    def make_peacock(self, **kwargs):
        from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom
        task = self.make_shop(PeacockKingdom, coin_num=0, skill_roaring_thunder=0, goto_page=Mock(), **kwargs)
        task.I_PK_STORE_SKILL_THUNDER = self.skill
        task.O_COIN_NUM = self.coin_rule
        task.I_PK_STORE_REFRESH = object()
        task.O_PK_STORE_REFRESH_TIME = object()
        return task


# ======================================================================================
# 一、用户给定的五个场景
# ======================================================================================

class CostCaseTest(ThunderSandbox):
    def test_case1_cost_200_is_counted(self):
        task = self.make_shop(coin=600, price=200)
        coin, bought = self.buy_thunder(task)
        self.assertEqual((coin, bought), (400, 1))
        self.assertTrue(self.has_message('Purchase verified, coin 600 -> 400, cost 200'))

    def test_case2_cost_400_is_rejected(self):
        task = self.make_shop(coin=600, price=400)
        coin, bought = self.buy_thunder(task)
        self.assertEqual(bought, 0)
        self.assertEqual(coin, 200)                                        # 返回的是买后的真实金币，不是点击前的 600
        self.assertTrue(self.has_message('Skill purchase cost mismatch: expected=200 actual=400', 'warning'))
        self.assertTrue(self.has_message(f'{self.skill.name} purchase verification failed, skip current shop.', 'warning'))

    def test_case3_countdown_600_500_400_400_is_counted(self):
        task = self.make_shop(coin=600, price=200, frames=(500,))
        self.assertEqual(self.buy_thunder(task)[1], 1)
        self.assertFalse(self.has_message('cost mismatch', 'warning'))      # 中间帧 500 不参与扣费比较

    def test_case4_countdown_600_500_200_200_is_rejected(self):
        # 17:46:39 的回放：旧验证在 500 这一帧就判买成
        task = self.make_shop(coin=600, price=400, frames=(500,))
        self.assertEqual(self.buy_thunder(task)[1], 0)
        self.assertTrue(self.has_message('Skill purchase cost mismatch: expected=200 actual=400', 'warning'))
        self.assertFalse(self.has_message('Purchase verified'))

    def test_case5_without_expected_cost_any_drop_still_counts(self):
        # 月之海路径：不传 expected_cost，第一帧下降就买成（D028 原样）
        for price, frames in ((200, ()), (400, ()), (200, (500,)), (400, (500,))):
            with self.subTest(price=price, frames=frames):
                self.events.clear()
                self.n = 0
                task = self.make_shop(coin=600, price=price, frames=frames)
                task._wait_coin_stable = Mock(side_effect=AssertionError('默认路径不应等稳定读数'))
                self.assertEqual(self.buy(task)[1], 1)
                self.assertFalse(self.has_message('cost mismatch', 'warning'))


# ======================================================================================
# 二、扣费对不上：本次商店不再买，下一次进店重试
# ======================================================================================

class MismatchStopsShopTest(ThunderSandbox):
    def test_mismatch_does_not_click_the_skill_again_in_the_same_shop(self):
        # 商品仍可见、金币仍够、失败次数没到上限，但已经花了钱、买到的东西不确定，不能再点
        task = self.make_shop(coin=1000, price=400)
        self.assertEqual(self.buy_thunder(task)[1], 0)
        self.assertEqual(len(self.clicks(self.skill.name)), 1)
        task.refresh_store.assert_not_called()

    def test_mismatch_keeps_the_peacock_state_and_the_next_shop_retries(self):
        task = self.make_peacock(coin=600, price=400)
        self.run_task(task.run_on_pk_store)
        self.assertEqual(task.skill_roaring_thunder, 0)
        self.assertEqual(task.coin_num, 200)
        task.goto_page.assert_called_once()

        # 下一次进店：真正的轰雷，扣 200
        self.shop.coin = self.shop.prev_coin = 600
        self.shop.price = 200
        self.shop.hud_at = None
        self.run_task(task.run_on_pk_store)
        self.assertEqual(task.skill_roaring_thunder, 1)
        self.assertEqual(len(self.clicks(self.skill.name)), 2)

    def test_coin_never_stable_after_paying_is_treated_as_mismatch(self):
        frames = tuple(range(580, 400, -20))                              # 动画比验证窗口长，读数一直在变
        task = self.make_shop(coin=600, price=200, frames=frames)
        self.assertEqual(self.buy_thunder(task)[1], 0)
        self.assertTrue(self.has_message('Purchase coin not stable', 'warning'))
        self.assertEqual(len(self.clicks(self.skill.name)), 1)
        self.assertLess(self.n, 60)

    def test_no_confirm_still_retries_like_d028(self):
        task = self.make_shop(coin=600, price=200, attempts=({'dialog': False}, {}))
        self.assertEqual(self.buy_thunder(task)[1], 1)                     # 没花钱的失败不触发「结束本次购买」
        self.assertEqual(len(self.clicks(self.skill.name)), 2)

    def test_no_coin_drop_still_stops_at_the_d028_cap(self):
        task = self.make_shop(coin=600, price=200, attempts=({'pay': False},))
        self.assertEqual(self.buy_thunder(task)[1], 0)
        self.assertEqual(len(self.clicks(self.skill.name)), SixRealmsCommon.BUY_MAX_FAILED_ATTEMPTS)
        self.assertFalse(self.has_message('skip current shop', 'warning'))


# ======================================================================================
# 三、购买前的稳定读数：刷新确认后 HUD 滞后
# ======================================================================================

class StableCoinBeforeTest(ThunderSandbox):
    def _refreshing_shop(self, lag):
        task = self.make_shop(coin=700, price=200, hidden_until_refresh=True)

        def refresh(*args):
            self.now += 1.6                                                # 真机刷新 + 确认约 2s，1.5s 节流已过
            self.shop.refresh(lag)
            return True

        task.refresh_store = Mock(side_effect=refresh)
        return task

    def test_stale_reading_after_refresh_is_not_used_as_coin_before(self):
        # 16:37 的形态：刷新后第一帧仍是刷新前的 700，实际已经是 600
        task = self._refreshing_shop(lag=0.5)
        coin, bought = self.buy_thunder(task)
        self.assertEqual((coin, bought), (400, 1))
        self.assertIn((1, 700), self.seen)                                 # 刷新后确实读到过滞后的旧值
        self.assertTrue(self.has_message(f'Try to buy {self.skill.name}, coin before: 600'))

    def test_unstable_coin_before_is_bounded(self):
        task = self.make_shop(coin=600, price=200)
        self.coin_rule.ocr = Mock(side_effect=itertools.count(990, -10))
        coin = self.run_task(lambda: task._wait_coin_stable(self.coin_rule, 1000))
        self.assertTrue(self.has_message('Coin not stable before purchase', 'warning'))
        self.assertLess(coin, 1000)
        self.assertLess(self.n, 15)

    def test_stable_coin_before_takes_only_one_extra_frame(self):
        task = self.make_shop(coin=600, price=200)
        self.run_task(lambda: task._wait_coin_stable(self.coin_rule, 600))
        self.assertEqual(self.n, 1)


# ======================================================================================
# 四、调用方：只有孔雀国轰雷传 expected_cost
# ======================================================================================

class CallerTest(ThunderSandbox):
    def test_peacock_passes_200_for_verification_and_keeps_the_300_gate(self):
        from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom
        task = PeacockKingdom.__new__(PeacockKingdom)
        task.coin_num = 0
        task.skill_roaring_thunder = 0
        task.goto_page = Mock()
        task.buy_skill = Mock(return_value=(400, 1))
        task.run_on_pk_store()
        call = task.buy_skill.call_args
        self.assertEqual(call.args[1], 300)                                # 门槛不变
        self.assertEqual(call.args[-1], 1)                                 # buy_num 不变
        self.assertEqual(call.kwargs, {'expected_cost': THUNDER_COST})
        self.assertEqual(PeacockKingdom.PK_SKILL_THUNDER_COST, THUNDER_COST)

    def test_moon_sea_does_not_pass_expected_cost(self):
        from tasks.SixRealms.moon_sea.moon_sea import MoonSea
        task = MoonSea.__new__(MoonSea)
        task.cnt_skill101 = 0
        task.coin_num = 0
        task.goto_page = Mock()
        task.buy_skill = Mock(return_value=(150, 1))
        task.run_on_ms_store()
        self.assertNotIn('expected_cost', task.buy_skill.call_args.kwargs)

    def test_expected_cost_defaults_to_none(self):
        for func in (SixRealmsCommon.buy_skill, SixRealmsCommon._confirm_skill_purchase):
            with self.subTest(func=func.__name__):
                self.assertIsNone(inspect.signature(func).parameters['expected_cost'].default)


# ======================================================================================
# 五、结构守卫：没有新增点击；新等待有上限；结束本次购买不计数
# ======================================================================================

class StructureGuardTest(TestCase):
    @staticmethod
    def _tree(func):
        return ast.parse(textwrap.dedent(inspect.getsource(func)))

    def test_stable_read_is_bounded_and_clicks_nothing(self):
        tree = self._tree(SixRealmsCommon._wait_coin_stable)
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.While)]
        self.assertEqual(len(loops), 1)
        calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertTrue(any(call.endswith('.reached') for call in calls))
        self.assertIn('self.screenshot', calls)
        self.assertFalse([call for call in calls if 'click' in call])

    def test_stable_read_only_runs_with_expected_cost(self):
        tree = self._tree(SixRealmsCommon.buy_skill)
        guarded = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                   and ast.unparse(node.test) == 'expected_cost is not None'
                   and '_wait_coin_stable' in ast.unparse(node)]
        self.assertEqual(len(guarded), 1)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and ast.unparse(node.func) == 'self._wait_coin_stable']
        self.assertEqual(len(calls), 1)

    def test_mismatch_branch_breaks_without_counting(self):
        tree = self._tree(SixRealmsCommon.buy_skill)
        branches = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                    and ast.unparse(node.test) == 'verified is None']
        self.assertEqual(len(branches), 1)
        body = branches[0].body
        self.assertIsInstance(body[-1], ast.Break)
        self.assertNotIn('buy_cnt', '\n'.join(ast.unparse(node) for node in body))
