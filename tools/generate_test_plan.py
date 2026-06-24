# tools/generate_test_plan.py — Produce TC-001..N prescriptive test plan
from typing import Dict, Any, List
import uuid
from datetime import datetime

from core.session import Session
from strategy.registry import StrategyRegistry
from models.plan import TestPlan, TestCase
from core.logger import get_logger

logger = get_logger("tools.generate_test_plan")


def handle_generate_test_plan(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Produce TC-001..N prescriptive test plan with Given/When/Then oracles.
    user_context is mandatory — tests derived from implementation alone
    without behavioral context will assert the wrong expected state.
    """
    file_path = arguments.get("file_path", "")
    strategy_id = arguments.get("strategy_id", "")
    user_context = arguments.get("user_context", "")

    if not file_path:
        return {"error": "file_path is required"}
    if not strategy_id:
        return {"error": "strategy_id is required"}
    if not user_context:
        return {
            "error": "user_context is required",
            "detail": "Tests derived from implementation alone without behavioral "
                      "context will assert the wrong expected state whenever the "
                      "implementation contains a bug.",
        }

    try:
        strategy = registry.active()
    except Exception as e:
        return {"error": f"No strategy loaded: {e}"}

    # Look up classification from session scan results
    scan = session.scan_results
    if not scan or "gap_map" not in scan:
        return {
            "error": "No scan results found. Run analyse_repo first.",
        }

    gap_map = scan["gap_map"]
    classification_data = None
    for key, value in gap_map.items():
        if key.endswith(file_path) or file_path.endswith(key) or key == file_path:
            classification_data = value
            break

    if not classification_data:
        return {
            "error": f"File '{file_path}' not found in scan results. Run analyse_repo first.",
        }

    class_type = classification_data["class_type"]
    public_interface = classification_data.get("ast_metrics", {}).get("public_interface", [])

    # Get oracle rules for this class type
    oracle_rules = strategy.get_oracle_rules()
    matching_rule = None
    for rule in oracle_rules:
        if rule.source_class_type == class_type:
            matching_rule = rule
            break

    if not matching_rule:
        # Fallback to generic rule
        matching_rule = oracle_rules[0] if oracle_rules else None

    # Generate test cases
    test_cases: List[TestCase] = []
    tc_counter = 1

    naming = strategy.get_naming_conventions()
    required_lanes = classification_data.get("required_lanes", ["unit"])

    for method_name in public_interface:
        # P1: Happy path test
        tc_id = f"TC-{tc_counter:03d}"
        tc_name = _generate_test_name(method_name, "valid_input", "success", naming.test_method_pattern)
        lane = required_lanes[0] if required_lanes else "unit"

        test_cases.append(TestCase(
            id=tc_id,
            name=tc_name,
            lane=lane,
            priority="P1",
            method_under_test=method_name,
            given=f"Valid input for {method_name} — {user_context}",
            when=f"{method_name}() is invoked with valid input",
            then=f"Expected successful outcome per behavioral contract",
            expected_state={"status": "success"},
            oracle_fields_required=matching_rule.required_oracle_fields if matching_rule else ["given", "when", "then"],
            mutation_sensitive=matching_rule.mutation_sensitive if matching_rule else False,
        ))
        tc_counter += 1

        # P2: Error / edge case test
        tc_id = f"TC-{tc_counter:03d}"
        tc_name = _generate_test_name(method_name, "invalid_input", "error", naming.test_method_pattern)

        test_cases.append(TestCase(
            id=tc_id,
            name=tc_name,
            lane=lane,
            priority="P2",
            method_under_test=method_name,
            given=f"Invalid or edge-case input for {method_name}",
            when=f"{method_name}() is invoked with invalid input",
            then=f"Expected error handling per behavioral contract",
            expected_state={"status": "error"},
            oracle_fields_required=matching_rule.required_oracle_fields if matching_rule else ["given", "when", "then"],
            mutation_sensitive=False,
        ))
        tc_counter += 1

    # If no public interface was detected, generate at least one test case
    if not test_cases:
        test_cases.append(TestCase(
            id="TC-001",
            name=f"test_{class_type}_behaves_correctly",
            lane=required_lanes[0] if required_lanes else "unit",
            priority="P1",
            method_under_test="<to be determined by AI analysis>",
            given=f"Preconditions for {class_type} — {user_context}",
            when=f"Primary action is invoked",
            then=f"Expected outcome per behavioral contract",
            oracle_fields_required=matching_rule.required_oracle_fields if matching_rule else ["given", "when", "then"],
            mutation_sensitive=matching_rule.mutation_sensitive if matching_rule else False,
        ))

    # Build coverage targets
    coverage_targets: Dict[str, int] = {}
    for lane in required_lanes:
        coverage_targets[lane] = sum(1 for tc in test_cases if tc.lane == lane)

    # Create plan
    plan_id = f"plan_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file_path.split('/')[-1].replace('.', '_')}"
    plan = TestPlan(
        plan_id=plan_id,
        strategy_id=strategy_id,
        source_file=file_path,
        classification={"class_type": class_type, "complexity_score": classification_data.get("complexity_score", 1)},
        test_cases=test_cases,
        coverage_targets=coverage_targets,
        generation_brief_ready=True,
    )

    # Store in session
    session.store_plan(plan.model_dump())
    logger.info(f"Test plan generated: {plan_id} with {len(test_cases)} test cases")

    return plan.model_dump()


def _generate_test_name(method: str, condition: str, expected: str, pattern: str) -> str:
    """Generate a test name following the naming convention pattern."""
    # For Kotlin backtick names
    if "`" in pattern:
        return f"`{method} {condition} expects {expected}`"
    # For Python test_action_when_condition_expects_expected
    return f"test_{method}_when_{condition}_expects_{expected}"
