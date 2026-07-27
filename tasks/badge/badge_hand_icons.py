"""手牌符咒图标的中文名称与文件名对照。

本文件与放大后的 badge_*.png 放在同一目录。导入后使用：

    ICON_FILENAME_BY_CHINESE["不屈灵符·贰"]
    # "badge_Buqulingfu_er.png"
"""

from pathlib import Path


_BASE_NAMES = {
    "Baiguiyexing": "百鬼夜行",
    "Bangzhiyuzhu": "蚌之御祝",
    "Beifuyuzhu": "被服御祝",
    "Bugua": "卜卦",
    "Buqulingfu": "不屈灵符",
    "Buweisuodong": "不为所动",
    "Dajiangshanwenzhang": "大江山纹章",
    "Dajiangshanzhuyin": "大江山朱印",
    "Dayaolingfu": "大妖灵符",
    "Duanrenwenzhang": "锻刃纹章",
    "Duanrenzhuyin": "锻刃朱印",
    "Duohaoji": "多号机",
    "Duzaiwenzhang": "毒灾纹章",
    "Duzaizhuyin": "毒灾朱印",
    "Fanjinfuzhou": "返金符咒",
    "Fengnafu": "奉纳符",
    "Fenliewenzhang": "分裂纹章",
    "Fenliezhuyin": "分裂朱印",
    "Fuzhiyuzhu": "福至御祝",
    "Guihuowenzhang": "鬼火纹章",
    "Guihuozhuyin": "鬼火朱印",
    "Guishenzhuli": "鬼神助力",
    "Haiguowenzhang": "海国纹章",
    "Haiguozhuyin": "海国朱印",
    "Hanshuangwenzhang": "寒霜纹章",
    "Hanshuangzhuyin": "寒霜朱印",
    "Heiyeshanzhuyin": "黑夜山朱印",
    "Hongfu": "洪福",
    "Hongyundamo": "鸿运达摩",
    "Houjibofa": "厚积薄发",
    "Huaeweiji": "化厄为吉",
    "Huangchuanwengzhang": "荒川纹章",
    "Huangchuanwenzhang": "荒川纹章",
    "Huangchuanzhuyin": "荒川朱印",
    "Huofuxiangyi": "祸福相依",
    "Huyaowenzhang": "狐妖纹章",
    "Huyaozhuyin": "狐妖朱印",
    "Huyouwenzhang": "护佑纹章",
    "Huyouzhuyin": "护佑朱印",
    "Jiazhouwenzhang": "甲胄纹章",
    "Jiazhouzhuyin": "甲胄朱印",
    "Jiejing": "捷径",
    "Jingxizhaohuan": "惊喜召唤",
    "Jingyanyushou": "经验御守",
    "Jingzhiyuzhu": "镜之御祝",
    "Jinyun": "金运",
    "Kuangyefuzhou": "狂野符咒",
    "Landiao": "蓝调",
    "Liuhuowenzhang": "流火纹章",
    "Liuhuozhuyin": "流火朱印",
    "Lunruzhidao": "轮入之道",
    "Mihunshangbing": "秘魂上宾",
    "Mingfuwenzhang": "冥府纹章",
    "Mingfuzhuyin": "冥府朱印",
    "Mumeiyuzhu": "木魅御祝",
    "Niepanyuzhu": "涅槃御祝",
    "Pinanjingwenzhang": "平安京纹章",
    "Pinganjingzhuyin": "平安京朱印",
    "Pojunzhishi": "破军之势",
    "Poshiyuzhu": "破势御祝",
    "Qiangqulingfu": "强驱灵符",
    "Qiangtiwenzhang": "强体纹章",
    "Qiangtizhuyin": "强体朱印",
    "Qiangyunzhuyin": "强运朱印",
    "Qiecuojiyi": "切磋技艺",
    "Qijiaoshanwenzhang": "七角山纹章",
    "Qijiaoshanzhuyin": "七角山朱印",
    "Qingnvfangyuzhu": "青女房御祝",
    "Qixinxieli": "齐心协力",
    "Qiyulingfu": "气愈灵符",
    "Shanghunniaoyuzhu": "伤魂鸟御祝",
    "Shangjin": "赏金",
    "Shencifuzhou": "神赐符咒",
    "Shenghezhili": "升贺之礼",
    "Shengjinfuzhou": "剩金符咒",
    "Shizhanwenzhang": "嗜战纹章",
    "Shizhanzhuyin": "嗜战朱印",
    "Shoulinglieren": "首领猎人",
    "Suijiwenzhang": "随机纹章",
    "Suoqian": "索签",
    "Tianjiangzhigui": "天降之鬼",
    "Tunjinguizhou": "吞金鬼咒",
    "Wangqieyuzhu": "网切御祝",
    "Xianxuezhiyong": "鲜血之拥",
    "Xiaoguilingfu": "小鬼灵符",
    "Xiuxing": "修行",
    "Xunshanwengua": "寻山问卦",
    "Yingshengchongyuzhu": "应声虫御祝",
    "Yinmoluoyuzhu": "阴摩罗御祝",
    "Yixingwenzhang": "易形纹章",
    "Yixingzhuyin": "易形朱印",
    "Yongqifuzhou": "勇气符咒",
    "Youxuanyuhun": "优选御魂",
    "Yuhuofuzhou": "御火符咒",
    "Zhaocaijigui": "招财吉鬼",
    "Zhaocaimaoyuzhu": "招财猫御祝",
    "Zhaofudamo": "招福达摩",
    "Zhengzhiyuzhu": "狰之御祝",
    "Zheshangjiazhe": "折上加折",
    "Zhongjianzhili": "中坚之力",
    "Zhuijiwenzhang": "追击纹章",
    "Zhuijizhuyin": "追击朱印",
    "Ziqidonglai": "紫气东来",
    "Zonghengjixing": "纵横疾行",
}

_SUFFIX_NAMES = {
    "er": "贰",
    "san": "叁",
    "da": "大",
    "xiao": "小",
    "daji": "大吉",
    "zhongji": "中吉",
    "xiaoji": "小吉",
    "zhengji": "正吉",
    "ji": "吉",
}


def _chinese_name(stem: str) -> str:
    base, separator, suffix = stem.rpartition("_")
    if separator and suffix in _SUFFIX_NAMES:
        return f"{_BASE_NAMES[base]}·{_SUFFIX_NAMES[suffix]}"
    return _BASE_NAMES[stem]


ICON_FILENAME_BY_CHINESE = {
    _chinese_name(path.stem.removeprefix("badge_")): path.name
    for path in sorted(Path(__file__).parent.glob("badge_*.png"))
}

CHINESE_BY_ICON_FILENAME = {
    filename: chinese for chinese, filename in ICON_FILENAME_BY_CHINESE.items()
}

