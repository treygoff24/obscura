# Suggested Improvement: Fused Token Splitting

## Problem

PyMuPDF's `page.get_text("words")` sometimes returns tokens where adjacent
words are joined by Unicode characters from the PDF's internal encoding.
This is common in legal PDFs where smart quotes, pilcrows, and superscript
characters get embedded without whitespace boundaries.

Examples of fused tokens extracted from real legal PDFs:

| Raw token from PyMuPDF | Expected words | After NFKC | Why `\b` fails |
|---|---|---|---|
| `³Elephant` | `Elephant` | `3Elephant` | `3` and `E` are both `\w` — no boundary |
| `Island´²a` | `Island`, `a` | `Island ́2a` | `2` and `a` are both `\w` — no boundary |
| `[REDACTED_KEYWORD]²the` | `[REDACTED_KEYWORD]`, `the` | `[REDACTED_KEYWORD]2the` | `a` and `2` are both `\w` — no boundary |
| `[REDACTED_KEYWORD]¶s` | `[REDACTED_KEYWORD]` | `[REDACTED_KEYWORD]¶s` | `¶` is NOT `\w`, so `\b` works here — but only by luck |

The root cause: NFKC normalization converts superscript digits (`³` → `3`,
`²` → `2`) into regular ASCII digits. These are `\w` characters, so
`regex`'s `\b` word boundary does not fire between them and adjacent
letters. Keywords like `elephant`, `[REDACTED_KEYWORD]`, or `island` fail to match
because the pattern `\belephant\b` requires word boundaries on both sides.

This was discovered and fixed in a production legal redaction pipeline
processing 20 PDFs. The fused tokens caused missed redactions of names,
locations, and phrases across 4 of the 20 documents.

## Where to Fix

### Primary: `_extract_line_words()` in `src/obscura/redact.py` (lines 67-98)

This function extracts words via `page.get_text("words")`, normalizes them,
groups by line, and joins into line text with character offset tracking. The
fix goes here because it sits between raw extraction and matching — all
downstream matching (plain, prefix, regex) benefits automatically.

Current flow:
```
get_text("words") → normalize each word → group by line → join with spaces
```

Proposed flow:
```
get_text("words") → split fused tokens → normalize each sub-token → group by line → join with spaces
```

### Secondary (optional): Substring matching for compound tokens

After the primary fix, a second issue remains: keywords embedded inside
compound tokens like email usernames (`kwame[REDACTED_KEYWORD]@gmail.com` contains
`kwame` and `[REDACTED_KEYWORD]`). The primary fix splits this into
`['kwame[REDACTED_KEYWORD]', 'gmail', 'com']`, but `kwame[REDACTED_KEYWORD]` is a single
alphanumeric string — the keyword `kwame` won't match via `\b` because
there's no word boundary inside it.

This affects `_search_keywords_on_page()` in `src/obscura/redact.py`
(lines 109-174).

## Proposed Fix: Token Expansion

### Step 1: Add a token splitting function

Split each raw word from `get_text("words")` on non-ASCII-alphanumeric
characters, preserving commas and periods (so dollar amounts like
`[REDACTED_KEYWORD].00` stay as single tokens).

```python
import re

_FUSED_TOKEN_SPLIT = re.compile(r'[^a-zA-Z0-9,.]+')

def _split_fused_token(text: str) -> list[str]:
    """Split a PDF-extracted word on non-alphanumeric boundaries.

    Preserves commas and periods so number tokens like '[REDACTED_KEYWORD].00'
    stay intact. Uses ASCII-only character class (not \\W) because
    NFKC-normalized Unicode digits would not be split by \\W.

    Examples:
        '³Elephant'  -> ['Elephant']
        'Island´²a'  -> ['Island', 'a']
        '[REDACTED_KEYWORD]²the' -> ['[REDACTED_KEYWORD]', 'the']
        '[REDACTED_KEYWORD]¶s'  -> ['[REDACTED_KEYWORD]', 's']
        '[REDACTED_KEYWORD]' -> ['[REDACTED_KEYWORD]']   (comma preserved)
        'hello'      -> ['hello']        (no split needed)
    """
    parts = _FUSED_TOKEN_SPLIT.split(text)
    return [p for p in parts if p]
```

Key design choice: `[^a-zA-Z0-9,.]+` instead of `[^\\w]+` or `\\W+`.
Python's `\W` is Unicode-aware — it considers `³` (U+00B3) a word character
(Unicode category `No`), which is the same reason `normalize_word` in the
private pipeline failed to strip it. The ASCII-only class avoids this.

### Step 2: Modify `_extract_line_words()` to expand tokens

Replace the current word processing loop (lines 77-82) with expansion:

```python
def _extract_line_words(
    page: fitz.Page, textpage: fitz.TextPage | None = None
) -> list[_LineWords]:
    """Extract normalized words grouped by line for reliable matching."""
    words = page.get_text("words", textpage=textpage) or []
    if not words:
        return []

    words.sort(key=lambda w: (w[5], w[6], w[7]))
    grouped: dict[tuple[int, int], list[tuple[str, fitz.Rect]]] = {}
    for w in words:
        raw_text = str(w[4])
        rect = fitz.Rect(w[:4])
        key = (int(w[5]), int(w[6]))

        # Split fused tokens, then normalize each part.
        # All sub-tokens share the original bounding rect so the
        # entire fused region gets redacted when any part matches.
        parts = _split_fused_token(raw_text)
        if not parts:
            continue
        for part in parts:
            norm = _normalize(part).lower()
            if norm:
                grouped.setdefault(key, []).append((norm, rect))

    # ... rest of line-joining logic unchanged ...
```

This means `³[REDACTED_KEYWORD]´²a` (3 raw tokens) expands to
`['elephant', 'island', 'a']` (3 normalized entries) in the line. The
line text becomes `"[REDACTED_KEYWORD] a"` and the pattern
`\b[REDACTED_KEYWORD]\b` matches cleanly.

### Step 3 (optional): Substring matching for compound tokens

For keywords embedded in tokens that can't be split further (e.g.,
`kwame[REDACTED_KEYWORD]` from an email address), add a post-match pass in
`_search_keywords_on_page()` that checks whether any plain keyword
of length >= 4 appears as a substring of unmatched tokens.

```python
# After existing plain/prefix/regex matching, for each line:
for line in lines:
    for kw in keywords.plain_keywords:
        if len(kw) >= 4 and kw in line.text:
            # Check if this occurrence was already matched
            for m_start in _find_all_substrings(line.text, kw):
                m_end = m_start + len(kw)
                rects = _rects_for_match(line.words, m_start, m_end)
                if rects:
                    add_rects(kw, rects)
```

This is more aggressive than `\b` matching and should be opt-in or
documented as a trade-off. The length >= 4 threshold prevents very
short keywords from causing false positives.

Trade-off: `\b` matching prevents "ben" from matching inside "benchmark".
Substring matching does not. For the legal redaction use case, where
keywords are specific names and terms, the risk is low. For a general-
purpose tool, this should be a user-facing option (e.g., a
`aggressive_matching` flag in project settings).

## Test Cases

### Fused token splitting

```python
def test_split_fused_superscript_prefix():
    """Superscript digit fused to word start: ³Elephant -> ['Elephant']"""
    assert _split_fused_token("³Elephant") == ["Elephant"]

def test_split_fused_multiple_separators():
    """Multiple Unicode chars between words: Island´²a -> ['Island', 'a']"""
    assert _split_fused_token("Island´²a") == ["Island", "a"]

def test_split_fused_pilcrow_possessive():
    """Pilcrow as possessive marker: [REDACTED_KEYWORD]¶s -> ['[REDACTED_KEYWORD]', 's']"""
    assert _split_fused_token("[REDACTED_KEYWORD]¶s") == ["[REDACTED_KEYWORD]", "s"]

def test_split_preserves_comma_numbers():
    """Commas in numbers must not split: [REDACTED_KEYWORD] -> ['[REDACTED_KEYWORD]']"""
    assert _split_fused_token("[REDACTED_KEYWORD]") == ["[REDACTED_KEYWORD]"]

def test_split_preserves_decimal_numbers():
    """Periods in decimals must not split: 1,000.00 -> ['1,000.00']"""
    assert _split_fused_token("1,000.00") == ["1,000.00"]

def test_split_plain_word_unchanged():
    """Normal words pass through: hello -> ['hello']"""
    assert _split_fused_token("hello") == ["hello"]

def test_split_email():
    """Email splits on @ and .: <kwame@gmail.com> -> ['kwame', 'gmail.com']"""
    assert _split_fused_token("<kwame@gmail.com>") == ["kwame", "gmail.com"]
```

### End-to-end redaction with fused tokens

Build a test PDF (using PyMuPDF's text insertion) that contains fused
tokens. Verify the keyword is redacted (text removed from content stream):

```python
def test_redact_fused_superscript_token(tmp_path):
    """Keyword preceded by superscript digit in PDF is still redacted."""
    # Create a PDF with text '³Elephant' as a single word
    doc = fitz.open()
    page = doc.new_page()
    # Insert text that simulates the fused token
    page.insert_text((72, 72), "³[REDACTED_KEYWORD] is beautiful")
    pdf_path = tmp_path / "fused.pdf"
    doc.save(str(pdf_path))
    doc.close()

    keywords = KeywordSet(["[REDACTED_KEYWORD]"], [], [])
    out_path = tmp_path / "redacted.pdf"
    result = redact_pdf(pdf_path, out_path, keywords)

    # Verify keyword is gone from output
    out_doc = fitz.open(str(out_path))
    text = out_doc[0].get_text().lower()
    assert "elephant" not in text
    assert "island" not in text
    out_doc.close()
```

### Substring matching for emails (if implemented)

```python
def test_redact_keyword_inside_email(tmp_path):
    """Keyword embedded in email username is redacted."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contact: kwame[REDACTED_KEYWORD]@gmail.com")
    pdf_path = tmp_path / "email.pdf"
    doc.save(str(pdf_path))
    doc.close()

    keywords = KeywordSet(["kwame", "[REDACTED_KEYWORD]"], [], [])
    out_path = tmp_path / "redacted.pdf"
    result = redact_pdf(pdf_path, out_path, keywords)

    out_doc = fitz.open(str(out_path))
    text = out_doc[0].get_text().lower()
    assert "kwame" not in text
    assert "[REDACTED_KEYWORD]" not in text
    out_doc.close()
```

## Files to Modify

| File | Change | Risk |
|---|---|---|
| `src/obscura/redact.py` | Add `_split_fused_token()`, modify `_extract_line_words()` loop | Low — only changes pre-matching tokenization; all downstream matching is unchanged |
| `src/obscura/redact.py` | (Optional) Add substring pass in `_search_keywords_on_page()` | Medium — could produce false positives; should be opt-in |
| `src/obscura/keywords.py` | No changes needed | — |
| `tests/test_redact.py` | Add fused token test cases | — |
| `tests/test_keywords.py` | Add `_split_fused_token` unit tests (if function lives in keywords.py) | — |

## Bump `MATCH_VERSION`

The token expansion changes matching semantics — the same keywords file
will now match text it previously missed. Bump `MATCH_VERSION` in
`src/obscura/keywords.py` (line 33) from `1` to `2` so the
`keyword_hash()` changes and verification reports reflect the new behavior.
