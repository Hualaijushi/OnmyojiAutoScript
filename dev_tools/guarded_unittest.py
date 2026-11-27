# This Python file uses the following encoding: utf-8
"""带资源守护的 unittest 运行入口（测试进程树的私人提交内存 / 总时长 / 日志大小上限）。

背景：测试里把截图、点击、时钟都换成 Mock 之后，一个没有退出条件的循环会高速空转，Mock 的调用记录无限增长。
2026-10-31 一次御魂回归把测试进程撑到约 40 GiB 私人提交、系统提交率 98%。被测进程自己的保护（Device 卡死保护、
Timer、虚拟时钟）都可能被测试替换掉，所以守护必须在**被测进程之外**，用真实单调时钟和真实的进程指标。

用法（都用 ``toolkit/python.exe``；``--`` 之后原样交给 ``python -m unittest``）::

    # 相关回归：默认 300 秒 / 3 GiB
    toolkit/python.exe dev_tools/guarded_unittest.py -- tests.test_a tests.test_b
    # 全量：默认 900 秒 / 3 GiB
    toolkit/python.exe dev_tools/guarded_unittest.py --profile full -- discover -s tests

口径与限制：

- 内存指标是**私人提交（Windows ``PrivateUsage`` / psutil ``memory_info().private``）**，对测试进程及其全部后代求和；
  取不到该指标（非 Windows 或 psutil 不提供）时明确失败，不静默换成 Working Set / RSS / 虚拟地址空间。
- 峰值是按 ``--interval`` 秒采样的最大值，**不是**捕获了瞬时真实最高值；采样间隔内的突增可能漏掉。
- 只跟踪并终止本入口启动的进程及其后代（用 psutil ``Process`` 对象，终止前核对进程创建时间，防止 PID 重用误杀）；
  从不按进程名批量处理，不碰 OAS 后端、OCR 服务或其他会话的进程。
- 超限后只停止并报告，**不会自动重跑、不会自动提高阈值**。
- 清理有明确结果：每个被跟踪的进程要被核验为「已退出」（PID + 创建时间）才算清理成功。清理轮数 / 等待有上限，
  不无限重试；仍存活或因权限 / 查询异常无法确认的进程，不会被当作已退出。
- 同一工作区默认只允许一份运行，靠**进程退出即释放的 OS 文件锁**（``guarded_unittest.mutex``）互斥，取得与陈旧记录接管都在
  持锁期间完成；第二份直接被拒绝，不读后删、不覆盖运行记录，也不会结束第一份。运行记录 ``guarded_unittest.lock`` 只是信息，
  记录守护 / 测试进程及已发现后代的 PID + 创建时间。
- **清理失败时运行记录会保留**（状态 ``cleanup_incomplete``，列出未确认退出的进程），下一份运行会拒绝启动并提示人工核对；
  只有确认全部已退出才删除记录。守护进程被强制结束时来不及清理：测试进程 / 已记录的后代仍存活就同样会拒绝下一份运行。
- 进程树靠按间隔采样发现，**不保证**捕获两次采样之间创建、并且已脱离父进程的进程；也不覆盖绕过本入口的手工 ``python -m unittest``。

退出码：0 通过；1 测试失败；2 参数 / 环境不可用；10 超时；11 私人提交超限；12 被中断；13 守护自身异常；
14 已有一份运行在进行（被拒绝）；15 日志超过大小上限；16 清理失败（仍有跟踪的进程存活或无法确认退出，
原始停止原因仍写在摘要里）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_TESTS_FAILED = 1
EXIT_UNAVAILABLE = 2
EXIT_TIMEOUT = 10
EXIT_MEMORY = 11
EXIT_INTERRUPTED = 12
EXIT_GUARD_ERROR = 13
EXIT_REFUSED = 14
EXIT_LOG_SIZE = 15
EXIT_CLEANUP_FAILED = 16

# 初始工程上限，不宣称适合所有套件
DEFAULT_MAX_PRIVATE_GIB = 3.0
PROFILE_TIMEOUT_S = {'related': 300.0, 'full': 900.0}
DEFAULT_INTERVAL_S = 1.0
DEFAULT_MAX_LOG_MIB = 512.0
DEFAULT_PROGRESS_S = 30.0
# 清理有界：最多这么多轮「发现 → 核验 → 请求终止 → 等待」，每轮最多等这么久；超出仍未确认退出就按清理失败处理
CLEANUP_ROUNDS = 6
CLEANUP_WAIT_S = 5.0
# 创建时间比较的容差（秒）：psutil 在不同调用间对同一进程给出的值应完全一致，留一点浮点余量
CREATE_TIME_TOLERANCE_S = 1.0
GIB = 1024 ** 3
MIB = 1024 ** 2


class MetricUnavailable(RuntimeError):
    """取不到私人提交指标。"""


def _import_psutil():
    try:
        import psutil
    except ImportError as exc:                               # pragma: no cover - 依赖缺失时才走到
        raise MetricUnavailable(f'psutil 不可用（requirements.txt 里是 psutil==6.1.1）：{exc}') from exc
    return psutil


def private_commit_bytes(proc) -> int:
    """单个进程的私人提交字节数；字段不存在就报 MetricUnavailable，不换口径。"""
    value = getattr(proc.memory_info(), 'private', None)
    if value is None:
        raise MetricUnavailable('psutil memory_info() 没有 private 字段（只有 Windows 提供私人提交）；'
                                '拒绝用 RSS / Working Set / 虚拟地址空间代替')
    return int(value)


def ensure_metric_available() -> None:
    psutil = _import_psutil()
    private_commit_bytes(psutil.Process())


def _identity(proc) -> tuple[int, float | None]:
    """(PID, 创建时间)：进程身份。创建时间取不到就是 None（此时只能算「身份无法核验」）。"""
    try:
        return proc.pid, proc.create_time()
    except Exception:                                        # noqa: BLE001 - 取不到身份由调用方按「无法确认」处理
        return proc.pid, None


def _classify(proc, psutil) -> tuple[str, str]:
    """('gone' | 'alive' | 'unknown', 原因)。查询失败是 unknown，**不**等于已退出。

    ``is_running()`` 会比对创建时间：PID 被别的进程重用时返回 False，所以不会把无关进程当成跟踪对象。
    """
    try:
        if not proc.is_running():
            return 'gone', ''
        if proc.status() == psutil.STATUS_ZOMBIE:
            return 'gone', 'zombie'
        return 'alive', ''
    except psutil.NoSuchProcess:
        return 'gone', ''
    except Exception as exc:                                 # noqa: BLE001 - 权限 / 其他查询异常：无法确认
        return 'unknown', f'{type(exc).__name__}: {exc}'


@dataclass
class CleanupResult:
    """清理的明确结果。``ok`` 仅当所有跟踪过的进程都被核验为已退出。"""
    killed: list[int] = field(default_factory=list)          # 已发出终止请求的 PID（发出请求 ≠ 已退出）
    gone: list[int] = field(default_factory=list)            # 核验为已退出的 PID
    unresolved: list[dict] = field(default_factory=list)     # 仍存活（alive）或无法确认（unknown）的进程身份
    errors: list[str] = field(default_factory=list)          # 终止 / 等待 / 发现过程中的异常，原样保留
    rounds: int = 0
    discovery_failed: bool = False                           # 后代发现失败：无法保证没有漏掉的后代

    @property
    def ok(self) -> bool:
        return not self.unresolved and not self.discovery_failed

    @property
    def status(self) -> str:
        if self.ok:
            return 'confirmed'
        return 'alive' if any(u['state'] == 'alive' for u in self.unresolved) else 'unconfirmed'

    def describe(self) -> str:
        parts = [f'清理未完成（{self.status}）']
        for u in self.unresolved:
            parts.append(f'PID {u["pid"]}（创建时间 {u["create_time"]}）{u["state"]}'
                         f'{"：" + u["reason"] if u.get("reason") else ""}')
        parts += self.errors
        return '；'.join(parts)

    def as_dict(self) -> dict:
        return {'status': self.status, 'ok': self.ok, 'rounds': self.rounds, 'killed': self.killed,
                'gone': self.gone, 'unresolved': self.unresolved, 'errors': self.errors,
                'discovery_failed': self.discovery_failed}

    def lock_entries(self, root_pid: int | None) -> list[dict]:
        """写进运行记录的未确认进程。后代发现失败时没有可核验的身份，写一条 sticky 记录，要人工确认后才能放行。"""
        entries = [dict(u) for u in self.unresolved]
        if self.discovery_failed or (not self.ok and not entries):
            entries.append({'pid': root_pid, 'create_time': None, 'state': 'unknown', 'sticky': True,
                            'reason': '无法列出后代 / 清理结果无法核验，需人工确认没有残留进程后手工删除运行记录'})
        return entries

    @classmethod
    def from_failure(cls, exc: BaseException, sampler, root_pid: int | None) -> 'CleanupResult':
        """清理过程本身异常：已跟踪的进程一律记为无法确认；异常原样保留。"""
        result = cls(errors=[f'清理过程异常：{type(exc).__name__}: {exc}'])
        try:
            identities = sampler.tracked_identities() if sampler is not None else []
        except Exception as inner:                           # noqa: BLE001
            identities = []
            result.errors.append(f'读取跟踪列表失败：{type(inner).__name__}: {inner}')
        for pid, create_time in identities:
            result.unresolved.append({'pid': pid, 'create_time': create_time, 'state': 'unknown',
                                      'reason': '清理过程异常，未能核验是否已退出'})
        if not result.unresolved and root_pid is not None:
            result.unresolved.append({'pid': root_pid, 'create_time': None, 'state': 'unknown', 'sticky': True,
                                      'reason': '清理过程异常且没有可核验的跟踪记录'})
        return result


class TreeSampler:
    """跟踪本入口启动的根进程及其后代，按进程返回私人提交，并负责终止。

    ``tracked`` 里放 psutil.Process 对象（带创建时间，用于识别 PID 重用）。后代一旦被看到就一直记着，
    即使它的父进程先退出（孤儿）也继续计入、继续可终止——这些都是测试进程树里的进程，而不是按名字找来的。
    后代靠采样发现：两次采样之间创建、并且已脱离父进程的进程可能没有被看到（保证范围见模块文档）。
    """

    def __init__(self, root_pid: int, *, cleanup_rounds: int = CLEANUP_ROUNDS, cleanup_wait_s: float = CLEANUP_WAIT_S):
        self._psutil = _import_psutil()
        self.root = self._psutil.Process(root_pid)
        self.tracked: dict[int, object] = {root_pid: self.root}
        self.cleanup_rounds = cleanup_rounds
        self.cleanup_wait_s = cleanup_wait_s

    def _prune(self) -> None:
        for pid, proc in list(self.tracked.items()):
            try:
                alive = proc.is_running() and proc.status() != self._psutil.STATUS_ZOMBIE
            except self._psutil.NoSuchProcess:
                alive = False
            if not alive:
                del self.tracked[pid]

    def _discover(self) -> None:
        for proc in list(self.tracked.values()):
            try:
                children = proc.children(recursive=True)
            except self._psutil.NoSuchProcess:
                continue
            for child in children:
                self.tracked.setdefault(child.pid, child)

    def tracked_identities(self) -> list[tuple[int, float | None]]:
        return sorted(_identity(p) for p in self.tracked.values())

    def sample(self) -> dict[int, int]:
        """返回 {pid: 私人提交字节}；已退出的进程不计入。"""
        self._prune()
        self._discover()
        out: dict[int, int] = {}
        for pid, proc in list(self.tracked.items()):
            try:
                out[pid] = private_commit_bytes(proc)
            except self._psutil.NoSuchProcess:
                self.tracked.pop(pid, None)
        return out

    def _wait(self, procs: list, timeout: float) -> None:
        self._psutil.wait_procs(procs, timeout=timeout)

    def terminate_tree(self) -> CleanupResult:
        """终止跟踪到的全部进程并**核验**是否真的退出。有界：最多 ``cleanup_rounds`` 轮、每轮最多等 ``cleanup_wait_s``。

        返回的 ``unresolved`` 是仍存活或无法确认的进程身份；发出 kill 请求、或 PID 出现在 ``killed`` 里都不代表已退出，
        只有 ``gone`` 里的才是核验过的。查询 / 权限异常一律记为无法确认，绝不当作已退出。
        """
        psutil = self._psutil
        result = CleanupResult()
        gone: set[int] = set()
        for _ in range(self.cleanup_rounds):
            self._discover_for_cleanup(result)
            live = []
            for pid, proc in list(self.tracked.items()):
                state, _reason = _classify(proc, psutil)
                if state == 'gone':
                    gone.add(pid)
                    del self.tracked[pid]
                    continue
                live.append(proc)
                try:
                    proc.kill()                              # psutil 在 kill 前再核对一次身份，PID 被重用则抛 NoSuchProcess
                    if pid not in result.killed:
                        result.killed.append(pid)
                except psutil.NoSuchProcess:
                    pass                                     # 下一轮 / 最终核验会确认它是否真的不在了
                except Exception as exc:                     # noqa: BLE001 - 终止失败：记录，进程留在 tracked 里等待核验
                    result.errors.append(f'PID {pid} 终止请求失败：{type(exc).__name__}: {exc}')
            if not live:
                break
            result.rounds += 1
            try:
                self._wait(live, self.cleanup_wait_s)
            except Exception as exc:                         # noqa: BLE001
                result.errors.append(f'等待进程退出时异常：{type(exc).__name__}: {exc}')
        for pid, proc in list(self.tracked.items()):         # 最终核验：以此时的状态为准，而不是以「发过 kill」为准
            state, reason = _classify(proc, psutil)
            if state == 'gone':
                gone.add(pid)
                del self.tracked[pid]
            else:
                _, create_time = _identity(proc)
                result.unresolved.append({'pid': pid, 'create_time': create_time, 'state': state, 'reason': reason})
        result.gone = sorted(gone)
        return result

    def _discover_for_cleanup(self, result: CleanupResult) -> None:
        for proc in list(self.tracked.values()):
            try:
                children = proc.children(recursive=True)
            except self._psutil.NoSuchProcess:
                continue
            except Exception as exc:                         # noqa: BLE001 - 不能列出后代：无法保证没有漏掉的进程
                result.discovery_failed = True
                result.errors.append(f'PID {proc.pid} 无法列出后代：{type(exc).__name__}: {exc}')
                continue
            for child in children:
                self.tracked.setdefault(child.pid, child)


# ----------------------------------------------------------------------------------------------
# 锁：同一工作区只允许一份运行
# ----------------------------------------------------------------------------------------------

def identity_state(pid: int | None, create_time: float | None) -> str:
    """'alive'：PID 存在且创建时间一致；'gone'：不存在，或 PID 已被别的进程重用；'unknown'：无法核验（权限 / 缺创建时间）。"""
    if pid is None:
        return 'gone'
    psutil = _import_psutil()
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return 'gone'
        if create_time is None:
            return 'unknown'
        if abs(proc.create_time() - create_time) > CREATE_TIME_TOLERANCE_S:
            return 'gone'
        return 'gone' if proc.status() == psutil.STATUS_ZOMBIE else 'alive'
    except psutil.NoSuchProcess:
        return 'gone'
    except Exception:                                        # noqa: BLE001 - 查询失败不等于已退出
        return 'unknown'


def process_identity_alive(pid: int | None, create_time: float | None) -> bool:
    return identity_state(pid, create_time) == 'alive'


def _create_time(pid: int) -> float:
    return _import_psutil().Process(pid).create_time()


def _try_os_lock(fd: int) -> bool:
    """非阻塞地取得文件的独占 OS 锁；持有者进程退出（含被强制结束）时系统自动释放。"""
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:                                                # pragma: no cover - 本项目只在 Windows 上跑
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class LockRefused(Exception):
    def __init__(self, message: str, info: dict | None):
        super().__init__(message)
        self.info = info


class RunLock:
    """同一工作区一份运行。职责分开：

    - ``<lock_dir>/guarded_unittest.mutex``：资源锁。独占 OS 文件锁，守护进程存活期间一直持有，进程退出即释放。
      取得锁与接管陈旧记录都在持锁期间完成，所以两个入口不可能同时接管；拿不到锁就直接拒绝，不读后删。
    - ``<lock_dir>/guarded_unittest.lock``：运行记录（JSON，仅供信息与人工核对）：守护 / 测试进程及已发现后代的
      PID + 创建时间。只有持有资源锁的一方写它，原子替换。
    """

    def __init__(self, lock_dir: Path):
        self.dir = Path(lock_dir)
        self.path = self.dir / 'guarded_unittest.lock'
        self.mutex_path = self.dir / 'guarded_unittest.mutex'
        self.me = {'guard_pid': os.getpid(), 'guard_create_time': _create_time(os.getpid())}
        self.held = False
        self._fd: int | None = None
        self._info: dict = {}

    # -- 读写运行记录 -------------------------------------------------------------------------
    def _read(self) -> dict | None:
        for _ in range(3):
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                return None
            except (ValueError, OSError):
                time.sleep(0.2)
        raise LockRefused(f'运行记录无法解析，不擅自判定为陈旧：{self.path}（确认没有测试在跑后手工删除）', None)

    def _peek(self) -> dict | None:
        """只为了在拒绝时展示已有运行信息；读不到不报错。"""
        try:
            return self._read()
        except LockRefused:
            return None

    def _write(self, info: dict) -> None:
        tmp = self.path.with_suffix('.lock.tmp')
        tmp.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
        for attempt in range(20):                            # Windows 上别的进程正好在读时 replace 会 PermissionError
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)

    @staticmethod
    def _active(info: dict) -> bool:
        """记录里的守护进程或测试进程是否仍是同一个进程（PID + 创建时间）；无法核验也按「仍活着」算。

        能走到这里说明我们已经拿到资源锁，所以记录里仍存活的「运行中」守护进程只可能是没有用资源锁的旧版本入口；
        ``cleanup_incomplete`` 记录是守护自己释放资源锁后留下的，守护进程是否还活着无关紧要，要看的是被跟踪的进程。
        """
        roles = ('test',) if info.get('state') == 'cleanup_incomplete' else ('guard', 'test')
        return any(identity_state(info.get(f'{role}_pid'), info.get(f'{role}_create_time')) != 'gone'
                   for role in roles)

    def _blocking_reason(self, info: dict) -> str | None:
        if self._active(info):
            return '记录中的守护 / 测试进程仍存活或无法核验是否已退出'
        for entry in info.get('tracked') or []:
            if entry.get('sticky') or identity_state(entry.get('pid'), entry.get('create_time')) != 'gone':
                return f'记录中跟踪的进程 PID {entry.get("pid")} 仍存活或无法核验是否已退出'
        if info.get('state') == 'cleanup_incomplete' and not info.get('tracked'):
            return '上一次运行标记为清理未完成，但没有可核验的进程身份'
        return None

    # -- 取得 / 更新 / 释放 -------------------------------------------------------------------
    def acquire(self, **extra) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.mutex_path, os.O_CREAT | os.O_RDWR)
        if not _try_os_lock(fd):
            os.close(fd)
            raise LockRefused('同一工作区已有一份受守护的测试在运行（运行互斥被占用）', self._peek())
        try:
            info = self._read()
            if info is not None:
                reason = self._blocking_reason(info)
                if reason:
                    raise LockRefused(f'已有运行记录需要先处理：{reason}', info)
            self._info = {**self.me, 'test_pid': None, 'test_create_time': None, 'state': 'running', 'tracked': [],
                          **extra}
            self._write(self._info)
        except BaseException:
            os.close(fd)                                     # 关闭句柄即释放 OS 锁；不动运行记录
            raise
        self._fd = fd
        self.held = True

    def update(self, **fields) -> None:
        self._info.update(fields)
        self._write(self._info)

    def _close_mutex(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.held = False

    def release(self) -> str | None:
        """确认测试进程树已全部退出后调用：删除运行记录并释放资源锁。返回告警文本（删除失败时），否则 None。"""
        warning = None
        if self.held:
            for attempt in range(20):
                try:
                    self.path.unlink()
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if attempt == 19:
                        warning = f'运行记录未能删除（{self.path}）；其中的进程均已退出，下次启动会按陈旧记录处理'
                    time.sleep(0.05)
        self._close_mutex()
        return warning

    def retain_incomplete(self, unresolved: list[dict]) -> str | None:
        """清理未完成：保留并更新运行记录（列出未确认退出的进程），再释放资源锁。下一份运行会因记录而拒绝启动。"""
        error = None
        if self.held:
            try:
                self.update(state='cleanup_incomplete', tracked=unresolved)
            except OSError as exc:
                error = f'运行记录未能更新：{exc}'
        self._close_mutex()
        return error


# ----------------------------------------------------------------------------------------------
# 运行
# ----------------------------------------------------------------------------------------------

_CASE_RE = re.compile(r'(\w+) \(([\w.]+\.\w+)\)')


def last_case_line(log_path: Path, tail_bytes: int = 64 * 1024) -> str | None:
    """从日志尾部找最后一个 unittest -v 打出的用例名（卡住时它就是正在跑的那个）。"""
    try:
        size = log_path.stat().st_size
        with open(log_path, 'rb') as f:
            f.seek(max(0, size - tail_bytes))
            text = f.read().decode('utf-8', errors='replace')
    except OSError:
        return None
    matches = _CASE_RE.findall(text)
    if not matches:
        return None
    name, where = matches[-1]
    return f'{name} ({where})'


def with_verbose(unittest_args: list[str]) -> list[str]:
    """unittest 要 ``-v`` 才会在每个用例开始时写出用例名；``discover`` 必须是第一个参数，所以 -v 放它后面。"""
    if any(a in ('-v', '--verbose', '-q', '--quiet') for a in unittest_args):
        return list(unittest_args)
    if unittest_args and unittest_args[0].lower() == 'discover':
        return [unittest_args[0], '-v', *unittest_args[1:]]
    return ['-v', *unittest_args]


@dataclass
class Summary:
    command: list[str]
    guard_pid: int
    test_pid: int | None = None
    started: str = ''
    finished: str = ''
    elapsed_s: float = 0.0
    peak_private_mib: float = 0.0              # 采样峰值（整棵树合计）
    peak_samples: int = 0
    peak_process_count: int = 0
    exit_code: int | None = None               # 本入口的退出码
    test_returncode: int | None = None         # 测试进程自己的退出码
    stop_reason: str = ''
    detail: str = ''
    log: str = ''
    last_case: str | None = None
    killed_pids: list[int] = field(default_factory=list)   # 已发出终止请求的 PID（发出请求不等于已退出，见 cleanup）
    limits: dict = field(default_factory=dict)
    original_exit_code: int | None = None      # 清理失败时：没有清理问题本应得到的退出码
    cleanup: dict = field(default_factory=dict)  # 清理结果：status / unresolved / errors / gone ...

    def render(self) -> str:
        return '\n'.join([
            '[guard] ===== 摘要 =====',
            f'[guard] 命令     : {" ".join(self.command)}',
            f'[guard] 测试 PID : {self.test_pid}（守护 PID {self.guard_pid}）',
            f'[guard] 起止     : {self.started} -> {self.finished}，耗时 {self.elapsed_s:.1f}s',
            f'[guard] 私人提交 : 采样峰值 {self.peak_private_mib:.0f} MiB（整棵树合计，{self.peak_process_count} 个进程时；'
            f'{self.peak_samples} 次采样，非瞬时最高值）',
            f'[guard] 退出码   : {self.exit_code}（测试进程 {self.test_returncode}）',
            f'[guard] 停止原因 : {self.stop_reason}{"：" + self.detail if self.detail else ""}',
            f'[guard] 最后用例 : {self.last_case}',
            f'[guard] 已请求终止: {self.killed_pids or "无"}',
            f'[guard] 清理结果 : {self.cleanup.get("status", "无需清理")}'
            f'（核验已退出 {self.cleanup.get("gone", [])}）',
            f'[guard] 日志     : {self.log}',
            *self._cleanup_failure_lines(),
        ])

    def _cleanup_failure_lines(self) -> list[str]:
        if not self.cleanup or self.cleanup.get('ok', True):
            return []
        lines = [f'[guard] !!! 清理失败：本入口启动的进程没有全部确认退出，退出码 {self.exit_code}'
                 f'（原始停止原因 {self.stop_reason}，其对应退出码 {self.original_exit_code}）']
        for u in self.cleanup.get('unresolved', []):
            lines.append(f'[guard] !!! 未确认退出: PID {u.get("pid")} 创建时间 {u.get("create_time")} '
                         f'状态 {u.get("state")}{"，" + u["reason"] if u.get("reason") else ""}')
        lines += [f'[guard] !!! {e}' for e in self.cleanup.get('errors', [])]
        lines.append(f'[guard] !!! 运行记录已保留：{self.cleanup.get("lock_retained")}；下一份运行会被拒绝，'
                     '请人工核对上述进程（确认已退出或无关）后再启动')
        return lines


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def run_guarded(
    unittest_args: list[str],
    *,
    profile: str = 'related',
    timeout_s: float | None = None,
    max_private_gib: float = DEFAULT_MAX_PRIVATE_GIB,
    interval_s: float = DEFAULT_INTERVAL_S,
    max_log_mib: float = DEFAULT_MAX_LOG_MIB,
    progress_s: float = DEFAULT_PROGRESS_S,
    log_dir: Path | None = None,
    log_name: str | None = None,
    overwrite: bool = False,
    lock_dir: Path | None = None,
    cwd: Path | None = None,
    sampler_factory=TreeSampler,
    out=print,
) -> Summary:
    """启动受守护的 unittest 并返回摘要（摘要里有退出码）。``sampler_factory`` 供测试注入受控的采样器。"""
    timeout_s = PROFILE_TIMEOUT_S[profile] if timeout_s is None else timeout_s
    log_dir = Path(log_dir) if log_dir else REPO / 'log' / 'test_runs'
    lock_dir = Path(lock_dir) if lock_dir else REPO / 'log' / 'test_runs'
    cwd = Path(cwd) if cwd else REPO
    command = [sys.executable, '-u', '-m', 'unittest', *with_verbose(unittest_args)]
    summary = Summary(command=command, guard_pid=os.getpid(),
                      limits={'max_private_gib': max_private_gib, 'timeout_s': timeout_s,
                              'interval_s': interval_s, 'max_log_mib': max_log_mib, 'profile': profile})

    try:
        ensure_metric_available()
    except MetricUnavailable as exc:
        summary.exit_code, summary.stop_reason, summary.detail = EXIT_UNAVAILABLE, 'metric_unavailable', str(exc)
        return summary

    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = log_dir / (log_name or f'{profile}_{stamp}_{os.getpid()}.log')
    if log_path.exists() and not overwrite:
        summary.exit_code, summary.stop_reason = EXIT_UNAVAILABLE, 'log_exists'
        summary.detail = f'日志已存在，不覆盖（要覆盖请显式 --overwrite）：{log_path}'
        return summary
    summary.log = str(log_path)

    lock = RunLock(lock_dir)
    try:
        lock.acquire(command=command, started=_now(), log=str(log_path))
    except LockRefused as exc:
        summary.exit_code, summary.stop_reason = EXIT_REFUSED, 'another_run_active'
        summary.detail = f'{exc}；已有运行信息：{json.dumps(exc.info, ensure_ascii=False) if exc.info else "无"}'
        return summary

    sampler = None
    child = None
    t0 = time.monotonic()
    started_wall = time.time()
    summary.started = _now()
    reason = None
    try:
        env = dict(os.environ, PYTHONUNBUFFERED='1')
        with open(log_path, 'wb') as log_file:
            child = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                     stdout=log_file, stderr=subprocess.STDOUT)
            summary.test_pid = child.pid
            try:
                lock.update(test_pid=child.pid, test_create_time=_create_time(child.pid))
            except Exception:                                  # noqa: BLE001 - 极快退出的测试进程可能已取不到创建时间
                lock.update(test_pid=child.pid)
            out(f'[guard] 测试 PID {child.pid}；上限 私人提交 {max_private_gib} GiB / {timeout_s:.0f}s / '
                f'日志 {max_log_mib:.0f} MiB；日志 {log_path}')
            try:
                sampler = sampler_factory(child.pid)
            except Exception:                                  # noqa: BLE001 - 进程已经退出：没有可跟踪的了
                if child.poll() is None:
                    raise
                sampler = None
            last_progress = t0
            last_tracked = None
            while True:
                samples = sampler.sample() if sampler is not None else {}
                total = sum(samples.values())
                if total > summary.peak_private_mib * MIB:
                    summary.peak_private_mib = total / MIB
                    summary.peak_process_count = len(samples)
                summary.peak_samples += 1
                if sampler is not None:
                    # 把已发现的后代身份尽早写进运行记录：守护被强制结束时，下一份运行仍能据此识别残留进程。
                    # 这是尽力而为的附加信息，写失败不影响本次运行；最终清理结果另行、强制地写入。
                    tracked = sampler.tracked_identities()
                    if tracked != last_tracked:
                        try:
                            lock.update(tracked=[{'pid': p, 'create_time': c} for p, c in tracked])
                            last_tracked = tracked
                        except OSError:
                            pass
                if child.poll() is not None:
                    break
                elapsed = time.monotonic() - t0
                if total > max_private_gib * GIB:
                    reason = ('memory_limit', f'整棵测试进程树私人提交合计 {total / GIB:.2f} GiB > {max_private_gib} GiB'
                                              f'（{len(samples)} 个进程：{ {p: round(v / MIB) for p, v in samples.items()} } MiB）')
                    break
                if elapsed > timeout_s:
                    reason = ('timeout', f'运行 {elapsed:.0f}s > {timeout_s:.0f}s')
                    break
                if log_path.stat().st_size > max_log_mib * MIB:
                    reason = ('log_size', f'日志 > {max_log_mib:.0f} MiB')
                    break
                if progress_s and time.monotonic() - last_progress >= progress_s:
                    last_progress = time.monotonic()
                    out(f'[guard] {elapsed:.0f}s 私人提交 {total / MIB:.0f} MiB，最后用例 {last_case_line(log_path)}')
                try:
                    child.wait(timeout=interval_s)
                except subprocess.TimeoutExpired:
                    pass
    except KeyboardInterrupt:
        # 清理在 finally 里做；以「被中断」的非零退出码和摘要结束，不当作通过，也不继续等测试
        reason = ('interrupted', '收到 Ctrl+C / 中断')
    except Exception as exc:                                   # noqa: BLE001 - 监控器自身异常
        reason = ('guard_error', f'{type(exc).__name__}: {exc}')
        summary.detail = traceback.format_exc()
    finally:
        # 清理有明确结果；原始停止原因（reason）与清理结果分开保存，谁也不覆盖谁
        cleanup = _terminate_tree(sampler, child)
        summary.cleanup = cleanup.as_dict()
        summary.killed_pids = list(cleanup.killed)
        if cleanup.ok and cleanup.killed and reason is None:
            summary.detail = f'测试结束后仍有后台进程 {cleanup.killed}，已终止并确认退出'
        summary.finished = _now()
        summary.elapsed_s = time.monotonic() - t0
        summary.test_returncode = child.poll() if child is not None else None
        summary.last_case = last_case_line(log_path)
        _finish(summary, reason, cleanup)
        # 只有确认测试进程及其后代都已退出才释放运行锁；否则保留记录，让下一份运行拒绝启动并提示人工核对
        if cleanup.ok:
            warning = lock.release()
        else:
            warning = lock.retain_incomplete(cleanup.lock_entries(summary.test_pid))
            summary.cleanup['lock_retained'] = str(lock.path)
        if warning:
            summary.cleanup['lock_warning'] = warning
        _write_summary(summary, log_path)
    return summary


def _terminate_tree(sampler, child) -> CleanupResult:
    """终止并核验本入口启动的进程树；任何情况下都返回明确结果，绝不抛出（KeyboardInterrupt 除外）。"""
    root_pid = child.pid if child is not None else None
    try:
        if sampler is None and child is not None and child.poll() is None:
            sampler = TreeSampler(child.pid)                   # 采样器没建起来、测试进程却还活着：用真实采样器兜底
        if sampler is None:
            return CleanupResult()                             # 测试进程根本没启动 / 启动即退出且没有可跟踪的
        return sampler.terminate_tree()
    except Exception as exc:                                   # noqa: BLE001 - 清理自身异常：记为无法确认，不当作成功
        return CleanupResult.from_failure(exc, sampler, root_pid)


def _finish(summary: Summary, reason, cleanup: CleanupResult) -> None:
    if reason is not None:
        name, detail = reason
        code = {'timeout': EXIT_TIMEOUT, 'memory_limit': EXIT_MEMORY, 'interrupted': EXIT_INTERRUPTED,
                'guard_error': EXIT_GUARD_ERROR, 'log_size': EXIT_LOG_SIZE}[name]
        summary.stop_reason, summary.exit_code = name, code
        if name != 'guard_error' or not summary.detail:
            summary.detail = detail
    elif summary.test_returncode == 0:
        summary.stop_reason, summary.exit_code = 'completed', EXIT_OK
    else:
        summary.stop_reason, summary.exit_code = 'tests_failed', EXIT_TESTS_FAILED
        summary.detail = f'测试进程退出码 {summary.test_returncode}'
    if not cleanup.ok:
        # 清理没成功：不报通过，也不被原始原因对应的退出码掩盖；原始原因与退出码另存
        summary.original_exit_code = summary.exit_code
        summary.exit_code = EXIT_CLEANUP_FAILED


def _write_summary(summary: Summary, log_path: Path) -> None:
    try:
        path = log_path.with_suffix(log_path.suffix + '.summary.json')
        path.write_text(json.dumps(summary.__dict__, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='guarded_unittest.py', description='带资源守护的 unittest 运行入口；-- 之后的参数原样交给 python -m unittest',
        epilog='示例: toolkit/python.exe dev_tools/guarded_unittest.py --profile full -- discover -s tests')
    p.add_argument('--profile', choices=sorted(PROFILE_TIMEOUT_S), default='related',
                   help='related=相关回归（默认 300s）；full=全量（默认 900s）')
    p.add_argument('--timeout-s', type=float, default=None, help='实际总时限（秒），覆盖 profile 默认值')
    p.add_argument('--max-private-gib', type=float, default=DEFAULT_MAX_PRIVATE_GIB,
                   help=f'测试进程树合计私人提交上限（GiB，默认 {DEFAULT_MAX_PRIVATE_GIB}）')
    p.add_argument('--interval', type=float, default=DEFAULT_INTERVAL_S, help='采样间隔（秒，默认 1）')
    p.add_argument('--max-log-mib', type=float, default=DEFAULT_MAX_LOG_MIB, help='日志大小上限（MiB）')
    p.add_argument('--progress-s', type=float, default=DEFAULT_PROGRESS_S, help='进度行间隔（秒，0=不打印）')
    p.add_argument('--log-dir', type=Path, default=None, help='日志目录，默认 <repo>/log/test_runs')
    p.add_argument('--log-name', default=None, help='日志文件名，默认 <profile>_<时间>_<PID>.log')
    p.add_argument('--overwrite', action='store_true', help='允许覆盖同名日志（默认拒绝）')
    p.add_argument('--lock-dir', type=Path, default=None, help='锁文件目录，默认 <repo>/log/test_runs')
    p.add_argument('--cwd', type=Path, default=None, help='测试进程工作目录，默认仓库根')
    p.add_argument('unittest_args', nargs=argparse.REMAINDER, help='-- 之后：python -m unittest 的参数')
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unittest_args = list(args.unittest_args)
    if unittest_args[:1] == ['--']:
        unittest_args = unittest_args[1:]
    if not unittest_args:
        print('[guard] 缺少 unittest 参数（例: -- discover -s tests 或 -- tests.test_x）', file=sys.stderr)
        return EXIT_UNAVAILABLE
    if args.max_private_gib <= 0 or args.interval <= 0 or (args.timeout_s is not None and args.timeout_s <= 0):
        print('[guard] 上限 / 间隔必须为正数', file=sys.stderr)
        return EXIT_UNAVAILABLE
    summary = run_guarded(
        unittest_args, profile=args.profile, timeout_s=args.timeout_s, max_private_gib=args.max_private_gib,
        interval_s=args.interval, max_log_mib=args.max_log_mib, progress_s=args.progress_s, log_dir=args.log_dir,
        log_name=args.log_name, overwrite=args.overwrite, lock_dir=args.lock_dir, cwd=args.cwd)
    print(summary.render())
    return summary.exit_code if summary.exit_code is not None else EXIT_GUARD_ERROR


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        # 清理阶段又被中断：测试进程可能还没清完，明确提示而不是当作成功
        print('[guard] 清理阶段再次被中断；请核对摘要里的测试 PID 是否仍在运行', file=sys.stderr)
        raise SystemExit(EXIT_INTERRUPTED)
