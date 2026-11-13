"""多账号超鬼王在默认过滤调度器中可被选中。"""

from types import SimpleNamespace
from unittest import TestCase

from module.config.config_model import ConfigModel
from module.config.scheduler import TaskScheduler
from tasks.Script.config_optimization import ScheduleRule


class RotationSchedulerTest(TestCase):
    def test_filter_includes_rotation_and_keeps_existing_task_order(self):
        task_name = ConfigModel.type('meta_demon_rotation')
        self.assertEqual('MetaDemonRotation', task_name)
        pending = [SimpleNamespace(command=name) for name in ('FrogBoss', task_name, 'MetaDemon', 'DailyTrifles')]
        selected = TaskScheduler.schedule(ScheduleRule.FILTER, pending)
        self.assertEqual(['DailyTrifles', 'MetaDemon', 'MetaDemonRotation', 'FrogBoss'],
                         [task.command for task in selected])
