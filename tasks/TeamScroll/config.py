from enum import Enum

from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler
from tasks.Component.GeneralBattle.config_general_battle import GreenMarkEnum, GreenMarkType
from tasks.Component.GeneralInvite.config_invite import InviteConfig
from tasks.Exploration.config import AutoRotate, ChooseRarity, ExplorationLevel, UpType
from tasks.RealmRaid.config import RaidConfig


class TeamScrollMode(str, Enum):
    LEADER = 'leader'
    MEMBER = 'member'


class TeamScrollConfig(BaseModel):
    teammate_config_name: str = Field(default='', description='teammate_config_name_help')
    mode: TeamScrollMode = Field(default=TeamScrollMode.LEADER, description='team_scroll_mode_help')
    realm_raid_ticket_threshold: int = Field(default=30, ge=1, le=30, description='realm_raid_ticket_threshold_help')
    execution_time: Time = Field(
        default=Time(minute=30),
        title='执行时间',
        description='team_scroll_execution_time_help',
    )


class TeamScrollExplorationConfig(BaseModel):
    buff_gold_50_click: bool = False
    buff_gold_100_click: bool = False
    buff_exp_50_click: bool = False
    buff_exp_100_click: bool = False
    minions_cnt: int = Field(title='战斗次数', default=30, ge=0, description='minions_cnt_help')
    exploration_level: ExplorationLevel = Field(title='探索等级', default=ExplorationLevel.EXPLORATION_28,
                                                description='exploration_level_help')
    collect_paper_reward: bool = True
    auto_rotate: AutoRotate = Field(title='自动添加候补式神', default=AutoRotate.no,
                                    description='auto_rotate_help')
    choose_rarity: ChooseRarity = Field(title='选择狗粮稀有度', default=ChooseRarity.N,
                                        description='choose_rarity_help')
    up_type: UpType = Field(title='UpType', default=UpType.ALL, description='up_type_help')


class TeamScrollBattleConfig(BaseModel):
    """通用战斗配置，但不提供队伍预设切换功能。"""
    lock_team_enable: bool = Field(default=False, description='lock_team_enable_help')
    green_enable: bool = Field(default=False, description='green_enable_help')
    green_mark_type: GreenMarkEnum = GreenMarkEnum.CHOOSE
    green_mark: GreenMarkType = Field(default=GreenMarkType.GREEN_LEFT1, description='green_mark_help')
    green_mark_name: str = Field(default='', description='green_mark_name_help')
    random_click_swipt_enable: bool = Field(default=False, description='random_click_swipt_enable_help')
    battle_timeout: int = Field(default=-1, description='battle_timeout_help', ge=-1)


class TeamScrollSoulConfig(BaseModel):
    switch_before_task: bool = Field(title='执行任务前切换御魂', default=False,
                                     description='team_scroll_switch_before_task_help')
    exploration_group_team: str = Field(title='探索御魂装配分组', default='-1,-1',
                                        description='switch_group_team_help')
    realm_raid_group_team: str = Field(title='结界突破御魂装配分组', default='-1,-1',
                                      description='switch_group_team_help')
    switch_by_name: bool = Field(title='通过OCR切换御魂预设', default=False,
                                 description='team_scroll_switch_by_name_help')
    exploration_group_name: str = Field(title='探索御魂分组名称', default='')
    exploration_team_name: str = Field(title='探索御魂预设名称', default='')
    realm_raid_group_name: str = Field(title='结界突破御魂分组名称', default='')
    realm_raid_team_name: str = Field(title='结界突破御魂预设名称', default='')


class TeamScroll(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    team_scroll_config: TeamScrollConfig = Field(default_factory=TeamScrollConfig)
    exploration_config: TeamScrollExplorationConfig = Field(default_factory=TeamScrollExplorationConfig)
    exploration_invite_config: InviteConfig = Field(default_factory=InviteConfig)
    exploration_battle_config: TeamScrollBattleConfig = Field(default_factory=TeamScrollBattleConfig)
    realm_raid_config: RaidConfig = Field(default_factory=RaidConfig)
    realm_raid_battle_config: TeamScrollBattleConfig = Field(default_factory=TeamScrollBattleConfig)
    switch_soul_config: TeamScrollSoulConfig = Field(default_factory=TeamScrollSoulConfig)
