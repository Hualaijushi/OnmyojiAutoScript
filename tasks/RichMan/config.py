# This Python file uses the following encoding: utf-8
"""大富翁任务配置。"""

from datetime import time, timedelta

from pydantic import Field, model_validator, validator

from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.config_base import ConfigBase, Time, dynamic_hide
from tasks.Component.config_scheduler import Scheduler


class RichManRunConfig(ConfigBase):
    limit_time: Time = Field(default=Time(hour=1, minute=30), description='总限制时间')
    throw_limit: int = Field(default=50, description='骰子投掷次数限制', ge=0)
    active_souls_clean: bool = Field(default=False, description='运行结束后清理御魂')
    random_sleep: bool = Field(
        default=False,
        title='RichMan Random Sleep',
        description='每轮投掷流程结束后随机休眠',
    )

    @model_validator(mode='before')
    @classmethod
    def migrate_pass_limit(cls, data):
        """兼容旧版门票爬塔次数限制。"""
        if isinstance(data, dict):
            data = dict(data)
            if 'throw_limit' not in data and 'pass_limit' in data:
                data['throw_limit'] = data['pass_limit']
        return data

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


class RichManSoulConfig(ConfigBase):
    enable_switch_normal: bool = Field(default=False, description='是否按编号切换普通战斗御魂预设')
    normal_group_team: str = Field(default='-1,-1', description='普通战斗御魂预设组号,队伍号')
    enable_switch_normal_by_name: bool = Field(default=False, description='是否按名称切换普通战斗御魂预设')
    normal_group_team_name: str = Field(default='', description='普通战斗御魂预设组名,队伍名')
    enable_switch_boss: bool = Field(default=False, description='是否按编号切换首领战御魂预设')
    boss_group_team: str = Field(default='-1,-1', description='首领战御魂预设组号,队伍号')
    enable_switch_boss_by_name: bool = Field(default=False, description='是否按名称切换首领战御魂预设')
    boss_group_team_name: str = Field(default='', description='首领战御魂预设组名,队伍名')

    @model_validator(mode='before')
    @classmethod
    def migrate_pass_soul_config(cls, data):
        """兼容旧版 pass 命名的普通战斗御魂配置。"""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        renamed = {
            'enable_switch_pass': 'enable_switch_normal',
            'pass_group_team': 'normal_group_team',
            'enable_switch_pass_by_name': 'enable_switch_normal_by_name',
            'pass_group_team_name': 'normal_group_team_name',
        }
        for old, new in renamed.items():
            if new not in data and old in data:
                data[new] = data[old]
        return data

    def validate_switch_soul(self):
        if self.enable_switch_normal:
            parts = self.normal_group_team.split(',')
            if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
                raise ValueError('[NORMAL]御魂预设必须是数字组号和队伍号，格式为 组号,队伍号')
        if self.enable_switch_normal_by_name:
            parts = self.normal_group_team_name.split(',')
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError('[NORMAL]御魂预设名称格式必须为 组名,队伍名')
        if self.enable_switch_boss:
            parts = self.boss_group_team.split(',')
            if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
                raise ValueError('[BOSS]御魂预设必须是数字组号和队伍号，格式为 组号,队伍号')
        if self.enable_switch_boss_by_name:
            parts = self.boss_group_team_name.split(',')
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError('[BOSS]御魂预设名称格式必须为 组名,队伍名')
        return self


class RichManNormalBattlePreset(GeneralBattleConfig):
    """普通战斗预设。"""


class RichManBossBattlePreset(GeneralBattleConfig):
    """首领战斗预设；首领阵容必须保持未锁定。"""

    hide_ignored_lock = dynamic_hide('lock_team_enable')


class RichMan(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    run_config: RichManRunConfig = Field(default_factory=RichManRunConfig)
    switch_soul_config: RichManSoulConfig = Field(default_factory=RichManSoulConfig)
    normal_battle_preset: RichManNormalBattlePreset = Field(default_factory=RichManNormalBattlePreset)
    boss_battle_preset: RichManBossBattlePreset = Field(default_factory=RichManBossBattlePreset)

    @model_validator(mode='before')
    @classmethod
    def migrate_battle_presets(cls, data):
        """兼容旧版爬塔式战斗配置命名，并丢弃未接入玩法的购买配置。"""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if 'run_config' not in data and 'general_climb' in data:
            data['run_config'] = data['general_climb']
        if 'normal_battle_preset' not in data and 'pass_battle_conf' in data:
            data['normal_battle_preset'] = data['pass_battle_conf']
        if 'boss_battle_preset' not in data and 'boss_battle_conf' in data:
            data['boss_battle_preset'] = data['boss_battle_conf']
        return data
