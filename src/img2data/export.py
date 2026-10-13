"""Turn documents into pandas DataFrames and write them in various formats."""

from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd

from img2data.model import ImageDocument

log = logging.getLogger(__name__)

FILETYPES = [
    ("CSV", "*.csv"),
    ("TSV", "*.tsv"),
    ("JSON", "*.json"),
    ("Excel", "*.xlsx"),
    ("HTML", "*.html"),
    ("Markdown", "*.md"),
    ("Text (tab separated)", "*.txt"),
]


def long_frame(docs: list[ImageDocument], include_pixels: bool = False) -> pd.DataFrame:
    cols = ["image", "series", "x", "y"] + (["px", "py"] if include_pixels else [])
    rows = []
    for d in docs:
        for s in d.series:
            for (px, py), data in zip(s.points, d.data_for(s)):
                x, y = data if data else (math.nan, math.nan)
                row = {"image": d.name, "series": s.name, "x": x, "y": y}
                if include_pixels:
                    row.update(px=px, py=py)
                rows.append(row)
    return pd.DataFrame(rows, columns=cols)


def wide_frame(docs: list[ImageDocument], include_pixels: bool = False) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    used: dict[str, int] = {}
    for d in docs:
        for s in d.series:
            prefix = s.name if len(docs) == 1 else f"{d.name}:{s.name}"
            used[prefix] = used.get(prefix, 0) + 1
            if used[prefix] > 1:
                prefix = f"{prefix} ({used[prefix]})"
            data = [t if t else (math.nan, math.nan) for t in d.data_for(s)]
            cols = {f"{prefix} x": [t[0] for t in data], f"{prefix} y": [t[1] for t in data]}
            if include_pixels:
                cols[f"{prefix} px"] = [p[0] for p in s.points]
                cols[f"{prefix} py"] = [p[1] for p in s.points]
            parts.append(pd.DataFrame(cols))
    return pd.concat(parts, axis=1) if parts else pd.DataFrame()


def build_frame(docs: list[ImageDocument], wide: bool = False,
                include_pixels: bool = False) -> pd.DataFrame:
    return (wide_frame if wide else long_frame)(docs, include_pixels)


def to_markdown(df: pd.DataFrame) -> str:
    cells = [[str(c) for c in df.columns]]
    cells += [["" if pd.isna(v) else str(v) for v in row] for row in df.itertuples(index=False)]
    lines = ["| " + " | ".join(r) + " |" for r in cells]
    lines.insert(1, "| " + " | ".join("---" for _ in df.columns) + " |")
    return "\n".join(lines) + "\n"


def to_clipboard_text(df: pd.DataFrame) -> str:
    return df.to_csv(sep="\t", index=False)


def write_frame(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    ext = path.suffix.lower()
    log.info("exporting %d rows x %d cols to %s", len(df), len(df.columns), path)
    if ext == ".csv":
        df.to_csv(path, index=False)
    elif ext in (".tsv", ".txt"):
        df.to_csv(path, index=False, sep="\t")
    elif ext == ".json":
        df.to_json(path, orient="records", indent=2)
    elif ext == ".xlsx":
        df.to_excel(path, index=False)
    elif ext in (".html", ".htm"):
        df.to_html(path, index=False)
    elif ext == ".md":
        path.write_text(to_markdown(df), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported export format: {ext or '(none)'}")
