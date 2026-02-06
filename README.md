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

## Install (macOS)

For non-technical users:

1. Download the latest `.dmg` from your project’s GitHub Releases page.
2. Open the `.dmg`.
3. Drag `Obscura.app` into `Applications`.
4. Open `Obscura` from `Applications`.

No terminal setup is required for end users.

## Development Requirements

- macOS
- Python 3.12+
- Tesseract language data (for local development OCR)

## Build Release Artifacts (Maintainers)

This produces a desktop app plus distributable files:
- `dist/Obscura.app`
- `release/Obscura-<version>-macos-<arch>.zip`
- `release/Obscura-<version>-macos-<arch>.dmg`

```bash
python -m pip install .[ui,build]
./scripts/package_macos.sh
```

Default OCR language bundle is `eng+spa`. To build English-only:

```bash
OBSCURA_LANGUAGES=eng ./scripts/package_macos.sh
```

Optional signing and notarization:

```bash
export OBSCURA_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export OBSCURA_NOTARY_PROFILE="AC_PASSWORD_PROFILE"
./scripts/package_macos.sh
```

If signing and notarization are enabled, Gatekeeper will treat the app as a standard downloadable Mac app.

Detailed release steps are in `docs/release-macos.md`.

## Dependency Licensing

Obscura is MIT-licensed. However, its core dependency [PyMuPDF](https://pymupdf.readthedocs.io/) is licensed under **AGPL-3.0** (with a commercial license available from [Artifex](https://artifex.com/products/pymupdf-pro)).

- **Using Obscura from source** (via `pip install`): PyMuPDF's AGPL terms apply to PyMuPDF itself. Your use of Obscura's MIT-licensed code is unrestricted.
- **Distributing a bundled app**: If you redistribute Obscura as a packaged application that includes PyMuPDF, AGPL obligations apply to the distribution. See [PyMuPDF's licensing page](https://pymupdf.readthedocs.io/en/latest/about.html#license) for details.

## License

MIT
