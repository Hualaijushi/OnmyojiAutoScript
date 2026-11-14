"""多账号超鬼王达成场次后领取积分。"""

import time

from module.atom.image import RuleImage
from tasks.MetaDemon import page as pages


SCORE_EMPTY = RuleImage(roi_front=(450, 253, 231, 53), roi_back=(420, 230, 320, 100),
                        threshold=0.85, method='Template matching',
                        file='./tasks/MetaDemonRotation/images/score_empty.png')


def claim_score(task) -> str:
    """仅在确认积分页面、奖励和返回状态时报告结果。"""
    time.sleep(5)
    task.screenshot()
    if not task.appear(task.I_CHECK_BOSS_PAGE):
        return 'unknown'
    if not task.appear_then_click(task.I_MD_SCORE_BOX, interval=1):
        return 'unknown'

    deadline = time.monotonic() + 20
    no_reward_before = time.monotonic() + 3
    empty_frames = 0
    reward_seen = False
    while time.monotonic() < deadline:
        task.screenshot()
        if task.appear(task.I_UI_REWARD):
            reward_seen = True
            empty_frames = 0
            task.click(pages.random_click(), interval=0.8)
            time.sleep(.5)
            continue
        if task.appear(SCORE_EMPTY) and task.appear(task.I_UI_BACK_YELLOW):
            empty_frames += 1
            if empty_frames >= 2 and (reward_seen or time.monotonic() >= no_reward_before):
                break
        else:
            empty_frames = 0
        time.sleep(.5)
    else:
        return 'unknown'

    if not task.appear_then_click(task.I_UI_BACK_YELLOW, interval=1):
        return 'unknown'
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        time.sleep(.4)
        task.screenshot()
        if task.appear(task.I_CHECK_BOSS_PAGE) and not task.appear(SCORE_EMPTY):
            return 'claimed' if reward_seen else 'empty'
    return 'unknown'
