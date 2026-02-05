# Obscura Implementation Plan — Review & Feedback

Date: 2026-02-05
Reviewer: Codex
Scope: Review of `docs/plans/2026-02-04-obscura-implementation.md`

This review focuses on correctness, security/safety, redaction quality, UX/product risks, testability, and long‑term maintainability. The plan is solid for a v0, but there are several correctness and risk gaps that should be addressed before shipping to legal teams.

---

## Executive Summary (Top Risks)

1. **Redaction accuracy and completeness risks**: Current matching logic is likely to miss real‑world redaction cases (hyphenation, ligatures, text in images, headers/footers, rotated text, multi‑span text, PDF structure oddities). The current `search_for(matched_text)` on matched substring is fragile and can mis‑locate or miss instances entirely.
2. **Verification is too weak as a safety net**: Verification does not reliably OCR pages (only unreadable detection). It doesn’t use OCR confidence at all, and “deep verify” is optional. This creates a false sense of safety for clean status.
3. **Sanitization is partial**: Metadata/annotations/embedded files are covered, but many PDF artifacts persist (XMP metadata, forms, JavaScript, links, named destinations, attachments in object streams, hidden layers).
4. **Failure handling and auditability**: Reports lack a stable schema/version, and failure cases do not include enough info for audit trails. There’s no log of inputs/outputs, run config, or deterministic run ID.
5. **UI/UX and workflow gaps**: The UI spec omits core workflows: file ingestion, progress/errors, cancelling runs, and multi‑file status. This is risky for legal teams.

---

## Phase 0: Project Setup

### Findings
- **PyMuPDF license risk noted but not addressed.** The plan depends on PyMuPDF (AGPL) and Tesseract. Legal review is referenced elsewhere but not integrated into the plan. Need a decision gate before packaging/distribution.
- **`build-system` uses legacy backend.** The `setuptools.backends._legacy` backend is discouraged and may cause packaging inconsistencies.

### Recommendations
- Add a **licensing decision gate** before Phase 8 (Packaging). If AGPL is not acceptable, consider `pypdfium2` or `pdfminer.six` + `ocrmypdf` as alternatives.
- Switch to `build-backend = "setuptools.build_meta"` unless legacy is required for a reason.

---

## Phase 1: KeywordSet

### Findings
- **Simple string matching is insufficient for legal redaction needs.** Cases that will be missed or mis‑redacted:
  - **Hyphenation across lines** (e.g., “confi-\n dential”).
  - **Ligatures** (e.g., “ﬁ” in PDF text extraction).
  - **Split spans**: keywords split across spans or blocks are not found with `text.find()`.
  - **Unicode normalization** (smart quotes, accents, homoglyphs).
  - **Word boundaries**: plain keywords can match inside words (e.g., “secretary” matches “secret”).
- **Regex timeout is only used in `finditer`, not in compilation.** Some regex patterns can still be pathological during matching, but there’s no per‑pattern timeout or safe‑guarding of overall search time.
- **Prefix matching uses `\w*`** which excludes hyphens and other word characters common in names (e.g., “investor‑relations”).
- **`keyword_hash` is based on lowercased normalized forms but does not include an explicit version or settings** (case sensitivity, normalization rules, locale, etc.). This may break traceability if matching rules change later.

### Recommendations
- Normalize input text and keywords consistently (NFKC) and allow configurable word boundary rules (default to whole‑word for safety).
- Provide an option to **disallow substring matches** for plain keywords unless explicitly requested.
- Include a **match mode** in `keyword_hash` (e.g., `match_version`, `normalization`, `word_boundary`).
- Consider using PyMuPDF’s **structured text extraction** (spans/blocks) and perform matching across contiguous spans to reduce misses.
- Expand tests to include hyphenation, ligatures, Unicode normalization, and word boundary cases.

---

## Phase 1.2: `redact_pdf`

### Findings
- **`search_for(matched_text)` is fragile.**
  - It depends on PyMuPDF’s text extraction matching exactly the substring found in a different extraction path, which often diverges (whitespace, normalization, ligatures).
  - If multiple occurrences of the same substring exist on a page, it may over‑redact (matches not necessarily corresponding to the exact matched keyword). Your code re‑searches the entire page for each `matched_text` rather than using character positions.
- **OCR is used only when no text exists, and OCR confidence is ignored.**
- **No handling of rotated text, annotations with text, form fields, or XObjects with text** (common in PDFs).
- **No font/text‑rendering layer redaction** for PDFs with text in vector shapes.
- **`apply_redactions()` called only when matches exist**; good, but multiple redactions per page may be incomplete if `search_for` misses spans.
- **Atomic write does not include fsync or tmp file handling on failure**; might be acceptable but can lose data on power loss.

### Recommendations
- Instead of `search_for(matched_text)`, use **`page.search_for(keyword)` directly per keyword** (with regex) OR use **text page objects with char bounding boxes** to map the found text ranges to rectangles. There are patterns for this in PyMuPDF (text page extraction with bounding boxes per span/char).
- Implement a **“redaction coverage” metric**: for each keyword match, record whether a rectangle was found, and include in report as a warning if not.
- Expand tests to include:
  - Keywords split across spans/lines.
  - Rotated text.
  - Words with ligatures.
  - PDFs with form fields.
- Consider adding a **“search_mode=word/substring”** setting to avoid over‑redaction.

---

## Phase 2: Sanitize

### Findings
- **Sanitize is incomplete for legal‑grade redaction.** Current implementation removes metadata, annotations, embedded files, and runs garbage collection. Missing:
  - XMP metadata
  - JavaScript actions
  - Form fields / AcroForm
  - Links / named destinations
  - File attachments stored in non‑standard places
  - Optional content groups (OCG) / layers
  - Redaction annotations might remain in history if not properly flattened
- **No explicit error handling for encrypted or corrupt PDFs** (sanitization will throw).

### Recommendations
- Add explicit handling for:
  - `doc.is_encrypted` and decrypt attempt if supported.
  - XMP metadata via `doc.xref_set_key` or `doc.set_metadata` + `doc.save(clean=True, garbage=4)` but verify XMP actually clears.
  - Clear forms: `doc.set_form_field_value` or remove AcroForm.
  - Remove JavaScript actions if present.
- Extend tests to cover **link annotations**, **form fields**, and **XMP metadata**.

---

## Phase 3: Project Model

### Findings
- **Project name is used as folder name without sanitization.** This can cause invalid paths or traversal issues (`../`), or names that fail on Windows if cross‑platform is ever needed.
- **No locking/concurrency handling** when multiple runs happen simultaneously.
- **`created` and `last_run` stored as strings** without timezone normalization; ok for now but lacks ordering semantics.

### Recommendations
- Sanitize and validate project name (no path separators, no reserved characters, length limit).
- Add a unique project ID in `project.json` to decouple display name from directory name.
- Consider file‑based lock (e.g., `project.lock`) to prevent parallel runs.

---

## Phase 4: Verification Layer

### Findings
- **OCR confidence not used at all**; `low_confidence_pages` is never populated.
- **Unreadable detection is too simplistic**: any page with images or page rect width > 0 is marked unreadable if no text. That will flag many legitimate pages unnecessarily and still won’t actually OCR them.
- **Residual matches are based on `page.get_text()` only**, which can fail to extract text even if the text is present in unusual encodings.
- **Deep verify is optional and has no performance guardrails** (e.g., for large documents).
- **No page text context by default**, which is good for privacy, but there’s no way to include a minimal safe snippet or bounding box to locate in the UI.

### Recommendations
- Implement **OCR pass for unreadable pages** and populate `low_confidence_pages` using OCR confidence. If OCR fails, mark unreadable.
- Provide a **configurable “verification mode”**:
  - Fast: text extraction only
  - Standard: OCR unreadable pages
  - Deep: rasterize and OCR all pages
- Track and report **verification coverage** (percentage of pages verified by text vs OCR vs unreadable).
- Consider adding **page-level bounding boxes** for residual matches to enable UI highlighting or at least page navigation.

---

## Phase 5: Runner

### Findings
- **Errors during per‑file processing are not isolated**. If `sanitize_pdf` or `verify_pdf` throws on one file, the entire run will crash and skip remaining files.
- **Reports are not versioned**. This makes future migrations hard.
- **No record of run configuration** (deep_verify, dpi, keyword hash, engine version, etc.) at the report header level.
- **Files with no matches still go through sanitize/verify** — ok, but not recorded for triage.

### Recommendations
- Add per‑file try/except to continue processing and record errors in the report.
- Introduce a report schema with top‑level metadata:
  - `schema_version`
  - `run_id` or timestamp
  - `engine_version`
  - `keyword_hash`
  - `project_name`
  - `settings` (deep_verify, dpi, thresholds)
- Write reports as `{ metadata: ..., files: [...] }` rather than bare list.

---

## Phase 6: CLI

### Findings
- **`report` command only shows last report; no selection** beyond `--last`.
- **No `create` command** for project creation.
- **Error messaging** for missing project is minimal.
- **`run` command does not validate keywords file** or empty keywords file; could produce false sense of redaction.

### Recommendations
- Add `create` command with `--root`, `--language`, `--threshold`.
- Add `report --list` or `report --path`.
- Validate `keywords.txt` non‑empty and warn if empty.

---

## Phase 7: Desktop UI

### Findings
- **UI spec is missing critical workflows**:
  - Ingestion: how PDFs are added to the project (drag/drop?) must copy into input dir.
  - Progress: large files take time; UI needs progress, cancellation, and status per file.
  - Error display: corrupt/encrypted files need surfaced clearly with next action.
  - Review: there is no notion of user approving redactions or opening specific pages.
- **Security**: `open_in_preview` and `reveal_in_finder` are macOS‑specific (`open`). There’s no OS abstraction.
- **Config path uses project root as config dir** (in `config.py`), which is odd; config belongs in `~/.config/obscura` or `~/Library/Application Support/Obscura`.
- **File dialogs**: The `_get_project_root` function is defined but not used in `launch()`.

### Recommendations
- Expand the UI design to include:
  - File ingestion and progress
  - File‑level status (redacted, needs review, error)
  - Ability to open report per file
  - Run history
- Move config storage to platform‑appropriate location (`appdirs` or `platformdirs`).
- Use `_get_project_root()` in `launch()` or remove it.
- Abstract `open` for Windows/Linux (or gate and report unsupported).

---

## Phase 8: Packaging

### Findings
- **PyInstaller bundling of Tesseract is OS‑specific** and likely brittle. `--add-binary` expects platform‑specific path separators; the plan assumes macOS only.
- **Tesseract data paths**: runtime must set `TESSDATA_PREFIX` or `--tessdata-dir` for OCR calls.
- **Missing dependency list**: PyMuPDF and pywebview include native components; bundle needs `--collect-all` or `--hidden-import` for them.

### Recommendations
- Add a runtime bootstrapping step to set `TESSDATA_PREFIX` when the app launches.
- Verify PyInstaller hooks for PyMuPDF and pywebview; add explicit `--collect-all fitz` if needed.
- Document supported OS version and architecture.

---

## Testing & QA Gaps

- No tests for **image‑only PDFs** in redaction flow (only in verify).
- No tests for **multipage PDFs with mixed text + image**.
- No tests for **OCR behavior** or `get_textpage_ocr` failures.
- No tests for **large PDFs** (performance, timeouts).
- No tests for **sanitize edge cases** (forms, JS, links, XMP metadata).
- No tests for **runner error handling**.

### Recommendations
- Add a focused suite of **integration tests** for full pipeline using mixed content PDFs.
- Add performance test for a “large” PDF and ensure timeouts are respected.

---

## Security & Privacy

- There is **no explicit guarantee that temporary files are deleted** on failure, or that OCR output doesn’t leak.
- No mention of **secure deletion**. For legal workflows, “delete input or temporary OCR data” might be required.
- No mention of **local‑only enforcement** (network calls blocked, telemetry disabled). If this is a compliance promise, the plan should confirm this in code and docs.

### Recommendations
- Document exactly where temporary files are created and cleaned.
- Consider an option to keep originals separate from redacted outputs, or hash‑locked for audit.
- Include a “local‑only” statement in the CLI/UI and a runtime assertion that no network calls are made (if feasible).

---

## Maintainability & Observability

- No structured logging (only prints in CLI). Errors in GUI mode will be silent.
- No concept of run logs per project.

### Recommendations
- Add simple logging (to `reports/` or `logs/`) with timestamps and error traces.
- Ensure the UI surfaces errors from API calls.

---

## Suggested Plan Amendments (High‑Value)

1. **Add a “Redaction Accuracy” task** after Task 1.2 to improve matching (character‑level bounding boxes, normalization) and expand tests.
2. **Add a “Verification OCR” task** after Task 4.1 to implement OCR on unreadable pages and confidence thresholds.
3. **Add a “Sanitize Advanced” task** after Task 2.1 to remove forms, JS, links, XMP metadata.
4. **Add report schema versioning** and metadata.
5. **Add UI status/progress/error handling** tasks.
6. **Add platform abstraction** for open/reveal and config storage.

---

## Concrete Next Steps (If you want me to implement)

- I can draft a follow‑up plan chunk with exact tasks, tests, and code changes for the redaction accuracy improvements and verification OCR.
- I can also add a report schema with metadata and update `runner.py`, CLI, and UI to consume it.

