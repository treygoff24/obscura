"""Integration tests for CLI entrypoint via subprocess.

These tests exercise the real `python -m obscura` entry point end-to-end.
Unit tests for individual CLI commands live in test_cli_module.py.
"""

import subprocess
import sys

import fitz

from obscura.project import create_project


def _add_pdf(project, filename, pages):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestCliSubprocess:
    """Subprocess integration tests that prove the real entry point works."""

    def test_run_command_end_to_end(self, tmp_dir):
        """Full redaction pipeline via subprocess — the definitive integration test."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret info."])

        result = subprocess.run(
            [sys.executable, "-m", "obscura", "run", str(project.path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (project.output_dir / "doc_redacted.pdf").exists()
        assert "Processed 1 file(s)." in result.stdout

    def test_run_then_report(self, tmp_dir):
        """Run then report via subprocess to verify the full lifecycle."""
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
        assert "schema_version" in result.stdout
