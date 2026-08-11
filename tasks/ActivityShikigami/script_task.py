# This Python file uses the following encoding: utf-8
# @author AzurTian
from tasks.ActivityShikigami.activities.fake_god import FakeGodAct
from tasks.ActivityShikigami.activities.normal import NormalClimbAct
from tasks.base_task import BaseTask


class ScriptTask(BaseTask):

    def run(self):
        # FakeGodAct(self.config, self.device).run()
        NormalClimbAct(self.config, self.device).run()


if __name__ == '__main__':
    print([1, 2, 3][2])
