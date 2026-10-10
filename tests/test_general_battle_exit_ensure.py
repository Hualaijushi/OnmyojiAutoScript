# This Python file uses the following encoding: utf-8
"""GeneralBattle `I_EXIT_ENSURE`（「确认退出战斗吗？」弹窗的「确定」）2026-10-10 新 UI 适配回归。

事故（2026-10-10 15:29~15:31，结界突破退四）：游戏更新后退出确认弹窗改版，旧模板在旧 ROI 内只有
-0.066 分；`exit_battle()` 认不出弹窗，每 6 秒再点一次 `GB_EXIT`，oas2 GameStuck、oas1
GameTooManyClick。新模板从 oas2 事故原帧按新按钮位置 (664,406,179,66) 裁出，ROI 同步更新。

这里只用真实画面：事故原帧、另一场景的同一弹窗（手动截图）作正样本；没有弹窗的战斗页（2026-10-07）
和结界突破列表页作负样本。仓库里没有「准备页但没有弹窗」的真实画面，所以负样本用这两张代替。
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from dev_tools.assets_extract import AssetsExtractor
from module.image.runtime import ImageRuntime
from tasks.Component.GeneralBattle import general_battle as gb
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralBattle.general_battle import GeneralBattle

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / 'tests' / 'fixtures' / 'general_battle'
DIALOG_OAS2 = FIX / 'exit_confirm_oas2_2026-10-10.png'
DIALOG_OTHER_SCENE = FIX / 'exit_confirm_other_scene_2026-10-10.png'
NO_DIALOG_BATTLE = FIX / 'no_dialog_battle_exit_visible_2026-10-07.png'
NO_DIALOG_LIST = FIX / 'no_dialog_realm_raid_list_2026-10-10.png'
OLD_TEMPLATE = FIX / 'old_gb_exit_ensure_2023.png'

NEW_ROI = (664, 406, 179, 66)
OLD_ROI = (674, 388, 135, 63)
FRAME_SECONDS = 0.35
MAX_SHOTS = 200


def _load_rgb(path):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), -1)[:, :, :3], cv2.COLOR_BGR2RGB)


def _strip_trailing_ws(text):
    # synevo 分支提交的 assets.py 去掉了生成器写出的行尾空格与文件末尾空行（git diff --check 规范），只按内容比较
    return '\n'.join(line.rstrip() for line in text.splitlines()).rstrip('\n')


class _InProcessImageClient:
    """生产匹配入口（RuleImage.match → 图像服务）的进程内替身：直接调 ImageRuntime，不经 RPC。"""

    def __init__(self, runtime):
        self.runtime = runtime

    def match_rule(self, rule_data, image, frame_id=None, threshold=None):
        return self.runtime._match_rule_payload(image=image, rule_data=rule_data, threshold=threshold)


class _RealMatcherCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = ImageRuntime()
        cls.patcher = patch('module.atom.image.get_image_client', return_value=_InProcessImageClient(cls.runtime))
        cls.patcher.start()
        cls.frames = {p: _load_rgb(p) for p in (DIALOG_OAS2, DIALOG_OTHER_SCENE, NO_DIALOG_BATTLE, NO_DIALOG_LIST)}

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.runtime.shutdown()

    def setUp(self):
        # `RuleImage.match` 命中时会改写共享资产的 roi_front：每个用例结束都还原，不污染其它测试
        self.saved = {n: list(getattr(GeneralBattleAssets, n).roi_front) for n in ('I_EXIT', 'I_EXIT_ENSURE')}

    def tearDown(self):
        for n, roi in self.saved.items():
            getattr(GeneralBattleAssets, n).roi_front = list(roi)

    def score(self, rule, frame):
        return self.runtime._match_rule_payload(image=self.frames[frame], rule_data=rule.to_service_payload())


# --------------------------------------------------------------------------------------
# 一、资产契约：名字 / 路径 / 阈值不变，ROI 是新位置，生成文件与 json 一致
# --------------------------------------------------------------------------------------

class ExitEnsureAssetContractTest(TestCase):
    def test_asset_keeps_its_name_file_and_threshold(self):
        rule = GeneralBattleAssets.I_EXIT_ENSURE
        self.assertTrue(rule.file.replace('\\', '/').endswith('tasks/Component/GeneralBattle/gb/gb_exit_ensure.png'))
        self.assertEqual(rule.name, 'GB_EXIT_ENSURE')   # 点击记录 / 日志里的 control_name 不变
        self.assertEqual(rule.threshold, 0.8)            # 不靠降阈值过关

    def test_roi_is_the_new_button_and_search_area_contains_it(self):
        rule = GeneralBattleAssets.I_EXIT_ENSURE
        self.assertEqual(tuple(rule.roi_front), NEW_ROI)
        bx, by, bw, bh = rule.roi_back
        x, y, w, h = NEW_ROI
        self.assertTrue(bx <= x and by <= y and bx + bw >= x + w and by + bh >= y + h)
        # 搜索区不能伸到左侧「取消」按钮（x≈437~615）
        self.assertGreater(bx, 615)

    def test_template_size_matches_roi(self):
        tpl = cv2.imdecode(np.fromfile(GeneralBattleAssets.I_EXIT_ENSURE.file, dtype=np.uint8), -1)
        self.assertEqual((tpl.shape[1], tpl.shape[0]), NEW_ROI[2:])

    def test_json_item_name_is_unchanged(self):
        # 防止重演 I_UI_REWARD → I_UI_REWARD_1：itemName 一改，assets.py 里的公共属性就消失
        data = json.loads((REPO / 'tasks/Component/GeneralBattle/gb/image.json').read_text(encoding='utf-8'))
        items = [it for it in data if it.get('imageName') == 'gb_exit_ensure.png']
        self.assertEqual([it['itemName'] for it in items], ['exit_ensure'])

    def test_assets_py_is_exactly_what_the_generator_produces(self):
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            ex = AssetsExtractor(str(REPO / 'tasks' / 'Component' / 'GeneralBattle'))
            ex.write_file = lambda: None
            ex.extract()
        finally:
            os.chdir(cwd)
        on_disk = (REPO / 'tasks' / 'Component' / 'GeneralBattle' / 'assets.py').read_bytes().decode('utf-8')
        self.assertEqual(_strip_trailing_ws(ex._result), _strip_trailing_ws(on_disk))


# --------------------------------------------------------------------------------------
# 二、真实画面识别（生产 ImageRuntime）
# --------------------------------------------------------------------------------------

class ExitEnsureRecognitionTest(_RealMatcherCase):
    def test_incident_frame_is_recognised_with_margin(self):
        res = self.score(GeneralBattleAssets.I_EXIT_ENSURE, DIALOG_OAS2)
        self.assertTrue(res['matched'])
        self.assertGreaterEqual(res['score'], 0.9)

    def test_same_dialog_over_another_scene_is_recognised(self):
        res = self.score(GeneralBattleAssets.I_EXIT_ENSURE, DIALOG_OTHER_SCENE)
        self.assertTrue(res['matched'])
        self.assertGreaterEqual(res['score'], 0.9)

    def test_no_dialog_frames_are_not_recognised(self):
        for frame in (NO_DIALOG_BATTLE, NO_DIALOG_LIST):
            res = self.score(GeneralBattleAssets.I_EXIT_ENSURE, frame)
            self.assertFalse(res['matched'], frame.name)
            self.assertLess(res['score'], 0.5, frame.name)

    def test_old_template_fails_on_the_incident_frame(self):
        """特征化：旧模板 + 旧 ROI 在新弹窗上不命中（事故的直接原因）。"""
        rule = GeneralBattleAssets.I_EXIT_ENSURE
        with patch.object(rule, 'file', str(OLD_TEMPLATE)), patch.object(rule, 'roi_front', list(OLD_ROI)), \
                patch.object(rule, 'roi_back', list(OLD_ROI)):
            res = self.score(rule, DIALOG_OAS2)
        self.assertFalse(res['matched'])
        self.assertLess(res['score'], 0.5)

    def test_exit_button_is_still_visible_behind_the_dialog(self):
        # 弹窗下面的 GB_EXIT 仍然能识别到：所以确认键认不出时，exit_battle 会去重复点 GB_EXIT
        self.assertTrue(self.score(GeneralBattleAssets.I_EXIT, DIALOG_OAS2)['matched'])


# --------------------------------------------------------------------------------------
# 三、退出事务：真实 exit_battle()，按点击推进的真实画面
# --------------------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _ExitWorld:
    """战斗页（有 GB_EXIT、无弹窗）--点 GB_EXIT--> 退出确认弹窗 --点 GB_EXIT_ENSURE--> 离开战斗。"""

    FRAMES = {'battle': NO_DIALOG_BATTLE, 'dialog': DIALOG_OAS2, 'left': NO_DIALOG_LIST}

    def __init__(self, case, start='battle'):
        self.case = case
        self.state = start
        self.shots = 0
        self.clicks = []
        self.clock = _Clock()
        task = GeneralBattle.__new__(GeneralBattle)
        task.device = SimpleNamespace(click=Mock(side_effect=self._click), image=None, image_frame_id=None,
                                      get_image_batch_cache=Mock(return_value=None))
        task.interval_timer = {}
        task.screenshot = self.screenshot
        self.task = task

    def _click(self, x, y, control_name=None):
        self.clicks.append(control_name)
        if control_name == 'GB_EXIT' and self.state == 'battle':
            self.state = 'dialog'
        elif control_name == 'GB_EXIT_ENSURE' and self.state == 'dialog':
            self.state = 'left'

    def screenshot(self):
        if self.shots >= MAX_SHOTS:
            raise AssertionError(f'screenshot budget exhausted ({MAX_SHOTS}), clicks={self.clicks[-6:]}')
        if self.shots:
            self.clock.now += FRAME_SECONDS
        self.shots += 1
        self.task.device.image = self.case.frames[self.FRAMES[self.state]]
        return self.task.device.image

    def current_page(self, _task):
        # 退出确认后游戏进入失败结算；这里只需要让 exit_battle 的循环在「已离开」时结束
        return gb.page_battle_result if self.state == 'left' else None

    def run(self, skip_first=True):
        with patch('module.base.timer.time', self.clock), \
                patch.object(gb.GameUi, 'get_current_page', self.current_page):
            return self.task.exit_battle(skip_first=skip_first)


class ExitBattleTransactionTest(_RealMatcherCase):
    def test_exit_then_confirm_then_leave(self):
        world = _ExitWorld(self)
        self.assertTrue(world.run())
        self.assertEqual(world.clicks, ['GB_EXIT', 'GB_EXIT_ENSURE'])
        self.assertEqual(world.state, 'left')

    def test_dialog_already_open_is_confirmed_without_clicking_exit_again(self):
        # 弹窗已经出现、GB_EXIT 在弹窗下面仍可见：只点确定，绝不再点 GB_EXIT
        world = _ExitWorld(self, start='dialog')
        self.assertTrue(world.run())
        self.assertEqual(world.clicks, ['GB_EXIT_ENSURE'])

    def test_old_template_reproduces_the_incident(self):
        """特征化：旧模板 + 旧 ROI 时，弹窗出现后仍每 6 秒点一次 GB_EXIT，直到外层保护兜底。"""
        rule = GeneralBattleAssets.I_EXIT_ENSURE
        world = _ExitWorld(self)
        with patch.object(rule, 'file', str(OLD_TEMPLATE)), patch.object(rule, 'roi_front', list(OLD_ROI)), \
                patch.object(rule, 'roi_back', list(OLD_ROI)):
            with self.assertRaises(AssertionError):
                world.run()
        self.assertNotIn('GB_EXIT_ENSURE', world.clicks)
        self.assertGreaterEqual(world.clicks.count('GB_EXIT'), 5)
        self.assertEqual(world.state, 'dialog')
