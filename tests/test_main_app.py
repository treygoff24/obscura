"""Tests for app and module entrypoints."""

import sys
import types

from obscura.config import AppConfig


def test_main_cli_only_env(monkeypatch):
    import obscura.cli as cli
    from obscura import __main__ as main_mod

    called = {"count": 0}

    def fake_main():
        called["count"] += 1

    monkeypatch.setattr(cli, "main", fake_main)
    monkeypatch.setenv("OBSCURA_CLI_ONLY", "1")
    monkeypatch.setattr(sys, "argv", ["obscura"])

    main_mod.main()
    assert called["count"] == 1


def test_main_with_args_invokes_cli(monkeypatch):
    import obscura.cli as cli
    from obscura import __main__ as main_mod

    called = {"count": 0}

    def fake_main():
        called["count"] += 1

    monkeypatch.setattr(cli, "main", fake_main)
    monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
    monkeypatch.setattr(sys, "argv", ["obscura", "list"])

    main_mod.main()
    assert called["count"] == 1


def test_main_launches_app_when_available(monkeypatch):
    from obscura import __main__ as main_mod

    called = {"count": 0}

    def fake_launch():
        called["count"] += 1

    module = types.ModuleType("obscura.app")
    module.launch = fake_launch
    monkeypatch.setitem(sys.modules, "obscura.app", module)
    monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
    monkeypatch.setattr(sys, "argv", ["obscura"])

    main_mod.main()
    assert called["count"] == 1


def test_main_falls_back_to_cli_on_import_error(monkeypatch):
    import obscura.cli as cli
    from obscura import __main__ as main_mod

    called = {"count": 0}

    def fake_cli():
        called["count"] += 1

    module = types.ModuleType("obscura.app")
    # No launch attribute -> ImportError in `from obscura.app import launch`
    monkeypatch.setitem(sys.modules, "obscura.app", module)
    monkeypatch.setattr(cli, "main", fake_cli)
    monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
    monkeypatch.setattr(sys, "argv", ["obscura"])

    main_mod.main()
    assert called["count"] == 1


def test_app_launch(monkeypatch, tmp_dir):
    calls = {}

    class DummyWindow:
        pass

    def create_window(title, url, js_api, width, height, min_size):
        calls["title"] = title
        calls["url"] = url
        calls["js_api"] = js_api
        calls["width"] = width
        calls["height"] = height
        calls["min_size"] = min_size
        return DummyWindow()

    def start():
        calls["started"] = True

    dummy_webview = types.SimpleNamespace(create_window=create_window, start=start)
    monkeypatch.setitem(sys.modules, "webview", dummy_webview)

    if "obscura.app" in sys.modules:
        del sys.modules["obscura.app"]

    import obscura.app as app

    project_root = tmp_dir / "Projects"
    project_root.mkdir()
    config = AppConfig(project_root=str(project_root), config_dir=tmp_dir)

    monkeypatch.setattr(app, "default_config_dir", lambda: tmp_dir)
    monkeypatch.setattr(app, "load_config", lambda config_dir: config)

    app.launch()

    assert calls["title"] == "Obscura"
    assert calls["started"] is True
    assert "ui" in calls["url"]
