"""AST walking utilities for Python source analysis.

Provides metrics extraction, assertion counting, test method discovery,
and common test-smell detection (bare asserts, skip markers).
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional


class ASTWalker:
    """Static analysis helpers built on the stdlib :mod:`ast` module."""

    # -- parsing ------------------------------------------------------------

    @staticmethod
    def parse_file(content: str) -> Optional[ast.Module]:
        """Parse *content* as Python source; return the AST or ``None`` on error."""
        try:
            return ast.parse(content, mode="exec")
        except SyntaxError:
            return None

    # -- metrics extraction -------------------------------------------------

    @staticmethod
    def extract_metrics(tree: ast.Module) -> Dict[str, Any]:
        """Return a metrics dict from an AST tree.

        Keys:
        - ``function_count``: number of top-level and nested function defs
        - ``class_count``: number of class defs
        - ``cyclomatic_complexity``: approximate McCabe complexity
        - ``has_side_effects``: heuristic — True if the module performs I/O
        - ``public_interface``: list of public function/method names
        - ``decorator_patterns``: list of unique decorator names found
        """
        function_count = 0
        class_count = 0
        complexity = 1  # base path
        has_side_effects = False
        public_interface: List[str] = []
        decorator_patterns: set[str] = set()

        _SIDE_EFFECT_NAMES = frozenset({
            "open", "print", "write", "read", "send", "connect",
            "execute", "commit", "request", "get", "post", "put", "delete",
            "subprocess", "system", "popen",
        })

        for node in ast.walk(tree):
            # --- functions ---
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1
                if not node.name.startswith("_"):
                    public_interface.append(node.name)
                for dec in node.decorator_list:
                    decorator_patterns.add(_decorator_name(dec))

            # --- classes ---
            elif isinstance(node, ast.ClassDef):
                class_count += 1
                if not node.name.startswith("_"):
                    public_interface.append(node.name)
                for dec in node.decorator_list:
                    decorator_patterns.add(_decorator_name(dec))

            # --- branching (cyclomatic complexity) ---
            elif isinstance(node, (ast.If, ast.IfExp)):
                complexity += 1
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # Each ``and`` / ``or`` adds a decision point.
                complexity += len(node.values) - 1

            # --- side-effect heuristic ---
            if isinstance(node, ast.Call):
                call_name = _call_name(node)
                if call_name and call_name in _SIDE_EFFECT_NAMES:
                    has_side_effects = True

        return {
            "function_count": function_count,
            "class_count": class_count,
            "cyclomatic_complexity": complexity,
            "has_side_effects": has_side_effects,
            "public_interface": public_interface,
            "decorator_patterns": sorted(decorator_patterns),
        }

    # -- assertion counting -------------------------------------------------

    @staticmethod
    def count_assertions(tree: ast.Module) -> int:
        """Count ``assert`` statements in the tree."""
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                count += 1
        return count

    # -- test method discovery ----------------------------------------------

    @staticmethod
    def find_test_methods(tree: ast.Module) -> List[str]:
        """Return names of functions / methods whose name starts with ``test``."""
        methods: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    methods.append(node.name)
        return methods

    # -- smell detectors ----------------------------------------------------

    @staticmethod
    def detect_bare_asserts(tree: ast.Module) -> List[int]:
        """Return line numbers of bare asserts like ``assert True`` or ``assert x is not None``.

        These are considered low-value assertions that rarely catch real bugs.
        """
        lines: List[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            test = node.test

            # assert True / assert False
            if isinstance(test, ast.Constant) and isinstance(test.value, bool):
                lines.append(node.lineno)
                continue

            # assert x is not None  /  assert x is None
            if isinstance(test, ast.Compare):
                if len(test.ops) == 1 and isinstance(test.ops[0], (ast.Is, ast.IsNot)):
                    for comparator in test.comparators:
                        if isinstance(comparator, ast.Constant) and comparator.value is None:
                            lines.append(node.lineno)
                            break

        return lines

    @staticmethod
    def detect_skip_markers(tree: ast.Module) -> List[str]:
        """Return names of test functions decorated with ``@pytest.mark.skip``
        or ``@unittest.skip``.
        """
        skipped: List[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test"):
                continue
            for dec in node.decorator_list:
                dec_name = _decorator_name(dec)
                if "skip" in dec_name.lower():
                    skipped.append(node.name)
                    break
        return skipped


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decorator_name(node: ast.expr) -> str:
    """Best-effort extraction of a decorator's dotted name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: List[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "<unknown>"


def _call_name(node: ast.Call) -> Optional[str]:
    """Extract the simple name of a call target, if available."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
