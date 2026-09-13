# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import time, datetime, timedelta
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig

from tasks.Component.GeneralBattle.general_battle import GeneralBattle, ExitMatcher, BattleContext, BattleAction
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.default_pages import page_reward
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.matcher import any_of
from tasks.GameUi.page import page_main, page_awake_zones, page_shikigami_records
from tasks.EvoZone.assets import EvoZoneAssets
from tasks.EvoZone.config import EvoZone, UserStatus, KirinType, Layer
from module.logger import logger
from module.exception import TaskEnd
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.reaction_profile import REACTION_FAST, REACTION_NORMAL, REACTION_DELIBERATE, REACTION_FIRE


# 觉醒单人挑战 FIRE 的有限 attempt / 总超时 / 点击后确认等待。engineering baseline，非 Level C 标定：
# 对齐 RealmRaid.fire()（RR_FIRE_MAX_TRIES=4 / RR_FIRE_TIMEOUT=10 / RR_FIRE_POST_CLICK_TIMEOUT=3）。
EVOZONE_FIRE_MAX_TRIES = 4
EVOZONE_FIRE_TIMEOUT = 10
EVOZONE_FIRE_POST_CLICK_TIMEOUT = 3


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, EvoZoneAssets, SwitchSoul):

    @property
    def active_evo_zone(self) -> EvoZone:
        return getattr(self, '_embedded_evo_zone', None) or self.config.evo_zone

    def _check_embedded_abort(self) -> None:
        callback = getattr(self, '_embedded_abort_check', None)
        if callback is not None:
            callback()

    def _return_to_main_after_run(self) -> None:
        if getattr(self, '_embedded_evo_zone', None) is None:
            self.goto_page(page_main)
            return
        # 多账号组队觉醒收尾只允许从探索页直接返回庭院，避免导航器绕行其他页面。
        self.ui_click(self.I_UI_BACK_YELLOW, self.I_CHECK_MAIN, interval=4)

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        if reward_page is None:
            return
        reward_page.recognizer = any_of(self.I_GI_SURE, reward_page.recognizer)

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        # 无论胜利与否, 都会出现是否邀请一次队友, 区别在于, 失败的话不会出现那个勾选默认邀请的框
        if self.active_evo_zone.evo_zone_config.user_status == UserStatus.LEADER and \
            self.check_and_invite(self.active_evo_zone.invite_config.default_invite):
            return BattleAction.CONTINUE
        return super()._handle_reward(context, config)

    def run(self) -> bool:
        success = self._run_core()
        if success:
            self.set_next_run('EvoZone', finish=True, success=True)
        else:
            self.set_next_run('EvoZone', finish=False, success=False)
        raise TaskEnd

    def run_embedded(
        self,
        *,
        user_status: UserStatus,
        limit_count: int,
        kirin_type: KirinType | None = None,
        layer: Layer | None = None,
        friend_list: list[str] | str = '',
        redact_sensitive_logs: bool = True,
        abort_check=None,
    ) -> bool:
        """Run EvoZone without changing its persisted config or scheduler."""
        if getattr(self, '_embedded_evo_zone', None) is not None:
            raise RuntimeError('Nested EvoZone embedded runs are not supported')
        embedded = self.config.evo_zone.model_copy(deep=True)
        embedded.evo_zone_config.user_status = user_status
        embedded.evo_zone_config.limit_count = limit_count
        if kirin_type is not None:
            embedded.evo_zone_config.kirin_type = kirin_type
        if layer is not None:
            embedded.evo_zone_config.layer = layer
        if isinstance(friend_list, list):
            friend_list = '\n'.join(friend_list)
        embedded.invite_config.friend_list = friend_list
        self._embedded_evo_zone = embedded
        self._redact_invite_friends = redact_sensitive_logs
        self._embedded_abort_check = abort_check
        try:
            success = self._run_core()
            return success and self.current_count >= limit_count
        finally:
            self._embedded_evo_zone = None
            self._redact_invite_friends = False
            self._embedded_abort_check = None

    def _run_core(self) -> bool:

        self._check_embedded_abort()
        self.start_time = datetime.now()
        limit_count = self.active_evo_zone.evo_zone_config.limit_count
        limit_time = self.active_evo_zone.evo_zone_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute,
                                               seconds=limit_time.second)
        con = self.active_evo_zone
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        self.goto_page(page_main)
        config: EvoZone = self.active_evo_zone
        if config.evo_zone_config.soul_buff_enable:
            self.open_buff()
            self.awake(is_open=True)
            self.close_buff()

        success = True
        match config.evo_zone_config.user_status:
            case UserStatus.LEADER:
                success = self.run_leader()
            case UserStatus.MEMBER:
                success = self.run_member()
            case UserStatus.ALONE:
                self.run_alone()
            case UserStatus.WILD:
                self.run_wild()
            case _:
                logger.error('Unknown user status')

        self._return_to_main_after_run()
        # 记得关掉
        if config.evo_zone_config.soul_buff_enable:
            self.open_buff()
            self.awake(is_open=False)
            self.close_buff()
        return success

    def evozone_enter(self) -> bool:
        logger.info('Enter evozone')
        kirintype = self.I_LIGHTNING_KIRIN
        match self.active_evo_zone.evo_zone_config.kirin_type:
            case KirinType.FIREKIRIN:
                kirintype = self.I_FIRE_KIRIN
            case KirinType.WINDKIRIN:
                kirintype = self.I_WIND_KIRIN
            case KirinType.WATERKIRIN:
                kirintype = self.I_WATER_KIRIN
            case KirinType.LIGHTNINGKIRIN:
                kirintype = self.I_LIGHTNING_KIRIN
        while True:
            self._check_embedded_abort()
            self.screenshot()
            if self.appear(self.I_FORM_TEAM):
                return True
            # 麒麟 / 材料类型选择：需要明显选择判断的稳定目标，DELIBERATE reaction
            if self.appear_then_click(kirintype, interval=1, confirm_delay=REACTION_DELIBERATE):
                continue
        return False

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            self.device.click(x=pos[0], y=pos[1])
            return True
        return False

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_awake_zones)
        self.evozone_enter()
        layer = self.active_evo_zone.evo_zone_config.layer
        logger.info("test0")
        self.check_layer(layer)
        logger.info("test1")
        # 同上：保留 synevo 的 `active_evo_zone` 配置源，吸收公共 reaction timing。
        self.check_lock(self.active_evo_zone.general_battle_config.lock_team_enable, self.I_EVOZONE_LOCK, self.I_EVOZONE_UNLOCK, confirm_delay=REACTION_FAST)
        logger.info("test2")
        # 创建队伍
        logger.info('Create team')
        while 1:
            self._check_embedded_abort()
            self.screenshot()
            if self.appear(self.I_CHECK_TEAM) or self.appear(self.I_CHECK_TEAM_2):
                break
            # 普通进入组队：稳定按钮，NORMAL reaction
            if self.appear_then_click(self.I_FORM_TEAM, interval=1, confirm_delay=REACTION_NORMAL):
                continue
        # 创建房间
        if not self.create_room():
            raise RuntimeError('Create room button did not appear')
        if not self.ensure_private():
            raise RuntimeError('Private room option did not appear')
        if not self.create_ensure():
            raise RuntimeError('Create room confirmation did not appear')
        # 邀请队友
        success = True
        is_first = True
        # 这个时候我已经进入房间了哦
        while 1:
            self._check_embedded_abort()
            self.screenshot()
            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('EvoZone count limit out')
                    break
            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('EvoZone time limit out')
                    break
            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                # 如果在探索界面或者是出现在组队界面， 那就是可能房间死了
                # 要结束任务
                sleep(0.5)
                if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                    sleep(0.5)
                    if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                        logger.warning('EvoZone task failed')
                        success = False
                        break
                continue
            # 点击挑战
            if not is_first:
                if self.run_invite(config=self.active_evo_zone.invite_config):
                    self.run_general_battle(
                        config=self.active_evo_zone.general_battle_config,
                        exit_matcher=any_of(self.I_CHECK_TEAM, self.I_CHECK_TEAM_2),
                    )
                else:
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this EvoZone task')
                    success = False
                    break
            # 第一次会邀请队友
            if is_first:
                if not self.run_invite(config=self.active_evo_zone.invite_config, is_first=True):
                    logger.warning('Invite failed and exit this evozone task')
                    success = False
                    break
                else:
                    is_first = False
                    self.run_general_battle(
                        config=self.active_evo_zone.general_battle_config,
                        exit_matcher=any_of(self.I_CHECK_TEAM, self.I_CHECK_TEAM_2),
                    )

        # 当结束或者是失败退出循环的时候只有两个UI的可能，在房间或者是在组队界面
        # 如果在房间就退出
        if self.exit_room():
            pass
        # 如果在组队界面就退出
        if self.exit_team():
            pass
        if not success:
            return False
        return True

    def run_member(self):
        logger.info('Start run member')
        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self._check_embedded_abort()
            self.screenshot()
            if self.current_count >= self.limit_count:
                logger.info('EvoZone count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('EvoZone time limit out')
                break
            if self.check_then_accept():
                continue
            if self.is_in_room(False):
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.active_evo_zone.invite_config.wait_time):
                    self.run_general_battle(
                        config=self.active_evo_zone.general_battle_config,
                        exit_matcher=any_of(self.I_CHECK_TEAM, self.I_CHECK_TEAM_2),
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self.active_evo_zone.general_battle_config,
                    exit_matcher=any_of(self.I_CHECK_TEAM, self.I_CHECK_TEAM_2),
                )

        while 1:
            # 有一种情况是本来要退出的，但是队长邀请了进入的战斗的加载界面
            self._check_embedded_abort()
            if self.appear(self.I_CHECK_MAIN) or self.appear(self.I_CHECK_EXPLORATION):
                break
            # 如果可能在房间就退出
            if self.exit_room():
                pass
            # 如果还在战斗中，就退出战斗
            if self.exit_battle():
                pass
        return True

    def _is_evozone_challenge_retryable(self) -> bool:
        """当前 fresh frame 是否**明确仍处于觉醒单人挑战可操作页面**（可再次点击挑战）。

        只读当前帧：不截图 / 不点击 / 不 sleep / 不改状态。觉醒单人挑战页除进攻按钮外没有
        其它稳定持久 marker，用 `I_EVOZONE_FIRE` 仍在场即可与 loading / 页面切换过渡帧区分。
        """
        return self.appear(self.I_EVOZONE_FIRE)

    def _wait_evozone_fire_state(self, timeout: float = EVOZONE_FIRE_POST_CLICK_TIMEOUT) -> str:
        """FIRE post-click / FIRE 未就绪时的有界状态轮询，区分三态、**不点任何坐标**：

        - `'battle'`：`is_in_battle()` —— 已进入 GeneralBattle 可接管的战斗流程（唯一 positive success）；
        - `'retryable'`：`_is_evozone_challenge_retryable()` —— 仍在觉醒挑战页 → 允许下一 bounded attempt；
        - `'timeout'`：整个 `timer` 内都是「挑战按钮消失、战斗未出现」的过渡 / 未知帧 ——
          **既不当 success 也不当 immediate failure**，timer 内持续等 `'battle'` / `'retryable'`。

        复用 `GeneralBattle.is_in_battle()` + 已有觉醒 marker，不新造 page detector。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            if self.is_in_battle(False):
                return 'battle'
            if self._is_evozone_challenge_retryable():
                return 'retryable'
        return 'timeout'

    def _fire_evozone_alone(self) -> bool:
        """觉醒单人：点击挑战按钮直到**正向确认进入战斗**。

        与 RealmRaid.fire() 同一 FIRE Contract（见 `docs/DECISIONS.md` D001 补记 FIRE 分节）：
        成功判据是 `is_in_battle()`，不以「`I_EVOZONE_FIRE` 消失」单独判成功；每次 attempt
        独立采样 `REACTION_FIRE` → `sleep` → fresh screenshot → 二次确认 `I_EVOZONE_FIRE` 仍在 →
        点击；post-click 走 `_wait_evozone_fire_state()` 的三态（battle / retryable / transition-unknown）。
        有限 `EVOZONE_FIRE_MAX_TRIES` + 有限 `Timer(EVOZONE_FIRE_TIMEOUT)`，用尽仍未进入战斗返回
        False，由调用方决定**不交接 `run_general_battle`**。

        :return: True 已进入战斗流程；False 有限重试 / 超时仍未进入
        """
        self.device.click_record_clear()
        timeout_timer = Timer(EVOZONE_FIRE_TIMEOUT).start()
        for attempt in range(1, EVOZONE_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            if self.is_in_battle(False):
                logger.info('EvoZone fire: entered battle')
                return True
            if not self.appear(self.I_EVOZONE_FIRE):
                # 挑战按钮未就绪：页面切换中 / loading / 弹窗遮挡 / 临时识别失败。
                # 有界等一个决定性状态，不在过渡帧里乱点。
                state = self._wait_evozone_fire_state()
                if state == 'battle':
                    logger.info('EvoZone fire: entered battle')
                    return True
                # 'retryable'（挑战页仍在，下一 attempt 顶端会点）/ 'timeout'（过渡 / 未知，不点）
                continue
            fire_delay = random_delay(*REACTION_FIRE)
            logger.info(f'EvoZone fire: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if not self.appear(self.I_EVOZONE_FIRE):
                logger.info('EvoZone fire: button gone during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_EVOZONE_FIRE, interval=0)
            state = self._wait_evozone_fire_state()
            if state == 'battle':
                logger.info('EvoZone fire: entered battle after click')
                return True
            # 'retryable' / 'timeout' → 下一 attempt（transition-unknown 不当 immediate failure）
        logger.warning('EvoZone fire: bounded retry / timeout without entering battle')
        return False

    def run_alone(self):
        logger.info('Start run alone')
        self.goto_page(page_awake_zones)
        self.evozone_enter()
        layer = self.active_evo_zone.evo_zone_config.layer
        self.check_layer(layer)
        # 配置源保持 synevo 的 `active_evo_zone`（多账号/多实例按当前账号选生效配置），
        # 只吸收公共 reaction timing（confirm_delay）与疲劳安全节点。
        self.check_lock(self.active_evo_zone.general_battle_config.lock_team_enable, self.I_EVOZONE_LOCK, self.I_EVOZONE_UNLOCK, confirm_delay=REACTION_FAST)
        # 觉醒单人是 host-controlled 连续循环：疲劳安全节点放在「一场战斗完整结束、run_general_battle
        # 已回到稳定挑战页」之后，休息结束回循环顶会先 screenshot + is_in_evozone 重新确认业务页面。
        self.begin_fatigue_task('EvoZone')
        deadline = self.start_time + self.limit_time

        def is_in_evozone(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_EVOZONE_FIRE)

        while 1:
            self.screenshot()
            if not is_in_evozone():
                continue
            if self.current_count >= self.limit_count:
                logger.info('EvoZone count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('EvoZone time limit out')
                break
            # 点击挑战：FIRE 三态状态机，正向确认进入战斗才交接 run_general_battle
            # （取代旧的「按钮消失即算开战」while 循环）；战斗配置仍取 synevo 的
            # `active_evo_zone`，保证多账号/多实例按当前账号选生效配置。
            if self._fire_evozone_alone():
                self.run_general_battle(
                    config=self.active_evo_zone.general_battle_config,
                    exit_matcher=self.I_EVOZONE_FIRE,
                )
                # 一场完整觉醒战斗结束、已回到稳定挑战页 → 疲劳安全节点
                self.try_fatigue_break(safe=True, repeat_completed=True, deadline=deadline)
            # 未进入战斗 → 回外层循环顶重新 screenshot + is_in_evozone 判定，不误交接 run_general_battle

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
