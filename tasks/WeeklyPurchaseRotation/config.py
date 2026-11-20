from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class WeeklyPurchaseRotation(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
