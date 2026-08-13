# This Python file uses the following encoding: utf-8
"""大富翁棋盘任务。"""

import random
import time

from cached_property import cached_property

from module.logger import logger
from tasks.RichMan.base_act import BaseAct
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
        while True:
            self.screenshot()
            self.update_status()

            if self.ui_reward_appear_click():
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=2):
                continue

            # 首领入口必须优先于投骰，避免进入下一步后错过入口。
            if self.appear(self.I_RM_FITGHT_BOSS, interval=1):
                self._run_boss_fight_task()
                # 首领战会换成首领御魂/预设，下一次普通战需要恢复普通装配。
                normal_loadout_required = True
                continue

            if self.appear_then_click(self.I_RM_THROW, interval=2):
                logger.hr('Throw ticket', 3)
                self.count_map[self.climb_type] += 1
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')

                wait_seconds = random.uniform(3, 5)
                logger.info(f'Wait {wait_seconds:.1f}s for RichMan mode')
                time.sleep(wait_seconds)
                self.screenshot()

                if self.appear(self.I_RM_MODE_THROW):
                    self._run_throw_task()
                    continue
                if self.appear(self.I_RM_MODE_ROB):
                    self._run_rob_task()
                    continue
                if self.appear(self.I_RM_MODE_FIGHT):
                    self._run_fight_task(switch_loadout=normal_loadout_required)
                    normal_loadout_required = False
                    continue

                if self.appear(self.I_RM_THROW):
                    logger.info('No RichMan mode detected, continue next throw')
                    continue

                logger.warning('No RichMan mode or throw button detected')
                continue

    def _run_throw_task(self):
        """最多点击三次投掷对决按钮，直到回到棋盘投骰状态。"""
        logger.hr('RichMan throw task', 3)
        for attempt in range(1, 4):
            self.screenshot()
            if not self.appear(self.I_RM_MODE_THROW):
                logger.info('Throw mode disappeared')
                self._sleep_and_screenshot(3, 5)
                break

            logger.info(f'Click throw mode: {attempt}/3')
            self.appear_then_click(self.I_RM_MODE_THROW, interval=1)
            self._sleep_and_screenshot(3, 5)
            if self.appear(self.I_RM_THROW):
                return
            if not self.appear(self.I_RM_MODE_THROW):
                logger.info('Throw mode finished')
                self._sleep_and_screenshot(3, 5)
                break

        self._wait_until_throw()

    def _run_rob_task(self):
        """等待后随机选择一个抢夺目标，直到回到棋盘投骰状态。"""
        logger.hr('RichMan rob task', 3)
        self._sleep_and_screenshot(1, 3)
        self.click(random.choice([
            self.C_RM_ROB_CHOICE_1,
            self.C_RM_ROB_CHOICE_2,
            self.C_RM_ROB_CHOICE_3,
            self.C_RM_ROB_CHOICE_4,
        ]))
        self._sleep_and_screenshot(3, 5)
        self._wait_until_throw()

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
        self.run_general_battle(
            battle_conf,
            battle_key=f'rich_man_fight_{self.count_map[self.climb_type]}',
            exit_matcher=self.I_RM_THROW,
        )
        self._wait_until_throw()

    def _run_boss_fight_task(self):
        """投骰前进入首领挑战并执行一次完整战斗。"""
        logger.hr('RichMan boss fight task', 3)
        self.ui_click(self.C_RM_FIGHT_BOSS_ENTER, stop=self.I_RM_MODE_FIGHT_BOSS, interval=1)
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
        self.run_general_battle(
            battle_conf,
            battle_key=f'rich_man_boss_{time.monotonic_ns()}',
            exit_matcher=self.I_RM_THROW,
        )
        self._sleep_and_screenshot(8, 10)
        self._wait_until_throw()

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
