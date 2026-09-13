# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from module.atom.swipe_endpoint import sample_swipe_endpoints
from module.base.utils.random import random_center_point_in_roi
from module.logger import logger


class RuleSwipe:

    def __init__(self, roi_front: tuple, roi_back: tuple, mode: str, name: str =None) -> None:
        """
        初始化
        :param roi_front:
        :param roi_back:
        :param mode:
        """
        self.roi_front = roi_front
        self.roi_back = roi_back
        self.mode = mode
        if name:
            self.name = name
        else:
            self.name = 'swipe'

        self.interval: int = 8  # 每次移动的间隔时间

    def coord(self) -> tuple:
        """
        获取坐标, 从roi_front随机获取坐标 和从roi_back随机获取的坐标
        :return: 两个坐标的tuple

        旧端点访问器：起终点各在自己 ROI 内中心偏置随机。保留给兼容 / 测试
        （生产滑动已改走 `sample_endpoints()`，见 `docs/DECISIONS.md` D022）。
        """
        start_x, start_y = random_center_point_in_roi(self.roi_front)
        end_x, end_y = random_center_point_in_roi(self.roi_back)
        return start_x, start_y, end_x, end_y

    def sample_endpoints(self) -> tuple:
        """普通滑动的 v2 端点采样（`BaseTask.swipe` 使用）。

        `roi_front` / `roi_back` 只表达方向与基准距离；具体起点 / 终点由
        `module/atom/swipe_endpoint.py` 采样：起终点各自独立、主成分集中 + 少量更宽尾部、
        夹到安全范围，并联合保证方向 / 有效距离不被破坏。见 `docs/DECISIONS.md` D022。
        """
        return sample_swipe_endpoints(self.roi_front, self.roi_back)
