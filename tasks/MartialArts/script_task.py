# This Python file uses the following encoding: utf-8
"""武道大会战斗任务。"""

import time

from cached_property import cached_property

from module.base.timer import Timer
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.MartialArts.assets import MartialArtsAssets
from tasks.MartialArts.config import MartialArts
import tasks.MartialArts.page as pages


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, MartialArtsAssets):
    AP_COST = 30
    TICKET_COST = 1
    RESOURCE_OCR_RETRIES = 3
    ENTER_BATTLE_TIMEOUT = 20

    battle_type = 'ap'

    @cached_property
    def conf(self) -> MartialArts:
        return self.config.model.martial_arts

    def _exit_matcher(self):
        """体力战结算完成并重新出现挑战按钮时，视为已返回日常训练。"""
        if self.battle_type == 'ap':
            return self.I_MAR_FIRE_AP
        return None

    def before_run(self):
        sequence = self.conf.general_climb.run_sequence_v
        logger.info(f'MartialArts run sequence: {sequence}')

    def enter_ap_battle(self):
        """从任意已知页面导航至武道大会日常训练页面。"""
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

    def switch_soul_before_battle(self, battle_type: str):
        """按体力战/首领战各自配置，在该类型首次执行前切换御魂。"""
        conf = self.conf.switch_soul_config
        enable_number = getattr(conf, f'enable_switch_{battle_type}')
        enable_name = getattr(conf, f'enable_switch_{battle_type}_by_name')
        if not enable_number and not enable_name:
            return

        conf.validate_switch_soul()
        logger.hr(f'Switch MartialArts {battle_type} soul', 2)
        self.ui_click(self.I_BATTLE_MAIN_TO_RECORDS, stop=self.I_CHECK_RECORDS, interval=1)
        if enable_name:
            group, team = getattr(conf, f'{battle_type}_group_team_name').split(',')
            self.run_switch_soul_by_name(group, team)
        else:
            self.run_switch_soul(getattr(conf, f'{battle_type}_group_team'))

        if battle_type == 'ap':
            self.goto_page(pages.page_martial_arts_ap)

    def lock_team(self, battle_conf: GeneralBattleConfig):
        """根据当前战斗类型配置锁定或解锁阵容。"""
        if battle_conf.lock_team_enable:
            logger.info(f'Lock MartialArts {self.battle_type} team')
            self.ui_click(self.I_AP_UNLOCK, stop=self.I_AP_LOCK, interval=1.5)
            return
        logger.info(f'Unlock MartialArts {self.battle_type} team')
        self.ui_click(self.I_AP_LOCK, stop=self.I_AP_UNLOCK, interval=1.5)

    def enter_battle(self) -> bool:
        """点击体力挑战并等待进入通用准备/战斗页面。"""
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

    def run_battle_round(self, battle_conf: GeneralBattleConfig) -> bool:
        """执行一轮体力挑战并等待结算返回日常训练页面。"""
        if not self.enter_battle():
            return False
        win = self.run_general_battle(
            battle_conf,
            battle_key='martial_arts_ap',
            exit_matcher=self.I_MAR_FIRE_AP,
        )
        logger.info(f'MartialArts AP battle {self.current_count} result: {"win" if win else "lose"}')
        return True

    def run_ap_battles(self):
        """按体力战配置执行完整循环。"""
        self.battle_type = 'ap'
        self.current_count = 0
        limit = self.conf.general_climb.ap_limit
        battle_conf = self.conf.ap_battle_conf

        self.enter_ap_battle()
        self.switch_soul_before_battle('ap')
        self.lock_team(battle_conf)
        while self.current_count < limit:
            self.goto_page(pages.page_martial_arts_ap)
            if not self.resources_enough():
                logger.info('MartialArts resources are insufficient, stop AP battles')
                break
            if not self.run_battle_round(battle_conf):
                break
        logger.info(f'MartialArts AP battles finished: {self.current_count}/{limit}')

    def run(self):
        self.before_run()
        for battle_type in self.conf.general_climb.run_sequence_v:
            if battle_type == 'ap':
                self.run_ap_battles()
                continue
            if battle_type == 'boss':
                logger.warning('MartialArts boss battle is configured but not implemented yet, skip')

        self.goto_page(pages.page_main)
        self.set_next_run(task='MartialArts', success=True, finish=True)
        raise TaskEnd('MartialArts')
