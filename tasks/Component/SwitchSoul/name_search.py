# This Python file uses the following encoding: utf-8
"""SwitchSoul 按名称找分组 / 找队伍：与设备无关的纯函数部分（OCR 结果解析、精确匹配、完整性判断）。

OCR 结果的真实结构是 `module.ocr.common.BoxedResult`：`ocr_text` 为文本，`box` 为 4×2 的点阵，
坐标相对 OCR 裁剪区域（`RuleOcr.roi`）的左上角。这里统一换算成屏幕绝对坐标的 `(x, y, w, h)`。
"""

from dataclasses import dataclass

from module.exception import GamePageUnknownError, RequestHumanTakeover

# 文字框离列表可视区上下沿不足这个像素数，就认为这一行被列表边缘裁切（文字可能不完整），本屏不点
EDGE_PAD = 3


class SwitchSoulNameError(RequestHumanTakeover):
    """确定需要人工修正配置或判断的情况：空名称、完整搜索后确认目标不存在、同屏精确同名、无法确认分组已选中。

    继承 `RequestHumanTakeover`：走调度器已有的人工处理分支（通知后进程退出），不会通过反复重启游戏去「解决」写错的名字，
    也不会在没有把握的情况下继续操作（可能选错分组 / 队伍）。消息里带目标名、阶段和原因。
    """


class SwitchSoulPageError(GamePageUnknownError):
    """临时识别 / 页面问题：OCR 连续读空、列表一直不稳定、滑动没发出、搜索达到保护上限但没有可靠确认到底、阶段超时。

    继承 `GamePageUnknownError`：沿用调度器已有的「通知 + 重启游戏 + 稍后重试」恢复。达到上限不会被写成「名称不存在」。
    设备类异常（截图 / 控制失败）不经过这里，保持原始异常类型。
    """


@dataclass(frozen=True)
class NameLine:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def box(self) -> tuple:
        return self.x, self.y, self.w, self.h


def normalize_target(kind: str, name) -> str:
    """目标名只去首尾空白；不去符号、不去内部空格、不做模糊纠错。空名直接报错。"""
    if not isinstance(name, str) or not name.strip():
        raise SwitchSoulNameError(f'{kind}名称为空，无法按名称切换预设，请在任务设置里填写{kind}名称')
    return name.strip()


def parse_lines(results, roi) -> list:
    """`detect_and_ocr()` 的结果 → 按 y 从上到下排序的 `NameLine`（空文本丢弃）。

    结构不符直接抛 `ValueError`（不静默截取）：box 必须是 4×2，`ocr_text` 必须是字符串。
    """
    ox, oy = int(roi[0]), int(roi[1])
    lines = []
    for item in results:
        text = getattr(item, 'ocr_text', None)
        box = getattr(item, 'box', None)
        if not isinstance(text, str):
            raise ValueError(f'OCR 结果缺少文本：{item!r}')
        try:
            x0, y0 = box[0][0], box[0][1]
            x1 = box[1][0]
            y2 = box[2][1]
            if len(box) != 4:
                raise ValueError('box 不是 4 个点')
        except (TypeError, IndexError, ValueError) as e:
            raise ValueError(f'OCR 结果的 box 不是 4×2 点阵：{item!r}') from e
        text = text.strip()
        if not text:
            continue
        lines.append(NameLine(text, int(round(x0 + ox)), int(round(y0 + oy)),
                              max(1, int(round(x1 - x0))), max(1, int(round(y2 - y0)))))
    lines.sort(key=lambda line: (line.y, line.x))
    return lines


def parse_matches(rule, matches) -> list:
    """`RuleImage.match_all_any()` 的真实结果 `[(score, x, y, w, h), ...]` → 内部统一的 `[(x, y, w, h), ...]`。

    格式不符直接抛 `ValueError`（带规则名），不静默截取：把 score 当成 x 会让所有位置错位。
    """
    boxes = []
    for item in matches:
        try:
            score, x, y, w, h = item
            float(score)
            boxes.append((int(x), int(y), int(w), int(h)))
        except (TypeError, ValueError) as e:
            raise ValueError(f'{getattr(rule, "name", rule)} 匹配结果不是 (score, x, y, w, h)：{item!r}') from e
    return boxes


def exact_matches(lines, name: str) -> list:
    """精确相等（已去首尾空白）。「魂土」不会匹配「魂土备用」，也不做单字回退。"""
    return [line for line in lines if line.text == name]


def is_complete(line: NameLine, viewport: tuple) -> bool:
    """文字框是否完整落在列表可视区内（上下各留 `EDGE_PAD`）。被边缘裁切的行不能当作可点击的命中。"""
    top, bottom = viewport
    return line.y >= top + EDGE_PAD and line.y + line.h <= bottom - EDGE_PAD
