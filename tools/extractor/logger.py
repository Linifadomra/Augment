"""
extractor/logger.py

Lightweight structured logger for the extractor pipeline.

Usage:
    from extractor.logger import get_logger
    log = get_logger(__name__)
    log.info("Starting walk")
    log.warning("Skipped %s", path)
    log.error("Fatal in %s: %s", path, exc)

The log level and optional file sink are configured once at startup via
configure(), which extract.py calls before spawning workers.  Worker
processes inherit the configuration because configure() writes to a
module-level dict that each spawned process re-imports.

By default (enabled=False) all output is suppressed via a NullHandler
nothing reaches stderr or disk unless --log-file or --verbose is passed.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Optional

_lock        = threading.Lock()
_initialized = False
_log_file: Optional[Path] = None


def configure(
    level: str = "WARNING",
    log_file: Optional[str] = None,
    verbose: bool = False,
    enabled: bool = True,
) -> None:
    """
    Call once from the main process before any workers are spawned.

    Args:
        level:    Root log level string: DEBUG / INFO / WARNING / ERROR.
                  Overridden to DEBUG when *verbose* is True.
        log_file: If given, all records are also written to this path
                  (appended, UTF-8).  The file is created if it does not exist.
        verbose:  Shorthand for level="DEBUG".
        enabled:  If False, installs a NullHandler and returns. 
                  Callers should pass
                  enabled=bool(log_file or verbose) so that a plain cmake
                  build produces zero logger noise.
    """
    global _initialized, _log_file

    with _lock:
        if _initialized:
            return

        root = logging.getLogger("extractor")
        root.handlers.clear()

        if not enabled:
            root.addHandler(logging.NullHandler())
            root.propagate = False
            _initialized = True
            return

        effective_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.WARNING)
        root.setLevel(effective_level)

        fmt = logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )

        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)

        if log_file:
            _log_file = Path(log_file)
            _log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(_log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)

        _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the 'extractor' namespace.

    If configure() has not been called yet (e.g. inside a worker process
    that was spawned before configure() ran), a NullHandler is attached so
    callers never see 'No handlers could be found' warnings.
    """
    logger = logging.getLogger(f"extractor.{name}")

    if not logging.getLogger("extractor").handlers:
        logging.getLogger("extractor").addHandler(logging.NullHandler())

    return logger
