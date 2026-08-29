from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

import numpy as np

from module.base.utils import random as random_utils
from module.base.decorator import Config
from module.device.method.minitouch import Minitouch


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

    def to_minitouch(self):
        return 'test-command\n'

    def clear(self):
        self.events.append(('clear',))
        self.delay = 0


class _SocketOutputStub:
    def __init__(self, lines):
        self.lines = iter(lines)

    def readline(self):
        return next(self.lines)


class _SocketClientStub:
    def __init__(self, lines):
        self.output = _SocketOutputStub(lines)
        self.connect_calls = []
        self.timeout = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, address):
        self.connect_calls.append(address)

    def makefile(self):
        return self.output

    def close(self):
        pass


class _RandomStub:
    def __init__(self):
        self.randint_calls = []
        self.triangular_calls = []

    def randint(self, min_value, max_value):
        self.randint_calls.append((min_value, max_value))
        return max_value

    def triangular(self, min_value, max_value, mode):
        self.triangular_calls.append((min_value, max_value, mode))
        return mode


class MinitouchRandomizationTest(TestCase):
    @staticmethod
    def _config_method(name, options):
        for record in Config.func_list[name]:
            func = record['func']
            if func.__module__ == 'module.device.method.minitouch' and record['options'] == options:
                return func
        raise AssertionError(f'未找到配置方法：{name} {options}')

    def _task(self, builder=None):
        task = Minitouch.__new__(Minitouch)
        if builder is not None:
            task.__dict__['minitouch_builder'] = builder
        task.minitouch_send = Mock()
        return task

    def test_public_random_helpers_use_module_system_random(self):
        rng = _RandomStub()
        with patch.object(random_utils, '_rng', rng):
            self.assertEqual(random_utils.random_int(6, 15), 15)
            self.assertEqual(random_utils.random_triangular(45, 130, 65), 65)

        self.assertEqual(rng.randint_calls, [(6, 15)])
        self.assertEqual(rng.triangular_calls, [(45.0, 130.0, 65.0)])

    def test_public_random_helpers_validate_parameters(self):
        for values in ((True, 1), (1.0, 2), (1, '2')):
            with self.subTest(values=values):
                with self.assertRaises(TypeError):
                    random_utils.random_int(*values)
        with self.assertRaises(ValueError):
            random_utils.random_int(2, 1)

        self.assertEqual(random_utils.random_int(3, 3), 3)

        invalid_triangular = (
            (True, 2, 1),
            (0, float('nan'), 0),
            (0, float('inf'), 0),
            (2, 1, 1),
            (0, 2, -1),
            (0, 2, 3),
        )
        for values in invalid_triangular:
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    random_utils.random_triangular(*values)

        self.assertEqual(random_utils.random_triangular(3, 3, 3), 3)

    def test_pressure_ranges_are_safe(self):
        for max_pressure in (1, 5, 10, 19, 20, 100):
            with self.subTest(max_pressure=max_pressure), \
                    patch('module.device.method.minitouch.random_int', side_effect=lambda low, high: high) as random_mock:
                task = SimpleNamespace(max_pressure=max_pressure)
                pressure = Minitouch._humanized_pressure(task)

                self.assertEqual(pressure, max_pressure)
                random_mock.assert_called_once_with(max(1, max_pressure // 2), max_pressure)

    def test_invalid_and_missing_pressure_use_minimum_fallback(self):
        for value in (0, -1, True, None, 'invalid'):
            with self.subTest(value=value), \
                    patch('module.device.method.minitouch.random_int', return_value=1) as random_mock:
                pressure = Minitouch._humanized_pressure(SimpleNamespace(max_pressure=value))

                self.assertEqual(pressure, 1)
                random_mock.assert_called_once_with(1, 1)

        with patch('module.device.method.minitouch.random_int', return_value=1) as random_mock:
            self.assertEqual(Minitouch._humanized_pressure(SimpleNamespace()), 1)
            random_mock.assert_called_once_with(1, 1)

    def test_handshake_reads_and_normalizes_max_pressure(self):
        init = self._config_method('minitouch_init', {'DEVICE_OVER_HTTP': False})
        for value, expected in ((100, 100), (10, 10), (0, 1), (-1, 1), ('invalid', 1)):
            with self.subTest(value=value):
                client = _SocketClientStub((
                    'v 1\n',
                    f'^ 2 1280 720 {value}\n',
                    '$ 123\n',
                ))
                task = Minitouch.__new__(Minitouch)
                task.get_orientation = Mock()
                task.adb_forward = Mock(return_value=1111)

                with patch('module.device.method.minitouch.socket.socket', return_value=client):
                    init(task)

                self.assertEqual(task.max_pressure, expected)
                self.assertEqual(task.max_x, 1280)
                self.assertEqual(task.max_y, 720)
                self.assertEqual(client.connect_calls, [('127.0.0.1', 1111)])

    def test_dwell_is_integer_and_covers_configured_bounds(self):
        for raw_value, expected in ((45.0, 45), (129.9, 130)):
            with self.subTest(raw_value=raw_value), \
                    patch('module.device.method.minitouch.random_triangular', return_value=raw_value) as random_mock:
                dwell = Minitouch._humanized_dwell(SimpleNamespace())

                self.assertEqual(dwell, expected)
                self.assertIsInstance(dwell, int)
                self.assertLessEqual(45, dwell)
                self.assertLessEqual(dwell, 130)
                random_mock.assert_called_once_with(45, 130, 65)

    @patch('module.device.method.minitouch.random_triangular', return_value=65.9)
    def test_click_is_down_wait_up_without_move(self, triangular_mock):
        builder = _BuilderStub()
        task = self._task(builder)
        task._humanized_pressure = Mock(return_value=73)

        task.click_minitouch(100, 200)

        self.assertEqual(builder.events, [
            ('down', 100, 200, 0, 73),
            ('commit',),
            ('wait', 66),
            ('up', 0),
            ('commit',),
        ])
        triangular_mock.assert_called_once_with(45, 130, 65)
        task.minitouch_send.assert_called_once_with()

    @patch('module.device.method.minitouch.time.sleep')
    def test_minitouch_send_waits_for_builder_delay_and_default_delay(self, sleep_mock):
        send = self._config_method('minitouch_send', {'DEVICE_OVER_HTTP': False})
        builder = _BuilderStub()
        builder.delay = 65
        task = Minitouch.__new__(Minitouch)
        task.__dict__['minitouch_builder'] = builder
        task._minitouch_client = Mock()

        send(task)

        task._minitouch_client.sendall.assert_called_once_with(b'test-command\n')
        task._minitouch_client.recv.assert_called_once_with(0)
        sleep_mock.assert_called_once_with(0.115)
        self.assertEqual(builder.events, [('clear',)])
        self.assertEqual(builder.delay, 0)

    def test_long_click_keeps_caller_duration_and_random_pressure(self):
        builder = _BuilderStub()
        task = self._task(builder)
        task._humanized_pressure = Mock(return_value=88)

        task.long_click_minitouch(100, 200, duration=1.25)

        self.assertEqual(builder.events, [
            ('down', 100, 200, 0, 88),
            ('commit',),
            ('wait', 1250),
            ('up', 0),
            ('commit',),
        ])
        task._humanized_pressure.assert_called_once_with()

    @patch('module.device.method.minitouch.insert_swipe', return_value=[(1, 2), (3, 4), (5, 6)])
    @patch('module.device.method.minitouch.random_int', side_effect=(6, 15))
    def test_swipe_samples_each_move_interval(self, random_mock, _insert_swipe_mock):
        builder = _BuilderStub()
        task = self._task(builder)

        task.swipe_minitouch((1, 2), (5, 6))

        self.assertEqual(random_mock.call_args_list, [call(6, 15), call(6, 15)])
        self.assertEqual([event for event in builder.events if event[0] == 'wait'], [
            ('wait', 6),
            ('wait', 15),
        ])

    @patch('module.device.method.minitouch.random_rectangle_point', return_value=np.array((0, 0)))
    @patch('module.device.method.minitouch.insert_swipe', return_value=[(1, 2), (3, 4), (5, 6)])
    @patch('module.device.method.minitouch.random_int', side_effect=(6, 15))
    def test_drag_samples_each_move_interval(
            self,
            random_mock,
            _insert_swipe_mock,
            _random_point_mock,
    ):
        builder = _BuilderStub()
        task = self._task(builder)

        task.drag_minitouch((1, 2), (5, 6))

        self.assertEqual(random_mock.call_args_list, [call(6, 15), call(6, 15)])
        self.assertEqual([event for event in builder.events if event[0] == 'wait'], [
            ('wait', 6),
            ('wait', 15),
            ('wait', 140),
            ('wait', 140),
        ])
