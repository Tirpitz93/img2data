"""Pixel <-> data coordinate mapping for axis-aligned plots."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

HANDLE_NAMES = ("x1", "x2", "y1", "y2")


class CalibrationError(ValueError):
    pass


@dataclass
class AxisCalibration:
    """Maps one pixel coordinate to a data value using two reference points."""

    p1: float
    p2: float
    v1: float
    v2: float
    log: bool = False

    def validate(self) -> None:
        if self.p1 == self.p2:
            raise CalibrationError("Reference points share the same pixel position")
        if self.v1 == self.v2:
            raise CalibrationError("Reference values must differ")
        if self.log and (self.v1 <= 0 or self.v2 <= 0):
            raise CalibrationError("Log axes need positive reference values")

    def to_data(self, p: float) -> float:
        t = (p - self.p1) / (self.p2 - self.p1)
        if self.log:
            a, b = math.log10(self.v1), math.log10(self.v2)
            return 10 ** (a + t * (b - a))
        return self.v1 + t * (self.v2 - self.v1)

    def to_pixel(self, v: float) -> float:
        if self.log:
            if v <= 0:
                raise CalibrationError("Log axes only accept positive values")
            a, b = math.log10(self.v1), math.log10(self.v2)
            t = (math.log10(v) - a) / (b - a)
        else:
            t = (v - self.v1) / (self.v2 - self.v1)
        return self.p1 + t * (self.p2 - self.p1)


def _default_values() -> dict[str, float]:
    return {"x1": 0.0, "x2": 1.0, "y1": 0.0, "y2": 1.0}


@dataclass
class Calibration:
    """Four draggable reference handles (pixels) plus their data values."""

    handles: dict[str, list[float] | None] = field(
        default_factory=lambda: {n: None for n in HANDLE_NAMES}
    )
    values: dict[str, float] = field(default_factory=_default_values)
    xlog: bool = False
    ylog: bool = False

    def axis(self, which: str) -> AxisCalibration | None:
        a, b = self.handles[which + "1"], self.handles[which + "2"]
        if a is None or b is None:
            return None
        i = 0 if which == "x" else 1
        ax = AxisCalibration(
            a[i], b[i], self.values[which + "1"], self.values[which + "2"],
            self.xlog if which == "x" else self.ylog,
        )
        try:
            ax.validate()
        except CalibrationError:
            return None
        return ax

    @property
    def is_ready(self) -> bool:
        return self.axis("x") is not None and self.axis("y") is not None

    def to_data(self, px: float, py: float) -> tuple[float, float] | None:
        ax, ay = self.axis("x"), self.axis("y")
        if ax is None or ay is None:
            return None
        return ax.to_data(px), ay.to_data(py)

    def to_pixel(self, x: float, y: float) -> tuple[float, float] | None:
        ax, ay = self.axis("x"), self.axis("y")
        if ax is None or ay is None:
            return None
        return ax.to_pixel(x), ay.to_pixel(y)

    def to_dict(self) -> dict:
        return {
            "handles": {k: (list(v) if v else None) for k, v in self.handles.items()},
            "values": dict(self.values),
            "xlog": self.xlog,
            "ylog": self.ylog,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        c = cls()
        for k in HANDLE_NAMES:
            h = d.get("handles", {}).get(k)
            c.handles[k] = [float(h[0]), float(h[1])] if h else None
            c.values[k] = float(d.get("values", {}).get(k, c.values[k]))
        c.xlog = bool(d.get("xlog", False))
        c.ylog = bool(d.get("ylog", False))
        return c
