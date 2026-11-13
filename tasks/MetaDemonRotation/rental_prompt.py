"""仅处理使用租借队伍挑战时的确认弹窗。"""

from __future__ import annotations

import re
import time
import unicodedata

import numpy as np

from module.atom.click import RuleClick
from module.atom.ocr import RuleOcr


TITLE = RuleOcr(name='md_rotation_rental_challenge_title', mode='Single', method='Default',
                roi=(470, 218, 350, 38), area=(470, 218, 350, 38), keyword='')
CHECKBOX = RuleClick(roi_front=(573, 378, 20, 22), roi_back=(573, 378, 20, 22),
                     name='md_rotation_rental_no_reminder')
CONFIRM = RuleClick(roi_front=(689, 449, 122, 36), roi_back=(689, 449, 122, 36),
                    name='md_rotation_rental_challenge_confirm')


def title_state(text: str) -> str:
    text = unicodedata.normalize('NFKC', str(text or ''))
    text = re.sub(r'[\s?？!！。,.，:：]', '', text)
    if text == '是否使用租借队伍进行挑战':
        return 'present'
    if '租借' in text and ('挑战' in text or '队伍' in text):
        return 'unknown'
    return 'absent'


def checkbox_state(image) -> str:
    """按截图中圆形勾选框的内部亮色勾检测；无法区分时返回未知。"""
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape != (720, 1280, 3):
        return 'unknown'
    region = image[378:401, 573:595]
    white = int(np.count_nonzero(np.all(region >= 185, axis=2)))
    dark = int(np.count_nonzero(np.all(region <= 130, axis=2)))
    if white >= 14 and dark >= 160:
        return 'checked'
    if white <= 4 and dark >= 240:
        return 'unchecked'
    return 'unknown'


def handle_rental_prompt(task, *, confirm_attempted: bool = False) -> str:
    """只在当前帧正向命中专属弹窗时点击，动作后重新检查。"""
    title = title_state(TITLE.ocr_single(task.device.image))
    if title != 'present':
        return title
    if confirm_attempted:
        return 'waiting'
    checked = checkbox_state(task.device.image)
    if checked == 'unchecked':
        task.click(CHECKBOX)
        time.sleep(.4)
        task.screenshot()
        if title_state(TITLE.ocr_single(task.device.image)) != 'present':
            return 'unknown'
        checked = checkbox_state(task.device.image)
    if checked != 'checked':
        return 'unknown'
    # 防止先前帧或反应间隔里的其他弹窗复用相同按钮位置。
    task.screenshot()
    if title_state(TITLE.ocr_single(task.device.image)) != 'present' or checkbox_state(task.device.image) != 'checked':
        return 'unknown'
    task.click(CONFIRM)
    return 'handled'
