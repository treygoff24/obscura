"""Tests for __main__.py routing and app.launch() entrypoint."""

import sys
import types

from obscura.config import AppConfig


class TestMainRouting:
    """Verify __main__.main() dispatches to CLI or app correctly."""

    def test_cli_only_env_bypasses_app(self, monkeypatch):
        import obscura.cli as cli
        from obscura import __main__ as main_mod

        invoked = []
        monkeypatch.setattr(cli, "main", lambda: invoked.append("cli"))
        monkeypatch.setenv("OBSCURA_CLI_ONLY", "1")
        monkeypatch.setattr(sys, "argv", ["obscura"])

        main_mod.main()
        assert invoked == ["cli"]

    def test_args_invoke_cli(self, monkeypatch):
        import obscura.cli as cli
        from obscura import __main__ as main_mod

        invoked = []
        monkeypatch.setattr(cli, "main", lambda: invoked.append("cli"))
        monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
        monkeypatch.setattr(sys, "argv", ["obscura", "list"])

        main_mod.main()
        assert invoked == ["cli"]

    def test_no_args_launches_app(self, monkeypatch):
        from obscura import __main__ as main_mod

        invoked = []

        module = types.ModuleType("obscura.app")
        module.launch = lambda: invoked.append("app")
        monkeypatch.setitem(sys.modules, "obscura.app", module)
        monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
        monkeypatch.setattr(sys, "argv", ["obscura"])

        main_mod.main()
        assert invoked == ["app"]

    def test_missing_app_falls_back_to_cli(self, monkeypatch):
        import obscura.cli as cli
        from obscura import __main__ as main_mod

        invoked = []
        monkeypatch.setattr(cli, "main", lambda: invoked.append("cli"))

        module = types.ModuleType("obscura.app")
        monkeypatch.setitem(sys.modules, "obscura.app", module)
        monkeypatch.delenv("OBSCURA_CLI_ONLY", raising=False)
        monkeypatch.setattr(sys, "argv", ["obscura"])

        main_mod.main()
        assert invoked == ["cli"]


class TestAppLaunch:
    """Verify app.launch() wires up webview correctly."""

    def test_launch_creates_window_and_starts(self, monkeypatch, tmp_dir):
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

    def test_launch_handles_missing_project_root(self, monkeypatch, tmp_dir):
        """When config.project_root points to a nonexistent dir, launch still works."""
        calls = {}

        class DummyWindow:
            pass

        def create_window(title, url, js_api, width, height, min_size):
            calls["js_api"] = js_api
            return DummyWindow()

        def start():
            calls["started"] = True

        dummy_webview = types.SimpleNamespace(create_window=create_window, start=start)
        monkeypatch.setitem(sys.modules, "webview", dummy_webview)

        if "obscura.app" in sys.modules:
            del sys.modules["obscura.app"]

        import obscura.app as app

        config = AppConfig(
            project_root=str(tmp_dir / "nonexistent"),
            config_dir=tmp_dir,
        )
        monkeypatch.setattr(app, "default_config_dir", lambda: tmp_dir)
        monkeypatch.setattr(app, "load_config", lambda config_dir: config)

        app.launch()

        assert calls["started"] is True
        assert calls["js_api"]._root is None
