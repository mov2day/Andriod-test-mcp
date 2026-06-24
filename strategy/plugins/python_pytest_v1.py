# strategy/plugins/python_pytest_v1.py — V1 bundled Python/pytest strategy
import ast
import re
from typing import List, Dict, Optional, Any

from ..base import (
    BaseStrategy, TestLane, TestLaneType, NamingConvention,
    BehavioralSpec, SourceClassification,
)


class PythonPytestStrategy(BaseStrategy):
    """
    Bundled strategy for Python projects using pytest.
    Classifies source files using AST analysis, enforces Given/When/Then
    spec contracts, and validates generated tests against naming and
    coverage rules.
    """

    # ── Properties ──────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return "python_pytest_v1"

    @property
    def name(self) -> str:
        return "Python Pytest Strategy"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def target_language(self) -> str:
        return "python"

    @property
    def target_framework(self) -> Optional[str]:
        return "pytest"

    # ── Lanes ───────────────────────────────────────────────────────

    def get_test_lanes(self) -> List[TestLane]:
        return [
            TestLane(
                TestLaneType.UNIT, required=True,
                file_glob="tests/unit/**/test_*.py",
                coverage_threshold=0.80,
            ),
            TestLane(
                TestLaneType.INTEGRATION, required=True,
                file_glob="tests/integration/**/test_*.py",
                coverage_threshold=0.60,
            ),
            TestLane(
                TestLaneType.CONTRACT, required=False,
                file_glob="tests/contract/**/test_*.py",
                coverage_threshold=0.0,
            ),
        ]

    # ── Naming ──────────────────────────────────────────────────────

    def get_naming_conventions(self) -> NamingConvention:
        return NamingConvention(
            test_file_pattern=r"test_(?P<source>.+)\.py",
            test_method_pattern=r"test_(?P<action>.+)_when_(?P<condition>.+)_expects_(?P<expected>.+)",
        )

    # ── Spec Rules ────────────────────────────────────────────────

    def get_behavioral_specs(self) -> List[BehavioralSpec]:
        return [
            BehavioralSpec(
                "service",
                required_spec_fields=["given", "when", "then", "expected_state"],
                required_assertions_min=2,
            ),
            BehavioralSpec(
                "repository",
                required_spec_fields=["given_db_state", "when", "then_db_state"],
                required_assertions_min=1,
            ),
            BehavioralSpec(
                "utility",
                required_spec_fields=["input", "expected_output"],
                required_assertions_min=1,
            ),
            BehavioralSpec(
                "controller",
                required_spec_fields=["given", "when_request", "then_status", "then_body"],
                required_assertions_min=2,
            ),
            BehavioralSpec(
                "dto",
                required_spec_fields=["input", "expected_output"],
                required_assertions_min=1,
            ),
        ]

    # ── Classification ──────────────────────────────────────────────

    def classify_source_file(
        self, file_path: str, content: str
    ) -> SourceClassification:
        """Pure AST-based classification — no I/O."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return SourceClassification(
                class_type="unknown",
                complexity_score=1,
                testability_issues=["syntax_error"],
                required_lanes=[TestLaneType.UNIT],
                ast_metrics={},
            )

        metrics = self._extract_metrics(tree)
        class_type = self._infer_class_type(file_path, tree)
        testability_issues = self._find_testability_issues(tree)
        required_lanes = self._lanes_for_type(class_type)

        return SourceClassification(
            class_type=class_type,
            complexity_score=min(10, max(1, metrics.get("cyclomatic_complexity", 1))),
            testability_issues=testability_issues,
            required_lanes=required_lanes,
            ast_metrics=metrics,
        )

    # ── Generation Brief ────────────────────────────────────────────

    def build_generation_brief(
        self,
        classification: SourceClassification,
        user_context: str,
        file_path: str,
        test_plan: List[Dict],
    ) -> str:
        behavioral_spec = self._get_oracle_for_type(classification.class_type)
        naming = self.get_naming_conventions()
        lanes = self.get_test_lanes()

        brief_parts = [
            "# Test Generation Brief",
            f"**Strategy:** {self.name} v{self.version}",
            f"**Source File:** {file_path}",
            f"**Class Type:** {classification.class_type}",
            f"**Complexity:** {classification.complexity_score}/10",
            "",
            "## Naming Convention",
            f"- File pattern: `{naming.test_file_pattern}`",
            f"- Method pattern: `{naming.test_method_pattern}`",
            "",
            "## Behavioral Contract",
        ]

        if behavioral_spec:
            brief_parts.append(f"Each test for a `{classification.class_type}` must include:")
            for field_name in behavioral_spec.required_spec_fields:
                brief_parts.append(f"  - **{field_name}**: (required in docstring)")
            brief_parts.append(
                f"- Minimum assertions per test: {behavioral_spec.required_assertions_min}"
            )
        brief_parts.append("")

        brief_parts.append("## Required Lanes")
        for lane in lanes:
            marker = "✓ REQUIRED" if lane.required else "○ optional"
            brief_parts.append(
                f"- {lane.lane_type.value}: {marker} "
                f"(threshold: {lane.coverage_threshold:.0%})"
            )
        brief_parts.append("")

        brief_parts.append("## Behavioral Context (user_context)")
        brief_parts.append(user_context if user_context else "_No context provided._")
        brief_parts.append("")

        brief_parts.append("## Test Plan")
        for tc in test_plan:
            tc_data = tc if isinstance(tc, dict) else tc.model_dump() if hasattr(tc, "model_dump") else {}
            brief_parts.append(f"### {tc_data.get('id', '?')} — {tc_data.get('name', '?')}")
            brief_parts.append(f"- Lane: {tc_data.get('lane', '?')}")
            brief_parts.append(f"- GIVEN: {tc_data.get('given', '?')}")
            brief_parts.append(f"- WHEN: {tc_data.get('when', '?')}")
            brief_parts.append(f"- THEN: {tc_data.get('then', '?')}")
            brief_parts.append("")

        if classification.testability_issues:
            brief_parts.append("## Testability Issues")
            for issue in classification.testability_issues:
                brief_parts.append(f"- ⚠ {issue}")

        brief_parts.append("")
        brief_parts.append("## Allure Reporting Annotations (MANDATORY)")
        brief_parts.append("Every generated test class and method MUST include Allure annotations:")
        brief_parts.append("- **Class level:** `@allure.epic('<feature area>')` and `@allure.feature('<module>')`")
        brief_parts.append("- **Method level:** `@allure.story('<user story>')` and `@allure.severity(allure.severity_level.NORMAL)`")
        brief_parts.append("- **Inside test body:** Use `with allure.step('<step description>'):` blocks for major actions.")
        brief_parts.append("- Import `import allure` at top of test file.")
        brief_parts.append("- Severity mapping: service/controller critical paths → CRITICAL, utility/dto → NORMAL, integration → CRITICAL.")

        return "\n".join(brief_parts)

    # ── Validation ──────────────────────────────────────────────────

    def validate_generated_test(
        self,
        test_content: str,
        source_classification: SourceClassification,
    ) -> Dict:
        violations: List[Dict] = []
        lanes_covered: List[str] = []

        # Parse the test file
        try:
            tree = ast.parse(test_content)
        except SyntaxError as e:
            return {
                "valid": False,
                "violations": [{"rule": "syntax", "severity": "error", "line": e.lineno or 0, "detail": str(e)}],
                "spec_completeness": 0.0,
                "lanes_covered": [],
                "missing_lanes": [lt.value for lt in source_classification.required_lanes],
            }

        # Find test functions
        test_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]

        if not test_funcs:
            violations.append({
                "rule": "no_test_functions",
                "severity": "error",
                "line": 0,
                "detail": "No test functions found in file",
            })

        # Check naming convention
        naming = self.get_naming_conventions()
        method_re = re.compile(naming.test_method_pattern)
        for func in test_funcs:
            if not method_re.match(func.name):
                violations.append({
                    "rule": "naming_convention.method_pattern",
                    "severity": "warning",
                    "line": func.lineno,
                    "detail": f"{func.name} does not match pattern {naming.test_method_pattern}",
                })

        # Check spec completeness via docstrings
        behavioral_spec = self._get_oracle_for_type(source_classification.class_type)
        spec_hits = 0
        spec_total = 0
        if behavioral_spec:
            for func in test_funcs:
                docstring = ast.get_docstring(func) or ""
                spec_total += len(behavioral_spec.required_spec_fields)
                for req_field in behavioral_spec.required_spec_fields:
                    if req_field.lower() in docstring.lower():
                        spec_hits += 1
                    else:
                        violations.append({
                            "rule": "spec_completeness",
                            "severity": "error",
                            "line": func.lineno,
                            "detail": f"{func.name}: missing spec field '{req_field}' for class_type '{source_classification.class_type}'",
                        })

        spec_completeness = spec_hits / spec_total if spec_total > 0 else 0.0

        # Check assertion counts
        if behavioral_spec:
            for func in test_funcs:
                assert_count = sum(
                    1 for node in ast.walk(func)
                    if isinstance(node, ast.Assert)
                    or (isinstance(node, ast.Call) and _is_assert_call(node))
                )
                if assert_count < behavioral_spec.required_assertions_min:
                    violations.append({
                        "rule": "assertion_count",
                        "severity": "error",
                        "line": func.lineno,
                        "detail": f"{func.name}: {assert_count} assertions, minimum {behavioral_spec.required_assertions_min}",
                    })

        # Detect bare asserts
        for func in test_funcs:
            for node in ast.walk(func):
                if isinstance(node, ast.Assert):
                    if isinstance(node.test, ast.Constant) and node.test.value is True:
                        violations.append({
                            "rule": "no_bare_asserts",
                            "severity": "warning",
                            "line": node.lineno,
                            "detail": "Bare 'assert True' is a vacuous spec",
                        })

        # Detect skip markers
        skip_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("skip", "skipIf", "skipUnless"):
                skip_count += 1
        max_skips = self.get_test_lanes()[0].max_allowed_skips
        if skip_count > max_skips:
            violations.append({
                "rule": "no_skipped_tests",
                "severity": "error",
                "line": 0,
                "detail": f"{skip_count} skipped tests exceed max_allowed_skips={max_skips}",
            })

        # Determine lane coverage (heuristic based on file path hints in content)
        content_lower = test_content.lower()
        if "unit" in content_lower or "unittest" in content_lower:
            lanes_covered.append("unit")
        if "integration" in content_lower or "fixture" in content_lower:
            lanes_covered.append("integration")
        if not lanes_covered and test_funcs:
            lanes_covered.append("unit")  # default

        missing = [
            lt.value for lt in source_classification.required_lanes
            if lt.value not in lanes_covered
        ]

        # --- Allure annotation validation ---
        has_allure_import = "import allure" in test_content
        if not has_allure_import:
            violations.append({
                "rule": "allure_missing_import",
                "severity": "warning",
                "line": 0,
                "detail": "Missing 'import allure'. Add Allure import for reporting annotations.",
            })

        has_epic = bool(re.search(r'@allure\.epic\s*\(', test_content))
        has_feature = bool(re.search(r'@allure\.feature\s*\(', test_content))
        if not has_epic:
            violations.append({
                "rule": "allure_missing_epic",
                "severity": "warning",
                "line": 0,
                "detail": "Missing @allure.epic() decorator on test class. Required for Allure reporting.",
            })
        if not has_feature:
            violations.append({
                "rule": "allure_missing_feature",
                "severity": "warning",
                "line": 0,
                "detail": "Missing @allure.feature() decorator on test class. Required for Allure reporting.",
            })

        # Check per-function @allure.story
        for func in test_funcs:
            func_has_story = False
            for decorator in func.decorator_list:
                if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Attribute)
                    and getattr(decorator.func.value, 'attr', '') == 'allure'
                    or (isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == 'story')):
                    func_has_story = True
                    break
                # Also check ast.Attribute form: allure.story(...)
                dec_src = ast.dump(decorator)
                if 'story' in dec_src:
                    func_has_story = True
                    break
            if not func_has_story:
                violations.append({
                    "rule": "allure_missing_story",
                    "severity": "warning",
                    "line": func.lineno,
                    "detail": f"{func.name}: missing @allure.story() decorator. Required for Allure traceability.",
                })

        has_errors = any(v["severity"] == "error" for v in violations)

        return {
            "valid": not has_errors,
            "violations": violations,
            "spec_completeness": round(spec_completeness, 2),
            "lanes_covered": lanes_covered,
            "missing_lanes": missing,
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _extract_metrics(self, tree: ast.AST) -> Dict[str, Any]:
        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        complexity = sum(
            1 for n in ast.walk(tree)
            if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler))
        )
        public_interface = [
            f.name for f in functions
            if not f.name.startswith("_")
        ]
        decorators = []
        for f in functions:
            for d in f.decorator_list:
                if isinstance(d, ast.Name):
                    decorators.append(d.id)
                elif isinstance(d, ast.Attribute):
                    decorators.append(d.attr)

        has_side_effects = any(
            isinstance(n, ast.Call) and _is_side_effect_call(n)
            for n in ast.walk(tree)
        )

        return {
            "function_count": len(functions),
            "class_count": len(classes),
            "cyclomatic_complexity": complexity,
            "has_side_effects": has_side_effects,
            "public_interface": public_interface,
            "decorator_patterns": list(set(decorators)),
        }

    def _infer_class_type(self, file_path: str, tree: ast.AST) -> str:
        path_lower = file_path.lower()
        if "service" in path_lower:
            return "service"
        if "repository" in path_lower or "repo" in path_lower:
            return "repository"
        if "controller" in path_lower or "route" in path_lower or "view" in path_lower:
            return "controller"
        if "dto" in path_lower or "schema" in path_lower or "model" in path_lower:
            return "dto"
        if "util" in path_lower or "helper" in path_lower:
            return "utility"
        if "config" in path_lower or "settings" in path_lower:
            return "config"
        # Fallback: if it has classes with methods → service, else utility
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        if classes:
            return "service"
        return "utility"

    def _find_testability_issues(self, tree: ast.AST) -> List[str]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "database" in node.module or "db" in node.module:
                    issues.append("hidden_dependency: database")
                if "requests" == node.module or "httpx" == node.module:
                    issues.append("hidden_dependency: http_client")
            if isinstance(node, ast.Global):
                issues.append("global_state_mutation")
        return issues

    def _lanes_for_type(self, class_type: str) -> List[TestLaneType]:
        mapping = {
            "service": [TestLaneType.UNIT, TestLaneType.INTEGRATION],
            "repository": [TestLaneType.UNIT, TestLaneType.INTEGRATION],
            "controller": [TestLaneType.UNIT, TestLaneType.INTEGRATION],
            "utility": [TestLaneType.UNIT],
            "dto": [TestLaneType.UNIT],
            "config": [TestLaneType.UNIT],
            "unknown": [TestLaneType.UNIT],
        }
        return mapping.get(class_type, [TestLaneType.UNIT])

    def _get_oracle_for_type(self, class_type: str) -> Optional[BehavioralSpec]:
        for rule in self.get_behavioral_specs():
            if rule.source_class_type == class_type:
                return rule
        return None


# ── Module-level helpers ────────────────────────────────────────────

def _is_assert_call(node: ast.Call) -> bool:
    """Check if a Call node is an assertion (e.g., assertEqual, assertRaises)."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr.startswith("assert")
    if isinstance(node.func, ast.Name):
        return node.func.id.startswith("assert")
    return False


def _is_side_effect_call(node: ast.Call) -> bool:
    """Heuristic: detect common side-effect-producing calls."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in ("write", "send", "post", "put", "delete", "execute", "commit")
    if isinstance(node.func, ast.Name):
        return node.func.id in ("open", "print", "exec", "eval")
    return False
