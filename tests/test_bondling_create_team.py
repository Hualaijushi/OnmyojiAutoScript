# This Python file uses the following encoding: utf-8
"""契灵队长「点击创建队伍之后」的页面确认：房间已出现就立刻交接邀请，不再空等私人设置的 15 秒。

背景（10-27 oas2 日志）：13:16:53 点击 BALL_CREATE_TEAM → 13:16:53 `Ensure private` → 13:17:08 `Ensure private timeout`
→ 13:17:08 `Ensure enter invite page`。旧代码点击后用点击前的旧截图判断「不在房间」，直接进 `ensure_private()`，
而后者只认私人 / 公开设置标志、没有「已经在房间」的退出分支。10-22 ~ 10-27 的实例日志里 37 次点击创建，36 次紧接着
`Ensure private timeout`、没有一次点到过私人设置标志（点击创建直接进房间）。

这里驱动真实的 `ScriptTask.create_bond_team` / `_observe_after_create` / `run_leader` 和真实的 `GeneralRoom.ensure_private`，
只替换截图 / 识别（`appear`、`appear_then_click`）/ 时钟；用虚拟世界决定每一帧能看到哪些标志。
离线只能验证流程与时间，真实截图识别、页面加载耗时和私人状态仍待真机。
"""

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module.exception import GamePageUnknownError, GameStuckError, TaskEnd
from tasks.BondlingFairyland import script_task as bt
from tasks.BondlingFairyland.script_task import ScriptTask
from tasks.Component.GeneralRoom import general_room as gr
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tests.test_switch_soul_numeric_v1 import _VTimer

ROOT = Path(__file__).resolve().parents[1]
SHOT = 0.3
MAX_SHOTS = 400


class World:
    """虚拟页面：每帧可见的标志集合由阶段决定；点击「创建队伍」之后按配置进入目标阶段。

    after_click：
      'room'     点击后（经过 delay 帧过渡）直接进房间（实测情形）
      'setting'  点击后出现创建设置页（私人设置标志），room_after 帧之后才进房间（None = 不进）
      'stay'     点击没有效果，仍是创建页
      'unknown'  点击后一直是看不到任何已知标志的页面
    """

    def __init__(self, after_click='room', delay=0, toggle_private=True, already_private=False, room_after=None,
                 throttle_first=0, stuck_after=None):
        self.after_click = after_click
        self.delay = delay
        self.toggle_private = toggle_private
        self.already_private = already_private
        self.room_after = room_after
        self.throttle_first = throttle_first        # 前 N 次创建点击被限流（没有发出）
        self.stuck_after = stuck_after              # 截图数达到后抛 GameStuckError（模拟设备层卡死检测）
        self.now = 0.0
        self.shots = 0
        self.phase = 'create'
        self.countdown = 0
        self.setting_frames = 0
        self.timers = {}                            # 与真实 `BaseTask.interval_timer` 同样的门控：按目标名保存 Timer，limit 不同就换一个新的（未启动 = 已到）
        self.events = []
        self.create_clicks = []                     # 发出的创建点击的虚拟时刻
        self.private_private = False
        self.looks = 0

    # ---- 页面 ----
    def visible(self):
        if self.phase == 'create':
            return {'create'}
        if self.phase == 'transition':
            return set()
        if self.phase == 'room':
            return {'room'}
        if self.phase == 'setting':
            return {'private_on' if self.private_private else 'private_off'}
        if self.phase == 'unknown':
            return set()
        return set()

    def screenshot(self):
        self.shots += 1
        self.now += SHOT
        if self.stuck_after is not None and self.shots >= self.stuck_after:
            raise GameStuckError('设备层卡死检测')
        if self.shots > MAX_SHOTS:
            raise AssertionError('截图次数失控：出现了无界循环')
        if self.phase == 'transition':
            self.countdown -= 1
            if self.countdown <= 0:
                self.phase = self.target
        if self.phase == 'setting' and self.room_after is not None:
            self.setting_frames += 1
            if self.setting_frames > self.room_after:
                self.phase = 'room'
        self.frame = self.visible()
        self.events.append(('screenshot', self.shots, tuple(sorted(self.frame))))

    # ---- 识别 / 点击替身（与真实 `BaseTask.appear` / `appear_then_click` 同样按 interval 门控）----
    KEYS = {'create': 'I_CREATE_TEAM', 'room': 'I_GI_IN_ROOM', 'private_on': ('I_ENSURE_PRIVATE', 'I_ENSURE_PRIVATE_2'),
            'private_off': ('I_ENSURE_PRIVATE_FALSE', 'I_ENSURE_PRIVATE_FALSE_2')}

    def seen(self, target):
        self.looks += 1
        if self.looks > 5000:                       # 不截图只识别的空转也要自动失败（否则变异会挂住）
            raise AssertionError('识别次数失控：出现了不截图的无界循环')
        for token in self.frame:
            names = self.KEYS[token]
            names = (names,) if isinstance(names, str) else names
            if any(target.name == getattr(ScriptTask, n).name for n in names):
                return True
        return False

    def gated(self, target, interval):
        if not interval:
            return True
        timer = self.timers.get(target.name)
        if timer is None or timer.limit != interval:
            timer = self.timers[target.name] = _VTimer(interval)
        return timer.reached()

    def appear(self, target, interval=None, threshold=None):
        if not self.gated(target, interval) or not self.seen(target):
            return False
        if interval:
            self.timers[target.name].reset()
        return True

    def appear_then_click(self, target, action=None, interval=None, threshold=None, **kwargs):
        if not self.appear(target, interval=interval, threshold=threshold):
            return False
        if target.name == ScriptTask.I_CREATE_TEAM.name:
            if self.throttle_first > 0:
                self.throttle_first -= 1
                self.events.append(('create_throttled', self.shots))
                return False
            self.create_clicks.append(self.now)
            self.events.append(('create_click', self.shots))
            self.on_create_click()
        elif target.name in (ScriptTask.I_ENSURE_PRIVATE_FALSE.name, ScriptTask.I_ENSURE_PRIVATE_FALSE_2.name):
            self.events.append(('private_click', self.shots))
            if self.toggle_private:
                self.private_private = True
        else:
            self.events.append(('click', target.name))
        return True

    def on_create_click(self):
        if self.after_click == 'stay':
            return
        self.target = {'room': 'room', 'setting': 'setting', 'unknown': 'unknown'}[self.after_click]
        if self.after_click == 'setting':
            self.private_private = self.already_private
        self.phase = 'transition'
        self.countdown = max(1, self.delay + 1)


class Base(TestCase):
    def build(self, world):
        self.world = world
        _VTimer.clock = lambda: world.now
        task = ScriptTask.__new__(ScriptTask)
        task.device = SimpleNamespace(image=None)
        task.screenshot = world.screenshot
        task.appear = world.appear
        task.appear_then_click = world.appear_then_click
        task.check_and_invite = Mock(return_value=False)
        task.ensure_private = Mock(wraps=task.ensure_private)          # 真实 `GeneralRoom.ensure_private`，只记录调用
        return task

    def sleep(self, seconds):
        self.world.now += seconds

    def drive(self, fn):
        with patch.object(gr, 'Timer', _VTimer), patch.object(bt, 'Timer', _VTimer), \
                patch.object(bt, 'sleep', side_effect=self.sleep), patch.object(bt, 'logger') as logger, \
                patch.object(gr, 'logger'):
            self.logger = logger
            return fn()

    def infos(self):
        return [str(c.args[0]) for c in self.logger.info.call_args_list if c.args]

    def create(self, task):
        return self.drive(task.create_bond_team)


class RoomRightAfterClickTest(Base):
    def test_the_room_appearing_right_after_the_click_is_handed_over_without_the_15_second_wait(self):
        world = World(after_click='room')
        task = self.build(world)
        self.assertTrue(self.create(task))
        self.assertEqual(len(world.create_clicks), 1)
        self.assertLess(world.now, 5.0)                                     # 旧写法这里要空等 15 秒
        task.ensure_private.assert_not_called()                             # 房间已出现：不进私人设置等待

    def test_the_old_logic_would_have_burned_the_full_15_seconds_on_the_same_world(self):
        # 特征化旧实现（点击后用点击前的旧截图判断，再无条件 `ensure_private()`）：证明这个虚拟世界能暴露原问题
        world = World(after_click='room')
        task = self.build(world)

        def legacy():
            while 1:
                task.screenshot()
                if task.appear(task.I_GI_IN_ROOM):
                    return True
                if task.appear(task.I_CREATE_TEAM, interval=1):
                    task.appear_then_click(task.I_CREATE_TEAM, interval=2)
                    if not task.appear(task.I_GI_IN_ROOM):             # 用的是点击前的旧截图
                        GeneralRoom.ensure_private(task)
                    continue
        self.drive(legacy)
        self.assertGreaterEqual(world.now, 15.0)

    def test_the_decision_after_the_click_uses_a_fresh_screenshot_not_the_one_from_before_the_click(self):
        world = World(after_click='room')
        task = self.build(world)
        self.create(task)
        click = [e for e in world.events if e[0] == 'create_click'][0][1]
        seen_room = [e[1] for e in world.events if e[0] == 'screenshot' and e[2] == ('room',)][0]
        self.assertGreater(seen_room, click)                                # 房间是在点击之后的新截图里看到的
        self.assertLessEqual(world.shots, seen_room + 1)                    # 看到房间之后只多一次循环顶的确认截图，没有空转

    def test_the_room_appearing_later_during_the_transition_is_waited_for_without_a_second_create_click(self):
        world = World(after_click='room', delay=5)                          # 过渡 5 帧（约 1.5 秒）才进房间
        task = self.build(world)
        self.assertTrue(self.create(task))
        self.assertEqual(len(world.create_clicks), 1)
        self.assertLess(world.now, 4.0)
        task.ensure_private.assert_not_called()

    def test_room_entry_is_logged_as_private_not_verified(self):
        world = World(after_click='room')
        task = self.build(world)
        self.create(task)
        self.assertTrue(any('NOT verified' in t for t in self.infos()))
        self.assertFalse(any('private setting verified' in t for t in self.infos()))      # 不假装验证过私人

    def test_a_transition_slower_than_the_window_does_not_cause_a_second_create_click(self):
        world = World(after_click='room', delay=30)                         # 过渡约 9 秒：超过 8 秒观察窗口，期间看不到创建按钮
        task = self.build(world)
        self.assertTrue(self.drive(task.create_bond_team))
        self.assertEqual(len(world.create_clicks), 1)                       # 窗口结束后也不会在过渡页上再点创建
        self.assertTrue(any('neither room nor setting page' in str(c.args[0]) for c in self.logger.warning.call_args_list))
        self.assertGreater(world.now, 8.0)


class SettingPageTest(Base):
    def test_a_create_setting_page_is_still_handled_and_private_is_verified(self):
        world = World(after_click='setting', toggle_private=True, room_after=3)
        task = self.build(world)
        self.assertTrue(self.create(task))
        task.ensure_private.assert_called_once()
        self.assertEqual(task.ensure_private.call_args.kwargs['exit_when'].name, ScriptTask.I_GI_IN_ROOM.name)
        self.assertTrue(any(e[0] == 'private_click' for e in world.events))   # 私人开关被真实点击切换（原功能没被跳过）
        self.assertTrue(any('private setting verified' in t for t in self.infos()))

    def test_an_already_private_setting_page_needs_no_toggle_click(self):
        world = World(after_click='setting', already_private=True, room_after=3)
        task = self.build(world)
        self.assertTrue(self.create(task))
        self.assertFalse(any(e[0] == 'private_click' for e in world.events))
        self.assertTrue(any('private setting verified' in t for t in self.infos()))

    def test_the_room_appearing_while_ensuring_private_ends_the_wait_without_claiming_private(self):
        world = World(after_click='setting', toggle_private=False, room_after=2)        # 设置页只出现两帧就进了房间
        task = self.build(world)
        self.assertTrue(self.create(task))
        self.assertLess(world.now, 6.0)                                     # 不会等满 15 秒
        self.assertFalse(any('private setting verified' in t for t in self.infos()))
        warned = [str(c.args[0]) for c in self.logger.warning.call_args_list if c.args]
        self.assertTrue(any('NOT verified' in t for t in warned))


class FailureTest(Base):
    def test_a_private_setting_that_cannot_be_confirmed_fails_explicitly_and_never_reports_success(self):
        world = World(after_click='setting', toggle_private=False, room_after=None)     # 一直停在设置页，点了也切不过去
        task = self.build(world)
        with self.assertRaises(GamePageUnknownError) as ctx:
            self.create(task)
        self.assertIn('private setting was not confirmed', str(ctx.exception))
        self.assertGreaterEqual(world.now, 15.0)                            # 正常等满 `ensure_private` 的预算（真实设备慢时不误判）

    def test_a_create_click_that_has_no_effect_is_retried_a_bounded_number_of_times_then_fails(self):
        world = World(after_click='stay')
        task = self.build(world)
        with self.assertRaises(GamePageUnknownError) as ctx:
            self.create(task)
        self.assertIn('no room appeared', str(ctx.exception))
        self.assertEqual(len(world.create_clicks), ScriptTask.CREATE_MAX_ATTEMPTS)
        gaps = [b - a for a, b in zip(world.create_clicks, world.create_clicks[1:])]
        self.assertTrue(all(g >= 8.0 for g in gaps), gaps)                  # 每次点击之间留足观察窗口
        self.assertEqual((ScriptTask.CREATE_OBSERVE_TIMEOUT, ScriptTask.CREATE_MAX_ATTEMPTS), (8.0, 3))

    def test_a_throttled_create_click_is_not_treated_as_clicked(self):
        world = World(after_click='room', throttle_first=2)
        task = self.build(world)
        spy = Mock(wraps=task._observe_after_create)
        task._observe_after_create = spy
        self.assertTrue(self.create(task))
        self.assertEqual([e[0] for e in world.events if e[0].startswith('create_')], ['create_throttled', 'create_throttled', 'create_click'])
        spy.assert_called_once()                                            # 只有真正点出去之后才进入观察
        self.assertEqual(len(world.create_clicks), 1)

    def test_an_unknown_page_after_the_click_is_not_mistaken_for_success_and_device_errors_propagate_unchanged(self):
        world = World(after_click='unknown', stuck_after=120)
        task = self.build(world)
        with self.assertRaises(GameStuckError):                             # 设备层的卡死检测原样向上传播，没有被包装
            self.create(task)
        self.assertEqual(len(world.create_clicks), 1)

    def test_device_errors_during_the_observation_keep_their_type(self):
        world = World(after_click='room', delay=4, stuck_after=3)
        task = self.build(world)
        with self.assertRaises(GameStuckError):
            self.create(task)


class RunLeaderChainTest(Base):
    """真实 `run_leader`：创建 → 房间已出现 → 立刻交给原有的邀请流程（邀请本身不在本轮范围，替身为失败以便退出循环）。"""

    def build_leader(self, world):
        task = self.build(world)
        task.current_count = 0
        task.limit_count = 5
        task.start_time = bt.datetime.now()
        task.limit_time = bt.timedelta(hours=1)
        invite_config = object()
        task.config = SimpleNamespace(bondling_fairyland=SimpleNamespace(
            invite_config=invite_config, battle_config=object(), bondling_config=SimpleNamespace(user_status=None)))
        task.invite_config = invite_config
        task.run_invite = Mock(return_value=False)
        task.exit_room = Mock(return_value=True)
        task.exit_team = Mock(return_value=False)
        task.goto_page = Mock()
        task.set_next_run = Mock()
        return task

    def test_the_real_leader_loop_hands_the_room_to_the_invite_flow_without_the_15_second_wait(self):
        world = World(after_click='room')
        task = self.build_leader(world)
        with self.assertRaises(TaskEnd):
            self.drive(task.run_leader)
        task.run_invite.assert_called_once()
        self.assertIs(task.run_invite.call_args.kwargs['config'], task.invite_config)
        self.assertTrue(task.run_invite.call_args.kwargs['is_first'])
        self.assertLess(world.now, 6.0)                                     # 房间一出现就交接，没有消耗私人设置的 15 秒
        task.ensure_private.assert_not_called()

    def test_a_failed_create_never_reaches_the_invite_flow(self):
        world = World(after_click='stay')
        task = self.build_leader(world)
        with self.assertRaises(GamePageUnknownError):
            self.drive(task.run_leader)
        task.run_invite.assert_not_called()


class PublicCallersTest(Base):
    """公共 `ensure_private` 默认行为不变；只有契灵传了 `exit_when`。"""

    def test_default_ensure_private_behaves_as_before(self):
        # 看到私人标志 → True；什么都看不到 → 等满 15 秒返回 False（默认不因「房间」之类的标志退出）
        world = World(after_click='setting', already_private=True)
        world.phase, world.private_private = 'setting', True
        task = self.build(world)
        task.ensure_private = GeneralRoom.ensure_private.__get__(task)
        self.assertTrue(self.drive(task.ensure_private))
        world = World()
        world.phase = 'room'                                                # 已在房间：默认调用不识别房间，只会等到超时
        task = self.build(world)
        task.ensure_private = GeneralRoom.ensure_private.__get__(task)
        self.assertFalse(self.drive(task.ensure_private))
        self.assertGreaterEqual(world.now, 15.0)

    def test_the_new_parameter_is_optional_with_a_none_default(self):
        import inspect
        parameter = inspect.signature(GeneralRoom.ensure_private).parameters['exit_when']
        self.assertIsNone(parameter.default)

    def test_only_the_bondling_leader_path_passes_the_exit_condition(self):
        users = []
        for path in (ROOT / 'tasks').rglob('*.py'):
            if path.name == 'assets.py':
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            if path.name != 'general_room.py' and re.search(r'ensure_private\([^)]*exit_when', text):
                users.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(users, ['tasks/BondlingFairyland/script_task.py'])

    def test_run_leader_calls_the_extracted_method_and_the_old_nested_closure_is_gone(self):
        tree = ast.parse((ROOT / 'tasks' / 'BondlingFairyland' / 'script_task.py').read_text(encoding='utf-8'))
        leader = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'run_leader'][0]
        self.assertIn('self.create_bond_team()', ast.unparse(leader))
        self.assertFalse([n for n in ast.walk(leader) if isinstance(n, ast.FunctionDef) and n is not leader])
