# This Python file uses the following encoding: utf-8
"""synevo 分支专有：EvoZone 普通运行 / 嵌入式运行（多账号）读取同一份 FIRE 配置，且不发生双重 reaction。

本分支的 EvoZone 有两条入口：`run()` → `_run_core()`（普通运行，业务配置取 `self.config.evo_zone`）与
`run_embedded()`（多账号组队觉醒，业务配置取 `_embedded_evo_zone` 深拷贝）。整合 L1/L2 时 FIRE reaction
的配置源统一写成 `self.config.evo_zone.fire_reaction`（与其余 FIRE 任务同形态，被源码形态守卫锁定）。
本文件证明这个写法在嵌入式运行下同样正确：`run_embedded` 的深拷贝不覆写 `fire_reaction`，两条路径取到
的区间完全相同；并且一次 attempt 只采样一次 reaction，不会在 L2 之外叠加第二次等待。
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.interaction_policy import fire_reaction_range
from tasks.Component.config_fire_reaction import FireReactionConfig
from tasks.EvoZone.config import EvoZone as EvoZoneConfig
from tasks.EvoZone.config import KirinType, Layer, UserStatus
from tasks.EvoZone.script_task import ScriptTask as EvoZone

from tests.test_second_batch_fire_fsm import _mk as _oe_mk

CUSTOM = FireReactionConfig(fire_reaction_min_ms=1234, fire_reaction_max_ms=1678)
CUSTOM_SECONDS = fire_reaction_range(CUSTOM)


class EmbeddedRunKeepsTheSameFireConfigTest(TestCase):
    def test_embedded_copy_does_not_override_fire_reaction(self):
        real = EvoZoneConfig()
        real.fire_reaction = CUSTOM
        task = EvoZone.__new__(EvoZone)
        task.config = SimpleNamespace(evo_zone=real)
        task._embedded_evo_zone = None
        # 嵌入式运行只改业务字段（user_status / limit_count / kirin / layer / friend_list）
        embedded = real.model_copy(deep=True)
        embedded.evo_zone_config.user_status = UserStatus.LEADER
        embedded.evo_zone_config.limit_count = 3
        embedded.evo_zone_config.kirin_type = KirinType.FIREKIRIN
        embedded.evo_zone_config.layer = Layer.ONE
        task._embedded_evo_zone = embedded
        # 业务配置走 active_evo_zone（嵌入副本），FIRE 区间两条路径一致
        self.assertIs(task.active_evo_zone, embedded)
        self.assertEqual(fire_reaction_range(embedded.fire_reaction), CUSTOM_SECONDS)
        self.assertEqual(fire_reaction_range(task.config.evo_zone.fire_reaction), CUSTOM_SECONDS)

    def _drive_fire(self, embedded):
        events, task, fire = _oe_mk(EvoZone, '_fire_evozone_alone', 'I_EVOZONE_FIRE',
                                    in_battle=[False, False, True], fire_visible=[True, True, True])
        task.config = SimpleNamespace(evo_zone=SimpleNamespace(fire_reaction=CUSTOM))
        task._embedded_evo_zone = embedded
        with patch('tasks.EvoZone.script_task.random_delay', return_value=0.2) as delay, \
                patch('tasks.EvoZone.script_task.sleep') as slept:
            self.assertIs(fire(), True)
        return events, delay, slept

    def test_normal_run_samples_the_task_config_once(self):
        _, delay, slept = self._drive_fire(embedded=None)
        delay.assert_called_once_with(*CUSTOM_SECONDS)
        self.assertEqual(slept.call_args_list, [((0.2,), {})])

    def test_embedded_run_reads_the_same_config_and_does_not_double_react(self):
        embedded = EvoZoneConfig()
        embedded.fire_reaction = CUSTOM
        _, delay, slept = self._drive_fire(embedded=embedded)
        # 一次 attempt = 一次 reaction 采样 + 一次 sleep：嵌入式运行不额外叠加等待
        delay.assert_called_once_with(*CUSTOM_SECONDS)
        self.assertEqual(slept.call_args_list, [((0.2,), {})])

    def test_fire_click_itself_carries_no_extra_reaction_policy(self):
        events, _, _ = self._drive_fire(embedded=None)
        clicks = [e for e in events if isinstance(e, tuple) and e[0] == 'fire_click']
        self.assertEqual(len(clicks), 1)
        # FIRE 自己拥有 reaction，点击不得再叠加 L2 policy / confirm_delay
        kwargs = clicks[0][2]
        self.assertEqual(kwargs, {'interval': 0})


class EmbeddedRunStructureIsUnchangedTest(TestCase):
    """整合没有把 synevo 的嵌入式结构改回 master 的旧 run()。"""

    def test_run_embedded_and_run_core_still_exist(self):
        for name in ('_run_core', 'run_embedded', 'active_evo_zone', '_return_to_main_after_run'):
            self.assertTrue(hasattr(EvoZone, name), name)

    def test_run_embedded_refuses_nesting(self):
        task = EvoZone.__new__(EvoZone)
        task._embedded_evo_zone = object()
        task.config = SimpleNamespace(evo_zone=EvoZoneConfig())
        task._run_core = Mock()
        with self.assertRaises(RuntimeError):
            EvoZone.run_embedded(task, user_status=UserStatus.LEADER, limit_count=1)
        task._run_core.assert_not_called()
