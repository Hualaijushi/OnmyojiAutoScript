# This Python file uses the following encoding: utf-8
from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class SyncConfig(BaseModel):
    # 两个实例填相同的值（用 PUT /config/task/group/copy 整组复制）；合法性在任务启动检查里做，不写 validator
    instance_a: str = Field(default='', description='instance_a_help')
    alias_a: str = Field(default='', description='alias_a_help')
    instance_b: str = Field(default='', description='instance_b_help')
    alias_b: str = Field(default='', description='alias_b_help')
    rendezvous_timeout: int = Field(default=600, description='rendezvous_timeout_help', ge=60, le=1800)


class ResetConfig(BaseModel):
    # 单独成组：整组复制 sync 时不能把「已打开」的人工确认带到另一个实例
    reset_unsafe: bool = Field(default=False, description='reset_unsafe_help')


class XinLan(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    reset: ResetConfig = Field(default_factory=ResetConfig)
