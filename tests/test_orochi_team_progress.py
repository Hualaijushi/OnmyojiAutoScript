# This Python file uses the following encoding: utf-8
"""御魂组队：次数以队长为准（D030 修订二）。

事故背景：队长和队员各自数 `current_count`，队长点了挑战却没真正开战也会 +1，两边就差一次（实测 100 / 99）：
队长先数满走人，队员在房间空等邀请到超时；或队员先走，队长邀请失败、任务判失败。

修复：组队同步会合后队长把已打次数和「打完了」写进在场文件，队员不按自己的计数走，队长打完才走并对齐次数。
没有会话（没开同步 / 单人 / 出错）时行为和以前一字不差。
测试驱动真实 `run_leader` / `run_member` / `run`，只替换截图 / 识别 / 邀请 / 房间 / 战斗 / 导航这些外部边界。
"""

import ast
import inspect
import textwrap
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from module.instance_sync.team import Progress, clear_session, set_session
from tasks.Orochi import script_task as orochi
from tasks.Orochi.config import UserStatus
from tasks.Orochi.script_task import ScriptTask


class _StillWaiting(Exception):
    """队员仍在等待：让「继续等待」的无限循环在断言处停下。"""


def _config(status=UserStatus.MEMBER):
    return SimpleNamespace(
        config_name='oas_test',
        orochi=SimpleNamespace(
            orochi_config=SimpleNamespace(user_status=status, layer='十一层', limit_count=100,
                                          limit_time=time(hour=1), soul_buff_enable=False,
                                          check_true_orochi_enable=False),
            invite_config=SimpleNamespace(wait_time=time(minute=2), default_invite=False),
            general_battle_config=SimpleNamespace(lock_team_enable=True),
            fire_reaction=None,
        ))


class _Base(TestCase):
    def setUp(self):
        patcher = patch.object(orochi, 'logger')
        self.logger = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(clear_session, 'oas_test')

    def info(self, text):
        return any(text in call.args[0] for call in self.logger.info.call_args_list)


class MemberTest(_Base):
    def make(self, *, count, limit=100, session=None, max_accept_calls=8, time_used=timedelta(0)):
        task = ScriptTask.__new__(ScriptTask)
        task.config = _config()
        task.start_time = datetime.now() - time_used
        task.limit_time = timedelta(hours=1)
        task.current_count = count
        task.limit_count = limit
        task.team_session = session
        task.device = SimpleNamespace(stuck_record_add=Mock(), stuck_record_clear=Mock())
        task._orochi_battle_key = lambda: 'orochi_test'
        task.screenshot = Mock()
        task.appear_then_click = Mock(return_value=False)
        task.appear = lambda target, *a, **k: target is task.I_CHECK_MAIN       # 收尾循环里认为已回到庭院

        def check_then_accept():
            if task.check_then_accept.call_count > max_accept_calls:
                raise _StillWaiting
            return False

        task.check_then_accept = Mock(side_effect=check_then_accept)
        task.is_in_room = Mock(return_value=False)
        task.is_in_battle = Mock(return_value=False)
        task.wait_battle = Mock(return_value=False)
        task.run_general_battle = Mock()
        task.exit_room = Mock(return_value=False)
        task.exit_battle = Mock(return_value=False)
        return task

    @staticmethod
    def leader(*progress):
        """依次返回给定的进度，最后一个一直重复。"""
        queue = list(progress)
        return SimpleNamespace(peer_progress=Mock(side_effect=lambda: queue.pop(0) if len(queue) > 1 else queue[0]))

    def test_member_does_not_leave_by_its_own_count_while_the_leader_is_still_playing(self):
        # 事故：队员数到 100 就走，队长其实只打了 99 场，下一场邀请不到人
        leader = self.leader(Progress(99, False))
        task = self.make(count=100, session=leader)
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 0), self.assertRaises(_StillWaiting):
            task.run_member()
        self.assertGreater(task.check_then_accept.call_count, 1)                # 一直在等队长的下一场邀请

    def test_member_leaves_when_the_leader_is_done_and_aligns_the_count(self):
        leader = self.leader(Progress(99, False), Progress(99, True))
        task = self.make(count=100, session=leader)
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 0):
            self.assertTrue(task.run_member())
        self.assertEqual(task.current_count, 99)                                # 对齐到队长的次数
        self.assertTrue(self.info('leader finished Orochi at 99, member counted 100'))

    def test_member_behind_the_leader_catches_up_to_the_leader_count(self):
        leader = self.leader(Progress(100, True))
        task = self.make(count=98, session=leader)
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 0):
            task.run_member()
        self.assertEqual(task.current_count, 100)

    def test_member_leaves_when_the_leader_left_without_a_count(self):
        leader = self.leader(Progress(None, True))
        task = self.make(count=7, session=leader)
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 0):
            task.run_member()
        self.assertEqual(task.current_count, 7)
        task.check_then_accept.assert_not_called()
        self.assertTrue(self.info('leader left Orochi'))

    def test_time_limit_is_still_the_fallback_when_the_leader_never_finishes(self):
        leader = self.leader(Progress(None, False))
        task = self.make(count=3, session=leader, time_used=timedelta(hours=2))
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 0):
            self.assertTrue(task.run_member())
        task.check_then_accept.assert_not_called()
        self.assertTrue(self.info('Orochi time limit out'))

    def test_leader_file_is_read_at_most_once_per_interval(self):
        leader = self.leader(Progress(1, False))
        task = self.make(count=1, session=leader, max_accept_calls=30)
        with patch.object(orochi, 'OROCHI_TEAM_POLL_INTERVAL', 3600), self.assertRaises(_StillWaiting):
            task.run_member()
        self.assertGreater(task.check_then_accept.call_count, 20)
        leader.peer_progress.assert_called_once()

    def test_without_a_session_the_member_still_leaves_by_its_own_count(self):
        task = self.make(count=100, limit=100, session=None)
        self.assertTrue(task.run_member())
        task.check_then_accept.assert_not_called()
        self.assertTrue(self.info('Orochi count limit out'))

    def test_without_a_session_below_the_limit_keeps_waiting(self):
        task = self.make(count=99, limit=100, session=None)
        with self.assertRaises(_StillWaiting):
            task.run_member()


class LeaderTest(_Base):
    def make(self, *, invites=(True,), limit=2, session=None):
        """invites：每次 run_invite 的返回值；战斗打一场 +1。"""
        task = ScriptTask.__new__(ScriptTask)
        task.config = _config(UserStatus.LEADER)
        task.start_time = datetime.now()
        task.limit_time = timedelta(hours=1)
        task.current_count = 0
        task.limit_count = limit
        task.team_session = session
        task._orochi_battle_key = lambda: 'orochi_test'
        self.events = []
        events = self.events
        invites = list(invites)

        task.goto_page = Mock()
        task.check_layer = Mock(return_value=True)
        task.check_lock = Mock()
        task.screenshot = Mock()
        task.appear = Mock(return_value=True)
        task.appear_then_click = Mock(return_value=False)
        task.create_room = Mock()
        task.ensure_private = Mock()
        task.create_ensure = Mock()
        task.is_in_room = Mock(return_value=True)
        task.is_room_dead = Mock(return_value=False)
        task.run_invite = Mock(side_effect=lambda **kw: invites.pop(0) if invites else True)

        def battle(**kw):
            task.current_count += 1
            events.append(f'battle {task.current_count}')

        task.run_general_battle = Mock(side_effect=battle)
        task.exit_room = Mock(side_effect=lambda: events.append('exit_room') or True)
        task.exit_team = Mock(side_effect=lambda: events.append('exit_team') or True)
        return task

    def session(self):
        session = SimpleNamespace()
        session.report = Mock(side_effect=lambda count, done=False: self.events.append(f'report {count} {done}'))
        return session

    def test_leader_reports_each_battle_then_done_before_leaving_the_room(self):
        session = self.session()
        task = self.make(limit=2, session=session)
        self.assertTrue(task.run_leader())
        self.assertEqual(self.events, ['battle 1', 'report 1 False', 'battle 2', 'report 2 False',
                                       'report 2 True', 'exit_room', 'exit_team'])

    def test_leader_reports_done_when_the_invite_fails(self):
        session = self.session()
        task = self.make(invites=(False,), limit=5, session=session)
        self.assertFalse(task.run_leader())
        self.assertEqual(self.events, ['report 0 True', 'exit_room', 'exit_team'])

    def test_leader_reports_done_on_the_time_limit(self):
        session = self.session()
        task = self.make(limit=100, session=session)
        task.start_time = datetime.now() - timedelta(hours=2)
        self.assertTrue(task.run_leader())
        self.assertEqual(self.events, ['report 0 True', 'exit_room', 'exit_team'])

    def test_without_a_session_the_leader_behaves_as_before(self):
        task = self.make(limit=2, session=None)
        self.assertTrue(task.run_leader())
        self.assertEqual(self.events, ['battle 1', 'battle 2', 'exit_room', 'exit_team'])


class RunTest(_Base):
    """`run()` 在开始时按实例名取会话，且只取御魂的。"""

    def make(self, status):
        task = ScriptTask.__new__(ScriptTask)
        task.config = _config(status)
        task.switch_orochi_souls = Mock()
        task.is_in_battle = Mock(return_value=False)
        task.goto_page = Mock()
        task.set_next_run = Mock()
        self.seen = []
        record = lambda: self.seen.append(task.team_session) or True
        task.run_leader = Mock(side_effect=record)
        task.run_member = Mock(side_effect=record)
        return task

    def test_run_picks_up_the_session_registered_for_this_instance(self):
        session = SimpleNamespace(task='Orochi')
        set_session('oas_test', session)
        for status in (UserStatus.LEADER, UserStatus.MEMBER):
            with self.subTest(status=status):
                task = self.make(status)
                with self.assertRaises(TaskEnd):
                    task.run()
                self.assertEqual(self.seen, [session])

    def test_run_ignores_a_session_of_another_task(self):
        set_session('oas_test', SimpleNamespace(task='BondlingFairyland'))
        task = self.make(UserStatus.MEMBER)
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(self.seen, [None])

    def test_run_without_any_session(self):
        task = self.make(UserStatus.LEADER)
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(self.seen, [None])


class StructureGuardTest(TestCase):
    @staticmethod
    def _src(func):
        return textwrap.dedent(inspect.getsource(func))

    def test_member_loop_keeps_time_limit_and_wait_battle_fallbacks(self):
        src = self._src(ScriptTask.run_member)
        self.assertIn('self._member_count_reached()', src)
        self.assertIn("logger.info('Orochi time limit out')", src)
        self.assertIn('self.wait_battle(', src)
        self.assertNotIn('self.current_count >= self.limit_count', src)         # 队员不再直接按自己的计数走

    def test_leader_reports_done_between_the_loop_and_leaving_the_room(self):
        src = self._src(ScriptTask.run_leader)
        self.assertLess(src.index('self._team_report(done=True)'), src.index('self.exit_room()'))
        # 首场和后续每场都经过 _leader_fight_once，每场战斗之后在里面上报一次
        self.assertEqual(src.count('self._leader_fight_once('), 2)
        self.assertEqual(self._src(ScriptTask._leader_fight_once).count('self._team_report()'), 1)

    def test_member_check_precedes_the_time_limit_and_the_accept(self):
        tree = ast.parse(self._src(ScriptTask.run_member))
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.While))
        tests = [ast.unparse(stmt.test) for stmt in loop.body if isinstance(stmt, ast.If)]
        self.assertLess(tests.index('self._member_count_reached()'),
                        tests.index('datetime.now() - self.start_time >= self.limit_time'))
