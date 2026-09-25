# This Python file uses the following encoding: utf-8
"""L2 Stage C1-A1：C0 复核后首批 4 个调用点接入既有 `InteractionPolicy`。

四处都只是给现有 `appear_then_click` 加 `policy=`（不改 L1、不改通用 L2 实现）：

| 模块 | 函数 | 目标 | Policy | reaction（秒） |
|---|---|---|---|---|
| Dokan | `priority_enter_dokan` | 动态 `target_priority` | NORMAL | 0.45~0.85 |
| Pets | `_feed` | `I_UI_BACK_CIRCLE` | NAVIGATION | 0.55~1.10 |
| SixRealms | `refresh_store` | 动态 `refresh_rule` | CONFIRM | 0.55~1.20 |
| SixRealms | `choose_and_enter_island` | 动态 `target_land` | NORMAL | 0.45~0.85 |

测试用**真实业务函数 + 真实 `BaseTask.appear_then_click` + 真实 `Control.click`（假后端）+ 真实 BehaviorTrace**，
用帧序列驱动（`frames[n]` = 第 n 次截图之后可见目标的 roi 映射，`frames[0]` = reaction 前的当前帧），包装采样器 / L1 执行器 /
`random_delay` / `sleep` 记录事件顺序；不靠源码字符串证明行为（AST 守卫只用来钉住「policy 关键字」与「无直接点击」）。

每处都验证：reaction 只采样一次、reaction 后 fresh 截图、目标在则点一次（新帧坐标、采样一次、`FinalPoint` 交 L1）、
目标消失零点击（不用旧坐标、不改点别的）、目标未出现时不触发 reaction；再加各自的业务兼容性（Dokan 的 Navigator 6 秒预算、
Pets 的后续导航、SixRealms 刷新失败不误报成功、岛屿消失不改选）。
"""

import ast
import inspect
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from dev_tools import click_callsite_register as reg
from dev_tools import click_entry_guard as guard
from module import behavior_trace
from module.atom.image import RuleImage
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_pipeline import FinalPoint, execute_single_click
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.exception import TaskEnd
from module.reaction_profile import REACTION_CONFIRM, REACTION_NAVIGATION, REACTION_NORMAL

_REPO = Path(__file__).resolve().parents[1]
ROI = (400, 300, 200, 90)
MOVED = (700, 450, 160, 70)
SHOT_COST = 0.25            # 虚拟时钟：每次截图耗时（仅用于 Navigator 预算场景）


def _inside(point, roi):
    x, y, w, h = roi
    return x <= point[0] < x + w and y <= point[1] < y + h


def _image(name, roi=ROI):
    return RuleImage(roi, roi, 'Template matching', 0.8, f'./{name}.png')


class Harness(TestCase):
    """帧序列驱动的真实 primitive 链路；`events` 按发生顺序记录 sample / execute / reaction / sleep / screenshot / backend。"""

    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.addCleanup(self._restore)                             # cleanup 后进先出：先 reset（关文件句柄）再删目录
        self.addCleanup(reset_behavior_traces)
        configure_behavior_trace('c1a1', enabled=True)
        self.events = []
        self.now = 0.0
        self.reaction_pick = 'lo'
        self.frame = {'n': 0}

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    # ---- 构造 ----
    def control(self):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(config_name='c1a1', script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        c.click_methods = {'minitouch': Mock(name='backend', side_effect=lambda x, y: self.events.append(('backend', x, y)))}
        c.long_click_methods = {}
        c.image = 'F'
        return c

    def make(self, cls, frames, **attrs):
        """`cls.__new__` 出真实业务类实例（不跑 `__init__`），只替换截图 / 识别 / 设备这三个外部边界。"""
        self.frame = {'n': 0}
        events, frame = self.events, self.frame

        def screenshot():
            frame['n'] += 1
            self.now += SHOT_COST
            if frame['n'] > 200:
                raise AssertionError('截图次数失控：可能出现了无界循环')
            events.append(('screenshot', frame['n']))

        def appear(target, interval=None, threshold=None):
            visible = frames[min(frame['n'], len(frames) - 1)].get(target.name)
            if visible is not None:
                target.roi_front = list(visible) if isinstance(target, RuleImage) else tuple(visible)
            return visible is not None

        task = cls.__new__(cls)
        task.interval_timer = {}
        task.screenshot = screenshot
        task.appear = appear
        task.device = self.control()
        for key, value in attrs.items():
            setattr(task, key, value)
        return task

    def keep_rois(self, *rules):
        saved = [(rule, list(rule.roi_front) if isinstance(rule.roi_front, list) else rule.roi_front) for rule in rules]

        def restore():
            for rule, roi in saved:
                rule.roi_front = roi
        self.addCleanup(restore)

    def run_task(self, fn):
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            self.events.append(('sample', tuple(roi), name))
            return original(roi, name, *a, **k)

        def executor(device, target, control_name=None, backend=None):
            self.events.append(('execute', target, control_name))
            return execute_single_click(device, target, control_name=control_name, backend=backend)

        def delay(lo, hi):
            self.events.append(('reaction', lo, hi))
            return lo if self.reaction_pick == 'lo' else hi

        def sleep(seconds):
            self.events.append(('sleep', seconds))
            self.now += seconds

        with patch.object(ClickSampler, 'sample_target', side_effect=counted), \
                patch('tasks.base_task.execute_single_click', side_effect=executor), \
                patch('tasks.base_task.random_delay', side_effect=delay), \
                patch('tasks.base_task.sleep', side_effect=sleep):
            return fn()

    # ---- 断言 ----
    def kinds(self):
        return [e[0] for e in self.events]

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

    def trace_rows(self):
        files = list(behavior_trace._LOG_DIR.glob('c1a1_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []

    def assert_reaction_click(self, roi, name, expected_range):
        """成功链路：识别 → reaction（一次，区间 = policy）→ sleep → fresh 截图 → 一次采样 → L1 一次（FinalPoint）→ 后端一次。"""
        core = [e for e in self.events if e[0] in ('reaction', 'sleep', 'screenshot', 'sample', 'execute', 'backend')]
        self.assertEqual([e[0] for e in core], ['reaction', 'sleep', 'screenshot', 'sample', 'execute', 'backend'])
        self.assertEqual(self.of('reaction')[0][1:], expected_range)                   # 区间来自 policy，且只采样一次
        self.assertEqual(self.of('sleep')[0][1], expected_range[0])                    # 睡的就是刚采样的那个值
        self.assertEqual(self.of('sample')[0][1], tuple(roi))                          # 采样发生在 fresh 帧的 roi 上
        _, target, control_name = self.of('execute')[0]
        self.assertIsInstance(target, FinalPoint)                                      # L1 只执行已定坐标，不再采样
        self.assertEqual(control_name, name)
        _, x, y = self.of('backend')[0]
        self.assertEqual((x, y), (target.x, target.y))
        self.assertTrue(_inside((x, y), roi))
        self.assertEqual([(r['action'], r['target'], r['extra']['x'], r['extra']['y']) for r in self.trace_rows()],
                         [('click', name, x, y)])

    def assert_zero_click_after_reaction(self):
        self.assertEqual(len(self.of('reaction')), 1)                                  # reaction 只采样一次，不重试
        for kind in ('sample', 'execute', 'backend'):
            self.assertEqual(self.of(kind), [], kind)
        self.assertEqual(self.trace_rows(), [])

    def assert_no_reaction_no_click(self):
        for kind in ('reaction', 'sleep', 'sample', 'execute', 'backend'):
            self.assertEqual(self.of(kind), [], kind)


# ======================================================================================
# 一、Dokan：优先级选择（Navigator 边动作，NORMAL）
# ======================================================================================

class _VTimer:
    """Navigator 预算场景的虚拟计时器：读的是 Harness 的虚拟时钟（截图 / reaction 都会推进它）。"""
    clock = None

    def __init__(self, limit, count=0):
        self.limit = limit

    def start(self):
        self.t0 = _VTimer.clock()
        return self

    def reached(self):
        return _VTimer.clock() - self.t0 >= self.limit

    def reset(self):
        self.t0 = _VTimer.clock()
        return self


class DokanPriorityTest(Harness):
    def _assets(self):
        from tasks.Dokan.assets import DokanAssets as A
        rules = [getattr(A, f'I_RYOU_DOKAN_ATTACK_PRIORITY_{i}') for i in range(5)]
        self.keep_rois(*rules)
        return rules

    def _task(self, frames, priority=2):
        from tasks.GameUi.navigator import GameUi
        task = self.make(GameUi, frames)
        task.config = SimpleNamespace(dokan=SimpleNamespace(dokan_config=SimpleNamespace(dokan_attack_priority=priority)))
        return task

    def _call(self, task):
        from tasks.Dokan.page import priority_enter_dokan
        return self.run_task(lambda: priority_enter_dokan(task))

    def test_selected_priority_is_clicked_after_reaction_on_the_fresh_frame(self):
        rules = self._assets()
        target = rules[2]
        task = self._task([{target.name: ROI}, {target.name: ROI}])
        self.assertTrue(self._call(task))
        self.assert_reaction_click(ROI, target.name, REACTION_NORMAL)
        self.assertEqual(task.interval_timer[target.name].limit, 1.2)                  # 原 interval=1.2 不变

    def test_priority_selection_rule_is_unchanged_for_every_configured_index(self):
        rules = self._assets()
        for index, chosen in enumerate(rules):
            with self.subTest(priority=index):
                self.events.clear()
                reset_behavior_traces()
                for f in behavior_trace._LOG_DIR.glob('c1a1_*.jsonl'):
                    f.unlink()
                configure_behavior_trace('c1a1', enabled=True)
                everything = {rule.name: ROI for rule in rules}                         # 5 个选项同时可见：只能点配置选中的那个
                task = self._task([everything, everything], priority=index)
                self.assertTrue(self._call(task))
                self.assertEqual([e[2] for e in self.of('execute')], [chosen.name])

    def test_target_moved_during_reaction_uses_the_new_position(self):
        target = self._assets()[2]
        task = self._task([{target.name: ROI}, {target.name: MOVED}])
        self.assertTrue(self._call(task))
        self.assert_reaction_click(MOVED, target.name, REACTION_NORMAL)
        self.assertNotIn(tuple(ROI), [e[1] for e in self.of('sample')])                # 旧位置从未被采样

    def test_target_gone_after_reaction_is_zero_click_and_false(self):
        rules = self._assets()
        target = rules[2]
        other = rules[3]
        task = self._task([{target.name: ROI, other.name: ROI}, {other.name: ROI}])    # 邻近选项仍在，也不能改点它
        self.assertFalse(self._call(task))
        self.assert_zero_click_after_reaction()

    def test_target_absent_triggers_no_reaction(self):
        self._assets()
        task = self._task([{}])
        self.assertFalse(self._call(task))
        self.assert_no_reaction_no_click()

    # ---- Navigator 6 秒 action 预算 / 4 秒页面到达等待 ----
    def _transition_env(self, frames):
        """真实 `GameUi._execute_transition` + 真实 `_execute_action` / `_invoke_callable`；预算计时器换成虚拟时钟。"""
        from tasks.Dokan.page import priority_enter_dokan
        task = self._task(frames)
        task.navigator = Mock()
        task.navigator.add_penalty.return_value = 1.0
        task._wait_for_destination = Mock(return_value=True)
        task._run_hooks = Mock()
        task._mark_page_entered = Mock()
        task._detect_current_page_with_fallback = Mock(return_value=None)
        task._navigation_detect_categories = Mock(return_value=set())
        page = lambda key: SimpleNamespace(key=key, on_leave_failure=(), on_leave_success=(),
                                           on_enter_failure=(), on_enter_success=())
        transition = SimpleNamespace(source=page('page_dokan_priority'), destination=page('page_dokan'),
                                     action=priority_enter_dokan, key='page_dokan_priority->page_dokan',
                                     on_leave_failure=(), on_leave_success=(), on_enter_failure=(), on_enter_success=())
        _VTimer.clock = lambda: self.now
        return task, transition

    def _execute_transition(self, task, transition):
        from tasks.GameUi import navigator
        with patch.object(navigator, 'Timer', _VTimer):
            return self.run_task(lambda: navigator.GameUi._execute_transition(task, transition))

    def test_navigator_budget_still_six_seconds_and_arrival_wait_still_four(self):
        from tasks.GameUi import navigator
        tree = ast.parse(inspect.getsource(navigator.GameUi._execute_transition).strip())
        timers = [n.args[0].value for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'Timer' and n.args]
        self.assertEqual(timers, [6.0])                                                 # action 预算
        self.assertEqual(inspect.signature(navigator.GameUi._wait_for_destination).parameters['timeout'].default, 4.0)

    def test_fresh_confirm_failure_is_retried_by_the_navigator_within_the_budget(self):
        target = self._assets()[2]
        # 第 1 轮：识别到但 reaction 后消失（不点）；第 2 轮起目标稳定存在 → 点击一次
        frames = [{}, {target.name: ROI}, {}, {target.name: ROI}, {target.name: MOVED}]
        task, transition = self._transition_env(frames)
        self.assertTrue(self._execute_transition(task, transition))
        self.assertEqual(len(self.of('backend')), 1)                                    # 只点一次
        self.assertEqual(len(self.of('reaction')), 2)                                   # 每次 attempt 各自一次 reaction
        self.assertEqual(self.of('sample')[0][1], tuple(MOVED))                         # 用的是最后一次 fresh 帧的坐标，不是旧坐标
        task._wait_for_destination.assert_called_once()

    def test_permanent_fresh_confirm_failure_times_out_without_clicking(self):
        target = self._assets()[2]
        # 每次识别到、reaction 后都消失：预算耗尽后 Navigator 正常失败退出，零点击
        frames_cycle = [{}, {target.name: ROI}]                  # 奇数帧（每轮循环顶部截图）有目标，偶数帧（fresh 截图）消失

        class Alternating(list):
            def __getitem__(self, i):
                return frames_cycle[i % 2]

            def __len__(self):
                return 10 ** 6

        task, transition = self._transition_env(Alternating())
        self.reaction_pick = 'hi'                                                       # 最坏情况：每次 reaction 取上限 0.85s
        self.assertFalse(self._execute_transition(task, transition))
        self.assertEqual(self.of('backend'), [])
        task.navigator.add_penalty.assert_called_once()                                 # 走的是原「动作未完成」失败分支
        task._wait_for_destination.assert_not_called()
        attempts = len(self.of('reaction'))
        self.assertTrue(1 <= attempts <= 7, attempts)                                   # 有界：6 秒预算内每次 attempt ≥ 1.35s
        # 预算 6s 计时起点在循环之前；最后一次 attempt 可能跨过 6s 边界，超出量不大于一次 attempt（截图×2 + reaction）
        self.assertLessEqual(self.now, 6.0 + 2 * SHOT_COST + 0.85 + 1e-9)

    def test_successful_reaction_consumes_part_of_the_six_second_budget(self):
        target = self._assets()[2]
        task, transition = self._transition_env([{}, {target.name: ROI}, {target.name: ROI}])
        self.reaction_pick = 'hi'
        self.assertTrue(self._execute_transition(task, transition))
        # 一次成功 attempt = 当前帧截图 + reaction + fresh 截图；预算是墙钟，reaction 会吃掉其中一部分（约 1.35s / 6s）
        self.assertAlmostEqual(self.now, 2 * SHOT_COST + 0.85, places=6)
        self.assertLess(self.now, 6.0)


# ======================================================================================
# 二、Pets：投喂后的返回按钮（NAVIGATION）
# ======================================================================================

class PetsFeedTest(Harness):
    def _task(self, frames, number):
        from tasks.Pets.script_task import ScriptTask
        back = ScriptTask.I_UI_BACK_CIRCLE
        self.keep_rois(back)
        frames = [{(back.name if k == 'BACK' else k): v for k, v in frame.items()} for frame in frames]
        conf = SimpleNamespace(pets_feast=True, enable_orochi_ten_once=False)
        task = self.make(ScriptTask, frames,
                         O_PET_FEED_AP=SimpleNamespace(ocr=Mock(return_value=number)),
                         config=SimpleNamespace(pets=SimpleNamespace(pets_config=conf)),
                         ui_click=Mock(), ui_click_until_disappear=Mock(), goto_page=Mock(), set_next_run=Mock())
        return task, back

    def _run(self, task):
        return self.run_task(lambda: task.run())

    def test_already_fed_clicks_back_once_after_reaction_then_goes_to_main(self):
        from tasks.GameUi.page import page_main
        from tasks.GameUi.default_pages import page_pet
        task, back = self._task([{'BACK': ROI}, {'BACK': ROI}], number=0)
        with self.assertRaises(TaskEnd):
            self._run(task)
        self.assert_reaction_click(ROI, back.name, REACTION_NAVIGATION)
        self.assertEqual([c.args[0] for c in task.goto_page.call_args_list], [page_pet, page_main])   # 后续导航不变，没有重复导航
        task.ui_click.assert_called_once()                                                           # 只有进入投喂界面那一次
        task.ui_click_until_disappear.assert_not_called()

    def test_fresh_confirm_failure_does_not_click_and_the_flow_still_closes_out(self):
        from tasks.GameUi.page import page_main
        from tasks.GameUi.default_pages import page_pet
        task, back = self._task([{'BACK': ROI}, {}], number=0)
        with self.assertRaises(TaskEnd):
            self._run(task)
        self.assert_zero_click_after_reaction()
        self.assertEqual([c.args[0] for c in task.goto_page.call_args_list], [page_pet, page_main])   # 仍由 goto_page(page_main) 收口
        task.set_next_run.assert_called_once()
        self.assertEqual(task.O_PET_FEED_AP.ocr.call_count, 1)                                         # 没有重复 OCR / 重复返回

    def test_not_yet_fed_triggers_no_back_reaction_and_no_back_click(self):
        task, back = self._task([{'BACK': ROI}], number=3)                                 # OCR 未满足「已投喂」条件
        with self.assertRaises(TaskEnd):
            self._run(task)
        self.assert_no_reaction_no_click()
        self.assertEqual(task.ui_click.call_count, 2)                                                  # 进入界面 + 原「投喂」点击
        task.ui_click_until_disappear.assert_called_once()

    def test_back_target_moved_uses_the_new_position(self):
        task, back = self._task([{'BACK': ROI}, {'BACK': MOVED}], number=0)
        with self.assertRaises(TaskEnd):
            self._run(task)
        self.assert_reaction_click(MOVED, back.name, REACTION_NAVIGATION)

    def test_back_button_absent_triggers_no_reaction(self):
        task, back = self._task([{}], number=0)
        with self.assertRaises(TaskEnd):
            self._run(task)
        self.assert_no_reaction_no_click()

    def test_feed_return_value_is_still_none(self):
        task, _ = self._task([{'BACK': ROI}, {'BACK': ROI}], number=0)
        self.assertIsNone(self.run_task(lambda: task._feed()))


# ======================================================================================
# 三、SixRealms：商店刷新（CONFIRM）
# ======================================================================================

class RefreshStoreTest(Harness):
    def _task(self, frames, times_text='剩3次'):
        from tasks.SixRealms.common import SixRealmsCommon
        refresh = _image('c1a1_refresh')
        times = SimpleNamespace(ocr=Mock(return_value=times_text))
        task = self.make(SixRealmsCommon, frames, C_STORE_ANIMATE_KEEP=object(),
                         wait_animate_stable=Mock(side_effect=lambda *a, **k: self.events.append(('animate', k))))
        return task, refresh, times

    def _refresh(self, task, refresh, times):
        return self.run_task(lambda: task.refresh_store(refresh, times))

    def test_refresh_clicks_once_after_reaction_then_waits_for_the_animation(self):
        task, refresh, times = self._task([{'C1A1_REFRESH': ROI}, {'C1A1_REFRESH': ROI}])
        self.assertTrue(self._refresh(task, refresh, times))
        self.assert_reaction_click(ROI, refresh.name, REACTION_CONFIRM)
        self.assertEqual(self.kinds()[-2:], ['backend', 'animate'])                     # 动画稳定等待仍在点击之后
        self.assertEqual(self.of('animate')[0][1], {'timeout': 1.5})                    # 原 timeout=1.5 不变
        task.wait_animate_stable.assert_called_once()
        self.assertEqual(times.ocr.call_count, 1)                                       # 刷新次数 OCR 仍只读一次

    def test_fresh_confirm_failure_reports_not_refreshed_and_skips_the_success_flow(self):
        task, refresh, times = self._task([{'C1A1_REFRESH': ROI}, {}])
        self.assertFalse(self._refresh(task, refresh, times))                           # 不误报刷新成功
        self.assert_zero_click_after_reaction()
        task.wait_animate_stable.assert_not_called()                                    # 不进入依赖「已刷新」的分支

    def test_refresh_icon_moved_uses_the_new_position(self):
        task, refresh, times = self._task([{'C1A1_REFRESH': ROI}, {'C1A1_REFRESH': MOVED}])
        self.assertTrue(self._refresh(task, refresh, times))
        self.assert_reaction_click(MOVED, refresh.name, REACTION_CONFIRM)

    def test_refresh_count_gates_are_unchanged_and_never_trigger_a_reaction(self):
        for text in ('剩0次', '没有匹配', ''):
            with self.subTest(text=text):
                self.events.clear()
                task, refresh, times = self._task([{'C1A1_REFRESH': ROI}, {'C1A1_REFRESH': ROI}], times_text=text)
                self.assertFalse(self._refresh(task, refresh, times))
                self.assert_no_reaction_no_click()
                task.wait_animate_stable.assert_not_called()

    def test_icon_absent_on_the_current_frame_triggers_no_reaction(self):
        task, refresh, times = self._task([{}])
        self.assertFalse(self._refresh(task, refresh, times))
        self.assert_no_reaction_no_click()
        task.wait_animate_stable.assert_not_called()

    def test_buy_skill_stops_cleanly_when_the_refresh_confirm_fails(self):
        from tasks.SixRealms.common import SixRealmsCommon
        skill = _image('c1a1_skill')
        refresh = _image('c1a1_refresh')
        coin = SimpleNamespace(ocr=Mock(return_value=1000))
        times = SimpleNamespace(ocr=Mock(return_value='剩3次'))
        frames = [{}, {'C1A1_REFRESH': ROI}, {}]                                        # 刷新图标在 reaction 期间消失；技能图标始终不可见
        task = self.make(SixRealmsCommon, frames, C_STORE_ANIMATE_KEEP=object(), wait_animate_stable=Mock())
        result = self.run_task(lambda: task.buy_skill(skill, 100, coin, refresh, times, buy_num=99))
        self.assertEqual(result, (1000, 0))                                             # 没有购买、没有误刷新、循环收敛退出
        self.assertEqual(self.of('backend'), [])
        task.wait_animate_stable.assert_not_called()
        self.assertEqual(len(self.of('reaction')), 1)                                   # 没有无界重试


# ======================================================================================
# 四、SixRealms：岛屿选择（NORMAL）
# ======================================================================================

class ChooseIslandTest(Harness):
    def _task(self, frames, cls=None):
        from tasks.SixRealms.common import SixRealmsCommon
        return self.make(cls or SixRealmsCommon, frames,
                         prepare_appear_cache=Mock(side_effect=lambda lands: self.events.append(('cache', len(lands)))))

    def _lands(self):
        return [_image('c1a1_land_a', (100, 200, 120, 80)), _image('c1a1_land_b', (500, 220, 120, 80)),
                _image('c1a1_land_c', (300, 420, 120, 80))]

    def _choose(self, task, lands):
        return self.run_task(lambda: task.choose_and_enter_island(lands))

    def test_first_recognized_island_is_clicked_after_reaction_and_fresh_confirm(self):
        a, b, c = self._lands()
        every = {land.name: land.roi_front for land in (a, b, c)}
        task = self._task([every, every])
        self.assertIsNone(self._choose(task, [a, b, c]))                                # 返回值仍是 None（外层不依赖）
        self.assert_reaction_click(tuple(a.roi_front), a.name, REACTION_NORMAL)         # 选择规则不变：取列表里第一个出现的
        self.assertEqual(task.interval_timer[a.name].limit, 0.8)                        # 原 interval=0.8 不变
        self.assertEqual(self.of('cache'), [('cache', 3)])                              # 批量匹配缓存只在 reaction 前的当前帧准备一次

    def test_island_filter_strategy_is_unchanged(self):
        from tasks.SixRealms.common import SixRealmsCommon
        a, b, c = self._lands()

        class SkipFirst(SixRealmsCommon):
            def _filter_island(self, appeared):
                return [land for land in appeared if land.name != 'C1A1_LAND_A']

        every = {land.name: land.roi_front for land in (a, b, c)}
        task = self._task([every, every], cls=SkipFirst)
        self._choose(task, [a, b, c])
        self.assert_reaction_click(tuple(b.roi_front), b.name, REACTION_NORMAL)         # 过滤后第一个 = B

    def test_moved_island_is_clicked_at_the_new_frame_position(self):
        a, b, c = self._lands()
        old_roi = tuple(a.roi_front)
        task = self._task([{a.name: old_roi}, {a.name: MOVED}])
        self._choose(task, [a, b, c])
        self.assert_reaction_click(MOVED, a.name, REACTION_NORMAL)
        self.assertNotIn(old_roi, [e[1] for e in self.of('sample')])                    # 旧位置从未被采样

    def test_vanished_island_is_not_clicked_and_no_other_island_is_substituted(self):
        a, b, c = self._lands()
        every = {land.name: land.roi_front for land in (a, b, c)}
        task = self._task([every, {b.name: b.roi_front, c.name: c.roi_front}])         # A 在 reaction 期间消失，B / C 仍在
        self.assertIsNone(self._choose(task, [a, b, c]))
        self.assert_zero_click_after_reaction()                                         # 不点旧坐标，也不改点旧帧里的其它岛屿
        self.assertEqual(self.of('cache'), [('cache', 3)])                              # 没有拿旧缓存再选一次；外层下一轮重新扫描

    def test_no_recognized_island_triggers_no_reaction(self):
        a, b, c = self._lands()
        task = self._task([{}])
        self.assertIsNone(self._choose(task, [a, b, c]))
        self.assert_no_reaction_no_click()

    def test_filtered_to_nothing_triggers_no_reaction(self):
        from tasks.SixRealms.common import SixRealmsCommon
        a, b, c = self._lands()

        class DropAll(SixRealmsCommon):
            def _filter_island(self, appeared):
                return []

        every = {land.name: land.roi_front for land in (a, b, c)}
        task = self._task([every, every], cls=DropAll)
        self._choose(task, [a, b, c])
        self.assert_no_reaction_no_click()

    def test_one_call_never_waits_more_than_one_reaction(self):
        a, b, c = self._lands()
        every = {land.name: land.roi_front for land in (a, b, c)}
        task = self._task([every, every])
        self._choose(task, [a, b, c])
        self.assertEqual((len(self.of('reaction')), len(self.of('screenshot'))), (1, 1))


# ======================================================================================
# 五、静态守卫 / 登记册（只钉「policy 关键字」与分类，不替代上面的运行期用例）
# ======================================================================================

def _calls(path, func, callee='appear_then_click'):
    tree = ast.parse((_REPO / path).read_text(encoding='utf-8'))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
    return [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, 'attr', None) == callee]


class DeclarationGuardTest(TestCase):
    SITES = (
        ('tasks/Dokan/page.py', 'priority_enter_dokan', 'NORMAL'),
        ('tasks/Pets/script_task.py', '_feed', 'NAVIGATION'),
        ('tasks/SixRealms/common.py', 'refresh_store', 'CONFIRM'),
        ('tasks/SixRealms/common.py', 'choose_and_enter_island', 'NORMAL'),
    )

    def test_each_site_declares_exactly_the_agreed_policy_and_no_confirm_delay(self):
        for path, func, policy in self.SITES:
            with self.subTest(func=func):
                calls = _calls(path, func)
                self.assertEqual(len(calls), 1)
                keywords = {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords}
                self.assertEqual(keywords['policy'], f'InteractionPolicy.{policy}')
                self.assertNotIn('confirm_delay', keywords)

    def test_no_direct_click_was_added_to_the_four_functions(self):
        for path, func, _ in self.SITES:
            with self.subTest(func=func):
                tree = ast.parse((_REPO / path).read_text(encoding='utf-8'))
                fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
                names = {getattr(c.func, 'attr', getattr(c.func, 'id', '')) for c in ast.walk(fn) if isinstance(c, ast.Call)}
                self.assertFalse({'click', 'long_click', 'click_with_backend', 'execute_single_click'} & names)

    def test_global_click_guard_still_passes(self):
        result = guard.check_repo()
        self.assertTrue(result.ok, result.render())

    def test_register_marks_exactly_the_four_sites_as_completed_and_leaves_the_rest_pending(self):
        sites = reg.classify_all(reg.scan_sites(), reg.load_audited_rows())
        # basis=c0 现在还包含 C0 归档的 DEFERRED / KEEP_* 点位（决定来源是 C0），「已完成」以 reason=C1 + ALREADY_L2 为准
        done = {(s['file'], s['func']) for s in sites if s['reason'] == 'C1'}
        self.assertEqual(done, {('tasks/Dokan/page.py', 'priority_enter_dokan'), ('tasks/Pets/script_task.py', '_feed'),
                                ('tasks/SixRealms/common.py', 'refresh_store'), ('tasks/SixRealms/common.py', 'choose_and_enter_island')})
        for s in sites:
            if s['reason'] == 'C1':
                self.assertEqual((s['basis'], s['decision']), ('c0', 'ALREADY_L2'))
        # C0 收口之后其余批次的状态见 tests/test_l2_c0_registry.py：这里只钉「它们没有被提前标记为已完成」
        not_done = {(s['file'], s['func']) for s in sites if s['decision'] in ('NEEDS_C', 'DEFERRED')}
        for expected in (('tasks/Duel/script_task.py', 'enter_practice_ban_mode'),
                         ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept'),
                         ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare'),
                         ('tasks/SixRealms/peacock_kingdom/peacock_kingdom.py', '_summon_store')):
            self.assertIn(expected, not_done)                                             # 其余批次没有被提前标记为完成
