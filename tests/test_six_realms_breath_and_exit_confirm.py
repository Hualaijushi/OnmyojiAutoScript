# This Python file uses the following encoding: utf-8
"""孔雀国唤息确认 / 退出孔雀国确认：2026-10-10 新版公共双按钮弹窗适配 + 唤息失败循环保护。

事故（2026-10-12 16:37 ~ 16:41，oas1）：
- 唤息弹窗「是否消耗300万相铃召唤宁息之屿」的确认键从「进入」改成新版「确认」，六道专用模板
  `I_PK_STORE_STILLIN` 只剩 0.028；`run_on_pk_store_confirm` 兜底点「取消」回主界面，唤息条件不变又去唤息，
  6 轮后 `GameTooManyClickError: MS_M_STORE_ACTIVITY, UI_UI_CANCEL`。
- 点「退出主界面」后新弹出「是否离开孔雀国？」确认框，到不了孔雀国页，目标页进入失败 hook 的 `ui_click`
  在弹窗上空等 60 秒 → GameStuckError。
修复：唤息弹窗正文命中后点公共 `I_UI_CONFIRM`（旧「进入」保留兼容）；确认不了时本轮不再唤息；
退出边加 `on_leave_failure` 点「确定」（排除唤息弹窗）。

- 真实画面：两张事故截图（`tests/fixtures/six_realms/`），走生产 `ImageRuntime` 匹配；其余状态用哨兵帧。
- 业务方法与导航 hook 执行（`_run_hooks` → `_execute_action` → `ConditionalAction`）都用真实实现。
"""

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

import tasks.SixRealms.peacock_kingdom.page as pk_pages
from module.image.runtime import ImageRuntime
from tasks.GameUi.action import ConditionalAction
from tasks.GameUi.navigator import GameUi
from tasks.SixRealms.page import page_peacock_kingdom
from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom

FIX = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'six_realms'
BREATH = FIX / 'pk_breath_dialog_2026-10-12.png'
EXIT = FIX / 'pk_exit_dialog_2026-10-12.png'
FRAME_SECONDS = 0.3
HARD_SCREENS = 300

CONFIRM = PeacockKingdom.I_UI_CONFIRM.name
CANCEL = PeacockKingdom.I_UI_CANCEL.name
BREATH_BUTTON = PeacockKingdom.I_M_STORE_ACTIVITY.name
STILLIN = PeacockKingdom.I_PK_STORE_STILLIN.name


def _load_rgb(path):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), -1)[:, :, :3], cv2.COLOR_BGR2RGB)


class _RunAway(BaseException):
    """假界面截图次数超过硬上限：保护失效时立刻中止。"""


# 哨兵帧上可见的资产
SENTINELS = {
    'PK_MAIN': {BREATH_BUTTON},
    'OLD_BREATH_DIALOG': {PeacockKingdom.I_MS_CHECK_OPEN_STORE.name, STILLIN, BREATH_BUTTON},
    'DIALOG_WITHOUT_BUTTON': {PeacockKingdom.I_MS_CHECK_OPEN_STORE.name, BREATH_BUTTON},
}


class _Kingdom(PeacockKingdom):
    """假孔雀国：`frame` 是当前画面；`effects` 定义点击后画面怎么变。真实帧走生产匹配，哨兵帧查表。"""

    runtime = None
    images = {}

    def __init__(self, frame, effects=None):
        self.now = 1000.0
        self.frame = frame
        self.effects = effects or {}
        self.clicks = []
        self.screens = 0
        self.coin_num = 500
        self.skill_roaring_thunder = 1
        self.breath_failed = False
        self.goto_page = Mock(name='goto_page')

    def screenshot(self):
        self.screens += 1
        if self.screens > HARD_SCREENS:
            raise _RunAway
        self.now += FRAME_SECONDS

    def maybe_screenshot(self, soft_skip=False):
        if not soft_skip:
            self.screenshot()

    def appear(self, target, interval=None, threshold=None):
        if self.frame in self.images:
            payload = target.to_service_payload()
            return self.runtime._match_rule_payload(image=self.images[self.frame], rule_data=payload,
                                                    threshold=threshold)['matched']
        return target.name in SENTINELS.get(self.frame, set())

    def appear_then_click(self, target, interval=None, threshold=None, **kwargs):
        if not self.appear(target, threshold=threshold):
            return False
        self.clicks.append(target.name)
        self.frame = self.effects.get((self.frame, target.name), self.frame)
        return True

    def get_remain_turns(self, rule):
        return 5


def _clock(kingdom):
    return patch('module.base.timer.time', SimpleNamespace(time=lambda: kingdom.now))


class _RealFramesCase(TestCase):
    @classmethod
    def setUpClass(cls):
        _Kingdom.runtime = ImageRuntime()
        _Kingdom.images = {'BREATH_DIALOG': _load_rgb(BREATH), 'EXIT_DIALOG': _load_rgb(EXIT)}

    @classmethod
    def tearDownClass(cls):
        _Kingdom.runtime.shutdown()
        _Kingdom.runtime, _Kingdom.images = None, {}


# --------------------------------------------------------------------------------------
# 一、唤息确认
# --------------------------------------------------------------------------------------

class BreathConfirmTest(_RealFramesCase):
    def test_new_breath_dialog_is_confirmed_not_cancelled(self):
        k = _Kingdom('PK_MAIN', effects={('PK_MAIN', BREATH_BUTTON): 'BREATH_DIALOG',
                                         ('BREATH_DIALOG', CONFIRM): 'PK_MAIN'})
        with _clock(k):
            self.assertTrue(k._use_breath())
        self.assertEqual(k.clicks, [BREATH_BUTTON, CONFIRM])
        self.assertEqual(k.coin_num, 200)
        self.assertFalse(k.breath_failed)
        k.goto_page.assert_not_called()

    def test_main_loop_handler_confirms_the_new_dialog(self):
        k = _Kingdom('BREATH_DIALOG', effects={('BREATH_DIALOG', CONFIRM): 'PK_MAIN'})
        with _clock(k):
            k.run_on_pk_store_confirm()
        self.assertEqual(k.clicks, [CONFIRM])
        self.assertNotIn(CANCEL, k.clicks)
        self.assertFalse(k.breath_failed)
        k.goto_page.assert_not_called()

    def test_old_enter_button_is_still_supported(self):
        k = _Kingdom('PK_MAIN', effects={('PK_MAIN', BREATH_BUTTON): 'OLD_BREATH_DIALOG',
                                         ('OLD_BREATH_DIALOG', STILLIN): 'PK_MAIN'})
        with _clock(k):
            self.assertTrue(k._use_breath())
        self.assertEqual(k.clicks, [BREATH_BUTTON, STILLIN])

    def test_new_dialog_frame_matches_the_public_buttons_but_not_the_old_template(self):
        k = _Kingdom('BREATH_DIALOG')
        self.assertTrue(k.appear(k.I_MS_CHECK_OPEN_STORE))
        self.assertTrue(k.appear(k.I_UI_CONFIRM))
        self.assertTrue(k.appear(k.I_UI_CANCEL))
        self.assertFalse(k.appear(k.I_PK_STORE_STILLIN))       # 旧「进入」模板：事故根因


# --------------------------------------------------------------------------------------
# 二、循环保护
# --------------------------------------------------------------------------------------

class BreathLoopGuardTest(_RealFramesCase):
    def test_confirm_failure_stops_further_breath_this_run(self):
        k = _Kingdom('PK_MAIN', effects={('PK_MAIN', BREATH_BUTTON): 'DIALOG_WITHOUT_BUTTON'})
        with _clock(k):
            self.assertFalse(k._use_breath())
        self.assertTrue(k.breath_failed)
        self.assertEqual(k.clicks, [BREATH_BUTTON])            # 没有点取消、也没有乱点
        k.frame = 'PK_MAIN'
        self.assertFalse(k._should_use_breath([k.I_PK_LAND_FIRE]))
        self.assertFalse(k._summon_store())
        self.assertEqual(k.clicks, [BREATH_BUTTON])            # 之后再也不点唤息

    def test_handler_cancels_once_and_marks_failure_when_the_dialog_stays(self):
        k = _Kingdom('DIALOG_WITHOUT_BUTTON')
        with _clock(k):
            k.run_on_pk_store_confirm()
        self.assertTrue(k.breath_failed)
        k.goto_page.assert_called_once_with(pk_pages.page_pk_main)

    def test_no_failure_when_the_dialog_already_closed(self):
        # 刚确认过、弹窗关闭动画期间被识别成 page_sr_open_store：不算失败，不点取消
        k = _Kingdom('PK_MAIN')
        with _clock(k):
            k.run_on_pk_store_confirm()
        self.assertFalse(k.breath_failed)
        k.goto_page.assert_not_called()

    def test_success_path_keeps_breath_available(self):
        k = _Kingdom('PK_MAIN')
        self.assertTrue(k._should_use_breath([k.I_PK_LAND_FIRE]))

    def test_before_run_resets_the_guard(self):
        src = inspect.getsource(PeacockKingdom.__mro__[1].before_run)
        self.assertIn('self.breath_failed = False', src)


# --------------------------------------------------------------------------------------
# 三、退出孔雀国确认
# --------------------------------------------------------------------------------------

def _exit_transition():
    return next(t for t in pk_pages.page_pk_exit.transitions if t.destination is page_peacock_kingdom)


class ExitConfirmTest(_RealFramesCase):
    def test_exit_transition_keeps_its_action_and_gains_a_leave_failure_confirm(self):
        transition = _exit_transition()
        self.assertIs(transition.action, PeacockKingdom.I_PK_EXIT_MAIN)
        self.assertEqual(transition.on_leave_failure, [pk_pages.PK_EXIT_DIALOG_CONFIRM])
        self.assertIsInstance(pk_pages.PK_EXIT_DIALOG_CONFIRM, ConditionalAction)

    def test_leave_failure_hook_clicks_confirm_on_the_real_exit_dialog(self):
        k = _Kingdom('EXIT_DIALOG')
        self.assertFalse(k.appear(k.I_PK_EXIT_MAIN))            # 旧返回图标在新弹窗上认不出
        k._run_hooks(_exit_transition().on_leave_failure)
        self.assertEqual(k.clicks, [CONFIRM])                  # 点「确定」，不点取消 / 不再提醒

    def test_leave_failure_hook_never_confirms_the_breath_dialog(self):
        k = _Kingdom('BREATH_DIALOG')
        k._run_hooks(_exit_transition().on_leave_failure)
        self.assertEqual(k.clicks, [])                         # 唤息弹窗会花相铃，绝不在这里确认

    def test_transition_leave_failure_runs_before_the_destination_enter_failure_hook(self):
        # 目标页（孔雀国）的进入失败 hook 是 ui_click(I_SR_SWITCH, ...)，在弹窗上会空等；确认必须排在它前面
        src = inspect.getsource(GameUi._execute_transition)
        branch = src[src.index('if self._wait_for_destination(destination):'):]
        self.assertLess(branch.index('self._run_hooks(transition.on_leave_failure)'),
                        branch.index('self._run_hooks(destination.on_enter_failure)'))
