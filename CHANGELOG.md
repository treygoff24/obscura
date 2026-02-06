# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-02-06

### Fixed
- Prevented report-file overwrite collisions for rapid back-to-back runs by using unique report filenames.
- Pruned stale PDF outputs when source input files are removed from a project.
- Added explicit `_redacted` output naming for generated files.
- Prevented output-file collisions when input names map to the same redacted base (for example, `doc.pdf` and `doc_redacted.pdf`).
- Ensured preview/reveal resolves the correct output file using latest report mappings.
- Restored ARIA list semantics for the documents list (`role="list"` with `role="listitem"` children).

### Changed
- Added test coverage for naming collisions, report mapping resolution, and ARIA list semantics.
