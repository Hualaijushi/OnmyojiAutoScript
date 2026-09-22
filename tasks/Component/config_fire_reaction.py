# This Python file uses the following encoding: utf-8
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from module.interaction_policy import (
    DEFAULT_FIRE_REACTION_MAX_MS,
    DEFAULT_FIRE_REACTION_MIN_MS,
    FIRE_REACTION_LIMIT_MS,
)


class FireReactionConfig(BaseModel):
    """当前任务的 FIRE（Battle Entry Action）点击前 reaction override，单位毫秒。

    各 FIRE 任务共用这一份 schema、各自保存取值；没有该配置组的任务用公共默认 400~800ms。
    校验：0 <= min <= max <= 5000，min == max 合法（固定延迟）。非法值在配置层直接拒绝，
    运行时不交换、不钳制。

    `validate_assignment` + 字段级交叉校验：OASX 单字段修改走 `setattr`，校验失败时旧值保持不变
    （用 model 级 after 校验会先写入非法值再报错，内存里残留非法状态）。
    """
    model_config = ConfigDict(validate_assignment=True)

    fire_reaction_min_ms: int = Field(default=DEFAULT_FIRE_REACTION_MIN_MS, ge=0, le=FIRE_REACTION_LIMIT_MS,
                                      description='fire_reaction_min_ms_help')
    fire_reaction_max_ms: int = Field(default=DEFAULT_FIRE_REACTION_MAX_MS, ge=0, le=FIRE_REACTION_LIMIT_MS,
                                      description='fire_reaction_max_ms_help')

    @field_validator('fire_reaction_min_ms')
    @classmethod
    def _min_not_above_max(cls, value: int, info: ValidationInfo) -> int:
        other = info.data.get('fire_reaction_max_ms')
        if other is not None and value > other:
            raise ValueError(f'FIRE 点击前最小延迟 {value}ms 不能大于最大延迟 {other}ms')
        return value

    @field_validator('fire_reaction_max_ms')
    @classmethod
    def _max_not_below_min(cls, value: int, info: ValidationInfo) -> int:
        other = info.data.get('fire_reaction_min_ms')
        if other is not None and value < other:
            raise ValueError(f'FIRE 点击前最大延迟 {value}ms 不能小于最小延迟 {other}ms')
        return value
