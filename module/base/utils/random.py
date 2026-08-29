from math import isfinite
from numbers import Integral, Real
from random import SystemRandom


_rng = SystemRandom()
_CENTER_BIASED_SAMPLES = 3


def random_int(min_value: int, max_value: int) -> int:
    """
    在闭区间内生成均匀随机整数
    """
    if isinstance(min_value, bool) or not isinstance(min_value, Integral):
        raise TypeError(f'最小值必须是整数：{min_value}')
    if isinstance(max_value, bool) or not isinstance(max_value, Integral):
        raise TypeError(f'最大值必须是整数：{max_value}')
    if min_value > max_value:
        raise ValueError('最小值不能大于最大值')

    return _rng.randint(min_value, max_value)


def random_triangular(min_value: Real, max_value: Real, mode: Real) -> float:
    """
    在指定范围内生成三角分布随机值
    """
    values = (min_value, max_value, mode)
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
        raise TypeError(f'三角分布参数必须是数值：{values}')

    min_value, max_value, mode = map(float, values)
    if not all(isfinite(value) for value in (min_value, max_value, mode)):
        raise ValueError('三角分布参数必须是有限数值')
    if min_value > max_value:
        raise ValueError('最小值不能大于最大值')
    if not min_value <= mode <= max_value:
        raise ValueError('众数必须位于最小值和最大值之间')
    if min_value == max_value:
        return min_value

    return _rng.triangular(min_value, max_value, mode)


def _center_biased_int(start: int, stop: int) -> int:
    """
    在半开区间内生成中心偏置整数
    """
    total = sum(_rng.randrange(start, stop) for _ in range(_CENTER_BIASED_SAMPLES))
    return (total + _CENTER_BIASED_SAMPLES // 2) // _CENTER_BIASED_SAMPLES


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


def random_center_point_in_roi(roi: tuple[int, int, int, int]) -> tuple[int, int]:
    """
    在ROI半开区间内生成中心偏置随机坐标
    """
    x, y, width, height = roi
    if not all(isinstance(value, Integral) for value in roi):
        raise TypeError(f'ROI必须由整数组成：{roi}')
    if width <= 0 or height <= 0:
        raise ValueError(f'ROI宽高必须大于0：{roi}')

    return (
        _center_biased_int(x, x + width),
        _center_biased_int(y, y + height),
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
