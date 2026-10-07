# This Python file uses the following encoding: utf-8
"""SwitchSoul V1：数字模式时序 / 点击节奏改造的回归护栏。

V1 只改 `switch_soul_one` 里「分组两次点击之后」的部分：

- 分组两次补点保留；两次之间 `GROUP_CLICK_GAP`（0.4~0.8）、第二次之后 `GROUP_SETTLE`（0.3~0.6）区间随机等待；
- 队伍不再是 `for range(3)` + `sleep(0.8)`：识别 → NORMAL reaction → fresh confirm → 恰好一次 L1 点击；
- 点击后在有界窗口内观察确认框：出现 → CONFIRM reaction + fresh confirm 点一次，仍在则沿用原 3 秒 interval 重试；
  没出现（已经装备同一预设）按原业务语义正常结束，不是失败；
- 常驻的假 warning「Click team N failed」消失。

OCR by-name 模式完全不动，这里只钉「没被碰」。滑顶调度 V1 时也不动；V2（2026-10-06）起改成
`_swipe_group_list_to_top`，其细节由 `tests/test_switch_soul_group_top_v2.py` 覆盖，本文件里原先钉死旧滑顶形态
（`swipe(…, 1.5)` + `sleep(0.5)`）的两条断言随之改写，其余 V1 行为断言不变。

测试用**真实 `SwitchSoul` 方法 + 真实 `BaseTask.appear_then_click` / `click` / `ui_click_until_disappear`**，只替换
截图 / 识别 / 设备三个外部边界：`frames[n]` = 第 n 次截图之后可见目标的 roi 映射（`frames[0]` = 进入前的当前帧）。
虚拟时钟：每次截图推进 0.3 秒（与 `screenshot_interval=0.3` 一致）、`sleep` 推进对应秒数，`Timer` 读虚拟时钟，
所以 3 秒 interval / 有界窗口的行为是确定的，不依赖真实时间。
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp
from module.atom.click import RuleClick
from module.atom.image import RuleImage
from tasks.Component.SwitchSoul import switch_soul as ss
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul

_REPO = Path(__file__).resolve().parents[1]
SOURCE = _REPO / 'tasks' / 'Component' / 'SwitchSoul' / 'switch_soul.py'

GROUP_ROI = (1087, 155, 162, 48)
TEAM_ROI = (978, 303, 25, 26)
TEAM_MOVED = (700, 450, 25, 26)         # 与 TEAM_ROI 完全不相交：落点落在哪个框里一眼能分辨
SURE_ROI = (668, 401, 180, 61)
BLOCK_ROI = (572, 408, 137, 49)
SHOT = 0.3                              # 虚拟时钟：每次截图耗时


def _image(name, roi):
    return RuleImage(roi, roi, 'Template matching', 0.8, f'./{name}.png')


def _inside(point, roi):
    x, y, w, h = roi
    return x <= point[0] < x + w and y <= point[1] < y + h


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


class Sandbox(TestCase):
    TEAM, SURE, BLOCK, GROUP = 'SW_TEAM', 'SW_SURE', 'SW_BLOCK', 'sw_group'

    def setUp(self):
        self.events = []
        self.now = 0.0
        self.n = 0
        _VTimer.clock = lambda: self.now

    # ---- 构造 ----
    def make(self, frames):
        """真实 SwitchSoul 实例（不跑 `__init__`），只接管截图 / 识别 / 设备 / 滑动四个外部边界。"""
        self.frames = frames
        self.team, self.sure, self.block = _image('sw_team', TEAM_ROI), _image('sw_sure', SURE_ROI), _image('sw_block', BLOCK_ROI)
        events = self.events

        def screenshot():
            self.n += 1
            self.now += SHOT
            if self.n > 300:
                raise AssertionError('截图次数失控：可能出现了无界循环')
            events.append(('screenshot', self.n))

        def appear(target, interval=None, threshold=None):
            visible = self.frames[min(self.n, len(self.frames) - 1)].get(target.name)
            if visible is not None and isinstance(target, RuleImage):
                target.roi_front = list(visible)
            return visible is not None

        def click(x, y, control_name):
            events.append(('click', control_name, x, y, round(self.now, 3)))

        task = SwitchSoul.__new__(SwitchSoul)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.appear = appear
        task.device = SimpleNamespace(image='F', click=Mock(side_effect=click))
        task.I_SOU_SWITCH_2 = self.team
        task.I_SOU_SWITCH_SURE = self.sure
        task.I_CHECK_BLOCK = self.block
        task.C_SOU_GROUP_2 = RuleClick(GROUP_ROI, GROUP_ROI, name=self.GROUP)
        # 滑顶阶段只做桩：OCR 永远读到同一段文本 → 第 1 轮盲滑一次、第 2 轮判停（原逻辑不动）
        task.O_SS_GROUP_NAME = SimpleNamespace(detect_and_ocr=lambda image: [])
        task.swipe = Mock(side_effect=lambda swipe, interval=None: events.append(('swipe', swipe.name, interval)))
        return task

    def run_task(self, fn):
        def sleep(seconds):
            self.events.append(('sleep', seconds))
            self.now += seconds

        def base_sleep(seconds):
            self.events.append(('reaction_sleep', seconds))
            self.now += seconds

        def delay(lo, hi):
            self.events.append(('delay', lo, hi))
            return lo

        def reaction(lo, hi):
            self.events.append(('reaction', lo, hi))
            return lo

        with patch.object(ss, 'sleep', side_effect=sleep), patch.object(ss, 'random_delay', side_effect=delay), \
                patch.object(ss, 'Timer', _VTimer), patch.object(ss, 'logger') as logger, \
                patch('tasks.base_task.sleep', side_effect=base_sleep), \
                patch('tasks.base_task.random_delay', side_effect=reaction), patch('tasks.base_task.Timer', _VTimer):
            self.logger = logger
            return fn()

    def switch_one(self, task):
        return self.run_task(lambda: task.switch_soul_one(2, 2))

    # ---- 断言辅助 ----
    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def clicks(self, name=None):
        return [e for e in self.of('click') if name is None or e[1] == name]

    def click_names(self):
        return [e[1] for e in self.of('click')]


# 进入 `switch_soul_one` 后先过滑顶阶段：frame 0 = 进入前，frame 1 / 2 = 滑顶两轮的截图
SWIPE_PHASE = [{}, {}, {}]


class NormalNewPresetTest(Sandbox):
    """目标队伍存在 → 点一次 → 确认框出现 → 确认 → 消失。"""

    def frames(self):
        return SWIPE_PHASE + [
            {self.TEAM: TEAM_ROI},      # 3 识别 target_team
            {self.TEAM: TEAM_ROI},      # 4 reaction 后 fresh confirm
            {self.SURE: SURE_ROI},      # 5 观察窗口内看到确认框
            {self.SURE: SURE_ROI},      # 6 CONFIRM reaction 后 fresh confirm
            {},                         # 7 恢复循环：确认框已消失
            {},                         # 8 末尾兜底 ui_click_until_disappear
        ]

    def test_normal_switch_clicks_group_twice_team_once_and_sure_once(self):
        task = self.make(self.frames())
        self.switch_one(task)
        self.assertEqual(self.click_names(), [self.GROUP, self.GROUP, self.team.name, self.sure.name])
        self.logger.warning.assert_not_called()                     # 不再有常驻的假「Click team N failed」

    def group_delays(self):
        """V1 的两段分组 delay；V2 滑顶 settle（`GROUP_TOP_SETTLE`）是滑顶阶段的，单独由 V2 测试覆盖，这里滤掉。"""
        return [d for d in self.of('delay') if d[1:] != ss.SwitchSoul.GROUP_TOP_SETTLE]

    def test_slide_phase_runs_before_the_group_clicks_and_adds_no_fixed_wait(self):
        # V1 原来在这里钉「interval=1.5 + sleep(0.5)」；V2 起滑顶节奏归 `_swipe_group_list_to_top`，
        # 细节由 `test_switch_soul_group_top_v2.py` 覆盖。这里只保留与 V1 有关的边界：
        # 已在顶部时恰好一次探测 swipe，且滑顶先于第一次分组点击、没有任何固定 0.5 秒等待。
        task = self.make(self.frames())
        self.switch_one(task)
        swipes = self.of('swipe')
        self.assertEqual(swipes, [('swipe', 'ss_group_swipe_up', None)])
        kinds = [e[0] if e[0] != 'click' else e[1] for e in self.events]
        self.assertLess(kinds.index('swipe'), kinds.index(self.GROUP))
        self.assertEqual([e for e in self.of('sleep') if e[1] == 0.5], [])        # 分组间隔 / 滑顶 settle 都不是固定 0.5

    def test_group_clicks_are_two_with_a_range_gap_then_a_range_settle(self):
        task = self.make(self.frames())
        self.switch_one(task)
        delays = self.group_delays()
        self.assertEqual(delays, [('delay', *ss.SwitchSoul.GROUP_CLICK_GAP), ('delay', *ss.SwitchSoul.GROUP_SETTLE)])
        self.assertEqual((ss.SwitchSoul.GROUP_CLICK_GAP, ss.SwitchSoul.GROUP_SETTLE), ((0.4, 0.8), (0.3, 0.6)))
        kinds = [e[0] if e[0] != 'click' else e[1] for e in self.events]
        first_group = kinds.index(self.GROUP)
        second_group = kinds.index(self.GROUP, first_group + 1)
        # 点击 #1 → 两次之间的间隔 → 点击 #2 → 第二次之后的 settle → 才进入队伍阶段的第一次截图
        self.assertEqual(self.events[first_group + 1][0:2], ('delay', 0.4))
        self.assertEqual(self.events[first_group + 2], ('sleep', 0.4))
        self.assertEqual(self.events[second_group + 1][0:2], ('delay', 0.3))
        self.assertEqual(self.events[second_group + 2], ('sleep', 0.3))
        self.assertEqual(self.events[second_group + 3][0], 'screenshot')

    def test_gap_and_settle_are_independent_samples_not_one_helper_with_one_range(self):
        task = self.make(self.frames())
        self.switch_one(task)
        gap, settle = self.group_delays()
        self.assertNotEqual(gap[1:], settle[1:])

    def test_team_click_goes_through_normal_reaction_then_fresh_confirm(self):
        task = self.make(self.frames())
        self.switch_one(task)
        reactions = self.of('reaction')
        self.assertEqual([r[1:] for r in reactions], [rp.REACTION_NORMAL, rp.REACTION_CONFIRM])   # 队伍 NORMAL、确认 CONFIRM，各一次
        kinds = [e[0] if e[0] != 'click' else e[1] for e in self.events]
        team_at = kinds.index(self.team.name)
        # 识别 → reaction → sleep → fresh 截图 → 才点击（队伍点击前恰好经过一次 reaction 与一次 fresh 截图）
        self.assertEqual(kinds[team_at - 3:team_at + 1], ['reaction', 'reaction_sleep', 'screenshot', self.team.name])

    def test_confirm_sure_goes_through_confirm_reaction_then_fresh_confirm(self):
        task = self.make(self.frames())
        self.switch_one(task)
        kinds = [e[0] if e[0] != 'click' else e[1] for e in self.events]
        sure_at = kinds.index(self.sure.name)
        self.assertEqual(kinds[sure_at - 3:sure_at + 1], ['reaction', 'reaction_sleep', 'screenshot', self.sure.name])
        self.assertEqual(self.of('reaction')[1][1:], rp.REACTION_CONFIRM)

    def test_no_old_third_round_no_fixed_08_sleep(self):
        task = self.make(self.frames())
        self.switch_one(task)
        self.assertEqual([e for e in self.of('sleep') if e[1] == 0.8], [])
        self.assertEqual(len(self.clicks(self.team.name)), 1)                      # 队伍恰好点一次，没有第三轮补点

    def test_team_is_clicked_at_the_fresh_frame_position(self):
        frames = SWIPE_PHASE + [{self.TEAM: TEAM_ROI}, {self.TEAM: TEAM_MOVED}, {self.SURE: SURE_ROI},
                                {self.SURE: SURE_ROI}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)
        x, y = self.clicks(self.team.name)[0][2:4]
        self.assertTrue(_inside((x, y), TEAM_MOVED))
        self.assertFalse(_inside((x, y), TEAM_ROI))                                # 旧坐标没被用

    def test_group_clicks_land_inside_the_group_roi_and_are_resampled(self):
        task = self.make(self.frames())
        self.switch_one(task)
        points = [(e[2], e[3]) for e in self.clicks(self.GROUP)]
        self.assertEqual(len(points), 2)
        for point in points:
            self.assertTrue(_inside(point, GROUP_ROI))


class AlreadyEquippedTest(Sandbox):
    """队伍点击后确认框始终不出现（已经装备同一预设）：有界观察后正常结束。"""

    def frames(self):
        return SWIPE_PHASE + [{self.TEAM: TEAM_ROI}, {self.TEAM: TEAM_ROI}] + [{}]

    def test_finishes_normally_without_warning_or_second_team_click(self):
        task = self.make(self.frames())
        self.switch_one(task)
        self.assertEqual(self.click_names(), [self.GROUP, self.GROUP, self.team.name])
        self.logger.warning.assert_not_called()
        info_texts = ' '.join(str(c.args[0]) for c in self.logger.info.call_args_list)
        self.assertIn('No confirm dialog', info_texts)                              # 只有 info，不是失败

    def test_observation_window_is_bounded_and_does_not_busy_loop(self):
        task = self.make(self.frames())
        self.switch_one(task)
        team_click = next(e for e in self.events if e[0] == 'click' and e[1] == self.team.name)
        shots_after_click = [e for e in self.events[self.events.index(team_click):] if e[0] == 'screenshot']
        # 窗口 2.0 秒、每次截图 0.3 秒：约 7 次观察截图 + 末尾兜底 1 次；每次观察都先截图，不空转
        self.assertGreaterEqual(len(shots_after_click), 7)
        self.assertLessEqual(len(shots_after_click), 9)
        # 点击之后到结束不超过：窗口 + 一次观察截图 + 一次兜底截图
        self.assertLessEqual(self.now - team_click[4], SwitchSoul.TEAM_RESPONSE_TIMEOUT + 2 * SHOT + 1e-9)

    def test_window_constants_match_the_agreed_range(self):
        self.assertTrue(1.5 <= SwitchSoul.TEAM_RESPONSE_TIMEOUT <= 2.0)
        self.assertGreater(SwitchSoul.TEAM_FIND_TIMEOUT, SwitchSoul.TEAM_RESPONSE_TIMEOUT)


class TeamGoneTest(Sandbox):
    def test_team_vanishes_during_reaction_is_not_clicked_with_the_old_position(self):
        # frame 3 识别到、frame 4（fresh）消失，之后一直不出现
        task = self.make(SWIPE_PHASE + [{self.TEAM: TEAM_ROI}, {}])
        self.switch_one(task)
        self.assertEqual(self.clicks(self.team.name), [])                           # 0 点击：不点旧坐标
        self.assertEqual(self.click_names(), [self.GROUP, self.GROUP])
        self.assertEqual(self.logger.warning.call_count, 1)                         # 真正没点出去才允许 warning
        self.assertIn('not found', self.logger.warning.call_args.args[0])
        self.assertNotIn('failed', self.logger.warning.call_args.args[0])

    def test_find_window_is_bounded_when_the_team_never_appears(self):
        task = self.make(SWIPE_PHASE + [{}])
        self.switch_one(task)
        self.assertEqual(self.clicks(self.team.name), [])
        self.assertEqual(self.of('reaction'), [])                                   # 目标没出现不触发 reaction
        team_phase = [e for e in self.of('screenshot') if e[1] > 2]
        # 窗口 3.0 秒，每次截图 0.3 秒：约 10 次 + 末尾兜底 1 次，有界
        self.assertLessEqual(len(team_phase), 13)

    def test_team_that_reappears_later_is_clicked_once_at_the_new_position(self):
        frames = SWIPE_PHASE + [{self.TEAM: TEAM_ROI}, {}, {self.TEAM: TEAM_MOVED}, {self.TEAM: TEAM_MOVED}, {}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)
        team_clicks = self.clicks(self.team.name)
        self.assertEqual(len(team_clicks), 1)
        self.assertTrue(_inside(team_clicks[0][2:4], TEAM_MOVED))
        self.assertEqual(len(self.of('reaction')), 2)                               # 每次真实 attempt 各自一次 reaction

    def test_list_refresh_latency_is_polled_not_clicked_early(self):
        frames = SWIPE_PHASE + [{}, {}, {self.TEAM: TEAM_ROI}, {self.TEAM: TEAM_ROI}, {}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)
        self.assertEqual(len(self.clicks(self.team.name)), 1)
        self.assertEqual(len(self.of('reaction')), 1)


class SureTest(Sandbox):
    def prefix(self):
        return SWIPE_PHASE + [{self.TEAM: TEAM_ROI}, {self.TEAM: TEAM_ROI}]

    def test_sure_vanishes_during_confirm_reaction_is_not_clicked(self):
        frames = self.prefix() + [{self.SURE: SURE_ROI}, {}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)
        self.assertEqual(self.clicks(self.sure.name), [])                           # 0 点击
        self.assertEqual(self.click_names(), [self.GROUP, self.GROUP, self.team.name])
        self.assertEqual(len(self.of('reaction')), 2)                               # 队伍 NORMAL + 确认 CONFIRM，各一次，没有无界重试
        self.logger.warning.assert_not_called()

    def test_stuck_dialog_retries_on_the_original_three_second_interval_without_reaction(self):
        # 确认框在首次点击后持续存在：frame 5 起可见，到 frame 17 之后才消失
        stuck = [{self.SURE: SURE_ROI}] * 13
        frames = self.prefix() + stuck + [{}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)
        sure_clicks = self.clicks(self.sure.name)
        self.assertEqual(len(sure_clicks), 2)                                       # 首次确认 + 一次恢复重试
        self.assertGreater(sure_clicks[1][4] - sure_clicks[0][4], 3.0)              # 原 interval=3 保护仍在：不会更早重点
        self.assertEqual(len(self.of('reaction')), 2)                               # 队伍 NORMAL + 首次 CONFIRM；重试不叠加 reaction
        # 重试之前每一轮恢复循环都先截图（不空转）：两次点击之间的截图数 ≥ 3 秒 / 0.3 秒
        between = [e for e in self.events[self.events.index(sure_clicks[0]):self.events.index(sure_clicks[1])]
                   if e[0] == 'screenshot']
        self.assertGreaterEqual(len(between), 10)
        self.logger.warning.assert_not_called()

    def test_stuck_dialog_eventually_clears_and_the_flow_exits(self):
        frames = self.prefix() + [{self.SURE: SURE_ROI}] * 8 + [{}, {}, {}]
        task = self.make(frames)
        self.switch_one(task)                                                       # 能退出即证明没有死循环
        self.assertEqual(len(self.clicks(self.sure.name)), 1)                       # 3 秒内消失 → 不需要重试

    def test_check_block_is_still_handled_inside_the_confirm_recovery_loop(self):
        frames = self.prefix() + [
            {self.SURE: SURE_ROI}, {self.SURE: SURE_ROI},       # 5 / 6：观察到确认框 + fresh confirm → 点 SURE
            {self.BLOCK: BLOCK_ROI},                            # 7：误触到式神检查，SURE 不在
            {}, {}, {},
        ]
        task = self.make(frames)
        self.switch_one(task)
        names = self.click_names()
        self.assertEqual(names.count(self.block.name), 1)                          # 保护仍可处理
        self.assertLess(names.index(self.sure.name), names.index(self.block.name))  # 先确认、后处理误触
        self.assertEqual(names[-1], self.block.name)


class DirectHelperTest(Sandbox):
    """直接驱动 helper：frame 0 就是当前帧。"""

    def test_click_target_team_returns_true_after_exactly_one_click(self):
        task = self.make([{self.TEAM: TEAM_ROI}, {self.TEAM: TEAM_ROI}])
        self.assertTrue(self.run_task(lambda: task._click_target_team(task.I_SOU_SWITCH_2)))
        self.assertEqual(len(self.clicks(self.team.name)), 1)

    def test_click_target_team_returns_false_when_never_clicked(self):
        task = self.make([{}])
        self.assertFalse(self.run_task(lambda: task._click_target_team(task.I_SOU_SWITCH_2)))
        self.assertEqual(self.clicks(), [])

    def test_observe_returns_whether_a_dialog_was_seen(self):
        task = self.make([{}])
        self.assertFalse(self.run_task(task._observe_confirm_dialog))
        self.events.clear()
        self.n, self.now = 0, 0.0
        task = self.make([{}, {self.SURE: SURE_ROI}, {self.SURE: SURE_ROI}, {}])     # 观察帧 / CONFIRM reaction 后 fresh 帧 / 确认框已消失
        self.assertTrue(self.run_task(task._observe_confirm_dialog))
        self.assertEqual(len(self.clicks(self.sure.name)), 1)


def _function(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')


class StaticStructureTest(TestCase):
    """AST 只钉「结构没被改回去 / 没有绕过 L1 / 没被碰的部分还在」，不替代上面的运行期用例。"""

    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.text)

    def test_old_three_round_loop_and_false_failed_warning_are_gone(self):
        fn = _function(self.tree, 'switch_soul_one')
        loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)
                 and isinstance(n.iter, ast.Call) and _call_name(n.iter) == 'range']
        self.assertEqual(loops, [])                                                 # 没有 for range(...)
        floats = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
        self.assertNotIn(0.8, floats)
        self.assertNotIn('Click team', self.text)
        self.assertNotIn('failed in group', self.text)

    def test_l1_unchanged_no_raw_device_click_and_no_backend_calls(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                chain = ast.unparse(node.func)
                self.assertFalse(chain.endswith('device.click'), chain)
                self.assertFalse(node.func.attr.startswith('click_') and node.func.attr != 'click_preset', chain)
        # 分组仍走 BaseTask.click（两次，各自独立采样）
        group = _function(self.tree, '_click_group_twice')
        self_clicks = [n for n in ast.walk(group) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'self.click']
        self.assertEqual(len(self_clicks), 2)

    def test_exactly_two_policy_clicks_with_the_agreed_policies_and_no_confirm_delay(self):
        found = []
        for fn in (n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)):
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) == 'appear_then_click'):
                keywords = {kw.arg: ast.unparse(kw.value) for kw in call.keywords}
                self.assertNotIn('confirm_delay', keywords)
                if 'policy' in keywords:
                    found.append((fn.name, ast.unparse(call.args[0]), keywords['policy']))
        self.assertEqual(sorted(found), [
            ('_click_target_team', 'target_team', 'InteractionPolicy.NORMAL'),
            ('_confirm_team_switch', 'self.I_SOU_SWITCH_SURE', 'InteractionPolicy.CONFIRM'),
        ])

    def test_reaction_never_stacks_with_a_local_random_delay_in_the_same_function(self):
        for fn in (n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)):
            calls = {_call_name(n) for n in ast.walk(fn) if isinstance(n, ast.Call)}
            with self.subTest(func=fn.name):
                policy_click = any(isinstance(n, ast.Call) and _call_name(n) == 'appear_then_click'
                                   and any(kw.arg == 'policy' for kw in n.keywords) for n in ast.walk(fn))
                self.assertFalse(policy_click and 'random_delay' in calls)

    def test_random_comes_only_from_the_shared_project_helper(self):
        imports = [n for n in ast.walk(self.tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        modules = {getattr(n, 'module', None) for n in imports if isinstance(n, ast.ImportFrom)}
        self.assertIn('module.base.utils.random', modules)
        self.assertNotIn('random', {alias.name for n in imports if isinstance(n, ast.Import) for alias in n.names})
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                self.assertNotIn(ast.unparse(node.func), ('random.random', 'random.uniform', 'random.randint', 'random.Random'))

    def test_switch_soul_one_delegates_the_slide_phase_and_keeps_no_swipe_or_sleep_itself(self):
        # V1 原来在这里钉旧滑顶形态（`swipe(…, 1.5)` + `sleep(0.5)`）；V2 起滑顶整体搬进 `_swipe_group_list_to_top`
        fn = _function(self.tree, 'switch_soul_one')
        calls = [ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        self.assertIn('self._swipe_group_list_to_top', calls)
        self.assertNotIn('self.swipe', calls)
        self.assertNotIn('sleep', calls)

    def test_ocr_by_name_mode_is_untouched(self):
        fn = _function(self.tree, 'switch_soul_by_name')
        sleeps = [n.args[0].value for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and _call_name(n) == 'sleep' and n.args and isinstance(n.args[0], ast.Constant)]
        self.assertEqual(sleeps, [2.5, 1.5, 2])
        self.assertIn('cnt_click >= 4', ast.unparse(fn))
        swipes = [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) == 'swipe']
        self.assertEqual(swipes, ['self.swipe(self.S_SS_GROUP_SWIPE_UP, 2)', 'self.swipe(self.S_SS_GROUP_SWIPE_DOWN)',
                                  'self.swipe(self.S_SS_TEAM_SWIPE_DOWN, 1.5)', 'self.swipe(self.S_SS_TEAM_SWIPE_UP, 0.3)'])
        text = ast.unparse(fn)
        self.assertIn('self.ocr_appear_click_by_rule(self.O_SS_TEAM_NAME, self.I_SOU_CLICK_PRESENT, interval=1.5)', text)
        self.assertNotIn('policy', text)

    def test_fallback_and_check_block_are_kept(self):
        fn = _function(self.tree, 'switch_soul_one')
        self.assertIn('self.ui_click_until_disappear(self.I_SOU_SWITCH_SURE)', ast.unparse(fn))
        confirm = ast.unparse(_function(self.tree, '_confirm_team_switch'))
        self.assertIn('self.appear_then_click(self.I_CHECK_BLOCK, interval=3)', confirm)
        self.assertIn('self.click(self.I_SOU_SWITCH_SURE, 3)', confirm)             # 原 3 秒 interval 恢复重试

    def test_appear_then_click_never_gets_a_positional_number_as_its_action(self):
        # `appear_then_click(target, action, interval, ...)` 的第二个位置参数是 `action`：
        # 把数字写成位置参数会在目标出现时 `3.coord()` 抛 AttributeError（I_CHECK_BLOCK 的保护曾因此形同虚设）。
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and _call_name(node) == 'appear_then_click' and len(node.args) > 1:
                self.assertNotIsInstance(node.args[1], ast.Constant, ast.unparse(node))

    def test_team_and_dialog_windows_are_class_constants_and_bounded(self):
        self.assertEqual((SwitchSoul.TEAM_FIND_TIMEOUT, SwitchSoul.TEAM_RESPONSE_TIMEOUT), (3.0, 2.0))
