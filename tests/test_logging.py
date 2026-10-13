import logging

from img2data.logging_setup import build_parser, resolve_level, setup_logging


def test_cli_levels():
    p = build_parser()
    assert resolve_level(p.parse_args([])) == "info"
    assert resolve_level(p.parse_args(["-v"])) == "debug"
    assert resolve_level(p.parse_args(["-q"])) == "error"
    assert resolve_level(p.parse_args(["-l", "WARNING", "a.png"])) == "warning"


def test_files_include_higher_levels(tmp_path):
    setup_logging("info", tmp_path)
    log = logging.getLogger("t")
    log.debug("d-msg")
    log.info("i-msg")
    log.error("e-msg")
    for h in logging.getLogger().handlers:
        h.flush()
    read = lambda n: (tmp_path / f"{n}.log").read_text()  # noqa: E731
    assert not (tmp_path / "debug.log").exists()
    assert "i-msg" in read("info") and "e-msg" in read("info") and "d-msg" not in read("info")
    assert "i-msg" not in read("error") and "e-msg" in read("error")
    logging.getLogger().handlers.clear()
