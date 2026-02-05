"""Shared test fixtures for Obscura test suite."""

from __future__ import annotations

import functools
import os
import pathlib
import shutil
import tempfile
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "src" / "obscura" / "ui"


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="obscura_test_")
    yield pathlib.Path(d)
    shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Playwright UI fixtures
# --------------------------------------------------------------------------- #

MOCK_API_JS = """
window.pywebview = { api: {
    list_projects: () => Promise.resolve(JSON.stringify({
        needs_root: false,
        projects: [
            {name: "Matter A", last_run: "2026-01-15T10:00:00Z", language: "eng", confidence_threshold: 70},
            {name: "Matter B", last_run: null, language: "spa", confidence_threshold: 80}
        ]
    })),
    select_project_root: () => Promise.resolve(JSON.stringify({status: "ok", root: "/tmp/obscura"})),
    create_project: (name, lang) => Promise.resolve(JSON.stringify({name: name, path: "/tmp/obscura/" + name})),
    run_project: (name, deep, dpi) => Promise.resolve(JSON.stringify({
        files_processed: 3, total_redactions: 12, files_needing_review: 1, report_path: null
    })),
    get_latest_report: (name) => Promise.resolve(JSON.stringify({
        schema_version: 1,
        files: [
            {
                file: "contract.pdf", status: "clean", redactions_applied: 5,
                residual_matches: [], low_confidence_pages: [], unreadable_pages: [],
                clean_pages: [1, 2, 3], language: "eng", confidence_threshold: 70,
                deep_verify: false, timestamp: "2026-01-15T10:00:00Z"
            },
            {
                file: "memo.pdf", status: "needs_review", redactions_applied: 7,
                residual_matches: [
                    {keyword: "confidential", page: 2, source: "standard"},
                    {keyword: "secret", page: 4, source: "ocr"}
                ],
                low_confidence_pages: [3],
                unreadable_pages: [5],
                unverified_warning: "Page 5 was not OCR-readable.",
                clean_pages: [1], language: "eng", confidence_threshold: 70,
                deep_verify: true, deep_verify_dpi: 300,
                timestamp: "2026-01-15T10:05:00Z"
            }
        ]
    })),
    get_keywords: (name) => Promise.resolve("confidential\\nsecret\\nregex:\\\\b\\\\d{3}-\\\\d{2}-\\\\d{4}\\\\b\\n"),
    get_project_settings: (name) => Promise.resolve(JSON.stringify({language: "eng", confidence_threshold: 70})),
    save_keywords: (name, content) => Promise.resolve(JSON.stringify({status: "ok"})),
    validate_keywords: (content) => Promise.resolve(JSON.stringify({valid: true, errors: []})),
    list_files: (name) => Promise.resolve(JSON.stringify({
        files: [
            {file: "contract.pdf", status: "clean", redactions_applied: 5},
            {file: "memo.pdf", status: "needs_review", redactions_applied: 7}
        ]
    })),
    add_files: (name, paths) => Promise.resolve(JSON.stringify({status: "ok", added: ["new.pdf"], skipped: []})),
    update_project_settings: (name, lang, thresh) => Promise.resolve(JSON.stringify({
        status: "ok", language: lang || "eng", confidence_threshold: thresh || 70
    })),
    open_in_preview: (name, filename) => Promise.resolve(JSON.stringify({status: "ok"})),
    reveal_in_finder: (name, filename) => Promise.resolve(JSON.stringify({status: "ok"}))
}};
"""

FIRE_EVENT_JS = "window.dispatchEvent(new Event('pywebviewready'));"

DEFAULT_MOCK_JS = MOCK_API_JS + FIRE_EVENT_JS


def build_mock_js(*, fire_event: bool = True, **overrides: str) -> str:
    """Build mock JS with selective method overrides applied BEFORE pywebviewready fires.

    Each override value should be a JS expression for the method body, e.g.:
        build_mock_js(list_projects='() => Promise.resolve(...)')
    """
    if not overrides:
        return DEFAULT_MOCK_JS if fire_event else MOCK_API_JS
    parts = [MOCK_API_JS.rstrip()]
    for method, body in overrides.items():
        parts.append(f"window.pywebview.api.{method} = {body};")
    if fire_event:
        parts.append(FIRE_EVENT_JS)
    return "\n".join(parts)


def _playwright_browser_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            return bool(path and os.path.exists(path))
    except Exception:
        return False


def pytest_addoption(parser):
    parser.addoption(
        "--ui",
        action="store_true",
        default=False,
        help="Run Playwright UI tests (requires browsers installed).",
    )


def pytest_collection_modifyitems(config, items):
    run_ui = config.getoption("--ui") or os.environ.get("OBSCURA_UI") == "1"
    if run_ui:
        if _playwright_browser_installed():
            return
        reason = "Playwright browsers not installed. Run `python -m playwright install`."
    else:
        reason = "UI tests skipped. Pass --ui or set OBSCURA_UI=1."
    skip_ui = pytest.mark.skip(reason=reason)
    for item in items:
        if "ui" in item.keywords:
            item.add_marker(skip_ui)


@pytest.fixture(scope="session")
def ui_server():
    """Start a local HTTP server serving the UI directory."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(UI_DIR))
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def ui_page(ui_server, page):
    """Navigate to the UI and inject the default mock pywebview bridge."""
    page.add_init_script(build_mock_js(fire_event=False))
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(
        ".project-card, .empty-state, .root-prompt:not(.hidden)", timeout=5000
    )
    return page
