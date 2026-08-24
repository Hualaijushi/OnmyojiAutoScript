from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.base_task import BaseTask
from module.exception import ScriptError
from module.logger import logger


class ExitGame(BaseTask, SwitchAccountAssets):

    def exitGame(self):
        logger.info("start game exit")
        # 头像只点击一次，避免设置页打开后再次点击同一坐标误触扫一扫。
        self.click(self.C_SA_EG_PROFILE_PHOTO)
        if not self.wait_until_appear(self.I_SA_USER_CENTER, wait_time=5):
            raise ScriptError("profile page not opened")
        if not self.appear_then_click(self.I_SA_USER_CENTER, interval=1):
            raise ScriptError("user center button not found")
        if not self.wait_until_appear(self.I_SA_SWITCH_ACCOUNT_BTN, wait_time=8):
            raise ScriptError("user center not opened")
        self.ui_click_until_disappear(self.I_SA_SWITCH_ACCOUNT_BTN, 3)
