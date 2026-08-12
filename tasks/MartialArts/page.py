"""武道大会页面图：庭院 -> 武道大会主页 -> 日常训练。"""

import time

from module.exception import GamePageUnknownError
from module.logger import logger
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.GameUi.action import conditional_action
from tasks.GameUi.default_pages import random_click
from tasks.GameUi.page import Page, page_main, page_shikigami_records
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.MartialArts.assets import MartialArtsAssets


ACTIVITY_COLUMN_SWITCH_MAX_TRIES = 8


def find_martial_arts_entry(task) -> bool:
    """循环切换庭院右侧活动栏目，直到武道大会入口出现。"""
    switched = 0
    for _ in range(ACTIVITY_COLUMN_SWITCH_MAX_TRIES):
        task.screenshot()
        if task.appear(MartialArtsAssets.I_MAIN_GOTO_MAR):
            return True
        if task.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=0.5):
            switched += 1
        time.sleep(0.5)

    task.screenshot()
    if task.appear(MartialArtsAssets.I_MAIN_GOTO_MAR):
        return True

    logger.warning(
        f'MartialArts entry not found after switching columns '
        f'{switched} times ({ACTIVITY_COLUMN_SWITCH_MAX_TRIES} checks)'
    )
    raise GamePageUnknownError(
        f'Cannot find MartialArts entry after '
        f'{ACTIVITY_COLUMN_SWITCH_MAX_TRIES} column switches'
    )


# 武道大会主页
page_martial_arts = Page(MartialArtsAssets.I_CHECK_MAIN_MAR)
page_martial_arts.add_enter_failure_hooks(
    find_martial_arts_entry,
    conditional_action(GlobalGameAssets.I_UI_REWARD, random_click),
    GlobalGameAssets.I_UI_BACK_RED,
)
page_martial_arts.connect(page_main, GlobalGameAssets.I_UI_BACK_YELLOW,
                          key="page_martial_arts->page_main")
page_main.connect(page_martial_arts, MartialArtsAssets.I_MAIN_GOTO_MAR,
                  key="page_main->page_martial_arts")

# 日常训练（体力战斗）页面
page_martial_arts_ap = Page(MartialArtsAssets.I_CHECK_BATTLE_AP)
page_martial_arts_ap.connect(page_martial_arts, GlobalGameAssets.I_UI_BACK_YELLOW,
                             key="page_martial_arts_ap->page_martial_arts")
page_martial_arts.connect(page_martial_arts_ap, MartialArtsAssets.I_TO_BATTLE_AP,
                          key="page_martial_arts->page_martial_arts_ap")

# 修行合训（首领地图）页面
page_martial_arts_boss = Page(MartialArtsAssets.I_CHECK_BATTLE_BOSS)
page_martial_arts_boss.connect(page_martial_arts, GlobalGameAssets.I_UI_BACK_YELLOW,
                               key="page_martial_arts_boss->page_martial_arts")
page_martial_arts.connect(page_martial_arts_boss, MartialArtsAssets.I_TO_BATTLE_BOSS,
                          key="page_martial_arts->page_martial_arts_boss")

# 搜寻首领后的战斗小界面
page_martial_arts_boss_main = Page(MartialArtsAssets.I_CHECK_BATTLE_BOSS_MAIN)
page_martial_arts_boss_main.connect(
    page_martial_arts_boss,
    MartialArtsAssets.I_BOSS_MAIN_GOTO_BOSS,
    key="page_martial_arts_boss_main->page_martial_arts_boss",
)

# 战斗小界面进入式神录切换御魂，返回键回到战斗小界面。
page_martial_arts_boss_main.connect(
    page_shikigami_records,
    MartialArtsAssets.I_BATTLE_BOSS_TO_RECORDS,
    key="page_martial_arts_boss_main->page_shikigami_records",
    cost=2,
)
page_shikigami_records.connect(
    page_martial_arts_boss_main,
    GlobalGameAssets.I_UI_BACK_YELLOW,
    key="page_shikigami_records->page_martial_arts_boss_main",
    cost=2,
)
