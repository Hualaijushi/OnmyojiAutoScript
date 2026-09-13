from time import sleep

from module.base.utils.random import random_delay
from module.logger import logger


def sleep_random_delay(min_value: float = 2.0, max_value: float = 6.0, decimal: int = 1):
    """
    防封。注意与公共 random_delay 的区别：本函数直接 sleep，不返回数值。
    """
    sleep(round(random_delay(min_value, max_value), decimal))


def random_sleep(probability: float = 0.05):
    if random_delay(0.0, 1.0) <= probability:
        logger.info('Tigger random sleep')
        sleep_random_delay()
