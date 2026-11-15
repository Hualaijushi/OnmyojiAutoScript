"""仅为多账号超鬼王补齐进入游戏超时后的单次登录恢复。"""

from types import SimpleNamespace

from module.exception import GameStuckError, RequestHumanTakeover
from module.logger import logger
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from tasks.Component.Login.service import LoginService
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.GameUi.navigator import GameUi


class _LoginRecoveryVerifier(GameUi, CourtyardCharacterVerifierMixin):
    """复用原庭院与角色核对，不使用切号器的成功缓存。"""


class RotationRetryLoginService(LoginService):
    """正常路径完全沿用原实现，仅对明确的进入游戏超时恢复一次。"""

    def __init__(self, *args, expected_account=None, **kwargs):
        super().__init__(*args, expected_account=expected_account, **kwargs)
        self._rotation_target = expected_account

    def _app_handle_login(self):
        try:
            return super()._app_handle_login()
        except GameStuckError as exc:
            if not self.fast_login or str(exc) != 'fast login enter game timeout after repeated attempts':
                raise

        target = self._rotation_target
        if target is None or not target.account or not target.svr or not target.character:
            raise RequestHumanTakeover('登录恢复缺少目标身份，停止当前账号')
        logger.warning('[超鬼王轮换] 进入游戏超时，重启后重试当前目标账号 1/1')
        try:
            self.device.app_stop()
            self.device.app_start()
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            # 新处理器重建点击计数和账号弹窗状态，仍复用原有页面识别与目标核对。
            retry = LoginService(self.config, self.device,
                                 skip_specific_server=self.skip_specific_server,
                                 fast_login=self.fast_login, expected_account=target)
            retry.set_specific_usr(self.character)
            # 不调用会自行重启的公共包装，避免失败后再次重启。
            retry._app_handle_login()
            verifier = _LoginRecoveryVerifier(self.config, self.device)
            expected = SimpleNamespace(instance=self.config.config_name, account_id='login-recovery-target',
                                       character=target.character)
            if verifier._verify_courtyard_character(expected) is not True:
                raise RequestHumanTakeover('重启后目标角色未确认，停止当前账号')
            logger.info('[超鬼王轮换] 重启后目标庭院核对通过，继续当前账号')
            return True
        except Exception as exc:
            # 失败直接暂停，不能被外层普通切号重试再次放大为多轮重启。
            logger.warning('[超鬼王轮换] 单次登录恢复失败：%s', type(exc).__name__)
            raise RequestHumanTakeover('重启后登录恢复未确认，停止当前账号') from exc


class RotationRetrySwitchAccount(SwitchAccount):
    """只在多账号超鬼王选择此处理器，其他调用方保持默认。"""

    login_service_type = RotationRetryLoginService
