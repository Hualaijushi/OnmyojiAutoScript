import time

from module.exception import GamePageUnknownError
from module.logger import logger
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.Fakegod.assets import FakegodAssets
from tasks.GameUi.action import conditional_action
from tasks.GameUi.default_pages import random_click
from tasks.GameUi.page import (Page, any_of, page_battle, page_battle_prepare,
                               page_battle_result, page_main, page_reward)
from tasks.GlobalGame.assets import GlobalGameAssets


ACTIVITY_COLUMN_SWITCH_MAX_TRIES = 8


def find_activity_entry(task) -> bool:
    """循环切换庭院右侧活动栏目，直到伪神活动入口出现。"""
    switched = 0
    for _ in range(ACTIVITY_COLUMN_SWITCH_MAX_TRIES):
        task.screenshot()
        if task.appear(FakegodAssets.I_MAIN_GOTO_ACT):
            return True
        if task.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=0.5):
            switched += 1
        time.sleep(0.5)

    task.screenshot()
    if task.appear(FakegodAssets.I_MAIN_GOTO_ACT):
        return True
    logger.warning(f'Fakegod entry not found after switching columns {switched} times')
    raise GamePageUnknownError('Cannot find Fakegod activity entry')


page_act = Page(FakegodAssets.I_TO_BATTLE_MAIN)
page_act.add_enter_failure_hooks(
    find_activity_entry,
    conditional_action(GlobalGameAssets.I_UI_REWARD, random_click),
    GlobalGameAssets.I_UI_BACK_RED,
    FakegodAssets.I_SKIP_BUTTON,
)
page_act.connect(page_main, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_act->page_main')
page_main.connect(page_act, FakegodAssets.I_MAIN_GOTO_ACT, key='page_main->fakegod_act')

page_act_ap = Page(FakegodAssets.I_CLIMB_MODE_AP)
page_act_ap.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_ap->fakegod_act')

page_act_pass = Page(FakegodAssets.I_CLIMB_MODE_PASS)
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_pass->fakegod_act')

page_act_ap100 = Page(FakegodAssets.I_CLIMB_MODE_AP100)
page_act_ap100.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)

page_act_boss = Page(FakegodAssets.I_CHECK_BATTLE_BOSS)
page_act_boss.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_boss->fakegod_act')
page_act.connect(page_act_boss, FakegodAssets.I_TO_BATTLE_BOSS, key='fakegod_act->fakegod_boss')
