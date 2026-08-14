"""大富翁独立页面导航。"""

from tasks.GameUi.page import Page, page_activity
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.RichMan.assets import RichManAssets


page_act = page_activity

page_act_pass = Page(RichManAssets.I_CHECK_RM_RICHMAN)
page_act_pass.connect(page_act, GlobalGameAssets.I_UI_BACK_YELLOW, key='rich_man_pass->rich_man_act')
page_act.connect(page_act_pass, RichManAssets.I_TO_BATTLE_MAIN, key='rich_man_act->rich_man_pass')
