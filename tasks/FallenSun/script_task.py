# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import random
from time import sleep
from datetime import time, datetime, timedelta

from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import any_of, page_main, page_reward, page_shikigami_records, page_soul_zones
from tasks.FallenSun.assets import FallenSunAssets
from tasks.FallenSun.config import FallenSun, UserStatus
from module.logger import logger
from module.exception import TaskEnd
from module.click_pipeline import execute_single_click, list_click_target
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.interaction_policy import fire_reaction_range
from tasks.Component.fire_battle_entry import is_battle_result_residue, is_new_battle_entry

# 日轮之陨单人挑战 FIRE 的有限 attempt / 总超时 / 点击后确认等待。engineering baseline，非 Level C 标定：
# 对齐 OROCHI_FIRE_* / RR_FIRE_*（4 / 10 / 3）。
FALLEN_SUN_FIRE_MAX_TRIES = 4
FALLEN_SUN_FIRE_TIMEOUT = 10
FALLEN_SUN_FIRE_POST_CLICK_TIMEOUT = 3


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, SwitchSoul, FallenSunAssets):

    def _fallen_sun_battle_key(self) -> str:
        return f"fallen_sun_{self.config.fallen_sun.fallen_sun_config.layer}"

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        if reward_page is None:
            return
        reward_page.recognizer = any_of(self.I_GREED_GHOST, self.I_REWARD, self.I_REWARD_GOLD)

    def run(self) -> bool:
        # 御魂切换方式一
        if self.config.fallen_sun.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.fallen_sun.switch_soul.switch_group_team)

        # 御魂切换方式二
        if self.config.fallen_sun.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.fallen_sun.switch_soul.group_name,
                                         self.config.fallen_sun.switch_soul.team_name)

        limit_count = self.config.fallen_sun.fallen_sun_config.limit_count
        limit_time = self.config.fallen_sun.fallen_sun_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)

        self.goto_page(page_main)
        config: FallenSun = self.config.fallen_sun

        success = True
        match config.fallen_sun_config.user_status:
            case UserStatus.LEADER: success = self.run_leader()
            case UserStatus.MEMBER: success = self.run_member()
            case UserStatus.ALONE: self.run_alone()
            case UserStatus.WILD: self.run_wild()
            case _: logger.error('Unknown user status')

        # 下一次运行时间
        if success:
            self.set_next_run('FallenSun', finish=True, success=True)
        else:
            self.set_next_run('FallenSun', finish=False, success=False)

        raise TaskEnd

    def fallen_sun_enter(self) -> bool:
        logger.info('Enter fallen_sun')
        while True:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM):
                return True
            if self.appear_then_click(self.I_FALLEN_SUN, interval=1):
                continue

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            control_name = f'FALLEN_SUN_LAYER_{layer}'
            execute_single_click(self.device, list_click_target(self.L_LAYER_LIST, pos, control_name), control_name=control_name)
            return True

    def check_lock(self, lock: bool = True) -> bool:
        """
        检查是否锁定阵容, 要求在八岐大蛇界面
        :param lock:
        :return:
        """
        logger.info('Check lock: %s', lock)
        if lock:
            while 1:
                self.screenshot()
                if self.appear(self.I_FALLEN_SUN_LOCK):
                    return True
                if self.appear_then_click(self.I_FALLEN_SUN_UNLOCK, interval=1):
                    continue
        else:
            while 1:
                self.screenshot()
                if self.appear(self.I_FALLEN_SUN_UNLOCK):
                    return True
                if self.appear_then_click(self.I_FALLEN_SUN_LOCK, interval=1):
                    continue

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_soul_zones)
        self.fallen_sun_enter()
        layer = self.config.fallen_sun.fallen_sun_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)
        # 创建队伍
        logger.info('Create team')
        while 1:
            self.screenshot()
            if self.appear(self.I_CHECK_TEAM):
                break
            if self.appear_then_click(self.I_FORM_TEAM, interval=1):
                continue
        # 创建房间
        self.create_room()
        self.ensure_private()
        self.create_ensure()

        # 邀请队友
        success = True
        is_first = True
        # 这个时候我已经进入房间了哦
        while 1:
            self.screenshot()
            # 无论胜利与否, 都会出现是否邀请一次队友
            # 区别在于，失败的话不会出现那个勾选默认邀请的框
            if self.check_and_invite(self.config.fallen_sun.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('FallenSun count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('FallenSun time limit out')
                    break

            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                # 如果在探索界面或者是出现在组队界面， 那就是可能房间死了
                # 要结束任务
                sleep(0.5)
                if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                    sleep(0.5)
                    if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                        logger.warning('FallenSun task failed')
                        success = False
                        break
                continue

            # 点击挑战
            if not is_first:
                if self.run_invite(config=self.config.fallen_sun.invite_config, fire_reaction=self.config.fallen_sun.fire_reaction):
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this fallen_sun task')
                    success = False
                    break

            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self.config.fallen_sun.invite_config, is_first=True,
                                       fire_reaction=self.config.fallen_sun.fire_reaction):
                    logger.warning('Invite failed and exit this fallen_sun task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )

        # 当结束或者是失败退出循环的时候只有两个UI的可能，在房间或者是在组队界面
        # 如果在房间就退出
        if self.exit_room():
            pass
        # 如果在组队界面就退出
        if self.exit_team():
            pass

        self.goto_page(page_main)

        if not success:
            return False
        return True

    def run_member(self):
        logger.info('Start run member')
        # self.goto_page(page_soul_zones)
        # self.fallen_sun_enter()
        # self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)

        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                logger.info('FallenSun count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('FallenSun time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room():
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.config.fallen_sun.invite_config.wait_time):
                    self.run_general_battle(
                        config=self.config.fallen_sun.general_battle_config,
                        battle_key=self._fallen_sun_battle_key(),
                        exit_matcher=self.I_CHECK_TEAM,
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self.config.fallen_sun.general_battle_config,
                    battle_key=self._fallen_sun_battle_key(),
                    exit_matcher=self.I_CHECK_TEAM,
                )

        while 1:
            # 有一种情况是本来要退出的，但是队长邀请了进入的战斗的加载界面
            if self.appear(self.I_CHECK_MAIN) or self.appear(self.I_CHECK_EXPLORATION):
                break
            # 如果可能在房间就退出
            if self.exit_room():
                pass
            # 如果还在战斗中，就退出战斗
            if self.exit_battle():
                pass


        self.goto_page(page_main)
        return True

    def run_alone(self):
        logger.info('Start run alone')
        self.goto_page(page_soul_zones)
        self.fallen_sun_enter()
        layer = self.config.fallen_sun.fallen_sun_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.fallen_sun.general_battle_config.lock_team_enable)

        def is_in_fallen_sun(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_FALLEN_SUN_FIRE)

        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if not is_in_fallen_sun():
                continue

            if self.current_count >= self.limit_count:
                logger.info('FallenSun count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('FallenSun time limit out')
                break

            # 点击挑战：FIRE 状态机，正向确认进入准备 / 战斗页才交接 run_general_battle；
            # 未进入战斗 → 回外层循环顶重新 screenshot + 判定挑战页
            if self._fire_fallen_sun_alone():
                self.run_general_battle(
                    config=self.config.fallen_sun.general_battle_config,
                    battle_key=self._fallen_sun_battle_key(),
                    exit_matcher=self.I_FALLEN_SUN_FIRE,
                )

        # 回去
        self.goto_page(page_main)

    def _classify_fallen_sun_fire_state(self) -> str:
        """单人挑战前后的当前帧分类，只读。优先级：battle > abnormal > ready > unknown。

        `'battle'` = `is_new_battle_entry()`（准备 / 战斗页）；`'abnormal'` = 结果 / 奖励页残留；
        `'ready'` = 日轮之陨挑战按钮在；其余是加载 / 过渡帧。
        """
        if is_new_battle_entry(self):
            return 'battle'
        if is_battle_result_residue(self):
            return 'abnormal'
        if self.appear(self.I_FALLEN_SUN_FIRE):
            return 'ready'
        return 'unknown'

    def _wait_fallen_sun_fire_state(self, timeout: float = FALLEN_SUN_FIRE_POST_CLICK_TIMEOUT) -> str:
        """点击后 / 挑战未就绪时的有界轮询，期间不点任何坐标；出现决定性状态即返回，否则 `'timeout'`。"""
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            state = self._classify_fallen_sun_fire_state()
            if state != 'unknown':
                return state
        return 'timeout'

    def _fire_fallen_sun_alone(self) -> bool:
        """单人点日轮之陨挑战直到**正向确认进入准备 / 战斗页**（FIRE Contract，D001 补记 FIRE 分节）。

        每次 attempt：分类当前帧 → 独立采样 `fallen_sun.fire_reaction` → `sleep` → fresh screenshot →
        重新确认挑战按钮在 → 点一次 → 有界等点击后状态。挑战按钮消失不算成功；过渡帧只等不点；
        结果 / 奖励页残留直接返回失败。有限 `FALLEN_SUN_FIRE_MAX_TRIES` + `Timer(FALLEN_SUN_FIRE_TIMEOUT)`。

        :return: True 已进入准备 / 战斗页；False 异常 / 有限尝试 / 总超时用尽（调用方不交接 run_general_battle）
        """
        timeout_timer = Timer(FALLEN_SUN_FIRE_TIMEOUT).start()
        for attempt in range(1, FALLEN_SUN_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            state = self._classify_fallen_sun_fire_state()
            if state == 'unknown':
                state = self._wait_fallen_sun_fire_state()
                if state in ('timeout', 'ready'):
                    continue
            if state == 'battle':
                logger.info('FallenSun fire: entered battle')
                return True
            if state == 'abnormal':
                logger.warning('FallenSun fire: result / reward page residue, not a new battle')
                return False
            fire_delay = random_delay(*fire_reaction_range(self.config.fallen_sun.fire_reaction))
            logger.info(f'FallenSun fire: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            state = self._classify_fallen_sun_fire_state()
            if state == 'battle':
                return True
            if state == 'abnormal':
                logger.warning('FallenSun fire: result / reward page residue during reaction')
                return False
            if state != 'ready':
                logger.info('FallenSun fire: button gone during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_FALLEN_SUN_FIRE, interval=0)
            state = self._wait_fallen_sun_fire_state()
            if state == 'battle':
                logger.info('FallenSun fire: entered battle after click')
                return True
            if state == 'abnormal':
                logger.warning('FallenSun fire: result / reward page after click, not a new battle')
                return False
            # 'ready'（仍在挑战页）/ 'timeout'（一直过渡）→ 下一 attempt
        logger.warning('FallenSun fire: bounded retry / timeout without entering battle')
        return False

    def run_wild(self):
        logger.error('Wild mode is not implemented')
        pass


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
    # t.check_layer('日蚀')
