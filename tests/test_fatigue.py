from math import exp
from random import SystemRandom
from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from module.base.utils import random as random_utils
from module.fatigue import (
    FatigueManager,
    FatigueSnapshot,
    get_fatigue_manager,
    reset_fatigue_managers,
)
from tasks.GlobalGame.config import FatigueConfig


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps = []

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


class FatigueManagerTest(TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.config = FatigueConfig(enable=True)
        self.manager = FatigueManager(self.config, clock=self.clock, sleeper=self.clock.sleep)
        self.manager.begin_task('RyouToppa', load_factor=1.0)

    def trigger_idle(self, duration: float):
        with patch('module.fatigue.random_triangular', return_value=duration):
            with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
                return self.manager.try_break(safe=True)

    def trigger_rest(self, duration: float):
        with patch('module.fatigue.random_triangular', return_value=duration):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                return self.manager.try_break(safe=True)

    def test_task_active_elapsed_uses_only_active_time(self):
        self.clock.advance(30 * 60)
        self.assertAlmostEqual(self.manager.task_active_elapsed(), 30 * 60)

    def test_idle_pauses_task_and_global_active_time(self):
        self.clock.advance(20 * 60)
        result = self.trigger_idle(5 * 60)
        self.clock.advance(10 * 60)
        self.assertEqual(result.kind, 'idle')
        self.assertAlmostEqual(self.manager.task_active_elapsed(), 30 * 60)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), 30 * 60)
        self.assertAlmostEqual(self.clock.value, 35 * 60)

    def test_rest_pauses_task_and_global_active_time(self):
        self.clock.advance(60 * 60)
        result = self.trigger_rest(10 * 60)
        self.assertEqual(result.kind, 'rest')
        self.assertAlmostEqual(self.manager.task_active_elapsed(), 60 * 60)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), 60 * 60)
        self.assertAlmostEqual(self.clock.value, 70 * 60)

    def test_wall_deadline_does_not_use_active_elapsed(self):
        wall_deadline = 60 * 60
        self.clock.advance(50 * 60)
        with patch('module.fatigue.random_triangular', return_value=20 * 60):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                result = self.manager.try_break(
                    safe=True,
                    max_break_seconds=wall_deadline - self.clock.value,
                )
        self.assertEqual(result.duration, 10 * 60)
        self.assertEqual(self.clock.value, wall_deadline)
        self.assertAlmostEqual(self.manager.task_active_elapsed(), 50 * 60)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), 50 * 60)

    def test_consecutive_idle_recovery_is_accumulated(self):
        self.clock.advance(60 * 60)
        first = self.trigger_idle(60.0)
        first_recovery = self.manager._task_recovery
        # 事件率模型下两次 idle 判断之间必须有真实 active 时间间隔
        self.clock.advance(60)
        second = self.trigger_idle(60.0)
        self.assertAlmostEqual(first_recovery, 8.0)
        self.assertAlmostEqual(self.manager._task_recovery, 16.0)
        self.assertLessEqual(second.after.task, first.after.task)

    def test_idle_then_rest_keeps_previous_recovery(self):
        self.clock.advance(90 * 60)
        idle = self.trigger_idle(60.0)
        recovery_after_idle = self.manager._task_recovery
        rest = self.trigger_rest(10 * 60)
        self.assertGreater(self.manager._task_recovery, recovery_after_idle)
        self.assertLessEqual(rest.after.task, idle.after.task)
        self.assertLessEqual(rest.after.global_, idle.after.global_)

    def test_rest_active_rest_preserves_active_time_and_recovery(self):
        self.clock.advance(90 * 60)
        first = self.trigger_rest(5 * 60)
        first_recovery = self.manager._global_recovery
        self.manager._rest_cooldown_until = 0.0
        self.clock.advance(10 * 60)
        second = self.trigger_rest(5 * 60)
        self.assertGreater(self.manager._global_recovery, first_recovery)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), 100 * 60)
        self.assertLess(second.after.global_, second.before.global_)
        self.assertLessEqual(first.after.global_, first.before.global_)

    def test_switching_task_resets_task_active_state_only(self):
        self.clock.advance(30 * 60)
        self.manager._task_recovery = 12.0
        with patch('module.fatigue.random_delay', return_value=1.0):
            self.manager.try_break(safe=True, repeat_completed=True)
        global_before = self.manager.global_active_elapsed()
        self.manager.begin_task('RealmRaid')
        self.assertEqual(self.manager.task_active_elapsed(), 0.0)
        self.assertEqual(self.manager.task_repetitions, 0)
        self.assertEqual(self.manager._task_recovery, 0.0)
        self.assertEqual(self.manager.global_active_elapsed(), global_before)

    def test_break_does_not_change_repeat_count_by_itself(self):
        self.clock.advance(60 * 60)
        repetitions = self.manager.task_repetitions
        self.trigger_idle(60.0)
        self.assertEqual(self.manager.task_repetitions, repetitions)

    def test_activity_state_distinguishes_scheduler_and_breaks(self):
        self.assertEqual(self.manager.activity_state, 'active')
        self.manager.end_global_activity()
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')
        self.manager.begin_global_activity()
        observed = []

        def observe_state(duration):
            observed.append(self.manager.activity_state)
            self.clock.sleep(duration)

        self.manager._sleep = observe_state
        self.clock.advance(30 * 60)
        self.trigger_idle(60.0)
        self.assertEqual(observed, ['idle'])
        self.assertEqual(self.manager.activity_state, 'active')

    def test_recovery_does_not_bank_against_future_activity(self):
        self.clock.advance(5 * 60)
        result = self.trigger_rest(20 * 60)
        self.assertEqual(result.after.task, 0.0)
        self.assertEqual(result.after.global_, 0.0)
        self.clock.advance(5 * 60)
        self.assertGreater(self.manager.task_fatigue(), 0.0)
        self.assertGreater(self.manager.global_fatigue(), 0.0)

    def test_lowering_load_factor_normalizes_task_recovery(self):
        self.clock.advance(60 * 60)
        self.manager.set_load_factor(1.3)
        self.manager._task_recovery = self.manager._raw_task_fatigue() - 5.0
        self.manager.set_load_factor(0.8)
        lowered_raw = self.manager._raw_task_fatigue()
        self.assertLessEqual(self.manager._task_recovery, lowered_raw)
        self.assertEqual(self.manager.task_fatigue(), 0.0)
        self.clock.advance(60.0)
        self.assertGreater(self.manager.task_fatigue(), 0.0)

    def test_raising_load_factor_increases_task_fatigue_without_recovery(self):
        self.clock.advance(60 * 60)
        self.manager.set_load_factor(0.8)
        before = self.manager.task_fatigue()
        self.manager.set_load_factor(1.2)
        self.assertEqual(self.manager._task_recovery, 0.0)
        self.assertGreater(self.manager.task_fatigue(), before)

    def test_load_factor_does_not_change_global_recovery(self):
        self.clock.advance(60 * 60)
        self.manager._global_recovery = 7.0
        self.manager.set_load_factor(0.8)
        self.assertEqual(self.manager._global_recovery, 7.0)
        self.manager.set_load_factor(1.3)
        self.assertEqual(self.manager._global_recovery, 7.0)

    def test_load_factor_preview_uses_current_idle_formula(self):
        preview = self.manager.load_factor_preview()
        self.assertEqual(len(preview), 11)
        self.assertEqual([item['factor'] for item in preview], [
            0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3,
        ])
        row = next(item for item in preview if item['factor'] == 1.1)
        expected_task = self._clamp_preview_task(1.1)
        snapshot = FatigueSnapshot(task=expected_task, global_=10.0)
        expected_score = self.manager.idle_score(snapshot)
        expected_intensity = self.manager.idle_intensity(expected_score)
        expected_rate = self.manager.idle_rate_per_hour(snapshot)
        self.assertEqual(row['task_fatigue'], round(expected_task, 2))
        self.assertEqual(row['idle_score'], round(expected_score, 2))
        self.assertEqual(row['idle_intensity'], round(expected_intensity, 4))
        self.assertEqual(row['idle_rate_per_hour'], round(expected_rate, 4))
        self.assertEqual(
            row['idle_probability_at_25s'],
            round(self.manager._node_probability_from_rate(expected_rate, 25.0), 6),
        )

    def _clamp_preview_task(self, factor: float) -> float:
        raw = self.manager._calculate_raw_task_fatigue(
            active_seconds=60 * 60,
            repetitions=170,
            load_factor=factor,
        )
        return self.manager._clamp(raw)

    def test_idle_ends_without_resuming_when_task_stops(self):
        self.clock.advance(60 * 60)
        with patch('module.fatigue.random_triangular', return_value=60.0):
            with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
                self.manager.try_break(safe=True, should_resume=lambda: False)
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')

    def test_rest_ends_without_resuming_at_deadline(self):
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_triangular', return_value=120.0):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                self.manager.try_break(safe=True, should_resume=lambda: False)
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')

    def test_break_exception_does_not_resume_activity(self):
        self.clock.advance(60 * 60)

        def fail_sleep(_duration):
            raise RuntimeError('stop')

        self.manager._sleep = fail_sleep
        with patch('module.fatigue.random_triangular', return_value=60.0):
            with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
                with self.assertRaises(RuntimeError):
                    self.manager.try_break(safe=True)
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')

    def test_task_fatigue_grows_with_time(self):
        start = self.manager.task_fatigue()
        self.clock.advance(40 * 60)
        self.assertGreater(self.manager.task_fatigue(), start)

    def test_task_fatigue_grows_with_repetitions(self):
        before = self.manager.task_fatigue()
        with patch('module.fatigue.random_delay', return_value=1.0):
            for _ in range(8):
                self.manager.try_break(safe=True, repeat_completed=True)
        self.assertGreater(self.manager.task_fatigue(), before)

    def test_task_fatigue_never_exceeds_one_hundred(self):
        self.manager.begin_task('RyouToppa', load_factor=2.0)
        self.clock.advance(24 * 60 * 60)
        with patch('module.fatigue.random_delay', return_value=1.0):
            for _ in range(200):
                self.manager.try_break(safe=True, repeat_completed=True)
        self.assertEqual(self.manager.task_fatigue(), 100.0)

    def test_global_fatigue_grows_monotonically(self):
        values = []
        for minutes in (0, 30, 60, 90, 120, 180):
            self.clock.value = minutes * 60
            values.append(self.manager.global_fatigue())
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[1])

    def test_scheduler_idle_time_does_not_add_global_fatigue(self):
        self.clock.advance(60 * 60)
        self.manager.end_global_activity()
        before = self.manager.global_fatigue()
        # scheduler_idle 只会冻结或恢复，绝不增加 GlobalFatigue
        self.clock.advance(8 * 60 * 60)
        self.assertLessEqual(self.manager.global_fatigue(), before)
        # 恢复后重新 active，GlobalFatigue 可以重新增长
        self.manager.begin_global_activity()
        self.clock.advance(60 * 60)
        self.assertGreater(self.manager.global_fatigue(), 0.0)

    def test_switching_task_resets_task_fatigue(self):
        self.clock.advance(60 * 60)
        before = self.manager.task_fatigue()
        self.manager.begin_task('RealmRaid')
        self.assertGreater(before, 0.0)
        self.assertEqual(self.manager.task_fatigue(), 0.0)

    def test_switching_task_keeps_global_fatigue(self):
        self.clock.advance(90 * 60)
        before = self.manager.global_fatigue()
        self.manager.begin_task('RealmRaid')
        self.assertEqual(self.manager.global_fatigue(), before)

    @patch('module.fatigue.random_triangular', return_value=60.0)
    def test_idle_mainly_recovers_task_fatigue(self, _duration_mock):
        self.clock.advance(60 * 60)
        before = self.manager.snapshot()
        with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
            result = self.manager.try_break(safe=True)
        task_drop = before.task - result.after.task
        global_drop = before.global_ - result.after.global_
        self.assertEqual(result.kind, 'idle')
        self.assertLess(result.after.global_, before.global_)
        self.assertGreater(task_drop, global_drop)

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_rest_recovers_both_fatigue_values(self, _duration_mock):
        self.clock.advance(150 * 60)
        before = self.manager.snapshot()
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            result = self.manager.try_break(safe=True)
        self.assertEqual(result.kind, 'rest')
        self.assertLess(result.after.task, before.task)
        self.assertLess(result.after.global_, before.global_)

    @patch('module.fatigue.random_triangular', return_value=1200.0)
    def test_recovery_never_makes_fatigue_negative(self, _duration_mock):
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            result = self.manager.try_break(safe=True)
        self.assertGreaterEqual(result.after.task, 0.0)
        self.assertGreaterEqual(result.after.global_, 0.0)

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_rest_starts_cooldown(self, _duration_mock):
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            result = self.manager.try_break(safe=True)
        self.assertGreater(result.cooldown, 0.0)
        self.assertGreater(self.manager.rest_cooldown_remaining(), 0.0)

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_cooldown_blocks_another_rest(self, _duration_mock):
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            self.manager.try_break(safe=True)
        with patch('module.fatigue.random_delay', return_value=1.0):
            result = self.manager.try_break(safe=True)
        self.assertTrue(result is None or result.kind != 'rest')
        self.assertEqual(self.manager.rest_probability(), 0.0)

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_rest_has_priority_over_idle(self, _duration_mock):
        self.clock.advance(150 * 60)
        draws = Mock(side_effect=[0.0, 1.0])
        with patch('module.fatigue.random_delay', draws):
            result = self.manager.try_break(safe=True)
        self.assertEqual(result.kind, 'rest')
        self.assertEqual(draws.call_count, 2)

    def test_unsafe_node_never_waits_or_records_repeat(self):
        with patch('module.fatigue.random_delay') as draw_mock:
            result = self.manager.try_break(safe=False, repeat_completed=True)
        self.assertIsNone(result)
        self.assertEqual(self.clock.sleeps, [])
        self.assertEqual(self.manager.task_repetitions, 0)
        draw_mock.assert_not_called()

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_break_is_clamped_to_wall_clock_deadline(self, _duration_mock):
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            result = self.manager.try_break(safe=True, max_break_seconds=180.0)
        self.assertEqual(result.duration, 180.0)
        self.assertEqual(self.clock.sleeps, [180.0])

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_break_is_skipped_when_deadline_is_too_close(self, _duration_mock):
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_delay', return_value=0.0):
            result = self.manager.try_break(safe=True, max_break_seconds=30.0)
        self.assertIsNone(result)
        self.assertEqual(self.clock.sleeps, [])

    def test_random_source_is_system_random(self):
        self.assertIsInstance(random_utils._rng, SystemRandom)

    def test_low_fatigue_has_low_trigger_probability(self):
        snapshot = self.manager.snapshot()
        self.assertLess(
            self.manager.idle_intensity(self.manager.idle_score(snapshot)), 0.02
        )
        # 低疲劳时事件率贴近基础值 rate_base，不是 0
        self.assertAlmostEqual(
            self.manager.idle_rate_per_hour(snapshot), self.config.idle.rate_base, delta=0.05
        )
        self.assertLess(self.manager.rest_probability(snapshot), 0.01)

    def test_high_fatigue_never_forces_trigger(self):
        high = FatigueSnapshot(task=100.0, global_=100.0)
        intensity = self.manager.idle_intensity(self.manager.idle_score(high))
        self.assertGreater(intensity, 0.99)
        self.assertLess(intensity, 1.0)
        rate = self.manager.idle_rate_per_hour(high)
        self.assertLess(rate, self.config.idle.rate_max)
        self.assertLess(self.manager.rest_probability(high), 1.0)

    def test_same_task_identity_keeps_accumulated_state(self):
        self.clock.advance(40 * 60)
        before = self.manager.task_fatigue()
        switched = self.manager.begin_task('RyouToppa', load_factor=1.1)
        self.assertFalse(switched)
        self.assertGreaterEqual(self.manager.task_fatigue(), before)

    def test_new_scheduler_run_restarts_same_task_fatigue(self):
        self.clock.advance(40 * 60)
        self.assertGreater(self.manager.task_fatigue(), 0.0)
        restarted = self.manager.begin_task('RyouToppa', restart=True)
        self.assertTrue(restarted)
        self.assertEqual(self.manager.task_fatigue(), 0.0)

    def test_disabled_fatigue_never_waits(self):
        self.manager.update_config(FatigueConfig(enable=False))
        self.clock.advance(180 * 60)
        with patch('module.fatigue.random_delay') as draw_mock:
            result = self.manager.try_break(safe=True, repeat_completed=True)
        self.assertIsNone(result)
        self.assertEqual(self.clock.sleeps, [])
        draw_mock.assert_not_called()

    def test_ui_snapshot_reports_disabled_state(self):
        self.manager.update_config(FatigueConfig(enable=False, load_factor=0.9))
        snapshot = self.manager.ui_snapshot()
        self.assertFalse(snapshot['fatigue_enabled'])
        self.assertEqual(snapshot['fatigue_state'], 'disabled')
        self.assertEqual(snapshot['fatigue_load_factor'], 0.9)

    @patch('module.fatigue.random_triangular', return_value=60.0)
    def test_ui_snapshot_reports_idle_while_sleeping(self, _duration_mock):
        states = []

        def observe_state(duration):
            states.append(self.manager.state)
            self.clock.sleep(duration)

        self.manager._sleep = observe_state
        self.clock.advance(60 * 60)
        with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
            self.manager.try_break(safe=True)
        self.assertEqual(states, ['idle'])
        self.assertEqual(self.manager.state, 'normal')

    @patch('module.fatigue.random_triangular', return_value=600.0)
    def test_ui_snapshot_reports_rest_then_cooldown(self, _duration_mock):
        states = []

        def observe_state(duration):
            states.append(self.manager.state)
            self.clock.sleep(duration)

        self.manager._sleep = observe_state
        self.clock.advance(150 * 60)
        with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
            self.manager.try_break(safe=True)
        self.assertEqual(states, ['rest'])
        self.assertEqual(self.manager.state, 'cooldown')

    def test_runtime_load_factor_updates_current_task(self):
        self.clock.advance(30 * 60)
        before = self.manager.task_fatigue()
        self.manager.set_load_factor(1.3)
        self.assertEqual(self.manager.ui_snapshot()['fatigue_load_factor'], 1.3)
        self.assertGreater(self.manager.task_fatigue(), before)

    def test_instances_keep_independent_load_factors(self):
        reset_fatigue_managers()
        first = get_fatigue_manager('oas1', FatigueConfig(enable=True, load_factor=1.1))
        second = get_fatigue_manager('oas2', FatigueConfig(enable=True, load_factor=0.9))
        first.set_load_factor(1.3)
        self.assertEqual(first.load_factor, 1.3)
        self.assertEqual(second.load_factor, 0.9)

    def test_load_factor_config_range(self):
        self.assertEqual(FatigueConfig(load_factor=0.8).load_factor, 0.8)
        self.assertEqual(FatigueConfig(load_factor=1.3).load_factor, 1.3)
        with self.assertRaises(ValidationError):
            FatigueConfig(load_factor=0.75)
        with self.assertRaises(ValidationError):
            FatigueConfig(load_factor=1.35)

    # P0-A：运行时调整负荷系数后始终满足 0 <= TaskRecovery <= 当前 RawTask

    def test_lowering_load_factor_after_real_rest_keeps_recovery_invariant(self):
        # 通过真实休息累计出较大的任务恢复量，再降低负荷系数
        self.clock.advance(90 * 60)
        self.trigger_rest(10 * 60)
        self.assertGreater(self.manager._task_recovery, 0.0)
        self.manager.set_load_factor(0.8)
        raw_task = self.manager._raw_task_fatigue()
        self.assertGreaterEqual(self.manager._task_recovery, 0.0)
        self.assertLessEqual(self.manager._task_recovery, raw_task + 1e-9)
        self.assertEqual(self.manager.task_fatigue(), 0.0)
        # 降到 0 之后继续 active，任务疲劳必须重新增长
        self.clock.advance(20 * 60)
        self.assertGreater(self.manager.task_fatigue(), 0.0)

    def test_lowering_load_factor_removes_recovery_dead_zone(self):
        self.clock.advance(90 * 60)
        self.trigger_rest(10 * 60)
        self.manager.set_load_factor(0.8)
        self.assertEqual(self.manager.task_fatigue(), 0.0)
        raw_at_zero = self.manager._raw_task_fatigue()
        self.clock.advance(5 * 60)
        raw_later = self.manager._raw_task_fatigue()
        self.assertGreater(raw_later, raw_at_zero)
        # 疲劳增量与 RawTask 增量一致，说明旧恢复量没有形成“死区”
        self.assertAlmostEqual(self.manager.task_fatigue(), raw_later - raw_at_zero)

    def test_update_config_lower_load_factor_keeps_recovery_invariant(self):
        self.clock.advance(90 * 60)
        self.trigger_rest(10 * 60)
        self.assertGreater(self.manager._task_recovery, 0.0)
        self.manager.update_config(FatigueConfig(enable=True, load_factor=0.8))
        raw_task = self.manager._raw_task_fatigue()
        self.assertGreaterEqual(self.manager._task_recovery, 0.0)
        self.assertLessEqual(self.manager._task_recovery, raw_task + 1e-9)

    def test_raising_load_factor_does_not_grow_recovery(self):
        self.clock.advance(60 * 60)
        self.trigger_idle(60.0)
        recovery_before = self.manager._task_recovery
        self.assertGreater(recovery_before, 0.0)
        self.manager.set_load_factor(1.3)
        self.assertEqual(self.manager._task_recovery, recovery_before)

    # P0-B：idle/rest 各终止路径不得错误重新开启 active 计时

    def _assert_scheduler_idle_and_frozen(self, task_before, global_before):
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')
        self.assertIsNone(self.manager._task_active_started_at)
        self.assertIsNone(self.manager._global_active_started_at)
        self.clock.advance(30 * 60)
        self.assertAlmostEqual(self.manager.task_active_elapsed(), task_before)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), global_before)

    def test_break_normal_end_resumes_active_segment(self):
        self.clock.advance(60 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()
        result = self.trigger_rest(10 * 60)
        self.assertEqual(result.kind, 'rest')
        self.assertEqual(self.manager.activity_state, 'active')
        self.assertIsNotNone(self.manager._task_active_started_at)
        self.assertIsNotNone(self.manager._global_active_started_at)
        # 休息本身不计入 active 时间
        self.assertAlmostEqual(self.manager.task_active_elapsed(), task_before)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), global_before)
        # 恢复后继续累计
        self.clock.advance(10 * 60)
        self.assertAlmostEqual(self.manager.task_active_elapsed(), task_before + 10 * 60)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), global_before + 10 * 60)

    def test_break_stop_does_not_resume_active_segment(self):
        self.clock.advance(60 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()
        with patch('module.fatigue.random_triangular', return_value=60.0):
            with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
                self.manager.try_break(safe=True, should_resume=lambda: False)
        self._assert_scheduler_idle_and_frozen(task_before, global_before)

    def test_break_deadline_does_not_resume_active_segment(self):
        self.clock.advance(150 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()
        with patch('module.fatigue.random_triangular', return_value=600.0):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                self.manager.try_break(
                    safe=True,
                    max_break_seconds=180.0,
                    should_resume=lambda: False,
                )
        self._assert_scheduler_idle_and_frozen(task_before, global_before)

    def test_break_cancel_does_not_resume_active_segment(self):
        self.clock.advance(60 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()

        def cancel_during_sleep(_duration):
            raise SystemExit()

        self.manager._sleep = cancel_during_sleep
        with patch('module.fatigue.random_triangular', return_value=60.0):
            with patch('module.fatigue.random_delay', side_effect=[1.0, 0.0]):
                with self.assertRaises(SystemExit):
                    self.manager.try_break(safe=True)
        self._assert_scheduler_idle_and_frozen(task_before, global_before)

    def test_break_terminating_exception_does_not_resume_active_segment(self):
        self.clock.advance(150 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()

        def boom_during_sleep(_duration):
            raise RuntimeError('terminating')

        self.manager._sleep = boom_during_sleep
        with patch('module.fatigue.random_triangular', return_value=600.0):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                with self.assertRaises(RuntimeError):
                    self.manager.try_break(safe=True)
        self._assert_scheduler_idle_and_frozen(task_before, global_before)

    def test_interrupted_break_applies_no_recovery_or_cooldown(self):
        self.clock.advance(150 * 60)
        task_recovery_before = self.manager._task_recovery
        global_recovery_before = self.manager._global_recovery

        def boom_during_sleep(_duration):
            raise RuntimeError('terminating')

        self.manager._sleep = boom_during_sleep
        with patch('module.fatigue.random_triangular', return_value=600.0):
            with patch('module.fatigue.random_delay', side_effect=[0.0, 1.0]):
                with self.assertRaises(RuntimeError):
                    self.manager.try_break(safe=True)
        self.assertEqual(self.manager._task_recovery, task_recovery_before)
        self.assertEqual(self.manager._global_recovery, global_recovery_before)
        self.assertEqual(self.manager.rest_cooldown_remaining(), 0.0)

    # idle 触发概率归一化：事件率 / hazard 模型

    def _run_silent_idle_check(self):
        # 走一次 idle 判断但强制不触发（rest、idle 抽签都取 1.0），只推进检查基准
        with patch('module.fatigue.random_triangular', return_value=60.0):
            with patch('module.fatigue.random_delay', return_value=1.0):
                return self.manager.try_break(safe=True)

    def test_node_probability_shrinks_with_denser_safe_nodes(self):
        rate = 2.0
        p_dense = self.manager._node_probability_from_rate(rate, 25.0)
        p_sparse = self.manager._node_probability_from_rate(rate, 180.0)
        self.assertLess(p_dense, p_sparse)
        self.assertAlmostEqual(p_dense, 1.0 - exp(-2.0 * 25.0 / 3600.0))
        self.assertAlmostEqual(p_sparse, 1.0 - exp(-2.0 * 180.0 / 3600.0))

    def test_overall_event_rate_independent_of_node_frequency(self):
        # 相同 IdleRate、相同总 active 时间：拆成 144 个 25s 密节点或 1 个 3600s 疏节点，
        # 累计“不触发”概率一致，说明整体事件率由时间决定、不随节点数放大。
        rate = 3.0
        miss_sparse = exp(-rate * 3600.0 / 3600.0)
        miss_dense = 1.0
        for _ in range(144):
            miss_dense *= 1.0 - self.manager._node_probability_from_rate(rate, 25.0)
        self.assertAlmostEqual(miss_dense, miss_sparse, places=6)

    def test_idle_rate_stays_within_base_and_max(self):
        base = self.config.idle.rate_base
        rate_max = self.config.idle.rate_max
        for task in range(0, 101, 10):
            for glob in range(0, 101, 10):
                snapshot = FatigueSnapshot(task=float(task), global_=float(glob))
                rate = self.manager.idle_rate_per_hour(snapshot)
                self.assertGreaterEqual(rate, base)
                self.assertLessEqual(rate, rate_max)

    def test_low_fatigue_intensity_near_zero_rate_near_base(self):
        snapshot = FatigueSnapshot(task=0.0, global_=0.0)
        self.assertLess(
            self.manager.idle_intensity(self.manager.idle_score(snapshot)), 0.01
        )
        self.assertAlmostEqual(
            self.manager.idle_rate_per_hour(snapshot),
            self.config.idle.rate_base,
            delta=0.05,
        )

    def test_high_fatigue_intensity_near_one_rate_near_max(self):
        snapshot = FatigueSnapshot(task=100.0, global_=100.0)
        intensity = self.manager.idle_intensity(self.manager.idle_score(snapshot))
        self.assertGreater(intensity, 0.99)
        self.assertLess(intensity, 1.0)
        rate = self.manager.idle_rate_per_hour(snapshot)
        self.assertGreater(rate, self.config.idle.rate_max - 0.1)
        self.assertLess(rate, self.config.idle.rate_max)

    def test_first_node_delta_is_active_time_since_task_start(self):
        self.clock.advance(30 * 60)
        self._run_silent_idle_check()
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 30 * 60)

    def test_idle_check_delta_excludes_idle_and_rest_time(self):
        self.clock.advance(20 * 60)
        self.trigger_idle(5 * 60)
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 20 * 60)
        self.clock.advance(10 * 60)
        self._run_silent_idle_check()
        # 墙钟已过 35 分钟，但基准只推进到 30 分钟（5 分钟发呆不计入）
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 30 * 60)

    def test_idle_check_baseline_advances_even_without_trigger(self):
        self.clock.advance(30 * 60)
        result = self._run_silent_idle_check()
        self.assertIsNone(result)
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 30 * 60)
        self.clock.advance(5 * 60)
        self._run_silent_idle_check()
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 35 * 60)

    def test_new_task_resets_idle_check_baseline(self):
        self.clock.advance(30 * 60)
        self._run_silent_idle_check()
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 30 * 60)
        self.manager.begin_task('RealmRaid')
        self.assertEqual(self.manager._last_idle_check_task_elapsed, 0.0)

    def test_same_task_page_switch_keeps_idle_check_baseline(self):
        self.clock.advance(30 * 60)
        self._run_silent_idle_check()
        baseline = self.manager._last_idle_check_task_elapsed
        self.assertAlmostEqual(baseline, 30 * 60)
        switched = self.manager.begin_task('RyouToppa', load_factor=1.0)
        self.assertFalse(switched)
        self.assertEqual(self.manager._last_idle_check_task_elapsed, baseline)

    def test_restart_same_task_resets_idle_check_baseline(self):
        self.clock.advance(30 * 60)
        self._run_silent_idle_check()
        self.assertAlmostEqual(self.manager._last_idle_check_task_elapsed, 30 * 60)
        restarted = self.manager.begin_task('RyouToppa', restart=True)
        self.assertTrue(restarted)
        self.assertEqual(self.manager._last_idle_check_task_elapsed, 0.0)

    def test_rest_trigger_advances_idle_baseline_without_rest_time(self):
        self.clock.advance(150 * 60)
        pre_rest_active = self.manager.task_active_elapsed()
        self.trigger_rest(10 * 60)
        self.assertAlmostEqual(
            self.manager._last_idle_check_task_elapsed, pre_rest_active
        )
        self.clock.advance(4 * 60)
        self._run_silent_idle_check()
        self.assertAlmostEqual(
            self.manager._last_idle_check_task_elapsed, pre_rest_active + 4 * 60
        )

    def test_idle_rate_drops_after_idle_recovery(self):
        self.clock.advance(60 * 60)
        rate_before = self.manager.idle_rate_per_hour()
        self.trigger_idle(60.0)
        self.assertLess(self.manager.idle_rate_per_hour(), rate_before)

    def test_load_factor_flows_into_idle_rate_via_task_fatigue(self):
        self.clock.advance(60 * 60)
        self.manager.set_load_factor(0.8)
        low = self.manager.idle_rate_per_hour()
        self.manager.set_load_factor(1.3)
        high = self.manager.idle_rate_per_hour()
        self.assertGreater(high, low)

    def test_idle_result_reports_rate_and_node_probability(self):
        self.clock.advance(60 * 60)
        before = self.manager.snapshot()
        expected_rate = self.manager.idle_rate_per_hour(before)
        result = self.trigger_idle(60.0)
        self.assertEqual(result.kind, 'idle')
        self.assertAlmostEqual(result.idle_rate, expected_rate)
        self.assertAlmostEqual(
            result.probability,
            self.manager._node_probability_from_rate(expected_rate, 60 * 60),
        )

    def test_preview_reference_scenario_uses_170_repetitions(self):
        preview = self.manager.load_factor_preview()
        self.assertEqual(
            [row['factor'] for row in preview],
            [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3],
        )
        row = next(r for r in preview if r['factor'] == 1.0)
        expected_task = self.manager._clamp(
            self.manager._calculate_raw_task_fatigue(
                active_seconds=60 * 60, repetitions=170, load_factor=1.0
            )
        )
        self.assertEqual(row['task_fatigue'], round(expected_task, 2))

    def test_preview_rows_expose_intensity_and_rate_within_bounds(self):
        for row in self.manager.load_factor_preview():
            self.assertIn('idle_intensity', row)
            self.assertIn('idle_rate_per_hour', row)
            self.assertIn('idle_probability_at_25s', row)
            self.assertGreaterEqual(row['idle_rate_per_hour'], self.config.idle.rate_base)
            self.assertLessEqual(row['idle_rate_per_hour'], self.config.idle.rate_max)

    def test_preview_rate_uses_production_formula(self):
        row = next(
            r for r in self.manager.load_factor_preview() if r['factor'] == 1.15
        )
        expected_task = self._clamp_preview_task(1.15)
        snapshot = FatigueSnapshot(task=expected_task, global_=10.0)
        expected_rate = self.manager.idle_rate_per_hour(snapshot)
        self.assertEqual(row['idle_rate_per_hour'], round(expected_rate, 4))
        self.assertEqual(
            row['idle_probability_at_25s'],
            round(self.manager._node_probability_from_rate(expected_rate, 25.0), 6),
        )

    # idle 事件率的 base/max 混合 + 时长分布 + 第一小时统计目标

    def test_idle_rate_is_base_plus_intensity_span(self):
        idle = self.config.idle
        for task, glob in ((0.0, 0.0), (40.0, 10.0), (80.0, 30.0), (100.0, 100.0)):
            snapshot = FatigueSnapshot(task=task, global_=glob)
            intensity = self.manager.idle_intensity(self.manager.idle_score(snapshot))
            expected = idle.rate_base + (idle.rate_max - idle.rate_base) * intensity
            self.assertAlmostEqual(
                self.manager.idle_rate_per_hour(snapshot), expected
            )

    def test_global_fatigue_raises_idle_rate_at_fixed_task_fatigue(self):
        low_global = FatigueSnapshot(task=50.0, global_=0.0)
        high_global = FatigueSnapshot(task=50.0, global_=80.0)
        self.assertGreater(
            self.manager.idle_rate_per_hour(high_global),
            self.manager.idle_rate_per_hour(low_global),
        )

    def test_idle_duration_min_is_15_and_mode_rises_with_fatigue(self):
        low = self.manager._duration_range(self.config.idle, 0.0)
        mid = self.manager._duration_range(self.config.idle, 50.0)
        high = self.manager._duration_range(self.config.idle, 100.0)
        self.assertEqual(low[0], 15.0)
        self.assertEqual(high[0], 15.0)
        self.assertLess(low[2], mid[2])
        self.assertLess(mid[2], high[2])
        self.assertLessEqual(low[1], mid[1])
        self.assertLessEqual(mid[1], high[1])
        self.assertLessEqual(high[1], self.config.idle.maximum_seconds)

    def test_idle_duration_mean_stays_moderate(self):
        for fatigue in (0.0, 30.0, 50.0, 80.0, 100.0):
            lo, hi, mode = self.manager._duration_range(self.config.idle, fatigue)
            mean = (lo + hi + mode) / 3.0
            self.assertGreaterEqual(mean, 15.0)
            self.assertLessEqual(mean, 90.0)
        lo, hi, mode = self.manager._duration_range(self.config.idle, 50.0)
        self.assertGreaterEqual(mode, 20.0)
        self.assertLessEqual(mode, 60.0)

    def test_idle_duration_hard_cap_is_120(self):
        self.assertEqual(self.config.idle.maximum_seconds, 120.0)
        # 任何疲劳档，三角分布上限都不超过 120 秒
        for fatigue in (0.0, 20.0, 40.0, 60.0, 80.0, 100.0):
            lo, hi, mode = self.manager._duration_range(self.config.idle, fatigue)
            self.assertLessEqual(hi, 120.0)
            self.assertLessEqual(mode, hi)
        # 满疲劳时正好触到 120 秒上限
        self.assertAlmostEqual(
            self.manager._duration_range(self.config.idle, 100.0)[1], 120.0
        )
        # 实际采样也不会超过上限
        for _ in range(200):
            self.assertLessEqual(self.manager._idle_duration(100.0), 120.0)

    def test_first_hour_theoretical_idle_expectation_in_target_band(self):
        # L=1.30，60 分钟连续 active，n 线性增至约 170，GlobalFatigue 按现有公式增长。
        # 对 hazard 做数值积分（不含真实随机触发与 recovery），期望 idle 次数应落在目标带内。
        self.manager.begin_task('RyouToppa', load_factor=1.3)
        total_rounds = 170
        minutes = 60
        step_seconds = 10
        expected_events = 0.0
        for sec in range(0, minutes * 60, step_seconds):
            t_min = sec / 60.0
            n = int(total_rounds * sec / (minutes * 60))
            task_fat = self.manager._clamp(
                self.manager._calculate_raw_task_fatigue(
                    active_seconds=sec, repetitions=n, load_factor=1.3
                )
            )
            global_fat = self.manager._clamp(
                100.0 * (1.0 - exp(-((t_min / 180.0) ** 2)))
            )
            snapshot = FatigueSnapshot(task=task_fat, global_=global_fat)
            rate = self.manager.idle_rate_per_hour(snapshot)
            expected_events += rate * step_seconds / 3600.0
        # 目标约 2~2.x 次；硬约束是不能明显 <1.5 或 >3.5
        self.assertGreater(expected_events, 1.5)
        self.assertLess(expected_events, 3.5)

    # scheduler_idle（调度空档）GlobalFatigue 自然恢复

    def _enter_scheduler_idle(self, active_minutes: float) -> float:
        self.clock.advance(active_minutes * 60)
        g0 = self.manager.global_fatigue()
        self.manager.end_global_activity()
        self.assertEqual(self.manager.activity_state, 'scheduler_idle')
        return g0

    def test_scheduler_idle_within_delay_freezes_global_fatigue(self):
        g0 = self._enter_scheduler_idle(90)
        self.clock.advance(4 * 60)
        self.assertAlmostEqual(self.manager.global_fatigue(), g0)

    def test_scheduler_idle_at_delay_boundary_recovers_nothing(self):
        g0 = self._enter_scheduler_idle(90)
        self.clock.advance(5 * 60)
        self.assertAlmostEqual(self.manager.global_fatigue(), g0, places=4)

    def test_scheduler_idle_recovery_ratio_curve(self):
        cases = {15: 0.255, 30: 0.521, 60: 0.802, 120: 0.966}
        for minutes, expected_ratio in cases.items():
            clock = FakeClock()
            manager = FatigueManager(
                FatigueConfig(enable=True), clock=clock, sleeper=clock.sleep
            )
            manager.begin_task('RyouToppa', load_factor=1.0)
            clock.advance(90 * 60)
            g0 = manager.global_fatigue()
            manager.end_global_activity()
            clock.advance(minutes * 60)
            recovered_ratio = (g0 - manager.global_fatigue()) / g0
            self.assertAlmostEqual(recovered_ratio, expected_ratio, delta=0.01)

    def test_scheduler_idle_recovery_never_negative(self):
        self._enter_scheduler_idle(90)
        self.clock.advance(24 * 60 * 60)
        self.assertGreaterEqual(self.manager.global_fatigue(), 0.0)

    def test_scheduler_idle_recovery_no_future_credit(self):
        self._enter_scheduler_idle(60)
        self.clock.advance(10 * 60 * 60)
        # 指数曲线只会渐近到 0，数小时后实际值极小
        self.assertAlmostEqual(self.manager.global_fatigue(), 0.0, places=4)
        self.assertLessEqual(
            self.manager._global_recovery, self.manager._raw_global_fatigue() + 1e-9
        )
        self.manager.begin_global_activity()
        self.assertAlmostEqual(self.manager.global_fatigue(), 0.0, places=2)
        self.clock.advance(45 * 60)
        self.assertGreater(self.manager.global_fatigue(), 0.0)

    def test_scheduler_idle_recovery_is_idempotent(self):
        g0 = self._enter_scheduler_idle(90)
        self.clock.advance(30 * 60)
        first = self.manager.global_fatigue()
        for _ in range(5):
            self.manager.global_fatigue()
            self.manager.snapshot()
            self.manager.ui_snapshot()
        self.assertEqual(self.manager.global_fatigue(), first)
        self.assertLess(first, g0)

    def test_disjoint_scheduler_idle_segments_are_not_summed(self):
        self._enter_scheduler_idle(90)
        self.clock.advance(4 * 60)
        self.manager.begin_global_activity()
        self.clock.advance(1 * 60)
        self.manager.end_global_activity()
        self.assertEqual(self.manager._scheduler_idle_recovery_applied, 0.0)
        self.clock.advance(4 * 60)
        self.assertEqual(self.manager._scheduler_idle_recovery_applied, 0.0)

    def test_scheduler_idle_session_ends_on_active(self):
        self._enter_scheduler_idle(90)
        self.clock.advance(20 * 60)
        recovered = self.manager.global_fatigue()
        self.manager.begin_global_activity()
        self.assertIsNone(self.manager._scheduler_idle_started_at)
        self.assertAlmostEqual(self.manager.global_fatigue(), recovered, places=4)

    def test_new_scheduler_idle_session_uses_fresh_baseline(self):
        self._enter_scheduler_idle(90)
        self.clock.advance(30 * 60)
        self.manager.begin_global_activity()
        self.clock.advance(10 * 60)
        g1 = self.manager.global_fatigue()
        self.manager.end_global_activity()
        self.assertEqual(self.manager._scheduler_idle_recovery_applied, 0.0)
        self.clock.advance(4 * 60)
        self.assertAlmostEqual(self.manager.global_fatigue(), g1)

    def test_scheduler_idle_does_not_change_active_elapsed(self):
        self.clock.advance(60 * 60)
        task_before = self.manager.task_active_elapsed()
        global_before = self.manager.global_active_elapsed()
        self.manager.end_global_activity()
        self.clock.advance(3 * 60 * 60)
        self.manager.global_fatigue()
        self.assertAlmostEqual(self.manager.task_active_elapsed(), task_before)
        self.assertAlmostEqual(self.manager.global_active_elapsed(), global_before)

    def test_scheduler_idle_recovery_does_not_touch_task_fatigue(self):
        self.clock.advance(60 * 60)
        task_before = self.manager.task_fatigue()
        self.assertGreater(task_before, 0.0)
        self.manager.end_global_activity()
        self.clock.advance(5 * 60 * 60)
        self.manager.global_fatigue()
        self.assertAlmostEqual(self.manager.task_fatigue(), task_before)

    def test_active_regrows_global_fatigue_after_scheduler_idle_recovery(self):
        self._enter_scheduler_idle(60)
        self.clock.advance(6 * 60 * 60)
        self.assertAlmostEqual(self.manager.global_fatigue(), 0.0, places=2)
        self.manager.begin_global_activity()
        self.clock.advance(60 * 60)
        self.assertGreater(self.manager.global_fatigue(), 5.0)

    def test_scheduler_idle_config_validation(self):
        from tasks.GlobalGame.config import SchedulerIdleConfig
        self.assertEqual(SchedulerIdleConfig().recovery_delay_minutes, 5.0)
        self.assertEqual(SchedulerIdleConfig().recovery_tau_minutes, 34.0)
        with self.assertRaises(ValidationError):
            SchedulerIdleConfig(recovery_delay_minutes=-1.0)
        with self.assertRaises(ValidationError):
            SchedulerIdleConfig(recovery_tau_minutes=0.0)
