# This Python file uses the following encoding: utf-8
"""契灵组队：队员按自己的战斗次数收尾。

事故（2026-10-13 oas1 队长 / oas2 队员，limit_count=100）：两边同一场打到 `Current count: 100`；队长按
`current_count >= limit_count` 拉人进房后退出（12:27:06），队员的同一检查自 bab92bac（2025-09-30）起被注释，
进房等待；队长退房后队员被退回契灵主界面，`wait_battle` 按 07-17（ba0e8d46）的「接受邀请过慢」返回 None，
队员继续等邀请，直到 120 秒邀请计时器到点（12:28:58）才退出。

修复：`run_member` 主循环恢复计数退出；`wait_battle` 的判断（含 07-17 的接受邀请过慢）一行不改。
测试驱动真实 `run_member`，只替换截图 / 识别 / 邀请 / 房间 / 战斗 / 导航这些外部边界。
"""

import ast
import inspect
import textwrap
from datetime import datetime, time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from tasks.BondlingFairyland import script_task as bf
from tasks.BondlingFairyland.config import UserStatus
from tasks.BondlingFairyland.script_task import ScriptTask


class _StillWaiting(Exception):
    """队员仍在等待邀请：让「继续等待」的无限循环在断言处停下。"""


class MemberWorld(TestCase):
    """队员侧的假世界：`place` 是当前所在画面，房间 / 战斗 / 邀请按脚本推进。"""

    def setUp(self):
        patcher = patch.object(bf, 'logger')
        self.logger = patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, *, count, limit=100, status=UserStatus.MEMBER, invites=(), battles=(), in_battle=(),
             max_accept_calls=6):
        """
        :param invites: 每轮 `check_then_accept` 的返回值（超出长度一律 False），True 表示接了邀请
        :param battles: 每次 `wait_battle` 的返回值（True 进战斗 / None 接受邀请过慢 / False 房间销毁）
        :param in_battle: 每轮 `is_in_battle` 的返回值（队长秒开），超出长度一律 False
        """
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(bondling_fairyland=SimpleNamespace(
            invite_config=SimpleNamespace(wait_time=time(minute=2)),
            bondling_config=SimpleNamespace(user_status=status, limit_time=time(hour=1)),
            battle_config=object()))
        task.start_time = datetime.now()
        task.current_count = count
        task.limit_count = limit
        task.device = SimpleNamespace(stuck_record_add=Mock())
        self.place = 'room'                                                # 打完上一场后队员回到房间
        self.events = []
        world = self
        invites, battles, in_battle = list(invites), list(battles), list(in_battle)

        def screenshot():
            world.events.append('screenshot')

        def check_then_accept():
            n = task.check_then_accept.call_count
            if n > max_accept_calls:
                raise _StillWaiting
            accepted = invites[n - 1] if n - 1 < len(invites) else False
            if accepted:
                world.place = 'room'
            return accepted

        def wait_battle(wait_time):
            result = battles.pop(0)
            if result is None:
                world.place = 'bondling'                                   # 接受邀请过慢：被退回契灵主界面
            return result

        def run_general_battle(config):
            task.current_count += 1
            world.place = 'room'
            world.events.append(f'battle {task.current_count}')

        def exit_room():
            world.events.append('exit_room')
            world.place = 'bondling'
            return True

        visible_on = {
            'bondling': (task.I_CHECK_BONDLING_FAIRYLAND, task.I_BALL_AREA),
            'main': (task.I_CHECK_MAIN,),
            'room': (),
        }

        task.screenshot = screenshot
        task.appear = lambda target, *a, **k: any(target is item for item in visible_on.get(world.place, ()))
        task.check_then_accept = Mock(side_effect=check_then_accept)
        task.is_in_room = Mock(side_effect=lambda is_screenshot=True: world.place == 'room')
        task.is_in_battle = Mock(side_effect=lambda is_screenshot=True: in_battle.pop(0) if in_battle else False)
        task.wait_battle = Mock(side_effect=wait_battle)
        task.run_general_battle = Mock(side_effect=run_general_battle)
        task.exit_room = Mock(side_effect=exit_room)
        task.exit_battle = Mock(return_value=False)
        task.goto_page = Mock()
        task.set_next_run = Mock()
        return task

    def assert_member_finished(self, task):
        task.goto_page.assert_called_once_with(bf.page_main)
        task.set_next_run.assert_called_once_with(task='BondlingFairyland', finish=True, success=True)

    def info(self, text):
        return any(text in call.args[0] for call in self.logger.info.call_args_list)


# ======================================================================================
# Case 1：达到 limit_count 直接收尾，不再等邀请
# ======================================================================================

class LimitReachedTest(MemberWorld):
    def test_case1_already_at_limit_finishes_without_waiting_for_an_invite(self):
        task = self.make(count=100, limit=100)
        with self.assertRaises(TaskEnd):
            task.run_member()
        task.check_then_accept.assert_not_called()
        task.wait_battle.assert_not_called()
        task.exit_room.assert_called_once()                                # 还在房间：走原有收尾退出房间
        self.assert_member_finished(task)
        self.assertTrue(self.info('契灵队员次数:100已完成,退出'))

    def test_case1_reaching_the_limit_in_the_last_battle_finishes_right_after_it(self):
        # 事故时序：第 99 场后进房、打第 100 场；旧代码这里会再进房等 120 秒
        task = self.make(count=99, limit=100, battles=(True,))
        with self.assertRaises(TaskEnd):
            task.run_member()
        self.assertEqual(task.current_count, 100)
        task.wait_battle.assert_called_once()                              # 只等了第 100 场那一次
        task.check_then_accept.assert_called_once()                        # 打完第 100 场不再接邀请
        # 打完第 100 场：下一轮循环头截一帧就收尾，接着由原有收尾退出房间
        self.assertEqual(self.events[-3:], ['battle 100', 'screenshot', 'exit_room'])
        task.exit_room.assert_called_once()
        self.assert_member_finished(task)

    def test_case1_limit_reached_through_an_instant_start_battle_also_finishes(self):
        # 队长秒开（队员直接进战斗）分支同样回到循环头检查次数
        task = self.make(count=99, limit=100, in_battle=(True,))
        self.place = 'invite'                                              # 既不在房间也不在主界面
        with self.assertRaises(TaskEnd):
            task.run_member()
        task.run_general_battle.assert_called_once()
        task.wait_battle.assert_not_called()
        self.assert_member_finished(task)


# ======================================================================================
# Case 2 / 3：未达到时保持原逻辑；接受邀请过慢 / 计时器兜底 / 房间销毁都不变
# ======================================================================================

class BelowLimitTest(MemberWorld):
    def test_case2_below_the_limit_keeps_waiting_for_invites(self):
        task = self.make(count=99, limit=100)
        self.place = 'bondling'
        with self.assertRaises(_StillWaiting):
            task.run_member()
        self.assertGreater(task.check_then_accept.call_count, 1)
        task.goto_page.assert_not_called()
        task.exit_room.assert_not_called()

    def test_case3_late_invitation_still_continues_waiting(self):
        task = self.make(count=50, limit=100, battles=(None,))
        with self.assertRaises(_StillWaiting):
            task.run_member()
        task.wait_battle.assert_called_once()
        task.run_general_battle.assert_not_called()
        task.exit_room.assert_not_called()                                 # 07-17：不按房间销毁结束
        task.goto_page.assert_not_called()
        self.assertTrue(self.info('邀请接受过慢'))

    def test_case3_late_invitation_then_the_last_battle_finishes_by_count(self):
        task = self.make(count=99, limit=100, invites=(False, True), battles=(None, True))
        with self.assertRaises(TaskEnd):
            task.run_member()
        self.assertEqual(task.wait_battle.call_count, 2)                   # 过慢一次后接下一轮邀请打第 100 场
        self.assertEqual(task.current_count, 100)
        self.assert_member_finished(task)

    def test_room_destroyed_still_ends_below_the_limit(self):
        task = self.make(count=10, limit=100, battles=(False,))
        with self.assertRaises(TaskEnd):
            task.run_member()
        task.wait_battle.assert_called_once()
        self.assert_member_finished(task)

    def test_invite_wait_timer_is_still_the_fallback_below_the_limit(self):
        class _ReachedTimer:
            def __init__(self, limit):
                self.limit = limit

            def start(self):
                return self

            def reset(self):
                return self

            def reached(self):
                return True

            def current(self):
                return self.limit

        task = self.make(count=10, limit=100)
        self.place = 'bondling'
        with patch.object(bf, 'Timer', _ReachedTimer), self.assertRaises(TaskEnd):
            task.run_member()
        task.check_then_accept.assert_not_called()
        self.assertTrue(self.info('队员等待超时'))
        self.assertFalse(self.info('契灵队员次数'))


# ======================================================================================
# handoff2：队员阶段按 limit_count // 2 结束后正常返回，交给 run() 转队长
# ======================================================================================

class HandoffTest(MemberWorld):
    def test_handoff_member_phase_returns_instead_of_ending_the_task(self):
        task = self.make(count=49, limit=50, status=UserStatus.handoff2, battles=(True,))
        self.assertIsNone(task.run_member())
        self.assertEqual(task.current_count, 50)
        task.set_next_run.assert_not_called()                              # 只有纯队员才结束任务
        task.goto_page.assert_not_called()


# ======================================================================================
# 结构守卫：队员检查的位置；队长与 wait_battle 不变
# ======================================================================================

class StructureGuardTest(TestCase):
    @staticmethod
    def _src(func):
        return textwrap.dedent(inspect.getsource(func))

    def test_member_count_check_breaks_before_accepting_or_waiting(self):
        tree = ast.parse(self._src(ScriptTask.run_member))
        main_loop = next(node for node in ast.walk(tree) if isinstance(node, ast.While))
        tests = [ast.unparse(stmt.test) for stmt in main_loop.body if isinstance(stmt, ast.If)]
        check = 'self.current_count >= self.limit_count'
        self.assertIn(check, tests)
        stmt = next(stmt for stmt in main_loop.body if isinstance(stmt, ast.If) and ast.unparse(stmt.test) == check)
        self.assertIsInstance(stmt.body[-1], ast.Break)
        self.assertLess(tests.index(check), tests.index('self.check_then_accept()'))
        self.assertLess(tests.index('wait_timer.reached()'), tests.index(check))   # 计时器兜底仍在最前

    def test_late_invitation_branch_in_run_member_is_kept(self):
        src = self._src(ScriptTask.run_member)
        tree = ast.parse(src)
        late = [node for node in ast.walk(tree) if isinstance(node, ast.If) and ast.unparse(node.test) == 'battle_state is None']
        self.assertEqual(len(late), 1)
        self.assertIsInstance(late[0].body[-1], ast.Continue)
        self.assertNotIn('breakpush_n', src)

    def test_wait_battle_still_treats_the_bondling_page_as_a_late_invitation(self):
        src = self._src(ScriptTask.wait_battle)
        self.assertIn('Late invitation', src)
        self.assertIn('success = None', src)
        self.assertIn("logger.warning('Room destroyed')", src)

    def test_case4_leader_still_invites_before_leaving_at_the_limit(self):
        src = self._src(ScriptTask.run_leader)
        order = ['if self.current_count >= self.limit_count:', 'if self.appear(self.I_GI_IN_ROOM):',
                 'self.invite_friends(self.config.bondling_fairyland.invite_config)', 'sleep(3)',
                 "logger.info(f'契灵次数:{self.current_count}已完成,退出')", 'break']
        positions = []
        start = 0
        for piece in order:
            start = src.index(piece, start)
            positions.append(start)
        self.assertEqual(positions, sorted(positions))
