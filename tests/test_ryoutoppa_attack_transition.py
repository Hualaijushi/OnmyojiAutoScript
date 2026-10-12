# This Python file uses the following encoding: utf-8
"""寮突破点击「进攻」后的过渡状态：不重点进攻、不把正常加载判成交互异常。

事故（2026-10-11 00:00 ~ 00:30，oas2，6 次）：点击进攻后游戏先把列表压暗转圈（遮罩下 `I_FIRE` 0.956、
`I_TOPPA_RECORD` 0.993 仍能匹配），再全屏加载，然后才进战斗。旧逻辑点完 0.1 秒就判「进攻按钮仍存在」，
第 2 次尝试里截到加载画面又判「状态已变化」并直接放弃，`INTERACTION_ERROR` → `GamePageUnknownError`，
连续 3 次后 oas2 进程退出；而那几场战斗其实都已开打。修复：点击后有界等待
（`RYOU_TOPPA_ATTACK_ENTER_TIMEOUT`），窗口内只认战斗页、不点任何东西，到时才按原逻辑处理。

- 真实 `attack_area` + 随点击 / 假时钟变化的假寮突破界面（`_Arena`）；压暗转圈与全屏加载两种过渡帧是
  事故当晚的真实截图，用生产 `ImageRuntime` 匹配；弹窗 / 战斗 / 列表用哨兵帧。
- 假界面自带硬帧数上限，保护失效时立刻失败而不是挂死。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.image.runtime import ImageRuntime
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.RealmRaid.assets import RealmRaidAssets
from tasks.RyouToppa.script_task import (
    RYOU_TOPPA_ACTION_RETRIES,
    RYOU_TOPPA_ATTACK_ENTER_TIMEOUT,
    AreaAttackResult,
    ScriptTask as RyouToppa,
)

RT = 'tasks.RyouToppa.script_task'
FIX = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'ryou_toppa'
DIMMED = FIX / 'attack_transition_dimmed_2026-10-11.png'
LOADING = FIX / 'attack_transition_loading_2026-10-11.png'
FRAME_SECONDS = 0.3
FIRE_DELAY = 0.5
HARD_SCREENS = 500
FOREVER = 10 ** 6

FIRE = RealmRaidAssets.I_FIRE.name


def _load_rgb(path):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), -1)[:, :, :3], cv2.COLOR_BGR2RGB)


class _RunAway(BaseException):
    """假界面截图次数超过硬上限：保护失效时立刻中止。"""


class _Arena(RyouToppa):
    """假寮突破界面：目标详情弹窗（进攻按钮可见）→ 点进攻 → 按 `effects` 走过渡，最后进战斗。

    `effects[i]` 是第 i 次有效进攻点击之后的时间线 `[(持续秒数, 帧), ...]`，最后一段一直保持；
    用完后沿用最后一条。帧：'POPUP'（弹窗，进攻按钮和列表标识都在）/ 'BATTLE' / 'LIST'（哨兵），
    以及真实截图 'DIMMED' / 'LOADING'（走生产匹配）。
    """

    runtime = None
    images = {}

    def __init__(self, effects):
        self.now = 1000.0
        self.effects = effects
        self.timeline, self.timeline_start = [(FOREVER, 'POPUP')], self.now
        self.fire_clicks, self.clicks = [], []
        self.screens = 0
        self.config = SimpleNamespace(ryou_toppa=SimpleNamespace(
            raid_config=SimpleNamespace(random_delay=False), fire_reaction=FireReactionConfig()))
        self.device = SimpleNamespace(click_record_clear=Mock(name='click_record_clear'))
        self.check_area = Mock(name='check_area', return_value=True)
        self._finish_area_battle = Mock(name='_finish_area_battle', return_value=AreaAttackResult.SUCCESS)

    # ---- 假时钟 / 假设备 ----
    def frame(self):
        elapsed = self.now - self.timeline_start
        for duration, frame in self.timeline:
            if elapsed < duration:
                return frame
            elapsed -= duration
        return self.timeline[-1][1]

    def screenshot(self):
        self.screens += 1
        if self.screens > HARD_SCREENS:
            raise _RunAway
        self.now += FRAME_SECONDS

    def sleep(self, seconds):
        self.now += seconds

    def is_in_battle(self, is_screenshot=True):
        return self.frame() == 'BATTLE'

    def appear(self, target, interval=None, threshold=None):
        frame = self.frame()
        if frame in self.images:
            payload = target.to_service_payload()
            return self.runtime._match_rule_payload(image=self.images[frame], rule_data=payload,
                                                    threshold=threshold)['matched']
        if target.name == FIRE:
            return frame == 'POPUP'
        if target.name == self.I_TOPPA_RECORD.name:
            return frame in ('POPUP', 'LIST')
        return False

    def confirm_page(self, page, skip_first_screenshot=True):
        if not skip_first_screenshot:
            self.screenshot()
        return self.frame() in ('POPUP', 'LIST', 'DIMMED')

    def click(self, target, interval=None):
        self.clicks.append((round(self.now - 1000.0, 2), target.name))
        return True

    def appear_then_click(self, target, interval=None, threshold=None):
        if not self.appear(target, threshold=threshold):
            return False
        self.click(target)
        if target.name == FIRE:
            self.fire_clicks.append(self.now)
            effect = self.effects[min(len(self.fire_clicks), len(self.effects)) - 1]
            self.timeline, self.timeline_start = effect, self.now
        return True


def _attack(arena, index=1):
    fake_time = SimpleNamespace(time=lambda: arena.now)
    with patch('module.base.timer.time', fake_time), \
            patch(f'{RT}.time.sleep', side_effect=arena.sleep), \
            patch(f'{RT}.random_delay', return_value=FIRE_DELAY):
        return arena.attack_area(index)


class _RealFramesCase(TestCase):
    @classmethod
    def setUpClass(cls):
        _Arena.runtime = ImageRuntime()
        _Arena.images = {'DIMMED': _load_rgb(DIMMED), 'LOADING': _load_rgb(LOADING)}

    @classmethod
    def tearDownClass(cls):
        _Arena.runtime.shutdown()
        _Arena.runtime, _Arena.images = None, {}

    def assert_single_fire_then_battle(self, arena, result):
        self.assertEqual(result, AreaAttackResult.SUCCESS)
        arena._finish_area_battle.assert_called_once_with(1)
        self.assertEqual(len(arena.fire_clicks), 1)                  # 等待窗口内没有重点进攻
        self.assertEqual([n for _, n in arena.clicks], [FIRE])       # 也没有重新点区域


# --------------------------------------------------------------------------------------
# 一、真实过渡帧本身：解释旧逻辑为什么会误判
# --------------------------------------------------------------------------------------

class TransitionFramesTest(_RealFramesCase):
    def test_dimmed_frame_still_matches_fire_and_list_marker(self):
        arena = _Arena([[(FOREVER, 'DIMMED')]])
        arena.timeline = [(FOREVER, 'DIMMED')]
        self.assertTrue(arena.appear(RealmRaidAssets.I_FIRE, threshold=0.8))      # 旧逻辑：「按钮仍存在」
        self.assertTrue(arena.appear(arena.I_TOPPA_RECORD, threshold=0.85))
        self.assertFalse(arena.is_in_battle(False))

    def test_loading_frame_matches_nothing(self):
        arena = _Arena([[(FOREVER, 'LOADING')]])
        arena.timeline = [(FOREVER, 'LOADING')]
        self.assertFalse(arena.appear(RealmRaidAssets.I_FIRE, threshold=0.8))     # 旧逻辑：「状态已变化」
        self.assertFalse(arena.appear(arena.I_TOPPA_RECORD, threshold=0.85))
        self.assertFalse(arena.is_in_battle(False))


# --------------------------------------------------------------------------------------
# 二、attack_area：点击后过渡只等待，不重点、不判异常
# --------------------------------------------------------------------------------------

class AttackTransitionTest(_RealFramesCase):
    def test_case1_long_dimmed_spinner_waits_without_clicking_fire_again(self):
        arena = _Arena([[(4.0, 'DIMMED'), (FOREVER, 'BATTLE')]])
        self.assert_single_fire_then_battle(arena, _attack(arena))

    def test_case2_long_loading_screen_keeps_waiting(self):
        arena = _Arena([[(0.3, 'DIMMED'), (4.0, 'LOADING'), (FOREVER, 'BATTLE')]])
        self.assert_single_fire_then_battle(arena, _attack(arena))

    def test_case3_battle_page_right_after_click(self):
        arena = _Arena([[(0.2, 'DIMMED'), (FOREVER, 'BATTLE')]])
        self.assert_single_fire_then_battle(arena, _attack(arena))

    def test_incident_replay_dimmed_then_loading_then_battle(self):
        # 与 00:01:33 同形：转圈约 1 秒、加载约 1.3 秒；旧逻辑在点击后 1.28 秒判交互异常
        arena = _Arena([[(1.0, 'DIMMED'), (1.3, 'LOADING'), (FOREVER, 'BATTLE')]])
        self.assert_single_fire_then_battle(arena, _attack(arena))

    def test_case4_never_enters_battle_falls_back_to_interaction_error(self):
        arena = _Arena([[(0.6, 'DIMMED'), (FOREVER, 'LOADING')]])
        start = arena.now
        self.assertEqual(_attack(arena), AreaAttackResult.INTERACTION_ERROR)
        arena._finish_area_battle.assert_not_called()
        self.assertEqual(len(arena.fire_clicks), 1)
        elapsed = arena.now - start
        self.assertGreaterEqual(elapsed, RYOU_TOPPA_ATTACK_ENTER_TIMEOUT)       # 等满窗口才处理
        self.assertLess(elapsed, RYOU_TOPPA_ATTACK_ENTER_TIMEOUT + 6)           # 而且有界

    def test_unregistered_click_is_retried_only_after_the_window(self):
        arena = _Arena([[(FOREVER, 'POPUP')]])
        self.assertEqual(_attack(arena), AreaAttackResult.INTERACTION_ERROR)
        self.assertEqual(len(arena.fire_clicks), RYOU_TOPPA_ACTION_RETRIES)
        gaps = [b - a for a, b in zip(arena.fire_clicks, arena.fire_clicks[1:])]
        self.assertTrue(all(gap >= RYOU_TOPPA_ATTACK_ENTER_TIMEOUT for gap in gaps))

    def test_fire_gone_on_the_last_attempt_still_waits_for_battle(self):
        # 第 1 次点击迟迟不生效（> 窗口），第 2 次尝试点击前按钮消失、开始加载：旧逻辑直接判交互异常
        arena = _Arena([[(RYOU_TOPPA_ATTACK_ENTER_TIMEOUT + 0.95, 'POPUP'), (1.5, 'LOADING'), (FOREVER, 'BATTLE')]])
        self.assertEqual(_attack(arena), AreaAttackResult.SUCCESS)
        arena._finish_area_battle.assert_called_once_with(1)
        self.assertEqual(len(arena.fire_clicks), 1)

    def test_fire_gone_at_the_start_of_the_last_attempt_waits_through_a_long_load(self):
        # 第 2 次尝试开头按钮已消失、加载 4 秒：旧逻辑只等 3 秒（`_wait_for_attack_state`）就放弃
        arena = _Arena([[(RYOU_TOPPA_ATTACK_ENTER_TIMEOUT + 0.45, 'POPUP'), (4.0, 'LOADING'), (FOREVER, 'BATTLE')]])
        self.assertEqual(_attack(arena), AreaAttackResult.SUCCESS)
        arena._finish_area_battle.assert_called_once_with(1)
        self.assertEqual(len(arena.fire_clicks), 1)


# --------------------------------------------------------------------------------------
# 三、等待方法本身：只读、有界
# --------------------------------------------------------------------------------------

class WaitForBattleAfterFireTest(_RealFramesCase):
    def _wait(self, timeline):
        arena = _Arena([timeline])
        arena.timeline, arena.timeline_start = timeline, arena.now
        fake_time = SimpleNamespace(time=lambda: arena.now)
        with patch('module.base.timer.time', fake_time):
            return arena, arena._wait_for_battle_after_fire()

    def test_returns_battle_as_soon_as_it_appears(self):
        arena, state = self._wait([(0.6, 'DIMMED'), (0.6, 'LOADING'), (FOREVER, 'BATTLE')])
        self.assertEqual(state, 'battle')
        self.assertLess(arena.now - 1000.0, 1.5)
        self.assertEqual(arena.clicks, [])

    def test_timeout_reports_the_last_frame_like_the_old_helper(self):
        for timeline, expected in (([(FOREVER, 'LOADING')], 'unknown'),
                                   ([(FOREVER, 'LIST')], 'list'),
                                   ([(FOREVER, 'DIMMED')], 'fire')):     # 遮罩超过窗口仍按「按钮还在」交回原逻辑
            with self.subTest(expected=expected):
                arena, state = self._wait(timeline)
                self.assertEqual(state, expected)
                self.assertGreaterEqual(arena.now - 1000.0, RYOU_TOPPA_ATTACK_ENTER_TIMEOUT)
                self.assertLess(arena.now - 1000.0, RYOU_TOPPA_ATTACK_ENTER_TIMEOUT + 2 * FRAME_SECONDS)
                self.assertEqual(arena.clicks, [])
