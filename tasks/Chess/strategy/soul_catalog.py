# This Python file uses the following encoding: utf-8

"""百鬼棋局御魂统一编号目录。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SoulEntry:
    number: int
    romaji: str
    chinese_name: str
    category: str

    @property
    def key(self) -> str:
        return f'{self.number}-{self.chinese_name}'

    @property
    def image_name(self) -> str:
        return f'sou_{self.romaji}.png'


SOUL_ENTRIES = (
    SoulEntry(1, 'poshi', '破势', 'attack'),
    SoulEntry(2, 'shanghunniao', '伤魂鸟', 'attack'),
    SoulEntry(3, 'fuyi', '蝠翼', 'attack'),
    SoulEntry(4, 'wangqie', '网切', 'attack'),
    SoulEntry(5, 'yinmoluo', '阴摩罗', 'attack'),
    SoulEntry(6, 'yingshengchong', '应声虫', 'attack'),
    SoulEntry(7, 'kuanggu', '狂骨', 'attack'),
    SoulEntry(8, 'beichuifang', '贝吹坊', 'attack'),
    SoulEntry(9, 'beifu', '被服', 'functional'),
    SoulEntry(10, 'bangjing', '蚌精', 'functional'),
    SoulEntry(11, 'niepanzhihuo', '涅槃之火', 'functional'),
    SoulEntry(12, 'qingnvfang', '青女房', 'functional'),
    SoulEntry(13, 'zheng', '狰', 'functional'),
    SoulEntry(14, 'huoling', '火灵', 'functional'),
    SoulEntry(15, 'dizangxiang', '地藏像', 'functional'),
    SoulEntry(16, 'wangliangzhixia', '魍魉之匣', 'functional'),
    SoulEntry(17, 'diaopinghuo', '钓瓶火', 'functional'),
    SoulEntry(18, 'zhaocaimao', '招财猫', 'functional'),
    SoulEntry(19, 'jingji', '镜姬', 'functional'),
    SoulEntry(20, 'mumei', '木魅', 'functional'),
)

SOUL_BY_NUMBER = {entry.number: entry for entry in SOUL_ENTRIES}
SOUL_BY_ROMAJI = {entry.romaji: entry for entry in SOUL_ENTRIES}
SOUL_BY_CHINESE_NAME = {
    entry.chinese_name: entry
    for entry in SOUL_ENTRIES
}
SOUL_BY_KEY = {entry.key: entry for entry in SOUL_ENTRIES}
SOUL_ALIASES = {
    '地藏': '地藏像',
}


def resolve_soul(value) -> SoulEntry | None:
    """解析编号、``编号-御魂``、代码名或中文名。"""
    if isinstance(value, SoulEntry):
        return value
    if isinstance(value, int):
        return SOUL_BY_NUMBER.get(value)
    text = str(value or '').strip()
    if not text:
        return None
    if text.isdigit():
        return SOUL_BY_NUMBER.get(int(text))
    text = SOUL_ALIASES.get(text, text)
    return (
        SOUL_BY_KEY.get(text)
        or SOUL_BY_ROMAJI.get(text)
        or SOUL_BY_CHINESE_NAME.get(text)
    )


def _validate_catalog() -> None:
    total = len(SOUL_ENTRIES)
    if total != 20:
        raise ValueError(f'御魂目录数量异常: {total}, expected=20')
    for label, index in (
        ('编号', SOUL_BY_NUMBER),
        ('代码名', SOUL_BY_ROMAJI),
        ('中文名', SOUL_BY_CHINESE_NAME),
        ('编号-御魂', SOUL_BY_KEY),
    ):
        if len(index) != total:
            raise ValueError(f'御魂目录存在重复{label}')
    if any(
        entry.category not in {'attack', 'functional'}
        for entry in SOUL_ENTRIES
    ):
        raise ValueError('御魂类型必须为 attack 或 functional')


_validate_catalog()
