/* Obscura UI — four-screen SPA communicating with Python via pywebview. */

(function () {
    "use strict";

    var currentProject = null;
    var currentReport = null;
    var currentFileName = null;
    var keywordSaveTimer = null;
    var lastFocused = null;
    var modalOpen = false;

    /* --- DOM refs --- */

    var screens = {
        welcome: document.getElementById("screen-welcome"),
        projects: document.getElementById("screen-projects"),
        workspace: document.getElementById("screen-workspace"),
        report: document.getElementById("screen-report"),
    };

    var el = {
        /* Welcome */
        getStartedBtn: document.getElementById("get-started-btn"),

        /* Project list */
        projectList: document.getElementById("project-list"),
        projectListBody: document.getElementById("project-list-body"),
        newProjectBtn: document.getElementById("new-project-btn"),
        changeProjectRootBtn: document.getElementById("change-project-root-btn"),

        /* Workspace header */
        backToProjects: document.getElementById("back-to-projects"),
        workspaceTitle: document.getElementById("workspace-title"),

        /* Stepper */
        stepTabs: document.querySelectorAll(".step-tab"),
        stepPanels: document.querySelectorAll(".step-panel"),

        /* Step 1: Keywords */
        stepKeywords: document.getElementById("step-keywords"),
        keywordsEditor: document.getElementById("keywords-editor"),
        saveIndicator: document.getElementById("save-indicator"),
        keywordErrors: document.getElementById("keyword-errors"),
        stepNextFiles: document.getElementById("step-next-files"),

        /* Step 2: Files */
        stepFiles: document.getElementById("step-files"),
        fileDrop: document.getElementById("file-drop"),
        addFilesBtn: document.getElementById("add-files-btn"),
        fileList: document.getElementById("file-list"),
        fileCount: document.getElementById("file-count"),
        stepPrevKeywords: document.getElementById("step-prev-keywords"),
        stepNextRun: document.getElementById("step-next-run"),

        /* Step 3: Run */
        stepRun: document.getElementById("step-run"),
        runBtn: document.getElementById("run-btn"),
        runProgress: document.getElementById("run-progress"),
        progressFill: document.getElementById("progress-fill"),
        progressText: document.getElementById("progress-text"),
        runSummary: document.getElementById("run-summary"),
        summaryVerdict: document.getElementById("summary-verdict"),
        sumFiles: document.getElementById("sum-files"),
        sumRedactions: document.getElementById("sum-redactions"),
        sumReview: document.getElementById("sum-review"),
        openOutputBtn: document.getElementById("open-output-btn"),
        viewFilesBtn: document.getElementById("view-files-btn"),
        languageSelect: document.getElementById("language-select"),
        deepVerifyCheck: document.getElementById("deep-verify-check"),
        dpiRow: document.getElementById("dpi-row"),
        dpiSelect: document.getElementById("dpi-select"),
        stepPrevFiles: document.getElementById("step-prev-files"),

        /* Report detail */
        backToWorkspace: document.getElementById("back-to-workspace"),
        reportTitle: document.getElementById("report-title"),
        reportVerdict: document.getElementById("report-verdict"),
        openPreviewBtn: document.getElementById("open-preview-btn"),
        revealFinderBtn: document.getElementById("reveal-finder-btn"),
        residualSection: document.getElementById("report-residual"),
        residualTableBody: document.querySelector("#residual-table tbody"),
        lowconfSection: document.getElementById("report-lowconf"),
        lowconfPages: document.getElementById("lowconf-pages"),
        unreadableSection: document.getElementById("report-unreadable"),
        unreadableWarning: document.getElementById("unreadable-warning"),
        unreadablePages: document.getElementById("unreadable-pages"),
        cleanSection: document.getElementById("report-clean"),
        cleanPages: document.getElementById("clean-pages"),
        metaRedactions: document.getElementById("meta-redactions"),
        metaDeepverify: document.getElementById("meta-deepverify"),
        metaLanguage: document.getElementById("meta-language"),
        metaThreshold: document.getElementById("meta-threshold"),
        metaTimestamp: document.getElementById("meta-timestamp"),

        /* Modal */
        modalOverlay: document.getElementById("modal-overlay"),
        modalNewProject: document.getElementById("modal-new-project"),
        modalProjectName: document.getElementById("modal-project-name"),
        modalProjectLanguage: document.getElementById("modal-project-language"),
        modalCancelBtn: document.getElementById("modal-cancel-btn"),
        modalCreateBtn: document.getElementById("modal-create-btn"),

        /* Toast */
        toastContainer: document.getElementById("toast-container"),
    };

    /* --- Routing --- */

    function showScreen(name) {
        Object.values(screens).forEach(function (s) {
            if (s) s.classList.remove("active");
        });
        if (screens[name]) {
            screens[name].classList.add("active");
            var heading = screens[name].querySelector("h1");
            if (heading) {
                heading.setAttribute("tabindex", "-1");
                heading.focus();
            }
        }
    }

    /* --- Stepper --- */

    var stepOrder = ["keywords", "files", "run"];

    function showStep(stepName) {
        el.stepTabs.forEach(function (tab) {
            if (tab.dataset.step === stepName) {
                tab.classList.add("active");
                tab.setAttribute("aria-selected", "true");
                tab.setAttribute("tabindex", "0");
            } else {
                tab.classList.remove("active");
                tab.setAttribute("aria-selected", "false");
                tab.setAttribute("tabindex", "-1");
            }
        });
        el.stepPanels.forEach(function (panel) {
            if (panel.id === "step-" + stepName) {
                panel.classList.add("active");
                var heading = panel.querySelector("h2");
                if (heading) {
                    heading.setAttribute("tabindex", "-1");
                    heading.focus();
                }
            } else {
                panel.classList.remove("active");
            }
        });
    }

    el.stepTabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            showStep(tab.dataset.step);
        });
        tab.addEventListener("keydown", function (e) {
            var currentIdx = stepOrder.indexOf(tab.dataset.step);
            var nextIdx = -1;
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                e.preventDefault();
                nextIdx = (currentIdx + 1) % stepOrder.length;
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                e.preventDefault();
                nextIdx = (currentIdx - 1 + stepOrder.length) % stepOrder.length;
            } else if (e.key === "Home") {
                e.preventDefault();
                nextIdx = 0;
            } else if (e.key === "End") {
                e.preventDefault();
                nextIdx = stepOrder.length - 1;
            }
            if (nextIdx >= 0) {
                var nextTab = document.querySelector('.step-tab[data-step="' + stepOrder[nextIdx] + '"]');
                if (nextTab) {
                    showStep(stepOrder[nextIdx]);
                    nextTab.focus();
                }
            }
        });
    });

    if (el.stepNextFiles) {
        el.stepNextFiles.addEventListener("click", function () { showStep("files"); });
    }
    if (el.stepPrevKeywords) {
        el.stepPrevKeywords.addEventListener("click", function () { showStep("keywords"); });
    }
    if (el.stepNextRun) {
        el.stepNextRun.addEventListener("click", function () { showStep("run"); });
    }
    if (el.stepPrevFiles) {
        el.stepPrevFiles.addEventListener("click", function () { showStep("files"); });
    }

    /* --- Helpers --- */

    function resetWorkspaceState() {
        if (el.keywordsEditor) el.keywordsEditor.value = "";
        if (el.saveIndicator) { el.saveIndicator.textContent = ""; el.saveIndicator.className = "save-indicator"; }
        if (el.keywordErrors) { el.keywordErrors.classList.add("hidden"); el.keywordErrors.innerHTML = ""; }
        if (el.fileList) el.fileList.innerHTML = "";
        if (el.fileCount) el.fileCount.textContent = "";
        if (el.runSummary) el.runSummary.classList.add("hidden");
        if (el.runProgress) el.runProgress.classList.add("hidden");
        if (el.runBtn) el.runBtn.disabled = false;
        if (el.workspaceTitle) el.workspaceTitle.textContent = "Project";
        setProgress(0);
    }

    function esc(str) {
        var d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }

    function formatDate(iso) {
        if (!iso) return "Never";
        try {
            var d = new Date(iso);
            return d.toLocaleDateString(undefined, {
                year: "numeric", month: "short", day: "numeric",
                hour: "2-digit", minute: "2-digit",
            });
        } catch (_) {
            return esc(iso);
        }
    }

    function statusClass(status) {
        if (!status) return "status-none";
        return "status-" + status;
    }

    function statusLabel(status) {
        if (!status) return "none";
        if (status === "not_run") return "not run";
        return status.replace(/_/g, " ");
    }

    function verdictHTML(status) {
        var label = esc(statusLabel(status));
        return '<span class="status-pill ' + esc(statusClass(status)) + '">' + label + "</span>";
    }

    function setProgress(value) {
        var bar = el.progressFill ? el.progressFill.parentElement : null;
        if (el.progressFill) {
            el.progressFill.style.transform = "scaleX(" + value + ")";
        }
        if (bar) {
            bar.setAttribute("aria-valuenow", Math.round(value * 100));
        }
    }

    /* --- Toasts --- */

    function showToast(message, type) {
        if (!el.toastContainer) return;
        var toast = document.createElement("div");
        toast.className = "toast" + (type ? " toast-" + type : "");
        toast.setAttribute("role", type === "error" ? "alert" : "status");
        var text = document.createElement("span");
        text.textContent = message;
        toast.appendChild(text);
        var closeBtn = document.createElement("button");
        closeBtn.textContent = "\u00d7";
        closeBtn.className = "toast-close";
        closeBtn.setAttribute("aria-label", "Dismiss");
        closeBtn.addEventListener("click", function () { toast.remove(); });
        toast.appendChild(closeBtn);
        el.toastContainer.appendChild(toast);
        var duration = type === "error" ? 8000 : 3000;
        var timer = setTimeout(function () {
            toast.classList.add("toast-exit");
            setTimeout(function () { toast.remove(); }, 300);
        }, duration);
        toast.addEventListener("mouseenter", function () { clearTimeout(timer); });
        toast.addEventListener("mouseleave", function () {
            timer = setTimeout(function () {
                toast.classList.add("toast-exit");
                setTimeout(function () { toast.remove(); }, 300);
            }, 2000);
        });
    }

    /* --- Modal --- */

    function openModal() {
        lastFocused = document.activeElement;
        if (el.modalProjectName) el.modalProjectName.value = "";
        if (el.modalProjectLanguage) el.modalProjectLanguage.value = "eng";
        if (el.modalOverlay) el.modalOverlay.classList.remove("hidden");
        if (el.modalOverlay) el.modalOverlay.setAttribute("aria-hidden", "false");
        if (el.modalNewProject) el.modalNewProject.classList.remove("hidden");
        Object.values(screens).forEach(function (s) {
            if (s) s.setAttribute("aria-hidden", "true");
        });
        modalOpen = true;
        if (el.modalProjectName) el.modalProjectName.focus();
    }

    function closeModal() {
        if (el.modalOverlay) el.modalOverlay.classList.add("hidden");
        if (el.modalOverlay) el.modalOverlay.setAttribute("aria-hidden", "true");
        if (el.modalNewProject) el.modalNewProject.classList.add("hidden");
        Object.values(screens).forEach(function (s) {
            if (s) s.removeAttribute("aria-hidden");
        });
        modalOpen = false;
        if (lastFocused && typeof lastFocused.focus === "function") {
            lastFocused.focus();
        }
    }

    if (el.modalCancelBtn) {
        el.modalCancelBtn.addEventListener("click", closeModal);
    }

    if (el.modalOverlay) {
        el.modalOverlay.addEventListener("click", function (e) {
            if (e.target === el.modalOverlay) closeModal();
        });
    }

    function getModalFocusables() {
        if (!el.modalNewProject) return [];
        return Array.prototype.slice.call(
            el.modalNewProject.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )
        );
    }

    document.addEventListener("keydown", function (e) {
        if (!modalOpen) return;
        if (e.key === "Escape") {
            e.preventDefault();
            closeModal();
            return;
        }
        if (e.key !== "Tab") return;
        var focusables = getModalFocusables();
        if (focusables.length === 0) return;
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });

    /* --- Screen 1: Welcome --- */

    async function chooseProjectRoot() {
        var result = await window.pywebview.api.select_project_root();
        try {
            return JSON.parse(result || "{}");
        } catch (_) {
            return {};
        }
    }

    if (el.getStartedBtn) {
        el.getStartedBtn.addEventListener("click", async function () {
            try {
                await chooseProjectRoot();
            } catch (_) {
                /* User may cancel folder selection; continue anyway */
            }
            showScreen("projects");
            await loadProjects();
        });
    }

    /* --- Screen 2: Project List --- */

    async function loadProjects() {
        el.projectListBody.innerHTML = '<p class="empty-state">Loading projects...</p>';
        try {
            var result = await window.pywebview.api.list_projects();
            var data = JSON.parse(result);
            var projects = data.projects || [];
            if (data.needs_root) {
                /* Show welcome screen for initial root selection */
                if (screens.welcome) {
                    showScreen("welcome");
                }
                el.projectListBody.innerHTML = "";
                return;
            }
            if (projects.length === 0) {
                el.projectListBody.innerHTML =
                    '<p class="empty-state">No projects yet. Click "New Project" to get started.</p>';
                return;
            }
            var grid = document.createElement("div");
            grid.className = "project-grid";
            projects.forEach(function (p) {
                var card = document.createElement("button");
                card.className = "project-card";
                card.type = "button";
                card.setAttribute("aria-label", "Open project: " + p.name);
                card.innerHTML =
                    '<span class="card-title">' + esc(p.name) + "</span>" +
                    '<div class="meta">' +
                    (p.last_run ? "Last run: " + formatDate(p.last_run) : "Not yet run") +
                    "<br>Language: " + esc(p.language) +
                    "</div>";
                card.addEventListener("click", function () { openProject(p.name, p.language); });
                grid.appendChild(card);
            });
            el.projectListBody.innerHTML = "";
            el.projectListBody.appendChild(grid);
        } catch (e) {
            el.projectListBody.innerHTML =
                '<p class="empty-state">Error loading projects.</p>';
        }
    }

    el.newProjectBtn.addEventListener("click", function () {
        openModal();
    });

    if (el.changeProjectRootBtn) {
        el.changeProjectRootBtn.addEventListener("click", async function () {
            try {
                var response = await chooseProjectRoot();
                if (response.error) {
                    if (response.error !== "No folder selected") {
                        showToast("Failed to change project folder.", "error");
                    }
                    return;
                }
                currentProject = null;
                currentReport = null;
                currentFileName = null;
                resetWorkspaceState();
                showScreen("projects");
                await loadProjects();
                showToast("Project folder updated.", "success");
            } catch (_) {
                showToast("Failed to change project folder.", "error");
            }
        });
    }

    if (el.modalCreateBtn) {
        el.modalCreateBtn.addEventListener("click", async function () {
            var name = el.modalProjectName ? el.modalProjectName.value.trim() : "";
            if (!name) return;
            var language = el.modalProjectLanguage ? el.modalProjectLanguage.value : "eng";
            closeModal();
            try {
                await window.pywebview.api.create_project(name, language);
                showToast("Project created.", "success");
                await loadProjects();
            } catch (e) {
                showToast("Failed to create project: " + (e.message || e), "error");
            }
        });
    }

    /* --- Screen 3: Workspace --- */

    async function openProject(name, language) {
        currentProject = name;
        currentReport = null;
        el.workspaceTitle.textContent = name;
        if (el.runSummary) el.runSummary.classList.add("hidden");
        if (el.runProgress) el.runProgress.classList.add("hidden");
        el.runBtn.disabled = false;
        showStep("keywords");
        showScreen("workspace");
        await Promise.all([loadProjectSettings(), loadKeywords()]);
        await loadReport();
        await loadFiles();
    }

    el.backToProjects.addEventListener("click", function () {
        currentProject = null;
        currentReport = null;
        currentFileName = null;
        resetWorkspaceState();
        showScreen("projects");
        loadProjects();
    });

    /* Keywords */

    async function loadKeywords() {
        try {
            var text = await window.pywebview.api.get_keywords(currentProject);
            el.keywordsEditor.value = text;
            await validateKeywords(text);
        } catch (_) {
            el.keywordsEditor.value = "";
            showToast("Could not load keywords.", "error");
        }
    }

    async function loadProjectSettings() {
        try {
            var result = await window.pywebview.api.get_project_settings(currentProject);
            var settings = JSON.parse(result);
            if (settings.language && el.languageSelect) {
                el.languageSelect.value = settings.language;
            }
        } catch (_) {
            showToast("Could not load project settings.", "error");
        }
    }

    if (el.languageSelect) {
        el.languageSelect.addEventListener("change", async function () {
            if (!currentProject) return;
            try {
                await window.pywebview.api.update_project_settings(
                    currentProject,
                    el.languageSelect.value,
                    null
                );
            } catch (_) {
                showToast("Failed to update language.", "error");
            }
        });
    }

    el.keywordsEditor.addEventListener("input", function () {
        if (keywordSaveTimer) {
            clearTimeout(keywordSaveTimer);
        }
        el.saveIndicator.textContent = "Editing...";
        el.saveIndicator.className = "save-indicator";
        keywordSaveTimer = setTimeout(function () {
            saveKeywords(true);
        }, 600);
    });

    async function validateKeywords(content) {
        try {
            var result = await window.pywebview.api.validate_keywords(content);
            var data = JSON.parse(result);
            if (!data.valid) {
                var message = data.errors.map(function (e) {
                    return "Line " + esc("" + e.line) + ": " + esc(e.error);
                }).join("<br>");
                el.keywordErrors.innerHTML = message;
                el.keywordErrors.classList.remove("hidden");
                return false;
            }
            el.keywordErrors.classList.add("hidden");
            el.keywordErrors.innerHTML = "";
            return true;
        } catch (_) {
            return true;
        }
    }

    async function saveKeywords(isAuto) {
        var content = el.keywordsEditor.value;
        var valid = await validateKeywords(content);
        if (!valid) {
            el.saveIndicator.textContent = "Invalid";
            el.saveIndicator.className = "save-indicator";
            return;
        }
        el.saveIndicator.textContent = "Saving...";
        el.saveIndicator.className = "save-indicator saving";
        try {
            await window.pywebview.api.save_keywords(currentProject, content);
            el.saveIndicator.textContent = "Saved";
            el.saveIndicator.className = "save-indicator saved";
            if (isAuto) {
                setTimeout(function () { el.saveIndicator.textContent = ""; }, 1500);
            } else {
                setTimeout(function () { el.saveIndicator.textContent = ""; }, 2000);
            }
        } catch (e) {
            el.saveIndicator.textContent = "Error";
            el.saveIndicator.className = "save-indicator";
        }
    }

    /* Report / File List */

    async function loadReport() {
        try {
            var result = await window.pywebview.api.get_latest_report(currentProject);
            var report = JSON.parse(result);
            currentReport = report;
        } catch (_) {
            currentReport = null;
            showToast("Could not load previous report.", "error");
        }
    }

    async function loadFiles() {
        el.fileList.innerHTML = '<p class="empty-state">Loading...</p>';
        try {
            var result = await window.pywebview.api.list_files(currentProject);
            var data = JSON.parse(result);
            renderFileList(data.files || []);
        } catch (_) {
            el.fileList.innerHTML =
                '<p class="empty-state">Could not load files.</p>';
            showToast("Could not load file list.", "error");
        }
    }

    function renderFileList(files) {
        if (files.length === 0) {
            el.fileList.innerHTML =
                '<p class="empty-state">No input files yet. Add PDFs to get started.</p>';
            el.fileCount.textContent = "";
            return;
        }
        el.fileCount.textContent = files.length + " file" + (files.length !== 1 ? "s" : "");
        el.fileList.innerHTML = "";
        el.fileList.setAttribute("role", "list");
        files.forEach(function (f) {
            var rowWrap = document.createElement("div");
            rowWrap.className = "file-row-wrap";
            rowWrap.setAttribute("role", "listitem");

            var row = document.createElement("button");
            row.className = "file-row";
            row.type = "button";
            row.setAttribute("aria-label", f.file + ", status: " + statusLabel(f.status));
            var pill = '<span class="status-pill ' + esc(statusClass(f.status)) + '">' +
                       esc(statusLabel(f.status)) + "</span>";
            var redactionsText = "";
            if (typeof f.redactions_applied === "number") {
                redactionsText = '<span class="file-redactions">' +
                                 f.redactions_applied + " redactions</span>";
            }
            row.innerHTML =
                '<span class="file-name">' + esc(f.file) + "</span>" +
                redactionsText + pill;
            row.addEventListener("click", function () {
                var reportEntry = findReportEntry(f.file);
                openFileReport(reportEntry || f);
            });

            var removeBtn = document.createElement("button");
            removeBtn.className = "file-remove-btn";
            removeBtn.type = "button";
            removeBtn.setAttribute("aria-label", "Remove " + f.file);
            removeBtn.textContent = "Remove";
            removeBtn.addEventListener("click", function (event) {
                event.stopPropagation();
                if (removeBtn.classList.contains("file-remove-confirm")) {
                    removeInputFile(f.file);
                } else {
                    removeBtn.textContent = "Sure?";
                    removeBtn.classList.add("file-remove-confirm");
                    removeBtn._revertTimer = setTimeout(function () {
                        removeBtn.textContent = "Remove";
                        removeBtn.classList.remove("file-remove-confirm");
                    }, 3000);
                }
            });

            rowWrap.appendChild(row);
            rowWrap.appendChild(removeBtn);
            el.fileList.appendChild(rowWrap);
        });
    }

    async function removeInputFile(filename) {
        if (!currentProject) return;
        try {
            var result = await window.pywebview.api.remove_file(currentProject, filename);
            var data = JSON.parse(result || "{}");
            if (data.error) {
                showToast("Failed to remove file: " + data.error, "error");
                return;
            }
            showToast("Removed " + filename + ".", "success");
            await loadFiles();
            var nextRow = el.fileList.querySelector(".file-row");
            if (nextRow) {
                nextRow.focus();
            } else if (el.addFilesBtn) {
                el.addFilesBtn.focus();
            }
        } catch (_) {
            showToast("Failed to remove file.", "error");
        }
    }

    function findReportEntry(filename) {
        if (!currentReport || !currentReport.files) return null;
        for (var i = 0; i < currentReport.files.length; i++) {
            if (currentReport.files[i].file === filename) {
                return currentReport.files[i];
            }
        }
        return null;
    }

    /* File ingestion */

    el.addFilesBtn.addEventListener("click", async function () {
        if (!currentProject) return;
        try {
            var result = await window.pywebview.api.add_files(currentProject);
            var data = JSON.parse(result);
            if (data.error) {
                showToast("Failed to add files: " + data.error, "error");
            } else if (data.added && data.added.length > 0) {
                showToast(data.added.length + " file" + (data.added.length !== 1 ? "s" : "") + " added.", "success");
            }
            if (data.skipped && data.skipped.length > 0) {
                showToast(data.skipped.length + " file" + (data.skipped.length !== 1 ? "s" : "") + " skipped (not PDF).", "error");
            }
            await loadFiles();
        } catch (e) {
            showToast("Failed to add files.", "error");
        }
    });

    el.fileDrop.addEventListener("dragover", function (e) {
        e.preventDefault();
        el.fileDrop.classList.add("active");
    });

    el.fileDrop.addEventListener("dragleave", function () {
        el.fileDrop.classList.remove("active");
    });

    el.fileDrop.addEventListener("drop", async function (e) {
        e.preventDefault();
        el.fileDrop.classList.remove("active");
        if (!currentProject) return;
        var files = Array.from(e.dataTransfer.files || []);
        var paths = files.map(function (f) { return f.path; }).filter(Boolean);
        try {
            var result;
            if (paths.length > 0) {
                result = await window.pywebview.api.add_files(currentProject, paths);
            } else {
                result = await window.pywebview.api.add_files(currentProject);
            }
            var data = JSON.parse(result);
            if (data.error) {
                showToast("Failed to add files: " + data.error, "error");
            } else if (data.added && data.added.length > 0) {
                showToast(data.added.length + " file" + (data.added.length !== 1 ? "s" : "") + " added.", "success");
            }
            if (data.skipped && data.skipped.length > 0) {
                showToast(data.skipped.length + " file" + (data.skipped.length !== 1 ? "s" : "") + " skipped (not PDF).", "error");
            }
            await loadFiles();
        } catch (err) {
            showToast("Failed to add files.", "error");
        }
    });

    /* Deep Verify toggle */

    if (el.deepVerifyCheck) {
        el.deepVerifyCheck.addEventListener("change", function () {
            el.dpiRow.classList.toggle("hidden", !el.deepVerifyCheck.checked);
        });
    }

    /* Run */

    el.runBtn.addEventListener("click", async function () {
        el.runBtn.disabled = true;
        if (el.runProgress) el.runProgress.classList.remove("hidden");
        setProgress(0);
        if (el.progressText) el.progressText.textContent = "Processing…";
        if (el.runSummary) el.runSummary.classList.add("hidden");
        try {
            var deepVerify = el.deepVerifyCheck ? el.deepVerifyCheck.checked : false;
            var dpi = el.dpiSelect ? parseInt(el.dpiSelect.value, 10) : 300;
            setProgress(0.3);
            var result = await window.pywebview.api.run_project(currentProject, deepVerify, dpi);
            setProgress(1);
            var summary = JSON.parse(result);
            el.sumFiles.textContent = summary.files_processed;
            el.sumRedactions.textContent = summary.total_redactions;
            el.sumReview.textContent = summary.files_needing_review;
            if (el.summaryVerdict) {
                if (summary.files_needing_review > 0) {
                    el.summaryVerdict.innerHTML = '<span class="status-pill status-needs_review">Needs review</span>';
                } else {
                    el.summaryVerdict.innerHTML = '<span class="status-pill status-clean">All clean</span>';
                }
            }
            if (el.runSummary) el.runSummary.classList.remove("hidden");
            showToast("Redaction complete", "success");
            await loadReport();
            await loadFiles();
        } catch (e) {
            showToast("Run failed: " + (e.message || e) + " — check View logs for details.", "error");
        } finally {
            if (el.runProgress) el.runProgress.classList.add("hidden");
            el.runBtn.disabled = false;
        }
    });

    el.openOutputBtn.addEventListener("click", async function () {
        if (!currentProject) return;
        try {
            var result = await window.pywebview.api.reveal_output_folder(currentProject);
            var data = JSON.parse(result);
            if (data.error) {
                showToast("Could not open output folder: " + data.error, "error");
            }
        } catch (e) {
            showToast("Could not open output folder.", "error");
        }
    });

    el.viewFilesBtn.addEventListener("click", function () {
        showStep("files");
    });

    /* --- Screen 4: File Report Detail --- */

    function openFileReport(fileData) {
        currentFileName = fileData.file;
        el.reportTitle.textContent = fileData.file;

        if (el.reportVerdict) {
            el.reportVerdict.innerHTML = verdictHTML(fileData.status);
        }

        /* Residual matches */
        var residuals = fileData.residual_matches || [];
        if (residuals.length > 0) {
            el.residualSection.classList.remove("hidden");
            el.residualTableBody.innerHTML = residuals.map(function (m) {
                return "<tr><td>" + esc(m.keyword) + "</td>" +
                       "<td>" + esc("" + m.page) + "</td>" +
                       "<td>" + esc(m.source || "standard") + "</td></tr>";
            }).join("");
        } else {
            el.residualSection.classList.add("hidden");
        }

        /* Low confidence pages */
        var lowConf = fileData.low_confidence_pages || [];
        if (lowConf.length > 0) {
            el.lowconfSection.classList.remove("hidden");
            el.lowconfPages.innerHTML = lowConf.map(function (p) {
                return '<span class="page-badge warn">Page ' + esc("" + p) + "</span>";
            }).join("");
        } else {
            el.lowconfSection.classList.add("hidden");
        }

        /* Unreadable pages */
        var unreadable = fileData.unreadable_pages || [];
        if (unreadable.length > 0) {
            el.unreadableSection.classList.remove("hidden");
            el.unreadableWarning.textContent =
                fileData.unverified_warning ||
                "Pages " + unreadable.join(", ") + " were not OCR-readable and could not be verified.";
            el.unreadablePages.innerHTML = unreadable.map(function (p) {
                return '<span class="page-badge danger">Page ' + esc("" + p) + "</span>";
            }).join("");
        } else {
            el.unreadableSection.classList.add("hidden");
        }

        /* Clean pages */
        var clean = fileData.clean_pages || [];
        if (clean.length > 0) {
            el.cleanSection.classList.remove("hidden");
            el.cleanPages.innerHTML = clean.map(function (p) {
                return '<span class="page-badge ok">Page ' + esc("" + p) + "</span>";
            }).join("");
        } else {
            el.cleanSection.classList.add("hidden");
        }

        /* Metadata */
        var standardRedactions =
            typeof fileData.redactions_applied === "number" ? fileData.redactions_applied : null;
        var ocrRedactions =
            typeof fileData.ocr_redactions_applied === "number" ? fileData.ocr_redactions_applied : 0;
        var hasFullReportMetadata = typeof fileData.deep_verify === "boolean";
        if (standardRedactions === null && ocrRedactions > 0) {
            el.metaRedactions.textContent = ocrRedactions;
        } else if (standardRedactions !== null) {
            el.metaRedactions.textContent = hasFullReportMetadata
                ? (standardRedactions + ocrRedactions)
                : standardRedactions;
        } else {
            el.metaRedactions.textContent = "--";
        }
        el.metaDeepverify.textContent = fileData.deep_verify ? "Yes (" + fileData.deep_verify_dpi + " DPI)" : "No";
        el.metaLanguage.textContent = fileData.language || "--";
        el.metaThreshold.textContent =
            typeof fileData.confidence_threshold === "number" ? fileData.confidence_threshold + "%" : "--";
        el.metaTimestamp.textContent = formatDate(fileData.timestamp);

        showScreen("report");
    }

    el.backToWorkspace.addEventListener("click", function () {
        showScreen("workspace");
    });

    el.openPreviewBtn.addEventListener("click", async function () {
        if (!currentProject || !currentFileName) return;
        try {
            var result = await window.pywebview.api.open_in_preview(currentProject, currentFileName);
            var data = JSON.parse(result);
            if (data.error) {
                showToast("Could not open file: " + data.error, "error");
            }
        } catch (e) {
            showToast("Could not open file.", "error");
        }
    });

    el.revealFinderBtn.addEventListener("click", async function () {
        if (!currentProject || !currentFileName) return;
        try {
            var result = await window.pywebview.api.reveal_in_finder(currentProject, currentFileName);
            var data = JSON.parse(result);
            if (data.error) {
                showToast("Could not reveal file: " + data.error, "error");
            }
        } catch (e) {
            showToast("Could not reveal file.", "error");
        }
    });

    /* --- Logs --- */

    var viewLogsBtn = document.getElementById("view-logs-btn");
    if (viewLogsBtn) {
        viewLogsBtn.addEventListener("click", async function () {
            try {
                var result = await window.pywebview.api.open_log_file();
                var data = JSON.parse(result);
                if (data.error) {
                    showToast("No log file found.", "error");
                }
            } catch (e) {
                showToast("Could not open log file.", "error");
            }
        });
    }

    /* --- Init --- */

    window.addEventListener("pywebviewready", function () {
        /* If welcome screen is active, wait for Get Started click.
           Otherwise go straight to project list. */
        if (screens.welcome && screens.welcome.classList.contains("active")) {
            /* Welcome screen handles its own flow */
            return;
        }
        loadProjects();
    });
})();
