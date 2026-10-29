# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import timedelta, datetime, time, date

from module.base.timer import Timer
from module.base.utils.random import random_int
from module.exception import TaskEnd
from module.interaction_policy import InteractionPolicy
from module.logger import logger

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_hunt, page_hunt_kirin, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Hunt.assets import HuntAssets

KIRIN, NETHERWORLD = 'kirin', 'netherworld'
# 进入战斗的结果：进了战斗 / 今天已挑战 / 没进去（时段内稍后再试）
BATTLE, DONE, TIMEOUT = 'battle', 'done', 'timeout'


class ScriptTask(GameUi, GeneralBattle, GeneralInvite, SwitchSoul, HuntAssets):
    # 开放时间（用户 2026-10-23 确认）：麒麟周一至周四 06:00–23:00，阴界之门周五至周日 18:00–23:00
    WINDOWS = {KIRIN: (time(6, 0), time(23, 0)), NETHERWORLD: (time(18, 0), time(23, 0))}
    # 雷麒麟固定在周四（用户 2026-10-23 确认），可单独配一套式神录预设
    THUNDER_KIRIN_WEEKDAY = 3
    KIRIN_ENTER_TIMEOUT = 60
    NW_ENTER_TIMEOUT = 60
    BACK_TIMEOUT = 10
    RETRY = timedelta(minutes=10)

    def run(self):
        now = datetime.now()
        mode = self._hunt_mode(now.date())
        start, end = self._window(mode, now.date())
        logger.info(f'Today is the {mode} day')
        if now < start:
            self._schedule(self._daily_plan(mode, now.date()))
            raise TaskEnd('Hunt')
        if now > end:
            self._schedule_next_day(now)
            raise TaskEnd('Hunt')

        self._switch_souls(mode, now.date())
        if mode == KIRIN:
            self.goto_page(page_hunt_kirin)
            result = self.kirin()
        else:
            self.goto_page(page_hunt)
            result = self.netherworld()
        sleep(1)

        if result == TIMEOUT:
            retry = datetime.now() + self.RETRY
            if retry < end:
                logger.warning(f'Did not get into the {mode} battle, retry at {retry}')
                self._schedule(retry)
                raise TaskEnd('Hunt')
        self._schedule_next_day(datetime.now())
        raise TaskEnd('Hunt')

    @staticmethod
    def _hunt_mode(day: date) -> str:
        """周一至周四是麒麟，周五至周日是阴界之门。"""
        return KIRIN if day.weekday() <= 3 else NETHERWORLD

    def _window(self, mode: str, day: date) -> tuple[datetime, datetime]:
        start, end = self.WINDOWS[mode]
        return datetime.combine(day, start), datetime.combine(day, end)

    def _planned_time(self, mode: str, day: date) -> datetime:
        """当天的计划时间 = 配置的运行时间；不在开放时间内就用开放时间。

        早于开放时间的配置（比如阴界之门设 17:30）以前会把下次运行排到今天已经过去的时间，调度器立刻又跑，一直空转到开放。
        """
        hunt_time = self.config.hunt.hunt_time
        configured = hunt_time.kirin_time if mode == KIRIN else hunt_time.netherworld_time
        start, end = self._window(mode, day)
        planned = datetime.combine(day, configured)
        return planned if start <= planned <= end else start

    def _daily_plan(self, mode: str, day: date) -> datetime:
        """正常每日计划 = 有效基准时间 + 一次随机延迟，写入排期前只算这一次。

        随机延迟的上限是 `Hunt.scheduler.float_time`，并且先按当天开放窗口缩小范围再采样：基准离截止点还剩
        N 秒，延迟就在 [0, min(float_time, N - 1)] 里均匀抽，不会先抽大延迟再统一截到 23:00 堆在截止点。
        - 减 1 秒：计划时间必须严格早于截止点，23:00:00 醒来时 `now > end` 已经算过窗口（与 10 分钟重试
          的 `retry < end` 一致）。
        - 基准已经在截止点上（配置 23:00:00）或只剩 1 秒：没有可随机的空间，保持基准，不改到第二天。
        - float_time 为 0 不采样，保持原来的确定时间。
        失败后的 10 分钟重试不走这里（`run` 里直接 `_schedule(retry)`），不加 float_time。
        """
        base = self._planned_time(mode, day)
        float_time = self.config.hunt.scheduler.float_time
        limit = float_time.hour * 3600 + float_time.minute * 60 + float_time.second
        _, end = self._window(mode, day)
        room = int((end - base).total_seconds()) - 1
        allowed = min(limit, room)
        if allowed <= 0:
            return base
        delay = random_int(0, allowed)
        logger.info(f'Hunt {mode} plan: base {base:%H:%M:%S} + {delay}s random delay (max {allowed}s)')
        return base + timedelta(seconds=delay)

    def _schedule_next_day(self, now: datetime) -> None:
        tomorrow = now.date() + timedelta(days=1)
        mode = self._hunt_mode(tomorrow)
        logger.info(f'Tomorrow is the {mode} day')
        self._schedule(self._daily_plan(mode, tomorrow))

    def _schedule(self, target: datetime) -> None:
        # server=False：否则服务器刷新时间不是 9 点时，task_delay 会把目标改到明天那个点
        self.set_next_run(task='Hunt', target=target, server=False)

    def _soul_preset(self, mode: str, day: date) -> str:
        """当天要换的式神录预设（组,队）；周四的雷麒麟没单独配就用麒麟通用的。"""
        con = self.config.hunt.hunt_config
        if mode == NETHERWORLD:
            return con.netherworld_group_team
        if day.weekday() == self.THUNDER_KIRIN_WEEKDAY and con.thunder_kirin_group_team != '-1,-1':
            return con.thunder_kirin_group_team
        return con.kirin_group_team

    def _switch_souls(self, mode: str, day: date) -> None:
        group_team = self._soul_preset(mode, day)
        if group_team != '-1,-1':
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(group_team)

    def _back(self, button) -> None:
        """点返回直到返回键消失，有上限。"""
        timer = Timer(self.BACK_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if not self.appear(button):
                return
            self.appear_then_click(button, interval=1, policy=InteractionPolicy.NAVIGATION)
        logger.warning(f'{button.name} is still there after {self.BACK_TIMEOUT}s')

    def kirin(self) -> str:
        logger.hr('kirin', 2)
        timer = Timer(self.KIRIN_ENTER_TIMEOUT).start()
        while 1:
            self.screenshot()
            if self.appear(self.I_PREPARE_HIGHLIGHT):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9, policy=InteractionPolicy.CONFIRM):
                continue
            if self.appear_then_click(self.I_KIRIN_CHALLAGE, interval=1.5, policy=InteractionPolicy.NORMAL):
                continue
            if self.appear(self.I_KIRIN_END):
                # 今日已挑战
                logger.warning('Today have already challenged the Kirin')
                self._back(self.I_UI_BACK_YELLOW)
                return DONE
            if timer.reached():
                logger.warning('Kirin challenge did not reach the prepare page')
                return TIMEOUT
        logger.info('Start battle')
        self.run_general_battle(
            self.config.hunt.kirin_battle_config,
            battle_key="hunt_kirin",
            exit_matcher=page_hunt_kirin,
        )
        return BATTLE

    def netherworld(self) -> str:
        logger.hr('netherworld', 2)
        timer = Timer(self.NW_ENTER_TIMEOUT).start()
        battle_entered = False
        while 1:
            self.screenshot()
            # 放在最前面：房间里迟迟没有挑战键时下面会直接 continue
            if timer.reached():
                logger.warning('Netherworld challenge did not get into the room battle')
                return TIMEOUT
            if self.is_in_room(False):
                self.screenshot()
                if not self.appear(self.I_FIRE):
                    continue
                # click_fire 现返回 battle-entry 结果：只有正向战斗确认才交接 run_general_battle
                battle_entered = self.click_fire() == 'battle'
                break

            if self.appear_then_click(self.I_NW, interval=0.9, policy=InteractionPolicy.NORMAL):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9, policy=InteractionPolicy.CONFIRM):
                continue
            if self.appear_then_click(self.I_NW_CHALLAGE, interval=1.5, policy=InteractionPolicy.NORMAL):
                continue
            if self.appear(self.I_NW_DONE):
                # 今日已挑战
                logger.warning('Today have already challenged the Netherworld')
                self._back(self.I_UI_BACK_RED)
                return DONE
        if not battle_entered:
            logger.warning('Netherworld room challenge did not confirm battle, retry later')
            return TIMEOUT
        logger.info('Start battle')
        self.run_general_battle(
            self.config.hunt.netherworld_battle_config,
            battle_key="hunt_netherworld",
            exit_matcher=page_hunt,
        )
        return BATTLE


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
