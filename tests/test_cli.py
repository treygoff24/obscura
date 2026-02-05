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
