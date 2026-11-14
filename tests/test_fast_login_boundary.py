"""快速切号从登录入口重试时的页面和账号边界。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.Component.SwitchAccount.login_account import LoginAccount
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets as A


class FastLoginBoundaryTest(TestCase):
    def task(self):
        task = Mock(spec=LoginAccount)
        task.account_logs_redacted = True
        for name in dir(A):
            if name.startswith(('I_', 'C_')):
                setattr(task, name, getattr(A, name))
        return task

    def test_login_entry_reopens_user_center_then_saved_accounts(self):
        task = self.task()
        state = {'page': 'entry'}
        def appear(rule):
            return ((state['page'] == 'entry' and rule is A.I_CHECK_LOGIN_FORM)
                    or (state['page'] == 'saved' and rule in (A.I_SA_NETEASE_GAME_LOGO, A.I_SA_ACCOUNT_LOGIN_BTN)))
        def click(rule, **kwargs):
            self.assertIs(A.C_SA_LOGIN_FORM_USER_CENTER, rule)
            state['page'] = 'center'
        def click_visible(rule, **kwargs):
            if state['page'] == 'center' and rule is A.I_SA_SWITCH_ACCOUNT_BTN:
                state['page'] = 'saved'
                return True
            return False
        task.appear.side_effect = appear
        task.click.side_effect = click
        task.appear_then_click.side_effect = click_visible
        with patch('tasks.Component.SwitchAccount.login_account.time.sleep'):
            self.assertTrue(LoginAccount._open_fast_saved_account_page(task))
        task.click.assert_called_once()
        task.wait_until_appear.assert_not_called()

    def test_unverified_channel_is_not_accepted_as_saved_account(self):
        task = self.task()
        task.appear.side_effect = lambda rule: rule is A.I_SA_LOGIN_FORM_APPLE
        self.assertFalse(LoginAccount._open_fast_saved_account_page(task))
        task.click.assert_not_called()

    def test_failed_page_recovery_never_waits_for_channel(self):
        task = self.task()
        task.appear.side_effect = lambda rule: rule is A.I_CHECK_LOGIN_FORM
        task._open_fast_saved_account_page.return_value = False
        self.assertFalse(LoginAccount.login_fast(task, SimpleNamespace(account='target', apple_or_android=True)))
        task.wait_until_appear.assert_not_called()
        task.submit_saved_account_login.assert_not_called()

    def test_unknown_page_times_out_without_clicking(self):
        task = self.task()
        task.appear.return_value = False
        task.appear_then_click.return_value = False
        with patch('tasks.Component.SwitchAccount.login_account.time.monotonic', side_effect=[0, 0, 16]), patch(
            'tasks.Component.SwitchAccount.login_account.time.sleep'):
            self.assertFalse(LoginAccount._open_fast_saved_account_page(task))
        task.click.assert_not_called()

    def test_unconfirmed_target_never_submits_or_waits_for_channel(self):
        task = self.task()
        task.appear.side_effect = lambda rule: rule in (A.I_CHECK_LOGIN_FORM, A.I_SA_NETEASE_GAME_LOGO)
        task._open_fast_saved_account_page.return_value = True
        task.selected_account_from_ui.return_value = 'target'
        task._netease_account_ui.return_value.account_matches.return_value = True
        task._account_selection_confirmed.return_value = False
        self.assertFalse(LoginAccount.login_fast(task, SimpleNamespace(account='target', apple_or_android=True)))
        task._netease_account_ui.return_value.click_login.assert_not_called()
        task.wait_until_appear.assert_not_called()

    def test_failed_or_verified_native_submission_controls_channel_wait(self):
        for submitted in (False, True):
            with self.subTest(submitted=submitted):
                task = self.task()
                task.appear.side_effect = lambda rule: rule in (A.I_CHECK_LOGIN_FORM, A.I_SA_NETEASE_GAME_LOGO)
                task._open_fast_saved_account_page.return_value = True
                task.selected_account_from_ui.return_value = 'target'
                task._netease_account_ui.return_value.account_matches.return_value = True
                task._account_selection_confirmed.return_value = True
                task._netease_account_ui.return_value.click_login.return_value = submitted
                task.wait_until_appear.return_value = True
                task._select_platform_and_confirm.return_value = True
                with patch('tasks.Component.SwitchAccount.login_account.time.sleep'):
                    self.assertEqual(submitted, LoginAccount.login_fast(task, SimpleNamespace(account='target', apple_or_android=True)))
                task._netease_account_ui.return_value.click_login.assert_called_once_with(expected_account='target')
                if submitted:
                    task.wait_until_appear.assert_called_once()
                else:
                    task.wait_until_appear.assert_not_called()
                task.submit_saved_account_login.assert_not_called()
