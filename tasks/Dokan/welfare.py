# This Python file uses the following encoding: utf-8
"""福利道馆模式：只找「鑫」馆，开馆进准备页点准备后立即关游戏，10 分钟后返回本馆放弃，选「再战道馆」。

只在 DokanConfig.welfare_mode 打开时由 `ScriptTask.run` 进入，普通道馆流程不经过这里。

设计边界（首版）：
- 不做进程中断后的续跑：启动时已经有进行中的道馆一律转人工；开过馆之后再出现自动恢复类异常
  也转人工，避免公共 Restart 把流程从头跑一遍、误开下一馆或误放弃当前馆。
- 前置公共步骤不能漏：进入找馆页后、预设之前先确认我方道馆已建立（没有就复用普通模式的建馆流程，
  见 `_ensure_own_dokan`），一次运行只检查一次。
- 所有「等」都有上限或可被进程终止打断；业务上不设刷新次数上限，但每一步的点击 / 等待有界，
  明确的游戏限制（刷新弹窗出不来等）转人工，不做高频连点。
- 页面状态一律以资源匹配为准，没有确认依据的步骤不盲点：缺什么画面见各步骤的提示。
"""
import random
import re
import time
from contextlib import contextmanager

import cv2
import numpy as np

from module.atom.frame_state import DEFAULT_PIXEL_THRESHOLD, frame_difference
from module.atom.swipe import RuleSwipe
from module.base.frame_wait import wait_for_changed_and_stable
from module.click_pipeline import ClickBounds, FinalPoint, execute_single_click
from module.exception import (
    GameBugError,
    GameNotRunningError,
    GamePageUnknownError,
    GameStuckError,
    GameTooManyClickError,
    RequestHumanTakeover,
)
from module.fatigue import get_fatigue_manager
from module.logger import logger
import tasks.Dokan.page as pages
from tasks.GlobalGame.assets import GlobalGameAssets

# 调度器会自动 Restart 并重新拉起任务的异常（见 Script._handle_task_exception）
AUTO_RECOVERED_ERRORS = (
    GameStuckError, GameTooManyClickError, GameBugError, GamePageUnknownError, GameNotRunningError,
)

MAX_DOKAN_PER_RUN = 2
CLOSED_WAIT_SECONDS = 600       # 确认游戏已关闭后等待
AGAIN_WAIT_SECONDS = 120        # 选「再战道馆」成功后等待（游戏保持开启）
WAIT_CHUNK_SECONDS = 1.0        # 等待分段，便于被打断；不用一个长 sleep

# 右侧候选列表（与 find_xin 的 roi_back 一致）：x1, y1, x2, y2
LIST_BOX = (1077, 0, 1248, 602)
# 候选卡片相对「鑫」图标匹配框中心的截取范围，用来给候选做指纹（去重 / 重新定位）
CARD_X = (1075, 1245)
CARD_Y_UP, CARD_Y_DOWN = 55, 88
# 同一张卡片的判定（D-08）：旧写法只比整张 34x30 小图的平均绝对差（< 6.0），用真实卡片（2026-10-26 / 27 整屏截图）量得：
# 同一张卡裁剪偏 1 px 就有 ≈5.2、偏 2 px ≈10（会被当成不同卡片），而把卡片里一行文字（4 px 高）换掉只有 ≈1.7、
# 换掉 12 px 也只有 ≈4.5（仍被当成同一张，漏检）。改为：上下各多留 CARD_MARGIN 行做 ±CARD_MARGIN px 对齐比较，
# 按水平带分别比较、取最大的一带，并屏蔽「鑫」徽记（所有候选都有、还会闪动，不携带区分信息）。
# 同样数据下：偏 ≤ 2 px ≈ 2，换一行文字 ≈ 10，两张真实不同卡片 ≈ 18.5；阈值 6.0 在两侧各留约 4 的余量。
CARD_MARGIN = 2
CARD_BANDS = 6
CARD_BAND_SAME = 6.0            # 对齐后任一水平带的平均绝对差小于它才认为是同一张卡片
CARD_BADGE_PAD = 3
CARD_SIZE = (34, 30)
CANDIDATE_CONTROL = 'dokan_welfare_candidate'   # 点候选的操作记录名（与 `execute_single_click` 的 control_name 一致）
LIST_DOWN_NAME = 'dokan_welfare_list_down'      # 回顶滑动的操作记录名（由 S_DOKAN_WELFARE_LIST_UP 的端点反向派生）
LIST_BOTTOM = 600               # 列表可见区域下沿：卡片截取范围超出它说明被裁切，本屏不检查
# 返回本馆：「集」字在「集结」丝带上，徽章在它右上方（按 2026-10-25 整屏截图量得）
BADGE_OFFSET = (84, -100)
# 选「再战道馆」后确认本方选中：只看按钮自己的框（点击时按钮匹配框），不看上方票数 / 倒计时。
# 变化阈值与稳定阈值与找馆列表一致的取法；缺「本方选中后」的真实画面，见 `_vote_again`
VOTE_CHANGED_THRESHOLD = 0.03
VOTE_STABLE_THRESHOLD = 0.01
VOTE_CLICK_TRIES = 3            # 只统计「没有真正发出」的限流调用；真正发出的点击只有一次
PEOPLE_RE = re.compile(r'(\d+)')

POPUP_TIMEOUT = 6.0
CHALLENGE_TIMEOUT = 4.0
HIDE_ATTEMPTS = 5
SWIPE_NO_CHANGE_LIMIT = 2       # 连续这么多次「落点稳定且相对滑动前没有推进」的滑动才算到底
SWIPE_OBSERVE_TIMEOUT = 4.0     # 滑动后首次观察列表停下来最多等这么久
SWIPE_SETTLE_TIMEOUT = 2.0      # 滑动后列表一直在变 / 落点又漂移：重新观察每次最多等这么久
SWIPE_SETTLE_TRIES = 3
SWIPE_HOLD_FRAMES = 3           # 判稳之后再取这么多帧都与落点一致，才采信为最终落点（挡住回弹中途的暂停）
SWIPE_SEND_TRIES = 3            # 连续这么多次滑动都没有真正发出：不是到底，转人工
# 「推进」判据：比较滑动前 / 最终落点两帧在 LIST_BOX 内逐行的变化像素占比，变化行占全部行的比例 >= 阈值才算推进。
# 列表滚动哪怕 1 px，整列卡片的文字 / 徽记 / 边框都会错位，几乎每一行都有变化像素（按 2026-10-28 报错截图合成
# 1 px 位移量得约 84% 的行）；角标 / 闪光动画只影响局部几行（合成角标整体闪动约 24%，连徽记一起整块噪声约 57%，
# 属于偏极端的合成上限）。阈值取在两者之间：不用「变化像素总占比」，因为一块够大的动画就能追平 1 px 滚动的占比。
LIST_CHANGED_THRESHOLD = 0.02   # 等待层的「相对滑动前有变化」线：只用来让 FrameWait 在变化且稳定后提前返回，不决定推进
LIST_STABLE_THRESHOLD = 0.01    # 相邻帧变化像素占比 <= 它才算安静
LIST_ROW_CHANGED = 0.05         # 一行里变化像素占比 >= 它，这一行才算「变了」
LIST_MOVED_ROW_COVERAGE = 0.65
OPEN_CONFIRM_TIMEOUT = 15.0
GATHER_TIMEOUT = 900.0
# 集结阶段与公共卡死保护（Device.stuck_record_check）的衔接：
# 公共保护在每次 screenshot() 前检查，「最近一次点击 / 清除」之后超过 60 秒（且 >= 60 次检查）就抛 GameStuckError；
# 登记 PAUSE 等长等待只能把上限延到 300 秒，撑不住 900 秒，所以集结期间靠「识别到集结页就清一次」保持，
# 识别不到就不清，保护照常倒计时。未知画面的容忍时间必须小于公共的 60 秒，才能先于它给出具体原因。
GATHER_UNKNOWN_TOLERANCE = 30.0     # 既不是集结页也不是可开始挑战的画面，连续超过这么久转人工
GATHER_START_CLICK_LIMIT = 5        # 本阶段「开始挑战」实际发出的点击上限：点这么多次仍没进准备页就是无效，不是在等
GATHER_START_OBSERVE = 3.0          # 点满之后再观察这么久（等最后一次点击的转场）
GATHER_LOG_INTERVAL = 60.0          # 集结等待的进度日志间隔
CLOSE_CONFIRM_TIMEOUT = 20.0
ABANDON_TIMEOUT = 90.0
VOTE_CONFIRM_TIMEOUT = 8.0
BACK_TO_FIND_TIMEOUT = 90.0
DOKAN_EXIT_TRIES = 2                # 再战返回时从道馆页导航回地图的次数上限（导航到达后仍是道馆页才会再来一次）
REFRESH_TRIES = 3
REFRESH_PAGE_TIMEOUT = 6.0          # 确认刷新之后等「找馆页」重新出现的上限
REFRESH_LOAD_ROUNDS = 3             # 刷新后列表一直没变化时最多再观察几轮（每轮自带有界稳定等待）
# 刷新后「列表内容变了」的判据：落点稳定后的列表与点刷新前（到底时）的列表比较变化行占比（同 `list_row_coverage`）。
# 比滑动的 0.65 低得多：刷新后列表可能保留部分相同候选、也可能很短（只有 1～2 张卡片，整列只有约 25% 的行有内容）。
# 没有真机的刷新前后画面，取值未校准；每次刷新都会把实测值写进日志，供真机校准
REFRESH_CHANGED_COVERAGE = 0.05
TOP_MAX_MOVES = 30                  # 回顶时最多接受这么多次「有效推进」的反向滑动，超过转人工（列表不会有这么长）
RELOCATE_LIMIT = 5                  # 同一批里连续这么多次点击前重新定位失败（没有任何进展）转人工
PRESET_NO_DIALOG_CLICKS = (2, 4)    # 不弹确认框时实际发出的预设点击数范围（含两端，一次抽定）
PRESET_CLICK_INTERVAL = 1.5         # 预设点击之间的最小间隔（传给 appear_then_click 的限流）
PRESET_OBSERVE_SECONDS = 2.0        # 发满之后观察确认框的时长（> 点击到弹框的正常延迟）
PRESET_TOTAL_TIMEOUT = 30.0         # 点击一直发不出去时的总时限（发满之后不再受它约束，只受观察时长约束）
PRESET_MISS_FRAMES = 3              # 连续这么多帧既无确认框又无预设按钮 → 转人工


def match_boxes(rule, matches):
    """把 `RuleImage.match_all_any()` 的结果 [(score, x, y, w, h), ...] 转成内部统一的 [(x, y, w, h), ...]。

    外部协议带置信度（见 `module/atom/image.py`），福利模块内部（排序、指纹、点击框）只用四项坐标，
    置信度在这里丢弃。格式不符直接报错并带上规则名：静默截取会把 score 当成 x，之后全部候选错位。
    """
    boxes = []
    for item in matches:
        try:
            score, x, y, w, h = item
            boxes.append((int(x), int(y), int(w), int(h)))
            float(score)
        except (TypeError, ValueError) as e:
            raise ValueError(f'{getattr(rule, "name", rule)} 匹配结果不是 (score, x, y, w, h)：{item!r}') from e
    return boxes


class CardFingerprint(np.ndarray):
    """候选卡片指纹：形状与旧版相同的 30x34 灰度小图，额外带 `tall`——上下各多留 CARD_MARGIN 行的原始灰度截图，
    和 `badge`——「鑫」徽记（含余量）在 `tall` 里的位置 (y0, y1, x0, x1)；`same_card` 用它们做对齐比较。"""

    tall = None
    badge = None


def card_fingerprint(image, box):
    """候选卡片指纹：以「鑫」图标匹配框 (x, y, w, h) 为基准截一块灰度图。

    返回 None 表示卡片（含对齐余量）被列表上下沿裁切，这一屏不检查它（滑动后会完整出现）。
    """
    x, y, w, h = box                # 内部四项坐标；外部五项结果先经 match_boxes 转换
    centre = y + h // 2
    top, bottom = centre - CARD_Y_UP - CARD_MARGIN, centre + CARD_Y_DOWN + CARD_MARGIN
    if top < LIST_BOX[1] or bottom > LIST_BOTTOM:
        return None
    crop = np.asarray(image)[top:bottom, CARD_X[0]:CARD_X[1]]
    if crop.size == 0:
        return None
    tall = (crop.astype(np.float32).mean(axis=2) if crop.ndim == 3 else crop.astype(np.float32)).copy()
    bx, by = x - CARD_X[0], y - top
    badge = (max(0, by - CARD_BADGE_PAD), by + h + CARD_BADGE_PAD, max(0, bx - CARD_BADGE_PAD), bx + w + CARD_BADGE_PAD)
    small = tall[CARD_MARGIN:tall.shape[0] - CARD_MARGIN].copy()
    small[max(0, badge[0] - CARD_MARGIN):max(0, badge[1] - CARD_MARGIN), badge[2]:badge[3]] = 0
    fingerprint = _small(small).view(CardFingerprint)
    fingerprint.tall = tall
    fingerprint.badge = badge
    return fingerprint


def _small(gray):
    return cv2.resize(gray, CARD_SIZE, interpolation=cv2.INTER_AREA)


def card_distance(a, b) -> float:
    """两张卡片指纹的差异：±CARD_MARGIN px 对齐后，各水平带平均绝对差的最大值（取各对齐方式中最小的）。"""
    if getattr(a, 'tall', None) is None or getattr(b, 'tall', None) is None:
        return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))           # 没有对齐信息的普通数组：退回整体平均
    rows = a.tall.shape[0]
    # 徽记位置按两张卡片的并集一起屏蔽：两次匹配的 x / y 有一两个像素的误差，各屏蔽各的会留下不对称的边缘
    y0, y1 = min(a.badge[0], b.badge[0]), max(a.badge[1], b.badge[1])
    x0, x1 = min(a.badge[2], b.badge[2]), max(a.badge[3], b.badge[3])
    ta, tb = a.tall.copy(), b.tall.copy()
    ta[y0:y1, x0:x1] = 0
    tb[y0:y1, x0:x1] = 0
    core = _small(ta[CARD_MARGIN:rows - CARD_MARGIN])
    best = None
    for shift in range(-CARD_MARGIN, CARD_MARGIN + 1):
        other = _small(tb[CARD_MARGIN + shift:rows - CARD_MARGIN + shift])
        diff = np.abs(core - other)
        worst = max(float(part.mean()) for part in np.array_split(diff, CARD_BANDS, axis=0))
        best = worst if best is None else min(best, worst)
    return best


def same_card(a, b) -> bool:
    return a is not None and b is not None and card_distance(a, b) < CARD_BAND_SAME


def list_row_coverage(before, after):
    """滑动前 / 最终落点两帧在 LIST_BOX 内的差异：返回 (变化行占比, 变化像素占比)。

    判「列表是否真的推进」用前者（见 LIST_MOVED_ROW_COVERAGE 的说明），后者只写进日志。
    像素是否变化沿用 `frame_difference` 的通道差阈值，帧形状不一致直接抛 ValueError。
    """
    a, b = np.asarray(before), np.asarray(after)
    if a.shape != b.shape:
        raise ValueError(f'两帧形状不一致：{a.shape} vs {b.shape}')
    x1, y1, x2, y2 = LIST_BOX
    diff = np.abs(a[y1:y2, x1:x2].astype(np.int16) - b[y1:y2, x1:x2].astype(np.int16))
    changed = (diff.max(axis=2) if diff.ndim == 3 else diff) > DEFAULT_PIXEL_THRESHOLD
    rows = changed.mean(axis=1) >= LIST_ROW_CHANGED
    return float(rows.mean()), float(changed.mean())


class WelfareDokan:
    def __init__(self, task, *, clock=time.monotonic, sleep=time.sleep, login=None):
        self.task = task
        self.clock = clock
        self.sleep = sleep
        self._login = login or self._default_login
        self.opened = 0              # 已经点过「确认开启」的馆数（有副作用的步骤，防重复）
        self.preset_done = False
        self.own_dokan_checked = False   # 我方道馆建立检查已完成（只在确认回到找馆页之后才设置）
        self._candidate_verified = False  # 刚检查完的候选已经形成有效业务结论（详情打开并读到结论），等它的详情关闭后再释放操作记录
        self._list_down = None

    # ------------------------------------------------------------------ 入口
    def run(self) -> int:
        """返回结束时**可靠识别**到的剩余机会数；无法识别一律转人工，绝不推算。"""
        self._precheck()
        try:
            return self._run()
        except AUTO_RECOVERED_ERRORS as error:
            if self.opened:
                raise RequestHumanTakeover(
                    f'福利道馆流程中途被 {error!r} 打断，本次已开启 {self.opened} 馆，现场状态和进度无法'
                    '可靠恢复。为避免自动 Restart 后从头重跑、误开下一馆或误放弃当前馆，已停止自动运行，'
                    '需要人工处理。'
                ) from error
            raise

    def _human(self, message: str):
        logger.critical(message)
        raise RequestHumanTakeover(message)

    def _precheck(self):
        # 点准备之后才发现不能关游戏就晚了：开馆之前先确认 app_stop / app_start 的前置条件
        if not self.task.config.script.error.handle_error:
            self._human(
                '福利道馆需要关闭并重新启动游戏，但「出错时自动处理（HandleError）」未开启，'
                'app_stop / app_start 会被拒绝。请先开启后再运行福利道馆。'
            )

    def _run(self) -> int:
        task = self.task
        task.goto_page(pages.page_dokan_map)
        state = self._map_state()
        if state == 'found':
            self._human(
                '启动时已经存在进行中的道馆，无法确认它是不是本程序开启的、处于哪个阶段。'
                '首版福利道馆不接管现场，请人工处理（返回或放弃）后再运行。'
            )
        if state is None:
            self._human('无法识别道馆地图页面（既不是找馆页也不是进行中），请人工确认当前画面。')
        count = self._read_count()
        if count is None:
            self._human('无法识别今日剩余挑战机会（未知不能当作 0，也不能默认还有 2 次），请人工确认。')
        logger.info(f'Welfare dokan: remaining chances {count}')
        if count <= 0:
            return 0
        if not self.own_dokan_checked:
            self._ensure_own_dokan()
        total = min(count, MAX_DOKAN_PER_RUN)
        opened_before = self.opened
        for index in range(total):
            last = index + 1 >= total
            if not self.preset_done:
                self._apply_preset()
            self._find_and_open()
            self._enter_prepare_and_close()
            closed_at = self._confirm_closed()
            self._wait_closed(closed_at)
            self._restart_and_return()
            outcome = self._abandon(want_again=not last)
            if outcome == 'finished':
                break
            if not last:
                self._wait_again()
                self._back_to_find_page(leave_dokan_page=True)
        # 最终次数必须来自识别：执行了两轮、或初始次数减循环次数，都不等于已确认当天机会用完
        final = self._read_count(retries=6)
        if final is None:
            self._human(
                f'本次已开启并放弃 {self.opened - opened_before} 馆，但无法读取最终剩余机会（未知不能当作 0，'
                '也不能用初始次数减循环次数推算），不写入次数、不按正常完成收尾，请人工确认。'
            )
        if final > 0:
            logger.warning(
                f'Welfare dokan: {final} chance(s) still left after this run; no further dokan is opened, '
                'the recognised count is reported as is')
        return final

    # ------------------------------------------------------------------ 读取页面 / 次数
    def _screenshot(self):
        self.task.screenshot()

    def _map_state(self, retries: int = 6):
        task = self.task
        for _ in range(retries):
            self._screenshot()
            found = task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN)
            finding = task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN)
            if found and not finding:
                return 'found'
            if finding and not found:
                return 'finding'
            self.sleep(0.5)
        return None

    def _read_count(self, retries: int = 6):
        task = self.task
        for _ in range(retries):
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO) or \
                    task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
                return 0
            if task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ONE):
                return 1
            if task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_TWO):
                return 2
            self.sleep(0.5)
        return None

    # ------------------------------------------------------------------ A2. 我方道馆
    def _ensure_own_dokan(self):
        """没有我方道馆就建（复用普通模式的 `ensure_dokan_created` / `creat_dokan` 及资源），并确认回到找馆页。

        - 用 strict 模式：普通模式「点了没弹确认框就当已建立」的推断在这里不可靠，见 `ScriptTask.ensure_dokan_created`；
        - 建馆是我方道馆的事，不碰 `opened`（那只统计「确认开启」过的对方道馆），也不扣减、推算攻打次数；
        - 不读 `try_start_dokan`：福利模式本身已经明确要求自动找馆开馆；
        - `own_dokan_checked` 只在建立 / 已建立并确认回到找馆页之后才设置，失败和异常出口都不设置。
        """
        if not self.task.ensure_dokan_created(strict=True):
            self._human(
                '无法确认我方道馆已经建立（建立流程没有完成，或建立入口的状态无法分辨），已停止：'
                '没有预设、没有找馆，也没有开启对方道馆。请人工确认我方道馆后再运行。'
            )
        state = self._map_state(retries=4)
        if state != 'finding':
            self._human(
                '我方道馆建立检查结束后没有回到找馆页（'
                + ('地图上出现了进行中的道馆' if state == 'found' else '无法识别当前画面')
                + '），已停止：没有预设、没有找馆，也没有开启对方道馆。'
            )
        self.own_dokan_checked = True
        logger.info('Welfare dokan: own dokan confirmed, back on the find page')

    # ------------------------------------------------------------------ B. 一键预设
    def _apply_preset(self):
        """找馆页 → 阵容 → 一键预设（有确认框就确认；没有就点 2～4 次后视为操作完成）→ 返回找馆页。

        - 进入阵容页以一键预设图标出现为准，不能只因点了入口就默认到达；
        - 预设点击见 `_click_preset`：确认框出现一律优先确认；账号此前已预设过、不弹确认框时，在已确认的
          阵容页上实际发出 2～4 次预设点击（一次抽定）并有界观察无确认框，即「预设操作完成」；
        - 这只是用户接受的操作完成判据：预设完成本身没有可识别的提示画面，程序没有验证最终御魂 / 阵容效果；
        - `preset_done` 只在返回找馆页并确认之后才设置：任何异常 / 失败出口都不设置。
        """
        task = self.task
        self._ensure_find_page()
        if not task.ui_click_until_appear_or_timeout(
                task.I_DOKAN_TEAM, stop=task.I_DOKAN_TEAM_PRESET, interval=1.5, timeout=10):
            self._human('点击「阵容」后没有进入阵容页（未出现一键预设图标），已停止，未做预设。')
        route, sent = self._click_preset()
        self._screenshot()
        if not task.appear(task.I_DOKAN_TEAM_PRESET):
            self._human('预设操作后不在阵容页，无法确认当前画面，已停止。')
        self._back_to_find_page(timeout=15)
        self.preset_done = True
        logger.info(f'Welfare dokan: preset operation done ({route}, {sent} preset click(s) sent; '
                    'final soul / team effect not verified)')

    def _click_preset(self):
        """点一键预设直到「预设操作完成」，返回 (路径, 实际发出的预设点击数)。

        每一帧先看确认框（优先于任何预设点击，重试期间确认框迟到也先确认），再看预设按钮：
        - 确认框出现 → 点「确定」直到消失（沿用有界 `ui_click_until_disappear`）→ 'confirm dialog'；
        - 按钮在：按 `PRESET_CLICK_INTERVAL` 点，**只有 `appear_then_click` 返回 True（= 过了限流、识别到
          目标并真正发出点击）才计数**，被限流 / 目标消失的调用不计；目标次数 PRESET_NO_DIALOG_CLICKS 内一次
          抽定，不随循环增长；发满之后再有界观察 PRESET_OBSERVE_SECONDS 仍无确认框 → 'no confirm dialog'；
        - 既没有确认框也没有按钮连续 PRESET_MISS_FRAMES 帧（被别的弹窗遮挡 / 未知页面）→ 转人工；
        - 总时限 PRESET_TOTAL_TIMEOUT 内凑不满次数（点击一直没发出）→ 转人工，不凑数。
        """
        task = self.task
        target = random.randint(*PRESET_NO_DIALOG_CLICKS)
        sent = 0
        missing = 0
        last_sent_at = None
        deadline = self.clock() + PRESET_TOTAL_TIMEOUT
        while True:
            self._screenshot()
            if task.appear(GlobalGameAssets.I_UI_CONFIRM):
                logger.info(f'Welfare dokan: preset confirm dialog appeared after {sent} preset click(s)')
                if not task.ui_click_until_disappear(
                        GlobalGameAssets.I_UI_CONFIRM, interval=1.5, timeout=10, max_clicks=3):
                    self._human('点击「确定」后确认框没有消失，无法确认预设已提交，已停止。')
                return 'confirm dialog', sent
            if not task.appear(task.I_DOKAN_TEAM_PRESET):
                missing += 1
                if missing >= PRESET_MISS_FRAMES:
                    self._human('预设过程中一键预设按钮持续识别不到（可能被其它弹窗遮挡或进入未知页面），已停止。')
                self.sleep(0.5)
                continue
            missing = 0
            if sent >= target:
                if self.clock() - last_sent_at >= PRESET_OBSERVE_SECONDS:
                    logger.info(f'Welfare dokan: no confirm dialog after {sent} preset click(s) (target {target})')
                    return 'no confirm dialog', sent
                self.sleep(0.3)
                continue
            if self.clock() >= deadline:
                self._human(f'一键预设点击一直没有实际发出（{PRESET_TOTAL_TIMEOUT:.0f} 秒内只发出 {sent}/{target} 次），已停止。')
            if task.appear_then_click(task.I_DOKAN_TEAM_PRESET, interval=PRESET_CLICK_INTERVAL):
                sent += 1
                last_sent_at = self.clock()
                logger.info(f'Welfare dokan: preset click {sent}/{target} sent')
            else:
                self.sleep(0.3)

    def _ensure_find_page(self):
        if self._map_state(retries=4) != 'finding':
            self._human('当前不在找馆页（没有出现「推荐」列表），已停止。')

    def _back_to_find_page(self, timeout: float = BACK_TO_FIND_TIMEOUT, leave_dokan_page: bool = False):
        """回到地图找馆页。找馆页 → 直接返回；进行中的馆 → 转人工；其余按原来点黄色返回键。

        `leave_dokan_page`（只有再战等待之后传 True）：再战之后停在哪一页没有真实画面证据，可能已回地图，也可能还在
        道馆页。道馆页上黄色返回键匹配不到（真实道馆页截图离线匹配 0.389，退出图标 `I_RYOU_DOKAN_DOKAN_QUIT` 0.993），
        所以看到道馆页标志（`I_RYOU_DOKAN_CHECK`）时交给现有 `page_dokan → page_dokan_map` 导航（退出图标 → 退出确认），
        不复制那套点击；导航返回后一律重新截图判断，不把「调用返回」当作到达。
        `goto_page` 的 `timeout` 是**无进展**超时（页面变化 / 点击推进会重置，不是总时限），这里传入剩余时间做上界，
        外层 deadline 并不能中断它；它超时抛 `GamePageUnknownError`，已开馆之后由 `run()` 转人工，不会重新投票或重新等待。
        """
        task = self.task
        deadline = self.clock() + timeout
        exits = 0
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN) and not task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                return
            if self.clock() >= deadline:
                break
            if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                self._human('回到地图后发现存在进行中的道馆，无法确认现场，请人工处理。')
            if leave_dokan_page and task.appear(task.I_RYOU_DOKAN_CHECK):
                exits += 1
                if exits > DOKAN_EXIT_TRIES:
                    self._human('已从道馆页导航退出多次，仍然停在道馆页，无法回到地图找馆页，已停止。')
                logger.info(f'Welfare dokan: still on the dokan page after the rematch wait, leave it through the '
                            f'existing page_dokan -> page_dokan_map navigation ({exits}/{DOKAN_EXIT_TRIES})')
                task.goto_page(pages.page_dokan_map, timeout=max(5, int(deadline - self.clock())))
                continue
            task.appear_then_click(GlobalGameAssets.I_UI_BACK_YELLOW, interval=1.5)
            self.sleep(0.5)
        self._human('没有回到找馆页，已停止。')

    # ------------------------------------------------------------------ C. 严格找馆
    def _find_and_open(self):
        """遍历右侧列表找「鑫」馆：人数 >= 门槛且可挑战的第一个。业务上不设刷新次数上限。"""
        refreshes = 0
        while True:
            self._ensure_find_page()
            if self._scan_list_once():
                return
            refreshes += 1
            logger.info(f'Welfare dokan: list exhausted, refresh #{refreshes}')
            self._refresh_list()
            self._scroll_list_to_top()
            logger.info(f'Welfare dokan: refresh #{refreshes} done, start searching the new batch from the top')

    def _scan_list_once(self) -> bool:
        """从上到下检查当前可见的每个「鑫」，检查完滑动；连续两次实际发出的滑动都没有推进才算到底（返回 False）。"""
        threshold = self.task.config.dokan.dokan_config.welfare_min_people
        checked = []
        unchanged = 0
        unsent = 0
        relocates = 0
        while True:
            self._hide_popup()
            relocate = False
            for candidate in self._candidates():
                if any(same_card(candidate['fp'], old) for old in checked):
                    continue
                verdict = self._check_candidate(candidate, threshold)
                if verdict == 'relocate':
                    relocate = True     # 列表动过了：回到循环顶重新识别，不用旧坐标
                    relocates += 1
                    if relocates >= RELOCATE_LIMIT:
                        self._human(f'连续 {relocates} 次点击前都无法在最新画面里重新定位候选馆（没有任何进展），已停止。')
                    break
                relocates = 0
                checked.append(candidate['fp'])
                if verdict == 'open' and self._confirm_open():
                    return True
            if relocate:
                continue
            verdict = self._swipe_list()
            if verdict == 'not_sent':
                # 没发出的滑动既不是推进也不是没动：不碰连续 static 计数，但连续发不出去要有界退出
                unsent += 1
                if unsent >= SWIPE_SEND_TRIES:
                    self._human(f'连续 {unsent} 次滑动列表都没有发出，无法判断列表是否到底，已停止（不当作到底）。')
                continue
            unsent = 0
            if verdict == 'moved':
                unchanged = 0
                continue
            unchanged += 1
            logger.info(f'Welfare dokan: list static streak {unchanged}/{SWIPE_NO_CHANGE_LIMIT}')
            if unchanged >= SWIPE_NO_CHANGE_LIMIT:
                logger.info('Welfare dokan: list bottom confirmed, hand over to refresh')
                return False

    def _candidates(self):
        task = self.task
        self._screenshot()
        image = task.device.image
        boxes = sorted(match_boxes(task.I_FIND_XIN, task.I_FIND_XIN.match_all_any(image)), key=lambda b: b[1])
        result = []
        for box in boxes:
            fp = card_fingerprint(image, box)
            if fp is not None:
                result.append({'box': box, 'fp': fp})
        return result

    def _hide_popup(self):
        """让候选详情卡片消失。这是「详情一定属于下一次点击的候选」的前提。"""
        task = self.task
        for _ in range(HIDE_ATTEMPTS):
            self._screenshot()
            if not task.appear(task.I_CENTER_CHALLENGE) and not task.appear(task.I_CENTER_POINT_PEOPLE_NUMBER):
                self._release_candidate_records()
                return
            task.click(task.C_DOKAN_CANCEL_SELECT_DOKAN)
            self.sleep(1.2)
        self._human('无法关闭候选馆详情卡片，不能保证人数属于同一个候选，已停止。')

    def _release_candidate_records(self):
        """一个新的候选详情已打开、得出结论并且详情已成功关闭之后，移除「点候选 + 取消详情」两类操作记录。

        公共 `Device` 在点击发出前写入记录并检查：每个候选各记一次候选点击和一次取消点击，最近 15 条里两者各到 6 次
        就抛「两个按钮」GameTooManyClickError——一批里检查 6 个候选就会触发（用真实 `Device` 记录逻辑复现过）。
        只有「有效业务推进」才清：详情读不出 / 没有详情 / 详情关不掉 / 重新定位失败都不置标记，所以无效的重复操作仍受
        公共保护（且各自有局部上限）。`click_record_remove` 只能按名字整体移除，不动其它按钮的记录。
        """
        if not self._candidate_verified:
            return
        self._candidate_verified = False
        task = self.task
        names = (CANDIDATE_CONTROL, task.C_DOKAN_CANCEL_SELECT_DOKAN.name)
        removed = [task.device.click_record_remove(name) for name in names]
        logger.info(f'Welfare dokan: candidate verified and its detail closed, released click records {dict(zip(names, removed))}')

    def _relocate(self, candidate):
        """用指纹在最新一帧里重新定位候选，不使用旧坐标。"""
        for item in self._candidates():
            if same_card(item['fp'], candidate['fp']):
                return item
        return None

    def _check_candidate(self, candidate, threshold: int) -> str:
        task = self.task
        self._hide_popup()              # 上一个候选的详情必须先消失，否则读到的人数可能是上一个的
        self._candidate_verified = False
        current = self._relocate(candidate)
        if current is None:
            return 'relocate'
        execute_single_click(task.device, ClickBounds(tuple(current['box']), CANDIDATE_CONTROL))
        if not self._wait_for(task.I_CENTER_POINT_PEOPLE_NUMBER, POPUP_TIMEOUT):
            logger.info('Welfare dokan: no detail popup, skip candidate')
            return 'skip'
        if not self._wait_for(task.I_CENTER_CHALLENGE, CHALLENGE_TIMEOUT):
            logger.info('Welfare dokan: not challengeable, skip candidate')
            self._candidate_verified = True         # 详情已打开（有人数标志）、确认不可挑战：这个候选有了明确结论
            return 'skip'
        people = self._read_people()
        if people is None:
            logger.info('Welfare dokan: defender count unreadable, skip candidate')
            return 'skip'
        if people < threshold:
            logger.info(f'Welfare dokan: defenders {people} < {threshold}, skip candidate')
            self._candidate_verified = True         # 详情已打开并读到人数：这个候选有了明确结论
            return 'skip'
        logger.info(f'Welfare dokan: defenders {people} >= {threshold}, open')
        return 'open'

    def _wait_for(self, rule, timeout: float) -> bool:
        deadline = self.clock() + timeout
        while True:
            self._screenshot()
            if self.task.appear(rule):
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(0.3)

    def _read_people(self):
        """连续两次读到同一个数才采信（详情刚弹出时数字可能还在更新）。"""
        task = self.task
        previous = None
        for _ in range(4):
            self._screenshot()
            if not task.appear(task.I_CENTER_POINT_PEOPLE_NUMBER):
                return None
            task.O_DOKAN_CENTER_PEOPLE_NUMBER.roi = tuple(
                a + b for a, b in zip(task.I_CENTER_POINT_PEOPLE_NUMBER.roi_front, (0, 0, 0, 30)))
            match = PEOPLE_RE.search(task.O_DOKAN_CENTER_PEOPLE_NUMBER.detect_text(task.device.image) or '')
            value = int(match.group(1)) if match else None
            if value is not None and value == previous:
                return value
            previous = value
            self.sleep(0.3)
        return None

    def _swipe_list(self, rule=None) -> str:
        """滑一次列表并判定结果：'moved' / 'static' / 'not_sent'。`rule` 默认是向下翻页，回顶传反向滑动。

        - not_sent：`task.swipe` 没有真正发出（返回 False）。既不是推进也不是没动，不计入到底，由调用方有界处理；
        - 发出后先等列表停稳（含滚动 / 回弹，见 `_settle_list`），再拿「滑动前独立拷贝的基准帧」和「最终落点帧」
          比较右侧卡片内容有没有真的移动（`list_row_coverage`）：推进 → moved；稳定却没推进 → static；
        - 不看 `wait_for_changed_and_stable` 的 `changed`：它是过程中锁存的，到底时的短暂回弹最后回到原位
          也会置位，会被误当成推进（福利道馆 Bug D-03）；
        - 一直不稳定转人工，不当作到底；截图 / 设备异常原样向上传播。
        """
        task = self.task
        rule = rule or task.S_DOKAN_WELFARE_LIST_UP
        self._hide_popup()
        baseline = np.array(task.device.image)      # 独立拷贝：设备层复用图像缓冲时基准不能跟着变
        if not task.swipe(rule):
            logger.warning('Welfare dokan: list swipe was not sent, not counted as moved or static')
            return 'not_sent'
        final = self._settle_list(baseline)
        coverage, ratio = list_row_coverage(baseline, final)
        moved = coverage >= LIST_MOVED_ROW_COVERAGE
        logger.info(
            f'Welfare dokan: list swipe {"moved" if moved else "static"} '
            f'(changed rows {coverage:.2f} vs line {LIST_MOVED_ROW_COVERAGE}, changed pixels {ratio:.3f})')
        if not moved:
            logger.info('Welfare dokan: static swipe, its click records are kept')
            return 'static'
        self._release_swipe_records(rule.name)
        return 'moved'

    def _release_swipe_records(self, name=None):
        """确认本次滑动真实推进之后，只移除福利滑动自己的操作记录（Bug D-04）。

        公共 `Device.handle_control_check` 在滑动**发出前**就写入记录并检查，同名累计 10 次抛
        GameTooManyClickError；长列表每次都是有效推进，不清就会在第 10 次滑动前被误伤。只有「已发出且 moved」
        才走到这里；static / not_sent / 未稳定 / 异常都不清，所以无效滑动仍受公共保护约束。
        `click_record_remove` 按 `str(button)` 匹配，RuleSwipe 没有 `__str__`，必须传名字（与记录的
        `control_name=swipe.name` 同一个字符串）；不清其它按钮的记录。
        """
        name = name or self.task.S_DOKAN_WELFARE_LIST_UP.name
        removed = self.task.device.click_record_remove(name)
        logger.info(f'Welfare dokan: list advanced, released {removed} click record(s) of {name}')

    def _settle_list(self, baseline, what: str = '滑动列表后'):
        """等滑动（或刷新）后的列表真正停下来，返回最终落点那一帧（独立拷贝）。有界：每轮观察都有 timeout，轮数有限。

        `wait_for_changed_and_stable` 只保证「曾经变化 + 此刻相邻帧安静」，到底回弹中途的短暂停顿也满足；
        所以稳定之后还要再取 SWIPE_HOLD_FRAMES 帧确认没有再漂移，漂移就以最新一帧为新起点重新观察。
        """
        task = self.task
        anchor, timeout = baseline, SWIPE_OBSERVE_TIMEOUT
        for attempt in range(1, SWIPE_SETTLE_TRIES + 2):
            result = self._observe_list(anchor, timeout)
            final = np.array(task.device.image)
            if result.stable and self._holds_still(final):
                logger.info(f'Welfare dokan: list settled (observe #{attempt}, {result.frames_checked} frames, '
                            f'{result.elapsed:.1f}s, hold {SWIPE_HOLD_FRAMES} frames ok)')
                return final
            logger.info(f'Welfare dokan: list not settled at observe #{attempt} (stable={result.stable})')
            anchor, timeout = np.array(task.device.image), SWIPE_SETTLE_TIMEOUT
        self._human(f'{what}画面一直在变化、没有稳定下来，无法可靠识别候选，已停止（不当作到底 / 不当作刷新成功）。')

    def _holds_still(self, final) -> bool:
        for _ in range(SWIPE_HOLD_FRAMES):
            self._screenshot()
            if frame_difference(final, self.task.device.image, roi=LIST_BOX) > LIST_STABLE_THRESHOLD:
                return False
        return True

    def _observe_list(self, baseline, timeout: float):
        task = self.task

        def frame():
            task.screenshot()
            return task.device.image

        return wait_for_changed_and_stable(
            baseline, frame, roi=LIST_BOX, changed_threshold=LIST_CHANGED_THRESHOLD,
            stable_threshold=LIST_STABLE_THRESHOLD, stable_frames=2, timeout=timeout, clock=self.clock)

    def _refresh_list(self):
        """刷新候选列表并确认新一批已就绪（游戏刷新费用逐次递增，业务上不设次数上限，但一次刷新的点击和等待有界）。

        与普通模式 `find_dokan` 共用同样的两个资源（C_DOKAN_REFRESH 点刷新、I_REFRESH_ENSURE 点确认），但普通模式的
        做法（`ui_click` + 无超时的 `ui_click_until_disappear` + 睡 3 秒，并受 `find_dokan_refresh_count` 限制）
        既无界也不确认结果，所以这里是有界版本，不受那个次数上限影响。「确认」是全屏模板匹配，别的弹窗上的「确认」
        也会命中，所以确认框消失不能证明列表刷新了：还要看页面回到找馆页、列表稳定下来，并且内容相对刷新前有变化。
        弹窗出不来 / 关不掉 / 页面没回来 / 列表一直没变化，都转人工，不把旧列表当成新一批。
        """
        task = self.task
        self._screenshot()
        before = np.array(task.device.image)        # 刷新前（到底时）的列表：只用来判断刷新后内容有没有变
        for _ in range(REFRESH_TRIES):
            task.click(task.C_DOKAN_REFRESH)
            if self._wait_for(task.I_REFRESH_ENSURE, 4.0):
                if not task.ui_click_until_disappear(task.I_REFRESH_ENSURE, interval=1.5, timeout=10, max_clicks=3):
                    self._human('确认刷新后确认框没有消失，已停止。')
                break
        else:
            self._human('点击刷新后没有出现确认框（可能货币不足或被游戏限制），已停止。')
        self._await_refreshed_list(before)

    def _await_refreshed_list(self, before):
        task = self.task
        deadline = self.clock() + REFRESH_PAGE_TIMEOUT
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN) and not task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN) \
                    and not task.appear(task.I_REFRESH_ENSURE):
                break
            if self.clock() >= deadline:
                self._human('确认刷新后没有回到找馆页（或仍有确认框），无法确认刷新结果，已停止。')
            self.sleep(0.5)
        for attempt in range(1, REFRESH_LOAD_ROUNDS + 1):
            final = self._settle_list(before, what='刷新后')
            coverage, ratio = list_row_coverage(before, final)
            logger.info(f'Welfare dokan: refreshed list check #{attempt}: changed rows {coverage:.2f} '
                        f'(line {REFRESH_CHANGED_COVERAGE}), changed pixels {ratio:.3f}')
            if coverage >= REFRESH_CHANGED_COVERAGE:
                return
        self._human('刷新确认后列表内容一直没有变化（可能被游戏限制 / 货币不足，或新列表恰好与旧的完全相同），'
                    '无法确认刷新生效，已停止，不重复检查旧列表。')

    def _list_down_rule(self):
        """回顶用的反向滑动：把现有向下翻页滑动 S_DOKAN_WELFARE_LIST_UP 的起终点对调（同一列表区域、同一 x 范围）。"""
        if self._list_down is None:
            up = self.task.S_DOKAN_WELFARE_LIST_UP
            self._list_down = RuleSwipe(roi_front=up.roi_back, roi_back=up.roi_front, mode=up.mode, name=LIST_DOWN_NAME)
        return self._list_down

    def _scroll_list_to_top(self):
        """刷新后确认列表在起始位置：没有刷新后位置的真机证据，所以不假设回顶——连续反向滑动，直到连续两次
        「稳定且没推进」（同 D-03 到底判据）才算已在顶部；推进次数、没发出的次数都有上限。"""
        rule = self._list_down_rule()
        static = unsent = moves = 0
        while True:
            verdict = self._swipe_list(rule)
            if verdict == 'not_sent':
                unsent += 1
                if unsent >= SWIPE_SEND_TRIES:
                    self._human(f'回顶时连续 {unsent} 次滑动列表都没有发出，无法确认列表在起始位置，已停止。')
                continue
            unsent = 0
            if verdict == 'moved':
                static = 0
                moves += 1
                if moves >= TOP_MAX_MOVES:
                    self._human(f'回顶滑动已有效推进 {moves} 次仍没有到顶，已停止。')
                continue
            static += 1
            if static >= SWIPE_NO_CHANGE_LIMIT:
                logger.info(f'Welfare dokan: list top confirmed ({moves} reverse move(s), {static} static)')
                return

    def _confirm_open(self) -> bool:
        """点挑战 → 确认；以地图出现「进行中」横幅为开启成功的依据。返回 False = 这个馆没开成，继续找。"""
        task = self.task
        if not task.ui_click_until_appear_or_timeout(
                task.I_CENTER_CHALLENGE, stop=task.I_CHALLENGE_ENSURE, interval=1.5, timeout=10):
            logger.info('Welfare dokan: no challenge confirm dialog, continue searching')
            return False
        self.opened += 1                # 点「确认」是有副作用的一步：先记账，之后任何异常都按已开馆处理
        task.ui_click_until_disappear(task.I_CHALLENGE_ENSURE, interval=1.5, timeout=10, max_clicks=3)
        deadline = self.clock() + OPEN_CONFIRM_TIMEOUT
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN) or task.appear(task.I_RYOU_DOKAN_CHECK):
                logger.info('Welfare dokan: dokan opened')
                return True
            if self.clock() >= deadline:
                self._human('确认开启后没有看到进行中的道馆，无法确认是否已开成，请人工处理。')
            self.sleep(0.5)

    # ------------------------------------------------------------------ D. 集结 → 准备 → 立即关闭
    def _enter_prepare_and_close(self):
        """集结 → 开始挑战 → 准备页点准备 → 立即关闭游戏。

        保护衔接（见 GATHER_UNKNOWN_TOLERANCE 的说明）：
        - 只有「道馆页 + 集结中」两个证据同时在的帧，才清一次公共卡死计时（正常集结可以等到业务总时限）；
          清除在本帧识别之后进行，所以下一次 screenshot() 前的公共检查看到的总是刚清过的计时；
        - 业务总时限 `deadline` 从进入本阶段起算，识别和清计时都不会重置它；
        - 可开始挑战的帧不清计时：它靠点击本身（点击会清计时）推进，点击次数有上限，不能靠它一直续命；
        - 其余画面（过渡 / 未知）不清计时，容忍时间小于公共 60 秒，到点转人工并说明原因；
        - 本方法没有登记任何特殊等待状态，也不捕获异常，退出（含异常）后公共保护不受影响。
        """
        task = self.task
        self._screenshot()
        if not task.appear(task.I_RYOU_DOKAN_CHECK):
            task.goto_page(pages.page_dokan)
        started = self.clock()
        deadline = started + GATHER_TIMEOUT
        logger.info(f'Welfare dokan: enter gather wait (business limit {GATHER_TIMEOUT:.0f}s)')
        unknown_since = None
        challenge_clicks = 0
        last_click_at = None
        gather_logged = False
        next_log = started + GATHER_LOG_INTERVAL
        while True:
            self._screenshot()
            if task.appear(task.I_PREPARE_HIGHLIGHT):
                # 核心时序：这一帧识别到可点击的准备 → 点击 → 点击接口返回 → 立即关闭游戏。
                # 中间不截图、不 sleep、不等战斗开始、不进通用战斗循环（日志放在点击之前 / 关闭之后）。
                logger.info('Welfare dokan: prepare button seen, click then close the game immediately')
                x, y = task.I_PREPARE_HIGHLIGHT.coord()
                execute_single_click(task.device, FinalPoint(x, y), control_name=task.I_PREPARE_HIGHLIGHT.name)
                task.device.app_stop()
                logger.info('Welfare dokan: prepare clicked, game stop requested')
                return
            now = self.clock()
            if now >= deadline:
                self._human(f'等待集结 / 挑战开放超时（{GATHER_TIMEOUT:.0f} 秒），没有进入可点击的准备页，请人工处理。')
            gathering = task.appear(task.I_RYOU_DOKAN_GATHERING)
            if gathering and task.appear(task.I_RYOU_DOKAN_CHECK):
                unknown_since = None
                task.device.stuck_record_clear()
                if not gather_logged:
                    gather_logged = True
                    logger.info('Welfare dokan: gathering page seen (waiting is allowed; public stuck timers '
                                'are only kept alive while this page is recognised)')
                elif now >= next_log:
                    logger.info(f'Welfare dokan: still gathering, {now - started:.0f}s elapsed')
                if now >= next_log:
                    next_log = now + GATHER_LOG_INTERVAL
            elif not gathering and task.appear(task.I_RYOU_DOKAN_START_CHALLENGE):
                unknown_since = None
                if challenge_clicks >= GATHER_START_CLICK_LIMIT:
                    if now - last_click_at >= GATHER_START_OBSERVE:
                        self._human(f'已点击「开始挑战」{challenge_clicks} 次仍没有进入准备页，点击无效，已停止，请人工处理。')
                elif task.appear_then_click(task.I_RYOU_DOKAN_START_CHALLENGE, interval=2):
                    challenge_clicks += 1
                    last_click_at = now
                    logger.info(f'Welfare dokan: gather over, start challenge clicked '
                                f'{challenge_clicks}/{GATHER_START_CLICK_LIMIT}')
            elif unknown_since is None:
                unknown_since = now
                logger.info('Welfare dokan: frame is neither the gathering page nor a startable challenge; '
                            f'tolerated for up to {GATHER_UNKNOWN_TOLERANCE:.0f}s, stuck timers are not kept alive')
            elif now - unknown_since >= GATHER_UNKNOWN_TOLERANCE:
                self._human(f'集结阶段连续 {now - unknown_since:.0f} 秒停在既不是集结页也不是可开始挑战的画面，'
                            '无法确认现场，已停止，请人工处理。')
            self.sleep(1.0)

    # ------------------------------------------------------------------ E. 确认关闭 → 等 10 分钟
    def _confirm_closed(self) -> float:
        """进程查询两次都确认不存在才算关闭；查询异常和「还在」都不算，超时转人工。返回确认时刻。"""
        task = self.task
        deadline = self.clock() + CLOSE_CONFIRM_TIMEOUT
        gone = 0
        last_error = None
        stopped_again = False
        while self.clock() < deadline:
            try:
                exists = task.device.app_process_exists()
            except Exception as error:
                last_error = error
                gone = 0
            else:
                if exists:
                    gone = 0
                    if not stopped_again and self.clock() > deadline - CLOSE_CONFIRM_TIMEOUT / 2:
                        stopped_again = True
                        task.device.app_stop()
                else:
                    gone += 1
                    if gone >= 2:
                        return self.clock()
            self.sleep(0.5)
        self._human(f'无法确认游戏已关闭（进程仍在或查询失败：{last_error!r}），未开始 10 分钟计时，请人工处理。')

    @contextmanager
    def _excluded_from_active(self):
        """业务等待期间不计入疲劳活跃时长，也不计入 Script 的防沉迷活跃时长；不产生任何恢复。"""
        task = self.task
        started = self.clock()
        manager = get_fatigue_manager(task.config.config_name, task.config.global_game.fatigue)
        with manager.suspend_active():
            try:
                yield
            finally:
                spent = max(0.0, self.clock() - started)
                data = task.config.__dict__
                data['excluded_active_seconds'] = float(data.get('excluded_active_seconds', 0.0) or 0.0) + spent

    def _wait(self, seconds: float):
        start = self.clock()
        while True:
            remain = seconds - (self.clock() - start)
            if remain <= 1e-6:      # 浮点残差：虚拟时钟下 now 很大时再加极小值不会前进
                return
            self.sleep(min(WAIT_CHUNK_SECONDS, remain))

    def _wait_closed(self, closed_at: float):
        logger.info(f'Welfare dokan: game closed, wait {CLOSED_WAIT_SECONDS}s (not counted as active time)')
        with self._excluded_from_active():
            self._wait(CLOSED_WAIT_SECONDS - (self.clock() - closed_at))

    # ------------------------------------------------------------------ F. 重启 → 返回本馆
    def _default_login(self):
        from tasks.Component.Login.service import LoginService
        LoginService(config=self.task.config, device=self.task.device).app_handle_login()

    def _restart_and_return(self):
        task = self.task
        task.device.app_start()
        task.device.wait_app_start_ready()
        self._login()
        task.goto_page(pages.page_dokan_map)
        for _ in range(8):
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                # 「集」字整屏搜索会命中底部「道馆突破集结中」：资源 roi_back 已排除底栏，这里再要求恰好一个
                matches = match_boxes(task.I_DOKAN_AGAIN_ENTER, task.I_DOKAN_AGAIN_ENTER.match_all_any(task.device.image))
                if len(matches) == 1:
                    x, y, w, h = matches[0]
                    point = FinalPoint(x + w // 2 + BADGE_OFFSET[0], y + h // 2 + BADGE_OFFSET[1])
                    execute_single_click(task.device, point, control_name='dokan_welfare_return_badge')
                    if self._wait_for(task.I_RYOU_DOKAN_CHECK, 10.0):
                        logger.info('Welfare dokan: back inside the dokan')
                        return
                elif len(matches) > 1:
                    logger.warning(f'Welfare dokan: {len(matches)} return markers, ambiguous')
            self.sleep(1.0)
        self._human(
            '重启后没有在地图上唯一定位到本次道馆的返回标志（集结丝带），不盲点，请人工处理。'
            '如果丝带在这个阶段会变样，需要补一张重启后地图的整屏截图。'
        )

    # ------------------------------------------------------------------ G. 放弃 → 再战 → 2 分钟
    def _abandon(self, want_again: bool) -> str:
        """放弃本馆并处理投票。返回 'again'（已选再战）或 'finished'（没有投票，机会已用完）。"""
        task = self.task
        if not task.ui_click_until_appear_or_timeout(
                task.I_DOKAN_ABANDONED_TOPPA, stop=task.I_DOKAN_ABANDONED_TOPPA_ENSURE, interval=1.5, timeout=10):
            self._human('没有出现放弃确认框，无法放弃本馆，请人工处理。')
        task.ui_click_until_disappear(task.I_DOKAN_ABANDONED_TOPPA_ENSURE, interval=1.5, timeout=10, max_clicks=2)
        deadline = self.clock() + ABANDON_TIMEOUT
        while self.clock() < deadline:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_TOPPA_RANK):
                task.click(task.C_DOKAN_TOPPA_RANK_CLOSE_AREA, interval=2)
            elif task.appear(task.I_DOKAN_ABANDONED_TOPPA_TITLE) and task.appear(task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED):
                # 「放弃 / 继续」投票阶段：选放弃
                task.appear_then_click(task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED, interval=2)
            elif task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                # 「保留赏金 / 再战道馆」投票阶段（与上面的标题不同时出现）
                if not want_again:
                    self._human('最后一馆放弃后出现了「再战 / 保留赏金」投票，与剩余机会不符，不选择，请人工处理。')
                if self._read_count(retries=3) != 1:
                    self._human('投票阶段读不到「剩余 1 次」，无法确认还有下一次机会，不选择，请人工处理。')
                self._vote_again()
                return 'again'
            elif task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO) or \
                    task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
                return 'finished'
            self.sleep(0.5)
        self._human('放弃后没有出现预期的投票或收尾画面，请人工处理。')

    def _vote_again(self):
        """点一次「再战道馆」（绝不点保留赏金），确认**本方**选择成功后才返回；否则转人工。

        成功依据（缺一不可，且都不依赖任意区域变化）：
        1. 点击真的发出（`appear_then_click` 返回 True）；限流没发出的调用不算，最多重试 `VOTE_CLICK_TRIES` 次；
        2. 只看「再战道馆」按钮自己的框（点击时的匹配框，不含票数 / 倒计时）相对点击前**变化并稳定**，
           且最后稳定的那一帧仍与点击前不同（短暂漏识别、闪一下又回到原样不算）——动画不稳定、票数变化都过滤掉；
        3. 稳定那一帧仍在投票界面（还能看到「再战道馆」或「保留赏金」），无关页面切换不算。

        只点一次：没有「重复点击不会取消选择」的证据，所以确认不了就不再点。缺的画面：点「再战道馆」之后、
        投票阶段还没结束时的整屏截图（本方选中后的样式）。有了它可以换成明确的选中模板。
        """
        task = self.task
        for _ in range(VOTE_CLICK_TRIES):
            self._screenshot()
            baseline = np.array(task.device.image)
            if not task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                self.sleep(0.4)
                continue
            if not task.appear_then_click(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                logger.info('Welfare dokan: vote click was throttled (not sent), try again')
                self.sleep(0.4)
                continue
            x, y, w, h = (int(v) for v in task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN.roi_front)
            roi = (x, y, x + w, y + h)

            def frame():
                task.screenshot()
                return task.device.image

            result = wait_for_changed_and_stable(
                baseline, frame, roi=roi, changed_threshold=VOTE_CHANGED_THRESHOLD,
                stable_threshold=VOTE_STABLE_THRESHOLD, stable_frames=2, timeout=VOTE_CONFIRM_TIMEOUT,
                clock=self.clock)
            still_voting = task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN) or \
                task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY)
            if result.success and result.last_difference >= VOTE_CHANGED_THRESHOLD and still_voting:
                return
            self._human(
                '点击「再战道馆」后无法可靠确认本方选择成功（按钮框没有稳定的、仍与点击前不同的变化，'
                '或已不在投票界面），未启动 120 秒等待，请人工处理。缺少「点再战道馆后、投票阶段的整屏截图」，'
                '补上后可改用明确的选中样式模板确认。'
            )
        self._human('「再战道馆」点击多次都没有真正发出（被点击限流），无法投票，请人工处理。')

    def _wait_again(self):
        # 选择成功后才开始；只计时一次（调用点不在任何循环里）。游戏保持开启，计入真实活跃时长
        logger.info(f'Welfare dokan: vote confirmed, wait {AGAIN_WAIT_SECONDS}s before the next dokan')
        self._wait(AGAIN_WAIT_SECONDS)
        # 与公共卡死保护衔接：`Device.screenshot()` 在取画面之前先 `stuck_record_check()`，判定同时要求「距最近一次
        # 清除超过 60 秒」和「自那以后的检查次数 > 60」。这 120 秒没有截图，时间条件一定满足；投票确认阶段（再战点击之后
        # 的「变化并稳定」等待，截图间隔 0.1～0.3 秒）累计的检查次数不固定，一旦 > 60，等待结束后的第一次截图就会在识别
        # 页面之前被判成卡死。这里是一段有明确业务依据、已经等满的固定等待，只在它正常结束之后清一次计时（异常 / 停止信号
        # 不会走到这里，没有 finally）；不动点击记录，也不留任何豁免，之后的无进展照常由公共保护判定。
        self.task.device.stuck_record_clear()
