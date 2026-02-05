"""pywebview API bridge — exposes project operations to the web UI."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
from typing import Iterable, TYPE_CHECKING

from obscura.project import Project, create_project, discover_projects
from obscura.runner import run_project
from obscura.config import AppConfig, save_config

if TYPE_CHECKING:
    import webview


class ObscuraAPI:
    """JS-callable API exposed via pywebview."""

    def __init__(self, project_root: pathlib.Path | None, config_dir: pathlib.Path) -> None:
        self._root = project_root
        self._config_dir = config_dir
        self._window: "webview.Window | None" = None

    def attach_window(self, window: "webview.Window") -> None:
        self._window = window

    def _ensure_root(self) -> pathlib.Path:
        if self._root is None:
            raise ValueError("Project root not set")
        return self._root

    def _resolve_project(self, name: str) -> Project:
        root = self._ensure_root().resolve()
        project_dir = (root / name).resolve()
        try:
            project_dir.relative_to(root)
        except ValueError:
            raise ValueError("Project name resolves outside root")
        return Project.load(project_dir)

    def list_projects(self) -> str:
        if self._root is None:
            return json.dumps({"needs_root": True, "projects": []})
        projects = discover_projects(self._root)
        return json.dumps({
            "needs_root": False,
            "projects": [
                {
                    "name": p.name,
                    "last_run": p.last_run,
                    "language": p.language,
                    "path": str(p.path),
                    "confidence_threshold": p.confidence_threshold,
                }
                for p in projects
            ],
        })

    def select_project_root(self) -> str:
        if self._window is None:
            return json.dumps({"error": "Window not ready"})
        import webview
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=str(pathlib.Path.home()),
        )
        if not result or not result[0]:
            return json.dumps({"error": "No folder selected"})
        chosen = pathlib.Path(result[0])
        chosen.mkdir(parents=True, exist_ok=True)
        self._root = chosen
        config = AppConfig(project_root=str(chosen), config_dir=self._config_dir)
        save_config(config)
        return json.dumps({"status": "ok", "root": str(chosen)})

    def create_project(
        self, name: str, language: str = "eng", confidence_threshold: int = 70
    ) -> str:
        project = create_project(
            self._ensure_root(), name, language=language,
            confidence_threshold=confidence_threshold,
        )
        return json.dumps({"name": project.name, "path": str(project.path)})

    def run_project(
        self, name: str, deep_verify: bool = False, dpi: int = 300
    ) -> str:
        project = self._resolve_project(name)
        summary = run_project(project, deep_verify=deep_verify, deep_verify_dpi=dpi)
        return json.dumps({
            "files_processed": summary.files_processed,
            "total_redactions": summary.total_redactions,
            "files_needing_review": summary.files_needing_review,
            "report_path": str(summary.report_path) if summary.report_path else None,
        })

    def get_latest_report(self, name: str) -> str:
        project = self._resolve_project(name)
        report_files = sorted(project.reports_dir.glob("*.json"))
        if not report_files:
            return json.dumps({"schema_version": 1, "files": []})
        return report_files[-1].read_text(encoding="utf-8")

    def get_keywords(self, name: str) -> str:
        project = self._resolve_project(name)
        return project.keywords_path.read_text(encoding="utf-8")

    def get_project_settings(self, name: str) -> str:
        project = self._resolve_project(name)
        return json.dumps({
            "language": project.language,
            "confidence_threshold": project.confidence_threshold,
        })

    def save_keywords(self, name: str, content: str) -> str:
        project = self._resolve_project(name)
        project.keywords_path.write_text(content, encoding="utf-8")
        return json.dumps({"status": "ok"})

    def validate_keywords(self, content: str) -> str:
        """Validate keyword file content and report regex errors."""
        import regex

        errors: list[dict] = []
        for idx, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("regex:"):
                pattern_str = line[len("regex:"):]
                try:
                    regex.compile(pattern_str, regex.IGNORECASE)
                except regex.error as exc:
                    errors.append({
                        "line": idx,
                        "error": f"Invalid regex: {exc}",
                    })
        return json.dumps({"valid": len(errors) == 0, "errors": errors})

    def list_files(self, name: str) -> str:
        """List input files with last known status from latest report."""
        project = self._resolve_project(name)
        input_files = sorted(project.input_dir.glob("*.pdf"))
        report_files = sorted(project.reports_dir.glob("*.json"))
        report_map: dict[str, dict] = {}
        if report_files:
            try:
                latest = json.loads(report_files[-1].read_text(encoding="utf-8"))
                for entry in latest.get("files", []):
                    report_map[entry.get("file", "")] = entry
            except Exception:
                report_map = {}

        items = []
        for pdf in input_files:
            entry = report_map.get(pdf.name, {})
            items.append({
                "file": pdf.name,
                "status": entry.get("status", "not_run"),
                "redactions_applied": entry.get("redactions_applied"),
            })
        return json.dumps({"files": items})

    def add_files(self, name: str, paths: Iterable[str] | None = None) -> str:
        project = self._resolve_project(name)
        selected: list[pathlib.Path] = []
        if paths is None:
            if self._window is None:
                return json.dumps({"error": "Window not ready"})
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("PDF files (*.pdf)",),
            )
            if not result:
                return json.dumps({"status": "cancelled", "added": []})
            selected = [pathlib.Path(p) for p in result]
        else:
            selected = [pathlib.Path(p) for p in paths]

        added: list[str] = []
        skipped: list[str] = []
        for src in selected:
            if src.suffix.lower() != ".pdf":
                skipped.append(str(src))
                continue
            if src.is_symlink():
                skipped.append(str(src))
                continue
            dest = project.input_dir / src.name
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists() and counter < 1000:
                    dest = project.input_dir / f"{stem}-{counter}{suffix}"
                    counter += 1
                if dest.exists():
                    skipped.append(str(src))
                    continue
            shutil.copy2(src, dest)
            added.append(dest.name)
        return json.dumps({"status": "ok", "added": added, "skipped": skipped})

    def update_project_settings(
        self, name: str, language: str | None = None, confidence_threshold: int | None = None
    ) -> str:
        project = self._resolve_project(name)
        if language:
            project.language = language
        if confidence_threshold is not None:
            project.confidence_threshold = int(confidence_threshold)
        project.save()
        return json.dumps({
            "status": "ok",
            "language": project.language,
            "confidence_threshold": project.confidence_threshold,
        })

    def open_in_preview(self, name: str, filename: str) -> str:
        project = self._resolve_project(name)
        file_path = _resolve_output_file(project, filename)
        if file_path is None or not file_path.exists():
            return json.dumps({"error": "File not found"})
        subprocess.Popen(["open", "--", str(file_path)])
        return json.dumps({"status": "ok"})

    def reveal_in_finder(self, name: str, filename: str) -> str:
        project = self._resolve_project(name)
        file_path = _resolve_output_file(project, filename)
        if file_path is None or not file_path.exists():
            return json.dumps({"error": "File not found"})
        subprocess.Popen(["open", "-R", "--", str(file_path)])
        return json.dumps({"status": "ok"})


def _resolve_output_file(project: Project, filename: str) -> pathlib.Path | None:
    candidate = pathlib.Path(filename)
    if candidate.name != filename:
        return None
    output_dir = project.output_dir.resolve()
    resolved = (output_dir / candidate).resolve()
    try:
        resolved.relative_to(output_dir)
    except ValueError:
        return None
    return resolved
