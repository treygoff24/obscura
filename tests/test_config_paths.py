"""Tests for config directory resolution across platforms."""

import os
import pathlib
import sys

from obscura.config import default_config_dir


def test_default_config_dir_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    path = default_config_dir()
    assert str(path).endswith("Library/Application Support/Obscura")


def test_default_config_dir_windows_with_appdata(monkeypatch, tmp_dir):
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_dir))
    path = default_config_dir()
    assert path == pathlib.Path(str(tmp_dir)) / "Obscura"


def test_default_config_dir_windows_without_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    path = default_config_dir()
    assert path.name == "Obscura"


def test_default_config_dir_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    path = default_config_dir()
    assert str(path).endswith(os.path.join(".config", "obscura"))
