# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from tasks.GlobalGame.config_emergency import Emergency
from tasks.Component.Costume.config import CostumeConfig


class Transport(str, Enum):
    TCP = 'TCP'
    SSL_TLS = 'SSL/TLS'


class TeamFlow(BaseModel):
    enable: bool = Field(default=False, description='enable_help')
    broker: str = Field(default='', description='broker_help')
    port: int = Field(default=8883, description='port_help')
    transport: Transport = Field(default=Transport.TCP, description='transport_help')
    ca: str = Field(default='', description='ca_help')
    username: str = Field(default='', description='username_help')
    password: str = Field(default='', description='password_help')


class BattleTaskOverEnum(str, Enum):
    FINISH = 'finish'
    EXIT = 'exit'


class BattleTakeover(BaseModel):
    battle_timeout: int = Field(default=420, description='battle_timeout_global_help', ge=1)
    on_takeover: BattleTaskOverEnum = Field(default=BattleTaskOverEnum.FINISH, description='on_takeover_help')


class OcrLog(BaseModel):
    save_ocr_log: bool = Field(default=False, description='save_ocr_log_help')


class FatigueProbability(BaseModel):
    maximum: float = Field(default=0.18, ge=0.0, lt=1.0)
    steepness: float = Field(default=0.11, gt=0.0)
    midpoint: float = Field(default=52.0, ge=0.0, le=100.0)


class TaskFatigueConfig(BaseModel):
    time_scale_minutes: float = Field(default=65.0, gt=0.0, description='task.time_scale_minutes_help')
    repeat_scale: float = Field(default=15.0, gt=0.0, description='task.repeat_scale_help')
    time_weight: float = Field(default=70.0, ge=0.0, description='task.time_weight_help')
    repeat_weight: float = Field(default=20.0, ge=0.0, description='task.repeat_weight_help')


class GlobalFatigueConfig(BaseModel):
    time_scale_minutes: float = Field(default=180.0, gt=0.0, description='global_fatigue.time_scale_minutes_help')
    exponent: float = Field(default=2.0, gt=1.0, description='global_fatigue.exponent_help')


class FatigueWeights(BaseModel):
    idle_task: float = Field(default=0.8, ge=0.0, description='weights.idle_task_help')
    idle_global: float = Field(default=0.2, ge=0.0, description='weights.idle_global_help')
    rest_task: float = Field(default=0.25, ge=0.0, description='weights.rest_task_help')
    rest_global: float = Field(default=0.75, ge=0.0, description='weights.rest_global_help')


class IdleFatigueConfig(BaseModel):
    # steepness / midpoint 即原 idle.probability 的 k / F0，数值不变，只是不再嵌套在
    # probability 子模型下；它们现在只决定“疲劳强度”logistic，不再是单节点概率。
    steepness: float = Field(default=0.11, gt=0.0, description='idle.steepness_help')
    midpoint: float = Field(default=52.0, ge=0.0, le=100.0, description='idle.midpoint_help')
    # idle 事件率：低疲劳保留少量自然走神，高疲劳趋近上限。单位：次 / 小时。
    # 上限只是高疲劳状态的理论值，不表示每小时必定触发这么多次。
    rate_base: float = Field(default=1.5, gt=0.0, description='idle.rate_base_help')
    rate_max: float = Field(default=4.0, gt=0.0, description='idle.rate_max_help')
    # 三角分布时长：最短、众数下限（低疲劳众数）、众数上限（高疲劳众数）、最长。
    minimum_seconds: float = Field(default=15.0, ge=0.0, description='idle.minimum_seconds_help')
    mode_minimum_seconds: float = Field(default=25.0, gt=0.0, description='idle.mode_minimum_seconds_help')
    mode_maximum_seconds: float = Field(default=70.0, gt=0.0, description='idle.mode_maximum_seconds_help')
    maximum_seconds: float = Field(default=120.0, gt=0.0, description='idle.maximum_seconds_help')
    range_floor_ratio: float = Field(default=0.12, ge=0.0, le=1.0, description='idle.range_floor_ratio_help')
    task_recovery_per_minute: float = Field(default=8.0, ge=0.0, description='idle.task_recovery_per_minute_help')
    global_recovery_per_minute: float = Field(default=0.5, ge=0.0, description='idle.global_recovery_per_minute_help')

    @model_validator(mode='after')
    def validate_rate(self):
        if self.rate_max < self.rate_base:
            raise ValueError('idle 事件率上限不能小于基础事件率')
        return self

    @model_validator(mode='after')
    def validate_duration(self):
        if not (
            self.minimum_seconds
            <= self.mode_minimum_seconds
            <= self.mode_maximum_seconds
            <= self.maximum_seconds
        ):
            raise ValueError('发呆时长必须满足 最短 <= 众数下限 <= 众数上限 <= 最长')
        return self


class RestProbability(FatigueProbability):
    maximum: float = Field(default=0.12, ge=0.0, lt=1.0, description='rest.probability.maximum_help')
    steepness: float = Field(default=0.10, gt=0.0, description='rest.probability.steepness_help')
    midpoint: float = Field(default=58.0, ge=0.0, le=100.0, description='rest.probability.midpoint_help')


class RestFatigueConfig(BaseModel):
    probability: RestProbability = Field(default_factory=RestProbability)
    minimum_seconds: float = Field(default=120.0, ge=0.0, description='rest.minimum_seconds_help')
    # 众数下限默认等于最短时间，保持 rest 时长的既有行为不变。
    mode_minimum_seconds: float = Field(default=120.0, gt=0.0, description='rest.mode_minimum_seconds_help')
    mode_maximum_seconds: float = Field(default=600.0, gt=0.0, description='rest.mode_maximum_seconds_help')
    maximum_seconds: float = Field(default=1200.0, gt=0.0, description='rest.maximum_seconds_help')
    range_floor_ratio: float = Field(default=0.2, ge=0.0, le=1.0, description='rest.range_floor_ratio_help')
    task_recovery_maximum: float = Field(default=70.0, ge=0.0, description='rest.task_recovery_maximum_help')
    task_recovery_tau_minutes: float = Field(default=7.0, gt=0.0, description='rest.task_recovery_tau_minutes_help')
    global_recovery_maximum: float = Field(default=65.0, ge=0.0, description='rest.global_recovery_maximum_help')
    global_recovery_tau_minutes: float = Field(default=9.0, gt=0.0, description='rest.global_recovery_tau_minutes_help')

    @model_validator(mode='after')
    def validate_duration(self):
        if not (
            self.minimum_seconds
            <= self.mode_minimum_seconds
            <= self.mode_maximum_seconds
            <= self.maximum_seconds
        ):
            raise ValueError('休息时长必须满足 最短 <= 众数下限 <= 众数上限 <= 最长')
        return self


class RestCooldownConfig(BaseModel):
    base_minutes: float = Field(default=30.0, ge=0.0, description='cooldown.base_minutes_help')
    rest_duration_multiplier: float = Field(default=3.0, ge=0.0, description='cooldown.rest_duration_multiplier_help')
    jitter_minimum: float = Field(default=0.85, gt=0.0, description='cooldown.jitter_minimum_help')
    jitter_maximum: float = Field(default=1.15, gt=0.0, description='cooldown.jitter_maximum_help')

    @model_validator(mode='after')
    def validate_jitter(self):
        if self.jitter_maximum < self.jitter_minimum:
            raise ValueError('休息冷却随机上限不能小于下限')
        return self


class SchedulerIdleConfig(BaseModel):
    # scheduler_idle（无任务可执行的调度空档）：前 recovery_delay_minutes 分钟只冻结
    # GlobalFatigue，超过后按 1 - exp(-(t - delay) / tau) 指数自然恢复。t 为真实墙钟分钟数。
    recovery_delay_minutes: float = Field(default=5.0, ge=0.0, description='scheduler_idle.recovery_delay_minutes_help')
    recovery_tau_minutes: float = Field(default=34.0, gt=0.0, description='scheduler_idle.recovery_tau_minutes_help')


class FatigueConfig(BaseModel):
    enable: bool = Field(default=False, description='是否启用疲劳、发呆和休息机制')
    load_factor: float = Field(
        default=1.1,
        ge=0.8,
        le=1.3,
        description='当前实例任务疲劳增长负荷系数',
    )
    task: TaskFatigueConfig = Field(default_factory=TaskFatigueConfig)
    global_fatigue: GlobalFatigueConfig = Field(default_factory=GlobalFatigueConfig)
    weights: FatigueWeights = Field(default_factory=FatigueWeights)
    idle: IdleFatigueConfig = Field(default_factory=IdleFatigueConfig)
    rest: RestFatigueConfig = Field(default_factory=RestFatigueConfig)
    cooldown: RestCooldownConfig = Field(default_factory=RestCooldownConfig)
    scheduler_idle: SchedulerIdleConfig = Field(default_factory=SchedulerIdleConfig)


class GlobalGame(BaseModel):
    emergency: Emergency = Field(default_factory=Emergency)
    costume_config: CostumeConfig = Field(default_factory=CostumeConfig)
    battle: BattleTakeover = Field(default_factory=BattleTakeover)
    ocr: OcrLog = Field(default_factory=OcrLog)
    team_flow: TeamFlow = Field(default_factory=TeamFlow)
    fatigue: FatigueConfig = Field(default_factory=FatigueConfig)
