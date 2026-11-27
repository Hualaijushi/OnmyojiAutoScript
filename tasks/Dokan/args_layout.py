# This Python file uses the following encoding: utf-8
"""道馆配置页的可选展示信息（GET /{script}/{task}/args/layout，kind = "dokan"，version = 1）。

只描述「已有参数怎么分组、哪个模式用、初始是否展开」：所有引用都是 /args 里原样的 (group, argument)，前端按原路径
PUT 保存；这里只读配置、不写配置、不参与任务执行，也不新增任何持久化字段。

模式选择绑定现有 `dokan_config.welfare_mode`（bool）：False = 普通道馆，True = 福利道馆；切换只改变展示，
另一种模式的参数不清空、不重置。字段归属以实际执行代码为准（见 docs/AI_CONTEXT.md 的字段归属清单）：
- 福利流程（`tasks/Dokan/welfare.py`）只读 `welfare_min_people` 和七个星期选择；它的一键预设是固定流程，不读任何配置；
- 普通流程读找馆条件 / 战斗配置 / 御魂切换 / 馆主次数；
- `dokan_run_time` 与 `daily_attack_count` 两种模式的 `next_run` 都会读，归「任务调度」。
"""

from tasks.Dokan.config import Dokan, WELFARE_WEEKDAY_FIELDS

LAYOUT_KIND = 'dokan'
LAYOUT_VERSION = 1

MODE_NORMAL, MODE_WELFARE = 'normal', 'welfare'
WEEKDAY_KEYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def _field(group: str, argument: str, **extra) -> dict:
    return {'type': 'field', 'group': group, 'argument': argument, **extra}


def _group(group: str) -> dict:
    return {'type': 'group', 'group': group}


def _weekdays() -> dict:
    """七个星期布尔字段组成的复合控件：固定周一到周日，每天引用原 group / argument 并按原路径各自 PUT 保存；
    不拼字符串、不新增字段；允许七天全部取消（福利模式没有允许运行的日期）。说明和空选提示只在这里出现一次。"""
    return {
        'type': 'weekdays',
        'key': 'welfare_run_days',
        'title': 'dokan_welfare_run_days',
        'help': 'welfare_run_days_help',
        'empty_hint': 'dokan_welfare_run_days_empty',
        'allow_empty': True,
        'days': [
            {'key': key, 'label': argument, 'group': 'dokan_config', 'argument': argument}
            for key, argument in zip(WEEKDAY_KEYS, WELFARE_WEEKDAY_FIELDS)
        ],
    }


def _section(key: str, modes: list, expanded_modes: list, mode: str, items: list, **extra) -> dict:
    """modes：哪些模式使用该分区（静态）；inactive_badge：当前模式不在 modes 里时前端挂的标注（静态，按当前草稿里的模式判断，
    不要用 GET 当时的快照）；initial_expanded：**只供首次载入**——按 GET 当时的模式算出的布尔值，前端之后重读 /args 时
    不应再据此收起用户正在编辑的区块。"""
    badge = {MODE_NORMAL: 'dokan_badge_normal_only', MODE_WELFARE: 'dokan_badge_welfare_only'}.get(modes[0])         if len(modes) == 1 else None
    return {
        'key': key,
        'title': f'dokan_section_{key}',
        'modes': modes,
        'inactive_badge': badge,
        'initial_expanded': mode in expanded_modes,
        'items': items,
        **extra,
    }


def build_args_layout(conf: Dokan) -> dict:
    mode = MODE_WELFARE if conf.dokan_config.welfare_mode else MODE_NORMAL
    both = [MODE_NORMAL, MODE_WELFARE]
    sections = [
        _section('welfare', [MODE_WELFARE], [MODE_WELFARE], mode, [
            _weekdays(),
            _field('dokan_config', 'welfare_min_people'),
            {'type': 'note', 'text': 'dokan_welfare_note'},
        ]),
        _section('normal_open', [MODE_NORMAL], [MODE_NORMAL], mode, [
            _field('dokan_config', 'monday_to_thursday'),
            _field('dokan_config', 'try_start_dokan'),
            _field('dokan_config', 'find_dokan_score'),
            _field('dokan_config', 'min_people_num'),
            _field('dokan_config', 'min_bounty'),
            _field('dokan_config', 'find_dokan_refresh_count'),
        ]),
        _section('normal_battle', [MODE_NORMAL], [MODE_NORMAL], mode, [
            _field('dokan_config', 'dokan_attack_priority'),
            _field('dokan_config', 'dokan_auto_cheering_while_cd'),
            _field('attack_count_config', 'attack_dokan_master'),
            _group('dokan_member_battle_conf'),
            _group('dokan_owner_battle_conf'),
        ]),
        _section('normal_preset', [MODE_NORMAL], [], mode, [
            _group('dokan_member_switch_soul'),
            _group('dokan_owner_switch_soul'),
        ]),
        # 两种模式的 next_run 都读 dokan_run_time 和 daily_attack_count；福利模式靠手动把下次运行时间设为现在触发，所以福利下默认展开
        _section('schedule', both, [MODE_WELFARE], mode, [
            _group('scheduler'),
            _field('dokan_config', 'dokan_run_time'),
            _field('attack_count_config', 'daily_attack_count'),
        ]),
        # random_delay：全仓没有读取它的执行路径，只保留在原位置（不删除、不改值）
        _section('advanced', both, [], mode, [
            _field('dokan_config', 'random_delay', note='dokan_note_no_execution_path'),
        ], collects_unreferenced=True),
    ]
    return {
        'kind': LAYOUT_KIND,
        'version': LAYOUT_VERSION,
        'title': 'dokan_layout_title',
        'mode': {
            'group': 'dokan_config',
            'argument': 'welfare_mode',
            'title': 'dokan_mode',
            'options': [
                {'key': MODE_NORMAL, 'value': False, 'title': 'dokan_mode_normal'},
                {'key': MODE_WELFARE, 'value': True, 'title': 'dokan_mode_welfare'},
            ],
        },
        'sections': sections,
    }
