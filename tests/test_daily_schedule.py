# This Python file uses the following encoding: utf-8
"""每日琐事的调度：下次运行 = 下一个服务器刷新（`server_update`，默认 09:00）与下一个 12:00 / 20:00 时段点中较早的一个，再加任务自己的随机延迟。

目的：每天开 OAS 时 09:00 已过、每日琐事立刻到点能最先跑；12 点 / 20 点庭院寿司时段仍各跑一次，都带 `float_time` 随机延迟；
不用「完成时间 + success_interval」（12 / 20 点的运行会拖动锚点，随机延迟累计后每天往后漂）。
延迟在 `plan_next_dt` 里自己算、以 `server=False` 交给调度：真实 `Config.task_delay` 只在 `server_update` 恰为 09:00 时才加延迟，
否则把目标推到明天。这里用真实 `Config.task_delay` 验证排出来的时间。
"""

import unittest
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.config.config import Config
from tasks.DailyTrifles.config import DailyTrifles
from tasks.DailyTrifles.script_task import ScriptTask as T
from tests.test_daily_trifles import FakeUi, make_task

SCRIPT = 'tasks.DailyTrifles.script_task'


def real_world(server_update=time(9, 0), float_time=time(0, 0)):
    """真实 BaseTask.set_next_run → 真实 Config.task_delay，只替换配置对象。"""
    t = make_task(FakeUi())
    d = DailyTrifles()
    d.scheduler.server_update = server_update
    d.scheduler.float_time = float_time
    config = SimpleNamespace(model=SimpleNamespace(daily_trifles=d), daily_trifles=d, reload=Mock(), save=Mock(),
                             lock_config=SimpleNamespace(acquire=Mock(), release=Mock()))
    config.task_delay = lambda *a, **k: Config.task_delay(config, *a, **k)
    t.config = config
    t.start_time = datetime(2026, 10, 26, 9, 30)
    return t, d


def plan(t, d, now):
    with patch(f'{SCRIPT}.datetime') as dt:
        dt.now.return_value = now
        t.plan_next_dt()
    return d.scheduler.next_run


class ScheduleTest(unittest.TestCase):
    def test_three_runs_a_day_with_the_first_one_at_the_server_refresh(self):
        t, d = real_world()
        now = datetime(2026, 10, 26, 9, 35)                     # 早上第一次（OAS 开了之后）
        seen = []
        for _ in range(7):
            target = plan(t, d, now)
            seen.append(target)
            now = target + timedelta(minutes=2)                 # 按排好的时间到点运行，跑 2 分钟
        self.assertEqual(seen, [datetime(2026, 10, 26, 12, 0), datetime(2026, 10, 26, 20, 0), datetime(2026, 10, 27, 9, 0),
                                datetime(2026, 10, 27, 12, 0), datetime(2026, 10, 27, 20, 0), datetime(2026, 10, 28, 9, 0),
                                datetime(2026, 10, 28, 12, 0)])

    def test_the_morning_run_does_not_drift_even_with_a_random_delay(self):
        t, d = real_world(float_time=time(1, 10))
        base = datetime(2026, 10, 26, 20, 5)                    # 20 点那次运行之后
        for day in range(30):
            starts = []
            for _ in range(20):
                starts.append(plan(t, d, base))
            nxt = datetime(2026, 10, 27, 9, 0)
            self.assertTrue(all(nxt <= s <= nxt + timedelta(minutes=70) for s in starts), starts[:3])
            base = datetime(2026, 10, 26, 20, 5)                # 锚点不依赖上一次实际开始的时间：每次都从同样的起点算
        # 漂移检查：早上那次实际在 10:10 才跑，之后的下次时间仍是 12:00 档 / 次日 09:00 档，不是「10:10 + 1 天」
        t2, d2 = real_world()
        self.assertEqual(plan(t2, d2, datetime(2026, 10, 26, 10, 10)), datetime(2026, 10, 26, 12, 0))

    def test_random_delay_comes_from_the_tasks_own_float_time_and_is_added_once(self):
        t, d = real_world(float_time=time(0, 30))
        targets = [plan(t, d, datetime(2026, 10, 26, 12, 5)) for _ in range(200)]
        self.assertTrue(all(datetime(2026, 10, 26, 20, 0) <= x <= datetime(2026, 10, 26, 20, 30) for x in targets))
        self.assertGreater(max(targets) - min(targets), timedelta(minutes=5))             # 确实随机了，不是固定值

    def test_zero_float_time_means_no_delay(self):
        t, d = real_world(float_time=time(0, 0))
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 12, 5)), datetime(2026, 10, 26, 20, 0))

    def test_a_non_default_server_update_neither_moves_the_slots_nor_pushes_them_to_tomorrow(self):
        t, d = real_world(server_update=time(5, 0))
        # 服务器刷新改成 05:00：日常锚点跟着配置走，12 / 20 点时段点不受影响，也不会被 task_delay 改到明天
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 12, 5)), datetime(2026, 10, 26, 20, 0))
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 20, 5)), datetime(2026, 10, 27, 5, 0))
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 3, 0)), datetime(2026, 10, 26, 5, 0))

    def test_at_or_after_the_refresh_time_the_next_refresh_is_tomorrow(self):
        t, d = real_world()
        self.assertEqual(T.next_daily_time(t, datetime(2026, 10, 26, 9, 0)), datetime(2026, 10, 27, 9, 0))
        self.assertEqual(T.next_daily_time(t, datetime(2026, 10, 26, 8, 59)), datetime(2026, 10, 26, 9, 0))

    def test_slot_points(self):
        cases = {(0, 0): (26, 12), (11, 59): (26, 12), (12, 0): (26, 20), (19, 59): (26, 20), (20, 0): (27, 12), (23, 59): (27, 12)}
        for (h, m), (day, hour) in cases.items():
            with self.subTest(now=f'{h}:{m:02d}'):
                self.assertEqual(T.next_slot_time(datetime(2026, 10, 26, h, m)), datetime(2026, 10, day, hour, 0))

    def test_success_interval_is_not_used_for_the_planned_time(self):
        t, d = real_world()
        d.scheduler.success_interval = timedelta(days=5)
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 12, 5)), datetime(2026, 10, 26, 20, 0))

    def test_a_run_started_long_after_the_refresh_is_due_at_once_next_time_it_is_planned_in_the_past(self):
        # 比如 20:30 才开 OAS：此前排的 09:00（过去）一进调度就到点，这里只验证规划函数本身不会把过去的点往后挪
        t, d = real_world()
        self.assertEqual(plan(t, d, datetime(2026, 10, 26, 20, 30)), datetime(2026, 10, 27, 9, 0))


if __name__ == '__main__':
    unittest.main()
