"""Desktop app launcher using pywebview."""

from __future__ import annotations

import pathlib

import webview

from obscura.api import ObscuraAPI
from obscura.config import load_config, save_config, AppConfig


def _get_project_root() -> pathlib.Path:
    default_dir = pathlib.Path.home() / "Obscura"
    config = load_config(config_dir=default_dir)

    if config.project_root:
        root = pathlib.Path(config.project_root)
        if root.exists():
            return root

    result = webview.windows[0].create_file_dialog(
        webview.FOLDER_DIALOG,
        directory=str(pathlib.Path.home()),
    )

    if result and result[0]:
        chosen = pathlib.Path(result[0])
    else:
        chosen = default_dir

    chosen.mkdir(parents=True, exist_ok=True)
    config = AppConfig(project_root=str(chosen), config_dir=chosen)
    save_config(config)
    return chosen


def launch() -> None:
    """Launch the Obscura desktop application."""
    html_dir = pathlib.Path(__file__).parent / "ui"
    index_html = html_dir / "index.html"

    default_root = pathlib.Path.home() / "Obscura"
    default_root.mkdir(parents=True, exist_ok=True)

    config = load_config(config_dir=default_root)
    project_root = pathlib.Path(config.project_root) if config.project_root else default_root

    api = ObscuraAPI(project_root=project_root)

    window = webview.create_window(
        "Obscura",
        url=str(index_html) if index_html.exists() else None,
        js_api=api,
        width=1200,
        height=800,
        min_size=(800, 600),
    )

    webview.start()
