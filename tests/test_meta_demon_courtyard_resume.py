"""旧战斗标记仅在庭院角色核对成功后解除。"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import RequestHumanTakeover
from tasks.MetaDemonRotation.engine import AccountResult
from tasks.MetaDemonRotation.progress import RotationProgress, RotationProgressError, account_identity
from tasks.MetaDemonRotation.rotation import run_rotation
from tasks.MetaDemonRotation.script_task import ScriptTask, _CourtyardResumeVerifier
from tasks.GameUi.registry import PageRegistry
from tasks.GameUi.session import NavigatorSession
from tasks.MetaDemon import page as meta_pages


class CourtyardResumeTest(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = RotationProgress(Path(temporary.name), 'oas3')
        self.account = SimpleNamespace(instance='oas3', position=1, login_account='test',
                                       server='server', character='role', account_id='A01', enabled=True)
        self.identity = account_identity('oas3', 1, 'test', 'server', 'role')
        self.switcher = Mock()
        self.switcher.ensure_account.return_value.success = True
        self.factory = Mock()

    def state(self, action='read', **kwargs):
        return self.store.update('A01', self.identity, action, target=2, **kwargs)

    def inflight(self, entered=True):
        self.state('begin')
        if entered:
            self.state('entered')
        return self.state()

    def run_rotation(self, resume):
        return run_rotation([self.account], self.switcher, self.store, self.factory,
                            rental_team=1, battle_limit=2, resume_account=resume)

    def test_pending_and_entered_keep_count_and_resume_without_switch(self):
        for entered in (False, True):
            with self.subTest(entered=entered):
                before = self.inflight(entered)
                def execute(*args, **kwargs):
                    current = self.state()
                    self.assertEqual(('idle', before['entered']), (current['phase'], current['entered']))
                    return AccountResult(False, current['entered'], '疲劳不足')
                with patch('tasks.MetaDemonRotation.rotation.run_account', side_effect=execute):
                    result = self.run_rotation(Mock(return_value=True))
                self.assertEqual(before['entered'], result[0].entered)
                self.switcher.ensure_account.assert_not_called()

    def test_failed_or_missing_verification_preserves_exact_record(self):
        self.inflight()
        before = self.store.path.read_bytes()
        for resume in (None, Mock(return_value=False), Mock(side_effect=RuntimeError('failed'))):
            with self.subTest(resume=resume):
                result = self.run_rotation(resume)
                self.assertFalse(result[0].completed)
                self.assertEqual(before, self.store.path.read_bytes())
        self.factory.assert_not_called()
        self.switcher.ensure_account.assert_not_called()

    def test_state_change_during_verification_is_not_cleared(self):
        self.inflight(False)
        def verify(account):
            self.state('entered')
            return True
        result = self.run_rotation(verify)
        self.assertFalse(result[0].completed)
        self.assertEqual(('entered', 1), (self.state()['phase'], self.state()['entered']))
        self.factory.assert_not_called()

    def test_already_at_target_requires_verification_then_skips(self):
        self.inflight()
        self.state('finished')
        self.inflight()
        resume = Mock(return_value=True)
        result = self.run_rotation(resume)
        self.assertTrue(result[0].completed)
        self.assertEqual(('idle', 2, 'completed'),
                         (self.state()['phase'], self.state()['entered'], self.state()['status']))
        resume.assert_called_once_with(self.account)
        self.factory.assert_not_called()
        self.switcher.ensure_account.assert_not_called()

    def test_idle_path_keeps_normal_switch_and_does_not_verify(self):
        resume = Mock()
        with patch('tasks.MetaDemonRotation.rotation.run_account', return_value=AccountResult(False, 0, '疲劳不足')):
            self.run_rotation(resume)
        resume.assert_not_called()
        self.switcher.ensure_account.assert_called_once_with(self.account)

    def test_stale_or_wrong_identity_cannot_clear_marker(self):
        before = self.inflight()
        with self.assertRaises(RotationProgressError):
            self.store.update('A01', 'wrong', 'resume_from_courtyard', target=2, expected_state=before)
        with self.assertRaises(RotationProgressError):
            self.state('resume_from_courtyard', expected_state={})
        self.assertEqual(before, self.state())

    def test_failed_resume_does_not_visit_next_account(self):
        self.inflight()
        other = SimpleNamespace(**vars(self.account))
        other.account_id = 'A02'
        resume = Mock(return_value=False)
        results = run_rotation([self.account, other], self.switcher, self.store, self.factory,
                               rental_team=1, battle_limit=2, resume_account=resume)
        self.assertEqual(['A01'], [item.account_id for item in results])
        self.assertNotIn('A02', self.store._load()['accounts'])


class CourtyardNavigationTest(TestCase):
    def run_resume(self, verifier):
        task = SimpleNamespace(config=object(), device=object())
        with patch('tasks.MetaDemonRotation.script_task._CourtyardResumeVerifier', return_value=verifier), patch(
            'tasks.MetaDemonRotation.script_task.RestartTask'
        ) as restart, patch('tasks.MetaDemonRotation.script_task.AccountSwitcher') as switcher:
            result = ScriptTask._resume_account_from_courtyard(task, object())
            restart.assert_not_called()
            switcher.assert_not_called()
            return result

    def test_navigation_and_character_check_use_guarded_new_frames(self):
        class Verifier:
            def screenshot(self):
                return None
            def _verify_courtyard_character(self, account):
                self.screenshot()
                return True
        verifier = Verifier()
        with patch('tasks.MetaDemonRotation.script_task.ensure_nonbattle_frame') as guard:
            self.assertTrue(self.run_resume(verifier))
            self.assertEqual(2, guard.call_count)
        self.assertNotIn('screenshot', vars(verifier))

    def test_protected_battle_page_stops_before_navigation(self):
        verifier = Mock()
        with patch('tasks.MetaDemonRotation.script_task.ensure_nonbattle_frame',
                   side_effect=RequestHumanTakeover('battle')):
            with self.assertRaises(RequestHumanTakeover):
                self.run_resume(verifier)
        verifier._verify_courtyard_character.assert_not_called()

    def test_role_mismatch_returns_false(self):
        verifier = Mock()
        verifier._verify_courtyard_character.return_value = False
        with patch('tasks.MetaDemonRotation.script_task.ensure_nonbattle_frame'):
            self.assertFalse(self.run_resume(verifier))

    def test_resume_uses_existing_boss_to_courtyard_graph(self):
        PageRegistry.load_all_pages()
        verifier = _CourtyardResumeVerifier.__new__(_CourtyardResumeVerifier)
        verifier.navigator = NavigatorSession(task_category=verifier._infer_task_category())
        verifier.navigator.bootstrap(PageRegistry.all())
        boss = verifier.navigator.resolve_page(meta_pages.page_meta_demon_boss)
        main = verifier.navigator.resolve_page(meta_pages.page_main)
        self.assertIn(boss.category, verifier._navigation_detect_categories(main))
        path = verifier._build_path(boss, main)
        self.assertEqual(['page_meta_demon_boss->page_meta_demon', 'page_meta_demon->page_main'],
                         [step.key for step in path])

    def test_navigation_budget_expiry_stops_before_new_action(self):
        verifier = Mock()
        screenshot = verifier.screenshot
        with patch('tasks.MetaDemonRotation.script_task.time.monotonic', side_effect=[0, 61]), patch(
            'tasks.MetaDemonRotation.script_task.ensure_nonbattle_frame'
        ):
            with self.assertRaises(RequestHumanTakeover):
                self.run_resume(verifier)
        screenshot.assert_not_called()
        verifier._verify_courtyard_character.assert_not_called()
