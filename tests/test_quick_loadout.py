import ast
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tasks' / 'Component' / 'QuickLoadout' / 'quick_loadout.py'


def _load_quick_loadout_helpers():
    """加载不依赖设备和图像服务的纯坐标/文本辅助方法。"""
    module = ast.parse(SOURCE.read_text(encoding='utf-8'))
    class_node = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'QuickLoadout')
    members = []
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & {'PANEL_FROM_FIGHT'}:
                members.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            '_offset_roi', '_result_center_y', '_normalize_name', '_name_similarity'
        }:
            members.append(node)
    isolated = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name='difflib')]),
            ast.Import(names=[ast.alias(name='re')]),
            ast.Import(names=[ast.alias(name='numpy', asname='np')]),
            ast.ClassDef(name='QuickLoadout', bases=[], keywords=[], body=members, decorator_list=[]),
        ],
        type_ignores=[],
    )
    namespace = {}
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), 'exec'), namespace)
    return namespace['QuickLoadout']


def test_goryou_fight_anchor_derives_expected_panel():
    quick = _load_quick_loadout_helpers()
    anchor_x, anchor_y = 668, 484
    dx, dy, width, height = quick.PANEL_FROM_FIGHT
    assert (anchor_x + dx, anchor_y + dy, width, height) == (405, 153, 551, 386)


def test_relative_roi_tracks_panel_origin():
    quick = _load_quick_loadout_helpers()
    assert quick._offset_roi((405, 153, 551, 386), (17, 7, 101, 356)) == (422, 160, 101, 356)
    assert quick._offset_roi((606, 231, 551, 386), (17, 7, 101, 356)) == (623, 238, 101, 356)


def test_ocr_result_y_is_translated_to_screen_coordinates():
    quick = _load_quick_loadout_helpers()

    class Result:
        box = np.array([[0, 8], [20, 8], [20, 28], [0, 28]])

    assert quick._result_center_y(Result(), 160) == 178


def test_name_similarity_tolerates_spacing_and_punctuation():
    quick = _load_quick_loadout_helpers()
    assert quick._name_similarity('武 道·大会', '武道大会') == 1.0
    assert quick._name_similarity('御灵', '武道大会') < 0.55


def test_martial_arts_boss_applies_quick_loadout_before_team_lock():
    source = (ROOT / 'tasks' / 'MartialArts' / 'script_task.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    run_boss_battles = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'run_boss_battles'
    )
    quick_calls = [
        node
        for node in ast.walk(run_boss_battles)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'run_quick_loadout'
    ]
    lock_calls = [
        node
        for node in ast.walk(run_boss_battles)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'lock_team'
    ]
    assert quick_calls
    assert lock_calls
    assert min(call.lineno for call in quick_calls) < max(call.lineno for call in lock_calls)


def test_martial_arts_oasx_group_order():
    source = (ROOT / 'tasks' / 'MartialArts' / 'config.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    martial_arts = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == 'MartialArts'
    )
    fields = [
        node.target.id
        for node in martial_arts.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    expected = ['switch_soul_config', 'boss_quick_loadout_config', 'ap_battle_conf', 'boss_battle_conf']
    indexes = [fields.index(name) for name in expected]
    assert indexes == sorted(indexes)


def test_goryou_no_longer_owns_quick_loadout_config():
    source = (ROOT / 'tasks' / 'GoryouRealm' / 'config.py').read_text(encoding='utf-8')
    assert 'quick_loadout_config' not in source


def test_custom_preset_parser_accepts_multiple_bosses():
    module = ast.parse(SOURCE.read_text(encoding='utf-8'))
    class_node = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == 'QuickLoadout'
    )
    parser = next(
        node for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == '_parse_custom_presets'
    )
    isolated = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name='ast')]),
            ast.Import(names=[ast.alias(name='re')]),
            ast.ClassDef(
                name='QuickLoadout', bases=[], keywords=[], body=[parser], decorator_list=[]
            ),
        ],
        type_ignores=[],
    )
    namespace = {}
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), 'exec'), namespace)
    parse = namespace['QuickLoadout']._parse_custom_presets

    assert parse('雷麒麟:("2","3");冥火姥姥:("御魂","长线")；') == {
        '雷麒麟': ('2', '3'),
        '冥火姥姥': ('御魂', '长线'),
    }
    assert parse('ALL:(1,1);雷麒麟:(2,3);') == {
        'ALL': ('1', '1'),
        '雷麒麟': ('2', '3'),
    }


def test_named_fields_are_only_exposed_by_opt_in_config():
    source = (
        ROOT / 'tasks' / 'Component' / 'QuickLoadout' / 'config.py'
    ).read_text(encoding='utf-8')
    tree = ast.parse(source)
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }

    def fields(class_name):
        return {
            node.target.id
            for node in classes[class_name].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }

    assert 'custom_preset' not in fields('QuickLoadoutConfig')
    assert {'custom_preset_enable', 'custom_preset'} <= fields('NamedQuickLoadoutConfig')


def test_quick_loadout_mode_uses_translated_enum_values():
    source = (
        ROOT / 'tasks' / 'Component' / 'QuickLoadout' / 'config.py'
    ).read_text(encoding='utf-8')
    assert "NUMBER = 'mode_number'" in source
    assert "OCR = 'mode_ocr'" in source


def test_martial_arts_opts_into_named_quick_loadout_and_passes_boss_ocr():
    config_source = (ROOT / 'tasks' / 'MartialArts' / 'config.py').read_text(encoding='utf-8')
    task_source = (ROOT / 'tasks' / 'MartialArts' / 'script_task.py').read_text(encoding='utf-8')
    assert 'boss_quick_loadout_config: NamedQuickLoadoutConfig' in config_source
    assert 'name_ocr=self.O_BOSS_NAME' in task_source
