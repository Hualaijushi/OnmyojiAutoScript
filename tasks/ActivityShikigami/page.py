from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.GameUi.page import (
    Page,
    all_of,
    any_of,
    conditional_action,
    page_activity,
    page_battle,
    page_battle_prepare,
    page_battle_result,
    page_main,
    page_reward,
    random_click,
)
from tasks.GlobalGame.assets import GlobalGameAssets


# 活动主界面统一由 GameUi 定义。
page_act = page_activity
# 体力爬塔页面
page_act_ap = Page(all_of(ActivityShikigamiAssets.I_CHECK_BATTLE_PASS,
                          ActivityShikigamiAssets.I_CLIMB_MODE_AP))
page_act_ap.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_act_ap->page_act")
# 门票爬塔页面
page_act_pass = Page(all_of(ActivityShikigamiAssets.I_CHECK_BATTLE_PASS,
                            ActivityShikigamiAssets.I_CLIMB_MODE_PASS))
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_act_pass->page_act")
# 100体爬塔页面
page_act_ap100 = Page(ActivityShikigamiAssets.I_CLIMB_MODE_AP100)
page_act_ap100.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)
# BOSS爬塔页面
page_act_boss = Page(ActivityShikigamiAssets.I_AS_BOSS_FIRE)
page_act_boss.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_act_boss->page_act")
page_act.connect(page_act_boss, ActivityShikigamiAssets.I_TO_BATTLE_BOSS, key="page_act->page_act_boss")
