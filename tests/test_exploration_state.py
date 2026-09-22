# This Python file uses the following encoding: utf-8
"""`Exploration` 状态机与 Boss 直退契约测试。

目的：在把探索流程迁移到「状态 → 动作 → 期望状态 → 显式验证」结构 **之前**，用纯 mock
锁住当前真实的页面分发 FSM、进入战斗的判定语义、循环边界、GeneralBattle 交接方式，作为
未来迁移的回归基线。

Exploration 与前三案例最大的不同：它已经是一个 **page-dispatch FSM**——`exec_exp_page`
的 `while True` 每轮 `screenshot → get_current_page() → exp_page_handle_dict[page]()`；且
`fire()` 用 **正向战斗页确认**（`cur_page in (page_battle_prepare, page_battle)`）+ **双重
上界**（`max_tries=4` 与 `Timer(10)`），可以返回 `False`——这正是 RealmRaid `fire()` 缺的。

基础用例保留迁移前 characterization。Boss 战后 reward / exit 走原项目**原生链**
（page_exp_main → collect_reward → 地图宝箱 or 小纸人 policy → 原生 quit_exp_main）；
2026-09-08 撤销了上一轮「Boss 后完全跳过地图宝箱直接退出」的错误需求专属结构，
独立成立的 Rotation Contract / Chapter FrameWait / solo Fatigue 能力保留。

源码：`tasks/Exploration/script_task.py`、`tasks/Exploration/base.py`。
"""

import ast
import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import tasks.Exploration.page as pages
from tasks.Exploration.base import BaseExploration as BE
from tasks.Exploration.script_task import InviteFailedException, ScriptTask as E


def _src(func):
    return inspect.getsource(func)


# --------------------------------------------------------------------------------------
# fire() —— 进入战斗（双重上界 + 正向战斗页确认，可返回 False）
# --------------------------------------------------------------------------------------

class FireCharacterizationTest(TestCase):
    def _mk(self, page_seq, click_seq=None):
        t = E.__new__(E)
        it = iter(page_seq)
        t.screenshot = Mock(name='screenshot')
        t.get_current_page = Mock(side_effect=lambda: next(it))
        t.appear_then_click = Mock(side_effect=(click_seq or [False] * 20))
        t.need_exit = True
        return t

    def test_returns_true_on_positive_battle_page(self):
        # 现状语义锁定：进入战斗的判据是**正向识别到 page_battle_prepare / page_battle**，
        # 不是「旧标识消失」。
        for p in (pages.page_battle_prepare, pages.page_battle):
            t = self._mk([p])
            self.assertIs(t.fire(t.I_BOSS_BATTLE_BUTTON), True)
            self.assertEqual(t.screenshot.call_count, 1)
            t.appear_then_click.assert_not_called()

    def test_returns_true_and_cancels_exit_on_exp_exit_page(self):
        t = self._mk([pages.page_exp_exit])
        self.assertIs(t.fire(t.I_BOSS_BATTLE_BUTTON), True)
        self.assertIs(t.need_exit, False)          # 退出动画期间又见怪 → 取消退出

    def test_bounded_by_max_tries_4(self):
        # 页面一直不是战斗页，点击每次都「点中」→ max_tries 递减，第 4 次后 return False
        t = self._mk([None] * 10, click_seq=[True] * 10)
        with patch('tasks.Exploration.base.Timer') as TimerMock:
            TimerMock.return_value.start.return_value.reached.return_value = False
            self.assertIs(t.fire(t.I_BOSS_BATTLE_BUTTON), False)
        self.assertEqual(t.appear_then_click.call_count, 4)   # 硬上界 4

    def test_bounded_by_timer_10s_even_if_click_never_lands(self):
        # 点击从不「命中 interval」→ max_tries 不减；靠 Timer(10) 收敛
        t = self._mk([None] * 50, click_seq=[False] * 50)
        with patch('tasks.Exploration.base.Timer') as TimerMock:
            reached = TimerMock.return_value.start.return_value.reached
            reached.side_effect = [False, False, True]   # 第 3 次检查超时
            self.assertIs(t.fire(t.I_BOSS_BATTLE_BUTTON), False)
        self.assertLessEqual(t.appear_then_click.call_count, 2)

    def test_source_uses_positive_page_and_double_bound(self):
        src = _src(BE.fire)
        self.assertIn('max_tries = 4', src)
        self.assertIn('Timer(10).start()', src)
        self.assertIn('while max_tries > 0 and not timeout_timer.reached():', src)
        self.assertIn('cur_page in (pages.page_battle_prepare, pages.page_battle)', src)
        self.assertIn('return False', src)
        # 明确不是 RealmRaid 那种「旧标识消失即成功」
        self.assertNotIn('not self.appear(', src)


# --------------------------------------------------------------------------------------
# get_fire_button() —— boss / normal 分支
# --------------------------------------------------------------------------------------

class GetFireButtonBranchTest(TestCase):
    def _mk(self):
        t = E.__new__(E)
        t.fire_monster_type = ''
        return t

    def test_boss_button_wins_and_sets_type(self):
        t = self._mk()
        t.appear = Mock(return_value=True)          # I_BOSS_BATTLE_BUTTON 命中
        t.search_up_fight = Mock()
        self.assertIs(t.get_fire_button(), t.I_BOSS_BATTLE_BUTTON)
        self.assertEqual(t.fire_monster_type, 'boss')
        t.search_up_fight.assert_not_called()

    def test_falls_through_to_search_up_fight_for_normal(self):
        t = self._mk()
        t.appear = Mock(return_value=False)         # 没有 boss
        sentinel = object()
        t.search_up_fight = Mock(return_value=sentinel)
        self.assertIs(t.get_fire_button(), sentinel)

    def test_search_up_fight_sets_normal_type_and_relocates_roi(self):
        # 现状：normal 目标的 ROI 是 match_all 后按最近距离动态重定位（不是静态 ROI）
        src = _src(BE.search_up_fight)
        self.assertIn('self.I_NORMAL_BATTLE_BUTTON.match_all(', src)
        self.assertIn('self.I_NORMAL_BATTLE_BUTTON.roi_front = roi_front', src)
        self.assertIn("self.fire_monster_type = 'normal'", src)
        self.assertIn('distances.sort(', src)       # 最近距离优先


# --------------------------------------------------------------------------------------
# exec_exp_page —— page-dispatch FSM
# --------------------------------------------------------------------------------------

class ExecExpPageDispatchTest(TestCase):
    def test_is_page_dispatch_while_true_loop(self):
        src = _src(E.exec_exp_page)
        self.assertIn('while True:', src)
        self.assertIn('self.screenshot()', src)
        self.assertIn('current_page = self.get_current_page()', src)
        self.assertIn('handle = self.exp_page_handle_dict.get(current_page, None)', src)
        self.assertIn('self.pre_page = current_page', src)
        # 无迭代上限 / 无 Timer——靠 check_exit + 异常收敛（state-bounded）
        self.assertNotIn('range(', src)
        self.assertNotIn('Timer(', src)

    def test_none_page_sleeps_half_second_and_continues(self):
        src = _src(E.exec_exp_page)
        self.assertIn('if current_page is None:', src)
        self.assertIn('time.sleep(0.5)', src)

    def test_unknown_page_routes_to_goto_page_exploration(self):
        src = _src(E.exec_exp_page)
        self.assertIn('if handle is None:', src)
        self.assertIn('self.goto_page(pages.page_exploration)', src)

    def test_invite_failed_exception_breaks_loop(self):
        src = _src(E.exec_exp_page)
        self.assertIn('except InviteFailedException', src)
        self.assertIn('break', src)

    def test_handle_dict_covers_all_exp_pages(self):
        t = E.__new__(E)
        # 挂上被引用的 handler 名，避免 property 里 getattr 失败
        for name in ('run_on_exp_main', 'run_on_exp_settings', 'run_on_exp_exit',
                     'run_on_exp_entrance', 'run_on_exp', 'run_on_battle',
                     'run_on_battle_team'):
            setattr(t, name, Mock(name=name))
        d = t.exp_page_handle_dict
        self.assertIn(pages.page_exploration, d)
        self.assertIn(pages.page_exp_main, d)
        self.assertIn(pages.page_battle_prepare, d)
        self.assertIn(pages.page_battle, d)
        self.assertIn(pages.page_battle_result, d)
        self.assertIn(pages.page_reward, d)
        self.assertIn(pages.page_battle_team, d)
        # 三个战斗页共用 run_on_battle（此处依赖 setattr 的同一个 Mock 实例做同一性断言）
        self.assertIs(d[pages.page_battle_prepare], d[pages.page_battle])
        self.assertIs(d[pages.page_battle], d[pages.page_battle_result])
        # 源码级：page_reward 是就地 lambda，点 random_click
        src = _src(E.exp_page_handle_dict.fget)
        self.assertIn('pages.page_battle_prepare: self.run_on_battle', src)
        self.assertIn('pages.page_battle: self.run_on_battle', src)
        self.assertIn('pages.page_battle_result: self.run_on_battle', src)
        self.assertIn('self.click(pages.random_click(), interval=0.8)', src)


# --------------------------------------------------------------------------------------
# run_on_battle —— GeneralBattle 交接
# --------------------------------------------------------------------------------------

class GeneralBattleHandoffTest(TestCase):
    def test_run_on_battle_is_native_handoff_no_boss_completion_helper(self):
        # 2026-09-08：撤销「Boss 后完全跳过地图宝箱直接退出」的错误需求专属结构。
        # run_on_battle 恢复原生：调 run_general_battle(exit_matcher=page_exp_main) + _match_end.refresh，
        # 之后由 exec_exp_page 的 page-dispatch 自然接管（page_exp_main → run_on_exp_main → collect_reward）。
        from datetime import datetime
        t = E.__new__(E)
        t.run_general_battle = Mock(return_value=True)
        t._match_end = SimpleNamespace(refresh=Mock())
        t._config = SimpleNamespace(general_battle_config=SimpleNamespace())
        t.fire_monster_type = 'boss'
        t.run_on_battle()
        _args, kwargs = t.run_general_battle.call_args
        self.assertEqual(kwargs['exit_matcher'], pages.page_exp_main)   # 用 Page 作 exit_matcher
        t._match_end.refresh.assert_called_once()                        # 防同图多次误判结束
        self.assertIsInstance(t.wait_start_time, datetime)              # 队友等待时间重置
        src = _src(E.run_on_battle)
        for tok in ('_complete_boss_business_cycle', '_run_boss_exit_transaction', 'battle_won'):
            self.assertNotIn(tok, src, tok)

    def test_exploration_only_overrides_exit_matcher_not_settlement(self):
        # RealmRaid 覆写了 PREPARE_CLICK_DELAY_RANGE / SETTLEMENT_CLICK_INTERVAL_RANGE；
        # Exploration 只覆写 _exit_matcher，Settlement 完全走基类 Contract v2 默认。
        self.assertIn('_exit_matcher', BE.__dict__)
        for name in ('_handle_result', '_handle_reward', '_settlement_click',
                     'PREPARE_CLICK_DELAY_RANGE', 'SETTLEMENT_CLICK_INTERVAL_RANGE'):
            self.assertNotIn(name, BE.__dict__, name)
            self.assertNotIn(name, E.__dict__, name)
        # GeneralBattle 确实在 MRO 里（交接对象），只是没有 override 任何结算相关成员
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        self.assertIn(GeneralBattle, E.__mro__)

    def test_exit_matcher_is_page_exp_main_recognizer(self):
        src = _src(BE._exit_matcher)
        self.assertIn('I_E_SETTINGS_BUTTON', src)
        self.assertIn('I_E_AUTO_ROTATE_ON', src)
        self.assertIn('I_E_AUTO_ROTATE_OFF', src)
        self.assertIn('any_of', src)

    def test_no_quick_exit_in_exploration(self):
        src = _src(inspect.getmodule(BE)) + _src(inspect.getmodule(E))
        self.assertNotIn('quick_exit', src)
        self.assertNotIn('build_quick_exit_config', src)


# --------------------------------------------------------------------------------------
# arrive_end —— 到达地图尽头（swipe 计数 + RuleAnimate 结构稳定）
# --------------------------------------------------------------------------------------

class ArriveEndTest(TestCase):
    # 直接调用 BE.arrive_end——E 的覆写只是在基类逻辑前加一个 28 章特判（另有单独测试），
    # 且那条特判会触发 _config cached_property（需真实 config），与本组要锁的结构逻辑无关。
    def test_returns_true_after_6_background_swipes(self):
        t = E.__new__(E)
        t.device = SimpleNamespace(
            click_record=SimpleNamespace(count=Mock(return_value=6)),
            click_record_clear=Mock(),
            image='FRAME', image_frame_id='FID',
        )
        t._match_end = SimpleNamespace(stable=Mock(return_value=False))
        self.assertIs(BE.arrive_end(t), True)
        t.device.click_record_clear.assert_called_once()
        t._match_end.stable.assert_not_called()

    def test_falls_back_to_ruleanimate_structural_stable(self):
        t = E.__new__(E)
        t.device = SimpleNamespace(
            click_record=SimpleNamespace(count=Mock(return_value=2)),
            click_record_clear=Mock(),
            image='FRAME', image_frame_id='FID',
        )
        t._match_end = SimpleNamespace(stable=Mock(return_value=True))
        self.assertIs(BE.arrive_end(t), True)
        _a, kw = t._match_end.stable.call_args
        self.assertIs(kw['refresh_after_stable'], True)

    def test_scripttask_arrive_end_special_cases_chapter_28(self):
        # E 覆写 arrive_end：28 章直接 appear(I_SWIPE_END)，否则 super()
        src = _src(E.arrive_end)
        self.assertIn('EXPLORATION_28', src)
        self.assertIn('self.appear(self.I_SWIPE_END)', src)
        self.assertIn('return super().arrive_end()', src)


# --------------------------------------------------------------------------------------
# check_exit —— 任务退出判定（Recovery / 跨任务）
# --------------------------------------------------------------------------------------

class CheckExitTest(TestCase):
    def _mk(self, *, count=0, minions=30, elapsed_s=0, limit_s=1800,
            user_status=None, wait_s=0, wait_limit_s=600):
        from datetime import datetime, timedelta
        t = E.__new__(E)
        t.current_count = count
        now = datetime.now()
        t.start_time = now - timedelta(seconds=elapsed_s)
        t.wait_start_time = now - timedelta(seconds=wait_s)
        from tasks.Exploration.config import UserStatus
        t.user_status = user_status or UserStatus.ALONE
        t._config = SimpleNamespace(
            exploration_config=SimpleNamespace(minions_cnt=minions),
            invite_config=SimpleNamespace(wait_time_v=timedelta(seconds=wait_limit_s)),
            scrolls=SimpleNamespace(scrolls_enable=False),
        )
        t.limit_time = timedelta(seconds=limit_s)
        t.activate_realm_raid = Mock()
        return t

    def test_exits_when_minions_count_reached(self):
        t = self._mk(count=30, minions=30)
        self.assertIs(t.check_exit(None), True)

    def test_exits_when_time_limit_reached(self):
        t = self._mk(elapsed_s=2000, limit_s=1800)
        self.assertIs(t.check_exit(None), True)

    def test_member_exits_on_wait_timeout(self):
        from tasks.Exploration.config import UserStatus
        t = self._mk(user_status=UserStatus.MEMBER, wait_s=700, wait_limit_s=600)
        self.assertIs(t.check_exit(None), True)

    def test_normal_case_returns_false_and_checks_scrolls(self):
        t = self._mk()
        self.assertIs(t.check_exit(None), False)
        t.activate_realm_raid.assert_called_once()

    def test_activate_realm_raid_is_cross_task_recovery(self):
        # 现状：绘卷模式下 activate_realm_raid 会给 RealmRaid / MemoryScrolls set_next_run
        # 并 raise TaskEnd —— 这是 Task 层的跨任务 recovery（不下沉到公共层，符合 D015）
        src = _src(BE.activate_realm_raid)
        self.assertIn("self.set_next_run(task='RealmRaid'", src)
        self.assertIn("self.set_next_run(task='MemoryScrolls'", src)
        self.assertIn('raise TaskEnd', src)


# --------------------------------------------------------------------------------------
# 循环 / 等待边界（源码级）
# --------------------------------------------------------------------------------------

class LoopAndWaitBoundsTest(TestCase):
    def test_open_expect_level_bounded_by_swipe_count_25(self):
        src = _src(BE.open_expect_level)
        self.assertIn('while True:', src)
        self.assertIn('swipeCount >= 25', src)
        self.assertIn('raise GameStuckError', src)
        self.assertIn('time.sleep(1)', src)
        self.assertIn('self._wait_chapter_list_settle(settle_baseline)', src)

    def test_fill_shikigami_is_state_bounded_by_stuck_conditions(self):
        src = _src(BE.fill_shikigami)
        self.assertIn('while True:', src)
        self.assertIn('time.sleep(0.5)', src)
        self.assertIn('>= 6', src)                       # click_record.count 上限判断
        self.assertIn('raise GameStuckError', src)
        self.assertNotIn('Timer(', src)                  # 没有总超时（state-bounded）

    def test_fire_is_the_only_double_bounded_retry_loop(self):
        self.assertIn('Timer(10).start()', _src(BE.fire))
        self.assertIn('max_tries = 4', _src(BE.fire))

    def test_wait_until_appear_in_exploration_passes_wait_time(self):
        # 与 RealmRaid 相反：Exploration 唯一的 wait_until_appear 传了 wait_time=3
        src = _src(inspect.getmodule(BE))
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'wait_until_appear']
        self.assertEqual(len(calls), 1)
        c = calls[0]
        self.assertTrue(any(kw.arg == 'wait_time' for kw in c.keywords), ast.unparse(c))


# --------------------------------------------------------------------------------------
# 结构事实 —— 输入全走 Control / FrameWait 零消费者 / RuleAnimate
# --------------------------------------------------------------------------------------

class StructureTest(TestCase):
    def test_all_input_through_control_no_direct_backend(self):
        src = _src(inspect.getmodule(BE)) + _src(inspect.getmodule(E))
        for token in ('swipe_adb', 'click_adb', 'adb_shell', 'swipe_minitouch',
                      'click_minitouch', 'self.device.click(', 'self.device.swipe('):
            self.assertNotIn(token, src, token)
        # 只有 click_record 的 clear / count（记账，不是输入）
        self.assertIn('self.device.click_record_clear()', src)

    def test_frame_wait_is_only_chapter_swipe_settle_consumer(self):
        src = _src(inspect.getmodule(BE)) + _src(inspect.getmodule(E))
        self.assertEqual(src.count('wait_for_changed_and_stable('), 1)
        self.assertIn('def _wait_chapter_list_settle', src)
        self.assertNotIn('FrameStateDetector', src)

    def test_structural_stability_uses_ruleanimate_not_framewait(self):
        # arrive_end 的「等地图尽头稳定」用 RuleAnimate.stable（2 帧模板稳定），
        # 不是 module/base/frame_wait.py —— 这是 Exploration 特有的既有 structural primitive
        src = _src(inspect.getmodule(BE))
        self.assertIn('RuleAnimate(self.I_SWIPE_END)', src)
        self.assertIn('self._match_end.stable(', src)

    def test_entry_is_run_then_pre_exec_post(self):
        src = _src(E.run)
        self.assertLess(src.index('self.pre_process()'), src.index('self.exec_exp_page()'))
        self.assertLess(src.index('self.exec_exp_page()'), src.index('self.post_process()'))
        self.assertIn('raise TaskEnd', _src(BE.post_process))


# --------------------------------------------------------------------------------------
# 2026-09-08：撤销「Boss 后完全跳过地图宝箱直接退出」的错误需求专属结构
# ——恢复原生 reward 链（查地图宝箱 + 有则领取 + 不领小纸人 → 原生退出）。
# 删除的旧用例对应已废弃的 contract（见 DEVELOP_LOG 同日条）：
#   BossDirectExitContractTest 全类（_run_boss_exit_transaction / _is_boss_exit_success_state /
#     _skip_treasure_once_at_entrance / BOSS_EXIT_* / EXIT_READY..EXIT_SUCCESS）
#   BossExitSuccessStatePredicateTest 全类、RunOnExpTreasureSkipTest 全类
#   ExplorationFatigueSafePointTest 里依赖 _complete_boss_business_cycle 的用例
# --------------------------------------------------------------------------------------


class BossRewardFlowNativeTest(TestCase):
    """Boss 战后恢复原项目原生 reward / exit 链。"""

    def test_no_boss_exit_transaction_structures_remain(self):
        src = _src(inspect.getmodule(E))
        for tok in ('_run_boss_exit_transaction', '_is_boss_exit_success_state',
                    '_wait_for_boss_exit_success_state', '_complete_boss_business_cycle',
                    '_wait_for_stable_page', '_boss_exit_probe', '_skip_treasure_once_at_entrance',
                    'ExplorationExitState', 'BOSS_EXIT_', 'exit_ready', 'exit_confirm',
                    'transition_unknown', 'exit_success'):
            self.assertNotIn(tok, src, tok)

    def test_run_on_exp_main_uses_native_collect_reward(self):
        # 原生：page_exp_main 上先 collect_reward()（内部 = 地图宝箱 or 小纸人 policy）
        src = _src(E.run_on_exp_main)
        self.assertIn('if self.collect_reward():', src)
        self.assertIn('return', src)

    def test_collect_reward_is_treasure_then_paper_man(self):
        src = _src(BE.collect_reward)
        self.assertIn('self.collect_treasure_box() or self.collect_paper_man_reward()', src)

    def test_paper_man_boss_no_reward_uses_native_quit(self):
        # 「不领取小纸人」配置 + 打过 Boss → 不点小纸人奖励，走原生 quit_exp_main() 退出
        src = _src(BE.collect_paper_man_reward)
        self.assertIn("self.fire_monster_type == 'boss' and not self._config.exploration_config.collect_paper_reward",
                      src)
        i_guard = src.index("not self._config.exploration_config.collect_paper_reward")
        after = src[i_guard:]
        self.assertIn('self.quit_exp_main()', after)
        self.assertIn('return True', after)
        # 地图宝箱领取分支仍在（两个奖励不是同一个开关）
        self.assertIn('self.appear(self.I_BATTLE_REWARD) and self._config.exploration_config.collect_paper_reward',
                      src)

    def test_treasure_box_collected_when_present(self):
        # collect_treasure_box：有小 / 大宝箱 → ui_click 领取 + 等奖励页消失，返回 True；无 → False
        src = _src(BE.collect_treasure_box)
        self.assertIn('self.appear(self.I_E_REWARD_BOX_SMALL)', src)
        self.assertIn('self.appear(self.I_E_REWARD_BOX_BIG)', src)
        self.assertIn('self.ui_click_until_disappear(self.I_REWARD', src)
        self.assertIn('return False', src)

    def test_run_on_exp_entrance_collects_treasure_natively(self):
        # 非 Boss 循环回到入口：无条件 collect_treasure_box（不再有一次性 skip）
        from tasks.Exploration.config import UserStatus
        t = E.__new__(E)
        t.user_status = UserStatus.ALONE
        t.fire_monster_type = ''                      # 非 Boss 循环 → _maybe_boss_cycle_fatigue 不触发
        t.collect_treasure_box = Mock()
        t.goto_page = Mock()
        t.run_on_exp_entrance()
        t.collect_treasure_box.assert_called_once_with()
        t.goto_page.assert_called_once_with(pages.page_exp_main)
        src = _src(E.run_on_exp_entrance)
        self.assertNotIn('skip_treasure', src)
        self.assertNotIn('_skip_treasure_once_at_entrance', src)

    def test_run_on_exp_alone_collects_treasure_natively(self):
        from tasks.Exploration.config import UserStatus
        t = E.__new__(E)
        t.user_status = UserStatus.ALONE
        t.fire_monster_type = ''
        t.collect_treasure_box = Mock()
        t.goto_page = Mock()
        t.run_on_exp()
        t.collect_treasure_box.assert_called_once_with()
        t.goto_page.assert_called_once_with(pages.page_exp_main)
        self.assertNotIn('skip_treasure', _src(E.run_on_exp))

    def test_quit_exp_main_is_stale_click_safe_via_confirm_delay(self):
        # 无宝箱时游戏可能自动退出——quit_exp_main 用 appear_then_click(confirm_delay=)，
        # delay 后重新截图二次确认 I_UI_BACK_YELLOW，消失则不点，天然避免 stale click。
        src = _src(BE.quit_exp_main)
        self.assertIn('appear_then_click(self.I_UI_BACK_YELLOW, interval=0.8, policy=InteractionPolicy.NAVIGATION)',
                      src)
        # 没有新造 Boss 专用 exit transaction / current-page guard
        self.assertNotIn('detect_page_in', src)
        self.assertNotIn('GameStuckError', src)


class BossCycleFatigueTest(TestCase):
    """Fatigue Safe Point 重新挂在原生完整 cycle 的外层稳定页。"""

    def _mk(self, *, user_status, fire_monster_type):
        from datetime import datetime, timedelta
        from tasks.Exploration.config import UserStatus  # noqa: F401 (给 subTest 名用)
        t = E.__new__(E)
        t.user_status = user_status
        t.fire_monster_type = fire_monster_type
        t.start_time = datetime.now()
        t.limit_time = timedelta(minutes=30)
        t.try_fatigue_break = Mock()
        return t

    def test_solo_boss_cycle_triggers_fatigue_and_consumes_flag(self):
        from tasks.Exploration.config import UserStatus
        t = self._mk(user_status=UserStatus.ALONE, fire_monster_type='boss')
        self.assertIs(t._maybe_boss_cycle_fatigue(), True)
        t.try_fatigue_break.assert_called_once_with(
            safe=True, repeat_completed=True, deadline=t.start_time + t.limit_time,
        )
        self.assertEqual(t.fire_monster_type, '')          # 消费 Boss 标记，避免重复

    def test_solo_non_boss_cycle_no_fatigue(self):
        from tasks.Exploration.config import UserStatus
        for mtype in ('normal', ''):
            with self.subTest(mtype=mtype):
                t = self._mk(user_status=UserStatus.ALONE, fire_monster_type=mtype)
                self.assertIs(t._maybe_boss_cycle_fatigue(), False)
                t.try_fatigue_break.assert_not_called()

    def test_group_modes_never_fatigue(self):
        from tasks.Exploration.config import UserStatus
        for status in (UserStatus.LEADER, UserStatus.MEMBER):
            with self.subTest(status=status):
                t = self._mk(user_status=status, fire_monster_type='boss')
                self.assertIs(t._maybe_boss_cycle_fatigue(), False)
                t.try_fatigue_break.assert_not_called()

    def test_outer_handlers_call_safe_point_before_treasure_then_early_return(self):
        # run_on_exp_entrance / run_on_exp 顶部先 _maybe_boss_cycle_fatigue()，命中即 return
        for name in ('run_on_exp_entrance', 'run_on_exp'):
            src = _src(getattr(E, name))
            i_fatigue = src.index('self._maybe_boss_cycle_fatigue()')
            self.assertIn('if self._maybe_boss_cycle_fatigue():\n', src)
            self.assertIn('return', src[i_fatigue:src.index('return', i_fatigue) + 10])
            self.assertLess(i_fatigue, src.index('self.collect_treasure_box()'))

    def test_run_on_exp_entrance_boss_cycle_defers_treasure_to_next_dispatch(self):
        from tasks.Exploration.config import UserStatus
        t = E.__new__(E)
        t.user_status = UserStatus.ALONE
        t.fire_monster_type = 'boss'
        t.start_time = __import__('datetime').datetime.now()
        t.limit_time = __import__('datetime').timedelta(minutes=30)
        t.try_fatigue_break = Mock()
        t.collect_treasure_box = Mock()
        t.goto_page = Mock()
        t.run_on_exp_entrance()
        t.try_fatigue_break.assert_called_once()
        t.collect_treasure_box.assert_not_called()          # 早返回，交下一轮 fresh dispatch
        t.goto_page.assert_not_called()

    def test_fatigue_never_on_page_exp_main(self):
        src = _src(E.run_on_exp_main)
        self.assertNotIn('_maybe_boss_cycle_fatigue', src)
        self.assertNotIn('try_fatigue_break', src)
        self.assertNotIn('begin_fatigue_task', src)

    def test_run_begins_fatigue_only_for_solo(self):
        from tasks.Exploration.config import UserStatus
        for status, expected in ((UserStatus.ALONE, 1), (UserStatus.LEADER, 0)):
            with self.subTest(status=status):
                t = E.__new__(E)
                t.pre_process = Mock(side_effect=lambda: setattr(t, 'user_status', status))
                t.begin_fatigue_task = Mock()
                t.exec_exp_page = Mock()
                t.post_process = Mock()
                t.run()
                self.assertEqual(t.begin_fatigue_task.call_count, expected)


class ChapterFrameWaitContractTest(TestCase):
    def test_helper_passes_explicit_roi_and_provisional_parameters(self):
        import tasks.Exploration.base as base_module
        result = SimpleNamespace(
            changed=False,
            stable=True,
            timed_out=True,
            elapsed=1.5,
            last_difference=0.0,
            success=False,
        )
        t = E.__new__(E)
        provider = Mock()
        t.device = SimpleNamespace(screenshot=provider)
        baseline = object()
        with patch('tasks.Exploration.base.wait_for_changed_and_stable', return_value=result) as wait:
            self.assertIs(t._wait_chapter_list_settle(baseline), False)
        wait.assert_called_once_with(
            baseline,
            provider,
            roi=base_module.EXPLORATION_LEVEL_SETTLE_ROI,
            changed_threshold=base_module.EXPLORATION_LEVEL_CHANGED_THRESHOLD,
            stable_threshold=base_module.EXPLORATION_LEVEL_STABLE_THRESHOLD,
            stable_frames=base_module.EXPLORATION_LEVEL_STABLE_FRAMES,
            timeout=base_module.EXPLORATION_LEVEL_SETTLE_TIMEOUT,
            poll_interval=base_module.EXPLORATION_LEVEL_POLL_INTERVAL,
        )

    def _chapter_task(self, settle_results):
        from tasks.Exploration.config import ExplorationLevel
        t = E.__new__(E)
        target = ExplorationLevel.EXPLORATION_28
        visible = SimpleNamespace(ocr_text=ExplorationLevel.EXPLORATION_27.value)
        found = SimpleNamespace(ocr_text=target.value)
        ocr = SimpleNamespace(
            detect_and_ocr=Mock(side_effect=[[visible], [visible], [found]]),
            keyword=None,
        )
        t.config = SimpleNamespace(
            exploration=SimpleNamespace(
                exploration_config=SimpleNamespace(exploration_level=target),
            ),
        )
        t.O_E_EXPLORATION_LEVEL_NUMBER = ocr
        t.I_E_EXPLORATION_CLICK = object()
        t.I_UI_CONFIRM = object()
        t.I_UI_CONFIRM_SAMLL = object()
        t.S_SWIPE_LEVEL_UP = object()
        t.S_SWIPE_LEVEL_DOWN = object()
        t.device = SimpleNamespace(image=object(), click_record_clear=Mock())
        t.screenshot = Mock()
        t.appear = Mock(side_effect=[False, False, False, True])
        t.appear_then_click = Mock(return_value=False)
        t.swipe = Mock(return_value=True)
        t._wait_chapter_list_settle = Mock(side_effect=settle_results)
        t.ocr_appear_click = Mock(return_value=False)
        t.wait_until_appear = Mock()
        return t, ocr

    def test_stable_framewait_is_not_semantic_chapter_success(self):
        t, ocr = self._chapter_task([True, True])
        with patch('tasks.Exploration.base.time.sleep') as sleep:
            self.assertIs(t.open_expect_level(), True)
        self.assertEqual(t._wait_chapter_list_settle.call_count, 2)
        self.assertEqual(ocr.detect_and_ocr.call_count, 3)
        sleep.assert_not_called()

    def test_framewait_timeout_still_returns_to_ocr_business_loop(self):
        t, ocr = self._chapter_task([False, False])
        with patch('tasks.Exploration.base.time.sleep') as sleep:
            self.assertIs(t.open_expect_level(), True)
        self.assertEqual(t._wait_chapter_list_settle.call_count, 2)
        self.assertEqual(ocr.detect_and_ocr.call_count, 3)
        sleep.assert_not_called()


# --------------------------------------------------------------------------------------
# 2026-09-08 Level C hotfix：轮换模式归用户所有 / Boss 直退 success 判据接受多个合法外层页
# --------------------------------------------------------------------------------------

class RotationOwnershipTest(TestCase):
    def _rot(self, auto_rotate, *, rotate_on=False, rotate_off=False):
        from tasks.Exploration.config import AutoRotate
        t = E.__new__(E)
        t._config = SimpleNamespace(
            exploration_config=SimpleNamespace(auto_rotate=auto_rotate))

        def _appear(target, **kw):
            if target is t.I_E_AUTO_ROTATE_ON:
                return rotate_on
            if target is t.I_E_AUTO_ROTATE_OFF:
                return rotate_off
            return False
        t.appear = Mock(side_effect=_appear)
        t.appear_then_click = Mock(return_value=False)
        t.click = Mock()
        return t, AutoRotate

    def test_no_config_observes_only_never_cancels_user_rotation(self):
        # 用户手工开着轮换（rotate_on=True），config=no → 脚本不点任何轮换开关，返回 False
        t, AutoRotate = self._rot('placeholder', rotate_on=True)
        t._config.exploration_config.auto_rotate = AutoRotate.no
        self.assertIs(t.switch_rotate(), False)
        t.appear_then_click.assert_not_called()
        # 没有对轮换 marker 的任何 click
        for c in t.click.call_args_list:
            self.assertNotIn(c.args[0], (t.I_E_AUTO_ROTATE_ON, t.I_E_AUTO_ROTATE_OFF))

    def test_no_config_source_has_no_rotate_toggle_click(self):
        src = _src(BE.switch_rotate)
        i_no = src.index('AutoRotate.no')
        no_branch = src[i_no:]
        self.assertNotIn('I_E_AUTO_ROTATE_ON', no_branch)
        self.assertNotIn('appear_then_click', no_branch)
        self.assertIn('pass', no_branch)

    def test_yes_config_still_manages_bench_fill(self):
        # config=yes + 轮换关着(rotate_off=True) → 打开设置页（后续 fill_shikigami + 开轮换）
        t, AutoRotate = self._rot('placeholder', rotate_off=True)
        t._config.exploration_config.auto_rotate = AutoRotate.yes
        self.assertIs(t.switch_rotate(), True)
        t.click.assert_called_once_with(t.C_CLICK_SETTINGS, interval=2)

    def test_i_e_auto_rotate_on_is_never_a_click_target_anywhere(self):
        # 全 Exploration 生产代码里，"轮换开着" marker 绝不作为 click / appear_then_click 目标
        # （点它 = 取消用户的轮换）。仅作为 page_exp_main / _exit_matcher 的识别 marker。
        src = _src(inspect.getmodule(BE)) + _src(inspect.getmodule(E))
        self.assertNotIn('appear_then_click(self.I_E_AUTO_ROTATE_ON', src)
        self.assertNotIn('click(self.I_E_AUTO_ROTATE_ON', src)
        self.assertNotIn('ui_click(self.I_E_AUTO_ROTATE_ON', src)

    def test_run_on_exp_main_still_gates_on_switch_rotate(self):
        src = _src(E.run_on_exp_main)
        self.assertIn('if self.switch_rotate() or self.user_status == UserStatus.MEMBER:', src)





if __name__ == '__main__':
    import unittest
    unittest.main()
