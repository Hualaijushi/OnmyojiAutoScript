# This Python file uses the following encoding: utf-8
"""KekkaiUtilize 寄养循环收敛保护（D023 补记）。

缺陷：`run_utilize` 选中目标后会把 `utilize_add_count` / `utilize_failed_count` 清零；若寄养点击没有生效、
育成页 `I_UTILIZE_ADD` 一直在，这两个业务计数永远到不了上限，`check_utilize_add` 会无休止地搜索 / 进结界 /
放式神（上一轮探针 200 次仍未退出）。修复：另设不被清零的「本轮总尝试次数」与单调时钟「总耗时」，用尽即
复用短期重试出口（只写一次 next_run，读回确认后 TaskEnd）。

- 单元层：真实 `ScriptTask.run()` / `check_utilize_add()` / `run_utilize()`，页面 / 搜索用替身。
- 调度层：真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay`（临时目录里的临时配置、冻结时钟）。
- 所有会「跑飞」的替身都有硬上限（`_RunAway`），变异回归时快速失败而不是挂死。
"""

import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tests.test_kekkai_utilize_retry_scheduler import (
    NOW, SchedulerHarness, _ended_with_task_end, _run, _task,
)

MAX = KU.UTILIZE_MAX_ATTEMPTS
HARD_LIMIT = 60          # 测试自身的安全上限：远大于 MAX，被突破说明保护失效


class _RunAway(BaseException):
    """替身被调用次数超过硬上限：保护失效时用它立刻中止，避免测试挂死。"""


def _tail(values):
    values = list(values)
    for v in values:
        yield v
    while True:
        yield values[-1]


def _counted(counter, results):
    """带调用计数与硬上限的替身函数：按 `results` 依次返回，耗尽后重复最后一个值。"""
    it = _tail(results)

    def _call(*args, **kwargs):
        counter['n'] += 1
        if counter['n'] > HARD_LIMIT:
            raise _RunAway
        return next(it)
    return _call


def _stuck_task(*, add=(True,), search=(True,), persist=True, **cfg):
    """育成页 `I_UTILIZE_ADD` 按 `add` 序列出现（耗尽后停在最后一个值），其余目标一律在场。

    `_run_search` 是搜索替身（True = 选中候选卡）；`run_utilize` 走真实实现，所以会真实地把
    `utilize_add_count` / `utilize_failed_count` 清零。
    """
    t = _task(persist=persist, **cfg)
    add_iter = _tail(add)
    t.appear = Mock(side_effect=lambda target, **kw: next(add_iter) if target is t.I_UTILIZE_ADD else True)
    t.search_calls = {'n': 0}
    t._run_search = Mock(side_effect=_counted(t.search_calls, search))
    t.switch_shikigami_class = Mock(name='switch_shikigami_class')
    t.set_shikigami = Mock(name='set_shikigami')
    return t


def _stub_run_utilize(t, counter, *, result=True):
    """直接替换 run_utilize：每次都返回 `result` 并按真实语义清零业务计数（CASE 1 的原始形态）。"""
    def _f(*args, **kwargs):
        counter['n'] += 1
        if counter['n'] > HARD_LIMIT:
            raise _RunAway
        t.utilize_add_count = 0
        t.utilize_failed_count = 0
        return result
    t.run_utilize = _f


RETRY_TARGET = NOW + timedelta(minutes=20)       # `_run` 默认 cooldown 固定 20 分钟


class ConvergenceGuardTest(TestCase):
    def test_case1_button_never_disappears_and_run_utilize_keeps_resetting_counters(self):
        # 本轮最重要的回归：I_UTILIZE_ADD 一直在、run_utilize 每次 True 且清零业务计数
        t = _task()
        t.appear = Mock(return_value=True)
        calls = {'n': 0}
        _stub_run_utilize(t, calls)
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(calls['n'], MAX)                        # 恰好 MAX 次尝试后停止，不是 200 次
        self.assertEqual(t.utilize_total_attempts, MAX)
        # 业务计数确实被反复清零：每圈顶端 +1、run_utilize 内清零，永远到不了 5 / 3
        self.assertEqual((t.utilize_add_count, t.utilize_failed_count), (1, 0))
        self.assertTrue(t.utilize_terminal_failure)
        t.set_next_run.assert_called_once_with(task='KekkaiUtilize', target=RETRY_TARGET, server=False)
        message = t.push_notify.call_args.kwargs['content']
        self.assertIn('总尝试次数', message)
        self.assertIn(f'{MAX}/{MAX}', message)
        t.receive_guild_assets.assert_not_called()               # 保护触发后不再做收尾页面操作

    def test_case2_normal_placement_finishes_well_below_the_cap(self):
        t = _stuck_task(add=(True, True, False))                 # 两个合法寄养位依次完成，然后按钮消失
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=3, minutes=10))
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.search_calls['n'], 2)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(hours=3, minutes=10), server=False)
        self.assertFalse(t.utilize_retry_scheduled)              # 走的是成功调度，没有触发保护

    def test_case2b_two_placements_each_with_two_soft_failures_fit_exactly_in_the_cap(self):
        # 最坏的合法情形：每个寄养位 2 次软失败 + 1 次成功，共 6 次 = 上限，仍不能被保护误伤
        t = _stuck_task(add=[True] * 6 + [False], search=[False, False, True, False, False, True])
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=2))
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.search_calls['n'], MAX)
        self.assertEqual(t.utilize_total_attempts, MAX)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(hours=2), server=False)
        self.assertFalse(t.utilize_terminal_failure)

    def test_case3_success_schedule_is_unchanged(self):
        t = _stuck_task(add=(False,))                            # 按钮已消失：本来就在寄养
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=3, minutes=10))
        self.assertTrue(_ended_with_task_end(t))
        t._run_search.assert_not_called()
        self.assertEqual(t.utilize_total_attempts, 0)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(hours=3, minutes=10), server=False)

    def test_case4_candidate_found_every_time_but_placement_never_takes_effect(self):
        t = _stuck_task(add=(True,), search=(True,))             # 真实 run_utilize：选中即清零计数、放置后按钮仍在
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.search_calls['n'], MAX)
        self.assertEqual(t.set_shikigami.call_count, MAX)
        self.assertEqual(t.utilize_failed_count, 0)              # 每次都「成功」，业务计数从不累计
        t.set_next_run.assert_called_once()

    def test_case5_reopening_the_friend_list_does_not_reset_the_total(self):
        t = _stuck_task(add=(True,))
        switches = {'n': 0}
        original = t._run_search

        def _search_with_reopen(friend):
            t.switch_friend_list(friend)                         # 每次尝试都重新打开 / 切换好友列表
            switches['n'] += 1
            return original(friend)

        t.switch_friend_list = Mock(name='switch_friend_list')
        t._run_search = _search_with_reopen
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(switches['n'], MAX)
        self.assertEqual(t.utilize_total_attempts, MAX)

    def test_case6_attempt_cap_schedules_exactly_one_retry(self):
        t = _stuck_task(add=(True,))
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.set_next_run.call_count, 1)
        self.assertEqual(t.config.kekkai_utilize.scheduler.next_run, RETRY_TARGET)
        self.assertTrue(t.utilize_retry_scheduled)

    def test_case7_total_time_cap_with_a_controllable_monotonic_clock(self):
        clock = {'t': 1000.0}
        t = _stuck_task(add=(True,))
        calls = {'n': 0}

        def _slow_run_utilize(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] > HARD_LIMIT:
                raise _RunAway
            clock['t'] += 700                                    # 每次尝试耗时 700 秒
            t.utilize_add_count = 0
            t.utilize_failed_count = 0
            return True

        t.run_utilize = _slow_run_utilize
        with patch('tasks.KekkaiUtilize.script_task.monotonic', side_effect=lambda: clock['t']):
            self.assertTrue(_ended_with_task_end(t))
        # 起点 1000：第 4 次检查时已过 2100s >= 1800s；此前 3 次尝试（0 / 700 / 1400s）都被允许
        self.assertEqual(calls['n'], 3)
        self.assertLess(t.utilize_total_attempts, MAX)           # 次数还没到上限，是耗时触发的
        self.assertIn('总耗时', t.push_notify.call_args.kwargs['content'])
        t.set_next_run.assert_called_once()

    def test_case7b_timer_starts_once_and_is_not_restarted_by_selecting_a_card(self):
        clock = {'t': 0.0}
        t = _stuck_task(add=(True,))
        starts = []

        def _fake_monotonic():
            starts.append(clock['t'])
            return clock['t']

        def _search(friend):
            clock['t'] += 10
            return True

        t._run_search = Mock(side_effect=_search)
        with patch('tasks.KekkaiUtilize.script_task.monotonic', side_effect=_fake_monotonic):
            self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(starts[0], 0.0)
        self.assertEqual(t.utilize_started_at, 0.0)              # 起点没有被后续循环覆盖

    def test_case8_retry_written_and_confirmed_ends_through_the_normal_retry_contract(self):
        t = _stuck_task(add=(True,))
        raised, ret = _run(t)
        self.assertFalse(raised)                                 # run() 以 TaskEnd 结束，而不是直接返回
        self.assertTrue(t.utilize_retry_scheduled)

    def test_case9_unconfirmed_retry_write_is_not_reported_as_normal_end(self):
        t = _stuck_task(add=(True,), persist=False)
        raised, ret = _run(t)
        self.assertTrue(raised)                                  # 直接返回 = 调度器记失败
        self.assertIsNone(ret)
        self.assertFalse(t.utilize_retry_scheduled)
        t.set_next_run.assert_called_once()                      # 只尝试写一次，没有第二次补写

    def test_case10_system_errors_are_not_swallowed_by_the_guard(self):
        # 育成页导航异常本来就没有业务捕获：原样上抛，不写 next_run
        t = _stuck_task(add=(True,))
        t.goto_page = Mock(side_effect=[True, True, True] + [GameStuckError('growth')] * 3)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), self.assertRaises(GameStuckError):
            t.run()
        t.set_next_run.assert_not_called()
        # 搜索 / 放置里未被既有业务捕获的异常同样原样上抛
        for attr in ('_run_search', 'set_shikigami'):
            with self.subTest(attr=attr):
                t = _stuck_task(add=(True,))
                setattr(t, attr, Mock(side_effect=RuntimeError('boom')))
                with patch('tasks.KekkaiUtilize.script_task.time.sleep'), self.assertRaises(RuntimeError):
                    t.run()
                t.set_next_run.assert_not_called()

    def test_case10b_new_guard_code_adds_no_exception_handling(self):
        for func in (KU._utilize_convergence_exhausted, KU._stop_utilize_for_convergence):
            src = inspect.getsource(func)
            self.assertNotIn('except', src, func.__name__)
            self.assertNotIn('try:', src, func.__name__)

    def test_case11_retry_after_the_guard_is_normalized_by_the_quiet_window(self):
        t = _stuck_task(add=(True,), jitter_min=10, jitter_max=10)
        raised, _ = _run(t, clock=datetime(2026, 9, 1, 23, 55), cooldown=[1200, 600])
        self.assertFalse(raised)
        # 23:55 + 20min = 00:15 落窗 → 次日 07:00 + 10min，只归一化这一次
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 2, 7, 10), server=False)

    def test_case14_far_more_than_the_old_probe_is_bounded_by_the_cap(self):
        t = _task()
        t.appear = Mock(return_value=True)
        calls = {'n': 0}
        _stub_run_utilize(t, calls)
        self.assertTrue(_ended_with_task_end(t))
        self.assertLess(calls['n'], HARD_LIMIT)                  # 旧探针 200 次仍不退出；现在到上限即停
        self.assertEqual(calls['n'], MAX)


class ConvergenceSchedulerTest(SchedulerHarness, TestCase):
    """真实 Script.run / Script.loop：按钮始终在场的寄养任务只按短期重试规则重新调度。"""

    def setUp(self):
        super().setUp()
        self.attempt_counters = []

    def _make_ku(self, config, device):
        t = super()._make_ku(config, device)
        counter = {'n': 0}
        self.attempt_counters.append(counter)
        t.appear = Mock(return_value=True)                       # I_UTILIZE_ADD 一直在
        _stub_run_utilize(t, counter)                            # 每次「寄养成功」并清零业务计数
        return t

    def test_case12_two_accounts_have_independent_counters_and_schedules(self):
        self._write_config('simA')
        self._write_config('simB', ku_options={'cooldown_min': 10, 'cooldown_max': 10})
        script_a, script_b = self._script('simA', cooldown='min'), self._script('simB', cooldown='min')
        b_before = self._saved_next_run('simB')
        self.assertTrue(script_a.run('KekkaiUtilize'))
        self.assertEqual([c['n'] for c in self.attempt_counters], [MAX])
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=5))
        self.assertEqual(self._saved_next_run('simB'), b_before)         # B 完全不受 A 影响
        self.assertTrue(script_b.run('KekkaiUtilize'))
        self.assertEqual([c['n'] for c in self.attempt_counters], [MAX, MAX])   # 计数各自从 0 开始
        self.assertEqual(self._saved_next_run('simB'), self.START + timedelta(minutes=10))

    def test_case13_loop_keeps_scheduling_other_tasks_after_the_guard_fires(self):
        self._write_config('simA', others={
            'duel': self.START - timedelta(hours=1),
            'area_boss': self.START + timedelta(minutes=90)})
        script = self._script('simA')
        from tests.test_kekkai_utilize_retry_scheduler import _StopLoop
        with self.assertRaises(_StopLoop):
            script.loop()
        # KU 每 20 分钟一轮，每轮都被上限截断在 MAX 次尝试，落盘的下一次都是合法的未来时间
        self.assertGreaterEqual(len(self.ku_runs), 3)
        self.assertTrue(all(c['n'] == MAX for c in self.attempt_counters))
        self.assertEqual(self.ku_runs, [self.START + timedelta(minutes=20 * i) for i in range(len(self.ku_runs))])
        self.exit_mock.assert_not_called()                                # 没有触发三次失败退出
        self.assertEqual(script.failure_record.get('KekkaiUtilize', 0), 0)
        ran = [c for c, _ in self.other_runs]
        self.assertTrue({'Duel', 'AreaBoss'} <= set(ran), ran)            # 其它任务照常被选取执行
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=100))
