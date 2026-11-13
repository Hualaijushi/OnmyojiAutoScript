"""仅核对恢复后的功能界面、当前队列选项及可选星级功能。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GamePageUnknownError
from tasks.MetaDemon import script_task as mod
from tasks.MetaDemon.config import MetaDemon, BossType


class CompatibilityTest(TestCase):
    def task(self):
        task = mod.ScriptTask.__new__(mod.ScriptTask)
        task.conf = MetaDemon()
        task.State = SimpleNamespace(done=False, switch_soul_done=False)
        task.cur_boss_type = None
        task.device = SimpleNamespace(image='假画面')
        return task

    def test_optional_current_queue_summons_and_confirms_empty_without_selecting_stars(self):
        for frames, ready in ((['summon','confirm','fire'], True), (['empty','empty'],False)):
            with self.subTest(frames=frames):
                task = self.task(); state = {'i': -1}; clicks=[]
                names={id(task.I_MD_FIRE):'fire',id(task.I_MD_SUMMON_BOSS):'summon',
                       id(task.I_MD_GET_BOSS):'confirm',id(task.I_MD_TICKET_EMPTY):'empty'}
                task.screenshot=lambda: state.update(i=min(state['i']+1,len(frames)-1))
                task.appear=lambda rule,**kw: names.get(id(rule))==frames[max(0,state['i'])]
                def click(rule,**kw):
                    found=task.appear(rule)
                    if found:clicks.append(names[id(rule)])
                    return found
                task.appear_then_click=click
                task.sync_current_boss_type=Mock()
                task._meta_battle_started=lambda: False
                with patch.object(mod.time,'sleep'):
                    self.assertEqual(task.summon_current_queue(),ready)
                self.assertEqual(clicks,['summon','confirm'] if ready else [])
                self.assertEqual(task.State.done,not ready)

    def test_all_original_groups_remain_and_disabled_soul_does_not_navigate(self):
        from module.config.config_model import ConfigModel
        args=ConfigModel(config_name='case').script_task('MetaDemon')
        self.assertEqual(set(args),{'scheduler','meta_demon_config','switch_soul'})
        self.assertTrue({'fire_sequence','synthesis_list','powerful_list','auto_tea','use_current_queue'} <=
                        {x['name'] for x in args['meta_demon_config']})
        task=self.task();task.goto_page=Mock()
        self.assertFalse(task.conf.meta_demon_config.use_current_queue)
        self.assertFalse(task.conf.switch_soul.enable)
        self.assertTrue(task.check_and_switch_soul())
        task.goto_page.assert_not_called()

    def test_enabled_star_based_features_read_the_current_star_instead_of_guessing(self):
        task=self.task();task.conf.switch_soul.enable=True
        task.O_MD_BOSS_STAR=SimpleNamespace(ocr_digit=Mock(return_value=5))
        task.sync_current_boss_type()
        self.assertEqual(task.cur_boss_type,BossType.FIVE_STARS)
        task.O_MD_BOSS_STAR.ocr_digit.return_value=0
        with self.assertRaises(GamePageUnknownError):task.sync_current_boss_type()

    def test_summon_entered_prepare_hands_off_without_more_summon_clicks(self):
        task=self.task(); task.screenshot=Mock(); task._meta_battle_started=Mock(return_value=True)
        task.appear_then_click=Mock(); task.sync_current_boss_type=Mock()
        self.assertTrue(task.summon_current_queue())
        task.appear_then_click.assert_not_called()
        task.sync_current_boss_type.assert_not_called()

    def test_battle_appears_during_power_check_does_not_click_switch(self):
        task=self.task(); task.screenshot=Mock(); task._meta_battle_started=Mock(side_effect=[False,True])
        task.appear=Mock(return_value=True); task.appear_then_click=Mock()
        self.assertTrue(task.check_and_switch_powerful())
        task.appear_then_click.assert_not_called()

    def test_normal_power_switch_and_unknown_state_are_bounded(self):
        task=self.task(); task.screenshot=Mock(); task._meta_battle_started=Mock(return_value=False)
        task.appear=Mock(side_effect=lambda rule: rule is task.I_MD_FIRE or rule is task.I_MD_DISABLE_POWERFUL_FIRE)
        task.appear_then_click=Mock()
        self.assertTrue(task.check_and_switch_powerful())
        task.appear_then_click.assert_not_called()
        task.appear=Mock(side_effect=lambda rule: rule is task.I_MD_FIRE)
        task.appear_then_click=Mock(return_value=False)
        with patch.object(mod.time,'sleep'):
            with self.assertRaisesRegex(GamePageUnknownError,'强力追击状态未确认'):
                task.check_and_switch_powerful()
        self.assertEqual(task.appear_then_click.call_count,60)
