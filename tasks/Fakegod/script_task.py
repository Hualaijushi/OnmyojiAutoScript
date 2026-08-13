"""伪神降临独立任务。"""

from tasks.Fakegod.assets import FakegodAssets
from tasks.Fakegod.base_act import BaseAct
import tasks.Fakegod.page as pages
from tasks.GlobalGame.assets import GlobalGameAssets


class ScriptTask(BaseAct):
    """保留旧伪神活动的页面结构与爬塔执行逻辑。"""

    def before_run(self):
        super().before_run()
        page_act = self.navigator.resolve_page(pages.page_act)
        page_act_pass = self.navigator.resolve_page(pages.page_act_pass)
        page_act_ap = self.navigator.resolve_page(pages.page_act_ap)

        page_act_2 = self.navigator.add_page(pages.Page(
            FakegodAssets.I_AS_CHECK_MAIN_2,
            category='fakegod',
        ))
        page_act_2.add_enter_success_hooks(GlobalGameAssets.I_UI_BACK_RED)
        page_act.connect(page_act_2, FakegodAssets.I_TO_BATTLE_MAIN, key='fakegod_act->fakegod_act_2')
        page_act_2.connect(page_act, GlobalGameAssets.I_UI_BACK_CIRCLE, key='fakegod_act_2->fakegod_act')

        page_act_dark = self.navigator.add_page(pages.Page(
            FakegodAssets.I_AS_CLOSE_EYE,
            category='fakegod',
            priority=75,
        ))
        page_act_dark.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)
        page_act_dark.add_enter_success_hooks(FakegodAssets.I_AS_LOCATE)
        page_act_dark.connect(page_act, GlobalGameAssets.I_UI_BACK_CIRCLE, key='fakegod_dark->fakegod_act')
        page_act_2.connect(page_act_dark, FakegodAssets.I_AS_OPEN_EYE, key='fakegod_act_2->fakegod_dark')

        page_act_pass.connect(page_act_dark, GlobalGameAssets.I_UI_BACK_YELLOW, key='fakegod_pass->fakegod_dark')
        page_act_dark.connect(page_act_pass, FakegodAssets.I_AS_TO_PASS, key='fakegod_dark->fakegod_pass')
        page_act.connect(page_act_ap, FakegodAssets.I_TO_BATTLE_AP, key='fakegod_act->fakegod_ap')

        pages.page_act_ap100.connect(
            page_act_dark,
            GlobalGameAssets.I_UI_BACK_YELLOW,
            key='fakegod_ap100->fakegod_dark',
        )
        page_act_dark.connect(
            pages.page_act_ap100,
            FakegodAssets.O_ENTER_AP100,
            key='fakegod_dark->fakegod_ap100',
        )
