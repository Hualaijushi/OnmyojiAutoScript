"""`module/atom/frame_state.py` 的纯单元测试。

全部用 numpy 人工构造帧，不使用任何真实游戏截图；不锁定任何真机阈值——
每个用例自己显式传入 changed_threshold / stable_threshold / stable_frames。
"""

import unittest

import numpy as np

from module.atom.frame_state import (
    DEFAULT_PIXEL_THRESHOLD,
    FrameStateDetector,
    FrameStateResult,
    frame_difference,
)


def _blank(h=40, w=60, value=0, channels=3):
    shape = (h, w, channels) if channels else (h, w)
    return np.full(shape, value, dtype=np.uint8)


class FrameDifferenceTest(unittest.TestCase):
    # 1. 完全相同
    def test_identical_frames_have_zero_difference(self):
        a = _blank(value=100)
        self.assertEqual(frame_difference(a, a.copy()), 0.0)

    # 2. 全图明显变化
    def test_full_frame_change_difference_is_one(self):
        a = _blank(value=0)
        b = _blank(value=255)
        self.assertEqual(frame_difference(a, b), 1.0)

    # 3 + 4. ROI 内变化被计入，ROI 外变化不被计入
    def test_roi_isolates_changed_region(self):
        a = _blank(h=40, w=60, value=0)
        b = a.copy()
        # 只改左上角 10x10 区域
        b[0:10, 0:10] = 255
        roi_inside = (0, 0, 10, 10)
        roi_outside = (30, 20, 60, 40)
        self.assertEqual(frame_difference(a, b, roi=roi_inside), 1.0)
        self.assertEqual(frame_difference(a, b, roi=roi_outside), 0.0)
        # 全图口径下只有一小块变化，占比很小
        self.assertAlmostEqual(frame_difference(a, b), 100 / (40 * 60))

    # 5. 小面积噪声低于阈值
    def test_small_noise_is_below_change_threshold(self):
        a = _blank(h=40, w=60, value=0)
        b = a.copy()
        b[5, 5] = 255
        b[20, 33] = 255
        b[39, 59] = 255
        score = frame_difference(a, b)
        self.assertGreater(score, 0.0)
        self.assertEqual(score, 3 / (40 * 60))
        self.assertLess(score, 0.05)

    # 14. score 恒在 [0, 1]
    def test_difference_score_always_in_unit_range(self):
        rng = np.random.default_rng(0)
        for _ in range(20):
            a = rng.integers(0, 256, size=(30, 45, 3), dtype=np.uint8)
            b = rng.integers(0, 256, size=(30, 45, 3), dtype=np.uint8)
            for roi in (None, (0, 0, 45, 30), (5, 5, 20, 20)):
                score = frame_difference(a, b, roi=roi)
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)

    def test_pixel_threshold_controls_sensitivity(self):
        a = _blank(value=100)
        b = _blank(value=110)  # 每像素差 10
        self.assertEqual(frame_difference(a, b, pixel_threshold=5), 1.0)
        self.assertEqual(frame_difference(a, b, pixel_threshold=20), 0.0)

    def test_grayscale_frames_supported(self):
        a = _blank(channels=0, value=0)
        b = _blank(channels=0, value=255)
        self.assertEqual(frame_difference(a, b), 1.0)
        self.assertEqual(frame_difference(a, a.copy()), 0.0)

    # 12. shape mismatch
    def test_shape_mismatch_raises(self):
        with self.assertRaises(ValueError):
            frame_difference(_blank(h=40, w=60), _blank(h=40, w=61))
        with self.assertRaises(ValueError):
            frame_difference(_blank(channels=3), _blank(channels=0))

    def test_none_frame_raises(self):
        with self.assertRaises(ValueError):
            frame_difference(None, _blank())
        with self.assertRaises(ValueError):
            frame_difference(_blank(), None)

    def test_non_ndarray_raises(self):
        with self.assertRaises(ValueError):
            frame_difference([[0, 0], [0, 0]], _blank())

    # 13. 非法 ROI
    def test_illegal_roi_raises(self):
        a = _blank(h=40, w=60)
        for bad in [(10, 10, 10, 20), (10, 10, 20, 10), (20, 5, 10, 25)]:
            with self.assertRaises(ValueError):
                frame_difference(a, a.copy(), roi=bad)
        # 完全越界
        with self.assertRaises(ValueError):
            frame_difference(a, a.copy(), roi=(100, 100, 200, 200))
        with self.assertRaises(ValueError):
            frame_difference(a, a.copy(), roi=(-50, 10, -10, 20))
        # 三元组
        with self.assertRaises(ValueError):
            frame_difference(a, a.copy(), roi=(0, 0, 10))

    def test_partially_out_of_bounds_roi_is_clamped(self):
        a = _blank(h=40, w=60, value=0)
        b = a.copy()
        b[30:40, 50:60] = 255  # 右下 10x10
        # ROI 超出右下边界，clamp 后应正好覆盖那块变化
        self.assertEqual(frame_difference(a, b, roi=(50, 30, 999, 999)), 1.0)


class FrameStateDetectorTest(unittest.TestCase):
    def _detector(self, changed_threshold=0.10, stable_threshold=0.02,
                  stable_frames=3, roi=None):
        return FrameStateDetector(
            changed_threshold=changed_threshold,
            stable_threshold=stable_threshold,
            stable_frames=stable_frames,
            roi=roi,
        )

    # 6. 一直静止：changed=False，stable=True
    def test_always_static_becomes_stable_never_changed(self):
        d = self._detector(stable_frames=3)
        a = _blank(value=100)
        d.reset(a)
        r1 = d.update(a.copy())
        r2 = d.update(a.copy())
        r3 = d.update(a.copy())
        self.assertEqual([r1.stable_count, r2.stable_count, r3.stable_count], [1, 2, 3])
        self.assertFalse(r3.changed)
        self.assertTrue(r3.stable)
        self.assertFalse(r1.stable)

    # 7. 变化后稳定：changed=True，stable=True
    def test_change_then_settle(self):
        d = self._detector(stable_frames=2)
        a = _blank(value=0)
        b = _blank(value=255)
        c = _blank(value=128)
        d.reset(a)
        d.update(b)              # A->B 大变化
        r_c1 = d.update(c)       # B->C 大变化，stable_count 归零
        r_c2 = d.update(c.copy())  # C->C 安静 1
        r_c3 = d.update(c.copy())  # C->C 安静 2 -> stable
        self.assertTrue(r_c1.changed)
        self.assertEqual(r_c1.stable_count, 0)
        self.assertEqual([r_c2.stable_count, r_c3.stable_count], [1, 2])
        self.assertTrue(r_c3.changed)
        self.assertTrue(r_c3.stable)

    # 8. 持续变化：changed=True，stable=False
    def test_continuous_change_never_stable(self):
        d = self._detector(stable_frames=3)
        d.reset(_blank(value=0))
        results = [d.update(_blank(value=v)) for v in (60, 120, 180, 240)]
        self.assertTrue(results[-1].changed)
        self.assertFalse(any(r.stable for r in results))
        self.assertTrue(all(r.stable_count == 0 for r in results))

    # 9. stable_count 在中途明显变化时重置
    def test_stable_count_resets_on_mid_change(self):
        d = self._detector(stable_frames=3)
        b = _blank(value=100)
        c = _blank(value=220)
        d.reset(_blank(value=0))
        d.update(b)                       # A->B 变化, count 0
        r_bb = d.update(b.copy())         # B->B 安静, count 1
        r_c = d.update(c)                 # B->C 明显变化, count 归零
        r_cc1 = d.update(c.copy())        # C->C 安静, count 1
        r_cc2 = d.update(c.copy())        # count 2
        self.assertEqual(r_bb.stable_count, 1)
        self.assertEqual(r_c.stable_count, 0)
        self.assertEqual([r_cc1.stable_count, r_cc2.stable_count], [1, 2])

    # 10. 变化后回到 baseline：changed 不回退，stable 仍可成立
    def test_change_then_return_to_baseline(self):
        d = self._detector(stable_frames=2)
        a = _blank(value=0)
        b = _blank(value=255)
        d.reset(a)
        r_b = d.update(b)          # A->B 变化 -> changed
        r_a1 = d.update(a.copy())  # B->A 变化, count 0, changed 仍 True
        r_a2 = d.update(a.copy())  # A->A 安静, count 1
        r_a3 = d.update(a.copy())  # count 2 -> stable
        self.assertTrue(r_b.changed)
        self.assertAlmostEqual(r_a1.difference, 0.0)  # 相对 baseline 已回到 0
        self.assertTrue(r_a1.changed)                 # 但 changed 不回退
        self.assertTrue(r_a3.changed)
        self.assertTrue(r_a3.stable)

    # 3 + 4 在 detector 层：ROI 外变化不触发 changed
    def test_detector_roi_ignores_outside_changes(self):
        roi = (0, 0, 10, 10)
        d_in = self._detector(changed_threshold=0.5, stable_frames=2, roi=roi)
        d_out = self._detector(changed_threshold=0.5, stable_frames=2, roi=roi)
        a = _blank(h=40, w=60, value=0)
        inside_change = a.copy()
        inside_change[0:10, 0:10] = 255
        outside_change = a.copy()
        outside_change[30:40, 50:60] = 255

        d_in.reset(a)
        self.assertTrue(d_in.update(inside_change).changed)

        d_out.reset(a)
        r = d_out.update(outside_change)
        self.assertEqual(r.difference, 0.0)
        self.assertFalse(r.changed)

    # 11. reset 清空状态
    def test_reset_clears_state(self):
        d = self._detector(stable_frames=2)
        a = _blank(value=0)
        b = _blank(value=255)
        d.reset(a)
        d.update(b)
        d.update(a.copy())
        d.update(a.copy())
        self.assertTrue(d.changed)
        d.reset(b)  # 新基线
        self.assertFalse(d.changed)
        self.assertEqual(d.stable_count, 0)
        self.assertFalse(d.stable)
        # 新基线下，喂入 b 是「无变化」
        r = d.update(b.copy())
        self.assertFalse(r.changed)
        self.assertEqual(r.difference, 0.0)

    # 首个 update 帧自动作为基线（不显式 reset）
    def test_first_update_becomes_baseline(self):
        d = self._detector(stable_frames=2)
        a = _blank(value=0)
        r0 = d.update(a)
        self.assertIsInstance(r0, FrameStateResult)
        self.assertFalse(r0.changed)
        self.assertEqual(r0.stable_count, 0)
        r1 = d.update(_blank(value=255))
        self.assertTrue(r1.changed)

    def test_property_accessors_track_last_update(self):
        d = self._detector(changed_threshold=0.5, stable_frames=2)
        a = _blank(value=0)
        d.reset(a)
        d.update(_blank(value=255))
        self.assertTrue(d.changed)
        self.assertGreater(d.last_difference, 0.5)
        # 回到基线：第一帧把 prev 从 255 拉回 a（相邻差异大，count 归零），
        # 之后两帧相邻安静，count 到 2 -> stable。
        d.update(a.copy())
        d.update(a.copy())
        d.update(a.copy())
        self.assertTrue(d.stable)
        self.assertEqual(d.stable_count, 2)

    def test_constructor_rejects_bad_params(self):
        with self.assertRaises(ValueError):
            FrameStateDetector(changed_threshold=0.1, stable_threshold=0.01, stable_frames=0)
        with self.assertRaises(ValueError):
            FrameStateDetector(changed_threshold=-0.1, stable_threshold=0.01, stable_frames=2)
        with self.assertRaises(ValueError):
            FrameStateDetector(changed_threshold=0.1, stable_threshold=-0.01, stable_frames=2)

    def test_update_shape_mismatch_raises(self):
        d = self._detector()
        d.reset(_blank(h=40, w=60))
        with self.assertRaises(ValueError):
            d.update(_blank(h=40, w=61))

    def test_reset_illegal_roi_raises_immediately(self):
        d = FrameStateDetector(changed_threshold=0.1, stable_threshold=0.01,
                               stable_frames=2, roi=(10, 10, 5, 20))
        with self.assertRaises(ValueError):
            d.reset(_blank(h=40, w=60))

    def test_default_pixel_threshold_is_documented_constant(self):
        # 该默认值只是通用保守值，不代表任何游戏页面的最佳参数。
        self.assertEqual(DEFAULT_PIXEL_THRESHOLD, 15)


if __name__ == '__main__':
    unittest.main()
