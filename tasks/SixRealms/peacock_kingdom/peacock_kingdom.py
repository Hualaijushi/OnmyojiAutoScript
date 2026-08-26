import time

from module.atom.image import RuleImage
from module.exception import TaskEnd
from module.logger import logger
from tasks.SixRealms.peacock_kingdom.base_peacock_kingdom import BasePeacockKingdom
import tasks.SixRealms.peacock_kingdom.page as pages
from typing import Callable


class PeacockKingdom(BasePeacockKingdom):

    def _default_detect_categories(self) -> set[str]:
        categories = super()._default_detect_categories()
        categories.add("six_realms")
        categories.add("peacock_kingdom")
        return categories

    @property
    def pk_page_handle_dict(self) -> dict[pages.Page, Callable]:
        return {
            pages.page_peacock_kingdom: self.run_on_pk,
            pages.page_pk_prepare: lambda : self.goto_page(pages.page_pk_main),
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
            return

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
        return self.skill_roaring_thunder >= 1 and \
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
        return False

    def _confirm_store_entry(self, wait_time: int = None) -> bool:
        """点击进入宁息之岚的确认按钮。"""
        if wait_time is not None and \
                not self.wait_until_appear(self.I_PK_STORE_STILLIN, wait_time=wait_time):
            return False
        return self.appear_then_click(self.I_PK_STORE_STILLIN, interval=1)

    def run_on_pk_main(self):
        """孔雀国主界面 执行策略选岛屿"""
        # 商店确认弹窗可能被识别为主页面，优先处理进入按钮
        if self.appear(self.I_PK_STORE_STILLIN):
            self.run_on_pk_store_confirm()
            return
        if self.appear(self.I_PK_BOSS_PREPARE) and \
                self.enter_battle(self.I_PK_BOSS_FIRE, boss_unlock=self.I_PK_BOSS_UNLOCK, boss_lock=self.I_PK_BOSS_LOCK):
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
                                                  self.I_PK_STORE_REFRESH, self.O_PK_STORE_REFRESH_TIME, 1)
        self.skill_roaring_thunder += buy_times
        logger.info(f'Skill level: {self.skill_roaring_thunder}')
        self.goto_page(pages.page_pk_main)

    def run_on_pk_store_confirm(self):
        """处理金币为300时进入宁息商店的确认弹窗。"""
        if self._confirm_store_entry():
            logger.info('确认进入宁息商店')
            return
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
