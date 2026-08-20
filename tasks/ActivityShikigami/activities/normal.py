"""当期爬塔独有页面与执行逻辑。"""

import random
import time

from module.logger import logger
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.ActivityShikigami.base_act import ActivityResourceNotEnough
import tasks.ActivityShikigami.page as pages


class NormalClimbAct:
    """体力、门票、首领和百体四种爬塔战斗。"""

    def setup_climb_pages(self):
        page_act = self.navigator.resolve_page(pages.page_act)
        page_pass = self.navigator.resolve_page(pages.page_climb_pass)
        page_ap = self.navigator.resolve_page(pages.page_climb_ap)

        page_act.connect(page_ap, ActivityShikigamiAssets.I_TO_BATTLE_MAIN, key='activity->climb_ap')
        page_ap.add_enter_failure_hooks(pages.conditional_action(
            condition=ActivityShikigamiAssets.I_CLIMB_MODE_PASS,
            action=ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH,
        ))
        page_act.connect(page_pass, ActivityShikigamiAssets.I_TO_BATTLE_MAIN, key='activity->climb_pass')
        page_pass.add_enter_failure_hooks(pages.conditional_action(
            condition=ActivityShikigamiAssets.I_CLIMB_MODE_AP,
            action=ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH,
        ))
        page_pass.connect(page_ap, ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH, key='climb_pass->climb_ap')
        page_ap.connect(page_pass, ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH, key='climb_ap->climb_pass')

    def run_climb(self):
        logger.hr('Start activity: Climb', 1)
        self.setup_climb_pages()
        for action_type in self.conf.general_config.climb_sequence_v:
            if self.time_limit_reached():
                return
            self._run_climb_type(action_type)

    def _run_climb_type(self, action_type: str):
        logger.hr(f'Start climb type: {action_type}', 2)
        self.current_action_type = action_type
        destination = getattr(pages, f'page_climb_{action_type}')
        self.goto_page(destination)
        self._sync_climb_team_lock(action_type)

        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if current_page == destination:
                if not self.prepare_next_action(action_type):
                    return
                try:
                    self._run_climb_action(action_type, destination)
                except ActivityResourceNotEnough:
                    logger.info(f'Climb resource exhausted: {action_type}')
                    return
                continue
            if current_page in (pages.page_battle_prepare, pages.page_battle):
                self.run_general_battle(
                    self.battle_config(action_type),
                    battle_key=f'activity_{action_type}',
                )
                continue
            if current_page == pages.page_reward:
                self.click(pages.random_click(ltrb=(False, False, True, False)), interval=1.5)
                continue
            if current_page is None:
                time.sleep(0.5)
                continue
            self.goto_page(destination)

    def _run_climb_action(self, action_type: str, destination):
        if not self._climb_resource_available(action_type):
            raise ActivityResourceNotEnough

        self.switch_soul_for(
            action_type,
            self.I_BATTLE_MAIN_TO_RECORDS,
            return_page=destination,
        )
        if self._climb_resource_needs_trial:
            self._climb_resource_needs_trial = False
            entered = self.verify_zero_ticket(
                f'ActivityShikigami {action_type} ticket',
                lambda: self._enter_climb_battle(action_type, max_times=1),
            )
        else:
            entered = self._enter_climb_battle(action_type)
        if not entered:
            raise ActivityResourceNotEnough

        self.record_action(action_type)
        self.run_general_battle(
            self.battle_config(action_type),
            battle_key=f'activity_{action_type}',
        )

    def _climb_fire_rule(self, action_type: str):
        return self.I_AS_BOSS_FIRE if action_type == 'boss' else self.I_ACT_FIRE

    def _enter_climb_battle(self, action_type: str, max_times: int | None = None) -> bool:
        click_times = 0
        fallback = max_times is not None
        max_times = max_times or random.randint(3, 5)
        fire_rule = self._climb_fire_rule(action_type)
        while True:
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if click_times >= max_times:
                logger.warning(f'{action_type} cannot enter battle, click reach max times')
                if fallback:
                    return False
                raise ActivityResourceNotEnough
            if self.appear(self.I_UI_BACK_RED, interval=1):
                logger.warning(f'{action_type} cannot enter battle, resource dialog appeared')
                if fallback:
                    return False
                raise ActivityResourceNotEnough
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1) or \
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(fire_rule, interval=1):
                self.device.click_record_clear()
                click_times += 1
                logger.info(f'Try click fire, remain times[{max_times - click_times}]')
                if fallback:
                    return self._wait_climb_trial_result(timeout=3.0)

    def _wait_climb_trial_result(self, timeout: float = 3.0) -> bool:
        """试探挑战后只观察战斗或两种不足界面，不继续点击。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if self.appear(self.I_UI_CONFIRM_SAMLL) or self.appear(self.I_UI_CONFIRM):
                return False
            if self.appear(self.I_UI_BACK_RED):
                return False
            time.sleep(0.2)
        logger.warning(f'{self.current_action_type} trial challenge timed out after {timeout:.1f}s')
        return False

    def _sync_climb_team_lock(self, action_type: str):
        enable = self.battle_config(action_type).lock_team_enable
        if action_type == 'boss':
            lock_rule, unlock_rule = self.I_LOCK, self.I_UNLOCK
        else:
            lock_rule, unlock_rule = self.I_AP_LOCK, self.I_AP_UNLOCK
        if enable:
            logger.info(f'Lock {action_type} team')
            self.ui_click(unlock_rule, stop=lock_rule, interval=1.5)
        else:
            logger.info(f'Unlock {action_type} team')
            self.ui_click(lock_rule, stop=unlock_rule, interval=1.5)

    def _climb_resource_available(self, action_type: str) -> bool:
        logger.hr(f'Check {action_type} resource')
        self.screenshot()
        self._climb_resource_needs_trial = False
        if action_type == 'pass':
            remain = self.O_REMAIN_PASS.ocr_digit(self.device.image)
        elif action_type == 'ap':
            remain = self.O_REMAIN_AP.ocr_quantity(self.device.image)
        elif action_type == 'boss':
            _, remain, _ = self.O_REMAIN_BOSS.ocr_digit_counter(self.device.image)
        else:
            remain = self.O_REMAIN_AP100.ocr_digit(self.device.image)

        if action_type in ('pass', 'boss') and remain <= 0:
            self._climb_resource_needs_trial = True
            return True
        previous = self.pre_resource_count[action_type]
        if previous - remain > 1:
            self.pre_resource_count[action_type] -= 1
            return True
        self.pre_resource_count[action_type] = remain
        return remain > 0
