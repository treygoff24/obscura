"""Runtime helpers for packaged and source executions."""

from __future__ import annotations

import os
import pathlib
import sys

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

    # Deduplicate while preserving order.
    seen: set[pathlib.Path] = set()
    unique: list[pathlib.Path] = []
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def configure_ocr_runtime(languages: tuple[str, ...] = ("eng",)) -> pathlib.Path | None:
    """Set TESSDATA_PREFIX to a valid directory when possible.

    Returns:
        The selected tessdata directory, or None if none was found.
    """
    for path in _candidate_tessdata_dirs():
        if _has_language_data(path, languages):
            os.environ["TESSDATA_PREFIX"] = str(path)
            return path
    return None
