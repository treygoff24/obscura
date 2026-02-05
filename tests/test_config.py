"""Tests for app-level configuration."""

import json

import pytest

from obscura.config import AppConfig, load_config, save_config


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
