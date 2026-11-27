# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import re
from time import monotonic, sleep
from datetime import timedelta, datetime

from module.exception import GameStuckError, TaskEnd
from module.logger import logger
from module.base.timer import Timer

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_shikigami_records, page_guild
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.fire_battle_entry import is_new_battle_entry
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.DemonRetreat.assets import DemonRetreatAssets
from tasks.AbyssShadows.assets import AbyssShadowsAssets
from tasks.DemonRetreat.config import DemonRetreat


class ScriptTask(GameUi, GeneralBattle, SwitchSoul, DemonRetreatAssets, AbyssShadowsAssets):
    GATHER_WAIT_SECONDS = 185
    BATTLE_ENTRY_TIMEOUT = 15
    ENTER_FIRE_GOLD_MIN = 30

    def run(self):
        """
        首领退治主函数
        """
        cfg: DemonRetreat = self.config.demon_retreat
        if not self.check_date(datetime.now()):
            logger.warning("Demon retreat is not available now")
            self.set_next_run(task='DemonRetreat', server=False, target=self.get_next_dt(datetime.now()))
            raise TaskEnd
        if cfg.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(cfg.switch_soul_config.switch_group_team)
        if cfg.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(cfg.switch_soul_config.group_name, cfg.switch_soul_config.team_name)

        # 进入妖怪退治
        if not self.goto_demon_retreat():
            logger.warning("Failed to enter demon retreat")
            if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                pass
            self.goto_page(page_main)
            self.set_next_run(task='DemonRetreat', server=False, target=self.get_next_dt(datetime.now()))
            raise TaskEnd

        # 首领退治战斗
        success = self.demon_retreat()

        # 战斗结束 回到寮信息界面 准备领取奖励
        # 先返回
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_PRAY, interval=1):
                logger.warning("Claim rewards")
            if self.appear_then_click(self.I_HUNT, interval=1):
                continue
            if self.appear_then_click(self.I_REWARD_ALL, interval=1.5):
                self.ui_reward_appear_click(True)
                logger.info('Claim rewards finished')
                break
            if self.appear(self.I_RANK_LSIT):
                logger.info("No rewards to claim")
                if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                    break

        self.goto_page(page_main)
        # 设置下次运行时间
        self.set_next_run(task='DemonRetreat', server=False, target=self.get_next_dt(datetime.now(), success))
        raise TaskEnd

    def goto_demon_retreat(self) -> bool:
        """
        进入首领退治
        """
        cfg: DemonRetreat = self.config.demon_retreat
        logger.info("Entering demon_retreat")
        self.goto_page(page_guild)

        entry_deadline = monotonic() + 20
        entrance_attempts = 0
        next_entrance_check = 0.0
        while monotonic() < entry_deadline:
            self.screenshot()
            # 进入神社
            if self.appear_then_click(self.I_SHRINE, interval=1):
                logger.info("Enter I_SHRINE")
                continue
            # 确保不离开退治
            if self.appear_then_click(self.I_QUIT_BACK, interval=1):
                continue
            if self.appear(self.I_HUNT_CHECK):
                logger.info("Enter demon_retreat success")
                return True

            # 周六打完了，但是迟到了只能领取奖励
            if self.appear_then_click(self.I_REWARD_ALL, interval=1):
                logger.info("Already challenged demon_retreat")
                sleep(1)
                if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                    pass
                logger.info(f"The next time the demon retreat is next Saturday")
                self.custom_next_run(task='DemonRetreat', custom_time=cfg.demon_retreat_time.custom_run_time,
                                     time_delta=7)
                raise TaskEnd

            # 入口点击后先用新帧等待切页，排行榜识别只在过渡结束后判定。
            if monotonic() < next_entrance_check:
                continue
            if entrance_attempts and self.appear(self.I_RANK_LSIT):
                now = datetime.now()
                start = cfg.demon_retreat_time
                if start.try_start_demon_retreat and self.check_date(now) and now.time() >= start.custom_run_time:
                    return self._open_demon_retreat()
                logger.info("Enter demon_retreat false")
                return False
            if entrance_attempts >= 3:
                break
            if self.appear_then_click(self.I_HUNT, interval=1.5):
                entrance_attempts += 1
                next_entrance_check = monotonic() + 2
        logger.warning("首领退治入口等待超时或已达到重试上限")
        return False

    def _has_retreat_open_prompt(self) -> bool:
        prompt = self.O_RETREAT_OPEN_PROMPT.ocr(self.device.image)
        return ''.join(prompt.split()).rstrip('？?') == '开启本周的首领退治活动'

    def _open_demon_retreat(self) -> bool:
        # 弹窗压暗后的背景仍可能匹配开启图，先检查弹窗是否已经出现。
        if not self._has_retreat_open_prompt() and not self.appear_then_click(self.I_DEMON_START):
            logger.warning("首领退治未识别到管理员开启按钮，可能未到开放时间、已结算或无开启权限")
            return False

        confirm_deadline = monotonic() + 8
        while monotonic() < confirm_deadline:
            self.screenshot()
            if self.appear(self.I_HUNT_CHECK):
                return True
            if not self._has_retreat_open_prompt():
                continue
            cost = self.O_RETREAT_OPEN_COST.ocr(self.device.image)
            if not re.fullmatch(r'是否要消耗[0-9]+阴阳寮勋章', ''.join(cost.split())):
                continue
            if self.ocr_appear_click(self.O_RETREAT_OPEN_CONFIRM):
                logger.info(f"已提交开启首领退治，保留游戏当前难度，{cost}")
                if self.wait_until_appear(self.I_HUNT_CHECK, wait_time=15):
                    return True
                logger.warning("已点击首领退治开启确认，但未识别到集结或挑战页，本轮停止提交")
                return False

        logger.warning("未确认首领退治开启弹窗，未提交开启")
        return False

    def demon_retreat(self):
        cfg: DemonRetreat = self.config.demon_retreat
        logger.hr('demon retreat', 2)

        self.device.stuck_record_clear()
        self.device.stuck_record_add('BATTLE_STATUS_S')
        logger.info(f'已进入首领退治，等待 {self.GATHER_WAIT_SECONDS} 秒后识别进战状态')
        sleep(self.GATHER_WAIT_SECONDS)

        deadline = monotonic() + self.BATTLE_ENTRY_TIMEOUT
        clicked = False
        while monotonic() < deadline:
            self.screenshot()
            if is_new_battle_entry(self):
                logger.info('已识别到首领退治准备或战斗页面，交接战斗流程')
                return self.run_demon_battle(cfg.general_battle)
            if not clicked and self.appear(self.I_HUNT_CHECK) and self._retreat_button_is_lit():
                if self.appear_then_click(self.I_ENTER_FIRE):
                    clicked = True
                    deadline = monotonic() + self.BATTLE_ENTRY_TIMEOUT
                    logger.info('首领退治按钮已亮，已点击一次，等待进战')

        raise GameStuckError('首领退治等待后未识别到准备或战斗页面')

    def _retreat_button_is_lit(self) -> bool:
        x, y, width, height = self.I_ENTER_FIRE.roi_back
        button = self.device.image[y:y + height, x:x + width]
        if button.size == 0:
            return False
        # 实测灰态色差约 1，金色亮态约 64。旧模板两态均可匹配。
        return bool(button[..., 0].mean() - button[..., 2].mean() >= self.ENTER_FIRE_GOLD_MIN)

    def run_demon_battle(self, config: GeneralBattleConfig = None) -> bool:
        """
        重写通用战斗
        三轮战斗 战斗过程中检测挑战
        """
        # TODO 战斗过程中切换预设
        logger.hr("General battle start", 2)
        self.current_count += 1
        logger.info(f"Current count: {self.current_count}")
        if config is None:
            config = GeneralBattleConfig()

        # 如果没有锁定队伍。那么可以根据配置设定队伍
        if not config.lock_team_enable and not self.appear(self.I_BATTLE_INFO):
            logger.info("Lock team is not enable")
            # 如果更换队伍
            if self.current_count == 1:
                self.switch_preset_team(config.preset_enable, config.preset_group, config.preset_team)

            # 已自动开打时跳过准备，即便准备按钮没有亮过。
            while 1:
                self.screenshot()
                if self.appear(self.I_BATTLE_INFO):
                    break
                if self.appear(self.I_BUFF) and self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                    logger.info('已点击首领退治准备按钮')

        # 绿标
        self.wait_until_disappear(self.I_BUFF)
        if self.is_in_battle(False):
            self.green_mark(config.green_enable, config.green_mark, config.green_mark_type, config.green_mark_name)

        win = self.battle_wait(config.random_click_swipt_enable)
        if win:
            return True
        else:
            return False

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        """
        重写 三轮战斗 战斗过程中点击准备 返回到寮信息界面
        :param random_click_swipt_enable:
        :return:
        """
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封 并点击 准备
        logger.info("Start battle process")
        stuck_timer = Timer(180)
        stuck_timer.start()
        while 1:
            self.screenshot()
            if self.appear(self.I_WIN):
                logger.info('Battle win')
                self.ui_click_until_disappear(self.I_WIN)
                return True
            # 战斗过程中出现准备
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
            # 如果出现失败 就点击，返回False
            if self.appear(self.I_FALSE, threshold=0.8):
                logger.info("Battle result is false")
                self.ui_click_until_disappear(self.I_FALSE)
                return False
            # 如果三分钟还没打完，再延长五分钟
            if stuck_timer and stuck_timer.reached():
                stuck_timer = None
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')

    def get_next_dt(self, now: datetime, success: bool = False) -> datetime:
        """获取下一次退治运行时间"""
        rt = self.config.model.demon_retreat.demon_retreat_time.custom_run_time
        scheduler = self.config.model.demon_retreat.scheduler
        if now.weekday() != 5:
            return datetime.combine(now + timedelta(days=(5 - now.weekday() + 7) % 7), rt)
        target_dt = datetime.combine(now.date(), rt)
        # 在1小时之内则间隔failure_interval后重试
        if target_dt <= now < target_dt + timedelta(hours=1) and not success:
            return now + scheduler.failure_interval
        return target_dt + timedelta(days=7)

    def check_date(self, now: datetime) -> bool:
        """检查当前日期是否可以运行退治"""
        return now.weekday() == 5


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('日常1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()

