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