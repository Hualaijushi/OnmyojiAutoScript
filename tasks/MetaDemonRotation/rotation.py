"""独立账号轮换协调；不写入既有每日和组队觉醒状态。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tasks.MetaDemonRotation.engine import AccountDriver, AccountResult, run_account
from tasks.MetaDemonRotation.progress import RotationProgress, account_identity


@dataclass(frozen=True)
class RotationResult:
    account_id: str
    completed: bool
    entered: int | None
    reason: str


def run_rotation(accounts: Iterable, switcher, progress: RotationProgress,
                 driver_factory: Callable, *, rental_team: int, battle_limit: int) -> list[RotationResult]:
    """按既有账号顺序切号；不确定的战斗中断本轮以免在战斗中切号。"""
    results = []
    for account in accounts:
        if not getattr(account, 'enabled', True):
            results.append(RotationResult(account.account_id, False, None, '账号资料不完整，跳过'))
            continue
        identity = account_identity(account.instance, account.position, account.login_account,
                                    account.server, account.character)
        state = progress.update(account.account_id, identity, 'read', target=battle_limit)
        if state['phase'] != 'idle':
            results.append(RotationResult(account.account_id, False, state['entered'],
                                          '上次战斗状态未确认，停止本轮'))
            break
        if state['entered'] >= battle_limit:
            results.append(RotationResult(account.account_id, True, state['entered'], '今日已达目标'))
            continue
        switched = switcher.ensure_account(account)
        if not switched.success:
            state = progress.update(account.account_id, identity, 'stop', target=battle_limit, reason='切号失败')
            results.append(RotationResult(account.account_id, False, state['entered'], '切号失败'))
            break
        try:
            outcome: AccountResult = run_account(driver_factory(account), progress,
                                                  account_id=account.account_id, identity=identity,
                                                  rental_team=rental_team, battle_limit=battle_limit)
        except Exception as exc:
            state = progress.update(account.account_id, identity, 'read', target=battle_limit)
            if state['phase'] == 'idle':
                state = progress.update(account.account_id, identity, 'stop', target=battle_limit,
                                        reason=f'执行失败：{type(exc).__name__}')
            results.append(RotationResult(account.account_id, False, state['entered'],
                                          f'执行失败：{type(exc).__name__}'))
            # 无法确认是否仍在战斗或危险页面，不能擅自切号。
            break
        results.append(RotationResult(account.account_id, outcome.completed, outcome.entered, outcome.reason))
        if progress.update(account.account_id, identity, 'read', target=battle_limit)['phase'] != 'idle':
            break
        if '未确认' in outcome.reason:
            break
    return results
