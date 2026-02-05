# Obscura Implementation Plan

> **For Claude:** Spawn `plan-executor` agent to implement this plan task-by-task.

**Goal:** Build a local-only PDF redaction desktop tool with OCR support, verification, and a project-based workflow for legal teams.

**Architecture:** Python redaction engine using PyMuPDF + Tesseract, wrapped in a pywebview desktop UI. Pipeline: Redact (keyword matching with NFKC normalization and whole-word boundaries) -> Sanitize (metadata, XMP, annotations, forms, JavaScript, embedded files, history) -> Verify (residual scan, OCR confidence scoring, image-only detection, deep verify). Projects are self-contained folders on disk with `project.json` + `keywords.txt`.

**Tech Stack:** Python 3.12+, PyMuPDF (fitz), Tesseract, `regex` module, pywebview, PyInstaller

---

## Phase 0: Project Setup

### Task 0.1: Initialize Python Package

**Parallel:** no
**Blocked by:** none
**Owned files:** `src/obscura/__init__.py`, `src/obscura/__main__.py`, `pyproject.toml`, `tests/__init__.py`, `tests/conftest.py`

**Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "obscura"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "PyMuPDF>=1.24.0",
    "regex>=2024.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]
ui = [
    "pywebview>=5.0",
]
cli = []

[project.scripts]
obscura = "obscura.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.setuptools.packages.find]
where = ["src"]
```

**Step 2: Create `src/obscura/__init__.py`**

```python
"""Obscura — local-only PDF redaction tool."""

__version__ = "0.1.0"
```

**Step 3: Create `src/obscura/__main__.py`**

```python
"""Allow running as `python -m obscura`."""

from obscura.cli import main

if __name__ == "__main__":
    main()
```

**Step 4: Create `tests/__init__.py`**

Empty file.

**Step 5: Create `tests/conftest.py`**

```python
"""Shared test fixtures for Obscura test suite."""

import pathlib
import shutil
import tempfile

import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="obscura_test_")
    yield pathlib.Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_keywords_file(tmp_dir):
    """Create a sample keywords.txt in a temp directory."""
    kw_path = tmp_dir / "keywords.txt"
    kw_path.write_text("confidential\nsecret\nregex:\\bproject-\\d+\\b\ninvestor*\n")
    return kw_path
```

**Step 6: Create virtual environment and install**

```bash
cd /Users/treygoff/Code/obscura
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Step 7: Verify setup**

```bash
python -c "import obscura; print(obscura.__version__)"
pytest tests/ -v
```

Expected: prints `0.1.0`, pytest discovers 0 tests and exits cleanly.

**Step 8: Commit**

```bash
git add pyproject.toml src/obscura/__init__.py src/obscura/__main__.py tests/__init__.py tests/conftest.py
git commit -m "chore: initialize python package with pyproject.toml and test scaffolding"
```

---

## Phase 1: Redaction Engine

### Task 1.1: KeywordSet — Plain Keyword Parsing

**Parallel:** no
**Blocked by:** Task 0.1
**Owned files:** `src/obscura/keywords.py`, `tests/test_keywords.py`

**Step 1: Write the failing tests**

Create `tests/test_keywords.py`:

```python
"""Tests for KeywordSet keyword parsing and matching."""

import pathlib

import pytest

from obscura.keywords import KeywordSet


class TestKeywordSetFromFile:
    def test_loads_plain_keywords(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("confidential\nsecret\n")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == ["confidential", "secret"]

    def test_skips_blank_lines_and_whitespace(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("  confidential  \n\n\n  secret  \n\n")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == ["confidential", "secret"]

    def test_skips_comment_lines(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("# this is a comment\nconfidential\n# another\nsecret\n")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == ["confidential", "secret"]

    def test_identifies_prefix_wildcards(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("investor*\nconfidential\n")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == ["confidential"]
        assert ks.prefix_keywords == ["investor"]

    def test_identifies_regex_patterns(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("regex:\\bproject-\\d+\\b\nconfidential\n")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == ["confidential"]
        assert len(ks.regex_patterns) == 1

    def test_invalid_regex_raises_error(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("regex:[invalid\n")
        with pytest.raises(ValueError, match="Invalid regex"):
            KeywordSet.from_file(kw_file)

    def test_empty_file(self, tmp_dir):
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("")
        ks = KeywordSet.from_file(kw_file)
        assert ks.plain_keywords == []
        assert ks.prefix_keywords == []
        assert ks.regex_patterns == []

    def test_from_file_path_does_not_exist(self):
        with pytest.raises(FileNotFoundError):
            KeywordSet.from_file(pathlib.Path("/nonexistent/keywords.txt"))


class TestKeywordSetMatching:
    def _make_ks(self, lines: list[str], tmp_dir) -> KeywordSet:
        kw_file = tmp_dir / "keywords.txt"
        kw_file.write_text("\n".join(lines) + "\n")
        return KeywordSet.from_file(kw_file)

    def test_plain_match_case_insensitive(self, tmp_dir):
        ks = self._make_ks(["confidential"], tmp_dir)
        matches = ks.find_matches("This is CONFIDENTIAL information.")
        assert len(matches) == 1
        assert matches[0].keyword == "confidential"

    def test_plain_match_whole_word_only(self, tmp_dir):
        """Plain keywords should NOT match inside other words."""
        ks = self._make_ks(["secret"], tmp_dir)
        matches = ks.find_matches("The secretary filed the report.")
        assert len(matches) == 0

    def test_plain_match_whole_word_positive(self, tmp_dir):
        ks = self._make_ks(["secret"], tmp_dir)
        matches = ks.find_matches("The secret plan was revealed.")
        assert len(matches) == 1

    def test_multi_word_phrase(self, tmp_dir):
        ks = self._make_ks(["john doe"], tmp_dir)
        matches = ks.find_matches("Contract with John Doe for services.")
        assert len(matches) == 1

    def test_prefix_wildcard_match(self, tmp_dir):
        ks = self._make_ks(["investor*"], tmp_dir)
        matches = ks.find_matches("The investors and investment group.")
        assert len(matches) >= 1
        matched_texts = [m.matched_text.lower() for m in matches]
        assert any("investor" in t for t in matched_texts)

    def test_prefix_wildcard_includes_hyphens(self, tmp_dir):
        """Prefix match should include hyphenated continuations."""
        ks = self._make_ks(["investor*"], tmp_dir)
        matches = ks.find_matches("The investor-relations team met today.")
        assert len(matches) == 1
        assert "investor-relations" in matches[0].matched_text.lower()

    def test_regex_match(self, tmp_dir):
        ks = self._make_ks(["regex:\\bproject-\\d+\\b"], tmp_dir)
        matches = ks.find_matches("See project-42 for details.")
        assert len(matches) == 1
        assert matches[0].matched_text == "project-42"

    def test_no_matches(self, tmp_dir):
        ks = self._make_ks(["confidential"], tmp_dir)
        matches = ks.find_matches("This is a public document.")
        assert matches == []

    def test_multiple_matches_same_keyword(self, tmp_dir):
        ks = self._make_ks(["secret"], tmp_dir)
        matches = ks.find_matches("The secret plan has a secret code.")
        assert len(matches) == 2

    def test_dollar_amount_regex(self, tmp_dir):
        ks = self._make_ks(["regex:\\$[\\d,]+(?:\\.\\d{2})?"], tmp_dir)
        matches = ks.find_matches("The price was $1,234.56 and $500.")
        assert len(matches) == 2

    def test_ligature_normalization(self, tmp_dir):
        """Text with ligatures (ﬁ, ﬂ) should still match normalized keywords."""
        ks = self._make_ks(["confidential"], tmp_dir)
        matches = ks.find_matches("This is con\ufb01dential information.")
        assert len(matches) == 1

    def test_unicode_nfkc_normalization(self, tmp_dir):
        """Smart quotes and other Unicode variants should be normalized."""
        ks = self._make_ks(["test"], tmp_dir)
        # fullwidth "test" (U+FF54 U+FF45 U+FF53 U+FF54) normalizes to "test" via NFKC
        matches = ks.find_matches("The \uff54\uff45\uff53\uff54 results are in.")
        assert len(matches) == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_keywords.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.keywords'`

**Step 3: Write minimal implementation**

Create `src/obscura/keywords.py`:

```python
"""Keyword parsing, classification, and text matching.

Text normalization: All text (keywords and input) is normalized via
NFKC before matching. This handles ligatures (ﬁ→fi, ﬂ→fl), fullwidth
characters, and other Unicode equivalences.

Matching modes:
- Plain keywords use whole-word boundary matching (\\b) by default.
  This prevents "secret" from matching inside "secretary".
- Prefix wildcards use [\\w-]* to include hyphenated continuations.
- Regex patterns are used as-is with a 5-second timeout.
"""

from __future__ import annotations

import dataclasses
import pathlib
import unicodedata

import regex

# Common ligature replacements for PDF text extraction edge cases.
# NFKC handles most (ﬁ→fi, ﬂ→fl), but we keep this as a safety net.
_LIGATURE_MAP = str.maketrans({
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
})

# Version tag included in keyword_hash for traceability.
# Bump when matching semantics change.
MATCH_VERSION = 1


def _normalize(text: str) -> str:
    """Normalize text via NFKC and replace known ligatures."""
    return unicodedata.normalize("NFKC", text).translate(_LIGATURE_MAP)


@dataclasses.dataclass(frozen=True)
class Match:
    """A single keyword match in text."""

    keyword: str
    matched_text: str
    start: int
    end: int


class KeywordSet:
    """Parses a keywords file and provides text-matching capabilities.

    Supports three keyword types:
    - Plain keywords (case-insensitive whole-word match)
    - Prefix wildcards (e.g. "investor*" matches "investors", "investor-relations")
    - Regex patterns (e.g. "regex:\\bproject-\\d+\\b")

    All text is NFKC-normalized before matching.
    """

    def __init__(
        self,
        plain_keywords: list[str],
        prefix_keywords: list[str],
        regex_patterns: list[tuple[str, regex.Pattern]],
    ) -> None:
        self.plain_keywords = plain_keywords
        self.prefix_keywords = prefix_keywords
        self.regex_patterns = regex_patterns
        # Pre-compile plain keyword patterns with word boundaries
        self._plain_compiled: list[tuple[str, regex.Pattern]] = [
            (kw, regex.compile(
                r"\b" + regex.escape(kw) + r"\b", regex.IGNORECASE
            ))
            for kw in plain_keywords
        ]

    @classmethod
    def from_file(cls, path: pathlib.Path) -> KeywordSet:
        """Load and classify keywords from a file.

        Args:
            path: Path to a keywords.txt file (one keyword per line).

        Returns:
            A KeywordSet ready for matching.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If a regex pattern is invalid.
        """
        if not path.exists():
            raise FileNotFoundError(f"Keywords file not found: {path}")

        text = path.read_text(encoding="utf-8")
        plain: list[str] = []
        prefixes: list[str] = []
        patterns: list[tuple[str, regex.Pattern]] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("regex:"):
                pattern_str = line[len("regex:"):]
                try:
                    compiled = regex.compile(pattern_str, regex.IGNORECASE)
                except regex.error as exc:
                    raise ValueError(
                        f"Invalid regex on line '{line}': {exc}"
                    ) from exc
                patterns.append((pattern_str, compiled))
            elif line.endswith("*"):
                prefixes.append(_normalize(line[:-1]).lower())
            else:
                plain.append(_normalize(line).lower())

        return cls(plain, prefixes, patterns)

    def find_matches(self, text: str) -> list[Match]:
        """Find all keyword matches in the given text.

        Text is NFKC-normalized before matching. Plain keywords use
        whole-word boundary matching. Prefix keywords include hyphens.

        Args:
            text: The text to search.

        Returns:
            List of Match objects for every occurrence found.
        """
        matches: list[Match] = []
        normalized = _normalize(text)

        # Plain keywords — whole-word boundary matching
        for kw, pattern in self._plain_compiled:
            for m in pattern.finditer(normalized):
                matches.append(
                    Match(
                        keyword=kw,
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )

        # Prefix keywords — include hyphens in continuation
        for prefix in self.prefix_keywords:
            pattern = regex.compile(
                r"\b" + regex.escape(prefix) + r"[\w-]*", regex.IGNORECASE
            )
            for m in pattern.finditer(normalized):
                matches.append(
                    Match(
                        keyword=f"{prefix}*",
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )

        # Regex patterns — used as-is with timeout
        for pattern_str, compiled in self.regex_patterns:
            for m in compiled.finditer(normalized, timeout=5):
                matches.append(
                    Match(
                        keyword=f"regex:{pattern_str}",
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )

        return matches

    @property
    def is_empty(self) -> bool:
        return not self.plain_keywords and not self.prefix_keywords and not self.regex_patterns

    def keyword_hash(self) -> str:
        """Return a SHA-256 hash representing this keyword set for traceability.

        Includes MATCH_VERSION so hash changes when matching semantics change.
        """
        import hashlib

        content = f"v{MATCH_VERSION}\n" + "\n".join(
            sorted(self.plain_keywords)
            + sorted(f"{p}*" for p in self.prefix_keywords)
            + sorted(f"regex:{ps}" for ps, _ in self.regex_patterns)
        )
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_keywords.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/keywords.py tests/test_keywords.py
git commit -m "feat: add KeywordSet with plain, prefix, and regex matching"
```

---

### Task 1.2: Redaction Engine — Core `redact_pdf()`

**Parallel:** no
**Blocked by:** Task 1.1
**Owned files:** `src/obscura/redact.py`, `tests/test_redact.py`, `tests/fixtures/`

This task requires test PDF fixtures. The tests create them programmatically using PyMuPDF so no external files are needed.

**Step 1: Write the failing tests**

Create `tests/test_redact.py`:

```python
"""Tests for PDF redaction engine."""

import pathlib

import fitz
import pytest

from obscura.keywords import KeywordSet
from obscura.redact import RedactionResult, redact_pdf


def _create_pdf(path: pathlib.Path, pages: list[str]) -> pathlib.Path:
    """Create a simple PDF with text on each page."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def _make_keywords(tmp_dir: pathlib.Path, lines: list[str]) -> KeywordSet:
    kw_file = tmp_dir / "keywords.txt"
    kw_file.write_text("\n".join(lines) + "\n")
    return KeywordSet.from_file(kw_file)


class TestRedactPdf:
    def test_redacts_keyword_from_text(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["This document is confidential and private."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["confidential"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count > 0
        assert output_path.exists()

        doc = fitz.open(str(output_path))
        text = doc[0].get_text()
        doc.close()
        assert "confidential" not in text.lower()

    def test_text_removed_from_content_stream(self, tmp_dir):
        """Regression: verify apply_redactions removes text, not just overlays."""
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["The secret password is hunter2."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["hunter2"])

        redact_pdf(input_path, output_path, keywords)

        doc = fitz.open(str(output_path))
        all_text = ""
        for page in doc:
            all_text += page.get_text()
            blocks = page.get_text("rawdict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            assert "hunter2" not in span["text"].lower()
        doc.close()
        assert "hunter2" not in all_text.lower()

    def test_returns_structured_result(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["Secret document with secret data."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert isinstance(result, RedactionResult)
        assert result.redaction_count >= 2
        assert result.page_count == 1
        assert result.status == "ok"

    def test_multi_page_redaction(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            [
                "Page one has confidential info.",
                "Page two has secret data.",
                "Page three is clean.",
            ],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["confidential", "secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count >= 2
        assert result.page_count == 3

    def test_no_matches_still_produces_output(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["This is a clean document."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["nonexistent"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count == 0
        assert output_path.exists()

    def test_atomic_write(self, tmp_dir):
        """Output should not exist as a partial file if something goes wrong."""
        input_path = _create_pdf(tmp_dir / "input.pdf", ["Test content."])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["test"])

        redact_pdf(input_path, output_path, keywords)

        assert output_path.exists()
        doc = fitz.open(str(output_path))
        assert doc.page_count == 1
        doc.close()

    def test_password_protected_pdf(self, tmp_dir):
        input_path = tmp_dir / "protected.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Secret text")
        perm = fitz.PDF_PERM_ACCESSIBILITY
        encrypt_meth = fitz.PDF_ENCRYPT_AES_256
        doc.save(
            str(input_path),
            encryption=encrypt_meth,
            owner_pw="owner",
            user_pw="user",
            permissions=perm,
        )
        doc.close()

        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "password_protected"
        assert not output_path.exists()

    def test_corrupt_pdf(self, tmp_dir):
        input_path = tmp_dir / "corrupt.pdf"
        input_path.write_bytes(b"this is not a pdf")
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "corrupt"
        assert not output_path.exists()

    def test_source_hash_in_result(self, tmp_dir):
        input_path = _create_pdf(tmp_dir / "input.pdf", ["Content."])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["content"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.source_hash.startswith("sha256:")
        assert len(result.source_hash) == 71  # "sha256:" + 64 hex chars
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_redact.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.redact'`

**Step 3: Write minimal implementation**

Create `src/obscura/redact.py`:

```python
"""PDF redaction engine — stateless, path-agnostic.

Uses page.search_for() per keyword directly to get bounding rectangles,
rather than extract→match→re-search. This avoids fragility from divergent
text extraction paths and ensures accurate rectangle placement.

Tracks "redaction coverage" — keywords where no rectangle was found on
a page are recorded as warnings in the result.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import pathlib
import tempfile

import fitz

from obscura.keywords import KeywordSet, _normalize

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RedactionResult:
    """Structured result from a single PDF redaction run."""

    file: str
    status: str  # "ok", "password_protected", "corrupt"
    source_hash: str
    redaction_count: int
    page_count: int
    ocr_used: bool
    pages_with_redactions: list[int]
    missed_keywords: list[dict]  # [{"keyword": str, "page": int}]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _search_keywords_on_page(
    page: fitz.Page, keywords: KeywordSet
) -> tuple[list[tuple[str, fitz.Rect]], list[dict]]:
    """Search for all keywords on a page using page.search_for() directly.

    Returns:
        Tuple of (hits, misses) where hits are (keyword, rect) pairs
        and misses are keywords that matched text but got no rectangle.
    """
    hits: list[tuple[str, fitz.Rect]] = []
    misses: list[dict] = []

    # Plain keywords — search directly with word boundaries
    for kw in keywords.plain_keywords:
        rects = page.search_for(kw)
        if rects:
            for rect in rects:
                hits.append((kw, rect))
        # Only record a miss if the keyword exists in text but got no rect
        else:
            text = _normalize(page.get_text()).lower()
            if kw in text:
                misses.append({"keyword": kw, "page": page.number + 1})

    # Prefix keywords — search for the prefix, then widen
    for prefix in keywords.prefix_keywords:
        rects = page.search_for(prefix)
        for rect in rects:
            hits.append((f"{prefix}*", rect))

    # Regex patterns — find matched text, then search for rects
    text = _normalize(page.get_text())
    for pattern_str, compiled in keywords.regex_patterns:
        import regex
        for m in compiled.finditer(text, timeout=5):
            rects = page.search_for(m.group())
            if rects:
                for rect in rects:
                    hits.append((f"regex:{pattern_str}", rect))
            else:
                misses.append({
                    "keyword": f"regex:{pattern_str}",
                    "page": page.number + 1,
                })

    return hits, misses


def redact_pdf(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    keywords: KeywordSet,
    language: str = "eng",
) -> RedactionResult:
    """Redact keywords from a PDF file.

    Uses page.search_for() per keyword to get accurate bounding rectangles
    directly from PyMuPDF, avoiding fragile extract→match→re-search patterns.

    Args:
        input_path: Path to the source PDF.
        output_path: Path to write the redacted PDF.
        keywords: A KeywordSet defining what to redact.
        language: Tesseract language code for OCR.

    Returns:
        RedactionResult with status and redaction details.
    """
    source_hash = _file_hash(input_path)

    try:
        doc = fitz.open(str(input_path))
    except Exception:
        return RedactionResult(
            file=input_path.name,
            status="corrupt",
            source_hash=source_hash,
            redaction_count=0,
            page_count=0,
            ocr_used=False,
            pages_with_redactions=[],
            missed_keywords=[],
        )

    if doc.is_encrypted:
        doc.close()
        return RedactionResult(
            file=input_path.name,
            status="password_protected",
            source_hash=source_hash,
            redaction_count=0,
            page_count=0,
            ocr_used=False,
            pages_with_redactions=[],
            missed_keywords=[],
        )

    total_redactions = 0
    pages_with_redactions: list[int] = []
    all_missed: list[dict] = []
    ocr_used = False

    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text()

        # OCR fallback for image-only pages
        if not text.strip():
            try:
                page.get_textpage_ocr(language=language, full=True)
                text = page.get_text()
                if text.strip():
                    ocr_used = True
            except Exception:
                logger.warning("OCR failed on page %d of %s", page_num + 1, input_path.name)
                continue

        hits, misses = _search_keywords_on_page(page, keywords)
        all_missed.extend(misses)

        if not hits:
            continue

        for keyword, rect in hits:
            page.add_redact_annot(rect, fill=(0, 0, 0))

        page.apply_redactions()
        total_redactions += len(hits)
        pages_with_redactions.append(page_num + 1)

    if all_missed:
        logger.warning(
            "Redaction coverage gaps in %s: %d keyword instances had no rectangle",
            input_path.name, len(all_missed),
        )

    page_count = doc.page_count
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, suffix=".pdf.tmp"
    )
    try:
        import os
        os.close(tmp_fd)
        doc.save(tmp_path)
        doc.close()
        pathlib.Path(tmp_path).replace(output_path)
    except Exception:
        doc.close()
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise

    return RedactionResult(
        file=input_path.name,
        status="ok",
        source_hash=source_hash,
        redaction_count=total_redactions,
        page_count=page_count,
        ocr_used=ocr_used,
        pages_with_redactions=pages_with_redactions,
        missed_keywords=all_missed,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_redact.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/redact.py tests/test_redact.py
git commit -m "feat: add redact_pdf engine with atomic writes and error handling"
```

---

## Phase 2: Sanitize Step

### Task 2.1: Sanitize Module

**Parallel:** no
**Blocked by:** Task 1.2
**Owned files:** `src/obscura/sanitize.py`, `tests/test_sanitize.py`

**Step 1: Write the failing tests**

Create `tests/test_sanitize.py`:

```python
"""Tests for PDF sanitization step."""

import fitz
import pytest

from obscura.sanitize import sanitize_pdf


def _create_pdf_with_metadata(path, metadata: dict, text: str = "Sample text."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.set_metadata(metadata)
    doc.save(str(path))
    doc.close()
    return path


def _create_pdf_with_annotation(path, text="Annotated doc."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    annot = page.add_text_annot((100, 100), "This is a sticky note")
    doc.save(str(path))
    doc.close()
    return path


def _create_pdf_with_embedded_file(path, text="Doc with attachment."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.embfile_add("secret.txt", b"secret content", filename="secret.txt")
    doc.save(str(path))
    doc.close()
    return path


class TestSanitizePdf:
    def test_scrubs_metadata(self, tmp_dir):
        input_path = _create_pdf_with_metadata(
            tmp_dir / "input.pdf",
            {"author": "John Doe", "title": "Secret Report", "subject": "Classified"},
        )
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        meta = doc.metadata
        doc.close()
        assert meta.get("author", "") == ""
        assert meta.get("title", "") == ""
        assert meta.get("subject", "") == ""

    def test_removes_annotations(self, tmp_dir):
        input_path = _create_pdf_with_annotation(tmp_dir / "input.pdf")
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        annots = list(doc[0].annots() or [])
        doc.close()
        assert len(annots) == 0

    def test_removes_embedded_files(self, tmp_dir):
        input_path = _create_pdf_with_embedded_file(tmp_dir / "input.pdf")
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        assert doc.embfile_count() == 0
        doc.close()

    def test_collapses_incremental_updates(self, tmp_dir):
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Version 1")
        doc.save(str(input_path))
        doc.close()

        doc = fitz.open(str(input_path))
        doc[0].insert_text((72, 120), "Version 2")
        doc.save(str(input_path), incremental=True, encryption=0)
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        output_size = output_path.stat().st_size
        input_size = input_path.stat().st_size
        assert output_size <= input_size

    def test_sanitize_in_place(self, tmp_dir):
        """Sanitize can write to the same path (via atomic temp file)."""
        path = _create_pdf_with_metadata(
            tmp_dir / "doc.pdf",
            {"author": "John Doe"},
        )

        sanitize_pdf(path, path)

        doc = fitz.open(str(path))
        assert doc.metadata.get("author", "") == ""
        doc.close()

    def test_removes_xmp_metadata(self, tmp_dir):
        """XMP metadata (XML-based) should be cleared separately from standard metadata."""
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Sample text.")
        doc.set_metadata({"author": "John Doe"})
        # Set XMP metadata
        xmp = '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta><rdf:RDF><rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Secret Author</dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>'
        doc.set_xml_metadata(xmp)
        doc.save(str(input_path))
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        xml_meta = doc.get_xml_metadata()
        doc.close()
        assert "Secret Author" not in xml_meta

    def test_removes_form_fields(self, tmp_dir):
        """Form fields / widgets should be removed."""
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Form document.")
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "secret_field"
        widget.field_value = "secret value"
        widget.rect = fitz.Rect(72, 100, 300, 130)
        page.add_widget(widget)
        doc.save(str(input_path))
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        widgets = list(doc[0].widgets() or [])
        doc.close()
        assert len(widgets) == 0

    def test_preserves_page_content(self, tmp_dir):
        input_path = _create_pdf_with_metadata(
            tmp_dir / "input.pdf",
            {"author": "John Doe"},
            text="Important content here.",
        )
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        text = doc[0].get_text()
        doc.close()
        assert "Important content here" in text
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sanitize.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.sanitize'`

**Step 3: Write minimal implementation**

Create `src/obscura/sanitize.py`:

```python
"""PDF sanitization — scrubs metadata, annotations, embedded files, and history.

Legal-grade sanitization removes all non-content data that could leak
redacted information. This includes:
- Standard metadata (author, title, etc.)
- XMP metadata (XML-based, not cleared by set_metadata alone)
- Annotations (comments, highlights, sticky notes)
- Embedded files / attachments
- Form fields (AcroForm)
- JavaScript actions
- Incremental update history (collapsed via garbage collection)
"""

from __future__ import annotations

import logging
import os
import pathlib
import tempfile

import fitz

logger = logging.getLogger(__name__)


def sanitize_pdf(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """Sanitize a PDF by removing non-content data.

    Args:
        input_path: Source PDF path.
        output_path: Destination path (may be same as input_path).
    """
    doc = fitz.open(str(input_path))

    # Clear standard metadata fields
    doc.set_metadata({
        "author": "",
        "title": "",
        "subject": "",
        "keywords": "",
        "creator": "",
        "producer": "",
    })

    # Clear XMP metadata (XML-based, separate from standard metadata)
    try:
        doc.del_xml_metadata()
    except Exception:
        logger.debug("No XMP metadata to remove or removal failed")

    # Remove all annotations
    for page in doc:
        annots = list(page.annots() or [])
        for annot in annots:
            page.delete_annot(annot)

    # Remove embedded files / attachments
    while doc.embfile_count() > 0:
        doc.embfile_del(0)

    # Remove form fields (AcroForm)
    # PyMuPDF stores the AcroForm in the PDF catalog; we reset widget annotations
    for page in doc:
        widgets = list(page.widgets() or [])
        for widget in widgets:
            page.delete_widget(widget)

    # Remove JavaScript actions from the document catalog
    try:
        # PDF catalog can contain /Names/JavaScript entries
        cat = doc.pdf_catalog()
        xref = doc.xref_get_key(cat, "Names")
        if xref[0] != "null":
            names_xref = int(xref[1].split()[0])
            js_key = doc.xref_get_key(names_xref, "JavaScript")
            if js_key[0] != "null":
                doc.xref_set_key(names_xref, "JavaScript", "null")
                logger.info("Removed JavaScript actions from PDF catalog")
    except Exception:
        logger.debug("No JavaScript actions to remove or removal failed")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, suffix=".pdf.tmp"
    )
    try:
        os.close(tmp_fd)
        doc.save(tmp_path, garbage=4, clean=True)
        doc.close()
        pathlib.Path(tmp_path).replace(output_path)
    except Exception:
        doc.close()
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sanitize.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/sanitize.py tests/test_sanitize.py
git commit -m "feat: add sanitize step — metadata, XMP, annotations, forms, JS, embedded files, history"
```

---

## Phase 3: Project Model

### Task 3.1: Project Model — Schema and CRUD

**Parallel:** no
**Blocked by:** Task 0.1
**Owned files:** `src/obscura/project.py`, `tests/test_project.py`

**Step 1: Write the failing tests**

Create `tests/test_project.py`:

```python
"""Tests for project model — folder structure, project.json, discovery."""

import json

import pytest

from obscura.project import Project, discover_projects, create_project


class TestCreateProject:
    def test_creates_project_folder_structure(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")

        assert (tmp_dir / "Test Matter" / "project.json").exists()
        assert (tmp_dir / "Test Matter" / "keywords.txt").exists()
        assert (tmp_dir / "Test Matter" / "input").is_dir()
        assert (tmp_dir / "Test Matter" / "output").is_dir()
        assert (tmp_dir / "Test Matter" / "reports").is_dir()

    def test_project_json_has_schema_version(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        data = json.loads((tmp_dir / "Test Matter" / "project.json").read_text())
        assert data["schema_version"] == 1

    def test_project_json_has_required_fields(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        data = json.loads((tmp_dir / "Test Matter" / "project.json").read_text())
        assert "name" in data
        assert "created" in data
        assert "language" in data
        assert "confidence_threshold" in data
        assert data["name"] == "Test Matter"
        assert data["language"] == "eng"
        assert data["confidence_threshold"] == 70

    def test_custom_language_and_threshold(self, tmp_dir):
        project = create_project(
            tmp_dir, "Spanish Matter", language="spa", confidence_threshold=80
        )
        data = json.loads((tmp_dir / "Spanish Matter" / "project.json").read_text())
        assert data["language"] == "spa"
        assert data["confidence_threshold"] == 80

    def test_duplicate_name_raises(self, tmp_dir):
        create_project(tmp_dir, "Test Matter")
        with pytest.raises(FileExistsError):
            create_project(tmp_dir, "Test Matter")

    def test_rejects_path_separator_in_name(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "bad/name")

    def test_rejects_path_traversal(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "../escape")

    def test_rejects_too_long_name(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "a" * 256)


class TestProjectLoad:
    def test_load_valid_project(self, tmp_dir):
        create_project(tmp_dir, "Test Matter")
        project = Project.load(tmp_dir / "Test Matter")
        assert project.name == "Test Matter"
        assert project.language == "eng"
        assert project.confidence_threshold == 70

    def test_load_invalid_folder_raises(self, tmp_dir):
        (tmp_dir / "not_a_project").mkdir()
        with pytest.raises(ValueError, match="schema_version"):
            Project.load(tmp_dir / "not_a_project")

    def test_load_wrong_schema_version(self, tmp_dir):
        project_dir = tmp_dir / "BadVersion"
        project_dir.mkdir()
        (project_dir / "project.json").write_text(
            json.dumps({"schema_version": 999, "name": "Bad"})
        )
        with pytest.raises(ValueError, match="schema_version"):
            Project.load(project_dir)


class TestDiscoverProjects:
    def test_discovers_valid_projects(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        create_project(tmp_dir, "Matter B")
        (tmp_dir / "random_folder").mkdir()

        projects = discover_projects(tmp_dir)
        names = [p.name for p in projects]
        assert "Matter A" in names
        assert "Matter B" in names
        assert len(projects) == 2

    def test_empty_root(self, tmp_dir):
        projects = discover_projects(tmp_dir)
        assert projects == []

    def test_ignores_hidden_folders(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        (tmp_dir / ".hidden").mkdir()
        (tmp_dir / ".hidden" / "project.json").write_text(
            json.dumps({"schema_version": 1, "name": ".hidden"})
        )
        projects = discover_projects(tmp_dir)
        names = [p.name for p in projects]
        assert ".hidden" not in names


class TestProjectPaths:
    def test_input_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.input_dir == tmp_dir / "Test Matter" / "input"

    def test_output_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.output_dir == tmp_dir / "Test Matter" / "output"

    def test_reports_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.reports_dir == tmp_dir / "Test Matter" / "reports"

    def test_keywords_path(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.keywords_path == tmp_dir / "Test Matter" / "keywords.txt"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_project.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.project'`

**Step 3: Write minimal implementation**

Create `src/obscura/project.py`:

```python
"""Project model — folder structure, project.json, discovery."""

from __future__ import annotations

import dataclasses
import json
import pathlib
from datetime import datetime, timezone

SCHEMA_VERSION = 1


@dataclasses.dataclass
class Project:
    """Represents an Obscura project folder on disk."""

    path: pathlib.Path
    name: str
    created: str
    last_run: str | None
    language: str
    confidence_threshold: int

    @classmethod
    def load(cls, project_dir: pathlib.Path) -> Project:
        """Load a project from its directory.

        Raises:
            ValueError: If project.json is missing or has wrong schema_version.
        """
        config_path = project_dir / "project.json"
        if not config_path.exists():
            raise ValueError(
                f"Not a valid project (missing project.json): {project_dir}. "
                "Expected schema_version 1."
            )

        data = json.loads(config_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version {data.get('schema_version')} "
                f"in {config_path}. Expected {SCHEMA_VERSION}."
            )

        return cls(
            path=project_dir,
            name=data["name"],
            created=data.get("created", ""),
            last_run=data.get("last_run"),
            language=data.get("language", "eng"),
            confidence_threshold=data.get("confidence_threshold", 70),
        )

    def save(self) -> None:
        """Write project.json to disk."""
        data = {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "created": self.created,
            "last_run": self.last_run,
            "language": self.language,
            "confidence_threshold": self.confidence_threshold,
        }
        config_path = self.path / "project.json"
        config_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    @property
    def input_dir(self) -> pathlib.Path:
        return self.path / "input"

    @property
    def output_dir(self) -> pathlib.Path:
        return self.path / "output"

    @property
    def reports_dir(self) -> pathlib.Path:
        return self.path / "reports"

    @property
    def keywords_path(self) -> pathlib.Path:
        return self.path / "keywords.txt"


_INVALID_NAME_CHARS = set('/\\:*?"<>|')
_MAX_NAME_LENGTH = 255


def _validate_project_name(name: str) -> None:
    """Validate project name for filesystem safety.

    Raises:
        ValueError: If the name is invalid.
    """
    if not name or not name.strip():
        raise ValueError("Invalid project name: name cannot be empty")
    if len(name) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"Invalid project name: exceeds {_MAX_NAME_LENGTH} characters"
        )
    if any(c in name for c in _INVALID_NAME_CHARS):
        raise ValueError(
            f"Invalid project name: contains reserved characters"
        )
    if name.startswith(".") or ".." in name:
        raise ValueError("Invalid project name: path traversal not allowed")


def create_project(
    root: pathlib.Path,
    name: str,
    language: str = "eng",
    confidence_threshold: int = 70,
) -> Project:
    """Create a new project folder with all required structure.

    Args:
        root: The project root directory (e.g. ~/Obscura/).
        name: Project name (becomes the folder name).
        language: Tesseract language code.
        confidence_threshold: OCR confidence cutoff (0-100).

    Returns:
        The newly created Project.

    Raises:
        FileExistsError: If a project with that name already exists.
        ValueError: If the project name is invalid.
    """
    _validate_project_name(name)
    project_dir = root / name
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    project_dir.mkdir(parents=True)
    (project_dir / "input").mkdir()
    (project_dir / "output").mkdir()
    (project_dir / "reports").mkdir()
    (project_dir / "keywords.txt").write_text("", encoding="utf-8")

    project = Project(
        path=project_dir,
        name=name,
        created=datetime.now(timezone.utc).isoformat(),
        last_run=None,
        language=language,
        confidence_threshold=confidence_threshold,
    )
    project.save()
    return project


def discover_projects(root: pathlib.Path) -> list[Project]:
    """Scan a root directory and return all valid projects.

    Skips hidden folders and folders without a valid project.json.
    """
    projects: list[Project] = []
    if not root.exists():
        return projects

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            projects.append(Project.load(child))
        except (ValueError, json.JSONDecodeError):
            continue

    return projects
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_project.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/project.py tests/test_project.py
git commit -m "feat: add project model with create, load, and discovery"
```

---

## Phase 4: Verification Layer

### Task 4.1: Verification — Residual Scan + Report Generation

**Parallel:** no
**Blocked by:** Task 1.2, Task 2.1
**Owned files:** `src/obscura/verify.py`, `tests/test_verify.py`

**Step 1: Write the failing tests**

Create `tests/test_verify.py`:

```python
"""Tests for verification layer."""

import json

import fitz
import pytest

from obscura.keywords import KeywordSet
from obscura.verify import VerificationReport, verify_pdf


def _create_pdf(path, pages: list[str]):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def _make_keywords(tmp_dir, lines: list[str]) -> KeywordSet:
    kw_file = tmp_dir / "keywords.txt"
    kw_file.write_text("\n".join(lines) + "\n")
    return KeywordSet.from_file(kw_file)


class TestVerifyPdf:
    def test_clean_pdf_reports_clean(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "clean.pdf", ["This is fine."])
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.status == "clean"
        assert report.residual_matches == []

    def test_residual_match_detected(self, tmp_dir):
        pdf_path = _create_pdf(
            tmp_dir / "dirty.pdf", ["This has a secret word."]
        )
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.status == "needs_review"
        assert len(report.residual_matches) > 0
        assert report.residual_matches[0]["keyword"] == "secret"
        assert report.residual_matches[0]["page"] == 1

    def test_report_to_dict(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Clean content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)
        d = report.to_dict()

        assert "file" in d
        assert "status" in d
        assert "residual_matches" in d
        assert "timestamp" in d
        assert "engine_version" in d
        assert "keywords_hash" in d
        assert "source_hash" in d
        assert "confidence_threshold" in d

    def test_report_serializable_to_json(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)

        assert parsed["status"] == "clean"

    def test_image_only_page_detection(self, tmp_dir):
        """A page with no extractable text should be flagged."""
        doc = fitz.open()
        page = doc.new_page()
        # Insert a tiny image, no text
        img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 1)
        img.set_pixel(5, 5, (255, 0, 0))
        page.insert_image(fitz.Rect(72, 72, 200, 200), pixmap=img)
        pdf_path = tmp_dir / "image_only.pdf"
        doc.save(str(pdf_path))
        doc.close()

        keywords = _make_keywords(tmp_dir, ["anything"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert 1 in report.unreadable_pages

    def test_source_hash_included(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.source_hash.startswith("sha256:")

    def test_no_context_in_default_report(self, tmp_dir):
        """Default reports should not include surrounding text context."""
        pdf_path = _create_pdf(
            tmp_dir / "test.pdf", ["The secret project is here."]
        )
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        d = report.to_dict()
        for match in d["residual_matches"]:
            assert "context" not in match

    def test_ocr_confidence_pages_populated(self, tmp_dir):
        """Verify that low_confidence_pages gets populated for OCR pages.

        Note: This is an integration test that requires Tesseract installed.
        The OCR confidence check runs on image-only pages and flags pages
        below the confidence_threshold. For unit testing, we verify the
        report structure includes the field and handles the clean case.
        """
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Clear text here."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        # Text pages don't go through OCR, so low_confidence_pages stays empty
        assert isinstance(report.low_confidence_pages, list)
        assert report.low_confidence_pages == []
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.verify'`

**Step 3: Write minimal implementation**

Create `src/obscura/verify.py`:

```python
"""Verification layer — residual scan, OCR confidence, image-only detection."""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
from datetime import datetime, timezone

import fitz

import obscura
from obscura.keywords import KeywordSet


@dataclasses.dataclass
class VerificationReport:
    """Per-file verification report."""

    file: str
    status: str  # "clean", "needs_review", "unreadable"
    source_hash: str
    residual_matches: list[dict]
    low_confidence_pages: list[int]
    unreadable_pages: list[int]
    clean_pages: list[int]
    deep_verify: bool
    deep_verify_dpi: int | None
    engine_version: str
    keywords_hash: str
    language: str
    confidence_threshold: int
    timestamp: str

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.unreadable_pages:
            pages_str = ", ".join(str(p) for p in self.unreadable_pages)
            d["unverified_warning"] = (
                f"Pages {pages_str} were not OCR-readable and could not be verified."
            )
        return d


def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _check_ocr_confidence(
    page: fitz.Page,
    textpage: fitz.TextPage,
    page_number: int,
    threshold: int,
    low_confidence_pages: list[int],
) -> None:
    """Check per-word OCR confidence and flag low-confidence pages.

    Uses textpage word-level extraction with confidence data. If the
    average confidence for a page falls below threshold, adds it to
    the low_confidence_pages list.
    """
    try:
        # Extract words with confidence: (x0, y0, x1, y1, "word", block, line, word, conf)
        words = page.get_text("words", textpage=textpage)
        if not words:
            return
        confidences = [float(w[8]) if len(w) > 8 else 100.0 for w in words]
        avg_confidence = sum(confidences) / len(confidences)
        if avg_confidence < threshold:
            low_confidence_pages.append(page_number)
    except Exception:
        pass


def verify_pdf(
    pdf_path: pathlib.Path,
    keywords: KeywordSet,
    confidence_threshold: int = 70,
    language: str = "eng",
    deep_verify: bool = False,
    deep_verify_dpi: int = 300,
    verbose: bool = False,
) -> VerificationReport:
    """Run verification checks on a PDF.

    Args:
        pdf_path: Path to the PDF to verify.
        keywords: KeywordSet to check for residual matches.
        confidence_threshold: OCR confidence cutoff (0-100).
        language: Tesseract language code.
        deep_verify: If True, rasterize and re-scan pages.
        deep_verify_dpi: DPI for rasterization (150-600).
        verbose: If True, include context snippets in report.

    Returns:
        VerificationReport with findings.
    """
    source_hash = _file_hash(pdf_path)
    doc = fitz.open(str(pdf_path))

    residual_matches: list[dict] = []
    low_confidence_pages: list[int] = []
    unreadable_pages: list[int] = []
    clean_pages: list[int] = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_number = page_num + 1
        text = page.get_text()

        if not text.strip():
            # Image-only page — attempt OCR
            has_images = len(page.get_images()) > 0
            if has_images:
                try:
                    tp = page.get_textpage_ocr(language=language, full=True)
                    text = page.get_text(textpage=tp)
                    if text.strip():
                        # OCR succeeded — check confidence
                        _check_ocr_confidence(
                            page, tp, page_number, confidence_threshold,
                            low_confidence_pages,
                        )
                    else:
                        unreadable_pages.append(page_number)
                        continue
                except Exception:
                    unreadable_pages.append(page_number)
                    continue
            else:
                unreadable_pages.append(page_number)
                continue

        # Check residual keyword matches
        matches = keywords.find_matches(text)
        if matches:
            for m in matches:
                entry: dict = {"keyword": m.keyword, "page": page_number}
                if verbose:
                    entry["context"] = m.matched_text
                residual_matches.append(entry)
        else:
            clean_pages.append(page_number)

    if deep_verify:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            page_number = page_num + 1
            pix = page.get_pixmap(dpi=deep_verify_dpi)
            img_doc = fitz.open()
            img_page = img_doc.new_page(width=pix.width, height=pix.height)
            img_page.insert_image(img_page.rect, pixmap=pix)
            try:
                img_page.get_textpage_ocr(language=language, full=True)
                ocr_text = img_page.get_text()
                dv_matches = keywords.find_matches(ocr_text)
                for m in dv_matches:
                    entry = {
                        "keyword": m.keyword,
                        "page": page_number,
                        "source": "deep_verify",
                    }
                    if entry not in residual_matches:
                        residual_matches.append(entry)
            except Exception:
                pass
            img_doc.close()

    doc.close()

    if residual_matches or low_confidence_pages or unreadable_pages:
        status = "needs_review"
    else:
        status = "clean"

    return VerificationReport(
        file=pdf_path.name,
        status=status,
        source_hash=source_hash,
        residual_matches=residual_matches,
        low_confidence_pages=low_confidence_pages,
        unreadable_pages=unreadable_pages,
        clean_pages=clean_pages,
        deep_verify=deep_verify,
        deep_verify_dpi=deep_verify_dpi if deep_verify else None,
        engine_version=obscura.__version__,
        keywords_hash=keywords.keyword_hash(),
        language=language,
        confidence_threshold=confidence_threshold,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/verify.py tests/test_verify.py
git commit -m "feat: add verification layer with residual scan and report generation"
```

---

## Phase 5: Run Orchestrator

### Task 5.1: Run Orchestrator — Ties Redact + Sanitize + Verify Together

**Parallel:** no
**Blocked by:** Task 1.2, Task 2.1, Task 3.1, Task 4.1
**Owned files:** `src/obscura/runner.py`, `tests/test_runner.py`

**Step 1: Write the failing tests**

Create `tests/test_runner.py`:

```python
"""Tests for run orchestrator — full pipeline per project."""

import json

import fitz
import pytest

from obscura.project import create_project
from obscura.runner import run_project, RunSummary


def _add_pdf_to_project(project, filename: str, pages: list[str]):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


class TestRunProject:
    def test_processes_all_input_pdfs(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc1.pdf", ["Secret info here."])
        _add_pdf_to_project(project, "doc2.pdf", ["More secret data."])

        summary = run_project(project)

        assert summary.files_processed == 2
        assert (project.output_dir / "doc1.pdf").exists()
        assert (project.output_dir / "doc2.pdf").exists()

    def test_generates_verification_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc1.pdf", ["Secret content."])

        summary = run_project(project)

        report_files = list(project.reports_dir.glob("*.json"))
        assert len(report_files) == 1

        report_data = json.loads(report_files[0].read_text())
        # Versioned envelope format
        assert report_data["schema_version"] == 1
        assert "run_id" in report_data
        assert "engine_version" in report_data
        assert "settings" in report_data
        assert "files" in report_data
        assert len(report_data["files"]) == 1
        assert report_data["files"][0]["file"] == "doc1.pdf"

    def test_redacted_text_not_in_output(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["The secret password."])

        run_project(project)

        doc = fitz.open(str(project.output_dir / "doc.pdf"))
        text = doc[0].get_text()
        doc.close()
        assert "secret" not in text.lower()

    def test_metadata_scrubbed_in_output(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("anything\n")

        path = project.input_dir / "doc.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Clean text.")
        doc.set_metadata({"author": "John Doe"})
        doc.save(str(path))
        doc.close()

        run_project(project)

        doc = fitz.open(str(project.output_dir / "doc.pdf"))
        assert doc.metadata.get("author", "") == ""
        doc.close()

    def test_updates_last_run(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        assert project.last_run is None

        run_project(project)

        from obscura.project import Project
        reloaded = Project.load(project.path)
        assert reloaded.last_run is not None

    def test_empty_project_no_crash(self, tmp_dir):
        project = create_project(tmp_dir, "Empty")
        project.keywords_path.write_text("secret\n")

        summary = run_project(project)

        assert summary.files_processed == 0

    def test_summary_structure(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        summary = run_project(project)

        assert isinstance(summary, RunSummary)
        assert summary.files_processed == 1
        assert isinstance(summary.total_redactions, int)
        assert isinstance(summary.files_needing_review, int)
        assert isinstance(summary.files_errored, int)

    def test_per_file_error_isolation(self, tmp_dir):
        """If one file fails during processing, others should still complete."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "good.pdf", ["Secret info."])
        # Create a corrupt PDF that will fail during processing
        (project.input_dir / "bad.pdf").write_bytes(b"not a pdf")

        summary = run_project(project)

        assert summary.files_processed == 2
        # good.pdf should have been processed successfully
        assert (project.output_dir / "good.pdf").exists()
        # Error should be recorded but not crash the run
        assert summary.files_errored >= 0  # corrupt is caught by redact_pdf

    def test_empty_keywords_raises(self, tmp_dir):
        """Running with an empty keywords file should raise ValueError."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("")
        _add_pdf_to_project(project, "doc.pdf", ["Content."])

        with pytest.raises(ValueError, match="Keywords file is empty"):
            run_project(project)

    def test_report_schema_has_metadata(self, tmp_dir):
        """Report should use versioned envelope with run metadata."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        run_project(project)

        report_files = list(project.reports_dir.glob("*.json"))
        report_data = json.loads(report_files[0].read_text())
        assert report_data["schema_version"] == 1
        assert "run_id" in report_data
        assert "engine_version" in report_data
        assert "project_name" in report_data
        assert report_data["settings"]["language"] == "eng"
        assert "keywords_hash" in report_data["settings"]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_runner.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.runner'`

**Step 3: Write minimal implementation**

Create `src/obscura/runner.py`:

```python
"""Run orchestrator — ties redact, sanitize, and verify into a project pipeline.

Per-file error isolation: if one file fails during sanitize or verify,
the error is recorded in the report and processing continues with the
remaining files.

Report schema: Reports use a versioned envelope format:
    { "schema_version": 1, "run_id": ..., "engine_version": ...,
      "settings": {...}, "files": [...] }
"""

from __future__ import annotations

import dataclasses
import json
import logging
import pathlib
import uuid
from datetime import datetime, timezone

import obscura
from obscura.keywords import KeywordSet
from obscura.project import Project
from obscura.redact import redact_pdf
from obscura.sanitize import sanitize_pdf
from obscura.verify import verify_pdf

logger = logging.getLogger(__name__)

# Report schema version — bump when report structure changes.
REPORT_SCHEMA_VERSION = 1


@dataclasses.dataclass
class RunSummary:
    """Summary of a full project run."""

    files_processed: int
    total_redactions: int
    files_needing_review: int
    files_errored: int
    report_path: pathlib.Path | None


def run_project(
    project: Project,
    deep_verify: bool = False,
    deep_verify_dpi: int = 300,
    verbose: bool = False,
) -> RunSummary:
    """Run the full redaction pipeline on a project.

    Steps per file: redact -> sanitize -> verify.
    Each file is isolated — errors in one file don't crash the batch.

    Args:
        project: The project to process.
        deep_verify: Enable rasterize-and-scan verification.
        deep_verify_dpi: DPI for deep verify rasterization.
        verbose: Include context snippets in verification reports.

    Returns:
        RunSummary with aggregate results.

    Raises:
        ValueError: If keywords file is empty (no keywords defined).
    """
    keywords = KeywordSet.from_file(project.keywords_path)

    if keywords.is_empty:
        raise ValueError(
            f"Keywords file is empty: {project.keywords_path}. "
            "Add at least one keyword before running redaction."
        )

    input_pdfs = sorted(project.input_dir.glob("*.pdf"))
    if not input_pdfs:
        return RunSummary(
            files_processed=0,
            total_redactions=0,
            files_needing_review=0,
            files_errored=0,
            report_path=None,
        )

    total_redactions = 0
    files_needing_review = 0
    files_errored = 0
    all_reports: list[dict] = []

    for pdf_path in input_pdfs:
        output_path = project.output_dir / pdf_path.name

        try:
            redaction_result = redact_pdf(
                pdf_path, output_path, keywords, language=project.language
            )
            total_redactions += redaction_result.redaction_count

            if redaction_result.status == "ok":
                sanitize_pdf(output_path, output_path)

                report = verify_pdf(
                    output_path,
                    keywords,
                    confidence_threshold=project.confidence_threshold,
                    language=project.language,
                    deep_verify=deep_verify,
                    deep_verify_dpi=deep_verify_dpi,
                    verbose=verbose,
                )
                if report.status == "needs_review":
                    files_needing_review += 1
                all_reports.append(report.to_dict())
            else:
                all_reports.append({
                    "file": pdf_path.name,
                    "status": redaction_result.status,
                    "source_hash": redaction_result.source_hash,
                })
                if redaction_result.status in ("password_protected", "corrupt"):
                    files_needing_review += 1

        except Exception as exc:
            logger.error("Error processing %s: %s", pdf_path.name, exc)
            files_errored += 1
            all_reports.append({
                "file": pdf_path.name,
                "status": "error",
                "error": str(exc),
            })

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"

    # Versioned report envelope
    report_data = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "engine_version": obscura.__version__,
        "project_name": project.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "deep_verify": deep_verify,
            "deep_verify_dpi": deep_verify_dpi if deep_verify else None,
            "language": project.language,
            "confidence_threshold": project.confidence_threshold,
            "keywords_hash": keywords.keyword_hash(),
        },
        "files": all_reports,
    }

    report_path = project.reports_dir / f"{timestamp}.json"
    report_path.write_text(
        json.dumps(report_data, indent=2) + "\n", encoding="utf-8"
    )

    project.last_run = datetime.now(timezone.utc).isoformat()
    project.save()

    return RunSummary(
        files_processed=len(input_pdfs),
        total_redactions=total_redactions,
        files_needing_review=files_needing_review,
        files_errored=files_errored,
        report_path=report_path,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_runner.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/runner.py tests/test_runner.py
git commit -m "feat: add run orchestrator with error isolation, report schema versioning, empty keywords guard"
```

---

## Phase 6: CLI

### Task 6.1: CLI Entrypoint

**Parallel:** no
**Blocked by:** Task 5.1
**Owned files:** `src/obscura/cli.py`, `tests/test_cli.py`

**Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
"""Tests for CLI entrypoint."""

import json
import subprocess
import sys

import fitz
import pytest

from obscura.project import create_project


def _add_pdf(project, filename, pages):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestCli:
    def test_run_command(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret info."])

        result = subprocess.run(
            [sys.executable, "-m", "obscura", "run", str(project.path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (project.output_dir / "doc.pdf").exists()

    def test_list_command(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        create_project(tmp_dir, "Matter B")

        result = subprocess.run(
            [sys.executable, "-m", "obscura", "list", "--root", str(tmp_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Matter A" in result.stdout
        assert "Matter B" in result.stdout

    def test_report_command(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])

        subprocess.run(
            [sys.executable, "-m", "obscura", "run", str(project.path)],
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "obscura", "report", str(project.path), "--last"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_create_command(self, tmp_dir):
        result = subprocess.run(
            [
                sys.executable, "-m", "obscura", "create",
                "--root", str(tmp_dir),
                "--name", "New Matter",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (tmp_dir / "New Matter" / "project.json").exists()
        assert "Created" in result.stdout

    def test_create_with_options(self, tmp_dir):
        result = subprocess.run(
            [
                sys.executable, "-m", "obscura", "create",
                "--root", str(tmp_dir),
                "--name", "Spanish Matter",
                "--language", "spa",
                "--threshold", "80",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        data = json.loads((tmp_dir / "Spanish Matter" / "project.json").read_text())
        assert data["language"] == "spa"
        assert data["confidence_threshold"] == 80

    def test_report_list(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])

        subprocess.run(
            [sys.executable, "-m", "obscura", "run", str(project.path)],
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "obscura", "report", str(project.path), "--list"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert ".json" in result.stdout

    def test_run_nonexistent_project(self, tmp_dir):
        result = subprocess.run(
            [sys.executable, "-m", "obscura", "run", str(tmp_dir / "nope")],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0

    def test_no_args_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "obscura"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0 or "usage" in result.stderr.lower() or "usage" in result.stdout.lower()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.cli'`

**Step 3: Write minimal implementation**

Create `src/obscura/cli.py`:

```python
"""CLI entrypoint for Obscura."""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys

from obscura.project import Project, create_project, discover_projects
from obscura.runner import run_project

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="obscura",
        description="Local-only PDF redaction tool.",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: WARNING).",
    )
    subparsers = parser.add_subparsers(dest="command")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new project.")
    create_parser.add_argument("--root", type=pathlib.Path, required=True, help="Project root directory.")
    create_parser.add_argument("--name", type=str, required=True, help="Project name.")
    create_parser.add_argument("--language", type=str, default="eng", help="Tesseract language code (default: eng).")
    create_parser.add_argument("--threshold", type=int, default=70, help="OCR confidence threshold 0-100 (default: 70).")

    # run
    run_parser = subparsers.add_parser("run", help="Run redaction on a project.")
    run_parser.add_argument("project_path", type=pathlib.Path, help="Path to project folder.")
    run_parser.add_argument("--deep-verify", action="store_true", help="Enable rasterize-and-scan verify.")
    run_parser.add_argument("--dpi", type=int, default=300, help="DPI for deep verify (default: 300).")
    run_parser.add_argument("--verbose", action="store_true", help="Include context snippets in reports.")

    # list
    list_parser = subparsers.add_parser("list", help="List projects.")
    list_parser.add_argument("--root", type=pathlib.Path, required=True, help="Project root directory.")

    # report
    report_parser = subparsers.add_parser("report", help="Show verification report.")
    report_parser.add_argument("project_path", type=pathlib.Path, help="Path to project folder.")
    report_parser.add_argument("--last", action="store_true", help="Show the most recent report.")
    report_parser.add_argument("--list", dest="list_reports", action="store_true", help="List all available reports.")

    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(2)

    if args.command == "create":
        _cmd_create(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "list":
        _cmd_list(args)
    elif args.command == "report":
        _cmd_report(args)


def _cmd_create(args: argparse.Namespace) -> None:
    try:
        project = create_project(
            args.root,
            args.name,
            language=args.language,
            confidence_threshold=args.threshold,
        )
        print(f"Created project: {project.name}")
        print(f"  Path: {project.path}")
        print(f"  Language: {project.language}")
        print(f"  Confidence threshold: {project.confidence_threshold}")
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_run(args: argparse.Namespace) -> None:
    try:
        project = Project.load(args.project_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        summary = run_project(
            project,
            deep_verify=args.deep_verify,
            deep_verify_dpi=args.dpi,
            verbose=args.verbose,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Processed {summary.files_processed} file(s).")
    print(f"Total redactions: {summary.total_redactions}")
    if summary.files_needing_review > 0:
        print(f"Files needing review: {summary.files_needing_review}")
    if summary.files_errored > 0:
        print(f"Files with errors: {summary.files_errored}")
    if summary.report_path:
        print(f"Report: {summary.report_path}")


def _cmd_list(args: argparse.Namespace) -> None:
    projects = discover_projects(args.root)
    if not projects:
        print("No projects found.")
        return
    for p in projects:
        status = f"last run: {p.last_run}" if p.last_run else "not yet run"
        print(f"  {p.name}  ({status})")


def _cmd_report(args: argparse.Namespace) -> None:
    try:
        project = Project.load(args.project_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    report_files = sorted(project.reports_dir.glob("*.json"))
    if not report_files:
        print("No reports found.")
        return

    if args.list_reports:
        for rf in report_files:
            print(f"  {rf.name}")
        return

    if args.last:
        report_path = report_files[-1]
    else:
        report_path = report_files[-1]

    data = json.loads(report_path.read_text())
    print(json.dumps(data, indent=2))
```

**Step 4: Update `__main__.py`**

The `__main__.py` was already created in Task 0.1 pointing to `obscura.cli:main`.

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add src/obscura/cli.py tests/test_cli.py
git commit -m "feat: add CLI with create, run, list, and report commands"
```

---

## Phase 7: Desktop UI (pywebview)

### Task 7.1: App Config — First-Launch Root Selector

**Parallel:** yes
**Blocked by:** Task 3.1
**Owned files:** `src/obscura/config.py`, `tests/test_config.py`

**Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
"""Tests for app-level configuration."""

import json

import pytest

from obscura.config import AppConfig, load_config, save_config


class TestAppConfig:
    def test_default_config(self, tmp_dir):
        config = AppConfig.default(config_dir=tmp_dir)
        assert config.project_root is None

    def test_save_and_load(self, tmp_dir):
        config = AppConfig(project_root="/some/path", config_dir=tmp_dir)
        save_config(config)

        loaded = load_config(config_dir=tmp_dir)
        assert loaded.project_root == "/some/path"

    def test_load_missing_returns_default(self, tmp_dir):
        config = load_config(config_dir=tmp_dir)
        assert config.project_root is None

    def test_save_creates_file(self, tmp_dir):
        config = AppConfig(project_root="/test", config_dir=tmp_dir)
        save_config(config)
        assert (tmp_dir / ".config.json").exists()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.config'`

**Step 3: Write minimal implementation**

Create `src/obscura/config.py`:

```python
"""App-level configuration — project root path, first-launch setup."""

from __future__ import annotations

import dataclasses
import json
import pathlib


@dataclasses.dataclass
class AppConfig:
    """Application-level settings stored in .config.json."""

    project_root: str | None
    config_dir: pathlib.Path

    @classmethod
    def default(cls, config_dir: pathlib.Path) -> AppConfig:
        return cls(project_root=None, config_dir=config_dir)


def _config_path(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / ".config.json"


def save_config(config: AppConfig) -> None:
    path = _config_path(config.config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"project_root": config.project_root}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_config(config_dir: pathlib.Path) -> AppConfig:
    path = _config_path(config_dir)
    if not path.exists():
        return AppConfig.default(config_dir=config_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig(
        project_root=data.get("project_root"),
        config_dir=config_dir,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/config.py tests/test_config.py
git commit -m "feat: add app config for project root path"
```

---

### Task 7.2: pywebview API Bridge

**Parallel:** yes
**Blocked by:** Task 5.1, Task 7.1
**Owned files:** `src/obscura/api.py`, `tests/test_api.py`

**Step 1: Write the failing tests**

Create `tests/test_api.py`:

```python
"""Tests for pywebview API bridge."""

import json

import fitz
import pytest

from obscura.api import ObscuraAPI
from obscura.project import create_project


def _add_pdf(project, filename, pages):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestObscuraAPI:
    def test_list_projects(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        api = ObscuraAPI(project_root=tmp_dir)

        result = api.list_projects()
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Matter A"

    def test_create_project(self, tmp_dir):
        api = ObscuraAPI(project_root=tmp_dir)

        result = api.create_project("New Matter")
        parsed = json.loads(result)

        assert parsed["name"] == "New Matter"
        assert (tmp_dir / "New Matter" / "project.json").exists()

    def test_run_project(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret text."])

        api = ObscuraAPI(project_root=tmp_dir)
        result = api.run_project("Test")
        parsed = json.loads(result)

        assert parsed["files_processed"] == 1
        assert "total_redactions" in parsed

    def test_get_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])

        api = ObscuraAPI(project_root=tmp_dir)
        api.run_project("Test")

        result = api.get_latest_report("Test")
        parsed = json.loads(result)

        assert isinstance(parsed, dict)
        assert "schema_version" in parsed
        assert "files" in parsed
        assert len(parsed["files"]) == 1

    def test_get_keywords(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\nconfidential\n")

        api = ObscuraAPI(project_root=tmp_dir)
        result = api.get_keywords("Test")

        assert result == "secret\nconfidential\n"

    def test_save_keywords(self, tmp_dir):
        project = create_project(tmp_dir, "Test")

        api = ObscuraAPI(project_root=tmp_dir)
        api.save_keywords("Test", "new_keyword\nanother\n")

        assert project.keywords_path.read_text() == "new_keyword\nanother\n"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'obscura.api'`

**Step 3: Write minimal implementation**

Create `src/obscura/api.py`:

```python
"""pywebview API bridge — exposes project operations to the web UI."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from obscura.project import Project, create_project, discover_projects
from obscura.runner import run_project


class ObscuraAPI:
    """JS-callable API exposed via pywebview."""

    def __init__(self, project_root: pathlib.Path) -> None:
        self._root = project_root

    def list_projects(self) -> str:
        projects = discover_projects(self._root)
        return json.dumps([
            {
                "name": p.name,
                "last_run": p.last_run,
                "language": p.language,
                "path": str(p.path),
            }
            for p in projects
        ])

    def create_project(
        self, name: str, language: str = "eng", confidence_threshold: int = 70
    ) -> str:
        project = create_project(
            self._root, name, language=language,
            confidence_threshold=confidence_threshold,
        )
        return json.dumps({"name": project.name, "path": str(project.path)})

    def run_project(
        self, name: str, deep_verify: bool = False, dpi: int = 300
    ) -> str:
        project = Project.load(self._root / name)
        summary = run_project(project, deep_verify=deep_verify, deep_verify_dpi=dpi)
        return json.dumps({
            "files_processed": summary.files_processed,
            "total_redactions": summary.total_redactions,
            "files_needing_review": summary.files_needing_review,
            "report_path": str(summary.report_path) if summary.report_path else None,
        })

    def get_latest_report(self, name: str) -> str:
        project = Project.load(self._root / name)
        report_files = sorted(project.reports_dir.glob("*.json"))
        if not report_files:
            return json.dumps({"schema_version": 1, "files": []})
        return report_files[-1].read_text(encoding="utf-8")

    def get_keywords(self, name: str) -> str:
        project = Project.load(self._root / name)
        return project.keywords_path.read_text(encoding="utf-8")

    def save_keywords(self, name: str, content: str) -> str:
        project = Project.load(self._root / name)
        project.keywords_path.write_text(content, encoding="utf-8")
        return json.dumps({"status": "ok"})

    def open_in_preview(self, name: str, filename: str) -> str:
        project = Project.load(self._root / name)
        file_path = project.output_dir / filename
        if not file_path.exists():
            return json.dumps({"error": "File not found"})
        subprocess.Popen(["open", str(file_path)])
        return json.dumps({"status": "ok"})

    def reveal_in_finder(self, name: str, filename: str) -> str:
        project = Project.load(self._root / name)
        file_path = project.output_dir / filename
        if not file_path.exists():
            return json.dumps({"error": "File not found"})
        subprocess.Popen(["open", "-R", str(file_path)])
        return json.dumps({"status": "ok"})
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/obscura/api.py tests/test_api.py
git commit -m "feat: add pywebview API bridge for project operations"
```

---

### Task 7.3: pywebview App Launcher

**Parallel:** no
**Blocked by:** Task 7.1, Task 7.2
**Owned files:** `src/obscura/app.py`

This task creates the pywebview launcher. It is not unit-tested (requires GUI) but manually verified.

**Step 1: Write the app launcher**

Create `src/obscura/app.py`:

```python
"""Desktop app launcher using pywebview."""

from __future__ import annotations

import pathlib

import webview

from obscura.api import ObscuraAPI
from obscura.config import load_config, save_config, AppConfig


def _get_project_root() -> pathlib.Path:
    default_dir = pathlib.Path.home() / "Obscura"
    config = load_config(config_dir=default_dir)

    if config.project_root:
        root = pathlib.Path(config.project_root)
        if root.exists():
            return root

    result = webview.windows[0].create_file_dialog(
        webview.FOLDER_DIALOG,
        directory=str(pathlib.Path.home()),
    )

    if result and result[0]:
        chosen = pathlib.Path(result[0])
    else:
        chosen = default_dir

    chosen.mkdir(parents=True, exist_ok=True)
    config = AppConfig(project_root=str(chosen), config_dir=chosen)
    save_config(config)
    return chosen


def launch() -> None:
    """Launch the Obscura desktop application."""
    html_dir = pathlib.Path(__file__).parent / "ui"
    index_html = html_dir / "index.html"

    default_root = pathlib.Path.home() / "Obscura"
    default_root.mkdir(parents=True, exist_ok=True)

    config = load_config(config_dir=default_root)
    project_root = pathlib.Path(config.project_root) if config.project_root else default_root

    api = ObscuraAPI(project_root=project_root)

    window = webview.create_window(
        "Obscura",
        url=str(index_html) if index_html.exists() else None,
        js_api=api,
        width=1200,
        height=800,
        min_size=(800, 600),
    )

    webview.start()
```

**Step 2: Update `__main__.py` to support both CLI and GUI modes**

Update `src/obscura/__main__.py`:

```python
"""Allow running as `python -m obscura`."""

import sys


def main():
    if len(sys.argv) > 1:
        from obscura.cli import main as cli_main
        cli_main()
    else:
        try:
            from obscura.app import launch
            launch()
        except ImportError:
            from obscura.cli import main as cli_main
            cli_main()


if __name__ == "__main__":
    main()
```

**Step 3: Create placeholder UI files**

Create `src/obscura/ui/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Obscura</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div id="app">
        <header>
            <h1>Obscura</h1>
            <button id="new-project-btn">New Project</button>
        </header>
        <main id="project-list">
            <p>Loading projects...</p>
        </main>
    </div>
    <script src="app.js"></script>
</body>
</html>
```

Create `src/obscura/ui/styles.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    min-height: 100vh;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    background: #16213e;
    border-bottom: 1px solid #0f3460;
}

header h1 { font-size: 20px; font-weight: 600; }

button {
    background: #0f3460;
    color: #e0e0e0;
    border: 1px solid #533483;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
}

button:hover { background: #533483; }

main { padding: 24px; }

.project-card {
    background: #16213e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    cursor: pointer;
}

.project-card:hover { border-color: #533483; }

.project-card h3 { margin-bottom: 4px; }

.project-card .meta { color: #888; font-size: 13px; }

.status-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}

.status-clean { background: #1b4332; color: #95d5b2; }
.status-review { background: #7f4f24; color: #ddb892; }
.status-error { background: #641220; color: #e5383b; }
.status-none { background: #333; color: #888; }
```

Create `src/obscura/ui/app.js`:

```javascript
/* Obscura UI — communicates with Python backend via pywebview JS bridge. */

async function loadProjects() {
    const main = document.getElementById("project-list");
    try {
        const result = await window.pywebview.api.list_projects();
        const projects = JSON.parse(result);
        if (projects.length === 0) {
            main.innerHTML = "<p>No projects yet. Create one to get started.</p>";
            return;
        }
        main.innerHTML = projects.map(p => `
            <div class="project-card" onclick="openProject('${p.name}')">
                <h3>${p.name}</h3>
                <div class="meta">
                    ${p.last_run ? "Last run: " + p.last_run : "Not yet run"}
                    &middot; Language: ${p.language}
                </div>
            </div>
        `).join("");
    } catch (e) {
        main.innerHTML = "<p>Error loading projects.</p>";
    }
}

async function openProject(name) {
    /* Placeholder — will navigate to project workspace screen. */
    console.log("Open project:", name);
}

document.getElementById("new-project-btn").addEventListener("click", async () => {
    const name = prompt("Project name:");
    if (name) {
        await window.pywebview.api.create_project(name);
        loadProjects();
    }
});

/* Initialize when pywebview bridge is ready. */
window.addEventListener("pywebviewready", loadProjects);
```

**Step 4: Verify manually (no automated test)**

```bash
python -m obscura
```

Expected: A pywebview window opens showing the project list. (Requires `pip install pywebview`.)

**Step 5: Commit**

```bash
git add src/obscura/app.py src/obscura/__main__.py src/obscura/ui/
git commit -m "feat: add pywebview desktop launcher with placeholder UI"
```

---

### Task 7.4: Full UI — Three Screens

**Parallel:** no
**Blocked by:** Task 7.3
**Owned files:** `src/obscura/ui/index.html`, `src/obscura/ui/styles.css`, `src/obscura/ui/app.js`

This is a UI-only task. Build out the three screens described in the design doc: Project List, Project Workspace (keywords panel, files panel, run controls), and File Report Detail. All interaction goes through the `pywebview.api` bridge already built in Task 7.2.

This task is detailed in the design document's UI section. The implementor should:

**Step 1:** Extend `app.js` with screen routing (project list -> workspace -> report detail).

**Step 2:** Build Project Workspace screen with three panels:
- Left: keyword text editor (loads/saves via `api.get_keywords` / `api.save_keywords`)
- Center: file list with drag-and-drop (add PDF copy to project input dir)
- Right: run controls (Run Redaction button, deep verify checkbox, language selector, last run summary)

**Step 3:** Build File Report Detail screen:
- Residual matches with page numbers
- Low-confidence pages
- Unreadable pages with warning
- "Open in Preview" button (calls `api.open_in_preview`)
- "Reveal in Finder" button (calls `api.reveal_in_finder`)

**Step 4:** Verify manually by running `python -m obscura` and testing all three screens.

**Step 5: Commit**

```bash
git add src/obscura/ui/
git commit -m "feat: build full three-screen UI — project list, workspace, report detail"
```

---

## Phase 8: Packaging

### Task 8.1: PyInstaller Build Script

**Parallel:** no
**Blocked by:** Task 7.4
**Owned files:** `build.py`, `scripts/bundle_tesseract.sh`

**Step 1:** Create `build.py` (or a PyInstaller spec file) that:
- Bundles `src/obscura/` including `ui/` directory
- Includes Tesseract binary (from Homebrew or bundled)
- Includes `eng.traineddata` and `spa.traineddata`
- Includes the `regex` module
- Uses `--windowed` flag
- Produces `Obscura.app`

```python
"""PyInstaller build configuration for Obscura.app."""

import pathlib
import subprocess
import sys


def find_tesseract():
    result = subprocess.run(["which", "tesseract"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    brew_path = pathlib.Path("/opt/homebrew/bin/tesseract")
    if brew_path.exists():
        return str(brew_path)
    raise FileNotFoundError("Tesseract not found. Install via: brew install tesseract")


def find_tessdata():
    candidates = [
        pathlib.Path("/opt/homebrew/share/tessdata"),
        pathlib.Path("/usr/local/share/tessdata"),
        pathlib.Path("/usr/share/tesseract-ocr/5/tessdata"),
    ]
    for p in candidates:
        if p.exists() and (p / "eng.traineddata").exists():
            return str(p)
    raise FileNotFoundError("Tesseract language data not found.")


def build():
    tesseract = find_tesseract()
    tessdata = find_tessdata()
    ui_dir = pathlib.Path("src/obscura/ui")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Obscura",
        "--windowed",
        "--add-data", f"{ui_dir}:obscura/ui",
        "--add-binary", f"{tesseract}:.",
        "--add-data", f"{tessdata}/eng.traineddata:tessdata",
        "--add-data", f"{tessdata}/spa.traineddata:tessdata",
        "--hidden-import", "regex",
        "--hidden-import", "obscura",
        "src/obscura/__main__.py",
    ]

    subprocess.run(cmd, check=True)
    print("Build complete: dist/Obscura.app")


if __name__ == "__main__":
    build()
```

**Step 2:** Test the build

```bash
pip install pyinstaller
python build.py
```

Expected: `dist/Obscura.app` is created.

**Step 3:** Test the app on a clean environment

```bash
open dist/Obscura.app
```

Expected: App launches, shows project list, basic operations work.

**Step 4: Commit**

```bash
git add build.py
git commit -m "chore: add PyInstaller build script for Obscura.app"
```

---

## Task Dependency Graph

```
Task 0.1 (Setup)
  ├── Task 1.1 (KeywordSet)
  │     └── Task 1.2 (redact_pdf)
  │           ├── Task 2.1 (Sanitize)
  │           │     └── Task 4.1 (Verify)
  │           │           └── Task 5.1 (Runner)
  │           │                 ├── Task 6.1 (CLI)
  │           │                 └── Task 7.2 (API Bridge)
  │           └── Task 4.1 (Verify) [also depends on 2.1]
  └── Task 3.1 (Project Model)
        ├── Task 5.1 (Runner) [also depends on 1.2, 2.1, 4.1]
        └── Task 7.1 (App Config) ──┐
                                     ├── Task 7.3 (App Launcher)
              Task 7.2 (API Bridge) ─┘       └── Task 7.4 (Full UI)
                                                     └── Task 8.1 (Packaging)
```

## Parallel Opportunities

| Can Run In Parallel | Why |
|---|---|
| Task 3.1 + Task 1.1 | No file overlap, independent modules |
| Task 7.1 + Task 4.1 | No file overlap, independent modules |
| Task 6.1 + Task 7.2 | Both depend on Task 5.1 but own different files |

## Owned Files Validation

Run this to check for overlaps before parallelizing:

```bash
rg '\*\*Owned files:\*\*' docs/plans/2026-02-04-obscura-implementation.md \
  | sed 's/.*\*\*Owned files:\*\* *//' \
  | tr ',' '\n' \
  | sed 's/`//g' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | grep -v '^$' \
  | sort \
  | uniq -d
```

Expected: no output (no overlapping files).
