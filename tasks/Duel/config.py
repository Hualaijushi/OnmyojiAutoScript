# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field
from datetime import time
from tasks.Component.SwitchOnmyoji.config import Onmyoji

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.GeneralBattle.config_general_battle import GreenMarkType
from enum import Enum
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class DuelConfig(ConfigBase):
    # 是否切换阴阳师
    switch_enabled: bool = Field(default=True, description='是否切换阴阳师')
    # 切换阴阳师
    switch_onmyoji: Onmyoji = Field(default=Onmyoji.YORIMITSU, description='切换阴阳师')
    # 一键切换斗技御魂
    switch_all_soul: bool = Field(default=False, description='switch_all_soul_help')
    # 限制时间
    limit_time: Time = Field(default=Time(minute=30), description='limit_time_help')
    # 目标分数
    target_score: int = Field(default=2000, description='达到目标分数后退出')
    # 刷满荣誉就退出
    honor_full_exit: bool = Field(default=False, description='honor_full_exit_help')
    # 是否开启绿标
    green_enable: bool = Field(default=False, description='green_enable_help')
    # 选哪一个绿标
    green_mark: GreenMarkType = Field(default=GreenMarkType.GREEN_LEFT1, description='green_mark_help')


class DuelCelebConfig(ConfigBase):
    # 是否开启名士战斗
    celeb_battle: bool = Field(
        title='是否开启名士战斗',
        default=False,
        description='仅当O_D_CELEB识别文本包含“名士”且该开关已开启时，才允许开始名士战斗',
    )
    # 名士荣誉约束
    celeb_honor_full_exit: bool = Field(
        title='刷满荣誉即退',
        default=False,
        description='勾选后，名士荣誉刷满时停止战斗',
    )
    practice_test: bool = Field(
        title='练习模式测试',
        default=False,
        description='开启后必须检测到练习入口才会开始战斗；允许在活动时间外运行，并自动选择Ban模式测试名士流程',
    )
    # 填写检查位置和式神名称，用于判断该式神是否被 Ban
    ban_check: str = Field(
        title='Ban检查位置及式神',
        default='',
        description='填写“序号,式神名字”，序号范围1-5，例如“5,平将门”；同一位置连续两次不是该式神时退出本局',
    )
    full_lineup_check: bool = Field(
        title='使用完整阵容对比',
        default=False,
        description='勾选后不使用单位置检查，改为按照完整阵容名单的顺序核对1-5号位置',
    )
    full_lineup_names: str = Field(
        title='完整斗技阵容名单',
        default='',
        description='按实际上阵从左到右顺序填写五个式神名字，以英文逗号分隔；仅在勾选完整阵容对比时生效',
    )
    celeb_star: int = Field(
        title='名士星星数目标',
        default=8,
        description='当前名士星星数达到该目标后停止战斗；设置为0时不限制',
    )


class Duel(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    duel_config: DuelConfig = Field(default_factory=DuelConfig)
    duel_celeb_config: DuelCelebConfig = Field(default_factory=DuelCelebConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
