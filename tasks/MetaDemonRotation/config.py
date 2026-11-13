"""独立超鬼王账号轮换配置。"""

from pydantic import Field, ValidationInfo, field_validator

from tasks.Component.config_base import ConfigBase, Time, TimeDelta
from tasks.Component.config_scheduler import Scheduler


class RotationSettings(ConfigBase):
    account_start: int = Field(default=1, json_schema_extra={'minimum': 1, 'maximum': 20}, description='本实例开始处理的账号序号')
    account_end: int = Field(default=18, validate_default=True, json_schema_extra={'minimum': 1, 'maximum': 20}, description='本实例结束处理的账号序号（含）')
    rental_team: int = Field(default=1, ge=1, le=3, description='租借队伍列表中可见的前一至三队')
    battle_limit: int = Field(default=40, ge=1, description='每个账号的挑战场数上限')

    @field_validator('account_start')
    @classmethod
    def validate_account_start(cls, start: int) -> int:
        if not 1 <= start <= 20:
            raise ValueError('起始账号序号必须在1至20之间')
        return start

    @field_validator('account_end')
    @classmethod
    def validate_account_range(cls, end: int, info: ValidationInfo) -> int:
        if not 1 <= end <= 20:
            raise ValueError('结束账号序号必须在1至20之间')
        if info.data.get('account_start', 1) > end:
            raise ValueError('起始账号序号不能大于结束账号序号')
        return end


class RotationPlaySettings(ConfigBase):
    use_current_queue: bool = Field(default=False, title='沿用当前队列', description='沿用当前队列，不按攻击顺序重新选择鬼王')
    limit_time: Time = Field(default=Time(), title='每号运行时长', description='每个账号的运行时长上限，00:00:00表示不限')
    auto_tea: bool = Field(default=False, title='自动喝茶', description='疲劳度满时是否自动喝茶')
    fatigue_wait_interval: TimeDelta = Field(default=TimeDelta(hours=1, minutes=40), title='疲劳等待时间', description='整轮已处理且未完成原因均为疲劳时，下次运行前的等待时间')
    fire_sequence: str = Field(default='4', title='攻击星级顺序', description='鬼王攻击顺序，按星级以空格分隔')
    powerful_list: str = Field(default='', title='强力追击星级', description='开启强力追击的鬼王星级，空格分隔')
    synthesis_list: str = Field(default='', title='鬼王合成星级', description='需要合成的鬼王星级，空格分隔')


class MetaDemonRotation(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    rotation_settings: RotationSettings = Field(default_factory=RotationSettings)
    rotation_play: RotationPlaySettings = Field(default_factory=RotationPlaySettings)
