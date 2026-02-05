# Obscura Code Review — 2026-02-05

> Historical snapshot: this review reflects repository state on 2026-02-05 and may not match current implementation.

**Scope**: Review of implementation against `docs/plans/2026-02-04-obscura-implementation.md` and `docs/plans/2026-02-04-obscura-design.md`, with focus on correctness, redaction safety, verification integrity, UI workflow completeness, and test coverage. Files reviewed include `src/obscura/*`, `src/obscura/ui/*`, and `tests/*`.

**Executive Summary**: Core pipeline, CLI, and API are implemented and test-covered, but several redaction correctness issues remain (case-insensitive matching, prefix handling, OCR redaction path). UI implementation is missing key workflows from the plan (file ingestion, language selection, regex validation, first-launch root selection). Packaging phase is not implemented. These gaps are material for legal-grade redaction and plan compliance.

**Plan Compliance**
1. Phase 0 (Project setup): Complete.
2. Phase 1–6 (Keywords, redaction, sanitize, project model, verify, runner, CLI): Implemented per plan, with correctness issues noted below.
3. Phase 7 (Desktop UI): Partial. Core screens exist, but required behaviors from the plan/design are missing: first-launch root selection integration, file ingestion/drag-drop, language selector, regex validation, and auto-save.
4. Phase 8 (Packaging): Missing. No `build.py` or PyInstaller spec/script found.
5. Design doc licensing gate: Not represented in code or build flow; still a dependency risk for distribution.

**Findings (Ordered by Severity)**
1. [P0] Redaction case-insensitivity is not guaranteed. Plain and prefix keywords are lowercased and passed to `page.search_for()` without ignore-case flags. If `search_for()` is case-sensitive (default), uppercase or mixed-case occurrences will not be redacted. `src/obscura/redact.py:63-76`. Recommendation: pass `flags=fitz.TEXT_IGNORECASE` (or equivalent), or use a regex-based search path with word-boundary handling to enforce case-insensitive matching.
2. [P0] Prefix matching does not redact the full matched token. The code searches for the prefix only (`page.search_for(prefix)`), so only the prefix substring is redacted, leaving suffix text visible (e.g., `investor-relations` would leave `-relations`). `src/obscura/redact.py:73-76`. Recommendation: compute full-word rectangles (e.g., via textpage word extraction) and redact the full matched token.
3. [P1] OCR fallback in redaction does not actually drive rectangle search. `page.get_textpage_ocr()` is called, but the OCR textpage is not used in `search_for()`. For image-only PDFs, this likely produces no redactions at all. `src/obscura/redact.py:153-164` and `src/obscura/redact.py:63-92`. Recommendation: pass the OCR `TextPage` to search (if supported) or build rectangles directly from OCR word boxes.
4. [P1] Report `source_hash` reflects the redacted output, not the original input. The design requires a source input hash for traceability. `src/obscura/verify.py:96-98` and `src/obscura/runner.py:93-114`. Recommendation: include input hash from `redact_pdf()` in the per-file report, and optionally include both input and output hashes.
5. [P1] `VerificationReport.status` never returns `unreadable` even though the schema and UI expect it. `src/obscura/verify.py:166-170`. Recommendation: set `status = "unreadable"` when unreadable pages exist and no residual matches are found, or define explicit precedence rules.
6. [P2] UI expects `redactions_applied` per file, but the report does not include it. This results in missing data in the file list and report metadata. `src/obscura/ui/app.js:214-226` and `src/obscura/ui/app.js:319-321` vs `src/obscura/runner.py:93-114`. Recommendation: add `redactions_applied` (from `RedactionResult.redaction_count`) to each file report entry.
7. [P2] First-launch root selector is not wired. `_get_project_root()` is unused, and the saved config location is inconsistent with the loader, so the project root never persists. `src/obscura/app.py:13-49`. Recommendation: call `_get_project_root()` from `launch()` and store config in a stable, dedicated config directory (not the project root).
8. [P2] Plan-required UI workflows are missing: file ingestion (drag-drop or add files), language selection, inline regex validation, and keyword auto-save. This blocks end-to-end usage and deviates from Phase 7.4 and the design doc. `src/obscura/ui/index.html` and `src/obscura/ui/app.js`.
9. [P2] `open_in_preview` and `reveal_in_finder` accept unsanitized filenames, enabling path traversal outside the output directory if the UI ever passes a crafted filename. `src/obscura/api.py:69-83`. Recommendation: resolve and validate that the target path is within `output_dir` before opening.
10. [P3] `python -m obscura` with no args launches the GUI when pywebview is installed, which can cause CLI test hangs. `src/obscura/__main__.py:6-16` and `tests/test_cli.py:131-138`. Recommendation: add a CLI-only flag or environment variable in tests (or skip the test when GUI deps are installed).

**Test Coverage Notes**
1. Missing tests for case-insensitive redaction and prefix-coverage behavior in `redact_pdf()`.
2. No tests assert OCR-driven redaction functionality (image-only PDFs in redaction path).
3. No tests validate report includes input source hash or per-file redaction counts.
4. UI workflows (ingest, regex validation, language selection) are not covered by tests.

**Suggested Next Steps**
1. Fix the redaction search path to be case-insensitive and to redact full prefix/regex matches (not just substrings), and add tests for these cases.
2. Wire OCR textpages into redaction rectangle lookup, or explicitly scope OCR-only redaction out and document the limitation.
3. Update report schema to include input hash and `redactions_applied`, and align UI rendering with the new fields.
4. Complete Phase 7.4 UI workflows, then implement Phase 8 packaging (`build.py` or PyInstaller spec) per plan.

**Verification Performed**
- Tests not run (review based on static analysis only).
