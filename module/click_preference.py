# This Python file uses the following encoding: utf-8
"""Target Preference Registry —— 「这个点击目标的习惯热点在哪」这一半职责（T7-5）。

与 `module/click_profile.py` / `module/click_sampler.py` 的分工：

- `ClickProfile`（`click_profile.py`）：一类目标的空间分布**形状**（core/medium 离散度、
  成分权重、Safe ROI 内边距、尺寸适配基础参数）。不含「具体哪个 target 的热点在哪」。
- `TargetPreference`（本模块）：**单个具体点击目标**（按 `rule.name` 索引，与 BehaviorTrace
  的 `target` 同名）的 preferred 热点（ROI 相对 `u / v`）+ 该热点的来源与可信度。
- `ClickSampler.sample_target` / `sample_region`（`click_sampler.py`）：先按来源解析热点锚点，
  再按运行时 ROI short_side 做 preferred 尺寸适配，最后写入对应 shape profile 并 `HABIT` 采样。

热点解析遵循两级正式优先级：目标有真实人工标定时使用 `EMPIRICAL`；否则使用
`RULE_FALLBACK` 的统一基础锚点 `(0.58, 0.59)`。二者数值可以相同，但来源必须可区分。
基础锚点再按 ROI 的 24/96 smoothstep 适配：小目标趋近中心，大目标完整释放右下热点。
没有人工数据仍不退回 Uniform，也不再把 `(0.5, 0.5)` 当作大目标最终热点。

本模块是**静态代码 registry + 离线人工标定**：不做在线学习 / EMA / 点击历史 / 配置系统改造 /
numpy。未来若要在线学习 preferred，身份键至少 `task + page + target + 记录时 ROI 几何`
（当前 BehaviorTrace 缺 page / ROI 字段，见 D014）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Provenance(str, Enum):
    """preferred 热点的来源，决定可信度与「能不能声称是该 target 自己测出来的」。"""

    # 有该 target 自己的人工点击样本 + 正确的 runtime / static ROI basis + ROI-relative 统计。
    EMPIRICAL = "empirical"
    # 没有该 target 自己的人工数据，但与某个 EMPIRICAL target 明确属于同一种交互语义，
    # 借用其热点方向。必须标这个，不能冒充 EMPIRICAL。
    SEMANTIC_TRANSFER = "semantic_transfer"
    # 有一定历史 / 屏幕空间经验，但缺少可靠的 ROI-relative 标定
    #（例：战斗「开始 / 进攻」按钮，屏幕空间热点已知、runtime ROI-relative 未标定）。
    PROVISIONAL = "provisional"
    # 没有该 target 自己的人工数据 → 使用统一 Rule Fallback Anchor，并按 ROI 尺寸适配。
    # 不能冒充 EMPIRICAL，也不是整 ROI Uniform。
    RULE_FALLBACK = "rule_fallback"


# 无人工热点时用的统一规则锚点。该值是工程规则，不代表任一 target 的人工采样结果。
RULE_BASE_PREFERRED = (0.58, 0.59)
# 无人工热点时用的通用 Point shape profile 名（定义在 `click_profile.DEFAULT_PROFILES`）。
RULE_FALLBACK_PROFILE = "default_point"
# Region Target（业务已选定的大安全区）的兜底 shape profile 名——spread 比 Point 宽；
# `ClickSampler.sample_region` 只适配 preferred，不继承 Point 的 sigma / tail 尺寸收缩。
REGION_FALLBACK_PROFILE = "default_region"


@dataclass(frozen=True)
class TargetPreference:
    """单个点击目标的习惯热点（ROI 相对）+ 语义 profile 名 + 来源可信度。"""

    target_name: str
    preferred_u: float
    preferred_v: float
    # 分布形状用哪个 `ClickProfile`（`click_profile.DEFAULT_PROFILES` 的键）。
    profile_name: str
    provenance: Provenance
    # 0..1 粗略可信度：EMPIRICAL 偏高、PROVISIONAL 居中、RULE_FALLBACK = 0。
    confidence: float = 0.0
    note: str = ""

    def __post_init__(self) -> None:
        for key in ("preferred_u", "preferred_v"):
            val = getattr(self, key)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{key} 必须在 [0, 1]：{val}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence 必须在 [0, 1]：{self.confidence}")
        if not self.profile_name:
            raise ValueError("TargetPreference.profile_name 不能为空")


# ------------------------------------------------------------------------------------------
# 显式标定或需要特定 shape profile 的 target（按 rule.name 索引）。未登记的一律
# RULE_FALLBACK（见下方 resolve_*）。
# ------------------------------------------------------------------------------------------
# 只在这里放**有真实依据**的条目。禁止「看起来这个按钮应该点右下 → 无依据填 (0.64,0.71)」。
# 允许来源见 `Provenance`。当前仓库能拿到可靠 ROI-relative 人工数据的只有寮突破目标卡片。
TARGET_PREFERENCES: dict[str, TargetPreference] = {
    # 寮突破目标卡片（EMPIRICAL，单账号单会话，仍标 confidence 偏保守）：
    #   人工采样 `log/manual_click/yys1_2026-09-01.jsonl` 的 cluster_A，burst-collapse 后
    #   107 个独立落点，对**真实 RuleClick ROI** `RyouToppa.C_AREA_1` `(514,141,223,116)` 的
    #   inside-only ROI-relative 统计：inside 105/107，mean=(0.582,0.586)≈median=(0.579,0.586)，
    #   std≈(0.13,0.14)。语义 profile = `wide_card`（其 core σ 0.16 与观察 std 量级相符）。
    #   `C_AREA_1` 目前经 `RyouToppa._click_toppa_area` 的显式 `sample_point(roi, 'wide_card')`
    #   走同一条链（T7-3.2）；这里登记后，即使某天改回默认 `.coord()` 路径，热点也不变。
    "area_1": TargetPreference(
        target_name="area_1",
        preferred_u=0.58,
        preferred_v=0.59,
        profile_name="wide_card",
        provenance=Provenance.EMPIRICAL,
        confidence=0.6,
        note="manual_click yys1_2026-09-01 cluster_A vs RyouToppa.C_AREA_1 ROI；单账号单会话",
    ),
    # T7-5 Stage 2：GeneralBattle Settlement V3 的三个大安全区（业务 `_select_reward_region`
    # 先选好 region，本条只管「选定 region 内怎么取点」）。当前无可靠人工 Region 热点数据 →
    # RULE_FALLBACK anchor=(0.58,0.59) + `default_region` shape profile，再按各 ROI 短边适配热点。
    # 显式登记而非靠 resolver 兜底：① 它们确实需要 `default_region` 而非 `default_point`；
    # ② 将来 Level C 用 BehaviorTrace/OASX 标定后可就地升 EMPIRICAL。经 `ClickSampler.sample_region`。
    "random_default": TargetPreference(
        target_name="random_default", preferred_u=RULE_BASE_PREFERRED[0], preferred_v=RULE_BASE_PREFERRED[1],
        profile_name="default_region", provenance=Provenance.RULE_FALLBACK, confidence=0.0,
        note="GeneralBattle Settlement V3 默认推进安全区；无人工数据，使用统一 Rule Fallback Anchor",
    ),
    "random_save_right": TargetPreference(
        target_name="random_save_right", preferred_u=RULE_BASE_PREFERRED[0], preferred_v=RULE_BASE_PREFERRED[1],
        profile_name="default_region", provenance=Provenance.RULE_FALLBACK, confidence=0.0,
        note="GeneralBattle Settlement V3 右侧安全区；无人工数据，使用统一 Rule Fallback Anchor",
    ),
    "random_save_bottom": TargetPreference(
        target_name="random_save_bottom", preferred_u=RULE_BASE_PREFERRED[0], preferred_v=RULE_BASE_PREFERRED[1],
        profile_name="default_region", provenance=Provenance.RULE_FALLBACK, confidence=0.0,
        note="GeneralBattle Settlement V3 底部安全区；无人工数据，使用统一 Rule Fallback Anchor",
    ),
}


def resolve_target_preference(target_name) -> TargetPreference:
    """按 `rule.name` 取 `TargetPreference`；未登记 / 空名 → `RULE_FALLBACK`。

    显式登记的 `EMPIRICAL` 总是优先并原样保留自己的热点锚点；未人工标定目标使用
    `RULE_BASE_PREFERRED`，来源保持 `RULE_FALLBACK`，不能冒充人工数据。
    """
    if target_name:
        pref = TARGET_PREFERENCES.get(target_name)
        if pref is not None:
            return pref
    return TargetPreference(
        target_name=str(target_name) if target_name else "",
        preferred_u=RULE_BASE_PREFERRED[0],
        preferred_v=RULE_BASE_PREFERRED[1],
        profile_name=RULE_FALLBACK_PROFILE,
        provenance=Provenance.RULE_FALLBACK,
        confidence=0.0,
    )


def provenance_counts() -> dict[str, int]:
    """registry 里各 provenance 的条目数（inventory / 报告用）。"""
    counts = {p.value: 0 for p in Provenance}
    for pref in TARGET_PREFERENCES.values():
        counts[pref.provenance.value] += 1
    return counts
