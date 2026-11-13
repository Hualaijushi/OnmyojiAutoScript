"""单账号超鬼王界面适配，复用既有导航和战斗组件。"""

from __future__ import annotations

import time
from types import SimpleNamespace

from tasks.MetaDemon.config import MetaDemonConfig, MetaDemonSwitchSoulConfig
from tasks.MetaDemon.script_task import ScriptTask as MetaDemonTask
from tasks.MetaDemon import page as pages
from tasks.MetaDemonRotation.rental import deploy_rental
from tasks.MetaDemonRotation.rental_prompt import handle_rental_prompt


class RotationDriver(MetaDemonTask):
    """每个账号新建独立实例，避免共享原任务的类级状态。"""

    def __init__(self, config, device):
        super().__init__(config, device)
        self.State = SimpleNamespace(done=False, switch_soul_done=False, synthesis_done=False)
        self.cur_boss_type = None

    def deploy_rental(self, sequence: int) -> str:
        self.rotation_started = time.monotonic()
        self.before_run()
        # 仅修改当前驱动的内存副本，不写超鬼王配置或其他账号设置。
        self.conf = self.conf.model_copy(deep=True)
        play = self.config.meta_demon_rotation.rotation_play
        self.conf.meta_demon_config = MetaDemonConfig(**play.model_dump(exclude={'fatigue_wait_interval'}))
        self.conf.switch_soul = MetaDemonSwitchSoulConfig()
        self.goto_page(pages.page_meta_demon_boss)
        return deploy_rental(self, sequence)

    def fatigue_status(self) -> str:
        limit = self.conf.meta_demon_config.limit_time_v.total_seconds()
        if limit > 0 and time.monotonic() - self.rotation_started >= limit:
            return 'time_limit'
        self.screenshot()
        current, remain, total = self.O_MD_FATIGUE.ocr_digit_counter(self.device.image)
        if not (0 < total and 0 <= current <= total and remain == total - current):
            return 'unknown'
        return 'unavailable' if current >= total and not self.conf.meta_demon_config.auto_tea else 'ready'

    def prepare_current_or_four_star(self) -> str:
        self.synthesis_boss_ticket()
        if not self.check_and_switch_ticket(deadline=time.monotonic() + 60):
            self.screenshot()
            return 'four_unavailable' if self.appear(self.I_CHECK_BOSS_PAGE) else 'unknown'
        self.screenshot()
        if self.conf.meta_demon_config.powerful_list_v and self.appear(self.I_MD_FIRE):
            self.sync_current_boss_type()
        return 'four_ready' if self.check_and_switch_powerful() else 'unknown'

    def challenge(self, on_entered):
        confirm_attempted = False
        def popup_handler():
            nonlocal confirm_attempted
            prompt = handle_rental_prompt(self, confirm_attempted=confirm_attempted)
            if prompt == 'handled':
                confirm_attempted = True
            return prompt
        result = self.start_battle(on_entered=on_entered, popup_handler=popup_handler,
                                   rotation_mode=True, deadline=time.monotonic() + 45)
        if result != 'finished':
            return result if result in ('fatigue', 'popup_unknown') else False
        self.goto_page(pages.page_meta_demon_boss)
        self.screenshot()
        return bool(self.appear(self.I_CHECK_BOSS_PAGE))
