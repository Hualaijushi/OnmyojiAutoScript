# This Python file uses the following encoding: utf-8
"""式神活动配置页的可选展示信息（GET /{script}/{task}/args/layout）。

只描述「哪个已有参数属于哪个玩法」，所有引用都是 /args 里原样的 (group, argument)，
前端按原路径 PUT 保存。这里只读配置、不写配置，也不参与任务执行。
"""

from tasks.ActivityShikigami.config import (
    ACTIVITY_NAME_ALIASES,
    ACTIVITY_NAME_TO_FIELD,
    ActivityShikigami,
    GeneralConfig,
)

LAYOUT_VERSION = 1
SEQUENCE_SEPARATOR = ','

# 玩法 → 其下的战斗类型；爬塔子分组顺序与 climb_sequence_v 的执行顺序一致
PLAY_BATTLES = {
    'rich_man': ('rich_man',),
    'climb': ('ap', 'pass', 'boss', 'ap100'),
    'fakegod': ('fakegod',),
}
# 只属于某个玩法、又不按战斗类型区分的参数
PLAY_EXTRA_ARGUMENTS = {
    'rich_man': (),
    'climb': ('use_penta_pass',),
    'fakegod': (),
}
COMMON_ARGUMENTS = ('limit_time', 'active_souls_clean', 'random_sleep')
ADVANCED_GROUPS = ('scheduler', 'fire_reaction')


def split_task_sequence(raw: str) -> tuple[list[str], list[str]]:
    """按 task_sequence_v 的别名与去重规则拆出玩法，但不按次数过滤、遇到未知项不抛异常。"""
    names, invalid = [], []
    for raw_name in raw.split(SEQUENCE_SEPARATOR):
        name = ACTIVITY_NAME_ALIASES.get(raw_name.strip().lower())
        if name is None:
            invalid.append(raw_name.strip())
        elif name not in names:
            names.append(name)
    return names, invalid


def _ref(group: str, argument: str) -> dict:
    return {'group': group, 'argument': argument}


def _limit_argument(battle: str) -> str:
    return 'throw_limit' if battle == 'rich_man' else f'{battle}_limit'


def _range_info(battle: str) -> dict:
    """只有体力有次数区间。min 与 limit 是同一个参数（ap_limit），新前端数 min 时不要再数 limit；
    max 不在 limit / soul / extra 里，是新增引用，旧前端忽略后它落入「其他设置」。"""
    if battle != 'ap':
        return {}
    return {
        'range': {
            'min': _ref('general_config', 'ap_limit'),
            'max': _ref('general_config', 'ap_limit_max'),
            'min_title': 'activity_ap_range_min',
            'max_title': 'activity_ap_range_max',
        },
    }


def _soul_arguments(battle: str) -> list[dict]:
    return [
        _ref('switch_soul_config', argument)
        for argument in (
            f'enable_switch_{battle}',
            f'{battle}_group_team',
            f'enable_switch_{battle}_by_name',
            f'{battle}_group_team_name',
        )
    ]


def build_args_layout(conf: ActivityShikigami) -> dict:
    general: GeneralConfig = conf.general_config
    selected, invalid = split_task_sequence(general.task_sequence)
    name_by_field = {field: name for name, field in ACTIVITY_NAME_TO_FIELD.items()}

    plays = []
    for play, battles in PLAY_BATTLES.items():
        name = name_by_field[play]
        play_selected = name in selected
        play_expanded = play_selected and general.activity_enabled(name)
        plays.append({
            'key': play,
            'value': name,
            'title': f'activity_play_{play}',
            'selected': play_selected,
            'initial_expanded': play_expanded,
            'battles': [
                {
                    'key': battle,
                    'title': f'activity_battle_{battle}',
                    'initial_expanded': play_expanded and general.limit_for(battle) > 0,
                    'limit': _ref('general_config', _limit_argument(battle)),
                    **_range_info(battle),
                    'soul': _soul_arguments(battle),
                    'battle_group': f'{battle}_battle_conf',
                }
                for battle in battles
            ],
            'extra': [_ref('general_config', argument) for argument in PLAY_EXTRA_ARGUMENTS[play]],
        })

    return {
        'version': LAYOUT_VERSION,
        'selector': {
            **_ref('general_config', 'task_sequence'),
            'separator': SEQUENCE_SEPARATOR,
            # 全部取消会变成空串，task_sequence_v 会因此抛错，所以至少保留一项
            'min_selected': 1,
            'options': [
                {'value': name, 'title': f'activity_play_{field}'}
                for name, field in ACTIVITY_NAME_TO_FIELD.items()
            ],
            'aliases': dict(ACTIVITY_NAME_ALIASES),
            'selected': selected,
            'invalid': invalid,
        },
        'plays': plays,
        'common': [_ref('general_config', argument) for argument in COMMON_ARGUMENTS],
        'advanced': {
            'title': 'activity_advanced_settings',
            'groups': list(ADVANCED_GROUPS),
            'initial_expanded': False,
        },
    }
