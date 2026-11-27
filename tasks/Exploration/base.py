# This Python file uses the following encoding: utf-8
# @author AzurTian
import time
import numpy as np
from cached_property import cached_property
from datetime import timedelta, datetime
from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.base.timer import Timer
from module.base.frame_wait import wait_for_changed_and_stable

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.Exploration.assets import ExplorationAssets
from tasks.Exploration.config import ChooseRarity, UpType, ExplorationLevel, AutoRotate, UserStatus, Exploration
from tasks.Component.GeneralBattle.general_battle import GeneralBattle, ExitMatcher, BattleContext, BattleAction
from tasks.GameUi.game_ui import GameUi
from tasks.Utils.config_enum import ShikigamiClass
import tasks.Exploration.page as pages

from module.logger import logger
from module.exception import TaskEnd, GameStuckError
from module.atom.animate import RuleAnimate
from module.interaction_policy import InteractionPolicy
from typing import Optional


# 章节列表的结构等待只观察现有 OCR 列表区域。ROI 由
# O_E_EXPLORATION_LEVEL_NUMBER.roi=(x, y, w, h) 直接换算为 ltrb。
# 以下阈值均为 Level A/B provisional 参数，需用真机滚动帧差分布校准。
EXPLORATION_LEVEL_SETTLE_ROI = (1065, 203, 1189, 555)
EXPLORATION_LEVEL_CHANGED_THRESHOLD = 0.02
EXPLORATION_LEVEL_STABLE_THRESHOLD = 0.01
EXPLORATION_LEVEL_STABLE_FRAMES = 2
EXPLORATION_LEVEL_SETTLE_TIMEOUT = 1.5
EXPLORATION_LEVEL_POLL_INTERVAL = 0.12

# Boss 胜利直退：从确认胜利到观察到合法外层页的总上限。超时视为退出失败，不假装进入下一轮。
BOSS_EXIT_TIMEOUT = 30

# fire() 每次实际点击后等待战斗页出现的结果窗口（秒）。依据：循环里两次点击的最小间隔是 0.8 秒
# （点击没出战斗页就会重击），窗口取其 2.5 倍，覆盖进战斗准备页的转场；最后一次点击或 10 秒上限边缘
# 的点击也据此有一次观察机会。
FIRE_RESULT_WINDOW = 2.0

# Boss 胜利直退状态（任务内存，不落盘）：
#   ''        没有进行中的直退
#   'exiting' 已确认 Boss 胜利，正在退出本次探索；跳过地图宝箱 / 小纸人
#   'exited'  已观察到外层页；新一轮真正开始前外层不补领刚才跳过的宝箱
BOSS_EXIT_IDLE = ''
BOSS_EXIT_EXITING = 'exiting'
BOSS_EXIT_EXITED = 'exited'


class BaseExploration(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, ReplaceShikigami, SwitchSoul, ExplorationAssets):
    fire_monster_type: str = ''
    need_exit: bool = False
    user_status: UserStatus = UserStatus.ALONE
    wait_start_time: datetime = datetime.now()
    pre_page: pages.Page = None
    # 本次战斗归属（'boss' / 'normal' / ''）：由 fire() 在确认进入战斗页时写入，run_on_battle 消费一次后清空
    _battle_target: str = ''
    _boss_exit_phase: str = BOSS_EXIT_IDLE
    _boss_exit_timer: Optional[Timer] = None
    # 刚完成的 Boss 直退循环尚未走过单人疲劳安全节点；只消费一次
    _boss_cycle_fatigue_due: bool = False

    def _exit_matcher(self) -> ExitMatcher:
        return pages.any_of(self.I_E_SETTINGS_BUTTON, self.I_E_AUTO_ROTATE_ON, self.I_E_AUTO_ROTATE_OFF)

    @cached_property
    def _config(self) -> Exploration:
        self.config.exploration.general_battle_config.lock_team_enable = True
        limit_time = self.config.exploration.exploration_config.limit_time
        self.limit_time: timedelta = timedelta(
            hours=limit_time.hour,
            minutes=limit_time.minute,
            seconds=limit_time.second
        )
        return self.config.model.exploration

    @cached_property
    def _match_end(self):
        return RuleAnimate(self.I_SWIPE_END)

    def pre_process(self):
        if self._config.switch_soul_config.enable:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul(self._config.switch_soul_config.switch_group_team)

        if self._config.switch_soul_config.enable_switch_by_name:
            self.goto_page(pages.page_shikigami_records)
            self.run_switch_soul_by_name(self._config.switch_soul_config.group_name,
                                         self._config.switch_soul_config.team_name)
        # 开启加成
        con = self.config.exploration.exploration_config
        if con.buff_gold_50_click or con.buff_gold_100_click or con.buff_exp_50_click or con.buff_exp_100_click:
            self.goto_page(pages.page_main)
            self.open_buff()
            if con.buff_gold_50_click:
                self.gold_50()
            if con.buff_gold_100_click:
                self.gold_100()
            if con.buff_exp_50_click:
                self.exp_50()
            if con.buff_exp_100_click:
                self.exp_100()
            self.close_buff()
        self.user_status = self._config.exploration_config.user_status
        self.wait_start_time = datetime.now()  # 重置等待时间
        self._reset_boss_exit_state()

    def post_process(self):
        self.goto_page(pages.page_exploration)
        con = self._config.exploration_config
        if con.buff_gold_50_click or con.buff_gold_100_click or con.buff_exp_50_click or con.buff_exp_100_click:
            self.goto_page(pages.page_main)
            self.open_buff()
            self.gold_50(is_open=False)
            self.gold_100(is_open=False)
            self.exp_50(is_open=False)
            self.exp_100(is_open=False)
            self.close_buff()
        self.set_next_run(task='Exploration', success=True, finish=False)
        raise TaskEnd

    def _reset_boss_exit_state(self) -> None:
        self._battle_target = ''
        self._boss_exit_phase = BOSS_EXIT_IDLE
        self._boss_exit_timer = None
        self._boss_cycle_fatigue_due = False

    def begin_boss_exit(self) -> None:
        """Boss 战斗确认胜利后进入直退：跳过本轮地图宝箱 / 小纸人，交页面分发执行退出。"""
        logger.info('Boss battle won, skip map rewards and exit exploration')
        self._boss_exit_phase = BOSS_EXIT_EXITING
        self._boss_exit_timer = Timer(BOSS_EXIT_TIMEOUT).start()
        self.need_exit = True
        self.fire_monster_type = ''

    def observe_boss_exit_outer(self, current_page) -> None:
        """分发拿到新截图识别出的页面；正向命中外层页才算退出成功（点击发出不算）。"""
        if self._boss_exit_phase != BOSS_EXIT_EXITING:
            return
        if current_page in (pages.page_exp_entrance, pages.page_exploration):
            logger.info('Boss exit done, reached outer page')
            self._boss_exit_phase = BOSS_EXIT_EXITED
            self._boss_exit_timer = None
            self._boss_cycle_fatigue_due = True
            self.need_exit = False

    def guard_boss_exit_deadline(self) -> None:
        if self._boss_exit_phase == BOSS_EXIT_EXITING and self._boss_exit_timer is not None                 and self._boss_exit_timer.reached():
            raise GameStuckError(f'Boss exit not finished within {BOSS_EXIT_TIMEOUT}s')

    def end_boss_exit_handoff(self) -> None:
        """新一轮真正开始（进地图 / 进战斗 / 组队开战），外层不再跳过宝箱。"""
        if self._boss_exit_phase == BOSS_EXIT_EXITED:
            self._boss_exit_phase = BOSS_EXIT_IDLE

    def _wait_chapter_list_settle(self, baseline) -> bool:
        """等待章节列表发生结构变化并停稳；结果不代表目标章节已找到。"""
        wait = wait_for_changed_and_stable(
            baseline,
            self.device.screenshot,
            roi=EXPLORATION_LEVEL_SETTLE_ROI,
            changed_threshold=EXPLORATION_LEVEL_CHANGED_THRESHOLD,
            stable_threshold=EXPLORATION_LEVEL_STABLE_THRESHOLD,
            stable_frames=EXPLORATION_LEVEL_STABLE_FRAMES,
            timeout=EXPLORATION_LEVEL_SETTLE_TIMEOUT,
            poll_interval=EXPLORATION_LEVEL_POLL_INTERVAL,
        )
        logger.info(
            'Exploration chapter swipe wait: changed=%s, stable=%s, timeout=%s, '
            'elapsed=%.3f, diff=%.3f'
            % (wait.changed, wait.stable, wait.timed_out, wait.elapsed, wait.last_difference)
        )
        return wait.success

    # 打开指定的章节：
    def open_expect_level(self):
        swipeCount = 0
        config_exploration_level = self.config.exploration.exploration_config.exploration_level
        while True:
            # 判断有无目标章节
            self.screenshot()
            # 获取当前章节名
            results = self.O_E_EXPLORATION_LEVEL_NUMBER.detect_and_ocr(self.device.image)
            text1 = [result.ocr_text for result in results]
            exp_level_enum_list = []
            for txt in text1:
                try:
                    exp_level_enum_list.append(ExplorationLevel(txt))
                except ValueError as e:
                    logger.warning(f'convert {txt} failed')
            sorted(exp_level_enum_list, key=lambda x: x.get_index())  # Sort by index
            # 判断当前章节有无目标章节
            result = set(text1).intersection({config_exploration_level})
            # 有则跳出检测
            if self.appear(self.I_E_EXPLORATION_CLICK) or result and len(result) > 0:
                break
            # 章节页确认弹窗：普通稳定选择，NORMAL reaction
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1, policy=InteractionPolicy.NORMAL):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1, policy=InteractionPolicy.NORMAL):
                continue
            self.device.click_record_clear()
            swiped = False
            if len(exp_level_enum_list) > 0:
                min_level = exp_level_enum_list[0]
                max_level = exp_level_enum_list[-1]
                if config_exploration_level.get_index() < min_level.get_index():
                    settle_baseline = self.device.image
                    swiped = self.swipe(self.S_SWIPE_LEVEL_UP)
                elif config_exploration_level.get_index() > max_level.get_index():
                    settle_baseline = self.device.image
                    swiped = self.swipe(self.S_SWIPE_LEVEL_DOWN)
            swipeCount += 1
            debug_info = f"Swiped {swipeCount} times, current exploration level: {text1}"
            logger.info(debug_info)
            if swipeCount >= 25:
                raise GameStuckError(
                    f"Swiped too many times ({swipeCount}), seems stuck in exploration level selection"
                )
            if swiped:
                # 这里只等待滑动后的结构变化与停稳；下一轮 OCR 仍负责业务收敛。
                self._wait_chapter_list_settle(settle_baseline)
            else:
                # 没有发出滑动时保留旧 1 秒作为 OCR / 动作未就绪的 retry throttle。
                time.sleep(1)

        # 选中对应章节
        while 1:
            self.screenshot()
            # 章节页确认弹窗：普通稳定选择，NORMAL reaction
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1, policy=InteractionPolicy.NORMAL):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1, policy=InteractionPolicy.NORMAL):
                continue
            self.O_E_EXPLORATION_LEVEL_NUMBER.keyword = config_exploration_level
            if self.ocr_appear_click(self.O_E_EXPLORATION_LEVEL_NUMBER):
                self.wait_until_appear(self.I_E_EXPLORATION_CLICK, wait_time=3)
            if self.appear(self.I_E_EXPLORATION_CLICK):
                break
            if self.is_in_room():
                break

        return True

    def fill_shikigami(self):
        """填充式神(最后回到探索主界面)"""
        # 候补出战数量识别
        cu, res, total = self.O_E_ALTERNATE_NUMBER.ocr(self.device.image)
        if cu >= 40:
            logger.info("Alternate number is enough")
            self.goto_page(pages.page_exp_main)
            return
        choose_rarity = self._config.exploration_config.choose_rarity
        rarity = ShikigamiClass.N if choose_rarity == ChooseRarity.N else ShikigamiClass.MATERIAL
        self.click(self.C_CLICK_STANDBY_TEAM)  # 先点击候补出战区域
        self.switch_shikigami_class(rarity)  # 切换式神类别
        pre = -1
        while True:
            time.sleep(0.5)
            self.screenshot()
            if not self.appear(self.I_E_OPEN_SETTINGS):
                logger.warning('Opening settings failed')
                return
            cur, res, total = self.O_E_ALTERNATE_NUMBER.ocr(self.device.image)
            if cur >= 40:
                logger.info(f'Alternate number is enough, exit')
                break
            # 连续向后滑动超过6次还能识别到候补狗粮(1. 滑动的不够× 2. 没新狗粮了)
            if self.device.click_record.count(self.S_SWIPE_SHIKI_TO_LEFT.name) >= 6 or \
                    self.device.click_record.count(self.S_SWIPE_SHIKI_TO_LEFT_ONE.name) >= 6:
                if cur > 0: # 上了一部分狗粮, 先用着
                    logger.warning(f'Alternate number is not enough, current: {cur}')
                    break
                # 滑动很多次了, 结果也没成功上狗粮, 要么滑的不够(基本不可能)要么没狗粮(大概率)
                # TODO: 1. 增加选项狗粮不够时继续打 2. 去召唤界面换狗粮(这里还有问题是否去商店买厕纸)
                raise GameStuckError(f"Alternate number is not enough")
            # 识别到右侧候补狗粮, 则大幅度向右移动
            if self.appear(self.I_E_ROTATE_EXIST_RIGHT):
                self.swipe(self.S_SWIPE_SHIKI_TO_LEFT)
                continue
            # 识别到候补狗粮, 则滑动一部分
            if self.appear(self.I_E_RATATE_EXSIT):
                self.swipe(self.S_SWIPE_SHIKI_TO_LEFT_ONE)
                continue
            # 没识别到候补狗粮(没狗粮/已经全满级)导致不滑动了, 但是上狗粮后数量又没变
            if pre == cur:
                if cur > 0:  # 上了一部分狗粮, 先用着
                    logger.warning(f'Alternate number is not enough, current: {cur}')
                    break
                # TODO: 同上一个todo
                raise GameStuckError(f"Alternate number is not enough")
            pre = cur
            # 长按上狗粮
            self.click(self.L_ROTATE_1)
            self.device.click_record_clear()
        self.goto_page(pages.page_exp_main)

    # 找up按钮
    def search_up_fight(self, up_type: UpType = None) -> Optional[RuleImage | RuleGif]:
        up_type = self._config.exploration_config.up_type if up_type is None else up_type
        if up_type == UpType.ALL and self.appear(self.I_NORMAL_BATTLE_BUTTON):
            return self.I_NORMAL_BATTLE_BUTTON
        match up_type:
            case UpType.EXP:
                find_flag = self.I_UP_EXP
            case UpType.COIN:
                find_flag = self.I_UP_COIN
            case UpType.DARUMAA:
                find_flag = self.I_UP_DARUMA
            case _:
                find_flag = self.I_UP_EXP
        appear = self.appear(find_flag)
        if not appear:
            return None
        # logger.info(f'Found up type: {up_type} at  {find_flag.roi_front}')
        x, y, _, _ = find_flag.roi_front
        x_center, y_center = find_flag.front_center()
        roi_back_y = max(0, y - 300)
        roi_back_h = y - 20 - roi_back_y
        roi_back_x = max(0, x - 160)
        roi_back_w = min(1280, x + 200) - roi_back_x
        # self.I_NORMAL_BATTLE_BUTTON.roi_back = [roi_back_x, roi_back_y, roi_back_w, roi_back_h]
        # logger.info(f'It will search normal battle button at {roi_back_x, roi_back_y, roi_back_w, roi_back_h}')
        matches = self.I_NORMAL_BATTLE_BUTTON.match_all(
            image=self.device.image,
            threshold=0.9,
            roi=[roi_back_x, roi_back_y, roi_back_w, roi_back_h],
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        distances = []
        for match in matches:
            x_match, y_match = match[1], match[2]
            distance = np.linalg.norm(
                np.array([x_center, y_center]) - np.array([x_match, y_match])
            )
            distances.append((distance, match))
        distances.sort(key=lambda x: x[0], reverse=False)
        match = distances[0][1]
        roi_front = list(match[1:])  # x,y,w,h
        self.I_NORMAL_BATTLE_BUTTON.roi_front = roi_front
        # logger.info(f"Found normal battle button at {roi_front}")
        self.fire_monster_type = 'normal'
        return self.I_NORMAL_BATTLE_BUTTON

    def activate_realm_raid(self, con_scrolls, con, current_page: pages.Page | None) -> None:
        # 判断是否开启突破票检测
        if not con_scrolls.scrolls_enable or current_page is None or \
                current_page not in (pages.page_exploration, pages.page_exp_entrance):
            return
        if current_page == pages.page_exp_entrance:
            cu, res, total = self.O_REALM_RAID_NUMBER1.ocr(self.device.image)
        else:
            cu, res, total = self.O_REALM_RAID_NUMBER.ocr(self.device.image)
        # 判断突破票数量
        if cu < con_scrolls.scrolls_threshold:
            return
        # 关闭加成
        if con.buff_gold_50_click or con.buff_gold_100_click or con.buff_exp_50_click or con.buff_exp_100_click:
            self.goto_page(pages.page_main)
            self.open_buff()
            self.gold_50(is_open=False)
            self.gold_100(is_open=False)
            self.exp_50(is_open=False)
            self.exp_100(is_open=False)
            self.close_buff()
        # 设置下次执行行时间
        logger.info("RealmRaid and Exploration  set_next_run !")
        next_run = datetime.now() + con_scrolls.scrolls_cd
        self.goto_page(pages.page_exploration)
        self.set_next_run(task='Exploration', success=False, finish=False, target=next_run)
        self.set_next_run(task='RealmRaid', success=False, finish=False, server=False, target=datetime.now())
        self.set_next_run(task='MemoryScrolls', success=False, finish=False, target=datetime.now())
        raise TaskEnd

    def check_exit(self, current_page: pages.Page | None) -> bool:
        # True 表示要退出这个任务
        if self.current_count >= self._config.exploration_config.minions_cnt:
            logger.info('Minions count is enough, exit')
            return True
        if datetime.now() - self.start_time >= self.limit_time:
            logger.info('Exploration time limit out, exit')
            return True
        if self.user_status == UserStatus.MEMBER and \
                datetime.now() - self.wait_start_time >= self._config.invite_config.wait_time_v:
            logger.info('Member wait time out, exit')
            return True
        self.activate_realm_raid(self._config.scrolls, self._config.exploration_config, current_page)
        return False

    def _observe_fire_result(self, button) -> bool:
        """fire() 的一次只读观察：截图并识别，已进入战斗页 / 退出弹窗返回 True。不发点击。

        归属只在这里正向识别到战斗页时写入；退出弹窗分支清空，不记作开战。
        """
        self.screenshot()
        cur_page = self.get_current_page()
        # 退出动画期间可能再次识别到怪物开始攻击, 因此取消退出
        if cur_page == pages.page_exp_exit:
            self.need_exit = False
            self._battle_target = ''
            return True
        if cur_page in (pages.page_battle_prepare, pages.page_battle):
            # 只有确认进入战斗页才记录归属；仅识别到按钮或点击不算
            self._battle_target = 'boss' if button is self.I_BOSS_BATTLE_BUTTON else 'normal'
            return True
        return False

    def fire(self, button) -> bool:
        """进入战斗(True:成功进入战斗/识别到退出弹窗, 否则False)
        这里之所以违反页面特性使用循环, 是因为由于怪物移动的原因可能导致一次点击会无法进入战斗,
        回到外循环之后由于UP旋转的特性可能导致识别不到怪物然后开始滑动, 导致错过的怪物更多
        因此这里使用贪心的思想, 只要识别到怪物一次就尽最大可能直接进入战斗, 保证尽可能有怪则打

        点击预算（最多 4 次）与结果确认分开：每次实际发出的点击都有 FIRE_RESULT_WINDOW 秒的结果窗口，
        主循环因次数用完或 10 秒上限退出时，若最后一次点击的窗口还没观察完，就在窗口内只截图识别
        （不再点击）。总耗时 <= 10 秒主循环 + 一次点击间隔内的一帧 + FIRE_RESULT_WINDOW。
        """
        self._battle_target = ''  # 上次未被消费的归属不带入本次
        max_tries = 4
        timeout_timer = Timer(10).start()  # 增加最大时间限制, 防止因未知因素引起无限等待
        last_click_window = None
        while max_tries > 0 and not timeout_timer.reached():
            if self._observe_fire_result(button):
                return True
            if self.appear_then_click(button, interval=0.8):
                max_tries -= 1
                last_click_window = Timer(FIRE_RESULT_WINDOW).start()
        if last_click_window is None:
            return False  # 点击从未实际发出, 没有待确认的结果
        # 尾部确认：不发点击、不重置主循环计时器；至少观察一帧，窗口到期即止
        while True:
            if self._observe_fire_result(button):
                return True
            if last_click_window.reached():
                return False

    def switch_rotate(self) -> bool:
        """按配置管理「自动添加候补式神」。返回是否执行了切换动作。

        轮换模式的开 / 关归**用户**所有：`auto_rotate=no`（默认）时脚本只观察，
        **绝不**点 `I_E_AUTO_ROTATE_ON` / `I_E_AUTO_ROTATE_OFF` 去取消用户手工开启的轮换
        （2026-09-08 Level C 实测：旧代码会把用户开着的轮换点关掉）。要脚本主动开轮换 +
        填充候补时，用户显式设 `auto_rotate=yes`。`page_exp_main` 的识别本就用
        `any_of(I_E_SETTINGS_BUTTON, I_E_AUTO_ROTATE_ON, I_E_AUTO_ROTATE_OFF)` 同时覆盖轮换
        开 / 关两种布局，不依赖脚本把轮换恢复成关闭态。
        """
        match self._config.exploration_config.auto_rotate:
            case AutoRotate.yes:
                if self.appear(self.I_E_AUTO_ROTATE_OFF):  # 轮换关闭/式神不够了则需要打开并添加式神
                    self.click(self.C_CLICK_SETTINGS, interval=2)
                    return True
            case AutoRotate.no:
                # observe only —— 不碰用户的轮换开关。
                pass
        return False

    def arrive_end(self) -> bool:
        """是否到达探索的最后方, 需要先调用截图(滑动超过6次直接判定已经到达底部)"""
        if self.device.click_record.count(self.S_SWIPE_BACKGROUND_RIGHT.name) >= 6:
            self.device.click_record_clear()
            return True
        return self._match_end.stable(self.device.image, refresh_after_stable=True, frame_id=self.device.image_frame_id)

    def get_fire_button(self) -> Optional[RuleImage | RuleGif]:
        """获取需要攻击的按钮"""
        if self.appear(self.I_BOSS_BATTLE_BUTTON):
            self.fire_monster_type = 'boss'
            return self.I_BOSS_BATTLE_BUTTON
        return self.search_up_fight()

    def collect_treasure_box(self) -> bool:
        """收集宝箱奖励"""
        if self.appear(self.I_E_REWARD_BOX_SMALL):  # 小宝箱
            logger.info('Treasure box small appear, get it.')
            self.ui_click(self.I_E_REWARD_BOX_SMALL, self.I_REWARD, interval=0.8)
            self.ui_click_until_disappear(self.I_REWARD, interval=0.8)
            return True
        if self.appear(self.I_E_REWARD_BOX_BIG):  # 大宝箱
            logger.info('Treasure box big appear, get it.')
            self.ui_click(self.I_E_REWARD_BOX_BIG, self.I_REWARD, interval=0.8)
            self.ui_click_until_disappear(self.I_REWARD, interval=0.8)
            return True
        return False

    def collect_paper_man_reward(self) -> bool:
        """收集小纸人奖励(普通怪阶段); Boss 胜利后由 begin_boss_exit 直退, 不经过这里"""
        if self.appear(self.I_BATTLE_REWARD) and self._config.exploration_config.collect_paper_reward:
            self.ui_get_reward(self.I_BATTLE_REWARD)
            self.wait_start_time = datetime.now()  # 队友等待时间重置
            return True
        return False

    def quit_exp_main(self):
        """退出探索主界面(要求当前必须处于探索主界面, 不保证任何后续结果)"""
        self.need_exit = True
        # 导航返回：NAVIGATION reaction
        clicked = self.appear_then_click(self.I_UI_BACK_YELLOW, interval=0.8, policy=InteractionPolicy.NAVIGATION)
        self.wait_start_time = datetime.now()  # 队友等待时间重置
        return clicked

    def collect_reward(self) -> bool:
        """处理掉落奖励(True表示进行了操作, False表示没有操作)"""
        return self.collect_treasure_box() or self.collect_paper_man_reward()

    def enter_team(self) -> bool:
        """进入战斗组队页面"""
        return self.create_room(self.I_EXP_CREATE_TEAM) and self.ensure_private() and self.create_ensure()

if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('绘卷oas2')
    device = Device(config)
    t = BaseExploration(config, device)
    t.screenshot()
    t.fill_shikigami()
