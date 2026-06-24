# tools/enforce.py — Quality gate: full sweep analyse + validate + threshold check
from typing import Dict, Any, List
from pathlib import Path

from core.session import Session
from strategy.registry import StrategyRegistry
from tools.analyse_repo import handle_analyse_repo
from tools.validate_tests import handle_validate_tests
from core.logger import get_logger

logger = get_logger("tools.enforce")


def handle_enforce(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Full sweep: analyse + validate + compare to thresholds.
    Designed to be treated as a hard gate — passed:false is a blocker.
    """
    repo_path = arguments.get("repo_path", "")
    strategy_id = arguments.get("strategy_id", "")

    if not repo_path:
        return {"error": "repo_path is required"}
    if not strategy_id:
        return {"error": "strategy_id is required"}

    # Step 1: Run analysis
    analysis = handle_analyse_repo(
        {"repo_path": repo_path, "strategy_id": strategy_id},
        session,
        registry,
    )
    if "error" in analysis:
        return {"error": f"Analysis failed: {analysis['error']}"}

    # Step 2: Validate all discovered test files
    try:
        strategy = registry.active()
    except Exception as e:
        return {"error": f"No strategy loaded: {e}"}

    test_files_found = analysis.get("test_files_found", 0)
    validation_errors: List[Dict] = []

    # Find test files from the scan
    scan = session.scan_results
    if scan:
        gap_map = scan.get("gap_map", {})
        for src_file, data in gap_map.items():
            existing_tests = data.get("existing_tests", [])
            for test_file in existing_tests:
                test_path = Path(test_file)
                if not test_path.is_absolute():
                    test_path = Path(repo_path) / test_file
                if test_path.exists():
                    val_result = handle_validate_tests(
                        {"test_file": str(test_path), "strategy_id": strategy_id},
                        session,
                        registry,
                    )
                    if not val_result.get("valid", True):
                        validation_errors.append({
                            "file": str(test_path),
                            "violations": val_result.get("violations", []),
                        })

    # Step 3: Check coverage thresholds
    coverage_by_lane = analysis.get("coverage_by_lane", {})
    lanes = strategy.get_test_lanes()
    blockers: List[Dict] = []
    warnings: List[Dict] = []

    for lane in lanes:
        lane_name = lane.lane_type.value
        lane_data = coverage_by_lane.get(lane_name, {})

        if lane.required and lane_data.get("status") == "BREACH":
            blockers.append({
                "type": "coverage_threshold_breach",
                "lane": lane_name,
                "threshold": lane.coverage_threshold,
                "actual": lane_data.get("actual", 0.0),
                "files_missing_tests": lane_data.get("files_missing", []),
            })

    # Step 4: Add validation error blockers
    for val_err in validation_errors:
        error_count = sum(
            1 for v in val_err.get("violations", [])
            if v.get("severity") == "error"
        )
        if error_count > 0:
            blockers.append({
                "type": "validation_errors_present",
                "file": val_err["file"],
                "error_count": error_count,
                "detail": "Oracle completeness or structural violations block acceptance",
            })

        warning_count = sum(
            1 for v in val_err.get("violations", [])
            if v.get("severity") == "warning"
        )
        if warning_count > 0:
            warnings.append({
                "file": val_err["file"],
                "issue": f"{warning_count} validation warnings",
            })

    # Build smells as warnings
    for smell in analysis.get("smells", []):
        warnings.append({
            "file": smell.get("file", ""),
            "issue": smell.get("smell", "unknown smell"),
        })

    passed = len(blockers) == 0

    result = {
        "passed": passed,
        "strategy_id": strategy_id,
        "summary": {
            "files_analysed": analysis.get("files_analysed", 0),
            "test_files_found": test_files_found,
            "coverage_by_lane": coverage_by_lane,
        },
        "blockers": blockers,
        "warnings": warnings,
    }

    session.store_enforce(result)
    logger.info(f"Enforce gate: passed={passed}, blockers={len(blockers)}, warnings={len(warnings)}")

    return result
