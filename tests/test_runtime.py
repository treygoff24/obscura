"""Tests for runtime OCR environment bootstrapping."""

from __future__ import annotations

import os
import pathlib

from obscura import runtime


def _write_traineddata(dir_path: pathlib.Path, languages: tuple[str, ...]) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for lang in languages:
        (dir_path / f"{lang}.traineddata").write_bytes(b"dummy")


class TestParseTesseractLanguages:
    def test_single_language(self):
        assert runtime.parse_tesseract_languages("eng") == ("eng",)

    def test_multiple_languages(self):
        assert runtime.parse_tesseract_languages("eng+spa") == ("eng", "spa")

    def test_whitespace_around_plus(self):
        assert runtime.parse_tesseract_languages(" eng + spa ") == ("eng", "spa")

    def test_empty_string_defaults_to_eng(self):
        assert runtime.parse_tesseract_languages("") == ("eng",)

    def test_none_defaults_to_eng(self):
        assert runtime.parse_tesseract_languages(None) == ("eng",)

    def test_whitespace_only_defaults_to_eng(self):
        assert runtime.parse_tesseract_languages("   ") == ("eng",)

    def test_plus_only_defaults_to_eng(self):
        assert runtime.parse_tesseract_languages("+") == ("eng",)

    def test_trailing_plus(self):
        assert runtime.parse_tesseract_languages("eng+") == ("eng",)


class TestHasLanguageData:
    def test_valid_dir_with_all_languages(self, tmp_dir):
        tessdata = tmp_dir / "tessdata"
        _write_traineddata(tessdata, ("eng", "spa"))
        assert runtime._has_language_data(tessdata, ("eng", "spa")) is True

    def test_missing_language_file(self, tmp_dir):
        tessdata = tmp_dir / "tessdata"
        _write_traineddata(tessdata, ("eng",))
        assert runtime._has_language_data(tessdata, ("eng", "spa")) is False

    def test_nonexistent_dir(self, tmp_dir):
        assert runtime._has_language_data(tmp_dir / "nope", ("eng",)) is False

    def test_path_is_file_not_dir(self, tmp_dir):
        file_path = tmp_dir / "not_a_dir"
        file_path.write_text("", encoding="utf-8")
        assert runtime._has_language_data(file_path, ("eng",)) is False


class TestCandidateTessdataDirs:
    def test_includes_meipass_bundled(self, monkeypatch, tmp_dir):
        bundle_root = tmp_dir / "bundle"
        monkeypatch.setattr(runtime.sys, "_MEIPASS", str(bundle_root), raising=False)
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)

        dirs = runtime._candidate_tessdata_dirs()
        assert bundle_root / "obscura" / "tessdata" in dirs
        assert bundle_root / "tessdata" in dirs

    def test_includes_env_prefix(self, monkeypatch, tmp_dir):
        monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_dir / "custom"))
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        dirs = runtime._candidate_tessdata_dirs()
        assert tmp_dir / "custom" in dirs

    def test_empty_env_prefix_excluded(self, monkeypatch, tmp_dir):
        monkeypatch.setenv("TESSDATA_PREFIX", "")
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        dirs = runtime._candidate_tessdata_dirs()
        for d in dirs:
            assert str(d) != ""

    def test_symlink_dedup(self, monkeypatch, tmp_dir):
        """Two candidates that resolve to the same directory via symlink are deduplicated."""
        real_dir = tmp_dir / "real_tessdata"
        real_dir.mkdir()
        link_dir = tmp_dir / "link_tessdata"
        link_dir.symlink_to(real_dir)

        monkeypatch.setenv("TESSDATA_PREFIX", str(real_dir))
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (link_dir,))
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        dirs = runtime._candidate_tessdata_dirs()
        resolved_dirs = [d.resolve() for d in dirs]
        assert resolved_dirs.count(real_dir.resolve()) == 1

    def test_no_meipass_attribute(self, monkeypatch, tmp_dir):
        """When sys._MEIPASS doesn't exist (normal Python), bundled paths are excluded."""
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        dirs = runtime._candidate_tessdata_dirs()
        for d in dirs:
            assert "bundle" not in str(d)


class TestConfigureOcrRuntime:
    def test_uses_existing_env(self, monkeypatch, tmp_dir):
        tessdata = tmp_dir / "tessdata"
        _write_traineddata(tessdata, ("eng",))

        monkeypatch.setenv("TESSDATA_PREFIX", str(tessdata))
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected == tessdata

    def test_prefers_bundled_over_invalid_env(self, monkeypatch, tmp_dir):
        bundle_root = tmp_dir / "bundle"
        bundled = bundle_root / "obscura" / "tessdata"
        _write_traineddata(bundled, ("eng",))

        monkeypatch.setattr(runtime.sys, "_MEIPASS", str(bundle_root), raising=False)
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", ())
        monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_dir / "missing"))

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected == bundled
        assert os.environ["TESSDATA_PREFIX"] == str(bundled)

    def test_returns_none_when_no_valid_candidate(self, monkeypatch, tmp_dir):
        empty = tmp_dir / "empty"
        empty.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (empty,))
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        monkeypatch.setattr(runtime.sys, "_MEIPASS", str(tmp_dir / "missing_bundle"), raising=False)

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected is None

    def test_empty_env_prefix_falls_through(self, monkeypatch, tmp_dir):
        """TESSDATA_PREFIX='' should be treated as unset."""
        system_dir = tmp_dir / "system_tessdata"
        _write_traineddata(system_dir, ("eng",))

        monkeypatch.setenv("TESSDATA_PREFIX", "")
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (system_dir,))
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected == system_dir

    def test_all_candidates_missing(self, monkeypatch, tmp_dir):
        """When every candidate path does not exist, returns None."""
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (
            tmp_dir / "a",
            tmp_dir / "b",
            tmp_dir / "c",
        ))
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected is None

    def test_selects_first_valid_candidate(self, monkeypatch, tmp_dir):
        """When multiple valid candidates exist, the first one wins."""
        first = tmp_dir / "first"
        second = tmp_dir / "second"
        _write_traineddata(first, ("eng",))
        _write_traineddata(second, ("eng",))

        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        monkeypatch.setattr(runtime, "SYSTEM_TESSDATA_DIRS", (first, second))
        if hasattr(runtime.sys, "_MEIPASS"):
            monkeypatch.delattr(runtime.sys, "_MEIPASS")

        selected = runtime.configure_ocr_runtime(("eng",))
        assert selected == first
        assert os.environ["TESSDATA_PREFIX"] == str(first)
