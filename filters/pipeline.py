from __future__ import annotations

import copy
import logging
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Hashable

from PIL import Image, ImageOps

from filters.base import FilterBase

log = logging.getLogger(__name__)
timing_log = logging.getLogger("img2data.filter_timing")


@dataclass(frozen=True)
class FilterResult:
    key: Hashable
    version: int
    filter_name: str
    mask: Image.Image | None = None
    histogram: tuple[int, ...] | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class _FilterJob:
    key: Hashable
    version: int
    filter_type: type[FilterBase]
    parameters: dict
    image: Image.Image
    submitted_at: float
    generation: object


class FilterPipeline:
    """Run filter calculations serially, coalescing queued updates per filter key."""

    def __init__(self):
        self._condition = threading.Condition()
        self._pending: OrderedDict[Hashable, _FilterJob] = OrderedDict()
        self._latest_versions: dict[Hashable, int] = {}
        self._next_version = 0
        self._filter_cache: dict[Hashable, FilterBase] = {}
        self._generations: dict[Hashable, object] = {}
        self._results: deque[FilterResult] = deque()
        self._closed = False
        self._worker = threading.Thread(
            target=self._run, name="filter-pipeline", daemon=True)
        self._worker.start()

    def submit(self, key: Hashable, filter_: FilterBase, image: Image.Image, *,
               parameter_overrides: dict | None = None) -> int:
        """Queue the latest filter configuration for a particular preview."""
        started = time.perf_counter()
        with self._condition:
            if self._closed:
                raise RuntimeError("Cannot submit work to a closed filter pipeline")
            self._next_version += 1
            version = self._next_version
            self._latest_versions[key] = version
            replaced = key in self._pending
            generation = self._generations.setdefault(key, object())
            parameters = copy.deepcopy(filter_.parameters)
            if parameter_overrides:
                for name, value in parameter_overrides.items():
                    parameters[name] = {**parameters.get(name, {}), **copy.deepcopy(value)}
            self._pending[key] = _FilterJob(
                key, version, type(filter_), parameters, image, started,
                generation)
            self._condition.notify()
        timing_log.debug("submit filter=%s version=%d image=%s replaced=%s elapsed_ms=%.2f",
                         type(filter_).__name__, version, image.size, replaced,
                         (time.perf_counter() - started) * 1000)
        return version

    def is_latest(self, key: Hashable, version: int) -> bool:
        with self._condition:
            return self._latest_versions.get(key) == version

    def get_result(self) -> FilterResult | None:
        """Return the next result, or None when no result is ready."""
        with self._condition:
            return self._results.popleft() if self._results else None

    def cancel(self, key: Hashable) -> None:
        """Discard pending work and cached data for a closed preview."""
        with self._condition:
            self._pending.pop(key, None)
            self._latest_versions.pop(key, None)
            self._filter_cache.pop(key, None)
            self._generations.pop(key, None)
            self._results = deque(result for result in self._results if result.key != key)

    def invalidate(self, key: Hashable) -> None:
        """Discard outstanding work while retaining image-dependent caches."""
        with self._condition:
            self._pending.pop(key, None)
            self._latest_versions.pop(key, None)
            self._results = deque(result for result in self._results if result.key != key)

    def close(self, wait: bool = False) -> None:
        """Discard queued work and stop after the currently-running filter finishes."""
        with self._condition:
            if not self._closed:
                self._closed = True
                self._pending.clear()
                self._latest_versions.clear()
                self._filter_cache.clear()
                self._generations.clear()
                self._results.clear()
                self._condition.notify_all()
        if wait and threading.current_thread() is not self._worker:
            self._worker.join()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                _, job = self._pending.popitem(last=False)

            started = time.perf_counter()
            try:
                with self._condition:
                    current_generation = self._generations.get(job.key) is job.generation
                    filter_instance = self._filter_cache.get(job.key) if current_generation else None
                if filter_instance is None or type(filter_instance) is not job.filter_type:
                    with self._condition:
                        if self._generations.get(job.key) is job.generation:
                            self._filter_cache.pop(job.key, None)
                    filter_instance = job.filter_type()
                    if getattr(job.filter_type, "cache_worker_instance", False):
                        with self._condition:
                            if (job.key in self._latest_versions and not self._closed
                                    and self._generations.get(job.key) is job.generation):
                                self._filter_cache[job.key] = filter_instance
                else:
                    filter_instance.parameters.clear()
                filter_instance.set_parameters(job.parameters)
                histogram_started = time.perf_counter()
                histogram = filter_instance.preview_histogram(job.image)
                histogram_ms = (time.perf_counter() - histogram_started) * 1000
                mask_started = time.perf_counter()
                mask = filter_instance.mask(job.image)
                if mask is None:
                    raise TypeError(f"{job.filter_type.__name__}.mask() returned None")
                if job.parameters.get("invert", {}).get("default", False):
                    mask = ImageOps.invert(mask.convert("L"))
                mask_ms = (time.perf_counter() - mask_started) * 1000
                result = FilterResult(
                    job.key, job.version, job.filter_type.__name__,
                    mask=mask, histogram=histogram)
                timing_log.debug(
                    "worker filter=%s version=%d image=%s queue_ms=%.2f histogram_ms=%.2f "
                    "mask_ms=%.2f total_ms=%.2f",
                    job.filter_type.__name__, job.version, job.image.size,
                    (started - job.submitted_at) * 1000, histogram_ms, mask_ms,
                    (time.perf_counter() - started) * 1000)
            except Exception as exc:
                log.exception("Filter %s failed", job.filter_type.__name__)
                result = FilterResult(
                    job.key, job.version, job.filter_type.__name__, error=exc)

            with self._condition:
                if (job.key in self._latest_versions and not self._closed
                        and self._generations.get(job.key) is job.generation):
                    self._results.append(result)
