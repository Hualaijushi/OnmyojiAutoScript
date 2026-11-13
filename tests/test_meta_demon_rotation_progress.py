"""账号轮换次数与中断边界。"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np

from tasks.MetaDemonRotation.config import MetaDemonRotation
from tasks.MetaDemonRotation.accounts import accounts_for_range
from tasks.MetaDemonRotation.engine import run_account
from tasks.MetaDemonRotation.progress import RotationProgress, RotationProgressError, account_identity
from tasks.MetaDemonRotation.rotation import run_rotation
from tasks.MetaDemonRotation.driver import RotationDriver
from tasks.MetaDemon.script_task import ScriptTask as MetaDemonTask
from tasks.MetaDemonRotation.rental_prompt import (
    CHECKBOX, CONFIRM, TITLE, checkbox_state, handle_rental_prompt, title_state,
)
from tasks.MetaDemonRotation.rental import DEPLOY, ENTRY, deploy_rental
from module.interaction_policy import InteractionPolicy


class RentalEntryTest(TestCase):
    def test_opens_preset_bar_then_selects_rental_and_deploys(self):
        task = Mock()
        task.I_CHECK_BOSS_PAGE = object()
        panel = {'open': False}

        def appear(target):
            if target is DEPLOY:
                return panel['open']
            return target is task.I_CHECK_BOSS_PAGE and not panel['open']

        def click_when_visible(target, **kwargs):
            if target is ENTRY:
                self.assertEqual(InteractionPolicy.NAVIGATION, kwargs.get('policy'))
                panel['open'] = True
                return True
            if target is DEPLOY:
                panel['open'] = False
                return True
            raise AssertionError('不应点击其他入口')

        task.appear.side_effect = appear
        task.appear_then_click.side_effect = click_when_visible
        with patch('tasks.MetaDemonRotation.rental.selected_border', return_value=True), patch(
            'tasks.MetaDemonRotation.rental.time.sleep'):
            self.assertEqual('ready', deploy_rental(task, 1))
        targets = [call.args[0] for call in task.appear_then_click.call_args_list]
        self.assertEqual([ENTRY, DEPLOY], targets)
        self.assertEqual(2, task.click.call_count)
        self.assertEqual((500, 235, 110, 48), task.click.call_args_list[0].args[0].roi_front)
        self.assertEqual((645, 235, 300, 30), task.click.call_args_list[1].args[0].roi_front)

    def test_unopened_panel_stops_without_selecting_team(self):
        task = Mock()
        task.appear.return_value = False
        task.appear_then_click.return_value = False
        clock = SimpleNamespace(monotonic=Mock(side_effect=[0, 0, 13]), sleep=Mock())
        with patch('tasks.MetaDemonRotation.rental.time', clock):
            self.assertEqual('unknown', deploy_rental(task, 1))
        task.appear_then_click.assert_called_once_with(
            ENTRY, interval=1, policy=InteractionPolicy.NAVIGATION,
        )
        task.click.assert_not_called()

    def test_missing_rental_row_stops_before_deploy(self):
        task = Mock()
        task.appear.return_value = True
        task.appear_then_click.return_value = True
        with patch('tasks.MetaDemonRotation.rental.selected_border', return_value=False), patch(
            'tasks.MetaDemonRotation.rental.time.sleep'
        ):
            self.assertEqual('unknown', deploy_rental(task, 3))
        self.assertEqual(2, task.click.call_count)
        self.assertNotIn(DEPLOY, [call.args[0] for call in task.appear_then_click.call_args_list])


class RentalPromptTest(TestCase):
    def make_image(self, white_pixels=0):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        # 使用显式坐标修改，避免非连续切片产生临时副本。
        for index in range(white_pixels):
            image[378 + index // 22, 573 + index % 22] = 240
        return image

    def test_title_and_checkbox_uncertainty(self):
        self.assertEqual('present', title_state(' 是否使用租借队伍进行挑战？ '))
        self.assertEqual('unknown', title_state('租借队伍挑战'))
        self.assertEqual('absent', title_state('其他确认弹窗'))
        self.assertEqual('unchecked', checkbox_state(self.make_image()))
        self.assertEqual('checked', checkbox_state(self.make_image(20)))
        self.assertEqual('unknown', checkbox_state(self.make_image(8)))
        self.assertEqual('unknown', checkbox_state(np.zeros((10, 10, 3), dtype=np.uint8)))

    def test_unchecked_then_checked_and_confirmed_once(self):
        task = Mock()
        task.device.image = self.make_image()
        task.screenshot.side_effect = lambda: setattr(task.device, 'image', self.make_image(20))
        with patch.object(TITLE, 'ocr_single', return_value='是否使用租借队伍进行挑战？'), patch(
            'tasks.MetaDemonRotation.rental_prompt.time.sleep'
        ):
            self.assertEqual('handled', handle_rental_prompt(task))
            self.assertEqual([CHECKBOX, CONFIRM], [call.args[0] for call in task.click.call_args_list])
            self.assertEqual('waiting', handle_rental_prompt(task, confirm_attempted=True))
            self.assertEqual(2, task.click.call_count)

    def test_already_checked_and_unknown_do_not_toggle(self):
        task = Mock()
        task.device.image = self.make_image(20)
        with patch.object(TITLE, 'ocr_single', return_value='是否使用租借队伍进行挑战？'):
            self.assertEqual('handled', handle_rental_prompt(task))
            task.click.assert_called_once_with(CONFIRM)
            task.click.reset_mock()
            task.device.image = self.make_image(8)
            self.assertEqual('unknown', handle_rental_prompt(task))
            task.click.assert_not_called()

    def test_other_popup_is_never_confirmed(self):
        task = Mock()
        task.device.image = self.make_image(20)
        with patch.object(TITLE, 'ocr_single', return_value='其他确认弹窗'):
            self.assertEqual('absent', handle_rental_prompt(task))
        task.click.assert_not_called()

    def test_no_popup_preserves_original_battle_counting(self):
        task = Mock()
        task._meta_battle_started.side_effect = [False, True]
        task.is_in_battle.return_value = False
        task.total_count = 0
        task.cur_boss_type = None
        task.I_MD_DRINK_TEA = object()
        task.I_MD_FIRE = object()
        task.appear.return_value = False
        entered = Mock()
        result = MetaDemonTask.start_battle(task, on_entered=entered, popup_handler=lambda: 'absent',
                                            rotation_mode=True)
        self.assertEqual('finished', result)
        entered.assert_called_once_with()
        task.appear_then_click.assert_called_once_with(task.I_MD_FIRE, interval=.8)
        task.run_general_battle.assert_called_once()
        self.assertEqual(1, task.total_count)

    def test_rotation_delegates_challenge_to_original_flow(self):
        task = Mock()
        task.I_CHECK_BOSS_PAGE = object()
        task.appear.return_value = True
        task.start_battle.return_value = 'finished'
        entered = Mock()
        self.assertTrue(RotationDriver.challenge(task, entered))
        kwargs = task.start_battle.call_args.kwargs
        self.assertIs(entered, kwargs['on_entered'])
        self.assertTrue(kwargs['rotation_mode'])
        self.assertTrue(callable(kwargs['popup_handler']))


class RotationProgressTest(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = account_identity('oas3', 1, 'person', 'server', 'character')
        self.store = RotationProgress(self.root, 'oas3', day='2026-11-13')

    def update(self, action, *, account='A01', identity=None, target=40):
        return self.store.update(account, identity or self.identity, action, target=target)

    def test_independent_instance_ranges_include_19_and_20(self):
        source = SimpleNamespace(account_list=[SimpleNamespace(account=f'account{n}', svr='server',
                                  character=f'character{n}') for n in range(1, 21)])
        a = accounts_for_range('oas3', source, 11, 20)
        b = accounts_for_range('oas4', source, 1, 10)
        self.assertEqual([f'A{n:02d}' for n in range(11, 21)], [account.account_id for account in a])
        self.assertEqual([f'B{n:02d}' for n in range(1, 11)], [account.account_id for account in b])
        self.assertTrue(all(account.enabled for account in a + b))

    def test_missing_account_is_logged_and_next_account_continues(self):
        source = [SimpleNamespace(account='person', svr='server', character='character'), None,
                  SimpleNamespace(account='other', svr='server', character='character2')]
        accounts = accounts_for_range('oas3', source, 1, 3)
        switcher = Mock()
        switcher.ensure_account.return_value.success = True
        driver = Mock()
        driver.deploy_rental.return_value = 'unavailable'
        results = run_rotation(accounts, switcher, self.store, lambda _: driver,
                               rental_team=1, battle_limit=40)
        self.assertEqual(['A01', 'A02', 'A03'], [result.account_id for result in results])
        self.assertEqual('账号资料不完整，跳过', results[1].reason)
        self.assertIsNone(results[1].entered)
        self.assertEqual(2, switcher.ensure_account.call_count)

    def test_range_configuration_defaults_and_invalid_ranges(self):
        from pydantic import ValidationError
        config = MetaDemonRotation()
        self.assertEqual((1, 18), (config.rotation_settings.account_start, config.rotation_settings.account_end))
        with self.assertRaises(ValidationError):
            type(config.rotation_settings)(account_start=11, account_end=10)
        with self.assertRaises(ValidationError):
            type(config.rotation_settings)(account_start=20)
        for kwargs in ({'account_start': 0}, {'account_end': 21}):
            with self.assertRaises(ValidationError):
                type(config.rotation_settings)(**kwargs)
        with self.assertRaises(ValueError):
            accounts_for_range('oas3', [], 0, 20)

    def test_range_change_keeps_completed_account_progress(self):
        account = SimpleNamespace(instance='oas3', position=1, login_account='person', server='server',
                                  character='character', account_id='A01', enabled=True)
        self.update('begin', target=1)
        self.update('entered', target=1)
        self.update('finished', target=1)
        before = self.store.path.read_bytes()
        switcher = Mock()
        result = run_rotation([account], switcher, self.store, lambda _: Mock(),
                              rental_team=1, battle_limit=1)
        self.assertTrue(result[0].completed)
        switcher.ensure_account.assert_not_called()
        self.assertEqual(before, self.store.path.read_bytes())

    def test_battle_count_is_per_account_and_defaults_are_disabled(self):
        config = MetaDemonRotation()
        self.assertFalse(config.scheduler.enable)
        self.assertEqual((1, 40), (config.rotation_settings.rental_team, config.rotation_settings.battle_limit))
        self.update('begin')
        self.assertEqual(1, self.update('entered')['entered'])
        self.assertEqual('pending', self.update('finished')['status'])
        self.assertEqual(0, self.update('read', account='A02')['entered'])

    def test_inflight_restart_does_not_begin_or_count_twice(self):
        self.update('begin')
        restarted = RotationProgress(self.root, 'oas3', day='2026-11-13')
        self.assertEqual('pending', restarted.update('A01', self.identity, 'read', target=40)['phase'])
        with self.assertRaises(RotationProgressError):
            restarted.update('A01', self.identity, 'begin', target=40)
        restarted.update('A01', self.identity, 'entered', target=40)
        with self.assertRaises(RotationProgressError):
            restarted.update('A01', self.identity, 'entered', target=40)
        self.assertEqual(1, restarted.update('A01', self.identity, 'finished', target=40)['entered'])

    def test_target_completion_and_identity_mismatch_are_preserved(self):
        self.update('begin', target=1)
        self.update('entered', target=1)
        self.assertEqual('completed', self.update('finished', target=1)['status'])
        before = self.store.path.read_bytes()
        with self.assertRaises(RotationProgressError):
            self.update('begin', target=1)
        with self.assertRaises(RotationProgressError):
            self.update('read', identity='different', target=1)
        self.assertEqual(before, self.store.path.read_bytes())

    def test_current_boss_then_four_star_count_battles(self):
        driver = Mock()
        driver.deploy_rental.return_value = 'ready'
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.side_effect = ['current', 'current', 'four_ready']
        driver.challenge.side_effect = lambda entered: (entered(), True)[1]
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=1, battle_limit=3)
        self.assertTrue(result.completed)
        self.assertEqual(3, result.entered)
        self.assertEqual(3, driver.challenge.call_count)
        driver.deploy_rental.assert_called_once_with(1)

    def test_unavailable_rental_skips_without_battle(self):
        driver = Mock()
        driver.deploy_rental.return_value = 'unavailable'
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=2, battle_limit=40)
        self.assertFalse(result.completed)
        self.assertEqual(0, result.entered)
        self.assertEqual('租借队伍不可用', result.reason)
        driver.challenge.assert_not_called()

    def test_ambiguous_battle_never_restarted_as_fresh(self):
        driver = Mock()
        driver.deploy_rental.return_value = 'ready'
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.return_value = 'four_ready'
        driver.challenge.return_value = False
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=1, battle_limit=40)
        self.assertFalse(result.completed)
        self.assertEqual('pending', self.update('read')['phase'])
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=1, battle_limit=40)
        self.assertFalse(result.completed)
        self.assertEqual(1, driver.challenge.call_count)

    def test_unconfirmed_rental_prompt_stops_without_counting(self):
        driver = Mock()
        driver.deploy_rental.return_value = 'ready'
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.return_value = 'current'
        driver.challenge.return_value = 'popup_unknown'
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=1, battle_limit=40)
        self.assertEqual('租借确认弹窗状态未确认，需人工核实', result.reason)
        self.assertEqual(0, result.entered)
        self.assertEqual('pending', self.update('read')['phase'])

    def test_confirmed_fatigue_without_entry_does_not_count(self):
        driver = Mock()
        driver.deploy_rental.return_value = 'ready'
        driver.fatigue_status.return_value = 'ready'
        driver.prepare_current_or_four_star.return_value = 'current'
        driver.challenge.return_value = 'fatigue'
        result = run_account(driver, self.store, account_id='A01', identity=self.identity,
                             rental_team=1, battle_limit=40)
        self.assertEqual(('疲劳不足', 0), (result.reason, result.entered))
        self.assertEqual('idle', self.update('read')['phase'])

    def test_unknown_rental_stops_before_switching_next_account(self):
        first = SimpleNamespace(instance='oas3', position=1, login_account='person', server='server',
                                character='character', account_id='A01')
        second = SimpleNamespace(instance='oas3', position=2, login_account='other', server='server',
                                 character='character2', account_id='A02')
        switcher = Mock()
        switcher.ensure_account.return_value.success = True
        driver = Mock()
        driver.deploy_rental.return_value = 'unknown'
        result = run_rotation([first, second], switcher, self.store, lambda _: driver,
                              rental_team=1, battle_limit=40)
        self.assertEqual('租借队伍状态未确认', result[0].reason)
        switcher.ensure_account.assert_called_once_with(first)

    def test_missing_four_star_closes_queue_and_switches_to_next_account(self):
        driver = Mock()
        driver.I_CHECK_BOSS_PAGE = object()
        driver.check_and_switch_ticket.return_value = False
        driver.appear.return_value = True
        self.assertEqual('four_unavailable', RotationDriver.prepare_current_or_four_star(driver))
        driver.synthesis_boss_ticket.assert_called_once_with()
        driver.check_and_switch_ticket.assert_called_once()

        first = SimpleNamespace(instance='oas3', position=1, login_account='person', server='server',
                                character='character', account_id='A01')
        second = SimpleNamespace(instance='oas3', position=2, login_account='other', server='server',
                                 character='character2', account_id='A02')
        switcher = Mock()
        switcher.ensure_account.return_value.success = True
        ready = Mock()
        ready.deploy_rental.return_value = 'ready'
        ready.fatigue_status.return_value = 'ready'
        ready.prepare_current_or_four_star.return_value = 'four_unavailable'
        results = run_rotation([first, second], switcher, self.store, lambda _: ready,
                               rental_team=1, battle_limit=40)
        self.assertEqual(2, switcher.ensure_account.call_count)
        self.assertEqual(['未识别到可召唤的目标鬼王'] * 2, [item.reason for item in results])

    def test_rotation_skips_completed_and_continues_after_unavailable_team(self):
        first = SimpleNamespace(instance='oas3', position=1, login_account='person', server='server',
                                character='character', account_id='A01')
        second = SimpleNamespace(instance='oas3', position=2, login_account='other', server='server',
                                 character='character2', account_id='A02')
        self.update('begin', target=1)
        self.update('entered', target=1)
        self.update('finished', target=1)
        switcher = Mock()
        switcher.ensure_account.return_value.success = True
        driver = Mock()
        driver.deploy_rental.return_value = 'unavailable'
        results = run_rotation([first, second], switcher, self.store, lambda _: driver,
                               rental_team=1, battle_limit=1)
        self.assertEqual([(True, '今日已达目标'), (False, '租借队伍不可用')],
                         [(item.completed, item.reason) for item in results])
        switcher.ensure_account.assert_called_once_with(second)

    def test_rotation_never_switches_after_unconfirmed_inflight_battle(self):
        first = SimpleNamespace(instance='oas3', position=1, login_account='person', server='server',
                                character='character', account_id='A01')
        self.update('begin')
        switcher = Mock()
        result = run_rotation([first], switcher, self.store, lambda _: Mock(), rental_team=1, battle_limit=40)
        self.assertFalse(result[0].completed)
        switcher.ensure_account.assert_not_called()
