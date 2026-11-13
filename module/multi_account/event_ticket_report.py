"""超鬼王门票只读HTML镜像，展示失败不能改变刷取事实。"""

from datetime import date
from html import escape
import json
import os
from pathlib import Path
import re
import threading
import uuid
from urllib.parse import quote

from module.multi_account.daily_task_archive import refresh_report_archive
from module.multi_account.file_lock import atomic_replace_with_retry, interprocess_file_lock


ROLES = ('leader', 'member_1', 'member_2')
STATUS = {'running': '刷取中', 'sampling': '采样中', 'finishing': '达标，正在收尾', 'completed': '三端已达标', 'failed': '未完成 / 已停止'}


def ticket_entry(day: str) -> str:
    day = date.fromisoformat(day).isoformat()
    filename = f'OAS超鬼王门票刷取情况_{day}.html'
    return (
        '<section class="card" id="ticket-report"><div style="padding:22px">'
        '<h2 style="margin:0 0 9px">超鬼王门票情况</h2>'
        '<p style="color:#687486">查看各账号组的三端门票、刷场进度和异常记录。</p>'
        f'<a href="{quote(filename)}" style="display:inline-block;background:#2865bd;color:white;'
        'padding:11px 18px;border-radius:7px;text-decoration:none">打开每日超鬼王门票刷取情况</a>'
        '</div></section>'
    )


def render_ticket_report(state: dict, account_emails: dict | None = None) -> str:
    """渲染门票与鬼王数量，不更改底层状态。"""
    from module.multi_account.event_ticket_layout import render_ticket_layout
    return render_ticket_layout(state, account_emails)


class EventTicketReport:
    def __init__(self, sync, *, group_count=20, group_start=1, group_end=0,
                 event_ocr_start=200, event_ocr_interval=10, battle_count=250, output_dir=None):
        self.sync = sync
        self.group_count = group_count
        self.policy = dict(group_start=group_start, group_end=group_end or group_count,
                           event_ocr_start=event_ocr_start, event_ocr_interval=event_ocr_interval,
                           battle_count=battle_count)
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / 'log/dailytask'

    def _account_emails(self):
        """仅从本机三端配置读取邮箱，不写回同步状态。"""
        result = {}
        for instance, prefix in (('oas3', 'A'), ('oas4', 'B'), ('oas5', 'C')):
            try:
                data = json.loads((self.sync.directory / f'{instance}.json').read_text(encoding='utf-8-sig'))
                accounts = data.get('multi_account_evo', {})
                for number in range(1, self.group_count + 1):
                    info = accounts.get(f'account_list_{number}', {})
                    if isinstance(info, dict):
                        result[f'{prefix}{number:02d}'] = str(info.get('account') or '').strip()
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
                continue
        return result

    @staticmethod
    def _write(path, text):
        temporary = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
        try:
            with temporary.open('w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            atomic_replace_with_retry(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def refresh(self, _daily_state=None):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with interprocess_file_lock(self.output_dir / '.daily_task_report.lock', timeout=10):
            state = self.sync.read() if self.sync.state_path.exists() else {
                'date': date.today().isoformat(), 'group_count': self.group_count,
                **self.policy,
            }
            day = date.fromisoformat(state['date']).isoformat()
            path = self.output_dir / f'OAS超鬼王门票刷取情况_{day}.html'
            if path.exists():
                old_bytes = path.read_bytes()
                old_text = old_bytes.decode('utf-8-sig')
                match = re.search(r'本机第(\d+)～(\d+)组', old_text)
                old_scope = tuple(map(int, match.groups())) if match else None
                new_scope = (state.get('group_start', 1),
                             state.get('group_end', state.get('group_count', 20)))
                if old_scope != new_scope:
                    # 范围切换时保留原日报；无法辨认旧范围也先备份。
                    backup = path.with_name(f'{path.name}.before-range-{uuid.uuid4().hex}.bak')
                    with backup.open('xb') as stream:
                        stream.write(old_bytes)
                        stream.flush()
                        os.fsync(stream.fileno())
            self._write(path, render_ticket_report(state, self._account_emails()))
            daily = self.output_dir / f'OAS每日任务结果_{day}.html'
            if daily.exists():
                content = daily.read_text(encoding='utf-8-sig')
                if 'id="ticket-report"' not in content:
                    self._write(daily, content.replace('</main>', ticket_entry(day) + '</main>', 1))
            else:
                self._write(daily, '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                            '<title>每日任务日志</title><main><h1>每日任务日志</h1>'
                            '<p>今日每日轮换尚无报告记录。</p>' + ticket_entry(day) + '</main></html>')
            refresh_report_archive(self.output_dir, date.today())
            return path
