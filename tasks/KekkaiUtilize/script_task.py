# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
import time
from cached_property import cached_property
from dataclasses import dataclass, field
from datetime import timedelta, datetime
from enum import Enum

from module.base.timer import Timer
from module.atom.image_grid import ImageGrid
from module.logger import logger
from module.exception import TaskEnd, GamePageUnknownError, GameStuckError

from tasks.GameUi.game_ui import GameUi
from tasks.KekkaiUtilize.page import page_guild_realm, page_guild_realm_utilize, page_guild_realm_growth, \
    page_friend_utilize, page_gr_ap_box, page_gr_exp_jug
from tasks.Utils.config_enum import ShikigamiClass
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets
from tasks.KekkaiUtilize.config import UtilizeRule, SelectFriendList
from tasks.KekkaiUtilize.utils import CardClass, target_to_card_class, \
    FISH_REWARD_TIERS, TAIKO_REWARD_TIERS, lower_reward_tier
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.GameUi.page import page_main, page_guild
from module.base.utils import point2str
from module.base.utils.random import random_delay, random_int
from module.base.frame_wait import wait_for_changed_and_stable
from module.click_pipeline import FinalPoint, execute_single_click
from module.device.touch_swipe_model import TouchSwipeModel
from tasks.KekkaiUtilize.selected_anchor import detect_selected_anchor
from tasks.KekkaiUtilize.frame_projection import actual_scroll_dy_px, dedup_by_projection
from tasks.KekkaiUtilize.scheduling import is_in_quiet_window, normalize_for_quiet_window

""" 结界蹭卡 """


class PassResult(str, Enum):
    """单个搜索 PASS 的结果。"""
    HIT = 'hit'                        # 命中当前阈值：当前 UI 已选中的卡就是目标
    PASS_MISS = 'pass_miss'           # 扫到列表底部但没有达标候选：换下一个 PASS
    FINAL_USE_LAST = 'final_use_last'  # 最后一个 PASS 扫到底：直接用最后一次点击、仍保持选中的候选
    ABORT = 'abort'                   # 超时 / 达到滑动上限 / 页面异常：交外层按失败重试


@dataclass
class SearchPass:
    """一次单向（TOP→BOTTOM）好友结界卡搜索的完整描述。

    切换同区 / 跨区分组后，游戏会把好友列表重新滚回顶部，所以每个 PASS 都只需要向下扫描，
    不存在反向 swipe / 蛇形搜索 / TOP marker。
    """
    friend_group: SelectFriendList        # 本 PASS 扫描哪个好友分组
    stars: frozenset                       # 允许的星级集合：{6} 或 {5, 6}
    threshold_map: dict                    # {'斗鱼': int, '太鼓': int}，本 PASS 的收益阈值
    final_fallback: bool                   # 是否是最后一个 PASS（到底后用最后点击的候选兜底）
    targets: ImageGrid = field(compare=False)  # 本 PASS 用于 find_everyone 的结界卡模板


class ScriptTask(GameUi, ReplaceShikigami, KekkaiUtilizeAssets):
    utilize_add_count = 0
    utilize_failed_count = 0
    utilize_terminal_failure = False
    utilize_found_eligible_card = False
    utilize_current_group_has_eligible_card = False
    utilize_current_group_scan_completed = False
    utilize_lazy_mode_active = False

    # 同类型、同星级结界卡的最高奖励。达到最高值后，本轮不再打开同档卡片。
    CARD_TIER_INFO = {
        CardClass.TAIKO4: ('太鼓', 4, 59),
        CardClass.TAIKO5: ('太鼓', 5, 67),
        CardClass.TAIKO6: ('太鼓', 6, 76),
        CardClass.FISH4: ('斗鱼', 4, 118),
        CardClass.FISH5: ('斗鱼', 5, 134),
        CardClass.FISH6: ('斗鱼', 6, 151),
    }
    # 寄养剩余时间 OCR 的兜底：识别失败或数值明显不合理时，按固定间隔重试，
    # 而不是把 next_run 设成当前时刻。
    UTILIZE_RES_TIME_FALLBACK = timedelta(minutes=5)
    UTILIZE_RES_TIME_MAX = timedelta(hours=12)
    # 切换好友分组的总超时，超时视为页面异常。
    SWITCH_FRIEND_LIST_TIMEOUT = 20
    # 好友结界卡列表的下划参数。起点在列表安全区内随机取。
    SWIPE_START_X_RANGE = (340, 600)
    SWIPE_START_Y_RANGE = (500, 565)
    # 怠惰路径 / 非 minitouch 回退（`perform_swipe_action` → `swipe_adb`）的固定位移，本轮不动。
    SWIPE_DISTANCE = 416
    # K2（2026-09-07）：标准 PASS 的 minitouch 路径改成每次 `_perform_search_swipe()` 独立随机
    # 一个「较短」commanded finger 位移。Level C 几何：好友结界卡列表一屏约 4 格、相邻卡片中心
    # 间距 row_pitch ≈ 106px（y≈220/326/432/538）；旧 416px ≈ 3.9 格、接近整屏，加上游戏列表
    # 惯性会更远 → 严重跨项漏卡。本轮只控制 commanded 位移，不做惯性补偿 / 实际 scroll dy 测量（那是 K4）。
    KEKKAI_ROW_PITCH_PX = 106
    # commanded finger 位移随机范围（**provisional，Level C 分档调参**）：
    #   首档 (212, 265)（≈2.0~2.5 row_pitch）—— 2026-09-07 首次 Level C 实测「一次内容仍滚 >4 格」，
    #                    证明 commanded finger distance ≠ actual content scroll（列表惯性放大），判定过大。
    #   当前 (140, 180)（≈1.3~1.7 row_pitch 的手指位移）—— 整体降约 1/3；受惯性放大预计实际仍滚 2~3 格，
    #                    目标是相邻两屏至少保留 1~2 格重叠（A B C D → B C D E / C D E F），避免几乎无重叠的大跨步。
    #   若二次 Level C 仍实际 >3 格，下一档再缩到 (110, 150)——单变量分阶段，本轮不直接跳第二档。
    # 只调这个 consumer 参数，不改 TouchSwipeModel / K1 起点范围 / K3 settle。
    SWIPE_DISTANCE_RANGE = (140, 180)
    # 轻微整体斜度（2026-09-07，仅标准 PASS + minitouch）：旧 `end_x == start_x` 让宏观轨迹接近
    # 严格竖直（TouchSwipeModel 只在中段给轻微曲率）。这里每次 `_perform_search_swipe()` 独立随机
    # 一个小幅横向偏移，只作用于**最终 end_x**（不给每个 MOVE 点加噪声）：有的轻微左斜、有的轻微
    # 右斜、有的接近竖直，整体仍明确向上 swipe。`end_x` 再夹回起点安全区 `SWIPE_START_X_RANGE`
    # （不扩大 start_x 范围）：start_x 靠边界时偏移被有界裁掉、退化成竖直，不会滑出可接受区。
    # provisional，需 Level C 调整。纵向距离 `SWIPE_DISTANCE_RANGE` 不因本轮再动。
    SWIPE_LATERAL_OFFSET_RANGE = (-12, 12)

    # K3（2026-09-07，仅标准 PASS + minitouch）：swipe settle 从固定 `time.sleep(2)` 改成
    # FrameWait —— baseline（swipe 前帧）→ swipe → 等「相对 baseline **changed 且 stable**」。
    # ROI 只盯好友结界卡列表滚动主体（card-column，取 `I_U_*_6` / `I_U_EMPTY_CARD` 的 `roi_back`
    # 包络：x≈530~620、y≈156~606；排除右侧详情栏 / tab / 底部 UI / OCR 数字，避免污染 changed·stable）。
    # 格式 = `(x1, y1, x2, y2)`（frame_state 口径，非 (x,y,w,h)）。
    SWIPE_WAIT_ROI = (525, 155, 620, 610)
    # 以下 3 个阈值 + timeout 是 K3 **provisional 首版，需 Level C 调整**（用 wait 日志的
    # `elapsed` 分布看旧 `sleep(2)` 实际通常要 0.4/0.8/1.3s…）。
    SWIPE_WAIT_CHANGED_THRESHOLD = 0.10   # 列表滚 2~2.5 格，card-column 变化远超 10%
    SWIPE_WAIT_STABLE_THRESHOLD = 0.02    # 停稳后相邻帧差异 < 2%
    SWIPE_WAIT_STABLE_FRAMES = 3          # 连续 3 帧相邻安静
    SWIPE_WAIT_TIMEOUT = 3.0             # 有限超时（旧固定等待 2s，惯性可能略长，3s 封顶）
    # 两次取帧之间额外 sleep 的秒数（检测采样 pacing）。FrameWait 全局默认 `poll_interval=0.0`
    # ——那是给「frame_provider 自带节流」的场景。这里**显式覆盖成正值**：好友列表 swipe 后的
    # 惯性微滚，可能让相邻两帧差异 < `SWIPE_WAIT_STABLE_THRESHOLD`；零间隔高速轮询下连续
    # `SWIPE_WAIT_STABLE_FRAMES` 帧就提前判 stable（甚至连抓到同一渲染帧）。加一档 pacing 让这
    # 3 帧跨越更长真实时间窗、更接近「惯性真的停了」。叠在 `device.screenshot` 自带的
    # `_screenshot_interval`（~0.1s）之上，**不是恢复固定 `sleep(2)`**（settle 仍以 changed&stable
    # 为准、命中即返回）。**provisional，需 Level C 调整**（`_screenshot_interval` 已够 → 可回 0；
    # 惯性帧仍 alias → 调大）。不动上面 4 个判定阈值。
    SWIPE_WAIT_POLL_INTERVAL = 0.15

    # 单个搜索 PASS 的安全边界。到底靠 I_U_EMPTY_CARD 判定；这里的两条只是「安全中止」，
    # 达到即视为页面异常/卡死，不当作「已经扫到列表底部」。
    SEARCH_MAX_SWIPES = 20
    SEARCH_PASS_TIMEOUT = 120
    # 点击一张候选后等右侧详情栏刷新（换成语义等待属 Level C，本轮沿用固定等待）。
    DETAIL_LOAD_WAIT = 2

    # K4（2026-09-07，解冻）：用 `I_IS_SELECTED` 发光竖线做**动态锚点**，测「上一稳定屏 → 当前
    # 稳定屏」的**实际**列表滚动像素 `actual_scroll_dy`（= selected anchor before_y − after_y，
    # **不是** commanded 位移 `SWIPE_DISTANCE_RANGE`——Level C 已确认 commanded ≠ actual）；把上一
    # 屏 `find_everyone` 候选按该像素向上投影到当前屏，和当前屏 `find_everyone` 结果做「同模板 +
    # bbox 真实几何交集」一对一去重，只把真正新进入的候选交给 D017 业务逻辑处理。
    # 测量不可靠（首屏无选中 / 多匹配 / dy 非法 / glow 被边界裁切）→ 完全退回当前完整扫描，
    # 绝不因 K4 漏卡。只 previous↔current 一帧对一帧、无持久历史。K3 失败仍 ABORT；BOTTOM 仍只
    # 认 I_U_EMPTY_CARD；FINAL_USE_LAST / clicked_any 语义不变。K2 / K3 一行不改。provisional，
    # 需 Level C（当前好友卡样本不足，本轮只做 Level A/B）。`K4_ENABLED` 是一处 kill switch。
    K4_ENABLED = True
    # 当前屏卡列可见 Y 范围 `(top, bottom)`：投影后中心出此范围的上一屏候选视为已滚出屏、忽略。
    # 取 card-column（`I_U_*_6` / `I_U_EMPTY_CARD` 的 roi_back）纵向包络。provisional。
    K4_LIST_VISIBLE_Y = (156, 606)

    def run(self):
        # Scheduler v1 入口守卫：当前处于静默窗口则直接重排 next_run 并结束，不进入任何
        # 页面 / OCR / 业务动作——即使 scheduler 意外在静默窗口内唤醒本任务也能立即拒绝。
        if self._guard_quiet_window():
            raise TaskEnd
        con = self.config.kekkai_utilize.utilize_config
        self.utilize_add_count = 0
        self.utilize_failed_count = 0
        self.utilize_terminal_failure = False
        self.utilize_found_eligible_card = False
        self.utilize_current_group_has_eligible_card = False
        self.utilize_current_group_scan_completed = False
        self.utilize_lazy_mode_active = False
        if con.utilize_enable and con.lazy_mode:
            lazy_roll = random_delay(0.0, 1.0)
            self.utilize_lazy_mode_active = (
                lazy_roll < con.lazy_mode_weight
            )
            logger.info(
                '怠惰模式随机判定: '
                f'roll={lazy_roll:.4f}, '
                f'weight={con.lazy_mode_weight:.4f}, '
                f'active={self.utilize_lazy_mode_active}'
            )
        # 进入寮结界
        self.goto_page(page_guild_realm)
        # 育成界面去蹭卡
        if con.utilize_enable:
            if not self.check_utilize_add():
                # 正常返回而非抛出 TaskEnd，使调度器把本轮记为失败；
                # 下次运行时间已由失败处理设置为 10 分钟后。
                return

        # 查看育成满级：开关关闭时完全跳过，不检测、不卸下、不切换、不补位
        if con.auto_replace_max_level:
            self.check_max_lv(con.shikigami_class, con.auto_fill)
        # 检查是否有蹭卡收获 是否收取
        if con.utilize_harvest:
            self.check_utilize_harvest()
        # 收体力盒子或者是经验盒子
        self.check_box_ap_or_exp(con.box_ap_enable, con.box_exp_enable, con.box_exp_waste)

        self.receive_guild_assets(con.harvest_guild_max_times)
        if not con.utilize_enable:
            self.set_next_run(task='KekkaiUtilize', finish=True, success=True)
        self.goto_page(page_main)
        raise TaskEnd

    # ------------------------------------------------------------------------------------
    # Scheduler v1：静默窗口归一化 + 短期 retry cooldown 随机化。
    #
    # 契约（详见 Inventory 报告 + 本轮实施报告）：
    #   正常寄养：OCR 剩余时间 → min_run_interval 地板 → _normalize_quiet_target → set_next_run
    #   短期 retry：_build_retry_target（随机 cooldown） → _schedule_target（内部同一次
    #               normalize） → set_next_run
    # 5 个 helper 只负责「候选值怎么来 / 怎么被静默窗口归一化 / 怎么写回」，不碰任何
    # OCR / 页面 / 好友筛选逻辑；quiet window 判定与归一化算法在 `scheduling.py`
    # 保持纯函数，这里只负责从 config 取参数、从统一随机源采样抖动秒数。
    # ------------------------------------------------------------------------------------

    def _is_in_quiet_window(self, now: datetime = None) -> bool:
        """当前（或指定）时刻是否处于配置的静默窗口内。"""
        sched = self.config.kekkai_utilize.scheduler
        if not sched.quiet_window_enable:
            return False
        now = now or datetime.now()
        return is_in_quiet_window(now.time(), sched.quiet_start, sched.quiet_end)

    def _quiet_jitter_seconds(self) -> int:
        """从项目统一随机源（SystemRandom）采样一次静默窗口恢复抖动（秒）。"""
        sched = self.config.kekkai_utilize.scheduler
        return random_int(sched.quiet_resume_jitter_min * 60, sched.quiet_resume_jitter_max * 60)

    def _normalize_quiet_target(self, candidate: datetime) -> datetime:
        """candidate → 静默窗口归一化。不调用 `set_next_run`，只算最终应该写入的时间。

        candidate 落在窗内才会采样随机抖动；不落在窗内 / 窗口关闭时原样返回 candidate，
        不产生任何随机数（保持在不需要归一化的多数情况下零副作用）。
        """
        sched = self.config.kekkai_utilize.scheduler
        if not sched.quiet_window_enable or not is_in_quiet_window(
                candidate.time(), sched.quiet_start, sched.quiet_end):
            return candidate
        return normalize_for_quiet_window(
            candidate,
            enable=sched.quiet_window_enable,
            quiet_start=sched.quiet_start,
            quiet_end=sched.quiet_end,
            jitter_seconds=self._quiet_jitter_seconds(),
        )

    def _build_retry_target(self, now: datetime = None) -> datetime:
        """短期 retry candidate：now + 随机 cooldown（`cooldown_min`~`cooldown_max` 分钟）。

        只负责候选值本身，不做静默窗口判断——调用方统一交给 `_schedule_target` 归一化。
        """
        sched = self.config.kekkai_utilize.scheduler
        now = now or datetime.now()
        cooldown_seconds = random_int(sched.cooldown_min * 60, sched.cooldown_max * 60)
        return now + timedelta(seconds=cooldown_seconds)

    def _schedule_target(self, candidate: datetime) -> datetime:
        """统一出口：candidate → 静默窗口归一化 → `set_next_run(target=final, server=False)`。

        `server=False`——候选值已经是完整算好的最终时间，不需要 `Config.task_delay()`
        再叠一层 `server_update` jitter（见本轮实施报告 §10 的逐出口核对）。
        """
        final = self._normalize_quiet_target(candidate)
        self.set_next_run(task='KekkaiUtilize', target=final, server=False)
        return final

    def _schedule_retry(self, reason: str) -> datetime:
        """短期失败 retry 统一出口：一个 owner、一个范围、一次随机——避免各分支各自
        调 `random_int` 导致 cooldown 范围漂移。"""
        candidate = self._build_retry_target()
        final = self._schedule_target(candidate)
        logger.info(
            f'KekkaiUtilize 短期重试: {reason}, '
            f'final_next_run={final.strftime("%Y-%m-%d %H:%M:%S")}'
        )
        return final

    def _guard_quiet_window(self) -> bool:
        """`run()` 入口守卫。当前处于静默窗口 → 直接把 next_run 重排到窗口结束 + 抖动、
        `return True`（caller 应立即 `raise TaskEnd`，不进入任何业务）；否则 `return False`。
        """
        if not self._is_in_quiet_window():
            return False
        final = self._schedule_target(datetime.now())
        logger.info(f'KekkaiUtilize 当前处于静默窗口，next_run 推迟至 {final.strftime("%Y-%m-%d %H:%M:%S")}')
        return True

    def receive_guild_assets(self, max_tries: int = 3):
        """收取寮奖励 会自动前往寮界面探测, 最后会退出到庭院"""
        for i in range(1, max_tries+1):
            self.goto_page(page_guild)
            ret = self.check_and_get_guild_rewards()
            logger.info(f'第[{i}]次收取寮奖励: {ret}')
            self.goto_page(page_main)
            # 一个都没收到说明已经没有可收取项，不必再往返
            if not ret:
                break

    def check_utilize_add(self):
        con = self.config.kekkai_utilize.utilize_config
        while 1:
            self.utilize_add_count += 1
            if self.utilize_add_count >= 5:
                if not self.utilize_found_eligible_card:
                    target_name = {
                        UtilizeRule.TAIKO: '太鼓',
                        UtilizeRule.FISH: '斗鱼',
                        UtilizeRule.DEFAULT: '太鼓或斗鱼',
                    }.get(con.utilize_rule, '目标结界卡')
                    message = f'未检测到四星及以上{target_name}, 稍后重试'
                    logger.warning(message)
                    self.push_notify(content=message)
                else:
                    logger.warning('已检测到四星及以上结界卡，但未能完成选择，稍后重试')
                self._schedule_retry('5 次尝试仍未找到合格结界卡')
                return True

            # 无论收不收到菜，都会进入看看至少看一眼时间还剩多少
            time.sleep(0.5)
            # 进入育成界面
            self.goto_page(page_guild_realm_growth)
            self.screenshot()
            if not self.appear(self.I_UTILIZE_ADD):
                remaining_time = self.O_UTILIZE_RES_TIME.ocr(self.device.image)
                logger.info(f'Utilize remaining time: {remaining_time}')
                # ocr_duration 解析失败时返回 timedelta(0)，与真的剩余 0 无法区分。
                # 直接拿来算 next_run 会把下次运行设成当前时刻，导致任务被立即
                # 重复调度形成热循环；识别出异常大的值同样不可信。两种情况都按
                # 固定兜底间隔重试。
                if (not isinstance(remaining_time, timedelta)
                        or remaining_time <= timedelta(0)
                        or remaining_time > self.UTILIZE_RES_TIME_MAX):
                    logger.warning(
                        f'寄养剩余时间识别异常({remaining_time})，'
                        f'按{self.UTILIZE_RES_TIME_FALLBACK}兜底重试'
                    )
                    remaining_time = self.UTILIZE_RES_TIME_FALLBACK
                # 已经蹭上卡了，设置下次蹭卡时间  # 减少30秒
                # remaining_time = remaining_time - timedelta(seconds=30)
                # 正常寄养调度契约（Scheduler v1，不被短期 retry cooldown 取代）：
                # OCR 剩余时间 → min_run_interval 地板 → 静默窗口归一化 → 写回。
                next_time = datetime.now() + remaining_time
                min_interval = con.min_run_interval
                if min_interval and min_interval.total_seconds() > 0:
                    next_time = max(next_time, datetime.now() + min_interval)
                self._schedule_target(next_time)
                return True
            # U3（2026-09-14）：导航失败必须阻断寄养业务——`goto_page` 失败时按契约要么抛
            # `GamePageUnknownError`/`GameStuckError`，要么（防御性地，兼容未来/测试注入的
            # bool 返回）给出假值；两种信号统一收敛成 `reached_utilize_page`，一旦不为真就
            # 禁止 `run_utilize(...)` 及其后续业务，复用既有终态失败出口（`_schedule_retry`
            # + `utilize_terminal_failure`），不新增第二套重试机制，也不重复计入
            # `utilize_add_count`/`utilize_failed_count`。
            try:
                reached_utilize_page = self.goto_page(page_guild_realm_utilize)
            except (GamePageUnknownError, GameStuckError) as error:
                reached_utilize_page = False
                logger.warning(
                    f'KekkaiUtilize navigation failed: target=page_guild_realm_utilize ({type(error).__name__})'
                )
            if not reached_utilize_page:
                logger.warning('KekkaiUtilize navigation failed, skip utilize business')
                self._schedule_retry('导航到好友结界寄养页失败')
                self.utilize_terminal_failure = True
                return False
            # 开始执行寄养
            self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order)
            if self.utilize_terminal_failure:
                return False
            self.goto_page(page_guild_realm_growth)

    def check_max_lv(self, shikigami_class: ShikigamiClass = ShikigamiClass.N, auto_fill: bool = False):
        """
        在结界界面，进入式神育成，检查是否有满级的，如果有就换下一个
        退出的时候还是结界界面
        :return:
        """
        self.goto_page(page_guild_realm_growth)
        if auto_fill:
            self.ui_click(self.I_AUTO_FILL, self.I_REMOVE_ALL, interval=1.5)
            self.goto_page(page_guild_realm)
            return
        if self.appear(self.I_RS_LEVEL_MAX):
            # 存在满级的式神
            logger.info('Exist max level shikigami and replace it')
            self.unset_shikigami_max_lv()
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)
        else:
            logger.info('No max level shikigami')
        if self.detect_no_shikigami():
            logger.warning('There are no any shikigami grow room')
            self.switch_shikigami_class(shikigami_class)
            self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)

        # 回到结界界面
        self.goto_page(page_guild_realm)

    def check_and_get_guild_rewards(self) -> bool:
        """
        在寮的主界面 检查是否有奖励可收取 资金/体力/抽奖/...
        如果有就顺带收取
        :return: 任意一个收取了就返回True, 一个没收返回False
        """
        harvest_dict: dict[str, bool] = {
            'ap': False, 'gold': False, 'lottery': False
        }
        timer_check = Timer(2).start()
        while True:
            self.screenshot()
            if self.ui_reward_appear_click():
                timer_check.reset()
                continue
            if timer_check.reached():
                return False
            # 关闭展开的寮活动横幅
            if self.appear_then_click(self.I_GUILD_EXPAND):
                timer_check.reset()
                continue
            # 资金收取确认
            if self.appear_then_click(self.I_GUILD_ASSETS_RECEIVE, interval=1):
                time.sleep(1)
                harvest_dict['gold'] = True
                timer_check.reset()
                continue
            # 收资金
            if self.appear_then_click(self.I_GUILD_ASSETS, interval=1.5, threshold=0.6):
                timer_check.reset()
                harvest_dict['gold'] = True
                continue
            # 收体力
            if self.appear_then_click(self.I_GUILD_AP, interval=1):
                # 等待1秒，看到获得奖励
                time.sleep(1)
                harvest_dict['ap'] = True
                timer_check.reset()
                self.device.click_record_clear()
                continue
            # 抽奖
            if self.appear(self.I_GUILD_LOTTERY, interval=1):
                self.guild_lottery()
                harvest_dict['lottery'] = True
                timer_check.reset()
                self.device.click_record_clear()
                continue
            if any(harvest_dict.values()) and not self.appear(self.I_UI_REWARD):
                return True
        return False

    def guild_lottery(self):
        """寮抽奖"""
        timeout_timer = Timer(4).start()
        while not timeout_timer.reached():  # 进入抽奖界面
            self.screenshot()
            if self.appear(self.I_GUILD_LOTTERY) and \
                    self.ui_click_until_appear_or_timeout(self.I_GUILD_LOTTERY, self.I_CHECK_GUILD_LOTTERY,
                                                          interval=1.5, timeout=7):  # 漫长的散步
                break
        timeout_timer.reset()
        while not timeout_timer.reached():
            self.screenshot()
            self.ui_reward_appear_click()
            if self.appear(self.I_GUILD_LOTTERY_SPECIAL_REWARD, interval=1):  # 特殊奖励
                self.click(self.C_UI_REWARD)
                continue
            if self.appear(self.I_KU_CHECK_CAN_LOTTERY, interval=3):  # 开始抽奖
                self.swipe(self.S_GUILD_LOTTERY)
                timeout_timer.reset()
                continue
        self.appear_then_click(self.I_UI_BACK_YELLOW)

    def check_box_ap_or_exp(self, ap_enable: bool = True, exp_enable: bool = True, exp_waste: bool = True) -> bool:
        """
        顺路检查盒子
        :param exp_waste:
        :param ap_enable:
        :param exp_enable:
        :return:
        """

        def _harvest_ap_box():
            """收取体力"""
            timer_ap = Timer(6)
            timer_ap.start()
            while True:
                if timer_ap.reached():
                    logger.warning('Extract ap box done')
                    break
                self.screenshot()
                if self.appear(self.I_UI_REWARD):
                    self.ui_click_until_smt_disappear(self.C_UI_REWARD, self.I_UI_REWARD, interval=1)
                    logger.info('Reward box')
                    break
                if self.appear_then_click(self.I_AP_EXTRACT, interval=2):
                    continue
            return True

        def _harvest_exp_jug():
            time_exp = Timer(12)
            time_exp.start()
            max_tries = random_int(2, 3)
            while True:
                if time_exp.reached():
                    logger.warning('Extract exp jug done')
                    break
                if max_tries <= 0:
                    logger.info('Exp maybe already full, ocr failed, exit')
                    break
                self.screenshot()
                # 如果出现结界皮肤， 表示收取好了
                if self.get_current_page() == page_guild_realm:
                    break
                # 如果出现收取确认，表明进入到了有满级的
                if self.appear(self.I_UI_CONFIRM) and self.appear(self.I_UI_CANCEL):
                    target_button = self.I_UI_CONFIRM if exp_waste else self.I_UI_CANCEL
                    self.ui_click_until_disappear(target_button)
                    break
                if self.appear(self.I_EXP_EXTRACT, interval=1):
                    # 如果达到今日领取的最大，就不领取了
                    cur, res, total = self.O_BOX_EXP.ocr(self.device.image)
                    if total <= 0:
                        logger.warning('Exp box OCR no data, retry')
                        continue
                    if cur == total:
                        logger.info('Exp box reach max do not collect')
                        break
                    self.click(self.I_EXP_EXTRACT)
                    max_tries -= 1
            return True

        self.screenshot()
        if ap_enable and self.appear(self.I_BOX_AP):
            self.goto_page(page_gr_ap_box)
            _harvest_ap_box()
            self.goto_page(page_guild_realm)
        if exp_enable and (self.appear(self.I_BOX_EXP) or self.appear(self.I_BOX_EXP_MAX)):
            self.goto_page(page_gr_exp_jug)
            _harvest_exp_jug()
            self.goto_page(page_guild_realm)
        return True

    def check_utilize_harvest(self) -> bool:
        """
        在寮结界界面检查是否有寄养收获
        :return: 如果没有返回False, 如果有就收菜返回True
        """
        self.screenshot()
        appear = self.appear(self.I_UTILIZE_EXP)
        if not appear:
            logger.info('No utilize harvest')
            return False

        # 收获
        self.ui_get_reward(self.I_UTILIZE_EXP)
        return True

    def switch_friend_list(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER) -> None:
        """
        切换不同的服务区
        :param friend:
        :raise GamePageUnknownError: 超时仍未切到目标分组
        """
        logger.info('Switch friend list to %s', friend)
        if friend == SelectFriendList.SAME_SERVER:
            check_image = self.I_UTILIZE_FRIEND_GROUP
        else:
            check_image = self.I_UTILIZE_ZONES_GROUP

        timer_click = Timer(1)
        timer_click.start()
        # 目标分组图标一直识别不到时不能无限点击，本方法在整条寄养链路上
        # 调用非常频繁，缺少总超时会直接卡死任务。
        timeout = Timer(self.SWITCH_FRIEND_LIST_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear(check_image):
                break
            if timeout.reached():
                message = (
                    f'切换好友分组超时，{self.SWITCH_FRIEND_LIST_TIMEOUT}秒内'
                    f'未识别到[{friend.value}]分组'
                )
                logger.error(message)
                raise GamePageUnknownError(message)
            if timer_click.reached():
                timer_click.reset()
                # L1 执行入口：目标图片未出现时沿用资产 ROI 的 `coord()` 采样一次，
                # 已定坐标以 FinalPoint 交给统一执行器，不新增识别 / 重试
                x, y = check_image.coord()
                execute_single_click(self.device, FinalPoint(x, y), control_name=check_image.name)
        if friend == SelectFriendList.DIFFERENT_SERVER:
            time.sleep(1)
        time.sleep(0.5)

    @cached_property
    def lazy_scan_targets(self) -> ImageGrid:
        """怠惰模式用于浏览位置的全部四星以上资源卡。"""
        return ImageGrid([
            self.I_U_FISH_6, self.I_U_TAIKO_6,
            self.I_U_FISH_5, self.I_U_TAIKO_5,
            self.I_U_FISH_4, self.I_U_TAIKO_4,
        ])

    # 单向分区搜索：星级 → 结界卡模板。第一阶段只放 6★，第二阶段放 5★+6★。
    # 真实奖励档位与星级不是一一对应（6★斗鱼也可能只有 118），所以第二阶段必须 5/6★ 都扫。
    _STAR_TEMPLATE_ATTR = {
        (6, '斗鱼'): 'I_U_FISH_6', (6, '太鼓'): 'I_U_TAIKO_6',
        (5, '斗鱼'): 'I_U_FISH_5', (5, '太鼓'): 'I_U_TAIKO_5',
    }

    def _rule_card_types(self) -> tuple[str, ...]:
        """当前 utilize_rule 允许的卡种。"""
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        if rule == UtilizeRule.TAIKO:
            return ('太鼓',)
        if rule == UtilizeRule.FISH:
            return ('斗鱼',)
        if rule == UtilizeRule.DEFAULT:
            return ('斗鱼', '太鼓')
        logger.error('Unknown utilize rule')
        raise ValueError('Unknown utilize rule')

    def _pass_targets(self, stars) -> ImageGrid:
        """按星级集合 + 当前 utilize_rule 组出本 PASS 用于 find_everyone 的模板网格。"""
        images = []
        for star in sorted(stars, reverse=True):          # 6★ 模板排前面，仅日志可读，不影响 y 排序
            for card_type in self._rule_card_types():
                images.append(getattr(self, self._STAR_TEMPLATE_ATTR[(star, card_type)]))
        return ImageGrid(images)

    def _card_type_matches_rule(self, card_type: str) -> bool:
        """详情 OCR 出来的卡种是否符合当前 utilize_rule。"""
        return card_type in self._rule_card_types()

    def _card_meets_pass(self, card_type: str, card_value: int, search_pass: SearchPass) -> bool:
        """当前详情卡是否满足本 PASS 的收益阈值（按详情 OCR 的卡种取阈值，并要求符合 rule）。"""
        if card_type not in ('斗鱼', '太鼓') or not self._card_type_matches_rule(card_type):
            return False
        threshold = search_pass.threshold_map.get(card_type)
        return threshold is not None and card_value >= threshold

    def _build_search_passes(self, friend: SelectFriendList) -> list[SearchPass]:
        """按「优先分组」生成完整 PASS 序列。

        优先跨区：跨6★HIGH → 同6★HIGH → 降一档 → 跨5/6★LOWER → 同5/6★LOWER(final)
        优先同区：同6★HIGH → 跨6★HIGH → 降一档 → 同5/6★LOWER(final)

        **相邻 PASS 的 `friend_group` 一定不同**（契约，见 `RunSearchGroupSwitchOnlyTest`）。
        `_run_search` 依赖这一点：每个 PASS 前只 `switch_friend_list(该分组)` 切一次即可——
        Level C 已确认「只要 SAME/CROSS 发生实际切换，新进入的分组列表必定从顶部显示」，
        所以全部 TOP→BOTTOM 单向扫描，不需要旧的 `_reset_utilize_friend_list` 回顶 / 预滚。
        最后一个 PASS 自身兼任兜底，没有额外的 fallback 轮次。
        """
        con = self.config.kekkai_utilize.utilize_config
        high = {'斗鱼': con.fish_reward_threshold, '太鼓': con.taiko_reward_threshold}
        lower = {
            '斗鱼': lower_reward_tier(con.fish_reward_threshold, FISH_REWARD_TIERS),
            '太鼓': lower_reward_tier(con.taiko_reward_threshold, TAIKO_REWARD_TIERS),
        }
        cross, same = SelectFriendList.DIFFERENT_SERVER, SelectFriendList.SAME_SERVER
        six, five_six = frozenset({6}), frozenset({5, 6})
        if friend == SelectFriendList.DIFFERENT_SERVER:          # 优先跨区
            specs = [
                (cross, six, high, False),
                (same, six, high, False),
                (cross, five_six, lower, False),
                (same, five_six, lower, True),
            ]
        else:                                                    # 优先同区（默认）
            specs = [
                (same, six, high, False),
                (cross, six, high, False),
                (same, five_six, lower, True),
            ]
        return [
            SearchPass(group, stars, thresholds, final, self._pass_targets(stars))
            for group, stars, thresholds, final in specs
        ]

    def _run_search(self, friend: SelectFriendList) -> bool | None:
        """按 PASS 序列做单向分区搜索。

        每个 PASS 前只 `switch_friend_list(search_pass.friend_group)` 切到目标分组：
        `_build_search_passes` 保证相邻 PASS 的分组一定不同，而 Level C 已确认「只要
        SAME/CROSS 发生实际切换，新进入的分组列表必定从顶部显示」，所以不需要旧的
        `_reset_utilize_friend_list`（滚到底 + 切走再切回）来回顶或预加载。列表的第一次
        滑动只发生在 `_run_search_pass` 的 TOP→BOTTOM 扫描里（`_perform_search_swipe`）。

        :return: True  = 某个 PASS 已选中目标（当前 UI 选中的即目标，可直接进入结界）；
                 None  = 从头到尾没有点开过任何 5/6★ 候选（两个分组都没有可用卡）；
                 False = 见过候选但都没达标，或搜索被安全中止（超时 / 滑动上限 / 页面异常）。
        :raise GamePageUnknownError: 切换好友分组超时，由 run_utilize 捕获按失败处理。
        """
        saw_any_candidate = False
        for search_pass in self._build_search_passes(friend):
            logger.hr(
                f'搜索 PASS: {search_pass.friend_group.value} '
                f'stars={sorted(search_pass.stars)} threshold={search_pass.threshold_map} '
                f'final={search_pass.final_fallback}',
                2,
            )
            self.switch_friend_list(search_pass.friend_group)            # 切到目标分组；实际切换后游戏自动回顶
            result, clicked_any = self._run_search_pass(search_pass)
            saw_any_candidate = saw_any_candidate or clicked_any
            if result in (PassResult.HIT, PassResult.FINAL_USE_LAST):
                return True
            if result == PassResult.ABORT:
                return False
            # PASS_MISS —— 换下一个 PASS
        return False if saw_any_candidate else None

    def _run_search_pass(self, search_pass: SearchPass) -> tuple[PassResult, bool]:
        """单个 PASS：列表已在该分组 TOP，只向下扫描。

        - 命中阈值 → HIT。
        - 到达列表底部（I_U_EMPTY_CARD）：final PASS 且本轮点开过候选 → FINAL_USE_LAST；否则 PASS_MISS。
        - 超时 / 达到滑动上限 / 页面异常 → ABORT。

        「当前屏没有本 PASS 的目标模板」**不等于**到底——好友列表是乱序的（6★/4★/太阴 交错），
        中间某屏没有目标模板只说明这一屏没有候选，继续向下滑，绝不当作 BOTTOM。
        """
        timer = Timer(self.SEARCH_PASS_TIMEOUT).start()
        clicked_any = False                        # 本 PASS 是否至少点开过一个候选（final 兜底用）
        prev_detections = None                     # K4：上一稳定屏 find_everyone 的完整结果（一帧对一帧，无持久历史）
        pending_anchor_before = None               # K4：上一屏 swipe 前的 selected anchor（配对本屏 anchor_after）
        for screen_index in range(self.SEARCH_MAX_SWIPES + 1):
            if timer.reached():
                logger.warning('结界卡搜索 PASS 超时，安全中止')
                return PassResult.ABORT, clicked_any

            self.screenshot()
            # K4：本屏是（上一屏 swipe 后的）稳定屏。若上一屏留了 detections + anchor_before，
            # 在这一帧测 anchor_after → 实际滚动像素 actual_scroll_dy。不可靠则本屏退回完整扫描。
            dedup_dy = None
            if self.K4_ENABLED and prev_detections is not None and pending_anchor_before is not None:
                anchor_after = detect_selected_anchor(
                    self.device.image, self.I_IS_SELECTED,
                    frame_id=self.device.image_frame_id,
                )
                dedup_dy = actual_scroll_dy_px(
                    pending_anchor_before, anchor_after,
                    max_dy=self.I_IS_SELECTED.roi_back[3],
                )
                if dedup_dy is None:
                    logger.info(
                        'Kekkai K4: measurement=unavailable '
                        '(before_available=%s after_available=%s) fallback=full_scan'
                        % (pending_anchor_before.available, anchor_after.available)
                    )

            cards = search_pass.targets.find_everyone(
                self.device.image, frame_id=self.device.image_frame_id,
            )
            scan_cards = cards
            if cards and prev_detections and dedup_dy is not None:
                dedup = dedup_by_projection(
                    prev_detections, cards, dedup_dy, visible_y=self.K4_LIST_VISIBLE_Y,
                )
                scan_cards = dedup.new_detections
                logger.info(
                    'Kekkai K4: actual_dy=%.1f rows≈%.2f previous=%d current=%d '
                    'duplicates=%d new=%d'
                    % (dedup_dy, dedup_dy / self.KEKKAI_ROW_PITCH_PX,
                       len(prev_detections), len(cards),
                       len(dedup.duplicate_indices), len(scan_cards))
                )

            for target, _, area in (scan_cards or []):
                # 当前屏候选按 find_everyone 的位置序（y 从上到下）逐个点开读收益
                self.C_SELECT_CARD.roi_front = area
                self.click(self.C_SELECT_CARD)
                time.sleep(self.DETAIL_LOAD_WAIT)
                clicked_any = True
                self.utilize_found_eligible_card = True
                card_type, card_value = self.check_card_num()
                if card_type == 'unknown' or card_value <= 0:
                    # OCR 无效 / 详情没加载完 —— 跳过该候选继续下一张，不做无限重读
                    logger.info(f'跳过无效卡: {card_type}@{card_value}')
                    continue
                if self._card_meets_pass(card_type, card_value, search_pass):
                    logger.info(
                        f'{search_pass.friend_group.value} 命中阈值: '
                        f'{card_type}@{card_value} >= '
                        f'{search_pass.threshold_map.get(card_type)}，直接使用当前选中的卡'
                    )
                    return PassResult.HIT, clicked_any

            # 当前屏候选处理完（或本屏没有目标模板）——只有 I_U_EMPTY_CARD 才是真正的到底
            if self.appear(self.I_U_EMPTY_CARD):
                if search_pass.final_fallback and clicked_any:
                    logger.info(
                        '最终 PASS 已扫到列表底部：直接使用最后一次点击、仍保持选中的候选'
                    )
                    return PassResult.FINAL_USE_LAST, clicked_any
                logger.info('本 PASS 已扫到列表底部，没有达标候选')
                return PassResult.PASS_MISS, clicked_any

            if screen_index == self.SEARCH_MAX_SWIPES:
                break                              # 已经看过 MAX+1 屏，不再多滑一次
            if self.K4_ENABLED:
                # K4：把本屏完整检测结果 + swipe 前 selected anchor 留给下一稳定屏做投影去重
                # （只保留上一屏、无持久历史）。swipe 前明确重截一帧，避免候选详情页污染锚点。
                prev_detections = cards
                self.screenshot()
                pending_anchor_before = detect_selected_anchor(
                    self.device.image, self.I_IS_SELECTED,
                    frame_id=self.device.image_frame_id,
                )
            if not self._perform_search_swipe():
                # K3：swipe 后列表未 changed&stable（滑不动 / 一直抖 / timeout）——
                # 不是到底（BOTTOM 只认 I_U_EMPTY_CARD），当作页面异常安全中止
                logger.warning('结界卡下划后未观察到有效滚动并稳定（FrameWait 失败），安全中止')
                return PassResult.ABORT, clicked_any

        # 达到最大滑动次数仍未见到底部 marker —— 当作页面异常安全中止，不当作到底
        logger.warning(
            f'结界卡搜索 PASS 达到最大滑动次数 {self.SEARCH_MAX_SWIPES}，安全中止'
        )
        return PassResult.ABORT, clicked_any

    def _reset_utilize_friend_list(self, friend: SelectFriendList) -> None:
        """[legacy / 仅怠惰模式] 滚到列表底部触发整份好友卡加载 + 切区来回双切刷新回顶。

        标准（非怠惰）PASS 路径**不再调用本方法**：`_run_search` 每个 PASS 前只
        `switch_friend_list(target)` 一次即可——Level C 已确认「只要 SAME/CROSS 发生实际
        切换，新进入的分组列表必定从顶部显示」。本方法目前仅 `_run_lazy_utilize` 仍在用，
        怠惰模式行为本轮保持不变；不要在标准路径重新引入本方法或 `S_U_END` 预滚。
        """
        if friend == SelectFriendList.SAME_SERVER:
            self.switch_friend_list(SelectFriendList.SAME_SERVER)
            self.swipe(self.S_U_END, interval=3)
            self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)
            self.switch_friend_list(SelectFriendList.SAME_SERVER)
        else:  # 跨区必须切换两次，否则结界卡不会刷新到顶部
            self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)
            self.swipe(self.S_U_END, interval=3)
            self.switch_friend_list(SelectFriendList.SAME_SERVER)
            self.switch_friend_list(SelectFriendList.DIFFERENT_SERVER)

    def _record_utilize_failure(self, reason: str) -> bool:
        """记录一次已选中目标后的实际蹭卡失败；三次后按失败延迟任务。"""
        self.utilize_failed_count += 1
        logger.warning(
            f'蹭卡失败: {reason} ({self.utilize_failed_count}/3)'
        )
        if self.utilize_failed_count < 3:
            return False

        message = '连续3次蹭卡失败，目标结界视为已经被蹭，任务失败，稍后重试'
        logger.error(message)
        self.push_notify(content=message)
        self._schedule_retry(f'连续 3 次蹭卡失败（最后一次原因: {reason}）')
        self.utilize_terminal_failure = True
        return False

    def _finish_low_value_utilize(self) -> bool:
        """跨区 + 同区搜索都完成，但没有找到符合「目标卡种 + 收益阈值」的结界卡——
        属短期 retry 场景（不是好友列表里完全没有结界卡），失败并延迟任务。"""
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        target_name = {
            UtilizeRule.TAIKO: '太鼓',
            UtilizeRule.FISH: '斗鱼',
            UtilizeRule.DEFAULT: '太鼓或斗鱼',
        }.get(rule, '目标结界卡')
        message = (
            f'本轮未找到符合"目标卡种（{target_name}）+ 收益阈值"的结界卡，'
            '同区和跨区搜索均已完成，稍后重试'
        )
        logger.error(message)
        self.push_notify(content=message)
        self._schedule_retry('跨区 + 同区都没有达标候选')
        self.utilize_terminal_failure = True
        return False

    def run_utilize(self, friend: SelectFriendList = SelectFriendList.SAME_SERVER,
                    shikigami_class: ShikigamiClass = ShikigamiClass.N,
                    shikigami_order: int = 7):
        """
        执行寄养
        :param shikigami_order:
        :param shikigami_class:
        :param friend:
        :param rule:
        :return:
        """
        logger.hr('Start utilize')

        # 怠惰模式保持原「优先分组 → 备选分组、首张够用即拿」的双分组流程（见 _run_lazy_utilize）；
        # 非怠惰走新的单向分区 PASS 搜索（切区回顶、TOP→BOTTOM、最后一轮兼任兜底）。
        try:
            if self.utilize_lazy_mode_active:
                selected = self._run_lazy_utilize(friend)
            else:
                selected = self._run_search(friend)
        except GamePageUnknownError as error:
            # 分组切换超时按本任务的失败计数处理，不升级为重启游戏
            return self._record_utilize_failure(f'刷新好友列表失败: {error}')

        if selected is None:
            # 两个分组都没有可用候选 → 低价值失败（20 分钟后重试）
            return self._finish_low_value_utilize()
        if selected is not True:
            # 见过候选但都没达标，或搜索被安全中止 → 软失败，交外层 3 次上限的重试链
            if not self.utilize_terminal_failure:
                return self._record_utilize_failure('结界卡搜索未选中满足阈值的目标')
            return False

        # 当前 UI 已选中目标，进入结界。重置次数
        self.utilize_add_count = 0
        logger.info('开始执行进入结界蹭卡流程')
        self.screenshot()
        # 进入结界
        if not self.appear(self.I_U_ENTER_REALM):
            logger.warning('Cannot find enter realm button')
            # 可能是滑动的时候出错
            logger.warning('The best reason is that the swipe is wrong')
            return self._record_utilize_failure('未识别到进入结界按钮')
        try:
            self.goto_page(page_friend_utilize)
        except (GamePageUnknownError, GameStuckError) as error:
            logger.warning('Appear friend realm failed')
            return self._record_utilize_failure(
                f'进入好友结界失败: {type(error).__name__}'
            )
        # 判断好友的有两个位置还是一个坑位
        stop_image = None
        self.screenshot()
        if self.appear(self.I_U_ADD_1):  # 右侧第一个有（无论左侧有没有）
            logger.info('Right side has one')
            stop_image = self.I_U_ADD_1
        elif self.appear(self.I_U_ADD_2) and not self.appear(self.I_U_ADD_1):  # 右侧第二个有 但是最左边的没有，这表示只留有一个坑位
            logger.info('Right side has two')
            stop_image = self.I_U_ADD_2
        if not stop_image:
            # 没有坑位可能是其他人的手速太快了抢占了
            self.save_image(content='没有坑位了', wait_time=0, push_flag=False, image_type='png')
            logger.warning('没有坑位可能是其他人的手速太快了抢占了')
            return self._record_utilize_failure('目标结界已经没有可用坑位')
        try:
            # 切换式神的类型
            self.switch_shikigami_class(shikigami_class)
            # 上式神
            self.set_shikigami(shikigami_order, stop_image)
        except (GamePageUnknownError, GameStuckError) as error:
            return self._record_utilize_failure(
                f'式神寄养失败: {type(error).__name__}'
            )
        self.utilize_failed_count = 0
        return True

    def _run_lazy_utilize(self, friend: SelectFriendList) -> bool | None:
        """怠惰模式的选卡：保持原「优先分组 → 备选分组，首张符合策略的高星卡即拿」双分组流程。

        本轮的单向分区 PASS 搜索只重写非怠惰路径；怠惰模式行为不变。

        :return: True=已选中；None=两个分组都没有可用卡；False=扫描超时等异常。
        :raise GamePageUnknownError: 切换好友分组超时，由 run_utilize 捕获。
        """
        fallback_friend = (
            SelectFriendList.DIFFERENT_SERVER
            if friend == SelectFriendList.SAME_SERVER
            else SelectFriendList.SAME_SERVER
        )
        for index, target_friend in enumerate((friend, fallback_friend), start=1):
            priority_text = '优先' if index == 1 else '备选'
            logger.hr(f'{priority_text}好友分组: {target_friend.value}', 2)
            self._reset_utilize_friend_list(target_friend)
            select_result = self._select_lazy_resource_card()
            if select_result is True:
                logger.info(
                    f'已在{priority_text}分组[{target_friend.value}]选中蹭卡目标，不再检查其他分组'
                )
                return True
            if select_result is False:
                logger.warning(f'分组[{target_friend.value}]怠惰扫描异常，本轮不切换分组')
                return False
            logger.info(f'分组[{target_friend.value}]没有当前策略可用的四星以上结界卡')
        return None

    def _lazy_card_matches_rule(self, card_class: CardClass) -> bool:
        """判断一张四星以上资源卡是否符合当前怠惰策略。"""
        tier_info = self.CARD_TIER_INFO.get(card_class)
        if not tier_info:
            return False
        card_type, _, _ = tier_info
        rule = self.config.kekkai_utilize.utilize_config.utilize_rule
        if rule == UtilizeRule.TAIKO:
            return card_type == '太鼓'
        if rule == UtilizeRule.FISH:
            return card_type == '斗鱼'
        if rule == UtilizeRule.DEFAULT:
            return card_type in ('太鼓', '斗鱼')
        logger.error('Unknown utilize rule')
        raise ValueError('Unknown utilize rule')

    def _select_lazy_resource_card(self) -> bool | None:
        """怠惰模式：选当前可见的首张高星卡，否则首张四星卡。"""
        max_swipes = 20
        consecutive_miss_limit = 3
        timeout = Timer(120).start()
        miss_count = 0
        self.utilize_current_group_has_eligible_card = False
        self.utilize_current_group_scan_completed = False

        logger.hr('怠惰模式快速选择结界卡', 2)
        for swipe_count in range(max_swipes + 1):
            if timeout.reached():
                logger.warning('怠惰模式扫描超时，不能确认当前分组无可用卡')
                return False

            self.screenshot()
            cards = self.lazy_scan_targets.find_everyone(
                self.device.image,
                frame_id=self.device.image_frame_id,
            )
            eligible_cards = []
            if cards:
                eligible_cards = [
                    card for card in cards
                    if self._lazy_card_matches_rule(
                        target_to_card_class(card[0])
                    )
                ]

            if eligible_cards:
                self.utilize_found_eligible_card = True
                self.utilize_current_group_has_eligible_card = True
                high_star_cards = [
                    card for card in eligible_cards
                    if self.CARD_TIER_INFO[
                        target_to_card_class(card[0])
                    ][1] >= 5
                ]
                target, _, area = (
                    high_star_cards[0]
                    if high_star_cards
                    else eligible_cards[0]
                )
                card_class = target_to_card_class(target)
                card_type, star, _ = self.CARD_TIER_INFO[card_class]
                self.C_SELECT_CARD.roi_front = area
                self.click(self.C_SELECT_CARD)
                time.sleep(2)
                logger.info(
                    f'怠惰模式已选择首个符合策略的{star}星{card_type}: '
                    f'swipe={swipe_count}, area={area}'
                )
                return True

            # 当前屏即使只有另一策略的四星以上资源卡，也说明仍位于
            # 有效卡区域，需要继续向下寻找，不能计入连续空屏。
            miss_count = 0 if cards else miss_count + 1
            logger.info(
                f'怠惰模式第{swipe_count}屏未发现当前策略四星以上结界卡'
            )
            if self.appear(self.I_U_EMPTY_CARD):
                logger.info('怠惰模式已到达好友列表空卡区域')
                self.utilize_current_group_scan_completed = True
                return None
            if miss_count > consecutive_miss_limit:
                logger.info(
                    f'怠惰模式连续{miss_count}屏没有四星以上资源卡，'
                    '结束当前分组扫描'
                )
                self.utilize_current_group_scan_completed = True
                return None
            self.perform_swipe_action()

        self.utilize_current_group_scan_completed = True
        logger.info(
            f'怠惰模式已按最大滑动次数{max_swipes}完成当前分组扫描'
        )
        return None

    def perform_swipe_action(self):
        """好友结界卡列表的统一下划操作。

        这里刻意使用 swipe_adb 而不是公共 self.swipe：好友列表对滑动
        距离敏感，引入该方法时就已经选定 adb swipe 并把公共实现注释保留
        （见下方注释行）。改回公共滑动会改变实际滚动距离，必须先做真机
        验证，不能只凭静态测试替换。
        """
        duration = 2
        safe_pos_x = random_int(*self.SWIPE_START_X_RANGE)
        safe_pos_y = random_int(*self.SWIPE_START_Y_RANGE)
        p1 = (safe_pos_x, safe_pos_y)
        p2 = (safe_pos_x, safe_pos_y - self.SWIPE_DISTANCE)
        logger.info('Swipe %s -> %s, %sS ' % (point2str(*p1), point2str(*p2), duration))
        self.device.swipe_adb(p1, p2, duration=duration)

        # self.swipe(self.S_U_UP, duration=1, wait_up_time=1)
        self.device.click_record_clear()
        time.sleep(2)

    def _perform_search_swipe(self) -> bool:
        """标准 PASS 搜索路径的列表下划（K1 输入后端 + K2 随机小步距离 + K3 swipe 后 FrameWait）。

        与 `perform_swipe_action` 的区别：
        - **输入实现（K1）**：minitouch 配置走 `TouchSwipeModel` 生成的 minimum-jerk 轨迹 →
          `Control.swipe_trajectory` → minitouch（BehaviorTrace 记 ACTION）；其它控制后端
          （adb / uiautomator2 等）沿用旧的 `perform_swipe_action`（`swipe_adb` 直连、固定
          `SWIPE_DISTANCE=416` + 2 秒固定等待），保证旧配置不崩。
        - **滑动距离（K2，仅 minitouch）**：每次调用**独立** `random_int(*SWIPE_DISTANCE_RANGE)`
          采样一个「较短」commanded 位移，取代固定 416px。`SWIPE_DISTANCE_RANGE` 是 provisional、
          Level C 分档调参（具体档位与依据见该类常量的注释）——首档实测「一次内容仍滚 >4 格」，
          已回调一档：commanded finger distance ≠ actual content scroll（列表惯性放大）。
        - **轻微整体斜度（2026-09-07，仅 minitouch）**：`end_x = start_x + lateral_offset`，
          `lateral_offset = random_int(*SWIPE_LATERAL_OFFSET_RANGE)`（小幅、有正有负），再夹回
          `SWIPE_START_X_RANGE`。只作用于**最终 end_x**，不给 MOVE 点加噪声；宏观轨迹由旧的接近
          严格竖直变成「有的轻微左斜 / 有的轻微右斜 / 有的接近竖直」，整体仍明确向上 swipe。
        - **swipe settle（K3，2026-09-07，仅 minitouch）**：swipe 后不再固定「2 秒等待猜停稳」，
          改成 `wait_for_changed_and_stable(baseline, self.device.screenshot, roi=SWIPE_WAIT_ROI,
          ...)`。`baseline` 是 swipe **前**明确重截的一帧（不复用可能被右侧详情栏污染的
          `self.device.image`）。只有相对 baseline **确实发生过变化（changed）且随后连续
          `SWIPE_WAIT_STABLE_FRAMES` 帧安静（stable）** 才返回 `True`、允许 `_run_search_pass`
          扫描下一屏。`changed` 迟迟不出现 / `changed` 后一直不 `stable` / timeout → 返回
          `False`，由 `_run_search_pass` 映射成 `ABORT`（外层 bounded recovery）。
          **`no change ≠ BOTTOM`**——D017 唯一 BOTTOM marker 仍是 `I_U_EMPTY_CARD`；本方法不新增
          「滑不动 → PASS_MISS」隐式到底语义。判定阈值 / `stable_frames` / `timeout` /
          `poll_interval`（检测采样 pacing，显式覆盖 FrameWait 默认 0.0）都是 provisional 首版，
          需 Level C 调整。

        决定「滑多远 / 往哪斜 / 何时算稳」在本方法（Kekkai 业务层）；`TouchSwipeModel` 只负责「怎么滑」
        （给定 start/end → 平滑轨迹），本轮不改它、不让它定距离 / 斜度；`FrameStateDetector` 只做帧差算法。
        起点安全区 / 曲率 / 时间模型 / tail 均与 K1/K2 一致；`end_x` 现在带有界的轻微斜度（见上）。
        怠惰模式 + 非 minitouch 回退仍走 `perform_swipe_action`（固定 416px 纯竖直 + 2 秒等待），不受本轮影响。

        :return: `True` = swipe 已执行且列表 `changed && stable`（或走非 minitouch 回退路径）；
                 `False` = minitouch 路径 swipe 后未在 `SWIPE_WAIT_TIMEOUT` 内 `changed && stable`。
        """
        if self.config.script.device.control_method != 'minitouch':
            # 非 minitouch：显式回退到旧 ADB 路径（`perform_swipe_action`，固定 416px + 2 秒等待，本轮不动）
            self.perform_swipe_action()
            return True

        # K3：swipe 前的参考帧——明确重截，不复用 self.device.image（可能是候选卡详情页的截图）
        baseline = self.device.screenshot()

        start_x = random_int(*self.SWIPE_START_X_RANGE)
        start_y = random_int(*self.SWIPE_START_Y_RANGE)
        distance = random_int(*self.SWIPE_DISTANCE_RANGE)       # K2：每次独立采样较短位移
        # 轻微整体斜度：小幅随机横向偏移只作用于最终 end_x，再夹回起点安全区（不扩大 start_x 范围）
        lateral_offset = random_int(*self.SWIPE_LATERAL_OFFSET_RANGE)
        lo_x, hi_x = self.SWIPE_START_X_RANGE
        end_x = min(hi_x, max(lo_x, start_x + lateral_offset))
        start = (start_x, start_y)
        end = (end_x, start_y - distance)                       # 纵向 = 本次随机 distance（K2 范围内）；横向 = 有界后的轻微斜度
        trajectory = TouchSwipeModel().generate(start, end)     # 只生成一次
        total_dt = sum(dt for _, _, dt in trajectory)
        logger.info(
            'KekkaiUtilize trajectory swipe: start=%s end=%s distance=%d lateral=%+d points=%d total_dt=%dms'
            % (point2str(*start), point2str(*end), distance, end_x - start_x,
               len(trajectory), total_dt)
        )
        self.device.swipe_trajectory(trajectory, control_name='KEKKAI_UTILIZE_SWIPE')
        self.device.click_record_clear()

        # K3：等列表相对 baseline changed 且 stable，取代固定 2 秒等待
        wait = wait_for_changed_and_stable(
            baseline,
            self.device.screenshot,
            roi=self.SWIPE_WAIT_ROI,
            changed_threshold=self.SWIPE_WAIT_CHANGED_THRESHOLD,
            stable_threshold=self.SWIPE_WAIT_STABLE_THRESHOLD,
            stable_frames=self.SWIPE_WAIT_STABLE_FRAMES,
            timeout=self.SWIPE_WAIT_TIMEOUT,
            poll_interval=self.SWIPE_WAIT_POLL_INTERVAL,   # 检测采样 pacing，叠在 _screenshot_interval 之上
        )
        logger.info(
            'KekkaiUtilize swipe wait: changed=%s stable=%s timed_out=%s frames=%d elapsed=%.2fs diff=%.3f'
            % (wait.changed, wait.stable, wait.timed_out,
               wait.frames_checked, wait.elapsed, wait.last_difference)
        )
        if not wait.success:
            logger.warning(
                'KekkaiUtilize swipe 后未在 %.1fs 内 changed&stable（changed=%s stable=%s）——'
                '不当作到底（BOTTOM 只认 I_U_EMPTY_CARD），交外层安全中止'
                % (self.SWIPE_WAIT_TIMEOUT, wait.changed, wait.stable)
            )
        return wait.success

    def check_card_num(self) -> tuple[str, int]:
        """优化版数值提取方法，返回结界卡类型及对应数值"""
        self.screenshot()
        # OCR识别
        raw_text = self.O_CARD_NUM.ocr(self.device.image)
        # logger.info(f'OCR原始结果: {raw_text}')

        # 判断结界卡类型
        if any(c in raw_text for c in ['体', 'カ', '力']):
            card_type = '斗鱼'
        elif any(c in raw_text for c in ['勾', '玉']):
            card_type = '太鼓'
        else:
            logger.warning(f'结界卡类型识别失败，原始内容: {raw_text}')
            # self.push_notify(content=f'结界卡类型识别失败: {raw_text}')
            return 'unknown', 0  # 未知类型返回0

        # 提取纯数字部分（兼容带+号的情况，如+100）
        cleaned = re.sub(r'[^\d+]', '', raw_text)  # 保留数字和加号
        match = re.search(r'\d+', cleaned)  # 匹配连续数字

        try:
            value = int(match.group()) if match else 0
        except ValueError:
            logger.warning(f'数值转换异常，清理后文本: {cleaned}')
            value = 0

        if value <= 0:
            self.push_notify(content=f'数值异常: {raw_text} -> 解析值: {value}')
            return card_type, 0

        # logger.info(f'识别成功: 卡类型: {card_type}, 数值: {value}')
        return card_type, value


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    c = Config('日常1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.run_utilize(SelectFriendList.DIFFERENT_SERVER)
    # t.check_utilize_add()
    # t.check_card_num('勾玉', 67)
    # t.screenshot()
    # print(t.appear(t.I_BOX_EXP, threshold=0.6))
    # print(t.appear(t.I_BOX_EXP_MAX, threshold=0.6))
