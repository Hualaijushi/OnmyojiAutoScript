from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from module.logger import logger
from module.multi_account.account_manager import AccountManager
from module.multi_account.account_switcher import AccountSwitcher, SwitchResult
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.daily_task_report import sync_account_result, write_markdown


@dataclass(slots=True)
class RotationSummary:
    instance: str
    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    daily_failed: dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return not self.failed


@dataclass(frozen=True, slots=True)
class DailyTaskOutcome:
    """每日任务适配器返回的执行结果及可选展示结果。"""

    success: bool
    result: str = ""
    skipped: bool = False
    failed_task: str = ""
    error: str = ""


class AccountRotationRunner:
    """切换并验证账号，并按配置执行每日任务列表。"""

    def __init__(
        self,
        manager: AccountManager,
        switcher: AccountSwitcher,
        state: DailyStateManager,
        *,
        skip_completed_today: bool = True,
        continue_on_failure: bool = True,
        group_barrier=None,
        daily_tasks: tuple[str, ...] = (),
        task_runner: Callable[[str], bool | None | DailyTaskOutcome] | None = None,
        daily_task_runnable: Callable[[object], bool] | None = None,
        task_runner_with_account: Callable[[str, object], bool | None | DailyTaskOutcome] | None = None,
        daily_task_due: Callable[[str, datetime], bool] | None = None,
    ) -> None:
        self.manager = manager
        self.switcher = switcher
        self.state = state
        self.skip_completed_today = skip_completed_today
        self.continue_on_failure = continue_on_failure
        self.group_barrier = group_barrier
        self.daily_tasks = tuple(daily_tasks)
        self.task_runner = task_runner
        self.daily_task_runnable = daily_task_runnable
        self.task_runner_with_account = task_runner_with_account
        self.daily_task_due = daily_task_due

    def _task_should_run(self, account, task_name: str, now: datetime | None = None) -> bool:
        """判断独立每日任务是否仍可执行且已到重试时间。"""
        now = now or datetime.now()
        # 任务过了当前时间窗口后不再执行，也不再消费失败重试状态。
        if self.daily_task_due is not None and not self.daily_task_due(task_name, now):
            return False
        task = (
            self.state.get_account_state(account.account_id, account.instance)
            .get("tasks", {})
            .get(task_name, {})
            or {}
        )
        status = str(task.get("status", "pending"))
        if status in {"completed", "skipped"}:
            return False
        if status != "failed":
            return True
        if int(task.get("attempts", 0) or 0) >= 3:
            return False
        try:
            retry_at = datetime.fromisoformat(str(task.get("retry_at", "")))
        except (TypeError, ValueError):
            return True
        return now >= retry_at

    def _account_completed_today(self, account) -> bool:
        if not self.daily_tasks:
            return self.state.login_status(account.instance, account.account_id) == "completed"
        for task_name in self.daily_tasks:
            if task_name == "DailyTrifles" and self.daily_task_runnable is not None:
                # DailyTrifles 内部按时段拆分，不能再使用聚合状态判断全天完成。
                if self.daily_task_runnable(account):
                    return False
                continue
            if self._task_should_run(account, task_name):
                return False
        return True

    def _run_daily_tasks(self, account, summary: RotationSummary) -> bool:
        if not self.daily_tasks:
            return True
        if self.task_runner is None and self.task_runner_with_account is None:
            raise RuntimeError("daily_tasks configured without a task_runner")
        # 此汇总标记与多账号组队觉醒使用的任务/队伍状态独立，
        # 仅表示当前模拟器的当前账号是否完成当天配置的每日轮换。
        self.state.mark_daily_task_completed(account.instance, account.account_id, False)
        account_has_failed = False
        for task_name in self.daily_tasks:
            if task_name == "DailyTrifles" and self.daily_task_runnable is not None:
                # 聚合状态只保留兼容用途，实际执行仍以当前可运行的子任务为准。
                if not self.daily_task_runnable(account):
                    logger.info(
                        "[Account] instance=%s account_id=%s task=%s skip=no_runnable_subtask",
                        account.instance,
                        account.account_id,
                        task_name,
                    )
                    continue
            elif not self._task_should_run(account, task_name):
                logger.info(
                    "[Account] instance=%s account_id=%s task=%s skip=completed_or_retry_wait",
                    account.instance,
                    account.account_id,
                    task_name,
                )
                continue
            self.state.mark_task(account.instance, account.account_id, task_name, "running")
            try:
                if self.task_runner_with_account is not None:
                    task_result = self.task_runner_with_account(task_name, account)
                else:
                    task_result = self.task_runner(task_name)
            except Exception as exc:
                success = False
                error = f"{type(exc).__name__}: {exc}".strip()
                task_skipped = False
                task_result_value = ""
                failed_task = ""
            else:
                if isinstance(task_result, DailyTaskOutcome):
                    task_skipped = task_result.skipped
                    success = task_result.success and not task_skipped
                    task_result_value = task_result.result
                    failed_task = task_result.failed_task
                    error = task_result.error or "task returned false"
                else:
                    task_skipped = task_result is None
                    success = not task_skipped and bool(task_result)
                    task_result_value = ""
                    failed_task = ""
                    error = "task returned false"
            if task_skipped:
                self.state.mark_task(account.instance, account.account_id, task_name, "skipped")
                logger.info(
                    "[Account] instance=%s account_id=%s task=%s skipped=not_applicable",
                    account.instance,
                    account.account_id,
                    task_name,
                )
                continue
            if not success:
                self.state.mark_task(account.instance, account.account_id, task_name, "failed", error=error)
                # 每日任务失败只记录在独立字段中，不视为账号切换失败。
                # 这样不会让本轮轮换或下一次调度以错误状态结束。
                summary.daily_failed[account.account_id] = f"task:{task_name}"
                logger.error(
                    "[Account] instance=%s account_id=%s task=%s failed=%s",
                    account.instance,
                    account.account_id,
                    task_name,
                    error,
                )
                sync_account_result(
                    self.state,
                    Path.cwd() / "config",
                    account.instance,
                    account.account_id,
                    False,
                    error=error,
                    failed_task=failed_task,
                )
                account_has_failed = True
                continue
            self.state.mark_task(
                account.instance,
                account.account_id,
                task_name,
                "completed",
                result=task_result_value,
            )
            logger.info(
                "[Account] instance=%s account_id=%s task=%s completed",
                account.instance,
                account.account_id,
                task_name,
            )
        self.state.mark_daily_task_completed(
            account.instance,
            account.account_id,
            not account_has_failed,
        )
        logger.info(
            "[每日任务结果] 实例=%s 账号=%s 结果=%s 任务=%s",
            account.instance,
            account.account_id,
            "部分失败" if account_has_failed else "完成",
            ",".join(self.daily_tasks),
        )
        sync_account_result(
            self.state,
            Path.cwd() / "config",
            account.instance,
            account.account_id,
            True,
        )
        return not account_has_failed

    def run(self) -> RotationSummary:
        summary = RotationSummary(self.manager.instance)
        for index, account in enumerate(self.manager.get_accounts_for_instance(enabled_only=True)):
            if self.group_barrier is not None:
                self.group_barrier.wait_for_previous_group(index)
            if self.skip_completed_today and self._account_completed_today(account):
                skip_reason = "no_runnable_daily_task" if (
                    "DailyTrifles" in self.daily_tasks and self.daily_task_runnable is not None
                ) else "completed_today"
                logger.info(
                    "[Account] instance=%s account_id=%s skip=%s",
                    account.instance,
                    account.account_id,
                    skip_reason,
                )
                logger.info(
                    "[每日任务结果] 实例=%s 账号=%s 结果=跳过 原因=%s",
                    account.instance,
                    account.account_id,
                    skip_reason,
                )
                if self.daily_tasks:
                    write_markdown(self.state, Path.cwd() / "config")
                summary.skipped.append(account.account_id)
                continue
            self.state.mark_login(account.instance, account.account_id, "running")
            result: SwitchResult = self.switcher.ensure_account(account)
            if result.success:
                self.state.mark_login(account.instance, account.account_id, "completed")
                logger.info("[Account] instance=%s account_id=%s login=completed changed=%s", account.instance, account.account_id, result.changed)
                if not self._run_daily_tasks(account, summary):
                    if not self.continue_on_failure:
                        break
                    continue
                summary.completed.append(account.account_id)
                continue
            error = f"{result.error_code.value}: {result.message}".strip()
            self.state.mark_login(account.instance, account.account_id, "failed", error=error)
            summary.failed[account.account_id] = result.error_code.value
            logger.error("[Account] instance=%s account_id=%s login=failed code=%s", account.instance, account.account_id, result.error_code.value)
            if not self.continue_on_failure:
                break
        return summary
