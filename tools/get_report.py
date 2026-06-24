# tools/get_report.py — Build full session report in JSON or Markdown
from typing import Dict, Any
from datetime import datetime, timezone

from core.session import Session
from strategy.registry import StrategyRegistry
from models.report import QEReport, LaneCoverageReport, ViolationReport
from core.logger import get_logger

logger = get_logger("tools.get_report")


def handle_get_report(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """Build full session report from in-memory state."""
    fmt = arguments.get("format", "json")

    scan = session.scan_results or {}
    enforce = session.enforce_result

    # Build coverage reports
    coverage_reports = []
    coverage_by_lane = scan.get("coverage_by_lane", {})
    for lane_name, data in coverage_by_lane.items():
        coverage_reports.append(LaneCoverageReport(
            lane=lane_name,
            required=data.get("required", False),
            threshold=data.get("threshold", 0.0),
            actual=data.get("actual", 0.0),
            status=data.get("status", "NOT_MEASURED"),
            files_missing=data.get("files_missing", []),
        ))

    # Build violation reports
    violation_reports = []
    for val in session.validation_results:
        for v in val.get("violations", []):
            violation_reports.append(ViolationReport(
                file=val.get("file", ""),
                rule=v.get("rule", ""),
                severity=v.get("severity", "warning"),
                line=v.get("line", 0),
                detail=v.get("detail", ""),
            ))

    # Get strategy info
    try:
        strategy = registry.active()
        strategy_id = strategy.id
        strategy_version = strategy.version
    except Exception:
        strategy_id = session.active_strategy_id or "unknown"
        strategy_version = "unknown"

    report = QEReport(
        generated_at=datetime.now(timezone.utc),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        repo_path=scan.get("repo_path", ""),
        enforce_passed=enforce.get("passed") if enforce else None,
        files_analysed=scan.get("files_analysed", 0),
        test_files_found=scan.get("test_files_found", 0),
        coverage=coverage_reports,
        violations=violation_reports,
        test_plans=list(session.test_plans.values()),
        smells=scan.get("smells", []),
        blockers=enforce.get("blockers", []) if enforce else [],
        warnings=enforce.get("warnings", []) if enforce else [],
    )

    if fmt == "json":
        return {"report": report.model_dump(mode="json"), "format": "json"}
    elif fmt == "markdown":
        md = _render_markdown(report)
        return {"report": md, "format": "markdown"}
    else:
        return {"error": f"Unsupported format: {fmt}. Use 'json' or 'markdown'."}


def _render_markdown(report: QEReport) -> str:
    """Render the QE report as Markdown."""
    parts = [
        f"# QE-MCP Report",
        f"**Generated:** {report.generated_at.isoformat()}",
        f"**Strategy:** {report.strategy_id} v{report.strategy_version}",
        f"**Repo:** {report.repo_path}",
        f"**Enforce Passed:** {'✅ Yes' if report.enforce_passed else '❌ No' if report.enforce_passed is False else '⏳ Not run'}",
        "",
        "## Summary",
        f"- Files analysed: {report.files_analysed}",
        f"- Test files found: {report.test_files_found}",
        "",
        "## Coverage by Lane",
        "",
        "| Lane | Required | Threshold | Actual | Status |",
        "|------|----------|-----------|--------|--------|",
    ]

    for cov in report.coverage:
        parts.append(
            f"| {cov.lane} | {'✓' if cov.required else '○'} | "
            f"{cov.threshold:.0%} | {cov.actual:.0%} | {cov.status} |"
        )

    if report.violations:
        parts.extend(["", "## Violations", ""])
        parts.append("| File | Rule | Severity | Line | Detail |")
        parts.append("|------|------|----------|------|--------|")
        for v in report.violations[:50]:  # Cap at 50
            parts.append(f"| {v.file} | {v.rule} | {v.severity} | {v.line} | {v.detail} |")

    if report.smells:
        parts.extend(["", "## Testability Smells", ""])
        for smell in report.smells:
            parts.append(f"- **{smell.get('file', '?')}**: {smell.get('smell', '?')}")

    if report.blockers:
        parts.extend(["", "## Blockers", ""])
        for blocker in report.blockers:
            parts.append(f"- ❌ **{blocker.get('type', '?')}** — Lane: {blocker.get('lane', '?')}, "
                         f"Threshold: {blocker.get('threshold', '?')}, Actual: {blocker.get('actual', '?')}")

    if report.warnings:
        parts.extend(["", "## Warnings", ""])
        for w in report.warnings:
            parts.append(f"- ⚠ {w.get('file', '?')}: {w.get('issue', '?')}")

    parts.extend(["", f"---", f"*{len(report.test_plans)} test plan(s) generated this session.*"])
    return "\n".join(parts)
