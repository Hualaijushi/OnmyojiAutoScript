from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase

from pydantic import ValidationError

from tasks.KekkaiUtilize.config import UtilizeConfig, UtilizeRule, SelectFriendList
from tasks.KekkaiUtilize.utils import (
    CardClass, FISH_REWARD_TIERS, TAIKO_REWARD_TIERS, lower_reward_tier,
)
from tasks.KekkaiUtilize.script_task import ScriptTask, SearchPass


class FakeTask:
    """只挂载被测纯逻辑方法的最小载体，避免依赖 device 与页面。"""

    CARD_TIER_INFO = ScriptTask.CARD_TIER_INFO
    _rule_card_types = ScriptTask._rule_card_types
    _card_type_matches_rule = ScriptTask._card_type_matches_rule
    _card_meets_pass = ScriptTask._card_meets_pass

    def __init__(self, rule=UtilizeRule.DEFAULT, **kwargs) -> None:
        utilize_config = UtilizeConfig(utilize_rule=rule, **kwargs)
        self.config = SimpleNamespace(
            kekkai_utilize=SimpleNamespace(utilize_config=utilize_config)
        )


def _pass(threshold_map, *, friend=SelectFriendList.DIFFERENT_SERVER,
          stars=frozenset({5, 6}), final=False):
    return SearchPass(friend, stars, threshold_map, final, targets=None)


# --------------------------------------------------------------------------------------
# lower_reward_tier —— 收益「向下取一档」（不是 threshold - 固定数字）
# --------------------------------------------------------------------------------------

class LowerRewardTierTest(TestCase):
    def test_fish_tier_ladder(self):
        expect = {151: 143, 143: 134, 134: 126, 126: 118, 118: 109, 109: 101, 101: 101}
        for value, lower in expect.items():
            self.assertEqual(lower_reward_tier(value, FISH_REWARD_TIERS), lower, value)

    def test_taiko_tier_ladder(self):
        expect = {76: 67, 67: 59, 59: 50, 50: 42, 42: 42}
        for value, lower in expect.items():
            self.assertEqual(lower_reward_tier(value, TAIKO_REWARD_TIERS), lower, value)

    def test_non_tier_input_falls_to_nearest_lower_tier(self):
        # 配置里输入的阈值不一定正好落在档位上
        self.assertEqual(lower_reward_tier(150, FISH_REWARD_TIERS), 143)
        self.assertEqual(lower_reward_tier(144, FISH_REWARD_TIERS), 143)
        self.assertEqual(lower_reward_tier(130, FISH_REWARD_TIERS), 126)
        self.assertEqual(lower_reward_tier(77, TAIKO_REWARD_TIERS), 76)

    def test_below_lowest_tier_keeps_lowest(self):
        self.assertEqual(lower_reward_tier(100, FISH_REWARD_TIERS), 101)
        self.assertEqual(lower_reward_tier(40, TAIKO_REWARD_TIERS), 42)
        self.assertEqual(lower_reward_tier(1, FISH_REWARD_TIERS), 101)

    def test_only_lowers_once_per_call(self):
        # 「降低一档」只发生一次：从 151 一次调用只到 143，不会连降到 134
        self.assertEqual(lower_reward_tier(151, FISH_REWARD_TIERS), 143)
        self.assertEqual(lower_reward_tier(76, TAIKO_REWARD_TIERS), 67)


# --------------------------------------------------------------------------------------
# _card_meets_pass / _card_type_matches_rule —— 按详情 OCR 卡种取本 PASS 阈值 + rule 过滤
# --------------------------------------------------------------------------------------

class CardMeetsPassTest(TestCase):
    def test_at_and_above_threshold_hits(self):
        task = FakeTask()
        p = _pass({'斗鱼': 143, '太鼓': 67})
        self.assertFalse(task._card_meets_pass('斗鱼', 142, p))
        self.assertTrue(task._card_meets_pass('斗鱼', 143, p))
        self.assertTrue(task._card_meets_pass('斗鱼', 151, p))
        self.assertFalse(task._card_meets_pass('太鼓', 59, p))
        self.assertTrue(task._card_meets_pass('太鼓', 67, p))

    def test_unknown_or_non_positive_never_hits(self):
        task = FakeTask()
        p = _pass({'斗鱼': 101, '太鼓': 42})
        self.assertFalse(task._card_meets_pass('unknown', 999, p))
        self.assertFalse(task._card_meets_pass('斗鱼', 0, p))

    def test_taiko_rule_rejects_fish_detail(self):
        task = FakeTask(rule=UtilizeRule.TAIKO)
        p = _pass({'斗鱼': 101, '太鼓': 42})
        self.assertTrue(task._card_meets_pass('太鼓', 42, p))
        self.assertFalse(task._card_meets_pass('斗鱼', 151, p))

    def test_fish_rule_rejects_taiko_detail(self):
        task = FakeTask(rule=UtilizeRule.FISH)
        p = _pass({'斗鱼': 101, '太鼓': 42})
        self.assertTrue(task._card_meets_pass('斗鱼', 101, p))
        self.assertFalse(task._card_meets_pass('太鼓', 76, p))

    def test_default_rule_accepts_both(self):
        task = FakeTask(rule=UtilizeRule.DEFAULT)
        p = _pass({'斗鱼': 151, '太鼓': 76})
        self.assertTrue(task._card_meets_pass('斗鱼', 151, p))
        self.assertTrue(task._card_meets_pass('太鼓', 76, p))

    def test_high_pass_threshold_rejects_low_six_star(self):
        # 6★ 斗鱼也可能只有 118，第一阶段高阈值下不达标
        task = FakeTask()
        high = _pass({'斗鱼': 151, '太鼓': 76}, stars=frozenset({6}))
        self.assertFalse(task._card_meets_pass('斗鱼', 118, high))
        lower = _pass({'斗鱼': 143, '太鼓': 67})
        self.assertFalse(task._card_meets_pass('斗鱼', 118, lower))

    def test_rule_card_types(self):
        self.assertEqual(FakeTask(rule=UtilizeRule.FISH)._rule_card_types(), ('斗鱼',))
        self.assertEqual(FakeTask(rule=UtilizeRule.TAIKO)._rule_card_types(), ('太鼓',))
        self.assertEqual(FakeTask(rule=UtilizeRule.DEFAULT)._rule_card_types(), ('斗鱼', '太鼓'))


class ThresholdConfigTest(TestCase):
    def test_threshold_config_rejects_non_positive(self):
        with self.assertRaises(ValidationError):
            UtilizeConfig(taiko_reward_threshold=0)
        with self.assertRaises(ValidationError):
            UtilizeConfig(fish_reward_threshold=-1)

    def test_default_threshold_equals_six_star_ceiling(self):
        # 默认高阈值 = 六星满值，第一阶段只接受满值 6★
        info = ScriptTask.CARD_TIER_INFO
        config = UtilizeConfig()
        self.assertEqual(config.taiko_reward_threshold, info[CardClass.TAIKO6][2])
        self.assertEqual(config.fish_reward_threshold, info[CardClass.FISH6][2])


class CardTierInfoTest(TestCase):
    def test_tier_ceiling_covers_scanned_classes(self):
        # lazy 模式的 _lazy_card_matches_rule / 高星判断仍读 CARD_TIER_INFO
        for card_class in (
            CardClass.FISH4, CardClass.FISH5, CardClass.FISH6,
            CardClass.TAIKO4, CardClass.TAIKO5, CardClass.TAIKO6,
        ):
            self.assertIn(card_class, ScriptTask.CARD_TIER_INFO)

    def test_tier_ceiling_increases_with_star(self):
        info = ScriptTask.CARD_TIER_INFO
        self.assertLess(info[CardClass.TAIKO4][2], info[CardClass.TAIKO5][2])
        self.assertLess(info[CardClass.TAIKO5][2], info[CardClass.TAIKO6][2])
        self.assertLess(info[CardClass.FISH4][2], info[CardClass.FISH5][2])
        self.assertLess(info[CardClass.FISH5][2], info[CardClass.FISH6][2])


class RemainingTimeFallbackTest(TestCase):
    """寄养剩余时间 OCR 兜底：不能把 next_run 设成当前时刻造成热循环。"""

    FALLBACK = ScriptTask.UTILIZE_RES_TIME_FALLBACK
    MAXIMUM = ScriptTask.UTILIZE_RES_TIME_MAX

    @staticmethod
    def _normalize(remaining, fallback, maximum):
        """与 check_utilize_add 中的判定保持一致的纯函数复刻。"""
        if (not isinstance(remaining, timedelta)
                or remaining <= timedelta(0)
                or remaining > maximum):
            return fallback
        return remaining

    def _run(self, remaining):
        return self._normalize(remaining, self.FALLBACK, self.MAXIMUM)

    def test_fallback_is_positive(self):
        self.assertGreater(self.FALLBACK, timedelta(0))

    def test_ocr_failure_zero_uses_fallback(self):
        self.assertEqual(self._run(timedelta(0)), self.FALLBACK)

    def test_negative_uses_fallback(self):
        self.assertEqual(self._run(timedelta(seconds=-1)), self.FALLBACK)

    def test_non_timedelta_uses_fallback(self):
        for bad in (None, '01:23:45', 0):
            self.assertEqual(self._run(bad), self.FALLBACK)

    def test_absurdly_large_value_uses_fallback(self):
        self.assertEqual(self._run(self.MAXIMUM + timedelta(seconds=1)), self.FALLBACK)

    def test_normal_value_is_kept(self):
        normal = timedelta(hours=3, minutes=20)
        self.assertEqual(self._run(normal), normal)

    def test_boundary_value_is_kept(self):
        self.assertEqual(self._run(self.MAXIMUM), self.MAXIMUM)
        one_second = timedelta(seconds=1)
        self.assertEqual(self._run(one_second), one_second)

    def test_next_run_never_lands_in_the_past(self):
        now = datetime(2026, 8, 30, 12, 0, 0)
        for bad in (timedelta(0), timedelta(seconds=-5), None, 'x'):
            self.assertGreater(now + self._run(bad), now)


class SwitchFriendListTimeoutTest(TestCase):
    def test_timeout_constant_is_positive(self):
        self.assertGreater(ScriptTask.SWITCH_FRIEND_LIST_TIMEOUT, 0)

    def test_switch_friend_list_declares_no_return(self):
        import inspect
        hints = inspect.signature(ScriptTask.switch_friend_list)
        self.assertIs(hints.return_annotation, None)
