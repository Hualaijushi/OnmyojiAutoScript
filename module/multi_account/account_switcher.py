from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from module.logger import logger
from module.multi_account.account import Account
from tasks.Component.SwitchAccount.switch_account import SwitchAccount


class SwitchErrorCode(str, Enum):
    NONE = "none"
    ACCOUNT_NOT_FOUND = "account_not_found"
    CURRENT_ACCOUNT_UNKNOWN = "current_account_unknown"
    OCR_FAILED = "ocr_failed"
    ROLE_MISMATCH = "role_mismatch"
    SWITCH_BUTTON_NOT_FOUND = "switch_button_not_found"
    LOGIN_TIMEOUT = "login_timeout"
    HOME_TIMEOUT = "home_timeout"
    SCREENSHOT_FAILED = "screenshot_failed"
    RPC_FAILED = "rpc_failed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SwitchResult:
    success: bool
    account_id: str
    changed: bool = False
    attempts: int = 0
    error_code: SwitchErrorCode = SwitchErrorCode.NONE
    message: str = ""
    elapsed_seconds: float = 0.0
    detected_account_id: str | None = None

    @property
    def retries(self) -> int:
        return max(0, self.attempts - 1)


class AccountSwitcher:
    """Finite, result-oriented facade over the project's proven switch flow."""

    def __init__(
        self,
        config,
        device,
        *,
        max_attempts: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 180.0,
        current_account_detector: Callable[[Account], bool] | None = None,
        home_verifier: Callable[[Account], bool] | None = None,
        switch_factory: Callable[..., object] = SwitchAccount,
        ocr_coordinator=None,
        fast: bool = False,
    ) -> None:
        self.config = config
        self.device = device
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay = max(0.0, float(retry_delay))
        self.timeout = max(0.01, float(timeout))
        self.current_account_detector = current_account_detector
        self.home_verifier = home_verifier
        self.switch_factory = switch_factory
        self.ocr_coordinator = ocr_coordinator
        self.fast = fast
        self._last_verified_account_id: str | None = None

    def get_current_account(self) -> str | None:
        return self._last_verified_account_id

    def verify_account(self, target_account: Account) -> bool:
        if self._last_verified_account_id == target_account.account_id:
            return True
        return bool(self.current_account_detector and self.current_account_detector(target_account))

    def wait_until_home(self, target_account: Account) -> bool:
        return True if self.home_verifier is None else bool(self.home_verifier(target_account))

    def switch_to(self, target_account: Account, **kwargs) -> SwitchResult:
        return self.ensure_account(target_account, **kwargs)

    @staticmethod
    def _classify(exc: BaseException) -> SwitchErrorCode:
        text = f"{exc.__class__.__name__}: {exc}".lower()
        if "timeout" in text or "timed out" in text:
            return SwitchErrorCode.TIMEOUT
        if "ocr" in text or "recogn" in text:
            return SwitchErrorCode.OCR_FAILED
        if "rpc" in text or "zerorpc" in text or "frame id" in text:
            return SwitchErrorCode.RPC_FAILED
        if "not found" in text or "account" in text and "missing" in text:
            return SwitchErrorCode.ACCOUNT_NOT_FOUND
        if "mismatch" in text or "character" in text or "role" in text:
            return SwitchErrorCode.ROLE_MISMATCH
        return SwitchErrorCode.UNKNOWN

    def ensure_account(
        self,
        account: Account,
        *,
        on_ocr_complete: Callable[[], None] | None = None,
    ) -> SwitchResult:
        started = time.monotonic()
        if not account.enabled:
            return SwitchResult(
                False, account.account_id, error_code=SwitchErrorCode.ACCOUNT_NOT_FOUND,
                message="account is disabled or incomplete",
            )

        try:
            already_current = self._last_verified_account_id == account.account_id
            if not already_current and self.current_account_detector is not None:
                already_current = bool(self.current_account_detector(account))
            if already_current:
                return SwitchResult(
                    True, account.account_id, changed=False,
                    elapsed_seconds=time.monotonic() - started,
                    detected_account_id=account.account_id,
                )
        except Exception as exc:
            logger.warning("[Account] instance=%s account_id=%s current detection failed: %s", account.instance, account.account_id, self._classify(exc).value)

        last_code = SwitchErrorCode.UNKNOWN
        last_message = "account switch returned false"
        for attempt in range(1, self.max_attempts + 1):
            if time.monotonic() - started >= self.timeout:
                last_code, last_message = SwitchErrorCode.TIMEOUT, "account switch deadline exceeded"
                break
            logger.info("[Account] instance=%s account_id=%s switch attempt=%s/%s", account.instance, account.account_id, attempt, self.max_attempts)
            try:
                switch = self.switch_factory(
                    self.config,
                    self.device,
                    account.to_account_info(),
                    redact_logs=True,
                    on_ocr_complete=on_ocr_complete,
                    ocr_coordinator=self.ocr_coordinator,
                    fast=self.fast,
                )
                if not bool(switch.switchAccount()):
                    last_code, last_message = SwitchErrorCode.ROLE_MISMATCH, "legacy switch verification failed"
                elif not self.wait_until_home(account):
                    last_code, last_message = SwitchErrorCode.ROLE_MISMATCH, "post-switch verification mismatch"
                else:
                    self._last_verified_account_id = account.account_id
                    return SwitchResult(
                        True, account.account_id, changed=True, attempts=attempt,
                        elapsed_seconds=time.monotonic() - started,
                        detected_account_id=account.account_id,
                    )
            except Exception as exc:
                last_code = self._classify(exc)
                last_message = str(exc) or exc.__class__.__name__
            if attempt < self.max_attempts and time.monotonic() - started < self.timeout:
                time.sleep(self.retry_delay)

        logger.error("[Account] instance=%s account_id=%s switch failed code=%s", account.instance, account.account_id, last_code.value)
        return SwitchResult(
            False, account.account_id, changed=False, attempts=min(self.max_attempts, attempt if 'attempt' in locals() else 0),
            error_code=last_code, message=last_message, elapsed_seconds=time.monotonic() - started,
        )
