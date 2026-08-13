# This Python file uses the following encoding: utf-8
# @author AzurTian
from tasks.ActivityShikigami.activities.normal import NormalClimbAct
from tasks.base_task import BaseTask


class ScriptTask(BaseTask):

    def run(self):
        NormalClimbAct(self.config, self.device).run()


if __name__ == '__main__':
    print([1, 2, 3][2])
