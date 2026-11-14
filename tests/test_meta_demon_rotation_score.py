"""积分领取流程与账号进度边界。"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.MetaDemonRotation.engine import run_account
from tasks.MetaDemonRotation.progress import RotationProgress, account_identity
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

    @staticmethod
    def account(number):
        return SimpleNamespace(account_id=f'A{number:02}', instance='oas3', position=number,
                               login_account=f'user{number}', server='server',
                               character=f'role{number}', enabled=True)

    @staticmethod
    def seed_old_score_pending(progress, account, *, entered, phase='idle'):
        identity = account_identity(account.instance, account.position, account.login_account,
                                    account.server, account.character)
        progress.update(account.account_id, identity, 'read', target=1)
        state = json.loads(progress.path.read_text(encoding='utf-8'))
        state['accounts'][account.account_id].update(entered=entered, phase=phase, target=1,
                                                      status='incomplete', score_pending=True,
                                                      reason='积分领取未确认')
        progress.path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        return identity

    def test_battle_target_completes_without_claim(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            driver = Mock()
            driver.deploy_rental.return_value = driver.fatigue_status.return_value = 'ready'
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: (entered(), True)[1]
            result = run_account(driver, progress, account_id='A01', identity='x', rental_team=1, battle_limit=1)
            self.assertEqual((True, 1, '已达目标'), (result.completed, result.entered, result.reason))
            state = progress.update('A01', 'x', 'read', target=1)
            self.assertEqual(('idle', 'completed'), (state['phase'], state['status']))
            self.assertNotIn('score_pending', state)
            driver.claim_score.assert_not_called()

    def test_old_score_pending_reached_target_skips_and_selects_next(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            first, second = self.account(1), self.account(2)
            identity = self.seed_old_score_pending(progress, first, entered=1)
            switcher, driver = Mock(), Mock()
            switcher.ensure_account.return_value.success = True
            driver.deploy_rental.return_value = 'unavailable'
            result = run_rotation([first, second], switcher, progress, lambda _: driver,
                                  rental_team=1, battle_limit=1)
            self.assertEqual([(True, 1), (False, 0)], [(x.completed, x.entered) for x in result])
            switcher.ensure_account.assert_called_once_with(second)
            self.assertEqual(1, progress.update('A01', identity, 'read', target=1)['entered'])
            driver.claim_score.assert_not_called()

    def test_old_score_pending_below_new_target_continues(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            account = self.account(1)
            identity = self.seed_old_score_pending(progress, account, entered=1)
            driver = Mock()
            driver.deploy_rental.return_value = driver.fatigue_status.return_value = 'ready'
            driver.prepare_current_or_four_star.return_value = 'four_ready'
            driver.challenge.side_effect = lambda entered: (entered(), True)[1]
            result = run_account(driver, progress, account_id='A01', identity=identity,
                                 rental_team=1, battle_limit=2)
            self.assertTrue(result.completed)
            self.assertEqual(2, result.entered)
            driver.claim_score.assert_not_called()

    def test_old_score_pending_does_not_bypass_inflight_guard(self):
        with tempfile.TemporaryDirectory() as root:
            progress = RotationProgress(Path(root), 'oas3')
            account = self.account(1)
            self.seed_old_score_pending(progress, account, entered=1, phase='entered')
            switcher = Mock()
            result = run_rotation([account], switcher, progress, lambda _: Mock(),
                                  rental_team=1, battle_limit=1)
            self.assertFalse(result[0].completed)
            self.assertIn('战斗状态未确认', result[0].reason)
            switcher.ensure_account.assert_not_called()
