"""跨天进度及卡死恢复的边界检查。"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.MetaDemonRotation.engine import AccountResult
from tasks.MetaDemonRotation.progress import RotationProgress, RotationProgressError, account_identity
from tasks.MetaDemonRotation.rotation import run_rotation
from tasks.MetaDemonRotation.script_task import ScriptTask, _RecoveryVerifier
from module.config.config_model import ConfigModel


class ContinuationTest(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.account = SimpleNamespace(instance='oas4', position=11, login_account='example', server='s',
                                       character='c', account_id='B11', enabled=True)
        self.identity = account_identity('oas4', 11, 'example', 's', 'c')

    def write_legacy(self, day, count, *, identity=None, phase='idle'):
        item = {'identity': identity or self.identity, 'entered': count, 'phase': phase,
                'status': 'pending', 'reason': ''}
        path = self.root / f'.meta_demon_rotation_oas4_{day}.json'
        path.write_text(json.dumps({'date': day, 'instance': 'oas4', 'accounts': {'B11': item}}), encoding='utf-8')
        return path

    def test_reset_setting_is_exposed_and_recovery_has_navigation(self):
        args = ConfigModel().script_task('MetaDemonRotation')['rotation_settings']
        field = next(item for item in args if item['name'] == 'reset_generation')
        self.assertEqual('进度重置批次', field['title'])
        self.assertEqual(0, field['value'])
        self.assertTrue(callable(_RecoveryVerifier.goto_page))
        self.assertTrue(callable(_RecoveryVerifier.get_current_page))

    def test_recovery_restarts_and_forces_fresh_verified_account_selection(self):
        task = object.__new__(ScriptTask)
        task.config, task.device = Mock(), Mock()
        with patch('tasks.MetaDemonRotation.script_task.RestartTask') as restart, patch(
            'tasks.MetaDemonRotation.script_task._RecoveryVerifier') as verifier, patch(
            'tasks.MetaDemonRotation.script_task.AccountSwitcher') as switcher:
            switcher.return_value.ensure_account.return_value.success = True
            self.assertTrue(task._recover_account(self.account))
        self.assertIs(self.account, restart.return_value.expected_account)
        restart.return_value.app_restart.assert_called_once()
        switcher.return_value.ensure_account.assert_called_once_with(self.account)
        self.assertEqual(1, switcher.call_args.kwargs['max_attempts'])
        self.assertEqual(verifier.return_value._verify_courtyard_character,
                         switcher.call_args.kwargs['home_verifier'])

    def test_latest_matching_history_continues_across_dates_without_adding(self):
        earlier = self.write_legacy('2026-11-12', 9)
        latest = self.write_legacy('2026-11-13', 4)
        self.write_legacy('2026-11-14', 18, identity='different')
        old = [earlier.read_bytes(), latest.read_bytes()]
        store = RotationProgress(self.root, 'oas4', day='2026-11-14')
        self.assertEqual(4, store.update('B11', self.identity, 'read', target=20)['entered'])
        store.update('B11', self.identity, 'begin', target=20)
        store.update('B11', self.identity, 'entered', target=20)
        store.update('B11', self.identity, 'finished', target=20)
        tomorrow = RotationProgress(self.root, 'oas4', day='2026-11-15')
        self.assertEqual(5, tomorrow.update('B11', self.identity, 'read', target=20)['entered'])
        self.assertEqual(old, [earlier.read_bytes(), latest.read_bytes()])

    def test_reset_backs_up_and_never_reimports_old_progress(self):
        self.write_legacy('2026-11-14', 4)
        first = RotationProgress(self.root, 'oas4')
        self.assertEqual(4, first.update('B11', self.identity, 'read', target=20)['entered'])
        original = first.path.read_bytes()
        reset = RotationProgress(self.root, 'oas4', reset_generation=1)
        self.assertEqual(0, reset.update('B11', self.identity, 'read', target=20)['entered'])
        backups = list(self.root.glob('*.backup-*')) + list(self.root.glob('.*.backup-*'))
        self.assertTrue(any(p.read_bytes() == original for p in backups))
        with self.assertRaises(RotationProgressError):
            first.update('B11', self.identity, 'read', target=20)
        self.assertEqual(0, reset.update('B11', self.identity, 'read', target=20)['entered'])

    def test_unconfirmed_old_battle_remains_unconfirmed(self):
        self.write_legacy('2026-11-14', 4, phase='entered')
        state = RotationProgress(self.root, 'oas4').update('B11', self.identity, 'read', target=20)
        self.assertEqual(('entered', 4), (state['phase'], state['entered']))

    def test_stuck_when_idle_restarts_once_and_preserves_count(self):
        store = RotationProgress(self.root, 'oas4')
        switcher, recover = Mock(), Mock(return_value=True)
        switcher.ensure_account.return_value.success = True
        driver = Mock()
        with patch('tasks.MetaDemonRotation.rotation.run_account',
                   side_effect=[GameStuckError('stuck'), AccountResult(True, 4, 'ok')]) as run:
            result = run_rotation([self.account], switcher, store, lambda _: driver,
                                  rental_team=1, battle_limit=20, recover_account=recover)
        recover.assert_called_once_with(self.account)
        self.assertEqual(2, run.call_count)
        self.assertTrue(result[0].completed)

    def test_stuck_during_unconfirmed_battle_never_restarts(self):
        store = RotationProgress(self.root, 'oas4')
        switcher, recover = Mock(), Mock(return_value=True)
        switcher.ensure_account.return_value.success = True
        def stuck(*args, **kwargs):
            store.update('B11', self.identity, 'begin', target=20)
            raise GameStuckError('stuck')
        with patch('tasks.MetaDemonRotation.rotation.run_account', side_effect=stuck):
            result = run_rotation([self.account], switcher, store, lambda _: Mock(),
                                  rental_team=1, battle_limit=20, recover_account=recover)
        self.assertFalse(result[0].completed)
        recover.assert_not_called()
        self.assertEqual('pending', store.update('B11', self.identity, 'read', target=20)['phase'])

    def test_failed_verification_or_second_stall_never_retries_again(self):
        for verified in (False, True):
            with self.subTest(verified=verified), tempfile.TemporaryDirectory() as folder:
                store = RotationProgress(Path(folder), 'oas4')
                switcher, recover = Mock(), Mock(return_value=verified)
                switcher.ensure_account.return_value.success = True
                with patch('tasks.MetaDemonRotation.rotation.run_account', side_effect=GameStuckError('stuck')) as run:
                    result = run_rotation([self.account], switcher, store, lambda _: Mock(),
                                          rental_team=1, battle_limit=20, recover_account=recover)
                self.assertFalse(result[0].completed)
                recover.assert_called_once()
                self.assertEqual(2 if verified else 1, run.call_count)
