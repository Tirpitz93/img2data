"""
Filter Images based on quality parameters as best as possible to reduce the number of images to be processed by the model.

Normalizes the images to a consistent exposure and brightness level to improve the accuracy of the model.

Flags images based on the following parameters:
    - shared similarity between images
    - motion blur
    - brightness
    - depth of field (region of image with high frequency content)

"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

import cv2
from tkinter import Tk, ttk, filedialog, colorchooser, messagebox
import tkinter as tk
from PIL import ImageTk as itk
from PIL import Image

import accordion
from accordion import Accordion
from filters.base import FilterBase
from filters.brightness import FilterBrightness
from filters.focus import FilterFocus
from filters.green_screen import FilterGreenScreen
from filters.pipeline import FilterPipeline

log = logging.getLogger(__name__)
timing_log = logging.getLogger("img2data.filter_timing")


class FilterControlsBase(accordion.Chord):
    def __init__(self, master: Accordion, filter: FilterBase, *,
                 filter_index: int, on_change):
        super().__init__(master, title=filter.__class__.__name__)
        self.master = master
        self.filter = filter
        self.filter_index = filter_index
        self.on_change = on_change
        self.parameter_widgets = []
        self.threshold_slider = None
        self.histogram_canvas = None
        self.histogram_counts = ()
        self.create_widgets()

    def on_parameter_change(self, param_name, value):
        """
        Callback function to handle parameter changes from the control widgets.
        :param param_name: Name of the parameter that changed
        :param value: New value of the parameter
        """
        started = time.perf_counter()
        self.filter.set_parameters({param_name: {"default": value}})
        if param_name == self.filter.histogram_threshold:
            histogram_started = time.perf_counter()
            self._draw_histogram()
            timing_log.debug("ui_histogram filter=%s parameter=%s elapsed_ms=%.2f",
                             type(self.filter).__name__, param_name,
                             (time.perf_counter() - histogram_started) * 1000)
        self.on_change(self.filter_index)
        timing_log.debug("ui_parameter filter=%s parameter=%s elapsed_ms=%.2f",
                         type(self.filter).__name__, param_name,
                         (time.perf_counter() - started) * 1000)

    def set_filter_enabled(self, enable_var):
        enabled = enable_var.get()
        self.on_parameter_change("enabled", enabled)
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in self.parameter_widgets:
            widget.configure(state=state)

    def create_widgets(self):
        params = self.filter.get_parameters()
        enabled = self.filter.enabled
        enable_label = tk.Label(self, text="Enable Filter")
        enable_label.pack()
        enable_var = tk.BooleanVar(master=self, value=enabled)
        enable_check = tk.Checkbutton(self, variable=enable_var,
                                      command=lambda: self.set_filter_enabled(enable_var))
        enable_check.pack()
        invert_var = tk.BooleanVar(master=self,
            value=self.filter.parameters.get("invert", {}).get("default", False))
        invert_check = tk.Checkbutton(
            self, text="Invert mask", variable=invert_var,
            command=lambda: self.on_parameter_change("invert", invert_var.get()))
        invert_check.pack()
        histogram_label = tk.Label(self, text=f"{self.filter.metric_label} distribution")
        histogram_label.pack()
        self.histogram_canvas = tk.Canvas(
            self, width=190, height=90, background="white", highlightthickness=0)
        self.histogram_canvas.pack(fill=tk.X, padx=4, pady=(0, 6))
        self.histogram_canvas.bind("<Configure>", lambda _event: self._draw_histogram())
        if self.filter.histogram_threshold:
            self.histogram_canvas.bind("<Button-1>", self._on_histogram_click)
            self.histogram_canvas.configure(cursor="crosshair")
        if params is None:
            return
        for param_name, param_info in params.items():
            if param_name in ("enabled", "invert"):
                continue
            label = param_info.get("label", param_name)
            type = param_info.get("type", "int")
            default = param_info.get("default", 0)
            range = param_info.get("range", (0, 100))
            if type == "int":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                scale_widget = tk.Scale(self, from_=range[0], to=range[1], orient=tk.HORIZONTAL)
                scale_widget.set(default)
                scale_widget.pack()
                self.parameter_widgets.append(scale_widget)
                if param_name == self.filter.histogram_threshold:
                    self.threshold_slider = scale_widget

                scale_widget.configure(
                    command=lambda value, param_name=param_name: self.on_parameter_change(param_name,
                                                                                          int(float(value))))
            if type == "float":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                scale_widget = tk.Scale(self, from_=range[0], to=range[1], orient=tk.HORIZONTAL, resolution=0.01)
                scale_widget.set(default)
                scale_widget.pack()
                self.parameter_widgets.append(scale_widget)
                scale_widget.configure(
                    command=lambda value, param_name=param_name: self.on_parameter_change(param_name, float(value)))
            if type == "bool":
                var = tk.BooleanVar(master=self, value=default)
                check_widget = tk.Checkbutton(self, text=label, variable=var)
                check_widget.pack()
                self.parameter_widgets.append(check_widget)
                check_widget.config(
                    command=lambda param_name=param_name, var=var: self.on_parameter_change(param_name, var.get()))
            if type == "str":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                entry_widget = tk.Entry(self)
                entry_widget.insert(0, default)
                entry_widget.pack()
                self.parameter_widgets.append(entry_widget)
                entry_widget.bind("<FocusOut>", lambda event, param_name=param_name,
                                                       entry_widget=entry_widget: self.on_parameter_change(param_name,
                                                                                                           entry_widget.get()))
            if type == "colour":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                colour_button = tk.Button(self, text="Select Colour", command=lambda: self.select_colour(param_name))
                colour_button.pack()
                self.parameter_widgets.append(colour_button)
                colour_var = tk.StringVar(master=self, value=default)
                colour_button.config(command=lambda: self.select_colour(param_name, colour_var))
                colour_label = tk.Label(self, textvariable=colour_var)
                colour_label.pack()
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in self.parameter_widgets:
            widget.configure(state=state)

    def set_histogram(self, counts):
        self.histogram_counts = tuple(counts or ())
        self._draw_histogram()

    def _histogram_bounds(self):
        canvas = self.histogram_canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1:
            width = int(canvas["width"])
        if height <= 1:
            height = int(canvas["height"])
        return 8, max(9, width - 8), 6, max(7, height - 16), height

    def _on_histogram_click(self, event):
        if not self.histogram_counts or not self.filter.enabled or self.threshold_slider is None:
            return
        left, right, _, _, _ = self._histogram_bounds()
        fraction = max(0.0, min(1.0, (event.x - left) / (right - left)))
        self.threshold_slider.set(round(fraction * 255))

    def _draw_histogram(self):
        if self.histogram_canvas is None:
            return
        canvas = self.histogram_canvas
        canvas.delete("all")
        if not self.histogram_counts:
            return
        left, right, top, bottom, height = self._histogram_bounds()
        plot_width, plot_height = right - left, bottom - top
        peak = max(self.histogram_counts)
        if peak == 0:
            peak = 1
        bin_width = plot_width / len(self.histogram_counts)
        for index, count in enumerate(self.histogram_counts):
            bar_height = plot_height * count / peak
            x0 = left + index * bin_width
            x1 = left + (index + 1) * bin_width
            canvas.create_rectangle(
                x0, bottom - bar_height, x1, bottom,
                fill="#4a78a8", outline="", tags=("histogram-bar",))
        canvas.create_line(left, bottom, right, bottom, fill="#666666")
        canvas.create_text(left, height - 7, text="0", anchor=tk.W, fill="#555555")
        canvas.create_text(right, height - 7, text="255", anchor=tk.E, fill="#555555")
        if self.threshold_slider is not None:
            x = left + (right - left) * self.threshold_slider.get() / 255
            canvas.create_line(x, top, x, bottom, fill="#b02020", width=2,
                               tags=("histogram-threshold",))

    def select_colour(self, param_name, colour_var):
        colour_code = colorchooser.askcolor(title="Choose colour")[1]
        if colour_code:
            colour_var.set(colour_code)
            self.on_parameter_change(param_name, colour_code)


def rgb_to_int(colour):
    """
    Convert a hex colour string to an integer representation.
    :param colour: Hex colour string (e.g., "#FF0000")
    :return: Integer representation of the colour
    """
    colour = colour.lstrip('#')
    return int(colour, 16)


class ImageTab(tk.Frame):
    def __init__(self, master, image_path, filters=()):
        image_pil = self.load_image(image_path)
        super().__init__(master)
        self.image_path = image_path
        self.filters = list(filters)
        self.filter_masks = [None] * len(self.filters)
        self.filter_histograms = [None] * len(self.filters)
        self.image_pil = image_pil
        self.background_sample = None
        self.background_sample_source = None
        self.canvas = tk.Canvas(self, width=self.winfo_width(), height=self.winfo_height(),
                                bg="white", borderwidth=0, highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tk_image = None
        self.tk_composite = None
        self._base_source = None
        self._base_size = None
        self._base_image = None
        self._overlay_cache = [None] * len(self.filters)
        self._render_layers = ()
        self._base_item = self.canvas.create_image(0, 0, anchor=tk.NW)
        self._composite_item = self.canvas.create_image(
            0, 0, anchor=tk.NW, tags="filter-overlay", state=tk.HIDDEN)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_canvas_configure(self, _event):
        self.update_canvas()

    def load_image(self, path):
        # Load image using OpenCV
        image = cv2.imread(path)
        if image is None:
            raise ValueError(f"Unable to read image: {path}")
        # Convert BGR to RGB
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Convert to PIL Image
        return Image.fromarray(image)

    def update_canvas(self):
        started = time.perf_counter()
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.image_pil is None:
            return
        display_size = (width, height)
        base_changed = self._base_source is not self.image_pil or self._base_size != display_size
        resize_ms = photo_ms = 0.0
        if base_changed:
            resize_started = time.perf_counter()
            source = self.image_pil if self.image_pil.mode == "RGB" else self.image_pil.convert("RGB")
            self._base_image = source.resize(display_size, Image.Resampling.LANCZOS)
            resize_ms = (time.perf_counter() - resize_started) * 1000
            photo_started = time.perf_counter()
            self.tk_image = itk.PhotoImage(self._base_image, master=self.canvas)
            photo_ms = (time.perf_counter() - photo_started) * 1000
            self.canvas.itemconfigure(self._base_item, image=self.tk_image)
            self._base_source = self.image_pil
            self._base_size = display_size
            self._overlay_cache = [None] * len(self.filters)

        overlays_started = time.perf_counter()
        layers = []
        for index, mask in enumerate(self.filter_masks):
            if mask is not None and self.filters[index].enabled:
                layers.append(self.apply_filter_mask(index, mask, display_size))
            else:
                self._overlay_cache[index] = None
        changed = (len(layers) != len(self._render_layers)
                   or any(layer is not old for layer, old in zip(layers, self._render_layers)))
        if base_changed or changed:
            if layers:
                composite = self._base_image.copy()
                for layer in layers:
                    composite.paste(layer, (0, 0), layer)
                self.tk_composite = itk.PhotoImage(composite, master=self.canvas)
                self.canvas.itemconfigure(
                    self._composite_item, image=self.tk_composite, state=tk.NORMAL)
            else:
                self.canvas.itemconfigure(self._composite_item, image="", state=tk.HIDDEN)
                self.tk_composite = None
            self._render_layers = tuple(layers)
        timing_log.debug(
            "ui_canvas image=%s display=%s base_resize_ms=%.2f base_photo_ms=%.2f "
            "overlays_ms=%.2f total_ms=%.2f",
            self.image_pil.size, display_size, resize_ms, photo_ms,
            (time.perf_counter() - overlays_started) * 1000,
            (time.perf_counter() - started) * 1000)

    def set_filter_mask(self, index: int, mask: Image.Image, *, redraw=True) -> None:
        self.filter_masks[index] = mask
        if redraw:
            self.update_canvas()

    def apply_filter_mask(self, index: int, mask: Image.Image, display_size=None):
        """Return a display-sized overlay, reusing it while its inputs are unchanged."""
        filter_instance = self.filters[index]
        display_size = display_size or (max(1, self.canvas.winfo_width()),
                                        max(1, self.canvas.winfo_height()))
        cached = self._overlay_cache[index]
        colour = filter_instance.overlay_colour
        if cached is not None:
            old_mask, old_size, old_colour, layer = cached
            if old_mask is mask and old_size == display_size and old_colour == colour:
                return layer
        started = time.perf_counter()
        overlay = filter_instance.overlay_layer(mask, display_size)
        overlay_ms = (time.perf_counter() - started) * 1000
        self._overlay_cache[index] = (mask, display_size, colour, overlay)
        timing_log.debug("ui_overlay filter=%s layer_ms=%.2f",
                         type(filter_instance).__name__, overlay_ms)
        return overlay


class ImageFilterBuilder(Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Filter Builder")
        self.geometry("1200x800")

        # create main Menu
        self.menu = tk.Menu(self)
        self.config(menu=self.menu)
        self.file_menu = tk.Menu(self.menu, tearoff=0)
        self.file_menu.add_command(label="Open Images", command=self.open_image)
        self.file_menu.add_command(label="Open Folder", command=self.open_folder)

        self.file_menu.add_command(label="Save Filtered Images", command=self.save_filtered_images)
        self.menu.add_cascade(label="File", menu=self.file_menu)

        self.tabs = []
        self._sampling_tab = None
        self.bind("<Escape>", self._escape_background_sample)
        self.pipeline = FilterPipeline()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(30, self._poll_filter_results)

        # create notebook for images
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # middle click to close tab
        self.notebook.bind("<Button-2>", lambda event: self.close_tab(event))

        sidebar = ttk.Frame(self)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        self.controls_canvas = tk.Canvas(sidebar, highlightthickness=0)
        self.controls_scrollbar = ttk.Scrollbar(
            sidebar, orient=tk.VERTICAL, command=self.controls_canvas.yview)
        self.controls_canvas.configure(yscrollcommand=self.controls_scrollbar.set)
        self.controls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.controls_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.controls_frame = Accordion(self.controls_canvas, accordion_style={'title_bg': 'ghost white', 'title_fg': 'black',
                                                               'highlight': 'white smoke'})
        controls_window = self.controls_canvas.create_window(
            (0, 0), window=self.controls_frame, anchor=tk.NW)
        self.controls_frame.bind(
            "<Configure>", lambda _event: self.controls_canvas.configure(
                scrollregion=self.controls_canvas.bbox("all")))
        self.controls_frame.bind(
            "<<AccordionChanged>>", lambda _event: self.after_idle(
                self._update_sidebar_scrollregion))
        self.controls_canvas.bind(
            "<Configure>", lambda event: self.controls_canvas.itemconfigure(
                controls_window, width=event.width))
        self.filters = [FilterBrightness, FilterFocus, FilterGreenScreen]
        self.filter_controls = []
        for filter_index, filter_class in enumerate(self.filters):
            filter_instance = filter_class()  # Pass None for image_path, will be set later

            _chord = FilterControlsBase(
                self.controls_frame, filter_instance, filter_index=filter_index,
                on_change=self.on_filter_change)
            if isinstance(filter_instance, FilterGreenScreen):
                self.background_filter_index = filter_index
                self.background_sample_label = tk.Label(_chord, text="Background: default green")
                self.background_sample_label.pack()
                tk.Button(_chord, text="Sample background from image",
                          command=self.start_background_sample).pack()
                tk.Button(_chord, text="Reset to green thresholds",
                          command=self.reset_background_sample).pack()
            self.filter_controls.append(_chord)
        self.controls_frame.append_chords(self.filter_controls)
        self.controls_frame.update_idletasks()
        self.controls_canvas.configure(width=self.controls_frame.winfo_reqwidth())

    def _update_sidebar_scrollregion(self):
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _selected_tab(self):
        selected = self.notebook.select()
        return self.notebook.nametowidget(selected) if selected else None

    def _on_tab_changed(self, _event):
        self._cancel_background_sample()
        self.update_canvas()

    def _cancel_background_sample(self):
        if self._sampling_tab is not None:
            self._sampling_tab.canvas.unbind("<Button-1>")
            self._sampling_tab.canvas.configure(cursor="")
            self._sampling_tab = None

    def _escape_background_sample(self, _event):
        if self._sampling_tab is not None:
            tab = self._sampling_tab
            self._cancel_background_sample()
            self._update_background_sample_label(tab)

    def _update_background_sample_label(self, tab):
        if tab.background_sample_source is not tab.image_pil:
            tab.background_sample = None
            tab.background_sample_source = None
        if self._sampling_tab is tab:
            self.background_sample_label.configure(text="Click the background in the image")
            return
        colour = tab.background_sample
        text = "Background: default green" if colour is None else (
            "Background: #%02X%02X%02X" % colour)
        self.background_sample_label.configure(text=text)

    def start_background_sample(self):
        tab = self._selected_tab()
        if tab is None:
            messagebox.showinfo("Sample background", "Open an image first.", parent=self)
            return
        self._cancel_background_sample()
        self._sampling_tab = tab
        tab.canvas.configure(cursor="crosshair")
        tab.canvas.bind("<Button-1>", lambda event: self._sample_background(tab, event))
        self.background_sample_label.configure(text="Click the background in the image")

    def _sample_background(self, tab, event):
        width, height = tab.canvas.winfo_width(), tab.canvas.winfo_height()
        x, y = tab.canvas.canvasx(event.x), tab.canvas.canvasy(event.y)
        if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
            return
        image_width, image_height = tab.image_pil.size
        pixel = (min(image_width - 1, int(x * image_width / width)),
                 min(image_height - 1, int(y * image_height / height)))
        source = tab.image_pil if tab.image_pil.mode == "RGB" else tab.image_pil.convert("RGB")
        tab.background_sample = source.getpixel(pixel)
        tab.background_sample_source = tab.image_pil
        self._cancel_background_sample()
        self._update_background_sample_label(tab)
        index = self.background_filter_index
        tab.filter_masks[index] = None
        if self.filter_controls[index].filter.enabled:
            self._submit_filter(tab, index, self.filter_controls[index].filter)
        if self._selected_tab() is tab:
            tab.update_canvas()

    def reset_background_sample(self):
        self._cancel_background_sample()
        tab = self._selected_tab()
        if tab is None:
            messagebox.showinfo("Reset background", "Open an image first.", parent=self)
            return
        tab.background_sample = None
        tab.background_sample_source = None
        self._update_background_sample_label(tab)
        index = self.background_filter_index
        tab.filter_masks[index] = None
        if self.filter_controls[index].filter.enabled:
            self._submit_filter(tab, index, self.filter_controls[index].filter)
        tab.update_canvas()

    def open_image(self):
        file_paths = filedialog.askopenfilenames(
            parent=self, filetypes=[("Image files", "*.jpg *.png *.jpeg *.bmp *.tif *.tiff")])
        errors = self.load_images(file_paths)
        if errors:
            messagebox.showerror("Unable to open images", "\n".join(errors), parent=self)

    def load_images(self, paths):
        errors = []
        for path in paths:
            try:
                self.load_image(path)
            except ValueError as exc:
                errors.append(str(exc))
                log.warning("%s", exc)
        return errors

    def update_canvas(self):
        # update the currently visible tab's canvas with the image

        selected_tab = self.notebook.select()
        if not selected_tab:
            return
        tab: ImageTab = self.notebook.nametowidget(selected_tab)
        tab.update_canvas()
        self._update_background_sample_label(tab)
        for control, histogram in zip(self.filter_controls, tab.filter_histograms):
            control.set_histogram(histogram)

    def load_image(self, path):
        path = os.fspath(path)
        filters = [control.filter for control in self.filter_controls]
        image_tab = ImageTab(self.notebook, path, filters)
        self.image_path = path
        self.image_pil = image_tab.image_pil
        self.notebook.add(image_tab, text=Path(path).name)
        self.tabs.append(image_tab)
        image_tab.update_canvas()
        for index, control in enumerate(self.filter_controls):
            if control.filter.enabled:
                self._submit_filter(image_tab, index, control.filter)
        return self.image_pil

    def open_folder(self):
        pass

    def save_filtered_images(self):
        pass

    def close_tab(self, event):
        # close the currently selected tab
        current_tab = self.notebook.select()
        if current_tab:
            tab = self.notebook.nametowidget(current_tab)
            if self._sampling_tab is tab:
                self._cancel_background_sample()
            for index in range(len(self.filter_controls)):
                self.pipeline.cancel((tab, index))
            self.notebook.forget(current_tab)
            self.tabs.remove(tab)
            self.update_canvas()

    def on_filter_change(self, index):
        started = time.perf_counter()
        for tab in self.tabs:
            tab.filter_masks[index] = None
            filter_instance = self.filter_controls[index].filter
            if filter_instance.enabled:
                self._submit_filter(tab, index, filter_instance)
            else:
                self.pipeline.invalidate((tab, index))
        self.update_canvas()
        timing_log.debug("ui_change filter=%s tabs=%d elapsed_ms=%.2f",
                         type(self.filter_controls[index].filter).__name__, len(self.tabs),
                         (time.perf_counter() - started) * 1000)

    def _submit_filter(self, tab, index, filter_instance):
        overrides = None
        if isinstance(filter_instance, FilterGreenScreen):
            if tab.background_sample_source is not tab.image_pil:
                tab.background_sample = None
                tab.background_sample_source = None
            overrides = {"background_rgb": {"default": tab.background_sample}}
        self.pipeline.submit((tab, index), filter_instance, tab.image_pil,
                             parameter_overrides=overrides)

    def _poll_filter_results(self):
        while result := self.pipeline.get_result():
            started = time.perf_counter()
            tab, index = result.key
            if tab not in self.tabs or not self.pipeline.is_latest(result.key, result.version):
                timing_log.debug("ui_result filter=%s version=%d stale=true",
                                 result.filter_name, result.version)
                continue
            if result.error is not None:
                log.error("Unable to calculate %s filter mask: %s",
                          result.filter_name, result.error)
                continue
            tab.filter_histograms[index] = result.histogram
            selected_tab = self.notebook.select()
            selected = bool(selected_tab and self.notebook.nametowidget(selected_tab) is tab)
            if selected:
                self.filter_controls[index].set_histogram(result.histogram)
            tab.set_filter_mask(index, result.mask, redraw=selected)
            timing_log.debug("ui_result filter=%s version=%d stale=false elapsed_ms=%.2f",
                             result.filter_name, result.version,
                             (time.perf_counter() - started) * 1000)
        self.after(30, self._poll_filter_results)

    def close(self):
        self.pipeline.close()
        self.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview image preprocessing filters")
    parser.add_argument("images", nargs="*", help="image files to open")
    args = parser.parse_args(argv)
    if os.environ.get("IMG2DATA_FILTER_TIMING") == "1":
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(threadName)s %(name)s %(message)s"))
        timing_log.addHandler(handler)
        timing_log.setLevel(logging.DEBUG)
        timing_log.propagate = False
    app = ImageFilterBuilder()
    errors = app.load_images(args.images)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        messagebox.showerror("Unable to open images", "\n".join(errors), parent=app)
    app.mainloop()


if __name__ == "__main__":
    main()
