# This Python file uses the following encoding: utf-8

"""上游自定义阵容（73d4ae84 的 ``custom_lineups`` / ``lineup_loader``）接入本地运行时的兼容层。

本地七套 Python 阵容仍是内置阵容的唯一来源，这里不改它们，也不改上游数据模型，只做三件事：

- 站位编号：棋局运行时（上游 Frame 的 13-24 号落点、`BOARD_RECALL_POSITIONS`、前排 1-6 判断）和编辑器统一使用
  「前排 1-6、后排 7-12」，这就是运行时内部编号；本地七套内置阵容写的是「奇数前排、偶数后排」，列号都是从左到右
  1-6，两边落在同一组物理格子上。内置阵容在选定阵容时一次性换成运行时编号（`to_runtime_numbering`），
  自定义阵容本来就是运行时编号，不换算。
- 本地运行时做不到的上游字段明确拒绝，不静默忽略：本地符咒识别不认识的纹章（符咒评分已随上游吸收，
  指定次要羁绊 `secondary_bond` 现在由 `grigri.lineup_bond_context` 支持，不再拒绝）。
- 本地内置阵容里能被上游格式无损表达的，转成只读模板给编辑器「另存为」；表达不了的不出现在编辑器里。
"""

from copy import deepcopy

from tasks.Chess.strategy.custom_lineups import BONDS, EMBLEMS, CustomLineup, _legacy_document, read_lineups
from tasks.Chess.strategy.grigri import grigri_bond_name, grigri_category
from tasks.Chess.strategy.lineup_loader import strategy_from_document

CUSTOM_PREFIX = 'custom:'
BUILTIN_PREFIX = 'builtin:'

# 本地纹章识别（符咒图鉴）认不出的纹章：编辑器不提供，自定义阵容里出现就拒绝
UNSUPPORTED_EMBLEMS = frozenset(
    key for key, entry in EMBLEMS.items()
    if grigri_category(entry['name']) != 'emblem' or grigri_bond_name(entry['name']) is None
)


def runtime_to_local_position(position) -> int:
    """运行时 / 编辑器站位号 → 本地内置阵容的站位号。"""
    position = int(position)
    if not 1 <= position <= 12:
        raise ValueError(f'站位号必须在 1-12 之间：{position}')
    return position * 2 - 1 if position <= 6 else (position - 6) * 2


def local_to_runtime_position(position) -> int:
    """本地内置阵容的站位号 → 运行时 / 编辑器站位号。"""
    position = int(position)
    if not 1 <= position <= 12:
        raise ValueError(f'站位号必须在 1-12 之间：{position}')
    column = (position + 1) // 2
    return column if position % 2 == 1 else column + 6


def unsupported_reasons(document: CustomLineup) -> list[str]:
    reasons = []
    for index, slot in enumerate(document.slots, 1):
        for item in slot.equipment:
            if item.kind == 'emblem' and item.key in UNSUPPORTED_EMBLEMS:
                reasons.append(f'{index} 号位的「{EMBLEMS[item.key]["name"]}」本地符咒识别不认识，运行时无法装备')
    return reasons


def check_runtime_support(document: CustomLineup) -> None:
    reasons = unsupported_reasons(document)
    if reasons:
        raise ValueError(f'自定义阵容 {document.key} 含本地运行时不支持的设置：' + '；'.join(reasons))


def to_runtime_numbering(strategy: dict) -> dict:
    """本地内置阵容策略（本地站位号）→ 运行时站位号的深拷贝；位置之外的字段原样，不改注册表里的原对象。

    换算是一一对应：同一位置放两名式神（流火 7 号位）换算后仍在同一位置，不会去重。
    """
    result = deepcopy(strategy)
    for unit in result['shikigami'].values():
        unit['position'] = local_to_runtime_position(unit['position'])
    for field in ('hakuzosu_protect_position', 'arakawa_goldfish_position'):
        if result.get(field) is not None:
            result[field] = local_to_runtime_position(result[field])
    return result


def load_custom_strategy(key: str) -> dict:
    """运行时读取自定义阵容：不存在、文件损坏、校验失败或含本地不支持的设置都抛错，不回落到任何内置阵容。

    读取与模型校验同上游 ``custom_lineups.load_strategy``；只读一次文件，校验和加载用同一份内容。
    自定义阵容本来就是运行时站位号，不做换算。
    """
    raw = read_lineups().get(key)
    if raw is None:
        raise ValueError(f'自定义阵容不存在：{key}；请先在 chesslineup 中保存')
    document = CustomLineup.model_validate(raw)
    check_runtime_support(document)
    return document.strategy()


def _builtin_config(key: str, strategy: dict) -> dict:
    """本地内置策略 → 上游 ``_legacy_document`` 接受的配置（站位换成运行时 / 编辑器编号）。"""
    def upstream(position):
        return None if position is None else local_to_runtime_position(position)

    return {
        'key': key,
        'display_name': strategy['display_name'],
        # 本地符咒评分把阵容中文名当主要羁绊；转成上游格式时显式写出，保持同一语义
        'primary_bond': strategy['display_name'] if strategy['display_name'] in BONDS else '',
        'hakuzosu_protect_position': upstream(strategy.get('hakuzosu_protect_position')),
        'arakawa_goldfish_position': upstream(strategy.get('arakawa_goldfish_position')),
        'shikigami_positions': {
            name: (unit['deploy_weight'], local_to_runtime_position(unit['position']), tuple(unit['preferred_souls']))
            for name, unit in strategy['shikigami'].items()
        },
    }


def _units(strategy: dict) -> dict:
    # 上游给每名式神都写 preferred_emblems（空就是 ()），本地内置不写；运行时一律 .get(..., ())，二者等价
    return {name: {field: value for field, value in unit.items() if not (field == 'preferred_emblems' and not value)}
            for name, unit in strategy['shikigami'].items()}


def builtin_document(key: str, strategy: dict) -> dict | None:
    """内置阵容的只读编辑器模板；往返（本地 → 上游格式 → 运行时）后与原策略的运行时形态不完全一致就返回 None。"""
    try:
        document = CustomLineup.model_validate(_legacy_document(_builtin_config(key, strategy)))
    except (KeyError, ValueError):
        return None
    if unsupported_reasons(document):
        return None
    back = strategy_from_document(document)
    expected = to_runtime_numbering(strategy)
    same = (
        _units(back) == _units(expected)
        and back['hakuzosu_protect_position'] == expected.get('hakuzosu_protect_position')
        and back['arakawa_goldfish_position'] == expected.get('arakawa_goldfish_position')
        and back['primary_bond'] == strategy['display_name']
    )
    return document.model_dump() if same else None


def builtin_documents(registry: dict) -> dict:
    """能无损表达的内置阵容模板 {key: 文档}，按注册顺序。"""
    result = {}
    for key, entry in registry.items():
        document = builtin_document(key, entry['strategy'])
        if document is not None:
            result[key] = document
    return result
