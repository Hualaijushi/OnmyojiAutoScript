"""单账号轮换流程；界面操作由调用方提供。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from tasks.MetaDemonRotation.progress import RotationProgress, RotationProgressError


Availability = Literal['ready', 'unavailable', 'unknown']
BossState = Literal['current', 'four_ready', 'four_unavailable', 'unknown']


class AccountDriver(Protocol):
    """所有判断均应基于新画面；未知不能按成功或零处理。"""

    def deploy_rental(self, sequence: int) -> Availability: ...
    def fatigue_status(self) -> Availability: ...
    def prepare_current_or_four_star(self) -> BossState: ...
    def challenge(self, on_entered: Callable[[], None]) -> bool | Literal['fatigue', 'popup_unknown']: ...


@dataclass(frozen=True)
class AccountResult:
    completed: bool
    entered: int
    reason: str


def run_account(driver: AccountDriver, progress: RotationProgress, *, account_id: str,
                identity: str, rental_team: int, battle_limit: int) -> AccountResult:
    """先处理已有鬼王，再选择四星；次数按进入战斗统计。"""
    def update(action: str, reason: str = '') -> dict:
        return progress.update(account_id, identity, action, target=battle_limit, reason=reason)

    state = update('read')
    if state['phase'] != 'idle':
        return AccountResult(False, state['entered'], '上次战斗状态未确认，需人工核实')
    if state['entered'] >= battle_limit:
        return AccountResult(True, state['entered'], '已达目标')

    def stop(reason: str) -> AccountResult:
        state = update('stop', reason)
        return AccountResult(False, state['entered'], reason)

    rental = driver.deploy_rental(rental_team)
    if rental != 'ready':
        return stop('租借队伍不可用' if rental == 'unavailable' else '租借队伍状态未确认')

    while True:
        fatigue = driver.fatigue_status()
        if fatigue == 'time_limit':
            return stop('本账号达到运行时长')
        if fatigue != 'ready':
            return stop('疲劳不足' if fatigue == 'unavailable' else '疲劳状态未确认')
        boss = driver.prepare_current_or_four_star()
        if boss == 'four_unavailable':
            return stop('未识别到可召唤的目标鬼王')
        if boss not in {'current', 'four_ready'}:
            return stop('鬼王状态未确认')

        update('begin')
        entered = False

        def on_entered() -> None:
            nonlocal entered
            if entered:
                raise RotationProgressError('同一场战斗重复确认入场')
            update('entered')
            entered = True

        # 失败或异常保留未完成阶段，不能自动猜测是否已进入战斗。
        result = driver.challenge(on_entered)
        if result == 'popup_unknown':
            state = update('read')
            return AccountResult(False, state['entered'], '租借确认弹窗状态未确认，需人工核实')
        if result == 'fatigue' and not entered:
            update('not_entered')
            return stop('疲劳不足')
        if result is not True or not entered:
            state = update('read')
            return AccountResult(False, state['entered'], '战斗未确认结束，需人工核实')
        state = update('finished')
        if state['entered'] >= battle_limit:
            return AccountResult(True, state['entered'], '已达目标')
