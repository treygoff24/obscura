"""Playwright UI tests for the Obscura four-screen SPA.

Tests the actual JS/DOM behavior via a local HTTP server with a mock
pywebview API bridge injected before each test.

Screens: Welcome -> Project List -> Workspace (stepper: Keywords/Files/Run) -> Report
"""

from __future__ import annotations

import json

import pytest
from tests.conftest import FIRE_EVENT_JS, build_mock_js

pytestmark = pytest.mark.ui


# =========================================================================== #
# Screen 1 — Welcome / Screen 2 — Project List
# =========================================================================== #


def test_shows_welcome_screen_when_no_root(ui_server, page):
    """When list_projects returns needs_root, the welcome screen is shown."""
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: true, projects: []}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    # Skip welcome to projects, then fire event so loadProjects runs and
    # detects needs_root, which navigates back to welcome
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    welcome = page.locator("#screen-welcome")
    welcome.wait_for(state="visible", timeout=5000)
    assert welcome.is_visible()
    assert page.locator("#get-started-btn").is_visible()


def test_shows_project_cards(ui_page):
    """Two project cards are rendered with correct names."""
    cards = ui_page.locator(".project-card")
    cards.first.wait_for(state="visible", timeout=3000)
    assert cards.count() == 2
    assert "Matter A" in cards.nth(0).locator(".card-title").text_content()
    assert "Matter B" in cards.nth(1).locator(".card-title").text_content()
    assert cards.nth(0).evaluate("el => el.tagName") == "BUTTON"


def test_new_project_calls_api(ui_server, page):
    """Clicking New Project opens modal; filling and submitting calls create_project."""
    mock = build_mock_js(fire_event=False) + """
    window._createCalled = false;
    window.pywebview.api.create_project = function() {
        window._createCalled = true;
        return Promise.resolve(JSON.stringify({name: "Test Project", path: "/tmp/obscura/Test Project"}));
    };
    """
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    # Bypass welcome screen
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    # Click New Project to open modal
    page.click("#new-project-btn")
    page.wait_for_selector("#modal-new-project:not(.hidden)", timeout=3000)

    # Fill in the modal form
    page.fill("#modal-project-name", "Test Project")
    page.click("#modal-create-btn")

    page.wait_for_function("window._createCalled === true", timeout=3000)
    assert page.evaluate("window._createCalled") is True


def test_change_project_root_reloads_projects(ui_server, page):
    """Change Project Folder calls selection API and reloads project list."""
    mock = build_mock_js(fire_event=False) + """
    window._selectCalls = 0;
    window._listCalls = 0;
    window.pywebview.api.select_project_root = function() {
        window._selectCalls += 1;
        return Promise.resolve(JSON.stringify({status: "ok", root: "/tmp/obscura-new"}));
    };
    window.pywebview.api.list_projects = function() {
        window._listCalls += 1;
        return Promise.resolve(JSON.stringify({
            needs_root: false,
            projects: [{name: "Reselected Matter", last_run: null, language: "eng", confidence_threshold: 70}]
        }));
    };
    """
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.click("#change-project-root-btn")
    page.wait_for_function("window._selectCalls === 1", timeout=3000)
    page.wait_for_function("window._listCalls >= 2", timeout=3000)

    card_title = page.locator(".project-card .card-title").first
    card_title.wait_for(state="visible", timeout=3000)
    assert "Reselected Matter" in card_title.text_content()

    toast = page.locator(".toast")
    toast.wait_for(state="visible", timeout=3000)
    assert "Project folder updated." in toast.first.text_content()


# =========================================================================== #
# Screen 3 — Workspace (Stepper: Keywords / Files / Run)
# =========================================================================== #


def test_navigates_to_workspace_on_card_click(ui_page):
    """Clicking a project card shows the workspace screen."""
    ui_page.locator(".project-card").first.click()
    workspace = ui_page.locator("#screen-workspace")
    workspace.wait_for(state="visible", timeout=3000)
    assert workspace.is_visible()
    assert "Matter A" in ui_page.locator("#workspace-title").text_content()


def test_no_external_fonts(ui_page):
    """UI should not load external fonts."""
    assert ui_page.evaluate("""
        () => document.querySelector('link[href*="fonts.googleapis.com"]') === null
    """)


def test_keywords_editor_has_label(ui_page):
    """Keywords editor should have a programmatic label."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    assert ui_page.evaluate("""
        () => document.querySelector('label[for="keywords-editor"]') !== null
    """)


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
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
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

    # Navigate to the files step
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)

    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    assert rows.count() == 2

    first_name = rows.nth(0).locator(".file-name").text_content()
    assert "contract.pdf" in first_name

    pills = ui_page.locator(".file-row .status-pill")
    assert pills.count() >= 2
    assert rows.nth(0).evaluate("el => el.tagName") == "BUTTON"


def test_files_step_scrolls_with_many_files(ui_server, page):
    """Files step should scroll when file list exceeds viewport height."""
    files = [
        {"file": f"file-{idx:03}.pdf", "status": "not_run", "redactions_applied": 0}
        for idx in range(1, 121)
    ]
    mock = build_mock_js(
        list_files='() => Promise.resolve(JSON.stringify({files: ' + json.dumps(files) + "}))",
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    metrics = page.evaluate("""
        () => {
            const panel = document.getElementById('step-files');
            const before = panel.scrollTop;
            panel.scrollTop = panel.scrollHeight;
            return {
                overflowY: getComputedStyle(panel).overflowY,
                canOverflow: panel.scrollHeight > panel.clientHeight,
                didScroll: panel.scrollTop > before,
            };
        }
    """)
    assert metrics["overflowY"] in ("auto", "scroll")
    assert metrics["canOverflow"] is True
    assert metrics["didScroll"] is True


def test_run_button_disables_during_run(ui_page):
    """Run button disables and progress bar shows while running."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the run step
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

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
        "!document.getElementById('run-progress').classList.contains('hidden')",
        timeout=3000,
    )

    # Wait for run to complete
    ui_page.wait_for_function(
        "!document.getElementById('run-btn').disabled",
        timeout=5000,
    )
    assert not ui_page.locator("#run-summary").evaluate("el => el.classList.contains('hidden')")


def test_language_selector_updates(ui_page):
    """Changing language dropdown calls update_project_settings."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the run step where settings live
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

    # Open the Settings details panel
    ui_page.locator("#step-run details.advanced-section summary").click()

    # Track update_project_settings calls
    ui_page.evaluate("""
        window._settingsUpdated = false;
        var _origUpdate = window.pywebview.api.update_project_settings;
        window.pywebview.api.update_project_settings = function(name, lang, thresh) {
            window._settingsUpdated = lang;
            return _origUpdate(name, lang, thresh);
        };
    """)

    ui_page.locator("#language-select").select_option("spa")

    ui_page.wait_for_function("window._settingsUpdated === 'spa'", timeout=3000)
    assert ui_page.evaluate("window._settingsUpdated") == "spa"


def test_deep_verify_toggle_shows_dpi(ui_page):
    """Checking deep verify checkbox reveals the DPI row."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the run step where settings live
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

    # Open the Settings details panel
    ui_page.locator("#step-run details.advanced-section summary").click()

    dpi_row = ui_page.locator("#dpi-row")
    assert dpi_row.evaluate("el => el.classList.contains('hidden')")

    ui_page.locator("#deep-verify-check").check()
    assert not dpi_row.evaluate("el => el.classList.contains('hidden')")


# =========================================================================== #
# Screen 4 — Report Detail
# =========================================================================== #


def test_file_click_opens_report(ui_page):
    """Clicking a file row opens the report detail screen."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the files step
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)

    rows = ui_page.locator(".file-row")
    rows.first.wait_for(state="visible", timeout=3000)
    rows.nth(1).click()  # memo.pdf — has residual matches

    report_screen = ui_page.locator("#screen-report")
    report_screen.wait_for(state="visible", timeout=3000)
    assert report_screen.is_visible()
    assert "memo.pdf" in ui_page.locator("#report-title").text_content()


def test_project_card_keyboard_activation(ui_page):
    """Enter on a focused project card opens the workspace."""
    card = ui_page.locator(".project-card").first
    card.focus()
    ui_page.keyboard.press("Enter")
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    assert ui_page.locator("#screen-workspace").is_visible()


def test_file_row_keyboard_activation(ui_page):
    """Enter on a focused file row opens the report screen."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    row = ui_page.locator(".file-row").first
    row.focus()
    ui_page.keyboard.press("Enter")
    ui_page.wait_for_selector("#screen-report.active", timeout=3000)
    assert ui_page.locator("#screen-report").is_visible()


def test_residual_matches_table(ui_page):
    """Report detail shows residual matches in table rows."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
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
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
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
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
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
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)

    empty = page.locator("#project-list-body .empty-state")
    empty.wait_for(state="visible", timeout=3000)
    assert "No projects yet" in empty.text_content()


def test_get_started_continues_on_root_error(ui_server, page):
    """Get Started click proceeds to projects even if select_project_root fails."""
    mock = build_mock_js(
        list_projects='() => Promise.resolve(JSON.stringify({needs_root: false, projects: []}))',
        select_project_root='() => Promise.reject(new Error("nope"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    # Welcome screen is active by default; click Get Started
    page.click("#get-started-btn")
    projects = page.locator("#screen-projects")
    projects.wait_for(state="visible", timeout=5000)
    assert projects.is_visible()


def test_create_project_error_toast(ui_server, page):
    """Create project failures surface via error toast."""
    mock = build_mock_js(
        create_project='() => Promise.reject(new Error("boom"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    # Open modal, fill name, click Create
    page.click("#new-project-btn")
    page.wait_for_selector("#modal-new-project:not(.hidden)", timeout=3000)
    page.fill("#modal-project-name", "Bad Project")
    page.click("#modal-create-btn")
    toast = page.locator(".toast.toast-error")
    toast.wait_for(state="visible", timeout=5000)
    assert "Failed to create project" in toast.text_content()


def test_modal_focus_trap_and_escape(ui_server, page):
    """Modal traps focus and closes on Escape."""
    mock = build_mock_js(fire_event=False)
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.click("#new-project-btn")
    page.wait_for_selector("#modal-new-project:not(.hidden)", timeout=3000)
    assert page.locator("#modal-overlay").get_attribute("aria-hidden") == "false"
    assert page.locator("#modal-new-project").get_attribute("role") == "dialog"
    assert page.locator("#modal-new-project").get_attribute("aria-modal") == "true"

    # Focus should start on the name input.
    assert page.evaluate("document.activeElement.id") == "modal-project-name"

    # Shift+Tab from first element should wrap to last element.
    page.keyboard.press("Shift+Tab")
    page.wait_for_function("document.activeElement.id === 'modal-create-btn'", timeout=2000)
    assert page.evaluate("document.activeElement.id") == "modal-create-btn"

    # Escape closes modal.
    page.keyboard.press("Escape")
    page.wait_for_function(
        "document.getElementById('modal-new-project').classList.contains('hidden')",
        timeout=3000,
    )
    page.wait_for_function(
        "document.getElementById('modal-overlay').getAttribute('aria-hidden') === 'true'",
        timeout=2000,
    )
    assert page.locator("#modal-overlay").get_attribute("aria-hidden") == "true"


def test_toast_exit_class_applied(ui_page):
    """Toast receives exit class before removal."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

    ui_page.evaluate("""
        window.pywebview.api.run_project = (name, deep, dpi) => {
            return Promise.resolve(JSON.stringify({
                files_processed: 1, total_redactions: 0,
                files_needing_review: 0, report_path: null
            }));
        };
    """)

    ui_page.locator("#run-btn").click()
    toast = ui_page.locator(".toast")
    toast.wait_for(state="visible", timeout=2000)
    ui_page.wait_for_function(
        "document.querySelector('.toast')?.classList.contains('toast-exit')",
        timeout=10000,
    )
    assert toast.evaluate("el => el.classList.contains('toast-exit')")


def test_toast_container_aria_live(ui_page):
    """Toast container should announce updates."""
    assert ui_page.evaluate("""
        () => {
            const el = document.getElementById('toast-container');
            return el && el.getAttribute('role') === 'status' && el.getAttribute('aria-live') === 'polite';
        }
    """)


def test_drop_icon_is_aria_hidden(ui_page):
    """Decorative drop icon should be aria-hidden."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    assert ui_page.evaluate("""
        () => document.querySelector('.drop-illustration span').getAttribute('aria-hidden') === 'true'
    """)


def test_file_list_has_listitem_semantics(ui_page):
    """File list uses list/listitem ARIA semantics."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)

    assert ui_page.evaluate("""
        () => {
            const list = document.getElementById('file-list');
            if (!list || list.getAttribute('role') !== 'list') return false;
            const items = list.querySelectorAll('[role=\"listitem\"]');
            return items.length > 0;
        }
    """)


def test_reduced_motion_disables_spinner_animation(ui_page):
    """Reduced motion should disable spinner animation."""
    ui_page.emulate_media(reduced_motion="reduce")
    ui_page.evaluate("""
        const ring = document.createElement('div');
        ring.className = 'spinner-ring';
        document.body.appendChild(ring);
    """)
    assert ui_page.evaluate("""
        () => getComputedStyle(document.querySelector('.spinner-ring')).animationName === 'none'
    """)


def test_reduced_motion_disables_toast_animation(ui_page):
    """Reduced motion should disable toast animation."""
    ui_page.emulate_media(reduced_motion="reduce")
    ui_page.evaluate("""
        const toast = document.createElement('div');
        toast.className = 'toast';
        document.body.appendChild(toast);
    """)
    assert ui_page.evaluate("""
        () => parseFloat(getComputedStyle(document.querySelector('.toast')).animationDuration) < 0.02
    """)


def test_progress_bar_uses_transform(ui_page):
    """Progress bar updates via transform scaleX."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

    ui_page.evaluate("""
        window.pywebview.api.run_project = (name, deep, dpi) => {
            return new Promise(resolve => {
                setTimeout(() => {
                    resolve(JSON.stringify({
                        files_processed: 1, total_redactions: 0,
                        files_needing_review: 0, report_path: null
                    }));
                }, 200);
            });
        };
    """)

    ui_page.locator("#run-btn").click()
    ui_page.wait_for_function(
        "document.getElementById('progress-fill').style.transform.includes('scaleX(')",
        timeout=3000,
    )
    assert "scaleX(" in ui_page.locator("#progress-fill").evaluate("el => el.style.transform")


def test_save_keywords_error_indicator(ui_server, page):
    """Save keyword failure should show Error indicator."""
    mock = build_mock_js(
        save_keywords='() => Promise.reject(new Error("fail"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
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


def test_run_project_error_toast(ui_server, page):
    """Run failures surface via error toast."""
    mock = build_mock_js(
        run_project='() => Promise.reject(new Error("run failed"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the run step
    page.click("[data-step='run']")
    page.wait_for_selector("#step-run.active", timeout=3000)

    page.click("#run-btn")
    toast = page.locator(".toast.toast-error")
    toast.wait_for(state="visible", timeout=5000)
    assert "Run failed" in toast.text_content()


def test_add_files_error_toast(ui_server, page):
    """Add files failure shows error toast."""
    mock = build_mock_js(
        add_files='() => Promise.reject(new Error("fail add"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the files step
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    page.click("#add-files-btn")
    toast = page.locator(".toast.toast-error")
    toast.wait_for(state="visible", timeout=5000)
    assert "Failed to add files" in toast.text_content()


def test_remove_file_updates_list(ui_server, page):
    """Removing a file calls API and refreshes the list."""
    mock = build_mock_js(fire_event=False) + """
    window._files = [
        {file: "contract.pdf", status: "not_run", redactions_applied: 0},
        {file: "memo.pdf", status: "not_run", redactions_applied: 0}
    ];
    window._removeCalls = [];
    window.pywebview.api.list_files = () => Promise.resolve(JSON.stringify({files: window._files}));
    window.pywebview.api.remove_file = (_name, filename) => {
        window._removeCalls.push(filename);
        window._files = window._files.filter(f => f.file !== filename);
        return Promise.resolve(JSON.stringify({status: "ok", removed: filename}));
    };
    """
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    page.locator(".file-row").first.wait_for(state="visible", timeout=3000)
    assert page.locator(".file-row").count() == 2

    remove_btn = page.locator('.file-remove-btn[aria-label="Remove contract.pdf"]')
    remove_btn.click()  # First click shows "Sure?"
    page.wait_for_function(
        'document.querySelector(\'.file-remove-btn[aria-label="Remove contract.pdf"]\').textContent === "Sure?"',
        timeout=3000,
    )
    remove_btn.click()  # Second click confirms removal

    page.wait_for_function("window._removeCalls.length === 1", timeout=3000)
    page.wait_for_function("document.querySelectorAll('.file-row').length === 1", timeout=3000)
    assert page.evaluate("window._removeCalls[0]") == "contract.pdf"
    assert "contract.pdf" not in page.locator("#file-list").text_content()


def test_remove_file_error_toast(ui_server, page):
    """Remove file failures surface via error toast."""
    mock = build_mock_js(
        remove_file='() => Promise.reject(new Error("remove failed"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    remove_btn = page.locator(".file-remove-btn").first
    remove_btn.click()  # First click shows "Sure?"
    page.wait_for_function(
        "document.querySelector('.file-remove-btn').textContent === 'Sure?'",
        timeout=3000,
    )
    remove_btn.click()  # Second click confirms removal
    toast = page.locator(".toast.toast-error")
    toast.wait_for(state="visible", timeout=5000)
    assert "Failed to remove file" in toast.text_content()


def test_remove_confirm_reverts_after_timeout(ui_server, page):
    """Remove button reverts from 'Sure?' back to 'Remove' after timeout."""
    mock = build_mock_js(fire_event=False)
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    remove_btn = page.locator(".file-remove-btn").first
    remove_btn.wait_for(state="visible", timeout=3000)
    remove_btn.click()

    page.wait_for_function(
        "document.querySelector('.file-remove-btn').textContent === 'Sure?'",
        timeout=3000,
    )
    assert remove_btn.text_content() == "Sure?"
    assert "file-remove-confirm" in remove_btn.get_attribute("class")

    # Wait for revert (3 second timer + buffer)
    page.wait_for_function(
        "document.querySelector('.file-remove-btn').textContent === 'Remove'",
        timeout=5000,
    )
    assert remove_btn.text_content() == "Remove"


def test_no_files_empty_state(ui_server, page):
    """No input files should show empty state message."""
    mock = build_mock_js(
        list_files='() => Promise.resolve(JSON.stringify({files: []}))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the files step
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)

    empty = page.locator("#file-list .empty-state")
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
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)
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
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
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
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)
    page.locator(".file-row").first.click()
    page.wait_for_selector("#screen-report.active", timeout=3000)

    assert "orphan.pdf" in page.locator("#report-title").text_content()
    assert "not run" in page.locator("#report-verdict").text_content()
    assert page.locator("#meta-redactions").text_content() == "--"
    assert page.locator("#meta-language").text_content() == "--"
    assert page.locator("#meta-threshold").text_content() == "--"
    assert page.locator("#meta-timestamp").text_content() == "Never"


def test_open_preview_and_reveal_errors(ui_server, page):
    """Preview/reveal failures surface via error toasts."""
    mock = build_mock_js(
        open_in_preview='() => Promise.reject(new Error("open fail"))',
        reveal_in_finder='() => Promise.reject(new Error("reveal fail"))',
        fire_event=False,
    )
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)
    page.locator(".project-card").first.click()
    page.wait_for_selector("#screen-workspace.active", timeout=3000)
    page.click("[data-step='files']")
    page.wait_for_selector("#step-files.active", timeout=3000)
    page.locator(".file-row").first.click()
    page.wait_for_selector("#screen-report.active", timeout=3000)

    page.click("#open-preview-btn")
    toast = page.locator(".toast.toast-error")
    toast.first.wait_for(state="visible", timeout=5000)
    assert "Could not open file" in toast.first.text_content()

    page.click("#reveal-finder-btn")
    page.wait_for_function(
        "document.querySelectorAll('.toast.toast-error').length >= 2",
        timeout=5000,
    )
    toasts = page.locator(".toast.toast-error")
    assert "Could not reveal file" in toasts.nth(1).text_content()


def test_keyboard_run_triggers(ui_page):
    """Enter on focused Run button triggers the action."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Navigate to the run step
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

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


def test_toast_close_button_removes_toast(ui_page):
    """Clicking the toast close button removes the toast."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)

    ui_page.evaluate("""
        window.pywebview.api.run_project = (name, deep, dpi) => {
            return Promise.resolve(JSON.stringify({
                files_processed: 1, total_redactions: 0,
                files_needing_review: 0, report_path: null
            }));
        };
    """)

    ui_page.locator("#run-btn").click()
    toast = ui_page.locator(".toast")
    toast.wait_for(state="visible", timeout=2000)
    ui_page.locator(".toast-close").click()
    ui_page.wait_for_function(
        "document.querySelectorAll('.toast').length === 0",
        timeout=3000,
    )
    assert ui_page.locator(".toast").count() == 0


def test_stepper_prev_next_navigation(ui_page):
    """Stepper prev/next buttons navigate between steps."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Start on keywords step
    assert ui_page.locator("#step-keywords").evaluate("el => el.classList.contains('active')")

    # Next: keywords -> files
    ui_page.click("#step-next-files")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    assert ui_page.locator("#step-files").evaluate("el => el.classList.contains('active')")

    # Prev: files -> keywords
    ui_page.click("#step-prev-keywords")
    ui_page.wait_for_selector("#step-keywords.active", timeout=3000)
    assert ui_page.locator("#step-keywords").evaluate("el => el.classList.contains('active')")

    # Next: keywords -> files -> run
    ui_page.click("#step-next-files")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    ui_page.click("#step-next-run")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)
    assert ui_page.locator("#step-run").evaluate("el => el.classList.contains('active')")

    # Prev: run -> files
    ui_page.click("#step-prev-files")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    assert ui_page.locator("#step-files").evaluate("el => el.classList.contains('active')")


def test_modal_overlay_click_closes(ui_server, page):
    """Clicking the modal overlay (not the modal itself) closes the modal."""
    mock = build_mock_js(fire_event=False)
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.click("#new-project-btn")
    page.wait_for_selector("#modal-new-project:not(.hidden)", timeout=3000)
    assert page.locator("#modal-overlay").get_attribute("aria-hidden") == "false"

    # Click the overlay itself (top-left corner, outside the modal)
    page.locator("#modal-overlay").click(position={"x": 5, "y": 5})
    page.wait_for_function(
        "document.getElementById('modal-new-project').classList.contains('hidden')",
        timeout=3000,
    )
    assert page.locator("#modal-overlay").get_attribute("aria-hidden") == "true"


def test_empty_project_name_no_submit(ui_server, page):
    """Clicking Create with an empty name does nothing (modal stays open)."""
    mock = build_mock_js(fire_event=False) + """
    window._createCalled = false;
    window.pywebview.api.create_project = function() {
        window._createCalled = true;
        return Promise.resolve(JSON.stringify({name: "X", path: "/tmp/X"}));
    };
    """
    page.add_init_script(mock)
    page.goto(ui_server + "/index.html", wait_until="domcontentloaded")
    page.evaluate("""
        document.getElementById('screen-welcome').classList.remove('active');
        document.getElementById('screen-projects').classList.add('active');
    """)
    page.evaluate(FIRE_EVENT_JS)
    page.wait_for_selector(".project-card", timeout=3000)

    page.click("#new-project-btn")
    page.wait_for_selector("#modal-new-project:not(.hidden)", timeout=3000)

    # Leave name empty and click Create
    page.click("#modal-create-btn")
    # Modal should remain open (or at least create_project should not be called)
    page.wait_for_function("true", timeout=500)
    assert page.evaluate("window._createCalled") is False


def test_focus_moves_to_heading_on_screen_transition(ui_page):
    """After navigating to a new screen, focus moves to the screen's h1."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)
    ui_page.wait_for_function(
        "document.activeElement && document.activeElement.id === 'workspace-title'",
        timeout=3000,
    )
    assert ui_page.evaluate("document.activeElement.id") == "workspace-title"


def test_tab_aria_selected_state(ui_page):
    """Active step tab has aria-selected=true, inactive tabs have false."""
    ui_page.locator(".project-card").first.click()
    ui_page.wait_for_selector("#screen-workspace.active", timeout=3000)

    # Keywords tab is active by default
    assert ui_page.locator("#tab-keywords").get_attribute("aria-selected") == "true"
    assert ui_page.locator("#tab-files").get_attribute("aria-selected") == "false"
    assert ui_page.locator("#tab-run").get_attribute("aria-selected") == "false"

    # Switch to files
    ui_page.click("[data-step='files']")
    ui_page.wait_for_selector("#step-files.active", timeout=3000)
    assert ui_page.locator("#tab-keywords").get_attribute("aria-selected") == "false"
    assert ui_page.locator("#tab-files").get_attribute("aria-selected") == "true"
    assert ui_page.locator("#tab-run").get_attribute("aria-selected") == "false"

    # Switch to run
    ui_page.click("[data-step='run']")
    ui_page.wait_for_selector("#step-run.active", timeout=3000)
    assert ui_page.locator("#tab-keywords").get_attribute("aria-selected") == "false"
    assert ui_page.locator("#tab-files").get_attribute("aria-selected") == "false"
    assert ui_page.locator("#tab-run").get_attribute("aria-selected") == "true"
