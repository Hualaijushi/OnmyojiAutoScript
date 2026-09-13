"""`module/base/frame_wait.py` 的纯单元测试。

全部用 numpy 人工构造帧 + 注入的假 clock / 假 provider，不启动 Device / 不真实 sleep。
锁住：成功语义（必须 changed 且 stable）、两种超时（从未变化 / 变化但未稳定）、
changed 锁存、stable_count 重置、provider 异常向上传播、校验分工、frames_checked。
"""

import itertools
import unittest

import numpy as np

from module.base import frame_wait
from module.base.frame_wait import wait_for_changed_and_stable


def _blank(value=0, h=20, w=30, channels=3):
    shape = (h, w, channels) if channels else (h, w)
    return np.full(shape, value, dtype=np.uint8)


def _clock(step=0.1, start=0.0):
    """确定性单调 clock：每次调用 +step。"""
    counter = itertools.count(start, step)
    return lambda: next(counter)


def _provider(frames):
    """依次返回给定帧；耗尽后 StopIteration（测试应保证在此之前已成功 / 超时）。"""
    it = iter(frames)
    return lambda: next(it)


A = _blank(0)
B = _blank(255)
C = _blank(128)
D = _blank(64)
E = _blank(200)


class WaitForChangedAndStableTest(unittest.TestCase):
    def _wait(self, baseline, frames, *, changed_threshold=0.5, stable_threshold=0.01,
              stable_frames=2, timeout=5.0, clock=None, provider=None, **kw):
        return wait_for_changed_and_stable(
            baseline,
            provider or _provider(frames),
            changed_threshold=changed_threshold,
            stable_threshold=stable_threshold,
            stable_frames=stable_frames,
            timeout=timeout,
            clock=clock or _clock(),
            **kw,
        )

    # Case 1：变化后稳定 -> 成功
    def test_change_then_stable_succeeds(self):
        r = self._wait(A, [B, C, C, C], stable_frames=2)
        self.assertTrue(r.changed)
        self.assertTrue(r.stable)
        self.assertFalse(r.timed_out)
        self.assertTrue(r.success)
        self.assertEqual(r.stable_count, 2)
        self.assertEqual(r.frames_checked, 4)
        self.assertEqual(r.last_difference, 1.0)

    # Case 2：从未变化 -> 超时，changed=False（即使 detector 内部 stable 可能为 True）
    def test_never_changed_times_out(self):
        clock = _clock(step=0.1)  # start 0.0，每轮 +0.1
        r = wait_for_changed_and_stable(
            A, lambda: A,  # 永远返回 baseline
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=1.0, clock=clock,
        )
        self.assertFalse(r.changed)
        self.assertTrue(r.timed_out)
        self.assertFalse(r.success)
        # 画面一直静止：detector 的 stable 会是 True，但 wait 仍判为未成功
        self.assertTrue(r.stable)
        self.assertGreaterEqual(r.frames_checked, 1)
        self.assertGreaterEqual(r.elapsed, 1.0)

    # Case 3：持续变化 -> 超时，changed=True 且 stable=False
    def test_changed_but_never_stable_times_out(self):
        clock = _clock(step=0.1)
        vals = itertools.cycle([B, C, D, E])
        r = wait_for_changed_and_stable(
            A, lambda: next(vals),
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=3,
            timeout=1.0, clock=clock,
        )
        self.assertTrue(r.changed)
        self.assertFalse(r.stable)
        self.assertTrue(r.timed_out)
        self.assertFalse(r.success)
        self.assertEqual(r.stable_count, 0)

    # Case 4：变化后回到 baseline -> changed 锁存，随后 stable -> 成功
    def test_change_then_return_to_baseline_still_succeeds(self):
        r = self._wait(A, [B, A, A, A], stable_frames=2)
        self.assertTrue(r.changed)          # 锁存，不因 difference 归零而回退
        self.assertTrue(r.stable)
        self.assertFalse(r.timed_out)
        self.assertTrue(r.success)
        self.assertEqual(r.last_difference, 0.0)  # 最后一帧相对 baseline 已无差异

    # Case 5：stable_count 被中途变化重置后重新累计 -> 最终成功
    def test_stable_count_resets_then_reaccumulates(self):
        # A -> B(变) -> C(变) -> C(静1) -> D(变, 归零) -> D(静1) -> D(静2) => stable_frames=2 成功
        r = self._wait(A, [B, C, C, D, D, D], stable_frames=2)
        self.assertTrue(r.success)
        self.assertEqual(r.frames_checked, 6)
        self.assertEqual(r.stable_count, 2)

    # Case 6：timeout 边界确定性（无真实 sleep）
    def test_timeout_boundary_deterministic(self):
        # clock 调用序列：start=0.0 -> loop1 elapsed=0.5(<1.0, 轮询 1 帧) -> loop2 elapsed=1.0(>=1.0, 超时)
        clock = _clock(step=0.5)
        r = wait_for_changed_and_stable(
            A, lambda: A,
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=1.0, clock=clock,
        )
        self.assertTrue(r.timed_out)
        self.assertEqual(r.elapsed, 1.0)
        self.assertEqual(r.frames_checked, 1)  # 超时前只轮询了 1 帧

    # Case 7：provider 第 N 次抛异常 -> 原样向上传播，不伪装成 timeout
    def test_provider_exception_propagates(self):
        calls = {"n": 0}

        def provider():
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("device gone")
            return B

        with self.assertRaises(RuntimeError):
            wait_for_changed_and_stable(
                A, provider,
                changed_threshold=0.5, stable_threshold=0.01, stable_frames=5,
                timeout=10.0, clock=_clock(),
            )

    # Case 8：校验分工 —— timeout / poll_interval 由本层校验
    def test_wait_layer_rejects_bad_timeout(self):
        for bad in [0, -1, -0.5, "x", None, True, False]:
            with self.assertRaises(ValueError):
                wait_for_changed_and_stable(
                    A, lambda: A, changed_threshold=0.5, stable_threshold=0.01,
                    stable_frames=2, timeout=bad, clock=_clock(),
                )

    def test_wait_layer_rejects_negative_poll_interval(self):
        with self.assertRaises(ValueError):
            wait_for_changed_and_stable(
                A, lambda: A, changed_threshold=0.5, stable_threshold=0.01,
                stable_frames=2, timeout=1.0, poll_interval=-0.1, clock=_clock(),
            )

    # 校验分工 —— 阈值 / stable_frames / baseline / frame shape 由 FrameStateDetector 抛
    def test_detector_rejects_bad_thresholds_and_frames(self):
        for kw in [{"changed_threshold": -0.1}, {"stable_threshold": -0.1}, {"stable_frames": 0}]:
            params = dict(changed_threshold=0.5, stable_threshold=0.01, stable_frames=2)
            params.update(kw)
            with self.assertRaises(ValueError):
                wait_for_changed_and_stable(
                    A, lambda: A, timeout=1.0, clock=_clock(), **params,
                )

    def test_baseline_none_raises(self):
        with self.assertRaises(ValueError):
            wait_for_changed_and_stable(
                None, lambda: A, changed_threshold=0.5, stable_threshold=0.01,
                stable_frames=2, timeout=1.0, clock=_clock(),
            )

    def test_frame_shape_mismatch_propagates(self):
        wrong = _blank(255, h=20, w=31)  # 与 baseline A(20x30) 不同
        with self.assertRaises(ValueError):
            wait_for_changed_and_stable(
                A, _provider([wrong]),
                changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
                timeout=5.0, clock=_clock(),
            )

    def test_baseline_shape_vs_roi_validated_eagerly(self):
        # 非法 ROI 在 reset(baseline) 阶段就抛，而不是等到轮询
        with self.assertRaises(ValueError):
            wait_for_changed_and_stable(
                A, lambda: A, changed_threshold=0.5, stable_threshold=0.01,
                stable_frames=2, timeout=1.0, roi=(10, 10, 5, 20), clock=_clock(),
            )

    # Case 9：frames_checked 语义 —— 不含 baseline
    def test_frames_checked_excludes_baseline(self):
        # A(baseline) -> B(变, 相邻差大 count=0) -> B(静 count=1) -> B(静 count=2) => 成功
        r = self._wait(A, [B, B, B], stable_frames=2)
        self.assertTrue(r.success)
        self.assertEqual(r.frames_checked, 3)

    # Case 10：poll_interval 时用注入 sleeper，且默认 0 不 sleep
    def test_poll_interval_uses_injected_sleeper(self):
        slept = []
        clock = _clock(step=0.1)
        wait_for_changed_and_stable(
            A, lambda: A,
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=0.35, poll_interval=0.05, clock=clock,
            sleeper=lambda s: slept.append(s),
        )
        self.assertTrue(slept)
        self.assertTrue(all(s == 0.05 for s in slept))

    def test_default_poll_interval_does_not_sleep(self):
        slept = []
        wait_for_changed_and_stable(
            A, lambda: A,
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=0.35, clock=_clock(step=0.1),
            sleeper=lambda s: slept.append(s),
        )
        self.assertEqual(slept, [])

    # 成功语义：stable 单独为 True 不算成功
    def test_stable_without_changed_is_not_success(self):
        r = wait_for_changed_and_stable(
            A, lambda: A,
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=1.0, clock=_clock(step=0.1),
        )
        self.assertTrue(r.stable)
        self.assertFalse(r.changed)
        self.assertFalse(r.success)
        self.assertTrue(r.timed_out)

    # _MAX_POLLS 兜底：注入不推进的 clock -> RuntimeError 而不是死循环
    def test_non_advancing_clock_hits_poll_cap(self):
        orig = frame_wait._MAX_POLLS
        frame_wait._MAX_POLLS = 50
        try:
            with self.assertRaises(RuntimeError):
                wait_for_changed_and_stable(
                    A, lambda: A,
                    changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
                    timeout=1.0, clock=lambda: 0.0,  # 永远 0
                )
        finally:
            frame_wait._MAX_POLLS = orig

    # ROI：只看 ROI 内变化
    def test_roi_scopes_the_wait(self):
        base = _blank(0, h=40, w=60)
        inside = base.copy(); inside[0:10, 0:10] = 255
        outside = base.copy(); outside[30:40, 50:60] = 255
        # ROI 内变化后静止 -> 成功
        r_in = wait_for_changed_and_stable(
            base, _provider([inside, inside, inside]),
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=5.0, roi=(0, 0, 10, 10), clock=_clock(),
        )
        self.assertTrue(r_in.success)
        # 只有 ROI 外变化 -> changed 永远 False -> 超时
        clock = _clock(step=0.2)
        r_out = wait_for_changed_and_stable(
            base, lambda: outside,
            changed_threshold=0.5, stable_threshold=0.01, stable_frames=2,
            timeout=1.0, roi=(0, 0, 10, 10), clock=clock,
        )
        self.assertFalse(r_out.changed)
        self.assertTrue(r_out.timed_out)
        self.assertEqual(r_out.last_difference, 0.0)

    def test_result_is_frozen_dataclass(self):
        r = self._wait(A, [B, C, C, C])
        with self.assertRaises(Exception):
            r.changed = False  # frozen


if __name__ == "__main__":
    unittest.main()
