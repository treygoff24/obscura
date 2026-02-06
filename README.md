# Obscura

Local-only, keyword-based PDF redaction. Your documents never leave your machine.

Obscura blacks out sensitive words and phrases in PDFs — names, dollar amounts, account numbers, anything you specify. It works on both digital and scanned documents, strips hidden metadata, and generates a verification report so you can confirm nothing was missed.

Everything runs locally. No cloud services, no uploads, no network calls.

## Features

- **Keyword-based redaction** — plain words, multi-word phrases, wildcards (`investor*`), dollar amounts, and regex patterns
- **Scanned document support** — OCR via Tesseract handles image-based and scanned PDFs (English + Spanish)
- **True redaction** — removes text from the PDF content stream, not just a visual overlay
- **Metadata sanitization** — strips document properties, annotations, embedded files, and incremental save history
- **Verification reports** — flags any residual keyword matches, low-confidence OCR pages, and unreadable pages
- **Deep verify mode** — rasterizes and rescans each page for high-stakes review
- **Project-based workflow** — organize redaction jobs with separate keyword lists and document sets
- **Desktop GUI + CLI** — point-and-click interface or command-line for automation

## Install

### macOS App

1. Download the latest `.dmg` from [Releases](https://github.com/treygoff24/obscura/releases)
2. Open the `.dmg` and drag **Obscura** into Applications
3. Open Obscura from Applications

No terminal or Python setup required.

### From Source

```bash
pip install git+https://github.com/treygoff24/obscura.git
```

Requires Python 3.12+ and [Tesseract](https://github.com/tesseract-ocr/tesseract) for OCR.

## How It Works

1. **Create a project** — give it a name and a folder
2. **Add keywords** — one per line in the keyword editor (or `keywords.txt`)
3. **Add PDFs** — drop files into the project
4. **Run** — Obscura redacts every keyword match, sanitizes metadata, and produces a verification report
5. **Review** — check the report for any flagged pages, then find your redacted files in the output folder (saved as `*_redacted.pdf`)

### Keyword Format

| Syntax | Example | Matches |
|--------|---------|---------|
| Plain word | `Acme` | "Acme" as a whole word (case-insensitive) |
| Multi-word phrase | `John Smith` | "John Smith" as an exact phrase |
| Wildcard | `investor*` | "investor", "investors", "investor-relations" |
| Dollar amount | `$5,000` | "$5,000" literally |
| Regex | `regex:\b\d{3}-\d{2}-\d{4}\b` | SSN-formatted numbers |

## CLI Usage

```bash
# Create a project
obscura create --root ~/redactions --name "Case 2026-01"

# Add keywords to the project's keywords.txt, then:
obscura run ~/redactions/case-2026-01

# Run with deep verification
obscura run ~/redactions/case-2026-01 --deep-verify --verbose

# View the latest report
obscura report ~/redactions/case-2026-01 --last
```

## Development

```bash
git clone https://github.com/treygoff24/obscura.git
cd obscura
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui]"
python -m pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

### Building the macOS App

```bash
pip install -e ".[ui,build]"
./scripts/package_macos.sh
```

Produces `dist/Obscura.app` and release artifacts in `release/`. Optional code signing:

```bash
export OBSCURA_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export OBSCURA_NOTARY_PROFILE="AC_PASSWORD_PROFILE"
./scripts/package_macos.sh
```

## Dependency Licensing

Obscura is MIT-licensed. However, its core dependency [PyMuPDF](https://pymupdf.readthedocs.io/) is licensed under **AGPL-3.0** (with a commercial license available from [Artifex](https://artifex.com/products/pymupdf-pro)).

- **Using Obscura from source** (via `pip install`): PyMuPDF's AGPL terms apply to PyMuPDF itself. Your use of Obscura's MIT-licensed code is unrestricted.
- **Distributing a bundled app**: If you redistribute Obscura as a packaged application that includes PyMuPDF, AGPL obligations apply to the distribution. See [PyMuPDF's licensing page](https://pymupdf.readthedocs.io/en/latest/about.html#license) for details.

## License

MIT
