import unittest

from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.MultiAccountEvo.script_task import ScriptTask as MultiAccountEvoScriptTask


class MultiAccountEvoClickSafetyTest(unittest.TestCase):
    def test_common_left_click_area_remains_unchanged(self):
        self.assertEqual(
            GeneralBattleAssets.C_RANDOM_LEFT.roi_front,
            (17, 104, 192, 506),
        )

    def test_multi_account_settlement_uses_right_area_only(self):
        click = MultiAccountEvoScriptTask._multi_account_settlement_click()

        self.assertEqual(click.roi_front, (1185, 209, 87, 441))

    def test_multi_account_blocks_only_legacy_lower_keepalive(self):
        task = object.__new__(MultiAccountEvoScriptTask)
        task.I_GI_EMOJI_2 = object()
        target = task.I_GI_EMOJI_2

        self.assertFalse(task.appear_then_click(target))


if __name__ == '__main__':
    unittest.main()
