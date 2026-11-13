# This Python file uses the following encoding: utf-8
"""式神活动配置页展示信息（/args/layout）回归护栏。

展示信息只引用 /args 里已有的 (group, argument)，不改字段、不写配置、不影响执行。
"""

import asyncio
import copy
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from module.config.config_model import ConfigModel
from tasks.ActivityShikigami.args_layout import build_args_layout
from tasks.ActivityShikigami.config import ActivityShikigami, ACTIVITY_NAME_ALIASES

TASK = 'ActivityShikigami'
BATTLES = ('rich_man', 'ap', 'pass', 'boss', 'ap100', 'fakegod')


def _items(result, group):
    return {item['name']: item for item in result[group]}


def _all_refs(layout):
    refs = [layout['selector']]
    refs += layout['common']
    for play in layout['plays']:
        refs += play['extra']
        for battle in play['battles']:
            refs.append(battle['limit'])
            refs += battle['soul']
    return refs


class LayoutBase(TestCase):
    def setUp(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        self.tmp = tempfile.mkdtemp(prefix='oas_layout_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, 'config'))
        os.chdir(self.tmp)

    def write(self, general=None, name='case', raw=None):
        data = ConfigModel().model_dump(mode='json')
        data.pop('config_name', None)
        if general:
            data['activity_shikigami']['general_config'].update(general)
            # 这些用例模拟的是体力区间出现之前的旧配置文件：不带 ap_limit_max
            if 'ap_limit_max' not in general:
                data['activity_shikigami']['general_config'].pop('ap_limit_max', None)
        if raw is not None:
            data = raw
        path = Path(self.tmp, 'config', f'{name}.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    @staticmethod
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest(), os.stat(path).st_mtime_ns


class LayoutContentTest(LayoutBase):
    def test_options_and_aliases(self):
        self.write()
        layout = ConfigModel('case').script_task_layout(TASK)
        self.assertEqual([o['value'] for o in layout['selector']['options']], ['大富翁', '爬塔', '伪神降临'])
        self.assertEqual(layout['selector']['aliases'], ACTIVITY_NAME_ALIASES)
        self.assertEqual(layout['selector']['separator'], ',')

    def test_old_order_is_reported_not_normalised(self):
        self.write({'task_sequence': 'fakegod, 爬塔 ,richman,climb'})
        layout = ConfigModel('case').script_task_layout(TASK)
        self.assertEqual(layout['selector']['selected'], ['伪神降临', '爬塔', '大富翁'])
        self.assertEqual(layout['selector']['invalid'], [])

    def test_invalid_entry_reported_without_raising(self):
        self.write({'task_sequence': '爬塔,乱写'})
        layout = ConfigModel('case').script_task_layout(TASK)
        self.assertEqual(layout['selector']['selected'], ['爬塔'])
        self.assertEqual(layout['selector']['invalid'], ['乱写'])

    def test_field_ownership_for_all_six_battles(self):
        self.write()
        model = ConfigModel('case')
        args = model.script_task(TASK)
        layout = model.script_task_layout(TASK)
        plays = {p['key']: p for p in layout['plays']}
        self.assertEqual([b['key'] for b in plays['climb']['battles']], ['ap', 'pass', 'boss', 'ap100'])
        self.assertEqual([b['key'] for b in plays['rich_man']['battles']], ['rich_man'])
        self.assertEqual([b['key'] for b in plays['fakegod']['battles']], ['fakegod'])
        seen = set()
        for play in plays.values():
            for battle in play['battles']:
                key = battle['key']
                limit = 'throw_limit' if key == 'rich_man' else f'{key}_limit'
                self.assertEqual(battle['limit'], {'group': 'general_config', 'argument': limit})
                self.assertEqual(
                    [r['argument'] for r in battle['soul']],
                    [f'enable_switch_{key}', f'{key}_group_team',
                     f'enable_switch_{key}_by_name', f'{key}_group_team_name'],
                )
                self.assertEqual(battle['battle_group'], f'{key}_battle_conf')
                self.assertIn(battle['battle_group'], args)
                seen.add(key)
        self.assertEqual(seen, set(BATTLES))
        self.assertEqual(plays['climb']['extra'], [{'group': 'general_config', 'argument': 'use_penta_pass'}])

    def test_every_reference_exists_in_args(self):
        self.write()
        model = ConfigModel('case')
        args = model.script_task(TASK)
        layout = model.script_task_layout(TASK)
        for ref in _all_refs(layout):
            self.assertIn(ref['argument'], _items(args, ref['group']), ref)
        for group in layout['advanced']['groups']:
            self.assertIn(group, args)

    def test_initial_expanded_follows_selection_and_limit(self):
        self.write({'task_sequence': '大富翁,爬塔', 'throw_limit': 0, 'ap_limit': 3, 'boss_limit': 0,
                    'fakegod_limit': 5})
        layout = ConfigModel('case').script_task_layout(TASK)
        plays = {p['key']: p for p in layout['plays']}
        # 选了但次数为零 → 收起；选了且有次数 → 展开；有次数但没选 → 收起
        self.assertFalse(plays['rich_man']['initial_expanded'])
        self.assertTrue(plays['climb']['initial_expanded'])
        self.assertFalse(plays['fakegod']['initial_expanded'])
        self.assertTrue(plays['fakegod']['battles'][0]['limit'] and not plays['fakegod']['selected'])
        climb = {b['key']: b['initial_expanded'] for b in plays['climb']['battles']}
        self.assertEqual(climb, {'ap': True, 'pass': False, 'boss': False, 'ap100': False})
        self.assertFalse(layout['advanced']['initial_expanded'])


class LayoutSafetyTest(LayoutBase):
    def test_reading_layout_does_not_write_or_change_args(self):
        path = self.write({'task_sequence': 'fakegod,climb', 'ap_limit': 2, 'fakegod_limit': 4})
        before = self.digest(path)
        with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('读取不得写配置')):
            model = ConfigModel('case')
            dump = model.model_dump_json()
            args_before = copy.deepcopy(model.script_task(TASK))
            model.script_task_layout(TASK)
            model.script_task_layout(TASK)
            self.assertEqual(model.script_task(TASK), args_before)
            self.assertEqual(model.model_dump_json(), dump)
        self.assertEqual(self.digest(path), before)

    def test_layout_is_not_in_saved_config(self):
        self.write()
        model = ConfigModel('case')
        model.script_task_layout(TASK)
        model.save()
        saved = json.loads(Path(self.tmp, 'config', 'case.json').read_text(encoding='utf-8'))
        self.assertNotIn('layout', json.dumps(saved).lower())

    def test_other_tasks_have_no_layout_and_unchanged_args(self):
        self.write()
        model = ConfigModel('case')
        for task in ('Orochi', 'GlobalGame', 'Script', 'Restart'):
            before = copy.deepcopy(model.script_task(task))
            self.assertEqual(model.script_task_layout(task), {})
            self.assertEqual(model.script_task(task), before)
        self.assertEqual(model.script_task_layout('NoSuchTask'), {})

    def test_defaults_and_field_names_unchanged(self):
        fields = ActivityShikigami().general_config.model_dump()
        self.assertEqual(fields['task_sequence'], '大富翁,爬塔,伪神降临')
        self.assertEqual(
            [k for k in fields],
            ['task_sequence', 'throw_limit', 'ap_limit', 'ap_limit_max', 'pass_limit', 'boss_limit',
             'ap100_limit', 'fakegod_limit', 'limit_time', 'active_souls_clean', 'random_sleep',
             'use_penta_pass'],  # 原有字段顺序不变，只新增 ap_limit_max
        )
        # 默认次数全为零 → 执行序列为空，与展示无关
        self.assertEqual(ActivityShikigami().general_config.task_sequence_v, [])


class SaveReloadTest(LayoutBase):
    def test_save_by_original_path_keeps_order_and_unselected_params(self):
        self.write({'task_sequence': '伪神降临,爬塔', 'fakegod_limit': 2, 'ap_limit': 1, 'throw_limit': 7})
        model = ConfigModel('case')
        layout = model.script_task_layout(TASK)
        rich = next(p for p in layout['plays'] if p['key'] == 'rich_man')
        self.assertFalse(rich['selected'])
        soul = rich['battles'][0]['soul']
        # 未选玩法的参数仍可按原路径编辑
        self.assertTrue(model.script_set_arg(TASK, 'switch_soul_config', soul[1]['argument'], '2,3'))
        self.assertTrue(model.script_set_arg(TASK, 'general_config', 'ap_limit', 5))
        again = ConfigModel('case')
        general = again.activity_shikigami.general_config
        self.assertEqual(general.task_sequence, '伪神降临,爬塔')
        self.assertEqual(general.task_sequence_v, ['伪神降临', '爬塔'])
        self.assertEqual(general.throw_limit, 7)
        self.assertEqual(general.ap_limit, 5)
        self.assertEqual(again.activity_shikigami.switch_soul_config.rich_man_group_team, '2,3')
        self.assertEqual(again.script_task_layout(TASK)['selector']['selected'], ['伪神降临', '爬塔'])

    def test_unselecting_a_play_via_sequence_keeps_its_parameters(self):
        self.write({'task_sequence': '大富翁,爬塔,伪神降临', 'throw_limit': 9, 'fakegod_limit': 3})
        model = ConfigModel('case')
        self.assertTrue(model.script_set_arg(TASK, 'general_config', 'task_sequence', '爬塔'))
        again = ConfigModel('case').activity_shikigami.general_config
        self.assertEqual((again.throw_limit, again.fakegod_limit), (9, 3))


class LegacyMigrationTest(LayoutBase):
    def test_legacy_config_loads_and_renders(self):
        legacy = {
            'rich_man': {
                'scheduler': {'enable': True},
                'run_config': {'throw_limit': 12, 'limit_time': '02:00:00'},
                'switch_soul': {'enable': True, 'switch_group_team': '1,2'},
            },
            'fakegod': {'scheduler': {'enable': True}, 'general_climb': {'pass_limit': 6}},
            'activity_shikigami': {'general_climb': {'ap_limit': 4, 'pass_limit': 0}},
        }
        self.write(raw=legacy)
        path = Path(self.tmp, 'config', 'case.json')
        before = self.digest(path)
        with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('读取不得写配置')):
            model = ConfigModel('case')
            args = model.script_task(TASK)
            layout = model.script_task_layout(TASK)
        self.assertEqual(self.digest(path), before)
        general = _items(args, 'general_config')
        self.assertEqual(general['task_sequence']['value'], '大富翁,爬塔,伪神降临')
        self.assertEqual(general['throw_limit']['value'], 12)
        self.assertEqual(general['ap_limit']['value'], 4)
        self.assertEqual(general['fakegod_limit']['value'], 6)
        self.assertEqual(_items(args, 'switch_soul_config')['rich_man_group_team']['value'], '1,2')
        self.assertEqual(layout['selector']['selected'], ['大富翁', '爬塔', '伪神降临'])
        for ref in _all_refs(layout):
            self.assertIn(ref['argument'], _items(args, ref['group']))


class RouteTest(LayoutBase):
    def test_route_serves_layout_and_args_unchanged(self):
        import httpx
        from fastapi import FastAPI
        self.write({'task_sequence': '爬塔', 'ap_limit': 1})
        fake = types.ModuleType('module.server.main_manager')
        fake.mm = SimpleNamespace(config_cache=lambda name: SimpleNamespace(model=ConfigModel(name)))
        with patch.dict(sys.modules, {'module.server.main_manager': fake}):
            sys.modules.pop('module.server.script_router', None)
            router = importlib.import_module('module.server.script_router')
            app = FastAPI()
            app.include_router(router.script_app)

            async def fetch():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url='http://oas') as client:
                    return (
                        await client.get(f'/case/{TASK}/args'),
                        await client.get(f'/case/{TASK}/args/layout'),
                        await client.get('/case/Orochi/args/layout'),
                    )

            args, layout, other = asyncio.run(fetch())
        sys.modules.pop('module.server.script_router', None)
        self.assertEqual(args.status_code, 200)
        self.assertEqual(layout.status_code, 200)
        # 剥离布局请求后，/args 与直接读取的协议逐字一致
        self.assertEqual(args.json(), json.loads(json.dumps(ConfigModel('case').script_task(TASK))))
        self.assertEqual(layout.json()['selector']['selected'], ['爬塔'])
        self.assertEqual(other.json(), {})
