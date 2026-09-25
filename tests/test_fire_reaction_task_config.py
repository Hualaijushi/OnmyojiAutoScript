# This Python file uses the following encoding: utf-8
"""FIRE 点击前延迟配置接入验证（RealmRaid / RyouToppa / EvoZone / Orochi 单人+组队 / ActivityShikigami /
EternitySea / FallenSun / Sougenbi）。

本轮把 L2 worktree 已实现的 `tasks/Component/config_fire_reaction.py` + `module/interaction_policy.py`
的 `fire_reaction_range` 最小范围接入本仓库运行的 master：只换 8 个任务既有 FIRE 点击的 reaction 来源
（硬编码 `REACTION_FIRE` / 完全无 reaction → 任务配置，默认 400~800ms），不改 FIRE FSM 形状、不改正向战斗
判据、不改重试超时契约。（L1 + L2 集成后 EternitySea / FallenSun / Sougenbi 由 Batch A 专用 owner 接管，见
`tests/test_fire_batch_a.py`；本文件对这三者改为驱动真实 owner 验证配置消费。）

真实验证要求「真实驱动」而不是只读源码字符串：对已有成熟 FSM（RealmRaid.fire / Orochi._fire_orochi_alone /
EvoZone._fire_evozone_alone / ActivityShikigami._enter_climb_battle / GeneralInvite.click_fire），复用
既有测试文件里已验证过的、能真正走到「FIRE 就绪 → reaction → click」分支的替身构造，只是把默认
`FireReactionConfig()` 换成明显不同的自定义区间，断言 `random_delay` 实际收到的参数确实来自这个自定义
配置（而不是恒等于旧的硬编码 0.4~0.8s）。RealmRaid._fire_again / RyouToppa.attack_area 沿用既有源码级
断言（其余测试文件已覆盖 FSM 形状，这里只做 fire_reaction_range 换算 + 真实配置隔离的独立证明）。
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from pydantic import ValidationError

from module.interaction_policy import fire_reaction_range
from tasks.Component.config_fire_reaction import FireReactionConfig

# 复用既有测试文件里已验证能正确驱动到「FIRE 就绪 → click」分支的模块级替身构造，
# 不重新发明一遍容易写错的状态序列。
from tests.test_fire_reaction_fsm import _RRHarness, _FakeTimer as _RRFakeTimer, _seq as _rr_seq
from tests.test_second_batch_fire_fsm import _mk as _oe_mk, _TASKS as _OE_TASKS
from tests.test_general_invite_challenge_reaction import _CF, _FakeTimer as _GIFakeTimer

from tasks.RealmRaid.config import RealmRaid as RealmRaidConfig
from tasks.RyouToppa.config import RyouToppa as RyouToppaConfig
from tasks.EvoZone.config import EvoZone as EvoZoneConfig
from tasks.Orochi.config import Orochi as OrochiConfig
from tasks.ActivityShikigami.config import ActivityShikigami as ActivityShikigamiConfig
from tasks.EternitySea.config import EternitySea as EternitySeaConfig
from tasks.FallenSun.config import FallenSun as FallenSunConfig
from tasks.Sougenbi.config import Sougenbi as SougenbiConfig

TASK_CONFIG_CLASSES = {
    'realm_raid': RealmRaidConfig, 'ryou_toppa': RyouToppaConfig, 'evo_zone': EvoZoneConfig,
    'orochi': OrochiConfig, 'activity_shikigami': ActivityShikigamiConfig,
    'eternity_sea': EternitySeaConfig, 'fallen_sun': FallenSunConfig, 'sougenbi': SougenbiConfig,
}


# =====================================================================================
# 一、8 个任务均有独立的 fire_reaction 配置组，默认 400/800ms，互相隔离
# =====================================================================================

class FireReactionConfigPresenceTest(TestCase):
    def test_all_eight_tasks_have_their_own_fire_reaction_group(self):
        for task_key, cls in TASK_CONFIG_CLASSES.items():
            with self.subTest(task=task_key):
                model = cls()
                self.assertIsInstance(model.fire_reaction, FireReactionConfig)
                self.assertEqual(model.fire_reaction.fire_reaction_min_ms, 400)
                self.assertEqual(model.fire_reaction.fire_reaction_max_ms, 800)

    def test_each_instance_gets_its_own_fire_reaction_object(self):
        # default_factory，不是共享的可变默认值
        a, b = RealmRaidConfig(), RealmRaidConfig()
        self.assertIsNot(a.fire_reaction, b.fire_reaction)

    def test_modifying_realm_raid_does_not_affect_evo_zone(self):
        rr = RealmRaidConfig()
        ez = EvoZoneConfig()
        rr.fire_reaction.fire_reaction_min_ms = 111
        rr.fire_reaction.fire_reaction_max_ms = 222
        self.assertEqual(ez.fire_reaction.fire_reaction_min_ms, 400)
        self.assertEqual(ez.fire_reaction.fire_reaction_max_ms, 800)
        # 也验证任意两个任务两两独立（不止 RealmRaid/EvoZone 这一对）
        orochi_a, orochi_b = OrochiConfig(), OrochiConfig()
        orochi_a.fire_reaction = FireReactionConfig(fire_reaction_min_ms=999, fire_reaction_max_ms=999)
        self.assertEqual(orochi_b.fire_reaction.fire_reaction_min_ms, 400)

    def test_ms_to_seconds_conversion(self):
        cfg = FireReactionConfig(fire_reaction_min_ms=111, fire_reaction_max_ms=222)
        self.assertEqual(fire_reaction_range(cfg), (0.111, 0.222))

    def test_no_override_falls_back_to_public_default_0_4_0_8(self):
        self.assertEqual(fire_reaction_range(None), (0.4, 0.8))


# =====================================================================================
# 二、校验：min == max 合法（固定延迟），非法区间被拒绝且旧值保持不变
# =====================================================================================

class FireReactionConfigValidationTest(TestCase):
    def test_min_equal_max_is_legal_fixed_delay(self):
        cfg = FireReactionConfig(fire_reaction_min_ms=500, fire_reaction_max_ms=500)
        self.assertEqual(fire_reaction_range(cfg), (0.5, 0.5))

    def test_min_greater_than_max_rejected_at_construction(self):
        with self.assertRaises(ValidationError):
            FireReactionConfig(fire_reaction_min_ms=800, fire_reaction_max_ms=400)

    def test_negative_and_over_limit_rejected(self):
        with self.assertRaises(ValidationError):
            FireReactionConfig(fire_reaction_min_ms=-1, fire_reaction_max_ms=800)
        with self.assertRaises(ValidationError):
            FireReactionConfig(fire_reaction_min_ms=400, fire_reaction_max_ms=5001)

    def test_invalid_assignment_rejected_and_old_value_kept(self):
        cfg = FireReactionConfig(fire_reaction_min_ms=400, fire_reaction_max_ms=800)
        with self.assertRaises(ValidationError):
            cfg.fire_reaction_max_ms = 100   # 会小于 min
        self.assertEqual(cfg.fire_reaction_max_ms, 800)   # 旧值保持不变
        with self.assertRaises(ValidationError):
            cfg.fire_reaction_min_ms = 900   # 会大于 max
        self.assertEqual(cfg.fire_reaction_min_ms, 400)

    def test_runtime_does_not_swap_or_clamp_illegal_range(self):
        # fire_reaction_range 本身不做交换 / 钳制；非法区间要在配置层被拒绝，不能漏到这里
        bad = SimpleNamespace(fire_reaction_min_ms=900, fire_reaction_max_ms=100)
        self.assertEqual(fire_reaction_range(bad), (0.9, 0.1))


# =====================================================================================
# 三、真实 FIRE consumer 使用任务配置，而不是硬编码默认值（真实驱动，不只读源码）
#     用明显不同于默认 400/800 的自定义区间，证明 random_delay 收到的确实是这个自定义值。
# =====================================================================================

CUSTOM = FireReactionConfig(fire_reaction_min_ms=111, fire_reaction_max_ms=333)
CUSTOM_SECONDS = (0.111, 0.333)


class RealConsumerReadsTaskConfigTest(TestCase):
    def test_realm_raid_fire_uses_custom_config_not_hardcoded_reaction_fire(self):
        h = _RRHarness()
        h.task.config.realm_raid.fire_reaction = CUSTOM
        h.task.is_in_battle = Mock(side_effect=_rr_seq([False, False, True]))
        fire_it = _rr_seq([True, True, True])
        h.task.appear = Mock(side_effect=lambda tgt, **kw: next(fire_it) if tgt is h.task.I_FIRE else False)
        _RRFakeTimer.budget = 8
        with patch('tasks.RealmRaid.script_task.Timer', _RRFakeTimer), \
             patch('tasks.RealmRaid.script_task.sleep'), \
             patch('tasks.RealmRaid.script_task.random_delay', return_value=0.2) as m_delay:
            result = h.task.fire(2)
        self.assertIs(result, True)
        m_delay.assert_called_once_with(*CUSTOM_SECONDS)

    def test_realm_raid_fire_independent_sampling_two_attempts_two_custom_calls(self):
        h = _RRHarness()
        h.task.config.realm_raid.fire_reaction = CUSTOM
        h.task.is_in_battle = Mock(side_effect=_rr_seq([False] * 200))
        fire_it = _rr_seq([True] * 8)
        h.task.appear = Mock(side_effect=lambda tgt, **kw: next(fire_it) if tgt is h.task.I_FIRE else False)
        _RRFakeTimer.budget = 8
        with patch('tasks.RealmRaid.script_task.Timer', _RRFakeTimer), \
             patch('tasks.RealmRaid.script_task.sleep'), \
             patch('tasks.RealmRaid.script_task.random_delay', return_value=0.2) as m_delay:
            h.task.fire(1)
        self.assertGreaterEqual(m_delay.call_count, 2)
        for call in m_delay.call_args_list:
            self.assertEqual(call.args, CUSTOM_SECONDS)   # 每次 attempt 独立采样同一份任务配置

    def test_orochi_and_evozone_fire_alone_use_their_own_custom_config(self):
        for name, cls, fm, wm, rm, attr, mt, to, pct, mod in _OE_TASKS:
            with self.subTest(task=name):
                events, t, fire = _oe_mk(cls, fm, attr, in_battle=[False, False, True],
                                         fire_visible=[True, True, True])
                task_key = 'orochi' if name == 'Orochi' else 'evo_zone'
                setattr(t.config, task_key, SimpleNamespace(fire_reaction=CUSTOM))
                with patch(f'{mod}.random_delay', return_value=0.2) as m_delay:
                    self.assertIs(fire(), True)
                m_delay.assert_called_once_with(*CUSTOM_SECONDS)

    def test_general_invite_click_fire_uses_caller_supplied_config_not_default(self):
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        import tasks.Component.GeneralInvite.general_invite as gi_mod
        _GIFakeTimer.budget = 6
        h = _CF(battle=[False, False, False, True], in_room=[True], fire=[True])
        with patch.object(gi_mod, 'Timer', _GIFakeTimer), patch.object(gi_mod, 'sleep'), \
             patch.object(gi_mod, 'random_delay', return_value=0.2) as m_delay:
            result = GeneralInvite.click_fire(h.task, fire_reaction=CUSTOM)
        self.assertEqual(result, 'battle')
        self.assertEqual(len(h.clicks), 1)
        m_delay.assert_called_once_with(*CUSTOM_SECONDS)

    def test_general_invite_click_fire_default_none_still_falls_back_to_0_4_0_8(self):
        # 未传 fire_reaction 的既有 consumer（ExperienceYoukai / GoldYoukai / Hunt / Tako 等）行为不变
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        import tasks.Component.GeneralInvite.general_invite as gi_mod
        _GIFakeTimer.budget = 6
        h = _CF(battle=[False, False, False, True], in_room=[True], fire=[True])
        with patch.object(gi_mod, 'Timer', _GIFakeTimer), patch.object(gi_mod, 'sleep'), \
             patch.object(gi_mod, 'random_delay', return_value=0.6) as m_delay:
            result = GeneralInvite.click_fire(h.task)
        self.assertEqual(result, 'battle')
        m_delay.assert_called_once_with(0.4, 0.8)

    def test_activity_shikigami_enter_climb_battle_uses_custom_config(self):
        # 复用 tests/test_activity_shikigami_climb.py::EnterClimbBattleTest._mk 里已验证过的
        # 精确替身配方（真实 _classify_climb_fire_state / _wait_climb_fire_state 不 mock，
        # 只替身 _is_active_battle_entry / appear / appear_then_click 这三个输入面）。
        from module.atom.image import RuleImage
        from tasks.ActivityShikigami.script_task import ScriptTask
        import tasks.ActivityShikigami.activities.normal as normal_mod

        def _img(name):
            return RuleImage(roi_front=(1, 2, 3, 4), roi_back=(1, 2, 3, 4),
                             method='Template matching', threshold=0.8,
                             file=f'./tests/_fake/{name.lower()}.png')

        class _FakeTimer:
            budget = 8

            def __init__(self, *a, **kw):
                self.n = 0

            def start(self):
                return self

            def reached(self):
                self.n += 1
                return self.n > self.budget

        t = ScriptTask.__new__(ScriptTask)
        events = []
        t.device = SimpleNamespace(image='F', click_record_clear=Mock())
        t.conf = SimpleNamespace(fire_reaction=CUSTOM)
        t.screenshot = Mock(side_effect=lambda: events.append('screenshot'))
        t.I_ACT_FIRE = _img('I_ACT_FIRE')
        t.I_AS_BOSS_FIRE = _img('I_AS_BOSS_FIRE')
        t.I_UI_CONFIRM = _img('I_UI_CONFIRM')
        t.I_UI_CONFIRM_SAMLL = _img('I_UI_CONFIRM_SAMLL')
        active_it = _rr_seq([False, False, True])
        fire_it = _rr_seq([True])
        t._is_active_battle_entry = Mock(side_effect=lambda: next(active_it))

        def _appear(target, **kw):
            if target.name in ('I_ACT_FIRE', 'I_AS_BOSS_FIRE'):
                return next(fire_it)
            return False

        t.appear = Mock(side_effect=_appear)

        def _atc(target, **kw):
            events.append(('atc', target.name))
            return False if target.name in ('I_UI_CONFIRM', 'I_UI_CONFIRM_SAMLL') else True

        t.appear_then_click = Mock(side_effect=_atc)

        with patch.object(normal_mod, 'Timer', _FakeTimer), \
             patch.object(normal_mod.time, 'sleep', Mock()), \
             patch.object(normal_mod, 'random_delay', return_value=0.2) as m_delay:
            result = t._enter_climb_battle('ap')
        self.assertIs(result, True)
        m_delay.assert_called_once_with(*CUSTOM_SECONDS)


# =====================================================================================
# 四、EternitySea / FallenSun / Sougenbi：本轮从「完全无 reaction」新接入 confirm_delay=
#     （复用 BaseTask.appear_then_click 既有机制），只验证三个任务各自传对了区间，
#     不重新验证 appear_then_click 内部的 sleep/fresh-confirm/click（那是 base_task 自己的契约，
#     已有 tests/test_base_task_confirm_click.py 覆盖）。
# =====================================================================================

class BatchAFireOwnersReadTaskConfigTest(TestCase):
    """EternitySea / FallenSun / Sougenbi 的 FIRE 已由 L2-3B Batch A 的专用 owner 接管（`_fire_*`）：
    真实驱动 owner，证明 `random_delay` 收到的正是本任务的自定义 `fire_reaction`（不是硬编码 0.4~0.8）。"""

    def test_each_batch_a_owner_samples_from_its_own_custom_config(self):
        from tests.test_fire_batch_a import PREPARE, TASKS, _clicks, _drive, _reactions, _spec
        self.assertEqual(TASKS, ('eternity_sea', 'fallen_sun', 'sougenbi'))
        for name in TASKS:
            spec = _spec(name)
            with self.subTest(task=name):
                result, events = _drive(spec, [spec['ready'], spec['ready'], {PREPARE}], cfg=CUSTOM)
                self.assertEqual(result, spec['ok'])
                self.assertEqual(_reactions(events), [('reaction',) + CUSTOM_SECONDS])
                self.assertEqual(len(_clicks(events)), 1)

    def test_callers_do_not_carry_a_second_fire_reaction(self):
        import inspect
        from tasks.EternitySea.script_task import ScriptTask as ES
        from tasks.FallenSun.script_task import ScriptTask as FS
        from tasks.Sougenbi.script_task import ScriptTask as SG
        for cls, method in ((ES, 'run_alone'), (FS, 'run_alone'), (SG, 'run')):
            with self.subTest(caller=f'{cls.__module__}.{method}'):
                src = inspect.getsource(getattr(cls, method))
                self.assertNotIn('confirm_delay=fire_reaction_range(', src)


# =====================================================================================
# 五、没有双重 Reaction：逐个任务确认唯一 timing owner，不叠加第二套延迟
# =====================================================================================

class NoDoubleReactionTest(TestCase):
    DIRECT_RANDOM_DELAY_OWNERS = (
        ('tasks/RealmRaid/script_task.py', 'fire'),
        ('tasks/RealmRaid/script_task.py', '_fire_again'),
        ('tasks/RyouToppa/script_task.py', 'attack_area'),
        ('tasks/EvoZone/script_task.py', '_fire_evozone_alone'),
        ('tasks/Orochi/script_task.py', '_fire_orochi_alone'),
        ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle'),
        ('tasks/Component/GeneralInvite/general_invite.py', 'click_fire'),
        # L2-3B Batch A 的专用 FIRE owner（自己采样一次 reaction，点击本身用 interval=0、不带 policy）
        ('tasks/EternitySea/script_task.py', '_fire_eternity_sea_alone'),
        ('tasks/FallenSun/script_task.py', '_fire_fallen_sun_alone'),
        ('tasks/Sougenbi/script_task.py', '_fire_sougenbi'),
    )

    @staticmethod
    def _source(rel, func_name):
        """函数源码去掉首个 docstring —— 只扫代码体，避免文档里提到的 random_delay( 字样误计数。"""
        import ast
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        text = (repo / rel).read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                full = ast.get_source_segment(text, node)
                parts = full.split('"""')
                return parts[2] if len(parts) >= 3 else full
        raise AssertionError(f'{rel}::{func_name} not found')

    def test_direct_owners_have_exactly_one_random_delay_call(self):
        for rel, func in self.DIRECT_RANDOM_DELAY_OWNERS:
            with self.subTest(owner=f'{rel}::{func}'):
                src = self._source(rel, func)
                self.assertIn('fire_reaction_range(', src)
                # RyouToppa 的 area pacing random_delay(1.0, 3.0) 与 FIRE reaction 是两个不同 owner，
                # 允许 2 处 random_delay；其余每个函数恰一次。
                expected = 2 if (rel, func) == ('tasks/RyouToppa/script_task.py', 'attack_area') else 1
                self.assertEqual(src.count('random_delay('), expected)
                self.assertNotIn('confirm_delay=REACTION', src)

    def test_general_invite_run_invite_forwards_fire_reaction_without_sampling_itself(self):
        import inspect
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        src = inspect.getsource(GeneralInvite.run_invite)
        self.assertNotIn('random_delay(', src)
        self.assertIn('fire_result = self.click_fire(fire_reaction=fire_reaction)', src)


# =====================================================================================
# 六、保存 / 重新加载 / 回显：ConfigModel.script_task 与 script_set_arg（复用嵌套字段展开机制）
# =====================================================================================

class SaveReloadRoundtripTest(TestCase):
    def setUp(self):
        from module.config.config_model import ConfigModel
        self._no_write = patch.object(ConfigModel, 'write_json',
                                      side_effect=lambda name, data: self.writes.append((name, data)))
        self.writes = []
        self._no_write.start()
        self.addCleanup(self._no_write.stop)

    def test_get_shows_fire_reaction_group_with_correct_names_and_defaults(self):
        from module.config.config_model import ConfigModel
        m = ConfigModel()
        for task in ('RealmRaid', 'RyouToppa', 'EvoZone', 'Orochi', 'ActivityShikigami',
                    'EternitySea', 'FallenSun', 'Sougenbi'):
            with self.subTest(task=task):
                items = {i['name']: i for i in m.script_task(task)['fire_reaction']}
                self.assertEqual(items['fire_reaction_min_ms']['default'], 400)
                self.assertEqual(items['fire_reaction_min_ms']['value'], 400)
                self.assertEqual(items['fire_reaction_max_ms']['default'], 800)
                self.assertEqual(items['fire_reaction_max_ms']['value'], 800)
                self.assertEqual(items['fire_reaction_min_ms']['type'], 'integer')

    def test_put_then_get_reflects_new_value_and_persists_via_save(self):
        from module.config.config_model import ConfigModel
        m = ConfigModel(config_name='case')
        ok = m.script_set_arg('RealmRaid', 'fire_reaction', 'fire_reaction_min_ms', 250)
        self.assertTrue(ok)
        self.assertEqual(m.realm_raid.fire_reaction.fire_reaction_min_ms, 250)
        self.assertEqual(len(self.writes), 1)
        items = {i['name']: i for i in m.script_task('RealmRaid')['fire_reaction']}
        self.assertEqual(items['fire_reaction_min_ms']['value'], 250)
        self.assertEqual(items['fire_reaction_max_ms']['value'], 800)   # 不相关字段不受影响

    def test_invalid_put_is_rejected_and_nothing_saved(self):
        from module.config.config_model import ConfigModel
        m = ConfigModel(config_name='case')
        before = m.model_dump()
        ok = m.script_set_arg('EvoZone', 'fire_reaction', 'fire_reaction_max_ms', 9999)
        self.assertFalse(ok)
        self.assertEqual(m.model_dump(), before)
        self.assertEqual(self.writes, [])

    def test_get_does_not_write_any_file(self):
        from module.config.config_model import ConfigModel
        m = ConfigModel()
        for task in TASK_CONFIG_CLASSES:
            m.script_task(''.join(p.capitalize() for p in task.split('_')))
        self.assertEqual(self.writes, [])


# =====================================================================================
# 七、OASX 中文标签（后端翻译资源）
# =====================================================================================

class OASXTranslationTest(TestCase):
    def test_fire_reaction_labels_resolve_to_chinese(self):
        from module.server.i18n import I18n
        zh = I18n.load_additions()['zh-CN']
        self.assertEqual(zh['fire_reaction'], 'FIRE 点击延迟')
        self.assertEqual(zh['fire_reaction_min_ms'], 'FIRE 点击前最小延迟')
        self.assertEqual(zh['fire_reaction_max_ms'], 'FIRE 点击前最大延迟')
        self.assertIn('400', zh['fire_reaction_min_ms_help'])
        self.assertIn('800', zh['fire_reaction_max_ms_help'])

    def test_labels_are_shared_across_all_eight_tasks_not_duplicated_per_task(self):
        # 8 个任务共用同一组翻译键（字段名本身相同），不需要也不应该按任务命名空间重复
        import json
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        raw = (repo / 'assets' / 'i18n' / 'zh-CN.json').read_text(encoding='utf-8')
        for key in ('fire_reaction', 'fire_reaction_min_ms', 'fire_reaction_max_ms'):
            self.assertEqual(raw.count(json.dumps(key, ensure_ascii=False) + ':'), 1)
