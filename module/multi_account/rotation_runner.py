from __future__ import annotations

from dataclasses import dataclass, field

from module.logger import logger
from module.multi_account.account_manager import AccountManager
from module.multi_account.account_switcher import AccountSwitcher, SwitchResult
from module.multi_account.daily_state import DailyStateManager


@dataclass(slots=True)
class RotationSummary:
    instance: str
    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return not self.failed


class AccountRotationRunner:
    """Switch and verify configured accounts; it runs no gameplay tasks."""

    def __init__(
        self,
        manager: AccountManager,
        switcher: AccountSwitcher,
        state: DailyStateManager,
        *,
        skip_completed_today: bool = True,
        continue_on_failure: bool = True,
        group_barrier=None,
    ) -> None:
        self.manager = manager
        self.switcher = switcher
        self.state = state
        self.skip_completed_today = skip_completed_today
        self.continue_on_failure = continue_on_failure
        self.group_barrier = group_barrier

    def run(self) -> RotationSummary:
        summary = RotationSummary(self.manager.instance)
        for index, account in enumerate(self.manager.get_accounts_for_instance(enabled_only=True)):
            if self.group_barrier is not None:
                self.group_barrier.wait_for_previous_group(index)
            if self.skip_completed_today and self.state.login_status(account.instance, account.account_id) == "completed":
                logger.info("[Account] instance=%s account_id=%s skip=completed_today", account.instance, account.account_id)
                summary.skipped.append(account.account_id)
                continue
            self.state.mark_login(account.instance, account.account_id, "running")
            result: SwitchResult = self.switcher.ensure_account(account)
            if result.success:
                self.state.mark_login(account.instance, account.account_id, "completed")
                summary.completed.append(account.account_id)
                logger.info("[Account] instance=%s account_id=%s login=completed changed=%s", account.instance, account.account_id, result.changed)
                continue
            error = f"{result.error_code.value}: {result.message}".strip()
            self.state.mark_login(account.instance, account.account_id, "failed", error=error)
            summary.failed[account.account_id] = result.error_code.value
            logger.error("[Account] instance=%s account_id=%s login=failed code=%s", account.instance, account.account_id, result.error_code.value)
            if not self.continue_on_failure:
                break
        return summary
