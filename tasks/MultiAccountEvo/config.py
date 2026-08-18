from __future__ import annotations

import re
from datetime import time
from enum import Enum
from typing import Any

from pydantic import Field, model_serializer, model_validator

from tasks.Component.SwitchAccount.switch_account_config import AccountInfo
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler
from tasks.EvoZone.config import KirinType, Layer


class MultiAccountEvoRole(str, Enum):
    LEADER = "leader"
    MEMBER_1 = "member_1"
    MEMBER_2 = "member_2"


class MultiAccountEvoConfig(ConfigBase):
    role: MultiAccountEvoRole = Field(default=MultiAccountEvoRole.LEADER, description="multi_account_evo_role_help")
    kirin_type: KirinType = Field(default=KirinType.LIGHTNINGKIRIN, description="multi_account_evo_kirin_type_help")
    layer: Layer = Field(default=Layer.TEN, description="multi_account_evo_layer_help")
    group_count: int = Field(default=18, ge=1, le=18, description="group_count_help")
    ios_count: int = Field(default=9, ge=0, le=18, description="ios_count_help")
    battle_count: int = Field(default=20, ge=1, description="battle_count_help")
    sync_timeout: Time = Field(default=Time(minute=10), description="sync_timeout_help")
    strict_platform_order: bool = Field(default=True, description="strict_platform_order_help")

    @model_validator(mode="after")
    def validate_counts(self):
        if self.ios_count > self.group_count:
            raise ValueError("ios_count cannot be greater than group_count")
        return self

    @property
    def sync_timeout_seconds(self) -> int:
        value = self.sync_timeout
        if isinstance(value, time):
            return value.hour * 3600 + value.minute * 60 + value.second
        return int(value.total_seconds())


class MultiAccountEvoAccountInfo(AccountInfo):
    related_account: str = Field(default="", description="related_account_help")


class MultiAccountEvo(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    multi_account_evo_config: MultiAccountEvoConfig = Field(default_factory=MultiAccountEvoConfig)
    account_list: list[MultiAccountEvoAccountInfo] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def collect_account_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        dynamic = []
        for key in sorted(
            (key for key in data if re.fullmatch(r"account_list_\d+", str(key))),
            key=lambda key: int(str(key).rsplit("_", 1)[1]),
        ):
            dynamic.append(data.pop(key))
        if dynamic:
            data["account_list"] = dynamic
        accounts = list(data.get("account_list") or [])
        while len(accounts) < 18:
            accounts.append(MultiAccountEvoAccountInfo(apple_or_android=len(accounts) >= 9))
        data["account_list"] = accounts
        return data

    @model_serializer()
    def serialize_model(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key == "account_list":
                for index, account in enumerate(value, start=1):
                    data[f"account_list_{index}"] = account.model_dump()
            elif hasattr(value, "model_dump"):
                data[key] = value.model_dump()
            else:
                data[key] = value
        return data

    @property
    def role(self) -> MultiAccountEvoRole:
        return self.multi_account_evo_config.role

    @property
    def group_count(self) -> int:
        return self.multi_account_evo_config.group_count

    @property
    def kirin_type(self) -> KirinType:
        return self.multi_account_evo_config.kirin_type

    @property
    def layer(self) -> Layer:
        return self.multi_account_evo_config.layer

    @property
    def ios_count(self) -> int:
        return self.multi_account_evo_config.ios_count

    @property
    def battle_count(self) -> int:
        return self.multi_account_evo_config.battle_count

    @property
    def sync_timeout_seconds(self) -> int:
        return self.multi_account_evo_config.sync_timeout_seconds

    def validate_runtime_accounts(self) -> None:
        if len(self.account_list) < 18:
            raise ValueError("at least 18 accounts are required")
        for index, account in enumerate(self.account_list[:18], start=1):
            missing = [
                field
                for field in ("character", "svr", "account")
                if not str(getattr(account, field, "") or "").strip()
            ]
            if missing:
                raise ValueError(f"account_list_{index} is missing required fields: {', '.join(missing)}")
            if self.multi_account_evo_config.strict_platform_order:
                expected_android = index > self.ios_count
                if account.apple_or_android != expected_android:
                    expected = "Android" if expected_android else "iOS"
                    raise ValueError(f"account_list_{index} must be {expected}")
