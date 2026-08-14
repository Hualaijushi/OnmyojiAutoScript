from tasks.Fakegod.assets import FakegodAssets
from tasks.GameUi.page import Page, page_activity
from tasks.GlobalGame.assets import GlobalGameAssets


page_act = page_activity

page_act_ap = Page(FakegodAssets.I_CLIMB_MODE_AP)
page_act_ap.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_ap->fakegod_act')

page_act_pass = Page(FakegodAssets.I_CLIMB_MODE_PASS)
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_pass->fakegod_act')

page_act_ap100 = Page(FakegodAssets.I_CLIMB_MODE_AP100)
page_act_ap100.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)

page_act_boss = Page(FakegodAssets.I_CHECK_BATTLE_BOSS)
page_act_boss.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_boss->fakegod_act')
page_act.connect(page_act_boss, FakegodAssets.I_TO_BATTLE_BOSS, key='fakegod_act->fakegod_boss')
