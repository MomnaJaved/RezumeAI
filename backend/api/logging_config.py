"""File + console logging under the ``rezume`` logger namespace."""
from __future__ import annotations

import logging
from pathlib import Path

from api.paths import repo_root


def setup_logging(log_dir: Path | None = None) -> None:
    root_path = repo_root()
    log_dir = log_dir or (root_path / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)

    rez = logging.getLogger("rezume")
    rez.handlers.clear()
    rez.setLevel(logging.INFO)
    rez.addHandler(fh)
    rez.addHandler(ch)
    rez.propagate = False
