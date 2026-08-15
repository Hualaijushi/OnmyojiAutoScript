# This Python file uses the following encoding: utf-8
"""大富翁棋盘任务。"""

import random
import time

from cached_property import cached_property

from module.exception import GameStuckError
from module.logger import logger
from tasks.RichMan.base_act import BaseAct, TicketsNotEnough
from tasks.RichMan.config import RichMan


class ScriptTask(BaseAct):

    @cached_property
    def conf(self) -> RichMan:
        return self.config.model.rich_man

    @property
    def scheduled_task_name(self) -> str:
        return 'RichMan'

    def _run_pass(self):
        logger.hr('Start RichMan', 1)
        normal_loadout_required = True
        self._boss_pending = False
        self._boss_wait_exp_reset = False
        while True:
            self.screenshot()
            self.update_status()

            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=2):
                continue

            if self.appear(self.I_RM_THROW):
                # 经验溢出后进入待挑战状态；仅当锚点进入指定范围才插入首领战。
                if self._boss_should_enter():
                    self._run_boss_fight_task()
                    self._boss_pending = False
                    self._boss_wait_exp_reset = True
                    # 首领战会换成首领御魂/预设，下一次普通战需要恢复普通装配。
                    normal_loadout_required = True
                    continue

                dice_count = self.O_CINQUE_COUNT.ocr_digit(self.device.image)
                logger.info(f'RichMan dice count before throw: {dice_count}')
                if not self.appear_then_click(self.I_RM_THROW, interval=2):
                    continue

                logger.hr('Throw ticket', 3)
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')

                # 先确认骰子数量发生变化，再衔接原有三模式检测。
                mode = self._wait_for_dice_count_change(dice_count)
                self.count_map[self.climb_type] += 1
                if mode is None:
                    mode = self._wait_for_mode_after_throw()
                if mode == 'throw':
                    self._run_throw_task()
                    continue
                if mode == 'rob':
                    self._run_rob_task()
                    continue
                if mode == 'fight':
                    self._run_fight_task(switch_loadout=normal_loadout_required)
                    normal_loadout_required = False
                    continue

    def _read_level_experience(self) -> tuple[int, int] | None:
        """读取等级经验 a/b；无有效分母时视为 OCR 失败。"""
        current, _, total = self.O_LEVEL_EXPERIENCE.ocr_digit_counter(self.device.image)
        if total <= 0:
            logger.warning(f'Invalid RichMan level experience OCR: {current}/{total}')
            return None
        logger.info(f'RichMan level experience: {current}/{total}')
        return current, total

    def _confirm_boss_experience_overflow(self) -> bool:
        """二次确认经验 a>b，避免单帧 OCR 误判触发首领战。"""
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
        """使用 anchor 自身的 roi_back 搜索动态起点锚点。"""
        return self.appear(self.I_RM_FITGHT_ANCHOR)

    def _boss_should_enter(self) -> bool:
        """维护首领待挑战/经验复位状态，并判断本轮是否进入首领战。"""
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
        """等待投骰消耗生效；初始读数为零时仅试投一次进行保底确认。"""
        timeout = 5.0
        deadline = time.monotonic() + timeout
        zero_fallback = previous_count == 0
        current_count = previous_count

        while True:
            self.screenshot()
            current_count = self.O_CINQUE_COUNT.ocr_digit(self.device.image)
            if current_count != previous_count:
                logger.info(f'RichMan dice count changed: {previous_count} -> {current_count}')
                return None

            # 初始 OCR 为零时，模式已经出现也能证明试投实际成功。
            if zero_fallback:
                mode = self._detect_richman_mode()
                if mode is not None:
                    logger.info('RichMan throw succeeded although initial dice OCR was zero')
                    return mode

            if time.monotonic() >= deadline:
                self.update_status()
                if zero_fallback and current_count == 0:
                    logger.warning('RichMan dice count remains zero after fallback throw')
                    raise TicketsNotEnough

                if self.appear_then_click(self.I_RM_THROW, interval=2):
                    logger.info('Dice count did not change, click throw again')
                else:
                    logger.info('RichMan is moving, continue waiting for dice count change')
                deadline = time.monotonic() + timeout

            time.sleep(0.3)

    def _detect_richman_mode(self) -> str | None:
        """返回当前出现的大富翁分支模式。"""
        if self.appear(self.I_RM_MODE_THROW):
            return 'throw'
        if self.appear(self.I_RM_MODE_ROB):
            return 'rob'
        if self.appear(self.I_RM_MODE_FIGHT):
            return 'fight'
        return None

    def _wait_for_mode_after_throw(self) -> str:
        """投骰后持续截图，直到识别出投掷、抢夺或战斗模式。"""
        timeout = 5.0
        deadline = time.monotonic() + timeout

        while True:
            self.screenshot()
            mode = self._detect_richman_mode()
            if mode is not None:
                return mode

            if time.monotonic() >= deadline:
                self.update_status()
                if self.appear_then_click(self.I_RM_THROW, interval=2):
                    logger.info('RichMan mode wait timed out, may be reward block')
                else:
                    logger.info('RichMan is moving, continue waiting for mode')
                deadline = time.monotonic() + timeout

            time.sleep(0.3)

    def _run_throw_task(self):
        """持续处理投掷对决；平局时重投，直到棋盘骰子按钮重新出现。"""
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
                logger.info(f'Click RichMan throw mode: {attempt}')
                continue

            if self.ui_reward_appear_click():
                continue
            if (self.appear_then_click(self.I_UI_CONFIRM, interval=1)
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1)):
                continue
            time.sleep(0.5)

    def _run_rob_task(self):
        """立即随机选择一个抢夺目标，并等待返回棋盘投骰状态。"""
        logger.hr('RichMan rob task', 3)
        choice = random.choice([
            self.C_RM_ROB_CHOICE_1,
            self.C_RM_ROB_CHOICE_2,
            self.C_RM_ROB_CHOICE_3,
            self.C_RM_ROB_CHOICE_4,
        ])
        self.click(choice)
        logger.info(f'Click RichMan rob choice: {choice.name}')

        deadline = time.monotonic() + 10.0
        while True:
            if time.monotonic() >= deadline:
                raise GameStuckError('RichMan rob mode timed out after 10 seconds')
            self.screenshot()
            if self.appear(self.I_RM_THROW):
                return
            time.sleep(0.3)

    def _run_fight_task(self, switch_loadout: bool):
        """执行一次普通格子战斗。"""
        logger.hr('RichMan fight task', 3)
        if switch_loadout:
            self._switch_battle_soul(self.I_RM_FIGHT_GOTO_RECORDS, mode='pass')

        source_conf = self.conf.pass_battle_conf
        battle_conf = source_conf.copy(update={
            'lock_team_enable': source_conf.lock_team_enable and not source_conf.preset_enable,
            'preset_enable': source_conf.preset_enable and switch_loadout,
            'continuous_battle': False,
            'max_continuous': 0,
        })
        self._apply_team_lock(
            unlock=self.I_RM_FIGHT_UNLOCK,
            lock=self.I_RM_FIGHT_LOCK,
            should_lock=battle_conf.lock_team_enable,
        )
        self._click_fight_challenge(self.I_RM_MODE_FIGHT, mode='normal')
        self.run_general_battle(
            battle_conf,
            battle_key=f'rich_man_fight_{self.count_map[self.climb_type]}',
            exit_matcher=self.I_RM_THROW,
        )
        self._wait_until_throw()

    def _run_boss_fight_task(self):
        """投骰前进入首领挑战并执行一次完整战斗。"""
        logger.hr('RichMan boss fight task', 3)
        self._enter_boss_fight_by_anchor()
        self._switch_battle_soul(self.I_RM_FIGHT_BOSS_GOTO_RECORDS, mode='boss')

        # 首领战必须保持阵容未锁定，才能在准备界面切换预设。
        self._apply_team_lock(
            unlock=self.I_RM_FIGHT_UNLOCK_BOSS,
            lock=self.I_RM_FIGHT_LOCK_BOSS,
            should_lock=False,
        )
        battle_conf = self.conf.boss_battle_conf.copy(update={
            'lock_team_enable': False,
            'continuous_battle': False,
            'max_continuous': 0,
        })
        self._click_fight_challenge(self.I_RM_MODE_FIGHT_BOSS, mode='boss')
        self.run_general_battle(
            battle_conf,
            battle_key=f'rich_man_boss_{time.monotonic_ns()}',
            exit_matcher=self.I_RM_THROW,
        )
        self._sleep_and_screenshot(8, 10)
        self._wait_until_throw()

    def _enter_boss_fight_by_anchor(self):
        """按动态锚点中心向上 70 像素点击，并确认进入首领挑战界面。"""
        for attempt in range(1, 3):
            self.screenshot()
            if self.appear(self.I_RM_MODE_FIGHT_BOSS):
                return
            if not self._boss_anchor_appear():
                logger.warning(f'RichMan boss anchor missing before entry attempt {attempt}/2')
                time.sleep(0.3)
                continue

            x, y, width, height = self.I_RM_FITGHT_ANCHOR.roi_front
            click_x = x + width // 2
            click_y = y + height // 2 - 70
            click_x = max(0, min(1279, click_x))
            click_y = max(0, min(719, click_y))
            logger.info(
                f'Click RichMan boss entry: attempt={attempt}/2, '
                f'anchor={(x, y, width, height)}, position={(click_x, click_y)}'
            )
            self.device.click(
                x=click_x,
                y=click_y,
                control_name='rm_boss_fight_dynamic_enter',
            )

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                self.screenshot()
                if self.appear(self.I_RM_MODE_FIGHT_BOSS):
                    return
                time.sleep(0.3)

        raise GameStuckError('RichMan boss entry failed after 2 dynamic click attempts')

    def _click_fight_challenge(self, challenge_button, mode: str):
        """在大富翁战斗界面显式点击挑战按钮，再交给通用战斗流程。"""
        self.screenshot()
        if self.appear_then_click(challenge_button):
            logger.info(f'Click RichMan {mode} fight challenge')
            return
        logger.warning(f'RichMan {mode} fight challenge button not found')

    def _switch_battle_soul(self, enter_button, mode: str):
        """从战斗准备界面进入式神录，按普通战或首领战配置切换御魂。"""
        conf = self.conf.switch_soul_config
        enable = getattr(conf, f'enable_switch_{mode}')
        enable_by_name = getattr(conf, f'enable_switch_{mode}_by_name')
        if not enable and not enable_by_name:
            return

        conf.validate_switch_soul()
        self.ui_click(enter_button, stop=self.I_CHECK_RECORDS, interval=1)
        if enable_by_name:
            group, team = getattr(conf, f'{mode}_group_team_name').split(',', 1)
            self.run_switch_soul_by_name(group.strip(), team.strip())
        else:
            self.run_switch_soul(getattr(conf, f'{mode}_group_team'))
        self.exit_shikigami_records()

    def _apply_team_lock(self, unlock, lock, should_lock: bool):
        """将准备界面的阵容锁切换到指定状态。"""
        self.screenshot()
        if should_lock:
            if self.appear(lock):
                return
            self.ui_click(unlock, stop=lock, interval=1)
            return
        if self.appear(unlock):
            return
        self.ui_click(lock, stop=unlock, interval=1)

    def _wait_until_throw(self):
        """统一处理分支收尾，唯一结束条件为重新检测到投骰按钮。"""
        while True:
            self.screenshot()
            if self.appear(self.I_RM_THROW):
                return
            if self.ui_reward_appear_click():
                continue
            if (self.appear_then_click(self.I_UI_CONFIRM, interval=1)
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1)):
                continue
            time.sleep(0.5)

    def _sleep_and_screenshot(self, minimum: float, maximum: float):
        seconds = random.uniform(minimum, maximum)
        logger.info(f'Wait {seconds:.1f}s')
        time.sleep(seconds)
        self.screenshot()
