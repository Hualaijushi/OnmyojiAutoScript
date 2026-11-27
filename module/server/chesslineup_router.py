"""Local Chess lineup editor, hosted alongside annotator."""
# 上游 73d4ae84 的阵容编辑器路由。本地适配（其余与上游一致）：
# - 内置阵容 = 本地七套 Python 阵容，只读：只列出能被上游格式无损表达的几套作模板，不能保存 / 转为内置 / 删除 / 应用；
# - 本地符咒识别不认识的纹章不提供；含本地运行时不支持设置的自定义阵容不能保存、不能应用；
# - 删除前的引用检查、应用写入都按本地配置语义（海国是内置海国，不是 custom:haiguo）；
# - 应用后在下次启动百鬼棋局任务时生效（本地在任务开始时选定阵容并建立快照）。
import re
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tasks.Chess.strategy.custom_lineups import (
    BONDS, EMBLEMS, ROOT, CustomLineup, read_lineups, save_lineup,
    delete_lineup,
)
from tasks.Chess.strategy.lineup import CUSTOM_LINEUP_VALUE, LINEUP_REGISTRY, LineupBond
from tasks.Chess.strategy.lineup_compat import UNSUPPORTED_EMBLEMS, builtin_documents, unsupported_reasons
from tasks.Chess.strategy.shikigami_catalog import SHIKIGAMI_ENTRIES
from tasks.Chess.strategy.soul_catalog import SOUL_ENTRIES

chesslineup_app = APIRouter(prefix='/tool/chesslineup', tags=['chesslineup'])
WEB = Path(__file__).resolve().parent / 'web/chesslineup'
BUILTIN_READ_ONLY = '内置阵容只读：请点「另存为」保存为自定义阵容后再修改或应用'


def _require_runtime_support(document: CustomLineup):
    reasons = unsupported_reasons(document)
    if reasons:
        raise HTTPException(400, '本地运行时不支持：' + '；'.join(reasons))


@chesslineup_app.get('')
async def editor():
    return FileResponse(WEB / 'index.html')


@chesslineup_app.get('/api/catalog')
async def catalog():
    def image(kind, key):
        return f'/tool/chesslineup/static/cards/{kind}_{key}.webp'
    return {
        'shikigami': [{'key': e.romaji, 'name': e.chinese_name, 'cost': e.cost,
                       'bonds': list(e.bonds), 'image': image('shikigami', e.romaji)} for e in SHIKIGAMI_ENTRIES],
        'soul': [{'key': e.romaji, 'name': e.chinese_name, 'category': e.category,
                  'image': image('soul', e.romaji)} for e in SOUL_ENTRIES],
        'emblem': [{'key': key, 'name': e['name'], 'image': image('emblem', key)} for key, e in EMBLEMS.items()
                   if key not in UNSUPPORTED_EMBLEMS],
        'bonds': BONDS,
        'configs': sorted(p.stem for p in (ROOT / 'config').glob('*.json') if p.stem != 'template'),
    }


@chesslineup_app.get('/api/lineups')
async def lineups():
    return {'builtin': list(builtin_documents(LINEUP_REGISTRY).values()),
            'custom': list(read_lineups().values())}


@chesslineup_app.post('/api/lineups')
async def save(data: CustomLineup, source: Literal['builtin', 'custom'] = 'custom'):
    if source == 'builtin':
        raise HTTPException(403, BUILTIN_READ_ONLY)
    _require_runtime_support(data)
    return save_lineup(data)


@chesslineup_app.post('/api/lineups/promote')
async def promote(data: CustomLineup):
    raise HTTPException(403, '本地内置阵容由代码维护，不支持把自定义阵容转为内置；自定义阵容可以直接应用')


def _custom_reference(path: Path):
    """该实例配置当前选的自定义阵容 ``custom:<标识>``；选的是内置阵容或没有棋局配置返回 None。"""
    try:
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise HTTPException(409, f'无法读取脚本配置 {path.stem}，不能确认阵容是否仍在使用')
    selected = raw.get('chess', {}).get('chess_config', {})
    if selected.get('lineup_bond') != CUSTOM_LINEUP_VALUE:
        return None
    active_key = selected.get('custom_lineup', '')
    return active_key if active_key.startswith(('builtin:', 'custom:')) else 'custom:' + active_key


@chesslineup_app.delete('/api/lineups/{source}/{key}')
async def remove(source: Literal['builtin', 'custom'], key: str):
    if source == 'builtin':
        raise HTTPException(403, '内置阵容由代码维护，不能删除')
    references = [path.stem for path in (ROOT / 'config').glob('*.json')
                  if path.stem != 'template' and _custom_reference(path) == f'custom:{key}']
    if references:
        raise HTTPException(409, '阵容仍被以下脚本使用，请先切换：' + '、'.join(references))
    try:
        delete_lineup(key)
    except KeyError:
        raise HTTPException(404, '阵容不存在')
    return {'message': '阵容已删除'}


class ApplyBody(BaseModel):
    key: str
    script: str
    source: Literal['builtin', 'custom'] = 'custom'


@chesslineup_app.post('/api/apply')
async def apply(data: ApplyBody):
    if data.source == 'builtin':
        raise HTTPException(400, '内置阵容请直接在 OASX 的「选择阵容羁绊」中选择')
    documents = read_lineups()
    if data.key not in documents:
        raise HTTPException(404, '请先保存阵容')
    _require_runtime_support(CustomLineup.model_validate(documents[data.key]))
    if not re.fullmatch(r'[\w -]{1,80}', data.script) or data.script == 'template':
        raise HTTPException(400, '脚本配置名无效')
    if not (ROOT / 'config' / f'{data.script}.json').is_file():
        raise HTTPException(404, '脚本配置不存在')
    from module.server.main_manager import mm
    config = mm.config_cache(data.script)
    config.model.chess.chess_config.custom_lineup = f'custom:{data.key}'
    config.model.chess.chess_config.lineup_bond = LineupBond.CUSTOM
    config.model.save()
    return {'message': f'已应用至 {data.script}：下次启动百鬼棋局任务时使用（正在运行的任务继续使用启动时的阵容）'}
