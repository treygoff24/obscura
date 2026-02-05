# Obscura — Desktop Tool Design

**Date:** 2026-02-04
**Status:** Draft (v3)
**Author:** Trey Goff

## Problem

Legal teams need to programmatically redact PDFs on a per-matter basis. Existing solutions are either expensive commercial tools or developer-operated scripts. Obscura is a local-only, open source desktop tool that makes keyword-based PDF redaction accessible to non-technical staff while remaining powerful for technical users.

## Constraints

- macOS desktop app — documents never leave the machine
- Usable by non-technical legal staff and power users alike
- Must handle everything from a handful of clean contracts to hundreds of mixed-quality scanned docs
- English and Spanish language documents

## Architecture

**Python end-to-end.** pywebview wraps a lightweight web UI in a native macOS window. The redaction engine runs directly as a Python module. Ships as a self-contained `.app` via PyInstaller with Tesseract and language data bundled.

**Licensing note:** PyMuPDF is AGPL-licensed. Distributing a `.app` (even internally) may trigger copyleft obligations. Before implementation, either: (a) purchase a commercial PyMuPDF license from Artifex, or (b) evaluate `pypdf` + `pdfplumber` as FOSS alternatives. This decision gates Phase 1. **Important:** if switching away from PyMuPDF, validate that alternatives support true text-removing redaction (not just overlay) and OCR integration. `pypdf` and `pdfplumber` are not drop-in replacements — this is a research task, not a swap.

**OCR toolchain:** Tesseract is called directly via PyMuPDF's built-in OCR integration (`page.get_textpage_ocr()`), not through ocrmypdf. This eliminates the ocrmypdf and Ghostscript dependencies, simplifying the bundle. Tesseract binary and language data (English + Spanish) are bundled inside the `.app`.

**Regex engine:** Uses the third-party `regex` module (not stdlib `re`) for pattern matching. The `regex` module is a drop-in replacement that supports match timeouts, preventing catastrophic backtracking (ReDoS) from user-supplied patterns. Stdlib `re` has no timeout mechanism.

```
┌──────────────────────────────────┐
│        pywebview window          │
│  ┌────────────────────────────┐  │
│  │     HTML / CSS / JS UI     │  │
│  └─────────────┬──────────────┘  │
│                │ JS bridge       │
│  ┌─────────────▼──────────────┐  │
│  │     Python app layer       │  │
│  │  (project mgmt, run orch)  │  │
│  └─────────────┬──────────────┘  │
│                │                 │
│  ┌─────────────▼──────────────┐  │
│  │     Redaction engine       │  │
│  │  (PyMuPDF + Tesseract)     │  │
│  └─────────────┬──────────────┘  │
│                │                 │
│  ┌─────────────▼──────────────┐  │
│  │      Sanitize step         │  │
│  │  (metadata, annotations,   │  │
│  │   embedded files, xrefs)   │  │
│  └─────────────┬──────────────┘  │
│                │                 │
│  ┌─────────────▼──────────────┐  │
│  │    Verification layer      │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

## Project Model

Each project is a self-contained folder on disk. No database.

```
~/Obscura/
├── Example Matter/
│   ├── project.json            # metadata + settings (see schema below)
│   ├── keywords.txt            # one keyword per line
│   ├── input/                  # original PDFs (copied in, not referenced)
│   ├── output/                 # redacted PDFs
│   └── reports/                # per-run verification reports (timestamped)
│       └── 2026-02-04T14-30-00.json
├── Vendor Contract Review/
│   └── ...
└── .config.json                # app-level settings (project root path)
```

The project root directory (`~/Obscura/` by default) is selectable on first launch and stored in `.config.json`. This avoids hardcoding a path and prepares for future macOS sandboxing/notarization, which requires file-picker-based permissions for directory access.

**`project.json` schema:**

```json
{
  "schema_version": 1,
  "name": "Example Matter",
  "created": "2026-02-04T14:00:00Z",
  "last_run": "2026-02-04T14:30:00Z",
  "language": "eng",
  "confidence_threshold": 70
}
```

- `schema_version` — validated on load; prevents the app from ingesting arbitrary folders.
- `language` — Tesseract language codes. Defaults to `"eng"`. Supports `"eng"`, `"spa"`, or `"eng+spa"`. Default is single-language because mixed-language OCR can reduce accuracy. The UI makes this an explicit choice with a note: "Mixed-language mode may reduce OCR accuracy on single-language documents."
- `confidence_threshold` — OCR confidence cutoff (0–100). Pages below this average are flagged. Configurable per project because scan quality varies by matter.

**Key decisions:**

- Flat files over SQLite — projects are browsable in Finder, portable via zip/USB.
- Keywords stay as a plain text file — power users edit in any text editor, the UI also provides an editor.
- Reports are JSON — structured for the UI to render, human-readable in a pinch.
- Input files are copied into the project, not symlinked — the project folder is the single source of truth.
- Project discovery validates `schema_version` before listing a folder as a project.

## Redaction Engine

Stateless module with a clean interface.

**Design:**

- Keyword state is encapsulated in a `KeywordSet` class, instantiated per project.
- Users can add regex patterns in `keywords.txt` with a `regex:` prefix (e.g., `regex:\binvestor\b`).
- Regex patterns are validated on load using the `regex` module. Invalid patterns produce a clear error. Match execution uses `regex.match(..., timeout=5)` to prevent ReDoS.
- Path-agnostic — engine takes input path, output path, and a `KeywordSet`. The app layer manages project structure.
- Per-file structured results instead of a flat text report.
- Language parameter passed to Tesseract for OCR (from `project.json`).

**Redaction correctness:** PyMuPDF's `apply_redactions()` removes underlying text objects, not just overlays. This is true redaction — text is deleted from the PDF content stream, not hidden. A regression test must verify this by attempting to extract text from redacted regions and asserting nothing is returned. This test is a Phase 1 deliverable.

**File handling:**

- Password-protected PDFs: detected on open, reported as `"status": "password_protected"` — user sees a clear message, not a stack trace.
- Corrupted PDFs: caught on open, reported as `"status": "corrupt"`.
- Signed PDFs: redaction will invalidate the signature. Reported as a warning in results.
- All output writes are atomic: write to a temp file in the output directory, then rename on success. Prevents partial/corrupt outputs on crash.
- Large PDFs are processed page-by-page. No full-document loading into memory.

**Core dependencies:**

- PyMuPDF for PDF manipulation (pending licensing decision)
- Tesseract for OCR
- `regex` module for pattern matching with timeouts

**Matching features:**

- Single keyword matching (case-insensitive, normalized)
- Multi-word phrase matching
- Hyphenated phrase matching
- Prefix/wildcard matching (e.g., `investor*`)
- Dollar amount detection and redaction
- User-defined regex patterns via `regex:` prefix

**Interface:**

```python
keywords = KeywordSet.from_file("path/to/keywords.txt")
result = redact_pdf(input_path, output_path, keywords, language="eng")
# result.redaction_count, result.pages, result.ocr_used, result.verification
```

## Sanitize Step

After redaction and before verification, every output PDF goes through a sanitize pass to ensure redacted content is not recoverable. This is the difference between cosmetic redaction and legal-grade redaction.

**What gets scrubbed:**

- **Metadata:** Document title, author, subject, keywords, creator, producer. Replaced with empty values via `doc.set_metadata({})`.
- **Annotations:** All non-redaction annotations removed via `page.delete_annot()` (comments, highlights, sticky notes that might reference redacted content).
- **Embedded files:** Attachments and portfolio entries removed via `doc.embfile_del()`.
- **Incremental updates:** PDF is saved with `garbage=4` and `clean=True` to collapse the xref table and remove prior revisions. No "undo" of redactions via PDF history.
- **Optional content groups (OCGs):** Best-effort flattening. PyMuPDF can enumerate OCGs via `doc.layer_ui_configs()` and set visibility, but full removal of optional content groups requires manipulating the page content stream. For v1: set all OCGs to visible and flatten during save. Document this as a known limitation — deeply nested optional content may require manual review. A regression test should verify that hidden-layer text is not extractable after save.

## Verification Layer

Runs on every output file after redaction and sanitization. Four checks:

**A. Residual keyword scan.** Re-extracts text from the redacted PDF and searches for surviving keyword matches. Catches partial matches, split-block misses, and normalizer edge cases. Logs each surviving match with page number. No context snippets by default — the report should not contain the very text being redacted. A `--verbose` flag (CLI) or debug toggle (UI) opts into context snippets for troubleshooting.

**B. OCR confidence scoring.** For OCR-processed pages, checks Tesseract per-word confidence. Pages below the project's `confidence_threshold` (default 70%) are flagged. Surfaces bad-scan-quality problems.

**C. Image-only page detection.** Flags pages with near-zero extractable text — pages OCR couldn't read or didn't attempt. These are "we couldn't even see this page" warnings. The report explicitly notes that unverified pages have not been confirmed clean.

**D. Rasterize and re-scan (optional).** For high-risk jobs, the user can enable a "deep verify" mode that rasterizes each output page to an image at 300 DPI (configurable, range 150–600), runs OCR on the rasterized image, and checks the result for surviving keywords. This catches content hidden in vector graphics, unusual font encodings, or text that PyMuPDF's extractor missed. Slower, but provides the highest confidence. Enabled per-run, not per-project.

**Per-file report structure:**

```json
{
  "file": "contract_v3.pdf",
  "status": "needs_review",
  "source_hash": "sha256:def456...",
  "redactions_applied": 47,
  "residual_matches": [
    {"keyword": "example-name", "page": 3}
  ],
  "low_confidence_pages": [5, 8],
  "unreadable_pages": [12],
  "unverified_warning": "Pages 12 were not OCR-readable and could not be verified.",
  "clean_pages": [1, 2, 4, 6, 7, 9, 10, 11],
  "deep_verify": false,
  "deep_verify_dpi": null,
  "engine_version": "1.0.0",
  "keywords_hash": "sha256:abc123...",
  "language": "eng",
  "confidence_threshold": 70,
  "timestamp": "2026-02-04T14:30:00Z"
}
```

**Report privacy:** Default reports contain keyword name + page number only. No surrounding text context. Verbose mode adds context snippets and is opt-in. This prevents the verification report from becoming a leak vector for redacted content.

**Traceability:** Each report includes engine version, a SHA-256 hash of the keywords file at run time, a SHA-256 hash of the source input file (`source_hash`), language setting, and confidence threshold. This proves which exact file was processed with which exact keyword set.

**File statuses:** clean (nothing flagged), needs_review (residual matches or low-confidence pages), unreadable (couldn't process), password_protected, corrupt. Rendered as green/yellow/red in the UI.

## UI

Three screens. Every action reachable within one click.

### Screen 1: Project List (home)

Clean list of projects sorted by last modified. Each row: project name, file count, last run date, status pill (green/yellow/red based on worst file from last run). "New Project" button in top bar. Click a project to open it.

The app discovers projects by scanning the configured project root and validating `schema_version` in each `project.json`. Power users can create project folders manually — the app picks them up if valid. On first launch, a dialog prompts the user to choose their project root directory (defaults to `~/Obscura/`).

### Screen 2: Project Workspace

The main working screen. Three panels:

- **Left — Keywords panel.** Text editor showing `keywords.txt`. Add, remove, edit directly. One per line. Supports `regex:` prefix with inline validation (invalid patterns show an error immediately, powered by the `regex` module). Auto-saves.
- **Center — Files panel.** Lists input PDFs. Drag-and-drop or "Add Files" button. Shows per-file status from last run (green/yellow/red/gray). Password-protected and corrupt files show distinct icons.
- **Right — Run controls + summary.** "Run Redaction" button. A "Deep Verify" checkbox for high-risk runs (with DPI selector, default 300). Language selector (English / Spanish / Both) with a note that mixed-language may reduce accuracy. Below the button: last run results (total files, total redactions, files needing review). Click a flagged file to drill down.

### Screen 3: File Report Detail

Single-file verification breakdown. Residual matches with page numbers (no context by default). Low-confidence pages. Unreadable pages with explicit "not verified" warning. Each flagged item shows the page number and has an **"Open in Preview"** button that opens the output PDF in Preview.app (note: macOS `open` cannot jump to a specific page without AppleScript — the button opens the file and the UI displays the page number so the user knows where to navigate). A **"Reveal in Finder"** button for the output file. Structured list — tells the user exactly where to look.

## Packaging & Distribution

**Build:** PyInstaller bundles Python, all dependencies (including `regex` module), Tesseract binary, and language data (English `eng.traineddata` + Spanish `spa.traineddata`) into a single `Obscura.app`. The `--windowed` flag suppresses the terminal. Expected app size ~50-70MB with Tesseract + two language packs.

**Gatekeeper:** macOS will block unsigned apps by default. For v1, users right-click > Open to bypass. If required, add notarization later ($99/yr Apple Developer account). Note: if sandboxed/notarized later, the app will need file-picker-based permissions for the project root — the selectable root directory (above) prepares for this.

**Distribution:** Zip the `.app`, distribute via GitHub Releases. Users drag to Applications.

**Updates:** Ship new zips via GitHub Releases. No auto-updater for v1.

## CLI Access

Power users get a CLI entrypoint for automation and scripting:

```bash
obscura run ~/Obscura/Example\ Matter/
obscura run ~/Obscura/Example\ Matter/ --deep-verify --dpi 400 --verbose
obscura list
obscura report ~/Obscura/Example\ Matter/ --last
```

Same engine, same project folders. The CLI and GUI operate on the same data. The `--verbose` flag enables context snippets in reports. The `--deep-verify` flag enables rasterize-and-scan verification. The `--dpi` flag sets rasterization resolution (default 300).

## Implementation Phases

1. **Engine refactor** — `KeywordSet` class, stateless `redact_pdf()`, `regex` module for pattern matching with timeouts, atomic writes, error handling for password/corrupt/signed PDFs. Resolve PyMuPDF licensing first (if FOSS route: validate alternatives support true redaction + OCR). Regression test: verify `apply_redactions()` removes text from content stream (extract text from redacted area, assert empty).
2. **Sanitize step** — metadata scrubbing, annotation removal, embedded file removal, OCG best-effort flattening, incremental update collapse. Regression test: verify hidden-layer text is not extractable after save.
3. **Project model** — folder management, `project.json` with schema validation, language and threshold settings, selectable project root on first launch.
4. **Verification layer** — residual scan (no context default), OCR confidence, image-only detection, rasterize+scan deep verify (configurable DPI, default 300), source file hash, report versioning.
5. **CLI** — thin CLI over phases 1–4. Usable tool for power users at this point.
6. **Desktop UI** — pywebview app, three screens, drag-and-drop, keyword editor with `regex`-powered validation, "Open in Preview" + page hint, first-launch root selector.
7. **Packaging** — PyInstaller build, bundle Tesseract + eng/spa language data + `regex` module, produce `.app`, test on clean Mac.

## Out of Scope for v1

- Multi-user collaboration or shared projects
- PDF preview in-app
- Auto-update mechanism
- Windows/Linux support
- Audit logging or compliance trail
- Per-redaction approval workflow
- Encryption at rest (macOS FileVault handles this at the OS level)
- Full job queue with cancel/pause (simple progress bar + threading is sufficient)
- AppleScript-based Preview page jumping (open file + show page number is sufficient)
