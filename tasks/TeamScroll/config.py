from enum import Enum

from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class TeamScrollMode(str, Enum):
    LEADER = 'leader'
    MEMBER = 'member'


class TeamScrollConfig(BaseModel):
    teammate_config_name: str = Field(default='', description='teammate_config_name_help')
    mode: TeamScrollMode = Field(default=TeamScrollMode.LEADER, description='team_scroll_mode_help')
    realm_raid_ticket_threshold: int = Field(default=30, ge=1, le=30, description='realm_raid_ticket_threshold_help')


class TeamScroll(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    team_scroll_config: TeamScrollConfig = Field(default_factory=TeamScrollConfig)
