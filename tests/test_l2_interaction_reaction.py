# This Python file uses the following encoding: utf-8
"""L2-1 Interaction Reaction Layer 回归护栏（`module/interaction_policy.py`，`docs/DECISIONS.md` D001 补记 L2）。

    Target Ready → InteractionPolicy → Reaction → Fresh Frame → Fresh Confirm → L1 单击

CASE 编号对应 L2-1 任务单：Reaction Profile（1–10）/ Fresh Confirm（11–16）/ FIRE 配置（17–27）/
Timing Ownership（28–35）。
"""

import ast
import inspect
import json
import textwrap
from pathlib import Path
from random import SystemRandom
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from module import interaction_policy as ip
from module import reaction_profile as rp
from module.base.utils import random as random_utils
from module.interaction_policy import InteractionPolicy, fire_reaction_range, resolve_reaction_range
from tasks.base_task import BaseTask
from tasks.Component.config_fire_reaction import FireReactionConfig

_REPO = Path(__file__).resolve().parents[1]

# 每个 FIRE owner：(文件, 函数, 该函数里 FIRE 目标在 appear_then_click 的第一个参数写法)
FIRE_OWNERS = (
    ('tasks/RealmRaid/script_task.py', 'fire', 'self.I_FIRE'),
    ('tasks/RealmRaid/script_task.py', '_fire_again', 'self.I_FIRE_AGAIN'),
    ('tasks/RyouToppa/script_task.py', 'attack_area', 'RealmRaidAssets.I_FIRE'),
    ('tasks/EvoZone/script_task.py', '_fire_evozone_alone', 'self.I_EVOZONE_FIRE'),
    ('tasks/Orochi/script_task.py', '_fire_orochi_alone', 'self.I_OROCHI_FIRE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'click_fire', 'target'),
    ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle', 'fire_rule'),
    # L2-3B FIRE Batch A
    ('tasks/EternitySea/script_task.py', '_fire_eternity_sea_alone', 'self.I_ETERNITY_SEA_FIRE'),
    ('tasks/FallenSun/script_task.py', '_fire_fallen_sun_alone', 'self.I_FALLEN_SUN_FIRE'),
    ('tasks/Sougenbi/script_task.py', '_fire_sougenbi', 'self.I_S_FIRE'),
)
FIRE_CONFIG_TASKS = ('realm_raid', 'ryou_toppa', 'evo_zone', 'orochi', 'activity_shikigami',
                     'eternity_sea', 'fallen_sun', 'sougenbi')


def _function_node(rel_path, func_name):
    tree = ast.parse((_REPO / rel_path).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    raise AssertionError(f'{rel_path}::{func_name} 不存在')


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')


def _names(obj):
    tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
    return {n.id if isinstance(n, ast.Name) else n.attr
            for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Attribute))}


def _imports(module):
    tree = ast.parse(inspect.getsource(module))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _task_with_frames(frames):
    """BaseTask 替身：`appear` 依次读取「当前帧」是否有目标，`screenshot` 推进到下一帧。

    target.coord() 返回当前帧上的坐标，用来证明点击坐标来自 fresh confirm 那一帧。
    """
    task = BaseTask.__new__(BaseTask)
    task.interval_timer = {}
    events = []
    state = {'frame': 0}
    task.device = SimpleNamespace(click=Mock(side_effect=lambda x, y, control_name: events.append(('click', x, y))),
                                  long_click=Mock())

    def appear(target, interval=None, threshold=None):
        present = frames[state['frame']]['present']
        events.append(('appear', state['frame'], present))
        return present

    def screenshot():
        state['frame'] += 1
        events.append(('screenshot', state['frame']))

    def coord():
        events.append(('coord', state['frame']))
        return frames[state['frame']]['xy']

    task.appear = appear
    task.screenshot = screenshot
    target = SimpleNamespace(name='L2_TARGET', coord=coord)
    return task, target, events


class ReactionProfileTest(TestCase):
    def test_case1_to_6_policy_ranges_come_from_existing_profiles(self):
        expected = {
            InteractionPolicy.FAST: (0.18, 0.35),
            InteractionPolicy.NORMAL: (0.45, 0.85),
            InteractionPolicy.NORMAL_HIGH: (0.60, 1.00),
            InteractionPolicy.CONFIRM: (0.55, 1.20),
            InteractionPolicy.NAVIGATION: (0.55, 1.10),
            InteractionPolicy.DELIBERATE: (0.90, 1.60),
        }
        for policy, bounds in expected.items():
            with self.subTest(policy=policy.name):
                self.assertEqual(resolve_reaction_range(policy), bounds)
                lo, hi = bounds
                for _ in range(200):
                    self.assertTrue(lo <= random_utils.random_delay(*resolve_reaction_range(policy)) <= hi)
        self.assertEqual(set(ip.POLICY_REACTION_RANGES), set(expected))

    @patch('tasks.base_task.sleep')
    def test_case7_every_attempt_resamples_reaction(self, _sleep):
        task, target, _ = _task_with_frames([{'present': True, 'xy': (1, 1)}] * 20)
        with patch('tasks.base_task.random_delay', side_effect=[0.487, 0.713, 0.561]) as rd:
            for _ in range(3):
                task.appear_then_click(target, policy=InteractionPolicy.NORMAL)
        self.assertEqual(rd.call_count, 3)
        for call in rd.call_args_list:
            self.assertEqual(call.args, rp.REACTION_NORMAL)
        samples = {round(random_utils.random_delay(*rp.REACTION_NORMAL), 6) for _ in range(50)}
        self.assertGreater(len(samples), 40)

    def test_case8_reaction_random_is_system_random(self):
        self.assertIsInstance(random_utils._rng, SystemRandom)
        with patch.object(random_utils._rng, 'uniform', return_value=0.5) as uniform:
            self.assertEqual(random_utils.random_delay(*rp.REACTION_NORMAL), 0.5)
        uniform.assert_called_once_with(0.45, 0.85)
        from tasks import base_task
        self.assertIs(base_task.random_delay, random_utils.random_delay)
        self.assertNotIn('random', _imports(ip))

    @patch('tasks.base_task.random_delay')
    @patch('tasks.base_task.sleep')
    def test_case9_immediate_adds_no_reaction(self, sleep_mock, delay_mock):
        task, target, events = _task_with_frames([{'present': True, 'xy': (3, 4)}])
        self.assertIsNone(resolve_reaction_range(InteractionPolicy.IMMEDIATE))
        self.assertTrue(task.appear_then_click(target, policy=InteractionPolicy.IMMEDIATE))
        sleep_mock.assert_not_called()
        delay_mock.assert_not_called()
        self.assertEqual(events, [('appear', 0, True), ('coord', 0), ('click', 3, 4)])

    @patch('tasks.base_task.random_delay')
    @patch('tasks.base_task.sleep')
    def test_case10_legacy_default_call_is_unchanged(self, sleep_mock, delay_mock):
        params = inspect.signature(BaseTask.appear_then_click).parameters
        self.assertIsNone(params['policy'].default)
        self.assertIsNone(params['confirm_delay'].default)
        task, target, events = _task_with_frames([{'present': True, 'xy': (5, 6)}])
        self.assertTrue(task.appear_then_click(target))
        sleep_mock.assert_not_called()
        delay_mock.assert_not_called()
        self.assertEqual(events, [('appear', 0, True), ('coord', 0), ('click', 5, 6)])

    def test_policy_validation(self):
        with self.assertRaises(TypeError):
            resolve_reaction_range('normal')
        for policy in (InteractionPolicy.FIRE_SPECIAL, InteractionPolicy.SPECIAL):
            with self.subTest(policy=policy.name), self.assertRaises(ValueError):
                resolve_reaction_range(policy)
        self.assertEqual(resolve_reaction_range(confirm_delay=(0.3, 0.6)), (0.3, 0.6))
        self.assertIsNone(resolve_reaction_range())


class FreshConfirmTest(TestCase):
    @patch('tasks.base_task.random_delay', return_value=0.5)
    @patch('tasks.base_task.sleep')
    def test_case11_13_14_reaction_then_fresh_frame_then_click_fresh_coordinate(self, sleep_mock, _delay):
        sleep_mock.side_effect = lambda _s: events.append(('sleep',))
        task, target, events = _task_with_frames([
            {'present': True, 'xy': (100, 100)},    # 第一次识别帧：坐标 A
            {'present': True, 'xy': (140, 120)},    # reaction 后的新帧：目标位置已变
        ])
        self.assertTrue(task.appear_then_click(target, policy=InteractionPolicy.NORMAL))
        self.assertEqual(events, [
            ('appear', 0, True), ('sleep',), ('screenshot', 1), ('appear', 1, True),
            ('coord', 1), ('click', 140, 120),
        ])
        task.device.click.assert_called_once()                   # CASE 11：恰一次点击

    @patch('tasks.base_task.random_delay', return_value=0.5)
    @patch('tasks.base_task.sleep')
    def test_case12_15_target_gone_after_reaction_no_click_no_retry(self, sleep_mock, delay_mock):
        task, target, events = _task_with_frames([
            {'present': True, 'xy': (100, 100)},
            {'present': False, 'xy': (100, 100)},
        ])
        self.assertFalse(task.appear_then_click(target, policy=InteractionPolicy.CONFIRM))
        task.device.click.assert_not_called()
        self.assertEqual(events, [('appear', 0, True), ('screenshot', 1), ('appear', 1, False)])
        self.assertEqual(sleep_mock.call_count, 1)
        self.assertEqual(delay_mock.call_count, 1)

    @patch('tasks.base_task.random_delay', return_value=0.2)
    @patch('tasks.base_task.sleep')
    def test_case16_one_attempt_at_most_one_physical_click(self, _sleep, _delay):
        from module.atom.click import RuleClick
        task, target, events = _task_with_frames([{'present': True, 'xy': (1, 1)}] * 3)
        action = RuleClick(roi_front=(10, 10, 20, 20), roi_back=(10, 10, 20, 20), name='L2_ACTION')
        self.assertTrue(task.appear_then_click(target, action=action, policy=InteractionPolicy.FAST))
        self.assertEqual(task.device.click.call_count, 1)
        body = _function_node('tasks/base_task.py', 'appear_then_click')
        self.assertFalse(any(isinstance(n, (ast.While, ast.For)) for n in ast.walk(body)))


class FireReactionConfigTest(TestCase):
    def test_case17_no_override_uses_public_default(self):
        self.assertEqual(fire_reaction_range(None), (0.4, 0.8))
        self.assertEqual(fire_reaction_range(FireReactionConfig()), (0.4, 0.8))
        self.assertEqual((ip.DEFAULT_FIRE_REACTION_MIN_MS / 1000, ip.DEFAULT_FIRE_REACTION_MAX_MS / 1000),
                         rp.REACTION_FIRE)

    def test_case18_20_24_override_and_ms_to_seconds(self):
        self.assertEqual(fire_reaction_range(FireReactionConfig(fire_reaction_min_ms=300, fire_reaction_max_ms=600)),
                         (0.3, 0.6))
        fixed = FireReactionConfig(fire_reaction_min_ms=650, fire_reaction_max_ms=650)
        self.assertEqual(fire_reaction_range(fixed), (0.65, 0.65))
        self.assertEqual(random_utils.random_delay(*fire_reaction_range(fixed)), 0.65)
        self.assertEqual(fire_reaction_range(FireReactionConfig(fire_reaction_min_ms=1234, fire_reaction_max_ms=1234)),
                         (1.234, 1.234))

    def test_case19_each_task_keeps_its_own_override(self):
        from tasks.EvoZone.config import EvoZone
        from tasks.RealmRaid.config import RealmRaid
        from tasks.RyouToppa.config import RyouToppa
        evo = EvoZone(fire_reaction={'fire_reaction_min_ms': 400, 'fire_reaction_max_ms': 700})
        rr = RealmRaid(fire_reaction={'fire_reaction_min_ms': 600, 'fire_reaction_max_ms': 1000})
        rt = RyouToppa()
        self.assertEqual(fire_reaction_range(evo.fire_reaction), (0.4, 0.7))
        self.assertEqual(fire_reaction_range(rr.fire_reaction), (0.6, 1.0))
        self.assertEqual(fire_reaction_range(rt.fire_reaction), (0.4, 0.8))
        self.assertIsNot(evo.fire_reaction, rt.fire_reaction)

    def test_case21_22_23_invalid_values_rejected_by_config_layer(self):
        for kwargs in ({'fire_reaction_min_ms': 900, 'fire_reaction_max_ms': 800},
                       {'fire_reaction_min_ms': -1},
                       {'fire_reaction_max_ms': 5001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                FireReactionConfig(**kwargs)
        self.assertEqual(FireReactionConfig(fire_reaction_min_ms=0, fire_reaction_max_ms=5000).fire_reaction_max_ms, 5000)

    def test_case21_invalid_assignment_is_rejected_and_state_is_kept(self):
        # OASX 单字段修改走 setattr（ConfigModel.script_set_arg 捕获 ValidationError 后不保存）。
        from tasks.Orochi.config import Orochi
        group = Orochi().fire_reaction
        for field, value in (('fire_reaction_min_ms', 900), ('fire_reaction_max_ms', 300),
                             ('fire_reaction_min_ms', -5), ('fire_reaction_max_ms', 6000)):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                setattr(group, field, value)
            self.assertEqual((group.fire_reaction_min_ms, group.fire_reaction_max_ms), (400, 800))
        group.fire_reaction_max_ms = 650
        group.fire_reaction_min_ms = 650
        self.assertEqual(fire_reaction_range(group), (0.65, 0.65))

    def test_runtime_never_swaps_an_invalid_range(self):
        broken = SimpleNamespace(fire_reaction_min_ms=800, fire_reaction_max_ms=400)
        self.assertEqual(fire_reaction_range(broken), (0.8, 0.4))
        with self.assertRaises(ValueError):
            random_utils.random_delay(*fire_reaction_range(broken))

    def test_schema_template_and_i18n_are_in_sync(self):
        template = json.loads((_REPO / 'config' / 'template.json').read_text(encoding='utf-8'))
        i18n = json.loads((_REPO / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8'))
        for task in FIRE_CONFIG_TASKS:
            with self.subTest(task=task):
                self.assertEqual(template[task]['fire_reaction'],
                                 {'fire_reaction_min_ms': 400, 'fire_reaction_max_ms': 800})
        for key in ('fire_reaction', 'fire_reaction_min_ms', 'fire_reaction_min_ms_help',
                    'fire_reaction_max_ms', 'fire_reaction_max_ms_help'):
            self.assertIn(key, i18n)
        schema = FireReactionConfig.model_json_schema()['properties']
        self.assertEqual((schema['fire_reaction_min_ms']['minimum'], schema['fire_reaction_max_ms']['maximum']),
                         (0, 5000))


class FireOwnerBehaviourTest(TestCase):
    """CASE 18 / 19 / 25 / 26：驱动真实 battle-entry 状态机，确认区间来自各自任务配置、契约不变。"""

    def _drive(self, module_path, task_cls, fire_method, fire_attr, wait_method, config_attr, group, post_states):
        import importlib
        module = importlib.import_module(module_path)
        events = []
        task = task_cls.__new__(task_cls)
        task.config = SimpleNamespace(**{config_attr: SimpleNamespace(fire_reaction=group)})
        task.device = SimpleNamespace(image='F', click_record_clear=Mock())
        task.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        battle_iter = iter([False] * 20)
        task.is_in_battle = Mock(side_effect=lambda *_a, **_k: events.append('positive_check') or next(battle_iter))
        fire_asset = getattr(task_cls, fire_attr)
        task.appear = Mock(side_effect=lambda tgt, **kw: events.append('appear_fire') or tgt is fire_asset)
        task.appear_then_click = Mock(side_effect=lambda *a, **kw: events.append(('click', a, kw)) or True)
        setattr(task, wait_method, Mock(side_effect=list(post_states)))
        with patch.object(module, 'random_delay', side_effect=lambda lo, hi: events.append(('reaction', lo, hi)) or lo), \
                patch.object(module, 'sleep', side_effect=lambda s: events.append('sleep')):
            result = getattr(task, fire_method)()
        return result, events, fire_asset

    def test_case18_19_25_26_orochi_and_evozone_use_their_own_override_per_attempt(self):
        from tasks.EvoZone.script_task import ScriptTask as EvoZone
        from tasks.Orochi.script_task import ScriptTask as Orochi
        cases = (
            ('tasks.EvoZone.script_task', EvoZone, '_fire_evozone_alone', 'I_EVOZONE_FIRE', '_wait_evozone_fire_state',
             'evo_zone', FireReactionConfig(fire_reaction_min_ms=300, fire_reaction_max_ms=600), (0.3, 0.6)),
            ('tasks.Orochi.script_task', Orochi, '_fire_orochi_alone', 'I_OROCHI_FIRE', '_wait_orochi_fire_state',
             'orochi', FireReactionConfig(fire_reaction_min_ms=700, fire_reaction_max_ms=900), (0.7, 0.9)),
        )
        for module_path, cls, method, attr, wait, cfg, group, bounds in cases:
            with self.subTest(task=cls.__module__):
                result, events, fire_asset = self._drive(module_path, cls, method, attr, wait, cfg, group,
                                                         post_states=('retryable', 'battle'))
                self.assertTrue(result)
                reactions = [e for e in events if isinstance(e, tuple) and e[0] == 'reaction']
                self.assertEqual(reactions, [('reaction', *bounds)] * 2)          # 两次 attempt 各采样一次
                clicks = [e for e in events if isinstance(e, tuple) and e[0] == 'click']
                self.assertEqual(len(clicks), 2)
                for _, args, kwargs in clicks:
                    self.assertIs(args[0], fire_asset)
                    self.assertNotIn('policy', kwargs)
                    self.assertNotIn('confirm_delay', kwargs)
                first = events.index(('reaction', *bounds))
                # reaction → sleep → fresh screenshot → positive-state 检查 → 按钮仍在 → click
                self.assertEqual(events[first + 1:first + 5], ['sleep', 'screenshot', 'positive_check', 'appear_fire'])
                self.assertEqual(events[first + 5][0], 'click')


class FireContractStaticTest(TestCase):
    def test_case25_26_27_35_every_fire_owner_keeps_its_contract(self):
        for rel_path, func_name, target_src in FIRE_OWNERS:
            with self.subTest(owner=f'{rel_path}::{func_name}'):
                node = _function_node(rel_path, func_name)
                text = (_REPO / rel_path).read_text(encoding='utf-8')
                calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
                reaction_calls = [n for n in calls if _call_name(n) == 'random_delay'
                                  and n.args and isinstance(n.args[0], ast.Starred)
                                  and isinstance(n.args[0].value, ast.Call)
                                  and _call_name(n.args[0].value) == 'fire_reaction_range']
                self.assertEqual(len(reaction_calls), 1)                         # 唯一 FIRE reaction owner
                loops = [n for n in ast.walk(node) if isinstance(n, ast.For)]
                self.assertTrue(any(reaction_calls[0] in list(ast.walk(loop)) for loop in loops))   # 每 attempt 采样
                self.assertTrue(any(isinstance(n, ast.Call) and _call_name(n) == 'range' for loop in loops
                                    for n in ast.walk(loop.iter)))                 # 有限 attempt 仍由 owner 拥有
                fire_clicks = [n for n in calls if _call_name(n) == 'appear_then_click' and n.args
                               and ast.get_source_segment(text, n.args[0]) == target_src]
                self.assertEqual(len(fire_clicks), 1)
                self.assertFalse({kw.arg for kw in fire_clicks[0].keywords} & {'policy', 'confirm_delay'})
                segment = ast.get_source_segment(text, node)
                tail = segment[segment.index(ast.get_source_segment(text, reaction_calls[0])):]
                tail = tail[:tail.index(ast.get_source_segment(text, fire_clicks[0]))]
                self.assertIn('sleep(', tail)                                     # reaction 真的等待
                self.assertIn('self.screenshot()', tail)                          # fresh frame
                self.assertTrue(any(tok in tail for tok in ('is_in_battle', '_is_active_battle_entry',
                                                            '_classify_room_entry_state',
                                                            '_classify_climb_fire_state',
                                                            '_classify_orochi_wild_fire_state',
                                                            '_classify_eternity_sea_fire_state',
                                                            '_classify_fallen_sun_fire_state',
                                                            '_classify_sougenbi_fire_state')))   # positive-state

    def test_fire_reaction_range_only_used_by_fire_owners_and_reaction_fire_not_hardcoded(self):
        owners = {(rel, func) for rel, func, _ in FIRE_OWNERS}
        found = set()
        for path in (_REPO / 'tasks').rglob('*.py'):
            rel = path.relative_to(_REPO).as_posix()
            text = path.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(text)
            self.assertNotIn('REACTION_FIRE', {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}, rel)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if any(isinstance(n, ast.Call) and _call_name(n) == 'fire_reaction_range' for n in ast.walk(node)):
                        found.add((rel, node.name))
        self.assertEqual(found, owners)

    def test_fire_config_is_propagated_not_guessed(self):
        gi = _function_node('tasks/Component/GeneralInvite/general_invite.py', 'click_fire')
        self.assertEqual([a.arg for a in gi.args.args], ['self', 'fire_reaction'])
        gi_src = inspect.getsource(__import__('tasks.Component.GeneralInvite.general_invite',
                                              fromlist=['GeneralInvite']).GeneralInvite)
        for forbidden in ('self.config', 'script_name', 'config_name', 'read_json'):
            self.assertNotIn(forbidden, gi_src)
        for rel, task in (('tasks/Orochi/script_task.py', 'orochi'), ('tasks/EvoZone/script_task.py', 'evo_zone')):
            text = (_REPO / rel).read_text(encoding='utf-8')
            self.assertEqual(text.count(f'fire_reaction=self.config.{task}.fire_reaction'), 2)


class TimingOwnershipTest(TestCase):
    def test_case28_29_settlement_does_not_use_l2_or_fire_config(self):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        settlement = [name for name in vars(GeneralBattle) if 'settlement' in name and callable(getattr(GeneralBattle, name))]
        self.assertGreaterEqual(len(settlement), 10)
        for name in settlement:
            with self.subTest(method=name):
                names = _names(getattr(GeneralBattle, name))
                for forbidden in ('InteractionPolicy', 'policy', 'confirm_delay', 'fire_reaction_range',
                                  'fire_reaction', 'REACTION_FAST', 'REACTION_NORMAL', 'REACTION_FIRE'):
                    self.assertNotIn(forbidden, names)
        # Settlement 的 0.10~0.30 observe 间隔仍是它自己的常量，不是 Reaction Profile。
        self.assertEqual(GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE, (0.10, 0.30))
        self.assertNotIn(GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE, rp.REACTION_PROFILES.values())

    def test_case30_31_32_no_reaction_below_l2(self):
        from module import click_pipeline
        from module.device import control
        from module.device.method import minitouch
        reaction_names = {'InteractionPolicy', 'resolve_reaction_range', 'fire_reaction_range', 'random_delay',
                          'confirm_delay', 'REACTION_FAST', 'REACTION_NORMAL', 'REACTION_FIRE'}
        for module in (click_pipeline, control, minitouch):
            with self.subTest(module=module.__name__):
                self.assertFalse(_imports(module) & {'module.interaction_policy', 'module.reaction_profile'})
        for fn in (click_pipeline.execute_single_click, control.Control.click, control.Control.click_with_backend,
                   control.Control._dispatch_click, minitouch.Minitouch.click_minitouch):
            with self.subTest(fn=fn.__qualname__):
                self.assertFalse(_names(fn) & (reaction_names | {'sleep', 'screenshot'}))

    def test_case33_fatigue_is_not_part_of_l2(self):
        from module import fatigue
        self.assertFalse(_imports(ip) & {'module.fatigue'})
        self.assertNotIn('module.interaction_policy', _imports(fatigue))
        self.assertFalse(_names(BaseTask.appear_then_click) & {'fatigue', 'FatigueManager', 'macro_idle'})
        self.assertFalse(_names(ip.resolve_reaction_range) & {'sleep', 'screenshot', 'Timer'})

    @patch('tasks.base_task.random_delay', return_value=0.3)
    @patch('tasks.base_task.sleep')
    def test_case34_policy_and_legacy_confirm_delay_cannot_stack(self, sleep_mock, delay_mock):
        task, target, events = _task_with_frames([{'present': True, 'xy': (1, 1)}] * 3)
        with self.assertRaises(ValueError):
            task.appear_then_click(target, policy=InteractionPolicy.NORMAL, confirm_delay=(0.45, 0.85))
        self.assertEqual(events, [])
        sleep_mock.assert_not_called()
        delay_mock.assert_not_called()
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        gb = GeneralBattle.__new__(GeneralBattle)
        gb.screenshot = Mock()
        gb.appear = Mock(return_value=False)
        gb.appear_then_click = BaseTask.appear_then_click.__get__(gb)
        gb.interval_timer = {}
        with self.assertRaises(ValueError):
            gb.check_lock(True, object(), SimpleNamespace(name='U'), confirm_delay=(0.1, 0.2),
                          policy=InteractionPolicy.FAST)

    def test_case34_35_static_no_stacked_reaction_call_sites(self):
        offenders = []
        legacy_profile_literals = []
        for sub in ('tasks', 'module'):
            for path in (_REPO / sub).rglob('*.py'):
                rel = path.relative_to(_REPO).as_posix()
                text = path.read_text(encoding='utf-8', errors='ignore')
                if 'confirm_delay=REACTION_' in text:
                    legacy_profile_literals.append(rel)
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.Call) and _call_name(node) in ('appear_then_click', 'check_lock'):
                        values = {kw.arg: kw.value for kw in node.keywords if kw.arg in ('policy', 'confirm_delay')}
                        # 形参原样透传（check_lock）不算叠加：两者同时非空会在 appear_then_click 里被拒绝。
                        passthrough = all(isinstance(v, ast.Name) and v.id == k for k, v in values.items())
                        if len(values) == 2 and not passthrough:
                            offenders.append((rel, node.lineno))
        self.assertEqual(offenders, [])
        self.assertEqual(legacy_profile_literals, [])    # 具名 profile 一律经 policy= 表达

    def test_case35_ordinary_reaction_consumers_use_policy(self):
        expected = {
            'tasks/EvoZone/script_task.py': 4,
            'tasks/Orochi/script_task.py': 5,
            'tasks/RealmRaid/script_task.py': 6,
            'tasks/RyouToppa/script_task.py': 3,
            'tasks/Exploration/base.py': 5,
            'tasks/Exploration/script_task.py': 3,
            'tasks/ActivityShikigami/page.py': 2,
            # L2-2（docs/L2_INTERACTION_POLICY_MAP.md）
            'tasks/Component/GeneralInvite/general_invite.py': 4,
            'tasks/Component/GeneralBattle/general_battle.py': 3,
            # L2 Stage C1-A1（C0 复核后的首批 4 处，docs/L2_INTERACTION_POLICY_MAP.md §4）
            'tasks/Dokan/page.py': 1,
            'tasks/Pets/script_task.py': 1,
            'tasks/SixRealms/common.py': 2,
        }
        actual = {}
        for path in (_REPO / 'tasks').rglob('*.py'):
            rel = path.relative_to(_REPO).as_posix()
            count = 0
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8', errors='ignore'))):
                if isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if kw.arg == 'policy' and isinstance(kw.value, ast.Attribute) \
                                and getattr(kw.value.value, 'id', '') == 'InteractionPolicy':
                            count += 1
            if count:
                actual[rel] = count
        self.assertEqual(actual, expected)
        # NORMAL_HIGH 保留定义、当前无生产 consumer（不为「有这个档位」硬找按钮）
        self.assertNotIn('NORMAL_HIGH', ''.join((_REPO / rel).read_text(encoding='utf-8') for rel in expected))
