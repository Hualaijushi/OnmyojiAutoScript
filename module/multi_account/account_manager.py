from __future__ import annotations

import re
from collections.abc import Iterable

from module.multi_account.account import Account


def _positions(value: str | Iterable[int] | None, maximum: int) -> list[int]:
    if value is None or value == "":
        return list(range(1, maximum + 1))
    if not isinstance(value, str):
        return [int(item) for item in value if 1 <= int(item) <= maximum]
    result: list[int] = []
    for token in re.split(r"[,，\s]+", value.strip()):
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        values = range(int(match.group(1)), int(match.group(2)) + 1) if match else [int(token)]
        for number in values:
            if 1 <= number <= maximum and number not in result:
                result.append(number)
    return result


class AccountManager:
    """Read/query accounts; it never performs login or mutates OAS config."""

    def __init__(
        self,
        instance: str,
        account_source,
        *,
        order: str | Iterable[int] | None = None,
        enabled: str | Iterable[int] | None = None,
    ) -> None:
        self.instance = str(instance).lower()
        source = getattr(account_source, "account_list", account_source)
        raw_accounts = list(source or [])
        enabled_positions = set(_positions(enabled, len(raw_accounts)))
        id_prefix = {"oas3": "A", "oas4": "B", "oas5": "C"}.get(self.instance)
        by_position: dict[int, Account] = {}
        for position, raw in enumerate(raw_accounts, start=1):
            character = str(getattr(raw, "character", "") or "").strip()
            server = str(getattr(raw, "svr", "") or "").strip()
            login_account = str(getattr(raw, "account", "") or "").strip()
            configured = bool(character and server and login_account)
            by_position[position] = Account(
                account_id=f"{id_prefix}{position:02d}" if id_prefix else f"{self.instance}-{position:02d}",
                instance=self.instance,
                position=position,
                character=character,
                server=server,
                login_account=login_account,
                account_alias=str(getattr(raw, "account_alias", "") or "").strip(),
                apple_or_android=bool(getattr(raw, "apple_or_android", True)),
                related_account=str(getattr(raw, "related_account", "") or "").strip(),
                enabled=configured and position in enabled_positions,
            )
        positions = _positions(order, len(raw_accounts))
        self._accounts = [by_position[position] for position in positions]
        self._by_id = {account.account_id: account for account in self._accounts}

    def get_accounts_for_instance(self, instance_name: str | None = None, *, enabled_only: bool = False) -> list[Account]:
        if instance_name is not None and str(instance_name).lower() != self.instance:
            return []
        accounts = list(self._accounts)
        return [account for account in accounts if account.enabled] if enabled_only else accounts

    def get_enabled_accounts(self, instance_name: str | None = None) -> list[Account]:
        return self.get_accounts_for_instance(instance_name, enabled_only=True)

    def get_account(self, account_id: str) -> Account | None:
        return self._by_id.get(account_id.upper()) or self._by_id.get(account_id.lower())

    def account_exists(self, account_id: str) -> bool:
        return self.get_account(account_id) is not None

    def get_next_account(
        self,
        instance_name: str | None = None,
        predicate=None,
        *,
        enabled_only: bool = True,
    ) -> Account | None:
        account_id = None
        if instance_name and str(instance_name).lower() != self.instance:
            account_id = str(instance_name)
            instance_name = None
        accounts = self.get_accounts_for_instance(instance_name, enabled_only=enabled_only)
        if predicate is not None:
            accounts = [account for account in accounts if predicate(account)]
        if not accounts:
            return None
        if account_id is None:
            return accounts[0]
        for index, account in enumerate(accounts):
            if account.account_id.lower() == account_id.lower():
                return accounts[index + 1] if index + 1 < len(accounts) else None
        return None
