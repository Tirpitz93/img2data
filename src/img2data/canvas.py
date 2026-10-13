"""Zoomable/pannable image canvas with draggable calibration handles and series points."""

from __future__ import annotations

import logging
import math
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageTk

from img2data.calibration import HANDLE_NAMES
from img2data.model import ImageDocument

log = logging.getLogger(__name__)

MIN_ZOOM, MAX_ZOOM = 0.02, 64.0
HANDLE_COLORS = {"x": "#ff9800", "y": "#00bcd4"}

Selection = tuple  # ("handle", name) | ("point", series_index, point_index)

MODES = ("pan", "calibrate", "add", "edit")


class PlotCanvas(tk.Canvas):
    HIT_RADIUS = 10

    def __init__(self, master, doc: ImageDocument, *,
                 on_change: Callable[[bool], None] | None = None,
                 on_select: Callable[[], None] | None = None,
                 on_cursor: Callable[[float, float], None] | None = None,
                 on_mode_key: Callable[[str], None] | None = None,
                 step: Callable[[], float] | None = None):
        super().__init__(master, background="#2b2b2b", highlightthickness=0,
                         cursor="crosshair", takefocus=True)
        self.doc = doc
        self.on_change = on_change or (lambda live: None)
        self.on_select = on_select or (lambda: None)
        self.on_cursor = on_cursor or (lambda x, y: None)
        self.on_mode_key = on_mode_key or (lambda m: None)
        self.step = step or (lambda: 1.0)
        self.mode = "add"
        self.sel: Selection | None = None
        self.pending: str | None = None  # calibration handle awaiting placement
        self.scale = 1.0
        self.ox = self.oy = 0.0
        self._photo: ImageTk.PhotoImage | None = None
        self._user_zoomed = False
        self._drag: dict | None = None
        self._pan: tuple[float, float, float, float] | None = None

        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        for b in (2, 3):
            self.bind(f"<ButtonPress-{b}>", self._pan_start)
            self.bind(f"<B{b}-Motion>", self._pan_move)
        self.bind("<Motion>", self._hover)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self.zoom_by(1.25, e.x, e.y))
        self.bind("<Button-5>", lambda e: self.zoom_by(0.8, e.x, e.y))
        self.bind("<Key>", self._key)
        self.bind("<Tab>", lambda e: self.step_selection(1))
        self.bind("<Shift-Tab>", lambda e: self.step_selection(-1))
        self.bind("<ISO_Left_Tab>", lambda e: self.step_selection(-1))

    # ---- coordinates -------------------------------------------------
    def to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale

    def to_image(self, cx: float, cy: float) -> tuple[float, float]:
        return (cx - self.ox) / self.scale, (cy - self.oy) / self.scale

    # ---- view --------------------------------------------------------
    def fit(self) -> None:
        w, h = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        iw, ih = self.doc.image.size
        self.scale = min(min(w / iw, h / ih) * 0.97, 4.0)
        self.ox = (w - iw * self.scale) / 2
        self.oy = (h - ih * self.scale) / 2
        self._user_zoomed = False
        self.redraw()

    def zoom_by(self, factor: float, cx: float | None = None, cy: float | None = None) -> None:
        if cx is None:
            cx, cy = self.winfo_width() / 2, self.winfo_height() / 2
        new = min(max(self.scale * factor, MIN_ZOOM), MAX_ZOOM)
        k = new / self.scale
        self.ox = cx - (cx - self.ox) * k
        self.oy = cy - (cy - self.oy) * k
        self.scale = new
        log.debug("zoom %.3f", new)
        self._user_zoomed = True
        self.redraw()

    def set_zoom(self, value: float) -> None:
        self.zoom_by(value / self.scale)

    def center_on(self, x: float, y: float) -> None:
        self.ox = self.winfo_width() / 2 - x * self.scale
        self.oy = self.winfo_height() / 2 - y * self.scale
        self._user_zoomed = True
        self.redraw()

    def _on_configure(self, _e) -> None:
        if self._user_zoomed:
            self.redraw()
        else:
            self.fit()

    # ---- drawing -----------------------------------------------------
    def redraw(self) -> None:
        self.delete("img")
        img = self.doc.image
        W, H = img.size
        cw, ch, s = self.winfo_width(), self.winfo_height(), self.scale
        l, t = max(0.0, -self.ox / s), max(0.0, -self.oy / s)
        r, b = min(float(W), (cw - self.ox) / s), min(float(H), (ch - self.oy) / s)
        if r - l > 0.5 / s and b - t > 0.5 / s:
            size = (max(1, round((r - l) * s)), max(1, round((b - t) * s)))
            resample = Image.NEAREST if s >= 2 else Image.BILINEAR
            crop = img.resize(size, resample, box=(l, t, r, b))
            self._photo = ImageTk.PhotoImage(crop)
            self.create_image(self.ox + l * s, self.oy + t * s, anchor="nw",
                              image=self._photo, tags="img")
            self.tag_lower("img")
        self.draw_overlay()

    def draw_overlay(self) -> None:
        self.delete("ov")
        cw, ch = self.winfo_width(), self.winfo_height()
        cal = self.doc.calibration
        for name in HANDLE_NAMES:
            h = cal.handles[name]
            if h is None:
                continue
            axis = name[0]
            col = HANDLE_COLORS[axis]
            cx, cy = self.to_canvas(*h)
            if axis == "x":
                self.create_line(cx, 0, cx, ch, fill=col, dash=(4, 4), tags="ov")
            else:
                self.create_line(0, cy, cw, cy, fill=col, dash=(4, 4), tags="ov")
            selected = self.sel == ("handle", name)
            r = 8 if selected else 6
            self.create_polygon(cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy,
                                outline="white" if selected else "black", fill=col, tags="ov")
            val = cal.values[name]
            self.create_text(cx + 10, cy - 10, text=f"{name.upper()}={val:g}", fill=col,
                             anchor="sw", font=("Segoe UI", 9, "bold"), tags="ov")
        for si, series in enumerate(self.doc.series):
            active = si == self.doc.active
            r = 4 if active else 3
            for pi, (px, py) in enumerate(series.points):
                cx, cy = self.to_canvas(px, py)
                if -20 < cx < cw + 20 and -20 < cy < ch + 20:
                    self.create_oval(cx - r, cy - r, cx + r, cy + r, outline="black",
                                     fill=series.color if active else "", width=1 if active else 2,
                                     tags="ov")
                    if not active:
                        self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=series.color,
                                         tags="ov")
                    if self.sel == ("point", si, pi):
                        self.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, outline="white",
                                         width=2, tags="ov")
                        self.create_line(cx - 14, cy, cx + 14, cy, fill="white", tags="ov")
                        self.create_line(cx, cy - 14, cx, cy + 14, fill="white", tags="ov")

    # ---- selection / editing ------------------------------------------
    def select(self, sel: Selection | None) -> None:
        log.debug("select %s", sel)
        self.sel = sel
        if sel and sel[0] == "point":
            self.doc.active = sel[1]
        self.draw_overlay()
        self.on_select()
        pos = self.position(sel)
        if pos:
            self.on_cursor(*pos)

    def position(self, sel: Selection | None) -> tuple[float, float] | None:
        if sel is None:
            return None
        if sel[0] == "handle":
            h = self.doc.calibration.handles[sel[1]]
            return tuple(h) if h else None
        try:
            return tuple(self.doc.series[sel[1]].points[sel[2]])
        except IndexError:
            return None

    def _set_position(self, sel: Selection, x: float, y: float) -> None:
        if sel[0] == "handle":
            self.doc.calibration.handles[sel[1]] = [x, y]
        else:
            self.doc.series[sel[1]].points[sel[2]] = [x, y]

    def hit_test(self, cx: float, cy: float) -> Selection | None:
        best, best_d = None, self.HIT_RADIUS
        for name in HANDLE_NAMES:
            h = self.doc.calibration.handles[name]
            if h:
                d = math.hypot(self.to_canvas(*h)[0] - cx, self.to_canvas(*h)[1] - cy)
                if d <= best_d:
                    best, best_d = ("handle", name), d
        for si, series in enumerate(self.doc.series):
            for pi, (px, py) in enumerate(series.points):
                x, y = self.to_canvas(px, py)
                d = math.hypot(x - cx, y - cy)
                # ties prefer the active series / later points
                if d < best_d or (d == best_d and si == self.doc.active):
                    best, best_d = ("point", si, pi), d
        return best

    def delete_selected(self) -> None:
        if self.sel and self.sel[0] == "point":
            log.info("delete point %s", self.sel)
            self.doc.push_undo()
            del self.doc.series[self.sel[1]].points[self.sel[2]]
            self.sel = None
            self.draw_overlay()
            self.on_select()
            self.on_change(False)

    def nudge(self, dx: float, dy: float) -> None:
        pos = self.position(self.sel)
        if pos is None:
            return
        log.debug("nudge %s by (%g, %g)", self.sel, dx, dy)
        self.doc.push_undo()
        self._set_position(self.sel, pos[0] + dx, pos[1] + dy)
        self.draw_overlay()
        self.on_cursor(pos[0] + dx, pos[1] + dy)
        self.on_change(False)

    def step_selection(self, delta: int) -> str:
        """Select the next/previous point in the current series (wrapping). Returns "break"
        so Tk does not move keyboard focus away from the canvas."""
        si = self.sel[1] if self.sel and self.sel[0] == "point" else self.doc.active
        n = len(self.doc.series[si].points)
        if n:
            if self.sel and self.sel[0] == "point":
                pi = (self.sel[2] + delta) % n
            else:
                pi = 0 if delta > 0 else n - 1
            self.select(("point", si, pi))
            x, y = self.doc.series[si].points[pi]
            cx, cy = self.to_canvas(x, y)
            if not (20 < cx < self.winfo_width() - 20 and 20 < cy < self.winfo_height() - 20):
                self.center_on(x, y)
        return "break"

    def next_missing_handle(self) -> str | None:
        for n in HANDLE_NAMES:
            if self.doc.calibration.handles[n] is None:
                return n
        return None

    # ---- mouse ---------------------------------------------------------
    def _press(self, e) -> None:
        self.focus_set()
        log.debug("press mode=%s at canvas (%d, %d)", self.mode, e.x, e.y)
        if self.mode == "pan":
            self._pan_start(e)
            return
        hit = self.hit_test(e.x, e.y)
        if (self.mode == "calibrate" and hit and hit[0] == "handle"
                and (self.pending or (e.state & 0x1 and self.next_missing_handle()))):
            hit = None  # explicit placement wins over grabbing an existing handle
        x, y = self.to_image(e.x, e.y)
        if hit is None:
            if self.mode == "calibrate":
                name = self.pending or self.next_missing_handle()
                if name is None:
                    return
                self.doc.push_undo()
                self.doc.calibration.handles[name] = [x, y]
                log.info("placed handle %s at (%.2f, %.2f)", name, x, y)
                self.pending = self.next_missing_handle()
                hit = ("handle", name)
            elif self.mode == "add":
                self.doc.push_undo()
                s = self.doc.current
                s.points.append([x, y])
                log.info("added point to '%s' at (%.2f, %.2f)", s.name, x, y)
                hit = ("point", self.doc.active, len(s.points) - 1)
            else:
                self.select(None)
                return
            self._drag = {"origin": (x, y), "start": (x, y), "undone": True}
            self.on_change(False)
        else:
            self._drag = {"origin": self.position(hit), "start": (x, y), "undone": False}
        self.select(hit)

    def _motion(self, e) -> None:
        if self._pan:
            self._pan_move(e)
            return
        if not self._drag or self.sel is None:
            return
        if not self._drag["undone"]:
            self.doc.push_undo()
            self._drag["undone"] = True
        x, y = self.to_image(e.x, e.y)
        ox, oy = self._drag["origin"]
        sx, sy = self._drag["start"]
        nx, ny = ox + (x - sx), oy + (y - sy)
        if e.state & 0x4:  # Ctrl locks to the dominant axis
            if abs(nx - ox) >= abs(ny - oy):
                ny = oy
            else:
                nx = ox
        self._set_position(self.sel, nx, ny)
        self.draw_overlay()
        self.on_cursor(nx, ny)
        self.on_change(True)

    def _release(self, _e) -> None:
        self._pan = None
        if self._drag:
            self._drag = None
            self.on_change(False)

    def _hover(self, e) -> None:
        x, y = self.to_image(e.x, e.y)
        self.on_cursor(x, y)

    def _wheel(self, e) -> None:
        self.zoom_by(1.2 if e.delta > 0 else 1 / 1.2, e.x, e.y)

    def _pan_start(self, e) -> None:
        self._pan = (e.x, e.y, self.ox, self.oy)

    def _pan_move(self, e) -> None:
        if self._pan:
            x0, y0, ox, oy = self._pan
            self.ox, self.oy = ox + e.x - x0, oy + e.y - y0
            self._user_zoomed = True
            self.redraw()

    # ---- keyboard --------------------------------------------------------
    def _key(self, e) -> None:
        arrows = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}
        if e.keysym in arrows:
            k = self.step() * (10 if e.state & 0x1 else 0.1 if e.state & 0x4 else 1)
            dx, dy = arrows[e.keysym]
            self.nudge(dx * k, dy * k)
        elif e.keysym in ("Delete", "BackSpace"):
            self.delete_selected()
        elif e.keysym == "Escape":
            self.pending = None
            self.select(None)
        elif e.keysym in ("plus", "equal", "KP_Add"):
            self.zoom_by(1.25)
        elif e.keysym in ("minus", "KP_Subtract"):
            self.zoom_by(0.8)
        elif e.keysym.lower() == "f":
            self.fit()
        elif e.char in ("1", "2", "3", "4"):
            self.on_mode_key(MODES[int(e.char) - 1])


class Loupe(tk.Label):
    """Magnifier showing the pixels around a point with the overlay and a crosshair."""

    RADIUS = 12  # source pixels each side of centre
    SIZE = 175

    def __init__(self, master):
        super().__init__(master, width=self.SIZE, height=self.SIZE, borderwidth=1, relief="solid")
        self._photo: ImageTk.PhotoImage | None = None

    def clear(self) -> None:
        self.configure(image="")
        self._photo = None

    def show(self, doc: ImageDocument, x: float, y: float) -> None:
        r = self.RADIUS
        x0, y0 = math.floor(x) - r, math.floor(y) - r
        n = 2 * r + 1
        m = self.SIZE / n
        crop = doc.image.crop((x0, y0, x0 + n, y0 + n)).resize((self.SIZE, self.SIZE),
                                                                Image.NEAREST).convert("RGB")
        d = ImageDraw.Draw(crop)

        def to_loupe(px: float, py: float) -> tuple[float, float]:
            return (px - x0) * m, (py - y0) * m

        for name in HANDLE_NAMES:
            h = doc.calibration.handles[name]
            if h:
                lx, ly = to_loupe(*h)
                d.polygon([(lx, ly - 7), (lx + 7, ly), (lx, ly + 7), (lx - 7, ly)],
                          outline="black", fill=HANDLE_COLORS[name[0]])
        for s in doc.series:
            for px, py in s.points:
                lx, ly = to_loupe(px, py)
                d.ellipse([lx - 5, ly - 5, lx + 5, ly + 5], outline=s.color, width=2)
        cx, cy = to_loupe(x, y)
        d.line([(cx, 0), (cx, self.SIZE)], fill="#ff00ff")
        d.line([(0, cy), (self.SIZE, cy)], fill="#ff00ff")
        self._photo = ImageTk.PhotoImage(crop)
        self.configure(image=self._photo)
