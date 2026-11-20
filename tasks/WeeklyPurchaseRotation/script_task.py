from datetime import datetime, timedelta
from pathlib import Path
import time

from module.config.utils import read_file, write_file
from module.exception import RequestHumanTakeover, TaskEnd
from module.logger import logger
from module.multi_account.account_manager import AccountManager
from module.multi_account.daily_task_archive import refresh_weekly_purchase_index
from tasks.AccountRotation.config import RotationFailurePolicy
from tasks.AccountRotation.script_task import RotationAccountSwitcher
from tasks.GameUi.page import page_main
from tasks.StoryRotation.state import StoryState
from tasks.WeeklyPurchase.script_task import ScriptTask as WeeklyPurchaseTask


class ScriptTask(WeeklyPurchaseTask):
    task_name = "WeeklyPurchaseRotation"

    @staticmethod
    def _week_start(now):
        monday = (now - timedelta(days=now.weekday())).replace(hour=9, minute=0, second=0, microsecond=0)
        return monday if now >= monday else monday - timedelta(days=7)

    def _confirm_courtyard(self):
        if not self.goto_page(page_main):
            raise RequestHumanTakeover("每周购买后无法返回庭院")
        confirmed = 0
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.screenshot()
            if (self.match_page_once(page_main)
                    and not self.appear(self.I_UI_BACK_RED)
                    and not self.appear(self.I_AD_CLOSE_RED)):
                confirmed += 1
                if confirmed >= 2:
                    return
            else:
                confirmed = 0
            time.sleep(0.5)
        raise RequestHumanTakeover("每周购买后未能稳定确认庭院")

    def run(self):
        settings = self.config.account_rotation.account_rotation_config
        manager = AccountManager(self.config.config_name, self.config.multi_account_evo,
                                 order=settings.account_order, enabled=settings.enabled_accounts)
        accounts = manager.get_enabled_accounts()
        if not accounts:
            raise RequestHumanTakeover("每周账号轮换购买没有资料完整的启用账号")
        instance = str(self.config.config_name).lower()
        if not instance or any(char in instance for char in '/\\.:'):
            raise RequestHumanTakeover("每周购买进度的实例名无效")
        path = Path.cwd() / "config" / f".weekly_purchase_rotation_{instance}.json"
        state = read_file(str(path)) if path.exists() else {"version": 1, "weeks": {}}
        if (not isinstance(state, dict) or state.get("version") != 1
                or not isinstance(state.get("weeks"), dict)
                or any(not isinstance(value, dict) for value in state["weeks"].values())):
            raise RequestHumanTakeover("每周购买进度格式无效，请检查原文件")
        week_start = self._week_start(datetime.now())
        week_key = week_start.isoformat(timespec="seconds")
        week = state["weeks"].setdefault(week_key, {})
        switcher = RotationAccountSwitcher(
            self.config, self.device, max_attempts=settings.max_switch_attempts,
            retry_delay=settings.retry_delay_seconds, timeout=settings.switch_timeout_seconds,
            fast=True,
        )
        failed = False
        for account in accounts:
            if self._week_start(datetime.now()) != week_start:
                break
            identity = StoryState.identity(account)
            if week.get(identity) == "completed":
                logger.info("[WeeklyPurchaseRotation] 本周已完成 account_id=%s", account.account_id)
                continue
            result = switcher.ensure_account(account)
            if not result.success:
                logger.error("[WeeklyPurchaseRotation] 切号失败 account_id=%s code=%s",
                             account.account_id, result.error_code.value)
                failed = True
                if settings.failure_policy == RotationFailurePolicy.STOP:
                    raise RequestHumanTakeover(f"每周购买切号失败 account_id={account.account_id}")
                continue
            week[identity] = "running"
            write_file(str(path), state)
            refresh_weekly_purchase_index(Path.cwd() / "log" / "dailytask")
            logger.info("[WeeklyPurchaseRotation] 开始购买 account_id=%s", account.account_id)
            con = self.config.weekly_purchase
            self.execute_tt(con.thousand_things)
            self.execute_shrine(con.shrine)
            self.execute_guild(con.guild_store)
            self.execute_mall()
            self._confirm_courtyard()
            week[identity] = "completed"
            write_file(str(path), state)
            refresh_weekly_purchase_index(Path.cwd() / "log" / "dailytask")
            logger.info("[WeeklyPurchaseRotation] 本周购买流程完成 account_id=%s", account.account_id)
        next_week = week_start + timedelta(days=7)
        now = datetime.now()
        if next_week <= now:
            target = now + timedelta(seconds=1)
        elif failed:
            target = min(now + timedelta(days=1), next_week)
        else:
            target = next_week
        self.set_next_run(self.task_name, target=target, server=False)
        raise TaskEnd(self.task_name)
