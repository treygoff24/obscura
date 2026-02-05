"""Keyword parsing, classification, and text matching.

Text normalization: All text (keywords and input) is normalized via
NFKC before matching. This handles ligatures (fi->fi, fl->fl), fullwidth
characters, and other Unicode equivalences.

Matching modes:
- Plain keywords use whole-word boundary matching (\\b) by default.
  This prevents "secret" from matching inside "secretary".
- Prefix wildcards use [\\w-]* to include hyphenated continuations.
- Regex patterns are used as-is with a 5-second timeout.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import unicodedata

import regex

_LIGATURE_MAP = str.maketrans({
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
})

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
        content = f"v{MATCH_VERSION}\n" + "\n".join(
            sorted(self.plain_keywords)
            + sorted(f"{p}*" for p in self.prefix_keywords)
            + sorted(f"regex:{ps}" for ps, _ in self.regex_patterns)
        )
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"