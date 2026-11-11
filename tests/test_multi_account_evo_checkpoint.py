"""验证逐场断点、三端补跑和旧执行段隔离，不连接设备。"""

import copy
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.Component.GeneralBattle.general_battle import BattleAction
from tasks.EvoZone.script_task import ScriptTask as EvoTask
from tasks.EvoZone.config import EvoZone
from tasks.MultiAccountEvo.recovery import TeamStallError
from tasks.MultiAccountEvo.script_task import ScriptTask
from tasks.MultiAccountEvo.config import MultiAccountEvo
from tasks.MultiAccountEvo.sync import (
    ROLES, MultiAccountEvoSync, RecoveryRequested, RunChangedError, SyncStateError,
)


class BattleCheckpointSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sync = MultiAccountEvoSync(self.temp.name, timeout=1, poll_interval=0.002)
        self.state = self.sync.start_or_resume(2, 200, '2026-11-11', checkpoint_key='team-key')
        self.run_id = self.state['run_id']
        self.ready()

    def ready(self):
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, 'ready', character=role)

    def seed(self, counts):
        # 直接构造持久断点夹具，不把190场历史模拟成真实执行。
        with self.sync._lock():
            state = self.sync._read_unlocked()
            state['battle_progress']['1'] = dict(zip(ROLES, counts))
            self.sync._write_unlocked(state)

    def finish_recovery(self):
        for role in ROLES:
            self.sync.acknowledge_recovery(self.run_id, 1, 1, role, 'paused')
        for role in ROLES:
            self.sync.acknowledge_recovery(self.run_id, 1, 1, role, 'restarted')
        self.sync.finish_recovery(self.run_id, 1, 1, 'leader')

    def test_late_role_gets_same_frozen_plan_after_peer_reports(self):
        self.seed((190, 189, 190))
        first = self.sync.begin_battle_segment(self.run_id, 1, 0)
        self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 1)
        late = self.sync.begin_battle_segment(self.run_id, 1, 0)
        self.assertEqual(11, first['remaining'])
        self.assertEqual(first['bases'], late['bases'])
        self.assertEqual(first['remaining'], late['remaining'])
        late['bases']['leader'] = 0
        self.assertEqual(190, self.sync.read()['battle_segment']['bases']['leader'])

    def test_duplicate_and_old_reports_do_not_increment_or_write(self):
        self.seed((190, 190, 190))
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        for n in (1, 2):
            self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', n)
        with patch.object(self.sync, '_write_unlocked') as write:
            for n in (1, 2, 1):
                state = self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', n)
                self.assertEqual(192, state['battle_progress']['1']['leader'])
            write.assert_not_called()

    def test_skipped_sequence_and_invalid_reports_are_rejected(self):
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        for n in (0, -1, True, 2, 201):
            with self.subTest(n=n), self.assertRaises(SyncStateError):
                self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', n)
        self.assertEqual(0, self.sync.read()['battle_progress']['1']['leader'])

    def test_recovery_preserves_confirmed_battles_and_rejects_old_epoch(self):
        self.seed((190, 190, 190))
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 1)
        self.sync.request_recovery(self.run_id, 1, 'leader', '卡住')
        with self.assertRaises((RecoveryRequested, RunChangedError)):
            self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 2)
        self.finish_recovery()
        with self.assertRaises(RunChangedError):
            self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 2)
        plan = self.sync.begin_battle_segment(self.run_id, 1, 1)
        self.assertEqual(dict(zip(ROLES, (191, 190, 190))), plan['bases'])
        self.assertEqual(10, plan['remaining'])

    def test_same_day_new_session_keeps_progress_and_recovery_budget(self):
        self.seed((190, 189, 190))
        self.sync.request_recovery(self.run_id, 1, 'leader', '卡住')
        new = self.sync.start_or_resume(2, 200, '2026-11-11', checkpoint_key='team-key')
        self.assertNotEqual(self.run_id, new['run_id'])
        self.assertEqual(dict(zip(ROLES, (190, 189, 190))), new['battle_progress']['1'])
        self.assertEqual({'1': 1}, new['recovery_attempts'])
        with self.assertRaises(RunChangedError):
            self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 1)
        self.run_id = new['run_id']
        self.ready()
        self.assertEqual(11, self.sync.begin_battle_segment(self.run_id, 1, 0)['remaining'])

    def test_date_rollover_does_not_reuse_old_progress(self):
        self.seed((190, 190, 190))
        new = self.sync.start_or_resume(2, 200, '2026-11-12', checkpoint_key='new-team')
        self.assertEqual({}, new['battle_progress'])
        self.assertEqual({}, new['recovery_attempts'])

    def test_changed_target_or_team_cannot_silently_reuse_progress(self):
        self.seed((190, 190, 190))
        before = self.sync.state_path.read_bytes()
        for groups, target, key in ((2, 200, 'other'), (2, 201, 'team-key'),
                                    (1, 200, 'team-key'), (2, 200, '')):
            with self.subTest(key=key, target=target), self.assertRaises(SyncStateError):
                self.sync.start_or_resume(groups, target, '2026-11-11', checkpoint_key=key)
        self.assertEqual(before, self.sync.state_path.read_bytes())

    def test_leading_role_participates_in_full_segment_and_count_is_capped(self):
        self.seed((200, 198, 199))
        plan = self.sync.begin_battle_segment(self.run_id, 1, 0)
        self.assertEqual(2, plan['remaining'])
        for role in ROLES:
            self.sync.record_battle_progress(self.run_id, 1, 0, role, 1)
            with self.assertRaises(SyncStateError):
                self.sync.update_role(self.run_id, 1, role, 'done', epoch=0)
            self.sync.record_battle_progress(self.run_id, 1, 0, role, 2)
            self.sync.update_role(self.run_id, 1, role, 'done', epoch=0)
        self.assertEqual(dict.fromkeys(ROLES, 200), self.sync.read()['battle_progress']['1'])
        state = self.sync.advance(self.run_id, 1, 'leader')
        self.assertEqual(2, state['current_group'])
        self.assertIsNone(state['battle_segment'])

    def test_all_confirmed_can_finish_without_replaying_battles(self):
        self.seed((200, 200, 200))
        self.assertEqual(0, self.sync.begin_battle_segment(self.run_id, 1, 0)['remaining'])
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, 'done', epoch=0)
        self.sync.advance(self.run_id, 1, 'leader')

    def test_persistence_failure_preserves_old_checkpoint(self):
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        with patch('tasks.MultiAccountEvo.sync.atomic_replace_with_retry', side_effect=OSError('写入失败')):
            with self.assertRaises(OSError):
                self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 1)
        self.assertEqual(0, self.sync.read()['battle_progress']['1']['leader'])
        self.assertFalse(list(self.sync.directory.glob('*.tmp')))

    def test_damaged_counts_or_segment_are_rejected(self):
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        original = self.sync.read()
        for bad in (True, -1, 201, '1'):
            state = copy.deepcopy(original)
            state['battle_progress']['1']['leader'] = bad
            with self.subTest(bad=bad), self.assertRaises(SyncStateError):
                self.sync._validate_state(state)
        state = copy.deepcopy(original)
        state['battle_segment']['remaining'] = 1
        with self.assertRaises(SyncStateError):
            self.sync._validate_state(state)

    def test_old_state_upgrade_does_not_invent_historical_battles(self):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=1)
            old = sync.start_or_resume(1, 200, '2026-11-11')
            sync.update_role(old['run_id'], 1, 'leader', 'done')
            new = sync.start_or_resume(1, 200, '2026-11-11', checkpoint_key='team-key')
            self.assertEqual({}, new['battle_progress'])

    def test_concurrent_duplicate_report_is_counted_once(self):
        self.sync.begin_battle_segment(self.run_id, 1, 0)
        errors = []
        def report():
            try:
                self.sync.record_battle_progress(self.run_id, 1, 0, 'leader', 1)
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=report) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual([], errors)
        self.assertEqual(1, self.sync.read()['battle_progress']['1']['leader'])


class BattleCheckpointTaskTest(unittest.TestCase):
    def make_task(self):
        task = object.__new__(ScriptTask)
        task._team_battle_checkpoint = Mock()
        task._wait_post_battle_state = Mock()
        return task

    def test_checkpoint_precedes_post_battle_room_failure(self):
        task = self.make_task()
        task._wait_post_battle_state.side_effect = TeamStallError('丢房')
        def battle(*args, **kwargs):
            task._team_battle_settled = True
            return True
        with patch.object(EvoTask, 'run_general_battle', side_effect=battle):
            with self.assertRaises(TeamStallError):
                task.run_general_battle()
        task._team_battle_checkpoint.assert_called_once_with()

    def test_battle_entry_or_exception_alone_does_not_count(self):
        for outcome in (True, GameStuckError('战斗中卡住')):
            task = self.make_task()
            with self.subTest(outcome=outcome), patch.object(
                EvoTask, 'run_general_battle', **(
                    {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                ),
            ):
                with self.assertRaises((TeamStallError, GameStuckError)):
                    task.run_general_battle()
            task._team_battle_checkpoint.assert_not_called()

    def test_checkpoint_failure_stops_before_more_ui_actions(self):
        task = self.make_task()
        task._team_battle_checkpoint.side_effect = OSError('写盘失败')
        def battle(*args, **kwargs):
            task._team_battle_settled = True
            return True
        with patch.object(EvoTask, 'run_general_battle', side_effect=battle):
            with self.assertRaises(OSError):
                task.run_general_battle()
        task._wait_post_battle_state.assert_not_called()
        self.assertFalse(task._is_recoverable_stall(OSError('写盘失败')))

    def test_actual_result_handler_marks_settlement(self):
        task = self.make_task()
        task.device = SimpleNamespace(click_record_clear=Mock())
        task.appear = Mock(return_value=False)
        task.click = Mock()
        context = SimpleNamespace(last_page=None)
        self.assertEqual(BattleAction.CONTINUE, task._handle_result(context, None))
        self.assertTrue(task._team_battle_settled)

    def test_invite_overlay_without_result_does_not_confirm_battle(self):
        task = self.make_task()
        task._embedded_evo_zone = EvoZone()
        task._team_battle_settled = False
        task.appear = Mock(return_value=True)
        task._post_battle_invite_step = Mock()
        task._handle_reward(SimpleNamespace(last_page=None), None)
        self.assertFalse(task._team_battle_settled)
        task._post_battle_invite_step.assert_called_once()

    def test_confirmed_loss_keeps_existing_completed_battle_count_semantics(self):
        task = self.make_task()
        def battle(*args, **kwargs):
            task._team_battle_settled = True
            return False
        with patch.object(EvoTask, 'run_general_battle', side_effect=battle):
            self.assertFalse(task.run_general_battle())
        task._team_battle_checkpoint.assert_called_once_with()
        task._wait_post_battle_state.assert_called_once_with()

    def test_all_confirmed_group_does_not_enter_embedded_or_restart_game(self):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=1)
            state = sync.start_or_resume(1, 200, checkpoint_key='team')
            run_id = state['run_id']
            for role in ROLES:
                sync.update_role(run_id, 1, role, 'ready', character=role)
            with sync._lock():
                state = sync._read_unlocked()
                state['battle_progress']['1'] = dict.fromkeys(ROLES, 200)
                sync._write_unlocked(state)
            task = self.make_task()
            task.run_embedded = Mock()
            config = SimpleNamespace(battle_count=200)
            with patch.object(sync, 'wait_all_done', return_value=state), patch(
                'tasks.MultiAccountEvo.script_task.GroupGameRestart',
            ) as restart:
                task._run_group_with_recovery(
                    config, sync, run_id, 1, 'leader', SimpleNamespace(character='leader'))
            task.run_embedded.assert_not_called()
            restart.assert_not_called()
            self.assertIsNone(task._team_battle_checkpoint)

    def test_checkpoint_key_is_stable_and_changes_with_account_identity(self):
        peers = [dict(name=name, role=role, kirin_type='雷麒麟', layer='拾层',
                      group_count=1, battle_count=200,
                      accounts=[dict(account='账号', character='角色', svr='区服', apple_or_android=False)])
                 for name, role in zip(('oas3', 'oas4', 'oas5'), ROLES)]
        key = ScriptTask._battle_checkpoint_key(peers)
        self.assertEqual(key, ScriptTask._battle_checkpoint_key(list(reversed(peers))))
        changed = copy.deepcopy(peers)
        changed[0]['accounts'][0]['svr'] = '另一区服'
        self.assertNotEqual(key, ScriptTask._battle_checkpoint_key(changed))
        self.assertEqual(64, len(key))

    def test_loaded_account_identity_must_match_fingerprinted_disk_config(self):
        task = self.make_task()
        config = MultiAccountEvo()
        task.config = SimpleNamespace(config_name='oas3', multi_account_evo=config)
        peer = dict(name='oas3', role=config.role.value, kirin_type=config.kirin_type,
                    layer=config.layer, group_count=config.group_count, battle_count=config.battle_count,
                    accounts=[{key: getattr(account, key) for key in (
                        'account', 'related_account', 'character', 'svr', 'apple_or_android')}
                        for account in config.account_list[:config.group_count]])
        task._validate_checkpoint_runtime_config([peer])
        for key, value in (('account', '另一个账号'), ('svr', '另一区服'), ('character', '另一角色'),
                           ('apple_or_android', True)):
            changed = copy.deepcopy(peer)
            changed['accounts'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'reload'):
                task._validate_checkpoint_runtime_config([changed])

    def test_three_roles_restart_from_minimum_confirmed_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=4, poll_interval=0.002)
            state = sync.start_or_resume(1, 200, checkpoint_key='team')
            run_id = state['run_id']
            for role in ROLES:
                sync.update_role(run_id, 1, role, 'ready', character=role)
            with sync._lock():
                state = sync._read_unlocked()
                state['battle_progress']['1'] = dict(zip(ROLES, (190, 189, 190)))
                sync._write_unlocked(state)
            barrier = threading.Barrier(3)
            tasks, segments, errors, restarts = {}, [], {}, []
            config = SimpleNamespace(battle_count=200, kirin_type='雷麒麟', layer='拾层')
            for role in ROLES:
                task = self.make_task()
                task.config = SimpleNamespace()
                task.device = SimpleNamespace(role=role)
                task._verify_courtyard_character = Mock(return_value=True)
                task._wait_post_battle_state = Mock()
                def embedded(*, task=task, role=role, **kwargs):
                    epoch = sync.recovery_epoch(task._team_control_check())
                    segments.append((role, epoch, kwargs['limit_count']))
                    rounds = 3 if epoch == 0 else kwargs['limit_count']
                    for _ in range(rounds):
                        task.run_general_battle()
                    if epoch == 0:
                        barrier.wait(timeout=3)
                        if role == 'leader':
                            raise GameStuckError('三场后卡住')
                        while True:
                            task._team_control_check()
                            time.sleep(0.002)
                    return True
                task.run_embedded = embedded
                tasks[role] = task
            def battle(task, *args, **kwargs):
                task._team_battle_settled = True
                return True
            def restart(config, device, check):
                def run():
                    check()
                    restarts.append(device.role)
                return SimpleNamespace(app_restart=run)
            def run(role):
                try:
                    tasks[role]._run_group_with_recovery(
                        config, sync, run_id, 1, role, SimpleNamespace(character=role))
                    if role == 'leader':
                        sync.advance(run_id, 1, role)
                except Exception as exc:
                    errors[role] = exc
                    sync.fail(run_id, 1, role, str(exc))
            with patch.object(EvoTask, 'run_general_battle', new=battle), patch(
                'tasks.MultiAccountEvo.script_task.GroupGameRestart', side_effect=restart,
            ):
                threads = [threading.Thread(target=run, args=(role,), daemon=True) for role in ROLES]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=8)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual({}, errors)
            self.assertEqual(list(ROLES), restarts)
            self.assertEqual({(role, 0, 11) for role in ROLES}, {s for s in segments if s[1] == 0})
            self.assertEqual({(role, 1, 8) for role in ROLES}, {s for s in segments if s[1] == 1})
            self.assertEqual(dict.fromkeys(ROLES, 200), sync.read()['battle_progress']['1'])
            self.assertTrue(sync.read()['complete'])
            self.assertTrue(all(task._team_battle_checkpoint is None for task in tasks.values()))


if __name__ == '__main__':
    unittest.main()
