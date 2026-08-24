from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta

from module.exception import RequestHumanTakeover, TaskEnd
from module.base.utils import load_module
from module.logger import logger
from module.multi_account.account_manager import AccountManager
from module.multi_account.account_switcher import AccountSwitcher
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.daily_task_schedule import is_daily_task_due
from module.multi_account.rotation_runner import AccountRotationRunner, DailyTaskOutcome
from tasks.AccountRotation.config import RotationFailurePolicy
from tasks.DailyTrifles.config import DailyGuildDonate, DailyTriflesConfig, DoneRecord
from tasks.base_task import BaseTask


_DAILY_TASK_MAX_RETRY = 3


class ScriptTask(BaseTask, CourtyardCharacterVerifierMixin):
    task_name = "AccountRotation"

    def _run_daily_task(self, task_name: str, account=None) -> bool | None | DailyTaskOutcome:
        if task_name not in {
            "DailyTrifles",
            "hunt_kirin",
            "hunt_netherworld",
            "cooperation_morning",
            "cooperation_evening",
        }:
            logger.error("[AccountRotation] unsupported daily task=%s", task_name)
            return False
        task_module_name = "DailyTrifles"
        path = Path.cwd() / "tasks" / task_module_name / "script_task.py"
        logger.info("[AccountRotation] run daily task=%s", task_name)
        task = None
        try:
            daily_settings = self.config.account_rotation.daily_task_config
            runtime_config = self.config.model_copy(deep=True)
            courtyard_affairs = daily_settings.daily_courtyard_affairs
            courtyard_morning = daily_settings.daily_courtyard_morning
            courtyard_evening = daily_settings.daily_courtyard_evening
            pickup_email = daily_settings.daily_pickup_email
            one_summon = daily_settings.daily_one_summon
            luck_msg = daily_settings.daily_luck_msg
            store_sign = daily_settings.daily_store_sign
            buy_sushi_count = daily_settings.daily_buy_sushi_count
            guild_donate_enable = daily_settings.daily_guild_donate_enable
            guild_medal_donate = daily_settings.daily_guild_medal_donate
            if task_name == "DailyTrifles" and account is not None and hasattr(self, "_rotation_state"):
                account_state = self._rotation_state.get_account_state(account.account_id, account.instance)
                task_nodes = account_state.get("tasks", {}) or {}
                courtyard_affairs = False
                now = datetime.now()

                def pending(task_id: str) -> bool:
                    node = task_nodes.get(task_id, {}) or {}
                    status = str(node.get("status", "pending"))
                    if status in {"completed", "skipped"}:
                        return False
                    if status != "failed":
                        return True
                    if int(node.get("attempts", 0) or 0) >= _DAILY_TASK_MAX_RETRY:
                        return False
                    try:
                        retry_at = datetime.fromisoformat(str(node.get("retry_at", "")))
                    except (TypeError, ValueError):
                        return True
                    return now >= retry_at

                courtyard_morning = (
                    (daily_settings.daily_courtyard_affairs or daily_settings.daily_courtyard_morning)
                    and pending("courtyard_morning")
                    and self._daily_task_is_due("courtyard_morning", now)
                )
                courtyard_evening = (
                    (daily_settings.daily_courtyard_affairs or daily_settings.daily_courtyard_evening)
                    and pending("courtyard_evening")
                    and self._daily_task_is_due("courtyard_evening", now)
                )
                pickup_email = daily_settings.daily_pickup_email and pending("pickup_email")
                one_summon = daily_settings.daily_one_summon and pending("summon")
                luck_msg = daily_settings.daily_luck_msg and pending("luck_msg")
                guild_donate_enable = daily_settings.daily_guild_donate_enable and pending("guild_donate")
                store_sign = daily_settings.daily_store_sign and pending("store_sign")
                buy_sushi_count = (
                    daily_settings.daily_buy_sushi_count
                    if daily_settings.daily_buy_sushi_count > 0 and pending("buy_sushi")
                    else -1
                )
                guild_medal_donate = daily_settings.daily_guild_medal_donate and pending("guild_medal_donate")
            runtime_config.daily_trifles.trifles_config = DailyTriflesConfig(
                courtyard_affairs=courtyard_affairs,
                courtyard_morning=courtyard_morning,
                courtyard_evening=courtyard_evening,
                pickup_email=pickup_email,
                one_summon=one_summon,
                summon_type=daily_settings.daily_summon_type,
                draw_mystery_pattern=daily_settings.daily_draw_mystery_pattern,
                luck_msg=luck_msg,
                store_sign=store_sign,
                buy_sushi_count=buy_sushi_count,
                guild_medal_donate=guild_medal_donate,
                guild_medal_amount=daily_settings.daily_guild_medal_amount,
                hunt_kirin=task_name == "hunt_kirin",
                hunt_netherworld=task_name == "hunt_netherworld",
                cooperation_morning=task_name == "cooperation_morning",
                cooperation_evening=task_name == "cooperation_evening",
            )
            runtime_config.daily_trifles.guild_donate = DailyGuildDonate(
                enable=guild_donate_enable,
                auto_get_rewards=daily_settings.daily_guild_auto_get_rewards,
                notify_enable=daily_settings.daily_guild_notify_enable,
                guild_member_list=daily_settings.daily_guild_member_list,
                friend_list=daily_settings.daily_guild_friend_list,
                name_check=daily_settings.daily_guild_name_check,
            )
            # 账号轮换状态是每个账号的唯一依据。
            # 清空每日琐事的全局完成记录，避免前一个账号影响本模拟器的下一个账号。
            runtime_config.daily_trifles.done_record = DoneRecord()
            module = load_module(f"account_rotation_{task_module_name}_script_task", str(path))
            task = module.ScriptTask(config=runtime_config, device=self.device)
            if task_name in {"hunt_kirin", "hunt_netherworld"}:
                result = task.run_hunt_rotation(task_name)
            elif task_name in {"cooperation_morning", "cooperation_evening"}:
                result = task.run_cooperation_rotation()
            else:
                result = task.run()

            if result is None:
                return None
            if isinstance(result, DailyTaskOutcome):
                return result
        except TaskEnd:
            return True
        except Exception as exc:
            logger.exception("[AccountRotation] daily task failed: %s", task_name)
            failed_task = str(getattr(task, "_active_daily_subtask", "") or "")
            return DailyTaskOutcome(
                success=False,
                failed_task=failed_task,
                error=f"{type(exc).__name__}: {exc}".strip(),
            )
        return result is not False

    @staticmethod
    def _daily_task_is_due(task_name: str, now: datetime) -> bool:
        return is_daily_task_due(task_name, now)

    @staticmethod
    def _daily_trifles_task_names(daily_settings) -> tuple[str, ...]:
        """根据账号轮换配置得到 DailyTrifles 的独立子任务列表。"""
        task_names: list[str] = []
        if daily_settings.daily_courtyard_affairs or daily_settings.daily_courtyard_morning:
            task_names.append("courtyard_morning")
        if daily_settings.daily_courtyard_affairs or daily_settings.daily_courtyard_evening:
            task_names.append("courtyard_evening")
        if daily_settings.daily_pickup_email:
            task_names.append("pickup_email")
        if daily_settings.daily_guild_donate_enable:
            task_names.append("guild_donate")
        if daily_settings.daily_guild_medal_donate:
            task_names.append("guild_medal_donate")
        if daily_settings.daily_luck_msg:
            task_names.append("luck_msg")
        if daily_settings.daily_store_sign:
            task_names.append("store_sign")
        if daily_settings.daily_buy_sushi_count > 0:
            task_names.append("buy_sushi")
        if daily_settings.daily_one_summon:
            task_names.append("summon")
        return tuple(task_names)

    def _has_runnable_daily_trifles(self, state: DailyStateManager, account, now: datetime | None = None) -> bool:
        """只依据当前可执行的 DailyTrifles 子任务决定是否需要登录。"""
        now = now or datetime.now()
        daily_settings = self.config.account_rotation.daily_task_config
        task_names = self._daily_trifles_task_names(daily_settings)

        account_state = state.get_account_state(account.account_id, account.instance)
        task_nodes = account_state.get("tasks", {}) or {}
        for task_name in task_names:
            task = task_nodes.get(task_name, {}) or {}
            status = str(task.get("status", "pending"))
            if status in {"completed", "skipped"}:
                continue
            if status == "failed" and int(task.get("attempts", 0) or 0) >= 3:
                continue
            if status == "failed":
                try:
                    retry_at = datetime.fromisoformat(str(task.get("retry_at", "")))
                except (TypeError, ValueError):
                    retry_at = None
                if retry_at is not None and now < retry_at:
                    continue
            if self._daily_task_is_due(task_name, now):
                return True
        return False

    @staticmethod
    def _next_daily_task_window(daily_settings, now: datetime) -> datetime | None:
        """计算已配置时段任务的下一次开始时间，避免成功间隔错过晚间任务。"""
        candidates: list[datetime] = []
        morning_enabled = (
            daily_settings.daily_courtyard_affairs
            or daily_settings.daily_courtyard_morning
            or daily_settings.daily_cooperation_morning
        )
        evening_enabled = (
            daily_settings.daily_courtyard_affairs
            or daily_settings.daily_courtyard_evening
            or daily_settings.daily_cooperation_evening
        )
        if morning_enabled:
            target = now.replace(hour=5, minute=0, second=0, microsecond=0)
            candidates.append(target if target > now else target + timedelta(days=1))
        if evening_enabled:
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            candidates.append(target if target > now else target + timedelta(days=1))

        if daily_settings.daily_hunt_kirin or daily_settings.daily_hunt_netherworld:
            for offset in range(8):
                day = now + timedelta(days=offset)
                if daily_settings.daily_hunt_kirin and day.weekday() <= 3:
                    target = day.replace(hour=6, minute=0, second=0, microsecond=0)
                    if target > now:
                        candidates.append(target)
                if daily_settings.daily_hunt_netherworld and day.weekday() >= 4:
                    target = day.replace(hour=18, minute=0, second=0, microsecond=0)
                    if target > now:
                        candidates.append(target)
        return min(candidates) if candidates else None

    def _next_daily_task_retry(
        self,
        state: DailyStateManager,
        daily_settings,
        now: datetime,
    ) -> datetime | None:
        """返回当前实例仍处于有效时间窗口内的最近重试时间。"""
        configured = set(self._daily_trifles_task_names(daily_settings))
        if daily_settings.daily_hunt_kirin:
            configured.add("hunt_kirin")
        if daily_settings.daily_hunt_netherworld:
            configured.add("hunt_netherworld")
        if daily_settings.daily_cooperation_morning:
            configured.add("cooperation_morning")
        if daily_settings.daily_cooperation_evening:
            configured.add("cooperation_evening")

        candidates: list[datetime] = []
        current = state.load_today()
        instance = str(self.config.config_name).lower()
        accounts = current.get("instances", {}).get(instance, {}).get("accounts", {}) or {}
        for account in accounts.values():
            for task_name, task in (account.get("tasks", {}) or {}).items():
                if task_name not in configured or task.get("status") != "failed":
                    continue
                if int(task.get("attempts", 0) or 0) >= _DAILY_TASK_MAX_RETRY:
                    continue
                try:
                    retry_at = datetime.fromisoformat(str(task.get("retry_at", "")))
                except (TypeError, ValueError):
                    continue
                # 重试时刻和当前时刻都必须处于任务窗口内，过期时段不再补跑。
                if (
                    retry_at.date() != now.date()
                    or not self._daily_task_is_due(task_name, retry_at)
                    or not self._daily_task_is_due(task_name, now)
                ):
                    continue
                candidates.append(max(retry_at, now))
        return min(candidates) if candidates else None

    def _delay_after_rotation_interruption(self) -> None:
        """轮换基础异常后推迟调度，避免进程重启形成高频循环。"""
        retry_target = datetime.now() + timedelta(minutes=10)
        logger.exception(
            "[AccountRotation] rotation interrupted; scheduler delayed until %s",
            retry_target,
        )
        try:
            self.set_next_run(self.task_name, target=retry_target)
        except Exception:
            logger.exception("[AccountRotation] failed to delay scheduler after interruption")

    def run(self) -> None:
        settings = self.config.account_rotation.account_rotation_config
        daily_task_mode = self.config.account_rotation.daily_task_config.daily_task_enable
        daily_settings = self.config.account_rotation.daily_task_config
        daily_tasks = ()
        if daily_task_mode:
            ordinary_enabled = any(
                (
                    daily_settings.daily_courtyard_affairs,
                    daily_settings.daily_courtyard_morning,
                    daily_settings.daily_courtyard_evening,
                    daily_settings.daily_pickup_email,
                    daily_settings.daily_one_summon,
                    daily_settings.daily_luck_msg,
                    daily_settings.daily_store_sign,
                    daily_settings.daily_buy_sushi_count > 0,
                    daily_settings.daily_guild_donate_enable,
                    daily_settings.daily_guild_medal_donate,
                )
            )
            daily_tasks = ("DailyTrifles",) if ordinary_enabled else ()
            selected_hunt_tasks = []
            if daily_settings.daily_hunt_kirin:
                selected_hunt_tasks.append("hunt_kirin")
            if daily_settings.daily_hunt_netherworld:
                selected_hunt_tasks.append("hunt_netherworld")
            selected_cooperation_tasks = []
            if daily_settings.daily_cooperation_morning:
                selected_cooperation_tasks.append("cooperation_morning")
            if daily_settings.daily_cooperation_evening:
                selected_cooperation_tasks.append("cooperation_evening")
            now = datetime.now()
            daily_tasks += tuple(
                task_name
                for task_name in (*selected_hunt_tasks, *selected_cooperation_tasks)
                if self._daily_task_is_due(task_name, now)
            )
            configured_rotation_tasks = (*selected_hunt_tasks, *selected_cooperation_tasks)
            if not daily_tasks and not ordinary_enabled and configured_rotation_tasks:
                next_window = self._next_daily_task_window(daily_settings, now)
                if next_window is None:
                    next_window = now + timedelta(days=1)
                logger.info("当前没有到执行时间的每日轮换任务，跳过登录，下一时间=%s", next_window)
                self.set_next_run(self.task_name, target=next_window)
                raise TaskEnd(self.task_name)
        manager = AccountManager(
            self.config.config_name,
            self.config.multi_account_evo,
            order=settings.account_order,
            enabled=settings.enabled_accounts,
        )
        if not manager.get_accounts_for_instance(enabled_only=True):
            raise RequestHumanTakeover("AccountRotation: no complete enabled accounts")
        try:
            state = DailyStateManager(
                Path.cwd() / "config",
                recover_instances={str(self.config.config_name).lower()},
            )
        except Exception:
            self._delay_after_rotation_interruption()
            raise
        self._rotation_state = state
        # 账号轮换始终按模拟器独立执行，三实例同步仅由多账号组队觉醒使用。
        logger.info("[AccountRotation] independent emulator rotation; cross-instance coordination disabled")
        # 账号轮换只需要账号切换模块已有的登录/账号确认。
        # 角色名校验保留给多账号组队觉醒，每日任务记录不依赖角色名。
        switcher = self._build_switcher(settings, None, verify_character=False)
        try:
            summary = AccountRotationRunner(
                manager,
                switcher,
                state,
                skip_completed_today=settings.skip_completed_today,
                continue_on_failure=settings.failure_policy == RotationFailurePolicy.CONTINUE,
                group_barrier=None,
                daily_tasks=daily_tasks,
                task_runner=self._run_daily_task,
                daily_task_runnable=lambda account: self._has_runnable_daily_trifles(state, account),
                task_runner_with_account=self._run_daily_task,
                daily_task_due=self._daily_task_is_due,
            ).run()
        except Exception:
            # 状态写入等基础异常不能让外部进程重启后立即重复撞错。
            self._delay_after_rotation_interruption()
            raise
        if summary.daily_failed:
            logger.warning(
                "[AccountRotation] %s account(s) daily task failed; recorded and ignored for scheduler status",
                len(summary.daily_failed),
            )
        if summary.failed:
            if not daily_task_mode or settings.failure_policy != RotationFailurePolicy.CONTINUE:
                self.set_next_run(self.task_name, finish=False, success=False)
                raise RequestHumanTakeover(
                    f"AccountRotation: {len(summary.failed)} account(s) failed; see redacted account_id logs"
                )
            # 每日轮换以完成后续账号为优先，登录失败保留在状态和日志中，不终止 OAS。
            logger.warning(
                "[AccountRotation] %s account(s) login failed; recorded and ignored for scheduler status",
                len(summary.failed),
            )
        now = datetime.now()
        next_window = self._next_daily_task_window(daily_settings, now)
        retry_at = self._next_daily_task_retry(state, daily_settings, now)
        if retry_at is not None:
            next_window = min(next_window, retry_at) if next_window is not None else retry_at
        if next_window is not None:
            self.set_next_run(self.task_name, target=next_window)
        else:
            self.set_next_run(self.task_name, finish=True, success=True)
        raise TaskEnd(self.task_name)

    def _build_switcher(self, settings, ocr_coordinator, *, verify_character: bool = True) -> AccountSwitcher:
        """构建启用快速登录路径的账号切换器。

        快速路径使用固定坐标选择登录平台并跳过服务器/角色 OCR。
        账号轮换按实例和账号 ID 记录每日完成状态，角色名校验仅由多账号组队觉醒启用。
        """
        return AccountSwitcher(
            self.config,
            self.device,
            max_attempts=settings.max_switch_attempts,
            retry_delay=settings.retry_delay_seconds,
            timeout=settings.switch_timeout_seconds,
            ocr_coordinator=ocr_coordinator,
            fast=True,
            home_verifier=self._verify_courtyard_character if verify_character else None,
        )
