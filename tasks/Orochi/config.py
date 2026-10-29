# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from datetime import datetime, time

from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig as BaseSwitchSoulConfig
from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.GeneralInvite.config_invite import InviteConfig
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig


class UserStatus(str, Enum):
    LEADER = 'leader'
    MEMBER = 'member'
    ALONE = 'alone'
    WILD = 'wild'  # 还不打算实现

class Layer(str, Enum):
    ONE = '壹层'
    TWO = '贰层'
    THREE = '叁层'
    FOUR = '肆层'
    FIVE = '伍层'
    SIX = '陆层'
    SEVEN = '柒层'
    EIGHT = '捌层'
    NINE = '玖层'
    TEN = '拾层'
    ELEVEN = '悲鸣'
    TWELVE = '神罚'
    THIRTEEN = '虚无'


class OrochiConfig(ConfigBase):
    # 身份
    user_status: UserStatus = Field(default=UserStatus.LEADER, description='user_status_help')
    # 层数
    layer: Layer = Field(default=Layer.ELEVEN, description='layer_help')
    # 限制时间
    limit_time: Time = Field(default=Time(minute=30), description='limit_time_help')
    # 限制次数
    limit_count: int = Field(default=30, description='limit_count_help')
    # 是否开启御魂加成
    soul_buff_enable: bool = Field(default=False, description='soul_buff_enable_help')
    # 是否御魂结束检测是否出现真蛇
    check_true_orochi_enable: bool = Field(default=False, description='check_true_orochi_enable_help')

class LoopConfig(BaseModel):
    """御魂 → 个人突破 循环。配对复用「组队同步」里的对方实例名，两个实例都要开组队同步。"""
    # OASX 逐字段保存走 setattr；不开赋值校验时越界值会被存进文件，下次加载时 `ConfigBase` 会把整个 loop_config
    # 组静默重置成默认值（轮数 / 最少 / 最多一起丢）。开了之后越界值保存失败（`script_set_arg` 返回 False），原值保留。
    # 最少 ≤ 最多不在这里校验（改区间的过程中不能因先后顺序被卡住），打开「开始循环」时才检查。
    model_config = ConfigDict(validate_assignment=True)

    # 一次性开关：脚本读到后立刻关回，只提交本次循环请求
    start_loop: bool = Field(default=False, description='start_loop_help')
    rounds: int = Field(default=3, ge=1, le=100, description='loop_rounds_help')
    # 每批御魂由队长在范围内随机一次目标场数，队员使用同一个值
    target_min: int = Field(default=10, ge=1, le=999, description='loop_target_min_help')
    target_max: int = Field(default=30, ge=1, le=999, description='loop_target_max_help')


class SwitchSoulConfig(BaseSwitchSoulConfig):
    enable: bool = Field(default=False)
    switch_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    enable_switch_by_name: bool = Field(default=False, description='enable_switch_by_name_help')
    group_name: str = Field(default='')
    team_name: str = Field(default='')
    auto_switch_soul: bool = Field(default=False, description='auto_switch_soul_orochi_help')
    # 十层 config
    ten_switch: str = Field(default='-1,-1', description='ten_switch_help')
    # 悲鸣 config
    eleven_switch: str = Field(default='-1,-1', description='eleven_switch_help')
    # 神罚 config
    twelve_switch: str = Field(default='-1,-1', description='twelve_switch_help')
    # 虚无 config
    thirteen_switch: str = Field(default='-1,-1', description='thirteen_switch_help')


class Orochi(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    orochi_config: OrochiConfig = Field(default_factory=OrochiConfig)
    loop_config: LoopConfig = Field(default_factory=LoopConfig)
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    general_battle_config: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    fire_reaction: FireReactionConfig = Field(default_factory=FireReactionConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)

