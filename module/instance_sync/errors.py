# This Python file uses the following encoding: utf-8
"""双实例同步核心的异常类型。

账本层（LedgerError 家族）的异常由 `SyncCoordinator` 在公共边界转成结果对象；
适配器 / 设备抛出的异常不在这里，核心不吞它们（见 docs/DECISIONS.md D015）。
"""


class SyncError(Exception):
    """同步核心异常基类。"""


class LedgerError(SyncError):
    """账本不可用：调用方应停止本轮业务，不得靠本地残留状态继续。"""


class LedgerLockTimeout(LedgerError):
    """在 lock_timeout 内没拿到账本锁。"""


class LedgerCorruptError(LedgerError):
    """账本不可读 / JSON 损坏 / 结构不合法 / schema_version 未知。原文件不会被覆盖。"""

    def __init__(self, message: str, backup: str = ''):
        super().__init__(message)
        self.backup = backup


class LedgerLostError(LedgerError):
    """账本缺失，或本地 journal 记录过的轮次在账本里不存在。不自动重建。"""


class LedgerWriteError(LedgerError):
    """原子写入失败；账本文件保持写入前的内容。"""


class InvariantViolation(SyncError):
    """某次状态变更违反了账本不变式，没有写入。出现它说明调用代码有缺陷。"""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('; '.join(self.problems))


class SyncCancelled(SyncError):
    """协作式取消：整轮已进入 failed，或本进程被更新的会话取代。

    适配器收到它必须让它继续向上传播（不要在 `except Exception` 里吞掉）。
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
