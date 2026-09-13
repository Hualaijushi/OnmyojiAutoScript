# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
from time import sleep
from cached_property import cached_property
from tasks.GameUi.default_pages import page_exploration

from tasks.base_task import BaseTask
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction, BattleContext, ExitMatcher, GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_realm_raid
from tasks.RealmRaid.assets import RealmRaidAssets
from tasks.RealmRaid.config import WhenAttackFail
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.RealmRaid.page import page_shikigami_records


from module.logger import logger
from module.exception import TaskEnd
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.atom.image_grid import ImageGrid
from module.atom.image import RuleImage
from module.atom.click import RuleClick
from module.reaction_profile import REACTION_FAST, REACTION_NORMAL, REACTION_CONFIRM, REACTION_FIRE


# fire() 的有限 attempt / 总超时 / 点击后正向确认等待。engineering baseline，非 Level C 标定：
# max_tries / timeout 参考 Exploration.fire()（max_tries=4 + Timer(10)）；点击后确认等待参考
# RyouToppa 的 RYOU_TOPPA_STATE_TIMEOUT=3。
RR_FIRE_MAX_TRIES = 4
RR_FIRE_TIMEOUT = 10
RR_FIRE_POST_CLICK_TIMEOUT = 3

# 目标级业务 pacing —— 已根据 fresh 九宫格确定本轮目标后、真正点开该目标详情前的人为停顿。
# 与 FIRE reaction（REACTION_FIRE，在 fire() 里）是两个不同 timing owner，不合并；只在每个新
# 选定目标点开详情前发生一次，不进 FIRE retry / post-click polling / 再次挑战 / battle /
# settlement / refresh。PROVISIONAL / Level C：RealmRaid 本轮首次引入自己的目标 pacing，取
# (1.0, 2.5)（RyouToppa 的区域 (1.0, 3.0) pacing 属 RyouToppa，与此无关、未动）。
RR_TARGET_PACING = (1.0, 2.5)

# 退四 = 对「只剩最后 1 个可攻打目标」的那个目标做 fire 一次 + 「再次挑战」4 次（前 3 次
# quick_exit 投降、第 4 次真打）——沿用旧 run() 里逐字硬编码的 4 次业务约定，不是新拍的次数。
RR_EXIT_FOUR_SURRENDERS = 4

# fire_again()（退四内部「再次挑战」）的有限 attempt / 总超时 / 点击后正向确认等待。
# engineering baseline，非 Level C 标定：对齐 fire() 的 RR_FIRE_*。
RR_AGAIN_MAX_TRIES = 4
RR_AGAIN_TIMEOUT = 10
RR_AGAIN_POST_CLICK_TIMEOUT = 3
# 退四「再次挑战」后的确认弹窗：确认按钮独立 reaction，不复用 I_FIRE_AGAIN 的 REACTION_FIRE。
RR_AGAIN_CONFIRM_DELAY = (0.3, 0.6)

# 疲劳安全节点前「确认已回到个人突破稳定九宫格」的有界等待（刷新 / 结算动画收尾）。
# 复用个人突破页固定返回键 I_BACK_RED 作为 recovery-complete 判据，不用固定 sleep。
# engineering baseline，非 Level C 标定。
RR_CYCLE_STABLE_TIMEOUT = 10


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, RealmRaidAssets):
    init_tickets: int = -1
    PREPARE_CLICK_DELAY_RANGE = (2.5, 3.5)
    SETTLEMENT_CLICK_INTERVAL_RANGE = (0.65, 0.95)

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if config.quick_exit:
            context.reward_no_battle_ts = None
            context.is_win = not self.appear(self.I_FALSE)
            return BattleAction.EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE
        return super()._handle_result(context, config)

    def _exit_matcher(self) -> ExitMatcher:
        return self.I_BACK_RED

    def run(self):
        con = self.config.realm_raid
        # 直接进入个人突破页面
        self.goto_page(page_realm_raid)

        # 在突破页面内先判断票数，如果没有票了或者已经达到攻击次数上限，就直接结束任务
        if not self.check_ticket(con.raid_config.number_base):
            self.goto_page(page_exploration)
            self.set_next_run(task='RealmRaid', success=False, finish=True)
            raise TaskEnd

        # 票数足够，现在开始进行御魂切换
        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
                
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)
            
        # 切换完成后，必须返回突破页面
        self.goto_page(page_realm_raid)

        # 有呱太活动的时候第一次进入还会 出现一个弹窗
        self.screenshot()
        if self.appear(self.I_FROG_RAID):
            logger.info(f'Click {self.I_FROG_RAID.name}')
            while 1:
                self.screenshot()
                if not self.appear(self.I_FROG_RAID):
                    break
                if self.appear_then_click(self.I_FROG_RAID, interval=1):
                    continue
        # 判断是不是锁定阵容
        self.ensure_lock(con.general_battle_config.lock_team_enable)
        # 判断是否是呱太活动
        frog = self.is_frog(True)
        if frog:
            logger.info(f'Frog raid')

        # 开始循环
        success = True
        last_battle = True  # 记录上一次战斗的结果
        # 用户配置的锁定阵容默认值——每轮循环顶复位（呱太目标会临时改成 False），退四用 try/finally 恢复它
        lock_default = con.general_battle_config.lock_team_enable
        # when_attack_fail == CONTINUE 时「本轮不再攻打的失败目标」——纯局部业务状态，不污染截图 /
        # 不改 asset / 不伪造 broken marker。只影响普通固定 1→9 选目标；退四的「只剩最后 1 个」判据
        # 始终看真实 UI 可攻打数。刷新成功（换新九宫格）后清空。
        failed_orders: set = set()
        # RealmRaid 主循环疲劳任务标记：安全节点在「一个目标业务循环完整结束、failure recovery
        # （刷新 / CONTINUE 跳过记录）也做完、回到个人突破稳定九宫格」之后触发
        # （见 _realm_raid_cycle_safe_break）。RealmRaid 无墙钟时限，deadline=None。
        self.begin_fatigue_task('RealmRaid')
        while 1:
            self.screenshot()
            con.general_battle_config.lock_team_enable = lock_default
            # 检查票数
            if not self.check_ticket(con.raid_config.number_base):
                break
            # ----------------------------------------固定 1→9（从左到右、从上到下）选第一个可攻打目标
            targets = self._grid_targets()
            # 普通选目标的候选先排除本轮 CONTINUE 已失败的 order（failed_orders 只影响这里，不影响
            # 下面的 only_last —— 退四判据始终用真实 UI 可攻打数 len(targets)）
            available = {order: m for order, m in targets.items() if order not in failed_orders}
            if not available:
                # 九宫格已无可选目标（全部已破 / 或本轮 CONTINUE 已全部跳过）
                if con.raid_config.when_attack_fail == WhenAttackFail.CONTINUE:
                    logger.info('No selectable target (all broken or skipped this grid) and then refresh')
                    if self.check_refresh():
                        failed_orders.clear()
                        self._realm_raid_cycle_safe_break()
                        continue
                    success = False
                    break
                logger.info('No one can attack, break')
                success = False
                break
            index = min(available)
            medal = available[index]
            only_last = len(targets) == 1

            if only_last and con.raid_config.exit_four:
                # ---- 退四：仅当九宫格只剩最后 1 个可攻打目标、且 exit_four 开启时进入 ----
                # 退四是高影响分支（解锁阵容 + 投降 + fire_again）：入口再取一帧、二次确认「确实
                # 只剩这 1 个可攻打目标」，避免单帧 template 漏识别直接触发。
                self.screenshot()
                if not self._is_only_remaining_target(index):
                    logger.info('Exit four: not the sole attackable target on fresh frame, re-scan')
                    continue
                logger.info(f'Exit four: order {index} is the last attackable target')
                # 退四前解锁阵容（仅退四最后目标）。临时状态用 try/finally 保证任何出口都恢复。
                self.ensure_lock(False)
                aborted = False
                try:
                    # 目标级 pacing + 点开详情；退四目标要求「点击前最后一帧仍是唯一可攻打目标」
                    if not self._enter_target(index, require_only_remaining=True):
                        continue
                    if not self.fire(index):
                        continue
                    last_battle = self.run_general_battle(config=self.build_quick_exit_config(con.general_battle_config))
                    for i in range(RR_EXIT_FOUR_SURRENDERS):
                        if not self._fire_again():
                            aborted = True
                            break
                        is_final = i == RR_EXIT_FOUR_SURRENDERS - 1
                        cfg = con.general_battle_config if is_final else self.build_quick_exit_config(con.general_battle_config)
                        last_battle = self.run_general_battle(config=cfg)
                finally:
                    # 无论正常结束 / continue / break / 异常，都恢复用户原本的锁定阵容配置
                    self.ensure_lock(lock_default)
                if aborted or not last_battle:
                    # 退四中断 / 退四完成后的最终失败 → 一律刷新，不再点「再次挑战」
                    logger.info('Exit four: aborted or final battle lost -> refresh (no more fire again)')
                    if self.check_refresh():
                        failed_orders.clear()
                        self._realm_raid_cycle_safe_break()
                        continue
                    success = False
                    break
                # 退四胜利 → 落共享尾部（尾部末尾统一触发疲劳安全节点）
            else:
                # ---- 普通目标 ----
                if self.check_medal_is_frog(frog, medal, index):
                    # 如果挑战的这只是呱太的话，就要把锁定改为不锁定（循环顶已复位 lock_default）
                    con.general_battle_config.lock_team_enable = False
                if not self._enter_target(index):
                    continue
                if not self.fire(index):
                    # 没有成功进入战斗则重新检查票数和其他条件
                    continue
                last_battle = self.run_general_battle(con.general_battle_config)

            # ---- 共享尾部 ----
            # 三胜奖励：领完立即回循环顶（属同一 cycle 的收尾，不在此触发疲劳）
            if self.reward_detect_click(False):
                logger.info('Rewards of three wins')
                continue
            # 刷新 >> 如果勾选了三次刷新并且到达了三次，就刷新
            if con.raid_config.three_refresh and self.appear(self.I_RR_THREE, threshold=0.8):
                logger.info('Three refresh')
                if self.check_refresh():
                    failed_orders.clear()
                    self._realm_raid_cycle_safe_break()
                    continue
                success = False
                break
            # 普通失败：按 when_attack_fail 完成 failure recovery 之后，才在稳定九宫格触发疲劳
            if not last_battle:
                if con.raid_config.when_attack_fail == WhenAttackFail.REFRESH:
                    logger.info('Battle lost and then refresh')
                    if self.check_refresh():
                        failed_orders.clear()
                        self._realm_raid_cycle_safe_break()
                        continue
                    success = False
                    break
                if con.raid_config.when_attack_fail == WhenAttackFail.EXIT:
                    logger.info('Battle lost and exit')
                    break
                if con.raid_config.when_attack_fail == WhenAttackFail.CONTINUE:
                    # 本轮不刷新：把当前失败目标加入 skip，回稳定九宫格后触发疲劳，
                    # 下一轮固定 1→9 会跳过它
                    logger.info(f'Battle lost, CONTINUE: skip order {index} for this grid')
                    failed_orders.add(index)
                    self._realm_raid_cycle_safe_break()
                    continue
            # 普通 / 退四胜利：回到稳定九宫格 → 疲劳安全节点
            self._realm_raid_cycle_safe_break()

        self.goto_page(page_exploration)
        self.set_next_run(task='RealmRaid', success=success, finish=True)
        raise TaskEnd

    # ----------------------------------------------------------------------------------------------------------------------
    # 2023.7.21 改版个人突破
    def ensure_lock(self, lock_team_enable: bool):
        """
        确保锁定阵容
        :param lock_team_enable:
        :return:
        """
        if lock_team_enable:
            while 1:
                self.screenshot()
                # 锁定 / 解锁是低频、含义明确的稳定按钮，识别后加一段 FAST reaction 再点
                if self.appear_then_click(self.I_UNLOCK, interval=1, confirm_delay=REACTION_FAST):
                    continue
                if self.appear_then_click(self.I_UNLOCK_2, interval=1, confirm_delay=REACTION_FAST):
                    continue
                if self.appear(self.I_LOCK_2, threshold=0.9):
                    break
                if self.appear(self.I_LOCK, threshold=0.9):
                    break
            logger.info(f'Click {self.I_UNLOCK.name}')
        else:
            while 1:
                self.screenshot()
                if self.appear_then_click(self.I_LOCK, interval=1, confirm_delay=REACTION_FAST):
                    continue
                if self.appear_then_click(self.I_LOCK_2, interval=1, confirm_delay=REACTION_FAST):
                    continue
                if self.appear(self.I_UNLOCK_2, threshold=0.9):
                    break
                if self.appear(self.I_UNLOCK, threshold=0.9):
                    break
            logger.info(f'Click {self.I_LOCK.name}')

    def is_frog(self, screenshot: bool=True) -> bool:
        """
        判断是不是呱太活动
        :return:
        """
        if screenshot:
            self.screenshot()
        if self.appear(self.I_FROG_MEDAL):
            return True
        return False

    def check_ticket(self, base: int=0) -> bool:
        """
        检查是不是有票， 检查这个票是否大于等于基准
        :param base:
        :return:
        """
        if base < 0 or base > 30:
            logger.warning(f'It is not a valid base {base}')
            base = 0
        self.wait_until_appear(self.I_BACK_RED)
        self.screenshot()
        cu, res, total = self.O_NUMBER.ocr(self.device.image)

        if total == 0:
            self.reward_detect_click(True)
            # 增加出现聊天框遮挡，处理奖励之后，重新识别票数
            cu, res, total = self.O_NUMBER.ocr(self.device.image)
        if cu == 0 and cu + res == total:
            logger.warning(f'Execute raid failed, no ticket')
            return False
        elif cu + res == total and cu < base:
            logger.warning(f'Execute raid failed, ticket is not enough')
            return False
        self.init_tickets = cu if self.init_tickets == -1 else self.init_tickets
        if self.init_tickets - cu >= self.config.realm_raid.raid_config.number_attack:  # 检查挑战次数
            logger.info(f'Current count {self.init_tickets - cu}, '
                        f'max count {self.config.realm_raid.raid_config.number_attack}')
            return False
        return True

    @cached_property
    def order_medal(self) -> ImageGrid:
        order_attack = self.config.realm_raid.raid_config.order_attack
        support_number = [0, 1, 2, 3, 4, 5]
        match = {
            0: self.I_MEDAL_0,
            1: self.I_MEDAL_1,
            2: self.I_MEDAL_2,
            3: self.I_MEDAL_3,
            4: self.I_MEDAL_4,
            5: self.I_MEDAL_5,
        }
        order = order_attack.replace(' ', '').replace('\n', '')
        order = re.split(r'>', order)
        order = [int(i) for i in order]
        order = [i for i in order if i in support_number]

        images = []
        for i in order:
            images.append(match[i])
        return ImageGrid(images)

    @cached_property
    def partition(self) -> list[RuleClick]:
        return [self.C_PARTITION_1, self.C_PARTITION_2, self.C_PARTITION_3, self.C_PARTITION_4, self.C_PARTITION_5,
                self.C_PARTITION_6, self.C_PARTITION_7, self.C_PARTITION_8, self.C_PARTITION_9]

    def _broken_orders(self) -> set:
        """当前帧里带失败 / 已攻破标记（RyouToppa loser-sign 模板 `false_image`）的九宫格位置
        （1-based 集合）。复用 `false_roi` + `false_image`；只读、不改帧。

        此前只在 `WhenAttackFail.CONTINUE` 下涂黑失败格；固定 1→9 选目标后**所有模式都需要**
        ——否则刚失败、还没刷新的格子会被重新选中。
        """
        broken = set()
        for i, roi in enumerate(self.false_roi):
            self.false_image.roi_back = roi
            if self.appear(self.false_image):
                logger.info(f'Position {i + 1} is a failed')
                broken.add(i + 1)
        return broken

    def _grid_targets(self) -> dict:
        """扫描当前 fresh frame，返回 `{1-based order: 该格勋章 RuleImage}`，已排除
        `_broken_orders()`。

        用 `order_medal.find_everyone` 一次扫全 9 格（`order_medal` 只作「这一格有没有可挑战
        对手」的过滤器——**不再按勋章数量 / `order_attack` 优先级排序**），把每个匹配按中心点
        映射到 `C_PARTITION_n`。失败格在**副本**上涂黑（不再原地污染共享帧）。调用方需保证
        已 `screenshot()`。
        """
        broken = self._broken_orders()
        image = self.device.image
        work = image.copy() if broken else image
        for order in broken:
            x, y, w, h = self.partition[order - 1].roi_back
            work[y:y + h, x:x + w, ...] = 0
        everyone = self.order_medal.find_everyone(work)
        targets: dict = {}
        if not everyone:
            return targets
        for medal_image, _score, (mx, my, mw, mh) in everyone:
            cx, cy = mx + mw / 2, my + mh / 2
            for i, click in enumerate(self.partition):
                fx, fy, fw, fh = click.roi_front
                if fx < cx < fx + fw and fy < cy < fy + fh:
                    order = i + 1
                    if order not in broken and order not in targets:
                        targets[order] = medal_image
                    break
        return targets

    def find_one(self, screenshot: bool=True) -> tuple:
        """按固定 1→9（从左到右、从上到下）返回第一个可攻打目标。

        1 2 3 / 4 5 6 / 7 8 9。可攻打 = 该九宫格位置匹配到 `order_medal` 里的任一勋章模板
        （有对手可挑战），且不在 `_broken_orders()` 里。**不再按勋章数量 / `order_attack`
        优先级 / 奖励高低排序**——只看位置。

        :return: (medal RuleImage, 1-based order)；无可攻打目标返回 (None, None)
        """
        if screenshot:
            self.screenshot()
        targets = self._grid_targets()
        if not targets:
            return None, None
        order = min(targets)
        logger.info(f'Find target order {order} (fixed 1->9)')
        return targets[order], order

    def _target_still_attackable(self, order: int) -> bool:
        """当前 fresh frame 下，`order`（1-based）这一格是否仍是可攻打目标。只读、不截图。"""
        return order in self._grid_targets()

    def _is_only_remaining_target(self, order: int) -> bool:
        """当前 fresh frame 下，九宫格是否**确实只剩 `order` 这一个可攻打目标**。

        退四是高影响分支（解锁阵容 + 投降 + fire_again），进入前 / 点击目标前都要用它二次确认，
        避免单帧漏识别直接触发退四。只读当前帧：不截图 / 不点击 / 不 sleep（截图责任在 caller）。
        """
        if not self._is_realm_raid_retryable_state():
            return False
        targets = self._grid_targets()
        return len(targets) == 1 and order in targets

    def _enter_target(self, order: int, require_only_remaining: bool = False) -> bool:
        """选定本轮目标后、真正点开该目标详情前的**目标级 pacing**（`RR_TARGET_PACING`，与
        FIRE reaction 不同 owner）+ fresh 二次确认：

        fresh screenshot → 确认 target 仍可攻打 → `random_delay(*RR_TARGET_PACING)` → `sleep`
        → fresh screenshot → 再确认（仍在个人突破可操作页 + target 仍可攻打）→ 点
        `C_PARTITION_n` 打开详情。pacing 期间目标变不可打 / 已离开可操作页 → 不点旧坐标、
        返回 False（由 `run()` 重新扫九宫格）。**只在每个新选定目标点开详情前一次。**

        `require_only_remaining=True`（退四目标专用）：pacing 前后的「仍可攻打」都收紧成
        「仍是九宫格唯一可攻打目标」（`_is_only_remaining_target`）——延迟期间若又出现别的可攻打
        目标，说明本次不是退四场景，返回 False 回主循环重扫。

        :return: True 已点开目标详情；False 目标已不可打 / 不再唯一 / 页面异常
        """
        self.screenshot()
        if require_only_remaining:
            if not self._is_only_remaining_target(order):
                return False
        elif not self._target_still_attackable(order):
            return False
        pacing = random_delay(*RR_TARGET_PACING)
        logger.info(f'Target {order}: business pacing {pacing:.2f}s before open')
        sleep(pacing)
        self.screenshot()
        if not self._is_realm_raid_retryable_state():
            logger.info(f'Target {order}: not on operable page after pacing, re-evaluate')
            return False
        if require_only_remaining:
            if not self._is_only_remaining_target(order):
                logger.info(f'Target {order}: no longer the sole remaining target after pacing, re-evaluate')
                return False
        elif not self._target_still_attackable(order):
            logger.info(f'Target {order}: no longer attackable after pacing, re-evaluate')
            return False
        self.click(self.partition[order - 1], interval=2)
        return True

    def _realm_raid_cycle_safe_break(self) -> None:
        """RealmRaid 一个完整目标业务循环（战斗 + 结果 + 必要的刷新 / CONTINUE 跳过记录）结束、
        已回到个人突破稳定九宫格后的疲劳安全节点。

        只在「一个目标（普通或退四）的战斗 + 结果 + failure recovery 都完成、即将回主循环顶重新
        `check_ticket` + 扫九宫格选目标」处调用。先有界等 `I_BACK_RED`（个人突破页固定返回键）
        确认刷新 / 结算动画结束、确实回到稳定九宫格（不用固定 sleep），再 fresh screenshot 确认
        可操作页才触发；休息 / 发呆结束后回循环顶会先 `screenshot` + `check_ticket` + `_grid_targets`
        重新扫描——即 fresh revalidate + reselect target。

        Fatigue 不进 target pacing / FIRE / FIRE retry / transition-unknown / battle / settlement /
        reward / 退四内部 / `_fire_again` 之间 / refresh 点击后但尚未确认完成 / 临时解锁未恢复时。
        RealmRaid 无墙钟时限，`deadline=None`。
        """
        self.wait_until_appear(self.I_BACK_RED, wait_time=RR_CYCLE_STABLE_TIMEOUT)
        self.screenshot()
        if not self._is_realm_raid_retryable_state():
            return
        self.try_fatigue_break(safe=True, repeat_completed=True, deadline=None)

    def check_medal_is_frog(self, is_activity: False, target: RuleImage, order: int) -> bool:
        """
        检查这个是不是呱太，为此之前你还需要判断是不是 处于呱太活动的
        :param target:
        :param is_activity: 如果不是呱太活动，那么就不需要检查了
        :param order:
        :return:
        """
        if not is_activity:
            return False
        # 好像呱太的位置是只有 789这三个
        if order < 7:
            return False
        # 有时候四星可能和五星的混一起
        if target != self.I_MEDAL_5 and target != self.I_MEDAL_4:
            return False
        match_ocr = {
            1: self.O_FROG_1,
            2: self.O_FROG_2,
            3: self.O_FROG_3,
            4: self.O_FROG_4,
            5: self.O_FROG_5,
            6: self.O_FROG_6,
            7: self.O_FROG_7,
            8: self.O_FROG_8,
            9: self.O_FROG_9,
        }
        target_ocr = match_ocr[order]
        self.screenshot()
        if target_ocr.ocr(self.device.image) == 20:
            logger.info(f'Find frog medal [{target}]')
            return True
        return False

    def reward_detect_click(self, screenshot: bool=True) -> bool:
        """
        检测是否出现 每三次就有奖励的界面, 有就领取
        :return:
        """
        if screenshot:
            self.screenshot()
        # 由于更改识别顺序，退出战斗之后，需要先等待回到个人突破界面，即识别到红色退出按钮，再进行奖励判断
        self.wait_until_appear(self.I_BACK_RED)
        self.ui_click_until_disappear(self.I_SOUL_RAID, interval=1.2)
        text = self.O_TEXT.ocr(self.device.image)
        # 识别突破卷区域，如果识别到了且其中含有文字，即有聊天框遮挡则进入循环，等待三胜奖励出现并点击，循环退出条件为识别到票（即*/*的形式）
        if text != "" and re.search(r'[\u4e00-\u9fff]', text):
            while 1:
                self.screenshot()
                result = self.O_TEXT.ocr(self.device.image)
                if not re.search(r'[\u4e00-\u9fff]', result) and re.search(r'(\d+)/(\d+)', result):
                    return True
                if self.appear_then_click(self.I_SOUL_RAID, interval=1.5):
                    continue
        return False

    def check_refresh(self, screenshot: bool=True) -> bool:
        """
        检查是否出现了刷新的按钮
        如果可以刷新就刷新，返回True
        如果在CD中，就返回False
        :return:
        """
        if screenshot:
            self.screenshot()
        if not self.appear(self.I_FRESH):
            logger.info(f'No find refresh button and it is in CD')
            return False
        while 1:
            self.screenshot()
            if self.appear(self.I_FRESH_ENSURE):
                break
            # 刷新动作本体：稳定按钮，NORMAL reaction
            if self.appear_then_click(self.I_FRESH, interval=1, confirm_delay=REACTION_NORMAL):
                continue
        while 1:
            self.screenshot()
            if not self.appear(self.I_FRESH_ENSURE):
                return True
            # 刷新确认弹窗：明确确认，CONFIRM reaction
            if self.appear_then_click(self.I_FRESH_ENSURE, interval=1, confirm_delay=REACTION_CONFIRM):
                continue
        return False

    def fire(self, order: int) -> bool:
        """
        挑战指定九宫格目标。

        成功判据是**正向战斗确认**（`is_in_battle()` —— 准备 / 战斗 / 结算 / 奖励页），
        不再以「目标详情页旧标识 `I_RR_PERSON` 消失」单独判成功（旧标识可能因页面切换中 /
        暂时识别失败 / 弹窗遮挡而消失，此时并未真正进入战斗）。

        每次真正点 `I_FIRE` 之前：独立采样 `REACTION_FIRE` 作为人为 reaction → `sleep` →
        重新截图 → 再次正向战斗确认 → 二次确认 `I_FIRE` 仍存在 → 仍存在才点。
        reaction 期间 `I_FIRE` 消失则不点旧坐标，回到循环顶按当前页面重新判断。

        **FIRE post-click / FIRE 未就绪时区分三种状态**（见 `_wait_fire_entered_battle`）：
        - `'battle'`：`is_in_battle()` —— 唯一 positive success，`return True`；
        - `'retryable'`：明确仍在个人突破可操作页面（`_is_realm_raid_retryable_state`）—— 允许下一
          attempt / 重新点九宫格打开目标详情；
        - `'timeout'`：整个 `RR_FIRE_POST_CLICK_TIMEOUT` 内一直是「旧 marker 消失、battle 未出现」的
          过渡 / 未知帧 —— **既不当 success 也不当 immediate failure**，不点任何坐标、只在 timer 内
          持续等；用尽则进入下一 attempt。

        有限 attempt（`RR_FIRE_MAX_TRIES`）+ 有限总时间（`RR_FIRE_TIMEOUT`）：用尽仍未进入
        战斗则 `return False`，由 `run()` 的 `if not self.fire(index): continue` 处理（不误交接
        `run_general_battle`）。

        :param order:  第几个（1~9）
        :return: True 已进入战斗流程；False 有限重试 / 超时仍未进入
        """
        click = self.partition[order - 1]
        self.wait_until_appear(self.I_RR_PERSON, wait_time=RR_FIRE_TIMEOUT)
        self.device.click_record_clear()
        timeout_timer = Timer(RR_FIRE_TIMEOUT).start()
        for attempt in range(1, RR_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            # 正向战斗确认：已进入准备 / 战斗流程即成功
            if self.is_in_battle(False):
                logger.info(f'Fire {order}: entered battle')
                return True
            # FIRE 未就绪：可能详情未打开 / 页面切换中 / 已点 FIRE 正在加载 / 弹窗遮挡 / 临时识别失败。
            # 有界等一个决定性状态，不在过渡帧里乱点九宫格、也不白白消耗 attempt。
            if not self.appear(self.I_FIRE, threshold=0.8):
                state = self._wait_fire_entered_battle()
                if state == 'battle':
                    logger.info(f'Fire {order}: entered battle')
                    return True
                if state == 'retryable':
                    # 明确仍在可操作的个人突破页面 → 按原逻辑点九宫格（重新）打开目标详情
                    self.click(click, interval=2)
                # state == 'timeout'（一直是 transition / unknown）→ 不点任何坐标
                continue
            # FIRE 就绪 → 每次 attempt 独立采样 reaction → fresh screenshot → 二次确认 → click
            fire_delay = random_delay(*REACTION_FIRE)
            logger.info(f'Fire {order}: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            if self.is_in_battle(False):
                return True
            if not self.appear(self.I_FIRE, threshold=0.8):
                # reaction 期间 FIRE 消失：不点旧坐标，回循环顶按当前页面判断
                logger.info(f'Fire {order}: FIRE gone during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_FIRE, interval=0, threshold=0.8)
            # post-state：有界区分 battle / retryable / transition-unknown
            state = self._wait_fire_entered_battle()
            if state == 'battle':
                logger.info(f'Fire {order}: entered battle after click')
                return True
            # 'retryable' / 'timeout' → 进入下一 attempt（transition-unknown 不当 immediate failure）
        logger.warning(f'Fire {order}: bounded retry / timeout without entering battle')
        return False

    def _wait_fire_entered_battle(self, timeout: float = RR_FIRE_POST_CLICK_TIMEOUT) -> str:
        """FIRE post-click / FIRE 未就绪时的有界状态轮询，区分三种状态、**不点任何坐标**：

        - `'battle'`：`is_in_battle()` —— 已进入 GeneralBattle 可接管的战斗流程（唯一 positive success）；
        - `'retryable'`：`_is_realm_raid_retryable_state()` —— 明确仍处于个人突破可操作页面 → 允许
          下一 attempt / 由调用方决定是否重开目标详情；
        - `'timeout'`：直到 `timer` 到期都是「旧 marker 消失、battle 未出现」的 transition / unknown ——
          **不当 immediate failure**，在 timer 内持续等 `'battle'` / `'retryable'`。

        复用 `GeneralBattle.is_in_battle()` + 已有 RealmRaid marker，不新造 page detector。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            if self.is_in_battle(False):
                return 'battle'
            if self._is_realm_raid_retryable_state():
                return 'retryable'
            # 否则 = TRANSITION_UNKNOWN：什么都不点，继续等
        return 'timeout'

    def _is_realm_raid_retryable_state(self) -> bool:
        """当前 fresh frame 是否**明确仍处于「个人突破可操作」状态**（可重新选对手 / 等待进攻按钮）。

        只读当前帧：不截图 / 不点击 / 不 sleep / 不改状态。用已有 RealmRaid marker 判定——
        - `I_RR_PERSON`：对手已选中（目标详情 / 进攻就绪态）；
        - `I_FIRE`：进攻按钮在场；
        - `I_BACK_RED`：个人突破页固定右上返回键（九宫格选择页、`_exit_matcher` 都依赖它）。
        任一命中即视为可操作；三者都没有 = 过渡 / 未知，不算 retryable。
        """
        return (
            self.appear(self.I_RR_PERSON, threshold=0.8)
            or self.appear(self.I_FIRE, threshold=0.8)
            or self.appear(self.I_BACK_RED)
        )

    def _is_active_battle_entry(self) -> bool:
        """当前 fresh frame 是否**确实已进入一场新的战斗**（准备页 / 战斗进行页）——
        `_fire_again()` 的 positive success 判据。

        **不是** `GeneralBattle.is_in_battle()`：那是「准备 + 战斗 + 结果 + 奖励」整个战斗
        生命周期 detector，OR 里含失败横幅 `I_FALSE`、胜负横幅 `I_WIN` / `I_DE_WIN`、奖励页
        `I_REWARD` / `I_REWARD_GOLD`。退四首战主动退出后停在失败结算页时 `is_in_battle()` 恒为
        True——会把「还停在上一场失败结果页」误判成「再次挑战已进入下一场战斗」（Level C
        2026-09-08 实测：`Battle result: Lose` 之后没有任何 `Fire again: attempt` / reaction /
        `I_FIRE_AGAIN` 点击，直接 `Fire again: entered battle`，caller 又 `run_general_battle()`
        立即重新识别同一个 result page → 假 battle 循环）。

        这里只取**窄 active-battle-entry positive**：`is_in_prepare()`（`I_BUFF` /
        `I_PREPARE_HIGHLIGHT` / `I_PREPARE_DARK` / `I_PRESET` / `I_PRESET_WIT_NUMBER`）或
        `is_in_real_battle()`（`I_BATTLE_INFO`）——两者都是 GeneralBattle 已有的窄 detector、
        都不含 result / reward marker。只读当前帧：不截图 / 不点击 / 不 sleep。
        `GeneralBattle.is_in_battle()` 本体及其它 consumer 不动。
        """
        return self.is_in_prepare(False) or self.is_in_real_battle(False)

    def _fire_again(self) -> bool:
        """**退四内部**失败结算页点「再次挑战」直到正向确认重新进入战斗。

        与 `fire()` 同一 FIRE Contract，但 positive success 用**窄 active-battle-entry 判据**
        `_is_active_battle_entry()`（准备 / 战斗进行页），**不用**含 result / reward marker 的
        `is_in_battle()`——失败结果页 `I_FALSE` 命中会让 `is_in_battle()` 恒 True，把「仍在失败
        结果页」误判成「已进入下一场战斗」。不再以「`I_FIRE_AGAIN` 消失」单独判成功；每次真实
        attempt 独立采样 `REACTION_FIRE` → `sleep` → fresh screenshot → 二次确认「再次挑战」仍在
        → 点击；post-click 走 `_wait_again_entered_battle()` 三态（battle / failure_page /
        transition-unknown）。有限 `RR_AGAIN_MAX_TRIES` + 有限 `Timer(RR_AGAIN_TIMEOUT)`，用尽
        仍未进入战斗返回 False（由 `run()` 退四路径改走刷新）。

        Level C 2026-09-11 实测修复：reaction 后 fresh screenshot 若发现 `I_FIRE_AGAIN` 已消失，
        同样先走一次 `_wait_again_entered_battle()` 有界确认再决定 success / 下一 attempt——此前
        这里是裸 `continue`，在非最后一次 attempt 靠下一轮循环顶部的 `_is_active_battle_entry()`
        隐式补一次确认掩盖了问题，但**最后一次 attempt** 没有下一轮，若此刻恰好是「按钮已消失、
        `page_battle_prepare` marker 尚未渲染完成」的过渡帧，会直接耗尽 attempt 判超时，任务遗留
        在已经成功进入的 `page_battle_prepare`。

        「不再提示」复选框 `I_SHOW_AGAIN` / 共享确认弹窗 `I_FRESH_ENSURE` 是失败结果流程的中间
        点击（无 reaction），先点掉再判「再次挑战」按钮。**只用于退四内部**，普通目标失败绝不调用。

        :return: True 已进入战斗；False 有限重试 / 超时仍未进入
        """
        self.wait_until_appear(self.I_FIRE_AGAIN, wait_time=RR_AGAIN_TIMEOUT)
        self.device.click_record_clear()
        timeout_timer = Timer(RR_AGAIN_TIMEOUT).start()
        for attempt in range(1, RR_AGAIN_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            # 正向确认：已进入一场新战斗（窄 detector，失败结果页 I_FALSE 不算）
            if self._is_active_battle_entry():
                logger.info('Fire again: entered battle')
                return True
            # 弹窗 / 复选框先点掉（失败结果流程的中间点击、无 reaction）
            if self.appear_then_click(self.I_SHOW_AGAIN, interval=2):
                continue
            if self.appear_then_click(self.I_FRESH_ENSURE, interval=2,
                                      confirm_delay=RR_AGAIN_CONFIRM_DELAY):
                continue
            # 「再次挑战」未就绪：有界等一个决定性状态，不在过渡帧乱点
            if not self.appear(self.I_FIRE_AGAIN, threshold=0.8):
                state = self._wait_again_entered_battle()
                if state == 'battle':
                    logger.info('Fire again: entered battle')
                    return True
                # 'failure_page'（仍在失败页，下一 attempt 顶端会点）/ 'timeout'（过渡 / 未知，不点）
                continue
            # 「再次挑战」就绪 → 每 attempt 独立 reaction → fresh screenshot → 二次确认 → click
            again_delay = random_delay(*REACTION_FIRE)
            logger.info(f'Fire again: attempt {attempt}, reaction {again_delay:.2f}s')
            sleep(again_delay)
            self.screenshot()
            if self._is_active_battle_entry():
                return True
            if not self.appear(self.I_FIRE_AGAIN, threshold=0.8):
                # reaction 期间按钮消失 ≠ 立即判失败：可能正处于「已点过、正在切去下一场」的过渡帧
                # （尤其最后一次 attempt，没有下一轮循环顶部的隐式重新确认）。与点击前未就绪分支
                # 同样有界等一个决定性状态，再决定 success / 进入下一 attempt。
                logger.info('Fire again: button gone during reaction, re-evaluate')
                state = self._wait_again_entered_battle()
                if state == 'battle':
                    logger.info('Fire again: entered battle')
                    return True
                continue
            self.appear_then_click(self.I_FIRE_AGAIN, interval=0, threshold=0.8)
            state = self._wait_again_entered_battle()
            if state == 'battle':
                logger.info('Fire again: entered battle after click')
                return True
            # 'failure_page' / 'timeout' → 进入下一 attempt
        logger.warning('Fire again: bounded retry / timeout without entering battle')
        return False

    def _wait_again_entered_battle(self, timeout: float = RR_AGAIN_POST_CLICK_TIMEOUT) -> str:
        """「再次挑战」post-click / 未就绪时的有界状态轮询，**不点任何坐标**：

        - `'battle'`：`_is_active_battle_entry()`（准备 / 战斗进行页的窄 detector）—— 唯一
          positive success，**不用** `is_in_battle()`（含 `I_FALSE` / 奖励 marker，会把失败结果
          页误判成已进战斗）；
        - `'failure_page'`：仍在失败结算页（`I_FIRE_AGAIN` / `I_FRESH_ENSURE` 可见）—— retryable，
          允许下一 attempt；
        - `'timeout'`：整个 timer 内一直是「按钮消失、active battle 未出现」的过渡 / 未知帧 ——
          **既不当 success 也不当 immediate failure**，timer 内持续等。

        复用 GeneralBattle 已有的窄 detector（`is_in_prepare` / `is_in_real_battle`）+ 已有失败页
        marker，不新造 page detector，不改 `is_in_battle()`。
        """
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            if self._is_active_battle_entry():
                return 'battle'
            if self.appear(self.I_FIRE_AGAIN, threshold=0.8) or self.appear(self.I_FRESH_ENSURE):
                return 'failure_page'
            # 否则 = TRANSITION_UNKNOWN：什么都不点，继续等
        return 'timeout'

    @cached_property
    def false_roi(self) -> list:
        width = 86
        height = 64
        x1 = 386
        x2 = 714
        x3 = 1047
        y1 = 143
        y2 = 277
        y3 = 414
        return [
            [x1, y1, width, height],  # 左上角
            [x2, y1, width, height],
            [x3, y1, width, height],
            [x1, y2, width, height],  # 左中
            [x2, y2, width, height],
            [x3, y2, width, height],
            [x1, y3, width, height],  # 左下
            [x2, y3, width, height],
            [x3, y3, width, height],
        ]

    @cached_property
    def false_image(self):
        return RuleImage(roi_front=(0 ,0, 63, 32),
                         roi_back=(0, 0, 100, 100),
                         threshold=0.8,
                         method="Template matching",
                         file="./tasks/RyouToppa/dev/loser_sign_1.png")


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device
    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)

    t.run()
