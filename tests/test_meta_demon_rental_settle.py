"""租借出战后的有限稳定等待与原恢复预算接通检查。"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GamePageUnknownError
from tasks.MetaDemonRotation.rental import DEPLOY, deploy_rental
from tasks.MetaDemonRotation.progress import RotationProgress, account_identity
from tasks.MetaDemonRotation.rotation import run_rotation


class RentalSettleTest(TestCase):
    def run_sequence(self, frames, *, border=True):
        task = Mock()
        task.I_CHECK_BOSS_PAGE = object()
        state = {'deployed': False, 'frame': (True, False), 'index': 0, 'time': 0.}
        def screenshot():
            if state['deployed']:
                state['frame'] = frames[min(state['index'], len(frames) - 1)]
                state['index'] += 1
        def appear(rule):
            return state['frame'][0] if rule is DEPLOY else rule is task.I_CHECK_BOSS_PAGE and state['frame'][1]
        def click_deploy(rule, **kwargs):
            self.assertIs(DEPLOY, rule)
            state['deployed'] = True
            return True
        task.screenshot.side_effect = screenshot
        task.appear.side_effect = appear
        task.appear_then_click.side_effect = click_deploy
        clock = SimpleNamespace(monotonic=lambda: state['time'],
                                sleep=lambda delay: state.update(time=state['time'] + delay))
        with patch('tasks.MetaDemonRotation.rental.time', clock), patch(
            'tasks.MetaDemonRotation.rental.selected_border', return_value=border
        ):
            try:
                outcome = deploy_rental(task, 1)
            except GamePageUnknownError:
                outcome = 'timeout'
        return outcome, task, state

    def test_slow_close_waits_without_reclicking_deploy(self):
        outcome, task, state = self.run_sequence([(True, False)] * 4 + [(False, True)] * 2)
        self.assertEqual('ready', outcome)
        self.assertEqual(6, state['index'])
        self.assertEqual(1, task.appear_then_click.call_count)
        self.assertEqual(2, task.click.call_count)

    def test_transient_boss_match_requires_two_consecutive_frames(self):
        outcome, task, state = self.run_sequence([(False, True), (False, False), (False, True), (False, True)])
        self.assertEqual('ready', outcome)
        self.assertEqual(4, state['index'])
        self.assertEqual(1, task.appear_then_click.call_count)

    def test_still_open_or_unrecognized_page_times_out_at_five_seconds(self):
        for frame in ((True, False), (False, False)):
            with self.subTest(frame=frame):
                outcome, task, state = self.run_sequence([frame])
                self.assertEqual('timeout', outcome)
                # 前两次0.5秒等待用于原选队，出战后的等待只增加5秒。
                self.assertAlmostEqual(6, state['time'])
                self.assertEqual(1, task.appear_then_click.call_count)

    def test_failure_before_deploy_keeps_original_unknown_result(self):
        outcome, task, state = self.run_sequence([(False, True)], border=False)
        self.assertEqual('unknown', outcome)
        self.assertFalse(state['deployed'])
        task.appear_then_click.assert_not_called()


class RentalRecoveryBudgetTest(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = RotationProgress(Path(temporary.name), 'oas3')
        self.account = SimpleNamespace(account_id='A11', instance='oas3', position=11, enabled=True,
                                       login_account='test', server='server', character='role')
        self.identity = account_identity('oas3', 11, 'test', 'server', 'role')
        for action in ('begin', 'entered', 'finished'):
            self.store.update('A11', self.identity, action, target=2)
        self.switcher = Mock()
        self.switcher.ensure_account.return_value.success = True
        self.recover = Mock(return_value=True)

    def driver(self, *, failure=None):
        driver = Mock()
        driver.rotation_started = 42
        driver.deploy_rental.return_value = 'ready'
        driver.deploy_rental.side_effect = failure
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.return_value = 'four_ready'
        driver.challenge.side_effect = lambda entered: entered() or True
        return driver

    def run_drivers(self, drivers):
        factory = Mock(side_effect=drivers)
        results = run_rotation([self.account], self.switcher, self.store, factory, rental_team=1,
                               battle_limit=2, recover_account=self.recover)
        return results, factory

    def test_post_deploy_timeout_recovers_same_account_without_duplicate_count(self):
        first = self.driver(failure=GamePageUnknownError('租借出战确认超时'))
        retry = self.driver()
        results, factory = self.run_drivers([first, retry])
        self.assertTrue(results[0].completed)
        self.assertEqual(2, results[0].entered)
        self.recover.assert_called_once_with(self.account)
        first.challenge.assert_not_called()
        retry.challenge.assert_called_once()
        self.assertEqual(42, retry.rotation_started)

    def test_rental_and_other_unknown_errors_share_three_restart_budget(self):
        drivers = [self.driver(failure=GamePageUnknownError(message)) for message in
                   ('队列页面未知', '租借出战确认超时', '租借出战确认超时', '租借出战确认超时')]
        results, factory = self.run_drivers(drivers)
        self.assertFalse(results[0].completed)
        self.assertEqual(1, results[0].entered)
        self.assertEqual(3, self.recover.call_count)
        self.assertEqual(4, factory.call_count)
        self.assertTrue(all(call.args[0] is self.account for call in self.recover.call_args_list))

    def test_failed_account_recovery_stops_immediately(self):
        self.recover.return_value = False
        results, factory = self.run_drivers([self.driver(failure=GamePageUnknownError('租借出战确认超时'))])
        self.assertFalse(results[0].completed)
        self.assertEqual(1, results[0].entered)
        self.assertEqual(1, factory.call_count)
        self.recover.assert_called_once()

    def test_unconfirmed_battle_does_not_enter_rental_or_restart(self):
        self.store.update('A11', self.identity, 'begin', target=2)
        results, factory = self.run_drivers([])
        self.assertFalse(results[0].completed)
        factory.assert_not_called()
        self.recover.assert_not_called()
