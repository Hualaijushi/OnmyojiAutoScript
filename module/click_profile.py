# This Python file uses the following encoding: utf-8
"""ClickProfile / ClickProfileManager —— 点击空间采样的「参数是什么」这一半职责。

与 `module/click_sampler.py` 的分工：

- `ClickProfile`（本模块）：只描述一类目标的空间点击参数（热点、离散度、成分权重、
  安全边距），**不产生随机坐标**。全部用 ROI 相对 `u / v`（`[0, 1]`），不存绝对屏幕坐标。
- `ClickSampler`（`click_sampler.py`）：读 profile、算 Safe ROI、按策略在 Safe ROI 内采样。

T7-1 第 2 阶段做了数据结构 + 一套可解释的 v1 默认 profile + 最小 resolve。
**这些默认值不会自动影响任何现有生产任务**——`Rule*.coord()` 仍走
`ClickSampler.sample(roi)` = `LEGACY_UNIFORM`，与 profile 完全无关。个人先验数值来自
当前单个用户的人工采样实验（见 `docs/DEVELOP_LOG.md` 2026-09-01/02），是「第一版个人
先验」，不是所有用户通用真值。T7-3.1 收口后 **`DEFAULT_PROFILES` 全部标 `provisional=True`**：
`default` / `tiny` / `small` / `strict` 是保守工程默认（数据不足）；`wide_card` 是单账号单次
会话样本，preferred 已按 `RyouToppa.C_AREA_1` RuleClick ROI 的坐标基准收口；`normal_button` /
`large_area` 的坐标基准尚未用真实 runtime ROI-relative 数据验证。`provisional` 只是文档标记，
不被任何采样 / 适配逻辑读取（`adapt_point_profile` 也原样透传）。

T7-2 / T7-4（本模块 `adapt_point_profile`）做「Point Target 连续尺寸适配」：语义基础
profile（当控件足够大时完整表现的个人热点 + 离散度）+ 当前运行时 ROI → EffectiveProfile。
用**同一个** smoothstep `size_factor` 连续调整三件事：小控件的 `preferred` 平滑向
`(0.5, 0.5)` 收缩、`core/medium sigma` 平滑收到「最保守小目标锚点」、`tail` 平滑归零；
大控件逐字恢复 base profile。取代 `if tiny / elif small / elif normal` 这种离散选择。
`adapt_preferred_by_size` 是其中只负责热点的公共纯函数：Point 与 Region 都复用它；Region
不会因此继承 Point 的 sigma / tail 收缩。
**纯计算**：不产生坐标、不调 RNG / 设备 / screenshot，只负责生成 profile。
唯一生产消费者是 `RyouToppa.C_AREA_1`（T7-3.2，经 `ClickSampler.sample_point`；其
`short_side = 116 ≥ POINT_SIZE_FULL_PX` → `size_factor = 1` → EffectiveProfile 逐字等于
`wide_card` base，T7-4 不改变它的生产行为）。

不做：task×page×target×account 复杂 identity 树、在线学习、EMA、配置系统改造、numpy。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from numbers import Real
from typing import Mapping


@dataclass(frozen=True)
class ClickProfile:
    """一类目标的点击空间参数（全部 ROI 相对，冻结不可变）。

    坐标 / 离散度单位都是 ROI 相对：`u` 沿 ROI 宽方向 `[0, 1]`，`v` 沿高方向 `[0, 1]`；
    `*_sigma_*` 是同一坐标系下的标准差（如 `0.13` ≈ ROI 宽的 13%）。
    """

    name: str
    # 习惯热点（ROI 相对）
    preferred_u: float = 0.5
    preferred_v: float = 0.5
    # core 成分：集中在热点附近的窄分布
    core_sigma_u: float = 0.10
    core_sigma_v: float = 0.10
    # medium 成分：较宽的日常抖动
    medium_sigma_u: float = 0.20
    medium_sigma_v: float = 0.20
    # 三成分权重（会归一化；每次点击只选其中一个成分再采样）
    core_weight: float = 0.80
    medium_weight: float = 0.18
    tail_weight: float = 0.02
    # Safe ROI 相对内边距（左右各收 safe_margin_u，上下各收 safe_margin_v）
    safe_margin_u: float = 0.06
    safe_margin_v: float = 0.06
    # 拒绝采样的有限上限；超过则 fallback 到 Safe ROI 内的热点投影
    max_attempts: int = 12
    # 仅文档标记：该 profile 的数值是不是「凑合默认」而非人工统计
    provisional: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ClickProfile.name 不能为空")
        for key in ("preferred_u", "preferred_v"):
            val = getattr(self, key)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{key} 必须在 [0, 1]：{val}")
        for key in ("core_sigma_u", "core_sigma_v", "medium_sigma_u", "medium_sigma_v"):
            val = getattr(self, key)
            if val < 0.0:
                raise ValueError(f"{key} 不能为负：{val}")
        for key in ("core_weight", "medium_weight", "tail_weight"):
            val = getattr(self, key)
            if val < 0.0:
                raise ValueError(f"{key} 不能为负：{val}")
        if self.core_weight + self.medium_weight + self.tail_weight <= 0.0:
            raise ValueError("三成分权重之和必须为正")
        for key in ("safe_margin_u", "safe_margin_v"):
            val = getattr(self, key)
            if not (0.0 <= val < 0.5):
                raise ValueError(f"{key} 必须在 [0, 0.5)（否则 Safe ROI 退化）：{val}")
        if int(self.max_attempts) < 1:
            raise ValueError(f"max_attempts 必须 >= 1：{self.max_attempts}")

    def normalized_weights(self) -> tuple[float, float, float]:
        """返回归一化后的 (core, medium, tail) 权重。"""
        total = self.core_weight + self.medium_weight + self.tail_weight
        return (self.core_weight / total, self.medium_weight / total, self.tail_weight / total)

    def without_tail(self) -> "ClickProfile":
        """返回一个把 tail 权重清零的副本（STRICT 策略用）。"""
        from dataclasses import replace

        return replace(self, tail_weight=0.0)


# STRICT 允许的最大 core sigma——超过就不叫「小目标可靠优先」了。
STRICT_MAX_CORE_SIGMA = 0.12


# --------------------------------------------------------------------------------------
# T7-2：Point Target 连续尺寸适配（Semantic Base Profile + 运行时 ROI → EffectiveProfile）
# --------------------------------------------------------------------------------------

# 尺寸锚点（provisional architecture constant，不是用户配置）。
# 来自当前全仓 ROI 尺寸普查的描述性统计（`docs/AI_CONTEXT.md` §4.26）：主 Click+Image+
# LongClick 子集 short_side p05≈21 / p25≈32 / median≈46 / p90≈100。
# short_side <= S_MIN：安全余量很小，`preferred` 应接近中心；
# short_side >= S_FULL：可以完整使用 Semantic Base Profile；
# 中间：smoothstep 平滑插值。
POINT_SIZE_MIN_PX = 24
POINT_SIZE_FULL_PX = 96

# T7-4：spread 连续尺寸适配的「最保守小目标锚点」——`size_factor = 0`（short_side <=
# POINT_SIZE_MIN_PX）时 `adapt_point_profile` 把 core/medium sigma 收到这里。
# 依据：审计 `DEFAULT_PROFILES` 里现成的保守 Point profile 的离散度参数——
#   default : core σ (0.10, 0.10) / medium σ (0.18, 0.18)
#   small   : core σ (0.09, 0.08) / medium σ (0.14, 0.12)
#   tiny    : core σ (0.06, 0.06) / medium σ (0.10, 0.10)  —— 语义 =「极小目标，离散度最窄、无 tail」
#   strict  : core σ (0.05, 0.05) / medium σ (0.09, 0.09)  —— 绑定 STRICT 策略语义（受
#             `STRICT_MAX_CORE_SIGMA` 约束），不是通用 Point 语义
# 取 `tiny` 的 σ 作锚点：它是 `DEFAULT_PROFILES` 里语义上正好对应「Point Target 最小尺寸」
# 的那一档，`core σ 0.06` 保守但不退化（不趋近 0，最终安全仍由 Safe ROI 兜底），且它本身
# 已经 `tail = 0`。不为 T7-4 另拍一组新数字。`strict` 更窄但语义是 STRICT 策略专用，不选。
# `tests/test_click_profile.py::test_point_min_spread_anchor_matches_tiny_profile` 锁这条依赖。
POINT_MIN_CORE_SIGMA_U = 0.06
POINT_MIN_CORE_SIGMA_V = 0.06
POINT_MIN_MEDIUM_SIGMA_U = 0.10
POINT_MIN_MEDIUM_SIGMA_V = 0.10


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _lerp(lo: float, hi: float, t: float) -> float:
    """线性插值，端点精确：`t = 0.0` → 恰好 `lo`，`t = 1.0` → 恰好 `hi`
    （写成 `lo*(1-t) + hi*t`，端点处一个乘子恰为 `0.0` / 一个恰为 `1.0`，无舍入）。"""
    return lo * (1.0 - t) + hi * t


def _roi_short_side(roi) -> float:
    """从 `(x, y, w, h)` 取 `min(w, h)`。错误处理沿用 `ClickSampler._as_int_roi` 风格：
    非四元组 / 非数值 `w·h` 抛异常，`w <= 0` 或 `h <= 0` 抛 `ValueError`。"""
    try:
        _x, _y, w, h = roi
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ROI 必须是 (x, y, w, h) 四元组：{roi!r}") from exc
    for v in (w, h):
        if not isinstance(v, Real) or isinstance(v, bool):
            raise TypeError(f"ROI 宽高必须是数值：{roi!r}")
    if w <= 0 or h <= 0:
        raise ValueError(f"ROI 宽高必须大于 0：{roi!r}")
    return float(min(w, h))


def point_size_factor(short_side: float) -> float:
    """`short_side` → `[0, 1]` 的连续尺寸系数（smoothstep）。

    `t = clamp((short_side - POINT_SIZE_MIN_PX) / (POINT_SIZE_FULL_PX - POINT_SIZE_MIN_PX), 0, 1)`；
    `factor = 3·t² - 2·t³`。`short_side <= 24` → `0`；`>= 96` → `1`；`60` → `0.5`。
    单调不减、两端一阶导为 0（无线性折点跳变）。
    """
    span = POINT_SIZE_FULL_PX - POINT_SIZE_MIN_PX
    t = _clamp01((float(short_side) - POINT_SIZE_MIN_PX) / span)
    return 3.0 * t * t - 2.0 * t * t * t


def adapt_preferred_by_size(preferred_u: float, preferred_v: float, roi) -> tuple[float, float]:
    """按 ROI 短边把热点锚点连续适配为当前有效热点。

    这是 T7「热点尺寸适配」的唯一纯计算入口，Point / Region 共用同一条 24/96 smoothstep：

        effective = 0.5 + (base - 0.5) * point_size_factor(min(width, height))

    本函数只返回 preferred，不读取或修改 `ClickProfile` 的 sigma、权重、Safe ROI 边距等
    分布形状。Point 的 shape 适配仍由 `adapt_point_profile` 负责；Region 只调用本函数，
    因而不会误用 Point 的 sigma / tail 收缩规则。

    Args:
        preferred_u: 足够大 ROI 下的横向热点锚点，范围 `[0, 1]`。
        preferred_v: 足够大 ROI 下的纵向热点锚点，范围 `[0, 1]`。
        roi: 当前运行时 ROI `(x, y, w, h)`。

    Returns:
        `(effective_u, effective_v)`。

    Raises:
        TypeError: preferred 不是实数，或 ROI 宽高不是数值。
        ValueError: preferred 越界，或 ROI 非法。
    """
    for name, value in (("preferred_u", preferred_u), ("preferred_v", preferred_v)):
        if not isinstance(value, Real) or isinstance(value, bool):
            raise TypeError(f"{name} 必须是数值：{value!r}")
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} 必须在 [0, 1]：{value}")
    factor = point_size_factor(_roi_short_side(roi))
    return (
        0.5 + (float(preferred_u) - 0.5) * factor,
        0.5 + (float(preferred_v) - 0.5) * factor,
    )


def adapt_point_profile(profile: ClickProfile, roi) -> ClickProfile:
    """Semantic Base Profile + 运行时 ROI → Effective Point Profile。

    用**同一个** `f = point_size_factor(min(w, h))`（smoothstep，锚点 24 / 96）连续调整
    三件事，`f` 越小控件越小、profile 越保守：

    1. 热点（T7-2）：
           effective_uv = 0.5 + (base.preferred_uv - 0.5) * f
       小控件 `f→0` 趋近中心，大控件 `f→1` 释放到 base 个人热点。公式对称，
       `base_u < 0.5` 时同样向左平滑释放。

    2. spread（T7-4）：`core_sigma` / `medium_sigma` 在「最保守小目标锚点」
       （`POINT_MIN_*_SIGMA_*`，取值依据见其定义处审计注释）与 base 之间线性插值：
           effective_sigma = anchor * (1 - f) + base_sigma * f
       `f=0` → 锚点（更集中），`f=1` → base。热点回中心的同时分布也一起收窄。

    3. tail（T7-4）：
           effective_tail_weight = base.tail_weight * f
       小控件 `f→0` 不保留远端散点（tail=0），大控件 `f→1` 恢复 base tail。被削掉的
       tail 权重整体回补到 `core_weight`（`core += base.tail_weight * (1 - f)`），
       `medium_weight` 不动。三成分权重之和恒等于 base 之和（base 都是 1.0）。
       不新增第四个 mixture 成分。

    `safe_margin_u/v` / `max_attempts` / `provisional` / `name` **原样透传**——Safe ROI 是
    `ClickSampler` 的**硬安全边界**（职责与分布形状独立），不随尺寸缩放；spread 只是
    分布形状。

    端点精确：`f = 1`（`short_side >= POINT_SIZE_FULL_PX`）时返回 profile 的**每个字段
    都逐字等于 base**（只有对象 identity 是新实例）——所以 `RyouToppa.C_AREA_1`
    （`short_side 116`）的生产行为不受 T7-4 影响。`f = 0` 时热点在中心、σ 在锚点、
    tail 为 0。中间由 `size_factor` 连续、单调、无折点地插值。

    Args:
        profile: 语义基础 `ClickProfile`（不被修改）。
        roi: 当前运行时 ROI `(x, y, w, h)`。

    Returns:
        新的 frozen `ClickProfile`（`profile` 未变）。

    Raises:
        ValueError / TypeError: ROI 非法（见 `_roi_short_side`）。
    """
    f = point_size_factor(_roi_short_side(roi))
    effective_u, effective_v = adapt_preferred_by_size(
        profile.preferred_u, profile.preferred_v, roi
    )
    return replace(
        profile,
        preferred_u=effective_u,
        preferred_v=effective_v,
        core_sigma_u=_lerp(POINT_MIN_CORE_SIGMA_U, profile.core_sigma_u, f),
        core_sigma_v=_lerp(POINT_MIN_CORE_SIGMA_V, profile.core_sigma_v, f),
        medium_sigma_u=_lerp(POINT_MIN_MEDIUM_SIGMA_U, profile.medium_sigma_u, f),
        medium_sigma_v=_lerp(POINT_MIN_MEDIUM_SIGMA_V, profile.medium_sigma_v, f),
        core_weight=profile.core_weight + profile.tail_weight * (1.0 - f),
        tail_weight=profile.tail_weight * f,
    )


# --------------------------------------------------------------------------------------
# v1 默认 profile（结构化默认值；**不自动作用于任何生产任务**）
# --------------------------------------------------------------------------------------

DEFAULT_PROFILES: dict[str, ClickProfile] = {
    # 保守居中，任何没匹配上具体类别的目标 fallback 到这里（`resolve_profile` / manager 的
    # 兜底键，语义 = 「类别未知」）。
    "default": ClickProfile(
        name="default",
        preferred_u=0.50, preferred_v=0.50,
        core_sigma_u=0.10, core_sigma_v=0.10,
        medium_sigma_u=0.18, medium_sigma_v=0.18,
        core_weight=0.82, medium_weight=0.16, tail_weight=0.02,
        safe_margin_u=0.06, safe_margin_v=0.06,
        provisional=True,
    ),
    # T7-5：无人工热点的普通 Point Target（按钮 / 图标 / 文本）默认分布形状。数值与
    # `default` 同源（保守居中、core 82% / medium 16% / tail 2%），**单列一个名字**让
    # 「全局 Point 默认」这条链路可读：
    #     TargetPreference RULE_FALLBACK=(0.58,0.59)  +  default_point
    #       →  adapt_point_profile(按运行时 ROI short_side)  →  HABIT 采样
    # 热点永远由 `TargetPreference` 提供；这里的 preferred 只是 shape profile 的中性占位，
    # 每次采样前都会被 EMPIRICAL 或 RULE_FALLBACK anchor 覆盖。与 `default` 分开是为了：
    # 将来单独调「普通按钮默认要多集中」时不动 `resolve_profile` 的兜底语义。
    "default_point": ClickProfile(
        name="default_point",
        preferred_u=0.50, preferred_v=0.50,
        core_sigma_u=0.10, core_sigma_v=0.10,
        medium_sigma_u=0.18, medium_sigma_v=0.18,
        core_weight=0.82, medium_weight=0.16, tail_weight=0.02,
        safe_margin_u=0.06, safe_margin_v=0.06,
        provisional=True,
    ),
    # T7-5 Stage 2：Region Target（业务已选定的大安全区，如 GeneralBattle Settlement V3 的
    # `C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`）的兜底 shape profile。
    # 与 `default_point` 的区别：Region 的空间尺度更大，spread 明显更宽（core σ 0.17 vs 0.10、
    # medium σ 0.30 vs 0.18、medium+tail 权重更高），但**仍然中心集中**——不是整 Region 均匀。
    # 走 `ClickSampler.sample_region`，只复用 `adapt_preferred_by_size` 的 24/96 热点尺寸规则，
    # **不经 `adapt_point_profile`**，因此不会把 Region 的 σ / tail 按 Point 规则收缩。这里的
    # preferred 是中性占位；实际热点由 EMPIRICAL 或 RULE_FALLBACK `TargetPreference` 覆盖。
    # 参数是保守起点（provisional），不是复活 Settlement Contract v2。
    "default_region": ClickProfile(
        name="default_region",
        preferred_u=0.50, preferred_v=0.50,
        core_sigma_u=0.17, core_sigma_v=0.17,
        medium_sigma_u=0.30, medium_sigma_v=0.30,
        core_weight=0.62, medium_weight=0.30, tail_weight=0.08,
        safe_margin_u=0.05, safe_margin_v=0.05,
        provisional=True,
    ),
    # 宽卡片（个人 provisional，T7-3.1 收口）：
    # 来源 = manual click `yys1_2026-09-01` 的 cluster_A（寮突破目标卡片）burst-collapse 后
    #        107 个独立落点，对**当前 WIP `RyouToppa.C_AREA_1` RuleClick ROI** `(514,141,223,116)`
    #        的 inside-only ROI-relative：inside 105/107，mean=(0.582,0.586)≈median=(0.579,0.586)，
    #        std≈(0.13,0.14)。这是 `adapt_point_profile` 会操作的坐标系（`rule.roi_front`）。
    # 旧值 (0.68,0.53) 是对**手工估的更大「完整可点卡片区」`(423,142,319,118)`** 算的（热点
    #        screen (641,205)），坐标基准与 `C_AREA_1` RuleClick ROI 不一致、无法直接喂
    #        `adapt_point_profile(base, C_AREA_1.roi_front)` —— 已按真实基准修正到 (0.58,0.59)。
    # 仍是**单账号单次会话**样本，未推广到其它卡片目标（Chess `C_SHIKIGAMI_*` 等需各自采样）。
    # sigma / weights 本轮不动（观察 std≈(0.13,0.14) 与 core_sigma 0.16 量级相符）。
    "wide_card": ClickProfile(
        name="wide_card",
        preferred_u=0.58, preferred_v=0.59,
        core_sigma_u=0.16, core_sigma_v=0.16,
        medium_sigma_u=0.26, medium_sigma_v=0.24,
        core_weight=0.75, medium_weight=0.20, tail_weight=0.05,
        safe_margin_u=0.05, safe_margin_v=0.05,
        provisional=True,
    ),
    # 普通按钮（个人 provisional，**尚未通过真实 runtime ROI-relative 数据验证**）：
    # cluster_B（寮突破「进攻」按钮）只有屏幕归一化 mean (0.527,0.545)，没有可靠的
    # runtime `I_FIRE` roi_front（RuleImage match 后是模板尺寸）—— (0.62,0.70) 是早轮
    # 依屏幕分布 + static roi_front 的估计，v=0.70 偏激进。本轮**不重新估计**（禁止拿
    # screen-space / static ROI 猜 runtime relative）；待 Level C `runtime_roi_probe` +
    # manual click 一起标定后再改。
    "normal_button": ClickProfile(
        name="normal_button",
        preferred_u=0.62, preferred_v=0.70,
        core_sigma_u=0.13, core_sigma_v=0.13,
        medium_sigma_u=0.22, medium_sigma_v=0.22,
        core_weight=0.78, medium_weight=0.18, tail_weight=0.04,
        safe_margin_u=0.06, safe_margin_v=0.06,
        provisional=True,
    ),
    # 大安全区（个人 provisional，**历史 / 屏幕空间混合来源，不是 Point Target profile**）：
    # cluster_C 混合了多个战后页面的连点，(0.74,0.67) 是这批**屏幕空间**分布的归一化中心，
    # 没有单一 ROI 基准。**禁止**用于 `adapt_point_profile` 的 Point Target 生产 opt-in——
    # 它描述的是「大安全区域整体偏右下」的 Region 语义。与 GeneralBattle Settlement RD
    # profile（`_SETTLEMENT_PRIMARY_PROFILE` preferred (0.54,0.53)）是不同东西，不合并。
    # 保留是因为历史测试 / 分析可能仍引用。
    "large_area": ClickProfile(
        name="large_area",
        preferred_u=0.74, preferred_v=0.67,
        core_sigma_u=0.22, core_sigma_v=0.20,
        medium_sigma_u=0.34, medium_sigma_v=0.30,
        core_weight=0.60, medium_weight=0.30, tail_weight=0.10,
        safe_margin_u=0.02, safe_margin_v=0.02,
        provisional=True,
    ),
    # 小目标（provisional：用户只说「基本居中，轻微偏右」，缺精确数据 → 保守）
    "small": ClickProfile(
        name="small",
        preferred_u=0.54, preferred_v=0.50,
        core_sigma_u=0.09, core_sigma_v=0.08,
        medium_sigma_u=0.14, medium_sigma_v=0.12,
        core_weight=0.88, medium_weight=0.11, tail_weight=0.01,
        safe_margin_u=0.08, safe_margin_v=0.08,
        provisional=True,
    ),
    # 极小目标（provisional：更靠中心、离散度最窄、无 tail）
    "tiny": ClickProfile(
        name="tiny",
        preferred_u=0.52, preferred_v=0.50,
        core_sigma_u=0.06, core_sigma_v=0.06,
        medium_sigma_u=0.10, medium_sigma_v=0.10,
        core_weight=0.95, medium_weight=0.05, tail_weight=0.0,
        safe_margin_u=0.10, safe_margin_v=0.10,
        provisional=True,
    ),
    # STRICT 策略在未指定 profile 时用的窄 profile（居中、极窄、无 tail）
    "strict": ClickProfile(
        name="strict",
        preferred_u=0.50, preferred_v=0.50,
        core_sigma_u=0.05, core_sigma_v=0.05,
        medium_sigma_u=0.09, medium_sigma_v=0.09,
        core_weight=0.97, medium_weight=0.03, tail_weight=0.0,
        safe_margin_u=0.12, safe_margin_v=0.12,
        provisional=True,
    ),
}


class ClickProfileManager:
    """内存里的 profile 注册表。第一版：只有内置默认 profile，无配置加载、无用户 override。

    LEGACY_UNIFORM 路径**不经过**这里（`ClickSampler` 只在显式请求 HABIT/STRICT/UNIFORM
    时才 resolve profile），所以本类不参与默认生产点击。
    """

    def __init__(self, profiles: Mapping[str, ClickProfile] | None = None) -> None:
        self._profiles: dict[str, ClickProfile] = dict(profiles) if profiles else dict(DEFAULT_PROFILES)

    def get(self, name: str) -> ClickProfile:
        """按名取 profile；找不到 fallback 到 `default`（是 target-specific → 类别
        profile → default 这条自然回退链的最小版本）。"""
        prof = self._profiles.get(name)
        if prof is not None:
            return prof
        return self._profiles["default"]

    def names(self) -> list[str]:
        return sorted(self._profiles)


# 进程内默认单例（只读用途）。需要自定义 profile 集时自己 new ClickProfileManager。
_DEFAULT_MANAGER = ClickProfileManager()


def resolve_profile(profile) -> ClickProfile:
    """把 `profile` 参数（None / 名字 / ClickProfile）统一成一个 `ClickProfile`。

    - `None` → `default`
    - `str` → 默认管理器按名取（找不到回退 `default`）
    - `ClickProfile` → 原样返回
    """
    if profile is None:
        return _DEFAULT_MANAGER.get("default")
    if isinstance(profile, ClickProfile):
        return profile
    if isinstance(profile, str):
        return _DEFAULT_MANAGER.get(profile)
    raise TypeError(f"profile 必须是 None / str / ClickProfile，得到 {type(profile)!r}")
