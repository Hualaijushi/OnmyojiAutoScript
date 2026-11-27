"""Chess lineup, template loading, and hand-card recognition."""

# This Python file uses the following encoding: utf-8

import time
from copy import deepcopy
from functools import cached_property
from pathlib import Path


from module.atom.image import RuleImage
from tasks.Chess.runtime.frame_cards import ChessFrameCardsMixin
from module.logger import logger
from tasks.Chess.strategy.lineup import CUSTOM_LINEUP_VALUE, resolve_lineup_key
from tasks.Chess.strategy.lineup_compat import to_runtime_numbering
from tasks.Chess.strategy.shikigami_catalog import (
    SHIKIGAMI_BY_ROMAJI,
)
from tasks.Chess.strategy.soul_catalog import SOUL_BY_ROMAJI


CHESS_TASK_DIR = Path(__file__).resolve().parents[1]


class ChessRecognitionMixin(ChessFrameCardsMixin):
    """Internal mixin; use through ``ScriptTask`` only."""

    def _configured_lineup_key(self):
        # 上游 73d4ae84 原函数，去掉了 reload 参数：本地只在任务开始时读一次配置（见 select_lineup_strategy），
        # 整份重载 Config 会把调度器在 config.model 上的运行态一起换掉
        task = getattr(self.config, 'chess', None)
        config = getattr(task, 'chess_config', None)
        selected = getattr(config, 'lineup_bond', self.DEFAULT_LINEUP_KEY)
        if getattr(selected, 'value', selected) == CUSTOM_LINEUP_VALUE:
            selected = getattr(config, 'custom_lineup', '')
            if not selected.startswith(('builtin:', 'custom:')):
                selected = 'custom:' + selected
        return selected

    def get_lineup_strategy(
        self,
        lineup_key: str | None = None,
    ) -> dict:
        """返回当前阵容策略；选过阵容之后返回本次任务的快照。

        ``custom:<标识>`` 读阵容编辑器保存的自定义阵容，不存在 / 损坏直接抛错；``builtin:<键>`` 指定的内置阵容
        不存在也抛错。旧配置里的中文名 / 拼音键沿用原来的解析与回落。
        """
        selected = (
            lineup_key
            or getattr(self, '_active_lineup_key', None)
            or self.DEFAULT_LINEUP_KEY
        )
        raw = str(getattr(selected, 'value', selected))
        snapshot = getattr(self, '_lineup_snapshot', None)
        if snapshot is not None and (lineup_key is None or raw == self._active_lineup_key):
            return snapshot
        if raw.startswith('custom:'):
            from tasks.Chess.strategy.lineup_compat import load_custom_strategy
            return load_custom_strategy(raw.removeprefix('custom:'))
        if raw == CUSTOM_LINEUP_VALUE:
            raise ValueError('选择了自定义阵容，但没有指定自定义阵容标识')
        if raw.startswith('builtin:'):
            entry = self.LINEUP_REGISTRY.get(raw.removeprefix('builtin:'))
            if entry is None:
                raise ValueError(f'阵容不存在：{raw}；请重新选择')
            return to_runtime_numbering(entry['strategy'])
        key = resolve_lineup_key(selected)
        entry = self.LINEUP_REGISTRY.get(key)
        if entry is None:
            raise ValueError(f'阵容不存在：{selected}；请在 chesslineup 中重新选择')
        return to_runtime_numbering(entry['strategy'])

    def select_lineup_strategy(self, lineup_key: str) -> dict:
        """切换当前阵容，建立本次任务的快照，并清除依赖阵容的图片规则缓存。

        快照取自上游 73d4ae84：之后所有 ``get_lineup_strategy()`` 都返回这份深拷贝，任务运行中改动阵容文件或
        配置不影响正在进行的对局，下次任务开始时才生效。
        """
        self.__dict__.pop('_lineup_snapshot', None)
        strategy = deepcopy(self.get_lineup_strategy(lineup_key))
        self._active_lineup_key = strategy['key']
        self._lineup_snapshot = strategy
        # 上游已不再用模板匹配手牌 / 商店（改 Frame 卡面库），旧的两个模板缓存不存在了；只剩守护之印规则依赖阵容
        self.__dict__.pop('hakuzosu_protect_rule', None)
        logger.info(
            f'Select Chess lineup strategy: '
            f'{strategy["key"]} ({strategy["display_name"]})'
        )
        return strategy

    def _shikigami_display_name(self, name: str | None) -> str:
        """把内部罗马音转换成日志中更易读的中文名。"""
        if not name:
            return '未知'
        strategy_config = self.get_lineup_strategy()['shikigami'].get(name)
        if strategy_config is not None:
            return strategy_config.get('display_name', name)
        entry = SHIKIGAMI_BY_ROMAJI.get(name)
        return entry.chinese_name if entry is not None else str(name)


    @staticmethod
    def _soul_category_display(category: str | None) -> str:
        if category == 'attack':
            return '输出'
        if category == 'functional':
            return '功能'
        return str(category or '未知')

    @property
    def shikigami_deploy_positions(self) -> dict[str, int]:
        return {
            name: int(config['position'])
            for name, config in self.get_lineup_strategy()['shikigami'].items()
        }

    def _lineup_final_level(self) -> int:
        """阵容最终不保留经济的阶数，等于当前羁绊式神总人数。"""
        return len(self.get_lineup_strategy()['shikigami'])

    @classmethod
    def _load_hand_template_folder(
        cls,
        folder: str,
        prefix: str,
    ) -> list[tuple[str, RuleImage]]:
        """将指定目录中的 PNG 加载为整个手牌区域的识别模板。"""
        template_dir = CHESS_TASK_DIR / folder
        rules: list[tuple[str, RuleImage]] = []
        for file in sorted(template_dir.glob('*.png')):
            stem = file.stem
            if not stem.startswith(prefix):
                continue

            name = stem[len(prefix):]
            # `_1` 是从图鉴裁出的头像模板；完整手牌模板没有该后缀。
            # 两类模板归一为同一个式神名，并同时参与匹配。
            if folder == 'shikigami' and name.endswith('_1'):
                name = name[:-2]
            rule = RuleImage(
                roi_front=(cls.HAND_AREA[0], cls.HAND_AREA[1], 1, 1),
                roi_back=cls.HAND_AREA,
                threshold=cls.HAND_TEMPLATE_THRESHOLD,
                method=RuleImage.METHOD_TEMPLATE_MATCH,
                file=file.as_posix(),
            )
            rules.append((name, rule))

        logger.debug(f'Loaded {len(rules)} Chess {folder} hand templates')
        return rules


    @cached_property
    def board_occupancy_rules(self) -> tuple[RuleImage, ...]:
        """直接加载三种场上勾玉；不依赖 assets/json 注册项。"""
        template_dir = CHESS_TASK_DIR / 'resource' / 'board'
        return tuple(
            RuleImage(
                roi_front=(0, 0, 1, 1),
                roi_back=(0, 0, 1, 1),
                threshold=self.BOARD_OCCUPANCY_TEMPLATE_THRESHOLD,
                method=RuleImage.METHOD_TEMPLATE_MATCH,
                file=(template_dir / f'c_card_{index}.png').as_posix(),
            )
            for index in range(1, 4)
        )


    @cached_property
    def hakuzosu_protect_rule(self) -> RuleImage:
        """梦山白藏主伴生手牌：守护之印。"""
        file = (
            CHESS_TASK_DIR
            / self.HAKUZOSU_PROTECT_IMAGE
        )
        return RuleImage(
            roi_front=(self.HAND_AREA[0], self.HAND_AREA[1], 1, 1),
            roi_back=self.HAND_AREA,
            threshold=self.HAND_TEMPLATE_THRESHOLD,
            method=RuleImage.METHOD_TEMPLATE_MATCH,
            file=file.as_posix(),
        )


    @cached_property
    def soul_hand_rules(self) -> list[tuple[str, RuleImage]]:
        """按拼音文件名加载御魂模板，运行时统一使用拼音键。"""
        rules = self._load_hand_template_folder('resource/soul', prefix='sou_')
        normalized = []
        for romaji, rule in rules:
            entry = SOUL_BY_ROMAJI.get(romaji)
            if entry is None:
                logger.warning(
                    f'Ignore unregistered Chess soul template: {romaji}'
                )
                continue
            normalized.append((entry.romaji, rule))
        return normalized

    def classify_hand_card(self, card_roi: tuple[int, int, int, int]) -> dict:
        """识别一个已定位的手牌框，未收录时返回 `unknown`。"""
        frame_card = self._frame_hand_in_roi(card_roi)
        if frame_card is not None:
            return dict(frame_card)
        x, y, width, height = card_roi
        return {
            'type': 'unknown',
            'name': None,
            'score': 0.0,
            'position': (x + width // 2, y + height // 2),
            'action': 'sell',
        }
