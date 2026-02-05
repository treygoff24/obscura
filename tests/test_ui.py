"""Playwright UI tests for the Obscura three-screen SPA.

Tests the actual JS/DOM behavior via a local HTTP server with a mock
pywebview API bridge injected before each test.
"""

from __future__ import annotations

import pytest
from tests.conftest import FIRE_EVENT_JS, build_mock_js

pytestmark = pytest.mark.ui


# =========================================================================== #
# Screen 1 — Project List
# =========================================================================== #


def test_shows_root_prompt_when_no_root(ui_server, page):
    """When list_projects returns needs_root, the root prompt is visible."""
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: true, projects: []}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
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
    mock = build_mock_js(fire_event=False) + """
    window._createCalled = false;
    window.pywebview.api.create_project = function() {
        window._createCalled = true;
        return Promise.resolve(JSON.stringify({name: "Test Project", path: "/tmp/obscura/Test Project"}));
    };
    """
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
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
    mock = build_mock_js(
        validate_keywords="""function(content) {
            if (content && content.includes('regex:[invalid')) {
                return Promise.resolve(JSON.stringify({
                    valid: false,
                    errors: [{line: 1, error: "Invalid regex: missing ]"}]
                }));
            }
            return Promise.resolve(JSON.stringify({valid: true, errors: []}));
        }""",
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
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
        window._savedSeen = false;
        const _saveEl = document.getElementById('save-indicator');
        const _obs = new MutationObserver(() => {
            if (_saveEl.textContent === 'Saved') window._savedSeen = true;
        });
        _obs.observe(_saveEl, {childList: true, characterData: true, subtree: true});
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
        "window._saveCalls.length > 0",
        timeout=5000,
    )
    ui_page.wait_for_function(
        "window._savedSeen === true || document.getElementById('save-indicator').textContent === ''",
        timeout=5000,
    )
    assert ui_page.evaluate("window._savedSeen") is True


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

    ui_page.wait_for_function(
        "document.getElementById('run-btn').disabled === true",
        timeout=3000,
    )
    ui_page.wait_for_function(
        "!document.getElementById('run-spinner').classList.contains('hidden')",
        timeout=3000,
    )

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


# =========================================================================== #
# Additional UI/UX coverage
# =========================================================================== #


def test_empty_project_list(ui_server, page):
    """If no projects exist, empty state renders."""
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: false, projects: []}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)

    empty = page.locator("#project-list-body .empty-state")
    empty.wait_for(state="visible", timeout=3000)
    assert "No projects yet" in empty.text_content()


def test_select_root_error_alert(ui_server, page):
    """Select root failure shows an alert."""
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: true, projects: []}))',
        select_project_root='() => Promise.reject(new Error("nope"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)

    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    page.click("#select-root-btn")
    page.wait_for_function("true", timeout=1000)  # yield for dialog handler
    assert any("Failed to select project folder" in m for m in messages)


def test_create_project_error_alert(ui_server, page):
    """Create project failures surface via alert."""
    mock = build_mock_js(
        create_project='() => Promise.reject(new Error("boom"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.evaluate("""
        var _promptCount = 0;
        window.prompt = function(msg, def_) {
            _promptCount++;
            if (_promptCount === 1) return 'Bad Project';
            return def_ || 'eng';
        };
    """)

    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    page.click("#new-project-btn")
    page.wait_for_function("true", timeout=1000)
    assert any("Failed to create project" in m for m in messages)


def test_save_keywords_error_indicator(ui_server, page):
    """Save keyword failure should show Error indicator."""
    mock = build_mock_js(
        save_keywords='() => Promise.reject(new Error("fail"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    editor = page.locator("#keywords-editor")
    editor.fill("confidential")
    editor.dispatch_event("input")
    page.wait_for_function(
        "document.getElementById('save-indicator').textContent === 'Error'",
        timeout=5000,
    )
    assert page.locator("#save-indicator").text_content() == "Error"


def test_run_project_error_alert(ui_server, page):
    """Run failures surface via alert."""
    mock = build_mock_js(
        run_project='() => Promise.reject(new Error("run failed"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    page.click("#run-btn")
    page.wait_for_function("true", timeout=1000)
    assert any("Run failed" in m for m in messages)


def test_add_files_error_alert(ui_server, page):
    """Add files failure shows alert."""
    mock = build_mock_js(
        add_files='() => Promise.reject(new Error("fail add"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
    page.click("#add-files-btn")
    page.wait_for_function("true", timeout=1000)
    assert any("Failed to add files" in m for m in messages)


def test_no_files_empty_state(ui_server, page):
    """No input files should show empty state message."""
    mock = build_mock_js(
        list_files='() => Promise.resolve(JSON.stringify({files: []}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    empty = page.locator(".empty-state")
    empty.wait_for(state="visible", timeout=3000)
    assert "No input files yet" in empty.text_content()


def test_report_sections_hidden_when_clean(ui_server, page):
    """Clean report hides residual/lowconf/unreadable and shows clean pages."""
    mock = build_mock_js(
        get_latest_report="""() => Promise.resolve(JSON.stringify({
            schema_version: 1,
            files: [{
                file: "clean.pdf", status: "clean", redactions_applied: 0,
                residual_matches: [], low_confidence_pages: [], unreadable_pages: [],
                clean_pages: [1, 2], language: "eng", confidence_threshold: 70,
                deep_verify: false, timestamp: "2026-01-15T10:00:00Z"
            }]
        }))""",
        list_files="""() => Promise.resolve(JSON.stringify({
            files: [{file: "clean.pdf", status: "clean", redactions_applied: 0}]
        }))""",
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.locator(".file-row").first.click()
    page.wait_for_selector("#screen-report.active", timeout=3000)

    assert page.locator("#report-residual").evaluate("el => el.classList.contains('hidden')")
    assert page.locator("#report-lowconf").evaluate("el => el.classList.contains('hidden')")
    assert page.locator("#report-unreadable").evaluate("el => el.classList.contains('hidden')")
    assert not page.locator("#report-clean").evaluate("el => el.classList.contains('hidden')")


def test_report_metadata_values(ui_page):
    """Metadata panel shows expected values."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.locator(".file-row").nth(1).click()  # memo.pdf
    ui_page.wait_for_selector("#screen-report.active", timeout=3000)

    assert ui_page.locator("#meta-redactions").text_content() == "7"
    assert "Yes (300 DPI)" in ui_page.locator("#meta-deepverify").text_content()
    assert ui_page.locator("#meta-language").text_content() == "eng"
    assert ui_page.locator("#meta-threshold").text_content() == "70%"
    assert "2026" in ui_page.locator("#meta-timestamp").text_content()


def test_file_report_fallback_when_missing_report(ui_server, page):
    """If a file isn't in the latest report, the file entry still opens."""
    mock = build_mock_js(
        get_latest_report='() => Promise.resolve(JSON.stringify({schema_version: 1, files: []}))',
        list_files='() => Promise.resolve(JSON.stringify({files: [{file: "orphan.pdf", status: "not_run"}]}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.locator(".file-row").first.click()
    page.wait_for_selector("#screen-report.active", timeout=3000)

    assert "orphan.pdf" in page.locator("#report-title").text_content()
    assert "not run" in page.locator("#report-status").text_content()
    assert page.locator("#meta-redactions").text_content() == "--"
    assert page.locator("#meta-language").text_content() == "--"
    assert page.locator("#meta-threshold").text_content() == "--"
    assert page.locator("#meta-timestamp").text_content() == "Never"


def test_open_preview_and_reveal_errors(ui_server, page):
    """Preview/reveal failures surface via alerts."""
    mock = build_mock_js(
        open_in_preview='() => Promise.reject(new Error("open fail"))',
        reveal_in_finder='() => Promise.reject(new Error("reveal fail"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.locator(".file-row").first.click()
    page.wait_for_selector("#screen-report.active", timeout=3000)

    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))

    page.click("#open-preview-btn")
    page.wait_for_function("true", timeout=1000)
    assert any("Could not open file" in m for m in messages)

    page.click("#reveal-finder-btn")
    page.wait_for_function("true", timeout=1000)
    assert any("Could not reveal file" in m for m in messages)


def test_keyboard_run_triggers(ui_page):
    """Enter on focused Run button triggers the action."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    ui_page.evaluate("""
        window._runCalled = false;
        window.pywebview.api.run_project = () => {
            window._runCalled = true;
            return Promise.resolve(JSON.stringify({
                files_processed: 1, total_redactions: 0, files_needing_review: 0, report_path: null
            }));
        };
    """)

    ui_page.locator("#run-btn").focus()
    ui_page.keyboard.press("Enter")
    ui_page.wait_for_function("window._runCalled === true", timeout=3000)
    assert ui_page.evaluate("window._runCalled") is True


def test_keyboard_back_to_projects(ui_page):
    """Enter on Back button returns to projects screen."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.locator("#back-to-projects").focus()
    ui_page.keyboard.press("Enter")
    ui_page.wait_for_selector("#screen-projects.active", timeout=3000)
