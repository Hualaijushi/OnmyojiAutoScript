import json
import sqlite3
from contextlib import closing
from datetime import datetime, time
from pathlib import Path
from typing import Callable

from tasks.TeamScroll.config import TeamScrollMode


class TeamScrollCoordinator:
    """Persistent cross-process state for one pair of OAS instances."""

    DB_PATH = Path('./config/team_scroll.sqlite3')
    STATE_VERSION = 2

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
        now = datetime.now().isoformat(timespec='seconds')
        return {
            'version': self.STATE_VERSION,
            'pair_id': self.pair_id,
            'round_id': 0,
            'phase': 'exploring',
            'leader': self.leader,
            'member': self.member,
            'started_at': now,
            'finished_at': None,
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
        def mutate(state):
            if state.get('version') != self.STATE_VERSION:
                state.clear()
                state.update(self._default_state())
                return
            if not state.get('started_at'):
                state['started_at'] = datetime.now().isoformat(timespec='seconds')
            state.setdefault('finished_at', None)
            # 已结束的协同轮次只允许在次日重新开始，避免另一个脚本在收尾时立即重开。
            if state.get('phase') != 'finished' or not state.get('finished_at'):
                return
            if datetime.fromisoformat(state['finished_at']).date() < datetime.now().date():
                state.clear()
                state.update(self._default_state())
        return self.update(mutate)

    def is_expired(self, execution_time: time):
        state = self.read()
        if state.get('phase') == 'finished':
            return True
        started_at = datetime.fromisoformat(state.get('started_at') or datetime.now().isoformat())
        elapsed = (datetime.now() - started_at).total_seconds()
        limit = execution_time.hour * 3600 + execution_time.minute * 60 + execution_time.second
        return elapsed >= limit

    def mark_finished(self):
        def mutate(state):
            state['phase'] = 'finished'
            state['finished_at'] = datetime.now().isoformat(timespec='seconds')
        return self.update(mutate)

    def request_realm_raid(self):
        def mutate(state):
            if self.config_name != state['leader'] or state['phase'] != 'exploring':
                return
            state['round_id'] += 1
            state['phase'] = 'raid_requested'
            for player in state['players'].values():
                player.update(exploration_exited=False, realm_raid_done=False, resume_ready=False)
        return self.update(mutate)

    def request_ticket_check(self):
        def mutate(state):
            if self.config_name != state['leader'] or state['phase'] != 'exploring':
                return
            state['round_id'] += 1
            state['phase'] = 'check_requested'
            for player in state['players'].values():
                player.update(exploration_exited=False, realm_raid_done=False, resume_ready=False)
        return self.update(mutate)

    def mark_exploration_exited(self):
        def mutate(state):
            if state['phase'] not in ('check_requested', 'raid_requested', 'realm_raid'):
                return
            state['players'][self.config_name]['exploration_exited'] = True
            if all(player['exploration_exited'] for player in state['players'].values()):
                state['phase'] = 'checking' if state['phase'] == 'check_requested' else 'realm_raid'
        return self.update(mutate)

    def resolve_ticket_check(self, reached: bool):
        def mutate(state):
            if self.config_name != state['leader'] or state['phase'] != 'checking':
                return
            state['phase'] = 'realm_raid' if reached else 'resume'
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
