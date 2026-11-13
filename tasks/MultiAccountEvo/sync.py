from __future__ import annotations

import copy
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import psutil

from module.multi_account.file_lock import atomic_replace_with_retry
from tasks.MultiAccountEvo.event import event_complete


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


class SessionReplacedError(RunChangedError):
    """队长换代；仅尚未进入战斗流程的队员可以重新接入。"""


class RecoveryRequested(MultiAccountEvoSyncError):
    """通知旧执行段停止，由当前组共同恢复。"""

    def __init__(self, epoch: int):
        self.epoch = epoch
        super().__init__(f"team recovery requested: epoch={epoch}")


class RecoveryExhausted(MultiAccountEvoSyncError):
    pass


class MultiAccountEvoSync:
    def __init__(
        self,
        directory: str | Path,
        timeout: float,
        poll_interval: float = 0.25,
        stale_lock_seconds: float = 30.0,
        event_mode: bool = False,
    ) -> None:
        self.directory = Path(directory)
        self.event_mode = event_mode
        name = ".multi_account_evo_event_50_sync" if event_mode else ".multi_account_evo_sync"
        self.state_path = self.directory / f"{name}.json"
        self.lock_path = self.directory / f"{name}.lock"
        self.timeout = float(timeout)
        self.poll_interval = float(poll_interval)
        self.stale_lock_seconds = float(stale_lock_seconds)
        # 本进程最近一次加锁读到或写入的状态，供高频控制检查复用。
        self._last_state: tuple[float, dict] | None = None

    # 截图钩子等高频控制检查的最长复用时间。每次检查都创建/删除锁文件会让
    # 三个进程在 Windows 上触发删除挂起和拒绝访问，进而卡住整组。
    control_check_interval: float = 1.0

    def _remember(self, data: dict) -> None:
        self._last_state = (time.monotonic(), copy.deepcopy(data))

    def _control_state(self, max_age: float, deadline: float | None = None) -> dict:
        cached = getattr(self, "_last_state", None)
        if max_age > 0 and cached is not None and time.monotonic() - cached[0] < max_age:
            return copy.deepcopy(cached[1])
        return self.read(deadline=deadline)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @contextmanager
    def _lock(self, *, deadline: float | None = None):
        self.directory.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        lock_deadline = time.monotonic() + self.timeout
        deadline = lock_deadline if deadline is None else min(deadline, lock_deadline)
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
                except PermissionError:
                    # Windows 删除中的锁文件可能短暂拒绝访问，仍按锁竞争等待。
                    pass
                if time.monotonic() >= deadline:
                    raise SyncLockError("timed out acquiring multi-account synchronization lock")
                time.sleep(self.poll_interval)
            except PermissionError as exc:
                # 只重试锁创建的短暂占用；持久权限错误仍受原期限约束。
                if time.monotonic() >= deadline:
                    raise SyncLockError("timed out acquiring multi-account synchronization lock") from exc
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
        self._remember(data)
        return data

    @staticmethod
    def _validate_state(data: object) -> None:
        if not isinstance(data, dict):
            raise SyncStateError("multi-account synchronization state must be an object")
        required = {"date", "run_id", "current_group", "group_count", "battle_count", "roles", "complete", "updated_at"}
        if not required.issubset(data):
            raise SyncStateError("multi-account synchronization state is missing required fields")
        start, end = data.get("group_start", 1), data.get("group_end", data["group_count"])
        if (type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= data["group_count"]
                or not start <= data["current_group"] <= end + 1):
            raise SyncStateError("invalid local account group range in synchronization state")
        roles = data.get("roles")
        if not isinstance(roles, dict) or set(roles) != set(ROLES):
            raise SyncStateError("multi-account synchronization roles are invalid")
        for role, role_data in roles.items():
            if not isinstance(role_data, dict) or role_data.get("status") not in ROLE_STATUSES:
                raise SyncStateError(f"multi-account synchronization role is invalid: {role}")
        recovery = data.get("recovery", {})
        if not isinstance(recovery, dict) or recovery.get("phase", "running") not in {"running", "recovering"}:
            raise SyncStateError("invalid team recovery state")
        if not isinstance(recovery.get("epoch", 0), int) or recovery.get("epoch", 0) < 0:
            raise SyncStateError("invalid team recovery epoch")
        if recovery.get("phase") == "recovering":
            for key in ("paused", "restarted"):
                if not isinstance(recovery.get(key), list) or not set(recovery[key]).issubset(ROLES):
                    raise SyncStateError("invalid team recovery acknowledgements")
        attempts = data.get("recovery_attempts", {})
        if not isinstance(attempts, dict) or any(
            not isinstance(value, int) or value < 0 for value in attempts.values()
        ):
            raise SyncStateError("invalid team recovery attempts")
        if "checkpoint_key" in data:
            if not isinstance(data["checkpoint_key"], str) or not data["checkpoint_key"]:
                raise SyncStateError("invalid battle checkpoint key")
            progress = data.get("battle_progress")
            if not isinstance(progress, dict):
                raise SyncStateError("invalid battle progress")
            for group, counts in progress.items():
                if (not str(group).isdigit() or not 1 <= int(group) <= data["group_count"]
                        or not isinstance(counts, dict) or set(counts) != set(ROLES)
                        or any(type(n) is not int or not 0 <= n <= data["battle_count"]
                               for n in counts.values())):
                    raise SyncStateError("invalid battle progress counts")
            segment = data.get("battle_segment")
            if segment is not None:
                if (not isinstance(segment, dict)
                        or segment.get("group") != data["current_group"]
                        or segment.get("epoch") != MultiAccountEvoSync.recovery_epoch(data)):
                    raise SyncStateError("invalid battle segment identity")
                bases, reported = segment.get("bases"), segment.get("reported")
                if (not isinstance(bases, dict) or set(bases) != set(ROLES)
                        or any(type(n) is not int or not 0 <= n <= data["battle_count"]
                               for n in bases.values())
                        or type(segment.get("remaining")) is not int
                        or segment["remaining"] != data["battle_count"] - (
                            max(bases.values()) if data.get("event_mode") else min(bases.values()))
                        or not isinstance(reported, dict) or set(reported) != set(ROLES)
                        or any(type(n) is not int or not 0 <= n <= segment["remaining"]
                               for n in reported.values())):
                    raise SyncStateError("invalid battle segment counts")
                counts = progress.get(str(segment["group"]), {})
                if any(counts.get(role) != min(data["battle_count"], bases[role] + reported[role])
                       for role in ROLES):
                    raise SyncStateError("battle segment does not match progress")
        if data.get("event_mode"):
            groups = data.get("event_groups")
            if not isinstance(groups, dict):
                raise SyncStateError("invalid event groups")
            for node in groups.values():
                if not isinstance(node, dict) or not isinstance(node.get("roles"), dict):
                    raise SyncStateError("invalid event role records")
                for info in node["roles"].values():
                    value = info.get("value")
                    if (value is not None and (type(value) is not int or not 0 <= value <= 50)
                            or type(info.get("reached", False)) is not bool
                            or info.get("reached") and value != 50):
                        raise SyncStateError("invalid event ticket value")

    def read(self, *, allow_missing: bool = False, deadline: float | None = None) -> dict | None:
        with self._lock(deadline=deadline):
            return self._read_unlocked(allow_missing=allow_missing)

    @staticmethod
    def recovery_epoch(state: dict) -> int:
        return state.get("recovery", {}).get("epoch", 0)

    @staticmethod
    def _check_control(state: dict, run_id: str, group: int, *,
                       epoch: int | None = None, allow_recovery: bool = False) -> None:
        if state["run_id"] != run_id:
            raise SessionReplacedError("leader started a new synchronization run")
        if state["current_group"] != group:
            raise RunChangedError("leader advanced to a different group")
        if state.get("event_mode") and state["date"] != date.today().isoformat():
            raise SyncStateError("event date changed; stopped at the old daily record")
        failures = [
            f"{role}: {info.get('error') or 'unknown error'}"
            for role, info in state["roles"].items()
            if info["status"] == "failed"
        ]
        if failures:
            raise PeerFailedError("; ".join(failures))
        recovery = state.get("recovery", {})
        if not allow_recovery and recovery.get("phase") == "recovering":
            raise RecoveryRequested(recovery["epoch"])
        if epoch is not None and MultiAccountEvoSync.recovery_epoch(state) != epoch:
            raise RunChangedError("team recovery epoch changed")

    def assert_active(self, run_id: str, group: int, *, epoch: int | None = None,
                      max_age: float = 0.0) -> dict:
        """max_age 大于 0 时可复用本进程最近状态；屏障和写入仍各自加锁实时读取。"""
        state = self._control_state(max_age)
        self._check_control(state, run_id, group, epoch=epoch)
        return state

    def assert_recovering(self, run_id: str, group: int, epoch: int,
                          *, deadline: float | None = None, max_age: float = 0.0) -> dict:
        state = self._control_state(max_age, deadline)
        self._check_control(state, run_id, group, epoch=epoch, allow_recovery=True)
        if state.get("recovery", {}).get("phase") != "recovering":
            raise RunChangedError("team recovery already finished")
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
            self._remember(data)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _empty_roles() -> dict:
        return {
            role: {"status": "pending", "character": "", "error": "", "updated_at": ""}
            for role in ROLES
        }

    def start_or_resume(self, group_count: int, battle_count: int, run_date: str | None = None,
                        *, checkpoint_key: str = "", group_start: int = 1, group_end: int = 0,
                        event_ocr_start: int = 200, event_ocr_interval: int = 10,
                        checkpoint_key_for_count: Callable[[int], str] | None = None) -> dict:
        run_date = run_date or date.today().isoformat()
        group_end = group_end or group_count
        if not 1 <= group_start <= group_end <= group_count:
            raise SyncStateError("invalid local account group range")
        with self._lock():
            previous = self._read_unlocked(allow_missing=True)
            same_day = previous is not None and previous["date"] == run_date
            if same_day and (previous.get("group_start", 1), previous.get("group_end", group_count)) != (group_start, group_end):
                raise SyncStateError("local group range changed; explicit progress migration is required")
            if same_day and previous.get("checkpoint_key"):
                increase_limit = (self.event_mode and not previous["complete"]
                                  and battle_count > previous["battle_count"]
                                  and group_count == previous["group_count"]
                                  and checkpoint_key_for_count is not None
                                  and checkpoint_key_for_count(previous["battle_count"]) == previous["checkpoint_key"])
                if not increase_limit and (checkpoint_key != previous["checkpoint_key"]
                        or group_count != previous["group_count"]
                        or battle_count != previous["battle_count"]):
                    raise SyncStateError("checkpoint configuration changed; cannot reuse today's progress")
                if increase_limit:
                    # 新会话仍保留原逐场及门票记录；先保存迁移前的精确状态。
                    backup = self.state_path.with_name(
                        f"{self.state_path.name}.before-limit-{uuid.uuid4().hex}.bak"
                    )
                    with backup.open("xb") as stream:
                        stream.write(self.state_path.read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
            if previous and previous["date"] == run_date and previous["complete"]:
                return previous
            current_group = group_start
            if previous and previous["date"] == run_date:
                current_group = int(previous["current_group"])
            state = {
                "date": run_date,
                "run_id": uuid.uuid4().hex,
                "leader_process": {"pid": os.getpid(), "created": psutil.Process().create_time()},
                "current_group": current_group,
                "group_count": int(group_count),
                "group_start": group_start,
                "group_end": group_end,
                "battle_count": int(battle_count),
                "roles": self._empty_roles(),
                "complete": False,
                "updated_at": self._now(),
                # 同日重新启动任务不能清空当前组已经用掉的恢复预算。
                "recovery_attempts": previous.get("recovery_attempts", {})
                if previous and previous["date"] == run_date else {},
                "recovery": {"phase": "running", "epoch": 0},
            }
            if checkpoint_key:
                state.update(
                    checkpoint_key=checkpoint_key,
                    battle_progress=copy.deepcopy(previous.get("battle_progress", {})) if same_day else {},
                    battle_segment=None,
                )
            if self.event_mode:
                state.update(event_mode=True,
                             event_ocr_start=event_ocr_start, event_ocr_interval=event_ocr_interval,
                             event_groups=copy.deepcopy(previous.get("event_groups", {})) if same_day else {})
            self._write_unlocked(state)
            return state

    def begin_battle_segment(self, run_id: str, group: int, epoch: int) -> dict:
        """在锁内冻结三端本段起点；迟到成员不能用已增长的进度另算剩余数。"""
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch)
            if not state.get("checkpoint_key"):
                raise SyncStateError("battle checkpoints are not enabled")
            if any(info["status"] not in {"ready", "running", "done"}
                   for info in state["roles"].values()):
                raise SyncStateError("cannot begin battles before all roles are READY")
            segment = state.get("battle_segment")
            if segment is None:
                counts = state["battle_progress"].setdefault(str(group), dict.fromkeys(ROLES, 0))
                segment = {
                    "group": group, "epoch": epoch, "bases": dict(counts),
                    "remaining": state["battle_count"] - (
                        max(counts.values()) if state.get("event_mode") else min(counts.values())),
                    "reported": dict.fromkeys(ROLES, 0),
                }
                state["battle_segment"] = segment
                if state.get("event_mode"):
                    node = state["event_groups"].setdefault(str(group), {"roles": {}, "samples": {}})
                    node.update(status="running", updated_at=self._now())
                    for role in ROLES:
                        node["roles"].setdefault(role, {"value": None, "reached": False})
                        node["roles"][role]["character"] = state["roles"][role].get("character", "")
                self._write_unlocked(state)
            return copy.deepcopy(segment)

    def record_battle_progress(self, run_id: str, group: int, epoch: int,
                              role: str, completed: int) -> dict:
        """上报本段已结算场数；重复/乱序不重复计数，旧执行段不能写入。"""
        if role not in ROLES or type(completed) is not int or completed < 1:
            raise SyncStateError("invalid battle progress report")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch)
            segment = state.get("battle_segment")
            if segment is None:
                raise SyncStateError("battle segment has not started")
            old = segment["reported"][role]
            if completed > segment["remaining"] or completed > old + 1:
                raise SyncStateError("battle report exceeds confirmed sequence")
            if completed <= old:
                return state
            segment["reported"][role] = completed
            state["battle_progress"][str(group)][role] = min(
                state["battle_count"], segment["bases"][role] + completed,
            )
            self._write_unlocked(state)
            return state

    def record_event_sample(self, run_id: str, group: int, epoch: int, role: str,
                            round_number: int, value: int, raw: str, reached: bool,
                            elapsed: float) -> str:
        if (role not in ROLES or type(value) is not int or not 0 <= value <= 50
                or type(reached) is not bool or reached and value != 50):
            raise SyncStateError("invalid event sample")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch)
            segment = state.get("battle_segment")
            if not state.get("event_mode") or segment is None:
                raise SyncStateError("event segment is not active")
            expected = segment["reported"][role] + 1
            if round_number != expected or not 1 <= round_number <= segment["remaining"]:
                raise SyncStateError("event sample does not match battle round")
            token = f"{run_id}:{epoch}:{round_number}"
            node = state["event_groups"][str(group)]
            info = node["roles"][role]
            if info.get("reached"):
                value, reached = 50, True
            info.update(value=value, reached=reached, raw=str(raw)[:100], updated_at=self._now())
            sample = node["samples"].setdefault(token, {
                "point": min(segment["bases"].values()) + round_number,
                "run_id": run_id, "epoch": epoch,
                "reports": {}, "ready": [], "created_at": self._now(),
            })
            sample["reports"][role] = {
                "value": value, "raw": str(raw)[:100], "reached": reached,
                "elapsed": round(float(elapsed), 3), "updated_at": self._now(),
            }
            node.update(status="sampling", updated_at=self._now())
            self._write_unlocked(state)
            return token

    def finish_event_sample(self, run_id: str, group: int, epoch: int,
                            role: str, token: str) -> dict:
        if role not in ROLES:
            raise SyncStateError("invalid event role")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch)
            segment = state.get("battle_segment")
            if segment is None or token != f'{run_id}:{epoch}:{segment["reported"][role]}':
                raise SyncStateError("stale event sample acknowledgement")
            node = state["event_groups"][str(group)]
            sample = node["samples"].get(token)
            if sample is None or role not in sample["reports"]:
                raise SyncStateError("event report missing before ready acknowledgement")
            if state["battle_segment"]["reported"][role] < int(token.rsplit(":", 1)[1]):
                raise SyncStateError("event battle has not finished")
            sample["ready"] = sorted(set(sample["ready"]) | {role})
            if set(sample["ready"]) == set(ROLES):
                node["status"] = "finishing" if event_complete(state, group) else "running"
            node.update(updated_at=self._now())
            self._write_unlocked(state)
        return self._wait(
            lambda data: set(data["event_groups"][str(group)]["samples"].get(token, {}).get("ready", [])) == set(ROLES),
            f"event sample {token}", run_id, epoch=epoch,
        )

    def _wait(
        self,
        predicate: Callable[[dict], bool],
        description: str,
        run_id: str | None = None,
        *,
        ignore_failures_until_match: bool = False,
        allow_recovery: bool = False,
        epoch: int | None = None,
        deadline: float | None = None,
    ) -> dict:
        wait_deadline = time.monotonic() + self.timeout
        deadline = wait_deadline if deadline is None else min(deadline, wait_deadline)
        while True:
            if time.monotonic() >= deadline:
                raise SyncTimeoutError(f"timed out waiting for {description}")
            with self._lock(deadline=deadline):
                state = self._read_unlocked(allow_missing=True)
            if state is not None:
                if run_id is not None and state["run_id"] != run_id:
                    raise SessionReplacedError("leader started a new synchronization run")
                matched = predicate(state)
                failures = [
                    f"{role}: {info.get('error') or 'unknown error'}"
                    for role, info in state["roles"].items()
                    if info["status"] == "failed"
                ]
                if failures and not (ignore_failures_until_match and not matched):
                    raise PeerFailedError("; ".join(failures))
                if run_id is not None:
                    recovery = state.get("recovery", {})
                    if not allow_recovery and recovery.get("phase") == "recovering":
                        raise RecoveryRequested(recovery["epoch"])
                    if epoch is not None and self.recovery_epoch(state) != epoch:
                        raise RunChangedError("team recovery epoch changed while waiting")
                if matched:
                    return state
            if time.monotonic() >= deadline:
                raise SyncTimeoutError(f"timed out waiting for {description}")
            time.sleep(self.poll_interval)

    @staticmethod
    def _leader_session_alive(state: dict) -> bool:
        """旧JSON不能证明队长还在；进程创建时间防止PID被复用后误接旧会话。"""
        owner = state.get("leader_process", {})
        pid, created = owner.get("pid"), owner.get("created")
        if type(pid) is not int or pid <= 0 or not isinstance(created, (int, float)):
            return False
        try:
            process = psutil.Process(pid)
            return process.is_running() and abs(process.create_time()-created) < .001
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def wait_for_session(self, run_date: str | None = None, *,
                         exclude_run_id: str | None = None, deadline: float | None = None) -> dict:
        run_date = run_date or date.today().isoformat()
        return self._wait(
            lambda state: state["date"] == run_date
            and state["run_id"] != exclude_run_id
            and (state["complete"] or (
                state["roles"]["leader"]["status"] in {"ready", "running", "done"}
                and self._leader_session_alive(state)))
            and all(info["status"] != "failed" for info in state["roles"].values()),
            "live leader READY session",
            ignore_failures_until_match=True,
            deadline=deadline,
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
        epoch: int | None = None,
    ) -> dict:
        if role not in ROLES or status not in ROLE_STATUSES:
            raise SyncStateError("invalid role or role status")
        with self._lock():
            state = self._read_unlocked()
            if state["run_id"] != run_id:
                raise SessionReplacedError("leader started a new synchronization run")
            if state["current_group"] != group:
                raise RunChangedError("leader advanced to a different group")
            if status != "failed":
                self._check_control(state, run_id, group, epoch=epoch)
            if status == "done" and state.get("checkpoint_key"):
                counts = state["battle_progress"].get(str(group), {})
                segment = state.get("battle_segment")
                complete = event_complete(state, group) if state.get("event_mode") else (
                    counts.get(role, 0) >= state["battle_count"] and segment is not None
                    and segment["reported"][role] >= segment["remaining"])
                if not complete:
                    raise SyncStateError("cannot finish before all segment battles are confirmed")
            if state.get("event_mode") and status == "failed":
                node = state["event_groups"].setdefault(str(group), {"roles": {}, "samples": {}})
                node.update(status="failed", error=str(error)[:500], updated_at=self._now())
            state["roles"][role] = {
                "status": status,
                "character": character if status in {"ocr_done", "ready", "running", "done"} else "",
                "error": str(error)[:300] if status == "failed" else "",
                "updated_at": self._now(),
            }
            self._write_unlocked(state)
            return state

    def wait_all_ready(self, run_id: str, group: int, *, deadline: float | None = None) -> dict:
        acceptable = {"ready", "running", "done"}
        return self._wait(
            lambda state: state["current_group"] == group
            and all(info["status"] in acceptable for info in state["roles"].values()),
            f"all roles READY for group {group}",
            run_id,
            deadline=deadline,
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

    def wait_all_done(self, run_id: str, group: int, *, epoch: int | None = None) -> dict:
        return self._wait(
            lambda state: state["current_group"] == group
            and all(info["status"] == "done" for info in state["roles"].values()),
            f"all roles DONE for group {group}",
            run_id,
            epoch=epoch,
        )

    def request_recovery(self, run_id: str, group: int, role: str, error: str,
                         *, max_attempts: int = 1) -> dict:
        """在同一把锁内合并并发请求，并消耗本组的持久恢复预算。"""
        if role not in ROLES:
            raise SyncStateError("invalid recovery role")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, allow_recovery=True)
            if state.get("recovery", {}).get("phase") == "recovering":
                return state
            attempts = state.setdefault("recovery_attempts", {})
            used = attempts.get(str(group), 0)
            if used >= max_attempts:
                raise RecoveryExhausted(f"group {group} automatic game recovery exhausted ({used})")
            attempts[str(group)] = used + 1
            state["recovery"] = {
                "phase": "recovering", "epoch": self.recovery_epoch(state) + 1,
                "requested_by": role, "reason": str(error)[:300],
                "paused": [], "restarted": [],
            }
            if state.get("checkpoint_key"):
                state["battle_segment"] = None
            self._write_unlocked(state)
            return state

    def acknowledge_recovery(self, run_id: str, group: int, epoch: int,
                             role: str, stage: str) -> dict:
        if role not in ROLES or stage not in {"paused", "restarted"}:
            raise SyncStateError("invalid recovery acknowledgement")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch, allow_recovery=True)
            recovery = state.get("recovery", {})
            if recovery.get("phase") != "recovering":
                raise RunChangedError("cannot acknowledge a finished recovery")
            if stage == "restarted":
                if set(recovery["paused"]) != set(ROLES):
                    raise SyncStateError("cannot restart before all roles paused")
                if not set(ROLES[:ROLES.index(role)]).issubset(recovery["restarted"]):
                    raise SyncStateError("game restarts must follow role order")
            recovery[stage] = sorted(set(recovery[stage]) | {role})
            self._write_unlocked(state)
            return state

    def wait_recovery_stage(self, run_id: str, group: int, epoch: int,
                            stage: str, roles: tuple[str, ...] = ROLES,
                            *, deadline: float | None = None) -> dict:
        if stage not in {"paused", "restarted"} or not set(roles).issubset(ROLES):
            raise SyncStateError("invalid recovery wait stage")
        return self._wait(
            lambda state: state["current_group"] == group
            and set(roles).issubset(state.get("recovery", {}).get(stage, [])),
            f"recovery {epoch} {stage}", run_id,
            allow_recovery=True, epoch=epoch, deadline=deadline,
        )

    def finish_recovery(self, run_id: str, group: int, epoch: int, role: str) -> dict:
        if role != "leader":
            raise SyncStateError("only leader can finish recovery")
        with self._lock():
            state = self._read_unlocked()
            self._check_control(state, run_id, group, epoch=epoch, allow_recovery=True)
            recovery = state.get("recovery", {})
            if recovery.get("phase") != "recovering" or set(recovery["restarted"]) != set(ROLES):
                raise SyncStateError("cannot finish before all games restarted")
            recovery["phase"] = "running"
            prebattle_switch = recovery.get("reason", "").startswith("PREBATTLE:")
            for info in state["roles"].values():
                if prebattle_switch:
                    info.update(status="pending", character="", error="", updated_at=self._now())
                else:
                    info.update(status="ready", error="", updated_at=self._now())
            self._write_unlocked(state)
            return state

    def wait_recovery_finished(self, run_id: str, group: int, epoch: int,
                               *, deadline: float | None = None) -> dict:
        return self._wait(
            lambda state: state["current_group"] == group
            and state.get("recovery", {}).get("phase") == "running",
            f"recovery {epoch} finished", run_id,
            allow_recovery=True, epoch=epoch, deadline=deadline,
        )

    def advance(self, run_id: str, group: int, role: str) -> dict:
        if role != "leader":
            raise SyncStateError("only leader can advance the group")
        with self._lock():
            state = self._read_unlocked()
            if state["run_id"] != run_id or state["current_group"] != group:
                raise RunChangedError("cannot advance a changed synchronization run")
            self._check_control(state, run_id, group)
            if any(info["status"] != "done" for info in state["roles"].values()):
                raise SyncStateError("leader cannot advance before all roles are DONE")
            if state.get("event_mode") and not event_complete(state, group):
                raise SyncStateError("cannot advance before all event tickets are confirmed")
            if state.get("checkpoint_key") and not state.get("event_mode") and any(
                count < state["battle_count"]
                for count in state["battle_progress"].get(str(group), dict.fromkeys(ROLES, 0)).values()
            ):
                raise SyncStateError("cannot advance with incomplete battle progress")
            if state.get("event_mode"):
                state["event_groups"][str(group)].update(status="completed", updated_at=self._now())
            if state.get("checkpoint_key"):
                state["battle_segment"] = None
            if group >= state.get("group_end", state["group_count"]):
                state["current_group"] = state.get("group_end", state["group_count"]) + 1
                state["complete"] = True
            else:
                state["current_group"] = group + 1
                state["roles"] = self._empty_roles()
                state["recovery"] = {"phase": "running", "epoch": 0}
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
            self._check_control(state, run_id, group)
            if state.get("event_mode"):
                if not event_complete(state, group):
                    raise SyncStateError("daily completion has no matching event evidence")
                state["event_groups"][str(group)].update(status="completed", updated_at=self._now())
            if state.get("checkpoint_key"):
                state["battle_segment"] = None
            if group >= state.get("group_end", state["group_count"]):
                state["current_group"] = state.get("group_end", state["group_count"]) + 1
                state["complete"] = True
            else:
                state["current_group"] = group + 1
                state["roles"] = self._empty_roles()
                state["recovery"] = {"phase": "running", "epoch": 0}
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
