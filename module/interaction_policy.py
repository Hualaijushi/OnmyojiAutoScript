# This Python file uses the following encoding: utf-8
"""L2 Interaction Reaction Layer：目标已经识别之后，「等多久」「点前要不要 fresh confirm」。

    Target Ready（业务 / 状态机已识别到目标）
      → InteractionPolicy（本模块：语义 → reaction 区间）
      → Reaction（random_delay，SystemRandom，每次 attempt 独立采样）
      → Fresh Frame（重新截图）→ Fresh Confirm（同一目标重新识别，并用新帧的坐标来源）
      → L1 单击（坐标采样 / 物理输入，见 `module/click_pipeline.py`）

分工（`docs/DECISIONS.md` D001 补记 L2 分节）：

- L1 只管「点在哪、怎么落下」，`Control.click` / 执行器 / minitouch 里**不许**有 reaction。
- L2 只管一次点击前的 reaction + fresh confirm；确认失败就是本次不点，**不重试**。
- L3（业务 FSM）拥有点击后的状态判定、有限重试、超时、恢复。

本模块只做「语义 → 区间」的解析，不 sleep、不采样、不截图、不点击；普通动作由
`BaseTask.appear_then_click(..., policy=...)` 消费，FIRE 由各自 battle-entry 状态机消费
`fire_reaction_range(...)`。区间数值仍全部来自 `module/reaction_profile.py`（PROVISIONAL）。
"""

from enum import Enum

from module.reaction_profile import (
    REACTION_CONFIRM,
    REACTION_DELIBERATE,
    REACTION_FAST,
    REACTION_FIRE,
    REACTION_NAVIGATION,
    REACTION_NORMAL,
    REACTION_NORMAL_HIGH,
)


class InteractionPolicy(str, Enum):
    # 识别成立后不加 reaction、不做 fresh confirm：旧 caller 的默认行为，或节奏由专门 FSM 自己拥有。
    IMMEDIATE = 'immediate'
    FAST = 'fast'
    NORMAL = 'normal'
    NORMAL_HIGH = 'normal_high'
    CONFIRM = 'confirm'
    NAVIGATION = 'navigation'
    DELIBERATE = 'deliberate'
    # FIRE = Battle Entry Action：reaction 由 battle-entry 状态机按任务配置拥有（`fire_reaction_range`），
    # 普通 appear_then_click 不能代替它的 positive-state confirm / 有限重试。
    FIRE_SPECIAL = 'fire_special'
    # 其它由专门状态机拥有 timing 的动作（如 Settlement micro-burst 的 observe 间隔）。
    SPECIAL = 'special'


POLICY_REACTION_RANGES: dict[InteractionPolicy, tuple[float, float]] = {
    InteractionPolicy.FAST: REACTION_FAST,
    InteractionPolicy.NORMAL: REACTION_NORMAL,
    InteractionPolicy.NORMAL_HIGH: REACTION_NORMAL_HIGH,
    InteractionPolicy.CONFIRM: REACTION_CONFIRM,
    InteractionPolicy.NAVIGATION: REACTION_NAVIGATION,
    InteractionPolicy.DELIBERATE: REACTION_DELIBERATE,
}

FSM_OWNED_POLICIES = frozenset({InteractionPolicy.FIRE_SPECIAL, InteractionPolicy.SPECIAL})

# FIRE 任务配置的公共默认与上限（毫秒）。默认值必须与 REACTION_FIRE 一致，由测试锁定。
DEFAULT_FIRE_REACTION_MIN_MS = 400
DEFAULT_FIRE_REACTION_MAX_MS = 800
FIRE_REACTION_LIMIT_MS = 5000


def resolve_reaction_range(policy: InteractionPolicy | None = None,
                           confirm_delay: tuple[float, float] | None = None) -> tuple[float, float] | None:
    """解析一次普通点击的 reaction 区间（秒）；`None` = 立即点击（旧行为）。

    优先级：同时给 `policy` 与 `confirm_delay` → 直接拒绝（一个动作只能有一个 reaction owner，
    静默取其一会掩盖双重 reaction 的写法）；只给 `policy` → 用 profile 区间（IMMEDIATE = None）；
    只给 legacy `confirm_delay` → 原样沿用；都不给 → None。
    """
    if policy is not None and confirm_delay is not None:
        raise ValueError('policy 与 confirm_delay 不能同时指定：一个点击只能有一个 reaction owner')
    if policy is None:
        return None if confirm_delay is None else tuple(confirm_delay)
    if not isinstance(policy, InteractionPolicy):
        raise TypeError(f'policy 必须是 InteractionPolicy：{policy!r}')
    if policy in FSM_OWNED_POLICIES:
        raise ValueError(f'{policy.name} 的 timing 由专门状态机拥有，不能交给通用 appear_then_click')
    return POLICY_REACTION_RANGES.get(policy)


def fire_reaction_range(fire_reaction=None) -> tuple[float, float]:
    """FIRE 点击前 reaction 区间（秒）。

    `fire_reaction` 是当前任务的 FIRE 配置组（有 `fire_reaction_min_ms` / `fire_reaction_max_ms`，
    取值校验在配置层完成）；没有配置 override（`None`）时用公共默认 `REACTION_FIRE`。这里只做
    毫秒 → 秒换算，不交换、不钳制非法区间——非法值应该在配置层就被拒绝，漏网时由 `random_delay`
    显式报错。
    """
    if fire_reaction is None:
        return REACTION_FIRE
    return fire_reaction.fire_reaction_min_ms / 1000.0, fire_reaction.fire_reaction_max_ms / 1000.0
