import cv2
import numpy as np
from PIL import Image

from filters.base import FilterBase


class FilterBrightness(FilterBase):
    cache_worker_instance = True
    histogram_image_only = True
    histogram_threshold = "brightness_threshold"

    def __init__(self):
        super().__init__()
        self.gray_image: np.ndarray | None = None
        self._source_image = None
        self.parameters = {
            "brightness_threshold": {"label": "Brightness Threshold", "type": "int", "default": 100, "range": (0, 255)},
            "brightness_colour": {"label": "Brightness Colour", "type": "colour", "default": "#FF0000"},
        }

    @property
    def metric_label(self) -> str:
        return "Brightness (0-255)"

    def metric(self, image: Image.Image) -> np.ndarray:
        gray_image = self.gray_image
        if image is not self._source_image or gray_image is None:
            image_rgb = np.asarray(image.convert("RGB"))
            gray_image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
            self.gray_image = gray_image
            self._source_image = image
        return gray_image

    def compute(self, image, *args, **kwargs) -> Image.Image:
        if not self.enabled:
            return Image.new("L", image.size, 0)
        threshold = int(self.parameters.get("brightness_threshold", {}).get("default", 100))
        _, mask = cv2.threshold(self.metric(image), threshold, 255, cv2.THRESH_BINARY)
        return Image.fromarray(mask, mode="L")

    def mask(self, image, *args, **kwargs) -> Image.Image:
        return self.compute(image, *args, **kwargs)
