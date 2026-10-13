# img2data – plan

Reverse-engineer numeric data from images of plots. ttkbootstrap/tkinter GUI.

## Stack
ttkbootstrap (UI), Pillow (images), pandas (tables/export), tkinterdnd2 (drag & drop), requests (URL drops from browsers), pytest.

## Package layout (`src/img2data`)
| Module | Responsibility |
|---|---|
| `calibration.py` | Pure maths: `AxisCalibration` (2 reference pixels ↔ 2 values, linear/log) and `Calibration` (x+y) → pixel↔data conversion. |
| `model.py` | `Series`, `ImageDocument` (image path, calibration, series, active series). Data stored in *pixel* coordinates so recalibration re-maps all points. JSON project save/load. |
| `export.py` | Build pandas DataFrames (long and wide form) and write csv, tsv, json, xlsx, html, markdown, latex, clipboard. |
| `dropping.py` | Parse drop payloads (file lists, URLs, data URIs) → PIL images / local paths; clipboard image paste. |
| `canvas.py` | `PlotCanvas`: zoom (wheel, centred on cursor), pan (middle/right drag or space+drag), drag handles, nudge, loupe. |
| `app.py` | Main window: Notebook tab per image, side panel (calibration, series, point table, tools), menu, status bar. |

## Interaction design
- **Modes** (toolbar / keys): Pan `1`, Calibrate `2`, Add points `3`, Select/Edit `4`.
- **Calibration**: four draggable handles (X1, X2 on the x axis, Y1, Y2 on the y axis). Each handle has a value entry and the axis a linear/log toggle. Handles are placed by click in calibrate mode (sequentially) and are draggable afterwards.
- **Series**: multiple named series with colours; click in add mode to append a point; drag to move; right-click/Delete to remove.
- **Precision tools**
  - Arrow keys nudge selected point/handle by 1 image px; Shift = 10 px; Alt = 0.1 px (sub-pixel).
  - Nudge step spin box and on-screen D-pad buttons.
  - Loupe (magnifier) window following the cursor / selected item, with crosshair.
  - Zoom to 3200 %, crosshair cursor, axis guide lines through handles.
  - Edit selected point's data X/Y numerically in the point table (back-computes pixels).
  - Undo/redo (Ctrl+Z / Ctrl+Y) per tab.
  - Optional snap-to-axis-guide for x or y while dragging (Ctrl held = lock to horizontal/vertical).
- **Tabs**: one per image; close button, rename via title. Open via menu, drag & drop (files, folders, browser images/URLs), or paste (Ctrl+V).
- **Export**: current tab or all tabs; csv, tsv, json, xlsx, html, markdown, latex, copy to clipboard; long format (`image, series, x, y`) or wide format.
- **Projects**: save/load `.i2d.json` project holding image path (+ embedded fallback path), calibration, series.

## Testing
pytest on calibration maths (linear/log, round trip), model (recalibration, undo), export formats, drop-payload parsing.

## Milestones
1. Project scaffold + dependencies ✔
2. calibration / model / export / dropping with tests
3. PlotCanvas
4. App shell, tabs, panels, menus
5. Smoke test (headless creation + scripted interactions)

## Future ideas (NOT implemented)
Automatic initial processing:
- Detect plot area / axes lines (Hough transform / long straight-line detection, or projections of dark-pixel histograms).
- Detect tick marks along the axes and propose reference points.
- OCR tick labels (Tesseract / EasyOCR) to propose axis values and detect log scaling from the spacing ratios.
- Detect axis titles/units and legends via OCR.
- Series extraction by colour: pick a colour → mask → trace curve (centre-line per column) or detect markers (blob detection) and propose points for review.
- Detect legend entries and map colours to series names.
- Grid-line detection to refine calibration; automatic skew/rotation correction (deskew) and perspective correction for photographed plots.
- Bar chart, error bar and scatter-marker specific extractors.
- Snap-to-curve: refine a clicked point to the local colour/edge centroid.
- Support rotated axes, polar and ternary plots; date axes.
- Light ML model (e.g. a pretrained chart-derendering model) for first-pass extraction.
