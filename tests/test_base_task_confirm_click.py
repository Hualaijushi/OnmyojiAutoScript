from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.base_task import BaseTask


class _TimerStub:
    def __init__(self, limit, ready, events=None):
        self.limit = limit
        self.ready = ready
        self.events = events

    def reached(self):
        if self.events is not None:
            self.events.append('interval')
        return self.ready

    def reset(self):
        if self.events is not None:
            self.events.append('reset')


class BaseTaskConfirmClickTest(TestCase):
    def setUp(self):
        self.task = BaseTask.__new__(BaseTask)
        self.task.interval_timer = {}
        self.task.device = SimpleNamespace(click=Mock(), long_click=Mock())

    @patch('tasks.base_task.random_delay')
    @patch('tasks.base_task.sleep')
    def test_old_path_keeps_original_behavior(self, sleep_mock, random_delay_mock):
        target = SimpleNamespace(name='target', coord=Mock(return_value=(10, 20)))
        self.task.appear = Mock(return_value=True)
        self.task.screenshot = Mock()

        result = self.task.appear_then_click(target, interval=1)

        self.assertTrue(result)
        self.task.appear.assert_called_once_with(target, interval=1, threshold=None)
        target.coord.assert_called_once_with()
        self.task.device.click.assert_called_once_with(10, 20, control_name='target')
        sleep_mock.assert_not_called()
        random_delay_mock.assert_not_called()
        self.task.screenshot.assert_not_called()

    @patch('tasks.base_task.random_delay', return_value=0.15)
    @patch('tasks.base_task.sleep')
    def test_confirm_path_rechecks_and_clicks_latest_position(self, sleep_mock, random_delay_mock):
        events = []
        target = SimpleNamespace(name='target', roi='A')

        def appear(_target, threshold=None):
            events.append(f'appear-{target.roi}')
            if target.roi == 'A':
                target.roi = 'B'
            return True

        def screenshot():
            events.append('screenshot')

        def coord():
            events.append(f'coord-{target.roi}')
            return (30, 40)

        def click(x, y, control_name):
            events.append(f'click-{x}-{y}-{control_name}')

        target.coord = coord
        self.task.appear = appear
        self.task.screenshot = screenshot
        self.task.device.click = click
        sleep_mock.side_effect = lambda delay: events.append(f'sleep-{delay}')

        result = self.task.appear_then_click(target, confirm_delay=(0.08, 0.22))

        self.assertTrue(result)
        random_delay_mock.assert_called_once_with(0.08, 0.22)
        self.assertEqual(events, [
            'appear-A',
            'sleep-0.15',
            'screenshot',
            'appear-B',
            'coord-B',
            'click-30-40-target',
        ])

    @patch('tasks.base_task.random_delay', return_value=0.15)
    @patch('tasks.base_task.sleep')
    def test_confirm_path_does_not_click_when_target_disappears(self, sleep_mock, _random_delay_mock):
        target = SimpleNamespace(name='target', coord=Mock(return_value=(10, 20)))
        timer = _TimerStub(limit=1, ready=True)
        timer.reset = Mock()
        self.task.interval_timer['target'] = timer
        self.task.appear = Mock(side_effect=[True, False])
        self.task.screenshot = Mock()

        result = self.task.appear_then_click(target, interval=1, confirm_delay=(0.08, 0.22))

        self.assertFalse(result)
        sleep_mock.assert_called_once_with(0.15)
        self.task.screenshot.assert_called_once_with()
        target.coord.assert_not_called()
        self.task.device.click.assert_not_called()
        timer.reset.assert_not_called()

    @patch('tasks.base_task.random_delay')
    @patch('tasks.base_task.sleep')
    def test_confirm_path_skips_everything_when_interval_is_not_ready(self, sleep_mock, random_delay_mock):
        target = SimpleNamespace(name='target', coord=Mock())
        self.task.interval_timer['target'] = _TimerStub(limit=1, ready=False)
        self.task.appear = Mock()
        self.task.screenshot = Mock()

        result = self.task.appear_then_click(target, interval=1, confirm_delay=(0.08, 0.22))

        self.assertFalse(result)
        self.task.appear.assert_not_called()
        random_delay_mock.assert_not_called()
        sleep_mock.assert_not_called()
        self.task.screenshot.assert_not_called()
        self.task.device.click.assert_not_called()

    @patch('tasks.base_task.random_delay', return_value=0.15)
    @patch('tasks.base_task.sleep')
    def test_confirm_path_resets_interval_after_click(self, sleep_mock, _random_delay_mock):
        events = []
        target = SimpleNamespace(name='target', coord=lambda: (10, 20))
        self.task.interval_timer['target'] = _TimerStub(limit=1, ready=True, events=events)
        self.task.appear = Mock(side_effect=lambda _target, threshold=None: events.append('appear') or True)
        self.task.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        self.task.device.click = Mock(side_effect=lambda *_args, **_kwargs: events.append('click'))
        sleep_mock.side_effect = lambda _delay: events.append('sleep')

        result = self.task.appear_then_click(
            target,
            interval=1,
            confirm_delay=(0.08, 0.22),
        )

        self.assertTrue(result)
        self.assertEqual(events, [
            'interval',
            'appear',
            'sleep',
            'screenshot',
            'appear',
            'click',
            'reset',
        ])
