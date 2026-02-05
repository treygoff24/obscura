"""CLI entrypoint for Obscura."""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys

from obscura.project import Project, create_project, discover_projects
from obscura.runner import run_project

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="obscura",
        description="Local-only PDF redaction tool.",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: WARNING).",
    )
    subparsers = parser.add_subparsers(dest="command")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new project.")
    create_parser.add_argument("--root", type=pathlib.Path, required=True, help="Project root directory.")
    create_parser.add_argument("--name", type=str, required=True, help="Project name.")
    create_parser.add_argument("--language", type=str, default="eng", help="Tesseract language code (default: eng).")
    create_parser.add_argument("--threshold", type=int, default=70, help="OCR confidence threshold 0-100 (default: 70).")

    # run
    run_parser = subparsers.add_parser("run", help="Run redaction on a project.")
    run_parser.add_argument("project_path", type=pathlib.Path, help="Path to project folder.")
    run_parser.add_argument("--deep-verify", action="store_true", help="Enable rasterize-and-scan verify.")
    run_parser.add_argument("--dpi", type=int, default=300, help="DPI for deep verify (default: 300).")
    run_parser.add_argument("--verbose", action="store_true", help="Include context snippets in reports.")

    # list
    list_parser = subparsers.add_parser("list", help="List projects.")
    list_parser.add_argument("--root", type=pathlib.Path, required=True, help="Project root directory.")

    # report
    report_parser = subparsers.add_parser("report", help="Show verification report.")
    report_parser.add_argument("project_path", type=pathlib.Path, help="Path to project folder.")
    report_parser.add_argument("--last", action="store_true", help="Show the most recent report.")
    report_parser.add_argument("--list", dest="list_reports", action="store_true", help="List all available reports.")

    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(2)

    if args.command == "create":
        _cmd_create(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "list":
        _cmd_list(args)
    elif args.command == "report":
        _cmd_report(args)


def _cmd_create(args: argparse.Namespace) -> None:
    try:
        project = create_project(
            args.root,
            args.name,
            language=args.language,
            confidence_threshold=args.threshold,
        )
        print(f"Created project: {project.name}")
        print(f"  Path: {project.path}")
        print(f"  Language: {project.language}")
        print(f"  Confidence threshold: {project.confidence_threshold}")
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_run(args: argparse.Namespace) -> None:
    try:
        project = Project.load(args.project_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        summary = run_project(
            project,
            deep_verify=args.deep_verify,
            deep_verify_dpi=args.dpi,
            verbose=args.verbose,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Processed {summary.files_processed} file(s).")
    print(f"Total redactions: {summary.total_redactions}")
    if summary.files_needing_review > 0:
        print(f"Files needing review: {summary.files_needing_review}")
    if summary.files_errored > 0:
        print(f"Files with errors: {summary.files_errored}")
    if summary.report_path:
        print(f"Report: {summary.report_path}")


def _cmd_list(args: argparse.Namespace) -> None:
    projects = discover_projects(args.root)
    if not projects:
        print("No projects found.")
        return
    for p in projects:
        status = f"last run: {p.last_run}" if p.last_run else "not yet run"
        print(f"  {p.name}  ({status})")


def _cmd_report(args: argparse.Namespace) -> None:
    try:
        project = Project.load(args.project_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    report_files = sorted(project.reports_dir.glob("*.json"))
    if not report_files:
        print("No reports found.")
        return

    if args.list_reports:
        for rf in report_files:
            print(f"  {rf.name}")
        return

    if args.last:
        report_path = report_files[-1]
    else:
        report_path = report_files[-1]

    data = json.loads(report_path.read_text())
    print(json.dumps(data, indent=2))
