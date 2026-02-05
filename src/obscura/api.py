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