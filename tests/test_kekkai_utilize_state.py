# This Python file uses the following encoding: utf-8
"""`KekkaiUtilize` 状态机迁移前的 characterization（现状锁定）测试。

目的：在把好友结界蹭卡流程迁移到「状态 → 动作 → 期望状态 → 显式验证」结构 **之前**，
用纯 mock 锁住当前真实的列表滑动参数、循环边界、`swipe_adb` 直连（绕过 `Control.swipe`
与 BehaviorTrace）、固定等待，作为未来迁移的回归基线。

本轮不改 `KekkaiUtilize` 任何生产行为——这些测试只描述「现在是什么样」。选卡 / 阈值 /
排名等业务策略已有 `tests/test_kekkai_utilize_threshold.py` 覆盖，这里只补状态机控制流。
详见 `docs/Kekkai状态机静态收口.md`。

源码：`tasks/KekkaiUtilize/script_task.py`。
"""

import inspect
import re
from datetime import datetime, time as dtime, timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from module.exception import TaskEnd
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tasks.KekkaiUtilize.selected_anchor import SelectedAnchorResult


# --------------------------------------------------------------------------------------
# perform_swipe_action —— 好友结界卡列表的统一下划
# --------------------------------------------------------------------------------------

class PerformSwipeActionCharacterizationTest(TestCase):
    """当前 = `swipe_adb`(duration=2) 直连 + `click_record_clear` + `sleep(2)`，
    起点在安全区随机、位移固定 `SWIPE_DISTANCE`，返回 None。"""

    def _task(self):
        task = KU.__new__(KU)
        task.device = SimpleNamespace(
            swipe_adb=Mock(name='swipe_adb'),
            swipe=Mock(name='Control.swipe'),          # 公共滑动，应当**不被调用**
            click_record_clear=Mock(name='click_record_clear'),
        )
        return task

    def test_swipe_adb_params_and_call_order(self):
        task = self._task()
        events = []
        task.device.swipe_adb.side_effect = lambda *a, **k: events.append(('swipe_adb', a, k))
        task.device.click_record_clear.side_effect = lambda: events.append(('clear',))
        with patch('tasks.KekkaiUtilize.script_task.time.sleep',
                   side_effect=lambda s: events.append(('sleep', s))), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[470, 530]) as ri:
            ret = task.perform_swipe_action()

        self.assertIsNone(ret)
        self.assertEqual(ri.call_args_list,
                         [call(340, 600), call(500, 565)])   # X 区间, Y 区间（闭区间）
        (name, args, kwargs) = events[0]
        self.assertEqual(name, 'swipe_adb')
        self.assertEqual(args[0], (470, 530))                # p1 = (随机X, 随机Y)
        self.assertEqual(args[1], (470, 530 - 416))          # p2 = (同X, Y - SWIPE_DISTANCE)
        self.assertEqual(kwargs, {'duration': 2})            # duration 固定 2（秒）
        # 顺序：swipe_adb -> click_record_clear -> sleep(2)
        self.assertEqual([e[0] for e in events], ['swipe_adb', 'clear', 'sleep'])
        self.assertEqual(events[2], ('sleep', 2))

    def test_does_not_route_through_control_swipe_or_behavior_trace(self):
        task = self._task()
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[400, 540]):
            task.perform_swipe_action()
        task.device.swipe.assert_not_called()               # 绕过 Control.swipe → 无 BehaviorTrace
        task.device.swipe_adb.assert_called_once()

    def test_swipe_constants_are_the_current_baseline(self):
        self.assertEqual(KU.SWIPE_START_X_RANGE, (340, 600))
        self.assertEqual(KU.SWIPE_START_Y_RANGE, (500, 565))
        self.assertEqual(KU.SWIPE_DISTANCE, 416)

    def test_source_uses_swipe_adb_and_keeps_common_swipe_commented(self):
        src = inspect.getsource(KU.perform_swipe_action)
        self.assertIn('self.device.swipe_adb(', src)
        self.assertNotIn('\n        self.swipe(', src)       # 公共滑动只在注释行
        self.assertIn('# self.swipe(self.S_U_UP', src)
        self.assertIn('duration = 2', src)
        self.assertIn('random_int(', src)                    # 用公共随机源（与 KA 不同）


# --------------------------------------------------------------------------------------
# check_card_num (KekkaiUtilize) —— OCR 结界卡类型 + 数值
# --------------------------------------------------------------------------------------

class CheckCardNumUtilizeTest(TestCase):
    """KU.check_card_num：截图 → `O_CARD_NUM.ocr` → 按关键字判类型 → 正则取数值，
    返回 `(card_type, value)`；无法识别类型返回 `('unknown', 0)`，`value<=0` 会
    `push_notify` 并返回 `(card_type, 0)`。"""

    def _task(self, ocr_text):
        task = KU.__new__(KU)
        task.device = SimpleNamespace(image='FRAME')
        task.screenshot = Mock(name='screenshot')
        task.push_notify = Mock(name='push_notify')
        task.O_CARD_NUM = SimpleNamespace(ocr=Mock(return_value=ocr_text))
        return task

    def test_fish_type_from_stamina_keywords(self):
        for text in ('体力+134', 'カ 134', '力134'):
            task = self._task(text)
            self.assertEqual(task.check_card_num(), ('斗鱼', 134), text)

    def test_taiko_type_from_jade_keywords(self):
        for text in ('勾玉 67', '玉67'):
            task = self._task(text)
            self.assertEqual(task.check_card_num(), ('太鼓', 67), text)

    def test_unknown_type_returns_unknown_zero(self):
        task = self._task('???garbage')
        self.assertEqual(task.check_card_num(), ('unknown', 0))
        task.push_notify.assert_not_called()

    def test_zero_value_pushes_notify_and_returns_zero(self):
        task = self._task('体力 0')
        self.assertEqual(task.check_card_num(), ('斗鱼', 0))
        task.push_notify.assert_called_once()

    def test_always_takes_a_fresh_screenshot(self):
        task = self._task('勾玉 76')
        task.check_card_num()
        task.screenshot.assert_called_once()


# --------------------------------------------------------------------------------------
# 循环 / retry 边界（源码级）
# --------------------------------------------------------------------------------------

class UtilizeLoopBoundsTest(TestCase):
    def test_check_utilize_add_bounded_by_count_5(self):
        src = inspect.getsource(KU.check_utilize_add)
        self.assertIn('while 1:', src)
        self.assertIn('self.utilize_add_count += 1', src)
        self.assertIn('self.utilize_add_count >= 5', src)

    def test_lazy_utilize_scans_exactly_two_friend_groups(self):
        # 怠惰路径保留旧的「优先分组 → 备选分组」双分组循环
        src = inspect.getsource(KU._run_lazy_utilize)
        self.assertIn('enumerate((friend, fallback_friend)', src)
        self.assertNotIn('while ', src)

    def test_run_utilize_dispatches_search_vs_lazy(self):
        src = inspect.getsource(KU.run_utilize)
        self.assertIn('self._run_lazy_utilize(friend)', src)
        self.assertIn('self._run_search(friend)', src)
        # 旧 global-best / reselect 主路径已从 run_utilize 移除
        self.assertNotIn('_select_optimal_resource_card', src)
        self.assertNotIn('_reselect_best_card', src)

    def test_run_search_pass_is_bounded(self):
        src = inspect.getsource(KU._run_search_pass)
        self.assertIn('range(self.SEARCH_MAX_SWIPES + 1)', src)
        self.assertIn('Timer(self.SEARCH_PASS_TIMEOUT)', src)
        self.assertEqual(KU.SEARCH_MAX_SWIPES, 20)
        self.assertEqual(KU.SEARCH_PASS_TIMEOUT, 120)
        # 「当前屏没有目标模板」不再被当作到底：源码里没有 miss_count 计数
        self.assertNotIn('miss_count', src)
        self.assertNotIn('CONSEC_MISS', src)

    def test_select_lazy_resource_card_is_double_bounded(self):
        src = inspect.getsource(KU._select_lazy_resource_card)
        self.assertIn('max_swipes = 20', src)
        self.assertIn('range(max_swipes + 1)', src)
        self.assertIn('Timer(120)', src)

    def test_global_best_and_reselect_cluster_removed(self):
        for name in ('_select_optimal_resource_card', '_current_select_best',
                     '_reselect_best_card', '_card_rank', '_reward_threshold',
                     '_reaches_reward_threshold', 'order_cards'):
            self.assertFalse(hasattr(KU, name), name)
        for attr in ('utilize_best_value', 'utilize_best_card_class',
                     'utilize_last_card_class', 'ap_max_num', 'jade_max_num'):
            self.assertFalse(hasattr(KU, attr), attr)

    def test_switch_friend_list_while_loop_has_total_timeout(self):
        src = inspect.getsource(KU.switch_friend_list)
        self.assertIn('while 1:', src)
        self.assertIn('Timer(self.SWITCH_FRIEND_LIST_TIMEOUT)', src)
        self.assertIn('raise GamePageUnknownError', src)
        self.assertEqual(KU.SWITCH_FRIEND_LIST_TIMEOUT, 20)

    def test_check_and_get_guild_rewards_is_state_bounded_progress_timer(self):
        # `while True` + `Timer(2)`，每收到一个奖励就 reset；无奖励 2s 后 return False
        src = inspect.getsource(KU.check_and_get_guild_rewards)
        self.assertIn('while True:', src)
        self.assertIn('timer_check = Timer(2).start()', src)
        self.assertIn('timer_check.reset()', src)
        self.assertIn('if timer_check.reached():', src)

    def test_receive_guild_assets_bounded_by_max_tries(self):
        src = inspect.getsource(KU.receive_guild_assets)
        self.assertIn('for i in range(1, max_tries+1)', src)


# --------------------------------------------------------------------------------------
# 固定 / 随机等待清单（源码级锁定关键点）
# --------------------------------------------------------------------------------------

class UtilizeWaitInventoryTest(TestCase):
    def test_detail_page_load_wait_is_fixed_sleep_2(self):
        # 「等待结界卡详情加载」当前是固定等待：搜索 PASS 用 DETAIL_LOAD_WAIT=2、
        # 怠惰路径用 time.sleep(2)。换成语义等待属 Level C。
        self.assertEqual(KU.DETAIL_LOAD_WAIT, 2)
        self.assertIn('time.sleep(self.DETAIL_LOAD_WAIT)', inspect.getsource(KU._run_search_pass))
        self.assertIn('time.sleep(2)', inspect.getsource(KU._select_lazy_resource_card))

    def test_post_swipe_wait_is_fixed_sleep_2(self):
        self.assertIn('time.sleep(2)', inspect.getsource(KU.perform_swipe_action))

    def test_lazy_mode_roll_uses_random_delay_as_a_float_source(self):
        # 既有瑕疵：`random_delay(0.0, 1.0)` 在这里被当成「取 [0,1) 随机数」用于概率判定，
        # 不是真的等待。本轮不改。
        src = inspect.getsource(KU.run)
        self.assertIn('random_delay(0.0, 1.0)', src)
        self.assertIn('self.utilize_lazy_mode_active = (', src)


# --------------------------------------------------------------------------------------
# 结构事实 —— FrameWait 消费者仅 _perform_search_swipe（K3）/ swipe_adb 直连清单
# --------------------------------------------------------------------------------------

class UtilizeStructureTest(TestCase):
    def test_frame_wait_consumer_is_only_perform_search_swipe(self):
        # K3（2026-09-07）：KekkaiUtilize 成为 FrameWait 的首个生产消费者，但**仅**用于
        # 标准 PASS + minitouch 的 swipe settle（`_perform_search_swipe`），别处一律不碰。
        mod_src = inspect.getsource(inspect.getmodule(KU))
        self.assertIn('from module.base.frame_wait import wait_for_changed_and_stable', mod_src)
        self.assertEqual(mod_src.count('wait = wait_for_changed_and_stable('), 1)   # 恰一处调用
        sw_src = inspect.getsource(KU._perform_search_swipe)
        self.assertIn('wait = wait_for_changed_and_stable(', sw_src)
        self.assertIn('return wait.success', sw_src)
        # 怠惰路径 / 非标准 PASS 循环 / 旧 ADB 下划都不接 FrameWait
        for fn in (KU._run_lazy_utilize, KU._select_lazy_resource_card,
                   KU.perform_swipe_action, KU.run_utilize, KU._run_search):
            self.assertNotIn('wait_for_changed_and_stable', inspect.getsource(fn))
        # 不自己实例化 FrameStateDetector（帧差算法是 FrameWait 内部职责，KekkaiUtilize 只调 wait 层）
        self.assertNotIn('FrameStateDetector(', mod_src)

    def test_swipe_adb_direct_call_sites_in_utilize_module(self):
        # 全模块只有 perform_swipe_action 一处直连 swipe_adb
        src = inspect.getsource(inspect.getmodule(KU))
        self.assertEqual(src.count('self.device.swipe_adb('), 1)

    def test_entry_is_run(self):
        src = inspect.getsource(KU.run)
        self.assertIn('self.goto_page(page_guild_realm)', src)
        self.assertIn('raise TaskEnd', src)


# --------------------------------------------------------------------------------------
# 单向分区 PASS 搜索（取消蛇形 / 全部 TOP→BOTTOM / 跨→同→跨→同 或 同→跨→同）
# --------------------------------------------------------------------------------------

from tasks.KekkaiUtilize.config import SelectFriendList, UtilizeRule
from tasks.KekkaiUtilize.script_task import PassResult, SearchPass
from tasks.KekkaiUtilize.utils import FISH_REWARD_TIERS, TAIKO_REWARD_TIERS, lower_reward_tier

CROSS = SelectFriendList.DIFFERENT_SERVER
SAME = SelectFriendList.SAME_SERVER


def _cfg(rule=UtilizeRule.DEFAULT, fish=151, taiko=76):
    from tasks.KekkaiUtilize.config import UtilizeConfig
    uc = UtilizeConfig(utilize_rule=rule, fish_reward_threshold=fish, taiko_reward_threshold=taiko)
    return SimpleNamespace(kekkai_utilize=SimpleNamespace(utilize_config=uc))


class BuildSearchPassesTest(TestCase):
    def _groups(self, passes):
        return [(p.friend_group, sorted(p.stars), p.final_fallback) for p in passes]

    def test_cross_priority_pass_order(self):
        t = KU.__new__(KU)
        t.config = _cfg()
        passes = t._build_search_passes(CROSS)
        self.assertEqual(self._groups(passes), [
            (CROSS, [6], False),
            (SAME, [6], False),
            (CROSS, [5, 6], False),
            (SAME, [5, 6], True),
        ])

    def test_same_priority_pass_order(self):
        t = KU.__new__(KU)
        t.config = _cfg()
        passes = t._build_search_passes(SAME)
        self.assertEqual(self._groups(passes), [
            (SAME, [6], False),
            (CROSS, [6], False),
            (SAME, [5, 6], True),
        ])

    def test_only_last_pass_is_final_fallback(self):
        t = KU.__new__(KU)
        t.config = _cfg()
        for friend in (CROSS, SAME):
            finals = [p.final_fallback for p in t._build_search_passes(friend)]
            self.assertEqual(finals.count(True), 1)
            self.assertTrue(finals[-1])

    def test_threshold_lowered_exactly_once_between_phases(self):
        t = KU.__new__(KU)
        t.config = _cfg(fish=151, taiko=76)
        passes = t._build_search_passes(CROSS)
        # 前两个 PASS = 高阈值（配置值）
        self.assertEqual(passes[0].threshold_map, {'斗鱼': 151, '太鼓': 76})
        self.assertEqual(passes[1].threshold_map, {'斗鱼': 151, '太鼓': 76})
        # 后面的 PASS = 降低一档（且只降一次，PASS3 和 PASS4 同一份 lower）
        lower = {'斗鱼': lower_reward_tier(151, FISH_REWARD_TIERS),
                 '太鼓': lower_reward_tier(76, TAIKO_REWARD_TIERS)}
        self.assertEqual(lower, {'斗鱼': 143, '太鼓': 67})
        self.assertEqual(passes[2].threshold_map, lower)
        self.assertEqual(passes[3].threshold_map, lower)

    def test_phase1_targets_are_six_star_only(self):
        t = KU.__new__(KU)
        t.config = _cfg(rule=UtilizeRule.DEFAULT)
        names = [im.name for im in t._build_search_passes(CROSS)[0].targets.images]
        self.assertEqual(sorted(names), ['UTILIZE_U_FISH_6', 'UTILIZE_U_TAIKO_6'])

    def test_phase2_targets_are_five_and_six_star(self):
        t = KU.__new__(KU)
        t.config = _cfg(rule=UtilizeRule.DEFAULT)
        names = [im.name for im in t._build_search_passes(CROSS)[2].targets.images]
        self.assertEqual(sorted(names), [
            'UTILIZE_U_FISH_5', 'UTILIZE_U_FISH_6',
            'UTILIZE_U_TAIKO_5', 'UTILIZE_U_TAIKO_6',
        ])

    def test_rule_filters_targets(self):
        t = KU.__new__(KU)
        t.config = _cfg(rule=UtilizeRule.FISH)
        p1 = [im.name for im in t._build_search_passes(SAME)[0].targets.images]
        self.assertEqual(p1, ['UTILIZE_U_FISH_6'])
        t.config = _cfg(rule=UtilizeRule.TAIKO)
        p3 = [im.name for im in t._build_search_passes(SAME)[-1].targets.images]
        self.assertEqual(sorted(p3), ['UTILIZE_U_TAIKO_5', 'UTILIZE_U_TAIKO_6'])


class RunSearchSequenceTest(TestCase):
    """_run_search 编排：每 PASS 前只 switch_friend_list(目标分组) → 跑 PASS → 命中即停 / 全部失败。"""

    def setUp(self):
        p = patch('tasks.KekkaiUtilize.script_task.logger')   # 控制台 GBK，屏蔽日志输出
        p.start()
        self.addCleanup(p.stop)

    def _task(self, pass_results):
        t = KU.__new__(KU)
        t.config = _cfg()
        t.switch_friend_list = Mock(name='switch')
        # 标准路径不再调用它；设成 Mock 只为断言 call_count == 0
        t._reset_utilize_friend_list = Mock(name='legacy_reset_must_not_be_called')
        # _build_search_passes 用真实的（纯逻辑），_run_search_pass 用脚本替身
        t._run_search_pass = Mock(side_effect=pass_results)
        return t

    def test_first_pass_hit_stops_immediately(self):
        t = self._task([(PassResult.HIT, True)])
        self.assertIs(t._run_search(CROSS), True)
        self.assertEqual(t._run_search_pass.call_count, 1)
        self.assertEqual(t.switch_friend_list.call_count, 1)
        self.assertEqual(t.switch_friend_list.call_args[0][0], CROSS)
        self.assertEqual(t._reset_utilize_friend_list.call_count, 0)   # legacy helper 不参与标准路径

    def test_second_pass_hit_skips_lower_phase(self):
        t = self._task([(PassResult.PASS_MISS, True), (PassResult.HIT, True)])
        self.assertIs(t._run_search(CROSS), True)
        self.assertEqual(t._run_search_pass.call_count, 2)   # 第 3、4 个 PASS 不执行
        self.assertEqual(
            [c[0][0] for c in t.switch_friend_list.call_args_list],
            [CROSS, SAME],
        )
        self.assertEqual(t._reset_utilize_friend_list.call_count, 0)

    def test_final_use_last_returns_true(self):
        t = self._task([(PassResult.PASS_MISS, False), (PassResult.PASS_MISS, False),
                        (PassResult.PASS_MISS, False), (PassResult.FINAL_USE_LAST, True)])
        self.assertIs(t._run_search(CROSS), True)
        self.assertEqual(t._run_search_pass.call_count, 4)

    def test_all_pass_miss_no_candidate_returns_none(self):
        t = self._task([(PassResult.PASS_MISS, False)] * 4)
        self.assertIsNone(t._run_search(CROSS))             # None → 外层按低价值失败 +20min

    def test_pass_miss_with_candidates_but_no_final_use_returns_false(self):
        # 极端：早期 PASS 点过候选没达标，final PASS 一张候选都没有 → False（外层重试链）
        t = self._task([(PassResult.PASS_MISS, True), (PassResult.PASS_MISS, False),
                        (PassResult.PASS_MISS, True), (PassResult.PASS_MISS, False)])
        self.assertIs(t._run_search(CROSS), False)

    def test_abort_bails_out(self):
        t = self._task([(PassResult.PASS_MISS, True), (PassResult.ABORT, False)])
        self.assertIs(t._run_search(CROSS), False)
        self.assertEqual(t._run_search_pass.call_count, 2)   # 不再跑剩余 PASS


class RunSearchGroupSwitchOnlyTest(TestCase):
    """标准 D017 每个 PASS 前只 `switch_friend_list(target)`，legacy `_reset_utilize_friend_list`
    / `S_U_END` 预滚 / away-back toggle 已从标准路径移除。依据：Level C 确认「只要 SAME/CROSS
    发生实际切换，新进入的分组列表必定从顶部显示」。"""

    def setUp(self):
        p = patch('tasks.KekkaiUtilize.script_task.logger')
        p.start()
        self.addCleanup(p.stop)

    def _task(self, pass_results):
        t = KU.__new__(KU)
        t.config = _cfg()
        t.switch_friend_list = Mock(name='switch')
        t._reset_utilize_friend_list = Mock(name='legacy_reset_must_not_be_called')
        t.swipe = Mock(name='swipe_must_not_be_called_in_run_search')
        t._run_search_pass = Mock(side_effect=pass_results)
        return t

    # 5. `_build_search_passes()`：相邻 PASS 的 friend_group 必须不同
    def test_adjacent_pass_groups_always_differ(self):
        t = KU.__new__(KU)
        t.config = _cfg()
        for friend in (SAME, CROSS):
            groups = [p.friend_group for p in t._build_search_passes(friend)]
            for a, b in zip(groups, groups[1:]):
                self.assertNotEqual(a, b, (friend, groups))

    # 3. SAME → CROSS → SAME：每个 PASS 前只 switch_friend_list(PASS.group)，无 _reset
    def test_same_priority_only_switches_no_reset(self):
        t = self._task([(PassResult.PASS_MISS, False)] * 3)
        t._run_search(SAME)
        self.assertEqual(
            [c[0][0] for c in t.switch_friend_list.call_args_list], [SAME, CROSS, SAME])
        self.assertEqual(t._reset_utilize_friend_list.call_count, 0)
        self.assertEqual(t.swipe.call_count, 0)

    # 4. CROSS → SAME → CROSS → SAME：同上
    def test_cross_priority_only_switches_no_reset(self):
        t = self._task([(PassResult.PASS_MISS, False)] * 4)
        t._run_search(CROSS)
        self.assertEqual(
            [c[0][0] for c in t.switch_friend_list.call_args_list], [CROSS, SAME, CROSS, SAME])
        self.assertEqual(t._reset_utilize_friend_list.call_count, 0)
        self.assertEqual(t.swipe.call_count, 0)

    # 1 + 6. FIRST_CANDIDATE_SCAN 之前：0 次 swipe、0 次 _reset；switch 恰在 _run_search_pass 之前
    def test_no_swipe_or_reset_before_first_pass_scan(self):
        order = []
        t = KU.__new__(KU)
        t.config = _cfg()
        t.switch_friend_list = Mock(side_effect=lambda g: order.append(('switch', g)))
        t._reset_utilize_friend_list = Mock(side_effect=lambda g: order.append(('reset', g)))
        t.swipe = Mock(side_effect=lambda *a, **k: order.append(('swipe',)))
        t._run_search_pass = Mock(side_effect=lambda sp: (order.append(('scan', sp.friend_group))
                                                         or (PassResult.HIT, True)))
        t._run_search(SAME)
        self.assertEqual(order, [('switch', SAME), ('scan', SAME)])   # 切一次 → 立即扫描

    # 6 (源码级). 标准 _run_search 里没有 S_U_END、没有对 legacy helper 的调用
    def test_run_search_source_has_no_s_u_end_and_no_legacy_reset_call(self):
        src = inspect.getsource(KU._run_search)
        self.assertIn('self.switch_friend_list(search_pass.friend_group)', src)
        self.assertNotIn('S_U_END', src)
        self.assertNotIn('self._reset_utilize_friend_list(', src)   # 只有 docstring 里提到名字，无调用

    # 2. switch_friend_list 行为：已在目标分组 → 0 次 tab click；不在 → 恰 1 次，且不做 away/back
    def test_switch_friend_list_no_click_when_already_on_target(self):
        t = KU.__new__(KU)
        t.screenshot = Mock()
        t.appear = Mock(return_value=True)          # 目标分组选中态一开始就在
        t.device = Mock()
        with patch('tasks.KekkaiUtilize.script_task.time'):
            t.switch_friend_list(SAME)
        self.assertEqual(t.device.click.call_count, 0)

    def test_switch_friend_list_single_click_when_not_on_target(self):
        t = KU.__new__(KU)
        t.screenshot = Mock()
        # 第一帧不在目标分组 → 点一次 tab → 第二帧到位 break
        t.appear = Mock(side_effect=[False, True])
        t.device = Mock()
        fake_tab = Mock()
        fake_tab.coord.return_value = (270, 127)
        fake_tab.name = 'utilize_friend_group'
        t.I_UTILIZE_FRIEND_GROUP = fake_tab
        with patch('tasks.KekkaiUtilize.script_task.time'), \
             patch('tasks.KekkaiUtilize.script_task.Timer') as TimerMock:
            TimerMock.return_value.start.return_value = TimerMock.return_value
            # reached() 调用序：iter1 timeout(False) → iter1 timer_click(True → 点击)
            TimerMock.return_value.reached.side_effect = [False, True]
            t.switch_friend_list(SAME)
        self.assertEqual(t.device.click.call_count, 1)                 # 恰 1 次，没有 away/back
        self.assertEqual(t.device.click.call_args.kwargs.get('x'), 270)
        self.assertEqual(t.device.click.call_args.kwargs.get('control_name'), 'utilize_friend_group')

    # 7. K1：标准 PASS 的下划入口不受本轮影响
    def test_k1_helper_call_site_unchanged(self):
        src = inspect.getsource(KU._run_search_pass)
        self.assertIn('self._perform_search_swipe()', src)
        self.assertNotIn('_reset_utilize_friend_list', src)

    # 8. lazy 仍保留 legacy helper（滚到底 + 双切）
    def test_lazy_still_calls_legacy_reset_helper(self):
        lazy_src = inspect.getsource(KU._run_lazy_utilize)
        self.assertIn('self._reset_utilize_friend_list(target_friend)', lazy_src)
        reset_src = inspect.getsource(KU._reset_utilize_friend_list)
        self.assertIn('self.swipe(self.S_U_END, interval=3)', reset_src)


class RunSearchPassTest(TestCase):
    """单个 PASS：只向下扫描，miss≠bottom，命中即停，final 到底用最后候选。"""

    def setUp(self):
        for target in ('tasks.KekkaiUtilize.script_task.logger',
                       'tasks.KekkaiUtilize.script_task.time.sleep'):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)
        # K4（2026-09-07）：`_run_search_pass` 每屏都会调 `detect_selected_anchor`（走图像 RPC）。
        # 本类只测 PASS 控制流，默认让锚点「测量不可用」——K4 退回完整扫描，D017 行为不变。
        p = patch('tasks.KekkaiUtilize.script_task.detect_selected_anchor',
                  return_value=SelectedAnchorResult(available=False))
        p.start()
        self.addCleanup(p.stop)

    def _task(self, screens, ocr_results, empty_after=None):
        """screens: 每屏 find_everyone 返回；ocr_results: 每次 check_card_num 返回；
        empty_after: I_U_EMPTY_CARD 从第几屏(0-indexed)开始出现（None=永不）。"""
        t = KU.__new__(KU)
        t.config = _cfg()
        t.I_U_EMPTY_CARD = object()
        t.C_SELECT_CARD = SimpleNamespace(roi_front=None)
        t.device = SimpleNamespace(image='IMG', image_frame_id='FID')
        t.screenshot = Mock()
        t.click = Mock()
        # 标准 PASS 的下划入口自 K1 起是 `_perform_search_swipe`（minitouch → TouchSwipe
        # trajectory，其它后端回退旧 `perform_swipe_action`）。K3 起它返回 bool：
        # True = swipe 后列表 changed&stable，False = 未滚动/不稳/超时。本类只测 PASS 循环
        # 控制流，默认让它「滑动成功」；失败分支单独测。
        t._perform_search_swipe = Mock(return_value=True)
        t.perform_swipe_action = Mock()          # 兼容旧断言 / 怠惰路径（此处不触发）
        t.check_card_num = Mock(side_effect=list(ocr_results))
        self._screen_iter = iter(screens)
        self._screen_idx = -1

        def _find(_img, frame_id=None):
            self._screen_idx += 1
            return next(self._screen_iter, None)
        self._find = _find

        def _appear(img):
            return empty_after is not None and self._screen_idx >= empty_after
        t.appear = Mock(side_effect=_appear)
        return t

    def _pass(self, final=False, stars=frozenset({5, 6})):
        return SearchPass(CROSS, stars, {'斗鱼': 143, '太鼓': 67}, final,
                          targets=SimpleNamespace(find_everyone=self._find))

    def test_hit_stops_and_returns_hit(self):
        card = ('img', 0.9, (10, 20, 5, 5))
        t = self._task([[card, card]], [('斗鱼', 118), ('斗鱼', 151)])
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass())
        self.assertIs(result, PassResult.HIT)
        self.assertTrue(clicked)
        self.assertEqual(t.click.call_count, 2)              # 同屏第 1 张不达标，继续查第 2 张

    def test_empty_screens_keep_swiping_not_bottom(self):
        card = ('img', 0.9, (10, 20, 5, 5))
        # 前 3 屏没有目标模板（乱序列表中间），第 4 屏才命中
        t = self._task([None, None, None, [card]], [('斗鱼', 151)])
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, _ = t._run_search_pass(self._pass())
        self.assertIs(result, PassResult.HIT)
        self.assertEqual(t._perform_search_swipe.call_count, 3)  # 空屏继续下滑，没有当作到底

    def test_final_pass_bottom_uses_last_clicked_candidate(self):
        card = ('img', 0.9, (10, 20, 5, 5))
        t = self._task(
            [[card], [card], [card], None],
            [('斗鱼', 109), ('斗鱼', 118), ('斗鱼', 126)],   # A/B/C 都不达 143
            empty_after=3,
        )
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass(final=True))
        self.assertIs(result, PassResult.FINAL_USE_LAST)
        self.assertTrue(clicked)
        self.assertEqual(t.click.call_count, 3)              # A/B/C 都点过；C 是最后一次点击

    def test_final_pass_bottom_without_any_candidate_is_pass_miss(self):
        t = self._task([None], [], empty_after=0)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass(final=True))
        self.assertIs(result, PassResult.PASS_MISS)
        self.assertFalse(clicked)                            # 一张候选都没点 → 不能盲目进结界

    def test_non_final_pass_bottom_no_hit_is_pass_miss(self):
        card = ('img', 0.9, (10, 20, 5, 5))
        t = self._task([[card], None], [('斗鱼', 118)], empty_after=1)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass(final=False))
        self.assertIs(result, PassResult.PASS_MISS)          # 普通 PASS 到底不达标 → 换下一 PASS
        self.assertTrue(clicked)

    def test_max_swipes_is_safety_abort_not_bottom(self):
        # 一直有候选、都不达标、EMPTY 永不出现 → 达到滑动上限当作页面异常 ABORT
        card = ('img', 0.9, (10, 20, 5, 5))
        t = self._task([[card]] * 25, [('斗鱼', 118)] * 25, empty_after=None)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, _ = t._run_search_pass(self._pass(final=True))
        self.assertIs(result, PassResult.ABORT)
        self.assertEqual(t._perform_search_swipe.call_count, KU.SEARCH_MAX_SWIPES)

    def test_ocr_unknown_candidate_is_skipped_but_counts_as_clicked(self):
        card = ('img', 0.9, (10, 20, 5, 5))
        t = self._task([[card, card], None],
                       [('unknown', 0), ('斗鱼', 143)], empty_after=1)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass(final=True))
        self.assertIs(result, PassResult.HIT)
        self.assertTrue(clicked)

    def test_swipe_wait_failure_maps_to_abort_not_bottom(self):
        # K3：swipe 后列表未 changed&stable（_perform_search_swipe 返回 False）——
        # 第一屏无候选、EMPTY 永不出现，下一次下划失败 → 立即 ABORT，绝不当作 PASS_MISS/到底
        t = self._task([None, [('img', 0.9, (10, 20, 5, 5))]], [('斗鱼', 151)],
                       empty_after=None)
        t._perform_search_swipe = Mock(return_value=False)
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            result, clicked = t._run_search_pass(self._pass(final=True))
        self.assertIs(result, PassResult.ABORT)          # 不是 PASS_MISS / FINAL_USE_LAST
        self.assertFalse(clicked)
        self.assertEqual(t._perform_search_swipe.call_count, 1)   # 一次失败即停，无内部重试
        t.appear.assert_called()                          # 仍先查过 I_U_EMPTY_CARD（未命中才滑）


# --------------------------------------------------------------------------------------
# K4：selected anchor 实际滚动位移 + 一帧对一帧投影去重（在 _run_search_pass 里集成）
# --------------------------------------------------------------------------------------

class K4IntegrationTest(TestCase):
    """K4 = 用 I_IS_SELECTED 锚点测实际滚动、把上一屏候选投影到当前屏去重，只处理真正新进入的。

    锁定：测量不可用 → 完整扫描（不漏卡）；全 duplicate 不 ABORT/BOTTOM/PASS_MISS；
    K3 失败仍 ABORT（不进 K4）；BOTTOM 仍只认 I_U_EMPTY_CARD；FINAL_USE_LAST / clicked_any 不变；
    K4_ENABLED=False → 纯 D017。
    """

    def setUp(self):
        for tgt in ('tasks.KekkaiUtilize.script_task.logger',
                    'tasks.KekkaiUtilize.script_task.time.sleep'):
            p = patch(tgt)
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def _card(name, y):
        return (SimpleNamespace(name=name), 0.9, (540, int(y), 70, 54))

    @staticmethod
    def _anchor(center_y):
        return SelectedAnchorResult(available=True, center_y=float(center_y),
                                    bbox=(610, int(center_y - 29.5), 21, 59), score=0.97, match_count=1)

    _UNAVAIL = SelectedAnchorResult(available=False)

    def _task(self, screens, ocr_results, anchor_side_effect, empty_after=None):
        t = KU.__new__(KU)
        t.config = _cfg()
        t.I_U_EMPTY_CARD = object()
        t.C_SELECT_CARD = SimpleNamespace(roi_front=None)
        t.device = SimpleNamespace(image='IMG', image_frame_id='FID')
        t.screenshot = Mock()
        t.click = Mock()
        t._perform_search_swipe = Mock(return_value=True)
        t.check_card_num = Mock(side_effect=list(ocr_results))
        self._it = iter(screens)
        self._idx = -1

        def _find(_img, frame_id=None):
            self._idx += 1
            return next(self._it, None)

        def _appear(_img):
            return empty_after is not None and self._idx >= empty_after

        t.appear = Mock(side_effect=_appear)
        anchor_patch = patch('tasks.KekkaiUtilize.script_task.detect_selected_anchor',
                             side_effect=list(anchor_side_effect))
        self.anchor_mock = anchor_patch.start()
        self.addCleanup(anchor_patch.stop)
        sp = SearchPass(CROSS, frozenset({5, 6}), {'斗鱼': 143, '太鼓': 67}, True,
                        targets=SimpleNamespace(find_everyone=_find))
        return t, sp

    # K4_LIST_VISIBLE_Y = (156, 606)；卡 h=54 → center=y+27；投影后中心须落 [156,606]
    # （即 129 <= y_prev - dy <= 579），否则该上一屏候选被判「已滚出屏」不参与去重。

    def test_dedup_projects_previous_and_only_new_candidates_are_clicked(self):
        # 屏0：A(T1,y300) B(T2,y406) —— 都点开、都不达标
        # anchor before_0=500 / after_1=400 → actual_dy=100 → 投影 A→200, B→306
        # 屏1：A'(T1,y200) B'(T2,y306) C(T1,y412) —— A'/B' 与投影重合 → duplicate；只有 C 是 new
        # 屏2：None + EMPTY → FINAL_USE_LAST（final PASS 且点过候选）
        screens = [
            [self._card('T1', 300), self._card('T2', 406)],
            [self._card('T1', 200), self._card('T2', 306), self._card('T1', 412)],
            None,
        ]
        ocr = [('斗鱼', 100)] * 20                       # 全部不达标（143），不会 HIT
        anchors = [self._anchor(500)] + [self._anchor(400)] * 20
        t, sp = self._task(screens, ocr, anchors, empty_after=2)
        result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.FINAL_USE_LAST)
        self.assertTrue(clicked)
        self.assertEqual(t.click.call_count, 3)          # 屏0: A,B(2) + 屏1: 只有 C(1)——A'/B' 被去重跳过

    def test_measurement_unavailable_falls_back_to_full_scan(self):
        # 同样两屏，但锚点全 unavailable → dedup_dy=None → 不去重，屏1 三张全处理
        screens = [
            [self._card('T1', 300), self._card('T2', 406)],
            [self._card('T1', 200), self._card('T2', 306), self._card('T1', 412)],
            None,
        ]
        ocr = [('斗鱼', 100)] * 20
        anchors = [self._UNAVAIL] * 20
        t, sp = self._task(screens, ocr, anchors, empty_after=2)
        result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.FINAL_USE_LAST)
        self.assertEqual(t.click.call_count, 5)          # 屏0: 2 + 屏1: 3（完整扫描，无去重）

    def test_all_duplicate_current_does_not_abort_or_bottom(self):
        # 屏1 检测到的卡全部来自屏0（小步 swipe），new=[] —— 不 ABORT/PASS_MISS/BOTTOM，继续下滑
        screens = [
            [self._card('T1', 300), self._card('T2', 406)],
            [self._card('T1', 250), self._card('T2', 356)],   # dy=50 → 投影 250/356，与屏1 重合
            None,
        ]
        ocr = [('斗鱼', 100)] * 20
        anchors = [self._anchor(500)] + [self._anchor(450)] * 20   # before_0=500 / after_1=450 → dy=50
        t, sp = self._task(screens, ocr, anchors, empty_after=2)
        result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.FINAL_USE_LAST)        # 靠 EMPTY 到底、点过候选
        self.assertTrue(clicked)
        self.assertEqual(t.click.call_count, 2)                 # 屏1 全 duplicate → 0 次点击
        self.assertGreaterEqual(t._perform_search_swipe.call_count, 1)  # 全 duplicate 仍继续下滑

    def test_k3_failure_still_aborts_and_k4_after_anchor_not_taken(self):
        # 屏0 处理完 → swipe 失败（K3 False）→ ABORT。绝不进入 K4 的 after anchor / dedup。
        screens = [[self._card('T1', 300)], [self._card('T1', 300)]]
        ocr = [('斗鱼', 100)] * 5
        anchors = [self._anchor(500)] * 5                # 只会用到 before_0
        t, sp = self._task(screens, ocr, anchors, empty_after=None)
        t._perform_search_swipe = Mock(return_value=False)
        result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.ABORT)
        self.assertEqual(t._perform_search_swipe.call_count, 1)
        # detect_selected_anchor 只被调 1 次（屏0 swipe 前的 before），没有 after
        self.assertEqual(self.anchor_mock.call_count, 1)

    def test_bottom_still_only_i_u_empty_card(self):
        # 屏1 全 duplicate（new=[]），屏2 起无候选，EMPTY 永不出现 → 下滑到 MAX → ABORT（不是 BOTTOM）
        screens = [[self._card('T1', 300)], [self._card('T1', 250)]] + [None] * 25
        ocr = [('斗鱼', 100)] * 5
        anchors = [self._anchor(500)] + [self._anchor(450)] * 60   # before_0=500 / after_1=450 → dy=50
        t, sp = self._task(screens, ocr, anchors, empty_after=None)
        result, _ = t._run_search_pass(sp)
        self.assertIs(result, PassResult.ABORT)           # 达到 MAX_SWIPES 安全中止，不当作到底
        self.assertEqual(t.click.call_count, 1)           # 只有屏0 那张（屏1 duplicate、之后无卡）

    def test_k4_disabled_is_pure_d017(self):
        screens = [
            [self._card('T1', 300), self._card('T2', 406)],
            [self._card('T1', 200), self._card('T2', 306), self._card('T1', 412)],
            None,
        ]
        ocr = [('斗鱼', 100)] * 20
        anchors = [self._anchor(500)] * 20
        t, sp = self._task(screens, ocr, anchors, empty_after=2)
        with patch.object(KU, 'K4_ENABLED', False):
            result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.FINAL_USE_LAST)
        self.assertEqual(t.click.call_count, 5)           # 无去重（屏0:2 + 屏1:3）
        self.anchor_mock.assert_not_called()             # K4 关 → 根本不调锚点检测

    def test_new_candidate_still_hits_threshold_normally(self):
        # 去重之后剩下的 new 候选仍走正常 threshold 判断 → HIT；dup 卡不被重复点
        screens = [
            [self._card('T1', 300)],
            [self._card('T1', 200)],        # dy=100 → 投影 200，与屏1 重合 → dup → new=[]
            [self._card('T2', 300)],        # 新的一屏，达标 → HIT
        ]
        ocr = [('斗鱼', 100), ('斗鱼', 151)] + [('斗鱼', 100)] * 10
        anchors = ([self._anchor(500), self._anchor(400),        # before_0 / after_1 → dy=100
                    self._anchor(400), self._anchor(300)]         # before_1 / after_2 → dy=100
                   + [self._anchor(300)] * 10)
        t, sp = self._task(screens, ocr, anchors, empty_after=None)
        result, clicked = t._run_search_pass(sp)
        self.assertIs(result, PassResult.HIT)
        self.assertEqual(t.click.call_count, 2)          # 屏0 T1 + 屏2 T2；屏1 dup 未点 —— dedup 失败会是 3

    def test_source_wires_k4_between_find_everyone_and_swipe(self):
        src = inspect.getsource(KU._run_search_pass)
        self.assertIn('detect_selected_anchor(', src)
        self.assertIn('actual_scroll_dy_px(', src)
        self.assertIn('dedup_by_projection(', src)
        self.assertIn('scan_cards', src)
        # K3 契约不变：swipe 失败仍直接 ABORT
        self.assertIn('if not self._perform_search_swipe():', src)
        self.assertIn('PassResult.ABORT, clicked_any', src)
        # BOTTOM 仍只认 I_U_EMPTY_CARD
        self.assertIn('self.appear(self.I_U_EMPTY_CARD)', src)
        # 无持久历史：只保留上一屏
        self.assertIn('prev_detections = cards', src)
        self.assertNotIn('candidate_history', src)
        self.assertNotIn('global_dedup', src)


class LazyModeUntouchedTest(TestCase):
    def test_run_utilize_still_routes_lazy_to_old_double_group_flow(self):
        src = inspect.getsource(KU.run_utilize)
        self.assertIn('if self.utilize_lazy_mode_active:', src)
        self.assertIn('self._run_lazy_utilize(friend)', src)
        lazy_src = inspect.getsource(KU._run_lazy_utilize)
        self.assertIn('self._select_lazy_resource_card()', lazy_src)
        self.assertIn('enumerate((friend, fallback_friend)', lazy_src)

    def test_select_lazy_resource_card_body_unchanged_shape(self):
        src = inspect.getsource(KU._select_lazy_resource_card)
        self.assertIn('consecutive_miss_limit = 3', src)
        self.assertIn('self.lazy_scan_targets.find_everyone(', src)
        self.assertIn('miss_count > consecutive_miss_limit', src)

    def test_lazy_still_uses_perform_swipe_action_not_the_k1_helper(self):
        # K1 只把「标准 PASS」（`_run_search_pass`）的下划入口换成 `_perform_search_swipe`；
        # 怠惰路径的下划在 `_select_lazy_resource_card` 里，仍走原 `perform_swipe_action`
        # （`swipe_adb` 直连），不受输入后端迁移影响。
        lazy_src = inspect.getsource(KU._select_lazy_resource_card)
        self.assertIn('self.perform_swipe_action()', lazy_src)
        self.assertNotIn('_perform_search_swipe', lazy_src)
        # 全模块 lazy 相关函数都不碰 K1 helper
        for fn in (KU._run_lazy_utilize, KU._select_lazy_resource_card):
            self.assertNotIn('_perform_search_swipe', inspect.getsource(fn))
        # perform_swipe_action 本身仍是旧 ADB 路径
        self.assertIn('self.device.swipe_adb(', inspect.getsource(KU.perform_swipe_action))


# --------------------------------------------------------------------------------------
# K1：标准 PASS 搜索的列表下划从 ADB 迁到 TouchSwipeModel + minitouch（只换输入后端）
# K2：minitouch 路径的 commanded 位移从固定 416px 改成每次独立随机采样一个较短位移
#     （SWIPE_DISTANCE_RANGE，Level C 分档：首档 (212,265) → 2026-09-07 回调 (140,180)）
# --------------------------------------------------------------------------------------

class PerformSearchSwipeK1Test(TestCase):
    """`_perform_search_swipe`：minitouch → TouchSwipeModel 轨迹 → `Control.swipe_trajectory`；
    非 minitouch → 回退旧 `perform_swipe_action`。起点安全区 / click_record_clear 与旧路径一致，
    怠惰模式不受影响。K2 起 minitouch 路径每次随机采样 `SWIPE_DISTANCE_RANGE` 内位移（见
    `PerformSearchSwipeK2Test`）；K3 起 minitouch 路径的 swipe settle 从固定 `sleep(2)` 改成
    `wait_for_changed_and_stable`（见 `PerformSearchSwipeK3Test`）；非 minitouch 回退仍固定
    `SWIPE_DISTANCE=416` + `sleep(2)`。本类的 minitouch 用例把 FrameWait patch 成成功。"""

    _WAIT_OK = SimpleNamespace(success=True, changed=True, stable=True, timed_out=False,
                               frames_checked=3, elapsed=0.5, last_difference=0.4)

    def _task(self, control_method):
        t = KU.__new__(KU)
        t.config = SimpleNamespace(
            script=SimpleNamespace(device=SimpleNamespace(control_method=control_method)))
        t.device = SimpleNamespace(
            screenshot=Mock(name='screenshot', return_value='BASELINE'),
            swipe_trajectory=Mock(name='swipe_trajectory'),
            swipe_adb=Mock(name='swipe_adb'),
            swipe=Mock(name='Control.swipe'),
            click_record_clear=Mock(name='click_record_clear'),
        )
        return t

    def test_minitouch_uses_touch_swipe_model_and_swipe_trajectory(self):
        t = self._task('minitouch')
        traj = [(400, 540, 0), (400, 300, 9), (400, 124, 12)]   # 哨兵轨迹
        model = Mock(name='TouchSwipeModel_instance')
        model.generate = Mock(return_value=traj)
        events = []
        t.device.swipe_trajectory.side_effect = lambda *a, **k: events.append(('traj', a, k))
        t.device.click_record_clear.side_effect = lambda: events.append(('clear',))
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model) as MODEL, \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[400, 540, 160, 7]) as ri, \
             patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable',
                   side_effect=lambda *a, **k: events.append(('wait',)) or self._WAIT_OK), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep',
                   side_effect=lambda s: events.append(('sleep', s))):
            ret = t._perform_search_swipe()

        self.assertIs(ret, True)                                # K3：返回 wait.success
        # 1) 用了正式 TouchSwipeModel，且 generate 只调一次
        MODEL.assert_called_once_with()
        model.generate.assert_called_once()
        # 2) 四次闭区间随机：start_x / start_y / distance(K2) / lateral_offset(斜度)
        self.assertEqual(ri.call_args_list,
                         [call(340, 600), call(500, 565),
                          call(*KU.SWIPE_DISTANCE_RANGE), call(*KU.SWIPE_LATERAL_OFFSET_RANGE)])
        (gen_start, gen_end), _gk = model.generate.call_args
        self.assertEqual(gen_start, (400, 540))
        # 3) K2：纵向位移 = 本次随机 distance（这里 160），不是固定 416
        self.assertEqual(gen_start[1] - gen_end[1], 160)
        # 4) 斜度：end_x = start_x + lateral_offset（这里 400 + 7）
        self.assertEqual(gen_end, (400 + 7, 540 - 160))
        # 4/5) 调 device.swipe_trajectory，轨迹**原样**传入（同一对象，未重新生成）
        (traj_arg,), traj_kw = t.device.swipe_trajectory.call_args
        self.assertIs(traj_arg, traj)
        # 6) control_name 稳定
        self.assertEqual(traj_kw.get('control_name'), 'KEKKAI_UTILIZE_SWIPE')
        # 7) 不走旧 ADB、不走 Control.swipe
        t.device.swipe_adb.assert_not_called()
        t.device.swipe.assert_not_called()
        # 8) K3：顺序 swipe -> click_record_clear -> FrameWait；minitouch 路径不再有固定 sleep(2)
        self.assertEqual([e[0] for e in events], ['traj', 'clear', 'wait'])
        self.assertNotIn('sleep', [e[0] for e in events])

    def test_trajectory_generated_exactly_once(self):
        t = self._task('minitouch')
        model = Mock()
        model.generate = Mock(return_value=[(0, 0, 0), (0, -160, 9)])
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[500, 540, 160, 0]), \
             patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable',
                   return_value=self._WAIT_OK), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            t._perform_search_swipe()
        self.assertEqual(model.generate.call_count, 1)          # 一次生成，直接执行，不 log 再生成

    def test_non_minitouch_falls_back_to_old_perform_swipe_action(self):
        for method in ('adb', 'uiautomator2', 'scrcpy', 'window_message'):
            with self.subTest(method=method):
                t = self._task(method)
                t.perform_swipe_action = Mock(name='perform_swipe_action')
                with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel') as MODEL, \
                     patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable') as WFCS:
                    ret = t._perform_search_swipe()
                self.assertIs(ret, True)                           # 回退路径固定视为「已滑动」
                t.perform_swipe_action.assert_called_once_with()   # 回退旧 ADB 路径
                t.device.swipe_trajectory.assert_not_called()      # 不碰新入口
                MODEL.assert_not_called()                          # 不构造 TouchSwipeModel
                WFCS.assert_not_called()                           # 回退路径不接 FrameWait

    def test_non_minitouch_keeps_old_swipe_adb_params(self):
        # 走真实 perform_swipe_action：非 minitouch 下参数与迁移前逐字一致
        t = self._task('adb')
        events = []
        t.device.swipe_adb.side_effect = lambda *a, **k: events.append(('adb', a, k))
        with patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[470, 530]), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep',
                   side_effect=lambda s: events.append(('sleep', s))):
            t._perform_search_swipe()
        (name, args, kw) = events[0]
        self.assertEqual(name, 'adb')
        self.assertEqual(args[0], (470, 530))
        self.assertEqual(args[1], (470, 530 - 416))
        self.assertEqual(kw, {'duration': 2})
        self.assertEqual([e[0] for e in events], ['adb', 'sleep'])   # click_record_clear 是 Mock 无 side_effect

    def test_standard_pass_loop_calls_k1_helper_not_perform_swipe_action(self):
        src = inspect.getsource(KU._run_search_pass)
        self.assertIn('self._perform_search_swipe()', src)
        self.assertNotIn('self.perform_swipe_action()', src)

    def test_k1_helper_uses_public_random_and_no_fixed_140_pause(self):
        src = inspect.getsource(KU._perform_search_swipe)
        self.assertIn('random_int(', src)                       # 公共 SystemRandom 路径
        self.assertNotIn('random.Random', src)
        self.assertNotIn('numpy', src)
        self.assertNotIn('140', src)                            # 不复制 drag 的固定尾部 wait
        self.assertIn("control_name='KEKKAI_UTILIZE_SWIPE'", src)
        self.assertIn('self.device.click_record_clear()', src)
        # K3：minitouch 路径不再有固定 sleep(2) 猜停稳，改成 FrameWait changed+stable
        self.assertNotIn('time.sleep(2)', src)
        self.assertIn('wait_for_changed_and_stable(', src)
        self.assertIn('return wait.success', src)
        # K2：minitouch 路径的主方向位移用随机范围常量，不再是固定 SWIPE_DISTANCE(416)
        self.assertIn('random_int(*self.SWIPE_DISTANCE_RANGE)', src)
        self.assertNotIn('start_y - self.SWIPE_DISTANCE)', src)  # 固定 416 的 end 计算已移除


class PerformSearchSwipeK2Test(TestCase):
    """K2：`_perform_search_swipe` 的 minitouch 路径每次独立随机采样一个「较短」commanded 位移，
    取代固定 416px。`SWIPE_DISTANCE_RANGE` 是 provisional、Level C 分档调参——首档 `(212, 265)`
    实测「一次内容仍滚 >4 格」，2026-09-07 回调为 `(140, 180)`。只控制「滑多远」——起点安全区 /
    X / TouchSwipeModel / 曲率 / 时间模型 / tail / control_name 全不变；lazy 与非 minitouch 回退
    仍固定 SWIPE_DISTANCE=416。（swipe settle 从 K3 起是 FrameWait，本类把它 patch 成成功，只看距离采样。）"""

    _WAIT_OK = SimpleNamespace(success=True, changed=True, stable=True, timed_out=False,
                               frames_checked=3, elapsed=0.5, last_difference=0.4)

    def setUp(self):
        p = patch('tasks.KekkaiUtilize.script_task.logger')
        p.start()
        self.addCleanup(p.stop)
        w = patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable',
                  return_value=self._WAIT_OK)
        w.start()
        self.addCleanup(w.stop)

    def _task(self, control_method='minitouch'):
        t = KU.__new__(KU)
        t.config = SimpleNamespace(
            script=SimpleNamespace(device=SimpleNamespace(control_method=control_method)))
        t.device = SimpleNamespace(
            screenshot=Mock(name='screenshot', return_value='BASELINE'),
            swipe_trajectory=Mock(name='swipe_trajectory'),
            swipe_adb=Mock(name='swipe_adb'),
            swipe=Mock(name='Control.swipe'),
            click_record_clear=Mock(name='click_record_clear'),
        )
        return t

    def test_range_constant_is_level_c_recalibrated_short_step(self):
        # Level C 分档：首档 (212, 265) 实测滚 >4 格 → 2026-09-07 回调 (140, 180)
        lo, hi = KU.SWIPE_DISTANCE_RANGE
        self.assertEqual((lo, hi), (140, 180))
        self.assertLess(lo, hi)
        self.assertEqual(KU.KEKKAI_ROW_PITCH_PX, 106)
        # ≈1.3~1.7 个 row_pitch 的手指位移（受列表惯性放大，实际内容滚动预计更多）
        self.assertAlmostEqual(lo / KU.KEKKAI_ROW_PITCH_PX, 1.3, delta=0.1)
        self.assertAlmostEqual(hi / KU.KEKKAI_ROW_PITCH_PX, 1.7, delta=0.1)
        self.assertLess(hi, KU.SWIPE_DISTANCE)                  # 明显短于旧固定 416
        self.assertLess(hi, 212)                                # 比首档上界还小（本轮是缩短，不是放大）

    def _one_swipe(self, t, model, ints):
        """跑一次 _perform_search_swipe（minitouch），返回 generate 收到的 (start, end)。
        ints = [start_x, start_y, distance, lateral_offset]（4 个闭区间随机）。"""
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=list(ints)) as ri, \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            t._perform_search_swipe()
        (gen_start, gen_end), _ = model.generate.call_args
        return gen_start, gen_end, ri.call_args_list

    def test_each_call_independently_samples_distance(self):
        # §8.1~8.3：连续三次 swipe，distance 分别取范围下界 / 中值 / 上界 → end_y = start_y - 该值
        # （lateral_offset 固定 0，本用例只看纵向距离；斜度另有专门用例）
        t = self._task()
        model = Mock(); model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        seen_ends = []
        for dist in (140, 160, 180):
            model.generate.reset_mock()
            gs, ge, ri_calls = self._one_swipe(t, model, [450, 520, dist, 0])
            # 四次闭区间随机，顺序固定：start_x / start_y / distance(K2) / lateral(斜度)
            self.assertEqual(ri_calls, [call(340, 600), call(500, 565),
                                       call(140, 180), call(-12, 12)])
            self.assertEqual(gs, (450, 520))
            self.assertEqual(ge[1], 520 - dist)               # §8.8 end_y == start_y - distance
            self.assertEqual(ge[0], gs[0])                     # lateral=0 → end_x == start_x
            seen_ends.append(ge[1])
        self.assertEqual(seen_ends, [520 - 140, 520 - 160, 520 - 180])

    def test_distance_always_within_range_and_resampled(self):
        # §8.4：真随机源，大量调用，纵向位移恒在 [140, 180]；不再固定单值、不出现旧值
        t = self._task()
        model = Mock(); model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        dists = []
        for _ in range(400):
            model.generate.reset_mock()
            with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
                 patch('tasks.KekkaiUtilize.script_task.time.sleep'):
                t._perform_search_swipe()
            (gs, ge), _ = model.generate.call_args
            dists.append(gs[1] - ge[1])                        # 纵向 = start_y - end_y
        self.assertTrue(all(140 <= d <= 180 for d in dists), (min(dists), max(dists)))
        self.assertGreater(len(set(dists)), 10)                # 每次独立采样，不是启动时一次
        self.assertNotIn(416, dists)                           # 标准 minitouch 路径不再用 416
        self.assertTrue(all(d < 212 for d in dists))           # 已从首档 (212,265) 缩短

    def test_lateral_offset_makes_swipe_slightly_tilted_but_bounded(self):
        # 斜度：end_x = clamp(start_x + lateral_offset, SWIPE_START_X_RANGE)；只作用于最终 end_x
        t = self._task()
        model = Mock(); model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        lo_x, hi_x = KU.SWIPE_START_X_RANGE
        lat_lo, lat_hi = KU.SWIPE_LATERAL_OFFSET_RANGE
        self.assertEqual(KU.SWIPE_LATERAL_OFFSET_RANGE, (-12, 12))
        self.assertLess(lat_lo, 0); self.assertGreater(lat_hi, 0)   # 有正有负：能左斜也能右斜

        # 中段起点：偏移原样落到 end_x，纵向不受影响
        for lat in (-12, -5, 0, 5, 12):
            model.generate.reset_mock()
            gs, ge, _ = self._one_swipe(t, model, [470, 530, 160, lat])
            self.assertEqual(gs, (470, 530))
            self.assertEqual(ge, (470 + lat, 530 - 160))       # end_x = start_x + lateral；end_y 不受影响
            self.assertGreaterEqual(ge[0], lo_x)               # 始终在安全区内
            self.assertLessEqual(ge[0], hi_x)
        gs_l, ge_l, _ = self._one_swipe(t, model, [470, 530, 160, -12])
        gs_r, ge_r, _ = self._one_swipe(t, model, [470, 530, 160, 12])
        self.assertLess(ge_l[0], gs_l[0])                      # 轻微左斜
        self.assertGreater(ge_r[0], gs_r[0])                   # 轻微右斜

        # 起点贴左边界：负偏移被有界裁掉 → 退化竖直，绝不滑出安全区
        _, ge_edge, _ = self._one_swipe(t, model, [lo_x, 530, 160, -12])
        self.assertEqual(ge_edge[0], lo_x)
        # 起点贴右边界：正偏移被有界裁掉
        _, ge_edge2, _ = self._one_swipe(t, model, [hi_x, 530, 160, 12])
        self.assertEqual(ge_edge2[0], hi_x)

    def test_lateral_offset_real_random_bounded_and_two_sided(self):
        t = self._task()
        model = Mock(); model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        lo_x, hi_x = KU.SWIPE_START_X_RANGE
        offsets = []
        for _ in range(400):
            model.generate.reset_mock()
            with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
                 patch('tasks.KekkaiUtilize.script_task.time.sleep'):
                t._perform_search_swipe()
            (gs, ge), _ = model.generate.call_args
            self.assertGreaterEqual(ge[0], lo_x)               # end_x 始终合法
            self.assertLessEqual(ge[0], hi_x)
            offsets.append(ge[0] - gs[0])                      # 有界后的实际横向
        self.assertTrue(all(-12 <= o <= 12 for o in offsets), (min(offsets), max(offsets)))
        self.assertTrue(any(o < 0 for o in offsets))           # 出现过左斜
        self.assertTrue(any(o > 0 for o in offsets))           # 出现过右斜
        self.assertTrue(any(o == 0 for o in offsets))          # 也出现过接近竖直

    def test_start_ranges_unchanged(self):
        # §8.4：起点 X/Y 随机范围仍是旧安全区（斜度不扩大 start_x 范围）
        self.assertEqual(KU.SWIPE_START_X_RANGE, (340, 600))
        self.assertEqual(KU.SWIPE_START_Y_RANGE, (500, 565))

    def test_trajectory_and_control_name_unchanged(self):
        # §8.8~8.11：swipe_trajectory 恰一次 / 轨迹原样 / control_name / click_record_clear。
        # K3：settle 不再是 sleep(2)（见 PerformSearchSwipeK3Test），这里只锁「怎么滑」。
        t = self._task()
        model = Mock(); traj = [(1, 2, 0), (1, -160, 9)]
        model.generate = Mock(return_value=traj)
        events = []
        t.device.swipe_trajectory.side_effect = lambda *a, **k: events.append(('traj', a, k))
        t.device.click_record_clear.side_effect = lambda: events.append(('clear',))
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[400, 540, 160, 0]), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep',
                   side_effect=lambda s: events.append(('sleep', s))):
            t._perform_search_swipe()
        self.assertEqual(t.device.swipe_trajectory.call_count, 1)
        (traj_arg,), traj_kw = t.device.swipe_trajectory.call_args
        self.assertIs(traj_arg, traj)                          # §8.7 收到的是本次真实轨迹
        self.assertEqual(traj_kw.get('control_name'), 'KEKKAI_UTILIZE_SWIPE')
        self.assertEqual([e[0] for e in events], ['traj', 'clear'])   # K3：minitouch 路径无 sleep
        self.assertNotIn('sleep', [e[0] for e in events])

    def test_lazy_and_non_minitouch_fallback_keep_fixed_416(self):
        # §5：怠惰 / 非 minitouch 回退（perform_swipe_action → swipe_adb）仍固定 SWIPE_DISTANCE=416
        pa_src = inspect.getsource(KU.perform_swipe_action)
        self.assertIn('safe_pos_y - self.SWIPE_DISTANCE', pa_src)
        self.assertNotIn('SWIPE_DISTANCE_RANGE', pa_src)
        self.assertEqual(KU.SWIPE_DISTANCE, 416)
        # 非 minitouch 时 _perform_search_swipe 直接回退，不采样 distance
        t = self._task('adb')
        t.perform_swipe_action = Mock()
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel') as MODEL, \
             patch('tasks.KekkaiUtilize.script_task.random_int') as ri:
            t._perform_search_swipe()
        t.perform_swipe_action.assert_called_once_with()
        MODEL.assert_not_called()
        ri.assert_not_called()                                  # 回退路径不在 _perform_search_swipe 里采样

    def test_d017_and_touchswipe_untouched(self):
        # §9/§二：不动 D017（switch_friend_list 初始化）/ TouchSwipeModel（只给 start/end）
        self.assertEqual(KU.SEARCH_MAX_SWIPES, 20)
        self.assertEqual(KU.SEARCH_PASS_TIMEOUT, 120)
        rs_src = inspect.getsource(KU._run_search)
        self.assertIn('self.switch_friend_list(search_pass.friend_group)', rs_src)
        self.assertNotIn('S_U_END', rs_src)
        self.assertNotIn('self._reset_utilize_friend_list(', rs_src)
        sw_src = inspect.getsource(KU._perform_search_swipe)
        self.assertIn('TouchSwipeModel().generate(start, end)', sw_src)   # 构造零参 + 只给 start/end
        self.assertNotIn('TouchSwipeModel(', sw_src.replace('TouchSwipeModel()', ''))  # 不给 TouchSwipeModel 传参
        self.assertNotIn('TouchSwipeParams', sw_src)                       # 不碰模型参数（曲率 / 时间 / tail）
        # 斜度是 Kekkai 业务层在 end 元组里做的，不是给 TouchSwipeModel / MOVE 点加噪声
        self.assertIn('lateral_offset = random_int(*self.SWIPE_LATERAL_OFFSET_RANGE)', sw_src)
        self.assertIn('end = (end_x, start_y - distance)', sw_src)


# --------------------------------------------------------------------------------------
# K3：标准 PASS + minitouch 的 swipe settle 从固定 sleep(2) 改成 FrameWait changed+stable
# --------------------------------------------------------------------------------------

class PerformSearchSwipeK3Test(TestCase):
    """K3：`_perform_search_swipe` 的 minitouch 路径 swipe 后不再固定 `time.sleep(2)`，改成
    `wait_for_changed_and_stable(baseline, self.device.screenshot, ...)`：

    - `baseline` 是 swipe **前**明确重截的一帧；
    - 相对 baseline `changed` 且随后 `stable` → 返回 `True`（`_run_search_pass` 扫下一屏）；
    - `no change` / `changed 后一直不 stable` / `timeout` → 返回 `False` → `_run_search_pass`
      映射成 `PassResult.ABORT`（**不是** PASS_MISS，也不经 `I_U_EMPTY_CARD` 空卡 marker）；
    - 一次 swipe → 一次 FrameWait，方法内部不做重试（bounded recovery 在 `run_utilize` 外层）；
    - 阈值 / stable_frames / timeout 是 provisional 首版，注释标注需 Level C 调整；
    - 怠惰 / 非 minitouch 回退仍走 `perform_swipe_action`（固定 416 + `sleep(2)`），不接 FrameWait。
    """

    _OK = SimpleNamespace(success=True, changed=True, stable=True, timed_out=False,
                          frames_checked=4, elapsed=0.7, last_difference=0.35)
    _NOCHANGE = SimpleNamespace(success=False, changed=False, stable=False, timed_out=True,
                                frames_checked=30, elapsed=3.0, last_difference=0.01)
    _UNSTABLE = SimpleNamespace(success=False, changed=True, stable=False, timed_out=True,
                                frames_checked=30, elapsed=3.0, last_difference=0.22)

    def setUp(self):
        p = patch('tasks.KekkaiUtilize.script_task.logger')
        p.start()
        self.addCleanup(p.stop)

    def _task(self, control_method='minitouch'):
        t = KU.__new__(KU)
        t.config = SimpleNamespace(
            script=SimpleNamespace(device=SimpleNamespace(control_method=control_method)))
        self.events = []
        counter = {'n': 0}

        def _shot():
            counter['n'] += 1
            f = f'FRAME{counter["n"]}'
            self.events.append(('shot', f))
            return f
        t.device = SimpleNamespace(
            screenshot=Mock(side_effect=_shot),
            swipe_trajectory=Mock(side_effect=lambda *a, **k: self.events.append(('traj', a, k))),
            swipe_adb=Mock(name='swipe_adb'),
            swipe=Mock(name='Control.swipe'),
            click_record_clear=Mock(side_effect=lambda: self.events.append(('clear',))),
        )
        return t

    def _run(self, t, wait_result):
        """跑一次 minitouch _perform_search_swipe，FrameWait patch 成 `wait_result`。"""
        model = Mock()
        model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        captured = {}

        def _wfcs(baseline, provider, **kw):
            captured['baseline'] = baseline
            captured['provider'] = provider
            captured['kw'] = kw
            self.events.append(('wait',))
            return wait_result
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[400, 540, 160, 0]), \
             patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable',
                   side_effect=_wfcs) as WFCS:
            ret = t._perform_search_swipe()
        return ret, captured, WFCS

    # 1) changed && stable → True
    def test_returns_true_on_changed_and_stable(self):
        ret, _cap, WFCS = self._run(self._task(), self._OK)
        self.assertIs(ret, True)
        WFCS.assert_called_once()

    # 2) no change / timeout → False
    def test_returns_false_on_no_change_timeout(self):
        ret, _cap, _WFCS = self._run(self._task(), self._NOCHANGE)
        self.assertIs(ret, False)

    # 3) changed 但一直不 stable → False
    def test_returns_false_on_changed_but_unstable(self):
        ret, _cap, _WFCS = self._run(self._task(), self._UNSTABLE)
        self.assertIs(ret, False)

    # 4) baseline 来自 swipe 前，调用顺序 shot -> traj -> clear -> wait
    def test_baseline_captured_before_swipe_and_call_order(self):
        t = self._task()
        ret, cap, _WFCS = self._run(t, self._OK)
        self.assertIs(ret, True)
        self.assertEqual([e[0] for e in self.events][:4], ['shot', 'traj', 'clear', 'wait'])
        self.assertEqual(cap['baseline'], 'FRAME1')          # 就是 swipe 前那一帧
        # FrameWait 的取帧 provider 是 device.screenshot 本身（同一 callable）
        self.assertIs(cap['provider'], t.device.screenshot)

    # 5) FrameWait 收到我们的 ROI / provisional 阈值 / 有限 timeout / 显式 poll_interval
    def test_frame_wait_gets_our_roi_thresholds_and_finite_timeout(self):
        t = self._task()
        ret, cap, _WFCS = self._run(t, self._OK)
        kw = cap['kw']
        self.assertEqual(kw['roi'], KU.SWIPE_WAIT_ROI)
        self.assertEqual(kw['changed_threshold'], KU.SWIPE_WAIT_CHANGED_THRESHOLD)
        self.assertEqual(kw['stable_threshold'], KU.SWIPE_WAIT_STABLE_THRESHOLD)
        self.assertEqual(kw['stable_frames'], KU.SWIPE_WAIT_STABLE_FRAMES)
        self.assertEqual(kw['timeout'], KU.SWIPE_WAIT_TIMEOUT)
        self.assertGreater(kw['timeout'], 0)                 # 有限正数
        self.assertLessEqual(kw['timeout'], 5)               # 不夸张
        self.assertIs(cap['provider'], t.device.screenshot)

    # 5b) poll_interval 被**显式**传（不吃 FrameWait 全局默认 0.0）——检测采样 pacing
    def test_frame_wait_gets_explicit_positive_poll_interval(self):
        t = self._task()
        _ret, cap, _WFCS = self._run(t, self._OK)
        kw = cap['kw']
        self.assertIn('poll_interval', kw)                   # 显式传，不是默认
        self.assertEqual(kw['poll_interval'], KU.SWIPE_WAIT_POLL_INTERVAL)
        self.assertGreater(kw['poll_interval'], 0.0)         # 正的 pacing
        self.assertLess(kw['poll_interval'], 2.0)            # 远小于旧固定 sleep(2)，不是恢复固定等待
        # 只是 pacing——不动 4 个判定阈值
        self.assertEqual(kw['changed_threshold'], KU.SWIPE_WAIT_CHANGED_THRESHOLD)
        self.assertEqual(kw['stable_threshold'], KU.SWIPE_WAIT_STABLE_THRESHOLD)
        self.assertEqual(kw['stable_frames'], KU.SWIPE_WAIT_STABLE_FRAMES)
        self.assertEqual(kw['timeout'], KU.SWIPE_WAIT_TIMEOUT)

    # 6) 一次 swipe → 一次 FrameWait，方法内部不重试（即便失败）
    def test_single_swipe_single_frame_wait_no_internal_retry(self):
        t = self._task()
        _ret, _cap, WFCS = self._run(t, self._NOCHANGE)
        self.assertEqual(t.device.swipe_trajectory.call_count, 1)
        WFCS.assert_called_once()

    # 7) minitouch 分支源码不再有固定 sleep(2)，改用 FrameWait 并返回 wait.success
    def test_minitouch_branch_has_no_fixed_sleep2(self):
        src = inspect.getsource(KU._perform_search_swipe)
        self.assertNotIn('time.sleep(2)', src)
        self.assertNotIn('time.sleep(', src)                 # minitouch 分支完全不 sleep
        self.assertIn('wait_for_changed_and_stable(', src)
        self.assertIn('return wait.success', src)
        self.assertIn('baseline = self.device.screenshot()', src)   # swipe 前重截

    # 8) _run_search_pass 把 False 映射成 ABORT，不当作到底（不经空卡 marker 判定）
    def test_run_search_pass_maps_false_to_abort_not_bottom(self):
        src = inspect.getsource(KU._run_search_pass)
        self.assertIn('if not self._perform_search_swipe():', src)
        idx = src.index('if not self._perform_search_swipe():')
        tail = src[idx:idx + 300]
        self.assertIn('PassResult.ABORT, clicked_any', tail)   # False → ABORT
        self.assertNotIn('PassResult.PASS_MISS', tail)         # 不是「换下一 PASS」
        self.assertNotIn('PassResult.FINAL_USE_LAST', tail)    # 也不是「到底用最后候选」
        self.assertNotIn('self.appear(', tail)                 # 不经 I_U_EMPTY_CARD 空卡判定

    # 9) ROI 只盯好友结界卡列表滚动主体（card-column），不是整屏
    def test_roi_is_card_column_not_full_screen(self):
        x1, y1, x2, y2 = KU.SWIPE_WAIT_ROI
        self.assertTrue(0 <= x1 < x2 <= 1280)
        self.assertTrue(0 <= y1 < y2 <= 720)
        self.assertLess(x2 - x1, 1280 * 0.5)                 # 窄条，不是整屏宽
        self.assertGreater(x1, 400)                          # 右移到卡列，排除左侧
        self.assertLess(x2, 720)                             # 不含右侧详情栏 / 数字

    # 10) provisional 参数在类里，注释标注需 Level C 调整
    def test_provisional_params_flagged_level_c(self):
        src = inspect.getsource(KU)
        self.assertIn('Level C', src)
        for name in ('SWIPE_WAIT_ROI', 'SWIPE_WAIT_CHANGED_THRESHOLD',
                     'SWIPE_WAIT_STABLE_THRESHOLD', 'SWIPE_WAIT_STABLE_FRAMES',
                     'SWIPE_WAIT_TIMEOUT', 'SWIPE_WAIT_POLL_INTERVAL'):
            self.assertTrue(hasattr(KU, name), name)
        # poll_interval 的注释明确它是「检测采样 pacing」
        self.assertIn('pacing', src)

    # 11) 怠惰 / 非 minitouch 回退不变：仍 perform_swipe_action（固定 416 + sleep(2)），不接 FrameWait
    def test_lazy_and_non_minitouch_fallback_unchanged(self):
        pa_src = inspect.getsource(KU.perform_swipe_action)
        self.assertIn('time.sleep(2)', pa_src)
        self.assertNotIn('wait_for_changed_and_stable', pa_src)
        self.assertIn('safe_pos_y - self.SWIPE_DISTANCE', pa_src)   # K2/K3 都不碰回退距离
        t = self._task('adb')
        t.perform_swipe_action = Mock()
        with patch('tasks.KekkaiUtilize.script_task.wait_for_changed_and_stable') as WFCS:
            ret = t._perform_search_swipe()
        self.assertIs(ret, True)                             # 回退路径固定视为「已滑动」
        t.perform_swipe_action.assert_called_once_with()
        WFCS.assert_not_called()                             # 回退不接 FrameWait
        t.device.screenshot.assert_not_called()             # 回退不截 baseline

    # 12) 真实 FrameWait 签名冒烟（不重造 FrameWait 的轮子，只证明调用签名对得上）
    def test_real_frame_wait_signature_smoke(self):
        import numpy as np
        base = np.zeros((720, 1280, 3), dtype=np.uint8)
        moved = base.copy()
        moved[160:600, 530:615] = 255                        # SWIPE_WAIT_ROI 内大变化
        t = self._task()
        t.device.screenshot = Mock(side_effect=iter([base] + [moved] * 40))
        model = Mock()
        model.generate = Mock(return_value=[(0, 0, 0), (0, -1, 9)])
        with patch('tasks.KekkaiUtilize.script_task.TouchSwipeModel', return_value=model), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[400, 540, 160, 0]), \
             patch.object(KU, 'SWIPE_WAIT_POLL_INTERVAL', 0.0):   # 冒烟不测 pacing 计时，避免真 sleep
            ret = t._perform_search_swipe()
        self.assertIs(ret, True)                             # changed(baseline→moved) + stable(moved×N)

    # K1 未受影响：TouchSwipeModel / swipe_trajectory 契约不变；K2：仍走随机范围常量（值可 Level C 调档）
    def test_k1_k2_untouched_by_k3(self):
        src = inspect.getsource(KU._perform_search_swipe)
        self.assertIn('TouchSwipeModel().generate(start, end)', src)
        self.assertIn("self.device.swipe_trajectory(trajectory, control_name='KEKKAI_UTILIZE_SWIPE')", src)
        self.assertIn('random_int(*self.SWIPE_DISTANCE_RANGE)', src)
        self.assertEqual(KU.SWIPE_DISTANCE_RANGE, (140, 180))   # Level C 分档：首档 (212,265) → 已回调


# --------------------------------------------------------------------------------------
# Scheduler v1 —— 静默窗口 + 短期 retry cooldown（Level B：`ScriptTask` 出口接入）
#
# 契约：
#   正常寄养：OCR 剩余时间 → min_run_interval 地板 → _normalize_quiet_target → set_next_run
#   短期 retry（5 次未达标 / 3 次失败 / 无达标卡）：_build_retry_target（随机 cooldown）
#       → _schedule_target（同一次 normalize）→ set_next_run，全部经 _schedule_retry 统一出口
#   run() 入口：_guard_quiet_window 在任何页面 / OCR / 业务动作之前拦截
#
# 纯 `datetime`/`time` 算法本身的边界（CASE A~H）在 `tests/test_kekkai_utilize_scheduling.py`
# 已覆盖，这里只测 `ScriptTask` 这一层「怎么从 config 取参数、怎么调用统一随机源、怎么接线到
# 5 个业务出口」，不重复造同义测试。
# --------------------------------------------------------------------------------------

def _sched_cfg(*, quiet_enable=True, quiet_start=dtime(0, 0, 0), quiet_end=dtime(7, 0, 0),
              jitter_min=5, jitter_max=30, cooldown_min=5, cooldown_max=30,
              min_run_interval=timedelta(0), utilize_enable=True, lazy_mode=False,
              utilize_rule=None, **utilize_kwargs):
    """构造 `self.config.kekkai_utilize`：`scheduler` 只放 Scheduler v1 需要的字段；
    `utilize_config` 带一份跑得通 `run()` 全链路（`utilize_enable=False` 分支）的最小默认值，
    被测用例按需通过 `utilize_kwargs` 覆盖（`SimpleNamespace`，不构造真实 pydantic 对象）。"""
    uc_defaults = dict(
        utilize_rule=utilize_rule,
        min_run_interval=min_run_interval,
        utilize_enable=utilize_enable,
        lazy_mode=lazy_mode,
        shikigami_class=None,
        auto_fill=False,
        auto_replace_max_level=False,
        utilize_harvest=False,
        box_ap_enable=False,
        box_exp_enable=False,
        box_exp_waste=False,
        harvest_guild_max_times=0,
    )
    uc_defaults.update(utilize_kwargs)
    return SimpleNamespace(
        kekkai_utilize=SimpleNamespace(
            scheduler=SimpleNamespace(
                quiet_window_enable=quiet_enable,
                quiet_start=quiet_start,
                quiet_end=quiet_end,
                quiet_resume_jitter_min=jitter_min,
                quiet_resume_jitter_max=jitter_max,
                cooldown_min=cooldown_min,
                cooldown_max=cooldown_max,
            ),
            utilize_config=SimpleNamespace(**uc_defaults),
        )
    )


def _patch_now(dt: datetime):
    """把 `tasks.KekkaiUtilize.script_task.datetime` 换成 `.now()` 恒返回 `dt` 的替身。

    被测路径只调用 `datetime.now()`（不调用 `datetime(...)` 构造 / `isinstance` 判断），
    因此只需覆盖 `.now`，返回值本身仍是真实 `datetime` 实例，算术运算不受影响。
    """
    mock_dt = Mock(name='datetime')
    mock_dt.now = Mock(return_value=dt)
    return patch('tasks.KekkaiUtilize.script_task.datetime', mock_dt)


class SchedulingHelperUnitTest(TestCase):
    """task-local helper 本身：怎么从 config 取参数、怎么调用统一随机源。"""

    def _task(self, **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(**cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        return t

    def test_is_in_quiet_window_reads_config_bounds(self):
        t = self._task(quiet_start=dtime(0, 0, 0), quiet_end=dtime(7, 0, 0))
        self.assertTrue(t._is_in_quiet_window(now=datetime(2026, 9, 1, 3, 0)))
        self.assertFalse(t._is_in_quiet_window(now=datetime(2026, 9, 1, 14, 20)))

    def test_is_in_quiet_window_false_when_disabled(self):
        t = self._task(quiet_enable=False)
        self.assertFalse(t._is_in_quiet_window(now=datetime(2026, 9, 1, 3, 0)))

    def test_quiet_jitter_seconds_uses_canonical_random_source(self):
        t = self._task(jitter_min=5, jitter_max=30)
        with patch('tasks.KekkaiUtilize.script_task.random_int', return_value=777) as ri:
            seconds = t._quiet_jitter_seconds()
        ri.assert_called_once_with(300, 1800)   # 5*60, 30*60
        self.assertEqual(seconds, 777)

    def test_build_retry_target_uses_canonical_random_source(self):
        t = self._task(cooldown_min=5, cooldown_max=30)
        now = datetime(2026, 9, 1, 14, 0)
        with patch('tasks.KekkaiUtilize.script_task.random_int', return_value=1200) as ri:  # 20min
            target = t._build_retry_target(now=now)
        ri.assert_called_once_with(300, 1800)
        self.assertEqual(target, datetime(2026, 9, 1, 14, 20))

    def test_normalize_quiet_target_outside_window_no_random_call(self):
        t = self._task()
        candidate = datetime(2026, 9, 1, 14, 20)
        with patch('tasks.KekkaiUtilize.script_task.random_int') as ri:
            final = t._normalize_quiet_target(candidate)
        ri.assert_not_called()
        self.assertEqual(final, candidate)

    def test_normalize_quiet_target_inside_window_resumes_with_jitter(self):
        t = self._task(jitter_min=10, jitter_max=10)
        candidate = datetime(2026, 9, 1, 0, 15)
        with patch('tasks.KekkaiUtilize.script_task.random_int', return_value=600):  # 10min
            final = t._normalize_quiet_target(candidate)
        self.assertEqual(final, datetime(2026, 9, 1, 7, 10))

    def test_schedule_target_calls_set_next_run_with_server_false(self):
        t = self._task()
        candidate = datetime(2026, 9, 1, 14, 20)
        final = t._schedule_target(candidate)
        t.set_next_run.assert_called_once_with(task='KekkaiUtilize', target=final, server=False)
        self.assertEqual(final, candidate)


class NoEligibleCardRetryExitTest(TestCase):
    """CASE 1/2（Level B 任务列表）：`_finish_low_value_utilize`——「无达标卡」出口。"""

    def _task(self, **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(**cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        t.push_notify = Mock(name='push_notify')
        return t

    def test_case1_no_quiet_overlap_14_00_plus_cooldown_20min(self):
        t = self._task()
        with _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=1200):  # cooldown 20min
            ret = t._finish_low_value_utilize()
        self.assertIs(ret, False)
        self.assertTrue(t.utilize_terminal_failure)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 14, 20), server=False)

    def test_case2_cooldown_candidate_falls_in_quiet_window(self):
        t = self._task(jitter_min=10, jitter_max=10)
        # 23:55 完成，cooldown 抽到 20min → candidate 次日 00:15（落窗）→ + 10min jitter → 次日 07:10
        with _patch_now(datetime(2026, 9, 1, 23, 55)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[1200, 600]) as ri:
            t._finish_low_value_utilize()
        self.assertEqual(ri.call_args_list, [call(300, 1800), call(600, 600)])
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 2, 7, 10), server=False)

    def test_log_message_states_card_type_and_threshold_not_vague_no_card(self):
        # §8 要求：明确「目标卡种 + 收益阈值」，不写模糊的「没有卡」
        t = self._task()
        with _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t._finish_low_value_utilize()
        message = t.push_notify.call_args.kwargs['content']
        self.assertIn('目标卡种', message)
        self.assertIn('收益阈值', message)
        self.assertNotIn('没有卡', message)


class NormalUtilizeSchedulingTest(TestCase):
    """CASE 3/4/5（Level B 任务列表）：`check_utilize_add` 的「已经在寄养」OCR 出口——
    正常寄养调度契约不被 cooldown 取代。"""

    def _task(self, remaining, *, min_run_interval=timedelta(0), **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(min_run_interval=min_run_interval, **cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        t.push_notify = Mock(name='push_notify')
        t.goto_page = Mock(name='goto_page', return_value=True)
        t.screenshot = Mock(name='screenshot')
        t.appear = Mock(name='appear', return_value=False)   # I_UTILIZE_ADD 不在 = 已经在寄养
        t.device = SimpleNamespace(image='FRAME')
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=Mock(return_value=remaining))
        t.utilize_add_count = 0
        t.utilize_found_eligible_card = False
        return t

    def test_case3_ocr_remaining_falls_in_quiet_window(self):
        t = self._task(timedelta(hours=3))
        with _patch_now(datetime(2026, 9, 1, 22, 30)), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=0) as ri:
            ret = t.check_utilize_add()
        self.assertIs(ret, True)
        # candidate = 22:30 + 3h = 次日 01:30，落窗（00:00~07:00）→ 次日 07:00 + jitter(0)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 2, 7, 0), server=False)
        ri.assert_called_once_with(300, 1800)   # 只为窗内归一化采样一次抖动，不叠加 cooldown

    def test_case4_ocr_remaining_outside_quiet_window_no_cooldown_applied(self):
        t = self._task(timedelta(hours=3))
        with _patch_now(datetime(2026, 9, 1, 10, 0)), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             patch('tasks.KekkaiUtilize.script_task.random_int') as ri:
            ret = t.check_utilize_add()
        self.assertIs(ret, True)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 13, 0), server=False)
        ri.assert_not_called()   # 不落窗，不产生任何随机数——绝不套 cooldown

    def test_case5_min_run_interval_floor_applied_before_quiet_normalize(self):
        # OCR 剩余 6 分钟 < 30 分钟地板 → 先取 floor(10:30) → 不落窗 → 原样作为 final
        t = self._task(timedelta(minutes=6), min_run_interval=timedelta(minutes=30))
        with _patch_now(datetime(2026, 9, 1, 10, 0)), \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             patch('tasks.KekkaiUtilize.script_task.random_int') as ri:
            t.check_utilize_add()
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 10, 30), server=False)
        ri.assert_not_called()


class RunEntryQuietGuardTest(TestCase):
    """CASE 6/7（Level B 任务列表）：`run()` 入口守卫——静默窗口内立即重排 + TaskEnd，
    不进入任何页面 / OCR / 业务方法；关闭时不拦截，正常进入业务链。"""

    def _task(self, **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(**cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        t.goto_page = Mock(name='goto_page', return_value=True)
        t.check_utilize_add = Mock(name='check_utilize_add')
        t.check_max_lv = Mock(name='check_max_lv')
        t.check_utilize_harvest = Mock(name='check_utilize_harvest')
        t.check_box_ap_or_exp = Mock(name='check_box_ap_or_exp')
        t.receive_guild_assets = Mock(name='receive_guild_assets')
        t.screenshot = Mock(name='screenshot')
        t.appear = Mock(name='appear')
        return t

    def test_case6_quiet_window_blocks_before_any_business_action(self):
        t = self._task(jitter_min=15, jitter_max=15)
        with _patch_now(datetime(2026, 9, 1, 6, 30)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=900):  # 15min
            with self.assertRaises(TaskEnd):
                t.run()
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 7, 15), server=False)
        # 不进任何页面 / OCR / 业务方法
        t.goto_page.assert_not_called()
        t.check_utilize_add.assert_not_called()
        t.check_max_lv.assert_not_called()
        t.check_utilize_harvest.assert_not_called()
        t.check_box_ap_or_exp.assert_not_called()
        t.receive_guild_assets.assert_not_called()
        t.screenshot.assert_not_called()
        t.appear.assert_not_called()

    def test_case7_quiet_disabled_does_not_block(self):
        t = self._task(quiet_enable=False, utilize_enable=False, lazy_mode=False)
        # utilize_enable=False 让 run() 走最短业务路径，不需要搭建 check_utilize_add 全链路
        t.check_utilize_add.side_effect = AssertionError('utilize_enable=False 不应调用')
        with _patch_now(datetime(2026, 9, 1, 6, 30)):
            with self.assertRaises(TaskEnd):
                t.run()
        # guard 未拦截：真正进入了业务链（goto_page 被调用），且用的是原有 success_interval 出口
        t.goto_page.assert_called()
        t.set_next_run.assert_called_once_with(task='KekkaiUtilize', finish=True, success=True)


class RetrySingleOwnerTest(TestCase):
    """短期失败出口全部使用同一个 cooldown helper（§9/CASE 8）：一个 owner、一个范围、
    一次随机——不允许某分支各自独立调用 `random_int`。"""

    def _task(self, **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(**cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        t.push_notify = Mock(name='push_notify')
        return t

    def test_five_attempt_cap_uses_schedule_retry(self):
        t = self._task()
        t.utilize_add_count = 5
        t.utilize_found_eligible_card = False
        t.config.kekkai_utilize.utilize_config.utilize_rule = None
        with patch.object(t, '_schedule_retry', wraps=t._schedule_retry) as sr, \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            ret = t.check_utilize_add()
        self.assertIs(ret, True)
        sr.assert_called_once()

    def test_three_strikes_failure_uses_schedule_retry(self):
        t = self._task()
        t.utilize_failed_count = 2
        with patch.object(t, '_schedule_retry', wraps=t._schedule_retry) as sr, \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t._record_utilize_failure('测试原因')
        sr.assert_called_once()
        self.assertTrue(t.utilize_terminal_failure)

    def test_no_eligible_card_uses_schedule_retry(self):
        t = self._task()
        t.config.kekkai_utilize.utilize_config.utilize_rule = None
        with patch.object(t, '_schedule_retry', wraps=t._schedule_retry) as sr, \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t._finish_low_value_utilize()
        sr.assert_called_once()

    def test_all_three_short_retry_exits_share_the_same_helper_source(self):
        # 源码级锁定：三个短期失败出口都调用 `self._schedule_retry(`，不各自另起 random_int。
        for func in (KU.check_utilize_add, KU._record_utilize_failure, KU._finish_low_value_utilize):
            src = inspect.getsource(func)
            self.assertIn('self._schedule_retry(', src, func.__name__)
            self.assertNotIn('random_int(', src, func.__name__)


# --------------------------------------------------------------------------------------
# 业务开关：满级检查/替换（新增 `auto_replace_max_level`）+ 寄养奖励领取（沿用既有
# `utilize_harvest`，不新增重复字段）——旧能力（`check_max_lv` / `check_utilize_harvest`）
# 逐字保留，只用开关控制是否执行；与 Scheduler v1 解耦（`_guard_quiet_window` 直接 mock 掉，
# 本轮不测静默窗口 / cooldown，只测这两个业务开关本身的接线）。
# --------------------------------------------------------------------------------------

class MaxLevelAndHarvestSwitchTest(TestCase):
    def _task(self, **cfg_kwargs):
        t = KU.__new__(KU)
        t.config = _sched_cfg(quiet_enable=False, utilize_enable=False, **cfg_kwargs)
        t._guard_quiet_window = Mock(name='_guard_quiet_window', return_value=False)
        t.set_next_run = Mock(name='set_next_run')
        t.goto_page = Mock(name='goto_page', return_value=True)
        t.check_max_lv = Mock(name='check_max_lv')
        t.check_utilize_harvest = Mock(name='check_utilize_harvest')
        t.check_box_ap_or_exp = Mock(name='check_box_ap_or_exp')
        t.receive_guild_assets = Mock(name='receive_guild_assets')
        return t

    def test_case1_auto_replace_max_level_false_skips_check_max_lv(self):
        t = self._task(auto_replace_max_level=False)
        with self.assertRaises(TaskEnd):
            t.run()
        t.check_max_lv.assert_not_called()

    def test_case2_auto_replace_max_level_true_calls_check_max_lv_with_original_args(self):
        t = self._task(auto_replace_max_level=True, shikigami_class='N', auto_fill=True)
        with self.assertRaises(TaskEnd):
            t.run()
        t.check_max_lv.assert_called_once_with('N', True)

    def test_case3_utilize_harvest_false_skips_check_utilize_harvest(self):
        t = self._task(utilize_harvest=False)
        with self.assertRaises(TaskEnd):
            t.run()
        t.check_utilize_harvest.assert_not_called()

    def test_case4_utilize_harvest_true_calls_check_utilize_harvest(self):
        t = self._task(utilize_harvest=True)
        with self.assertRaises(TaskEnd):
            t.run()
        t.check_utilize_harvest.assert_called_once()

    def test_case5_new_field_defaults_to_false(self):
        from tasks.KekkaiUtilize.config import UtilizeConfig
        self.assertIs(UtilizeConfig().auto_replace_max_level, False)
        # 既有字段默认值不变（不擅自改动既有配置行为）
        self.assertIs(UtilizeConfig().utilize_harvest, True)

    def test_case6_full_config_model_instantiates_and_dumps_schema(self):
        from tasks.KekkaiUtilize.config import KekkaiUtilize
        k = KekkaiUtilize()
        dumped = k.model_dump()
        self.assertIn('auto_replace_max_level', dumped['utilize_config'])
        self.assertIn('utilize_harvest', dumped['utilize_config'])
        schema = KekkaiUtilize.model_json_schema()
        self.assertTrue(schema)
        # 前端渲染依据：JSON Schema 里 bool 字段必须是 'boolean'（Checkbox 分支的判据）
        uc_defs = schema['$defs']['UtilizeConfig']['properties']
        self.assertEqual(uc_defs['auto_replace_max_level']['type'], 'boolean')
        self.assertEqual(uc_defs['utilize_harvest']['type'], 'boolean')

    def test_switch_source_shape(self):
        src = inspect.getsource(KU.run)
        self.assertIn('if con.auto_replace_max_level:', src)
        self.assertIn('self.check_max_lv(con.shikigami_class, con.auto_fill)', src)
        self.assertIn('if con.utilize_harvest:', src)
        self.assertIn('self.check_utilize_harvest()', src)

    def test_old_capabilities_not_removed(self):
        # 旧能力（check_max_lv 及其内部依赖）逐字保留，只是调用点加了开关
        for name in ('check_max_lv', 'unset_shikigami_max_lv', 'switch_shikigami_class', 'set_shikigami'):
            self.assertTrue(hasattr(KU, name), name)


# --------------------------------------------------------------------------------------
# U3（2026-09-14）：进入好友结界寄养页导航失败必须阻断寄养业务
#
# 背景：`check_utilize_add()` 里 `if not self.goto_page(page_guild_realm_utilize): logger.info(...)`
# 只记录日志、没有 return/continue，导致导航失败后仍会落入 `run_utilize(...)`，在错误页面
# 继续 OCR / swipe / click。修复后：`goto_page` 失败（无论是显式假值返回，还是抛出
# `GamePageUnknownError`/`GameStuckError`）统一收敛成本地判定，失败就复用既有终态失败出口
# （`_schedule_retry` + `utilize_terminal_failure=True` + `return False`），不新增第二套
# 重试机制，也不接触 `utilize_add_count`/`utilize_failed_count` 这两个既有计数器。
# --------------------------------------------------------------------------------------

from module.exception import GamePageUnknownError, GameStuckError
from tasks.KekkaiUtilize.page import page_guild_realm_utilize, page_guild_realm_growth


def _goto_page_map(failures: dict = None):
    """按目标页返回不同结果的 `goto_page` 替身：默认所有页面导航成功，`failures` 里列出的
    页面返回 `False`（或指定的异常类），其余页面一律成功——用于精确模拟「只有寄养页导航
    失败，其它页面导航不受影响」。"""
    failures = failures or {}

    def _side_effect(page, *a, **kw):
        outcome = failures.get(page)
        if outcome is None:
            return True
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome('模拟导航失败')
        return outcome
    return Mock(name='goto_page', side_effect=_side_effect)


class UtilizeNavigationFailureGuardTest(TestCase):
    """U3 CASE 1~10：导航到 `page_guild_realm_utilize` 失败必须阻断本轮全部寄养业务。"""

    def _task(self, *, goto_page_failures: dict = None, **cfg_kwargs):
        t = KU.__new__(KU)
        # select_friend_list/shikigami_order：导航成功时 run_utilize(...) 的真实调用参数会读取
        # 这两个字段，导航失败的用例走不到那一行，给个占位默认值即可。
        cfg_kwargs.setdefault('select_friend_list', SelectFriendList.SAME_SERVER)
        cfg_kwargs.setdefault('shikigami_order', 7)
        t.config = _sched_cfg(**cfg_kwargs)
        t.set_next_run = Mock(name='set_next_run')
        t.push_notify = Mock(name='push_notify')
        t.screenshot = Mock(name='screenshot')
        t.device = SimpleNamespace(image='FRAME')
        t.O_UTILIZE_RES_TIME = SimpleNamespace(ocr=Mock(return_value=timedelta(hours=1)))
        t.utilize_add_count = 0
        t.utilize_found_eligible_card = False
        t.utilize_terminal_failure = False
        t.utilize_failed_count = 0
        # I_UTILIZE_ADD：第 1 次调用 True（还没蹭上，需要新增）→ 第 2 次调用 False（已经
        # 蹭上，走「已在寄养」OCR 出口）——让循环在「1 次寄养尝试」后自然、真实地结束，
        # 不用伪造 terminal_failure 当测试开关。
        t.appear = Mock(name='appear', side_effect=[True, False])
        t.goto_page = _goto_page_map(goto_page_failures)
        t.run_utilize = Mock(name='run_utilize')
        return t

    # ---------------- CASE 1：导航成功 ----------------

    def test_case1_navigation_success_calls_run_utilize_once(self):
        t = self._task()
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            ret = t.check_utilize_add()
        t.run_utilize.assert_called_once()
        self.assertIs(ret, True)   # 走到「已在寄养」OCR 出口，既有成功语义不变

    # ---------------- CASE 2：导航失败 → run_utilize 0 次 ----------------

    def test_case2_navigation_failure_blocks_run_utilize(self):
        t = self._task(goto_page_failures={page_guild_realm_utilize: False})
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            ret = t.check_utilize_add()
        t.run_utilize.assert_not_called()
        self.assertIs(ret, False)
        self.assertTrue(t.utilize_terminal_failure)

    def test_case2b_navigation_exception_also_blocks_run_utilize(self):
        # goto_page 的真实契约是「成功 True / 失败抛 GamePageUnknownError」，不是返回
        # False——本地 guard 必须同时接住异常这条真实路径,不能只处理理论上的假值返回。
        for exc in (GamePageUnknownError, GameStuckError):
            with self.subTest(exc=exc.__name__):
                t = self._task(goto_page_failures={page_guild_realm_utilize: exc})
                with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
                     _patch_now(datetime(2026, 9, 1, 14, 0)), \
                     patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
                    ret = t.check_utilize_add()
                t.run_utilize.assert_not_called()
                self.assertIs(ret, False)

    # ---------------- CASE 3/4/5：导航失败后无业务 OCR / swipe / click 穿透 ----------------

    def test_case345_navigation_failure_real_run_utilize_never_enters_business_dispatch(self):
        # 不满足于「run_utilize 这个黑盒 mock 没被调用」——把 run_utilize 换回真实实现，
        # 只 mock 它内部两个仅有的业务分发口（_run_search / _run_lazy_utilize，好友 OCR /
        # 结界卡 OCR / 收益 OCR / 列表 swipe / 结界卡点击全部在这两者之下），证明真实
        # run_utilize 方法体本身从未被进入，而不是只验证外层一层 mock。
        t = self._task(goto_page_failures={page_guild_realm_utilize: False})
        del t.run_utilize   # 恢复类上的真实 run_utilize，不用本 _task() 的黑盒 mock
        t.utilize_lazy_mode_active = False
        t._run_search = Mock(name='_run_search')
        t._run_lazy_utilize = Mock(name='_run_lazy_utilize')
        t.switch_shikigami_class = Mock(name='switch_shikigami_class')
        t.set_shikigami = Mock(name='set_shikigami')
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t.check_utilize_add()
        # 好友 OCR / 结界卡 OCR / 收益 OCR / 列表 swipe（CASE3/4 全部在 _run_search /
        # _run_lazy_utilize 之下）
        t._run_search.assert_not_called()
        t._run_lazy_utilize.assert_not_called()
        # 结界卡点击 / 寄养点击（CASE5，均在 run_utilize 选中候选之后才会执行）
        t.switch_shikigami_class.assert_not_called()
        t.set_shikigami.assert_not_called()

    # ---------------- CASE 6/7：导航失败复用既有 retry/scheduler pipeline ----------------

    def test_case6_navigation_failure_uses_existing_schedule_retry_helper(self):
        t = self._task(goto_page_failures={page_guild_realm_utilize: False})
        with patch.object(t, '_schedule_retry', wraps=t._schedule_retry) as sr, \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300) as ri:  # cooldown 5min
            t.check_utilize_add()
        sr.assert_called_once()
        # 候选时间落在既有 5~30min cooldown 范围内采样，不是固定 5/10/20 分钟
        ri.assert_called_once_with(300, 1800)
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 1, 14, 5), server=False)

    def test_case7_navigation_failure_retry_still_normalized_into_quiet_window(self):
        t = self._task(goto_page_failures={page_guild_realm_utilize: False}, jitter_min=10, jitter_max=10)
        # 23:55 失败，cooldown 抽到 20min → candidate 次日 00:15（落窗 00:00~07:00）
        # → + 10min jitter → 次日 07:10，证明 U3 没有绕过 Scheduler v1。
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 23, 55)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', side_effect=[1200, 600]) as ri:
            t.check_utilize_add()
        self.assertEqual(ri.call_args_list, [call(300, 1800), call(600, 600)])
        t.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', target=datetime(2026, 9, 2, 7, 10), server=False)

    # ---------------- CASE 8：失败只计一次 ----------------

    def test_case8_failure_recorded_exactly_once_not_double_counted(self):
        t = self._task(goto_page_failures={page_guild_realm_utilize: False})
        with patch.object(t, '_schedule_retry', wraps=t._schedule_retry) as sr, \
             patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t.check_utilize_add()
        sr.assert_called_once()   # 不会被主循环 + 某个内层分支各自触发一次、变成两次
        # 导航失败是独立的终态失败出口，不经过、也不重复消耗既有的两个业务计数器
        self.assertEqual(t.utilize_failed_count, 0)
        self.assertEqual(t.utilize_add_count, 1)

    # ---------------- CASE 9：本轮结束，不继续向下执行 ----------------

    def test_case9_navigation_failure_stops_current_iteration_immediately(self):
        t = self._task(goto_page_failures={page_guild_realm_utilize: False})
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'), \
             _patch_now(datetime(2026, 9, 1, 14, 0)), \
             patch('tasks.KekkaiUtilize.script_task.random_int', return_value=300):
            t.check_utilize_add()
        # goto_page(page_guild_realm_growth) 只应该发生「进入本次循环」那一次（导航失败分支
        # 之前），不应该再发生循环底部那一次「回育成界面继续下一轮」的调用。
        growth_calls = [c for c in t.goto_page.call_args_list if c.args and c.args[0] is page_guild_realm_growth]
        self.assertEqual(len(growth_calls), 1)
        t.run_utilize.assert_not_called()

    # ---------------- CASE 10：成功路径完全不变 ----------------

    def test_case10_success_path_source_unchanged_after_gate(self):
        # 导航成功分支的既有语句原样保留在新 guard 之后，不是被本轮重写。
        src = inspect.getsource(KU.check_utilize_add)
        self.assertIn(
            'self.run_utilize(con.select_friend_list, con.shikigami_class, con.shikigami_order)', src)
        self.assertIn('if self.utilize_terminal_failure:', src)
        self.assertIn('self.goto_page(page_guild_realm_growth)', src)
        # 新 guard 复用既有终态失败出口，没有另起一套判定/调度
        self.assertIn('self._schedule_retry(', src)
        self.assertIn('self.utilize_terminal_failure = True', src)

    def test_case10b_success_then_terminal_failure_from_run_utilize_still_returns_false(self):
        # 导航成功后，run_utilize 内部产生的 terminal failure（既有语义）不受本轮影响。
        t = self._task()

        def _set_terminal(*a, **kw):
            t.utilize_terminal_failure = True
        t.run_utilize.side_effect = _set_terminal
        with patch('tasks.KekkaiUtilize.script_task.time.sleep'):
            ret = t.check_utilize_add()
        t.run_utilize.assert_called_once()
        self.assertIs(ret, False)


if __name__ == '__main__':
    import unittest
    unittest.main()
