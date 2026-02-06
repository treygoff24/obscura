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


def disambiguate_output_filenames(input_names: list[str]) -> dict[str, str]:
    """Map input names to unique output names while preserving order.

    Example:
        ["doc.pdf", "doc_redacted.pdf"] ->
        {"doc.pdf": "doc_redacted.pdf",
         "doc_redacted.pdf": "doc_redacted_1.pdf"}
    """
    mapping: dict[str, str] = {}
    used_names_ci: set[str] = set()

    for input_name in input_names:
        base = output_filename_for_input(input_name)
        candidate = base
        base_path = pathlib.Path(base)
        counter = 1
        while candidate.lower() in used_names_ci:
            candidate = f"{base_path.stem}_{counter}{base_path.suffix}"
            counter += 1

        mapping[input_name] = candidate
        used_names_ci.add(candidate.lower())

    return mapping
