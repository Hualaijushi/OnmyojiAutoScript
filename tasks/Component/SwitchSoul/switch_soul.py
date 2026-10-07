# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from typing import Union

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.click_pipeline import FinalPoint, execute_single_click
from module.interaction_policy import InteractionPolicy
from tasks.base_task import BaseTask
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets
from module.logger import logger


def switch_parser(switch_str: str) -> tuple:
    switch_list = switch_str.split(',')
    if len(switch_list) != 2:
        raise ValueError('Switch_str must be 2 length')
    return int(switch_list[0]), int(switch_list[1])


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
            self._observe_confirm_dialog()
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

    def _confirm_team_switch(self) -> None:
        """确认框事务：首次确认走 CONFIRM reaction + fresh confirm；确认框仍在则沿用原有的 3 秒间隔重试。

        多开模拟器卡顿时确认框可能点不掉（4d74f701），所以后续恢复重试不叠加 reaction，保持原 interval=3。
        `I_CHECK_BLOCK` 是误触到式神检查的保护（e4e6be23），同样留在恢复循环里。
        注意 `appear_then_click` 的第二个位置参数是 `action`，间隔必须写成 `interval=`；
        原来写成位置参数 `3` 会在 `I_CHECK_BLOCK` 真正出现时把 `3` 当成点击动作而抛 AttributeError。
        """
        self.appear_then_click(self.I_SOU_SWITCH_SURE, interval=3, policy=InteractionPolicy.CONFIRM)
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_CHECK_BLOCK, interval=3):
                continue
            if not self.appear(self.I_SOU_SWITCH_SURE):
                break
            self.click(self.I_SOU_SWITCH_SURE, 3)

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
        """
        保证在式神录的界面
        :return:
        """
        logger.hr('Switch soul by name')
        # 滑动至分组最上层
        last_group_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            now_group_text = str([result.ocr_text for result in compare1])
            if now_group_text == last_group_text:
                break
            self.swipe(self.S_SS_GROUP_SWIPE_UP, 2)
            sleep(2.5)
            last_group_text = now_group_text
        logger.info('Swipe to top of group')

        # 判断有无目标分组
        while 1:
            self.screenshot()
            # 获取当前分组名
            results = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            text1 = [result.ocr_text for result in results]
            # 判断当前分组有无目标分组
            result = set(text1).intersection({groupName})
            # 有则跳出检测
            if result and len(result) > 0:
                break
            self.swipe(self.S_SS_GROUP_SWIPE_DOWN)
            sleep(1.5)
        logger.info('Swipe down to find target group')

        # 选中分组
        while 1:
            self.screenshot()
            self.O_SS_GROUP_NAME.keyword = groupName
            if self.ocr_appear_click(self.O_SS_GROUP_NAME):
                break
        logger.info(f'Select group {groupName}')

        # 滑动至阵容最上层
        last_team_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_TEAM_NAME.detect_and_ocr(self.device.image)
            now_team_text = str([result.ocr_text for result in compare1])
            # 向上滑动
            if now_team_text == last_team_text:
                break
            self.swipe(self.S_SS_TEAM_SWIPE_DOWN, 1.5)
            sleep(2)
            last_team_text = now_team_text
        logger.info('Swipe to top of team')

        # 判断当前分组有无目标阵容
        while 1:
            self.screenshot()
            # 获取当前阵容名
            results = self.O_SS_TEAM_NAME.detect_and_ocr(self.device.image)
            text1 = [result.ocr_text for result in results]
            # 判断当前分组有无目标阵容
            result = set(text1).intersection({teamName})
            # 有则跳出检测
            if result and len(result) > 0:
                break
            self.swipe(self.S_SS_TEAM_SWIPE_UP, 0.3)
        logger.info('Swipe up to find target team')

        # 选中分组
        logger.info(f'Select team {teamName}')
        # 切换御魂
        cnt_click: int = 0
        self.O_SS_TEAM_NAME.keyword = teamName
        while 1:
            self.screenshot()
            if cnt_click >= 4:
                break
            if self.appear_then_click(self.I_SOU_SWITCH_SURE, interval=0.8):
                continue
            if self.ocr_appear_click_by_rule(self.O_SS_TEAM_NAME, self.I_SOU_CLICK_PRESENT, interval=1.5):
                cnt_click += 1
                continue
        logger.info(f'Switch soul_one group {groupName} team {teamName}')

    def ocr_appear_click_by_rule(self,
                                 target: RuleOcr,
                                 action: Union[RuleClick, RuleLongClick] = None,
                                 interval: float = None,
                                 duration: float = None) -> bool:
        """
        ocr识别目标，如果目标存在，则触发动作
        :param target:
        :param action:
        :param interval:
        :param duration:
        :return:
        """
        appear = self.ocr_appear(target, interval)

        if not appear:
            return False

        x1, y1 = target.coord()
        x, y = action.coord()

        # 按钮列（action 采样的 x）× 命中队伍名所在行（OCR 采样的 y）：两轴各已采样一次，
        # 组合点就是最终落点，不再采样。
        execute_single_click(self.device, FinalPoint(x, y1), control_name=target.name)
        return True


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
