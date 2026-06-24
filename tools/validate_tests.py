# tools/validate_tests.py — 7-layer validation of generated tests
import ast
from typing import Dict, Any, List
from pathlib import Path

from core.session import Session
from strategy.registry import StrategyRegistry
from strategy.base import SourceClassification, TestLaneType
from core.logger import get_logger

logger = get_logger("tools.validate_tests")


def handle_validate_tests(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Check generated tests against naming conventions, oracle completeness,
    required lane coverage. Runs MCP Core checks + strategy-specific checks.
    """
    test_file = arguments.get("test_file", "")
    strategy_id = arguments.get("strategy_id", "")

    if not test_file:
        return {"error": "test_file is required"}
    if not strategy_id:
        return {"error": "strategy_id is required"}

    # Read test file
    test_path = Path(test_file)
    if not test_path.exists():
        return {"error": f"Test file not found: {test_file}"}

    try:
        test_content = test_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"Cannot read test file: {e}"}

    # Get strategy
    try:
        strategy = registry.active()
    except Exception as e:
        return {"error": f"No strategy loaded: {e}"}

    # Find source classification from session
    source_classification = _find_classification(test_file, session, strategy)

    # ── MCP Core checks ──────────────────────────────────────────
    core_violations: List[Dict] = []

    # Layer 1: Syntax parse
    lang = strategy.target_language
    if lang == "python":
        try:
            ast.parse(test_content)
        except SyntaxError as e:
            core_violations.append({
                "rule": "syntax_parse",
                "severity": "error",
                "line": e.lineno or 0,
                "detail": f"Syntax error: {e.msg}",
            })

    # Layer 6: No bare asserts (Python only)
    if lang == "python":
        try:
            tree = ast.parse(test_content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assert):
                    if isinstance(node.test, ast.Constant) and node.test.value is True:
                        core_violations.append({
                            "rule": "no_bare_asserts",
                            "severity": "warning",
                            "line": node.lineno,
                            "detail": "Bare 'assert True' is a vacuous oracle",
                        })
                    if (isinstance(node.test, ast.Compare)
                        and isinstance(node.test.ops[0], ast.IsNot)
                        and isinstance(node.test.comparators[0], ast.Constant)
                        and node.test.comparators[0].value is None
                        and not node.msg):
                        core_violations.append({
                            "rule": "no_bare_asserts",
                            "severity": "warning",
                            "line": node.lineno,
                            "detail": "'assert x is not None' as sole assertion is a weak oracle",
                        })
        except SyntaxError:
            pass  # Already caught above

    # Layer 7: No skipped tests
    lanes = strategy.get_test_lanes()
    max_skips = max((lane.max_allowed_skips for lane in lanes), default=0)

    if lang == "python":
        skip_count = test_content.count("@pytest.mark.skip") + test_content.count("@unittest.skip")
        if skip_count > max_skips:
            core_violations.append({
                "rule": "no_skipped_tests",
                "severity": "error",
                "line": 0,
                "detail": f"{skip_count} skipped tests exceed max_allowed_skips={max_skips}",
            })
    elif lang == "kotlin":
        skip_count = test_content.count("@Ignore") + test_content.count("@Disabled")
        if skip_count > max_skips:
            core_violations.append({
                "rule": "no_skipped_tests",
                "severity": "error",
                "line": 0,
                "detail": f"{skip_count} skipped tests exceed max_allowed_skips={max_skips}",
            })

    # ── Strategy-specific validation ─────────────────────────────
    try:
        strategy_result = strategy.validate_generated_test(test_content, source_classification)
    except Exception as e:
        logger.error(f"Strategy validation failed: {e}")
        strategy_result = {
            "valid": False,
            "violations": [{"rule": "strategy_error", "severity": "error", "line": 0, "detail": str(e)}],
            "oracle_completeness": 0.0,
            "lanes_covered": [],
            "missing_lanes": [],
        }

    # Merge violations
    all_violations = core_violations + strategy_result.get("violations", [])
    has_errors = any(v["severity"] == "error" for v in all_violations)

    result = {
        "valid": not has_errors,
        "violations": all_violations,
        "oracle_completeness": strategy_result.get("oracle_completeness", 0.0),
        "lanes_covered": strategy_result.get("lanes_covered", []),
        "missing_lanes": strategy_result.get("missing_lanes", []),
    }

    # Store in session
    session.store_validation({"file": test_file, **result})
    logger.info(f"Validated {test_file}: valid={result['valid']}, violations={len(all_violations)}")

    return result


def _find_classification(
    test_file: str,
    session: Session,
    strategy,
) -> SourceClassification:
    """Find the source classification for a test file from session scan results."""
    scan = session.scan_results
    if scan and "gap_map" in scan:
        # Try to match test file to a source file
        test_base = Path(test_file).stem  # e.g. "test_order_service" or "OrderServiceTest"
        for src_path, data in scan["gap_map"].items():
            src_base = Path(src_path).stem
            if src_base in test_base or test_base.replace("test_", "").replace("Test", "") == src_base:
                return SourceClassification(
                    class_type=data["class_type"],
                    complexity_score=data.get("complexity_score", 1),
                    testability_issues=data.get("testability_issues", []),
                    required_lanes=[
                        TestLaneType(lt) for lt in data.get("required_lanes", [])
                        if lt in [e.value for e in TestLaneType]
                    ],
                    ast_metrics=data.get("ast_metrics", {}),
                )

    # Fallback: generic classification
    return SourceClassification(
        class_type="unknown",
        complexity_score=1,
        testability_issues=[],
        required_lanes=[TestLaneType.UNIT],
        ast_metrics={},
    )
