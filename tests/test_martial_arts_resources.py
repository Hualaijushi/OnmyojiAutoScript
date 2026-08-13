import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tasks' / 'MartialArts' / 'script_task.py'


def _load_number_parser():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    script_task = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == 'ScriptTask'
    )
    parser = next(
        node for node in script_task.body
        if isinstance(node, ast.FunctionDef) and node.name == '_parse_ocr_number'
    )
    isolated = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name='re')]),
            ast.ClassDef(
                name='ScriptTask',
                bases=[],
                keywords=[],
                body=[parser],
                decorator_list=[],
            ),
        ],
        type_ignores=[],
    )
    namespace = {}
    exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), 'exec'), namespace)
    return namespace['ScriptTask']._parse_ocr_number


def test_resource_parser_supports_abbreviated_large_numbers():
    parse = _load_number_parser()
    assert parse('5.3万') == 53_000
    assert parse('1.2萬') == 12_000
    assert parse('3.4亿') == 340_000_000
    assert parse('519') == 519


def test_boss_ap_is_checked_after_panel_open_before_loadout_and_battle():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    run_boss_battles = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'run_boss_battles'
    )
    call_lines = {}
    for node in ast.walk(run_boss_battles):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        call_lines.setdefault(node.func.attr, []).append(node.lineno)

    search_line = min(call_lines['search_boss'])
    ap_line = min(call_lines['boss_ap_enough'])
    quick_line = min(call_lines['run_quick_loadout'])
    battle_line = min(call_lines['run_boss_battle_round'])
    assert search_line < ap_line < quick_line < battle_line
