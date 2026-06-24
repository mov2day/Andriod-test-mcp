# tools/diff_coverage.py — V2: PR-scoped gap analysis via git diff
import subprocess
from typing import Dict, Any, List
from pathlib import Path

from core.session import Session
from strategy.registry import StrategyRegistry
from tools.analyse_repo import handle_analyse_repo
from core.logger import get_logger

logger = get_logger("tools.diff_coverage")


def handle_diff_coverage(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    PR-scoped gap analysis: only analyse files changed in the current
    branch vs base_ref. Uses git diff --name-only.
    """
    repo_path = arguments.get("repo_path", "")
    strategy_id = arguments.get("strategy_id", "")
    base_ref = arguments.get("base_ref", "main")

    if not repo_path:
        return {"error": "repo_path is required"}
    if not strategy_id:
        return {"error": "strategy_id is required"}

    repo = Path(repo_path)
    if not repo.exists():
        return {"error": f"Path does not exist: {repo_path}"}

    # Get changed files via git diff
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True, text=True, cwd=str(repo),
            timeout=30,
        )
        if result.returncode != 0:
            return {"error": f"git diff failed: {result.stderr.strip()}"}
        changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.TimeoutExpired:
        return {"error": "git diff timed out"}
    except FileNotFoundError:
        return {"error": "git not found in PATH"}

    if not changed_files:
        return {
            "changed_files": [],
            "files_with_tests": [],
            "files_missing_tests": [],
            "pr_coverage_ratio": 1.0,
            "gap_map": {},
            "message": "No changed files detected.",
        }

    # Filter to source files only (exclude tests, configs, docs)
    try:
        strategy = registry.active()
    except Exception as e:
        return {"error": f"No strategy loaded: {e}"}

    lang = strategy.target_language
    source_extensions = {
        "python": {".py"},
        "kotlin": {".kt", ".kts"},
        "typescript": {".ts", ".tsx"},
    }.get(lang, {".py"})

    exclude_patterns = ["test", "spec", "fixture", "mock", "__pycache__", "build", ".gradle"]
    source_changed = [
        f for f in changed_files
        if Path(f).suffix in source_extensions
        and not any(p in f.lower() for p in exclude_patterns)
    ]

    # Run analysis if not already done
    if not session.scan_results:
        handle_analyse_repo(
            {"repo_path": repo_path, "strategy_id": strategy_id},
            session, registry,
        )

    scan = session.scan_results or {}
    gap_map = scan.get("gap_map", {})

    # Filter gap_map to changed files
    pr_gap_map: Dict[str, Dict] = {}
    files_with_tests: List[str] = []
    files_missing_tests: List[str] = []

    for changed_file in source_changed:
        # Find matching entry in gap_map
        matched = None
        for key in gap_map:
            if key.endswith(changed_file) or changed_file.endswith(key) or key == changed_file:
                matched = key
                break

        if matched:
            entry = gap_map[matched]
            pr_gap_map[changed_file] = entry
            if entry.get("existing_tests"):
                files_with_tests.append(changed_file)
            else:
                files_missing_tests.append(changed_file)
        else:
            files_missing_tests.append(changed_file)
            pr_gap_map[changed_file] = {
                "class_type": "unknown",
                "missing_lanes": ["unit"],
                "existing_tests": [],
                "note": "Not found in scan results — may need analyse_repo refresh",
            }

    total_source = len(source_changed)
    with_tests = len(files_with_tests)
    pr_coverage = with_tests / total_source if total_source > 0 else 1.0

    logger.info(
        f"Diff coverage: {with_tests}/{total_source} changed source files have tests "
        f"({pr_coverage:.0%})"
    )

    return {
        "changed_files": changed_files,
        "source_changed": source_changed,
        "files_with_tests": files_with_tests,
        "files_missing_tests": files_missing_tests,
        "pr_coverage_ratio": round(pr_coverage, 2),
        "gap_map": pr_gap_map,
    }
