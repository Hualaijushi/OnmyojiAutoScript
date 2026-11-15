"""超鬼王登录超时仅恢复一次，正常及其他任务路径保持原实现。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GameStuckError, RequestHumanTakeover
from module.multi_account.account_switcher import AccountSwitcher
from tasks.Component.Login.service import LoginService, FAST_LOGIN_ENTER_GAME_INTERVAL, FAST_LOGIN_MAX_ENTER_GAME_ATTEMPTS
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.GameUi.page import page_login
from tasks.MetaDemonRotation.login_recovery import RotationRetryLoginService, RotationRetrySwitchAccount


TIMEOUT = 'fast login enter game timeout after repeated attempts'


class RotationLoginRetryTest(TestCase):
    def handler(self):
        handler = object.__new__(RotationRetryLoginService)
        handler.config = SimpleNamespace(config_name='oas4')
        handler.device = Mock()
        handler.fast_login = True
        handler.skip_specific_server = True
        handler.character = 'server'
        handler._rotation_target = SimpleNamespace(account='target', svr='server', character='role')
        handler._enter_game_attempts = 3
        handler._login_method_page_handled = True
        return handler

    def test_normal_success_does_not_restart_or_create_retry(self):
        handler = self.handler()
        with patch.object(LoginService, '_app_handle_login', return_value=True), patch(
            'tasks.MetaDemonRotation.login_recovery.LoginService'
        ) as retry:
            self.assertTrue(handler.app_handle_login())
        retry.assert_not_called()
        handler.device.app_stop.assert_not_called()
        handler.device.app_start.assert_not_called()

    def test_timeout_restarts_and_retries_same_target_then_verifies_role(self):
        handler = self.handler()
        events = []
        handler.device.app_stop.side_effect = lambda: events.append('stop')
        handler.device.app_start.side_effect = lambda: events.append('start')
        with patch.object(LoginService, '_app_handle_login', side_effect=GameStuckError(TIMEOUT)), patch(
            'tasks.MetaDemonRotation.login_recovery.LoginService'
        ) as make_retry, patch('tasks.MetaDemonRotation.login_recovery._LoginRecoveryVerifier') as make_verifier:
            make_retry.return_value._app_handle_login.side_effect = lambda: events.append('login')
            make_verifier.return_value._verify_courtyard_character.side_effect = lambda account: events.append('verify') or True
            self.assertTrue(handler.app_handle_login())
            self.assertIs(handler._rotation_target, make_retry.call_args.kwargs['expected_account'])
            self.assertTrue(make_retry.call_args.kwargs['fast_login'])
            self.assertTrue(make_retry.call_args.kwargs['skip_specific_server'])
            make_retry.return_value.set_specific_usr.assert_called_once_with('server')
            make_retry.return_value._app_handle_login.assert_called_once_with()
            make_retry.return_value.app_handle_login.assert_not_called()
            expected = make_verifier.return_value._verify_courtyard_character.call_args.args[0]
            self.assertEqual(('oas4', 'role'), (expected.instance, expected.character))
        self.assertEqual(['stop', 'start', 'login', 'verify'], events)
        self.assertEqual(8.0, FAST_LOGIN_ENTER_GAME_INTERVAL)
        self.assertEqual(3, FAST_LOGIN_MAX_ENTER_GAME_ATTEMPTS)

    def test_retry_failure_or_wrong_role_pauses_without_second_restart(self):
        for failure in (GameStuckError(TIMEOUT), RequestHumanTakeover('unknown account'), RuntimeError('rpc'), None):
            with self.subTest(failure=failure):
                handler = self.handler()
                with patch.object(LoginService, '_app_handle_login', side_effect=GameStuckError(TIMEOUT)), patch(
                    'tasks.MetaDemonRotation.login_recovery.LoginService'
                ) as retry, patch('tasks.MetaDemonRotation.login_recovery._LoginRecoveryVerifier') as verifier:
                    retry.return_value._app_handle_login.side_effect = failure
                    verifier.return_value._verify_courtyard_character.return_value = False
                    with self.assertRaises(RequestHumanTakeover):
                        handler.app_handle_login()
                    handler.device.app_stop.assert_called_once_with()
                    handler.device.app_start.assert_called_once_with()
                    retry.assert_called_once()

    def test_initial_identity_rejection_never_restarts(self):
        handler = self.handler()
        with patch.object(LoginService, '_app_handle_login', side_effect=RequestHumanTakeover('wrong account')):
            with self.assertRaises(RequestHumanTakeover):
                handler.app_handle_login()
        handler.device.app_stop.assert_not_called()

    def test_missing_target_cannot_restart_or_continue(self):
        handler = self.handler()
        handler._rotation_target = None
        with patch.object(LoginService, '_app_handle_login', side_effect=GameStuckError(TIMEOUT)):
            with self.assertRaises(RequestHumanTakeover):
                handler.app_handle_login()
        handler.device.app_stop.assert_not_called()

    def test_restart_failure_cannot_reach_login(self):
        handler = self.handler()
        handler.device.app_start.side_effect = RuntimeError('start failed')
        with patch.object(LoginService, '_app_handle_login', side_effect=GameStuckError(TIMEOUT)), patch(
            'tasks.MetaDemonRotation.login_recovery.LoginService'
        ) as retry:
            with self.assertRaises(RequestHumanTakeover):
                handler.app_handle_login()
        retry.assert_not_called()
        handler.device.app_start.assert_called_once_with()

    def test_other_stuck_reason_keeps_existing_handling(self):
        handler = self.handler()
        with patch.object(LoginService, '_app_handle_login', side_effect=GameStuckError('create account')), patch(
            'tasks.MetaDemonRotation.login_recovery.LoginService'
        ) as retry:
            with self.assertRaises(RequestHumanTakeover):
                handler.app_handle_login()
        retry.assert_not_called()
        handler.device.app_start.assert_called_once_with()

    def test_retry_takeover_bypasses_outer_switch_restarts(self):
        account = SimpleNamespace(enabled=True, instance='oas4', account_id='B15', to_account_info=Mock())
        factory = Mock()
        factory.return_value.switchAccount.side_effect = RequestHumanTakeover('recovery failed')
        switcher = AccountSwitcher(Mock(), Mock(), fast=True, switch_factory=factory)
        with self.assertRaises(RequestHumanTakeover):
            switcher.ensure_account(account)
        factory.assert_called_once()


class SwitchHandlerSelectionTest(TestCase):
    def task(self, kind):
        task = object.__new__(kind)
        task.config = Mock()
        task.device = Mock()
        task.to_account_info = SimpleNamespace(svr='server')
        task.redact_account_logs = True
        task.fast = True
        task.on_ocr_complete = None
        task.screenshot = Mock()
        task.get_current_page = Mock(return_value=page_login)
        task.login_fast = Mock(return_value=True)
        return task

    def test_default_switch_uses_original_service(self):
        task = self.task(SwitchAccount)
        with patch('tasks.Component.SwitchAccount.switch_account.LoginService') as original:
            self.assertTrue(task.switchAccount())
        original.assert_called_once()

    def test_only_rotation_switch_selects_retry_service(self):
        task = self.task(RotationRetrySwitchAccount)
        with patch.object(RotationRetrySwitchAccount, 'login_service_type') as retry, patch(
            'tasks.Component.SwitchAccount.switch_account.LoginService'
        ) as original:
            self.assertTrue(task.switchAccount())
        retry.assert_called_once()
        original.assert_not_called()
