"""独立的多账号超鬼王轮换入口。"""

from pathlib import Path
from datetime import datetime
import time

from module.exception import RequestHumanTakeover, TaskEnd
from module.logger import logger
from module.multi_account.account_switcher import AccountSwitcher
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from tasks.AccountRotation.script_task import RotationAccountSwitcher
from tasks.base_task import BaseTask
from tasks.GameUi.navigator import GameUi
from tasks.GameUi.nonbattle_recovery import ensure_nonbattle_frame
from tasks.MetaDemon import page as meta_pages
from tasks.MetaDemonRotation.accounts import accounts_for_range
from tasks.MetaDemonRotation.driver import RotationDriver
from tasks.MetaDemonRotation.progress import RotationProgress
from tasks.MetaDemonRotation.rotation import run_rotation
from tasks.Restart.script_task import ScriptTask as RestartTask


def fatigue_retry_only(results, total: int) -> bool:
    """只对整轮完成遍历且未完成原因均为疲劳设置疲劳等待。"""
    unfinished = [item for item in results if not item.completed]
    return len(results) == total and bool(unfinished) and all(item.reason == '疲劳不足' for item in unfinished)


class _RecoveryVerifier(GameUi, CourtyardCharacterVerifierMixin):
    """使用现有庭院导航与角色核对，不能依赖切号器缓存。"""


class _CourtyardResumeVerifier(_RecoveryVerifier):
    """续刷时识别超鬼王页面，复用活动首领到庭院的既有返回路径。"""

    def _infer_task_category(self):
        return meta_pages.page_meta_demon_boss.category


class ScriptTask(BaseTask):
    task_name = 'MetaDemonRotation'

    def _resume_account_from_courtyard(self, account):
        """只为旧战斗记录核对庭院；不重启游戏、不主动切换账号。"""
        verifier = _CourtyardResumeVerifier(self.config, self.device)
        screenshot = verifier.screenshot
        deadline = time.monotonic() + 60

        def guarded_screenshot():
            if time.monotonic() >= deadline:
                raise RequestHumanTakeover('庭院续刷核对超时，保留旧战斗标记')
            result = screenshot()
            if time.monotonic() >= deadline:
                raise RequestHumanTakeover('庭院续刷核对超时，保留旧战斗标记')
            # 导航与角色核对每次取新帧都排除战斗、结算及登录等受保护页面。
            ensure_nonbattle_frame(verifier)
            return result

        verifier.screenshot = guarded_screenshot
        try:
            verifier.screenshot()
            return verifier._verify_courtyard_character(account) is True
        finally:
            del verifier.screenshot

    def _recover_account(self, account):
        restart = RestartTask(self.config, self.device)
        restart.expected_account = account
        restart.app_restart()
        verifier = _RecoveryVerifier(self.config, self.device)
        switcher = AccountSwitcher(self.config, self.device, max_attempts=1, fast=True,
                                   home_verifier=verifier._verify_courtyard_character)
        return switcher.ensure_account(account).success

    def run(self):
        settings = self.config.account_rotation.account_rotation_config
        conf = self.config.meta_demon_rotation.rotation_settings
        accounts = accounts_for_range(self.config.config_name, self.config.multi_account_evo,
                                      conf.account_start, conf.account_end)
        if not accounts:
            raise RequestHumanTakeover('超鬼王轮换没有可用的启用账号')
        switcher = RotationAccountSwitcher(
            self.config, self.device, max_attempts=settings.max_switch_attempts,
            retry_delay=settings.retry_delay_seconds, timeout=settings.switch_timeout_seconds,
            fast=True, home_verifier=None,
        )
        progress = RotationProgress(Path.cwd() / 'config', self.config.config_name,
                                    reset_generation=conf.reset_generation)
        results = run_rotation(accounts, switcher, progress,
                               lambda account: RotationDriver(self.config, self.device),
                               rental_team=conf.rental_team, battle_limit=conf.battle_limit,
                               recover_account=self._recover_account,
                               resume_account=self._resume_account_from_courtyard)
        for item in results:
            logger.info('[超鬼王轮换] 账号=%s 场次=%s/%s 结果=%s',
                        item.account_id, item.entered if item.entered is not None else '未确认',
                        conf.battle_limit, item.reason)
        if len(results) != len(accounts) or any(not item.completed for item in results):
            if fatigue_retry_only(results, len(accounts)):
                wait = self.config.meta_demon_rotation.rotation_play.fatigue_wait_interval
                self.set_next_run(self.task_name, target=datetime.now() + wait)
            else:
                self.set_next_run(self.task_name, finish=False, success=False)
            raise RequestHumanTakeover('超鬼王轮换存在未完成账号，请查看各账号日志')
        self.set_next_run(self.task_name, finish=True, success=True)
        raise TaskEnd(self.task_name)
