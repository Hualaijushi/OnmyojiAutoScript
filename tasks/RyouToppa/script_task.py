# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
from datetime import datetime, timedelta, time as dt_time
from enum import Enum
import random
import secrets

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.RyouToppa.assets import RyouToppaAssets
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.config_base import ConfigBase, Time
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_realm_raid, page_main, page_kekkai_toppa, page_shikigami_records
from tasks.RealmRaid.assets import RealmRaidAssets

from module.logger import logger
from module.exception import ScriptError, TaskEnd
from module.base.timer import Timer
from module.exception import GamePageUnknownError


area_map = (
    {
        "fail_sign": (RyouToppaAssets.I_AREA_1_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_1_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_1,
        "finished_sign": (RyouToppaAssets.I_AREA_1_FINISHED, RyouToppaAssets.I_AREA_1_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_2_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_2_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_2,
        "finished_sign": (RyouToppaAssets.I_AREA_2_FINISHED, RyouToppaAssets.I_AREA_2_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_3_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_3_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_3,
        "finished_sign": (RyouToppaAssets.I_AREA_3_FINISHED, RyouToppaAssets.I_AREA_3_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_4_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_4_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_4,
        "finished_sign": (RyouToppaAssets.I_AREA_4_FINISHED, RyouToppaAssets.I_AREA_4_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_5_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_5_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_5,
        "finished_sign": (RyouToppaAssets.I_AREA_5_FINISHED, RyouToppaAssets.I_AREA_5_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_6_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_6_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_6,
        "finished_sign": (RyouToppaAssets.I_AREA_6_FINISHED, RyouToppaAssets.I_AREA_6_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_7_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_7_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_7,
        "finished_sign": (RyouToppaAssets.I_AREA_7_FINISHED, RyouToppaAssets.I_AREA_7_FINISHED_NEW)
    },
    {
        "fail_sign": (RyouToppaAssets.I_AREA_8_IS_FAILURE_NEW, RyouToppaAssets.I_AREA_8_IS_FAILURE),
        "rule_click": RyouToppaAssets.C_AREA_8,
        "finished_sign": (RyouToppaAssets.I_AREA_8_FINISHED, RyouToppaAssets.I_AREA_8_FINISHED_NEW)
    }
)

RYOU_TOPPA_VISIBLE_AREAS = 6
RYOU_TOPPA_STATE_TIMEOUT = 3
RYOU_TOPPA_ENTRY_RETRIES = 3
RYOU_TOPPA_ACTION_RETRIES = 2
RYOU_TOPPA_TICKET_OCR_RETRIES = 3
RYOU_TOPPA_MAIN_FAILURE_LIMIT = 2
RYOU_TOPPA_AREA_CONTENT_STD = 8.0
_random = secrets.SystemRandom()


class AreaAttackResult(Enum):
    SUCCESS = 'success'
    FAILED_MARKED = 'failed_marked'
    INTERACTION_ERROR = 'interaction_error'
    UNAVAILABLE = 'unavailable'


def random_delay(min_value: float = 1.0, max_value: float = 3.0):
    """
    生成一个指定范围内的随机小数
    """
    return _random.uniform(min_value, max_value)


class ScriptTask(GeneralBattle, GameUi, SwitchSoul, RyouToppaAssets):
    def _detect_ryou_toppa_state(self) -> str | None:
        if self.appear(self.I_SUCCESS_PENETRATION, threshold=0.8):
            return 'success'
        if self.appear(self.I_SELECT_RYOU_BUTTON, threshold=0.8):
            return 'select'
        if self.appear(self.I_NO_SELECT_RYOU, threshold=0.8):
            return 'not_open'
        if self.appear(self.I_RYOU_REWARD, threshold=0.8) or \
                self.appear(self.I_RYOU_REWARD_90, threshold=0.8):
            return 'ready'
        return None

    def _wait_for_ryou_toppa_state(self) -> str:
        logger.info('寮突破：正在等待任务页面状态')
        for attempt in range(1, RYOU_TOPPA_ENTRY_RETRIES + 1):
            timer = Timer(RYOU_TOPPA_STATE_TIMEOUT).start()
            while not timer.reached():
                self.screenshot()
                state = self._detect_ryou_toppa_state()
                if state is not None:
                    return state

            if attempt >= RYOU_TOPPA_ENTRY_RETRIES:
                break

            self.screenshot()
            clicked = False
            if self.appear(RealmRaidAssets.I_REALM_RAID):
                clicked = self.appear_then_click(RealmRaidAssets.I_REALM_RAID, interval=0)
            elif self.appear(self.I_REAL_RAID_REFRESH, threshold=0.8):
                clicked = self.appear_then_click(self.I_RYOU_TOPPA, interval=0)

            if clicked:
                logger.warning(f'寮突破：入口点击后页面未切换，第{attempt}次重试')
            else:
                logger.warning(f'寮突破：未识别到可用入口，第{attempt}次重试')

        message = '寮突破页面识别超时，无法确认当前任务状态'
        logger.error(message)
        raise GamePageUnknownError(message)

    def _ensure_team_lock_state(self, lock_team: bool) -> None:
        expected = self.I_TOPPA_LOCK_TEAM if lock_team else self.I_TOPPA_UNLOCK_TEAM
        source = self.I_TOPPA_UNLOCK_TEAM if lock_team else self.I_TOPPA_LOCK_TEAM
        state_name = '锁定' if lock_team else '解锁'

        timer = Timer(RYOU_TOPPA_STATE_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(expected):
                logger.info(f'寮突破：阵容已处于{state_name}状态，无需点击')
                return
            if self.appear(source):
                logger.info(f'寮突破：点击一次阵容{state_name}按钮')
                self.appear_then_click(source, interval=0)
                break
        else:
            message = '寮突破：无法识别当前阵容锁定状态'
            logger.error(message)
            raise GamePageUnknownError(message)

        timer = Timer(RYOU_TOPPA_STATE_TIMEOUT).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(expected):
                logger.info(f'寮突破：阵容{state_name}状态设置成功')
                return

        message = f'寮突破：阵容{state_name}状态设置失败'
        logger.error(message)
        raise GamePageUnknownError(message)

    def _wait_for_attack_state(self, timeout: float = RYOU_TOPPA_STATE_TIMEOUT) -> str:
        timer = Timer(timeout).start()
        list_seen = False
        while not timer.reached():
            self.screenshot()
            if self.is_in_battle(False):
                return 'battle'
            if self.appear(RealmRaidAssets.I_FIRE, threshold=0.8):
                return 'fire'
            if self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                list_seen = True
        return 'list' if list_seen else 'unknown'

    def _wait_for_ryou_toppa_list(self, timeout: float = RYOU_TOPPA_STATE_TIMEOUT) -> bool:
        timer = Timer(timeout).start()
        while not timer.reached():
            self.screenshot()
            if self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                return True
        return False

    def _wait_for_ryou_toppa_page(self, timeout: float = RYOU_TOPPA_STATE_TIMEOUT) -> bool:
        timer = Timer(timeout).start()
        while not timer.reached():
            if self.confirm_page(page_kekkai_toppa, skip_first_screenshot=False) and \
                    self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                return True
        return False

    def _area_has_failure_mark(self, index: int) -> bool:
        failure_new, failure_old = area_map[index].get('fail_sign')
        return self.appear(failure_new, threshold=0.8) or \
            self.appear(failure_old, threshold=0.8)

    def _area_has_finished_mark(self, index: int) -> bool:
        finished_old, finished_new = area_map[index].get('finished_sign')
        return self.appear(finished_old, threshold=0.8) or \
            self.appear(finished_new, threshold=0.8)

    def _area_content_recognizable(self, index: int) -> bool:
        if self._area_has_failure_mark(index) or self._area_has_finished_mark(index):
            return True
        if not self.appear(self.I_TOPPA_LOCK_TEAM) and not self.appear(self.I_TOPPA_UNLOCK_TEAM):
            return False
        x, y, width, height = area_map[index].get('rule_click').roi_front
        area_image = self.device.image[y:y + height, x:x + width]
        return bool(area_image.size) and float(area_image.std()) >= RYOU_TOPPA_AREA_CONTENT_STD

    def _finish_area_battle(self, index: int) -> AreaAttackResult:
        logger.info(f'寮突破：区域{index + 1}已进入准备或战斗页面')
        battle_success = self.run_general_battle(
            config=self.config.ryou_toppa.general_battle_config,
            exit_matcher=self.I_TOPPA_RECORD,
        )
        for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1):
            if self._wait_for_ryou_toppa_page():
                break
            logger.warning(
                f'寮突破：区域{index + 1}战斗返回后未识别到目标列表，第{attempt}次重试'
            )
        else:
            logger.error(f'寮突破：区域{index + 1}战斗返回页面异常，无法判断战斗结果')
            return AreaAttackResult.INTERACTION_ERROR

        self.screenshot()
        if self._area_has_failure_mark(index):
            logger.warning(f'寮突破：区域{index + 1}战斗返回后明确识别到失败标识')
            return AreaAttackResult.FAILED_MARKED
        if not battle_success:
            logger.warning(
                f'寮突破：区域{index + 1}通用战斗判定失败，但返回页面未发现失败标识，继续按页面状态处理'
            )
        if not self._area_content_recognizable(index):
            logger.error(f'寮突破：区域{index + 1}战斗返回后无法正常识别区域内容')
            return AreaAttackResult.INTERACTION_ERROR
        logger.info(f'寮突破：区域{index + 1}战斗返回后未发现失败标识')
        return AreaAttackResult.SUCCESS

    def _attack_limit_reached(self, ryou_config, deadline: datetime) -> bool:
        if self.current_count >= ryou_config.raid_config.limit_count:
            logger.warning('寮突破：已达到最大进攻次数，结束任务')
            return True
        if datetime.now() >= deadline:
            logger.warning('寮突破：已达到最大运行时间，结束任务')
            return True
        return False

    def _reopen_area_after_fire_disappear(self, index: int) -> str:
        if not self._wait_for_ryou_toppa_page():
            logger.error(f'寮突破：区域{index + 1}进攻按钮消失后未能确认目标列表')
            return 'unknown'
        if not self.check_area(index):
            return 'unavailable'

        logger.warning(f'寮突破：区域{index + 1}进攻按钮消失但未进入战斗，重新点击区域一次')
        self.click(area_map[index].get('rule_click'))
        return self._wait_for_attack_state()

    def run(self):
        """
        执行
        :return:
        """
        ryou_config = self.config.ryou_toppa
        time_limit: Time = ryou_config.raid_config.limit_time
        time_delta = timedelta(hours=time_limit.hour, minutes=time_limit.minute, seconds=time_limit.second)

        if ryou_config.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(ryou_config.switch_soul_config.switch_group_team)

        if ryou_config.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(ryou_config.switch_soul_config.group_name, ryou_config.switch_soul_config.team_name)

        self.goto_page(page_kekkai_toppa)
        ryou_toppa_start_flag = True
        ryou_toppa_success_penetration = False
        ryou_toppa_admin_flag = False
        toppa_state = self._wait_for_ryou_toppa_state()
        if toppa_state == 'success':
            ryou_toppa_success_penetration = True
        elif toppa_state == 'select':
            ryou_toppa_start_flag = False
            ryou_toppa_admin_flag = True
        elif toppa_state == 'not_open':
            ryou_toppa_start_flag = False

        logger.attr('ryou_toppa_start_flag', ryou_toppa_start_flag)
        logger.attr('ryou_toppa_success_penetration', ryou_toppa_success_penetration)
        # 寮突未开 并且有权限， 开开寮突，没有权限则标记失败
        if not ryou_toppa_start_flag:
            if ryou_config.raid_config.ryou_access and ryou_toppa_admin_flag:
                # 作为寮管理，开启今天的寮突
                logger.info("As the manager of the ryou, try to start ryou toppa.")
                self.start_ryou_toppa()
            else:
                logger.info("The ryou toppa is not open and you are a ryou member.")
                self.set_next_run(task='RyouToppa', finish=True, server=True, success=False)
                raise TaskEnd

        # 100% 攻破, 第二天再执行
        if ryou_toppa_success_penetration:
            logger.info('RyouToppa is 100%')
            self.plan_tomorrow_ryoutoppa()
            raise TaskEnd
        self._ensure_team_lock_state(self.config.ryou_toppa.general_battle_config.lock_team_enable)
        # --------------------------------------------------------------------------------------------------------------
        # 开始突破
        # --------------------------------------------------------------------------------------------------------------
        current_index = 0
        main_failure_count = 0
        success = True
        stop_attack = False
        deadline = self.start_time + time_delta
        while 1:
            # 设置长任务标志,用来寻找寮突可进攻的目标
            self.device.stuck_record_add('PREPARE_BEFORE_BATTLE')
            if not self.has_ticket():
                logger.info('寮突破：没有剩余进攻次数，结束任务并等待下次运行')
                success = False
                break
            if self._attack_limit_reached(ryou_config, deadline):
                break

            if current_index >= RYOU_TOPPA_VISIBLE_AREAS:
                logger.info('寮突破：当前前6个区域均已完成失败处理')
                logger.info('寮突破：准备滑动加载下一批目标')
                self.flush_area_cache()
                current_index = 0
                main_failure_count = 0
                continue

            logger.info(f'寮突破：当前主攻击区域为区域{current_index + 1}')
            result = self.attack_area(current_index)
            if result == AreaAttackResult.INTERACTION_ERROR:
                message = f'寮突破：区域{current_index + 1}发生交互异常，不计入目标失败次数'
                logger.error(message)
                raise GamePageUnknownError(message)
            if result == AreaAttackResult.SUCCESS:
                logger.info(f'寮突破：区域{current_index + 1}攻击成功，保持当前主攻击位置')
                main_failure_count = 0
                self.screenshot()
                continue

            main_unavailable = result == AreaAttackResult.UNAVAILABLE
            if result == AreaAttackResult.FAILED_MARKED:
                main_failure_count += 1
                logger.warning(
                    f'寮突破：区域{current_index + 1}第{main_failure_count}次真实攻击失败'
                )

            if ryou_config.raid_config.skip_difficult and \
                    main_failure_count >= RYOU_TOPPA_MAIN_FAILURE_LIMIT:
                logger.warning(
                    f'寮突破：区域{current_index + 1}连续失败2次，暂时跳过'
                )
                current_index += 1
                main_failure_count = 0
                if current_index < RYOU_TOPPA_VISIBLE_AREAS:
                    logger.info(f'寮突破：主攻击区域切换为区域{current_index + 1}')
                continue

            neighbor_success = False
            for neighbor_index in (current_index + 1, current_index + 2):
                if neighbor_index >= RYOU_TOPPA_VISIBLE_AREAS:
                    continue
                if self._attack_limit_reached(ryou_config, deadline):
                    stop_attack = True
                    break
                if not self.has_ticket():
                    logger.info('寮突破：邻近尝试前发现没有剩余进攻次数')
                    success = False
                    stop_attack = True
                    break

                logger.info(f'寮突破：尝试邻近区域{neighbor_index + 1}')
                neighbor_result = self.attack_area(neighbor_index)
                if neighbor_result == AreaAttackResult.INTERACTION_ERROR:
                    message = f'寮突破：邻近区域{neighbor_index + 1}发生交互异常，不计入目标失败次数'
                    logger.error(message)
                    raise GamePageUnknownError(message)
                if neighbor_result == AreaAttackResult.SUCCESS:
                    logger.info(
                        f'寮突破：邻近区域{neighbor_index + 1}攻击成功，重新尝试主区域{current_index + 1}'
                    )
                    neighbor_success = True
                    self.screenshot()
                    break
                if neighbor_result == AreaAttackResult.FAILED_MARKED:
                    logger.warning(f'寮突破：邻近区域{neighbor_index + 1}战斗后出现失败标识')
                else:
                    logger.info(f'寮突破：邻近区域{neighbor_index + 1}当前不可攻击')

            if stop_attack:
                break
            if neighbor_success:
                continue

            if main_unavailable:
                logger.warning(
                    f'寮突破：主区域{current_index + 1}攻击前已有失败标识，且邻近区域未能推动队列，'
                    '结束本轮但不新增失败次数'
                )
                success = False
                break

            if ryou_config.raid_config.skip_difficult:
                logger.info(f'寮突破：邻近区域均未成功，重新尝试主区域{current_index + 1}')
                continue

            if main_failure_count < RYOU_TOPPA_MAIN_FAILURE_LIMIT:
                logger.info(
                    f'寮突破：未启用困难目标跳过，重新尝试主区域{current_index + 1}'
                )
                continue

            logger.warning(
                f'寮突破：未启用困难目标跳过，主区域{current_index + 1}本轮已有限重试2次，'
                '结束本轮并保留后续再次尝试'
            )
            success = False
            break

        if success:
            self.set_next_run(task='RyouToppa', finish=True, server=True, success=True)
        else:
            self.set_next_run(task='RyouToppa', finish=True, server=True, success=False)
        self.goto_page(page_main)
        raise TaskEnd

    def plan_tomorrow_ryoutoppa(self):
        # 安排下次寮突破，便于复用
        now = datetime.now()
        # 如果时间在00:00-5:00之间则设定时间为当天的自定义时间
        if now.time() < dt_time(5, 0):  # 不确定 time 的使用范围，重命名 datetime 中的 time
            self.custom_next_run(task='RyouToppa', custom_time=self.config.ryou_toppa.raid_config.next_ryoutoppa_time, time_delta=0)
        # 如果时间在05:00-23:59之间则设定时间为明天的自定义时间
        else:
            self.custom_next_run(task='RyouToppa', custom_time=self.config.ryou_toppa.raid_config.next_ryoutoppa_time, time_delta=1)

    def start_ryou_toppa(self):
        """
        开启寮突破
        :return:
        """
        # 点击寮突
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_SELECT_RYOU_BUTTON, interval=1):
                break
        logger.info(f'Click {self.I_SELECT_RYOU_BUTTON.name}')

        # 选择第一个寮
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_GUILD_ORDERS_REWARDS, action=self.C_SELECT_FIRST_RYOU, interval=1):
                break
        logger.info(f'Click {self.C_SELECT_FIRST_RYOU.name}')

        # 点击开始突入
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_START_TOPPA_BUTTON, interval=1):
                continue
            # 出现寮奖励， 说明寮突已开
            if self.appear(self.I_RYOU_REWARD, threshold=0.8):
                break
        logger.info(f'Click {self.I_START_TOPPA_BUTTON.name}')

    def has_ticket(self) -> bool:
        """
        如果没有票了，那么就返回False
        :return:
        """
        # 21点至次日5点前按无限进攻次数处理
        if datetime.now().hour >= 21 or datetime.now().hour < 5:
            return True
        if not self.wait_until_appear(self.I_TOPPA_RECORD, wait_time=RYOU_TOPPA_STATE_TIMEOUT):
            message = '寮突破：票数识别前未找到目标列表标志'
            logger.error(message)
            raise GamePageUnknownError(message)

        for attempt in range(1, RYOU_TOPPA_TICKET_OCR_RETRIES + 1):
            self.screenshot()
            cu, res, total = self.O_NUMBER.ocr(self.device.image)
            if total > 0:
                logger.info(f'寮突破：当前进攻次数为{cu}/{total}')
                if cu == 0 and cu + res == total:
                    logger.warning('寮突破：剩余进攻次数为0')
                    return False
                return True
            logger.warning(f'寮突破票数第{attempt}次识别失败')

        message = '寮突破票数连续3次识别失败，无法确认剩余进攻次数'
        logger.error(message)
        raise ScriptError(message)

    def check_area(self, index: int) -> bool:
        """
        检查该区域是否攻略失败
        :return:
        """
        self.screenshot()
        # 如果该区域已经被攻破则退出
        # Ps: 这时候能打过的都打过了，没有能攻打的结界了, 代表任务已经完成，set_next_run time=1d
        if self._area_has_finished_mark(index):
            logger.info('RyouToppa has tried to attack')
            self.plan_tomorrow_ryoutoppa()
            raise TaskEnd
        # 如果该区域攻略失败返回 False
        if self._area_has_failure_mark(index):
            logger.info(f'寮突破：区域{index + 1}攻击前已经存在失败标识，本次不重复点击')
            return False
        return True

    def flush_area_cache(self):
        for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1):
            if not self._wait_for_ryou_toppa_page():
                logger.warning(f'寮突破：滑动前未识别到寮突破页面，第{attempt}次重试')
                continue

            if attempt == 1:
                start_x = 850 + random.randint(-12, 12)
                start_y = 520 + random.randint(-8, 8)
                end_x = start_x + random.randint(-3, 3)
                distance = random.randint(97, 105)
                duration = random_delay(0.342, 0.362)
            else:
                start_x = 850 + random.randint(-3, 3)
                start_y = 520 + random.randint(-2, 2)
                end_x = start_x + random.randint(-1, 1)
                distance = random.randint(100, 102)
                duration = random_delay(0.349, 0.355)

            self.device.swipe(
                p1=(start_x, start_y),
                p2=(end_x, start_y - distance),
                duration=duration,
                control_name='寮突破列表滑动',
            )
            logger.info(f'寮突破：第{attempt}次列表滑动完成，重新识别区域')
            if self._wait_for_ryou_toppa_page():
                self.screenshot()
                if self._area_content_recognizable(0):
                    logger.info('寮突破：列表滑动完成，目标区域识别正常')
                    return
            if attempt < RYOU_TOPPA_ACTION_RETRIES:
                logger.warning('寮突破：滑动后未能正常识别目标区域，准备重试')
            else:
                logger.error('寮突破：第2次列表滑动仍无法恢复区域识别')

        message = '寮突破：列表滑动验证失败，结束当前任务'
        logger.error(message)
        raise GamePageUnknownError(message)

    def attack_area(self, index: int) -> AreaAttackResult:
        """
        :return: 区域战斗结果
        """
        # 每次进攻前检查区域可用性
        if not self.check_area(index):
            return AreaAttackResult.UNAVAILABLE
        # 正式进攻前增加1至3秒随机等待，页面推进仍以状态识别为准。
        if self.config.ryou_toppa.raid_config.random_delay:
            delay = random_delay(1.0, 3.0)
            logger.info(f'寮突破：正式进攻前随机等待{delay:.2f}秒')
            time.sleep(delay)
        rcl = area_map[index].get("rule_click")
        self.device.click_record_clear()

        for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1):
            self.screenshot()
            if self.is_in_battle(False):
                return self._finish_area_battle(index)
            if self.appear(RealmRaidAssets.I_FIRE, threshold=0.8):
                break
            if not self.appear(self.I_TOPPA_RECORD, threshold=0.85):
                if not self._wait_for_ryou_toppa_list():
                    logger.error(f'寮突破：点击区域{index + 1}前目标列表状态异常')
                    return AreaAttackResult.INTERACTION_ERROR

            logger.info(f'寮突破：点击区域{index + 1}，第{attempt}次尝试')
            self.click(rcl)
            state = self._wait_for_attack_state()
            if state == 'battle':
                return self._finish_area_battle(index)
            if state == 'fire':
                break
            if state == 'unknown':
                if not self._wait_for_ryou_toppa_page():
                    logger.error(f'寮突破：点击区域{index + 1}后页面状态异常')
                    return AreaAttackResult.INTERACTION_ERROR
                logger.warning(f'寮突破：区域{index + 1}点击后未出现进攻按钮，第{attempt}次重试')
                continue
            logger.warning(f'寮突破：区域{index + 1}点击后未出现进攻按钮，第{attempt}次重试')
        else:
            logger.error(f'寮突破：区域{index + 1}有限重试后仍未出现进攻按钮，判定为交互异常')
            return AreaAttackResult.INTERACTION_ERROR

        reopen_area = False
        for attempt in range(1, RYOU_TOPPA_ACTION_RETRIES + 1):
            if reopen_area:
                state = self._reopen_area_after_fire_disappear(index)
                reopen_area = False
                if state == 'battle':
                    return self._finish_area_battle(index)
                if state == 'unavailable':
                    logger.info(f'寮突破：区域{index + 1}重新识别后已不可攻击')
                    return AreaAttackResult.UNAVAILABLE
                if state != 'fire':
                    logger.error(f'寮突破：区域{index + 1}重新点击后仍未出现进攻按钮或进入战斗')
                    return AreaAttackResult.INTERACTION_ERROR
            else:
                self.screenshot()
                if self.is_in_battle(False):
                    return self._finish_area_battle(index)
                if not self.appear(RealmRaidAssets.I_FIRE, threshold=0.8):
                    state = self._wait_for_attack_state()
                    if state == 'battle':
                        return self._finish_area_battle(index)
                    if state == 'list' and attempt < RYOU_TOPPA_ACTION_RETRIES:
                        reopen_area = True
                        logger.warning(f'寮突破：区域{index + 1}进攻按钮已消失，准备重新点击区域')
                        continue
                    if state != 'fire':
                        logger.warning(f'寮突破：区域{index + 1}进攻按钮已消失但尚未进入战斗')
                        continue

            logger.info(f'寮突破：点击区域{index + 1}进攻按钮，第{attempt}次尝试')
            fire_delay = random_delay(0.2, 0.6)
            logger.info(f'寮突破：进攻按钮确认后等待{fire_delay:.2f}秒再点击')
            time.sleep(fire_delay)
            self.screenshot()
            if self.is_in_battle(False):
                return self._finish_area_battle(index)
            if not self.appear(RealmRaidAssets.I_FIRE, threshold=0.8):
                if attempt < RYOU_TOPPA_ACTION_RETRIES and self._wait_for_ryou_toppa_page():
                    reopen_area = True
                    logger.warning(f'寮突破：区域{index + 1}等待点击期间返回目标列表，准备重新点击区域')
                    continue
                logger.warning(f'寮突破：等待点击期间进攻按钮状态已变化，第{attempt}次重新识别')
                continue
            self.appear_then_click(RealmRaidAssets.I_FIRE, interval=0, threshold=0.8)
            state = self._wait_for_attack_state()
            if state == 'battle':
                return self._finish_area_battle(index)
            if state == 'fire':
                logger.warning(f'寮突破：区域{index + 1}进攻按钮点击后仍存在，第{attempt}次重试')
                continue
            if state == 'list' and attempt < RYOU_TOPPA_ACTION_RETRIES:
                reopen_area = True
                logger.warning(f'寮突破：区域{index + 1}点击进攻后返回目标列表，准备重新点击区域')
                continue
            if state == 'unknown':
                if attempt < RYOU_TOPPA_ACTION_RETRIES and self._wait_for_ryou_toppa_page():
                    reopen_area = True
                    logger.warning(f'寮突破：区域{index + 1}点击进攻后状态短暂异常，准备重新点击区域')
                    continue
                logger.error(f'寮突破：点击区域{index + 1}进攻按钮后页面状态异常')
                return AreaAttackResult.INTERACTION_ERROR

        logger.error(f'寮突破：区域{index + 1}进攻按钮有限重试后仍未进入战斗，判定为交互异常')
        return AreaAttackResult.INTERACTION_ERROR


if __name__ == "__main__":
    from module.config.config import Config
    from module.device.device import Device

    config = Config('oas1')
    device = Device(config)
    t = ScriptTask(config, device)
    t.run()
