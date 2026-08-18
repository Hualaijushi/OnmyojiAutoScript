from __future__ import annotations

from dataclasses import dataclass

from tasks.Component.SwitchAccount.switch_account_config import AccountInfo


@dataclass(frozen=True, slots=True)
class Account:
    """One configured game account with an immutable internal identity."""

    account_id: str
    instance: str
    position: int
    character: str
    server: str
    login_account: str
    account_alias: str = ""
    apple_or_android: bool = True
    related_account: str = ""
    enabled: bool = True

    @property
    def role_name(self) -> str:
        return self.character

    @property
    def alias(self) -> str:
        return self.account_alias

    def to_account_info(self) -> AccountInfo:
        return AccountInfo(
            character=self.character,
            svr=self.server,
            account=self.login_account,
            account_alias=self.account_alias,
            apple_or_android=self.apple_or_android,
        )
