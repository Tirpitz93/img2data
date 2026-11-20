import cv2
import numpy as np
from PIL import Image

from filters.base import FilterBase


class FilterGreenScreen(FilterBase):
    """Extract the foreground contour nearest the center of an image."""

    cache_worker_instance = True
    histogram_image_only = True

    def __init__(self):
        super().__init__()
        self.parameters = {
            "enabled": {"default": False},
            "hue_min": {"label": "Background Hue Min", "type": "int", "default": 35, "range": (0, 179)},
            "hue_max": {"label": "Background Hue Max", "type": "int", "default": 85, "range": (0, 179)},
            "saturation_min": {"label": "Background Saturation Min", "type": "int", "default": 40, "range": (0, 255)},
            "value_min": {"label": "Background Brightness Min", "type": "int", "default": 40, "range": (0, 255)},
            "colour_tolerance": {"label": "Sample Colour Tolerance (Lab)", "type": "int", "default": 25, "range": (0, 100)},
            "morphology_radius": {"label": "Cleanup Radius (px)", "type": "int", "default": 3, "range": (0, 15)},
            "min_area_percent": {"label": "Minimum Contour Area (%)", "type": "float", "default": 0.5, "range": (0, 10)},
            "dilate_px": {"label": "Dilate Radius (px)", "type": "int", "default": 10, "range": (0, 30)},
            "mask_colour": {"label": "Foreground Colour", "type": "colour", "default": "#00BFFF"},
        }
        self._source_image = None
        self._hsv = None
        self._lab_source_image = None
        self._lab = None

    @property
    def metric_label(self) -> str:
        return "OpenCV hue (0-179)"

    def _hsv_image(self, image: Image.Image) -> np.ndarray:
        if image is not self._source_image or self._hsv is None:
            self._hsv = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2HSV)
            self._source_image = image
        return self._hsv

    def metric(self, image: Image.Image) -> np.ndarray:
        return self._hsv_image(image)[:, :, 0]

    def _lab_image(self, image: Image.Image) -> np.ndarray:
        if image is not self._lab_source_image or self._lab is None:
            self._lab = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB)
            self._lab_source_image = image
        return self._lab

    def mask(self, image: Image.Image, *args, **kwargs) -> Image.Image:
        if not self.enabled:
            return Image.new("L", image.size, 0)

        params = self.parameters
        hue_min = int(params["hue_min"]["default"])
        hue_max = int(params["hue_max"]["default"])
        saturation_min = int(params["saturation_min"]["default"])
        value_min = int(params["value_min"]["default"])
        tolerance = int(params["colour_tolerance"]["default"])
        radius = int(params["morphology_radius"]["default"])
        area_percent = float(params["min_area_percent"]["default"])
        dilate_px = int(params["dilate_px"]["default"])
        if not (0 <= hue_min <= 179 and 0 <= hue_max <= 179
                and 0 <= saturation_min <= 255 and 0 <= value_min <= 255
                and 0 <= tolerance <= 100
                and 0 <= radius <= 15 and 0 <= area_percent <= 100
                and 0 <= dilate_px <= 30):
            raise ValueError("Green-screen filter parameters are out of range")

        sampled = params.get("background_rgb", {}).get("default")
        if sampled is not None:
            if (not isinstance(sampled, (tuple, list)) or len(sampled) != 3
                    or any(not isinstance(channel, int) or not 0 <= channel <= 255
                           for channel in sampled)):
                raise ValueError("Sampled background colour must be three RGB bytes")
            sample = np.array([[sampled]], dtype=np.uint8)
            lab_colour = cv2.cvtColor(sample, cv2.COLOR_RGB2LAB)[0, 0].astype(np.int16)
            lower = np.clip(lab_colour - tolerance, 0, 255).astype(np.uint8)
            upper = np.clip(lab_colour + tolerance, 0, 255).astype(np.uint8)
            background = cv2.inRange(self._lab_image(image), lower, upper)
        else:
            hsv = self._hsv_image(image)

            def threshold(low, high):
                return cv2.inRange(hsv, (low, saturation_min, value_min), (high, 255, 255))

            if hue_min <= hue_max:
                background = threshold(hue_min, hue_max)
            else:
                background = cv2.bitwise_or(threshold(hue_min, 179), threshold(0, hue_max))
        foreground = cv2.bitwise_not(background)

        if radius:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
            foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
            foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel)

        height, width = foreground.shape
        contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = width * height * area_percent / 100
        best_contour = None
        best_distance = float("inf")
        for contour in contours:
            if cv2.contourArea(contour) < min_area:
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            x = moments["m10"] / moments["m00"]
            y = moments["m01"] / moments["m00"]
            distance = (x - width / 2) ** 2 + (y - height / 2) ** 2
            if distance < best_distance:
                best_distance = distance
                best_contour = contour

        result = np.zeros((height, width), dtype=np.uint8)
        if best_contour is not None:
            cv2.drawContours(result, [best_contour], -1, 255, cv2.FILLED)
            if dilate_px:
                kernel = cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
                result = cv2.dilate(result, kernel)
        return Image.fromarray(result)
