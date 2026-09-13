# This Python file uses the following encoding: utf-8
"""业务 Reaction Timing 语义 profile —— 「识别到稳定目标之后、点击之前，人停多久」。

与其它时序层的分工（见 `docs/DECISIONS.md` D001 / D008、`docs/ARCHITECTURE.md`
「时序职责分层」）：

- **State / Ready**：页面什么时候可以操作 —— `appear` / `wait_until_appear` /
  `wait_until_disappear` / `wait_for_changed_and_stable` / 页面 FSM。
- **Reaction（本模块）**：目标已稳定可见后，到点击之间的人为反应延迟 —— 唯一入口是
  `BaseTask.appear_then_click(..., confirm_delay=(lo, hi))`，其内部会做
  「`sleep(random_delay(lo, hi))` → 重新 `screenshot` → 二次 `appear`（目标没了则不点、
  返回 False）→ 重新 `coord()` → `device.click`」。
- **Input**：minitouch dwell、`TouchSwipeModel` 逐段 dt。
- **Macro idle**：`FatigueManager` 的发呆 / 休息（仅 task-cycle 安全节点）。

本模块只提供**具名的 (min, max) 秒区间常量**，供业务 consumer 在调用点**显式**传给
`confirm_delay=`。它：

- 不定义任何函数 / FSM / 采样逻辑，不调用 `sleep` / `random_delay`；
- 不 import task / device / config；
- 不改 `appear_then_click` 的默认行为（不传 `confirm_delay=` 时一切照旧）；
- 不在 asset / `RuleImage` 层设置默认 —— reaction 归业务 consumer 按调用点决定。

**所有区间当前是 PROVISIONAL / engineering baseline**，来自旧 C++ 延迟分析后的业务抽象，
不是人工 Level C 标定结果。后续按 `dev_tools/manual_click_recorder.py` 人工样本 +
BehaviorTrace + 真机观察继续调整；在拿到 Level C 证据前不擅自放大区间。
"""

# 锁定 / 解锁、简单开关、低频管理按钮、动作含义非常明确的稳定按钮。
REACTION_FAST: tuple[float, float] = (0.18, 0.35)

# 普通进入 / 组队 / 普通稳定页面操作 / 普通稳定选择。
REACTION_NORMAL: tuple[float, float] = (0.45, 0.85)

# 高频重复执行但目标长期稳定、每轮可能点一到多次、可安全 fresh-frame 二次确认。
# 本轮 Batch A 暂无合适 consumer，允许 0 消费者。
REACTION_NORMAL_HIGH: tuple[float, float] = (0.60, 1.00)

# 刷新确认 / 明确确认 / 具有一定流程影响的确认按钮。
REACTION_CONFIRM: tuple[float, float] = (0.55, 1.20)

# 返回 / 取消退出 / 离开当前页面 / 导航返回。
REACTION_NAVIGATION: tuple[float, float] = (0.55, 1.10)

# 材料类型 / 阵容 / 预设 / 需要明显选择判断的稳定目标。
REACTION_DELIBERATE: tuple[float, float] = (0.90, 1.60)

# 进攻按钮（FIRE）：已识别到稳定的 `I_FIRE` 后、真正执行 FIRE click 前的人为 reaction。
# 2026-09-08 起 RyouToppa 与 RealmRaid 的 `I_FIRE` 统一使用本区间（此前 RyouToppa 手写
# 0.2~0.6、RealmRaid 无 reaction）。每次真实 FIRE attempt 独立采样，不与 confirm_delay /
# 其它 repeat delay 叠加。
REACTION_FIRE: tuple[float, float] = (0.4, 0.8)

# 是否为 PROVISIONAL（未经 Level C 人工标定）。所有 profile 统一为 True，改动需连带更新
# `docs/DECISIONS.md` D001 补记与 `docs/AI_CONTEXT.md`。
REACTION_PROFILES_PROVISIONAL: bool = True

# 便于测试 / 工具遍历；不参与任何运行时逻辑。
REACTION_PROFILES: dict[str, tuple[float, float]] = {
    'FAST': REACTION_FAST,
    'NORMAL': REACTION_NORMAL,
    'NORMAL_HIGH': REACTION_NORMAL_HIGH,
    'CONFIRM': REACTION_CONFIRM,
    'NAVIGATION': REACTION_NAVIGATION,
    'DELIBERATE': REACTION_DELIBERATE,
    'FIRE': REACTION_FIRE,
}
