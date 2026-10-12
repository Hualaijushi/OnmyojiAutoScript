# This Python file uses the following encoding: utf-8
"""秘闻奖励页的结算推进区域：只用面板下方的 `C_RANDOM_SAVE_BOTTOM`。

事故（2026-10-12 13:06，oas2，秘闻第 2 层）：秘闻奖励页同样有奖励宝袋，通用 `_select_reward_region`
选 `C_RANDOM_DEFAULT`；秘闻页右下多了「本次通关时间 / 分享」面板，锚点 (1016, 619) 落在面板上，
同一状态一直复用这个锚点，点满 9 次后 60 秒无点击 → GameStuckError。修复只在 Secret 任务里覆盖选区。

- 真实画面：事故帧（`tests/fixtures/secret/`），面板范围从画面里测出来，不写死；通用选区用生产
  `ImageRuntime` 匹配。
- 采样走生产路径：`_start_settlement_session` / `_advance_settlement_anchor` →
  `ClickSampler.sample_region`。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

import cv2
import numpy as np

from module.image.runtime import ImageRuntime
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Orochi.script_task import ScriptTask as OrochiTask
from tasks.RealmRaid.script_task import ScriptTask as RealmRaidTask
from tasks.Secret.script_task import ScriptTask as SecretTask

FRAME = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'secret' / 'secret_reward_page_2026-10-12.png'
INCIDENT_ANCHOR = (1016, 619)
SAMPLES = 1000


def _load_bgr():
    return cv2.imdecode(np.fromfile(str(FRAME), dtype=np.uint8), -1)[:, :, :3]


def _panel_box(bgr):
    """从事故帧测出「本次通关时间 / 分享」面板的上下沿：面板中段一行里深色像素过半即算面板行。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    rows = [y for y in range(500, 700) if (gray[y, 880:1140] < 30).mean() > 0.5]
    return min(rows), max(rows)


def _context():
    return SimpleNamespace(settlement_total_clicks=0, settlement_anchor_switches=0, settlement_anchor=None,
                           settlement_region_name=None, settlement_session_active=False,
                           settlement_click_budget=0, settlement_clicks_used=0, settlement_stage_name=None)


def _in_roi(point, roi):
    x, y = point
    rx, ry, rw, rh = roi
    return rx <= x < rx + rw and ry <= y < ry + rh


class _Matching(GeneralBattle):
    """通用 GeneralBattle 的 `appear` 换成事故帧上的生产匹配，用来观察通用选区。"""

    runtime = None
    image = None

    def appear(self, target, interval=None, threshold=None):
        payload = target.to_service_payload()
        return self.runtime._match_rule_payload(image=self.image, rule_data=payload, threshold=threshold)['matched']


class SecretRewardRegionTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bgr = _load_bgr()
        cls.panel_top, cls.panel_bottom = _panel_box(cls.bgr)
        cls.task = SecretTask.__new__(SecretTask)

    def test_panel_geometry_measured_from_the_incident_frame(self):
        # 面板约在 y 546~620；事故锚点落在面板底边上
        self.assertTrue(540 <= self.panel_top <= 550, self.panel_top)
        self.assertTrue(615 <= self.panel_bottom <= 625, self.panel_bottom)
        self.assertTrue(self.panel_top <= INCIDENT_ANCHOR[1] <= self.panel_bottom + 2)

    def test_case1_secret_uses_the_bottom_region_below_the_panel(self):
        region = self.task._select_reward_region()
        self.assertIs(region, self.task.C_RANDOM_SAVE_BOTTOM)
        self.assertGreater(region.roi_front[1], self.panel_bottom)          # 整个区域都在面板下方

    def test_case1_session_anchors_never_land_on_the_panel_or_share_button(self):
        gray = cv2.cvtColor(self.bgr, cv2.COLOR_BGR2GRAY)
        region = self.task._select_reward_region()
        for _ in range(SAMPLES):
            context = _context()
            self.task._start_settlement_session(context, region, 'reward')
            x, y = context.settlement_anchor
            self.assertTrue(_in_roi((x, y), region.roi_front), (x, y))
            self.assertGreater(y, self.panel_bottom + 2, (x, y))           # 面板与「分享」按钮都在这条线以上
            self.assertGreaterEqual(gray[y, x], 30, (x, y))                # 落在地面上，不是面板的深色底

    def test_result_to_reward_switch_resamples_out_of_an_old_default_anchor(self):
        # 若先经过结果页（默认区采样），切到奖励页时旧锚点不在底部区内 → 强制重采样到底部区
        region = self.task._select_reward_region()
        for _ in range(200):
            context = _context()
            context.settlement_anchor, context.settlement_stage_name = INCIDENT_ANCHOR, 'generic_result'
            self.task._advance_settlement_anchor(context, region, 'reward')
            self.assertTrue(_in_roi(context.settlement_anchor, region.roi_front), context.settlement_anchor)
            self.assertGreater(context.settlement_anchor[1], self.panel_bottom + 2)


class GenericRewardRegionUnchangedTest(TestCase):
    @classmethod
    def setUpClass(cls):
        _Matching.runtime = ImageRuntime()
        _Matching.image = cv2.cvtColor(_load_bgr(), cv2.COLOR_BGR2RGB)
        cls.panel_top, cls.panel_bottom = _panel_box(_load_bgr())

    @classmethod
    def tearDownClass(cls):
        _Matching.runtime.shutdown()
        _Matching.runtime, _Matching.image = None, None

    def test_case2_generic_selection_on_the_same_frame_is_still_the_default_region(self):
        task = _Matching.__new__(_Matching)
        self.assertIs(task._select_reward_region(), task.C_RANDOM_DEFAULT)   # 奖励宝袋标志命中 → 默认区（行为不变）
        self.assertTrue(_in_roi(INCIDENT_ANCHOR, task.C_RANDOM_DEFAULT.roi_front))

    def test_case2_default_region_overlaps_the_panel_which_is_why_secret_needs_its_own(self):
        task = _Matching.__new__(_Matching)
        hits = 0
        for _ in range(SAMPLES):
            context = _context()
            task._start_settlement_session(context, task.C_RANDOM_DEFAULT, 'reward')
            x, y = context.settlement_anchor
            if self.panel_top <= y <= self.panel_bottom and 855 <= x <= 1245:
                hits += 1
        self.assertGreater(hits, 0)

    def test_case2_other_tasks_keep_the_generic_method(self):
        for task_cls in (GeneralBattle, RealmRaidTask, OrochiTask):
            with self.subTest(task=task_cls.__module__):
                self.assertIs(task_cls._select_reward_region, GeneralBattle._select_reward_region)
        self.assertIn('_select_reward_region', SecretTask.__dict__)
