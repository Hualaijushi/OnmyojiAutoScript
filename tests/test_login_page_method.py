"""登录方式页面必须由提示文字确认。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.Component.Login.service import LoginService, LOGIN_METHOD_PAGE_BACK
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets


class LoginMethodPageTest(TestCase):
    def setUp(self):
        self.task = Mock()
        self.task.device = Mock()
        self.task._login_method_page_handled = False
        self.task._enter_game_attempts = 1

    @staticmethod
    def boxes(*texts):
        return [SimpleNamespace(ocr_text=text) for text in texts]

    def test_normal_login_text_does_not_trigger_back_even_when_forced(self):
        with patch('tasks.Component.Login.service.O_LOGIN_AGREEMENT_WARNING.detect_and_ocr',
                   return_value=self.boxes('进入游戏')):
            self.assertFalse(LoginService._handle_login_method_page(self.task))
            self.assertFalse(LoginService._handle_login_method_page(self.task, force=True))
        self.task.click.assert_not_called()

    def test_empty_or_partial_warning_does_not_trigger_back(self):
        for boxes in ([], self.boxes('未勾选'), self.boxes('无法登录')):
            with self.subTest(boxes=boxes), patch(
                'tasks.Component.Login.service.O_LOGIN_AGREEMENT_WARNING.detect_and_ocr', return_value=boxes
            ):
                self.assertFalse(LoginService._handle_login_method_page(self.task, force=True))
        self.task.click.assert_not_called()

    def test_specific_other_login_warning_triggers_back(self):
        with patch('tasks.Component.Login.service.O_LOGIN_AGREEMENT_WARNING.detect_and_ocr',
                   return_value=self.boxes('未勾选同意', '将无法登录')):
            self.assertTrue(LoginService._handle_login_method_page(self.task))
        self.task.click.assert_called_once_with(LOGIN_METHOD_PAGE_BACK, interval=1.0)

    def test_normal_page_continues_original_enter_game(self):
        self.task.fast_login = True
        self.task.skip_specific_server = True
        self.task._enter_game_attempts = 0
        self.task._handle_login_method_page.side_effect = lambda force=False: LoginService._handle_login_method_page(
            self.task, force=force)
        self.task._enter_game_interval.return_value = 8.0
        self.task._max_enter_game_attempts.return_value = 3
        self.task.appear.return_value = False
        self.task.click.return_value = True
        with patch('tasks.Component.Login.service.O_LOGIN_AGREEMENT_WARNING.detect_and_ocr',
                   return_value=self.boxes('进入游戏')):
            self.assertTrue(LoginService._try_click_enter_game(self.task))
        self.task.click.assert_called_once_with(SwitchAccountAssets.C_SA_LOGIN_FORM_ENTER_GAME_BTN, interval=8.0)

    def test_provider_or_channel_page_never_clicks_underlying_enter_game(self):
        self.task.fast_login = True
        self.task._handle_login_method_page.return_value = False
        for active in (SwitchAccountAssets.I_SA_NETEASE_GAME_LOGO,
                       SwitchAccountAssets.I_SA_ACCOUNT_LOGIN_BTN,
                       SwitchAccountAssets.I_SA_LOGIN_FORM_APPLE,
                       SwitchAccountAssets.I_SA_LOGIN_FORM_ANDROID):
            with self.subTest(active=active):
                self.task.appear.side_effect = lambda rule: rule is active
                self.assertFalse(LoginService._try_click_enter_game(self.task))
        self.task.click.assert_not_called()

    def test_other_login_page_is_checked_without_background_login_marker(self):
        task = Mock()
        task._saved_account_popup = None
        task.appear_then_click.return_value = False
        frame = {'number': 0}
        task.screenshot.side_effect = lambda: frame.update(number=frame['number'] + 1)
        task.appear.side_effect = lambda rule, **kwargs: (
            rule is SwitchAccountAssets.I_SA_NETEASE_GAME_LOGO if frame['number'] == 1
            else rule is task.I_CHECK_CHESS
        )
        task._handle_login_method_page.return_value = True
        self.assertTrue(LoginService._app_handle_login(task))
        task._handle_login_method_page.assert_called_once_with()
        task._try_click_enter_game.assert_not_called()
