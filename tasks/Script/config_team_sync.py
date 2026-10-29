# This Python file uses the following encoding: utf-8
from pydantic import BaseModel, Field


class TeamSync(BaseModel):
    enable: bool = Field(default=False, description='team_sync_enable_help')
    peer_instance: str = Field(default='', description='peer_instance_help')
