"""当期爬塔独有页面与执行逻辑。"""

import time

from module.atom.click import RuleClick
from module.base.timer import Timer
from module.base.utils.random import random_delay, random_int
from module.click_pipeline import FinalPoint, execute_single_click
from module.exception import GamePageUnknownError
from module.logger import logger
from module.interaction_policy import fire_reaction_range
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.ActivityShikigami.base_act import ActivityResourceNotEnough
from tasks.ActivityShikigami.config import CLIMB_TYPES
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction, BattleContext
from tasks.GameUi.page import Page, page_battle_result, page_reward
import tasks.ActivityShikigami.page as pages


# 活动挑战 FIRE 事务参数（PROVISIONAL / engineering baseline，对齐 GeneralInvite `GI_FIRE_*` /
# RealmRaid `RR_FIRE_*` 的量级，未经 Level C 标定；改值连带更新 D001 补记 / AI_CONTEXT）：
# 有限 attempt + 墙钟 timeout + post-click 三态轮询上限，保证 fire 键一直不出现 / 页面一直
# unknown / transition 卡住都能有限退出。
ACTIVITY_FIRE_MAX_TRIES = 4
ACTIVITY_FIRE_TIMEOUT = 12
ACTIVITY_FIRE_POST_CLICK_TIMEOUT = 4
# 战斗结束后 drain 本期「活动专用结算弹窗」并正向确认回到稳定挑战页的上限（PROVISIONAL）。
ACTIVITY_SETTLEMENT_MAX_CLICKS = 6
ACTIVITY_SETTLEMENT_TIMEOUT = 15
# `_run_climb_type` 主循环连续识别不到任何已知页面（`get_current_page()` 持续为 None）的
# 墙钟上限（PROVISIONAL）。2026-09-22 真机事故：此前该分支只有 `sleep(0.5); continue`，
# 没有任何上限——一旦页面持续无法归类（例如被 `_drain_activity_settlement` 的兜底误点干扰），
# 会静默空转到任务墙钟耗尽都不会产生一行日志。超时后 `raise GamePageUnknownError`，交给外层
# 既有的页面异常处理，不在本层自行猜测恢复动作。
ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT = 20
# 普通爬塔专用结算单击的「点击前反应」区间（秒，PROVISIONAL，未经 Level C 标定）。
# 本线自己持有这个 reaction owner，不再借用 GeneralBattle 的
# `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`——后者语义是 Micro-Burst **同一 burst 内两击之间的
# 观察间隔**（0.10~0.30s），既不是「点击前反应」，也属于通用 Settlement V3 的 timing，本线
# 已经退出 Micro-Burst（见 `docs/DECISIONS.md` D025 补记），继续复用只会把两种语义混在一起、
# 且任何一方调参都会误伤另一方。区间量级对齐 `module/reaction_profile.py` 的 `REACTION_NORMAL`
# （普通确认类动作），但**不走** `InteractionPolicy` / `appear_then_click(policy=)`——本事务的
# timing 由本状态机自己拥有（`InteractionPolicy.SPECIAL` 语义），只允许这一层 reaction。
ACTIVITY_SETTLEMENT_REACTION = (0.45, 0.85)


class NormalClimbAct:
    """体力、门票、首领和百体四种爬塔战斗。"""

    def setup_climb_pages(self):
        # 本期普通爬塔是「二层入口」：page_act --I_TO_BATTLE_MAIN--> page_climb_main
        # --I_TO_BATTLE_MAIN_2--> page_climb_ap / page_climb_pass。旧的 page_act 直连 climb 页
        # 已不成立（用户真机确认）。中间页 positive marker 与两条边动作见 `pages.page_climb_main`。
        page_act = self.navigator.resolve_page(pages.page_act)
        page_mid = self.navigator.resolve_page(pages.page_climb_main)
        page_pass = self.navigator.resolve_page(pages.page_climb_pass)
        page_ap = self.navigator.resolve_page(pages.page_climb_ap)

        page_act.connect(page_mid, ActivityShikigamiAssets.I_TO_BATTLE_MAIN, key='activity->climb_main')

        page_mid.connect(page_ap, ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2, key='climb_main->climb_ap')
        page_ap.add_enter_failure_hooks(pages.conditional_action(
            condition=ActivityShikigamiAssets.I_CLIMB_MODE_PASS,
            action=ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH,
        ))
        page_mid.connect(page_pass, ActivityShikigamiAssets.I_TO_BATTLE_MAIN_2, key='climb_main->climb_pass')
        page_pass.add_enter_failure_hooks(pages.conditional_action(
            condition=ActivityShikigamiAssets.I_CLIMB_MODE_AP,
            action=ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH,
        ))
        page_pass.connect(page_ap, ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH, key='climb_pass->climb_ap')
        page_ap.connect(page_pass, ActivityShikigamiAssets.I_CLIMB_MODE_SWITCH, key='climb_ap->climb_pass')

    def run_climb(self):
        logger.hr('Start activity: Climb', 1)
        self.setup_climb_pages()
        # 爬塔线的宏观空闲（macro idle）由 Fatigue 安全节点（`_activity_challenge_safe_break`
        # 里的 `try_fatigue_break`）接管，`prepare_next_action` 不再叠加旧 `random_sleep`
        # （见 `docs/DECISIONS.md` D001 Fatigue Safe Point 补记）。
        self._fatigue_owns_macro_idle = True
        # 爬塔线专用的单击结算（2026-09-23）：`_handle_result` / `_handle_reward` 只在本线运行
        # 期间才接管，大富翁 / 伪神降临仍走 GeneralBattle 原有 Settlement V3。
        self._climb_owns_settlement_single_click = True
        self.begin_fatigue_task('ActivityShikigami')
        for action_type in self.conf.general_config.climb_sequence_v:
            if self.time_limit_reached():
                return
            self._run_climb_type(action_type)

    def _run_climb_type(self, action_type: str):
        logger.hr(f'Start climb type: {action_type}', 2)
        self.current_action_type = action_type
        destination = getattr(pages, f'page_climb_{action_type}')
        self.goto_page(destination)
        self._sync_climb_team_lock(action_type)
        # 首轮没有「上一轮 cycle complete」：第一次 Challenge Ready 仍可记 Fatigue 安全节点，
        # 但 `repeat_completed=False`；一场 battle + 活动结算 drain 完整跑完后才置 True。
        cycle_completed = False
        # 连续识别不到已知页面的墙钟：只在真正连续 None 时才计时，一旦识别到任意已知页面
        # 立即清空——不惩罚偶发的一帧过渡，只兜住持续卡在未知页面的情况。
        unknown_page_timer = None

        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if current_page is not None:
                unknown_page_timer = None
            if current_page == destination:
                self._sync_climb_penta_pass()
                if not self.prepare_next_action(action_type):
                    return
                try:
                    if not self._activity_challenge_safe_break(
                            action_type, destination, repeat_completed=cycle_completed):
                        # 不在挑战页 / 挑战键未就绪 / 休息后状态变化 —— 回循环顶重判
                        time.sleep(0.3)
                        continue
                    self._run_climb_action(action_type, destination)
                except ActivityResourceNotEnough:
                    logger.info(f'Climb resource exhausted: {action_type}')
                    return
                cycle_completed = True
                continue
            if current_page in (pages.page_battle_prepare, pages.page_battle):
                self.run_general_battle(
                    self.battle_config(action_type),
                    battle_key=f'activity_{action_type}',
                )
                self._drain_activity_settlement(action_type, destination)
                cycle_completed = True
                continue
            if current_page == pages.page_reward:
                self.click(pages.random_click(ltrb=(False, False, True, False)), interval=1.5)
                continue
            if current_page is None:
                if unknown_page_timer is None:
                    unknown_page_timer = Timer(ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT).start()
                    logger.warning(
                        f'Climb {action_type}: current page not recognized, '
                        f'start bounded wait ({ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT}s)'
                    )
                elif unknown_page_timer.reached():
                    logger.warning(
                        f'Climb {action_type}: page stayed unrecognized for '
                        f'{ACTIVITY_CLIMB_UNKNOWN_PAGE_TIMEOUT}s, abort this climb type'
                    )
                    raise GamePageUnknownError(
                        f'ActivityShikigami climb {action_type}: page unrecognized too long'
                    )
                time.sleep(0.5)
                continue
            self.goto_page(destination)

    def _run_climb_action(self, action_type: str, destination):
        if not self._climb_resource_available(action_type):
            raise ActivityResourceNotEnough

        self.switch_soul_for(
            action_type,
            self.I_BATTLE_MAIN_TO_RECORDS,
            return_page=destination,
        )
        entered = self._enter_climb_battle(action_type)
        if not entered:
            raise ActivityResourceNotEnough

        self._record_climb_consumption(action_type)
        self.record_action(action_type)
        self.run_general_battle(
            self.battle_config(action_type),
            battle_key=f'activity_{action_type}',
        )
        self._drain_activity_settlement(action_type, destination)

    def _climb_fire_rule(self, action_type: str):
        return self.I_AS_BOSS_FIRE if action_type == 'boss' else self.I_ACT_FIRE

    # ------------------------------------------------------------------------------------
    # 爬塔线专用结算单击（2026-09-23）：只在 `_climb_owns_settlement_single_click` 为真
    # （= `run_climb()` 运行期间）接管 `_handle_result` / `_handle_reward`，取消 GeneralBattle
    # 通用 Settlement Micro-Burst Session（segment 预算 / burst 连击 / anchor 跨调用复用）在本线
    # 的参与；大富翁 / 伪神降临不受影响，`super()` 原样回落到 GeneralBattle 原有实现。
    #
    # 每次 `_handle_result` / `_handle_reward` 调用最多点一次，且每次都是独立完整的一轮事务
    # （reaction → fresh screenshot → 再确认结算状态仍存在 → 70/30 选区域 → 现采坐标 → 单击），
    # 不预授权第二击、不跨调用复用上一次的 anchor——需要继续处理结算时，由 `run_general_battle`
    # 主循环下一帧重新调用本方法，自然形成全新的一轮。
    # ------------------------------------------------------------------------------------

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if not self._climb_owns_settlement_single_click:
            return super()._handle_result(context, config)
        # 与 BaseAct._handle_result 一致：boss 结算前先点掉专属附属弹窗，不因本轮改造丢失。
        if self.current_action_type == 'boss':
            self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
        context.reward_no_battle_ts = None
        context.is_win = not self.appear(self.I_FALSE, threshold=0.8)
        if context.last_page != page_battle_result:
            self.device.click_record_clear()
        if self._is_generic_result_context():
            self._activity_settlement_single_click(context, current_page=page_battle_result)
        else:
            # 非通用结果标志（更宽的 I_BATTLE_STATE_INFO）：本轮不改，沿用旧的单次节流点击。
            self._settlement_click(context)
        return BattleAction.CONTINUE

    def _handle_reward(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if not self._climb_owns_settlement_single_click:
            return super()._handle_reward(context, config)
        context.reward_no_battle_ts = None
        context.is_win = True
        if context.last_page != page_reward:
            self.device.click_record_clear()
        # 特殊弹窗：本轮确实点中任意一个就立即 CONTINUE，下一轮 fresh screenshot 再判
        # （与 GeneralBattle._handle_reward 一致，未改）。
        if self.appear_then_click(self.I_OVER_GHOST, interval=0.8):
            return BattleAction.CONTINUE
        if self.appear_then_click(self.I_GB_SKIN_CONFIRM, interval=0.8):
            return BattleAction.CONTINUE
        self._activity_settlement_single_click(context, current_page=page_reward)
        return BattleAction.CONTINUE

    def _activity_settlement_single_click(self, context: BattleContext, current_page: Page) -> None:
        """一次独立的结算单击事务，最多执行 1 次 `execute_single_click`。

        reaction owner：本线自己的 `ACTIVITY_SETTLEMENT_REACTION`（0.45~0.85s，见常量定义处），
        不再借用 GeneralBattle 的 `SETTLEMENT_BURST_CLICK_INTERVAL_RANGE`（那是 Micro-Burst
        同一 burst 内两击之间的观察间隔，语义不同、且属于通用 Settlement V3 的 timing）。
        本事务的 timing 由本状态机自己拥有（`InteractionPolicy.SPECIAL` 语义），手动采样 +
        sleep，不经过 `appear_then_click(policy=...)` / `confirm_delay`，因此整条链路上
        **只有这一层 reaction**，不会和通用 L2 policy 叠加。

        顺序固定：reaction → sleep → fresh screenshot → 确认仍需结算（含真实挑战页 / 挑战键
        硬停止）→ 70/30 选区域 → 现采坐标 → 单击。**坐标一定在等待之后才采样**，不允许先采样
        再跨等待复用。
        """
        reaction = random_delay(*ACTIVITY_SETTLEMENT_REACTION)
        time.sleep(reaction)
        self.screenshot()
        if self._climb_settlement_should_stop():
            return
        if self._classify_general_battle_page() != current_page:
            # 结算状态已经变化（含彻底离开 result/reward）：不用旧判断硬点，交回外层
            # `run_general_battle` 主循环下一帧 fresh classify、按新状态重新分发。
            return
        region = self._select_activity_settlement_region()
        x, y = self._sample_settlement_point(region)
        execute_single_click(self.device, FinalPoint(x, y), control_name=region.name)

    def _climb_settlement_should_stop(self) -> bool:
        """结算期间若已经出现真正的挑战页（`page_climb_<type>`）或挑战键，说明战斗-结算
        流程其实已经结束，不能再当成结算继续点——复用已有的 `page_climb_<type>` /
        `_climb_fire_rule`，不新造判据（2026-09-22 真机事故教训：`page_climb_pass` 不是
        弹窗，是真实挑战页）。非爬塔行动类型理论上不会走到这里（由
        `_climb_owns_settlement_single_click` 门控），这里仍加一层防御性判断。"""
        action_type = self.current_action_type
        if action_type not in CLIMB_TYPES:
            return False
        destination = getattr(pages, f'page_climb_{action_type}')
        if self.get_current_page() == destination:
            return True
        return self.appear(self._climb_fire_rule(action_type))

    def _select_activity_settlement_region(self) -> RuleClick:
        """70% `C_RANDOM_ACTIVITY_1` / 30% `C_RANDOM_ACTIVITY_2`。用项目已有的
        `module.base.utils.random.random_int`（模块级 `SystemRandom`，与
        `GeneralBattle._select_reward_region` 同一随机源），不新建 `random.Random`。"""
        if random_int(1, 100) <= 70:
            return self.C_RANDOM_ACTIVITY_1
        return self.C_RANDOM_ACTIVITY_2

    def _record_climb_consumption(self, action_type: str) -> None:
        """成功进入战斗时保存本场不可变的资源消耗快照。"""
        penta_enabled = (
            self.penta_pass_active
            and self.climb_consumable_count['penta_pass'] > 0
        )
        resource_consumption = 5 if penta_enabled else 1
        penta_consumption = 1 if penta_enabled else 0
        self.climb_pending_consumption[action_type] = resource_consumption
        self.climb_pending_consumption['penta_pass'] = penta_consumption
        logger.info(
            'Record climb consumption snapshot: '
            f'resource={action_type}:{resource_consumption}, '
            f'penta_pass={penta_consumption}'
        )

    def _sync_climb_penta_pass(self) -> None:
        """按通用配置及剩余数量同步五倍卷开关。"""
        configured = self.conf.general_config.use_penta_pass
        remain = None
        desired_enabled = False
        pending_consumption = self.climb_pending_consumption['penta_pass']
        if configured or pending_consumption > 0:
            raw_remain = self.O_REMAIN_PENTA_PASS.ocr_digit(
                self.device.image
            )
            remain = self._update_climb_consumable_count(
                'penta_pass', raw_remain
            )
            desired_enabled = configured and remain > 0
            if not desired_enabled:
                logger.info('Climb penta pass exhausted; disable penta mode')

        enabled_rule = self.I_FIGHT_PENTA_USE
        disabled_rule = self.I_FIGHT_PENTA_DISUSE
        target_rule = enabled_rule if desired_enabled else disabled_rule
        click_rule = disabled_rule if desired_enabled else enabled_rule

        for attempt in range(1, 4):
            self.screenshot()
            if self.appear(target_rule):
                self.penta_pass_active = desired_enabled
                logger.debug(
                    'Climb penta mode synchronized: '
                    f'enabled={desired_enabled}, remain={remain}'
                )
                return
            if not self.appear(click_rule):
                self.penta_pass_active = self.appear(enabled_rule)
                logger.warning(
                    'Cannot identify climb penta toggle state; '
                    f'enabled={desired_enabled}, remain={remain}'
                )
                return
            self.click(click_rule, interval=0)
            time.sleep(0.5)
            logger.debug(
                'Toggle climb penta mode: '
                f'enabled={desired_enabled}, attempt={attempt}/3'
            )

        logger.warning(
            'Failed to synchronize climb penta mode after 3 attempts: '
            f'enabled={desired_enabled}, remain={remain}'
        )
        self.screenshot()
        self.penta_pass_active = self.appear(enabled_rule)

    @staticmethod
    def _normalize_climb_consumable_count(
            name: str,
            raw_count: int,
            previous_count: int,
            expected_consumption: int,
    ) -> int:
        """根据上一场消耗快照修正任意爬塔资源的 OCR 异常下降。"""
        if previous_count < 0:
            if raw_count <= 0:
                logger.info(
                    f'Climb {name} count is 0 on entry; resource exhausted'
                )
            return max(raw_count, 0)

        if expected_consumption <= 0:
            return max(raw_count, 0)

        expected_count = max(previous_count - expected_consumption, 0)
        if raw_count < expected_count:
            logger.warning(
                f'Climb {name} OCR decreased beyond consumption snapshot: '
                f'previous={previous_count}, raw={raw_count}, '
                f'consumption={expected_consumption}, '
                f'corrected={expected_count}'
            )
            return expected_count

        if raw_count < previous_count:
            logger.info(
                f'Climb {name} count decreased: '
                f'{previous_count} -> {raw_count}, '
                f'expected_consumption={expected_consumption}'
            )
        return raw_count

    def _update_climb_consumable_count(
            self, name: str, raw_count: int
    ) -> int:
        """用公共修复器更新一种爬塔资源，并消费其待确认快照。"""
        previous_count = self.climb_consumable_count[name]
        expected_consumption = self.climb_pending_consumption[name]
        remain = self._normalize_climb_consumable_count(
            name=name,
            raw_count=raw_count,
            previous_count=previous_count,
            expected_consumption=expected_consumption,
        )
        self.climb_consumable_count[name] = remain
        self.climb_pending_consumption[name] = 0
        logger.info(
            f'Climb {name} remain: raw={raw_count}, normalized={remain}, '
            f'previous={previous_count}, '
            f'expected_consumption={expected_consumption}'
        )
        return remain

    def _activity_challenge_safe_break(self, action_type: str, destination,
                                       *, repeat_completed: bool) -> bool:
        """「稳定活动挑战页 + 挑战键 Ready」= 本期活动的 Fatigue 安全节点（唯一
        `try_fatigue_break` 调用点，task-local，不影响大富翁 / 伪神降临线）。

        链：fresh screenshot → 当前页 == destination 且挑战键 positive → 把上一轮记为 cycle
        complete（`repeat_completed`，首轮为 False）→ `try_fatigue_break` → 若真的休息 / 发呆过：
        结束后 fresh screenshot 重新确认「仍在挑战页 + 挑战键仍在 + 资源 OCR 仍允许」——挑战页
        变化 → 返回 False（回循环顶重判，不点旧坐标）；资源在休息期间耗尽 →
        `raise ActivityResourceNotEnough`（优雅停止本 action type）。

        Returns:
            bool: 是否可以继续进入 FIRE。
        """
        self.screenshot()
        if self.get_current_page() != destination:
            return False
        fire_rule = self._climb_fire_rule(action_type)
        if not self.appear(fire_rule):
            return False
        result = self.try_fatigue_break(
            safe=True,
            repeat_completed=repeat_completed,
            deadline=self.start_time + self.conf.general_config.limit_time_v,
        )
        if result is None:
            return True
        # 真的休息 / 发呆过 —— 不能沿用休息前的旧帧，必须重新识别当前状态。
        self.screenshot()
        if self.get_current_page() != destination or not self.appear(fire_rule):
            logger.info('Activity challenge page changed during fatigue break, re-evaluate')
            return False
        # 休息期间资源可能耗尽（活动结束 / 门票用完）。`_climb_resource_available` 自带 fresh
        # screenshot + OCR；此处提前消费 `climb_pending_consumption[action_type]` 无害——
        # 紧接着 `_run_climb_action` 的 pre-FIRE 复检会以 expected_consumption=0 重读一次。
        if not self._climb_resource_available(action_type):
            logger.info(f'Activity resource exhausted during fatigue break: {action_type}')
            raise ActivityResourceNotEnough
        return True

    def _classify_climb_fire_state(self, fire_rule) -> str:
        """当前 fresh frame 的爬塔 FIRE 事务状态（**不截图 / 不点击**）：

        - ``'battle'``  —— 已进入一场**新**战斗（窄 detector `_is_active_battle_entry()`：
          准备页 / 战斗进行页；不含 result / reward / win / false / 活动结算弹窗）；
        - ``'ready'``  —— 仍在挑战页且挑战键可见；
        - ``'unknown'`` —— 过渡 / 加载 / 未知帧（既不算成功也不算失败）。

        RESOURCE_EMPTY 不在这里判：本期无置灰挑战按钮、无资源不足弹窗、无购买确认弹窗，
        资源不足仅一闪而过的 ~1s 提示文字（无稳定 marker，不作主判据）。资源判据是 FIRE 前
        `_climb_resource_available` 的 OCR + bounded 用尽后的语义收敛（见 `_enter_climb_battle`）。
        """
        if self._is_active_battle_entry():
            return 'battle'
        if self.appear(fire_rule):
            return 'ready'
        return 'unknown'

    def _wait_climb_fire_state(self, fire_rule,
                              timeout: float = ACTIVITY_FIRE_POST_CLICK_TIMEOUT) -> str:
        """post-click / 挑战未就绪时的有界状态轮询，**期间不点任何坐标**。

        返回 ``'battle'`` / ``'ready'``（出现决定性状态即返回）/ ``'timeout'``（整个 timer 内
        一直是 ``'unknown'`` 过渡帧 —— 既不当 success 也不当 failure，timer 内持续等）。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            state = self._classify_climb_fire_state(fire_rule)
            if state != 'unknown':
                return state
        return 'timeout'

    def _enter_climb_battle(self, action_type: str) -> bool:
        """在爬塔挑战页点「挑战」直到正向确认进入一场**新**战斗的 bounded battle-entry
        transaction（取代旧的 `while True` + 宽 `is_in_battle(False)` + 仅 `random.randint(3,5)`
        次点击、无墙钟 timeout 的写法）。

        - 正向成功唯一判据 = `_is_active_battle_entry()`（准备页 / 战斗进行页窄 detector），
          **不含** result / reward / win / false / 活动结算弹窗 —— 见 `docs/DECISIONS.md`
          D001 补记「Battle Lifecycle Detector ≠ New Battle Entry Detector」。
        - 每次真实点击前独立采样任务 FIRE reaction（`fire_reaction_range`，默认 0.4~0.8） → `sleep` → fresh screenshot →
          二次确认挑战键仍在 → 点击；reaction 期间离开 ready / 按钮消失 → 不点旧坐标。
        - 有限 attempt(`ACTIVITY_FIRE_MAX_TRIES`) + 墙钟(`ACTIVITY_FIRE_TIMEOUT`) + post-click
          三态轮询上限(`ACTIVITY_FIRE_POST_CLICK_TIMEOUT`)：fire 键一直不出现 / 页面一直
          unknown / transition 卡住都有限退出。用尽 → 返回 False，caller（`_run_climb_action`）
          转 `ActivityResourceNotEnough` 优雅停止本 action type。
        """
        fire_rule = self._climb_fire_rule(action_type)
        overall_timer = Timer(ACTIVITY_FIRE_TIMEOUT).start()
        for attempt in range(1, ACTIVITY_FIRE_MAX_TRIES + 1):
            if overall_timer.reached():
                break
            self.screenshot()
            state = self._classify_climb_fire_state(fire_rule)
            if state == 'battle':
                logger.info(f'Climb {action_type} fire: already at battle entry')
                return True
            if state == 'unknown':
                # 过渡 / 未知帧 → 有界等一个决定性状态，不点任何坐标
                if self._wait_climb_fire_state(fire_rule) == 'battle':
                    logger.info(f'Climb {action_type} fire: entered battle during transition')
                    return True
                continue
            # state == 'ready' —— 挑战键确实在
            if self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=1) or \
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                self.device.click_record_clear()
                continue
            fire_delay = random_delay(*fire_reaction_range(self.conf.fire_reaction))
            logger.info(
                f'Climb {action_type} fire: attempt {attempt}/{ACTIVITY_FIRE_MAX_TRIES}, '
                f'reaction {fire_delay:.2f}s before click {fire_rule.name}'
            )
            time.sleep(fire_delay)
            self.screenshot()
            state = self._classify_climb_fire_state(fire_rule)
            if state == 'battle':
                logger.info(f'Climb {action_type} fire: entered battle during reaction')
                return True
            if state != 'ready' or not self.appear(fire_rule):
                logger.info(f'Climb {action_type} fire: target gone during reaction, re-evaluate')
                continue
            self.appear_then_click(fire_rule, interval=1)
            self.device.click_record_clear()
            if self._wait_climb_fire_state(fire_rule) == 'battle':
                logger.info(f'Climb {action_type} fire: entered battle after click')
                return True
            # 'ready' / 'timeout' → 下一 attempt（transition-unknown 不当 immediate failure）
        logger.warning(
            f'Climb {action_type} fire: bounded battle-entry retry exhausted '
            '(transition unknown / resource may be depleted)'
        )
        return False

    def _drain_activity_settlement(self, action_type: str, destination) -> bool:
        """本期活动战斗结束后是一个「活动专用结算弹窗」（不是旧的通用胜负结果页）。用户实测
        该弹窗可安全套用 GeneralBattle Settlement V3 的 `C_RANDOM_DEFAULT`（`random_default`）
        大安全区推进，不会点到危险控件。

        `run_general_battle` 内部（配合 `BaseAct.before_run` 把 `I_UI_BACK_RED` 并入
        `page_battle_result` recognizer）通常已把弹窗点掉；本方法是**有界的兜底 + 回稳定挑战页
        的正向确认**：直到 `destination` 页 + 挑战键可见（= cycle complete 边界）或点击次数 /
        墙钟用尽。**弹窗消失本身不算成功**——必须重新识别到挑战页 + 挑战键 positive。

        2026-09-22 真机事故修正：`self.get_current_page() == destination`（结构性已经在挑战页，
        如标题横幅 + 模式标志）为真、但 `fire_rule`（挑战/FIRE 键）还没渲染出来这一状态，**不是**
        残留结算弹窗——是挑战页自己的进场动画还没走完，此时点 `C_RANDOM_DEFAULT` 既没有意义（没有
        弹窗要点掉），也可能干扰挑战键的正常渲染。这里复用 FIRE 契约已有的
        `_wait_climb_fire_state`（`_enter_climb_battle` 同款有界三态轮询），只等、不点；等到
        `'battle'`（又落回战斗态）按原语义交回外层，等到 `'ready'` 或 `'timeout'` 都回到本函数
        顶部重新判定——**不新增点击路径、不绕过既有的次数 / 墙钟上限**。只有 `get_current_page()`
        不等于 `destination`（真正还是别的页面 / 未知帧）才继续走原有的盲点兜底。
        """
        fire_rule = self._climb_fire_rule(action_type)
        timer = Timer(ACTIVITY_SETTLEMENT_TIMEOUT).start()
        clicks = 0
        while not timer.reached():
            self.screenshot()
            if self.get_current_page() == destination:
                if self.appear(fire_rule):
                    logger.info(
                        f'Activity settlement drained, back to climb {action_type} challenge page'
                    )
                    return True
                # 已经结构性落在挑战页，只是挑战键还没就绪——不是弹窗，不能盲点，有界等一个
                # 决定性状态（复用 FIRE 契约既有的三态轮询，不新发明机制）。
                logger.info(
                    f'Activity settlement drain: on {destination} but {fire_rule.name} not ready yet, '
                    'wait instead of blind click'
                )
                state = self._wait_climb_fire_state(fire_rule)
                if state == 'battle':
                    logger.info(
                        'Activity settlement drain: battle re-entered while waiting for fire, defer to loop'
                    )
                    return False
                continue  # 'ready' 下一轮顶部会命中 return True；'timeout' 回到顶部重新判定
            if self._is_active_battle_entry():
                # 兜底：又落回战斗态，交回外层循环处理，不在这里点 random_default
                logger.info('Activity settlement drain: battle entry re-detected, defer to loop')
                return False
            if clicks >= ACTIVITY_SETTLEMENT_MAX_CLICKS:
                break
            # 复用 GeneralBattle Settlement V3 的大安全区采样，不新造坐标 / 区域
            self._sample_settlement_click(self.C_RANDOM_DEFAULT)
            clicks += 1
            time.sleep(random_delay(*self.SETTLEMENT_CLICK_INTERVAL_RANGE))
        logger.warning(
            f'Activity settlement drain bounded out (clicks={clicks}); '
            'return to challenge page will be retried by loop'
        )
        return self.get_current_page() == destination and self.appear(fire_rule)

    def _sync_climb_team_lock(self, action_type: str):
        enable = self.battle_config(action_type).lock_team_enable
        if action_type == 'boss':
            lock_rule, unlock_rule = self.I_LOCK, self.I_UNLOCK
        else:
            lock_rule, unlock_rule = self.I_AP_LOCK, self.I_AP_UNLOCK
        if enable:
            logger.info(f'Lock {action_type} team')
            self.ui_click(unlock_rule, stop=lock_rule, interval=1.5)
        else:
            logger.info(f'Unlock {action_type} team')
            self.ui_click(lock_rule, stop=unlock_rule, interval=1.5)

    def _climb_resource_available(self, action_type: str) -> bool:
        logger.hr(f'Check {action_type} resource')
        self.screenshot()
        if action_type == 'pass':
            raw_remain = self.O_REMAIN_PASS.ocr_digit(self.device.image)
        elif action_type == 'ap':
            raw_remain = self.O_REMAIN_AP.ocr_quantity(self.device.image)
        elif action_type == 'boss':
            _, raw_remain, _ = self.O_REMAIN_BOSS.ocr_digit_counter(self.device.image)
        else:
            raw_remain = self.O_REMAIN_AP100.ocr_digit(self.device.image)

        remain = self._update_climb_consumable_count(
            action_type, raw_remain
        )
        return remain > 0
