"""手动采集鬼王数量的独立任务配置。"""

from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class GhostCount(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
