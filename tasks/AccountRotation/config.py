from enum import Enum

from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from tasks.DailyTrifles.config import GuildMedalAmount, SummonType
from tasks.Component.config_base import MultiLine


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


class RotationDailyTaskConfig(ConfigBase):
    daily_task_enable: bool = Field(default=False, description="account_rotation_daily_task_enable_help")
    daily_courtyard_affairs: bool = Field(default=False, description="courtyard_affairs")
    daily_courtyard_morning: bool = Field(default=False, description="courtyard_morning")
    daily_courtyard_evening: bool = Field(default=False, description="courtyard_evening")
    daily_pickup_email: bool = Field(default=False, description="pickup_email")
    daily_one_summon: bool = Field(default=False, description="one_summon")
    daily_summon_type: SummonType = Field(default=SummonType.default, description="召唤类型")
    daily_draw_mystery_pattern: bool = Field(default=False, description="draw_mystery_pattern")
    daily_luck_msg: bool = Field(default=False, description="luck_msg")
    daily_store_sign: bool = Field(default=False, description="store_sign")
    daily_buy_sushi_count: int = Field(default=-1, description="buy_sushi_count")
    daily_guild_donate_enable: bool = Field(default=False, description="guild_donate")
    daily_guild_auto_get_rewards: bool = Field(default=True, description="auto_get_rewards")
    daily_guild_notify_enable: bool = Field(default=False, description="guild_donate_notify_help")
    daily_guild_member_list: MultiLine = Field(default="", description="guild_member_list_help")
    daily_guild_friend_list: MultiLine = Field(default="", description="invite_friend_list_help")
    daily_guild_name_check: bool = Field(default=True, description="guild_donate_name_check_help")
    daily_guild_medal_donate: bool = Field(default=False, description="guild_medal_donate_help")
    daily_guild_medal_amount: GuildMedalAmount = Field(default=GuildMedalAmount.amount_20, description="guild_medal_amount_help")
    daily_hunt_kirin: bool = Field(default=False, description="daily_hunt_kirin_help")
    daily_hunt_netherworld: bool = Field(default=False, description="daily_hunt_netherworld_help")
    daily_cooperation_morning: bool = Field(default=False, description="daily_cooperation_morning_help")
    daily_cooperation_evening: bool = Field(default=False, description="daily_cooperation_evening_help")


class AccountRotation(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    account_rotation_config: AccountRotationConfig = Field(default_factory=AccountRotationConfig)
    daily_task_config: RotationDailyTaskConfig = Field(default_factory=RotationDailyTaskConfig)
