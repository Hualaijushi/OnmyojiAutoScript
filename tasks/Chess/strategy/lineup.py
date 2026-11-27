# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容羁绊注册表。

新增体系时：
1. 以羁绊拼音创建独立策略 Python 文件；
2. 在 ``LINEUP_REGISTRY`` 注册拼音键、中文显示名和策略对象。

OASX 下拉选项和主任务运行时选择均由本注册表生成。
"""

from enum import Enum

from tasks.Chess.strategy.lineup_strategy import (
    ARAKAWA,
    DAJIANGSHAN,
    HAIGUO,
    HUYAO,
    MINGFU,
    QIJIAOSHAN,
    LIUHUO,
)


LINEUP_REGISTRY = {
    'qijiaoshan': {
        'display_name': '七角山',
        'strategy': QIJIAOSHAN,
    },
    'haiguo': {
        'display_name': '海国',
        'strategy': HAIGUO,
    },
    'dajiangshan': {
        'display_name': '大江山',
        'strategy': DAJIANGSHAN,
    },
    'huyao': {
        'display_name': '狐妖',
        'strategy': HUYAO,
    },
    'mingfu': {
        'display_name': '冥府',
        'strategy': MINGFU,
    },
    'liuhuo': {
        'display_name': '流火',
        'strategy': LIUHUO,
    },
    'arakawa': {
        'display_name': '荒川',
        'strategy': ARAKAWA,
    },
}

DEFAULT_LINEUP_KEY = 'arakawa'

# 选它时由 ChessConfig.custom_lineup 指定 ``custom:<标识>``（阵容编辑器保存的自定义阵容）
CUSTOM_LINEUP_VALUE = '自定义阵容'

# 枚举值使用中文，使 OASX 下拉框直接显示中文；运行时通过下面的解析
# 函数还原成稳定的拼音键。
LineupBond = Enum(
    'LineupBond',
    {
        key.upper(): entry['display_name']
        for key, entry in LINEUP_REGISTRY.items()
    } | {'CUSTOM': CUSTOM_LINEUP_VALUE},
    type=str,
)


def resolve_lineup_key(value) -> str:
    """将拼音键、中文显示名或 OASX 枚举值统一解析为拼音键。"""
    raw = getattr(value, 'value', value)
    raw = str(raw or '').strip()
    if raw in LINEUP_REGISTRY:
        return raw
    for key, entry in LINEUP_REGISTRY.items():
        if raw == entry['display_name']:
            return key
    return DEFAULT_LINEUP_KEY


def oasx_lineup_choices() -> dict[str, str]:
    """Build fresh display labels with stable source/key identities for OASX."""
    # 上游 73d4ae84 原函数；本地适配：内置阵容取本地 Python 注册表（上游取内置 JSON），
    # 自定义阵容文件读不出时只列内置并记警告，不让整个配置页报错
    from module.logger import logger
    from tasks.Chess.strategy.custom_lineups import read_lineups
    try:
        custom = read_lineups()
    except Exception as exc:
        logger.warning(f'Chess custom lineups unreadable, list builtin lineups only: {exc}')
        custom = {}
    choices = {}
    for source, label, records in (
        ('builtin', '内置', LINEUP_REGISTRY),
        ('custom', '自定义', custom),
    ):
        for key, record in records.items():
            choices[f'{label} · {record["display_name"]} [{key}]'] = f'{source}:{key}'
    return choices
