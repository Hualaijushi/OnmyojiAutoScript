from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from module.multi_account.file_lock import atomic_replace_with_retry


ROLES = ("leader", "member_1", "member_2")
ROLE_STATUSES = {"pending", "ocr_done", "ready", "running", "done", "failed"}


class MultiAccountEvoSyncError(RuntimeError):
    pass


class SyncTimeoutError(MultiAccountEvoSyncError):
    pass


class SyncLockError(MultiAccountEvoSyncError):
    pass


class SyncStateError(MultiAccountEvoSyncError):
    pass


class PeerFailedError(MultiAccountEvoSyncError):
    pass


class RunChangedError(MultiAccountEvoSyncError):
    pass


class MultiAccountEvoSync:
    def __init__(
        self,
        directory: str | Path,
        timeout: float,
        poll_interval: float = 0.25,
        stale_lock_seconds: float = 30.0,
    ) -> None:
        self.directory = Path(directory)
        self.state_path = self.directory / ".multi_account_evo_sync.json"
        self.lock_path = self.directory / ".multi_account_evo_sync.lock"
        self.timeout = float(timeout)
        self.poll_interval = float(poll_interval)
        self.stale_lock_seconds = float(stale_lock_seconds)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @contextmanager
    def _lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"token": token, "created_at": self._now()}, stream)
                break
            except FileExistsError:
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > self.stale_lock_seconds:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise SyncLockError("timed out acquiring multi-account synchronization lock")
                time.sleep(self.poll_interval)
            except OSError as exc:
                raise SyncLockError(f"cannot acquire multi-account synchronization lock: {exc}") from exc
        try:
            yield
        finally:
            try:
                lock_data = json.loads(self.lock_path.read_text(encoding="utf-8"))
                if lock_data.get("token") == token:
                    self.lock_path.unlink(missing_ok=True)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass

    def _read_unlocked(self, *, allow_missing: bool = False) -> dict | None:
        if not self.state_path.exists():
            if allow_missing:
                return None
            raise SyncStateError("multi-account synchronization state does not exist")
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"multi-account synchronization state is damaged: {exc}") from exc
        self._validate_state(data)
        return data

    @staticmethod
    def _validate_state(data: object) -> None:
        if not isinstance(data, dict):
            raise SyncStateError("multi-account synchronization state must be an object")
        required = {"date", "run_id", "current_group", "group_count", "battle_count", "roles", "complete", "updated_at"}
        if not required.issubset(data):
            raise SyncStateError("multi-account synchronization state is missing required fields")
        roles = data.get("roles")
        if not isinstance(roles, dict) or set(roles) != set(ROLES):
            raise SyncStateError("multi-account synchronization roles are invalid")
        for role, role_data in roles.items():
            if not isinstance(role_data, dict) or role_data.get("status") not in ROLE_STATUSES:
                raise SyncStateError(f"multi-account synchronization role is invalid: {role}")

    def read(self, *, allow_missing: bool = False) -> dict | None:
        return self._read_unlocked(allow_missing=allow_missing)

    def assert_active(self, run_id: str, group: int) -> dict:
        state = self._read_unlocked()
        if state["run_id"] != run_id:
            raise RunChangedError("leader started a new synchronization run")
        if state["current_group"] != group:
            raise RunChangedError("leader advanced to a different group")
        failures = [
            f"{role}: {info.get('error') or 'unknown error'}"
            for role, info in state["roles"].items()
            if info["status"] == "failed"
        ]
        if failures:
            raise PeerFailedError("; ".join(failures))
        return state

    def _write_unlocked(self, data: dict) -> None:
        data["updated_at"] = self._now()
        self._validate_state(data)
        temp_path = self.directory / f".{self.state_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            atomic_replace_with_retry(temp_path, self.state_path, timeout=5)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _empty_roles() -> dict:
        return {
            role: {"status": "pending", "character": "", "error": "", "updated_at": ""}
            for role in ROLES
        }

    def start_or_resume(self, group_count: int, battle_count: int, run_date: str | None = None) -> dict:
        run_date = run_date or date.today().isoformat()
        with self._lock():
            previous = self._read_unlocked(allow_missing=True)
            if previous and previous["date"] == run_date and previous["complete"]:
                return previous
            current_group = 1
            if previous and previous["date"] == run_date:
                current_group = int(previous["current_group"])
            state = {
                "date": run_date,
                "run_id": uuid.uuid4().hex,
                "current_group": current_group,
                "group_count": int(group_count),
                "battle_count": int(battle_count),
                "roles": self._empty_roles(),
                "complete": False,
                "updated_at": self._now(),
            }
            self._write_unlocked(state)
            return state

    def _wait(
        self,
        predicate: Callable[[dict], bool],
        description: str,
        run_id: str | None = None,
        *,
        ignore_failures_until_match: bool = False,
    ) -> dict:
        deadline = time.monotonic() + self.timeout
        while True:
            state = self._read_unlocked(allow_missing=True)
            if state is not None:
                if run_id is not None and state["run_id"] != run_id:
                    raise RunChangedError("leader started a new synchronization run")
                matched = predicate(state)
                failures = [
                    f"{role}: {info.get('error') or 'unknown error'}"
                    for role, info in state["roles"].items()
                    if info["status"] == "failed"
                ]
                if failures and not (ignore_failures_until_match and not matched):
                    raise PeerFailedError("; ".join(failures))
                if matched:
                    return state
            if time.monotonic() >= deadline:
                raise SyncTimeoutError(f"timed out waiting for {description}")
            time.sleep(self.poll_interval)

    def wait_for_session(self, run_date: str | None = None) -> dict:
        run_date = run_date or date.today().isoformat()
        return self._wait(
            lambda state: state["date"] == run_date
            and all(info["status"] != "failed" for info in state["roles"].values()),
            "leader session",
            ignore_failures_until_match=True,
        )

    def update_role(
        self,
        run_id: str,
        group: int,
        role: str,
        status: str,
        *,
        character: str = "",
        error: str = "",
    ) -> dict:
        if role not in ROLES or status not in ROLE_STATUSES:
            raise SyncStateError("invalid role or role status")
        with self._lock():
            state = self._read_unlocked()
            if state["run_id"] != run_id:
                raise RunChangedError("leader started a new synchronization run")
            if state["current_group"] != group:
                raise RunChangedError("leader advanced to a different group")
            state["roles"][role] = {
                "status": status,
                "character": character if status in {"ocr_done", "ready", "running", "done"} else "",
                "error": str(error)[:300] if status == "failed" else "",
                "updated_at": self._now(),
            }
            self._write_unlocked(state)
            return state

    def wait_all_ready(self, run_id: str, group: int) -> dict:
        acceptable = {"ready", "running", "done"}
        return self._wait(
            lambda state: state["current_group"] == group
            and all(info["status"] in acceptable for info in state["roles"].values()),
            f"all roles READY for group {group}",
            run_id,
        )

    def wait_roles_ready(self, run_id: str, group: int, roles: tuple[str, ...]) -> dict:
        """Wait until earlier instances have completed account/character OCR."""
        unknown = set(roles) - set(ROLES)
        if unknown:
            raise SyncStateError(f"invalid predecessor roles: {sorted(unknown)}")
        acceptable = {"ocr_done", "ready", "running", "done"}
        return self._wait(
            lambda state: state["current_group"] == group
            and all(state["roles"][role]["status"] in acceptable for role in roles),
            f"roles {', '.join(roles)} READY for group {group}",
            run_id,
        )

    def wait_all_done(self, run_id: str, group: int) -> dict:
        return self._wait(
            lambda state: state["current_group"] == group
            and all(info["status"] == "done" for info in state["roles"].values()),
            f"all roles DONE for group {group}",
            run_id,
        )

    def advance(self, run_id: str, group: int, role: str) -> dict:
        if role != "leader":
            raise SyncStateError("only leader can advance the group")
        with self._lock():
            state = self._read_unlocked()
            if state["run_id"] != run_id or state["current_group"] != group:
                raise RunChangedError("cannot advance a changed synchronization run")
            if any(info["status"] != "done" for info in state["roles"].values()):
                raise SyncStateError("leader cannot advance before all roles are DONE")
            if group >= state["group_count"]:
                state["current_group"] = state["group_count"] + 1
                state["complete"] = True
            else:
                state["current_group"] = group + 1
                state["roles"] = self._empty_roles()
            self._write_unlocked(state)
            return state

    def skip_completed_group(self, run_id: str, group: int, role: str) -> dict:
        """Advance a group already completed in today's durable state."""
        if role != "leader":
            raise SyncStateError("only leader can skip a completed group")
        with self._lock():
            state = self._read_unlocked()
            if state["run_id"] != run_id or state["current_group"] != group:
                raise RunChangedError("cannot skip a changed synchronization run")
            if group >= state["group_count"]:
                state["current_group"] = state["group_count"] + 1
                state["complete"] = True
            else:
                state["current_group"] = group + 1
                state["roles"] = self._empty_roles()
            self._write_unlocked(state)
            return state

    def wait_for_advance(self, run_id: str, group: int) -> dict:
        return self._wait(
            lambda state: state["complete"] or state["current_group"] > group,
            f"leader to advance group {group}",
            run_id,
        )

    def fail(self, run_id: str, group: int, role: str, error: str) -> None:
        try:
            self.update_role(run_id, group, role, "failed", error=error)
        except MultiAccountEvoSyncError:
            pass
