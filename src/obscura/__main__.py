"""Allow running as `python -m obscura`."""

import logging
import os
import pathlib
import sys
from logging.handlers import RotatingFileHandler

from obscura.runtime import configure_ocr_runtime

logger = logging.getLogger(__name__)


def _setup_logging() -> pathlib.Path | None:
    """Configure logging to both stderr and a rotating log file.

    Returns the log file path, or None if file logging could not be set up.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console: warnings and above only
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(console)

    # File: everything (debug+), rotating 5MB x 3 files
    if sys.platform == "darwin":
        log_dir = pathlib.Path.home() / "Library" / "Logs" / "Obscura"
    else:
        log_dir = pathlib.Path.home() / ".local" / "share" / "Obscura" / "logs"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "obscura.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(file_handler)
        return log_file
    except OSError:
        root_logger.warning("Could not create log directory: %s", log_dir)
        return None


def main():
    log_file = _setup_logging()
    if log_file:
        logger.info("Obscura starting — log file: %s", log_file)

    # Store log path for the API to expose to the UI
    os.environ["OBSCURA_LOG_FILE"] = str(log_file) if log_file else ""

    tessdata_dir = configure_ocr_runtime()
    if tessdata_dir is None:
        logger.warning("No tessdata directory found; OCR will be unavailable")

    if len(sys.argv) > 1 or os.environ.get("OBSCURA_CLI_ONLY") == "1":
        from obscura.cli import main as cli_main
        cli_main()
    else:
        try:
            from obscura.app import launch
            launch()
        except ImportError:
            from obscura.cli import main as cli_main
            cli_main()


if __name__ == "__main__":
    main()
