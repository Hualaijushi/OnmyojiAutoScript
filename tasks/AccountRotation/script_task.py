from __future__ import annotations

import json
from pathlib import Path

from module.exception import RequestHumanTakeover, TaskEnd
from module.multi_account.account_manager import AccountManager
from module.multi_account.account_switcher import AccountSwitcher
from module.multi_account.coordinator import SharedOcrCoordinator, ThreeInstanceGroupBarrier
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from module.multi_account.daily_state import DailyStateManager
from module.multi_account.rotation_runner import AccountRotationRunner
from tasks.AccountRotation.config import RotationFailurePolicy
from tasks.base_task import BaseTask


class ScriptTask(BaseTask, CourtyardCharacterVerifierMixin):
    task_name = "AccountRotation"

    @staticmethod
    def _validate_three_instance_configs() -> None:
        signatures = {}
        for instance in ("oas3", "oas4", "oas5"):
            path = Path.cwd() / "config" / f"{instance}.json"
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"cannot read three-instance config {instance}: {exc}") from exc
            task = data.get("account_rotation", {})
            scheduler = task.get("scheduler", {})
            settings = task.get("account_rotation_config", {})
            if not scheduler.get("enable", False):
                raise ValueError(f"three-instance coordination requires AccountRotation enabled on {instance}")
            if not settings.get("three_instance_coordination", False):
                raise ValueError(f"three-instance coordination is disabled on {instance}")
            signatures[instance] = (
                str(settings.get("account_order", "")),
                str(settings.get("enabled_accounts", "")),
            )
        if len(set(signatures.values())) != 1:
            raise ValueError("oas3/oas4/oas5 AccountRotation order and enabled accounts must match")

    def run(self) -> None:
        settings = self.config.account_rotation.account_rotation_config
        manager = AccountManager(
            self.config.config_name,
            self.config.multi_account_evo,
            order=settings.account_order,
            enabled=settings.enabled_accounts,
        )
        if not manager.get_accounts_for_instance(enabled_only=True):
            raise RequestHumanTakeover("AccountRotation: no complete enabled accounts")
        state = DailyStateManager(
            Path.cwd() / "config",
            recover_instances={str(self.config.config_name).lower()},
        )
        ocr_coordinator = None
        group_barrier = None
        if settings.three_instance_coordination:
            self._validate_three_instance_configs()
            ocr_coordinator = SharedOcrCoordinator(
                Path.cwd() / "config",
                self.config.config_name,
                acquire_timeout=settings.ocr_acquire_timeout_seconds,
                lease_timeout=settings.ocr_lease_timeout_seconds,
            )
            positions = [account.position for account in manager.get_accounts_for_instance(enabled_only=True)]
            group_barrier = ThreeInstanceGroupBarrier(
                state,
                positions,
                timeout=settings.coordination_timeout_seconds,
            )
        switcher = self._build_switcher(settings, ocr_coordinator)
        summary = AccountRotationRunner(
            manager,
            switcher,
            state,
            skip_completed_today=settings.skip_completed_today,
            continue_on_failure=settings.failure_policy == RotationFailurePolicy.CONTINUE,
            group_barrier=group_barrier,
        ).run()
        if summary.failed:
            self.set_next_run(self.task_name, finish=False, success=False)
            raise RequestHumanTakeover(
                f"AccountRotation: {len(summary.failed)} account(s) failed; see redacted account_id logs"
            )
        self.set_next_run(self.task_name, finish=True, success=True)
        raise TaskEnd(self.task_name)

    def _build_switcher(self, settings, ocr_coordinator) -> AccountSwitcher:
        """Build the account switcher with the fast login path enabled.

        The fast path uses fixed-coordinate platform clicks and skips
        server/character OCR, and the shared courtyard verifier keeps the
        "switch success" contract identical to MultiAccountEvo: the account
        must reach the courtyard with the expected top-left character.
        """
        return AccountSwitcher(
            self.config,
            self.device,
            max_attempts=settings.max_switch_attempts,
            retry_delay=settings.retry_delay_seconds,
            timeout=settings.switch_timeout_seconds,
            ocr_coordinator=ocr_coordinator,
            fast=True,
            home_verifier=self._verify_courtyard_character,
        )
