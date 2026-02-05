/* Obscura UI — three-screen SPA communicating with Python via pywebview. */

(function () {
    "use strict";

    let currentProject = null;
    let currentReport = null;
    let currentFileName = null;

    /* --- DOM refs --- */

    const screens = {
        projects: document.getElementById("screen-projects"),
        workspace: document.getElementById("screen-workspace"),
        report: document.getElementById("screen-report"),
    };

    const el = {
        projectList: document.getElementById("project-list"),
        newProjectBtn: document.getElementById("new-project-btn"),
        backToProjects: document.getElementById("back-to-projects"),
        workspaceTitle: document.getElementById("workspace-title"),
        workspaceLanguage: document.getElementById("workspace-language"),
        keywordsEditor: document.getElementById("keywords-editor"),
        saveKeywordsBtn: document.getElementById("save-keywords-btn"),
        saveIndicator: document.getElementById("save-indicator"),
        fileList: document.getElementById("file-list"),
        fileCount: document.getElementById("file-count"),
        runBtn: document.getElementById("run-btn"),
        deepVerifyCheck: document.getElementById("deep-verify-check"),
        dpiRow: document.getElementById("dpi-row"),
        dpiSelect: document.getElementById("dpi-select"),
        runSpinner: document.getElementById("run-spinner"),
        runSummary: document.getElementById("run-summary"),
        sumFiles: document.getElementById("sum-files"),
        sumRedactions: document.getElementById("sum-redactions"),
        sumReview: document.getElementById("sum-review"),
        backToWorkspace: document.getElementById("back-to-workspace"),
        reportTitle: document.getElementById("report-title"),
        reportStatus: document.getElementById("report-status"),
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
    };

    /* --- Routing --- */

    function showScreen(name) {
        Object.values(screens).forEach(function (s) { s.classList.remove("active"); });
        screens[name].classList.add("active");
    }

    /* --- Helpers --- */

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
            return iso;
        }
    }

    function statusClass(status) {
        if (!status) return "status-none";
        return "status-" + status;
    }

    function statusLabel(status) {
        if (!status) return "none";
        return status.replace(/_/g, " ");
    }

    /* --- Screen 1: Project List --- */

    async function loadProjects() {
        el.projectList.innerHTML = '<p class="empty-state">Loading projects...</p>';
        try {
            var result = await window.pywebview.api.list_projects();
            var projects = JSON.parse(result);
            if (projects.length === 0) {
                el.projectList.innerHTML =
                    '<p class="empty-state">No projects yet. Click "New Project" to get started.</p>';
                return;
            }
            var grid = document.createElement("div");
            grid.className = "project-grid";
            projects.forEach(function (p) {
                var card = document.createElement("div");
                card.className = "project-card";
                card.innerHTML =
                    "<h3>" + esc(p.name) + "</h3>" +
                    '<div class="meta">' +
                    (p.last_run ? "Last run: " + formatDate(p.last_run) : "Not yet run") +
                    "<br>Language: " + esc(p.language) +
                    "</div>";
                card.addEventListener("click", function () { openProject(p.name, p.language); });
                grid.appendChild(card);
            });
            el.projectList.innerHTML = "";
            el.projectList.appendChild(grid);
        } catch (e) {
            el.projectList.innerHTML =
                '<p class="empty-state">Error loading projects.</p>';
        }
    }

    el.newProjectBtn.addEventListener("click", async function () {
        var name = prompt("Project name:");
        if (!name || !name.trim()) return;
        try {
            await window.pywebview.api.create_project(name.trim());
            await loadProjects();
        } catch (e) {
            alert("Failed to create project: " + e.message);
        }
    });

    /* --- Screen 2: Workspace --- */

    async function openProject(name, language) {
        currentProject = name;
        currentReport = null;
        el.workspaceTitle.textContent = name;
        el.workspaceLanguage.textContent = language || "eng";
        el.runSummary.classList.add("hidden");
        el.runSpinner.classList.add("hidden");
        el.runBtn.disabled = false;
        showScreen("workspace");
        await Promise.all([loadKeywords(), loadReport()]);
    }

    el.backToProjects.addEventListener("click", function () {
        currentProject = null;
        currentReport = null;
        showScreen("projects");
        loadProjects();
    });

    /* Keywords */

    async function loadKeywords() {
        try {
            var text = await window.pywebview.api.get_keywords(currentProject);
            el.keywordsEditor.value = text;
        } catch (_) {
            el.keywordsEditor.value = "";
        }
    }

    el.saveKeywordsBtn.addEventListener("click", async function () {
        el.saveIndicator.textContent = "Saving...";
        el.saveIndicator.className = "save-indicator saving";
        try {
            await window.pywebview.api.save_keywords(currentProject, el.keywordsEditor.value);
            el.saveIndicator.textContent = "Saved";
            el.saveIndicator.className = "save-indicator saved";
            setTimeout(function () { el.saveIndicator.textContent = ""; }, 2000);
        } catch (e) {
            el.saveIndicator.textContent = "Error";
            el.saveIndicator.className = "save-indicator";
        }
    });

    /* Report / File List */

    async function loadReport() {
        el.fileList.innerHTML = '<p class="empty-state">Loading...</p>';
        try {
            var result = await window.pywebview.api.get_latest_report(currentProject);
            var report = JSON.parse(result);
            currentReport = report;
            renderFileList(report);
        } catch (_) {
            currentReport = null;
            el.fileList.innerHTML =
                '<p class="empty-state">Run redaction to see file results.</p>';
        }
    }

    function renderFileList(report) {
        var files = report.files || [];
        if (files.length === 0) {
            el.fileList.innerHTML =
                '<p class="empty-state">Run redaction to see file results.</p>';
            el.fileCount.textContent = "";
            return;
        }
        el.fileCount.textContent = files.length + " file" + (files.length !== 1 ? "s" : "");
        el.fileList.innerHTML = "";
        files.forEach(function (f) {
            var row = document.createElement("div");
            row.className = "file-row";
            var pill = '<span class="status-pill ' + statusClass(f.status) + '">' +
                       statusLabel(f.status) + "</span>";
            var redactionsText = "";
            if (typeof f.redactions_applied === "number") {
                redactionsText = '<span class="file-redactions">' +
                                 f.redactions_applied + " redactions</span>";
            }
            row.innerHTML =
                '<span class="file-name">' + esc(f.file) + "</span>" +
                redactionsText + pill;
            row.addEventListener("click", function () { openFileReport(f); });
            el.fileList.appendChild(row);
        });
    }

    /* Deep Verify toggle */

    el.deepVerifyCheck.addEventListener("change", function () {
        el.dpiRow.classList.toggle("hidden", !el.deepVerifyCheck.checked);
    });

    /* Run */

    el.runBtn.addEventListener("click", async function () {
        el.runBtn.disabled = true;
        el.runSpinner.classList.remove("hidden");
        el.runSummary.classList.add("hidden");
        try {
            var deepVerify = el.deepVerifyCheck.checked;
            var dpi = parseInt(el.dpiSelect.value, 10);
            var result = await window.pywebview.api.run_project(currentProject, deepVerify, dpi);
            var summary = JSON.parse(result);
            el.sumFiles.textContent = summary.files_processed;
            el.sumRedactions.textContent = summary.total_redactions;
            el.sumReview.textContent = summary.files_needing_review;
            el.runSummary.classList.remove("hidden");
            await loadReport();
        } catch (e) {
            alert("Run failed: " + (e.message || e));
        } finally {
            el.runSpinner.classList.add("hidden");
            el.runBtn.disabled = false;
        }
    });

    /* --- Screen 3: File Report Detail --- */

    function openFileReport(fileData) {
        currentFileName = fileData.file;
        el.reportTitle.textContent = fileData.file;
        el.reportStatus.textContent = statusLabel(fileData.status);
        el.reportStatus.className = "status-pill " + statusClass(fileData.status);

        /* Residual matches */
        var residuals = fileData.residual_matches || [];
        if (residuals.length > 0) {
            el.residualSection.classList.remove("hidden");
            el.residualTableBody.innerHTML = residuals.map(function (m) {
                return "<tr><td>" + esc(m.keyword) + "</td>" +
                       "<td>" + m.page + "</td>" +
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
                return '<span class="page-badge warn">Page ' + p + "</span>";
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
                return '<span class="page-badge danger">Page ' + p + "</span>";
            }).join("");
        } else {
            el.unreadableSection.classList.add("hidden");
        }

        /* Clean pages */
        var clean = fileData.clean_pages || [];
        if (clean.length > 0) {
            el.cleanSection.classList.remove("hidden");
            el.cleanPages.innerHTML = clean.map(function (p) {
                return '<span class="page-badge ok">Page ' + p + "</span>";
            }).join("");
        } else {
            el.cleanSection.classList.add("hidden");
        }

        /* Metadata */
        el.metaRedactions.textContent =
            typeof fileData.redactions_applied === "number" ? fileData.redactions_applied : "--";
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
            await window.pywebview.api.open_in_preview(currentProject, currentFileName);
        } catch (e) {
            alert("Could not open file: " + (e.message || e));
        }
    });

    el.revealFinderBtn.addEventListener("click", async function () {
        if (!currentProject || !currentFileName) return;
        try {
            await window.pywebview.api.reveal_in_finder(currentProject, currentFileName);
        } catch (e) {
            alert("Could not reveal file: " + (e.message || e));
        }
    });

    /* --- Init --- */

    window.addEventListener("pywebviewready", loadProjects);
})();
