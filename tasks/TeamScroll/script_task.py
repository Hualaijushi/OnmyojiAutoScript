import json
from datetime import datetime, timedelta
from pathlib import Path

from module.exception import TaskEnd
from module.logger import logger
from tasks.TeamScroll.config import TeamScrollMode
from tasks.TeamScroll.coordinator import TeamScrollCoordinator
from tasks.base_task import BaseTask


class ScriptTask(BaseTask):
    def _delay_self(self, seconds: int = 30):
        self.set_next_run(task='TeamScroll', success=False, finish=False, server=False,
                          target=datetime.now() + timedelta(seconds=seconds))

    def _load_peer(self, name: str):
        path = Path('./config') / f'{name}.json'
        if not path.is_file():
            raise ValueError(f'协同脚本配置不存在: {name}')
        with path.open('r', encoding='utf-8-sig') as file:
            return json.load(file)

    def _validate(self):
        con = self.config.team_scroll.team_scroll_config
        peer_name = con.teammate_config_name.strip()
        if not peer_name:
            logger.warning('协同脚本名字为空，跳过组队绘卷')
            self.set_next_run(task='TeamScroll', success=True, finish=True)
            return None
        if peer_name == self.config.config_name:
            raise ValueError('协同脚本名字不能是当前脚本')
        if not self.config.exploration.scheduler.enable or not self.config.realm_raid.scheduler.enable:
            raise ValueError('组队绘卷强制要求启用探索和个人突破任务')

        peer = self._load_peer(peer_name)
        peer_team = peer.get('team_scroll', {})
        peer_detail = peer_team.get('team_scroll_config', {})
        if not peer_team.get('scheduler', {}).get('enable', False):
            raise ValueError(f'协同脚本 {peer_name} 未启用组队绘卷')
        if not peer.get('exploration', {}).get('scheduler', {}).get('enable', False) or \
                not peer.get('realm_raid', {}).get('scheduler', {}).get('enable', False):
            raise ValueError(f'协同脚本 {peer_name} 未同时启用探索和个人突破')
        if peer_detail.get('teammate_config_name', '').strip() != self.config.config_name:
            raise ValueError(f'协同脚本 {peer_name} 没有反向指向 {self.config.config_name}')
        expected_mode = TeamScrollMode.MEMBER if con.mode == TeamScrollMode.LEADER else TeamScrollMode.LEADER
        if peer_detail.get('mode') != expected_mode.value:
            raise ValueError('组队绘卷双方必须分别设置为队长和队员')
        return TeamScrollCoordinator.from_config(self.config)

    def run(self):
        logger.hr('TeamScroll')
        try:
            coordinator = self._validate()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            logger.error(str(error))
            self._delay_self(300)
            raise TaskEnd
        if coordinator is None:
            raise TaskEnd

        state = coordinator.ensure_session()
        phase = state['phase']
        player = state['players'][self.config.config_name]
        logger.info(f"TeamScroll round={state['round_id']} phase={phase}")

        if phase == 'exploring':
            self.set_next_run(task='Exploration', success=False, finish=False, server=False, target=datetime.now())
        elif phase == 'raid_requested' and not player['exploration_exited']:
            self.set_next_run(task='Exploration', success=False, finish=False, server=False, target=datetime.now())
        elif phase == 'realm_raid' and not player['realm_raid_done']:
            self.set_next_run(task='RealmRaid', success=False, finish=False, server=False, target=datetime.now())
        elif phase == 'resume':
            coordinator.mark_resume_ready()
            self.set_next_run(task='Exploration', success=False, finish=False, server=False, target=datetime.now())

        self._delay_self()
        raise TaskEnd
