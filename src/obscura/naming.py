"""Shared naming utilities for input-to-output file mapping."""

from __future__ import annotations

import pathlib


def output_filename_for_input(input_name: str) -> str:
    """Derive the output filename from an input filename.

    Appends '_redacted' before the extension, unless the stem already
    ends with '_redacted' (case-insensitive).

    Examples:
        'doc.pdf' -> 'doc_redacted.pdf'
        'doc_redacted.pdf' -> 'doc_redacted.pdf'
        'Doc_Redacted.PDF' -> 'Doc_Redacted.PDF'
    """
    candidate = pathlib.Path(input_name)
    stem = candidate.stem
    suffix = candidate.suffix
    if stem.lower().endswith("_redacted"):
        return candidate.name
    return f"{stem}_redacted{suffix}"
