# This Python file uses the following encoding: utf-8
"""循环与脚本主流程的衔接：调度钩子、真实 `Script.loop` 的循环步骤前置（疲劳 → 会合 → 门口 → 运行）、
异常处理里的恢复登记、一次性开关、界面停止。

调度钩子用真实的 Function / TaskScheduler；`Script.loop` 用临时目录里的真实 Config 和真实在场文件，
只把模块加载、疲劳管理器、运行时准备换成替身。不碰设备 / 游戏 / OCR。
离线通过不等于真机通过。
"""

import asyncio
import json
import os
import shutil
import tempfile
import time as real_time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from module.config.config import Function
from module.config.config_model import ConfigModel
from module.exception import GameStuckError, ScriptError, TaskEnd
from module.instance_sync.team import PresenceBoard, WAITING, clear_session, get_session
from module.script import loop_controller as lc
from module.script.loop_controller import ACTIVE, FAILED, LoopController, LoopParams
from module.script.team_sync import TeamSync
from tasks.Script.config_optimization import ScheduleRule


class _StopLoop(BaseException):
    """穿过 `Script.loop` 的 `except Exception`，用来结束调度循环。"""


NOW = datetime(2026, 10, 24, 12, 0, 0)


def fn(name, priority=5, minutes_ago=1):
    from module.config.utils import convert_to_underscore
    return Function(convert_to_underscore(name), {'scheduler': {
        'enable': True, 'next_run': datetime.now() - timedelta(minutes=minutes_ago), 'priority': priority}})


def fake_config(rule=ScheduleRule.FILTER, orochi_priority=5, raid_priority=5):
    return SimpleNamespace(model=SimpleNamespace(
        script=SimpleNamespace(optimization=SimpleNamespace(schedule_rule=rule)),
        orochi=SimpleNamespace(scheduler=SimpleNamespace(priority=orochi_priority)),
        realm_raid=SimpleNamespace(scheduler=SimpleNamespace(priority=raid_priority))))


class HookBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_hook_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        self.addCleanup(patch.stopall)
        self.board = PresenceBoard(self.tmp, 'A', 'B')
        self.peer_board = PresenceBoard(self.tmp, 'B', 'A')
        self.ctrl = LoopController('A', rng=Random(1))
        self.ctrl.bind_board(self.board)
        self.ctrl.request_start(LoopParams('leader', 2, 3, 3), self.board)

    def commands(self, items):
        return [f.command for f in items]


class ScheduleHookTest(HookBase):
    def test_ordinary_orochi_and_realm_raid_are_paused_and_only_the_step_is_inserted(self):
        pending = [fn('Orochi'), fn('RealmRaid'), fn('Sougenbi')]
        got_pending, got_waiting = self.ctrl.schedule_hook(fake_config(), pending, [fn('RealmRaid', minutes_ago=-5)])
        self.assertEqual(self.commands(got_pending), ['Orochi'])            # 同级以下的 Sougenbi 不插入
        self.assertEqual(self.commands(got_waiting), [])

    def test_only_strictly_higher_tasks_are_inserted_before_the_step(self):
        pending = [fn('Orochi'), fn('KekkaiUtilize'), fn('DailyTrifles'), fn('Sougenbi'), fn('EternitySea')]
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), pending, [])
        # 默认规则按固定顺序：KekkaiUtilize、DailyTrifles 排在 Orochi 前面；之后的不插入
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize', 'DailyTrifles', 'Orochi'])

    def test_raid_step_has_a_different_boundary_and_runs_even_when_its_own_switch_is_off(self):
        self.ctrl.loop['idx'] = 1                                          # 个人突破
        pending = [fn('KekkaiUtilize'), fn('DailyTrifles'), fn('Orochi')]    # RealmRaid 开关关闭：不在列表里
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), pending, [])
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize', 'RealmRaid'])
        self.assertTrue(got_pending[-1].enable)

    def test_restart_is_always_allowed_even_if_ranked_below_the_step(self):
        pending = [fn('Orochi'), fn('Restart')]
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), pending, [])
        self.assertEqual(self.commands(got_pending), ['Restart', 'Orochi'])

    def test_priority_rule_never_inserts_same_priority_tasks(self):
        pending = [fn('Orochi', 5), fn('DailyTrifles', 5), fn('KekkaiUtilize', 4), fn('Sougenbi', 6)]
        got_pending, _ = self.ctrl.schedule_hook(fake_config(ScheduleRule.PRIORITY), pending, [])
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize', 'Orochi'])

    def test_fifo_rule_has_no_priority_so_only_recovery_is_inserted(self):
        pending = [fn('KekkaiUtilize', minutes_ago=30), fn('Restart', minutes_ago=2), fn('Orochi')]
        got_pending, _ = self.ctrl.schedule_hook(fake_config(ScheduleRule.FIFO), pending, [])
        self.assertEqual(self.commands(got_pending), ['Restart', 'Orochi'])

    def test_blocked_by_unrecovered_tasks_shows_no_step_and_waits_for_them(self):
        self.ctrl.unrecovered.add('KekkaiUtilize')
        waiting = [fn('KekkaiUtilize', minutes_ago=-3), fn('Sougenbi', minutes_ago=-1)]
        got_pending, got_waiting = self.ctrl.schedule_hook(fake_config(), [fn('Orochi')], waiting)
        self.assertEqual(self.commands(got_pending), [])
        self.assertEqual(self.commands(got_waiting), ['KekkaiUtilize'])

    def test_blocked_with_nothing_runnable_waits_instead_of_falling_back_to_the_original_tasks(self):
        # 恢复 / 未恢复任务挡住时，不能把原始列表还给调度器：普通御魂和低优先级任务会绕过阻塞
        self.ctrl.recovery_pending = True
        pending, waiting = [fn('Sougenbi'), fn('Orochi'), fn('RealmRaid')], [fn('Orochi', minutes_ago=-4)]
        got_pending, got_waiting = self.ctrl.schedule_hook(fake_config(), pending, waiting)
        self.assertEqual(got_pending, [])
        self.assertEqual(len(got_waiting), 1)                                # 一个远在未来的占位项：调度器有东西可等
        self.assertGreater(got_waiting[0].next_run, datetime.now() + timedelta(minutes=30))

    def test_placeholder_wait_goes_through_the_real_scheduler_without_error(self):
        from module.config.config import Config
        self.ctrl.unrecovered.add('KekkaiUtilize')
        config = Config.__new__(Config)
        config.model = ConfigModel()
        config.model.running_task = ''
        for key, value in config.model.model_dump().items():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                getattr(config.model, key).scheduler.enable = key in ('orochi', 'sougenbi')
                getattr(config.model, key).scheduler.next_run = datetime.now() - timedelta(minutes=1)
        config.__dict__['scheduler_hook'] = self.ctrl.schedule_hook
        task = Config.get_next(config)                                       # 不会因为「没有任何任务」而抛 RequestHumanTakeover
        self.assertGreater(task.next_run, datetime.now() + timedelta(minutes=30))
        self.assertEqual(config.pending_task, [])                            # 普通御魂 / 低优先级任务没有被放行

    def test_recovery_task_runs_first_even_when_ranked_below_the_step(self):
        self.ctrl.recovery_pending = True
        for rule in (ScheduleRule.PRIORITY, ScheduleRule.FIFO, ScheduleRule.FILTER):
            pending = [fn('Orochi', 5), fn('Restart', 9, minutes_ago=1), fn('Sougenbi', 5)]
            got_pending, _ = self.ctrl.schedule_hook(fake_config(rule), pending, [])
            self.assertEqual(self.commands(got_pending), ['Restart'], rule)

    def test_recovery_task_is_not_dropped_by_the_priority_filter_when_the_step_is_inserted(self):
        pending = [fn('Orochi', 5), fn('Restart', 9)]
        got_pending, _ = self.ctrl.schedule_hook(fake_config(ScheduleRule.PRIORITY), pending, [])
        self.assertEqual(self.commands(got_pending), ['Restart', 'Orochi'])

    def test_without_a_live_loop_the_schedule_is_untouched(self):
        self.ctrl.fail('x')
        pending, waiting = [fn('Orochi'), fn('RealmRaid')], [fn('Sougenbi', minutes_ago=-1)]
        got_pending, got_waiting = self.ctrl.schedule_hook(fake_config(), pending, waiting)
        self.assertIs(got_pending, pending)
        self.assertIs(got_waiting, waiting)

    def test_waiting_for_the_peer_to_finish_stays_inside_the_loop_and_does_not_release_lower_tasks(self):
        self.ctrl.loop['idx'] = self.ctrl.last_idx
        self.ctrl.loop['done_idx'] = self.ctrl.last_idx                      # 最后一步（个人突破）我这边已完成
        self.assertIsNone(self.ctrl.current_step())
        self.assertTrue(self.ctrl.live)
        pending = [fn('Orochi'), fn('KekkaiUtilize'), fn('DailyTrifles'), fn('Sougenbi')]
        waiting = [fn('Sougenbi', minutes_ago=-1), fn('KekkaiUtilize', minutes_ago=-2)]
        got_pending, got_waiting = self.ctrl.schedule_hook(fake_config(), pending, waiting)
        # 参照最后一步（个人突破）：只放行位次更高的任务；DailyTrifles / Sougenbi 排在它后面，不放行；不注入任何步骤
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize'])
        self.assertEqual(self.commands(got_waiting), ['KekkaiUtilize'])

    def test_waiting_for_the_peer_with_nothing_higher_uses_the_placeholder(self):
        self.ctrl.loop['idx'] = self.ctrl.last_idx
        self.ctrl.loop['done_idx'] = self.ctrl.last_idx
        got_pending, got_waiting = self.ctrl.schedule_hook(
            fake_config(), [fn('Orochi'), fn('Sougenbi')], [fn('Sougenbi', minutes_ago=-1)])
        self.assertEqual(got_pending, [])
        self.assertEqual(len(got_waiting), 1)
        self.assertGreater(got_waiting[0].next_run, datetime.now() + timedelta(minutes=30))


class ReadyWithdrawalTest(HookBase):
    """A 已发布 ready 又让出去做别的：B 不能凭旧的 ready 放行。"""

    def setUp(self):
        super().setUp()
        self.peer = LoopController('B', rng=Random(2))
        self.peer.bind_board(self.peer_board)
        self.peer.request_start(LoopParams('member', 2, 3, 3), self.peer_board)
        for _ in range(3):
            self.peer.tick()
            self.ctrl.tick()
        self.assertEqual((self.ctrl.state, self.peer.state), (ACTIVE, ACTIVE))

    def test_peer_is_released_by_a_stale_ready_without_the_withdrawal(self):
        self.assertEqual(self.ctrl.barrier(), 'wait')                        # A 先就绪
        self.assertTrue(self.ctrl.loop['ready'])
        self.assertEqual(self.peer.barrier(), 'go')                          # B 看到 A 就绪就放行（正常）

    def test_withdrawn_ready_keeps_the_peer_waiting_until_the_step_is_ready_again(self):
        self.ctrl.barrier()
        self.ctrl.abandon_run()                                              # A 让出去做高优先级任务
        self.assertFalse(self.ctrl.loop['ready'])
        self.assertFalse(self.peer_board.read_peer() is None)
        self.assertEqual(self.peer.barrier(), 'wait')                        # B 不能凭旧 ready 开始
        self.assertEqual(self.ctrl.barrier(), 'go')                          # A 回来重新就绪（B 已就绪）
        self.assertTrue(self.ctrl.loop['ready'])

    def test_withdraw_then_peer_polls_interleaved_never_releases_on_the_old_ready(self):
        import threading
        for _ in range(30):
            self.ctrl.barrier()
            seen_after = []
            stop = threading.Event()
            withdrawn = threading.Event()

            def poll():
                while not stop.is_set():
                    verdict = self.peer.barrier()
                    if withdrawn.is_set():
                        seen_after.append(verdict)

            thread = threading.Thread(target=poll, daemon=True)
            thread.start()
            self.ctrl.abandon_run()
            withdrawn.set()
            self.peer.barrier()                                              # 撤回完成之后至少再读一次
            stop.set()
            thread.join(timeout=5)
            # 撤回完成之后的读取（B 的轮询线程可能有一次读取横跨撤回，所以只看最后一次）
            self.assertEqual(self.peer.barrier(), 'wait')
            self.ctrl.loop['ready'] = False

    def test_a_started_step_is_never_preempted_and_keeps_its_ready(self):
        self.ctrl.barrier()
        self.peer.barrier()
        self.assertEqual(self.ctrl.barrier(), 'go')
        self.assertTrue(self.ctrl.begin_run())
        self.ctrl.withdraw_ready()                                           # 已经开始的步骤：撤回不生效
        self.assertTrue(self.ctrl.loop['ready'])
        self.assertTrue(self.ctrl.in_step)

    def test_withdraw_without_a_live_loop_is_harmless(self):
        self.ctrl.fail('x')
        self.ctrl.withdraw_ready()
        self.assertEqual(self.ctrl.state, FAILED)


class TeamTaskArbitrationTest(HookBase):
    def peer_view(self, task_rank, step_rank):
        self.peer_board.publish(
            'idle', {'KekkaiUtilize': {'role': 'leader', 'enable': True, 'next_run': NOW, 'rank': task_rank}})
        self.peer_board.set_loop({'id': 'x', 'state': 'ACTIVE', 'step_rank': step_rank, 'step_task': 'Orochi',
                                  'role': 'member'})

    def test_task_is_inserted_only_when_both_sides_rank_it_above_their_step(self):
        self.peer_view(task_rank=3, step_rank=20)
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), [fn('KekkaiUtilize'), fn('Orochi')], [])
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize', 'Orochi'])
        self.assertEqual(self.ctrl.pop_deferred(), [])

    def test_task_is_postponed_when_the_peer_does_not_rank_it_higher(self):
        self.peer_view(task_rank=30, step_rank=20)
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), [fn('KekkaiUtilize'), fn('Orochi')], [])
        self.assertEqual(self.commands(got_pending), ['Orochi'])             # 不强行插入
        self.assertEqual(self.ctrl.pop_deferred(), ['KekkaiUtilize'])

    def test_peer_without_the_task_enabled_keeps_the_existing_postpone_rule(self):
        self.peer_board.publish('idle', {})
        self.peer_board.set_loop({'id': 'x', 'state': 'ACTIVE', 'step_rank': 5, 'step_task': 'Orochi', 'role': 'member'})
        got_pending, _ = self.ctrl.schedule_hook(fake_config(), [fn('KekkaiUtilize'), fn('Orochi')], [])
        self.assertEqual(self.commands(got_pending), ['KekkaiUtilize', 'Orochi'])      # 由门口的既有规则去推迟


class ExceptionRecordingTest(unittest.TestCase):
    """`_handle_task_exception` 里登记恢复，要在 task_call('Restart') 之前。"""

    def setUp(self):
        import script as script_mod
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_exc_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        self.addCleanup(patch.stopall)
        self.board = PresenceBoard(self.tmp, 'A', 'B')
        self.script = script_mod.Script.__new__(script_mod.Script)
        self.order = []
        self.config = SimpleNamespace(
            task_call=Mock(side_effect=lambda *a, **k: self.order.append('task_call')),
            notifier=Mock(), task_runtime_outcome=None,
            model=SimpleNamespace(restart=SimpleNamespace(scheduler=SimpleNamespace(enable=True))))
        self.script.__dict__['config'] = self.config
        self.script.config_name = 'simA'
        self.script.last_task_runtime_outcome = None
        self.script.device = SimpleNamespace(package='pkg', sleep=Mock())
        self.script.save_error_log = Mock()
        self.script.exception_handler = Mock()
        ctrl = LoopController('simA', rng=Random(1))
        ctrl.bind_board(self.board)
        ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)
        ctrl.loop['state'] = ACTIVE
        self.script.__dict__['loop_controller'] = ctrl
        self.ctrl = ctrl
        original = ctrl.note_recovery
        ctrl.note_recovery = Mock(side_effect=lambda *a, **k: (self.order.append('note'), original(*a, **k))[1])

    def test_restart_branches_register_the_recovery_before_calling_restart(self):
        from module.exception import GameBugError, GameNotRunningError, GamePageUnknownError
        for exc in (GameStuckError('x'), GameBugError('x'), GamePageUnknownError('x'), GameNotRunningError('x')):
            self.order.clear()
            self.ctrl.recovery_pending = False
            self.script._handle_task_exception(exc, 'Orochi')
            self.assertEqual(self.order, ['note', 'task_call'], type(exc).__name__)
            self.assertTrue(self.ctrl.recovery_pending)
            self.config.task_call.assert_called_with('Restart')

    def test_restart_disabled_stops_the_loop_instead_of_waiting_forever(self):
        self.config.model.restart.scheduler.enable = False
        self.script._handle_task_exception(GameStuckError('x'), 'Orochi')
        self.assertEqual(self.ctrl.state, FAILED)
        self.assertEqual(self.ctrl.loop['reason'], 'restart_disabled')

    def test_task_end_marks_the_run_as_ended_normally(self):
        self.script._run_ended = False
        self.assertTrue(self.script._handle_task_exception(TaskEnd(), 'RealmRaid'))
        self.assertTrue(self.script._run_ended)

    def test_exception_is_not_a_normal_end(self):
        self.script._run_ended = False
        self.script._handle_task_exception(GameStuckError('x'), 'RealmRaid')
        self.assertFalse(self.script._run_ended)

    def test_fatal_exit_tells_the_peer_first(self):
        with self.assertRaises(SystemExit):
            self.script._handle_task_exception(ScriptError('boom'), 'Orochi')
        self.assertEqual(self.ctrl.state, FAILED)
        self.assertEqual(self.ctrl.loop['reason'], 'process_exit')
        self.assertEqual(self.board.snapshot()['loop']['state'], FAILED)


class _FakeTime:
    """代理 time 模块，只把 sleep 换掉。"""

    def __init__(self, sleep):
        self.sleep = sleep

    def __getattr__(self, name):
        return getattr(real_time, name)


class ScriptFixture(unittest.TestCase):
    """真实 Script + 真实 Config + 真实在场文件；对方是另一个进程的替身（板子 + 控制器）。"""

    def setUp(self):
        import script as script_mod
        from module.config.config import Config
        from module.script import ScriptRuntimeDecision
        self.script_mod = script_mod
        self._cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_script_')
        os.chdir(self.tmp)
        os.makedirs('config')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.chdir, self._cwd)
        patch.object(script_mod.logger, 'set_file_logger').start()
        patch.object(script_mod, 'IS_WINDOWS', False).start()
        patch.object(Config, 'notifier', Mock(name='notifier')).start()
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        patch.object(script_mod, 'LOOP_POLL_INTERVAL', 0).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(clear_session, 'simA')
        self.ran = []
        self.seen = {}
        self.manager = Mock(name='fatigue')
        self.manager.load_factor = 1.0
        self.manager.enabled = False
        self.manager.task_identity = None
        patch.object(script_mod, 'get_fatigue_manager', return_value=self.manager).start()
        patch.object(script_mod, 'load_module', side_effect=self._module).start()
        self.decision_ready = ScriptRuntimeDecision.READY
        self.sleeps = []

    def _module(self, name, path):
        command = Path(path).parent.name

        def run():
            self.ran.append(command)
            controller = self.script.loop_controller
            self.seen = {'in_step': controller.in_step, 'session': get_session('simA', command),
                         'begin_calls': self.manager.begin_task.call_count,
                         'break_calls': self.manager.try_break.call_count}
            raise _StopLoop

        return SimpleNamespace(ScriptTask=lambda config, device: SimpleNamespace(run=run))

    def write_config(self, *, enable=(), orochi_enable=False, tweak=None):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                value['scheduler']['enable'] = False
        for key in enable:
            data[key]['scheduler'].update(enable=True, next_run=datetime.now() - timedelta(minutes=1))
        data['orochi']['scheduler']['enable'] = orochi_enable            # 普通排期的开关关着也要能作为循环步骤
        data['orochi']['orochi_config']['user_status'] = 'leader'
        data['orochi']['loop_config'].update(rounds=1, target_min=2, target_max=2)
        data['script']['team_sync'] = {'enable': True, 'peer_instance': 'peerX'}
        if tweak is not None:
            tweak(data)
        ConfigModel.write_json('simA', data)

    def write_peer_config(self, tweak=None):
        """对方实例 peerX 自己的配置：同样开组队同步，peer 指向 simA。"""
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        for value in data.values():
            if isinstance(value, dict) and isinstance(value.get('scheduler'), dict):
                value['scheduler']['enable'] = False
        data['script']['team_sync'] = {'enable': True, 'peer_instance': 'simA'}
        if tweak is not None:
            tweak(data)
        ConfigModel.write_json('peerX', data)

    def make_script(self):
        script = self.script_mod.Script.__new__(self.script_mod.Script)
        script.team_sync = TeamSync('simA', started_at=datetime.now() - timedelta(minutes=10))
        script.server = script.state_queue = script.command_queue = script.gui_update_task = None
        script._emulator_down = False
        script.is_first_task = False
        script.config_name = 'simA'
        script.failure_record = {}
        script.last_task_runtime_outcome = None
        script.loop_thread = None
        script.device = Mock(name='device')
        script.runtime = Mock(name='runtime')
        script.runtime.prepare_task_execution.return_value = self.decision_ready
        script.runtime.handle_wait_during_idle.side_effect = _StopLoop
        self.script = script
        return script

    def start_loop(self, script, peer_ready):
        """脚本这边是队长；对方（peerX）是队员，已经加入，peer_ready 时已经在 Orochi 门口等。"""
        board = script.team_sync._board(script.config)
        self.peer_board = PresenceBoard(script.team_sync.root, 'peerX', 'simA')
        self.peer = LoopController('peerX', rng=Random(2))
        self.peer.bind_board(self.peer_board)
        script.loop_controller.bind_board(board)
        script.loop_controller.request_start(LoopParams('leader', 1, 2, 2), board)
        self.peer.request_start(LoopParams('member', 1, 2, 2), self.peer_board)
        for _ in range(3):
            self.peer.tick()
            script.loop_controller.tick()
        self.assertEqual(script.loop_controller.state, ACTIVE)
        if peer_ready:
            self.peer.barrier()
            self.peer_board.publish(WAITING, {'Orochi': {'role': 'member', 'enable': True, 'next_run': datetime.now()}},
                                    task='Orochi', role='member', token='peer-token', since=datetime.now())



class ScriptLoopStepTest(ScriptFixture):
    def test_step_runs_only_after_fatigue_and_rendezvous_even_with_the_ordinary_switch_off(self):
        self.write_config(enable=())                                  # 只有循环，没有任何普通任务启用
        script = self.make_script()
        self.start_loop(script, peer_ready=True)
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Orochi'])
        self.assertTrue(self.seen['in_step'])
        self.assertIsNotNone(self.seen['session'])                    # 经过现有的组队门口会合
        # 疲劳：会合前检查过一次，Script.run 里没有重复初始化
        self.assertEqual(self.seen['break_calls'], 1)
        self.assertEqual(self.seen['begin_calls'], 1)
        self.manager.begin_task.assert_called_once_with('Orochi', load_factor=1.0, restart=True)
        self.manager.try_break.assert_called_once_with(safe=True)

    def test_first_battle_is_blocked_until_the_peer_joins_the_same_step(self):
        self.write_config()
        script = self.make_script()
        self.start_loop(script, peer_ready=False)                     # 对方已加入但还没在这一步就绪
        sleeps = []
        fake = _FakeTime(lambda seconds: (sleeps.append(seconds), (_ for _ in ()).throw(_StopLoop))[1])
        with patch.object(self.script_mod, 'time', fake), self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, [])
        self.assertTrue(sleeps)
        self.assertEqual(self.manager.try_break.call_count, 1)        # 先疲劳检查，再等对方
        self.assertFalse(script.loop_controller.in_step)

    def test_long_wait_pushes_one_notice_and_keeps_waiting(self):
        self.write_config()
        script = self.make_script()
        self.start_loop(script, peer_ready=False)
        script._loop_notify = Mock()
        ticks = iter([0.0, 4000.0, 8000.0, 9000.0])
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                raise _StopLoop

        fake = _FakeTime(sleep)
        fake.monotonic = lambda: next(ticks)
        with patch.object(self.script_mod, 'time', fake), self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(script._loop_notify.call_count, 1)             # 只提醒一次
        self.assertEqual(len(sleeps), 3)                                # 没有因此放弃等待
        self.assertEqual(self.ran, [])

    def test_yield_withdraws_the_published_ready_so_the_peer_cannot_start_on_it(self):
        self.write_config(enable=())
        script = self.make_script()
        self.start_loop(script, peer_ready=False)                     # 对方还没就绪：我先就绪并等它
        calls = []

        def sleep(seconds):
            calls.append(seconds)
            if len(calls) == 1:
                model = script.config.model
                model.kekkai_utilize.scheduler.enable = True
                model.kekkai_utilize.scheduler.next_run = datetime.now() - timedelta(minutes=1)
                script.config.save()
                return
            raise _StopLoop

        with patch.object(self.script_mod, 'time', _FakeTime(sleep)), self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['KekkaiUtilize'])
        self.assertFalse(script.loop_controller.loop['ready'])                       # 让出时撤回
        self.assertFalse(self.peer_board.read_peer()['loop']['step_task'] is None)
        self.assertFalse(PresenceBoard(script.team_sync.root, 'peerX', 'simA').read_peer()['loop']['ready'])
        self.assertEqual(self.peer.barrier(), 'wait')                                # 对方不能凭旧 ready 开始

    def test_a_step_that_already_started_is_not_preempted_by_a_later_high_priority_task(self):
        self.write_config(enable=())
        script = self.make_script()
        self.start_loop(script, peer_ready=True)
        script._loop_should_yield = Mock(return_value=True)
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Orochi'])                        # 双方就绪后直接开始，不再看是否让出
        script._loop_should_yield.assert_not_called()

    def test_ordinary_orochi_gate_does_not_pull_or_meet_a_loop_step(self):
        """对方在循环里的 Orochi 门口等；我这边普通的 Orochi 到点，不能被拉进去也不能会合。"""
        self.write_config(enable=('orochi',), orochi_enable=True)
        script = self.make_script()
        self.start_loop(script, peer_ready=True)
        script.loop_controller.fail('test')                           # 本方循环已结束：Orochi 回到普通排期
        self.assertIsNone(script.team_sync.peer_request(script.config))
        self.assertIsNone(script.team_sync.answer(script.config))
        script.team_sync.board = script.team_sync._board(script.config)
        decision = script.team_sync.gate(script.config, 'Orochi', should_abort=lambda: True)
        self.assertEqual(decision.reason, 'peer_in_loop')

    def test_higher_priority_task_becoming_due_while_waiting_runs_before_the_step(self):
        self.write_config(enable=())
        script = self.make_script()
        self.start_loop(script, peer_ready=False)
        calls = []

        def sleep(seconds):
            calls.append(seconds)
            if len(calls) == 1:                                       # 等待期间 KekkaiUtilize 到点了
                model = script.config.model
                model.kekkai_utilize.scheduler.enable = True
                model.kekkai_utilize.scheduler.next_run = datetime.now() - timedelta(minutes=1)
                script.config.save()                                  # 配置到点是落在文件里的，重载后仍然在
                return
            raise _StopLoop

        with patch.object(self.script_mod, 'time', _FakeTime(sleep)), self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['KekkaiUtilize'])                 # 先跑更高优先级任务，御魂步骤没有开战
        self.assertFalse(script.loop_controller.in_step)


class RecoveryScheduleTest(ScriptFixture):
    def test_restart_requested_by_an_exception_is_not_skipped_as_the_startup_restart(self):
        from module.exception import GameNotRunningError
        self.write_config(enable=(), tweak=lambda d: d['restart']['scheduler'].update(enable=True))
        script = self.make_script()
        script.is_first_task = True                                   # 这是脚本启动后的第一个任务
        script.exception_handler = Mock()
        self.start_loop(script, peer_ready=False)
        calls = []

        def prepare(task):
            calls.append(task)
            if len(calls) == 1:
                raise GameNotRunningError('adb disconnected')        # 首个任务的准备阶段就要 Restart
            return self.decision_ready

        script.runtime.prepare_task_execution.side_effect = prepare
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Restart'])                       # Restart 真的运行了，没有被「Skip first restart」吃掉
        self.assertFalse(script.is_first_task is True)
        self.assertTrue(script.loop_controller.recovery_pending)
        self.assertEqual(calls[0], 'Orochi')

    def test_plain_first_task_behaviour_is_unchanged_without_a_live_loop(self):
        self.write_config(enable=('orochi',), orochi_enable=True)
        script = self.make_script()
        script.is_first_task = True
        script.config.model.restart.scheduler.enable = True
        script._loop_note_recovery()                                  # 没有活动循环：不登记，也不改 is_first_task
        self.assertTrue(script.is_first_task)
        self.assertFalse(script.loop_controller.recovery_pending)

    def test_nothing_runnable_during_recovery_keeps_waiting_in_the_loop_path(self):
        self.write_config(enable=('orochi', 'sougenbi'), orochi_enable=True)
        script = self.make_script()
        self.start_loop(script, peer_ready=False)
        script.loop_controller.recovery_pending = True                # Restart 还没跑完
        script.config.model.restart.scheduler.enable = False          # 没有可运行的恢复任务
        sleeps = []
        with patch.object(self.script_mod, 'time', _FakeTime(lambda seconds: sleeps.append(seconds) or (_ for _ in ()).throw(_StopLoop))), \
                self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, [])                                # 普通御魂 / 低优先级任务没有绕过阻塞
        self.assertTrue(sleeps)                                       # 走的是循环的明确等待路径


class BetaArbitrationAcrossBothSidesTest(ScriptFixture):
    """B 先在组队任务 X 的门口，A 随后才进入循环 / 发布步骤位次：走两侧真实的调用链。"""

    def sides(self, task_key, a_role, b_role):
        def tweak_a(data):
            data[task_key]['scheduler'].update(enable=True, next_run=datetime.now() + timedelta(hours=5))
            for group in data[task_key].values():
                if isinstance(group, dict) and 'user_status' in group:
                    group['user_status'] = a_role

        def tweak_b(data):
            data[task_key]['scheduler'].update(enable=True, next_run=datetime.now() - timedelta(minutes=1))
            for group in data[task_key].values():
                if isinstance(group, dict) and 'user_status' in group:
                    group['user_status'] = b_role

        self.write_config(tweak=tweak_a)
        self.write_peer_config(tweak_b)
        script = self.make_script()
        from module.config.config import Config
        config_b = Config('peerX')
        team_b = TeamSync('peerX', root=script.team_sync.root, started_at=datetime.now() - timedelta(minutes=10),
                          sleep=Mock())
        # A 平时就在线（空闲、没进循环）：B 到门口时能读到 A 的在场文件
        script.team_sync.on_schedule(script.config, 'Orochi', datetime.now() + timedelta(hours=5))
        return script, config_b, team_b

    def a_enters_the_loop_and_publishes(self, script):
        board = script.team_sync._board(script.config)
        script.loop_controller.bind_board(board)
        script.loop_controller.request_start(LoopParams('leader', 1, 2, 2), board)
        script._loop_prepare_schedule()
        script.team_sync.on_schedule(script.config, 'Orochi', datetime.now())

    def test_x_that_a_ranks_lower_than_its_step_is_postponed_by_the_waiting_side(self):
        script, config_b, team_b = self.sides('bondling_fairyland', 'handoff2', 'handoff1')

        waits = []

        def b_sleeps(seconds):
            waits.append(seconds)
            if len(waits) > 6:
                raise _StopLoop                                        # 兜底：不能让门口无限等下去
            if not getattr(self, 'a_joined', False):
                self.a_joined = True                                   # B 已经在门口等了一轮，A 这时才进入循环并发布位次
                self.a_enters_the_loop_and_publishes(script)

        team_b.sleep = b_sleeps
        decision = team_b.gate(config_b, 'BondlingFairyland', should_abort=lambda: False)
        self.assertEqual((decision.action, decision.reason), ('postpone', 'peer_ranks_lower'))
        self.assertTrue(self.a_joined)
        self.assertGreater(decision.until, datetime.now())            # 按既有的让路间隔推迟，不是无限等 A

    def test_x_that_both_rank_higher_keeps_waiting_and_a_yields_to_it_at_the_boundary(self):
        script, config_b, team_b = self.sides('exploration', 'member', 'leader')
        self.a_enters_the_loop_and_publishes(script)
        # B 到门口等：A 认为 Exploration 严格高于御魂，所以不推迟，继续等
        sleeps = []

        def stop(seconds):
            sleeps.append(seconds)
            raise _StopLoop

        team_b.sleep = stop
        with self.assertRaises(_StopLoop):
            team_b.gate(config_b, 'Exploration', should_abort=lambda: False)
        self.assertTrue(sleeps)
        # A 在步骤边界（会合等待中）把它拉到现在并让出
        self.assertTrue(script._loop_should_yield('Orochi'))
        self.assertIn('Exploration', [f.command for f in script.config.pending_task])

    def test_x_ranked_lower_by_a_is_not_pulled_into_a(self):
        script, config_b, team_b = self.sides('bondling_fairyland', 'handoff2', 'handoff1')
        self.a_enters_the_loop_and_publishes(script)
        board_b = team_b._board(config_b)
        board_b.publish('waiting', {'BondlingFairyland': {'role': 'handoff1', 'enable': True,
                                                        'next_run': datetime.now()}},
                        task='BondlingFairyland', role='handoff1', token='tb', since=datetime.now())
        self.assertIsNone(script.team_sync.peer_request(script.config))              # 位次不高于步骤：不拉
        self.assertFalse(script._loop_should_yield('Orochi'))

    def test_loop_step_door_and_ordinary_rendezvous_stay_compatible(self):
        """同一循环双方的御魂门口照常会合（回归）。"""
        self.write_config(enable=())
        script = self.make_script()
        self.start_loop(script, peer_ready=True)
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ran, ['Orochi'])


class ConsumeRequestTest(ScriptFixture):
    def test_switch_is_consumed_once_and_creates_exactly_one_loop(self):
        self.write_config()
        data = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        data['orochi']['loop_config']['start_loop'] = True
        Path('config', 'simA.json').write_text(json.dumps(data), encoding='utf-8')
        script = self.make_script()
        script._loop_consume_request()
        first = script.loop_controller.loop['id']
        self.assertEqual(script.loop_controller.state, 'FORMING')
        saved = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['orochi']['loop_config']['start_loop'])         # 自动关回
        # 再打开一次：已有活动循环，不排出第二个
        script.config.model.orochi.loop_config.start_loop = True
        script._loop_consume_request()
        self.assertEqual(script.loop_controller.loop['id'], first)
        self.assertFalse(script.config.model.orochi.loop_config.start_loop)

    def test_invalid_request_is_consumed_and_reported_without_creating_a_loop(self):
        self.write_config()
        data = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        data['orochi']['loop_config']['start_loop'] = True
        data['orochi']['orochi_config']['user_status'] = 'alone'
        Path('config', 'simA.json').write_text(json.dumps(data), encoding='utf-8')
        script = self.make_script()
        script._loop_consume_request()
        self.assertIsNone(script.loop_controller.loop)
        saved = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['orochi']['loop_config']['start_loop'])

    def test_request_is_refused_when_team_sync_is_not_usable(self):
        self.write_config()
        data = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        data['orochi']['loop_config']['start_loop'] = True
        data['script']['team_sync'] = {'enable': True, 'peer_instance': 'simA'}      # 填了自己
        Path('config', 'simA.json').write_text(json.dumps(data), encoding='utf-8')
        script = self.make_script()
        script._loop_consume_request()
        self.assertIsNone(script.loop_controller.loop)

    def test_ordinary_orochi_run_never_creates_a_loop(self):
        self.write_config(enable=('orochi',), orochi_enable=True)
        script = self.make_script()
        script._loop_prepare_schedule()
        self.assertIsNone(script.loop_controller.loop)
        self.assertFalse(script.loop_controller.is_step('Orochi'))


class StopProcessTest(unittest.TestCase):
    """ScriptProcess.stop：有活动循环时先通知，再终止；没有时保持原样。"""

    def setUp(self):
        self._cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='oas_loop_stop_')
        os.chdir(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.chdir, self._cwd)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        patch.object(lc, 'STOP_ACK_TIMEOUT', 0.4).start()
        patch.object(lc, 'STOP_ACK_POLL', 0.02).start()
        self.addCleanup(patch.stopall)
        from module.server.script_process import ScriptProcess
        self.events = []
        proc = SimpleNamespace(pid=4242, is_alive=lambda: True, terminate=lambda: self.events.append('terminate'))
        self.sp = ScriptProcess.__new__(ScriptProcess)
        self.sp.config_name = 'simA'
        self.sp._process = proc
        self.sp.state = 1
        self.sp.broadcast_state = AsyncMock()
        self.sp._default_fatigue_state = lambda: {}
        self.sp.command_queue = SimpleNamespace(put=lambda command: self.events.append(('put', command)))
        root = Path('log', 'instance_sync')
        self.board = PresenceBoard(root, 'simA', 'peerX')
        self.board.pid = 4242
        self.ctrl = LoopController('simA', rng=Random(1))
        self.ctrl.bind_board(self.board)

    def stop(self):
        asyncio.run(self.sp.stop())

    def test_no_loop_terminates_immediately_without_any_command(self):
        self.board.publish('idle', {})
        self.stop()
        self.assertEqual(self.events, ['terminate'])
        self.assertIsNone(self.sp._process)

    def test_active_loop_is_cancelled_by_the_child_before_terminate(self):
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)
        self.sp.command_queue = SimpleNamespace(
            put=lambda command: (self.events.append('put'), self.ctrl.cancel_by_command(command)))
        self.stop()
        self.assertEqual(self.events, ['put', 'terminate'])
        self.assertEqual(self.ctrl.state, 'CANCELLED')
        self.assertEqual(json.loads(Path('log/instance_sync/team/simA.json').read_text(encoding='utf-8'))
                         ['loop']['state'], 'CANCELLED')

    def test_unresponsive_child_still_gets_terminated_after_a_bounded_wait(self):
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)
        started = real_time.time()
        self.stop()
        self.assertEqual([e if isinstance(e, str) else e[0] for e in self.events], ['put', 'terminate'])
        self.assertLess(real_time.time() - started, 3.0)
        self.assertEqual(self.ctrl.state, 'FORMING')                  # 没确认：交给对端的失联规则

    def test_presence_of_another_process_is_not_touched(self):
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)
        self.board.pid = 1                                            # 文件是别的进程写的
        self.board.heartbeat()
        self.stop()
        self.assertEqual(self.events, ['terminate'])

    def test_notice_failure_never_blocks_the_stop(self):
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)

        def broken(command):
            raise RuntimeError('queue closed')

        self.sp.command_queue = SimpleNamespace(put=broken)
        self.stop()
        self.assertEqual(self.events, ['terminate'])

    def test_stale_cancel_command_left_in_the_queue_does_not_hit_the_next_process(self):
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), self.board)
        command = lc.build_cancel_command(Path('log/instance_sync'), 'simA', 4242)
        new_board = PresenceBoard(Path('log/instance_sync'), 'simA', 'peerX')       # 新进程：新的 boot_id
        fresh = LoopController('simA', rng=Random(2))
        fresh.bind_board(new_board)
        fresh.request_start(LoopParams('leader', 1, 2, 2), new_board)
        self.assertFalse(fresh.cancel_by_command(command))
        self.assertEqual(fresh.state, 'FORMING')


if __name__ == '__main__':
    unittest.main()
