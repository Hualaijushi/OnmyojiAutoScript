# This Python file uses the following encoding: utf-8
"""通用双实例同步核心（D029）。

与具体游戏业务解耦：不 import tasks.*，不碰设备 / 截图 / OCR。业务通过 `SyncAdapter` 接入。
"""

from module.instance_sync.adapter import Evidence, PrepareResult, SyncAdapter, SyncContext
from module.instance_sync.coordinator import (
    NEXT_DEFER, NEXT_DONE, NEXT_RETRY, S_ALREADY, S_COMPLETED, S_FAILED, AckResult, SyncCoordinator, SyncResult,
)
from module.instance_sync.errors import (
    InvariantViolation, LedgerCorruptError, LedgerError, LedgerLockTimeout, LedgerLostError, LedgerWriteError,
    SyncCancelled, SyncError,
)

__all__ = [
    'SyncAdapter', 'SyncContext', 'Evidence', 'PrepareResult', 'SyncCoordinator', 'SyncResult', 'AckResult',
    'S_COMPLETED', 'S_ALREADY', 'S_FAILED', 'NEXT_DONE', 'NEXT_RETRY', 'NEXT_DEFER',
    'SyncError', 'SyncCancelled', 'LedgerError', 'LedgerLockTimeout', 'LedgerCorruptError', 'LedgerLostError',
    'LedgerWriteError', 'InvariantViolation',
]
