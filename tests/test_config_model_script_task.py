# This Python file uses the following encoding: utf-8
"""`ConfigModel.script_task`（GET /{script}/{task}/args）嵌套配置组回归护栏。

GlobalGame.fatigue 的子模型字段用 default_factory 声明，pydantic 2 的 schema 里只有 `$ref`、没有 `default`，
旧 `merge_value` 直接取 `value["default"]` → KeyError → HTTP 500。修复后嵌套字段展开成「父.子」叶子参数，
实际值取当前配置、默认值取字段自己的默认实例；其它任务的输出必须与旧实现逐字一致。
"""

import copy
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import types
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import patch

import inflection
from pydantic import BaseModel, Field, create_model

from module.config.config_model import ConfigModel
from module.config.utils import convert_to_underscore
from tasks.GlobalGame.config import FatigueConfig, GlobalGame

_REPO = Path(__file__).resolve().parents[1]
GLOBAL_GROUPS = ['emergency', 'costume_config', 'battle', 'ocr', 'team_flow', 'fatigue']
FATIGUE_NESTED = ['task', 'global_fatigue', 'weights', 'idle', 'rest', 'cooldown', 'scheduler_idle']
# 用户改过的疲劳参数（与模型默认值不同），用来证明读取时不会被偷偷恢复成默认值
USER_FATIGUE = {
    'enable': True,
    'load_factor': 1.25,
    ('task', 'time_scale_minutes'): 40.0,
    ('idle', 'minimum_seconds'): 10.0,
    ('idle', 'mode_maximum_seconds'): 90.0,
    ('idle', 'maximum_seconds'): 180.0,
    ('rest', 'probability', 'maximum'): 0.05,
}


def _flatten(data: dict, prefix: str = '') -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(_flatten(value, f'{prefix}{key}.'))
        else:
            out[f'{prefix}{key}'] = value
    return out


def _user_data() -> dict:
    data = ConfigModel().model_dump()
    data.pop('config_name', None)
    fatigue = data['global_game']['fatigue']
    for path, value in USER_FATIGUE.items():
        path = path if isinstance(path, tuple) else (path,)
        node = fatigue
        for name in path[:-1]:
            node = node[name]
        node[path[-1]] = value
    return data


def _user_model() -> ConfigModel:
    return ConfigModel(config_name='case', **copy.deepcopy(_user_data()))


def _items(result: dict, group: str) -> dict:
    return {item['name']: item for item in result[group]}


def _legacy_script_task(model, task: str) -> dict:
    """修复前 `ConfigModel.script_task` 的逐字副本，作为非嵌套配置组输出的对照基线。"""
    task = getattr(model, convert_to_underscore(task), None)

    def extract_groups(sch):
        results, properties = {}, {}
        for key, value in sch["properties"].items():
            if 'items' in value:
                properties[key] = re.search(r"/([^/]+)$", value['items']['$ref']).group(1)
            else:
                properties[key] = re.search(r"/([^/]+)$", value['$ref']).group(1)
        for key, value in properties.items():
            results[key] = sch["$defs"][value]
        return results

    def merge_value(groups, jsons, definitions):
        result = []
        for key, value in groups["properties"].items():
            if key in jsons and jsons[key] == 0xABCDEF:
                continue
            item = {"name": key, "title": value["title"] if "title" in value else inflection.underscore(key)}
            if "description" in value:
                item["description"] = value["description"]
            item["default"] = value["default"]
            item["value"] = jsons[key] if key in jsons else value["default"]
            item["type"] = value["type"] if "type" in value else "enum"
            if '$ref' in value:
                enum_key = re.search(r"/([^/]+)$", value['$ref']).group(1)
                item["enumEnum"] = definitions[enum_key]["enum"]
            result.append(item)
        return result

    schema = task.model_json_schema()
    groups = extract_groups(schema)
    groups_value = groups.copy()
    result = {}
    for key, value in task.model_dump(context={'hide': True}).items():
        if value == 0xABCDEF:
            continue
        if key not in groups:
            for group_name in groups.keys():
                if group_name in key:
                    groups_value[key] = groups[group_name]
        result[key] = merge_value(groups_value[key], value, schema["$defs"])
    return result


# 合成模型：多层嵌套 + default_factory 覆写子模型默认值 + 显式 default + 枚举 + 必填字段
class Color(str, Enum):
    RED = 'red'
    BLUE = 'blue'


class Inner(BaseModel):
    x: int = 1
    color: Color = Color.RED


class Mid(BaseModel):
    inner: Inner = Field(default_factory=Inner)
    ratio: float = 0.5


class Group(BaseModel):
    flag: bool = Field(default=True, description='flag_help')
    mode: Color = Field(default=Color.BLUE, description='mode_help')
    plain: Mid = Field(default_factory=Mid)
    overridden: Mid = Field(default_factory=lambda: Mid(inner=Inner(x=9), ratio=0.25), description='overridden_help')
    literal: Inner = Inner(x=7)


class Required(BaseModel):
    need: int
    sub: Inner


class SyntheticTask(BaseModel):
    group: Group = Field(default_factory=Group)
    required: Required = Field(default_factory=lambda: Required(need=3, sub=Inner(x=4)))


class ScriptTaskNestedSchemaTest(TestCase):
    def setUp(self):
        # 读取不得写文件：任何 save 都直接让用例失败
        self._no_write = patch.object(ConfigModel, 'write_json', side_effect=AssertionError('GET 不得写配置'))
        self._no_write.start()
        self.addCleanup(self._no_write.stop)

    def test_case1_global_game_schema_and_groups(self):
        schema = GlobalGame.model_json_schema()
        self.assertIn('FatigueConfig', schema['$defs'])
        result = ConfigModel().script_task('GlobalGame')
        self.assertEqual(list(result), GLOBAL_GROUPS)

    def test_case2_fatigue_nested_fields_have_no_schema_default_but_do_not_raise(self):
        props = FatigueConfig.model_json_schema()['properties']
        for name in FATIGUE_NESTED:
            self.assertEqual(set(props[name]), {'$ref'})          # 复现前提：default_factory 没有 default
        items = _items(ConfigModel().script_task('GlobalGame'), 'fatigue')
        self.assertNotIn('task', items)                            # 嵌套模型本身不是一个参数
        self.assertIn('task.time_scale_minutes', items)
        self.assertEqual(set(items), set(_flatten(FatigueConfig().model_dump(mode='json'))))

    def test_case3_multi_level_ref_uses_the_right_nested_class_and_factory(self):
        items = _items(ConfigModel().script_task('GlobalGame'), 'fatigue')
        # RestProbability 覆写了 FatigueProbability 的默认值（0.18 → 0.12）
        self.assertEqual(items['rest.probability.maximum']['default'], 0.12)
        self.assertEqual(items['rest.probability.midpoint']['default'], 58.0)
        synthetic = _items(ConfigModel.script_task(SimpleNamespace(synthetic_task=SyntheticTask()), 'synthetic_task'), 'group')
        self.assertEqual(synthetic['overridden.inner.x']['default'], 9)   # 父级工厂覆写，不是 Inner 类默认 1
        self.assertEqual(synthetic['overridden.ratio']['default'], 0.25)
        self.assertEqual(synthetic['plain.inner.x']['default'], 1)
        self.assertEqual(synthetic['plain.inner.color']['type'], 'enum')
        self.assertEqual(synthetic['plain.inner.color']['enumEnum'], ['red', 'blue'])

    def test_case4_explicit_defaults_and_enums_keep_the_old_behaviour(self):
        items = _items(ConfigModel().script_task('GlobalGame'), 'fatigue')
        self.assertEqual(items['enable'], {'name': 'enable', 'title': 'Enable', 'description': '是否启用疲劳、发呆和休息机制',
                                           'default': False, 'value': False, 'type': 'boolean'})
        self.assertEqual(items['load_factor']['default'], 1.1)
        synthetic = _items(ConfigModel.script_task(SimpleNamespace(synthetic_task=SyntheticTask()), 'synthetic_task'), 'group')
        self.assertEqual(synthetic['mode']['default'], 'blue')
        self.assertEqual(synthetic['mode']['type'], 'enum')
        self.assertEqual(synthetic['mode']['description'], 'mode_help')
        self.assertEqual(synthetic['literal.x']['default'], 7)             # 字面量 default（schema 声明的 dict）

    def test_case5_default_factory_defaults_equal_the_model_defaults(self):
        items = _items(ConfigModel().script_task('GlobalGame'), 'fatigue')
        for name, default in _flatten(FatigueConfig().model_dump(mode='json')).items():
            self.assertEqual(items[name]['default'], default, name)
            self.assertEqual(type(items[name]['default']), type(default), name)
        # 必填嵌套字段没有默认实例：叶子回落到各自 schema 默认，必填叶子不编造值
        required = _items(ConfigModel.script_task(SimpleNamespace(synthetic_task=SyntheticTask()), 'synthetic_task'), 'required')
        self.assertIsNone(required['need']['default'])
        self.assertEqual(required['need']['value'], 3)
        self.assertEqual(required['sub.x']['value'], 4)

    def test_case6_user_values_are_returned_not_defaults(self):
        items = _items(_user_model().script_task('GlobalGame'), 'fatigue')
        defaults = _flatten(FatigueConfig().model_dump(mode='json'))
        for path, value in USER_FATIGUE.items():
            name = '.'.join(path) if isinstance(path, tuple) else path
            self.assertEqual(items[name]['value'], value, name)
            self.assertEqual(items[name]['default'], defaults[name], name)
            self.assertNotEqual(items[name]['value'], items[name]['default'], name)

    def test_case8_every_group_is_a_list_of_renderable_scalar_items(self):
        result = _user_model().script_task('GlobalGame')
        self.assertEqual(list(result), GLOBAL_GROUPS)
        for group, items in result.items():
            self.assertIsInstance(items, list, group)
            self.assertTrue(items, group)
            for item in items:
                self.assertTrue({'name', 'title', 'default', 'value', 'type'} <= set(item), item)
                self.assertNotIsInstance(item['value'], (dict, BaseModel), item['name'])
                self.assertNotIsInstance(item['default'], (dict, BaseModel), item['name'])
        json.dumps(result, default=str)

    def test_case9_other_tasks_output_identical_to_legacy_implementation(self):
        for model in (ConfigModel(), _user_model()):
            for field in type(model).model_fields:
                if field in ('config_name', 'running_task', 'global_game'):
                    continue
                with self.subTest(task=field):
                    self.assertEqual(model.script_task(field), _legacy_script_task(model, field))
        # GlobalGame 的非嵌套组也与旧实现逐字一致：去掉 fatigue 的同构模型可以跑旧实现
        flat_global = create_model('GlobalGame', **{name: (field.annotation, field)
                                                    for name, field in GlobalGame.model_fields.items() if name != 'fatigue'})
        model = _user_model()
        probe = SimpleNamespace(global_game=flat_global(**model.global_game.model_dump(exclude={'fatigue'})))
        new = model.script_task('GlobalGame')
        legacy = _legacy_script_task(probe, 'GlobalGame')
        self.assertEqual(list(legacy), GLOBAL_GROUPS[:-1])
        for group in legacy:
            self.assertEqual(new[group], legacy[group], group)

    def test_case10_fire_reaction_groups_return_400_800(self):
        model = ConfigModel()
        tasks = [f for f in type(model).model_fields
                 if isinstance(getattr(model, f), BaseModel) and 'fire_reaction' in type(getattr(model, f)).model_fields]
        if not tasks:
            self.skipTest('当前基线没有 fire_reaction 配置组')
        for task in tasks:
            with self.subTest(task=task):
                items = _items(model.script_task(task), 'fire_reaction')
                self.assertEqual((items['fire_reaction_min_ms']['default'], items['fire_reaction_min_ms']['value']), (400, 400))
                self.assertEqual((items['fire_reaction_max_ms']['default'], items['fire_reaction_max_ms']['value']), (800, 800))

    def test_case11_reading_does_not_reset_values(self):
        model = _user_model()
        before = model.model_dump()
        for field in type(model).model_fields:
            if field not in ('config_name', 'running_task'):
                model.script_task(field)
        self.assertEqual(model.model_dump(), before)


class ScriptTaskNestedWriteTest(TestCase):
    """展开出的「父.子」参数必须能写回，并且整体校验；写入只落到替身，不碰真实文件。"""

    def setUp(self):
        self.writes = []
        p = patch.object(ConfigModel, 'write_json', side_effect=lambda name, data: self.writes.append((name, data)))
        p.start()
        self.addCleanup(p.stop)
        self.model = _user_model()

    def test_nested_write_updates_only_the_leaf_and_saves(self):
        before = _flatten(self.model.model_dump(mode='json'))
        self.assertTrue(self.model.script_set_arg('GlobalGame', 'fatigue', 'idle.maximum_seconds', 200.0))
        self.assertTrue(self.model.script_set_arg('GlobalGame', 'fatigue', 'rest.probability.maximum', 0.07))
        after = _flatten(self.model.model_dump(mode='json'))
        changed = {k for k in before if before[k] != after[k]}
        self.assertEqual(changed, {'global_game.fatigue.idle.maximum_seconds', 'global_game.fatigue.rest.probability.maximum'})
        self.assertEqual(len(self.writes), 2)
        self.assertEqual(self.writes[-1][0], 'case')
        items = _items(self.model.script_task('GlobalGame'), 'fatigue')
        self.assertEqual(items['idle.maximum_seconds']['value'], 200.0)

    def test_invalid_nested_write_is_rejected_and_nothing_changes(self):
        before = self.model.model_dump()
        # 违反字段约束（lt=1.0）/ 违反子模型 model_validator（最长 < 众数上限）/ 不存在的路径
        self.assertFalse(self.model.script_set_arg('GlobalGame', 'fatigue', 'rest.probability.maximum', 1.5))
        self.assertFalse(self.model.script_set_arg('GlobalGame', 'fatigue', 'idle.maximum_seconds', 5.0))
        self.assertFalse(self.model.script_set_arg('GlobalGame', 'fatigue', 'idle.no_such_field', 1.0))
        self.assertFalse(self.model.script_set_arg('GlobalGame', 'fatigue', 'no_such_group.x', 1.0))
        self.assertEqual(self.model.model_dump(), before)
        self.assertEqual(self.writes, [])

    def test_flat_write_still_uses_the_original_path(self):
        self.assertTrue(self.model.script_set_arg('GlobalGame', 'Fatigue', 'LoadFactor', 1.0))
        self.assertEqual(self.model.global_game.fatigue.load_factor, 1.0)
        self.assertEqual(len(self.writes), 1)


class ScriptTaskFileAndApiTest(TestCase):
    """CASE 7 / 12：真实读文件路径 + 真实 GET 路由，都在临时目录的配置副本上进行。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='oas_args_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, 'config'))
        self.cwd = os.getcwd()
        self.addCleanup(os.chdir, self.cwd)

    @staticmethod
    def _digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest(), os.stat(path).st_mtime_ns

    def _write_user_config(self, name='case'):
        path = os.path.join(self.tmp, 'config', f'{name}.json')
        Path(path).write_text(_user_model().model_dump_json(), encoding='utf-8')
        return path

    def test_case7_get_does_not_touch_the_config_file(self):
        path = self._write_user_config()
        before = self._digest(path)
        os.chdir(self.tmp)
        with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('GET 不得写配置')):
            model = ConfigModel('case')
            for task in ('GlobalGame', 'Orochi', 'Script'):
                model.script_task(task)
        self.assertEqual(self._digest(path), before)

    def test_case12_real_route_returns_200_and_a_json_object(self):
        import asyncio
        import httpx
        from fastapi import FastAPI
        path = self._write_user_config()
        before = self._digest(path)
        os.chdir(self.tmp)
        # main_manager 在 import 时会为每份配置建 ScriptProcess 并起推送线程；这里只替身出 mm.config_cache，
        # 路由函数本身用真实的 script_router
        fake = types.ModuleType('module.server.main_manager')
        fake.mm = SimpleNamespace(config_cache=lambda name: SimpleNamespace(model=ConfigModel(name)))
        with patch.dict(sys.modules, {'module.server.main_manager': fake}):
            sys.modules.pop('module.server.script_router', None)
            router = importlib.import_module('module.server.script_router')
            app = FastAPI()
            app.include_router(router.script_app)

            # toolkit 的 starlette TestClient 与 httpx 0.28 不兼容，直接走 ASGI 传输层
            async def fetch():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url='http://oas') as client:
                    return await client.get('/case/GlobalGame/args'), await client.get('/case/Orochi/args')

            resp, other = asyncio.run(fetch())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, dict)
        self.assertEqual(list(body), GLOBAL_GROUPS)
        items = _items(body, 'fatigue')
        self.assertEqual(items['load_factor']['value'], 1.25)
        self.assertEqual(items['rest.probability.maximum']['value'], 0.05)
        self.assertEqual(other.status_code, 200)
        self.assertIsInstance(other.json(), dict)
        self.assertEqual(self._digest(path), before)


@skipUnless((_REPO / 'config' / 'oas1.json').exists() or (_REPO / 'config' / 'oas2.json').exists(),
            '本地没有真实 oas 配置')
class RealLocalConfigTest(TestCase):
    """本地真实 oas*.json（被 .gitignore 忽略）：复制到临时目录读取，只断言结构与值一致，不输出配置内容。"""

    def test_real_configs_render_global_game_with_actual_values(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        tmp = tempfile.mkdtemp(prefix='oas_args_real_')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, 'config'))
        for src in sorted((_REPO / 'config').glob('oas*.json')):
            with self.subTest(config=src.stem):
                digest = hashlib.sha256(src.read_bytes()).hexdigest()
                shutil.copy(src, os.path.join(tmp, 'config', src.name))
                os.chdir(tmp)
                with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('GET 不得写配置')):
                    model = ConfigModel(src.stem)
                    result = model.script_task('GlobalGame')
                os.chdir(cwd)
                self.assertEqual(list(result), GLOBAL_GROUPS)
                items = _items(result, 'fatigue')
                actual = _flatten(model.global_game.fatigue.model_dump(mode='json'))
                self.assertEqual({n: i['value'] for n, i in items.items()}, actual)
                raw = json.loads(src.read_text(encoding='utf-8')).get('global_game', {}).get('fatigue') or {}
                for name, value in _flatten(raw).items():
                    self.assertEqual(items[name]['value'], value, name)
                self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), digest)
