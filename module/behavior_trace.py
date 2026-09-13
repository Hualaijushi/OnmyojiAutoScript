# This Python file uses the following encoding: utf-8
"""行为观测日志（BehaviorTrace）v1。

只读记录关键业务动作（click / swipe / long_click）和任务 episode 耗时，
按 config 与日期写入 ``log/behavior/<config>_<日期>.jsonl``，每行一条 JSON。

设计约束：

- 只记录，不干预。任何内部异常都被吞掉并自禁用，绝不向业务调用方传播。
- 默认关闭。关闭时 ``record()`` 第一时间返回，不建目录、不开文件、不构造事件。
- 不 import Config / Device / Timer / BaseTask，避免循环依赖；配置来源由外部通过
  ``configure_behavior_trace()`` 一次性注入，之后 ``record()`` 不再读配置。
- 仅在自禁用告警时惰性 import 项目 logger：该 import 无环（logger 只依赖标准库和
  rich），且再套一层 try/except，保证告警失败也不影响业务。
- 不使用后台线程 / 异步队列 / 数据库 / fsync。文件行缓冲（buffering=1），每条事件写完
  即刷到 OS，进程被杀也不丢尾部；进程内一把轻量 Lock，防未来 daemon 线程与主线程同时写。
"""

import json
import threading
from datetime import datetime
from pathlib import Path

# 输出根目录，相对项目根（module/logger.py 启动时已 chdir 到根）。测试会替换此值。
_LOG_DIR = Path("log/behavior")


def _now() -> datetime:
    # 单独封装便于测试注入固定时间，验证跨天轮转。
    return datetime.now()


class BehaviorTrace:
    def __init__(self, config_name: str, enabled: bool = False) -> None:
        self._config_name = config_name
        self._enabled = bool(enabled)
        # 内部出错后置位：之后所有 record() 直接返回，不再重试写入。
        self._broken = False
        self._lock = threading.Lock()
        # 最佳努力的重入保护，配合 _broken 一起防 record -> logger -> record 递归。
        self._in_record = False
        # 当前任务名，由 Script.run 通过 set_task 维护，供 ACTION 事件复用。
        self._task = ""
        self._fh = None
        self._fh_date = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def set_task(self, task: str) -> None:
        self._task = task or ""

    def is_recording(self) -> bool:
        """当前调用 record() 是否会真的落盘（enabled 且未因内部错误自禁用）。

        语义与 record() 的首行短路条件一致；record() 自身仍独立判断，本方法只是让
        调用方在关闭态跳过「组装大 extra」（如 swipe 轨迹的几十个点）这类无用功，
        不改变 record() 的任何契约。
        """
        return self._enabled and not self._broken

    def record(
        self,
        event: str,
        *,
        task: str = "",
        action: str = "",
        target: str = "",
        result: str = "ok",
        elapsed_ms: int | float | None = None,
        extra: dict | None = None,
    ) -> None:
        # 关闭或已损坏时第一时间返回：开销约等于一次布尔判断，不做任何 IO 或构造。
        if not self._enabled or self._broken:
            return
        if self._in_record:
            return
        self._in_record = True
        try:
            payload = {
                "ts": _now().astimezone().isoformat(timespec="milliseconds"),
                "config": self._config_name,
                "task": task or self._task,
                "event": event,
                "action": action,
                "target": target,
                "result": result,
            }
            if elapsed_ms is not None:
                payload["elapsed_ms"] = elapsed_ms
            if extra:
                payload["extra"] = extra
            # default=str 兜底不可序列化对象（datetime / 异常 / 项目对象），不让序列化失败传播。
            line = json.dumps(payload, ensure_ascii=False, default=str)
            with self._lock:
                self._write_line(line)
        except BaseException as exc:  # 观测层绝不能把异常抛给业务
            self._mark_broken(exc)
        finally:
            self._in_record = False

    def _write_line(self, line: str) -> None:
        today = _now().date()
        if self._fh is None or self._fh_date != today:
            self._open_handle(today)
        self._fh.write(line + "\n")

    def _open_handle(self, today) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except BaseException:
                pass
            self._fh = None
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOG_DIR / f"{self._config_name}_{today.isoformat()}.jsonl"
        # buffering=1 行缓冲：每条事件写完即刷到 OS（非 fsync），保证进程被杀时不丢尾部，
        # 且省去显式 flush。开销是每条一次 write 系统调用，量级见吞吐测试。
        self._fh = open(path, "a", encoding="utf-8", buffering=1)
        self._fh_date = today

    def _mark_broken(self, exc: BaseException) -> None:
        # 先置位，任何再入的 record() 都会在首行返回；再收尾句柄；最后尽力告警。
        self._broken = True
        if self._fh is not None:
            try:
                self._fh.close()
            except BaseException:
                pass
            self._fh = None
        try:
            from module.logger import logger

            logger.warning(
                f"BehaviorTrace disabled after error: {type(exc).__name__}: {exc}"
            )
        except BaseException:
            pass


_registry_lock = threading.Lock()
_registry: dict[str, BehaviorTrace] = {}


def configure_behavior_trace(config_name: str, enabled: bool) -> BehaviorTrace:
    """在进程启动阶段一次性设置某个 config 的 trace 开关。

    幂等：重复调用只更新 enabled，不重建实例、不重新读磁盘配置。
    """
    with _registry_lock:
        trace = _registry.get(config_name)
        if trace is None:
            trace = BehaviorTrace(config_name, enabled)
            _registry[config_name] = trace
        else:
            trace.set_enabled(enabled)
        return trace


def get_behavior_trace(config_name: str) -> BehaviorTrace:
    """获取进程内 trace 单例；未经 configure 的场景（standalone / 测试）返回默认关闭实例。"""
    with _registry_lock:
        trace = _registry.get(config_name)
        if trace is None:
            trace = BehaviorTrace(config_name, enabled=False)
            _registry[config_name] = trace
        return trace


def reset_behavior_traces() -> None:
    """清空进程内单例并关闭句柄，仅供测试使用。"""
    with _registry_lock:
        for trace in _registry.values():
            if trace._fh is not None:
                try:
                    trace._fh.close()
                except BaseException:
                    pass
        _registry.clear()
