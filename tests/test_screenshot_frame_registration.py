# This Python file uses the following encoding: utf-8
"""截图帧注册开关：annotator 实时采集不能顶掉同名配置正在运行的脚本的帧（图像服务每个 config_name 只保留一帧）。"""
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from module.device.screenshot import Screenshot
from module.server import tool_capture_worker


class FakeImageClient:
    def __init__(self):
        self.registered = []

    def register_frame(self, image, config_name):
        self.registered.append(config_name)
        return {'frame_id': f'F{len(self.registered)}'}


def make_probe():
    """不走 Device 的完整初始化，只提供 Screenshot.screenshot() 用到的最小环境。"""
    probe = object.__new__(Screenshot)
    probe.__dict__['screenshot_methods'] = {'X': lambda: np.zeros((2, 2, 3), dtype=np.uint8)}
    probe.config = SimpleNamespace(
        config_name='oas1',
        script=SimpleNamespace(device=SimpleNamespace(screenshot_method='X'),
                               error=SimpleNamespace(save_error=False)))
    probe.check_screen_size = lambda: True
    probe.check_screen_black = lambda: True
    return probe


class ScreenshotFrameRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeImageClient()
        patcher = mock.patch('module.device.screenshot.get_image_client', return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_registers_one_frame_per_screenshot(self):
        probe = make_probe()
        self.assertTrue(probe.register_image_frame)
        probe.screenshot()
        self.assertEqual(self.client.registered, ['oas1'])
        self.assertEqual(probe.image_frame_id, 'F1')

    def test_disabled_never_registers_and_clears_the_frame_id(self):
        probe = make_probe()
        probe.image_frame_id = 'OLD'
        probe.register_image_frame = False
        image = probe.screenshot()
        probe.screenshot()
        self.assertEqual(self.client.registered, [])
        self.assertIsNone(probe.image_frame_id)
        self.assertEqual(image.shape, (2, 2, 3))

    def test_flag_is_per_instance(self):
        quiet, normal = make_probe(), make_probe()
        quiet.register_image_frame = False
        quiet.screenshot()
        normal.screenshot()
        self.assertEqual(self.client.registered, ['oas1'])
        self.assertTrue(normal.register_image_frame)


class AnnotatorDeviceTest(unittest.TestCase):
    def test_capture_worker_device_does_not_register_frames(self):
        created = []

        class FakeDevice:
            def __init__(self, config):
                created.append(self)
                self.calls = []

            def disable_stuck_detection(self):
                self.calls.append('stuck')

            def screenshot_interval_set(self, interval):
                self.calls.append(('interval', interval))

        with mock.patch.object(tool_capture_worker, 'Device', FakeDevice):
            device = tool_capture_worker._build_device('s1', 'oas1', object(), 0.5)
        self.assertIs(device, created[0])
        self.assertFalse(device.register_image_frame)
        self.assertEqual(device.calls, ['stuck', ('interval', 0.5)])


if __name__ == '__main__':
    unittest.main()
