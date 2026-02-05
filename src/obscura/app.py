"""Desktop app launcher using pywebview."""

from __future__ import annotations

import pathlib

import webview

from obscura.api import ObscuraAPI
from obscura.config import default_config_dir, load_config


def launch() -> None:
    """Launch the Obscura desktop application."""
    html_dir = pathlib.Path(__file__).parent / "ui"
    index_html = html_dir / "index.html"

    config_dir = default_config_dir()
    config = load_config(config_dir=config_dir)
    project_root = pathlib.Path(config.project_root) if config.project_root else None
    if project_root and not project_root.exists():
        project_root = None

    api = ObscuraAPI(project_root=project_root, config_dir=config_dir)

    window = webview.create_window(
        "Obscura",
        url=str(index_html) if index_html.exists() else None,
        js_api=api,
        width=1200,
        height=800,
        min_size=(800, 600),
    )
    api.attach_window(window)

    webview.start()
