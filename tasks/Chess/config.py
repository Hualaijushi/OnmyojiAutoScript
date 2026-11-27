# This Python file uses the following encoding: utf-8

from pydantic import Field

from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler
from tasks.Chess.strategy.lineup import (
    CUSTOM_LINEUP_VALUE,
    DEFAULT_LINEUP_KEY,
    LINEUP_REGISTRY,
    LineupBond,
    oasx_lineup_choices,
    resolve_lineup_key,
)


class ChessConfig(ConfigBase):
    """百鬼棋局循环与结束条件。"""

    lineup_bond: LineupBond = Field(
        title='选择阵容羁绊',
        default=LineupBond.ARAKAWA,
        description='选择百鬼棋局使用的阵容羁绊与对应运营策略',
    )

    custom_lineup: str = Field(title='自定义阵容标识', default='',
                               description='custom_lineup_help')

    rank_protection: bool = Field(
        title='保段位',
        default=False,
        description='开启后每完成前四名一局主动退出三局；退出局不计入执行次数',
    )

    run_count: int = Field(
        title='执行次数',
        default=1,
        ge=-1,
        description='完成目标局数后结束；设置为-1时一直执行',
    )
    matchmaking_timeout_seconds: int = Field(
        title='匹配限制时间（秒）',
        default=60,
        ge=10,
        description=(
            '单次匹配超过限制后取消并重新匹配；连续三次超时'
            '则标记为等待过多并结束任务'
        ),
    )
    limit_time: Time = Field(
        title='运行时间限制',
        default=Time(minute=30),
        description='达到限制时间后不再开始下一局，已经开始的对局会正常完成',
    )
    coin_full_exit: bool = Field(
        title='刷满鼬乐币',
        default=False,
        description='勾选后检测到鼬乐币已满时立即结束百鬼棋局',
    )
    continue_grigri_refresh_below_nine: bool = Field(
        title='刷新非前40%符咒',
        default=True,
        description=(
            '按当前品质符咒总数的实际收益排名，保留排名前40%的'
            '选项，只刷新其余仍有刷新次数的位置；同收益边界按'
            '固定图鉴顺序确定名次'
        ),
    )


class Chess(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    chess_config: ChessConfig = Field(default_factory=ChessConfig)

    def oasx_args(self, groups):
        # 上游 73d4ae84 原函数；本地适配：默认项取本地默认阵容（上游写死七角山）
        choices = oasx_lineup_choices()
        selected = self.chess_config.lineup_bond
        if getattr(selected, 'value', selected) == CUSTOM_LINEUP_VALUE:
            identity = self.chess_config.custom_lineup
            if not identity.startswith(('builtin:', 'custom:')):
                identity = 'custom:' + identity
        else:
            identity = 'builtin:' + resolve_lineup_key(selected)
        current = next((label for label, key in choices.items() if key == identity), None)
        labels = list(choices)
        if current is None:
            current = f'阵容不存在 [{identity}]'
            labels.append(current)
        items = groups.get('chess_config', [])
        for item in items:
            if item['name'] == 'lineup_bond':
                item.update(type='enum', enumEnum=labels, value=current,
                            default=next((label for label, key in choices.items()
                                          if key == 'builtin:' + DEFAULT_LINEUP_KEY), current))
        groups['chess_config'] = [item for item in items if item['name'] != 'custom_lineup']
        return groups

    def select_oasx_lineup(self, value):
        """Handle dynamic choices while retaining the old enum/id storage contract."""
        # 上游 73d4ae84 原函数；本地适配：内置阵容仍按原枚举值保存（lineup_bond=中文名，custom_lineup 不动），
        # 只有自定义阵容才写「自定义阵容 + custom:<标识>」。上游把内置也存成「自定义阵容 + builtin:<键>」。
        import re
        choices = oasx_lineup_choices()
        identity = choices.get(str(value))
        if identity is None and str(value).startswith(('builtin:', 'custom:')):
            identity = str(value)
        if identity is None:
            match = re.fullmatch(r'(内置|自定义) · .* \[([a-z][a-z0-9_]{0,47})\]', str(value))
            if match:
                identity = ('builtin:' if match[1] == '内置' else 'custom:') + match[2]
        if identity is None:
            return None
        if identity not in choices.values():
            return False
        source, key = identity.split(':', 1)
        if source == 'builtin':
            update = {'lineup_bond': LINEUP_REGISTRY[key]['display_name']}
        else:
            update = {'lineup_bond': CUSTOM_LINEUP_VALUE, 'custom_lineup': identity}
        self.chess_config = ChessConfig.model_validate({**self.chess_config.model_dump(), **update})
        return True
