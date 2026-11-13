import time

from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.Restart.assets import RestartAssets
from tasks.base_task import BaseTask
from module.exception import ScriptError
from module.logger import logger


class ExitGame(BaseTask, SwitchAccountAssets):

    def exitGame(self):
        logger.info("start game exit")
        # 复用庭院导航的关闭规则；只有关闭弹窗并重新确认庭院后才允许再次点头像。
        deadline = time.monotonic() + 12
        profile_clicked = False
        courtyard_frames = 0
        waiting_bind_cancel = False
        while time.monotonic() < deadline:
            self.screenshot()
            if waiting_bind_cancel:
                if self.appear_then_click(RestartAssets.I_LOGIN_LOGIN_CANCEL_BIND_PHONE, interval=1):
                    logger.info("切号时取消绑定提示，重新确认页面")
                    waiting_bind_cancel = False
                    profile_clicked = False
                    courtyard_frames = 0
                    time.sleep(0.5)
                else:
                    time.sleep(0.3)
                continue
            if self.appear_then_click(RestartAssets.I_LOGIN_LOGIN_GOTO_BIND_PHONE, interval=1):
                logger.info("切号时发现绑定提示，等待取消按钮")
                waiting_bind_cancel = True
                continue
            if self.appear(self.I_SA_USER_CENTER):
                break
            if not profile_clicked and (
                    self.appear_then_click(GameUiAssets.I_AD_CLOSE_RED, interval=1)
                    or self.appear_then_click(GlobalGameAssets.I_UI_BACK_RED, interval=1)):
                logger.info("切号时关闭庭院弹窗，重新确认页面")
                profile_clicked = False
                courtyard_frames = 0
                time.sleep(0.5)
                continue
            if not profile_clicked:
                if self.appear(GameUiAssets.I_CHECK_MAIN):
                    courtyard_frames += 1
                    if courtyard_frames >= 2:
                        self.click(self.C_SA_EG_PROFILE_PHOTO)
                        profile_clicked = True
                else:
                    courtyard_frames = 0
            time.sleep(0.3)
        else:
            raise ScriptError("profile page not opened")
        if not self.appear_then_click(self.I_SA_USER_CENTER, interval=1):
            raise ScriptError("user center button not found")
        if not self.wait_until_appear(self.I_SA_SWITCH_ACCOUNT_BTN, wait_time=8):
            raise ScriptError("user center not opened")
        self.ui_click_until_disappear(self.I_SA_SWITCH_ACCOUNT_BTN, 3)
