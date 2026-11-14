"""处理轮换登录中重新出现的网易保存账号弹窗。"""

import time

from module.exception import RequestHumanTakeover
from module.logger import logger
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.login_account import LoginAccount
from tasks.Component.SwitchAccount.netease_account_ui import AccountUiUnavailable, NeteaseAccountUi


class _CheckedAccountUi(NeteaseAccountUi):
    """复用原生账号选择，并在每次读写前后响应组队恢复检查。"""

    def __init__(self, device, check):
        super().__init__(device)
        self._check = check

    def dump(self):
        self._check()
        result = super().dump()
        self._check()
        return result

    def _click_bounds(self, bounds, name):
        self._check()
        result = super()._click_bounds(bounds, name)
        self._check()
        return result

    def _scroll(self, root, *, toward_start):
        self._check()
        result = super()._scroll(root, toward_start=toward_start)
        self._check()
        return result


class _PlatformDelegate(SwitchAccountAssets):
    """平台选择复用原切号逻辑，并沿用登录服务的截图和控制。"""

    account_logs_redacted = True
    select_login_platform_fast = LoginAccount.select_login_platform_fast
    _platform_page_closed = LoginAccount._platform_page_closed
    _select_platform_and_confirm = LoginAccount._select_platform_and_confirm

    def __init__(self, task):
        self.task = task

    def screenshot(self):
        return self.task.screenshot()

    def appear(self, *args, **kwargs):
        return self.task.appear(*args, **kwargs)

    def appear_then_click(self, *args, **kwargs):
        return self.task.appear_then_click(*args, **kwargs)


class SavedAccountPopup:
    """仅在正向识别弹窗且目标账号得到原生核验后提交。"""

    def __init__(self, task, expected_account, check=None):
        self.task = task
        self.expected_account = expected_account
        self.check = check or (lambda: None)
        self.submitted_at = None

    def _popup_visible(self):
        logo = self.task.appear(SwitchAccountAssets.I_SA_NETEASE_GAME_LOGO)
        button = self.task.appear(SwitchAccountAssets.I_SA_ACCOUNT_LOGIN_BTN)
        if logo and button:
            return True
        if not logo and not button:
            return False
        # 部分图像命中时检查原生控件，避免把其他网易登录页当作此弹窗。
        ui = _CheckedAccountUi(self.task.device, self.check)
        try:
            root = ui.dump()
            ids = (ui.ACCOUNT_ITEM_ID, ui.ACCOUNT_LIST_ID, *ui.ACCOUNT_TEXT_IDS)
            if any(ui._nodes(root, resource_id) for resource_id in ids):
                raise RequestHumanTakeover('保存账号弹窗图像识别不完整')
        except AccountUiUnavailable as exc:
            raise RequestHumanTakeover('登录页面图像识别不完整且原生界面不可用') from exc
        return False

    def step(self):
        self.check()
        if self.submitted_at is not None:
            elapsed = time.monotonic() - self.submitted_at
            if self.task.appear(SwitchAccountAssets.I_SA_LOGIN_FORM_APPLE):
                platform = _PlatformDelegate(self.task)
                if not platform._select_platform_and_confirm(
                        bool(getattr(self.expected_account, 'apple_or_android', True))):
                    raise RequestHumanTakeover('保存账号弹窗后的登录平台未确认')
                self.submitted_at = None
                return True
            if self._popup_visible():
                if elapsed >= 20:
                    raise RequestHumanTakeover('保存账号弹窗提交后未关闭')
                time.sleep(.3)
                return True
            if elapsed < 2:
                time.sleep(.3)
                return True
            self.submitted_at = None
            return False

        if not self._popup_visible():
            return False
        expected = (getattr(self.expected_account, 'login_account', None)
                    or getattr(self.expected_account, 'account', None))
        if not isinstance(expected, str) or not expected.strip():
            raise RequestHumanTakeover('保存账号弹窗缺少可核验的目标账号')
        ui = _CheckedAccountUi(self.task.device, self.check)
        try:
            current = ui.current_account()
            if not ui.account_matches(current, expected):
                if not ui.select_account(expected):
                    raise RequestHumanTakeover('保存账号弹窗无法选择目标账号')
            # 按钮点击使用同一原生快照再次核验账号，避免选择结果变化。
            if not ui.click_login(expected_account=expected):
                raise RequestHumanTakeover('保存账号弹窗目标账号或登录按钮未确认')
        except AccountUiUnavailable as exc:
            raise RequestHumanTakeover('保存账号弹窗原生账号信息不可用') from exc
        logger.info('已核验目标账号并提交保存账号登录')
        self.submitted_at = time.monotonic()
        return True
