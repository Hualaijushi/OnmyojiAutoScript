# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

import math

import numpy as np
import cv2

from module.ocr.base_ocr import BaseCor, OcrMode, OcrMethod, OcrMethodType
from module.ocr.sub_ocr import Full, Single, Digit, DigitCounter, Duration, Quantity
from module.click_sampler import ClickSampler
from module.logger import logger

# 游戏固定运行在 1280x720。OCR / OpenCV 检测框贴屏幕右下边缘时，向上取整可能得到
# 1281 / 721，而 random_point_in_roi 的上界是半开的，会取到屏幕外 1px，这里做最小裁剪。
_OCR_CLICK_MAX_X = 1280
_OCR_CLICK_MAX_Y = 720


def _normalize_ocr_click_area(area) -> tuple:
    """
    把 OCR / OpenCV 检测框（可能是 numpy 浮点）的 (x, y, width, height) 规范化成
    ClickSampler / random_point_in_roi 要求的整数 ROI。

    - 左 / 上边界 floor，右 / 下边界 ceil：整数框完全包住原浮点框，取整不缩小可点区域；
    - 已是整数的 ROI（RuleClick / RuleImage、以及非 FULL 模式的静态 self.roi）经此变换
      结果不变，语义保持；
    - 贴边时把右 / 下裁到 1280 / 720，不引入新的全局裁剪语义；
    - 兜底保证宽 / 高 >= 1，绝不产生 0 或负尺寸。
    """
    if area is None or len(area) != 4:
        return area

    x, y, width, height = area
    x1 = max(0, math.floor(x))
    y1 = max(0, math.floor(y))
    x2 = min(_OCR_CLICK_MAX_X, math.ceil(x + width))
    y2 = min(_OCR_CLICK_MAX_Y, math.ceil(y + height))
    return int(x1), int(y1), max(1, int(x2 - x1)), max(1, int(y2 - y1))


class RuleOcr(Digit, DigitCounter, Duration, Single, Full, Quantity):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def pre_process(self, image):
        match self.method.get_method_type():
            case OcrMethodType.DEFAULT:
                pass
            case OcrMethodType.CF_RGB:
                _val = self.method.get_val()
                lower, upper = _val.split(',')
                lower = np.array([int(lower[i:i + 2], 16) for i in (0, 2, 4)])
                upper = np.array([int(upper[i:i + 2], 16) for i in (0, 2, 4)])
                mask = cv2.inRange(image, lower, upper)
                res_img = cv2.bitwise_and(image, image, mask=mask)
                return res_img
            case OcrMethodType.CF_HSV:
                _val = self.method.get_val()
                lower, upper = _val.split(',')
                lower = np.array([int(lower[i:i + 2], 16) for i in (0, 2, 4)])
                upper = np.array([int(upper[i:i + 2], 16) for i in (0, 2, 4)])
                res_img = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
                mask = cv2.inRange(res_img, lower, upper)
                res_img = cv2.bitwise_and(res_img, res_img, mask=mask)
                res_img = cv2.cvtColor(res_img, cv2.COLOR_HSV2RGB)
                return res_img
        return image

    def after_process(self, result):
        match self.mode:
            case OcrMode.FULL:
                return Full.after_process(self, result)
            case OcrMode.SINGLE:
                return Single.after_process(self, result)
            case OcrMode.DIGIT:
                return Digit.after_process(self, result)
            case OcrMode.DIGITCOUNTER:
                return DigitCounter.after_process(self, result)
            case OcrMode.DURATION:
                return Duration.after_process(self, result)
            case OcrMode.QUANTITY:
                return Quantity.after_process(self, result)
            case _:
                return result

    def ocr(self, image, keyword=None):

        match self.mode:
            case OcrMode.FULL:
                return Full.ocr_full(self, image, keyword)
            case OcrMode.SINGLE:
                return Single.ocr_single(self, image)
            case OcrMode.DIGIT:
                return Digit.ocr_digit(self, image)
            case OcrMode.DIGITCOUNTER:
                return DigitCounter.ocr_digit_counter(self, image)
            case OcrMode.DURATION:
                return Duration.ocr_duration(self, image)
            case OcrMode.QUANTITY:
                return Quantity.ocr_quantity(self, image)
            case _:
                return None

    def coord(self) -> tuple:
        """
        获取一个区域，随机返回一个坐标
        :return:
        """
        area = None
        if self.mode == OcrMode.FULL:
            area = self.area
        else:
            area = self.roi

        # FULL 模式下 self.area 由 OCR 检测框写入，可能是浮点；先规范化成整数 ROI（floor/ceil，
        # 完整包住原框，不放宽下游整数契约），再按目标 preferred 热点 + 偏移模型取点（T7-5）。
        # 无专属 preference 的 OCR 文本 = RULE_FALLBACK，并按 bbox 尺寸适配热点；不恢复 Uniform。
        return ClickSampler.sample_target(_normalize_ocr_click_area(area), self.name)


if __name__ == "__main__":
    pass
