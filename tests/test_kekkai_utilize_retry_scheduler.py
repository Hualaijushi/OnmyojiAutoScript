# This Python file uses the following encoding: utf-8
"""KekkaiUtilize 短期重试与通用调度器失败计数的交互回归（D023 补记）。

缺陷：业务上已经写好 5~30 分钟后 `next_run` 的「稍后重试」出口（无达标卡 / 3 次寄养失败 / 导航失败）
直接 `return`，`Script.run` 把它记为失败，`Script.loop` 连续 3 次失败会 `exit(1)` 终止整个调度线程；
而同样是业务重试的「5 次尝试用尽」出口却是 `TaskEnd`（记为成功）。修复后已确认写入 `next_run`
的重试出口统一 `raise TaskEnd`，系统异常与「重试没有可靠写入」仍走原有失败路径。

- 单元层（`ScriptTask.run()`）：逐个出口验证结局（`TaskEnd` / 返回 / 异常）与只写一次 `next_run`。
- 调度层：真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay` 落盘（临时目录里的临时配置）+
  冻结时钟；`exit(1)` 换成可观察的替身，不会结束测试进程；不碰真实 `config/*.json`。
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import script as script_mod
from module.config.config import Config
from module.config.config_model import ConfigModel
from module.exception import GamePageUnknownError, GameStuckError, TaskEnd
from module.script import ScriptRuntimeDecision
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tests.test_kekkai_utilize_state import _patch_now, _persisting_set_next_run, _sched_cfg

NOW = datetime(2026, 9, 1, 14, 0)


# ======================================================================================
# 一、ScriptTask.run() 出口矩阵（SimpleNamespace 配置 + 写入口替身，冻结在 14:00）
# ======================================================================================

def _task(*, persist=True, **cfg_kwargs):
    """构造能跑通 `run()` 全链路的 KU：页面 / 截图 / 收尾业务全部替身，只保留调度逻辑。"""
    cfg_kwargs.setdefault('select_friend_list', None)
    cfg_kwargs.setdefault('shikigami_order', 4)
    t = KU.__new__(KU)
    t.config = _sched_cfg(**cfg_kwargs)
    t.set_next_run = _persisting_set_next_run(t) if persist else Mock(name='set_next_run')
    t.push_notify = Mock(name='push_notify')
    t.goto_page = Mock(name='goto_page')
    t.screenshot = Mock(name='screenshot')
    t.appear = Mock(name='appear', return_value=True)      # I_UTILIZE_ADD 在场 = 还有空位，要去蹭卡
    t.device = SimpleNamespace(image='F')
    t.check_max_lv = Mock(name='check_max_lv')
    t.check_utilize_harvest = Mock(name='check_utilize_harvest')
    t.check_box_ap_or_exp = Mock(name='check_box_ap_or_exp')
    t.receive_guild_assets = Mock(name='receive_guild_assets')
    return t


def _run(t, *, clock=NOW, cooldown=1200):
    """在冻结时钟与固定随机值下跑一遍 `run()`，返回 (run() 是否直接返回, run() 返回值)。

    `cooldown` 给标量则每次采样都返回它；给列表则按调用顺序依次返回（cooldown、静默抖动）。
    """
    random_kwargs = ({'side_effect': list(cooldown)} if isinstance(cooldown, (list, tuple))
                     else {'return_value': cooldown})
    with _patch_now(clock), \
         patch('tasks.KekkaiUtilize.script_task.random_int', **random_kwargs), \
         patch('tasks.KekkaiUtilize.script_task.time.sleep'):
        try:
            return True, t.run()
        except TaskEnd:
            return False, None


def _ended_with_task_end(t, **kwargs):
    """`run()` 是否以 TaskEnd 结束（True）；直接返回则为 False。"""
    raised, _ret = _run(t, **kwargs)
    return not raised


class RetryExitMatrixTest(TestCase):
    def test_1_no_usable_card_schedules_retry_and_ends_normally(self):
        t = _task()
        t._run_search = Mock(return_value=None)                 # 从头到尾没点开过任何 5/6★ 候选
        self.assertTrue(_ended_with_task_end(t))
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(minutes=20), server=False)
        self.assertTrue(t.utilize_terminal_failure)
        self.assertTrue(t.utilize_retry_scheduled)
        # 失败出口不再做任何收尾页面操作
        t.receive_guild_assets.assert_not_called()
        t.check_box_ap_or_exp.assert_not_called()

    def test_2_three_soft_failures_reach_the_cap_then_end_normally(self):
        t = _task()
        t._run_search = Mock(return_value=False)               # 见过候选但都没达标 → 软失败
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t._run_search.call_count, 3)          # 恰好三次软失败后才进入短期重试
        t.set_next_run.assert_called_once()                    # 期间不改 next_run，只在第 3 次写一次
        self.assertEqual(t.utilize_failed_count, 3)
        self.assertTrue(t.utilize_retry_scheduled)

    def test_3_navigation_failure_schedules_retry_and_ends_normally(self):
        t = _task()
        calls = []

        def _goto(page):
            calls.append(page)
            if len(calls) == 3:                                # 进结界、进育成页成功，进寄养页失败
                raise GamePageUnknownError('nav')
            return True

        t.goto_page = Mock(side_effect=_goto)
        t.run_utilize = Mock()
        self.assertTrue(_ended_with_task_end(t))
        t.run_utilize.assert_not_called()                      # 导航失败禁止继续寄养业务
        t.set_next_run.assert_called_once()
        self.assertTrue(t.utilize_retry_scheduled)

    def test_3b_navigation_stuck_error_is_also_the_existing_recoverable_exit(self):
        t = _task()
        t.goto_page = Mock(side_effect=[True, True, GameStuckError('stuck')])
        t.run_utilize = Mock()
        self.assertTrue(_ended_with_task_end(t))
        t.set_next_run.assert_called_once()

    def test_4_five_attempts_exhausted_keeps_bounded_exit_and_business_tail(self):
        t = _task()
        t.run_utilize = Mock(return_value=False)               # 既不失败计数也不选中：只累加尝试次数
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.run_utilize.call_count, 4)          # 第 5 次循环顶端进入短期重试
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(minutes=20), server=False)
        # 与其它重试出口一致（TaskEnd），且保持既有语义：5 次出口仍继续收尾业务
        t.receive_guild_assets.assert_called_once()
        self.assertFalse(t.utilize_terminal_failure)

    def test_5_retry_inside_quiet_window_is_normalized_once(self):
        t = _task(jitter_min=10, jitter_max=10)
        t._run_search = Mock(return_value=None)
        raised, _ = _run(t, clock=datetime(2026, 9, 1, 23, 55), cooldown=[1200, 600])
        self.assertFalse(raised)
        # 23:55 + 20min = 00:15 落窗 → 次日 07:00 + 10min，仅这一次归一化
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 2, 7, 10), server=False)

    def test_5b_real_clock_has_microseconds_but_saved_next_run_is_truncated(self):
        # 生产里 `datetime.now()` 带微秒，`task_delay` 落盘时截断到秒：读回确认必须按同样口径比较
        t = _task()
        t._run_search = Mock(return_value=None)
        clock = NOW.replace(microsecond=123456)
        self.assertTrue(_ended_with_task_end(t, clock=clock))
        self.assertEqual(t.config.kekkai_utilize.scheduler.next_run,
                         (clock + timedelta(minutes=20)).replace(microsecond=0))
        self.assertTrue(t.utilize_retry_scheduled)

    def test_6_saved_next_run_is_written_once_and_not_touched_by_wrap_up(self):
        t = _task()
        t._run_search = Mock(return_value=None)
        self.assertTrue(_ended_with_task_end(t))
        self.assertEqual(t.set_next_run.call_count, 1)
        self.assertEqual(t.config.kekkai_utilize.scheduler.next_run, NOW + timedelta(minutes=20))

    def test_7_ocr_failure_keeps_the_five_minute_fallback(self):
        t = _task()
        t.appear = Mock(return_value=False)                    # 已在寄养
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(0))
        self.assertTrue(_ended_with_task_end(t))
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(minutes=5), server=False)
        self.assertFalse(t.utilize_retry_scheduled)            # 走的是成功路径，与重试出口无关
        t.receive_guild_assets.assert_called_once()

    def test_8_normal_utilize_success_schedule_is_unchanged(self):
        t = _task()
        t.appear = Mock(return_value=False)
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=3, minutes=10))
        self.assertTrue(_ended_with_task_end(t))
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=NOW + timedelta(hours=3, minutes=10), server=False)

    def test_8b_quiet_window_entry_guard_is_unchanged(self):
        t = _task(jitter_min=5, jitter_max=5)
        t.goto_page = Mock()
        raised, _ = _run(t, clock=datetime(2026, 9, 1, 3, 0), cooldown=300)
        self.assertFalse(raised)
        t.goto_page.assert_not_called()                        # 静默窗内不进入任何页面
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 7, 5), server=False)

    def test_9_system_errors_propagate_and_are_not_turned_into_task_end(self):
        for error in (GamePageUnknownError('page'), GameStuckError('stuck')):
            with self.subTest(error=type(error).__name__):
                t = _task()
                t.goto_page = Mock(side_effect=error)          # 进寮结界这一步：没有业务重试出口
                with _patch_now(NOW), self.assertRaises(type(error)):
                    t.run()
                t.set_next_run.assert_not_called()             # 系统异常不写 next_run（原有行为）

    def test_9b_stuck_error_from_the_growth_page_navigation_propagates(self):
        t = _task()
        t.goto_page = Mock(side_effect=[True, GameStuckError('growth')])
        with _patch_now(NOW), patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
                self.assertRaises(GameStuckError):
            t.run()
        t.set_next_run.assert_not_called()

    def test_10_unconfirmed_retry_write_is_not_reported_as_normal_end(self):
        t = _task(persist=False)                               # set_next_run 静默没有落值
        t._run_search = Mock(return_value=None)
        raised, ret = _run(t)
        self.assertTrue(raised)                                # 直接返回（= 调度器记失败），没有抛 TaskEnd
        self.assertIsNone(ret)
        self.assertTrue(t.utilize_terminal_failure)
        self.assertFalse(t.utilize_retry_scheduled)

    def test_10b_unconfirmed_write_on_the_five_attempt_exit_is_also_a_failure_return(self):
        t = _task(persist=False)
        t.run_utilize = Mock(return_value=False)
        raised, _ = _run(t)
        self.assertTrue(raised)
        t.receive_guild_assets.assert_not_called()             # 没有可靠的重试时间，不继续收尾

    def test_10c_write_error_propagates_instead_of_a_normal_end(self):
        t = _task()
        t._run_search = Mock(return_value=None)
        t.set_next_run = Mock(side_effect=OSError('disk full'))
        with _patch_now(NOW), patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300), \
                patch('tasks.KekkaiUtilize.script_task.time.sleep'), self.assertRaises(OSError):
            t.run()


# ======================================================================================
# 二、真实 Script.run / Script.loop + 真实 Config.task_delay（临时目录里的临时配置）
# ======================================================================================

class _StopLoop(BaseException):
    """测试用哨兵：不继承 Exception，穿过 `Script.run` / `Script.loop` 的 `except Exception`。"""


class _ExitCalled(BaseException):
    """替代 `exit(1)`：可观察，且不会结束测试进程。"""


class _Clock:
    def __init__(self, now):
        self.now = now


def _fake_datetime(clock):
    """`.now()` 返回冻结时钟；`isinstance(x, datetime)` 仍对真实 datetime 成立（Config 里有这类判断）。"""
    class _Meta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, datetime)

    class FakeDT(datetime, metaclass=_Meta):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    return FakeDT


class SchedulerHarness:
    """真实 Script / Config 的调度层驱动（不含用例，供其它测试文件复用）。

    除 `ku_options` 指定的字段外调度参数都取模型默认值；时间只由 `_Clock` 推进。
    """

    START = datetime(2026, 9, 1, 14, 0)

    def setUp(self):
        self._cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='oas_ku_sched_')
        os.chdir(self.tmp)                                     # module.logger 已在导入时 chdir 过，这里才切换
        os.makedirs('config')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.chdir, self._cwd)
        self.clock = _Clock(self.START)
        self.ku_runs, self.other_runs, self.snapshots = [], [], []
        fake = _fake_datetime(self.clock)
        for target in ('tasks.KekkaiUtilize.script_task.datetime', 'module.config.config.datetime',
                       'script.datetime'):
            patch(target, fake).start()
        patch('tasks.KekkaiUtilize.script_task.time.sleep').start()
        patch.object(script_mod.logger, 'set_file_logger').start()
        patch.object(script_mod, 'IS_WINDOWS', False).start()
        patch.object(script_mod.Script, 'save_error_log').start()
        patch.object(script_mod.Script, 'exception_handler').start()
        patch.object(Config, 'notifier', Mock(name='notifier')).start()
        self.exit_mock = patch.object(script_mod, 'exit', side_effect=_ExitCalled, create=True).start()
        self.addCleanup(patch.stopall)

    # ---- 配置与 Script 构造 ----
    def _write_config(self, name, *, ku_next_run=None, ku_options=None, others=None):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        ku = data['kekkai_utilize']['scheduler']
        ku.update(enable=True, next_run=ku_next_run or self.START - timedelta(hours=1))
        ku.update(ku_options or {})
        for task, next_run in (others or {}).items():
            data[task]['scheduler'].update(enable=True, next_run=next_run)
        ConfigModel.write_json(name, data)

    def _saved_next_run(self, name, task='kekkai_utilize'):
        raw = json.loads(Path('config', f'{name}.json').read_text(encoding='utf-8'))
        return datetime.fromisoformat(raw[task]['scheduler']['next_run'])

    def _script(self, name, *, cooldown=1200):
        script = script_mod.Script.__new__(script_mod.Script)
        script.server = script.state_queue = script.command_queue = script.gui_update_task = None
        script._emulator_down = False
        script.is_first_task = False
        script.config_name = name
        script.failure_record = {}
        script.last_task_runtime_outcome = None
        script.loop_thread = None
        script.device = Mock(name='device')
        script.runtime = Mock(name='runtime')
        script.runtime.prepare_task_execution.return_value = ScriptRuntimeDecision.READY
        script.runtime.handle_wait_during_idle.side_effect = self._wait_until
        patch('tasks.KekkaiUtilize.script_task.random_int',
              side_effect=lambda lo, hi: lo if cooldown == 'min' else cooldown).start()
        patch.object(script_mod, 'load_module', side_effect=lambda mod, path: self._module_for(
            Path(path).parent.name, script)).start()
        return script

    def _wait_until(self, next_run):
        """替身「空闲等待」：把冻结时钟推进到下一个任务的 next_run，并记下当时的失败计数。"""
        self.snapshots.append(dict(self._current_script.failure_record))
        if len(self.snapshots) > 60:                           # 防挂死：回归时预期的终止条件不成立也要能结束
            raise _StopLoop
        self.clock.now = max(self.clock.now, next_run)
        return ScriptRuntimeDecision.READY

    # ---- 被调度的任务 ----
    def _module_for(self, command, script):
        self._current_script = script
        if command == 'KekkaiUtilize':
            return SimpleNamespace(ScriptTask=self._make_ku)
        return SimpleNamespace(ScriptTask=lambda config, device: _OtherTask(self, command, config))

    def _make_ku(self, config, device):
        t = KU.__new__(KU)
        t.config, t.device = config, device
        t.start_time = self.clock.now
        t.goto_page = Mock(name='goto_page')
        t.screenshot = Mock(name='screenshot')
        t.push_notify = Mock(name='push_notify')
        t.appear = Mock(name='appear', return_value=True)       # 还有空位
        t._run_search = Mock(name='_run_search', return_value=None)   # 好友列表里没有任何 5/6★ 卡
        self.ku_runs.append(self.clock.now)
        self.last_ku = t
        return t


class SchedulerInteractionTest(SchedulerHarness, TestCase):
    # ---- 用例 ----
    def test_three_and_more_no_card_rounds_only_reschedule_and_the_loop_survives(self):
        # KU 每 20 分钟重试一次；AreaBoss 在 T0+90 分钟才到期——它能被执行，说明调度线程没有被 KU 拖垮
        self._write_config('simA', others={
            'duel': self.START - timedelta(hours=1),
            'area_boss': self.START + timedelta(minutes=90)})
        script = self._script('simA')
        with self.assertRaises(_StopLoop):
            script.loop()
        # 三次以上都实际执行到 KU，每次间隔恰为 20 分钟（既有 cooldown 规则），最后一次仍在 T0+80
        self.assertEqual(self.ku_runs, [self.START + timedelta(minutes=20 * i) for i in range(5)])
        self.assertGreaterEqual(len(self.ku_runs), 3)
        # 没有触发三次失败退出；KU 的失败计数始终为 0，其它任务也被正常执行
        self.exit_mock.assert_not_called()
        self.assertEqual(script.failure_record.get('KekkaiUtilize', 0), 0)
        self.assertTrue(all(s.get('KekkaiUtilize', 0) == 0 for s in self.snapshots))
        ran = [c for c, _ in self.other_runs]
        self.assertTrue({'Duel', 'AreaBoss'} <= set(ran), ran)   # 默认启用的 Restart 也会被正常调度
        # 每轮落盘的 next_run 都是「本轮开始 + 20 分钟」，没有被收尾流程覆盖成别的值
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=100))

    def test_every_round_persists_a_future_next_run_before_the_next_round(self):
        self._write_config('simA', others={'area_boss': self.START + timedelta(minutes=45)})
        script = self._script('simA')
        seen = []
        original = self._wait_until

        def _hook(next_run):
            seen.append((self.clock.now, self._saved_next_run('simA')))
            return original(next_run)

        script.runtime.handle_wait_during_idle.side_effect = _hook
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertGreaterEqual(len(seen), 3)
        for now, saved in seen:
            self.assertGreater(saved, now - timedelta(seconds=1))   # 合法：不是过去的时间
            self.assertLessEqual(saved - now, timedelta(minutes=30))

    def test_unconfirmed_retry_still_counts_as_failure_and_hits_the_three_strike_guard(self):
        # 对照：没有可靠写入 next_run 时不许冒充正常结束——失败照常累计，第 3 次仍触发（被替身的）exit(1)
        self._write_config('simA')
        script = self._script('simA')
        with patch.object(KU, '_is_next_run_persisted', return_value=False), \
                self.assertRaises(_ExitCalled):
            script.loop()
        self.assertEqual(len(self.ku_runs), 3)
        self.assertEqual(script.failure_record['KekkaiUtilize'], 3)
        self.exit_mock.assert_called_once_with(1)

    def test_system_error_keeps_the_original_failure_handling(self):
        self._write_config('simA')
        script = self._script('simA')
        original = self._make_ku

        def _stuck_ku(config, device):
            t = original(config, device)
            t.goto_page = Mock(side_effect=GameStuckError('stuck'))
            return t

        patch.object(self, '_make_ku', _stuck_ku).start()
        with patch.object(Config, 'task_call') as task_call:
            outcome = script.run('KekkaiUtilize')
        self.assertFalse(outcome)                              # 系统异常仍是失败，没有被伪装成正常结束
        task_call.assert_called_once_with('Restart')            # 原有恢复路径：重启游戏
        # KU 自己的 next_run 没有被改写（仍是过去时间）
        self.assertLess(self._saved_next_run('simA'), self.START)

    def test_retry_round_reports_success_through_the_real_script_run(self):
        self._write_config('simA')
        script = self._script('simA')
        self.assertTrue(script.run('KekkaiUtilize'))
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=20))

    def test_microsecond_clock_round_is_confirmed_through_the_real_config(self):
        self._write_config('simA')
        self.clock.now = self.START.replace(microsecond=987654)
        script = self._script('simA')
        self.assertTrue(script.run('KekkaiUtilize'))            # 真实 task_delay 截断微秒后仍读回一致
        self.assertEqual(self._saved_next_run('simA'),
                         (self.START.replace(microsecond=987654) + timedelta(minutes=20)).replace(microsecond=0))

    def test_accounts_are_scheduled_independently(self):
        self._write_config('simA')
        self._write_config('simB', ku_options={'cooldown_min': 10, 'cooldown_max': 10})
        script_a, script_b = self._script('simA', cooldown='min'), self._script('simB', cooldown='min')
        b_before = self._saved_next_run('simB')
        self.assertTrue(script_a.run('KekkaiUtilize'))         # 只有 A 跑一轮无卡重试
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(minutes=5))
        self.assertEqual(self._saved_next_run('simB'), b_before)   # B 的调度与失败计数完全不受影响
        self.assertEqual(script_b.failure_record, {})
        self.assertTrue(script_b.run('KekkaiUtilize'))
        self.assertEqual(self._saved_next_run('simB'), self.START + timedelta(minutes=10))  # B 用自己的 cooldown


class _OtherTask:
    """其它任务：正常完成并给自己排下一次；AreaBoss 到期时用哨兵结束本次模拟。"""

    def __init__(self, case, command, config):
        self.case, self.command, self.config = case, command, config

    def run(self):
        self.case.other_runs.append((self.command, self.case.clock.now))
        self.config.task_delay(task=self.command, success=True, server=False)
        if self.command == 'AreaBoss':
            raise _StopLoop
        raise TaskEnd
