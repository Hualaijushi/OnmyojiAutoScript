# This Python file uses the following encoding: utf-8
"""式神活动体力爬塔随机区间：自动异常恢复边界。

驱动真实的 Script.run（含 _handle_task_exception / task_call('Restart')）、真实 Config 排期和真实
ScriptTask.run；只替身设备、游戏叶节点和随机源。关注的是：异常 → Restart → 再次调度之后，
活动不会被立刻重新拉起并重新随机、从零开始。
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from cached_property import cached_property

from module.config.config import Config
from module.config.config_model import ConfigModel
from module.exception import GamePageUnknownError, GameStuckError, RequestHumanTakeover
from tasks.ActivityShikigami.base_act import ActivityResourceNotEnough
from tasks.ActivityShikigami.config import BATTLE_TYPES
from tasks.ActivityShikigami.script_task import ScriptTask

RANDOM = 'tasks.ActivityShikigami.base_act.random_int'
TASK = 'ActivityShikigami'


class Fixture(TestCase):
    def setUp(self):
        import script as script_mod
        self.script_mod = script_mod
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.tmp = tempfile.mkdtemp(prefix='oas_aprecover_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.chdir(self.tmp)
        os.makedirs('config')
        patch.object(script_mod.logger, 'set_file_logger').start()
        patch.object(Config, 'notifier', Mock(name='notifier')).start()
        manager = Mock(name='fatigue')
        manager.load_factor = 1.0
        manager.enabled = False
        patch.object(script_mod, 'get_fatigue_manager', return_value=manager).start()
        patch.object(script_mod, 'get_behavior_trace', return_value=Mock()).start()
        patch.object(script_mod, 'set_ocr_logging_enabled').start()
        patch.object(script_mod, 'load_module', side_effect=self._load_module).start()
        patch.object(script_mod.Script, 'exception_handler').start()
        patch.object(script_mod.Script, 'save_error_log').start()
        patch.object(script_mod.Script, '_loop_note_recovery').start()
        patch.object(script_mod.Script, '_loop_fail_before_exit').start()
        self.addCleanup(patch.stopall)
        self.started_ago = timedelta(0)   # 本次任务已经运行了多久
        self.created = []          # 每次真正构造出的 ScriptTask
        self.calls = []            # 玩法叶节点调用记录
        self.behaviour = {}        # 命令 -> 叶节点行为
        self.script = None

    # ---- 配置 / Script
    def write_config(self, general, *, others=(), scheduler=None):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                value['scheduler']['enable'] = False
        act = data['activity_shikigami']
        act['scheduler'].update(enable=True, next_run=datetime.now() - timedelta(minutes=1))
        act['general_config'].update(general)
        act['scheduler'].update(scheduler or {})
        for name in ('restart', *others):
            data[name]['scheduler'].update(enable=True, next_run=datetime.now() - timedelta(minutes=1))
        ConfigModel.write_json('simA', data)

    def make_script(self):
        script_mod = self.script_mod
        script = script_mod.Script.__new__(script_mod.Script)
        script.config_name = 'simA'
        script.failure_record = {}
        script.last_task_runtime_outcome = None
        script._fatigue_prepared_for = None
        script._run_ended = False
        script.is_first_task = False
        script.device = Mock(name='device')
        script.device.package = 'pkg'
        self.script = script
        return script

    def reload_config(self):
        """调度器每次失败后都 del_cached_property(config)：模拟，并返回全新的配置对象。"""
        self.script.__dict__.pop('config', None)
        return self.script.config

    def next_task(self):
        """调度器此刻会拉起的任务；下一个任务的时间还没到时返回 None（它会等到那个时间）。"""
        task = self.reload_config().get_next()
        return task.command if task.next_run <= datetime.now() else None

    def run_activity(self, expect_return=None):
        result = self.script.run(TASK)
        if expect_return is not None:
            self.assertEqual(result, expect_return)
        return result

    # ---- ScriptTask 工厂：真实 ScriptTask.run，叶节点按场景替身
    def _load_module(self, name, path):
        command = os.path.basename(os.path.dirname(path))
        if command != TASK:
            behaviour = self.behaviour[command]
            return SimpleNamespace(ScriptTask=lambda config, device: SimpleNamespace(run=behaviour))
        return SimpleNamespace(ScriptTask=self._activity_task)

    def _activity_task(self, config, device):
        t = ScriptTask.__new__(ScriptTask)
        t.config = config
        t.device = device
        t.conf = config.model.activity_shikigami
        t.action_count = {name: 0 for name in BATTLE_TYPES}
        t.ap_target = None
        t.current_action_type = ''
        t.activity_time_reached = False
        t._fatigue_owns_macro_idle = True
        t.start_time = datetime.now() - self.started_ago
        t.before_run = Mock()
        t.goto_page = Mock()
        t.run_rich_man = Mock(side_effect=lambda: self._rich_man(t))
        t.run_fakegod = Mock()
        t.run_climb = Mock(side_effect=lambda: self.behaviour['climb'](t))
        self.created.append(t)
        return t

    def _rich_man(self, t):
        self.calls.append('rich_man')

    @staticmethod
    def battles(t, count):
        """走真实的进场检查 + 计数，就像 _run_climb_action 那样每场一次。"""
        for _ in range(count):
            assert t.prepare_next_action('ap')
            t.record_action('ap')


RANGE = {'task_sequence': '大富翁,爬塔', 'throw_limit': 5, 'ap_limit': 100, 'ap_limit_max': 140}


class InterruptedExecutionTest(Fixture):
    def test_stuck_after_80_battles_does_not_restart_a_new_random_batch(self):
        self.write_config(RANGE)
        self.make_script()

        def climb(t):
            self.calls.append('climb_start')
            self.battles(t, 80)
            raise GameStuckError('卡死')

        self.behaviour['climb'] = climb
        with patch(RANDOM, side_effect=[120, 135]) as rnd:
            self.run_activity(False)
            self.assertEqual(self.created[0].ap_target, 120)
            self.assertEqual(self.created[0].action_count['ap'], 80)

            # 原始异常没有被吞：Script.run 记为失败；Restart 已排队，活动自己被延后
            self.assertIs(self.script.config.__dict__['last_task_delay'].get('activity_shikigami'), False)
            self.assertEqual(self.next_task(), 'Restart')
            config = self.script.config
            activity = config.model.activity_shikigami.scheduler
            self.assertGreaterEqual(activity.next_run, datetime.now() + timedelta(hours=23))

            # Restart 跑完（只恢复环境）之后，再调度多次：活动不会被拉起
            for _ in range(3):
                config.task_delay(task='Restart', success=True)
                config.task_call('Restart')
                config.task_delay(task='Restart', success=True)
                config = self.reload_config()
                self.assertIsNone(self.next_task())
                self.assertGreater(config.model.activity_shikigami.scheduler.next_run, datetime.now())

        self.assertEqual(len(self.created), 1)            # 没有第二个 ScriptTask
        self.assertEqual(rnd.call_count, 1)               # 没有再次抽取
        self.assertEqual(self.calls, ['rich_man', 'climb_start'])   # 前面的玩法没有重跑

    def test_rich_man_done_then_stuck_before_ap_does_not_rerun_the_activity(self):
        self.write_config(RANGE)
        self.make_script()

        def climb(t):
            raise GamePageUnknownError('页面未知')

        self.behaviour['climb'] = climb
        with patch(RANDOM, return_value=120) as rnd:
            self.run_activity(False)
            self.next_task()
            self.script.config.task_delay(task='Restart', success=True)
            self.assertIsNone(self.next_task())
        self.assertEqual(self.calls, ['rich_man'])
        self.assertEqual(rnd.call_count, 1)
        self.assertEqual(len(self.created), 1)

    def test_manual_run_now_after_the_stop_is_a_new_execution(self):
        self.write_config(RANGE)
        self.make_script()
        completed = []

        def climb(t):
            self.battles(t, 3)
            if not completed:
                completed.append(True)
                raise GameStuckError('卡死')

        self.behaviour['climb'] = climb
        with patch(RANDOM, side_effect=[120, 135]) as rnd:
            self.run_activity(False)
            self.assertEqual(rnd.call_count, 1)
            # 用户在 OASX 明确「现在运行」= 把下次运行时间改成现在（也等价于进程重启后重读配置）
            config = self.reload_config()
            config.model.activity_shikigami.scheduler.next_run = datetime.now() - timedelta(seconds=1)
            self.assertEqual(self.reload_config().get_next().command in (TASK, 'Restart'), True)
            self.script.__dict__.pop('config', None)
            self.run_activity()
        self.assertEqual(len(self.created), 2)
        self.assertEqual(rnd.call_count, 2)
        self.assertEqual(self.created[1].ap_target, 135)
        self.assertEqual(self.created[1].action_count['ap'], 3)   # 新执行从 0 开始计数

    def test_normal_completion_schedules_success_and_next_execution_redraws(self):
        self.write_config(RANGE)
        self.make_script()
        self.behaviour['climb'] = lambda t: self.battles(t, 2)
        with patch(RANDOM, side_effect=[110, 130]) as rnd:
            self.run_activity(True)                    # TaskEnd → 正常结束
            self.assertIs(self.script.config.__dict__['last_task_delay'].get('activity_shikigami'), True)
            config = self.reload_config()
            config.model.activity_shikigami.scheduler.next_run = datetime.now() - timedelta(seconds=1)
            self.script.__dict__.pop('config', None)
            self.run_activity(True)
        self.assertEqual([t.ap_target for t in self.created], [110, 130])
        self.assertEqual(rnd.call_count, 2)

    def test_resource_not_enough_and_reentry_inside_one_execution_do_not_redraw(self):
        self.write_config({**RANGE, 'throw_limit': 0, 'task_sequence': '爬塔'})
        self.make_script()

        def climb(t):
            for _ in range(3):                         # 重进挑战页 / 资源不足换下一项都在同一对象内
                t.prepare_next_action('ap')
                try:
                    raise ActivityResourceNotEnough
                except ActivityResourceNotEnough:
                    pass

        self.behaviour['climb'] = climb
        with patch(RANDOM, return_value=120) as rnd:
            self.run_activity(True)
        self.assertEqual(rnd.call_count, 1)


class UnaffectedBehaviourTest(Fixture):
    def test_fixed_ap_count_keeps_the_old_retry_behaviour(self):
        self.write_config({**RANGE, 'ap_limit': 120, 'ap_limit_max': 120})
        self.make_script()

        def climb(t):
            raise GameStuckError('卡死')

        self.behaviour['climb'] = climb
        with patch(RANDOM) as rnd:
            self.run_activity(False)
            # 固定次数没有随机目标：不延后，Restart 之后仍会按原样被重新拉起
            self.assertEqual(self.next_task(), 'Restart')
            self.script.config.task_delay(task='Restart', success=True)
            self.assertEqual(self.next_task(), TASK)
        rnd.assert_not_called()

    def test_legacy_n_config_keeps_the_old_retry_behaviour(self):
        general = {**RANGE, 'ap_limit': 120}
        self.write_config(general)
        data = ConfigModel.read_json('simA')
        data['activity_shikigami']['general_config'].pop('ap_limit_max')
        ConfigModel.write_json('simA', data)
        self.make_script()
        self.behaviour['climb'] = Mock(side_effect=GameStuckError('卡死'))
        self.run_activity(False)
        self.script.config.task_delay(task='Restart', success=True)
        self.assertEqual(self.next_task(), TASK)

    def test_exception_before_any_play_starts_is_not_deferred(self):
        self.write_config(RANGE)
        self.make_script()

        def factory(config, device):
            task = self._activity_task(config, device)
            task.before_run = Mock(side_effect=GameStuckError('卡死'))
            return task

        self.script_mod.load_module.side_effect = lambda n, p: SimpleNamespace(ScriptTask=factory)
        self.run_activity(False)
        self.script.config.task_delay(task='Restart', success=True)
        self.assertEqual(self.next_task(), TASK)

    def test_fatal_exception_keeps_old_behaviour_user_restart_runs_it(self):
        self.write_config(RANGE)
        self.make_script()
        self.behaviour['climb'] = Mock(side_effect=ValueError('bug'))
        with patch(RANDOM, return_value=120), self.assertRaises(SystemExit):
            self.run_activity()
        # exit(1) 的致命错误不会被自动重跑；排期未被改动，用户重新启动进程就是新执行
        self.assertEqual(self.reload_config().model.activity_shikigami.scheduler.next_run.date() <= datetime.now().date(), True)
        self.assertLessEqual(self.script.config.model.activity_shikigami.scheduler.next_run, datetime.now())

    def test_other_task_restart_recovery_is_unchanged(self):
        self.write_config(RANGE, others=('orochi',))
        self.make_script()
        self.behaviour['Orochi'] = Mock(side_effect=GameStuckError('卡死'))
        self.assertFalse(self.script.run('Orochi'))
        config = self.reload_config()
        self.assertEqual(config.get_next().command, 'Restart')       # 仍然 task_call('Restart')
        self.assertLessEqual(config.model.orochi.scheduler.next_run, datetime.now())   # 自己没被延后
        self.assertEqual(len(self.created), 0)


class PostponeBoundaryTest(Fixture):
    """延后排期的时间基准与失败兜底：保护靠「活动的 next_run 落在未来」，做不到就走人工处理。"""

    def interrupt(self):
        """活动在体力打了几场后被卡死异常打断。"""
        def climb(t):
            self.battles(t, 3)
            raise GameStuckError('卡死')

        self.behaviour['climb'] = climb

    def observe_handler(self):
        seen = []
        real = self.script_mod.Script._handle_task_exception

        def handler(script, e, command):
            seen.append(e)
            return real(script, e, command)

        patch.object(self.script_mod.Script, '_handle_task_exception', handler).start()
        return seen

    def assert_never_rerun(self, rnd):
        self.assertEqual(len(self.created), 1)
        self.assertEqual(rnd.call_count, 1)

    def test_long_run_with_short_failure_interval_is_still_in_the_future(self):
        self.started_ago = timedelta(minutes=30)
        self.write_config(RANGE, scheduler={'failure_interval': '00 00:10:00'}, others=('orochi',))
        self.make_script()
        self.interrupt()
        with patch(RANDOM, return_value=120) as rnd:
            self.assertFalse(self.script.run(TASK))
            next_run = self.reload_config().model.activity_shikigami.scheduler.next_run
            # 以中断时刻为基准：约 10 分钟后；若以任务开始时刻为基准会落在 20 分钟前
            self.assertGreater(next_run, datetime.now() + timedelta(minutes=8))
            self.assertLess(next_run, datetime.now() + timedelta(minutes=11))
            self.assertEqual(self.next_task(), 'Restart')
            self.script.config.task_delay(task='Restart', success=True)
            # Restart 之后：其他任务按原调度，活动不被拉起
            self.assertEqual(self.next_task(), 'Orochi')
        self.assert_never_rerun(rnd)

    def test_non_default_server_update_final_schedule_is_in_the_future(self):
        self.started_ago = timedelta(minutes=30)
        self.write_config(RANGE, scheduler={'failure_interval': '00 00:10:00', 'server_update': '04:00:00'})
        self.make_script()
        self.interrupt()
        with patch(RANDOM, return_value=120) as rnd:
            self.assertFalse(self.script.run(TASK))
            next_run = self.reload_config().model.activity_shikigami.scheduler.next_run
            self.assertGreater(next_run, datetime.now())
            # 现有规则：非 09:00 的 server_update 排到下一个服务器更新点
            self.assertEqual(next_run.time().replace(second=0, microsecond=0).isoformat(), '04:00:00')
            self.assertEqual(next_run.date(), (datetime.now() + timedelta(days=1)).date())
            self.script.config.task_delay(task='Restart', success=True)
            self.assertIsNone(self.next_task())
        self.assert_never_rerun(rnd)

    def test_zero_interval_with_default_server_update_stops_for_manual_handling(self):
        self.started_ago = timedelta(minutes=30)
        self.write_config(RANGE, scheduler={'failure_interval': '00 00:00:00'})
        self.make_script()
        self.interrupt()
        seen = self.observe_handler()
        with patch(RANDOM, return_value=120) as rnd, \
                patch.object(Config, 'task_call', autospec=True, side_effect=Config.task_call) as call, \
                self.assertRaises(SystemExit):
            self.script.run(TASK)
        self.assertIsInstance(seen[0], RequestHumanTakeover)
        self.assertIsInstance(seen[0].__cause__, GameStuckError)
        self.assertIn('需要人工处理', str(seen[0]))
        self.assertIn('不在未来', str(seen[0]))
        call.assert_not_called()                      # 没有安排自动 Restart
        self.assert_never_rerun(rnd)

    def test_zero_interval_with_non_default_server_update_is_valid(self):
        self.write_config(RANGE, scheduler={'failure_interval': '00 00:00:00', 'server_update': '04:00:00'})
        self.make_script()
        self.interrupt()
        with patch(RANDOM, return_value=120) as rnd:
            self.assertFalse(self.script.run(TASK))
            self.script.config.task_delay(task='Restart', success=True)
            self.assertIsNone(self.next_task())
        self.assert_never_rerun(rnd)

    def test_save_failure_escalates_instead_of_automatic_restart(self):
        self.write_config(RANGE)
        self.make_script()
        self.interrupt()
        seen = self.observe_handler()
        with patch(RANDOM, return_value=120) as rnd, \
                patch.object(Config, 'task_delay', side_effect=OSError('磁盘不可写')), \
                patch.object(Config, 'task_call', autospec=True, side_effect=Config.task_call) as call, \
                self.assertRaises(SystemExit):
            self.script.run(TASK)
        error = seen[0]
        self.assertIsInstance(error, RequestHumanTakeover)
        self.assertIn('本次体力目标和进度无法可靠恢复', str(error))
        self.assertIn('延后排期写入失败', str(error))
        # 两个原因都可追踪：人工处理 ← 保存失败 ← 原始游戏异常
        self.assertIsInstance(error.__cause__, OSError)
        self.assertIsInstance(error.__cause__.__context__, GameStuckError)
        call.assert_not_called()
        self.assert_never_rerun(rnd)
        # 排期没有被改动（磁盘不可写时没有持久化保护，只能靠当前进程停止）
        self.assertLessEqual(self.reload_config().model.activity_shikigami.scheduler.next_run, datetime.now())

    def test_save_reports_success_but_schedule_is_not_in_the_future(self):
        self.write_config(RANGE)
        self.make_script()
        self.interrupt()
        seen = self.observe_handler()
        with patch(RANDOM, return_value=120) as rnd, \
                patch.object(Config, 'task_delay', return_value=None), \
                patch.object(Config, 'task_call', autospec=True, side_effect=Config.task_call) as call, \
                self.assertRaises(SystemExit):
            self.script.run(TASK)
        self.assertIsInstance(seen[0], RequestHumanTakeover)
        self.assertIsInstance(seen[0].__cause__, GameStuckError)
        call.assert_not_called()
        self.assert_never_rerun(rnd)

    def test_escalation_is_not_success_and_a_manual_start_is_a_new_execution(self):
        self.write_config(RANGE, scheduler={'failure_interval': '00 00:00:00'})
        self.make_script()
        self.interrupt()
        with patch(RANDOM, side_effect=[120, 135]):
            with self.assertRaises(SystemExit):
                self.script.run(TASK)
            self.assertIs(self.script.config.__dict__['last_task_delay'].get('activity_shikigami'), False)
            # 用户修好后重新启动：重新读取配置，活动仍处于到点状态，这是新的一次执行
            self.script.__dict__.pop('config', None)
            self.behaviour['climb'] = lambda t: self.battles(t, 1)
            self.assertTrue(self.script.run(TASK))
        self.assertEqual([t.ap_target for t in self.created], [120, 135])
