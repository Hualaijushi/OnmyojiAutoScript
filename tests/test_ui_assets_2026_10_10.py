# This Python file uses the following encoding: utf-8
"""2026-10-10 游戏 UI 更新：公共确认 / 取消 / 获得奖励 / 邀请勾选框等模板重截的资产回归。

当天更新后，标准双按钮弹窗的「确定 / 取消」、「获得奖励」标题、组队邀请的勾选框等都换了样式，
相关模板已按新版画面重截并更新 ROI。这里守三件事：

1. 资产契约：每个改过的条目 itemName 不变、资产名还在、PNG 尺寸放得进 roi_back；
   `assets.py` 与项目生成器输出逐字节一致（防止重演 `ui_reward → ui_reward_1` 导致 `I_UI_REWARD` 消失）。
2. 真实画面：用当天真实的标准双按钮弹窗（结界突破退出确认，两个场景）验证全部「确定 / 取消」系资产命中，
   无弹窗画面不命中。各弹窗的按钮像素位置一致，所以同一张画面能覆盖不同任务的拷贝。
3. 新版「获得奖励」：仓库里没有新版奖励弹窗的真实画面，只做契约检查和「现有画面不误命中」。
"""

import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np

from dev_tools.assets_extract import AssetsExtractor
from module.image.runtime import ImageRuntime
from tasks.AbyssShadows.assets import AbyssShadowsAssets
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.Component.ReplaceShikigami.assets import ReplaceShikigamiAssets
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from tasks.DailyTrifles.assets import DailyTriflesAssets
from tasks.DemonEncounter.assets import DemonEncounterAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.RealmRaid.assets import RealmRaidAssets

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / 'tests' / 'fixtures' / 'general_battle'
DIALOG_FRAMES = (FIX / 'exit_confirm_oas2_2026-10-10.png', FIX / 'exit_confirm_other_scene_2026-10-10.png')
NO_DIALOG_FRAMES = (FIX / 'no_dialog_battle_exit_visible_2026-10-07.png', FIX / 'no_dialog_realm_raid_list_2026-10-10.png')

# (json 文件, itemName, 资产对象) —— 2026-10-10 改过 PNG 或 ROI 的条目
CHANGED_ITEMS = [
    ('tasks/GlobalGame/ui/image.json', 'ui_confirm', GlobalGameAssets.I_UI_CONFIRM),
    ('tasks/GlobalGame/ui/image.json', 'ui_cancel', GlobalGameAssets.I_UI_CANCEL),
    ('tasks/GlobalGame/ui/image.json', 'ui_reward', GlobalGameAssets.I_UI_REWARD),
    ('tasks/GameUi/page/image_activity.json', 'activity_award', GameUiAssets.I_ACTIVITY_AWARD),
    ('tasks/GameUi/page/image_chess.json', 'chess_exit_confirm', GameUiAssets.I_CHESS_EXIT_CONFIRM),
    ('tasks/GameUi/page/image_chess.json', 'chess_exit_cancel', GameUiAssets.I_CHESS_EXIT_CANCEL),
    ('tasks/ActivityShikigami/as/page/image.json', 'activity_award', ActivityShikigamiAssets.I_ACTIVITY_AWARD),
    ('tasks/Component/SwitchSoul/ss/image.json', 'sou_switch_sure', SwitchSoulAssets.I_SOU_SWITCH_SURE),
    ('tasks/Component/GeneralInvite/gi/image.json', 'gi_sure', GeneralInviteAssets.I_GI_SURE),
    ('tasks/Component/GeneralInvite/gi/image.json', 'i_default', GeneralInviteAssets.I_I_DEFAULT),
    ('tasks/Component/GeneralInvite/gi/image.json', 'i_no_default', GeneralInviteAssets.I_I_NO_DEFAULT),
    ('tasks/Component/GeneralBattle/gb/image.json', 'exit_ensure', GeneralBattleAssets.I_EXIT_ENSURE),
    ('tasks/RealmRaid/res/image.json', 'fresh_ensure', RealmRaidAssets.I_FRESH_ENSURE),
    ('tasks/DemonEncounter/boss/image.json', 'boss_confirm', DemonEncounterAssets.I_BOSS_CONFIRM),
    ('tasks/AbyssShadows/res/image.json', 'ensure_button', AbyssShadowsAssets.I_ENSURE_BUTTON),
    ('tasks/AbyssShadows/res/image.json', 'start_ensure', AbyssShadowsAssets.I_START_ENSURE),
    ('tasks/DailyTrifles/dt/image_pickup_email.json', 'harvest_mail_confirm', DailyTriflesAssets.I_HARVEST_MAIL_CONFIRM),
    ('tasks/Component/ReplaceShikigami/rs/supplement.json', 'u_confirm_small', ReplaceShikigamiAssets.I_U_CONFIRM_SMALL),
]

# 标准双按钮弹窗右侧「确定」与左侧「取消」的全部拷贝
CONFIRM_RULES = [GlobalGameAssets.I_UI_CONFIRM, SwitchSoulAssets.I_SOU_SWITCH_SURE, GeneralInviteAssets.I_GI_SURE,
                 RealmRaidAssets.I_FRESH_ENSURE, DemonEncounterAssets.I_BOSS_CONFIRM, AbyssShadowsAssets.I_ENSURE_BUTTON,
                 AbyssShadowsAssets.I_START_ENSURE, GameUiAssets.I_CHESS_EXIT_CONFIRM, GeneralBattleAssets.I_EXIT_ENSURE]
CANCEL_RULES = [GlobalGameAssets.I_UI_CANCEL, GameUiAssets.I_CHESS_EXIT_CANCEL]
REWARD_RULES = [GlobalGameAssets.I_UI_REWARD, GameUiAssets.I_ACTIVITY_AWARD, ActivityShikigamiAssets.I_ACTIVITY_AWARD]

MODULES = ['tasks/GlobalGame', 'tasks/GameUi', 'tasks/ActivityShikigami', 'tasks/Component/SwitchSoul',
           'tasks/Component/GeneralInvite', 'tasks/Component/GeneralBattle', 'tasks/Component/ReplaceShikigami',
           'tasks/RealmRaid', 'tasks/DemonEncounter', 'tasks/AbyssShadows', 'tasks/DailyTrifles']


def _roi(text):
    return tuple(int(v) for v in text.split(','))


class UiAssetContractTest(TestCase):
    def test_changed_items_keep_their_item_name_and_match_the_asset(self):
        for json_path, item_name, rule in CHANGED_ITEMS:
            with self.subTest(item=item_name, json=json_path):
                data = json.loads((REPO / json_path).read_text(encoding='utf-8'))
                items = [it for it in data if it.get('itemName') == item_name]
                self.assertEqual(len(items), 1)
                item = items[0]
                self.assertTrue(rule.file.replace('\\', '/').endswith(f"{Path(json_path).parent.as_posix()}/{item['imageName']}"))
                self.assertEqual(tuple(rule.roi_front), _roi(item['roiFront']))
                self.assertEqual(tuple(rule.roi_back), _roi(item['roiBack']))

    def test_templates_fit_inside_their_search_area(self):
        for _, item_name, rule in CHANGED_ITEMS:
            with self.subTest(item=item_name):
                tpl = cv2.imdecode(np.fromfile(rule.file, dtype=np.uint8), -1)
                fx, fy, fw, fh = rule.roi_front
                bx, by, bw, bh = rule.roi_back
                self.assertTrue(bx <= fx and by <= fy and bx + bw >= fx + fw and by + bh >= fy + fh)
                self.assertLessEqual(tpl.shape[1], bw)
                self.assertLessEqual(tpl.shape[0], bh)

    def test_ui_reward_asset_still_exists_under_its_public_name(self):
        # 2026-10-10 曾把 itemName 改成 ui_reward_1，`I_UI_REWARD` 消失后 OAS 一启动就 AttributeError
        self.assertTrue(hasattr(GlobalGameAssets, 'I_UI_REWARD'))
        self.assertFalse(hasattr(GlobalGameAssets, 'I_UI_REWARD_1'))
        self.assertTrue(GlobalGameAssets.I_UI_REWARD.file.replace('\\', '/').endswith('tasks/GlobalGame/ui/ui_ui_reward.png'))
        import tasks.GameUi.default_pages  # noqa: F401  模块加载时就会读 GlobalGameAssets.I_UI_REWARD

    def test_assets_py_is_exactly_what_the_generator_produces(self):
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            for module in MODULES:
                with self.subTest(module=module):
                    ex = AssetsExtractor(str(REPO / module))
                    ex.write_file = lambda: None
                    ex.extract()
                    self.assertEqual(ex._result, (REPO / module / 'assets.py').read_bytes().decode('utf-8'))
        finally:
            os.chdir(cwd)


class _InProcessImageClient:
    """生产匹配入口（RuleImage.match → 图像服务）的进程内替身：直接调 ImageRuntime，不经 RPC。"""

    def __init__(self, runtime):
        self.runtime = runtime

    def match_rule(self, rule_data, image, frame_id=None, threshold=None):
        return self.runtime._match_rule_payload(image=image, rule_data=rule_data, threshold=threshold)


class UiAssetRecognitionTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = ImageRuntime()
        cls.patcher = patch('module.atom.image.get_image_client', return_value=_InProcessImageClient(cls.runtime))
        cls.patcher.start()
        cls.frames = {p: cv2.cvtColor(cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), -1)[:, :, :3], cv2.COLOR_BGR2RGB)
                      for p in DIALOG_FRAMES + NO_DIALOG_FRAMES}

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.runtime.shutdown()

    def score(self, rule, frame):
        return self.runtime._match_rule_payload(image=self.frames[frame], rule_data=rule.to_service_payload())

    def test_every_confirm_and_cancel_copy_matches_the_new_dialog(self):
        for frame in DIALOG_FRAMES:
            for rule in CONFIRM_RULES + CANCEL_RULES:
                with self.subTest(frame=frame.name, rule=rule.name):
                    res = self.score(rule, frame)
                    self.assertTrue(res['matched'])
                    self.assertGreaterEqual(res['score'], 0.9)

    def test_no_dialog_frames_do_not_match(self):
        for frame in NO_DIALOG_FRAMES:
            for rule in CONFIRM_RULES + CANCEL_RULES:
                with self.subTest(frame=frame.name, rule=rule.name):
                    res = self.score(rule, frame)
                    self.assertFalse(res['matched'])
                    self.assertLess(res['score'], 0.5)

    def test_reward_titles_do_not_fire_on_non_reward_frames(self):
        for frame in DIALOG_FRAMES + NO_DIALOG_FRAMES:
            for rule in REWARD_RULES:
                with self.subTest(frame=frame.name, rule=rule.name):
                    res = self.score(rule, frame)
                    self.assertFalse(res['matched'])
                    self.assertLess(res['score'], 0.5)
