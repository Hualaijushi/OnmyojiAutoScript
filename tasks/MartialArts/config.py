# This Python file uses the following encoding: utf-8
"""武道大会任务配置。"""

from pydantic import BaseModel, Field

from tasks.ActivityShikigami.config import check_soul_by_number, check_soul_by_ocr
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.QuickLoadout.config import NamedQuickLoadoutConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler


class GeneralClimb(ConfigBase):
    limit_time: Time = Field(
        title='运行时间限制',
        default=Time(minute=30),
        description='达到限制时间后不再开始下一场战斗，已经开始的战斗会正常完成',
    )
    ap_limit: int = Field(default=300)
    boss_limit: int = Field(default=20)
    run_sequence: str = Field(
        default='ap,boss',
        description='ap:体力战斗,boss:首领战斗\n'
                    '逗号分隔,从左到右依次运行\n'
                    '例:ap,boss=体力战斗->首领战斗',
    )

    @property
    def run_sequence_v(self) -> list[str]:
        """返回次数大于 0 且按配置排序的战斗类型。"""
        self.valid_run_sequence()
        sequence = [battle_type.strip() for battle_type in self.run_sequence.split(',')]
        return [
            battle_type for battle_type in sequence
            if getattr(self, f'{battle_type}_limit', 0) > 0
        ]

    def valid_run_sequence(self):
        if not self.run_sequence or not self.run_sequence.strip():
            raise ValueError('run sequence cannot be empty')
        sequence = [battle_type.strip() for battle_type in self.run_sequence.split(',')]
        labels = {field.replace('_limit', '') for field in self.model_fields if field.endswith('_limit')}
        for battle_type in sequence:
            if battle_type not in labels:
                raise ValueError(
                    f'run sequence can only be one of {", ".join(labels)}, now is {battle_type}'
                )
        return self


class SwitchSoulConfig(BaseModel):
    enable_switch_ap: bool = Field(default=False)
    ap_group_team: str = Field(default='-1,-1')
    enable_switch_ap_by_name: bool = Field(default=False)
    ap_group_team_name: str = Field(default='')

    enable_switch_boss: bool = Field(default=False)
    boss_group_team: str = Field(default='-1,-1')
    enable_switch_boss_by_name: bool = Field(default=False)
    boss_group_team_name: str = Field(default='')

    def validate_switch_soul(self):
        for battle_type in ('ap', 'boss'):
            check_soul_by_number(
                getattr(self, f'enable_switch_{battle_type}'),
                getattr(self, f'{battle_type}_group_team'),
                label=battle_type.upper(),
            )
            check_soul_by_ocr(
                getattr(self, f'enable_switch_{battle_type}_by_name'),
                getattr(self, f'{battle_type}_group_team_name'),
                label=battle_type.upper(),
            )
        return self


class MartialArts(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    general_climb: GeneralClimb = Field(default_factory=GeneralClimb)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    boss_quick_loadout_config: NamedQuickLoadoutConfig = Field(default_factory=NamedQuickLoadoutConfig)
    ap_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    boss_battle_conf: GeneralBattleConfig = Field(
        default_factory=lambda: GeneralBattleConfig(battle_timeout=600)
    )
