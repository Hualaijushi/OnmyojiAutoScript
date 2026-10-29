# This Python file uses the following encoding: utf-8
"""契灵组队：游戏内「锁定队伍」状态、通用战斗的 `lock_team_enable` 配置标志、默认邀请三件事的衔接。

已确认的事实（源码）：
- 游戏内锁队：队长在 `run_catch` / `run_search` 开头调用 `lock_team()`（看到锁定图标才返回）；队员原来不经过任何锁队检查；
- `BattleConfig` 隐藏了 `lock_team_enable`，继承默认 False；组队的 `run_leader` / `run_member` 直接把它传给 `run_general_battle`；
- `GeneralBattle._prepare_click_ready`：`lock_team_enable=True` 时进准备页先等一段延迟（默认 3 秒）才允许点准备，False 时立即判断；
- 通用邀请 `check_then_accept` 不设置锁队标志，默认邀请也不是锁队证据。
实际误点发生时的画面没有捕获，这里不宣称证明了误标记的唯一原因；离线只验证配置衔接和准备等待的逻辑，自动准备后是否还误点待真机。

这里驱动真实的 `lock_team` / `confirm_team_locked` / `team_battle_config` / `run_leader` / `run_member`，并把生成出来的配置交给真实的
`GeneralBattle._build_context` / `_prepare_click_ready` / `_handle_prepare`（虚拟时钟），只替换截图 / 识别 / 设备。
"""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import TaskEnd
from tasks.BondlingFairyland import script_task as bt
from tasks.BondlingFairyland.config import BattleConfig, UserStatus
from tasks.BondlingFairyland.script_task import ScriptTask
from tasks.Component.GeneralBattle import general_battle as gb
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction
from tasks.GameUi.page import page_battle, page_battle_prepare

ROOT = Path(__file__).resolve().parents[1]
SHOT = 0.3


class VTimer:
    """虚拟计时器：读世界的虚拟时钟；接口与 `module.base.timer.Timer` 一致（含 started / clear）。"""
    clock = None

    def __init__(self, limit, count=0):
        self.limit = limit
        self.count = count
        self._t0 = None

    def start(self):
        if self._t0 is None:
            self._t0 = VTimer.clock()
        return self

    def started(self):
        return self._t0 is not None

    def clear(self):
        self._t0 = None
        return self

    def reset(self):
        self._t0 = VTimer.clock()
        return self

    def reached(self):
        return self._t0 is None or VTimer.clock() - self._t0 > self.limit

    def current(self):
        return 0.0 if self._t0 is None else VTimer.clock() - self._t0


class World:
    """虚拟页面：锁定 / 未锁定图标、房间、主界面是否可见；图标点击会把「未锁定」切成「锁定」。"""

    def __init__(self, lock='locked', in_main=False):
        self.lock = lock                    # 'locked' / 'unlocked' / 'none'（这个页面没有锁队图标）
        self.in_main = in_main
        self.now = 0.0
        self.shots = 0
        self.clicks = []
        self.room = False
        self.lock_visible_from = 0.0         # 页面刚进入时图标还没渲染出来

    def screenshot(self):
        self.shots += 1
        self.now += SHOT
        if self.shots > 600:
            raise AssertionError('截图次数失控：出现了无界循环')

    def seen(self, target):
        name = target.name
        locked = (ScriptTask.I_BALL_LOCK.name, ScriptTask.I_BF_LOCK.name)
        unlocked = (ScriptTask.I_BALL_UNLOCK.name, ScriptTask.I_BF_UNLOCK.name)
        if name in locked:
            return self.lock == 'locked' and self.now >= self.lock_visible_from
        if name in unlocked:
            return self.lock == 'unlocked'
        if name == ScriptTask.I_GI_IN_ROOM.name:
            return self.room
        if name == ScriptTask.I_CHECK_MAIN.name:
            return self.in_main
        return False

    def appear(self, target, interval=None, threshold=None):
        return self.seen(target)

    def appear_then_click(self, target, action=None, interval=None, threshold=None, **kwargs):
        if not self.seen(target):
            return False
        self.clicks.append(target.name)
        if target.name in (ScriptTask.I_BALL_UNLOCK.name, ScriptTask.I_BF_UNLOCK.name):
            self.lock = 'locked'
        return True


def make_config(**overrides):
    battle = BattleConfig(**overrides)
    return SimpleNamespace(bondling_fairyland=SimpleNamespace(
        battle_config=battle,
        invite_config=SimpleNamespace(wait_time=SimpleNamespace(minute=10)),
        bondling_config=SimpleNamespace(user_status=UserStatus.MEMBER)))


class Base(TestCase):
    def build(self, world, **battle_overrides):
        self.world = world
        VTimer.clock = lambda: world.now
        task = ScriptTask.__new__(ScriptTask)
        task.config = make_config(**battle_overrides)
        task.device = SimpleNamespace(image=None, stuck_record_add=Mock())
        task.screenshot = world.screenshot
        task.appear = world.appear
        task.appear_then_click = world.appear_then_click
        task.check_and_invite = Mock(return_value=False)
        task.current_count = 0
        task.limit_count = 2
        task.start_time = bt.datetime.now()
        task.limit_time = bt.timedelta(hours=1)
        task.battles = []
        task.run_general_battle = Mock(side_effect=lambda config, **kw: self.battle(task, config))
        task.goto_page = Mock()
        task.set_next_run = Mock()
        task.exit_room = Mock(return_value=True)
        task.exit_team = Mock(return_value=False)
        return task

    def battle(self, task, config):
        task.battles.append(config)
        task.current_count += 1
        return self.battle_results.pop(0) if getattr(self, 'battle_results', None) else True

    def drive(self, fn):
        with patch.object(bt, 'Timer', VTimer), patch.object(bt, 'sleep', side_effect=self.sleep), patch.object(bt, 'logger') as logger:
            self.logger = logger
            return fn()

    def sleep(self, seconds):
        self.world.now += seconds

    def lock_flags(self, task):
        return [c.lock_team_enable for c in task.battles]


class TeamBattleConfigTest(Base):
    def test_the_copy_keeps_every_other_field_and_never_touches_the_shared_config(self):
        world = World()
        task = self.build(world, battle_timeout=77, green_enable=True, random_click_swipt_enable=True)
        original = task.config.bondling_fairyland.battle_config
        before = original.model_dump()
        for locked in (False, True):
            task.team_locked = locked
            copy = task.team_battle_config()
            self.assertIsNot(copy, original)
            self.assertIsInstance(copy, BattleConfig)
            self.assertEqual(copy.lock_team_enable, locked)
            self.assertEqual({k: v for k, v in copy.model_dump().items() if k != 'lock_team_enable'},
                             {k: v for k, v in before.items() if k != 'lock_team_enable'})
        self.assertEqual(original.model_dump(), before)                      # 共享配置对象没有被改（也不会写回 JSON）
        self.assertFalse(original.lock_team_enable)
        self.assertEqual((copy.battle_timeout, copy.green_enable, copy.random_click_swipt_enable), (77, True, True))

    def test_the_flag_defaults_to_not_locked(self):
        self.assertFalse(ScriptTask.team_locked)
        self.assertFalse(BattleConfig().lock_team_enable)                    # 隐藏字段的默认值（问题的来源）


class LeaderEntryPointsTest(Base):
    def run_leader_chain(self, lock_first=True, battle_results=(False, True)):
        """lock_team()（run_catch 开头做的事）→ 真实 run_leader：第一次战斗输了 → 走「邀请 + 后续战斗」分支 → 次数到了收尾。"""
        world = World(lock='unlocked' if lock_first else 'none')
        task = self.build(world)
        self.battle_results = list(battle_results)
        world.room = True
        task.run_invite = Mock(return_value=True)
        task.invite_friends = Mock()
        if lock_first:
            self.drive(task.lock_team)                                       # 真实：点「未锁定」→ 看到锁定图标才返回
        with self.assertRaises(TaskEnd):
            self.drive(task.run_leader)
        return task, world

    def test_every_leader_battle_entry_gets_a_locked_copy_after_lock_team_confirmed_it(self):
        task, world = self.run_leader_chain()
        self.assertTrue(task.team_locked)
        self.assertEqual(len(task.battles), 2)                               # 首次邀请 + 之后的后续战斗两个入口
        self.assertEqual(self.lock_flags(task), [True, True])
        self.assertEqual(task.run_invite.call_count, 2)
        self.assertTrue(task.run_invite.call_args_list[0].kwargs['is_first'])
        self.assertNotIn('is_first', task.run_invite.call_args_list[1].kwargs)   # 第二次走的是 not is_first 分支
        original = task.config.bondling_fairyland.battle_config
        self.assertFalse(original.lock_team_enable)
        self.assertTrue(all(c is not original for c in task.battles))

    def test_without_a_confirmed_lock_the_leader_flag_stays_false(self):
        task, world = self.run_leader_chain(lock_first=False)
        self.assertFalse(task.team_locked)
        self.assertEqual(self.lock_flags(task), [False, False])              # 标志来自确认的状态，不是写死 True

    def test_lock_team_only_returns_after_the_lock_icon_is_seen(self):
        world = World(lock='unlocked')
        task = self.build(world)
        self.assertTrue(self.drive(task.lock_team))
        self.assertTrue(any(n in world.clicks for n in (ScriptTask.I_BALL_UNLOCK.name, ScriptTask.I_BF_UNLOCK.name)))
        self.assertTrue(task.team_locked)
        self.assertEqual(world.lock, 'locked')


class MemberEntryPointsTest(Base):
    def run_member_chain(self, lock, accept_first=False, locked_before=False):
        world = World(lock=lock, in_main=True)
        task = self.build(world)
        task.team_locked = locked_before
        task.confirm_team_locked = Mock(wraps=task.confirm_team_locked)
        accepted = [accept_first]

        def accept():
            if accepted[0]:
                accepted[0] = False
                return True                                                  # 默认邀请被接受：这一轮只接受，不进战斗
            return False
        task.check_then_accept = Mock(side_effect=accept)
        rooms = [True, False, False]
        task.is_in_room = Mock(side_effect=lambda *a, **k: rooms.pop(0) if rooms else False)
        task.wait_battle = Mock(return_value=True)
        task.is_in_battle = Mock(return_value=True)
        with self.assertRaises(TaskEnd):
            self.drive(task.run_member)
        return task, world

    def test_every_member_battle_entry_gets_a_locked_copy_when_the_lock_icon_is_seen(self):
        task, world = self.run_member_chain('locked')
        self.assertTrue(task.team_locked)
        self.assertEqual(len(task.battles), 2)                               # 房间里等到开战 + 队长秒开（已在战斗中）两个入口
        self.assertEqual(self.lock_flags(task), [True, True])
        self.assertFalse(task.config.bondling_fairyland.battle_config.lock_team_enable)

    def test_an_unlocked_icon_or_no_icon_means_not_confirmed_and_the_game_state_is_not_changed(self):
        for lock in ('unlocked', 'none'):
            with self.subTest(lock=lock):
                task, world = self.run_member_chain(lock)
                self.assertFalse(task.team_locked)
                self.assertEqual(self.lock_flags(task), [False, False])
                self.assertEqual(world.clicks, [])                           # 队员侧只观察，不替用户点锁定

    def test_the_member_check_is_bounded_and_waits_for_a_late_icon(self):
        self.assertEqual(ScriptTask.LOCK_CONFIRM_TIMEOUT, 6.0)
        world = World(lock='none')
        task = self.build(world)
        self.assertFalse(self.drive(task.confirm_team_locked))
        self.assertGreaterEqual(world.now, 6.0)                              # 看不到任何图标：等满窗口才放弃
        self.assertLess(world.now, 8.0)
        world = World(lock='locked')
        world.lock_visible_from = 3.0                                        # 图标 3 秒后才渲染出来：窗口内仍能确认
        task = self.build(world)
        self.assertTrue(self.drive(task.confirm_team_locked))
        self.assertGreaterEqual(world.now, 3.0)

    def test_accepting_a_default_invite_is_not_treated_as_lock_evidence(self):
        task, world = self.run_member_chain('none', accept_first=True)
        self.assertTrue(task.check_then_accept.called)
        self.assertFalse(task.team_locked)
        self.assertEqual(self.lock_flags(task), [False, False])

    def test_the_leaders_lock_is_not_assumed_for_a_member_that_never_confirmed_its_own(self):
        # 队长侧 `team_locked` 是各自账号的实例状态：队员实例没经过锁队检查，就必须自己观察
        task, world = self.run_member_chain('none')
        task.confirm_team_locked.assert_called_once()
        self.assertFalse(task.team_locked)

    def test_a_player_that_locked_itself_earlier_does_not_need_to_observe_again(self):
        task, world = self.run_member_chain('none', locked_before=True)      # handoff：先当过队长，lock_team() 已看到锁定图标
        task.confirm_team_locked.assert_not_called()
        self.assertEqual(self.lock_flags(task), [True, True])


class PrepareWaitingTest(Base):
    """把契灵真正生成的配置交给通用战斗的准备页处理：已锁队先等，自动进战斗就不点；一直停在准备页，到点仍然点准备。"""

    def make_battle(self, config):
        world = self.world
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(global_game=SimpleNamespace(battle=SimpleNamespace(battle_timeout=420)))
        task._battle_shared_state = {}
        task._get_battle_behavior_scopes = Mock(return_value={})
        task._build_timed_battle_inspections = Mock(return_value={})
        task._run_battle_behavior_once = Mock()
        task.appear_then_click = Mock(side_effect=lambda target, **kw: self.prepare_click(target))
        self.prepare_clicks = []
        with patch.object(gb, 'Timer', VTimer):
            context = task._build_context(config, None, 'bondling')
        return task, context

    def prepare_click(self, target):
        if target.name == ScriptTask.I_PREPARE_HIGHLIGHT.name:
            self.prepare_clicks.append(round(self.world.now, 2))
            return True
        return False

    def run_prepare(self, config, seconds, battle_after=None):
        """在准备页停留 `seconds` 秒（每 0.3 秒一帧）；`battle_after` 秒之后自动进入战斗页。"""
        task, context = self.make_battle(config)
        start = self.world.now
        with patch.object(gb, 'Timer', VTimer):
            while self.world.now - start < seconds:
                self.world.now += SHOT
                if battle_after is not None and self.world.now - start >= battle_after:
                    task._sync_prepare_click_timer(context, page_battle)
                    break
                task._sync_prepare_click_timer(context, page_battle_prepare)
                self.assertEqual(task._handle_prepare(context, config), BattleAction.CONTINUE)
        return start

    def produced_config(self, locked):
        task = self.build(self.world)
        task.team_locked = locked
        return task.team_battle_config()

    def setUp(self):
        self.world = World()
        VTimer.clock = lambda: self.world.now

    def test_a_locked_team_waits_before_the_first_prepare_click_and_still_clicks_when_nothing_happens(self):
        config = self.produced_config(True)
        start = self.run_prepare(config, 6.0)
        self.assertTrue(self.prepare_clicks)
        self.assertGreaterEqual(self.prepare_clicks[0] - start, 3.0)         # 原有约 3 秒自动准备等待：期间不补点
        self.assertLess(self.prepare_clicks[0] - start, 4.0)                 # 到点（约 3 秒 + 一帧）仍然点准备（兜底保留）

    def test_a_locked_team_that_enters_the_battle_by_itself_never_clicks_prepare(self):
        config = self.produced_config(True)
        self.run_prepare(config, 6.0, battle_after=2.0)                      # 2 秒时游戏自动准备、进入战斗
        self.assertEqual(self.prepare_clicks, [])

    def test_an_unconfirmed_team_keeps_the_old_behaviour_of_clicking_prepare_immediately(self):
        config = self.produced_config(False)
        start = self.run_prepare(config, 1.5)
        self.assertTrue(self.prepare_clicks)
        self.assertLess(self.prepare_clicks[0] - start, 0.6)

    def test_other_tasks_prepare_behaviour_is_unchanged(self):
        # 通用默认配置 lock_team_enable=False：立即判断准备；True：沿用同一段等待——公共实现没有改
        self.assertFalse(GeneralBattleConfig().lock_team_enable)
        start = self.run_prepare(GeneralBattleConfig(), 1.5)
        self.assertLess(self.prepare_clicks[0] - start, 0.6)
        self.prepare_clicks.clear()
        start = self.run_prepare(GeneralBattleConfig(lock_team_enable=True), 6.0)
        self.assertGreaterEqual(self.prepare_clicks[0] - start, 3.0)


class ScopeTest(TestCase):
    def test_only_bondling_uses_the_team_battle_config_and_the_four_team_entry_points_all_do(self):
        users = []
        for path in (ROOT / 'tasks').rglob('*.py'):
            if re.search(r'\bteam_battle_config\b', path.read_text(encoding='utf-8', errors='ignore')):
                users.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(users, ['tasks/BondlingFairyland/script_task.py'])
        text = (ROOT / 'tasks' / 'BondlingFairyland' / 'script_task.py').read_text(encoding='utf-8')
        self.assertEqual(text.count('self.run_general_battle(self.team_battle_config())'), 4)       # 队长 2 + 队员 2
        self.assertNotIn('run_general_battle(self.config.bondling_fairyland.battle_config)', text)

    def test_common_invite_and_battle_code_do_not_set_the_flag(self):
        for rel in ('tasks/Component/GeneralInvite/general_invite.py', 'tasks/Component/GeneralBattle/general_battle.py'):
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertNotRegex(text, r'lock_team_enable\s*=\s*(True|False)\b')
