"""Runtime constants for the Chess task."""

from tasks.Chess.strategy.lineup import (
    DEFAULT_LINEUP_KEY as REGISTERED_DEFAULT_LINEUP_KEY,
    LINEUP_REGISTRY as REGISTERED_LINEUP_REGISTRY,
)
from tasks.Chess.strategy.soul_catalog import SOUL_ENTRIES


class ChessRuntimeSettings:
    """Tuning values shared by the Chess runtime mixins."""

    # 保段位：前四名之后主动退出的局数。上游是 2，本地规则是 3（config 说明与历史行为一致），不随上游改。
    RANK_PROTECTION_EXIT_COUNT = 3

    HAND_AREA = (179, 540, 957, 158)
    # Retained for ordinary soul and protection templates, not shikigami fallback.
    HAND_TEMPLATE_THRESHOLD = 0.75
    HAND_DEPLOY_TEMPLATE_THRESHOLD = 0.75
    HAND_DEPLOY_CONFIRM_FRAMES = 1
    # Chess 运行时统一使用四档间隔。较慢的 2/3 秒轮询通过倍数表达，
    # 不再为每个功能分别维护近似数值。
    FAST_OPERATION_INTERVAL = 0.1
    SCREENSHOT_INTERVAL = 0.35
    ACTION_SETTLE_INTERVAL = 0.6
    SLOW_POLL_INTERVAL = 1.0
    ACTION_ICON_WAIT_TIMEOUT = 3.0
    ACTION_ICON_MAX_ATTEMPTS = 3
    # 详情已打开后，在单次确认时间预算内初读与最多新截图复读 O_DETAIL_NAME 的总次数上限。
    SPECIFICS_DETAIL_NAME_MAX_READS = 3
    # 详情名字白字前景各通道最小亮度与最少像素阈值：隔离纯白式神名，过滤半透明底层榜单玩家名。
    SPECIFICS_DETAIL_NAME_WHITE_MIN_CHANNEL = 145
    SPECIFICS_DETAIL_NAME_WHITE_MIN_PIXELS = 20
    # 详情名字区连续新帧稳定性检查：仅追踪亮前景区 (>=120) 及面板均值突变，避免底层动态噪声误判。
    SPECIFICS_DETAIL_NAME_STABLE_BRIGHT_FLOOR = 120
    SPECIFICS_DETAIL_NAME_STABLE_MAX_CHANGED_PIXELS = 8
    SPECIFICS_DETAIL_NAME_STABLE_MAX_MEAN_DIFF = 12.0
    # 首领挑战会大幅改变棋盘显示位置，固定站位的勾玉检测框不可用。
    BOSS_CHALLENGE_ROUNDS = frozenset({9, 15, 21, 27, 33})
    HAND_DEPLOY_SAFETY_LIMIT = 20
    HAND_CLEANUP_SAFETY_LIMIT = 30
    HAND_CLEANUP_CLEAN_CONFIRM_FRAMES = 3
    # 系统自动上阵优先占用棋盘右侧 6、12、5、11 号位。百鬼结束后
    # 只需要依次回收这些候选格；若 5 号位由脚本亲自部署，则保留该格。
    BOARD_RECALL_POSITIONS = (6, 12, 5, 11)
    # c_card_1/2/3.png 专用于检测棋盘式神头顶的三种勾玉颜色。
    BOARD_OCCUPANCY_TEMPLATE_THRESHOLD = 0.68
    # 普通准备阶段以每格上阵落点 (cx, cy) 为基准，偏移 (-31, -26) 取 59x55 区域匹配小纸人确认空格。
    # 偏移来自 1 号位标注：落点 (377, 398) -> 搜索框 (346, 372, 59, 55)。
    BOARD_EMPTY_PAPER_OFFSET = (-31, -26)
    BOARD_EMPTY_PAPER_SIZE = (59, 55)
    # 准备阶段关店后左栏「荒川」羁绊数量读数：以 I_C_ARAKAWA_SIGN 匹配左上角 (x, y) 为基准，
    # 裁 (x + 14, y + 15, 12, 16) 并用 cv2.INTER_LINEAR 放大 3 倍到 36x48，仅原始 OCR 数字 >= 2 放行。
    ARAKAWA_SIGN_COUNT_OFFSET = (14, 15)
    ARAKAWA_SIGN_COUNT_SIZE = (12, 16)
    ARAKAWA_SIGN_COUNT_UPSCALE = 3
    ARAKAWA_GOLDFISH_MIN_COUNT = 2
    # 常规找金鱼优先检查格序，其余已确认未登记占格按编号升序排在后面。
    GOLDFISH_INSPECT_PRIORITY_POSITIONS = (6, 5, 11, 12)
    # 以下时间阈值（秒）依据 log/2026-11-25_oas2.txt 真机实测耗时制定：
    # - 关店+扫牌约 0.58~1.00s（L2912/2958/3229/3285）
    # - Press_and_Drag 单次拖拽 0.78~1.24s（22 次样本均值 0.93s）
    # - 单次点开/超时详情确认约 3.5~3.61s（ACTION_ICON_WAIT_TIMEOUT=3.0s；L3191 耗时 3.61s，L3284 三连点达 10.56s）
    # 单格 1 次详情核查至少需保留 4s；仅补拖已定位金鱼（拖拽约 1.2s + 确认约 1~2s）至少需保留 3s；
    GOLDFISH_SINGLE_INSPECT_MIN_REMAINING = 4
    GOLDFISH_REGULAR_MOVE_MIN_REMAINING = 3
    # 常规巡检找金鱼至少需保留 6s（单次查格约 3.6s + 拖拽约 1.1s + 余量）；
    GOLDFISH_REGULAR_SEARCH_MIN_REMAINING = 6
    # 已知目标格为金鱼时的清格上卡至少需保留 6s（搬运约 1.1s + 确认到位腾空约 1.5s + 扫牌上卡约 2.5s）；
    GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING = 6
    # 未知阻塞格“查一次详情 + 搬金鱼/回收 + 确认腾空 + 扫牌上卡”至少需保留 9s（3.6 + 1.1 + 1.5 + 2.5 ≈ 8.7s）；
    GOLDFISH_BLOCKED_INSPECT_AND_MOVE_MIN_REMAINING = 9
    # 升级/刷新买到新卡后的关店补上阵至少需保留 4s（关店扫牌 0.7~1.0s + 拖卡确认 1.5~2.5s）。
    PREPARATION_ECONOMY_POST_BUY_REDEPLOY_MIN_REMAINING = 4
    # 跨回合旧待核实记录单轮共享上限与时间预算：
    # 单次详情核查本身约需 3.5~3.61s（GOLDFISH_SINGLE_INSPECT_MIN_REMAINING=4s，含 3.0s 等待上限），
    # 再为后续收尾/穿御魂/拖拽预留约 2s 余量，故可读倒计时 >= 6s（与 GOLDFISH_REGULAR_SEARCH_MIN_REMAINING 同档）才核实。
    PENDING_DEPLOY_MAX_INSPECTS_PER_ROUND = 1
    PENDING_DEPLOY_RECONCILE_MIN_REMAINING = (
        GOLDFISH_SINGLE_INSPECT_MIN_REMAINING + 2
    )
    # 拖卡后动画稳定、连续稳定帧与回弹确认参数：
    DEPLOY_SETTLE_WAIT_TIMEOUT = 1.6
    DEPLOY_CONFIRM_STABLE_FRAMES = 2
    # 准备阶段单次整理时间片共享预算（候选整理 / 找金鱼 / 逐格检查共用同一预算）：
    PREP_SLICE_MAX_INSPECTS = 1
    PREP_SLICE_MAX_WALL_SECONDS = 4.5
    # 未完成首轮装备前至少保留 8s 才开新详情查询；首轮装备后降至 6s；小于 3s 停止新整理/装备动作：
    PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP = 8
    PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP = 6
    PREP_ACTION_MIN_REMAINING = 3
    # 被替换回手牌式神的同格冷却与连续置换链上限：
    DISPLACED_LINEUP_COOLDOWN_SECONDS = 2.0
    DISPLACED_CHAIN_MAX_STEPS = 4
    # 站位视觉巡检防抖：连续 2 帧 empty 才失效已确认身份；连续 2 帧星级升高才标记 suspect_merge：
    SLOT_EMPTY_CONFIRM_FRAMES = 2
    SLOT_STAR_CHANGE_CONFIRM_FRAMES = 2
    # 单格穿戴连续失败 2 次触发重新核查与冷却：
    EQUIP_FAILURE_REVERIFY_THRESHOLD = 2
    BOARD_SLOT_REVERIFY_ROUNDS = 4
    PREP_FOLLOWUP_MAX_DURATION_S = 25.0
    PREP_UNKNOWN_TIME_SLICE_BUDGET_S = 8.0
    ROUND_CONFIRM_FRAMES = 2
    GAME_END_CONFIRM_FRAMES = 3
    GAME_OVER_WAIT_TIMEOUT = 60.0
    GAME_ENTER_TIMEOUT = 120.0
    # 匹配到 8/8 后，取消匹配按钮会先消失，随后可能长时间停留在
    # “匹配成功/加载中 100%”页面。该阶段不再沿用开战按钮的短超时。
    MATCHED_LOADING_TIMEOUT = 600.0
    UNKNOWN_STATE_TIMEOUT = 25.0
    SHOP_OPEN_TIMEOUT = 8.0
    SHOP_CLOSE_TIMEOUT = 8.0
    SHOP_REFRESH_CHANGED_SLOT_MINIMUM = 3
    SHOP_REFRESH_SLOT_IMAGE_DIFF_THRESHOLD = 8.0
    ECONOMY_CONFIRM_RETRIES = 2
    SHOP_BUY_TIMEOUT = 30.0
    GRIGRI_SELECT_TIMEOUT = 12.0
    GRIGRI_REFRESH_MAXIMUM = 3
    GRIGRI_ICON_THRESHOLD = 0.72
    EXPERIENCE_COST = 4
    SHOP_REFRESH_COST = 2
    HAKUZOSU_PROTECT_NAME = 'hakuzosu_protect'
    HAKUZOSU_PROTECT_DISPLAY_NAME = '守护之印'
    HAKUZOSU_PROTECT_IMAGE = 'resource/card/c_hakuzosu_protect.png'
    HAKUZOSU_NAME = 'yume_san_byakuzou'
    ARAKAWA_BOND_NAME = '荒川'
    DEFAULT_LINEUP_KEY = REGISTERED_DEFAULT_LINEUP_KEY
    LINEUP_REGISTRY = REGISTERED_LINEUP_REGISTRY
    SOUL_EQUIP_SAFETY_LIMIT = 20
    DISCOVER_SOUL_SAFETY_LIMIT = 10
    DISCOVER_SOUL_UI_TIMEOUT = 8.0
    SOUL_FRONT_ROW_Y_OFFSET = -5
    SOUL_TEMPLATE_THRESHOLD = 0.60
    SOUL_TEMPLATE_SCALES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20)
    SOUL_DISPLAY_NAMES = {
        entry.romaji: entry.chinese_name
        for entry in SOUL_ENTRIES
    }
    ATTACK_SOUL_NAMES = {
        entry.romaji
        for entry in SOUL_ENTRIES
        if entry.category == 'attack'
    }
    FUNCTIONAL_SOUL_NAMES = {
        entry.romaji
        for entry in SOUL_ENTRIES
        if entry.category == 'functional'
    }
