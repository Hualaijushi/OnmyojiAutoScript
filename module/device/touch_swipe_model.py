# This Python file uses the following encoding: utf-8
"""TouchSwipeModel —— minitouch 自定义滑动轨迹的「怎么移动」这一半职责。

分工（Plan B，见 `docs/DECISIONS.md` D018 / `docs/Minitouch自定义轨迹能力审查.md`）：

- `TouchSwipeModel`（本模块）：**纯数学轨迹生成器**。给定起点 / 终点 + 一组有界形状参数，
  产出 `list[(x, y, dt_ms)]`。不 import device / Config / BaseTask，可脱离设备单测。
- `Minitouch.swipe_minitouch_trajectory`（`method/minitouch.py`）：把点列表逐点发给 minitouch。
- `Control.swipe_trajectory`（`control.py`）：显式 opt-in 入口 + BehaviorTrace。

本模块**不涉及**：截图 / FrameWait / OCR / ROI / 业务状态 / minitouch socket / BehaviorTrace /
设备旋转与分辨率换算（换算由 `CommandBuilder.convert` 负责）/ pressure（pressure 只是执行层的
协议兼容字段，不是轨迹形状变量）。

轨迹结构（不是「随机 Bezier」，有明确运动学）：

- 位置进度用 minimum-jerk 归一化函数 ``s(t) = 10 t^3 - 15 t^4 + 6 t^5``（``t ∈ [0, 1]``）：
  ``s(0)=0``、``s(1)=1``、``s'(0)=s'(1)=0``、``s'`` 在 ``t=0.5`` 最大 —— 起步慢、中段快、收尾慢。
  ``s`` 就是「已走距离占全程的比例」。
- 横向曲率是**整体**函数 ``curve_amplitude * sin(pi * t)``：两端为 0、中间幅度最大；
  ``curve_amplitude`` 一次采样、可正可负（右弯 / 左弯 / 近直线），绝对值有上限。
  不给每个 MOVE 点叠加独立随机抖动，避免锯齿 / 蛇形。**曲率参数（``max_curve_px`` /
  ``curve_px_ratio``）与本文件第二阶段的时间优化无关，保持不动。**

时间模型（第二阶段）：``final_dt = base_dt(s) + smooth_noise``。

- ``base_dt(s)`` 是**基础趋势**，决定「前慢 → 中快 → 后慢」：
  ``base_dt_ms * (1 + end_slow_ratio*(1 - sin(pi*t)) + tail_slow_gain*smoothstep(k))``，
  其中 ``k`` 是尾段（``s >= tail_start_ratio``）内的归一化进度，``smoothstep`` 在 ``k=0``
  处一阶导为 0，所以进入尾段的放慢是**平滑接续**，不会从 8ms 突跳到 25ms。
- ``smooth_noise`` 只负责小幅自然变化，用一阶低通（EMA）让相邻 MOVE 的扰动**连续**：
  ``raw_i = rng.randint(-dt_jitter_ms, +dt_jitter_ms)``；
  ``noise_i = alpha*noise_{i-1} + (1-alpha)*raw_i``（``noise_0 = 0``）。
  它是 ``[-dt_jitter_ms, +dt_jitter_ms]`` 内取值的凸组合 → **恒有界、零均值、不长期漂移**，
  且 ``|noise_i - noise_{i-1}| <= (1-alpha)*2*dt_jitter_ms`` → 无无界跳变。
  取代第一阶段「每个 MOVE 独立 ``randint(-3,3)``」造成的 speed 尖峰。
- **趋势 > 噪声**：``base_dt(s)`` 跨度 ~[10, 25]ms，``|noise|`` <= ``dt_jitter_ms`` = 3ms。

尾段慢拖（第二阶段）：进入 ``s >= tail_start_ratio``（按**已走距离占比**度量，约最后
10~15% 距离）后 —— MOVE 点按 ``tail_density_gain`` 倍加密、``dt`` 平滑增大、speed 平滑下降；
最终仍精确到原 ``end``，**不额外滑一段、不做固定 pre-UP 停顿、不做过冲后回拉**。

``dt_ms`` 语义（D018 固定，本轮不改）：``trajectory[i][2]`` 是「MOVE 到第 ``i`` 点后 ``wait``
的毫秒（到达当前点之后、下一次移动之前的停留）」。第 0 点是落点，其 ``dt`` 恒为 0 且被
执行层忽略（不加按压前置停顿）。
"""

import math
from dataclasses import dataclass

from module.base.utils.random import random_int


def _minimum_jerk_s(t: float) -> float:
    """minimum-jerk 归一化位置进度 s(t) = 10t³ - 15t⁴ + 6t⁵。"""
    return t * t * t * (10.0 + t * (-15.0 + 6.0 * t))


def _t_for_s(target_s: float) -> float:
    """给定已走距离占比 ``target_s ∈ [0, 1]``，二分求对应的参数 ``t``（s(t) 严格单增）。"""
    if target_s <= 0.0:
        return 0.0
    if target_s >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if _minimum_jerk_s(mid) < target_s:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _smoothstep(k: float) -> float:
    """3k² - 2k³，k 夹到 [0, 1]；k=0 / k=1 处一阶导为 0（平滑起步 / 收尾）。"""
    if k <= 0.0:
        return 0.0
    if k >= 1.0:
        return 1.0
    return k * k * (3.0 - 2.0 * k)


class _DefaultRng:
    """默认随机源：直接复用项目公共 SystemRandom 封装（`module/base/utils/random`）。

    只暴露模型需要的一个整数接口。生产走公共 `random_int`（模块级 `SystemRandom`，见
    D007：新代码优先用公共随机模块、不新建 `SystemRandom` 实例、不引入可 seed 的全局
    `random`）；测试注入确定性实现即可复现。
    """

    @staticmethod
    def randint(min_value: int, max_value: int) -> int:
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        return random_int(int(min_value), int(max_value))


@dataclass(frozen=True)
class TouchSwipeParams:
    """轨迹形状的有界可调参数。默认值面向常见 100~700px 滑动，保持简单可解释。"""

    avg_step_px: float = 16.0            # 目标平均空间步长（决定主段 MOVE 点数量）
    min_points: int = 8                  # 轨迹总点数下限（含起终点）
    max_points: int = 80                 # 轨迹总点数上限（含起终点，尾段加密后留余量）
    base_dt_ms: float = 10.0             # 中段每段基础停留
    end_slow_ratio: float = 0.5          # 两端相对中段的放慢比例（0 = 不放慢）
    dt_jitter_ms: int = 3               # 逐段 dt 原始随机幅度（±），经低通平滑后叠加
    dt_smooth_alpha: float = 0.72        # dt 扰动一阶低通系数（0=每段独立抖动，越接近 1 越平滑），[0,1)
    min_dt_ms: int = 4                 # 单段 dt 下限
    max_dt_ms: int = 34                # 单段 dt 上限（尾段慢拖后需要更高上限）
    max_curve_px: float = 16.0           # 横向曲率幅度绝对上限（第二阶段不动）
    curve_px_ratio: float = 0.12        # 横向曲率幅度相对总距离的上限（第二阶段不动）
    tail_start_ratio: float = 0.85       # 尾段慢拖起点，按「已走距离占比 s」度量，[0.5,1.0)
    tail_density_gain: float = 1.35      # 尾段 MOVE 点密度相对主段的倍数（1.0=不加密），[1.0,4.0]
    tail_slow_gain: float = 0.35         # 尾段额外时间放慢（叠加在 end_slow_ratio 之上），[0.0,3.0]
    tail_correction_enable: bool = False   # 尾部微修正开关（默认关，与尾段慢拖无关，见 §10）
    tail_correction_pct: int = 35       # 开启时的触发概率（百分比）
    tail_correction_max_px: int = 3    # 开启且触发时的修正幅度上限（±，垂直方向）

    def __post_init__(self):
        if self.min_points < 3:
            raise ValueError(f'min_points 至少为 3：{self.min_points}')
        if self.max_points < self.min_points:
            raise ValueError(f'max_points 不能小于 min_points：{self.max_points}')
        if self.avg_step_px <= 0:
            raise ValueError(f'avg_step_px 必须为正：{self.avg_step_px}')
        if self.min_dt_ms < 1 or self.max_dt_ms < self.min_dt_ms:
            raise ValueError(
                f'dt 边界非法：min={self.min_dt_ms} max={self.max_dt_ms}')
        if self.dt_jitter_ms < 0 or self.tail_correction_max_px < 0:
            raise ValueError('抖动 / 修正幅度不能为负')
        if not (0.0 <= self.dt_smooth_alpha < 1.0):
            raise ValueError(f'dt_smooth_alpha 必须在 [0, 1)：{self.dt_smooth_alpha}')
        if not (0.5 <= self.tail_start_ratio < 1.0):
            raise ValueError(f'tail_start_ratio 必须在 [0.5, 1.0)：{self.tail_start_ratio}')
        if not (1.0 <= self.tail_density_gain <= 4.0):
            raise ValueError(f'tail_density_gain 必须在 [1.0, 4.0]：{self.tail_density_gain}')
        if not (0.0 <= self.tail_slow_gain <= 3.0):
            raise ValueError(f'tail_slow_gain 必须在 [0.0, 3.0]：{self.tail_slow_gain}')


# 尾部微修正（默认关，非本轮重点）只作用于**参数 t** 的最后这一段：k = (t - START) / (1 - START)。
# 注意：这与尾段慢拖用的 tail_start_ratio（按「已走距离占比 s」度量）是两个不同的量。
_TAIL_CORRECTION_START = 0.85


class TouchSwipeModel:
    """由起终点 + 形状参数生成一条 minimum-jerk + 有界曲率 + 平滑时间结构 + 尾段慢拖的轨迹。"""

    def __init__(self, params: TouchSwipeParams = None, rng=None):
        self.params = params if params is not None else TouchSwipeParams()
        self._rng = rng if rng is not None else _DefaultRng()

    def generate(self, start, end) -> list:
        """生成一条自定义滑动轨迹。

        Args:
            start: (x, y) 起点（落点）。
            end: (x, y) 终点（必须精确到达，只受整数取整影响）。

        Returns:
            list[tuple[int, int, int]]: ``[(x, y, dt_ms), ...]``。首点 ``dt`` 恒 0（执行层
            忽略），其余点 ``dt > 0``；至少 2 个点；首点 == ``start``、末点 == ``end``（取整后）。

        Raises:
            ValueError: 坐标非有限数值 / 非 (x, y)，或起终点距离 < 2px（属点击、不是滑动）。
        """
        sx, sy = self._as_xy(start, 'start')
        ex, ey = self._as_xy(end, 'end')

        dx, dy = ex - sx, ey - sy
        dist = math.hypot(dx, dy)
        if dist < 2.0:
            raise ValueError(f'起终点距离过小（{dist:.2f}px），不是滑动')

        p = self.params
        ux, uy = dx / dist, dy / dist          # 主方向单位向量
        perp_x, perp_y = -uy, ux                # 垂直单位向量（曲率方向）

        # ---- 采样点的参数 t 网格：主段等距 + 尾段（s >= tail_start_ratio）加密 ----
        n_intervals = int(round(dist / p.avg_step_px))
        n_intervals = max(n_intervals, p.min_points - 1)
        n_intervals = min(n_intervals, p.max_points - 1)
        n_intervals = min(n_intervals, max(1, int(dist)))

        t_tail = _t_for_s(p.tail_start_ratio)                   # s(t)=tail_start_ratio 对应的 t
        n_main = max(1, int(round(n_intervals * t_tail)))
        main_step_t = t_tail / n_main
        tail_step_t = main_step_t / p.tail_density_gain
        n_tail = max(2, int(round((1.0 - t_tail) / tail_step_t)))
        if n_main + n_tail + 1 > p.max_points:                  # 总点数封顶，等比缩减
            budget = p.max_points - 1
            n_main = max(1, int(round(budget * n_main / (n_main + n_tail))))
            n_tail = max(2, budget - n_main)

        ts = [main_step_t * i for i in range(n_main)]           # 0 .. <t_tail
        ts += [t_tail + (1.0 - t_tail) * j / n_tail for j in range(n_tail + 1)]  # t_tail .. 1.0

        # 单次曲率幅度：一次采样，可正可负；上限同时受绝对值与相对距离约束
        curve_cap = int(min(p.max_curve_px, dist * p.curve_px_ratio))
        curve_amp = self._rng.randint(-curve_cap, curve_cap) if curve_cap >= 1 else 0

        # 尾部微修正（默认关）：小概率、小幅度，末段 sin 回到 0 —— 不改终点、不反向、不改主方向
        tail_amp = 0
        if p.tail_correction_enable and p.tail_correction_max_px >= 1:
            if self._rng.randint(1, 100) <= p.tail_correction_pct:
                tail_amp = self._rng.randint(
                    -p.tail_correction_max_px, p.tail_correction_max_px)

        raw = []
        for t in ts:
            s = _minimum_jerk_s(t)
            along = s * dist
            lateral = curve_amp * math.sin(math.pi * t)
            if tail_amp and t >= _TAIL_CORRECTION_START:
                k = (t - _TAIL_CORRECTION_START) / (1.0 - _TAIL_CORRECTION_START)
                lateral += tail_amp * math.sin(math.pi * k)
            x = sx + ux * along + perp_x * lateral
            y = sy + uy * along + perp_y * lateral
            raw.append((x, y, t, s))

        # 起终点强制精确（消除浮点误差；理论上 s(0)=0 / s(1)=1、sin(0)=sin(pi)=0 已成立）
        raw[0] = (float(sx), float(sy), 0.0, 0.0)
        raw[-1] = (float(ex), float(ey), 1.0, 1.0)

        ex_i, ey_i = int(round(ex)), int(round(ey))
        out = []
        noise = 0.0                                             # dt 扰动的一阶低通状态
        for i, (x, y, t, s) in enumerate(raw):
            xi, yi = int(round(x)), int(round(y))
            if i == 0:
                out.append((xi, yi, 0))          # 落点，dt 恒 0（执行层忽略）
                continue
            if out and (xi, yi) == (out[-1][0], out[-1][1]):
                # 相邻整数点重合（短滑动 / 尾段密集时会出现）：直接丢弃，不折叠 dt。
                # 少数几段的合并对整体结构 / 「距离越长总时长越长」无影响，换来更简单可测。
                continue
            slow = 1.0 + p.end_slow_ratio * (1.0 - math.sin(math.pi * t))
            if s >= p.tail_start_ratio:                         # 尾段：额外平滑放慢
                k = (s - p.tail_start_ratio) / (1.0 - p.tail_start_ratio)
                slow += p.tail_slow_gain * _smoothstep(k)
            raw_noise = self._rng.randint(-p.dt_jitter_ms, p.dt_jitter_ms)
            noise = p.dt_smooth_alpha * noise + (1.0 - p.dt_smooth_alpha) * raw_noise
            dt = p.base_dt_ms * slow + noise
            dt = max(p.min_dt_ms, min(p.max_dt_ms, int(round(dt))))
            out.append((xi, yi, dt))

        # 保证最后一点精确落在 end（去重可能把被强制成 end 的末点也并掉）；用尾段放慢后的 dt
        if out[-1][0] != ex_i or out[-1][1] != ey_i:
            dt_end = max(p.min_dt_ms, min(p.max_dt_ms, int(round(
                p.base_dt_ms * (1.0 + p.end_slow_ratio + p.tail_slow_gain)))))
            out.append((ex_i, ey_i, dt_end))
        if len(out) < 2:
            # 理论上不会走到（dist >= 2 且 min_points >= 3），兜底保证结构合法
            out = [(int(round(sx)), int(round(sy)), 0), (ex_i, ey_i, int(round(p.base_dt_ms)))]
        return out

    @staticmethod
    def _as_xy(point, label):
        try:
            x, y = point
        except (TypeError, ValueError):
            raise ValueError(f'{label} 必须是 (x, y)：{point!r}')
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError(f'{label} 坐标不能是 bool：{point!r}')
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            raise ValueError(f'{label} 坐标必须是数值：{point!r}')
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f'{label} 坐标必须是有限数值：{point!r}')
        return x, y
