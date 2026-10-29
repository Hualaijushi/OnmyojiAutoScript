# This Python file uses the following encoding: utf-8
"""福利道馆模式：离线假游戏 + 虚拟时钟测试，用真实的 WelfareDokan 流程驱动一个假游戏（World）。

World 只负责「点什么 → 画面怎么变」，时间是虚拟的（每次截图 +0.2s，sleep 直接推进），所以 600 秒 /
120 秒等待不用真等。World 是测试替身，不是真实 MuMu / 游戏，不代表模板匹配 / OCR / 滑动 / 游戏时序
真实可用，这些仍待真机验收。
"""

import unittest
import zlib
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from module.atom.swipe import RuleSwipe
from module.base import timer as timer_module
from module.base.timer import Timer
from module.device.device import Device
from module.exception import GamePageUnknownError, GameStuckError, GameTooManyClickError, RequestHumanTakeover
from module.fatigue import FatigueManager
from tasks.Dokan import script_task as dokan_script
from tasks.Dokan import welfare
import tasks.Dokan.page as pages
from tasks.Dokan.assets import DokanAssets
from tasks.Dokan.config import Dokan
from tasks.Dokan.script_task import ScriptTask
from tasks.Dokan.welfare import WelfareDokan, card_fingerprint, same_card
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.GlobalGame.config import FatigueConfig

SLOT_Y = [70 + 145 * i for i in range(4)]


def XIN_MATCH(slot):
    """第 slot 行「鑫」的真实五项匹配结果：越靠下分数越高，x 在 1150～1156 之间错开。"""
    return (0.90 + 0.02 * slot, 1150 + (slot * 5) % 7, SLOT_Y[slot] - 17, 19, 34)


def card(cid, *, xin=True, people=150, challengeable=True, lag=0):
    return {'id': cid, 'xin': xin, 'people': people, 'challengeable': challengeable, 'lag': lag}


def texture(seed, shape):
    return np.random.RandomState(seed).randint(0, 255, shape, dtype=np.uint8)


class Rule:
    def __init__(self, key, roi_front=(100, 100, 20, 20)):
        self.key = key
        self.name = key.lower()
        self.roi_front = roi_front
        self.roi = (0, 0, 0, 0)

    def coord(self):
        x, y, w, h = self.roi_front
        return x + w // 2, y + h // 2


class Fatigue:
    """记录 suspend_active 的起止（虚拟时间）。"""

    def __init__(self, world):
        self.world = world
        self.intervals = []

    def suspend_active(self):
        manager = self

        class Ctx:
            def __enter__(self):
                self.start = manager.world.now

            def __exit__(self, *exc):
                manager.intervals.append((self.start, manager.world.now))
                return False

        return Ctx()


class World:
    def __init__(self, *, remaining=2, cards=None, refreshes=(), start='find', gather=30.0, count_known=True,
                 hide_clicks=1, exists=None, vote_mode='selected', vote_close_delay=20.0,
                 again_matches=None, refresh_blocked=False, abandon_stage=False, next_cards=None, lose_swipes=0,
                 swipe_mode='normal', final_unreadable=False, final_left=None, throttle=0, flicker=4,
                 swipe_script=None, base_frame=None, unsent_swipes=0, click_guard=False,
                 preset_mode='dialog', late_after=2, late_delay=1.0, preset_throttle=0, back_blocked=False,
                 own='created', create_mode='ok', create_late=1.0,
                 stuck_guard=False, transition=0.0, start_mode='ok',
                 refresh_scroll='top', refresh_delay=0.0, refresh_effect='ok', highlight=False,
                 after_again='find', exit_mode='ok', exit_result='find', exit_delay=0.4,
                 snap_step=0.2, vote_change_delay=0.0):
        self.now = 0.0
        self.remaining = remaining
        self.cards = cards if cards is not None else [card('a')]
        self.refreshes = list(refreshes)
        self.phase = start
        self.scroll = 0
        self.selected = None
        self.last_selected = None
        self.reads = 0
        self.gather = gather
        self.count_known = count_known
        self.hide_clicks = hide_clicks
        self.hidden = 0
        self.exists_script = list(exists) if exists is not None else None
        self.vote_mode = vote_mode
        self.vote_close_delay = vote_close_delay
        self.again_matches = [(0.93, 264, 346, 18, 32)] if again_matches is None else again_matches
        self.refresh_blocked = refresh_blocked
        self.abandon_stage = abandon_stage
        self.next_cards = next_cards
        self.lose_swipes = lose_swipes
        self.swipe_mode = swipe_mode            # normal / animate（一直在变）/ late（先在变、之后稳定）
        self.noise_left = 0
        # 再战等待结束后停在哪：find（游戏自动回到地图找馆页，原行为）/ dokan_page（仍停在道馆页，要走「退出图标 → 退出确认」）；
        # exit_mode：ok / quit_dead（退出图标点了没反应）/ ensure_dead（退出确认点了没反应，仍在道馆页）；
        # exit_result：退出确认生效后看到什么——find（找馆页）/ found（进行中的馆）/ blank（什么都认不出）
        self.after_again, self.exit_mode, self.exit_result, self.exit_delay = after_again, exit_mode, exit_result, exit_delay
        self.exit_due = self.map_due = None
        # 每次截图推进的虚拟秒数（真实截图间隔在 0.1～0.3 秒之间）；再战点击之后按钮框晚多少秒才出现选中样式
        # （这期间每一帧都会经过公共卡死检查，用来制造「等待前检查次数 > 60、时间还没到 60 秒」）
        self.snap_step, self.vote_change_delay, self.vote_clicked_at = snap_step, vote_change_delay, 0.0
        self.goto_calls = []
        self.snapshots = 0
        # 脚本化滑动结果：每次「实际发出」的滑动取一项 (帧序列, 列表前进的卡片数)；帧序列用完后重复最后一帧。
        # 用来表达「回弹 / 小幅滚动 / 只有动画」这类默认随机纹理表达不了的真实画面变化
        self.swipe_script = list(swipe_script) if swipe_script is not None else None
        self.base_frame = base_frame
        self.queue = None
        self.unsent_swipes = unsent_swipes          # 前 N 次 task.swipe 调用没有发出（返回 False）
        # 预设：dialog（点一次就弹确认框）/ none（此前已预设过，永远不弹）/ late（第 late_after 次点击之后
        # 过 late_delay 秒才弹）/ stuck（弹出后点确定也关不掉）/ vanish（点了之后进入未知弹窗，按钮和确认框都看不到）
        self.preset_mode = preset_mode
        self.late_after = late_after
        self.late_delay = late_delay
        self.preset_throttle = preset_throttle      # 前 N 次对预设按钮的 appear_then_click 被限流（没有发出）
        self.back_blocked = back_blocked            # True：阵容页的返回按钮点了没反应
        self.preset_clicks = 0
        self.dialog_due = None
        # 我方道馆：own = created（已建立）/ uncreated（未建立）/ ambiguous（两个图标都分不出）/ absent（图标不在）；
        # create_mode = ok / no_dialog（点建立入口没反应）/ late（确认框晚 create_late 秒出）/ ensure_dead（点确认没反应）/
        # info_stuck（信息页关不掉）/ popup（点确认后进入未知弹窗）
        self.own = own
        self.create_mode = create_mode
        self.create_late = create_late
        self.create_due = None
        # 集结阶段：stuck_guard=True 时设备带真实 Device 的卡死检查（screenshot 前检查 / 点击清除 / app_stop 清除）；
        # transition = 集结结束后先出现这么久的未知画面才出现「开始挑战」；start_mode = ok / dead（点开始挑战没反应）
        # 刷新（D-09）：refresh_scroll = top（刷新后列表回到顶部）/ keep（保持刷新前的位置）；refresh_delay = 点确认之后
        # 新列表晚多少秒才出现（这期间还是旧列表）；refresh_effect = ok / none（确认框消失了，但游戏限制了刷新，列表不变）/
        # unknown_page（点确认后进入了认不出的画面）
        self.refresh_scroll = refresh_scroll
        self.refresh_delay = refresh_delay
        self.refresh_effect = refresh_effect
        self.refresh_due = None
        self.refresh_count = 0
        self.highlight = highlight          # True：被选中的候选卡片画一圈高亮边框
        self.stuck_guard = stuck_guard
        self.transition = transition
        self.start_mode = start_mode
        self.wall_base = 1_000_000.0                # 真实 Timer 用 time.time()：给虚拟时钟加偏移，避开「0 = 未启动」
        self.last_click_at = {}
        self.click_guard = click_guard              # True：设备带真实 Device 的操作记录写入 / 检查 / 移除逻辑
        self.final_unreadable = final_unreadable   # 放弃后「用完」只看得到一帧，最终读取时读不到
        self.final_left = final_left                # 放弃后「用完」只看得到一帧，最终读取时读到这个数
        self.done_looks = 0
        self.throttle_clicks = throttle             # 前 N 次点击再战按钮的调用被限流（没有发出）
        self.flicker = flicker                      # flicker 模式：点击后按钮漏识别的截图数
        self.flicker_left = 0
        self.snap_no = 0
        self.events = []
        self.checked = []           # 被点击检查过的候选 id（按顺序）
        self.opened = []
        self.closed_at = None
        self.alive = True
        self.vote_seed = 1
        self.gather_until = None
        self.vote_until = None
        self.fatigue = Fatigue(self)
        self.violations = []
        self.dokans_done = 0

    # --- 时间
    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.log('sleep', round(seconds, 3))

    def log(self, *event):
        self.events.append(event)
        if len(self.events) > 6000:
            raise AssertionError('流程失控：事件数超过上限（疑似死循环）')

    def kinds(self, kind):
        return [event for event in self.events if event[0] == kind]

    # --- 画面
    @property
    def visible_cards(self):
        return self.cards[self.scroll:self.scroll + 4]

    @property
    def max_scroll(self):
        return max(0, len(self.cards) - 4)

    def finish_exit(self):
        if self.exit_result == 'find':
            self.phase = 'find'
            if self.next_cards is not None:
                self.cards, self.scroll, self.selected = self.next_cards, 0, None
        elif self.exit_result == 'found':
            self.phase = 'map_found'
        else:
            self.phase = 'blank'

    def snapshot(self):
        self.now += self.snap_step
        self.snapshots += 1
        if self.snapshots > 5000:
            raise AssertionError('流程失控：截图次数超过上限（疑似无界循环）')
        if self.phase == 'exit_wait' and self.now >= self.exit_due:
            self.phase = 'exit_dialog'
        if self.phase == 'map_wait' and self.now >= self.map_due:
            self.finish_exit()
        if self.phase == 'closed':
            self.violations.append(('screenshot_while_closed', self.now))
        if self.phase == 'dokan_gathering' and self.now >= self.gather_until:
            self.phase = 'transition' if self.transition > 0 else 'dokan_ready'
        if self.phase == 'transition' and self.now >= self.gather_until + self.transition:
            self.phase = 'dokan_ready'
        if self.dialog_due is not None and self.phase == 'team' and self.now >= self.dialog_due:
            self.phase, self.dialog_due = 'preset_dialog', None
        if self.refresh_due is not None and self.phase == 'find' and self.now >= self.refresh_due:
            self.refresh_due = None
            self.apply_refresh()
        if self.create_due is not None and self.phase == 'find' and self.now >= self.create_due:
            self.phase, self.create_due = 'create_dialog', None
        if self.phase == 'vote_selected' and self.now >= self.vote_until:
            if self.after_again == 'dokan_page':
                self.phase = 'dokan_stay'
            else:
                self.phase = 'find'
                if self.next_cards is not None:
                    self.cards, self.scroll, self.selected = self.next_cards, 0, None
        self.log('screenshot', round(self.now, 2))
        if self.swipe_script is not None and self.phase == 'find':
            if self.queue and len(self.queue) > 1:
                frame = self.queue.pop(0)
            else:
                frame = self.queue[0] if self.queue else self.base_frame
            return np.array(frame() if callable(frame) else frame)
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        if self.phase in ('find', 'refresh_dialog', 'challenge_dialog'):
            for slot, item in enumerate(self.visible_cards):
                cy = SLOT_Y[slot]
                image[cy - 55:cy + 88, 1075:1245] = texture(zlib.crc32(item['id'].encode()) % 100000, (143, 170, 3))
                if self.highlight and self.selected is item:
                    image[cy - 55:cy - 51, 1075:1245] = 255
                    image[cy + 84:cy + 88, 1075:1245] = 255
        if self.phase in ('vote', 'vote_selected'):
            self.snap_no += 1
            image[215:330, 1150:1265] = texture(1, (115, 115, 3))
            if self.phase == 'vote_selected':
                if self.vote_mode == 'selected' and self.now >= self.vote_clicked_at + self.vote_change_delay:
                    image[250:320, 1160:1250] = texture(3, (70, 90, 3))               # 按钮框变成选中样式并保持
                elif self.vote_mode == 'counts_only':
                    image[215:245, 1150:1265] = texture(100 + self.snap_no, (30, 115, 3))   # 只有票数在变
                elif self.vote_mode == 'animation':
                    image[250:320, 1160:1250] = texture(200 + self.snap_no, (70, 90, 3))    # 按钮框一直在变
                elif self.vote_mode == 'page_switch':
                    image[:, :] = texture(300, (720, 1280, 3))                      # 切到无关页面
        if self.noise_left > 0:
            self.noise_left -= 1
            image[0:602, 1077:1248] = texture(500 + self.snap_no, (602, 171, 3))
            self.snap_no += 1
        return image

    def icon_visible(self, key, threshold):
        """「建立道馆」入口图标。两个模板互相匹配分约 0.96（真实量得）：默认阈值 0.8 下两张都命中，
        只有高阈值才分得开。"""
        if self.phase != 'find' or self.own == 'absent':
            return False
        if self.own == 'ambiguous':
            return True
        mine = 'HAVE' if self.own == 'created' else 'CREATE'
        if key == mine:
            return True
        return threshold is None or threshold < 0.97

    def visible(self, key):
        phase = self.phase
        if key == 'FINDING':
            return phase in ('find', 'refresh_dialog', 'challenge_dialog')
        if key == 'FOUND':
            return phase in ('map_found', 'map_returned')
        if key == 'CHECK':
            return phase in ('dokan_gathering', 'dokan_ready', 'dokan_scene', 'abandon_dialog', 'vote',
                             'vote_selected', 'abandon_vote', 'rank_popup', 'dokan_stay', 'exit_dialog')
        if key == 'QUIT':
            return phase == 'dokan_stay'
        if key == 'EXIT_ENSURE':
            return phase == 'exit_dialog'
        if key == 'GATHERING':
            return phase == 'dokan_gathering'
        if key == 'START':
            return phase == 'dokan_ready'
        if key == 'PREPARE':
            return phase == 'prepare'
        if key in ('COUNT_ZERO', 'COUNT_DONE', 'COUNT_ONE', 'COUNT_TWO'):
            if phase == 'map_done' and (self.final_unreadable or self.final_left is not None):
                self.done_looks += 1
                if self.done_looks <= 2:                 # 放弃收尾那一帧：ZERO / DONE 各看一次
                    return key == 'COUNT_ZERO' and self.done_looks == 1
                if self.final_left is not None:
                    return key == {1: 'COUNT_ONE', 2: 'COUNT_TWO'}.get(self.final_left)
                return False
            if not self.count_known or phase not in ('find', 'map_found', 'dokan_scene', 'vote', 'map_done',
                                                      'vote_selected', 'refresh_dialog', 'challenge_dialog'):
                return False
            value = {'COUNT_ZERO': 0, 'COUNT_ONE': 1, 'COUNT_TWO': 2}.get(key)
            return value == self.remaining
        if key == 'CREATE_ENSURE':
            return phase == 'create_dialog'
        if key == 'INFO_CLOSE':
            return phase == 'create_info'
        if key == 'TEAM':
            return phase == 'find'
        if key == 'PRESET':
            return phase == 'team'
        if key == 'UI_CONFIRM':
            return phase == 'preset_dialog'
        if key == 'UI_BACK':
            return phase in ('team',)
        if key == 'CENTER_PEOPLE':
            return phase == 'find' and self.selected is not None
        if key == 'CENTER_CHALLENGE':
            return phase == 'find' and self.selected is not None and self.selected['challengeable']
        if key == 'CHALLENGE_ENSURE':
            return phase == 'challenge_dialog'
        if key == 'REFRESH_ENSURE':
            return phase == 'refresh_dialog'
        if key == 'ABANDON':
            return phase == 'dokan_scene'
        if key == 'ABANDON_ENSURE':
            return phase == 'abandon_dialog'
        if key == 'RANK':
            return phase == 'rank_popup'
        if key in ('TITLE', 'ABANDONED'):
            return phase == 'abandon_vote'
        if key in ('BATTLE_AGAIN', 'KEEP'):
            if phase == 'vote':
                return True
            if phase != 'vote_selected':
                return False
            if self.vote_mode == 'flicker':
                if self.flicker_left > 0:
                    self.flicker_left -= 1
                    return False
                return True
            return self.vote_mode in ('selected', 'counts_only', 'animation', 'stays')
        return False

    # --- 动作
    def click_key(self, key):
        phase = self.phase
        self.log('click', key)
        if key == 'UI_BACK' and phase == 'team':
            if not self.back_blocked:
                self.phase = 'find'
        elif key == 'TEAM' and phase == 'find':
            self.phase = 'team'
        elif key == 'CREATE' and phase == 'find':
            if self.own == 'uncreated' and self.create_mode != 'no_dialog':
                if self.create_mode == 'late':
                    self.create_due = self.now + self.create_late
                else:
                    self.phase = 'create_dialog'
        elif key == 'CREATE_ENSURE' and phase == 'create_dialog':
            self.log('create_confirmed')
            if self.create_mode == 'popup':
                self.phase = 'popup'
            elif self.create_mode != 'ensure_dead':
                self.phase = 'create_info'
        elif key == 'INFO_CLOSE' and phase == 'create_info':
            if self.create_mode != 'info_stuck':
                self.phase, self.own = 'find', 'created'
                self.log('own_created')
        elif key == 'PRESET' and phase == 'team':
            self.preset_clicks += 1
            if self.preset_mode in ('dialog', 'stuck'):
                self.phase = 'preset_dialog'
            elif self.preset_mode == 'vanish':
                self.phase = 'popup'
            elif self.preset_mode == 'late' and self.preset_clicks == self.late_after:
                self.dialog_due = self.now + self.late_delay
        elif key == 'UI_CONFIRM' and phase == 'preset_dialog':
            if self.preset_mode != 'stuck':
                self.phase = 'team'
                self.log('preset_confirmed')
        elif key == 'CANCEL' and phase == 'find' and self.selected is not None:
            self.hidden += 1
            if self.hidden >= self.hide_clicks:
                self.last_selected, self.selected, self.hidden = self.selected, None, 0
        elif key == 'CENTER_CHALLENGE' and self.visible('CENTER_CHALLENGE'):
            self.phase = 'challenge_dialog'
        elif key == 'CHALLENGE_ENSURE' and phase == 'challenge_dialog':
            self.remaining -= 1
            self.opened.append(self.selected['id'])
            self.log('opened', self.selected['id'], self.now)
            self.phase = 'map_found'
        elif key == 'REFRESH' and phase == 'find' and not self.refresh_blocked:
            self.phase = 'refresh_dialog'
        elif key == 'REFRESH_ENSURE' and phase == 'refresh_dialog':
            self.refresh_count += 1
            self.selected = None
            if self.refresh_effect == 'unknown_page':
                self.phase = 'popup'
            elif self.refresh_effect == 'none':
                self.phase = 'find'
                self.log('refresh_ignored')
            else:
                self.phase = 'find'
                if self.refresh_delay > 0:
                    self.refresh_due = self.now + self.refresh_delay
                else:
                    self.apply_refresh()
        elif key == 'START' and phase == 'dokan_ready':
            if self.start_mode != 'dead':
                self.phase = 'prepare'
        elif key == 'QUIT' and phase == 'dokan_stay' and self.exit_mode != 'quit_dead':
            self.phase, self.exit_due = 'exit_wait', self.now + self.exit_delay
        elif key == 'EXIT_ENSURE' and phase == 'exit_dialog' and self.exit_mode != 'ensure_dead':
            self.phase, self.map_due = 'map_wait', self.now + self.exit_delay
        elif key == 'ABANDON' and phase == 'dokan_scene':
            self.phase = 'abandon_dialog'
        elif key == 'ABANDON_ENSURE' and phase == 'abandon_dialog':
            self.log('abandoned', self.now)
            self.dokans_done += 1
            if self.remaining > 0:
                self.phase = 'abandon_vote' if self.abandon_stage else 'vote'
            else:
                self.phase = 'map_done'
        elif key == 'ABANDONED' and phase == 'abandon_vote':
            self.phase = 'vote'
        elif key == 'BATTLE_AGAIN' and phase in ('vote', 'vote_selected'):
            self.log('vote_again', self.now)
            self.vote_clicked_at = self.now
            self.vote_until = self.now + self.vote_close_delay
            self.flicker_left = self.flicker
            self.phase = 'vote_selected'
        elif key == 'KEEP':
            self.log('keep_bounty', self.now)
            self.violations.append(('keep_bounty', self.now))

    def apply_refresh(self):
        old_scroll = self.scroll
        self.cards = self.refreshes.pop(0) if self.refreshes else []
        self.scroll = 0 if self.refresh_scroll == 'top' else min(old_scroll, self.max_scroll)
        self.selected = None
        if self.swipe_script is not None and self.base_frame is not None:
            self.base_frame = np.flipud(np.array(self.base_frame)).copy()      # 脚本化画面：刷新后换一个明显不同的列表画面
            self.queue = None
        self.log('refreshed')

    def click_xy(self, x, y, control_name):
        self.log('click_xy', control_name, x, y)
        if control_name == 'dokan_welfare_candidate':
            if self.selected is not None:
                self.violations.append(('candidate_click_with_popup', self.now))
            slot = min(range(4), key=lambda i: abs(SLOT_Y[i] - y))
            item = self.visible_cards[slot]
            self.selected = item
            self.reads = 0
            self.checked.append(item['id'])
        elif control_name == 'prepare':
            if self.phase != 'prepare':
                self.violations.append(('prepare_click_outside_prepare', self.phase))
            self.log('prepare_click')
        elif control_name == 'dokan_welfare_return_badge':
            self.log('badge', x, y)
            if self.phase == 'map_returned':
                self.phase = 'dokan_scene'

    def swipe(self, reverse=False):
        self.log('swipe_down' if reverse else 'swipe')
        if len(self.kinds('swipe')) > 400:
            raise AssertionError('流程失控：滑动次数超过上限（疑似无限滑动）')
        if self.swipe_script is not None:
            frames, advance = self.swipe_script.pop(0) if self.swipe_script else ([self.base_frame], 0)
            self.queue = list(frames)
            self.scroll = min(self.scroll + advance, self.max_scroll)
            return
        if self.lose_swipes > 0:
            self.lose_swipes -= 1                     # 这一次滑动没有生效
            return
        if self.swipe_mode == 'animate':
            self.noise_left = 10 ** 9                 # 列表一直在变化，永远不稳定
        elif self.swipe_mode == 'late':
            self.noise_left = 30                      # 先变化一阵，之后稳定
        if reverse:
            self.scroll = max(0, self.scroll - 2)
        elif self.scroll < self.max_scroll:
            self.scroll = min(self.scroll + 2, self.max_scroll)

    def goto(self, page):
        self.log('goto', 'dokan_map' if page is pages.page_dokan_map else 'dokan')
        if page is pages.page_dokan_map:
            if self.phase == 'courtyard':
                self.phase = 'map_returned'
        elif page is pages.page_dokan:
            if self.phase == 'map_found':
                self.phase = 'dokan_gathering'
                self.gather_until = self.now + self.gather

    # --- 设备
    def app_stop(self):
        self.log('app_stop', self.now)
        if self.phase == 'prepare':
            self.log('stopped_from_prepare')
        self.alive = False
        self.phase = 'closed'
        self.closed_at = self.now

    def app_start(self):
        self.log('app_start', self.now)
        if self.closed_at is None or self.now - self.closed_at < welfare.CLOSED_WAIT_SECONDS:
            self.violations.append(('started_early', self.now))
        self.alive = True
        self.phase = 'courtyard'

    def app_process_exists(self):
        self.log('process_query', self.now)
        if self.exists_script:
            step = self.exists_script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return self.alive

    def people_text(self):
        item = self.selected
        if item is None:
            return ''
        self.reads += 1
        if item['people'] is None:
            return ''
        if self.reads <= item['lag']:
            return '999人'
        return f"{item['people']}人"

    def match_xin(self):
        """与真实 `RuleImage.match_all_any()` 同一协议：每项 (score, x, y, w, h)。

        score / x 刻意与行号不单调相关，且整体按「分数从高到低」返回（不是从上到下），
        这样按 score 或 x 排序的错误实现都会暴露。
        """
        result = []
        if self.phase in ('find', 'refresh_dialog', 'challenge_dialog'):
            for slot, item in enumerate(self.visible_cards):
                if item['xin']:
                    result.append(XIN_MATCH(slot))
        return sorted(result, key=lambda m: -m[0])

    def login(self):
        self.log('login', self.now)


class RecordGuard:
    """真实 `Device` 的操作记录逻辑：写入 / 检查 / 移除的函数直接取自 `Device`（不是 mock），只把 deque 换成
    实例自有的（`Device.click_record` 是类属性，会在用例之间串）。阈值、清空行为都是公共代码本身。"""

    def __init__(self, world):
        self.world = world
        self.click_record = deque(maxlen=15)

    click_record_add = Device.click_record_add
    click_record_clear = Device.click_record_clear
    click_record_check = Device.click_record_check

    def stuck_record_clear(self):
        pass

    def handle_control_check(self, button):
        self.world.log('record_add', str(button))
        Device.handle_control_check(self, button)

    def click_record_remove(self, button):
        removed = Device.click_record_remove(self, button)
        self.world.log('record_remove', str(button), removed)
        return removed

    def count(self, name):
        return list(self.click_record).count(name)


class StuckRecordGuard(RecordGuard):
    """在 RecordGuard 上再加真实 `Device` 的卡死检查（stuck_record_add / clear / check 和 `stuck_long_wait_list` 取自 Device，
    不是 mock）；计时器是实例自有的 `Timer`，时间取自被替换的虚拟时钟（见 `make`）。"""

    stuck_long_wait_list = Device.stuck_long_wait_list
    stuck_record_add = Device.stuck_record_add

    def __init__(self, world):
        super().__init__(world)
        self.last_clear = world.now         # 记录「最近一次清除」到「每次检查」的最大间隔，用来看检查有没有机会误报
        self.max_gap = 0.0
        self.detect_record = set()
        self.stuck_timer = Timer(60, count=60).start()
        self.stuck_timer_long = Timer(300, count=300).start()

    def stuck_record_clear(self):
        self.last_clear = self.world.now
        Device.stuck_record_clear(self)

    def stuck_record_check(self):
        self.max_gap = max(self.max_gap, self.world.now - self.last_clear)
        return Device.stuck_record_check(self)

    def app_is_running(self):
        return self.world.alive

    def app_stop(self):
        self.stuck_record_clear()           # 与 Device.app_stop 一致
        self.click_record_clear()


class FakeDevice:
    def __init__(self, world):
        self.world = world
        self.image = None
        self.guard = StuckRecordGuard(world) if world.stuck_guard else (RecordGuard(world) if world.click_guard else None)

    def click(self, x, y, control_name='Click'):
        if self.guard:
            self.guard.handle_control_check(control_name)       # 与 Control.click 一样：先记录并检查，再执行
        self.world.click_xy(x, y, control_name)

    def click_record_remove(self, button):
        return self.guard.click_record_remove(button) if self.guard else 0

    def stuck_record_clear(self):
        if self.guard:
            self.guard.stuck_record_clear()

    def stuck_record_add(self, button):
        if self.guard:
            self.guard.stuck_record_add(button)

    def app_stop(self):
        self.world.app_stop()
        if self.world.stuck_guard:
            self.guard.app_stop()

    def app_start(self):
        self.world.app_start()
        if self.world.stuck_guard:
            self.guard.stuck_record_clear()         # 与 Device.app_start 一致
            self.guard.click_record_clear()

    def wait_app_start_ready(self):
        self.world.log('wait_ready')

    def app_process_exists(self):
        return self.world.app_process_exists()


class FakeTask:
    NAMES = {
        'I_RYOU_DOKAN_FOUND_DOKAN': 'FOUND', 'I_RYOU_DOKAN_FINDING_DOKAN': 'FINDING',
        'I_RYOU_DOKAN_CHECK': 'CHECK', 'I_RYOU_DOKAN_GATHERING': 'GATHERING',
        'I_RYOU_DOKAN_START_CHALLENGE': 'START', 'I_PREPARE_HIGHLIGHT': 'PREPARE',
        'I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ZERO': 'COUNT_ZERO', 'I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_DONE': 'COUNT_DONE',
        'I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_ONE': 'COUNT_ONE', 'I_RYOU_DOKAN_REMAIN_ATTACK_COUNT_TWO': 'COUNT_TWO',
        'I_DOKAN_TEAM': 'TEAM', 'I_DOKAN_TEAM_PRESET': 'PRESET',
        'I_CENTER_CHALLENGE': 'CENTER_CHALLENGE', 'I_CENTER_POINT_PEOPLE_NUMBER': 'CENTER_PEOPLE',
        'I_CHALLENGE_ENSURE': 'CHALLENGE_ENSURE', 'I_REFRESH_ENSURE': 'REFRESH_ENSURE',
        'C_DOKAN_CANCEL_SELECT_DOKAN': 'CANCEL', 'C_DOKAN_REFRESH': 'REFRESH',
        'C_DOKAN_TOPPA_RANK_CLOSE_AREA': 'RANK_CLOSE',
        'I_DOKAN_ABANDONED_TOPPA': 'ABANDON', 'I_DOKAN_ABANDONED_TOPPA_ENSURE': 'ABANDON_ENSURE',
        'I_DOKAN_ABANDONED_TOPPA_TITLE': 'TITLE', 'I_RYOU_DOKAN_ABANDONED_TOPPA_ABANDONED': 'ABANDONED',
        'I_RYOU_DOKAN_TOPPA_RANK': 'RANK',
        'I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN': 'BATTLE_AGAIN', 'I_RYOU_DOKAN_FAILED_VOTE_KEEP_BOUNTY': 'KEEP',
        'I_RYOU_DOKAN_CREATE_DOKAN': 'CREATE', 'I_RYOU_DOKAN_HAVE_DOKAN': 'HAVE',
        'I_RYOU_DOKAN_CREATE_DOKAN_ENSURE': 'CREATE_ENSURE', 'I_RYOU_DOKAN_DOKAN_INFO_CLOSE': 'INFO_CLOSE',
        'I_RYOU_DOKAN_DOKAN_QUIT': 'QUIT', 'I_RYOU_DOKAN_EXIT_ENSURE': 'EXIT_ENSURE',
    }

    # 真实的建馆方法（不是 mock）：识别 / 点击 / 时钟由本替身提供
    ensure_dokan_created = ScriptTask.ensure_dokan_created
    _ensure_dokan_created_strict = ScriptTask._ensure_dokan_created_strict
    own_dokan_state = ScriptTask.own_dokan_state
    creat_dokan = ScriptTask.creat_dokan

    def __init__(self, world, *, min_people=100, handle_error=True):
        self.world = world
        self.device = FakeDevice(world)
        for attr, key in self.NAMES.items():
            rule = Rule(key)
            real = getattr(DokanAssets, attr, None)
            if real is not None:
                rule.name = real.name            # 操作记录按真实资源名记（双按钮保护按名字计数）
            setattr(self, attr, rule)
        self.I_PREPARE_HIGHLIGHT.name = 'prepare'
        self.I_PREPARE_HIGHLIGHT.roi_front = (1128, 536, 100, 100)
        self.I_CENTER_POINT_PEOPLE_NUMBER.roi_front = (700, 400, 80, 24)
        self.I_RYOU_DOKAN_FAILED_VOTE_BATTLE_AGAIN.roi_front = (1160, 250, 90, 70)   # 点击时的按钮匹配框
        self.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image: world.match_xin())
        self.I_DOKAN_AGAIN_ENTER = SimpleNamespace(name='again', match_all_any=lambda image: list(world.again_matches))
        self.O_DOKAN_CENTER_PEOPLE_NUMBER = SimpleNamespace(roi=None, detect_text=lambda image: world.people_text())
        self.S_DOKAN_WELFARE_LIST_UP = DokanAssets.S_DOKAN_WELFARE_LIST_UP       # 真实资源：回顶滑动由它的端点反向派生
        dokan = Dokan()
        dokan.dokan_config.welfare_mode = True
        dokan.dokan_config.welfare_min_people = min_people
        self.config = SimpleNamespace(
            script=SimpleNamespace(error=SimpleNamespace(handle_error=handle_error)),
            dokan=dokan, config_name='sim', global_game=SimpleNamespace(fatigue=None))

    def _key(self, rule):
        if rule is GlobalGameAssets.I_UI_CONFIRM:
            return 'UI_CONFIRM'
        if rule is GlobalGameAssets.I_UI_BACK_YELLOW:
            return 'UI_BACK'
        return rule.key

    def screenshot(self):
        if self.world.stuck_guard:
            self.device.guard.stuck_record_check()          # 与 Device.screenshot 一致：先检查卡死，再截图
        self.device.image = self.world.snapshot()

    def appear(self, rule, interval=None, threshold=None):
        key = self._key(rule)
        if key in ('CREATE', 'HAVE'):
            return self.world.icon_visible(key, threshold)
        return self.world.visible(key)

    def wait_until_appear(self, target, skip_first_screenshot=False, wait_time=None):
        end = self.world.now + wait_time if wait_time else None
        while True:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.screenshot()
            if end is not None and self.world.now >= end:
                return False
            if self.appear(target):
                return True

    def appear_then_click(self, rule, action=None, interval=None, **kwargs):
        if self.appear(rule):
            key = self._key(rule)
            if interval:
                last = self.world.last_click_at.get(key)
                if last is not None and self.world.now - last < interval:
                    return False                         # 与真实 interval 限流一致：没到间隔，没有点击
            if key == 'PRESET' and self.world.preset_throttle > 0:
                self.world.preset_throttle -= 1          # 限流：看到了但没有发出点击
                return False
            self.world.last_click_at[key] = self.world.now
            if self.device.guard:
                self.device.guard.handle_control_check(rule.name)    # 真实 appear_then_click：先记录并检查，再点
            if self._key(rule) == 'BATTLE_AGAIN' and self.world.throttle_clicks > 0:
                self.world.throttle_clicks -= 1          # 限流：看到了但没有发出点击
                return False
            self.world.click_key(self._key(rule))
            return True
        return False

    def click(self, rule, interval=None, policy=None):
        if self.device.guard:
            self.device.guard.handle_control_check(rule.name)
        self.world.click_key(self._key(rule))
        return True

    def swipe(self, rule, interval=None):
        if self.world.unsent_swipes > 0:
            self.world.unsent_swipes -= 1
            self.world.log('swipe_not_sent')
            return False
        if self.device.guard:
            self.device.guard.handle_control_check(rule.name)   # Device.swipe_trajectory：先记录并检查，再滑
        self.world.swipe(reverse=rule.roi_back[1] > rule.roi_front[1])
        return True

    def goto_page(self, page, confirm_wait=0, skip_first_screenshot=True, timeout=30):
        """目的地 page_dokan_map 且当前在道馆页（CHECK 可见）时，按**真实**的 `page_dokan → page_dokan_map` 转换定义导航：
        取 `pages.page_dokan.transitions` 里的 ActionSequence（退出图标 → 退出确认），逐个识别并点击，再用新截图确认到达；
        无进展超过 `timeout` 抛 `GamePageUnknownError`（与真实 `goto_page` 的无进展超时同义）。其它情形沿用 world.goto。"""
        self.world.goto_calls.append(('goto', timeout))
        if page is pages.page_dokan_map and self.world.visible('CHECK'):
            transition = [t for t in pages.page_dokan.transitions if t.destination is pages.page_dokan_map][0]
            by_name = {getattr(DokanAssets, attr).name: getattr(self, attr) for attr in ('I_RYOU_DOKAN_DOKAN_QUIT', 'I_RYOU_DOKAN_EXIT_ENSURE')}
            steps = [by_name[item.name] for item in transition.action.actions]      # 真实序列里的资源，替身里没有就 KeyError
            start = self.world.now
            while True:
                self.screenshot()
                if self.appear(self.I_RYOU_DOKAN_FOUND_DOKAN) or self.appear(self.I_RYOU_DOKAN_FINDING_DOKAN):
                    return True
                if self.world.now - start >= timeout:
                    raise GamePageUnknownError(f'Cannot goto page[{page}]')
                if self.appear(self.I_RYOU_DOKAN_CHECK):
                    for step in steps:
                        self.screenshot()
                        self.appear_then_click(step, interval=1.5)
                self.world.sleep(0.5)
        self.world.goto(page)

    def ui_click_until_appear_or_timeout(self, click, stop=None, interval=1, timeout=10, policy=None):
        end = self.world.now + timeout
        while self.world.now < end:
            self.screenshot()
            if self.appear(stop):
                return True
            self.appear_then_click(click)
            self.world.sleep(interval)
        return False

    def ui_click_until_disappear(self, click, interval=1, policy=None, *, timeout=None, max_clicks=None, **kwargs):
        end = self.world.now + (timeout if timeout is not None else 1e9)
        clicks = 0
        clicked = False
        while self.world.now < end:
            self.screenshot()
            if not self.appear(click):
                return clicked
            if max_clicks is not None and clicks >= max_clicks:
                return False
            self.appear_then_click(click)
            clicks += 1
            clicked = True
            self.world.sleep(interval)
        return False


def make(world=None, *, min_people=100, handle_error=True, **kwargs):
    world = world or World(**kwargs)
    patchers = [patch.object(dokan_script, 'sleep', world.sleep)]       # 建馆方法里的 sleep 走虚拟时钟
    if world.stuck_guard:       # 真实 Timer 用 time.time()：先换成虚拟时钟，再创建带计时器的设备
        patchers.append(patch.object(timer_module, 'time', SimpleNamespace(time=lambda: world.wall_base + world.now)))
    for item in patchers:
        item.start()
    task = FakeTask(world, min_people=min_people, handle_error=handle_error)
    fatigue = world.fatigue
    fatigue_patch = patch.object(welfare, 'get_fatigue_manager', return_value=fatigue)
    fatigue_patch.start()
    patchers.insert(0, fatigue_patch)
    patcher = SimpleNamespace(stop=lambda: [item.stop() for item in reversed(patchers)])
    runner = WelfareDokan(task, clock=world.clock, sleep=world.sleep, login=world.login)
    return world, task, runner, patcher


class Base(unittest.TestCase):
    def build(self, **kwargs):
        world, task, runner, patcher = make(**kwargs)
        self.addCleanup(patcher.stop)
        return world, task, runner

    def run_ok(self, **kwargs):
        world, task, runner = self.build(**kwargs)
        result = runner.run()
        self.assertEqual(world.violations, [])
        return world, runner, result


# ---------------------------------------------------------------------------------------------- A. 次数
class CountTest(Base):
    def test_zero_ends_without_any_action(self):
        world, runner, result = self.run_ok(remaining=0)
        self.assertEqual(result, 0)
        self.assertEqual(world.kinds('click'), [])
        self.assertEqual(world.opened, [])

    def test_one_chance_runs_one_dokan_without_vote_or_wait(self):
        world, runner, result = self.run_ok(remaining=1, cards=[card('a')])
        self.assertEqual(world.opened, ['a'])
        self.assertEqual(world.kinds('vote_again'), [])
        self.assertEqual(result, 0)

    def test_two_chances_run_two_dokans(self):
        world, runner, result = self.run_ok(remaining=2, cards=[card('a'), card('b')])
        self.assertEqual(len(world.opened), 2)
        self.assertEqual(result, 0)

    def test_unknown_count_is_not_zero_and_not_two(self):
        world, task, runner = self.build(remaining=2, count_known=False)
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual(world.kinds('click'), [])
        self.assertEqual(world.opened, [])

    def test_final_count_unreadable_after_two_dokans_is_human_not_normal_exit(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], final_unreadable=True)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('最终剩余机会', str(ctx.exception))
        self.assertEqual(len(world.opened), 2)                  # 已完成的操作如实保留，没有谎称没执行
        self.assertEqual(world.violations, [])

    def test_final_count_unknown_writes_no_count_and_schedules_nothing(self):
        from tasks.Dokan.script_task import ScriptTask
        world, task, runner = self.build(remaining=1, cards=[card('a')], final_unreadable=True)
        conf = SimpleNamespace(
            dokan_config=SimpleNamespace(monday_to_thursday=False, welfare_mode=True),
            attack_count_config=Mock())
        entry = ScriptTask.__new__(ScriptTask)
        entry.config = SimpleNamespace(save=Mock(), model=SimpleNamespace(dokan=conf))
        entry.next_run = Mock()
        entry.goto_page = Mock()
        with patch('tasks.Dokan.script_task.WelfareDokan', return_value=runner),                 patch.object(ScriptTask, 'before_run'),                 self.assertRaises(RequestHumanTakeover):
            entry.run()
        conf.attack_count_config.set_attack_count.assert_not_called()      # 不写推算次数
        entry.next_run.assert_not_called()                                 # 不进入正常 next_run 收尾

    def test_final_zero_is_the_only_normal_finish(self):
        world, runner, result = self.run_ok(remaining=2, cards=[card('a'), card('b')])
        self.assertEqual(result, 0)

    def test_final_clearly_has_chances_is_reported_as_is_without_a_third_dokan(self):
        world, runner, result = self.run_ok(remaining=1, cards=[card('a'), card('b')], final_left=1)
        self.assertEqual(result, 1)                              # 不谎报用完
        self.assertEqual(len(world.opened), 1)                   # 也不再开下一馆

    def test_no_assumed_value_remains_in_the_source(self):
        import inspect
        src = inspect.getsource(WelfareDokan.run) + inspect.getsource(WelfareDokan._run)
        self.assertNotIn('assume', src)
        self.assertNotIn('remaining = count', src)

    def test_existing_dokan_at_start_is_not_taken_over(self):
        world, task, runner = self.build(remaining=1, start='map_found')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('进行中的道馆', str(ctx.exception))
        self.assertEqual(world.kinds('click'), [])
        self.assertEqual(world.kinds('app_stop'), [])

    def test_unknown_page_goes_to_human(self):
        world, task, runner = self.build(start='courtyard')
        with self.assertRaises(RequestHumanTakeover):
            runner.run()

    def test_handle_error_off_is_refused_before_any_action(self):
        world, task, runner = self.build(handle_error=False)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('HandleError', str(ctx.exception))
        self.assertEqual(world.events, [])


# ---------------------------------------------------------------------------------------------- A2. 我方道馆
class OwnDokanTest(Base):
    """福利入口接入我方建馆前置流程（D-02）：真实 `WelfareDokan._run` + 真实 `ScriptTask.ensure_dokan_created /
    creat_dokan`，只替换设备 / 识别 / 虚拟时钟。World 的建立入口图标按真实量得的「互相匹配分约 0.96」建模：
    默认阈值下两个图标同时命中，只有高阈值才分得开。"""

    def run_human(self, **kwargs):
        world, task, runner = self.build(**kwargs)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        return world, task, runner, str(ctx.exception)

    @staticmethod
    def count_clicks(world, key):
        return len([e for e in world.events if e == ('click', key)])

    def assertStopped(self, world, task, runner):
        """建馆检查失败：没有预设、没有找馆、没有开启对方道馆，也没有扣次数 / 排期。"""
        self.assertEqual(self.count_clicks(world, 'TEAM'), 0)
        self.assertEqual(self.count_clicks(world, 'PRESET'), 0)
        self.assertEqual(world.kinds('click_xy'), [])
        self.assertEqual(world.opened, [])
        self.assertEqual(runner.opened, 0)
        self.assertFalse(runner.own_dokan_checked)
        self.assertFalse(runner.preset_done)
        self.assertEqual(world.kinds('app_stop'), [])

    # --- 1：已建立
    def test_created_goes_straight_to_preset_without_the_create_flow(self):
        world, runner, result = self.run_ok(remaining=1, own='created')
        self.assertEqual(self.count_clicks(world, 'CREATE'), 0)
        self.assertEqual(self.count_clicks(world, 'HAVE'), 0)
        self.assertEqual(world.kinds('create_confirmed'), [])
        self.assertEqual(self.count_clicks(world, 'TEAM'), 1)
        self.assertEqual(world.opened, ['a'])
        self.assertTrue(runner.own_dokan_checked)

    # --- 2：未建立
    def test_uncreated_is_created_confirmed_closed_then_preset_then_search(self):
        world, runner, result = self.run_ok(remaining=1, own='uncreated')
        events = world.events
        order = [events.index(('click', 'CREATE')), events.index(('create_confirmed',)),
                 events.index(('click', 'INFO_CLOSE')), events.index(('own_created',)),
                 events.index(('click', 'TEAM')), events.index(('preset_confirmed',)),
                 next(i for i, e in enumerate(events) if e[:2] == ('click_xy', 'dokan_welfare_candidate'))]
        self.assertEqual(order, sorted(order))
        self.assertEqual(world.own, 'created')
        self.assertTrue(runner.own_dokan_checked)
        self.assertEqual(world.opened, ['a'])

    def test_create_dialog_arriving_late_within_the_wait_still_creates(self):
        world, runner, _ = self.run_ok(remaining=1, own='uncreated', create_mode='late', create_late=1.5)
        self.assertEqual(world.kinds('create_confirmed'), [('create_confirmed',)])
        self.assertEqual(self.count_clicks(world, 'CREATE'), 1)             # 没有因为晚到而重复点建立入口

    # --- 3：创建失败 / 确认无效 / 页面未知
    def test_click_without_a_dialog_is_not_treated_as_created(self):
        world, task, runner, message = self.run_human(remaining=1, own='uncreated', create_mode='no_dialog')
        self.assertEqual(self.count_clicks(world, 'CREATE'), 2)             # 有界：只点两次
        self.assertStopped(world, task, runner)
        self.assertEqual(world.kinds('own_created'), [])

    def test_confirm_that_does_nothing_is_bounded_and_stops(self):
        world, task, runner, message = self.run_human(remaining=1, own='uncreated', create_mode='ensure_dead')
        self.assertLessEqual(self.count_clicks(world, 'CREATE_ENSURE'), 3 * 5)
        self.assertLess(world.now, 120)
        self.assertStopped(world, task, runner)

    def test_info_window_that_cannot_be_closed_is_not_success(self):
        world, task, runner, message = self.run_human(remaining=1, own='uncreated', create_mode='info_stuck')
        self.assertLessEqual(self.count_clicks(world, 'INFO_CLOSE'), 4)
        self.assertStopped(world, task, runner)

    def test_strict_create_itself_returns_false_when_the_info_window_cannot_be_closed(self):
        # 直接测公共方法的返回值：不依赖福利侧随后的「回到找馆页」检查兜底
        world, task, runner = self.build(remaining=1, own='uncreated', create_mode='info_stuck')
        task.screenshot()
        self.assertFalse(task.ensure_dokan_created(strict=True))
        self.assertEqual(world.phase, 'create_info')

    def test_strict_create_itself_returns_false_for_a_dialog_that_never_opens_and_for_unreadable_states(self):
        for kwargs in (dict(own='uncreated', create_mode='no_dialog'), dict(own='ambiguous'), dict(own='absent')):
            with self.subTest(**kwargs):
                world, task, runner = self.build(remaining=1, **kwargs)
                task.screenshot()
                self.assertFalse(task.ensure_dokan_created(strict=True))

    def test_unknown_popup_after_confirming_is_not_success(self):
        world, task, runner, message = self.run_human(remaining=1, own='uncreated', create_mode='popup')
        self.assertStopped(world, task, runner)

    def test_unreadable_icon_state_stops_without_clicking_anything(self):
        for own in ('ambiguous', 'absent'):
            with self.subTest(own=own):
                world, task, runner, message = self.run_human(remaining=1, own=own)
                self.assertEqual(self.count_clicks(world, 'CREATE'), 0)
                self.assertEqual(self.count_clicks(world, 'HAVE'), 0)
                self.assertStopped(world, task, runner)
                self.assertLess(world.now, 30)

    def test_stop_message_never_claims_a_dokan_was_opened(self):
        world, task, runner, message = self.run_human(remaining=1, own='uncreated', create_mode='no_dialog')
        self.assertIn('我方道馆', message)
        self.assertNotIn('已开启', message)
        self.assertNotIn('已经开启', message)

    def test_not_back_on_the_find_page_after_creating_stops(self):
        world, task, runner = self.build(remaining=1, own='uncreated')
        with patch.object(WelfareDokan, '_map_state', side_effect=['finding', 'found']):   # 进入地图时 / 建完之后
            with self.assertRaises(RequestHumanTakeover) as ctx:
                runner.run()
        self.assertIn('没有回到找馆页', str(ctx.exception))
        self.assertFalse(runner.own_dokan_checked)
        self.assertEqual(self.count_clicks(world, 'TEAM'), 0)
        self.assertEqual(world.opened, [])

    # --- 4 / 5 / 6：前置判断先于建馆
    def test_dokan_in_progress_is_not_taken_over_and_no_create_is_attempted(self):
        world, task, runner, message = self.run_human(remaining=1, start='map_found', own='uncreated')
        self.assertIn('进行中的道馆', message)
        self.assertEqual(world.kinds('click'), [])

    def test_zero_chances_ends_normally_without_creating(self):
        world, runner, result = self.run_ok(remaining=0, own='uncreated')
        self.assertEqual(result, 0)
        self.assertEqual(world.kinds('click'), [])
        self.assertFalse(runner.own_dokan_checked)

    def test_unreadable_chances_do_not_create_and_do_not_assume_any(self):
        world, task, runner, message = self.run_human(remaining=2, count_known=False, own='uncreated')
        self.assertEqual(world.kinds('click'), [])
        self.assertFalse(runner.own_dokan_checked)

    # --- 7：调用顺序
    def test_call_order_is_state_then_chances_then_own_dokan_then_preset_then_search(self):
        world, task, runner = self.build(remaining=1, own='uncreated')
        calls = []
        seen = {}

        def spy(name):
            original = getattr(runner, name)

            def wrapper(*args, **kwargs):
                calls.append(name)
                seen.setdefault(name, (world.phase, world.own, world.remaining, runner.opened))
                return original(*args, **kwargs)
            setattr(runner, name, wrapper)

        for name in ('_map_state', '_read_count', '_ensure_own_dokan', '_apply_preset', '_find_and_open'):
            spy(name)
        runner.run()
        firsts = [name for i, name in enumerate(calls) if name not in calls[:i]]
        self.assertEqual(firsts, ['_map_state', '_read_count', '_ensure_own_dokan', '_apply_preset', '_find_and_open'])
        # 预设开始时：已回到找馆页、我方道馆已建立、没有扣次数、没有计入开启的馆
        self.assertEqual(seen['_apply_preset'], ('find', 'created', 1, 0))

    # --- 8：两馆
    def test_two_dokans_check_own_dokan_once_and_preset_once(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], own='uncreated')
        task.ensure_dokan_created = Mock(wraps=task.ensure_dokan_created)
        runner.run()
        task.ensure_dokan_created.assert_called_once_with(strict=True)
        self.assertEqual(world.kinds('create_confirmed'), [('create_confirmed',)])
        self.assertEqual(self.count_clicks(world, 'TEAM'), 1)
        self.assertEqual(len(world.opened), 2)

    # --- 9：状态不串
    def test_creating_own_dokan_does_not_touch_opened_chances_or_schedule(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], own='uncreated')
        before = task.config.dokan.attack_count_config.model_dump()
        seen = {}
        original = runner._ensure_own_dokan

        def spy():
            original()
            seen['after_create'] = (runner.opened, world.remaining, world.opened[:])
        runner._ensure_own_dokan = spy
        runner.run()
        self.assertEqual(seen['after_create'], (0, 2, []))            # 建馆后：没记 opened、没扣次数、没开对方馆
        self.assertEqual(task.config.dokan.attack_count_config.model_dump(), before)
        self.assertFalse(hasattr(task, 'next_run'))                  # 福利控制器自己不排期、不写成功

    def test_failed_create_leaves_every_counter_untouched(self):
        world, task, runner, message = self.run_human(remaining=2, own='uncreated', create_mode='no_dialog')
        self.assertEqual((runner.opened, world.remaining, world.opened), (0, 2, []))

    # --- 10：配置
    def test_user_config_is_not_rewritten_and_try_start_dokan_is_not_a_gate(self):
        for flag in (False, True):
            with self.subTest(try_start_dokan=flag):
                world, task, runner = self.build(remaining=1, own='uncreated')
                task.config.dokan.dokan_config.try_start_dokan = flag
                before = task.config.dokan.model_dump()
                runner.run()
                self.assertEqual(world.kinds('create_confirmed'), [('create_confirmed',)])   # 不被该开关阻止
                self.assertEqual(task.config.dokan.model_dump(), before)

    def test_checked_flag_is_never_set_by_a_failure_or_exception(self):
        world, task, runner = self.build(remaining=1, own='uncreated')
        with patch.object(FakeTask, '_ensure_dokan_created_strict', side_effect=GameStuckError('boom')):
            with self.assertRaises(GameStuckError):
                runner.run()
        self.assertFalse(runner.own_dokan_checked)
        self.assertEqual(world.opened, [])


class OrdinaryCreateCompatTest(Base):
    """普通模式的 `ensure_dokan_created()`（不带 strict）保持原行为；strict 只是福利模式用的更严判定。"""

    def task_for(self, **kwargs):
        world, task, runner = self.build(**kwargs)
        task.screenshot()
        return world, task

    @staticmethod
    def create_clicks(world):
        return len([e for e in world.events if e == ('click', 'CREATE')])

    def test_signature_defaults_keep_the_ordinary_behaviour(self):
        import inspect
        for method in (ScriptTask.ensure_dokan_created, ScriptTask.creat_dokan):
            self.assertIs(inspect.signature(method).parameters['strict'].default, False)

    def test_ordinary_uncreated_still_creates(self):
        world, task = self.task_for(own='uncreated')
        self.assertTrue(task.ensure_dokan_created())
        self.assertEqual(world.own, 'created')

    def test_ordinary_click_without_dialog_is_still_treated_as_created(self):
        world, task = self.task_for(own='uncreated', create_mode='no_dialog')
        self.assertTrue(task.ensure_dokan_created())                          # 原行为（不可靠，但普通模式保持）
        self.assertEqual(self.create_clicks(world), 2)
        self.assertEqual(world.own, 'uncreated')
        task.screenshot()
        self.assertFalse(task.ensure_dokan_created(strict=True))              # 同一画面 strict 不会当成已建立

    def test_ordinary_created_icon_is_still_clicked_twice_and_accepted(self):
        world, task = self.task_for(own='created')
        self.assertTrue(task.ensure_dokan_created())
        self.assertEqual(self.create_clicks(world), 2)

    def test_ordinary_unrecognised_marker_is_still_false_without_clicking(self):
        world, task = self.task_for(own='absent')
        self.assertFalse(task.ensure_dokan_created())
        self.assertEqual(world.kinds('click'), [])


class OwnDokanIconResourceTest(unittest.TestCase):
    """用真实截图 + 真实模板文件离线核对「已建立 / 未建立」两个图标的区分（不经过图像服务，直接 TM_CCOEFF_NORMED，
    与 `runtime._template_match_image` 同一算法）。样本只有 2026-10-27 / 28 两天各一张，覆盖面有限。"""

    FIXTURES = Path(__file__).parent / 'fixtures' / 'dokan_welfare'
    RES = Path(__file__).resolve().parents[1] / 'tasks' / 'Dokan' / 'res'

    def scores(self, sample):
        shot = cv2.imread(str(self.FIXTURES / sample))
        have = cv2.imread(str(self.RES / 'res_ryou_dokan_have_dokan.png'))
        create = cv2.imread(str(self.RES / 'res_ryou_dokan_create_dokan.png'))
        self.assertEqual(shot.shape, have.shape)
        self.assertEqual(shot.shape, create.shape)             # 样本即 roi_back 区域，单一位置
        return (float(cv2.matchTemplate(shot, have, cv2.TM_CCOEFF_NORMED).max()),
                float(cv2.matchTemplate(shot, create, cv2.TM_CCOEFF_NORMED).max()))

    def test_both_templates_hit_either_icon_at_the_default_threshold(self):
        have, create = self.scores('own_dokan_icon_created_oas1_20261027.png')
        self.assertGreater(create, DokanAssets.I_RYOU_DOKAN_CREATE_DOKAN.threshold)        # 默认阈值分不开
        have, create = self.scores('own_dokan_icon_uncreated_oas1_20261028.png')
        self.assertGreater(have, DokanAssets.I_RYOU_DOKAN_HAVE_DOKAN.threshold)

    def test_strict_threshold_separates_the_two_icons(self):
        threshold = dokan_script.OWN_DOKAN_MARKER_THRESHOLD
        have, create = self.scores('own_dokan_icon_created_oas1_20261027.png')
        self.assertGreater(have, threshold)
        self.assertLess(create, threshold)
        have, create = self.scores('own_dokan_icon_uncreated_oas1_20261028.png')
        self.assertGreater(create, threshold)
        self.assertLess(have, threshold)

    def test_both_markers_share_the_roi_the_samples_were_cut_from(self):
        self.assertEqual(tuple(DokanAssets.I_RYOU_DOKAN_HAVE_DOKAN.roi_back), (240, 600, 94, 90))
        self.assertEqual(tuple(DokanAssets.I_RYOU_DOKAN_CREATE_DOKAN.roi_back), (240, 600, 94, 90))


# ---------------------------------------------------------------------------------------------- B. 预设
class PresetTest(Base):
    def test_preset_once_before_first_search_and_not_for_second(self):
        world, runner, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')])
        confirmed = [i for i, e in enumerate(world.events) if e[0] == 'preset_confirmed']
        first_candidate = next(i for i, e in enumerate(world.events) if e[:2] == ('click_xy', 'dokan_welfare_candidate'))
        self.assertEqual(len(confirmed), 1)
        self.assertLess(confirmed[0], first_candidate)
        self.assertEqual(len([e for e in world.events if e[:2] == ('click', 'TEAM')]), 1)

    # D-06 之前这里有一条「没有确认框 → 转人工」的用例，固化的是旧业务口径；用户 2026-10-28 确认口径改为
    # 「此前已预设过时不弹确认框，实际点 2～4 次即视为预设操作完成」，旧用例由下面的 PresetFlowTest 取代。


class PresetFlowTest(Base):
    """福利预设：有确认框 / 无确认框两条路径。真实 `_apply_preset` / `_click_preset`，替换设备、识别和虚拟时钟；
    `FakeTask.appear_then_click` 用虚拟时钟模拟真实的 interval 限流（没到间隔 = 没有点击，返回 False）。"""

    def preset(self, randint=None, **kwargs):
        world, task, runner = self.build(remaining=1, **kwargs)
        if randint is not None:
            patcher = patch.object(welfare.random, 'randint', return_value=randint)
            patcher.start()
            self.addCleanup(patcher.stop)
        return world, task, runner

    @staticmethod
    def sent(world):
        return len([e for e in world.events if e == ('click', 'PRESET')])

    def assertNotDone(self, runner, world):
        self.assertFalse(runner.preset_done)
        self.assertEqual(world.opened, [])

    # --- 1：有确认框
    def test_confirm_dialog_is_confirmed_closed_and_preset_is_done(self):
        world, task, runner = self.preset(randint=3)
        runner._apply_preset()
        self.assertTrue(runner.preset_done)
        self.assertEqual(world.kinds('preset_confirmed'), [('preset_confirmed',)])
        self.assertEqual(self.sent(world), 1)                       # 弹出确认框后不再点预设
        self.assertEqual(world.phase, 'find')

    # --- 2：无确认框，目标 2 / 3 / 4
    def test_no_dialog_sends_exactly_the_drawn_number_of_clicks_then_goes_back(self):
        for target in (2, 3, 4):
            with self.subTest(target=target):
                world, task, runner = self.preset(randint=target, preset_mode='none')
                runner._apply_preset()
                self.assertTrue(runner.preset_done)
                self.assertEqual(self.sent(world), target)
                self.assertEqual(world.kinds('preset_confirmed'), [])
                self.assertEqual(world.phase, 'find')

    def test_no_dialog_clicks_respect_the_interval(self):
        world, task, runner = self.preset(randint=4, preset_mode='none')
        stamps = []
        original = world.click_key

        def spy(key):
            if key == 'PRESET':
                stamps.append(world.now)
            original(key)

        world.click_key = spy
        runner._apply_preset()
        self.assertEqual(len(stamps), 4)
        self.assertTrue(all(b - a >= welfare.PRESET_CLICK_INTERVAL for a, b in zip(stamps, stamps[1:])), stamps)

    def test_target_is_drawn_once_in_range_and_never_exceeds_four_clicks(self):
        draws = []
        real = welfare.random.randint

        def spy(a, b):
            value = real(a, b)
            draws.append(value)
            return value

        for _ in range(30):
            world, task, runner = self.build(remaining=1, preset_mode='none')
            with patch.object(welfare.random, 'randint', spy):
                runner._apply_preset()
            self.assertEqual(self.sent(world), draws[-1])
            self.assertIn(self.sent(world), (2, 3, 4))
        self.assertEqual(len(draws), 30)                            # 每次预设只抽一次，不是每轮重抽
        self.assertEqual(welfare.PRESET_NO_DIALOG_CLICKS, (2, 4))

    # --- 3：确认框延迟出现
    def test_late_dialog_is_confirmed_first_and_the_button_behind_it_is_not_clicked_again(self):
        for delay in (0.3, 1.0, 1.49):
            with self.subTest(delay=delay):
                world, task, runner = self.preset(randint=4, preset_mode='late', late_after=2, late_delay=delay)
                runner._apply_preset()
                self.assertTrue(runner.preset_done)
                self.assertEqual(self.sent(world), 2)
                self.assertEqual(world.kinds('preset_confirmed'), [('preset_confirmed',)])

    def test_dialog_after_the_last_click_is_still_caught_by_the_observation(self):
        world, task, runner = self.preset(randint=2, preset_mode='late', late_after=2, late_delay=1.2)
        runner._apply_preset()
        self.assertEqual(self.sent(world), 2)
        self.assertEqual(world.kinds('preset_confirmed'), [('preset_confirmed',)])

    # --- 4：限流
    def test_throttled_calls_are_not_counted_as_sent_clicks(self):
        world, task, runner = self.preset(randint=3, preset_mode='none', preset_throttle=5)
        runner._apply_preset()
        self.assertTrue(runner.preset_done)
        self.assertEqual(self.sent(world), 3)                       # 5 次限流调用没被当成点击

    def test_clicks_that_never_get_sent_stop_within_the_total_timeout(self):
        world, task, runner = self.preset(randint=2, preset_mode='none', preset_throttle=10 ** 6)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._apply_preset()
        self.assertIn('没有实际发出', str(ctx.exception))
        self.assertNotDone(runner, world)
        self.assertEqual(self.sent(world), 0)
        self.assertLessEqual(world.now, welfare.PRESET_TOTAL_TIMEOUT + 15)    # 有界

    # --- 5：按钮 / 页面异常
    def test_team_page_never_entered_is_human_and_no_preset_click(self):
        world, task, runner = self.preset(randint=2, preset_mode='none')
        original = world.click_key
        world.click_key = lambda key: world.log('click', key) if key == 'TEAM' else original(key)
        with self.assertRaises(RequestHumanTakeover):
            runner._apply_preset()
        self.assertNotDone(runner, world)
        self.assertEqual(self.sent(world), 0)

    def test_unknown_popup_after_a_click_is_human_not_a_no_dialog_success(self):
        world, task, runner = self.preset(randint=3, preset_mode='vanish')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._apply_preset()
        self.assertIn('识别不到', str(ctx.exception))
        self.assertNotDone(runner, world)
        self.assertEqual(self.sent(world), 1)                       # 页面都变了，不再继续点

    # --- 6：确认框持续存在
    def test_dialog_that_cannot_be_closed_is_a_bounded_failure(self):
        world, task, runner = self.preset(randint=3, preset_mode='stuck')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._apply_preset()
        self.assertIn('确认框没有消失', str(ctx.exception))
        self.assertNotDone(runner, world)
        self.assertEqual(self.sent(world), 1)
        self.assertLessEqual(len([e for e in world.events if e == ('click', 'UI_CONFIRM')]), 3)

    # --- 7：返回失败 / 异常
    def test_back_failure_does_not_set_done_on_either_route(self):
        for mode in ('dialog', 'none'):
            with self.subTest(mode=mode):
                world, task, runner = self.preset(randint=2, preset_mode=mode, back_blocked=True)
                with self.assertRaises(RequestHumanTakeover) as ctx:
                    runner._apply_preset()
                self.assertIn('没有回到找馆页', str(ctx.exception))
                self.assertFalse(runner.preset_done)

    def test_exception_during_the_preset_never_sets_done(self):
        world, task, runner = self.preset(randint=3, preset_mode='none')
        real = task.screenshot

        def shot():
            if world.phase == 'team' and world.preset_clicks >= 1:
                raise RuntimeError('device lost')
            real()

        task.screenshot = shot
        with self.assertRaises(RuntimeError):
            runner._apply_preset()
        self.assertFalse(runner.preset_done)

    # --- 8：第二馆不重复
    def test_preset_runs_once_for_the_first_dokan_only_on_the_no_dialog_route_too(self):
        world, runner, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')], preset_mode='none')
        self.assertIn(self.sent(world), (2, 3, 4))
        self.assertEqual(len([e for e in world.events if e[:2] == ('click', 'TEAM')]), 1)
        self.assertTrue(runner.preset_done)

    def test_full_run_on_the_no_dialog_route_reaches_the_search(self):
        world, runner, _ = self.run_ok(remaining=1, cards=[card('a', people=150)], preset_mode='none')
        self.assertEqual(world.opened, ['a'])
        first_candidate = next(i for i, e in enumerate(world.events) if e[:2] == ('click_xy', 'dokan_welfare_candidate'))
        last_preset = max(i for i, e in enumerate(world.events) if e == ('click', 'PRESET'))
        self.assertLess(last_preset, first_candidate)

    # --- 记录保护：本阶段不触发公共重复操作保护，也不清记录
    def test_preset_clicks_stay_below_the_public_guard_and_nothing_is_cleared(self):
        for target in (2, 3, 4):
            with self.subTest(target=target):
                world, task, runner = self.preset(randint=target, preset_mode='none', click_guard=True)
                task.device.guard.click_record_clear = lambda: self.fail('预设阶段不允许清记录')
                runner._apply_preset()
                self.assertTrue(runner.preset_done)
                self.assertEqual(self.sent(world), target)

    def test_no_dialog_is_not_human_any_more(self):
        world, task, runner = self.preset(randint=2, preset_mode='none')
        runner._apply_preset()                                      # 旧实现：8 秒内没出现确认框 → 转人工
        self.assertTrue(runner.preset_done)


# ---------------------------------------------------------------------------------------------- C. 找馆
class SearchTest(Base):
    def test_threshold_100_accepts_100_and_rejects_99(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('c99', people=99), card('c100', people=100)])
        self.assertEqual(world.checked, ['c99', 'c100'])
        self.assertEqual(world.opened, ['c100'])

    def test_checks_top_to_bottom_and_opens_first_match_not_best(self):
        cards = [card('low', people=50), card('ok1', people=120), card('ok2', people=400)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        self.assertEqual(world.checked, ['low', 'ok1'])
        self.assertEqual(world.opened, ['ok1'])

    def test_non_xin_cards_are_never_clicked(self):
        cards = [card('plain', xin=False, people=999), card('xin', people=150)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        self.assertEqual(world.checked, ['xin'])

    def test_unchallengeable_and_unreadable_are_skipped(self):
        cards = [card('busy', challengeable=False), card('blank', people=None), card('good', people=150)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        self.assertEqual(world.checked, ['busy', 'blank', 'good'])
        self.assertEqual(world.opened, ['good'])

    def test_detail_not_updated_yet_is_not_trusted(self):
        # B 的详情先显示残留的 999 再更新成 50：连续两次一致才采信，50 < 100 不开
        cards = [card('b', people=50, lag=1), card('ok', people=150)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        self.assertEqual(world.opened, ['ok'])

    def test_previous_detail_is_hidden_before_each_candidate_click(self):
        cards = [card('a', people=10), card('b', people=20), card('c', people=150)]
        world, _, _ = self.run_ok(remaining=1, cards=cards, hide_clicks=2)
        self.assertEqual(world.opened, ['c'])        # violations 为空：没有在详情未消失时点下一个候选

    def test_scrolls_and_checks_each_card_once_despite_overlap(self):
        cards = [card(f'c{i}', people=10) for i in range(8)] + [card('target', people=200)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        self.assertEqual(world.opened, ['target'])
        self.assertEqual(sorted(world.checked), sorted(set(world.checked)))      # 没有重复检查
        self.assertEqual(world.checked, [f'c{i}' for i in range(8)] + ['target'])
        self.assertGreaterEqual(len(world.kinds('swipe')), 2)

    def test_bottom_needs_consecutive_unchanged_swipes_then_refreshes(self):
        first = [card(f'a{i}', people=10) for i in range(6)]
        second = [card('b0', people=10), card('win', people=300)]
        world, _, _ = self.run_ok(remaining=1, cards=first, refreshes=[second])
        self.assertEqual(world.kinds('refreshed'), [('refreshed',)])
        self.assertEqual(world.opened, ['win'])
        # 到底之后恰好两次无效滑动才刷新
        swipes = [i for i, e in enumerate(world.events) if e == ('swipe',)]
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        trailing = [i for i in swipes if i < refresh]
        # 6 张卡：第一次滑动生效，之后连续两次无变化才算到底 → 恰好 3 次滑动后刷新
        self.assertEqual(len(trailing), 3)

    def test_one_lost_swipe_is_not_mistaken_for_the_bottom(self):
        cards = [card(f'c{i}', people=10) for i in range(8)] + [card('target', people=200)]
        world, _, _ = self.run_ok(remaining=1, cards=cards, lose_swipes=1)
        self.assertEqual(world.opened, ['target'])
        self.assertEqual(world.kinds('refreshed'), [])

    def test_changed_but_never_stable_is_human_and_never_counts_as_the_bottom(self):
        cards = [card(f'c{i}', people=10) for i in range(8)]
        world, task, runner = self.build(remaining=1, cards=cards, swipe_mode='animate')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('没有稳定', str(ctx.exception))
        self.assertEqual(world.kinds('refreshed'), [])           # 没有当作到底去刷新
        self.assertEqual(len(world.kinds('swipe')), 1)           # 重新观察不再滑动，有界退出
        self.assertEqual(world.opened, [])

    def test_late_settling_list_is_recognised_only_after_it_is_stable(self):
        cards = [card(f'c{i}', people=10) for i in range(8)] + [card('target', people=200)]
        world, _, _ = self.run_ok(remaining=1, cards=cards, swipe_mode='late')
        self.assertEqual(world.opened, ['target'])
        self.assertEqual(world.kinds('refreshed'), [])
        # 滑动之后的第一次候选点击必须晚于列表稳定（噪声截图都消耗完）
        self.assertEqual(world.violations, [])

    def test_stable_without_change_is_static_and_changed_then_stable_is_moved(self):
        world, task, runner = self.build(remaining=1, cards=[card('a', people=1), card('b', people=1)])
        runner._hide_popup = lambda: None
        task.screenshot()
        self.assertEqual(runner._swipe_list(), 'static')         # 只有 2 张卡，列表本来就在底
        world2, task2, runner2 = self.build(remaining=1, cards=[card(f'c{i}', people=1) for i in range(8)])
        runner2._hide_popup = lambda: None
        task2.screenshot()
        self.assertEqual(runner2._swipe_list(), 'moved')

    def test_screenshot_error_during_swipe_is_not_counted_as_the_bottom(self):
        cards = [card(f'c{i}', people=10) for i in range(8)]
        world, task, runner = self.build(remaining=1, cards=cards)
        real = task.screenshot
        state = {'swiped': False}
        original_swipe = task.swipe

        def swipe(rule, interval=None):
            state['swiped'] = True
            return original_swipe(rule, interval)

        def shot():
            if state['swiped']:
                raise RuntimeError('device lost')
            real()

        task.swipe, task.screenshot = swipe, shot
        with self.assertRaises(RuntimeError):
            runner.run()
        self.assertEqual(world.kinds('refreshed'), [])

    def test_no_refresh_cap_and_no_fallback_selection(self):
        # 旧 find_dokan 刷新 7 次后会随机选一个；福利模式要继续刷到有达标的
        refreshes = [[card(f'r{i}', people=99)] for i in range(12)] + [[card('late', people=100)]]
        world, _, _ = self.run_ok(remaining=1, cards=[card('start', people=1)], refreshes=refreshes)
        self.assertEqual(len(world.kinds('refreshed')), 13)
        self.assertEqual(world.opened, ['late'])
        self.assertNotIn('r11', world.opened)

    def test_threshold_is_never_lowered(self):
        world, task, runner = self.build(remaining=1, cards=[card('a', people=99)], refreshes=[[card('b', people=99)]] * 3)
        # 达不到门槛的列表无限刷新：只会被刷新弹窗出不来的「游戏限制」终止，而不是降低条件
        calls = {'n': 0}
        original = world.click_key

        def limited(key):
            if key == 'REFRESH':
                calls['n'] += 1
                if calls['n'] > 2:
                    world.refresh_blocked = True
            original(key)

        world.click_key = limited
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('刷新', str(ctx.exception))
        self.assertEqual(world.opened, [])

    def test_refresh_dialog_missing_stops_instead_of_spamming(self):
        world, task, runner = self.build(remaining=1, cards=[card('a', people=1)], refresh_blocked=True)
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual(len([e for e in world.events if e == ('click', 'REFRESH')]), welfare.REFRESH_TRIES)

    def test_swipe_goes_through_task_swipe_not_the_device(self):
        world, task, runner = self.build(remaining=1, cards=[card(f'c{i}', people=1) for i in range(5)] + [card('w', people=500)])
        self.assertFalse(hasattr(task.device, 'swipe'))
        runner.run()
        self.assertGreaterEqual(len(world.kinds('swipe')), 1)


# ---------------------------------------------------------------------------------------------- C2. 滑动是否真正推进
# 图像来源：FIXTURE 是 2026-10-28 oas1 报错截图（log/error/oas1_1793191242911，GameTooManyClickError 现场）
# 里 LIST_BOX 的原始裁剪（两张报错截图在 LIST_BOX 内逐像素相同）。滚动 / 回弹 / 角标动画是**在这张真实
# 列表图上合成**的帧序列，不是真机录下来的中间帧；角标 / 徽记位置是按截图目测的近似值。
FIXTURE = Path(__file__).parent / 'fixtures' / 'dokan_welfare' / 'list_box_oas1_20261028_204042.png'
BADGES = [(1177, 27 + 145 * i, 40, 36) for i in range(4)]         # 卡片右上角的蓝色「升」角标（近似）
EMBLEMS = [(1122, 30 + 145 * i, 80, 80) for i in range(4)]        # 圆形徽记（近似）


def real_list_frame():
    x1, y1, x2, y2 = welfare.LIST_BOX
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    crop = cv2.imread(str(FIXTURE))
    assert crop is not None and crop.shape[:2] == (y2 - y1, x2 - x1), FIXTURE
    canvas[y1:y2, x1:x2] = crop
    return canvas


def scrolled(frame, dy):
    """合成：列表内容整体上移 dy 像素，底部补最后一行（滚动 / 回弹中的一帧）。"""
    x1, y1, x2, y2 = welfare.LIST_BOX
    out = frame.copy()
    if dy:
        region = frame[y1:y2, x1:x2]
        out[y1:y2 - dy, x1:x2] = region[dy:]
        out[y2 - dy:y2, x1:x2] = region[-1:]
    return out


def glint(frame, boxes, seed, amp=80):
    """合成：只在给定框里叠随机亮度（角标 / 闪光动画），其余像素不动。"""
    rng = np.random.RandomState(seed)
    out = frame.copy()
    for x, y, w, h in boxes:
        patch = out[y:y + h, x:x + w].astype(np.int16) + rng.randint(-amp, amp, (h, w, 3))
        out[y:y + h, x:x + w] = np.clip(patch, 0, 255).astype(np.uint8)
    return out


def frame_diff(a, b):
    from module.atom.frame_state import frame_difference
    return frame_difference(a, b, roi=welfare.LIST_BOX)


class Screen:
    """按「当前画面」逐次构造滑动脚本：每一项是一次实际发出的滑动之后截到的帧序列。"""

    def __init__(self):
        self.base = real_list_frame()
        self.cur = self.base
        self.items = []

    def static(self):
        self.items.append(([self.cur], 0))
        return self

    def moved(self, dy, advance=2, via=()):
        self.cur = scrolled(self.cur, dy)
        self.items.append(([*via, self.cur], advance))
        return self

    def raw(self, frames, advance=0):
        self.items.append((frames, advance))
        return self


class SwipeProgressTest(Base):
    """`_swipe_list` 只认「最终稳定的列表相对滑动前真的推进了」，不认过程中锁存的 changed。"""

    def build_screen(self, screen, cards=None, **kwargs):
        # 非「鑫」卡片：不产生候选，指纹去重不会干扰（合成帧里各槽位的指纹本来就不对应具体卡片）
        cards = cards if cards is not None else [card('a', xin=False), card('b', xin=False)]
        return self.build(remaining=1, cards=cards, swipe_script=screen.items, base_frame=screen.base, **kwargs)

    def swipe_once(self, screen, **kwargs):
        world, task, runner = self.build_screen(screen, **kwargs)
        runner._hide_popup = lambda: None
        task.screenshot()
        return world, runner, runner._swipe_list()

    # --- 1 / 2 / 11：推进 vs 回弹
    def test_content_changes_and_settles_is_moved(self):
        screen = Screen()
        _, _, verdict = self.swipe_once(screen.moved(148, via=[scrolled(screen.base, 30), scrolled(screen.base, 90)]))
        self.assertEqual(verdict, 'moved')

    def test_rebound_back_to_the_original_position_is_static(self):
        screen = Screen()
        peak = [scrolled(screen.base, dy) for dy in (30, 70, 90, 60, 20)]
        _, _, verdict = self.swipe_once(screen.raw(peak + [screen.base]))
        self.assertEqual(verdict, 'static')

    def test_rebound_that_pauses_stably_off_position_before_returning_is_static(self):
        # 回弹到一半停了几帧（过程中「稳定」过），随后才回到原位：必须看最终落点，不能在中途那次稳定就判推进
        screen = Screen()
        pause = [scrolled(screen.base, 30)] * 3
        _, _, verdict = self.swipe_once(screen.raw(pause + [scrolled(screen.base, 12), screen.base]))
        self.assertEqual(verdict, 'static')

    def test_pause_then_continues_to_scroll_is_judged_by_the_final_position(self):
        screen = Screen()
        pause = [scrolled(screen.base, 30)] * 3
        _, _, verdict = self.swipe_once(screen.raw(pause + [scrolled(screen.base, 75), scrolled(screen.base, 120)], advance=2))
        self.assertEqual(verdict, 'moved')

    # --- 5：只有动画
    def test_badge_animation_only_is_not_progress(self):
        screen = Screen()
        flash = glint(screen.base, BADGES, seed=1)            # 角标整体闪成另一个样子并保持：占列表约 5%
        _, _, verdict = self.swipe_once(screen.raw([flash]))
        self.assertEqual(verdict, 'static')
        self.assertGreaterEqual(frame_diff(screen.base, flash), 0.02)       # 旧的 0.02「变化」线会把它当推进

    def test_tiny_drifting_sparkles_are_not_progress(self):
        screen = Screen()
        sparkles = [glint(screen.base, [(1190 + 3 * i, 60 + 145 * j, 6, 6) for j in range(4)], seed=i, amp=70)
                    for i in range(1, 4)]
        _, _, verdict = self.swipe_once(screen.raw(sparkles))
        self.assertEqual(verdict, 'static')

    def test_even_heavy_badge_and_emblem_animation_stays_below_the_progress_line(self):
        base = real_list_frame()
        coverage, _ = welfare.list_row_coverage(base, glint(base, BADGES + EMBLEMS, seed=2))
        self.assertLess(coverage, welfare.LIST_MOVED_ROW_COVERAGE)

    # --- 6：小幅滚动不能漏
    def test_small_scrolls_are_still_progress(self):
        base = real_list_frame()
        for dy in (1, 2, 3, 6, 12):
            with self.subTest(dy=dy):
                coverage, _ = welfare.list_row_coverage(base, scrolled(base, dy))
                self.assertGreaterEqual(coverage, welfare.LIST_MOVED_ROW_COVERAGE)
        _, _, verdict = self.swipe_once(Screen().moved(3))
        self.assertEqual(verdict, 'moved')

    def test_small_scroll_under_badge_animation_is_still_progress(self):
        base = real_list_frame()
        coverage, _ = welfare.list_row_coverage(base, glint(scrolled(base, 3), BADGES, seed=3))
        self.assertGreaterEqual(coverage, welfare.LIST_MOVED_ROW_COVERAGE)

    def test_identical_frames_have_no_row_coverage(self):
        base = real_list_frame()
        self.assertEqual(welfare.list_row_coverage(base, base.copy()), (0.0, 0.0))

    def test_baseline_is_a_private_copy_not_the_live_image_buffer(self):
        # 设备层复用同一块图像缓冲时，滑动后「基准」不能跟着变：缓冲被就地改写成滑动后的画面，仍要判成推进
        screen = Screen()
        world, task, runner = self.build_screen(screen.raw([scrolled(screen.base, 148)], advance=2))
        runner._hide_popup = lambda: None
        buffer = screen.base.copy()

        def shot():
            buffer[:] = world.snapshot()
            task.device.image = buffer

        task.screenshot = shot
        shot()
        self.assertEqual(runner._swipe_list(), 'moved')

    # --- 3 / 4：连续两次 static 才到底
    def test_two_consecutive_static_swipes_end_the_batch_and_hand_over_to_refresh(self):
        world, task, runner = self.build_screen(Screen().static().static(), refreshes=[[card('win', people=300)]])
        runner.run()
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        self.assertEqual(len([e for e in world.events[:refresh] if e == ('swipe',)]), 2)
        self.assertEqual(world.kinds('refreshed'), [('refreshed',)])
        self.assertEqual(world.opened, ['win'])

    def test_a_rebound_swipe_counts_as_static_not_as_progress(self):
        # 第一次滑动是回弹（static），第二次明确没动（static）：两次连续 static 就到底；旧实现会把回弹当推进而多滑
        screen = Screen()
        screen.raw([scrolled(screen.base, 60), scrolled(screen.base, 30), screen.base]).static()
        world, task, runner = self.build_screen(screen, refreshes=[[card('win', people=300)]])
        runner.run()
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        self.assertEqual(len([e for e in world.events[:refresh] if e == ('swipe',)]), 2)

    def test_static_then_a_real_advance_clears_the_streak(self):
        cards = [card(f'c{i}', xin=False) for i in range(9)] + [card('target', people=200)]
        screen = Screen()
        for _ in range(3):
            screen.static().moved(100, advance=2)
        world, task, runner = self.build_screen(screen, cards=cards)
        runner.run()
        self.assertEqual(world.kinds('refreshed'), [])         # static 不连续，所以从没到底
        self.assertEqual(world.opened, ['target'])
        self.assertEqual(len(world.kinds('swipe')), 6)

    # --- 7：一直不稳定
    def test_never_settling_frames_are_human_not_bottom_and_do_not_swipe_again(self):
        screen = Screen()
        counter = {'n': 0}

        def churn():
            counter['n'] += 1
            return glint(screen.base, EMBLEMS, seed=1000 + counter['n'])

        world, task, runner = self.build_screen(screen.raw([churn]))
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('没有稳定', str(ctx.exception))
        self.assertEqual(len(world.kinds('swipe')), 1)
        self.assertEqual(world.kinds('refreshed'), [])
        self.assertLess(counter['n'], 200)                      # 有界

    # --- 8：没发出
    def test_unsent_swipes_are_not_counted_as_the_bottom(self):
        world, task, runner = self.build_screen(
            Screen().static().static(), refreshes=[[card('win', people=300)]], unsent_swipes=2)
        runner.run()
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        before = world.events[:refresh]
        self.assertEqual(len([e for e in before if e == ('swipe_not_sent',)]), 2)
        self.assertEqual(len([e for e in before if e == ('swipe',)]), 2)     # 到底仍要两次「实际发出」的 static

    def test_swipe_never_sent_stops_after_a_few_tries_without_bottom_or_refresh(self):
        world, task, runner = self.build_screen(Screen(), unsent_swipes=10 ** 6)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('没有发出', str(ctx.exception))
        self.assertEqual(len(world.kinds('swipe_not_sent')), welfare.SWIPE_SEND_TRIES)
        self.assertEqual(world.kinds('swipe'), [])
        self.assertEqual(world.kinds('refreshed'), [])

    def test_unsent_swipe_is_neither_moved_nor_static(self):
        world, task, runner = self.build_screen(Screen(), unsent_swipes=1)
        runner._hide_popup = lambda: None
        task.screenshot()
        self.assertEqual(runner._swipe_list(), 'not_sent')

    # --- 9：异常原样传播（含滑动稳定之后的最终落点确认阶段）
    def test_screenshot_error_at_any_point_after_the_swipe_propagates(self):
        for fail_at in (1, 3, 4, 6):
            with self.subTest(fail_at=fail_at):
                world, task, runner = self.build_screen(Screen().moved(120))
                real = task.screenshot
                state = {'swiped': False, 'shots': 0}
                original_swipe = task.swipe

                def swipe(rule, interval=None, _o=original_swipe, _s=state):
                    _s['swiped'] = True
                    return _o(rule, interval)

                def shot(_r=real, _s=state, _n=fail_at):
                    if _s['swiped']:
                        _s['shots'] += 1
                        if _s['shots'] == _n:
                            raise RuntimeError('device lost')
                    _r()

                task.swipe, task.screenshot = swipe, shot
                runner._hide_popup = lambda: None
                real()
                with self.assertRaises(RuntimeError):
                    runner._swipe_list()
                self.assertEqual(world.kinds('refreshed'), [])

    # --- 10：当前屏没有「鑫」也要继续翻页
    def test_screen_without_xin_still_pages_on_when_the_list_advances(self):
        cards = [card(f'p{i}', xin=False) for i in range(4)] + [card('target', people=200), card('pad', xin=False)]
        world, task, runner = self.build_screen(Screen().moved(120, advance=2), cards=cards)
        runner.run()
        self.assertEqual(world.checked, ['target'])
        self.assertEqual(world.opened, ['target'])
        self.assertEqual(world.kinds('refreshed'), [])


# ---------------------------------------------------------------------------------------------- C3. 有效翻页与重复操作保护
SWIPE_NAME = DokanAssets.S_DOKAN_WELFARE_LIST_UP.name


class SwipeRecordTest(Base):
    """D-04：公共 `Device.click_record`（deque 15、同名 >= 10 抛 GameTooManyClickError）在「滑动发出前」就写入并检查，
    所以连续有效推进时必须在每次确认 moved 之后只移除福利滑动自己的记录。

    这里的设备桩（`RecordGuard`）直接使用真实 `Device.handle_control_check` / `click_record_check` /
    `click_record_remove`，不 mock 公共保护。
    """

    def build_guarded(self, screen=None, cards=None, **kwargs):
        if screen is not None:
            kwargs.update(swipe_script=screen.items, base_frame=screen.base)
        cards = cards if cards is not None else [card(f'c{i}', xin=False) for i in range(30)]
        return self.build(remaining=1, cards=cards, click_guard=True, **kwargs)

    @staticmethod
    def kinds_of(world, kind):
        return [e for e in world.events if e[0] == kind]

    def swipe_once(self, world, task, runner):
        runner._hide_popup = lambda: None
        task.screenshot()
        return runner._swipe_list()

    # --- 1：连续真实推进超过 10 次
    def test_more_than_ten_real_advances_do_not_trip_the_public_guard(self):
        world, task, runner = self.build_guarded(refreshes=[[card('win', people=300)]])
        runner.run()
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        swipes_before_bottom = len([e for e in world.events[:refresh] if e == ('swipe',)])
        self.assertEqual(swipes_before_bottom, 15)                # 13 次推进 + 连续 2 次 static
        self.assertEqual(world.opened, ['win'])
        self.assertEqual(world.violations, [])

    def test_the_public_guard_really_trips_at_the_tenth_unreleased_swipe_record(self):
        # 不清记录时，同一份真实检查逻辑在第 10 次滑动「发出前」就抛异常：证明保护是真实经过的
        world, task, runner = self.build_guarded()
        guard = task.device.guard
        for _ in range(9):
            guard.handle_control_check(SWIPE_NAME)
        with self.assertRaises(GameTooManyClickError):
            guard.handle_control_check(SWIPE_NAME)

    def test_record_is_written_and_checked_before_the_swipe_and_removed_only_after_moved(self):
        world, task, runner = self.build_guarded()
        self.assertEqual(self.swipe_once(world, task, runner), 'moved')
        trail = [e for e in world.events if e[0] in ('record_add', 'swipe', 'record_remove')]
        self.assertEqual(trail, [('record_add', SWIPE_NAME), ('swipe',), ('record_remove', SWIPE_NAME, 1)])
        self.assertEqual(task.device.guard.count(SWIPE_NAME), 0)

    def test_every_advance_in_a_long_run_releases_exactly_the_swipe_records(self):
        world, task, runner = self.build_guarded(refreshes=[[card('win', people=300)]])
        runner.run()
        removes = self.kinds_of(world, 'record_remove')
        self.assertEqual({e[1] for e in removes}, {SWIPE_NAME})
        self.assertEqual([e[2] for e in removes], [1] * 13)       # 13 次推进，每次移除当时唯一的一条

    # --- 2：只清福利滑动自己的记录
    def test_only_the_welfare_swipe_name_is_removed_and_other_history_is_kept(self):
        world, task, runner = self.build_guarded(cards=[card(f'c{i}', xin=False) for i in range(8)])
        guard = task.device.guard
        for name in ('dokan_welfare_candidate', 'dokan_cancel_select_dokan', SWIPE_NAME, 'refresh', SWIPE_NAME):
            guard.click_record.append(name)
        self.assertEqual(self.swipe_once(world, task, runner), 'moved')
        self.assertEqual(list(guard.click_record), ['dokan_welfare_candidate', 'dokan_cancel_select_dokan', 'refresh'])
        self.assertEqual(self.kinds_of(world, 'record_remove'), [('record_remove', SWIPE_NAME, 3)])

    # --- 3：到底
    def test_bottom_keeps_both_static_records_and_hands_over_to_refresh(self):
        world, task, runner = self.build_guarded(
            cards=[card(f'c{i}', xin=False) for i in range(6)], refreshes=[[card('win', people=300)]])
        runner.run()
        self.assertEqual(len(self.kinds_of(world, 'record_remove')), 1)       # 只有那一次推进
        self.assertEqual(task.device.guard.count(SWIPE_NAME), 2)              # 两次 static 的记录原样保留
        self.assertEqual(world.kinds('refreshed'), [('refreshed',)])
        self.assertEqual(world.opened, ['win'])

    def test_static_swipe_releases_nothing(self):
        world, task, runner = self.build_guarded(cards=[card('a', xin=False), card('b', xin=False)])
        self.assertEqual(self.swipe_once(world, task, runner), 'static')
        self.assertEqual(self.kinds_of(world, 'record_remove'), [])
        self.assertEqual(task.device.guard.count(SWIPE_NAME), 1)

    # --- 4：没发出
    def test_unsent_swipe_writes_no_record_and_releases_nothing(self):
        world, task, runner = self.build_guarded(unsent_swipes=10 ** 6)
        task.device.guard.click_record.append(SWIPE_NAME)
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual([e for e in self.kinds_of(world, 'record_add') if e[1] == SWIPE_NAME], [])   # 没发出的滑动不写滑动记录
        self.assertEqual(self.kinds_of(world, 'record_remove'), [])
        self.assertEqual(len(world.kinds('swipe_not_sent')), welfare.SWIPE_SEND_TRIES)
        self.assertEqual(task.device.guard.count(SWIPE_NAME), 1)

    # --- 5：不稳定 / 异常
    def test_unstable_page_releases_nothing_and_stays_bounded(self):
        screen = Screen()
        counter = {'n': 0}

        def churn():
            counter['n'] += 1
            return glint(screen.base, EMBLEMS, seed=3000 + counter['n'])

        world, task, runner = self.build_guarded(screen.raw([churn]), cards=[card('a', xin=False)])
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual(self.kinds_of(world, 'record_remove'), [])
        self.assertEqual(task.device.guard.count(SWIPE_NAME), 1)
        self.assertEqual(len(world.kinds('swipe')), 1)
        self.assertLess(counter['n'], 200)

    def test_screenshot_error_after_the_swipe_releases_nothing_and_propagates(self):
        for fail_at in (1, 4, 6):
            with self.subTest(fail_at=fail_at):
                world, task, runner = self.build_guarded(Screen().moved(120))
                real, state = task.screenshot, {'swiped': False, 'shots': 0}
                original = task.swipe

                def swipe(rule, interval=None, _o=original, _s=state):
                    _s['swiped'] = True
                    return _o(rule, interval)

                def shot(_r=real, _s=state, _n=fail_at):
                    if _s['swiped']:
                        _s['shots'] += 1
                        if _s['shots'] == _n:
                            raise RuntimeError('device lost')
                    _r()

                task.swipe, task.screenshot = swipe, shot
                runner._hide_popup = lambda: None
                real()
                with self.assertRaises(RuntimeError):
                    runner._swipe_list()
                self.assertEqual(self.kinds_of(world, 'record_remove'), [])
                self.assertEqual(task.device.guard.count(SWIPE_NAME), 1)

    # --- 6：持续无有效进展不能靠清记录绕过
    def test_batches_without_progress_never_release_their_static_swipe_records_and_stay_bounded(self):
        # 每批都是短列表：只有 static，没有任何推进 → 滑动记录一次也不清，每批只滑固定的 2 次。
        # 原先这条用例断言「公共保护最终会终止无限刷新」：那是因为替身没有记录刷新点击 / 确认点击，只有滑动记录
        # 在累计。真实 `Device` 里每轮还有刷新和确认的点击记录，同名记录占不到 10、两个按钮也各不到 6，
        # 而「业务上不设刷新次数上限」本来就允许无限多轮（D-09），所以这里不再靠公共保护终止它，
        # 只固定：static 的滑动记录不被清、每批滑动次数有界；单次刷新的操作有界另见 RefreshClosureTest。
        refreshes = [[card(f'r{i}', xin=False)] for i in range(8)] + [[card('hit', people=150)]]
        world, task, runner = self.build_guarded(cards=[card('a', xin=False)], refreshes=refreshes)
        runner.run()
        self.assertEqual(world.opened, ['hit'])
        self.assertEqual([e for e in self.kinds_of(world, 'record_remove') if e[1] == SWIPE_NAME], [])
        self.assertEqual(len(world.kinds('swipe')), 2 * 9)           # 9 个没有合格馆的批次，每批恰好 2 次 static 滑动
        self.assertEqual(len(world.kinds('refreshed')), 9)

    # --- 7：公共保护默认行为不变
    def test_public_guard_defaults_are_unchanged(self):
        world, task, runner = self.build_guarded()
        guard = task.device.guard
        for _ in range(9):
            guard.handle_control_check('same_button')
        with self.assertRaises(GameTooManyClickError):
            guard.handle_control_check('same_button')
        guard.click_record_clear()
        for i in range(6):
            guard.handle_control_check('a')
            if i < 5:
                guard.handle_control_check('b')
        with self.assertRaises(GameTooManyClickError):
            guard.handle_control_check('b')

    def test_welfare_code_never_clears_or_removes_anything_but_its_own_swipe_name(self):
        world, task, runner = self.build_guarded(refreshes=[[card('win', people=300)]])
        task.device.guard.click_record_clear = lambda: self.fail('福利流程不允许清空整个记录')
        runner.run()
        self.assertEqual({e[1] for e in self.kinds_of(world, 'record_remove')}, {SWIPE_NAME})

    def test_released_name_is_the_exact_string_the_real_swipe_records(self):
        # 真实 BaseTask.swipe → swipe_trajectory(control_name=swipe.name) → Device 以 str(name) 记录；
        # click_record_remove 按 str(button) 匹配，所以必须传名字字符串（RuleSwipe 没有 __str__，传对象会匹配不到）
        self.assertEqual(SWIPE_NAME, 'dokan_welfare_list_up')
        world, task, runner = self.build_guarded()
        self.assertEqual(task.S_DOKAN_WELFARE_LIST_UP.name, SWIPE_NAME)
        self.assertNotEqual(str(DokanAssets.S_DOKAN_WELFARE_LIST_UP), SWIPE_NAME)

    # --- 8：D-03 回归（带真实记录保护）
    def test_rebound_and_icon_animation_stay_static_and_keep_their_records(self):
        base = real_list_frame()
        for label, frames in (
            ('rebound', [scrolled(base, 30), scrolled(base, 70), scrolled(base, 20), base]),
            ('badge animation', [glint(base, BADGES, seed=1)]),
        ):
            with self.subTest(label):
                screen = Screen()
                world, task, runner = self.build_guarded(screen.raw(frames), cards=[card('a', xin=False)])
                self.assertEqual(self.swipe_once(world, task, runner), 'static')
                self.assertEqual(self.kinds_of(world, 'record_remove'), [])
                self.assertEqual(task.device.guard.count(SWIPE_NAME), 1)

    def test_small_real_advance_is_moved_and_releases_the_record(self):
        world, task, runner = self.build_guarded(Screen().moved(3), cards=[card('a', xin=False)])
        self.assertEqual(self.swipe_once(world, task, runner), 'moved')
        self.assertEqual(self.kinds_of(world, 'record_remove'), [('record_remove', SWIPE_NAME, 1)])

    def test_scripted_long_list_pages_on_then_reaches_the_bottom_and_refreshes(self):
        screen = Screen()
        for k in range(13):
            screen.raw([scrolled(screen.base, 30 if k % 2 == 0 else 90)], advance=2)     # 相邻两次画面不同：真实推进
        last = scrolled(screen.base, 30)                       # 第 13 次推进后停在这一帧，两次 static 都保持它
        screen.raw([last]).raw([last])
        world, task, runner = self.build_guarded(screen, refreshes=[[card('win', people=300)]])
        runner.run()
        refresh = next(i for i, e in enumerate(world.events) if e == ('click', 'REFRESH'))
        self.assertEqual(len([e for e in world.events[:refresh] if e == ('swipe',)]), 15)
        self.assertEqual(len(self.kinds_of(world, 'record_remove')), 13)
        self.assertEqual(world.opened, ['win'])


class SwipeResourceTest(unittest.TestCase):
    def test_welfare_swipe_is_inside_the_right_list_and_vertical_up(self):
        rule = DokanAssets.S_DOKAN_WELFARE_LIST_UP
        self.assertIsInstance(rule, RuleSwipe)
        x1, y1, x2, y2 = welfare.LIST_BOX
        for roi in (rule.roi_front, rule.roi_back):
            x, y, w, h = roi
            self.assertGreaterEqual(x, x1)
            self.assertLessEqual(x + w, x2)
        self.assertLess(rule.roi_back[1], rule.roi_front[1])
        for _ in range(100):
            sx, sy, ex, ey = rule.sample_endpoints()
            self.assertTrue(x1 <= sx <= x2 and x1 <= ex <= x2)
            self.assertTrue(ey < sy)

    def test_base_task_swipe_uses_the_trajectory_entry(self):
        from tasks.Dokan.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.interval_timer = {}
        task.config = SimpleNamespace(script=SimpleNamespace(device=SimpleNamespace(control_method='minitouch')))
        task.device = Mock()
        self.assertTrue(task.swipe(DokanAssets.S_DOKAN_WELFARE_LIST_UP))
        task.device.swipe_trajectory.assert_called_once()
        self.assertEqual(task.device.swipe_trajectory.call_args.kwargs['control_name'], 'dokan_welfare_list_up')
        task.device.swipe.assert_not_called()

    def test_non_minitouch_falls_back_to_the_endpoint_swipe(self):
        from tasks.Dokan.script_task import ScriptTask
        task = ScriptTask.__new__(ScriptTask)
        task.interval_timer = {}
        task.config = SimpleNamespace(script=SimpleNamespace(device=SimpleNamespace(control_method='ADB')))
        task.device = Mock()
        task.swipe(DokanAssets.S_DOKAN_WELFARE_LIST_UP)
        task.device.swipe.assert_called_once()
        task.device.swipe_trajectory.assert_not_called()

    def test_return_marker_search_area_excludes_the_bottom_banner(self):
        x, y, w, h = DokanAssets.I_DOKAN_AGAIN_ENTER.roi_back
        banner = (527, 640, 156, 30)          # 「道馆突破集结中」横幅（整屏截图量得）
        self.assertLess(y + h, banner[1])
        fx, fy, fw, fh = DokanAssets.I_DOKAN_AGAIN_ENTER.roi_front
        self.assertTrue(x <= fx and y <= fy and fx + fw <= x + w and fy + fh <= y + h)

    def test_fingerprint_is_position_independent_and_distinguishes_cards(self):
        image_a = np.zeros((720, 1280, 3), np.uint8)
        image_b = np.zeros((720, 1280, 3), np.uint8)
        image_a[15:158, 1075:1245] = texture(1, (143, 170, 3))
        image_b[305:448, 1075:1245] = texture(1, (143, 170, 3))
        fa = card_fingerprint(image_a, (1153, 53, 19, 34))
        fb = card_fingerprint(image_b, (1153, 343, 19, 34))
        self.assertTrue(same_card(fa, fb))
        image_b[305:448, 1075:1245] = texture(2, (143, 170, 3))
        self.assertFalse(same_card(fa, card_fingerprint(image_b, (1153, 343, 19, 34))))
        self.assertIsNone(card_fingerprint(image_a, (1153, 560, 19, 34)))     # 被列表下沿裁切


# ---------------------------------------------------------------------------------------------- C2. 刷新闭环 / 候选身份 / 候选记录（D-09 / D-08）
CANDIDATE_NAME = 'dokan_welfare_candidate'
CANCEL_NAME = DokanAssets.C_DOKAN_CANCEL_SELECT_DOKAN.name
DOWN_NAME = welfare.LIST_DOWN_NAME


class RefreshClosureTest(Base):
    """福利找馆的「到底 → 刷新 → 新一批从顶部重新搜索」闭环。真实 `_find_and_open / _scan_list_once / _refresh_list /
    _scroll_list_to_top / _check_candidate`，替身设备 / 识别 / 虚拟时钟；World 的 `click_guard=True` 带真实 `Device`
    的操作记录写入 / 检查 / 移除逻辑。"""

    def run_find(self, **kwargs):
        world, task, runner = self.build(remaining=1, **kwargs)
        runner._find_and_open()
        return world, task, runner

    def low(self, prefix, count, people=50):
        return [card(f'{prefix}{i}', people=people) for i in range(count)]

    # --- 1：本批无「鑫」 → 到底 → 刷新 → 下一批开馆
    def test_batch_without_xin_is_scanned_to_the_bottom_then_refreshed_then_the_next_batch_opens(self):
        world, task, runner = self.run_find(
            cards=[card(f'n{i}', xin=False) for i in range(8)], refreshes=[[card('hit', people=150)]])
        self.assertEqual(world.opened, ['hit'])                  # 新一批里的合格馆被开启
        self.assertEqual(world.checked, ['hit'])
        self.assertEqual(len(world.kinds('refreshed')), 1)
        self.assertEqual(world.phase, 'map_found')

    # --- 2：有「鑫」但人数不足 → 逐个检查完才刷新；人数等于门槛时允许
    def test_all_low_candidates_are_checked_before_refreshing_and_the_threshold_is_inclusive(self):
        world, task, runner = self.run_find(
            cards=self.low('l', 6, people=99), refreshes=[[card('eq', people=100)]])
        self.assertEqual(world.checked, [f'l{i}' for i in range(6)] + ['eq'])
        refreshed_at = world.events.index(('refreshed',))
        checks_before = [e for e in world.events[:refreshed_at] if e[:2] == ('click_xy', CANDIDATE_NAME)]
        self.assertEqual(len(checks_before), 6)                  # 刷新之前 6 个候选都检查过了
        self.assertEqual(world.refresh_count, 1)

    # --- 3：最后一屏有合格候选 → 先处理，不提前刷新
    def test_qualified_candidate_on_the_last_screen_is_taken_without_refreshing(self):
        cards = self.low('c', 7) + [card('last', people=150)]
        world, task, runner = self.run_find(cards=cards, refreshes=[[card('never', people=150)]])
        self.assertEqual(world.checked[-1], 'last')
        self.assertEqual(world.refresh_count, 0)
        self.assertEqual(len(world.checked), 8)

    # --- 4：翻页重叠不重复；不同馆不被误去重
    def test_overlapping_pages_check_each_distinct_card_exactly_once(self):
        world, task, runner = self.run_find(cards=self.low('c', 9), refreshes=[[card('hit', people=150)]])
        self.assertEqual(world.checked[:9], [f'c{i}' for i in range(9)])
        self.assertEqual(world.checked.count('c3'), 1)

    def test_selection_highlight_does_not_break_the_identity_of_a_card(self):
        world, task, runner = self.run_find(cards=self.low('c', 8), highlight=True,
                                            refreshes=[[card('hit', people=150)]])
        self.assertEqual(world.checked[:8], [f'c{i}' for i in range(8)])      # 每张只检查一次、没有因高亮重复 / 漏检

    # --- 5：刷新后上一批的记录不污染下一批（即使部分候选相同）
    def test_previous_batch_memory_does_not_block_the_same_card_in_the_new_batch(self):
        world, task, runner = self.run_find(
            cards=[card('x', people=50)], refreshes=[[card('x', people=50), card('y', people=150)]])
        self.assertEqual(world.checked, ['x', 'x', 'y'])         # 新批次里的 x 照样被检查

    # --- 6：刷新确认与等待
    def test_delayed_loading_list_is_waited_for_and_the_old_list_is_not_rescanned(self):
        world, task, runner = self.run_find(
            cards=[card('o', people=50)], refreshes=[[card('n', people=150)]], refresh_delay=6.0)
        self.assertEqual(world.checked, ['o', 'n'])              # 旧列表只检查了一次，新列表出来后才开始新一批
        self.assertLess(world.now, 120)

    def test_confirm_that_vanishes_without_refreshing_the_list_is_not_taken_as_a_refresh(self):
        world, task, runner = self.build(remaining=1, cards=[card('o', people=50)], refresh_effect='none')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._find_and_open()
        self.assertIn('没有变化', str(ctx.exception))
        self.assertEqual(world.checked, ['o'])                   # 没有把旧列表当新一批重复检查
        self.assertEqual(world.refresh_count, 1)                 # 也没有为「看起来没生效」反复花钱刷新
        self.assertEqual(world.kinds('refreshed'), [])
        self.assertLess(world.now, 120)

    def test_page_that_does_not_come_back_after_confirming_is_bounded_and_not_a_success(self):
        world, task, runner = self.build(remaining=1, cards=[card('o', people=50)], refresh_effect='unknown_page')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._find_and_open()
        self.assertIn('没有回到找馆页', str(ctx.exception))
        self.assertEqual(world.checked, ['o'])
        self.assertLess(world.now, 60)

    def test_refresh_dialog_missing_is_bounded_by_the_refresh_tries(self):
        world, task, runner = self.build(remaining=1, cards=[card('o', people=50)], refresh_blocked=True)
        with self.assertRaises(RequestHumanTakeover):
            runner._find_and_open()
        self.assertEqual(len([e for e in world.events if e == ('click', 'REFRESH')]), welfare.REFRESH_TRIES)

    # --- 7：刷新后列表位置
    def test_list_that_resets_to_the_top_is_confirmed_by_static_reverse_swipes_only(self):
        world, task, runner = self.run_find(
            cards=self.low('o', 8), refreshes=[[card('n0', people=150)] + self.low('n', 7)])
        self.assertEqual(world.checked[-1], 'n0')
        self.assertEqual(len(world.kinds('swipe_down')), welfare.SWIPE_NO_CHANGE_LIMIT)

    def test_list_that_keeps_its_scroll_position_is_scrolled_back_to_the_top_before_scanning(self):
        new = [card('n0', people=150)] + self.low('n', 9)
        world, task, runner = self.run_find(cards=self.low('o', 10), refreshes=[new], refresh_scroll='keep')
        self.assertEqual(world.checked[-1], 'n0')                # 顶部那张没有被漏掉
        self.assertEqual(world.checked[:10], [f'o{i}' for i in range(10)])
        self.assertGreaterEqual(len(world.kinds('swipe_down')), 3 + welfare.SWIPE_NO_CHANGE_LIMIT)
        self.assertEqual(world.refresh_count, 1)                 # 没有因为从中间开始扫到底而白白再刷新一次

    def test_long_reverse_scroll_back_goes_through_the_real_guard_without_a_false_trip(self):
        new = [card('n0', people=150)] + self.low('n', 29)
        world, task, runner = self.build(remaining=1, cards=self.low('o', 30), refreshes=[new],
                                         refresh_scroll='keep', click_guard=True)
        runner._scan_list_once = Mock(side_effect=[False, True])      # 只关心回顶：第一批到底、第二批立即找到
        world.scroll = world.max_scroll                               # 刷新前列表停在最底部
        with patch.object(WelfareDokan, '_confirm_open', return_value=True):
            runner._find_and_open()
        self.assertGreaterEqual(len(world.kinds('swipe_down')), 10)   # 反向推进次数超过公共「同名 10 次」的线
        removed = [e for e in world.events if e[0] == 'record_remove' and e[1] == DOWN_NAME]
        self.assertTrue(removed)                                      # 有效推进之后移除了回顶滑动自己的记录
        self.assertEqual(world.scroll, 0)

    def test_top_scroll_is_bounded_when_the_list_never_reaches_the_top(self):
        world, task, runner = self.build(remaining=1, cards=self.low('o', 4), unsent_swipes=0)
        with patch.object(WelfareDokan, '_swipe_list', return_value='moved'):
            with self.assertRaises(RequestHumanTakeover):
                runner._scroll_list_to_top()
        with patch.object(WelfareDokan, '_swipe_list', return_value='not_sent'):
            with self.assertRaises(RequestHumanTakeover):
                runner._scroll_list_to_top()

    # --- 8：普通刷新次数上限与福利无关
    def test_welfare_ignores_the_ordinary_refresh_count_cap_and_the_ordinary_code_keeps_it(self):
        import inspect
        batches = [[card(f'b{i}', people=50)] for i in range(5)] + [[card('hit', people=150)]]
        world, task, runner = self.build(remaining=1, cards=[card('o', people=50)], refreshes=batches)
        task.config.dokan.dokan_config.find_dokan_refresh_count = 1
        runner._find_and_open()
        self.assertEqual(world.refresh_count, 6)                  # 远超普通模式的上限 1
        self.assertEqual(world.checked[-1], 'hit')
        self.assertNotIn('.find_dokan_refresh_count', inspect.getsource(welfare))      # 没有读取普通模式的刷新次数配置
        self.assertIn('find_dokan_refresh_count', inspect.getsource(ScriptTask.find_dokan))   # 普通模式仍受它限制

    # --- 10：停止 / 截图 / 设备异常原样传播
    def test_errors_during_the_refresh_propagate_and_nothing_else_happens(self):
        for error in (OSError('adb gone'), KeyboardInterrupt(), SystemExit(0)):
            with self.subTest(error=repr(error)):
                world, task, runner = self.build(remaining=1, cards=[card('o', people=50)],
                                                 refreshes=[[card('hit', people=150)]])
                original = task.screenshot

                def shot(original=original, error=error, world=world):
                    if world.refresh_count >= 1:
                        raise error
                    original()
                task.screenshot = shot
                with self.assertRaises(type(error)):
                    runner._find_and_open()
                self.assertEqual(world.refresh_count, 1)          # 没有继续刷新
                self.assertEqual(world.opened, [])
                self.assertEqual(world.checked, ['o'])            # 没有找馆 / 开馆

    def test_errors_during_the_scroll_back_propagate_without_scanning_or_opening(self):
        world, task, runner = self.build(remaining=1, cards=self.low('o', 10),
                                         refreshes=[[card('hit', people=150)] + self.low('n', 9)], refresh_scroll='keep')
        original = task.screenshot

        def shot():
            if world.kinds('swipe_down'):
                raise OSError('adb gone')
            original()
        task.screenshot = shot
        with self.assertRaises(OSError):
            runner._find_and_open()
        self.assertEqual(world.opened, [])
        self.assertNotIn('hit', world.checked)


class CandidateRecordTest(Base):
    """候选「点击 + 取消详情」两类操作记录与公共双按钮保护（D-04 遗留项）：用真实 `Device` 记录逻辑核实。"""

    def guarded(self, **kwargs):
        kwargs.setdefault('remaining', 1)
        return self.build(click_guard=True, **kwargs)

    def test_dense_distinct_candidates_pass_the_real_public_guard(self):
        cards = [card(f'd{i}', people=50) for i in range(16)]
        world, task, runner = self.guarded(cards=cards, refreshes=[[card('hit', people=150)]])
        runner._find_and_open()
        self.assertEqual(world.checked[:16], [f'd{i}' for i in range(16)])
        self.assertEqual(world.checked[-1], 'hit')
        removed = {e[1] for e in world.events if e[0] == 'record_remove'}
        self.assertTrue({CANDIDATE_NAME, CANCEL_NAME} <= removed)

    def test_the_same_scan_trips_the_two_button_rule_without_the_release(self):
        # 修复前的行为：不释放候选记录 → 一批里检查 6 个候选就触发「两个按钮」保护（真实 Device 记录逻辑）
        cards = [card(f'd{i}', people=50) for i in range(16)]
        world, task, runner = self.guarded(cards=cards, refreshes=[[card('hit', people=150)]])
        with patch.object(WelfareDokan, '_release_candidate_records', lambda self: None):
            with self.assertRaises(GameTooManyClickError) as ctx:
                runner._find_and_open()
        self.assertIn('between 2 buttons', str(ctx.exception))
        self.assertIn(CANDIDATE_NAME, str(ctx.exception))

    def test_release_happens_before_the_next_candidate_click_so_the_window_never_fills(self):
        cards = [card(f'd{i}', people=50) for i in range(12)]
        world, task, runner = self.guarded(cards=cards, refreshes=[[card('hit', people=150)]])
        guard = task.device.guard
        peak = {'cand': 0, 'cancel': 0}
        original = guard.click_record_check

        def watch():
            peak['cand'] = max(peak['cand'], guard.count(CANDIDATE_NAME))
            peak['cancel'] = max(peak['cancel'], guard.count(CANCEL_NAME))
            return original()
        guard.click_record_check = watch
        runner._find_and_open()
        self.assertLessEqual(peak['cand'], 2)                     # 写入 + 检查时窗口里最多只有刚点的那一个（外加极少数交错）
        self.assertLessEqual(peak['cancel'], 2)

    def test_unreadable_candidates_are_not_valid_progress_and_stay_protected(self):
        cards = [card(f'u{i}', people=None) for i in range(14)]
        world, task, runner = self.guarded(cards=cards)
        with self.assertRaises(GameTooManyClickError):
            runner._find_and_open()
        removed = {e[1] for e in world.events if e[0] == 'record_remove'}
        self.assertFalse({CANDIDATE_NAME, CANCEL_NAME} & removed)  # 没有读到人数 = 没有有效推进 = 不清

    def test_unchallengeable_candidates_count_as_verified_and_release(self):
        cards = [card(f'n{i}', people=150, challengeable=False) for i in range(14)]
        world, task, runner = self.guarded(cards=cards, refreshes=[[card('hit', people=150)]])
        runner._find_and_open()
        self.assertEqual(world.checked[-1], 'hit')

    def test_detail_that_cannot_be_closed_stops_without_releasing_anything(self):
        world, task, runner = self.guarded(cards=[card('a', people=50), card('b', people=50)], hide_clicks=99)
        with self.assertRaises(RequestHumanTakeover):
            runner._find_and_open()
        self.assertEqual([e for e in world.events if e[0] == 'record_remove'], [])
        self.assertLessEqual(len([e for e in world.events if e == ('click', 'CANCEL')]), welfare.HIDE_ATTEMPTS)

    def test_relocation_that_keeps_failing_is_bounded_and_clicks_nothing(self):
        world, task, runner = self.guarded(cards=[card('a', people=50)])
        with patch.object(WelfareDokan, '_relocate', lambda self, candidate: None):
            with self.assertRaises(RequestHumanTakeover) as ctx:
                runner._find_and_open()
        self.assertIn('重新定位', str(ctx.exception))
        self.assertEqual(world.kinds('click_xy'), [])

    def test_other_buttons_records_are_never_touched_by_the_release(self):
        world, task, runner = self.guarded(cards=[card('a', people=50)], refreshes=[[card('hit', people=150)]])
        guard = task.device.guard
        guard.click_record.append('other_button')
        runner._find_and_open()
        removed = {e[1] for e in world.events if e[0] == 'record_remove'}
        self.assertTrue(removed <= {CANDIDATE_NAME, CANCEL_NAME, SWIPE_NAME, DOWN_NAME})
        self.assertIn('other_button', guard.click_record)


class CardIdentityTest(unittest.TestCase):
    """D-08：候选身份（指纹）。用 2026-10-26 / 27 两张真实整屏截图里的真实「鑫」卡片（列表列裁剪样本）量：
    同一张卡片微小错位、徽记闪动不能被当成不同卡片；真正不同的卡片（哪怕只差一行文字）不能被当成同一张。"""

    FIXTURES = Path(__file__).parent / 'fixtures' / 'dokan_welfare'
    A_BOX = (1153, 205, 19, 34)
    B_BOX = (1153, 486, 19, 34)

    def canvas(self, name):
        crop = cv2.imread(str(self.FIXTURES / name))
        image = np.zeros((720, 1280, 3), np.uint8)
        image[0:crop.shape[0], 1060:1060 + crop.shape[1]] = crop
        return image

    def setUp(self):
        self.a = self.canvas('list_xin_oas2_20261026.png')
        self.b = self.canvas('list_xin_oas2_20261027.png')
        self.fa = card_fingerprint(self.a, self.A_BOX)

    @staticmethod
    def old_distance(x, y):
        return float(np.mean(np.abs(np.asarray(x) - np.asarray(y))))      # 旧判据：整张 34x30 小图的平均绝对差（< 6.0 判同一张）

    def edit_text_band(self, rows):
        image = self.a.copy()
        top = self.A_BOX[1] + 17 + 20
        image[top:top + rows, 1160:1245] = 255 - image[top:top + rows, 1160:1245]
        return image

    def test_fingerprint_keeps_the_30x34_shape_and_carries_the_alignment_crop(self):
        self.assertEqual(self.fa.shape, (30, 34))
        self.assertEqual(self.fa.tall.shape[0], 143 + 2 * welfare.CARD_MARGIN)

    def test_two_really_different_cards_are_different(self):
        fb = card_fingerprint(self.b, self.B_BOX)
        self.assertFalse(same_card(self.fa, fb))

    def test_the_same_card_with_a_small_location_error_is_still_the_same_card(self):
        for dy in (-2, -1, 1, 2):
            with self.subTest(dy=dy):
                shifted = card_fingerprint(self.a, (self.A_BOX[0], self.A_BOX[1] + dy, 19, 34))
                self.assertTrue(same_card(self.fa, shifted))
        # 旧判据对 2 px 的定位误差已经判成不同卡片（会重复检查 / 重新定位失败）
        old = card_fingerprint(self.a, (self.A_BOX[0], self.A_BOX[1] + 2, 19, 34))
        self.assertGreater(self.old_distance(self.fa, old), 6.0)

    def test_a_card_that_differs_by_one_line_of_text_is_a_different_card(self):
        for rows in (4, 8, 12):
            with self.subTest(rows=rows):
                other = card_fingerprint(self.edit_text_band(rows), self.A_BOX)
                self.assertFalse(same_card(self.fa, other))
        # 旧判据在这些真实卡片上把「只差一行文字」的卡片判成同一张（漏检）
        other = card_fingerprint(self.edit_text_band(4), self.A_BOX)
        self.assertLess(self.old_distance(self.fa, other), 6.0)

    def test_badge_animation_does_not_change_the_identity(self):
        glint = self.a.copy()
        x, y, w, h = self.A_BOX
        glint[y - 3:y + h + 3, x - 3:x + w + 3] = 255
        self.assertTrue(same_card(self.fa, card_fingerprint(glint, self.A_BOX)))

    def test_cards_clipped_by_the_list_edges_are_not_fingerprinted(self):
        self.assertIsNone(card_fingerprint(self.a, (1153, 20, 19, 34)))        # 上沿：对齐余量也不够
        self.assertIsNone(card_fingerprint(self.a, (1153, 560, 19, 34)))


# ---------------------------------------------------------------------------------------------- G2. 再战之后返回找馆页（道馆页的退出分支）
class RematchReturnTest(Base):
    """再战等待结束后停在哪一页没有真实画面证据：可能已回到地图找馆页，也可能还停在道馆页。真实 `_back_to_find_page`；
    替身 `FakeTask.goto_page` 在「目的地 = 地图且当前在道馆页」时按真实的 `page_dokan → page_dokan_map` 转换定义
    （`pages.page_dokan.transitions` 里的「退出图标 → 退出确认」序列）逐步识别并点击，再用新截图确认到达，
    无进展超时抛 `GamePageUnknownError`（与真实 `goto_page` 的无进展超时同义）；World 有真实的失败形态（退出图标 /
    退出确认没反应、退出后是进行中的馆 / 认不出的画面）和延迟。"""

    CLICKS = (('click', 'QUIT'), ('click', 'EXIT_ENSURE'))

    def back(self, phase, *, leave=True, timeout=None, **kwargs):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], **kwargs)
        world.phase = phase
        args = {'leave_dokan_page': leave}
        if timeout is not None:
            args['timeout'] = timeout
        return world, task, runner, args

    def quit_clicks(self, world):
        return [e for e in world.events if e in self.CLICKS]

    # --- 1：起始就是找馆页
    def test_already_on_the_find_page_returns_without_any_exit_navigation(self):
        world, task, runner, args = self.back('find')
        runner._back_to_find_page(**args)
        self.assertEqual(world.goto_calls, [])
        self.assertEqual(self.quit_clicks(world), [])

    # --- 2：起始是道馆页：走现有退出图标 → 退出确认
    def test_on_the_dokan_page_it_leaves_through_the_existing_exit_icon_and_confirm(self):
        world, task, runner, args = self.back('dokan_stay')
        runner._back_to_find_page(**args)
        self.assertEqual(self.quit_clicks(world), list(self.CLICKS))     # 先退出图标、再退出确认，各一次
        self.assertEqual(len(world.goto_calls), 1)
        self.assertEqual(world.phase, 'find')

    def test_the_navigation_timeout_is_bounded_by_the_remaining_time_not_left_at_the_default(self):
        world, task, runner, args = self.back('dokan_stay')
        runner._back_to_find_page(**args)
        self.assertLessEqual(world.goto_calls[0][1], welfare.BACK_TO_FIND_TIMEOUT)
        world, task, runner, args = self.back('dokan_stay', timeout=15)
        runner._back_to_find_page(**args)
        self.assertLessEqual(world.goto_calls[0][1], 15)

    # --- 3：退出后仍是进行中的馆
    def test_a_dokan_in_progress_after_the_exit_is_a_human_stop_and_nothing_else_happens(self):
        world, task, runner, args = self.back('dokan_stay', exit_result='found')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._back_to_find_page(**args)
        self.assertIn('进行中的道馆', str(ctx.exception))
        self.assertEqual(len(world.goto_calls), 1)
        self.assertEqual(world.kinds('click_xy'), [])

    # --- 4：认不出的画面 / 导航没到达：有界失败
    def test_an_unknown_page_after_the_exit_fails_within_the_bound(self):
        world, task, runner, args = self.back('dokan_stay', exit_result='blank', timeout=15)
        with self.assertRaises(GamePageUnknownError):                     # 导航自己的无进展超时：已开馆后 run() 会转人工
            runner._back_to_find_page(**args)
        self.assertEqual(len(world.goto_calls), 1)                        # 没有因为认不出就反复导航
        self.assertLessEqual(world.goto_calls[0][1], 15)
        self.assertLess(world.now, 60)
        self.assertNotEqual(world.phase, 'find')

    def test_exit_that_never_takes_effect_fails_in_the_navigation_and_is_not_taken_as_success(self):
        for mode in ('quit_dead', 'ensure_dead'):
            with self.subTest(mode=mode):
                world, task, runner, args = self.back('dokan_stay', exit_mode=mode)
                with self.assertRaises(GamePageUnknownError):
                    runner._back_to_find_page(**args)
                self.assertEqual(len(world.goto_calls), 1)
                self.assertNotEqual(world.phase, 'find')

    def test_failed_navigation_does_not_revote_or_wait_120_seconds_again(self):
        for mode in ('quit_dead', 'ensure_dead'):
            with self.subTest(mode=mode):
                world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')],
                                                 after_again='dokan_page', exit_mode=mode)
                with self.assertRaises(RequestHumanTakeover):            # 已开馆之后：run() 转人工，不是自动 Restart
                    runner.run()
                self.assertEqual(len(world.kinds('vote_again')), 1)
                self.assertEqual(len(world.opened), 1)
                voted = world.kinds('vote_again')[0][1]
                self.assertLess(world.now - voted, 120 + 60 + 40)         # 只有一次 120 秒等待，之后的导航有界

    def test_a_navigation_that_claims_success_but_leaves_us_on_the_dokan_page_is_not_trusted(self):
        world, task, runner, args = self.back('dokan_stay')
        # 真实 goto_page 只有到达才返回；这里假设它「返回了但页面没变」（不能把调用返回当作到达）：重新截图发现仍在道馆页，有限次后转人工
        task.goto_page = lambda page, **kwargs: world.goto_calls.append(('goto', kwargs.get('timeout'))) or True
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._back_to_find_page(**args)
        self.assertEqual(len(world.goto_calls), welfare.DOKAN_EXIT_TRIES)
        self.assertIn('仍然停在道馆页', str(ctx.exception))

    # --- 5：经过短暂过渡后到达：新截图确认
    def test_arrival_after_a_transition_is_confirmed_by_a_fresh_screenshot(self):
        world, task, runner, args = self.back('dokan_stay', exit_delay=3.0)
        before = world.snapshots
        runner._back_to_find_page(**args)
        self.assertEqual(world.phase, 'find')
        self.assertGreater(world.snapshots - before, 5)                   # 过渡期间取了多帧，最后一帧是找馆页
        self.assertEqual(len(world.goto_calls), 1)

    # --- 7：异常原样传播
    def test_screenshot_device_and_stop_signals_propagate_and_nothing_else_starts(self):
        for error in (OSError('adb gone'), KeyboardInterrupt(), SystemExit(0)):
            with self.subTest(error=repr(error)):
                world, task, runner, args = self.back('dokan_stay')
                original = task.screenshot

                def shot(original=original, error=error, world=world):
                    if world.goto_calls and world.phase == 'exit_wait':
                        raise error
                    original()
                task.screenshot = shot
                with self.assertRaises(type(error)):
                    runner._back_to_find_page(**args)
                self.assertEqual(world.kinds('click_xy'), [])
                self.assertEqual(world.opened, [])

    # --- 8：整条两馆调用关系
    def test_two_dokans_vote_wait_once_leave_the_dokan_page_and_search_the_second_without_redoing_setup(self):
        world, runner, result = self.run_ok(remaining=2, cards=[card('a'), card('b')], after_again='dokan_page',
                                            own='uncreated')
        self.assertEqual(result, 0)
        self.assertEqual(len(world.opened), 2)
        self.assertEqual(len(world.kinds('vote_again')), 1)
        self.assertEqual(self.quit_clicks(world), list(self.CLICKS))       # 整条流程里只有再战之后离开道馆页这一次
        voted = world.kinds('vote_again')[0][1]
        second_open = [e for e in world.events if e[0] == 'opened'][1][2]
        self.assertGreaterEqual(second_open - voted, welfare.AGAIN_WAIT_SECONDS)
        exit_at = world.events.index(('click', 'QUIT'))
        vote_at = world.events.index(('vote_again', voted))
        waited = sum(e[1] for e in world.events[vote_at:exit_at] if e[0] == 'sleep')
        self.assertGreaterEqual(waited, welfare.AGAIN_WAIT_SECONDS)       # 120 秒在退出之前，只等一次
        self.assertEqual(world.kinds('create_confirmed'), [('create_confirmed',)])          # 我方建馆只一次（第一馆前）
        self.assertEqual(len([e for e in world.events if e == ('click', 'TEAM')]), 1)       # 预设只一次
        self.assertEqual(world.kinds('keep_bounty'), [])

    def test_when_the_game_already_returns_to_the_map_the_exit_navigation_is_never_used(self):
        world, runner, result = self.run_ok(remaining=2, cards=[card('a'), card('b')])      # after_again = find（原行为）
        self.assertEqual(self.quit_clicks(world), [])
        self.assertEqual(len(world.opened), 2)

    # --- 9：最后一馆不走这条链
    def test_the_last_dokan_does_not_use_the_rematch_return_chain(self):
        world, runner, result = self.run_ok(remaining=1, cards=[card('a')], after_again='dokan_page')
        self.assertEqual(result, 0)
        self.assertEqual(self.quit_clicks(world), [])
        self.assertEqual(world.kinds('vote_again'), [])

    # --- 预设返回保持原样（不扩大为任意页面都走退出导航）
    def test_the_preset_return_and_the_default_call_do_not_use_the_exit_navigation(self):
        world, task, runner, args = self.back('dokan_stay', leave=False, timeout=5)
        with self.assertRaises(RequestHumanTakeover):
            runner._back_to_find_page(**args)                              # 默认只点黄色返回键，道馆页上点不到
        self.assertEqual(world.goto_calls, [])
        self.assertEqual(self.quit_clicks(world), [])

    # --- 修复前：旧实现停在道馆页只能等到超时
    def test_the_old_implementation_cannot_leave_the_dokan_page(self):
        def legacy(self, timeout=welfare.BACK_TO_FIND_TIMEOUT, leave_dokan_page=False):
            task = self.task
            deadline = self.clock() + timeout
            while True:
                self._screenshot()
                if task.appear(task.I_RYOU_DOKAN_FINDING_DOKAN) and not task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                    return
                if self.clock() >= deadline:
                    break
                if task.appear(task.I_RYOU_DOKAN_FOUND_DOKAN):
                    self._human('回到地图后发现存在进行中的道馆，无法确认现场，请人工处理。')
                task.appear_then_click(GlobalGameAssets.I_UI_BACK_YELLOW, interval=1.5)
                self.sleep(0.5)
            self._human('没有回到找馆页，已停止。')

        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], after_again='dokan_page')
        with patch.object(WelfareDokan, '_back_to_find_page', legacy):
            with self.assertRaises(RequestHumanTakeover) as ctx:
                runner.run()
        self.assertIn('没有回到找馆页', str(ctx.exception))
        self.assertEqual(self.quit_clicks(world), [])


# ---------------------------------------------------------------------------------------------- G3. 再战后 120 秒等待与公共卡死保护
class AgainWaitGuardTest(Base):
    """再战投票确认成功之后固定等待 120 秒（无截图），等待结束后的第一次 `screenshot()` 会先过公共卡死检查。
    真实 `Device.stuck_record_check / clear` 与真实 `Timer`（60 / 300 秒 + 检查次数条件；时间取虚拟时钟）：
    距最近一次清除超过 60 秒、且自那以后的检查次数 > 60 才抛 GameStuckError。投票确认阶段的帧数不固定（截图间隔
    0.1～0.3 秒夹取，按钮变化到稳定可能要好几秒），帧数一多，120 秒之后的第一次截图就会在识别页面之前被判成卡死。"""

    def guarded(self, **kwargs):
        kwargs.setdefault('remaining', 2)
        kwargs.setdefault('cards', [card('a'), card('b')])
        return self.build(stuck_guard=True, snap_step=0.1, **kwargs)

    @staticmethod
    def spy_entry(runner, world, task):
        """记录进入 `_wait_again` 时的公共保护状态：自最近一次清除以来的检查次数 / 经过的虚拟秒数。"""
        seen = {'calls': 0}
        original = runner._wait_again

        def wrapper():
            guard = task.device.guard
            seen['calls'] += 1
            seen['count'] = guard.stuck_timer._reach_count
            seen['since_clear'] = world.now - guard.last_clear
            return original()
        runner._wait_again = wrapper
        return seen

    def age(self, world, task, checks):
        """模拟再战点击之后：清一次计时，再取 `checks` 帧（每帧都走真实公共检查，时间还远不到 60 秒）。"""
        task.device.guard.stuck_record_clear()
        for _ in range(checks):
            task.screenshot()

    # --- 1：等待前检查次数 > 60、时间 < 60 秒，等待结束后的第一次截图不误报
    def test_many_checks_before_the_wait_do_not_trip_the_first_screenshot_after_it(self):
        world, task, runner = self.guarded()
        world.phase, world.alive = 'find', True
        self.age(world, task, 70)
        guard = task.device.guard
        self.assertGreater(guard.stuck_timer._reach_count, 60)
        self.assertLess(world.now - guard.last_clear, 60)
        runner._wait_again()
        task.screenshot()                                                  # 等待之后的第一次真实截图：不抛

    def test_whole_two_dokan_run_with_a_slow_vote_confirmation_passes_the_real_guard(self):
        world, task, runner = self.guarded(vote_change_delay=7.0)
        seen = self.spy_entry(runner, world, task)
        result = runner.run()
        self.assertEqual(result, 0)
        self.assertEqual(len(world.opened), 2)
        self.assertGreater(seen['count'], 60)                              # 进入等待时已经累计超过 60 次检查
        self.assertLess(seen['since_clear'], 60)                           # 但时间还不到 60 秒：正是会误报的组合
        self.assertEqual(world.violations, [])

    # --- 2：检查次数较少：原路径继续通过
    def test_a_normal_vote_confirmation_still_passes(self):
        world, task, runner = self.guarded()
        seen = self.spy_entry(runner, world, task)
        self.assertEqual(runner.run(), 0)
        self.assertLess(seen['count'], 60)
        self.assertEqual(len(world.opened), 2)

    # --- 修复前：旧实现在等待后的第一次截图触发公共保护
    def test_the_old_wait_trips_the_public_guard_at_the_first_screenshot_after_it(self):
        def legacy(self):
            self._wait(welfare.AGAIN_WAIT_SECONDS)
        world, task, runner = self.guarded(vote_change_delay=7.0)
        with patch.object(WelfareDokan, '_wait_again', legacy):
            with self.assertRaises(RequestHumanTakeover) as ctx:           # 已开馆之后 run() 把它转成人工
                runner.run()
        self.assertIsInstance(ctx.exception.__cause__, GameStuckError)     # 真实公共保护的结果：Wait too long
        self.assertEqual(len(world.kinds('vote_again')), 1)
        self.assertEqual(len(world.opened), 1)                             # 没有继续找第二馆

    # --- 3：等待结束后公共保护恢复
    def test_after_the_wait_the_public_guard_still_fires_on_real_no_progress(self):
        world, task, runner = self.guarded()
        world.phase, world.alive = 'find', True
        self.age(world, task, 70)
        runner._wait_again()
        guard = task.device.guard
        self.assertEqual(guard.detect_record, set())                       # 没有留下任何特殊等待登记
        self.assertIs(type(guard).stuck_record_check, StuckRecordGuard.stuck_record_check)   # 公共检查没有被替换
        world.now += 70
        with self.assertRaises(GameStuckError):
            for _ in range(200):                                           # 独立的失控上限
                task.screenshot()

    # --- 4：只等待一次、总时长不变
    def test_the_wait_is_one_block_of_120_seconds_and_is_not_restarted_by_the_protection(self):
        world, task, runner = self.guarded()
        world.phase, world.alive = 'find', True
        self.age(world, task, 70)
        start = world.now
        events_before = len(world.events)
        runner._wait_again()
        self.assertGreaterEqual(world.now - start, welfare.AGAIN_WAIT_SECONDS)
        self.assertLessEqual(world.now - start, welfare.AGAIN_WAIT_SECONDS + 1.0)
        self.assertEqual([e for e in world.events[events_before:] if e[0] == 'screenshot'], [])   # 等待期间没有截图
        self.assertEqual([e for e in world.events[events_before:] if e[0] in ('click', 'click_xy', 'swipe')], [])
        self.assertLessEqual(max(e[1] for e in world.events[events_before:] if e[0] == 'sleep'), 1.5)   # 分段，可被打断

    def test_whole_run_votes_once_waits_once_and_the_second_dokan_does_not_wait_or_rematch(self):
        world, task, runner = self.guarded(vote_change_delay=7.0)
        waits = Mock(wraps=runner._wait_again)
        runner._wait_again = waits
        runner.run()
        self.assertEqual(waits.call_count, 1)
        self.assertEqual(len(world.kinds('vote_again')), 1)
        self.assertEqual(len(world.kinds('abandoned')), 2)                 # 两馆都放弃
        last_abandon = [e for e in world.events if e[0] == 'abandoned'][-1]
        trailing = sum(e[1] for e in world.events[world.events.index(last_abandon):] if e[0] == 'sleep')
        self.assertLess(trailing, 60)                                      # 最后一馆之后没有 120 秒等待
        self.assertEqual(world.kinds('keep_bounty'), [])

    # --- 5：在线计时
    def test_the_wait_is_online_time_not_excluded_and_not_a_fatigue_pause(self):
        world, task, runner = self.guarded()
        world.phase, world.alive = 'find', True
        intervals = len(world.fatigue.intervals)
        runner._wait_again()
        self.assertEqual(len(world.fatigue.intervals), intervals)          # 没有 suspend_active
        self.assertNotIn('excluded_active_seconds', task.config.__dict__)
        world, task, runner = self.guarded(vote_change_delay=7.0)
        runner.run()
        spans = [round(end - start) for start, end in world.fatigue.intervals]
        self.assertEqual(len(spans), 2)                                    # 只有两次 600 秒离线等待被排除
        self.assertTrue(all(590 <= span <= 620 for span in spans), spans)

    # --- 6：停止信号和异常原样传播，没有继续业务的收尾
    def test_stop_signals_and_errors_during_the_wait_propagate_without_any_follow_up(self):
        for error in (KeyboardInterrupt(), SystemExit(0), OSError('adb gone')):
            with self.subTest(error=repr(error)):
                world, task, runner = self.guarded()
                world.phase, world.alive = 'find', True
                self.age(world, task, 70)
                guard = task.device.guard
                cleared_at, shots = guard.last_clear, len(world.kinds('screenshot'))
                calls = {'n': 0}
                original_sleep = runner.sleep

                def sleep(seconds, original=original_sleep, error=error):
                    calls['n'] += 1
                    if calls['n'] > 5:
                        raise error
                    original(seconds)
                runner.sleep = sleep
                with self.assertRaises(type(error)):
                    runner._wait_again()
                self.assertEqual(guard.last_clear, cleared_at)             # 异常出口没有做保护维护 / 收尾
                self.assertEqual(len(world.kinds('screenshot')), shots)
                self.assertEqual(world.goto_calls, [])
                self.assertEqual(world.kinds('click_xy'), [])

    # --- 7：不清无关记录，不替换公共检查
    def test_click_records_and_the_public_check_methods_are_left_alone(self):
        world, task, runner = self.guarded()
        world.phase, world.alive = 'find', True
        guard = task.device.guard
        for name in ('res_dokan_team', 'dokan_welfare_candidate', 'dokan_welfare_candidate'):
            guard.click_record.append(name)
        before = list(guard.click_record)
        check, clear = type(guard).stuck_record_check, type(guard).stuck_record_clear
        runner._wait_again()
        self.assertEqual(list(guard.click_record), before)
        self.assertIs(type(guard).stuck_record_check, check)
        self.assertIs(type(guard).stuck_record_clear, clear)
        self.assertEqual(Device.stuck_timer.limit, 60)                     # 公共阈值没动
        self.assertEqual((Device.stuck_timer.count, Device.stuck_timer_long.limit), (60, 300))

    # --- 9：再战返回导航等回归
    def test_the_rematch_return_through_the_dokan_page_still_works_after_a_slow_vote(self):
        world, runner, result = self.run_ok(remaining=2, cards=[card('a'), card('b')], stuck_guard=True,
                                            snap_step=0.1, vote_change_delay=7.0, after_again='dokan_page')
        self.assertEqual(result, 0)
        self.assertEqual(len(world.opened), 2)
        self.assertEqual(len([e for e in world.events if e == ('click', 'QUIT')]), 1)


# ---------------------------------------------------------------------------------------------- D0. 集结与公共卡死保护
class GatherGuardTest(Base):
    """福利集结阶段与公共卡死保护（D-05）：真实 `WelfareDokan._enter_prepare_and_close`，设备带真实 `Device` 的
    `stuck_record_add / clear / check`（`World(stuck_guard=True)`：screenshot 前先检查、点击和 app_stop / app_start 清除），
    计时器用真实 `Timer`、时间取自虚拟时钟（公共的 60 秒 / 300 秒 + 检查次数条件都在）。不是 mock 掉 `stuck_record_check`。"""

    def stage(self, **kwargs):
        """只跑集结阶段：世界停在「地图上有进行中的馆」，由真实 `_enter_prepare_and_close` 进入道馆并等待。"""
        kwargs.setdefault('remaining', 1)
        kwargs.setdefault('start', 'map_found')
        world, task, runner = self.build(stuck_guard=True, **kwargs)
        return world, task, runner

    @staticmethod
    def gather_start(world, gather):
        return world.gather_until - gather

    # --- 1 / 2：正常集结超过公共 60 / 300 秒
    def test_gathering_beyond_the_public_60_seconds_is_not_a_stuck_error(self):
        world, task, runner = self.stage(gather=100.0)
        runner._enter_prepare_and_close()
        self.assertEqual(len(world.kinds('app_stop')), 1)
        self.assertEqual(world.violations, [])

    def test_gathering_beyond_the_public_300_second_long_wait_cap_is_still_allowed(self):
        for gather in (320.0, 850.0):
            with self.subTest(gather=gather):
                world, task, runner = self.stage(gather=gather)
                runner._enter_prepare_and_close()
                self.assertEqual(len(world.kinds('app_stop')), 1)
                self.assertEqual(self.count(world, ('click', 'START')), 1)

    @staticmethod
    def count(world, event):
        return len([e for e in world.events if e == event])

    def test_the_old_behaviour_trips_the_public_guard_at_about_60_seconds(self):
        # 说明「公共检查是真的」：把集结阶段换成补丁前的无保活写法，同一个世界在 60 秒左右被公共保护判成卡死
        world, task, runner = self.stage(gather=100.0)
        with patch.object(WelfareDokan, '_enter_prepare_and_close', legacy_enter_prepare_and_close):
            with self.assertRaises(GameStuckError):
                runner._enter_prepare_and_close()
        waited = world.now - self.gather_start(world, 100.0)
        self.assertTrue(55 <= waited <= 90, waited)

    # --- 为什么截图前检查不会提前误报
    def test_the_check_before_each_screenshot_never_sees_a_gap_near_the_public_limit(self):
        world, task, runner = self.stage(gather=850.0)
        runner._enter_prepare_and_close()
        self.assertLess(task.device.guard.max_gap, 5.0)          # 每次检查时，距最近一次清除 < 5 秒（公共上限 60 秒）

    def test_no_special_wait_state_is_registered_and_public_timers_are_the_common_ones(self):
        world, task, runner = self.stage(gather=100.0)
        runner._enter_prepare_and_close()
        guard = task.device.guard
        self.assertEqual(guard.detect_record, set())
        self.assertEqual(guard.stuck_long_wait_list, ['BATTLE_STATUS_S', 'PAUSE', 'LOGIN_CHECK', 'PREPARE_BEFORE_BATTLE'])
        self.assertEqual((guard.stuck_timer.limit, guard.stuck_timer_long.limit), (60, 300))

    # --- 3：业务总时限
    def test_business_limit_is_counted_from_stage_start_and_never_extended(self):
        world, task, runner = self.stage(gather=5000.0)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._enter_prepare_and_close()
        self.assertIn('超时', str(ctx.exception))
        waited = world.now - self.gather_start(world, 5000.0)
        self.assertGreaterEqual(waited, welfare.GATHER_TIMEOUT)
        self.assertLess(waited, welfare.GATHER_TIMEOUT + 5)       # 没有被每帧识别 / 清计时重置
        self.assertEqual(world.kinds('app_stop'), [])
        self.assertEqual(self.count(world, ('click', 'START')), 0)

    # --- 4 / 5：集结结束 → 开始挑战 → 准备 → 立即关闭
    def test_gather_over_clicks_start_challenge_then_prepare_then_closes_immediately(self):
        world, task, runner = self.stage(gather=100.0)
        runner._enter_prepare_and_close()
        events = world.events
        start = events.index(('click', 'START'))
        prepare = events.index(('prepare_click',))
        self.assertLess(start, prepare)
        self.assertEqual(self.count(world, ('click', 'START')), 1)
        # 点击与关闭紧邻：click_xy(prepare) → prepare_click → app_stop → stopped_from_prepare，中间没有截图 / sleep / 查询
        self.assertEqual(events[prepare - 1][:2], ('click_xy', 'prepare'))
        self.assertEqual(events[prepare + 1][0], 'app_stop')
        self.assertEqual(events[prepare + 2], ('stopped_from_prepare',))

    def test_prepare_seen_in_the_very_first_frame_is_clicked_without_any_wait(self):
        world, task, runner = self.stage(gather=100.0)
        world.phase = 'prepare'
        runner._enter_prepare_and_close()
        self.assertEqual(len(world.kinds('app_stop')), 1)
        self.assertEqual(self.count(world, ('click', 'START')), 0)

    # --- 6：未知画面
    def test_unknown_page_stops_within_the_tolerance_and_never_refreshes_the_stuck_timers(self):
        world, task, runner = self.stage(gather=60.0, transition=10 ** 9)
        guard = task.device.guard
        clears = []
        original = guard.stuck_record_clear
        guard.stuck_record_clear = lambda: (clears.append(world.now), original())
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._enter_prepare_and_close()
        self.assertIn('既不是集结页', str(ctx.exception))
        unknown_for = world.now - world.gather_until
        self.assertLess(unknown_for, welfare.GATHER_UNKNOWN_TOLERANCE + 5)
        self.assertLess(welfare.GATHER_UNKNOWN_TOLERANCE, 60)              # 先于公共 60 秒给出具体原因
        self.assertEqual([t for t in clears if t >= world.gather_until], [])         # 集结页消失之后一次都没清过
        self.assertEqual(world.kinds('app_stop'), [])

    # --- 7：开始挑战始终无效
    def test_start_challenge_that_never_works_is_bounded_and_not_kept_alive_by_recognition(self):
        world, task, runner = self.stage(gather=20.0, start_mode='dead')
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner._enter_prepare_and_close()
        self.assertIn('点击无效', str(ctx.exception))
        self.assertEqual(self.count(world, ('click', 'START')), welfare.GATHER_START_CLICK_LIMIT)
        self.assertLess(world.now - world.gather_until, 30)
        self.assertEqual(world.kinds('app_stop'), [])

    # --- 8：过渡后恢复
    def test_a_short_transition_is_tolerated_and_a_long_one_is_not(self):
        world, task, runner = self.stage(gather=60.0, transition=20.0)
        runner._enter_prepare_and_close()
        self.assertEqual(len(world.kinds('app_stop')), 1)
        world, task, runner = self.stage(gather=60.0, transition=welfare.GATHER_UNKNOWN_TOLERANCE + 10)
        with self.assertRaises(RequestHumanTakeover):
            runner._enter_prepare_and_close()
        self.assertEqual(world.kinds('app_stop'), [])

    # --- 9：异常原样传播
    def test_screenshot_and_stop_signals_propagate_and_nothing_starts_the_battle(self):
        for error in (OSError('adb gone'), KeyboardInterrupt(), SystemExit(0)):
            with self.subTest(error=repr(error)):
                world, task, runner = self.stage(gather=100.0)
                original = task.screenshot

                def shot(original=original, error=error):
                    if world.gather_until is not None and world.now > self.gather_start(world, 100.0) + 10:
                        raise error
                    original()
                task.screenshot = shot
                with self.assertRaises(type(error)):
                    runner._enter_prepare_and_close()
                self.assertEqual(world.kinds('app_stop'), [])
                self.assertEqual(self.count(world, ('click', 'START')), 0)

    def test_device_error_on_app_stop_propagates_without_further_interaction(self):
        world, task, runner = self.stage(gather=20.0)
        with patch.object(world, 'app_stop', side_effect=RuntimeError('adb down')):
            with self.assertRaises(RuntimeError):
                runner._enter_prepare_and_close()
        tail = world.events[world.events.index(('prepare_click',)) + 1:]
        self.assertEqual(tail, [])                                          # 点准备之后没有任何截图 / sleep / 点击

    # --- 10：阶段退出后不遗留特殊状态，公共保护仍然有效
    def assertPublicGuardStillWorks(self, world, task):
        world.phase, world.alive = 'find', True                             # 假定游戏已在运行（否则公共检查报的是「游戏已死」）
        world.now += 70
        with self.assertRaises(GameStuckError):
            for _ in range(200):                                            # 独立的失控上限
                task.screenshot()
        self.assertEqual(task.device.guard.detect_record, set())

    def test_after_a_normal_exit_the_public_guard_still_fires_on_real_no_progress(self):
        world, task, runner = self.stage(gather=100.0)
        runner._enter_prepare_and_close()
        self.assertEqual(task.device.guard.detect_record, set())
        self.assertPublicGuardStillWorks(world, task)

    def test_after_an_exception_exit_the_public_guard_still_fires_on_real_no_progress(self):
        world, task, runner = self.stage(gather=60.0, transition=10 ** 9)
        with self.assertRaises(RequestHumanTakeover):
            runner._enter_prepare_and_close()
        self.assertPublicGuardStillWorks(world, task)

    # --- 11：整条流程
    def test_whole_run_with_a_long_gather_reaches_the_end_under_the_real_guard(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], gather=400.0, stuck_guard=True)
        result = runner.run()
        self.assertEqual(result, 0)
        self.assertEqual(len(world.opened), 2)
        self.assertEqual(world.violations, [])

    def test_ordinary_dokan_gathering_branch_is_untouched(self):
        import inspect
        source = inspect.getsource(ScriptTask.run_on_dokan)
        self.assertIn('self.device.stuck_record_clear()', source)           # 普通道馆自己的保活写法保持原样
        self.assertIn('I_RYOU_DOKAN_GATHERING', source)


def legacy_enter_prepare_and_close(self):
    """D-05 之前的集结循环（原样），只用来证明公共保护确实会在约 60 秒判成卡死。"""
    task = self.task
    self._screenshot()
    if not task.appear(task.I_RYOU_DOKAN_CHECK):
        task.goto_page(pages.page_dokan)
    deadline = self.clock() + welfare.GATHER_TIMEOUT
    while True:
        self._screenshot()
        if task.appear(task.I_PREPARE_HIGHLIGHT):
            x, y = task.I_PREPARE_HIGHLIGHT.coord()
            welfare.execute_single_click(task.device, welfare.FinalPoint(x, y), control_name=task.I_PREPARE_HIGHLIGHT.name)
            task.device.app_stop()
            return
        if self.clock() >= deadline:
            self._human('等待集结 / 挑战开放超时，没有进入可点击的准备页，请人工处理。')
        if not task.appear(task.I_RYOU_DOKAN_GATHERING) and task.appear(task.I_RYOU_DOKAN_START_CHALLENGE):
            task.appear_then_click(task.I_RYOU_DOKAN_START_CHALLENGE, interval=2)
        self.sleep(1.0)


# ---------------------------------------------------------------------------------------------- D/E/F/G. 开启、关闭、等待、返回、放弃
class FlowTest(Base):
    def test_prepare_click_is_followed_immediately_by_app_stop(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('a')])
        i = next(i for i, e in enumerate(world.events) if e == ('prepare_click',))
        # click_xy 先于 prepare_click 记一条；app_stop 紧跟其后：中间没有截图、sleep、查询
        self.assertEqual(world.events[i - 1][:2], ('click_xy', 'prepare'))
        self.assertEqual(world.events[i + 1][0], 'app_stop')
        self.assertEqual(world.events[i + 2], ('stopped_from_prepare',))

    def test_only_the_game_is_closed_and_no_ordinary_battle_starts(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('a')])
        self.assertEqual(len(world.kinds('app_stop')), 1)
        self.assertEqual(world.kinds('screenshot_battle'), [])

    def test_no_screenshot_and_no_start_while_closed_for_600_seconds(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('a')])
        stop = world.kinds('app_stop')[0][1]
        start = world.kinds('app_start')[0][1]
        self.assertGreaterEqual(start - stop, 600)
        self.assertEqual([v for v in world.violations if v[0] in ('screenshot_while_closed', 'started_early')], [])

    def test_600_seconds_start_after_closure_is_confirmed(self):
        # 进程查询前两次异常、一次仍在：不能开始计时；之后连续两次确认不存在才开始
        world, task, runner = self.build(remaining=1, cards=[card('a')],
                                         exists=[OSError('adb'), True, False, OSError('adb'), False, False])
        runner.run()
        confirmed_at = [e for e in world.events if e[0] == 'process_query'][-1][1]
        start = world.kinds('app_start')[0][1]
        self.assertGreaterEqual(start - confirmed_at, 599.0)
        self.assertEqual(world.violations, [])

    def test_query_errors_are_never_treated_as_closed(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')], exists=[OSError('adb')] * 200)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('无法确认游戏已关闭', str(ctx.exception))
        self.assertEqual(world.kinds('app_start'), [])
        self.assertEqual(world.fatigue.intervals, [])        # 没有开始 10 分钟计时

    def test_process_still_alive_is_not_closed(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')], exists=[True] * 200)
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual(world.kinds('app_start'), [])
        self.assertGreaterEqual(len(world.kinds('app_stop')), 1)

    def test_return_uses_the_marker_offset_and_enters_before_abandon(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('a')], again_matches=[(0.93, 264, 346, 18, 32)])
        badge = world.kinds('badge')[0]
        self.assertEqual((badge[1], badge[2]), (264 + 9 + 84, 346 + 16 - 100))
        order = [e[0] if e[0] != 'click' else e[1] for e in world.events]
        self.assertLess(order.index('badge'), order.index('ABANDON'))

    def test_marker_missing_or_ambiguous_never_clicks_blindly(self):
        for matches in ([], [(0.93, 264, 346, 18, 32), (0.91, 527, 650, 18, 32)]):
            with self.subTest(matches=matches):
                world, task, runner = self.build(remaining=1, cards=[card('a')], again_matches=matches)
                with self.assertRaises(RequestHumanTakeover):
                    runner.run()
                self.assertEqual(world.kinds('badge'), [])
                self.assertNotIn(('click', 'ABANDON'), world.events)

    def test_never_votes_keep_bounty_and_waits_120_seconds_once_after_the_vote(self):
        world, _, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')])
        self.assertEqual(world.kinds('keep_bounty'), [])
        self.assertEqual(len(world.kinds('vote_again')), 1)
        voted = world.kinds('vote_again')[0][1]
        second_open = [e for e in world.events if e[0] == 'opened'][1][2]
        self.assertGreaterEqual(second_open - voted, 120)
        start = world.events.index(('vote_again', voted))
        end = next(i for i, e in enumerate(world.events) if e[0] == 'opened' and e[2] == second_open)
        sleeps = [e[1] for e in world.events[start:end] if e[0] == 'sleep']
        self.assertLessEqual(max(sleeps), 1.5)      # 等待是分段的（可被打断），不是一个长 sleep

    def test_vote_confirmed_by_a_stable_change_of_the_button_itself_starts_the_wait_once(self):
        world, _, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')], vote_mode='selected')
        self.assertEqual(len(world.kinds('vote_again')), 1)
        self.assertEqual(world.kinds('keep_bounty'), [])

    def _expect_human_without_wait(self, **kwargs):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], **kwargs)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertEqual(len(world.opened), 1)                  # 不继续找第二馆
        self.assertEqual(world.kinds('keep_bounty'), [])         # 全程不点保留赏金
        voted = world.kinds('vote_again')
        after = world.events[world.events.index(voted[-1]):]
        self.assertLess(sum(e[1] for e in after if e[0] == 'sleep'), 60)    # 没有启动 120 秒等待
        return world, str(ctx.exception)

    def test_vote_without_any_visible_change_stops(self):
        world, message = self._expect_human_without_wait(vote_mode='stays')
        self.assertIn('无法可靠确认本方选择成功', message)
        self.assertEqual(len(world.kinds('vote_again')), 1)      # 确认不了就不再点第二次

    def test_only_vote_count_changes_is_not_a_selection(self):
        self._expect_human_without_wait(vote_mode='counts_only')

    def test_only_animation_is_not_a_selection(self):
        self._expect_human_without_wait(vote_mode='animation')

    def test_unrelated_page_switch_is_not_a_selection(self):
        self._expect_human_without_wait(vote_mode='page_switch')

    def test_button_missing_briefly_then_back_unchanged_is_not_a_selection(self):
        self._expect_human_without_wait(vote_mode='flicker')

    def test_button_gone_for_good_is_not_a_selection(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], vote_mode='page_switch')
        with self.assertRaises(RequestHumanTakeover):
            runner.run()

    def test_throttled_click_is_not_a_vote_and_is_retried_until_really_sent(self):
        world, _, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')], throttle=2)
        self.assertEqual(len(world.kinds('vote_again')), 1)      # 限流的两次没有发出，不算投票

    def test_click_never_sent_stops_without_waiting(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')], throttle=99)
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIn('没有真正发出', str(ctx.exception))
        self.assertEqual(world.kinds('vote_again'), [])
        self.assertEqual(world.kinds('keep_bounty'), [])
        self.assertEqual(len(world.opened), 1)

    def test_abandon_vote_stage_is_distinguished_from_the_rematch_vote(self):
        world, _, _ = self.run_ok(remaining=2, cards=[card('a'), card('b')], abandon_stage=True)
        self.assertIn(('click', 'ABANDONED'), world.events)
        self.assertEqual(world.kinds('keep_bounty'), [])
        self.assertEqual(len(world.opened), 2)

    def test_last_dokan_has_no_vote_no_wait_and_no_third_dokan(self):
        world, _, result = self.run_ok(remaining=2, cards=[card('a'), card('b'), card('c')])
        self.assertEqual(len(world.opened), 2)
        self.assertEqual(world.remaining, 0)
        self.assertEqual(result, 0)
        self.assertEqual(len(world.kinds('vote_again')), 1)
        last_abandon = [e for e in world.events if e[0] == 'abandoned'][-1][1]
        trailing = sum(e[1] for e in world.events[world.events.index(('abandoned', last_abandon)):] if e[0] == 'sleep')
        self.assertLess(trailing, 60)              # 最后一馆之后没有 120 秒等待

    def test_second_dokan_is_searched_again_with_the_same_threshold(self):
        world, _, _ = self.run_ok(remaining=2, cards=[card('low', people=99), card('ok', people=100)],
                                  next_cards=[card('low2', people=5), card('ok2', people=100)])
        self.assertEqual(world.opened, ['ok', 'ok2'])
        self.assertEqual(world.checked, ['low', 'ok', 'low2', 'ok2'])
        self.assertEqual(len(world.kinds('refreshed')), 0)       # 第二馆重新找，但不降低条件


# ---------------------------------------------------------------------------------------------- 活跃时长 / 停止 / 异常
class ActiveTimeTest(Base):
    def test_only_the_closed_wait_is_excluded_from_active_time(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')])
        runner.run()
        intervals = world.fatigue.intervals
        self.assertEqual(len(intervals), 2)                      # 两馆各一次 10 分钟
        for start, end in intervals:
            self.assertAlmostEqual(end - start, 600, delta=3)
        excluded = task.config.__dict__['excluded_active_seconds']
        self.assertAlmostEqual(excluded, sum(e - s for s, e in intervals), delta=0.01)
        self.assertLess(excluded, 1300)                          # 120 秒（游戏开着）没有被扣除

    def test_real_fatigue_manager_stops_accruing_during_the_wait(self):
        clock = {'now': 1000.0}
        manager = FatigueManager(FatigueConfig(), clock=lambda: clock['now'], sleeper=lambda s: None)
        manager.begin_global_activity()
        clock['now'] += 100
        with manager.suspend_active():
            clock['now'] += 600
            self.assertAlmostEqual(manager.global_active_elapsed(), 100)
        clock['now'] += 50
        self.assertAlmostEqual(manager.global_active_elapsed(), 150)
        self.assertEqual(manager.activity_state, 'active')      # 没有被当成疲劳休息

    def test_suspend_is_a_noop_outside_global_activity(self):
        clock = {'now': 0.0}
        manager = FatigueManager(FatigueConfig(), clock=lambda: clock['now'], sleeper=lambda s: None)
        manager.end_global_activity()
        before = manager.global_active_elapsed()
        with manager.suspend_active():
            clock['now'] += 5
        self.assertEqual(manager.activity_state, 'scheduler_idle')
        self.assertEqual(manager.global_active_elapsed(), before)


class StopAndErrorTest(Base):
    class Stopped(BaseException):
        pass

    def test_stop_during_the_closed_wait_does_not_restart_the_game(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')])
        original = world.sleep

        def stopping(seconds):
            original(seconds)
            if world.closed_at is not None and world.now - world.closed_at > 300:
                raise self.Stopped

        runner.sleep = stopping
        with self.assertRaises(self.Stopped):
            runner.run()
        self.assertEqual(world.kinds('app_start'), [])
        self.assertEqual(len(world.fatigue.intervals), 1)         # 上下文被正常退出

    def test_stop_during_the_120_second_wait_keeps_the_game_open_and_does_nothing_more(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')])
        original = world.sleep

        def stopping(seconds):
            original(seconds)
            votes = world.kinds('vote_again')
            if votes and world.now - votes[0][1] > 60:
                raise self.Stopped

        runner.sleep = stopping
        with self.assertRaises(self.Stopped):
            runner.run()
        self.assertEqual(len(world.kinds('app_stop')), 1)
        self.assertEqual(len(world.opened), 1)

    def test_error_after_opening_is_not_left_to_the_generic_restart(self):
        world, task, runner = self.build(remaining=2, cards=[card('a'), card('b')])

        def broken_login():
            raise GameStuckError('登录卡死')

        runner._login = broken_login
        with self.assertRaises(RequestHumanTakeover) as ctx:
            runner.run()
        self.assertIsInstance(ctx.exception.__cause__, GameStuckError)
        self.assertIn('已开启 1 馆', str(ctx.exception))
        self.assertEqual(len(world.opened), 1)

    def test_error_before_opening_keeps_the_original_exception(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')])
        task.I_FIND_XIN = SimpleNamespace(name='x', match_all_any=Mock(side_effect=GameStuckError('卡死')))
        with self.assertRaises(GameStuckError):
            runner.run()
        self.assertEqual(world.opened, [])

    def test_a_repeated_run_after_the_dokan_is_open_is_not_taken_over(self):
        # 异常后公共 Restart 会重新跑任务：此时馆还开着，福利流程必须停下，不能误放弃 / 误开下一馆
        world, task, runner = self.build(remaining=1, start='map_found')
        with self.assertRaises(RequestHumanTakeover):
            runner.run()
        self.assertEqual(world.kinds('click'), [])


class MatchContractTest(Base):
    """外部 `match_all_any()` 是 (score, x, y, w, h)；福利模块内部一律用 (x, y, w, h)。

    2026-10-26 首次实测：把五项当四项拆包（ValueError），而旧替身返回四项，离线测试没抓到。
    """

    REAL = (0.9298649430274963, 1153, 205, 19, 34)        # 实测日志里的原始输入

    def test_real_logged_match_produces_a_candidate_fingerprint_without_unpacking_error(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')])
        task.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image: [self.REAL])
        found = runner._candidates()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['box'], (1153, 205, 19, 34))        # 内部只有四项坐标，score 没有混进去
        self.assertEqual(found[0]['fp'].shape, (30, 34))

    def test_candidates_are_ordered_top_to_bottom_not_by_score_or_x(self):
        cards = [card(f'c{i}') for i in range(4)]
        world, task, runner = self.build(remaining=1, cards=cards)
        raw = world.match_xin()
        self.assertNotEqual([m[2] for m in raw], sorted(m[2] for m in raw))           # 外部返回顺序不是从上到下
        self.assertNotEqual([m[1] for m in raw], sorted(m[1] for m in raw))
        ys = [c['box'][1] for c in runner._candidates()]
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(ys), 4)

    def test_candidate_click_lands_inside_the_four_item_box_and_score_is_not_a_coordinate(self):
        cards = [card('a', people=10), card('b', people=10), card('c', people=150)]
        world, _, _ = self.run_ok(remaining=1, cards=cards)
        clicks = [e for e in world.events if e[0] == 'click_xy' and e[1] == 'dokan_welfare_candidate']
        self.assertEqual(len(clicks), 3)
        self.assertEqual(world.checked, ['a', 'b', 'c'])
        for (_, _, cx, cy), slot in zip(clicks, range(3)):
            _, x, y, w, h = XIN_MATCH(slot)
            self.assertTrue(x <= cx <= x + w and y <= cy <= y + h, (slot, cx, cy))

    def test_relocate_finds_the_same_card_from_a_five_item_result_after_it_moved(self):
        cards = [card(f'c{i}', people=10) for i in range(5)]
        world, task, runner = self.build(remaining=1, cards=cards)
        target = runner._candidates()[2]                    # 第 3 行那张
        world.scroll = 1                                   # 列表往上滚一行：同一张卡落到第 2 行
        moved = runner._relocate(target)
        self.assertIsNotNone(moved)
        self.assertEqual(moved['box'], XIN_MATCH(1)[1:])
        self.assertEqual(len(moved['box']), 4)

    def test_malformed_matches_fail_loudly_with_the_source_not_silently(self):
        for bad in ([(1153, 205, 19, 34)], [(0.9, 1153, 205, 19)], [(0.9, 1153, 205, 19, 34, 1)],
                    [(0.9, 'x', 205, 19, 34)], [None]):
            with self.subTest(bad=bad):
                world, task, runner = self.build(remaining=1, cards=[card('a')])
                task.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image, bad=bad: bad)
                with self.assertRaises(ValueError) as ctx:
                    runner._candidates()
                self.assertIn('find_xin', str(ctx.exception))

    def test_empty_matches_and_cards_cut_by_the_list_edge(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')])
        task.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image: [])
        self.assertEqual(runner._candidates(), [])
        edge = (0.95, 1153, welfare.LIST_BOX[1] - 5, 19, 34)               # 被列表上沿裁切
        task.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image: [edge])
        self.assertEqual(runner._candidates(), [])

    def test_return_badge_uses_the_unique_five_item_marker(self):
        world, _, _ = self.run_ok(remaining=1, cards=[card('a')], again_matches=[(0.77, 300, 400, 20, 30)])
        badge = world.kinds('badge')[0]
        self.assertEqual((badge[1], badge[2]), (300 + 10 + 84, 400 + 15 - 100))

    def test_return_marker_with_four_items_is_a_loud_error_not_a_blind_click(self):
        world, task, runner = self.build(remaining=1, cards=[card('a')], again_matches=[(264, 346, 18, 32)])
        with self.assertRaises(ValueError):
            runner.run()
        self.assertEqual(world.kinds('badge'), [])

    def test_real_ruleimage_wrapper_with_a_fake_rpc_client_feeds_the_welfare_code(self):
        # 不启动图像服务：只替换 RPC 客户端，让真实 RuleImage.match_all_any 的返回格式化走一遍
        client = SimpleNamespace(match_all_any=Mock(return_value={'matches': [list(self.REAL)]}))
        with patch('module.atom.image.get_image_client', return_value=client):
            out = DokanAssets.I_FIND_XIN.match_all_any(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertEqual(out, [self.REAL])
        world, task, runner = self.build(remaining=1, cards=[card('a')])
        task.I_FIND_XIN = SimpleNamespace(name='find_xin', match_all_any=lambda image: out)
        found = runner._candidates()
        self.assertEqual([c['box'] for c in found], [(1153, 205, 19, 34)])


if __name__ == '__main__':
    unittest.main()
