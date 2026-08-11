# This Python file uses the following encoding: utf-8
"""武道大会任务配置。"""

from datetime import time, timedelta

from pydantic import Field
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler


class MartialArtsConfig(ConfigBase):
    limit_time: Time = Field(default=Time(minute=30), description='武道大会单次运行时间上限')
    battle_count: int = Field(default=20, description='武道大会最大战斗次数')

    @property
    def limit_time_v(self) -> timedelta:
        if isinstance(self.limit_time, time):
            return timedelta(
                hours=self.limit_time.hour,
                minutes=self.limit_time.minute,
                seconds=self.limit_time.second,
            )
        return self.limit_time


class MartialArts(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    martial_arts_config: MartialArtsConfig = Field(default_factory=MartialArtsConfig)
    battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
