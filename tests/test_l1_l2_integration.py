# This Python file uses the following encoding: utf-8
"""L1（全局单击管线）+ L2（交互反应层）在 master 上的联动与全仓登记册护栏。

- 联动：真实 `BaseTask.appear_then_click` + 真实 `Control.click`（假后端）+ 真实采样器包装计数——
  证明「一个点击动作只采样一次坐标、reaction 之后才用新帧采样、目标消失零采样零点击」。
- 全仓登记册（`docs/L2_CALLSITE_REGISTER.md`，由 `dev_tools/click_callsite_register.py` 生成）：
  汇总数字与当前源码逐项对账；policy / confirm_delay 只允许出现在已人工审计的文件；受保护路径
  （KekkaiUtilize / Settlement / FIRE owner）不得带普通 reaction；每个点击调用点都有归属。
- 调度：真实 `Script.run` / `Script.loop` + 真实 `Config.task_delay`，reaction 的耗时不进入 next_run。
"""

import ast
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from dev_tools import click_callsite_register as reg
from module import behavior_trace
from module.behavior_trace import configure_behavior_trace, reset_behavior_traces
from module.click_sampler import ClickSampler
from module.device.control import Control
from module.exception import TaskEnd
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask
from tests.test_l2_policy_migration import INVENTORY

_REPO = Path(__file__).resolve().parents[1]
REGISTER_DOC = _REPO / 'docs' / 'L2_CALLSITE_REGISTER.md'


# ======================================================================================
# 一、L1 × L2 联动：一个动作一次坐标采样
# ======================================================================================

class _Target:
    """规则目标替身：`coord()` 与真实 `RuleClick.coord()` 同口径——每次调用走一次 `ClickSampler.sample_target`。"""

    def __init__(self, name='link_btn', roi=(400, 300, 200, 90)):
        self.name, self.roi = name, roi

    def coord(self):
        return ClickSampler.sample_target(self.roi, self.name)


def _control(backend):
    c = Control.__new__(Control)
    c.config = SimpleNamespace(
        config_name='l1l2', script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
    c.click_methods = {'minitouch': backend}
    return c


def _inside(point, roi):
    x, y, w, h = roi
    return x <= point[0] < x + w and y <= point[1] < y + h


class LinkedClickHarness(TestCase):
    """帧序列驱动：第 n 次 `screenshot()` 之后看到 frames[n - 1]（frames 元素 = 该帧可见目标的 roi 映射）。"""

    def setUp(self):
        reset_behavior_traces()
        self._log_dir = behavior_trace._LOG_DIR
        self._tmp = tempfile.TemporaryDirectory()
        behavior_trace._LOG_DIR = Path(self._tmp.name)
        self.events = []
        self.backend = Mock(name='backend', side_effect=lambda x, y: self.events.append(('click', x, y)))
        self.addCleanup(self._restore)                             # cleanup 后进先出：先 reset（关文件句柄）再删临时目录
        self.addCleanup(reset_behavior_traces)

    def _restore(self):
        behavior_trace._LOG_DIR = self._log_dir
        self._tmp.cleanup()

    def _task(self, frames, target):
        state = {'frame': 0}
        events = self.events

        def screenshot():
            state['frame'] += 1
            events.append(('screenshot', state['frame']))

        def frame():
            return frames[min(state['frame'], len(frames) - 1)]

        def appear(t, interval=None, threshold=None):
            visible = frame().get(t.name)
            if visible is not None:
                t.roi = visible                                     # 与真实 `RuleImage.match` 一样把最新帧的框写回目标
            return visible is not None

        task = SimpleNamespace(screenshot=screenshot, appear=appear, interval_timer={},
                               device=_control(self.backend))
        return task

    def _run(self, frames, target, **kwargs):
        task = self._task(frames, target)
        original = ClickSampler.sample_target

        def counted(roi, name=None, *a, **k):
            self.events.append(('sample', tuple(roi)))
            return original(roi, name, *a, **k)

        with patch.object(ClickSampler, 'sample_target', side_effect=counted), \
                patch('tasks.base_task.random_delay', side_effect=lambda lo, hi: self.events.append(('reaction', lo, hi)) or lo), \
                patch('tasks.base_task.sleep', side_effect=lambda s: self.events.append(('sleep', s))):
            configure_behavior_trace('l1l2', enabled=True)
            return BaseTask.appear_then_click(task, target, **kwargs)

    def _kinds(self):
        return [e[0] for e in self.events]

    def _rows(self):
        files = list(behavior_trace._LOG_DIR.glob('l1l2_*.jsonl'))
        return [json.loads(ln) for ln in files[0].read_text(encoding='utf-8').splitlines() if ln] if files else []


class LinkedClickTest(LinkedClickHarness):
    ROI = (400, 300, 200, 90)

    def test_policy_click_samples_exactly_once_after_the_reaction_on_the_fresh_frame(self):
        target = _Target(roi=self.ROI)
        result = self._run([{'link_btn': self.ROI}], target, policy=InteractionPolicy.NORMAL)
        self.assertTrue(result)
        self.assertEqual(self._kinds(), ['reaction', 'sleep', 'screenshot', 'sample', 'click'])
        self.assertEqual(self._kinds().count('sample'), 1)           # 一个动作一次采样，没有「反应前采一次、反应后再偏一次」
        _, x, y = self.events[-1]
        self.assertTrue(_inside((x, y), self.ROI))
        rows = self._rows()
        self.assertEqual([(r['extra']['x'], r['extra']['y']) for r in rows], [(x, y)])   # 行为日志记录的就是实际执行坐标

    def test_reaction_range_comes_from_the_declared_policy_and_is_sampled_once(self):
        from module.reaction_profile import REACTION_NORMAL
        self._run([{'link_btn': self.ROI}], _Target(roi=self.ROI), policy=InteractionPolicy.NORMAL)
        reactions = [e for e in self.events if e[0] == 'reaction']
        self.assertEqual(reactions, [('reaction',) + tuple(REACTION_NORMAL)])

    def test_target_gone_after_reaction_means_zero_samples_and_zero_clicks(self):
        result = self._run([{'link_btn': self.ROI}, {}], _Target(roi=self.ROI), policy=InteractionPolicy.FAST)
        self.assertFalse(result)
        self.assertNotIn('sample', self._kinds())
        self.assertNotIn('click', self._kinds())
        self.backend.assert_not_called()

    def test_target_moved_during_reaction_is_clicked_at_the_new_position(self):
        moved = (700, 500, 120, 60)
        result = self._run([{'link_btn': self.ROI}, {'link_btn': moved}], _Target(roi=self.ROI),
                           policy=InteractionPolicy.CONFIRM)
        self.assertTrue(result)
        samples = [e for e in self.events if e[0] == 'sample']
        self.assertEqual(samples, [('sample', moved)])               # 只按新帧的框采样，旧框从未被采样
        _, x, y = self.events[-1]
        self.assertTrue(_inside((x, y), moved))

    def test_immediate_and_legacy_calls_keep_the_original_immediate_click(self):
        for kwargs in ({}, {'policy': InteractionPolicy.IMMEDIATE}):
            with self.subTest(kwargs=kwargs):
                self.events.clear()
                result = self._run([{'link_btn': self.ROI}], _Target(roi=self.ROI), **kwargs)
                self.assertTrue(result)
                self.assertEqual(self._kinds(), ['sample', 'click'])   # 无 reaction、无 sleep、无二次截图

    def test_legacy_confirm_delay_still_works_without_a_second_wait(self):
        result = self._run([{'link_btn': self.ROI}], _Target(roi=self.ROI), confirm_delay=(0.2, 0.3))
        self.assertTrue(result)
        self.assertEqual(self._kinds().count('reaction'), 1)
        self.assertEqual(self._kinds().count('sample'), 1)

    def test_policy_together_with_confirm_delay_is_rejected_before_any_sampling(self):
        with self.assertRaises(ValueError):
            self._run([{'link_btn': self.ROI}], _Target(roi=self.ROI),
                      policy=InteractionPolicy.NORMAL, confirm_delay=(0.2, 0.3))
        self.assertEqual(self.events, [])

    def test_fsm_owned_policies_are_rejected_by_the_generic_click(self):
        for policy in (InteractionPolicy.FIRE_SPECIAL, InteractionPolicy.SPECIAL):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self._run([{'link_btn': self.ROI}], _Target(roi=self.ROI), policy=policy)
        self.assertEqual(self.events, [])

    def test_control_adds_no_spatial_jitter_of_its_own(self):
        # 后端收到的坐标 == 管线采样出的坐标：L1 决定落点，Control 只执行
        target = _Target(roi=self.ROI)
        with patch.object(ClickSampler, 'sample_target', return_value=(431, 322)):
            self._run([{'link_btn': self.ROI}], target)
        self.backend.assert_called_once_with(431, 322)


# ======================================================================================
# 二、特殊状态机的延迟所有权（静态）
# ======================================================================================

def _functions(rel):
    text = (_REPO / rel).read_text(encoding='utf-8')
    return text, [n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _click_calls(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
            if name in reg.HELPERS:
                yield name, {kw.arg: kw.value for kw in n.keywords}, n


class SpecialFsmOwnershipTest(TestCase):
    def test_settlement_functions_have_no_ordinary_reaction(self):
        text, funcs = _functions('tasks/Component/GeneralBattle/general_battle.py')
        checked = 0
        for fn in funcs:
            if 'settlement' in fn.name or fn.name in ('_handle_result', '_handle_reward'):
                checked += 1
                with self.subTest(func=fn.name):
                    for name, kws, call in _click_calls(fn):
                        self.assertNotIn('policy', kws)
                        self.assertNotIn('confirm_delay', kws)
                    self.assertNotIn('random_delay(*REACTION', ast.get_source_segment(text, fn) or '')
        self.assertGreaterEqual(checked, 5)

    def test_fire_owner_click_uses_task_config_only_and_never_a_generic_policy(self):
        owners = (
            ('tasks/RealmRaid/script_task.py', 'fire'), ('tasks/RealmRaid/script_task.py', '_fire_again'),
            ('tasks/Orochi/script_task.py', '_fire_orochi_alone'), ('tasks/EvoZone/script_task.py', '_fire_evozone_alone'),
            ('tasks/EternitySea/script_task.py', '_fire_eternity_sea_alone'),
            ('tasks/FallenSun/script_task.py', '_fire_fallen_sun_alone'), ('tasks/Sougenbi/script_task.py', '_fire_sougenbi'),
            ('tasks/Component/GeneralInvite/general_invite.py', 'click_fire'),
            ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle'),
        )
        for rel, name in owners:
            _, funcs = _functions(rel)
            fn = next(f for f in funcs if f.name == name)
            with self.subTest(owner=f'{rel}::{name}'):
                names = [n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
                         for n in ast.walk(fn) if isinstance(n, ast.Call)]
                self.assertIn('fire_reaction_range', names)              # 反应等待归任务 FIRE 配置这唯一 owner
                self.assertEqual(names.count('random_delay'), 1)         # 只采样一次，不叠第二个 reaction
                for _, kws, _call in _click_calls(fn):
                    self.assertNotIn('policy', kws)                      # 不叠加普通 policy
                    if 'confirm_delay' in kws:
                        # 唯一例外：RealmRaid「再次挑战」后的确认弹窗是另一次点击，独立 legacy 区间（L2 map 已登记），
                        # 不是 FIRE 这一击的第二个 reaction
                        self.assertEqual((name, ast.unparse(kws['confirm_delay'])), ('_fire_again', 'RR_AGAIN_CONFIRM_DELAY'))

    def test_orochi_wild_stays_excluded_and_unchanged(self):
        text, funcs = _functions('tasks/Orochi/script_task.py')
        names = {f.name for f in funcs}
        self.assertNotIn('_fire_orochi_wild', names)                     # 项目决定：不启用 / 不扩展野队 FIRE 状态机
        wild = next(f for f in funcs if f.name == 'run_wild')
        wild_src = ast.get_source_segment(text, wild)
        self.assertIn('self.appear_then_click(self.I_OROCHI_WILD_FIRE, interval=1, threshold=0.8)', wild_src)

    def test_kekkai_utilize_has_no_reaction_declared_anywhere(self):
        for rel in ('tasks/KekkaiUtilize/script_task.py', 'tasks/KekkaiUtilize/page.py', 'tasks/KekkaiUtilize/utils.py'):
            path = _REPO / rel
            if not path.exists():
                continue
            with self.subTest(file=rel):
                text = path.read_text(encoding='utf-8')
                self.assertNotIn('policy=InteractionPolicy', text)
                self.assertNotIn('confirm_delay=', text)

    def test_generic_navigator_executor_stays_immediate(self):
        text, funcs = _functions('tasks/GameUi/navigator.py')
        action = next(f for f in funcs if f.name == '_execute_action')
        for name, kws, call in _click_calls(action):
            self.assertNotIn('policy', kws)
            self.assertNotIn('confirm_delay', kws)


# ======================================================================================
# 三、全仓登记册护栏
# ======================================================================================

class CallsiteRegisterGuardTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = reg.classify_all(reg.scan_sites(), [tuple(r) for r in INVENTORY])
        cls.summary = reg.summarize(cls.sites)

    def test_every_site_has_exactly_one_known_decision_and_reason(self):
        for site in self.sites:
            self.assertIn(site['decision'], reg.DECISIONS)
            self.assertIn(site['reason'], reg.REASONS)
        self.assertEqual(sum(self.summary['by_decision'].values()), self.summary['total'])

    def test_register_doc_summary_matches_the_current_source_scan(self):
        # 只对账汇总（总数 / decision / 模块）：不写行号，无关改动不会让它失效；新增 / 删除点击调用点会
        text = REGISTER_DOC.read_text(encoding='utf-8')
        expected = reg.render_markdown(self.sites)
        start, end = '## 2. 汇总', '## 4. 理由代码'
        self.assertEqual(text[text.index(start):text.index(end)], expected[expected.index(start):expected.index(end)],
                         '登记册汇总与源码扫描不一致：运行 `toolkit\\python.exe -m dev_tools.click_callsite_register --write` 重新生成')

    def test_reaction_declarations_only_in_human_audited_files(self):
        for site in self.sites:
            if site['policy'] or site['confirm_delay']:
                with self.subTest(site=f'{site["file"]}::{site["qual"]}#{site["ordinal"]}'):
                    if site['basis'] == 'c0':
                        # C0 复核后迁移的点位：必须在 `C1_MIGRATED` 里逐点登记（文件 / 函数 / 目标 / policy 全部对得上）
                        self.assertIn((site['file'], site['func'], site['target'], site['policy']), reg.C1_MIGRATED)
                    else:
                        self.assertIn(site['file'], reg.AUDITED_FILES)
                        self.assertEqual(site['basis'], 'human')

    def test_no_site_declares_both_policy_and_confirm_delay(self):
        # `check_lock` 把两个形参原样透传给 appear_then_click（运行时同时非 None 会被 resolve_reaction_range 拒绝），
        # 不算「同时声明」；只有字面写了 `policy=InteractionPolicy.*` 又写了 confirm_delay 才算
        both = [s for s in self.sites if (s['policy'] or '').startswith('InteractionPolicy.') and s['confirm_delay']]
        self.assertEqual(both, [])

    def test_excluded_and_primitive_scopes_are_what_the_decisions_say(self):
        excluded_modules = {s['module'] for s in self.sites if s['decision'] == 'EXCLUDED'}
        self.assertEqual(excluded_modules, {m for m in reg.EXCLUDED_MODULES if any(s['module'] == m for s in self.sites)})
        self.assertTrue(all(s['file'] == 'tasks/base_task.py' or s['file'].startswith('module/')
                            for s in self.sites if s['decision'] == 'PRIMITIVE'))

    def test_l1_migration_state_is_locked(self):
        summary = self.summary
        # 45 + 2026-09-23 爬塔线专用结算单击改造新增 1 处 execute_single_click（`_activity_settlement_single_click`）
        self.assertEqual(summary['l1_pipeline_sites'], 46)
        # Stage 3B 之后生产直接单击对所有模块（含原项目排除模块）都归零：裸点只剩底层 / 非点击（module/）
        production_raw = [s for s in self.sites if s['kind'] in ('raw_device_click', 'raw_backend')
                          and not s['file'].startswith('module/')]
        self.assertEqual([(s['file'], s['qual']) for s in production_raw], [])
        self.assertEqual(summary['raw_click_sites'], summary['raw_module'] + summary['raw_excluded'])
        self.assertEqual((summary['raw_module'], summary['raw_primitive'], summary['raw_excluded']), (4, 0, 0))
        # 仍直接 device.click / 后端直调的调用点 = primitive + 已知例外（`test_l1_click_pipeline` 的白名单逐条给出理由）
        raw_files = {s['file'] for s in self.sites if s['kind'] in ('raw_device_click', 'raw_backend')}
        self.assertNotIn('tasks/Hyakkiyakou/slave/hya_device.py', raw_files)    # 百鬼夜行已经走 click_with_backend
        self.assertEqual(summary['policy_sites'], 36)                                   # 32 + C1-A1 的 4 处
        self.assertEqual(summary['confirm_delay_sites'], 3)                       # GeneralBattle.check_lock 透传 ×2 + RealmRaid 再次挑战确认 ×1

    def test_needs_c_sites_are_pinned_so_new_candidates_need_a_conscious_decision(self):
        by_module = {}
        for s in self.sites:
            if s['decision'] == 'NEEDS_C':
                by_module[s['module']] = by_module.get(s['module'], 0) + 1
        # C0 收口后：C1-A1 已迁走 4 点；Duel 2 + SixRealms 商店 4 归档为 DEFERRED（用户暂缓）；Buy 2 / DemonRetreat / Quiz /
        # SixRealms 3 点归档为 KEEP_*；只剩 GeneralInvite / GeneralBattle 需要真机依据的 7 点仍是 NEEDS_C（且 dev_status=DEFERRED）
        self.assertEqual(by_module, {'tasks/Component/GeneralBattle': 2, 'tasks/Component/GeneralInvite': 5})
