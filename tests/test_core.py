import math

import pytest
from PIL import Image

from img2data import dropping
from img2data.calibration import AxisCalibration, Calibration, CalibrationError
from img2data.export import build_frame, to_markdown, write_frame
from img2data.model import ImageDocument, load_project, save_project


def make_doc(tmp_path):
    p = tmp_path / "plot.png"
    Image.new("RGB", (200, 100), "white").save(p)
    d = ImageDocument(p)
    c = d.calibration
    c.handles.update(x1=[10, 90], x2=[110, 90], y1=[10, 90], y2=[10, 10])
    c.values.update(x1=0, x2=10, y1=0, y2=100)
    return d


def test_linear_round_trip():
    a = AxisCalibration(10, 110, 0, 10)
    assert a.to_data(60) == pytest.approx(5)
    assert a.to_pixel(a.to_data(37.5)) == pytest.approx(37.5)


def test_log_axis():
    a = AxisCalibration(0, 100, 1, 100, log=True)
    assert a.to_data(50) == pytest.approx(10)
    assert a.to_pixel(10) == pytest.approx(50)
    with pytest.raises(CalibrationError):
        a.to_pixel(-1)


def test_invalid_axes():
    with pytest.raises(CalibrationError):
        AxisCalibration(1, 1, 0, 1).validate()
    with pytest.raises(CalibrationError):
        AxisCalibration(0, 1, 0, 1, log=True).validate()
    assert Calibration().to_data(1, 1) is None


def test_document_data_and_edit(tmp_path):
    d = make_doc(tmp_path)
    d.current.points.append([60, 50])
    assert d.data_for(d.current)[0] == pytest.approx((5, 50))
    assert d.set_point_data(0, 0, 2, 20)
    assert d.current.points[0] == pytest.approx([30, 74])


def test_recalibration_remaps_points(tmp_path):
    d = make_doc(tmp_path)
    d.current.points.append([60, 50])
    d.push_undo()
    d.calibration.values["x2"] = 20
    assert d.data_for(d.current)[0][0] == pytest.approx(10)
    assert d.undo()
    assert d.data_for(d.current)[0][0] == pytest.approx(5)
    assert d.redo()
    assert d.calibration.values["x2"] == 20


def test_project_round_trip(tmp_path):
    d = make_doc(tmp_path)
    d.current.points.append([60, 50])
    d.add_series("B").points.append([20, 20])
    f = tmp_path / "p.i2d.json"
    save_project([d], f)
    (d2,) = load_project(f)
    assert [s.name for s in d2.series] == ["Series 1", "B"]
    assert d2.calibration.handles["x2"] == [110, 90]
    assert d2.series[1].points == [[20, 20]]


def test_export_formats(tmp_path):
    d = make_doc(tmp_path)
    d.current.points += [[60, 50], [110, 10]]
    d.add_series("B").points.append([10, 90])
    long = build_frame([d])
    assert list(long.columns) == ["image", "series", "x", "y"]
    assert len(long) == 3
    wide = build_frame([d], wide=True, include_pixels=True)
    assert "B x" in wide.columns and len(wide) == 2 and math.isnan(wide["B x"][1])
    for ext in ("csv", "tsv", "json", "xlsx", "html", "md", "txt"):
        write_frame(long, tmp_path / f"out.{ext}")
        assert (tmp_path / f"out.{ext}").stat().st_size > 0
    assert to_markdown(long).startswith("| image |")
    with pytest.raises(ValueError):
        write_frame(long, tmp_path / "out.xyz")


def test_extract_sources():
    split = lambda s: tuple(s.split())  # noqa: E731
    assert dropping.extract_sources('<img src="http://a/b.png?x=1&amp;y=2">', split) == [
        "http://a/b.png?x=1&y=2"]
    assert dropping.extract_sources("C:/a.png C:/b.png", split) == ["C:/a.png", "C:/b.png"]
    assert dropping.extract_sources("  ", split) == []


def test_resolve_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(dropping, "CACHE_DIR", tmp_path / "cache")
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(img)
    assert dropping.resolve_source(str(img)) == [img]
    assert dropping.resolve_source(str(tmp_path)) == [img]
    uri = "data:image/png;base64," + __import__("base64").b64encode(img.read_bytes()).decode()
    (p,) = dropping.resolve_source(uri)
    assert p.exists() and p.parent == tmp_path / "cache"
    with pytest.raises(FileNotFoundError):
        dropping.resolve_source(str(tmp_path / "missing.png"))

def test_shared_x_unified_frame():
    from img2data.export import build_frame
    from img2data.model import ImageDocument
    import math
    doc = ImageDocument("x.png")
    doc.calibration.handles.update(x1=[0, 0], x2=[100, 0], y1=[0, 0], y2=[0, 100])
    doc.calibration.values.update(x1=0, x2=100, y1=0, y2=100)
    doc.shared_x = True
    doc.series[0].points = [[10, 10], [30, 30]]
    s2 = doc.add_series()
    s2.points = [[doc.grid_x(1, 10.5), 50]]
    s2.points.append([doc.grid_x(1, 12), 60])
    assert s2.points[1][0] == 30
    s2.points[1] = [20, 60]
    assert s2.points[0][0] == 10
    assert doc.x_locked(1, 0) and not doc.x_locked(1, 1)
    doc.move_point(1, 0, 99, 70)
    assert s2.points[0] == [10, 70]
    doc.move_point(0, 0, 12, 10)
    assert s2.points[0][0] == 12
    df = build_frame([doc])
    assert list(df.columns) == ["x", "Series 1", "Series 2"]
    assert list(df["x"]) == [12, 20, 30]
    assert math.isnan(df["Series 1"][1]) and math.isnan(df["Series 2"][2])
