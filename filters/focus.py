from functools import cached_property
from socket import fromfd

import logging
import time

import cv2
import numpy as np
from PIL import Image

from filters.base import FilterBase

timing_log = logging.getLogger("img2data.filter_timing")


class FilterFocus(FilterBase):
    cache_worker_instance = True
    histogram_image_only = True
    histogram_threshold = "focus_threshold"

    def __init__(self):
        super().__init__()
        self.parameters = {
            "focus_threshold": {"label": "Focus Threshold", "type": "int", "default": 100, "range": (0, 255)},
            "dilate_px": {"label": "Dilate Radius (px)", "type": "int", "default": 0, "range": (0, 30)},
            "erode_px": {"label": "Erode Radius (px)", "type": "int", "default": 0, "range": (0, 30)},
            "focus_colour": {"label": "Focus Colour", "type": "colour", "default": "#00FF00"},
        }
        self.laplacian: np.ndarray | None = None
        self._source_image = None

    @property
    def metric_label(self) -> str:
        return "Focus (0-255)"


    def metric(self, image: Image.Image) -> np.ndarray:
        started = time.perf_counter()
        laplacian = self.laplacian
        cache_hit = image is self._source_image and laplacian is not None
        if not cache_hit:
            image_rgb = np.asarray(image.convert("RGB"))
            gray_image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
            source_laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
            max_focus_measure = float(np.max(np.abs(source_laplacian)))
            if max_focus_measure:
                laplacian = cv2.convertScaleAbs(
                    source_laplacian, alpha=255.0 / max_focus_measure)
            else:
                laplacian = np.zeros_like(gray_image)
            self.laplacian = laplacian
            self._source_image = image
        timing_log.debug("focus_metric image=%s cache_hit=%s elapsed_ms=%.2f",
                         image.size, cache_hit, (time.perf_counter() - started) * 1000)
        return laplacian

    def compute(self, image, *args, **kwargs) -> Image.Image:
        if not self.enabled:
            return Image.new("L", image.size, 0)
        threshold = int(self.parameters.get("focus_threshold", {}).get("default", 100))
        dilate_px = int(self.parameters.get("dilate_px", {}).get("default", 0))
        erode_px = int(self.parameters.get("erode_px", {}).get("default", 0))
        if not (0 <= dilate_px <= 30 and 0 <= erode_px <= 30):
            raise ValueError("Focus morphology radii must be between 0 and 30 pixels")
        _, mask = cv2.threshold(self.metric(image), threshold, 255, cv2.THRESH_BINARY)
        if dilate_px:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
            mask = cv2.dilate(mask, kernel)
        if erode_px:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * erode_px + 1, 2 * erode_px + 1))
            mask = cv2.erode(mask, kernel)
        return Image.fromarray(mask, mode="L")

    def mask(self, image, *args, **kwargs) -> Image.Image:
        return self.compute(image, *args, **kwargs)
