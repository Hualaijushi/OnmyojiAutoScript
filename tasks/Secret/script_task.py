# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
from cached_property import cached_property
from datetime import datetime

from module.exception import TaskEnd
from module.logger import logger
from module.atom.click import RuleClick
from module.atom.ocr import RuleOcr

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_secret_zones, page_shikigami_records, page_battle_result, any_of
from tasks.Secret.config import SecretConfig, Secret
from tasks.Secret.assets import SecretAssets
from tasks.Component.GeneralBattle.general_battle import ExitMatcher, GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Component.GeneralBuff.config_buff import BuffClass
from tasks.WeeklyTrifles.assets import WeeklyTriflesAssets


class ScriptTask(GameUi, GeneralBattle, SwitchSoul, SecretAssets):
    LAYER_TITLE_AREA = (194, 132, 366, 500)
    LAYER_CARD_LEFT = 194
    LAYER_CARD_WIDTH = 360
    LAYER_CARD_HEIGHT = 121
    LAYER_TITLE_TOP_OFFSET = 10
    LAYER_STATUS_OFFSET = (240, 40, 100, 50)

    def _exit_matcher(self) -> ExitMatcher:
        return self.I_SE_FIRE

    @cached_property
    def match_layer(self) -> dict:
        return {
            '壹': 1, '贰': 2,
            '叁': 3, '肆': 4,
            '伍': 5, '陆': 6,
            '柒': 7, '捌': 8,
            '玖': 9, '拾': 10,
        }

    @cached_property
    def layer_title_ocr(self) -> RuleOcr:
        """识别列表内“壹·标题”至“拾·标题”的完整关卡名。"""
        return RuleOcr(
            roi=self.LAYER_TITLE_AREA,
            area=self.LAYER_TITLE_AREA,
            mode='Single',
            method='Default',
            keyword='',
            name='secret_layer_title',
        )

    @cached_property
    def battle_config(self) -> GeneralBattleConfig:
        conf = self.config.model.secret.general_battle
        conf.lock_team_enable = False
        return conf

    def before_run(self):
        battle_result = self.navigator.resolve_page(page_battle_result)
        battle_result.recognizer = any_of(self.I_SE_BATTLE_WIN, battle_result.recognizer)

    def run(self):
        self.before_run()
        self.check_time()
        secret: Secret = self.config.secret
        con = secret.secret_config
        if secret.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(secret.switch_soul.switch_group_team)
        if secret.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(secret.switch_soul.group_name, secret.switch_soul.team_name)
        self.goto_page(page_secret_zones)

        # 进入
        success = True
        self.ui_click(self.I_SE_ENTER, self.I_SE_FIRE)
        time.sleep(1)  # 有一个很傻逼的动画
        self.screenshot()
        if not self.appear(self.I_SE_PLACEMENT):
            logger.warning('Unsuccessful entry. You must have entered the secret zone before.')
            success = False

        # 开始
        logger.info('Start secret zone')
        first_battle = True
        while 1:
            self.screenshot()
            if not success:
                logger.warning('Secret zone failed to enter, skip')
                break
            if not self.appear(self.I_SE_FIRE):
                continue
            if self.appear(self.I_SE_FINISHED_1):
                logger.info('Secret zone finished')
                break
            layer = self.find_battle()
            logger.info(f'Current layer: {layer}')
            if not layer:
                if self.appear(WeeklyTriflesAssets.I_WT_SE_SHARE):
                    logger.warning('You have completed the weekly trifles, skip')
                    break
                text = self.O_SE_TOTAL_TIME.ocr_single(self.device.image)
                if '尚未' not in text:
                    logger.warning('You have completed the weekly trifles, skip')
                    break
                continue
            if layer >= 6:
                first_battle = False
            if first_battle and layer <= 5:
                first_battle = False
                buff = []
                if con.secret_gold_50:
                    buff.append(BuffClass.GOLD_50)
                if con.secret_gold_100:
                    buff.append(BuffClass.GOLD_100)
                if buff is []:
                    buff = None
                self.click_battle()
                success = self.run_general_battle(self.battle_config, buff=buff, battle_key="secret")
                continue
            if not first_battle and layer == 6:
                # 第六次关闭加成，但是发现没有这个接口。。。！！！居然没有注意到
                buff = []
                if con.secret_gold_50:
                    buff.append(BuffClass.GOLD_50_CLOSE)
                if con.secret_gold_100:
                    buff.append(BuffClass.GOLD_100_CLOSE)
                if buff is []:
                    buff = None
                self.click_battle()
                success = self.run_general_battle(self.battle_config, buff=buff, battle_key="secret")
                continue
            elif not first_battle and layer == 9 and con.layer_9:
                self.click_battle()
                success = self.run_general_battle(self.battle_config, battle_key="secret")
                continue
            elif not first_battle and layer == 10 and con.layer_10:
                self.click_battle()
                success = self.run_general_battle(self.battle_config, battle_key="secret")
                break
            elif not first_battle:
                # 其他层
                self.click_battle()
                success = self.run_general_battle(self.battle_config, battle_key="secret")
                continue

        self.goto_page(page_main)
        if con.secret_gold_50 or con.secret_gold_100:
            self.open_buff()
            if con.secret_gold_50:
                self.gold_50(False)
            if con.secret_gold_100:
                self.gold_100(False)
            self.close_buff()
        self.set_next_run(task='Secret', success=True, finish=True)
        raise TaskEnd('Secret')

    def find_battle(self, screenshot: bool = False) -> int or None:
        """按关卡标题定位卡片，只选择状态为“未通关”的关卡。"""
        if screenshot:
            self.screenshot()
        if self.appear(self.I_CHAT_CLOSE_BUTTON):
            self.ui_click_until_disappear(self.I_CHAT_CLOSE_BUTTON, interval=2)

        roi_x, roi_y, _, _ = self.LAYER_TITLE_AREA
        candidates = []
        for result in self.layer_title_ocr.detect_and_ocr(
            self.device.image
        ):
            text = ''.join(str(result.ocr_text or '').split())
            if not text:
                continue
            layer = self.match_layer.get(text[0])
            if layer is None:
                continue

            points = result.box
            title_left = roi_x + min(int(point[0]) for point in points)
            title_top = roi_y + min(int(point[1]) for point in points)
            card_top = max(0, title_top - self.LAYER_TITLE_TOP_OFFSET)
            card_top = min(
                self.device.image.shape[0] - self.LAYER_CARD_HEIGHT,
                card_top,
            )
            candidates.append({
                'layer': layer,
                'title': text,
                'title_position': (title_left, title_top),
                'card_roi': (
                    self.LAYER_CARD_LEFT,
                    card_top,
                    self.LAYER_CARD_WIDTH,
                    self.LAYER_CARD_HEIGHT,
                ),
            })

        # OCR 偶尔会为同一标题返回重叠文本，只保留每个卡片位置的
        # 第一条结果，并按照画面从上到下检查。
        distinct = []
        for candidate in sorted(
            candidates,
            key=lambda item: item['card_roi'][1],
        ):
            if any(
                abs(
                    candidate['card_roi'][1]
                    - kept['card_roi'][1]
                ) <= 12
                for kept in distinct
            ):
                continue
            distinct.append(candidate)

        for candidate in distinct:
            card_x, card_y, _, _ = candidate['card_roi']
            offset_x, offset_y, status_width, status_height = (
                self.LAYER_STATUS_OFFSET
            )
            status_roi = (
                card_x + offset_x,
                card_y + offset_y,
                status_width,
                status_height,
            )
            status_rule = RuleOcr(
                roi=status_roi,
                area=status_roi,
                mode='Single',
                method='Default',
                keyword='',
                name=f'secret_layer_{candidate["layer"]}_status',
            )
            status = ''.join(
                str(status_rule.ocr(self.device.image) or '').split()
            )
            logger.info(
                f'Secret layer candidate: '
                f'layer={candidate["layer"]}, '
                f'title=[{candidate["title"]}], '
                f'status=[{status}], card={candidate["card_roi"]}'
            )
            if '未解锁' in status:
                continue
            if '未通关' not in status:
                # 时间或其他完成信息都表示该层已经挑战过。
                continue

            # 点击卡片左侧内容区，避开右侧状态文字；按需求连续点击两次。
            click_roi = (
                card_x + 12,
                card_y + 8,
                216,
                self.LAYER_CARD_HEIGHT - 16,
            )
            click_rule = RuleClick(
                roi_front=click_roi,
                roi_back=click_roi,
                name=f'secret_layer_{candidate["layer"]}_card',
            )
            click_x, click_y = click_rule.center
            for click_index in range(1, 3):
                self.device.click(
                    x=click_x,
                    y=click_y,
                    control_name=(
                        f'SECRET_LAYER_{candidate["layer"]}'
                        f'_SELECT_{click_index}'
                    ),
                )
                time.sleep(0.4)
            return candidate['layer']

        # 当前画面没有可挑战关卡时继续向下滚动，外层循环会重新 OCR。
        self.swipe(self.S_SE_DOWN_SEIPE, interval=3)
        time.sleep(2)
        return None

    def click_battle(self):
        while 1:
            self.screenshot()
            if not self.appear(self.I_SE_FIRE):
                break
            if self.appear_then_click(self.I_SE_FIRE, interval=1):
                continue

    def check_time(self) -> None:
        """
        周一早上不能打
        @return:
        """
        time_now = datetime.now()
        if time_now.weekday() == 0 and time_now.hour < 8:
            self.set_next_run(task='Secret',
                              finish=True,
                              target=time_now.replace(hour=9, minute=0, second=0, microsecond=0))
            raise TaskEnd('Secret')


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
