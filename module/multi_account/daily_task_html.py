"""将内存中的每日表格转换为本地可勾选 HTML。"""

from __future__ import annotations

import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from module.multi_account.daily_task_images import CooperationGallery
from module.multi_account.event_ticket_report import ticket_entry


_PERIODS = {"早间协作统计": "cooperation_morning", "晚间协作统计": "cooperation_evening"}


def read_html_checks(path: Path) -> set[tuple[str, ...]]:
    """保留尚未在浏览器打开过的迁移勾选初值。"""
    class CheckParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.checks: set[tuple[str, ...]] = set()

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag != "input" or values.get("type") != "checkbox" or "checked" not in values:
                return
            try:
                key = json.loads(values.get("data-key", ""))
            except (TypeError, json.JSONDecodeError):
                return
            if isinstance(key, list) and len(key) == 5 and all(isinstance(item, str) for item in key):
                if key[0] in _PERIODS.values():
                    self.checks.add(tuple(key))

    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return set()
    parser = CheckParser()
    parser.feed(content)
    return parser.checks


def render_interactive_report(
    markdown: str, *, title: str, report_date: str, checked_keys: set[tuple[str, ...]],
    row_galleries: dict[tuple[str, int], CooperationGallery] | None = None,
) -> str:
    """生成真实复选框；人工进度保存在浏览器，不改变自动任务状态。"""
    sections = []
    current_title = "每日任务汇总"
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            current_title = line[3:].strip()
        if not line.startswith("|"):
            index += 1
            continue
        table_lines = []
        while index < len(lines) and lines[index].startswith("|"):
            table_lines.append(lines[index])
            index += 1
        cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in table_lines]
        headers, rows = cells[0], cells[2:]
        period = _PERIODS.get(current_title)
        body = []
        if period:
            headers = ["完成", *headers, "协作详情"]
        for row_index, row in enumerate(rows):
            values = [escape(value) for value in row]
            if period:
                checkbox = "-"
                if len(row) == 4 and row[0] != "无":
                    key = (period, row[0], row[1].lower(), row[2], row[3])
                    encoded = escape(json.dumps(key, ensure_ascii=False), quote=True)
                    label = escape(f"标记完成：{row[0]}，{row[3]}", quote=True)
                    checked = " checked" if key in checked_keys else ""
                    checkbox = f'<input type="checkbox" data-key="{encoded}" aria-label="{label}"{checked}>'
                values.insert(0, checkbox)
                gallery = (row_galleries or {}).get((period, row_index))
                pictures = []
                if gallery:
                    encoded_key = escape(json.dumps(gallery.key, ensure_ascii=False), quote=True)
                    for picture in gallery.images:
                        if not picture.valid():
                            continue
                        label = escape(picture.label, quote=True)
                        pictures.append(
                            '<figure><img class="cooperation-image" '
                            f'src="{escape(picture.data_uri, quote=True)}" alt="{label}" '
                            f'data-image-key="{encoded_key}" data-slot="{picture.slot}" '
                            f'width="300" height="510" tabindex="0" '
                            f'aria-label="{label}，悬停或聚焦查看大图"><figcaption>{label}</figcaption></figure>'
                        )
                values.append(
                    '<div class="cooperation-images">' + ''.join(pictures) + '</div>' if pictures
                    else ('<span class="no-image">暂无截图</span>' if checkbox != "-" else "-")
                )
            body.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
        table = (
            '<div class="table-wrap"><table><thead><tr>'
            + "".join(f"<th>{escape(value)}</th>" for value in headers)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
        )
        if period:
            sections.append(
                '<section class="card cooperation"><div class="section-heading">'
                f'<h2>{escape(current_title)}</h2><span class="period-count"></span></div>{table}</section>'
            )
        else:
            sections.append(f'<details class="card summary"><summary>每日任务汇总</summary>{table}</details>')
    sections.sort(key=lambda section: section.startswith("<details"))
    return (
        '<!doctype html>\n<html lang="zh-CN" data-report-date="' + escape(report_date, quote=True) + '">\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>' + escape(title) + '</title><style>' + _STYLE + '</style></head><body>'
        '<main><header><div><p class="date">' + escape(report_date) + '</p><h1>每日协作记录</h1>'
        '<p class="hint">点击方框标记完成，进度自动保存在当前浏览器。截图悬停查看大图。更换浏览器前可保存勾选副本。</p></div>'
        '<div class="header-actions"><a href="index.html">近7天日志</a>'
        '<button id="download" type="button">保存勾选副本</button></div></header>'
        '<div class="progress-bar"><strong id="progress"></strong><span id="save-status" role="status"></span></div>'
        + "".join(sections)
        + ticket_entry(report_date) + '</main><script>' + _SCRIPT + '</script></body></html>\n'
    )


_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#202735;font:15px/1.55 "Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:36px auto;padding:0 24px 40px}header{display:flex;justify-content:space-between;gap:24px;align-items:center}
h1{font-size:28px;margin:0 0 10px}h2{font-size:19px;margin:0}.date{color:#687486;font-size:14px;margin:0 0 4px}.hint{color:#687486;margin:0}
button{border:1px solid #ced6e2;border-radius:7px;padding:10px 17px;background:white;color:#344054;cursor:pointer;white-space:nowrap}
button:hover{background:#edf3fd}.progress-bar{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:25px 0 18px;color:#526175}
.header-actions{display:flex;align-items:center;gap:18px;white-space:nowrap}.header-actions a{color:#245ba8;text-decoration:none}
#progress{font-size:17px;color:#1d4e9b}#save-status{font-size:13px}.card{background:white;border:1px solid #e0e5ed;border-radius:10px;margin-bottom:20px;overflow:hidden}
.section-heading{display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e0e5ed}.period-count{color:#687486;font-size:14px}
.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left}th{background:#f7f9fc;color:#526175;font-size:13px;font-weight:600}
th,td{padding:13px 20px;border-bottom:1px solid #e8ecf2;white-space:nowrap}tbody tr:last-child td{border-bottom:0}.cooperation th:first-child,.cooperation td:first-child{width:76px;text-align:center}
.cooperation tbody tr:hover{background:#fafcff}.cooperation tbody tr.done{background:#eff8f2}
.cooperation td{vertical-align:middle}.cooperation th:last-child{width:256px}
.cooperation-images{display:flex;gap:8px}.cooperation-images figure{margin:0;width:64px;flex-shrink:0}
.cooperation-image{display:block;width:64px;height:110px;object-fit:contain;border:1px solid #e0e5ed;border-radius:5px;cursor:zoom-in;background:#f7f9fc}
.cooperation-image:focus-visible{outline:2px solid #2b6ac9;outline-offset:3px}
.cooperation-images figcaption{font-size:12px;color:#687486;margin-top:4px}.no-image{font-size:13px;color:#8792a2}
#image-preview{position:fixed;z-index:1000;padding:8px;border:1px solid #d7dfe9;border-radius:9px;background:white;box-shadow:0 10px 36px #1c2b4540;pointer-events:none}
#image-preview img{display:block;width:auto;height:auto;max-width:calc(100vw - 50px);max-height:calc(100vh - 50px);border-radius:4px}
input[type=checkbox]{appearance:auto;width:21px;height:21px;margin:0;vertical-align:middle;cursor:pointer;accent-color:#2b6ac9}
summary{padding:18px 22px;font-weight:600;cursor:pointer}.summary .table-wrap{max-height:460px}.summary td,.summary th{padding:10px 14px;font-size:13px}
@media(max-width:680px){main{margin:20px auto;padding:0 12px}header{align-items:flex-start;flex-direction:column;gap:14px}h1{font-size:24px}.progress-bar{align-items:flex-start;flex-direction:column;gap:6px}th,td{padding:12px 14px}}
"""


_SCRIPT = """
(() => {
  const inputs = Array.from(document.querySelectorAll('input[data-key]'));
  const storageKey = 'oas-daily-cooperation:' + document.documentElement.dataset.reportDate;
  const status = document.getElementById('save-status');
  let saved = {}, storageAvailable = true;
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || '{}');
    if (value && typeof value === 'object' && !Array.isArray(value)) saved = value;
  } catch (_) { storageAvailable = false; }
  inputs.forEach(input => {
    if (Object.prototype.hasOwnProperty.call(saved, input.dataset.key)) input.checked = saved[input.dataset.key] === true;
  });
  function render() {
    const done = inputs.filter(input => input.checked).length;
    document.getElementById('progress').textContent = `已完成 ${done} / ${inputs.length}`;
    document.querySelectorAll('.cooperation').forEach(section => {
      const rows = Array.from(section.querySelectorAll('input[data-key]'));
      section.querySelector('.period-count').textContent = `${rows.filter(input => input.checked).length} / ${rows.length} 已完成`;
    });
    inputs.forEach(input => input.closest('tr').classList.toggle('done', input.checked));
    status.textContent = storageAvailable ? '勾选进度已保存在当前浏览器' : '浏览器保存不可用，请点击“保存勾选副本”';
  }
  inputs.forEach(input => input.addEventListener('change', () => {
    saved[input.dataset.key] = input.checked;
    try { localStorage.setItem(storageKey, JSON.stringify(saved)); storageAvailable = true; }
    catch (_) { storageAvailable = false; }
    render();
  }));
  const preview = document.createElement('div');
  preview.id = 'image-preview'; preview.hidden = true; preview.setAttribute('role', 'tooltip');
  const previewImage = document.createElement('img');
  previewImage.width = 300; previewImage.height = 510; preview.appendChild(previewImage);
  document.body.appendChild(preview);
  let activeThumbnail = null;
  function positionPreview() {
    if (!activeThumbnail || preview.hidden) return;
    const anchor = activeThumbnail.getBoundingClientRect(), box = preview.getBoundingClientRect();
    const margin = 16, gap = 12;
    let left = anchor.right + gap;
    if (left + box.width > innerWidth - margin) left = anchor.left - gap - box.width;
    const top = anchor.top - (box.height - anchor.height) / 2;
    preview.style.left = Math.max(margin, Math.min(left, innerWidth - margin - box.width)) + 'px';
    preview.style.top = Math.max(margin, Math.min(top, innerHeight - margin - box.height)) + 'px';
  }
  function hidePreview() { preview.hidden = true; activeThumbnail = null; }
  function showPreview(thumbnail) {
    activeThumbnail = thumbnail;
    previewImage.src = thumbnail.currentSrc || thumbnail.src;
    previewImage.alt = thumbnail.alt;
    preview.hidden = false;
    positionPreview();
  }
  previewImage.addEventListener('load', positionPreview);
  document.querySelectorAll('.cooperation-image').forEach(thumbnail => {
    thumbnail.addEventListener('mouseenter', () => showPreview(thumbnail));
    thumbnail.addEventListener('mouseleave', hidePreview);
    thumbnail.addEventListener('focus', () => showPreview(thumbnail));
    thumbnail.addEventListener('blur', hidePreview);
  });
  window.addEventListener('scroll', hidePreview, true);
  window.addEventListener('resize', hidePreview);
  window.addEventListener('blur', hidePreview);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hidePreview(); });
  document.getElementById('download').addEventListener('click', () => {
    const copy = document.documentElement.cloneNode(true);
    copy.querySelector('#image-preview').remove();
    copy.querySelectorAll('input[data-key]').forEach((input, index) => input.toggleAttribute('checked', inputs[index].checked));
    const blob = new Blob(['<!doctype html>\\n' + copy.outerHTML], {type: 'text/html;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = document.title + '_已勾选.html'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  render();
})();
"""
