# strategy/plugins/android_compose_v1.py — Android Compose test strategy from teststrategy.md v6.0
import re
from typing import List, Dict, Optional, Any

from ..base import (
    BaseStrategy, TestLane, TestLaneType, NamingConvention,
    OracleRule, SourceClassification,
)


class AndroidComposeStrategy(BaseStrategy):
    """
    Strategy for Android applications built with Jetpack Compose.
    Implements the four-lane test model, ARIA generation rules, flakiness
    management, and CI/CD quality gates from teststrategy.md v6.0.

    Classification uses regex/string heuristics on Kotlin source files
    since Python's ast module does not parse Kotlin.
    """

    # ── Properties ──────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return "android_compose_v1"

    @property
    def name(self) -> str:
        return "Android Compose Test Strategy"

    @property
    def version(self) -> str:
        return "6.0.0"

    @property
    def target_language(self) -> str:
        return "kotlin"

    @property
    def target_framework(self) -> Optional[str]:
        return "compose"

    # ── Lanes (Four-Lane Model) ─────────────────────────────────────

    def get_test_lanes(self) -> List[TestLane]:
        return [
            TestLane(
                TestLaneType.UNIT, required=True,
                file_glob="app/src/test/java/**/*Test.kt",
                coverage_threshold=0.90,
                max_allowed_skips=0,
            ),
            TestLane(
                TestLaneType.INTEGRATION, required=True,
                file_glob="app/src/test/java/**/*ScreenTest.kt",
                coverage_threshold=0.0,  # measured by state coverage, not lines
                max_allowed_skips=0,
            ),
            TestLane(
                TestLaneType.CONTRACT, required=False,
                file_glob="app/src/androidTest/java/**/*Test.kt",
                coverage_threshold=0.0,
            ),
            TestLane(
                TestLaneType.E2E, required=False,
                file_glob="app/src/androidTest/java/**/*JourneyTest.kt",
                coverage_threshold=0.0,
            ),
            TestLane(
                TestLaneType.PERFORMANCE, required=False,
                file_glob="macrobenchmark/src/androidTest/java/**/*Benchmark.kt",
                coverage_threshold=0.0,
            ),
        ]

    # ── Naming Convention ───────────────────────────────────────────

    def get_naming_conventions(self) -> NamingConvention:
        return NamingConvention(
            test_file_pattern=r"(?P<source>.+)Test\.kt",
            test_method_pattern=r"`(?P<description>.+)`",
        )

    # ── Oracle Rules ────────────────────────────────────────────────

    def get_oracle_rules(self) -> List[OracleRule]:
        return [
            OracleRule(
                "viewmodel",
                required_oracle_fields=["given", "when", "then", "expected_state"],
                required_assertions_min=2,
                mutation_sensitive=True,
            ),
            OracleRule(
                "composable_screen",
                required_oracle_fields=["given_state", "when_rendered", "then_visible", "then_not_visible"],
                required_assertions_min=2,
            ),
            OracleRule(
                "composable_component",
                required_oracle_fields=["given_props", "when_rendered", "then_visible"],
                required_assertions_min=1,
            ),
            OracleRule(
                "navigation",
                required_oracle_fields=["given_route", "when_action", "then_destination"],
                required_assertions_min=1,
            ),
            OracleRule(
                "dto_mapper",
                required_oracle_fields=["input", "expected_output"],
                required_assertions_min=1,
            ),
            OracleRule(
                "use_case",
                required_oracle_fields=["given", "when", "then", "expected_state"],
                required_assertions_min=2,
                mutation_sensitive=True,
            ),
            OracleRule(
                "reducer",
                required_oracle_fields=["given", "when", "then", "expected_state"],
                required_assertions_min=2,
                mutation_sensitive=True,
            ),
            OracleRule(
                "validator",
                required_oracle_fields=["input", "expected_output"],
                required_assertions_min=1,
            ),
        ]

    # ── Classification (Regex/Heuristic for Kotlin) ─────────────────

    def classify_source_file(
        self, file_path: str, content: str
    ) -> SourceClassification:
        """
        Uses regex/string heuristics to classify Kotlin source files.
        Detects @Composable, ViewModel, data class mappers, NavHost, etc.
        """
        testability_issues: List[str] = []
        lines = content.split("\n")
        line_count = len(lines)

        # Count branching for complexity
        branch_count = sum(
            1 for line in lines
            if re.search(r'\b(if|when|for|while|catch|else)\b', line)
        )
        complexity = min(10, max(1, branch_count // 3 + 1))

        # Detect class type
        class_type = self._detect_class_type(file_path, content)

        # Detect testability smells
        testability_issues.extend(self._detect_smells(file_path, content, class_type))

        # Determine required lanes
        required_lanes = self._lanes_for_type(class_type)

        # Extract basic metrics
        function_count = len(re.findall(r'\bfun\s+\w+', content))
        class_count = len(re.findall(r'\bclass\s+\w+', content))
        composable_count = len(re.findall(r'@Composable', content))

        public_interface = re.findall(r'(?:^|\s)fun\s+(\w+)', content)
        public_interface = [f for f in public_interface if not f.startswith("_")]

        return SourceClassification(
            class_type=class_type,
            complexity_score=complexity,
            testability_issues=testability_issues,
            required_lanes=required_lanes,
            ast_metrics={
                "function_count": function_count,
                "class_count": class_count,
                "composable_count": composable_count,
                "line_count": line_count,
                "branch_count": branch_count,
                "public_interface": public_interface,
            },
        )

    # ── Generation Brief ────────────────────────────────────────────

    def build_generation_brief(
        self,
        classification: SourceClassification,
        user_context: str,
        file_path: str,
        test_plan: List[Dict],
    ) -> str:
        oracle_rule = self._get_oracle_for_type(classification.class_type)

        brief = f"""# Android Compose Test Generation Brief
**Strategy:** {self.name} v{self.version}
**Source File:** {file_path}
**Class Type:** {classification.class_type}
**Complexity:** {classification.complexity_score}/10

---

## Four-Lane Test Model

| Lane | Scope | Runner | Env | Gate |
|------|-------|--------|-----|------|
| Lane 1 | Logic & State (ViewModel, use case, reducer, DTO) | JUnit 5 | JVM | Hard PR gate |
| Lane 2 | Compose Screen/Component (state-hoisted) | JUnit 4 | JVM (Robolectric) | Hard PR gate |
| Lane 3 | Device Interaction (NavHost, IME, permissions) | JUnit 4 | Emulator/Device | Selective PR gate |
| Lane 4 | Release Confidence (Journeys + Macrobenchmark) | JUnit 4 | Real device | Release gate |

## Lane Selection Decision Tree

```
Does the target have no Android runtime import?
AND does it operate on Kotlin types, StateFlow, or sealed classes?
  → Lane 1

Does the target @Composable accept state and callbacks directly (state-hoisted)?
AND can all states be driven without a real device?
  → Lane 2

Does the manifest declare a deviceRisk field with at least one true entry?
OR does the target require NavHost, back press, IME, permission, or real lifecycle?
  → Lane 3

Does the target span two or more screens, measure startup/frame/scroll timing,
or validate a critical journey under release-build conditions?
  → Lane 4
```

## Lane-Specific Instructions

### Lane 1 — Logic & State
- **No Hilt.** Construct all classes via direct constructor injection with fakes.
- Use `UnconfinedTestDispatcher()` and inject via constructor.
- `Dispatchers.setMain(testDispatcher)` in `@BeforeEach`, `Dispatchers.resetMain()` in `@AfterEach`.
- Use Turbine `.test {{ }}` for `StateFlow` assertions.
- **Sealed state coverage rule:** Every sealed subclass of a ViewModel's UiState must have at least one test.
- `CancellationException` must NOT be emitted as `UiState.Error`.
- `SavedStateHandle` — construct directly: `SavedStateHandle(mapOf(...))`. Always test the missing-argument path.
- Use `@ParameterizedTest` with `@MethodSource` or `@CsvSource` for DTO mapping and reducer state machines.
- Do NOT use companion object singletons or `object` declarations in fakes.

### Lane 2 — Compose Screen/Component
- Use `@RunWith(RobolectricTestRunner::class)` and `@Config(sdk = [33])`.
- Use `createComposeRule()` (NOT `createAndroidComposeRule`).
- Test state-hoisted Screen composables, NOT Route composables.
- **Theme:** Detect the project's custom `AppTheme` composable and use it in all `setContent {{}}` calls. Fall back to `MaterialTheme` only if no custom theme exists.
- **Infinite animations:** If the composable uses `rememberInfiniteTransition`, `CircularProgressIndicator`, or `InfiniteRepeatableSpec`:
  - Set `composeTestRule.mainClock.autoAdvance = false` BEFORE `setContent`
  - Use `mainClock.advanceTimeBy(ms)` instead of `waitForIdle()`
  - Do NOT call `waitForIdle()` while infinite animations are active.
- `assertIsDisplayed()` verifies semantic inclusion only — not pixel-bound visibility.
- IME and window inset assertions belong in Lane 3, NOT Lane 2.
- Use `StateRestorationTester` for `rememberSaveable` tests.
- **Paparazzi snapshots:** Generate for all `configurationVariants` × `localeVariants` declared in the manifest:
  - darkMode, fontScale200, rtl, each locale
  - Use `paparazzi.unsafeUpdateConfig(...)` for variants
  - RTL requires `CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl)`

### Lane 3 — Device Interaction
- Use `createAndroidComposeRule<ComponentActivity>()` (NOT `<MainActivity>`).
- **Hilt ordering:** `@get:Rule(order = 0) hiltRule`, `@get:Rule(order = 1) composeTestRule`.
- Call `hiltRule.inject()` in `@Before`; call `setContent {{}}` in the test body AFTER injection.
- `enableAccessibilityChecks()` + `onRoot().tryPerformAccessibilityChecks()`.
- **MockWebServer** for network interception via `@TestInstallIn`. No airplane mode toggling.
- **waitUntil timeout tiers:** 1000ms (UI transition), 3000ms (network/data), 5000ms (animation/debounce). > 5000ms is a SLOW_WAITUNTIL smell.
- **Meaningful image assertions:** Use expected text from manifest `accessibilityProfile.meaningfulImages`.
- `waitForIdle()` after every state-triggering action.

### Lane 4 — Release Confidence
- **Journey tests:** Multi-screen flows using full app composition.
- **Macrobenchmark:** Separate `:macrobenchmark` module, `MacrobenchmarkRule()`, `StartupTimingMetric()` + `FrameTimingMetric()`.
- `testTagsAsResourceId = true` on root ancestor for `By.res()` to resolve Compose test tags.

## Flakiness Rules (ALL LANES)
- **PROHIBITED:** `Thread.sleep()`, `kotlinx.coroutines.delay()` in test bodies.
- `waitForIdle()` after every state-triggering action (except infinite animations).
- One `setContent` call per test method.
- `animationsDisabled = true` in `testOptions`.

## Oracle Contract
Each test MUST include this KDoc comment:
```kotlin
/**
 * GIVEN:  <precondition>
 * WHEN:   <action>
 * THEN:   <positive assertion>
 * AND:    <negative assertion>
 * SOURCE: <source of truth state>
 * LOCALE: <locale or "default">
 * CONFIG: <config variant or "default">
 */
```
A test with only a positive assertion and no negative assertion is a **partial oracle** and is REJECTED.

## Oracle Fingerprint Format
```
{{screen}}|{{uiState}}|{{action}}|{{positiveAssertion}}|{{negativeAssertion}}|{{sourceOfTruth}}|{{locale}}|{{configVariant}}
```

## Mutation Verification — Tier 1 (Mandatory at PR)
Generated test must fail at least one of:
1. Replace composable content with `Box {{}}`
2. Remove click callback
3. Remove success content branch

## Selector Policy
Priority: `testTag` → `contentDescription` → visible text
Tag naming: `{{screen_name}}_{{element_role}}` in snake_case

## Test Placement
```
Lane 1:          app/src/test/java
Lane 2:          app/src/test/java
Lane 3:          app/src/androidTest/java
Lane 4 Journey:  app/src/androidTest/java
Lane 4 Perf:     macrobenchmark/src/androidTest/java
Shared utils:    app/src/testFixtures/java
```

"""

        if oracle_rule:
            brief += f"\n## Oracle Fields for `{classification.class_type}`\n"
            for field_name in oracle_rule.required_oracle_fields:
                brief += f"- **{field_name}** (required)\n"
            brief += f"- Minimum assertions: {oracle_rule.required_assertions_min}\n"

        brief += "\n## Behavioral Context (user_context)\n"
        brief += user_context if user_context else "_No context provided._"
        brief += "\n"

        brief += "\n## Test Plan\n"
        for tc in test_plan:
            tc_data = tc if isinstance(tc, dict) else tc.model_dump() if hasattr(tc, "model_dump") else {}
            brief += f"\n### {tc_data.get('id', '?')} — {tc_data.get('name', '?')}\n"
            brief += f"- Lane: {tc_data.get('lane', '?')}\n"
            brief += f"- GIVEN: {tc_data.get('given', '?')}\n"
            brief += f"- WHEN: {tc_data.get('when', '?')}\n"
            brief += f"- THEN: {tc_data.get('then', '?')}\n"

        if classification.testability_issues:
            brief += "\n## Testability Smells Detected\n"
            for issue in classification.testability_issues:
                brief += f"- ⚠ {issue}\n"

        brief += "\n## Generated Test Review Checklist\n"
        brief += """- [ ] Oracle is complete (GIVEN/WHEN/THEN/AND/SOURCE/LOCALE/CONFIG)
- [ ] Selector strategy matches policy (testTag for automation, semantic for accessibility)
- [ ] No Thread.sleep() or delay() in test body
- [ ] waitForIdle() present after every state-triggering action
- [ ] waitUntil timeout uses standard tier value
- [ ] Project theme composable used in every setContent {} block
- [ ] Mutation gate Tier 1 evidence confirmed
- [ ] Test assigned to correct lane and placed in correct source set
- [ ] No duplicate oracle fingerprint
"""

        return brief

    # ── Validation ──────────────────────────────────────────────────

    def validate_generated_test(
        self,
        test_content: str,
        source_classification: SourceClassification,
    ) -> Dict:
        violations: List[Dict] = []
        lanes_covered: List[str] = []
        lines = test_content.split("\n")

        # --- Prohibited patterns ---
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Thread.sleep() / delay()
            if re.search(r'\bThread\.sleep\s*\(', line):
                violations.append({
                    "rule": "no_thread_sleep",
                    "severity": "error",
                    "line": i,
                    "detail": "Thread.sleep() is prohibited in test bodies",
                })
            if re.search(r'\bdelay\s*\(', line) and "IdlingResource" not in line:
                violations.append({
                    "rule": "no_delay",
                    "severity": "error",
                    "line": i,
                    "detail": "kotlinx.coroutines.delay() is prohibited in test bodies",
                })

        # --- Lane 1: No Hilt ---
        if source_classification.class_type in ("viewmodel", "use_case", "reducer", "validator", "dto_mapper"):
            if re.search(r'@HiltAndroidTest', test_content):
                violations.append({
                    "rule": "lane1_no_hilt",
                    "severity": "error",
                    "line": _find_line(lines, "@HiltAndroidTest"),
                    "detail": "Lane 1 tests must not use @HiltAndroidTest. Use direct constructor injection.",
                })
            if re.search(r'HiltAndroidRule', test_content):
                violations.append({
                    "rule": "lane1_no_hilt",
                    "severity": "error",
                    "line": _find_line(lines, "HiltAndroidRule"),
                    "detail": "Lane 1 tests must not use HiltAndroidRule.",
                })

        # --- Lane 2: No ActivityScenario ---
        if source_classification.class_type in ("composable_screen", "composable_component"):
            if re.search(r'ActivityScenario', test_content):
                violations.append({
                    "rule": "lane2_no_activity_scenario",
                    "severity": "error",
                    "line": _find_line(lines, "ActivityScenario"),
                    "detail": "Lane 2 tests must not use ActivityScenario. Use createComposeRule().",
                })
            # Check for AppTheme vs MaterialTheme
            if re.search(r'MaterialTheme\s*\{', test_content) and not re.search(r'\w+Theme\s*\{', test_content):
                violations.append({
                    "rule": "lane2_use_app_theme",
                    "severity": "warning",
                    "line": _find_line(lines, "MaterialTheme"),
                    "detail": "Use the project's custom AppTheme instead of raw MaterialTheme.",
                })

        # --- Infinite animation + waitForIdle() ---
        has_infinite_animation = bool(re.search(
            r'rememberInfiniteTransition|CircularProgressIndicator|InfiniteRepeatableSpec|RepeatMode',
            test_content,
        ))
        if has_infinite_animation and re.search(r'waitForIdle\s*\(', test_content):
            violations.append({
                "rule": "infinite_animation_wait_for_idle",
                "severity": "error",
                "line": _find_line(lines, "waitForIdle"),
                "detail": "waitForIdle() must not be called when infinite animations are present. Use mainClock.autoAdvance = false + advanceTimeBy().",
            })

        # --- Oracle completeness ---
        oracle_rule = self._get_oracle_for_type(source_classification.class_type)
        oracle_hits = 0
        oracle_total = 0

        # Find test functions (backtick-named Kotlin tests)
        test_func_matches = list(re.finditer(r'@Test\s+fun\s+`([^`]+)`', test_content))
        if not test_func_matches:
            # Also match regular fun testXxx
            test_func_matches = list(re.finditer(r'@Test\s+fun\s+(\w+)', test_content))

        if not test_func_matches:
            violations.append({
                "rule": "no_test_functions",
                "severity": "error",
                "line": 0,
                "detail": "No @Test functions found in file",
            })

        if oracle_rule:
            # Check KDoc/comments for oracle fields
            # Look for GIVEN/WHEN/THEN in comments above each @Test
            test_blocks = re.split(r'@Test', test_content)
            for block in test_blocks[1:]:  # skip preamble
                oracle_total += len(oracle_rule.required_oracle_fields)
                block_upper = block.upper()
                for req_field in oracle_rule.required_oracle_fields:
                    if req_field.upper() in block_upper:
                        oracle_hits += 1
                    else:
                        violations.append({
                            "rule": "oracle_completeness",
                            "severity": "error",
                            "line": 0,
                            "detail": f"Missing oracle field '{req_field}' for class_type '{source_classification.class_type}'",
                        })

        oracle_completeness = oracle_hits / oracle_total if oracle_total > 0 else 0.0

        # --- Assertion count ---
        assertion_patterns = [
            r'assert\w+\s*\(', r'assertThat\s*\(', r'assertEquals\s*\(',
            r'assertTrue\s*\(', r'assertFalse\s*\(', r'assertIs\s*\(',
            r'\.assert\w+\s*\(', r'expectThat\s*\(',
        ]
        assertion_count = sum(
            len(re.findall(pat, test_content))
            for pat in assertion_patterns
        )

        if oracle_rule and test_func_matches:
            min_total = oracle_rule.required_assertions_min * len(test_func_matches)
            if assertion_count < min_total:
                violations.append({
                    "rule": "assertion_count",
                    "severity": "error",
                    "line": 0,
                    "detail": f"{assertion_count} total assertions found, minimum {min_total} expected ({oracle_rule.required_assertions_min} per test × {len(test_func_matches)} tests)",
                })

        # --- Determine lane coverage ---
        if re.search(r'createComposeRule\s*\(', test_content):
            lanes_covered.append("integration")  # Lane 2
        if re.search(r'createAndroidComposeRule', test_content):
            lanes_covered.append("contract")  # Lane 3
        if re.search(r'MacrobenchmarkRule|MacroBenchmark', test_content):
            lanes_covered.append("performance")  # Lane 4 perf
        if re.search(r'runTest\s*\{|@Test.*fun.*`', test_content) and not lanes_covered:
            lanes_covered.append("unit")  # Lane 1

        missing = [
            lt.value for lt in source_classification.required_lanes
            if lt.value not in lanes_covered
        ]

        has_errors = any(v["severity"] == "error" for v in violations)

        return {
            "valid": not has_errors,
            "violations": violations,
            "oracle_completeness": round(oracle_completeness, 2),
            "lanes_covered": lanes_covered,
            "missing_lanes": missing,
        }

    # ── Private Helpers ─────────────────────────────────────────────

    def _detect_class_type(self, file_path: str, content: str) -> str:
        """Infer class type from Kotlin file content using regex heuristics."""
        path_lower = file_path.lower()

        # Check for @Composable
        has_composable = bool(re.search(r'@Composable', content))

        # Check for ViewModel
        has_viewmodel = bool(re.search(
            r':\s*ViewModel\s*\(|extends\s+ViewModel|:\s*AndroidViewModel',
            content,
        ))

        # Check for NavHost/NavGraph
        has_nav = bool(re.search(r'NavHost|NavGraphBuilder|NavController', content))

        # Check for data class with mapping
        has_data_class = bool(re.search(r'data\s+class\s+\w+', content))
        has_mapper = bool(re.search(r'fun\s+\w+\.to\w+\s*\(|fun\s+\w+Dto|toDomain|toEntity', content))

        # Check for sealed class (state machine)
        has_sealed = bool(re.search(r'sealed\s+(class|interface)\s+\w+', content))

        # Infer type
        if has_viewmodel or "viewmodel" in path_lower:
            return "viewmodel"
        if has_nav or "navigation" in path_lower or "navgraph" in path_lower:
            return "navigation"
        if has_composable:
            # Check if it's state-hoisted (accepts state + callbacks)
            if re.search(r'@Composable\s+fun\s+\w+Screen\s*\(', content):
                return "composable_screen"
            if re.search(r'@Composable\s+fun\s+\w+Route\s*\(', content):
                return "composable_screen"  # Route composable
            return "composable_component"
        if has_data_class and has_mapper:
            return "dto_mapper"
        if has_sealed and "reducer" in path_lower:
            return "reducer"
        if "usecase" in path_lower or "use_case" in path_lower:
            return "use_case"
        if "validator" in path_lower:
            return "validator"
        if "repository" in path_lower or "repo" in path_lower:
            return "repository"
        if has_data_class:
            return "dto_mapper"
        return "utility"

    def _detect_smells(self, file_path: str, content: str, class_type: str) -> List[str]:
        """Detect testability smells from Kotlin source content."""
        smells: List[str] = []

        # VIEWMODEL_COUPLED_COMPOSABLE: Composable accepts ViewModel directly
        if class_type in ("composable_screen", "composable_component"):
            if re.search(r'hiltViewModel\s*\(', content):
                smells.append("VIEWMODEL_COUPLED_COMPOSABLE: Composable uses hiltViewModel() directly. Split into Route + Screen.")

        # INFINITE_ANIMATION_IN_TEST_TARGET
        if re.search(r'rememberInfiniteTransition|CircularProgressIndicator|InfiniteRepeatableSpec', content):
            smells.append("INFINITE_ANIMATION_IN_TEST_TARGET: Contains infinite animation. Tests must use mainClock.autoAdvance = false.")

        # CONSTRUCTOR_REQUIRES_HILT_IN_LANE1
        if class_type in ("viewmodel", "use_case", "reducer"):
            if re.search(r'@HiltViewModel|@Inject\s+constructor', content):
                if not re.search(r'constructor\s*\(', content):
                    smells.append("CONSTRUCTOR_REQUIRES_HILT_IN_LANE1: Cannot construct without DI graph.")

        # SavedStateHandle detection
        if re.search(r'SavedStateHandle', content):
            smells.append("SAVED_STATE_HANDLE_DETECTED: Must test missing-argument edge case.")

        # NO_CUSTOM_THEME_DETECTED is emitted at analysis time, not per-file

        return smells

    def _lanes_for_type(self, class_type: str) -> List[TestLaneType]:
        """Map class type to required test lanes."""
        mapping = {
            "viewmodel": [TestLaneType.UNIT],
            "use_case": [TestLaneType.UNIT],
            "reducer": [TestLaneType.UNIT],
            "validator": [TestLaneType.UNIT],
            "dto_mapper": [TestLaneType.UNIT],
            "composable_screen": [TestLaneType.UNIT, TestLaneType.INTEGRATION],
            "composable_component": [TestLaneType.INTEGRATION],
            "navigation": [TestLaneType.CONTRACT],
            "repository": [TestLaneType.UNIT, TestLaneType.INTEGRATION],
            "utility": [TestLaneType.UNIT],
        }
        return mapping.get(class_type, [TestLaneType.UNIT])

    def _get_oracle_for_type(self, class_type: str) -> Optional[OracleRule]:
        for rule in self.get_oracle_rules():
            if rule.source_class_type == class_type:
                return rule
        return None


# ── Module-level helpers ────────────────────────────────────────────

def _find_line(lines: List[str], pattern: str) -> int:
    """Find the first line number containing the pattern."""
    for i, line in enumerate(lines, 1):
        if pattern in line:
            return i
    return 0
