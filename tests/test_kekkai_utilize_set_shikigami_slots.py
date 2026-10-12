# This Python file uses the following encoding: utf-8
"""好友结界寄养：确认后不再盲点式神（`set_shikigami(slot_images=..., empty_slots=...)`）。

事故（2026-10-06 23:57 / 10-09 15:04 / 10-10 16:46，均为 oas1）：好友结界两个寄养位都空，`run_utilize`
把右数第一格 `I_U_ADD_1` 当结束条件；游戏把式神放进右数第二格，右数第一格一直空着，旧条件永远不满足，
确认后继续按 1.5 / 4.5 秒节奏点式神坐标，`GameTooManyClickError: shikigami_left_2`。寄养其实已经成功
（重跑 10 秒内读到 5:59:2x）。修复：只有好友结界寄养传入空位图标——结束条件改成空位数比进场时少，
点过确认后只在有界时间内观察、不再点式神。不传时 `set_shikigami` 行为完全不变（`check_max_lv`）。

- 单元层：真实 `set_shikigami` + 会随点击变化的假好友结界（`_FriendRealm`，假时钟），游戏放置规则取自
  3 次失败的真实截图（两格都空时先放右数第二格）。
- 接线层：真实 `run_utilize`，替身同 `test_kekkai_utilize_convergence._stuck_task`。
- 真实画面：10-10 事故帧（寄养已成功），用生产 `ImageRuntime` 匹配两个空位图标。
"""

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.exception import GameStuckError
from module.image.runtime import ImageRuntime
from tasks.Component.ReplaceShikigami.replace_shikigami import ReplaceShikigami
from tasks.KekkaiUtilize.config import SelectFriendList
from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tasks.Utils.config_enum import ShikigamiClass
from tests.test_kekkai_utilize_convergence import _RunAway, _stuck_task

RS = 'tasks.Component.ReplaceShikigami.replace_shikigami'
REPO = Path(__file__).resolve().parents[1]
INCIDENT_FRAME = REPO / 'tests' / 'fixtures' / 'kekkai_utilize' / 'friend_realm_after_placement_2026-10-10.png'
HARD_SCREENS = 1000         # 测试自身的安全上限：旧实现跑满 120 秒假时间约 400 帧
FRAME_SECONDS = 0.3
SETTLE = ReplaceShikigami.SET_CONFIRM_SETTLE
MAX_CONFIRM = ReplaceShikigami.SET_CONFIRM_MAX_CLICKS

LEFT_2 = KU.C_SHIKIGAMI_LEFT_2.name
LEFT_6 = KU.C_SHIKIGAMI_LEFT_6.name
CONFIRM = KU.I_U_CONFIRM_SMALL.name
SELECT_NAMES = {getattr(KU, f'C_SHIKIGAMI_LEFT_{i}').name for i in range(1, 8)}


class _Clock:
    def __init__(self, now=1000.0):
        self.now = now


class _FriendRealm(KU):
    """假好友结界式神育成页：右上两个寄养位 + 底部式神选择面板 + 寄养确认框。

    点式神 → 确认框出现；点确认 → 确认框消失、面板关闭，`place_delay` 秒后游戏放置式神：两格都空时先放
    右数第二格（3 次失败截图均如此），否则放剩下那格。`place=False` 模拟点了确认但放置没有生效。
    `appear` / `click` 的 interval 沿用真实语义（未到间隔不点击、返回 False）。
    """

    def __init__(self, *, slots, place=True, sticky_confirm=False, selects_needed=1, place_delay=FRAME_SECONDS):
        self.clock = _Clock()
        self.slots = list(slots)                 # [右数第一格空, 右数第二格空]
        self.place, self.sticky_confirm = place, sticky_confirm
        self.selects_needed, self.place_delay = selects_needed, place_delay
        self.panel_open, self.confirm_visible = True, False
        self.selects = 0
        self.clicks, self.click_times = [], []
        self.pending, self.screens = [], 0
        self.last_true, self.last_click = {}, {}

    def screenshot(self):
        self.screens += 1
        if self.screens > HARD_SCREENS:
            raise _RunAway
        self.clock.now += FRAME_SECONDS
        for item in [p for p in self.pending if p[0] <= self.clock.now]:
            self.pending.remove(item)
            item[1]()

    def _visible(self, name):
        if name == self.I_U_ADD_1.name:
            return self.slots[0]
        if name == self.I_U_ADD_2.name:
            return self.slots[1]
        if name == CONFIRM:
            return self.confirm_visible
        return False

    def appear(self, target, interval=None, threshold=None):
        if interval:
            last = self.last_true.get(target.name)
            if last is not None and self.clock.now - last < interval:
                return False
        seen = self._visible(target.name)
        if seen and interval:
            self.last_true[target.name] = self.clock.now
        return seen

    def click(self, target, interval=None):
        if interval:
            last = self.last_click.get(target.name)
            if last is not None and self.clock.now - last < interval:
                return False
        self.last_click[target.name] = self.clock.now
        self.clicks.append(target.name)
        self.click_times.append(self.clock.now)
        if target.name in SELECT_NAMES and self.panel_open and not self.confirm_visible:
            self.selects += 1
            if self.selects >= self.selects_needed:
                self.confirm_visible = True
        elif target.name == CONFIRM:
            if not self.sticky_confirm:
                self.confirm_visible = False
            if self.place and self.panel_open:
                self.panel_open = False
                self.pending.append((self.clock.now + self.place_delay, self._fill))
        return True

    def _fill(self):
        if self.slots[1]:
            self.slots[1] = False
        elif self.slots[0]:
            self.slots[0] = False

    def appear_then_click(self, target, interval=None):
        if self.appear(target, interval):
            self.click(target)
            return True
        return False

    def after_first_confirm(self):
        return self.clicks[self.clicks.index(CONFIRM) + 1:]


def _set(world, *args, **kwargs):
    """在假时钟下调用真实的 `set_shikigami`（`time.time` / `Timer` / `monotonic` 都走假时钟）。"""
    fake_time = SimpleNamespace(time=lambda: world.clock.now)
    with patch(f'{RS}.time', fake_time), patch('module.base.timer.time', fake_time), \
            patch(f'{RS}.monotonic', side_effect=lambda: world.clock.now):
        return world.set_shikigami(*args, **kwargs)


def _set_slots(world, empty_slots, order=2):
    return _set(world, order, slot_images=(world.I_U_ADD_1, world.I_U_ADD_2), empty_slots=empty_slots)


# --------------------------------------------------------------------------------------
# 一、空位模式：确认后不再点式神
# --------------------------------------------------------------------------------------

class SlotModeTest(TestCase):
    def test_case1_both_slots_empty_exits_when_the_game_fills_the_second_slot(self):
        w = _FriendRealm(slots=(True, True))
        _set_slots(w, 2)
        self.assertEqual(w.clicks, [LEFT_2, CONFIRM])
        self.assertEqual(w.slots, [True, False])            # 右数第一格仍空：旧结束条件永远不满足

    def test_case2_one_slot_left_exits_normally(self):
        for slots, after in (((False, True), [False, False]), ((True, False), [False, False])):
            with self.subTest(slots=slots):
                w = _FriendRealm(slots=slots)
                _set_slots(w, 1)
                self.assertEqual(w.clicks, [LEFT_2, CONFIRM])
                self.assertEqual(w.slots, after)

    def test_case3_no_selection_click_after_confirm_even_if_the_slots_never_change(self):
        w = _FriendRealm(slots=(True, True), place=False)
        _set_slots(w, 2)
        self.assertEqual(w.after_first_confirm(), [])
        confirmed_at = w.click_times[w.clicks.index(CONFIRM)]
        self.assertGreaterEqual(w.clock.now - confirmed_at, SETTLE)              # 观察满 settle 才退出
        self.assertLess(w.clock.now - confirmed_at, SETTLE + 2 * FRAME_SECONDS)  # 而且是有界的

    def test_confirm_dialog_that_keeps_coming_back_is_clicked_a_bounded_number_of_times(self):
        w = _FriendRealm(slots=(True, True), place=False, sticky_confirm=True)
        _set_slots(w, 2)
        self.assertEqual(w.clicks.count(CONFIRM), MAX_CONFIRM)
        self.assertFalse(SELECT_NAMES & set(w.after_first_confirm()))

    def test_selection_is_still_retried_before_the_confirm_dialog_appears(self):
        w = _FriendRealm(slots=(True, True), selects_needed=3)
        _set_slots(w, 2)
        before = w.clicks[:w.clicks.index(CONFIRM)]
        self.assertEqual(len(before), 3)
        self.assertTrue(set(before) <= {LEFT_2, LEFT_6})
        self.assertEqual(w.after_first_confirm(), [])

    def test_slow_placement_waits_without_clicking_instead_of_reselecting(self):
        # 10-10 正常样本：确认后 0.27 秒还多点了一次 shikigami_left_6 才退出；空位模式下这一下也没有
        w = _FriendRealm(slots=(False, True), place_delay=1.0)
        _set_slots(w, 1)
        self.assertEqual(w.clicks, [LEFT_2, CONFIRM])


# --------------------------------------------------------------------------------------
# 二、不传 slot_images：行为与原来完全一致
# --------------------------------------------------------------------------------------

class DefaultPathUnchangedTest(TestCase):
    def test_old_stop_image_still_breaks_when_it_disappears(self):
        # 与 10-10 10:38 正常样本同形：确认后放置稍慢，旧逻辑会再点一次 left_6 才退出
        w = _FriendRealm(slots=(False, True), place_delay=1.0)
        _set(w, 2, w.I_U_ADD_2)
        self.assertEqual(w.clicks, [LEFT_2, CONFIRM, LEFT_6])

    def test_old_single_stop_image_reproduces_the_incident(self):
        # 两格都空、旧调用 stop_image=I_U_ADD_1：确认后一直盲点式神，直到 120 秒超时
        w = _FriendRealm(slots=(True, True))
        with self.assertRaises(GameStuckError):
            _set(w, 2, w.I_U_ADD_1)
        blind = [n for n in w.after_first_confirm() if n in SELECT_NAMES]
        self.assertGreaterEqual(blind.count(LEFT_2), 10)    # 生产里第 10 次就触发 GameTooManyClickError

    def test_confirm_is_not_capped_without_slot_images(self):
        # 旧逻辑确认框还在就一直点；上限只属于空位模式
        w = _FriendRealm(slots=(False, True), place=False, sticky_confirm=True)
        with self.assertRaises(GameStuckError):
            _set(w, 2, w.I_U_ADD_2)
        self.assertGreater(w.clicks.count(CONFIRM), MAX_CONFIRM)

    def test_check_max_lv_calls_are_untouched(self):
        src = inspect.getsource(KU.check_max_lv)
        self.assertEqual(src.count('self.set_shikigami(shikigami_order=7, stop_image=self.I_RS_NO_ADD)'), 2)
        self.assertNotIn('slot_images', src)


# --------------------------------------------------------------------------------------
# 三、接线：run_utilize 按进场时的空位数传参
# --------------------------------------------------------------------------------------

def _wired(slot_1, slot_2):
    t = _stuck_task()
    t.appear = Mock(side_effect=lambda target, **kw: {id(t.I_U_ADD_1): slot_1,
                                                      id(t.I_U_ADD_2): slot_2}.get(id(target), True))
    t.save_image = Mock(name='save_image')
    return t


class RunUtilizeWiringTest(TestCase):
    def test_empty_slot_count_is_passed_with_both_slot_images(self):
        for slot_1, slot_2, expected in ((True, True, 2), (True, False, 1), (False, True, 1)):
            with self.subTest(slot_1=slot_1, slot_2=slot_2):
                t = _wired(slot_1, slot_2)
                self.assertTrue(t.run_utilize(SelectFriendList.SAME_SERVER, ShikigamiClass.N, 2))
                t.set_shikigami.assert_called_once_with(
                    2, slot_images=(t.I_U_ADD_1, t.I_U_ADD_2), empty_slots=expected)

    def test_no_empty_slot_is_still_a_soft_failure(self):
        t = _wired(False, False)
        self.assertFalse(t.run_utilize(SelectFriendList.SAME_SERVER, ShikigamiClass.N, 2))
        t.set_shikigami.assert_not_called()
        self.assertEqual(t.utilize_failed_count, 1)


# --------------------------------------------------------------------------------------
# 四、真实画面：10-10 事故帧上新旧结束条件的差别
# --------------------------------------------------------------------------------------

class IncidentFrameTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = ImageRuntime()
        cls.frame = cv2.cvtColor(cv2.imdecode(np.fromfile(str(INCIDENT_FRAME), dtype=np.uint8), -1)[:, :, :3],
                                 cv2.COLOR_BGR2RGB)

    @classmethod
    def tearDownClass(cls):
        cls.runtime.shutdown()

    def matched(self, rule):
        return self.runtime._match_rule_payload(image=self.frame, rule_data=rule.to_service_payload())['matched']

    def test_after_placement_the_old_stop_image_is_still_visible_but_the_slot_count_dropped(self):
        add_1, add_2 = self.matched(KU.I_U_ADD_1), self.matched(KU.I_U_ADD_2)
        self.assertTrue(add_1)                       # 旧条件 `not appear(I_U_ADD_1)` 永远不成立
        self.assertFalse(add_2)                      # 本账号式神已在右数第二格
        self.assertLess(int(add_1) + int(add_2), 2)  # 新条件：空位 2 → 1，退出
