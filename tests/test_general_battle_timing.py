import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from module.base.timer import Timer
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.page import page_battle_result
from tasks.RealmRaid.script_task import ScriptTask as RealmRaidScriptTask


class _TimerStub:
    def __init__(self, started=False, reached=False):
        self.limit = 0
        self._started = started
        self._reached = reached
        self.reset_count = 0

    def started(self):
        return self._started

    def reached(self):
        return self._reached

    def reset(self):
        self._started = True
        self.reset_count += 1
        return self


class GeneralBattleTimingTest(TestCase):
    def setUp(self):
        self.task = GeneralBattle.__new__(GeneralBattle)

    def _build_context(self):
        self.task.config = SimpleNamespace(
            global_game=SimpleNamespace(
                battle=SimpleNamespace(battle_timeout=420),
            ),
        )
        self.task._battle_shared_state = {}
        self.task._get_battle_behavior_scopes = Mock(return_value={})
        self.task._build_timed_battle_inspections = Mock(return_value={})
        config = SimpleNamespace(battle_timeout=60, quick_exit=False)
        return self.task._build_context(config, None, 'test'), config

    def test_default_ranges_keep_old_values(self):
        self.assertEqual(self.task._next_prepare_click_delay(), 3.0)
        self.assertEqual(self.task._next_settlement_click_interval(), 0.8)

    @patch('tasks.Component.GeneralBattle.general_battle.random_delay')
    def test_custom_ranges_use_public_random_delay(self, random_delay_mock):
        random_delay_mock.side_effect = (2.8, 0.72)
        self.task.PREPARE_CLICK_DELAY_RANGE = (2.5, 3.5)
        self.task.SETTLEMENT_CLICK_INTERVAL_RANGE = (0.65, 0.95)

        self.assertEqual(self.task._next_prepare_click_delay(), 2.8)
        self.assertEqual(self.task._next_settlement_click_interval(), 0.72)
        self.assertEqual(random_delay_mock.call_args_list, [
            call(2.5, 3.5),
            call(0.65, 0.95),
        ])

    def test_invalid_ranges_use_public_validation(self):
        invalid_ranges = (
            (-1.0, 1.0),
            (1.0, -1.0),
            (2.0, 1.0),
            (float('nan'), 1.0),
            (0.0, float('inf')),
            (True, 1.0),
            ('0.1', 1.0),
        )
        for value in invalid_ranges:
            with self.subTest(value=value):
                self.task.PREPARE_CLICK_DELAY_RANGE = value
                with self.assertRaises((TypeError, ValueError)):
                    self.task._next_prepare_click_delay()

    @patch('tasks.Component.GeneralBattle.general_battle.random_delay')
    def test_context_creation_does_not_sample_settlement_interval(self, random_delay_mock):
        random_delay_mock.return_value = 3.0
        first, _ = self._build_context()
        second, _ = self._build_context()

        self.assertFalse(first.settlement_click_timer.started())
        self.assertFalse(second.settlement_click_timer.started())
        self.assertEqual(first.settlement_click_timer.limit, 0)
        self.assertEqual(second.settlement_click_timer.limit, 0)
        self.assertIsNot(first.settlement_click_timer, second.settlement_click_timer)
        first.settlement_click_timer.reset()
        self.assertTrue(first.settlement_click_timer.started())
        self.assertFalse(second.settlement_click_timer.started())
        self.assertEqual(random_delay_mock.call_args_list, [
            call(3.0, 3.0),
            call(3.0, 3.0),
        ])

    def test_prepare_timer_only_applies_when_team_is_locked(self):
        context = SimpleNamespace(prepare_click_timer=Timer(3.0))

        self.assertFalse(
            self.task._prepare_click_ready(
                context,
                SimpleNamespace(lock_team_enable=True),
            )
        )
        self.assertTrue(context.prepare_click_timer.started())

        self.assertTrue(
            self.task._prepare_click_ready(
                context,
                SimpleNamespace(lock_team_enable=False),
            )
        )
        self.assertFalse(context.prepare_click_timer.started())

    def test_leaving_prepare_page_clears_prepare_timer(self):
        context = SimpleNamespace(prepare_click_timer=Timer(3.0).start())

        self.task._sync_prepare_click_timer(context, None)

        self.assertFalse(context.prepare_click_timer.started())

    def test_first_settlement_click_is_immediate(self):
        timer = _TimerStub()
        context = SimpleNamespace(settlement_click_timer=timer)
        self.task.click = Mock()
        self.task._next_settlement_click_interval = Mock(return_value=0.8)

        self.assertTrue(self.task._settlement_click(context))
        self.task.click.assert_called_once()
        self.task._next_settlement_click_interval.assert_called_once_with()
        self.assertEqual(timer.limit, 0.8)
        self.assertEqual(timer.reset_count, 1)

    def test_later_settlement_click_waits_and_resamples(self):
        timer = _TimerStub(started=True, reached=False)
        context = SimpleNamespace(settlement_click_timer=timer)
        self.task.click = Mock()
        self.task._next_settlement_click_interval = Mock(return_value=0.9)

        self.assertFalse(self.task._settlement_click(context))
        self.task.click.assert_not_called()
        self.task._next_settlement_click_interval.assert_not_called()

        timer._reached = True
        self.assertTrue(self.task._settlement_click(context))
        self.task.click.assert_called_once()
        self.task._next_settlement_click_interval.assert_called_once_with()
        self.assertEqual(timer.limit, 0.9)
        self.assertEqual(timer.reset_count, 1)

    def test_result_and_reward_share_settlement_timer(self):
        timer = _TimerStub()
        context = SimpleNamespace(
            settlement_click_timer=timer,
            reward_no_battle_ts=None,
            is_win=False,
            last_page=None,
        )
        config = SimpleNamespace()
        self.task.device = SimpleNamespace(click_record_clear=Mock())
        self.task.appear = Mock(return_value=False)
        self.task.appear_then_click = Mock(return_value=False)
        self.task.click = Mock()
        self.task._next_settlement_click_interval = Mock(return_value=0.8)

        self.task._handle_result(context, config)
        context.last_page = page_battle_result
        self.task._handle_reward(context, config)

        self.task.click.assert_called_once()
        self.assertEqual(timer.reset_count, 1)

    @patch('tasks.Component.GeneralBattle.general_battle.random_delay')
    def test_new_round_replaces_settlement_timer(self, random_delay_mock):
        random_delay_mock.side_effect = (3.0, 3.2)
        context, config = self._build_context()
        old_prepare_timer = context.prepare_click_timer
        old_timer = context.settlement_click_timer
        old_timer.reset()

        self.task._reset_round_context(context, config, continuous_count=2)

        self.assertIsNot(context.prepare_click_timer, old_prepare_timer)
        self.assertEqual(context.prepare_click_timer.limit, 3.2)
        self.assertIsNot(context.settlement_click_timer, old_timer)
        self.assertFalse(context.settlement_click_timer.started())
        self.assertEqual(context.settlement_click_timer.limit, 0)

    def test_click_exception_does_not_reset_timer(self):
        timer = _TimerStub()
        context = SimpleNamespace(settlement_click_timer=timer)
        self.task.click = Mock(side_effect=RuntimeError('click failed'))
        self.task._next_settlement_click_interval = Mock(return_value=0.8)

        with self.assertRaises(RuntimeError):
            self.task._settlement_click(context)

        self.task._next_settlement_click_interval.assert_not_called()
        self.assertEqual(timer.reset_count, 0)

    @patch('tasks.Component.GeneralBattle.general_battle.random_delay')
    def test_realm_raid_ranges_are_read_by_general_battle(self, random_delay_mock):
        random_delay_mock.side_effect = (2.9, 0.75)
        task = RealmRaidScriptTask.__new__(RealmRaidScriptTask)

        self.assertEqual(task._next_prepare_click_delay(), 2.9)
        self.assertEqual(task._next_settlement_click_interval(), 0.75)
        self.assertEqual(random_delay_mock.call_args_list, [
            call(2.5, 3.5),
            call(0.65, 0.95),
        ])

    def test_realm_raid_has_no_click_reaction_delay(self):
        self.assertNotIn('CLICK_REACTION_DELAY', RealmRaidScriptTask.__dict__)

    def test_realm_raid_fire_keeps_original_timing_arguments(self):
        source = inspect.getsource(RealmRaidScriptTask.fire)

        self.assertIn('self.appear_then_click(self.I_FIRE, interval=1)', source)
        self.assertIn('self.click(click, interval=2)', source)
        self.assertNotIn('confirm_delay', source)
        self.assertNotIn('reaction_delay', source)

    def test_realm_raid_quick_exit_skips_settlement_click(self):
        task = RealmRaidScriptTask.__new__(RealmRaidScriptTask)
        task.appear = Mock(return_value=False)
        task._settlement_click = Mock()
        context = SimpleNamespace(reward_no_battle_ts=1, is_win=False)
        config = SimpleNamespace(quick_exit=True)

        task._handle_result(context, config)

        task._settlement_click.assert_not_called()
