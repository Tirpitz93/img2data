from PIL import Image, ImageColor

import numpy as np


class FilterBase:
    histogram_threshold = None
    histogram_image_only = False

    def __init__(self):
        # self.image_pil = self.load_image(self.image_path)
        self.parameters = {}
        self._histogram_source = None
        self._histogram_cache = None
        # self.enabled = True  # Default to enabled, can be overridden by subclasses

    @property
    def enabled(self):
        return self.parameters.get("enabled", {}).get("default", True)

    @property
    def overlay_colour(self) -> str:
        for parameter in self.parameters.values():
            if parameter.get("type") == "colour":
                return parameter.get("default", "#FF0000")
        return self.parameters.get("mask_colour", {}).get("default", "#FF0000")

    def paint_overlays(self, canvas, *args, **kwargs):
        """
        Paint the filters output onto the current canvas. This is a placeholder method that should be overridden by subclasses to implement specific filter overlays.
        for example
        :param canvas:
        :param colour:
        :return:
        """

        pass

    def get_parameters(self) -> dict[str, dict]:
        """
        Get the parameters for the filter. This is a placeholder method that should be overridden by subclasses to implement specific filter parameters.
        this will be called by the filters control class to great the control widgets, expose all user adjustable parameters for the filter here.
        :return:
        """
        return self.parameters

    def set_parameters(self, params: dict):
        """
        Set the parameters for the filter. This is a placeholder method that should be overridden by subclasses to implement specific filter parameters.
        this will be called by the filters control class to set the parameters from the control widgets, expose all user adjustable parameters for the filter here.
        :param params:
        :return:
        """
        for name, value in params.items():
            self.parameters[name] = {**self.parameters.get(name, {}), **value}

    def mask(self, image: Image.Image, *args, **kwargs) -> Image.Image:
        """
        return a single channel single bit mask image of the filter output, this will be used to overlay the filter output on the image in the canvas.

        active pixels are white, inactive pixels are black, the mask will be resized to the canvas size before being overlayed on the image.

        for example
        :param canvas:
        :param colour:
        :return:
        """
        raise NotImplementedError(f"{self.__class__.__name__}.mask() must be implemented")

    def metric(self, image: Image.Image):
        """Return the per-pixel values used to build this filter's mask."""
        raise NotImplementedError(f"{self.__class__.__name__}.metric() must be implemented")

    def histogram(self, image: Image.Image, bins: int = 32) -> tuple[int, ...]:
        """Count pixels in evenly spaced bins across the filter's 0-255 metric."""
        counts, _ = np.histogram(self.metric(image), bins=bins, range=(0, 256))
        return tuple(int(count) for count in counts)

    def preview_histogram(self, image: Image.Image) -> tuple[int, ...]:
        if not self.histogram_image_only:
            return self.histogram(image)
        if self._histogram_source is not image or self._histogram_cache is None:
            self._histogram_cache = self.histogram(image)
            self._histogram_source = image
        return self._histogram_cache

    @property
    def metric_label(self) -> str:
        return "Metric (0-255)"

    def overlay(self, image: Image.Image, mask: Image.Image, opacity: int = 128) -> Image.Image:
        """Return the image with the filter's mask blended over matching pixels."""
        base = image.convert("RGBA")
        return Image.alpha_composite(base, self.overlay_layer(mask, base.size, opacity))

    def overlay_layer(self, mask: Image.Image, size: tuple[int, int],
                      opacity: int = 128) -> Image.Image:
        """Return a transparent, coloured layer for the matching mask pixels."""
        mask = mask.convert("L")
        if mask.size != size:
            mask = mask.resize(size, Image.Resampling.NEAREST)
        alpha = mask.point(lambda value: value * opacity // 255)
        layer = Image.new("RGBA", size, ImageColor.getrgb(self.overlay_colour) + (0,))
        layer.putalpha(alpha)
        return layer

    @property
    def stats(self) -> dict:
        """
        return a dictionary of statistics about the filter output, this will be used to display the filter output in the filters table.
        for example: % area of image that matches the filter
        distribution of filter values across the image
        :return:
        """
        pass
