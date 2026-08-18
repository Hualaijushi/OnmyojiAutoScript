# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from module.base.timer import Timer
from module.atom.click import RuleClick
from module.atom.ocr import RuleOcr
from module.exception import RequestHumanTakeover, GameTooManyClickError, GameStuckError
from module.logger import logger
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.chess_battle import ChessBattleNavigationMixin
from tasks.Restart.assets import RestartAssets
from tasks.base_task import BaseTask


FAST_LOGIN_ENTER_GAME_INTERVAL = 30.0
FAST_LOGIN_MAX_ENTER_GAME_ATTEMPTS = 3

# NetEase launcher "other login method" page blocks enter-game until the
# agreement checkbox is ticked ("未勾选同意将无法登录").  The warning sits at
# the bottom-centre of the 1280x720 launcher layout.
O_LOGIN_AGREEMENT_WARNING = RuleOcr(
    name="login_agreement_warning",
    mode="FULL",
    method="Default",
    roi=(380, 520, 520, 120),
    area=(380, 520, 520, 120),
    keyword="",
)
# Top-left back button of the NetEase "other login method" page.
LOGIN_METHOD_PAGE_BACK = RuleClick(
    roi_front=(15, 10, 60, 60),
    roi_back=(15, 10, 60, 60),
    name="login_method_page_back",
)


class LoginService(
    ChessBattleNavigationMixin,
    BaseTask,
    RestartAssets,
    GameUiAssets,
):
    character: str

    def __init__(self, *wargs, skip_specific_server: bool = False, fast_login: bool = False, **kwargs):
        super().__init__(*wargs, **kwargs)
        self.skip_specific_server = skip_specific_server
        self.fast_login = fast_login or self._recovery_should_use_fast_login()
        self._enter_game_attempts = 0
        self._login_method_page_handled = False
        self.character = self.config.restart.login_character_config.character
        self.O_LOGIN_SPECIFIC_SERVE.keyword = self.character

    def _recovery_should_use_fast_login(self) -> bool:
        """Enable the fast login path during Restart recovery for MultiAccountEvo.

        The runtime controller restarts the game through the generic Restart
        task right before MultiAccountEvo runs, and that recovery still uses
        the legacy rapid-click login, which stalls on accounts whose launcher
        login is slow.  When MultiAccountEvo is the next pending task and no
        task is running, reuse the fast login path (fixed platform clicks and
        enter-game backoff) without changing the Restart task itself.
        """
        try:
            running = getattr(self.config.model, "running_task", "")
            evo_enabled = bool(self.config.multi_account_evo.scheduler.enable)
        except Exception:
            return False
        if running and str(running).casefold() != "multiaccountevo":
            return False
        if evo_enabled:
            return True
        pending = getattr(self.config, "pending_task", None)
        try:
            first = pending[0] if pending else None
        except Exception:
            return False
        return str(getattr(first, "command", "")).casefold() == "multiaccountevo"

    def _handle_login_method_page(self) -> bool:
        """Leave the launcher "other login method" page when it blocks login.

        The 手机账号/扫码登录 page requires a manual phone login ("未勾选同意将
        无法登录"); ticking the box alone is not enough.  Click the top-left
        back button to return to the saved-account page where enter-game works,
        otherwise the login recovery stalls on all instances.
        """
        if self._login_method_page_handled:
            return False
        try:
            text = str(O_LOGIN_AGREEMENT_WARNING.ocr(self.device.image) or "")
        except Exception:
            return False
        if "未勾选" not in text:
            return False
        logger.info("Leave other-login page via top-left back button")
        self.click(LOGIN_METHOD_PAGE_BACK, interval=1.0)
        self._login_method_page_handled = True
        return True

    def _enter_game_interval(self) -> float:
        """Seconds between enter-game clicks; fast login waits much longer."""
        return FAST_LOGIN_ENTER_GAME_INTERVAL if self.fast_login else 3.0

    @staticmethod
    def _max_enter_game_attempts() -> int:
        return FAST_LOGIN_MAX_ENTER_GAME_ATTEMPTS

    def _try_click_enter_game(self) -> bool:
        """Click the launcher's enter-game button with fast-login backoff.

        Clicking enter-game starts the game login, and clicking it again while
        the session is still settling interrupts that login and keeps the
        launcher on screen.  Fast mode therefore leaves a long quiet interval
        between attempts and, after a bounded number of clicks, falls through
        to the existing stuck/app-restart recovery instead of spamming the
        button until the too-many-click guard trips.
        """
        if self._handle_login_method_page():
            return False
        if not self.ocr_appear_click(self.O_LOGIN_ENTER_GAME, interval=self._enter_game_interval()):
            return False
        self._enter_game_attempts += 1
        if not self.skip_specific_server:
            self.wait_until_appear(self.I_LOGIN_SPECIFIC_SERVE, True, wait_time=5)
        if self.fast_login and self._enter_game_attempts >= self._max_enter_game_attempts():
            logger.warning(
                'Fast login enter-game did not progress after %s attempts',
                self._enter_game_attempts,
            )
            raise GameStuckError('fast login enter game timeout after repeated attempts')
        return True

    def _app_handle_login(self) -> bool:
        """
        最终是在庭院界面
        :return:
        """
        logger.hr('App login')
        self.device.stuck_record_add('LOGIN_CHECK')

        confirm_timer = Timer(1.5, count=2).start()
        orientation_timer = Timer(10)
        login_success = False

        while 1:
            if not login_success and orientation_timer.reached():
                self.device.get_orientation()
                orientation_timer.reset()

            self.screenshot()
            if self.appear_then_click(
                self.I_RETURN_CHESS_CANCEL,
                interval=0.8,
            ):
                logger.info(
                    'Cancel returning to interrupted Chess battle; '
                    'wait for result flow'
                )
                continue
            if self.appear(self.I_CHECK_CHESS):
                logger.info(
                    'Login recovery reached Chess lobby; '
                    'finish recovery without returning to courtyard'
                )
                return True
            if self.chess_result_flow_visible():
                logger.info(
                    'Login recovery detected unfinished Chess result flow'
                )
                self.return_to_chess_lobby()
                return True
            if self.appear_then_click(self.I_CANCEL_BATTLE, interval=0.8):
                logger.info('Cancel continue battle')
                continue
            if self.appear(self.I_CHECK_MAIN, interval=0.2) and not self.appear(self.I_MAIN_GOTO_SHIKIGAMI_RECORDS):
                logger.info('The main had already appeared, but shikigami records had not yet appeared')
                if self.click(self.C_LOGIN_SCROLL_CLOSE_AREA, interval=2):
                    continue
            if self.appear(self.I_MAIN_GOTO_SHIKIGAMI_RECORDS, interval=0.2):
                if confirm_timer.reached():
                    logger.info('Login to main confirm (shikigami records button appears)')
                    break
            else:
                confirm_timer.reset()
            if self.appear(self.I_MAIN_GOTO_SHIKIGAMI_RECORDS, interval=0.5):
                logger.info('Login success: shikigami records button appears')
                login_success = True
            if self.appear(self.I_HARVEST_ZIDU, interval=1):
                self.I_HARVEST_ZIDU.roi_front[0] -= 200
                self.I_HARVEST_ZIDU.roi_front[1] -= 200
                if self.click(self.I_HARVEST_ZIDU, interval=2):
                    logger.info('Close zidu')
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=2.5):
                logger.info('Soul overflow confirm')
                continue
            if self.appear_then_click(self.I_LOGIN_LOAD_DOWN, interval=1):
                logger.info('Download inbetweening')
                continue
            if self.appear_then_click(self.I_WATCH_VIDEO_CANCEL, interval=0.6):
                logger.info('Close video')
                continue
            if self.appear_then_click(self.I_LOGIN_RED_CLOSE, interval=0.6):
                logger.info('Close red close')
                continue
            if self.appear_then_click(self.I_LOGIN_YELLOW_CLOSE, interval=0.6):
                logger.info('Close yellow close')
                continue
            if self.appear_then_click(self.I_LOGIN_LOGIN_GOTO_BIND_PHONE):
                while 1:
                    self.screenshot()
                    if self.appear_then_click(self.I_LOGIN_LOGIN_CANCEL_BIND_PHONE):
                        logger.info("Close bind phone")
                        break
                continue
            from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as gia
            if self.appear_then_click(gia.I_I_REJECT, interval=0.8):
                logger.info("reject invites")
                continue
            if self.appear_then_click(self.I_LOGIN_LOGIN_ONMYOJI_GENIE):
                logger.info("click onmyoji genie")
                continue
            if not self.skip_specific_server and self.appear(self.I_LOGIN_SPECIFIC_SERVE, interval=0.6) \
                    and self.ocr_appear_click(self.O_LOGIN_SPECIFIC_SERVE, interval=0.6):
                while True:
                    self.screenshot()
                    if self.appear(self.I_LOGIN_SPECIFIC_SERVE):
                        self.click(self.C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR, interval=2)
                        continue
                    break
                logger.info('login specific user')
                continue

            if self.appear(self.I_CREATE_ACCOUNT):
                logger.warning('Appear create account')
                raise GameStuckError('Appear create account')

            if self.appear(self.I_CHARACTARS, interval=1):
                logger.info('误入区服设置')
                self.device.click(x=106, y=535)

            if not self.appear(self.I_LOGIN_8):
                continue

            if self.appear(self.I_EARLY_SERVER):
                if self.appear_then_click(self.I_EARLY_SERVER_CANCEL):
                    logger.info('Cancel switch from early server to normal server')
                    continue
            if self._try_click_enter_game():
                continue
            if self.appear(self.I_LOGIN_SCROOLL_CLOSE) or self.appear(self.I_LOGIN_SCROOLL_OPEN):
                return login_success

    def app_handle_login(self) -> bool:
        self.device.stuck_record_clear()
        self.device.click_record_clear()
        try:
            self._app_handle_login()
            return True
        except (GameTooManyClickError, GameStuckError) as e:
            logger.warning(e)
            self.device.app_stop()
            self.device.app_start()

        logger.critical('Login failed')
        logger.critical('Onmyoji server may be under maintenance, or you may lost network connection')
        raise RequestHumanTakeover

    def set_specific_usr(self, character: str):
        self.character = character
        self.O_LOGIN_SPECIFIC_SERVE.keyword = character
