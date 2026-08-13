# This Python file uses the following encoding: utf-8
"""大富翁任务配置。"""

from datetime import time, timedelta

from pydantic import Field, validator

from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler


class RichManRunConfig(ConfigBase):
    limit_time: Time = Field(default=Time(hour=1, minute=30), description='总限制时间')
    pass_limit: int = Field(default=50, description='最多投掷次数')
    active_souls_clean: bool = Field(default=False, description='运行结束后清理御魂')
    random_sleep: bool = Field(default=False, description='点击战斗前随机休息')

    @property
    def limit_time_v(self) -> timedelta:
        if isinstance(self.limit_time, time):
            return timedelta(hours=self.limit_time.hour, minutes=self.limit_time.minute,
                             seconds=self.limit_time.second)
        return self.limit_time

    @property
    def run_sequence_v(self) -> list[str]:
        return ['pass']

    @validator('limit_time', pre=True, always=True)
    def parse_limit_time(cls, value):
        if isinstance(value, str):
            if value.isdigit():
                delta = timedelta(seconds=int(value))
                return time(hour=delta.seconds // 3600, minute=delta.seconds // 60 % 60,
                            second=delta.seconds % 60)
            try:
                return time.fromisoformat(value)
            except ValueError:
                logger.warning('Invalid limit_time value. Expected format: HH:MM:SS')
                return time(hour=1, minute=30)
        return value


class RichManPurchaseConfig(ConfigBase):
    buy_ap: bool = Field(default=False, description='是否购买体力')
    buy_reward: bool = Field(default=False, description='是否购买奖励积分')
    buy_ticket: bool = Field(default=False, description='是否购买定向骰子')


class RichManSoulConfig(ConfigBase):
    enable_switch_pass: bool = Field(default=False, description='是否按编号切换御魂预设')
    pass_group_team: str = Field(default='-1,-1', description='御魂预设组号,队伍号')
    enable_switch_pass_by_name: bool = Field(default=False, description='是否按名称切换御魂预设')
    pass_group_team_name: str = Field(default='', description='御魂预设组名,队伍名')
    enable_switch_boss: bool = Field(default=False, description='是否按编号切换首领战御魂预设')
    boss_group_team: str = Field(default='-1,-1', description='首领战御魂预设组号,队伍号')
    enable_switch_boss_by_name: bool = Field(default=False, description='是否按名称切换首领战御魂预设')
    boss_group_team_name: str = Field(default='', description='首领战御魂预设组名,队伍名')

    def validate_switch_soul(self):
        if self.enable_switch_pass:
            parts = self.pass_group_team.split(',')
            if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
                raise ValueError('[PASS]御魂预设必须是数字组号和队伍号，格式为 组号,队伍号')
        if self.enable_switch_pass_by_name:
            parts = self.pass_group_team_name.split(',')
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError('[PASS]御魂预设名称格式必须为 组名,队伍名')
        if self.enable_switch_boss:
            parts = self.boss_group_team.split(',')
            if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
                raise ValueError('[BOSS]御魂预设必须是数字组号和队伍号，格式为 组号,队伍号')
        if self.enable_switch_boss_by_name:
            parts = self.boss_group_team_name.split(',')
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError('[BOSS]御魂预设名称格式必须为 组名,队伍名')
        return self


class RichMan(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    general_climb: RichManRunConfig = Field(default_factory=RichManRunConfig)
    purchase: RichManPurchaseConfig = Field(default_factory=RichManPurchaseConfig)
    switch_soul_config: RichManSoulConfig = Field(default_factory=RichManSoulConfig)
    pass_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    boss_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
