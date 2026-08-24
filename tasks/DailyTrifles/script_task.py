# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import copy
from time import sleep

import difflib
from datetime import time, datetime, timedelta
from module.atom.image import RuleImage
from module.ocr.common import BoxedResult

from tasks.Component.config_base import Time
from tasks.DailyTrifles.page import page_store_gift_room, page_friends_luck, page_guild_wish

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_summon, page_guild, page_mall, page_friends, page_courtyard_affairs
from tasks.DailyTrifles.config import DailyTriflesConfig
from tasks.DailyTrifles.assets import DailyTriflesAssets
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets
from tasks.Component.Summon.summon import Summon

from module.logger import logger
from module.exception import ScriptError, TaskEnd
from module.base.timer import Timer
from tasks.DailyTrifles.config import SummonType
from tasks.DailyTrifles.hunt_adapter import HuntRotationAdapter
from tasks.DailyTrifles.cooperation_adapter import CooperationAdapter
import re
from typing import Any, Optional, List, Callable


class ScriptTask(GameUi, Summon, DailyTriflesAssets):

    def _run_daily_subtask(self, task_id: str, action):
        """记录当前执行的子任务，供账号轮换准确归属异常。"""
        self._active_daily_subtask = task_id
        result = action()
        self._active_daily_subtask = ""
        return result

    def run_hunt_rotation(self, task_name: str) -> bool | None:
        """由账号轮换调用的麒麟/阴界之门专用入口。"""
        adapter = HuntRotationAdapter(self)
        if task_name == "hunt_kirin":
            return adapter.run_kirin_rotation()
        if task_name == "hunt_netherworld":
            return adapter.run_netherworld_rotation()
        raise ValueError(f"不支持的 Hunt 轮换任务: {task_name}")

    def run_cooperation_rotation(self):
        """执行账号轮换的单时段协作检查，不触发邀请或悬赏执行。"""
        return CooperationAdapter(self).run()

    def run(self):
        con = self.config.daily_trifles.trifles_config
        # 每日召唤
        if con.one_summon:
            self._run_daily_subtask("summon", self.run_one_summon)
        courtyard_period = self._current_courtyard_period()
        if courtyard_period == 'morning' and (con.courtyard_affairs or con.courtyard_morning):
            self._run_daily_subtask("courtyard_morning", lambda: self.run_courtyard_affairs('morning'))
        elif courtyard_period == 'evening' and (con.courtyard_affairs or con.courtyard_evening):
            self._run_daily_subtask("courtyard_evening", lambda: self.run_courtyard_affairs('evening'))
        if con.pickup_email:
            self._run_daily_subtask("pickup_email", self.run_pickup_email)
        if self.config.daily_trifles.guild_donate.enable:
            self._run_daily_subtask("guild_donate", self.run_guild_donate)
        if con.guild_medal_donate:
            self._run_daily_subtask("guild_medal_donate", self.run_guild_medal_donate)
        # 吉闻
        if con.luck_msg:
            self._run_daily_subtask("luck_msg", self.run_luck_msg)
        # 商店签到 or 购买寿司
        if con.store_sign or con.buy_sushi_count > 0:
            self.run_store()
        self.config.save()
        # 当每日琐事由账号轮换调用时，由外层账号轮换负责调度；
        # 运行时配置没有 task_delay()，因此不再对嵌套任务重复调度。
        if hasattr(self.config, 'task_delay'):
            self.plan_next_dt()
        raise TaskEnd('DailyTrifles')

    def _read_guild_medal_amount(self) -> int | None:
        """从捐赠按钮的小范围区域中读取当前金额。"""
        try:
            results = self.O_DT_GUILD_MEDAL_AMOUNT.detect_and_ocr(self.device.image)
        except Exception as exc:
            logger.warning('Guild medal amount OCR failed: %s', exc)
            return None
        for result in results:
            text = str(getattr(result, 'ocr_text', '') or '')
            for token in re.findall(r'100|80|60|40|20', text):
                amount = int(token)
                if amount in (20, 40, 60, 80, 100):
                    return amount
        return None

    def _wait_guild_medal_amount(self, timeout: float = 4.0) -> int | None:
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            amount = self._read_guild_medal_amount()
            if amount is not None:
                return amount
        return None

    def _wait_guild_medal_reward(self, timeout: float = 5.0) -> bool:
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            # 复用稳定的全局奖励弹窗识别和弹窗外点击区域，
            # 不另外增加容易失效的勋章弹窗关闭坐标。
            if self.ui_reward_appear_click():
                return True
        return False

    def _finish_guild_medal_donate(self, target: int) -> bool:
        self.config.daily_trifles.done_record.guild_medal_donate_dt = datetime.now()
        self.config.save()
        self.goto_page(page_main)
        logger.info('Guild medal donation completed amount=%s', target)
        return True

    def run_guild_medal_donate(self) -> bool:
        """按照配置的勾玉数量完成寮勋章捐赠。"""
        logger.hr('guild medal donate', 2)
        if self.config.daily_trifles.today_is_done('guild_medal_donate'):
            logger.info('Guild medal donation already completed today, skip')
            return True

        target = int(self.config.daily_trifles.trifles_config.guild_medal_amount)
        # 进入阴阳寮主页面。I_GUILD_REALM 只用于确认场景，不能点击；
        # 点击它会进入个人结界。确认寮境场景后，再点击右下角“寮信息”。
        self.goto_page(page_guild)
        if not self.wait_until_appear(KekkaiUtilizeAssets.I_GUILD_REALM, wait_time=5):
            raise ScriptError('Guild realm scene was not recognized')
        if not self.wait_until_appear(KekkaiUtilizeAssets.I_GUILD_INFO, wait_time=5):
            raise ScriptError('Guild realm hall was not recognized after opening guild realm')
        logger.info('Guild realm hall recognized, opening guild information')
        if not self.appear_then_click(KekkaiUtilizeAssets.I_GUILD_INFO, interval=0.8):
            raise ScriptError('Guild information entry was not found in guild realm')
        # 确认寮信息页面稳定后再操作勾玉数量，
        # 使用现有寮相关任务的页面识别流程。
        if not self.wait_until_appear(self.I_CHECK_GUILD, wait_time=5):
            raise ScriptError('Guild information page was not recognized before medal donation')
        logger.info('Guild page recognized, start guild medal donation')
        sleep(0.8)
        # 达到每日上限的账号不会打开捐赠弹窗，游戏只会在点击寮信息页加号后
        # 显示提示。按照任务规则，检测到这种情况时视为已完成。
        if not self.click(self.C_DT_GUILD_MEDAL_OPEN, interval=0.8):
            raise ScriptError('Guild medal donation entry was not clicked')
        if self._wait_guild_medal_reward(timeout=0.8):
            return self._finish_guild_medal_donate(target)

        current = self._wait_guild_medal_amount(timeout=1.5)
        if current is None:
            # 已捐赠或达到每日上限时，点击入口不会打开金额弹窗。
            # 再点击一次确认仍无弹窗后，按任务规则视为今日已完成。
            self.click(self.C_DT_GUILD_MEDAL_OPEN, interval=0.8)
            current = self._wait_guild_medal_amount(timeout=1.5)
            if current is None:
                if self._wait_guild_medal_reward(timeout=0.8):
                    return self._finish_guild_medal_donate(target)
                logger.info('Guild medal donation already completed or capped; mark done')
                return self._finish_guild_medal_donate(target)
        if current is None:
            raise ScriptError('Guild medal amount OCR failed after dialog opened')
        if current not in (20, 40, 60, 80, 100):
            self.click(self.C_DT_GUILD_MEDAL_OPEN, interval=0.8)
            if self._wait_guild_medal_reward(timeout=1.2):
                return self._finish_guild_medal_donate(target)
            raise ScriptError(f'Guild medal amount is invalid or capped: {current}')
        logger.info('Guild medal donation amount current=%s target=%s', current, target)

        # 弹窗横向滑块从左到右对应 20/40/60/80/100。
        # 现在直接拖动一次，最后仍以 OCR 校验结果为准。
        if (target - current) % 20:
            raise ScriptError(f'Guild medal amount is not a 20-step value: current={current}, target={target}')
        slider_y = 390
        slider_min_x = 515
        slider_max_x = 846
        current_x = round(slider_min_x + (current - 20) / 80 * (slider_max_x - slider_min_x))
        target_x = round(slider_min_x + (target - 20) / 80 * (slider_max_x - slider_min_x))
        if current_x != target_x:
            logger.info('Guild medal slider drag current=%s target=%s x=%s->%s', current, target, current_x, target_x)
            sleep(0.4)
            self.device.swipe(
                p1=(current_x, slider_y),
                p2=(target_x, slider_y),
                duration=0.6,
                control_name='dt_guild_medal_slider',
            )

        confirmed = self._wait_guild_medal_amount(timeout=2.0)
        if confirmed != target:
            logger.warning('Guild medal slider mismatch: target=%s actual=%s, retry drag', target, confirmed)
            if confirmed not in (20, 40, 60, 80, 100) or (target - confirmed) % 20:
                raise ScriptError(f'Guild medal amount confirmation failed: expected {target}, got {confirmed}')
            corrected_x = round(slider_min_x + (target - 20) / 80 * (slider_max_x - slider_min_x))
            current_x = round(slider_min_x + (confirmed - 20) / 80 * (slider_max_x - slider_min_x))
            sleep(0.4)
            self.device.swipe(
                p1=(current_x, slider_y),
                p2=(corrected_x, slider_y),
                duration=0.6,
                control_name='dt_guild_medal_slider_retry',
            )
            confirmed = self._wait_guild_medal_amount(timeout=2.0)
            if confirmed != target:
                raise ScriptError(f'Guild medal amount confirmation failed: expected {target}, got {confirmed}')
        if not self.click(self.C_DT_GUILD_MEDAL_CONFIRM, interval=0.8):
            raise ScriptError('Guild medal donation confirm button was not clicked')
        if not self._wait_guild_medal_reward():
            raise ScriptError('Guild medal donation reward was not recognized')
        return self._finish_guild_medal_donate(target)

    def run_one_summon(self):
        logger.hr('daily summon', 2)
        if self.config.daily_trifles.today_is_done('summon'):
            logger.info('Today is done, skip')
            return
        self.goto_page(page_summon)
        config = self.config.daily_trifles.trifles_config
        if config.summon_type == SummonType.default:
            self.summon_one(draw_mystery_pattern=config.draw_mystery_pattern)
            self.check_time()
        elif config.summon_type == SummonType.recall:
            self.summon_recall()
        self.back_summon_main()
        self.config.daily_trifles.done_record.summon_dt = datetime.now()

    def check_time(self):
        config = self.config.daily_trifles.trifles_config
        now = datetime.now()
        next_run = now + self.config.daily_trifles.scheduler.success_interval
        # 检查是否跨月（next_run的月份与当前月份不同）
        if next_run.month != now.month:
            # 跨月重置神秘图案触发状态
            if not config.draw_mystery_pattern:
                config.draw_mystery_pattern = True
                logger.info(
                    f"reset draw_mystery_pattern to True, next_run: {next_run}")
        else:
            # 如果还是在同一月份，则没必要再绘制神秘图案
            config.draw_mystery_pattern = False
        self.config.save()

    def summon_recall(self):
        """
        确保在召唤界面,每日召唤一次
        召唤结束后回到 召唤主界面
        :return:
        """
        list = [self.O_SELECT_SM2, self.O_SELECT_SM3, self.O_SELECT_SM4]
        count = 0
        while True:
            count += 1

            for i in range(len(list)):
                sleep(1)
                self.goto_page(page_summon)
                self.appear_then_click(self.I_UI_BACK_RED, interval=1)
                x, y = list[i].coord()
                self.device.click(x, y)
                sleep(1)
                self.screenshot()
                if self.appear(self.I_RECALL_TICKET):
                    break
                logger.info("Select preset group RECALL")

            self.screenshot()
            if self.appear(self.I_RECALL_TICKET):
                break
            if count >= 3:
                self.config.notifier.push(title='今忆召唤抽卡失败', content='每日任务,今忆召唤抽卡失败!!!')
                return

        logger.info('Summon one RECALL')
        self.wait_until_appear(self.I_RECALL_TICKET)
        while True:
            ticket_info = self.O_RECALL_TICKET_AREA.ocr(self.device.image)
            # 处理 None 和空字符串
            if ticket_info is None or ticket_info == '':
                ticket_info = 0
            else:
                # 使用正则表达式提取字符串中的数字
                match = re.search(r'\d+', ticket_info)
                if match:
                    ticket_info = int(match.group())
                else:
                    logger.warning(f'Invalid ticket_info value: {ticket_info}, expected a numeric string')
                    ticket_info = 0  # 将无效值设置为默认值 0
            if ticket_info <= 0:
                logger.warning('There is no any one RECALL ticket')
                return
            # 某些情况下滑动异常
            self.S_RANDOM_SWIPE_1.name = 'S_RANDOM_SWIPE'
            self.S_RANDOM_SWIPE_2.name = 'S_RANDOM_SWIPE'
            self.S_RANDOM_SWIPE_3.name = 'S_RANDOM_SWIPE'
            self.S_RANDOM_SWIPE_4.name = 'S_RANDOM_SWIPE'
            while 1:
                self.screenshot()
                if self.appear(self.I_RECALL_ONE_TICKET):
                    break
                if self.appear_then_click(self.I_RECALL_TICKET, interval=1):
                    continue

            # 画一张票
            sleep(1)
            while 1:
                self.screenshot()
                if self.appear(self.I_RECALL_SM_CONFIRM, interval=0.6):
                    self.ui_click_until_disappear(self.I_RECALL_SM_CONFIRM)
                    break
                if self.appear(self.I_SM_CONFIRM_2, interval=0.6):
                    self.ui_click_until_disappear(self.I_SM_CONFIRM_2)
                    break
                if self.appear(self.I_RECALL_ONE_TICKET, interval=1):
                    # 某些时候会点击到 “语言召唤”
                    if self.appear_then_click(self.I_UI_CANCEL, interval=0.8):
                        continue
                    self.summon()
                    continue
            logger.info('Summon one success')

    def run_guild_donate(self):
        logger.hr('guild donate', 2)
        if self.config.daily_trifles.today_is_done('guild_donate'):
            logger.info('Today is done, skip')
            return
        self.goto_page(page_guild_wish)
        timeout_timer = Timer(2).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear(self.I_DT_GW_THANKS):
                self.ui_click(self.I_DT_GW_THANKS, self.I_DT_GW_THANKED, interval=0.8)
                timeout_timer.reset()
                continue
        self.appear_then_click(self.I_UI_BACK_RED)
        donate_datas: list = [
            (self.config.daily_trifles.guild_donate.guild_member_list_v,
             lambda : self.switch_select(self.I_DT_GW_GUILD_MEMBER_SELECTED, self.I_DT_GW_FRIEND_SELECTED, self.I_DT_GW_SELECT_GUILD_MEMBER),
             self.config.daily_trifles.guild_donate.name_check),
            (self.config.daily_trifles.guild_donate.friend_list_v,
             lambda : self.switch_select(self.I_DT_GW_FRIEND_SELECTED, self.I_DT_GW_GUILD_MEMBER_SELECTED, self.I_DT_GW_SELECT_FRIEND),
             self.config.daily_trifles.guild_donate.name_check)
        ]
        all_done = True
        for name_list, switch_func, name_check in donate_datas:
            all_done = all_done and self.donate(name_list, switch_func, name_check)
        if self.config.daily_trifles.guild_donate.auto_get_rewards:
            self.guild_donate_get_reward()
        self.config.daily_trifles.done_record.guild_donate_finish = all_done
        self.goto_page(page_main)

    def guild_donate_get_reward(self):
        """领取捐赠碎片的奖励"""
        timeout_timer = Timer(3).start()
        has_reward = False
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear(self.I_UI_BACK_RED, interval=0.6):
                break
            if self.appear(self.I_DT_GW_DONATE_RECORD_RED):
                self.ui_click(self.I_DT_GW_DONATE_RECORD, self.I_UI_BACK_RED, interval=1.2)
                has_reward = True
                continue
        if not has_reward:
            logger.info('No reward can get, exit')
            return
        timeout_timer.reset()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.6):
                continue
            if self.appear(self.I_DT_GW_DONATE_RECORD_THANKS):  # 受赠界面的一键感谢
                self.ui_get_reward(self.I_DT_GW_DONATE_RECORD_THANKS)
                timeout_timer.reset()
                continue
            if self.appear(self.I_DT_GW_DONATE_RED, interval=2.5):  # 赠予界面的一键领取
                self.ui_click(self.I_DT_GW_GIVE, self.I_DT_GW_ONE_COLLECT)
                self.appear_then_click(self.I_DT_GW_ONE_COLLECT, interval=0.6)
                timeout_timer.reset()
                continue
        self.ui_click_until_disappear(self.I_UI_BACK_RED)

    def donate(self, name_list: List[str], switch_func: Callable, name_check: bool) -> bool:
        """执行碎片捐赠流程

        :param name_list: 待捐赠碎皮的名称列表
        :param switch_func: 切换好友/阴阳寮/...的方法
        :param name_check: 是否使用ocr检查用户名
        :return: 是否全部捐赠成功 (出现检索名称后为空或者碎皮不足都是False, 仅全部捐成功才是True)
        """
        all_done = True
        for name in name_list:
            switch_func()
            self.swipe(self.S_DT_GW_OPEN_SEARCH, interval=1.2)  # 向下滑动拉出搜索框
            # 从按照交换搜索切换到按名称搜索
            self.switch_select(self.I_DT_GW_SEARCH_BY_NAME, self.I_DT_GW_SEARCH_BY_SWAP, self.I_DT_GW_SELECT_BY_NAME)
            self.appear_then_click(self.I_DT_GW_CLEAR_SEARCH)  # 清除搜索框内容
            self.ui_click(self.C_DT_GW_INPUT_SEARCH, self.I_DT_GW_CONFIRM, interval=1.5)  # 点击搜索框
            self.click(self.C_DT_GW_CLICK_INPUT)  # 点击名称输入框
            self.device.adb.send_keys(name)  # 输入名称
            self.ui_click_until_disappear(self.I_DT_GW_CONFIRM, interval=1.5)  # 点击确定
            donate_btn = self.I_DT_GW_DONATE
            if name_check:  # 若有多个相同前缀名称, 则需要取出一样的或最相近的名称
                name_roi = self.find_target_name(name)
                if name_roi is None:
                    logger.warning(f'{name} check failed, maybe not wish or not find')
                    all_done = False
                    continue
                # 设置赠与按钮back与对应name同一行
                donate_btn.roi_back = [name_roi[0], name_roi[1] - 15, max(name_roi[2] + 700, 1280),
                                       max(name_roi[3] + 60, 720)]
            self.I_DT_GW_FULL.roi_back = donate_btn.roi_back  # 设置已捐满标志back区域和赠与按钮同一行
            self.I_DT_GW_INSUFFICIENT.roi_back = donate_btn.roi_back  # 设置碎片不足标志back区域和赠与按钮同一行
            donate_ret = self.process_donate(donate_btn, name)
            all_done = all_done and donate_ret  # 有一次没成功则all_done永远False
        return all_done

    def process_donate(self, donate_btn: RuleImage, name: str) -> bool:
        """捐赠式神碎片

        :param name: 被捐方名称
        :param donate_btn: 赠与按钮
        :return: 捐赠是否成功
        """
        timeout_timer = Timer(3).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.6):
                continue
            if self.appear(self.I_DT_GW_SEARCH_EMPTY):
                logger.warning('Maybe not wish or not find, skip')
                if self.config.daily_trifles.guild_donate.notify_enable:
                    self.config.notifier.push(title='好友搜索失败', content=f'{name} 搜索失败, 没有搜索到对应用户, 无法捐赠')
                return False
            if self.appear_then_click(donate_btn, interval=0.6):
                timeout_timer.reset()
                continue
            if self.appear(self.I_DT_GW_INSUFFICIENT, interval=0.6):
                logger.warning('Not enough fragment to donate, skip')
                if self.config.daily_trifles.guild_donate.notify_enable:
                    self.config.notifier.push(title='捐赠碎片不足', content=f'捐给{name}的碎片不足, 请上线查看')
                return False
            if self.appear(self.I_DT_GW_FULL, interval=1.2):
                logger.info(f'Donate success!')
                return True
        return False

    def find_target_name(self, name) -> List[int]:
        """寻找目标名称
        :param name: 名称
        :return: [x, y, w, h]
        """
        timeout_timer = Timer(3).start()
        name_roi: List[int] = None
        # TODO: 这里只找了第一页, 若相似名称过多后续需要添加翻页继续找功能
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear(self.I_DT_GW_SEARCH_EMPTY):  # 空的直接退出
                if self.config.daily_trifles.guild_donate.notify_enable:
                    self.config.notifier.push(title='好友搜索失败', content=f'没有搜索到对应用户 {name}, 无法捐赠')
                return None
            text_results = self.O_DT_GW_NAME.detect_and_ocr(self.device.image)
            mx_similarity = 0.5
            for result in text_results:
                if result.ocr_text == name:
                    return self.extract_roi(result)  # 名称一模一样则直接返回
                similarity = difflib.SequenceMatcher(None, result.ocr_text, name).ratio()
                if similarity > mx_similarity:
                    mx_similarity = similarity
                    name_roi = self.extract_roi(result)
            if name_roi is None:
                continue
            return name_roi  # 找到了直接退出
        return name_roi

    def extract_roi(self, result: BoxedResult) -> list[int]:
        """从ocr结果提取对应的roi坐标"""
        x = self.O_DT_GW_NAME.roi[0] + result.box[0, 0]
        y = self.O_DT_GW_NAME.roi[1] + result.box[0, 1]
        w, h = result.box[1, 0] - result.box[0, 0], result.box[2, 1] - result.box[0, 1]
        return [x, y, w, h]

    def switch_select(self, target: RuleImage, other: RuleImage, select: RuleImage):
        """切换选中的元素"""
        while True:
            self.screenshot()
            if self.appear(target):
                break
            if self.appear_then_click(select, interval=0.6):
                continue
            if self.appear_then_click(other, interval=1.8):
                continue

    def run_luck_msg(self):
        logger.hr('luck msg', 2)
        if self.config.daily_trifles.today_is_done('luck_msg'):
            logger.info('Today is done, skip')
            return
        self.goto_page(page_friends_luck)
        logger.info('Start luck msg')
        check_timer = Timer(2)
        check_timer.start()
        while 1:
            self.screenshot()

            if self.appear_then_click(self.I_CLICK_BLESS, interval=1):
                continue
            if self.appear_then_click(self.I_ONE_CLICK_BLESS, interval=1):
                continue
            if self.ui_reward_appear_click():
                logger.info('Get reward of luck msg')
                break
            if check_timer.reached():
                logger.warning('There is no any luck msg')
                break

        self.goto_page(page_main)
        self.config.daily_trifles.done_record.luck_msg_dt = datetime.now()

    def run_store(self):
        con = self.config.daily_trifles.trifles_config
        self._active_daily_subtask = "store_sign" if con.store_sign else "buy_sushi"
        if self.check_store_all_done():
            logger.info('Store all done, skip')
            self._active_daily_subtask = ""
            return
        self.goto_page(page_mall, confirm_wait=3)
        if con.store_sign:
            self._run_daily_subtask("store_sign", self.run_store_sign)
        if con.buy_sushi_count > 0:
            self._run_daily_subtask("buy_sushi", self.run_buy_sushi)
        self.goto_page(page_main)
        self._active_daily_subtask = ""

    def run_store_sign(self):
        logger.hr('store sign', 2)
        if self.config.daily_trifles.today_is_done('store_sign'):
            logger.info('Today is done, skip')
            return
        self.config.daily_trifles.done_record.store_sign_dt = datetime.now()
        self.goto_page(page_store_gift_room)
        self.screenshot()
        self.appear_then_click(self.I_GIFT_RECOMMEND, interval=1)
        logger.info('Enter store sign')
        sleep(1)  # 等个动画
        self.screenshot()
        if not self.appear(self.I_GIFT_SIGN):
            logger.warning('There is no gift sign')
            return

        if self.ui_get_reward(self.I_GIFT_SIGN, click_interval=2.5):
            logger.info('Get reward of gift sign')

    def run_buy_sushi(self):
        logger.hr('store sushi', 2)
        if self.config.daily_trifles.today_is_done('sushi'):
            logger.info('Today is done, skip')
            return
        # 进入Special
        while 1:
            from tasks.WeeklyPurchase.assets import WeeklyPurchaseAssets
            self.screenshot()
            if self.appear(WeeklyPurchaseAssets.I_SIDE_CHECK_SPECIAL):
                break
            if self.appear_then_click(WeeklyPurchaseAssets.I_MALL_SUNDRY, interval=1):
                continue


        def detect_buy_count(base_element) -> (int, int):
            # 返回count,price
            MAX_PRICE = 9999
            MAX_COUNT = 9999
            roi = copy.deepcopy(base_element.roi_front)
            roi[0] = roi[0] + roi[2]
            roi[1] = roi[1] + roi[3] - 30
            roi[2] = 60
            roi[3] = 30
            self.O_STORE_SUSHI_PRICE.roi = roi
            _price = self.O_STORE_SUSHI_PRICE.detect_text(self.device.image)
            # 保守策略，避免OCR错误购买
            try:
                _price = int(_price)
            except Exception as e:
                _price = MAX_PRICE

            if _price < 60:
                return 0, MAX_PRICE
            _count = (_price - 60) / 20
            return _count, _price

        roi = None
        # 购买体力
        while 1:
            self.screenshot()
            # count, price = detect_buy_count(roi)
            # if count >= self.config.model.daily_trifles.trifles_config.buy_sushi_count:
            #     break
            if self.appear(self.I_STORE_COST_TYPE_JADE):
                count, price = detect_buy_count(self.I_STORE_COST_TYPE_JADE)
                if count >= self.config.daily_trifles.trifles_config.buy_sushi_count:
                    break
                self.ui_click_until_disappear(self.I_STORE_COST_TYPE_JADE, interval=2)
                logger.info(f"Buy Sushi With {price} Jade")
                continue

            if self.appear(self.I_SPECIAL_SUSHI):
                # 此处确定当前购买体力所需勾玉数量的位置,用于后续识别
                count, price = detect_buy_count(self.I_SPECIAL_SUSHI)
                if count >= self.config.daily_trifles.trifles_config.buy_sushi_count:
                    break
                self.ui_click(self.I_SPECIAL_SUSHI, stop=self.I_STORE_COST_TYPE_JADE, interval=2)
                continue
        self.config.daily_trifles.done_record.sushi_dt = datetime.now()

    @staticmethod
    def _current_courtyard_period() -> str | None:
        """返回当前庭院事务时间段。"""
        current = datetime.now().time()
        if time(5, 0) <= current < time(18, 0):
            return 'morning'
        if time(18, 0) <= current:
            return 'evening'
        return None

    def run_courtyard_affairs(self, period: str = 'morning'):
        """执行指定时间段的庭院事务。"""
        if period not in {'morning', 'evening'}:
            raise ValueError(f'无效庭院事务时间段: {period}')
        mode = f'courtyard_{period}'
        if self.config.daily_trifles.today_is_done(mode):
            logger.info('Courtyard %s already completed today, skip', period)
            return
        logger.hr('courtyard affairs', 2)

        def finish_courtyard_affairs():
            now = datetime.now()
            setattr(self.config.daily_trifles.done_record, f'{mode}_dt', now)
            # 保留旧字段，兼容原有每日琐事状态读取。
            self.config.daily_trifles.done_record.courtyard_affairs_dt = now
            try:
                returned = self.goto_page(page_main)
            except Exception as exc:
                returned = False
                logger.warning('Courtyard affairs return to main error, mark completed: %s', exc)
            if not returned:
                # 庭院事务入口处理后可能发生变化，避免失败状态触发再次进入误点。
                logger.warning('Courtyard affairs return to main failed, mark completed')

        self.goto_page(page_main)
        timeout_timer = Timer(5).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear(self.I_ENTER_COURTYARD_AFFAIRS, interval=1.2):
                self.goto_page(page_courtyard_affairs)
                timeout_timer.reset()
                break
        if timeout_timer.reached():
            logger.info('Courtyard affairs entry not found, mark completed')
            finish_courtyard_affairs()
            return
        while True:
            self.screenshot()
            if self.appear(self.I_CHECK_IN_DAILY, interval=0.5):
                break
            if self.appear_then_click(self.I_ENTER_DAILY, interval=1):
                continue

        def close_reward_and_wait_page(timeout: float = 6.0) -> bool:
            reward_clicked = False
            reward_timer = Timer(timeout).start()
            while not reward_timer.reached():
                self.screenshot()
                if reward_clicked and self.appear(self.I_CHECK_COURTYARD_AFFAIRS):
                    return True
                if not reward_clicked and self.appear(self.I_DAILYFFAIR_REWARD):
                    # 奖励弹窗会拦截本次点击，复用“一键完成”区域将其关闭。
                    self.click(self.I_ONE_COMPLETE)
                    reward_clicked = True
                    continue
                if reward_clicked:
                    # 点击未生效时有限重试，直到庭院事务页面重新出现。
                    self.click(self.I_ONE_COMPLETE, interval=1)
                    continue
            return False

        if not self.wait_until_appear(self.I_CHECK_COURTYARD_AFFAIRS, wait_time=3):
            logger.warning('Courtyard affairs page is not stable, mark completed')
            finish_courtyard_affairs()
            return
        if self.appear(self.I_IS_COMPLETE):
            logger.info('Courtyard affairs already completed')
            finish_courtyard_affairs()
            return

        for attempt in range(3):
            self.screenshot()
            if self.appear(self.I_IS_COMPLETE):
                logger.info('Courtyard affairs completed before attempt=%s', attempt + 1)
                finish_courtyard_affairs()
                return
            if not self.appear_then_click(self.I_ONE_COMPLETE, interval=1):
                logger.warning('Courtyard affairs complete button not found, attempt=%s', attempt + 1)
                continue
            try:
                reward_closed = close_reward_and_wait_page()
            except Exception as exc:
                reward_closed = False
                logger.warning('Courtyard affairs reward popup error, mark completed: %s', exc)
            if not reward_closed:
                logger.warning('Courtyard affairs reward popup failed, mark completed')
                finish_courtyard_affairs()
                return
            if self.wait_until_appear(self.I_IS_COMPLETE, wait_time=5):
                logger.info('Courtyard affairs completed, attempt=%s', attempt + 1)
                finish_courtyard_affairs()
                return
            logger.warning('Courtyard affairs is still incomplete, attempt=%s', attempt + 1)

        logger.warning('Courtyard affairs incomplete after three attempts, mark completed')
        finish_courtyard_affairs()

    def run_pickup_email(self):
        """领取邮件"""
        logger.hr('pick up email', 2)
        self.goto_page(page_main)
        timeout_timer = Timer(3).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear_then_click(self.I_DT_HARVEST_MAIL_COPY2, interval=1.2) or \
                    self.appear_then_click(self.I_HARVEST_MAIL, interval=1.2) or \
                    self.appear_then_click(self.I_HARVEST_MAIL_COPY, interval=1.2):
                continue
            if self.appear_then_click(self.I_HARVEST_MAIL_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_HARVEST_MAIL_ALL, interval=2):
                timeout_timer.reset()
                continue
            if self.appear_then_click(self.I_READ_ALL_MAIL, interval=3):
                continue
        self.goto_page(page_main)
        self.config.daily_trifles.done_record.pickup_email_dt = datetime.now()

    def plan_next_dt(self):
        # 定时领体力（每天 12-14、20-22 时内各有 20 体力）
        now = datetime.now()
        # 如果时间在00:00-12:00之间则设定时间为当日 12 时
        if now.time() < time(12, 0):
            self.custom_next_run(task='DailyTrifles', custom_time=Time(12, 0), time_delta=0)
        # 如果时间在12:00-20:00之间则设定时间为当日 20 时
        elif time(12, 0) <= now.time() < time(20, 0):
            self.custom_next_run(task='DailyTrifles', custom_time=Time(20, 0), time_delta=0)
        # 如果时间在20:00-23:59之间则设定时间为次日 12 时
        else:
            self.custom_next_run(task='DailyTrifles', custom_time=Time(12, 0), time_delta=1)

    def check_store_all_done(self) -> bool:
        """判断商店任务是否都做完了, 做完了则不再进入商店"""
        if self.config.daily_trifles.trifles_config.store_sign and not self.config.daily_trifles.today_is_done('store_sign'):
            return False
        if self.config.daily_trifles.trifles_config.buy_sushi_count > 0 and not self.config.daily_trifles.today_is_done('sushi'):
            return False
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas2')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run_guild_donate()
