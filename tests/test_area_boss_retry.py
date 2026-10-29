# This Python file uses the following encoding: utf-8
"""地域鬼王：当前目标「明确战败」后的有限重试（含首次最多 3 次）。

驱动真实的 `ScriptTask.run` / `boss_fight` / `start_fight` / `fight_reward_boss` / `_handle_result`，只替换设备、识别、
页面导航和战斗本体（`run_general_battle` 用脚本化的结果；它内部走真实的 `AreaBoss._handle_result`，
基类的 `_handle_result` 替身只负责按脚本设置 `context.is_win`，对应「识别到 / 没识别到失败横幅」）。

规则：
- 同一阶段最多 3 次（首次 + 重试 2 次）；任意一次明确胜利立即结束；三败记警告、关闭详情页、继续后续目标。
- 只有「明确失败」（识别到失败横幅）才重试；结果不明、异常、停止不吞掉；每次重试先重新确认详情页，
  再走正常的挑战入口（`I_FIRE`），不点失败页的「再次挑战」。
- 60 级前置战斗成功后进入极地鬼是后续阶段，有自己的预算（一个目标最多 3 + 3 场）。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError, TaskEnd
from tasks.AreaBoss import script_task as ab
from tasks.AreaBoss.config import AreaBoss
from tasks.AreaBoss.config_boss import AreaBossFloor
from tasks.AreaBoss.script_task import ScriptTask as T
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.page import page_area_boss, page_main
from tasks.RealmRaid.assets import RealmRaidAssets
from tests.test_daily_trifles import FakeUi

WIN, LOSS, UNKNOWN = 'win', 'loss', 'unknown'
AGAIN = RealmRaidAssets.I_FIRE_AGAIN


def make_world(outcomes, *, boss_reward=False, boss_number=3, attack_60=False, raises=None):
    """详情页（红色关闭 + 挑战按钮）常驻；点挑战 → 进战斗（两个资产都消失）；`run_general_battle` 按脚本给结果并回到详情页。

    `outcomes`：每场战斗的结果序列（WIN / LOSS / UNKNOWN）。`raises[i]` 是第 i 场战斗抛出的异常。
    """
    ui = FakeUi([T.I_AB_CLOSE_RED, T.I_FIRE])
    ui.on_click[id(T.I_FIRE)] = lambda: ui.hide(T.I_AB_CLOSE_RED, T.I_FIRE)
    t = T.__new__(T)
    t.config = SimpleNamespace(area_boss=AreaBoss(), set_next_run=Mock())
    con = t.config.area_boss
    con.boss.boss_reward = boss_reward
    con.boss.boss_number = boss_number
    con.boss.Attack_60 = attack_60
    con.boss.reward_floor = AreaBossFloor.TEN
    t.screenshot = ui.screenshot
    t.appear = ui.appear
    t.click = ui.click
    t.appear_then_click = ui.appear_then_click
    t.goto_page = ui.goto_page
    t.wait_until_appear = lambda rule, skip_first_screenshot=False, wait_time=None: ui.appear(rule)
    t.ui_click_until_disappear = Mock(name='ui_click_until_disappear')
    t.check_can_run = Mock(name='check_can_run')
    t.set_next_run = Mock(name='set_next_run')
    t.open_filter = Mock(name='open_filter')
    t.switch_to_famous = Mock(name='switch_to_famous')
    t.switch_to_collect = Mock(name='switch_to_collect')
    t.open_boss_detail = Mock(name='open_boss_detail', return_value=True)
    t.is_group_ranked = Mock(name='is_group_ranked', return_value=False)
    t.get_difficulty = Mock(name='get_difficulty', return_value=True)       # 已经是极地鬼
    t.switch_difficulty = Mock(name='switch_difficulty')
    t.switch_to_level_60 = Mock(name='switch_to_level_60')
    t.switch_to_floor_1 = Mock(name='switch_to_floor_1')
    t.switch_to_floor_10 = Mock(name='switch_to_floor_10')
    t.RETRY_DETAIL_TIMEOUT = 0.2
    script = list(outcomes)
    fights = []
    raises = dict(raises or {})

    def run_general_battle(config=None, **kw):
        index = len(fights)
        fights.append(script[index])
        if index in raises:
            raise raises[index]
        ui.show(T.I_AB_CLOSE_RED, T.I_FIRE)                  # 战斗结束回到详情页
        outcome = script[index]
        if outcome == LOSS:
            ui.show(AGAIN)                                   # 陷阱：战败后详情页上仍看得见「再次挑战」，代码不能点它
        context = SimpleNamespace(is_win=(outcome == WIN))
        if outcome in (WIN, LOSS):
            t._handle_result(context, config)                # 真实的 AreaBoss._handle_result 记录「明确失败」
            return context.is_win
        return False                                         # 结果不明：没经过结果页（is_win 默认 False）
    t.run_general_battle = run_general_battle
    return t, ui, fights


def base_result_stub(self, context, config):
    """基类 `_handle_result` 的替身：`context.is_win` 已由脚本设置，这里只表示「识别过结果页」。"""
    from tasks.Component.GeneralBattle.general_battle import BattleAction
    return BattleAction.CONTINUE


class Case(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(GeneralBattle, '_handle_result', base_result_stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fire_clicks(self, ui):
        return ui.clicked(T.I_FIRE)


class SingleTargetRetryTest(Case):
    def test_first_win_fights_once(self):
        t, ui, fights = make_world([WIN])
        self.assertTrue(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [WIN])
        self.assertEqual(self.fire_clicks(ui), 1)

    def test_lose_then_win_fights_twice(self):
        t, ui, fights = make_world([LOSS, WIN])
        self.assertTrue(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [LOSS, WIN])
        self.assertEqual(self.fire_clicks(ui), 2)

    def test_two_losses_then_win_fights_three_times(self):
        t, ui, fights = make_world([LOSS, LOSS, WIN])
        self.assertTrue(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [LOSS, LOSS, WIN])
        self.assertEqual(self.fire_clicks(ui), 3)

    def test_three_losses_stop_with_a_warning_and_no_fourth_fight(self):
        t, ui, fights = make_world([LOSS, LOSS, LOSS, WIN])
        with self.assertLogs('oas', level='WARNING') as logs:
            self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [LOSS, LOSS, LOSS])          # 没有第四场
        self.assertEqual(self.fire_clicks(ui), 3)
        text = '\n'.join(logs.output)
        self.assertIn('lost 3 times', text)
        self.assertIn('Area Boss Fight Failed', text)          # 不写成挑战成功
        t.ui_click_until_disappear.assert_called()             # 关闭当前详情页

    def test_retry_reconfirms_the_detail_page_and_uses_the_normal_fire_entry(self):
        t, ui, fights = make_world([LOSS, WIN])
        shots_before_retry = []
        original = t.run_general_battle

        def spy(config=None, **kw):
            shots_before_retry.append(ui.shots)
            return original(config, **kw)
        t.run_general_battle = spy
        t.boss_fight(t.I_BATTLE_1)
        self.assertGreater(shots_before_retry[1], shots_before_retry[0])    # 重试前截了新图
        self.assertEqual(ui.clicked(AGAIN), 0)                               # 从不点失败页的「再次挑战」
        self.assertEqual({r for r in ui.clicks}, {T.I_FIRE})                 # 只点正常挑战入口

    def test_retry_needs_the_detail_page_and_fire_button_otherwise_it_stops(self):
        t, ui, fights = make_world([LOSS, WIN])
        original = t.run_general_battle

        def lose_and_leave(config=None, **kw):
            result = original(config, **kw)
            ui.hide(T.I_FIRE)                                # 战败后详情页没有可点的挑战按钮（例如次数用完）
            return result
        t.run_general_battle = lose_and_leave
        self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [LOSS])                      # 不盲目开下一场
        self.assertEqual(self.fire_clicks(ui), 1)

    def test_each_retry_checks_the_time_window_again(self):
        t, ui, fights = make_world([LOSS, WIN])
        t.check_can_run.side_effect = [None, TaskEnd()]
        with self.assertRaises(TaskEnd):
            t.boss_fight(t.I_BATTLE_1)
        self.assertEqual(fights, [LOSS])


class NotAClearLossIsNotRetriedTest(Case):
    def test_unknown_result_is_not_guessed_as_a_loss(self):
        t, ui, fights = make_world([UNKNOWN, WIN])
        self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [UNKNOWN])
        self.assertEqual(self.fire_clicks(ui), 1)

    def test_a_loss_banner_followed_by_a_win_return_is_ambiguous_and_not_retried(self):
        t, ui, fights = make_world([WIN])
        original = t.run_general_battle

        def mixed(config=None, **kw):
            original(config, **kw)
            t._loss_seen = True                              # 看到过失败横幅，但战斗函数返回了胜利
            return True
        t.run_general_battle = mixed
        self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(self.fire_clicks(ui), 1)

    def test_stuck_error_in_a_retry_propagates(self):
        t, ui, fights = make_world([LOSS, LOSS, WIN], raises={1: GameStuckError('stuck')})
        with self.assertRaises(GameStuckError):
            t.boss_fight(t.I_BATTLE_1)
        self.assertEqual(fights, [LOSS, LOSS])                # 抛出的那一场也算开过；没有第三场

    def test_stop_request_in_a_retry_propagates(self):
        t, ui, fights = make_world([LOSS, WIN], raises={1: KeyboardInterrupt()})
        with self.assertRaises(KeyboardInterrupt):
            t.boss_fight(t.I_BATTLE_1)

    def test_failing_to_open_the_detail_page_is_not_a_battle_loss(self):
        t, ui, fights = make_world([WIN])
        t.open_boss_detail.return_value = False
        self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [])
        self.assertEqual(self.fire_clicks(ui), 0)

    def test_already_ranked_target_is_skipped_without_fighting(self):
        t, ui, fights = make_world([WIN])
        t.is_group_ranked.return_value = True
        self.assertTrue(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [])

    def test_loss_flag_is_reset_for_every_fight(self):
        t, ui, fights = make_world([LOSS, UNKNOWN])
        self.assertFalse(t.boss_fight(t.I_BATTLE_1))
        self.assertEqual(fights, [LOSS, UNKNOWN])             # 第二场没有失败横幅：不能沿用上一场的标记继续重试


class PerTargetBudgetTest(Case):
    def test_each_normal_target_has_its_own_budget_and_the_task_is_not_restarted(self):
        t, ui, fights = make_world([LOSS, LOSS, LOSS, WIN, LOSS, WIN])
        spy = Mock(wraps=t.boss_fight)
        t.boss_fight = spy
        with self.assertRaises(TaskEnd):
            t.run()
        self.assertEqual(fights, [LOSS, LOSS, LOSS, WIN, LOSS, WIN])    # 目标 1：3 败跳过；目标 2：1 场胜；目标 3：败后胜
        self.assertEqual([c.args[0] is t_i for c, t_i in zip(spy.call_args_list, (t.I_BATTLE_1, t.I_BATTLE_2, t.I_BATTLE_3))],
                         [True, True, True])
        self.assertEqual(spy.call_count, 3)
        self.assertEqual(ui.pages.count(page_area_boss), 1)              # 没有重新拉起整个 AreaBoss 流程
        self.assertEqual(ui.pages.count(page_main), 1)
        t.set_next_run.assert_called_once_with(task='AreaBoss', success=True, finish=False)
        self.assertEqual(t.open_filter.call_count, 1 + 3)                # run 里 1 次 + 每个目标 boss_fight 开筛选 1 次，重试不重开

    def test_a_target_that_is_won_is_not_fought_again(self):
        t, ui, fights = make_world([WIN, WIN, WIN])
        with self.assertRaises(TaskEnd):
            t.run()
        self.assertEqual(fights, [WIN, WIN, WIN])

    def test_failure_after_three_losses_still_continues_with_the_next_target(self):
        t, ui, fights = make_world([LOSS, LOSS, LOSS, WIN, WIN], boss_number=2)
        with self.assertRaises(TaskEnd):
            t.run()
        self.assertEqual(fights, [LOSS, LOSS, LOSS, WIN])
        t.set_next_run.assert_called_once()


class RewardAndSixtyLevelPathsTest(Case):
    def test_reward_target_retries_inside_its_ultra_fight(self):
        t, ui, fights = make_world([LOSS, WIN], boss_reward=True, boss_number=1)
        t.get_hot_in_reward = Mock(return_value=(False, 'boss', t.C_AB_BOSS_REWARD_PHOTO_1))
        with self.assertRaises(TaskEnd):
            t.run()
        self.assertEqual(fights, [LOSS, WIN])                  # 悬赏目标胜利 → boss_fought=1 → 没有普通目标
        t.switch_to_floor_10.assert_called_once()              # 层数只调整一次，重试不重复
        self.assertEqual(t.open_boss_detail.call_count, 1)     # 没有重新打开详情页

    def test_reward_target_three_losses_then_normal_targets_continue(self):
        t, ui, fights = make_world([LOSS, LOSS, LOSS, WIN], boss_reward=True, boss_number=1)
        t.get_hot_in_reward = Mock(return_value=(False, 'boss', t.C_AB_BOSS_REWARD_PHOTO_1))
        with self.assertRaises(TaskEnd):
            t.run()
        self.assertEqual(fights, [LOSS, LOSS, LOSS, WIN])      # 悬赏 3 败不算成功 → 仍打 1 个普通目标
        t.switch_to_floor_10.assert_called_once()

    def test_sixty_level_pre_battle_has_its_own_budget_and_ultra_is_a_later_stage(self):
        t, ui, fights = make_world([LOSS, LOSS, WIN, LOSS, LOSS, LOSS], attack_60=True)
        t.get_difficulty.return_value = False                  # 还不是极
        t.appear = lambda rule, **kw: False if rule is t.I_AB_DIFFICULTY_NORMAL else ui.appear(rule)
        self.assertFalse(t.boss_fight(t.I_BATTLE_1, True, fileter_open=False))
        self.assertEqual(fights, [LOSS, LOSS, WIN, LOSS, LOSS, LOSS])   # 60 级阶段 3 场（第 3 场胜）+ 极阶段 3 场（全败）
        t.switch_to_level_60.assert_called_once()
        t.switch_difficulty.assert_called_once_with(True)       # 60 级胜利后切极，只切一次

    def test_sixty_level_pre_battle_all_lost_never_reaches_ultra(self):
        t, ui, fights = make_world([LOSS, LOSS, LOSS, WIN], attack_60=True)
        t.get_difficulty.return_value = False
        t.appear = lambda rule, **kw: False if rule is t.I_AB_DIFFICULTY_NORMAL else ui.appear(rule)
        with self.assertLogs('oas', level='WARNING') as logs:
            self.assertFalse(t.boss_fight(t.I_BATTLE_1, True, fileter_open=False))
        self.assertEqual(fights, [LOSS, LOSS, LOSS])           # 3 败后放弃，不进极
        t.switch_difficulty.assert_not_called()
        self.assertIn('you are so weakness', '\n'.join(logs.output))

    def test_sixty_level_win_on_the_first_try_then_ultra_loses_then_wins(self):
        t, ui, fights = make_world([WIN, LOSS, WIN], attack_60=True)
        t.get_difficulty.return_value = False
        t.appear = lambda rule, **kw: False if rule is t.I_AB_DIFFICULTY_NORMAL else ui.appear(rule)
        self.assertTrue(t.boss_fight(t.I_BATTLE_1, True, fileter_open=False))
        self.assertEqual(fights, [WIN, LOSS, WIN])             # 60 级成功后的极地鬼不是对它的重试：自己的预算


class RetryConstantsTest(unittest.TestCase):
    def test_the_limit_is_fixed_at_three_and_not_a_config_field(self):
        self.assertEqual(T.BATTLE_MAX_ATTEMPTS, 3)
        self.assertFalse(any('retry' in name.lower() or 'attempt' in name.lower()
                             for name in AreaBoss().boss.model_fields))


if __name__ == '__main__':
    unittest.main()
