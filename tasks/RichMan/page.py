"""大富翁独立页面导航。"""

import time

from module.exception import GamePageUnknownError
from module.logger import logger
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.GameUi.action import conditional_action
from tasks.GameUi.default_pages import random_click
from tasks.GameUi.page import (Page, any_of, page_battle, page_battle_prepare,
                               page_battle_result, page_main, page_reward)
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.RichMan.assets import RichManAssets


ACTIVITY_COLUMN_SWITCH_MAX_TRIES = 8


def find_activity_entry(task) -> bool:
    """循环切换庭院右侧活动栏目，直到大富翁所属活动入口出现。"""
    switched = 0
    for _ in range(ACTIVITY_COLUMN_SWITCH_MAX_TRIES):
        task.screenshot()
        if task.appear(RichManAssets.I_MAIN_GOTO_ACT):
            return True
        if task.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=0.5):
            switched += 1
        time.sleep(0.5)

    task.screenshot()
    if task.appear(RichManAssets.I_MAIN_GOTO_ACT):
        return True

    logger.warning(
        f'RichMan activity entry not found after switching columns '
        f'{switched} times ({ACTIVITY_COLUMN_SWITCH_MAX_TRIES} checks)'
    )
    raise GamePageUnknownError(
        f'Cannot find RichMan activity entry after '
        f'{ACTIVITY_COLUMN_SWITCH_MAX_TRIES} column switches'
    )


page_act = Page(RichManAssets.I_TO_BATTLE_MAIN)
page_act.add_enter_failure_hooks(
    find_activity_entry,
    conditional_action(GlobalGameAssets.I_UI_REWARD, random_click),
    GlobalGameAssets.I_UI_BACK_RED,
    RichManAssets.I_SKIP_BUTTON,
)
page_act.connect(page_main, GlobalGameAssets.I_UI_BACK_YELLOW, key='rich_man_act->page_main')
page_main.connect(page_act, RichManAssets.I_MAIN_GOTO_ACT, key='page_main->rich_man_act')

page_act_pass = Page(RichManAssets.I_CLIMB_MODE_PASS)
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='rich_man_pass->rich_man_act')
page_act.connect(page_act_pass, RichManAssets.I_AS_TO_PASS, key='rich_man_act->rich_man_pass')
