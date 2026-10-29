# This Python file uses the following encoding: utf-8
"""预设切换确认之后出现「契灵已装配于其他阴阳师，是否替换？」确认框：有界观察、点确定、确认关闭后再继续。

用户选了这个预设就等于允许替换，不加配置。检测只在预设切换上下文内、且只在「预设确认框出现过并已确认」之后做；
没出现就正常继续；点了关不掉（持续存在）在有界超时后抛 `GamePageUnknownError` 交还原有异常处理，不无限点击，
也不记「切换成功」。数字 / 按名称两条路径共用 `_confirm_bondling_replace_dialog`。

沿用 `tests/test_switch_soul_numeric_v1.py` 的 Sandbox：真实 `SwitchSoul` 方法 + 真实 `BaseTask.appear_then_click`，
只替换截图 / 识别 / 设备 / 滑动，虚拟时钟确定。`frames[n]` = 第 n 次截图之后可见目标的 roi 映射。
识别资源复用 `I_SOU_SWITCH_SURE`（「确定」按钮，与预设确认框同一位置）；离线只能验证流程，真机要确认弹窗确实能被它识别。
"""

from types import SimpleNamespace
from unittest.mock import Mock

from module import reaction_profile as rp
from module.exception import GamePageUnknownError
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tests.test_switch_soul_numeric_v1 import SHOT, SURE_ROI, SWIPE_PHASE, TEAM_ROI, Sandbox, ss


class ReplaceDialogSandbox(Sandbox):
    # 数字模式：队伍识别 + fresh 确认（idx 3、4）→ 预设确认框（5、6）→ 确认框消失（7）；之后 idx 8 起由用例决定
    NUMERIC_BASE = SWIPE_PHASE + [{'SW_TEAM': TEAM_ROI}, {'SW_TEAM': TEAM_ROI}, {'SW_SURE': SURE_ROI},
                                  {'SW_SURE': SURE_ROI}, {}]
    # 按名称模式：8 个前置截图（分组回顶 / 找分组 / 点分组 / 队伍回顶 / 找队伍 / 点击前定位）→ idx 8 起是切换循环。
    # 搜索阶段本身由 `tests/test_switch_soul_name_search.py` 用真实 OCR / 滑动 / 稳定等待覆盖；这里只替身它们，
    # 并让每个阶段占用固定数量的截图，使下面所有用例关心的「确认循环」帧序号保持不变。
    NAME_PREFIX = [{} for _ in range(8)]
    SURE_FRAME = {'SW_SURE': SURE_ROI}

    def sure_clicks(self):
        return self.clicks(self.sure.name)

    def switched_logged(self):
        return any('Switch soul_one group' in str(c.args[0]) for c in self.logger.info.call_args_list if c.args)

    def run_numeric(self, tail):
        task = self.make(self.NUMERIC_BASE + tail)
        return task, lambda: task.switch_soul_one(2, 2)

    def make_by_name(self, tail, confirm_at_9=True, loop=None, team_ok=True):
        """按名称模式：切换循环 idx 8 点队伍（cnt 1）、idx 9 预设确认框（点确定）、idx 10~12 点队伍 cnt 2~4、idx 13 退出循环。

        `loop` 可以整体替换 idx 8 起的帧；`team_ok=False` 让点队伍的 OCR 点击一直不成功（cnt 不增加，只剩「确定」分支在转）。
        """
        loop = loop if loop is not None else [{}, self.SURE_FRAME if confirm_at_9 else {}, {}, {}, {}, {}]      # idx 8~13
        task = self.make(self.NAME_PREFIX + loop + tail)
        def stage(shots):
            def run(*args, **kwargs):
                for _ in range(shots):
                    task.screenshot()
            return run
        task._name_to_top = stage(1)          # 分组回顶、队伍回顶各 1 张
        task._name_find = stage(1)            # 找分组、找队伍各 1 张
        task._name_select_group = stage(2)
        task._name_locate = stage(2)
        task.I_SOU_CLICK_PRESENT = object()
        # 沙箱的 appear 不认 interval；真实 `BaseTask.appear` 会按 interval 限流，这里补上，点击频率才贴近真机
        base_appear, last_hit = task.appear, {}

        def gated_appear(target, interval=None, threshold=None):
            visible = base_appear(target)
            if visible and interval:
                previous = last_hit.get(target.name)
                if previous is not None and self.now - previous < interval:
                    return False
                last_hit[target.name] = self.now
            return visible
        task.appear = gated_appear
        task._click_team_by_name = Mock(
            side_effect=lambda team, interval=None: (self.events.append(('team_click', round(self.now, 3))), team_ok)[1])
        return task, lambda: task.switch_soul_by_name('G', 'T')


class NumericPathTest(ReplaceDialogSandbox):
    def test_only_the_original_confirm_dialog_is_clicked_once_and_the_flow_continues(self):
        task, fn = self.run_numeric([{}])
        self.run_task(fn)
        self.assertEqual(len(self.sure_clicks()), 1)
        self.assertTrue(self.switched_logged())

    def test_replace_dialog_appearing_after_the_original_confirm_gets_one_more_confirm_click(self):
        task, fn = self.run_numeric([{}, {}] + [self.SURE_FRAME] * 15 + [{}])   # idx 8、9 空；10 起替换确认框撑 15 帧（约 4.5 秒），之后关闭
        self.run_task(fn)
        clicks = self.sure_clicks()
        self.assertEqual(len(clicks), 2)
        self.assertGreater(clicks[1][4], clicks[0][4])                                    # 第二次点击在原确认之后
        self.assertEqual([r[1:] for r in self.of('reaction')][-1], rp.REACTION_CONFIRM)  # 走 CONFIRM reaction，点击前有 fresh 确认
        self.assertTrue(self.switched_logged())                                           # 弹窗关闭后才继续并记成功
        self.assertEqual(self.of('click')[-1][1], self.sure.name)

    def test_no_extra_dialog_means_a_bounded_short_observation_and_no_extra_click(self):
        task, fn = self.run_numeric([{}])
        self.run_task(fn)
        self.assertEqual(len(self.sure_clicks()), 1)
        confirm_at = self.sure_clicks()[0][4]
        self.assertLessEqual(self.now - confirm_at, ss.SwitchSoul.REPLACE_OBSERVE_TIMEOUT + 4 * SHOT)   # 不是长时间固定等待
        self.assertEqual(self.of('sleep').count(('sleep', ss.SwitchSoul.REPLACE_OBSERVE_TIMEOUT)), 0)
        self.logger.warning.assert_not_called()

    def test_the_replace_dialog_closing_after_the_click_lets_the_flow_continue(self):
        task, fn = self.run_numeric([{}] + [self.SURE_FRAME] * 15 + [{}])   # 点击之后还撑几帧才消失
        self.run_task(fn)
        self.assertLessEqual(len(self.sure_clicks()), 3)
        self.assertTrue(self.switched_logged())

    def test_a_dialog_that_never_closes_stops_with_a_bounded_exception_and_no_success(self):
        task, fn = self.run_numeric([{}, {}, self.SURE_FRAME])                             # idx 10 起一直在
        with self.assertRaises(GamePageUnknownError):
            self.run_task(fn)
        confirm_at = self.sure_clicks()[0][4]
        limit = ss.SwitchSoul.REPLACE_OBSERVE_TIMEOUT + ss.SwitchSoul.REPLACE_CLOSE_TIMEOUT + 6 * SHOT
        self.assertLessEqual(self.now - confirm_at, limit)                                 # 有界
        self.assertLessEqual(len(self.sure_clicks()), 1 + 1 + int(ss.SwitchSoul.REPLACE_CLOSE_TIMEOUT // 3) + 1)   # 点击次数有界
        self.assertFalse(self.switched_logged())                                           # 不记成功

    def test_already_equipped_preset_never_looks_for_or_clicks_a_replace_dialog(self):
        # 没有预设确认框（已经装备同一预设）：不在这里做额外观察，也不点任何确定
        frames = SWIPE_PHASE + [{'SW_TEAM': TEAM_ROI}, {'SW_TEAM': TEAM_ROI}, {}]
        task = self.make(frames)
        self.run_task(lambda: task.switch_soul_one(2, 2))
        self.assertEqual(self.sure_clicks(), [])
        self.assertTrue(self.switched_logged())


class ByNamePathTest(ReplaceDialogSandbox):
    def test_only_the_original_confirm_dialog_is_clicked_once(self):
        task, fn = self.make_by_name([{}])
        self.run_task(fn)
        self.assertEqual(len(self.sure_clicks()), 1)
        self.assertEqual(len(self.of('team_click')), 4)                    # 原有「点 4 次队伍」的流程不变
        self.assertTrue(self.switched_logged())

    def test_replace_dialog_after_the_loop_gets_one_more_confirm_click(self):
        task, fn = self.make_by_name([{}] + [self.SURE_FRAME] * 8 + [{}])   # idx 14 空；15 起替换确认框撑 8 帧（约 2.4 秒，不到一次 3 秒重试），之后关闭
        self.run_task(fn)
        self.assertEqual(len(self.sure_clicks()), 2)
        self.assertEqual(len(self.of('team_click')), 4)
        self.assertEqual([r[1:] for r in self.of('reaction')][-1], rp.REACTION_CONFIRM)
        self.assertTrue(self.switched_logged())

    def test_no_extra_dialog_is_a_short_bounded_observation(self):
        task, fn = self.make_by_name([{}])
        self.run_task(fn)
        last_confirm = self.sure_clicks()[-1][4]
        self.assertLessEqual(self.now - last_confirm, 4 * 1.5 + 2.5 + ss.SwitchSoul.REPLACE_OBSERVE_TIMEOUT + 8 * SHOT)

    def test_a_dialog_that_never_closes_stops_with_a_bounded_exception_and_no_success(self):
        task, fn = self.make_by_name([{}, self.SURE_FRAME])
        with self.assertRaises(GamePageUnknownError):
            self.run_task(fn)
        self.assertLessEqual(len(self.sure_clicks()), 1 + 1 + int(ss.SwitchSoul.REPLACE_CLOSE_TIMEOUT // 3) + 1)
        self.assertFalse(self.switched_logged())

    def test_without_any_preset_confirm_there_is_no_extra_observation(self):
        task, fn = self.make_by_name([{}], confirm_at_9=False)
        self.run_task(fn)
        self.assertEqual(self.sure_clicks(), [])
        self.assertTrue(self.switched_logged())


class OnlyAfterAPresetConfirmTest(ReplaceDialogSandbox):
    """额外观察只在预设确认框出现并确认过之后做：没有预设确认框就不调用，不是全局观察。"""

    def test_numeric_calls_the_helper_only_after_a_preset_confirm(self):
        task, fn = self.run_numeric([{}])
        task._confirm_bondling_replace_dialog = Mock(return_value=False)
        self.run_task(fn)
        task._confirm_bondling_replace_dialog.assert_called_once()
        frames = SWIPE_PHASE + [{'SW_TEAM': TEAM_ROI}, {'SW_TEAM': TEAM_ROI}, {}]
        self.events.clear()
        self.n, self.now = 0, 0.0
        task = self.make(frames)
        task._confirm_bondling_replace_dialog = Mock()
        self.run_task(lambda: task.switch_soul_one(2, 2))
        task._confirm_bondling_replace_dialog.assert_not_called()

    def test_by_name_calls_the_helper_only_after_a_preset_confirm(self):
        task, fn = self.make_by_name([{}])
        task._confirm_bondling_replace_dialog = Mock(return_value=False)
        self.run_task(fn)
        task._confirm_bondling_replace_dialog.assert_called_once()
        self.events.clear()
        self.n, self.now = 0, 0.0
        task, fn = self.make_by_name([{}], confirm_at_9=False)
        task._confirm_bondling_replace_dialog = Mock()
        self.run_task(fn)
        task._confirm_bondling_replace_dialog.assert_not_called()


class ContinuousAndStuckConfirmTest(ReplaceDialogSandbox):
    """预设确认框和契灵替换框连续出现（中间没有空白帧）/「确定」从第一次出现起就点不掉：两条路径都有界退出。"""

    NUMERIC_HEAD = SWIPE_PHASE + [{'SW_TEAM': TEAM_ROI}, {'SW_TEAM': TEAM_ROI}]       # idx 0~4，idx 5 起由用例决定

    def bound(self):
        return ss.SwitchSoul.CONFIRM_CLOSE_TIMEOUT

    # ---- 数字模式 ----
    def test_numeric_two_dialogs_back_to_back_without_a_blank_frame_are_handled_inside_the_confirm_loop(self):
        task = self.make(self.NUMERIC_HEAD + [self.SURE_FRAME] * 13 + [{}])             # 原确认 → 紧接着替换框，约 3.9 秒后全部消失
        self.run_task(lambda: task.switch_soul_one(2, 2))
        clicks = self.sure_clicks()
        self.assertGreaterEqual(len(clicks), 2)                                           # 第二个框也被点了
        self.assertLessEqual(len(clicks), 4)
        self.assertLessEqual(self.now - clicks[0][4], self.bound())
        self.assertTrue(self.switched_logged())                                           # 都点掉之后才继续并记成功

    def test_numeric_sure_that_is_there_from_the_first_frame_and_never_goes_away_stops_with_an_exception(self):
        task = self.make(self.NUMERIC_HEAD + [self.SURE_FRAME])                           # idx 5 起一直在
        with self.assertRaises(GamePageUnknownError):
            self.run_task(lambda: task.switch_soul_one(2, 2))
        clicks = self.sure_clicks()
        self.assertLessEqual(self.now - clicks[0][4], self.bound() + 4 * SHOT)             # 本地超时，不靠外层
        self.assertLessEqual(len(clicks), 2 + int(self.bound() // 3))                      # 点击仍是 3 秒间隔，次数有界
        self.assertFalse(self.switched_logged())

    def test_numeric_timeout_does_not_change_the_click_pacing_or_reaction(self):
        task = self.make(self.NUMERIC_HEAD + [self.SURE_FRAME])
        with self.assertRaises(GamePageUnknownError):
            self.run_task(lambda: task.switch_soul_one(2, 2))
        times = [c[4] for c in self.sure_clicks()]
        gaps = [round(b - a, 1) for a, b in zip(times, times[1:])]
        self.assertTrue(all(g >= 2.9 for g in gaps), gaps)                                 # 仍是 3 秒间隔
        self.assertEqual(len([r for r in self.of('reaction') if r[1:] == rp.REACTION_CONFIRM]), 1)   # 只有首次确认带 reaction

    # ---- 按名称模式 ----
    def test_by_name_two_dialogs_back_to_back_without_a_blank_frame_are_handled_and_continue(self):
        task, fn = self.make_by_name([], loop=[{}] + [self.SURE_FRAME] * 14 + [{}])        # idx 9 起「确定」连续在约 4.2 秒
        self.run_task(fn)
        self.assertGreaterEqual(len(self.sure_clicks()), 2)
        self.assertLessEqual(len(self.sure_clicks()), 8)
        self.assertTrue(self.switched_logged())

    def test_by_name_sure_that_never_goes_away_stops_with_an_exception_and_no_success(self):
        task, fn = self.make_by_name([], loop=[{}] + [self.SURE_FRAME])                    # idx 9 起一直在
        with self.assertRaises(GamePageUnknownError):
            self.run_task(fn)
        self.assertLessEqual(len(self.sure_clicks()), int(self.bound() / 0.8) + int(ss.SwitchSoul.REPLACE_CLOSE_TIMEOUT // 3) + 4)
        self.assertFalse(self.switched_logged())

    def test_by_name_loop_has_its_own_local_timeout_even_if_the_team_click_never_succeeds(self):
        # 点队伍一直不成功时 cnt_click 不增加，旧循环只剩「确定」分支在转：必须由循环自己的本地超时退出
        task, fn = self.make_by_name([], loop=[{}] + [self.SURE_FRAME], team_ok=False)
        with self.assertRaises(GamePageUnknownError):
            self.run_task(fn)
        clicks = self.sure_clicks()
        self.assertLessEqual(self.now - clicks[0][4], self.bound() + 4 * SHOT)
        self.assertLessEqual(len(clicks), int(self.bound() / 0.8) + 3)                     # 点击次数有界（0.8 秒间隔）
        self.assertFalse(self.switched_logged())


    def test_by_name_timer_restarts_when_the_dialog_blinks_away(self):
        # 确定每次连续出现都不到超时（中间有空白帧），总时间超过超时：不能误报成点不掉
        blink = [self.SURE_FRAME] * 3 + [{}]
        task, fn = self.make_by_name([{}], loop=[{}] + blink * 8)
        task.CONFIRM_CLOSE_TIMEOUT = 1.0
        calls = [0]

        def team_click(*args, **kwargs):                       # 前 6 次点队伍不成功：让循环多转几个来回，「确定」在循环里被点好几次
            calls[0] += 1
            self.events.append(('team_click', round(self.now, 3)))
            return calls[0] > 6
        task._click_team_by_name = Mock(side_effect=team_click)
        self.run_task(fn)
        in_loop = [c for c in self.sure_clicks()]
        self.assertGreaterEqual(len(in_loop), 3)
        self.assertGreater(in_loop[-1][4] - in_loop[0][4], 1.0)   # 总时长超过超时，但每次连续出现都不到
        self.assertTrue(self.switched_logged())


class TotalLoopTimeoutTest(ReplaceDialogSandbox):
    """按名称模式「选队伍 + 处理确认」循环的总超时（`SWITCH_LOOP_TIMEOUT`）。

    只覆盖这一段循环；分组查找、滑动、导航没有被它覆盖。三种超时各管一段，下面的用例分别验证实际覆盖范围：
    连续确认超时（`CONFIRM_CLOSE_TIMEOUT`，「确定」连续存在）、契灵替换框超时（`REPLACE_CLOSE_TIMEOUT`，循环之后）、
    总超时（循环整体，不被任何分支重置）。
    """

    def total(self):
        return ss.SwitchSoul.SWITCH_LOOP_TIMEOUT

    def loop_elapsed(self):
        started = self.of('team_click')[0][1]
        return self.now - started

    def run_expect(self, fn):
        with self.assertRaises(GamePageUnknownError) as cm:
            self.run_task(fn)
        return str(cm.exception)

    def test_never_seeing_sure_and_never_clicking_the_team_stops_at_the_total_timeout(self):
        task, fn = self.make_by_name([], loop=[{}], team_ok=False)                  # 全程没有确定、点队伍一直失败
        message = self.run_expect(fn)
        self.assertIn('Team switch loop', message)
        self.assertGreater(self.loop_elapsed(), self.total() - 2 * SHOT)
        self.assertLessEqual(self.loop_elapsed(), self.total() + 3 * SHOT)
        self.assertLess(self.n, 250)                                                 # 靠总超时退出，不是撞沙箱的截图失控保护
        self.assertEqual(self.sure_clicks(), [])
        self.assertFalse(self.switched_logged())

    def test_sure_blinking_with_no_progress_is_stopped_by_the_total_timeout_not_the_sure_timer(self):
        blink = [self.SURE_FRAME] * 3 + [{}] * 5                                     # 每次连续出现约 0.9 秒，远不到 10 秒
        task, fn = self.make_by_name([], loop=[{}] + blink * 30, team_ok=False)
        message = self.run_expect(fn)
        self.assertIn('Team switch loop', message)                                   # 不是 'Preset confirm dialog'
        self.assertGreater(self.loop_elapsed(), self.total() - 2 * SHOT)
        self.assertLessEqual(self.loop_elapsed(), self.total() + 3 * SHOT)
        self.assertGreaterEqual(len(self.sure_clicks()), 10)                         # 确定被反复点过（sure_timer 反复清零）
        self.assertLessEqual(len(self.sure_clicks()), int(self.total() / 0.8) + 2)
        self.assertLess(self.n, 250)
        self.assertFalse(self.switched_logged())

    def test_the_sure_click_continue_branch_cannot_bypass_the_total_timeout(self):
        # 连续确认超时放到不可能触发：只剩「点确定 → continue」这条分支在转，总超时仍然每轮都检查
        task, fn = self.make_by_name([], loop=[{}] + [self.SURE_FRAME], team_ok=False)
        task.CONFIRM_CLOSE_TIMEOUT = 100000.0
        message = self.run_expect(fn)
        self.assertIn('Team switch loop', message)
        self.assertLessEqual(self.loop_elapsed(), self.total() + 3 * SHOT)
        self.assertLessEqual(len(self.sure_clicks()), int(self.total() / 0.8) + 2)   # 点击仍是 0.8 秒间隔，次数有界
        self.assertFalse(self.switched_logged())

    def test_normal_flows_finish_far_below_the_total_timeout_with_the_original_click_pacing(self):
        for tail, loop in (([{}], None),                                            # 只有原确认框
                           ([{}], [{}] + [self.SURE_FRAME] * 14 + [{}]),             # 原确认 + 契灵确认连续出现
                           ([{}] + [self.SURE_FRAME] * 8 + [{}], None)):             # 循环之后才出现契灵确认
            with self.subTest(loop=loop is not None, tail=len(tail)):
                self.setUp()
                task, fn = self.make_by_name(tail, loop=loop)
                self.run_task(fn)
                self.assertEqual(len(self.of('team_click')), 4)                      # 四次队伍点击规则不变
                self.assertLess(self.loop_elapsed(), self.total() / 3)                # 正常流程不会逼近总超时
                times = [c[4] for c in self.sure_clicks()]
                self.assertTrue(all(b - a >= 0.8 - 1e-6 for a, b in zip(times, times[1:])), times)   # 0.8 秒间隔不变
                self.assertTrue(self.switched_logged())

    def test_each_timeout_covers_its_own_stretch_and_reports_it(self):
        # 1) 连续确认超时：确定一直在、点队伍一直失败 → 约 10 秒，早于总超时
        task, fn = self.make_by_name([], loop=[{}] + [self.SURE_FRAME], team_ok=False)
        message = self.run_expect(fn)
        self.assertIn('Preset confirm dialog', message)
        self.assertLess(self.loop_elapsed(), ss.SwitchSoul.CONFIRM_CLOSE_TIMEOUT + 3 * SHOT + 1.0)
        self.assertLess(self.loop_elapsed(), self.total())
        # 2) 契灵替换框超时：循环正常结束，之后的替换框一直在 → 8 秒，属于循环之后的那一段
        self.setUp()
        task, fn = self.make_by_name([{}, self.SURE_FRAME])
        message = self.run_expect(fn)
        self.assertIn('Bondling replace dialog', message)
        # 3) 总超时：没有任何确定、点队伍失败 → 45 秒，前两条都管不到
        self.setUp()
        task, fn = self.make_by_name([], loop=[{}], team_ok=False)
        message = self.run_expect(fn)
        self.assertIn('Team switch loop', message)


class ScopeTest(ReplaceDialogSandbox):
    def test_the_helper_is_a_shared_small_method_used_by_both_paths_and_not_a_global_click(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(ss))
        users = {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
                 and any(isinstance(n, ast.Attribute) and n.attr == '_confirm_bondling_replace_dialog'
                         for n in ast.walk(fn))}
        self.assertEqual(users, {'switch_soul_one', 'switch_soul_by_name'})
        self.assertEqual(ss.SwitchSoul.REPLACE_OBSERVE_TIMEOUT, 2.0)

    def test_helper_alone_does_nothing_when_no_dialog_shows(self):
        task = self.make([{}])
        self.assertFalse(self.run_task(task._confirm_bondling_replace_dialog))
        self.assertEqual(self.of('click'), [])
