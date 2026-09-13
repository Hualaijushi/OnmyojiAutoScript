# This Python file uses the following encoding: utf-8
"""`KekkaiActivation` 状态机迁移前的 characterization（现状锁定）测试。

目的：在把结界挂卡流程迁移到「状态 → 动作 → 期望状态 → 显式验证」结构 **之前**，
用纯 mock 锁住当前真实的动作序列、循环边界、swipe 参数、等待时序，作为未来迁移的
回归基线。

本轮不改 `KekkaiActivation` 任何生产行为——这些测试只描述「现在是什么样」，包括几处
既有瑕疵（`harvest_card` 8 连点前后无截图 / 无验证；`check_card_num` 用 stdlib
`random.randint` 而非公共随机源；多处 `while 1` 无迭代上限）也照实锁定，注释标明未在
本轮修复。详见 `docs/Kekkai状态机静态收口.md`。

源码：`tasks/KekkaiActivation/script_task.py`。
"""

import inspect
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from module.atom.click import RuleClick
from tasks.KekkaiActivation.script_task import ScriptTask as KA
from tasks.KekkaiActivation.config import CardType


# --------------------------------------------------------------------------------------
# harvest_card —— 收取结界卡经验
# --------------------------------------------------------------------------------------

class HarvestCardCharacterizationTest(TestCase):
    """`harvest_card` 当前 = 对同一帧做 8 次 `appear_then_click`，无截图 / 无循环 /
    无验证 / 无 reward popup 处理，返回 None。"""

    EXPECTED_ORDER = [
        'I_A_HARVEST_EXP',
        'I_A_HARVEST_FISH4',
        'I_A_HARVEST_KAIKO_4',
        'I_A_HARVEST_KAIKO_3',
        'I_A_HARVEST_KAIKO_6',
        'I_A_HARVEST_FISH_6',
        'I_A_HARVEST_MOON_3',
        'I_A_HARVEST_FISH_3',
    ]

    def _task(self):
        task = KA.__new__(KA)
        task.screenshot = Mock(name='screenshot')
        return task

    def test_eight_appear_then_click_calls_in_fixed_order(self):
        task = self._task()
        task.appear_then_click = Mock(return_value=False)
        ret = task.harvest_card()

        self.assertIsNone(ret)
        self.assertEqual(task.appear_then_click.call_count, 8)
        targets = [c.args[0].name for c in task.appear_then_click.call_args_list]
        expected_names = [getattr(task, n).name for n in self.EXPECTED_ORDER]
        self.assertEqual(targets, expected_names)

    def test_no_screenshot_no_interval_no_action_kwargs(self):
        task = self._task()
        task.appear_then_click = Mock(return_value=False)
        task.harvest_card()

        task.screenshot.assert_not_called()
        for c in task.appear_then_click.call_args_list:
            self.assertEqual(len(c.args), 1)           # 只有 target 一个位置参数
            self.assertEqual(c.kwargs, {})             # 无 interval / threshold / action

    def test_all_targets_present_still_exactly_eight_calls_no_early_exit(self):
        task = self._task()
        task.appear_then_click = Mock(return_value=True)   # 每次都「点中」
        task.harvest_card()
        self.assertEqual(task.appear_then_click.call_count, 8)

    def test_source_is_linear_no_loop_no_wait_no_verify(self):
        src = inspect.getsource(KA.harvest_card)
        for token in ('self.screenshot', 'while ', 'for ', 'Timer', 'sleep',
                      'wait_until', 'if ', 'return '):
            self.assertNotIn(token, src, token)
        # 恰好 8 行 appear_then_click
        self.assertEqual(src.count('self.appear_then_click('), 8)


# --------------------------------------------------------------------------------------
# check_card_num (KekkaiActivation 覆写) —— 找目标数量的卡 + 列表内 swipe
# --------------------------------------------------------------------------------------

class _OcrResult:
    def __init__(self, text, box=None):
        self.ocr_text = text
        self.box = box or [(10, 20), (40, 20), (40, 50), (10, 50)]


class CheckCardNumActivationTest(TestCase):
    """KA.check_card_num：`while 1` + `ocr_count > 3` 上界；未命中就 `swipe_adb`
    (duration=2) + `sleep(1)`；命中返回一个 name='tmpclick' 的 `RuleClick`。"""

    def _task(self, *, card_type=CardType.TAIKO, min_num=3):
        task = KA.__new__(KA)
        task.device = SimpleNamespace(
            image='FRAME',
            swipe_adb=Mock(name='swipe_adb'),
        )
        task.screenshot = Mock(name='screenshot')
        cfg = SimpleNamespace(card_type=card_type, min_taiko_num=min_num, min_fish_num=min_num)
        task.config = SimpleNamespace(
            kekkai_activation=SimpleNamespace(activation_config=cfg))
        task.O_CHECK_CARD_NUMBER = SimpleNamespace(
            roi=(100, 200, 50, 40),
            detect_and_ocr=Mock(name='detect_and_ocr'),
        )
        return task

    def test_no_result_bounded_by_ocr_count_gt_3(self):
        task = self._task()
        task.O_CHECK_CARD_NUMBER.detect_and_ocr.return_value = []   # 每次都空
        with patch('tasks.KekkaiActivation.script_task.time.sleep') as sleep_mock, \
             patch('tasks.KekkaiActivation.script_task.random.randint', side_effect=[300, 590] * 4):
            ret = task.check_card_num()

        self.assertIsNone(ret)
        # 4 次 OCR（ocr_count 1..4，第 4 次 4>3 直接 return，不再 swipe）
        self.assertEqual(task.O_CHECK_CARD_NUMBER.detect_and_ocr.call_count, 4)
        self.assertEqual(task.screenshot.call_count, 4)
        self.assertEqual(task.device.swipe_adb.call_count, 3)
        self.assertEqual(sleep_mock.call_args_list, [call(1), call(1), call(1)])

    def test_swipe_adb_params_current_shape(self):
        task = self._task()
        task.O_CHECK_CARD_NUMBER.detect_and_ocr.return_value = []
        with patch('tasks.KekkaiActivation.script_task.time.sleep'), \
             patch('tasks.KekkaiActivation.script_task.random.randint', side_effect=[250, 585, 260, 590, 400, 600]):
            task.check_card_num()

        first = task.device.swipe_adb.call_args_list[0]
        p1, p2 = first.args[0], first.args[1]
        self.assertEqual(p1, (250, 585))
        self.assertEqual(p2, (250, 585 - 410))          # 固定位移 410，起点 x 不变
        self.assertEqual(first.kwargs, {'duration': 2})  # duration 是 int 秒，不随机

    def test_uses_stdlib_random_not_common_helper(self):
        # 既有瑕疵：这里用 `tasks.KekkaiActivation.script_task.random`（stdlib），
        # 而 KekkaiUtilize.perform_swipe_action 用公共 `random_int`。本轮不统一。
        src = inspect.getsource(KA.check_card_num)
        self.assertIn('random.randint(', src)
        self.assertNotIn('random_int(', src)

    def test_hit_returns_tmpclick_ruleclick_no_swipe(self):
        task = self._task(min_num=3)
        task.O_CHECK_CARD_NUMBER.detect_and_ocr.return_value = [
            _OcrResult('勾玉 5', box=[(0, 0), (30, 0), (30, 12), (0, 12)]),
        ]
        with patch('tasks.KekkaiActivation.script_task.time.sleep'):
            ret = task.check_card_num()

        self.assertIsInstance(ret, RuleClick)
        self.assertEqual(ret.name, 'tmpclick')
        task.device.swipe_adb.assert_not_called()
        self.assertEqual(task.screenshot.call_count, 1)
        # roi = O_CHECK_CARD_NUMBER.roi[:2] + box 偏移
        self.assertEqual(ret.roi_front, (100 + 0, 200 + 0, 30 - 0, 12 - 0))

    def test_number_below_min_is_ignored_then_swipes(self):
        task = self._task(min_num=6)
        task.O_CHECK_CARD_NUMBER.detect_and_ocr.side_effect = [
            [_OcrResult('勾玉 4')],   # 4 < 6 → 跳过 → 视为无结果
            [_OcrResult('勾玉 8', box=[(0, 0), (30, 0), (30, 12), (0, 12)])],
        ]
        with patch('tasks.KekkaiActivation.script_task.time.sleep'), \
             patch('tasks.KekkaiActivation.script_task.random.randint', side_effect=[300, 590]):
            ret = task.check_card_num()

        self.assertIsInstance(ret, RuleClick)
        self.assertEqual(task.device.swipe_adb.call_count, 1)   # 第 1 屏没达标滑了一次

    def test_unknown_card_type_raises_valueerror(self):
        task = self._task(card_type='not_a_real_type')
        with self.assertRaises(ValueError):
            task.check_card_num()


# --------------------------------------------------------------------------------------
# 循环边界（源码级）—— run_activation / screening_card / check_card_effect
# --------------------------------------------------------------------------------------

class ActivationLoopBoundsTest(TestCase):
    def test_run_activation_is_state_bounded_no_iteration_cap(self):
        src = inspect.getsource(KA.run_activation)
        self.assertIn('while 1:', src)
        # 没有迭代上限 / 总超时：退出全靠 card_status / card_effect 组合命中
        self.assertNotIn('range(', src)
        self.assertNotIn('Timer(', src)
        # 退出点：卡使用中 return False / 激活成功 return True
        self.assertIn('return False', src)
        self.assertIn('return True', src)

    def test_screening_card_has_four_uncapped_while_loops(self):
        # 3 个顶层 `while 1:`（选卡类别 / 点掉类别 / 找最优卡）+ `I_A_EMPTY` 块里 1 个嵌套
        src = inspect.getsource(KA.screening_card)
        self.assertEqual(src.count('while 1:'), 4)
        self.assertNotIn('Timer(', src)
        self.assertNotIn('range(', src)

    def test_check_card_effect_has_uncapped_recovery_loop(self):
        src = inspect.getsource(KA.check_card_effect)
        self.assertIn('while 1:', src)
        self.assertNotIn('Timer(', src)

    def test_check_card_num_activation_is_bounded_by_ocr_count(self):
        src = inspect.getsource(KA.check_card_num)
        self.assertIn('ocr_count > 3', src)
        self.assertIn('return None', src)

    def test_card_not_found_always_ends_with_taskend(self):
        # `_card_not_found` 两条分支最后都 `raise TaskEnd`，所以 target is None 不会死循环
        src = inspect.getsource(KA._card_not_found)
        self.assertIn('raise TaskEnd', src)
        self.assertEqual(len(re.findall(r'set_next_run\(', src)), 1)


# --------------------------------------------------------------------------------------
# 结构事实 —— 入口 / 继承 / FrameWait 零消费者
# --------------------------------------------------------------------------------------

class ActivationStructureTest(TestCase):
    def test_entry_is_run_and_calls_harvest_then_run_activation(self):
        src = inspect.getsource(KA.run)
        self.assertIn('self.goto_page(page_guild_realm)', src)
        self.assertLess(src.index('self.harvest_card()'), src.index('self.run_activation(con)'))
        self.assertIn("raise TaskEnd('KekkaiActivation')", src)

    def test_activation_extends_utilize_scripttask(self):
        from tasks.KekkaiUtilize.script_task import ScriptTask as KU
        self.assertIn(KU, KA.__mro__)
        # KA 覆写了 check_card_num（返回 RuleClick），KU 版本返回 (type, value) 元组
        self.assertIn('check_card_num', KA.__dict__)
        self.assertIn('check_card_num', KU.__dict__)

    def test_no_frame_wait_consumer_in_activation(self):
        src = inspect.getsource(inspect.getmodule(KA))
        for token in ('wait_for_changed_and_stable', 'frame_wait', 'FrameStateDetector',
                      'changed_threshold', 'stable_threshold', 'stable_frames'):
            self.assertNotIn(token, src, token)


if __name__ == '__main__':
    import unittest
    unittest.main()
