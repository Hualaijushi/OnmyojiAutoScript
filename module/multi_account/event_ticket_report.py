"""超鬼王门票只读HTML镜像，展示失败不能改变刷取事实。"""

from datetime import date
from html import escape
import os
from pathlib import Path
import threading
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


def render_ticket_report(state: dict) -> str:
    day = str(state['date'])
    rows = []
    groups = state.get('event_groups', {})
    start, end = state.get('group_start', 1), state.get('group_end', state.get('group_count', 20))
    for number in range(start, end + 1):
        node = groups.get(str(number), {})
        cells = []
        for role, prefix in zip(ROLES, ('A', 'B', 'C')):
            info = node.get('roles', {}).get(role, {})
            value = info.get('value')
            display = '未采集' if value is None else f'{value}/50'
            suffix = ' · 已达标，继续跟队' if info.get('reached') else ''
            character = escape(str(info.get('character') or ''))
            cells.append(f'<td><strong>{prefix}{number:02d} {character}</strong><br>{escape(display + suffix)}</td>')
        counts = state.get('battle_progress', {}).get(str(number), {})
        progress = escape(' / '.join(str(counts.get(role, '—')) for role in ROLES))
        status = ('人工确认完成' if node.get('completion_source') == 'user_confirmed'
                  else STATUS.get(node.get('status'), '尚无记录'))
        rows.append(f'<tr><td>第{number:02d}组</td>' + ''.join(cells)
                    + f'<td>{progress}</td><td>{status}</td>'
                    + f'<td>{escape(str(node.get("updated_at") or "—"))}</td></tr>')
        history = []
        for sample in node.get('samples', {}).values():
            values = []
            for role in ROLES:
                result = sample.get('reports', {}).get(role, {})
                values.append(escape(str(result.get('raw', '未返回')))
                              + f'（{escape(str(result.get("elapsed", "—")))}秒）')
            history.append(f'<li>第{escape(str(sample["point"]))}把：' + '；'.join(values) + '</li>')
        error = escape(str(node.get('error') or ''))
        rows.append('<tr><td colspan="7"><details><summary>采样记录与异常</summary>'
                    + (f'<p class="error">{error}</p>' if error else '')
                    + ('<ul>' + ''.join(history) + '</ul>' if history else '<p>尚无采样记录。</p>')
                    + '</details></td></tr>')
    completed = sum(groups.get(str(number), {}).get('status') == 'completed' for number in range(start, end + 1))
    daily = quote(f'OAS每日任务结果_{day}.html')
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>每日超鬼王门票刷取情况</title><style>'
        'body{margin:0;background:#f5f6f8;color:#202735;font:15px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}'
        'main{max-width:1380px;margin:32px auto;padding:0 24px}a{color:#245ba8;text-decoration:none}'
        'header{display:flex;justify-content:space-between;gap:20px;align-items:center}h1{font-size:27px}'
        '.card{background:white;border:1px solid #e0e5ed;border-radius:9px;overflow:auto;margin:20px 0}'
        'table{border-collapse:collapse;width:100%;text-align:left;min-width:980px}th,td{padding:12px 18px;border-bottom:1px solid #e8ecf2}'
        'th{background:#f7f9fc}p{color:#687486}.error{color:#b42318}summary{cursor:pointer;color:#245ba8}'
        '</style></head><body><main><header><div><p>' + escape(day) + '</p><h1>每日超鬼王门票刷取情况</h1></div>'
        f'<nav><a href="{daily}">返回每日任务日志</a>　<a href="index.html">近7天日志</a></nav></header>'
        f'<p>三端均确认50/50才完成。本机第{start}～{end}组；已完成组：{completed}/{end-start+1}。'
        f'最后更新：{escape(str(state.get("updated_at") or "尚无采集记录"))}</p>'
        f'<p>第{int(state.get("event_ocr_start", 200))}把开始，每{int(state.get("event_ocr_interval", 10))}把检查一次，'
        f'{int(state.get("battle_count", 250))}把为保护上限。未采集不代表0/50；刷新页面查看最新记录。</p>'
        '<div class="card"><table><thead><tr><th>账号组</th><th>oas3 · 队长</th><th>oas4 · 队员一</th>'
        '<th>oas5 · 队员二</th><th>已确认场数（A/B/C）</th><th>组状态</th><th>更新时间</th></tr></thead><tbody>'
        + ''.join(rows) + '</tbody></table></div></main></body></html>\n'
    )


class EventTicketReport:
    def __init__(self, sync, *, group_count=20, group_start=1, group_end=0,
                 event_ocr_start=200, event_ocr_interval=10, battle_count=250, output_dir=None):
        self.sync = sync
        self.group_count = group_count
        self.policy = dict(group_start=group_start, group_end=group_end or group_count,
                           event_ocr_start=event_ocr_start, event_ocr_interval=event_ocr_interval,
                           battle_count=battle_count)
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parents[2] / 'log/dailytask'

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
            self._write(path, render_ticket_report(state))
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
