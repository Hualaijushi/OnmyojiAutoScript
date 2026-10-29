# This Python file uses the following encoding: utf-8
"""业务适配器协议：同步核心只通过这几个方法碰「游戏」，核心自己不 import 任何 tasks / 设备。

适配器负责：进到操作界面、点一下、看结果、二次核验、崩溃后看游戏现状。
核心负责：什么时候允许点、点之前写什么、结果怎么记、失败怎么传播、预算和重试。

约定：
- `ctx.check_alive()` 在每个游戏操作之前调用；它在整轮已 failed 时抛 `SyncCancelled`，适配器不要吞掉。
- `dispatch` 里只做那一次不可撤销的点击（不要用 click-until 之类会重复点击的封装）；
  任何异常都会被当成「请求可能已经发出」→ `unknown`，不会重发。
- `judge` 只在稳定界面上给证据；没识别到成功提示 / OCR 没读到 / 页面没变化 / 超时，都不是失败证据，应返回 unknown。
- 所有等待都要受 `ctx.remaining()`（总预算）约束；核心不会替适配器中断阻塞调用。
- `await_turn` 是可选钩子（默认直接放行），给「两端有先后顺序」的业务用：在每次写下发送意图之前调用，适配器在这里
  等到轮到本端，可以用 `ctx.wait_until` 看对端的尝试。必须幂等（重试时会再被调用一次）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from module.instance_sync.state_machine import AttemptView

EV_DONE = 'done'
EV_NOT_DONE = 'not_done'
EV_UNKNOWN = 'unknown'


@dataclass(frozen=True)
class Evidence:
    """一次尝试在游戏里的证据。done = 已确认生效；not_done = 已确认没发出去且再发是安全的；其余都是 unknown。"""
    kind: str
    detail: str = ''

    @classmethod
    def done(cls, detail: str = '') -> 'Evidence':
        return cls(EV_DONE, detail)

    @classmethod
    def not_done(cls, detail: str = '') -> 'Evidence':
        return cls(EV_NOT_DONE, detail)

    @classmethod
    def unknown(cls, detail: str = '') -> 'Evidence':
        return cls(EV_UNKNOWN, detail)


@dataclass(frozen=True)
class PrepareResult:
    """导航 + 就绪检查的结果。ok=False 表示这一轮无法进入就绪（安全失败，没有发过任何请求）。"""
    ok: bool
    reason: str = ''


class SyncAdapter(ABC):
    business_id: str = ''

    @abstractmethod
    def protocol_params(self) -> Mapping[str, float]:
        """业务约束，两端必须一致（加入时逐项比对）：retry_wait / budget / min_attempt_cost / max_rounds。"""

    @abstractmethod
    def business_day(self, now: float) -> str:
        """业务日 'YYYY-MM-DD'（由业务的每日重置时间决定，核心不自己猜）。"""

    @abstractmethod
    def prepare(self, ctx: 'SyncContext') -> PrepareResult:
        """进入实际操作界面并确认入口可用（本机账号、目标好友、互赠入口）。不计入总预算，受会合窗口约束。"""

    def await_turn(self, ctx: 'SyncContext') -> bool:
        """每次写下发送意图（prepared）之前调用：True = 轮到本端，可以发；False = 等不到，本轮按 prepare 失败收场。

        返回 False 时本端还没有尝试：整轮是否仍可安全重来，由账本里所有尝试的状态决定（对端若已经有 prepared /
        unknown / done，就是 unsafe，不再自动重来）。默认没有先后顺序，直接放行。
        """
        return True

    @abstractmethod
    def dispatch(self, ctx: 'SyncContext', attempt: AttemptView) -> None:
        """执行那一次不可撤销的操作（只点一次）。"""

    @abstractmethod
    def judge(self, ctx: 'SyncContext', attempt: AttemptView) -> Evidence:
        """dispatch 之后在稳定界面上判定结果。"""

    @abstractmethod
    def verify(self, ctx: 'SyncContext') -> bool:
        """游戏内二次核验（如好友页）。True = 已确认完成。"""

    @abstractmethod
    def inspect_attempt(self, ctx: 'SyncContext', attempt: AttemptView) -> Evidence:
        """崩溃恢复：账本里留着 prepared 的尝试，看游戏现状给证据。只读，不得发送。"""

    def after_wait(self, seconds: float) -> None:
        """核心做完一次较长的纯等待（不截图）之后调用。适配器可在这里重置设备的卡死计时。"""


class SyncContext:
    """适配器拿到的上下文：只读快照 + 协作式取消 + 受控等待，没有可写的账本结构。"""

    def __init__(self, coordinator):
        self._c = coordinator

    @property
    def instance(self) -> str:
        return self._c.instance

    @property
    def round_id(self) -> str:
        return self._c.round_id

    @property
    def params(self) -> Mapping[str, float]:
        return self._c.protocol['params']

    @property
    def rendezvous_deadline_at(self):
        return self._c.rendezvous_deadline_at

    @property
    def deadline_at(self):
        """总预算截止时间（epoch 秒）；双方都 ready 之前是 None。"""
        return self._c.deadline_at

    def now(self) -> float:
        return self._c.clock()

    def remaining(self):
        """距总预算截止还剩多少秒；预算还没开始返回 None。"""
        deadline = self._c.deadline_at
        return None if deadline is None else deadline - self._c.clock()

    def sleep(self, seconds: float) -> None:
        self._c.sleep(seconds)

    def view(self):
        return self._c.view()

    def check_alive(self):
        """整轮已 failed 时抛 SyncCancelled；否则返回最新快照。"""
        return self._c.check_alive()

    def wait_until(self, predicate, timeout: float = None) -> bool:
        """轮询账本直到 predicate(view) 为真（返回 True）或 timeout 到（返回 False）；整轮 failed 则抛 SyncCancelled。"""
        return self._c.wait_until(predicate, timeout)
