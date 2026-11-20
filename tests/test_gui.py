"""Headless-ish GUI smoke test (needs a display; skipped otherwise)."""

import pytest
import time
import logging
from PIL import Image

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="session")
def _app():
    from img2data.app import App

    try:
        a = App()
    except tk.TclError:
        pytest.skip("no display")
    yield a
    a.root.destroy()


@pytest.fixture
def app(_app):
    yield _app
    while _app.tabs:
        _app.close_tab()
    _app.set_mode("calibrate")


def ev(**kw):
    return type("E", (), kw)()


def test_gui_flow(app, tmp_path):
    img = tmp_path / "g.png"
    Image.new("RGB", (300, 200), "white").save(img)
    app.open_sources([str(img), str(img)])
    app.root.update()
    assert len(app.tabs) == 2
    c = app.tab.canvas
    c.fit()
    app.root.update()
    # calibrate: four clicks
    app.set_mode("calibrate")
    for x, y in ((50, 150), (250, 150), (50, 150), (50, 30)):
        cx, cy = c.to_canvas(x, y)
        c._press(ev(x=cx, y=cy, state=0x1))
        c._release(None)
    assert c.doc.calibration.handles["y2"] is not None
    app.val_vars["x2"].set("10")
    app.apply_value("x2")
    app.val_vars["y2"].set("100")
    app.apply_value("y2")
    assert c.doc.calibration.is_ready
    # add a point and nudge it
    app.set_mode("add")
    cx, cy = c.to_canvas(150, 90)
    c._press(ev(x=cx, y=cy, state=0))
    c._release(None)
    assert len(c.doc.current.points) == 1
    c.nudge(0.5, 0)
    assert c.doc.current.points[0][0] == pytest.approx(150.5, abs=0.2)
    assert len(app.tree.get_children()) == 1
    c.delete_selected()
    assert not c.doc.current.points
    app.undo()
    assert len(c.doc.current.points) == 1
    app.close_tab()
    assert len(app.tabs) == 1

def test_add_point_via_real_events_does_not_loop(app, tmp_path):
    img = tmp_path / "e.png"
    Image.new("RGB", (300, 200), "white").save(img)
    app.open_sources([str(img)])
    app.set_mode("add")
    app.root.update()
    c = app.tab.canvas
    c.event_generate("<ButtonPress-1>", x=100, y=100)
    c.event_generate("<ButtonRelease-1>", x=100, y=100)
    app.root.update()  # used to spin forever on tree-select feedback
    assert len(c.doc.current.points) == 1
    assert c.sel == ("point", 0, 0)

def test_tab_cycles_points(app, tmp_path):
    img = tmp_path / "t.png"
    Image.new("RGB", (300, 200), "white").save(img)
    app.open_sources([str(img)])
    app.root.update()
    c = app.tab.canvas
    c.doc.current.points += [[10, 10], [20, 20], [30, 30]]
    app.refresh_points()
    assert c.bind("<Tab>") and c.bind("<Shift-Tab>")  # key events need real window focus
    c.select(("point", 0, 0))
    assert c.step_selection(1) == "break"  # "break" keeps focus on the canvas
    assert c.sel == ("point", 0, 1)
    c.step_selection(-1)
    c.step_selection(-1)
    assert c.sel == ("point", 0, 2)  # wrapped backwards
    assert app.tree.selection() == ("2",)
    c.select(None)
    c.step_selection(1)
    assert c.sel == ("point", 0, 0)


def test_filter_overlay_is_drawn_after_the_base_image(tmp_path):
    from filters.brightness import FilterBrightness
    from pre_process import ImageTab

    image_path = tmp_path / "filtered.png"
    Image.new("RGB", (20, 20), "white").save(image_path)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")

    try:
        root.geometry("100x100")
        tab = ImageTab(root, str(image_path), [FilterBrightness()])
        tab.pack(fill="both", expand=True)
        root.update()

        tab.set_filter_mask(0, Image.new("L", (20, 20), 255))
        items = tab.canvas.find_all()
        assert len(items) == 2
        assert tab.canvas.gettags(items[-1]) == ("filter-overlay",)
    finally:
        root.destroy()


def test_preview_reuses_layers_and_composites_in_filter_order(tmp_path, monkeypatch):
    from PIL import ImageTk
    from filters.brightness import FilterBrightness
    from filters.focus import FilterFocus
    from pre_process import ImageTab

    image_path = tmp_path / "cached.png"
    Image.new("RGB", (20, 20), "white").save(image_path)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.geometry("100x100")
        filters = [FilterBrightness(), FilterFocus()]
        calls = [0, 0]
        for index, filter_ in enumerate(filters):
            original = filter_.overlay_layer

            def counted(mask, size, opacity=128, *, index=index, original=original):
                calls[index] += 1
                return original(mask, size, opacity)

            monkeypatch.setattr(filter_, "overlay_layer", counted)
        tab = ImageTab(root, str(image_path), filters)
        tab.pack(fill="both", expand=True)
        root.update()
        mask = Image.new("L", (20, 20), 255)
        tab.set_filter_mask(0, mask)
        tab.set_filter_mask(1, mask)
        base_photo = tab.tk_image
        first_layer = tab._overlay_cache[0][3]
        assert ImageTk.getimage(tab.tk_composite).getpixel((0, 0))[:3] == (127, 191, 63)

        calls_before = calls.copy()
        tab.update_canvas()
        assert calls == calls_before
        assert tab.tk_image is base_photo
        tab.set_filter_mask(1, Image.new("L", (20, 20), 0))
        assert calls == [calls_before[0], calls_before[1] + 1]
        assert tab._overlay_cache[0][3] is first_layer
        assert ImageTk.getimage(tab.tk_composite).getpixel((0, 0))[:3] == (255, 127, 127)

        filters[0].set_parameters({"brightness_colour": {"default": "#0000FF"}})
        tab.update_canvas()
        assert calls[0] == calls_before[0] + 1
        assert ImageTk.getimage(tab.tk_composite).getpixel((0, 0))[:3] == (127, 127, 255)
        root.geometry("120x120")
        root.update()
        assert tab.tk_image is not base_photo
        assert tab._overlay_cache[0][1] == (tab.canvas.winfo_width(), tab.canvas.winfo_height())
    finally:
        root.destroy()


def test_disabled_filter_skips_work_and_reenables(tmp_path, monkeypatch):
    from filters.green_screen import FilterGreenScreen
    from pre_process import ImageFilterBuilder

    calls = []
    original = FilterGreenScreen.histogram

    def counted(self, image, bins=32):
        calls.append(1)
        return original(self, image, bins)

    monkeypatch.setattr(FilterGreenScreen, "histogram", counted)
    image_path = tmp_path / "disabled.png"
    Image.new("RGB", (20, 20), "green").save(image_path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        index = 2
        control = app.filter_controls[index]
        app.load_image(str(image_path))
        tab = app.tabs[-1]
        app.update()
        assert not calls
        assert tab.filter_histograms[index] is None
        control.on_parameter_change("enabled", True)
        deadline = time.monotonic() + 5
        while tab.filter_masks[index] is None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert tab.filter_masks[index] is not None
        assert calls == [1]
        control.on_parameter_change("enabled", False)
        control.on_parameter_change("enabled", True)
        deadline = time.monotonic() + 5
        while tab.filter_masks[index] is None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert tab.filter_masks[index] is not None
        assert calls == [1]
    finally:
        app.close()


def test_filter_controls_draw_metric_histogram():
    from accordion import Accordion
    from filters.brightness import FilterBrightness
    from pre_process import FilterControlsBase

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")

    try:
        accordion = Accordion(root, accordion_style={
            "title_bg": "ghost white", "title_fg": "black", "highlight": "white smoke"})
        control = FilterControlsBase(
            accordion, FilterBrightness(), filter_index=0, on_change=lambda _index: None)
        accordion.pack(fill="both", expand=True)
        control.pack(fill="x")
        root.update()

        control.set_histogram([0] * 31 + [10])
        root.update()

        bars = control.histogram_canvas.find_withtag("histogram-bar")
        assert len(bars) == 32
        assert control.histogram_canvas.itemcget(bars[0], "fill") == "#4a78a8"
    finally:
        root.destroy()


def test_filter_parameter_change_preserves_metric_histogram():
    from filters.brightness import FilterBrightness
    from pre_process import FilterControlsBase

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")

    try:
        control = FilterControlsBase(
            root, FilterBrightness(), filter_index=0, on_change=lambda _index: None)
        control.pack()
        root.update()
        control.set_histogram([0] * 31 + [10])
        before = control.histogram_canvas.find_withtag("histogram-bar")

        control.on_parameter_change("brightness_threshold", 150)
        root.update()

        after = control.histogram_canvas.find_withtag("histogram-bar")
        assert len(before) == len(after) == 32
        assert control.histogram_counts == (0,) * 31 + (10,)
    finally:
        root.destroy()


def test_filter_timing_reports_ui_stages(tmp_path, caplog):
    from filters.brightness import FilterBrightness
    from pre_process import FilterControlsBase, ImageTab

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")

    caplog.set_level(logging.DEBUG, logger="img2data.filter_timing")
    try:
        image_path = tmp_path / "timing.png"
        Image.new("RGB", (20, 20), "white").save(image_path)
        filter_ = FilterBrightness()
        tab = ImageTab(root, str(image_path), [filter_])
        tab.pack()
        control = FilterControlsBase(root, filter_, filter_index=0, on_change=lambda _: None)
        control.pack()
        root.update()
        tab.set_filter_mask(0, Image.new("L", (20, 20), 255))
        control.on_parameter_change("brightness_threshold", 150)
        messages = [record.getMessage() for record in caplog.records
                    if record.name == "img2data.filter_timing"]
        assert any("ui_canvas" in message and "base_resize_ms=" in message
                   and "overlays_ms=" in message for message in messages)
        assert any("ui_overlay" in message and "layer_ms=" in message for message in messages)
        assert any("ui_parameter" in message and "brightness_threshold" in message
                   for message in messages)
    finally:
        root.destroy()


@pytest.mark.parametrize(("filter_name", "parameter"), [
    ("brightness", "brightness_threshold"),
    ("focus", "focus_threshold"),
])
def test_histogram_click_sets_threshold_slider(filter_name, parameter):
    from filters.brightness import FilterBrightness
    from filters.focus import FilterFocus
    from pre_process import FilterControlsBase

    filter_type = {"brightness": FilterBrightness, "focus": FilterFocus}[filter_name]
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")

    try:
        changes = []
        control = FilterControlsBase(
            root, filter_type(), filter_index=0, on_change=changes.append)
        control.pack(fill="both", expand=True)
        root.geometry("400x400")
        root.update()
        canvas = control.histogram_canvas

        canvas.event_generate("<Button-1>", x=0, y=20)
        root.update()
        assert not changes

        control.set_histogram([1] * 32)
        left, right, _, _, _ = control._histogram_bounds()
        for x, expected in [(0, 0), (round((left + right) / 2), 128),
                            (canvas.winfo_width() - 1, 255)]:
            canvas.event_generate("<Button-1>", x=x, y=20)
            root.update()
            assert abs(control.threshold_slider.get() - expected) <= 1
            assert control.filter.parameters[parameter]["default"] == control.threshold_slider.get()
            marker, = canvas.find_withtag("histogram-threshold")
            marker_x = canvas.coords(marker)[0]
            assert marker_x == pytest.approx(
                left + (right - left) * control.threshold_slider.get() / 255)
        assert changes == [0, 0, 0]
        control.set_filter_enabled(tk.BooleanVar(master=root, value=False))
        changes.clear()
        canvas.event_generate("<Button-1>", x=0, y=20)
        root.update()
        assert control.threshold_slider.get() == 255
        assert not changes
    finally:
        root.destroy()


def test_green_screen_histogram_does_not_bind_threshold_click():
    from filters.green_screen import FilterGreenScreen
    from pre_process import FilterControlsBase

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        control = FilterControlsBase(root, FilterGreenScreen(), filter_index=0,
                                     on_change=lambda _index: None)
        assert not control.histogram_canvas.bind("<Button-1>")
    finally:
        root.destroy()


def test_green_screen_filter_in_applet(tmp_path):
    from filters.green_screen import FilterGreenScreen
    from pre_process import ImageFilterBuilder

    image_path = tmp_path / "green.png"
    image = Image.new("RGB", (40, 40), (0, 255, 0))
    for y in range(10, 30):
        for x in range(10, 30):
            image.putpixel((x, y), (255, 0, 0))
    image.save(image_path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")

    try:
        index = next(i for i, control in enumerate(app.filter_controls)
                     if isinstance(control.filter, FilterGreenScreen))
        control = app.filter_controls[index]
        assert not control.filter.enabled
        control.on_parameter_change("dilate_px", 0)
        control.set_filter_enabled(tk.BooleanVar(master=app, value=True))
        app.load_image(str(image_path))
        tab = app.tabs[-1]
        deadline = time.monotonic() + 5
        while tab.filter_masks[index] is None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert tab.filter_masks[index] is not None
        assert tab.filter_masks[index].getpixel((20, 20)) == 255
        assert tab.filter_masks[index].getpixel((0, 0)) == 0
        assert sum(tab.filter_histograms[index]) == 1600
        assert control.histogram_counts == tab.filter_histograms[index]
    finally:
        app.close()


def test_background_sampling_is_per_tab_and_uses_original_pixels(tmp_path):
    from pre_process import ImageFilterBuilder

    paths = [tmp_path / "blue.png", tmp_path / "white.png"]
    for path, background in zip(paths, [(0, 0, 255), (255, 255, 255)]):
        image = Image.new("RGB", (40, 40), background)
        for x in range(10, 30):
            for y in range(10, 30):
                image.putpixel((x, y), (255, 0, 0))
        image.save(path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        control = app.filter_controls[app.background_filter_index]
        control.on_parameter_change("dilate_px", 0)
        control.on_parameter_change("morphology_radius", 0)
        control.on_parameter_change("enabled", True)
        app.load_image(str(paths[0]))
        app.load_image(str(paths[1]))
        app.update()
        first, second = app.tabs
        index = app.background_filter_index

        def wait_for_mask(tab):
            deadline = time.monotonic() + 5
            while tab.filter_masks[index] is None and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert tab.filter_masks[index] is not None

        def sample(tab):
            app.notebook.select(tab)
            app.update()
            app.start_background_sample()
            tab.canvas.event_generate("<Button-1>", x=5, y=5)
            app.update()
            wait_for_mask(tab)

        sample(first)
        assert first.background_sample == (0, 0, 255)
        assert second.background_sample is None
        assert first.filter_masks[index].getpixel((0, 0)) == 0
        assert first.filter_masks[index].getpixel((20, 20)) == 255
        sample(second)
        assert second.background_sample == (255, 255, 255)
        assert first.background_sample == (0, 0, 255)
        assert second.filter_masks[index].getpixel((0, 0)) == 0
        assert second.filter_masks[index].getpixel((20, 20)) == 255

        control.on_parameter_change("colour_tolerance", 15)
        wait_for_mask(first)
        wait_for_mask(second)
        assert first.filter_masks[index].getpixel((0, 0)) == 0
        assert second.filter_masks[index].getpixel((0, 0)) == 0
        app.notebook.select(first)
        app.update()
        assert "#0000FF" in app.background_sample_label.cget("text")
        app.reset_background_sample()
        assert first.background_sample is None
        assert second.background_sample == (255, 255, 255)
        wait_for_mask(first)
        assert first.filter_masks[index].getpixel((0, 0)) == 255
    finally:
        app.close()


def test_background_sample_can_be_cancelled_and_disabled_filter_remains_idle(tmp_path):
    from pre_process import ImageFilterBuilder

    path = tmp_path / "sample.png"
    Image.new("RGB", (20, 20), "blue").save(path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.load_image(str(path))
        app.update()
        tab = app.tabs[0]
        app.start_background_sample()
        app._escape_background_sample(None)
        assert app._sampling_tab is None
        assert tab.background_sample is None
        app.start_background_sample()
        tab.canvas.event_generate("<Button-1>", x=3, y=3)
        app.update()
        assert tab.background_sample == (0, 0, 255)
        assert tab.filter_masks[app.background_filter_index] is None
        tab.image_pil = Image.new("RGB", (20, 20), "red")
        app.update_canvas()
        assert tab.background_sample is None
    finally:
        app.close()


def test_filter_sidebar_scrollbar_reaches_expanded_controls():
    from pre_process import ImageFilterBuilder

    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.geometry("700x350")
        for control in app.filter_controls:
            app.controls_frame._click_handler(control)
        app.update()
        canvas = app.controls_canvas
        assert canvas.yview()[1] < 1
        canvas.yview_moveto(1)
        app.update()
        assert canvas.yview()[1] == pytest.approx(1)
        last_control = app.filter_controls[-1]
        assert last_control.winfo_rooty() + last_control.winfo_height() <= (
            canvas.winfo_rooty() + canvas.winfo_height() + 1)
        for control in app.filter_controls:
            app.controls_frame._click_handler(control)
        app.update()
        assert canvas.yview()[0] == pytest.approx(0)
    finally:
        app.close()


def test_preprocess_multi_file_dialog_opens_valid_images_and_reports_errors(tmp_path, monkeypatch):
    from pre_process import ImageFilterBuilder

    paths = [tmp_path / "first image.png", tmp_path / "missing.png", tmp_path / "second.png"]
    Image.new("RGB", (4, 4), "red").save(paths[0])
    Image.new("RGB", (4, 4), "blue").save(paths[2])
    errors = []
    monkeypatch.setattr("pre_process.filedialog.askopenfilenames",
                        lambda **_: tuple(map(str, paths)))
    monkeypatch.setattr("pre_process.messagebox.showerror",
                        lambda title, message, **_: errors.append((title, message)))
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.open_image()
        assert [tab.image_path for tab in app.tabs] == [str(paths[0]), str(paths[2])]
        assert [app.notebook.tab(tab, "text") for tab in app.tabs] == [
            "first image.png", "second.png"]
        assert len(errors) == 1 and str(paths[1]) in errors[0][1]
    finally:
        app.close()


def test_preprocess_command_line_passes_all_images(monkeypatch, capsys):
    import pre_process

    calls = []

    class FakeApp:
        def load_images(self, paths):
            calls.append(paths)
            return ["Unable to read image: bad.png"]

        def mainloop(self):
            calls.append("mainloop")

    monkeypatch.setattr(pre_process, "ImageFilterBuilder", FakeApp)
    monkeypatch.setattr(pre_process.messagebox, "showerror",
                        lambda title, message, **_: calls.append(message))
    pre_process.main(["first image.png", "bad.png", "second.png"])
    assert calls == [["first image.png", "bad.png", "second.png"],
                     "Unable to read image: bad.png", "mainloop"]
    assert "bad.png" in capsys.readouterr().err


def test_preprocess_command_line_empty_starts_without_images(monkeypatch):
    import pre_process

    calls = []

    class FakeApp:
        def load_images(self, paths):
            calls.append(paths)
            return []

        def mainloop(self):
            calls.append("mainloop")

    monkeypatch.setattr(pre_process, "ImageFilterBuilder", FakeApp)
    pre_process.main([])
    assert calls == [[], "mainloop"]


def test_preprocess_command_line_opens_multiple_tabs(tmp_path, monkeypatch):
    import pre_process

    paths = [tmp_path / "first image.png", tmp_path / "second.png"]
    for path in paths:
        Image.new("RGB", (4, 4), "red").save(path)
    try:
        app = pre_process.ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        monkeypatch.setattr(pre_process, "ImageFilterBuilder", lambda: app)
        monkeypatch.setattr(app, "mainloop", lambda: None)
        pre_process.main([str(path) for path in paths])
        assert [tab.image_path for tab in app.tabs] == [str(path) for path in paths]
    finally:
        app.close()


def test_focus_morphology_sliders_update_preview(tmp_path):
    from pre_process import ImageFilterBuilder

    image_path = tmp_path / "focus-morphology.png"
    image = Image.new("RGB", (20, 20), "black")
    image.putpixel((10, 10), (255, 255, 255))
    image.save(image_path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")
    try:
        app.load_image(str(image_path))
        control = app.filter_controls[1]
        app.controls_frame._click_handler(control)
        app.update()
        tab = app.tabs[-1]

        def wait_for_mask():
            deadline = time.monotonic() + 5
            while tab.filter_masks[1] is None and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert tab.filter_masks[1] is not None
            return tab.filter_masks[1]

        initial = wait_for_mask()
        histogram = tab.filter_histograms[1]
        sliders = [widget for widget in control.parameter_widgets
                   if isinstance(widget, tk.Scale)]
        assert len(sliders) == 3
        sliders[1].set(2)
        app.update()
        dilated = wait_for_mask()
        assert sum(dilated.get_flattened_data()) > sum(initial.get_flattened_data())
        sliders[2].set(1)
        app.update()
        eroded = wait_for_mask()
        assert sum(eroded.get_flattened_data()) < sum(dilated.get_flattened_data())
        assert tab.filter_histograms[1] == histogram
    finally:
        app.close()


def test_focus_slider_reuses_laplacian_in_applet(tmp_path, monkeypatch):
    import cv2
    from filters.focus import FilterFocus
    from pre_process import ImageFilterBuilder

    original = cv2.Laplacian
    calls = []

    def counting_laplacian(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cv2, "Laplacian", counting_laplacian)
    image_path = tmp_path / "focus.png"
    image = Image.new("RGB", (20, 20), "black")
    image.putpixel((10, 10), (255, 255, 255))
    image.save(image_path)
    try:
        app = ImageFilterBuilder()
    except tk.TclError:
        pytest.skip("no display")

    try:
        index = next(i for i, control in enumerate(app.filter_controls)
                     if isinstance(control.filter, FilterFocus))
        app.load_image(str(image_path))
        tab = app.tabs[-1]

        def wait_for_mask():
            deadline = time.monotonic() + 5
            while tab.filter_masks[index] is None and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert tab.filter_masks[index] is not None

        wait_for_mask()
        histogram = tab.filter_histograms[index]
        assert len(calls) == 1
        control = app.filter_controls[index]
        app.controls_frame._click_handler(control)
        app.update()
        canvas = control.histogram_canvas
        canvas.event_generate("<Button-1>", x=canvas.winfo_width() - 1, y=20)
        app.update()
        assert control.threshold_slider.get() == 255
        wait_for_mask()
        assert tab.filter_masks[index].getbbox() is None
        assert tab.filter_histograms[index] == histogram
        assert len(calls) == 1
    finally:
        app.close()