from __future__ import annotations

import hashlib
import itertools
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable


class OcrServiceClosedError(RuntimeError):
    pass


class StaleOcrRequestError(TimeoutError):
    pass


@dataclass(order=True)
class _QueuedRequest:
    priority: int
    sequence: int
    created_at: float = field(compare=False)
    ttl: float = field(compare=False)
    key: tuple = field(compare=False)
    recognizer: Callable[[Any], Any] = field(compare=False)
    image: Any = field(compare=False)
    future: Future = field(compare=False)
    cache_ttl: float = field(compare=False)


_SENTINEL = _QueuedRequest(
    2**31 - 1, 2**63 - 1, 0.0, 0.0, (), lambda value: value, None, Future(), 0.0
)


class OCRService:
    """Small local scheduler in front of the existing shared OCR RPC service.

    It does not start another OCR engine.  OAS processes still share the
    project's RPC server; this class only serializes a client's requests.
    """

    _instance: "OCRService | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None or cls._instance._closed:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, worker_count: int = 1) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._closed = False
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._sequence = itertools.count()
        self._guard = threading.RLock()
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._inflight: dict[tuple, Future] = {}
        self._workers = [
            threading.Thread(target=self._worker, name=f"account-ocr-{index + 1}", daemon=True)
            for index in range(max(1, int(worker_count)))
        ]
        for worker in self._workers:
            worker.start()

    @classmethod
    def get_instance(cls) -> "OCRService":
        return cls()

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instance_lock:
            instance = cls._instance
            cls._instance = None
        if instance is not None:
            instance.shutdown(wait=True)

    @staticmethod
    def _image_identity(image: Any, frame_id: str | int | None) -> str:
        if frame_id is not None:
            return str(frame_id)
        try:
            raw = memoryview(image).cast("B")
            return hashlib.blake2b(raw, digest_size=8).hexdigest()
        except (TypeError, ValueError):
            return f"object:{id(image)}"

    def submit(
        self,
        recognizer: Callable[[Any], Any],
        image: Any,
        *,
        frame_id: str | int | None = None,
        recognition_type: str = "generic",
        region: tuple | None = None,
        priority: int = 10,
        ttl: float = 5.0,
        cache_ttl: float = 2.0,
        use_cache: bool = True,
    ) -> Future:
        if self._closed:
            raise OcrServiceClosedError("OCR service is closed")
        now = time.monotonic()
        key = (self._image_identity(image, frame_id), recognition_type, tuple(region or ()))
        with self._guard:
            cached = self._cache.get(key)
            if use_cache and cached and cached[0] > now:
                future = Future()
                future.set_result(cached[1])
                return future
            if cached:
                self._cache.pop(key, None)
            if key in self._inflight:
                return self._inflight[key]
            future = Future()
            self._inflight[key] = future
            self._queue.put(_QueuedRequest(
                int(priority), next(self._sequence), now, max(0.0, float(ttl)), key,
                recognizer, image, future, max(0.0, float(cache_ttl)),
            ))
            return future

    def recognize(self, recognizer: Callable[[Any], Any], image: Any, *, timeout: float = 30.0, **kwargs) -> Any:
        return self.submit(recognizer, image, **kwargs).result(timeout=timeout)

    def recognize_rule(
        self,
        rule,
        image: Any,
        *,
        frame_id: str | int | None = None,
        priority: int = 10,
        timeout: float = 30.0,
        ttl: float = 5.0,
        cache_ttl: float = 2.0,
    ) -> Any:
        """Run an existing RuleOcr through its configured shared RPC model."""
        mode = getattr(getattr(rule, "mode", None), "value", getattr(rule, "mode", "generic"))
        region = getattr(rule, "area", None) or getattr(rule, "roi", None)
        return self.recognize(
            rule.ocr,
            image,
            frame_id=frame_id,
            recognition_type=f"rule:{getattr(rule, 'name', mode)}:{mode}",
            region=region,
            priority=priority,
            timeout=timeout,
            ttl=ttl,
            cache_ttl=cache_ttl,
        )

    def _worker(self) -> None:
        while True:
            request = self._queue.get()
            if request is _SENTINEL:
                self._queue.task_done()
                return
            try:
                if request.future.cancelled():
                    continue
                if request.ttl and time.monotonic() - request.created_at > request.ttl:
                    raise StaleOcrRequestError("OCR request expired in queue")
                result = request.recognizer(request.image)
                if request.cache_ttl:
                    with self._guard:
                        self._cache[request.key] = (time.monotonic() + request.cache_ttl, result)
                request.future.set_result(result)
            except BaseException as exc:
                if not request.future.done():
                    request.future.set_exception(exc)
            finally:
                with self._guard:
                    if self._inflight.get(request.key) is request.future:
                        self._inflight.pop(request.key, None)
                self._queue.task_done()

    def shutdown(self, *, wait: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        for _ in self._workers:
            self._queue.put(_SENTINEL)
        if wait:
            for worker in self._workers:
                worker.join(timeout=5)
