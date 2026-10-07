# This Python file uses the following encoding: utf-8
"""SwitchSoul V2：数字模式「分组列表滑到顶」的调度（`SwitchSoul._swipe_group_list_to_top`）。

历史（Git + BehaviorTrace 核实）：这段从 5b032282（2023-08-06）起就是 `while 1` 的「滑一次 → 看一次 → 还没稳定再滑」；
`swipe(…, 6)` 的 6 秒 interval 让它长期只能真滑 1 次，4d74f701（2024-07-22，提交信息「现在可以正确的滑动到最顶部」）
把 interval 改成 0.5 才真正多滑，e4e6be23（2025-03-19）又把它改成 1.5 —— 比一轮约 1 秒的循环还长，第二滑被
`BaseTask.swipe` 的 interval 门静默吞掉（没有日志、不更新计时器），是否放行取决于 OCR 快慢。
2026-10-06 oas1 18:25:09 的真机 BehaviorTrace 里有一次数字模式真滑了 2 次（文本日志的连续相同行去重把它藏起来了）。

V2 的契约：每一滑都是一次独立的 `RuleSwipe` 手势（`sample_endpoints` + `TouchSwipeModel` 每次重新生成），滑完先
`random_delay(*GROUP_TOP_SETTLE)`、再截新图 + OCR，文字与滑之前相同才算到顶；节奏归循环所有，所以数字滑顶这个调用点
不再传 `interval`；真实 swipe 次数最多 `MAX_GROUP_TOP_SWIPES`，达到上限只 warning 并返回 False，业务照常继续。

测试用**真实 `SwitchSoul` / `BaseTask.swipe` / `RuleSwipe.sample_endpoints` / `TouchSwipeModel`**，只替换截图、OCR 和
最底层 `device.swipe_trajectory`；虚拟时钟：截图 0.3 秒、OCR `OCR_COST`、一次 swipe 0.27 秒、`sleep` 推进对应秒数，
`BaseTask` 的 `Timer`（interval 门）读同一个时钟，所以「第二滑会不会被门吞掉」是确定的。
"""

import ast
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.atom.swipe import RuleSwipe
from module.device.device import Device
from module.device.touch_swipe_model import TouchSwipeModel
from module.exception import GameTooManyClickError
from tasks.Component.SwitchSoul import switch_soul as ss
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul

_REPO = Path(__file__).resolve().parents[1]
SOURCE = _REPO / 'tasks' / 'Component' / 'SwitchSoul' / 'switch_soul.py'

SHOT = 0.3            # 虚拟时钟：每次截图
SWIPE_SECONDS = 0.27  # 虚拟时钟：一次 swipe（真机 0.24~0.31 秒）
MAX_SWIPES = SwitchSoul.MAX_GROUP_TOP_SWIPES


class _VTimer:
    """虚拟计时器（`tasks.base_task.Timer` 的替身）：读沙盒的虚拟时钟；未启动时 `reached()` 恒为真，与真实 `Timer` 一致。"""
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


class Sandbox(TestCase):
    OCR_COST = 0.4    # 真机 OCR 约 0.4~0.85 秒；取偏快的值让一轮周期 < 1.5 秒（旧 interval 会吞第二滑）

    def setUp(self):
        self.events = []
        self.now = 0.0
        self.n = 0
        self.ocr_calls = 0
        self.sample_calls = []
        self.generate_calls = []
        self.trajectories = []
        _VTimer.clock = lambda: self.now

    # ---- 构造 ----
    def make(self, observations):
        """`observations[i]` = 第 i 次 OCR 读到的文字列表（可以是字符串或字符串元组）；超出后重复最后一个。"""
        self.observations = observations
        events = self.events

        def screenshot():
            self.n += 1
            self.now += SHOT
            if self.n > 300:
                raise AssertionError('截图次数失控：可能出现了无界循环')
            events.append(('screenshot', self.n))

        def detect_and_ocr(image):
            texts = self.observations[min(self.ocr_calls, len(self.observations) - 1)]
            texts = [texts] if isinstance(texts, str) else list(texts)
            events.append(('ocr', self.ocr_calls, tuple(texts)))
            self.ocr_calls += 1
            self.now += self.OCR_COST
            return [SimpleNamespace(ocr_text=t) for t in texts]

        device = SimpleNamespace(image='F', last_trajectory=None)

        def swipe_trajectory(trajectory, control_name):
            self.trajectories.append(tuple(trajectory))
            device.last_trajectory = list(trajectory)          # 给「缓存上一条轨迹」类变异一个可抓的入口
            self.now += SWIPE_SECONDS
            events.append(('swipe', control_name, round(self.now, 3)))

        device.swipe_trajectory = swipe_trajectory
        task = SwitchSoul.__new__(SwitchSoul)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.config = SimpleNamespace(script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        task.device = device
        task.O_SS_GROUP_NAME = SimpleNamespace(detect_and_ocr=detect_and_ocr)
        return task

    def run_task(self, fn):
        def sleep(seconds):
            self.events.append(('sleep', seconds))
            self.now += seconds

        def delay(lo, hi):
            self.events.append(('delay', lo, hi))
            return lo

        original_sample = RuleSwipe.sample_endpoints

        def spy_sample(rule):
            self.sample_calls.append(rule.name)
            return original_sample(rule)

        def make_model():
            def generate(start, end):
                self.generate_calls.append((start, end))
                return TouchSwipeModel().generate(start, end)
            return SimpleNamespace(generate=generate)

        with patch.object(ss, 'sleep', side_effect=sleep), patch.object(ss, 'random_delay', side_effect=delay), \
                patch.object(ss, 'logger') as logger, patch('tasks.base_task.Timer', _VTimer), \
                patch('tasks.base_task.TouchSwipeModel', side_effect=make_model), \
                patch.object(RuleSwipe, 'sample_endpoints', spy_sample):
            self.logger = logger
            return fn()

    def run_top(self, observations):
        task = self.make(observations)
        return task, self.run_task(task._swipe_group_list_to_top)

    # ---- 断言辅助 ----
    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def swipes(self):
        return self.of('swipe')

    def info_text(self):
        return ' '.join(str(c.args[0]) for c in self.logger.info.call_args_list)


class SwipeCountScenarioTest(Sandbox):
    def test_already_at_top_one_probe_swipe_then_stable(self):
        _, stable = self.run_top(['A', 'A'])
        self.assertTrue(stable)
        self.assertEqual(len(self.swipes()), 1)                                    # 第一轮无条件探测滑一次
        self.assertEqual(self.ocr_calls, 2)                                        # 滑之前一次、滑之后一次，不多做确认
        self.assertIn('stabilized after 1 swipe(s)', self.info_text())
        self.logger.warning.assert_not_called()

    def test_needs_two_swipes(self):
        _, stable = self.run_top(['A', 'B', 'B'])
        self.assertTrue(stable)
        self.assertEqual((len(self.swipes()), self.ocr_calls), (2, 3))
        self.assertIn('after 2 swipe(s), changed=[True, False]', self.info_text())

    def test_needs_three_swipes(self):
        _, stable = self.run_top(['A', 'B', 'C', 'C'])
        self.assertTrue(stable)
        self.assertEqual((len(self.swipes()), self.ocr_calls), (3, 4))

    def test_one_equal_observation_stops_immediately(self):
        # 后面还有会变的文字也不再看：一次相同即停，不要求连续两次相同
        self.run_top(['A', 'A', 'B', 'C', 'D'])
        self.assertEqual((len(self.swipes()), self.ocr_calls), (1, 2))

    def test_single_ocr_jitter_costs_one_extra_swipe_and_terminates(self):
        # A → B（抖动 / 真的又动了一格）→ C → C：有限滑动后停止
        _, stable = self.run_top(['A', 'B', 'C', 'C'])
        self.assertTrue(stable)
        self.assertLessEqual(len(self.swipes()), MAX_SWIPES)

    def test_text_comparison_is_exact_equality_of_the_ordered_list(self):
        self.run_top([('甲', '乙'), ('乙', '甲'), ('乙', '甲')])                    # 顺序不同也算「变了」，沿用原 str(list) 精确比较
        self.assertEqual(len(self.swipes()), 2)


class IntervalGateTest(Sandbox):
    def test_second_swipe_is_not_swallowed_by_an_interval_gate(self):
        task, stable = self.run_top(['A', 'B', 'B'])
        self.assertTrue(stable)
        self.assertEqual(len(self.swipes()), 2)                                    # 两次都真正走到设备层
        # 两次 swipe 结束之间 = settle(0.4) + 截图 0.3 + OCR 0.4 + swipe 0.27 = 1.37 秒 < 旧 interval 1.5
        first, second = (e[2] for e in self.swipes())
        self.assertLess(second - first, 1.5)

    def test_the_old_interval_form_would_have_swallowed_it(self):
        # 同样的节奏下，带 interval=1.5 的旧写法第二次会被 BaseTask.swipe 挡掉（返回 False、不更新计时器、没有日志）
        task = self.make(['A'])
        def old_style():
            first = task.swipe(task.S_SS_GROUP_SWIPE_UP, 1.5)
            self.now += 1.0                                                        # 一轮 settle + 截图 + OCR ≈ 1 秒
            second = task.swipe(task.S_SS_GROUP_SWIPE_UP, 1.5)
            return first, second
        self.assertEqual(self.run_task(old_style), (True, False))
        self.assertEqual(len(self.swipes()), 1)

    def test_numeric_call_site_passes_no_interval(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_swipe_group_list_to_top')
        swipes = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'self.swipe']
        self.assertEqual([ast.unparse(n) for n in swipes], ['self.swipe(self.S_SS_GROUP_SWIPE_UP)'])


class EachSwipeIsAFreshGestureTest(Sandbox):
    def test_every_swipe_resamples_endpoints_and_regenerates_the_trajectory(self):
        self.run_top(['A', 'B', 'C', 'C'])
        self.assertEqual(len(self.swipes()), 3)
        self.assertEqual(len(self.sample_calls), 3)                                # RuleSwipe.sample_endpoints 每滑一次调用一次
        self.assertEqual(set(self.sample_calls), {'ss_group_swipe_up'})
        self.assertEqual(len(self.generate_calls), 3)                              # TouchSwipeModel 每滑一次新建 + generate 一次
        self.assertEqual(len(set(self.trajectories)), 3)                           # 三条轨迹互不相同：没有缓存 / 复用

    def test_swipes_go_through_the_unified_swipe_trajectory_entry(self):
        self.run_top(['A', 'A'])
        self.assertEqual(self.swipes(), [('swipe', 'ss_group_swipe_up', self.swipes()[0][2])])


class SettleTest(Sandbox):
    def test_exactly_one_range_settle_after_every_real_swipe(self):
        self.run_top(['A', 'B', 'C', 'C'])
        delays = self.of('delay')
        self.assertEqual(delays, [('delay', *SwitchSoul.GROUP_TOP_SETTLE)] * 3)    # 3 次 swipe → 3 次 settle，范围 = (0.4, 0.7)
        self.assertEqual(SwitchSoul.GROUP_TOP_SETTLE, (0.4, 0.7))
        for i, event in enumerate(self.events):
            if event[0] == 'swipe':
                # swipe → delay → sleep(刚采样的值) → 新截图 → OCR；settle 与 swipe 一一对应
                self.assertEqual(self.events[i + 1], ('delay', 0.4, 0.7))
                self.assertEqual(self.events[i + 2], ('sleep', 0.4))
                self.assertEqual(self.events[i + 3][0], 'screenshot')
                self.assertEqual(self.events[i + 4][0], 'ocr')

    def test_no_fixed_sleep_and_no_extra_sleep_besides_the_settle(self):
        self.run_top(['A', 'B', 'B'])
        self.assertEqual(self.of('sleep'), [('sleep', 0.4)] * 2)                  # 只有 settle 返回的值，没有固定 0.5 之类
        self.assertEqual(len(self.of('delay')), len(self.swipes()))

    def test_no_delay_when_no_swipe_happens(self):
        task = self.make(['A'])
        self.run_task(lambda: task._group_list_text())
        self.assertEqual(self.of('delay') + self.of('sleep') + self.swipes(), [])


class MaxSwipesTest(Sandbox):
    CHANGING = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

    def test_reaching_the_cap_warns_returns_false_and_never_swipes_again(self):
        _, stable = self.run_top(self.CHANGING)
        self.assertFalse(stable)
        self.assertEqual(len(self.swipes()), MAX_SWIPES)                          # 恰好 MAX 次，不执行第 MAX+1 次
        self.assertEqual(self.ocr_calls, MAX_SWIPES + 1)                          # 最后一滑之后仍然观察了一次
        self.assertEqual(self.logger.warning.call_count, 1)
        self.assertIn(f'not stable after {MAX_SWIPES} swipes', self.logger.warning.call_args.args[0])
        self.assertNotIn('stabilized', self.info_text())

    def test_oscillating_text_is_also_bounded(self):
        _, stable = self.run_top(['A', 'B', 'A', 'B', 'A', 'B', 'A', 'B'])
        self.assertFalse(stable)
        self.assertEqual(len(self.swipes()), MAX_SWIPES)

    def test_stable_on_the_last_allowed_swipe_is_a_success_not_a_warning(self):
        observations = self.CHANGING[:MAX_SWIPES] + [self.CHANGING[MAX_SWIPES - 1]]   # 第 MAX 滑之后文字不再变
        _, stable = self.run_top(observations)
        self.assertTrue(stable)
        self.assertEqual(len(self.swipes()), MAX_SWIPES)
        self.logger.warning.assert_not_called()

    def test_cap_does_not_raise_or_end_the_task(self):
        task = self.make(self.CHANGING)
        self.run_task(task._swipe_group_list_to_top)                              # 不抛 TaskEnd / RequestHumanTakeover / 任何异常

    def test_cap_value_is_below_the_device_guard_even_for_back_to_back_switches(self):
        self.assertLess(MAX_SWIPES, 10)
        self.assertEqual(MAX_SWIPES, 4)


class NoBusyLoopTest(Sandbox):
    def test_between_two_swipes_there_is_settle_screenshot_and_ocr(self):
        self.run_top(['A', 'B', 'C', 'C'])
        kinds = [e[0] for e in self.events]
        swipe_at = [i for i, k in enumerate(kinds) if k == 'swipe']
        for a, b in zip(swipe_at, swipe_at[1:]):
            between = kinds[a + 1:b]
            self.assertEqual(between, ['delay', 'sleep', 'screenshot', 'ocr'])
        self.assertEqual(len(self.of('screenshot')), self.ocr_calls)               # 每次 OCR 前都有一张新截图

    def test_adjacent_swipes_are_spaced_by_a_full_observation_cycle(self):
        self.run_top(['A', 'B', 'C', 'D', 'E', 'F'])
        times = [e[2] for e in self.swipes()]
        for a, b in zip(times, times[1:]):
            self.assertGreaterEqual(b - a, 1.0)                                    # 周期 = swipe + settle + 截图 + OCR，不会快速连滑


class IntegrationWithV1Test(Sandbox):
    def make_switch(self, observations):
        task = self.make(observations)
        order = []
        task._click_group_twice = Mock(side_effect=lambda rule: order.append(('group', self.now, len(self.events))))
        task._click_target_team = Mock(side_effect=lambda rule: order.append(('team', self.now, len(self.events))) or True)
        task._observe_confirm_dialog = Mock(side_effect=lambda: order.append(('observe', self.now, len(self.events))))
        task.ui_click_until_disappear = Mock()
        task.I_SOU_SWITCH_SURE = SimpleNamespace(name='sure')
        task.C_SOU_GROUP_2 = SimpleNamespace(name='group')
        task.I_SOU_SWITCH_2 = SimpleNamespace(name='team')
        return task, order

    def test_group_click_follows_the_last_observation_with_no_extra_wait(self):
        task, order = self.make_switch(['A', 'B', 'B'])
        self.run_task(lambda: task.switch_soul_one(2, 2))
        self.assertEqual([o[0] for o in order], ['group', 'team', 'observe'])
        group_event_count = order[0][2]
        after_slide = self.events[:group_event_count]
        self.assertEqual(after_slide[-1][0], 'ocr')                                # 最后一个事件就是稳定的那次 OCR
        # 滑顶结束到第一次分组点击之间没有任何 sleep / delay / screenshot
        self.assertEqual(self.of('sleep'), [('sleep', 0.4)] * 2)

    def test_business_continues_after_the_cap(self):
        task, order = self.make_switch(MaxSwipesTest.CHANGING)
        self.run_task(lambda: task.switch_soul_one(2, 2))
        self.assertEqual([o[0] for o in order], ['group', 'team', 'observe'])      # 达到上限只 warning，分组 / 队伍照常进行
        self.assertEqual(self.logger.warning.call_count, 1)
        self.assertEqual(len(self.swipes()), MAX_SWIPES)


class StaticFreezeTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE.read_text(encoding='utf-8'))

    def fn(self, name):
        return next(n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef) and n.name == name)

    def test_by_name_swipes_and_intervals_are_untouched(self):
        swipes = [ast.unparse(n) for n in ast.walk(self.fn('switch_soul_by_name'))
                  if isinstance(n, ast.Call) and ast.unparse(n.func) == 'self.swipe']
        self.assertEqual(swipes, ['self.swipe(self.S_SS_GROUP_SWIPE_UP, 2)', 'self.swipe(self.S_SS_GROUP_SWIPE_DOWN)',
                                  'self.swipe(self.S_SS_TEAM_SWIPE_DOWN, 1.5)', 'self.swipe(self.S_SS_TEAM_SWIPE_UP, 0.3)'])
        sleeps = [n.args[0].value for n in ast.walk(self.fn('switch_soul_by_name'))
                  if isinstance(n, ast.Call) and ast.unparse(n.func) == 'sleep' and n.args and isinstance(n.args[0], ast.Constant)]
        self.assertEqual(sleeps, [2.5, 1.5, 2])
        self.assertIn('cnt_click >= 4', ast.unparse(self.fn('switch_soul_by_name')))

    def test_l1_and_the_swipe_model_are_not_referenced_from_switch_soul(self):
        text = SOURCE.read_text(encoding='utf-8')
        for token in ('TouchSwipeModel', 'swipe_trajectory', 'sample_endpoints', 'device.swipe', 'RuleSwipe('):
            self.assertNotIn(token, text)

    def test_random_comes_only_from_the_shared_project_helper(self):
        calls = {ast.unparse(n.func) for n in ast.walk(self.tree) if isinstance(n, ast.Call)}
        self.assertFalse({'random.random', 'random.uniform', 'random.randint', 'random.Random'} & calls)
        helper = ast.unparse(self.fn('_swipe_group_list_to_top'))
        self.assertIn('sleep(random_delay(*self.GROUP_TOP_SETTLE))', helper)

    def test_v1_helpers_are_still_there_with_their_agreed_shape(self):
        for name in ('_click_group_twice', '_click_target_team', '_observe_confirm_dialog', '_confirm_team_switch'):
            self.fn(name)
        self.assertIn('policy=InteractionPolicy.NORMAL', ast.unparse(self.fn('_click_target_team')))
        self.assertIn('policy=InteractionPolicy.CONFIRM', ast.unparse(self.fn('_confirm_team_switch')))
        self.assertIn('random_delay(*self.GROUP_CLICK_GAP)', ast.unparse(self.fn('_click_group_twice')))
        self.assertIn('random_delay(*self.GROUP_SETTLE)', ast.unparse(self.fn('_click_group_twice')))

    def test_slide_helper_has_a_bounded_loop_with_a_warning_exit(self):
        helper = ast.unparse(self.fn('_swipe_group_list_to_top'))
        self.assertIn('self.MAX_GROUP_TOP_SWIPES', helper)
        self.assertIn('logger.warning', helper)
        self.assertNotIn('raise', helper)                                          # 不新增失败契约


class DeviceGuardDerivationTest(TestCase):
    """`MAX_GROUP_TOP_SWIPES = 4` 的依据：Device 对「最近 15 条记录里同名 control ≥10」抛 GameTooManyClickError，
    连续两次切换之间只隔 3 次点击（分组 ×2 + 队伍）。用真实 `Device.click_record_check` 模拟，
    证明 4 即使前后几次切换都滑满上限也不会到 10，而 5 会（所以改大这个常量必须先重新论证）。"""

    def chain(self, max_swipes, switches=4, between=('sou_group_2', 'sou_group_2', 'SS_SOU_SWITCH_1')):
        device = Device.__new__(Device)
        device.click_record = deque(maxlen=15)                                     # 实例属性，不碰类级共享的 deque
        for _ in range(switches):
            for name in ['ss_group_swipe_up'] * max_swipes + list(between):
                device.click_record.append(name)
                Device.click_record_check(device)

    def test_four_swipes_per_switch_never_trip_the_guard_even_back_to_back(self):
        self.chain(4)

    def test_four_is_the_largest_such_value(self):
        with self.assertRaises(GameTooManyClickError):
            self.chain(5)
