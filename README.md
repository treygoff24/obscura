# Obscura

Local-only, keyword-based PDF redaction. Your documents never leave your machine.

Obscura is a desktop tool for batch-redacting sensitive information from PDFs. It supports keyword matching, regex patterns, OCR for scanned documents, and post-redaction verification to catch anything that slipped through.

## Features

- **Project-based workflow** — organize redaction jobs by matter, each with its own keyword list and documents
- **Keyword matching** — single words, multi-word phrases, wildcards, dollar amounts, and custom regex patterns
- **OCR support** — automatically handles scanned/image-based PDFs via Tesseract (English + Spanish)
- **Legal-grade redaction** — removes underlying text from the PDF content stream, not just visual overlay
- **Post-redaction sanitization** — scrubs metadata, annotations, embedded files, and incremental PDF history
- **Verification reports** — flags residual matches, low-confidence OCR pages, and unreadable pages so you know where to look
- **Deep verify mode** — rasterize-and-rescan for high-stakes jobs
- **Desktop GUI + CLI** — point-and-click interface for non-technical users, CLI for power users and automation

## Status

Obscura is in the design phase. See [`docs/plans/2026-02-04-obscura-design.md`](docs/plans/2026-02-04-obscura-design.md) for the full design document.

## Requirements

- macOS (desktop app)
- Python 3.12+
- Tesseract (bundled in `.app` release, or `brew install tesseract` for development)

## License

MIT
