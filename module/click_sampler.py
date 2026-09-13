# This Python file uses the following encoding: utf-8
"""点击坐标空间采样的唯一公共责任点：ClickSampler。

`RuleImage` / `RuleClick` / `RuleOcr` / `RuleGif` 的 `coord()` 统一经这里，把当前 ROI
变成最终整数点击坐标 `(x, y)`，再交给 `BaseTask` → `Control` → 各后端执行。
`Control` / minitouch / scrcpy / window_message **不得再对坐标做任何空间 jitter**——
最终点击 x/y 的空间随机化只在本层发生（见 `docs/DECISIONS.md` D014）。

策略（`strategy=`）：

- `LEGACY_UNIFORM`（**默认**，唯一在生产链上被调用的策略）：与既有
  `module.base.utils.random.random_point_in_roi` **逐字等价**（直接调它，共用同一个
  模块级 `SystemRandom`）。极轻：不 resolve profile、不算 Safe ROI、不构造任何状态。
  `Rule*.coord()` 全部走这一条，引入本层不改变任何生产点击分布。
- `UNIFORM`：在 Safe ROI 内均匀。语义上是「该目标本来就应该全区域均匀」的显式声明
  （区别于 `LEGACY_UNIFORM` 这个「兼容旧行为」的 fallback）。
- `HABIT`：三成分 mixture（core / medium / tail），每次点击先按权重选一个成分再采样一次；
  core / medium 是 ROI 相对的独立二维正态，tail 是 Safe ROI 内均匀。所有候选点必须落在
  Safe ROI 内，否则有限次 rejection 重采样，仍失败则 fallback 到 Safe ROI 内的热点投影
  （单点，**不做边界 clamp**，避免边缘堆积）。
- `STRICT`：给 tiny / small / 高风险目标用，可靠性优先。用 HABIT 的机制但强制窄 profile
  （无 tail、core sigma 受 `STRICT_MAX_CORE_SIGMA` 约束）。

参数在 `module/click_profile.py`（`ClickProfile` / `ClickProfileManager`），本层只负责
「怎么采样」，不在 if/else 里写死热点 / spread / margin。

`Rule*.coord()` 只传 `LEGACY_UNIFORM`（默认），默认生产点击分布不受本层其它策略影响。
非 LEGACY 策略只有**逐调用点显式 opt-in**才会走到：
- `HABIT`：GeneralBattle Settlement RD（`_settlement_click`，Contract v2）；`RyouToppa.C_AREA_1`
  目标卡片（经 `ClickSampler.sample_point` + `wide_card` profile，T7-3.2 首个普通 Point Target
  生产 opt-in）。
- `STRICT` / `UNIFORM`：当前没有任何生产消费者。
启用某个具体目标是显式 opt-in + 真机验证，不按 ROI 尺寸自动切换策略。
"""

from __future__ import annotations

from dataclasses import replace
from numbers import Integral

from module.base.utils.random import random_normal, random_point_in_roi
from module.click_profile import (
    STRICT_MAX_CORE_SIGMA,
    ClickProfile,
    adapt_point_profile,
    adapt_preferred_by_size,
    resolve_profile,
)
from module.click_preference import (
    REGION_FALLBACK_PROFILE,
    Provenance,
    resolve_target_preference,
)
from module.base.utils.random import _rng  # 复用同一个模块级 SystemRandom，不新建 RNG

# 兼容旧行为的默认策略（唯一在生产链上被调用的）。
LEGACY_UNIFORM = "legacy_uniform"
# 显式声明「该目标业务语义就是全区域均匀」。
STRATEGY_UNIFORM = "uniform"
# 三成分 mixture 习惯模型。
STRATEGY_HABIT = "habit"
# 小目标 / 高风险目标的窄分布。
STRATEGY_STRICT = "strict"

_COMPONENTS = ("core", "medium", "tail")


def _as_int_roi(roi) -> tuple[int, int, int, int]:
    """校验并返回 `(x, y, w, h)` 整数四元组（与 `random_point_in_roi` 同口径）。"""
    x, y, w, h = roi
    if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (x, y, w, h)):
        raise TypeError(f'ROI 必须由整数组成：{roi}')
    if w <= 0 or h <= 0:
        raise ValueError(f'ROI 宽高必须大于 0：{roi}')
    return int(x), int(y), int(w), int(h)


def _safe_roi(roi, profile: ClickProfile) -> tuple[int, int, int, int]:
    """由原 ROI + profile 的相对内边距算出 Safe ROI（整数 `(x, y, w, h)`，半开）。

    左右各收 `safe_margin_u * w`，上下各收 `safe_margin_v * h`。收完宽或高 < 1 像素则
    视为配置错误抛 `ValueError`（不静默退化）。
    """
    x, y, w, h = _as_int_roi(roi)
    dx = int(round(profile.safe_margin_u * w))
    dy = int(round(profile.safe_margin_v * h))
    sx, sy = x + dx, y + dy
    sw, sh = w - 2 * dx, h - 2 * dy
    if sw < 1 or sh < 1:
        raise ValueError(
            f'Safe ROI 退化（profile={profile.name!r} margin=({profile.safe_margin_u}, '
            f'{profile.safe_margin_v}) 对 ROI {roi} 收成 {(sw, sh)}）'
        )
    return sx, sy, sw, sh


def _inside(px: int, py: int, safe: tuple[int, int, int, int]) -> bool:
    sx, sy, sw, sh = safe
    return sx <= px < sx + sw and sy <= py < sy + sh


def _choose_component(weights: tuple[float, float, float]) -> str:
    """按归一化权重抽一个成分（`'core'` / `'medium'` / `'tail'`）。测试可 patch 本函数。"""
    r = _rng.random()
    acc = 0.0
    for name, wgt in zip(_COMPONENTS, weights):
        acc += wgt
        if r < acc:
            return name
    return _COMPONENTS[-1]


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def _fallback_point(roi, profile: ClickProfile, safe: tuple[int, int, int, int]) -> tuple[int, int]:
    """rejection 用尽后的确定安全点：把热点 u/v 夹进内边距范围，投影到原 ROI 再落进 Safe ROI。

    这是**一个确定点**，不是对越界样本做边界 clamp，所以不会在四条边上堆积。
    """
    x, y, w, h = _as_int_roi(roi)
    sx, sy, sw, sh = safe
    u = _clamp(profile.preferred_u, profile.safe_margin_u, 1.0 - profile.safe_margin_u)
    v = _clamp(profile.preferred_v, profile.safe_margin_v, 1.0 - profile.safe_margin_v)
    px = int(round(x + u * w))
    py = int(round(y + v * h))
    px = int(_clamp(px, sx, sx + sw - 1))
    py = int(_clamp(py, sy, sy + sh - 1))
    return px, py


def _sample_gaussian_component(
    roi, profile: ClickProfile, sigma_u: float, sigma_v: float,
    safe: tuple[int, int, int, int],
) -> tuple[int, int]:
    """core / medium 成分：ROI 相对独立二维正态，有限次 rejection，失败 fallback。"""
    x, y, w, h = _as_int_roi(roi)
    for _ in range(int(profile.max_attempts)):
        u = random_normal(profile.preferred_u, sigma_u)
        v = random_normal(profile.preferred_v, sigma_v)
        px = int(round(x + u * w))
        py = int(round(y + v * h))
        if _inside(px, py, safe):
            return px, py
    return _fallback_point(roi, profile, safe)


def _sample_mixture(roi, profile: ClickProfile) -> tuple[int, int]:
    """HABIT / STRICT 的核心：选一个成分再采样一次。"""
    safe = _safe_roi(roi, profile)
    component = _choose_component(profile.normalized_weights())
    if component == "core":
        return _sample_gaussian_component(
            roi, profile, profile.core_sigma_u, profile.core_sigma_v, safe
        )
    if component == "medium":
        return _sample_gaussian_component(
            roi, profile, profile.medium_sigma_u, profile.medium_sigma_v, safe
        )
    # tail：Safe ROI 内均匀。仍在安全区内，不会变成真正的误点。
    return random_point_in_roi(safe)


class ClickSampler:
    """把 ROI 转成最终整数点击坐标。`LEGACY_UNIFORM` 路径轻量、无状态、无 IO、无锁、无 numpy。"""

    @staticmethod
    def sample(roi, *, strategy: str = LEGACY_UNIFORM, profile=None) -> tuple[int, int]:
        """在 `roi` 内采样一个整数点击坐标。

        Args:
            roi: 当前 ROI，格式 `(x, y, w, h)`（整数，`w > 0` 且 `h > 0`）。每次传入
                **当前** ROI（如 `RuleImage.roi_front` 在 `match()` 后被 `_update_roi_front`
                改写的值），本层不缓存。
            strategy: `LEGACY_UNIFORM`（默认）/ `UNIFORM` / `HABIT` / `STRICT`。
            profile: 仅 `HABIT` / `STRICT` / `UNIFORM` 用。`None` / profile 名 / `ClickProfile`
                实例；`None` 时 `HABIT`·`UNIFORM` 用 `default`，`STRICT` 用 `strict`。

        Returns:
            `(x, y)` 整数坐标。`LEGACY_UNIFORM` 与 `random_point_in_roi(roi)` 完全等价。
            其余策略保证结果落在对应的 Safe ROI 内。

        Raises:
            ValueError: 未知策略 / ROI 或 profile 配置非法 / STRICT 拿到过宽的 profile。
            TypeError: 非整数 ROI（由校验透传）。
        """
        if strategy == LEGACY_UNIFORM:
            return random_point_in_roi(roi)

        if strategy == STRATEGY_UNIFORM:
            prof = resolve_profile("default" if profile is None else profile)
            return random_point_in_roi(_safe_roi(roi, prof))

        if strategy == STRATEGY_HABIT:
            prof = resolve_profile(profile)
            return _sample_mixture(roi, prof)

        if strategy == STRATEGY_STRICT:
            prof = resolve_profile("strict" if profile is None else profile)
            if prof.core_sigma_u > STRICT_MAX_CORE_SIGMA or prof.core_sigma_v > STRICT_MAX_CORE_SIGMA:
                raise ValueError(
                    f"STRICT 需要窄 profile：{prof.name!r} 的 core sigma "
                    f"({prof.core_sigma_u}, {prof.core_sigma_v}) 超过上限 {STRICT_MAX_CORE_SIGMA}"
                )
            return _sample_mixture(roi, prof.without_tail())

        raise ValueError(f"未知 ClickSampler 策略：{strategy!r}")

    @staticmethod
    def sample_point(roi, base_profile=None) -> tuple[int, int]:
        """Point Target 显式生产 opt-in 的最小组合入口。

        把「语义基础 profile」按当前 `roi` 的尺寸做连续适配（`adapt_point_profile`），
        再走 `HABIT` 采样一次。等价于：

            sample(roi, strategy=HABIT, profile=adapt_point_profile(base_profile, roi))

        只给「某个具体调用点显式启用个人热点 + 连续尺寸适配」用——是否启用某个 target
        是**逐调用点的显式 opt-in**，本方法不按 ROI 尺寸自动切换策略，`Rule*.coord()`
        默认路径也**不经过**这里（仍是 `LEGACY_UNIFORM`）。见 `docs/DECISIONS.md` D014。

        Args:
            roi: 当前 ROI `(x, y, w, h)`（整数）。同时用于尺寸适配与最终采样，每次传入
                当前值（如 `RuleClick.roi_front`），本层不缓存。
            base_profile: `None` / profile 名 / `ClickProfile` 实例（经 `resolve_profile`
                统一）。`adapt_point_profile` 只连续调整 `preferred`，`sigma` / `weights` /
                `margin` / `provisional` / `name` 原样保留。

        Returns:
            `(x, y)` 整数坐标，落在该（适配后）profile 的 Safe ROI 内。
        """
        effective = adapt_point_profile(resolve_profile(base_profile), roi)
        return ClickSampler.sample(roi, strategy=STRATEGY_HABIT, profile=effective)

    @staticmethod
    def sample_target(roi, target_name) -> tuple[int, int]:
        """T7-5 全局默认 Point 采样：按 target 身份取 preferred 热点 → 语义 profile → 连续
        尺寸适配 → `HABIT` 采样一次。

        `Rule*.coord()`（`RuleClick` / `RuleImage` / `RuleOcr` / `RuleGif` / `RuleLongClick`）
        的**默认路径**就是这一条 —— 普通生产 Point 点击不再是整 ROI `LEGACY_UNIFORM`。

        - 已登记 target（`module/click_preference.py` 的 `TARGET_PREFERENCES`）→ 用它的
          `preferred_u/v` + `profile_name`（例：`area_1` → `(0.58, 0.59)` + `wide_card`）。
        - 未登记 / 空名 → `RULE_FALLBACK`：基础热点 `(0.58, 0.59)` + `default_point`
          shape profile，再按 ROI 短边做 24/96 smoothstep。小目标趋近中心，大目标释放完整热点。

        与 `sample_point` 的关系：`sample_point` 是「某个具体调用点显式启用某个语义 profile」
        （逐调用点 opt-in，传 `base_profile`）；`sample_target` 是「按 target 身份查表得到
        默认行为」。两者都最终走 `adapt_point_profile` + `HABIT`，**空间随机只发生这一次**
        （`Control` / 后端不得再 jitter，见 `docs/DECISIONS.md` D014）。

        Args:
            roi: 当前运行时 ROI `(x, y, w, h)`（整数）。同时用于尺寸适配与最终采样，每次
                传入当前值（如 `RuleImage.roi_front` 在 `match()` 后被改写的值），本层不缓存。
            target_name: 该点击目标的稳定身份（= `rule.name`，与 BehaviorTrace 的 `target`
                同名）。`None` / 空串 → `RULE_FALLBACK`。

        Returns:
            `(x, y)` 整数坐标，落在（适配后 profile 的）Safe ROI 内。

        Raises:
            ValueError / TypeError: ROI 非法（由 `adapt_point_profile` / `_as_int_roi` 透传，
                口径与 `LEGACY_UNIFORM` 一致）。
        """
        pref = resolve_target_preference(target_name)
        base = resolve_profile(pref.profile_name)
        if base.preferred_u != pref.preferred_u or base.preferred_v != pref.preferred_v:
            base = replace(base, preferred_u=pref.preferred_u, preferred_v=pref.preferred_v)
        effective = adapt_point_profile(base, roi)
        return ClickSampler.sample(roi, strategy=STRATEGY_HABIT, profile=effective)

    @staticmethod
    def sample_region(roi, target_name) -> tuple[int, int]:
        """T7-5 Stage 2 Region 采样：业务已选定 region，本方法只在**该 region 内**按 preferred
        热点 + 偏移模型取一次点。

        与 `sample_target` 的区别：**不做 `adapt_point_profile` 的 Point shape 尺寸适配**。
        Region 只复用 `adapt_preferred_by_size` 的 24/96 热点规则，不收缩 `default_region`
        的 sigma / tail；因此细长安全区会按短边收敛热点，但仍保留 Region 分布形状。

        - 已登记 EMPIRICAL target（将来 Level C 标定后）→ 用它自己的
          `preferred_u/v` + `profile_name`。
        - 未登记 / RULE_FALLBACK → 基础热点 `(0.58, 0.59)` + `default_region`，再按 ROI
          短边计算有效热点。来源仍是规则推导，不能记成 EMPIRICAL。

        业务的 region 选择（GeneralBattle `_select_reward_region` 的 marker → DEFAULT、否则
        80% SAVE_RIGHT / 20% SAVE_BOTTOM）与本方法**完全无关**——本方法只收「选定 region 内
        怎么取坐标」。空间随机只发生这一次（无 double jitter）。

        Args:
            roi: 已选定 region 的 ROI `(x, y, w, h)`（整数）。
            target_name: 该 region 的稳定身份（= `rule.name`，与 BehaviorTrace `target` 同名）。

        Returns:
            `(x, y)` 整数坐标，落在该 region 的 Safe ROI 内。
        """
        pref = resolve_target_preference(target_name)
        profile_name = (
            REGION_FALLBACK_PROFILE
            if pref.provenance is Provenance.RULE_FALLBACK
            else pref.profile_name
        )
        base = resolve_profile(profile_name)
        effective_u, effective_v = adapt_preferred_by_size(
            pref.preferred_u, pref.preferred_v, roi
        )
        effective = replace(base, preferred_u=effective_u, preferred_v=effective_v)
        return ClickSampler.sample(roi, strategy=STRATEGY_HABIT, profile=effective)
