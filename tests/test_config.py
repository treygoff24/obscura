"""Tests for app-level configuration and platform config directory resolution."""

import json
import os
import pathlib
import sys

import pytest

from obscura.config import AppConfig, default_config_dir, load_config, save_config


class TestAppConfig:
    def test_default_config(self, tmp_dir):
        config = AppConfig.default(config_dir=tmp_dir)
        assert config.project_root is None

    def test_save_and_load(self, tmp_dir):
        config = AppConfig(project_root="/some/path", config_dir=tmp_dir)
        save_config(config)

        loaded = load_config(config_dir=tmp_dir)
        assert loaded.project_root == "/some/path"

    def test_load_missing_returns_default(self, tmp_dir):
        config = load_config(config_dir=tmp_dir)
        assert config.project_root is None

    def test_save_creates_file(self, tmp_dir):
        config = AppConfig(project_root="/test", config_dir=tmp_dir)
        save_config(config)
        assert (tmp_dir / ".config.json").exists()

    def test_load_corrupt_json_raises(self, tmp_dir):
        (tmp_dir / ".config.json").write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_config(config_dir=tmp_dir)

    def test_load_missing_keys_returns_none(self, tmp_dir):
        (tmp_dir / ".config.json").write_text("{}", encoding="utf-8")
        config = load_config(config_dir=tmp_dir)
        assert config.project_root is None

    def test_save_overwrites_existing(self, tmp_dir):
        config1 = AppConfig(project_root="/first", config_dir=tmp_dir)
        save_config(config1)
        config2 = AppConfig(project_root="/second", config_dir=tmp_dir)
        save_config(config2)
        loaded = load_config(config_dir=tmp_dir)
        assert loaded.project_root == "/second"


class TestDefaultConfigDir:
    """Platform-specific config directory resolution (moved from test_config_paths.py)."""

    def test_darwin(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin", raising=False)
        path = default_config_dir()
        assert str(path).endswith("Library/Application Support/Obscura")

    def test_windows_with_appdata(self, monkeypatch, tmp_dir):
        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        monkeypatch.setenv("APPDATA", str(tmp_dir))
        path = default_config_dir()
        assert path == pathlib.Path(str(tmp_dir)) / "Obscura"

    def test_windows_without_appdata(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        path = default_config_dir()
        assert path.name == "Obscura"

    def test_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux", raising=False)
        path = default_config_dir()
        assert str(path).endswith(os.path.join(".config", "obscura"))
