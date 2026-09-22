# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime, timedelta

from module.click_pipeline import execute_single_click, list_click_target
from module.exception import TaskEnd
from module.logger import logger
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.EternitySea.config import EternitySea

from tasks.GameUi.game_ui import GameUi
from tasks.Component.GeneralBattle.general_battle import (
    BattleAction,
    BattleContext,
    GeneralBattle,
)
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.EternitySea.assets import EternitySeaAssets
from tasks.GameUi.matcher import any_of
from tasks.Orochi.config import UserStatus
from module.exception import RequestHumanTakeover
from tasks.GameUi.page import page_main, page_reward, page_soul_zones, page_shikigami_records
from time import sleep
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.interaction_policy import fire_reaction_range
from tasks.Component.fire_battle_entry import is_battle_result_residue, is_new_battle_entry

# 永生之海单人挑战 FIRE 的有限 attempt / 总超时 / 点击后确认等待。engineering baseline，非 Level C 标定：
# 对齐 OROCHI_FIRE_* / RR_FIRE_*（4 / 10 / 3）。
ETERNITY_SEA_FIRE_MAX_TRIES = 4
ETERNITY_SEA_FIRE_TIMEOUT = 10
ETERNITY_SEA_FIRE_POST_CLICK_TIMEOUT = 3


class ScriptTask(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, SwitchSoul, EternitySeaAssets):
    """永生之海"""

    @property
    def task_name(self):
        return "EternitySea"

    @property
    def _task_config(self) -> EternitySea:
        return self.config.model.eternity_sea

    @property
    def _limit_time(self) -> timedelta:
        limit_time = self._task_config.eternity_sea_config.limit_time
        return timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        reward_page.recognizer = any_of(self.I_GI_SURE, reward_page.recognizer)

    def _handle_continuous_prepare(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if 0 < config.max_continuous <= context.continuous_count:
            return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
        self.device.click_record_clear()
        self._reset_round_context(context, config, continuous_count=context.continuous_count + 1)
        if getattr(self, "_member_stage_preset_switched", False) or context.continuous_count != 2 or \
                self._task_config.eternity_sea_config.user_status != UserStatus.MEMBER :
            return BattleAction.CONTINUE
        battle_config = self._task_config.general_battle_config
        logger.info("Switch member preset at continuous round 2")
        self.switch_preset_team(battle_config.preset_enable, battle_config.preset_group, battle_config.preset_team)
        self._member_stage_preset_switched = True
        return BattleAction.CONTINUE

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        # 无论胜利与否, 都会出现是否邀请一次队友, 区别在于, 失败的话不会出现那个勾选默认邀请的框
        if self._task_config.eternity_sea_config.user_status == UserStatus.LEADER and \
                self.check_and_invite(self._task_config.invite_config.default_invite):
            return BattleAction.CONTINUE
        return super()._handle_reward(context, config)

    def run(self) -> None:
        self._member_stage_preset_switched = False
        self._two_teams_switch_sous(self._task_config.switch_soul_config_1)
        self._two_teams_switch_sous(self._task_config.switch_soul_config_2)
        success = False
        match self._task_config.eternity_sea_config.user_status:
            case UserStatus.LEADER: success = self.run_leader()
            case UserStatus.MEMBER: success = self.run_member()
            case UserStatus.ALONE: success = self.run_alone()
            case _: logger.error('Unknown user status')
        self.goto_page(page_main)
        if success:
            self.set_next_run(self.task_name, finish=True, success=True)
        else:
            self.set_next_run(self.task_name, finish=False, success=False)
        raise TaskEnd(self.task_name)

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_soul_zones)
        self._enter_eternity_sea()
        layer = self._task_config.eternity_sea_config.layer
        self.check_layer(layer)
        self.check_lock(self._task_config.general_battle_config.lock_team_enable, self.I_NEWETERNITYSEA_LOCK,
                        self.I_ETERNITYSEA_UNLOCK)
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
            if self.current_count >= self._task_config.eternity_sea_config.limit_count:
                logger.info("EternitySea count limit out")
                break
            if datetime.now() - self.start_time >= self._limit_time:
                logger.info("EternitySea time limit out")
                break
            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                if self.is_room_dead():
                    logger.warning('eternity_sea task failed')
                    success = False
                    break
                continue
            # 点击挑战
            if not is_first:
                if self.run_invite(config=self._task_config.invite_config, fire_reaction=self._task_config.fire_reaction):
                    self.run_general_battle(
                        config=self._task_config.general_battle_config,
                        exit_matcher=self.I_GI_EMOJI_1,
                    )
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this eternity_sea task')
                    success = False
                    break
            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self._task_config.invite_config, is_first=True,
                                       fire_reaction=self._task_config.fire_reaction):
                    logger.warning('Invite failed and exit this eternity_sea task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(
                        config=self._task_config.general_battle_config,
                        exit_matcher=self.I_GI_EMOJI_1,
                    )
        self.exit_room()
        self.exit_team()
        return success

    def run_member(self):
        logger.info('Start run member')
        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()
            if self.current_count >= self._task_config.eternity_sea_config.limit_count:
                logger.info("EternitySea count limit out")
                break
            if datetime.now() - self.start_time >= self._limit_time:
                logger.info("EternitySea time limit out")
                break
            if self.check_then_accept():
                continue
            if self.is_in_room(False):
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self._task_config.invite_config.wait_time):
                    self.run_general_battle(
                        config=self._member_general_battle_config(),
                        exit_matcher=any_of(self.I_GI_EMOJI_1, self.I_CHECK_MAIN),
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self._member_general_battle_config(),
                    exit_matcher=any_of(self.I_GI_EMOJI_1, self.I_CHECK_MAIN),
                )
        self.exit_room()
        self.exit_team()
        return True

    def run_alone(self) -> bool:
        logger.info("Start run alone")
        self.goto_page(page_soul_zones)
        self._enter_eternity_sea()
        if self._task_config.general_battle_config.lock_team_enable == False:
            logger.critical(f"Only supports lock team mode")
            raise RequestHumanTakeover
        while 1:
            self.screenshot()
            if not self.appear(self.I_ETERNITY_SEA_FIRE):
                continue
            if self.current_count >= self._task_config.eternity_sea_config.limit_count:
                logger.info("EternitySea count limit out")
                break
            if datetime.now() - self.start_time >= self._limit_time:
                logger.info("EternitySea time limit out")
                break
            # 点击挑战：FIRE 状态机，正向确认进入准备 / 战斗页才交接 run_general_battle；
            # 未进入战斗 → 回外层循环顶重新 screenshot + 判定挑战页
            if self._fire_eternity_sea_alone():
                self.run_general_battle(
                    config=self._task_config.general_battle_config,
                    exit_matcher=self.I_ETERNITY_SEA_FIRE,
                )
        self.exit_room()
        return True

    def _classify_eternity_sea_fire_state(self) -> str:
        """单人挑战前后的当前帧分类，只读。优先级：battle > abnormal > ready > unknown。

        `'battle'` = `is_new_battle_entry()`（准备 / 战斗页）；`'abnormal'` = 结果 / 奖励页残留；
        `'ready'` = 永生之海挑战按钮在；其余是加载 / 过渡帧。
        """
        if is_new_battle_entry(self):
            return 'battle'
        if is_battle_result_residue(self):
            return 'abnormal'
        if self.appear(self.I_ETERNITY_SEA_FIRE):
            return 'ready'
        return 'unknown'

    def _wait_eternity_sea_fire_state(self, timeout: float = ETERNITY_SEA_FIRE_POST_CLICK_TIMEOUT) -> str:
        """点击后 / 挑战未就绪时的有界轮询，期间不点任何坐标；出现决定性状态即返回，否则 `'timeout'`。"""
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            state = self._classify_eternity_sea_fire_state()
            if state != 'unknown':
                return state
        return 'timeout'

    def _fire_eternity_sea_alone(self) -> bool:
        """单人点永生之海挑战直到**正向确认进入准备 / 战斗页**（FIRE Contract，D001 补记 FIRE 分节）。

        每次 attempt：分类当前帧 → 独立采样 `eternity_sea.fire_reaction` → `sleep` → fresh screenshot →
        重新确认挑战按钮在 → 点一次 → 有界等点击后状态。挑战按钮消失不算成功；过渡帧只等不点；
        结果 / 奖励页残留直接返回失败。有限 `ETERNITY_SEA_FIRE_MAX_TRIES` + `Timer(ETERNITY_SEA_FIRE_TIMEOUT)`。

        :return: True 已进入准备 / 战斗页；False 异常 / 有限尝试 / 总超时用尽（调用方不交接 run_general_battle）
        """
        timeout_timer = Timer(ETERNITY_SEA_FIRE_TIMEOUT).start()
        for attempt in range(1, ETERNITY_SEA_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            state = self._classify_eternity_sea_fire_state()
            if state == 'unknown':
                state = self._wait_eternity_sea_fire_state()
                if state in ('timeout', 'ready'):
                    continue
            if state == 'battle':
                logger.info('EternitySea fire: entered battle')
                return True
            if state == 'abnormal':
                logger.warning('EternitySea fire: result / reward page residue, not a new battle')
                return False
            fire_delay = random_delay(*fire_reaction_range(self._task_config.fire_reaction))
            logger.info(f'EternitySea fire: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            state = self._classify_eternity_sea_fire_state()
            if state == 'battle':
                return True
            if state == 'abnormal':
                logger.warning('EternitySea fire: result / reward page residue during reaction')
                return False
            if state != 'ready':
                logger.info('EternitySea fire: button gone during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_ETERNITY_SEA_FIRE, interval=0)
            state = self._wait_eternity_sea_fire_state()
            if state == 'battle':
                logger.info('EternitySea fire: entered battle after click')
                return True
            if state == 'abnormal':
                logger.warning('EternitySea fire: result / reward page after click, not a new battle')
                return False
            # 'ready'（仍在挑战页）/ 'timeout'（一直过渡）→ 下一 attempt
        logger.warning('EternitySea fire: bounded retry / timeout without entering battle')
        return False

    def is_room_dead(self) -> bool:
        # 如果在探索界面或者是出现在组队界面，那就是可能房间死了
        sleep(0.5)
        if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
            sleep(0.5)
            if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                return True
        return False

    def _enter_eternity_sea(self) -> bool:
        logger.info("Enter eternity_sea")
        while True:
            self.screenshot()
            if self.appear(self.I_FORM_TEAM, interval=1):
                return True
            if self.appear_then_click(self.I_ETERNITY_SEA, interval=1):
                continue
            #有可能点击到录像
            if self.appear_then_click(self.I_UI_BACK_RED, interval=1):
                continue
        return False

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            control_name = f'ETERNITY_SEA_LAYER_{layer}'
            execute_single_click(self.device, list_click_target(self.L_LAYER_LIST, pos, control_name), control_name=control_name)
            return True
        return False

    def _two_teams_switch_sous(self, config):
        if config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(config.switch_group_team)

        if config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(config.group_name, config.team_name)

    def _member_general_battle_config(self) -> GeneralBattleConfig:
        return self._task_config.general_battle_config.model_copy(update={"preset_enable": False})

if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    c = Config("oas1")
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()
