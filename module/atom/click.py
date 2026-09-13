# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from module.base.decorator import cached_property
from module.click_sampler import ClickSampler
from module.logger import logger


class RuleClick:

    def __init__(self, roi_front: tuple, roi_back: tuple, name: str = None) -> None:
        """
        初始化
        :param roi_front:
        :param roi_back:
        """
        self.roi_front = roi_front
        self.roi_back = roi_back
        if name:
            self.name = name
        else:
            self.name = 'click'

    def coord(self) -> tuple:
        """
        获取坐标, 从roi_front按该目标的 preferred 热点 + 偏移模型取点（T7-5）。
        未登记的目标 = RULE_FALLBACK 基础锚点 + default_point，并按 ROI 尺寸适配热点，
        不是整 ROI 均匀。见 docs/DECISIONS.md D014。
        :return:
        """
        return ClickSampler.sample_target(self.roi_front, self.name)

    def coord_more(self) -> tuple:
        """
        从roi_back按同一目标身份取点（roi_back 全仓无调用方，路由一致仅为收敛入口）。
        :return:
        """
        return ClickSampler.sample_target(self.roi_back, self.name)

    @property
    def center(self) -> tuple:
        """
        返回roi_front的中心坐标
        :return:
        """
        x, y, w, h = self.roi_front
        return x + w // 2, y + h // 2

    def move(self, x: int, y: int) -> None:
        """
        移动roi_front, 需要限幅x是0-1280, y是0-720
        :param x:
        :param y:
        :return:
        """
        x, y, w, h = self.roi_front
        x += x
        y += y
        if x <= 0:
            x = 0
        elif x >= 1280:
            x = 1280

        if y <= 0:
            y = 0
        elif y >= 720:
            y = 720

        self.roi_front = x, y, w, h

    def __repr__(self):
        return self.name
