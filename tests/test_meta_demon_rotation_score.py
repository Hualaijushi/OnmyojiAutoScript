"""积分领取流程与账号进度边界。"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.MetaDemonRotation.engine import run_account
from tasks.MetaDemonRotation.progress import RotationProgress
from tasks.MetaDemonRotation.score_claim import SCORE_EMPTY, claim_score
from tasks.MetaDemonRotation.rotation import run_rotation


class FakeClock:
    def __init__(self):
        self.value = 0
        self.waits = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.value += seconds


class ScoreClaimTest(TestCase):
    def task(self, after_click):
        task = Mock()
        task.I_CHECK_BOSS_PAGE = object()
        task.I_MD_SCORE_BOX = object()
        task.I_UI_REWARD = object()
        task.I_UI_BACK_YELLOW = object()
        state = {'page': 'boss'}

        def appear(rule):
            return ((rule is task.I_CHECK_BOSS_PAGE and state['page'] == 'boss')
                    or (rule is task.I_UI_REWARD and state['page'] == 'reward')
                    or (rule is SCORE_EMPTY and state['page'] == 'empty')
                    or (rule is task.I_UI_BACK_YELLOW and state['page'] == 'empty'))

        def appear_click(rule, **kwargs):
            if rule is task.I_MD_SCORE_BOX and state['page'] == 'boss':
                state['page'] = after_click
                return True
            if rule is task.I_UI_BACK_YELLOW and state['page'] == 'empty':
                state['page'] = 'boss'
                return True
            return False

        def click(*args, **kwargs):
            if state['page'] == 'reward':
                state['page'] = 'empty'

        task.appear.side_effect = appear
        task.appear_then_click.side_effect = appear_click
        task.click.side_effect = click
        return task

    def test_reward_is_closed_and_returns_to_boss(self):
        task = self.task('reward')
        clock = FakeClock()
        with patch('tasks.MetaDemonRotation.score_claim.time', clock):
            self.assertEqual('claimed', claim_score(task))
        self.assertEqual(5, clock.waits[0])
        task.click.assert_called_once()
        self.assertEqual(2, task.appear_then_click.call_count)

    def test_empty_page_waits_then_returns_without_claiming(self):
        task = self.task('empty')
        clock = FakeClock()
        with patch('tasks.MetaDemonRotation.score_claim.time', clock):
            self.assertEqual('empty', claim_score(task))
        self.assertGreaterEqual(clock.value, 8)
        task.click.assert_not_called()

    def test_unknown_page_stops_without_back_click(self):
        task = self.task('unknown')
        with patch('tasks.MetaDemonRotation.score_claim.time', FakeClock()):
            self.assertEqual('unknown', claim_score(task))
        task.click.assert_not_called()
        self.assertEqual(1, task.appear_then_click.call_count)

    def test_reached_target_records_result_without_repeat_battle(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3', day='2026-11-13')
            driver = Mock()
            driver.deploy_rental.return_value = 'ready'
            driver.fatigue_status.return_value = 'ready'
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: (entered(), True)[1]
            driver.claim_score.return_value = 'empty'
            result = run_account(driver, progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertTrue(result.completed)
            self.assertEqual('已达目标，无可领取积分', result.reason)
            self.assertEqual('无可领取积分', progress.update('A01', 'x', 'read', target=1)['reason'])
            result = run_account(driver, progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertTrue(result.completed)
            driver.claim_score.assert_called_once()

    def test_unknown_claim_preserves_count_and_stops(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3', day='2026-11-13')
            driver = Mock()
            driver.deploy_rental.return_value = 'ready'
            driver.fatigue_status.return_value = 'ready'
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: (entered(), True)[1]
            driver.claim_score.return_value = 'unknown'
            result = run_account(driver, progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertFalse(result.completed)
            self.assertEqual((1, '积分领取未确认'), (result.entered, result.reason))
            self.assertEqual(1, progress.update('A01', 'x', 'read', target=1)['entered'])
            again = run_account(driver, RotationProgress(Path(root), 'oas3'),
                                account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertFalse(again.completed)
            self.assertEqual('积分领取未确认，需人工核实', again.reason)
            driver.claim_score.assert_called_once()

    def test_crash_before_claim_is_persistently_pending_even_with_new_target(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            for action in ('begin', 'entered', 'finished'):
                progress.update('A01', 'x', action, target=1)
            driver = Mock()
            resumed = RotationProgress(Path(root), 'oas3')
            result = run_account(driver, resumed, account_id='A01', identity='x', rental_team=1, battle_limit=4)
            self.assertEqual((False, 1, '积分领取未确认，需人工核实'),
                             (result.completed, result.entered, result.reason))
            driver.deploy_rental.assert_not_called()
            driver.claim_score.assert_not_called()

    def test_claim_exception_never_skips_on_restart(self):
        account = SimpleNamespace(account_id='A01', instance='oas3', position=1, login_account='user',
                                  server='server', character='role', enabled=True)
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            driver = Mock()
            driver.deploy_rental.return_value = driver.fatigue_status.return_value = 'ready'
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: (entered(), True)[1]
            driver.claim_score.side_effect = RuntimeError('failed')
            switcher = Mock()
            switcher.ensure_account.return_value.success = True
            first = run_rotation([account], switcher, progress, lambda _: driver, rental_team=1, battle_limit=1)
            second = run_rotation([account], switcher, RotationProgress(Path(root), 'oas3'),
                                  lambda _: driver, rental_team=1, battle_limit=1)
            self.assertFalse(first[0].completed)
            self.assertEqual('积分领取未确认，需人工核实', second[0].reason)
            switcher.ensure_account.assert_called_once()

    def test_historical_completed_account_does_not_claim(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            progress.update('A01', 'x', 'read', target=1)
            state = json.loads(progress.path.read_text(encoding='utf-8'))
            state['accounts']['A01'].update(entered=1, status='completed', target=1, reason='')
            progress.path.write_text(json.dumps(state), encoding='utf-8')
            driver = Mock()
            result = run_account(driver, progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertTrue(result.completed)
            driver.claim_score.assert_not_called()

    def test_old_unconfirmed_claim_stays_paused(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            progress.update('A01', 'x', 'read', target=1)
            state = json.loads(progress.path.read_text(encoding='utf-8'))
            state['accounts']['A01'].update(entered=1, status='incomplete', target=1,
                                            reason='积分领取未确认')
            progress.path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
            result = run_account(Mock(), progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertFalse(result.completed)
            self.assertEqual('积分领取未确认，需人工核实', result.reason)

    def test_unknown_claim_does_not_switch_to_next_account(self):
        def account(number):
            return SimpleNamespace(account_id=f'A{number:02}', instance='oas3', position=number,
                                   login_account=f'user{number}', server='server',
                                   character=f'role{number}', enabled=True)
        first, second = account(1), account(2)
        switcher = Mock()
        switcher.ensure_account.return_value.success = True
        driver = Mock()
        driver.deploy_rental.return_value = 'ready'
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.return_value = 'four_ready'
        driver.challenge.side_effect = lambda entered: (entered(), True)[1]
        driver.claim_score.return_value = 'unknown'
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3', day='2026-11-13')
            result = run_rotation([first, second], switcher, progress, lambda _: driver,
                                  rental_team=1, battle_limit=1)
        self.assertEqual(1, len(result))
        self.assertEqual('积分领取未确认', result[0].reason)
        switcher.ensure_account.assert_called_once_with(first)
