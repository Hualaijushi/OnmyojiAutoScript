"""让 RPC 等待后台任务时仍能处理通信和心跳。"""

import time
from concurrent.futures import TimeoutError

import gevent


def wait_future(future, *, deadline=None):
    """截止时间使用单调时钟；可调用对象用于区分排队与执行预算。"""
    while not future.done():
        limit = deadline() if callable(deadline) else deadline
        if limit is not None and time.monotonic() >= limit:
            raise TimeoutError('后台任务超过等待期限')
        gevent.sleep(0.01)
    return future.result()
