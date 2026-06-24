# tools/get_generation_brief.py — Assemble full agent prompt brief via strategy
from typing import Dict, Any

from core.session import Session
from strategy.registry import StrategyRegistry
from strategy.base import SourceClassification
from core.logger import get_logger

logger = get_logger("tools.get_generation_brief")


def handle_get_generation_brief(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Assemble the full agent prompt brief via the strategy's
    build_generation_brief() method. MCP never calls LLMs —
    it returns the brief for the agent to act on.
    """
    plan_id = arguments.get("plan_id", "")
    file_path = arguments.get("file_path", "")

    if not plan_id:
        return {"error": "plan_id is required"}
    if not file_path:
        return {"error": "file_path is required"}

    # Get plan from session
    plan_data = session.get_plan(plan_id)
    if not plan_data:
        return {"error": f"Plan '{plan_id}' not found in session. Run generate_test_plan first."}

    # Get strategy
    try:
        strategy = registry.active()
    except Exception as e:
        return {"error": f"No strategy loaded: {e}"}

    # Get classification from scan results
    scan = session.scan_results
    classification_data = None
    if scan and "gap_map" in scan:
        for key, value in scan["gap_map"].items():
            if key.endswith(file_path) or file_path.endswith(key) or key == file_path:
                classification_data = value
                break

    if not classification_data:
        # Build minimal classification from plan data
        plan_class = plan_data.get("classification", {})
        classification = SourceClassification(
            class_type=plan_class.get("class_type", "unknown"),
            complexity_score=plan_class.get("complexity_score", 1),
            testability_issues=[],
            required_lanes=[],
            ast_metrics={},
        )
    else:
        from strategy.base import TestLaneType
        classification = SourceClassification(
            class_type=classification_data["class_type"],
            complexity_score=classification_data.get("complexity_score", 1),
            testability_issues=classification_data.get("testability_issues", []),
            required_lanes=[
                TestLaneType(lt) for lt in classification_data.get("required_lanes", [])
                if lt in [e.value for e in TestLaneType]
            ],
            ast_metrics=classification_data.get("ast_metrics", {}),
        )

    # Get user_context from the plan's test cases
    user_context = ""
    test_cases = plan_data.get("test_cases", [])
    if test_cases:
        first_given = test_cases[0].get("given", "")
        user_context = first_given

    # Build brief via strategy
    brief = strategy.build_generation_brief(
        classification=classification,
        user_context=user_context,
        file_path=file_path,
        test_plan=test_cases,
    )

    logger.info(f"Generation brief assembled for plan {plan_id}, file {file_path}")

    return {
        "brief": brief,
        "plan_id": plan_id,
        "strategy_id": strategy.id,
        "constraints": {
            "naming": strategy.get_naming_conventions().__dict__,
            "lanes": [lane.lane_type.value for lane in strategy.get_test_lanes() if lane.required],
            "oracle_fields": [r.__dict__ for r in strategy.get_oracle_rules()],
        },
    }
