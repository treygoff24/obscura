"""App-level configuration — project root path, first-launch setup."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys


@dataclasses.dataclass
class AppConfig:
    """Application-level settings stored in .config.json."""

    project_root: str | None
    config_dir: pathlib.Path

    @classmethod
    def default(cls, config_dir: pathlib.Path) -> AppConfig:
        return cls(project_root=None, config_dir=config_dir)


def _config_path(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / ".config.json"


def default_config_dir() -> pathlib.Path:
    """Return the platform-appropriate config directory."""
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "Obscura"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(pathlib.Path.home())
        return pathlib.Path(base) / "Obscura"
    return pathlib.Path.home() / ".config" / "obscura"


def save_config(config: AppConfig) -> None:
    path = _config_path(config.config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"project_root": config.project_root}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_config(config_dir: pathlib.Path) -> AppConfig:
    path = _config_path(config_dir)
    if not path.exists():
        return AppConfig.default(config_dir=config_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig(
        project_root=data.get("project_root"),
        config_dir=config_dir,
    )
