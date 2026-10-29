# This Python file uses the following encoding: utf-8
"""御魂 → 个人突破循环的配置在 OASX 里的展示 / 编辑 / 保存 / 重读 / 实际消费整条链（只覆盖后端这一侧）。

用真实的 `ConfigModel`（参数输出 `script_task`、逐字段保存 `script_set_arg`）和真实的配置文件（临时目录），
重读用一个全新的 `ConfigModel(config_name=...)`，消费用真实的 `Script._loop_consume_request`。
OASX 这一侧（Flutter）没有在本机运行；OASX 对翻译键、整数输入的行为是读源码确认的：
- 标签 = 参数的 `name`（字段名）`.tr`，说明 = `description`（`*_help`）`.tr`，分组名 = 组 key `.tr`；
- 翻译来源 = OASX 自带的 Dart 表 + 启动时从后端 `/home/additional_translate`（即 `assets/i18n/*.json`）追加（后者覆盖前者）；
  `module/config/i18n/zh_CN.xml` 没有任何代码读它。
"""

import json
import re
import unittest
from pathlib import Path
from unittest.mock import Mock

from module.config.config_model import ConfigModel
from tasks.Orochi.config import LoopConfig
from tests.test_loop_script_glue import ScriptFixture

ROOT = Path(__file__).resolve().parents[1]
CHINESE = re.compile('[一-鿿]')

GROUP_LABEL = '御魂→个人突破循环'
FIELD_LABELS = {
    'start_loop': '开始循环（一次性）',
    'rounds': '循环轮数',
    'target_min': '每批御魂最少场数',
    'target_max': '每批御魂最多场数',
}


def additions(language):
    return json.loads((ROOT / 'assets' / 'i18n' / f'{language}.json').read_text(encoding='utf-8'))


class TranslationTest(unittest.TestCase):
    """OASX 实际消费的翻译键（字段名 / 说明键 / 分组名）都能得到中文。"""

    def loop_items(self):
        model = ConfigModel()
        return model.script_task('orochi')['loop_config']

    def test_every_key_oasx_looks_up_has_chinese_in_the_source_oasx_loads(self):
        zh = additions('zh-CN')
        keys = ['loop_config']
        for item in self.loop_items():
            keys.append(item['name'])                       # OASX 的标签 = 字段名
            keys.append(item['description'])                # 说明 = description（*_help）
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(key, zh)
                self.assertRegex(zh[key], CHINESE)

    def test_labels_are_the_agreed_chinese(self):
        zh = additions('zh-CN')
        self.assertEqual(zh['loop_config'], GROUP_LABEL)
        for name, label in FIELD_LABELS.items():
            self.assertEqual(zh[name], label)

    def test_help_texts_explain_the_loop_clearly(self):
        zh = additions('zh-CN')
        self.assertIn('一次性', zh['start_loop_help'])
        self.assertIn('自动关回', zh['start_loop_help'])
        self.assertIn('不是永久', zh['start_loop_help'])
        self.assertIn('一批御魂', zh['loop_rounds_help'])
        self.assertIn('个人突破', zh['loop_rounds_help'])
        self.assertIn('队长', zh['loop_target_min_help'])
        self.assertIn('随机一次', zh['loop_target_min_help'])
        self.assertIn('队员使用同一个数', zh['loop_target_min_help'])
        self.assertIn('固定场数', zh['loop_target_min_help'])
        self.assertIn('不能小于最少场数', zh['loop_target_max_help'])
        self.assertIn('正常结束', zh['loop_target_max_help'])

    def test_english_additions_exist_so_the_english_ui_is_not_raw_keys(self):
        en = additions('en-US')
        for key in ['loop_config', *FIELD_LABELS, 'start_loop_help', 'loop_rounds_help',
                    'loop_target_min_help', 'loop_target_max_help']:
            self.assertIn(key, en)
            self.assertNotRegex(en[key], CHINESE)

    def test_the_new_keys_do_not_clash_with_other_tasks_fields(self):
        # 翻译键是全局的：字段名 rounds / target_min / target_max / start_loop 只有循环配置在用
        hits = []
        for path in list((ROOT / 'tasks').rglob('config*.py')):
            text = path.read_text(encoding='utf-8', errors='ignore')
            for name in FIELD_LABELS:
                if re.search(rf'^\s+{name}\s*:', text, re.M):
                    hits.append((path.relative_to(ROOT).as_posix(), name))
        self.assertEqual({p for p, _ in hits}, {'tasks/Orochi/config.py'})


class EditSaveReloadTest(ScriptFixture):
    """120～140：输入 → 保存 → 离开再回来 / 重新加载仍是 120 和 140 → 循环启动时实际读到。"""

    def model(self):
        return ConfigModel(config_name='simA')

    def loop_values(self, model):
        return {item['name']: item['value'] for item in model.script_task('orochi')['loop_config']}

    def test_args_output_has_the_two_editable_integer_fields_with_values(self):
        self.write_config()
        items = {item['name']: item for item in self.model().script_task('orochi')['loop_config']}
        self.assertEqual(list(items), ['start_loop', 'rounds', 'target_min', 'target_max'])
        for name in ('rounds', 'target_min', 'target_max'):
            self.assertEqual(items[name]['type'], 'integer')
        self.assertEqual(items['start_loop']['type'], 'boolean')
        self.assertEqual((items['target_min']['value'], items['target_max']['value']), (2, 2))   # 夹具里写的值

    def test_120_to_140_is_saved_survives_a_fresh_reload_and_is_what_the_loop_reads(self):
        self.write_config()
        server_side = self.model()
        self.assertTrue(server_side.script_set_arg('orochi', 'loop_config', 'target_min', 120))
        self.assertTrue(server_side.script_set_arg('orochi', 'loop_config', 'target_max', 140))
        reloaded = self.model()                                   # 离开页面再回来 / 重新加载配置
        values = self.loop_values(reloaded)
        self.assertEqual((values['target_min'], values['target_max']), (120, 140))
        saved = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['orochi']['loop_config']['target_min'], 120)
        self.assertEqual(saved['orochi']['loop_config']['target_max'], 140)
        # 打开一次性开关：循环启动时读到的就是 120～140，队长据此随机
        self.assertTrue(server_side.script_set_arg('orochi', 'loop_config', 'start_loop', True))
        script = self.make_script()
        script._loop_consume_request()
        self.assertEqual((script.loop_controller.loop['tmin'], script.loop_controller.loop['tmax']), (120, 140))
        again = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))['orochi']['loop_config']
        self.assertEqual((again['start_loop'], again['target_min'], again['target_max']), (False, 120, 140))   # 开关关回，区间保留

    def test_changing_from_the_old_range_works_in_either_order_without_getting_stuck(self):
        for first, second in (('target_min', 'target_max'), ('target_max', 'target_min')):
            with self.subTest(order=first):
                self.write_config(tweak=lambda d: d['orochi']['loop_config'].update(target_min=10, target_max=30))
                model = self.model()
                new = {'target_min': 120, 'target_max': 140}
                self.assertTrue(model.script_set_arg('orochi', 'loop_config', first, new[first]))    # 中间状态 120>30 或 10>140 允许
                self.assertTrue(model.script_set_arg('orochi', 'loop_config', second, new[second]))
                values = self.loop_values(self.model())
                self.assertEqual((values['target_min'], values['target_max']), (120, 140))

    def test_typing_digit_by_digit_ends_on_the_final_number(self):
        self.write_config()
        model = self.model()
        for typed in (1, 12, 120):
            self.assertTrue(model.script_set_arg('orochi', 'loop_config', 'target_min', typed))
        self.assertEqual(self.loop_values(self.model())['target_min'], 120)

    def test_equal_bounds_mean_a_fixed_count_and_start(self):
        self.write_config(tweak=lambda d: d['orochi']['loop_config'].update(start_loop=True, target_min=130, target_max=130))
        script = self.make_script()
        script._loop_consume_request()
        self.assertEqual((script.loop_controller.loop['tmin'], script.loop_controller.loop['tmax']), (130, 130))

    def test_min_above_max_is_refused_at_start_with_a_clear_chinese_message_and_the_switch_is_consumed(self):
        self.write_config(tweak=lambda d: d['orochi']['loop_config'].update(start_loop=True, target_min=140, target_max=120))
        script = self.make_script()
        script.loop_controller.notify = Mock()
        script._loop_consume_request()
        self.assertIsNone(script.loop_controller.loop)
        message = script.loop_controller.notify.call_args.args[0]
        self.assertIn('最少场数', message)
        self.assertIn('最多场数', message)
        self.assertIn('140', message)
        self.assertIn('120', message)
        saved = json.loads(Path('config', 'simA.json').read_text(encoding='utf-8'))['orochi']['loop_config']
        self.assertFalse(saved['start_loop'])                              # 一次性：被拒绝也读过了、关回了
        self.assertEqual((saved['target_min'], saved['target_max']), (140, 120))   # 没有擅自改用户的值

    def test_out_of_range_and_non_integer_values_are_refused_not_silently_kept_and_never_reset_the_group(self):
        self.write_config(tweak=lambda d: d['orochi']['loop_config'].update(rounds=7, target_min=120, target_max=140))
        model = self.model()
        for argument, bad in (('target_min', 0), ('target_min', 1000), ('target_max', 0), ('target_max', 1000),
                              ('rounds', 0), ('rounds', 101), ('target_min', 'abc'), ('target_max', None)):
            with self.subTest(argument=argument, value=bad):
                self.assertFalse(model.script_set_arg('orochi', 'loop_config', argument, bad))
        values = self.loop_values(self.model())
        self.assertEqual((values['rounds'], values['target_min'], values['target_max']), (7, 120, 140))   # 整组没被重置成默认值

    def test_boundaries_one_and_999_are_accepted(self):
        self.write_config()
        model = self.model()
        self.assertTrue(model.script_set_arg('orochi', 'loop_config', 'target_min', 1))
        self.assertTrue(model.script_set_arg('orochi', 'loop_config', 'target_max', 999))
        self.assertTrue(model.script_set_arg('orochi', 'loop_config', 'rounds', 100))
        values = self.loop_values(self.model())
        self.assertEqual((values['target_min'], values['target_max'], values['rounds']), (1, 999, 100))

    def test_old_config_files_still_load_with_their_values_and_defaults(self):
        # 没有 loop_config 的旧配置：整组走默认值；已有 loop_config 的：值原样保留
        self.write_config(tweak=lambda d: d['orochi'].pop('loop_config'))
        values = self.loop_values(self.model())
        self.assertEqual((values['rounds'], values['target_min'], values['target_max'], values['start_loop']),
                         (3, 10, 30, False))
        self.write_config(tweak=lambda d: d['orochi']['loop_config'].update(rounds=5, target_min=11, target_max=22))
        values = self.loop_values(self.model())
        self.assertEqual((values['rounds'], values['target_min'], values['target_max']), (5, 11, 22))

    def test_field_names_and_defaults_are_unchanged(self):
        defaults = LoopConfig()
        self.assertEqual((defaults.start_loop, defaults.rounds, defaults.target_min, defaults.target_max),
                         (False, 3, 10, 30))
        self.assertEqual(list(LoopConfig.model_fields), ['start_loop', 'rounds', 'target_min', 'target_max'])


if __name__ == '__main__':
    unittest.main()
