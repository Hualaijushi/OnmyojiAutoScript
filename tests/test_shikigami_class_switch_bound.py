# This Python file uses the following encoding: utf-8
"""式神分类切换（`ReplaceShikigami.switch_shikigami_class`）的有界化（D023 补记（四））。

缺陷：函数是一个没有任何本地边界的 `while 1`，唯一的退出条件是目标分类的「已选中」图标出现。点击没有生效 /
目标图标始终识别不到时，只能靠 Device 的 60 秒无点击卡死判定或「同一按钮 10 次点击」兜底——后者抛出的
GameTooManyClickError 没有被 `run_utilize` 当业务失败处理，会直接升级成重启游戏。修复：本地点击次数 +
`monotonic` 耗时（并接受上层传入的任务总截止时间），用尽即抛既有的 `GameStuckError`（`run_utilize` 早已把它当
软失败处理，不再上式神），由已有的「3 次软失败 → 一次 `_schedule_retry` → 读回确认 → TaskEnd」收口。

- 单元层：真实 `switch_shikigami_class` + 会随点击 / 时间变化的假界面（`_Switcher`，假 `monotonic` 时钟）。
- 任务层：真实 `run_utilize` / `check_utilize_add` / `run()`；调度层：真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay`。
- 假界面自带硬性上限（`_RunAway`），保护失效时立刻失败而不是挂死。
"""

import inspect
from datetime import timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.device.device import Device
from module.exception import GameStuckError
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tasks.Utils.config_enum import ShikigamiClass
from tests.test_kekkai_utilize_convergence import _RunAway, _stuck_task
from tests.test_kekkai_utilize_retry_scheduler import SchedulerHarness, _StopLoop, _task
from tests.test_kekkai_utilize_success_jitter import D, SCHED, _Rand, _drive, _target

RS = 'tasks.Component.ReplaceShikigami.replace_shikigami'
MAX_CLICKS = ReplaceShikigami.SWITCH_CLASS_MAX_CLICKS
LOCAL_TIMEOUT = ReplaceShikigami.SWITCH_CLASS_TIMEOUT
SETTLE = ReplaceShikigami.SWITCH_CLASS_SETTLE
HARD_SCREENS = 400          # 测试自身的安全上限：远大于任何合法流程，被突破说明保护失效


class _Clock:
    def __init__(self, now=1000.0):
        self.now = now


class _Switcher(ReplaceShikigami):
    """假界面：左下角当前分类图标（默认「全部」）→ 点击展开分类 → 点目标分类 → 出现「已选中」图标。

    只覆盖会碰设备的少数方法（截图 / 匹配 / 点击 / 位置稳定等待），`switch_shikigami_class` 用真实实现。
    截图每次推进 0.5 秒假时间；`appear(interval=)` 沿用真实语义（只有命中才重新计时）。
    """

    def __init__(self, clock, *, state='all', menu=False, effective=lambda k: True, delay=0.0, stable=True):
        self.clock = clock
        self._initial = (state, menu)
        self.effective, self.delay, self.stable = effective, delay, stable
        self.reset()

    def reset(self):
        self.state, self.menu = self._initial
        self.pending = []
        self.clicks = []
        self.screens = 0
        self.last_true = {}

    # ---- 假设备 ----
    def screenshot(self):
        self.screens += 1
        if self.screens > HARD_SCREENS:
            raise _RunAway
        self.clock.now += 0.5
        for item in [p for p in self.pending if p[0] <= self.clock.now]:
            self.pending.remove(item)
            item[1]()

    def _visible(self, name):
        if name == self.I_RS_N_SELECTED.name:
            return self.state == 'n'
        if name == self.I_RS_ALL_SELECTED.name:
            return self.state == 'all' and not self.menu
        if name == self.I_RS_N.name:
            return self.menu
        return False

    def appear(self, target, interval=None, threshold=None):
        if interval:
            last = self.last_true.get(target.name)
            if last is not None and self.clock.now - last < interval:
                return False
        seen = self._visible(target.name)
        if seen and interval:
            self.last_true[target.name] = self.clock.now
        return seen

    def wait_until_pos_stable(self, target, stable_time=0.3, timeout=2, threshold=None, skip_first_screenshot=True):
        self.clock.now += 1.0
        return self.stable

    def click(self, target, interval=None):
        self.clicks.append(target.name)
        index = len(self.clicks)
        if not self.effective(index):
            return True
        if target.name == self.I_RS_ALL_SELECTED.name:
            change = lambda: setattr(self, 'menu', True)
        else:
            def change():
                self.state, self.menu = 'n', False
        if self.delay:
            self.pending.append((self.clock.now + self.delay, change))
        else:
            change()
        return True

    def appear_then_click(self, target, interval=None):
        if self.appear(target, interval):
            self.click(target)
            return True
        return False


def _switch(sw, **kwargs):
    """在假 `monotonic` 时钟下调用真实的 `switch_shikigami_class`。"""
    with patch(f'{RS}.monotonic', side_effect=lambda: sw.clock.now):
        return sw.switch_shikigami_class(ShikigamiClass.N, **kwargs)


class SwitchBoundTest(TestCase):
    def test_case1_already_on_the_target_class_succeeds_without_clicking(self):
        sw = _Switcher(_Clock(), state='n')
        _switch(sw)
        self.assertEqual((sw.clicks, sw.screens), ([], 1))

    def test_case2_first_switch_succeeds_after_the_two_normal_clicks(self):
        sw = _Switcher(_Clock())
        _switch(sw)
        self.assertEqual(sw.clicks, [sw.I_RS_ALL_SELECTED.name, sw.I_RS_N.name])
        self.assertEqual(sw.state, 'n')

    def test_case3_succeeds_after_several_attempts(self):
        sw = _Switcher(_Clock(), effective=lambda k: k != 2)          # 点目标的第一次点击丢失
        _switch(sw)
        self.assertEqual(len(sw.clicks), 3)
        self.assertEqual(sw.state, 'n')

    def test_case3b_a_delayed_effect_of_the_last_allowed_click_is_still_accepted(self):
        # 最后一次（第 4 次）点击生效但界面 2 秒后才刷新：不能被误判为失败
        sw = _Switcher(_Clock(), menu=True, effective=lambda k: k == MAX_CLICKS, delay=2.0)
        _switch(sw)
        self.assertEqual((len(sw.clicks), sw.state), (MAX_CLICKS, 'n'))

    def test_case3c_an_effect_later_than_the_settle_window_is_a_failure(self):
        sw = _Switcher(_Clock(), menu=True, effective=lambda k: k == MAX_CLICKS, delay=SETTLE + 3)
        with self.assertRaises(GameStuckError):
            _switch(sw)
        self.assertEqual(len(sw.clicks), MAX_CLICKS)

    def test_case4_the_switch_icon_is_always_present_and_the_state_never_changes(self):
        sw = _Switcher(_Clock(), effective=lambda k: False)           # 「全部」图标一直在，点了没有反应
        start = sw.clock.now
        with self.assertRaises(GameStuckError) as ctx:
            _switch(sw)
        self.assertEqual(len(sw.clicks), MAX_CLICKS)                   # 恰好点满上限就停，没有第 5 次
        self.assertEqual(set(sw.clicks), {sw.I_RS_ALL_SELECTED.name})
        self.assertLess(sw.clock.now - start, LOCAL_TIMEOUT)          # 先按次数收口，远早于耗时上限
        self.assertIn('切换失败', str(ctx.exception))
        self.assertLess(sw.screens, HARD_SCREENS)

    def test_case5_the_target_class_is_never_recognized_and_nothing_is_clickable(self):
        sw = _Switcher(_Clock(), state='sr')                          # 当前是别的分类：什么图标都识别不到
        start = sw.clock.now
        with self.assertRaises(GameStuckError) as ctx:
            _switch(sw)
        elapsed = sw.clock.now - start
        self.assertEqual(sw.clicks, [])
        self.assertGreaterEqual(elapsed, LOCAL_TIMEOUT)
        self.assertLess(elapsed, LOCAL_TIMEOUT + 2)                   # 到 30 秒即止（一帧 0.5 秒的粒度）
        self.assertIn('超时', str(ctx.exception))

    def test_case6_clicks_have_no_effect_and_hit_the_click_cap(self):
        sw = _Switcher(_Clock(), menu=True, effective=lambda k: False)  # 分类已展开，点目标始终没有反应
        with self.assertRaises(GameStuckError):
            _switch(sw)
        self.assertEqual(sw.clicks, [sw.I_RS_N.name] * MAX_CLICKS)

    def test_case6b_an_unstable_target_position_never_clicks_and_is_bounded_by_time(self):
        sw = _Switcher(_Clock(), menu=True, stable=False)
        with self.assertRaises(GameStuckError):
            _switch(sw)
        self.assertEqual(sw.clicks, [])

    def test_case7_monotonic_time_beyond_the_limit_stops_the_loop(self):
        clock = _Clock()
        sw = _Switcher(clock, state='sr')
        original = sw.screenshot

        def _jump():
            original()
            clock.now += LOCAL_TIMEOUT                                # 一次调用就跳过整个本地上限
        sw.screenshot = _jump
        with self.assertRaises(GameStuckError):
            _switch(sw)
        self.assertLessEqual(sw.screens, 2)

    def test_case8_the_task_deadline_bounds_the_call_and_an_expired_one_stops_before_any_click(self):
        clock = _Clock()
        sw = _Switcher(clock, state='sr')
        start = clock.now
        with self.assertRaises(GameStuckError):
            _switch(sw, deadline=start + 10)                          # 任务只剩 10 秒：比本地 30 秒更早
        self.assertLess(clock.now - start, 12)
        sw = _Switcher(clock)
        with self.assertRaises(GameStuckError):
            _switch(sw, deadline=clock.now - 1)                       # 入口就已过期：一次点击都不做
        self.assertEqual((sw.clicks, sw.screens), ([], 1))

    def test_case8b_an_expired_deadline_does_not_block_an_already_selected_class(self):
        sw = _Switcher(_Clock(), state='n')
        _switch(sw, deadline=sw.clock.now - 100)
        self.assertEqual(sw.clicks, [])

    def test_local_limits_stay_below_the_device_level_guards(self):
        # 本地边界必须先于 Device 兜底触发，否则先出来的是重启游戏的 GameTooManyClickError
        self.assertLess(MAX_CLICKS, 6)                                # Device：两个按钮各 >= 6 / 同一按钮 >= 10
        self.assertLess(LOCAL_TIMEOUT, Device.stuck_timer.limit)      # Device：60 秒无点击判卡死

    def test_the_signature_keeps_existing_positional_callers_working(self):
        params = inspect.signature(ReplaceShikigami.switch_shikigami_class).parameters
        self.assertIsNone(params['deadline'].default)                # Exploration 等只传一个位置参数的调用方不受影响
        self.assertEqual(list(params)[:2], ['self', 'shikigami_class'])


# ======================================================================================
# 任务层：真实 run_utilize / check_utilize_add / run()，分类切换用假界面 + 真实实现
# ======================================================================================

def _wire_switcher(t, clock, **ui):
    """让 KU 任务的 `switch_shikigami_class` 走真实实现 + 假界面（每次调用界面回到初始状态）。"""
    sw = _Switcher(clock, **ui)
    t.switch_deadlines = []
    t.switch_click_counts = []

    def _switch_call(shikigami_class, deadline=None):
        t.switch_deadlines.append(deadline)
        sw.reset()
        try:
            return sw.switch_shikigami_class(shikigami_class, deadline=deadline)
        finally:
            t.switch_click_counts.append(len(sw.clicks))

    t.switch_shikigami_class = _switch_call
    t.sw = sw
    return sw


def _failing_task(clock, *, persist=True, **cfg):
    """按钮始终在场 + 每次都选中卡 + 进结界有坑位；分类切换的界面点击始终无效。"""
    cfg.setdefault('shikigami_class', ShikigamiClass.N)
    t = _stuck_task(add=(True,), search=(True,), persist=persist, **cfg)
    t.set_shikigami = Mock(name='set_shikigami')
    _wire_switcher(t, clock, effective=lambda k: False)
    return t


def _drive_with_clock(t, clock, rand=None, now=D(2026, 9, 1, 14, 0)):
    """调度层 datetime 冻结 + 分类切换 / 任务计时共用同一个假 monotonic 时钟。"""
    rand = rand or _Rand(others=[1200])
    with patch(f'{RS}.monotonic', side_effect=lambda: clock.now), \
            patch(f'{SCHED}.monotonic', side_effect=lambda: clock.now):
        return _drive(t, now, rand), rand


class SwitchFailurePropagationTest(TestCase):
    NOW = D(2026, 9, 1, 14, 0)

    def test_case9_a_failed_class_switch_never_places_a_shikigami_or_reports_success(self):
        clock = _Clock()
        t = _failing_task(clock)
        with patch(f'{RS}.monotonic', side_effect=lambda: clock.now):
            result = t.run_utilize()
        self.assertIs(result, False)                                  # 不是「寄养成功」
        t.set_shikigami.assert_not_called()                           # 没有继续放置式神
        self.assertEqual(t.utilize_failed_count, 1)                   # 沿既有业务软失败路径计数
        self.assertFalse(t.utilize_terminal_failure)
        t.set_next_run.assert_not_called()                            # 第 1 次软失败不排重试

    def test_case10_always_failing_switch_ends_with_exactly_one_short_retry(self):
        clock = _Clock()
        t = _failing_task(clock)
        start = clock.now
        ended, rand = _drive_with_clock(t, clock)
        self.assertTrue(ended)                                        # 重试读回确认后以 TaskEnd 正常结束
        self.assertEqual(len(t.switch_deadlines), 3)                  # 分类切换最多执行 3 次（3 次软失败即终态）
        self.assertTrue(all(count == MAX_CLICKS for count in t.switch_click_counts))   # 每次都恰点满上限就停
        t.set_shikigami.assert_not_called()
        self.assertEqual(t.utilize_failed_count, 3)
        self.assertTrue(t.utilize_terminal_failure)
        self.assertEqual(_target(t), self.NOW + timedelta(seconds=1200))   # 仅一次 5~30 分钟短期重试（写入一次）
        self.assertEqual(rand.calls, [(300, 1800)])                   # 只采样一次 cooldown，没有成功延迟
        self.assertLess(clock.now - start, 3 * LOCAL_TIMEOUT)         # 三次切换合计 < 90 秒假时间
        self.assertTrue(t.utilize_retry_scheduled)

    def test_case10b_the_task_level_guard_and_business_counters_are_untouched(self):
        clock = _Clock()
        t = _failing_task(clock)
        _drive_with_clock(t, clock)
        self.assertEqual(t.utilize_total_attempts, 3)                 # 本轮总尝试次数照常累计（上限 6）
        self.assertLess(t.utilize_total_attempts, KU.UTILIZE_MAX_ATTEMPTS)

    def test_case11_an_unconfirmed_retry_write_is_not_reported_as_a_normal_end(self):
        clock = _Clock()
        t = _failing_task(clock, persist=False)                       # set_next_run 静默没有落值
        ended, _ = _drive_with_clock(t, clock)
        self.assertFalse(ended)                                       # 直接返回 = 失败，不冒充 TaskEnd
        self.assertFalse(t.utilize_retry_scheduled)
        t.set_next_run.assert_called_once()                           # 也只写了一次
        t.set_shikigami.assert_not_called()

    def test_case8c_repeated_calls_share_the_single_task_deadline(self):
        clock = _Clock()
        t = _failing_task(clock)
        with patch(f'{RS}.monotonic', side_effect=lambda: clock.now), \
                patch(f'{SCHED}.monotonic', side_effect=lambda: clock.now):
            t.utilize_started_at = clock.now - (KU.UTILIZE_TOTAL_TIMEOUT - 10)   # 任务预算只剩 10 秒
            self.assertEqual(t._utilize_deadline(), clock.now + 10)
            first_start = clock.now
            t.run_utilize()
            self.assertLess(clock.now - first_start, 12)              # 第 1 次只能用剩下的 10 秒，不是完整 30 秒
            second_start = clock.now
            t.run_utilize()
            self.assertEqual(len(t.sw.clicks), 0)                     # 预算用尽后再次调用：一次点击都不做
            self.assertLess(clock.now - second_start, 2)
        self.assertEqual(set(t.switch_deadlines), {t.utilize_started_at + KU.UTILIZE_TOTAL_TIMEOUT})

    def test_deadline_is_none_before_the_task_timer_starts(self):
        t = _task()
        self.assertIsNone(t._utilize_deadline())

    def test_case13_normal_switch_and_placement_and_success_schedule_are_unchanged(self):
        clock = _Clock()
        t = _stuck_task(add=(True, False), search=(True,), shikigami_class=ShikigamiClass.N)
        t.set_shikigami = Mock(name='set_shikigami')
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=6))
        sw = _wire_switcher(t, clock)                                 # 界面正常：两次点击后选中
        ended, rand = _drive_with_clock(t, clock, _Rand())
        self.assertTrue(ended)
        self.assertEqual(sw.clicks, [sw.I_RS_ALL_SELECTED.name, sw.I_RS_N.name])
        t.set_shikigami.assert_called_once()                          # 切换成功后才放置
        self.assertEqual(_target(t), self.NOW + timedelta(hours=6))   # 成功调度 = OCR 剩余时间，0/0 不采样
        self.assertEqual(rand.calls, [])
        self.assertEqual(t.utilize_failed_count, 0)

    def test_case10c_soft_failures_then_a_working_switch_recovers_without_scheduling_a_retry(self):
        clock = _Clock()
        t = _stuck_task(add=(True, True, False), search=(True,), shikigami_class=ShikigamiClass.N)
        t.set_shikigami = Mock(name='set_shikigami')
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=6))
        sw = _wire_switcher(t, clock, effective=lambda k: False)
        outcomes = []
        real = t.switch_shikigami_class

        def _flaky(shikigami_class, deadline=None):                   # 第 1 次切换失败，第 2 次界面恢复正常
            outcomes.append(len(outcomes))
            if len(outcomes) >= 2:
                sw.effective = lambda k: True
            return real(shikigami_class, deadline=deadline)

        t.switch_shikigami_class = _flaky
        ended, _ = _drive_with_clock(t, clock, _Rand())
        self.assertTrue(ended)
        self.assertEqual(len(outcomes), 2)
        t.set_shikigami.assert_called_once()
        self.assertEqual(_target(t), self.NOW + timedelta(hours=6))   # 最终仍是成功调度，没有多写重试
        self.assertFalse(t.utilize_terminal_failure)


# ======================================================================================
# 调度层：真实 Script.run / Script.loop + 真实 Config.task_delay
# ======================================================================================

class SwitchFailureSchedulerTest(SchedulerHarness, TestCase):
    def setUp(self):
        super().setUp()
        self.mono = _Clock()
        patch(f'{RS}.monotonic', side_effect=lambda: self.mono.now).start()
        patch(f'{SCHED}.monotonic', side_effect=lambda: self.mono.now).start()
        self.switch_calls = []

    def _make_ku(self, config, device):
        t = super()._make_ku(config, device)
        t.appear = Mock(name='appear', return_value=True)             # 按钮一直在，且好友结界有坑位
        t._run_search = Mock(return_value=True)                       # 每次都选中一张卡
        t.set_shikigami = Mock(name='set_shikigami')
        sw = _wire_switcher(t, self.mono, effective=lambda k: False)
        self.switch_calls.append(t)
        return t

    def test_case12_loop_keeps_running_other_tasks_and_only_reschedules_the_short_retry(self):
        self._write_config('simA', others={
            'duel': self.START - timedelta(hours=1),
            'area_boss': self.START + timedelta(minutes=90)})
        script = self._script('simA')
        with self.assertRaises(_StopLoop):
            script.loop()
        # 每 20 分钟一轮（既有 5~30 分钟 cooldown），每轮分类切换恰 3 次、从不上式神
        self.assertEqual(self.ku_runs, [self.START + timedelta(minutes=20 * i) for i in range(5)])
        self.assertTrue(all(len(t.switch_deadlines) == 3 for t in self.switch_calls))
        self.assertTrue(all(t.set_shikigami.call_count == 0 for t in self.switch_calls))
        self.exit_mock.assert_not_called()                            # 没有触发三次失败退出
        self.assertEqual(script.failure_record.get('KekkaiUtilize', 0), 0)
        ran = [c for c, _ in self.other_runs]
        self.assertTrue({'Duel', 'AreaBoss'} <= set(ran), ran)         # 其它任务照常被调度
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=100))
