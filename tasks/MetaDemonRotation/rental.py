"""超鬼王队伍租借面板；仅选择当前可见的前三队。"""

from __future__ import annotations

import time
import cv2
import numpy as np

from module.atom.click import RuleClick
from module.interaction_policy import InteractionPolicy
from tasks.MetaDemon.assets import MetaDemonAssets


ENTRY = MetaDemonAssets.I_MD_PRESET
DEPLOY = MetaDemonAssets.I_MD_PRE_FIGHT


def relative_click(name: str, dx: int, dy: int, width: int, height: int) -> RuleClick:
    """以识别到的出战按钮为锚点生成点击区域。"""
    x, y, _, _ = DEPLOY.roi_front
    roi = (x + dx, y + dy, width, height)
    return RuleClick(roi_front=roi, roi_back=roi, name=name)


def selected_border(image: np.ndarray, index: int) -> bool:
    """检查截图中对应队伍卡片左侧的紫色选中边框。"""
    if index not in (1, 2, 3) or image is None or image.shape[:2] != (720, 1280):
        return False
    x, y, _, _ = DEPLOY.roi_front
    x -= 139
    y += -328 + (index - 1) * 96
    strip = image[y + 5:y + 82, x:x + 11]
    if strip.size == 0:
        return False
    hsv = cv2.cvtColor(strip, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array((125, 65, 100), dtype=np.uint8),
                       np.array((170, 255, 255), dtype=np.uint8))
    return int(np.count_nonzero(mask)) >= 45


def deploy_rental(task, sequence: int) -> str:
    """选择租借序号并确认出战；无法证明步骤成功时不继续战斗。"""
    if sequence not in (1, 2, 3):
        return 'unknown'
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        task.screenshot()
        if task.appear(DEPLOY):
            break
        task.appear_then_click(ENTRY, interval=1, policy=InteractionPolicy.NAVIGATION)
        time.sleep(.3)
    else:
        return 'unknown'

    task.click(relative_click('md_rotation_rental_tab', -263, -325, 110, 48))
    time.sleep(.5)
    task.screenshot()
    if not task.appear(DEPLOY):
        return 'unknown'
    row = relative_click(f'md_rotation_rental_row_{sequence}', -118,
                         -325 + (sequence - 1) * 96, 300, 30)
    task.click(row)
    time.sleep(.5)
    task.screenshot()
    if not task.appear(DEPLOY):
        return 'unknown'
    if not selected_border(task.device.image, sequence):
        return 'unknown'
    if not task.appear_then_click(DEPLOY, policy=InteractionPolicy.CONFIRM):
        return 'unknown'
    for _ in range(2):
        time.sleep(.4)
        task.screenshot()
        if task.appear(DEPLOY) or not task.appear(task.I_CHECK_BOSS_PAGE):
            return 'unknown'
    return 'ready'
