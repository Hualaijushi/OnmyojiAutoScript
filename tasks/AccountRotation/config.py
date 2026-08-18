from enum import Enum

from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class RotationFailurePolicy(str, Enum):
    CONTINUE = "continue"
    STOP = "stop"


class AccountRotationConfig(ConfigBase):
    account_order: str = Field(default="1-18", description="account_order_help")
    enabled_accounts: str = Field(default="1-18", description="enabled_accounts_help")
    skip_completed_today: bool = Field(default=True, description="skip_completed_today_help")
    max_switch_attempts: int = Field(default=3, ge=1, le=10, description="max_switch_attempts_help")
    retry_delay_seconds: int = Field(default=2, ge=0, le=60, description="retry_delay_seconds_help")
    switch_timeout_seconds: int = Field(default=300, ge=30, le=900, description="switch_timeout_seconds_help")
    failure_policy: RotationFailurePolicy = Field(default=RotationFailurePolicy.CONTINUE, description="rotation_failure_policy_help")
    three_instance_coordination: bool = Field(default=True, description="three_instance_coordination_help")
    coordination_timeout_seconds: int = Field(default=300, ge=30, le=900, description="coordination_timeout_seconds_help")
    ocr_acquire_timeout_seconds: int = Field(default=90, ge=10, le=300, description="ocr_acquire_timeout_seconds_help")
    ocr_lease_timeout_seconds: int = Field(default=45, ge=10, le=180, description="ocr_lease_timeout_seconds_help")


class AccountRotation(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    account_rotation_config: AccountRotationConfig = Field(default_factory=AccountRotationConfig)
