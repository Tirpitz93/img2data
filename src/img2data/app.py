"""Main ttkbootstrap application window."""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog

import ttkbootstrap as ttk
from PIL import ImageGrab
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, YES
from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD

import logging

from img2data import dropping
from img2data.logging_setup import build_parser, resolve_level, setup_logging
from img2data.calibration import HANDLE_NAMES
from img2data.canvas import MODES, Loupe, PlotCanvas
from img2data.export import FILETYPES, build_frame, to_clipboard_text, write_frame
from img2data.model import ImageDocument, load_project, save_project

MODE_LABELS = {"pan": "Pan (1)", "calibrate": "Calibrate (2)", "add": "Add points (3)",
               "edit": "Select/Edit (4)"}
MODE_HINTS = {
    "pan": "Drag to pan. Mouse wheel zooms. Right/middle-drag always pans.",
    "calibrate": "Click to place the next reference handle (Shift-click or a Set button forces placement over an existing handle); drag handles to adjust.",
    "add": "Click to add a point to the active series; click-drag existing points to move them.",
    "edit": "Click to select, drag to move. Arrows nudge (Shift = x10, Ctrl = x0.1). Del removes.",
}


log = logging.getLogger(__name__)


def fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:.6g}"


class ValueDialog(tk.Toplevel):
    """Modal dialog editing two numbers."""

    def __init__(self, parent, title: str, labels: tuple[str, str], values: tuple[float, float]):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result: tuple[float, float] | None = None
        self.vars = [tk.StringVar(value=f"{v:.10g}") for v in values]
        body = ttk.Frame(self, padding=12)
        body.pack(fill=BOTH, expand=YES)
        entries = []
        for i, (lab, var) in enumerate(zip(labels, self.vars)):
            ttk.Label(body, text=lab).grid(row=i, column=0, sticky="w", pady=3)
            e = ttk.Entry(body, textvariable=var, width=22)
            e.grid(row=i, column=1, padx=(8, 0))
            e.bind("<Return>", lambda _e: self._ok())
            entries.append(e)
        btns = ttk.Frame(body)
        btns.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(btns, text="OK", command=self._ok).pack(side=LEFT, padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy, bootstyle="secondary").pack(side=LEFT)
        self.bind("<Escape>", lambda _e: self.destroy())
        entries[0].focus_set()
        entries[0].select_range(0, tk.END)
        self.grab_set()
        self.wait_window()

    def _ok(self) -> None:
        try:
            self.result = (float(self.vars[0].get()), float(self.vars[1].get()))
        except ValueError:
            messagebox.showerror("Invalid value", "Please enter numbers.", parent=self)
            return
        self.destroy()


class DocTab(ttk.Frame):
    def __init__(self, master, doc: ImageDocument, app: "App"):
        super().__init__(master)
        self.doc = doc
        self.canvas = PlotCanvas(self, doc, on_change=app.on_change, on_select=app.on_select,
                                 on_cursor=app.on_cursor, on_mode_key=app.set_mode,
                                 step=app.get_step)
        self.canvas.pack(fill=BOTH, expand=YES)


class App:
    def __init__(self):
        self.root = ttk.Window(title="img2data", themename="bootstrap-light", size=(1400, 880))
        self.root.minsize(900, 600)
        TkinterDnD._require(self.root)
        self.mode_var = tk.StringVar(value="calibrate")
        self.step_var = tk.DoubleVar(value=1.0)
        self.wide_var = tk.BooleanVar(value=False)
        self.pixels_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar()
        self.hint_var = tk.StringVar()
        self.series_var = tk.StringVar()
        self.val_vars = {n: tk.StringVar() for n in HANDLE_NAMES}
        self.px_vars = {n: tk.StringVar(value="not set") for n in HANDLE_NAMES}
        self.log_vars = {"x": tk.BooleanVar(), "y": tk.BooleanVar()}
        self._syncing = False
        self._last_cursor: tuple[float, float] | None = None

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(8, 2)
                  ).pack(side="bottom", fill=X)
        ttk.Label(self.root, textvariable=self.hint_var, anchor="w", padding=(8, 2),
                  bootstyle="secondary").pack(side="bottom", fill=X)
        self._bind_keys()
        self.set_mode("calibrate")
        self._update_placeholder()

    # ------------------------------------------------------------------ UI
    def _build_menu(self) -> None:
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="Open images…", accelerator="Ctrl+O", command=self.open_dialog)
        f.add_command(label="Paste image", accelerator="Ctrl+V", command=self.paste_image)
        f.add_separator()
        f.add_command(label="Open project…", command=self.open_project)
        f.add_command(label="Save project…", accelerator="Ctrl+S", command=self.save_project)
        f.add_separator()
        f.add_command(label="Export current tab…", accelerator="Ctrl+E",
                      command=lambda: self.export(False))
        f.add_command(label="Export all tabs…", command=lambda: self.export(True))
        f.add_command(label="Copy data to clipboard", command=self.copy_data)
        f.add_command(label="View data table", command=self.show_table)
        f.add_separator()
        f.add_checkbutton(label="Export wide format (one column pair per series)",
                          variable=self.wide_var)
        f.add_checkbutton(label="Export pixel coordinates", variable=self.pixels_var)
        f.add_separator()
        f.add_command(label="Close tab", accelerator="Ctrl+W", command=self.close_tab)
        f.add_command(label="Exit", command=self.root.destroy)
        m.add_cascade(label="File", menu=f)
        e = tk.Menu(m, tearoff=False)
        e.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        e.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        e.add_command(label="Delete selected point", accelerator="Del",
                      command=lambda: self.tab and self.tab.canvas.delete_selected())
        m.add_cascade(label="Edit", menu=e)
        v = tk.Menu(m, tearoff=False)
        v.add_command(label="Fit to window", accelerator="F", command=lambda: self._view("fit"))
        v.add_command(label="Zoom 100%", command=lambda: self._view("100"))
        v.add_command(label="Zoom in", accelerator="+", command=lambda: self._view("in"))
        v.add_command(label="Zoom out", accelerator="-", command=lambda: self._view("out"))
        v.add_separator()
        t = tk.Menu(v, tearoff=False)
        for name in ("bootstrap-light", "bootstrap-dark", "nord-light", "nord-dark", "solarized-light", "solarized-dark", "dracula-dark"):
            t.add_command(label=name, command=lambda n=name: self.root.style.theme_use(n))
        v.add_cascade(label="Theme", menu=t)
        m.add_cascade(label="View", menu=v)
        self.root.config(menu=m)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(6, 4))
        bar.pack(fill=X)
        for mode in MODES:
            ttk.Radiobutton(bar, text=MODE_LABELS[mode], value=mode, variable=self.mode_var,
                            bootstyle="outline-toolbutton",
                            command=lambda: self.set_mode(self.mode_var.get())
                            ).pack(side=LEFT, padx=2)
        ttk.Separator(bar, orient="vertical").pack(side=LEFT, fill=Y, padx=8)
        for text, cmd in (("Fit", "fit"), ("100%", "100"), ("＋", "in"), ("－", "out")):
            ttk.Button(bar, text=text, width=5, bootstyle="secondary-outline",
                       command=lambda c=cmd: self._view(c)).pack(side=LEFT, padx=2)
        ttk.Separator(bar, orient="vertical").pack(side=LEFT, fill=Y, padx=8)
        ttk.Button(bar, text="Undo", bootstyle="secondary-outline", command=self.undo
                   ).pack(side=LEFT, padx=2)
        ttk.Button(bar, text="Redo", bootstyle="secondary-outline", command=self.redo
                   ).pack(side=LEFT, padx=2)
        ttk.Button(bar, text="Export…", command=lambda: self.export(False)
                   ).pack(side=RIGHT, padx=2)
        ttk.Button(bar, text="Open…", bootstyle="success", command=self.open_dialog
                   ).pack(side=RIGHT, padx=2)

    def _build_body(self) -> None:
        paned = ttk.Panedwindow(self.root, orient="horizontal")
        paned.pack(fill=BOTH, expand=YES)
        left = ttk.Frame(paned, width=900, height=600)
        left.pack_propagate(False)  # keep the default size instead of shrinking to the notebook
        self.nb = ttk.Notebook(left)
        self.nb.pack(fill=BOTH, expand=YES)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_changed())
        self.nb.bind("<Button-2>", self._middle_close)
        self.placeholder = ttk.Label(
            left, text="Drop images here (from Explorer or a browser)\n"
                       "or use File → Open images… / Ctrl+V to paste",
            justify="center", font=("Segoe UI", 13), bootstyle="secondary")
        paned.add(left, weight=1)

        side = ttk.Frame(paned, padding=6, width=360)
        self._build_side(side)
        paned.add(side, weight=0)

        for w in (left, self.nb, self.placeholder):
            self._register_drop(w)

        self.paned = paned
        self.root.update_idletasks()
        self._set_sash()
        self.root.bind("<Map>", lambda _e: self._set_sash(), add="+")

    def _set_sash(self) -> None:
        """Give the side panel a fixed width so the image area gets the rest at startup."""
        if getattr(self, "_sash_done", False):
            return
        total = self.paned.winfo_width()
        if total > 400:
            self.paned.sashpos(0, total - 380)
            self._sash_done = True

    def _build_side(self, side: ttk.Frame) -> None:
        cal = ttk.Labelframe(side, text="Axis calibration", padding=6)
        cal.pack(fill=X)
        ttk.Label(cal, text="Reference").grid(row=0, column=0)
        ttk.Label(cal, text="Value").grid(row=0, column=1)
        ttk.Label(cal, text="Pixel position").grid(row=0, column=2)
        for r, name in enumerate(HANDLE_NAMES, start=1):
            ttk.Button(cal, text=f"Set {name.upper()}", width=7, bootstyle="warning-outline" if
                       name[0] == "x" else "info-outline",
                       command=lambda n=name: self.set_pending(n)).grid(row=r, column=0, pady=2)
            e = ttk.Entry(cal, textvariable=self.val_vars[name], width=11)
            e.grid(row=r, column=1, padx=4)
            e.bind("<Return>", lambda _e, n=name: self.apply_value(n))
            e.bind("<FocusOut>", lambda _e, n=name: self.apply_value(n))
            ttk.Label(cal, textvariable=self.px_vars[name]).grid(row=r, column=2, sticky="w")
        logs = ttk.Frame(cal)
        logs.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        for ax in ("x", "y"):
            ttk.Checkbutton(logs, text=f"{ax.upper()} log scale", variable=self.log_vars[ax],
                            command=self.apply_log).pack(side=LEFT, padx=(0, 10))
        ttk.Button(logs, text="Clear", bootstyle="danger-outline", width=6,
                   command=self.clear_calibration).pack(side=LEFT)

        ser = ttk.Labelframe(side, text="Series", padding=6)
        ser.pack(fill=X, pady=6)
        self.series_combo = ttk.Combobox(ser, textvariable=self.series_var, state="readonly")
        self.series_combo.pack(fill=X)
        self.series_combo.bind("<<ComboboxSelected>>", self._on_series_chosen)
        row = ttk.Frame(ser)
        row.pack(fill=X, pady=(4, 0))
        for text, cmd in (("New", self.new_series), ("Rename", self.rename_series),
                          ("Colour", self.pick_color), ("Delete", self.delete_series)):
            ttk.Button(row, text=text, bootstyle="secondary-outline", command=cmd
                       ).pack(side=LEFT, expand=YES, fill=X, padx=1)

        pts = ttk.Labelframe(side, text="Points (active series)", padding=6)
        pts.pack(fill=BOTH, expand=YES)
        cols = ("n", "x", "y", "px", "py")
        self.tree = ttk.Treeview(pts, columns=cols, show="headings", height=6,
                                 selectmode="browse")
        for c, w in zip(cols, (32, 76, 76, 58, 58)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="e", stretch=c != "n")
        sb = ttk.Scrollbar(pts, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self.tree.pack(fill=BOTH, expand=YES)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _e: self.edit_point())
        self.tree.bind("<Delete>", lambda _e: self.tab and self.tab.canvas.delete_selected())

        fine = ttk.Labelframe(side, text="Fine adjustment", padding=6)
        fine.pack(fill=X, pady=(6, 0))
        top = ttk.Frame(fine)
        top.pack(fill=X)
        pad = ttk.Frame(top)
        pad.pack(side=LEFT)
        for text, r, c, d in (("▲", 0, 1, (0, -1)), ("◀", 1, 0, (-1, 0)), ("▶", 1, 2, (1, 0)),
                              ("▼", 2, 1, (0, 1))):
            ttk.Button(pad, text=text, width=3, bootstyle="secondary",
                       command=lambda d=d: self.nudge_step(*d)).grid(row=r, column=c, padx=1, pady=1)
        opts = ttk.Frame(top)
        opts.pack(side=LEFT, padx=10)
        ttk.Label(opts, text="Step (image px)").pack(anchor="w")
        ttk.Spinbox(opts, from_=0.01, to=100, increment=0.1, textvariable=self.step_var,
                    width=7).pack(anchor="w")
        ttk.Button(opts, text="Edit value…", bootstyle="secondary-outline",
                   command=self.edit_point).pack(anchor="w", pady=(4, 0), fill=X)
        ttk.Button(opts, text="Zoom to point", bootstyle="secondary-outline",
                   command=self.zoom_to_selection).pack(anchor="w", pady=(2, 0), fill=X)
        self.loupe = Loupe(fine)
        self.loupe.pack(pady=(6, 0))

    def _bind_keys(self) -> None:
        r = self.root
        for seq, fn in (("<Control-o>", self.open_dialog), ("<Control-s>", self.save_project),
                        ("<Control-w>", self.close_tab), ("<Control-z>", self.undo),
                        ("<Control-y>", self.redo), ("<Control-e>", lambda: self.export(False)),
                        ("<Control-v>", self._paste_key)):
            r.bind_all(seq, lambda _e, fn=fn: fn())

    # ----------------------------------------------------------- drag & drop
    def _register_drop(self, widget) -> None:
        try:
            widget.drop_target_register(DND_FILES, DND_TEXT, "CF_HTML")
        except tk.TclError:
            widget.drop_target_register(DND_FILES, DND_TEXT)
        widget.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        self.open_sources(dropping.extract_sources(event.data, self.root.tk.splitlist))
        return event.action

    def open_sources(self, sources: list[str]) -> None:
        errors, opened = [], 0
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            for src in sources:
                try:
                    for p in dropping.resolve_source(src):
                        self.add_doc(ImageDocument(p))
                        opened += 1
                except Exception as exc:  # noqa: BLE001 - report every failing source
                    log.exception("failed to open source %.120s", src)
                    errors.append(f"{src[:80]}: {exc}")
        finally:
            self.root.config(cursor="")
        if errors:
            messagebox.showerror("Could not open", "\n".join(errors[:8]))
        elif not opened and sources:
            messagebox.showinfo("Nothing opened", "No images found in the dropped data.")

    # ----------------------------------------------------------------- tabs
    @property
    def tab(self) -> DocTab | None:
        sel = self.nb.select()
        return self.root.nametowidget(sel) if sel else None

    @property
    def tabs(self) -> list[DocTab]:
        return [self.root.nametowidget(t) for t in self.nb.tabs()]

    def add_doc(self, doc: ImageDocument) -> DocTab:
        doc.image  # fail early on unreadable files
        log.info("opened tab for %s (%dx%d)", doc.path, *doc.image.size)
        tab = DocTab(self.nb, doc, self)
        tab.canvas.mode = self.mode_var.get()
        self._register_drop(tab.canvas)
        self.nb.add(tab, text=doc.name)
        self.nb.select(tab)
        self._update_placeholder()
        return tab

    def close_tab(self) -> None:
        tab = self.tab
        if tab:
            log.info("closing tab %s", tab.doc.name)
            self.nb.forget(tab)
            tab.destroy()
            self._update_placeholder()
            self._on_tab_changed()

    def _middle_close(self, e) -> None:
        try:
            idx = self.nb.index(f"@{e.x},{e.y}")
        except tk.TclError:
            return
        self.nb.select(idx)
        self.close_tab()

    def _update_placeholder(self) -> None:
        if self.nb.tabs():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _on_tab_changed(self) -> None:
        self.loupe.clear()
        self.refresh_panel()
        tab = self.tab
        if tab:
            tab.canvas.focus_set()

    # --------------------------------------------------------------- actions
    def open_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Open images",
            filetypes=[("Images", " ".join(f"*{e}" for e in sorted(dropping.IMAGE_EXTS))),
                       ("All files", "*.*")])
        self.open_sources([str(p) for p in paths])

    def _paste_key(self) -> None:
        try:
            focus = self.root.focus_get()
        except KeyError:  # tkinter cannot name combobox popdown windows
            focus = None
        if isinstance(focus, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            return
        self.paste_image()

    def paste_image(self) -> None:
        try:
            clip = ImageGrab.grabclipboard()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Paste failed", str(exc))
            return
        if clip is None:
            try:
                text = self.root.clipboard_get()
            except tk.TclError:
                text = ""
            srcs = dropping.extract_sources(text, self.root.tk.splitlist)
            if srcs:
                self.open_sources(srcs)
            else:
                messagebox.showinfo("Paste", "The clipboard holds no image.")
        elif isinstance(clip, list):
            self.open_sources([str(p) for p in clip])
        else:
            path = dropping.CACHE_DIR / f"clipboard_{time.strftime('%Y%m%d_%H%M%S')}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            clip.save(path)
            self.open_sources([str(path)])

    def open_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("img2data project", "*.i2d.json *.json")])
        if not path:
            return
        try:
            for doc in load_project(path):
                self.add_doc(doc)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open project", str(exc))

    def save_project(self) -> None:
        if not self.tabs:
            return
        path = filedialog.asksaveasfilename(defaultextension=".i2d.json",
                                            filetypes=[("img2data project", "*.i2d.json")])
        if path:
            save_project([t.doc for t in self.tabs], path)

    def _docs_for_export(self, all_tabs: bool) -> list[ImageDocument]:
        if all_tabs:
            return [t.doc for t in self.tabs]
        return [self.tab.doc] if self.tab else []

    def export(self, all_tabs: bool) -> None:
        docs = self._docs_for_export(all_tabs)
        if not docs:
            return
        df = build_frame(docs, self.wide_var.get(), self.pixels_var.get())
        stem = docs[0].path.stem if len(docs) == 1 else "img2data"
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=FILETYPES,
                                            initialfile=f"{stem}_data")
        if not path:
            return
        try:
            write_frame(df, path)
        except Exception as exc:  # noqa: BLE001
            log.exception("export failed")
            messagebox.showerror("Export failed", str(exc))
        else:
            self.status_var.set(f"Exported {len(df)} rows to {path}")

    def copy_data(self) -> None:
        docs = self._docs_for_export(False)
        if docs:
            df = build_frame(docs, self.wide_var.get(), self.pixels_var.get())
            self.root.clipboard_clear()
            self.root.clipboard_append(to_clipboard_text(df))
            self.status_var.set(f"Copied {len(df)} rows to the clipboard")

    def show_table(self) -> None:
        docs = self._docs_for_export(True)
        if not docs:
            return
        df = build_frame(docs, self.wide_var.get(), self.pixels_var.get())
        win = ttk.Toplevel(title="Data table", size=(700, 450))
        cols = list(df.columns)
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=str(c))
            tv.column(c, width=100, anchor="e")
        for row in df.itertuples(index=False):
            tv.insert("", "end", values=["" if v != v else v for v in row])
        sb = ttk.Scrollbar(win, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        tv.pack(fill=BOTH, expand=YES)

    def undo(self) -> None:
        self._history(lambda d: d.undo())

    def redo(self) -> None:
        self._history(lambda d: d.redo())

    def _history(self, fn) -> None:
        tab = self.tab
        if tab and fn(tab.doc):
            tab.canvas.sel = None
            tab.canvas.redraw()
            self.refresh_panel()

    def _view(self, what: str) -> None:
        tab = self.tab
        if not tab:
            return
        c = tab.canvas
        {"fit": c.fit, "100": lambda: c.set_zoom(1.0), "in": lambda: c.zoom_by(1.25),
         "out": lambda: c.zoom_by(0.8)}[what]()

    def set_mode(self, mode: str) -> None:
        log.debug("mode -> %s", mode)
        self.mode_var.set(mode)
        self.hint_var.set(MODE_HINTS[mode])
        for t in self.tabs:
            t.canvas.mode = mode
            t.canvas.configure(cursor="fleur" if mode == "pan" else "crosshair")
        tab = self.tab
        if tab and mode != "calibrate":
            tab.canvas.pending = None
        if tab:
            tab.canvas.focus_set()

    def set_pending(self, name: str) -> None:
        tab = self.tab
        if not tab:
            return
        self.set_mode("calibrate")
        tab.canvas.pending = name
        self.status_var.set(f"Click on the image to place {name.upper()}")

    # ----------------------------------------------------------- calibration
    def apply_value(self, name: str) -> None:
        tab = self.tab
        if not tab or self._syncing:
            return
        cal = tab.doc.calibration
        try:
            v = float(self.val_vars[name].get())
        except ValueError:
            self.val_vars[name].set(f"{cal.values[name]:g}")
            return
        if v == cal.values[name]:
            return
        tab.doc.push_undo()
        cal.values[name] = v
        tab.canvas.draw_overlay()
        self.refresh_points()
        if (cal.xlog if name[0] == "x" else cal.ylog) and v <= 0:
            self.status_var.set("Log axes need positive reference values")

    def apply_log(self) -> None:
        tab = self.tab
        if not tab:
            return
        tab.doc.push_undo()
        tab.doc.calibration.xlog = self.log_vars["x"].get()
        tab.doc.calibration.ylog = self.log_vars["y"].get()
        self.refresh_points()

    def clear_calibration(self) -> None:
        tab = self.tab
        if tab:
            tab.doc.push_undo()
            tab.doc.calibration.handles = {n: None for n in HANDLE_NAMES}
            tab.canvas.pending = None
            tab.canvas.sel = None
            tab.canvas.draw_overlay()
            self.refresh_panel()

    # ---------------------------------------------------------------- series
    def _on_series_chosen(self, _e) -> None:
        tab = self.tab
        if tab:
            tab.doc.active = self.series_combo.current()
            tab.canvas.sel = None
            tab.canvas.draw_overlay()
            self.refresh_points()

    def new_series(self) -> None:
        tab = self.tab
        if tab:
            tab.doc.push_undo()
            tab.doc.add_series()
            self.set_mode("add")
            self.refresh_panel()

    def rename_series(self) -> None:
        tab = self.tab
        if tab:
            name = simpledialog.askstring("Rename series", "Name:", initialvalue=tab.doc.current.name)
            if name:
                tab.doc.push_undo()
                tab.doc.current.name = name
                self.refresh_panel()

    def pick_color(self) -> None:
        tab = self.tab
        if tab:
            _, hexcol = colorchooser.askcolor(color=tab.doc.current.color)
            if hexcol:
                tab.doc.push_undo()
                tab.doc.current.color = hexcol
                tab.canvas.draw_overlay()

    def delete_series(self) -> None:
        tab = self.tab
        if tab and messagebox.askyesno("Delete series", f"Delete '{tab.doc.current.name}'?"):
            tab.doc.push_undo()
            tab.doc.remove_series(tab.doc.active)
            tab.canvas.sel = None
            tab.canvas.draw_overlay()
            self.refresh_panel()

    # ------------------------------------------------------------ point edit
    def get_step(self) -> float:
        try:
            v = float(self.step_var.get())
            return v if v > 0 else 1.0
        except (tk.TclError, ValueError):
            return 1.0

    def nudge_step(self, dx: float, dy: float) -> None:
        tab = self.tab
        if tab:
            k = self.get_step()
            tab.canvas.nudge(dx * k, dy * k)

    def zoom_to_selection(self) -> None:
        tab = self.tab
        if tab and tab.canvas.position(tab.canvas.sel):
            c = tab.canvas
            c.set_zoom(max(c.scale, 12.0))
            c.center_on(*c.position(c.sel))

    def edit_point(self) -> None:
        tab = self.tab
        if not tab or not tab.canvas.sel:
            return
        c, doc, sel = tab.canvas, tab.doc, tab.canvas.sel
        if sel[0] == "handle":
            messagebox.showinfo("Edit", "Edit axis reference values in the calibration panel.")
            return
        pos = c.position(sel)
        if pos is None:
            return
        data = doc.calibration.to_data(*pos)
        if data is None:
            dlg = ValueDialog(self.root, "Edit point (pixels)", ("px", "py"), pos)
            if dlg.result:
                doc.push_undo()
                doc.series[sel[1]].points[sel[2]] = list(dlg.result)
        else:
            dlg = ValueDialog(self.root, "Edit point (data)", ("x", "y"), data)
            if dlg.result:
                doc.push_undo()
                if not doc.set_point_data(sel[1], sel[2], *dlg.result):
                    doc._undo.pop()
                    messagebox.showerror("Edit", "Value is not valid for the current axes.")
        c.draw_overlay()
        self.refresh_points()

    # ------------------------------------------------ canvas -> panel callbacks
    def on_change(self, live: bool) -> None:
        tab = self.tab
        if not tab:
            return
        if live:
            sel = tab.canvas.sel
            if sel and sel[0] == "point" and sel[1] == tab.doc.active:
                iid = str(sel[2])
                if self.tree.exists(iid):
                    self.tree.item(iid, values=self._row(tab.doc, sel[2]))
            else:
                self._refresh_cal_labels()
        else:
            self.refresh_panel()

    def on_select(self) -> None:
        tab = self.tab
        if not tab:
            return
        sel = tab.canvas.sel
        self._syncing = True
        try:
            if sel and sel[0] == "point" and sel[1] == tab.doc.active and \
                    self.tree.exists(str(sel[2])):
                if self.tree.selection() != (str(sel[2]),):
                    self.tree.selection_set(str(sel[2]))
                self.tree.see(str(sel[2]))
            else:
                self.tree.selection_remove(self.tree.selection())
        finally:
            self._syncing = False

    def on_cursor(self, x: float, y: float) -> None:
        tab = self.tab
        if not tab:
            return
        data = tab.doc.calibration.to_data(x, y)
        d = f"   data ({data[0]:.6g}, {data[1]:.6g})" if data else "   (calibration incomplete)"
        self.status_var.set(f"pixel ({x:.2f}, {y:.2f}){d}   zoom {tab.canvas.scale * 100:.0f}%")
        self.loupe.show(tab.doc, x, y)

    def _on_tree_select(self, _e) -> None:
        tab = self.tab
        sel = self.tree.selection()
        if self._syncing or not tab or not sel:
            return
        target = ("point", tab.doc.active, int(sel[0]))
        if tab.canvas.sel == target:  # echo of a canvas-driven selection
            return
        log.debug("Tree selected point %s", target)
        tab.canvas.select(target)
        pos = tab.canvas.position(tab.canvas.sel)
        c = tab.canvas
        if pos:
            cx, cy = c.to_canvas(*pos)
            if not (20 < cx < c.winfo_width() - 20 and 20 < cy < c.winfo_height() - 20):
                c.center_on(*pos)

    # -------------------------------------------------------- panel refresh
    def _row(self, doc: ImageDocument, i: int) -> tuple:
        px, py = doc.current.points[i]
        data = doc.calibration.to_data(px, py)
        return (i + 1, fmt(data[0] if data else None), fmt(data[1] if data else None),
                f"{px:.1f}", f"{py:.1f}")

    def _refresh_cal_labels(self) -> None:
        tab = self.tab
        cal = tab.doc.calibration
        for n in HANDLE_NAMES:
            h = cal.handles[n]
            self.px_vars[n].set("not set" if h is None else f"({h[0]:.1f}, {h[1]:.1f})")

    def refresh_points(self) -> None:
        self.tree.delete(*self.tree.get_children())
        tab = self.tab
        if tab:
            for i in range(len(tab.doc.current.points)):
                self.tree.insert("", "end", iid=str(i), values=self._row(tab.doc, i))
            self.on_select()

    def refresh_panel(self) -> None:
        log.debug("refresh panel")
        tab = self.tab
        self._syncing = True
        try:
            if tab is None:
                for n in HANDLE_NAMES:
                    self.px_vars[n].set("not set")
                self.series_combo.configure(values=[])
                self.series_var.set("")
                self.tree.delete(*self.tree.get_children())
                return
            cal = tab.doc.calibration
            for n in HANDLE_NAMES:
                self.val_vars[n].set(f"{cal.values[n]:g}")
            self.log_vars["x"].set(cal.xlog)
            self.log_vars["y"].set(cal.ylog)
            self._refresh_cal_labels()
            self.series_combo.configure(values=[s.name for s in tab.doc.series])
            self.series_combo.current(tab.doc.active)
        finally:
            self._syncing = False
        self.refresh_points()

    def run(self, paths: list[str]) -> None:
        if paths:
            self.root.after(200, lambda: self.open_sources(paths))
        self.root.report_callback_exception = self._report_exception
        self.root.mainloop()

    @staticmethod
    def _report_exception(et, ev, tb) -> None:
        log.error("Exception in Tk callback", exc_info=(et, ev, tb))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    setup_logging(resolve_level(args), args.log_dir)
    app = App()
    app.run(args.images)
    log.info("Application closed")


if __name__ == "__main__":
    main()
