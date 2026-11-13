"""独立的多账号超鬼王轮换入口。"""

from pathlib import Path
from datetime import datetime

from module.exception import RequestHumanTakeover, TaskEnd
from module.logger import logger
from tasks.AccountRotation.script_task import RotationAccountSwitcher
from tasks.base_task import BaseTask
from tasks.MetaDemonRotation.accounts import accounts_for_range
from tasks.MetaDemonRotation.driver import RotationDriver
from tasks.MetaDemonRotation.progress import RotationProgress
from tasks.MetaDemonRotation.rotation import run_rotation


def fatigue_retry_only(results, total: int) -> bool:
    """只对整轮完成遍历且未完成原因均为疲劳设置疲劳等待。"""
    unfinished = [item for item in results if not item.completed]
    return len(results) == total and bool(unfinished) and all(item.reason == '疲劳不足' for item in unfinished)


class ScriptTask(BaseTask):
    task_name = 'MetaDemonRotation'

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
        progress = RotationProgress(Path.cwd() / 'config', self.config.config_name)
        results = run_rotation(accounts, switcher, progress,
                               lambda account: RotationDriver(self.config, self.device),
                               rental_team=conf.rental_team, battle_limit=conf.battle_limit)
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
