# img2data

Reverse-engineer data from images of plots. See `PLAN.md` for design and future ideas.

    uv sync
    uv run python -m img2data [image ...]
    uv run pytest

- Open images via File → Open, drag & drop (Explorer or browser), or Ctrl+V.
- **Calibrate (2)**: place X1/X2/Y1/Y2 handles, type their values (optional log axes). Use the
  *Set* buttons or Shift-click to place a handle on top of another (e.g. at the origin).
- **Add points (3)**: click to add; drag to move. Arrows nudge (Shift ×10, Ctrl ×0.1, step is
  configurable), Ctrl-drag locks an axis, the loupe shows pixels around the point.
- Export csv/tsv/json/xlsx/html/md/txt (long or wide), copy to clipboard, save/load projects.

## Image preprocessing

Run `uv run python pre_process.py [image ...]` to open the applet with zero or
more images, or select multiple images using **File → Open Images**. Each image
opens in its own tab.

The background filter (`FilterGreenScreen`) is disabled by default; enable it to preview
a foreground mask for the object closest to the image center. For another background
colour, select **Sample background from image**, then click a background pixel in the
preview. The original image pixel is sampled, not the overlay. Each tab keeps its own
sample; use **Reset to green thresholds** to remove it. Escape cancels sampling.
Adjust **Sample Colour Tolerance (Lab)** to include similar colours: it is the maximum
per-channel difference in OpenCV's 8-bit Lab space. With a sample, the HSV bounds are
ignored. Without one, the original green HSV thresholds apply; a hue minimum greater
than the maximum selects a range wrapping around hue zero. Cleanup, minimum area and
dilation still apply in both modes. The histogram shows OpenCV hue values (0–179), not
colour distance or mask values. Invert mask flips the preview mask. A single colour
may not isolate varied backgrounds or foreground regions with similar colours. The
applet does not currently export SfM mask files.
Click the brightness or focus histogram to set its threshold; the red line marks the
current slider value.
The focus filter's dilation and erosion sliders use pixel radii on the thresholded
mask; dilation is applied first, followed by erosion and then optional inversion.
Both default to zero, leaving the mask unchanged. Use the sidebar scrollbar to
reach controls when the expanded filters do not fit in the window.
Previews cache the resized base image, overlay layers, and image-only histograms.
Disabled filters do not run; re-enabling a filter restores its preview while reusing
any cached image metrics.

To diagnose slow filter updates, set `IMG2DATA_FILTER_TIMING=1` in the
`pre_process.py` run configuration and inspect the PyCharm console. For example, in
PowerShell run `$env:IMG2DATA_FILTER_TIMING = "1"; uv run python pre_process.py`.
The timing lines report UI redraw and overlay costs, worker queue, histogram and mask
times, and focus metric cache hits; durations are milliseconds. Worker versions allow
submission, computation and result logs to be correlated.

## Logging
Logs go to `./logs` (`--log-dir`): `debug.log`, `info.log`, `warning.log`, `error.log`,
`critical.log` — each contains its own level and everything more severe (so `debug.log` has
everything). Only files from the chosen level upward are written, and that level is also echoed
to the console. `fatal.log` captures hard crashes (faulthandler).
```bash
python -m img2data -v                 # debug
python -m img2data -l warning a.png   # choose level
python -m img2data -q                 # errors only
```