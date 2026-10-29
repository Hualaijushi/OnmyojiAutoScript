# This Python file uses the following encoding: utf-8
"""共享账本：跨进程文件锁 + 原子写 + 事务（读 → 校验 → 变更 → 校验 → 写）。

`transact` 是账本的**唯一**读写入口：
- 全程在一把 FileLock 里完成「读、校验、变更、再校验、写」，不存在 read_file / write_file 各自加锁造成的丢更新。
- 持锁期间不截图、不点击、不回调适配器、不嵌套锁；拿不到锁就按 lock_timeout 报错，不无限等。
- 损坏 / 缺失 / 未知版本一律抛 LedgerError，**不覆盖、不重建**；损坏文件先备份一份再停止。
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from filelock import FileLock, Timeout

from module.config.atomicwrites import atomic_write
from module.instance_sync import state_machine as sm
from module.instance_sync.errors import (
    InvariantViolation, LedgerCorruptError, LedgerLockTimeout, LedgerLostError, LedgerWriteError,
)
from module.instance_sync.invariants import validate_document, validate_transition
from module.instance_sync.journal import Journal
from module.logger import logger


class Ledger:
    def __init__(self, root, key: dict, journal: Optional[Journal] = None, *,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 lock_timeout: float = 10.0, write_retries: int = 3, write_backoff: float = 0.05):
        self.root = Path(root)
        self.key = key
        self.journal = journal
        self.clock = clock
        self.sleep = sleep
        self.lock_timeout = lock_timeout
        self.write_retries = write_retries
        self.write_backoff = write_backoff
        self.name = sm.ledger_filename(key)
        self.path = self.root / self.name
        self.lock_path = self.root / f'{self.name}.lock'

    def transact(self, fn: Callable[[dict, float], Any], *, create_if_missing: bool = False) -> tuple[Any, bool]:
        """在锁内对账本做一次事务。fn(doc, now) 原地修改传入的深拷贝并返回任意值。

        返回 (fn 的返回值, 是否写盘)。fn 或校验抛出的异常会原样上抛，且此时不写盘。
        """
        self.root.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.lock_path), timeout=self.lock_timeout)
        try:
            lock.acquire()
        except Timeout as exc:
            raise LedgerLockTimeout(f'cannot lock {self.name} within {self.lock_timeout}s') from exc
        try:
            now = self.clock()
            old = self._load(create_if_missing)
            new = copy.deepcopy(old)
            value = fn(new, now)
            if new == old:
                return value, False
            problems = validate_transition(old, new)
            if problems:
                raise InvariantViolation(problems)
            self._write(new)
            return value, True
        finally:
            lock.release()

    def _load(self, create_if_missing: bool) -> dict:
        if not self.path.exists():
            if self.journal is not None and self.journal.knows_ledger(self.name):
                raise LedgerLostError(f'ledger {self.name} is missing but the journal recorded rounds in it')
            if not create_if_missing:
                raise LedgerLostError(f'ledger {self.name} is missing')
            return sm.new_document(self.key)
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise LedgerCorruptError(f'ledger {self.name} is unreadable: {exc}') from exc
        try:
            doc = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise self._corrupt(raw, f'not valid JSON: {exc}') from exc
        problems = validate_document(doc, self.key)
        if problems:
            raise self._corrupt(raw, '; '.join(problems[:5]))
        if self.journal is not None:
            missing = self.journal.known_rounds(self.name) - {r['round_id'] for r in doc['rounds']}
            if missing:
                raise LedgerLostError(f'ledger {self.name} lacks rounds the journal recorded: {sorted(missing)}')
        return doc

    def _corrupt(self, raw: bytes, why: str) -> LedgerCorruptError:
        """损坏时只备份、不修复：同一份内容只备份一次（文件名带内容哈希）。"""
        backup = self.path.with_name(f'{self.name}.corrupt-{hashlib.sha1(raw).hexdigest()[:8]}')
        try:
            if not backup.exists():
                backup.write_bytes(raw)
        except OSError as exc:
            logger.warning(f'Cannot back up corrupt ledger {self.name}: {exc}')
            backup = None
        logger.error(f'Instance sync ledger {self.name} is corrupt ({why}); original kept, backup: {backup}')
        return LedgerCorruptError(f'ledger {self.name} is corrupt: {why}', str(backup or ''))

    def _write(self, doc: dict) -> None:
        data = json.dumps(doc, ensure_ascii=False, indent=2)
        last: Optional[Exception] = None
        for attempt in range(self.write_retries + 1):
            try:
                with atomic_write(str(self.path), overwrite=True, encoding='utf-8', newline='') as f:
                    f.write(data)
                return
            except PermissionError as exc:
                # 杀毒 / 索引器短暂占用目标文件时 MoveFileEx 会 PermissionError。
                # 退避总共不到半秒，是持锁期间唯一的 sleep；写不进去就如实报错，账本保持写前内容。
                last = exc
                if attempt < self.write_retries:
                    self.sleep(self.write_backoff * (2 ** attempt))
            except OSError as exc:
                raise LedgerWriteError(f'cannot write ledger {self.name}: {exc}') from exc
        raise LedgerWriteError(f'cannot write ledger {self.name}: {last}') from last
