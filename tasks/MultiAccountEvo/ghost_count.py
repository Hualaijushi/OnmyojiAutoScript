"""读取超鬼王召唤队列中五星、六星的持有数量。"""

from __future__ import annotations

import re
import time

from module.atom.ocr import RuleOcr
from tasks.MetaDemon import page as pages
from tasks.MetaDemon.script_task import ScriptTask as MetaDemonTask


def parse_count(raw: str) -> int | None:
    """只接受完整数字；空白、模糊或其他文本不能当成零。"""
    value = str(raw or '').strip()
    return int(value) if re.fullmatch(r'[0-9]{1,4}', value) else None


def count_roi(rule) -> tuple[int, int, int, int] | None:
    """按当前匹配到的图标位置，定位其右下方的数字区域。"""
    x, y, width, height = map(int, rule.roi_front)
    x, y = x + width - 10, y + height + 15
    if x < 0 or y < 0 or x + 30 > 1280 or y + 30 > 720:
        return None
    return x, y, 30, 30


def collect_ghost_counts(config, device) -> dict[str, int | None]:
    """只打开队列并读数，不点击召唤或修改队列。"""
    task = MetaDemonTask(config, device)
    task.before_run()
    task.goto_page(pages.page_meta_demon_boss, timeout=20)
    deadline = time.monotonic() + 15
    opened = False
    try:
        while time.monotonic() < deadline:
            task.screenshot()
            if task.appear(task.I_MD_GET_BOSS):
                opened = True
                break
            task.appear_then_click(task.I_MD_SWITCH_TICKET, interval=1)
            time.sleep(.3)
        if not opened:
            return {'5': None, '6': None}

        counts = {}
        for star, rule in (('5', task.I_MD_FIVE_STARS), ('6', task.I_MD_SIX_STARS)):
            readings = []
            try:
                for _ in range(2):
                    task.screenshot()
                    if not task.appear(task.I_MD_GET_BOSS) or not task.appear(rule):
                        break
                    roi = count_roi(rule)
                    if roi is None:
                        break
                    ocr = RuleOcr(name=f'md_ghost_count_{star}', mode='Single', method='Default',
                                  roi=roi, area=roi, keyword='')
                    readings.append(parse_count(ocr.ocr_single(task.device.image)))
                    time.sleep(.2)
            except Exception:
                readings.clear()
            counts[star] = readings[0] if len(readings) == 2 and readings[0] is not None and readings[0] == readings[1] else None
        return counts
    finally:
        if opened:
            task.screenshot()
            if task.appear(task.I_MD_GET_BOSS):
                task.appear_then_click(task.I_MD_CLOSE_POPUP, interval=0)
