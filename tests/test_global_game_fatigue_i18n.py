# This Python file uses the following encoding: utf-8
"""GlobalGame.fatigue 全局配置中文显示护栏。

OASX 用 `name`（嵌套字段是 `idle.steepness` 这样的完整路径）做标签键、`description` 做说明键，都走 GetX `.tr`
（整串键查表，点号无特殊含义）；远程翻译来自 `GET /home/additional_translate` → `assets/i18n/zh-CN.json`，
`appendTranslations` 追加并覆盖同名本地键。`enable` 由 OASX 本地全局键「启用该功能」提供，远程不覆盖。
"""

import asyncio
import json
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from module.config.config_model import ConfigModel
from module.server.i18n import I18n
from tasks.GlobalGame.config import FatigueConfig

_REPO = Path(__file__).resolve().parents[1]
ZH_CN = _REPO / 'assets' / 'i18n' / 'zh-CN.json'
CJK = re.compile(r'[一-鿿]')
# OASX 本地全局键：所有任务的 enable 共用「启用该功能」，远程翻译不得覆盖
OASX_LOCAL_KEYS = {'enable'}
# 改之前的默认值（锁住：翻译修复不得改动疲劳参数）
EXPECTED_DEFAULTS = {
    'enable': False, 'load_factor': 1.1,
    'task.time_scale_minutes': 65.0, 'task.repeat_scale': 15.0, 'task.time_weight': 70.0, 'task.repeat_weight': 20.0,
    'global_fatigue.time_scale_minutes': 180.0, 'global_fatigue.exponent': 2.0,
    'weights.idle_task': 0.8, 'weights.idle_global': 0.2, 'weights.rest_task': 0.25, 'weights.rest_global': 0.75,
    'idle.steepness': 0.11, 'idle.midpoint': 52.0, 'idle.rate_base': 1.5, 'idle.rate_max': 4.0,
    'idle.minimum_seconds': 15.0, 'idle.mode_minimum_seconds': 25.0, 'idle.mode_maximum_seconds': 70.0,
    'idle.maximum_seconds': 120.0, 'idle.range_floor_ratio': 0.12, 'idle.task_recovery_per_minute': 8.0,
    'idle.global_recovery_per_minute': 0.5,
    'rest.probability.maximum': 0.12, 'rest.probability.steepness': 0.1, 'rest.probability.midpoint': 58.0,
    'rest.minimum_seconds': 120.0, 'rest.mode_minimum_seconds': 120.0, 'rest.mode_maximum_seconds': 600.0,
    'rest.maximum_seconds': 1200.0, 'rest.range_floor_ratio': 0.2, 'rest.task_recovery_maximum': 70.0,
    'rest.task_recovery_tau_minutes': 7.0, 'rest.global_recovery_maximum': 65.0, 'rest.global_recovery_tau_minutes': 9.0,
    'cooldown.base_minutes': 30.0, 'cooldown.rest_duration_multiplier': 3.0, 'cooldown.jitter_minimum': 0.85,
    'cooldown.jitter_maximum': 1.15,
    'scheduler_idle.recovery_delay_minutes': 5.0, 'scheduler_idle.recovery_tau_minutes': 34.0,
}


def _fatigue_items() -> list[dict]:
    with patch.object(ConfigModel, 'write_json', side_effect=AssertionError('GET 不得写配置')):
        return ConfigModel().script_task('GlobalGame')['fatigue']


def _remote_zh() -> dict:
    # 与 GET /home/additional_translate 相同的加载函数
    return I18n.load_additions()['zh-CN']


def _tr(key: str, remote: dict) -> str | None:
    """GetX `.tr` 的查表语义：整串键精确匹配，找不到返回键本身（这里返回 None 方便断言）。"""
    return remote.get(key)


class FatigueI18nCoverageTest(TestCase):
    def test_api_field_list_and_defaults_are_unchanged(self):
        items = _fatigue_items()
        self.assertEqual([i['name'] for i in items], list(EXPECTED_DEFAULTS))
        self.assertEqual({i['name']: i['default'] for i in items}, EXPECTED_DEFAULTS)
        # 字段标识保持原样（配置读写依赖它），不能被翻译替换
        for name in ('idle.steepness', 'rest.probability.maximum', 'weights.rest_global'):
            self.assertIn(name, {i['name'] for i in items})

    def test_every_fatigue_label_resolves_to_chinese(self):
        remote = _remote_zh()
        items = _fatigue_items()
        covered = []
        for item in items:
            name = item['name']
            with self.subTest(name=name):
                if name in OASX_LOCAL_KEYS:
                    self.assertNotIn(name, remote)              # 不覆盖 OASX 全局键
                    covered.append(name)
                    continue
                label = _tr(name, remote)
                self.assertIsNotNone(label, name)
                self.assertTrue(label.strip())
                self.assertNotEqual(label, name)
                self.assertRegex(label, CJK)
                self.assertNotIn('_', label)                    # 不把内部变量名当中文名
                covered.append(name)
        self.assertEqual(len(covered), len(items))
        self.assertEqual(len(items), 41)

    def test_every_fatigue_field_has_a_chinese_description(self):
        remote = _remote_zh()
        for item in _fatigue_items():
            name = item['name']
            with self.subTest(name=name):
                description = item.get('description')
                self.assertTrue(description, name)
                if CJK.search(description):
                    continue                                    # 顶层 enable / load_factor 自带中文说明
                self.assertEqual(description, f'{name}_help')   # 嵌套字段沿用「<键>_help」规则
                text = _tr(description, remote)
                self.assertIsNotNone(text, description)
                self.assertRegex(text, CJK)
                self.assertNotEqual(text, description)

    def test_group_title_is_translated(self):
        self.assertRegex(_tr('fatigue', _remote_zh()), CJK)

    def test_time_and_ratio_fields_state_their_unit(self):
        remote = _remote_zh()
        for item in _fatigue_items():
            name = item['name']
            label = remote.get(name, '')
            with self.subTest(name=name):
                if name.endswith('_seconds'):
                    self.assertIn('秒', label)
                if name.endswith('_minutes'):
                    self.assertIn('分钟', label)
                if name.endswith(('range_floor_ratio', 'probability.maximum')):
                    self.assertIn('0~1', label)
                if name.startswith('idle.rate_'):
                    self.assertIn('次/小时', label)

    def test_new_keys_are_unique_and_do_not_shadow_other_tasks(self):
        raw = ZH_CN.read_text(encoding='utf-8')
        keys = ['fatigue', 'load_factor'] + [k for i in _fatigue_items() if '.' in i['name']
                                              for k in (i['name'], f"{i['name']}_help")]
        keys = list(dict.fromkeys(keys))
        for key in keys:
            with self.subTest(key=key):
                self.assertEqual(raw.count(json.dumps(key, ensure_ascii=False) + ':'), 1)
        # 其它任务的配置字段名不会被这些键误翻：只有 GlobalGame.fatigue 用到这些名字
        model = ConfigModel()
        other_names = set()
        for field in type(model).model_fields:
            if field in ('config_name', 'running_task', 'global_game'):
                continue
            for group, items in model.script_task(field).items():
                other_names.add(group)
                other_names.update(i['name'] for i in items)
        self.assertEqual(other_names & set(keys), set())

    def test_nested_names_still_write_back(self):
        writes = []
        with patch.object(ConfigModel, 'write_json', side_effect=lambda name, data: writes.append(name)):
            model = ConfigModel(config_name='case', **{})
            self.assertTrue(model.script_set_arg('GlobalGame', 'fatigue', 'idle.maximum_seconds', 150.0))
        self.assertEqual(model.global_game.fatigue.idle.maximum_seconds, 150.0)
        self.assertEqual(writes, ['case'])

    def test_fatigue_model_descriptions_do_not_change_runtime_values(self):
        cfg = FatigueConfig()
        self.assertEqual(cfg.idle.steepness, 0.11)
        self.assertEqual(cfg.rest.probability.maximum, 0.12)
        self.assertEqual(FatigueConfig.model_validate(cfg.model_dump()).model_dump(), cfg.model_dump())


class AdditionalTranslateRouteTest(TestCase):
    """真实 GET /home/additional_translate 路由（ASGI 传输层）下发的就是这些键。"""

    def test_route_serves_fatigue_translations(self):
        import importlib

        import httpx
        from fastapi import FastAPI
        fake = types.ModuleType('module.server.main_manager')
        fake.MainManager = SimpleNamespace
        fake.mm = SimpleNamespace()
        with patch.dict(sys.modules, {'module.server.main_manager': fake}):
            sys.modules.pop('module.server.home_router', None)
            router = importlib.import_module('module.server.home_router')
            app = FastAPI()
            app.include_router(router.home_app)

            async def fetch():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url='http://oas') as client:
                    return await client.get('/home/additional_translate')

            resp = asyncio.run(fetch())
        self.assertEqual(resp.status_code, 200)
        zh = resp.json()['zh-CN']
        self.assertEqual(zh['idle.steepness'], '发呆强度曲线陡峭度')
        self.assertEqual(zh['weights.rest_global'], '休息评分·全局疲劳权重')
        self.assertIn('次/小时', zh['idle.rate_base'])
        self.assertRegex(zh['rest.probability.maximum_help'], CJK)
