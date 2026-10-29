# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
from dataclasses import dataclass
from datetime import timedelta, time, datetime
from time import sleep

from tasks.GameUi.default_pages import page_battle_prepare, page_battle
from tasks.GameUi.matcher import any_of
from typing import List, Callable, Optional

from cached_property import cached_property

from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.click_pipeline import FinalPoint, execute_single_click
from module.exception import GameStuckError, TaskEnd
from module.image.recipes import match_highlight_rule
from module.logger import logger
from tasks.Component.Costume.config import MainType
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.GameUi.page import page_main, page_exploration, page_shikigami_records
from tasks.Secret.script_task import ScriptTask as SecretScriptTask
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationType, CooperationSelectMask, WQInfo, WQType, WantedQuestsConfig
from tasks.WantedQuests.explore import WQExplore, ExploreWantedBoss


# 推荐地点行开头的类型词；「式神碎片」「式神」都按内部「挑战」处理，长词优先避免被短词截断。
_WQ_TYPE_PREFIXES = tuple(sorted(
    [('式神碎片', WQType.CHALLENGE), ('式神', WQType.CHALLENGE)]
    + [(wq_type.value, wq_type) for wq_type in WQType],
    key=lambda item: len(item[0]),
    reverse=True,
))
# 「数量」之后允许残留的右括号 / 引号；其余残留视为识别异常，不猜数量。
_WQ_ROW_PATTERN = re.compile(r"(.+?)\(?[数教]量:(\d+)[)\"'”’]*")


@dataclass(frozen=True)
class WQRowReading:
    """推荐地点单行的读取结论。

    failed（识别 / 解析失败）与 filtered（按业务规则明确跳过）必须分开：
    只有后者才允许取消追踪去处理下一项，前者要按异常收尾。
    """
    index: int
    status: str  # ok / filtered / failed / absent
    info: Optional[WQInfo] = None
    reason: str = ''


class ScriptTask(WQExplore, SecretScriptTask, WantedQuestsAssets):
    WQ_LIST_MAX_SCROLLS = 4
    WQ_LIST_EDGE_MARGIN = 80
    # 详情打不开时，带新截图重新定位 / 点击的有界次数；超过即按异常收尾，不靠滑动列表掩盖
    WQ_OPEN_MAX_RETRIES = 2
    # 推荐信息整体读取失败时，换新截图重读的次数
    WQ_INFO_READ_ATTEMPTS = 3
    # 取消追踪：总时限、取消按钮最多点击次数、回到列表需要连续确认的帧数
    WQ_CANCEL_TIMEOUT = 12
    WQ_CANCEL_MAX_CLICKS = 3
    WQ_CANCEL_LIST_CONFIRM_FRAMES = 2
    # 单次运行允许的「取消追踪跳过」上限，防止取消没生效时反复打开同一悬赏
    WQ_MAX_SKIPS = 12
    wq_skip_count = 0

    # 追踪界面(显示"前往"按钮的界面,左上角位置,神秘任务不好使)显示以下名称时,任务不再执行
    unwanted_boss_name_list: list = []
    # 已经执行过的悬赏封印(仅记录执行过的, 不一定成功运行)
    wq_executed_set: set[WQInfo] = set()

    def run(self):
        con = self.config.model.wanted_quests
        unwanted_boss_names = con.wanted_quests_config.unwanted_boss_names
        if unwanted_boss_names is not None and unwanted_boss_names != '':
            self.unwanted_boss_name_list = re.split(r"[，,]", unwanted_boss_names)

        # 悬赏会使用探索和秘闻战斗，御魂直接复用这两个任务的预设。
        self.switch_mission_souls()

        preSuc = False
        if (self.get_config()).cooperation_only:
            preSuc = self.pre_work_cooperation_only()
        else:
            preSuc = self.pre_work()
        if not preSuc:
            # 无法完成预处理 很有可能你已经完成了悬赏任务
            logger.warning('Cannot pre-work')
            logger.warning('You may have completed the reward task')
            self.next_run()
            raise TaskEnd('WantedQuests')

        error_count = 0
        open_failures = 0
        self.wq_skip_count = 0
        while 1:
            self.screenshot()
            if not self.is_wq_remained():
                logger.info("no more wq remained")
                break
            if self.appear(self.I_WQ_BOX):
                logger.info("get reward")
                self.ui_get_reward(self.I_WQ_BOX)
                continue
            if self.appear(self.I_E_REWARD_BOX_BIG):
                logger.info("get treasure")
                self.ui_get_reward(self.I_E_REWARD_BOX_BIG)
                continue
            current, found, total, self.O_WQ_TEXT_ALL.area = self.find_wq(
                self.device.image,
                allow_edge_fallback=(
                    error_count >= self.WQ_LIST_MAX_SCROLLS
                ),
            )
            if found == -1:
                if error_count >= self.WQ_LIST_MAX_SCROLLS:
                    logger.warning(
                        'No unfinished wanted quest after scrolling '
                        f'{self.WQ_LIST_MAX_SCROLLS} times, exit'
                    )
                    break
                error_count += 1
                # 当前画面没有可靠候选，保留原逻辑：手指上滑以继续浏览列表下方。
                self.swipe(self.S_WQ_LIST_UP, interval=1)
                sleep(1)
                continue
            if not self.open_wq_info():
                # 列表上已识别到未完成进度却打不开详情：这是识别 / 页面异常，不是「悬赏已完成」，
                # 不滑动列表、不走正常排期，重试耗尽后抛异常交给调度器（保存现场截图、计失败次数）。
                open_failures += 1
                logger.warning(
                    f'Wanted quest detail not opened ({open_failures}/{self.WQ_OPEN_MAX_RETRIES + 1})'
                )
                if open_failures > self.WQ_OPEN_MAX_RETRIES:
                    raise GameStuckError(
                        'Wanted quest detail cannot be opened although unfinished progress was recognized'
                    )
                continue
            open_failures = 0
            error_count = 0
            self.execute_mission(total - current)
            sleep(1.5)
        self.next_run()
        raise TaskEnd('WantedQuests')

    def switch_mission_souls(self) -> None:
        """为悬赏装配探索与秘闻任务已配置的御魂预设。"""
        soul_configs = (
            ('Exploration', self.config.model.exploration.switch_soul_config),
            ('Secret', self.config.model.secret.switch_soul),
        )
        for task_name, soul_config in soul_configs:
            if soul_config.enable:
                logger.info(f'Wanted quests use {task_name} soul preset')
                self.goto_page(page_shikigami_records)
                self.run_switch_soul(soul_config.switch_group_team)
            if soul_config.enable_switch_by_name:
                logger.info(f'Wanted quests use {task_name} named soul preset')
                self.goto_page(page_shikigami_records)
                self.run_switch_soul_by_name(
                    soul_config.group_name,
                    soul_config.team_name,
                )

    def open_wq_info(self) -> bool:
        """打开对应怪物悬赏详情界面；返回 False 表示详情没有被确认打开（不是没有悬赏）"""
        timeout_timer = Timer(5).start()
        while not timeout_timer.reached():
            self.screenshot()
            if self.wq_detail_opened():
                return True
            self.click(self.O_WQ_TEXT_ALL, interval=1.2)
        # 最后一次点击可能恰好在超时前生效，用新截图再确认一次
        self.screenshot()
        return self.wq_detail_opened()

    def wq_detail_opened(self) -> bool:
        """详情右下角的「取消追踪」(已追踪) 或「追踪」(未追踪) 按钮任一出现，即详情已打开。

        I_TRACE_TRUE 与主界面的 I_TRACE_DISABLE 外观几乎一致（离线匹配 0.95），
        所以只能在探索页的详情场景使用，不能拿去判断主界面。
        """
        if self.appear(self.I_TRACE_TRUE):
            return True
        if self.appear(self.I_TRACE_FALSE):
            logger.warning('Wanted quest detail opened in untracked state')
            return True
        return False

    def cancel_wq_trace(self) -> bool:
        """取消当前悬赏追踪并回到列表；仅在「已取消」且「列表连续稳定出现」时返回 True。

        详情页取消后可能留在未追踪详情，也可能直接关闭：前者用 I_TRACE_FALSE 确认后点红叉关闭，
        后者必须在点击之后看到探索列表连续多帧才算数，不能只因 I_TRACE_TRUE 消失一帧。
        """
        timer = Timer(self.WQ_CANCEL_TIMEOUT).start()
        cancel_clicks = 0
        cancelled = False
        list_frames = 0
        while not timer.reached():
            self.screenshot()
            if self.appear(self.I_TRACE_TRUE):
                list_frames = 0
                if cancel_clicks >= self.WQ_CANCEL_MAX_CLICKS:
                    break
                if self.appear_then_click(self.I_TRACE_TRUE, interval=1.5):
                    cancel_clicks += 1
                    cancelled = True
                continue
            if self.appear(self.I_TRACE_FALSE):
                list_frames = 0
                cancelled = True
                self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
                continue
            if self.appear(self.I_CHECK_EXPLORATION):
                # 没有任何取消证据就在列表上，说明详情根本没开着，不能当作取消成功
                if not cancelled:
                    return False
                list_frames += 1
                if list_frames >= self.WQ_CANCEL_LIST_CONFIRM_FRAMES:
                    return True
                continue
            list_frames = 0
        return False

    def skip_current_wq(self, reason: str) -> None:
        """按业务规则跳过当前悬赏：取消追踪并确认回到列表；取消不成功按异常收尾。"""
        logger.warning(f'Skip current wanted quest: {reason}')
        self.wq_skip_count += 1
        if self.wq_skip_count > self.WQ_MAX_SKIPS:
            raise GameStuckError('Too many wanted quest skips, cancel trace may not take effect')
        if not self.cancel_wq_trace():
            raise GameStuckError(f'Cannot cancel wanted quest trace and return to list ({reason})')

    def next_run(self):
        before_end: time = self.get_config().before_end
        if before_end == time(hour=0, minute=0, second=0):
            self.set_next_run(task='WantedQuests', success=True, finish=True)
            return
        time_delta = timedelta(hours=-before_end.hour, minutes=-before_end.minute, seconds=-before_end.second)
        now_datetime = datetime.now()
        now_time = now_datetime.time()
        if time(hour=5) <= now_time < time(hour=18):
            # 如果是在5点到18点之间，那就设定下一次运行的时间为第二天的5点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=5))
            next_run_datetime = next_run_datetime + time_delta
        elif time(hour=18) <= now_time < time(hour=23, minute=59, second=59):
            # 如果是在18点到23点59分59秒之间，那就设定下一次运行的时间为第二天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date() + timedelta(days=1), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        else:
            # 如果是在0点到5点之间，那就设定下一次运行的时间为今天的18点 + before_end
            next_run_datetime = datetime.combine(now_datetime.date(), time(hour=18))
            next_run_datetime = next_run_datetime + time_delta
        self.set_next_run(task='WantedQuests', target=next_run_datetime)

    def pre_work(self):
        """
        前置工作，
        :return:
        """
        self.goto_page(page_main)
        done_timer = Timer(5)
        while 1:
            self.screenshot()
            if self.appear(self.I_TRACE_DISABLE):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click(self.I_WQ_DONE, interval=1):
                continue
            if self.appear_then_click(self.I_TRACE_ENABLE, interval=1):
                continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False
        # 已追踪所有任务
        logger.info('All wanted quests are traced')

        # 存在协作任务则邀请
        self.screenshot()
        if self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3):
            if self.need_invite_vip():
                self.all_cooperation_invite()
            else:
                self.invite_five()
        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.goto_page(page_exploration)
        return True

    def pre_work_cooperation_only(self):
        if self.get_current_page() != page_main:
            self.goto_page(page_main)
        # 打开悬赏封印 界面
        done_timer = Timer(5)
        while 1:
            self.screenshot()
            if self.appear(self.I_TRACE_ENABLE) or self.appear(self.I_TRACE_DISABLE):
                break
            if self.appear_then_click(self.I_WQ_SEAL, interval=1):
                continue
            if self.appear_then_click(self.I_WQ_DONE, interval=1):
                continue
            if self.special_main and self.click(self.C_SPECIAL_MAIN, interval=3):
                logger.info('Click special main left to find wanted quests')
                continue
            if self.appear(self.I_UI_BACK_RED):
                if not done_timer.started():
                    done_timer.start()
            if done_timer.started() and done_timer.reached():
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return False

        if not (self.appear(self.I_WQ_INVITE_1) or self.appear(self.I_WQ_INVITE_2) or self.appear(self.I_WQ_INVITE_3)):
            logger.info("there is no cooperation quest")
            return False

        # 追踪任务 并邀请
        self.all_cooperation_invite()

        self.ui_click_until_disappear(self.I_UI_BACK_RED)
        self.goto_page(page_exploration)
        return True

    def trace_one(self, btn: RuleImage):
        """
            参数必须为邀请按钮(I_WQ_INVITE_n ),特定场景,就不做通用的函数了,怪麻烦的,若还有什么奇葩需求,再扩展吧
        @param btn: 邀请按钮,
        @type btn:
        """
        self.screenshot()
        if not self.appear(btn):
            return
        while 1:
            self.screenshot()
            # 追踪成功  或  是现世任务 不需要追踪
            if self.appear(self.I_WQ_TRACE_ONE_ENABLE) or self.appear(self.I_WQ_TRACE_ONE_REALWORLD):
                break
            if self.appear(self.I_WQ_TRACE_ONE_DISABLE):
                self.click(self.I_WQ_TRACE_ONE_DISABLE, interval=1.5)
                continue
            # 根据邀请按钮位置生成 对应的点击位置 打开追踪界面
            # NOTE magic Number

            # 落点在邀请按钮左上角上方 40px（按钮框外），是业务偏移，按 FinalPoint 原样执行。
            point = FinalPoint(btn.roi_front[0], btn.roi_front[1] - 40)
            execute_single_click(self.device, point, control_name=str(btn) + ' y-40')
            # 防止点击后界面来不及刷新
            sleep(1.5)
        # 关闭单个任务的追踪界面
        self.ui_click_until_smt_disappear(self.C_WQ_TRACE_ONE_CLOSE, stop=self.I_WQ_TRACE_ONE_CHECK_OPENED,
                                          interval=1.5)

    def execute_mission(self, num_want: int):
        """
        执行对应的悬赏任务
        :param num_want: 一共要打败的怪物数量
        :return:
        """
        logger.hr('Start wanted quests')
        if not self.goto_button_visible():
            # 如果没有出现 '前往'按钮， 那就是这个可能是神秘任务但是没有解锁
            logger.info('This is a secret mission but not unlock')
            self.skip_current_wq('secret mission not unlock')
            return False
        # 跳过不想打的
        monster_name = self.O_WQ_MONSTER_TYPE.detect_text(self.device.image)
        if monster_name in self.unwanted_boss_name_list:
            logger.warning(f'unwanted {monster_name}')
            self.skip_current_wq(f'unwanted {monster_name}')
            return False
        # 获取排序后的悬赏信息列表
        ordered_wq_infos = self.read_ordered_wq_infos(num_want)
        if not ordered_wq_infos:
            # read_ordered_wq_infos 已排除识别失败，走到这里只可能是全部被业务规则过滤
            logger.info('Current wanted quest skipped all, cancel it')
            self.skip_current_wq('all recommendations filtered by rules')
            return False
        wq_call_dict: dict[WQType, Callable] = {
            WQType.CHALLENGE: self.challenge,
            WQType.EXPLORE: self.explore,
            WQType.SECRET: self.secret
        }
        # 获取当前需要执行的悬赏策略
        wq_info = self.get_need_exec_wq(ordered_wq_infos)
        if not wq_info:
            logger.info('Current wanted quests can not be executed')
            self.skip_current_wq('no executable recommendation')
            return False
        try:
            logger.info(f'Choose wq: {wq_info}')
            wq_call_dict[wq_info.type](wq_info.goto_btn, wq_info.do_num)
        except ExploreWantedBoss:
            logger.warning('Maybe only need attack boss')
        finally:
            self.wq_executed_set.add(wq_info)
            self.goto_page(page_exploration)

    def get_need_exec_wq(self, ordered_wq_infos: List[WQInfo]) -> Optional[WQInfo]:
        """获取需要执行的悬赏(按优先级选择最靠前的)"""
        for wq_info in ordered_wq_infos:
            if WQType.CHALLENGE == wq_info.type:
                number_challenge = self.O_WQ_NUMBER.ocr(self.device.image)
                if number_challenge < 5:  # 挑战卷5张都没有了, 省着点吧试试别的
                    logger.warning("Challenge ticket num < 5, skip")
                    continue
            return wq_info
        return None

    def goto_button_visible(self) -> bool:
        """详情刚打开的几帧里按钮可能还没画全，缺失需连续多帧确认才算「没有前往按钮」。"""
        for attempt in range(3):
            if self.appear(self.I_GOTO_1):
                return True
            if attempt < 2:
                sleep(0.5)
                self.screenshot()
        return False

    def read_ordered_wq_infos(self, num_want: int) -> List[WQInfo]:
        """读取并排序推荐地点；全部是识别失败时换新截图重读，仍失败则按异常收尾。

        识别失败（failed）不能当作「被规则跳过」：否则会取消追踪或让任务被排到明天。
        """
        for attempt in range(self.WQ_INFO_READ_ATTEMPTS):
            readings = self.read_wq_rows(num_want)
            ordered = self.order_wq_infos(readings)
            failed = [r for r in readings if r.status == 'failed']
            if ordered or not failed:
                if failed:
                    logger.warning(
                        'Some wanted quest recommendation rows are unreadable: '
                        f'{[(r.index, r.reason) for r in failed]}, use other readable rows'
                    )
                return ordered
            logger.warning(
                f'Wanted quest recommendations unreadable ({attempt + 1}/{self.WQ_INFO_READ_ATTEMPTS}): '
                f'{[(r.index, r.reason) for r in failed]}'
            )
            if attempt + 1 < self.WQ_INFO_READ_ATTEMPTS:
                sleep(0.5)
                self.screenshot()
        raise GameStuckError('Wanted quest recommendation rows cannot be recognized')

    def get_ordered_wq_infos(self, num_want: int) -> List[WQInfo]:
        """获取当前悬赏妖怪页面排好序的信息列表, 会自动排除无法执行的悬赏"""
        return self.order_wq_infos(self.read_wq_rows(num_want))

    def order_wq_infos(self, readings: List[WQRowReading]) -> List[WQInfo]:
        wq_info_list = [r.info for r in readings if r.status == 'ok']
        type_ordered_list = self.get_config()._wq_type_ordered_list
        wq_info_list.sort(key=lambda x: type_ordered_list.index(x.type))
        return wq_info_list

    def read_wq_rows(self, num_want: int) -> List[WQRowReading]:
        """逐行读取推荐地点；第 i 行始终绑定自己的 I_GOTO_i，某行失败 / 被过滤不影响其他行的按钮。"""
        wq_info_ocr = [self.O_WQ_INFO_1, self.O_WQ_INFO_2, self.O_WQ_INFO_3, self.O_WQ_INFO_4]
        goto_btn_list = [self.I_GOTO_1, self.I_GOTO_2, self.I_GOTO_3, self.I_GOTO_4]
        return [
            self.build_wq_info(i + 1, wq_info_ocr[i], goto_btn_list[i], num_want)
            for i in range(4)
        ]

    @staticmethod
    def parse_wq_row_text(text: str) -> Optional[tuple[WQType, str, int]]:
        """解析整行「类型 目的地(数量:n)」；任何一段缺失 / 异常都返回 None，不猜类型或数量。"""
        normalized = ''.join(str(text).split())
        normalized = normalized.replace('：', ':').replace('（', '(').replace('）', ')')
        for prefix, wq_type in _WQ_TYPE_PREFIXES:
            if normalized.startswith(prefix):
                rest = normalized[len(prefix):]
                break
        else:
            return None
        match = _WQ_ROW_PATTERN.fullmatch(rest)
        if not match:
            return None
        dest = match.group(1).rstrip('(').strip()
        number = int(match.group(2))
        if not re.search(r'\w', dest) or number <= 0:
            return None
        return wq_type, dest, number

    def build_wq_info(self, index: int, info_rule: RuleOcr, goto_btn_rule: RuleImage, num_want: int) -> WQRowReading:
        """
        构建单条悬赏信息
        :param index: 行号(1-4)
        :param info_rule: 整行 OCR（类型 + 目的地 + 数量）
        :param goto_btn_rule: 本行前往按钮
        :param num_want: 想要攻击的数量
        """
        text = info_rule.ocr(self.device.image)
        goto_visible = self.appear(goto_btn_rule)
        parsed = self.parse_wq_row_text(text)
        if parsed is None:
            if not str(text).strip() and not goto_visible:
                # 没有文字也没有前往按钮：这一行本来就不存在（推荐不足四条）
                return WQRowReading(index, 'absent')
            logger.warning(f'Unknown wq info (row {index}): {text!r}')
            return WQRowReading(index, 'failed', reason=f'unparsable {text!r}')
        wq_type, wq_dest, wq_number = parsed
        type_ordered_list = self.get_config()._wq_type_ordered_list
        if wq_type not in type_ordered_list:
            logger.warning(f'{wq_type.value} is not in the order list')
            return WQRowReading(index, 'filtered', reason='type not in priority')
        # 跳过高层秘闻
        if any(wq_dest.endswith(layer) for layer in ("捌", "玖", "拾", "番外")):
            logger.warning('This secret layer is too high, skip')
            return WQRowReading(index, 'filtered', reason='high secret layer')
        if not goto_visible:
            logger.warning(f'Goto button of row {index} not visible')
            return WQRowReading(index, 'failed', reason='goto button not visible')
        do_num = num_want // wq_number + (num_want % wq_number > 0)
        wq_info = WQInfo(wq_type, wq_dest, wq_number, goto_btn_rule, do_num)
        # 跳过已经执行过的(例:都是探索第5层4只怪, 上次计算需要打2次但是这次还是打2次, 肯定出问题了也不需要执行了)
        if wq_info in self.wq_executed_set:
            logger.warning('This wanted quest has been executed, skip')
            return WQRowReading(index, 'filtered', reason='already executed')
        return WQRowReading(index, 'ok', info=wq_info)

    def challenge(self, goto_btn, num):
        self.ui_click(goto_btn, self.I_WQC_FIRE)
        self.ui_click(self.I_WQC_UNLOCK, self.I_WQC_LOCK)
        self.ui_click_until_disappear(self.I_WQC_FIRE)
        # 锁定阵容进入战斗
        wq_config = GeneralBattleConfig(lock_team_enable=True)
        self.run_general_battle(config=wq_config, exit_matcher=self.I_WQC_FIRE)

    def secret(self, goto, num=1):
        self.ui_click(goto, self.I_WQSE_FIRE)
        for i in range(num):
            self.screenshot()
            # 若是当周特殊秘闻则禁止连续进攻, 战斗结束之后直接退到探索页面重新进入挑战(避免当周秘闻没打结果跳转到第一层)
            if self.appear(self.I_WQSE_SPECIAL_FIRE):
                logger.warning('Current is special secret, exit and retry')
                return 
            # 又臭又长的对话针的是服了这个网易
            click_count = 0
            while 1:
                self.screenshot()
                if self.get_current_page() in [page_battle_prepare, page_battle]:
                    self.run_general_battle(self.battle_config, exit_matcher=any_of(self.I_UI_BACK_RED, self.I_WQSE_SPECIAL_FIRE))
                    break
                if self.appear_then_click(self.I_WQSE_FIRE, interval=1):
                    continue
                if self.appear(self.I_UI_BACK_RED, threshold=0.7) and not self.appear(self.I_WQSE_FIRE):
                    self.click(self.C_SECRET_CHAT, interval=0.8)
                    click_count += 1
                    if click_count >= 6:
                        logger.warning('Secret mission chat too long, force to close')
                        click_count = 0
                        self.device.click_record_clear()
        logger.info('Secret mission finished')

    def invite_random(self, add_button: RuleImage):
        self.screenshot()
        if not self.appear(add_button):
            return False
        self.ui_click(add_button, self.I_WQ_INVITE_ENSURE, interval=2.5)
        logger.info('enter invite form')
        sleep(1)
        self.click(self.I_WQ_FRIEND_1)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_2)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_3)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_4)
        sleep(0.4)
        self.click(self.I_WQ_FRIEND_5)
        sleep(0.2)
        self.screenshot()
        if not self.appear(self.I_SELECTED):
            logger.warning('No friend selected')
            return False
        self.ui_click_until_disappear(self.I_INVITE_ENSURE)
        sleep(0.5)

    def invite_five(self):
        """
        邀请好友，默认点五个
        :return:
        """

        logger.hr('Invite friends')
        self.invite_random(self.I_WQ_INVITE_1)
        self.invite_random(self.I_WQ_INVITE_2)
        self.invite_random(self.I_WQ_INVITE_3)

    def all_cooperation_invite(self, name_all: str = None):
        """
            所有的协作任务依次邀请
            如果配置了只完成协作任务 还会将该任务设置为追踪
        @return:

        """
        self.screenshot()
        if not self.appear(self.I_WQ_INVITE_1):
            return False

        ret = self.get_cooperation_info()
        if len(ret) == 0:
            logger.info("no Cooperation found")
            return False
        typeMask = 15
        typeMask = CooperationSelectMask[(self.get_config()).cooperation_type.value]
        for item in ret:
            # 该任务是需要邀请的任务类型
            if not (item['type'] & typeMask):
                # BUG 存在多个协作任务时,邀请完第一个协作任务对方接受后,未邀请的任务位置无法确定(缺少信息)
                # 例如 按顺序存在 abc 3个协作任务,邀请完a,好友接受后,这三个任务在界面上的顺序变化,abc 还是bca
                # 如果顺序不变 则应该没有问题
                logger.info("cooperationType %s But needed Type %s ,Skipped", item['type'], typeMask)
                break
            '''
               尝试5次 如果邀请失败 等待20s 重新尝试
               阴阳师BUG: 好友明明在线 但邀请界面找不到该好友(好友未接受任何协作任务的情况下)
           '''
            index = 0
            item['inviteResult'] = False
            if name_all is None:
                name = self.get_invite_vip_name(item['type'])
            else:
                name = name_all
            logger.warning("find cooperationType %s ,start invite %s", item['type'], name)
            while index < 5:
                if self.cooperation_invite(item['inviteBtn'], name):
                    item['inviteResult'] = True
                    index = 5
                    continue
                logger.info("%s not found,Wait 20s,%d invitations left", name, 5 - index - 1)
                index += 1
                sleep(20) if index < 5 else sleep(0)
                # NOTE 等待过程如果出现协作邀请 将会卡住 为了防止卡住
                self.screenshot()
            # 邀请追踪一起吧,只有邀请成功才追踪
            if item['inviteResult']:
                self.invite_success_callback(item['type'], name)
                if (self.get_config()).cooperation_only:
                    logger.info("start trace_one")
                    self.trace_one(item['inviteBtn'])
        return ret

    def cooperation_invite(self, btn: RuleImage, name: str):
        """
            单个协作任务邀请
        @param btn:
        @param name:
        @return:
        """
        self.ui_click(btn, stop=self.I_WQ_INVITE_ENSURE, interval=2.5)

        # 选人
        self.O_WQ_INVITE_COLUMN_1.keyword = name
        self.O_WQ_INVITE_COLUMN_2.keyword = name

        find = False
        for i in range(2):
            self.wait_until_appear(self.I_WQ_INVITE_FRIEND_LIST_APPEAR, wait_time=4)
            self.screenshot()
            in_col_1 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_1)
            in_col_2 = self.ocr_appear_click(self.O_WQ_INVITE_COLUMN_2)
            find = in_col_2 or in_col_1
            if find:
                self.wait_until_appear(self.I_WQ_INVITE_SELECTED, wait_time=2)
                self.screenshot()
                if self.appear(self.I_WQ_INVITE_SELECTED):
                    logger.info("friend found and selected")
                    break
                # TODO OCR识别到文字 但是没有选中 尝试重新选择  (选择好友时,弹出协作邀请导致选择好友失败)
            # 检测跨服好友按钮是否高亮
            while 1:
                self.screenshot()
                if not self.appear_highlight(self.I_WQ_INVITE_DIFF_SVR_HIGHLIGHT):
                    self.click(self.I_WQ_INVITE_DIFF_SVR)
                    continue
                break
            # 等待好友列表加载
            self.wait_until_appear(self.I_WQ_INVITE_DIFF_SVR_HIGHLIGHT, wait_time=4)
        # 没有找到需要邀请的人,点击取消 返回悬赏封印界面
        if not find:
            self.screenshot()
            self.ui_click_until_disappear(self.I_WQ_INVITE_CANCEL, interval=1.5)
            return False
        #
        self.ui_click_until_disappear(self.I_WQ_INVITE_ENSURE, interval=1)
        return True

    def get_cooperation_info(self) -> List:
        """
            获取协作任务详情
        @return: 协作任务类型与邀请按钮
        """
        self.screenshot()
        retList = []
        i = 0
        for index in range(3):
            btn = self.__getattribute__("I_WQ_INVITE_" + str(index + 1))
            if not self.appear(btn):
                break
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_JADE_" + str(index + 1))):
                retList.append({'type': CooperationType.Jade, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_DOG_FOOD_" + str(index + 1))):
                retList.append({'type': CooperationType.Food, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_CAT_FOOD_" + str(index + 1))):
                retList.append({'type': CooperationType.Food, 'inviteBtn': btn})
                continue
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_SUSHI_" + str(index + 1))):
                retList.append({'type': CooperationType.Sushi, 'inviteBtn': btn})
                continue
            # NOTE 因为食物协作里面也有金币奖励 ,所以判断金币协作放在最后面
            if self.appear(self.__getattribute__("I_WQ_COOPERATION_TYPE_GOLD_" + str(index + 1))):
                retList.append({'type': CooperationType.Gold, 'inviteBtn': btn})
                continue
        logger.info(f"get cooperation size {len(retList)}")
        return retList

    # 使用平均亮度检测是否一致
    def appear_highlight(self, rule_image: RuleImage):
        return match_highlight_rule(rule_image, self.device.image, frame_id=self.device.image_frame_id)

    @cached_property
    def special_main(self) -> bool:
        # 特殊的庭院需要点一下，左边然后才能找到图标
        main_type = self.config.global_game.costume_config.costume_main_type
        if main_type == MainType.COSTUME_MAIN_3:
            return True
        return False

    def get_config(self) -> WantedQuestsConfig:
        return self.config.wanted_quests.wanted_quests_config

    def need_invite_vip(self):
        return bool(self.get_config().invite_friend_name)

    def get_invite_vip_name(self, ctype: CooperationType):
        return self.get_config().invite_friend_name

    def invite_success_callback(self, ctype: CooperationType, name):
        """
           邀请成功回调
        @param ctype:
        @type ctype:
        @param name:
        @type name:
        """

        return True

    def process_ocr(self, txt):
        def detect_spliter(txt):
            index = txt.find('/')
            if index != -1:
                return index
            # 由于斜杠'/'经常被误识别为'7',且悬赏封印悬赏怪物总数没有与‘7’相关的数字
            reg = re.compile(r'^(\d+)([7/])(\d+)$')
            match = reg.match(txt)
            if match:
                return match.start(2)
            return -1

        index = detect_spliter(txt)
        if index < 0:
            return 0, 0, 0
        return int(txt[:index]), 1, int(txt[index + 1:])

    def txt_ocr_appear(self, ocr_item: RuleOcr, reg, img):
        res = ocr_item.ocr(img)
        regex = re.compile(reg)
        ismatch = regex.match(res)
        return ismatch is not None

    @staticmethod
    def _wq_box_xywh(box) -> List[int]:
        """将 OCR 的四点坐标转换为相对 OCR 截图的 xywh。"""
        xs = [int(point[0]) for point in box]
        ys = [int(point[1]) for point in box]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        return [x1, y1, x2 - x1, y2 - y1]

    @staticmethod
    def _normalize_wq_list_text(text: str) -> str:
        """清理列表 OCR 文本，保留进度分隔符的容错字符 7。"""
        return ''.join(str(text).split()).replace('／', '/')

    @staticmethod
    def _has_wq_label_hint(text: str) -> bool:
        """完整或被底部裁切的“悬赏封印”都可作为局部归属证据。"""
        if '悬赏' in text or '封印' in text:
            return True
        return re.search(r'[封野][印卬]', text) is not None

    def find_wq(
        self,
        img,
        *,
        allow_edge_fallback: bool = False,
    ) -> tuple[int, int, int, List[int]]:
        """
        在探索页面定位未完成的悬赏卡位。

        新逻辑先找进度，再用同一卡位附近的“悬赏/封印”文字确认归属，
        避免将真八岐大蛇等其他左侧入口误当成悬赏。靠近底部的卡位先
        通过外层翻页移到完整区域；连续翻页仍无法完整显示时才启用边缘保底。

        :param img: 当前截图
        :param allow_edge_fallback: 已连续翻页到下方时，允许点击文字裁切的底部卡位
        :return: (已完成数量, 有效标记, 总数量, 进度文字点击 roi)
        """
        res_list = self.O_WQ_TEXT_ALL.detect_and_ocr(img)
        progress_pattern = re.compile(
            r'(?<!\d)(\d{1,2})([7/])(\d{1,2})(?!\d)'
        )
        roi_x, roi_y, _, roi_height = self.O_WQ_TEXT_ALL.roi
        safe_progress_bottom = (
            roi_y + roi_height - self.WQ_LIST_EDGE_MARGIN
        )

        ocr_items = []
        for result in res_list:
            relative_area = self._wq_box_xywh(result.box)
            absolute_area = [
                relative_area[0] + roi_x,
                relative_area[1] + roi_y,
                relative_area[2],
                relative_area[3],
            ]
            ocr_items.append((
                self._normalize_wq_list_text(result.ocr_text),
                absolute_area,
            ))

        confirmed_candidates = []
        edge_candidates = []
        for text, progress_area in ocr_items:
            match = progress_pattern.search(text)
            if not match:
                continue
            current, total = int(match.group(1)), int(match.group(3))
            if total <= 0 or total > 14 or current > total:
                logger.warning(
                    'Ignore abnormal wanted quest progress: '
                    f'{text}'
                )
                continue
            if current == total:
                continue

            progress_top = progress_area[1]
            progress_bottom = progress_top + progress_area[3]
            label_confirmed = self._has_wq_label_hint(text)
            if not label_confirmed:
                for nearby_text, nearby_area in ocr_items:
                    if not self._has_wq_label_hint(nearby_text):
                        continue
                    nearby_top = nearby_area[1]
                    nearby_bottom = nearby_top + nearby_area[3]
                    if (
                        nearby_bottom >= progress_top - 12
                        and nearby_top <= progress_bottom + 82
                    ):
                        label_confirmed = True
                        break

            candidate = (
                progress_top,
                current,
                total,
                progress_area,
                text,
            )
            if progress_top >= safe_progress_bottom:
                # 最底一项即使识别到局部文字，也先翻页将其移入完整区域。
                edge_candidates.append(candidate)
            elif label_confirmed:
                confirmed_candidates.append(candidate)

        candidates = confirmed_candidates
        if not candidates and allow_edge_fallback:
            candidates = edge_candidates
            if candidates:
                logger.warning(
                    'Use cropped bottom wanted quest as fallback after '
                    'list scrolling'
                )
        if candidates:
            _, current, total, click_area, raw_text = min(
                candidates,
                key=lambda item: item[0],
            )
            logger.info(
                f'Find wanted quest progress {raw_text}: '
                f'{current}/{total}, click={click_area}'
            )
            return current, 1, total, click_area
        return -1, -1, -1, [0, 0, 0, 0]

    def is_wq_remained(self):
        """检测是否仍有悬赏；兼容列表底部仅剩裁切卡位。"""
        if self.appear(self.O_WQ_LIST_CHECK):
            return True
        progress_pattern = re.compile(
            r'(?<!\d)(\d{1,2})([7/])(\d{1,2})(?!\d)'
        )
        for result in self.O_WQ_TEXT_ALL.detect_and_ocr(
            self.device.image,
            logDisplay=False,
        ):
            text = self._normalize_wq_list_text(result.ocr_text)
            match = progress_pattern.search(text)
            if not match:
                continue
            current, total = int(match.group(1)), int(match.group(3))
            if 0 <= current < total <= 14:
                logger.info(
                    'Wanted quest remains by cropped progress fallback: '
                    f'{current}/{total}'
                )
                return True
        return False


if __name__ == '__main__':
    # 原始版本
    strict_pattern = re.compile(r"^(.+?)\(?[数教]量:\s*(\d+)\)?$")
    # OCR容错版本
    ocr_pattern = re.compile(r"(.+?)\s*\(?[数教]量[:：]\s*(\d+)")
    test_cases = [
        "第十章(数量:2)",
        '第十章(数量:2)"',
        '第十章(数量:2""',
        "第十章 数量:2",
        "第十章 数量：2",
        "第十章(数量：2)",
        "第十章 (数量: 2)",
        "第十章(教量:2)",
        "第十章(数量:2abc)",
        "第十章(数量:20)",
        "第十章数量:2",
        "第十章",
        "",
    ]
    test_cases.extend([
        "第十章（数量：2）",  # 中文括号
        "第十章(数最:2)",  # OCR错字
        "第十章(数量:Z)",  # OCR数字识别失败
        "第十章(数量:2 )",
        "第十章(数量: 2)",
        "第十章(数量:02)",
        "第十章(数量:2.”)",
        "第十章(数量:2。)",
    ])

    def test(pattern, text):
        match = pattern.search(text)
        if not match:
            return "❌ 不匹配"
        return (
            f"✅ 匹配 "
            f"dest=[{match.group(1).strip()}], "
            f"number=[{int(match.group(2))}]"
        )

    for text in test_cases:
        print("=" * 60)
        print(f"输入: {repr(text)}")
        print("\n【严格模式】")
        print(test(strict_pattern, text))
        print("\n【OCR容错模式】")
        print(test(ocr_pattern, text))
        print()
