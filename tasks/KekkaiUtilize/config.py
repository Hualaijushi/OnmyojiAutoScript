# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime, time, timedelta

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time, TimeDelta
from tasks.Utils.config_enum import ShikigamiClass

class SelectFriendList(str, Enum):
    SAME_SERVER = 'same_server'
    DIFFERENT_SERVER = 'different_server'

class UtilizeRule(str, Enum):
    DEFAULT = 'default'  # 默认就好
    TAIKO = 'kaiko'  # 太鼓优先
    FISH = 'fish'  # 斗鱼优先
    # AUTO = 'auto'  # 自动 兼容代码罢了



class UtilizeScheduler(Scheduler):
    priority: int = Field(default=2, description='priority_help')
    success_interval: TimeDelta = Field(default=TimeDelta(hours=6), description='success_interval_help')
    failure_interval: TimeDelta = Field(default=TimeDelta(hours=6), description='failure_interval_help')

    # 静默窗口（Scheduler v1）：默认 00:00~07:00 不进入实际业务；候选 next_run 落入窗内
    # 时顺延到窗口结束 + 随机恢复抖动。类型沿用 `AntiBan.sleep_start/sleep_end` 同一套
    # `Time`（复用既有 schema，不发明新的 time-range 类型）。
    quiet_window_enable: bool = Field(default=True, description='quiet_window_enable_help')
    quiet_start: Time = Field(default=Time(hour=0, minute=0, second=0), description='quiet_start_help')
    quiet_end: Time = Field(default=Time(hour=7, minute=0, second=0), description='quiet_end_help')
    quiet_resume_jitter_min: int = Field(default=5, ge=0, description='quiet_resume_jitter_min_help')
    quiet_resume_jitter_max: int = Field(default=30, ge=0, description='quiet_resume_jitter_max_help')

    # 短期 retry cooldown（分钟）：未找到达标结界卡 / 好友列表刷新失败等短期失败出口
    # 统一走它（见 `docs/DECISIONS.md` 对应 ADR），取代此前各出口各自硬编码的 5/10/20 分钟。
    cooldown_min: int = Field(default=5, ge=0, description='cooldown_min_help')
    cooldown_max: int = Field(default=30, ge=0, description='cooldown_max_help')

    # 跨字段边界校验用 `field_validator`（沿用 `tasks/Dokan/config.py` 等既有 `ConfigBase`
    # 子类的写法），不用 `model_validator`——`ConfigBase.__init__` 的异常恢复只按
    # `exc.errors()[0]['loc'][0]` 取出单个越界字段名做默认值回退，`model_validator` 产生的
    # 模型级错误 `loc` 为空元组，会让那段恢复逻辑直接 `IndexError` 崩溃（本轮实测复现）。
    @field_validator('cooldown_max', mode='after')
    @classmethod
    def validate_cooldown_max(cls, v, info):
        cooldown_min = info.data.get('cooldown_min')
        if cooldown_min is not None and v < cooldown_min:
            raise ValueError('cooldown_max 不能小于 cooldown_min')
        return v

    @field_validator('quiet_resume_jitter_max', mode='after')
    @classmethod
    def validate_quiet_resume_jitter_max(cls, v, info):
        jitter_min = info.data.get('quiet_resume_jitter_min')
        if jitter_min is not None and v < jitter_min:
            raise ValueError('quiet_resume_jitter_max 不能小于 quiet_resume_jitter_min')
        return v

class UtilizeConfig(BaseModel):
    utilize_rule: UtilizeRule = Field(default=UtilizeRule.DEFAULT, description='utilize_rule_help')
    select_friend_list: SelectFriendList = Field(default=SelectFriendList.SAME_SERVER, description='select_friend_list_help')
    # 收益阈值：浏览到不低于该值的结界卡就直接进入寄养，不再继续下划。
    # 默认取六星满值，等价于改动前只有命中理论最高收益才提前停止的行为。
    taiko_reward_threshold: int = Field(default=76, ge=1, description='taiko_reward_threshold_help')
    fish_reward_threshold: int = Field(default=151, ge=1, description='fish_reward_threshold_help')
    auto_fill: bool = Field(default=False, description='auto_fill_help')
    # 是否自动检查自己结界里的满级式神并替换：True 保留 check_max_lv() 全套逻辑（满级检测 →
    # 卸下 → 切换式神 → 自动补位）；False 完全跳过。默认关闭，不影响 shikigami_class / auto_fill
    # 本身的语义——它们仍是 check_max_lv() 的参数，只是这个开关决定要不要调它。
    auto_replace_max_level: bool = Field(default=False, description='auto_replace_max_level_help')
    shikigami_class: ShikigamiClass = Field(default=ShikigamiClass.N, description='shikigami_class_help')
    shikigami_order: int = Field(default=4, description='shikigami_order_help')
    min_run_interval: TimeDelta = Field(default=timedelta(0), description='min_run_interval_help')
    harvest_guild_max_times: int = Field(default=2, description='harvest_guild_max_times_help')
    utilize_harvest: bool = Field(default=True, description='utilize_harvest_help')
    utilize_enable: bool = Field(default=True, description='utilize_enable_help')
    lazy_mode: bool = Field(default=False, description='lazy_mode_help')
    lazy_mode_weight: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description='lazy_mode_weight_help',
    )
    box_ap_enable: bool = Field(default=True)
    box_exp_enable: bool = Field(default=True)
    box_exp_waste: bool = Field(default=True, description='box_exp_waste_help')


class KekkaiUtilize(ConfigBase):
    scheduler: UtilizeScheduler = Field(default_factory=UtilizeScheduler)
    utilize_config: UtilizeConfig = Field(default_factory=UtilizeConfig)
