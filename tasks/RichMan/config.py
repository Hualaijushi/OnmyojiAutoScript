# This Python file uses the following encoding: utf-8
"""大富翁任务配置。"""

from datetime import time, timedelta

from pydantic import Field, model_validator, validator

from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time
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


class RichMan(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    run_config: RichManRunConfig = Field(default_factory=RichManRunConfig)
    general_battle: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)

    @model_validator(mode='before')
    @classmethod
    def migrate_common_configs(cls, data):
        """兼容旧版分离的普通战/首领战配置。"""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if 'run_config' not in data and 'general_climb' in data:
            data['run_config'] = data['general_climb']
        if 'switch_soul' not in data:
            soul = data.get('common_switch_soul', data.get('switch_soul_config'))
            if isinstance(soul, dict):
                normal_enable = soul.get(
                    'enable_switch_normal', soul.get('enable_switch_pass', False),
                )
                normal_by_name = soul.get(
                    'enable_switch_normal_by_name',
                    soul.get('enable_switch_pass_by_name', False),
                )
                boss_enable = soul.get('enable_switch_boss', False)
                boss_by_name = soul.get('enable_switch_boss_by_name', False)

                enable = soul.get(
                    'enable', soul.get('common_enable_switch', normal_enable or boss_enable),
                )
                enable_by_name = soul.get(
                    'enable_switch_by_name',
                    soul.get('common_enable_switch_by_name', normal_by_name or boss_by_name),
                )
                if 'switch_group_team' in soul:
                    group_team = soul['switch_group_team']
                elif 'common_group_team' in soul:
                    group_team = soul['common_group_team']
                elif normal_enable:
                    group_team = soul.get('normal_group_team', soul.get('pass_group_team', '-1,-1'))
                elif boss_enable:
                    group_team = soul.get('boss_group_team', '-1,-1')
                else:
                    group_team = soul.get('group_team', '-1,-1')

                group_name = soul.get('group_name', '')
                team_name = soul.get('team_name', '')
                if not group_name and not team_name:
                    combined_name = soul.get('common_group_team_name', soul.get('group_team_name', ''))
                    if not combined_name:
                        if normal_by_name:
                            combined_name = soul.get(
                                'normal_group_team_name', soul.get('pass_group_team_name', ''),
                            )
                        elif boss_by_name:
                            combined_name = soul.get('boss_group_team_name', '')
                    if isinstance(combined_name, str) and ',' in combined_name:
                        group_name, team_name = (
                            part.strip() for part in combined_name.split(',', 1)
                        )

                data['switch_soul'] = {
                    'enable': enable,
                    'switch_group_team': group_team,
                    'enable_switch_by_name': enable_by_name,
                    'group_name': group_name,
                    'team_name': team_name,
                }

        if 'general_battle' not in data:
            if isinstance(data.get('common_battle_config'), dict):
                data['general_battle'] = data['common_battle_config']
                return data
            normal = data.get('normal_battle_preset', data.get('pass_battle_conf'))
            boss = data.get('boss_battle_preset', data.get('boss_battle_conf'))
            if isinstance(normal, dict):
                common = dict(normal)
                # 普通战未配置预设、但首领战已配置时，保留首领战的预设选择。
                if (not common.get('preset_enable', False)
                        and isinstance(boss, dict) and boss.get('preset_enable', False)):
                    common['preset_enable'] = True
                    common['preset_group'] = boss.get('preset_group', 1)
                    common['preset_team'] = boss.get('preset_team', 1)
                data['general_battle'] = common
            elif isinstance(boss, dict):
                data['general_battle'] = boss
        return data
