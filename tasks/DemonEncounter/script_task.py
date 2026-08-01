# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
from time import sleep

from enum import Enum
from cached_property import cached_property
from datetime import datetime, timedelta

from module.logger import logger
from module.exception import GameStuckError, TaskEnd
from module.base.timer import Timer

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.DemonEncounter.config import BossType, DemonEncounter, convert_to_general_battle_config
from tasks.DemonEncounter.page import page_rwt
from tasks.GameUi.default_pages import page_main
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_shikigami_records
from tasks.DemonEncounter.assets import DemonEncounterAssets
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.DemonEncounter.data.answer import Answer


class LanternClass(Enum):
    BATTLE = 0  # 打怪  --> 无法判断因为怪的图片不一样，用排除法
    BOX = 1  # 开宝箱
    MAIL = 2  # 邮件答题
    REALM = 3  # 打结界
    EMPTY = 4  # 空
    MYSTERY = 5  # 神秘任务
    BOSS = 6  # 大鬼王


class ScriptTask(GameUi, GeneralBattle, DemonEncounterAssets, SwitchSoul):
    conf: DemonEncounter = None
    LANTERN_BATTLE_OPEN_MAX_CLICKS = 5

    def run(self):
        self.conf = self.config.demon_encounter
        if not self.check_time():
            logger.warning('Time is not right')
            raise TaskEnd('DemonEncounter')
        # 切换御魂
        soul_config = self.config.demon_encounter.demon_soul_config
        best_soul_config = self.config.demon_encounter.best_demon_soul_config
        if soul_config.enable or best_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.checkout_soul()
        self.goto_page(page_rwt)
        self.execute_lantern()
        self.execute_boss()
        self.goto_page(page_main)
        self.set_next_run(task='DemonEncounter', success=True, finish=False)
        raise TaskEnd('DemonEncounter')

    def checkout_soul(self):
        """
        切换御魂
        """
        select_best_demon = getattr(self.conf.best_demon_boss_config, f'{self.boss_type}_select', False)
        if select_best_demon:
            group, team = getattr(self.conf.best_demon_soul_config, self.boss_type).split(",")
        else:
            group, team = getattr(self.conf.demon_soul_config, self.boss_type).split(",")
        if group and team:
            self.run_switch_soul_by_name(group, team)
            return
        logger.error(f'Unknown switch soul conf: group[{group}], team[{team}]')

    def execute_boss(self):
        """
        打boss
        :return:
        """
        logger.hr('Start boss battle', 1)

        def find_boss():
            def boss_page_opened() -> bool:
                return (
                    self.appear(self.I_BOSS_FIRE)
                    or self.appear(self.I_BEST_BOSS_FIRE)
                )

            def wait_boss_page_opened(wait_time: float = 2.0) -> bool:
                timer = Timer(wait_time)
                timer.start()
                while True:
                    self.screenshot()
                    if boss_page_opened():
                        return True
                    if timer.reached():
                        return False

            def try_open_boss(
                    marker,
                    label: str,
                    *,
                    threshold: float | None = None,
                    mechanical: bool = False,
            ) -> bool:
                self.screenshot()
                if boss_page_opened():
                    return True

                if mechanical:
                    logger.warning(
                        f'{label} marker not recognized; '
                        'mechanically click its target position'
                    )
                    self.click(marker)
                else:
                    if not self.appear(
                            marker,
                            threshold=threshold,
                    ):
                        return False
                    logger.info(
                        f'Finding {label}...'
                        if threshold is None else
                        f'Finding {label} with threshold={threshold:.1f}...'
                    )
                    self.click(marker)

                if wait_boss_page_opened():
                    return True

                # 点击底部入口后，地图中央还需要再点一次首领目标。
                self.click(self.C_DM_BOSS_CLICK)
                return wait_boss_page_opened()

            if self.best_demon_enable:
                marker = self.I_DE_BOSS_BEST
                label = 'best boss'
            else:
                marker = self.I_DE_BOSS
                label = 'normal boss'

            for cycle in range(1, 6):
                logger.info(
                    f'Open {label} fallback cycle {cycle}/5'
                )
                self.device.stuck_record_clear()
                self.device.click_record_clear()

                if try_open_boss(marker, label):
                    return True
                if try_open_boss(marker, label, threshold=0.7):
                    return True
                if try_open_boss(marker, label, mechanical=True):
                    return True

                self.screenshot()
                if self.appear(self.I_JADE_50):
                    # 误点到地图宝箱时先关闭购买界面，再进入下一轮。
                    self.ui_click_until_smt_disappear(
                        self.I_DE_FIND,
                        self.I_JADE_50,
                        interval=1,
                    )

                self.screenshot()
                logger.warning(
                    f'{label} page still closed after fallback cycle '
                    f'{cycle}/5'
                )

            raise GameStuckError(
                f'DemonEncounter: failed to open {label} page '
                'after 5 fallback cycles'
            )

        def enter_boss():
            logger.info('trying to enter boss...')
            # 点击集结挑战
            boss_fire_count = 0  # 五次没点到就意味着今天已经挑战过了
            ocr_people_item = self.O_DE_BEST_BOSS_PEOPLE if self.best_demon_enable else self.O_DE_BOSS_PEOPLE
            while 1:
                self.screenshot()

                if self.appear(self.I_BOSS_FIRE) or self.appear(self.I_BEST_BOSS_FIRE):
                    current, remain, total = ocr_people_item.ocr(self.device.image)
                    if total == 300 and current >= 290:
                        logger.info('Boss battle people is full')
                        if not self.appear(self.I_UI_BACK_RED):
                            logger.warning('Boss battle people is full but no red back')
                            continue
                        self.ui_click_until_disappear(self.I_UI_BACK_RED)
                        # 退出重新选一个没人慢的boss
                        logger.info('Exit and reselect')
                        return False

                logger.info('Boss battle people is not full')

                if self.appear(self.I_BOSS_CONFIRM):
                    self.ui_click(self.I_BOSS_NO_SELECT, self.I_BOSS_SELECTED)
                    self.ui_click(self.I_BOSS_CONFIRM, self.I_BOSS_GATHER)
                    break
                if self.appear(self.I_BOSS_GATHER):
                    break
                if boss_fire_count >= 5:
                    logger.warning('Boss battle already done')
                    self.set_next_run(
                        task='DemonEncounter',
                        success=True,
                        finish=True,
                        server=True,
                    )
                    self.ui_click_until_disappear(self.I_UI_BACK_RED)
                    self.config.model.running_task = ''
                    raise TaskEnd('DemonEncounter')

                if (self.appear_then_click(self.I_BOSS_FIRE, interval=3)
                        or self.appear_then_click(self.I_BEST_BOSS_FIRE, interval=3)):
                    boss_fire_count += 1
                    continue
            return True

        fail_count = 0
        while True:
            if fail_count >= 5:
                return
            if not find_boss():
                continue
            if enter_boss():
                break
            fail_count += 1

        logger.info('Boss battle confirm and enter')
        self.device.stuck_record_clear()
        # 等待挑战, 5秒也是等
        time.sleep(5)
        refresh_timer = Timer(280)
        while True:
            self.screenshot()
            if self.appear(self.I_BOSS_DONE_CHECK):
                break
            if self.appear(self.I_BOSS_GATHER):
                if not refresh_timer.started() or refresh_timer.reached():
                    self.device.stuck_record_clear()
                    self.device.stuck_record_add('BATTLE_STATUS_S')
                    logger.info('Boss Gathering...')
                    refresh_timer.reset()
                sleep(2)
                continue
            if self.appear(self.I_BOSS_WAIT):
                logger.info('Boss battle failed, waiting for 2 seconds...')
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
                refresh_timer.reset()
                sleep(2)
                continue
            if self.appear(self.I_PREPARE_HIGHLIGHT):
                if self.best_demon_enable:
                    general_battle_config = convert_to_general_battle_config(self.boss_type,
                                                                             best_demon_battle_conf=self.conf.best_demon_battle_config)
                else:
                    general_battle_config = convert_to_general_battle_config(self.boss_type,
                                                                             demon_battle_conf=self.conf.demon_battle_config)
                self.run_general_battle(config=general_battle_config, battle_key=self.boss_type)
                continue
            logger.info('Unknown scene Or Boss fight failed.waiting for Prepare_Button appear...')
            self.wait_until_appear(self.I_PREPARE_HIGHLIGHT, wait_time=2)

        # 等待回到挑战boss主界面
        self.wait_until_appear(self.I_BOSS_GATHER)
        while 1:
            self.screenshot()
            if self.appear(self.I_DE_LOCATION):
                break
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1):
                continue
            if self.appear_then_click(self.I_BOSS_BACK_WHITE, interval=1):
                continue
        # 返回到封魔主界面

    def execute_lantern(self):
        """
        点灯笼 四次
        :return:
        """
        # 只有进入页面时同时满足次数为0/4、顶部达摩位置已经变成
        # de_award，才确认今日现世逢魔已经完整处理。单独命中任一项
        # 都不能跳过，以免把本轮刚完成寻找但尚未处理的灯笼漏掉。
        self.screenshot()
        current, remain, total = self.O_DE_COUNTER.ocr(
            self.device.image
        )
        encounter_over = self.appear(self.I_DE_AWARD)
        logger.info(
            'DemonEncounter initial real-world status: '
            f'counter={current}/{total}, remain={remain}, '
            f'de_award={encounter_over}'
        )
        if (
                current == 0
                and remain == 4
                and total == 4
                and encounter_over
        ):
            logger.info(
                'Real-world DemonEncounter already completed today; '
                'skip finding and lantern handling'
            )
            return

        # 先点四次
        ocr_timer = Timer(0.8)
        ocr_timer.start()
        while 1:
            self.screenshot()
            if not ocr_timer.reached():
                continue
            else:
                ocr_timer.reset()
            cu, re, total = self.O_DE_COUNTER.ocr(self.device.image)
            if cu + re != total:
                logger.warning('Lantern count error')
                continue
            if cu == 0 and re == 4:
                break

            if self.appear_then_click(self.I_DE_FIND, interval=2.5):
                continue
        logger.info('Lantern count success')
        # 然后领取红色达摩
        self.screenshot()
        if not self.appear(self.I_DE_AWARD):
            self.ui_get_reward(self.I_DE_RED_DHARMA)
        self.wait_until_appear(self.I_DE_AWARD)
        # 然后到四个灯笼
        match_click = {
            1: self.C_DE_1,
            2: self.C_DE_2,
            3: self.C_DE_3,
            4: self.C_DE_4,
        }
        for i in range(1, 5):
            logger.hr(f'Check lantern {i}', 3)
            lantern_type = self.check_lantern(i)
            self.device.click_record_clear()
            match lantern_type:
                case LanternClass.BOX:
                    self._box(match_click[i])
                case LanternClass.MAIL:
                    self._mail(match_click[i])
                case LanternClass.REALM:
                    self._realm(match_click[i])
                case LanternClass.EMPTY:
                    logger.warning(f'Lantern {i} is empty')
                case LanternClass.BATTLE:
                    self._battle(match_click[i])
                case LanternClass.MYSTERY:
                    self._mystery(match_click[i])
                case LanternClass.BOSS:
                    self._boss(match_click[i])
            time.sleep(1)

    def check_lantern(self, index: int = 1):
        """
        检查灯笼的类型
        :param index: 四个灯笼，从1开始
        :return:
        """
        match_roi = {
            1: self.C_DE_1.roi_front,
            2: self.C_DE_2.roi_front,
            3: self.C_DE_3.roi_front,
            4: self.C_DE_4.roi_front,
        }
        match_empty = {
            1: self.I_DE_DEFEAT_1,
            2: self.I_DE_DEFEAT_2,
            3: self.I_DE_DEFEAT_3,
            4: self.I_DE_DEFEAT_4,
        }
        self.I_DE_BOX.roi_back = match_roi[index]
        self.I_DE_LETTER.roi_back = match_roi[index]
        self.I_DE_MYSTERY.roi_back = match_roi[index]
        self.I_DE_REALM.roi_back = match_roi[index]
        self.I_DE_FIND_BOSS.roi_back = match_roi[index]
        target_box = self.I_DE_BOX
        target_letter = self.I_DE_LETTER
        target_mystery = self.I_DE_MYSTERY
        target_realm = self.I_DE_REALM
        target_find_boss = self.I_DE_FIND_BOSS
        target_empty = match_empty[index]

        # 开始判断
        self.screenshot()
        if self.appear(target_box):
            logger.info(f'Lantern {index} is box')
            return LanternClass.BOX
        elif self.appear(target_letter):
            logger.info(f'Lantern {index} is letter')
            return LanternClass.MAIL
        elif self.appear(target_mystery):
            logger.info(f'Lantern {index} is mystery task')
            return LanternClass.MYSTERY
        elif self.appear(target_realm):
            logger.info(f'Lantern {index} is realm')
            return LanternClass.REALM
        elif self.appear(target_empty):
            logger.info(f'Lantern {index} is empty')
            return LanternClass.EMPTY
        elif self.appear(target_find_boss):
            logger.info(f'Lantern {index} is boss')
            return LanternClass.BOSS
        else:
            # 无法判断是否是战斗的还是结界的
            logger.info(f'Lantern {index} is battle')
            return LanternClass.BATTLE

    def _box(self, target_click):
        box_buy_config = self.config.demon_encounter.box_buy_config
        while 1:
            self.screenshot()
            if self.appear(self.I_JADE_50):
                break
            if self.click(target_click, interval=1):
                continue
        while 1:
            self.screenshot()
            if not self.appear(self.I_MYSTERY_AMULET) and not (box_buy_config.box_buy_sushi and self.appear(self.I_SUSHI)):
                if self.appear_then_click(self.I_DE_FIND, interval=2.5):
                    break
            # 默认购买蓝票
            if self.appear(self.I_MYSTERY_AMULET):
                logger.info('Buy a mystery amulet for 50 jade')
                self.click(self.I_JADE_50)
                continue
            # 可选购买体力
            if box_buy_config.box_buy_sushi and self.appear(self.I_SUSHI):
                logger.info('Buy one hundred sushi for 50 jade')
                self.click(self.I_JADE_50)
                continue

    def _mail(self, target_click):
        # 答题
        def answer():
            click_match = {
                1: self.C_ANSWER_1,
                2: self.C_ANSWER_2,
                3: self.C_ANSWER_3,
            }
            index = None
            self.screenshot()
            question = self.O_LETTER_QUESTION.detect_text(self.device.image)
            question = question.replace('?', '').replace('？', '')
            answer_1 = self.O_LETTER_ANSWER_1.detect_text(self.device.image)
            answer_2 = self.O_LETTER_ANSWER_2.detect_text(self.device.image)
            answer_3 = self.O_LETTER_ANSWER_3.detect_text(self.device.image)
            if answer_1 == '其余选项皆对':
                index = 1
            elif answer_2 == '其余选项皆对':
                index = 2
            elif answer_3 == '其余选项皆对':
                index = 3
            if not index:
                index = Answer().answer_one(question=question, options=[answer_1, answer_2, answer_3])
            if index is None:
                index = 1
            logger.info(f'Question: {question}, Answer: {index}')
            return click_match[index]

        while 1:
            self.screenshot()
            if self.appear(self.I_LETTER_CLOSE):
                break
            if self.click(target_click, interval=1):
                continue
        logger.info('Question answering Start')
        for i in range(1, 4):
            # 还未测试题库无法识别的情况
            logger.hr(f'Answer {i}', 3)
            answer_click = answer()
            while 1:
                self.screenshot()
                if self.ui_reward_appear_click():
                    time.sleep(0.5)
                    while 1:
                        self.screenshot()
                        # 等待动画结束
                        if not self.appear(self.I_UI_REWARD, threshold=0.6):
                            logger.info('Get reward success')
                            break
                        # 一直点击
                        if self.ui_reward_appear_click():
                            continue
                    break
                # 如果没有出现红色关闭按钮，说明答题结束
                if not self.appear(self.I_LETTER_CLOSE):
                    time.sleep(1.8)
                    self.screenshot()
                    if not self.appear(self.I_LETTER_CLOSE):
                        logger.warning('Answer finish')
                        return

                # 一直点击
                self.click(answer_click, interval=1.5)
            time.sleep(0.5)

    def _battle(self, target_click):
        click_count = 0
        while 1:
            self.screenshot()
            if not self.appear(self.I_DE_LOCATION):
                logger.info('Battle Start')
                break
            if self.appear(self.I_DE_SMALL_FIRE):
                # 小鬼王
                logger.info('Small Boss')
                while 1:
                    self.screenshot()
                    if not self.appear(self.I_DE_SMALL_FIRE):
                        break
                    if self.appear_then_click(self.I_DE_SMALL_FIRE, interval=1):
                        continue
                break

            if self.click(target_click, interval=1):
                click_count += 1
                if click_count >= self.LANTERN_BATTLE_OPEN_MAX_CLICKS:
                    logger.warning(
                        'Lantern classified as battle did not open after '
                        f'{click_count} clicks; treat it as empty or '
                        'unrecognized and continue'
                    )
                    return False
                continue
        self.current_count = 0
        if self.run_general_battle():
            logger.info('Battle End')
        return True

    def _realm(self, target_click):
        # 结界
        while 1:
            self.screenshot()
            if not self.appear(self.I_DE_LOCATION):
                logger.info('Battle Start')
                break
            if self.appear_then_click(self.I_DE_REALM_FIRE, interval=0.7):
                continue

            if self.click(target_click, interval=1):
                continue
        self.current_count = 0
        if self.run_general_battle():
            logger.info('Battle End')

    def _mystery(self, target_click):
        # 神秘任务， 不做
        pass

    def _boss(self, target_click):
        # 运气爆表，点灯笼出现大鬼王
        while 1:
            self.screenshot()
            if self.appear(self.I_BOSS_KILLED):
                # 这个大鬼王已经击败
                logger.warning('Boss already killed')
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                break
            if self.appear(self.I_BOSS_FIRE):
                self.execute_boss()
                break
            if self.click(target_click, interval=2.3):
                continue

    def check_time(self):
        """
        检查时间是否正确，
        如果正确就继续
        如果不在17:00到22:00之间,就推迟到下一个 17:30
        :return:
        """
        now = datetime.now()
        if now.hour < 17:
            # 17点之前，推迟到当天的17点半
            logger.info('Before 17:00, wait to 17:30')
            target_time = datetime(now.year, now.month, now.day, 17, 30, 0)
            self.set_next_run(task='DemonEncounter', success=False, finish=False, target=target_time)
            return False
        elif now.hour >= 23:
            # 23点之后，推迟到第二天的17:30
            logger.info('After 23:00, wait to 17:30')
            target_time = datetime(now.year, now.month, now.day, 17, 30, 0) + timedelta(days=1)
            self.set_next_run(task='DemonEncounter', success=False, finish=False, target=target_time)
            return False
        else:
            return True

    @property
    def boss_type(self) -> str:
        boss_name = BossType(datetime.now().weekday()).name
        if self.best_demon_enable:
            return f'best_demon_{boss_name}'
        return f'demon_{boss_name}'

    @property
    def best_demon_enable(self) -> bool:
        boss_name = BossType(datetime.now().weekday()).name
        return getattr(self.conf.best_demon_boss_config, f'best_demon_{boss_name}_select', False)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('du')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
