# This Python file uses the following encoding: utf-8
# @author AzurTian
import time
from datetime import datetime, timedelta

from module.logger import logger
from module.interaction_policy import InteractionPolicy
from tasks.Exploration.base import BaseExploration, BOSS_EXIT_EXITING, BOSS_EXIT_EXITED
from tasks.Exploration.config import AutoRotate, UserStatus, ExplorationLevel
import tasks.Exploration.page as pages
from tasks.GameUi.page_definition import Page
from typing import Callable


class InviteFailedException(Exception):
    pass


class ScriptTask(BaseExploration):
    """探索"""

    def confirm_page(self, page: Page, skip_first_screenshot: bool = True) -> bool:
        """探索页面跳转更改为单帧确认"""
        self.maybe_screenshot(skip_first_screenshot)
        return self.match_page_once(page)

    def arrive_end(self) -> bool:
        # 28章直接匹配
        if self._config.exploration_config.exploration_level == ExplorationLevel.EXPLORATION_28:
            return self.appear(self.I_SWIPE_END)
        return super().arrive_end()

    @property
    def exp_page_handle_dict(self) -> dict[Page, Callable]:
        return {
            pages.page_exp_main: self.run_on_exp_main,
            pages.page_exp_settings: self.run_on_exp_settings,
            pages.page_exp_exit: self.run_on_exp_exit,
            pages.page_exp_entrance: self.run_on_exp_entrance,
            pages.page_exploration: self.run_on_exp,
            pages.page_battle_prepare: self.run_on_battle,
            pages.page_battle: self.run_on_battle,
            pages.page_battle_result: self.run_on_battle,
            pages.page_reward: lambda : self.click(pages.random_click(), interval=0.8),
            pages.page_battle_team: self.run_on_battle_team
        }

    def run(self):
        logger.hr('exploration')
        self.pre_process()
        if self.user_status == UserStatus.ALONE:
            self.begin_fatigue_task('Exploration')
        self.exec_exp_page()
        self.post_process()

    def _maybe_boss_cycle_fatigue(self) -> bool:
        """Boss 胜利直退完成、已观察到合法外层页后的疲劳安全节点。

        调用点在 `run_on_exp_entrance` / `run_on_exp` 顶部——这两个 handler 只在
        `exec_exp_page` 的 `get_current_page()` 正向命中外层页时才分发。标记在这里一次性消费
        （所有角色都消费，避免残留到下一轮重复休息），仅 solo 真正休息；命中后调用方 `return`，
        交 `exec_exp_page` 下一轮 fresh screenshot + 重新分发 = 休息后的新截图确认。
        不在 `page_exp_main` 触发。

        :return: 本轮是否命中安全节点（命中则调用方应 return）
        """
        if not self._boss_cycle_fatigue_due:
            return False
        self._boss_cycle_fatigue_due = False
        if self.user_status != UserStatus.ALONE:
            return False
        self.try_fatigue_break(
            safe=True,
            repeat_completed=True,
            deadline=self.start_time + self.limit_time,
        )
        return True

    def _collect_outer_treasure_box(self) -> bool:
        """外层补领宝箱；Boss 直退交接期内不补领刚才跳过的宝箱。"""
        if self._boss_exit_phase == BOSS_EXIT_EXITED:
            return False
        return self.collect_treasure_box()

    def exec_exp_page(self):
        pages.page_battle_team_exit = self.navigator.resolve_page(pages.page_battle_team_exit)
        pages.page_battle_team_exit.connect(pages.page_exp_entrance, self.I_UI_CONFIRM, key="page_battle_team_exit->page_exp_entrance")
        while True:
            self.screenshot()
            self.guard_boss_exit_deadline()
            current_page = self.get_current_page()
            self.observe_boss_exit_outer(current_page)
            if current_page is None:
                time.sleep(0.5)
                continue
            # Boss 直退进行中先完成本轮退出（有 guard_boss_exit_deadline 兜底），不在中途收尾
            if self.check_exit(current_page) and self._boss_exit_phase != BOSS_EXIT_EXITING:
                self.appear_then_click(self.I_UI_CANCEL, interval=0.8)  # 处理队长结束的邀请弹窗
                break
            handle = self.exp_page_handle_dict.get(current_page, None)
            if handle is None:
                if self._boss_exit_phase == BOSS_EXIT_EXITING:
                    time.sleep(0.5)  # 退出途中的未知页面只观察，不盲点
                    continue
                self.goto_page(pages.page_exploration)
                continue
            try:
                handle()
                self.pre_page = current_page  # 更新上一个页面为当前页面
            except InviteFailedException as e:
                logger.warning(e)
                break

    def run_on_exp_main(self):
        if self.pre_page and self.pre_page != pages.page_exp_main:
            # 防止因延迟过大, 一直在主界面和奖励页面切换导致too many click
            self.device.click_record_clear()
        if self._boss_exit_phase == BOSS_EXIT_EXITING:
            # Boss 已确认胜利：跳过地图宝箱 / 小纸人（与 collect_paper_reward 开关无关），直接退出
            self.quit_exp_main()
            return
        self.end_boss_exit_handoff()
        if self.collect_reward():
            return
        if self.user_status != UserStatus.ALONE:
            if self.fire_monster_type == 'boss':
                return
            if not self.appear(self.I_TEAM_EMOJI):
                logger.info('Friend disappeared, quit')
                self.quit_exp_main()
                return
        if self.switch_rotate() or self.user_status == UserStatus.MEMBER:
            return
        fire_button = self.get_fire_button()
        if fire_button is not None and self.fire(fire_button):
            return
        if self.fire_monster_type != 'boss' and self.swipe(self.S_SWIPE_BACKGROUND_RIGHT, interval=1.5) and self.arrive_end():
            self.quit_exp_main()

    def run_on_exp_entrance(self):
        # 回到外层稳定页：完整业务循环结束，先走 solo Boss 疲劳安全节点（命中则交下一轮 fresh dispatch）
        if self._maybe_boss_cycle_fatigue():
            return
        self._collect_outer_treasure_box()
        self.fire_monster_type = ''  # 入口处重置怪物类型
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                if self.check_and_invite(self._config.invite_config.default_invite):
                    return
                if datetime.now() - self.wait_start_time >= timedelta(seconds=10) or self.current_count == 0:
                    self.enter_team()
            case UserStatus.ALONE:
                self.goto_page(pages.page_exp_main)
            case UserStatus.MEMBER:
                self.check_then_accept()
                self.device.stuck_record_clear()

    def run_on_exp(self):
        # 同 run_on_exp_entrance：外层稳定页，先走 solo Boss 疲劳安全节点
        if self._maybe_boss_cycle_fatigue():
            return
        self.fire_monster_type = ''  # 入口处重置怪物类型
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                # TODO: 队长宝箱收集(游戏问题导致邀请和宝箱出现时间不一致, 一旦先点中宝箱就会出现卡死), 当前先取消队长在探索界面的宝箱收集
                if self.check_and_invite(self._config.invite_config.default_invite):
                    return
                if datetime.now() - self.wait_start_time >= timedelta(seconds=10) or self.current_count == 0:
                    self.goto_page(pages.page_exp_entrance)
            case UserStatus.ALONE:
                self._collect_outer_treasure_box()
                self.goto_page(pages.page_exp_main)
            case UserStatus.MEMBER:
                self._collect_outer_treasure_box()
                self.check_then_accept()
                self.device.stuck_record_clear()

    def run_on_battle(self):
        # 归属只消费一次，上一场的 Boss 标记不会污染后续战斗
        target, self._battle_target = self._battle_target, ''
        self.end_boss_exit_handoff()
        won = self.run_general_battle(self._config.general_battle_config, exit_matcher=pages.page_exp_main)
        self._match_end.refresh()  # 防止同一张图多次打怪导致误以为探索结束
        self.wait_start_time = datetime.now()  # 队友等待时间重置
        # 通用战斗确认胜利且本场归属 Boss 才直退；战败 / 主动退出 / 未能开战都不算
        if won is True and target == 'boss':
            self.begin_boss_exit()

    def run_on_battle_team(self):
        self.end_boss_exit_handoff()
        self.need_exit = False
        match self.user_status:
            case UserStatus.LEADER:
                if self.run_invite(self._config.invite_config, self.current_count == 0):
                    return
                raise InviteFailedException('Invite failed, quit')
            case UserStatus.ALONE:
                self.goto_page(pages.page_exp_main)

    def run_on_exp_settings(self):
        if self._config.exploration_config.auto_rotate == AutoRotate.no:
            self.goto_page(pages.page_exp_main)
            return
        self.fill_shikigami()
        # 设置页开关：含义明确的稳定按钮，FAST reaction
        self.appear_then_click(self.I_E_AUTO_ROTATE_OFF, interval=0.8, policy=InteractionPolicy.FAST)

    def run_on_exp_exit(self):
        if not self.need_exit: # 不需要退出则点取消, 通常是直接在探索界面启动脚本(或退出期间在主界面再次识别到需要攻击的怪物)
            # 取消退出：NAVIGATION reaction
            self.appear_then_click(self.I_E_EXIT_CANCEL, interval=0.8, policy=InteractionPolicy.NAVIGATION)
            return
        # 退出确认：CONFIRM reaction（confirm_delay 会在 delay 后重新截图二次确认，
        # 若此时游戏已自动离开退出弹窗则不点，天然避免 stale click）
        self.appear_then_click(self.I_E_EXIT_CONFIRM, interval=0.8, policy=InteractionPolicy.CONFIRM)
        self.wait_start_time = datetime.now()  # 队友等待时间重置


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('丰年2')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run()
