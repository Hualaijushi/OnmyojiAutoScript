# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
import numpy as np

from enum import Enum
from cached_property import cached_property
from datetime import timedelta, time
from module.atom.image import RuleImage
from module.click_pipeline import FinalPoint, execute_single_click
from module.click_sampler import ClickSampler

from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.interaction_policy import InteractionPolicy, fire_reaction_range
from tasks.GameUi.assets import GameUiAssets
from tasks.base_task import BaseTask
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.Component.GeneralInvite.config_invite import InviteConfig, FindMode
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from module.logger import logger


# 组队 battle-entry（房间内点「挑战 / 开始战斗」）的有限 attempt / 总超时 / 点击后确认等待。
# engineering baseline，**PROVISIONAL / Level C 待标定**：max_tries 对齐 RealmRaid / Orochi / EvoZone
# 的 4；总超时取 15（组队进战斗比个人突破慢——队友加载 / 队长开战同步；`run_invite` 的
# `timer_wait` 是整轮邀请预算、`Timer(20/30)` 是补邀节奏，都不 bound 这个「按开始→战斗加载」窗口）；
# 点击后确认 4（略宽于 RealmRaid 的 3，覆盖组队战斗加载）。
GI_FIRE_MAX_TRIES = 4
GI_FIRE_TIMEOUT = 15
GI_FIRE_POST_CLICK_TIMEOUT = 4


class FriendList(str, Enum):
    RECENT_FRIEND = 'recent_friend'
    GUILD_FRIEND = 'guild_friend'
    FRIEND = 'friend'
    OTHER_FRIEND = 'other_friend'


class RoomType(str, Enum):
    # 房间只可以两个人的： 探索
    NORMAL_2 = 'normal_2'
    # 房间可以两三个人的： 觉醒、御魂、日轮、石距（石距是单次没有锁定阵容）
    NORMAL_3 = 'normal_3'
    # 永生之海不一样
    ETERNITY_SEA = 'eternity_sea'
    # 经验妖怪和金币妖怪
    NORMAL_5 = 'normal_5'
    # 契灵之境
    BONDLING_FAIRYLAND = 'bondling_fairyland'


class GeneralInvite(BaseTask, GeneralInviteAssets):
    timer_invite = None
    timer_wait = None
    timer_emoji = None  # 等待期间如果没有操作的话，可能会导致长时间无响应报错

    def run_invite(self, config: InviteConfig, is_first: bool = False, fire_reaction=None) -> bool:
        """
        队长！！身份。。。在组队界面邀请好友（ 如果开启is_first） 等待队员进入开启挑战
        请注意，返回的时候成功时是进入战斗了！！！
        如果是失败，那就是没有队友进入，然后会退出房间的界面
        :param config:
        :param is_first: 如果是第一次开房间的那就要邀请队员，其他情况等待队员进入
        :param fire_reaction: 当前任务的 FIRE reaction 配置组（没有则用公共默认），原样交给 click_fire
        :return:
        """
        if not self.ensure_enter():
            logger.warning('Not enter invite page')
            return False
        if is_first:
            _ = self.room_type
            self.timer_invite = Timer(20)
            self.timer_invite.start()
            self.ensure_room_type(len(config.friend_list.split('\n')))
            self.invite_friends(config)
        else:
            self.timer_invite = Timer(30)
            self.timer_invite.start()
            self.timer_emoji = Timer(20)
            self.timer_emoji.start()
        wait_second = config.wait_time.second + config.wait_time.minute * 60
        self.timer_wait = Timer(wait_second)
        self.timer_wait.start()
        while 1:
            self.screenshot()
            if self.timer_wait.reached():
                logger.warning('Wait timeout')
                return False
            if self.appear(self.I_MATCHING):
                logger.warning('Timeout, now is no room')
                return False

            if not self.is_in_room():
                continue

            if self.timer_emoji and self.timer_emoji.reached():
                self.timer_emoji.reset()
                self.appear_then_click(self.I_GI_EMOJI_1)
                self.appear_then_click(self.I_GI_EMOJI_2)

            # 点击挑战
            if self.room_check_can_fire(config):
                fire_result = self.click_fire(fire_reaction=fire_reaction)
                if fire_result == 'battle':
                    return True
                # room_failed / timeout：不把「旧房间状态消失」当成功，返回 False 让 caller
                # 走既有「邀请失败退出任务」分支，不误交接 run_general_battle
                logger.warning(f'Room challenge did not confirm battle ({fire_result}), exit invite')
                return False
            if self.timer_invite and self.timer_invite.reached():
                if is_first:
                    logger.info('Invitation is triggered every 20s')
                    self.timer_invite.reset()
                else:
                    logger.info('Wait for 30s and invite again')
                    self.timer_invite = None
                invite_success = self.invite_friends(config)
                if not is_first and self.room_type == RoomType.BONDLING_FAIRYLAND and not invite_success:
                    self._ensure_midway_bondling_invite(config)
        return False

    def _ensure_midway_bondling_invite(self, config: InviteConfig) -> None:
        """
        契灵之境中途补邀失败时，等待队伍状态稳定后再确认一次。

        打开邀请面板失败可能是队友恰好在此期间进入房间。等待 5 秒并
        刷新截图后，如果邀请位已经消失，则按队友已进入处理；如果邀请
        位仍然存在，则再执行一次邀请，避免一次识别或点击失败后直接开战。
        """
        logger.info('Midway invite failed, wait 5s and check the room again')
        sleep(5)
        self.screenshot()
        if not self.appear(self.I_ADD_1):
            logger.info('Invite button disappeared, teammate is already in the room')
            return

        logger.warning('Invite button still exists, retry invite friend')
        self.invite_friends(config)

    def room_check_can_fire(self, config: InviteConfig) -> bool:
        fire = False  # 是否开启挑战
        # 如果这个房间最多只容纳两个人（意思是只可以邀请一个人），且已经邀请一个人了，那就开启挑战
        if self.room_type == RoomType.NORMAL_2 and not self.appear(self.I_ADD_2):
            logger.info('Start challenge and this room can only invite one friend')
            fire = True
        # 如果这个房间最多容纳三个人（意思是可以邀请两个人），且设定邀请一个就开启挑战，那就开启挑战
        elif self.room_type == RoomType.NORMAL_3 and len(config.friend_list_v) == 1 and not self.appear(self.I_ADD_1):
            logger.info('Start challenge and user only invite one friend')
            fire = True
        # 如果这个房间最多容纳三个人（意思是可以邀请两个人），且设定邀请两个就开启挑战，那就开启挑战
        elif self.room_type == RoomType.NORMAL_3 and len(config.friend_list_v) == 2 and not self.appear(self.I_ADD_2):
            logger.info('Start challenge and user invite two friends')
            fire = True
        # 如果这个房间是五人的，且设定邀请一个就开启挑战，那就开启挑战
        elif self.room_type == RoomType.NORMAL_5 and len(config.friend_list_v) == 1 and not self.appear(self.I_ADD_5_1):
            logger.info('Start challenge and user only invite one friend')
            fire = True
        # 如果这个房间是五人的，且设定邀请两个就开启挑战，那就开启挑战
        elif self.room_type == RoomType.NORMAL_5 and len(config.friend_list_v) == 2 and not self.appear(self.I_ADD_5_2):
            logger.info('Start challenge and user invite two friends')
            fire = True
        # 如果是永生之海
        elif self.room_type == RoomType.ETERNITY_SEA and not self.appear(self.I_ADD_SEA):
            logger.info('Start challenge and this is lock sea')
            fire = True
        # 契灵之境(两人间但队友在一号位)
        elif self.room_type == RoomType.BONDLING_FAIRYLAND and not self.appear(self.I_ADD_1):
            logger.info('Start challenge and this is bondling fairyland')
            fire = True
        return fire

    def invite_friends(self, config: InviteConfig, open_invite: bool = True, confirm_rule: RuleImage = None) -> bool:
        """
        邀请多个好友
        :param confirm_rule: 确认规则(邀请时的点击按钮：邀请/分享/...)
        :param config: 邀请配置
        :param open_invite: 是否需要在本方法内打开邀请界面
        :return: 邀请是否成功
        """
        logger.hr('Invite friends', 2)
        if not config.friend_list_v:
            logger.warning('No friend to invite')
            return False
        logger.info(f'Need invite friend list: {config.friend_list_v}')
        if not self._open_invite_panel_if_needed(open_invite):
            return True
        friend_class = self._read_friend_classes()
        selected_set: set[str] = set()
        match config.find_mode:
            case FindMode.RECENT_FRIEND:
                self._select_recent_mode_friends(friend_class, config.friend_list_v, selected_set)
            case FindMode.AUTO_FIND:
                self._select_auto_mode_friends(friend_class, config.friend_list_v, selected_set)
        return self._confirm_invite_and_validate(selected_set, config.friend_list_v, confirm_rule)

    def ensure_enter(self) -> bool:
        """
        确认是否进入了组队界面
        :return:
        """
        logger.info('Ensure enter invite page')
        while 1:
            self.screenshot()
            if self.appear(self.I_ADD_2):
                return True
            if self.appear(self.I_ADD_5_4):
                return True
            if self.appear(self.I_LOCK_SEA):
                return True
            if self.appear(self.I_UNLOCK_SEA):
                return True
            # 修复三人组队卡住bug，#78
            # 增加左上角协战房间判断，存在就说明在组队界面
            if self.appear(self.I_GI_IN_ROOM):
                return True
            if self.appear(self.I_MATCHING):
                return False

    # 判断是否在房间里面
    def is_in_room(self, is_screenshot: bool = True) -> bool:
        """
        判断是否在房间里面
        :return:
        """
        if is_screenshot:
            self.screenshot()
        if self.appear(GeneralInviteAssets.I_GI_EMOJI_1):
            return True
        if self.appear(GeneralInviteAssets.I_GI_EMOJI_2):
            return True
        return False

    def exit_room(self) -> bool:
        """
        退出房间
        :return:
        """
        if not self.is_in_room():
            return True
        logger.info('Exit room')
        timeout_timer = Timer(5).start()
        while True:
            self.screenshot()
            if timeout_timer.reached():
                break
            if not self.is_in_room() and \
                    not self.appear_then_click(GeneralInviteAssets.I_GI_SURE, interval=0.8) and \
                    not self.appear(self.I_BACK_YELLOW):
                return True
            if self.appear_then_click(GeneralInviteAssets.I_GI_SURE, interval=0.5):
                continue
            if not self.appear(GeneralInviteAssets.I_GI_SURE) and self.appear_then_click(self.I_BACK_YELLOW, interval=0.8):
                self.wait_until_appear(GeneralInviteAssets.I_GI_SURE, wait_time=0.8)
                continue
            if not self.appear(GeneralInviteAssets.I_GI_SURE) and self.appear_then_click(self.I_BACK_YELLOW_SEA, interval=0.8):
                self.wait_until_appear(GeneralInviteAssets.I_GI_SURE, wait_time=0.8)
                continue
        return False

    def _battle_entry_positive(self) -> bool:
        """当前帧是否已进入 GeneralBattle 可接管的战斗流程。

        优先复用 `GeneralBattle.is_in_battle()`——`click_fire()` 的 11 个 consumer 全部在 MRO
        里带 `GeneralBattle`，正常生产路径都走这条。`GeneralInvite` 自身基类不含它
        （`MysteryShop` 混入 `GeneralInvite` 但不调 `click_fire`），故留一个保守 fallback：
        只取 `is_in_battle()` 里的两个 battle-entry marker `I_BATTLE_INFO` / `I_PREPARE_HIGHLIGHT`
        （严格子集，不新造 detector、不引入 `is_in_battle` 未采用的更宽 heuristic）。只读当前帧、不截图。
        """
        checker = getattr(self, 'is_in_battle', None)
        if callable(checker):
            return bool(checker(False))
        return (
            self.appear(GeneralBattleAssets.I_BATTLE_INFO)
            or self.appear(GeneralBattleAssets.I_PREPARE_HIGHLIGHT)
        )

    def _room_entry_failed(self) -> bool:
        """当前帧是否**明确是「组队房间已失效」的业务失败**（非正常 battle transition）。

        复用现有失败 marker、只读当前帧、不新造 detector：
        - `I_MATCHING`：回到匹配 / 房间没了（`ensure_enter` / `run_invite` 已用此判 `return False`）；
        - `GameUiAssets.I_CHECK_MAIN` / `I_CHECK_EXPLORATION`：回到庭院 / 探索 = 房间销毁
          （`wait_battle` 已用此判 'Room destroyed'）。
        「队长跑路」（`wait_battle` 里 `I_FIRE` 可见即判 leader gone）在 `click_fire` 语境里
        不适用——这里本机就是房主 / 队长，`I_FIRE` 可见是正常的待点挑战按钮。
        """
        return (
            self.appear(self.I_MATCHING)
            or self.appear(GameUiAssets.I_CHECK_MAIN)
            or self.appear(GameUiAssets.I_CHECK_EXPLORATION)
        )

    def _classify_room_entry_state(self) -> str:
        """对当前 fresh frame 分类，**不截图 / 不点击 / 只读**。优先级：battle > room_failed > retryable > unknown。

        - `'battle'`：`_battle_entry_positive()` —— 唯一 positive success；
        - `'room_failed'`：`_room_entry_failed()` —— 明确房间失效（庭院 / 探索 / 匹配页）；
        - `'retryable'`：`is_in_room(False)` —— 明确仍在可操作组队房间；
        - `'unknown'`：三者都不是 —— loading / blank / 页面转换过渡帧。
        """
        if self._battle_entry_positive():
            return 'battle'
        if self._room_entry_failed():
            return 'room_failed'
        if self.is_in_room(False):
            return 'retryable'
        return 'unknown'

    def _wait_room_entry_state(self, timeout: float = GI_FIRE_POST_CLICK_TIMEOUT) -> str:
        """post-click / 挑战未就绪时的有界状态轮询，**期间不点任何坐标**。

        返回 `'battle'` / `'room_failed'` / `'retryable'`（出现决定性状态即返回）/ `'timeout'`
        （整个 timer 内一直是 `'unknown'` 过渡 / 未知帧 —— **既不当 success 也不当 failure**，
        timer 内持续等）。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            state = self._classify_room_entry_state()
            if state != 'unknown':
                return state
        return 'timeout'

    def click_fire(self, fire_reaction=None) -> str:
        """房间内点击「挑战 / 开始战斗」的 **bounded battle-entry transaction**（组队进入战斗的公共 owner）。

        返回值（`str`，测试锁全部取值）：
        - `'battle'`：**正向战斗确认**（`_battle_entry_positive()` —— 复用 `is_in_battle()`）——
          唯一 success，caller 才交接 `run_general_battle`；
        - `'room_failed'`：明确房间失效（回庭院 / 探索 / 匹配页）——立即失败，不再点挑战；
        - `'timeout'`：有限 attempt（`GI_FIRE_MAX_TRIES`）/ 墙钟（`GI_FIRE_TIMEOUT`）用尽仍未确认。

        **四态**（`_classify_room_entry_state` / `_wait_room_entry_state`）：BATTLE / ROOM_FAILED /
        RETRYABLE_ROOM / TRANSITION_UNKNOWN。**「不在房间」单独发生 ≠ success**——无 battle / 无
        failure marker 时归 UNKNOWN，有界 polling 等决定性状态，不点任何坐标。

        RETRYABLE_ROOM 下识别 `I_FIRE`（优先）/ `I_FIRE_SEA` → 每 attempt 独立
        `random_delay(*fire_reaction_range(fire_reaction))`（调用方沿配置传入的任务 FIRE override；
        未传 = 公共默认 0.4~0.8s）
        → `sleep` → fresh `screenshot` → 重新分类 + 二次确认挑战按钮仍在 → `appear_then_click(...,
        interval=1, threshold=0.7)`。reaction 期间离开 retryable / 按钮消失 → 不点旧坐标。

        `is_in_room` 状态判据、`run_invite` 的 `Timer(20/30)` / `timer_wait`、`interval=1` click
        节流、minitouch dwell 均不变；不叠 `confirm_delay` / 第二套 reaction。**不接 Fatigue**
        （组队 critical path）。`GI_FIRE_*` 常量 PROVISIONAL / Level C 待标定。
        """
        overall_timer = Timer(GI_FIRE_TIMEOUT).start()
        for attempt in range(1, GI_FIRE_MAX_TRIES + 1):
            if overall_timer.reached():
                break
            self.screenshot()
            state = self._classify_room_entry_state()
            if state == 'battle':
                logger.info('Room challenge: entered battle')
                return 'battle'
            if state == 'room_failed':
                logger.warning('Room challenge: room disbanded / left before click')
                return 'room_failed'
            if state == 'unknown':
                # 过渡 / 未知帧 → 有界等一个决定性状态，不点任何坐标
                state = self._wait_room_entry_state()
                if state == 'battle':
                    logger.info('Room challenge: entered battle')
                    return 'battle'
                if state == 'room_failed':
                    logger.warning('Room challenge: room disbanded during transition')
                    return 'room_failed'
                # 'retryable' / 'timeout' → 下一 attempt（transition-unknown 不当 immediate failure）
                continue
            # state == 'retryable' —— 明确仍在可操作组队房间
            target = None
            if self.appear(self.I_FIRE, threshold=0.7):
                target = self.I_FIRE
            elif self.appear(self.I_FIRE_SEA, threshold=0.7):
                target = self.I_FIRE_SEA
            if target is None:
                # 在房间但挑战按钮还没出现（`room_check_can_fire` 边界 / 加载）→ 有界等，不点
                state = self._wait_room_entry_state()
                if state == 'battle':
                    return 'battle'
                if state == 'room_failed':
                    return 'room_failed'
                continue
            fire_delay = random_delay(*fire_reaction_range(fire_reaction))
            logger.info(f'Room challenge: attempt {attempt}, reaction {fire_delay:.2f}s before click {target.name}')
            sleep(fire_delay)
            self.screenshot()
            state = self._classify_room_entry_state()
            if state == 'battle':
                return 'battle'
            if state == 'room_failed':
                logger.warning('Room challenge: room disbanded during reaction')
                return 'room_failed'
            if state != 'retryable':
                # reaction 期间离开 retryable（transition / unknown）→ 不点旧坐标
                logger.info('Room challenge: left retryable during reaction, re-evaluate')
                continue
            if not self.appear(target, threshold=0.7):
                # 挑战按钮在 reaction 期间消失但仍在房间 → 不点旧坐标
                logger.info('Room challenge: button gone during reaction, re-evaluate')
                continue
            self.appear_then_click(target, interval=1, threshold=0.7)
            state = self._wait_room_entry_state()
            if state == 'battle':
                logger.info('Room challenge: entered battle after click')
                return 'battle'
            if state == 'room_failed':
                logger.warning('Room challenge: room disbanded after click')
                return 'room_failed'
            # 'retryable' / 'timeout' → 下一 attempt
        logger.warning('Room challenge: bounded attempts / timeout without entering battle')
        return 'timeout'

    @cached_property
    def room_type(self) -> RoomType:
        """
        只需要在队长进入的时候判断一次就可以了，任务后面之间使用

        :return:
        """
        self.screenshot()
        room_type = self.check_room_type(image=self.device.image)
        logger.info(f'Room type: {room_type}')
        return room_type

    def check_room_type(self, image: np.array = None, pre_type: RoomType = None) -> RoomType | None:
        """
        检查房间类型
        :param image:
        :param pre_type: 可以先指定这个类型，如果不指定，就自动检查
        :return:
        """

        def check_3(img) -> bool:
            appear = False
            if self.I_ADD_1.match(img) and self.I_ADD_2.match(img):
                appear = True
            return appear

        def check_2(img) -> bool:
            appear = False
            if not self.I_ADD_1.match(img) and self.I_ADD_2.match(img):
                appear = True
            return appear

        def check_5(img) -> bool:
            appear = False
            if self.I_ADD_5_1.match(img) and self.I_ADD_5_2.match(img) \
                    and self.I_ADD_5_3.match(img) and self.I_ADD_5_4.match(img):
                appear = True
            return appear

        def check_eternity_sea(img) -> bool:
            appear = False
            if self.I_LOCK_SEA.match(img) or self.I_UNLOCK_SEA.match(img):
                appear = True
            return appear

        def check_bondling_fairyland(img) -> bool:
            return self.I_ADD_1.match(img) and not self.I_ADD_2.match(img)

        room_type = None
        if pre_type is not None:
            match pre_type:
                case RoomType.NORMAL_2:
                    room_type = RoomType.NORMAL_2 if check_2(image) else None
                case RoomType.NORMAL_3:
                    room_type = RoomType.NORMAL_3 if check_3(image) else None
                case RoomType.NORMAL_5:
                    room_type = RoomType.NORMAL_5 if check_5(image) else None
                case RoomType.ETERNITY_SEA:
                    room_type = RoomType.ETERNITY_SEA if check_eternity_sea(image) else None
        if room_type:
            return room_type
        if room_type is None and check_2(image):
            room_type = RoomType.NORMAL_2
            return room_type
        if room_type is None and check_3(image):
            room_type = RoomType.NORMAL_3
            return room_type
        if room_type is None and check_5(image):
            room_type = RoomType.NORMAL_5
            return room_type
        if room_type is None and check_eternity_sea(image):
            room_type = RoomType.ETERNITY_SEA
            return room_type
        if room_type is None and check_bondling_fairyland(image):
            room_type = RoomType.BONDLING_FAIRYLAND
            return room_type
        return room_type

    def ensure_room_type(self, friend_number: int = None) -> bool:
        """
        确认设定的邀请人数是否会超出房间的最大
        :param friend_number: 这个输入的是用户选项中的invite_number
        :return:  如果超出了，就返回False
        """
        if friend_number == 2:
            if self.room_type == RoomType.NORMAL_2:
                # 整个房间就可以两个人，还邀请两个 这个是报错的
                logger.error('Room can only be one people, but invite two people')
                return False
            elif self.room_type == RoomType.ETERNITY_SEA:
                # 永生之海，只能邀请一个人
                logger.error('Room can only be one people, but invite two people')
                return False
            return True
        return True

    @cached_property
    def friend_class(self) -> list[str]:
        return ['好友', '最近', '跨区', '寮友', '蔡友', '路区', '察友', '区']

    @staticmethod
    def _normalize_friend_name_text(text: str) -> str:
        if text is None:
            return ''
        return str(text).replace(' ', '').replace('　', '').strip()

    def _find_exact_friend_area(self, rule, name: str) -> tuple[int, int, int, int] | None:
        target_name = self._normalize_friend_name_text(name)
        if not target_name:
            return None

        boxed_results = rule.detect_and_ocr(self.device.image)
        if not boxed_results:
            return None

        for result in boxed_results:
            ocr_text = self._normalize_friend_name_text(result.ocr_text)
            if ocr_text != target_name:
                continue
            box = result.box
            rec_x = box[0, 0]
            rec_y = box[0, 1]
            rec_w = box[1, 0] - box[0, 0]
            rec_h = box[2, 1] - box[0, 1]
            area = (
                int(rec_x + rule.roi[0]),
                int(rec_y + rule.roi[1]),
                int(rec_w),
                int(rec_h)
            )
            logger.info(f'Exact match friend "{name}" in {rule.name} at {area}')
            return area
        return None

    def _wait_selected_appear(self, pre_cnt: int, timeout: float = 2) -> bool:
        """
        点击后等待选中动画结束。要求连续两帧都识别到选中，避免单帧滞后误判。
        """
        timer = Timer(timeout).start()
        selected_count = 0
        while not timer.reached():
            self.screenshot()
            if len(self.I_SELECTED.match_all_any(self.device.image, frame_id=self.device.image_frame_id)) >= pre_cnt + 1:
                selected_count += 1
                if selected_count >= 2:
                    return True
            else:
                selected_count = 0
        return False

    def _detect_select(self, name: str = None) -> bool:
        """
        在当前的页面检测是否有好友， 如果有就选中这个好友
        :return: 是否成功选中好友
        """
        if not name:
            return False
        max_retry = 3
        self.screenshot()
        pre_cnt = len(self.I_SELECTED.match_all_any(self.device.image, frame_id=self.device.image_frame_id))
        for _ in range(max_retry):
            self.screenshot()
            if len(self.I_SELECTED.match_all_any(self.device.image, frame_id=self.device.image_frame_id)) >= pre_cnt + 1:
                return True
            rule = self.O_FRIEND_NAME_1
            select_area = self._find_exact_friend_area(rule, name)
            if select_area is None:
                rule = self.O_FRIEND_NAME_2
                select_area = self._find_exact_friend_area(rule, name)
            if select_area is None:
                logger.info('Current page no exact friend')
                return False
            # T7-5 Stage 2：匹配到的好友名 OCR bbox 是安全点击 ROI，从任务私有整框均匀
            # `_random_point_in_area` 迁到统一 preferred 模型（未登记 → RULE_FALLBACK）。
            click_x, click_y = ClickSampler.sample_target(select_area, rule.name)
            execute_single_click(self.device, FinalPoint(click_x, click_y), control_name=rule.name)
            if self._wait_selected_appear(pre_cnt):
                return True
        logger.warning(f'Find friend "{name}" but failed to select')
        return False

    def _get_invite_friend_list(self, config: InviteConfig) -> list[str]:
        """
        获取邀请名单。
        :param config: 邀请配置
        :return: 由配置拆分得到的好友名称列表
        """
        return config.friend_list.split('\n')

    def _open_invite_panel_if_needed(self, open_invite: bool) -> bool:
        """
        按需打开邀请面板。
        :param open_invite: 是否需要在当前流程中主动打开邀请面板
        :return: True 表示继续邀请流程，False 表示直接提前结束（保持当前兼容语义）
        """
        if not open_invite:
            return True
        logger.info('Click add to invite friend')
        no_click_timeout = Timer(5).start()
        click_timer = Timer(1)
        while True:
            self.screenshot()
            if no_click_timeout.started() and no_click_timeout.reached():
                logger.warning('Cannot invite friend, maybe already existing')
                return False
            if self.appear(self.I_LOAD_FRIEND) or self.appear(self.I_INVITE_ENSURE):
                return True
            if not click_timer.started() or click_timer.reached():
                # 房间「+」加人位：稳定可见的普通按钮，NORMAL reaction + fresh confirm（位子已被占则不点）。
                clicked = self.appear_then_click(self.I_ADD_1, policy=InteractionPolicy.NORMAL) or \
                    self.appear_then_click(self.I_ADD_2, policy=InteractionPolicy.NORMAL) or \
                    self.appear_then_click(self.I_ADD_5_4, policy=InteractionPolicy.NORMAL) or \
                    self.appear_then_click(self.I_ADD_SEA, policy=InteractionPolicy.NORMAL)
                click_timer.reset()
                if clicked:
                    no_click_timeout.reset()

    @staticmethod
    def _normalize_friend_class_name(friend_class: str) -> str:
        """
        归一化好友分类文字，消除 OCR 近形字干扰。
        :param friend_class: OCR 识别到的分类文本
        :return: 归一化后的分类文本
        """
        mapping = {'蔡友': '寮友', '路区': '跨区', '察友': '寮友', '区': '跨区'}
        return mapping.get(friend_class, friend_class)

    def _read_friend_classes(self) -> list[str]:
        """
        识别当前可用的好友分类页签。
        :return: 分类列表，顺序与页签顺序一致
        """
        raw_list = [
            self.O_F_LIST_1.ocr(self.device.image).replace(' ', '').replace('、', ''),
            self.O_F_LIST_2.ocr(self.device.image).replace(' ', '').replace('、', ''),
            self.O_F_LIST_3.ocr(self.device.image).replace(' ', '').replace('、', ''),
            self.O_F_LIST_4.ocr(self.device.image).replace(' ', '').replace('、', '')
        ]
        friend_class = []
        for item in raw_list:
            if item is not None and item != '' and item in self.friend_class:
                friend_class.append(self._normalize_friend_class_name(item))
        logger.info(f'Friend class: {friend_class}')
        return friend_class

    def _switch_friend_class(self, index: int) -> None:
        """
        切换到指定索引的好友分类标签。
        :param index: 分类索引，0~3
        :return:
        """
        match index:
            case 0:
                self.ui_click(self.I_FLAG_1_OFF, self.I_FLAG_1_ON, interval=1.2)
            case 1:
                self.ui_click(self.I_FLAG_2_OFF, self.I_FLAG_2_ON, interval=1.2)
            case 2:
                self.ui_click(self.I_FLAG_3_OFF, self.I_FLAG_3_ON, interval=1.2)
            case 3:
                self.ui_click(self.I_FLAG_4_OFF, self.I_FLAG_4_ON, interval=1.2)

    def _select_current_page_friends(self, friend_list: list[str], selected_set: set[str]) -> None:
        """
        在当前分类页中尝试选择多个好友。
        :param friend_list: 目标好友名称列表
        :param selected_set: 已成功选中的好友集合（原地更新）
        :return:
        """
        for name in friend_list:
            if name not in selected_set and self._detect_select(name):
                selected_set.add(name)

    def _select_recent_mode_friends(self, friend_class: list[str], friend_list: list[str], selected_set: set[str]) -> bool:
        """
        在“最近”分类下执行好友选择。
        :param friend_class: 当前可用分类列表
        :param friend_list: 目标好友名称列表
        :param selected_set: 已成功选中的好友集合（原地更新）
        :return: True 表示流程可继续，False 表示失败
        """
        logger.info('Find recent friend')
        if '最近' not in friend_class:
            logger.warning('No recent friend')
            return False
        recent_index = friend_class.index('最近')
        self._switch_friend_class(recent_index)
        sleep(0.5)
        logger.info('Now find friend in ”最近“')
        self._select_current_page_friends(friend_list, selected_set)
        return True

    def _select_auto_mode_friends(self, friend_class: list[str], friend_list: list[str], selected_set: set[str]) -> None:
        """
        自动遍历所有分类并尝试选择目标好友。
        :param friend_class: 当前可用分类列表
        :param friend_list: 目标好友名称列表
        :param selected_set: 已成功选中的好友集合（原地更新）
        :return:
        """
        for index in range(len(friend_class)):
            if len(selected_set) == len(friend_list):
                break
            self._switch_friend_class(index)
            sleep(0.5)
            logger.info(f'Now find friend in {friend_class[index]}')
            self._select_current_page_friends(friend_list, selected_set)

    def _confirm_invite_and_validate(self, selected_set: set[str], friend_list: list[str], confirm_rule: RuleImage = None) -> bool:
        """
        点击邀请确认并校验最终结果。
        :param selected_set: 已成功选中的好友集合
        :param friend_list: 目标好友名称列表
        :return: 全部选中返回 True，否则 False
        """
        logger.info('Click invite ensure')
        if not confirm_rule:
            confirm_rule = self.I_INVITE_ENSURE
        if not self.appear(confirm_rule):
            logger.warning('No appear invite ensure while invite friend')
        self.ui_click_until_disappear(confirm_rule)
        if len(selected_set) != len(friend_list):
            logger.warning('Cannot find friend')
            return False
        return True

    def invite_again(self, default_invite: bool=True) -> bool:
        """
        作为队长战斗胜利后再次邀请队友，
        :param default_invite:  是否勾选默认
        :return:
        """
        logger.info('Invite again')
        # 判断是否进入界面
        while 1:
            self.screenshot()
            if self.appear(self.I_GI_SURE):
                break
        # 如果勾选了默认邀请
        if default_invite:
            logger.info('Click default invite')
            while 1:
                self.screenshot()
                if self.appear(self.I_I_DEFAULT):
                    break
                if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                    continue
        else:
            logger.info('Click no default invite')
            while 1:
                self.screenshot()
                if self.appear(self.I_I_NO_DEFAULT):
                    break
                if self.appear_then_click(self.I_I_DEFAULT, interval=1):
                    continue

        # 点击确认
        logger.info('Click invite ensure')
        while 1:
            self.screenshot()
            if not self.appear(self.I_GI_SURE):
                break
            if self.appear_then_click(self.I_GI_SURE):
                continue

    def check_and_invite(self, default_invite: bool=True) -> bool:
        """
        队长战斗后 邀请队友
        :param default_invite:
        :return:
        """
        if not self.appear(self.I_GI_SURE):
            return False

        if default_invite:
            # 有可能是挑战失败的
            if self.appear(self.I_I_DEFAULT) or self.appear(self.I_I_NO_DEFAULT):
                logger.info('Click default invite')
                while 1:
                    self.screenshot()
                    if self.is_in_room(False):
                        break
                    if self.appear(self.I_I_DEFAULT):
                        break
                    if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                        continue
        # 点击确认
        while 1:
            self.screenshot()
            if self.is_in_room(False):
                break
            if not self.appear(self.I_GI_SURE):
                break
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                continue

        return True

    def check_then_accept(self) -> bool:
        """
        队员接受邀请
        :return:
        """
        if not self.appear_accept():
            return False
        logger.info('Click accept')
        while True:
            self.screenshot()
            if self.is_in_room():
                return True
            # 被秒开
            # https://github.com/runhey/OnmyojiAutoScript/issues/230
            if self.appear(GeneralBattleAssets.I_EXIT):
                return False
            if self.appear_then_click(self.I_I_NO_DEFAULT, interval=1):
                continue
            if self.appear_then_click(self.I_GI_SURE, interval=1):
                continue
            if self.appear_then_click(self.I_I_ACCEPT_DEFAULT, interval=1):
                continue
            if self.appear_then_click(self.I_I_ACCEPT, interval=1) or \
                    self.appear_then_click(self.I_I_ACCEPT_APPRENTICE, interval=1):
                continue
        return True

    def appear_accept(self) -> bool:
        """出现邀请标志"""
        return self.appear(self.I_I_ACCEPT) or self.appear(self.I_I_ACCEPT_APPRENTICE)

    def wait_battle(self, wait_time: time) -> bool:
        """
        在房间等待,(要求保证在房间里面) 队长开启战斗
        如果队长跑路了，或者的等待了很久还没开始
        :return: 如果成功进入战斗（反正就是不在房间 ）返回 True
                 如果失败了，（退出房间）返回 False
        """
        self.timer_emoji = Timer(15)
        self.timer_emoji.start()
        wait_second = wait_time.second + wait_time.minute * 60
        self.timer_wait = Timer(wait_second)
        self.timer_wait.start()
        logger.info(f'Wait battle {wait_second} seconds')
        success = True
        while 1:
            self.screenshot()

            # 如果自己在探索界面或者是庭院，那就是房间已经被销毁了
            # 两帧确认避免加载过渡页误匹配
            if self.appear(GameUiAssets.I_CHECK_MAIN) or self.appear(GameUiAssets.I_CHECK_EXPLORATION):
                self.screenshot()
                if self.appear(GameUiAssets.I_CHECK_MAIN) or self.appear(GameUiAssets.I_CHECK_EXPLORATION):
                    logger.warning('Room destroyed')
                    success = False
                    break

            if self.timer_wait.reached():
                logger.warning('Wait battle time out')
                success = False
                break

            # 如果队长跑路了，自己变成了队长: 自己也要跑路
            if self.appear(self.I_FIRE) or self.appear(self.I_FIRE_SEA):
                logger.warning('Leader run away while wait battle and become leader now')
                success = False
                break

            # 判断是否进入战斗
            if self.is_in_room(is_screenshot=False):
                if self.timer_emoji.reached():
                    self.timer_emoji.reset()
                    self.appear_then_click(self.I_GI_EMOJI_1)
                    self.appear_then_click(self.I_GI_EMOJI_2)
            else:
                break

        # 调出循环只有这些可能性：
        # 1. 进入战斗（ui是战斗）
        # 2. 队长跑路（自己还是在房间里面）
        # 3. 等待时间到没有开始（还是在房间里面）
        # 4. 房间的时间到了被迫提出房间（这个时候来到了探索界面）
        if not success:
            logger.info('Leave room')
            self.exit_room()

        return success
