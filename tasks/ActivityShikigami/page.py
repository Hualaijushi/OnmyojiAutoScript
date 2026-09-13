"""式神活动统一页面定义。"""

import random
import time

from module.base.timer import Timer
from module.exception import GamePageUnknownError
from module.logger import logger
from module.reaction_profile import REACTION_NAVIGATION
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.GameUi.page import (
    Page,
    all_of,
    any_of,
    conditional_action,
    page_battle,
    page_battle_prepare,
    page_battle_result,
    page_main,
    page_reward,
    page_shikigami_records,
    random_click,
)
from tasks.GlobalGame.assets import GlobalGameAssets


ACTIVITY_COLUMN_SWITCH_MAX_TRIES = 8
ACTIVITY_AUXILIARY_SETTLE_SECONDS = 1.0


def _settle_activity_auxiliary(task):
    """附属界面出现后等待一秒，再用新截图确认并处理。"""
    time.sleep(ACTIVITY_AUXILIARY_SETTLE_SECONDS)
    task.screenshot()


def _activity_entry_visible(task) -> bool:
    """本期活动入口图标是否可见：优先当期 `I_MAIN_GOTO_ACT_2`，旧图标 `I_MAIN_GOTO_ACT`
    作跨活动周期兼容回退（两者都在 `assets.py` 里，旧图标不机械删除）。"""
    return (task.appear(ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2)
            or task.appear(ActivityShikigamiAssets.I_MAIN_GOTO_ACT))


def goto_activity_entry(task) -> bool:
    """庭院 → 本期式神活动页的边动作。优先点当期入口图标 `main_goto_act_2`，旧图标作回退；
    每次 delay 后 fresh 二次确认目标仍在才点（`REACTION_NAVIGATION`）。入口图标消失本身
    **不**代表进入活动成功——是否真正进入仍由 `page_act` 的 positive marker 判定。"""
    if task.appear_then_click(
            ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2, interval=1,
            confirm_delay=REACTION_NAVIGATION):
        return True
    return task.appear_then_click(
        ActivityShikigamiAssets.I_MAIN_GOTO_ACT, interval=1,
        confirm_delay=REACTION_NAVIGATION)


def find_activity_entry(task) -> bool:
    """在庭院右侧栏目中寻找本期式神活动入口。"""
    switched = 0
    for _ in range(ACTIVITY_COLUMN_SWITCH_MAX_TRIES):
        task.screenshot()
        if not task.appear(task.I_CHECK_MAIN):
            return False
        if _activity_entry_visible(task):
            return True
        if task.appear(RightActivityAssets.I_TOGGLE_BUTTON):
            _settle_activity_auxiliary(task)
            if task.appear_then_click(RightActivityAssets.I_TOGGLE_BUTTON, interval=0):
                switched += 1
        time.sleep(0.5)

    task.screenshot()
    if _activity_entry_visible(task):
        return True
    logger.warning(
        f'ActivityShikigami entry not found after switching columns {switched} times '
        f'({ACTIVITY_COLUMN_SWITCH_MAX_TRIES} checks)'
    )
    raise GamePageUnknownError('Cannot find ActivityShikigami entry')


def handle_activity_reward(task) -> bool:
    if not task.appear(GlobalGameAssets.I_UI_REWARD):
        return False
    _settle_activity_auxiliary(task)
    if not task.appear(GlobalGameAssets.I_UI_REWARD):
        return False
    click = random_click()
    logger.info(f'Clear activity reward page via {click.name}')
    task.click(click, interval=0)
    task.device.click_record_clear()
    return True


def handle_activity_close(task) -> bool:
    if not task.appear(GlobalGameAssets.I_UI_BACK_RED):
        return False
    _settle_activity_auxiliary(task)
    return task.appear_then_click(GlobalGameAssets.I_UI_BACK_RED, interval=0)


def handle_activity_story(task) -> bool:
    """处理剧情跳过按钮及其确认页面，两次操作前分别等待一秒。"""
    if task.appear(ActivityShikigamiAssets.I_SKIP_BUTTON):
        _settle_activity_auxiliary(task)
        if not task.appear_then_click(ActivityShikigamiAssets.I_SKIP_BUTTON, interval=0):
            return False
        task.device.click_record_clear()
        time.sleep(ACTIVITY_AUXILIARY_SETTLE_SECONDS)
        task.screenshot()
        if task.appear_then_click(ActivityShikigamiAssets.I_CONFIRM_SKIP, interval=0):
            task.device.click_record_clear()
        return True
    if task.appear(ActivityShikigamiAssets.I_CONFIRM_SKIP):
        _settle_activity_auxiliary(task)
        return task.appear_then_click(ActivityShikigamiAssets.I_CONFIRM_SKIP, interval=0)
    return False


def handle_activity_overlay(task) -> bool:
    """清理活动奖励、签到等附属页面，并等待活动主页稳定。"""
    timer = Timer(15).start()
    award_clicked = False
    while not timer.reached():
        task.screenshot()

        if task.appear(ActivityShikigamiAssets.I_ACTIVITY_AWARD):
            if not award_clicked:
                _settle_activity_auxiliary(task)
                if task.appear(ActivityShikigamiAssets.I_ACTIVITY_AWARD):
                    click = random_click()
                    logger.info(f'Clear activity award overlay via {click.name}')
                    task.click(click, interval=0)
                    task.device.click_record_clear()
                    award_clicked = True
            time.sleep(0.2)
            continue

        if task.appear(ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE):
            _settle_activity_auxiliary(task)
            if task.appear_then_click(ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE, interval=0):
                logger.info('Close activity sign-in overlay')
                task.device.click_record_clear()
            time.sleep(0.2)
            continue

        if task.appear(ActivityShikigamiAssets.I_CHECK_BATTLE_MAIN):
            # 主界面标志可能先于延迟弹窗出现，等待一秒后再确认稳定。
            _settle_activity_auxiliary(task)
            if task.appear(ActivityShikigamiAssets.I_ACTIVITY_AWARD) or \
                    task.appear(ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE):
                continue
            if task.appear(ActivityShikigamiAssets.I_CHECK_BATTLE_MAIN):
                logger.info('ActivityShikigami main page ready')
                return True

        time.sleep(0.2)

    logger.warning('ActivityShikigami overlays did not finish within 15s')
    return False


# 活动主页和附属弹窗均由本任务自行识别、进入和处理。
page_act = Page(
    any_of(
        ActivityShikigamiAssets.I_CHECK_BATTLE_MAIN,
        ActivityShikigamiAssets.I_ACTIVITY_AWARD,
        ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE,
    ),
    priority=70,
)
page_act.add_enter_success_hooks(handle_activity_overlay)
page_act.add_enter_failure_hooks(
    find_activity_entry,
    handle_activity_reward,
    handle_activity_close,
    handle_activity_story,
)
page_act.connect(page_main, GlobalGameAssets.I_UI_BACK_YELLOW, key='activity->main')
page_main.connect(page_act, goto_activity_entry, key='main->activity')

# 本期普通爬塔的「二层入口」中间页（活动主页点第一次「进入爬塔」后到达）。
# 该页面自己的可靠 positive marker = `I_TO_BATTLE_MAIN_2`（「战斗·<本期名>」进入按钮，是这个
# 页面上稳定存在的元素，不是靠「上一页按钮消失」判断）。它同时是 `page_climb_main -> page_climb_*`
# 的边动作。旧活动是一层入口（无此中间页）；本期结构见 `docs/DECISIONS.md` D001「§4.62」补记。
page_climb_main = Page(ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2)
page_climb_main.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='climb_main->activity')

# 真正的普通爬塔战斗页。本期标题横幅换成 `I_CHECK_BATTLE_PASS_2`，旧 `I_CHECK_BATTLE_PASS`
# 作跨活动周期兼容回退（`any_of` 二选一）；仍要求同时命中对应 mode 标志（`all_of`），保证
# 中间页 / 其它页不会被误判成真正爬塔页。
page_climb_ap = Page(all_of(
    any_of(
        ActivityShikigamiAssets.I_CHECK_BATTLE_PASS_2,
        ActivityShikigamiAssets.I_CHECK_BATTLE_PASS,
    ),
    ActivityShikigamiAssets.I_CLIMB_MODE_AP,
))
page_climb_ap.connect(page_climb_main, GlobalGameAssets.I_UI_BACK_YELLOW, key='climb_ap->climb_main')

page_climb_pass = Page(all_of(
    any_of(
        ActivityShikigamiAssets.I_CHECK_BATTLE_PASS_2,
        ActivityShikigamiAssets.I_CHECK_BATTLE_PASS,
    ),
    ActivityShikigamiAssets.I_CLIMB_MODE_PASS,
))
page_climb_pass.connect(page_climb_main, GlobalGameAssets.I_UI_BACK_YELLOW, key='climb_pass->climb_main')

page_climb_ap100 = Page(ActivityShikigamiAssets.I_CLIMB_MODE_AP100)
page_climb_ap100.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)

page_climb_boss = Page(ActivityShikigamiAssets.I_AS_BOSS_FIRE)
page_climb_boss.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='climb_boss->activity')
page_act.connect(page_climb_boss, ActivityShikigamiAssets.I_TO_BATTLE_BOSS, key='activity->climb_boss')

# 大富翁棋盘。
page_rich_man = Page(ActivityShikigamiAssets.I_CHECK_RM_RICHMAN)
page_rich_man.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='rich_man->activity')

# 伪神降临沿用旧素材作为占位；下次复刻时整体替换 fakegod 子目录。
page_fakegod_action = Page(ActivityShikigamiAssets.I_FG_CLIMB_MODE_PASS)
page_fakegod_action.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_action->activity')
