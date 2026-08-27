# This Python file uses the following encoding: utf-8
"""式神活动统一配置。"""

from datetime import time, timedelta

from pydantic import BaseModel, Field, model_validator, validator

from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler


ACTIVITY_NAME_TO_FIELD = {
    '大富翁': 'rich_man',
    '爬塔': 'climb',
    '伪神降临': 'fakegod',
}
ACTIVITY_NAME_ALIASES = {
    'richman': '大富翁',
    'rich_man': '大富翁',
    '大富翁': '大富翁',
    'climb': '爬塔',
    'normal': '爬塔',
    '爬塔': '爬塔',
    'fakegod': '伪神降临',
    'fake_god': '伪神降临',
    '伪神': '伪神降临',
    '伪神降临': '伪神降临',
}
CLIMB_TYPES = ('ap', 'pass', 'boss', 'ap100')
BATTLE_TYPES = ('rich_man', *CLIMB_TYPES, 'fakegod')


class GeneralConfig(ConfigBase):
    task_sequence: str = Field(
        default='大富翁,爬塔,伪神降临',
        title='Activity Task Sequence',
        description='activity_task_sequence_help',
    )
    throw_limit: int = Field(default=0, title='Throw Limit', ge=0)
    ap_limit: int = Field(default=0, title='Ap Limit', ge=0)
    pass_limit: int = Field(default=0, title='Pass Limit', ge=0)
    boss_limit: int = Field(default=0, title='Boss Limit', ge=0)
    ap100_limit: int = Field(default=0, title='Ap100 Limit', ge=0)
    fakegod_limit: int = Field(default=0, title='Fakegod Limit', ge=0)
    limit_time: Time = Field(
        default=Time(hour=1, minute=30),
        title='Activity Limit Time',
        description='activity_limit_time_help',
    )
    active_souls_clean: bool = Field(
        default=False,
        title='Active Souls Clean',
        description='active_souls_clean_help',
    )
    random_sleep: bool = Field(
        default=False,
        title='Activity Random Sleep',
        description='activity_random_sleep_help',
    )
    use_penta_pass: bool = Field(
        default=False,
        title='Use Penta Pass',
        description='use_penta_pass_help',
    )

    @property
    def limit_time_v(self) -> timedelta:
        if isinstance(self.limit_time, time):
            return timedelta(
                hours=self.limit_time.hour,
                minutes=self.limit_time.minute,
                seconds=self.limit_time.second,
            )
        return self.limit_time

    @property
    def task_sequence_v(self) -> list[str]:
        names = []
        for raw_name in self.task_sequence.split(','):
            name = ACTIVITY_NAME_ALIASES.get(raw_name.strip().lower())
            if name is None:
                raise ValueError(
                    f'任务启用顺序仅支持 {", ".join(ACTIVITY_NAME_TO_FIELD)}，当前为 {raw_name.strip()}'
                )
            if name not in names and self.activity_enabled(name):
                names.append(name)
        return names

    @property
    def climb_sequence_v(self) -> list[str]:
        """爬塔四种战斗按 UI 约定顺序执行，并跳过次数为零的项。"""
        return [name for name in CLIMB_TYPES if getattr(self, f'{name}_limit') > 0]

    def activity_enabled(self, activity_name: str) -> bool:
        field = ACTIVITY_NAME_TO_FIELD[activity_name]
        if field == 'rich_man':
            return self.throw_limit > 0
        if field == 'climb':
            return bool(self.climb_sequence_v)
        return self.fakegod_limit > 0

    def limit_for(self, action_type: str) -> int:
        field = 'throw_limit' if action_type == 'rich_man' else f'{action_type}_limit'
        return getattr(self, field, 0)

    @validator('limit_time', pre=True, always=True)
    def parse_limit_time(cls, value):
        if isinstance(value, str):
            if value.isdigit():
                delta = timedelta(seconds=int(value))
                return time(
                    hour=delta.seconds // 3600,
                    minute=delta.seconds // 60 % 60,
                    second=delta.seconds % 60,
                )
            try:
                return time.fromisoformat(value)
            except ValueError:
                logger.warning('Invalid activity limit_time value. Expected format: HH:MM:SS')
                return time(hour=1, minute=30)
        return value


def check_soul_by_number(enable_switch: bool, group_team: str, label: str):
    if not enable_switch:
        return
    parts = group_team.split(',') if group_team else []
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise ValueError(f'[{label}]御魂预设必须为数字组号和队伍号，格式为 组号,队伍号')


def check_soul_by_ocr(enable_switch: bool, group_team_name: str, label: str):
    if not enable_switch:
        return
    parts = group_team_name.split(',') if group_team_name else []
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ValueError(f'[{label}]御魂预设名称必须为 组名,队伍名')


class SwitchSoulConfig(BaseModel):
    enable_switch_rich_man: bool = Field(default=False)
    rich_man_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_rich_man_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    rich_man_group_team_name: str = Field(default='')

    enable_switch_ap: bool = Field(default=False)
    ap_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_ap_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    ap_group_team_name: str = Field(default='')

    enable_switch_pass: bool = Field(default=False)
    pass_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_pass_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    pass_group_team_name: str = Field(default='')

    enable_switch_boss: bool = Field(default=False)
    boss_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_boss_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    boss_group_team_name: str = Field(default='')

    enable_switch_ap100: bool = Field(default=False)
    ap100_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_ap100_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    ap100_group_team_name: str = Field(default='')

    enable_switch_fakegod: bool = Field(default=False)
    fakegod_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_fakegod_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    fakegod_group_team_name: str = Field(default='')

    def validate_switch_soul(self):
        for label in BATTLE_TYPES:
            check_soul_by_number(
                getattr(self, f'enable_switch_{label}'),
                getattr(self, f'{label}_group_team'),
                label.upper(),
            )
            check_soul_by_ocr(
                getattr(self, f'enable_switch_{label}_by_name'),
                getattr(self, f'{label}_group_team_name'),
                label.upper(),
            )
        return self


class ActivityShikigami(ConfigBase):
    # OASX 按字段顺序排版：任务调度、通用设置、切换御魂、六种战斗配置。
    scheduler: Scheduler = Field(default_factory=Scheduler)
    general_config: GeneralConfig = Field(default_factory=GeneralConfig)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)

    rich_man_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    ap_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    pass_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    boss_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    ap100_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    fakegod_battle_conf: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)

    @model_validator(mode='before')
    @classmethod
    def migrate_legacy_configs(cls, data):
        """合并旧爬塔、大富翁和伪神降临配置。"""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        old_climb = data.get('general_climb')
        old_rich_man = data.pop('_legacy_rich_man', None)
        old_fakegod = data.pop('_legacy_fakegod', None)

        if 'general_config' not in data:
            general = {}
            if isinstance(old_climb, dict):
                for key in (
                    'limit_time', 'ap_limit', 'pass_limit', 'boss_limit', 'ap100_limit',
                    'active_souls_clean', 'random_sleep',
                ):
                    if key in old_climb:
                        general[key] = old_climb[key]
                general['task_sequence'] = '爬塔'

            if isinstance(old_rich_man, dict):
                run = old_rich_man.get('run_config', old_rich_man.get('general_climb', {}))
                if isinstance(run, dict):
                    general['throw_limit'] = run.get('throw_limit', run.get('pass_limit', 0))
                    general.setdefault('limit_time', run.get('limit_time', '01:30:00'))
                    general['active_souls_clean'] = bool(
                        general.get('active_souls_clean', False) or run.get('active_souls_clean', False)
                    )
                    general['random_sleep'] = bool(
                        general.get('random_sleep', False) or run.get('random_sleep', False)
                    )

            if isinstance(old_fakegod, dict):
                run = old_fakegod.get('general_climb', {})
                if isinstance(run, dict):
                    general['fakegod_limit'] = run.get('pass_limit', 0)
                    general.setdefault('limit_time', run.get('limit_time', '01:30:00'))

            enabled_sequence = []
            if isinstance(old_rich_man, dict) and old_rich_man.get('scheduler', {}).get('enable'):
                enabled_sequence.append('大富翁')
            if isinstance(old_climb, dict):
                enabled_sequence.append('爬塔')
            if isinstance(old_fakegod, dict) and old_fakegod.get('scheduler', {}).get('enable'):
                enabled_sequence.append('伪神降临')
            if enabled_sequence:
                general['task_sequence'] = ','.join(enabled_sequence)
            data['general_config'] = general

        soul = dict(data.get('switch_soul_config') or {})
        if isinstance(old_rich_man, dict):
            old_soul = old_rich_man.get('switch_soul', old_rich_man.get('common_switch_soul', {}))
            if isinstance(old_soul, dict):
                soul.setdefault('enable_switch_rich_man', old_soul.get('enable', False))
                soul.setdefault('rich_man_group_team', old_soul.get('switch_group_team', '-1,-1'))
                soul.setdefault(
                    'enable_switch_rich_man_by_name', old_soul.get('enable_switch_by_name', False),
                )
                combined = ','.join(filter(None, [old_soul.get('group_name', ''), old_soul.get('team_name', '')]))
                soul.setdefault('rich_man_group_team_name', combined)
        if isinstance(old_fakegod, dict):
            old_soul = old_fakegod.get('switch_soul_config', {})
            if isinstance(old_soul, dict):
                soul.setdefault('enable_switch_fakegod', old_soul.get('enable_switch_pass', False))
                soul.setdefault(
                    'enable_switch_fakegod_by_name', old_soul.get('enable_switch_pass_by_name', False),
                )
                soul.setdefault('fakegod_group_team', old_soul.get('pass_group_team', '-1,-1'))
                soul.setdefault('fakegod_group_team_name', old_soul.get('pass_group_team_name', ''))
        data['switch_soul_config'] = soul

        if isinstance(old_rich_man, dict):
            data.setdefault('rich_man_battle_conf', old_rich_man.get('general_battle', {}))
        if isinstance(old_fakegod, dict):
            data.setdefault('fakegod_battle_conf', old_fakegod.get('pass_battle_conf', {}))
        return data
