import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Callable

from tasks.TeamScroll.config import TeamScrollMode


class TeamScrollCoordinator:
    """Persistent cross-process state for one pair of OAS instances."""

    DB_PATH = Path('./config/team_scroll.sqlite3')

    def __init__(self, config_name: str, teammate: str, mode: TeamScrollMode | str):
        self.config_name = config_name.strip()
        self.teammate = teammate.strip()
        self.mode = TeamScrollMode(mode)
        self.leader = self.config_name if self.mode == TeamScrollMode.LEADER else self.teammate
        self.member = self.teammate if self.mode == TeamScrollMode.LEADER else self.config_name
        self.pair_id = '|'.join(sorted((self.config_name, self.teammate)))
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_config(cls, config, require_session: bool = False):
        if not config.team_scroll.scheduler.enable:
            return None
        con = config.team_scroll.team_scroll_config
        teammate = con.teammate_config_name.strip()
        if not teammate:
            return None
        coordinator = cls(config.config_name, teammate, con.mode)
        if require_session and not coordinator.exists():
            return None
        return coordinator

    def _connect(self):
        connection = sqlite3.connect(self.DB_PATH, timeout=5)
        connection.execute('PRAGMA busy_timeout=5000')
        connection.execute('PRAGMA journal_mode=WAL')
        return connection

    def _initialize(self):
        with closing(self._connect()) as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS team_scroll_state ('
                'pair_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TEXT NOT NULL)'
            )
            connection.commit()

    def _default_state(self):
        return {
            'pair_id': self.pair_id,
            'round_id': 0,
            'phase': 'exploring',
            'leader': self.leader,
            'member': self.member,
            'players': {
                self.leader: {'exploration_exited': False, 'realm_raid_done': False, 'resume_ready': False},
                self.member: {'exploration_exited': False, 'realm_raid_done': False, 'resume_ready': False},
            },
        }

    def read(self):
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT state_json FROM team_scroll_state WHERE pair_id=?', (self.pair_id,)).fetchone()
        return json.loads(row[0]) if row else self._default_state()

    def exists(self):
        with closing(self._connect()) as connection:
            row = connection.execute(
                'SELECT 1 FROM team_scroll_state WHERE pair_id=?', (self.pair_id,)
            ).fetchone()
        return row is not None

    def update(self, mutator: Callable[[dict], None]):
        with closing(self._connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT state_json FROM team_scroll_state WHERE pair_id=?', (self.pair_id,)).fetchone()
            state = json.loads(row[0]) if row else self._default_state()
            if state.get('leader') != self.leader or state.get('member') != self.member:
                state = self._default_state()
            mutator(state)
            now = datetime.now().isoformat(timespec='seconds')
            connection.execute(
                'INSERT INTO team_scroll_state(pair_id,state_json,updated_at) VALUES(?,?,?) '
                'ON CONFLICT(pair_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at',
                (self.pair_id, json.dumps(state, ensure_ascii=False), now),
            )
            connection.commit()
            return state

    def ensure_session(self):
        return self.update(lambda state: None)

    def request_realm_raid(self):
        def mutate(state):
            if self.config_name != state['leader'] or state['phase'] != 'exploring':
                return
            state['round_id'] += 1
            state['phase'] = 'raid_requested'
            for player in state['players'].values():
                player.update(exploration_exited=False, realm_raid_done=False, resume_ready=False)
        return self.update(mutate)

    def mark_exploration_exited(self):
        def mutate(state):
            if state['phase'] not in ('raid_requested', 'realm_raid'):
                return
            state['players'][self.config_name]['exploration_exited'] = True
            if all(player['exploration_exited'] for player in state['players'].values()):
                state['phase'] = 'realm_raid'
        return self.update(mutate)

    def mark_realm_raid_done(self):
        def mutate(state):
            if state['phase'] not in ('realm_raid', 'resume'):
                return
            state['players'][self.config_name]['realm_raid_done'] = True
            if all(player['realm_raid_done'] for player in state['players'].values()):
                state['phase'] = 'resume'
        return self.update(mutate)

    def mark_resume_ready(self):
        def mutate(state):
            if state['phase'] != 'resume':
                return
            state['players'][self.config_name]['resume_ready'] = True
            if all(player['resume_ready'] for player in state['players'].values()):
                state['phase'] = 'exploring'
                for player in state['players'].values():
                    player.update(exploration_exited=False, realm_raid_done=False, resume_ready=False)
        return self.update(mutate)
