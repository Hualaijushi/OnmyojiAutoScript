# This Python file uses the following encoding: utf-8
# @brief    Configurations for Ryou Dokan Toppa (阴阳竂道馆突破配置)
# @author   jackyhwei
# @note     draft version without full test
# github    https://github.com/roarhill/oas
import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator
from typing_extensions import Annotated

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time, dynamic_hide
from tasks.Component.config_scheduler import Scheduler


# 福利模式人数门槛：严格正整数，拒绝 1.5、'100'、True 这类会被宽松转换悄悄接受的值
_WELFARE_MIN_PEOPLE = TypeAdapter(Annotated[int, Field(ge=1, strict=True)])

# 福利模式每周允许运行的日期：下标 = datetime.weekday()（周一 = 0）。普通模式不读这几项，仍只看 monday_to_thursday
WELFARE_WEEKDAY_FIELDS = (
    'welfare_run_monday', 'welfare_run_tuesday', 'welfare_run_wednesday', 'welfare_run_thursday',
    'welfare_run_friday', 'welfare_run_saturday', 'welfare_run_sunday',
)
WEEKDAY_NAMES = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


class AttackDokanMasterType(str, Enum):
    """
        NOTE: 如果第一个道馆没有放弃突破,那么没有第二次选择道馆的机会
            目前如果设置打一次馆主,如果打不过(失败),会一直等待->挑战循环
            导致失去放弃突破的机会->无法进行第二次道馆
    """
    # 不打馆主                                  0
    ATTACK_ZERO_ZERO = "ATTACK_ZERO_ZERO"
    # 第二次攻击时攻击馆主一次                     1
    ATTACK_ZERO_ONE = "ATTACK_ZERO_ONE"
    # 第一次攻击时不攻击馆主,第二次攻击时攻击馆主一次     2
    ATTACK_ZERO_TWO = "ATTACK_ZERO_TWO"
    #                                           3
    ATTACK_ONE_ZERO = "ATTACK_ONE_ZERO"
    # 第一次攻击时攻击馆主一次,第二次攻击时攻击馆主一次 4
    ATTACK_ONE_ONE = "ATTACK_ONE_ONE"
    # 第一次攻击时攻击馆主一次,第二次攻击时攻击馆主二次 5
    ATTACK_ONE_TWO = "ATTACK_ONE_TWO"
    # 第一次攻击时攻击馆主二次, 没有第二次了          8
    ATTACK_TWO_TWO = "ATTACK_TWO_TWO"

    def __int__(self):
        match self.value:
            case "ATTACK_ZERO_ZERO":
                return 0
            case "ATTACK_ZERO_ONE":
                return 1
            case "ATTACK_ZERO_TWO":
                return 2
            case "ATTACK_ONE_ZERO":
                return 3
            case "ATTACK_ONE_ONE":
                return 4
            case "ATTACK_ONE_TWO":
                return 5
            case "ATTACK_TWO_TWO":
                return 8
            case _:
                return 8


class AttackAccountConfig(BaseModel):
    # 当天可攻击次数,用以记录当天运行历史,用作状态恢复,不用配置
    remain_attack_count: int = Field(default=2, description='remain_attack_count_help')
    # remain_attack_count 值记录的时间,不用配置
    attack_date: str = Field(default='2023-01-01', description='attack_date_help')
    # 每日最大攻击次数(1-2,默认2次),建议:僵尸寮配置2,其他寮配置1
    daily_attack_count: int = Field(default=2, description='daily_attack_count_help')
    # 攻击馆主配置,格式:ATTACK_X_Y          X:  第一个道馆,只打馆主一阵/两阵都打
    #                                    Y:  第二个道馆,只打馆主一阵/两阵都打
    # 建议普通寮配置ATTACK_TWO_TWO,僵尸寮看自己喜好
    attack_dokan_master: AttackDokanMasterType = Field(default=AttackDokanMasterType.ATTACK_TWO_TWO,
                                                       description='attack_dokan_master_help')

    hide_fields = dynamic_hide('remain_attack_count', 'attack_date')

    def init_attack_count(self, callback=None):
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.attack_date:
            self.attack_date = today
            self.remain_attack_count = 2
        if not callback:
            return
        callback()

    def attack_dokan_master_count(self) -> int:
        """
        根据当前配置,获取此次道馆突破,需要攻击馆主的次数
        @return: 当前突破,可攻击馆主的次数
        @rtype:
        """
        if self.attack_dokan_master == AttackDokanMasterType.ATTACK_ZERO_ZERO:
            return 0
        if self.attack_dokan_master == AttackDokanMasterType.ATTACK_TWO_TWO:
            return 2
        # 只攻击一次
        # 或者
        # 还有一次选择寮的机会,即,在打第一个寮的过程中
        if self.daily_attack_count == 1 or self.remain_attack_count >= 1:
            return int(self.attack_dokan_master) // 3
        # 攻击两次 且 在打第二个寮的过程中
        return int(self.attack_dokan_master) % 3

    def set_attack_count(self, count=2, callback=None):
        if count < 0:
            return
        self.attack_date = datetime.now().strftime("%Y-%m-%d")
        self.remain_attack_count = count
        if not callback:
            return
        callback()

    def del_attack_count(self, count, callback=None):
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.attack_date:
            self.attack_date = today
            self.remain_attack_count = 2
        self.remain_attack_count -= count
        if not callback:
            return
        callback()


class DokanConfig(BaseModel):
    dokan_run_time: Time = Field(Time(hour=20, minute=0, second=0), description='dokan_run_time_help')
    # 攻击优先顺序: 见习=0,初级=1...
    dokan_attack_priority: int = Field(default=0, description='dokan_attack_priority_help')
    # 失败CD后自动加油
    dokan_auto_cheering_while_cd: bool = Field(default=False, description='dokan_auto_cheering_while_cd_help')
    # 正式进攻会设定 2s - 10s 的随机延迟，避免攻击间隔及其相近被检测为脚本。
    random_delay: bool = Field(default=False, description='random_delay_help')
    # 只在周一到周四开启道馆
    monday_to_thursday: bool = Field(default=True, description='monday_to_thursday_help')
    # 是否尝试开启道馆,在道馆未开启时,尝试查找合适道馆并开启,需要有权限
    try_start_dokan: bool = Field(default=False, description='try_start_dokan')
    # 道馆系数,赏金/人数 根据喜好配置
    find_dokan_score: float = Field(default=4.6, description='dokan_score_help')
    # 道馆最小人数限制
    min_people_num: int = Field(default=-1, description='min_people_num_help')
    # 最少赏金设置
    min_bounty: int = Field(default=0, description='min_bounty_help')
    # 单次查找道馆时,最大刷新次数.超过此次数后,若还未找到符合要求的,会随机选择一个道馆
    find_dokan_refresh_count: int = Field(default=7, description='find_dokan_refresh_count_help')
    # 福利道馆模式（默认关闭）：只找「鑫」馆，防守人数 >= 门槛才开，开馆后点准备立即关游戏
    welfare_mode: bool = Field(default=False, description='welfare_mode_help')
    welfare_min_people: int = Field(default=100, ge=1, description='welfare_min_people_help')
    # 福利模式每周允许运行的日期（只限制哪天可以执行，不是开始时间；运行时机仍由调度器决定）。默认值 = 旧限制「只在周一到周四」。
    # 旧配置文件里没有这七项时按 monday_to_thursday 推导，见 `_derive_missing_welfare_weekdays`。
    # 说明文案只挂在第一项上（description 七项相同会让旧配置页重复七遍长说明）；展示分组见 tasks/Dokan/args_layout.py
    welfare_run_monday: bool = Field(default=True, description='welfare_run_days_help')
    welfare_run_tuesday: bool = True
    welfare_run_wednesday: bool = True
    welfare_run_thursday: bool = True
    welfare_run_friday: bool = False
    welfare_run_saturday: bool = False
    welfare_run_sunday: bool = False

    @model_validator(mode='after')
    def _derive_missing_welfare_weekdays(self):
        """键缺失（旧配置）≠ 显式 False：只有「文件里没有这个键」才按旧开关推导，保存过的值（含全 False）原样保留。

        推导结果直接写进实例（不进 model_fields_set），所以逐字段 PUT 只改一项时，其余六项带着推导出的值一起被
        `model_dump` 写回文件，不会因为只保存第一项而丢掉兼容值；读取本身不写文件。
        monday_to_thursday = True → 周一到周四允许；False → 七天都允许。
        """
        legacy_limited = self.monday_to_thursday
        for index, name in enumerate(WELFARE_WEEKDAY_FIELDS):
            if name not in self.model_fields_set:
                self.__dict__[name] = (index < 4) if legacy_limited else True
        return self

    def welfare_runs_on(self, weekday: int) -> bool:
        return bool(getattr(self, WELFARE_WEEKDAY_FIELDS[weekday]))

    def welfare_allowed_weekdays(self) -> tuple:
        return tuple(i for i in range(7) if self.welfare_runs_on(i))

    def __setattr__(self, name, value):
        # DokanConfig 没开 validate_assignment（不改变其他字段的保存行为），
        # 这里只让福利门槛在保存时校验：失败抛 ValidationError，原值保持不变
        if name == 'welfare_min_people':
            value = _WELFARE_MIN_PEOPLE.validate_python(value)
        super().__setattr__(name, value)


class DokanBattleConfig(GeneralBattleConfig):
    continuous_battle: bool = True

    @field_validator('continuous_battle', mode='after')
    @classmethod
    def validate_continuous_battle(cls, v):
        return True


class Dokan(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    dokan_config: DokanConfig = Field(default_factory=DokanConfig)
    dokan_member_battle_conf: DokanBattleConfig = Field(default_factory=DokanBattleConfig)
    dokan_owner_battle_conf: DokanBattleConfig = Field(default_factory=DokanBattleConfig)
    dokan_member_switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    dokan_owner_switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    attack_count_config: AttackAccountConfig = Field(default_factory=AttackAccountConfig)
