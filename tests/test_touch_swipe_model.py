# This Python file uses the following encoding: utf-8
"""TouchSwipeModel 单元测试（Plan B 的「怎么移动」纯逻辑层）。

第一阶段覆盖：起终点精确、点数合理、dt 全正、无 NaN/inf、纵向单调、±横向曲率、
曲率上限、无锯齿、minimum-jerk 前慢中快后慢、距离越长总时长越长、极短滑动仍有效、
非法输入抛 ValueError、确定性 RNG 可复现、默认随机源路径可用、可选尾部微修正。

第二阶段（时间连续性 + 尾段慢拖，任务规格「十九～二十二」）覆盖：
- 逐段 dt 扰动改为一阶低通（EMA）后相邻 dt 无无界跳变、扰动不长期漂移、趋势 > 噪声、
  固定 RNG 可复现、不同 RNG 仍有变化、慢→快→慢趋势仍成立；
- 尾段（按已走距离占比）MOVE 点更密、平均空间步长更小、平均 dt 更大、平均速度更小、
  终点精确不过冲不反向、无固定 pre-UP 停顿；
- 120 / 260 / 440px 总时长严格递增且不爆炸。

确定性优先：形状相关断言全部注入固定 RNG（FakeRng / SeqRng），只在「默认随机源路径」
一条用例里走真实 SystemRandom。
"""

import math
import unittest

from module.device.touch_swipe_model import (
    TouchSwipeModel,
    TouchSwipeParams,
    _DefaultRng,
    _minimum_jerk_s,
    _t_for_s,
)


class FakeRng:
    """确定性随机源：每次 randint 都返回被夹进 [min, max] 的固定值。"""

    def __init__(self, value: int):
        self.value = value
        self.calls = []

    def randint(self, min_value, max_value):
        self.calls.append((min_value, max_value))
        return max(min_value, min(max_value, self.value))


class SeqRng:
    """确定性随机源：按给定序列循环返回（夹进 [min, max]），用于测时间扰动的连续性。"""

    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def randint(self, min_value, max_value):
        v = self.seq[self.i % len(self.seq)]
        self.i += 1
        return max(min_value, min(max_value, v))


def _seg_steps(points):
    return [math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
            for i in range(1, len(points))]


def _move_segments(points):
    """executor 时间对齐的 MOVE→MOVE 段：段 p_i→p_{i+1}（i = 1..n-2）用 dt_i。

    dt_i（``points[i][2]``）是「到达 p_i 后、移动到 p_{i+1} 前的 WAIT」（D018）。
    排除 p0→p1（DOWN，无显式 dt）与 dt_{n-1}（pre-UP dwell，无下一段）。
    返回 [(spatial_step_px, dt_ms), ...]。
    """
    return [
        (math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]),
         points[i][2])
        for i in range(1, len(points) - 1)
    ]


def _split_mid_tail(points, *, tail_from=0.85, mid_lo=0.30, mid_hi=0.65):
    """按「已走距离占比」把 MOVE→MOVE 段分成中段 / 尾段，返回 (mid_segs, tail_segs)。

    每个 seg = (spatial_step_px, dt_ms)，dt 已按 executor 对齐（段 p_i→p_{i+1} 用 dt_i）。
    已走距离占比从 p0 起算（含被排除的 p0→p1 前导段），保证「尾段」判定准确。
    """
    segs = _move_segments(points)
    lead = math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1])  # p0→p1
    total = (lead + sum(st for st, _dt in segs)) or 1.0
    cum = lead
    mid, tail = [], []
    for st, dt in segs:
        cum += st
        frac = cum / total
        if frac >= tail_from:
            tail.append((st, dt))
        elif mid_lo <= frac <= mid_hi:
            mid.append((st, dt))
    return mid, tail


def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _perp_offsets(points, start, end):
    """每个点到 start->end 直线的带符号垂直距离。"""
    sx, sy = start
    ex, ey = end
    dist = math.hypot(ex - sx, ey - sy)
    ux, uy = (ex - sx) / dist, (ey - sy) / dist
    return [ (x - sx) * (-uy) + (y - sy) * ux for x, y, _ in points ]


def _segment_speeds(points):
    """executor 时间对齐的段速度：段 p_i→p_{i+1}（i = 1..n-2）速度 = 距离 / dt_i。

    dt_i 是「到达 p_i 后、移动到 p_{i+1} 前的 WAIT」；排除 p0→p1 与 dt_{n-1}。
    """
    return [st / dt for st, dt in _move_segments(points) if dt > 0]


class MoveSegmentAlignmentTest(unittest.TestCase):
    """锁死本文件测试 helper 的 executor 时间对齐（配合 dev tool 的 `trajectory_segments`）。

    executor：DOWN(p0) | MOVE(p1) WAIT(dt1) MOVE(p2) WAIT(dt2) ... MOVE(p_{n-1})
    WAIT(dt_{n-1}) | UP —— 段 p_i→p_{i+1} 的时间是 dt_i（i = 1..n-2）。
    """

    MANUAL = [(0, 0, 0), (20, 0, 5), (25, 0, 20), (35, 0, 10)]

    def test_move_segments_pair_step_with_dt_of_from_point(self):
        segs = _move_segments(self.MANUAL)
        self.assertEqual(segs, [(5.0, 5), (10.0, 20)])       # (p1→p2, dt1) / (p2→p3, dt2)

    def test_segment_speeds_match_manual_hand_calc(self):
        # p1→p2: 5px / 5ms = 1.0 ; p2→p3: 10px / 20ms = 0.5
        self.assertEqual(_segment_speeds(self.MANUAL), [1.0, 0.5])

    def test_p0_p1_and_last_dt_excluded(self):
        segs = _move_segments(self.MANUAL)
        self.assertNotIn(20.0, [st for st, _dt in segs])     # p0→p1 的 20px 位移不成段
        self.assertNotIn(10, [dt for _st, dt in segs])       # dt_last=10（pre-UP）不配给任何段
        self.assertEqual(len(segs), len(self.MANUAL) - 2)


class TouchSwipeModelBasicShapeTest(unittest.TestCase):
    START = (640, 600)
    END = (640, 200)          # 纵向向上 400px

    def _gen(self, start=None, end=None, rng_value=0, params=None):
        model = TouchSwipeModel(params=params, rng=FakeRng(rng_value))
        return model.generate(start or self.START, end or self.END)

    def test_starts_exactly_at_start(self):
        out = self._gen()
        self.assertEqual(out[0][:2], self.START)

    def test_ends_exactly_at_end(self):
        out = self._gen()
        self.assertEqual(out[-1][:2], self.END)

    def test_first_point_dt_is_zero_rest_positive(self):
        out = self._gen()
        self.assertEqual(out[0][2], 0)
        self.assertTrue(all(dt > 0 for _, _, dt in out[1:]))

    def test_reasonable_point_count(self):
        out = self._gen()
        # 400px / avg_step 16 ≈ 25 段；至少 min_points，且不超过 max_points
        self.assertGreaterEqual(len(out), 8)
        self.assertLessEqual(len(out), TouchSwipeParams().max_points)

    def test_no_nan_or_inf(self):
        out = self._gen(rng_value=7)
        for x, y, dt in out:
            for value in (x, y, dt):
                self.assertTrue(math.isfinite(value))
                self.assertIsInstance(value, int)

    def test_upward_swipe_y_monotonic_non_increasing(self):
        out = self._gen(self.START, (640, 200))
        ys = [y for _, y, _ in out]
        self.assertTrue(all(ys[i] <= ys[i - 1] for i in range(1, len(ys))))
        self.assertGreater(ys[0], ys[-1])

    def test_downward_swipe_y_monotonic_non_decreasing(self):
        out = self._gen((640, 200), (640, 600))
        ys = [y for _, y, _ in out]
        self.assertTrue(all(ys[i] >= ys[i - 1] for i in range(1, len(ys))))
        self.assertLess(ys[0], ys[-1])

    def test_supports_negative_lateral_curvature(self):
        # 纵向 swipe + 负曲率 -> x 向左鼓出，仍精确回到 end
        out = self._gen(rng_value=-14)
        xs = [x for x, _, _ in out]
        self.assertLess(min(xs), self.START[0] - 3)
        self.assertEqual(out[0][:2], self.START)
        self.assertEqual(out[-1][:2], self.END)

    def test_supports_positive_lateral_curvature(self):
        out = self._gen(rng_value=14)
        xs = [x for x, _, _ in out]
        self.assertGreater(max(xs), self.START[0] + 3)
        self.assertEqual(out[-1][:2], self.END)

    def test_lateral_offset_within_configured_cap(self):
        params = TouchSwipeParams()
        for rng_value in (-999, -3, 0, 5, 999):
            out = self._gen(rng_value=rng_value, params=params)
            offsets = _perp_offsets(out, self.START, self.END)
            self.assertLessEqual(max(abs(o) for o in offsets),
                                 params.max_curve_px + 1.5)

    def test_no_sawtooth_lateral_single_hump(self):
        # 纯曲率（无尾部修正）时，垂直偏移应是「单峰」：一次上升 + 一次下降，不来回跳
        out = self._gen(rng_value=999)
        offsets = _perp_offsets(out, self.START, self.END)
        sign_changes = 0
        prev = 0.0
        for i in range(1, len(offsets)):
            delta = offsets[i] - offsets[i - 1]
            if abs(delta) <= 1.0:            # 死区：忽略取整噪声
                continue
            sign = 1.0 if delta > 0 else -1.0
            if prev and sign != prev:
                sign_changes += 1
            prev = sign
        self.assertLessEqual(sign_changes, 1)

    def test_minimum_jerk_speed_structure_slow_fast_slow(self):
        out = self._gen(rng_value=0)               # 直线，便于比速度
        speeds = _segment_speeds(out)
        n = len(speeds)
        third = max(1, n // 3)
        first = sum(speeds[:third]) / third
        mid = sum(speeds[third:2 * third]) / third
        last = sum(speeds[2 * third:]) / (n - 2 * third)
        self.assertGreater(mid, first * 1.5)
        self.assertGreater(mid, last * 1.5)

    def test_longer_distance_takes_more_total_time(self):
        short = self._gen((0, 0), (0, -120), rng_value=0)
        long = self._gen((0, 0), (0, -600), rng_value=0)
        self.assertGreater(sum(dt for _, _, dt in long[1:]),
                           sum(dt for _, _, dt in short[1:]))

    def test_very_short_but_valid_swipe_still_produces_trajectory(self):
        out = self._gen((100, 300), (100, 286), rng_value=0)   # 14px
        self.assertGreaterEqual(len(out), 2)
        self.assertEqual(out[0][:2], (100, 300))
        self.assertEqual(out[-1][:2], (100, 286))
        self.assertTrue(all(dt > 0 for _, _, dt in out[1:]))

    def test_dt_never_exceeds_configured_bounds(self):
        params = TouchSwipeParams()
        out = self._gen(rng_value=999, params=params)
        for _, _, dt in out[1:]:
            self.assertGreaterEqual(dt, params.min_dt_ms)
            self.assertLessEqual(dt, params.max_dt_ms)


class TouchSwipeModelInvalidInputTest(unittest.TestCase):
    def test_zero_length_raises(self):
        with self.assertRaises(ValueError):
            TouchSwipeModel().generate((100, 100), (100, 100))

    def test_below_min_distance_raises(self):
        with self.assertRaises(ValueError):
            TouchSwipeModel().generate((100, 100), (100, 101))

    def test_non_finite_coordinate_raises(self):
        for bad_end in ((float('inf'), 0), (0, float('nan'))):
            with self.assertRaises(ValueError):
                TouchSwipeModel().generate((0, 0), bad_end)

    def test_non_numeric_point_raises(self):
        with self.assertRaises(ValueError):
            TouchSwipeModel().generate('bad', (10, 10))
        with self.assertRaises(ValueError):
            TouchSwipeModel().generate((0, 0, 0), (10, 10))

    def test_bool_coordinate_rejected(self):
        with self.assertRaises(ValueError):
            TouchSwipeModel().generate((0, True), (10, 10))

    def test_invalid_params_rejected(self):
        for kwargs in (dict(min_points=2), dict(min_points=10, max_points=5),
                       dict(avg_step_px=0), dict(min_dt_ms=0),
                       dict(min_dt_ms=20, max_dt_ms=10), dict(dt_jitter_ms=-1),
                       # 第二阶段新增参数的非法组合
                       dict(dt_smooth_alpha=1.0), dict(dt_smooth_alpha=-0.1),
                       dict(tail_start_ratio=0.4), dict(tail_start_ratio=1.0),
                       dict(tail_density_gain=0.9), dict(tail_density_gain=5.0),
                       dict(tail_slow_gain=-0.1), dict(tail_slow_gain=3.5)):
            with self.assertRaises(ValueError):
                TouchSwipeParams(**kwargs)

    def test_new_params_have_sane_defaults(self):
        p = TouchSwipeParams()
        self.assertEqual(p.dt_smooth_alpha, 0.72)
        self.assertEqual(p.tail_start_ratio, 0.85)
        self.assertGreater(p.tail_density_gain, 1.0)
        self.assertGreater(p.tail_slow_gain, 0.0)
        # 曲率参数本轮不动
        self.assertEqual(p.max_curve_px, 16.0)
        self.assertEqual(p.curve_px_ratio, 0.12)


class TouchSwipeModelRngTest(unittest.TestCase):
    def test_injected_deterministic_rng_is_reproducible(self):
        a = TouchSwipeModel(rng=FakeRng(3)).generate((100, 600), (100, 200))
        b = TouchSwipeModel(rng=FakeRng(3)).generate((100, 600), (100, 200))
        self.assertEqual(a, b)

    def test_different_rng_value_changes_shape(self):
        a = TouchSwipeModel(rng=FakeRng(-15)).generate((640, 600), (640, 200))
        b = TouchSwipeModel(rng=FakeRng(15)).generate((640, 600), (640, 200))
        self.assertNotEqual(a, b)
        # 但起终点都必须精确
        self.assertEqual(a[0][:2], b[0][:2])
        self.assertEqual(a[-1][:2], b[-1][:2])

    def test_default_rng_path_produces_valid_trajectory(self):
        model = TouchSwipeModel()                 # 走真实公共 SystemRandom
        for _ in range(10):
            out = model.generate((100, 620), (100, 210))
            self.assertGreaterEqual(len(out), 8)
            self.assertEqual(out[0][:2], (100, 620))
            self.assertEqual(out[-1][:2], (100, 210))
            self.assertEqual(out[0][2], 0)
            self.assertTrue(all(dt > 0 for _, _, dt in out[1:]))
            ys = [y for _, y, _ in out]
            self.assertTrue(all(ys[i] <= ys[i - 1] for i in range(1, len(ys))))

    def test_default_rng_adapter_delegates_to_public_helper(self):
        seen = []
        import module.device.touch_swipe_model as mod
        original = mod.random_int

        def spy(a, b):
            seen.append((a, b))
            return original(a, b)

        mod.random_int = spy
        try:
            self.assertIn(_DefaultRng().randint(3, 9), range(3, 10))
        finally:
            mod.random_int = original
        self.assertEqual(seen, [(3, 9)])


class TouchSwipeModelTailCorrectionTest(unittest.TestCase):
    START = (640, 600)
    END = (640, 200)

    def _gen(self, params, rng_value):
        return TouchSwipeModel(params=params, rng=FakeRng(rng_value)).generate(
            self.START, self.END)

    def test_disabled_by_default(self):
        self.assertFalse(TouchSwipeParams().tail_correction_enable)

    def test_correction_disabled_matches_plain_curve(self):
        off = self._gen(TouchSwipeParams(), rng_value=4)
        # 打开 enable 但概率设 0 -> 依然不触发 -> 轨迹与关闭时一致
        never = self._gen(
            TouchSwipeParams(tail_correction_enable=True, tail_correction_pct=0),
            rng_value=4)
        self.assertEqual(off, never)

    def test_correction_forced_changes_only_tail_not_endpoint(self):
        base = TouchSwipeParams()
        forced = TouchSwipeParams(tail_correction_enable=True,
                                  tail_correction_pct=100,
                                  tail_correction_max_px=3)
        off = self._gen(base, rng_value=2)
        on = self._gen(forced, rng_value=2)
        self.assertNotEqual(off, on)
        # 终点不变
        self.assertEqual(on[-1][:2], self.END)
        # 差异集中在末段（correction 只作用于 t >= _TAIL_CORRECTION_START）：
        # 前 60% 的点逐字一致（尾段加密可能让 off/on 长度差 1，只比公共前缀）
        common = min(len(off), len(on))
        first_diff = next((i for i in range(common) if off[i][:2] != on[i][:2]), common)
        self.assertGreater(first_diff, len(off) * 0.6)

    def test_forced_correction_amplitude_is_bounded(self):
        forced = TouchSwipeParams(tail_correction_enable=True,
                                  tail_correction_pct=100,
                                  tail_correction_max_px=3,
                                  max_curve_px=16.0)
        out = self._gen(forced, rng_value=999)
        offsets = _perp_offsets(out, self.START, self.END)
        self.assertLessEqual(max(abs(o) for o in offsets),
                             forced.max_curve_px + forced.tail_correction_max_px + 1.5)


# ======================================================================================
# 第二阶段：时间连续性（平滑 dt 扰动）—— 任务规格「十九」
# ======================================================================================

class SmoothDtNoiseTest(unittest.TestCase):
    START = (520, 460)
    END = (520, 200)            # 纵向向上 260px

    def _dts(self, rng, start=None, end=None, params=None):
        traj = TouchSwipeModel(params=params, rng=rng).generate(
            start or self.START, end or self.END)
        return [traj[i][2] for i in range(1, len(traj))], traj

    def test_helpers_solve_minimum_jerk(self):
        for s in (0.1, 0.5, 0.85, 0.97):
            self.assertAlmostEqual(_minimum_jerk_s(_t_for_s(s)), s, places=4)
        self.assertEqual(_t_for_s(0.0), 0.0)
        self.assertEqual(_t_for_s(1.0), 1.0)

    def test_default_alpha_is_a_lowpass_not_zero(self):
        self.assertGreater(TouchSwipeParams().dt_smooth_alpha, 0.0)
        self.assertLess(TouchSwipeParams().dt_smooth_alpha, 1.0)

    def test_adjacent_dt_has_no_unbounded_jump(self):
        # 交替极值输入：不平滑时相邻 raw 会一次摆动 2*jitter=6ms。
        # 经一阶低通后，非尾段（趋势平坦）相邻 dt 变化必须远小于此。
        dts, traj = self._dts(SeqRng([3, -3] * 60))
        mid, _tail = _split_mid_tail(traj)
        # 取中段对应的 dt 索引范围粗略用 [第 30%, 第 65%] 点
        n = len(dts)
        lo, hi = int(n * 0.30), int(n * 0.62)
        mid_dts = dts[lo:hi]
        jumps = [abs(mid_dts[i] - mid_dts[i - 1]) for i in range(1, len(mid_dts))]
        self.assertLessEqual(max(jumps), 3)          # 远小于未平滑的 6

    def test_smooth_noise_does_not_drift(self):
        # 恒定偏置输入：低通输出收敛到该偏置并保持，不会持续累积 / 发散
        params = TouchSwipeParams()
        biased, _ = self._dts(SeqRng([3] * 200), params=params)
        zero, _ = self._dts(FakeRng(0), params=params)
        m = min(len(biased), len(zero))
        # 每一段的偏置量都被夹在 [-jitter, jitter] 内，不随长度增长
        deltas = [biased[i] - zero[i] for i in range(m)]
        self.assertLessEqual(max(deltas), params.dt_jitter_ms + 1)
        self.assertGreaterEqual(min(deltas), -1)
        # 中段（趋势平坦）偏置基本恒定，不是逐点递增
        lo, hi = int(m * 0.30), int(m * 0.62)
        seg = deltas[lo:hi]
        self.assertLessEqual(max(seg) - min(seg), 2)

    def test_same_seq_rng_is_reproducible(self):
        seq = [2, -1, 3, 0, -2, 1, 3, -3]
        a, _ = self._dts(SeqRng(seq))
        b, _ = self._dts(SeqRng(seq))
        self.assertEqual(a, b)

    def test_different_seq_rng_changes_dt_but_not_endpoints(self):
        a_dt, a = self._dts(SeqRng([3, 2, 3, 2]))
        b_dt, b = self._dts(SeqRng([-3, -2, -3, -2]))
        self.assertNotEqual(a_dt, b_dt)
        self.assertEqual(a[0][:2], b[0][:2])
        self.assertEqual(a[-1][:2], b[-1][:2])

    def test_trend_still_slow_fast_slow_even_with_noise(self):
        _dts, traj = self._dts(SeqRng([3, -3] * 60))
        speeds = _segment_speeds(traj)
        n = len(speeds)
        third = max(1, n // 3)
        first = sum(speeds[:third]) / third
        mid = sum(speeds[third:2 * third]) / third
        last = sum(speeds[2 * third:]) / (n - 2 * third)
        self.assertGreater(mid, first)
        self.assertGreater(mid, last)

    def test_noise_does_not_dominate_trend(self):
        # 中段 dt 的波动幅度必须明显小于「尾段趋势抬升」
        _dts, traj = self._dts(SeqRng([3, -3] * 60), end=(520, 40))   # 420px
        mid, tail = _split_mid_tail(traj)
        mid_dts = [d for _s, d in mid]
        tail_dts = [d for _s, d in tail]
        mid_spread = max(mid_dts) - min(mid_dts)
        trend_rise = _avg(tail_dts) - _avg(mid_dts)
        self.assertGreater(trend_rise, mid_spread)


# ======================================================================================
# 第二阶段：尾段慢拖 —— 任务规格「二十 / 二十一」
# ======================================================================================

class TailDragSpaceTest(unittest.TestCase):
    def _traj(self, start, end, rng_value=0, params=None):
        return TouchSwipeModel(params=params, rng=FakeRng(rng_value)).generate(start, end)

    def _cases(self):
        # (start, end, label)：纵向上 / 纵向下，260 / 440px
        return [
            ((520, 460), (520, 200), 'up-260'),
            ((520, 200), (520, 460), 'down-260'),
            ((520, 620), (520, 180), 'up-440'),
            ((520, 180), (520, 620), 'down-440'),
        ]

    def test_tail_has_multiple_move_points(self):
        for s, e, label in self._cases():
            with self.subTest(label=label):
                traj = self._traj(s, e)
                _mid, tail = _split_mid_tail(traj)
                self.assertGreaterEqual(len(tail), 3)

    def test_tail_spatial_step_finer_than_mid(self):
        for s, e, label in self._cases():
            with self.subTest(label=label):
                traj = self._traj(s, e)
                mid, tail = _split_mid_tail(traj)
                self.assertLess(_avg([st for st, _d in tail]),
                                _avg([st for st, _d in mid]))

    def test_no_run_of_duplicate_coords(self):
        for s, e, label in self._cases():
            with self.subTest(label=label):
                traj = self._traj(s, e)
                dup_pairs = sum(1 for i in range(1, len(traj))
                                if traj[i][:2] == traj[i - 1][:2])
                self.assertLessEqual(dup_pairs, 1)

    def test_end_exact_no_overshoot_no_reverse(self):
        for s, e, label in self._cases():
            with self.subTest(label=label):
                traj = self._traj(s, e)
                self.assertEqual(traj[0][:2], s)
                self.assertEqual(traj[-1][:2], e)
                ys = [p[1] for p in traj]
                if e[1] < s[1]:                              # 向上：y 单调不增，且不低于 end
                    self.assertTrue(all(ys[i] <= ys[i - 1] for i in range(1, len(ys))))
                    self.assertGreaterEqual(min(ys), e[1])
                else:                                        # 向下：y 单调不减，且不超过 end
                    self.assertTrue(all(ys[i] >= ys[i - 1] for i in range(1, len(ys))))
                    self.assertLessEqual(max(ys), e[1])

    def test_no_fixed_pre_up_pause_in_source(self):
        # 尾段慢拖靠结构表达，不复制 drag 的 wait(140)×2 / 不加 UP 前固定停顿
        import inspect

        import module.device.touch_swipe_model as mod
        src = inspect.getsource(mod)
        self.assertNotIn('140', src)
        self.assertNotIn('pre_up', src.lower())


class TailDragTimeTest(unittest.TestCase):
    def _traj(self, start, end, rng_value=0):
        return TouchSwipeModel(rng=FakeRng(rng_value)).generate(start, end)

    def test_tail_avg_dt_greater_than_mid_avg_dt(self):
        for s, e in (((520, 460), (520, 200)), ((520, 620), (520, 180))):
            with self.subTest(dist=abs(e[1] - s[1])):
                mid, tail = _split_mid_tail(self._traj(s, e))
                self.assertGreater(_avg([d for _st, d in tail]),
                                   _avg([d for _st, d in mid]))

    def test_tail_avg_speed_less_than_mid_avg_speed(self):
        for s, e in (((520, 460), (520, 200)), ((520, 620), (520, 180))):
            with self.subTest(dist=abs(e[1] - s[1])):
                mid, tail = _split_mid_tail(self._traj(s, e))
                mid_spd = _avg([st for st, _d in mid]) / _avg([d for _st, d in mid])
                tail_spd = _avg([st for st, _d in tail]) / _avg([d for _st, d in tail])
                self.assertLess(tail_spd, mid_spd)

    def test_tail_dt_ramp_is_gradual_not_a_jump(self):
        # 进入尾段的 dt 不能从中段值突跳一大截（smoothstep 平滑起步）
        traj = self._traj((520, 620), (520, 180))
        dts = [traj[i][2] for i in range(1, len(traj))]
        jumps = [abs(dts[i] - dts[i - 1]) for i in range(1, len(dts))]
        self.assertLessEqual(max(jumps), 4)      # 无 8ms→25ms 之类的跳变

    def test_last_segment_is_in_slow_region(self):
        traj = self._traj((520, 620), (520, 180))
        dts = [traj[i][2] for i in range(1, len(traj))]
        mid, _tail = _split_mid_tail(traj)
        self.assertGreater(dts[-1], _avg([d for _st, d in mid]))


class TotalDurationTest(unittest.TestCase):
    def _total(self, dist):
        traj = TouchSwipeModel(rng=FakeRng(0)).generate((520, 100 + dist), (520, 100))
        return sum(dt for _x, _y, dt in traj)

    def test_short_lt_medium_lt_long(self):
        t120, t260, t440 = self._total(120), self._total(260), self._total(440)
        self.assertLess(t120, t260)
        self.assertLess(t260, t440)

    def test_totals_within_sane_upper_bound(self):
        # 尾段参数错误会让总时长爆炸；这里按当前模型量级设宽松上限（非真机数据）
        self.assertLess(self._total(120), 200)
        self.assertLess(self._total(260), 360)
        self.assertLess(self._total(440), 600)

    def test_totals_meaningfully_above_zero(self):
        self.assertGreater(self._total(120), 60)


if __name__ == '__main__':
    unittest.main()
