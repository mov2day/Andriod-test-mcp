# tools/analyse_repo.py — Discover source files, classify via strategy, produce gap map
from typing import Dict, Any, List
from pathlib import Path

from core.session import Session
from core.file_scanner import FileScanner
from core.ast_walker import ASTWalker
from strategy.registry import StrategyRegistry
from strategy.base import SourceClassification
from core.logger import get_logger

logger = get_logger("tools.analyse_repo")


def handle_analyse_repo(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Discover source files, run classification via strategy plugin,
    produce gap map with coverage by lane, and generate an analysis prompt
    instructing the invoking AI to perform deep semantic analysis.
    """
    repo_path = arguments.get("repo_path", "")
    strategy_id = arguments.get("strategy_id", "")

    if not repo_path:
        return {"error": "repo_path is required"}
    if not strategy_id:
        return {"error": "strategy_id is required"}

    try:
        if strategy_id and strategy_id != registry.active_id:
            strategy = registry.load(strategy_id)
        else:
            strategy = registry.active()
    except Exception as e:
        return {"error": f"Strategy load failed: {e}"}

    session.active_strategy_id = strategy_id
    scanner = FileScanner(repo_path)
    ast_walker = ASTWalker()
    lanes = strategy.get_test_lanes()
    naming = strategy.get_naming_conventions()

    # Discover source files (exclude test files, build dirs, etc.)
    lang = strategy.target_language
    if lang == "python":
        source_globs = ["**/*.py"]
        exclude = ["**/test_*", "**/tests/**", "**/__pycache__/**", "**/venv/**", "**/.venv/**"]
    elif lang == "kotlin":
        source_globs = ["**/*.kt"]
        exclude = ["**/test/**", "**/androidTest/**", "**/build/**", "**/.gradle/**"]
    else:
        source_globs = ["**/*"]
        exclude = []

    source_files = scanner.discover_source_files(source_globs, exclude)
    test_globs = [lane.file_glob for lane in lanes]
    test_files = scanner.find_test_files(test_globs)
    # Derive replacement template from language (the naming.test_file_pattern is a
    # regex which pair_source_to_test cannot use — it expects a {name} template).
    if lang == "python":
        pair_template = "test_{name}.py"
    elif lang == "kotlin":
        pair_template = "{name}Test.kt"
    else:
        pair_template = "test_{name}"
    source_test_pairs = scanner.pair_source_to_test(source_files, test_files, pair_template)

    # Classify each source file
    gap_map: Dict[str, Dict] = {}
    all_smells: List[Dict] = []
    files_requiring_analysis: List[Dict] = []

    for src_file in source_files:
        src_path = Path(repo_path) / src_file
        try:
            content = src_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Cannot read {src_file}: {e}")
            continue

        # Classify via strategy
        try:
            classification = strategy.classify_source_file(str(src_file), content)
        except Exception as e:
            logger.warning(f"Classification failed for {src_file}: {e}")
            classification = SourceClassification(
                class_type="unknown",
                complexity_score=1,
                testability_issues=[f"classification_error: {e}"],
                required_lanes=[],
                ast_metrics={},
            )

        # Determine existing tests and missing lanes
        existing_tests = source_test_pairs.get(str(src_file), [])
        existing_test_list = existing_tests if isinstance(existing_tests, list) else [existing_tests] if existing_tests else []

        # Determine which lanes are covered by existing tests
        covered_lanes = _infer_covered_lanes(existing_test_list, lanes, strategy)
        missing_lanes = [
            lt.value for lt in classification.required_lanes
            if lt.value not in covered_lanes
        ]

        # Build gap entry
        rel_path = str(src_path.relative_to(repo_path)) if str(src_file).startswith(repo_path) else str(src_file)
        gap_entry = {
            "class_type": classification.class_type,
            "complexity_score": classification.complexity_score,
            "required_lanes": [lt.value for lt in classification.required_lanes],
            "existing_tests": existing_test_list,
            "missing_lanes": missing_lanes,
            "testability_issues": classification.testability_issues,
            "ast_metrics": classification.ast_metrics,
        }
        gap_map[rel_path] = gap_entry

        # Collect smells
        for issue in classification.testability_issues:
            all_smells.append({"file": rel_path, "smell": issue})

        # Track files needing deeper analysis
        if missing_lanes:
            files_requiring_analysis.append({
                "file": rel_path,
                "class_type": classification.class_type,
                "missing_lanes": missing_lanes,
                "public_interface": classification.ast_metrics.get("public_interface", []),
            })

    # Compute coverage by lane
    coverage_by_lane: Dict[str, Dict] = {}
    for lane in lanes:
        files_requiring = [
            f for f, g in gap_map.items()
            if lane.lane_type.value in g["required_lanes"]
        ]
        files_with_tests = [
            f for f in files_requiring
            if lane.lane_type.value not in gap_map[f]["missing_lanes"]
        ]
        total = len(files_requiring)
        covered = len(files_with_tests)
        actual = covered / total if total > 0 else 1.0
        status = "OK" if actual >= lane.coverage_threshold or not lane.required else "BREACH"
        if total == 0:
            status = "NOT_MEASURED"

        coverage_by_lane[lane.lane_type.value] = {
            "required": lane.required,
            "threshold": lane.coverage_threshold,
            "actual": round(actual, 2),
            "status": status,
            "files_missing": [
                f for f in files_requiring
                if lane.lane_type.value in gap_map[f]["missing_lanes"]
            ],
        }

    # Build the AI analysis prompt
    analysis_prompt = _build_analysis_prompt(files_requiring_analysis, strategy)

    # Store in session
    scan_results = {
        "repo_path": repo_path,
        "strategy_id": strategy_id,
        "files_analysed": len(source_files),
        "test_files_found": len(test_files),
        "gap_map": gap_map,
        "coverage_by_lane": coverage_by_lane,
        "smells": all_smells,
    }
    session.store_scan(scan_results)

    return {
        "files_analysed": len(source_files),
        "test_files_found": len(test_files),
        "gap_map": gap_map,
        "coverage_by_lane": coverage_by_lane,
        "smells": all_smells,
        "analysis_prompt": analysis_prompt,
    }


def _infer_covered_lanes(test_files: List[str], lanes: list, strategy) -> List[str]:
    """Determine which lanes are covered by existing test files.

    Delegates to the strategy's ``infer_lane_from_test_path`` so that
    lane-inference logic stays inside the plugin, not in the core tool.
    """
    covered = []
    for tf in test_files:
        lane = strategy.infer_lane_from_test_path(tf)
        if lane:
            covered.append(lane)
    return list(set(covered))


def _build_analysis_prompt(files_requiring_analysis: List[Dict], strategy) -> str:
    """
    Build a structured prompt instructing the invoking AI to perform
    deep semantic analysis of each file that has missing test coverage.
    """
    if not files_requiring_analysis:
        return "All source files have adequate test coverage. No further analysis required."

    prompt_parts = [
        "# Detailed Source File Analysis Required",
        "",
        "The following source files have gaps in test coverage. You must read each file,",
        "deeply understand its semantics, and produce the detailed classification below.",
        "",
        "## Instructions",
        "For EACH file listed below:",
        "1. Read the full file content",
        "2. Identify: what the class/module does, its public API, state transitions,",
        "   dependencies, error handling paths, edge cases",
        "3. For ViewModels: list every sealed UiState subclass",
        "4. For Composables: list every UI state handled, user actions, selectors (testTags)",
        "5. For DTOs/Mappers: list nullable fields, enum fallbacks, mapping edge cases",
        "6. Output the analysis in the exact JSON format below",
        "",
        "## Required Output Format (per file)",
        "```json",
        "{",
        '  "file": "<file_path>",',
        '  "class_type": "<detected_type>",',
        '  "public_api": ["<method1>", "<method2>"],',
        '  "state_transitions": ["<state1> -> <state2>"],',
        '  "dependencies": ["<dep1>", "<dep2>"],',
        '  "error_paths": ["<error_case1>", "<error_case2>"],',
        '  "edge_cases": ["<edge1>", "<edge2>"],',
        '  "sealed_states": ["<State1>", "<State2>"],',
        '  "ui_states_handled": ["Loading", "Success", "Error"],',
        '  "user_actions": ["retry", "click", "scroll"],',
        '  "selectors": {"<name>": "<testTag>"},',
        '  "nullable_fields": ["<field1>"],',
        '  "missing_lanes": ["<lane>"],',
        '  "recommended_test_count": <int>,',
        '  "testability_smells": ["<smell1>"]',
        "}",
        "```",
        "",
        "## Files Requiring Analysis",
    ]

    for entry in files_requiring_analysis:
        prompt_parts.append(f"\n### {entry['file']}")
        prompt_parts.append(f"- **Detected type:** {entry['class_type']}")
        prompt_parts.append(f"- **Missing lanes:** {', '.join(entry['missing_lanes'])}")
        if entry.get("public_interface"):
            prompt_parts.append(f"- **Known public API:** {', '.join(entry['public_interface'][:10])}")
        prompt_parts.append("")

    return "\n".join(prompt_parts)
