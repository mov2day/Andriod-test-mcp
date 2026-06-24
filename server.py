# server.py — QE-MCP server entrypoint (stdio transport)
"""
QE-MCP: A Python-based Model Context Protocol server that enforces
configurable QA automation strategies — enabling AI agents to analyse
repositories, generate prescriptive test plans, validate test output,
and enforce quality gates through a plug-and-play strategy plugin
architecture.
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.logger import get_logger
from core.session import Session
from strategy.registry import StrategyRegistry, StrategyLoadError

# Tool handlers
from tools.list_strategies import handle_list_strategies
from tools.load_strategy import handle_load_strategy
from tools.analyse_repo import handle_analyse_repo
from tools.generate_test_plan import handle_generate_test_plan
from tools.get_generation_brief import handle_get_generation_brief
from tools.validate_tests import handle_validate_tests
from tools.enforce import handle_enforce
from tools.get_report import handle_get_report
from tools.analyse_dependencies import handle_analyse_dependencies
from tools.diff_coverage import handle_diff_coverage
from tools.export_report import handle_export_report
from tools.watch_repo import handle_watch_repo

logger = get_logger("qe_mcp.server")

# ── Singletons ──────────────────────────────────────────────────────
mcp = FastMCP("qe-mcp")
session = Session()
registry = StrategyRegistry()


# ── V1 Tools (8) ────────────────────────────────────────────────────

@mcp.tool()
def list_strategies() -> dict:
    """List all registered strategy IDs and metadata from the manifest."""
    try:
        return handle_list_strategies({}, session, registry)
    except Exception as e:
        logger.error(f"list_strategies failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def load_strategy(strategy_id: str) -> dict:
    """Validate contract and activate a strategy plugin. Raises StrategyLoadError on failure."""
    try:
        return handle_load_strategy({"strategy_id": strategy_id}, session, registry)
    except Exception as e:
        logger.error(f"load_strategy failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def analyse_repo(repo_path: str, strategy_id: str) -> dict:
    """
    Discover source files, run classification via strategy plugin,
    produce gap map vs declared lanes, and generate an analysis prompt
    instructing the invoking AI to perform deep semantic analysis of
    each file. Returns files_analysed, gap_map, coverage_by_lane, smells,
    and an analysis_prompt with the exact JSON output format the AI must use.
    """
    try:
        return handle_analyse_repo(
            {"repo_path": repo_path, "strategy_id": strategy_id},
            session, registry,
        )
    except Exception as e:
        logger.error(f"analyse_repo failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def generate_test_plan(file_path: str, strategy_id: str, user_context: str) -> dict:
    """
    Produce TC-001..N prescriptive test plan with Given/When/Then behavioral specs
    per class type. user_context is required — tests derived from
    implementation alone will assert the wrong expected state.
    """
    try:
        return handle_generate_test_plan(
            {"file_path": file_path, "strategy_id": strategy_id, "user_context": user_context},
            session, registry,
        )
    except Exception as e:
        logger.error(f"generate_test_plan failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def get_generation_brief(plan_id: str, file_path: str) -> dict:
    """
    Assemble full agent prompt brief via strategy's build_generation_brief().
    MCP never calls LLMs. Returns a structured brief for the agent to act on.
    """
    try:
        return handle_get_generation_brief(
            {"plan_id": plan_id, "file_path": file_path},
            session, registry,
        )
    except Exception as e:
        logger.error(f"get_generation_brief failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def validate_tests(test_file: str, strategy_id: str) -> dict:
    """
    Check generated tests against naming conventions, spec completeness,
    required lane coverage. Runs 7-layer validation (MCP Core + Strategy).
    """
    try:
        return handle_validate_tests(
            {"test_file": test_file, "strategy_id": strategy_id},
            session, registry,
        )
    except Exception as e:
        logger.error(f"validate_tests failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def enforce(repo_path: str, strategy_id: str) -> dict:
    """
    Full sweep: analyse + validate + compare to thresholds.
    Designed to be treated as a hard gate — passed:false is a blocker.
    Returns {passed, blockers, warnings, summary}.
    """
    try:
        return handle_enforce(
            {"repo_path": repo_path, "strategy_id": strategy_id},
            session, registry,
        )
    except Exception as e:
        logger.error(f"enforce failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def get_report(format: str = "json") -> dict:
    """
    Build full session report from in-memory state: all gaps, violations,
    enforce results, coverage by lane. Supports 'json' and 'markdown' formats.
    """
    try:
        return handle_get_report({"format": format}, session, registry)
    except Exception as e:
        logger.error(f"get_report failed: {e}")
        return {"error": str(e)}


# ── V2 Tools (4) ────────────────────────────────────────────────────

@mcp.tool()
def analyse_dependencies(repo_path: str) -> dict:
    """
    Compute import graph and coupling scores for the repository (V2).
    For Python repos: automated AST-based analysis.
    For non-Python: returns instructions for the AI to perform analysis.
    """
    try:
        return handle_analyse_dependencies(
            {"repo_path": repo_path},
            session, registry,
        )
    except Exception as e:
        logger.error(f"analyse_dependencies failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def diff_coverage(repo_path: str, strategy_id: str, base_ref: str = "main") -> dict:
    """
    PR-scoped gap analysis via git diff (V2). Only analyses files changed
    in the current branch vs base_ref. Returns changed_files, coverage ratio,
    and a filtered gap_map for the PR scope.
    """
    try:
        return handle_diff_coverage(
            {"repo_path": repo_path, "strategy_id": strategy_id, "base_ref": base_ref},
            session, registry,
        )
    except Exception as e:
        logger.error(f"diff_coverage failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def export_report(format: str, output_path: str) -> dict:
    """
    Write the session report to disk in JSON, Markdown, or HTML format (V2).
    """
    try:
        return handle_export_report(
            {"format": format, "output_path": output_path},
            session, registry,
        )
    except Exception as e:
        logger.error(f"export_report failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def watch_repo(repo_path: str, strategy_id: str = "", action: str = "start") -> dict:
    """
    Start or stop file-change monitoring for the repository (V2).
    When active, source file changes mark the session as stale.
    Re-run analyse_repo to refresh. Requires watchdog: pip install qe-mcp[v2]
    """
    try:
        return handle_watch_repo(
            {"repo_path": repo_path, "strategy_id": strategy_id, "action": action},
            session, registry,
        )
    except Exception as e:
        logger.error(f"watch_repo failed: {e}")
        return {"error": str(e)}


# ── Entry Point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting QE-MCP server (stdio)")
    mcp.run()
