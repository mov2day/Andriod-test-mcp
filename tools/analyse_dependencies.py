# tools/analyse_dependencies.py — V2: Import graph and coupling score
import ast
from typing import Dict, Any, List
from pathlib import Path

from core.session import Session
from strategy.registry import StrategyRegistry
from core.logger import get_logger

logger = get_logger("tools.analyse_dependencies")


def handle_analyse_dependencies(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Compute import graph and coupling scores for Python modules.
    For non-Python repos, returns instructions for the AI to perform
    dependency analysis manually.
    """
    repo_path = arguments.get("repo_path", "")
    if not repo_path:
        return {"error": "repo_path is required"}

    repo = Path(repo_path)
    if not repo.exists():
        return {"error": f"Path does not exist: {repo_path}"}

    try:
        strategy = registry.active()
    except Exception:
        strategy = None

    lang = strategy.target_language if strategy else "python"

    if lang != "python":
        return {
            "message": "Automated dependency analysis is only available for Python repos.",
            "ai_instruction": (
                "Please perform dependency analysis manually for this repo:\n"
                "1. Read each source file and identify its imports\n"
                "2. Build an adjacency map: {module: [imported_modules]}\n"
                "3. Compute coupling_score per module = unique imports + importers\n"
                "4. Return the result in this JSON format:\n"
                '{"dependency_graph": {...}, "coupling_scores": {...}, "highly_coupled": [...]}'
            ),
        }

    # Python: walk all .py files, extract imports
    dependency_graph: Dict[str, List[str]] = {}
    all_modules: set = set()

    for py_file in repo.rglob("*.py"):
        rel = str(py_file.relative_to(repo))
        # Skip test files, venv, build dirs
        if any(skip in rel for skip in ["test_", "tests/", "__pycache__", "venv", ".venv", "build"]):
            continue

        module_name = rel.replace("/", ".").replace(".py", "")
        all_modules.add(module_name)

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            continue

        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        dependency_graph[module_name] = imports

    # Compute coupling scores
    # coupling = unique outgoing imports + unique incoming imports (modules that import this one)
    incoming: Dict[str, int] = {m: 0 for m in all_modules}
    for module, deps in dependency_graph.items():
        for dep in deps:
            if dep in incoming:
                incoming[dep] += 1

    coupling_scores: Dict[str, Dict] = {}
    for module in all_modules:
        outgoing = len(set(dependency_graph.get(module, [])))
        inc = incoming.get(module, 0)
        coupling_scores[module] = {
            "outgoing_imports": outgoing,
            "incoming_imports": inc,
            "coupling_score": outgoing + inc,
        }

    # Identify highly coupled modules (coupling > 10)
    threshold = 10
    highly_coupled = [
        {"module": m, **scores}
        for m, scores in coupling_scores.items()
        if scores["coupling_score"] > threshold
    ]
    highly_coupled.sort(key=lambda x: x["coupling_score"], reverse=True)

    logger.info(f"Dependency analysis: {len(all_modules)} modules, {len(highly_coupled)} highly coupled")

    return {
        "dependency_graph": dependency_graph,
        "coupling_scores": coupling_scores,
        "highly_coupled": highly_coupled,
        "total_modules": len(all_modules),
    }
