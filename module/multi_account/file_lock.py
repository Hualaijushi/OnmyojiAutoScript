from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class InterProcessLockTimeout(TimeoutError):
    pass


_thread_locks_guard = threading.Lock()
_thread_locks: dict[str, threading.Lock] = {}


def _thread_lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _thread_locks_guard:
        return _thread_locks.setdefault(key, threading.Lock())


def _try_os_lock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_os_lock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def interprocess_file_lock(path: str | Path, *, timeout: float = 10.0, poll_interval: float = 0.02):
    """Serialize threads and processes without creating/deleting sentinel files.

    Keeping one lock file and locking its first byte avoids the Windows race in
    which one process deletes a lock file while another process is opening it.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timeout = max(0.01, float(timeout))
    deadline = time.monotonic() + timeout
    thread_lock = _thread_lock_for(path)
    if not thread_lock.acquire(timeout=timeout):
        raise InterProcessLockTimeout(f"file lock timeout: {path}")

    stream = None
    locked = False
    last_error: OSError | None = None
    try:
        while time.monotonic() < deadline:
            try:
                stream = path.open("a+b")
                stream.seek(0, os.SEEK_END)
                if stream.tell() < 1:
                    stream.write(b"\0")
                    stream.flush()
                _try_os_lock(stream)
                locked = True
                break
            except OSError as exc:
                last_error = exc
                if stream is not None:
                    stream.close()
                    stream = None
                time.sleep(poll_interval)
        if not locked:
            detail = f": {last_error}" if last_error is not None else ""
            raise InterProcessLockTimeout(f"file lock timeout: {path}{detail}")
        yield
    finally:
        if locked and stream is not None:
            try:
                _unlock_os_lock(stream)
            finally:
                stream.close()
        elif stream is not None:
            stream.close()
        thread_lock.release()


def atomic_replace_with_retry(source: str | Path, target: str | Path, *, timeout: float = 2.0) -> None:
    """Retry transient Windows sharing violations during atomic replacement."""

    source = Path(source)
    target = Path(target)
    deadline = time.monotonic() + max(0.01, float(timeout))
    delay = 0.01
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(0.1, delay * 2)
