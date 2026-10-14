"""Document model: image + calibration + series. Points are stored in pixels."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from img2data.calibration import Calibration

log = logging.getLogger(__name__)

PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
           "#42d4f4", "#f032e6", "#bfef45", "#9a6324", "#ffe119"]
MAX_UNDO = 200


@dataclass
class Series:
    name: str
    color: str
    points: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "color": self.color, "points": [list(p) for p in self.points]}

    @classmethod
    def from_dict(cls, d: dict) -> "Series":
        return cls(d["name"], d.get("color", PALETTE[0]),
                   [[float(p[0]), float(p[1])] for p in d.get("points", [])])


class ImageDocument:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.calibration = Calibration()
        self.series: list[Series] = [Series("Series 1", PALETTE[0])]
        self.active = 0
        self.shared_x = False
        self._image: Image.Image | None = None
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def image(self) -> Image.Image:
        if self._image is None:
            log.info("loading image %s", self.path)
            with Image.open(self.path) as im:
                im.load()
                self._image = im.convert("RGBA")
        return self._image

    @property
    def current(self) -> Series:
        return self.series[self.active]

    def add_series(self, name: str | None = None) -> Series:
        n = len(self.series)
        s = Series(name or f"Series {n + 1}", PALETTE[n % len(PALETTE)])
        self.series.append(s)
        self.active = n
        return s

    def remove_series(self, index: int) -> None:
        del self.series[index]
        if not self.series:
            self.series.append(Series("Series 1", PALETTE[0]))
        self.active = min(self.active, len(self.series) - 1)

    def data_for(self, series: Series) -> list[tuple[float, float] | None]:
        return [self.calibration.to_data(px, py) for px, py in series.points]

    # ---- shared x values ------------------------------------------------
    # With shared_x, series 0 defines the x grid: points of later series that sit on one of
    # its x values are locked to it (only y is editable) and follow it when it moves.
    def anchor_index(self, si: int, pi: int) -> int | None:
        """Index of the series-0 point whose x this point is locked to, or None."""
        if not self.shared_x or si == 0:
            return None
        px = self.series[si].points[pi][0]
        for i, p in enumerate(self.series[0].points):
            if p[0] == px:
                return i
        return None

    def x_locked(self, si: int, pi: int) -> bool:
        return self.anchor_index(si, pi) is not None

    def snap_x(self, si: int, px: float, tol: float) -> float:
        """Snap px to the nearest x of another series (series 0 wins ties) within tol."""
        if not self.shared_x:
            return px
        best, best_d = px, tol
        for sj in sorted(range(len(self.series)), key=lambda j: j != 0):
            if sj == si:
                continue
            for p in self.series[sj].points:
                d = abs(p[0] - px)
                if d < best_d:
                    best, best_d = p[0], d
        return best

    def grid_x(self, si: int, px: float) -> float | None:
        """Nearest series-0 x not yet used by series si (None if si is 0 or all are used)."""
        if not self.shared_x or si == 0:
            return None
        used = {p[0] for p in self.series[si].points}
        free = [p[0] for p in self.series[0].points if p[0] not in used]
        return min(free, key=lambda v: abs(v - px)) if free else None

    def move_point(self, si: int, pi: int, x: float, y: float, lock: bool = True) -> None:
        pt = self.series[si].points[pi]
        if self.shared_x:
            if si == 0:
                for s in self.series[1:]:
                    for q in s.points:
                        if q[0] == pt[0]:
                            q[0] = x
            elif lock and self.x_locked(si, pi):
                x = pt[0]
        pt[0], pt[1] = x, y

    def set_point_data(self, si: int, pi: int, x: float, y: float) -> bool:
        pix = self.calibration.to_pixel(x, y)
        if pix is None:
            return False
        self.move_point(si, pi, pix[0], pix[1])
        return True

    # undo/redo operate on snapshots of the editable state
    def snapshot(self) -> dict:
        return copy.deepcopy({
            "calibration": self.calibration.to_dict(),
            "series": [s.to_dict() for s in self.series],
            "active": self.active,
            "shared_x": self.shared_x,
        })

    def _restore(self, snap: dict) -> None:
        self.calibration = Calibration.from_dict(snap["calibration"])
        self.series = [Series.from_dict(s) for s in snap["series"]]
        self.active = min(snap["active"], len(self.series) - 1)
        self.shared_x = bool(snap.get("shared_x", False))

    def push_undo(self) -> None:
        self._undo.append(self.snapshot())
        del self._undo[:-MAX_UNDO]
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        log.debug("undo (%d left)", len(self._undo) - 1)
        self._redo.append(self.snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        log.debug("redo (%d left)", len(self._redo) - 1)
        self._undo.append(self.snapshot())
        self._restore(self._redo.pop())
        return True

    def to_dict(self) -> dict:
        d = self.snapshot()
        d["path"] = str(self.path.resolve())
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ImageDocument":
        doc = cls(d["path"])
        doc._restore(d)
        return doc


def save_project(docs: list[ImageDocument], path: str | Path) -> None:
    log.info("saving project %s (%d documents)", path, len(docs))
    data = {"version": 1, "documents": [d.to_dict() for d in docs]}
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project(path: str | Path) -> list[ImageDocument]:
    log.info("loading project %s", path)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ImageDocument.from_dict(d) for d in data["documents"]]
