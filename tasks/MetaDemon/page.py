"""超鬼王独立页面与庭院直达入口。"""

import time

from module.base.timer import Timer
from module.exception import GamePageUnknownError
from module.interaction_policy import InteractionPolicy
from module.logger import logger
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.GameUi.page import (
    Page,
    page_battle,
    page_battle_prepare,
    page_battle_result,
    page_main,
    page_reward,
    page_shikigami_records,
    random_click,
)
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.MetaDemon.assets import MetaDemonAssets


ACTIVITY_COLUMN_SWITCH_MAX_TRIES = 8
ACTIVITY_ENTRY_FALLBACK_TIMEOUT = 20
ACTIVITY_AUXILIARY_SETTLE_SECONDS = 1.0


def _activity_entry_visible(task) -> bool:
    """仅识别超鬼王自己的入口模板，不借用式神活动运行期资源。"""
    return (task.appear(MetaDemonAssets.I_MAIN_GOTO_ACT_2)
            or task.appear(MetaDemonAssets.I_MAIN_GOTO_ACT))


def goto_activity_entry(task) -> bool:
    """庭院优先点击直达入口，再尝试备用入口；点击成功不等于到达活动页。"""
    if not task.appear(task.I_CHECK_MAIN):
        return False
    if task.appear_then_click(
            MetaDemonAssets.I_MAIN_GOTO_ACT_2, interval=1,
            policy=InteractionPolicy.NAVIGATION):
        return True
    if not task.appear(task.I_CHECK_MAIN):
        return False
    if task.appear_then_click(
            MetaDemonAssets.I_MAIN_GOTO_ACT, interval=1,
            policy=InteractionPolicy.NAVIGATION):
        return True
    logger.info('MetaDemon: 庭院入口未命中，等待右侧栏目查找')
    return False


def find_activity_entry(task) -> bool:
    """在庭院右侧栏目内有界查找，离开庭院立即交回导航器。

    与式神活动采用相同的次数与时间预算。时间预算只在调用返回后检查，
    不能中断底层截图或识别阻塞；栏目切换前用新帧确认页面与按钮。
    """
    timer = Timer(ACTIVITY_ENTRY_FALLBACK_TIMEOUT).start()
    need_screenshot = True
    for _ in range(ACTIVITY_COLUMN_SWITCH_MAX_TRIES):
        if timer.reached():
            raise GamePageUnknownError('超鬼王庭院入口查找超时')
        if need_screenshot:
            task.screenshot()
        need_screenshot = True
        if not task.appear(task.I_CHECK_MAIN):
            return False
        if _activity_entry_visible(task):
            return True
        if not task.appear(RightActivityAssets.I_TOGGLE_BUTTON):
            time.sleep(0.5)
            continue

        time.sleep(ACTIVITY_AUXILIARY_SETTLE_SECONDS)
        task.screenshot()
        if timer.reached():
            raise GamePageUnknownError('超鬼王庭院入口查找超时')
        if not task.appear(task.I_CHECK_MAIN):
            return False
        if _activity_entry_visible(task):
            return True
        if not task.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=0):
            continue
        task.screenshot()
        need_screenshot = False
        if not task.appear(task.I_CHECK_MAIN):
            return False
        if _activity_entry_visible(task):
            return True

    task.screenshot()
    if not task.appear(task.I_CHECK_MAIN):
        return False
    if _activity_entry_visible(task):
        return True
    raise GamePageUnknownError('切换庭院栏目后仍未找到超鬼王入口')


page_meta_demon = Page(MetaDemonAssets.I_MD_CHECK_MAIN_PAGE)
page_meta_demon.add_enter_success_hooks(MetaDemonAssets.I_MD_GET_YESTERDAY_REWARD, MetaDemonAssets.I_MD_CLOSE_POPUP)
page_meta_demon.add_enter_failure_hooks(find_activity_entry)
page_meta_demon.connect(page_main, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_meta_demon->page_main")
page_main.connect(page_meta_demon, goto_activity_entry, key="page_main->page_meta_demon")

page_meta_demon_boss = Page(MetaDemonAssets.I_CHECK_BOSS_PAGE)
page_meta_demon_boss.add_enter_success_hooks(MetaDemonAssets.I_MD_CLOSE_POPUP)
page_meta_demon_boss.connect(page_meta_demon, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_meta_demon_boss->page_meta_demon")
page_meta_demon.connect(page_meta_demon_boss, MetaDemonAssets.I_MD_GOTO_BOSS, key="page_meta_demon->page_meta_demon_boss")

page_reward.connect(page_meta_demon_boss, random_click(), key="page_reward->page_meta_demon_boss")
page_battle_result.connect(page_meta_demon_boss, random_click(), key="page_battle_result->page_meta_demon_boss")
