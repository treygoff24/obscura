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
        """Text with ligatures (fi, fl) should still match normalized keywords."""
        ks = self._make_ks(["confidential"], tmp_dir)
        matches = ks.find_matches("This is con\ufb01dential information.")
        assert len(matches) == 1

    def test_unicode_nfkc_normalization(self, tmp_dir):
        """Smart quotes and other Unicode variants should be normalized."""
        ks = self._make_ks(["test"], tmp_dir)
        # fullwidth "test" (U+FF54 U+FF45 U+FF53 U+FF54) normalizes to "test" via NFKC
        matches = ks.find_matches("The \uff54\uff45\uff53\uff54 results are in.")
        assert len(matches) == 1