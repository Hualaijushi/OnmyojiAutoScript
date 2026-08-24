"""账号轮换每日琐事专用的麒麟和阴界之门适配流程。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from module.exception import ScriptError
from module.logger import logger
from module.multi_account.daily_task_schedule import is_daily_task_due
from tasks.Component.GeneralBattle.assets import GeneralBattleAssets
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.GameUi.page import page_hunt, page_hunt_kirin, page_main, page_reward, page_town
from tasks.Hunt.assets import HuntAssets


@dataclass(frozen=True, slots=True)
class HuntRotationAdapter:
    """复用 Hunt 页面资源，但不调用 Hunt.run() 的局部适配器。"""

    owner: object
    entry_timeout: float = 30.0
    battle_timeout: float = 20.0
    exit_timeout: float = 12.0
    battle_seconds: float = 5.0

    @staticmethod
    def _is_available(mode: str, now: datetime) -> bool:
        """按独立 Hunt 的规则判断当前活动是否处于可挑战时间。"""
        return mode in {"hunt_kirin", "hunt_netherworld"} and is_daily_task_due(mode, now)

    def run_kirin_rotation(self) -> bool | None:
        """执行账号轮换模式的麒麟短战斗。非麒麟日返回 None。"""
        if not self._is_available("hunt_kirin", datetime.now()):
            logger.info("账号轮换跳过麒麟：当前不是周一至周四")
            return None
        return self._run_mode(
            mode="hunt_kirin",
            page=page_hunt_kirin,
            challenge=HuntAssets.I_KIRIN_CHALLAGE,
            done=HuntAssets.I_KIRIN_END,
            prepare=True,
        )

    def run_netherworld_rotation(self) -> bool | None:
        """执行账号轮换模式的阴界之门短战斗。非阴界之门日返回 None。"""
        if not self._is_available("hunt_netherworld", datetime.now()):
            logger.info("账号轮换跳过阴界之门：当前不是周五至周日")
            return None
        return self._run_mode(
            mode="hunt_netherworld",
            page=page_hunt,
            challenge=HuntAssets.I_NW_CHALLAGE,
            done=HuntAssets.I_NW_DONE,
            prepare=False,
        )

    def _run_mode(self, *, mode, page, challenge, done, prepare: bool) -> bool:
        if not self.owner.goto_page(page, timeout=int(self.entry_timeout)):
            error_type = ScriptError if mode == "hunt_netherworld" else TimeoutError
            raise error_type(f"{mode} 活动页面进入超时")

        deadline = time.monotonic() + self.entry_timeout
        while time.monotonic() < deadline:
            self.owner.screenshot()
            if self.owner.appear(done):
                logger.info("账号轮换%s已显示当天完成", mode)
                return True
            if self._is_real_battle():
                if mode == "hunt_netherworld":
                    return self._short_battle(mode, page, error_type=ScriptError)
                return self._short_battle(mode, page)
            if prepare and self.owner.appear_then_click(GeneralBattleAssets.I_PREPARE_HIGHLIGHT, interval=0.5):
                continue
            if not prepare:
                room_state = self._handle_netherworld_room()
                if room_state is True:
                    return self._wait_and_short_battle(mode, page)
                if room_state is False:
                    continue
            if not prepare and self.owner.appear_then_click(HuntAssets.I_NW, interval=0.9):
                continue
            if self.owner.appear_then_click(self.owner.I_UI_CONFIRM, interval=0.6):
                continue
            if self.owner.appear_then_click(challenge, interval=0.8):
                continue
            time.sleep(0.1)
        error_type = ScriptError if mode == "hunt_netherworld" else TimeoutError
        raise error_type(f"{mode} 等待进入真实战斗超时")

    def _handle_netherworld_room(self) -> bool | None:
        """处理阴界之门已有房间，所有等待均受外层超时保护。"""
        if not self.owner.appear(GeneralInviteAssets.I_GI_EMOJI_1) and not self.owner.appear(
            GeneralInviteAssets.I_GI_EMOJI_2
        ):
            return None
        if self.owner.appear_then_click(GeneralInviteAssets.I_FIRE, interval=0.6, threshold=0.7):
            return True
        if self.owner.appear_then_click(GeneralInviteAssets.I_FIRE_SEA, interval=0.6, threshold=0.7):
            return True
        return False

    def _wait_and_short_battle(self, mode, exit_page) -> bool:
        """确认进入真实战斗后执行账号轮换专用短战斗。"""
        deadline = time.monotonic() + self.battle_timeout
        while time.monotonic() < deadline:
            self.owner.screenshot()
            if self._is_real_battle():
                return self._short_battle(mode, exit_page, error_type=ScriptError)
            if self.owner.appear_then_click(GeneralBattleAssets.I_PREPARE_HIGHLIGHT, interval=0.5):
                continue
            time.sleep(0.1)
        raise ScriptError(f"{mode} 等待进入真实战斗超时")

    def _is_real_battle(self) -> bool:
        """只用战斗信息标志确认已经进入真实战斗，不把准备页算作战斗。"""
        return bool(self.owner.appear(GeneralBattleAssets.I_BATTLE_INFO))

    def _battle_finished(self) -> bool:
        """确认战斗自然结束或已经进入结算/奖励页面。"""
        if any(
            self.owner.appear(marker)
            for marker in (
                GeneralBattleAssets.I_WIN,
                GeneralBattleAssets.I_REWARD,
                GeneralBattleAssets.I_REWARD_GOLD,
            )
        ):
            return True
        current = self.owner.get_current_page(skip_first_screenshot=True, fallback=False)
        return current is page_reward

    def _short_battle(self, mode, exit_page, error_type=None) -> bool:
        """从真实战斗状态开始计时，约五秒后退出并确认退出成功。"""
        start = time.monotonic()
        logger.info("账号轮换%s确认进入真实战斗，开始计时 %.1f 秒", mode, self.battle_seconds)
        while time.monotonic() - start < self.battle_seconds:
            self.owner.screenshot()
            if self._battle_finished():
                logger.info("账号轮换%s在五秒内自然结束", mode)
                return self._return_to_activity(mode, exit_page, error_type=error_type or TimeoutError)
            time.sleep(0.15)
        if error_type is None:
            return self._exit_battle(mode, exit_page)
        return self._exit_battle(mode, exit_page, error_type=error_type)

    def _exit_battle(self, mode, exit_page, error_type=TimeoutError) -> bool:
        """使用通用战斗退出图标，但在适配层增加超时和页面确认。"""
        deadline = time.monotonic() + self.exit_timeout
        clicked = False
        while time.monotonic() < deadline:
            self.owner.screenshot()
            if self._battle_finished():
                return self._return_to_activity(mode, exit_page, error_type=error_type)
            if self.owner.appear_then_click(GeneralBattleAssets.I_EXIT_ENSURE, interval=0.5):
                clicked = True
                continue
            if self.owner.appear_then_click(GeneralBattleAssets.I_EXIT, interval=0.5):
                clicked = True
                continue
            if clicked and not self._is_real_battle():
                return self._return_to_activity(mode, exit_page, error_type=error_type)
            time.sleep(0.1)
        raise error_type(f"{mode} 退出战斗超时")

    def _return_to_activity(self, mode, activity_page, error_type=TimeoutError) -> bool:
        """退出结算页并确认回到对应活动页。"""
        try:
            current = self.owner.get_current_page(skip_first_screenshot=True, fallback=True)
            if current in (activity_page, page_main, page_town):
                logger.info("账号轮换%s退出战斗成功，当前页面=%s", mode, current)
                return True
            if self.owner.goto_page(activity_page, timeout=5):
                logger.info("账号轮换%s退出战斗成功", mode)
                return True
            # 结算页有时不能直接规划回活动页，回到主页面同样说明已经离开战斗。
            if self.owner.goto_page(page_main, timeout=5):
                logger.info("账号轮换%s退出战斗成功，已回到主页面", mode)
                return True
        except Exception as exc:
            logger.warning("账号轮换%s退出后返回活动页失败: %s", mode, exc)
        raise error_type(f"{mode} 退出后页面状态无法确认")
