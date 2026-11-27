# This Python file uses the following encoding: utf-8
"""地域鬼王：单个目标的结果类型，以及「本次任务运行」内的不同鬼王完成记录。"""
from enum import Enum


class BossResult(Enum):
    WON = '挑战成功'
    ALREADY_RANKED = '此前已上榜'
    DUPLICATE = '本轮已完成的鬼王，重复跳过'
    LOST = '挑战失败'
    UNKNOWN = '结果不明'
    DETAIL_FAILED = '详情打不开'
    NAME_UNKNOWN = '名字无法读取'
    NOT_ELIGIBLE = '悬赏目标没有极且未开启60级前置'
    NO_TARGET = '没有可挑战的悬赏目标'

    @property
    def completed(self) -> bool:
        """这个目标的结果为本次打赢或此前已上榜；具体计数与身份规则见 `BossRunRecord`。"""
        return self in (BossResult.WON, BossResult.ALREADY_RANKED)

    # 保持旧的真值语义（挑战成功 / 已上榜跳过为真，其余为假）；计数一律走 `BossRunRecord`，不要靠真值
    def __bool__(self) -> bool:
        return self.completed


class BossRunRecord:
    """一次任务运行内的完成记录，只在这个对象里，不写配置、不跨运行、不做类级共享。

    按规范化后的完整名字记「不同鬼王」；名字未知的实际胜利单列为匿名次数，不伪造身份，也不因缺名字漏打。
    失败、结果不明以及名字未知的此前已上榜都不增加完成计数。
    """

    def __init__(self, target: int):
        self.target = target
        self.done: dict[str, str] = {}
        self.anonymous_wins: list[str] = []
        self.notes: list[tuple[str, str | None, BossResult]] = []

    @property
    def count(self) -> int:
        return len(self.done) + len(self.anonymous_wins)

    @property
    def reached(self) -> bool:
        return self.count >= self.target

    def mark(self, name: str | None, how: str) -> None:
        if name is None:
            self.anonymous_wins.append(how)
        else:
            self.done.setdefault(name, how)

    def note(self, where: str, name: str | None, result: BossResult) -> None:
        self.notes.append((where, name, result))

    def summary(self) -> str:
        names = '、'.join(f'{n}({how})' for n, how in self.done.items()) or '无'
        text = f'完成 {self.count} / 目标 {self.target}，完成名单：{names}'
        if self.anonymous_wins:
            text += (f'；已确认不同鬼王 {len(self.done)}，匿名挑战成功 {len(self.anonymous_wins)} 次'
                     f'（身份未确认，可能重复）：{"、".join(self.anonymous_wins)}')
        return text

    def skipped_reasons(self) -> str:
        items = [f'{where} {name or "未知"}：{result.value}' for where, name, result in self.notes
                 if not result.completed or (name is None and result is BossResult.ALREADY_RANKED)]
        return '；'.join(items) or '无'
