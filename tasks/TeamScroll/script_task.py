import json
from datetime import datetime, timedelta
from pathlib import Path

from module.exception import TaskEnd
from module.logger import logger
from tasks.TeamScroll.config import TeamScrollMode
from tasks.TeamScroll.coordinator import TeamScrollCoordinator
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Exploration.config import Exploration, ExplorationConfig, Scrolls, UserStatus
from tasks.Exploration.script_task import ScriptTask as ExplorationTask
from tasks.RealmRaid.config import RealmRaid
from tasks.RealmRaid.script_task import ScriptTask as RealmRaidTask
import tasks.Exploration.page as exploration_pages


class _ModelProxy:
    def __init__(self, model, overrides):
        self._model = model
        self._overrides = overrides

    def __getattr__(self, name):
        return self._overrides[name] if name in self._overrides else getattr(self._model, name)


class _EmbeddedConfig:
    def __init__(self, base, overrides):
        self._base = base
        self._overrides = overrides
        self.model = _ModelProxy(base.model, overrides)

    def __getattr__(self, name):
        return self._overrides[name] if name in self._overrides else getattr(self._base, name)

    def task_delay(self, task, *args, **kwargs):
        if task in ('Exploration', 'RealmRaid', 'MemoryScrolls'):
            logger.info(f'TeamScroll ignores embedded {task} scheduler update')
            return
        return self._base.task_delay(task, *args, **kwargs)


class _TeamScrollExplorationTask(ExplorationTask):
    coordinator: TeamScrollCoordinator

    def check_exit(self, current_page):
        if self.coordinator.is_expired(self.config.team_scroll.team_scroll_config.execution_time):
            self.coordinator.mark_finished()
            return True
        state = self.coordinator.read()
        if state['phase'] in ('raid_requested', 'realm_raid'):
            self._team_scroll_exit_requested = True
            return True
        if self.coordinator.mode == TeamScrollMode.LEADER and state['phase'] == 'exploring' and current_page in (
                exploration_pages.page_exploration, exploration_pages.page_exp_entrance):
            ocr = self.O_REALM_RAID_NUMBER1 if current_page == exploration_pages.page_exp_entrance \
                else self.O_REALM_RAID_NUMBER
            current, _, _ = ocr.ocr(self.device.image)
            threshold = self.config.team_scroll.team_scroll_config.realm_raid_ticket_threshold
            if current >= threshold:
                logger.info(f'TeamScroll ticket threshold reached: {current}/{threshold}')
                self.coordinator.request_realm_raid()
                self._team_scroll_exit_requested = True
                return True
        return super().check_exit(current_page)

    def run(self):
        logger.hr('TeamScroll Exploration')
        self.pre_process()
        self.exec_exp_page()
        if getattr(self, '_team_scroll_exit_requested', False):
            state = self.coordinator.mark_exploration_exited()
            logger.info(f"TeamScroll exploration exited, phase={state['phase']}")
        self.post_process()


class ScriptTask(ExplorationTask):
    def _delay_self(self, seconds: int = 30):
        self.set_next_run(task='TeamScroll', success=False, finish=False, server=False,
                          target=datetime.now() + timedelta(seconds=seconds))

    def _finish(self, coordinator):
        if coordinator.read()['phase'] != 'finished':
            coordinator.mark_finished()
        self.set_next_run(task='TeamScroll', success=True, finish=True)
        raise TaskEnd

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
        peer = self._load_peer(peer_name)
        peer_team = peer.get('team_scroll', {})
        peer_detail = peer_team.get('team_scroll_config', {})
        if not peer_team.get('scheduler', {}).get('enable', False):
            raise ValueError(f'协同脚本 {peer_name} 未启用组队绘卷')
        if peer_detail.get('teammate_config_name', '').strip() != self.config.config_name:
            raise ValueError(f'协同脚本 {peer_name} 没有反向指向 {self.config.config_name}')
        expected_mode = TeamScrollMode.MEMBER if con.mode == TeamScrollMode.LEADER else TeamScrollMode.LEADER
        if peer_detail.get('mode') != expected_mode.value:
            raise ValueError('组队绘卷双方必须分别设置为队长和队员')
        return TeamScrollCoordinator.from_config(self.config)

    @staticmethod
    def _battle_config(source):
        return GeneralBattleConfig(**source.model_dump())

    def _exploration_view(self):
        team = self.config.team_scroll
        role = UserStatus.LEADER if team.team_scroll_config.mode == TeamScrollMode.LEADER else UserStatus.MEMBER
        detail = ExplorationConfig(**team.exploration_config.model_dump(), user_status=role,
                                   limit_time=team.team_scroll_config.execution_time)
        return Exploration(exploration_config=detail, scrolls=Scrolls(scrolls_enable=False),
                           invite_config=team.exploration_invite_config,
                           general_battle_config=self._battle_config(team.exploration_battle_config),
                           switch_soul_config=SwitchSoulConfig(enable=False))

    def _realm_raid_view(self):
        team = self.config.team_scroll
        return RealmRaid(raid_config=team.realm_raid_config,
                         general_battle_config=self._battle_config(team.realm_raid_battle_config),
                         switch_soul_config=SwitchSoulConfig(enable=False))

    def _switch_soul_for(self, phase: str):
        soul = self.config.team_scroll.switch_soul_config
        if not soul.switch_before_task:
            return
        self.goto_page(exploration_pages.page_shikigami_records)
        if soul.switch_by_name:
            group = soul.exploration_group_name if phase == 'exploration' else soul.realm_raid_group_name
            team = soul.exploration_team_name if phase == 'exploration' else soul.realm_raid_team_name
            self.run_switch_soul_by_name(group, team)
        else:
            target = soul.exploration_group_team if phase == 'exploration' else soul.realm_raid_group_team
            self.run_switch_soul(target)

    def _run_exploration(self, coordinator):
        self._switch_soul_for('exploration')
        task = _TeamScrollExplorationTask(
            _EmbeddedConfig(self.config, {'exploration': self._exploration_view()}), self.device)
        task.coordinator = coordinator
        try:
            task.run()
        except TaskEnd:
            pass

    def _run_realm_raid(self, coordinator):
        self._switch_soul_for('realm_raid')
        task = RealmRaidTask(_EmbeddedConfig(self.config, {'realm_raid': self._realm_raid_view()}), self.device)
        try:
            task.run()
        except TaskEnd:
            pass
        state = coordinator.mark_realm_raid_done()
        logger.info(f"TeamScroll RealmRaid done, phase={state['phase']}")

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
        if state['phase'] == 'finished' or coordinator.is_expired(
                self.config.team_scroll.team_scroll_config.execution_time):
            self._finish(coordinator)
        phase = state['phase']
        player = state['players'][self.config.config_name]
        logger.info(f"TeamScroll round={state['round_id']} phase={phase}")
        if phase == 'exploring':
            self._run_exploration(coordinator)
        elif phase == 'raid_requested' and not player['exploration_exited']:
            self._run_exploration(coordinator)
        elif phase == 'realm_raid' and not player['realm_raid_done']:
            self._run_realm_raid(coordinator)
        elif phase == 'resume':
            coordinator.mark_resume_ready()
        self._delay_self()
        raise TaskEnd
