"""轮换重启时的保存账号弹窗：目标核对、提交与恢复边界。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from lxml import etree

from module.exception import RequestHumanTakeover
from module.multi_account.account_switcher import AccountSwitcher, SwitchErrorCode, SwitchResult
from tasks.AccountRotation.script_task import RotationAccountSwitcher
from tasks.Component.Login.saved_account_popup import SavedAccountPopup, _CheckedAccountUi
from tasks.Component.Login.service import LoginService
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets as A
from tasks.Component.SwitchAccount.netease_account_ui import AccountUiUnavailable, NeteaseAccountUi
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.GameUi.page import page_login
from tasks.MultiAccountEvo.recovery import GroupGameRestart
from tasks.Restart.script_task import ScriptTask as RestartTask


class SavedAccountPopupTest(TestCase):
    def setUp(self):
        self.task = Mock()
        self.target = SimpleNamespace(account='target@example.test', svr='server', apple_or_android=True)
        self.visible = {A.I_SA_NETEASE_GAME_LOGO, A.I_SA_ACCOUNT_LOGIN_BTN}
        self.task.appear.side_effect = lambda rule: rule in self.visible
        self.ui = Mock()
        self.ui.account_matches.side_effect = lambda actual, expected: actual == expected
        self.ui.current_account.return_value = self.target.account
        self.ui.click_login.return_value = True

    def test_no_popup_leaves_normal_login_untouched(self):
        self.visible.clear()
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi') as make_ui:
            self.assertFalse(SavedAccountPopup(self.task, self.target).step())
        make_ui.assert_not_called()

    def test_partial_image_match_blocks_known_account_popup(self):
        self.visible.remove(A.I_SA_ACCOUNT_LOGIN_BTN)
        ui = Mock()
        ui.ACCOUNT_ITEM_ID = 'item'
        ui.ACCOUNT_LIST_ID = 'list'
        ui.ACCOUNT_TEXT_IDS = ('account',)
        ui._nodes.side_effect = lambda root, name: [object()] if name == 'account' else []
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=ui):
            with self.assertRaises(RequestHumanTakeover):
                SavedAccountPopup(self.task, self.target).step()
        ui.click_login.assert_not_called()

    def test_partial_image_other_page_keeps_normal_flow(self):
        self.visible.remove(A.I_SA_ACCOUNT_LOGIN_BTN)
        ui = Mock()
        ui.ACCOUNT_TEXT_IDS = ('account',)
        ui._nodes.return_value = []
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=ui):
            self.assertFalse(SavedAccountPopup(self.task, self.target).step())

    def test_generic_restart_guards_unknown_target_only_for_rotation_tasks(self):
        task = object.__new__(RestartTask)
        task.config = Mock()
        task.config.model.running_task = ''
        for name in ('AccountRotation', 'MultiAccountEvo', 'MetaDemonRotation'):
            task.config.pending_task = [SimpleNamespace(command=name)]
            self.assertTrue(task._rotation_recovery_pending())
        task.config.pending_task = [SimpleNamespace(command='EvoZone')]
        self.assertFalse(task._rotation_recovery_pending())
        task.config.model.running_task = 'AccountRotation'
        self.assertTrue(task._rotation_recovery_pending())

    def test_matching_account_submits_once_and_waits_without_reclick(self):
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=self.ui), patch(
            'tasks.Component.Login.saved_account_popup.time.monotonic', return_value=100
        ), patch('tasks.Component.Login.saved_account_popup.time.sleep'):
            handler = SavedAccountPopup(self.task, self.target)
            self.assertTrue(handler.step())
            self.assertTrue(handler.step())
        self.ui.select_account.assert_not_called()
        self.ui.click_login.assert_called_once_with(expected_account=self.target.account)
        self.task.click.assert_not_called()

    def test_different_account_selects_target_before_submit(self):
        self.ui.current_account.return_value = 'another@example.test'
        self.ui.select_account.return_value = True
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=self.ui):
            self.assertTrue(SavedAccountPopup(self.task, self.target).step())
        self.ui.select_account.assert_called_once_with(self.target.account)
        self.ui.click_login.assert_called_once_with(expected_account=self.target.account)

    def test_unconfirmed_or_unreadable_account_never_submits(self):
        for mode in ('missing', 'changed', 'unreadable'):
            with self.subTest(mode=mode):
                ui = Mock()
                ui.account_matches.return_value = False
                ui.current_account.return_value = 'different@example.test'
                ui.select_account.return_value = mode == 'changed'
                ui.click_login.return_value = False
                if mode == 'unreadable':
                    ui.current_account.side_effect = AccountUiUnavailable('sensitive internal detail')
                with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=ui):
                    with self.assertRaises(RequestHumanTakeover) as caught:
                        SavedAccountPopup(self.task, self.target).step()
                self.assertNotIn('sensitive', str(caught.exception))
                if mode != 'changed':
                    ui.click_login.assert_not_called()

    def test_unknown_target_stops_before_native_login(self):
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi') as make_ui:
            with self.assertRaises(RequestHumanTakeover):
                SavedAccountPopup(self.task, SimpleNamespace()).step()
        make_ui.assert_not_called()

    def test_popup_remains_after_submit_stops_without_second_click(self):
        with patch('tasks.Component.Login.saved_account_popup._CheckedAccountUi', return_value=self.ui), patch(
            'tasks.Component.Login.saved_account_popup.time.monotonic', side_effect=[100, 121]
        ):
            handler = SavedAccountPopup(self.task, self.target)
            self.assertTrue(handler.step())
            with self.assertRaises(RequestHumanTakeover):
                handler.step()
        self.ui.click_login.assert_called_once()

    def test_platform_after_popup_uses_target_platform(self):
        handler = SavedAccountPopup(self.task, self.target)
        handler.submitted_at = 100
        self.visible = {A.I_SA_LOGIN_FORM_APPLE}
        delegate = Mock()
        delegate._select_platform_and_confirm.return_value = True
        with patch('tasks.Component.Login.saved_account_popup._PlatformDelegate', return_value=delegate), patch(
            'tasks.Component.Login.saved_account_popup.time.monotonic', return_value=101
        ):
            self.assertTrue(handler.step())
        delegate._select_platform_and_confirm.assert_called_once_with(True)

    def test_group_guard_runs_around_native_dump_and_can_abort(self):
        ui = _CheckedAccountUi(Mock(), Mock(side_effect=RuntimeError('group stopped')))
        with self.assertRaisesRegex(RuntimeError, 'group stopped'):
            ui.dump()
        ui.device.u2.dump_hierarchy.assert_not_called()

    def test_login_button_rechecks_account_in_same_snapshot(self):
        root = etree.fromstring(b'''
            <hierarchy><node resource-id="pkg:id/netease_mpay__login_username" text="target@example.test"/>
            <node resource-id="pkg:id/netease_mpay__login" class="android.widget.Button"
                  clickable="true" bounds="[400,400][900,480]"/></hierarchy>''')
        device = Mock()
        ui = NeteaseAccountUi(device)
        ui.dump = Mock(return_value=root)
        self.assertFalse(ui.click_login(expected_account='other@example.test'))
        device.click.assert_not_called()
        self.assertTrue(ui.click_login(expected_account='target@example.test'))
        device.click.assert_called_once()

    def test_login_loop_handles_popup_before_any_other_click(self):
        task = Mock()
        task._saved_account_popup.step.side_effect = [True, False]
        task.appear_then_click.return_value = False
        task.appear.return_value = True
        self.assertTrue(LoginService._app_handle_login(task))
        self.assertEqual(2, task.screenshot.call_count)
        task._try_click_enter_game.assert_not_called()
        self.assertEqual(1, task.appear_then_click.call_count)

    def test_switch_account_passes_target_to_login(self):
        task = Mock()
        task.redact_account_logs = True
        task.fast = True
        task.on_ocr_complete = None
        task.to_account_info = self.target
        task.get_current_page.return_value = page_login
        task.login_fast.return_value = True
        with patch('tasks.Component.SwitchAccount.switch_account.LoginService') as login:
            self.assertTrue(SwitchAccount.switchAccount(task))
        self.assertIs(self.target, login.call_args.kwargs['expected_account'])

    def test_rotation_restart_receives_same_account(self):
        task = object.__new__(RotationAccountSwitcher)
        task.config = Mock()
        task.device = Mock()
        target = SimpleNamespace(instance='oas3', account_id='A01')
        results = [SwitchResult(False, 'A01', error_code=SwitchErrorCode.UNKNOWN),
                   SwitchResult(True, 'A01')]
        with patch.object(AccountSwitcher, 'ensure_account', side_effect=results), patch(
            'tasks.AccountRotation.script_task.RestartTask'
        ) as restart:
            self.assertTrue(task.ensure_account(target).success)
        self.assertIs(target, restart.return_value.expected_account)
        restart.return_value.app_restart.assert_called_once()

    def test_group_restart_passes_target_and_control_guard(self):
        task = object.__new__(GroupGameRestart)
        task.config = Mock()
        task.device = Mock()
        task.expected_account = self.target
        task._recovery_check = Mock()
        login = SimpleNamespace(screenshot=Mock(), app_handle_login=Mock())
        with patch('tasks.MultiAccountEvo.recovery.LoginService', return_value=login) as make_login:
            task.app_start()
        self.assertIs(self.target, make_login.call_args.kwargs['expected_account'])
        self.assertIs(task._recovery_check, make_login.call_args.kwargs['account_guard'])
