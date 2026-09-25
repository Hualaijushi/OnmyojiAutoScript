# This Python file uses the following encoding: utf-8
"""GeneralBattle 通用结算推进（SETTLEMENT CONTRACT V3 + Micro-Burst v1.2）离线测试。

契约 v3（v1 的 one-primary / 2 秒观察 / same-page 超时 / sticky RD2 / Reward marker 决定
区域，v2 的 `C_RANDOM_RD` + HABIT profile —— 全部 Superseded）：

- 三个大安全点击区：`C_RANDOM_DEFAULT` / `C_RANDOM_SAVE_RIGHT` / `C_RANDOM_SAVE_BOTTOM`，
  采样一律整 ROI 均匀（`LEGACY_UNIFORM`），不做 HABIT 偏置、不走 `appear_then_click`。
- 非通用结果标志（含更宽的 `I_BATTLE_STATE_INFO`）→ 退回旧的单次节流点击（未改）。
- `page_reward`：命中 `I_OVER_GHOST` / `I_GB_SKIN_CONFIRM` 就本帧 CONTINUE（不再同帧 region
  click）；否则 `_select_reward_region()`：`I_GET_BATTLE_REWARD` / `_2` 命中 → DEFAULT，
  都没命中 → 80% RIGHT / 20% BOTTOM（未改）。
- 默认间隔 `SETTLEMENT_CLICK_INTERVAL_RANGE = (0.7, 1.0)`，每次成功 burst 后独立重采（未改）。
- `is_win` / `_exit_matcher` / 2.5s missing fallback 不变。

Micro-Burst v1.2（`docs/DECISIONS.md` D025，见 `SettlementMicroBurstTest`）：`page_battle_result`
通用胜负上下文（`I_WIN`/`I_DE_WIN`/`I_FALSE` 命中）与 `page_reward` 普通奖励布局统一收进同一个
Settlement Lifecycle——每个 semantic state 拥有独立的 2~4 click segment；segment 耗尽且 fresh
state 仍是 result/reward 时允许续段，只有 semantic terminal 才 teardown。单次 observed burst 最多
2 次（同一 anchor，第一下后 fresh classify 决定能否补第二下）；状态前向变化时按安全区域交集决定
anchor 保留/换点（全 session 最多 1 次主动换点）。固定总安全帽保证续段有界。旧
`_advance_generic_result`（首帧强制两次、各自独立采样）已被这个 session 模型吸收替代、不再存在。
"""

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tasks.Component.GeneralBattle import general_battle as gb
from tasks.Component.GeneralBattle.general_battle import BattleAction, GeneralBattle


class _Timer:
    """最小结算节流计时器替身：默认「未启动」→ 首次点击立即放行。"""

    def __init__(self):
        self.limit = 0
        self._started = False
        self._reached = False

    def started(self):
        return self._started

    def reached(self):
        return self._reached

    def reset(self):
        self._started = True
        self._reached = False
        return self

    def expire(self):
        self._reached = True


def _make_task():
    task = GeneralBattle.__new__(GeneralBattle)
    task.device = SimpleNamespace(click_record_clear=Mock(), click=Mock())
    task.screenshot = Mock()   # v1.1 Observed Micro-Burst 需要 mid-burst fresh screenshot
    return task


def _settlement_context(**overrides):
    """构造一份带全部 Settlement Micro-Burst 字段的 context（`SimpleNamespace`）。

    字段集合与 `general_battle.py::BattleContext` 的 `settlement_*` 字段保持一致，
    默认值对应「本轮结算 session 尚未初始化」。
    """
    base = dict(
        settlement_click_timer=_Timer(),
        reward_no_battle_ts=None,
        is_win=False,
        last_page=None,
        settlement_session_active=False,
        settlement_click_budget=0,
        settlement_clicks_used=0,
        settlement_total_clicks=0,
        settlement_anchor=None,
        settlement_region_name=None,
        settlement_stage_name=None,
        settlement_anchor_switches=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _SettlementHarness:
    """构造一个只带结算相关字段的 GeneralBattle 实例 + context。"""

    def __init__(self, interval=0.8):
        self.task = _make_task()
        self.task._next_settlement_click_interval = Mock(return_value=interval)
        self.regions = []  # 采样点击到的 RuleClick 顺序
        self.task._sample_settlement_click = Mock(side_effect=lambda rule: self.regions.append(rule))
        # v1.1 Observed Micro-Burst 默认假设「观察后仍是同一页」（page_battle_result——
        # 本 harness 历史上主要给 result 相关测试用；reward 相关测试用 `_reward_harness()`
        # 覆盖成 page_reward）。
        self.task._classify_general_battle_page = Mock(return_value=gb.page_battle_result)
        self.context = _settlement_context()
        self.timer = self.context.settlement_click_timer

    @property
    def names(self):
        return [r.name for r in self.regions]


# --------------------------------------------------------------------------------------
# A. Resource Contract —— 旧 RD/RD2 移除，新三区域到位
# --------------------------------------------------------------------------------------

class ResourceContractTest(unittest.TestCase):
    def test_general_battle_source_no_longer_references_rd_regions(self):
        src = inspect.getsource(GeneralBattle)
        # 允许注释里出现「已移除」说明，但不允许出现真实属性访问
        self.assertNotIn("self.C_RANDOM_RD", src)
        self.assertNotIn("self.C_RANDOM_RD2", src)
        self.assertNotIn("_SETTLEMENT_PRIMARY_PROFILE", src)
        self.assertNotIn("_SETTLEMENT_FALLBACK_PROFILE", src)

    def test_module_has_no_settlement_profile_symbols(self):
        for name in ("_SETTLEMENT_PRIMARY_PROFILE", "_SETTLEMENT_FALLBACK_PROFILE",
                     "ClickProfile", "STRATEGY_HABIT"):
            self.assertFalse(hasattr(gb, name), f"{name} 仍在 general_battle 模块里")

    def test_rd_assets_removed_from_general_battle_assets(self):
        self.assertFalse(hasattr(GeneralBattle, "C_RANDOM_RD"))
        self.assertFalse(hasattr(GeneralBattle, "C_RANDOM_RD2"))

    def test_three_safe_regions_exist_with_expected_roi(self):
        self.assertEqual(GeneralBattle.C_RANDOM_DEFAULT.roi_front, (742, 430, 362, 230))
        self.assertEqual(GeneralBattle.C_RANDOM_DEFAULT.name, "random_default")
        self.assertEqual(GeneralBattle.C_RANDOM_SAVE_RIGHT.roi_front, (1185, 209, 87, 441))
        self.assertEqual(GeneralBattle.C_RANDOM_SAVE_RIGHT.name, "random_save_right")
        self.assertEqual(GeneralBattle.C_RANDOM_SAVE_BOTTOM.roi_front, (819, 639, 425, 69))
        self.assertEqual(GeneralBattle.C_RANDOM_SAVE_BOTTOM.name, "random_save_bottom")

    def test_reward_layout_markers_exist_and_are_images(self):
        from module.atom.image import RuleImage
        self.assertIsInstance(GeneralBattle.I_GET_BATTLE_REWARD, RuleImage)
        self.assertIsInstance(GeneralBattle.I_GET_BATTLE_REWARD_2, RuleImage)

    def test_reward_layout_markers_not_in_page_reward_recognizer(self):
        # 布局判别标志不得进 page_reward 识别器（决策 3）
        from tasks.GameUi.default_pages import page_reward
        rec_src = repr(page_reward.recognizer)
        self.assertNotIn("get_battle_reward", rec_src.lower())

    def test_no_v1_v2_concepts_left(self):
        for name in ("REWARD_MARKERS", "_reward_marker_present", "_advance_settlement",
                     "_reset_settlement_stage", "_sync_settlement_stage",
                     "_SETTLEMENT_PRIMARY_OBSERVE_SECONDS"):
            self.assertFalse(hasattr(gb, name) or hasattr(GeneralBattle, name), name)
        fields = {f.name for f in gb.BattleContext.__dataclass_fields__.values()}
        for f in ("settlement_stage", "settlement_primary_ts", "settlement_fallback"):
            self.assertNotIn(f, fields)


# --------------------------------------------------------------------------------------
# B. Generic Result —— 通用胜负页 positive guard
# --------------------------------------------------------------------------------------

class GenericResultGuardTest(unittest.TestCase):
    def test_guard_only_checks_win_dewin_false(self):
        src = inspect.getsource(GeneralBattle._is_generic_result_context)
        self.assertIn("self.appear(self.I_WIN)", src)
        self.assertIn("self.appear(self.I_DE_WIN)", src)
        self.assertIn("self.appear(self.I_FALSE)", src)
        self.assertNotIn("self.appear(self.I_BATTLE_STATE_INFO)", src)

    def test_guard_true_when_any_verdict_banner_present(self):
        task = _make_task()
        for present in (task.I_WIN, task.I_DE_WIN, task.I_FALSE):
            task.appear = Mock(side_effect=lambda r, **kw: r is present)
            self.assertTrue(task._is_generic_result_context(), present.name)

    def test_guard_false_when_only_battle_state_info(self):
        task = _make_task()
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_BATTLE_STATE_INFO)
        self.assertFalse(task._is_generic_result_context())


class NonGenericResultTest(unittest.TestCase):
    """非通用结果标志（更宽的 I_BATTLE_STATE_INFO）：不纳入 burst session，现状未改。"""

    def test_non_generic_result_frame_uses_single_throttled_click(self):
        h = _SettlementHarness()
        h.task.appear = Mock(return_value=False)                 # 没有任何 verdict banner
        h.task._handle_result(h.context, SimpleNamespace())
        self.assertEqual(h.names, ["random_default"])            # 单次，不是 burst

    def test_result_keeps_is_win_and_click_record_semantics(self):
        src = inspect.getsource(GeneralBattle._handle_result)
        self.assertIn("context.reward_no_battle_ts = None", src)
        self.assertIn("context.is_win = not self.appear(self.I_FALSE, threshold=0.8)", src)
        self.assertIn("self.device.click_record_clear()", src)
        self.assertIn("return BattleAction.CONTINUE", src)


# --------------------------------------------------------------------------------------
# B'. Settlement Micro-Burst Session v1（2026-09-12，`docs/DECISIONS.md` D025）
# --------------------------------------------------------------------------------------

_REGION_A = SimpleNamespace(name="region_a", roi_front=(0, 0, 100, 100))
_REGION_B_COMPAT = SimpleNamespace(name="region_b", roi_front=(0, 0, 200, 200))       # 含旧 anchor
_REGION_B_INCOMPAT = SimpleNamespace(name="region_b", roi_front=(500, 500, 100, 100))  # 不含旧 anchor


class _BurstHarness:
    """Micro-Burst 专用最小 harness：直接 mock 采样 / 点击两个原语（不经过真实
    ClickSampler / device），可以精确断言「anchor 是否被复用、有没有重新采样」。
    """

    def __init__(self, *, interval=0.8, burst_interval=0.2):
        self.task = _make_task()
        self.task._next_settlement_click_interval = Mock(return_value=interval)
        self.task._sample_interval = Mock(return_value=burst_interval)
        self.sample_calls: list[str] = []      # 每次采样记录 region.name
        self.point_seq: list[tuple[int, int]] = []   # 待返回坐标序列，测试自行填充
        self.task._sample_settlement_point = Mock(
            side_effect=lambda region: (self.sample_calls.append(region.name), self.point_seq.pop(0))[1])
        self.clicks: list[tuple] = []          # (point, control_name)
        self.task._click_settlement_point = Mock(
            side_effect=lambda point, name: self.clicks.append((point, name)))
        # v1.1 Observed Micro-Burst：默认「第一下点击后观察，仍是同一页」（跟随最近一次
        # `step()` 传入的 `current_page`）；测试可在调用 `step()` 前显式覆盖
        # `self.task._classify_general_battle_page` 来模拟"已推进 / 已离开 / Unknown"。
        self._last_current_page = None
        self.task._classify_general_battle_page = Mock(side_effect=lambda: self._last_current_page)
        self.context = _settlement_context()

    def step(self, *, current_page, stage_name, region):
        self._last_current_page = current_page
        self.task._settlement_burst_step(
            self.context, current_page=current_page, stage_name=stage_name,
            region_provider=(region if callable(region) else (lambda: region)),
        )


class SettlementMicroBurstTest(unittest.TestCase):
    def test_case1_same_anchor_double_click(self):
        # CASE 1：budget=2（roll<=5），burst_size=2 → 两次点击坐标 / control_name 完全相同。
        h = _BurstHarness()
        h.point_seq = [(100, 200)]
        with patch.object(gb, "random_int", side_effect=[1, 2]):
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.clicks, [((100, 200), "random_default"), ((100, 200), "random_default")])

    def test_case2_anchor_sampled_once_not_per_click(self):
        # CASE 2：同一 state 内，anchor sampler 只调用 1 次，两次 click 共用同一 anchor。
        h = _BurstHarness()
        h.point_seq = [(100, 200)]
        with patch.object(gb, "random_int", side_effect=[1, 2]):
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.sample_calls, ["random_default"])

    def test_case_b_result_burst_stops_when_observation_advances_to_reward(self):
        # CASE B（v1.1）：Result 第一下点击后 mid-burst 观察发现已经推进到 Reward——即使
        # desired burst=2，也必须只点 1 次；不在旧 state（Result）上补第二下，新 state
        # 留给下一次 `_settlement_burst_step` 调用重新决定 anchor（不在本次 burst 内处理）。
        h = _BurstHarness()
        h.point_seq = [(100, 200)]
        h.task._classify_general_battle_page = Mock(return_value=gb.page_reward)
        with patch.object(gb, "random_int", side_effect=[1, 2]):   # budget=2, desired_burst=2
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.clicks, [((100, 200), "random_default")])   # 只点了 1 次
        self.assertEqual(h.context.settlement_clicks_used, 1)
        self.assertEqual(h.context.settlement_total_clicks, 1)
        self.assertTrue(h.context.settlement_session_active)   # 仍在 settlement 内，未销毁
        self.assertEqual(h.context.settlement_click_budget, 2)  # Result segment 未被 teardown 清零

    def test_case_e_chained_result_burst_stop_then_reward_keeps_anchor(self):
        # CASE E（v1.1，链式，锁定十一的核心要求）：紧接 CASE B 的同一个 session——burst
        # 被 observe 中止后不动 anchor；主循环下一帧把 last_page 同步为 Result，用
        # current_page=Reward 再调用一次 step()，anchor 落在 Reward 安全区域内且随机
        # 结果=keep，证明「页面推进 != 必须换点」在跨帧真实链路上同样成立。
        h = _BurstHarness()
        h.point_seq = [(50, 50)]
        h.task._classify_general_battle_page = Mock(return_value=gb.page_reward)
        with patch.object(gb, "random_int", side_effect=[1, 2]):   # budget=2, desired_burst=2
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(len(h.clicks), 1)
        self.assertTrue(h.context.settlement_session_active)
        self.assertEqual(h.context.settlement_anchor, (50, 50))

        h.context.last_page = gb.page_battle_result   # 模拟主循环把上一帧页面同步进 context
        with patch.object(gb, "random_int", side_effect=[1, 1]):   # keep + Reward segment budget=2
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.context.settlement_anchor, (50, 50))   # 仍是同一个 A
        self.assertEqual(h.context.settlement_click_budget, 2)     # Reward 获得独立 segment
        self.assertEqual(h.context.settlement_clicks_used, 0)
        # session 初始化时采样过 1 次（拿到 A）；Reward 阶段判定安全+keep，没有再重新采样。
        self.assertEqual(h.sample_calls, ["random_default"])
        self.assertEqual(len(h.clicks), 1)   # 第二帧被节流计时器挡下，没有产生新点击

    def test_case3_state_advance_keep_when_safe_and_random_keeps(self):
        # CASE 3：Generic Result → Reward，旧 anchor 在新 state 安全区域内，随机结果=keep。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = _REGION_A.name
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        h.point_seq = [(999, 999)]   # 如果误触发重新采样会被点到，用于反证
        with patch.object(gb, "random_int", side_effect=[1, 1, 2]):  # keep + 新 segment=2 + burst=2
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.context.settlement_anchor, (50, 50))          # anchor 未变
        self.assertEqual(h.sample_calls, [])                              # 完全没有重新采样
        self.assertEqual(h.clicks, [((50, 50), "region_b"), ((50, 50), "region_b")])
        self.assertEqual(h.context.settlement_anchor_switches, 0)

    def test_case4_state_advance_resample_when_random_switches(self):
        # CASE 4：安全、但随机结果=换点 → resample 一次得到 B，B 只采样一次。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = _REGION_A.name
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        h.point_seq = [(80, 80)]
        with patch.object(gb, "random_int", side_effect=[100, 1, 1]):  # switch + 新 segment=2 + burst=1
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.sample_calls, ["region_b"])            # 只重新采样一次
        self.assertEqual(h.context.settlement_anchor, (80, 80))
        self.assertEqual(h.context.settlement_anchor_switches, 1)
        self.assertEqual(h.clicks, [((80, 80), "region_b")])

    def test_case5_unsafe_cross_state_forces_resample_even_if_random_would_keep(self):
        # CASE 5：旧 anchor 不在新 state 安全区域内 —— 即使随机策略想 keep，也必须强制换点，
        # 且不计入「主动换点」次数。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = _REGION_A.name
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        h.point_seq = [(600, 600)]
        with patch.object(gb, "random_int", side_effect=[1, 1]) as ri:  # 新 segment=2 + burst=1
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_INCOMPAT)
        self.assertEqual(h.sample_calls, ["region_b"])
        self.assertEqual(h.context.settlement_anchor, (600, 600))
        self.assertEqual(h.context.settlement_anchor_switches, 0)   # 安全 fallback 不计入主动换点
        # 不安全分支不咨询 keep/switch 概率：只消费新 segment budget + burst size。
        self.assertEqual(ri.call_count, 2)

    def test_case6_segment_budget_is_not_a_fill_requirement(self):
        # segment 抽到 4，但一次 burst 只用了 2；semantic terminal 可让剩余节奏预算直接作废。
        h = _BurstHarness()
        h.point_seq = [(10, 10)]
        with patch.object(gb, "random_int", side_effect=[9, 2]):  # budget roll=9 -> 4，burst_size roll=2 -> 2
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.context.settlement_click_budget, 4)
        self.assertEqual(h.context.settlement_clicks_used, 2)     # 只用了 2，不是 4
        self.assertEqual(h.context.settlement_total_clicks, 2)
        self.assertEqual(len(h.clicks), 2)

    def test_case6b_segment_exhausted_renews_on_fresh_same_state(self):
        # v1.2：fresh classify 仍是同一结算 state 时，used == budget 续一个新 segment。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 2
        h.context.settlement_clicks_used = 2
        h.context.settlement_total_clicks = 2
        h.context.settlement_anchor = (10, 10)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        with patch.object(gb, "random_int", side_effect=[1, 1]) as ri:  # 新 segment=2 + burst=1
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.clicks, [((10, 10), "random_default")])
        self.assertEqual(h.context.settlement_click_budget, 2)
        self.assertEqual(h.context.settlement_clicks_used, 1)
        self.assertEqual(h.context.settlement_total_clicks, 3)
        self.assertEqual(ri.call_count, 2)

    def test_case_c_unit_reward_to_terminal_freezes_after_first_click_and_tears_down(self):
        # CASE C（v1.1，单元级；端到端版本见 SettlementSessionTeardownTest）：Reward 第
        # 一下点击后 mid-burst 观察发现已经进入 page_battle_prepare（Challenge 占位）——
        # 即使 remaining budget>0、desired burst=2，也必须只点 1 次并立即 teardown。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "reward"
        h.context.last_page = gb.page_reward
        h.task._classify_general_battle_page = Mock(return_value=gb.page_battle_prepare)
        with patch.object(gb, "random_int", side_effect=[2]):   # desired_burst=2
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(h.clicks, [((50, 50), "random_default")])   # 只点了 1 次
        self.assertFalse(h.context.settlement_session_active)         # 已 teardown
        self.assertEqual(h.context.settlement_click_budget, 0)
        self.assertEqual(h.context.settlement_total_clicks, 0)
        self.assertIsNone(h.context.settlement_anchor)

    def test_case_d_unknown_observation_cancels_second_click_without_teardown(self):
        # CASE D（v1.1）：第一下点击后 fresh 观察既不是同一 state、也不是另一个已知结算
        # 页、也不是明确的 Challenge/FIRE 相关页——而是 Unknown（None）。必须不补第二
        # 下，但也不能销毁 session（不能断定已经离开 settlement），交给既有 bounded
        # recovery / missing-page 处理决定下一步。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "reward"
        h.context.last_page = gb.page_reward
        h.task._classify_general_battle_page = Mock(return_value=None)
        with patch.object(gb, "random_int", side_effect=[2]):   # desired_burst=2
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(h.clicks, [((50, 50), "random_default")])   # 只点了 1 次，不盲点第二下
        self.assertTrue(h.context.settlement_session_active)          # 未 teardown
        self.assertEqual(h.context.settlement_clicks_used, 2)
        self.assertEqual(h.context.settlement_total_clicks, 2)
        self.assertEqual(h.context.settlement_anchor, (50, 50))       # anchor 原样保留

    def test_case_g_budget_ceiling_not_filled_when_terminal_right_after_first_click(self):
        # CASE G（v1.1，显式版）：budget=4，但第一下点击后立刻观察到 terminal——总点击数
        # 必须是 1，teardown 当下真实 used=1/4（通过日志断言，而不是 teardown 清零后的
        # 0），不会为了「凑够预算」继续补点。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 0
        h.context.settlement_total_clicks = 0
        h.context.settlement_anchor = (70, 70)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "reward"
        h.context.last_page = gb.page_reward
        h.task._classify_general_battle_page = Mock(return_value=gb.page_battle_prepare)
        with patch.object(gb, "random_int", side_effect=[2]), \
             patch.object(gb.logger, "info") as info:
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(len(h.clicks), 1)
        self.assertFalse(h.context.settlement_session_active)
        teardown_msgs = [c.args[0] for c in info.call_args_list
                         if c.args[0].startswith("Settlement terminal reached:")]
        self.assertEqual(len(teardown_msgs), 1)
        self.assertIn("total_clicks=1", teardown_msgs[0])

    def test_case7_direct_reward_entry_skips_result_without_error(self):
        # CASE 7：状态跳级——从未见过 Generic Result，直接在 Reward 首次触发 session，
        # 不报错、正常初始化并点击。
        h = _BurstHarness()
        h.point_seq = [(300, 300)]
        h.context.last_page = None   # 从未处理过任何结算页
        with patch.object(gb, "random_int", side_effect=[1, 2]):
            h.step(current_page=gb.page_reward, stage_name="reward",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertTrue(h.context.settlement_session_active)
        self.assertEqual(h.clicks, [((300, 300), "random_default"), ((300, 300), "random_default")])

    def test_case9_repeated_polling_after_safety_cap_does_not_grow_clicks(self):
        # 固定 lifecycle 安全帽耗尽后，即使页面持续 Reward，也不再续 segment / 点击。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 2
        h.context.settlement_clicks_used = 2
        h.context.settlement_total_clicks = GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS
        h.context.settlement_anchor = (10, 10)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        for _ in range(10):
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.clicks, [])
        self.assertEqual(h.context.settlement_clicks_used, 2)
        self.assertEqual(h.context.settlement_total_clicks, GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS)

    def test_case10_blind_burst_never_exceeds_two_even_with_large_budget(self):
        # CASE 10：即使 budget=4，单次 burst（无截图/无重新 classify）永远 <= 2。
        h = _make_task()
        for _ in range(500):
            self.assertIn(h._sample_settlement_burst_size(), (1, 2))
        src = inspect.getsource(GeneralBattle._sample_settlement_burst_size)
        self.assertIn("random_int(1, 2)", src)

    def test_case_h_no_third_click_before_next_fresh_semantic_decision(self):
        # CASE H（v1.1）：同 state 内 first→approved second 是唯一被允许的「无 fresh 语义
        # 判断」连续点击；紧接着的下一次调用（哪怕 remaining budget 仍然充足）必须被节
        # 流计时器挡下——不会因为「burst_size 抽到过 2」就在没有新的 fresh 语义判断的
        # 情况下产生第三次点击。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 0
        h.context.settlement_total_clicks = 0
        h.context.settlement_anchor = (20, 20)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "generic_result"
        h.context.last_page = gb.page_battle_result
        h.task._classify_general_battle_page = Mock(return_value=gb.page_battle_result)
        with patch.object(gb, "random_int", side_effect=[2]):   # desired_burst=2 -> first+approved second
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                  region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(len(h.clicks), 2)
        self.assertEqual(h.context.settlement_clicks_used, 2)

        # 紧接着再调用一次（模拟主循环下一帧仍处于同一 state、budget 仍剩 2）——节流
        # 计时器刚被武装、尚未到期，必须直接放行、不产生第三次点击。
        h.step(current_page=gb.page_battle_result, stage_name="generic_result",
              region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(len(h.clicks), 2)   # 仍然是 2，不是 3

    def test_case11_old_fixed_two_click_replaced_not_stacked(self):
        # CASE 11：旧 `_advance_generic_result`（固定两次）已被移除，不存在旧 + 新叠加执行。
        self.assertFalse(hasattr(GeneralBattle, "_advance_generic_result"))
        result_src = inspect.getsource(GeneralBattle._handle_result)
        self.assertEqual(result_src.count("_settlement_burst_step("), 1)
        self.assertNotIn("_advance_generic_result", result_src)

    def test_case12_reward_burst_uses_select_reward_region_as_provider(self):
        # CASE 12：Reward 的 layout-aware 安全区域策略保持——burst 的 region_provider
        # 就是现有 `_select_reward_region`，没有被统一退化成 random_default。
        reward_src = inspect.getsource(GeneralBattle._handle_reward)
        self.assertIn("region_provider=self._select_reward_region", reward_src)

    def test_case13_lose_frame_uses_same_burst_path_as_win(self):
        # CASE 13：Lose（I_FALSE）本就属于 `_is_generic_result_context()`（既有范围，未缩小
        # 也未扩大），因此和 Win 一样纳入同一个 Micro-Burst Session，不做特殊排除。
        h = _SettlementHarness()
        h.task.appear = Mock(side_effect=lambda r, **kw: r is h.task.I_FALSE)
        with patch.object(gb, "random_int", side_effect=[1, 1]):
            h.task._handle_result(h.context, SimpleNamespace())
        self.assertTrue(h.context.settlement_session_active)     # 走的是 session/burst 路径
        self.assertEqual(h.context.settlement_region_name, "random_default")
        h.task.device.click.assert_called()                      # 真实产生了点击（未被特殊排除）

    def test_v12_case1_level_c_budget2_result_reward_then_reward_renews(self):
        # 真机失败链：Result 先用 1 下；Reward 获得独立 budget=2，用完后仍为 Reward 则续段。
        h = _BurstHarness()
        h.point_seq = [(50, 50)]
        with patch.object(gb, "random_int", side_effect=[1, 1]):  # Result segment=2，burst=1
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                   region=GeneralBattle.C_RANDOM_DEFAULT)
        h.context.last_page = gb.page_battle_result
        h.context.settlement_click_timer.expire()
        with patch.object(gb, "random_int", side_effect=[1, 1, 1]):  # keep，Reward segment=2，burst=1
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.context.settlement_click_budget, 2)
        self.assertEqual(h.context.settlement_clicks_used, 1)
        self.assertEqual(h.context.settlement_total_clicks, 2)

        h.context.last_page = gb.page_reward
        h.context.settlement_click_timer.expire()
        with patch.object(gb, "random_int", return_value=1):
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.context.settlement_clicks_used, 2)

        h.context.settlement_click_timer.expire()
        with patch.object(gb, "random_int", side_effect=[1, 1]):  # renew segment=2，burst=1
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertTrue(h.context.settlement_session_active)
        self.assertEqual(h.context.settlement_clicks_used, 1)
        self.assertEqual(h.context.settlement_total_clicks, 4)
        self.assertEqual(len(h.clicks), 4)

    def test_v12_case2_second_segment_reaches_terminal_and_tears_down(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=2,
            settlement_total_clicks=2, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="reward",
            last_page=gb.page_reward,
        )
        h.task._classify_general_battle_page = Mock(return_value=gb.page_battle_prepare)
        with patch.object(gb, "random_int", side_effect=[1, 2]):  # renew segment=2，想补第二下
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(h.clicks, [((50, 50), "region_a")])
        self.assertFalse(h.context.settlement_session_active)
        self.assertEqual(h.context.settlement_total_clicks, 0)

    def test_v12_case3_segment_exhaustion_is_not_terminal(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=2,
            settlement_total_clicks=2, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="reward",
            last_page=gb.page_reward,
        )
        with patch.object(gb, "random_int", side_effect=[1, 1]), \
             patch.object(gb.logger, "info") as info:
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        messages = [c.args[0] for c in info.call_args_list]
        self.assertTrue(any(m.startswith("Settlement segment exhausted:") for m in messages))
        self.assertFalse(any("terminal" in m.lower() for m in messages))
        self.assertTrue(h.context.settlement_session_active)
        self.assertEqual(len(h.clicks), 1)

    def test_v12_case4_semantic_terminal_preempts_remaining_segment_budget(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=4, settlement_clicks_used=1,
            settlement_total_clicks=1, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="reward",
            last_page=gb.page_reward,
        )
        h.task._classify_general_battle_page = Mock(return_value=gb.page_battle_prepare)
        with patch.object(gb, "random_int", return_value=2):
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(len(h.clicks), 1)
        self.assertFalse(h.context.settlement_session_active)

    def test_v12_case5_unknown_does_not_renew_or_blind_second_click(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=1,
            settlement_total_clicks=1, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="reward",
            last_page=gb.page_reward,
        )
        h.task._classify_general_battle_page = Mock(return_value=None)
        h.task._sample_settlement_segment_budget = Mock(return_value=2)
        with patch.object(gb, "random_int", return_value=2):
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(len(h.clicks), 1)
        self.assertEqual(h.context.settlement_clicks_used, 2)
        h.task._sample_settlement_segment_budget.assert_not_called()
        self.assertTrue(h.context.settlement_session_active)

    def test_v12_case6_state_advance_gets_independent_segment_budget(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=1,
            settlement_total_clicks=1, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="generic_result",
            last_page=gb.page_battle_result,
        )
        with patch.object(gb, "random_int", side_effect=[1, 9, 1]):  # keep，Reward budget=4，burst=1
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_B_COMPAT)
        self.assertEqual(h.context.settlement_click_budget, 4)
        self.assertEqual(h.context.settlement_clicks_used, 1)
        self.assertEqual(h.context.settlement_total_clicks, 2)

    def test_v12_case7_segment_renew_keeps_safe_anchor(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=2,
            settlement_total_clicks=2, settlement_anchor=(50, 50),
            settlement_region_name="region_a", settlement_stage_name="reward",
            last_page=gb.page_reward,
        )
        with patch.object(gb, "random_int", side_effect=[1, 1]):
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(h.context.settlement_anchor, (50, 50))
        self.assertEqual(h.sample_calls, [])
        self.assertEqual(h.clicks, [((50, 50), "region_a")])

    def test_v12_case8_safety_cap_blocks_renew_without_claiming_terminal(self):
        h = _BurstHarness()
        h.context = _settlement_context(
            settlement_session_active=True, settlement_click_budget=2, settlement_clicks_used=2,
            settlement_total_clicks=GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS,
            settlement_anchor=(50, 50), settlement_region_name="region_a",
            settlement_stage_name="reward", last_page=gb.page_reward,
        )
        h.task._sample_settlement_segment_budget = Mock(return_value=2)
        with patch.object(gb.logger, "info") as info:
            for _ in range(5):
                h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
        self.assertEqual(h.clicks, [])
        h.task._sample_settlement_segment_budget.assert_not_called()
        self.assertTrue(h.context.settlement_session_active)
        self.assertFalse(any("terminal" in c.args[0].lower() for c in info.call_args_list))

    def test_v12_case9_multiple_segments_are_bounded_by_total_click_cap(self):
        h = _BurstHarness()
        h.point_seq = [(50, 50)]
        with patch.object(gb, "random_int", return_value=2):
            for index in range(10):
                if index:
                    h.context.settlement_click_timer.expire()
                h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)
                h.context.last_page = gb.page_reward
        self.assertEqual(len(h.clicks), GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS)
        self.assertEqual(h.context.settlement_total_clicks, GeneralBattle.SETTLEMENT_MAX_TOTAL_CLICKS)
        self.assertTrue(h.context.settlement_session_active)
        self.assertEqual(h.sample_calls, ["region_a"])  # 多 segment 不强制换 anchor

    def test_v12_case10_state_advance_still_cancels_blind_second_click(self):
        h = _BurstHarness()
        h.point_seq = [(50, 50)]
        h.task._classify_general_battle_page = Mock(return_value=gb.page_reward)
        with patch.object(gb, "random_int", side_effect=[1, 2]):
            h.step(current_page=gb.page_battle_result, stage_name="generic_result",
                   region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(h.clicks, [((50, 50), "random_default")])
        self.assertEqual(h.context.settlement_total_clicks, 1)

    def test_budget_distribution_weights(self):
        # 权重表本身：1~5 -> 2、6~8 -> 3、9~10 -> 4。
        task = _make_task()
        mapping = {1: 2, 3: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 4, 10: 4}
        for roll, expected in mapping.items():
            with patch.object(gb, "random_int", return_value=roll):
                self.assertEqual(task._sample_settlement_segment_budget(), expected, roll)

    def test_budget_range_is_2_to_4_over_many_samples(self):
        task = _make_task()
        seen = {task._sample_settlement_segment_budget() for _ in range(500)}
        self.assertTrue(seen.issubset({2, 3, 4}))
        self.assertEqual(seen, {2, 3, 4})   # 500 次抽样应该三个值都出现过


# --------------------------------------------------------------------------------------
# B'''. Micro-Burst observe 间隔数值（2026-09-23：0.10~0.30 → 0.30~0.60）
#
# 本节只锁「等多久再看」这一个数值，以及「放宽间隔之后状态机一个字都没变」——第二下仍必须
# 由观察到的新状态重新授权，不能退化成固定 sleep 后无条件补第二下。
# --------------------------------------------------------------------------------------

class SettlementBurstIntervalValueTest(unittest.TestCase):
    RANGE = (0.30, 0.60)

    def _harness_with_real_interval(self):
        """用真实的 `_sample_interval`（不 mock），让 burst 真的走到 `random_delay`。"""
        h = _BurstHarness()
        del h.task._sample_interval      # 去掉实例上的 Mock，回落到类里的真实实现
        return h

    def test_constant_is_exactly_0_30_to_0_60(self):
        self.assertEqual(GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE, self.RANGE)

    def test_fire_settlement_burst_reads_that_constant(self):
        src = inspect.getsource(GeneralBattle._fire_settlement_burst)
        self.assertIn('self._sample_interval(self.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)', src)

    def test_observe_interval_is_sampled_from_the_new_range_at_runtime(self):
        h = self._harness_with_real_interval()
        h.point_seq = [(100, 200)]
        with patch.object(gb, 'random_int', side_effect=[1, 2]), \
                patch.object(gb, 'random_delay', return_value=0.4) as delay, \
                patch.object(gb.time, 'sleep') as slept:
            h.step(current_page=gb.page_battle_result, stage_name='generic_result',
                   region=GeneralBattle.C_RANDOM_DEFAULT)
        delay.assert_called_once_with(*self.RANGE)
        slept.assert_called_once_with(0.4)      # 睡的就是本次采样值

    def test_each_burst_samples_the_interval_independently(self):
        """两次 burst 各自独立采样一次，不是任务开始时抽一次后固定复用。"""
        h = self._harness_with_real_interval()
        h.point_seq = [(100, 200), (300, 400)]
        with patch.object(gb, 'random_int', side_effect=[1, 2, 1, 2]), \
                patch.object(gb, 'random_delay', side_effect=[0.31, 0.59]) as delay, \
                patch.object(gb.time, 'sleep'):
            h.step(current_page=gb.page_battle_result, stage_name='generic_result',
                   region=GeneralBattle.C_RANDOM_DEFAULT)
            h.context.settlement_clicks_used = 0        # 让下一段仍有预算
            # 跨 burst 节流（`SETTLEMENT_CLICK_INTERVAL_RANGE`，另一个独立 owner）到点，
            # 模拟「下一帧」——否则第二次 burst 会被节流挡住，测不到本轮要验的 observe 间隔。
            h.context.settlement_click_timer.expire()
            h.step(current_page=gb.page_battle_result, stage_name='generic_result',
                   region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(delay.call_args_list, [call(*self.RANGE), call(*self.RANGE)])

    def test_longer_interval_does_not_unconditionally_authorize_the_second_click(self):
        """核心回归：间隔调大之后，第二下仍然只有在 fresh 观察到「还是同一个结算页」时才发生。
        观察到已经推进 → 只点 1 次；观察仍是同一页 → 才点第 2 次。"""
        # ① 观察发现已推进到 Reward：只点 1 次
        advanced = self._harness_with_real_interval()
        advanced.point_seq = [(100, 200)]
        advanced.task._classify_general_battle_page = Mock(return_value=gb.page_reward)
        with patch.object(gb, 'random_int', side_effect=[1, 2]), \
                patch.object(gb, 'random_delay', return_value=0.4), \
                patch.object(gb.time, 'sleep'):
            advanced.step(current_page=gb.page_battle_result, stage_name='generic_result',
                          region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(len(advanced.clicks), 1)
        # ② 观察仍是同一页：才允许同 anchor 的第二下
        same = self._harness_with_real_interval()
        same.point_seq = [(100, 200)]
        with patch.object(gb, 'random_int', side_effect=[1, 2]), \
                patch.object(gb, 'random_delay', return_value=0.4), \
                patch.object(gb.time, 'sleep'):
            same.step(current_page=gb.page_battle_result, stage_name='generic_result',
                      region=GeneralBattle.C_RANDOM_DEFAULT)
        self.assertEqual(same.clicks, [((100, 200), 'random_default'),
                                       ((100, 200), 'random_default')])
        # 第二下之前确实重新截图 + 重新分类过（Click → Observe → Decide 未被间隔改动破坏）
        self.assertGreaterEqual(same.task.screenshot.call_count, 1)
        self.assertGreaterEqual(same.task._classify_general_battle_page.call_count, 1)

    def test_activity_shikigami_reaction_is_a_separate_constant(self):
        """ActivityShikigami 专用结算 reaction 与本常量完全独立，不因本轮调整而变化。"""
        from tasks.ActivityShikigami.activities.normal import ACTIVITY_SETTLEMENT_REACTION
        self.assertEqual(ACTIVITY_SETTLEMENT_REACTION, (0.45, 0.85))
        self.assertNotEqual(ACTIVITY_SETTLEMENT_REACTION,
                            GeneralBattle.SETTLEMENT_BURST_CLICK_INTERVAL_RANGE)


# --------------------------------------------------------------------------------------
# B''. Settlement 点击永不穿透到 Challenge / FIRE 页面 —— 离开结算立即销毁 session
# --------------------------------------------------------------------------------------

class SettlementSessionTeardownTest(unittest.TestCase):
    def _active_context(self):
        return _settlement_context(
            settlement_session_active=True,
            settlement_click_budget=4,
            settlement_clicks_used=1,
            settlement_total_clicks=1,
            settlement_anchor=(100, 200),
            settlement_region_name="random_default",
            settlement_stage_name="generic_result",
            settlement_anchor_switches=1,
        )

    def test_teardown_clears_all_settlement_fields(self):
        task = _make_task()
        ctx = self._active_context()
        task._teardown_settlement_session(ctx)
        self.assertFalse(ctx.settlement_session_active)
        self.assertEqual(ctx.settlement_click_budget, 0)
        self.assertEqual(ctx.settlement_clicks_used, 0)
        self.assertEqual(ctx.settlement_total_clicks, 0)
        self.assertIsNone(ctx.settlement_anchor)
        self.assertIsNone(ctx.settlement_region_name)
        self.assertIsNone(ctx.settlement_stage_name)
        self.assertEqual(ctx.settlement_anchor_switches, 0)

    def test_teardown_is_noop_when_session_not_active(self):
        # 没有 session 时销毁不应该产生任何副作用 / 报错（也不应该打印销毁日志）。
        task = _make_task()
        ctx = _settlement_context()
        with patch.object(gb.logger, "info") as info:
            task._teardown_settlement_session(ctx)
        info.assert_not_called()

    def test_main_loop_destroys_active_burst_session_before_leaving(self):
        """v1.1 端到端（CASE C 的最强版本）：第 1 帧命中通用结果标志、session 建立并执行
        第一次点击；**第一下点击后 mid-burst 的 fresh 语义观察就直接发现已经进入
        page_battle_prepare（Challenge 占位页）**——必须在同一次 burst 内立即销毁 session、
        绝不执行第二下；主循环第 2 帧再次确认该页并正常退出。全程真实 `device.click`
        只应该被调用 1 次，不是 2 次。
        """
        task = _make_task()
        task.current_count = 0
        task.config = SimpleNamespace(global_game=SimpleNamespace(battle=SimpleNamespace(battle_timeout=420)))
        task._battle_shared_state = {}
        task._get_battle_behavior_scopes = Mock(return_value={})
        task._build_timed_battle_inspections = Mock(return_value={})
        task._custom_pages_registered = True
        task.device = SimpleNamespace(
            click=Mock(), click_record_clear=Mock(),
            stuck_record_add=Mock(), stuck_record_clear=Mock(), detect_record=set(),
            screenshot_interval_set=Mock(),
        )
        task.screenshot = Mock()
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_WIN)   # 通用结果 -> 走 burst
        task.appear_then_click = Mock(return_value=False)

        real_fire_burst = gb.GeneralBattle._fire_settlement_burst
        fire_calls = []

        def _tracked_fire(self, context, current_page):
            fire_calls.append(context.settlement_session_active)
            return real_fire_burst(self, context, current_page)
        task._fire_settlement_burst = _tracked_fire.__get__(task, gb.GeneralBattle)

        captured_contexts = []
        original_build_context = task._build_context

        def _capture(*a, **kw):
            ctx = original_build_context(*a, **kw)
            captured_contexts.append(ctx)
            return ctx
        task._build_context = _capture

        config = gb.GeneralBattleConfig()
        # random_int 序列：budget roll -> 2；desired_burst_size roll -> 2（想补第二下，
        # 但会被 mid-burst 观察否决）。detect_page_in 序列：主循环第 1 帧 = result；
        # 第一下点击后 mid-burst 观察 = 已经是 prepare（Challenge 占位）；主循环第 2 帧
        # 再次确认 = prepare（触发 `_handle_prepare` 的非连战早退分支）。
        with patch.object(gb, "random_int", side_effect=[1, 2]), \
             patch.object(gb.GameUi, "detect_page_in",
                          side_effect=[gb.page_battle_result, gb.page_battle_prepare,
                                       gb.page_battle_prepare]):
            task.run_general_battle(config=config)

        context = captured_contexts[0]
        self.assertTrue(fire_calls[0])          # burst 触发时 session 确实是活跃的
        self.assertFalse(context.settlement_session_active)   # mid-burst 观察后必须已销毁
        self.assertEqual(context.settlement_click_budget, 0)
        self.assertEqual(context.settlement_total_clicks, 0)
        self.assertEqual(context.settlement_anchor, None)
        task.device.click.assert_called_once()   # 只点了 1 次——第二下被 observe 取消，不是 2 次

    def test_v12_second_reward_segment_terminal_returns_battle_result(self):
        """端到端复现 v1.2：Result 一下、Reward 首段两下、Reward 第二段一下后 terminal。"""
        task = _make_task()
        task.current_count = 0
        task.config = SimpleNamespace(global_game=SimpleNamespace(battle=SimpleNamespace(battle_timeout=420)))
        task._battle_shared_state = {}
        task._get_battle_behavior_scopes = Mock(return_value={})
        task._build_timed_battle_inspections = Mock(return_value={})
        task._custom_pages_registered = True
        task.device = SimpleNamespace(
            click=Mock(), click_record_clear=Mock(),
            stuck_record_add=Mock(), stuck_record_clear=Mock(), detect_record=set(),
            screenshot_interval_set=Mock(),
        )
        task.screenshot = Mock()
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_WIN)
        task.appear_then_click = Mock(return_value=False)
        task._select_reward_region = Mock(return_value=task.C_RANDOM_DEFAULT)
        task._sample_settlement_point = Mock(return_value=(800, 500))
        task._sample_interval = Mock(return_value=0)
        task._next_settlement_click_interval = Mock(return_value=0)

        captured_contexts = []
        original_build_context = task._build_context

        def _capture(*a, **kw):
            ctx = original_build_context(*a, **kw)
            # 主循环可能在同一毫秒内推进；用确定性 timer 避免真实时钟让某一帧偶发未到点。
            ctx.settlement_click_timer = _Timer()
            ctx.settlement_click_timer.reached = Mock(return_value=True)
            captured_contexts.append(ctx)
            return ctx

        task._build_context = _capture
        pages = [
            gb.page_battle_result, gb.page_reward,  # outer Result + mid-burst observe advances
            gb.page_reward, gb.page_reward,         # Reward segment #1: click 1 + click 2
            gb.page_reward, gb.page_battle_prepare, # Reward segment #2 click 1 + terminal observe
            gb.page_battle_prepare,                 # outer semantic terminal -> normal result return
        ]
        rolls = [
            1, 2,       # Result segment=2，burst wants 2 but advance cancels second
            1, 1, 1,   # keep anchor，Reward segment=2，first burst=1
            1,          # Reward segment #1 second burst=1 -> exhausted
            1, 2,       # renew segment=2，first click observes terminal
        ]
        with patch.object(gb, "random_int", side_effect=rolls), \
             patch.object(gb.GameUi, "detect_page_in", side_effect=pages):
            result = task.run_general_battle(config=gb.GeneralBattleConfig())

        self.assertTrue(result)
        self.assertEqual(task.device.click.call_count, 4)
        context = captured_contexts[0]
        self.assertFalse(context.settlement_session_active)
        self.assertEqual(context.settlement_total_clicks, 0)

    def test_case_i_teardown_ordering_click_then_observe_then_teardown(self):
        # CASE I（v1.1）：不仅验证最终字段被清空，还要验证真实调用顺序——click → fresh
        # observe → teardown，且 teardown 之后没有任何第二次 click 调用（此时 FIRE
        # handler 尚未执行）。
        h = _BurstHarness()
        h.context.settlement_session_active = True
        h.context.settlement_click_budget = 4
        h.context.settlement_clicks_used = 1
        h.context.settlement_total_clicks = 1
        h.context.settlement_anchor = (50, 50)
        h.context.settlement_region_name = "random_default"
        h.context.settlement_stage_name = "reward"
        h.context.last_page = gb.page_reward

        events = []
        real_click = h.task._click_settlement_point
        h.task._click_settlement_point = Mock(
            side_effect=lambda point, name: (events.append("click"), real_click(point, name))[1])

        def _tracked_observe():
            events.append("observe")
            return gb.page_battle_prepare
        h.task._classify_general_battle_page = Mock(side_effect=_tracked_observe)

        real_teardown = h.task._teardown_settlement_session

        def _tracked_teardown(context):
            events.append("teardown")
            return real_teardown(context)
        h.task._teardown_settlement_session = Mock(side_effect=_tracked_teardown)

        with patch.object(gb, "random_int", side_effect=[2]):
            h.step(current_page=gb.page_reward, stage_name="reward", region=_REGION_A)

        self.assertEqual(events, ["click", "observe", "teardown"])   # 严格顺序：先点、再观察、再销毁
        self.assertEqual(len(h.clicks), 1)   # 真实点击次数仍然只有 1（teardown 后没有第二次 click）


# --------------------------------------------------------------------------------------
# C. Reward Overlay —— 点中就本帧 CONTINUE，不再同帧 region click
# --------------------------------------------------------------------------------------

class RewardOverlayTest(unittest.TestCase):
    def _reward_harness(self):
        h = _SettlementHarness()
        h.context.last_page = gb.page_reward
        h.task._classify_general_battle_page = Mock(return_value=gb.page_reward)
        return h

    def test_over_ghost_click_returns_continue_without_region_click(self):
        h = self._reward_harness()
        h.task.appear_then_click = Mock(side_effect=lambda r, **kw: r is h.task.I_OVER_GHOST)
        action = h.task._handle_reward(h.context, SimpleNamespace())
        self.assertEqual(action, BattleAction.CONTINUE)
        self.assertEqual(h.names, [])                            # 没有 region click
        h.task._sample_settlement_click.assert_not_called()

    def test_skin_confirm_click_returns_continue_without_region_click(self):
        h = self._reward_harness()
        h.task.appear_then_click = Mock(side_effect=lambda r, **kw: r is h.task.I_GB_SKIN_CONFIRM)
        action = h.task._handle_reward(h.context, SimpleNamespace())
        self.assertEqual(action, BattleAction.CONTINUE)
        self.assertEqual(h.names, [])

    def test_overlay_checked_in_order_over_ghost_then_skin_confirm(self):
        h = self._reward_harness()
        seen = []
        h.task.appear_then_click = Mock(side_effect=lambda r, **kw: seen.append(r) or False)
        h.task._select_reward_region = Mock(return_value=h.task.C_RANDOM_DEFAULT)
        h.task._handle_reward(h.context, SimpleNamespace())
        self.assertEqual(seen, [h.task.I_OVER_GHOST, h.task.I_GB_SKIN_CONFIRM])
        for c in h.task.appear_then_click.call_args_list:
            self.assertEqual(c.kwargs, {"interval": 0.8})

    def test_no_overlay_falls_through_to_region_click(self):
        # Micro-Burst v1.2：普通奖励布局走 `_settlement_burst_step`（`_sample_settlement_point`
        # + `_click_settlement_point`），不再是旧的 `_sample_settlement_click` 单步——
        # 这里改断言真实 `device.click` 收到的 `control_name`，语义不变：仍是
        # `_select_reward_region()` 选中的那个安全区域。
        h = self._reward_harness()
        h.task.appear_then_click = Mock(return_value=False)
        h.task._select_reward_region = Mock(return_value=h.task.C_RANDOM_SAVE_RIGHT)
        h.task._handle_reward(h.context, SimpleNamespace())
        h.task.device.click.assert_called()                      # 未 mock 随机源，burst 可能 1~2 次
        calls = h.task.device.click.call_args_list
        for c in calls:
            self.assertEqual(c.kwargs["control_name"], "random_save_right")
        # 同一 burst 内坐标必须完全相同（anchor persistence）。
        self.assertEqual(len({(c.kwargs["x"], c.kwargs["y"]) for c in calls}), 1)

    def test_reward_keeps_is_win_true(self):
        src = inspect.getsource(GeneralBattle._handle_reward)
        self.assertIn("context.is_win = True", src)


# --------------------------------------------------------------------------------------
# D. Reward Layout Policy —— marker → DEFAULT，否则 80/20
# --------------------------------------------------------------------------------------

class RewardLayoutPolicyTest(unittest.TestCase):
    def _task_with_markers(self, marker=None):
        task = _make_task()
        task.appear = Mock(side_effect=lambda r, **kw: marker is not None and r is marker)
        return task

    def test_get_battle_reward_marker_selects_default(self):
        task = self._task_with_markers(marker=None)
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_GET_BATTLE_REWARD)
        self.assertIs(task._select_reward_region(), task.C_RANDOM_DEFAULT)

    def test_get_battle_reward_2_marker_selects_default(self):
        task = _make_task()
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_GET_BATTLE_REWARD_2)
        self.assertIs(task._select_reward_region(), task.C_RANDOM_DEFAULT)

    def test_no_marker_80_percent_reaches_right(self):
        task = self._task_with_markers(marker=None)
        with patch.object(gb, "random_int", return_value=80):
            self.assertIs(task._select_reward_region(), task.C_RANDOM_SAVE_RIGHT)
        with patch.object(gb, "random_int", return_value=1):
            self.assertIs(task._select_reward_region(), task.C_RANDOM_SAVE_RIGHT)

    def test_no_marker_20_percent_reaches_bottom(self):
        task = self._task_with_markers(marker=None)
        with patch.object(gb, "random_int", return_value=81):
            self.assertIs(task._select_reward_region(), task.C_RANDOM_SAVE_BOTTOM)
        with patch.object(gb, "random_int", return_value=100):
            self.assertIs(task._select_reward_region(), task.C_RANDOM_SAVE_BOTTOM)

    def test_split_uses_public_random_int_1_100(self):
        task = self._task_with_markers(marker=None)
        with patch.object(gb, "random_int", return_value=50) as ri:
            task._select_reward_region()
        ri.assert_called_once_with(1, 100)

    def test_random_int_is_systemrandom_backed(self):
        from module.base.utils import random as rnd
        self.assertIs(gb.random_int, rnd.random_int)
        # 边界闭区间抽样，落在 [1, 100]
        got = {gb.random_int(1, 100) for _ in range(200)}
        self.assertTrue(min(got) >= 1 and max(got) <= 100)


# --------------------------------------------------------------------------------------
# E. Sampling —— 整 ROI 均匀、落点在界内、每次独立
# --------------------------------------------------------------------------------------

class SamplingTest(unittest.TestCase):
    def test_sample_settlement_click_uses_region_model_and_keeps_name(self):
        # T7-5 Stage 2：selected-region 内采样从整 ROI LEGACY_UNIFORM 改为 sample_region
        # （preferred 偏置 + default_region profile）。region 的**选择**逻辑不在这里。
        # L1 Stage 2：源码形态改为 `ClickRegion(rule.roi_front, rule.name)`，其解析恰好是同一个
        # `ClickSampler.sample_region(roi, name)`（行为等价由下一个用例的运行期断言证明）。
        src = inspect.getsource(GeneralBattle._sample_settlement_click)
        self.assertIn("ClickRegion(rule.roi_front, rule.name)", src)
        self.assertNotIn("ClickSampler.sample(rule.roi_front)", src)
        self.assertNotIn("sample_target", src)
        self.assertNotIn("STRATEGY_HABIT", src)          # 策略封装在 sample_region 内
        self.assertIn("control_name=rule.name", src)
        self.assertNotIn("self.device.click(", src)
        # 运行期：sample_region 恰一次、参数是（选定 region 的 roi_front, 名字）；sample_target 从未被调用
        task = _make_task()
        with patch.object(gb.ClickSampler, "sample_region", return_value=(801, 502)) as region,                 patch.object(gb.ClickSampler, "sample_target") as target:
            task._sample_settlement_click(GeneralBattle.C_RANDOM_DEFAULT)
        region.assert_called_once_with(GeneralBattle.C_RANDOM_DEFAULT.roi_front, GeneralBattle.C_RANDOM_DEFAULT.name)
        target.assert_not_called()

    def test_sample_settlement_click_forwards_sampler_coords(self):
        task = _make_task()
        # sample_region 内部最终仍调 ClickSampler.sample(roi, strategy=HABIT, profile=...)
        with patch.object(gb.ClickSampler, "sample", return_value=(812, 511)) as sample:
            task._sample_settlement_click(GeneralBattle.C_RANDOM_DEFAULT)
        (called_roi,), kwargs = sample.call_args
        self.assertEqual(called_roi, GeneralBattle.C_RANDOM_DEFAULT.roi_front)   # roi 位置参数不变
        self.assertEqual(kwargs.get("strategy"), "habit")
        task.device.click.assert_called_once_with(x=812, y=511, control_name="random_default")

    def test_repeated_settlement_clicks_center_biased_inside_each_region(self):
        from module.click_sampler import ClickSampler
        for region in (GeneralBattle.C_RANDOM_DEFAULT, GeneralBattle.C_RANDOM_SAVE_RIGHT,
                       GeneralBattle.C_RANDOM_SAVE_BOTTOM):
            rx, ry, rw, rh = region.roi_front
            pts = [ClickSampler.sample_region(region.roi_front, region.name) for _ in range(2000)]
            for x, y in pts:
                self.assertTrue(rx <= x < rx + rw, (region.name, x))    # 全在自身 region 内
                self.assertTrue(ry <= y < ry + rh, (region.name, y))
            self.assertGreater(len(set(pts)), 50)                        # 每次独立采样 → 非固定坐标
            # 明显围绕中心更集中（中央 25% 面积占比 > 40%，整区均匀只会 ~25%）
            cx, cy = rx + rw / 2, ry + rh / 2
            central = sum(1 for x, y in pts if abs(x - cx) < rw / 4 and abs(y - cy) < rh / 4)
            self.assertGreater(central / len(pts), 0.40, region.name)

    def test_settlement_click_throttle_arms_fresh_interval(self):
        h = _SettlementHarness()
        h.task._next_settlement_click_interval = Mock(side_effect=[0.71, 0.93])
        h.task._settlement_click(h.context)
        self.assertEqual(h.timer.limit, 0.71)
        h.timer.expire()
        h.task._settlement_click(h.context)
        self.assertEqual(h.timer.limit, 0.93)


# --------------------------------------------------------------------------------------
# F. is_win / exit_matcher / missing fallback 不变
# --------------------------------------------------------------------------------------

class UnchangedSemanticsTest(unittest.TestCase):
    def test_missing_battle_page_2_5s_fallback_unchanged(self):
        src = inspect.getsource(GeneralBattle._handle_missing_battle_page)
        self.assertIn("time.time() - context.reward_no_battle_ts >= 2.5", src)
        self.assertIn("EXIT_WIN if context.is_win else BattleAction.EXIT_LOSE", src)

    def test_base_exit_matcher_still_none(self):
        self.assertIsNone(GeneralBattle._exit_matcher(GeneralBattle.__new__(GeneralBattle)))

    def test_run_loop_unchanged_shape(self):
        src = inspect.getsource(GeneralBattle.run_general_battle)
        self.assertIn("page = GameUi.detect_page_in(self, page_battle_prepare, page_battle, "
                      "page_battle_result,", src)
        self.assertIn("resolved_exit_matcher = exit_matcher if exit_matcher is not None "
                      "else self._exit_matcher()", src)
        self.assertNotIn("_advance_generic_result", src)   # 序列只在 handler 里


# --------------------------------------------------------------------------------------
# G. random_click / navigation 分离，默认 RuleClick 仍 LEGACY
# --------------------------------------------------------------------------------------

class RegressionBoundaryTest(unittest.TestCase):
    def test_general_battle_no_longer_uses_random_click(self):
        src = inspect.getsource(gb)
        self.assertNotIn("import random_click", src)
        self.assertNotIn("random_click()", src)

    def test_random_click_default_right_only_intentional_baseline(self):
        # `tasks/GameUi/default_pages.py` 的 `random_click` 默认 `ltrb` 当前是
        # (False, False, True, False)（仅 RIGHT）——用户本人有意的业务修改，是当前工作树
        # 的有意基线，本轮结算迁移不得触碰它、也不得把新的 SAVE 区域反向接进它。
        from tasks.GameUi.default_pages import random_click
        sig = inspect.signature(random_click)
        self.assertEqual(sig.parameters["ltrb"].default, (False, False, True, False))
        self.assertIsNone(sig.parameters["low"].default)
        self.assertIsNone(sig.parameters["high"].default)

    def test_save_regions_not_wired_into_navigation_random_click(self):
        src = inspect.getsource(inspect.getmodule(gb))
        from tasks.GameUi import default_pages
        dp_src = inspect.getsource(default_pages)
        for token in ("random_save_right", "random_save_bottom", "C_RANDOM_SAVE"):
            self.assertNotIn(token, dp_src, token)

    def test_settlement_click_path_is_region_model_not_point_model(self):
        # T7-5 Stage 1：默认 RuleClick.coord 走 sample_target（Point preferred 偏置）。
        # T7-5 Stage 2：GeneralBattle 结算点击**不经过** coord —— `_sample_settlement_click`
        # 对业务已选定 region 走 `ClickSampler.sample_region`（Region preferred 偏置，
        # default_region profile，不做 Point 的 short_side 尺寸适配），**不是** `sample_target`。
        coord_src = inspect.getsource(gb.RuleClick.coord)
        self.assertIn("ClickSampler.sample_target(self.roi_front, self.name)", coord_src)
        settle_src = inspect.getsource(gb.GeneralBattle._sample_settlement_click)
        self.assertIn("ClickRegion(rule.roi_front, rule.name)", settle_src)   # Stage 2：Region 语义显式声明，解析即 sample_region
        self.assertNotIn("sample_target", settle_src)
        self.assertNotIn("ClickSampler.sample(rule.roi_front)", settle_src)

    def test_phase_b_private_handlers_untouched(self):
        for mod in ("tasks.SixRealms.moon_sea.base_moon_sea",
                    "tasks.SixRealms.peacock_kingdom.base_peacock_kingdom"):
            m = __import__(mod, fromlist=["*"])
            self.assertIn("random_click", inspect.getsource(m))


# --------------------------------------------------------------------------------------
# H. Task 兼容性 —— private override 不被穿透 / super() caller 走新策略
# --------------------------------------------------------------------------------------

class TaskCompatibilityTest(unittest.TestCase):
    def test_bondling_result_is_fully_private_no_super(self):
        from tasks.BondlingFairyland.script_task import ScriptTask
        src = inspect.getsource(ScriptTask._handle_result)
        self.assertNotIn("super()._handle_result", src)          # 不穿透到公共双击
        self.assertIn("random_click()", src)                     # 保留私有胜负 + 落子逻辑

    def test_bondling_reward_calls_super_and_preserves_is_win(self):
        from tasks.BondlingFairyland.script_task import ScriptTask
        src = inspect.getsource(ScriptTask._handle_reward)
        self.assertIn("super()._handle_reward(context, config)", src)
        self.assertIn("context.is_win = is_win", src)

    def test_sixrealms_moon_sea_result_and_reward_private_no_super(self):
        from tasks.SixRealms.moon_sea.base_moon_sea import BaseMoonSea
        for name in ("_handle_result", "_handle_reward"):
            src = inspect.getsource(getattr(BaseMoonSea, name))
            self.assertNotIn("super()." + name, src)

    def test_sixrealms_peacock_result_and_reward_private_no_super(self):
        from tasks.SixRealms.peacock_kingdom.base_peacock_kingdom import BasePeacockKingdom
        for name in ("_handle_result", "_handle_reward"):
            src = inspect.getsource(getattr(BasePeacockKingdom, name))
            self.assertNotIn("super()." + name, src)

    def test_realm_raid_result_quick_exit_skips_settlement_then_super(self):
        from tasks.RealmRaid.script_task import ScriptTask
        src = inspect.getsource(ScriptTask._handle_result)
        self.assertIn("if config.quick_exit:", src)
        self.assertIn("return super()._handle_result(context, config)", src)

    def test_realm_raid_quick_exit_path_does_not_call_settlement(self):
        from tasks.RealmRaid.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.appear = Mock(return_value=False)
        task._settlement_click = Mock()
        task._settlement_burst_step = Mock()
        ctx = SimpleNamespace(reward_no_battle_ts=1, is_win=False)
        task._handle_result(ctx, SimpleNamespace(quick_exit=True))
        task._settlement_click.assert_not_called()
        task._settlement_burst_step.assert_not_called()

    def test_realm_raid_non_quick_exit_reaches_settlement_burst_session(self):
        # RealmRaid 非 quick_exit 路径 `super()._handle_result()` 落到公共
        # GeneralBattle，因此自然继承 Settlement Micro-Burst v1.2（segment budget=2~4、
        # 同一 anchor burst）——不再是旧的「固定两次、各自独立采样」。
        from tasks.RealmRaid.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.device = SimpleNamespace(click_record_clear=Mock(), click=Mock())
        task.screenshot = Mock()
        task.appear = Mock(side_effect=lambda r, **kw: r is task.I_WIN)
        task._next_settlement_click_interval = Mock(return_value=0.8)
        task._sample_interval = Mock(return_value=0.2)
        task._sample_settlement_point = Mock(return_value=(700, 500))
        task._classify_general_battle_page = Mock(return_value=gb.page_battle_result)  # 观察后仍是同一页
        ctx = _settlement_context(last_page=None)
        with patch.object(gb, "random_int", side_effect=[1, 2]):  # budget=2, burst_size=2
            task._handle_result(ctx, SimpleNamespace(quick_exit=False))
        self.assertEqual(
            [c.kwargs for c in task.device.click.call_args_list],
            [{"x": 700, "y": 500, "control_name": "random_default"}] * 2,
        )
        self.assertTrue(ctx.settlement_session_active)

    def test_activityshikigami_result_calls_super(self):
        from tasks.ActivityShikigami.base_act import BaseAct
        src = inspect.getsource(BaseAct._handle_result)
        self.assertIn("super()._handle_result(context, config)", src)

    def test_herotest_result_super_on_non_skill_add(self):
        from tasks.HeroTest.script_task import ScriptTask
        src = inspect.getsource(ScriptTask._handle_result)
        self.assertIn("return super()._handle_result(context, config)", src)

    def test_orochi_result_reward_call_super(self):
        from tasks.Orochi.script_task import ScriptTask
        self.assertIn("super()._handle_result(context, config)",
                      inspect.getsource(ScriptTask._handle_result))
        self.assertIn("super()._handle_reward(context, config)",
                      inspect.getsource(ScriptTask._handle_reward))

    def test_eternitysea_evozone_reward_call_super(self):
        from tasks.EternitySea.script_task import ScriptTask as ES
        from tasks.EvoZone.script_task import ScriptTask as EZ
        self.assertIn("super()._handle_reward(context, config)", inspect.getsource(ES._handle_reward))
        self.assertIn("super()._handle_reward(context, config)", inspect.getsource(EZ._handle_reward))

    def test_ryoutoppa_exploration_falldownsun_do_not_override_result_reward(self):
        import importlib
        for mod in ("tasks.RyouToppa.script_task", "tasks.Exploration.script_task",
                    "tasks.FallenSun.script_task", "tasks.Dokan.script_task"):
            cls = importlib.import_module(mod).ScriptTask
            self.assertNotIn("_handle_result", cls.__dict__, mod)
            self.assertNotIn("_handle_reward", cls.__dict__, mod)


if __name__ == "__main__":
    unittest.main()
