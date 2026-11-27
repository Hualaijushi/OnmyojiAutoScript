# This Python file uses the following encoding: utf-8
"""福利道馆模式：只找「鑫」馆，开馆进准备页点准备、缓冲 1.85 秒后关游戏，10 分钟后返回本馆放弃，选「再战道馆」。

只在 DokanConfig.welfare_mode 打开时由 `ScriptTask.run` 进入，普通道馆流程不经过这里。

设计边界（首版）：
- 不做进程中断后的续跑：启动时已经有进行中的道馆一律转人工；开过馆之后再出现自动恢复类异常
  也转人工，避免公共 Restart 把流程从头跑一遍、误开下一馆或误放弃当前馆。
- 前置公共步骤不能漏：每一馆在找「鑫」之前都重新确认我方道馆已建立（没有就复用普通模式的建馆流程，
  见 `_ensure_own_dokan`）：第一馆在进入找馆页后、预设之前；第二馆在再战点击后回庭院、等满 120 秒、返回并确认找馆页之后。
  阵容预设仍只做一次（`preset_done`）。
- 所有「等」都有上限或可被进程终止打断；业务上不设刷新次数上限，但每一步的点击 / 等待有界，
  明确的游戏限制（刷新弹窗出不来等）转人工，不做高频连点。
- 页面状态一律以资源匹配为准，没有确认依据的步骤不盲点：缺什么画面见各步骤的提示。
"""
import random
import re
import time
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np

from module.atom.frame_state import DEFAULT_PIXEL_THRESHOLD, frame_difference
from module.base.frame_wait import FrameWaitResult
from module.base.utils import save_image
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
from module.server.log_service import ERROR_LOG_ROOT, build_error_log_dir_name
import tasks.Dokan.page as pages
from tasks.Dokan.assets import DokanAssets
from tasks.GlobalGame.assets import GlobalGameAssets

# 调度器会自动 Restart 并重新拉起任务的异常（见 Script._handle_task_exception）
AUTO_RECOVERED_ERRORS = (
    GameStuckError, GameTooManyClickError, GameBugError, GamePageUnknownError, GameNotRunningError,
)

MAX_DOKAN_PER_RUN = 2
CLOSED_WAIT_SECONDS = 600       # 确认游戏已关闭后等待
AGAIN_WAIT_SECONDS = 120        # 再战点击实际发出（接口正常返回）起算的总时长（游戏保持开启）：回庭院的导航耗时包含在内，只补等剩余
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
LIST_BOTTOM = 600               # 列表可见区域下沿：卡片截取范围超出它说明被裁切，本屏不检查
# 返回本馆：「集」字在「集结」丝带上，徽章在它右上方（按 2026-10-25 整屏截图量得）
BADGE_OFFSET = (84, -100)
# 选「再战道馆」：用户 2026-11-26 调整确认口径——放弃确认后约 1 秒会弹出战绩/排名遮罩（其中「击败排名」不含
# 「突破排名」模板而右端又露出「再战道馆」按钮，导致旧流程隔遮罩误点后立刻退馆）。现流程为：
# 1) 放弃确认消失后等待 ABANDON_POPUP_WAIT_SECONDS，先点安全右侧空白区 C_DOKAN_TOPPA_RANK_CLOSE_AREA 关掉弹窗；
# 2) 点击「再战道馆」后有界确认该标识连续 VOTE_GONE_FRAMES 帧消失（且未出现排名遮罩），仍在时补点，上限 VOTE_MAX_CLICKS 次；
# 3) 确认消失后按生效那次点击时刻起算 120 秒，并立即走原有路径回庭院。
ABANDON_POPUP_WAIT_SECONDS = 1.5  # 放弃确认框消失后等待战绩弹窗弹出时长（分段可中断）
VOTE_MAX_CLICKS = 3             # 实际发出「再战道馆」点击的次数上限（迟到未识别弹窗吃掉首击时有界补点）
VOTE_CLICK_TRIES = 3            # 只统计「没有真正发出」的调用（按钮没找到 / 点击被限流）
VOTE_DISAPPEAR_TIMEOUT = 3.0    # 每次点击「再战道馆」后等待该标识消失的观察时限
VOTE_GONE_FRAMES = 2            # 连续这么多帧既看不到「再战道馆」也看不到排名遮罩才确认点击生效
# 放弃后会先出结算弹窗/排名遮罩（需先点掉才能点到后面的「再战道馆」）；
# 遮罩下的按钮仍能被模板匹配到，而点在遮罩上只会关掉遮罩、不会选中再战（2026-10-29 / 2026-11-26 oas2 实测）。
RANK_CLOSE_TIMEOUT = 10.0       # 关闭遮罩并确认它消失的总时限
RANK_CLOSE_CLICK_LIMIT = 4      # 关闭遮罩实际发出的点击上限
RANK_GONE_FRAMES = 2            # 连续这么多帧都看不到遮罩才算关掉（挡住渐隐中途的漏识别）
VOTE_MASK_ROUNDS = 3            # 投票方法里「发现遮罩 → 关闭 → 重新截图」的次数上限
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
SWIPE_UNKNOWN_OBSERVES = 1      # 推进结论 unknown 且当前屏回退扫描无合格「鑫」后，至多补 1 次同一落点观察（只截图、不滑），仍 unknown 转人工
SWIPE_REBOUND_CONSECUTIVE_LIMIT = 1  # 连续允许「疑似触底过冲回弹」复位重滑的最大次数；紧接着仍反向或未知则转人工
SWIPE_REBOUND_BATCH_LIMIT = 2        # 同一批次内允许回弹复位重滑的总次数上限，防止同批内反复震荡
# 变化行占比（`list_row_coverage`）：列表滚动哪怕 1 px，整列卡片的文字 / 徽记 / 边框都会错位，几乎每一行都有变化像素
# （按 2026-10-28 报错截图合成 1 px 位移量得约 84% 的行）；角标 / 闪光动画只影响局部几行（合成角标整体闪动约 24%，
# 连徽记一起整块噪声约 57%，属于偏极端的合成上限）。它用于落点确认里「大面积变化」(wide) 的线及刷新后变化检测；
# 滑动是否推进改由单卡锚点匹配（`list_progress`）判定。
LIST_CHANGED_THRESHOLD = 0.02   # 等待层的「相对滑动前有变化」线：只用来让 FrameWait 在变化且稳定后提前返回，不决定推进
LIST_STABLE_THRESHOLD = 0.01    # 相邻帧变化像素占比 <= 它才算安静
LIST_ROW_CHANGED = 0.05         # 一行里变化像素占比 >= 它，这一行才算「变了」
LIST_MOVED_ROW_COVERAGE = 0.65
OBSERVE_STABLE_FRAMES = 2       # 观察层连续这么多帧内容安静即判稳定（与原 wait_for_changed_and_stable 一致）
OBSERVE_LOCAL_RATIO_MAX = 0.05  # 观察层相邻帧变化 > 1% 且判为 local 时，允许放过的原地局部动画像素占比上限
OBSERVE_LOCAL_ROWS_MAX = 0.35   # 观察层允许放过的原地局部动画变化行占比上限（3 个动态徽记约 0.10，半屏级噪点仍拒绝）
OBSERVE_MAX_POLLS = 1_000_000   # 防止异常/未推进 clock 导致观察循环死锁的轮询上限
# 落点确认（`_hold_failure`）只回答「列表内容有没有还在动」，不回答「画面是否逐像素不变」：
# 与落点帧比较时，没有位移的局部变化（角标 / 徽记 / 闪光 / 渐变发光）可以放过；整体竖直平移（滚动 / 漂移 / 回弹）
# 和大面积变化必须拦住。数值只在「真实列表截图 + 合成帧」上验证过，没有 oas1 的真实连续帧（见 docs/AI_CONTEXT.md）。
HOLD_SHIFT_MAX = 150            # 试探内容整体竖直平移的最大位移（px）；更大的位移靠变化行占比拦（稠密列表）
HOLD_SHIFT_GAIN = 0.5           # 平移后的变化像素占比不超过不平移时的这个比例，才判定是内容在平移（不是局部变化）
# 滑动推进判据（DOKAN-SWIPE-ANCHOR-01，单卡身份区锚点匹配）：
# 在滑动前新鲜图像的 LIST_BOX 有效可见区内，取最下方「战力条→馆名区」身份区域完整且在当前屏唯一的馆卡（不要求带「鑫」），
# 用高通处理后的战力数字带与馆名带做 OpenCV 刚体模板匹配（避开徽记、右上角标动画、固定金圆图标与外边框），
# 在停稳后的整列中搜索同一张卡并算「滑前 y - 滑后 y」：
# - 数值在三张真实列表裁图（oas1 10-28、oas2 10-26/27）及其合成平移 / 抖动 / 动画 / 变暗样本上标定，未经真机连续帧核验；
# - 真实同卡（含徽记+角标重动画、-60 变暗或亚像素模糊微扰）联合相关 >= 0.88、单带 >= 0.85、次佳峰 <= 0.37；
# - 异卡 / 换页联合相关 <= 0.43，重复卡片次佳峰约 1.0（分差不足被拒）。
PROGRESS_BLUR_SIGMA = 3.0       # 高通用的高斯模糊 sigma（抵消整列变暗与大块缓慢发光）
ANCHOR_LIST_TOP = 22            # LIST_BOX 顶部木质装饰栏下沿（y < 22 为顶栏，不参与卡片定位与模板搜索）
ANCHOR_POWER_DY = (-22, -2)     # 相对战力条下沿 e 的战力数字带纵坐标范围（高 20 px）
ANCHOR_POWER_X = (76, 142)      # 相对 LIST_BOX 左沿的战力数字 +「万」横坐标范围（避开左侧固定金圆图标）
ANCHOR_NAME_DY = (2, 24)        # 相对战力条下沿 e 的馆名带纵坐标范围（高 22 px）
ANCHOR_NAME_X = (24, 148)       # 相对 LIST_BOX 左沿的馆名横坐标范围（避开左右外边框）
ANCHOR_BAR_X = (26, 145)        # 检测战力深色底条→米白馆名背景明暗阶跃的横坐标范围
ANCHOR_BAR_STEP_MIN = 40.0      # 馆名背景中位亮度 - 战力条中位亮度的最小阶跃
ANCHOR_POLARITY_MIN = 50.0      # 战力亮字对比（p95 - med）与馆名暗字对比（med - p05）的最小幅值
ANCHOR_CARD_NMS = 90            # 相邻馆卡战力条下沿的最小纵距（真实卡片节距约 146 px）
# 滑前锚点候选的赏金图标校验（复用 I_RIGHTPAD_POINT_BOUNTY 27x29 局部灰度模板，仅验证疑似赏金条位置）：
# 校验在相近候选 NMS 之前执行，排除底部仅露徽记的半张卡误判并防止挤掉上方完整卡；前后两帧仍只用战力数字与馆名匹配。
ANCHOR_BOUNTY_X = 1125 - LIST_BOX[0]    # 预期左上角在 LIST_BOX 内的横坐标（屏幕 x≈1125，不依赖可变 roi_front）
ANCHOR_BOUNTY_DY = -30                  # 预期左上角相对赏金条下沿 e 的纵偏移（屏幕 y≈下沿 y-30）
ANCHOR_BOUNTY_X_PAD = 3                 # 赏金图标校验横向允许偏差（±3 px）
ANCHOR_BOUNTY_Y_PAD = 4                 # 赏金图标校验纵向允许偏差（±4 px）
ANCHOR_BOUNTY_MATCH_MIN = 0.80          # 赏金图标灰度归一化匹配（TM_CCOEFF_NORMED）下限
ANCHOR_X_PAD = 4                # 模板匹配允许的水平微偏移（±4 px，战力与馆名共享同一刚体水平偏移）
ANCHOR_MIN_STD = 8.0            # 高通后的战力带 / 馆名带各自最小标准差（过滤空白 / 极低纹理）
ANCHOR_MATCH_MIN = 0.80         # 战力带与馆名带联合相关系数下限
ANCHOR_PART_MIN = 0.70          # 战力带与馆名带各自相关系数下限（防止单带巧合误配）
ANCHOR_MARGIN_MIN = 0.15        # 最佳峰与排除邻域外次佳峰的最小分差（拒绝重复卡片或得分歧义）
ANCHOR_PEAK_WINDOW = 10         # 歧义检测排除最佳纵坐标附近 ±10 px
ANCHOR_STATIC_TOLERANCE = 2     # |滑前 y - 滑后 y| <= 此像素视为同卡回到原位（允许少量回弹/子像素定位抖动）
ANCHOR_REBOUND_MAX = 150        # 允许判定为「触底过冲回弹复位」的最大反向位移幅度（约 1 张馆卡高 146px）；更大反向位移直接按 unknown 转人工
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
# 点准备的点击接口返回之后、调用 app_stop 之前的缓冲（用户 2026-10-29 实测后确定；离线后没有自动战斗，怀疑关得太快，
# 但服务端具体卡在哪一步没有证明）。待实测的策略，不保证足以触发离线自动战斗；不计入 600 秒离线等待
PREPARE_CLOSE_BUFFER_SECONDS = 1.85
ABANDON_TIMEOUT = 90.0
BACK_TO_FIND_TIMEOUT = 90.0
RETURN_NAV_TRIES = 3                # 再战返回时按已识别页面导航回地图的次数上限（导航返回后重新截图仍不是找馆页才会再来一次）
RETURN_UNKNOWN_TOLERANCE = 30.0     # 再战返回时连续认不出页面的容忍时间：只重新识别，不点任何返回键，到点转人工
REFRESH_TRIES = 3
REFRESH_PAGE_TIMEOUT = 6.0          # 确认刷新之后等「找馆页」重新出现的上限
REFRESH_LOAD_ROUNDS = 3             # 刷新后列表一直没变化时最多再观察几轮（每轮自带有界稳定等待）
# 刷新后「列表内容变了」的判据：落点稳定后的列表与点刷新前（到底时）的列表比较变化行占比（同 `list_row_coverage`）。
# 比滑动的 0.65 低得多：刷新后列表可能保留部分相同候选、也可能很短（只有 1～2 张卡片，整列只有约 25% 的行有内容）。
# 没有真机的刷新前后画面，取值未校准；每次刷新都会把实测值写进日志，供真机校准
REFRESH_CHANGED_COVERAGE = 0.05
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


def _list_gray(image):
    """LIST_BOX 的灰度裁剪（独立的连续数组，不引用设备图像缓冲）。"""
    x1, y1, x2, y2 = LIST_BOX
    region = np.ascontiguousarray(np.asarray(image)[y1:y2, x1:x2])
    return cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region


def list_content_shift(anchor, frame):
    """试探 LIST_BOX 内容有没有整体竖直平移：返回 (最佳位移 px, 该位移下的变化像素占比, 不位移时的变化像素占比)。

    位移 s > 0 表示 frame 的内容比 anchor 上移了 s 行。只在两帧差异已经超过稳定线时才调用（见 `list_change_kind`）。
    三个数都按灰度算（只为比较「平移前后谁更像」，一次试探只要零点几毫秒；与 `list_row_coverage` 的逐通道占比不是同一个量）。
    """
    a, b = _list_gray(anchor), _list_gray(frame)
    height = a.shape[0]

    def changed(shift):
        pa, pb = (a[shift:], b[:height - shift]) if shift >= 0 else (a[:height + shift], b[-shift:])
        return int(np.count_nonzero(cv2.absdiff(pa, pb) > DEFAULT_PIXEL_THRESHOLD)) / pa.size

    best = (0, 1.0)
    for shift in range(-HOLD_SHIFT_MAX, HOLD_SHIFT_MAX + 1):
        if shift:
            ratio = changed(shift)
            if ratio < best[1]:
                best = (shift, ratio)
    return best[0], best[1], changed(0)


def list_change_kind(anchor, frame):
    """落点帧与之后一帧在 LIST_BOX 内的差异性质，返回 dict(kind, ratio, rows, shift, shifted_ratio)。

    - same：变化像素占比不超过稳定线，视为没变；
    - shifted：内容整体竖直平移（平移后差异明显更小）——还在滚动 / 漂移 / 回弹；
    - wide：变化行占比达到「推进」线（`LIST_MOVED_ROW_COVERAGE`，与 D-03 同一条线），大面积变化，不是局部动画；
    - local：其余——内容没有位移，只有局部视觉变化（角标 / 徽记 / 闪光 / 渐变），不影响候选定位。
    稠密列表里 1 px 的滚动就会让约 84% 的行变化，所以 wide 能拦住任何速度的滚动；稀疏列表（只有一两张卡片）
    1 px 滚动只有约 20% 的行变化，只能靠 shifted 的平移检验拦（位移超过 `HOLD_SHIFT_MAX` 时稀疏列表拦不住，见文档）。
    """
    coverage, ratio = list_row_coverage(anchor, frame)
    info = {'kind': 'same', 'ratio': ratio, 'rows': coverage, 'shift': 0, 'shifted_ratio': None, 'unshifted_ratio': None}
    if ratio <= LIST_STABLE_THRESHOLD:
        return info
    shift, shifted_ratio, unshifted_ratio = list_content_shift(anchor, frame)
    info.update(shift=shift, shifted_ratio=shifted_ratio, unshifted_ratio=unshifted_ratio)
    # unshifted_ratio == 0 时（只有色差、亮度几乎不变）没有比较意义，不能判平移
    if unshifted_ratio > 0 and shifted_ratio <= unshifted_ratio * HOLD_SHIFT_GAIN:
        info['kind'] = 'shifted'
    elif coverage >= LIST_MOVED_ROW_COVERAGE:
        info['kind'] = 'wide'
    else:
        info['kind'] = 'local'
    return info


def _is_observe_local_stable(info: dict) -> bool:
    """观察层相邻帧变化是否属于可放过的有界原地局部动画（无整体平移、无大面积变化、幅度在局部徽记上界内）。"""
    return (
        info['kind'] == 'local'
        and info['ratio'] <= OBSERVE_LOCAL_RATIO_MAX
        and info['rows'] <= OBSERVE_LOCAL_ROWS_MAX
    )


def _list_highpass(gray):
    """LIST_BOX 的高通灰度图（+128 偏移的 uint8）：抵消整列变暗与大块缓慢发光，保留文字与数字轮廓。"""
    f = gray.astype(np.float32)
    high = f - cv2.GaussianBlur(f, (0, 0), PROGRESS_BLUR_SIGMA)
    return np.clip(high + 128, 0, 255).astype(np.uint8)


_BOUNTY_ICON_TEMPLATE = None


def _bounty_icon_template():
    """复用现有 `I_RIGHTPAD_POINT_BOUNTY` 赏金图标素材，按与 `_list_gray` 一致的灰度转换加载并缓存局部模板。"""
    global _BOUNTY_ICON_TEMPLATE
    if _BOUNTY_ICON_TEMPLATE is None:
        icon = DokanAssets.I_RIGHTPAD_POINT_BOUNTY.image
        gray_icon = cv2.cvtColor(icon, cv2.COLOR_BGR2GRAY) if icon.ndim == 3 else icon
        _BOUNTY_ICON_TEMPLATE = np.ascontiguousarray(gray_icon, dtype=np.uint8)
    return _BOUNTY_ICON_TEMPLATE


def _bounty_icon_score(gray, e: int) -> float:
    """在疑似赏金条下沿 e 左侧预期位置做小范围灰度归一化模板匹配；搜索区不足或零纹理返回 -1.0。"""
    tpl = _bounty_icon_template()
    th, tw = tpl.shape[:2]
    h, w = gray.shape[:2]
    vis_bottom = min(LIST_BOTTOM - LIST_BOX[1], h)
    exp_x = ANCHOR_BOUNTY_X
    exp_y = e + ANCHOR_BOUNTY_DY
    x0 = max(0, exp_x - ANCHOR_BOUNTY_X_PAD)
    x1 = min(w, exp_x + tw + ANCHOR_BOUNTY_X_PAD)
    y0 = max(0, exp_y - ANCHOR_BOUNTY_Y_PAD)
    y1 = min(vis_bottom, exp_y + th + ANCHOR_BOUNTY_Y_PAD)
    if (x1 - x0) < tw or (y1 - y0) < th:
        return -1.0
    roi = gray[y0:y1, x0:x1]
    if float(roi.std()) < 1e-3:
        return -1.0
    res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
    return float(res.max())


def _find_card_bar_edges(gray):
    """在 LIST_BOX 灰度图内定位所有身份区（战力数字 + 馆名）完整且左侧可验证赏金图标的馆卡下沿 y，按从下到上返回。

    严格顺序：找到疑似阶跃下沿 → 验证身份区域完整与赏金图标 → 排除相近的重复候选（NMS）→ 从下往上返回。
    半张卡的假位置在 NMS 之前过滤，避免挤掉上方完整卡；图标只用于验证赏金条位置，不参与前后帧同卡匹配。
    """
    h, w = gray.shape[:2]
    vis_bottom = min(LIST_BOTTOM - LIST_BOX[1], h)
    min_e = ANCHOR_LIST_TOP - ANCHOR_POWER_DY[0]
    max_e = vis_bottom - ANCHOR_NAME_DY[1]
    px0, px1 = ANCHOR_POWER_X
    nx0, nx1 = ANCHOR_NAME_X
    if max_e < min_e or h < 40 or w < max(px1, nx1):
        return []

    row_med = np.median(gray[:, ANCHOR_BAR_X[0]:ANCHOR_BAR_X[1]], axis=1).astype(np.float32)
    step_arr = np.zeros(h, dtype=np.float32)
    for y in range(18, h - 18):
        step_arr[y] = float(row_med[y + 2:y + 18].mean() - row_med[y - 16:y - 2].mean())

    candidates = np.zeros(h, dtype=np.float32)
    for y in range(max(18, min_e - 4), min(h - 18, max_e + 5)):
        step = step_arr[y]
        if step < ANCHOR_BAR_STEP_MIN:
            continue
        # 必须是局部阶跃峰，避免被上下沿裁切卡片拖到边界
        if step < float(step_arr[max(0, y - 6):min(h, y + 7)].max()):
            continue
        lo, hi = max(18, y - 6), min(h - 18, y + 7)
        grad = row_med[lo + 2:hi + 2] - row_med[lo - 2:hi - 2]
        e = lo + int(np.argmax(grad))
        # 验证身份区域完整（战力带在顶栏下、馆名带在列表可见下沿内）
        if not (min_e <= e <= max_e):
            continue
        p1_inner = gray[e - 18:e - 4, px0:px1]
        p2 = gray[e + ANCHOR_NAME_DY[0]:e + ANCHOR_NAME_DY[1], nx0:nx1]
        if p1_inner.size == 0 or p2.size == 0:
            continue
        p1_med = float(np.median(p1_inner))
        p1_hi = float(np.percentile(p1_inner, 95))
        p2_med = float(np.median(p2))
        p2_lo = float(np.percentile(p2, 5))
        if (p1_hi - p1_med) < ANCHOR_POLARITY_MIN or (p2_med - p2_lo) < ANCHOR_POLARITY_MIN \
                or (p2_med - p1_med) < ANCHOR_BAR_STEP_MIN:
            continue
        # 在排除相近重复候选（NMS）之前先校验左侧赏金图标，防止半张卡假下沿挤掉上方完整卡
        if _bounty_icon_score(gray, e) < ANCHOR_BOUNTY_MATCH_MIN:
            continue
        if step > candidates[e]:
            candidates[e] = step

    edges = []
    while True:
        idx = int(np.argmax(candidates))
        if candidates[idx] <= 0:
            break
        edges.append(idx)
        candidates[max(0, idx - ANCHOR_CARD_NMS):min(h, idx + ANCHOR_CARD_NMS + 1)] = 0
    return sorted(edges, reverse=True)


def _match_anchor_in_highpass(target_hp, power_patch, name_patch):
    """用 OpenCV TM_CCOEFF_NORMED 在有效可见区内刚体匹配「战力带 + 馆名带」，返回最佳纵坐标与分离度。"""
    vis_bottom = min(LIST_BOTTOM - LIST_BOX[1], target_hp.shape[0])
    vis = target_hp[ANCHOR_LIST_TOP:vis_bottom]
    px0, px1 = ANCHOR_POWER_X
    nx0, nx1 = ANCHOR_NAME_X
    r_pow = cv2.matchTemplate(vis[:, px0 - ANCHOR_X_PAD:px1 + ANCHOR_X_PAD], power_patch, cv2.TM_CCOEFF_NORMED)
    r_name = cv2.matchTemplate(vis[:, nx0 - ANCHOR_X_PAD:nx1 + ANCHOR_X_PAD], name_patch, cv2.TM_CCOEFF_NORMED)
    gap = ANCHOR_NAME_DY[0] - ANCHOR_POWER_DY[0]
    rows = min(r_pow.shape[0], r_name.shape[0] - gap)
    if rows <= 0:
        return None
    comb = 0.5 * (r_pow[:rows, :] + r_name[gap:gap + rows, :])
    row_best_x = np.argmax(comb, axis=1)
    row_scores = comb[np.arange(rows), row_best_x]
    best_i = int(np.argmax(row_scores))
    best_x = int(row_best_x[best_i])
    best_score = float(row_scores[best_i])
    power_score = float(r_pow[best_i, best_x])
    name_score = float(r_name[best_i + gap, best_x])
    best_e = ANCHOR_LIST_TOP + best_i - ANCHOR_POWER_DY[0]

    mask = np.ones(rows, dtype=bool)
    mask[max(0, best_i - ANCHOR_PEAK_WINDOW):min(rows, best_i + ANCHOR_PEAK_WINDOW + 1)] = False
    second_score = float(row_scores[mask].max()) if mask.any() else -1.0
    return {
        'e': best_e,
        'score': best_score,
        'power_score': power_score,
        'name_score': name_score,
        'second': second_score,
    }


def extract_list_anchor(image):
    """从滑动前新鲜图像中选取最下方身份区域完整且在当前屏唯一的馆卡锚点（不要求带「鑫」）。"""
    gray = _list_gray(image)
    hp = _list_highpass(gray)
    edges = _find_card_bar_edges(gray)
    if not edges:
        reason = 'low_texture' if float(hp[ANCHOR_LIST_TOP:min(LIST_BOTTOM - LIST_BOX[1], hp.shape[0])].std()) < ANCHOR_MIN_STD else 'no_anchor'
        return None, reason, {'candidates': 0, 'self_second': None}

    px0, px1 = ANCHOR_POWER_X
    nx0, nx1 = ANCHOR_NAME_X
    fail_reason = 'no_anchor'
    best_self_second = None
    for e in edges:
        power = hp[e + ANCHOR_POWER_DY[0]:e + ANCHOR_POWER_DY[1], px0:px1]
        name = hp[e + ANCHOR_NAME_DY[0]:e + ANCHOR_NAME_DY[1], nx0:nx1]
        if float(power.std()) < ANCHOR_MIN_STD or float(name.std()) < ANCHOR_MIN_STD:
            fail_reason = 'low_texture'
            continue
        self_match = _match_anchor_in_highpass(hp, power, name)
        if self_match is None:
            fail_reason = 'no_anchor'
            continue
        self_second = self_match['second']
        best_self_second = self_second if best_self_second is None else min(best_self_second, self_second)
        if (1.0 - self_second) < ANCHOR_MARGIN_MIN or abs(self_match['e'] - e) > 2:
            fail_reason = 'ambiguous'
            continue
        return {
            'e': e,
            'before_y': LIST_BOX[1] + e,
            'power': power,
            'name': name,
            'self_second': self_second,
            'candidates': len(edges),
        }, None, {'candidates': len(edges), 'self_second': self_second}
    return None, fail_reason, {'candidates': len(edges), 'self_second': best_self_second}


def nominal_swipe_info(rule) -> dict:
    """计算滑动规则的名义起点、终点中心与名义纵向位移（向上滑为正），与实际内容位移分开记录。"""
    fx = rule.roi_front[0] + rule.roi_front[2] // 2
    fy = rule.roi_front[1] + rule.roi_front[3] // 2
    bx = rule.roi_back[0] + rule.roi_back[2] // 2
    by = rule.roi_back[1] + rule.roi_back[3] // 2
    return {
        'name': rule.name,
        'start': (fx, fy),
        'end': (bx, by),
        'nominal_dy': fy - by,
    }


def list_progress(before, after, *, anchor=None):
    """滑动前基准帧与停稳后落点帧之间的单卡锚点位移判断（DOKAN-SWIPE-ANCHOR-01）。返回 dict：

    kind = moved / static / unknown，reason（unknown 原因；moved / static 为 None），
    before_y / after_y（锚点馆卡战力条下沿的屏幕纵坐标；未知时可为 None），
    dy / shift（滑前 y - 滑后 y，> 0 = 内容上移即向下翻页），
    score / power_score / name_score / second / margin / self_second / candidates。

    判据：
    - 默认从 before 取最下方身份区完整且本屏唯一的馆卡（战力数字 + 馆名，不含徽记 / 角标 / 边框），
      也可由调用方传入发手势前已取得的 `anchor`，在停稳后的 after 有效可见区做刚体模板匹配；
    - 得分不足或单带不足 → unknown (anchor_missing)；次佳峰分差不足 → unknown (ambiguous)；
    - |dy| <= ANCHOR_STATIC_TOLERANCE → static（允许少量回弹/子像素定位抖动）；
    - dy < -ANCHOR_STATIC_TOLERANCE → unknown (wrong_direction)；
    - dy > ANCHOR_STATIC_TOLERANCE → moved（唯一同卡可信上移，不被旧整列差异否决）。
    帧形状不一致抛 ValueError。
    """
    if np.asarray(before).shape != np.asarray(after).shape:
        raise ValueError(f'两帧形状不一致：{np.asarray(before).shape} vs {np.asarray(after).shape}')

    result = {
        'kind': 'unknown',
        'reason': None,
        'before_y': None,
        'after_y': None,
        'dy': None,
        'shift': 0,
        'score': None,
        'power_score': None,
        'name_score': None,
        'second': None,
        'margin': None,
        'self_second': None,
        'candidates': 0,
    }
    if anchor is None:
        anchor, fail_reason, meta = extract_list_anchor(before)
        result.update(candidates=meta['candidates'], self_second=meta['self_second'])
        if anchor is None:
            result['reason'] = fail_reason
            return result
    else:
        result.update(candidates=anchor['candidates'], self_second=anchor['self_second'])

    after_hp = _list_highpass(_list_gray(after))
    matched = _match_anchor_in_highpass(after_hp, anchor['power'], anchor['name'])
    result['before_y'] = anchor['before_y']
    if matched is None:
        result['reason'] = 'anchor_missing'
        return result

    after_y = LIST_BOX[1] + matched['e']
    dy = anchor['before_y'] - after_y
    margin = matched['score'] - matched['second']
    result.update(
        after_y=after_y,
        score=matched['score'],
        power_score=matched['power_score'],
        name_score=matched['name_score'],
        second=matched['second'],
        margin=margin,
    )
    if matched['score'] < ANCHOR_MATCH_MIN or matched['power_score'] < ANCHOR_PART_MIN \
            or matched['name_score'] < ANCHOR_PART_MIN:
        result['reason'] = 'anchor_missing'
        return result
    if margin < ANCHOR_MARGIN_MIN:
        result['reason'] = 'ambiguous'
        return result

    result.update(dy=dy, shift=dy)
    if abs(dy) <= ANCHOR_STATIC_TOLERANCE:
        result['kind'] = 'static'
    elif dy < -ANCHOR_STATIC_TOLERANCE:
        result['reason'] = 'wrong_direction'
    else:
        result['kind'] = 'moved'
    return result


def progress_text(info) -> str:
    """`list_progress` 结果的单行日志文字（包含滑前 / 滑后 y、实际 dy 或未知原因）。"""
    if info['score'] is None:
        self_next = f', self_next={info["self_second"]:.3f}' if info['self_second'] is not None else ''
        return (f'{info["kind"]} (reason={info["reason"]}: anchor before_y={info["before_y"]} '
                f'after_y={info["after_y"]} actual_dy=unknown, candidates={info["candidates"]}{self_next})')
    reason = f'reason={info["reason"]}: ' if info['reason'] else ''
    dy_text = f'{info["dy"]:+d}px' if info['dy'] is not None else 'unknown'
    return (f'{info["kind"]} ({reason}anchor before_y={info["before_y"]} after_y={info["after_y"]} '
            f'actual_dy={dy_text}, score={info["score"]:.3f} '
            f'[pow={info["power_score"]:.3f} name={info["name_score"]:.3f}], '
            f'next={info["second"]:.3f}, margin={info["margin"]:.3f}, self_next={info["self_second"]:.3f}; '
            f'min_score={ANCHOR_MATCH_MIN:.2f}, min_part={ANCHOR_PART_MIN:.2f}, '
            f'min_margin={ANCHOR_MARGIN_MIN:.2f}, static_tol=±{ANCHOR_STATIC_TOLERANCE}px)')


def _is_recoverable_rebound(info) -> bool:
    """判定是否属于可经「复位后重滑」恢复的疑似触底过冲回弹。

    要求 `list_progress` 已通过高置信度单卡锚点匹配并判为 `wrong_direction`，且反向回落幅度在
    `ANCHOR_REBOUND_MAX` 以内（`0 < -dy <= ANCHOR_REBOUND_MAX`）。
    """
    return (
        info.get('kind') == 'unknown'
        and info.get('reason') == 'wrong_direction'
        and info.get('dy') is not None
        and 0 < -info['dy'] <= ANCHOR_REBOUND_MAX
    )


class WelfareDokan:
    def __init__(self, task, *, clock=time.monotonic, sleep=time.sleep, login=None):
        self.task = task
        self.clock = clock
        self.sleep = sleep
        self._login = login or self._default_login
        self.opened = 0              # 已经点过「确认开启」的馆数（有副作用的步骤，防重复）
        self.preset_done = False
        self.own_dokan_checked = False   # 最近一次我方道馆建立检查已通过（每馆开始前重置，只在确认回到找馆页之后才设置；不是跨馆缓存）
        self._candidate_verified = False  # 刚检查完的候选已经形成有效业务结论（详情打开并读到结论），等它的详情关闭后再释放操作记录
        self._again_deadline = None       # 再战点击实际发出时建立的唯一 120 秒截止时刻（单调时钟）；等完剩余时间后清除
        self._hold_locals = []            # 最近一次落点确认中被放过的局部变化（只用于日志）
        self._observe_locals = []         # 最近一次观察层中被放过的原地局部动画（只用于日志）
        self._last_swipe_had_unknown = False  # 本次滑动是否曾出现 unknown（未知后转 static 不能与未知前的疑似到底拼成确认到底）

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
        total = min(count, MAX_DOKAN_PER_RUN)
        opened_before = self.opened
        for index in range(total):
            last = index + 1 >= total
            self._ensure_own_dokan()      # 用户 2026-11-01：每一馆找「鑫」之前都重新检查，不复用上一馆的结果
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
                # 用户 2026-11-02：120 秒从再战点击发出起算，点完立即回庭院（导航耗时包含在 120 秒内），确认到达后只等剩余时间
                self._return_to_courtyard()
                self._wait_again()
                self._back_to_find_page(after_rematch=True)
                rematch_count = self._read_count()
                if rematch_count is None:
                    self._human(
                        '返回找馆页准备第二馆前无法识别今日剩余挑战机会（投票时已确认剩余 1 次，'
                        '未知不能当作 0，也不进入第二馆），请人工确认。'
                    )
                if rematch_count == 0:
                    logger.info(
                        'Welfare dokan: rematch count recheck on find page is 0 (exhausted/done), '
                        'skipping second dokan and finishing normally with 0'
                    )
                    return 0
                if rematch_count == 2:
                    logger.warning(
                        'Welfare dokan: rematch count mismatch (投票时 1 次，回找馆页后 2 次), '
                        'stopping before second dokan'
                    )
                    self._human(
                        '返回找馆页准备第二馆前识别到今日剩余挑战机会不一致（投票时 1 次，回找馆页后 2 次），'
                        '不进入第二馆，也不写入该次数，请人工确认。'
                    )
                logger.info('Welfare dokan: rematch count recheck on find page is 1, continuing to second dokan')
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
        - 每一馆开始前都调用，每次都重新识别当时的实际建馆状态；`own_dokan_checked` 进入时先清零，
          只在建立 / 已建立并确认回到找馆页之后才设置，失败和异常出口都不设置（不是跨馆缓存，不会让第二馆跳过检查）。
        """
        self.own_dokan_checked = False
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

    def _return_to_courtyard(self, timeout: float = BACK_TO_FIND_TIMEOUT):
        """再战点击发出后立即回庭院（计入 120 秒，截止时刻见 `_start_again_timer`）：复用现有 `goto_page(page_main)`，
        到达由新截图 + 页面识别确认，不把「调用返回」当作到达。

        - 游戏已自动回庭院时，第一帧识别到庭院就直接返回，不导航、不点任何返回键；
        - 地图上仍有进行中的馆：转人工，不导航；
        - 认不出的页面：只重新识别，不点任何键，连续 `RETURN_UNKNOWN_TOLERANCE` 秒认不出转人工；
        - 导航返回后新截图仍不是庭院，最多再导航 `RETURN_NAV_TRIES` 次，用尽转人工；
        - 导航自己的无进展超时抛 `GamePageUnknownError`、截图 / 停止信号原样向上传播，已开馆之后由 `run()` 转人工；
          不重新投票、不重新计时，也没有 finally；时间已超过 120 秒也不会因此跳过导航失败，失败就是失败。
        之后由 `_wait_again` 只补等剩余时间，再由 `_back_to_find_page(after_rematch=True)` 复用既有导航进入道馆地图并确认找馆页。
        """
        task = self.task
        deadline = self.clock() + timeout
        navigations = 0
        unknown_since = None
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                self._human('再战之后地图上仍有进行中的道馆，无法确认现场，没有回庭院，请人工处理。')
            page = task.get_current_page()
            if page == pages.page_main:
                logger.info('Welfare dokan: back in the courtyard (confirmed by a fresh screenshot)')
                return
            if page is None:
                now = self.clock()
                unknown_since = now if unknown_since is None else unknown_since
                if now - unknown_since >= RETURN_UNKNOWN_TOLERANCE:
                    self._human(f'再战之后连续 {now - unknown_since:.0f} 秒认不出当前页面，没有点任何返回键，'
                                '无法回到庭院，已停止，请人工处理。')
                self.sleep(1.0)
                continue
            unknown_since = None
            navigations += 1
            if navigations > RETURN_NAV_TRIES:
                self._human(f'已按识别到的页面导航回庭院 {RETURN_NAV_TRIES} 次，新截图仍然不是庭院，已停止，请人工处理。')
            logger.info(f'Welfare dokan: after the rematch wait the game is on {page}, go to the courtyard through the '
                        f'existing navigation ({navigations}/{RETURN_NAV_TRIES})')
            task.goto_page(pages.page_main, timeout=max(5, int(deadline - self.clock())))

    def _back_to_find_page(self, timeout: float = BACK_TO_FIND_TIMEOUT, after_rematch: bool = False):
        """回到地图找馆页。找馆页 → 直接返回；进行中的馆 → 转人工；其余按原来点黄色返回键（预设返回等调用者）。

        `after_rematch`（只有再战之后的回地图传 True）：这时页面由游戏自己决定——放弃后游戏内约一分钟倒计时，倒计时结束
        游戏会自动回庭院，它与程序等的 120 秒是两个独立计时；现在程序会先回庭院再补等剩余时间，进入这里时通常已在庭院
        （也可能是别的页面）。此时不再点黄色返回键逐层退（它只对部分页面有效），而是：重新截图 → 用现有页面识别
        （`task.get_current_page`，两帧稳定）确认当前在哪一页 → 已识别就复用现有 `goto_page(page_dokan_map)`
        （庭院 → 寮 → 神社 → 道馆地图；道馆页 → 退出图标 → 退出确认）→ 导航返回后一律用新截图确认到达，不把
        「调用返回」当作到达。认不出页面只重新识别，不点任何返回键，连续 `RETURN_UNKNOWN_TOLERANCE` 秒认不出转人工。
        `goto_page` 的 `timeout` 是**无进展**超时（页面变化 / 点击推进会重置，不是总时限），这里传入剩余时间做上界，
        外层 deadline 并不能中断它；它超时抛 `GamePageUnknownError`，已开馆之后由 `run()` 转人工，不会重新投票或重新等待。
        """
        task = self.task
        deadline = self.clock() + timeout
        navigations = 0
        unknown_since = None
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN) and not task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                return
            if self.clock() >= deadline:
                break
            if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                self._human('回到地图后发现存在进行中的道馆，无法确认现场，请人工处理。')
            if after_rematch:
                page = task.get_current_page()
                if page is None:
                    now = self.clock()
                    unknown_since = now if unknown_since is None else unknown_since
                    if now - unknown_since >= RETURN_UNKNOWN_TOLERANCE:
                        self._human(f'再战之后连续 {now - unknown_since:.0f} 秒认不出当前页面，没有点任何返回键，'
                                    '无法回到地图找馆页，已停止，请人工处理。')
                    self.sleep(1.0)
                    continue
                unknown_since = None
                navigations += 1
                if navigations > RETURN_NAV_TRIES:
                    self._human(f'已按识别到的页面导航 {RETURN_NAV_TRIES} 次，仍然没有回到地图找馆页，已停止。')
                logger.info(f'Welfare dokan: after the rematch wait the game is on {page}, go to the dokan map through the '
                            f'existing navigation ({navigations}/{RETURN_NAV_TRIES})')
                task.goto_page(pages.page_dokan_map, timeout=max(5, int(deadline - self.clock())))
                continue
            task.appear_then_click(GlobalGameAssets.I_UI_BACK_YELLOW, interval=1.5)
            self.sleep(0.5)
        self._human('没有回到找馆页，已停止。')

    # ------------------------------------------------------------------ C. 严格找馆
    def _find_and_open(self):
        """遍历右侧列表找「鑫」馆：人数 >= 门槛且可挑战的第一个。业务上不设刷新次数上限。

        首次进入、刷新成功后（以及第二馆回到找馆页后）都直接从当前画面开始扫描，不做反向回顶：用户 2026-11-05 现场确认
        这几种情况下列表都已在顶部（旧的回顶是缺少位置证据时的保守做法，每次刷新多两次反向滑动）。
        """
        refreshes = 0
        while True:
            self._ensure_find_page()
            if self._scan_list_once():
                return
            refreshes += 1
            logger.info(f'Welfare dokan: list exhausted, refresh #{refreshes}')
            self._refresh_list()
            logger.info(f'Welfare dokan: refresh #{refreshes} done, scan the new batch from the current (top) position')

    def _find_page_flags(self):
        """基于当前最新截图 `task.device.image` 判断是否为可操作的找馆页（不额外截图、不加等待）。

        复用 `_await_refreshed_list` 同一组页面标志：可见 `I_RYOU_DOKAN_FINDING_DOKAN`，
        且不可见 `I_RYOU_DOKAN_FOUND_DOKAN` 与 `I_REFRESH_ENSURE`。
        """
        task = self.task
        finding = bool(task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN))
        found = bool(task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN))
        refresh_ensure = bool(task.appear(task.I_REFRESH_ENSURE))
        return finding and not found and not refresh_ensure, {
            'finding': finding,
            'found': found,
            'refresh_ensure': refresh_ensure,
        }

    def _save_page_check_evidence(self, stage: str, headline: str, images, flags: dict):
        """找馆页确认未通过时按现有 `save_error` 开关一次性留图并写明页面标志（不逐帧写盘）。"""
        try:
            if not getattr(self.task.config.script.error, 'save_error', False):
                logger.info(f'Welfare dokan: save_error is off, find page check evidence not saved ({stage})')
                return None
            folder = Path(ERROR_LOG_ROOT) / build_error_log_dir_name(self.task.config.config_name, int(time.time() * 1000))
            folder.mkdir(parents=True, exist_ok=True)
            for filename, frame in images:
                save_image(np.asarray(frame), str(folder / filename))
            flag_text = f'finding={flags["finding"]}, found={flags["found"]}, refresh_ensure={flags["refresh_ensure"]}'
            lines = [
                f'福利道馆：{headline}',
                f'阶段：{stage}',
                f'页面标志：{flag_text}',
                '图片：' + '；'.join(name for name, _ in images),
            ]
            (folder / 'log.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            logger.warning(f'Welfare dokan: find page check evidence saved to {folder} ({stage})')
            return folder
        except Exception as error:
            logger.warning(f'Welfare dokan: saving find page check evidence failed ({stage}): {error!r}')
            return None

    def _abort_invalid_find_page(self, stage: str, headline: str, images, flags: dict, detail: str):
        """找馆页确认不通过时的统一收口：记警告日志、按开关留图、转人工（不发手势/不点候选/不计静止/不刷新）。"""
        flag_text = f'finding={flags["finding"]}, found={flags["found"]}, refresh_ensure={flags["refresh_ensure"]}'
        logger.warning(f'Welfare dokan: {headline} ({stage}, {flag_text})')
        folder = self._save_page_check_evidence(stage, headline, images, flags)
        where = f'诊断截图与页面状态已保存到 {folder}。' if folder else ''
        self._human(f'{headline}（{flag_text}），{detail}。{where}')

    def _verify_find_page_on_current_frame(self, stage: str, headline: str, detail: str, *, extra_images=()):
        """用当前最新截图做找馆页身份确认；通过则返回该同一帧的独立拷贝，不通过则留图转人工。"""
        current = np.array(self.task.device.image)
        ok, flags = self._find_page_flags()
        if ok:
            return current
        images = [*extra_images, (f'welfare_list_{stage}_page_invalid.png', current)]
        self._abort_invalid_find_page(stage, headline, images, flags, detail)

    def _scan_visible_candidates(self, checked, threshold, *, verify_find_page: bool = False):
        """按现有逻辑从上到下扫描整张当前屏的「鑫」候选。返回 ('opened' | 'done', acted)。"""
        relocates = 0
        acted = False
        while True:
            self._hide_popup()
            relocate = False
            for candidate in self._candidates(verify_find_page=verify_find_page, stage='fallback_scan_candidates'):
                if any(same_card(candidate['fp'], old) for old in checked):
                    continue
                acted = True
                verdict = self._check_candidate(candidate, threshold, verify_find_page=verify_find_page)
                if verdict == 'relocate':
                    relocate = True     # 列表动过了：回到循环顶重新识别，不用旧坐标
                    relocates += 1
                    if relocates >= RELOCATE_LIMIT:
                        self._human(f'连续 {relocates} 次点击前都无法在最新画面里重新定位候选馆（没有任何进展），已停止。')
                    break
                relocates = 0
                checked.append(candidate['fp'])
                if verdict == 'open' and self._confirm_open():
                    return 'opened', acted
            if not relocate:
                return 'done', acted

    def _scan_list_once(self) -> bool:
        """从上到下检查当前可见的每个「鑫」，检查完滑动；连续两次实际发出的滑动均可靠停回原位才算到底（返回 False）。"""
        threshold = self.task.config.dokan.dokan_config.welfare_min_people
        checked = []
        unchanged = 0
        unsent = 0
        rebound_consecutive = 0
        rebound_batch = 0
        while True:
            scan_verdict, _ = self._scan_visible_candidates(checked, threshold)
            if scan_verdict == 'opened':
                return True
            can_rebound_retry = (
                rebound_consecutive < SWIPE_REBOUND_CONSECUTIVE_LIMIT
                and rebound_batch < SWIPE_REBOUND_BATCH_LIMIT
            )
            verdict = self._swipe_list(
                on_unknown=lambda: self._scan_visible_candidates(checked, threshold, verify_find_page=True),
                allow_rebound_recovery=can_rebound_retry,
            )
            if verdict == 'opened':
                return True
            if verdict == 'not_sent':
                # 没发出的滑动既不是推进也不是没动：不碰连续 static 与回弹计数，但连续发不出去要有界退出
                unsent += 1
                if unsent >= SWIPE_SEND_TRIES:
                    self._human(f'连续 {unsent} 次滑动列表都没有发出，无法判断列表是否到底，已停止（不当作到底）。')
                continue
            unsent = 0
            if verdict == 'rebounded':
                if unchanged:
                    logger.info('Welfare dokan: clearing prior suspected bottom after overscroll rebound reset')
                unchanged = 0
                rebound_consecutive += 1
                rebound_batch += 1
                logger.info(
                    f'Welfare dokan: rebound reset handled (consecutive {rebound_consecutive}/{SWIPE_REBOUND_CONSECUTIVE_LIMIT}, '
                    f'batch {rebound_batch}/{SWIPE_REBOUND_BATCH_LIMIT}), re-scanning from current settled screen'
                )
                continue
            rebound_consecutive = 0
            if verdict == 'moved':
                if unchanged:
                    logger.info('Welfare dokan: confirmation swipe moved, cleared suspected bottom state')
                unchanged = 0
                continue
            if self._last_swipe_had_unknown:
                # 未知不等于静止，也不能把未知前的疑似静止与未知后的结果拼成到底确认
                if unchanged:
                    logger.info('Welfare dokan: clearing prior suspected bottom after unknown swipe, '
                                'cannot combine into bottom confirmation')
                unchanged = 0
            unchanged += 1
            if unchanged < SWIPE_NO_CHANGE_LIMIT:
                logger.info(f'Welfare dokan: suspected bottom (anchor back at original position), '
                            f'list static streak {unchanged}/{SWIPE_NO_CHANGE_LIMIT}, will confirm with one more swipe')
            else:
                logger.info(f'Welfare dokan: list static streak {unchanged}/{SWIPE_NO_CHANGE_LIMIT}')
                logger.info('Welfare dokan: list bottom confirmed, hand over to refresh')
                return False

    def _candidates(self, *, verify_find_page: bool = False, stage: str = 'fallback_scan_candidates'):
        task = self.task
        self._screenshot()
        if verify_find_page:
            self._verify_find_page_on_current_frame(
                stage,
                '回退扫屏重新截图后无法确认找馆页，已停止',
                '不点击候选、不计静止、不刷新',
            )
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

    def _relocate(self, candidate, *, verify_find_page: bool = False):
        """用指纹在最新一帧里重新定位候选，不使用旧坐标。"""
        for item in self._candidates(verify_find_page=verify_find_page, stage='fallback_scan_relocate'):
            if same_card(item['fp'], candidate['fp']):
                return item
        return None

    def _check_candidate(self, candidate, threshold: int, *, verify_find_page: bool = False) -> str:
        task = self.task
        self._hide_popup()              # 上一个候选的详情必须先消失，否则读到的人数可能是上一个的
        self._candidate_verified = False
        current = self._relocate(candidate, verify_find_page=verify_find_page)
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

    def _acquire_pre_swipe_anchor(self):
        """发滑动手势前先从最新画面提取可识别锚点；第一张失败则补拍一次并确认仍在可操作的找馆页，失败均留证转人工、不发手势。"""
        task = self.task
        shot1 = np.array(task.device.image)      # 独立拷贝：设备层复用图像缓冲时基准不能跟着变
        anchor, reason1, meta1 = extract_list_anchor(shot1)
        if anchor is not None:
            logger.info(f'Welfare dokan: pre-swipe anchor acquired on shot 1/2 '
                        f'(before_y={anchor["before_y"]}, candidates={anchor["candidates"]}, '
                        f'self_next={anchor["self_second"]:.3f})')
            return shot1, anchor
        logger.info(f'Welfare dokan: pre-swipe anchor unavailable on shot 1/2 '
                    f'(reason={reason1}, candidates={meta1["candidates"]}), retrying 1 screenshot before swipe')
        self._screenshot()
        shot2 = np.array(task.device.image)
        page_ok, flags = self._find_page_flags()
        if not page_ok:
            self._abort_invalid_find_page(
                'pre_swipe_retry',
                '滑前补拍后无法确认找馆页，滑动未发出',
                [('welfare_list_before_swipe_1.png', shot1), ('welfare_list_before_swipe_2_page_invalid.png', shot2)],
                flags,
                '已停止（未发手势、不计静止、不刷新）',
            )
        anchor, reason2, meta2 = extract_list_anchor(shot2)
        if anchor is not None:
            logger.info(f'Welfare dokan: pre-swipe anchor acquired on shot 2/2 '
                        f'(before_y={anchor["before_y"]}, candidates={anchor["candidates"]}, '
                        f'self_next={anchor["self_second"]:.3f})')
            return shot2, anchor
        logger.warning(f'Welfare dokan: 滑前锚点获取失败，滑动未发出 '
                       f'(shot1={reason1}/candidates={meta1["candidates"]}, '
                       f'shot2={reason2}/candidates={meta2["candidates"]})')
        folder = self._save_pre_swipe_anchor_evidence(shot1, shot2, reason1, meta1, reason2, meta2)
        where = f'滑前诊断截图与原因已保存到 {folder}。' if folder else ''
        self._human(f'滑前锚点获取失败，滑动未发出（第 1 张：{reason1}；补拍第 2 张：{reason2}），'
                    f'已停止（未发手势、未进入滑后等待、不计静止、不刷新）。{where}')

    def _save_pre_swipe_anchor_evidence(self, shot1, shot2, reason1, meta1, reason2, meta2):
        """两张滑前画面都取不到锚点时一次性保存诊断：两张均为滑动前画面 + 失败原因（受 `save_error` 控制）。"""
        try:
            if not getattr(self.task.config.script.error, 'save_error', False):
                logger.info('Welfare dokan: save_error is off, pre-swipe anchor evidence not saved')
                return None
            folder = Path(ERROR_LOG_ROOT) / build_error_log_dir_name(self.task.config.config_name, int(time.time() * 1000))
            folder.mkdir(parents=True, exist_ok=True)
            save_image(np.asarray(shot1), str(folder / 'welfare_list_before_swipe_1.png'))
            save_image(np.asarray(shot2), str(folder / 'welfare_list_before_swipe_2.png'))
            s1_next = f', self_next={meta1["self_second"]:.3f}' if meta1.get('self_second') is not None else ''
            s2_next = f', self_next={meta2["self_second"]:.3f}' if meta2.get('self_second') is not None else ''
            lines = [
                '福利道馆：滑前锚点获取失败，滑动未发出（连续 2 张滑动前画面均无法取得可用参照馆卡，未发手势、未进入滑后等待、不计静止、不刷新）。',
                f'滑动前第 1 张：reason={reason1}, candidates={meta1["candidates"]}{s1_next}',
                f'滑动前补拍第 2 张：reason={reason2}, candidates={meta2["candidates"]}{s2_next}',
                f'LIST_BOX={LIST_BOX}；有效搜索纵坐标 [{ANCHOR_LIST_TOP}, {LIST_BOTTOM})，'
                f'战力带 dy={ANCHOR_POWER_DY} x={ANCHOR_POWER_X}，馆名带 dy={ANCHOR_NAME_DY} x={ANCHOR_NAME_X}，'
                f'赏金图标校验 x={LIST_BOX[0] + ANCHOR_BOUNTY_X}±{ANCHOR_BOUNTY_X_PAD} '
                f'dy={ANCHOR_BOUNTY_DY}±{ANCHOR_BOUNTY_Y_PAD} score>={ANCHOR_BOUNTY_MATCH_MIN:.2f}。',
                '图片说明（两张均为滑动前画面，均未发出滑动手势）：',
                '- welfare_list_before_swipe_1.png = 滑动前第 1 张画面',
                '- welfare_list_before_swipe_2.png = 滑动前补拍第 2 张画面',
            ]
            (folder / 'log.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            logger.warning(f'Welfare dokan: pre-swipe anchor evidence saved to {folder}')
            return folder
        except Exception as error:
            logger.warning(f'Welfare dokan: saving pre-swipe anchor evidence failed: {error!r}')
            return None

    def _swipe_list(self, *, on_unknown=None, allow_rebound_recovery: bool = False) -> str:
        """向下翻页滑一次列表并判定结果：'moved' / 'static' / 'not_sent' / 'opened' / 'rebounded'
        （滑前无锚点或滑后仍 unknown 且不满足有界回弹复位条件则转人工）。

        - 先关闭详情并确认仍在同一找馆列表，在发手势前先取锚点（第一张失败补拍一次，两张均失败则留证转人工、不发手势）；
        - not_sent：`task.swipe` 没有真正发出（返回 False）。既不是推进也不是没动，不计入到底，保留记录；
        - 发出后先等列表停稳（含滚动 / 回弹，见 `_settle_list`），再用滑前取得的同一锚点做单卡身份区匹配（`list_progress`）
          计算「滑前 y - 滑后 y」：唯一同卡可信上移 → moved（仅释放本福利滑动记录）；停回原位（±抖动）→ static（保留记录）；
        - 滑前有锚点但滑后 unknown（锚点缺失 / 裁切 / 反向 / 歧义）：不计入 moved / static、不清操作记录、不刷新、
          不再发手势；若传入 `on_unknown`，先用现有逻辑扫完整个当前屏的「鑫」，找到合格候选则直接按原流程处理（返回 'opened'）；
          若开启 `allow_rebound_recovery` 且满足 `_is_recoverable_rebound(info)`（高置信度单卡整体回落且幅度 <= ANCHOR_REBOUND_MAX），
          则按有界触底过冲回弹复位返回 `'rebounded'`（由上层清零疑似到底计数后从当前停稳画面重滑确认）；
          否则至多补 SWIPE_UNKNOWN_OBSERVES（1）次同一滑动落点观察（只截图、不滑），仍 unknown 保存诊断后转人工；
        - 一直不稳定转人工，不按未停稳画面点候选；截图 / 设备异常、停止信号原样向上传播。
        """
        task = self.task
        rule = task.S_DOKAN_WELFARE_LIST_UP
        self._last_swipe_had_unknown = False
        self._hide_popup()
        if not self._find_page_flags()[0]:
            self._ensure_find_page()
            self._hide_popup()
            self._verify_find_page_on_current_frame(
                'pre_swipe_initial',
                '滑前无法确认找馆页，滑动未发出',
                '已停止（未发手势、不计静止、不刷新）',
            )
        baseline, anchor = self._acquire_pre_swipe_anchor()
        nominal = nominal_swipe_info(rule)
        logger.info(f'Welfare dokan: list swipe nominal gesture name={nominal["name"]} '
                    f'{nominal["start"]}->{nominal["end"]} nominal_dy={nominal["nominal_dy"]}px')
        if not task.swipe(rule):
            logger.warning('Welfare dokan: list swipe was not sent, not counted as moved or static')
            return 'not_sent'
        self._settle_list(baseline)
        final = self._verify_find_page_on_current_frame(
            'post_swipe_settle',
            '滑后停稳无法确认找馆页，已停止',
            '不采信推进/静止、不点候选、不刷新、不清除滑动记录',
            extra_images=[('welfare_list_1_before_swipe.png', baseline)],
        )
        info = list_progress(baseline, final, anchor=anchor)
        observed = 0
        fallback_scanned = False
        while info['kind'] == 'unknown':
            self._last_swipe_had_unknown = True
            logger.info(f'Welfare dokan: list swipe progress {progress_text(info)} '
                        f'(observation {observed + 1}/{SWIPE_UNKNOWN_OBSERVES + 1}, not counted, records kept)')
            if not fallback_scanned and on_unknown is not None:
                fallback_scanned = True
                logger.info(f'Welfare dokan: unknown progress fallback scan on current screen for xin '
                            f'(reason={info["reason"]})')
                scan_verdict, acted = on_unknown()
                if scan_verdict == 'opened':
                    logger.info('Welfare dokan: unknown fallback scan found and opened a qualified xin candidate')
                    return 'opened'
                if acted:
                    self._hide_popup()
                if not (allow_rebound_recovery and _is_recoverable_rebound(info)):
                    logger.info(f'Welfare dokan: unknown fallback scan found no qualified xin, '
                                f'running at most {SWIPE_UNKNOWN_OBSERVES} extra observation (screenshot only, no swipe)')
            if allow_rebound_recovery and _is_recoverable_rebound(info):
                logger.info(
                    f'Welfare dokan: suspected bottom overscroll rebound reset '
                    f'(before_y={info["before_y"]}, after_y={info["after_y"]}, actual_dy={info["dy"]:+d}px, '
                    f'max_rebound={ANCHOR_REBOUND_MAX}px); not counted as static, swipe records kept, '
                    'will re-swipe from current settled screen'
                )
                return 'rebounded'
            if observed >= SWIPE_UNKNOWN_OBSERVES:
                folder = self._save_progress_evidence(baseline, final, info, nominal=nominal)
                where = f'诊断截图与判据已保存到 {folder}。' if folder else ''
                self._human(f'滑动列表后连续 {observed + 1} 次观察都无法确认列表是否推进（{info["reason"]}），'
                            f'已停止（不当作到底 / 不当作推进，不刷新）。{where}')
            observed += 1
            self._settle_list(baseline)         # 只重新观察落点，不再滑动；基准仍是本次滑动前的那一帧
            final = self._verify_find_page_on_current_frame(
                'post_swipe_extra_observe',
                '滑后补观察停稳无法确认找馆页，已停止',
                '不采信推进/静止、不点候选、不刷新、不清除滑动记录',
                extra_images=[('welfare_list_1_before_swipe.png', baseline)],
            )
            info = list_progress(baseline, final, anchor=anchor)
        logger.info(f'Welfare dokan: list swipe {progress_text(info)} (nominal_dy={nominal["nominal_dy"]}px)')
        if info['kind'] == 'static':
            logger.info('Welfare dokan: static swipe, its click records are kept')
            return 'static'
        self._release_swipe_records(rule.name)
        return 'moved'

    def _save_progress_evidence(self, baseline, final, info, nominal=None):
        """推进结论一直 unknown 时一次性保存诊断：滑动前基准帧 + 最后一次停稳落点帧 + 判据文字（同 `_save_settle_evidence`
        的开关与目录，不逐帧落盘）。保存失败只记日志，不掩盖转人工；停止信号照常向上传播。"""
        try:
            if not getattr(self.task.config.script.error, 'save_error', False):
                logger.info('Welfare dokan: save_error is off, list progress evidence not saved')
                return None
            folder = Path(ERROR_LOG_ROOT) / build_error_log_dir_name(self.task.config.config_name, int(time.time() * 1000))
            folder.mkdir(parents=True, exist_ok=True)
            save_image(np.asarray(baseline), str(folder / 'welfare_list_1_before_swipe.png'))
            save_image(np.asarray(final), str(folder / 'welfare_list_2_final.png'))
            nominal_line = (
                f'名义手势：{nominal["name"]} {nominal["start"]}->{nominal["end"]} (nominal_dy={nominal["nominal_dy"]}px)'
                if nominal else '名义手势：未记录'
            )
            lines = [f'福利道馆：滑动列表后无法确认列表是否推进（追加观察 {SWIPE_UNKNOWN_OBSERVES} 次后仍为 unknown）。',
                     nominal_line,
                     f'最后一次判据：{progress_text(info)}',
                     f'LIST_BOX={LIST_BOX}；有效搜索纵坐标 [{ANCHOR_LIST_TOP}, {LIST_BOTTOM})，'
                     f'战力带 dy={ANCHOR_POWER_DY} x={ANCHOR_POWER_X}，馆名带 dy={ANCHOR_NAME_DY} x={ANCHOR_NAME_X}，'
                     f'阈值 score>={ANCHOR_MATCH_MIN} / part>={ANCHOR_PART_MIN} / margin>={ANCHOR_MARGIN_MIN} / '
                     f'static_tol=±{ANCHOR_STATIC_TOLERANCE}px。',
                     '图片：1=滑动前基准帧；2=最后一次停稳落点帧。']
            (folder / 'log.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            logger.warning(f'Welfare dokan: list progress evidence saved to {folder}')
            return folder
        except Exception as error:
            logger.warning(f'Welfare dokan: saving list progress evidence failed: {error!r}')
            return None

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

        观察层（`_observe_list`）先等列表相对 `baseline` 出现变化且连续 `OBSERVE_STABLE_FRAMES` 帧内容安静：
        相邻帧像素变化 `<= LIST_STABLE_THRESHOLD` 直接放行，超过时再经 `list_change_kind` 判定是否属于有界原地局部动画
        （`_is_observe_local_stable`）；整体平移 / 大面积变化 / 超界变化均重置连续计数。
        由于观察层只保证「曾经变化 + 此刻内容安静」，到底回弹中途的短暂停顿也可能通过，所以稳定之后还要再取
        SWIPE_HOLD_FRAMES 帧确认列表内容没有相对落点帧再动（`_hold_failure`），在动就以最新一帧为新起点重新观察。
        两层都会经 `list_change_kind` 放过局部动画、拦住「内容位移 / 大面积变化」。
        全部轮次都没通过时转人工，并把最后一轮的基准帧 / 失败帧存进 log/error 供定位。
        """
        task = self.task
        anchor, timeout = baseline, SWIPE_OBSERVE_TIMEOUT
        rounds = []
        for attempt in range(1, SWIPE_SETTLE_TRIES + 2):
            result = self._observe_list(anchor, timeout)
            final = np.array(task.device.image)
            failure = self._hold_failure(final) if result.stable else None
            if result.stable and failure is None:
                note = f'{self._observe_note()}{self._hold_note()}'
                logger.info(f'Welfare dokan: list settled (observe #{attempt}, {result.frames_checked} frames, '
                            f'{result.elapsed:.1f}s, hold {SWIPE_HOLD_FRAMES} frames ok{note})')
                return final
            rounds.append(self._unsettled_round(attempt, anchor, final, result, failure))
            for old in rounds[:-1]:
                old.pop('frames', None)             # 只保留最后一轮的画面，内存有界
            logger.info(f'Welfare dokan: list not settled at observe #{attempt} (stable={result.stable}): '
                        f'{rounds[-1]["text"]}')
            anchor, timeout = np.array(task.device.image), SWIPE_SETTLE_TIMEOUT
        folder = self._save_settle_evidence(what, baseline, rounds)
        where = f'诊断截图与判据已保存到 {folder}。' if folder else ''
        self._human(f'{what}画面一直在变化、没有稳定下来，无法可靠识别候选，已停止（不当作到底 / 不当作刷新成功）。{where}')

    def _hold_failure(self, final):
        """落点确认：取 SWIPE_HOLD_FRAMES 帧，每帧都和**同一张**落点帧比较；全部通过返回 None，否则返回失败详情。

        只有 `list_change_kind` 判为 shifted / wide（内容在动 / 大面积变化）才算失败；same / local 通过。
        不用相邻帧比较：内容位移会一直保留在「和落点比较」的结果里，局部渐变动画则被 local 放过。
        """
        self._hold_locals = []
        for index in range(1, SWIPE_HOLD_FRAMES + 1):
            self._screenshot()
            frame = np.array(self.task.device.image)
            info = list_change_kind(final, frame)
            if info['kind'] in ('shifted', 'wide'):
                return {**info, 'index': index, 'frame': frame}
            if info['kind'] == 'local':
                self._hold_locals.append(info)
        return None

    def _observe_note(self) -> str:
        """通过观察层时，若期间曾放过有界原地局部动画，附在 settled 日志后面（真机核对用）。"""
        obs = self._observe_locals
        if not obs:
            return ''
        worst = max(obs, key=lambda item: item['ratio'])
        return (f', ignored local change in observe ({len(obs)} frame(s): '
                f'changed pixels {worst["ratio"]:.3f}, rows {worst["rows"]:.2f})')

    def _hold_note(self) -> str:
        """通过确认时，若期间出现过被放过的局部变化，附在 settled 日志后面（真机上看有没有局部动画）。"""
        locals_ = self._hold_locals
        if not locals_:
            return ''
        worst = max(locals_, key=lambda item: item['ratio'])
        return (f', ignored local change in {len(locals_)} frame(s): changed pixels {worst["ratio"]:.3f}, '
                f'rows {worst["rows"]:.2f}')

    def _unsettled_round(self, attempt, anchor, final, result, failure) -> dict:
        """一轮没通过的原因（文字 + 画面），用于日志和最终失败时的诊断保存。"""
        if failure is None:
            layer = 'observe'
            text = (f'observation layer: not stable within the time limit (changed={result.changed}, '
                    f'last difference {result.last_difference:.3f} vs changed line {LIST_CHANGED_THRESHOLD}, '
                    f'{result.frames_checked} frames, {result.elapsed:.1f}s)')
            frames = {'round_anchor': anchor, 'round_final': final}
        else:
            layer = 'hold'
            shift = f', best vertical shift {failure["shift"]}px -> changed pixels {failure["shifted_ratio"]:.3f}'
            text = (f'hold layer: frame {failure["index"]}/{SWIPE_HOLD_FRAMES} {failure["kind"]} '
                    f'(changed pixels {failure["ratio"]:.3f} vs {LIST_STABLE_THRESHOLD}, '
                    f'changed rows {failure["rows"]:.2f} vs {LIST_MOVED_ROW_COVERAGE}{shift}; '
                    f'observation stable after {result.frames_checked} frames, {result.elapsed:.1f}s)')
            frames = {'round_anchor': anchor, 'hold_base': final, 'hold_failed': failure['frame']}
        return {'attempt': attempt, 'layer': layer, 'text': text, 'frames': frames}

    def _save_settle_evidence(self, what: str, baseline, rounds):
        """最终失败时一次性保存诊断：滑动前基准帧 + 最后一轮的基准帧 / 失败帧 + 失败帧相对基准帧的变化图 + 判据文字。

        只在 `save_error` 打开时保存（与公共错误现场同一个开关和目录），不逐帧落盘；保存失败只记日志，不能掩盖原始的
        转人工错误（停止信号 KeyboardInterrupt / SystemExit 不是 Exception，照常向上传播）。
        """
        try:
            if not getattr(self.task.config.script.error, 'save_error', False):
                logger.info('Welfare dokan: save_error is off, list settle evidence not saved')
                return None
            folder = Path(ERROR_LOG_ROOT) / build_error_log_dir_name(self.task.config.config_name, int(time.time() * 1000))
            folder.mkdir(parents=True, exist_ok=True)
            frames = rounds[-1].get('frames', {})
            images = [('1_before_swipe', baseline), *((f'{i}_{name}', frame) for i, (name, frame)
                                                      in enumerate(frames.items(), start=2))]
            base = frames.get('hold_base', frames.get('round_anchor'))
            failed = frames.get('hold_failed', frames.get('round_final'))
            if base is not None and failed is not None:
                x1, y1, x2, y2 = LIST_BOX
                diff = np.abs(np.asarray(base)[y1:y2, x1:x2].astype(np.int16) - np.asarray(failed)[y1:y2, x1:x2].astype(np.int16))
                mask = (diff.max(axis=2) > DEFAULT_PIXEL_THRESHOLD).astype(np.uint8) * 255
                images.append((f'{len(images) + 1}_changed_pixels_list_box', np.stack([mask] * 3, axis=2)))
            for name, frame in images:
                save_image(np.asarray(frame), str(folder / f'welfare_list_{name}.png'))
            lines = [f'福利道馆：{what}列表一直没有判定为稳定（全部 {len(rounds)} 轮都没通过）。',
                     f'阈值：相邻帧稳定线 {LIST_STABLE_THRESHOLD}（观察层局部动画上限 {OBSERVE_LOCAL_RATIO_MAX}/'
                     f'{OBSERVE_LOCAL_ROWS_MAX}），观察层变化线 {LIST_CHANGED_THRESHOLD}，'
                     f'确认层帧数 {SWIPE_HOLD_FRAMES}，平移试探 ±{HOLD_SHIFT_MAX}px（增益 {HOLD_SHIFT_GAIN}），'
                     f'大面积变化行占比线 {LIST_MOVED_ROW_COVERAGE}；LIST_BOX={LIST_BOX}',
                     *(f'第 {item["attempt"]} 轮：{item["text"]}' for item in rounds),
                     '图片：1=滑动前；其余=最后一轮的基准帧 / 失败帧（hold_base 是落点帧，hold_failed 是之后与它比较失败的帧），'
                     '最后一张是两者在 LIST_BOX 内的变化像素（白=变了）。']
            (folder / 'log.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            logger.warning(f'Welfare dokan: list settle evidence saved to {folder}')
            return folder
        except Exception as error:
            logger.warning(f'Welfare dokan: saving list settle evidence failed: {error!r}')
            return None

    def _observe_list(self, baseline, timeout: float):
        """福利列表专用观察层：等待相对 `baseline` 发生变化并连续 `OBSERVE_STABLE_FRAMES` 帧内容安静（不改公共 FrameWait）。

        相邻帧变化像素 `<= LIST_STABLE_THRESHOLD` 直接计为安静（快速路径）；超过时调用 `list_change_kind(prev, curr)`，
        仅当属于有界原地局部动画（`_is_observe_local_stable`）才累计安静计数并记录到 `self._observe_locals`，
        整体平移 / 大面积变化 / 超界变化均将连续计数清零。
        """
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(f'timeout 必须是正数：{timeout!r}')
        task = self.task
        base = np.array(baseline)
        prev = base
        changed = False
        stable_count = 0
        last_difference = 0.0
        frames_checked = 0
        self._observe_locals = []
        start = self.clock()

        while True:
            elapsed = self.clock() - start
            if elapsed >= timeout:
                return FrameWaitResult(
                    changed=changed,
                    stable=stable_count >= OBSERVE_STABLE_FRAMES,
                    timed_out=True,
                    last_difference=last_difference,
                    stable_count=stable_count,
                    frames_checked=frames_checked,
                    elapsed=elapsed,
                )
            if frames_checked >= OBSERVE_MAX_POLLS:
                raise RuntimeError(
                    f'welfare _observe_list 轮询超过 {OBSERVE_MAX_POLLS} 帧仍未到 timeout，'
                    'clock 可能未推进'
                )

            task.screenshot()
            curr = np.array(task.device.image)  # 独立拷贝：避免设备层复用图像缓冲导致 prev 与 curr 同一对象
            frames_checked += 1

            last_difference = frame_difference(base, curr, roi=LIST_BOX)
            if not changed and last_difference >= LIST_CHANGED_THRESHOLD:
                changed = True

            prev_info = list_change_kind(prev, curr)
            if prev_info['kind'] == 'same':
                stable_count += 1
            elif _is_observe_local_stable(prev_info):
                stable_count += 1
                self._observe_locals.append(prev_info)
            else:
                stable_count = 0
            prev = curr

            if changed and stable_count >= OBSERVE_STABLE_FRAMES:
                return FrameWaitResult(
                    changed=True,
                    stable=True,
                    timed_out=False,
                    last_difference=last_difference,
                    stable_count=stable_count,
                    frames_checked=frames_checked,
                    elapsed=elapsed,
                )

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
        self._release_refresh_records()

    def _release_refresh_records(self):
        """确认本轮列表刷新已真实生效之后，定向释放刷新、确认框与刚结束批次遗留的福利滑动记录。

        公共 `Device.click_record`（maxlen=15）中任意两按钮各自累计 >= 6 次即触发双按钮保护，
        同一按钮 >= 10 次触发单按钮保护。此前仅在滑动推进与候选检查后释放记录，连续刷到第 6 轮时会因
        `dokan_refresh` / `RES_RYOU_DOKAN_REFRESH_ENSURE` 各自满 6 次而报错；短列表连续多批无 `moved` 时
        触底的 `dokan_welfare_list_up` 也会持续滞留。仅在刷新弹窗确认消失、回到找馆页、列表停稳且内容变化后
        按名精准释放上述三项，刷新失败或异常退出一律保留，绝不调用 `click_record_clear()`。
        """
        task = self.task
        names = (
            task.C_DOKAN_REFRESH.name,
            task.I_REFRESH_ENSURE.name,
            task.S_DOKAN_WELFARE_LIST_UP.name,
        )
        removed = [task.device.click_record_remove(name) for name in names]
        logger.info(f'Welfare dokan: refresh confirmed, released click records {dict(zip(names, removed))}')

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

    # ------------------------------------------------------------------ D. 集结 → 准备 → 缓冲 → 关闭
    def _enter_prepare_and_close(self):
        """集结 → 开始挑战 → 准备页点准备 → 缓冲 1.85 秒 → 关闭游戏。

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
                # 核心时序：这一帧识别到可点击的准备 → 点击 → 点击接口正常返回 → 缓冲 PREPARE_CLOSE_BUFFER_SECONDS →
                # 关闭游戏。缓冲是可中断的 sleep，不截图、不识别、不等战斗开始、不进通用战斗循环；点击抛异常不会走到
                # 缓冲和关闭；缓冲期间的停止 / 异常原样向上传播，没有 finally，也就不会在异常出口关游戏。
                # 缓冲不计入 600 秒：600 秒从 `_confirm_closed` 确认进程退出的时刻起算。
                logger.info(f'Welfare dokan: prepare button seen, click, wait {PREPARE_CLOSE_BUFFER_SECONDS}s, then close the game')
                x, y = task.I_PREPARE_HIGHLIGHT.coord()
                execute_single_click(task.device, FinalPoint(x, y), control_name=task.I_PREPARE_HIGHLIGHT.name)
                self._wait(PREPARE_CLOSE_BUFFER_SECONDS)
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
        """放弃本馆并处理再战选择。返回 'again'（再战点击已确认生效）或 'finished'（机会已用完）。"""
        task = self.task
        if not task.ui_click_until_appear_or_timeout(
                task.I_DOKAN_ABANDONED_TOPPA, stop=task.I_DOKAN_ABANDONED_TOPPA_ENSURE, interval=1.5, timeout=10):
            self._human('没有出现放弃确认框，无法放弃本馆，请人工处理。')
        task.ui_click_until_disappear(task.I_DOKAN_ABANDONED_TOPPA_ENSURE, interval=1.5, timeout=10, max_clicks=2)
        # 放弃确认消失后约 1 秒弹出战绩弹窗（含无法被「突破排名」模板命中的「击败排名」）：
        # 先等待弹出并点击安全右侧空白区 C_DOKAN_TOPPA_RANK_CLOSE_AREA（在投票区下方、不碰保留赏金/再战道馆）
        self._wait(ABANDON_POPUP_WAIT_SECONDS)
        self._screenshot()
        self._clear_rank_mask(dismiss_once=True)
        deadline = self.clock() + ABANDON_TIMEOUT
        while self.clock() < deadline:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_TOPPA_RANK):
                self._clear_rank_mask()
            elif task.appear(task.I_DOKAN_ABANDONED_TOPPA_TITLE) and task.appear(task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED):
                # 「放弃 / 继续」投票阶段：选放弃
                task.appear_then_click(task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED, interval=2)
            elif task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                # 「保留赏金 / 再战道馆」阶段（与上面的标题不同时出现）
                if not want_again:
                    self._human('最后一馆放弃后出现了「再战 / 保留赏金」按钮，与剩余机会不符，不选择，请人工处理。')
                if self._read_count(retries=3) != 1:
                    self._human('投票阶段读不到「剩余 1 次」，无法确认还有下一次机会，不选择，请人工处理。')
                self._vote_again()
                return 'again'
            elif task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO) or \
                    task.appear(task.I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE):
                return 'finished'
            self.sleep(0.5)
        self._human('放弃后没有出现预期的投票或收尾画面，请人工处理。')

    def _clear_rank_mask(self, *, dismiss_once: bool = False):
        """点击安全右侧空白区关闭结算/排名遮罩，并连续帧确认已无「突破排名」遮罩。

        `dismiss_once=True` 时即使「突破排名」模板未命中（如「击败排名」弹窗），也会先点一次安全空白区
        C_DOKAN_TOPPA_RANK_CLOSE_AREA（位于投票区下方）再做连续帧确认；超限转人工且不启动计时。
        """
        task = self.task
        deadline = self.clock() + RANK_CLOSE_TIMEOUT
        clicks = gone = 0
        dismiss_pending = bool(dismiss_once)
        while True:
            if task.appear(task.I_RYOU_DOKAN_TOPPA_RANK) or dismiss_pending:
                gone = 0
                if clicks >= RANK_CLOSE_CLICK_LIMIT or self.clock() >= deadline:
                    self._human('放弃后的「突破排名」遮罩点击多次仍没有关掉，无法继续投票，未启动 120 秒等待，请人工处理。')
                if task.click(task.C_DOKAN_TOPPA_RANK_CLOSE_AREA, interval=2):
                    clicks += 1
                    dismiss_pending = False
                    logger.info(f'Welfare dokan: rank mask close clicked ({clicks}/{RANK_CLOSE_CLICK_LIMIT})')
            else:
                gone += 1
                if gone >= RANK_GONE_FRAMES:
                    return
            self.sleep(0.5)
            self._screenshot()

    def _wait_vote_disappear(self, *, initial_gone: int = 0) -> str:
        """点击「再战道馆」后在观察窗内确认标识确实消失（排除排名遮罩遮挡）。"""
        task = self.task
        gone = initial_gone
        if gone >= VOTE_GONE_FRAMES:
            return 'disappeared'
        deadline = self.clock() + VOTE_DISAPPEAR_TIMEOUT
        while True:
            if self.clock() >= deadline:
                return 'still_visible'
            self.sleep(0.5)
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_TOPPA_RANK):
                return 'mask'
            if not task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                gone += 1
                if gone >= VOTE_GONE_FRAMES:
                    return 'disappeared'
            else:
                gone = 0

    def _vote_again(self):
        """点「再战道馆」（绝不点保留赏金）并确认该标识消失后才启动 120 秒计时；仍有标识时有界补点。"""
        task = self.task
        sent_clicks = 0
        miss_or_throttle = 0
        mask_rounds = 0
        last_clicked_at = None
        while True:
            self._screenshot()
            if task.appear(task.I_RYOU_DOKAN_TOPPA_RANK):
                mask_rounds += 1
                if mask_rounds > VOTE_MASK_ROUNDS:
                    self._human('投票前排名遮罩反复出现，无法稳定进入投票界面，未启动 120 秒等待，请人工处理。')
                logger.info(f'Welfare dokan: rank mask in front of the vote ({mask_rounds}/{VOTE_MASK_ROUNDS}), close it first')
                self._clear_rank_mask()
                continue
            if not task.appear(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                if sent_clicks > 0:
                    status = self._wait_vote_disappear(initial_gone=1)
                    if status == 'disappeared':
                        self._start_again_timer(started_at=last_clicked_at)
                        logger.info(
                            f'Welfare dokan: rematch confirmed (button disappeared after click '
                            f'{sent_clicks}/{VOTE_MAX_CLICKS})'
                        )
                        return
                    if status == 'mask':
                        mask_rounds += 1
                        if mask_rounds > VOTE_MASK_ROUNDS:
                            self._human('投票前排名遮罩反复出现，无法稳定进入投票界面，未启动 120 秒等待，请人工处理。')
                        logger.info(
                            f'Welfare dokan: rank mask appeared during rematch confirm '
                            f'({mask_rounds}/{VOTE_MASK_ROUNDS}), close it first'
                        )
                        self._clear_rank_mask()
                    continue
                miss_or_throttle += 1
                if miss_or_throttle >= VOTE_CLICK_TRIES:
                    self._human('「再战道馆」点击多次都没有真正发出（按钮没有找到或被点击限流），无法投票，未启动 120 秒等待，请人工处理。')
                self.sleep(0.4)
                continue
            if sent_clicks >= VOTE_MAX_CLICKS:
                self._human(f'已点击「再战道馆」{sent_clicks} 次但该标识仍未消失，无法确认已选中再战，未启动 120 秒等待，请人工处理。')
            if not task.appear_then_click(task.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN):
                miss_or_throttle += 1
                logger.info('Welfare dokan: vote click was throttled (not sent), try again')
                if miss_or_throttle >= VOTE_CLICK_TRIES:
                    self._human('「再战道馆」点击多次都没有真正发出（按钮没有找到或被点击限流），无法投票，未启动 120 秒等待，请人工处理。')
                self.sleep(0.4)
                continue
            sent_clicks += 1
            miss_or_throttle = 0
            last_clicked_at = self.clock()
            logger.info(
                f'Welfare dokan: rematch click {sent_clicks}/{VOTE_MAX_CLICKS} sent, '
                'confirming button disappears'
            )
            status = self._wait_vote_disappear()
            if status == 'disappeared':
                self._start_again_timer(started_at=last_clicked_at)
                logger.info(
                    f'Welfare dokan: rematch confirmed (button disappeared after click '
                    f'{sent_clicks}/{VOTE_MAX_CLICKS})'
                )
                return
            if status == 'mask':
                mask_rounds += 1
                if mask_rounds > VOTE_MASK_ROUNDS:
                    self._human('投票前排名遮罩反复出现，无法稳定进入投票界面，未启动 120 秒等待，请人工处理。')
                logger.info(
                    f'Welfare dokan: rank mask appeared after rematch click '
                    f'({mask_rounds}/{VOTE_MASK_ROUNDS}), close it first'
                )
                self._clear_rank_mask()
                continue
            logger.info(
                f'Welfare dokan: rematch button still visible after click {sent_clicks}/{VOTE_MAX_CLICKS}, '
                'will retry'
            )

    def _start_again_timer(self, *, started_at: float | None = None):
        """再战点击实际发出并确认生效的边界建立 120 秒截止时刻（单调时钟）。只建立一次：已建立时保留
        原截止时刻，不重置——回庭院的导航与重试耗时都在这 120 秒之内，不会重新计时。"""
        if self._again_deadline is not None:
            logger.warning('Welfare dokan: the rematch deadline already exists, keep it (never restarted)')
            return
        base = self.clock() if started_at is None else started_at
        self._again_deadline = base + AGAIN_WAIT_SECONDS

    def _wait_again(self):
        """已确认回到庭院之后，只补等 `max(0, 截止时刻 - 现在)` 秒。没有计时（再战点击没有实际发出）转人工，不盲等。

        游戏保持开启，导航和这段等待都计入真实活跃时长（不放入 600 秒离线排除）。导航已经用掉 120 秒时不追加等待。
        只在这段等待正常结束之后维护公共卡死保护（见下）；异常 / 停止信号不会走到这里，没有 finally。
        """
        deadline = self._again_deadline
        if deadline is None:
            self._human('没有再战点击实际发出的计时，却进入了再战后的等待，状态异常，已停止，请人工处理。')
        remaining = max(0.0, deadline - self.clock())
        if remaining <= 0:
            logger.info('Welfare dokan: the 120s since the rematch click are already used up by the navigation, no extra wait')
            self._again_deadline = None
            return
        logger.info(f'Welfare dokan: back in the courtyard, wait the remaining {remaining:.1f}s of {AGAIN_WAIT_SECONDS}s since the rematch click')
        self._wait(remaining)
        self._again_deadline = None
        # 与公共卡死保护衔接：`Device.screenshot()` 在取画面之前先 `stuck_record_check()`，判定同时要求「距最近一次
        # 清除超过 60 秒」和「自那以后的检查次数 > 60」。这段剩余等待没有截图，时间条件一定满足；放弃 / 关遮罩 / 投票 / 回庭院
        # 阶段累计的检查次数不固定，一旦 > 60，等待结束后的第一次截图就会在识别页面之前被判成卡死。这里是一段有明确业务依据、已经
        # 等满的固定等待，只在它正常结束之后清一次计时（异常 / 停止信号不会走到这里，没有 finally）；不动点击记录，也不留任何
        # 豁免，之后的无进展照常由公共保护判定。没有发生等待（剩余为 0）时没有空窗期，也就不清。
        self.task.device.stuck_record_clear()
