"""独立账号轮换协调；不写入既有每日和组队觉醒状态。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from module.exception import GamePageUnknownError, GameStuckError
from module.logger import logger
from tasks.MetaDemonRotation.engine import AccountDriver, AccountResult, run_account
from tasks.MetaDemonRotation.progress import RotationProgress, account_identity


@dataclass(frozen=True)
class RotationResult:
    account_id: str
    completed: bool
    entered: int | None
    reason: str


def run_rotation(accounts: Iterable, switcher, progress: RotationProgress,
                 driver_factory: Callable, *, rental_team: int, battle_limit: int,
                 recover_account: Callable | None = None,
                 resume_account: Callable | None = None) -> list[RotationResult]:
    """按既有账号顺序切号；不确定的战斗中断本轮以免在战斗中切号。"""
    results = []
    for account in accounts:
        if not getattr(account, 'enabled', True):
            results.append(RotationResult(account.account_id, False, None, '账号资料不完整，跳过'))
            continue
        identity = account_identity(account.instance, account.position, account.login_account,
                                    account.server, account.character)
        state = progress.update(account.account_id, identity, 'read', target=battle_limit)
        resumed = False
        if state['phase'] != 'idle':
            try:
                if resume_account is None or resume_account(account) is not True:
                    results.append(RotationResult(account.account_id, False, state['entered'],
                                                  '上次战斗状态未确认，庭院账号核对未通过，停止本轮'))
                    break
                state = progress.update(account.account_id, identity, 'resume_from_courtyard',
                                        target=battle_limit, expected_state=state)
                resumed = True
                logger.info('[超鬼王轮换] 账号=%s 庭院核对通过，保留场次=%s，解除旧战斗标记',
                            account.account_id, state['entered'])
            except Exception as exc:
                results.append(RotationResult(account.account_id, False, state['entered'],
                                              f'庭院续刷未确认：{type(exc).__name__}，停止本轮'))
                break
        if state['entered'] >= battle_limit:
            results.append(RotationResult(account.account_id, True, state['entered'], '本轮已达目标'))
            continue
        # 恢复入口已通过新画面核对，无需再走普通切号入口。
        if not resumed and not switcher.ensure_account(account).success:
            state = progress.update(account.account_id, identity, 'stop', target=battle_limit, reason='切号失败')
            results.append(RotationResult(account.account_id, False, state['entered'], '切号失败'))
            break
        try:
            driver = driver_factory(account)
            unknown_restarts = 0
            stuck_restarts = 0
            while True:
                try:
                    outcome: AccountResult = run_account(driver, progress,
                                                          account_id=account.account_id, identity=identity,
                                                          rental_team=rental_team, battle_limit=battle_limit)
                    break
                except (GamePageUnknownError, GameStuckError) as exc:
                    state = progress.update(account.account_id, identity, 'read', target=battle_limit)
                    if state['phase'] != 'idle' or state['entered'] >= battle_limit or recover_account is None:
                        raise
                    if isinstance(exc, GamePageUnknownError):
                        if unknown_restarts >= 3:
                            raise
                        unknown_restarts += 1
                        attempt, limit = unknown_restarts, 3
                    else:
                        if stuck_restarts >= 1:
                            raise
                        stuck_restarts += 1
                        attempt, limit = stuck_restarts, 1
                    logger.warning('[超鬼王轮换] 账号=%s 异常=%s，重启并核对账号 %s/%s',
                                   account.account_id, type(exc).__name__, attempt, limit)
                    if not recover_account(account):
                        raise RuntimeError('重启后账号核对未通过')
                    retry_driver = driver_factory(account)
                    if hasattr(driver, 'rotation_started'):
                        retry_driver.rotation_started = driver.rotation_started
                    driver = retry_driver
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
