# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from module.atom.ocr import RuleOcr
from module.atom.image import RuleImage
from module.base.timer import Timer
from module.logger import logger

from tasks.base_task import BaseTask
from tasks.Utils.config_enum import ShikigamiClass
from tasks.Component.ReplaceShikigami.assets import ReplaceShikigamiAssets
import time
from time import monotonic
from module.exception import GameStuckError


class ReplaceShikigami(BaseTask, ReplaceShikigamiAssets):
    # 分类切换（`switch_shikigami_class`）的本地边界。正常流程只有两步点击：先点左下角当前分类图标
    # （「全部」）展开分类，再点目标分类，随后目标分类的「已选中」图标出现；允许把这两步整体再重复一轮
    # （吸收一次丢失的点击），共 4 次点击。它必须小于 Device 兜底的「同一按钮 10 次 / 两个按钮各 6 次」
    # （`click_record_check`），这样先触发的是这里的业务失败，而不是重启游戏的 GameTooManyClickError。
    SWITCH_CLASS_MAX_CLICKS = 4
    # 最后一次点击之后再观察多久才判失败：与目标按钮自身的重点击间隔（3 秒）一致——原逻辑认为 3 秒内
    # 没有生效才会再点，所以最后一次点击也要给足这段时间确认，否则会把「刚点中还没刷新」误判为失败。
    SWITCH_CLASS_SETTLE = 3.0
    # 本次分类切换的总耗时上限（软边界）：4 次点击的最坏耗时约 20 秒（左下角图标 5 秒重点击间隔 + 目标
    # 按钮位置稳定等待最多 2.5 秒），加上最后一次确认；取 30 秒，并且小于 Device 的 60 秒无点击卡死判定。
    # 只在控制权回到循环时才检查，不能中断底层某次永久阻塞的调用。
    SWITCH_CLASS_TIMEOUT = 30

    def in_shikigami_growth(self, screenshot=False) -> bool:
        # 判定是否在式神育成界面
        # 判定的依据是是否出现了 式神录 这个图片
        if screenshot:
            self.screenshot()
        return self.appear(self.I_RS_RECORDS_SHIKI, interval=0.5)

    def switch_shikigami_class(self, shikigami_class: ShikigamiClass = ShikigamiClass.N,
                               deadline: float = None):
        """
        要求在式神育成的界面
        切换分类；成功标志是目标分类的「已选中」图标（`I_RS_*_SELECTED`）在重新截图后出现。
        :param shikigami_class:
        :param deadline: 调用方给的绝对截止时间（`time.monotonic()` 口径），与本地 30 秒上限取较早者，
                         让上层任务的总时间预算不会因为反复调用本函数而被重新获得。
        :raise GameStuckError: 点击次数或耗时用尽仍没有确认选中目标分类。
        """
        match_selected = {ShikigamiClass.MATERIAL: self.I_RS_MATERIAL_SELECTED,
                          ShikigamiClass.N: self.I_RS_N_SELECTED,
                          ShikigamiClass.R: self.I_RS_R_SELECTED,
                          ShikigamiClass.SR: self.I_RS_SR_SELECTED,
                          ShikigamiClass.SSR: self.I_RS_SSR_SELECTED,
                          ShikigamiClass.SP: self.I_RS_SP_SELECTED,
                          ShikigamiClass.UR: self.I_RS_UR_SELECTED}
        match_click = {ShikigamiClass.MATERIAL: self.I_RS_MATERIAL,
                       ShikigamiClass.N: self.I_RS_N,
                       ShikigamiClass.R: self.I_RS_R,
                       ShikigamiClass.SR: self.I_RS_SR,
                       ShikigamiClass.SSR: self.I_RS_SSR,
                       ShikigamiClass.SP: self.I_RS_SP,
                       ShikigamiClass.UR: self.I_RS_UR}
        check_selected = match_selected[shikigami_class]
        check_click = match_click[shikigami_class]
        # 选择式神的种类
        end_time = monotonic() + self.SWITCH_CLASS_TIMEOUT
        if deadline is not None:
            end_time = min(end_time, deadline)
        clicks = 0
        last_click_time = None
        while 1:
            self.screenshot()
            # 成功只认重新截图后的「已选中」图标；已经在目标分类时第一帧就直接成功
            if self.appear(check_selected, interval=1):
                break
            # 还没确认选中：任何点击之前先检查边界。点击次数和耗时都不会因为找到按钮 / 重新截图而清零
            if monotonic() >= end_time:
                logger.error(f'式神分类切换超时：已点击 {clicks} 次仍未确认选中 {shikigami_class}')
                raise GameStuckError(f'式神分类切换超时（{shikigami_class}）')
            if clicks >= self.SWITCH_CLASS_MAX_CLICKS:
                # 不再点击，只等最后一次点击刷新界面；观察满一个间隔仍没有选中才判失败
                if monotonic() - last_click_time >= self.SWITCH_CLASS_SETTLE:
                    logger.error(f'式神分类切换失败：已点击 {clicks} 次仍未确认选中 {shikigami_class}')
                    raise GameStuckError(f'式神分类切换失败（{shikigami_class}）')
                continue
            if self.appear(check_click, interval=3):
                if self.wait_until_pos_stable(check_click, stable_time=0.8, timeout=2.5):
                    self.click(check_click)
                    clicks += 1
                    last_click_time = monotonic()
                continue
            if self.appear_then_click(self.I_RS_ALL_SELECTED, interval=5):
                clicks += 1
                last_click_time = monotonic()
                continue
        logger.info('Select shikigami class: %s' % shikigami_class)

    def unset_shikigami_max_lv(self):
        """
        要求在式神育成的界面
        拉下满级的式神，留空位置
        :return:
        """
        while 1:
            self.screenshot()
            if not self.appear(self.I_RS_LEVEL_MAX):
                break
            else:
                self.appear_then_click(self.I_RS_LEVEL_MAX, interval=0.5)
        logger.info('Unset all shikigami max lv')

    def set_shikigami(self, shikigami_order: int = 7, stop_image: RuleImage = None):
        """
        要求在式神育成的界面
        选择式神 1-7
        :param stop_image:  结束的图片，如果不出现就结束
        :param shikigami_order:
        :return:
        """
        # 选择式神
        _click_match = {1: self.C_SHIKIGAMI_LEFT_1,
                        2: self.C_SHIKIGAMI_LEFT_2,
                        3: self.C_SHIKIGAMI_LEFT_3,
                        4: self.C_SHIKIGAMI_LEFT_4,
                        5: self.C_SHIKIGAMI_LEFT_5,
                        6: self.C_SHIKIGAMI_LEFT_6,
                        7: self.C_SHIKIGAMI_LEFT_7}
        click_match = _click_match[shikigami_order]
        TIMEOUT_SEC = 120          # 超时时长（秒）
        start_time = time.time()   # 记录起始时间
        click_interval_timer = Timer(1.5).start()  # 点击选择式神间隔
        clicked = False
        while 1:
            # ——1. 先做超时检查——
            if time.time() - start_time > TIMEOUT_SEC:
                logger.error('寄养等待超过 2 分钟，自动退出')
                raise GameStuckError('寄养超时（>120 s）')
            # 恢复点击操作
            if click_interval_timer.reached_and_reset():
                clicked = False
            self.screenshot()
            if self.appear_then_click(self.I_U_CONFIRM_SMALL, interval=0.5):
                clicked = False  # 点击了确认, 恢复选式神的操作
                continue
            if not self.appear(stop_image):
                break
            # 与下方点击第7个式神操作互斥, 防止确认按钮还没有出现被下方取消掉
            if not clicked and self.click(click_match, interval=1.5):
                clicked = True
                continue
            if not clicked and self.click(_click_match[6], interval=4.5):
                # 有的时候第七个格子被占用到寄养上去了
                # 导致一直无法选上
                clicked = True
                continue
            if self.appear_then_click(self.I_U_CIRCLE_ALTERNATE, interval=2.5):
                self.appear_then_click(self.I_U_CONFIRM_ALTERNATE, interval=1.5)
                continue
        logger.info('Set shikigami: %d' % shikigami_order)

    def detect_no_shikigami(self) -> bool:
        self.screenshot()
        if self.appear(self.I_DETECT_EMPTY_1)\
            or self.appear(self.I_DETECT_EMPTY_2) \
                or self.appear(self.I_DETECT_EMPTY_3) \
                or self.appear(self.I_DETECT_EMPTY_4) \
                or self.appear(self.I_DETECT_EMPTY_5) \
                or self.appear(self.I_DETECT_EMPTY_6):
            return True
        return False


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('日常2')
    d = Device(c)
    t = ReplaceShikigami(c, d)
    t.switch_shikigami_class(ShikigamiClass.N)
