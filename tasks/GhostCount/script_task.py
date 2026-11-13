"""手动轮换本实例账号并采集五星、六星鬼王数量。"""

from datetime import date
from pathlib import Path

from module.exception import RequestHumanTakeover, TaskEnd
from module.logger import logger
from module.multi_account.courtyard_verifier import CourtyardCharacterVerifierMixin
from module.multi_account.event_ticket_report import EventTicketReport
from tasks.AccountRotation.script_task import RotationAccountSwitcher
from tasks.GameUi.game_ui import GameUi
from tasks.MetaDemonRotation.accounts import accounts_for_range
from tasks.MultiAccountEvo.ghost_count import collect_ghost_counts
from tasks.MultiAccountEvo.sync import MultiAccountEvoSync


class ScriptTask(GameUi, CourtyardCharacterVerifierMixin):
    task_name = 'GhostCount'

    def run(self):
        # 手动启用一次即关闭调度，避免采集任务隔天自行运行。
        self.config.reload()
        self.config.ghost_count.scheduler.enable = False
        self.config.save()
        evo = self.config.multi_account_evo
        instance = str(self.config.config_name).lower()
        roles = {'oas3': 'leader', 'oas4': 'member_1', 'oas5': 'member_2'}
        role = roles.get(instance)
        if role is None or evo.role.value != role:
            raise RequestHumanTakeover('鬼王数量采集的实例与觉醒角色不匹配')
        sync = MultiAccountEvoSync(Path.cwd() / 'config', timeout=evo.sync_timeout_seconds, event_mode=True)
        state = sync.read(allow_missing=True)
        if (not state or state['date'] != date.today().isoformat() or not state.get('event_mode')
                or not state.get('complete')
                or (state.get('group_start', 1), state.get('group_end', state['group_count']))
                != (evo.group_start, evo.group_end)):
            raise RequestHumanTakeover('请先完成本机今日门票组队觉醒，再手动采集鬼王数量')
        run_id = state['run_id']
        accounts = accounts_for_range(instance, evo, evo.group_start, evo.group_end)
        if not accounts or any(not account.enabled for account in accounts):
            raise RequestHumanTakeover('鬼王数量采集范围内存在未配置完整的账号')
        settings = self.config.account_rotation.account_rotation_config
        switcher = RotationAccountSwitcher(
            self.config, self.device, max_attempts=settings.max_switch_attempts,
            retry_delay=settings.retry_delay_seconds, timeout=settings.switch_timeout_seconds,
            fast=True, home_verifier=self._verify_courtyard_character,
        )
        report = EventTicketReport(sync, group_count=evo.group_count)
        missing = []
        for account in accounts:
            result = switcher.ensure_account(account)
            if not result.success:
                raise RequestHumanTakeover(f'鬼王数量采集切号失败：{account.account_id} {result.error_code.value}')
            counts = collect_ghost_counts(self.config, self.device)
            if any(value is None for value in counts.values()):
                missing.append(account.account_id)
            with sync._lock():
                current = sync._read_unlocked()
                if (current['date'] != date.today().isoformat() or current['run_id'] != run_id
                        or not current.get('complete')):
                    raise RequestHumanTakeover('门票会话已变化，停止写入鬼王数量')
                node = current['event_groups'].setdefault(str(account.position), {'roles': {}, 'samples': {}})
                info = node['roles'].setdefault(role, {})
                info['ghost_counts'] = dict(counts)
                info['ghost_counts_at'] = sync._now()
                sync._write_unlocked(current)
            report.refresh()
            logger.info('鬼王数量采集：账号=%s 5x=%s 6x=%s', account.account_id, counts['5'], counts['6'])
        if missing:
            self.set_next_run(self.task_name, finish=False, success=False)
            raise RequestHumanTakeover('部分账号的鬼王数量未识别，请查看日志与报告')
        self.set_next_run(self.task_name, finish=True, success=True)
        raise TaskEnd(self.task_name)
