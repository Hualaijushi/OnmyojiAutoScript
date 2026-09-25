# This Python file uses the following encoding: utf-8
"""KekkaiUtilize 成功寄养后的独立随机延迟（D023 补记（三））。

新增任务级配置 `scheduler.success_jitter_min/max`（分钟，默认 0~0）：只在「读到有效寄养剩余时间」的正常成功
调度里，先按原规则算出 `max(now + OCR 剩余, now + min_run_interval)`，再额外加一次随机延迟，最后交给既有
`_schedule_target` 做静默窗口归一化并写入 next_run。OCR 兜底 / 短期重试 / 收敛保护 / 静默守卫 /
`utilize_enable=False` 都不使用它；0~0 时不采样，结果与改动前逐秒一致。

- 单元层：真实 `ScriptTask.run()` / `check_utilize_add()`（页面 / 截图 / OCR 用替身）+ 真实静默归一化；
  `random_int` 换成可控随机源（成功延迟区间与 cooldown / 静默抖动分开供值，并记录每次调用）。
- 配置层：真实 `ConfigModel.script_task` / `script_set_arg`（临时目录里的临时配置，不碰真实 `config/*.json`）。
- 调度层：真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay` 落盘 + 冻结时钟。
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from module.config.config import Config
from module.config.config_model import ConfigModel
from module.exception import TaskEnd
from tasks.KekkaiUtilize.config import SUCCESS_JITTER_LIMIT_MINUTES, UtilizeScheduler
from tasks.KekkaiUtilize.scheduling import normalize_for_quiet_window
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tests.test_kekkai_utilize_convergence import HARD_LIMIT, _RunAway, _stuck_task
from tests.test_kekkai_utilize_retry_scheduler import (
    SchedulerHarness, _StopLoop, _task,
)
from tests.test_kekkai_utilize_state import _patch_now

D = datetime
SCHED = 'tasks.KekkaiUtilize.script_task'


class _Rand:
    """`random_int` 替身：成功延迟区间与其它区间（cooldown / 静默抖动）分开供值，并记录每次调用。

    成功延迟的值耗尽后再被采样 = 多采样，直接抛 AssertionError 让用例失败（而不是悄悄复用旧值）。
    """

    def __init__(self, success_range=None, success=(), others=()):
        self.success_range = success_range
        self.success = list(success)
        self.others = list(others)
        self.calls = []

    def __call__(self, lo, hi):
        self.calls.append((lo, hi))
        if self.success_range is not None and (lo, hi) == self.success_range:
            if not self.success:
                raise AssertionError(f'成功延迟被多采样了一次: {(lo, hi)}')
            return self.success.pop(0)
        if not self.others:
            raise AssertionError(f'不该发生的随机采样: {(lo, hi)}')
        return self.others.pop(0)

    def success_calls(self):
        return [c for c in self.calls if c == self.success_range]


def _drive(t, now, rand, *, entry='run'):
    """冻结时钟 + 可控随机源下驱动一次；返回是否以 TaskEnd 结束（正常调度结束）。"""
    with _patch_now(now), patch(f'{SCHED}.random_int', side_effect=rand), patch(f'{SCHED}.time.sleep'):
        try:
            getattr(t, 'run' if entry == 'run' else entry)()
        except TaskEnd:
            return True
    return False


def _fostering_task(remaining=timedelta(hours=6), **cfg):
    """育成页 `I_UTILIZE_ADD` 一开始就不在（已在寄养）+ OCR 读到 `remaining`。"""
    t = _task(**cfg)
    t.appear = Mock(return_value=False)
    t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: remaining)
    return t


def _placing_task(remaining=timedelta(hours=6), **cfg):
    """先真实走一遍 `run_utilize`（`_run_search` 选中卡）寄养成功，下一圈按钮消失再读 OCR。"""
    t = _stuck_task(add=(True, False), search=(True,), **cfg)
    t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: remaining)
    return t


def _target(t):
    t.set_next_run.assert_called_once()
    return t.set_next_run.call_args.kwargs['target']


def _legacy_success_next_run(now, remaining, floor, *, quiet_jitter=600):
    """改动前的成功调度结果（逐字复刻：OCR 剩余 → 地板 → 静默归一化），作为 0/0 兼容基线。"""
    target = now + remaining
    if floor and floor.total_seconds() > 0:
        target = max(target, now + floor)
    return normalize_for_quiet_window(
        target, enable=True, quiet_start=dtime(0, 0), quiet_end=dtime(7, 0), jitter_seconds=quiet_jitter)


# ======================================================================================
# 一、单元层：公式 / 采样 / 路径隔离
# ======================================================================================

class SuccessJitterFormulaTest(TestCase):
    NOW = D(2026, 9, 1, 10, 0)

    def test_case1_default_zero_is_byte_compatible_and_never_samples(self):
        t = _placing_task(remaining=timedelta(hours=6))                     # 默认 0/0
        rand = _Rand()                                                     # 任何采样都会让用例失败
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertEqual(_target(t), D(2026, 9, 1, 16, 0))
        self.assertEqual(rand.calls, [])
        t.set_next_run.assert_called_once_with(task='KekkaiUtilize', target=D(2026, 9, 1, 16, 0), server=False)

    def test_case1b_zero_zero_matches_the_legacy_formula_across_a_grid(self):
        # 0/0 与改动前公式逐秒一致：覆盖静默窗口内外 / 地板生效与否 / 跨午夜
        for hour in range(0, 24, 3):
            for remaining in (timedelta(minutes=5), timedelta(hours=1), timedelta(hours=6), timedelta(hours=11)):
                for floor in (timedelta(0), timedelta(hours=2), timedelta(hours=8)):
                    with self.subTest(hour=hour, remaining=remaining, floor=floor):
                        now = D(2026, 9, 1, hour, 7, 3, 250000)
                        t = _fostering_task(remaining, min_run_interval=floor)
                        rand = _Rand(others=[600] * 3)
                        _drive(t, now, rand, entry='check_utilize_add')
                        self.assertEqual(_target(t), _legacy_success_next_run(now, remaining, floor))
                        self.assertEqual(rand.success_calls(), [])

    def test_case2_random_range_is_sampled_once_within_the_configured_bounds(self):
        for sample, expect in ((1800, D(2026, 9, 1, 16, 30)), (2400, D(2026, 9, 1, 16, 40)),
                               (5400, D(2026, 9, 1, 17, 30))):
            with self.subTest(sample=sample):
                t = _placing_task(success_jitter_min=30, success_jitter_max=90)
                rand = _Rand((1800, 5400), success=[sample])
                self.assertTrue(_drive(t, self.NOW, rand))
                self.assertEqual(rand.calls, [(1800, 5400)])              # 分钟 × 60，且只采样一次
                self.assertEqual(_target(t), expect)

    def test_case3_equal_bounds_add_a_fixed_delay(self):
        t = _placing_task(success_jitter_min=60, success_jitter_max=60)
        rand = _Rand((3600, 3600), success=[3600])
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertEqual(rand.calls, [(3600, 3600)])
        self.assertEqual(_target(t), D(2026, 9, 1, 17, 0))

    def test_case3b_zero_to_thirty_range_uses_zero_lower_bound(self):
        t = _placing_task(success_jitter_min=0, success_jitter_max=30)
        rand = _Rand((0, 1800), success=[0])
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertEqual(rand.calls, [(0, 1800)])
        self.assertEqual(_target(t), D(2026, 9, 1, 16, 0))

    def test_case4_every_successful_schedule_samples_independently_once(self):
        t = _placing_task(success_jitter_min=30, success_jitter_max=90)
        rand = _Rand((1800, 5400), success=[2000, 4000])
        self.assertTrue(_drive(t, self.NOW, rand))
        first = _target(t)
        self.assertEqual(len(rand.success_calls()), 1)                    # 第一轮：恰好一次
        # 同一个任务对象再跑一轮（状态由 run() 重置）：不复用上一轮的随机值
        t2 = _placing_task(success_jitter_min=30, success_jitter_max=90)
        self.assertTrue(_drive(t2, self.NOW, rand))
        second = _target(t2)
        self.assertEqual(len(rand.success_calls()), 2)                    # 总共两次，每轮各一次
        self.assertEqual(first, self.NOW + timedelta(hours=6, seconds=2000))
        self.assertEqual(second, self.NOW + timedelta(hours=6, seconds=4000))

    def test_case4b_the_same_task_object_run_twice_does_not_reuse_the_sample(self):
        t = _fostering_task(success_jitter_min=30, success_jitter_max=90)
        rand = _Rand((1800, 5400), success=[2000, 4000])
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertTrue(_drive(t, self.NOW, rand))
        targets = [c.kwargs['target'] for c in t.set_next_run.call_args_list]
        self.assertEqual(targets, [self.NOW + timedelta(hours=6, seconds=2000),
                                   self.NOW + timedelta(hours=6, seconds=4000)])

    def test_case7_already_fostering_counts_as_the_same_normal_success_path(self):
        t = _fostering_task(timedelta(hours=3), success_jitter_min=30, success_jitter_max=90)
        rand = _Rand((1800, 5400), success=[2400])
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertEqual(rand.calls, [(1800, 5400)])
        self.assertEqual(_target(t), self.NOW + timedelta(hours=3, minutes=40))

    def test_case11_min_run_interval_floor_is_applied_before_the_jitter(self):
        cases = (
            # (剩余, 地板, 成功延迟(分钟), 期望)
            (timedelta(hours=1), timedelta(hours=3), 0, D(2026, 9, 1, 13, 0)),
            (timedelta(hours=1), timedelta(hours=3), 30, D(2026, 9, 1, 13, 30)),   # 地板生效：3h + 30min
            (timedelta(hours=6), timedelta(hours=3), 30, D(2026, 9, 1, 16, 30)),   # 地板不生效：6h + 30min
        )
        for remaining, floor, jitter, expect in cases:
            with self.subTest(remaining=remaining, floor=floor, jitter=jitter):
                t = _fostering_task(remaining, min_run_interval=floor,
                                    success_jitter_min=jitter, success_jitter_max=jitter)
                rand = _Rand((jitter * 60, jitter * 60), success=[jitter * 60] if jitter else [])
                self.assertTrue(_drive(t, self.NOW, rand))
                self.assertEqual(_target(t), expect)
                self.assertEqual(len(rand.success_calls()), 1 if jitter else 0)

    def test_case16_a_successful_schedule_writes_next_run_exactly_once(self):
        t = _placing_task(success_jitter_min=30, success_jitter_max=90)
        self.assertTrue(_drive(t, self.NOW, _Rand((1800, 5400), success=[2400])))
        t.set_next_run.assert_called_once()                               # 没有先写原定时间、再覆盖
        self.assertTrue(all(c.kwargs.get('server') is False for c in t.set_next_run.call_args_list))


class SuccessJitterQuietWindowTest(TestCase):
    def test_case8_jitter_pushes_the_candidate_into_the_quiet_window_then_normalizes_once(self):
        # 23:00 成功，剩余 2h → 原定 01:00；+30min → 01:30 落窗 → 07:00 + 静默抖动 10min
        now = D(2026, 9, 1, 23, 0)
        t = _fostering_task(timedelta(hours=2), success_jitter_min=30, success_jitter_max=30)
        rand = _Rand((1800, 1800), success=[1800], others=[600])
        self.assertTrue(_drive(t, now, rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 7, 10))
        self.assertEqual(rand.calls, [(1800, 1800), (300, 1800)])          # 先成功延迟、后静默抖动，各一次

    def test_case9_jitter_carries_a_quiet_window_candidate_out_of_the_window(self):
        # 22:50 + 8h = 06:50（窗内）；+20min = 07:10（窗外）→ 保留 07:10，不再做静默归一化
        now = D(2026, 9, 1, 22, 50)
        t = _fostering_task(timedelta(hours=8), success_jitter_min=20, success_jitter_max=20)
        rand = _Rand((1200, 1200), success=[1200])                         # others 为空：静默抖动被采样即失败
        self.assertTrue(_drive(t, now, rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 7, 10))
        self.assertEqual(rand.calls, [(1200, 1200)])

    def test_case9b_without_jitter_the_same_candidate_is_normalized_to_the_resume_time(self):
        now = D(2026, 9, 1, 22, 50)
        t = _fostering_task(timedelta(hours=8))                            # 0/0：原候选 06:50 在窗内
        rand = _Rand(others=[600])
        self.assertTrue(_drive(t, now, rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 7, 10))                 # 07:00 + 静默抖动 10min
        self.assertEqual(rand.calls, [(300, 1800)])

    def test_case10_the_success_jitter_is_not_added_again_after_the_quiet_resume(self):
        # 23:00 + 2h = 01:00；+45min = 01:45 落窗 → 07:00 + 5min = 07:05（不是 07:50）
        now = D(2026, 9, 1, 23, 0)
        t = _fostering_task(timedelta(hours=2), success_jitter_min=45, success_jitter_max=45)
        rand = _Rand((2700, 2700), success=[2700], others=[300])
        self.assertTrue(_drive(t, now, rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 7, 5))
        self.assertEqual(len(rand.success_calls()), 1)
        self.assertEqual(len(rand.calls), 2)

    def test_quiet_window_disabled_keeps_the_jittered_candidate(self):
        now = D(2026, 9, 1, 23, 0)
        t = _fostering_task(timedelta(hours=2), quiet_enable=False, success_jitter_min=30, success_jitter_max=30)
        rand = _Rand((1800, 1800), success=[1800])
        self.assertTrue(_drive(t, now, rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 1, 30))


class SuccessJitterIsolationTest(TestCase):
    """case 5 / 6 / 15：非成功路径一律不使用成功延迟。"""
    NOW = D(2026, 9, 1, 14, 0)
    JITTER = dict(success_jitter_min=30, success_jitter_max=90)

    def _assert_retry_only(self, t, rand, *, ended=True):
        self.assertEqual(_drive(t, self.NOW, rand), ended)
        self.assertEqual(rand.success_calls(), [])                         # 成功延迟从未被采样
        self.assertEqual(_target(t), self.NOW + timedelta(seconds=1200))    # 仍是原有 5~30 分钟 cooldown
        self.assertTrue(t.utilize_retry_scheduled)

    def test_case5_no_usable_card_keeps_the_short_retry_only(self):
        t = _task(**self.JITTER)
        t._run_search = Mock(return_value=None)
        self._assert_retry_only(t, _Rand((1800, 5400), others=[1200]))

    def test_case5b_three_soft_failures_keep_the_short_retry_only(self):
        t = _task(**self.JITTER)
        t._run_search = Mock(return_value=False)
        self._assert_retry_only(t, _Rand((1800, 5400), others=[1200]))

    def test_case5c_navigation_failure_keeps_the_short_retry_only(self):
        from module.exception import GamePageUnknownError
        t = _task(**self.JITTER)
        t.goto_page = Mock(side_effect=[True, True, GamePageUnknownError('nav')])
        self._assert_retry_only(t, _Rand((1800, 5400), others=[1200]))

    def test_case15_attempt_cap_guard_does_not_use_the_success_jitter(self):
        t = _task(**self.JITTER)
        t.appear = Mock(return_value=True)
        counter = {'n': 0}

        def _run_utilize(*args, **kwargs):                                # 每次「成功」并清零业务计数
            counter['n'] += 1
            if counter['n'] > HARD_LIMIT:
                raise _RunAway
            t.utilize_add_count = t.utilize_failed_count = 0
            return True

        t.run_utilize = _run_utilize
        self._assert_retry_only(t, _Rand((1800, 5400), others=[1200]))
        self.assertEqual(counter['n'], KU.UTILIZE_MAX_ATTEMPTS)
        self.assertTrue(t.utilize_terminal_failure)

    def test_case15b_time_cap_guard_does_not_use_the_success_jitter(self):
        t = _task(**self.JITTER)
        t.appear = Mock(return_value=True)
        mono = [0.0]

        def _run_utilize(*args, **kwargs):
            mono[0] += KU.UTILIZE_TOTAL_TIMEOUT + 1
            t.utilize_add_count = t.utilize_failed_count = 0
            return True

        t.run_utilize = _run_utilize
        with patch(f'{SCHED}.monotonic', side_effect=lambda: mono[0]):
            self._assert_retry_only(t, _Rand((1800, 5400), others=[1200]))
        self.assertEqual(t.utilize_total_attempts, 1)                     # 一次尝试就到耗时上限

    def test_case15c_unconfirmed_retry_write_is_still_not_a_normal_end(self):
        t = _task(persist=False, **self.JITTER)                           # 读回确认契约保持不变
        t._run_search = Mock(return_value=None)
        rand = _Rand((1800, 5400), others=[1200])
        self.assertFalse(_drive(t, self.NOW, rand))                       # 直接返回 = 失败，不是 TaskEnd
        self.assertFalse(t.utilize_retry_scheduled)
        self.assertEqual(rand.success_calls(), [])

    def test_case6_invalid_ocr_uses_the_five_minute_fallback_without_jitter(self):
        for label, value in (('zero', timedelta(0)), ('too_large', timedelta(hours=13)), ('not_delta', None)):
            with self.subTest(ocr=label):
                t = _fostering_task(value, **self.JITTER)
                rand = _Rand((1800, 5400))                                # 任何随机采样都失败
                self.assertTrue(_drive(t, self.NOW, rand))
                self.assertEqual(rand.calls, [])
                self.assertEqual(_target(t), self.NOW + timedelta(minutes=5))
                self.assertFalse(t.utilize_retry_scheduled)               # 走的是成功路径而不是重试出口

    def test_case6b_fallback_still_honours_the_min_run_interval_floor_without_jitter(self):
        t = _fostering_task(timedelta(0), min_run_interval=timedelta(hours=1), **self.JITTER)
        rand = _Rand((1800, 5400))
        self.assertTrue(_drive(t, self.NOW, rand))
        self.assertEqual(_target(t), self.NOW + timedelta(hours=1))
        self.assertEqual(rand.calls, [])

    def test_utilize_disabled_uses_the_existing_finish_schedule_without_jitter(self):
        t = _task(utilize_enable=False, **self.JITTER)
        rand = _Rand((1800, 5400))
        self.assertTrue(_drive(t, self.NOW, rand))
        t.set_next_run.assert_called_once_with(task='KekkaiUtilize', finish=True, success=True)
        self.assertEqual(rand.calls, [])

    def test_quiet_entry_guard_reschedules_without_jitter(self):
        t = _fostering_task(**self.JITTER)
        rand = _Rand((1800, 5400), others=[600])
        self.assertTrue(_drive(t, D(2026, 9, 2, 3, 0), rand))
        self.assertEqual(_target(t), D(2026, 9, 2, 7, 10))
        self.assertEqual(rand.success_calls(), [])
        t.goto_page.assert_not_called()                                    # 入口守卫之后不进入任何页面业务


# ======================================================================================
# 二、配置层：默认值 / 校验 / 单字段保存 / 旧文件兼容 / GET 与中文
# ======================================================================================

class _TempConfigCase(TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix='oas_ku_sj_')
        os.chdir(self.tmp)
        os.makedirs('config')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(os.chdir, self._cwd)

    def _data(self, **scheduler):
        data = ConfigModel().model_dump()
        data.pop('config_name', None)
        data['kekkai_utilize']['scheduler'].update(scheduler)
        return data

    def _model(self, name='cfg', **scheduler):
        ConfigModel.write_json(name, self._data(**scheduler))
        return ConfigModel(config_name=name, **ConfigModel.read_json(name))

    def _disk(self, name='cfg'):
        return json.loads(Path('config', f'{name}.json').read_text(encoding='utf-8'))['kekkai_utilize']['scheduler']

    def _put(self, model, field, value):
        return model.script_set_arg('KekkaiUtilize', 'scheduler', field, value)

    def _pair(self, model):
        sched = model.kekkai_utilize.scheduler
        return sched.success_jitter_min, sched.success_jitter_max


class SuccessJitterConfigTest(_TempConfigCase):
    def test_defaults_and_units(self):
        sched = UtilizeScheduler()
        self.assertEqual((sched.success_jitter_min, sched.success_jitter_max), (0, 0))
        self.assertEqual(SUCCESS_JITTER_LIMIT_MINUTES, 720)
        # 其它调度参数的默认值不因本字段改变
        self.assertEqual((sched.cooldown_min, sched.cooldown_max), (5, 30))
        self.assertEqual((sched.quiet_resume_jitter_min, sched.quiet_resume_jitter_max), (5, 30))

    def test_case13_save_and_echo_through_the_real_config_io(self):
        model = self._model()
        # 0/0 → 30/90：先抬高 max、再抬高 min，每一步落盘的区间都合法
        self.assertTrue(self._put(model, 'success_jitter_max', 90))
        self.assertTrue(self._put(model, 'success_jitter_min', 30))
        raw = self._disk()
        self.assertEqual((raw['success_jitter_min'], raw['success_jitter_max']), (30, 90))   # 已落盘
        saved = ConfigModel.read_json('cfg')
        saved.pop('config_name', None)                                     # save() 会把 config_name 一并写入
        reloaded = ConfigModel(config_name='cfg', **saved)
        self.assertEqual(self._pair(reloaded), (30, 90))
        echoed = {i['name']: i for i in reloaded.script_task('KekkaiUtilize')['scheduler']}
        self.assertEqual((echoed['success_jitter_min']['value'], echoed['success_jitter_max']['value']), (30, 90))

    def test_case13b_saving_one_field_does_not_touch_other_scheduler_fields(self):
        model = self._model(cooldown_min=7, cooldown_max=9, next_run='2026-09-05 10:11:12')
        before = self._disk()
        self.assertTrue(self._put(model, 'success_jitter_max', 45))
        after = self._disk()
        changed = {k for k in after if after[k] != before.get(k)}
        self.assertEqual(changed, {'success_jitter_max'})

    def test_case14_illegal_values_are_rejected_and_the_old_config_stays(self):
        model = self._model(success_jitter_min=30, success_jitter_max=90)
        before_disk = Path('config', 'cfg.json').read_bytes()
        illegal = (
            ('success_jitter_min', -1),                       # 负数
            ('success_jitter_max', -1),
            ('success_jitter_min', 91),                       # min > max（不会自动交换）
            ('success_jitter_max', 29),                       # max < min
            ('success_jitter_max', SUCCESS_JITTER_LIMIT_MINUTES + 1),   # 超过模型上限
            ('success_jitter_min', SUCCESS_JITTER_LIMIT_MINUTES + 1),
        )
        for field, value in illegal:
            with self.subTest(field=field, value=value):
                self.assertFalse(self._put(model, field, value))
                self.assertEqual(self._pair(model), (30, 90))                 # 内存里旧值保持
                self.assertEqual(Path('config', 'cfg.json').read_bytes(), before_disk)   # 磁盘没有被改

    def test_case14b_constructor_rejects_min_above_max_instead_of_swapping(self):
        for lo, hi in ((5, 1), (721, 721)):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(ValidationError):
                UtilizeScheduler(success_jitter_min=lo, success_jitter_max=hi)

    def test_case14c_out_of_range_values_in_a_hand_edited_file_are_never_used_as_is(self):
        # `ConfigBase.__init__` 对越界字段一律回退到默认值（既有的加载期策略，与 cooldown 等字段一致），
        # 所以手改文件写出 -1 / 721 也不会被当作有效延迟使用；最终区间始终满足 0 <= min <= max <= 720。
        for lo, hi in ((0, 721), (-1, 5)):
            with self.subTest(lo=lo, hi=hi):
                sched = UtilizeScheduler(success_jitter_min=lo, success_jitter_max=hi)
                self.assertTrue(0 <= sched.success_jitter_min <= sched.success_jitter_max
                                <= SUCCESS_JITTER_LIMIT_MINUTES)
                self.assertNotIn(721, (sched.success_jitter_min, sched.success_jitter_max))
                self.assertNotIn(-1, (sched.success_jitter_min, sched.success_jitter_max))

    def test_boundary_values_are_accepted(self):
        for lo, hi in ((0, 0), (0, 30), (30, 90), (60, 60), (720, 720), (0, 720)):
            with self.subTest(lo=lo, hi=hi):
                sched = UtilizeScheduler(success_jitter_min=lo, success_jitter_max=hi)
                self.assertEqual((sched.success_jitter_min, sched.success_jitter_max), (lo, hi))

    def test_single_field_edits_never_persist_an_intermediate_illegal_pair(self):
        # 单字段 PUT 序列：每一步后落盘的都是合法区间（min <= max）；违规一步被拒绝、旧值保持
        model = self._model(success_jitter_min=30, success_jitter_max=90)
        steps = [
            ('success_jitter_min', 100, False),               # 想调到 100/200：先改 min 会 min > max，被拒绝
            ('success_jitter_max', 200, True),                # 先抬高 max
            ('success_jitter_min', 100, True),                # 再抬高 min
            ('success_jitter_min', 10, True),                 # 调低：先改 min
            ('success_jitter_max', 20, True),                 # 再改 max
            ('success_jitter_max', 0, False),                 # max 不能低于 min(10)
            ('success_jitter_min', 0, True),
            ('success_jitter_max', 0, True),                  # 回到 0/0
        ]
        for field, value, ok in steps:
            with self.subTest(field=field, value=value):
                self.assertEqual(self._put(model, field, value), ok)
                raw = self._disk()
                self.assertLessEqual(raw['success_jitter_min'], raw['success_jitter_max'])
        self.assertEqual(self._pair(model), (0, 0))

    def test_oasx_draft_save_order_converges_within_two_passes_and_never_persists_an_illegal_pair(self):
        # 模拟 OASX 草稿保存：按用户编辑顺序逐字段 PUT，失败的字段保持 dirty，再点一次保存只重试失败项
        transitions = (((0, 0), (30, 90)), ((30, 90), (100, 200)), ((100, 200), (10, 20)), ((30, 90), (0, 0)))
        for old, new in transitions:
            for order in (('success_jitter_min', 'success_jitter_max'), ('success_jitter_max', 'success_jitter_min')):
                with self.subTest(old=old, new=new, order=order):
                    model = self._model(success_jitter_min=old[0], success_jitter_max=old[1])
                    values = dict(zip(('success_jitter_min', 'success_jitter_max'), new))
                    dirty, passes = [f for f in order if values[f] != dict(zip(
                        ('success_jitter_min', 'success_jitter_max'), old))[f]], 0
                    while dirty:
                        passes += 1
                        self.assertLessEqual(passes, 2)
                        failed = []
                        for field in dirty:
                            if not self._put(model, field, values[field]):
                                failed.append(field)
                            raw = self._disk()
                            self.assertLessEqual(raw['success_jitter_min'], raw['success_jitter_max'])
                        dirty = failed
                    self.assertEqual(self._pair(model), new)

    def test_existing_scheduler_fields_still_accept_valid_edits_after_enabling_assignment_validation(self):
        model = self._model()
        self.assertTrue(self._put(model, 'cooldown_min', 10))
        self.assertTrue(self._put(model, 'cooldown_max', 40))
        self.assertTrue(self._put(model, 'quiet_resume_jitter_min', 1))
        self.assertTrue(self._put(model, 'priority', 3))
        sched = model.kekkai_utilize.scheduler
        self.assertEqual((sched.cooldown_min, sched.cooldown_max, sched.priority), (10, 40, 3))

    def test_old_config_files_without_the_new_fields_load_with_defaults_and_keep_other_values(self):
        data = self._data(success_interval='00 08:00:00', cooldown_min=7, next_run='2026-09-05 10:11:12')
        for key in ('success_jitter_min', 'success_jitter_max'):
            data['kekkai_utilize']['scheduler'].pop(key)                   # 旧用户文件里没有这两个键
        ConfigModel.write_json('old', data)
        raw_before = Path('config', 'old.json').read_bytes()
        config = Config(config_name='old')
        sched = config.model.kekkai_utilize.scheduler
        self.assertEqual((sched.success_jitter_min, sched.success_jitter_max), (0, 0))
        self.assertEqual(sched.cooldown_min, 7)
        self.assertEqual(sched.success_interval, timedelta(hours=8))
        self.assertEqual(sched.next_run, D(2026, 9, 5, 10, 11, 12))         # 已有 next_run 不被重算
        self.assertEqual(Path('config', 'old.json').read_bytes(), raw_before)   # 加载不回写

    def test_get_args_lists_the_new_fields_with_defaults_and_does_not_write(self):
        model = self._model()
        raw_before = Path('config', 'cfg.json').read_bytes()
        items = {i['name']: i for i in model.script_task('KekkaiUtilize')['scheduler']}
        for name in ('success_jitter_min', 'success_jitter_max'):
            self.assertIn(name, items)
            self.assertEqual((items[name]['default'], items[name]['value'], items[name]['type']), (0, 0, 'integer'))
            self.assertEqual(items[name]['description'], f'{name}_help')
        self.assertEqual(Path('config', 'cfg.json').read_bytes(), raw_before)   # GET 不写文件

    def test_two_accounts_have_independent_configs(self):
        a = self._model('accA')
        b = self._model('accB', success_jitter_min=30, success_jitter_max=90)
        self.assertEqual((self._pair(a), self._pair(b)), ((0, 0), (30, 90)))
        self.assertTrue(self._put(a, 'success_jitter_max', 45))
        self.assertEqual(self._pair(b), (30, 90))                           # A 的保存不影响 B
        self.assertEqual(self._disk('accB')['success_jitter_max'], 90)

    def test_template_and_zh_cn_translation_are_in_sync_with_the_model(self):
        repo = Path(__file__).resolve().parents[1]
        template = json.loads((repo / 'config' / 'template.json').read_text(encoding='utf-8'))
        sched = template['kekkai_utilize']['scheduler']
        self.assertEqual((sched['success_jitter_min'], sched['success_jitter_max']), (0, 0))
        zh = json.loads((repo / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        self.assertEqual(zh['success_jitter_min'], '成功后最小随机延迟')
        self.assertEqual(zh['success_jitter_max'], '成功后最大随机延迟')
        for name in ('success_jitter_min_help', 'success_jitter_max_help'):
            self.assertIn('分钟', zh[name])
            self.assertIn('剩余寄养时间', zh[name])
            self.assertIn('设为 0 时不增加延迟', zh[name])
        # 描述键必须与模型 description 一一对应（GET args 用它当翻译键）
        self.assertEqual(UtilizeScheduler.model_fields['success_jitter_min'].description, 'success_jitter_min_help')
        self.assertEqual(UtilizeScheduler.model_fields['success_jitter_max'].description, 'success_jitter_max_help')


# ======================================================================================
# 三、调度层：真实 Script.run / Script.loop + 真实 Config.task_delay 落盘
# ======================================================================================

class SuccessJitterSchedulerTest(SchedulerHarness, TestCase):
    def _make_ku(self, config, device):
        t = super()._make_ku(config, device)
        t.appear = Mock(name='appear', return_value=False)                # 已经在寄养，读 OCR 剩余时间
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=lambda img: timedelta(hours=6))
        t.check_max_lv = Mock()
        t.check_utilize_harvest = Mock()
        t.check_box_ap_or_exp = Mock()
        t.receive_guild_assets = Mock()
        return t

    def _rand(self, success_value=1800, quiet=600):
        """成功延迟区间之外的采样一律当静默抖动；用例可断言 `calls`。"""
        calls = []

        def _f(lo, hi):
            calls.append((lo, hi))
            return success_value if (lo, hi) == (1800, 1800) else quiet

        patch(f'{SCHED}.random_int', side_effect=_f).start()
        return calls

    def test_case12_two_accounts_use_their_own_config_and_schedule(self):
        self._write_config('simA')                                        # 0/0
        self._write_config('simB', ku_options={'success_jitter_min': 30, 'success_jitter_max': 30})
        script_a, script_b = self._script('simA'), self._script('simB')
        calls = self._rand()
        b_before = self._saved_next_run('simB')
        self.assertTrue(script_a.run('KekkaiUtilize'))
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(hours=6))
        self.assertEqual(self._saved_next_run('simB'), b_before)          # A 的成功调度不碰 B
        self.assertEqual(calls, [])                                       # A 是 0/0：完全没有采样
        self.assertTrue(script_b.run('KekkaiUtilize'))
        self.assertEqual(self._saved_next_run('simB'), self.START + timedelta(hours=6, minutes=30))
        self.assertEqual(calls, [(1800, 1800)])                           # 只有 B 采样一次
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(hours=6))

    def test_case1_zero_zero_with_microsecond_clock_matches_the_legacy_saved_value(self):
        self._write_config('simA')
        script = self._script('simA')
        self._rand()
        self.clock.now = D(2026, 9, 1, 10, 0, 0, 654321)
        self.assertTrue(script.run('KekkaiUtilize'))
        self.assertEqual(self._saved_next_run('simA'), D(2026, 9, 1, 16, 0, 0))   # 与旧版一样截断到秒

    def test_case16_real_config_writes_next_run_exactly_once_per_successful_schedule(self):
        self._write_config('simA', ku_options={'success_jitter_min': 30, 'success_jitter_max': 30})
        script = self._script('simA')
        self._rand()
        writes = []
        original = Config.task_delay

        def _spy(config, task, *args, **kwargs):
            writes.append((task, kwargs.get('target')))
            return original(config, task, *args, **kwargs)

        with patch.object(Config, 'task_delay', _spy):
            self.assertTrue(script.run('KekkaiUtilize'))
        self.assertEqual(writes, [('KekkaiUtilize', self.START + timedelta(hours=6, minutes=30))])
        self.assertEqual(self._saved_next_run('simA'), self.START + timedelta(hours=6, minutes=30))

    def test_sync_next_run_target_is_written_verbatim_regardless_of_the_jitter_config(self):
        self._write_config('simA', ku_options={'success_jitter_min': 30, 'success_jitter_max': 90})
        script = self._script('simA')
        target = D(2026, 9, 1, 15, 34, 56)                                 # 早于 success_interval 到期，取较早者
        script.config.task_delay(task='KekkaiUtilize', success=True, target=target)   # 等价于路由的 sync_next_run
        self.assertEqual(self._saved_next_run('simA'), target)

    def test_case17_loop_keeps_scheduling_other_tasks_and_applies_the_delay_per_success(self):
        self._write_config('simA', ku_options={'success_jitter_min': 30, 'success_jitter_max': 30}, others={
            'duel': self.START - timedelta(hours=1),
            'area_boss': self.START + timedelta(hours=20)})              # AreaBoss 到期时模拟结束
        script = self._script('simA')
        calls = self._rand()
        with self.assertRaises(_StopLoop):
            script.loop()
        # 第 1 次 14:00 → 20:30（6h + 30min）；第 2 次 20:30 → 03:00 落静默窗 → 07:00 + 10min 抖动
        self.assertEqual(self.ku_runs[:3], [self.START, self.START + timedelta(hours=6, minutes=30),
                                            D(2026, 9, 2, 7, 10)])
        self.exit_mock.assert_not_called()
        self.assertEqual(script.failure_record.get('KekkaiUtilize', 0), 0)
        ran = [c for c, _ in self.other_runs]
        self.assertTrue({'Duel', 'AreaBoss'} <= set(ran), ran)             # 其它任务照常被调度
        self.assertEqual(calls.count((1800, 1800)), len(self.ku_runs))     # 每次成功调度恰好采样一次

    def test_short_retry_loop_is_unchanged_when_success_jitter_is_configured(self):
        # 无卡重试路径：即使配置了成功延迟，也保持 20 分钟一轮的短期重试，且不采样成功延迟
        self._write_config('simA', ku_options={'success_jitter_min': 30, 'success_jitter_max': 90},
                           others={'area_boss': self.START + timedelta(minutes=90)})
        script = self._script('simA', cooldown=1200)
        calls = []
        base = patch(f'{SCHED}.random_int', side_effect=lambda lo, hi: calls.append((lo, hi)) or 1200)
        base.start()

        def _no_card(config, device):
            t = super(SuccessJitterSchedulerTest, self)._make_ku(config, device)
            t.appear = Mock(return_value=True)
            t._run_search = Mock(return_value=None)
            return t

        self._make_ku = _no_card
        with self.assertRaises(_StopLoop):
            script.loop()
        self.assertEqual(self.ku_runs[:5], [self.START + timedelta(minutes=20 * i) for i in range(5)])
        self.assertNotIn((1800, 5400), calls)
        self.exit_mock.assert_not_called()
        self.assertEqual(script.failure_record.get('KekkaiUtilize', 0), 0)
