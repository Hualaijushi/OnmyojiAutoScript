from math import isfinite
from numbers import Integral, Real
from random import SystemRandom


_rng = SystemRandom()


def random_point_in_roi(roi: tuple[int, int, int, int]) -> tuple[int, int]:
    """
    在ROI半开区间内生成均匀随机坐标
    """
    x, y, width, height = roi
    if not all(isinstance(value, Integral) for value in roi):
        raise TypeError(f'ROI必须由整数组成：{roi}')
    if width <= 0 or height <= 0:
        raise ValueError(f'ROI宽高必须大于0：{roi}')

    return (
        _rng.randrange(x, x + width),
        _rng.randrange(y, y + height),
    )


def random_delay(min_seconds: Real, max_seconds: Real) -> float:
    """
    生成指定秒数范围内的连续随机值
    """
    if isinstance(min_seconds, bool) or not isinstance(min_seconds, Real):
        raise TypeError(f'最小秒数必须是数值：{min_seconds}')
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, Real):
        raise TypeError(f'最大秒数必须是数值：{max_seconds}')

    min_seconds = float(min_seconds)
    max_seconds = float(max_seconds)
    if not isfinite(min_seconds) or not isfinite(max_seconds):
        raise ValueError('随机时间范围必须是有限数值')
    if min_seconds < 0 or max_seconds < 0:
        raise ValueError('随机时间范围不能小于0')
    if min_seconds > max_seconds:
        raise ValueError('最小秒数不能大于最大秒数')
    if min_seconds == max_seconds:
        return min_seconds

    return _rng.uniform(min_seconds, max_seconds)
