"""验证三端卡死恢复、强制游戏重启和同组重跑，全程不连接设备。"""

import json
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError, RequestHumanTakeover, ScriptError
from tasks.EvoZone.script_task import ScriptTask as EvoZoneTask
from tasks.MultiAccountEvo.recovery import GroupGameRestart, TeamStallError
from tasks.MultiAccountEvo.script_task import ScriptTask
from tasks.MultiAccountEvo.sync import (
    ROLES, MultiAccountEvoSync, PeerFailedError, RecoveryExhausted,
    RecoveryRequested, RunChangedError, SyncLockError, SyncStateError, SyncTimeoutError,
)


class ControlCheckThrottleTest(unittest.TestCase):
    """高频控制检查复用本进程状态，避免每帧创建/删除共享锁文件。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sync = MultiAccountEvoSync(self.temp.name, timeout=0.15, poll_interval=0.002)
        self.run_id = self.sync.start_or_resume(2, 20, run_date="2026-10-15")["run_id"]
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, "ready", character=role)

    def test_throttled_checks_do_not_touch_lock_within_interval(self):
        self.sync.read()
        with patch.object(self.sync, "_lock", side_effect=AssertionError("不应加锁")):
            for _ in range(50):
                self.sync.assert_active(self.run_id, 1, max_age=10)

    def test_throttled_check_still_waits_for_lock_after_interval(self):
        self.sync.read()
        with patch.object(self.sync, "_lock", side_effect=SyncLockError("锁被占用")):
            with self.assertRaises(SyncLockError):
                self.sync.assert_active(self.run_id, 1, max_age=0)
        self.sync._last_state = (time.monotonic() - 5, self.sync._last_state[1])
        with patch.object(self.sync, "_lock", side_effect=SyncLockError("锁被占用")):
            with self.assertRaises(SyncLockError):
                self.sync.assert_active(self.run_id, 1, max_age=1)

    def test_peer_change_is_seen_after_interval(self):
        other = MultiAccountEvoSync(self.temp.name, timeout=0.15, poll_interval=0.002)
        self.sync.assert_active(self.run_id, 1, max_age=0.05)
        other.request_recovery(self.run_id, 1, "member_1", "Wait too long")
        # 间隔内复用旧状态，超过间隔后必须读到队友发起的恢复。
        self.sync.assert_active(self.run_id, 1, max_age=10)
        time.sleep(0.06)
        with self.assertRaises(RecoveryRequested):
            self.sync.assert_active(self.run_id, 1, max_age=0.05)

    def test_own_write_refreshes_cache_immediately(self):
        self.sync.assert_active(self.run_id, 1, max_age=10)
        self.sync.request_recovery(self.run_id, 1, "leader", "Wait too long")
        with self.assertRaises(RecoveryRequested):
            self.sync.assert_active(self.run_id, 1, max_age=10)
        self.assertEqual(1, self.sync.assert_recovering(self.run_id, 1, 1, max_age=10)["recovery"]["epoch"])

    def test_cached_state_cannot_be_mutated_by_caller(self):
        state = self.sync.assert_active(self.run_id, 1, max_age=10)
        state["current_group"] = 99
        self.assertEqual(1, self.sync.assert_active(self.run_id, 1, max_age=10)["current_group"])


class RecoverySyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sync = MultiAccountEvoSync(self.temp.name, timeout=0.15, poll_interval=0.002)
        self.state = self.sync.start_or_resume(2, 20, run_date="2026-10-15")
        self.run_id = self.state["run_id"]
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, "ready", character=role)

    def request(self):
        return self.sync.request_recovery(self.run_id, 1, "leader", "Wait too long")

    def finish(self):
        self.request()
        for role in ROLES:
            self.sync.acknowledge_recovery(self.run_id, 1, 1, role, "paused")
        for role in ROLES:
            self.sync.acknowledge_recovery(self.run_id, 1, 1, role, "restarted")
        return self.sync.finish_recovery(self.run_id, 1, 1, "leader")

    def test_complete_recovery_preserves_characters_and_group(self):
        state = self.finish()
        self.assertEqual(1, state["current_group"])
        self.assertFalse(state["complete"])
        self.assertEqual({"1": 1}, state["recovery_attempts"])
        for role in ROLES:
            self.assertEqual("ready", state["roles"][role]["status"])
            self.assertEqual(role, state["roles"][role]["character"])
        self.assertEqual(1, self.sync.assert_active(self.run_id, 1, epoch=1)["recovery"]["epoch"])

    def test_concurrent_requests_consume_one_attempt(self):
        self.sync.timeout = 2
        barrier = threading.Barrier(3)
        results, errors = [], []

        def request(role):
            try:
                barrier.wait(timeout=1)
                results.append(self.sync.request_recovery(self.run_id, 1, role, role))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=request, args=(role,)) for role in ROLES]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual([], errors)
        self.assertEqual([1, 1, 1], [item["recovery"]["epoch"] for item in results])
        self.assertEqual({"1": 1}, self.sync.read()["recovery_attempts"])

    def test_active_and_done_waits_interrupt_even_if_old_roles_are_done(self):
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, "done", character=role)
        self.request()
        for operation in (
            lambda: self.sync.assert_active(self.run_id, 1),
            lambda: self.sync.wait_all_ready(self.run_id, 1),
            lambda: self.sync.wait_all_done(self.run_id, 1),
            lambda: self.sync.wait_for_advance(self.run_id, 1),
        ):
            with self.subTest(operation=operation), self.assertRaises(RecoveryRequested):
                operation()

    def test_game_restart_requires_all_paused_and_predecessors(self):
        self.request()
        with self.assertRaises(SyncStateError):
            self.sync.acknowledge_recovery(self.run_id, 1, 1, "leader", "restarted")
        for role in ROLES:
            self.sync.acknowledge_recovery(self.run_id, 1, 1, role, "paused")
        with self.assertRaises(SyncStateError):
            self.sync.acknowledge_recovery(self.run_id, 1, 1, "member_1", "restarted")

    def test_pause_barrier_times_out_when_peer_never_responds(self):
        self.request()
        self.sync.acknowledge_recovery(self.run_id, 1, 1, "leader", "paused")
        with self.assertRaises(SyncTimeoutError):
            self.sync.wait_recovery_stage(self.run_id, 1, 1, "paused")

    def test_expired_shared_deadline_cannot_be_reset_by_a_new_wait_stage(self):
        self.request()
        with patch('tasks.MultiAccountEvo.sync.time.monotonic', return_value=10):
            with self.assertRaises(SyncTimeoutError):
                self.sync.wait_recovery_stage(self.run_id, 1, 1, 'restarted', (), deadline=9)

    def test_old_epoch_cannot_ack_or_write_done(self):
        self.request()
        with self.assertRaises(RunChangedError):
            self.sync.acknowledge_recovery(self.run_id, 1, 0, "leader", "paused")
        with self.assertRaises(RecoveryRequested):
            self.sync.update_role(self.run_id, 1, "leader", "done", epoch=0)
        self.finish()
        with self.assertRaises(RunChangedError):
            self.sync.update_role(self.run_id, 1, "leader", "done", epoch=0)
        with self.assertRaises(RunChangedError):
            self.sync.acknowledge_recovery(self.run_id, 1, 1, "leader", "paused")

    def test_only_leader_can_finish_after_all_restarts(self):
        self.request()
        with self.assertRaises(SyncStateError):
            self.sync.finish_recovery(self.run_id, 1, 1, "member_1")
        with self.assertRaises(SyncStateError):
            self.sync.finish_recovery(self.run_id, 1, 1, "leader")
        with self.assertRaises(RecoveryRequested):
            self.sync.advance(self.run_id, 1, "leader")

    def test_second_stall_exhausts_budget_and_task_restart_does_not_reset_it(self):
        self.finish()
        with self.assertRaises(RecoveryExhausted):
            self.request()
        state = self.sync.start_or_resume(2, 20, run_date="2026-10-15")
        with self.assertRaises(RecoveryExhausted):
            self.sync.request_recovery(state["run_id"], 1, "leader", "again")
        state = self.sync.start_or_resume(2, 20, run_date="2026-10-16")
        self.sync.request_recovery(state["run_id"], 1, "leader", "new day")

    def test_next_group_has_own_budget(self):
        self.finish()
        for role in ROLES:
            self.sync.update_role(self.run_id, 1, role, "done", character=role, epoch=1)
        self.sync.advance(self.run_id, 1, "leader")
        state = self.sync.request_recovery(self.run_id, 2, "member_1", "new group")
        self.assertEqual({"1": 1, "2": 1}, state["recovery_attempts"])

    def test_peer_failure_stops_recovery_waits_and_cannot_start_new_recovery(self):
        self.request()
        self.sync.fail(self.run_id, 1, "member_1", "login failed")
        for operation in (
            lambda: self.sync.assert_recovering(self.run_id, 1, 1),
            lambda: self.sync.wait_recovery_stage(self.run_id, 1, 1, "restarted"),
            self.request,
        ):
            with self.subTest(operation=operation), self.assertRaises(PeerFailedError):
                operation()

    def test_old_json_without_recovery_fields_remains_readable(self):
        state = self.sync.read()
        del state["recovery"]
        del state["recovery_attempts"]
        self.sync.state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(0, self.sync.recovery_epoch(self.sync.assert_active(self.run_id, 1)))
        self.assertEqual(1, self.request()["recovery"]["epoch"])

    def test_damaged_recovery_state_is_rejected(self):
        for value in ([], {"phase": "invalid"}, {"epoch": -1}, {"phase": "recovering"}):
            with self.subTest(value=value):
                state = dict(self.state, recovery=value)
                with self.assertRaises(SyncStateError):
                    self.sync._validate_state(state)

    def test_transient_windows_lock_permission_error_is_retried(self):
        import os
        original = os.open
        calls = []

        def open_lock(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                raise PermissionError('delete pending')
            return original(*args, **kwargs)

        with patch('tasks.MultiAccountEvo.sync.os.open', side_effect=open_lock):
            self.assertEqual(self.run_id, self.sync.read()['run_id'])
        self.assertEqual(2, len(calls))

    def test_persistent_lock_permission_error_is_bounded(self):
        with patch('tasks.MultiAccountEvo.sync.os.open', side_effect=PermissionError('denied')), patch(
            'tasks.MultiAccountEvo.sync.time.monotonic', side_effect=[0, 1],
        ):
            with self.assertRaises(SyncLockError):
                self.sync.read()


class GameRestartAdapterTest(unittest.TestCase):
    def make_restart(self):
        task = object.__new__(GroupGameRestart)
        task.config = SimpleNamespace(task_call=Mock(), restart=SimpleNamespace(scheduler=SimpleNamespace(enable=False)))
        task.device = Mock()
        task._recovery_check = Mock()
        return task

    def test_force_stop_start_login_without_daily_or_scheduler_changes(self):
        task = self.make_restart()
        login = SimpleNamespace(screenshot=Mock(), app_handle_login=Mock())
        with patch('tasks.MultiAccountEvo.recovery.LoginService', return_value=login):
            task.app_restart()
        self.assertEqual(['app_stop', 'app_start', 'wait_app_start_ready'],
                         [call[0] for call in task.device.mock_calls])
        login.app_handle_login.assert_called_once_with()
        task.config.task_call.assert_not_called()
        self.assertFalse(task.config.restart.scheduler.enable)

    def test_terminal_check_prevents_game_stop(self):
        task = self.make_restart()
        task._recovery_check.side_effect = PeerFailedError('stop')
        with self.assertRaises(PeerFailedError):
            task.app_restart()
        task.device.app_stop.assert_not_called()

    def test_login_failure_propagates_without_rescheduling(self):
        task = self.make_restart()
        login = SimpleNamespace(screenshot=Mock(), app_handle_login=Mock(side_effect=RequestHumanTakeover('login')))
        with patch('tasks.MultiAccountEvo.recovery.LoginService', return_value=login):
            with self.assertRaises(RequestHumanTakeover):
                task.app_restart()
        task.config.task_call.assert_not_called()

    def test_login_checks_control_after_new_screenshot(self):
        task = self.make_restart()
        alive = [True]

        def check():
            if not alive[0]:
                raise PeerFailedError('peer failed')

        task._recovery_check = check
        shot = Mock(side_effect=lambda: alive.__setitem__(0, False))
        login = SimpleNamespace(screenshot=shot)
        login.app_handle_login = lambda: login.screenshot()
        with patch('tasks.MultiAccountEvo.recovery.LoginService', return_value=login):
            with self.assertRaises(PeerFailedError):
                task.app_restart()
        shot.assert_called_once_with()


class RecoveryTaskTest(unittest.TestCase):
    def test_snapshot_hook_interrupts_inner_wait_before_device_access(self):
        task = object.__new__(ScriptTask)
        task._team_control_check = Mock(side_effect=RecoveryRequested(1))
        with patch.object(EvoZoneTask, 'screenshot') as screenshot:
            with self.assertRaises(RecoveryRequested):
                task.screenshot()
        screenshot.assert_not_called()

    def test_snapshot_hook_checks_after_capture_too(self):
        task = object.__new__(ScriptTask)
        task._team_control_check = Mock(side_effect=[None, RecoveryRequested(1)])
        with patch.object(EvoZoneTask, 'screenshot') as screenshot:
            with self.assertRaises(RecoveryRequested):
                task.screenshot()
        screenshot.assert_called_once_with()

    def test_only_known_team_and_game_stalls_are_recoverable(self):
        self.assertTrue(ScriptTask._is_recoverable_stall(GameStuckError('stuck')))
        self.assertTrue(ScriptTask._is_recoverable_stall(TeamStallError('room')))
        for exc in (ScriptError('bad config'), ValueError('account'), RequestHumanTakeover('login'),
                    SyncStateError('corrupt file'), RunChangedError('other run')):
            with self.subTest(exc=exc):
                self.assertFalse(ScriptTask._is_recoverable_stall(exc))

    def run_three_roles(self, *, fail_again=False, bad_character=False, early_done=False):
        with tempfile.TemporaryDirectory() as directory:
            sync = MultiAccountEvoSync(directory, timeout=3, poll_interval=0.002)
            state = sync.start_or_resume(1, 20)
            run_id = state['run_id']
            for role in ROLES:
                sync.update_role(run_id, 1, role, 'ready', character=role)
            tasks, errors, restart_order, segments = {}, {}, [], []
            config = SimpleNamespace(battle_count=20, kirin_type='kirin', layer='layer')
            for role in ROLES:
                task = object.__new__(ScriptTask)
                task.config = SimpleNamespace()
                task.device = SimpleNamespace(role=role)
                task._verify_courtyard_character = Mock(return_value=not (bad_character and role == 'leader'))
                tasks[role] = task

                def run_embedded(*, role=role, task=task, **kwargs):
                    epoch = sync.recovery_epoch(task._team_control_check())
                    segments.append((role, epoch, kwargs['limit_count']))
                    if role == 'leader' and (epoch == 0 or fail_again):
                        if early_done and epoch == 0:
                            for _ in range(500):
                                if sync.read()['roles']['member_1']['status'] == 'done':
                                    break
                                time.sleep(0.002)
                            else:
                                raise AssertionError('member did not finish old segment')
                        raise GameStuckError('Wait too long')
                    if epoch == 0 and not (early_done and role == 'member_1'):
                        for _ in range(1000):
                            task.screenshot()
                            time.sleep(0.002)
                        raise AssertionError('inner wait did not receive recovery')
                    return True

                task.run_embedded = run_embedded

            def restart_factory(config, device, check):
                def restart():
                    check()
                    self.assertEqual(set(ROLES), set(sync.read()['recovery']['paused']))
                    restart_order.append(device.role)
                    check()
                return SimpleNamespace(app_restart=restart)

            def run(role):
                try:
                    tasks[role]._run_group_with_recovery(
                        config, sync, run_id, 1, role, SimpleNamespace(character=role),
                    )
                    if role == 'leader':
                        sync.advance(run_id, 1, role)
                except Exception as exc:
                    errors[role] = exc
                    sync.fail(run_id, 1, role, str(exc))

            with patch.object(EvoZoneTask, 'screenshot'), patch(
                'tasks.MultiAccountEvo.script_task.GroupGameRestart', side_effect=restart_factory,
            ):
                threads = [threading.Thread(target=run, args=(role,), daemon=True) for role in ROLES]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
                self.assertFalse(any(thread.is_alive() for thread in threads))
            final = sync.read()
            self.assertTrue(all(getattr(task, '_team_control_check', None) is None for task in tasks.values()))
            return final, errors, restart_order, segments

    def test_real_shared_file_coordinates_restart_and_same_group_retry(self):
        state, errors, order, segments = self.run_three_roles()
        self.assertEqual({}, errors)
        self.assertEqual(list(ROLES), order)
        self.assertTrue(state['complete'])
        self.assertEqual({(role, 1, 20) for role in ROLES}, {item for item in segments if item[1] == 1})

    def test_member_already_waiting_for_advance_also_retries(self):
        state, errors, order, segments = self.run_three_roles(early_done=True)
        self.assertEqual({}, errors)
        self.assertTrue(state['complete'])
        self.assertIn(('member_1', 0, 20), segments)
        self.assertIn(('member_1', 1, 20), segments)
        self.assertEqual(list(ROLES), order)

    def test_second_stall_stops_all_roles_without_another_restart(self):
        state, errors, order, segments = self.run_three_roles(fail_again=True)
        self.assertEqual(set(ROLES), set(errors))
        self.assertIsInstance(errors['leader'], RecoveryExhausted)
        self.assertEqual(list(ROLES), order)
        self.assertFalse(state['complete'])
        self.assertEqual(1, state['current_group'])

    def test_wrong_character_stops_before_other_games_restart(self):
        state, errors, order, segments = self.run_three_roles(bad_character=True)
        self.assertEqual(set(ROLES), set(errors))
        self.assertEqual(['leader'], order)
        self.assertFalse(state['complete'])
        self.assertFalse(any(item[1] == 1 for item in segments))


if __name__ == '__main__':
    unittest.main()
