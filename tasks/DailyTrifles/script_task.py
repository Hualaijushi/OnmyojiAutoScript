# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import copy
from time import sleep

import difflib
from datetime import time, datetime, timedelta
from module.atom.image import RuleImage
from module.base.utils.random import random_delay, random_int
from module.click_pipeline import FinalPoint, execute_single_click
from module.interaction_policy import InteractionPolicy, resolve_reaction_range
from module.ocr.common import BoxedResult

from tasks.Component.config_base import Time
from tasks.DailyTrifles.page import page_store_gift_room, page_friends_luck, page_guild_wish

from tasks.GameUi.default_pages import random_click
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_summon, page_guild, page_mall, page_friends, page_courtyard_affairs
from tasks.DailyTrifles.config import DailyTriflesConfig
from tasks.DailyTrifles.assets import DailyTriflesAssets
from tasks.Restart.assets import RestartAssets
from tasks.Component.Summon.summon import Summon
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets

from module.logger import logger
from module.exception import TaskEnd
from module.base.timer import Timer
from tasks.DailyTrifles.config import SummonType
import re
from typing import Any, Optional, List, Callable


class ScriptTask(GameUi, Summon, DailyTriflesAssets):
    # 领取邮件：邮箱里没有可操作按钮的持续秒数（认为领完）、两次「打开邮箱」点击的最小间隔（展开动画）、
    # 打开邮箱的最多点击次数、「一键领取」始终没有出现确认弹窗的最多点击次数、整段流程的总时限（都是故障边界）
    PICKUP_IDLE = 3
    PICKUP_OPEN_GAP = 3
    PICKUP_OPEN_TRIES = 3
    PICKUP_ALL_TRIES = 6
    PICKUP_TIMEOUT = 60
    # 领完之后点关闭叉退出邮箱的最长等待、已经进过邮箱却一直看不到邮箱标志（弹窗 / 全屏页没关掉）时的最长等待
    PICKUP_EXIT_TIMEOUT = 6
    PICKUP_LOST_TIMEOUT = 10
    # 每种弹窗 / 关闭按钮最多点几次：弹窗点了不消失时不能无限点（同名按钮 15 条记录里 ≥10 次会触发点击守卫报错），超过就放弃
    PICKUP_POPUP_TRIES = 5
    # 吉闻：每点一次祝福就重新计时，奖励弹窗比点击晚出来也能等到
    LUCK_IDLE = 3
    LUCK_TIMEOUT = 20
    LUCK_REWARD_CLOSE_TIMEOUT = 5
    LUCK_FRIENDSHIP_MAX = 3
    # 庭院事务（流程照 synevo 分支）
    COURTYARD_ENTRY_WAIT = 5
    COURTYARD_TAB_TIMEOUT = 10
    COURTYARD_ROUNDS = 3
    COURTYARD_BUTTON_WAIT = 3
    COURTYARD_REWARD_TIMEOUT = 6
    COURTYARD_COMPLETE_WAIT = 5
    # 庭院体力寿司：12 点、20 点出现，2 小时后消失；每个时段只检查一次，没有寿司也记已处理
    SUSHI_FIND_WAIT = 5
    # 原来没有本地上限的循环
    SWITCH_TIMEOUT = 10
    STORE_SIGN_WAIT = 3
    SUSHI_ENTER_TIMEOUT = 15
    SUSHI_BUY_TIMEOUT = 60
    SUSHI_DIALOG_WAIT = 10
    # 商店买体力：第一次 60 勾玉，之后每次 +20
    SUSHI_FIRST_PRICE = 60
    SUSHI_PRICE_STEP = 20
    RECALL_STEP_TIMEOUT = 15

    def run(self):
        con = self.config.daily_trifles.trifles_config
        # 寿司只在两个 2 小时的时段里有，放在最前面
        if con.courtyard_sushi:
            sushi_period = self._current_sushi_period()
            if sushi_period is not None:
                self.run_courtyard_sushi(sushi_period)
        # 每日召唤
        if con.one_summon:
            self.run_one_summon()
        if con.courtyard_affairs:
            period = self._current_courtyard_period()
            if period is None:
                logger.info('Courtyard affairs refresh at 05:00, skip before that')
            else:
                self.run_courtyard_affairs(period)
        if con.pickup_email:
            self.run_pickup_email()
        if self.config.daily_trifles.guild_donate.enable:
            self.run_guild_donate()
        # 吉闻
        if con.luck_msg:
            self.run_luck_msg()
        # 商店签到 or 购买寿司
        if con.store_sign or con.buy_sushi_count > 0:
            self.run_store()
        self.config.save()
        self.plan_next_dt()
        raise TaskEnd('DailyTrifles')

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
                self.appear_then_click(self.I_UI_BACK_RED, interval=1, policy=InteractionPolicy.NAVIGATION)
                self._click_recall_preset(list[i])
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
        if not self.wait_until_appear(self.I_RECALL_TICKET, wait_time=self.RECALL_STEP_TIMEOUT):
            logger.warning('Recall ticket not found, stop recall summon')
            return
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
            step_timer = Timer(self.RECALL_STEP_TIMEOUT).start()
            while 1:
                self.screenshot()
                if self.appear(self.I_RECALL_ONE_TICKET):
                    break
                if step_timer.reached():
                    logger.warning('Recall single draw not found, stop recall summon')
                    return
                if self.appear_then_click(self.I_RECALL_TICKET, interval=1, policy=InteractionPolicy.NORMAL):
                    continue

            # 画一张票
            sleep(1)
            step_timer.reset()
            while 1:
                self.screenshot()
                if self.appear(self.I_RECALL_SM_CONFIRM, interval=0.6):
                    self.ui_click_until_disappear(self.I_RECALL_SM_CONFIRM, policy=InteractionPolicy.CONFIRM)
                    break
                if self.appear(self.I_SM_CONFIRM_2, interval=0.6):
                    self.ui_click_until_disappear(self.I_SM_CONFIRM_2, policy=InteractionPolicy.CONFIRM)
                    break
                if step_timer.reached():
                    logger.warning('Recall summon result not confirmed, stop recall summon')
                    return
                if self.appear(self.I_RECALL_ONE_TICKET, interval=1):
                    # 某些时候会点击到 “语言召唤”
                    if self.appear_then_click(self.I_UI_CANCEL, interval=0.8, policy=InteractionPolicy.CONFIRM):
                        continue
                    self.summon()
                    step_timer.reset()
                    continue
            logger.info('Summon one success')

    def _click_recall_preset(self, preset):
        """点今忆召唤的预设分组：固定坐标，没有能在新截图里再确认的目标，只在点击前加 NORMAL 反应时间。

        单独成方法：同一函数里先有本地 random_delay、后有带 policy 的点击，会被 L2 守卫当成叠加反应。
        """
        x, y = preset.coord()
        sleep(random_delay(*resolve_reaction_range(InteractionPolicy.NORMAL)))
        # 原写法未传 control_name（Control 默认 'Click'），迁移后保持不传，日志 / trace 名字不变
        execute_single_click(self.device, FinalPoint(x, y))

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
                self.ui_click(self.I_DT_GW_THANKS, self.I_DT_GW_THANKED, interval=0.8, policy=InteractionPolicy.NORMAL)
                timeout_timer.reset()
                continue
        self.appear_then_click(self.I_UI_BACK_RED, policy=InteractionPolicy.NAVIGATION)
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
            # 先执行再合并：写成 all_done and self.donate(...) 会在寮友名单失败后短路，好友名单就不执行了
            ok = self.donate(name_list, switch_func, name_check)
            all_done = all_done and ok
        if self.config.daily_trifles.guild_donate.auto_get_rewards:
            self.guild_donate_get_reward()
        # today_is_done('guild_donate') 按这个日期判断当天；以前没写，开启后一天每次运行都会重新捐
        self.config.daily_trifles.done_record.guild_donate_dt = datetime.now()
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
                self.ui_click(self.I_DT_GW_DONATE_RECORD, self.I_UI_BACK_RED, interval=1.2, policy=InteractionPolicy.NORMAL)
                has_reward = True
                continue
        if not has_reward:
            logger.info('No reward can get, exit')
            return
        timeout_timer.reset()
        while not timeout_timer.reached():
            self.screenshot()
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.6, policy=InteractionPolicy.CONFIRM):
                continue
            if self.appear(self.I_DT_GW_DONATE_RECORD_THANKS):  # 受赠界面的一键感谢
                self.ui_get_reward(self.I_DT_GW_DONATE_RECORD_THANKS, policy=InteractionPolicy.NORMAL, close_policy=InteractionPolicy.NAVIGATION)
                timeout_timer.reset()
                continue
            if self.appear(self.I_DT_GW_DONATE_RED, interval=2.5):  # 赠予界面的一键领取
                self.ui_click(self.I_DT_GW_GIVE, self.I_DT_GW_ONE_COLLECT, policy=InteractionPolicy.FAST)
                self.appear_then_click(self.I_DT_GW_ONE_COLLECT, interval=0.6, policy=InteractionPolicy.NORMAL)
                timeout_timer.reset()
                continue
        self.ui_click_until_disappear(self.I_UI_BACK_RED, policy=InteractionPolicy.NAVIGATION)

    def donate(self, name_list: List[str], switch_func: Callable, name_check: bool) -> bool:
        """执行碎片捐赠流程

        :param name_list: 待捐赠碎皮的名称列表
        :param switch_func: 切换好友/阴阳寮/...的方法
        :param name_check: 是否使用ocr检查用户名
        :return: 是否全部捐赠成功 (出现检索名称后为空或者碎皮不足都是False, 仅全部捐成功才是True)
        """
        all_done = True
        for name in name_list:
            if not switch_func():
                logger.warning('Cannot switch guild wish tab, skip the rest of this list')
                return False
            self.swipe(self.S_DT_GW_OPEN_SEARCH, interval=1.2)  # 向下滑动拉出搜索框
            # 从按照交换搜索切换到按名称搜索
            if not self.switch_select(self.I_DT_GW_SEARCH_BY_NAME, self.I_DT_GW_SEARCH_BY_SWAP,
                                      self.I_DT_GW_SELECT_BY_NAME):
                logger.warning(f'Cannot switch to search by name, skip {name}')
                all_done = False
                continue
            self.appear_then_click(self.I_DT_GW_CLEAR_SEARCH, policy=InteractionPolicy.FAST)  # 清除搜索框内容
            self.ui_click(self.C_DT_GW_INPUT_SEARCH, self.I_DT_GW_CONFIRM, interval=1.5, policy=InteractionPolicy.NORMAL)  # 点击搜索框
            self.click(self.C_DT_GW_CLICK_INPUT, policy=InteractionPolicy.NORMAL)  # 点击名称输入框
            self.device.adb.send_keys(name)  # 输入名称
            self.ui_click_until_disappear(self.I_DT_GW_CONFIRM, interval=1.5, policy=InteractionPolicy.CONFIRM)  # 点击确定
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
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.6, policy=InteractionPolicy.CONFIRM):
                continue
            if self.appear(self.I_DT_GW_SEARCH_EMPTY):
                logger.warning('Maybe not wish or not find, skip')
                if self.config.daily_trifles.guild_donate.notify_enable:
                    self.config.notifier.push(title='好友搜索失败', content=f'{name} 搜索失败, 没有搜索到对应用户, 无法捐赠')
                return False
            if self.appear_then_click(donate_btn, interval=0.6, policy=InteractionPolicy.NORMAL):
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

    def switch_select(self, target: RuleImage, other: RuleImage, select: RuleImage) -> bool:
        """切换选中的元素；超时返回 False"""
        timer = Timer(self.SWITCH_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(target):
                return True
            if self.appear_then_click(select, interval=0.6, policy=InteractionPolicy.FAST):
                continue
            if self.appear_then_click(other, interval=1.8, policy=InteractionPolicy.FAST):
                continue
        logger.warning(f'Switch to {target.name} timeout')
        return False

    def run_luck_msg(self):
        logger.hr('luck msg', 2)
        if self.config.daily_trifles.today_is_done('luck_msg'):
            logger.info('Today is done, skip')
            return
        if self.goto_page(page_friends_luck) is False:
            # 页面没进去不算「没有吉闻」，不记已处理
            logger.warning('Luck msg page not entered, not recorded')
            return
        logger.info('Start luck msg')
        # 每点一次祝福就重新计时：奖励弹窗常在最后一次点击之后才出来，旧写法 2 秒一到就离开，
        # 回庭院时的点击落在奖励框里的道具上，留下道具说明框挡住庭院（10-16 两个号都因此重启）
        idle_timer = Timer(self.LUCK_IDLE).start()
        total_timer = Timer(self.LUCK_TIMEOUT).start()
        got_reward = False
        reward_closed = True
        friendship_closed = 0
        while not total_timer.reached():
            self.screenshot()
            if self.appear(self.I_UI_REWARD, threshold=0.6):
                got_reward = True
                reward_closed = self._close_luck_reward()
                break
            # 只关几次、也不重新计时：这张小模板只在固定位置找，万一误匹配也不能把循环拖长、连续点击
            if friendship_closed < self.LUCK_FRIENDSHIP_MAX and \
                    self.appear_then_click(self.I_FRIENDSHIP_UP, interval=1, policy=InteractionPolicy.NAVIGATION):
                friendship_closed += 1
                continue
            if self.appear_then_click(self.I_CLICK_BLESS, interval=1, policy=InteractionPolicy.NORMAL):
                idle_timer.reset()
                continue
            if self.appear_then_click(self.I_ONE_CLICK_BLESS, interval=1, policy=InteractionPolicy.NORMAL):
                idle_timer.reset()
                continue
            if idle_timer.reached():
                break

        self.goto_page(page_main)
        if got_reward and not reward_closed:
            # 奖励已出现但弹窗没关掉：明确的处理失败，不伪装成「没有奖励」，也不记已处理
            logger.warning('Luck msg reward popup did not close, not recorded')
            return
        if got_reward:
            logger.info('吉闻已领取，今日处理完成。')
        else:
            logger.info('未发现可领取吉闻，今日检查完成。')
        self.config.daily_trifles.done_record.luck_msg_dt = datetime.now()

    def _close_luck_reward(self) -> bool:
        """关吉闻的「获得奖励」。

        奖励框改版后，公共关闭区域 C_UI_REWARD 会点到框里的道具（弹出友情点 / 体力说明），
        这里改点屏幕下方空白；公共区域还有几十处在用，不动。
        """
        timer = Timer(self.LUCK_REWARD_CLOSE_TIMEOUT).start()
        while not timer.reached():
            if not self.appear(self.I_UI_REWARD, threshold=0.6):
                return True
            self.click(GeneralBattleAssets.C_RANDOM_BOTTOM, interval=1, policy=InteractionPolicy.NAVIGATION)
            self.screenshot()
        logger.warning('Luck msg reward popup did not close')
        return False

    def run_store(self):
        if self.check_store_all_done():
            logger.info('Store all done, skip')
            return
        self.goto_page(page_mall, confirm_wait=3)
        if self.config.daily_trifles.trifles_config.store_sign:
            self.run_store_sign()
        if self.config.daily_trifles.trifles_config.buy_sushi_count > 0:
            self.run_buy_sushi()
        self.goto_page(page_main)

    def run_store_sign(self):
        logger.hr('store sign', 2)
        if self.config.daily_trifles.today_is_done('store_sign'):
            logger.info('Today is done, skip')
            return
        self.goto_page(page_store_gift_room)
        self.screenshot()
        self.appear_then_click(self.I_GIFT_RECOMMEND, interval=1, policy=InteractionPolicy.FAST)
        logger.info('Enter store sign')
        # 等推荐页的动画；没有签到按钮按原规则当作今天已签
        if not self.wait_until_appear(self.I_GIFT_SIGN, wait_time=self.STORE_SIGN_WAIT):
            logger.warning('There is no gift sign, treat as signed today')
            self.config.daily_trifles.done_record.store_sign_dt = datetime.now()
            return

        self.ui_get_reward(self.I_GIFT_SIGN, click_interval=2.5, policy=InteractionPolicy.NORMAL, close_policy=InteractionPolicy.NAVIGATION)
        # ui_get_reward 超时也返回 True，所以领完要看签到按钮还在不在；还在就不记完成，下次运行再试
        self.screenshot()
        if self.appear(self.I_GIFT_SIGN):
            logger.warning('Gift sign is still there, retry next run')
            return
        logger.info('Get reward of gift sign')
        self.config.daily_trifles.done_record.store_sign_dt = datetime.now()

    def run_buy_sushi(self):
        """商店杂货 Special 里用勾玉买体力，买到设定次数。

        价格 = 60 + 20 × 今天已买次数，次数从价格反推，所以下次运行重试不会因为本地计数丢了而多买。
        读不出价格就停（宁可少买，不多花勾玉）；本次运行最多买「设定次数 − 开始时已买次数」次，不管之后读到什么。
        价格框、等列表加载、买完关「获得奖励」三处是 8 月 13 日 658f5a7d 的修复，被 8 月 18 日的合并 73bcafcb 冲掉过。
        """
        logger.hr('store sushi', 2)
        if self.config.daily_trifles.today_is_done('sushi'):
            logger.info('Today is done, skip')
            return
        target = self.config.daily_trifles.trifles_config.buy_sushi_count
        # 签到结束会停在礼包屋子页，先回商城主页再去杂货
        self.goto_page(page_mall)
        # 进入 Special，等到体力商品也出现（列表已加载）
        from tasks.WeeklyPurchase.assets import WeeklyPurchaseAssets
        enter_timer = Timer(self.SUSHI_ENTER_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear(WeeklyPurchaseAssets.I_SIDE_CHECK_SPECIAL) and self.appear(self.I_SPECIAL_SUSHI):
                break
            if enter_timer.reached():
                logger.warning('Cannot enter mall special page, skip buying sushi')
                return
            if self.appear_then_click(WeeklyPurchaseAssets.I_MALL_SUNDRY, interval=1, policy=InteractionPolicy.FAST):
                continue

        planned = None  # 本次运行最多买几次，第一次在列表上读到有效次数时定下
        bought = 0
        # 购买体力；超时或任何读不准的情况都不记完成，下次运行再试
        buy_timer = Timer(self.SUSHI_BUY_TIMEOUT).start()
        while 1:
            self.screenshot()
            if buy_timer.reached():
                logger.warning('Buying sushi timeout, retry next run')
                return
            if self.appear(self.I_STORE_COST_TYPE_JADE):
                count, price = self._read_sushi_bought(self.I_STORE_COST_TYPE_JADE)
                if count is None or planned is None or count >= target or bought >= planned:
                    logger.warning(f'Stop buying sushi in the purchase dialog: price={price}, '
                                   f'bought={bought}, planned={planned}, target={target}')
                    return
                # 买完会弹「获得奖励」盖住列表，要关掉才能继续
                self.ui_get_reward(self.I_STORE_COST_TYPE_JADE, click_interval=2.5, policy=InteractionPolicy.CONFIRM, close_policy=InteractionPolicy.NAVIGATION)
                bought += 1
                logger.info(f'Buy Sushi With {price} Jade')
                continue

            if self.appear(self.I_SPECIAL_SUSHI):
                count, price = self._read_sushi_bought(self.I_SPECIAL_SUSHI)
                if count is None:
                    logger.warning(f'Cannot read sushi price ({price}), stop buying and retry next run')
                    return
                if count >= target:
                    logger.info(f'Already bought sushi {count} times')
                    break
                if planned is None:
                    planned = target - count
                elif bought >= planned:
                    logger.warning(f'Bought {bought} times this run but the price shows {count}, '
                                   f'stop and retry next run')
                    return
                if not self.ui_click_until_appear_or_timeout(self.I_SPECIAL_SUSHI, stop=self.I_STORE_COST_TYPE_JADE,
                                                             interval=2, timeout=self.SUSHI_DIALOG_WAIT,
                                                             policy=InteractionPolicy.NORMAL):
                    logger.warning('Sushi purchase dialog did not open, retry next run')
                    return
                continue
        self.config.daily_trifles.done_record.sushi_dt = datetime.now()

    def _read_sushi_bought(self, base_element) -> tuple[int | None, int | None]:
        """读 base_element 右侧的价格，返回 (今天已买次数, 价格)。

        读不出数字、或价格不是 60 + 20k 时次数为 None：以前低于 60 就当作「还没买」，
        少读一位（80 读成 8）会多买一次，连续读错会一直买。
        """
        roi = copy.deepcopy(base_element.roi_front)
        roi[0] = roi[0] + roi[2]
        roi[1] = roi[1] + roi[3] - 45
        roi[2] = 75
        roi[3] = 45
        self.O_STORE_SUSHI_PRICE.roi = roi
        text = self.O_STORE_SUSHI_PRICE.detect_text(self.device.image)
        try:
            price = int(text)
        except (TypeError, ValueError):
            return None, None
        if price < self.SUSHI_FIRST_PRICE or (price - self.SUSHI_FIRST_PRICE) % self.SUSHI_PRICE_STEP:
            return None, price
        return (price - self.SUSHI_FIRST_PRICE) // self.SUSHI_PRICE_STEP, price

    @staticmethod
    def _current_sushi_period(now: datetime = None) -> str | None:
        """庭院体力寿司 12 点、20 点出现，2 小时后消失；返回当前所在时段，不在时段内返回 None。"""
        current = (now or datetime.now()).time()
        if time(12, 0) <= current < time(14, 0):
            return 'noon'
        if time(20, 0) <= current < time(22, 0):
            return 'evening'
        return None

    def run_courtyard_sushi(self, period: str):
        """点庭院上的体力寿司领「获得奖励」；每个时段只检查一次。

        领到、或正常进入庭院等过 `SUSHI_FIND_WAIT` 仍没有寿司，都记这个时段已处理；
        页面没进去、领完寿司仍在这类明确未完成的情况不记（也不再安排重试，下次正常运行再看）。
        """
        mode = f'courtyard_sushi_{period}'
        if self.config.daily_trifles.today_is_done(mode):
            logger.info(f'Courtyard sushi {period} already handled today, skip')
            return
        logger.hr('courtyard sushi', 2)
        if self.goto_page(page_main) is False:
            logger.warning('Courtyard main page not entered, sushi not recorded')
            return
        # 庭院上的式神会走动，可能挡住寿司，多等几秒
        if not self.wait_until_appear(self.I_COURTYARD_SUSHI, wait_time=self.SUSHI_FIND_WAIT):
            logger.info(f'未发现可领取寿司，本时段（{period}）检查完成。')
            setattr(self.config.daily_trifles.done_record, f'{mode}_dt', datetime.now())
            return
        # 只在当前画面认出寿司时才点；奖励只有体力一个道具，用公共关闭区域即可（商店签到已验证）
        self.ui_get_reward(self.I_COURTYARD_SUSHI, click_interval=2, policy=InteractionPolicy.NORMAL, close_policy=InteractionPolicy.NAVIGATION)
        self.screenshot()
        if self.appear(self.I_COURTYARD_SUSHI):
            logger.warning('Courtyard sushi is still there after reward, not recorded')
            return
        logger.info(f'庭院寿司已领取，本时段（{period}）处理完成。')
        setattr(self.config.daily_trifles.done_record, f'{mode}_dt', datetime.now())

    @staticmethod
    def _current_courtyard_period(now: datetime = None) -> str | None:
        """庭院事务每天 05 点、18 点各刷新一次，返回当前所在时段；05 点之前返回 None。"""
        current = (now or datetime.now()).time()
        if time(5, 0) <= current < time(18, 0):
            return 'morning'
        if time(18, 0) <= current:
            return 'evening'
        return None

    def run_courtyard_affairs(self, period: str = 'morning'):
        """执行指定时段的庭院事务（流程照 synevo 分支，不含账号轮换部分）。

        逢魔最多出现 3 次现世首领，每出现一次都要重新一键完成才能领下一个奖励，所以最多点 3 轮，
        每轮关掉奖励页后看「全部完成」。各种失败也记完成，避免当天反复进入误点（synevo 的取舍）。
        """
        if period not in {'morning', 'evening'}:
            raise ValueError(f'无效庭院事务时间段: {period}')
        mode = f'courtyard_{period}'
        if self.config.daily_trifles.today_is_done(mode):
            logger.info(f'Courtyard {period} already completed today, skip')
            return
        logger.hr('courtyard affairs', 2)

        def finish_courtyard_affairs():
            now = datetime.now()
            setattr(self.config.daily_trifles.done_record, f'{mode}_dt', now)
            # 保留旧字段，兼容原有每日琐事状态读取
            self.config.daily_trifles.done_record.courtyard_affairs_dt = now
            try:
                returned = self.goto_page(page_main)
            except Exception as exc:
                returned = False
                logger.warning(f'Courtyard affairs return to main error, mark completed: {exc}')
            if not returned:
                logger.warning('Courtyard affairs return to main failed, mark completed')

        def close_reward_and_wait_page() -> bool:
            reward_clicked = False
            reward_timer = Timer(self.COURTYARD_REWARD_TIMEOUT).start()
            while not reward_timer.reached():
                self.screenshot()
                # 弹窗后面的庭院事务页照样认得出来，必须先处理弹窗
                if self._cancel_two_button_popup():
                    reward_timer.reset()
                    continue
                if reward_clicked and self.appear(self.I_CHECK_COURTYARD_AFFAIRS):
                    return True
                if not reward_clicked and self.appear(self.I_DAILYFFAIR_REWARD):
                    # 奖励页会拦截本次点击，复用「一键完成」的位置把它关掉
                    self.click(self.I_ONE_COMPLETE, policy=InteractionPolicy.NAVIGATION)
                    reward_clicked = True
                    continue
                if reward_clicked:
                    # 点击没生效时有限重试，直到庭院事务页重新出现
                    self.click(self.I_ONE_COMPLETE, interval=1, policy=InteractionPolicy.NAVIGATION)
                    continue
            return False

        self.goto_page(page_main)
        timeout_timer = Timer(self.COURTYARD_ENTRY_WAIT).start()
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
        tab_timer = Timer(self.COURTYARD_TAB_TIMEOUT).start()
        while True:
            self.screenshot()
            if self.appear(self.I_CHECK_IN_DAILY, interval=0.5):
                break
            if tab_timer.reached():
                logger.warning('Cannot switch to courtyard daily tab, mark completed')
                finish_courtyard_affairs()
                return
            if self.appear_then_click(self.I_ENTER_DAILY, interval=1, policy=InteractionPolicy.FAST):
                continue

        if not self.wait_until_appear(self.I_CHECK_COURTYARD_AFFAIRS, wait_time=3):
            logger.warning('Courtyard affairs page is not stable, mark completed')
            finish_courtyard_affairs()
            return
        if self.appear(self.I_IS_COMPLETE):
            logger.info('Courtyard affairs already completed')
            finish_courtyard_affairs()
            return

        for attempt in range(self.COURTYARD_ROUNDS):
            # 刚切到日常标签或现世首领提示还在时，按钮会晚一点出来；先等一会再判断，
            # 不然 3 轮会在一秒内用完、什么都没领就记完成（这里偏离 synevo 的写法，见 D031）
            button_timer = Timer(self.COURTYARD_BUTTON_WAIT).start()
            clicked = False
            while True:
                self.screenshot()
                if self.appear(self.I_IS_COMPLETE):
                    logger.info(f'Courtyard affairs completed before attempt={attempt + 1}')
                    finish_courtyard_affairs()
                    return
                # 弹窗开着时一键完成按钮照样认得出来，先关弹窗再点
                if self._cancel_two_button_popup():
                    button_timer.reset()
                    continue
                if self.appear_then_click(self.I_ONE_COMPLETE, interval=1, policy=InteractionPolicy.NORMAL):
                    clicked = True
                    break
                if button_timer.reached():
                    break
            if not clicked:
                logger.warning(f'Courtyard affairs complete button not found, attempt={attempt + 1}')
                continue
            try:
                reward_closed = close_reward_and_wait_page()
            except Exception as exc:
                reward_closed = False
                logger.warning(f'Courtyard affairs reward popup error, mark completed: {exc}')
            if not reward_closed:
                logger.warning('Courtyard affairs reward popup failed, mark completed')
                finish_courtyard_affairs()
                return
            if self.wait_until_appear(self.I_IS_COMPLETE, wait_time=self.COURTYARD_COMPLETE_WAIT):
                logger.info(f'Courtyard affairs completed, attempt={attempt + 1}')
                finish_courtyard_affairs()
                return
            logger.warning(f'Courtyard affairs is still incomplete, attempt={attempt + 1}')

        logger.warning(f'Courtyard affairs incomplete after {self.COURTYARD_ROUNDS} attempts, mark completed')
        finish_courtyard_affairs()

    def _cancel_two_button_popup(self) -> bool:
        """当前帧里「取消」「确认」两个小按钮都在时点「取消」。

        庭院事务一键完成时，结界里放的式神满级会弹「是否提取」（用户决定不提取）；
        只认两个按钮同时在的弹窗，单独一个取消按钮不算，也从不替用户点确认。
        """
        if not (self.appear(self.I_UI_CANCEL_SAMLL) and self.appear(self.I_UI_CONFIRM_SAMLL)):
            return False
        if self.appear_then_click(self.I_UI_CANCEL_SAMLL, interval=1, policy=InteractionPolicy.CONFIRM):
            logger.info('Cancel the two-button popup (e.g. max level shikigami in realm)')
            return True
        return False

    def _in_mailbox(self) -> bool:
        """当前帧是否在邮箱页面：「邮箱」标题或「系统邮件」标签打开状态任一出现即可（资源在 Restart 任务里，已按当前界面重新标注）。

        邮箱打开后顶栏的信封图标仍然露在边框上方，`I_DT_HARVEST_MAIL_COPY2` 照样能匹配，所以必须先判断是不是已经在邮箱里。
        """
        return self.appear(RestartAssets.I_HARVEST_MAIL_TITLE) or self.appear(RestartAssets.I_SYSTEM_MAIL_OPEN)

    def _pickup_popup(self, counts: dict) -> bool:
        """领取后可能弹出的弹窗，处理了返回 True。只在领取邮件流程里被调用（`counts` 是本次流程各弹窗的点击计数）。

        - 「是否立即启用…？」这类两个大按钮（取消 / 确定）同时在：只点取消（不改用户当前的设置），从不点确定；
        - 「获得插画」：点安全空白处关闭（没有关闭叉）。
        """
        if self.appear(self.I_UI_CANCEL) and self.appear(self.I_UI_CONFIRM):
            if self.appear_then_click(self.I_UI_CANCEL, interval=1, policy=InteractionPolicy.CONFIRM):
                counts['cancel'] = counts.get('cancel', 0) + 1
                logger.info('Pick up email: cancel the two-button popup (e.g. enable the new illustration now?)')
                return True
            return False
        if self.appear_then_click(self.I_GET_PICTURE, action=random_click(), interval=1.5, policy=InteractionPolicy.NORMAL):
            counts['picture'] = counts.get('picture', 0) + 1
            logger.info('Pick up email: close the get-illustration popup')
            return True
        return False

    def run_pickup_email(self):
        """领取邮件：打开邮箱 → 一键领取 → 处理弹窗 → 领完后点关闭叉退出邮箱。

        - **进过邮箱就一直算在邮箱流程里，直到自己点了退出**：领取后会出现确认 / 获得头像框 / 获得插画 / 「是否立即启用」等弹窗和全屏页，
          它们会盖住邮箱标志，不能因为这一帧看不到标志就认为离开了邮箱（更不能再去点「打开邮箱」按钮）；
        - 邮箱标志 = 「邮箱」标题或「系统邮件」标签打开状态任一出现；已在邮箱里不再点任何「打开邮箱」按钮
          （顶栏信封在邮箱打开后仍然露着，原先因此和「一键领取」来回点到点击守卫报错）；
        - 弹窗：领取确认的「确定」→ 点；两个大按钮的启用确认 → 只点取消；获得插画 → 点安全空白处；看不到邮箱标志时的红色关闭叉（头像框等全屏页）→ 点；
          每种最多点 `PICKUP_POPUP_TRIES` 次，点了不消失就放弃（不无限点、不触发点击守卫）；
        - 一键领取不再出现持续 `PICKUP_IDLE` 秒算领完，然后点邮箱自己的关闭叉退出（最多等 `PICKUP_EXIT_TIMEOUT` 秒，仍没退出由 `goto_page` 兜底）；
        - 打开邮箱最多点 `PICKUP_OPEN_TRIES` 次、间隔不少于 `PICKUP_OPEN_GAP`；一键领取点了 `PICKUP_ALL_TRIES` 次都没出现确认弹窗就放弃；
        - 邮箱始终没有确认打开、一键领取始终无效、总超时都**不记今天已完成**（下次运行再试）。
        """
        logger.hr('pick up email', 2)
        if self.config.daily_trifles.today_is_done('pickup_email'):
            logger.info('Today is done, skip')
            return
        self.goto_page(page_main)
        total = Timer(self.PICKUP_TIMEOUT).start()
        idle = Timer(self.PICKUP_IDLE)          # 邮箱里没有可操作按钮开始计时；一键领取 / 弹窗处理会清零
        open_gap = Timer(self.PICKUP_OPEN_GAP)
        exit_timer = Timer(self.PICKUP_EXIT_TIMEOUT)
        lost = Timer(self.PICKUP_LOST_TIMEOUT)  # 进过邮箱却看不到邮箱标志（弹窗 / 全屏页）开始计时
        opened = False                          # 看到过邮箱标志（只由标志置位：打开邮箱之前出现的「确定」之类弹窗不算）
        claimed = False                         # 邮箱里点过一键领取 / 确认弹窗
        popups = {}                             # 各弹窗 / 关闭按钮的点击次数
        finished = False
        gave_up = False
        open_clicks = 0
        all_clicks = 0
        while 1:
            self.screenshot()
            if total.reached():
                logger.warning('Pick up email: total timeout')
                gave_up = True
                break
            if any(count > self.PICKUP_POPUP_TRIES for count in popups.values()):
                logger.warning(f'Pick up email: a popup is still there after {self.PICKUP_POPUP_TRIES} clicks, give up: {popups}')
                gave_up = True
                break
            if self.appear_then_click(self.I_HARVEST_MAIL_CONFIRM, interval=1, policy=InteractionPolicy.CONFIRM):
                popups['confirm'] = popups.get('confirm', 0) + 1
                if opened:
                    claimed = True
                    all_clicks = 0
                idle.clear()
                lost.clear()
                continue
            if opened and not finished and self._pickup_popup(popups):
                idle.clear()
                lost.clear()
                continue
            if self._in_mailbox():
                opened = True
                lost.clear()
                if finished:
                    # 领完：点邮箱自己的关闭叉退出；等不到退出由 goto_page 兜底
                    if not exit_timer.started():
                        exit_timer.start()
                    if exit_timer.reached():
                        logger.warning('Pick up email: mailbox did not close, leave it to goto_page')
                        break
                    self.appear_then_click(self.I_UI_BACK_RED, interval=1.5, policy=InteractionPolicy.NAVIGATION)
                    continue
                if self.appear_then_click(self.I_HARVEST_MAIL_ALL, interval=2, policy=InteractionPolicy.NORMAL):
                    claimed = True
                    all_clicks += 1
                    if all_clicks > self.PICKUP_ALL_TRIES:
                        logger.warning(f'Pick up email: one-key claim clicked {self.PICKUP_ALL_TRIES} times '
                                       f'without a confirm popup, give up')
                        gave_up = True
                        break
                    idle.clear()
                    continue
                self.appear_then_click(self.I_READ_ALL_MAIL, interval=3, policy=InteractionPolicy.NORMAL)
                if not idle.started():
                    idle.start()
                if idle.reached():
                    finished = True             # 一键领取不再出现：领完了
                continue
            if opened:
                if finished:
                    break                       # 已经点了退出，邮箱标志消失：退出成功
                if self.appear(self.I_CHECK_MAIN):
                    break                       # 已经回到主界面（邮箱被关掉了）：不用再等
                # 进过邮箱但这一帧看不到邮箱标志（弹窗 / 全屏页）：仍算在邮箱流程里，不点「打开邮箱」；
                # 全屏页（获得头像框等）的红色关闭叉可以直接点
                if self.appear_then_click(self.I_UI_BACK_RED, interval=1.5, policy=InteractionPolicy.NAVIGATION):
                    popups['back'] = popups.get('back', 0) + 1
                    idle.clear()
                    lost.clear()
                    continue
                if not lost.started():
                    lost.start()
                if lost.reached():
                    logger.warning('Pick up email: mailbox markers not seen for a long time, leave it to goto_page')
                    break
                continue
            # 还没进邮箱：才点「打开邮箱」
            if open_gap.started() and not open_gap.reached():
                continue
            if open_clicks >= self.PICKUP_OPEN_TRIES:
                logger.warning(f'Pick up email: mailbox did not open after {open_clicks} clicks')
                gave_up = True
                break
            if self.appear_then_click(self.I_DT_HARVEST_MAIL_COPY2, interval=1.2, policy=InteractionPolicy.NORMAL) or \
                    self.appear_then_click(self.I_HARVEST_MAIL, interval=1.2, policy=InteractionPolicy.NORMAL) or \
                    self.appear_then_click(self.I_HARVEST_MAIL_COPY, interval=1.2, policy=InteractionPolicy.NORMAL):
                open_clicks += 1
                open_gap.reset()
        self.goto_page(page_main)
        if (finished or claimed) and not gave_up:
            self.config.daily_trifles.done_record.pickup_email_dt = datetime.now()
        else:
            logger.warning('Pick up email not finished, not marked as done')

    def next_daily_time(self, now: datetime) -> datetime:
        """日常下次时间：下一个服务器刷新时间（`scheduler.server_update`，默认 09:00）。

        每天开 OAS 时这个时间通常已过，每日琐事立刻到点、能最先跑；不随上一次运行漂移（不用「完成时间 + success_interval」：
        12 点 / 20 点那两次运行也会拖动锚点，随机延迟累计后每天往后漂）。
        """
        update = self.config.daily_trifles.scheduler.server_update
        today = now.replace(hour=update.hour, minute=update.minute, second=update.second, microsecond=0)
        return today if now < today else today + timedelta(days=1)

    @staticmethod
    def next_slot_time(now: datetime) -> datetime:
        """庭院寿司的时段点：今天 12:00、20:00，过了 20:00 就是明天 12:00（每天 12-14、20-22 时内各有 20 体力）。"""
        if now.time() < time(12, 0):
            return now.replace(hour=12, minute=0, second=0, microsecond=0)
        if now.time() < time(20, 0):
            return now.replace(hour=20, minute=0, second=0, microsecond=0)
        return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    def plan_next_dt(self):
        """下次运行 = 日常下次时间（下一个服务器刷新）与庭院寿司时段点中较早的一个，再加任务自己配置的随机延迟（`float_time`）。

        随机延迟在这里自己算、以 `server=False` 交给调度：公共 `task_delay` 只在 `server_update` 恰为 09:00 时才加延迟，
        换成别的值会把目标推到明天，会悄悄破坏 12 点 / 20 点的排期。
        """
        now = datetime.now()
        target = min(self.next_daily_time(now), self.next_slot_time(now))
        float_time = self.config.daily_trifles.scheduler.float_time
        float_seconds = float_time.hour * 3600 + float_time.minute * 60 + float_time.second
        target += timedelta(seconds=random_int(0, int(float_seconds)))
        self.set_next_run(task='DailyTrifles', target=target, server=False)

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
