"""多账号轮换复用原超鬼王流程的关键边界。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tasks.MetaDemon.config import MetaDemon, MetaDemonConfig
from tasks.MetaDemon.script_task import ScriptTask as MetaDemonTask
from tasks.MetaDemonRotation.config import MetaDemonRotation
from tasks.MetaDemonRotation.driver import RotationDriver
from tasks.MetaDemonRotation.script_task import fatigue_retry_only


class OriginalFlowTest(TestCase):
    def test_independent_defaults_and_config_values(self):
        rotation = MetaDemonRotation()
        self.assertEqual('4', rotation.rotation_play.fire_sequence)
        self.assertFalse(rotation.rotation_play.auto_tea)
        self.assertEqual('', rotation.rotation_play.synthesis_list)
        self.assertEqual(40, rotation.rotation_settings.battle_limit)
        ordinary = MetaDemon()
        rotation.rotation_play.fire_sequence = '5 6'
        self.assertEqual('1 2 3 4', ordinary.meta_demon_config.fire_sequence)

    def test_fatigue_wait_does_not_hide_other_failures(self):
        completed = SimpleNamespace(completed=True, reason='已达目标')
        fatigue = SimpleNamespace(completed=False, reason='疲劳不足')
        unknown = SimpleNamespace(completed=False, reason='鬼王状态未确认')
        self.assertTrue(fatigue_retry_only([completed, fatigue], 2))
        self.assertFalse(fatigue_retry_only([completed, fatigue], 3))
        self.assertFalse(fatigue_retry_only([fatigue, unknown], 2))
        self.assertFalse(fatigue_retry_only([completed], 1))

    def test_rotation_configuration_does_not_change_ordinary_task(self):
        ordinary = MetaDemon()
        rotation = MetaDemonRotation()
        rotation.rotation_play = type(rotation.rotation_play)(
            fire_sequence='5 6', auto_tea=True, synthesis_list='1 2', powerful_list='5')
        task = Mock()
        task.config.meta_demon_rotation = rotation
        task.before_run.side_effect = lambda: setattr(task, 'conf', ordinary)
        with patch('tasks.MetaDemonRotation.driver.deploy_rental', return_value='ready'):
            self.assertEqual('ready', RotationDriver.deploy_rental(task, 1))
        self.assertEqual('5 6', task.conf.meta_demon_config.fire_sequence)
        self.assertTrue(task.conf.meta_demon_config.auto_tea)
        self.assertEqual('1 2', task.conf.meta_demon_config.synthesis_list)
        self.assertEqual('5', task.conf.meta_demon_config.powerful_list)
        self.assertFalse(task.conf.switch_soul.enable)
        self.assertEqual('1 2 3 4', ordinary.meta_demon_config.fire_sequence)
        self.assertFalse(ordinary.meta_demon_config.auto_tea)

    def test_preparation_uses_original_summon_and_power_settings(self):
        task = Mock()
        task.conf.meta_demon_config = MetaDemonConfig(powerful_list='4')
        task.check_and_switch_ticket.return_value = True
        task.appear.return_value = True
        task.check_and_switch_powerful.return_value = True
        self.assertEqual('four_ready', RotationDriver.prepare_current_or_four_star(task))
        task.synthesis_boss_ticket.assert_called_once()
        task.check_and_switch_ticket.assert_called_once()
        task.sync_current_boss_type.assert_called_once()
        task.check_and_switch_powerful.assert_called_once()

    def test_original_summon_waits_for_challenge_without_reopening_queue(self):
        task = Mock()
        task.conf = MetaDemon()
        task.conf.meta_demon_config.fire_sequence = '4'
        task.State = SimpleNamespace(done=False, switch_soul_done=False)
        task.cur_boss_type = None
        names = ('I_MD_FIRE', 'I_MD_GET_BOSS', 'I_MD_TICKET_EMPTY', 'I_MD_SWITCH_TICKET',
                 'I_MD_ONE_STAR', 'I_MD_TWO_STARS', 'I_MD_THREE_STARS', 'I_MD_FOUR_STARS',
                 'I_MD_FIVE_STARS', 'I_MD_SIX_STARS', 'I_MD_CHECK_SELECTED')
        for name in names:
            setattr(task, name, Mock(name=name))
        task.I_MD_FOUR_STARS.roi_front = (557, 325, 69, 58)
        task.I_MD_CHECK_SELECTED.coord.return_value = (590, 295)
        scene = {'value': 'home'}
        actions = []

        def appear(target, **kwargs):
            if target is task.I_MD_FIRE:
                return scene['value'] == 'ready'
            if target is task.I_MD_GET_BOSS:
                return scene['value'] in ('queue', 'selected')
            if target is task.I_MD_FOUR_STARS:
                return scene['value'] in ('queue', 'selected')
            if target is task.I_MD_CHECK_SELECTED:
                return scene['value'] == 'selected'
            return False

        def click(target, **kwargs):
            actions.append(target)
            if target is task.I_MD_SWITCH_TICKET:
                scene['value'] = 'queue'
                return True
            if target is task.I_MD_FOUR_STARS:
                scene['value'] = 'selected'
                return True
            return False

        task.appear.side_effect = appear
        task.appear_then_click.side_effect = click
        task.ui_click_until_disappear.side_effect = lambda *args, **kwargs: scene.update(value='ready')
        self.assertTrue(MetaDemonTask.check_and_switch_ticket(task))
        self.assertEqual([task.I_MD_SWITCH_TICKET, task.I_MD_FOUR_STARS], actions)
        task.ui_click_until_disappear.assert_called_once_with(task.I_MD_GET_BOSS, interval=0.6)

    def test_full_fatigue_obeys_tea_setting_and_time_limit(self):
        task = Mock()
        task.rotation_started = 10
        task.conf.meta_demon_config = MetaDemonConfig()
        task.O_MD_FATIGUE.ocr_digit_counter.return_value = (100, 0, 100)
        with patch('tasks.MetaDemonRotation.driver.time.monotonic', return_value=20):
            self.assertEqual('unavailable', RotationDriver.fatigue_status(task))
            task.conf.meta_demon_config.auto_tea = True
            self.assertEqual('ready', RotationDriver.fatigue_status(task))
            task.conf.meta_demon_config = MetaDemonConfig(limit_time='00:00:05', auto_tea=True)
            self.assertEqual('time_limit', RotationDriver.fatigue_status(task))

    def test_unknown_popup_returns_without_clicking_challenge(self):
        task = Mock()
        task._meta_battle_started.return_value = False
        task.is_in_battle.return_value = False
        task.appear.return_value = False
        result = MetaDemonTask.start_battle(task, popup_handler=lambda: 'unknown', rotation_mode=True)
        self.assertEqual('popup_unknown', result)
        task.appear_then_click.assert_not_called()
