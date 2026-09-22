# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import time, datetime, timedelta

from tasks.Sougenbi.assets import SougenbiAssets
from tasks.Sougenbi.config import SougenbiConfig, SougenbiClass
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import any_of, page_main, page_shikigami_records, page_soul_zones
from module.logger import logger
from module.exception import TaskEnd
from module.base.timer import Timer
from module.base.utils.random import random_delay
from module.interaction_policy import fire_reaction_range
from tasks.Component.fire_battle_entry import is_battle_result_residue, is_new_battle_entry

# 业原火挑战 FIRE 的有限 attempt / 总超时 / 点击后确认等待。engineering baseline，非 Level C 标定：
# 对齐 OROCHI_FIRE_* / RR_FIRE_*（4 / 10 / 3）。
SOUGENBI_FIRE_MAX_TRIES = 4
SOUGENBI_FIRE_TIMEOUT = 10
SOUGENBI_FIRE_POST_CLICK_TIMEOUT = 3


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, SougenbiAssets):

    def _classify_sougenbi_fire_state(self) -> str:
        """业原火挑战前后的当前帧分类，只读。优先级：battle > abnormal > ready > unknown。

        `'battle'` = `is_new_battle_entry()`（准备 / 战斗页）；`'abnormal'` = 结果 / 奖励页残留；
        `'ready'` = 仍在业原火页（`I_S_CHECK_SOUGENBI`）且挑战按钮在；其余是加载 / 过渡帧。
        """
        if is_new_battle_entry(self):
            return 'battle'
        if is_battle_result_residue(self):
            return 'abnormal'
        if self.appear(self.I_S_CHECK_SOUGENBI) and self.appear(self.I_S_FIRE):
            return 'ready'
        return 'unknown'

    def _wait_sougenbi_fire_state(self, timeout: float = SOUGENBI_FIRE_POST_CLICK_TIMEOUT) -> str:
        """点击后 / 挑战未就绪时的有界轮询，期间不点任何坐标；出现决定性状态即返回，否则 `'timeout'`。"""
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            state = self._classify_sougenbi_fire_state()
            if state != 'unknown':
                return state
        return 'timeout'

    def _fire_sougenbi(self) -> bool:
        """点业原火挑战直到**正向确认进入准备 / 战斗页**（FIRE Contract，D001 补记 FIRE 分节）。

        每次 attempt：分类当前帧 → 独立采样 `sougenbi.fire_reaction` → `sleep` → fresh screenshot →
        重新确认仍在业原火页且挑战按钮在 → 点一次 → 有界等点击后状态。挑战按钮消失不算成功；过渡帧只等不点；
        结果 / 奖励页残留直接返回失败。有限 `SOUGENBI_FIRE_MAX_TRIES` + `Timer(SOUGENBI_FIRE_TIMEOUT)`。

        :return: True 已进入准备 / 战斗页；False 异常 / 有限尝试 / 总超时用尽（调用方不交接 run_general_battle）
        """
        timeout_timer = Timer(SOUGENBI_FIRE_TIMEOUT).start()
        for attempt in range(1, SOUGENBI_FIRE_MAX_TRIES + 1):
            if timeout_timer.reached():
                break
            self.screenshot()
            state = self._classify_sougenbi_fire_state()
            if state == 'unknown':
                state = self._wait_sougenbi_fire_state()
                if state in ('timeout', 'ready'):
                    continue
            if state == 'battle':
                logger.info('Sougenbi fire: entered battle')
                return True
            if state == 'abnormal':
                logger.warning('Sougenbi fire: result / reward page residue, not a new battle')
                return False
            fire_delay = random_delay(*fire_reaction_range(self.config.sougenbi.fire_reaction))
            logger.info(f'Sougenbi fire: attempt {attempt}, reaction {fire_delay:.2f}s')
            sleep(fire_delay)
            self.screenshot()
            state = self._classify_sougenbi_fire_state()
            if state == 'battle':
                return True
            if state == 'abnormal':
                logger.warning('Sougenbi fire: result / reward page residue during reaction')
                return False
            if state != 'ready':
                logger.info('Sougenbi fire: left ready state during reaction, re-evaluate')
                continue
            self.appear_then_click(self.I_S_FIRE, interval=0)
            state = self._wait_sougenbi_fire_state()
            if state == 'battle':
                logger.info('Sougenbi fire: entered battle after click')
                return True
            if state == 'abnormal':
                logger.warning('Sougenbi fire: result / reward page after click, not a new battle')
                return False
            # 'ready'（仍在业原火页）/ 'timeout'（一直过渡）→ 下一 attempt
        logger.warning('Sougenbi fire: bounded retry / timeout without entering battle')
        return False


    def run(self):
        con = self.config.sougenbi
        s_con: SougenbiConfig = con.sougenbi_config
        limit_time = con.sougenbi_config.limit_time
        self.limit_time: timedelta = timedelta(hours=limit_time.hour, minutes=limit_time.minute,
                                               seconds=limit_time.second)
        if s_con.buff_enable:
            self.goto_page(page_main)
            self.open_buff()
            if s_con.buff_gold_50_click:
                self.gold_50(True)
            if s_con.buff_gold_100_click:
                self.gold_100(True)
            if s_con.buff_exp_50_click:
                self.exp_50(True)
            if s_con.buff_exp_100_click:
                self.exp_100(True)
            self.close_buff()

        if con.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(con.switch_soul_config.switch_group_team)
        if con.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(con.switch_soul_config.group_name, con.switch_soul_config.team_name)

        self.goto_page(page_soul_zones)
        while 1:
            self.screenshot()
            if self.appear(self.I_S_CHECK_SOUGENBI):
                break
            if self.appear_then_click(self.I_S_SOUGENBI, interval=1):
                continue
        logger.info('Click sougenbi in soul zones')
        sleep(0.5)
        image_target = None
        click_target = None
        number_target = None
        match con.sougenbi_config.sougenbi_class:
            case SougenbiClass.GREED:
                image_target = self.I_S_FIRE_GREED
                click_target = self.C_C_GREED
                number_target = self.O_S_GREED
            case SougenbiClass.Anger:
                image_target = self.I_S_FIRE_ANGER
                click_target = self.C_C_ANGER
                number_target = self.O_S_ANGER
            case SougenbiClass.Foolery:
                image_target = self.I_S_FIRE_FOOLERY
                click_target = self.C_C_FOOLERY
                number_target = self.O_S_FOOLERY
            case _:
                raise ValueError('Sougenbi class error')
        self.check_lock(con.general_battle_config.lock_team_enable, self.I_S_TEAM_LOCK, self.I_S_TEAM_UNLOCK)
        while 1:
            self.screenshot()
            if self.appear(image_target):
                break
            if self.click(click_target, interval=0.5):
                pass

        # 开始循环
        while 1:
            self.screenshot()

            if not self.appear(self.I_S_CHECK_SOUGENBI):
                continue
            if self.current_count >= con.sougenbi_config.limit_count:
                logger.info('Sougenbi count limit out')
                break
            if datetime.now() - self.start_time >= self.limit_time:
                logger.info('Sougenbi time limit out')
                break
            ticket = number_target.ocr(self.device.image)
            if ticket == 0:
                break

            # 点击挑战：FIRE 状态机，正向确认进入准备 / 战斗页才交接 run_general_battle；
            # 未进入战斗 → 回外层循环顶重新 screenshot + 判定业原火页与票数
            if self._fire_sougenbi():
                self.run_general_battle(
                    config=con.general_battle_config,
                    exit_matcher=any_of(self.I_S_FIRE, self.I_S_CHECK_SOUGENBI),
                )
        self.goto_page(page_main)
        if s_con.buff_enable:
            self.open_buff()
            if s_con.buff_gold_50_click:
                self.gold_50(False)
            if s_con.buff_gold_100_click:
                self.gold_100(False)
            if s_con.buff_exp_50_click:
                self.exp_50(False)
            if s_con.buff_exp_100_click:
                self.exp_100(False)
            self.close_buff()

        self.set_next_run("Sougenbi", success=True, finish=True)
        raise TaskEnd







if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('test')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
    # print(t.appear(t.I_S_FOOLERY, threshold=0.97))

