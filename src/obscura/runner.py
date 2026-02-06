"""Run orchestrator — ties redact, sanitize, and verify into a project pipeline.

Per-file error isolation: if one file fails during sanitize or verify,
the error is recorded in the report and processing continues with the
remaining files.

Report schema: Reports use a versioned envelope format:
    { "schema_version": 1, "run_id": ..., "engine_version": ...,
      "settings": {...}, "files": [...] }
"""

from __future__ import annotations

import dataclasses
import json
import logging
import pathlib
import uuid
from datetime import datetime, timezone

import obscura
from obscura.keywords import KeywordSet
from obscura.project import Project
from obscura.redact import redact_pdf
from obscura.sanitize import sanitize_pdf
from obscura.verify import verify_pdf

logger = logging.getLogger(__name__)

REPORT_SCHEMA_VERSION = 1


@dataclasses.dataclass
class RunSummary:
    """Summary of a full project run."""

    files_processed: int
    total_redactions: int
    files_needing_review: int
    files_errored: int
    report_path: pathlib.Path | None


def run_project(
    project: Project,
    deep_verify: bool = False,
    deep_verify_dpi: int = 300,
    verbose: bool = False,
) -> RunSummary:
    """Run the full redaction pipeline on a project.

    Steps per file: redact -> sanitize -> verify.
    Each file is isolated — errors in one file don't crash the batch.

    Args:
        project: The project to process.
        deep_verify: Enable rasterize-and-scan verification.
        deep_verify_dpi: DPI for deep verify rasterization.
        verbose: Include context snippets in verification reports.

    Returns:
        RunSummary with aggregate results.

    Raises:
        ValueError: If keywords file is empty (no keywords defined).
    """
    keywords = KeywordSet.from_file(project.keywords_path)

    if keywords.is_empty:
        raise ValueError(
            f"Keywords file is empty: {project.keywords_path}. "
            "Add at least one keyword before running redaction."
        )

    input_pdfs = sorted(project.input_dir.glob("*.pdf"))
    if not input_pdfs:
        return RunSummary(
            files_processed=0,
            total_redactions=0,
            files_needing_review=0,
            files_errored=0,
            report_path=None,
        )

    total_redactions = 0
    files_needing_review = 0
    files_errored = 0
    all_reports: list[dict] = []

    for pdf_path in input_pdfs:
        output_path = project.output_dir / pdf_path.name

        try:
            redaction_result = redact_pdf(
                pdf_path, output_path, keywords, language=project.language
            )
            total_redactions += redaction_result.redaction_count + redaction_result.ocr_redaction_count

            if redaction_result.status == "ok":
                sanitize_pdf(output_path, output_path)

                report = verify_pdf(
                    output_path,
                    keywords,
                    confidence_threshold=project.confidence_threshold,
                    language=project.language,
                    deep_verify=deep_verify,
                    deep_verify_dpi=deep_verify_dpi,
                    verbose=verbose,
                    source_hash=redaction_result.source_hash,
                )
                if report.status in ("needs_review", "unreadable"):
                    files_needing_review += 1
                report_dict = report.to_dict()
                report_dict["redactions_applied"] = redaction_result.redaction_count
                report_dict["ocr_redactions_applied"] = redaction_result.ocr_redaction_count
                report_dict["ocr_used"] = redaction_result.ocr_used
                report_dict["missed_keywords"] = redaction_result.missed_keywords
                all_reports.append(report_dict)
            else:
                all_reports.append({
                    "file": pdf_path.name,
                    "status": redaction_result.status,
                    "source_hash": redaction_result.source_hash,
                    "redactions_applied": 0,
                })
                if redaction_result.status in ("password_protected", "corrupt"):
                    files_needing_review += 1

        except Exception as exc:
            logger.error("Error processing %s: %s", pdf_path.name, exc)
            files_errored += 1
            all_reports.append({
                "file": pdf_path.name,
                "status": "error",
                "error": str(exc),
            })

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"

    report_data = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "engine_version": obscura.__version__,
        "project_name": project.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "deep_verify": deep_verify,
            "deep_verify_dpi": deep_verify_dpi if deep_verify else None,
            "language": project.language,
            "confidence_threshold": project.confidence_threshold,
            "keywords_hash": keywords.keyword_hash(),
        },
        "files": all_reports,
    }

    report_path = project.reports_dir / f"{timestamp}.json"
    report_path.write_text(
        json.dumps(report_data, indent=2) + "\n", encoding="utf-8"
    )

    project.last_run = datetime.now(timezone.utc).isoformat()
    project.save()

    return RunSummary(
        files_processed=len(input_pdfs),
        total_redactions=total_redactions,
        files_needing_review=files_needing_review,
        files_errored=files_errored,
        report_path=report_path,
    )
