"""两台电脑各有完整三端队伍，保持绝对账号组号及本地断点隔离。"""

from datetime import date, timedelta
import tempfile
import unittest
from unittest.mock import Mock, patch

from tasks.MultiAccountEvo.config import MultiAccountEvo, MultiAccountEvoConfig
from tasks.MultiAccountEvo.script_task import ScriptTask
from tasks.MultiAccountEvo.sync import MultiAccountEvoSync, ROLES, SyncStateError
from module.multi_account.event_ticket_report import render_ticket_report
from tasks.MultiAccountEvo.recovery import wait_for_ocr_recovery


class GroupRangeTest(unittest.TestCase):
    def test_range_validation_and_default(self):
        self.assertEqual(0, MultiAccountEvoConfig().group_end)
        for start, end in ((0, 10), (11, 10), (1, 21), (19, 20)):
            config = MultiAccountEvo()
            config.multi_account_evo_config.group_start = start
            config.multi_account_evo_config.group_end = end
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                config.validate_runtime_accounts()

    def test_each_machine_runs_only_its_range_and_keeps_absolute_group_id(self):
        for start, end in ((1, 10), (11, 20)):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as directory:
                sync = MultiAccountEvoSync(directory, timeout=.1)
                state = sync.start_or_resume(20, 1, group_start=start, group_end=end)
                run_id = state['run_id']
                self.assertEqual(start, state['current_group'])
                for group in range(start, end + 1):
                    for role in ROLES:
                        sync.update_role(run_id, group, role, 'done')
                    state = sync.advance(run_id, group, 'leader')
                    self.assertEqual(group + 1, state['current_group'])
                    self.assertEqual(group == end, state['complete'])
                self.assertEqual(state, sync.start_or_resume(20, 1, group_start=start, group_end=end))

    def test_changed_range_cannot_silently_reuse_same_day_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=.1)
            before = sync.start_or_resume(20, 250, checkpoint_key='accounts')
            with self.assertRaises(SyncStateError):
                sync.start_or_resume(20, 250, group_end=10, checkpoint_key='accounts')
            self.assertEqual(before, sync.read())

    def test_report_uses_local_scope_and_actual_policy(self):
        page = render_ticket_report(dict(date=date.today().isoformat(), group_count=20,
            group_start=11, group_end=20, event_ocr_start=210, event_ocr_interval=5, battle_count=240))
        self.assertIn('本机第11～20组', page)
        self.assertIn('第210把开始，每5把检查一次，240把', page)
        self.assertIn('A11', page)
        self.assertNotIn('A01', page)

    def test_stale_date_run_and_group_cannot_write_daily_status(self):
        sync = Mock()
        state = dict(date=date.today().isoformat(), run_id='current', current_group=2)
        sync.read.return_value = state
        self.assertTrue(ScriptTask._can_write_daily_status(sync, 'current', 2))
        self.assertFalse(ScriptTask._can_write_daily_status(sync, 'old', 2))
        self.assertFalse(ScriptTask._can_write_daily_status(sync, 'current', 1))
        state['date'] = (date.today() - timedelta(days=1)).isoformat()
        self.assertFalse(ScriptTask._can_write_daily_status(sync, 'current', 2))


class OcrHealthCompatibilityTest(unittest.TestCase):
    def test_legacy_and_current_server_readiness(self):
        for info in ({'loaded_worker_count': 1}, {'loaded_worker_count': 0, 'warmup_complete': True}):
            with self.subTest(info=info), patch('zerorpc.Client') as factory, patch(
                'module.ocr.rpc.get_ocr_client', new=lambda refresh: None,
            ):
                client = factory.return_value
                client.get_server_info.return_value = info
                with patch('tasks.MultiAccountEvo.recovery.time.monotonic', return_value=1):
                    wait_for_ocr_recovery(deadline=3, check=Mock())
                client.close.assert_called_once()
                self.assertEqual(2, factory.call_args.kwargs['timeout'])

    def test_cancel_closes_connection_without_waiting_or_restarting_services(self):
        with patch('zerorpc.Client') as factory, patch(
            'module.ocr.rpc.get_ocr_client', new=lambda refresh: None,
        ):
            client = factory.return_value
            client.get_server_info.return_value = {'warmup_complete': False, 'loaded_worker_count': 1}
            check = Mock(side_effect=[None, RuntimeError('停止')])
            with patch('tasks.MultiAccountEvo.recovery.time.monotonic', return_value=1):
                with self.assertRaises(RuntimeError):
                    wait_for_ocr_recovery(deadline=3, check=check)
            client.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
