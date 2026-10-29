# This Python file uses the following encoding: utf-8
"""道馆普通模式的特征测试（福利模式接入前后都必须成立）+ 福利开关接入 / 配置 / 活跃时长结算。

普通模式：福利开关关闭时，次数识别、放弃投票、next_run 排期、run 的入口路径都与原行为一致。
这些用例只固定「现有行为」，不改变它。
"""

import json
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.config.config_model import ConfigModel
from module.exception import TaskEnd
import tasks.Dokan.page as pages
from tasks.Dokan import script_task as dokan_task
from tasks.Dokan.config import Dokan, DokanConfig
from tasks.Dokan.script_task import ScriptTask

REPO = Path(__file__).resolve().parents[1]
_Base = dokan_task.datetime


def fixed_datetime(year, month, day, hour, minute):
    class Fixed(_Base):
        @classmethod
        def now(cls, tz=None):
            return _Base(year, month, day, hour, minute, 0)

    return Fixed


def make_task(*, dokan=None):
    task = ScriptTask.__new__(ScriptTask)
    dokan = dokan or Dokan()
    task.conf = dokan
    task.config = SimpleNamespace(model=SimpleNamespace(dokan=dokan), dokan=dokan, save=Mock())
    task.screenshot = Mock()
    return task


class RemainCountTest(unittest.TestCase):
    def count_for(self, visible):
        task = make_task()
        task.appear = lambda rule: rule is visible
        return task, task.update_remain_attack_count()

    def test_zero_done_one_two(self):
        for name, expected in (('I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO', 0), ('I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE', 0),
                               ('I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ONE', 1), ('I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_TWO', 2)):
            with self.subTest(name=name):
                task = make_task()
                visible = getattr(task, name)
                task.appear = lambda rule, v=visible: rule is v
                self.assertEqual(task.update_remain_attack_count(), expected)
                self.assertEqual(task.conf.attack_count_config.remain_attack_count, expected)

    def test_unknown_returns_minus_one_and_keeps_the_local_count(self):
        task = make_task()
        task.conf.attack_count_config.remain_attack_count = 2
        task.appear = lambda rule: False
        self.assertEqual(task.update_remain_attack_count(), -1)
        self.assertEqual(task.conf.attack_count_config.remain_attack_count, 2)


class NextRunTest(unittest.TestCase):
    def target(self, now, *, activated, skip_today=False, remain=2, daily=2):
        task = make_task()
        task.conf.attack_count_config.remain_attack_count = remain
        task.conf.attack_count_config.daily_attack_count = daily
        task.set_next_run = Mock()
        with patch.object(dokan_task, 'datetime', fixed_datetime(*now)):
            task.next_run(skip_today=skip_today, is_dokan_activated=activated)
        task.set_next_run.assert_called_once()
        return task.set_next_run.call_args.kwargs['target'], task

    def test_not_started_before_run_time_waits_for_run_time(self):
        target, _ = self.target((2026, 10, 26, 18, 30), activated=False)
        self.assertEqual((target.day, target.hour, target.minute), (26, 20, 0))

    def test_not_started_long_after_run_time_counts_as_done_for_today(self):
        target, _ = self.target((2026, 10, 26, 21, 30), activated=False)
        self.assertEqual((target.day, target.hour), (27, 20))

    def test_not_started_within_the_hour_retries_after_failure_interval(self):
        target, task = self.target((2026, 10, 26, 20, 30), activated=False)
        self.assertEqual(target, _Base(2026, 10, 26, 20, 30, 0) + task.conf.scheduler.failure_interval)

    def test_first_of_two_dokans_uses_failure_interval(self):
        target, task = self.target((2026, 10, 26, 20, 30), activated=True, remain=1, daily=2)
        self.assertEqual(target, _Base(2026, 10, 26, 20, 30, 0) + task.conf.scheduler.failure_interval)

    def test_finished_goes_to_the_next_day(self):
        target, _ = self.target((2026, 10, 26, 20, 30), activated=True, remain=0)
        self.assertEqual((target.day, target.hour), (27, 20))

    def test_friday_skips_to_monday(self):
        target, _ = self.target((2026, 10, 30, 12, 0), activated=False, skip_today=True)      # 周五
        self.assertEqual((target.month, target.day, target.hour), (11, 2, 20))


class AbandonVoteTest(unittest.TestCase):
    """普通模式 abandoned_toppa 的投票分支（含「保留赏金」）保持原样；福利模式不使用它。"""

    def test_title_present_votes_abandon(self):
        task = make_task()
        visible = {task.I_DOKAN_ABANDONED_TOPPA_TITLE, task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED}
        task.appear = lambda rule: rule in visible
        task.wait_until_appear = Mock()
        task.ui_click_until_disappear = Mock()
        task.abandoned_toppa()
        task.ui_click_until_disappear.assert_called_once_with(task.I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED)

    def test_title_absent_votes_keep_bounty_in_normal_mode(self):
        task = make_task()
        visible = {task.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY}
        task.appear = lambda rule: rule in visible
        task.wait_until_appear = Mock()
        task.ui_click_until_disappear = Mock()
        task.abandoned_toppa()
        task.ui_click_until_disappear.assert_called_once_with(task.I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY)


class RunEntryTest(unittest.TestCase):
    class Sentinel(Exception):
        pass

    def task(self, *, welfare):
        task = make_task()
        task.conf.dokan_config.monday_to_thursday = False
        task.conf.dokan_config.welfare_mode = welfare
        task.before_run = Mock()
        task.goto_page = Mock()
        return task

    def test_welfare_off_takes_the_ordinary_path_and_never_builds_the_welfare_runner(self):
        task = self.task(welfare=False)
        task.goto_page.side_effect = self.Sentinel
        with patch.object(dokan_task, 'WelfareDokan', side_effect=AssertionError('福利模式关闭时不得进入')):
            with self.assertRaises(self.Sentinel):
                task.run()
        self.assertIs(task.goto_page.call_args[0][0], pages.page_dokan_map)

    def test_welfare_on_hands_over_and_schedules_like_a_finished_dokan(self):
        task = self.task(welfare=True)
        task.set_next_run = Mock()
        runner = Mock()
        runner.run.return_value = 0
        with patch.object(dokan_task, 'WelfareDokan', return_value=runner) as factory, \
                patch.object(dokan_task, 'datetime', fixed_datetime(2026, 10, 26, 22, 0)):
            with self.assertRaises(TaskEnd):
                task.run()
        factory.assert_called_once_with(task)
        self.assertEqual(task.conf.attack_count_config.remain_attack_count, 0)
        task.goto_page.assert_called_once_with(pages.page_main)
        target = task.set_next_run.call_args.kwargs['target']
        self.assertEqual((target.day, target.hour), (27, 20))            # 次日运行时间，不是 failure_interval 重试

    def test_weekday_limit_still_applies_in_welfare_mode(self):
        task = self.task(welfare=True)
        task.conf.dokan_config.monday_to_thursday = True
        task.next_run = Mock()
        with patch.object(dokan_task, 'datetime', fixed_datetime(2026, 10, 30, 12, 0)), \
                patch.object(dokan_task, 'WelfareDokan', side_effect=AssertionError('周五不得进入')):
            with self.assertRaises(TaskEnd):
                task.run()
        task.next_run.assert_called_once_with(True)


class RunOnDokanMapTest(unittest.TestCase):
    """普通模式的建馆分支（福利模式接入前后都必须成立）：照旧调用无参的 `ensure_dokan_created()`，
    `try_start_dokan=False` 仍然直接按「未开启」退出，用户配置不被改写。"""

    def map_task(self, *, try_start, remain=2, created=True):
        dokan = Dokan()
        dokan.dokan_config.try_start_dokan = try_start
        task = make_task(dokan=dokan)
        task.found_dokan_cnt = 0
        task.appear = lambda rule: rule is task.I_RYOU_DOKAN_FINDING_DOKAN
        task.update_remain_attack_count = Mock(return_value=remain)
        task.ensure_dokan_created = Mock(return_value=created)
        task.find_dokan = Mock(return_value=False)
        return task

    def test_try_start_off_exits_before_any_create_attempt_and_keeps_the_config(self):
        task = self.map_task(try_start=False)
        with self.assertRaises(dokan_task.DokanNotStartedError):
            task.run_on_dokan_map()
        task.ensure_dokan_created.assert_not_called()
        self.assertFalse(task.conf.dokan_config.try_start_dokan)

    def test_try_start_on_checks_the_own_dokan_with_the_default_arguments(self):
        task = self.map_task(try_start=True)
        with self.assertRaises(dokan_task.DokanNotStartedError):          # find_dokan 返回 False → 未开启
            task.run_on_dokan_map()
        task.ensure_dokan_created.assert_called_once_with()               # 不带 strict，普通模式行为不变
        task.find_dokan.assert_called_once()

    def test_create_failure_stops_before_selecting_a_target(self):
        task = self.map_task(try_start=True, created=False)
        with self.assertRaises(dokan_task.DokanNotStartedError):
            task.run_on_dokan_map()
        task.find_dokan.assert_not_called()

    def test_no_chances_left_counts_as_finished_without_creating(self):
        task = self.map_task(try_start=True, remain=0)
        with self.assertRaises(dokan_task.DokanFinishedError):
            task.run_on_dokan_map()
        task.ensure_dokan_created.assert_not_called()


class ConfigTest(unittest.TestCase):
    def test_defaults_and_old_fields_unchanged(self):
        config = DokanConfig()
        self.assertFalse(config.welfare_mode)
        self.assertEqual(config.welfare_min_people, 100)
        for name, value in (('find_dokan_score', 4.6), ('min_people_num', -1), ('min_bounty', 0),
                            ('find_dokan_refresh_count', 7), ('try_start_dokan', False), ('monday_to_thursday', True)):
            self.assertEqual(getattr(config, name), value)

    def test_threshold_is_saved_strictly_and_a_bad_value_keeps_the_old_one(self):
        config = DokanConfig()
        config.welfare_min_people = 150
        for bad in (0, -5, 1.5, '100', True, None):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    config.welfare_min_people = bad
                self.assertEqual(config.welfare_min_people, 150)
        config.welfare_min_people = 1
        self.assertEqual(config.welfare_min_people, 1)

    def test_other_dokan_fields_keep_their_old_assignment_behaviour(self):
        config = DokanConfig()
        config.find_dokan_refresh_count = -3          # 旧行为：赋值不校验
        self.assertEqual(config.find_dokan_refresh_count, -3)

    def test_bad_threshold_through_the_save_entry_does_not_reset_the_group(self):
        with patch.object(ConfigModel, 'write_json'):
            model = ConfigModel()
            self.assertTrue(model.script_set_arg('Dokan', 'dokan_config', 'welfare_min_people', 120))
            self.assertTrue(model.script_set_arg('Dokan', 'dokan_config', 'find_dokan_score', 3.5))
            self.assertFalse(model.script_set_arg('Dokan', 'dokan_config', 'welfare_min_people', 1.5))
            self.assertFalse(model.script_set_arg('Dokan', 'dokan_config', 'welfare_min_people', 0))
            config = model.dokan.dokan_config
            self.assertEqual((config.welfare_min_people, config.find_dokan_score), (120, 3.5))

    def test_args_output_carries_the_new_fields_and_old_config_still_loads(self):
        with patch.object(ConfigModel, 'write_json'):
            model = ConfigModel()
            items = {item['name']: item for item in model.script_task('Dokan')['dokan_config']}
        self.assertEqual((items['welfare_mode']['type'], items['welfare_mode']['default']), ('boolean', False))
        self.assertEqual((items['welfare_min_people']['type'], items['welfare_min_people']['default']), ('integer', 100))
        self.assertEqual(items['welfare_min_people']['description'], 'welfare_min_people_help')
        data = Dokan().model_dump()
        data['dokan_config'].pop('welfare_mode')
        data['dokan_config'].pop('welfare_min_people')
        old = Dokan(**data)
        self.assertEqual((old.dokan_config.welfare_mode, old.dokan_config.welfare_min_people), (False, 100))

    def test_template_and_translations(self):
        template = json.loads((REPO / 'config' / 'template.json').read_text(encoding='utf-8'))
        section = template['dokan']['dokan_config']
        self.assertEqual((section['welfare_mode'], section['welfare_min_people']), (False, 100))
        for lang in ('zh-CN', 'en-US'):
            table = json.loads((REPO / 'assets' / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
            for key in ('welfare_mode', 'welfare_mode_help', 'welfare_min_people', 'welfare_min_people_help'):
                self.assertIn(key, table, (lang, key))
        zh = json.loads((REPO / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        self.assertIn('大于等于', zh['welfare_min_people_help'])


class ActiveSecondsTest(unittest.TestCase):
    """Script 的防沉迷活跃时长：任务内的业务等待被扣除，其他任务口径不变。"""

    def script(self):
        import script as script_mod
        script = script_mod.Script.__new__(script_mod.Script)
        script._active_date = script_mod.date.today()
        script._active_seconds_today = 0
        script.config = SimpleNamespace()
        return script_mod, script

    def test_excluded_seconds_are_subtracted_once(self):
        script_mod, script = self.script()
        script.config.__dict__['excluded_active_seconds'] = 600.0
        started = script_mod.datetime.now() - timedelta(seconds=900)
        script._add_active_seconds(started)
        self.assertAlmostEqual(script._active_seconds_today, 300, delta=2)
        self.assertNotIn('excluded_active_seconds', script.config.__dict__)

    def test_plain_tasks_count_their_full_wall_time(self):
        script_mod, script = self.script()
        started = script_mod.datetime.now() - timedelta(seconds=120)
        script._add_active_seconds(started)
        self.assertAlmostEqual(script._active_seconds_today, 120, delta=2)

    def test_exclusion_never_makes_the_total_negative(self):
        script_mod, script = self.script()
        script.config.__dict__['excluded_active_seconds'] = 5000.0
        script._add_active_seconds(script_mod.datetime.now() - timedelta(seconds=60))
        self.assertEqual(script._active_seconds_today, 0)


if __name__ == '__main__':
    unittest.main()
