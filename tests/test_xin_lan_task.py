# This Python file uses the following encoding: utf-8
"""XinLan 任务骨架（P2）：reset_unsafe 一次性消费、配对检查、排期映射、配置注册。全部不碰设备 / 游戏。"""
import json
import unittest
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from module.config.config_menu import ConfigMenu
from module.config.config_model import ConfigModel
from module.instance_sync import (
    NEXT_DEFER, NEXT_DONE, NEXT_RETRY, S_ALREADY, S_COMPLETED, S_FAILED, AckResult, SyncAdapter, SyncResult,
)
from tasks.XinLan import business
from tasks.XinLan.adapter import ReceiverAdapter, SenderAdapter
from tasks.XinLan.config import ResetConfig, SyncConfig, XinLan
from tasks.XinLan.script_task import ScriptTask, check_pair

_REPO = Path(__file__).resolve().parents[1]


def make_conf(*, reset=False, a='oas1', alias_a='A01', b='oas2', alias_b='A02', timeout=600):
    conf = XinLan()
    conf.sync = SyncConfig(instance_a=a, alias_a=alias_a, instance_b=b, alias_b=alias_b, rendezvous_timeout=timeout)
    conf.reset = ResetConfig(reset_unsafe=reset)
    return conf


class FakeCoordinator:
    def __init__(self, calls, result, ack=AckResult(True, 'acknowledged', 'r1', 1), ack_error=None, run_error=None):
        self.calls, self.result, self.ack = calls, result, ack
        self.ack_error, self.run_error = ack_error, run_error
        self.ack_reason = None

    def acknowledge_unsafe(self, reason=''):
        self.calls.append('ack')
        self.ack_reason = reason
        if self.ack_error:
            raise self.ack_error
        return self.ack

    def run(self):
        self.calls.append('run')
        if self.run_error:
            raise self.run_error
        return self.result


def make_task(conf, calls, *, adapter=object(), coordinator=None, save_error=None, config_name='oas1'):
    task = ScriptTask.__new__(ScriptTask)

    def save():
        calls.append(('save', conf.reset.reset_unsafe))
        if save_error:
            raise save_error

    task.config = SimpleNamespace(config_name=config_name, xin_lan=conf, save=save)
    task.set_next_run = lambda **kw: calls.append(('next', kw))
    task._build_adapter = lambda: adapter

    def build(adp, c):
        calls.append('build')
        return coordinator

    task._build_coordinator = build
    return task


OK = SyncResult(S_COMPLETED, 'completed', NEXT_DONE)


class ResetFlagTest(unittest.TestCase):
    def test_flag_off_neither_saves_nor_acks(self):
        calls = []
        make_task(make_conf(), calls, coordinator=FakeCoordinator(calls, OK)).run()
        self.assertEqual(calls, ['build', 'run', ('next', {'task': 'XinLan', 'success': True})])

    def test_flag_on_saves_off_before_ack_then_runs(self):
        calls = []
        conf = make_conf(reset=True)
        coordinator = FakeCoordinator(calls, OK)
        make_task(conf, calls, coordinator=coordinator).run()
        self.assertEqual(calls[:4], [('save', False), 'build', 'ack', 'run'])
        self.assertFalse(conf.reset.reset_unsafe)
        self.assertIn('oas1', coordinator.ack_reason)

    def test_rejected_ack_still_runs_and_flag_stays_off(self):
        calls = []
        conf = make_conf(reset=True)
        ack = AckResult(False, 'round_open')
        make_task(conf, calls, coordinator=FakeCoordinator(calls, OK, ack=ack)).run()
        self.assertEqual(calls[:4], [('save', False), 'build', 'ack', 'run'])
        self.assertFalse(conf.reset.reset_unsafe)

    def test_ack_exception_propagates_after_flag_is_consumed(self):
        calls = []
        conf = make_conf(reset=True)
        coordinator = FakeCoordinator(calls, OK, ack_error=RuntimeError('boom'))
        with self.assertRaises(RuntimeError):
            make_task(conf, calls, coordinator=coordinator).run()
        self.assertEqual(calls, [('save', False), 'build', 'ack'])
        self.assertFalse(conf.reset.reset_unsafe)

    def test_invalid_pair_consumes_flag_and_never_acks(self):
        calls = []
        conf = make_conf(reset=True, a='')
        make_task(conf, calls, coordinator=FakeCoordinator(calls, OK)).run()
        self.assertEqual(calls, [('save', False), ('next', {'task': 'XinLan', 'success': False})])

    def test_save_failure_means_no_ack(self):
        calls = []
        conf = make_conf(reset=True)
        with self.assertRaises(OSError):
            make_task(conf, calls, coordinator=FakeCoordinator(calls, OK), save_error=OSError('disk')).run()
        self.assertEqual(calls, [('save', False)])

    def test_default_task_builds_the_adapter_for_its_role(self):
        conf = make_conf()
        for name, expected in (('oas1', SenderAdapter), ('oas2', ReceiverAdapter)):
            task = ScriptTask.__new__(ScriptTask)
            task.config = SimpleNamespace(config_name=name, xin_lan=conf)
            adapter = task._build_adapter()
            self.assertIsInstance(adapter, expected)
            self.assertEqual(adapter.peer_alias, 'A02' if name == 'oas1' else 'A01')


class CheckPairTest(unittest.TestCase):
    def check(self, name='oas1', **kw):
        return check_pair(make_conf(**kw).sync, name)

    def test_valid_for_either_member(self):
        self.assertIsNone(self.check('oas1'))
        self.assertIsNone(self.check('oas2'))

    def test_blank_or_whitespace_fields(self):
        for field in ('a', 'alias_a', 'b', 'alias_b'):
            with self.subTest(field=field):
                self.assertIsNotNone(self.check(**{field: ''}))
                self.assertIsNotNone(self.check(**{field: '  '}))

    def test_duplicate_instance_or_alias(self):
        self.assertIsNotNone(self.check(b='oas1'))
        self.assertIsNotNone(self.check(alias_b='A01'))

    def test_self_must_be_a_member(self):
        self.assertIsNotNone(self.check('oas3'))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertIsNone(self.check('oas1', a=' oas1 ', alias_a=' A01 '))


class ScheduleTest(unittest.TestCase):
    def schedule(self, result):
        calls = []
        make_task(make_conf(), calls, coordinator=FakeCoordinator(calls, result)).run()
        return calls[-1]

    def test_done_and_already_completed_are_success(self):
        self.assertEqual(self.schedule(OK), ('next', {'task': 'XinLan', 'success': True}))
        already = SyncResult(S_ALREADY, 'completed', NEXT_DONE)
        self.assertEqual(self.schedule(already), ('next', {'task': 'XinLan', 'success': True}))

    def test_retry_later_uses_failure_interval(self):
        result = SyncResult(S_FAILED, 'rendezvous_timeout', NEXT_RETRY)
        self.assertEqual(self.schedule(result), ('next', {'task': 'XinLan', 'success': False}))

    def test_defer_goes_to_next_business_day(self):
        fixed = datetime(2026, 10, 21, 13, 0, 0)
        with mock.patch('tasks.XinLan.script_task.datetime') as fake_dt:
            fake_dt.now.return_value = fixed
            kind, kw = self.schedule(SyncResult(S_FAILED, 'unsafe_prior_round', NEXT_DEFER))
        self.assertEqual(kind, 'next')
        self.assertEqual(kw, {'task': 'XinLan', 'server': False,
                              'target': business.next_business_day_start(fixed)})
        self.assertGreater(kw['target'], fixed)

    def test_adapter_exception_is_not_swallowed(self):
        calls = []
        coordinator = FakeCoordinator(calls, OK, run_error=ConnectionError('device'))
        with self.assertRaises(ConnectionError):
            make_task(make_conf(), calls, coordinator=coordinator).run()
        self.assertFalse([c for c in calls if isinstance(c, tuple) and c[0] == 'next'])


class StubAdapter(SyncAdapter):
    business_id = business.BUSINESS_ID

    def protocol_params(self):
        return business.PROTOCOL_PARAMS

    def business_day(self, now):
        return business.business_day(now)

    def prepare(self, ctx):
        raise NotImplementedError

    dispatch = judge = verify = inspect_attempt = prepare


class BuildCoordinatorTest(unittest.TestCase):
    def test_arguments_come_from_config(self):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(config_name='oas2')
        coordinator = ScriptTask._build_coordinator(task, StubAdapter(), make_conf(timeout=300))
        self.assertEqual(coordinator.instance, 'oas2')
        self.assertEqual(coordinator.rendezvous_timeout, 300.0)
        self.assertEqual({m['instance'] for m in coordinator.members}, {'oas1', 'oas2'})
        self.assertEqual(coordinator.protocol['params']['max_rounds'], 4)


class BusinessDayTest(unittest.TestCase):
    def test_default_midnight_reset(self):
        self.assertEqual(business.business_day(datetime(2026, 10, 21, 0, 0, 1).timestamp()), '2026-10-21')
        self.assertEqual(business.business_day(datetime(2026, 10, 21, 23, 59, 59).timestamp()), '2026-10-21')
        self.assertEqual(business.next_business_day_start(datetime(2026, 10, 21, 13, 0)), datetime(2026, 10, 22))
        self.assertEqual(business.next_business_day_start(datetime(2026, 10, 21, 0, 0)), datetime(2026, 10, 22))

    def test_reset_time_boundaries(self):
        with mock.patch.object(business, 'DAILY_RESET', time(5, 0)):
            self.assertEqual(business.business_day(datetime(2026, 10, 21, 4, 59, 59).timestamp()), '2026-10-20')
            self.assertEqual(business.business_day(datetime(2026, 10, 21, 5, 0, 0).timestamp()), '2026-10-21')
            self.assertEqual(business.next_business_day_start(datetime(2026, 10, 21, 3, 0)),
                             datetime(2026, 10, 21, 5, 0))
            self.assertEqual(business.next_business_day_start(datetime(2026, 10, 21, 5, 0)),
                             datetime(2026, 10, 22, 5, 0))


class ConfigRegistrationTest(unittest.TestCase):
    def test_defaults(self):
        conf = XinLan()
        self.assertFalse(conf.scheduler.enable)
        self.assertFalse(conf.reset.reset_unsafe)
        self.assertEqual((conf.sync.instance_a, conf.sync.alias_b, conf.sync.rendezvous_timeout), ('', '', 600))

    def test_reset_switch_is_not_part_of_the_copyable_sync_group(self):
        self.assertNotIn('reset_unsafe', SyncConfig.model_fields)
        self.assertEqual(list(ResetConfig.model_fields), ['reset_unsafe'])

    def test_old_config_without_xin_lan_loads_with_defaults(self):
        model = ConfigModel.model_validate({'running_task': ''})
        self.assertFalse(model.xin_lan.reset.reset_unsafe)
        self.assertFalse(model.xin_lan.scheduler.enable)

    def test_menu_lists_the_task(self):
        self.assertIn('XinLan', ConfigMenu().menu['Daily Task'])

    def test_template_matches_model(self):
        template = json.loads((_REPO / 'config' / 'template.json').read_text(encoding='utf-8'))
        self.assertEqual(template['xin_lan'], json.loads(XinLan().model_dump_json()))
        self.assertNotIn('reset_unsafe', template['xin_lan']['sync'])
        self.assertIs(template['xin_lan']['reset']['reset_unsafe'], False)

    def test_i18n_covers_every_label_and_help(self):
        i18n = json.loads((_REPO / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        for key in ('XinLan', 'xin_lan', 'sync', 'reset', 'reset_unsafe', 'reset_unsafe_help'):
            self.assertIn(key, i18n)
        for group in (SyncConfig, ResetConfig):
            for name, field in group.model_fields.items():
                with self.subTest(field=name):
                    self.assertIn(name, i18n)
                    self.assertIn(field.description, i18n)


if __name__ == '__main__':
    unittest.main()
