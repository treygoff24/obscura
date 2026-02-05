# Obscura

Local-only PDF redaction tool with OCR support.

## Tech Stack

- **Language**: Python 3.12+
- **PDF Handling**: PyMuPDF (fitz) — pending licensing decision (AGPL)
- **OCR**: Tesseract (via PyMuPDF integration)
- **Regex**: `regex` module (not stdlib `re`) for timeout support
- **Desktop UI**: pywebview
- **Packaging**: PyInstaller

## Directory Structure

```
obscura/
├── src/obscura/          Application source
├── tests/                Test suite
├── docs/plans/           Design documents
└── .venv/                Python virtual environment
```

## Key Commands

| Command | Description |
|---------|-------------|
| `python -m pytest tests/` | Run test suite |
| `python -m obscura` | Run the desktop app |

## Architecture

See `docs/plans/2026-02-04-obscura-design.md` for the full design document.

Core pipeline: **Redact** (keyword matching + black box) → **Sanitize** (metadata, annotations, embedded files) → **Verify** (residual scan, OCR confidence, image detection).

## Conventions

- Keywords file: one term per line
- Prefix matching: append `*` (e.g., `investor*`)
- Regex patterns: prefix with `regex:` (e.g., `regex:\binvestor\b`)
- Case-insensitive matching throughout
- Projects are self-contained folders with `project.json` + `keywords.txt`
