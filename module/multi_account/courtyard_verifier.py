from __future__ import annotations

import re
import time

from module.exception import OcrUnavailableError, ImageFrameExpiredError, CourtyardStallRecoveryExhausted
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

    def _ensure_courtyard_for_character_verification(self, account: Account) -> bool:
        """读取角色名前先恢复到已确认的庭院。

        GameUi 任务走 ``goto_page(page_main)``，使阴阳师精灵等登录后浮层与
        AccountRotation 的每日琐事导航一样按未知页面关闭；未提供 Navigator 的
        轻量调用方保留页面判定兜底。
        """
        goto_page = getattr(self, "goto_page", None)
        if callable(goto_page):
            try:
                arrived = goto_page(page_main)
            except (OcrUnavailableError, ImageFrameExpiredError, CourtyardStallRecoveryExhausted):
                raise
            except Exception as exc:
                logger.warning(
                    "[Account] instance=%s account_id=%s courtyard navigation failed before character verification: %s",
                    account.instance,
                    account.account_id,
                    exc.__class__.__name__,
                )
                return False
            if not arrived:
                logger.warning(
                    "[Account] instance=%s account_id=%s courtyard navigation did not confirm page_main before character verification",
                    account.instance,
                    account.account_id,
                )
                return False
            return True

        return self.get_current_page() == page_main

    def _verify_courtyard_character(self, account: Account) -> bool:
        expected = self._normalize_character(account.character)
        if not expected:
            return False
        if not self._ensure_courtyard_for_character_verification(account):
            return False
        for attempt in range(1, self.character_verify_attempts + 1):
            try:
                # 每次页面判断使用新画面，避免弹窗变化后反复识别旧帧。
                self.screenshot()
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
            except (OcrUnavailableError, ImageFrameExpiredError):
                raise
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
