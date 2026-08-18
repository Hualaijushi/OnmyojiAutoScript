from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from module.multi_account.file_lock import (
    InterProcessLockTimeout,
    atomic_replace_with_retry,
    interprocess_file_lock,
)


class DailyStateLockError(TimeoutError):
    pass


class DailyStateManager:
    """Crash-safe, cross-process daily progress store."""

    VALID_STATUSES = {"pending", "running", "completed", "failed", "skipped"}

    def __init__(
        self,
        directory: str | Path,
        *,
        today: Callable[[], date] = date.today,
        lock_timeout: float = 10.0,
        recover_instances: set[str] | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.path = self.directory / ".multi_account_daily_state.json"
        self.lock_path = self.directory / ".multi_account_daily_state.lock"
        self.today = today
        self.lock_timeout = lock_timeout
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._locked():
            state = self._load_unlocked(recover_corrupt=True)
            state = self._roll_date_unlocked(state)
            if self._recover_running(state, recover_instances):
                self._save_unlocked(state)
            elif not self.path.exists():
                self._save_unlocked(state)

    def _new_state(self) -> dict:
        return {
            "date": self.today().isoformat(),
            "updated_at": self._now(),
            "instances": {},
            "teams": {},
        }

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @contextmanager
    def _locked(self):
        try:
            with interprocess_file_lock(self.lock_path, timeout=self.lock_timeout, poll_interval=0.02):
                yield
        except InterProcessLockTimeout as exc:
            raise DailyStateLockError(f"daily state lock timeout: {self.lock_path}") from exc

    def _load_unlocked(self, *, recover_corrupt: bool = False) -> dict:
        if not self.path.exists():
            return self._new_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("instances", {}), dict):
                raise ValueError("invalid daily state structure")
            return data
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if not recover_corrupt:
                raise
            suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{suffix}.json")
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            return self._new_state()

    def _roll_date_unlocked(self, state: dict) -> dict:
        current = self.today().isoformat()
        if state.get("date") == current:
            return state
        previous = str(state.get("date") or "unknown")
        if self.path.exists():
            archive = self.path.with_name(f".multi_account_daily_state.{previous}.json")
            if not archive.exists():
                try:
                    os.replace(self.path, archive)
                except OSError:
                    pass
        fresh = self._new_state()
        self._save_unlocked(fresh)
        return fresh

    @classmethod
    def _recover_running(cls, state: dict, instances: set[str] | None = None) -> bool:
        changed = False
        normalized = {str(item).lower() for item in instances} if instances is not None else None
        for instance_name, instance in state.get("instances", {}).items():
            if normalized is not None and instance_name.lower() not in normalized:
                continue
            for account in instance.get("accounts", {}).values():
                login = account.get("login", {})
                if login.get("status") == "running":
                    login.update(status="pending", error="interrupted before completion")
                    changed = True
                for task in account.get("tasks", {}).values():
                    if task.get("status") == "running":
                        task.update(status="pending", error="interrupted before completion")
                        changed = True
        return changed

    def _save_unlocked(self, state: dict) -> None:
        state["updated_at"] = self._now()
        temp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace_with_retry(temp, self.path)

    def load(self) -> dict:
        with self._locked():
            state = self._roll_date_unlocked(self._load_unlocked(recover_corrupt=True))
            return json.loads(json.dumps(state))

    def load_today(self) -> dict:
        return self.load()

    @staticmethod
    def _instance_for(account_id: str, instance: str | None = None) -> str:
        if instance:
            return instance.lower()
        prefix = str(account_id)[:1].upper()
        mapped = {"A": "oas3", "B": "oas4", "C": "oas5"}.get(prefix)
        if mapped:
            return mapped
        raise ValueError("instance is required for a non A/B/C account id")

    def get_account_state(self, account_id: str, instance: str | None = None) -> dict:
        state = self.load()
        node = state.get("instances", {}).get(self._instance_for(account_id, instance), {}).get("accounts", {})
        return json.loads(json.dumps(node.get(account_id, {
            "login": {"status": "pending", "attempts": 0, "error": "", "updated_at": ""},
            "tasks": {},
        })))

    def is_login_completed(self, account_id: str, instance: str | None = None) -> bool:
        return self.login_status(self._instance_for(account_id, instance), account_id) == "completed"

    def mark_login_running(self, account_id: str, instance: str | None = None) -> None:
        self.mark_login(self._instance_for(account_id, instance), account_id, "running")

    def mark_login_completed(self, account_id: str, instance: str | None = None) -> None:
        self.mark_login(self._instance_for(account_id, instance), account_id, "completed")

    def mark_login_failed(self, account_id: str, error: str, instance: str | None = None) -> None:
        self.mark_login(self._instance_for(account_id, instance), account_id, "failed", error=error)

    def save(self, state: dict) -> None:
        with self._locked():
            self._save_unlocked(state)

    @staticmethod
    def _account_node(state: dict, instance: str, account_id: str) -> dict:
        instances = state.setdefault("instances", {})
        instance_node = instances.setdefault(instance.lower(), {"accounts": {}})
        accounts = instance_node.setdefault("accounts", {})
        return accounts.setdefault(account_id, {
            "login": {"status": "pending", "attempts": 0, "error": "", "updated_at": ""},
            "tasks": {},
        })

    def login_status(self, instance: str, account_id: str) -> str:
        state = self.load()
        node = state.get("instances", {}).get(instance.lower(), {}).get("accounts", {}).get(account_id, {})
        return node.get("login", {}).get("status", "pending")

    def mark_login(self, instance: str, account_id: str, status: str, *, error: str = "") -> None:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid login status: {status}")
        with self._locked():
            state = self._roll_date_unlocked(self._load_unlocked(recover_corrupt=True))
            login = self._account_node(state, instance, account_id)["login"]
            if status == "running":
                login["attempts"] = int(login.get("attempts", 0)) + 1
            login.update(status=status, error=str(error or ""), updated_at=self._now())
            self._save_unlocked(state)

    def task_status(self, instance: str, account_id: str, task_name: str) -> str:
        state = self.load()
        node = state.get("instances", {}).get(instance.lower(), {}).get("accounts", {}).get(account_id, {})
        return node.get("tasks", {}).get(task_name, {}).get("status", "pending")

    def get_task_status(self, account_id: str, task_name: str, instance: str | None = None) -> str:
        return self.task_status(self._instance_for(account_id, instance), account_id, task_name)

    def mark_task_running(self, account_id: str, task_name: str, instance: str | None = None) -> None:
        self.mark_task(self._instance_for(account_id, instance), account_id, task_name, "running")

    def mark_task_completed(self, account_id: str, task_name: str, instance: str | None = None) -> None:
        self.mark_task(self._instance_for(account_id, instance), account_id, task_name, "completed")

    def mark_task_failed(self, account_id: str, task_name: str, error: str, instance: str | None = None) -> None:
        self.mark_task(self._instance_for(account_id, instance), account_id, task_name, "failed", error=error)

    def mark_task(self, instance: str, account_id: str, task_name: str, status: str, *, error: str = "") -> None:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid task status: {status}")
        with self._locked():
            state = self._roll_date_unlocked(self._load_unlocked(recover_corrupt=True))
            task = self._account_node(state, instance, account_id)["tasks"].setdefault(
                task_name, {"status": "pending", "attempts": 0, "error": "", "updated_at": ""}
            )
            if status == "running":
                task["attempts"] = int(task.get("attempts", 0)) + 1
            task.update(status=status, error=str(error or ""), updated_at=self._now())
            self._save_unlocked(state)

    def update_team_progress(self, team_id: str, task_name: str, progress: int, *, target: int | None = None) -> None:
        with self._locked():
            state = self._roll_date_unlocked(self._load_unlocked(recover_corrupt=True))
            task = state.setdefault("teams", {}).setdefault(team_id, {"tasks": {}}).setdefault(
                "tasks", {}
            ).setdefault(task_name, {"status": "running", "progress": 0})
            task.update(status="running", progress=int(progress), updated_at=self._now())
            if target is not None:
                task["target"] = int(target)
                if int(progress) >= int(target):
                    task["status"] = "completed"
            self._save_unlocked(state)

    def mark_team_task_status(
        self,
        team_id: str,
        task_name: str,
        status: str,
        *,
        error: str = "",
        target: int | None = None,
    ) -> None:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid team task status: {status}")
        with self._locked():
            state = self._roll_date_unlocked(self._load_unlocked(recover_corrupt=True))
            task = state.setdefault("teams", {}).setdefault(str(team_id), {"tasks": {}}).setdefault(
                "tasks", {}
            ).setdefault(str(task_name), {"status": "pending", "progress": 0})
            # A late peer error must not turn a fully completed group back into
            # failed after the leader has already persisted completion.
            if task.get("status") == "completed" and status != "completed":
                return
            task.update(status=status, error=str(error or ""), updated_at=self._now())
            if target is not None:
                task["target"] = int(target)
            self._save_unlocked(state)

    def get_team_task_state(self, team_id: str, task_name: str) -> dict:
        state = self.load()
        task = (
            state.get("teams", {})
            .get(str(team_id), {})
            .get("tasks", {})
            .get(str(task_name), {})
        )
        return json.loads(json.dumps(task))

    def is_team_task_completed_today(self, team_id: str, task_name: str) -> bool:
        state = self.load()
        today = self.today().isoformat()
        task = (
            state.get("teams", {})
            .get(str(team_id), {})
            .get("tasks", {})
            .get(str(task_name), {})
        )
        updated_at = str(task.get("updated_at") or "")
        return (
            state.get("date") == today
            and task.get("status") == "completed"
            and updated_at[:10] == today
        )
