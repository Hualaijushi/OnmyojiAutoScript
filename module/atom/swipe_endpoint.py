# This Python file uses the following encoding: utf-8
"""普通滑动「起点 / 终点具体落在哪里」这一层的唯一公共责任点：SwipeEndpointSampler。

分层（长期契约见 `docs/DECISIONS.md` D022）：

- **业务层**（各 `assets.py` 的 `RuleSwipe(roi_front, roi_back)`）：只表达「往哪个方向、
  滑多远」的意图——用 `roi_front` / `roi_back` 两个 ROI 的相对位置编码方向与基准距离。
- **端点采样层**（本模块）：把这对 ROI 变成一次滑动的**具体整数起点 / 终点**。起点、终点
  **各自独立采样**（不是给整条线加一个共同平移量——那只会让同类滑动变成一簇平行线），
  但联合校验方向与有效距离不被破坏。
- **`TouchSwipeModel`**（`module/device/touch_swipe_model.py`）：只负责「两点之间怎么走」
  （minimum-jerk + 曲率 + 逐段 dt + 尾段慢拖），本模块**不碰**。
- **执行层**（`Control` / minitouch）：把点列发给设备。

### 为什么要这一层

`RuleSwipe.coord()`（旧路径）对 `roi_front` / `roi_back` 各做一次 `random_center_point_in_roi`
（3 次采样取均值的中心偏置）。问题不在「起终点是否共享偏移」——它们本来就独立——而在
大量 swipe 资产的 `roi_front` / `roi_back` 只有 ~21×21 甚至 4×4 / 2×4，中心偏置在这么小的
框里有效标准差只有 3~6px，于是同类滑动的起点挤成一团、终点挤成一团、轨迹高度重合
（OASX 行为统计已观察到）。

### 采样策略（沿用「点击空间模型」的思路，见 `module/click_sampler.py` HABIT）

对**每个端点**：

- 参照点 `preferred` = 该 ROI 整数取值范围的几何中点（不发明业务坐标）。
- 「游走尺度」`offset_scale` 由**业务基准距离**（两 ROI 中点距离）按比例推出，夹在
  `[offset_min_px, offset_max_px]`——短滑动少游走、长滑动多游走，且有绝对上限。
- 主成分（~85%）：以 `preferred` 为中心、`core_sigma_frac * offset_scale` 为标准差的高斯
  （比旧中心偏置更散，但仍集中）。尾部（~15%）：`tail_sigma_frac * offset_scale` 的更宽
  高斯。二选一后按轴采样。
- **轴向 ROI 足够大**（`>= wide_axis_px`）时该轴**逐字保持旧 `_center_biased_int` 行为**
  ——作者已用大 ROI 表达了期望散布（如 `S_BATTLE_RANDOM_*` / Summon `S_RANDOM_SWIPE_*`
  的 100~480px 框），不去二次收缩。两端两轴都大 → 整体等价旧 `coord()`。
- 每个高斯样本必须落在 `[preferred ± hard_half]`（再夹到屏幕安全边界、且不小于原 ROI
  范围）内，有限次 rejection，用尽 → 回退该轴中心（**不对越界样本做边界 clamp**，避免
  边缘堆积，与 D014 一致）。

联合校验（起点、终点都采完之后）：

- 采样向量与业务向量夹角 <= `~acos(min_cos)`（默认 ~25°）；
- 采样距离 ∈ `[min_dist_ratio, max_dist_ratio] * 基准距离`，且 >= `abs_min_dist_px`
  （避免落进 `BaseTask.swipe_trajectory` 的 <10px 端点回退）；
- 业务主轴方向符号必须一致（「向上滚」不能采成「向下」）。

任一不满足 → 重新整体采样，`joint_max_attempts` 次用尽 → 回退到 `(preferred_start,
preferred_end)` 两个中点（一定过校验：夹角 0、距离 = 基准距离）。全程**有界**，无 `while True`。

参数（`SwipeEndpointParams`，frozen）全部是 **provisional 工程默认**，等 Level C 用真实
滑动分布标定；本模块只负责「怎么采」，不写死某个资产的偏好。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot as _hypot
from numbers import Integral

from module.base.utils.random import _center_biased_int, _rng, random_normal


def _as_int_roi(roi) -> tuple[int, int, int, int]:
    """校验并返回 `(x, y, w, h)` 整数四元组（与 `random_point_in_roi` 同口径）。"""
    x, y, w, h = roi
    if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (x, y, w, h)):
        raise TypeError(f'ROI 必须由整数组成：{roi}')
    if w <= 0 or h <= 0:
        raise ValueError(f'ROI 宽高必须大于 0：{roi}')
    return int(x), int(y), int(w), int(h)


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def _iround(value: float) -> int:
    return int(round(value))


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


@dataclass(frozen=True)
class SwipeEndpointParams:
    """端点空间分布的有界可调参数。默认值面向常见 80~700px 普通滑动，全部 provisional。"""

    # 轴向 ROI >= 该像素：该轴保持旧 `_center_biased_int`，不做 v2（作者已用大 ROI 表达散布）
    wide_axis_px: int = 48
    # 游走尺度 = 该比例 × 业务基准距离，再夹到 [min, max]
    offset_dist_ratio: float = 0.12
    offset_min_px: float = 6.0
    offset_max_px: float = 40.0
    # 单端点硬夹半宽 = min(clamp_sigma_mult × 游走尺度, clamp_dist_ratio × 基准距离)
    clamp_sigma_mult: float = 2.4
    clamp_dist_ratio: float = 0.30
    # 主成分（窄高斯）权重；其余为 tail（宽高斯）
    core_weight: float = 0.85
    core_sigma_frac: float = 0.55
    tail_sigma_frac: float = 1.30
    # 单轴高斯越界 rejection 上限 → 回退该轴中心
    axis_max_attempts: int = 8
    # 联合方向 / 距离校验
    min_cos: float = 0.906            # 采样向量与业务向量夹角 <= ~25°
    min_dist_ratio: float = 0.55
    max_dist_ratio: float = 1.45
    abs_min_dist_px: float = 10.0
    joint_max_attempts: int = 6      # 用尽 → 回退 (preferred_start, preferred_end)
    # 屏幕安全边界（最终整数坐标兜底夹取；1280×720，留 2px 边）
    screen_x_lo: int = 2
    screen_x_hi: int = 1277
    screen_y_lo: int = 2
    screen_y_hi: int = 717

    def __post_init__(self) -> None:
        if self.wide_axis_px < 2:
            raise ValueError(f'wide_axis_px 至少为 2：{self.wide_axis_px}')
        if self.offset_min_px <= 0 or self.offset_max_px < self.offset_min_px:
            raise ValueError(
                f'游走尺度边界非法：min={self.offset_min_px} max={self.offset_max_px}')
        for key in ('offset_dist_ratio', 'clamp_sigma_mult', 'clamp_dist_ratio',
                    'core_sigma_frac', 'tail_sigma_frac'):
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} 必须为正：{getattr(self, key)}')
        if not (0.0 < self.core_weight <= 1.0):
            raise ValueError(f'core_weight 必须在 (0, 1]：{self.core_weight}')
        if not (0.0 <= self.min_cos < 1.0):
            raise ValueError(f'min_cos 必须在 [0, 1)：{self.min_cos}')
        if not (0.0 < self.min_dist_ratio <= 1.0 <= self.max_dist_ratio):
            raise ValueError(
                f'距离比例非法：min={self.min_dist_ratio} max={self.max_dist_ratio}')
        if self.abs_min_dist_px < 0:
            raise ValueError('abs_min_dist_px 不能为负')
        if self.axis_max_attempts < 1 or self.joint_max_attempts < 1:
            raise ValueError('rejection / 重采样上限必须 >= 1')
        if self.screen_x_hi <= self.screen_x_lo or self.screen_y_hi <= self.screen_y_lo:
            raise ValueError('屏幕安全边界非法')


_DEFAULT_PARAMS = SwipeEndpointParams()


def _axis_center(origin: int, size: int) -> float:
    """ROI 某一轴的整数取值范围中点（`origin .. origin + size - 1` 的中点）。"""
    return origin + (size - 1) / 2.0


def _sample_axis(origin: int, size: int, center: float, sigma: float,
                 hard_half: float, screen_lo: int, screen_hi: int,
                 p: SwipeEndpointParams) -> int:
    """单轴采样：宽轴保持旧中心偏置；窄轴以 center 为均值的高斯 + 有限 rejection。"""
    if size >= p.wide_axis_px:
        return _center_biased_int(origin, origin + size)
    lo = center - hard_half
    hi = center + hard_half
    # 不小于原 ROI 的整数范围（v2 只放宽、不收窄作者给的框）
    lo = min(lo, float(origin))
    hi = max(hi, float(origin + size - 1))
    # 最终夹到屏幕安全边界
    lo = max(lo, float(screen_lo))
    hi = min(hi, float(screen_hi))
    if hi <= lo:
        return _iround(_clamp(center, screen_lo, screen_hi))
    for _ in range(p.axis_max_attempts):
        value = random_normal(center, sigma)
        if lo <= value <= hi:
            return _iround(value)
    return _iround(_clamp(center, lo, hi))


def _sample_one_endpoint(roi: tuple[int, int, int, int], cx: float, cy: float,
                         offset_scale: float, hard_half: float,
                         p: SwipeEndpointParams) -> tuple[int, int]:
    x, y, w, h = roi
    core = _rng.random() < p.core_weight
    sigma = (p.core_sigma_frac if core else p.tail_sigma_frac) * offset_scale
    sx = _sample_axis(x, w, cx, sigma, hard_half, p.screen_x_lo, p.screen_x_hi, p)
    sy = _sample_axis(y, h, cy, sigma, hard_half, p.screen_y_lo, p.screen_y_hi, p)
    return sx, sy


def _direction_distance_ok(sx: int, sy: int, ex: int, ey: int,
                           dx0: float, dy0: float, base_dist: float,
                           p: SwipeEndpointParams) -> bool:
    dx, dy = ex - sx, ey - sy
    dist = _hypot(dx, dy)
    if dist < p.abs_min_dist_px:
        return False
    if not (p.min_dist_ratio * base_dist <= dist <= p.max_dist_ratio * base_dist):
        return False
    cos_theta = (dx * dx0 + dy * dy0) / (dist * base_dist)
    if cos_theta < p.min_cos:
        return False
    # 业务主轴方向符号兜底（cos 已基本保证）
    if abs(dx0) >= abs(dy0):
        if dx0 != 0 and _sign(dx) != _sign(dx0):
            return False
    else:
        if dy0 != 0 and _sign(dy) != _sign(dy0):
            return False
    return True


def sample_swipe_endpoints(roi_front, roi_back, *,
                           params: SwipeEndpointParams = None) -> tuple[int, int, int, int]:
    """由 `roi_front` / `roi_back` 采样一次普通滑动的整数起点 / 终点。

    Args:
        roi_front: 起点 ROI `(x, y, w, h)`（整数，`w > 0` 且 `h > 0`）。
        roi_back: 终点 ROI，同格式。
        params: 覆盖默认 `SwipeEndpointParams`；`None` 用模块默认。

    Returns:
        `(start_x, start_y, end_x, end_y)` 四个整数。方向 / 有效距离与「两 ROI 中点连线」
        一致（在 params 容差内）；两端各自独立采样、不是平行平移。

    Raises:
        TypeError / ValueError: ROI 非整数或宽高非正（由 `_as_int_roi` 透传）。
    """
    p = params if params is not None else _DEFAULT_PARAMS
    fx, fy, fw, fh = _as_int_roi(roi_front)
    bx, by, bw, bh = _as_int_roi(roi_back)

    pfx, pfy = _axis_center(fx, fw), _axis_center(fy, fh)
    pbx, pby = _axis_center(bx, bw), _axis_center(by, bh)
    fallback = (_iround(pfx), _iround(pfy), _iround(pbx), _iround(pby))

    # 两端两轴都足够大：作者已用大 ROI 表达期望散布，逐字保持旧 center-biased 行为
    front_wide = fw >= p.wide_axis_px and fh >= p.wide_axis_px
    back_wide = bw >= p.wide_axis_px and bh >= p.wide_axis_px
    if front_wide and back_wide:
        return (_center_biased_int(fx, fx + fw), _center_biased_int(fy, fy + fh),
                _center_biased_int(bx, bx + bw), _center_biased_int(by, by + bh))

    dx0, dy0 = pbx - pfx, pby - pfy
    base_dist = _hypot(dx0, dy0)
    if base_dist < p.abs_min_dist_px:
        # 业务本身就是超短滑动（真实资产基本不会）——直接给中点，不折腾
        return fallback

    offset_scale = _clamp(base_dist * p.offset_dist_ratio, p.offset_min_px, p.offset_max_px)
    hard_half = min(p.clamp_sigma_mult * offset_scale, p.clamp_dist_ratio * base_dist)

    for _ in range(p.joint_max_attempts):
        sx, sy = _sample_one_endpoint((fx, fy, fw, fh), pfx, pfy, offset_scale, hard_half, p)
        ex, ey = _sample_one_endpoint((bx, by, bw, bh), pbx, pby, offset_scale, hard_half, p)
        if _direction_distance_ok(sx, sy, ex, ey, dx0, dy0, base_dist, p):
            return (sx, sy, ex, ey)
    return fallback
