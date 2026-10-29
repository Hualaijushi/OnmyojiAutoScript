# This Python file uses the following encoding: utf-8
"""式神活动 → 爬塔 → 体力：可配置随机战斗次数区间 [ap_limit, ap_limit_max] 回归护栏。

执行类用例走真实的 ScriptTask.run / prepare_next_action / record_action /
_record_climb_consumption，只替身随机源和游戏叶节点；不手工给目标赋值。
"""

import copy
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from module.config.config_model import ConfigModel
from module.exception import RequestHumanTakeover
from tasks.ActivityShikigami.args_layout import build_args_layout
from tasks.ActivityShikigami.config import ActivityShikigami, BATTLE_TYPES, GeneralConfig
from tasks.ActivityShikigami.script_task import ScriptTask

TASK = 'ActivityShikigami'
RANDOM = 'tasks.ActivityShikigami.base_act.random_int'


def make_task(**general):
    t = ScriptTask.__new__(ScriptTask)
    t.conf = ActivityShikigami(general_config=general)
    t.action_count = {name: 0 for name in BATTLE_TYPES}
    t.ap_target = None
    t.current_action_type = ''
    t.activity_time_reached = False
    t._fatigue_owns_macro_idle = True
    t.start_time = datetime.now()
    t.climb_pending_consumption = {n: 0 for n in ('pass', 'ap', 'boss', 'ap100', 'penta_pass')}
    t.climb_consumable_count = {n: -1 for n in ('pass', 'ap', 'boss', 'ap100', 'penta_pass')}
    t.penta_pass_active = False
    return t


def run_whole(t, record=None):
    """跑真实的 ScriptTask.run，玩法叶节点替身并按顺序记录当时看到的目标。"""
    record = [] if record is None else record
    t.before_run = Mock()
    t.finish_activity_task = Mock()
    t.run_rich_man = Mock(side_effect=lambda: record.append(('rich_man', t.ap_target)))
    t.run_fakegod = Mock(side_effect=lambda: record.append(('fakegod', t.ap_target)))
    t.run_climb = Mock(side_effect=lambda: record.append(('climb', t.ap_target)))
    t.run()
    return record


class Base(TestCase):
    def setUp(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.tmp = tempfile.mkdtemp(prefix='oas_aprange_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, 'config'))
        os.chdir(self.tmp)

    def write(self, general=None, name='case', drop=(), top=None):
        data = ConfigModel().model_dump(mode='json')
        data.pop('config_name', None)
        g = data['activity_shikigami']['general_config']
        g.update(general or {})
        for key in drop:
            g.pop(key, None)
        if top is not None:
            data = top
        path = Path(self.tmp, 'config', f'{name}.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    @staticmethod
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest(), os.stat(path).st_mtime_ns

    def general(self, name='case'):
        return ConfigModel(name).activity_shikigami.general_config

    def saved_general(self, name='case'):
        data = json.loads(Path(self.tmp, 'config', f'{name}.json').read_text(encoding='utf-8'))
        return data['activity_shikigami']['general_config']


# ------------------------------------------------------------------ 配置兼容
class ConfigCompatTest(Base):
    def test_legacy_fixed_n_is_n_to_n(self):
        self.write({'ap_limit': 120}, drop=('ap_limit_max',))
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max), (120, 120))
        self.assertIsNone(g.ap_range_error())

    def test_legacy_zero_is_zero_to_zero(self):
        self.write({'ap_limit': 0}, drop=('ap_limit_max',))
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max), (0, 0))
        self.assertIsNone(g.ap_range_error())
        self.assertEqual(g.climb_sequence_v, [])

    def test_explicit_zero_max_differs_from_missing(self):
        self.write({'ap_limit': 100, 'ap_limit_max': 0})
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max), (100, 0))
        self.assertIn('100～0', g.ap_range_error())
        self.write({'ap_limit': 100}, drop=('ap_limit_max',))
        self.assertEqual(self.general().ap_limit_max, 100)

    def test_old_migration_paths_keep_fixed_semantics(self):
        legacy = {'activity_shikigami': {'general_climb': {'ap_limit': 80, 'pass_limit': 0}}}
        self.write(top=legacy)
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max), (80, 80))
        self.assertEqual(g.task_sequence, '爬塔')
        legacy_rich = {'rich_man': {'scheduler': {'enable': True}, 'run_config': {'throw_limit': 5}},
                       'activity_shikigami': {'general_climb': {'ap_limit': 0}}}
        self.write(top=legacy_rich, name='case2')
        g2 = self.general('case2')
        self.assertEqual((g2.ap_limit, g2.ap_limit_max, g2.throw_limit), (0, 0, 5))

    def test_load_and_get_do_not_write_the_file(self):
        path = self.write({'ap_limit': 120}, drop=('ap_limit_max',))
        before = self.digest(path)
        with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('读取不得写配置')):
            model = ConfigModel('case')
            args = model.script_task(TASK)
            model.script_task_layout(TASK)
        self.assertEqual(self.digest(path), before)
        self.assertNotIn('ap_limit_max', self.saved_general())
        item = {i['name']: i for i in args['general_config']}['ap_limit_max']
        self.assertEqual((item['value'], item['default'], item['type']), (120, 0, 'integer'))

    def test_legacy_then_lowering_min_keeps_old_value_as_max_and_can_widen(self):
        self.write({'ap_limit': 120}, drop=('ap_limit_max',))
        model = ConfigModel('case')
        self.assertTrue(model.script_set_arg(TASK, 'general_config', 'ap_limit', 100))
        g = self.general()
        # 上限不是「永远跟随下限」：已经按旧固定次数落成 120，之后可以独立修改
        self.assertEqual((g.ap_limit, g.ap_limit_max), (100, 120))
        self.assertTrue(ConfigModel('case').script_set_arg(TASK, 'general_config', 'ap_limit_max', 140))
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max), (100, 140))
        self.assertIsNone(g.ap_range_error())

    def test_field_by_field_edit_in_either_order(self):
        for order in (('ap_limit', 100, 'ap_limit_max', 140), ('ap_limit_max', 140, 'ap_limit', 100)):
            with self.subTest(order=order):
                self.write({'ap_limit': 10, 'ap_limit_max': 30})
                model = ConfigModel('case')
                # 中间状态（如 100～30）允许保存，不卡住后面一步
                self.assertTrue(model.script_set_arg(TASK, 'general_config', order[0], order[1]))
                self.assertTrue(ConfigModel('case').script_set_arg(TASK, 'general_config', order[2], order[3]))
                g = self.general()
                self.assertEqual((g.ap_limit, g.ap_limit_max), (100, 140))
                self.assertIsNone(g.ap_range_error())

    def test_bad_values_rejected_and_nothing_is_lost(self):
        self.write({'ap_limit': 100, 'ap_limit_max': 140, 'throw_limit': 7, 'task_sequence': '爬塔,大富翁'})
        model = ConfigModel('case')
        for bad in (-1, 1.5, '12', None, True):
            with self.subTest(bad=bad):
                self.assertFalse(model.script_set_arg(TASK, 'general_config', 'ap_limit_max', bad))
                self.assertFalse(model.script_set_arg(TASK, 'general_config', 'ap_limit', bad))
        g = self.general()
        self.assertEqual((g.ap_limit, g.ap_limit_max, g.throw_limit, g.task_sequence), (100, 140, 7, '爬塔,大富翁'))
        saved = self.saved_general()
        self.assertEqual((saved['ap_limit'], saved['ap_limit_max']), (100, 140))

    def test_other_integer_fields_keep_their_old_save_behaviour(self):
        general = GeneralConfig()
        general.throw_limit = -3   # 旧行为：不在赋值时校验，本轮不改
        self.assertEqual(general.throw_limit, -3)
        with self.assertRaises(ValidationError):
            general.ap_limit = -3
        self.assertEqual(general.ap_limit, 0)

    def test_range_error_messages_are_chinese_with_actual_values(self):
        for low, high in ((0, 50), (100, 50), (120, 0)):
            with self.subTest(low=low, high=high):
                msg = GeneralConfig(ap_limit=low, ap_limit_max=high).ap_range_error()
                self.assertIn(f'{low}～{high}', msg)
                self.assertIn('1 ≤ 最少 ≤ 最多', msg)
        for low, high in ((0, 0), (1, 1), (100, 140), (120, 120)):
            self.assertIsNone(GeneralConfig(ap_limit=low, ap_limit_max=high).ap_range_error())

    def test_defaults_and_old_field_names_unchanged(self):
        d = GeneralConfig().model_dump()
        self.assertEqual(list(d)[:4], ['task_sequence', 'throw_limit', 'ap_limit', 'ap_limit_max'])
        self.assertEqual((d['ap_limit'], d['ap_limit_max']), (0, 0))
        for key in ('pass_limit', 'boss_limit', 'ap100_limit', 'fakegod_limit', 'throw_limit'):
            self.assertEqual(d[key], 0)


# ------------------------------------------------------------------ 执行
class DrawTest(TestCase):
    def test_both_ends_are_reachable_and_bounds_passed_to_random(self):
        for stub in (100, 140):
            with self.subTest(stub=stub), patch(RANDOM, return_value=stub) as rnd:
                t = make_task(ap_limit=100, ap_limit_max=140)
                self.assertEqual(t.action_limit('ap'), stub)
                rnd.assert_called_once_with(100, 140)

    def test_fixed_range_does_not_sample(self):
        with patch(RANDOM) as rnd:
            t = make_task(ap_limit=120, ap_limit_max=120)
            self.assertEqual(t.action_limit('ap'), 120)
        rnd.assert_not_called()

    def test_legacy_n_behaves_exactly_like_old_fixed_limit(self):
        with patch(RANDOM) as rnd:
            t = make_task(ap_limit=3)
            self.assertEqual(t.action_limit('ap'), 3)
            self.assertEqual(t.conf.general_config.climb_sequence_v, ['ap'])
        rnd.assert_not_called()

    def test_disabled_zero_range_never_runs_and_never_samples(self):
        with patch(RANDOM) as rnd:
            t = make_task(ap_limit=0, ap_limit_max=0, task_sequence='爬塔')
            self.assertEqual(t.action_limit('ap'), 0)
            self.assertFalse(t.prepare_next_action('ap'))
            self.assertEqual(t.conf.general_config.task_sequence_v, [])
        rnd.assert_not_called()

    def test_drawn_once_across_entries_exit_checks_and_logs(self):
        with patch(RANDOM, return_value=126) as rnd:
            t = make_task(ap_limit=100, ap_limit_max=140)
            for _ in range(5):
                self.assertTrue(t.prepare_next_action('ap'))
                t.record_action('ap')
                t.action_limit('ap')
        self.assertEqual(rnd.call_count, 1)
        self.assertEqual(t.ap_target, 126)

    def test_real_exit_check_stops_exactly_at_the_target(self):
        with patch(RANDOM, return_value=3):
            t = make_task(ap_limit=1, ap_limit_max=5)
            entered = 0
            while t.prepare_next_action('ap'):
                t.record_action('ap')
                entered += 1
                self.assertLess(entered, 50)
        self.assertEqual(entered, 3)

    def test_log_message(self):
        with patch(RANDOM, return_value=126), patch('tasks.ActivityShikigami.base_act.logger') as log:
            make_task(ap_limit=100, ap_limit_max=140).action_limit('ap')
        log.info.assert_any_call('体力爬塔本次目标：126 次，配置区间：100～140 次')

    def test_target_is_not_written_back_to_config(self):
        with patch(RANDOM, return_value=126):
            t = make_task(ap_limit=100, ap_limit_max=140)
            before = t.conf.model_dump_json()
            t.action_limit('ap')
        self.assertEqual(t.conf.model_dump_json(), before)

    def test_time_limit_still_stops_before_target(self):
        with patch(RANDOM, return_value=100):
            t = make_task(ap_limit=100, ap_limit_max=140)
            t.start_time = datetime.now() - timedelta(hours=2)
            self.assertFalse(t.prepare_next_action('ap'))
            self.assertEqual(t.action_count['ap'], 0)

    def test_penta_pass_still_counts_one_battle(self):
        with patch(RANDOM, return_value=100):
            t = make_task(ap_limit=100, ap_limit_max=140)
            t.penta_pass_active = True
            t.climb_consumable_count['penta_pass'] = 3
            t._record_climb_consumption('ap')
            t.record_action('ap')
        # 一场开五倍券的战斗：体力消耗快照 5、五倍券消耗 1，但进入战斗的计数只 +1
        self.assertEqual(t.climb_pending_consumption['ap'], 5)
        self.assertEqual(t.climb_pending_consumption['penta_pass'], 1)
        self.assertEqual(t.action_count['ap'], 1)
        self.assertEqual(t.action_limit('ap'), 100)


class RunLifecycleTest(TestCase):
    def test_target_fixed_before_other_plays_and_unchanged_after(self):
        with patch(RANDOM, return_value=126) as rnd:
            t = make_task(task_sequence='大富翁,爬塔', throw_limit=5, ap_limit=100, ap_limit_max=140)
            record = run_whole(t)
        self.assertEqual(record, [('rich_man', 126), ('climb', 126)])
        self.assertEqual(rnd.call_count, 1)

    def test_next_fresh_execution_draws_again(self):
        with patch(RANDOM, side_effect=[110, 130]) as rnd:
            first = make_task(task_sequence='爬塔', ap_limit=100, ap_limit_max=140)
            second = make_task(task_sequence='爬塔', ap_limit=100, ap_limit_max=140)
            r1, r2 = run_whole(first), run_whole(second)
        self.assertEqual((r1, r2), ([('climb', 110)], [('climb', 130)]))
        self.assertEqual(rnd.call_count, 2)
        self.assertEqual(first.ap_target, 110)

    def test_same_execution_recovery_inside_run_keeps_target(self):
        """同一个任务对象内部的恢复（资源不足换下一项、重新进入爬塔等）不重抽。"""
        with patch(RANDOM, return_value=126) as rnd:
            t = make_task(task_sequence='爬塔', ap_limit=100, ap_limit_max=140)
            run_whole(t)
            t.run_climb = Mock(side_effect=lambda: t.climb_ap_target())
            t.run()
            t.run()
        self.assertEqual(rnd.call_count, 1)

    def test_climb_not_selected_is_not_enabled_by_the_range(self):
        with patch(RANDOM) as rnd:
            t = make_task(task_sequence='大富翁', throw_limit=5, ap_limit=100, ap_limit_max=140)
            record = run_whole(t)
        self.assertEqual(record, [('rich_man', None)])
        rnd.assert_not_called()

    def test_other_play_limits_are_unchanged(self):
        with patch(RANDOM) as rnd:
            t = make_task(throw_limit=4, pass_limit=3, boss_limit=2, ap100_limit=1, fakegod_limit=6)
            self.assertEqual(
                [t.action_limit(n) for n in ('rich_man', 'pass', 'boss', 'ap100', 'fakegod')],
                [4, 3, 2, 1, 6],
            )
            self.assertEqual(t.conf.general_config.climb_sequence_v, ['pass', 'boss', 'ap100'])
        rnd.assert_not_called()

    def test_ap_joins_climb_sequence_in_ui_order(self):
        g = GeneralConfig(ap_limit=100, ap_limit_max=140, pass_limit=2, boss_limit=1)
        self.assertEqual(g.climb_sequence_v, ['ap', 'pass', 'boss'])

    def test_invalid_range_is_refused_before_any_game_action(self):
        for low, high in ((0, 50), (100, 50), (120, 0)):
            with self.subTest(low=low, high=high), patch(RANDOM) as rnd:
                t = make_task(task_sequence='爬塔', ap_limit=low, ap_limit_max=high)
                t.before_run = Mock()
                t.run_climb = Mock()
                with self.assertRaises(RequestHumanTakeover) as ctx:
                    t.run()
                self.assertIn(f'{low}～{high}', str(ctx.exception))
                t.before_run.assert_not_called()
                t.run_climb.assert_not_called()
                rnd.assert_not_called()


# ------------------------------------------------------------------ 接口
class InterfaceTest(Base):
    def test_get_and_layout_never_sample(self):
        self.write({'ap_limit': 100, 'ap_limit_max': 140, 'task_sequence': '爬塔'})
        with patch(RANDOM) as rnd, patch('module.base.utils.random.random_int') as rnd2:
            model = ConfigModel('case')
            for _ in range(3):
                model.script_task(TASK)
                model.script_task_layout(TASK)
        rnd.assert_not_called()
        rnd2.assert_not_called()

    def test_layout_range_refs_resolve_and_do_not_duplicate(self):
        self.write({'ap_limit': 100, 'ap_limit_max': 140, 'task_sequence': '爬塔'})
        model = ConfigModel('case')
        args = model.script_task(TASK)
        layout = model.script_task_layout(TASK)
        self.assertEqual(layout['version'], 1)
        names = {(g, i['name']) for g, items in args.items() for i in items}
        battles = {b['key']: b for p in layout['plays'] for b in p['battles']}
        ap = battles['ap']
        rng = ap['range']
        self.assertEqual(rng['min'], {'group': 'general_config', 'argument': 'ap_limit'})
        self.assertEqual(rng['max'], {'group': 'general_config', 'argument': 'ap_limit_max'})
        self.assertEqual(rng['min'], ap['limit'])
        for ref in (rng['min'], rng['max']):
            self.assertIn((ref['group'], ref['argument']), names)
        for key, battle in battles.items():
            if key != 'ap':
                self.assertNotIn('range', battle)

        # 旧前端（不认识 range）数到的引用：无重复，且不含 ap_limit_max → 它会作为普通字段出现
        old_refs = [layout['selector']] + layout['common']
        for play in layout['plays']:
            old_refs += play['extra']
            for battle in play['battles']:
                old_refs += [battle['limit'], *battle['soul']]
        keys = [(r['group'], r['argument']) for r in old_refs]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertNotIn(('general_config', 'ap_limit_max'), keys)
        # 新前端：min 与 limit 是同一个参数，只数一次；max 只被 range 引用
        new_keys = set(keys) | {('general_config', 'ap_limit_max')}
        self.assertEqual(len(new_keys), len(keys) + 1)

    def test_stripping_range_leaves_the_old_layout_shape(self):
        layout = build_args_layout(ActivityShikigami())
        for play in layout['plays']:
            for battle in play['battles']:
                battle.pop('range', None)
                self.assertEqual(
                    set(battle),
                    {'key', 'title', 'initial_expanded', 'limit', 'soul', 'battle_group'},
                )

    def test_initial_expanded_follows_range_upper_bound(self):
        legacy = build_args_layout(ActivityShikigami(general_config={'task_sequence': '爬塔', 'ap_limit': 5}))
        ap = [b for p in legacy['plays'] for b in p['battles'] if b['key'] == 'ap'][0]
        self.assertTrue(ap['initial_expanded'])
        off = build_args_layout(ActivityShikigami(general_config={'task_sequence': '爬塔'}))
        ap = [b for p in off['plays'] for b in p['battles'] if b['key'] == 'ap'][0]
        self.assertFalse(ap['initial_expanded'])

    def test_translations_exist_for_new_keys(self):
        repo = Path(__file__).resolve().parents[1]
        for lang in ('zh-CN', 'en-US'):
            table = json.loads((repo / 'assets' / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
            for key in ('ap_limit_max', 'ap_limit_help', 'ap_limit_max_help',
                        'activity_ap_range_min', 'activity_ap_range_max'):
                self.assertIn(key, table, (lang, key))
        zh = json.loads((repo / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        self.assertEqual(zh['activity_ap_range_min'], '最少战斗次数')
        self.assertEqual(zh['activity_ap_range_max'], '最多战斗次数')

    def test_other_tasks_unchanged(self):
        self.write()
        model = ConfigModel('case')
        for task in ('Orochi', 'GlobalGame', 'Script'):
            before = copy.deepcopy(model.script_task(task))
            self.assertEqual(model.script_task_layout(task), {})
            self.assertEqual(model.script_task(task), before)
