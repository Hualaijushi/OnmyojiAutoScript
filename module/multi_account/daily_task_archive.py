"""维护近七天的日报入口，并清理到期的已知格式日志。"""

from __future__ import annotations

import os
import re
import threading
from datetime import date, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote

from module.logger import logger
from module.multi_account.file_lock import atomic_replace_with_retry


RETENTION_DAYS = 7
_REPORT_NAME = re.compile(r"(?:OAS每日任务结果|OAS超鬼王门票刷取情况)_(\d{4}-\d{2}-\d{2})\.(html|md|txt)", re.IGNORECASE)


def report_date(path: Path) -> date | None:
    """仅识别本功能生成的日期日志，排除无关文件。"""
    match = _REPORT_NAME.fullmatch(path.name)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def refresh_report_archive(output_dir: Path, today: date) -> list[Path]:
    """调用方持有报告锁；先更新入口，再逐个删除七天前的日志。"""
    root = output_dir.resolve()
    cutoff = today - timedelta(days=RETENTION_DAYS - 1)
    candidates = []
    reports = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            continue
        day = report_date(path)
        if day is None:
            continue
        if day < cutoff:
            candidates.append(path)
        elif day <= today and path.suffix.lower() == ".html":
            reports.append((day, path.name))
    reports.sort(reverse=True)
    index_path = root / "index.html"
    temp = index_path.with_name(f"{index_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(_render_index(
                [item for item in reports if item[1].startswith('OAS每日任务结果_')], today, cutoff,
                [item for item in reports if item[1].startswith('OAS超鬼王门票刷取情况_')],
            ))
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace_with_retry(temp, index_path)
    finally:
        temp.unlink(missing_ok=True)
    removed = []
    for path in candidates:
        # 不递归清理，不跟随链接；删除前再次确认目标仍在指定日志目录中。
        if path.is_symlink() or path.resolve().parent != root:
            continue
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("过期每日任务日志清理失败：%s；%s", path, exc)
    return removed


def _render_index(reports: list[tuple[date, str]], today: date, cutoff: date,
                  ticket_reports: list[tuple[date, str]] | None = None) -> str:
    rows = []
    for day, filename in reports:
        label = "今天" if day == today else "历史报告"
        rows.append(
            f'<tr><td>{day.isoformat()}</td><td>{label}</td>'
            f'<td><a href="{escape(quote(filename), quote=True)}">打开报告</a></td></tr>'
        )
    latest = (
        f'<a id="latest" class="primary" href="{escape(quote(reports[0][1]), quote=True)}">'
        f'打开最新报告（{reports[0][0].isoformat()}）</a>'
        if reports else '<p class="empty">暂无报告</p>'
    )
    tickets = '<h2>超鬼王门票情况</h2>'
    if ticket_reports:
        tickets += ''.join(f'<p><a href="{escape(quote(name), quote=True)}">每日超鬼王门票刷取情况 · {day.isoformat()}</a></p>'
                           for day, name in ticket_reports)
    else:
        tickets += '<p>尚无门票记录</p>'
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>每日任务日志</title>'
        '<style>body{margin:0;background:#f5f6f8;color:#202735;font:16px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}'
        'main{max-width:820px;margin:48px auto;padding:0 24px}h1{margin-bottom:8px}p{color:#687486}'
        'a{color:#245ba8;text-decoration:none}.primary{display:inline-block;background:#2865bd;color:white;padding:12px 20px;border-radius:7px;margin:10px 0 28px}'
        'table{width:100%;border-collapse:collapse;background:white;border:1px solid #e0e5ed}'
        'th,td{text-align:left;padding:14px 20px;border-bottom:1px solid #e8ecf2}th{background:#f7f9fc;font-size:14px}</style>'
        '</head><body><main><h1>每日任务日志</h1>'
        f'<p>最近 {RETENTION_DAYS} 天：{cutoff.isoformat()} 至 {today.isoformat()}</p>'
        + latest
        + '<table><thead><tr><th>日期</th><th>说明</th><th>查看</th></tr></thead><tbody>'
        + "".join(rows) + '</tbody></table>' + tickets + '</main><script>'
        "if(new URLSearchParams(location.search).get('open')==='latest'){"
        "const link=document.getElementById('latest');if(link)location.replace(link.href);}"
        '</script></body></html>\n'
    )
