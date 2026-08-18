from __future__ import annotations

import re
import time

from module.atom.ocr import RuleOcr
from module.logger import logger
from module.multi_account.account import Account
from tasks.GameUi.page import page_main


class CourtyardCharacterVerifierMixin:
    """Shared courtyard character verification for multi-account switching.

    Every multi-account switching flow (MultiAccountEvo and AccountRotation)
    uses this so that "switch success" always means the account is in the
    courtyard AND the top-left character matches the target account, instead
    of merely that the login was submitted.
    """

    courtyard_character_ocr = RuleOcr(
        name="multi_account_courtyard_character",
        mode="Single",
        method="Default",
        roi=(115, 25, 230, 48),
        area=(115, 25, 230, 48),
        keyword="",
    )
    character_verify_attempts = 3
    character_verify_interval = 0.8

    @staticmethod
    def _normalize_character(value: object) -> str:
        return re.sub(r"\s+", "", str(value or "")).strip()

    def _verify_courtyard_character(self, account: Account) -> bool:
        expected = self._normalize_character(account.character)
        if not expected:
            return False
        for attempt in range(1, self.character_verify_attempts + 1):
            try:
                if self.get_current_page() != page_main:
                    logger.warning(
                        "[Account] instance=%s account_id=%s courtyard verification page mismatch attempt=%s/%s",
                        account.instance,
                        account.account_id,
                        attempt,
                        self.character_verify_attempts,
                    )
                else:
                    self.screenshot()
                    detected = self._normalize_character(
                        self.courtyard_character_ocr.ocr(self.device.image)
                    )
                    if detected == expected:
                        logger.info(
                            "[Account] instance=%s account_id=%s courtyard character verified",
                            account.instance,
                            account.account_id,
                        )
                        return True
                    logger.warning(
                        "[Account] instance=%s account_id=%s courtyard character mismatch attempt=%s/%s",
                        account.instance,
                        account.account_id,
                        attempt,
                        self.character_verify_attempts,
                    )
            except Exception as exc:
                logger.warning(
                    "[Account] instance=%s account_id=%s courtyard character verification failed attempt=%s/%s: %s",
                    account.instance,
                    account.account_id,
                    attempt,
                    self.character_verify_attempts,
                    exc.__class__.__name__,
                )
            if attempt < self.character_verify_attempts:
                time.sleep(self.character_verify_interval)
        return False
