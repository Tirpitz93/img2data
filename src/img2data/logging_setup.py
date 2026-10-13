"""Logging setup: one file per level, each including all more-severe levels."""

from __future__ import annotations

import argparse
import faulthandler
import logging
import sys
import threading
from pathlib import Path

LEVELS = ["debug", "info", "warning", "error", "critical"]
FORMAT = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s"
_fault_file = None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="img2data", description="Extract data from plot images")
    p.add_argument("images", nargs="*", help="images or project files to open")
    p.add_argument("-l", "--log-level", choices=LEVELS, type=str.lower,
                   help="highest verbosity: files are written for this level and every "
                        "more-severe one; this level is also shown on the console (default: info)")
    p.add_argument("-v", "--verbose", action="store_true", help="shortcut for --log-level debug")
    p.add_argument("-q", "--quiet", action="store_true", help="shortcut for --log-level error")
    p.add_argument("--log-dir", default="logs", help="directory for log files (default: ./logs)")
    return p


def resolve_level(args: argparse.Namespace) -> str:
    if args.log_level:
        return args.log_level
    return "debug" if args.verbose else "error" if args.quiet else "info"


def setup_logging(level: str = "info", log_dir: str | Path = "logs") -> Path:
    """Create `<log_dir>/<level>.log` for each level from `level` up to critical.

    `debug.log` contains everything, `info.log` info and above, and so on. The chosen level
    is also streamed to the console. Returns the log directory.
    """
    global _fault_file
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(FORMAT)
    chosen = LEVELS.index(level)
    for name in LEVELS[chosen:]:
        h = logging.FileHandler(log_dir / f"{name}.log", mode="w", encoding="utf-8")
        h.setLevel(getattr(logging, name.upper()))
        h.setFormatter(fmt)
        root.addHandler(h)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, level.upper()))
    console.setFormatter(fmt)
    root.addHandler(console)
    logging.getLogger("PIL").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    log = logging.getLogger("img2data")

    def excepthook(et, ev, tb):
        log.critical("Unhandled exception", exc_info=(et, ev, tb))

    def thread_hook(a):
        log.critical("Unhandled exception in thread %s", a.thread, exc_info=a.exc_info)

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    if _fault_file is None:  # hard crashes (segfaults) leave a traceback here
        _fault_file = open(log_dir / "fatal.log", "w")
        faulthandler.enable(_fault_file)
    log.info("Logging started: level=%s dir=%s", level, log_dir.resolve())
    return log_dir
