"""门票模式真实共享文件和三端任务联测，所有设备与OCR均隔离。"""

from datetime import date, timedelta
from html import escape
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.multi_account.event_ticket_report import EventTicketReport, render_ticket_report
from module.multi_account.daily_task_archive import refresh_report_archive
from tasks.EvoZone.config import EvoZone
from tasks.EvoZone.script_task import ScriptTask as EvoTask
from tasks.GameUi.default_pages import page_reward
from tasks.MultiAccountEvo.config import MultiAccountEvo
from tasks.MultiAccountEvo.event import EventGoalError, event_complete, parse_ticket_value
from tasks.MultiAccountEvo.ghost_count import collect_ghost_counts, count_roi, parse_count
from tasks.MultiAccountEvo.script_task import ScriptTask
from tasks.MultiAccountEvo.sync import MultiAccountEvoSync, ROLES, RunChangedError, SyncStateError


class EventPureTest(unittest.TestCase):
    def test_ghost_count_requires_explicit_digits_and_uses_icon_offset(self):
        self.assertEqual(0, parse_count('0'))
        self.assertEqual(12, parse_count(' 12 '))
        for value in ('', 'O', '1?', '持有:', '-1', '1/2'):
            self.assertIsNone(parse_count(value))
        self.assertEqual((758, 385, 30, 30), count_roi(SimpleNamespace(roi_front=(718, 323, 50, 47))))
        self.assertIsNone(count_roi(SimpleNamespace(roi_front=(1260, 700, 20, 20))))

    def test_queue_collects_stable_values_without_clicking_summon(self):
        task = Mock()
        task.I_MD_GET_BOSS = object()
        task.I_MD_SWITCH_TICKET = object()
        task.I_MD_CLOSE_POPUP = object()
        task.I_MD_FIVE_STARS = SimpleNamespace(roi_front=(718, 323, 50, 47))
        task.I_MD_SIX_STARS = SimpleNamespace(roi_front=(819, 326, 44, 44))
        task.appear.return_value = True
        task.device.image = object()
        ocr = Mock()
        ocr.ocr_single.side_effect = ['12', '12', '', '1']
        with patch('tasks.MultiAccountEvo.ghost_count.MetaDemonTask', return_value=task), patch(
            'tasks.MultiAccountEvo.ghost_count.RuleOcr', return_value=ocr,
        ), patch('tasks.MultiAccountEvo.ghost_count.time.sleep'):
            result = collect_ghost_counts(Mock(), task.device)
        self.assertEqual({'5': 12, '6': None}, result)
        task.appear_then_click.assert_called_once_with(task.I_MD_CLOSE_POPUP, interval=0)

    def test_manual_completion_is_explicit_dated_and_does_not_fabricate_ocr(self):
        state = {'date': '2026-11-11', 'group_count': 1, 'event_groups': {'1': {
            'roles': {}, 'status': 'completed', 'completion_source': 'user_confirmed',
            'manual_completed_at': '2026-11-11T11:30:00',
        }}}
        self.assertTrue(event_complete(state, 1))
        html = render_ticket_report(state)
        self.assertIn('人工确认完成', html)
        self.assertIn('未采集', html)
        self.assertEqual({}, state['event_groups']['1']['roles'])
        state['date'] = '2026-11-12'
        self.assertFalse(event_complete(state, 1))
        state['date'] = '2026-11-11'
        state['event_groups']['1']['completion_source'] = 'automatic'
        self.assertFalse(event_complete(state, 1))

    def test_strict_full_counter(self):
        for raw, expected in [('0/50', 0), ('49/50', 49), (' ５０ ／ ５０ ', 50),
                              ('51/50', None), ('50', None), ('O/50', None),
                              ('50/500', None), ('x50/50', None), ('-1/50', None)]:
            with self.subTest(raw=raw):
                self.assertEqual(expected, parse_ticket_value(raw))

    def test_event_config_is_opt_in_and_checks_start_limit(self):
        config = MultiAccountEvo()
        self.assertFalse(config.multi_account_evo_config.event_progress_enable)
        config.multi_account_evo_config.event_progress_enable = True
        config.multi_account_evo_config.battle_count = 199
        with self.assertRaises(ValueError):
            config.validate_runtime_accounts()

    def test_199_skips_and_six_points_include_200(self):
        task = object.__new__(ScriptTask)
        task._event_segment = dict(completed=0, floor=0, remaining=250, start=200, interval=10, pending=False)
        points = []
        for completed in range(250):
            task._event_segment['completed'] = completed
            if task._event_sample_due():
                points.append(completed + 1)
        self.assertEqual([200, 210, 220, 230, 240, 250], points)

    def test_resume_205_reads_after_five_and_pending_reads_first(self):
        task = object.__new__(ScriptTask)
        task._event_segment = dict(completed=0, floor=205, remaining=45, start=200, interval=10, pending=False)
        self.assertFalse(task._event_sample_due())
        task._event_segment['completed'] = 4
        self.assertTrue(task._event_sample_due())
        task._event_segment.update(completed=0, pending=True)
        self.assertTrue(task._event_sample_due())

    def test_counter_mode_keeps_time_limit_and_event_mode_uses_goal(self):
        task = object.__new__(ScriptTask)
        task.current_count = task.limit_count = 250
        task.start_time = __import__('datetime').datetime.now() - timedelta(hours=2)
        task.limit_time = timedelta(minutes=30)
        self.assertTrue(task._evo_count_limit_reached())
        self.assertTrue(task._evo_time_limit_reached())
        task._event_segment = {}
        task._event_stop = False
        self.assertFalse(task._evo_count_limit_reached())
        self.assertFalse(task._evo_time_limit_reached())
        self.assertFalse(task._embedded_count_complete(250))
        task._event_stop = True
        self.assertTrue(task._embedded_count_complete(250))


class EventSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sync = MultiAccountEvoSync(self.temp.name, timeout=0.15, poll_interval=0.002, event_mode=True)
        self.state = self.sync.start_or_resume(1, 250, checkpoint_key='event')
        self.run_id = self.state['run_id']
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, 'ready', character=role)

    def seed(self, count=199, reached=False):
        with self.sync._lock():
            state = self.sync._read_unlocked()
            state['battle_progress']['1'] = dict.fromkeys(ROLES, count)
            if reached:
                state['event_groups']['1'] = {'roles': {r: {'value': 50, 'reached': True} for r in ROLES}, 'samples': {}}
            self.sync._write_unlocked(state)

    def test_event_file_does_not_replace_normal_state(self):
        self.assertEqual('.multi_account_evo_event_50_sync.json', self.sync.state_path.name)
        self.assertFalse((Path(self.temp.name) / '.multi_account_evo_sync.json').exists())

    def test_ghost_results_preserve_ticket_goal_and_require_current_session(self):
        with self.assertRaises(SyncStateError):
            self.sync.record_ghost_counts(self.run_id, 1, 'leader', 0, {'5': 3, '6': None})
        self.seed(200, reached=True)
        self.sync.record_ghost_counts(self.run_id, 1, 'leader', 0, {'5': 0, '6': None})
        self.sync.record_ghost_counts(self.run_id, 1, 'member_1', 0, {'5': 2, '6': 4})
        with self.assertRaises(Exception):
            self.sync.wait_ghost_counts(self.run_id, 1, epoch=0)
        self.sync.record_ghost_counts(self.run_id, 1, 'member_2', 0, {'5': None, '6': 1})
        result = self.sync.wait_ghost_counts(self.run_id, 1, epoch=0)
        self.assertTrue(event_complete(result, 1))
        self.assertEqual({'5': 0, '6': None}, result['event_groups']['1']['roles']['leader']['ghost_counts'])
        with self.assertRaises(SyncStateError):
            self.sync.record_ghost_counts(self.run_id, 1, 'leader', 0, {'5': False, '6': 0})

    def test_250_without_three_tickets_cannot_be_done(self):
        self.seed(250)
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        with self.assertRaises(SyncStateError):
            self.sync.update_role(self.run_id, 1, 'leader', 'done', epoch=0)
        self.assertFalse(self.sync.read()['complete'])

    def test_fifty_allows_early_done_without_fabricated_battle_count(self):
        self.seed(200, reached=True)
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, 'done', epoch=0)
        result = self.sync.advance(self.run_id, 1, 'leader')
        self.assertTrue(result['complete'])
        self.assertEqual(dict.fromkeys(ROLES, 200), result['battle_progress']['1'])

    def test_report_alone_does_not_acknowledge_battle_or_release_barrier(self):
        self.seed()
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        token = self.sync.record_event_sample(self.run_id, 1, 0, 'leader', 1, 50, '50/50', True, 0.1)
        with self.assertRaises(SyncStateError):
            self.sync.finish_event_sample(self.run_id, 1, 0, 'leader', token)
        self.assertFalse(event_complete(self.sync.read(), 1))

    def test_old_run_or_epoch_report_cannot_change_tickets(self):
        self.seed()
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        self.sync.request_recovery(self.run_id, 1, 'leader', '卡住')
        with self.assertRaises(Exception):
            self.sync.record_event_sample(self.run_id, 1, 0, 'leader', 1, 50, '50/50', True, 0)
        new = self.sync.start_or_resume(1, 250, checkpoint_key='event')
        self.assertEqual(199, new['battle_progress']['1']['leader'])
        with self.assertRaises(RunChangedError):
            self.sync.record_event_sample(self.run_id, 1, 0, 'leader', 1, 50, '50/50', True, 0)

    def test_cross_day_active_checks_stop(self):
        state = self.sync.read()
        state['date'] = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(SyncStateError):
            self.sync._check_control(state, self.run_id, 1)


class EventTaskIntegrationTest(unittest.TestCase):
    def run_roles(self, *, initial=199, partial=False, never_reached=False, bad_ocr=False, late_role=False,
                  scan_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=3, poll_interval=0.002, event_mode=True)
            state = sync.start_or_resume(1, 250, checkpoint_key='event')
            run_id = state['run_id']
            for role in ROLES:
                sync.update_role(run_id, 1, role, 'ready', character=role)
            with sync._lock():
                state = sync._read_unlocked()
                state['battle_progress']['1'] = dict.fromkeys(ROLES, initial)
                sync._write_unlocked(state)
            model = MultiAccountEvo()
            model.multi_account_evo_config.event_progress_enable = True
            model.multi_account_evo_config.battle_count = 250
            tasks, errors, reads = {}, {}, {r: 0 for r in ROLES}
            for role in ROLES:
                task = object.__new__(ScriptTask)
                task.config = SimpleNamespace(evo_zone=EvoZone())
                task.device = SimpleNamespace(image=role, click_record_clear=Mock())
                task.screenshot = Mock()
                task.appear = Mock(return_value=False)
                task.appear_then_click = Mock(return_value=False)
                task.click = Mock()
                task._wait_post_battle_state = Mock(return_value='room')
                task._event_reward_visible = Mock(return_value=True)
                def embedded(*, task=task, **kwargs):
                    task.current_count = 0
                    task.limit_count = kwargs['limit_count']
                    for _ in range(kwargs['limit_count']):
                        task.run_general_battle()
                        if task._evo_count_limit_reached():
                            break
                    return task._embedded_count_complete(kwargs['limit_count'])
                task.run_embedded = embedded
                tasks[role] = task
            def ocr(role):
                reads[role] += 1
                if bad_ocr and role == 'member_1':
                    return 'unknown'
                if never_reached or partial and role == 'member_1' and reads[role] == 1:
                    return '49/50'
                return '50/50'
            def battle(task, **kwargs):
                import time
                task.current_count += 1
                # 模拟奖励袋已经稳定显示超过一秒。
                task._event_reward_visible_since = time.monotonic() - 2
                task._handle_reward(SimpleNamespace(last_page=None), None)
                return True
            def collect(config, device):
                if scan_failure and device.image == 'member_1':
                    raise RuntimeError('模拟采集失败')
                return {'5': 3, '6': None}
            def run(role):
                try:
                    if late_role and role == 'member_2':
                        import time
                        deadline = time.monotonic() + 2
                        while not sync.read().get('event_groups', {}).get('1', {}).get('samples'):
                            if time.monotonic() >= deadline:
                                raise AssertionError('队长未到采样点')
                            time.sleep(0.002)
                    tasks[role]._run_group_with_recovery(model, sync, run_id, 1, role,
                                                       SimpleNamespace(character=role))
                    if role == 'leader':
                        sync.advance(run_id, 1, role)
                except Exception as exc:
                    errors[role] = exc
                    sync.fail(run_id, 1, role, str(exc))
            with patch.object(EvoTask, 'run_general_battle', new=battle), patch.object(
                ScriptTask.O_EVENT_PROGRESS_50, 'ocr', side_effect=ocr,
            ), patch('tasks.MultiAccountEvo.script_task.GameUi.detect_page_in', return_value=page_reward), patch(
                'tasks.MultiAccountEvo.ghost_count.collect_ghost_counts', side_effect=collect,
            ):
                threads = [threading.Thread(target=run, args=(r,), daemon=True) for r in ROLES]
                for thread in threads:thread.start()
                for thread in threads:thread.join(timeout=8)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertTrue(all(t._event_segment is None for t in tasks.values()))
            return sync.read(), errors, reads

    def test_three_roles_stop_at_200_and_require_two_fresh_fifties(self):
        state, errors, reads = self.run_roles(initial=198)
        self.assertEqual({}, errors)
        self.assertTrue(state['complete'])
        self.assertEqual(dict.fromkeys(ROLES, 200), state['battle_progress']['1'])
        self.assertEqual(dict.fromkeys(ROLES, 2), reads)
        self.assertTrue(all(state['event_groups']['1']['roles'][role]['ghost_counts'] == {'5': 3, '6': None}
                            for role in ROLES))

    def test_collection_failure_keeps_event_goal_and_advances(self):
        state, errors, _ = self.run_roles(initial=198, scan_failure=True)
        self.assertEqual({}, errors)
        self.assertTrue(state['complete'])
        self.assertTrue(event_complete(state, 1))
        self.assertEqual({'5': None, '6': None}, state['event_groups']['1']['roles']['member_1']['ghost_counts'])

    def test_reached_leader_and_member_keep_playing_until_last_role_at_210(self):
        state, errors, reads = self.run_roles(partial=True)
        self.assertEqual({}, errors)
        self.assertTrue(state['complete'])
        self.assertEqual(dict.fromkeys(ROLES, 210), state['battle_progress']['1'])
        self.assertEqual({'leader': 2, 'member_1': 3, 'member_2': 2}, reads)

    def test_late_role_does_not_mistake_current_sample_for_recovery_pending(self):
        state, errors, reads = self.run_roles(initial=198, late_role=True)
        self.assertEqual({}, errors)
        self.assertTrue(state['complete'])
        self.assertEqual(dict.fromkeys(ROLES, 200), state['battle_progress']['1'])
        self.assertEqual(dict.fromkeys(ROLES, 2), reads)

    def test_250_last_check_without_fifty_stops_incomplete(self):
        state, errors, reads = self.run_roles(initial=249, never_reached=True)
        self.assertEqual(set(ROLES), set(errors))
        self.assertFalse(state['complete'])
        self.assertEqual(dict.fromkeys(ROLES, 250), state['battle_progress']['1'])
        self.assertEqual(dict.fromkeys(ROLES, 1), reads)

    def test_invalid_ocr_is_bounded_and_never_completes(self):
        state, errors, reads = self.run_roles(bad_ocr=True)
        self.assertFalse(state['complete'])
        self.assertEqual(3, reads['member_1'])
        self.assertTrue(errors)


class EventReportTest(unittest.TestCase):
    def test_card_report_keeps_existing_checkbox_key_and_group_controls(self):
        state = {'date': '2026-11-13', 'group_count': 1, 'event_groups': {'1': {
            'roles': {'leader': {'value': 50, 'reached': True}}, 'samples': {},
        }}}
        html = render_ticket_report(state, {'A01': 'a@example.com'})
        self.assertIn('oas-ghost-done-2026-11-13', html)
        self.assertIn('class="ghost-group" data-group="1"', html)
        self.assertEqual(3, html.count('class="ghost-account"'))
        self.assertIn('a@example.com', html)
        self.assertIn('已达标', html)
        self.assertIn('采样记录与异常', html)

    def test_ghost_counts_totals_do_not_treat_missing_as_zero(self):
        state = {'date': date.today().isoformat(), 'group_count': 1, 'event_groups': {'1': {
            'roles': {'leader': {'ghost_counts': {'5': 0, '6': 2}},
                      'member_1': {'ghost_counts': {'5': None, '6': 3}},
                      'member_2': {'ghost_counts': {'5': 4, '6': None}}}, 'samples': {},
        }}}
        html = render_ticket_report(state)
        self.assertIn('5x：4（2/3 账号已采集）', html)
        self.assertIn('6x：5（2/3 账号已采集）', html)
        self.assertIn('队长 5x', html)
        self.assertIn('队员二 6x', html)
        self.assertIn('未采集', html)

    def test_unknown_and_unsafe_raw_text_are_displayed_safely(self):
        html = render_ticket_report({'date': date.today().isoformat(), 'group_count': 1})
        self.assertIn('未采集', html)
        self.assertNotIn('>0/50', html)
        raw = '<script>alert(1)</script>'
        state = {'date': date.today().isoformat(), 'group_count': 1, 'event_groups': {'1': {
            'roles': {}, 'samples': {'x': {'point': 200, 'reports': {'leader': {'raw': raw}}}}, 'error': raw,
        }}}
        html = render_ticket_report(state)
        self.assertNotIn(raw, html)
        self.assertIn(escape(raw), html)

    def test_writer_preserves_existing_daily_content_and_keeps_default_daily_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sync = MultiAccountEvoSync(root/'config', timeout=1, event_mode=True)
            sync.start_or_resume(1, 250, checkpoint_key='event')
            output = root/'reports';output.mkdir()
            day = date.today().isoformat()
            daily = output/f'OAS每日任务结果_{day}.html'
            daily.write_text('<html><main><input type="checkbox" checked><img src="data:image/png;base64,YQ=="></main></html>',encoding='utf-8')
            report = EventTicketReport(sync, group_count=1, output_dir=output)
            page = report.refresh()
            report.refresh()
            text = daily.read_text(encoding='utf-8')
            self.assertEqual(1, text.count('id="ticket-report"'))
            self.assertIn('<input type="checkbox" checked>', text)
            self.assertIn('base64,YQ==', text)
            self.assertTrue(page.exists())
            index = (output/'index.html').read_text(encoding='utf-8')
            self.assertIn('id="latest"', index)
            self.assertIn('超鬼王门票情况', index)

    def test_archive_retains_seven_days_without_deleting_unrelated_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root/f'OAS超鬼王门票刷取情况_{date.today()-timedelta(days=7)}.html'
            old.write_text('旧记录', encoding='utf-8')
            unrelated = root/'门票备注.html';unrelated.write_text('保留',encoding='utf-8')
            refresh_report_archive(root,date.today())
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())


if __name__ == '__main__':
    unittest.main()
