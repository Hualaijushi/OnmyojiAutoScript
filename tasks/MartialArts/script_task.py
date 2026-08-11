# This Python file uses the following encoding: utf-8
"""武道大会日常训练（体力模式）战斗循环。"""

import time
from datetime import datetime

from cached_property import cached_property

from module.base.timer import Timer
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.MartialArts.assets import MartialArtsAssets
from tasks.MartialArts.config import MartialArts
import tasks.MartialArts.page as pages


class ScriptTask(GeneralBattle, GameUi, MartialArtsAssets):
    AP_COST = 30
    TICKET_COST = 1
    RESOURCE_OCR_RETRIES = 3
    ENTER_BATTLE_TIMEOUT = 20

    @cached_property
    def conf(self) -> MartialArts:
        return self.config.model.martial_arts

    def _exit_matcher(self):
        """结算完成并重新出现挑战按钮时，视为已回到日常训练页面。"""
        return self.I_MAR_FIRE_AP

    def before_run(self):
        self.limit_time = self.conf.martial_arts_config.limit_time_v
        self.limit_count = self.conf.martial_arts_config.battle_count
        logger.info(
            f'MartialArts limits: count={self.limit_count}, '
            f'time={self.limit_time.total_seconds():.0f}s'
        )

    def enter_ap_battle(self):
        """从任意已知页面导航至武道大会日常训练（体力战斗）页面。"""
        logger.hr('Enter MartialArts AP battle page', 2)
        self.goto_page(pages.page_martial_arts_ap)
        logger.info('Entered MartialArts AP battle page')

    @staticmethod
    def _parse_ocr_number(value) -> int:
        """从 OCR 返回值中提取整数；空值或无法识别时返回 0。"""
        text = str(value)
        replacements = {
            'I': '1', 'l': '1', 'D': '0', 'O': '0', 'o': '0',
            'S': '5', 'B': '8', 'd': '6', '?': '2', '？': '2',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        digits = ''.join(char for char in text if char.isdigit())
        return int(digits) if digits else 0

    def read_resources(self) -> tuple[int, int]:
        """读取体力和门票，多次识别取最大值以降低偶发空识别影响。"""
        best_ap = 0
        best_ticket = 0
        for attempt in range(1, self.RESOURCE_OCR_RETRIES + 1):
            self.screenshot()
            ap = self._parse_ocr_number(self.O_AP_COUNT.ocr(self.device.image))
            ticket = self._parse_ocr_number(self.O_AP_TICKET.ocr(self.device.image))
            best_ap = max(best_ap, ap)
            best_ticket = max(best_ticket, ticket)
            logger.info(
                f'MartialArts resources OCR {attempt}/{self.RESOURCE_OCR_RETRIES}: '
                f'AP={ap}, ticket={ticket}'
            )
            if ap > self.AP_COST and ticket >= self.TICKET_COST:
                return ap, ticket
            if attempt < self.RESOURCE_OCR_RETRIES:
                time.sleep(0.5)
        return best_ap, best_ticket

    def resources_enough(self) -> bool:
        ap, ticket = self.read_resources()
        enough = ap > self.AP_COST and ticket >= self.TICKET_COST
        logger.info(
            f'MartialArts resources: AP={ap} (need > {self.AP_COST}), '
            f'ticket={ticket} (need >= {self.TICKET_COST}), enough={enough}'
        )
        return enough

    def lock_team(self):
        """根据通用战斗配置锁定或解锁日常训练阵容。"""
        if self.conf.battle_conf.lock_team_enable:
            logger.info('Lock MartialArts AP team')
            self.ui_click(self.I_AP_UNLOCK, stop=self.I_AP_LOCK, interval=1.5)
            return
        logger.info('Unlock MartialArts AP team')
        self.ui_click(self.I_AP_LOCK, stop=self.I_AP_UNLOCK, interval=1.5)

    def enter_battle(self) -> bool:
        """点击挑战并等待进入通用准备/战斗页面。"""
        timer = Timer(self.ENTER_BATTLE_TIMEOUT).start()
        click_count = 0
        while not timer.reached():
            self.screenshot()
            if self.is_in_battle(False):
                logger.info(f'Entered battle after {click_count} challenge clicks')
                return True
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1) or \
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                logger.warning('Challenge rejected, AP or ticket may be insufficient')
                return False
            if self.appear_then_click(self.I_MAR_FIRE_AP, interval=1.5):
                click_count += 1
                self.device.click_record_clear()
                continue
            time.sleep(0.5)
        logger.warning(f'Cannot enter MartialArts battle within {self.ENTER_BATTLE_TIMEOUT}s')
        return False

    def run_battle_round(self) -> bool:
        """执行一轮挑战并等待结算返回日常训练页面。"""
        if not self.enter_battle():
            return False
        win = self.run_general_battle(
            self.conf.battle_conf,
            battle_key='martial_arts_ap',
            exit_matcher=self.I_MAR_FIRE_AP,
        )
        logger.info(f'MartialArts battle {self.current_count} result: {"win" if win else "lose"}')
        return True

    def limit_reached(self) -> bool:
        if self.limit_count <= 0:
            logger.info('MartialArts battle count is 0, stop task')
            return True
        if self.current_count >= self.limit_count:
            logger.info(f'MartialArts battle count reached: {self.current_count}/{self.limit_count}')
            return True
        elapsed = datetime.now() - self.start_time
        if elapsed >= self.limit_time:
            logger.info(
                f'MartialArts time limit reached: '
                f'{elapsed.total_seconds():.1f}/{self.limit_time.total_seconds():.1f}s'
            )
            return True
        return False

    def run(self):
        self.before_run()
        self.enter_ap_battle()
        self.lock_team()

        while not self.limit_reached():
            self.goto_page(pages.page_martial_arts_ap)
            if not self.resources_enough():
                logger.info('MartialArts resources are insufficient, stop AP battles')
                break
            if not self.run_battle_round():
                break

        logger.info(f'MartialArts AP battles finished, total count: {self.current_count}')
        self.goto_page(pages.page_main)
        self.set_next_run(task='MartialArts', success=True, finish=True)
        raise TaskEnd('MartialArts')
