import time

from module.atom.image import RuleImage
from module.base.timer import Timer
from module.exception import GameStuckError, TaskEnd
from module.logger import logger
from tasks.SixRealms.peacock_kingdom.base_peacock_kingdom import BasePeacockKingdom
import tasks.SixRealms.peacock_kingdom.page as pages
from typing import Callable


class PeacockKingdom(BasePeacockKingdom):
    # 本轮唤息确认失败过：不再唤息（`before_run` 重置）
    breath_failed = False
    # 轰雷实际扣费，只用于购买后验证；买入门槛仍是 run_on_pk_store 里的 300（真机 6 次购买 5 次扣 200）
    PK_SKILL_THUNDER_COST = 200
    # 首领战前无轰雷主动放弃试炼的总超时（秒），避免异常界面下无界死等
    GIVEUP_TIMEOUT = 30.0

    def _default_detect_categories(self) -> set[str]:
        categories = super()._default_detect_categories()
        categories.add("six_realms")
        categories.add("peacock_kingdom")
        return categories

    def _navigation_detect_categories(self, destination: pages.Page) -> set[str]:
        """导航识别当前页时保留孔雀国分类，避免跨副本回退误命中月之海准备页。"""
        categories = super()._navigation_detect_categories(destination)
        categories.add("peacock_kingdom")
        return categories

    @property
    def pk_page_handle_dict(self) -> dict[pages.Page, Callable]:
        return {
            pages.page_peacock_kingdom: self.run_on_pk,
            pages.page_pk_prepare: self._enter_pk_main_from_prepare,
            pages.page_pk_main: self.run_on_pk_main,
            pages.page_pk_shop_land: self.run_on_pk_store,
            pages.page_pk_mistery_land: lambda : self.goto_page(pages.page_pk_main),
            pages.page_pk_chaos_land: self.run_on_pk_chaos,
            pages.page_pk_bloom_land: lambda : self.goto_page(pages.page_pk_main),
            pages.page_pk_battle_land: self.run_on_pk_battle,
            pages.page_pk_challenge: self.run_on_pk_challenge,
            pages.page_pk_map: lambda: self.goto_page(pages.page_pk_main),
            pages.page_pk_exit: lambda: self.click(pages.random_click(ltrb=(True, False, False, False)), interval=1.2),
            pages.page_sr_prepare_exit: lambda: self.goto_page(pages.page_pk_prepare),
            pages.page_sr_open_store: self.run_on_pk_store_confirm,
            pages.page_battle_prepare: self.run_on_pk_challenge,
            pages.page_battle: self.run_on_pk_challenge,
            pages.page_battle_result: self.run_on_pk_challenge,
            pages.page_reward: lambda: self.click(pages.random_click(), interval=1.2),
        }

    def run(self):
        self.before_run()
        logger.hr('Peacock Kingdom', 1)
        while True:
            self.screenshot()
            current_page = self.get_current_page()
            if current_page is None:
                time.sleep(0.5)
                continue
            handle = self.pk_page_handle_dict.get(current_page, None)
            if handle is None:
                self.goto_page(pages.page_peacock_kingdom)
                continue
            try:
                handle()
            except TaskEnd:
                break
        logger.info('Peacock Kingdom task ended')
                
    def run_on_pk(self):
        """孔雀国界面"""
        if self.appear_then_click(self.I_PK_CONTINUE, interval=1):
            return
        if self.appear_then_click(self.I_PK_START, interval=1):
            self.thunder_state_known = True
            return

    def _enter_pk_main_from_prepare(self):
        """从孔雀国准备界面进入主界面，标记本局为完整新开局。"""
        self.thunder_state_known = True
        self.goto_page(pages.page_pk_main)

    def run_on_pk_prepare(self):
        """进入孔雀国主界面前的准备界面"""
        if self.appear_then_click(self.I_PK_START_CONFIRM, interval=1.5) or \
                self.appear_then_click(self.I_PK_START_CONFIRM2, interval=1.5) or \
                self.appear_then_click(self.I_PK_START_THIRD_SKILL, interval=1.5) or \
                self.appear_then_click(self.I_MFIRST_SKILL, interval=1.5):
            return

    def _filter_island(self, appeared_islands: list[RuleImage]) -> list[RuleImage]:
        remain_turns = self.get_remain_turns(self.O_REMAIN_TURNS)
        appeared_shop = self.appear(self.I_PK_LAND_STORE)
        # 当前没有商店且已经跳过两个绽放之屿了(剩余不到9回合), 还是没有轰雷, 则只要钱够就开商店找轰雷
        if not appeared_shop and self.skill_roaring_thunder == 0 and remain_turns <= 9 and self.coin_num >= 600:
            if self._summon_store():
                return []
        # 出现商店&岛屿数量>2&金币不够买轰雷&剩余回合数>1, 则不选择商店, 先攒金币
        if self.skill_roaring_thunder == 0 and appeared_shop and \
                len(appeared_islands) >= 2 and self.coin_num < 300 and remain_turns > 1:
            logger.info('Money is not enough, choose other land')
            appeared_islands.remove(self.I_PK_LAND_STORE)
        # 已经获得轰雷且可选岛屿较少时，使用唤息跳过普通岛屿
        if self._should_use_breath(appeared_islands) and self._use_breath():
            return []
        return appeared_islands

    def _should_use_breath(self, current_islands: list[RuleImage]) -> bool:
        """判断当前是否满足使用唤息的条件。"""
        return not self.breath_failed and \
            self.skill_roaring_thunder >= 1 and \
            len(current_islands) < 4 and \
            self.coin_num >= 300 and \
            self.appear(self.I_M_STORE_ACTIVITY) and \
            not self.appear(self.I_PK_BOSS_PREPARE) and \
            self.I_PK_LAND_STORE not in current_islands and \
            self.I_PK_LAND_MYSTERY not in current_islands and \
            self.I_PK_LAND_BLOOM not in current_islands and \
            self.get_remain_turns(self.O_REMAIN_TURNS) <= 9

    def _summon_store(self) -> bool:
        """无轰雷时单次唤息召唤宁息商店。"""
        if self.breath_failed:
            return False
        if not self.appear_then_click(self.I_M_STORE_ACTIVITY, interval=1.5):
            return False
        if not self.wait_until_appear(self.I_UI_CONFIRM, wait_time=2):
            return False
        if not self.appear_then_click(self.I_UI_CONFIRM, interval=1):
            return False
        self.coin_num = max(0, self.coin_num - 300)
        logger.info('召唤宁息商店')
        return True

    def _use_breath(self) -> bool:
        """点击唤息并处理金币为300时出现的确认弹窗。"""
        if not self.appear_then_click(self.I_M_STORE_ACTIVITY, interval=1.5):
            return False
        if self._confirm_store_entry(wait_time=5):
            # 唤息成功后同步扣除金币，避免使用旧金币状态再次点击唤息
            self.coin_num = max(0, self.coin_num - 300)
            logger.info('使用唤息')
            return True
        self._mark_breath_failed('唤息弹窗没有确认成功')
        return False

    def _mark_breath_failed(self, reason: str) -> None:
        """本轮不再唤息：确认不了时原逻辑会取消回主界面、条件不变又去唤息，循环到 GameTooManyClickError。"""
        self.breath_failed = True
        logger.warning(f'{reason}，本轮不再使用唤息')

    def _confirm_store_entry(self, wait_time: float = None) -> bool:
        """点击唤息确认弹窗的确认按钮。

        2026-10-10 起弹窗是公共新版双按钮，确认键文字是「确认」；旧模板「进入」（`I_PK_STORE_STILLIN`）只剩
        0.028，先走 `_confirm_breath_dialog`，旧版「进入」只作兼容兜底（只看当前帧，不再额外等待）。
        """
        if self._confirm_breath_dialog(wait_time or 0):
            return True
        return self.appear_then_click(self.I_PK_STORE_STILLIN, interval=1)

    def _confirm_breath_dialog(self, wait_time: float = 0) -> bool:
        """新版唤息弹窗：正文 `I_MS_CHECK_OPEN_STORE` 命中才点公共「确认」，有界等待 `wait_time` 秒。

        正文不在就不点，不会确认到别的弹窗；看到旧版「进入」立即交回兼容分支。
        """
        timer = Timer(wait_time).start()
        while 1:
            self.screenshot()
            if self.appear(self.I_PK_STORE_STILLIN):
                return False
            if self.appear(self.I_MS_CHECK_OPEN_STORE) and \
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                return True
            if timer.reached():
                return False

    def _should_give_up_boss(self) -> bool:
        """仅当本局已确认过轰雷状态且仍无轰雷时，Boss 战前主动放弃试炼。"""
        return self.thunder_state_known and self.skill_roaring_thunder == 0

    def _give_up_trial(self) -> bool:
        """Boss 战前无轰雷主动放弃试炼：点返回 -> 放弃试炼 -> 确认 -> 失败结算不点双倍直到回入口页。"""
        logger.info('No roaring thunder before boss battle, give up trial')
        if getattr(self, 'device', None) is not None:
            self.device.stuck_record_clear()
        timeout_timer = Timer(self.GIVEUP_TIMEOUT).start()
        confirmed_giveup = False
        left_pk_main = False
        current_page = None
        while not timeout_timer.reached():
            self.screenshot()
            current_page = self.get_current_page()
            if current_page == pages.page_peacock_kingdom:
                logger.info('Give up trial done, arrived page_peacock_kingdom')
                return True
            if not confirmed_giveup:
                if self.appear(self.I_UI_CONFIRM) and self.appear(self.I_UI_CANCEL) and \
                        not self.appear(self.I_MS_CHECK_OPEN_STORE):
                    if self.appear_then_click(self.I_UI_CONFIRM, interval=1.5):
                        confirmed_giveup = True
                        logger.info('Confirmed give up trial')
                    continue
                if self.appear_then_click(self.I_PK_GIVEUP, interval=1.0):
                    continue
                if current_page == pages.page_pk_main and \
                        self.appear_then_click(self.I_UI_BACK_BLUE, interval=1.2):
                    continue
                continue
            if not left_pk_main and current_page != pages.page_pk_main and \
                    not self.appear(self.I_PK_CHECK_MAIN) and not self.appear(self.I_PK_BOSS_PREPARE):
                left_pk_main = True
            if not left_pk_main:
                if self.appear(self.I_UI_CONFIRM) and self.appear(self.I_UI_CANCEL) and \
                        not self.appear(self.I_MS_CHECK_OPEN_STORE):
                    self.appear_then_click(self.I_UI_CONFIRM, interval=1.5)
                continue
            if self.appear_then_click(self.I_SR_DOUBLE_REWARD_CANCEL, interval=1.5):
                continue
            if self.appear(self.I_SR_CHECK_BUY_BOX):
                if self.appear_then_click(self.I_SR_NOT_TIP, interval=1.5) and \
                        self.appear_then_click(self.I_UI_CANCEL):
                    continue
            if self.appear(self.I_UI_CANCEL) and not self.appear(self.I_MS_CHECK_OPEN_STORE):
                self.appear_then_click(self.I_UI_CANCEL, interval=1.5)
                continue
            if current_page == pages.page_reward:
                self.click(pages.random_click(), interval=1.2)
                continue
        page_name = getattr(current_page, 'name', None)
        msg = (
            f'孔雀国放弃试炼超时（{self.GIVEUP_TIMEOUT}s 内未回到入口页：'
            f'confirmed_giveup={confirmed_giveup}, left_pk_main={left_pk_main}, current_page={page_name}）'
        )
        logger.warning(msg)
        raise GameStuckError(msg)

    def run_on_pk_main(self):
        """孔雀国主界面 执行策略选岛屿"""
        # 商店确认弹窗可能被识别为主页面，优先处理进入按钮
        if self.appear(self.I_PK_STORE_STILLIN):
            self.run_on_pk_store_confirm()
            return
        if self.appear(self.I_PK_BOSS_PREPARE):
            if self._should_give_up_boss():
                if self._give_up_trial():
                    raise TaskEnd
                raise GameStuckError('孔雀国放弃试炼未完成')
            if self.enter_battle(self.I_PK_BOSS_FIRE, boss_unlock=self.I_PK_BOSS_UNLOCK, boss_lock=self.I_PK_BOSS_LOCK):
                logger.info('Start boss battle')
                self.run_general_battle(
                    battle_key='boss',
                    exit_matcher=pages.page_peacock_kingdom,
                )
                raise TaskEnd
        # 优先级：商店 > 神秘 > 绽放之屿 > 战斗 > 混沌
        islands = [self.I_PK_LAND_STORE, self.I_PK_LAND_MYSTERY, self.I_PK_LAND_BLOOM, self.I_PK_LAND_FIRE,
                 self.I_PK_LAND_CHAOS]
        self.choose_and_enter_island(islands)

    def run_on_pk_challenge(self):
        """孔雀国挑战界面"""
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            self.run_general_battle(battle_key="normal", exit_matcher=pages.page_pk_main)

    def run_on_pk_store(self):
        """宁息商店"""
        logger.hr('shop land')
        if self.skill_roaring_thunder >= 1:
            logger.info('Skill level is enough, skip shopping')
            self.goto_page(pages.page_pk_main)
            return
        self.coin_num, buy_times = self.buy_skill(self.I_PK_STORE_SKILL_THUNDER, 300, self.O_COIN_NUM,
                                                  self.I_PK_STORE_REFRESH, self.O_PK_STORE_REFRESH_TIME, 1,
                                                  expected_cost=self.PK_SKILL_THUNDER_COST)
        self.skill_roaring_thunder += buy_times
        logger.info(f'Skill level: {self.skill_roaring_thunder}')
        self.goto_page(pages.page_pk_main)

    def run_on_pk_store_confirm(self):
        """处理金币为300时进入宁息商店的确认弹窗。"""
        if self._confirm_store_entry(wait_time=1.5):
            logger.info('确认进入宁息商店')
            return
        if not self.appear(self.I_MS_CHECK_OPEN_STORE):
            # 弹窗已经关了（多半是刚才的确认正在生效），不算失败
            return
        self._mark_breath_failed('唤息弹窗仍在但确认不了')
        self.goto_page(pages.page_pk_main)

    def run_on_pk_chaos(self):
        """混沌之屿 宝箱/精英"""
        logger.hr('chaos land')
        is_box: bool = self.appear(self.I_PK_CHAOS_BOX)
        if is_box:
            logger.info('Do not get box')
            self.goto_page(pages.page_pk_main)
            return
        self.ui_click(self.C_NPC_FIRE_CENTER, self.I_PK_BATTLE_FIRE, interval=0.8)
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            logger.info('Start elite battle')
            self.run_general_battle(battle_key="elite", exit_matcher=pages.page_pk_main)

    def run_on_pk_battle(self):
        """鏖战之屿 普通怪"""
        logger.hr('fire land')
        self.ui_click(self.C_NPC_FIRE_RIGHT, self.I_PK_BATTLE_FIRE, interval=0.8)
        if self.enter_battle(self.I_PK_BATTLE_FIRE):
            logger.info('Start normal battle')
            self.run_general_battle(battle_key="normal", exit_matcher=pages.page_pk_main)
