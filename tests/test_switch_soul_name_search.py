# This Python file uses the following encoding: utf-8
"""SwitchSoul 按名称找分组 / 找队伍：整条搜索链（回顶 → 找分组 → 点分组 → 回顶 → 找队伍 → 点队伍）的离线验证。

替身只放在外部边界，且遵守真实协议：
- OCR：真实 `RuleOcr.detect_and_ocr`（真实裁剪 / 分数过滤），只替换 OCR 模型，模型返回真实的 `BoxedResult`
  （`box` 为 4×2 点阵，坐标相对裁剪区域左上角）；
- 滑动：真实 `BaseTask.swipe` + 真实 `RuleSwipe.sample_endpoints()`，只替换最底层的 `swipe_trajectory`
  （记录起终点并按手指方向移动虚拟列表）；
- 稳定等待：真实 `wait_for_changed_and_stable` + 真实帧差，帧是按虚拟列表状态渲染的真实 ndarray；
- 分组选中标志：真实 `RuleImage.match_all_any`（只替换 RPC 客户端，客户端用 cv2 在渲染的帧上做真实模板匹配，返回真实的
  `[score, x, y, w, h]` 协议），模板是项目里数字模式用的 `ss_sou_check_group_*.png`，世界把同一张图贴在选中行上；
- 时钟：虚拟，每次截图推进固定时间；截图次数有失控保护，找不到目标时自动失败而不是挂住。
真实分组 / 队伍的识别率、真实滚动覆盖、最终预设效果只能真机验证。
"""

import copy
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.atom.swipe import RuleSwipe
from module.exception import GamePageUnknownError, GameStuckError, RequestHumanTakeover
from module.ocr.common import BoxedResult
from tasks.base_task import BaseTask
from tasks.Component.SwitchSoul import switch_soul as ss
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from tasks.Component.SwitchSoul.name_search import (
    SwitchSoulNameError, SwitchSoulPageError, exact_matches, is_complete, normalize_target, parse_lines, parse_matches)
from tasks.Component.SwitchSoul.switch_soul import GROUP_LIST, TEAM_LIST, SwitchSoul
from tests.test_switch_soul_numeric_v1 import _VTimer

# 列表几何（取自 ss/ocr.json：groupName 右侧列表、teamName 中央列表；一屏约 8 个分组 / 3.4 个队伍）
LISTS = {
    'group': dict(vp=(94, 627), x=(1090, 1240), pitch=66, roi=(1087, 91, 155, 566)),
    'team': dict(vp=(144, 619), x=(576, 846), pitch=140, roi=(573, 140, 277, 481)),
}
SHOT = 0.3
MARKER = cv2.imread(str(Path(SwitchSoulAssets.I_SOU_CHECK_GROUP_2.file)))        # 选中标志（金色竖条）：项目里的真实模板
# 点击的 control_name = 真实 OCR 资源的 name（生成资源时已大写）
GROUP_CTL = SwitchSoulAssets.O_SS_GROUP_NAME.name
TEAM_CTL = SwitchSoulAssets.O_SS_TEAM_NAME.name
MAX_SHOTS = 600


_TEXTURES = {}


def _texture(seed, shape):
    key = (seed, shape)
    if key not in _TEXTURES:                       # 渲染每帧都要用，缓存以免测试变慢
        _TEXTURES[key] = np.random.RandomState(seed % (2 ** 31)).randint(0, 255, shape, dtype=np.uint8)
    return _TEXTURES[key]


class World:
    """虚拟的「队伍预设」页面：右侧分组列表 + 中央队伍列表。"""

    def __init__(self, groups, teams, *, selected=0, group_offset=0, team_offset=0, gain=1.0, anim=0,
                 refresh_delay=2, shot=SHOT, duplicate_in_view=None, marker=True, click_ignored=False,
                 noise_on_click=False, refresh_never=False, extra_marker=None, max_shots=MAX_SHOTS):
        self.groups = list(groups)
        self.teams = {g: list(t) for g, t in teams.items()}
        self.selected = selected                    # 当前选中分组的下标
        self.shown = selected                       # 中央列表当前显示的是哪个分组的队伍
        self.off = {'group': group_offset, 'team': team_offset}
        self.pending = {}                           # kind -> (目标偏移, 剩余动画帧)
        self.gain = gain
        self.anim = anim
        self.refresh_delay = refresh_delay
        self.refresh_in = None                      # 点分组后，队伍列表在多少帧后才换成新分组的内容
        self.now = 0.0
        self.shot = shot
        self.shots = 0
        self.clicks = []                            # (control_name, x, y)
        self.swipes = []                            # (control_name, start, end)
        self.lost_swipes = 0                        # 前 N 次滑动没有生效
        self.ignore_swipes = False
        self.jitter = set()                         # 哪些列表区域每一帧都在变化（永远不稳定）：{'group'} / {'team'}
        self.empty_reads = {'group': 0, 'team': 0}  # 前 N 次 OCR 读到 0 行
        self.always_empty = set()
        self.empty_from = {}                        # kind -> n：第 n 次之后的 OCR 调用全部读到 0 行
        self.coast = None                           # 一次性：下一次截图时队伍列表偏移被 +N（惯性滑动）
        self.coast_forever = 0                      # 每次截图队伍列表偏移 +N（始终在动）
        self.garbage = {}                           # (kind, 下标) -> 被 OCR 读成的文字
        self.ocr_calls = {'group': 0, 'team': 0}
        self.duplicate_in_view = duplicate_in_view  # (kind, 文本)：该文本在同一屏再出现一次
        self.marker = marker                        # False：页面上不画选中标志（模板在当前页面识别不到的情形）
        self.click_ignored = click_ignored          # 点分组没有生效（选中状态不变）
        self.noise_on_click = noise_on_click        # 点分组之后右上角的无关区域持续变化（动画）
        self.noise = False
        self.refresh_never = refresh_never          # 选中了但中央队伍列表一直不刷新
        self.extra_marker = extra_marker            # 额外在这一行画第二个选中标志（歧义）
        self.max_shots = max_shots

    # ---- 列表内容 ----
    def names(self, kind):
        return self.groups if kind == 'group' else self.teams.get(self.groups[self.shown], names('默认队', 9))

    def max_off(self, kind):
        spec = LISTS[kind]
        return max(0, len(self.names(kind)) * spec['pitch'] - (spec['vp'][1] - spec['vp'][0]))

    def rows(self, kind):
        """可见行：[(下标, 文本框 (x, y, w, h)，已按列表可视区裁切)]。"""
        spec = LISTS[kind]
        top, bottom = spec['vp']
        result = []
        for i, name in enumerate(self.names(kind)):
            row_top = top + i * spec['pitch'] - self.off[kind]
            y0, y1 = row_top + spec['pitch'] // 2 - 12, row_top + spec['pitch'] // 2 + 12
            y0, y1 = max(y0, top), min(y1, bottom)
            if y1 - y0 < 4:
                continue
            result.append((i, (spec['x'][0] + 12, int(y0), 12 * max(2, len(name)), int(y1 - y0))))
        return result

    # ---- 截图 / 动画 ----
    def screenshot(self):
        self.shots += 1
        self.now += self.shot
        if self.shots > self.max_shots:
            raise AssertionError('截图次数失控：出现了无界循环')
        if self.coast:
            self.off['team'] = min(self.max_off('team'), self.off['team'] + self.coast)
            self.coast = None
        if self.coast_forever:
            self.off['team'] = (self.off['team'] + self.coast_forever) % max(1, self.max_off('team'))
        for kind, (target, left) in list(self.pending.items()):
            left -= 1
            self.off[kind] = target if left <= 0 else self.off[kind] + (target - self.off[kind]) / (left + 1)
            if left <= 0:
                del self.pending[kind]
            else:
                self.pending[kind] = (target, left)
        if self.refresh_in is not None:
            self.refresh_in -= 1
            if self.refresh_in <= 0:
                self.shown = self.selected
                self.off['team'] = 0
                self.refresh_in = None
        return self.render()

    def render(self):
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        for kind in ('group', 'team'):
            spec = LISTS[kind]
            top, bottom = spec['vp']
            names = self.names(kind)
            for i, name in enumerate(names):
                row_top = int(top + i * spec['pitch'] - self.off[kind])
                a, b = max(row_top, top), min(row_top + spec['pitch'], bottom)
                if b <= a:
                    continue
                seed = hash((kind, self.shown if kind == 'team' else -1, name, i)) & 0x7fffffff
                patch_ = _texture(seed, (spec['pitch'], spec['x'][1] - spec['x'][0], 3))
                if kind == 'group' and i == self.selected:
                    patch_ = 255 - patch_                          # 选中分组的高亮
                image[a:b, spec['x'][0]:spec['x'][1]] = patch_[a - row_top:b - row_top]
        if self.marker:
            for index in {self.selected, self.extra_marker} - {None}:
                spec = LISTS['group']
                row_top = int(spec['vp'][0] + index * spec['pitch'] - self.off['group'])
                y0 = row_top + (spec['pitch'] - MARKER.shape[0]) // 2
                if spec['vp'][0] <= y0 and y0 + MARKER.shape[0] <= spec['vp'][1]:        # 只画完整可见的
                    image[y0:y0 + MARKER.shape[0], 1087:1087 + MARKER.shape[1]] = MARKER
        if self.noise:
            image[10:60, 100:300] = _texture(self.shots + 3, (50, 200, 3))
        if 'team' in self.jitter:
            image[200:300, 600:700] = _texture(self.shots, (100, 100, 3))
        if 'group' in self.jitter:
            image[200:300, 1100:1200] = _texture(self.shots + 7, (100, 100, 3))
        return image

    # ---- OCR（模型替身：返回真实 BoxedResult）----
    def detect(self, crop):
        kind = 'group' if crop.shape[:2] == (LISTS['group']['roi'][3], LISTS['group']['roi'][2]) else 'team'
        self.ocr_calls[kind] += 1
        if kind in self.always_empty or self.ocr_calls[kind] > self.empty_from.get(kind, 10 ** 9):
            return []
        if self.empty_reads[kind] > 0:
            self.empty_reads[kind] -= 1
            return []
        ox, oy = LISTS[kind]['roi'][:2]
        results = []
        for i, (x, y, w, h) in self.rows(kind):
            text = self.garbage.get((kind, i), self.names(kind)[i])
            results.append(self._boxed(text, x - ox, y - oy, w, h))
            if kind == 'team':                                      # 队伍等级之类的噪声：精确匹配不应受影响
                results.append(self._boxed('40', x - ox + 150, y - oy, 24, h))
            if self.duplicate_in_view == (kind, text):
                results.append(self._boxed(text, x - ox, y - oy + 3, w, h))
        return results

    @staticmethod
    def _boxed(text, x, y, w, h):
        box = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32)
        return BoxedResult(box, None, text, 0.99)

    # ---- 设备 ----
    def on_swipe(self, start, end, *, control_name='SWIPE', fallback=True):
        self.swipes.append((control_name, tuple(start), tuple(end)))
        if self.lost_swipes > 0:
            self.lost_swipes -= 1
            return
        if self.ignore_swipes:
            return
        for kind, spec in LISTS.items():
            if spec['x'][0] <= start[0] <= spec['x'][1] and spec['vp'][0] <= start[1] <= spec['vp'][1]:
                target = min(max(0, self.off[kind] + (start[1] - end[1]) * self.gain), self.max_off(kind))
                if self.anim:
                    self.pending[kind] = (target, self.anim)
                else:
                    self.off[kind] = target
                return

    def on_click(self, x, y, control_name):
        self.clicks.append((control_name, x, y))
        if control_name == GROUP_CTL:
            spec = LISTS['group']
            index = int((y - spec['vp'][0] + self.off['group']) // spec['pitch'])
            if self.noise_on_click:
                self.noise = True
            if self.click_ignored:
                return
            if 0 <= index < len(self.groups):
                self.selected = index
                if not self.refresh_never:
                    self.refresh_in = self.refresh_delay + 1

    def row_at(self, kind, y):
        spec = LISTS[kind]
        return int((y - spec['vp'][0] + self.off[kind]) // spec['pitch'])


class FakeImageClient:
    """真实 `ImageClient.match_all_any` 的协议：返回 `{"matches": [[score, x, y, w, h], ...]}`；匹配用 cv2 真实做。"""

    def match_all_any(self, rule_data, image=None, frame_id=None, threshold=None, roi=None, nms_threshold=0.3):
        template = cv2.imread(rule_data['file'])
        x, y, w, h = roi
        result = np.nan_to_num(cv2.matchTemplate(image[y:y + h, x:x + w], template, cv2.TM_CCOEFF_NORMED))
        limit = rule_data['threshold'] if threshold is None else threshold
        th, tw = template.shape[:2]
        matches = []
        while True:
            _, best, _, loc = cv2.minMaxLoc(result)
            if best < limit:
                break
            matches.append([float(best), int(loc[0] + x), int(loc[1] + y), tw, th])
            cv2.rectangle(result, (max(0, loc[0] - tw // 2), max(0, loc[1] - th // 2)), (loc[0] + tw // 2, loc[1] + th // 2), -1, -1)
        return {'matches': matches}


def names(prefix, n):
    return [f'{prefix}{i + 1}' for i in range(n)]


class Base(TestCase):
    def build(self, world, *, swipe_ok=True):
        self.world = world
        _VTimer.clock = lambda: world.now
        task = SwitchSoul.__new__(SwitchSoul)
        task.interval_timer = {}
        task.device = SimpleNamespace(image=None, click=Mock(side_effect=world.on_click))
        task.screenshot = lambda: setattr(task.device, 'image', world.screenshot())
        task.O_SS_GROUP_NAME = self.rule(SwitchSoulAssets.O_SS_GROUP_NAME, world)
        task.O_SS_TEAM_NAME = self.rule(SwitchSoulAssets.O_SS_TEAM_NAME, world)
        for name in ('S_SS_NAME_GROUP_TO_TOP', 'S_SS_NAME_GROUP_NEXT', 'S_SS_NAME_TEAM_TO_TOP', 'S_SS_NAME_TEAM_NEXT'):
            setattr(task, name, getattr(SwitchSoulAssets, name))
        task.I_SOU_CLICK_PRESENT = SwitchSoulAssets.I_SOU_CLICK_PRESENT
        task.I_SOU_CHECK_GROUP_2 = SwitchSoulAssets.I_SOU_CHECK_GROUP_2
        task.I_SOU_SWITCH_SURE = SimpleNamespace(name='sure')
        task.swipe_trajectory = world.on_swipe
        real_swipe = types.MethodType(BaseTask.swipe, task)
        task.swipe = real_swipe if swipe_ok else (lambda swipe, interval=None: False)
        task.appear = lambda target, interval=None, threshold=None: False
        task.appear_then_click = lambda target, action=None, interval=None, **kwargs: False
        return task

    @staticmethod
    def rule(asset, world):
        rule = copy.copy(asset)
        rule.__dict__['model'] = SimpleNamespace(detect_and_ocr=lambda crop, **kwargs: world.detect(crop))
        return rule

    def run_flow(self, task, group, team):
        with patch.object(ss, 'Timer', _VTimer), patch.object(ss, 'monotonic', lambda: self.world.now), \
                patch.object(ss, 'sleep'), patch.object(ss, 'logger') as logger, \
                patch('module.atom.image.get_image_client', return_value=FakeImageClient()):
            self.logger = logger
            return task.switch_soul_by_name(group, team)

    def run_stage(self, fn):
        with patch.object(ss, 'Timer', _VTimer), patch.object(ss, 'monotonic', lambda: self.world.now), \
                patch.object(ss, 'logger') as logger, patch('module.atom.image.get_image_client', return_value=FakeImageClient()):
            self.logger = logger
            return fn()

    def success_logged(self):
        return any('Switch soul_one group' in str(c.args[0]) for c in self.logger.info.call_args_list if c.args)

    def click_of(self, name):
        return [c for c in self.world.clicks if c[0] == name]

    def assert_fails(self, task, group, team, *fragments, human=False):
        """`human=True`：确定需要人工的错误（`SwitchSoulNameError`，是 `RequestHumanTakeover`）；
        默认：临时识别 / 页面问题（`SwitchSoulPageError`，是 `GamePageUnknownError`，沿用重启恢复）。两类互不是对方的子类。"""
        kind, other = (SwitchSoulNameError, GamePageUnknownError) if human else (SwitchSoulPageError, RequestHumanTakeover)
        with self.assertRaises(kind) as ctx:
            self.run_flow(task, group, team)
        self.assertNotIsInstance(ctx.exception, other)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))
        self.assertFalse(self.success_logged())
        return ctx.exception


GROUPS8 = names('组', 8)
GROUPS12 = names('组', 12)
TEAMS = {g: names(f'{g}队', 9) for g in GROUPS12}


class FindAndClickTest(Base):
    def test_current_screen_group_and_team_are_found_and_clicked(self):
        world = World(GROUPS8, TEAMS, selected=0)
        task = self.build(world)
        self.run_flow(task, '组2', '组2队2')
        self.assertTrue(self.success_logged())
        group_click = self.click_of(GROUP_CTL)
        self.assertEqual(world.row_at('group', group_click[0][2]), 1)       # 点在「组2」那一行
        self.assertEqual(world.selected, 1)
        team_clicks = self.click_of(TEAM_CTL)
        self.assertEqual(len(team_clicks), 4)                               # 原有的 4 次队伍点击规则保留
        self.assertEqual({world.row_at('team', c[2]) for c in team_clicks}, {1})

    def test_eighth_group_and_a_team_that_only_appears_after_scrolling(self):
        world = World(GROUPS12, TEAMS, selected=0)
        task = self.build(world)
        self.run_flow(task, '组8', '组8队8')
        self.assertEqual(world.selected, 7)                                 # 第 8 组，超过数字模式的 7 组
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {7})
        self.assertTrue(self.success_logged())

    def test_starting_from_the_middle_of_both_lists_scrolls_back_to_the_top_first(self):
        world = World(GROUPS12, TEAMS, selected=0, group_offset=300, team_offset=500)
        task = self.build(world)
        self.run_flow(task, '组1', '组1队1')                                  # 目标在最顶上：不先回顶就找不到
        self.assertEqual(world.selected, 0)
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {0})

    def test_every_team_is_reachable_with_random_swipes_so_edge_teams_are_not_skipped(self):
        # 一个 14 队的列表，逐个队伍搜索；每次滑动的端点都是真实随机采样，增益 0.85（滑得比手指短）
        teams = {g: names('队', 14) for g in GROUPS8}
        for index in range(14):
            with self.subTest(team=index):
                world = World(GROUPS8, teams, gain=0.85)
                task = self.build(world)
                self.run_flow(task, '组3', f'队{index + 1}')
                self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {index})

    def test_a_list_that_settles_slowly_after_each_swipe_still_works(self):
        world = World(GROUPS12, TEAMS, anim=3)
        task = self.build(world)
        self.run_flow(task, '组10', '组10队6')
        self.assertEqual(world.selected, 9)
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {5})

    def test_click_geometry_group_in_its_line_team_in_the_button_column(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        self.run_flow(task, '组5', '组5队3')
        gx, gy = self.click_of(GROUP_CTL)[0][1:]
        row = [box for i, box in world.rows('group') if i == 4]
        # 点击时列表是静止的，所以现在的行位置就是点击时的位置
        x, y, w, h = row[0]
        self.assertTrue(x <= gx <= x + w + 1 and y <= gy <= y + h + 1, (gx, gy, row))
        column = SwitchSoulAssets.I_SOU_CLICK_PRESENT.roi_front
        for _, tx, ty in self.click_of(TEAM_CTL):
            self.assertTrue(column[0] <= tx < column[0] + column[2], tx)
            self.assertEqual(world.row_at('team', ty), 2)


class PostGroupClickTest(Base):
    def test_team_search_waits_for_the_central_list_to_refresh_and_uses_the_new_group(self):
        # 旧分组（组1）和新分组（组2）里都有「共同队」，但位置不同：不等刷新就找会点到旧列表里的行
        teams = {g: names(f'{g}队', 9) for g in GROUPS8}
        teams['组1'] = ['x1', 'x2', '共同队'] + names('a', 6)
        teams['组2'] = ['y1', 'y2', 'y3', 'y4', 'y5', '共同队'] + names('b', 3)
        world = World(GROUPS8, teams, selected=0, refresh_delay=2)
        task = self.build(world)
        self.run_flow(task, '组2', '共同队')
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {5})
        self.assertEqual(world.shown, 1)

    def test_a_group_that_is_already_selected_is_confirmed_by_the_marker_and_not_clicked(self):
        world = World(GROUPS8, TEAMS, selected=1)                           # 目标分组本来就是选中的
        task = self.build(world)
        self.run_flow(task, '组2', '组2队1')
        self.assertEqual(self.click_of(GROUP_CTL), [])                      # 有可靠证据（标志在目标行）：不点击，直接继续
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {0})
        self.assertTrue(any('already_selected=True' in str(c.args[0]) for c in self.logger.info.call_args_list))
        self.assertTrue(self.success_logged())

    def test_team_list_unreadable_after_the_group_click_is_an_error(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        world.always_empty.add('team')
        self.assert_fails(task, '组2', '组2队1', '组2', '队伍')
        self.assertEqual(self.click_of(TEAM_CTL), [])


class BoundedFailureTest(Base):
    def test_missing_group_exits_with_the_name_and_stage_and_never_clicks_anything(self):
        world = World(GROUPS12, TEAMS)
        task = self.build(world)
        self.assert_fails(task, '不存在的组', '组1队1', '不存在的组', '分组', '查找', '底部', human=True)
        self.assertEqual(world.clicks, [])
        self.assertLess(world.shots, 120)

    def test_missing_team_exits_with_the_name_and_stage_and_does_not_fall_back_to_another_team(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        self.assert_fails(task, '组2', '不存在的队', '不存在的队', '队伍', '查找', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])                 # 没有回退到任何别的队伍
        self.assertLess(world.shots, 250)

    def test_blank_names_are_rejected_before_touching_the_screen(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        for group, team in (('', 'x'), ('x', '   '), (None, 'x')):
            with self.subTest(group=group, team=team):
                with self.assertRaises(SwitchSoulNameError) as ctx:
                    self.run_flow(task, group, team)
                self.assertIsInstance(ctx.exception, RequestHumanTakeover)          # 空名称是配置问题：人工处理，不是重启
        self.assertEqual((world.shots, world.swipes), (0, []))

    def test_slow_screenshots_hit_the_stage_timeout_instead_of_running_for_ever(self):
        world = World(GROUPS12, TEAMS)
        task = self.build(world)
        task.NAME_STAGE_TIMEOUT = 2.0                                       # 虚拟时钟下 2 秒：第二轮循环就该超时
        self.assert_fails(task, '组12', '组12队1', '超过')
        self.assertLess(world.shots, 40)

    def test_page_cap_is_the_last_line_of_defence_when_the_boundary_is_never_confirmed(self):
        # 每次滑动都"有变化"（列表在无限滚动）：到 max_pages 屏还没有找到，也没有确认到底 → 明确报错
        world = World(names('组', 8), TEAMS)
        world.groups = names('组', 8)
        task = self.build(world)
        original = world.on_swipe

        def endless(start, end, **kwargs):
            original(start, end, **kwargs)
            if kwargs.get('control_name') == 'ss_name_group_next':          # 回顶正常；只有向后翻页永远得到新内容
                world.groups = [f'循环{world.shots}-{i}' for i in range(8)]
        task.swipe_trajectory = endless
        exc = self.assert_fails(task, '目标', '队', '目标', '分组', '保护上限')           # 临时问题：不是「名称不存在」
        self.assertNotIn('没有这个名字', str(exc))
        self.assertLess(world.shots, 400)


class OcrFailureTest(Base):
    def test_ocr_that_never_reads_anything_is_an_error_never_a_boundary(self):
        for kind in ('group', 'team'):
            with self.subTest(kind=kind):
                world = World(GROUPS8, TEAMS)
                world.always_empty.add(kind)
                task = self.build(world)
                self.assert_fails(task, '组2', '组2队1', '读不到')
                self.assertEqual(world.clicks if kind == 'group' else self.click_of(TEAM_CTL), [])

    def test_ocr_going_blind_exactly_at_the_top_or_during_the_search_is_reported_for_that_stage(self):
        # 回顶阶段：初次读取成功（第 1 次 OCR），到顶确认那一帧起读不到 → 不能当作到顶
        world = World(GROUPS8, TEAMS, group_offset=200)
        world.empty_from['group'] = 1
        task = self.build(world)
        self.assert_fails(task, '组2', '组2队1', '到顶时')
        self.assertEqual(world.clicks, [])
        # 查找阶段：回顶成功（2 次 OCR）后第一屏起读不到 → 不能判断目标在不在，也不能翻到底后说「没有这个名字」
        world = World(GROUPS8, TEAMS)
        world.empty_from['group'] = 2
        task = self.build(world)
        exc = self.assert_fails(task, '组2', '组2队1', '读不到')
        self.assertNotIn('没有这个名字', str(exc))
        self.assertEqual(world.clicks, [])

    def test_a_few_empty_reads_are_retried_and_do_not_end_the_search(self):
        world = World(GROUPS12, TEAMS)
        world.empty_reads = {'group': 2, 'team': 2}                         # 偶发漏识别：每个列表前 2 次读到 0 行（单次读取最多换帧重读 3 次）
        task = self.build(world)
        self.run_flow(task, '组9', '组9队5')
        self.assertEqual(world.selected, 8)
        self.assertTrue(self.success_logged())

    def test_empty_reads_at_the_bottom_do_not_claim_the_target_is_missing_or_present(self):
        world = World(GROUPS12, TEAMS)
        task = self.build(world)
        # 目标不存在 + 偶发空读（2 次）：仍然得到「没有这个名字」，而不是别的结论
        world.empty_reads['group'] = 2
        self.assert_fails(task, '不存在', '队', '不存在', human=True)

    def test_malformed_ocr_structure_fails_loudly(self):
        for bad in ([SimpleNamespace(ocr_text='x', box=None)], [SimpleNamespace(ocr_text=None, box=np.zeros((4, 2)))],
                    [SimpleNamespace(ocr_text='x', box=[[0, 0], [1, 1]])]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_lines(bad, (0, 0, 10, 10))


class ExactNameTest(Base):
    def test_similar_names_are_never_mixed_up(self):
        groups = ['魂土备用组', '魂土组'] + names('组', 6)
        teams = {g: ['魂土备用', '魂土', '魂土2', '魂 土'] + names('q', 5) for g in groups}
        world = World(groups, teams)
        task = self.build(world)
        self.run_flow(task, '魂土组', '魂土')
        self.assertEqual(world.selected, 1)
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {1})

    def test_target_that_is_only_a_substring_of_a_listed_name_is_not_found(self):
        teams = {g: ['魂土备用'] + names('q', 8) for g in GROUPS8}
        world = World(GROUPS8, teams)
        task = self.build(world)
        self.assert_fails(task, '组1', '魂土', '魂土', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_ocr_garbage_fragments_never_substitute_for_the_exact_name(self):
        # OCR 把「茨球」读成「茨」：旧实现的单字回退会命中，现在必须不命中
        teams = {g: ['茨球'] + names('q', 8) for g in GROUPS8}
        world = World(GROUPS8, teams)
        world.garbage[('team', 0)] = '茨'
        task = self.build(world)
        self.assert_fails(task, '组1', '茨球', '茨球', human=True)

    def test_surrounding_whitespace_is_trimmed_but_inner_spaces_and_symbols_are_kept(self):
        self.assertEqual(normalize_target('队伍', '  魂土 备用·2 '), '魂土 备用·2')
        lines = parse_lines([World._boxed(' 魂土 ', 0, 0, 40, 20), World._boxed('魂 土', 0, 30, 40, 20)], (0, 0, 100, 100))
        self.assertEqual([l.text for l in exact_matches(lines, '魂土')], ['魂土'])
        self.assertEqual([l.text for l in exact_matches(lines, '魂 土')], ['魂 土'])

    def test_two_identical_names_on_one_screen_are_reported_as_ambiguous_without_clicking(self):
        for kind in ('group', 'team'):
            with self.subTest(kind=kind):
                world = World(GROUPS8, TEAMS, duplicate_in_view=(kind, '组1' if kind == 'group' else '组1队1'))
                task = self.build(world)
                self.assert_fails(task, '组1', '组1队1', '完全同名', human=True)
                self.assertEqual(self.click_of(TEAM_CTL), [])
                if kind == 'group':
                    self.assertEqual(world.clicks, [])


class SwipeBehaviourTest(Base):
    def test_a_change_that_never_settles_is_an_error_not_a_boundary(self):
        for kind in ('group', 'team'):
            with self.subTest(kind=kind):
                world = World(GROUPS12, TEAMS)
                world.jitter = {kind}
                task = self.build(world)
                self.assert_fails(task, '组2', '组2队1', '没有稳定')
                self.assertEqual(self.click_of(TEAM_CTL), [])                # 不稳定时不会点到队伍
                if kind == 'group':
                    self.assertEqual(world.clicks, [])
                self.assertLess(world.shots, 90)

    def test_a_swipe_that_was_never_sent_is_not_counted(self):
        world = World(GROUPS12, TEAMS, group_offset=300)
        task = self.build(world, swipe_ok=False)
        self.assert_fails(task, '组1', '组1队1', '滑动没有发出')
        self.assertEqual(world.swipes, [])

    def test_swipes_that_have_no_effect_at_all_never_lead_to_a_wrong_click(self):
        world = World(GROUPS12, TEAMS, group_offset=300)
        world.ignore_swipes = True
        task = self.build(world)
        exc = self.assert_fails(task, '组1', '组1队1', '所有滑动都没有让列表移动')    # 滑动全部无效：页面问题，不能当作「名称不存在」
        self.assertNotIn('没有这个名字', str(exc))
        self.assertEqual(world.clicks, [])

    def test_a_short_list_that_fits_on_one_screen_proves_the_bottom_without_any_swipe_moving(self):
        world = World(names('组', 3), TEAMS)
        world.ignore_swipes = True                                          # 列表本来就不会动：最后一行下面空着一整行就是证据
        task = self.build(world)
        self.assert_fails(task, '不存在', '队', '不存在', '没有这个名字', human=True)

    def test_one_lost_swipe_is_not_mistaken_for_the_bottom(self):
        world = World(GROUPS12, TEAMS)
        world.lost_swipes = 1
        task = self.build(world)
        self.run_flow(task, '组11', '组11队9')
        self.assertEqual(world.selected, 10)

    def test_target_moving_after_the_search_is_clicked_at_its_new_position(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        # 找到「队5」之后、点击之前列表又滚了一段（惯性）：点击必须用新坐标
        original = task._name_find
        drifted = []

        def find_then_drift(spec, target, *rest):
            line = original(spec, target, *rest)
            if spec is TEAM_LIST:
                before = world.off['team']
                world.off['team'] = min(world.max_off('team'), before + 30)     # 又往后滚了 30px（行整体上移，仍完整可见）
                drifted.append(world.off['team'] - before)
            return line
        task._name_find = find_then_drift
        self.run_flow(task, '组2', '组2队5')
        self.assertTrue(drifted and drifted[0] != 0)
        clicks = self.click_of(TEAM_CTL)
        self.assertEqual({world.row_at('team', c[2]) for c in clicks}, {4})
        index, box = [(i, b) for i, b in world.rows('team') if i == 4][0]
        for _, _, y in clicks:                                      # 落点用的是漂移之后的新位置
            self.assertTrue(box[1] <= y <= box[1] + box[3] + 1, (y, box))

    def test_a_list_that_keeps_coasting_is_never_clicked_blindly(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        original = task._name_find

        def find_then_coast(spec, target, *rest):
            line = original(spec, target, *rest)
            if spec is TEAM_LIST:
                world.coast_forever = 40
            return line
        task._name_find = find_then_coast
        self.assert_fails(task, '组2', '组2队5', '无法稳定定位')
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_search_uses_only_the_ocr_specific_swipe_resources(self):
        world = World(GROUPS12, TEAMS, group_offset=200, team_offset=400)
        task = self.build(world)
        self.run_flow(task, '组9', '组9队7')
        used = {name for name, *_ in world.swipes}
        self.assertEqual(used, {'ss_name_group_to_top', 'ss_name_group_next', 'ss_name_team_to_top', 'ss_name_team_next'})


class SwipeResourceGeometryTest(Base):
    """新资源的方向与落点：手指方向、必须落在对应列表内、翻页距离留有重叠。"""

    @staticmethod
    def text_band(kind):
        """一个 24px 高的名称文字框能「完整可见」的纵向范围宽度：翻页位移小于它，任何文字都至少在某一屏完整出现一次。"""
        top, bottom = LISTS[kind]['vp']
        return (bottom - top) - 24 - 2 * 3

    def sample(self, swipe, times=300):
        return [swipe.sample_endpoints() for _ in range(times)]

    def check(self, swipe, kind, direction):
        spec = LISTS[kind]
        shifts = []
        for sx, sy, ex, ey in self.sample(swipe):
            self.assertTrue(spec['x'][0] <= sx <= spec['x'][1] and spec['x'][0] <= ex <= spec['x'][1], (sx, ex))
            self.assertTrue(spec['vp'][0] <= sy <= spec['vp'][1] and spec['vp'][0] <= ey <= spec['vp'][1], (sy, ey))
            shifts.append(sy - ey)
        self.assertTrue(all(s * direction > 0 for s in shifts), (direction, min(shifts), max(shifts)))
        return min(abs(s) for s in shifts), max(abs(s) for s in shifts)

    def test_group_swipes_land_inside_the_right_list_and_keep_overlap(self):
        _, hi = self.check(SwitchSoulAssets.S_SS_NAME_GROUP_NEXT, 'group', +1)         # 手指向上 = 向后翻页
        self.assertLess(hi, self.text_band('group'))
        self.check(SwitchSoulAssets.S_SS_NAME_GROUP_TO_TOP, 'group', -1)               # 手指向下 = 回顶

    def test_team_swipes_land_inside_the_central_list_and_keep_overlap(self):
        lo, hi = self.check(SwitchSoulAssets.S_SS_NAME_TEAM_NEXT, 'team', +1)
        self.assertLess(hi, self.text_band('team'))
        # 小步幅：基准约 135px（一行约 150px）；采样后的范围约 75～190，不能退回约 250px 的大步幅
        shifts = [sy - ey for sx, sy, ex, ey in self.sample(SwitchSoulAssets.S_SS_NAME_TEAM_NEXT, 1500)]
        mean = sum(shifts) / len(shifts)
        self.assertTrue(120 <= mean <= 150, mean)
        self.assertTrue(lo >= 60 and hi <= 210, (lo, hi))
        self.assertLess(hi, LISTS['team']['pitch'] + 70)                                # 最大位移也只比一行多一点
        top_lo, top_hi = self.check(SwitchSoulAssets.S_SS_NAME_TEAM_TO_TOP, 'team', -1)
        self.assertGreater(top_lo, mean)                                                # 回顶仍是较大步幅（最小位移也超过向后翻页的平均）
        # 落点避开左侧式神列表（x < 573）与底部新增按钮（y > 619）
        for swipe in (SwitchSoulAssets.S_SS_NAME_TEAM_NEXT, SwitchSoulAssets.S_SS_NAME_TEAM_TO_TOP):
            for sx, sy, ex, ey in self.sample(swipe):
                self.assertGreater(min(sx, ex), 573)
                self.assertLess(max(sy, ey), 619)

    def test_numeric_mode_resources_are_unchanged(self):
        expected = {
            'S_SS_GROUP_SWIPE_UP': ((1154, 180, 90, 21), (1153, 322, 86, 21)),
            'S_SS_GROUP_SWIPE_DOWN': ((1155, 388, 21, 22), (1152, 177, 22, 24)),
            'S_SS_TEAM_SWIPE_UP': ((782, 406, 21, 21), (793, 356, 21, 21)),
            'S_SS_TEAM_SWIPE_DOWN': ((709, 308, 21, 21), (709, 449, 21, 21)),
        }
        for name, (front, back) in expected.items():
            rule = getattr(SwitchSoulAssets, name)
            self.assertEqual((tuple(rule.roi_front), tuple(rule.roi_back)), (front, back), name)

    def test_ocr_regions_are_unchanged(self):
        self.assertEqual(tuple(SwitchSoulAssets.O_SS_GROUP_NAME.roi), (1087, 91, 155, 566))
        self.assertEqual(tuple(SwitchSoulAssets.O_SS_TEAM_NAME.roi), (573, 140, 277, 481))

    def test_every_new_swipe_is_a_real_ruleswipe(self):
        for name in ('S_SS_NAME_GROUP_TO_TOP', 'S_SS_NAME_GROUP_NEXT', 'S_SS_NAME_TEAM_TO_TOP', 'S_SS_NAME_TEAM_NEXT'):
            self.assertIsInstance(getattr(SwitchSoulAssets, name), RuleSwipe)

    def test_edge_rows_are_not_clickable(self):
        line = parse_lines([World._boxed('x', 0, 0, 30, 20)], (0, 144, 100, 100))[0]
        self.assertFalse(is_complete(line, (144, 619)))                                  # 贴着可视区上沿
        line = parse_lines([World._boxed('x', 0, 200, 30, 20)], (0, 144, 100, 400))[0]
        self.assertTrue(is_complete(line, (144, 619)))


class GroupConfirmationTest(Base):
    """目标分组是否选中，只看「选中标志落在目标行」这个状态证据；中央队伍列表可读 / 区域变化都不是证据。"""

    SAME_NAME = None

    def same_name_teams(self):
        teams = {g: names(f'{g}队', 9) for g in GROUPS8}
        teams['组1'] = ['x1', 'x2', '魂土'] + names('a', 6)                                  # 旧分组里「魂土」在第 3 行
        teams['组2'] = ['y1', 'y2', 'y3', 'y4', 'y5', '魂土'] + names('b', 3)                # 目标分组里「魂土」在第 6 行
        return teams

    def test_click_that_does_not_take_effect_stops_before_any_team_is_clicked(self):
        world = World(GROUPS8, TEAMS, selected=0, click_ignored=True)
        task = self.build(world)
        self.assert_fails(task, '组2', '组2队1', '组2', '无法确认目标分组已选中', '选中标志仍在别的分组', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])                       # 不会去点旧分组里的队伍
        self.assertEqual(len(self.click_of(GROUP_CTL)), SwitchSoul.NAME_GROUP_CLICK_TRIES)
        self.assertFalse(any('selection confirmed' in str(c.args[0]) for c in self.logger.info.call_args_list))

    def test_two_groups_with_the_same_team_name_are_never_confused(self):
        # 点击没生效、仍停在旧分组（它也有「魂土」）：不能误选旧分组里的「魂土」
        world = World(GROUPS8, self.same_name_teams(), selected=0, click_ignored=True)
        task = self.build(world)
        self.assert_fails(task, '组2', '魂土', '无法确认', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])
        # 点击生效：点的是目标分组里的「魂土」（第 6 行），不是旧分组里的（第 3 行）
        world = World(GROUPS8, self.same_name_teams(), selected=0)
        task = self.build(world)
        self.run_flow(task, '组2', '魂土')
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {5})
        self.assertEqual(world.shown, 1)

    def test_a_list_that_refreshes_late_is_waited_for_and_the_new_content_is_used(self):
        for delay in (2, 6):
            with self.subTest(delay=delay):
                world = World(GROUPS8, self.same_name_teams(), selected=0, refresh_delay=delay)
                task = self.build(world)
                self.run_flow(task, '组2', '魂土')
                self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {5})

    def test_only_an_unrelated_animation_is_not_a_selection(self):
        world = World(GROUPS8, TEAMS, selected=0, click_ignored=True, noise_on_click=True)
        task = self.build(world)
        self.assert_fails(task, '组2', '组2队1', '无法确认', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_a_selected_marker_with_a_central_list_that_never_changes_is_not_trusted(self):
        world = World(GROUPS8, self.same_name_teams(), selected=0, refresh_never=True)
        task = self.build(world)
        self.assert_fails(task, '组2', '魂土', '中央队伍列表一直没有变化', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_no_marker_anywhere_stops_safely_and_names_the_missing_screenshot(self):
        world = World(GROUPS8, TEAMS, marker=False)                         # 模板在当前页面识别不到
        task = self.build(world)
        self.assert_fails(task, '组2', '组2队1', '没有识别到任何分组选中标志', '整屏截图', 'ss_sou_check_group', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])
        self.assertLessEqual(len(self.click_of(GROUP_CTL)), SwitchSoul.NAME_GROUP_CLICK_TRIES)

    def test_two_markers_cannot_be_judged(self):
        world = World(GROUPS8, TEAMS, selected=0, extra_marker=4)
        task = self.build(world)
        self.assert_fails(task, '组2', '组2队1', '多个分组选中标志', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_previously_selected_group_scrolled_out_of_view_is_a_normal_case(self):
        world = World(GROUPS12, TEAMS, selected=10)                         # 选中的分组在可视区外：看不到任何标志
        task = self.build(world)
        self.run_flow(task, '组2', '组2队3')
        self.assertEqual(world.selected, 1)
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {2})

    def test_success_is_logged_only_after_the_marker_and_the_central_list_are_both_confirmed(self):
        world = World(GROUPS8, TEAMS, selected=0)
        task = self.build(world)
        self.run_flow(task, '组3', '组3队1')
        infos = [str(c.args[0]) for c in self.logger.info.call_args_list if c.args]
        confirmed = [i for i, t in enumerate(infos) if 'selection confirmed' in t]
        selected = [i for i, t in enumerate(infos) if t.startswith('Select group')]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(len(selected), 1)
        self.assertLess(confirmed[0], selected[0])


class ErrorClassificationTest(Base):
    """哪些错误转人工、哪些沿用重启恢复，以及它们在真实 `Script._handle_task_exception` 里实际怎么走。"""

    def setUp(self):
        super().setUp()
        import script as script_mod
        self.script = script_mod.Script.__new__(script_mod.Script)
        self.config = SimpleNamespace(task_call=Mock(), notifier=Mock(), task_runtime_outcome=None,
                                      model=SimpleNamespace(restart=SimpleNamespace(scheduler=SimpleNamespace(enable=True))))
        self.script.__dict__['config'] = self.config
        self.script.config_name = 'simA'
        self.script.last_task_runtime_outcome = None
        self.script.device = SimpleNamespace(package='pkg', sleep=Mock())
        self.script.save_error_log = Mock()
        self.script.exception_handler = Mock()
        self.script._loop_note_recovery = Mock()
        self.script._loop_fail_before_exit = Mock()

    def raised(self, world, group, team, human):
        task = self.build(world)
        kind = SwitchSoulNameError if human else SwitchSoulPageError
        with self.assertRaises(kind) as ctx:
            self.run_flow(task, group, team)
        self.assertFalse(self.success_logged())
        return ctx.exception

    def test_config_style_errors_are_human_takeover_errors(self):
        cases = [
            (World(GROUPS8, TEAMS), '', '队'),                                               # 空名称
            (World(GROUPS12, TEAMS), '不存在的组', '队'),                                     # 完整搜索后确认不存在
            (World(GROUPS8, TEAMS, duplicate_in_view=('group', '组1')), '组1', '组1队1'),     # 同屏重名
            (World(GROUPS8, TEAMS, click_ignored=True), '组2', '组2队1'),                     # 无法确认分组选中
        ]
        for world, group, team in cases:
            with self.subTest(group=group):
                exc = self.raised(world, group, team, human=True)
                self.assertIsInstance(exc, RequestHumanTakeover)
                self.assertNotIsInstance(exc, GamePageUnknownError)

    def test_transient_errors_are_page_errors_and_never_claim_the_name_does_not_exist(self):
        def endless_world():
            world = World(names('组', 8), TEAMS)
            return world
        blind = World(GROUPS8, TEAMS)
        blind.always_empty.add('group')
        unstable = World(GROUPS12, TEAMS)
        unstable.jitter = {'group'}
        dead = World(GROUPS12, TEAMS, group_offset=300)
        dead.ignore_swipes = True
        for name, world in (('OCR 失败', blind), ('不稳定', unstable), ('滑动全部无效', dead)):
            with self.subTest(case=name):
                exc = self.raised(world, '组1', '组1队1', human=False)
                self.assertIsInstance(exc, GamePageUnknownError)
                self.assertNotIsInstance(exc, RequestHumanTakeover)
                self.assertNotIn('没有这个名字', str(exc))

    def test_device_errors_keep_their_original_type(self):
        world = World(GROUPS8, TEAMS)
        task = self.build(world)
        original = task.screenshot

        def broken():
            if world.shots >= 2:
                raise GameStuckError('设备卡死')
            original()
        task.screenshot = broken
        with self.assertRaises(GameStuckError):                             # 不被包装成配置错误或页面错误
            self.run_flow(task, '组2', '组2队1')

    def test_script_sends_a_name_error_to_human_takeover_without_scheduling_a_restart(self):
        exc = self.raised(World(GROUPS12, TEAMS), '不存在的组', '队', human=True)
        with self.assertRaises(SystemExit):
            self.script._handle_task_exception(exc, 'AreaBoss')
        for call in self.config.task_call.call_args_list:
            self.assertNotEqual(call.args, ('Restart',))                    # 写错名字不会触发「重启游戏」
        self.config.task_call.assert_not_called()
        self.script.exception_handler.assert_called_once()
        self.assertIs(self.script.exception_handler.call_args.kwargs['e'], exc)         # 原异常对象传下去，目标 / 阶段可追踪
        self.assertIn('不存在的组', str(exc))
        self.assertIn('从上到下查找', str(exc))
        self.assertIn('RequestHumanTakeover', self.config.notifier.push.call_args.kwargs['content'])

    def test_script_keeps_the_existing_restart_recovery_for_page_errors(self):
        dead = World(GROUPS12, TEAMS, group_offset=300)
        dead.ignore_swipes = True
        exc = self.raised(dead, '组1', '组1队1', human=False)
        self.assertFalse(self.script._handle_task_exception(exc, 'AreaBoss'))
        self.config.task_call.assert_called_once_with('Restart')
        self.assertIs(self.script.exception_handler.call_args.kwargs['e'], exc)
        self.script.save_error_log.assert_called_once()

    def test_exception_classes_are_local_and_do_not_touch_the_shared_ones(self):
        self.assertTrue(issubclass(SwitchSoulNameError, RequestHumanTakeover))
        self.assertTrue(issubclass(SwitchSoulPageError, GamePageUnknownError))
        self.assertFalse(issubclass(SwitchSoulNameError, GamePageUnknownError))
        self.assertFalse(issubclass(SwitchSoulPageError, RequestHumanTakeover))
        self.assertEqual(GamePageUnknownError.__mro__[1], Exception)         # 公共异常的继承关系没动
        self.assertEqual(RequestHumanTakeover.__mro__[1], Exception)


class SmallStepSearchTest(Base):
    """队伍向后翻页改成小步幅（基准约 135px，一行约 150px）：逐行可见、不漏边缘行、不误报循环、预算够用。"""

    def long_world(self, n, **kwargs):
        return World(GROUPS8, {g: names('队', n) for g in GROUPS8}, max_shots=2500, **kwargs)

    def test_neighbouring_teams_become_visible_in_turn_with_overlap_between_screens(self):
        world = self.long_world(14)
        task = self.build(world)
        pages = []
        original = task._name_read

        def spy(spec, fresh=True):
            lines = original(spec, fresh)
            if spec is TEAM_LIST:
                shown = [l.text for l in lines if l.text != '40']
                if not pages or pages[-1] != shown:
                    pages.append(shown)
            return lines
        task._name_read = spy
        self.run_flow(task, '组3', '队14')
        seen = [t for page in pages for t in page]
        for index in range(14):
            self.assertIn(f'队{index + 1}', seen)                            # 每个队伍都在某一屏出现过
        for before, after in zip(pages, pages[1:]):
            self.assertTrue(set(before) & set(after), (before, after))       # 相邻两屏有重叠：没有跳行
        self.assertGreater(len(pages), 4)                                    # 小步幅：确实是一点点往下看

    def test_a_target_first_seen_clipped_at_the_bottom_is_found_after_the_next_swipe(self):
        clipped_then_found = 0
        for index in range(14):
            with self.subTest(team=index):
                world = self.long_world(14)
                task = self.build(world)
                name = f'队{index + 1}'
                seen = []
                real = ss.is_complete

                def spy(line, viewport, real=real, name=name, seen=seen):
                    ok = real(line, viewport)
                    if line.text == name:
                        seen.append(ok)
                    return ok
                # 向后翻页的端点固定成 100px（落在采样范围 75～190 内）：随机采样下「先被裁切」是否出现取决于抽到的步幅，断言会时有时无；
                # 步幅 100px、行距 140px 时，第 6 个队伍（下标 5）第一次露头正好在下沿被裁切（文字框贴着可视区下沿）
                fixed = patch.object(SwitchSoulAssets.S_SS_NAME_TEAM_NEXT, 'sample_endpoints', return_value=(680, 430, 680, 330))
                with fixed, patch.object(ss, 'is_complete', spy):
                    self.run_flow(task, '组3', name)
                self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {index})
                first_complete = seen.index(True) if True in seen else len(seen)
                if False in seen[:first_complete]:
                    clipped_then_found += 1
        self.assertGreater(clipped_then_found, 0)                            # 至少有一个队伍先在下沿被裁切、翻页后才完整出现并被找到

    def test_many_identical_neighbouring_screens_are_not_mistaken_for_a_loop(self):
        world = self.long_world(14, gain=0.3)                                # 每次只滚约 40px：连续很多屏文字完全相同
        task = self.build(world)
        self.run_flow(task, '组3', '队14')
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {13})

    def test_a_long_list_is_searched_within_the_budget(self):
        world = self.long_world(40)
        task = self.build(world)
        start = world.now
        self.run_flow(task, '组3', '队40')
        forward = [s for s in world.swipes if s[0] == 'ss_name_team_next']
        self.assertLessEqual(len(forward), TEAM_LIST.max_pages)
        self.assertLess(world.now - start, task.NAME_STAGE_TIMEOUT * TEAM_LIST.timeout_scale)
        self.assertEqual({world.row_at('team', c[2]) for c in self.click_of(TEAM_CTL)}, {39})

    def test_a_missing_name_in_a_long_list_still_confirms_the_bottom_then_asks_for_a_human(self):
        world = self.long_world(40)
        task = self.build(world)
        self.assert_fails(task, '组3', '不存在', '没有这个名字', human=True)
        self.assertEqual(self.click_of(TEAM_CTL), [])

    def test_returning_to_the_top_from_the_bottom_of_a_long_list_stays_within_its_budget(self):
        world = self.long_world(30)
        world.shown = 2
        world.off['team'] = world.max_off('team')
        task = self.build(world)
        moved = self.run_stage(lambda: task._name_to_top(TEAM_LIST, 'x'))
        self.assertTrue(moved)
        self.assertEqual(world.off['team'], 0)
        self.assertLessEqual(len([s for s in world.swipes if s[0] == 'ss_name_team_to_top']), TEAM_LIST.max_top)

    def test_budgets_are_bounded_and_scaled_for_the_smaller_step(self):
        self.assertEqual((TEAM_LIST.max_top, TEAM_LIST.max_pages, TEAM_LIST.timeout_scale), (30, 60, 2.0))
        self.assertEqual((GROUP_LIST.max_top, GROUP_LIST.max_pages, GROUP_LIST.timeout_scale), (12, 20, 1.0))
        self.assertEqual(SwitchSoul.NAME_STAGE_TIMEOUT * TEAM_LIST.timeout_scale, 300.0)

    def test_the_search_still_goes_through_the_swipe_pipeline_entry_points(self):
        world = self.long_world(14)
        task = self.build(world)
        calls = []
        base = task.swipe_trajectory

        def spy(start, end, *, control_name='SWIPE', fallback=True):
            calls.append(control_name)
            return base(start, end, control_name=control_name, fallback=fallback)
        task.swipe_trajectory = spy                                           # `BaseTask.swipe` 最终调用的就是它
        self.run_flow(task, '组3', '队9')
        self.assertIn('ss_name_team_next', calls)
        self.assertTrue(set(calls) <= {'ss_name_group_to_top', 'ss_name_group_next', 'ss_name_team_to_top', 'ss_name_team_next'})
