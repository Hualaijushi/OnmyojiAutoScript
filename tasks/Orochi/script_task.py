# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import random
from time import sleep, monotonic
from datetime import time, datetime, timedelta
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig

from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle, ExitMatcher, BattleContext
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralBuff.general_buff import GeneralBuff
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import any_of, page_main, page_reward, page_shikigami_records, page_soul_zones
from tasks.Orochi.assets import OrochiAssets
from tasks.Orochi.config import Orochi, UserStatus, Layer
from tasks.TrueOrochi.assets import TrueOrochiAssets
from module.logger import logger
from module.click_pipeline import execute_single_click, list_click_target
from module.exception import TaskEnd
from module.instance_sync.team import get_session
from module.script.loop_controller import get_step_controller
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.interaction_policy import InteractionPolicy, fire_reaction_range
from tasks.Orochi.page import page_orochi


# 御魂单人挑战 FIRE 的有限 attempt / 总超时 / 点击后确认等待。engineering baseline，非 Level C 标定：
# 对齐 RealmRaid.fire()（RR_FIRE_MAX_TRIES=4 / RR_FIRE_TIMEOUT=10 / RR_FIRE_POST_CLICK_TIMEOUT=3）。
OROCHI_FIRE_MAX_TRIES = 4
OROCHI_FIRE_TIMEOUT = 10
OROCHI_FIRE_POST_CLICK_TIMEOUT = 3
# 队员读队长进度的间隔（秒）：主循环每帧都会走到，不能每帧读文件
OROCHI_TEAM_POLL_INTERVAL = 2.0


class ScriptTask(GeneralBattle, GeneralInvite, GeneralBuff, GeneralRoom, GameUi, SwitchSoul, OrochiAssets, TrueOrochiAssets):
    # 组队同步会合后的这一次组队；没有（没开 / 单人 / 出错）时全部走原来的逻辑
    team_session = None
    _leader_checked_at = 0.0
    _leader_progress = None
    # 御魂 → 个人突破 循环的控制器；只有本次运行正是循环的御魂步骤时才有，普通运行为 None，走原来的逻辑
    loop = None
    # 本次开战尝试的证据（循环的可信计数用）：先看到准备 / 战斗页确认是新战斗，之后看到结算 / 奖励页才算一场；
    # 只见到结算页是上一场残留的，不能证明有新战斗
    _battle_seen = False
    _result_seen = False

    def _may_fire(self) -> bool:
        # 外层检查之后 run_invite 可能等很久，真正点「挑战」之前再确认一次循环还有效；普通运行不受影响
        return self.loop is None or self.loop.check(force=True)

    def _handle_prepare(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        self._battle_seen = True
        return super()._handle_prepare(context, config)

    def _handle_in_battle(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        self._battle_seen = True
        return super()._handle_in_battle(context, config)

    def _team_report(self, done: bool = False) -> None:
        if self.team_session is not None:
            self.team_session.report(self.current_count, done)

    def _member_count_reached(self) -> bool:
        """队员是否因为次数退出。有组队会话时以队长为准：队长打完（或离开）才走，次数对齐到队长的。

        两边各数各的会差一次（队长点了挑战却没真正开战也会 +1），队长先走队员空等邀请，队员先走队长邀请失败。
        """
        if self.loop is not None:
            # 循环里队员以队长上报的「这一批是否完成」为准，不用自己数的次数
            state = self.loop.member_batch_state()
            if state == 'running':
                return False
            logger.info(f'Loop: leader batch {state}')
            return True
        session = self.team_session
        if session is None:
            if self.current_count >= self.limit_count:
                logger.info('Orochi count limit out')
                return True
            return False
        now = monotonic()
        if self._leader_progress is None or now - self._leader_checked_at >= OROCHI_TEAM_POLL_INTERVAL:
            self._leader_checked_at = now
            self._leader_progress = session.peer_progress()
        progress = self._leader_progress
        if not progress.finished:
            return False
        if progress.count is not None:
            logger.info(f'Team sync: leader finished Orochi at {progress.count}, member counted {self.current_count}')
            self.current_count = progress.count
        else:
            logger.info(f'Team sync: leader left Orochi, member counted {self.current_count}')
        return True

    def _orochi_battle_key(self) -> str:
        return f"orochi_{self.config.orochi.orochi_config.layer}"

    def _register_custom_pages(self) -> None:
        reward_page = self.navigator.resolve_page(page_reward)
        if reward_page is None:
            return
        reward_page.recognizer = any_of(self.I_GI_SURE, self.I_GREED_GHOST, self.I_PET_PRESENT,
                                        reward_page.recognizer)

    def _exit_matcher(self) -> ExitMatcher | None:
        return any_of(self.I_GI_EMOJI_1, self.I_GI_EMOJI_2, self.I_CHECK_EXPLORATION)

    def _close_orochi_soul_choice_popup(self) -> bool:
        """关闭八岐大蛇战斗结束后偶发出现的御魂自选活动界面。"""
        if not self.appear_then_click(self.I_GB_CLOSE_RED, interval=0.8):
            return False
        logger.info('Close Orochi soul-choice event popup after battle')
        return True

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        self._result_seen = self._result_seen or self._battle_seen
        if self._close_orochi_soul_choice_popup():
            context.reward_no_battle_ts = None
            return BattleAction.CONTINUE
        return super()._handle_result(context, config)

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        self._result_seen = self._result_seen or self._battle_seen
        if self._close_orochi_soul_choice_popup():
            context.reward_no_battle_ts = None
            return BattleAction.CONTINUE
        # 无论胜利与否, 都会出现是否邀请一次队友, 区别在于, 失败的话不会出现那个勾选默认邀请的框
        if self.config.orochi.orochi_config.user_status == UserStatus.LEADER and \
            self.check_and_invite(self.config.orochi.invite_config.default_invite):
            return BattleAction.CONTINUE
        return super()._handle_reward(context, config)

    def _handle_missing_battle_page(
        self,
        context: BattleContext,
        config: GeneralBattleConfig,
        exit_matcher: ExitMatcher | None,
    ) -> BattleAction:
        # 活动弹窗可能在结算页、奖励页或两者之间直接出现；覆盖页面后
        # 通用识别通常会落入 unknown，因此必须在战后退出判断前关闭。
        if self._close_orochi_soul_choice_popup():
            context.reward_no_battle_ts = None
            return BattleAction.CONTINUE
        return super()._handle_missing_battle_page(
            context,
            config,
            exit_matcher,
        )

    def run(self) -> bool:
        self.switch_orochi_souls()

        limit_count = self.config.orochi.orochi_config.limit_count
        limit_time = self.config.orochi.orochi_config.limit_time
        self.current_count = 0
        self.limit_count: int = limit_count
        self.team_session = get_session(getattr(self.config, 'config_name', ''), 'Orochi')
        self._leader_progress = None
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute, seconds=limit_time.second)
        self.loop = get_step_controller(getattr(self.config, 'config_name', ''), 'Orochi')
        if self.loop is not None:
            # 循环的目标场数替代普通的次数和时长限制
            self.limit_count = 1 << 30
            self.limit_time = timedelta(days=3650)
            status = self.config.orochi.orochi_config.user_status
            if status not in (UserStatus.LEADER, UserStatus.MEMBER) or status.value != self.loop.snapshot()['role']:
                logger.error('Orochi user status changed during the loop, stop it')
                self.loop.fail('role_changed')
                raise TaskEnd

        config: Orochi = self.config.orochi
        if not self.is_in_battle(True):
            self.goto_page(page_main)
            if config.orochi_config.soul_buff_enable:
                self.open_buff()
                self.soul(is_open=True)
                self.close_buff()

        success = True
        match config.orochi_config.user_status:
            case UserStatus.LEADER: success = self.run_leader()
            case UserStatus.MEMBER: success = self.run_member()
            case UserStatus.ALONE: self.run_alone()
            case UserStatus.WILD: success = self.run_wild()
            case _: logger.error('Unknown user status')

        # 御魂结束后检测是否出现真蛇
        if config.orochi_config.check_true_orochi_enable:
            self.goto_page(page_orochi)
            self.screenshot()
            if self.appear(self.I_FIND_TS):
                logger.info('Find true orochi after orochi battle, set TrueOrochi task to run now')
                self.set_next_run(task='TrueOrochi', success=False, finish=False, server=False, target=datetime.now())
        self.goto_page(page_main)
        # 记得关掉
        if config.orochi_config.soul_buff_enable:
            self.open_buff()
            self.soul(is_open=False)
            self.close_buff()
        # 下一次运行时间
        if success:
            self.set_next_run('Orochi', finish=True, success=True)
        else:
            self.set_next_run('Orochi', finish=False, success=False)

        raise TaskEnd

    def switch_orochi_souls(self):
        # 御魂切换方式一
        if self.config.orochi.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.orochi.switch_soul.switch_group_team)

        # 御魂切换方式二
        if self.config.orochi.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.orochi.switch_soul.group_name,
                                         self.config.orochi.switch_soul.team_name)
        # 根据选层切换御魂
        self.orochi_switch_soul()

    def check_layer(self, layer: str) -> bool:
        """
        检查挑战的层数, 并选中挑战的层
        :return:
        """
        pos = self.list_find(self.L_LAYER_LIST, layer)
        if pos:
            control_name = f'LAYER_{layer}'
            execute_single_click(self.device, list_click_target(self.L_LAYER_LIST, pos, control_name), control_name=control_name)
            return True
        return False

    def run_leader(self):
        logger.info('Start run leader')
        self.goto_page(page_orochi)
        layer = self.config.orochi.orochi_config.layer
        self.check_layer(layer)
        # https://github.com/runhey/OnmyojiAutoScript/issues/592
        self.config.orochi.general_battle_config.lock_team_enable = True
        self.check_lock(self.config.orochi.general_battle_config.lock_team_enable, self.I_OROCHI_LOCK, self.I_OROCHI_UNLOCK, policy=InteractionPolicy.FAST)
        # 创建队伍
        logger.info('Create team')
        while 1:
            self.screenshot()
            if self.appear(self.I_CHECK_TEAM):
                break
            # 普通进入组队：稳定按钮，NORMAL reaction
            if self.appear_then_click(self.I_FORM_TEAM, interval=1, policy=InteractionPolicy.NORMAL):
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
            if self.loop is not None:
                if not self.loop.check():
                    logger.info('Loop stopped, no more battles')
                    success = False
                    break
                if self.loop.remaining() <= 0 and self.is_in_room():
                    logger.info('Loop batch target reached')
                    break
            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('Orochi count limit out')
                    break
            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('Orochi time limit out')
                    break
            # 如果没有进入房间那就不需要后面的邀请
            if not self.is_in_room():
                if self.is_room_dead():
                    logger.warning('Orochi task failed')
                    success = False
                    break
                continue
            # 点击挑战
            if not is_first:
                if not self._leader_fight_once(is_first=False):
                    # 邀请失败，退出任务
                    logger.warning('Invite failed and exit this orochi task')
                    success = False
                    break
            # 第一次会邀请队友
            if is_first:
                if not self._leader_fight_once(is_first=True):
                    logger.warning('Invite failed and exit this orochi task')
                    success = False
                    break
                else:
                    is_first = False

        # 队长说了算：先告诉队员打完了（次数、时间、邀请失败三种退出都经过这里），队员不用空等邀请超时
        self._team_report(done=True)
        if self.loop is not None:
            # 这一批是否完成由循环的可信计数决定，不用 current_count
            self.loop.report_batch(ok_if_reached=success)
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

    def _battle_config(self) -> GeneralBattleConfig:
        """循环里关掉内部连战，保证每一场都能单独确认；只改本次调用用的拷贝，不动用户配置。"""
        config = self.config.orochi.general_battle_config
        if self.loop is not None and config.continuous_battle:
            return config.model_copy(update={'continuous_battle': False})
        return config

    def _leader_fight_once(self, is_first: bool) -> bool:
        """队长邀请并打一场。返回 False 表示邀请失败。

        循环模式下的可信计数：邀请前先记下「可能开战」；邀请没进战斗且没点过挑战按钮则撤销；
        进入战斗并且看到结算页才记一场，其余情况无法确认，由控制器停止循环。
        """
        if self.loop is not None:
            self.loop.attempt_begin()
            self.fire_click_issued = False
            self._battle_seen = False
            self._result_seen = False
        invited = self.run_invite(config=self.config.orochi.invite_config, is_first=is_first,
                                  fire_reaction=self.config.orochi.fire_reaction)
        if not invited:
            if self.loop is not None:
                self.loop.attempt_cancelled(self.fire_click_issued)
            return False
        self.run_general_battle(
            config=self._battle_config(),
            battle_key=self._orochi_battle_key()
        )
        self._team_report()
        if self.loop is not None:
            self.loop.attempt_resolved(fire_clicked=self.fire_click_issued, battle_seen=self._battle_seen,
                                       result_seen=self._result_seen)
        return True

    def run_member(self):
        logger.info('Start run member')
        # 进入战斗流程
        self.device.stuck_record_add('BATTLE_STATUS_S')
        while 1:
            self.screenshot()

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue
            if self._member_count_reached():
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('Orochi time limit out')
                break

            if self.check_then_accept():
                continue

            if self.is_in_room(False):
                self.device.stuck_record_clear()
                if self.wait_battle(wait_time=self.config.orochi.invite_config.wait_time):
                    self.run_general_battle(
                        config=self._battle_config(),
                        battle_key=self._orochi_battle_key()
                    )
                else:
                    break
            # 队长秒开的时候，检测是否进入到战斗中
            if self.is_in_battle(False):
                self.run_general_battle(
                    config=self._battle_config(),
                    battle_key=self._orochi_battle_key()
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

        return True

    def _is_orochi_challenge_retryable(self) -> bool:
        """当前 fresh frame 是否**明确仍处于御魂单人挑战可操作页面**（可再次点击挑战）。

        只读当前帧：不截图 / 不点击 / 不 sleep / 不改状态。御魂单人挑战页除进攻按钮外没有
        其它稳定持久 marker，用 `I_OROCHI_FIRE` 仍在场即可与 loading / 页面切换过渡帧区分。
        """
        return self.appear(self.I_OROCHI_FIRE)

    def _wait_orochi_fire_state(self, timeout: float = OROCHI_FIRE_POST_CLICK_TIMEOUT) -> str:
        """FIRE post-click / FIRE 未就绪时的有界状态轮询，区分三态、**不点任何坐标**：

        - `'battle'`：`is_in_battle()` —— 已进入 GeneralBattle 可接管的战斗流程（唯一 positive success）；
        - `'retryable'`：`_is_orochi_challenge_retryable()` —— 仍在御魂挑战页 → 允许下一 bounded attempt；
        - `'timeout'`：整个 `timer` 内都是「挑战按钮消失、战斗未出现」的过渡 / 未知帧 ——
          **既不当 success 也不当 immediate failure**，timer 内持续等 `'battle'` / `'retryable'`。

        复用 `GeneralBattle.is_in_battle()` + 已有御魂 marker，不新造 page detector。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            if self.is_in_battle(False):
                return 'battle'
            if self._is_orochi_challenge_retryable():
                return 'retryable'
        return 'timeout'

    def _fire_orochi_alone(self) -> bool:
        """御魂单人：点击挑战按钮直到**正向确认进入战斗**。

        与 RealmRaid.fire() 同一 FIRE Contract（见 `docs/DECISIONS.md` D001 补记 FIRE 分节）：
        成功判据是 `is_in_battle()`，不以「`I_OROCHI_FIRE` 消失」单独判成功；每次 attempt
        独立采样任务 FIRE reaction（`fire_reaction_range`，默认 400~800ms） → `sleep` → fresh screenshot → 二次确认 `I_OROCHI_FIRE` 仍在 →
        点击；post-click 走 `_wait_orochi_fire_state()` 的三态（battle / retryable / transition-unknown）。
        有限 `OROCHI_FIRE_MAX_TRIES` + 有限 `Timer(OROCHI_FIRE_TIMEOUT)`，用尽仍未进入战斗返回
        False，由调用方决定**不交接 `run_general_battle`**。

        :return: True 已进入战斗流程；False 有限重试 / 超时仍未进入
        """
        self.device.click_record_clear()
        timeout_timer = Timer(OROCHI_FIRE_TIMEOUT).start()
        for attempt in range(1, OROCHI_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            if self.is_in_battle(False):
                logger.info('Orochi fire: entered battle')
                return True
            if not self.appear(self.I_OROCHI_FIRE):
                # 挑战按钮未就绪：页面切换中 / loading / 弹窗遮挡 / 临时识别失败。
                # 有界等一个决定性状态，不在过渡帧里乱点。
                state = self._wait_orochi_fire_state()
                if state == 'battle':
                    logger.info('Orochi fire: entered battle')
                    return True
                # 'retryable'（挑战页仍在，下一 attempt 顶端会点）/ 'timeout'（过渡 / 未知，不点）
                continue
            fire_delay = random_delay(*fire_reaction_range(self.config.orochi.fire_reaction))
            logger.info(f'Orochi fire: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if not self.appear(self.I_OROCHI_FIRE):
                logger.info('Orochi fire: button gone during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_OROCHI_FIRE, interval=0)
            state = self._wait_orochi_fire_state()
            if state == 'battle':
                logger.info('Orochi fire: entered battle after click')
                return True
            # 'retryable' / 'timeout' → 下一 attempt（transition-unknown 不当 immediate failure）
        logger.warning('Orochi fire: bounded retry / timeout without entering battle')
        return False

    def run_alone(self):
        logger.info('Start run alone')
        self.goto_page(page_orochi)
        layer = self.config.orochi.orochi_config.layer
        self.check_layer(layer)
        self.check_lock(self.config.orochi.general_battle_config.lock_team_enable, self.I_OROCHI_LOCK, self.I_OROCHI_UNLOCK, policy=InteractionPolicy.FAST)
        # 御魂单人是 host-controlled 连续循环：疲劳安全节点放在「一场战斗完整结束、run_general_battle
        # 已回到稳定挑战页」之后，休息结束回循环顶会先 screenshot + is_in_orochi 重新确认业务页面。
        self.begin_fatigue_task('Orochi')
        deadline = self.start_time + self.limit_time

        def is_in_orochi(screenshot=False) -> bool:
            if screenshot:
                self.screenshot()
            return self.appear(self.I_OROCHI_FIRE)

        while 1:
            self.screenshot()
            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue
            if not is_in_orochi():
                continue
            if self.current_count >= self.limit_count:
                logger.info('Orochi count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('Orochi time limit out')
                break
            # 点击挑战：FIRE 三态状态机，正向确认进入战斗才交接 run_general_battle
            if self._fire_orochi_alone():
                self.run_general_battle(
                    config=self.config.orochi.general_battle_config,
                    battle_key=self._orochi_battle_key(),
                    exit_matcher=self.I_OROCHI_FIRE)
                # 一场完整御魂战斗结束、已回到稳定挑战页 → 疲劳安全节点
                self.try_fatigue_break(safe=True, repeat_completed=True, deadline=deadline)
            # 未进入战斗 → 回外层循环顶重新 screenshot + is_in_orochi 判定，不误交接 run_general_battle

    def run_wild(self):
        logger.info('Start run wild')

        # 已经在战斗中不必初始化，保证已经组队开始战斗的情况下可以自动执行后续任务
        if not self.is_in_battle(True):
            self.goto_page(page_orochi)
            layer = self.config.orochi.orochi_config.layer
            self.check_layer(layer)
            self.check_lock(self.config.orochi.general_battle_config.lock_team_enable, self.I_OROCHI_LOCK, self.I_OROCHI_UNLOCK, policy=InteractionPolicy.FAST)
            # 创建队伍
            logger.info('Create team')
            while 1:
                self.screenshot()
                if self.appear(self.I_CHECK_TEAM):
                    break
                # 普通进入组队：稳定按钮，NORMAL reaction
                if self.appear_then_click(self.I_FORM_TEAM, interval=1, policy=InteractionPolicy.NORMAL):
                    continue
            # 创建房间
            self.create_room()
            self.ensure_public()
            self.create_ensure()

        success = True
        while 1:
            self.screenshot()
            # 无论胜利与否, 都会出现是否邀请一次队友
            # 区别在于，失败的话不会出现那个勾选默认邀请的框
            if self.check_and_invite(self.config.orochi.invite_config.default_invite):
                continue

            # 检查猫咪奖励
            if self.appear_then_click(self.I_PET_PRESENT, action=self.C_RANDOM_RIGHT, interval=1):
                continue

            if self.current_count >= self.limit_count:
                if self.is_in_room():
                    logger.info('Orochi count limit out')
                    break

            if datetime.now() - self.start_time >= self.limit_time:
                if self.is_in_room():
                    logger.info('Orochi time limit out')
                    break

            if not self.is_in_room():
                if self.is_room_dead():
                    logger.warning('Orochi task failed')
                    success = False
                    break
                continue

            # 点击挑战
            logger.info('Wait for starting')
            while 1:
                self.screenshot()
                # 在进入战斗前必然会出现挑战界面，因此点击失败必须重复点击，防止卡在挑战界面，
                # 点击成功后如果网络卡顿，导致没有进入战斗，则无法进入 run_general_battle 流程，
                # 所以如果判断是在战斗中，则执行通用战斗流程
                if not self.is_in_battle(False):
                    if not self.is_in_room() and self.is_room_dead():
                        break
                    if not self.appear_then_click(self.I_OROCHI_WILD_FIRE, interval=1, threshold=0.8):
                        continue

                self.screenshot()
                if not self.appear(self.I_OROCHI_WILD_FIRE, threshold=0.8):
                    self.run_general_battle(
                        config=self.config.orochi.general_battle_config,
                        battle_key=self._orochi_battle_key(),
                        exit_matcher=any_of(self.I_OROCHI_WILD_FIRE, self.I_CHECK_TEAM),
                    )
                    break

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

    def is_room_dead(self) -> bool:
        # 如果在探索界面或者是出现在组队界面，那就是可能房间死了
        sleep(0.5)
        if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
            sleep(0.5)
            if self.appear(self.I_MATCHING) or self.appear(self.I_CHECK_EXPLORATION):
                return True
        return False

    def orochi_switch_soul(self) -> None:
        # 判断是否开启根据选层切换御魂
        orochi_switch_soul = self.config.orochi.switch_soul
        if not orochi_switch_soul.auto_switch_soul:
            return
        group_team: str = ''
        layer = self.config.orochi.orochi_config.layer
        match layer:
            case Layer.TEN:
                group_team = orochi_switch_soul.ten_switch
            case Layer.ELEVEN:
                group_team = orochi_switch_soul.eleven_switch
            case Layer.TWELVE:
                group_team = orochi_switch_soul.twelve_switch
            case Layer.THIRTEEN:
                group_team = orochi_switch_soul.thirteen_switch
        self.goto_page(page_shikigami_records)
        self.run_switch_soul(group_team)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('日常2')
    d = Device(c)
    t = ScriptTask(c, d)

    t._open_invite_panel_if_needed(True)
