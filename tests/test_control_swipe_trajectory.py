# This Python file uses the following encoding: utf-8
"""Control.swipe_trajectory 单元测试（Plan B 第一阶段的显式 opt-in 入口）。

对应任务规格「二十一、测试要求：Control」：
- minitouch -> 分派到 swipe_minitouch_trajectory。
- 非 minitouch -> 明确 NotImplementedError（不静默退化成端点滑动）。
- BehaviorTrace 仍只记一次 ACTION（action='swipe' + target + elapsed_ms），不记每个 MOVE。
- control_name 正确透传。
- 原 Control.swipe 行为完全不受影响。
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from module import behavior_trace
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.device.control import Control


class ControlSwipeTrajectoryTest(unittest.TestCase):
    def setUp(self):
        reset_behavior_traces()
        self._orig_dir = behavior_trace._LOG_DIR
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._tmpdir.name) / 'behavior'
        behavior_trace._LOG_DIR = self.log_dir

    def tearDown(self):
        reset_behavior_traces()
        behavior_trace._LOG_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def _make_control(self, method='minitouch', config_name='trajtest'):
        c = Control.__new__(Control)
        c.config = SimpleNamespace(
            config_name=config_name,
            script=SimpleNamespace(device=SimpleNamespace(control_method=method)),
        )
        c.swipe_minitouch_trajectory = Mock(name='swipe_minitouch_trajectory')
        c.swipe_minitouch = Mock(name='swipe_minitouch')
        c._invalidate_image_batch_cache = Mock()
        return c

    def _lines(self, config_name):
        files = list(self.log_dir.glob(f'{config_name}_*.jsonl'))
        if not files:
            return []
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln]

    # --- 分派 ---------------------------------------------------------------

    def test_minitouch_dispatches_to_trajectory_executor(self):
        c = self._make_control('minitouch')
        traj = [(100, 500, 0), (100, 460, 9), (100, 420, 12)]
        c.swipe_trajectory(traj, control_name='FRIEND_LIST')
        c.swipe_minitouch_trajectory.assert_called_once()
        (passed,), _ = c.swipe_minitouch_trajectory.call_args
        self.assertEqual(passed, traj)
        c.swipe_minitouch.assert_not_called()

    def test_accepts_iterator_input(self):
        c = self._make_control('minitouch')
        c.swipe_trajectory(iter([(0, 0, 0), (0, 40, 9)]))
        (passed,), _ = c.swipe_minitouch_trajectory.call_args
        self.assertEqual(passed, [(0, 0, 0), (0, 40, 9)])

    def test_non_minitouch_backends_raise_not_implemented(self):
        for method in ('adb', 'uiautomator2', 'scrcpy', 'window_message', 'ADB'):
            with self.subTest(method=method):
                c = self._make_control(method)
                with self.assertRaises(NotImplementedError):
                    c.swipe_trajectory([(1, 1, 0), (1, 40, 9)])
                c.swipe_minitouch_trajectory.assert_not_called()

    def test_non_iterable_trajectory_raises_valueerror(self):
        c = self._make_control('minitouch')
        with self.assertRaises(ValueError):
            c.swipe_trajectory(42)

    # --- BehaviorTrace ---------------------------------------------------------

    def test_records_single_action_swipe_event(self):
        c = self._make_control('minitouch', config_name='trajtrace')
        configure_behavior_trace('trajtrace', enabled=True)

        traj = [(10, 10, 0), (10, 300, 9), (10, 320, 9)]
        c.swipe_trajectory(traj, control_name='KEKKAI_SWIPE')

        rows = self._lines('trajtrace')
        # 1) 一次 swipe = 恰一行 ACTION
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['event'], 'ACTION')
        self.assertEqual(row['action'], 'swipe')
        # 9) target = control_name 原样
        self.assertEqual(row['target'], 'KEKKAI_SWIPE')
        self.assertIn('elapsed_ms', row)
        self.assertIsInstance(row['elapsed_ms'], int)
        # 8) 不逐 MOVE 落事件：顶层没有单点坐标键
        self.assertNotIn('x', row)
        extra = row['extra']
        # 2/3/4) trajectory 完整、顺序保留、dt_ms 保留
        self.assertEqual(extra['trajectory'],
                         [[10, 10, 0], [10, 300, 9], [10, 320, 9]])
        # 7) point_count == len(trajectory)
        self.assertEqual(extra['point_count'], 3)
        # 5/6) start == trajectory[0] 的 xy，end == trajectory[-1] 的 xy
        self.assertEqual((extra['start_x'], extra['start_y']), (10, 10))
        self.assertEqual((extra['end_x'], extra['end_y']), (10, 320))

    def test_trace_records_full_long_trajectory_as_one_action(self):
        # 60 个点也只写一条 ACTION，点全保留、顺序完整
        c = self._make_control('minitouch', config_name='trajlong')
        configure_behavior_trace('trajlong', enabled=True)
        traj = [(100, 500 - i, 0 if i == 0 else 8) for i in range(60)]
        c.swipe_trajectory(traj, control_name='LONG')
        rows = self._lines('trajlong')
        self.assertEqual(len(rows), 1)
        self.assertNotIn('MOVE', {r.get('action') for r in rows})
        pts = rows[0]['extra']['trajectory']
        self.assertEqual(len(pts), 60)
        self.assertEqual(rows[0]['extra']['point_count'], 60)
        self.assertEqual([p[1] for p in pts], [500 - i for i in range(60)])  # y 顺序完整
        self.assertEqual(pts[0], [100, 500, 0])
        self.assertEqual(pts[-1], [100, 441, 8])

    def test_trajectory_records_ints_even_if_caller_passes_floats(self):
        c = self._make_control('minitouch', config_name='trajflo')
        configure_behavior_trace('trajflo', enabled=True)
        c.swipe_trajectory([(10.4, 10.6, 0.0), (10.4, 300.5, 9.2)], control_name='F')
        pts = self._lines('trajflo')[0]['extra']['trajectory']
        self.assertEqual(pts, [[10, 11, 0], [10, 300, 9]])
        for p in pts:
            for v in p:
                self.assertIsInstance(v, int)

    def test_trace_disabled_by_default_no_file(self):
        c = self._make_control('minitouch', config_name='trajoff')
        c.swipe_trajectory([(10, 10, 0), (10, 300, 9)])
        self.assertEqual(self._lines('trajoff'), [])

    def test_disabled_trace_does_not_build_trajectory_extra(self):
        # 关闭态：is_recording() False -> 不组装 extra（自然规避几十个点的拷贝）
        import module.device.control as control_mod
        c = self._make_control('minitouch', config_name='trajoff2')
        configure_behavior_trace('trajoff2', enabled=False)
        called = []
        orig = control_mod._swipe_trajectory_extra
        control_mod._swipe_trajectory_extra = lambda t: called.append(t) or orig(t)
        try:
            c.swipe_trajectory([(1, 1, 0), (1, 40, 9)])
        finally:
            control_mod._swipe_trajectory_extra = orig
        self.assertEqual(called, [])
        self.assertEqual(self._lines('trajoff2'), [])

    def test_executor_failure_still_records_nothing_extra(self):
        c = self._make_control('minitouch', config_name='trajfail')
        c.swipe_minitouch_trajectory.side_effect = ValueError('bad trajectory')
        configure_behavior_trace('trajfail', enabled=True)
        with self.assertRaises(ValueError):
            c.swipe_trajectory([(1, 1, 0)])
        # 动作没有正常返回 -> 不写 ACTION（与 Control.swipe 一致的 v1 契约）
        self.assertEqual(self._lines('trajfail'), [])

    # --- 不影响 Control.swipe --------------------------------------------------

    def test_control_swipe_still_uses_endpoint_path(self):
        c = self._make_control('minitouch', config_name='swipeplain')
        c.handle_control_check = Mock()
        c.swipe((10, 10), (10, 400))
        c.swipe_minitouch.assert_called_once()
        c.swipe_minitouch_trajectory.assert_not_called()

    def test_legacy_control_swipe_trace_carries_endpoints_only_no_fake_trajectory(self):
        # section 三十四：legacy Control.swipe 只知道 p1/p2 —— extra 带端点，绝不伪造 trajectory
        c = self._make_control('minitouch', config_name='swipetrace')
        c.handle_control_check = Mock()
        configure_behavior_trace('swipetrace', enabled=True)
        # x 有位移，避免 distance_check 的 +1 兜底，端点即调用方给的值
        c.swipe((120, 200), (160, 600), control_name='FRIEND_LIST')
        rows = self._lines('swipetrace')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['event'], row['action']), ('ACTION', 'swipe'))
        self.assertEqual(row['target'], 'FRIEND_LIST')
        extra = row['extra']
        self.assertEqual((extra['start_x'], extra['start_y']), (120, 200))
        self.assertEqual((extra['end_x'], extra['end_y']), (160, 600))
        self.assertEqual(extra['point_count'], 2)
        self.assertNotIn('trajectory', extra)          # 没有完整轨迹 -> 不写 trajectory 键

    def test_swipe_trajectory_does_not_call_distance_check_or_duration(self):
        # swipe_trajectory 不做端点合成 / distance_check：<10px 也照发
        c = self._make_control('minitouch')
        c.swipe_trajectory([(100, 100, 0), (103, 104, 9)])
        c.swipe_minitouch_trajectory.assert_called_once()


if __name__ == '__main__':
    unittest.main()
