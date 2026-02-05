"""Tests for runtime OCR environment bootstrapping."""

from __future__ import annotations

import os
import pathlib

from obscura import runtime


def _write_traineddata(dir_path: pathlib.Path, languages: tuple[str, ...]) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for lang in languages:
        (dir_path / f"{lang}.traineddata").write_bytes(b"dummy")


def test_parse_tesseract_languages():
    assert runtime.parse_tesseract_languages("eng+spa") == ("eng", "spa")
    assert runtime.parse_tesseract_languages(" eng + spa ") == ("eng", "spa")
    assert runtime.parse_tesseract_languages("") == ("eng",)
    assert runtime.parse_tesseract_languages(None) == ("eng",)


def test_configure_ocr_runtime_uses_existing_env(monkeypatch, tmp_dir):
    tessdata = tmp_dir / "tessdata"
    _write_traineddata(tessdata, ("eng",))

    monkeypatch.setenv("TESSDATA_PREFIX", str(tessdata))
    monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())

    selected = runtime.configure_ocr_runtime(("eng",))
    assert selected == tessdata


def test_candidate_tessdata_dirs_includes_meipass(monkeypatch, tmp_dir):
    bundle_root = tmp_dir / "bundle"
    monkeypatch.setattr(runtime.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)

    dirs = runtime._candidate_tessdata_dirs()
    assert bundle_root / "obscura" / "tessdata" in dirs


def test_configure_ocr_runtime_prefers_bundled_tessdata(monkeypatch, tmp_dir):
    bundle_root = tmp_dir / "bundle"
    bundled = bundle_root / "obscura" / "tessdata"
    _write_traineddata(bundled, ("eng",))

    monkeypatch.setattr(runtime.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_dir / "missing"))

    selected = runtime.configure_ocr_runtime(("eng",))
    assert selected == bundled
    assert os.environ["TESSDATA_PREFIX"] == str(bundled)


def test_configure_ocr_runtime_returns_none_when_missing(monkeypatch, tmp_dir):
    empty = tmp_dir / "empty"
    empty.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (empty,))
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setattr(runtime.sys, "_MEIPASS", str(tmp_dir / "missing_bundle"), raising=False)

    selected = runtime.configure_ocr_runtime(("eng",))
    assert selected is None
