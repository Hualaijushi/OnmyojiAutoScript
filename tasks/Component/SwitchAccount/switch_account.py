from adbutils import device
from typing import Callable

from module.config.config import Config
from module.device.device import Device
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.exit_game import ExitGame
from tasks.Component.SwitchAccount.login_account import LoginAccount
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.Component.Login.service import LoginService
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_login

from module.logger import logger


class SwitchAccount(LoginAccount, ExitGame, GameUi, SwitchAccountAssets):

    def __init__(
        self,
        config: Config,
        device: Device,
        to: AccountInfo,
        frm: AccountInfo = None,
        *,
        redact_logs: bool = False,
        on_ocr_complete: Callable[[], None] | None = None,
        ocr_coordinator=None,
        fast: bool = False,
    ):
        """

        @param config:
        @type config:
        @param device:
        @type device:
        @param to: 要登录的账号信息
        @type to:
        @param frm: 上一个账号信息 ,避免关键字from
        @type frm:
        """
        super().__init__(config, device)
        self.to_account_info = to
        self.from_account_info = frm
        self.redact_account_logs = redact_logs
        self.on_ocr_complete = on_ocr_complete
        self.ocr_coordinator = ocr_coordinator
        self.fast = fast

    def switchAccount(self):
        if self.redact_account_logs:
            logger.info("start switchAccount [redacted]")
        else:
            logger.info("start switchAccount %s-%s", self.to_account_info.character, self.to_account_info.svr)
        # MultiAccountEvo peers can wait longer than the image server frame
        # TTL. Register a fresh frame before page detection so a stale frame
        # reference cannot abort the next instance's account switch.
        self.screenshot()
        # 判断所处界面
        curPage = self.get_current_page()

        if curPage != page_login and curPage != page_main:
            self.goto_page(page_main)
            curPage = self.get_current_page()
        if curPage == page_main:
            self.exitGame()

        # 处于登录界面
        if self.fast:
            if not self.login_fast(self.to_account_info):
                return False
        else:
            if not self.login(self.to_account_info):
                return False
        if self.on_ocr_complete is not None:
            self.on_ocr_complete()
        if self.redact_account_logs:
            logger.info("account login success [redacted]")
        else:
            logger.info("%s login suc", self.to_account_info.character)
        # 处理位于登录界面各种奇葩弹窗
        login_handler = LoginService(
            config=self.config,
            device=self.device,
            skip_specific_server=self.fast,
            fast_login=self.fast,
        )
        login_handler.set_specific_usr(self.to_account_info.svr)
        login_handler.app_handle_login()

        return True


if __name__ == '__main__':
    config = Config('oas1')
    device=Device()
    toAccount=AccountInfo(account="email0@163.com", account_alias="emailO#emailo", apple_or_android=True, character="粘贴", svr="立秋夕烛")
    sa=SwitchAccount(config,device,toAccount)
    sa.switchAccount()
