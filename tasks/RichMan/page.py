"""大富翁独立页面导航。"""

import time

from module.logger import logger
from tasks.GameUi.default_pages import handle_activity_overlay
from tasks.GameUi.page import (
    Page,
    any_of,
    page_activity,
    page_battle,
    page_battle_prepare,
    page_battle_result,
    page_main,
    page_reward,
    random_click,
)
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.RichMan.assets import RichManAssets


RICHMAN_ENTRY_SETTLE_SECONDS = 3.0


def enter_richman_board(task) -> bool:
    """等待活动附属页弹出并完成清理后，再进入大富翁棋盘。"""
    logger.info(f'Wait {RICHMAN_ENTRY_SETTLE_SECONDS:.1f}s for RichMan activity overlays')
    time.sleep(RICHMAN_ENTRY_SETTLE_SECONDS)
    if not handle_activity_overlay(task):
        return False
    task.screenshot()
    return task.appear_then_click(RichManAssets.I_TO_BATTLE_MAIN, interval=0)


page_act = page_activity

page_act_pass = Page(RichManAssets.I_CHECK_RM_RICHMAN)
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='rich_man_pass->rich_man_act')
page_act.connect(page_act_pass, enter_richman_board, key='rich_man_act->rich_man_pass')
