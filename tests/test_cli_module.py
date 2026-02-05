"""Direct tests for CLI module logic (non-subprocess)."""

from __future__ import annotations

import json
import pathlib

import pytest

from obscura import cli
from obscura.project import create_project
from obscura.runner import RunSummary


def _create_report(project, name="2026-01-01.json", payload=None):
    if payload is None:
        payload = {"schema_version": 1, "files": []}
    report_path = project.reports_dir / name
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    return report_path


def test_main_no_args_prints_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    out = capsys.readouterr()
    assert "usage" in (out.err.lower() + out.out.lower())


def test_create_success(tmp_dir, capsys):
    cli.main(["create", "--root", str(tmp_dir), "--name", "Matter A"])
    assert (tmp_dir / "Matter A" / "project.json").exists()
    assert "Created project" in capsys.readouterr().out


def test_create_invalid_name_exits(tmp_dir, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["create", "--root", str(tmp_dir), "--name", "bad/name"])
    assert exc.value.code == 1
    assert "Error:" in capsys.readouterr().err


def test_list_no_projects(tmp_dir, capsys):
    cli.main(["list", "--root", str(tmp_dir)])
    assert "No projects found." in capsys.readouterr().out


def test_list_projects(tmp_dir, capsys):
    create_project(tmp_dir, "Matter A")
    create_project(tmp_dir, "Matter B")
    cli.main(["list", "--root", str(tmp_dir)])
    out = capsys.readouterr().out
    assert "Matter A" in out
    assert "Matter B" in out


def test_report_no_reports(tmp_dir, capsys):
    project = create_project(tmp_dir, "Matter A")
    cli.main(["report", str(project.path)])
    assert "No reports found." in capsys.readouterr().out


def test_report_list(tmp_dir, capsys):
    project = create_project(tmp_dir, "Matter A")
    _create_report(project, name="r1.json")
    _create_report(project, name="r2.json")
    cli.main(["report", str(project.path), "--list"])
    out = capsys.readouterr().out
    assert "r1.json" in out
    assert "r2.json" in out


def test_report_last(tmp_dir, capsys):
    project = create_project(tmp_dir, "Matter A")
    payload = {"schema_version": 1, "files": [{"file": "doc.pdf"}]}
    _create_report(project, name="2026-01-01.json", payload=payload)
    cli.main(["report", str(project.path), "--last"])
    out = capsys.readouterr().out
    assert '"schema_version": 1' in out
    assert '"doc.pdf"' in out


def test_run_missing_project_exits(tmp_dir, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", str(tmp_dir / "missing")])
    assert exc.value.code == 1
    assert "Error:" in capsys.readouterr().err


def test_run_empty_keywords_exits(tmp_dir, capsys):
    project = create_project(tmp_dir, "Matter A")
    project.keywords_path.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", str(project.path)])
    assert exc.value.code == 1
    assert "Error:" in capsys.readouterr().err


def test_run_prints_summary(tmp_dir, capsys, monkeypatch):
    project = create_project(tmp_dir, "Matter A")
    summary = RunSummary(
        files_processed=1,
        total_redactions=2,
        files_needing_review=1,
        files_errored=1,
        report_path=pathlib.Path("report.json"),
    )

    monkeypatch.setattr(cli, "run_project", lambda *_args, **_kwargs: summary)

    cli.main(["run", str(project.path)])
    out = capsys.readouterr().out
    assert "Processed 1 file(s)." in out
    assert "Total redactions: 2" in out
    assert "Files needing review: 1" in out
    assert "Files with errors: 1" in out
    assert "Report: report.json" in out
