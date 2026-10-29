# This Python file uses the following encoding: utf-8
"""异常请求的 Restart 不能被「调度器启动时跳过首次 Restart」吞掉（D-07）。

驱动真实的 `Script.loop` / `Script.run` / `_handle_task_exception`、真实 `Config.task_call('Restart')` 和真实调度选择
（临时目录里的真实配置文件，每次失败后重载配置）；只替身设备、运行时准备、任务叶节点和模拟器。

区分两类 Restart：
- A：脚本刚启动时已经到点的例行 / 陈旧 Restart，沿用原规则跳过（否则每次启动都会无条件重启游戏）；
- B：本进程内由任务运行 / 准备阶段异常请求的恢复 Restart，登记成功之后不能再被当成 A。
跨进程（用户在 GUI 点停止再启动）的新进程不属于 B，见 `test_new_process_*`。
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.config.config import Config
from module.config.config_model import ConfigModel
from module.exception import (
    GameBugError, GameNotRunningError, GamePageUnknownError, GameStuckError, GameTooManyClickError,
    RequestHumanTakeover, ScriptError, TaskEnd,
)

LOOP_GUARD = 40     # 独立的失控上限：任务叶节点被调用的总次数，防止错误实现让循环挂死测试


class _StopLoop(BaseException):
    """穿过 `Script.loop` 的 `except Exception`，用来结束调度循环。"""


class Fixture(unittest.TestCase):
    def setUp(self):
        import script as script_mod
        from module.script import ScriptRuntimeDecision
        self.script_mod = script_mod
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.tmp = tempfile.mkdtemp(prefix='oas_restart_first_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.chdir(self.tmp)
        os.makedirs('config')
        patch.object(script_mod.logger, 'set_file_logger').start()
        patch.object(script_mod, 'IS_WINDOWS', False).start()
        patch.object(script_mod, 'LOOP_POLL_INTERVAL', 0).start()
        patch.object(Config, 'notifier', Mock(name='notifier')).start()
        manager = Mock(name='fatigue')
        manager.load_factor = 1.0
        manager.enabled = False
        manager.task_identity = None
        patch.object(script_mod, 'get_fatigue_manager', return_value=manager).start()
        patch.object(script_mod, 'get_behavior_trace', return_value=Mock()).start()
        patch.object(script_mod, 'set_ocr_logging_enabled').start()
        patch.object(script_mod, 'load_module', side_effect=self._module).start()
        patch.object(script_mod.Script, 'exception_handler').start()
        patch.object(script_mod.Script, 'save_error_log').start()
        self.addCleanup(patch.stopall)
        self.decision_ready = ScriptRuntimeDecision.READY
        self.ran = []            # 任务叶节点被真正调用的顺序
        self.plan = {}           # 命令 -> 每次调用的脚本：异常实例 / 'ok' / 'stop' / 可调用
        self.prepare_plan = []   # 每次 prepare_task_execution 的脚本：异常实例 / None（正常）
        self.script = None

    # ---- 任务叶节点：按脚本抛异常 / 正常结束 / 结束循环
    def _module(self, name, path):
        command = Path(path).parent.name

        def run():
            self.ran.append(command)
            if len(self.ran) > LOOP_GUARD:
                raise AssertionError('流程失控：任务被调用的次数超过上限（疑似无限重启 / 死循环）')
            steps = self.plan.get(command, [])
            step = steps.pop(0) if steps else 'stop'
            if step == 'stop':
                raise _StopLoop
            if step == 'ok':
                self.script.config.task_delay(task=command, success=True, server=True)   # 真实任务结束前都会自己排期
                raise TaskEnd
            if callable(step):
                return step()
            raise step

        return SimpleNamespace(ScriptTask=lambda config, device: SimpleNamespace(run=run))

    # ---- 配置 / Script
    def write_config(self, *, restart_due, dokan_due=True, tweak=None):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                value['scheduler']['enable'] = False
        due = datetime.now() - timedelta(minutes=1)
        future = datetime.now() + timedelta(days=1)
        data['restart']['scheduler'].update(enable=True, next_run=due if restart_due else future)
        data['dokan']['scheduler'].update(enable=True, next_run=due if dokan_due else future)
        if tweak is not None:
            tweak(data)
        ConfigModel.write_json('simA', data)

    def make_script(self, *, first=True):
        from module.script.team_sync import TeamSync
        script = self.script_mod.Script.__new__(self.script_mod.Script)
        script.team_sync = TeamSync('simA', started_at=datetime.now() - timedelta(minutes=10))
        script.server = script.state_queue = script.command_queue = script.gui_update_task = None
        script._emulator_down = False
        script.is_first_task = first
        script.config_name = 'simA'
        script.failure_record = {}
        script.last_task_runtime_outcome = None
        script.loop_thread = None
        script.device = Mock(name='device')
        script.device.package = 'pkg'
        script.runtime = Mock(name='runtime')
        script.runtime.prepare_task_execution.side_effect = self._prepare
        script.runtime.handle_wait_during_idle.side_effect = _StopLoop     # 没有到点的任务：调度循环到此结束
        self.script = script
        return script

    def _prepare(self, task):
        step = self.prepare_plan.pop(0) if self.prepare_plan else None
        if isinstance(step, BaseException):
            raise step
        return self.decision_ready

    def restart_next_run(self):
        self.script.__dict__.pop('config', None)
        return self.script.config.model.restart.scheduler.next_run

    def run_loop(self, script):
        """跑一轮调度循环直到它自己结束（_StopLoop）；返回是否因 _StopLoop 结束。"""
        try:
            script.loop()
        except _StopLoop:
            return True
        return False


# ---------------------------------------------------------------------------------------------- A：例行 Restart
class RoutineRestartTest(Fixture):
    def test_stale_restart_at_startup_is_still_skipped_when_no_exception_requested_it(self):
        self.write_config(restart_due=True)
        script = self.make_script(first=True)
        self.plan['Dokan'] = ['stop']
        self.run_loop(script)
        self.assertEqual(self.ran, ['Dokan'])                       # 例行 Restart 没有跑
        self.assertGreater(self.restart_next_run(), datetime.now())  # 被推迟到下一次，而不是留在「已到点」

    def test_after_the_first_task_a_due_restart_runs_normally(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)

        def first_task():
            script.config.model.restart.scheduler.next_run = datetime.now() - timedelta(seconds=1)   # 首个任务期间 Restart 到点
            script.config.save()
            script.config.task_delay(task='Dokan', success=True, server=True)
            raise TaskEnd

        self.plan.update(Dokan=[first_task], Restart=['ok'])
        self.run_loop(script)
        self.assertEqual(self.ran, ['Dokan', 'Restart'])            # 首个任务之后，到点的 Restart 不再被跳过


# ---------------------------------------------------------------------------------------------- B：异常请求的恢复
class RequestedRecoveryTest(Fixture):
    RECOVERABLE = (GameStuckError('stuck'), GameTooManyClickError('too many'), GameBugError('bug'),
                   GamePageUnknownError('unknown'), GameNotRunningError('died'))

    def test_exception_in_the_first_task_run_is_followed_by_an_executed_restart(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        self.plan.update(Dokan=[GameTooManyClickError('dokan_welfare_list_up'), 'ok'], Restart=['ok'])
        self.run_loop(script)
        self.assertEqual(self.ran, ['Dokan', 'Restart', 'Dokan'])   # Restart 真的运行了，且恰好一次
        self.assertGreater(self.restart_next_run(), datetime.now())  # 恢复后这次请求已清理，不会再被拉起

    def test_exception_in_the_first_task_preparation_is_followed_by_an_executed_restart(self):
        for error in self.RECOVERABLE:
            with self.subTest(error=type(error).__name__):
                self.ran.clear()
                self.write_config(restart_due=False)
                script = self.make_script(first=True)
                self.plan.update(Dokan=['ok'], Restart=['ok'])
                self.prepare_plan = [error]                         # 首个任务的准备阶段就出异常
                self.run_loop(script)
                self.assertEqual(self.ran, ['Restart', 'Dokan'])    # 没有被「Skip first restart」吃掉
                self.assertFalse(script.is_first_task)

    def test_request_survives_config_reload_and_scheduler_reentry_in_the_same_process(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        self.plan.update(Dokan=['ok'], Restart=['ok'])
        self.prepare_plan = [GameStuckError('stuck')]
        script.device.sleep.side_effect = [_StopLoop, None]         # 登记之后的 10 秒等待处结束这一轮调度
        self.assertTrue(self.run_loop(script))
        self.assertEqual(self.ran, [])
        script.__dict__.pop('config', None)                         # 配置重载
        self.assertLessEqual(script.config.model.restart.scheduler.next_run, datetime.now())   # 请求落在文件里
        self.run_loop(script)                                       # 同一个进程内重新进入调度循环
        self.assertEqual(self.ran, ['Restart', 'Dokan'])

    def test_new_process_with_a_leftover_request_is_the_startup_case_by_design(self):
        # 10-27 oas2 的实际经过：异常登记 Restart 后，用户在 GUI 点了停止再启动（新进程、新的 Script）；
        # 新进程无法区分「异常留下的请求」和「陈旧的例行 Restart」，仍按启动规则跳过。这是已知边界，不属于本进程内的 B
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        self.prepare_plan = [GameStuckError('stuck')]
        script.device.sleep.side_effect = _StopLoop
        self.run_loop(script)
        fresh = self.make_script(first=True)
        self.plan.update(Dokan=['stop'])
        self.run_loop(fresh)
        self.assertEqual(self.ran, ['Dokan'])

    def test_request_is_executed_only_once_and_other_tasks_continue_as_scheduled(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        self.plan.update(Dokan=[GameStuckError('stuck'), 'ok'], Restart=['ok', 'ok'])
        self.run_loop(script)
        self.assertEqual(self.ran.count('Restart'), 1)
        self.assertEqual(self.ran, ['Dokan', 'Restart', 'Dokan'])

    def test_persistent_failure_still_stops_after_three_failures_without_endless_restarts(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        self.plan.update(Dokan=[GameStuckError('stuck')] * 3, Restart=['ok', 'ok', 'ok'])
        with self.assertRaises(SystemExit):
            script.loop()
        self.assertEqual(self.ran, ['Dokan', 'Restart', 'Dokan', 'Restart', 'Dokan'])   # 现有的 3 次上限

    def test_fatal_errors_do_not_request_a_restart(self):
        for error in (ScriptError('bug'), RequestHumanTakeover('stop')):
            with self.subTest(error=type(error).__name__):
                self.write_config(restart_due=False)
                script = self.make_script(first=True)
                script._loop_fail_before_exit = Mock()
                with patch.object(Config, 'task_call') as task_call, self.assertRaises(SystemExit):
                    script._handle_task_exception(error, 'Dokan')
                task_call.assert_not_called()
                self.assertTrue(script.is_first_task)


# ---------------------------------------------------------------------------------------------- 请求登记失败
class RegistrationTest(Fixture):
    def test_failed_registration_does_not_pretend_the_recovery_is_scheduled(self):
        for result in (False, OSError('disk full')):
            with self.subTest(result=repr(result)):
                self.write_config(restart_due=False)
                script = self.make_script(first=True)
                kwargs = {'side_effect': result} if isinstance(result, BaseException) else {'return_value': result}
                with patch.object(Config, 'task_call', **kwargs):
                    if isinstance(result, BaseException):
                        with self.assertRaises(OSError):
                            script._handle_task_exception(GameStuckError('stuck'), 'Dokan')
                    else:
                        self.assertFalse(script._handle_task_exception(GameStuckError('stuck'), 'Dokan'))
                self.assertTrue(script.is_first_task)               # 没有登记成功：不改调度状态

    def test_every_recoverable_branch_registers_then_marks_the_startup_as_over(self):
        for error in RequestedRecoveryTest.RECOVERABLE:
            with self.subTest(error=type(error).__name__):
                self.write_config(restart_due=False)
                script = self.make_script(first=True)
                order = []
                original = Config.task_call

                def spy(config, task=None, force_call=True, _original=original):
                    order.append(('task_call', task, script.is_first_task))
                    return _original(config, task, force_call)

                with patch.object(Config, 'task_call', spy):
                    script._handle_task_exception(error, 'Dokan')
                self.assertEqual(order, [('task_call', 'Restart', True)])   # 登记时还是 True，登记成功之后才改
                self.assertFalse(script.is_first_task)


# ---------------------------------------------------------------------------------------------- 福利道馆
class WelfareRecoveryTest(Fixture):
    """福利开馆前的可恢复异常沿用原恢复路径；已开启对方道馆后的异常仍转人工，不登记 Restart、不重跑福利路线。"""

    def welfare_run(self, world, runner):
        return lambda: runner.run()

    def build_world(self, **kwargs):
        from tests.test_dokan_welfare import make
        world, task, runner, patcher = make(**kwargs)
        self.addCleanup(patcher.stop)
        return world, task, runner

    def test_error_before_opening_goes_through_the_restart_recovery_and_restart_runs(self):
        from tests.test_dokan_welfare import card
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        world, task, runner = self.build_world(remaining=1, cards=[card(str(i), xin=False) for i in range(8)])
        task.swipe = Mock(side_effect=GameTooManyClickError('dokan_welfare_list_up'))      # 找馆翻页触发公共保护
        self.plan.update(Dokan=[self.welfare_run(world, runner), 'stop'], Restart=['ok'])
        self.run_loop(script)
        self.assertEqual(self.ran, ['Dokan', 'Restart', 'Dokan'])
        self.assertEqual(world.opened, [])                           # 开馆之前出的异常，没有开过馆
        self.assertEqual(runner.opened, 0)

    def test_error_after_opening_stays_a_human_takeover_without_any_restart_request(self):
        self.write_config(restart_due=False)
        script = self.make_script(first=True)
        script._loop_fail_before_exit = Mock()
        world, task, runner = self.build_world(remaining=2)
        original = task.screenshot

        def screenshot():
            if world.opened:
                raise GameStuckError('Wait too long')                # 已经点过「确认开启」，现场无法可靠恢复
            original()
        task.screenshot = screenshot
        self.plan.update(Dokan=[self.welfare_run(world, runner)], Restart=['ok'])
        with patch.object(Config, 'task_call', wraps=None) as task_call, self.assertRaises(SystemExit):
            script.loop()
        task_call.assert_not_called()                                # 没有登记 Restart
        self.assertEqual(self.ran, ['Dokan'])                        # Restart 没有运行，福利流程没有重跑
        self.assertEqual(world.opened, ['a'])                        # 只开过一馆，没有误开下一馆
        self.assertEqual(world.kinds('app_start'), [])               # 没有被自动重启
        self.assertTrue(script.is_first_task)


if __name__ == '__main__':
    unittest.main()
