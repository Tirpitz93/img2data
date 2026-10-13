"""Resolve drag & drop / paste payloads (files, URLs, HTML, data URIs) to image files."""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

log = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
CACHE_DIR = Path.home() / ".img2data" / "images"
_IMG_SRC = re.compile(r"""<img[^>]+src\s*=\s*["']([^"']+)["']""", re.I)
_HTML_ENTITIES = {"&amp;": "&", "&quot;": '"', "&#39;": "'", "&lt;": "<", "&gt;": ">"}


def _unescape(s: str) -> str:
    for k, v in _HTML_ENTITIES.items():
        s = s.replace(k, v)
    return s


def extract_sources(data: str, splitlist: Callable[[str], tuple[str, ...]]) -> list[str]:
    """Split a drop payload into candidate sources (paths, URLs, data URIs)."""
    data = data.strip()
    log.debug("drop payload: %.200r", data)
    if not data:
        return []
    if data.startswith("<") or "<img" in data.lower():
        return [_unescape(m) for m in _IMG_SRC.findall(data)]
    if data.startswith("data:"):
        return [data]
    try:
        items = list(splitlist(data))
    except Exception:
        items = data.splitlines()
    return [i.strip() for i in items if i.strip()]


def expand_dir(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def _cache_path(key: str, ext: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}{ext}"


def save_bytes(content: bytes, key: str, ext: str = ".png") -> Path:
    p = _cache_path(key, ext)
    p.write_bytes(content)
    return p


def _download(url: str) -> Path:
    import requests

    log.info("downloading %s", url)
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 img2data"})
    r.raise_for_status()
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in IMAGE_EXTS:
        ext = mimetypes.guess_extension(r.headers.get("content-type", "").split(";")[0]) or ".png"
    return save_bytes(r.content, url, ext)


def _from_data_uri(uri: str) -> Path:
    header, _, payload = uri.partition(",")
    raw = base64.b64decode(payload) if ";base64" in header else unquote(payload).encode("latin-1")
    ext = mimetypes.guess_extension(header[5:].split(";")[0]) or ".png"
    return save_bytes(raw, uri[:200] + str(len(uri)), ext)


def resolve_source(src: str) -> list[Path]:
    """Turn one source into local image paths (downloading if necessary)."""
    log.debug("resolving source %.120s", src)
    if src.startswith("data:"):
        return [_from_data_uri(src)]
    if re.match(r"https?://", src, re.I):
        return [_download(src)]
    if src.lower().startswith("file:"):
        src = url2pathname(urlparse(src).path)
        if re.match(r"^/[A-Za-z]:", src):
            src = src[1:]
    p = Path(src)
    if p.is_dir():
        return expand_dir(p)
    if p.is_file():
        return [p]
    raise FileNotFoundError(src)
