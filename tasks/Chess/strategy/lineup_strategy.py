# This Python file uses the following encoding: utf-8

"""百鬼棋局阵容羁绊配置。

阵容配置只描述阵容自身：

- ``shikigami_positions``：式神 ->
  ``(上阵权重, 站位, (限定御魂...), 是否装守护之印)``。权重越低越
  优先上阵；同权重仍按手牌从左到右处理。
- ``arakawa_goldfish_position``：荒川羁绊召唤金鱼后应移动到的位置。
  金鱼默认从棋盘右侧 12、11、10、9 号位依次寻找生成格。

经济策略属于通用运营流程，写在主任务中，不放入阵容配置。
"""

from tasks.Chess.strategy.shikigami_catalog import build_lineup_shikigami


def build_lineup_strategy(config: dict) -> dict:
    """把轻量阵容配置转换成主程序使用的标准结构。"""
    strategy = {
        'key': config['key'],
        'display_name': config['display_name'],
        'shikigami': build_lineup_shikigami(
            config.get('shikigami_positions', {})
        ),
    }
    goldfish_position = int(config.get('arakawa_goldfish_position', 12))
    if not 1 <= goldfish_position <= 12:
        raise ValueError(
            'arakawa_goldfish_position must be between 1 and 12'
        )
    strategy['arakawa_goldfish_position'] = goldfish_position
    return strategy


QIJIAOSHAN_CONFIG = {
    'key': 'qijiaoshan',
    'display_name': '七角山',
    'shikigami_positions': {
        '古笼火': (2, 1, (), False),
        '薰': (1, 2, ('魍魉之匣', '钓瓶火'), '守护之印'),
        '一目连': (2, 3, (), False),
        '白狼': (1, 4, (), False),
        '萤草': (1, 5, (), False),
        '小松丸': (1, 6, (), False),
        '梦山白藏主': (2, 7, (), False),
        '山风': (2, 8, (), False),
    },
}


QIJIAOSHAN = build_lineup_strategy(QIJIAOSHAN_CONFIG)


HAIGUO_CONFIG = {
    'key': 'haiguo',
    'display_name': '海国',
    'shikigami_positions': {
        '黑童子': (1, 1, (), False),
        '蟹姬': (1, 2, (), False),
        '化鲸': (1, 3, (), False),
        '久次良': (1, 4, (), False),
        '灵海蝶': (1, 5, (), False),
        '铃鹿御前': (1, 6, (), False),
        '白童子': (1, 7, (), False),
        '大岳丸': (1, 8, (), False),
    },
}


HAIGUO = build_lineup_strategy(HAIGUO_CONFIG)


DAJIANGSHAN_CONFIG = {
    'key': 'dajiangshan',
    'display_name': '大江山',
    'shikigami_positions': {
        '雪女': (1, 1, (), False),
        '觉': (1, 2, (), False),
        '鲸汐千姬': (1, 3, (), False),
        '鬼切': (1, 4, (), False),
        '狸猫': (1, 5, (), False),
        '茨木童子': (1, 6, (), False),
        '山童': (1, 7, (), False),
        '薰': (1, 8, (), False),
        '酒吞童子': (1, 10, (), False),
    },
}


DAJIANGSHAN = build_lineup_strategy(DAJIANGSHAN_CONFIG)


HUYAO_CONFIG = {
    'key': 'huyao',
    'display_name': '狐妖',
    'shikigami_positions': {
        '青行灯': (1, 1, (), '守护之印'),
        '烬天玉藻前': (1, 2, (), False),
        '梦山白藏主': (1, 3, (), False),
        '妖狐': (1, 4, (), False),
        '本真三尾狐': (1, 5, (), False),
        '葛叶': (1, 6, (), False),
        '御馔津': (1, 7, (), False),
        '妖刀姬': (1, 8, (), False),
    },
}


HUYAO = build_lineup_strategy(HUYAO_CONFIG)


MINGFU_CONFIG = {
    'key': 'mingfu',
    'display_name': '冥府',
    'shikigami_positions': {
        '青行灯': (1, 1, (), '守护之印'),
        '阎魔': (1, 2, (), False),
        '夜叉': (1, 3, (), False),
        '鬼使黑': (1, 4, (), False),
        '黑童子': (1, 5, (), False),
        '判官': (1, 6, (), False),
        '花鸟卷': (1, 7, (), False),
        '鬼使白': (1, 8, (), False),
        '白童子': (1, 9, (), False),
    },
}


MINGFU = build_lineup_strategy(MINGFU_CONFIG)


LIUHUO_CONFIG = {
    'key': 'liuhuo',
    'display_name': '流火',
    'shikigami_positions': {
        '思金神': (1, 1, (), '守护之印'),
        '凤凰火': (1, 2, (), False),
        '古笼火': (1, 3, (), False),
        '阿修罗': (1, 4, (), False),
        '云间不见岳': (1, 5, (), False),
        '天火命铃彦姬': (1, 7, (), False),
        '梦山白藏主': (1, 7, (), False),
        '烬天玉藻前': (1, 8, (), False),
        '金鱼姬': (1, 9, (), False),
    },
}


LIUHUO = build_lineup_strategy(LIUHUO_CONFIG)
