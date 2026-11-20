"""界面日志采用有界、尽力发送；慢消费者不能阻塞业务线程。"""

import threading
import time
from queue import Empty, Full, Queue


class BoundedLogSender:
    def __init__(self, send, *, capacity=256, max_chars=4096):
        if capacity < 1 or max_chars < 1:
            raise ValueError('界面日志容量和单条长度必须为正数')
        self._send = send
        self._queue = Queue(maxsize=capacity)
        self._max_chars = max_chars
        # _closing 只拒收新日志并排空积压；_stop 是硬停止（发送失败或排空超时）。
        self._closing = threading.Event()
        self._stop = threading.Event()
        self._count_lock = threading.Lock()
        self.dropped = 0
        self._thread = threading.Thread(target=self._run, name='frontend_log_sender', daemon=True)
        self._thread.start()

    def _drop(self):
        with self._count_lock:
            self.dropped += 1

    def put(self, message):
        if self._closing.is_set() or self._stop.is_set():
            return
        if len(message) > self._max_chars:
            message = message[:self._max_chars] + '\n[界面日志已截断，完整内容见本地日志文件]\n'
        try:
            self._queue.put_nowait(message)
            return
        except Full:
            pass
        try:
            self._queue.get_nowait()
            self._queue.task_done()
            self._drop()
        except Empty:
            pass
        try:
            self._queue.put_nowait(message)
        except Full:
            self._drop()

    def _run(self):
        reported = 0
        while not self._stop.is_set():
            try:
                # 关闭阶段不再等新日志，排空即退出。
                message = (self._queue.get_nowait() if self._closing.is_set()
                           else self._queue.get(timeout=0.1))
            except Empty:
                if self._closing.is_set():
                    return
                continue
            try:
                with self._count_lock:
                    dropped = self.dropped
                if dropped > reported:
                    self._send(f'[界面日志拥塞，已丢弃 {dropped} 条；完整记录保留在本地文件]\n')
                    reported = dropped
                self._send(message)
            except Exception:
                # 发送失败不能递归记录日志，也不能反向影响任务。
                self._stop.set()
            finally:
                self._queue.task_done()

    def drain(self, timeout=1.0):
        """有限等待积压日志发出，用于进程退出前送出最后的错误信息。"""
        deadline = time.monotonic() + max(0.0, timeout)
        while self._thread.is_alive() and not self._stop.is_set():
            if self._queue.unfinished_tasks == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout=0.1):
        """先在期限内排空积压再退出；超时则硬停止，不让关闭阻塞业务。"""
        self._closing.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            self._stop.set()
        return not self._thread.is_alive()
