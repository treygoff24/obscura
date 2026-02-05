"""Runtime helpers for packaged and source executions."""

from __future__ import annotations

import logging
import os
import pathlib
import sys

logger = logging.getLogger(__name__)

SYSTEM_TESSDATA_DIRS = (
    pathlib.Path("/opt/homebrew/share/tessdata"),
    pathlib.Path("/usr/local/share/tessdata"),
    pathlib.Path("/usr/share/tesseract-ocr/5/tessdata"),
)


def parse_tesseract_languages(language: str | None) -> tuple[str, ...]:
    """Normalize a Tesseract language string into language codes."""
    if not language:
        return ("eng",)
    parts = [part.strip() for part in language.split("+")]
    cleaned = tuple(part for part in parts if part)
    return cleaned or ("eng",)


def _has_language_data(tessdata_dir: pathlib.Path, languages: tuple[str, ...]) -> bool:
    if not tessdata_dir.exists() or not tessdata_dir.is_dir():
        return False
    return all((tessdata_dir / f"{lang}.traineddata").exists() for lang in languages)


def _available_languages(
    tessdata_dir: pathlib.Path, languages: tuple[str, ...]
) -> tuple[str, ...]:
    """Return the subset of *languages* that have traineddata files in *tessdata_dir*."""
    if not tessdata_dir.exists() or not tessdata_dir.is_dir():
        return ()
    return tuple(lang for lang in languages if (tessdata_dir / f"{lang}.traineddata").exists())


def _candidate_tessdata_dirs() -> list[pathlib.Path]:
    """Return tessdata locations in preference order."""
    candidates: list[pathlib.Path] = []

    current = os.environ.get("TESSDATA_PREFIX")
    if current:
        candidates.append(pathlib.Path(current))

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = pathlib.Path(meipass)
        candidates.append(base / "obscura" / "tessdata")
        candidates.append(base / "tessdata")

    package_dir = pathlib.Path(__file__).resolve().parent
    candidates.append(package_dir / "tessdata")

    candidates.extend(SYSTEM_TESSDATA_DIRS)

    # Deduplicate while preserving order (always resolve to catch symlinks).
    seen: set[pathlib.Path] = set()
    unique: list[pathlib.Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def configure_ocr_runtime(languages: tuple[str, ...] = ("eng",)) -> pathlib.Path | None:
    """Set TESSDATA_PREFIX to a valid directory when possible.

    Prefers a directory with all requested languages. Falls back to the
    directory with the most available languages and logs a warning about
    the missing ones.

    Returns:
        The selected tessdata directory, or None if none was found.
    """
    candidates = _candidate_tessdata_dirs()

    # First pass: exact match (all languages present).
    for path in candidates:
        if _has_language_data(path, languages):
            os.environ["TESSDATA_PREFIX"] = str(path)
            logger.debug("Selected tessdata directory: %s", path)
            return path

    # Second pass: partial match — pick directory with most coverage.
    best_path: pathlib.Path | None = None
    best_available: tuple[str, ...] = ()
    for path in candidates:
        available = _available_languages(path, languages)
        if len(available) > len(best_available):
            best_path = path
            best_available = available

    if best_path is not None and best_available:
        missing = tuple(lang for lang in languages if lang not in best_available)
        logger.warning(
            "Tessdata directory %s is missing language data for: %s",
            best_path,
            ", ".join(missing),
        )
        os.environ["TESSDATA_PREFIX"] = str(best_path)
        logger.debug("Selected tessdata directory (partial): %s", best_path)
        return best_path

    logger.warning("No tessdata directory found with data for any of: %s", ", ".join(languages))
    return None
