# This Python file uses the following encoding: utf-8
"""个人突破在「御魂 → 个人突破」循环里的行为：自身的结束规则一律照旧，只在每个目标开打前确认循环还有效。

驱动真实 `RealmRaid.ScriptTask.run`，只替换截图 / 识别 / 导航这些外部边界。离线通过不等于真机通过。
"""

import shutil
import tempfile
import unittest
from random import Random
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from module.instance_sync.team import PresenceBoard
from module.script import loop_controller as lc
from module.script.loop_controller import LoopController, LoopParams, set_controller
from tasks.RealmRaid import script_task as raid
from tasks.RealmRaid.script_task import ScriptTask


class RealmRaidLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_raid_loop_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        patch.object(raid, 'logger').start()
        self.addCleanup(patch.stopall)
        board = PresenceBoard(self.tmp, 'A', 'B')
        self.ctrl = LoopController('rr', rng=Random(1))
        self.ctrl.bind_board(board)
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), board)
        self.ctrl.loop['state'] = 'ACTIVE'
        self.ctrl.loop['idx'] = 1                      # 个人突破这一步
        self.ctrl.in_step = True
        set_controller('rr', self.ctrl)

    def task(self, ticket_results):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(config_name='rr', realm_raid=SimpleNamespace(
            raid_config=SimpleNamespace(number_base=0, number_attack=30),
            switch_soul_config=SimpleNamespace(enable=False, enable_switch_by_name=False),
            general_battle_config=SimpleNamespace(lock_team_enable=False)))
        task.goto_page = Mock()
        task.screenshot = Mock()
        task.appear = Mock(return_value=False)
        task.ensure_lock = Mock()
        task.is_frog = Mock(return_value=False)
        task.begin_fatigue_task = Mock()
        task.set_next_run = Mock()
        task.check_ticket = Mock(side_effect=ticket_results)
        task._grid_targets = Mock(side_effect=AssertionError('no battle should be prepared'))
        return task

    def test_own_end_rule_still_ends_the_step_normally(self):
        task = self.task([True, False])                # 进来有票，开打前检查时已经没票：个人突破自己的结束出口
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(task.check_ticket.call_count, 2)
        task.set_next_run.assert_called_once()

    def test_no_ticket_at_entry_is_also_a_normal_end(self):
        task = self.task([False])
        with self.assertRaises(TaskEnd):
            task.run()
        task.begin_fatigue_task.assert_not_called()

    def test_stopped_loop_prevents_the_next_target_from_being_started(self):
        task = self.task([True, True])
        entry_check = task.check_ticket

        def ticket(base=0):
            result = entry_check(base)
            if entry_check.call_count == 1:
                self.ctrl.fail('peer_lost')            # 任务运行中途，对方失联
            return result

        task.check_ticket = Mock(side_effect=ticket)
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(entry_check.call_count, 1)                   # 循环顶在检查票数之前就停了
        task._grid_targets.assert_not_called()
        task.set_next_run.assert_called_once()                        # 仍然走自己的收尾出口，由控制器忽略终态循环的完成记录

    def test_ordinary_run_without_a_loop_is_not_affected(self):
        self.ctrl.fail('x')
        set_controller('rr', self.ctrl)
        task = self.task([True, False])
        self.ctrl.in_step = False                                      # 普通运行：控制器不把自己交给任务
        with self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(task.check_ticket.call_count, 2)


class RealmRaidInnerStartGateTest(unittest.TestCase):
    """退四内部的「再次挑战」/ 确认弹窗 / 首战点击：外部要求停止后不再开新战斗；整个流程仍由个人突破自己处理。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_raid_gate_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patch.object(lc, 'CHECK_INTERVAL', 0).start()
        patch.object(raid, 'logger').start()
        patch.object(raid, 'sleep').start()
        self.addCleanup(patch.stopall)
        board = PresenceBoard(self.tmp, 'A', 'B')
        self.board = board
        self.ctrl = LoopController('rr_gate', rng=Random(1))
        self.ctrl.bind_board(board)
        self.ctrl.request_start(LoopParams('leader', 1, 2, 2), board)
        self.ctrl.loop['state'] = 'ACTIVE'
        self.ctrl.loop['idx'] = 1
        self.ctrl.in_step = True
        set_controller('rr_gate', self.ctrl)

    def cancel(self):
        self.ctrl.cancel_by_command({'boot_id': self.board.boot_id, 'loop_id': self.ctrl.loop['id']})

    def base_task(self, with_loop=True):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(config_name='rr_gate', realm_raid=SimpleNamespace(
            fire_reaction=None,
            raid_config=SimpleNamespace(number_base=0, number_attack=30, exit_four=True, three_refresh=False,
                                        when_attack_fail=raid.WhenAttackFail.REFRESH),
            switch_soul_config=SimpleNamespace(enable=False, enable_switch_by_name=False),
            general_battle_config=SimpleNamespace(lock_team_enable=False)))
        task.loop = self.ctrl if with_loop else None
        task.device = SimpleNamespace(click_record_clear=Mock())
        task.screenshot = Mock()
        task.wait_until_appear = Mock()
        task._is_active_battle_entry = Mock(return_value=False)
        task.appear_then_click = Mock(return_value=False)
        task._wait_again_entered_battle = Mock(return_value='failure_page')
        task._wait_fire_entered_battle = Mock(return_value='timeout')
        task.is_in_battle = Mock(return_value=False)
        task.partition = [None] * 9
        task.click = Mock()
        return task

    def only_visible(self, task, *names):
        """只有这些按钮在场；真正点中的按钮记在 task.clicked（对不在场的按钮只是探测，不算点击）。"""
        wanted = [getattr(task, name) for name in names]
        task.clicked = []

        def visible(target):
            return any(target is w for w in wanted)

        def click(target, *a, **k):
            if visible(target):
                task.clicked.append(target)
                return True
            return False

        task.appear = Mock(side_effect=lambda target, *a, **k: visible(target))
        task.appear_then_click = Mock(side_effect=click)

    # ---- 再次挑战 ----
    def test_fire_again_does_not_click_once_the_loop_is_stopped(self):
        task = self.base_task()
        self.only_visible(task, 'I_FIRE_AGAIN')
        self.cancel()
        self.assertFalse(task._fire_again())
        self.assertEqual(task.clicked, [])                               # 没有点「再次挑战」
        self.assertTrue(task._loop_halted)

    def test_fire_again_does_not_confirm_the_popup_once_the_loop_is_stopped(self):
        task = self.base_task()
        self.only_visible(task, 'I_FRESH_ENSURE')
        self.cancel()
        self.assertFalse(task._fire_again())
        self.assertEqual(task.clicked, [])                               # 确认弹窗才真正开始下一场：不点
        self.assertTrue(task._loop_halted)

    def test_fire_again_in_the_normal_run_is_untouched(self):
        for with_loop in (False, True):                                  # 没有循环 / 循环有效：都照旧点击
            task = self.base_task(with_loop)
            self.only_visible(task, 'I_FIRE_AGAIN')
            task._wait_again_entered_battle = Mock(return_value='battle')
            self.assertTrue(task._fire_again())
            self.assertEqual(task.clicked, [task.I_FIRE_AGAIN])
            self.assertFalse(task._loop_halted)

    def test_fire_does_not_click_once_the_loop_is_stopped(self):
        task = self.base_task()
        self.only_visible(task, 'I_FIRE')
        self.cancel()
        self.assertFalse(task.fire(1))
        self.assertEqual(task.clicked, [])

    # ---- run() 里的退四 ----
    def run_exit_four(self, task, *, again_results=None, refresh=False, visible=(), first_battle=None):
        task.goto_page = Mock()
        task.check_ticket = Mock(side_effect=[True, True, False, False])
        task.ensure_lock = Mock()
        task.is_frog = Mock(return_value=False)
        task.begin_fatigue_task = Mock()
        task.set_next_run = Mock()
        task.reward_detect_click = Mock(return_value=False)
        task._grid_targets = Mock(return_value={1: 'medal'})            # 只剩最后一个可攻打目标 → 退四
        task._is_only_remaining_target = Mock(return_value=True)
        task._enter_target = Mock(return_value=True)
        task.fire = Mock(return_value=True)
        task.build_quick_exit_config = Mock(return_value='quick')
        task.check_refresh = Mock(return_value=refresh)
        task._realm_raid_cycle_safe_break = Mock()
        task.check_medal_is_frog = Mock(return_value=False)
        task.appear = Mock(return_value=False)
        if visible:
            self.only_visible(task, *visible)
        task.run_general_battle = Mock(side_effect=first_battle or (lambda *a, **k: False))   # 首战主动退出
        if again_results is not None:                                    # 不给就用真实的 _fire_again
            task._fire_again = Mock(side_effect=again_results)
        with self.assertRaises(TaskEnd):
            task.run()

    def test_cancel_inside_exit_four_stops_without_refreshing_or_retrying_and_is_not_a_step_failure(self):
        task = self.base_task()

        def first_battle(*args, **kwargs):
            self.cancel()                                                # 首战（投降）结算期间外部要求停止
            return False

        # 真实的 _fire_again：失败页上「再次挑战」可见，但开战点击前被拦住
        self.run_exit_four(task, visible=('I_FIRE_AGAIN',), first_battle=first_battle)
        self.assertEqual(task.clicked, [])                               # 没有点「再次挑战」
        task.check_refresh.assert_not_called()                           # 不走「退四中断 → 刷新」
        task.set_next_run.assert_called_once()                           # 仍走自己的结束出口
        self.assertEqual(task.ensure_lock.call_args_list[-1].args, (False,))   # 锁定阵容恢复到用户配置
        self.assertEqual(self.ctrl.state, 'CANCELLED')                   # 控制器是被取消，不是步骤失败也不是完成
        self.ctrl.after_run('RealmRaid', ended=True, delay_success=None)
        self.assertEqual(self.ctrl.state, 'CANCELLED')                   # 取消不会被当成正常完成去推进
        self.assertEqual(self.ctrl.loop['done_idx'], -1)

    def test_normal_exit_four_surrender_loss_and_refresh_stay_inside_realm_raid(self):
        task = self.base_task()
        # 退四内部：首战投降（输）→ 四次再次挑战 → 最终战败 → 刷新；全部由个人突破自己处理，直到整个任务结束
        self.run_exit_four(task, again_results=[True] * raid.RR_EXIT_FOUR_SURRENDERS, refresh=True)
        self.assertEqual(task._fire_again.call_count, raid.RR_EXIT_FOUR_SURRENDERS)
        task.check_refresh.assert_called_once()                          # 最终战败 → 刷新（个人突破自己的规则）
        self.assertEqual(self.ctrl.state, 'ACTIVE')                      # 内部输赢 / 刷新不驱动循环
        self.assertIsNone(self.ctrl.completed_idx)                       # 也不代表步骤完成
        self.ctrl.after_run('RealmRaid', ended=True, delay_success=None)  # 只有整个任务正常走到结束出口才完成
        self.assertEqual(self.ctrl.loop['done_idx'], 1)

    def test_aborted_exit_four_without_a_stop_request_still_refreshes_as_before(self):
        task = self.base_task()
        self.run_exit_four(task, again_results=[False], refresh=True)    # 没有外部停止：退四中断照旧刷新
        task.check_refresh.assert_called_once()
        self.assertEqual(self.ctrl.state, 'ACTIVE')

    def test_ordinary_run_without_a_loop_never_halts(self):
        task = self.base_task(with_loop=False)
        self.run_exit_four(task, again_results=[False], refresh=True)
        task.check_refresh.assert_called_once()
        self.assertFalse(task._loop_halted)


if __name__ == '__main__':
    unittest.main()
