"""大富翁独有棋盘流程。"""

import random
import time

from module.exception import GameStuckError
from module.logger import logger
from tasks.ActivityShikigami.base_act import ActivityResourceNotEnough
import tasks.ActivityShikigami.page as pages


RICHMAN_ENTRY_SETTLE_SECONDS = 3.0


class RichManAct:
    def setup_rich_man_pages(self):
        page_act = self.navigator.resolve_page(pages.page_act)
        page_board = self.navigator.resolve_page(pages.page_rich_man)

        def enter_board(task) -> bool:
            logger.info(f'Wait {RICHMAN_ENTRY_SETTLE_SECONDS:.1f}s for RichMan activity overlays')
            time.sleep(RICHMAN_ENTRY_SETTLE_SECONDS)
            if not pages.handle_activity_overlay(task):
                return False
            task.screenshot()
            return task.appear_then_click(task.I_RM_TO_BATTLE_MAIN, interval=0)

        page_act.connect(page_board, enter_board, key='activity->rich_man')

    def run_rich_man(self):
        logger.hr('Start activity: RichMan', 1)
        self.setup_rich_man_pages()
        self.goto_page(pages.page_rich_man)
        common_loadout_required = True
        self._boss_pending = False
        self._boss_wait_exp_reset = False
        self._boss_max_level = False

        try:
            while True:
                self.screenshot()
                if self.ui_reward_appear_click():
                    continue
                if self.appear_then_click(self.I_UI_CONFIRM, interval=2):
                    continue

                if not self.appear(self.I_RM_THROW):
                    time.sleep(0.3)
                    continue
                if self._sync_rich_man_team_lock(switch_loadout=common_loadout_required):
                    continue

                if self._boss_should_enter():
                    self._run_rich_man_boss_fight(switch_loadout=common_loadout_required)
                    common_loadout_required = False
                    self._boss_pending = False
                    self._boss_wait_exp_reset = True
                    continue

                # 全局时间与随机休眠都只在真正开始下一次掷骰子前生效。
                if not self.prepare_next_action('rich_man'):
                    return

                dice_count = self.O_CINQUE_COUNT.ocr_digit(self.device.image)
                logger.info(f'RichMan dice count before throw: {dice_count}')
                if not self.appear_then_click(self.I_RM_THROW, interval=2):
                    continue

                logger.hr('Throw ticket', 3)
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                mode = self._wait_for_dice_count_change(dice_count)
                self.record_action('rich_man')
                if mode is None:
                    mode = self._wait_for_mode_after_throw()
                if mode == 'throw':
                    self._run_throw_task()
                elif mode == 'rob':
                    self._run_rob_task()
                elif mode == 'fight':
                    self._run_rich_man_fight(switch_loadout=common_loadout_required)
                    common_loadout_required = False
        except ActivityResourceNotEnough:
            logger.info('RichMan dice exhausted')

    def _read_level_experience(self) -> tuple[int, int] | None:
        current, _, total = self.O_LEVEL_EXPERIENCE.ocr_digit_counter(self.device.image)
        if total <= 0:
            logger.warning(f'Invalid RichMan level experience OCR: {current}/{total}')
            return None
        logger.info(f'RichMan level experience: {current}/{total}')
        return current, total

    def _boss_level_is_max(self) -> bool:
        if self._boss_max_level:
            return True
        current, _, total = self.O_LEVEL.ocr_digit_counter(self.device.image)
        logger.info(f'RichMan level: {current}/{total}')
        if current == 10 and total == 10:
            logger.info('RichMan max level reached, disable subsequent boss challenges')
            self._boss_max_level = True
            self._boss_pending = False
            self._boss_wait_exp_reset = False
            return True
        return False

    def _confirm_boss_experience_overflow(self) -> bool:
        first = self._read_level_experience()
        if first is None or first[0] <= first[1]:
            return False
        time.sleep(0.3)
        self.screenshot()
        second = self._read_level_experience()
        if second != first:
            logger.warning(f'RichMan boss experience confirmation mismatch: {first} -> {second}')
            return False
        logger.info(f'RichMan boss challenge pending at experience {first[0]}/{first[1]}')
        return True

    def _boss_anchor_appear(self) -> bool:
        return self.appear(self.I_RM_FITGHT_ANCHOR)

    def _boss_should_enter(self) -> bool:
        if self._boss_level_is_max():
            return False
        if self._boss_wait_exp_reset:
            experience = self._read_level_experience()
            if experience is not None and experience[0] <= experience[1]:
                logger.info('RichMan boss experience reset confirmed')
                self._boss_wait_exp_reset = False
            return False
        if not self._boss_pending:
            self._boss_pending = self._confirm_boss_experience_overflow()
        if not self._boss_pending:
            return False
        if self._boss_anchor_appear():
            logger.info(f'RichMan boss anchor found at {self.I_RM_FITGHT_ANCHOR.roi_front}')
            return True
        logger.info('RichMan boss pending, anchor is outside its roi_back or not visible')
        return False

    def _wait_for_dice_count_change(self, previous_count: int) -> str | None:
        deadline = time.monotonic() + 5.0
        zero_fallback = previous_count == 0
        while True:
            self.screenshot()
            if self.appear(self.I_CINQUE_NOT_ENOUGH):
                logger.warning('RichMan dice not enough prompt appeared')
                self.click(self.C_RM_RANDOM_CLOSE_SAFE_MAIN, interval=1)
                self.device.click_record_clear()
                raise ActivityResourceNotEnough

            current_count = self.O_CINQUE_COUNT.ocr_digit(self.device.image)
            if current_count != previous_count:
                logger.info(f'RichMan dice count changed: {previous_count} -> {current_count}')
                self.device.click_record_clear()
                return None
            if zero_fallback:
                mode = self._detect_richman_mode()
                if mode is not None:
                    logger.info('RichMan throw succeeded although initial dice OCR was zero')
                    self.device.click_record_clear()
                    return mode
            if time.monotonic() >= deadline:
                if self.appear_then_click(self.I_RM_THROW, interval=2):
                    logger.info('Dice count did not change, click throw again')
                else:
                    logger.info('RichMan is moving, continue waiting for dice count change')
                deadline = time.monotonic() + 5.0
            time.sleep(0.3)

    def _detect_richman_mode(self) -> str | None:
        if self.appear(self.I_RM_MODE_THROW):
            return 'throw'
        if self.appear(self.I_RM_MODE_ROB):
            return 'rob'
        if self.appear(self.I_RM_MODE_FIGHT):
            return 'fight'
        return None

    def _wait_for_mode_after_throw(self) -> str:
        deadline = time.monotonic() + 5.0
        while True:
            self.screenshot()
            mode = self._detect_richman_mode()
            if mode is not None:
                return mode
            if time.monotonic() >= deadline:
                if self.appear_then_click(self.I_RM_THROW, interval=2):
                    logger.info('RichMan mode wait timed out, may be reward block')
                else:
                    logger.info('RichMan is moving, continue waiting for mode')
                deadline = time.monotonic() + 5.0
            time.sleep(0.3)

    def _run_throw_task(self):
        logger.hr('RichMan throw task', 3)
        deadline = time.monotonic() + 20.0
        attempt = 0
        while True:
            if time.monotonic() >= deadline:
                raise GameStuckError('RichMan throw mode timed out after 20 seconds')
            self.screenshot()
            if self.appear(self.I_RM_THROW):
                logger.info(f'RichMan throw task finished after {attempt} attempt(s)')
                return
            if self.appear(self.I_RM_MODE_THROW) and \
                    self.appear_then_click(self.I_RM_THROW_FIGHT, interval=1):
                attempt += 1
                continue
            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1) or \
                    self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            time.sleep(0.5)

    def _run_rob_task(self):
        logger.hr('RichMan rob task', 3)
        choice = random.choice([
            self.C_RM_ROB_CHOICE_1,
            self.C_RM_ROB_CHOICE_2,
            self.C_RM_ROB_CHOICE_3,
            self.C_RM_ROB_CHOICE_4,
        ])
        self.click(choice)
        deadline = time.monotonic() + 10.0
        while True:
            if time.monotonic() >= deadline:
                raise GameStuckError('RichMan rob mode timed out after 10 seconds')
            self.screenshot()
            if self.appear(self.I_RM_THROW):
                return
            time.sleep(0.3)

    def _run_rich_man_fight(self, switch_loadout: bool):
        logger.hr('RichMan fight task', 3)
        if switch_loadout:
            self.switch_soul_for(
                'rich_man',
                self.I_RM_FIGHT_GOTO_RECORDS,
                exit_records=True,
            )
        source = self.battle_config('rich_man')
        battle = source.copy(update={
            'lock_team_enable': False,
            'preset_enable': source.preset_enable and switch_loadout,
            'continuous_battle': False,
            'max_continuous': 0,
        })
        self._click_rich_man_challenge(self.I_RM_MODE_FIGHT, mode='normal')
        self.run_general_battle(
            battle,
            battle_key=f'rich_man_fight_{self.action_count["rich_man"]}',
            exit_matcher=self.I_RM_THROW,
        )
        self._wait_until_throw()

    def _run_rich_man_boss_fight(self, switch_loadout: bool):
        logger.hr('RichMan boss fight task', 3)
        self._enter_boss_fight_by_anchor()
        if switch_loadout:
            self.switch_soul_for(
                'rich_man',
                self.I_RM_FIGHT_BOSS_GOTO_RECORDS,
                exit_records=True,
            )
        source = self.battle_config('rich_man')
        battle = source.copy(update={
            'lock_team_enable': False,
            'preset_enable': source.preset_enable and switch_loadout,
            'continuous_battle': False,
            'max_continuous': 0,
        })
        self._click_rich_man_challenge(self.I_RM_MODE_FIGHT_BOSS, mode='boss')
        self.run_general_battle(
            battle,
            battle_key=f'rich_man_boss_{time.monotonic_ns()}',
            exit_matcher=self.I_RM_THROW,
        )
        self._close_boss_level_up()

    def _close_boss_level_up(self):
        level_up_seen = False
        while True:
            self.screenshot()
            if self.appear(self.I_LEVEL_UP):
                level_up_seen = True
                self.click(self.C_RM_RANDOM_CLOSE_SAFE, interval=1)
                continue
            if level_up_seen:
                return
            time.sleep(0.3)

    def _enter_boss_fight_by_anchor(self):
        for attempt in range(1, 3):
            self.screenshot()
            if self.appear(self.I_RM_MODE_FIGHT_BOSS):
                return
            if not self._boss_anchor_appear():
                time.sleep(0.3)
                continue
            x, y, width, height = self.I_RM_FITGHT_ANCHOR.roi_front
            click_x = max(0, min(1279, x + width // 2))
            click_y = max(0, min(719, y + height // 2 - 70))
            self.device.click(x=click_x, y=click_y, control_name='rm_boss_fight_dynamic_enter')
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                self.screenshot()
                if self.appear(self.I_RM_MODE_FIGHT_BOSS):
                    return
                time.sleep(0.3)
        raise GameStuckError('RichMan boss entry failed after 2 dynamic click attempts')

    def _click_rich_man_challenge(self, challenge_button, mode: str):
        self.screenshot()
        if self.appear_then_click(challenge_button):
            logger.info(f'Click RichMan {mode} fight challenge')
        else:
            logger.warning(f'RichMan {mode} fight challenge button not found')

    def _sync_rich_man_team_lock(self, switch_loadout: bool) -> bool:
        conf = self.battle_config('rich_man')
        should_lock = conf.lock_team_enable and not (conf.preset_enable and switch_loadout)
        self.screenshot()
        if should_lock:
            if self.appear(self.I_RM_MAIN_LOCK):
                return False
            if self.appear(self.I_RM_MAIN_UNLOCK):
                self.ui_click(self.I_RM_MAIN_UNLOCK, stop=self.I_RM_MAIN_LOCK, interval=1)
                return True
        else:
            if self.appear(self.I_RM_MAIN_UNLOCK):
                return False
            if self.appear(self.I_RM_MAIN_LOCK):
                self.ui_click(self.I_RM_MAIN_LOCK, stop=self.I_RM_MAIN_UNLOCK, interval=1)
                return True
        logger.warning('RichMan main team lock status not detected')
        return False

    def _wait_until_throw(self):
        while True:
            self.screenshot()
            if self.appear(self.I_RM_THROW):
                return
            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1) or \
                    self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            time.sleep(0.5)
