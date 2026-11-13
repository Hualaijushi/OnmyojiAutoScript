"""超鬼王本期截图配套检查，不依赖已撤回的纯循环实现。"""

from pathlib import Path
from unittest import TestCase


class RealScreenshotTest(TestCase):
    """直接调用生产匹配函数，不创建RPC客户端；自匹配不能当独立识别率证据。"""

    def match(self, rule, template=None):
        import numpy as np
        from PIL import Image
        from module.image.runtime import ImageRuntime
        root = Path(__file__).resolve().parents[1]
        with Image.open(root / 'tests/fixtures/meta_demon/boss_ready.png') as image:
            frame = np.array(image.convert('RGB'))
        with Image.open(root / (template or rule.file)) as image:
            target = np.array(image.convert('RGB'))
        runtime = ImageRuntime.__new__(ImageRuntime)
        return runtime._template_match_image(frame, target, list(rule.roi_back),
                                              rule.threshold, rule.name)

    def test_current_fire_template_matches_but_previous_one_does_not(self):
        from tasks.MetaDemon.assets import MetaDemonAssets as A
        found, score, roi = self.match(A.I_MD_FIRE)
        self.assertTrue(found)
        self.assertGreater(score, 0.99)
        old_found, old_score, _ = self.match(A.I_MD_FIRE, 'tests/fixtures/meta_demon/old_fire.png')
        self.assertFalse(old_found)
        self.assertLess(old_score, A.I_MD_FIRE.threshold)

    def test_real_boss_page_marker_matches(self):
        from tasks.MetaDemon.assets import MetaDemonAssets as A
        self.assertTrue(self.match(A.I_CHECK_BOSS_PAGE)[0])

    def test_empty_friend_list_in_real_frame_is_not_no_boss(self):
        from tasks.MetaDemon.assets import MetaDemonAssets as A
        self.assertFalse(self.match(A.I_MD_TICKET_EMPTY)[0])
