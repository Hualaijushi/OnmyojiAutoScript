# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from dataclasses import dataclass
from time import sleep, monotonic

import copy

import numpy as np

from module.atom.click import RuleClick
from module.atom.frame_state import frame_difference
from module.atom.image import RuleImage
from module.atom.ocr import _normalize_ocr_click_area
from module.base.frame_wait import wait_for_changed_and_stable
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.click_pipeline import FinalPoint, execute_single_click
from module.click_sampler import ClickSampler
from module.exception import GamePageUnknownError
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from tasks.Component.SwitchSoul.name_search import (
    SwitchSoulNameError, SwitchSoulPageError, exact_matches, is_complete, normalize_target, parse_lines, parse_matches)
from module.logger import logger


def switch_parser(switch_str: str) -> tuple:
    switch_list = switch_str.split(',')
    if len(switch_list) != 2:
        raise ValueError('Switch_str must be 2 length')
    return int(switch_list[0]), int(switch_list[1])


@dataclass(frozen=True)
class _NameList:
    """按名称模式里的一个可滚动列表（分组 / 队伍）。"""
    kind: str            # 报错里显示的名称
    rule: str            # OCR 资源属性名（运行时 getattr，便于测试替换）
    to_top: str          # 回顶 swipe 资源属性名：手指向下，列表内容向前
    forward: str         # 向后翻页 swipe 资源属性名：手指向上
    viewport: tuple      # 列表可视区的 (上沿 y, 下沿 y)，取自 ocr.json 的 roiBack（= 名称实际出现的范围）
    max_top: int         # 回顶最多滑几次（故障边界，不是游戏支持的数量）
    max_pages: int       # 从上到下最多看几屏（同上）
    timeout_scale: float  # 阶段总时限 = `NAME_STAGE_TIMEOUT` × 它（队伍向后翻页的步幅更小，要看的屏数更多）
    row_pitch: int       # 一行的大致高度（像素）：只用来判断「最后一行下面还空着一整行」= 列表在可视区内就结束了


# 预算依据（都是故障边界，不是游戏支持的数量；真实组 / 队伍总数未知，超过只会报「没有可靠确认到底」，不会写成名称不存在）：
# - 分组：一屏约 8 个、翻页约 260px（≈ 4 组），20 屏足够 ≈ 60 个分组；回顶 12 次。
# - 队伍：翻页基准手指位移约 135px（一行约 150px，平均每次约 0.9 行，最小约 75px），60 屏约 ≥ 40 个队伍；
#   回顶用较大步幅（约 250px，最小约 150px），30 次约 ≥ 30 个队伍；每屏约 3~5 秒（截图 + OCR + 滑动 + 稳定等待），
#   所以队伍阶段时限取 2 倍（300 秒）。
GROUP_LIST = _NameList('分组', 'O_SS_GROUP_NAME', 'S_SS_NAME_GROUP_TO_TOP', 'S_SS_NAME_GROUP_NEXT', (94, 627), 12, 20, 1.0, 66)
TEAM_LIST = _NameList('队伍', 'O_SS_TEAM_NAME', 'S_SS_NAME_TEAM_TO_TOP', 'S_SS_NAME_TEAM_NEXT', (144, 619), 30, 60, 2.0, 150)


class _LineTarget:
    """把一行 OCR 命中包装成「有 name 和 coord()」的点击目标，采样口径和 `RuleOcr.coord()` 一致，但不改共享的 OCR 资源。"""

    def __init__(self, name: str, line):
        self.name = name
        self.line = line

    def coord(self) -> tuple:
        return ClickSampler.sample_target(_normalize_ocr_click_area(self.line.box), self.name)


class SwitchSoul(BaseTask, SwitchSoulAssets):
    # 数字模式分组：两次补点之间的间隔、第二次点击后给队伍列表刷新的 settle（秒）。
    # 两段语义不同，范围也分开写；每次运行各自独立采样（`random_delay` 复用项目统一随机源）。
    GROUP_CLICK_GAP = (0.4, 0.8)
    GROUP_SETTLE = (0.3, 0.6)
    # 数字模式队伍：识别 target_team 的有界窗口、点击后观察确认框的有界窗口（秒）。
    # 实测确认框在队伍点击后 1 秒内出现；已经装备同一预设时不会弹确认框，窗口到期就是正常结束。
    TEAM_FIND_TIMEOUT = 3.0
    TEAM_RESPONSE_TIMEOUT = 2.0
    # 数字模式滑顶：每次真实 swipe 之后的 settle（秒）、一次切换里真实 swipe 的上限。
    # 上限是故障安全帽，不是正常节奏目标：Device 对「同名 control 在最近 15 条记录里 ≥10 次」抛
    # GameTooManyClickError，且连续两次切换（EternitySea 两队 / Orochi 按层）之间只隔 3~4 次点击，
    # 4 是即使前一次也滑满上限、也不会让同名计数到 10 的最大值；达到上限只 warning 并继续，不升级成重启游戏。
    GROUP_TOP_SETTLE = (0.4, 0.7)
    MAX_GROUP_TOP_SWIPES = 4
    # 预设确认之后观察「契灵已装配于其他阴阳师，是否替换？」确认框的有界窗口、点击后等它关闭的上限（秒）。
    # 只在预设确认框出现并确认过之后才观察；没出现就是正常结束，不是失败。
    REPLACE_OBSERVE_TIMEOUT = 2.0
    REPLACE_CLOSE_TIMEOUT = 8.0
    # 预设确认框「确定」连续存在、始终点不掉时的本地超时（秒）：数字模式的确认恢复循环、按名称模式的切换循环都用它。
    # 原确认框和紧接着出现的契灵替换框中间没有空白帧时，两个框都在这一段时间里处理（点击仍是 3 秒 / 0.8 秒间隔）。
    CONFIRM_CLOSE_TIMEOUT = 10.0
    # 按名称模式「选队伍 + 处理确认」整段循环的总超时（秒），故障保护，不是节奏参数：正常流程是 4 次队伍点击
    # （每次最少隔 1.5 秒，约 6 秒）加预设确认的 0.8 秒间隔点击，慢模拟器上加 OCR 与页面响应也在 10~15 秒内；
    # 取 45 秒留 3 倍以上余量，不会让正常流程等满。进入循环时启动，不因看到 / 看不到「确定」、点击失败或空白帧重置。
    SWITCH_LOOP_TIMEOUT = 45.0
    # ---- 按名称找分组 / 队伍（均为故障边界，不是性能目标）----
    # 一次 OCR 读到 0 行时最多再换帧重读几次：偶发漏识别不能当作「列表是空的 / 到顶 / 到底」。
    NAME_OCR_TRIES = 3
    # 滑动后等列表「变化并稳定」：阈值与福利道馆列表同口径（0.02 / 0.01 / 连续 2 帧）；
    # 变化了但一直不稳定时再换基准帧有界重观察，仍不稳定就明确报错，不当作到底。
    NAME_CHANGED = 0.02
    NAME_STABLE = 0.01
    NAME_STABLE_FRAMES = 2
    NAME_SETTLE_TIMEOUT = 4.0
    NAME_SETTLE_RETRIES = 2
    NAME_SETTLE_RETRY_TIMEOUT = 2.0
    # 连续几次「滑了但画面没有变化」才算到边界（一次可能只是滑动没生效）。
    NAME_EDGE_CONFIRMS = 2
    # 点击前连续两帧里目标 y 的最大偏差（像素）、最多重试几轮：列表还在惯性滑动时不点。
    NAME_LOCATE_TRIES = 4
    NAME_POS_TOL = 6
    # 点分组后确认选中生效的最多点击次数：分组没有可识别的选中标志，只能看列表区域是否变化。
    NAME_GROUP_CLICK_TRIES = 2
    # 分组「选中」标志：复用数字模式的选中高亮模板（金色竖条，`I_SOU_CHECK_GROUP_*`，随皮肤替换），只在名称模式里把搜索范围放宽到
    # 整条左边缘（x 1080~1120、列表可视区高度），按「标志中心 y 与目标行中心 y 相差不超过 NAME_MARKER_TOL」判断选中的是不是目标行
    # （行距约 66px，取 25px 保证不会把相邻行当成目标行）。这些模板来自数字模式的旧页面，当前页面是否能识别待真机验证。
    NAME_MARKER_COLUMN = (1080, 94, 40, 533)
    NAME_MARKER_TOL = 25
    # 点分组确认选中之后，中央队伍列表「变化并稳定」的最多观察轮数（每轮 `NAME_SETTLE_TIMEOUT` 秒）。
    NAME_TEAM_READY_ROUNDS = 3
    # 回顶 / 找目标 / 选分组每个阶段的总时限（秒）。
    NAME_STAGE_TIMEOUT = 150.0

    def run_switch_soul(self, target: tuple | list[tuple] | str):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(target, str):
            try:
                target = switch_parser(target)
            except ValueError:
                logger.error('Switch soul config error')
                return
        self.click_preset()
        self.switch_souls(target)

    def click_preset(self) -> None:
        """
        点击预设
        :return:
        """
        while 1:
            self.screenshot()
            if self.appear(self.I_SOU_SWITCH_1):
                break
            if self.appear(self.I_SOU_SWITCH_2):
                break
            if self.appear(self.I_SOU_SWITCH_3):
                break
            if self.appear(self.I_SOU_SWITCH_4):
                break
            if self.appear(self.I_SOU_TEAM_PRESENT):
                break
            if self.appear_then_click(self.I_SOUL_PRESET, interval=2):
                continue
        logger.info('Click preset in switch soul')

    def switch_soul_one(self, group: int, team: int) -> None:
        """
        设置一个队伍的预设御魂
        :param group: 只能是[1-7]
        :param team: 只能是[1-4]
        :return:
        """

        def get_group_assets(group: int) -> tuple:
            match = {
                1: tuple([self.C_SOU_GROUP_1, self.I_SOU_CHECK_GROUP_1]),
                2: tuple([self.C_SOU_GROUP_2, self.I_SOU_CHECK_GROUP_2]),
                3: tuple([self.C_SOU_GROUP_3, self.I_SOU_CHECK_GROUP_3]),
                4: tuple([self.C_SOU_GROUP_4, self.I_SOU_CHECK_GROUP_4]),
                5: tuple([self.C_SOU_GROUP_5, self.I_SOU_CHECK_GROUP_5]),
                6: tuple([self.C_SOU_GROUP_6, self.I_SOU_CHECK_GROUP_6]),
                7: tuple([self.C_SOU_GROUP_7, self.I_SOU_CHECK_GROUP_7]),
            }
            return match[group]

        def get_team_asset(team: int):
            match = {
                1: self.I_SOU_SWITCH_1,
                2: self.I_SOU_SWITCH_2,
                3: self.I_SOU_SWITCH_3,
                4: self.I_SOU_SWITCH_4,
            }
            return match[team]

        # 滑动至分组最上层(分組過多, 导致第一个分组显示不全)
        self._swipe_group_list_to_top()

        if group < 1 or group > 7:
            raise ValueError('Switch soul_one group must be in [1-7]')
        if team < 1 or team > 4:
            raise ValueError('Switch soul_one team must be in [1-4]')
        # 这一步是选择组
        target_click, target_check = get_group_assets(group)
        self._click_group_twice(target_click)
        # 点击队伍：单次正式点击事务 + 有界观察确认框
        target_team = get_team_asset(team)
        if self._click_target_team(target_team):
            if self._observe_confirm_dialog():
                self._confirm_bondling_replace_dialog()
        else:
            logger.warning(f'Team {team} not found in group {group}, skip clicking')
        # 兜底若还出现确认按钮则点击
        self.ui_click_until_disappear(self.I_SOU_SWITCH_SURE)
        logger.info(f'Switch soul_one group {group} team {team}')

    def _group_list_text(self) -> str:
        """截一张新图并读分组列表文字；文本格式沿用原滑顶的 `str(list)`，只做精确相等比较。"""
        self.screenshot()
        results = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
        return str([result.ocr_text for result in results])

    def _swipe_group_list_to_top(self) -> bool:
        """数字模式：观察 → 滑一次 → settle → 再观察，列表文字不再变化才算到顶。

        每一滑都是一次独立的 `RuleSwipe` 手势（端点与轨迹每次重新采样），滑完先 settle、截新图、OCR，
        再由观察结果决定要不要发起下一滑；不预授权多滑。第一轮无条件探测滑一次——「滑之前和滑之后
        文字相同」才说明这一滑没有让列表移动。节奏归本循环所有，所以这里不传 `interval`：原来的
        `interval=1.5` 比一轮约 1 秒的循环还长，第二滑会被静默吞掉（见 e4e6be23），是否放行还取决于 OCR 快慢。

        返回 True = 列表已稳定；达到 `MAX_GROUP_TOP_SWIPES` 仍在变化返回 False，业务照常继续（不新增失败契约）。
        """
        previous = self._group_list_text()
        changes = []
        while 1:
            if len(changes) >= self.MAX_GROUP_TOP_SWIPES:
                logger.warning(f'Group list not stable after {len(changes)} swipes, continue anyway')
                return False
            self.swipe(self.S_SS_GROUP_SWIPE_UP)
            sleep(random_delay(*self.GROUP_TOP_SETTLE))
            current = self._group_list_text()
            changed = current != previous
            changes.append(changed)
            logger.debug(f'Group top swipe {len(changes)}/{self.MAX_GROUP_TOP_SWIPES}, changed={changed}')
            if not changed:
                logger.info(f'Group list stabilized after {len(changes)} swipe(s), changed={changes}')
                return True
            previous = current

    def _click_group_twice(self, target_click: RuleClick) -> None:
        """分组两次补点。

        分组切换没有可靠的成功标志（历史上的验证循环已换成无反馈点击），所以两次点击保留，
        本方法只管两次点击的时序：两次之间、第二次之后各有一段区间随机等待，语义不同、范围分开。
        每次 `click` 都重新采样落点（L1），这里不缓存坐标。
        """
        self.click(target_click)
        sleep(random_delay(*self.GROUP_CLICK_GAP))
        self.click(target_click)
        sleep(random_delay(*self.GROUP_SETTLE))

    def _click_target_team(self, target_team: RuleImage) -> bool:
        """队伍首次点击事务：识别 → NORMAL reaction → fresh confirm → 单次 L1 点击。

        返回 True 表示点击已经发出（恰好一次，不再补点）。reaction 后目标消失只是本次不点，
        在 `TEAM_FIND_TIMEOUT` 内重新识别；永远不复用 reaction 之前的旧坐标。窗口内始终没有点出去返回 False。
        """
        timer = Timer(self.TEAM_FIND_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear_then_click(target_team, policy=InteractionPolicy.NORMAL):
                return True
            if timer.reached():
                return False

    def _observe_confirm_dialog(self) -> bool:
        """队伍点击后在有界窗口内观察确认框，出现就走确认事务。

        没出现不是失败：已经装备同一预设时游戏不会弹确认框，窗口到期按当前业务语义正常结束。
        截图自带 0.3 秒最小间隔，轮询不会空转。返回确认框是否出现过。
        """
        timer = Timer(self.TEAM_RESPONSE_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear(self.I_SOU_SWITCH_SURE):
                self._confirm_team_switch()
                return True
            if timer.reached():
                logger.info('No confirm dialog after team click, preset may already be equipped')
                return False

    def _raise_confirm_stuck(self, what: str, timeout: float = None) -> None:
        """确认框始终点不掉：本地明确超时，交还 `script.py` 的 GamePageUnknownError 处理；调用方不会再写成功日志。"""
        message = f'{what} is still there after {timeout or self.CONFIRM_CLOSE_TIMEOUT}s'
        logger.error(message)
        raise GamePageUnknownError(message)

    def _press_sure(self) -> bool:
        """点预设确认框 / 契灵替换确认框的「确定」：CONFIRM reaction + fresh confirm，3 秒间隔。两处共用同一个点击点。"""
        return self.appear_then_click(self.I_SOU_SWITCH_SURE, interval=3, policy=InteractionPolicy.CONFIRM)

    def _confirm_team_switch(self) -> None:
        """确认框事务：首次确认走 CONFIRM reaction + fresh confirm；确认框仍在则沿用原有的 3 秒间隔重试。

        多开模拟器卡顿时确认框可能点不掉（4d74f701），所以后续恢复重试不叠加 reaction，保持原 interval=3。
        `I_CHECK_BLOCK` 是误触到式神检查的保护（e4e6be23），同样留在恢复循环里。
        注意 `appear_then_click` 的第二个位置参数是 `action`，间隔必须写成 `interval=`；
        原来写成位置参数 `3` 会在 `I_CHECK_BLOCK` 真正出现时把 `3` 当成点击动作而抛 AttributeError。
        """
        self._press_sure()
        timer = Timer(self.CONFIRM_CLOSE_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_CHECK_BLOCK, interval=3):
                continue
            if not self.appear(self.I_SOU_SWITCH_SURE):
                break
            if timer.reached():
                self._raise_confirm_stuck('Preset confirm dialog')
            self.click(self.I_SOU_SWITCH_SURE, 3)

    def _confirm_bondling_replace_dialog(self) -> bool:
        """预设确认之后，契灵已装配在其他阴阳师时游戏会再弹「是否替换」确认框，不处理会挡住后面的导航。

        用户选了这个预设就等于允许替换，不加配置：在 `REPLACE_OBSERVE_TIMEOUT` 内短时观察，出现就点「确定」
        （复用预设确认框的 `I_SOU_SWITCH_SURE`，同一位置的确定按钮；CONFIRM reaction + fresh confirm），
        再等它关闭。没出现返回 False，正常继续；点了关不掉（弹窗持续存在）在 `REPLACE_CLOSE_TIMEOUT` 后抛
        `GamePageUnknownError` 交还原有异常处理，不无限点击，调用方也不会记成切换成功。
        只在预设切换流程里、预设确认已经发生之后调用，不是全局的「看到确定就点」。
        点击走 `_press_sure`（3 秒间隔）：预设确认刚点过同一个按钮时，替换框的首次点击最多晚到 3 秒后，
        期间只是继续截图观察，不额外点击。
        """
        timer = Timer(self.REPLACE_OBSERVE_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear(self.I_SOU_SWITCH_SURE):
                break
            if timer.reached():
                return False
        logger.info('Bondling replace dialog after preset switch, confirm')
        close_timer = Timer(self.REPLACE_CLOSE_TIMEOUT).start()
        while 1:
            self._press_sure()
            self.screenshot()
            if not self.appear(self.I_SOU_SWITCH_SURE):
                return True
            if close_timer.reached():
                self._raise_confirm_stuck('Bondling replace dialog', self.REPLACE_CLOSE_TIMEOUT)

    def switch_souls(self, target: tuple or list[tuple]) -> None:
        """
        切换御魂
        :param target: [(1, 1), (2, 2), (3, 3), (4, 4)]  或者是单独的一个元组(4, 4) 第一个是组, 第二个是队伍
        :return:
        """
        if isinstance(target, tuple):
            target = [target]
        for group, team in target:
            group = int(group)
            team = int(team)
            self.switch_soul_one(group, team)

    def exit_shikigami_records(self) -> None:
        """
        退出式神录的界面
        :return:
        """
        while 1:
            self.screenshot()
            if not self.appear(self.I_SOU_CHECK_IN):
                break
            if self.appear_then_click(self.I_RECORD_SOUL_BACK, interval=3.5):
                continue
        logger.info('Exit shikigami records')

    def run_switch_soul_by_name(self, groupName, teamName):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(groupName, str) and isinstance(teamName, str):
            self.click_preset()
            self.switch_soul_by_name(groupName, teamName)

    def switch_soul_by_name(self, groupName, teamName):
        """按名称切换预设：分组回顶 → 从上到下找 → 重新定位并点击 → 确认选中、队伍列表就绪
        → 队伍回顶 → 从上到下找 → 重新定位 → 点击预设切换按钮并处理确认框。

        名称只做首尾去空白后的精确相等；找不到 / 同屏重名 / 画面不稳定都抛 `SwitchSoulNameError`
        （消息带目标名和阶段），不会回退到随便一个预设，也不会写成功日志。
        """
        logger.hr('Switch soul by name')
        group = normalize_target('分组', groupName)
        team = normalize_target('队伍', teamName)

        self._name_find(GROUP_LIST, group, self._name_to_top(GROUP_LIST, group))
        self._name_select_group(group)
        logger.info(f'Select group {group}')

        self._name_find(TEAM_LIST, team, self._name_to_top(TEAM_LIST, team))
        self._name_locate(TEAM_LIST, team, '点击前重新定位队伍')
        logger.info(f'Select team {team}')
        # 切换御魂
        cnt_click: int = 0
        confirmed = False
        sure_timer = None   # 「确定」连续出现的计时：这一帧看不到确定就清零；连续超过 CONFIRM_CLOSE_TIMEOUT 说明点不掉
        loop_timer = Timer(self.SWITCH_LOOP_TIMEOUT).start()   # 整个循环的总计时：确认框和队伍都识别不到 / 确认框间歇出现无进展都由它兜底
        while 1:
            self.screenshot()
            if cnt_click >= 4:
                break
            if loop_timer.reached():   # 放在所有 continue 分支之前，每轮都检查
                self._raise_confirm_stuck(f'Team switch loop (group={group}, team={team})', self.SWITCH_LOOP_TIMEOUT)
            if self.appear_then_click(self.I_SOU_SWITCH_SURE, interval=0.8):
                confirmed = True
                if sure_timer is None:
                    sure_timer = Timer(self.CONFIRM_CLOSE_TIMEOUT).start()
                elif sure_timer.reached():
                    self._raise_confirm_stuck('Preset confirm dialog')
                continue
            if sure_timer is not None and not self.appear(self.I_SOU_SWITCH_SURE):
                sure_timer = None
            if self._click_team_by_name(team, interval=1.5):
                cnt_click += 1
                continue
        # 预设确认过之后，契灵替换确认框可能稍后才出现；异常时抛出，不会走到下面的成功日志
        if confirmed:
            self._confirm_bondling_replace_dialog()
        logger.info(f'Switch soul_one group {group} team {team}')

    # ------------------------------------------------------------------ 按名称：读列表 / 滑动 / 稳定等待
    def _name_error(self, spec: _NameList, target: str, stage: str, detail: str, human: bool = False):
        """`human=True`：确定需要人工修正 / 判断（`SwitchSoulNameError`，走人工处理，不重启游戏）；
        默认是临时识别 / 页面问题（`SwitchSoulPageError`，沿用既有的重启恢复）。"""
        message = f'按名称切换预设失败：{spec.kind}「{target}」，阶段「{stage}」：{detail}'
        logger.error(message)
        return SwitchSoulNameError(message) if human else SwitchSoulPageError(message)

    def _name_stage_timeout(self, spec: _NameList) -> float:
        return self.NAME_STAGE_TIMEOUT * spec.timeout_scale

    def _name_read(self, spec: _NameList, fresh: bool = True) -> list:
        """截图并 OCR，返回按 y 排序的非空文本行。0 行时换帧重读，最多 `NAME_OCR_TRIES` 次；仍为空返回 []。"""
        rule = getattr(self, spec.rule)
        for attempt in range(self.NAME_OCR_TRIES):
            if fresh or attempt:
                self.screenshot()
            lines = parse_lines(rule.detect_and_ocr(self.device.image), rule.roi)
            if lines:
                return lines
        return []

    def _name_roi(self, *specs: _NameList) -> tuple:
        """帧差用的 (x1, y1, x2, y2)：这些列表 OCR 区域的外包框。"""
        boxes = [getattr(self, spec.rule).roi for spec in specs]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes))

    def _name_observe(self, baseline, roi: tuple, timeout: float):
        def frame():
            self.screenshot()
            return self.device.image

        return wait_for_changed_and_stable(
            baseline, frame, roi=roi, changed_threshold=self.NAME_CHANGED, stable_threshold=self.NAME_STABLE,
            stable_frames=self.NAME_STABLE_FRAMES, timeout=timeout, clock=lambda: monotonic())

    def _name_settle(self, spec: _NameList, target: str, stage: str, baseline, roi: tuple) -> str:
        """动作（滑动 / 点分组）之后等画面稳定，返回 'moved'（变化且已稳定）或 'static'（明确稳定且没有变化）。

        `FrameWaitResult.success` = 变化且稳定且没超时；超时不抛异常。变化了但一直不稳定的情况不能算正常完成、
        也不能当作到边界：换基准帧有界重观察，稳定后按「相对动作前是否真的变了」归类，仍不稳定就报错。
        """
        result = self._name_observe(baseline, roi, self.NAME_SETTLE_TIMEOUT)
        if result.success:
            return 'moved'
        if result.stable and not result.changed:
            return 'static'
        for _ in range(self.NAME_SETTLE_RETRIES):
            settled = self._name_observe(np.array(self.device.image), roi, self.NAME_SETTLE_RETRY_TIMEOUT)
            if settled.stable:
                moved = frame_difference(baseline, self.device.image, roi=roi) >= self.NAME_CHANGED
                return 'moved' if moved else 'static'
        raise self._name_error(spec, target, stage, '画面一直在变化、没有稳定下来，无法可靠识别（不当作到边界）')

    def _name_swipe(self, spec: _NameList, target: str, stage: str, attr: str) -> str:
        """用 `BaseTask.swipe(RuleSwipe)` 滑一次（端点采样 + 轨迹模型都在里面），再等稳定。

        没有发出的滑动（`swipe()` 返回 False，例如被 interval 限流）不算一次有效滑动，直接报错。
        """
        baseline = np.array(self.device.image)
        if not self.swipe(getattr(self, attr)):
            raise self._name_error(spec, target, stage, '滑动没有发出')
        return self._name_settle(spec, target, stage, baseline, self._name_roi(spec))

    def _name_guard(self, timer, spec: _NameList, target: str, stage: str) -> None:
        if timer.reached():
            raise self._name_error(spec, target, stage, f'超过 {self._name_stage_timeout(spec):.0f} 秒仍未完成')

    # ------------------------------------------------------------------ 按名称：回顶 / 找目标 / 点击前定位
    def _name_to_top(self, spec: _NameList, target: str) -> bool:
        """有界回到列表顶部：连续 `NAME_EDGE_CONFIRMS` 次「滑了但画面没变」才算到顶，且到顶那一帧必须读到有效文字。

        只凭文字相同不判到顶，OCR 读空也不判到顶（读空报错，不假定列表是空的）。
        返回回顶过程中是否有过真正生效的滑动（`_name_find` 用它判断滑动是不是全部无效）。
        """
        stage = f'回到{spec.kind}列表顶部'
        timer = Timer(self._name_stage_timeout(spec)).start()
        self._name_read(spec)
        edge = 0
        moved = False
        for index in range(spec.max_top):
            self._name_guard(timer, spec, target, stage)
            outcome = self._name_swipe(spec, target, stage, spec.to_top)
            moved = moved or outcome == 'moved'
            edge = edge + 1 if outcome == 'static' else 0
            logger.debug(f'{spec.kind} top swipe {index + 1}/{spec.max_top}: {outcome}')
            if edge >= self.NAME_EDGE_CONFIRMS:
                if not self._name_read(spec):
                    raise self._name_error(spec, target, stage, '到顶时 OCR 连续读不到文字，不能确认列表内容')
                logger.info(f'{spec.kind} list at top after {index + 1} swipe(s)')
                return moved
        raise self._name_error(spec, target, stage, f'滑动 {spec.max_top} 次仍没有到顶')

    def _name_pick(self, spec: _NameList, target: str, stage: str, lines: list):
        """本屏里的精确命中：0 个返回 None；同屏多个精确同名直接报歧义；被列表边缘裁切的行返回 None。"""
        hits = exact_matches(lines, target)
        if len(hits) > 1:
            raise self._name_error(spec, target, stage, f'同一屏出现 {len(hits)} 个完全同名的{spec.kind}，无法判断该点哪个，请把名称改成唯一的', human=True)
        if hits and is_complete(hits[0], spec.viewport):
            return hits[0]
        return None

    def _name_find(self, spec: _NameList, target: str, top_moved: bool = False):
        """从上到下逐屏找精确同名的目标，返回命中的行。

        没找到就向后翻页；连续 `NAME_EDGE_CONFIRMS` 次翻页画面都没变化、且本屏读到有效文字，才确认到底并报「没有这个名字」。
        只覆盖首次命中的那一屏：不同屏出现同名时不做全列表唯一性检查（成本高，且没有可靠依据）。
        「到底」还要有滑动真的生效过（回顶或翻页里出现过 moved），或者最后一行下面空着整整一行（列表本来就没满一屏）：
        否则可能只是滑动全部无效，属于页面问题（`SwitchSoulPageError`，沿用重启恢复），不能当作「名称不存在」转人工。
        """
        stage = f'在{spec.kind}列表中从上到下查找'
        timer = Timer(self._name_stage_timeout(spec)).start()
        edge = 0
        trail = []              # 依次出现过的不同内容（相邻相同的折叠掉：步幅小于一行时相邻两屏文字常常相同，不是循环）
        moved_any = top_moved
        for index in range(spec.max_pages):
            self._name_guard(timer, spec, target, stage)
            lines = self._name_read(spec)
            if not lines:
                raise self._name_error(spec, target, stage, 'OCR 连续读不到任何文字，不能判断目标在不在')
            hit = self._name_pick(spec, target, stage, lines)
            if hit is None and edge >= self.NAME_EDGE_CONFIRMS:
                # 已确认在底部：被下沿裁切的命中也只能在这里用了（再没有更后面的内容可以滑出来）
                hits = exact_matches(lines, target)
                if hits:
                    hit = hits[0]
            if hit is not None:
                logger.info(f'Found {spec.kind} {target} on screen {index + 1}')
                return hit
            if edge >= self.NAME_EDGE_CONFIRMS:
                blank_below = spec.viewport[1] - max(line.y + line.h for line in lines) >= spec.row_pitch
                if not (moved_any or blank_below):
                    raise self._name_error(spec, target, stage, '所有滑动都没有让列表移动，无法确认已经翻到底（可能是滑动无效）')
                raise self._name_error(spec, target, stage, f'已从确认的顶部翻到确认的底部（共看了 {index + 1} 屏，OCR 有效），没有这个名字；'
                                                              f'请核对名称是否写对（也可能是 OCR 把它读错了）', human=True)
            signature = tuple(line.text for line in lines)
            if not trail or signature != trail[-1]:
                if signature in trail:
                    raise self._name_error(spec, target, stage, '翻页后又回到了之前出现过的内容，疑似列表循环')
                trail.append(signature)
            outcome = self._name_swipe(spec, target, stage, spec.forward)
            moved_any = moved_any or outcome == 'moved'
            edge = edge + 1 if outcome == 'static' else 0
        raise self._name_error(spec, target, stage, f'翻了 {spec.max_pages} 屏仍没有找到，也没有确认到底（达到保护上限，不是名称不存在）')

    def _name_locate(self, spec: _NameList, target: str, stage: str):
        """点击前重新定位：连续两帧都只命中一个、且 y 基本一致才返回；旧 OCR 坐标不跨滑动 / 刷新使用。"""
        timer = Timer(self._name_stage_timeout(spec)).start()
        for _ in range(self.NAME_LOCATE_TRIES):
            self._name_guard(timer, spec, target, stage)
            first = self._name_pick(spec, target, stage, self._name_read(spec))
            second = self._name_pick(spec, target, stage, self._name_read(spec))
            if first is not None and second is not None and abs(first.y - second.y) <= self.NAME_POS_TOL:
                return second
        raise self._name_error(spec, target, stage, '点击前连续两帧都无法稳定定位到目标（可能列表仍在滚动，或目标被遮挡）')

    def _group_selection_state(self, line) -> str:
        """当前帧里分组列表的「选中标志」与目标行的关系：'target'（标志只有一个且落在目标行）/ 'other'（只有一个，在别的行）/
        'none'（没有任何标志：选中的分组可能滚到了可视区外，也可能模板识别不到）/ 'ambiguous'（多个标志，无法判断）。

        用 `copy.copy` 临时放宽搜索范围，不改共享资源（含被皮肤替换过的 file / 阈值）。
        """
        rule = copy.copy(self.I_SOU_CHECK_GROUP_2)
        matches = rule.match_all_any(self.device.image, roi=list(self.NAME_MARKER_COLUMN))
        boxes = parse_matches(rule, matches)
        if not boxes:
            return 'none'
        if len(boxes) > 1:
            return 'ambiguous'
        _, y, _, h = boxes[0]
        if abs((y + h / 2) - (line.y + line.h / 2)) <= self.NAME_MARKER_TOL:
            return 'target'
        return 'other'

    def _name_team_ready(self, group: str, baseline, require_change: bool) -> None:
        """分组确认之后单独检查中央队伍列表就绪：先前不是目标分组时，列表必须相对点击前「变化并稳定」（读到旧内容 = 还没刷新）；
        本来就是目标分组时只要求稳定。变化后一直不稳定是临时问题，多轮观察仍无变化则无法排除读到旧分组，转人工。
        """
        stage = '等待中央队伍列表刷新'
        roi = self._name_roi(TEAM_LIST)
        for _ in range(self.NAME_TEAM_READY_ROUNDS):
            outcome = self._name_settle(TEAM_LIST, group, stage, baseline, roi)
            if outcome == 'moved' or not require_change:
                return
        raise self._name_error(TEAM_LIST, group, stage, '分组已显示选中，但中央队伍列表一直没有变化，无法排除读到的是旧分组的队伍，不继续选队伍', human=True)

    def _name_select_group(self, group: str) -> None:
        """点击分组并确认选中，再单独确认中央队伍列表就绪。

        选中的依据是「选中标志落在目标行」这个状态证据（数字模式的选中高亮模板，见 `NAME_MARKER_COLUMN`），而不是
        「区域变了」或「队伍列表读得到文字」：动画 / 无关区域变化、旧分组的列表都不能算选组成功。
        - 点击前标志已在目标行：本来就是目标分组，不点击，只确认中央列表稳定；
        - 否则点击（最多 `NAME_GROUP_CLICK_TRIES` 次，每次点击前都重新定位）→ 等分组区域稳定 → 再检查标志；
        - 始终确认不了（标志在别的行 / 没有标志 / 多个标志）：转人工，不继续找队伍，避免点到旧分组里的同名队伍。
        """
        stage = '点击分组并确认选中'
        rule = getattr(self, GROUP_LIST.rule)
        group_roi = self._name_roi(GROUP_LIST)
        selected_before = False
        team_baseline = None
        state = 'none'
        for attempt in range(self.NAME_GROUP_CLICK_TRIES + 1):
            line = self._name_locate(GROUP_LIST, group, '点击前重新定位分组')
            state = self._group_selection_state(line)
            if attempt == 0:
                selected_before = state == 'target'
                team_baseline = np.array(self.device.image)
            if state == 'target':
                break
            if attempt == self.NAME_GROUP_CLICK_TRIES:
                break
            baseline = np.array(self.device.image)
            self._click_line(_LineTarget(rule.name, line))
            self._name_settle(GROUP_LIST, group, stage, baseline, group_roi)
        if state != 'target':
            reason = {
                'other': '点击后选中标志仍在别的分组上（点击没有生效）',
                'none': '没有识别到任何分组选中标志（缺：选中某个分组时右侧分组列表的整屏截图，用来核对 ss_sou_check_group_* 模板在当前页面能否识别）',
                'ambiguous': '同时识别到多个分组选中标志，无法判断选中了哪个',
            }[state]
            raise self._name_error(GROUP_LIST, group, stage, f'无法确认目标分组已选中：{reason}。不继续选队伍，避免点到旧分组里的同名队伍', human=True)
        self._name_team_ready(group, team_baseline, require_change=not selected_before)
        if not self._name_read(TEAM_LIST):
            raise self._name_error(TEAM_LIST, group, '读取中央队伍列表', '分组已确认选中，但队伍列表读不到任何文字')
        logger.info(f'Group {group} selection confirmed (marker on target row, already_selected={selected_before}), team list ready')

    def _click_team_by_name(self, team: str, interval: float) -> bool:
        """确认循环里的一次队伍点击：按 `interval` 限流 → 对当前帧 OCR → 只命中一个完整的精确同名行才点（预设按钮列）。"""
        rule = getattr(self, TEAM_LIST.rule)
        timer = self.interval_timer.get(rule.name)
        if timer is None or timer.limit != interval:
            timer = self.interval_timer[rule.name] = Timer(interval)
        if not timer.reached():
            return False
        timer.reset()
        stage = '确认循环中点击队伍'
        lines = parse_lines(rule.detect_and_ocr(self.device.image), rule.roi)
        hit = self._name_pick(TEAM_LIST, team, stage, lines)
        if hit is None:
            return False
        self._click_line(_LineTarget(rule.name, hit), self.I_SOU_CLICK_PRESENT)
        return True

    def _click_line(self, target, action=None) -> None:
        """按命中行点击：y 来自 OCR 命中行；给了 `action`（预设按钮列）时 x 取按钮列，否则整点取自命中行。

        两轴各已采样一次，组合点就是最终落点，不再采样（`test_l1_click_pipeline` 的 case 23 守这一点）。
        """
        x, y = target.coord()
        if action is not None:
            x = action.coord()[0]
        execute_single_click(self.device, FinalPoint(x, y), control_name=target.name)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    s = SwitchSoul(c, d)

    s.click_preset()
    # s.switch_soul_one(4, 1)
    # s.switch_soul_by_name('契灵', '茨球')
    s.switch_soul_by_name('默认分组', '队伍5')
