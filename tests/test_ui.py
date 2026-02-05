"""Playwright UI tests for the Obscura three-screen SPA.

Tests the actual JS/DOM behavior via a local HTTP server with a mock
pywebview API bridge injected before each test.
"""

from __future__ import annotations

import pytest
from tests.conftest import build_mock_js

pytestmark = pytest.mark.ui


# =========================================================================== #
# Screen 1 — Project List
# =========================================================================== #


def test_shows_root_prompt_when_no_root(ui_server, page):
    """When list_projects returns needs_root, the root prompt is visible."""
    page.goto(ui_server + "/index.html")
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: true, projects: []}))'
    )
    page.evaluate(mock)
    prompt = page.locator("#root-prompt")
    prompt.wait_for(state="visible", timeout=5000)
    assert prompt.is_visible()
    assert "Select a Project Folder" in prompt.locator("h2").text_content()


def test_shows_project_cards(ui_page):
    """Two project cards are rendered with correct names."""
    cards = ui_page.locator(".project-card")
    cards.first.wait_for(state="visible", timeout=3000)
    assert cards.count() == 2
    assert "Matter A" in cards.nth(0).locator("h3").text_content()
    assert "Matter B" in cards.nth(1).locator("h3").text_content()


def test_new_project_calls_api(ui_server, page):
    """Clicking New Project with prompt override calls create_project."""
    page.goto(ui_server + "/index.html")

    mock = build_mock_js() + """
    window._createCalled = false;
    window.pywebview.api.create_project = function() {
        window._createCalled = true;
        return Promise.resolve(JSON.stringify({name: "Test Project", path: "/tmp/obscura/Test Project"}));
    };
    """
    page.evaluate(mock)
    page.wait_for_selector(".project-card", timeout=3000)

    # Override both prompts used by the New Project handler
    page.evaluate("""
        var _promptCount = 0;
        window.prompt = function(msg, def_) {
            _promptCount++;
            if (_promptCount === 1) return 'Test Project';
            return def_ || 'eng';
        };
    """)
    page.click("#new-project-btn")

    page.wait_for_function("window._createCalled === true", timeout=3000)
    assert page.evaluate("window._createCalled") is True


# =========================================================================== #
# Screen 2 — Workspace
# =========================================================================== #


def test_navigates_to_workspace_on_card_click(ui_page):
    """Clicking a project card shows the workspace screen."""
    ui_page.locator(".project-card").first.click()
    workspace = ui_page.locator("#screen-workspace")
    workspace.wait_for(state="visible", timeout=3000)
    assert workspace.is_visible()
    assert "Matter A" in ui_page.locator("#workspace-title").text_content()


def test_keywords_editor_loads_content(ui_page):
    """Keywords textarea is populated after opening a project."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_function(
        "document.getElementById('keywords-editor').value.length > 0",
        timeout=3000,
    )
    value = ui_page.locator("#keywords-editor").input_value()
    assert "confidential" in value
    assert "secret" in value


def test_keyword_validation_shows_errors(ui_server, page):
    """Typing an invalid regex shows validation errors."""
    page.goto(ui_server + "/index.html")
    mock = build_mock_js(
        validate_keywords="""function(content) {
            if (content && content.includes('regex:[invalid')) {
                return Promise.resolve(JSON.stringify({
                    valid: false,
                    errors: [{line: 1, error: "Invalid regex: missing ]"}]
                }));
            }
            return Promise.resolve(JSON.stringify({valid: true, errors: []}));
        }"""
    )
    page.evaluate(mock)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    editor = page.locator("#keywords-editor")
    editor.fill("regex:[invalid")
    editor.dispatch_event("input")

    errors = page.locator("#keyword-errors")
    errors.wait_for(state="visible", timeout=5000)
    assert "Invalid regex" in errors.inner_text()


def test_keyword_autosave(ui_page):
    """After typing in the editor, autosave fires and shows 'Saved'."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    ui_page.evaluate("""
        window._saveCalls = [];
        const _origSave = window.pywebview.api.save_keywords;
        window.pywebview.api.save_keywords = (name, content) => {
            window._saveCalls.push({name, content});
            return _origSave(name, content);
        };
    """)

    editor = ui_page.locator("#keywords-editor")
    editor.fill("newkeyword")
    editor.dispatch_event("input")

    # Autosave timer is 600ms, then async save + "Saved" text
    ui_page.wait_for_function(
        "document.getElementById('save-indicator').textContent === 'Saved'",
        timeout=5000,
    )
    assert ui_page.locator("#save-indicator").text_content() == "Saved"


def test_file_list_renders_with_status(ui_page):
    """File list shows file names and status pills."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    assert rows.count() == 2

    first_name = rows.nth(0).locator(".file-name").text_content()
    assert "contract.pdf" in first_name

    pills = ui_page.locator(".file-row .status-pill")
    assert pills.count() >= 2


def test_run_button_disables_during_run(ui_page):
    """Run button disables and spinner shows while running."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Make run_project slow so we can catch the disabled state
    ui_page.evaluate("""
        window.pywebview.api.run_project = (name, deep, dpi) => {
            return new Promise(resolve => {
                setTimeout(() => {
                    resolve(JSON.stringify({
                        files_processed: 3, total_redactions: 12,
                        files_needing_review: 1, report_path: null
                    }));
                }, 500);
            });
        };
    """)

    run_btn = ui_page.locator("#run-btn")
    run_btn.click()

    assert run_btn.is_disabled()
    assert not ui_page.locator("#run-spinner").evaluate("el => el.classList.contains('hidden')")

    # Wait for run to complete
    ui_page.wait_for_function(
        "!document.getElementById('run-btn').disabled",
        timeout=5000,
    )
    assert not ui_page.locator("#run-summary").evaluate("el => el.classList.contains('hidden')")


def test_language_selector_updates(ui_page):
    """Changing language dropdown updates the workspace language badge."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # The mock update_project_settings returns the language we send
    ui_page.locator("#language-select").select_option("spa")

    # The change handler calls update_project_settings then updates the badge
    ui_page.wait_for_function(
        "document.getElementById('workspace-language').textContent === 'spa'",
        timeout=3000,
    )
    assert ui_page.locator("#workspace-language").text_content() == "spa"


def test_deep_verify_toggle_shows_dpi(ui_page):
    """Checking deep verify checkbox reveals the DPI row."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    dpi_row = ui_page.locator("#dpi-row")
    assert dpi_row.evaluate("el => el.classList.contains('hidden')")

    ui_page.locator("#deep-verify-check").check()
    assert not dpi_row.evaluate("el => el.classList.contains('hidden')")


# =========================================================================== #
# Screen 3 — Report Detail
# =========================================================================== #


def test_file_click_opens_report(ui_page):
    """Clicking a file row opens the report detail screen."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    rows.nth(1).click()  # memo.pdf — has residual matches

    report_screen = ui_page.locator("#screen-report")
    report_screen.wait_for(state="visible", timeout=3000)
    assert report_screen.is_visible()
    assert "memo.pdf" in ui_page.locator("#report-title").text_content()


def test_residual_matches_table(ui_page):
    """Report detail shows residual matches in table rows."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    rows.nth(1).click()  # memo.pdf
    ui_page.wait_for_selector("#screen-report.active", timeout=3000)

    residual_section = ui_page.locator("#report-residual")
    assert not residual_section.evaluate("el => el.classList.contains('hidden')")

    table_rows = ui_page.locator("#residual-table tbody tr")
    assert table_rows.count() == 2
    assert "confidential" in table_rows.first.text_content()


def test_report_shows_low_confidence_and_unreadable(ui_page):
    """Report detail shows low confidence and unreadable page badges."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    rows.nth(1).click()  # memo.pdf
    ui_page.wait_for_selector("#screen-report.active", timeout=3000)

    lowconf = ui_page.locator("#report-lowconf")
    assert not lowconf.evaluate("el => el.classList.contains('hidden')")
    assert lowconf.locator(".page-badge.warn").count() >= 1

    unreadable = ui_page.locator("#report-unreadable")
    assert not unreadable.evaluate("el => el.classList.contains('hidden')")
    assert unreadable.locator(".page-badge.danger").count() >= 1


def test_back_to_workspace(ui_page):
    """Back button from report returns to workspace."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.locator(".file-row").first.wait_for(state="visible", timeout=3000)
    ui_page.locator(".file-row").first.click()
    ui_page.wait_for_selector("#screen-report.active", timeout=3000)

    ui_page.click("#back-to-workspace")
    workspace = ui_page.locator("#screen-workspace")
    workspace.wait_for(state="visible", timeout=3000)
    assert workspace.is_visible()


def test_back_to_projects(ui_page):
    """Back button from workspace returns to project list."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    ui_page.click("#back-to-projects")
    projects = ui_page.locator("#screen-projects")
    projects.wait_for(state="visible", timeout=3000)
    assert projects.is_visible()
