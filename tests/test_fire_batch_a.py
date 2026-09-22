# This Python file uses the following encoding: utf-8
"""L2-3B FIRE Batch A 回归护栏：Orochi 野队 / EternitySea / FallenSun / Sougenbi 的 battle-entry 状态机。

Pre-State → FIRE Reaction（任务配置）→ Fresh Confirm → 单次点击 → 正向 Battle Entry（准备 / 战斗页）→
有界重试 / 失败。驱动真实状态机方法，截图 / 识别用帧序列替身；`Timer` 用确定性替身（可轮询次数 = limit）。
"""

import ast
import importlib
import inspect
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.interaction_policy import fire_reaction_range
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets as GBA
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets as GIA
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.GameUi.assets import GameUiAssets as GUA

_REPO = Path(__file__).resolve().parents[1]

PREPARE = GBA.I_PREPARE_HIGHLIGHT.name
PREPARE_DARK = GBA.I_PREPARE_DARK.name
BATTLE = GBA.I_BATTLE_INFO.name
WIN = GBA.I_WIN.name
REWARD = GBA.I_REWARD.name
ROOM = GIA.I_GI_EMOJI_1.name
MATCHING = 'I_MATCHING'
WILD_FIRE = 'I_OROCHI_WILD_FIRE'


class _FakeTimer:
    """确定性 Timer：`reached()` 在第 `limit` 次之后为 True（limit 取整后作为允许的轮询次数）。"""

    def __init__(self, limit, count=0):
        self.limit = limit
        self.calls = 0

    def start(self):
        return self

    def reached(self):
        self.calls += 1
        return self.calls > int(self.limit)


def _spec(name):
    """四条 FIRE 路径的差异点：模块、类、方法、FIRE 目标、ready 帧、配置挂载、成功 / 失败返回值。"""
    if name == 'eternity_sea':
        from tasks.EternitySea.script_task import ScriptTask
        return dict(module='tasks.EternitySea.script_task', cls=ScriptTask, method='_fire_eternity_sea_alone',
                    fire=ScriptTask.I_ETERNITY_SEA_FIRE.name, ready={ScriptTask.I_ETERNITY_SEA_FIRE.name},
                    broken_ready={ScriptTask.I_ETERNITY_SEA_FIRE.name, WIN},
                    timeout_const='ETERNITY_SEA_FIRE_TIMEOUT', max_tries=4,
                    config=lambda cfg: SimpleNamespace(model=SimpleNamespace(eternity_sea=SimpleNamespace(fire_reaction=cfg))),
                    ok=True, fail=False, abnormal=False)
    if name == 'fallen_sun':
        from tasks.FallenSun.script_task import ScriptTask
        return dict(module='tasks.FallenSun.script_task', cls=ScriptTask, method='_fire_fallen_sun_alone',
                    fire=ScriptTask.I_FALLEN_SUN_FIRE.name, ready={ScriptTask.I_FALLEN_SUN_FIRE.name},
                    broken_ready={ScriptTask.I_FALLEN_SUN_FIRE.name, REWARD},
                    timeout_const='FALLEN_SUN_FIRE_TIMEOUT', max_tries=4,
                    config=lambda cfg: SimpleNamespace(fallen_sun=SimpleNamespace(fire_reaction=cfg)),
                    ok=True, fail=False, abnormal=False)
    from tasks.Sougenbi.script_task import ScriptTask
    return dict(module='tasks.Sougenbi.script_task', cls=ScriptTask, method='_fire_sougenbi',
                fire=ScriptTask.I_S_FIRE.name, ready={ScriptTask.I_S_CHECK_SOUGENBI.name, ScriptTask.I_S_FIRE.name},
                broken_ready={ScriptTask.I_S_FIRE.name},     # 挑战键还在但已不在业原火页
                timeout_const='SOUGENBI_FIRE_TIMEOUT', max_tries=4,
                config=lambda cfg: SimpleNamespace(sougenbi=SimpleNamespace(fire_reaction=cfg)),
                ok=True, fail=False, abnormal=False)


TASKS = ('eternity_sea', 'fallen_sun', 'sougenbi')
CFG_300_600 = FireReactionConfig(fire_reaction_min_ms=300, fire_reaction_max_ms=600)


def _drive(spec, frames, cfg=CFG_300_600, timeout=None):
    """驱动真实 FIRE 方法。`frames`：每次 screenshot 后的可见 marker 名集合；用尽后停在最后一帧。"""
    module = importlib.import_module(spec['module'])
    task = spec['cls'].__new__(spec['cls'])
    task.config = spec['config'](cfg)
    task.device = SimpleNamespace(image='F', click_record_clear=Mock())
    events = []
    state = {'i': 0}
    current = lambda: frames[min(max(state['i'] - 1, 0), len(frames) - 1)]   # 第 n 次 screenshot 看到 frames[n-1]

    def screenshot():
        state['i'] += 1
        events.append(('screenshot', state['i']))

    def appear(target, interval=None, threshold=None):
        return getattr(target, 'name', target) in current()

    def appear_then_click(target, interval=None, threshold=None, **kw):
        if target.name not in current():
            return False
        events.append(('click', state['i'], kw))
        return True

    task.screenshot = screenshot
    task.appear = appear
    task.appear_then_click = appear_then_click
    task.is_in_room = lambda is_screenshot=True: ROOM in current()
    task.I_MATCHING = SimpleNamespace(name=MATCHING)
    for attr, value in spec.get('extra', {}).items():
        setattr(task, attr, value)
    patches = [
        patch.object(module, 'Timer', _FakeTimer),
        patch.object(module, 'sleep', side_effect=lambda s: events.append(('sleep', s))),
        patch.object(module, 'random_delay', side_effect=lambda lo, hi: events.append(('reaction', lo, hi)) or lo),
    ]
    if timeout is not None:
        patches.append(patch.object(module, spec['timeout_const'], timeout))
    for p in patches:
        p.start()
    try:
        result = getattr(task, spec['method'])()
    finally:
        for p in reversed(patches):
            p.stop()
    return result, events


def _clicks(events):
    return [e for e in events if e[0] == 'click']


def _reactions(events):
    return [e for e in events if e[0] == 'reaction']


class FireBatchABehaviourTest(TestCase):
    def test_1_success_reaction_then_fresh_confirm_then_single_click_then_positive_entry(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], spec['ready'], {PREPARE}])
                self.assertEqual(result, spec['ok'])
                self.assertEqual(_reactions(events), [('reaction', 0.3, 0.6)])   # 任务配置 300~600ms → 秒
                self.assertEqual(len(_clicks(events)), 1)
                i = events.index(('reaction', 0.3, 0.6))
                self.assertEqual(events[i + 1][0], 'sleep')
                self.assertEqual(events[i + 2][0], 'screenshot')                 # fresh frame
                self.assertEqual(events[i + 3][0], 'click')
                self.assertEqual(events[i + 3][1], 2)                            # 点在 reaction 之后的新帧
                self.assertNotIn('policy', events[i + 3][2])

    def test_2_target_gone_during_reaction_zero_click(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], set()])
                self.assertEqual(result, spec['fail'])
                self.assertEqual(_clicks(events), [])

    def test_3_pre_state_changed_during_reaction_no_stale_click(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], spec['broken_ready']])
                self.assertNotEqual(result, spec['ok'])
                self.assertEqual(_clicks(events), [])

    def test_4_button_gone_without_positive_state_is_not_success(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], spec['ready'], set()])
                self.assertEqual(result, spec['fail'])
                self.assertEqual(len(_clicks(events)), 1)                         # 过渡期只等不点

    def test_5_8_still_ready_retries_with_fresh_reaction_and_is_bounded(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready']])
                self.assertEqual(result, spec['fail'])
                self.assertEqual(len(_clicks(events)), spec['max_tries'])
                self.assertEqual(len(_reactions(events)), spec['max_tries'])      # 每次 attempt 独立采样
                reaction_idx = [i for i, e in enumerate(events) if e[0] == 'reaction']
                click_idx = [i for i, e in enumerate(events) if e[0] == 'click']
                for r, c in zip(reaction_idx, click_idx):
                    self.assertLess(r, c)

    def test_6_transition_waits_without_clicking_then_positive(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [set(), set(), {PREPARE_DARK}])
                self.assertEqual(result, spec['ok'])
                self.assertEqual(_clicks(events), [])
                self.assertEqual(_reactions(events), [])

    def test_6_transition_after_click_then_battle_page(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], spec['ready'], set(), set(), {BATTLE}])
                self.assertEqual(result, spec['ok'])
                self.assertEqual(len(_clicks(events)), 1)

    def test_7_result_or_reward_residue_is_not_a_new_battle(self):
        for name in TASKS:
            spec = _spec(name)
            for residue in (WIN, REWARD):
                with self.subTest(task=name, residue=residue):
                    result, events = _drive(spec, [spec['ready'] | {residue}])
                    self.assertEqual(result, spec['abnormal'])
                    self.assertNotEqual(result, spec['ok'])
                    self.assertEqual(_clicks(events), [])
                    result, events = _drive(spec, [spec['ready'], spec['ready'], {residue}])
                    self.assertEqual(result, spec['abnormal'])
                    self.assertEqual(len(_clicks(events)), 1)

    def test_9_total_time_budget_ends_the_attempts(self):
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready']], timeout=2)
                self.assertEqual(result, spec['fail'])
                self.assertEqual(len(_clicks(events)), 2)

    def test_default_config_is_400_800_and_each_task_has_its_own_group(self):
        from tasks.EternitySea.config import EternitySea
        from tasks.FallenSun.config import FallenSun
        from tasks.Orochi.config import Orochi
        from tasks.Sougenbi.config import Sougenbi
        models = [EternitySea(), FallenSun(), Sougenbi(), Orochi()]
        for model in models:
            self.assertEqual(fire_reaction_range(model.fire_reaction), (0.4, 0.8))
        self.assertEqual(len({id(m.fire_reaction) for m in models}), 4)
        spec = _spec('eternity_sea')
        _, events = _drive(spec, [spec['ready'], spec['ready'], {PREPARE}],
                           cfg=FireReactionConfig(fire_reaction_min_ms=700, fire_reaction_max_ms=900))
        self.assertEqual(_reactions(events), [('reaction', 0.7, 0.9)])


class CallerHandoffTest(TestCase):
    """CASE 10：成功只交接一次 run_general_battle；FIRE 失败不交接、不计入战斗次数。"""

    def _battle(self, task):
        def run_general_battle(*args, **kwargs):
            task.current_count += 1
            return True
        return Mock(side_effect=run_general_battle)

    def test_eternity_sea_run_alone(self):
        from tasks.EternitySea.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(model=SimpleNamespace(eternity_sea=SimpleNamespace(
            general_battle_config=SimpleNamespace(lock_team_enable=True),
            eternity_sea_config=SimpleNamespace(limit_count=1, limit_time=SimpleNamespace(hour=1, minute=0, second=0)))))
        task.current_count, task.start_time = 0, datetime.now()
        task.goto_page = Mock()
        task._enter_eternity_sea = Mock()
        task.screenshot = Mock()
        task.appear = Mock(return_value=True)
        task.exit_room = Mock()
        task._fire_eternity_sea_alone = Mock(side_effect=[False, True])
        task.run_general_battle = self._battle(task)
        self.assertTrue(task.run_alone())
        self.assertEqual(task.run_general_battle.call_count, 1)
        self.assertEqual(task.current_count, 1)

    def test_fallen_sun_run_alone(self):
        from tasks.FallenSun.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(fallen_sun=SimpleNamespace(
            general_battle_config=SimpleNamespace(lock_team_enable=True),
            fallen_sun_config=SimpleNamespace(layer='L')))
        task.current_count, task.limit_count = 0, 1
        task.start_time, task.limit_time = datetime.now(), timedelta(hours=1)
        for name in ('goto_page', 'fallen_sun_enter', 'check_layer', 'check_lock', 'screenshot'):
            setattr(task, name, Mock())
        task.appear_then_click = Mock(return_value=False)
        task.appear = Mock(return_value=True)
        task._fire_fallen_sun_alone = Mock(side_effect=[False, True])
        task.run_general_battle = self._battle(task)
        task.run_alone()
        self.assertEqual(task.run_general_battle.call_count, 1)
        self.assertEqual(task.current_count, 1)

    def test_sougenbi_run(self):
        from module.exception import TaskEnd
        from tasks.Sougenbi.config import SougenbiClass
        from tasks.Sougenbi.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(sougenbi=SimpleNamespace(
            sougenbi_config=SimpleNamespace(limit_time=SimpleNamespace(hour=1, minute=0, second=0), buff_enable=False,
                                            sougenbi_class=SougenbiClass.GREED, limit_count=1),
            switch_soul_config=SimpleNamespace(enable=False, enable_switch_by_name=False),
            general_battle_config=SimpleNamespace(lock_team_enable=True)))
        task.current_count, task.start_time = 0, datetime.now()
        for name in ('goto_page', 'screenshot', 'check_lock', 'set_next_run'):
            setattr(task, name, Mock())
        task.appear = Mock(return_value=True)
        task.O_S_GREED = SimpleNamespace(ocr=Mock(return_value=5))
        task.device = SimpleNamespace(image='F')
        task._fire_sougenbi = Mock(side_effect=[False, True])
        task.run_general_battle = self._battle(task)
        with patch('tasks.Sougenbi.script_task.sleep'), self.assertRaises(TaskEnd):
            task.run()
        self.assertEqual(task.run_general_battle.call_count, 1)
        self.assertEqual(task.current_count, 1)


class TimingOwnershipStaticTest(TestCase):
    CALLERS = (
        ('tasks/EternitySea/script_task.py', 'run_alone', 'I_ETERNITY_SEA_FIRE', '_fire_eternity_sea_alone'),
        ('tasks/FallenSun/script_task.py', 'run_alone', 'I_FALLEN_SUN_FIRE', '_fire_fallen_sun_alone'),
        ('tasks/Sougenbi/script_task.py', 'run', 'I_S_FIRE', '_fire_sougenbi'),
    )

    @staticmethod
    def _func(rel, name):
        text = (_REPO / rel).read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node, ast.get_source_segment(text, node)
        raise AssertionError(f'{rel}::{name}')

    def test_callers_no_longer_click_fire_themselves_or_add_reaction(self):
        for rel, caller, target, fire_method in self.CALLERS:
            node, src = self._func(rel, caller)
            with self.subTest(caller=f'{rel}::{caller}'):
                self.assertNotIn(f'appear_then_click(self.{target}', src)
                self.assertIn(f'self.{fire_method}()', src)
                self.assertNotIn('random_delay', src)
                self.assertNotIn('fire_reaction_range', src)

    def test_fire_methods_single_reaction_owner_no_ordinary_policy_no_wide_detector(self):
        for rel, _caller, target, fire_method in self.CALLERS:
            node, src = self._func(rel, fire_method)
            with self.subTest(method=fire_method):
                self.assertEqual(src.count('random_delay('), 1)
                self.assertNotIn('policy=', src)
                self.assertNotIn('confirm_delay', src)
                self.assertNotIn('is_in_battle(', src)
                self.assertNotIn('click_record_clear', src)   # 保留既有 too-many-click 兜底
                classify = fire_method.replace('_fire_', '_classify_').replace('_alone', '') + '_fire_state'
                _, csrc = self._func(rel, classify)
                self.assertIn('is_new_battle_entry(self)', csrc)
                self.assertIn('is_battle_result_residue(self)', csrc)
                self.assertNotIn('is_in_battle(', csrc)

    def test_shared_positive_detector_excludes_result_and_reward_markers(self):
        from tasks.Component import fire_battle_entry
        names = {n.attr for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fire_battle_entry.is_new_battle_entry))))
                 if isinstance(n, ast.Attribute)}
        self.assertTrue({'I_PREPARE_HIGHLIGHT', 'I_PREPARE_DARK', 'I_BATTLE_INFO'} <= names)
        self.assertFalse(names & {'I_WIN', 'I_DE_WIN', 'I_FALSE', 'I_REWARD', 'I_REWARD_GOLD', 'I_BUFF', 'I_PRESET'})
        for rel in ('tasks/Component/fire_battle_entry.py',):
            text = (_REPO / rel).read_text(encoding='utf-8')
            for forbidden in ('screenshot', 'sleep', 'click'):
                self.assertNotIn(f'.{forbidden}(', text)

    def test_team_paths_forward_own_fire_reaction_to_general_invite(self):
        # 同一任务的组队 FIRE（GeneralInvite.click_fire）也吃本任务 fire_reaction 组，与 Orochi / EvoZone 一致
        for rel, expr in (('tasks/FallenSun/script_task.py', 'self.config.fallen_sun.fire_reaction'),
                          ('tasks/EternitySea/script_task.py', 'self._task_config.fire_reaction')):
            text = (_REPO / rel).read_text(encoding='utf-8')
            calls = [n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == 'run_invite']
            with self.subTest(file=rel):
                self.assertEqual(len(calls), 2)
                for call in calls:
                    kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
                    self.assertEqual(kw.get('fire_reaction'), expr)
