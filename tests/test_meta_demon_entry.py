"""超鬼王庭院直达入口回归：假画面与虚拟时钟，不连接设备或识别服务。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image

from module.exception import GamePageUnknownError
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask
from tasks.Component.RightActivity.assets import RightActivityAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.matcher import collect_rule_images
from tasks.GameUi.session import NavigatorSession
from tasks.MetaDemon import page as pages
from tasks.MetaDemon.assets import MetaDemonAssets as A


ROOT = Path(__file__).resolve().parents[1]


class Frames:
    """截图才推进画面，独立次数哨兵防止错误循环；图像识别仅按资源身份返回。"""

    I_CHECK_MAIN = GameUiAssets.I_CHECK_MAIN

    def __init__(self, frames):
        self.frames = frames
        self.index = -1
        self.screenshots = 0
        self.clicks = []

    def screenshot(self):
        self.screenshots += 1
        if self.screenshots > 60:
            raise AssertionError('超鬼王入口测试截图超过60次')
        self.index = min(self.index + 1, len(self.frames) - 1)

    def appear(self, target, **kwargs):
        frame = self.frames[max(0, self.index)]
        if target is self.I_CHECK_MAIN:
            return frame.get('main', True)
        if target is A.I_MAIN_GOTO_ACT_2:
            return frame.get('new', False)
        if target is A.I_MAIN_GOTO_ACT:
            return frame.get('legacy', False)
        if target is RightActivityAssets.I_TOGGLE_BUTTON:
            return frame.get('toggle', False)
        return False

    def appear_then_click(self, target, **kwargs):
        if self.appear(target):
            self.clicks.append(target)
            return True
        return False


class Clock:
    def __init__(self, budget=100):
        self.now = 0
        self.budget = budget

    def sleep(self, delay):
        self.now += delay

    def timer(self, limit):
        deadline = self.now + min(limit, self.budget)
        return SimpleNamespace(start=lambda: SimpleNamespace(reached=lambda: self.now >= deadline))


def drive(frames, budget=100):
    task = Frames(frames)
    clock = Clock(budget)
    with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
        return pages.find_activity_entry(task), task


class EntryClickTest(TestCase):
    def test_new_entry_preferred_with_navigation_confirmation(self):
        task = Frames([{'new': True, 'legacy': True}])
        task.appear_then_click = Mock(wraps=task.appear_then_click)
        self.assertTrue(pages.goto_activity_entry(task))
        task.appear_then_click.assert_called_once_with(
            A.I_MAIN_GOTO_ACT_2, interval=1, policy=InteractionPolicy.NAVIGATION)

    def test_legacy_entry_is_tried_after_missing_new_entry(self):
        task = Frames([{'legacy': True}])
        task.appear_then_click = Mock(wraps=task.appear_then_click)
        self.assertTrue(pages.goto_activity_entry(task))
        self.assertEqual([c.args[0] for c in task.appear_then_click.call_args_list],
                         [A.I_MAIN_GOTO_ACT_2, A.I_MAIN_GOTO_ACT])
        self.assertTrue(all(c.kwargs['policy'] is InteractionPolicy.NAVIGATION
                            for c in task.appear_then_click.call_args_list))

    def test_no_entry_does_not_claim_a_click(self):
        task = Frames([{}])
        self.assertFalse(pages.goto_activity_entry(task))
        self.assertEqual(task.clicks, [])

    def test_entry_like_icon_off_courtyard_is_not_clicked(self):
        task = Frames([{'main': False, 'new': True}])
        self.assertFalse(pages.goto_activity_entry(task))
        self.assertEqual(task.clicks, [])

    def test_click_error_and_stop_propagate(self):
        for error in (RuntimeError('点击失败'), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                task = Frames([{'new': True}])
                task.appear_then_click = Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    pages.goto_activity_entry(task)

    def test_page_change_during_new_entry_confirmation_prevents_legacy_click(self):
        task = Frames([{'new': True}, {'main': False, 'legacy': True}])

        def confirm(target, **kwargs):
            task.screenshot()
            return False

        task.index = 0
        task.appear_then_click = Mock(side_effect=confirm)
        self.assertFalse(pages.goto_activity_entry(task))
        task.appear_then_click.assert_called_once()

    def test_real_primitive_rechecks_new_frame_and_uses_new_position(self):
        for disappears in (True, False):
            with self.subTest(disappears=disappears):
                task = Frames([{'new': True}, {'new': not disappears}])
                task.index = 0
                task.interval_timer = {}
                task.device = object()
                task.appear_then_click = BaseTask.appear_then_click.__get__(task)
                with patch('tasks.base_task.random_delay', return_value=0), \
                        patch('tasks.base_task.sleep'), \
                        patch('tasks.base_task.execute_single_click') as execute, \
                        patch.object(A.I_MAIN_GOTO_ACT_2, 'coord',
                                     side_effect=lambda: (100 + task.index, 200)) as coord:
                    self.assertEqual(pages.goto_activity_entry(task), not disappears)
                if disappears:
                    execute.assert_not_called()
                    coord.assert_not_called()
                else:
                    self.assertEqual(execute.call_count, 1)
                    self.assertEqual((execute.call_args.args[1].x, execute.call_args.args[1].y), (101, 200))
                    coord.assert_called_once()


class EntrySearchTest(TestCase):
    def test_visible_entry_needs_no_column_switch(self):
        for key in ('new', 'legacy'):
            with self.subTest(key=key):
                result, task = drive([{key: True, 'toggle': True}])
                self.assertTrue(result)
                self.assertEqual(task.clicks, [])
                self.assertEqual(task.screenshots, 1)

    def test_finds_entry_in_fresh_frame_after_switch(self):
        result, task = drive([{'toggle': True}, {'toggle': True}, {'new': True}])
        self.assertTrue(result)
        self.assertEqual(task.clicks, [RightActivityAssets.I_TOGGLE_BUTTON])
        self.assertEqual(task.screenshots, 3)

    def test_entry_appearing_during_settle_is_not_toggled_away(self):
        result, task = drive([{'toggle': True}, {'new': True, 'toggle': True}])
        self.assertTrue(result)
        self.assertEqual(task.clicks, [])

    def test_off_courtyard_returns_without_click_even_with_entry_like_icon(self):
        result, task = drive([{'main': False, 'new': True, 'toggle': True}])
        self.assertFalse(result)
        self.assertEqual(task.clicks, [])

    def test_leaving_courtyard_during_settle_prevents_switch(self):
        result, task = drive([{'toggle': True}, {'main': False, 'toggle': True}])
        self.assertFalse(result)
        self.assertEqual(task.clicks, [])

    def test_leaving_courtyard_after_switch_is_not_entry_success(self):
        result, task = drive([{'toggle': True}, {'toggle': True}, {'main': False, 'new': True}])
        self.assertFalse(result)
        self.assertEqual(len(task.clicks), 1)

    def test_no_entry_exits_after_eight_switches(self):
        task = Frames([{'toggle': True}])
        clock = Clock()
        with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
            with self.assertRaises(GamePageUnknownError):
                pages.find_activity_entry(task)
        self.assertEqual(len(task.clicks), 8)

    def test_missing_toggle_is_bounded_and_never_clicked(self):
        task = Frames([{}])
        clock = Clock()
        with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
            with self.assertRaises(GamePageUnknownError):
                pages.find_activity_entry(task)
        self.assertLessEqual(task.screenshots, 9)
        self.assertEqual(task.clicks, [])

    def test_toggle_disappearing_during_settle_is_not_clicked(self):
        task = Frames([{'toggle': True}, {}])
        clock = Clock()
        with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
            with self.assertRaises(GamePageUnknownError):
                pages.find_activity_entry(task)
        self.assertEqual(task.clicks, [])

    def test_time_budget_can_end_before_switch_budget(self):
        task = Frames([{'toggle': True}])
        clock = Clock(1.5)
        with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
            with self.assertRaisesRegex(GamePageUnknownError, '超时'):
                pages.find_activity_entry(task)
        self.assertEqual(len(task.clicks), 1)

    def test_expired_budget_never_takes_a_screenshot_or_click(self):
        task = Frames([{'toggle': True}])
        clock = Clock(0)
        with patch.object(pages, 'Timer', clock.timer), patch.object(pages.time, 'sleep', clock.sleep):
            with self.assertRaises(GamePageUnknownError):
                pages.find_activity_entry(task)
        self.assertEqual((task.screenshots, task.clicks), (0, []))

    def test_screenshot_error_and_stop_are_not_swallowed(self):
        for error in (RuntimeError('截图失败'), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                task = Frames([{}])
                task.screenshot = Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    pages.find_activity_entry(task)

    def test_recognition_error_is_not_swallowed(self):
        task = Frames([{}])
        task.appear = Mock(side_effect=RuntimeError('识别失败'))
        with self.assertRaisesRegex(RuntimeError, '识别失败'):
            pages.find_activity_entry(task)


class EntryNavigationTest(TestCase):
    def make_ui(self):
        ui = GameUi.__new__(GameUi)
        ui.navigator = NavigatorSession('MetaDemon')
        ui.navigator.bootstrap([pages.page_main, pages.page_meta_demon, pages.page_meta_demon_boss])
        return ui

    def test_real_route_enters_directly_then_reaches_boss(self):
        ui = self.make_ui()
        route = ui._build_path(ui.navigator.resolve_page(pages.page_main),
                               ui.navigator.resolve_page(pages.page_meta_demon_boss))
        self.assertEqual([edge.key for edge in route],
                         ['page_main->page_meta_demon', 'page_meta_demon->page_meta_demon_boss'])
        self.assertIs(route[0].action, pages.goto_activity_entry)

    def test_return_route_does_not_depend_on_old_activity_list(self):
        ui = self.make_ui()
        route = ui._build_path(ui.navigator.resolve_page(pages.page_meta_demon_boss),
                               ui.navigator.resolve_page(pages.page_main))
        self.assertEqual([edge.key for edge in route],
                         ['page_meta_demon_boss->page_meta_demon', 'page_meta_demon->page_main'])

    def test_main_page_title_is_not_used_as_the_enter_boss_click(self):
        edge = next(e for e in pages.page_meta_demon.transitions
                    if e.destination is pages.page_meta_demon_boss)
        self.assertIs(edge.action, A.I_MD_GOTO_BOSS)
        self.assertIsNot(edge.action, A.I_MD_CHECK_MAIN_PAGE)

    def test_entry_click_without_destination_confirmation_is_failure(self):
        ui = self.make_ui()
        edge = next(e for e in ui.navigator.resolve_page(pages.page_main).transitions
                    if e.key == 'page_main->page_meta_demon')
        ui._execute_action = Mock(return_value=True)
        ui._wait_for_destination = Mock(return_value=False)
        ui._run_hooks = Mock()
        ui._detect_current_page_with_fallback = Mock(return_value=edge.source)
        ui._mark_page_entered = Mock()
        self.assertFalse(ui._execute_transition(edge))
        ui._wait_for_destination.assert_called_once_with(edge.destination)
        ui._mark_page_entered.assert_not_called()
        self.assertIs(ui.navigator.current_page, edge.source)

    def test_activity_recognition_still_requires_its_positive_marker(self):
        self.assertEqual(list(collect_rule_images(pages.page_meta_demon.recognizer)),
                         [A.I_MD_CHECK_MAIN_PAGE])
        self.assertIn(pages.find_activity_entry, pages.page_meta_demon.on_enter_failure)


class EntryResourceTest(TestCase):
    def test_annotation_json_png_and_generated_assets_are_paired(self):
        folder = ROOT / 'tasks/MetaDemon/md'
        rows = json.loads((folder / 'image.json').read_text(encoding='utf-8'))
        for name in ('main_goto_act_2', 'main_goto_act', 'md_goto_boss'):
            with self.subTest(name=name):
                row = next(r for r in rows if r['itemName'] == name)
                rule = getattr(A, 'I_' + name.upper())
                self.assertEqual(Path(rule.file).parent.as_posix(), 'tasks/MetaDemon/md')
                self.assertEqual(tuple(rule.roi_front), tuple(map(int, row['roiFront'].split(','))))
                self.assertEqual(tuple(rule.roi_back), tuple(map(int, row['roiBack'].split(','))))
                self.assertEqual(rule.threshold, row['threshold'])
                with Image.open(folder / row['imageName']) as image:
                    self.assertEqual(image.size, tuple(rule.roi_front[2:]))

    def test_assets_match_generator_without_writing_other_tasks(self):
        from dev_tools.assets_extract import AssetsExtractor
        extractor = AssetsExtractor('tasks/MetaDemon')
        with patch.object(extractor, 'write_file'):
            extractor.extract()
        self.assertEqual(ast.dump(ast.parse((ROOT / 'tasks/MetaDemon/assets.py').read_text(encoding='utf-8'))),
                         ast.dump(ast.parse(extractor._result)))
