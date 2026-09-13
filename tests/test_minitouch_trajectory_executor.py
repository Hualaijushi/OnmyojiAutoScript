# This Python file uses the following encoding: utf-8
"""minitouch 自定义轨迹执行层单元测试（Plan B 第一阶段）。

对应任务规格「二十、测试要求：executor」：
- 用 fake builder，不连真实 minitouch。
- 命令序列严格为 DOWN·COMMIT·SEND / (MOVE·COMMIT·WAIT)* / SEND / UP·COMMIT·SEND。
- 每段 dt 原样写入、x 正负变化不被夹直、轨迹不被重新 insert_swipe、不再叠加
  random_int(6, 15)、pressure 走现有 _humanized_pressure。
- `_ensure_trajectory` 非法输入抛 ValueError（在 @retry 之外）。
"""

import unittest
from unittest.mock import Mock, patch

from module.device.method.minitouch import Minitouch, _ensure_trajectory


class _BuilderStub:
    def __init__(self):
        self.events = []
        self.delay = 0
        self.DEFAULT_DELAY = 0.05

    def down(self, x, y, contact=0, pressure=100):
        self.events.append(('down', x, y, contact, pressure))
        return self

    def move(self, x, y, contact=0, pressure=100):
        self.events.append(('move', x, y, contact, pressure))
        return self

    def up(self, contact=0):
        self.events.append(('up', contact))
        return self

    def commit(self):
        self.events.append(('commit',))
        return self

    def wait(self, milliseconds=10):
        self.events.append(('wait', milliseconds))
        self.delay += milliseconds
        return self

    def clear(self):
        self.events.append(('clear',))
        self.delay = 0


class EnsureTrajectoryTest(unittest.TestCase):
    def test_valid_trajectory_is_rounded_and_first_dt_zeroed(self):
        cleaned = _ensure_trajectory([(1.6, 2.4, 99), (10.2, 20.8, 8.9), (30, 40, 12)])
        self.assertEqual(cleaned, [(2, 2, 0), (10, 21, 9), (30, 40, 12)])

    def test_rejects_fewer_than_two_points(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0)])

    def test_rejects_non_iterable(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory(123)

    def test_rejects_point_without_three_fields(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (2, 2)])

    def test_rejects_non_positive_move_dt(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (2, 2, 0)])
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (2, 2, 0.4)])   # round(0.4) -> 0

    def test_rejects_nan_or_inf(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (float('nan'), 2, 5)])
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (2, 2, float('inf'))])

    def test_rejects_bool_fields(self):
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (True, 2, 5)])
        with self.assertRaises(ValueError):
            _ensure_trajectory([(1, 1, 0), (2, 2, True)])

    def test_first_point_dt_ignored_even_if_negative(self):
        cleaned = _ensure_trajectory([(1, 1, -50), (2, 2, 5)])
        self.assertEqual(cleaned[0], (1, 1, 0))


class SwipeMinitouchTrajectoryTest(unittest.TestCase):
    def _task(self, builder):
        task = Minitouch.__new__(Minitouch)
        task.__dict__['minitouch_builder'] = builder
        task.minitouch_send = Mock()
        task._humanized_pressure = Mock(return_value=1)
        return task

    def test_command_sequence_is_down_moves_up(self):
        builder = _BuilderStub()
        task = self._task(builder)

        task.swipe_minitouch_trajectory([
            (100, 500, 0),
            (99, 480, 8),
            (97, 450, 10),
            (100, 420, 14),
        ])

        self.assertEqual(builder.events, [
            ('down', 100, 500, 0, 1), ('commit',),
            ('move', 99, 480, 0, 1), ('commit',), ('wait', 8),
            ('move', 97, 450, 0, 1), ('commit',), ('wait', 10),
            ('move', 100, 420, 0, 1), ('commit',), ('wait', 14),
            ('up', 0), ('commit',),
        ])
        # DOWN 批 / MOVE 批 / UP 批各 send 一次
        self.assertEqual(task.minitouch_send.call_count, 3)

    def test_each_segment_dt_written_verbatim(self):
        builder = _BuilderStub()
        task = self._task(builder)
        task.swipe_minitouch_trajectory([(0, 0, 0), (1, 10, 7), (2, 20, 21), (3, 30, 4)])
        waits = [e[1] for e in builder.events if e[0] == 'wait']
        self.assertEqual(waits, [7, 21, 4])

    def test_x_sign_changes_not_flattened(self):
        builder = _BuilderStub()
        task = self._task(builder)
        task.swipe_minitouch_trajectory([(100, 600, 0), (96, 560, 9),
                                         (104, 520, 9), (100, 480, 9)])
        move_xs = [e[1] for e in builder.events if e[0] == 'move']
        self.assertEqual(move_xs, [96, 104, 100])

    def test_pressure_uses_humanized_pressure_once_for_whole_gesture(self):
        builder = _BuilderStub()
        task = self._task(builder)
        task._humanized_pressure = Mock(return_value=37)
        task.swipe_minitouch_trajectory([(0, 0, 0), (1, 10, 9), (2, 20, 9)])
        task._humanized_pressure.assert_called_once_with()
        pressures = {e[-1] for e in builder.events if e[0] in ('down', 'move')}
        self.assertEqual(pressures, {37})

    def test_does_not_reinsert_swipe_or_resample_interval(self):
        builder = _BuilderStub()
        task = self._task(builder)
        with patch('module.device.method.minitouch.insert_swipe') as insert_mock, \
             patch('module.device.method.minitouch.random_int') as random_mock:
            task.swipe_minitouch_trajectory([(0, 0, 0), (5, 40, 11), (10, 80, 12)])
        insert_mock.assert_not_called()
        random_mock.assert_not_called()

    def test_invalid_trajectory_raises_valueerror_without_retry(self):
        builder = _BuilderStub()
        task = self._task(builder)
        # 若校验在 @retry 之内会被吞掉并最终抛 RequestHumanTakeover；这里必须是干净 ValueError
        with self.assertRaises(ValueError):
            task.swipe_minitouch_trajectory([(1, 1, 0)])
        self.assertEqual(builder.events, [])
        task.minitouch_send.assert_not_called()

    def test_retry_wrapper_present_on_run(self):
        # 发命令的内层套用现有 @retry（函数名带 __wrapped__ 说明被 functools.wraps 包过）
        self.assertTrue(hasattr(Minitouch._swipe_minitouch_trajectory_run, '__wrapped__'))


if __name__ == '__main__':
    unittest.main()
