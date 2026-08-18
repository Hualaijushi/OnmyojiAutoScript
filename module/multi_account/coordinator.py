from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from module.logger import logger
from module.multi_account.file_lock import (
    InterProcessLockTimeout,
    atomic_replace_with_retry,
    interprocess_file_lock,
)


class CoordinationTimeoutError(TimeoutError):
    pass


class SharedOcrCoordinator:
    """Cross-process fair lease for OCR-sensitive account switching steps.

    Only the lightweight lease state is file based.  Actual recognition still
    runs through the existing shared OCR RPC server.
    """

    INSTANCE_ORDER = ("oas3", "oas4", "oas5")

    def __init__(
        self,
        directory: str | Path,
        instance: str,
        *,
        acquire_timeout: float = 90.0,
        lease_timeout: float = 45.0,
        turn_grace: float = 0.35,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.instance = str(instance).lower()
        if self.instance not in self.INSTANCE_ORDER:
            raise ValueError(f"unsupported coordinated OCR instance: {instance}")
        self.path = self.directory / ".multi_account_ocr_coord.json"
        self.lock_path = self.directory / ".multi_account_ocr_coord.lock"
        self.acquire_timeout = max(1.0, float(acquire_timeout))
        self.lease_timeout = max(5.0, float(lease_timeout))
        self.turn_grace = max(0.0, float(turn_grace))

    @contextmanager
    def _locked(self, timeout: float = 10.0):
        try:
            with interprocess_file_lock(self.lock_path, timeout=timeout, poll_interval=0.01):
                yield
        except InterProcessLockTimeout as exc:
            raise CoordinationTimeoutError("OCR coordinator lock timeout") from exc

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        return {"version": 1, "turn_index": 0, "lease": None, "pending": {}}

    def _save(self, state: dict) -> None:
        temp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace_with_retry(temp, self.path)

    def _clean(self, state: dict, now: float) -> None:
        lease = state.get("lease")
        if lease and now - float(lease.get("acquired_at", 0)) > self.lease_timeout:
            logger.warning("[OCR-Coordinator] reclaim stale lease instance=%s", lease.get("instance"))
            state["lease"] = None
        pending = state.setdefault("pending", {})
        for instance, item in list(pending.items()):
            if now - float(item.get("requested_at", 0)) > self.acquire_timeout + self.lease_timeout:
                pending.pop(instance, None)

    def _candidate(self, state: dict, now: float) -> str | None:
        pending = state.get("pending", {})
        if not pending:
            return None
        start = int(state.get("turn_index", 0)) % len(self.INSTANCE_ORDER)
        expected = self.INSTANCE_ORDER[start]
        if expected in pending:
            return expected
        oldest = min(float(item.get("requested_at", now)) for item in pending.values())
        if now - oldest < self.turn_grace:
            return None
        for offset in range(1, len(self.INSTANCE_ORDER) + 1):
            candidate = self.INSTANCE_ORDER[(start + offset) % len(self.INSTANCE_ORDER)]
            if candidate in pending:
                return candidate
        return None

    def acquire(self, scene: str) -> tuple[str, float]:
        request_id = uuid.uuid4().hex
        requested_at = time.time()
        deadline = time.monotonic() + self.acquire_timeout
        while time.monotonic() < deadline:
            with self._locked():
                state = self._load()
                now = time.time()
                self._clean(state, now)
                pending = state.setdefault("pending", {})
                pending[self.instance] = {
                    "request_id": request_id,
                    "requested_at": requested_at,
                    "scene": str(scene),
                }
                if state.get("lease") is None and self._candidate(state, now) == self.instance:
                    state["lease"] = {
                        "instance": self.instance,
                        "request_id": request_id,
                        "scene": str(scene),
                        "acquired_at": now,
                    }
                    self._save(state)
                    waited = max(0.0, now - requested_at)
                    logger.info(
                        "[OCR-Coordinator] grant instance=%s scene=%s wait=%.2fs",
                        self.instance,
                        scene,
                        waited,
                    )
                    return request_id, waited
                self._save(state)
            time.sleep(0.03)
        with self._locked():
            state = self._load()
            pending = state.setdefault("pending", {})
            if pending.get(self.instance, {}).get("request_id") == request_id:
                pending.pop(self.instance, None)
                self._save(state)
        raise CoordinationTimeoutError(f"OCR lease timeout: {self.instance} scene={scene}")

    def release(self, request_id: str) -> None:
        with self._locked():
            state = self._load()
            lease = state.get("lease")
            if lease and lease.get("request_id") == request_id:
                index = self.INSTANCE_ORDER.index(self.instance)
                state["turn_index"] = (index + 1) % len(self.INSTANCE_ORDER)
                state["lease"] = None
            pending = state.setdefault("pending", {})
            if pending.get(self.instance, {}).get("request_id") == request_id:
                pending.pop(self.instance, None)
            self._save(state)

    @contextmanager
    def lease(self, scene: str):
        request_id, waited = self.acquire(scene)
        try:
            yield waited
        finally:
            self.release(request_id)


class ThreeInstanceGroupBarrier:
    """Keep A/B/C account groups aligned using the shared daily state."""

    TERMINAL = {"completed", "failed", "skipped"}

    def __init__(self, daily_state, positions: list[int], *, timeout: float = 300.0) -> None:
        self.daily_state = daily_state
        self.positions = list(positions)
        self.timeout = max(10.0, float(timeout))

    @staticmethod
    def _account_ids(position: int) -> tuple[tuple[str, str], ...]:
        return (
            ("oas3", f"A{position:02d}"),
            ("oas4", f"B{position:02d}"),
            ("oas5", f"C{position:02d}"),
        )

    def wait_for_previous_group(self, index: int) -> float:
        if index <= 0:
            return 0.0
        previous = self.positions[index - 1]
        started = time.monotonic()
        deadline = started + self.timeout
        while time.monotonic() < deadline:
            statuses = [
                self.daily_state.login_status(instance, account_id)
                for instance, account_id in self._account_ids(previous)
            ]
            if all(status in self.TERMINAL for status in statuses):
                waited = time.monotonic() - started
                if waited >= 0.1:
                    logger.info(
                        "[Account-Barrier] previous_position=%s statuses=%s wait=%.2fs",
                        previous,
                        statuses,
                        waited,
                    )
                return waited
            time.sleep(0.2)
        raise CoordinationTimeoutError(f"three-instance group barrier timeout after position {previous}")
