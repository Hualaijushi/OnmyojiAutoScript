"""超鬼王门票报告的卡片布局。"""

from datetime import date
from html import escape
from urllib.parse import quote


def render_ticket_layout(state: dict, account_emails: dict | None = None) -> str:
    roles = [('leader', '队长', 'oas3', 'A'), ('member_1', '队员一', 'oas4', 'B'), ('member_2', '队员二', 'oas5', 'C')]
    statuses = {'running': '刷取中', 'sampling': '采样中', 'finishing': '正在收尾', 'completed': '门票已达标', 'failed': '已停止'}
    start, end = state.get('group_start', 1), state.get('group_end', state['group_count'])
    groups = state.get('event_groups', {})
    emails = account_emails or {}

    totals = {5: 0, 6: 0}
    collected = {5: 0, 6: 0}
    cards = []
    complete = 0
    for n in range(start, end + 1):
        node = groups.get(str(n), {})
        status = node.get('status')
        complete += status == 'completed'
        account_cards = []
        for role, label, instance, prefix in roles:
            info = node.get('roles', {}).get(role, {})
            account = f'{prefix}{n:02d}'
            email = escape(str(emails.get(account) or '邮箱未配置'))
            ticket = info.get('value')
            ticket_display = '未采集' if ticket is None else f'{ticket} / 50'
            reached = ' · 已达标' if info.get('reached') else ''
            fields = []
            for star in (5, 6):
                value = (info.get('ghost_counts') or {}).get(str(star))
                if type(value) is int and value >= 0:
                    totals[star] += value
                    collected[star] += 1
                    display = str(value)
                    marker = ''
                else:
                    display = '—'
                    marker = '<span class="missing">未采集</span>'
                fields.append(f'<div class="stat" aria-label="{label} {star}x"><span>{star} 星鬼王</span><div><strong>{display}</strong>{marker}</div></div>')
            account_cards.append(
                f'<article class="account"><div class="account-top"><span class="role">{escape(label)} · {instance}</span>'
                f'<span class="ticket-label">门票 <b>{escape(ticket_display)}</b>{reached}</span></div>'
                f'<label class="account-name"><input type="checkbox" class="ghost-account" data-account="{account}" '
                f'data-group="{n}" aria-label="{account}超鬼王已打"><span><b>{account}</b>'
                f'<small>{email}</small></span></label><div class="stats">{"".join(fields)}</div></article>'
            )
        history = []
        for sample in node.get('samples', {}).values():
            values = []
            for role, label, _, _ in roles:
                item = sample.get('reports', {}).get(role, {})
                values.append(f'{label} {escape(str(item.get("raw", "未返回")))}（{escape(str(item.get("elapsed", "—")))}秒）')
            history.append(f'<li>第 {escape(str(sample.get("point", "—")))} 场：' + ' · '.join(values) + '</li>')
        error = escape(str(node.get('error') or ''))
        error_html = f'<p class="error">{error}</p>' if error else ''
        details = '<ul>' + ''.join(history) + '</ul>' if history else '<p>尚无采样记录</p>'
        progress = state.get('battle_progress', {}).get(str(n), {})
        battle = ' / '.join(str(progress.get(role, '—')) for role, _, _, _ in roles)
        label = '人工确认完成' if node.get('completion_source') == 'user_confirmed' else statuses.get(status, '尚无记录')
        state_class = 'good' if status == 'completed' else ('failed' if status == 'failed' else 'neutral')
        group_updated = escape(str(node.get('updated_at') or '—').replace('T', ' ')[:19])
        cards.append(
            f'<section class="group"><div class="group-head"><div class="group-title">'
            f'<label class="group-name"><input type="checkbox" class="ghost-group" data-group="{n}" '
            f'aria-label="第{n:02d}组三个账号超鬼王已打"><span>第 {n:02d} 组</span></label>'
            f'<span class="status {state_class}"><i></i>{escape(label)}</span></div>'
            f'<div class="group-meta"><span>已确认场数</span><strong>{escape(battle)}</strong><span class="slash">A / B / C</span><span>更新 {group_updated}</span></div></div>'
            f'<div class="accounts">{"".join(account_cards)}</div>'
            f'<details class="details"><summary>采样记录与异常</summary>{error_html}{details}</details></section>'
        )

    count = max(0, end - start + 1) * 3
    total5 = str(totals[5]) if collected[5] else '—'
    total6 = str(totals[6]) if collected[6] else '—'
    updated = escape(str(state.get('updated_at') or '尚无采集记录').replace('T', ' ')[:19])
    day = date.fromisoformat(str(state['date'])).isoformat()
    daily_link = quote(f'OAS每日任务结果_{day}.html')
    archive_link = 'index.html'
    summary5 = str(totals[5]) if collected[5] else '未采集'
    summary6 = str(totals[6]) if collected[6] else '未采集'
    ocr_start = int(state.get('event_ocr_start', 200))
    ocr_interval = int(state.get('event_ocr_interval', 10))
    battle_limit = int(state.get('battle_count', 250))
    html = f'''<!doctype html>
    <html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>每日超鬼王门票刷取情况</title>
    <style>
    :root{{--ink:#152e2b;--muted:#728482;--green:#176e5a;--line:#e1e9e6;--cream:#f5f8f6}}
    *{{box-sizing:border-box}}body{{margin:0;background:#f2f6f4;color:var(--ink);font:14px/1.5 "Microsoft YaHei","Segoe UI",sans-serif}}
    main{{max-width:1460px;margin:auto;padding:30px 32px 52px}}.mast{{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:22px}}
    .eyebrow{{font:700 11px/1.5 "Segoe UI",sans-serif;letter-spacing:.16em;color:#579181;text-transform:uppercase}}a{{color:#32745e;text-decoration:none}}a:hover{{text-decoration:underline}}.nav{{display:flex;gap:14px;justify-content:flex-end;margin-bottom:7px}}
    h1{{font-size:27px;letter-spacing:.02em;margin:5px 0 4px}}.sub{{margin:0;color:var(--muted);font-size:13px}}.date{{color:#687d77;font-size:13px;text-align:right;white-space:nowrap}}
    .preview{{border:1px solid #d7e7e0;background:#eaf5ef;color:#477666;border-radius:10px;padding:10px 14px;margin:0 0 19px;font-size:13px}}
    .overview{{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:12px;margin-bottom:24px}}.metric{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 18px;display:flex;justify-content:space-between;align-items:end;min-height:76px}}
    .metric .caption{{font-size:12px;color:var(--muted)}}.metric strong{{font:700 27px/1 "Segoe UI",sans-serif;letter-spacing:-.03em;color:#173a34}}.metric .small{{font-size:12px;color:#8b9a95;white-space:nowrap}}
    .bar{{display:flex;align-items:end;justify-content:space-between;margin-bottom:12px;gap:12px}}.bar h2{{font-size:16px;margin:0}}.bar span{{font-size:12px;color:var(--muted)}}
    .group{{background:white;border:1px solid var(--line);border-radius:13px;margin-bottom:12px;overflow:hidden;box-shadow:0 3px 12px #133b2208}}
    .group-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 17px;border-bottom:1px solid #edf1ef}}
    .group-title{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}.group-name{{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;cursor:pointer}}
    input[type=checkbox]{{width:15px;height:15px;accent-color:#20836a;cursor:pointer;margin:0;flex:none}}
    .status{{display:inline-flex;align-items:center;gap:5px;border-radius:20px;padding:3px 8px;font-size:11px;font-weight:600}}.status i{{width:6px;height:6px;border-radius:50%;background:currentColor}}
    .good{{background:#e9f5ef;color:#25825e}}.neutral{{background:#f0f4f2;color:#6a8077}}.failed{{background:#fff2ec;color:#b4563f}}
    .group-meta{{color:#97a8a1;font-size:12px;display:flex;gap:8px;align-items:center}}.group-meta strong{{color:#405c53;font-size:13px;font-weight:600}}.slash{{font-size:10px}}
    .accounts{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}}.account{{padding:13px 17px 14px;min-width:0}}.account+.account{{border-left:1px solid #edf1ef}}
    .account-top{{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px}}.role{{font-size:11px;font-weight:700;letter-spacing:.02em;color:#7a8c86}}.ticket-label{{font-size:11px;color:#94a49e;white-space:nowrap}}.ticket-label b{{color:#3f6d5d;font-weight:650}}
    .account-name{{display:flex;align-items:flex-start;gap:8px;cursor:pointer;min-width:0}}.account-name input{{margin-top:3px}}.account-name span{{min-width:0}}.account-name b{{font-size:13px}}.account-name small{{display:block;color:#82928c;font:12px/1.45 "Segoe UI",sans-serif;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .stats{{display:flex;gap:10px;margin:11px 0 0 23px}}.stat{{flex:1;background:#f5f8f6;border-radius:8px;padding:7px 10px;min-width:0}}.stat>span{{display:block;font-size:11px;color:#879b90}}.stat strong{{font:700 17px/1.35 "Segoe UI",sans-serif;color:#1b5947}}.missing{{font-size:10px;color:#9aaba3;margin-left:5px}}
    .details{{border-top:1px solid #edf1ef;color:#7b8d86;font-size:12px}}.details summary{{padding:9px 17px;cursor:pointer;list-style:none}}.details summary:before{{content:'＋';margin-right:7px;color:#68a58e}}.details[open] summary:before{{content:'－'}}.details ul{{margin:0;padding:0 35px 14px}}.details p{{margin:0;padding:0 17px 12px}}.error{{color:#b44a3b}}
    @media(max-width:800px){{main{{padding:20px 14px 32px}}.mast{{display:block}}.date{{text-align:left;margin-top:10px}}.preview{{overflow-wrap:anywhere}}.overview{{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}.metric{{min-width:0;gap:5px}}.metric .small{{white-space:normal;text-align:right}}.metric:first-child{{grid-column:1/-1}}.accounts{{grid-template-columns:1fr}}.account+.account{{border-left:0;border-top:1px solid #edf1ef}}.group-head{{display:block}}.group-meta{{flex-wrap:wrap;justify-content:flex-start;margin-top:8px}}.bar{{flex-wrap:wrap}}}}
    </style></head><body><main>
    <div class="mast"><div><div class="eyebrow">OAS · EVENT RECORD</div><h1>超鬼王门票情况</h1><p class="sub">每组门票进度、鬼王数量及采样记录</p></div><div class="date"><nav class="nav"><a href="{daily_link}">每日任务日志</a><a href="{archive_link}">近 7 天记录</a></nav>{day}<br>更新于 {updated}</div></div>
    <p class="sub" style="margin:-8px 0 18px">本机第{start}～{end}组；三端均确认50/50才完成。第{ocr_start}把开始，每{ocr_interval}把检查一次，{battle_limit}把为保护上限。</p>
    <div class="overview"><div class="metric"><div><div class="caption">账号组进度</div><strong>{complete} <span style="font-size:16px;color:#a2b4ab">/ {end-start+1}</span></strong></div><div class="small">第 {start}–{end} 组</div></div>
    <div class="metric"><div><div class="caption">五星鬼王 · 已采集合计</div><strong>{total5}</strong></div><div class="small">{collected[5]} / {count} 个账号</div></div>
    <div class="metric"><div><div class="caption">六星鬼王 · 已采集合计</div><strong>{total6}</strong></div><div class="small">{collected[6]} / {count} 个账号</div></div></div>
    <div class="bar"><h2>账号明细</h2><span id="ghost-save-status">勾选表示该账号超鬼王已打</span></div>
    {''.join(cards)}
    <p class="sub" style="margin:22px 0 8px;font-weight:600">数量合计：5x：{summary5}（{collected[5]}/{count} 账号已采集）；6x：{summary6}（{collected[6]}/{count} 账号已采集）</p>
    <p class="sub">未采集不代表数量为 0。可单独勾选账号，勾选组号会同时选择或取消该组三个账号。</p>
    </main><script>
    const key='oas-ghost-done-{day}';const accounts=[...document.querySelectorAll('.ghost-account')], groups=[...document.querySelectorAll('.ghost-group')];
    let saved={{}};try{{const data=JSON.parse(localStorage.getItem(key)||'{{}}');if(data&&typeof data==='object'&&!Array.isArray(data))saved=data}}catch(e){{saved={{}}}}
    accounts.forEach(a=>a.checked=saved[a.dataset.account]===true);
    function update(){{groups.forEach(g=>{{let a=accounts.filter(x=>x.dataset.group===g.dataset.group),n=a.filter(x=>x.checked).length;g.checked=n===a.length;g.indeterminate=n>0&&n<a.length;}})}}
    function save(){{accounts.forEach(a=>{{if(a.checked)saved[a.dataset.account]=true;else delete saved[a.dataset.account]}});try{{localStorage.setItem(key,JSON.stringify(saved));document.getElementById('ghost-save-status').textContent='勾选已保存在当前浏览器'}}catch(e){{document.getElementById('ghost-save-status').textContent='浏览器无法保存勾选'}}update()}}
    accounts.forEach(a=>a.addEventListener('change',save));groups.forEach(g=>g.addEventListener('change',()=>{{accounts.filter(a=>a.dataset.group===g.dataset.group).forEach(a=>a.checked=g.checked);save()}}));update();
    </script></body></html>'''
    return html
