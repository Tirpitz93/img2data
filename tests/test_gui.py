"""Headless-ish GUI smoke test (needs a display; skipped otherwise)."""

import pytest
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