# This Python file uses the following encoding: utf-8
"""从当期爬塔中拆出的大富翁任务。"""

import random

from cached_property import cached_property

from module.base.protect import random_sleep
from module.base.timer import Timer
from module.logger import logger
from tasks.RichMan.base_act import BaseAct, TicketsNotEnough
from tasks.DemonEncounter.data.answer import Answer
from tasks.RichMan.config import RichMan
from tasks.Quiz.debug import Debugger, remove_symbols


class ScriptTask(BaseAct, Debugger):

    @cached_property
    def conf(self) -> RichMan:
        return self.config.model.rich_man

    @property
    def scheduled_task_name(self) -> str:
        return 'RichMan'

    @cached_property
    def answer(self) -> Answer:
        return Answer()

    def _run_pass(self):
        logger.hr('Start RichMan', 1)
        self.click(self.I_TO_BATTLE_MAIN)
        switch_souled = False
        click_ticket, no_tickets = 0, random.randint(4, 6)
        click_fire, no_fire = 0, random.randint(3, 5)
        while True:
            self.screenshot()
            self.update_status()
            if self.appear(self.I_RM_NO_TICKET, interval=2) or click_ticket > no_tickets:
                logger.warning(f'Click ticket {click_ticket} times, no tickets left')
                break
            if click_fire > no_fire:
                logger.warning(f'Click fire {click_fire} times, no fire left')
                break
            if self.ui_reward_appear_click():
                continue
            if self.appear(self.I_RM_FORWARD, interval=1.2):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=2):
                continue
            # TODO: 首领战斗暂不处理。后续应在跟随人物的地图视角中 OCR
            # 检测固定范围内的“起点”，同时 OCR 判断经验是否已满；满足
            # 两项条件后设置待挑战状态，并在下一次投骰前插入首领战斗。
            if self.appear_then_click(self.I_RM_THROW, interval=2):
                logger.hr('Throw ticket', 3)
                self.count_map[self.climb_type] += 1
                click_ticket = 0
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                while True:
                    self.screenshot()
                    if self.ui_reward_appear_click():
                        break
                    if self.appear(self.I_RM_THROW_WIN, interval=1.5):
                        logger.info('Throw win')
                        continue
                    if self.appear(self.I_RM_THROW_EQUAL, interval=1.5):
                        logger.info('Throw equal')
                        continue
                    if self.appear_then_click(self.I_RM_THROW, interval=2):
                        logger.info('Throw again')
                        self.device.stuck_record_clear()
                        self.device.stuck_record_add('BATTLE_STATUS_S')
                        continue
                continue
            if (self.appear(self.I_RM_BUY_AP) or self.appear(self.I_RM_BUY_REWARD)
                    or self.appear(self.I_RM_BUY_TICKET)):
                logger.hr('Buy event', 3)
                click_ticket = 0
                purchase = self.conf.purchase
                timeout_timer = Timer(5).start()
                while True:
                    self.screenshot()
                    if self.ui_reward_appear_click():
                        break
                    if (self.appear_then_click(self.I_UI_CONFIRM, interval=1)
                            or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1)):
                        timeout_timer.reset()
                        continue
                    if timeout_timer.reached():
                        logger.warning('Buy timeout, exit buy')
                        self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
                        continue
                    if not purchase.buy_ap and not purchase.buy_ticket and not purchase.buy_reward:
                        self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
                        continue
                    if purchase.buy_ticket and self.appear_then_click(self.I_RM_BUY_TICKET, interval=1.5):
                        continue
                    if purchase.buy_reward and self.appear_then_click(self.I_RM_BUY_REWARD, interval=1.5):
                        continue
                    if purchase.buy_ap and self.appear_then_click(self.I_RM_BUY_AP, interval=1.5):
                        continue
            if self.appear(self.I_RM_QUESTION, interval=2):
                click_ticket = 0
                logger.hr('Start question', 3)
                question, answer_1, answer_2, answer_3 = self.detect_question_and_answers()
                index = self.answer.answer_one(question=question, options=[answer_1, answer_2, answer_3])
                if index is None:
                    logger.error('Now question has no answer, please check')
                    self.append_one(question=question, options=[answer_1, answer_2, answer_3])
                    self.config.notifier.push(title='Quiz',
                                              content=f'New question: \n{question} \n{[answer_1, answer_2, answer_3]}')
                    index = 1
                logger.attr(index, 'Answer')
                self.click([self.O_RM_ANSWER_1, self.O_RM_ANSWER_2, self.O_RM_ANSWER_3][index - 1], interval=1)
                self.device.click_record_clear()
                continue
            if self.appear(self.I_ACT_FIRE, interval=2):
                click_ticket = 0
                if not switch_souled:
                    self.switch_soul(self.I_BATTLE_MAIN_TO_RECORDS)
                    switch_souled = True
                if self.conf.general_climb.random_sleep:
                    random_sleep(probability=0.2)
                self.click(self.I_ACT_FIRE)
                click_fire += 1
                self.run_general_battle(self.conf.pass_battle_conf, 'rich_man')
                continue

        while True:
            self.screenshot()
            if self.appear(self.I_TO_BATTLE_MAIN, interval=1):
                break
            if (self.appear_then_click(self.I_UI_CONFIRM, interval=1)
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1)):
                continue
            self.close_unknown_pages()
        raise TicketsNotEnough

    def detect_question_and_answers(self) -> tuple:
        self.screenshot()
        results = self.O_RM_QUESTION.detect_and_ocr(self.device.image)
        question = ''
        answer_1 = remove_symbols(self.O_RM_ANSWER_1.ocr(self.device.image))
        answer_2 = remove_symbols(self.O_RM_ANSWER_2.ocr(self.device.image))
        answer_3 = remove_symbols(self.O_RM_ANSWER_3.ocr(self.device.image))

        for result in results:
            y_start = result.box[0][1]
            y_end = result.box[2][1]
            if y_start >= 0 and y_end <= 150:
                question += result.ocr_text

        return remove_symbols(question), answer_1, answer_2, answer_3
