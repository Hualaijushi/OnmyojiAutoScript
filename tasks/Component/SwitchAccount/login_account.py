import math
import time

from module.atom.click import RuleClick
from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.image.operators import threshold_bgr_to_inverted_rgb
from module.logger import logger
from tasks.Component.SwitchAccount.assets import SwitchAccountAssets
from tasks.Component.SwitchAccount.netease_account_ui import AccountUiUnavailable, NeteaseAccountUi
from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.base_task import BaseTask


class LoginAccount(BaseTask, SwitchAccountAssets):

    @property
    def account_logs_redacted(self) -> bool:
        return bool(getattr(self, 'redact_account_logs', False))

    def _coordinated_ocr(self, scene: str, recognizer, *, preprocess=None):
        """Acquire the cross-process OCR turn before taking a fresh frame."""
        coordinator = getattr(self, "ocr_coordinator", None)
        if coordinator is None:
            image = self.device.image
            if preprocess is not None:
                image = preprocess(image)
            return recognizer(image)
        with coordinator.lease(scene):
            # The frame must be created after the wait.  Otherwise a request
            # queued behind two instances can refer to an already expired ID.
            self.device.screenshot()
            image = self.device.image
            if preprocess is not None:
                image = preprocess(image)
            return recognizer(image)

    def ocr_appear(self, target: RuleOcr, interval: float = None) -> bool:
        coordinator = getattr(self, "ocr_coordinator", None)
        if coordinator is None:
            return super().ocr_appear(target, interval)
        with coordinator.lease(f"appear:{target.name}"):
            self.device.screenshot()
            return super().ocr_appear(target, interval)

    def _netease_account_ui(self) -> NeteaseAccountUi:
        return NeteaseAccountUi(self.device)

    def selected_account_from_ui(self) -> str | None:
        """Read the selected saved account without OCR."""
        return self._netease_account_ui().current_account()

    def get_svr_name(self):
        return self._coordinated_ocr(
            "login_server_name",
            self.O_SA_LOGIN_FORM_SVR_NAME.ocr,
        )

    def switch_svr(self, svrName: str):
        """
            需保证账号已登录 且处于登录界面
        @param svrName:
        @type svrName:
        """
        self.O_SA_LOGIN_FORM_SVR_NAME.keyword = svrName
        if self.ocr_appear(self.O_SA_LOGIN_FORM_SVR_NAME):
            return True
        self.ui_click(self.C_SA_LOGIN_FORM_SWITCH_SVR_BTN, self.I_SA_CHECK_SELECT_SVR_1, 1.5)
        # 展开底部角色列表,显示角色所属服务器
        self.screenshot()
        if self.appear(self.I_SA_CHECK_SELECT_SVR_1) and (not self.appear(self.I_SA_CHECK_SELECT_SVR_2)):
            self.click(self.O_SA_SELECT_SVR_CHARACTER_LIST)

        self.O_SA_SELECT_SVR_SVR_LIST.keyword = svrName
        found = False
        lastSvrList: tuple = ()
        while 1:
            ocrRes = self._coordinated_ocr(
                "server_list",
                self.O_SA_SELECT_SVR_SVR_LIST.detect_and_ocr,
                preprocess=lambda image: threshold_bgr_to_inverted_rgb(image, threshold=100),
            )
            # 受限于图像识别文字准确率,此处对识别结果与实际服务器名字 进行检查 字重合度大于阈值 就认为查找成功
            thresh = 0.5
            ocrSvrList = [res.ocr_text for res in ocrRes]
            for index, ocrSvrName in enumerate(ocrSvrList):
                if len(ocrSvrName) < 3:
                    break
                tmp = set(svrName).intersection(set(ocrSvrName))
                if len(tmp) > max(len(svrName), len(ocrSvrName)) * thresh:
                    if self.account_logs_redacted:
                        logger.info("target server found [redacted]")
                    else:
                        logger.info("found svr %s which is similar with %s", ocrSvrName, svrName)
                    found = True
                    # 确定点击位置
                    box = ocrRes[index].box
                    self.O_SA_SELECT_SVR_SVR_LIST.area = [self.O_SA_SELECT_SVR_SVR_LIST.roi[0] + box[0][0],
                                                          self.O_SA_SELECT_SVR_SVR_LIST.roi[1] + box[0][1],
                                                          box[1][0] - box[0][0],
                                                          box[2][1] - box[1][1]]
                    # 跳出此层for循环
                    break
            # 两次OCR结果相等表示滑动到最右侧
            if found or lastSvrList == ocrSvrList:
                break
            lastSvrList = ocrSvrList
            self.swipe(self.S_SA_SVR_SWIPE_LEFT)
            time.sleep(3.5)
        if found:
            self.click(self.O_SA_SELECT_SVR_SVR_LIST, interval=1.5)
            return True
        # 没找到 点击空白区域关闭选择服务器界面
        self.click(self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT)
        return False

    def switch_character(self, characterName: str):
        """
              需保证账号已登录 且处于登录界面
        @param characterName:
        @return:
        @rtype:
        """
        logger.info("start switch_character")
        # 改成对比是否出现 已有角色
        self.ui_click(self.C_SA_LOGIN_FORM_SWITCH_SVR_BTN, self.O_SA_CHECK_SELECT_SVR)
        # 展开底部角色列表,显示角色所属服务器
        self.screenshot()
        while (not self.appear(self.I_SA_CHECK_SELECT_SVR_2)) and self.appear(self.I_SA_CHECK_SELECT_SVR_1):
            logger.info("open svr icon")
            self.click(self.C_SA_SELECT_SVR_CHARACTER_LIST, interval=1.5)
            self.wait_until_appear(self.I_SA_CHECK_SELECT_SVR_2, False, 1)
            # self.ui_click(self.C_SA_SELECT_SVR_CHARACTER_LIST, self.I_SA_CHECK_SELECT_SVR_2, 1.5)
            self.screenshot()

        self.O_SA_SELECT_SVR_CHARACTER_LIST.keyword = characterName
        lastCharacterNameList = []
        while 1:
            ocrRes = self._coordinated_ocr(
                "character_list",
                self.O_SA_SELECT_SVR_CHARACTER_LIST.detect_and_ocr,
            )
            # 去除角色等级数字
            characterNameList = [ocrResItem.ocr_text.lstrip('1234567890 ([<>])【】（）《》') for ocrResItem in ocrRes]
            if self.account_logs_redacted:
                logger.info("OCR character candidates: %s", len(characterNameList))
            else:
                logger.info(characterNameList)
            ocrResBoxList = [ocrResItem.box for ocrResItem in ocrRes]
            for index, item in enumerate(characterNameList):
                if item != characterName:
                    continue
                tmp = self.O_SA_SELECT_SVR_CHARACTER_LIST
                from copy import deepcopy
                tmpClick = RuleClick(
                    roi_back=deepcopy(tmp.roi),
                    roi_front=[
                        tmp.roi[0] + ocrResBoxList[index][0][0],
                        tmp.roi[1] + ocrResBoxList[index][0][1],
                        ocrResBoxList[index][1][0] - ocrResBoxList[index][0][0],
                        ocrResBoxList[index][2][1] - ocrResBoxList[index][1][1]],
                    name="tmpClick"
                )

                # 此时 tmp 内存储的时角色名位置,而点击角色名没有反应
                # 所以需要获取到对应的服务器图标位置
                tmpClick.roi_front[1] -= 30
                self.ui_click_until_disappear(tmpClick, stop=self.I_SA_CHECK_SELECT_SVR_2,
                                              interval=3)
                if self.account_logs_redacted:
                    logger.info("target character found and server icon clicked [redacted]")
                else:
                    logger.info("character %s found,and clicked svr icon", characterName)
                return True
            if lastCharacterNameList == characterNameList:
                break
            if self.account_logs_redacted:
                logger.info('target character not found, start swipe [redacted]')
            else:
                logger.info(f'{characterName} not found,start swipe')
            lastCharacterNameList = characterNameList
            self.swipe(self.S_SA_ACCOUNT_LIST_UP)
            # 等待滑动动画完成
            time.sleep(1.5)

        self.click(self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT, 1.5)
        return False

    def jump2SelectAccount(self):
        """
            跳转到切换账号页面 该页面有红色登录按钮
        @return:
        @rtype:
        """
        while 1:
            if self.appear(self.I_SA_NETEASE_GAME_LOGO) and self.appear(self.I_SA_ACCOUNT_DROP_DOWN_CLOSED):
                return
            if self.handle_login_method_page():
                continue
            if self.appear_then_click(self.I_SA_SWITCH_ACCOUNT_BTN, interval=1.5):
                continue
            if self.appear(self.I_CHECK_LOGIN_FORM):
                self.click(self.C_SA_LOGIN_FORM_USER_CENTER, 1.5)
                continue
        return

    def handle_login_method_page(self) -> bool:
        """Enter NetEase email login from the provider selection page."""
        if not self.appear(self.I_SA_NETEASE_GAME_LOGO):
            return False
        if self.appear(self.I_SA_ACCOUNT_LOGIN_BTN) or self.appear(self.I_SA_ACCOUNT_DROP_DOWN_CLOSED):
            return False
        if not self.ocr_appear(self.O_SA_LOGIN_METHOD_EMAIL):
            return False
        logger.info("Login method page detected, select NetEase email")
        # The page normally opens unchecked. If an interrupted attempt left
        # it checked, retrying this handler once restores the checked state.
        self.click(self.C_SA_LOGIN_METHOD_AGREEMENT, interval=0.5)
        self.click(self.C_SA_LOGIN_METHOD_EMAIL, interval=1.5)
        return True

    def submit_saved_account_login(self) -> None:
        """Click the native login control, with the old safe area as fallback."""
        try:
            if self._netease_account_ui().click_login():
                logger.info("Submit saved account login using native UI control")
                time.sleep(1.0)
                return
        except AccountUiUnavailable as exc:
            logger.warning("Native account login control unavailable: %s", exc)
        logger.info("Submit saved account login using safe button area fallback")
        self.click(self.C_SA_ACCOUNT_LOGIN_SAFE, interval=1.0)
        time.sleep(1.0)

    def select_login_platform_fast(self, apple_or_android: bool) -> None:
        """通过模板匹配选择苹果或安卓登录平台。

        复用已有平台模板获取按钮实际坐标，避免随机点击固定区域边缘。
        """
        if self.account_logs_redacted:
            logger.info("Select login platform using image matching [redacted]")
        else:
            logger.info(
                "Select login platform using image matching, apple_or_android=%s",
                apple_or_android,
            )
        platform = self.I_SA_LOGIN_FORM_ANDROID if apple_or_android else self.I_SA_LOGIN_FORM_APPLE
        self.appear_then_click(platform, interval=1.0)

    def login_fast(self, accountInfo: AccountInfo) -> bool:
        """执行不包含服务商、服务器和角色识别的快速多账号登录。

        通过原生界面选择并提交已保存账号，再匹配苹果或安卓平台按钮。
        跳过服务商 OCR、服务器和角色选择，由游戏自动进入默认角色，
        最后由调用方校验庭院角色。
        """
        self.screenshot()
        if not (self.appear(self.I_CHECK_LOGIN_FORM) or self.appear(self.I_SA_NETEASE_GAME_LOGO)):
            if self.account_logs_redacted:
                logger.error("Unknown page, fast account login failed [redacted]")
            else:
                logger.error("Unknown Page,%s %s Login Failed", accountInfo.character, accountInfo.svr)
            return False

        # Recovery: leave a stray server/character selection page left by an
        # interrupted attempt without OCR-selecting anything.
        for _ in range(3):
            self.screenshot()
            if not (self.appear(self.I_SA_CHECK_SELECT_SVR_1) or self.appear(self.I_SA_CHECK_SELECT_SVR_2)):
                break
            self.click(self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT)

        # Saved-account page: select the target account and submit.
        if self.appear(self.I_SA_NETEASE_GAME_LOGO) and not self.appear(self.I_SA_LOGIN_FORM_APPLE):
            if not accountInfo.account:
                logger.error("param account is None, cannot switch account")
                return False
            try:
                selected_account = self.selected_account_from_ui()
                selected_matches = self._netease_account_ui().account_matches(
                    selected_account,
                    accountInfo.account,
                )
                if not selected_account:
                    raise AccountUiUnavailable("selected account field missing")
            except AccountUiUnavailable as exc:
                logger.warning(
                    "Native selected-account check unavailable, falling back to OCR: %s",
                    exc,
                )
                self.O_SA_ACCOUNT_ACCOUNT_SELECTED.keyword = accountInfo.account
                selected_matches = self.ocr_appear(self.O_SA_ACCOUNT_ACCOUNT_SELECTED)
            if not selected_matches:
                if not self.selectAccount(accountInfo):
                    self.ui_click_until_disappear(
                        self.C_SA_LOGIN_FORM_ACCOUNT_CLOSE_BTN,
                        stop=self.I_SA_NETEASE_GAME_LOGO,
                    )
                    return False
                self.screenshot()
                # Defense: never submit unless the dropdown is closed and the
                # selected account really matches the target.  A stale UI-tree
                # bounds click can otherwise open the "other account login"
                # page and leave the switch retrying from the wrong screen.
                if not self._account_selection_confirmed(accountInfo):
                    logger.warning(
                        "Fast account selection did not confirm target [redacted]"
                    )
                    return False
            self.submit_saved_account_login()

        # 平台页面到达时间不固定，先有界等待页面标识，再匹配对应平台按钮。
        if not self.wait_until_appear(self.I_SA_LOGIN_FORM_APPLE, False, wait_time=45):
            logger.warning("Fast login platform page timeout")
            return False
        if not self._select_platform_and_confirm(accountInfo.apple_or_android):
            logger.warning("Fast login platform selection did not close the page")
            return False
        return True

    def _select_platform_and_confirm(self, apple_or_android: bool, max_attempts: int = 3) -> bool:
        """点击对应平台按钮，并确认平台页面已经关闭。

        前两次使用短确认窗口快速补点，最后一次保留较长窗口兼容页面加载缓慢。
        """
        attempt_limit = max(1, int(max_attempts))
        for attempt in range(1, attempt_limit + 1):
            self.select_login_platform_fast(apple_or_android)
            confirm_wait = 8 if attempt == attempt_limit else 2
            if self._platform_page_closed(wait_time=confirm_wait):
                return True
            logger.warning(
                "Fast login platform click attempt %s/%s did not close the page",
                attempt,
                max_attempts,
            )
        return False

    def _platform_page_closed(self, wait_time: float = 8.0) -> bool:
        """Wait until the provider page disappears after the platform click.

        A click swallowed by the page transition would otherwise leave the
        launcher on "select login platform" while app_handle_login has no
        enter-game button to click, hanging until the stuck guard fires.
        """
        deadline = time.monotonic() + max(0.0, float(wait_time))
        while time.monotonic() < deadline:
            self.screenshot()
            if not self.appear(self.I_SA_LOGIN_FORM_APPLE):
                return True
            time.sleep(0.3)
        return False

    def _account_selection_confirmed(self, accountInfo: AccountInfo) -> bool:
        """Confirm the launcher actually selected the target account.

        Returns False when the account dropdown is still open or the selected
        account does not match, so the fast path retries instead of submitting
        from a wrong page (e.g. the "other account login" entry).
        """
        try:
            selected = self.selected_account_from_ui()
            if not selected:
                return False
            return self._netease_account_ui().account_matches(
                selected,
                accountInfo.account,
            )
        except AccountUiUnavailable as exc:
            logger.warning(
                "Native selected-account check unavailable, falling back to OCR: %s",
                exc,
            )
            self.O_SA_ACCOUNT_ACCOUNT_SELECTED.keyword = accountInfo.account
            return bool(self.ocr_appear(self.O_SA_ACCOUNT_ACCOUNT_SELECTED))

    def selectAccount(self, accountInfo: AccountInfo):
        """Select and confirm a saved account through the native UI tree."""
        logger.info("start selectAccount using native UI control")
        try:
            selected = self._netease_account_ui().select_account(accountInfo.account)
            if selected:
                if self.account_logs_redacted:
                    logger.info("account selected and confirmed by native UI [redacted]")
                else:
                    logger.info("account selected and confirmed by native UI: %s", accountInfo.account)
                return True
            logger.warning("Target account not found or not confirmed in native account list")
            if self.fast:
                # 原生列表偶发漏项时，仅在快速路径复用已有 OCR 选择作为第二层兜底。
                logger.warning("Native account selection missed target, falling back to OCR")
                return self._selectAccountByOcr(accountInfo)
            return False
        except AccountUiUnavailable as exc:
            logger.warning("Native account UI unavailable, falling back to OCR: %s", exc)
            return self._selectAccountByOcr(accountInfo)

    def _selectAccountByOcr(self, accountInfo: AccountInfo):
        logger.info("start selectAccount")
        self.O_SA_ACCOUNT_ACCOUNT_LIST.keyword = accountInfo.account
        self.O_SA_ACCOUNT_ACCOUNT_SELECTED.keyword = accountInfo.account
        # 正常情况一次就行,但防不住OCR搞幺蛾子 保险起见 多来几次吧 反正挂机不差这点
        for i in range(3):
            while 1:
                self.screenshot()
                if self.appear(self.I_SA_ACCOUNT_DROP_DOWN_CLOSED):
                    if self.ocr_appear(self.O_SA_ACCOUNT_ACCOUNT_SELECTED):
                        return True
                    self.ui_click_until_disappear(self.I_SA_ACCOUNT_DROP_DOWN_CLOSED,
                                                  interval=1.5)
                    continue

                # 账号列表已打开状态
                ocrRes = self._coordinated_ocr(
                    "account_list",
                    self.O_SA_ACCOUNT_ACCOUNT_LIST.detect_and_ocr,
                )

                # 找到该账号
                for index, ocr_account in enumerate([ocrResItem.ocr_text for ocrResItem in ocrRes]):
                    if not accountInfo.is_account_alias(ocr_account):
                        continue
                    # if accountInfo.account in [ocrResItem.ocr_text for ocrResItem in ocrRes]:
                    #     index = [ocrResItem.ocr_text for ocrResItem in ocrRes].index(accountInfo.account)
                    ocrResBoxList = [ocrResItem.box for ocrResItem in ocrRes]
                    self.O_SA_ACCOUNT_ACCOUNT_LIST.area = [
                        self.O_SA_ACCOUNT_ACCOUNT_LIST.roi[0] + ocrResBoxList[index][0][
                            0],
                        self.O_SA_ACCOUNT_ACCOUNT_LIST.roi[1] + ocrResBoxList[index][0][
                            1],
                        ocrResBoxList[index][1][0] - ocrResBoxList[index][0][0],
                        ocrResBoxList[index][2][1] - ocrResBoxList[index][1][1]]
                    time.sleep(1)
                    self.click(self.O_SA_ACCOUNT_ACCOUNT_LIST)
                    if self.account_logs_redacted:
                        logger.info("account found [redacted]")
                    else:
                        logger.info("account [ %s ] found", accountInfo.account)
                    return True

                # 未找到该账号
                if self.appear(self.I_SA_ACCOUNT_DROP_DOWN_ADD_ACCOUNT):
                    break
                self.swipe(self.S_SA_ACCOUNT_LIST_UP, 1.5)
                time.sleep(0.5)
        if self.account_logs_redacted:
            logger.info("account not found [redacted]")
        else:
            logger.info("account [ %s ] not found ", accountInfo.account)
        return False

    # def loginSubmit(self, appleOrAndroid: bool):
    #     """
    #
    #     @param appleOrAndroid: 安卓平台还是苹果平台
    #     @type appleOrAndroid:   False           Apple
    #                             True            Android
    #     @return:
    #     @rtype:
    #     """
    #     self.screenshot()
    #     if not (self.appear(self.I_SA_ACCOUNT_LOGIN_BTN) and self.appear(self.I_SA_NETEASE_GAME_LOGO)):
    #         # 不在登录界面,返回失败
    #         return False
    #     self.ui_click(self.C_SA_LOGIN_FORM_LOGIN_BTN, self.I_SA_LOGIN_FORM_APPLE, 1)
    #     if appleOrAndroid:
    #         logger.info("APPLE selected")
    #         self.ui_click_until_disappear(self.I_SA_LOGIN_FORM_APPLE, 1)
    #     else:
    #         logger.info("ANDROID selected")
    #         self.ui_click_until_disappear(self.I_SA_LOGIN_FORM_ANDROID, 1)
    #     return True

    def login(self, accountInfo: AccountInfo) -> bool:
        """

        @param accountInfo:
        @type accountInfo:
        @return:    True    点击了"进入游戏"按钮
                    False   未找到相应角色
        @rtype:bool
        """
        self.screenshot()
        #
        if not (self.appear(self.I_CHECK_LOGIN_FORM) or self.appear(self.I_SA_NETEASE_GAME_LOGO)):
            if self.account_logs_redacted:
                logger.error("Unknown page, account login failed [redacted]")
            else:
                logger.error("Unknown Page,%s %s Login Failed", accountInfo.character, accountInfo.svr)
            return False

        #
        isAccountLogon = False
        isCharacterSelected = False
        self.O_SA_ACCOUNT_ACCOUNT_SELECTED.keyword = accountInfo.account
        self.O_SA_LOGIN_FORM_USER_CENTER_ACCOUNT.keyword = accountInfo.account
        while 1:
            self.screenshot()
            # 处于 选择服务器界面 直接点击空白区域退出该界面 进入切换账号流程
            if self.appear(self.I_SA_CHECK_SELECT_SVR_1) or self.appear(self.I_SA_CHECK_SELECT_SVR_2):
                self.click(self.C_SA_LOGIN_FORM_CANCEL_SVR_SELECT)
                continue

            if self.handle_login_method_page():
                isAccountLogon = False
                continue

            # 处于选择 苹果安卓界面
            if self.appear(self.I_SA_LOGIN_FORM_APPLE):
                btn = self.I_SA_LOGIN_FORM_ANDROID if accountInfo.apple_or_android else self.I_SA_LOGIN_FORM_APPLE
                self.ui_click_until_disappear(btn)
                isAccountLogon = True
                continue
            # 处于选择账号界面
            if self.appear(self.I_SA_NETEASE_GAME_LOGO) and not self.appear(self.I_SA_LOGIN_FORM_APPLE):
                if not accountInfo.account:
                    logger.error("param account is None,cannot switch account")
                    return False
                # Prefer the native account field. OCR is retained only when
                # the hierarchy service is temporarily unavailable.
                try:
                    selected_account = self.selected_account_from_ui()
                    selected_matches = self._netease_account_ui().account_matches(
                        selected_account,
                        accountInfo.account,
                    )
                    if not selected_account:
                        raise AccountUiUnavailable("selected account field missing")
                except AccountUiUnavailable as exc:
                    logger.warning("Native selected-account check unavailable, falling back to OCR: %s", exc)
                    selected_matches = self.ocr_appear(self.O_SA_ACCOUNT_ACCOUNT_SELECTED)
                # 当前选择账号不是account
                if not selected_matches:
                    # 没有找到account
                    if not self.selectAccount(accountInfo):
                        self.ui_click_until_disappear(self.C_SA_LOGIN_FORM_ACCOUNT_CLOSE_BTN,
                                                      stop=self.I_SA_NETEASE_GAME_LOGO)
                        return False
                    # selectAccount 后更新图片
                    self.screenshot()
                self.submit_saved_account_login()
                continue
            # 在用户中心界面
            if self.appear(self.I_SA_SWITCH_ACCOUNT_BTN):
                # 如果当前已登录用户就是account
                ocrRes = self._coordinated_ocr(
                    "current_account",
                    self.O_SA_LOGIN_FORM_USER_CENTER_ACCOUNT.ocr_single,
                )
                # NOTE 由于邮箱账号@符号极易被误识别为其他,故对账号信息做预处理 便于比对
                if (accountInfo.account is None) or accountInfo.account == "" or accountInfo.is_account_alias(ocrRes):
                    if self.account_logs_redacted:
                        logger.info("current account matches target [redacted]")
                    else:
                        logger.info("current is the account we want:ocr result %s", ocrRes)
                    isAccountLogon = True
                    self.ui_click_until_disappear(self.C_SA_LOGIN_FORM_USER_CENTER_CLOSE_BTN, interval=1,
                                                  stop=self.I_SA_SWITCH_ACCOUNT_BTN)
                    continue
                #
                if self.ui_click(self.I_SA_SWITCH_ACCOUNT_BTN, self.I_SA_NETEASE_GAME_LOGO):
                    isAccountLogon = False
                    continue
                continue
            # 在游戏登录界面 不在用户中心 不在切换账号界面
            if not (self.appear(self.I_SA_NETEASE_GAME_LOGO) or self.appear(self.I_SA_SWITCH_ACCOUNT_BTN)):
                # 判断是否已经账号登录
                if not isAccountLogon:
                    self.click(self.C_SA_LOGIN_FORM_USER_CENTER)
                    continue

                # 已登录 查找对应角色
                if not isCharacterSelected and self.switch_character(accountInfo.character):
                    isCharacterSelected = True
                    continue
                break
            continue

        # 切换角色失败 /未找到该角色
        # 尝试使用 选择服务器方式
        if isAccountLogon and not isCharacterSelected and accountInfo.svr is not None and accountInfo.svr != "":
            if self.account_logs_redacted:
                logger.info("try to find character by server [redacted]")
            else:
                logger.info("try to find character with svrName %s", accountInfo.svr)
            isCharacterSelected = self.switch_svr(accountInfo.svr)
        if isAccountLogon and isCharacterSelected:
            # 成功登录账号 找到角色
            # self.ui_click_until_disappear(self.C_SA_LOGIN_FORM_ENTER_GAME_BTN, stop=self.I_CHECK_LOGIN_FORM)
            if self.account_logs_redacted:
                logger.info("account login success [redacted], platform=%s",
                            'Android' if accountInfo.apple_or_android else 'Apple')
            else:
                logger.info("character %s-%s account:%s %s login Success", accountInfo.character, accountInfo.svr,
                            accountInfo.account,
                            'Android' if accountInfo.apple_or_android else 'Apple')
            return True

        if self.account_logs_redacted:
            logger.error("account login failed [redacted], platform=%s",
                         'Android' if accountInfo.apple_or_android else 'Apple')
        else:
            logger.error("character %s-%s account:%s %s login Failed", accountInfo.character, accountInfo.svr,
                         accountInfo.account,
                         'Android' if accountInfo.apple_or_android else 'Apple')
        return False

    def ui_click_until_disappear(self, click, interval: float = 1, stop: RuleImage | RuleGif = None):
        """
        重写原ui_click_until_disappear方法,增加stop参数
        点击一个按钮直到stop消失
        如果click为RuleOcr ,直接当作RuleClick点击,不会进行ocr识别,
        @param interval:
        @param click:
        @param stop:
        @type stop:
        @return:
        """
        if (isinstance(click, RuleImage) or isinstance(click, RuleGif)) and (stop is None):
            stop = click
        while 1:
            self.screenshot()
            if not self.appear(stop):
                break
            if isinstance(click, RuleImage) or isinstance(click, RuleGif):
                self.appear_then_click(click, interval=interval)
                continue
            elif isinstance(click, RuleClick):
                self.click(click, interval)
                continue
            elif isinstance(click, RuleOcr):
                self.click(click)
                continue
