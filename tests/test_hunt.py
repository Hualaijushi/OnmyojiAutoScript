# This Python file uses the following encoding: utf-8
"""狩猎战（麒麟 / 阴界之门）：开放时间、排程（不排到已经过去的时间、server=False）、有界的进入流程、
正常每日计划的随机延迟（`Hunt.scheduler.float_time`，受开放窗口限制，失败重试不加）。

用 `tests/test_daily_trifles.py` 的假界面驱动真实的 `ScriptTask` 方法；时间用替身固定，
`set_next_run` / `run_general_battle` / `click_fire` / 换御魂是替身。
"""

import unittest
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import random

from module.config.config import Config
from module.exception import TaskEnd
from tasks.Component.config_base import Time
from tasks.GameUi.page import page_hunt, page_hunt_kirin, page_shikigami_records
from tasks.Hunt.config import Hunt
from tasks.Hunt.script_task import ScriptTask as T
from tests.test_daily_trifles import FakeUi

MON, TUE, THU = date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 29)
FRI, SAT, SUN = date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)
ROOM = object()          # 「在房间里」这个画面状态


def at(day, h, m=0):
    return datetime.combine(day, time(h, m))


def fake_now(dt):
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return dt
    return patch('tasks.Hunt.script_task.datetime', FakeDT)


def make_hunt(ui, **consts):
    t = T.__new__(T)
    t.config = SimpleNamespace(hunt=Hunt())
    t.screenshot = ui.screenshot
    t.appear = ui.appear
    t.appear_then_click = ui.appear_then_click
    t.goto_page = ui.goto_page
    t.is_in_room = lambda is_screenshot=True: ui.appear(ROOM)
    t.set_next_run = Mock(name='set_next_run')
    t.run_general_battle = Mock(name='run_general_battle', return_value=True)
    t.click_fire = Mock(name='click_fire', return_value='battle')
    t.run_switch_soul = Mock(name='run_switch_soul')
    for k, v in dict(KIRIN_ENTER_TIMEOUT=0.3, NW_ENTER_TIMEOUT=0.3, BACK_TIMEOUT=0.3, **consts).items():
        setattr(t, k, v)
    return t


class HuntCase(unittest.TestCase):
    def run_at(self, t, dt):
        with fake_now(dt), patch('tasks.Hunt.script_task.sleep'), self.assertRaises(TaskEnd):
            t.run()

    def assert_scheduled(self, t, target):
        t.set_next_run.assert_called_once_with(task='Hunt', target=target, server=False)


class ModeAndScheduleTest(HuntCase):
    def test_mode_by_weekday(self):
        for day in (MON, TUE, THU):
            self.assertEqual(T._hunt_mode(day), 'kirin')
        for day in (FRI, SAT, SUN):
            self.assertEqual(T._hunt_mode(day), 'netherworld')

    def test_planned_time_is_clamped_into_the_open_window(self):
        t = make_hunt(FakeUi())
        self.assertEqual(t._planned_time('netherworld', FRI), at(FRI, 19))          # 默认 19:00
        t.config.hunt.hunt_time.netherworld_time = time(17, 30)
        self.assertEqual(t._planned_time('netherworld', FRI), at(FRI, 18))          # 早于开放 → 18:00
        t.config.hunt.hunt_time.kirin_time = time(5, 30)
        self.assertEqual(t._planned_time('kirin', MON), at(MON, 6))
        t.config.hunt.hunt_time.kirin_time = time(23, 30)
        self.assertEqual(t._planned_time('kirin', MON), at(MON, 6))                 # 晚于结束也按开放时间

    def test_waking_up_early_never_schedules_a_time_already_past(self):
        # 阴界之门设 17:30：以前 17:30 醒来又排回今天 17:30，调度器立刻又跑，一直空转到开放
        ui = FakeUi()
        t = make_hunt(ui)
        t.config.hunt.hunt_time.netherworld_time = time(17, 30)
        self.run_at(t, at(FRI, 17, 30))
        self.assert_scheduled(t, at(FRI, 18))
        self.assertEqual(ui.pages, [])

    def test_netherworld_opens_at_18(self):
        ui = FakeUi()
        t = make_hunt(ui)
        self.run_at(t, at(FRI, 17, 59))
        self.assertEqual(ui.pages, [])                          # 17:59 还不能打
        ui = FakeUi()
        t = make_hunt(ui)
        self.run_at(t, at(FRI, 18, 0))
        self.assertIn(page_hunt, ui.pages)                      # 18:00 开始打

    def test_after_the_window_goes_to_the_next_day_mode(self):
        t = make_hunt(FakeUi())
        self.run_at(t, at(THU, 23, 30))
        self.assert_scheduled(t, at(FRI, 19))                   # 周四之后是阴界之门
        t = make_hunt(FakeUi())
        self.run_at(t, at(SUN, 23, 30))
        self.assert_scheduled(t, at(MON + timedelta(days=7), 19))   # 周日之后是下周一的麒麟

    def test_switch_souls_only_for_the_mode_of_the_day(self):
        ui = FakeUi([T.I_KIRIN_END, T.I_UI_BACK_YELLOW])
        ui.on_click[id(T.I_UI_BACK_YELLOW)] = lambda: ui.hide(T.I_UI_BACK_YELLOW)
        t = make_hunt(ui)
        t.config.hunt.hunt_config.netherworld_group_team = '2,3'
        self.run_at(t, at(MON, 19))
        t.run_switch_soul.assert_not_called()                   # 今天是麒麟，阴界的预设不用换
        self.assertNotIn(page_shikigami_records, ui.pages)
        t = make_hunt(ui)
        t.config.hunt.hunt_config.kirin_group_team = '1,2'
        self.run_at(t, at(MON, 19))
        t.run_switch_soul.assert_called_once_with('1,2')


class SoulPresetTest(HuntCase):
    """麒麟分「通用」和「雷麒麟（周四）」两套式神录预设。"""

    def task(self, ui=None, kirin='-1,-1', thunder='-1,-1', nw='-1,-1'):
        t = make_hunt(ui or FakeUi())
        con = t.config.hunt.hunt_config
        con.kirin_group_team, con.thunder_kirin_group_team, con.netherworld_group_team = kirin, thunder, nw
        return t

    def done_kirin_page(self):
        ui = FakeUi([T.I_KIRIN_END, T.I_UI_BACK_YELLOW])
        ui.on_click[id(T.I_UI_BACK_YELLOW)] = lambda: ui.hide(T.I_UI_BACK_YELLOW)
        return ui

    def test_thursday_uses_the_thunder_preset_other_kirin_days_the_general_one(self):
        t = self.task(kirin='1,2', thunder='3,4')
        self.assertEqual(t._soul_preset('kirin', THU), '3,4')
        for day in (MON, TUE, date(2026, 10, 28)):
            with self.subTest(day=day):
                self.assertEqual(t._soul_preset('kirin', day), '1,2')

    def test_thursday_without_a_thunder_preset_falls_back_to_the_general_one(self):
        self.assertEqual(self.task(kirin='1,2')._soul_preset('kirin', THU), '1,2')

    def test_netherworld_only_looks_at_its_own_preset(self):
        t = self.task(kirin='1,2', thunder='3,4', nw='5,6')
        self.assertEqual(t._soul_preset('netherworld', FRI), '5,6')
        self.assertEqual(self.task(kirin='1,2', thunder='3,4')._soul_preset('netherworld', SAT), '-1,-1')

    def test_thursday_switches_to_the_thunder_preset_before_entering_the_kirin_page(self):
        ui = self.done_kirin_page()
        t = self.task(ui, kirin='1,2', thunder='3,4')
        self.run_at(t, at(THU, 19))
        t.run_switch_soul.assert_called_once_with('3,4')
        self.assertLess(ui.pages.index(page_shikigami_records), ui.pages.index(page_hunt_kirin))

    def test_nothing_configured_never_visits_the_shikigami_records(self):
        ui = self.done_kirin_page()
        t = self.task(ui)
        self.run_at(t, at(THU, 19))
        t.run_switch_soul.assert_not_called()
        self.assertNotIn(page_shikigami_records, ui.pages)


class KirinTest(HuntCase):
    def world(self, challenge=True, done=False):
        ui = FakeUi()
        if challenge:
            ui.show(T.I_KIRIN_CHALLAGE)
            ui.on_click[id(T.I_KIRIN_CHALLAGE)] = lambda: (ui.hide(T.I_KIRIN_CHALLAGE), ui.show(T.I_PREPARE_HIGHLIGHT))
        if done:
            ui.show(T.I_KIRIN_END, T.I_UI_BACK_YELLOW)
            ui.on_click[id(T.I_UI_BACK_YELLOW)] = lambda: ui.hide(T.I_UI_BACK_YELLOW)
        return ui

    def test_challenge_then_battle_then_tomorrow(self):
        ui = self.world()
        t = make_hunt(ui)
        self.run_at(t, at(MON, 19))
        self.assertIn(page_hunt_kirin, ui.pages)
        t.run_general_battle.assert_called_once_with(
            t.config.hunt.kirin_battle_config, battle_key='hunt_kirin', exit_matcher=page_hunt_kirin)
        self.assert_scheduled(t, at(TUE, 19))

    def test_already_challenged_goes_back_and_waits_for_tomorrow(self):
        ui = self.world(challenge=False, done=True)
        t = make_hunt(ui)
        self.run_at(t, at(MON, 19))
        t.run_general_battle.assert_not_called()
        self.assertEqual(ui.clicked(T.I_UI_BACK_YELLOW), 1)
        self.assert_scheduled(t, at(TUE, 19))

    def test_never_reaching_the_prepare_page_is_bounded_and_retried(self):
        t = make_hunt(FakeUi())
        self.run_at(t, at(MON, 19))
        t.run_general_battle.assert_not_called()
        self.assert_scheduled(t, at(MON, 19, 10))                # 时段内 10 分钟后再试

    def test_no_retry_after_the_window_closes(self):
        t = make_hunt(FakeUi())
        self.run_at(t, at(MON, 22, 55))
        self.assert_scheduled(t, at(TUE, 19))                   # 23:05 已经过了 23:00


class NetherworldTest(HuntCase):
    def world(self, room=True, fire=True, done=False):
        ui = FakeUi()
        if room:
            ui.show(T.I_NW_CHALLAGE)
            ui.on_click[id(T.I_NW_CHALLAGE)] = lambda: (ui.hide(T.I_NW_CHALLAGE), ui.show(ROOM),
                                                        ui.show(T.I_FIRE) if fire else None)
        if done:
            ui.show(T.I_NW_DONE, T.I_UI_BACK_RED)
            ui.on_click[id(T.I_UI_BACK_RED)] = lambda: ui.hide(T.I_UI_BACK_RED)
        return ui

    def test_room_fire_then_battle_then_tomorrow(self):
        ui = self.world()
        t = make_hunt(ui)
        self.run_at(t, at(FRI, 19))
        self.assertIn(page_hunt, ui.pages)
        t.click_fire.assert_called_once()
        t.run_general_battle.assert_called_once_with(
            t.config.hunt.netherworld_battle_config, battle_key='hunt_netherworld', exit_matcher=page_hunt)
        self.assert_scheduled(t, at(SAT, 19))

    def test_fire_without_battle_confirmation_does_not_fight_and_retries(self):
        ui = self.world()
        t = make_hunt(ui)
        t.click_fire.return_value = 'room_failed'
        self.run_at(t, at(FRI, 19))
        t.run_general_battle.assert_not_called()
        self.assert_scheduled(t, at(FRI, 19, 10))

    def test_already_challenged_goes_back_and_waits_for_tomorrow(self):
        ui = self.world(room=False, done=True)
        t = make_hunt(ui)
        self.run_at(t, at(SAT, 20))
        t.run_general_battle.assert_not_called()
        self.assertEqual(ui.clicked(T.I_UI_BACK_RED), 1)
        self.assert_scheduled(t, at(SUN, 19))

    def test_never_getting_in_is_bounded_and_retried(self):
        t = make_hunt(FakeUi())
        self.run_at(t, at(FRI, 19))
        self.assert_scheduled(t, at(FRI, 19, 10))

    def test_in_room_without_the_fire_button_is_bounded(self):
        ui = self.world(fire=False)
        t = make_hunt(ui)
        self.run_at(t, at(FRI, 19))
        t.click_fire.assert_not_called()
        self.assert_scheduled(t, at(FRI, 19, 10))


def hi(low, high):
    """把随机延迟固定在上界。"""
    return high


def lo(low, high):
    """把随机延迟固定在下界。"""
    return low


def with_float(t, minutes=10, seconds=0):
    t.config.hunt.scheduler.float_time = Time(hour=0, minute=minutes, second=seconds)
    return t


def sampling(side_effect):
    return patch('tasks.Hunt.script_task.random_int', side_effect=side_effect)


LAST_SECOND = timedelta(seconds=59)


class FloatDelayTest(HuntCase):
    """正常每日计划 = 有效基准时间 + 一次随机延迟（上限 float_time，且不越过当天开放窗口）。"""

    def test_zero_float_time_keeps_the_deterministic_time_and_never_samples(self):
        t = make_hunt(FakeUi())
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('netherworld', FRI), at(FRI, 19))
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 19))
        rnd.assert_not_called()

    def test_kirin_and_netherworld_base_time_plus_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(9, 0)
        t.config.hunt.hunt_time.netherworld_time = time(19, 0)
        with sampling(lambda a, b: 137) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 9) + timedelta(seconds=137))
            rnd.assert_called_once_with(0, 600)
        with sampling(lambda a, b: 137) as rnd:
            self.assertEqual(t._daily_plan('netherworld', FRI), at(FRI, 19) + timedelta(seconds=137))
            rnd.assert_called_once_with(0, 600)

    def test_range_bounds_are_the_base_time_and_base_plus_float(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(9, 0)
        t.config.hunt.hunt_time.netherworld_time = time(19, 0)
        with sampling(lo):
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 9))
            self.assertEqual(t._daily_plan('netherworld', FRI), at(FRI, 19))
        with sampling(hi):
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 9, 10))
            self.assertEqual(t._daily_plan('netherworld', FRI), at(FRI, 19, 10))

    def test_float_time_with_seconds_is_counted_in_seconds(self):
        t = with_float(make_hunt(FakeUi()), minutes=1, seconds=30)
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 19) + timedelta(seconds=90))
        rnd.assert_called_once_with(0, 90)

    def test_near_the_close_the_sampling_range_shrinks_instead_of_clamping(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(22, 55)
        with sampling(hi) as rnd:
            planned = t._daily_plan('kirin', MON)
        rnd.assert_called_once_with(0, 299)                  # 只剩 5 分钟：范围缩到 299 秒，不是先抽 600 再截断
        self.assertEqual(planned, at(MON, 22, 59) + LAST_SECOND)
        self.assertLess(planned, at(MON, 23))
        t.config.hunt.hunt_time.kirin_time = time(22, 59, 30)
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 22, 59) + LAST_SECOND)
        rnd.assert_called_once_with(0, 29)

    def test_near_the_close_plans_spread_out_and_never_pile_up_at_the_cutoff(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(22, 55)
        random.seed(20261026)
        plans = [t._daily_plan('kirin', MON) for _ in range(3000)]
        self.assertTrue(all(at(MON, 22, 55) <= p < at(MON, 23) for p in plans))
        self.assertGreater(len(set(plans)), 200)             # 真正铺开
        cutoff = at(MON, 22, 59) + LAST_SECOND
        self.assertLess(sum(p == cutoff for p in plans), 3000 * 0.03)

    def test_base_on_the_last_second_before_the_close_gets_no_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(22, 59, 59)
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 22, 59) + LAST_SECOND)
        rnd.assert_not_called()                              # 距截止只剩 1 秒：没有可随机的空间

    def test_base_exactly_on_the_close_is_kept_not_moved_to_tomorrow_and_not_randomised(self):
        # 配置 23:00:00 本来就落在窗口里（`start <= planned <= end`）：保持 23:00:00，不随机、不改到第二天
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(23, 0)
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 23))
        rnd.assert_not_called()
        # 到点醒来时 now 已经 > 23:00:00，原有逻辑按「已过窗口」排到下一个工作日：只排一次，不会反复立即调度
        with sampling(lo):
            self.run_at(t, at(MON, 23) + timedelta(seconds=1))
        self.assert_scheduled(t, at(TUE, 23))

    def test_out_of_window_config_still_falls_back_to_the_open_time_then_adds_the_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(5, 30)
        with sampling(hi) as rnd:
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 6, 10))              # 06:00 + 10 分钟
        rnd.assert_called_once_with(0, 600)
        t.config.hunt.hunt_time.kirin_time = time(23, 30)
        with sampling(lo):
            self.assertEqual(t._daily_plan('kirin', MON), at(MON, 6))
        t.config.hunt.hunt_time.netherworld_time = time(17, 30)
        with sampling(hi):
            self.assertEqual(t._daily_plan('netherworld', FRI), at(FRI, 18, 10))

    def test_planned_time_itself_is_still_the_plain_base_time(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        with sampling(hi) as rnd:
            self.assertEqual(t._planned_time('kirin', MON), at(MON, 19))
        rnd.assert_not_called()

    def test_daily_plan_is_sampled_once_when_written_and_not_again_on_reads(self):
        ui = KirinTest().world()
        t = with_float(make_hunt(ui), minutes=10)
        with sampling(lambda a, b: 100) as rnd:
            self.run_at(t, at(MON, 19))
        rnd.assert_called_once_with(0, 600)
        written = at(TUE, 19) + timedelta(seconds=100)
        t.set_next_run.assert_called_once_with(task='Hunt', target=written, server=False)
        with sampling(hi) as rnd:                            # 之后再读基准时间都不会重新随机，写入的值也不变
            t._planned_time('kirin', TUE)
            t._planned_time('kirin', TUE)
            self.assertEqual(t.set_next_run.call_args.kwargs['target'], written)
        rnd.assert_not_called()

    def test_waking_before_the_window_plans_with_a_single_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        t.config.hunt.hunt_time.netherworld_time = time(17, 30)
        with sampling(lambda a, b: 45) as rnd:
            self.run_at(t, at(FRI, 17, 30))
        rnd.assert_called_once_with(0, 600)
        self.assert_scheduled(t, at(FRI, 18) + timedelta(seconds=45))

    def test_after_the_window_the_next_day_plan_uses_the_next_mode_base_and_a_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)                  # 周四 → 周五：麒麟 → 阴界之门
        t.config.hunt.hunt_time.netherworld_time = time(19, 0)
        with sampling(hi) as rnd:
            self.run_at(t, at(THU, 23, 30))
        rnd.assert_called_once_with(0, 600)
        self.assert_scheduled(t, at(FRI, 19, 10))
        for rolled, delta in ((lo, 0), (hi, 600)):                       # 周日 → 下周一：阴界之门 → 麒麟
            t = with_float(make_hunt(FakeUi()), minutes=10)
            t.config.hunt.hunt_time.kirin_time = time(9, 0)
            with sampling(rolled):
                self.run_at(t, at(SUN, 23, 30))
            self.assert_scheduled(t, at(MON + timedelta(days=7), 9) + timedelta(seconds=delta))

    def test_thursday_to_friday_and_sunday_to_monday_after_a_finished_battle(self):
        t = with_float(make_hunt(KirinTest().world(challenge=False, done=True)), minutes=10)
        with sampling(lambda a, b: 60):
            self.run_at(t, at(THU, 19))
        self.assert_scheduled(t, at(FRI, 19) + timedelta(seconds=60))   # 周四打完 → 周五阴界之门
        t = with_float(make_hunt(NetherworldTest().world(room=False, done=True)), minutes=10)
        t.config.hunt.hunt_time.kirin_time = time(8, 0)
        with sampling(lambda a, b: 60):
            self.run_at(t, at(SUN, 20))
        self.assert_scheduled(t, at(MON + timedelta(days=7), 8) + timedelta(seconds=60))   # 周日打完 → 周一麒麟


class RetryHasNoDelayTest(HuntCase):
    def test_ten_minute_retry_never_samples_and_never_adds_float_time(self):
        for world, day in ((KirinTest().world(challenge=False), MON), (NetherworldTest().world(room=False), FRI)):
            t = with_float(make_hunt(world), minutes=10)
            with sampling(hi) as rnd:
                self.run_at(t, at(day, 19))
            rnd.assert_not_called()
            self.assert_scheduled(t, at(day, 19, 10))

    def test_retry_beyond_the_window_falls_to_the_next_day_plan_with_one_delay(self):
        t = with_float(make_hunt(FakeUi()), minutes=10)
        with sampling(hi) as rnd:
            self.run_at(t, at(MON, 22, 55))
        rnd.assert_called_once_with(0, 600)                  # 23:05 已过窗口，改排明天：这是新的每日计划，只随机一次
        self.assert_scheduled(t, at(TUE, 19, 10))


class ServerUpdateTest(HuntCase):
    """Hunt 一直用 server=False 写排期：服务器刷新时间不是 09:00 也不会改写目标时间，float_time 也不会被 task_delay 再叠加。"""

    def real_world(self, server_update):
        t = make_hunt(FakeUi())
        hunt = t.config.hunt
        hunt.scheduler.server_update = server_update
        config = SimpleNamespace(model=SimpleNamespace(hunt=hunt), hunt=hunt, reload=Mock(), save=Mock(),
                                 lock_config=SimpleNamespace(acquire=Mock(), release=Mock()))
        config.task_delay = lambda *a, **k: Config.task_delay(config, *a, **k)
        t.config = config
        t.start_time = at(MON, 9)
        del t.set_next_run                                   # 用 BaseTask 的真实 set_next_run → Config.task_delay
        return t, hunt

    def test_a_non_default_server_update_does_not_rewrite_the_planned_time(self):
        t, hunt = self.real_world(time(5, 0))
        target = at(MON, 9, 7) + timedelta(seconds=13)
        t._schedule(target)
        self.assertEqual(hunt.scheduler.next_run, target)
        # 对照：server=True 会被改到「明天 05:00」
        t.set_next_run(task='Hunt', target=target, server=True)
        self.assertNotEqual(hunt.scheduler.next_run, target)

    def test_float_time_on_the_scheduler_is_not_added_a_second_time_by_task_delay(self):
        t, hunt = self.real_world(time(9, 0))
        with_float(t, minutes=10)
        target = at(MON, 9, 3)
        t._schedule(target)                                  # server=False：task_delay 不再叠加 float_time
        self.assertEqual(hunt.scheduler.next_run, target)


if __name__ == '__main__':
    unittest.main()
