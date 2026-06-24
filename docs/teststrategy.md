# Android Compose AI Test Generation Strategy
**Version:** 6.0  
**Scope:** Android applications built with Jetpack Compose — full test surface from logic to release  
**Classification:** Principal QA Architecture — ARIA Generation Contract  
**Supersedes:** v5.0 (infinite animation waitForIdle hang, Hilt/ComponentActivity race condition, Paparazzi variant matrix mandate, MockWebServer dispatcher state bleed, design system tag naming exception)

---

## 1. Executive Summary

This document defines the test strategy and AI generation contract for Android applications built with Jetpack Compose. It covers the four-lane test model, toolchain, orchestrator configuration, lane-by-lane test design, ARIA generation rules, visual regression, accessibility, flakiness management, and CI/CD quality gates.

Three principles govern the strategy.

**Architecture uses four lanes. CI uses three execution modes.** Lane 1 and Lane 2 run on the JVM for fast feedback. Lane 3 runs on device selectively, only for screens with declared runtime risk. Lane 4 runs post-merge as two separately invoked concerns: journey tests (orchestrated instrumented tests) and performance tests (a dedicated Macrobenchmark module with its own build variant and compilation state). The CI pipeline expresses these as three modes: Fast PR Gate, Selective Device Gate, and Post-Merge Release Gate.

**State transition coverage takes precedence over line coverage.** A ViewModel at 85% line coverage with every sealed state exercised outperforms one at 95% line coverage missing `UiState.Error`. UI and device layers are measured by state, screen, and route coverage — not lines.

**AI generation requires a contract, not prose.** ARIA consumes machine-readable manifests, lane selection rules, oracle fingerprints, testability smell outputs, mutation verification tiers, and source-set placement metadata. Every design decision in this document has a corresponding ARIA execution rule in Section 11.

---

## 2. Scope

This strategy covers the full Android app test surface:

- ViewModel state machines, use cases, reducers, and DTO-to-domain mapping
- Composable rendering across all defined UI states
- Visual regression via snapshot testing
- Device-level runtime behaviour: navigation, deep links, IME, animations, permissions, lifecycle
- Accessibility validation
- End-to-end user journeys
- Performance: startup timing, frame timing, scroll, Macrobenchmark, Baseline Profiles

Scope does not include: backend service testing, server-side consumer-driven contract testing (Pact/provider), or native module testing outside the Android JVM and Compose surface.

---

## 3. Four-Lane Test Model

### 3.1 Lane Definitions

```
Lane 1 │ Logic & State            │ JUnit 5 │ JVM              │ Hard PR gate
Lane 2 │ Compose Screen/Component │ JUnit 4 │ JVM (Robolectric)│ Hard PR gate
Lane 3 │ Device Interaction       │ JUnit 4 │ Emulator/Device  │ Selective PR gate
Lane 4 │ Release Confidence       │ JUnit 4 │ Real device      │ Release promotion gate
```

**Lane 1** — ViewModel state machines, coroutine behaviour, use cases, reducers, validators, DTO-to-domain mapping, repository fake boundaries, and offline/cache logic. No Android runtime dependency. No Hilt. All classes constructed directly via constructor injection with fakes and `SavedStateHandle`.

**Lane 2** — Composable rendering for every defined UI state, user interaction against hoisted state, `rememberSaveable` restoration, and visual snapshots. Uses state-hoisted screen composables (not ViewModel-coupled route composables). Runs on JVM via Robolectric. Does not test pixel-bound visibility, IME insets, or real window inset behaviour — these belong in Lane 3.

**Lane 3** — NavHost and deep link resolution, IME, system permissions, lifecycle recreation, accessibility checks, animations, predictive back, network interception via `MockWebServer`, and real runtime wiring for offline/cache. Generated only for screens with declared device risk. Runs under the Android Test Orchestrator. Failure artifacts (screenshots or video) are uploaded to CI automatically.

**Lane 4** — Two distinct concerns sharing a post-merge pipeline stage:
- *Journey tests*: multi-screen business flows, correctness assertions, instrumented tests under Orchestrator
- *Performance tests*: Macrobenchmark startup/frame/scroll timing and Baseline Profile generation, running in a dedicated `:macrobenchmark` module with its own build variant and compilation state

Lane 3 proves Android runtime behaviour. Lane 4 proves release safety and performance.

### 3.2 Three Execution Modes (CI Operational Model)

```
Mode 1: Fast PR Gate
  Runs: Lane 1 + Lane 2 (JVM, < 90s)
  Trigger: Every PR
  Gate: Hard block on any failure

Mode 2: Selective Device Gate
  Runs: Lane 3 — only for screens where changedFeatureGate = true or deviceRisk is declared
  Trigger: PR touching files linked to risk-flagged screens
  Gate: 100% pass for smoke/changed-feature tests; expanded non-blocking
  Retry: Up to 2 automatic retries per test before failure classification (Section 10.4)

Mode 3: Post-Merge Release Gate
  Runs on trunk, async, separate invocations:
    Mode 3a: Lane 4 journey tests (instrumented, Orchestrator, real device)
    Mode 3b: Lane 4 performance (:macrobenchmark module, BenchmarkRunner, no Orchestrator)
  Gate: Does not block feature PR merge.
        Failures above severity threshold block release promotion, not feature merge.
```

### 3.3 Route/Screen Composable Split

```kotlin
// Route: injects ViewModel, collects state — tested in Lane 3 via NavHost
@Composable
fun ProductListRoute(viewModel: ProductListViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    ProductListScreen(state = state, onRetry = viewModel::retry, onProductClick = viewModel::openProduct)
}

// Screen: pure UI composable — tested in Lane 2 with direct state injection
@Composable
fun ProductListScreen(
    state: ProductListUiState,
    onRetry: () -> Unit,
    onProductClick: (String) -> Unit
) {
    when (state) {
        is ProductListUiState.Loading      -> LoadingIndicator()
        is ProductListUiState.Success      -> ProductList(state.products, onProductClick)
        is ProductListUiState.Empty        -> EmptyState()
        is ProductListUiState.Error        -> ErrorState(state.message, onRetry)
        is ProductListUiState.CachedSuccess -> CachedProductList(state.products, state.isOffline, onProductClick)
        is ProductListUiState.OfflineError  -> OfflineErrorState(onRetry)
    }
}
```

Lane 1 tests `ProductListViewModel`. Lane 2 tests `ProductListScreen`. Lane 3 tests `ProductListRoute` through `NavHost`. Lane 4 tests full journeys.

### 3.4 ARIA Lane Selection Decision Tree

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

---

## 4. Toolchain

### 4.1 Version Catalog Policy

All dependency coordinates are managed through the project's `libs.versions.toml` Gradle version catalog. The aliases below are illustrative; the catalog is authoritative. ARIA must use catalog-defined versions and must not override them.

```kotlin
// Lane 1 — Logic & State (app/src/test)
testImplementation(libs.junit.jupiter)
testImplementation(libs.kotlinx.coroutines.test)
testImplementation(libs.turbine)
testImplementation(libs.mockk)

// Lane 2 — Compose Screen (app/src/test)
testImplementation(libs.robolectric)
testImplementation(libs.androidx.compose.ui.test.junit4)
testImplementation(libs.paparazzi)

// Lane 3 — Device Interaction (app/src/androidTest)
androidTestImplementation(libs.androidx.compose.ui.test.junit4)
androidTestImplementation(libs.androidx.compose.ui.test.manifest)
androidTestImplementation(libs.androidx.compose.ui.test.accessibility)  // pure Compose
androidTestImplementation(libs.androidx.navigation.testing)
androidTestImplementation(libs.hilt.android.testing)
androidTestImplementation(libs.espresso.core)
androidTestImplementation(libs.mockwebserver)                            // network interception
// androidTestImplementation(libs.espresso.accessibility)  // hybrid View+Compose only
androidTestUtil(libs.androidx.test.orchestrator)

// Lane 4 Journey (app/src/androidTest)
androidTestImplementation(libs.androidx.compose.ui.test.junit4)

// Lane 4 Performance (:macrobenchmark/src/androidTest — separate module)
// androidTestImplementation(libs.androidx.benchmark.macro)
// androidTestImplementation(libs.androidx.profileinstaller)
```

### 4.2 Build Configuration

```kotlin
android {
    defaultConfig {
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["clearPackageData"] = "true"
        testInstrumentationRunnerArguments["useTestStorageService"] = "true"
    }
    testOptions {
        execution = "ANDROIDX_TEST_ORCHESTRATOR"
        animationsDisabled = true
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}
```

```kotlin
// macrobenchmark/build.gradle.kts
plugins { alias(libs.plugins.androidx.benchmark) }
android {
    defaultConfig {
        testInstrumentationRunner = "androidx.benchmark.junit4.AndroidBenchmarkRunner"
    }
    // No ORCHESTRATOR. No clearPackageData. Benchmark controls its own process.
    targetProjectPath = ":app"
    experimentalProperties["android.experimental.self-instrumenting"] = true
}
```

---

## 5. Orchestrator Architecture

### 5.1 Isolation Model

The Android Test Orchestrator runs each test **method** in its own `Instrumentation` invocation. With `clearPackageData = true`, app data (SharedPreferences, Room databases, in-memory singletons) is cleared after each test invocation. Isolation is per test method.

The Orchestrator applies to **Lane 3** and **Lane 4 journey tests** only. Lane 4 performance tests (Macrobenchmark, Baseline Profile) run in the `:macrobenchmark` module under `AndroidBenchmarkRunner`, which controls the app process lifecycle and compilation state independently. Applying `clearPackageData` or the standard Orchestrator to a Macrobenchmark invocation interferes with its measurement model and must not be done.

### 5.2 JVM Test Isolation — Accurate Model

Lanes 1 and 2 run in Gradle-forked JVM test processes. Gradle forks a JVM for test execution, but by default multiple test classes can share the same forked process. Static state — Robolectric shadows, `Dispatchers.Main` overrides, fake singleton registrations, and thread-local caches — can leak between test classes sharing a fork.

**Required state resets for Lane 1 and Lane 2:**

- Reset `Dispatchers.Main` in every `@AfterEach` / `@After` via `Dispatchers.resetMain()`
- Reset fake repository state in `@Before` via a `reset()` method, not by relying on field re-initialisation order
- Do not use companion object singletons or `object` declarations in fakes — they persist across tests in the same fork
- For Robolectric: shadow state is reset between tests within a class, but `@Config` changes between test classes can require separate fork instances

Use `forkEvery = 1` in `testOptions.unitTests` only for suites with known leaky static state, as it significantly increases runtime. It is not the default.

### 5.3 testTagsAsResourceId — Correct Application

```kotlin
setContent {
    Box(modifier = Modifier.semantics { testTagsAsResourceId = true }) {
        MyAppNavHost(navController = rememberNavController())
    }
}
```

A `Modifier.semantics { ... }` created without being passed to a composable argument has no effect.

### 5.4 Failure Capture for Lane 3 and Lane 4

`useTestStorageService = "true"` enables the Android test storage service but does not automatically capture failure artifacts. Lane 3 and Lane 4 tests must be configured to upload screenshots or video on failure so that ARIA's ANALYSE phase and human reviewers can diagnose flakiness without re-running tests.

```kotlin
// Add to Lane 3 and Lane 4 base test class
@get:Rule(order = 0)
val screenshotRule = ScreenCaptureTestRule()  // or TestStorageScreenshotTestRule()
```

For CI environments that support it (Firebase Test Lab, Gradle Managed Devices), configure video recording:

```yaml
# Firebase Test Lab — failure video
- name: Lane 3 Device Gate
  run: |
    gcloud firebase test android run \
      --record-video \
      --results-bucket gs://myapp-test-results \
      ...
```

Failure artifact storage paths are included in the ARIA ANALYSE phase failure report, linked per test method.

### 5.5 Runtime-Based Sharding

```
Shard count = ceil(total_lane3_p90_runtime_seconds / target_stage_runtime_seconds)
```

ARIA tracks median and P90 test method duration per lane and recalculates shard targets after each suite growth of more than 20 tests. Target stage runtime is typically 600 seconds for Mode 2.

### 5.6 ARIA Phase Loop

**DISCOVER** — Scans `@Composable` signatures, NavGraph, ViewModel sealed states, and `@Preview` annotations. Reads existing test files. Emits testability smells (Section 11.7). If no manifest is found for a screen, applies fallback rules (Section 11.2). Output: screen manifest per screen.

**GENERATE** — Applies lane decision tree. Checks oracle fingerprint (including locale and configVariant) for duplicates. Produces test stubs conforming to the oracle contract.

**EXECUTE** — Mode 1 (JVM, < 90s). On pass, triggers Mode 2 for risk-flagged screens with infrastructure retry policy (Section 10.4). Mode 3a and 3b run post-merge.

**ANALYSE** — Classifies failures by root cause (Section 10.1). Attaches failure capture artifact links. Routes to repair agent per category.

**GATE** — Enforces gates per Section 12.1. Blocks release promotion per Section 12.2.

---

## 6. Lane 1 — Logic & State

### 6.1 Construction Pattern — No Hilt, Direct Injection

Lane 1 tests construct all classes directly via constructor injection. `@HiltAndroidTest` and `HiltAndroidRule` require Android instrumentation and must not appear in Lane 1. A class that cannot be constructed without Hilt is a testability smell (Section 11.7). Hilt wiring is validated in Lane 3 smoke tests.

```kotlin
val testDispatcher = UnconfinedTestDispatcher()
val viewModel = ProductListViewModel(
    repository  = FakeProductRepository(),
    dispatcher  = testDispatcher
)
```

### 6.2 SavedStateHandle Injection

ViewModels that consume `SavedStateHandle` for navigation arguments or process death state must receive it via constructor injection in tests. Do not mock `SavedStateHandle` — it is a concrete class designed to be constructed directly.

```kotlin
@Test
fun `loads product id from SavedStateHandle on initialisation`() = runTest {
    val handle = SavedStateHandle(mapOf("productId" to "ABC-123"))
    val viewModel = ProductDetailViewModel(
        repository    = FakeProductRepository(),
        savedState    = handle,
        dispatcher    = testDispatcher
    )

    viewModel.uiState.test {
        skipItems(1)
        val state = awaitItem() as UiState.Success
        assertThat(state.product.id).isEqualTo("ABC-123")
        cancelAndIgnoreRemainingEvents()
    }
}

@Test
fun `missing productId in SavedStateHandle emits UiState Error`() = runTest {
    val handle = SavedStateHandle(emptyMap())   // simulate missing nav argument
    val viewModel = ProductDetailViewModel(
        repository = FakeProductRepository(),
        savedState = handle,
        dispatcher = testDispatcher
    )

    viewModel.uiState.test {
        skipItems(1)
        assertThat(awaitItem()).isInstanceOf(UiState.Error::class.java)
        cancelAndIgnoreRemainingEvents()
    }
}
```

Every ViewModel that consumes `SavedStateHandle` must have at least one test covering the missing-argument path. ARIA detects `SavedStateHandle` in ViewModel constructor signatures and generates both the happy path and the missing-argument edge case.

### 6.3 ViewModel State Testing

```kotlin
@OptIn(ExperimentalCoroutinesApi::class)
class ProductListViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()

    @BeforeEach fun setup()    { Dispatchers.setMain(testDispatcher) }
    @AfterEach  fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun `emits Loading then Success when repository returns data`() = runTest {
        val viewModel = ProductListViewModel(
            repository = FakeProductRepository(products = listOf(Product(id = "1", name = "Widget"))),
            dispatcher = testDispatcher
        )
        viewModel.uiState.test {
            assertThat(awaitItem()).isInstanceOf(UiState.Loading::class.java)
            assertThat((awaitItem() as UiState.Success).products).hasSize(1)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `emits Loading then Error on IOException`() = runTest {
        val viewModel = ProductListViewModel(
            repository = FakeProductRepository(throwOnFetch = IOException("timeout")),
            dispatcher = testDispatcher
        )
        viewModel.uiState.test {
            skipItems(1)
            assertThat((awaitItem() as UiState.Error).message).isNotEmpty()
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `CancellationException is not emitted as UiState Error`() = runTest {
        val viewModel = ProductListViewModel(
            repository = FakeProductRepository(throwOnFetch = CancellationException()),
            dispatcher = testDispatcher
        )
        viewModel.uiState.test {
            skipItems(1); expectNoEvents(); cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `concurrent load calls cancel the prior request`() = runTest {
        val fakeRepo = FakeProductRepository(products = listOf(Product(id = "1", name = "Widget")))
        val viewModel = ProductListViewModel(repository = fakeRepo, dispatcher = testDispatcher)
        viewModel.load(); advanceTimeBy(50); viewModel.load(); advanceUntilIdle()
        assertThat(fakeRepo.cancelledRequestCount).isEqualTo(1)
        assertThat(fakeRepo.completedRequestCount).isEqualTo(1)
    }
}
```

**Sealed state coverage rule:** Every sealed subclass of a ViewModel's `UiState` must have at least one Lane 1 test. A ViewModel with any uncovered sealed subclass fails the Lane 1 gate.

### 6.4 Parameterized Testing for DTOs and Reducers

DTO-to-domain mapping, validators, and reducer state machines involve matrix combinations. Use JUnit 5 `@ParameterizedTest` to cover combinations without creating a separate test method per case.

```kotlin
// DTO mapping — parameterized by nullable price
@ParameterizedTest
@CsvSource(
    "null,   true,  0.00",   // null price, out of stock, display as 0.00
    "9.99,   false, 9.99",
    "0.00,   false, 0.00"
)
fun `ProductDto price and stock map correctly to domain`(
    rawPrice: String?, isOutOfStock: Boolean, displayPrice: Double
) {
    val dto = ProductDto(id = "1", price = rawPrice?.toDoubleOrNull(), stockCount = if (isOutOfStock) 0 else 1)
    val domain = dto.toDomain()
    assertThat(domain.isOutOfStock).isEqualTo(isOutOfStock)
    assertThat(domain.displayPrice).isEqualTo(displayPrice)
}

// Reducer — state + action matrix
@ParameterizedTest
@MethodSource("reducerCases")
fun `reducer transitions state correctly`(initial: CartState, action: CartAction, expected: CartState) {
    assertThat(cartReducer(initial, action)).isEqualTo(expected)
}

companion object {
    @JvmStatic
    fun reducerCases(): Stream<Arguments> = Stream.of(
        Arguments.of(CartState.Empty,         CartAction.AddItem(item1), CartState.HasItems(listOf(item1))),
        Arguments.of(CartState.HasItems(listOf(item1)), CartAction.RemoveItem(item1), CartState.Empty),
        Arguments.of(CartState.Empty,         CartAction.Checkout,       CartState.Error("Cart is empty"))
    )
}
```

**ARIA rule:** For every mapper function and reducer with more than two input combinations, ARIA must generate a `@ParameterizedTest` with `@MethodSource` or `@CsvSource` rather than individual test methods per case. Individual test methods per case are generated only for named edge cases with distinct business semantics (e.g., `CancellationException` handling).

### 6.5 DTO-to-Domain Mapping

```kotlin
@Test
fun `null price field in DTO maps to null in domain model`() {
    val domain = ProductDto(id = "1", displayName = "Widget", price = null, stockCount = 0).toDomain()
    assertThat(domain.price).isNull()
    assertThat(domain.isOutOfStock).isTrue()
}

@Test
fun `unknown enum value in DTO maps to UNKNOWN variant`() {
    val domain = ProductDto(status = "FUTURE_VALUE_NOT_YET_IN_CLIENT").toDomain()
    assertThat(domain.status).isEqualTo(ProductStatus.UNKNOWN)
}
```

### 6.6 Offline and Cache Logic

```kotlin
@Test
fun `emits CachedSuccess with offline marker when network unavailable and cache exists`() = runTest {
    val viewModel = ProductListViewModel(
        repository = FakeProductRepository(
            cachedProducts = listOf(Product(id = "1", name = "Cached")),
            networkAvailable = false
        ),
        dispatcher = testDispatcher
    )
    viewModel.uiState.test {
        skipItems(1)
        val state = awaitItem() as UiState.CachedSuccess
        assertThat(state.isOffline).isTrue()
        cancelAndIgnoreRemainingEvents()
    }
}
```

### 6.7 Hilt DI Wiring — Lane 3 Only

```kotlin
@TestInstallIn(components = [SingletonComponent::class], replaces = [ProductModule::class])
@Module
object TestProductModule {
    @Provides fun provideProductRepository(): ProductRepository = FakeProductRepository()
}
```

Used in Lane 3 tests only. Not generated in Lane 1 or Lane 2 test classes.

---

## 7. Lane 2 — Compose Screen/Component

### 7.1 Robolectric Limitations

Lane 2 runs on Robolectric, which provides a fast JVM-based Android environment but has meaningful differences from a real device. ARIA must not generate Lane 2 tests for concerns that require real Android layout and window behaviour.

**`assertIsDisplayed()` bounds caveat.** Robolectric does not calculate true pixel-bound view visibility. `assertIsDisplayed()` in Lane 2 verifies semantic inclusion in the composition tree — a node that would be clipped or off-screen on a real device can still pass `assertIsDisplayed()` in Robolectric. True layout and bounds validation belongs in Lane 3.

**IME and window insets.** Robolectric does not simulate real window inset resolution. Assertions on `imePadding()`, `WindowInsets.ime`, keyboard height, or any composable that adjusts layout based on soft keyboard state will produce unreliable results in Lane 2. All IME-dependent layout assertions must be deferred to Lane 3.

**Real animation timing.** Robolectric supports basic clock control but does not faithfully reproduce all animation timing behaviours. Complex shared element transitions or spring physics animations should be validated in Lane 3.

**Infinite animation `waitForIdle()` hang — critical.** Any composable containing a continuous, non-terminating animation — `rememberInfiniteTransition`, `CircularProgressIndicator`, indeterminate shimmer, pulsating badge — keeps the Compose clock perpetually busy. Calling `composeTestRule.waitForIdle()` while such an animation is active will block the test indefinitely and hang the CI job. This applies in both Lane 2 (Robolectric) and Lane 3 (device).

The required pattern when an infinite animation is present:

```kotlin
// WRONG: hangs indefinitely if a CircularProgressIndicator is in the composition
composeTestRule.setContent { MyAppTheme { ProductListScreen(ProductListUiState.Loading, {}, {}) } }
composeTestRule.waitForIdle()  // ← hangs

// CORRECT: disable auto-advance before composing; advance manually to assert state
composeTestRule.mainClock.autoAdvance = false
composeTestRule.setContent { MyAppTheme { ProductListScreen(ProductListUiState.Loading, {}, {}) } }
composeTestRule.mainClock.advanceTimeBy(500)  // advance past initial composition frame
composeTestRule.onNodeWithTag("product_list_loading_indicator").assertIsDisplayed()
```

`waitForIdle()` must not be called while an infinite animation is running. ARIA must detect the presence of `rememberInfiniteTransition`, `CircularProgressIndicator`, `InfiniteRepeatableSpec`, or `RepeatMode` in any composable that is a test target, disable `mainClock.autoAdvance` in the generated test, and emit an `INFINITE_ANIMATION_IN_TEST_TARGET` testability smell.

### 7.2 AppTheme vs MaterialTheme

Apps use a custom `AppTheme` composable that extends `MaterialTheme` with dynamic color schemes, custom typography, shape overrides, and design token mappings. Using raw `MaterialTheme {}` in Lane 2 tests misses these tokens, causing snapshot assertions to test against a different visual baseline than production.

**ARIA detection rule:** ARIA must scan the project for a composable function whose name ends in `Theme` (e.g., `MyAppTheme`, `ProductAppTheme`) and that calls `MaterialTheme` internally. If found, ARIA uses the project's theme composable as the wrapper in all `setContent {}` calls, not raw `MaterialTheme {}`.

```kotlin
// ARIA detects and uses the project's theme
composeTestRule.setContent {
    MyAppTheme {  // detected from codebase, not hardcoded as MaterialTheme
        ProductListScreen(state = ..., onRetry = {}, onProductClick = {})
    }
}
```

If no custom theme is detected, `MaterialTheme {}` is used as the fallback. ARIA emits a `NO_CUSTOM_THEME_DETECTED` testability smell when falling back, prompting the team to verify the fallback is intentional.

### 7.3 State-Hoisted Screen Testing

```kotlin
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class ProductListScreenTest {

    @get:Rule val composeTestRule = createComposeRule()

    @Test fun `success state renders list`() {
        composeTestRule.setContent {
            MyAppTheme { ProductListScreen(ProductListUiState.Success(sampleProducts()), {}, {}) }
        }
        composeTestRule.waitForIdle()
        composeTestRule.onAllNodesWithTag("product_list_item").assertCountEquals(5)
    }

    @Test fun `error state shows retry and hides list`() {
        composeTestRule.setContent {
            MyAppTheme { ProductListScreen(ProductListUiState.Error("err"), {}, {}) }
        }
        composeTestRule.waitForIdle()
        composeTestRule.onNodeWithTag("product_list_retry_button").assertIsDisplayed()
        composeTestRule.onNodeWithTag("product_list_container").assertDoesNotExist()
    }

    @Test fun `retry callback fires on tap`() {
        var count = 0
        composeTestRule.setContent {
            MyAppTheme { ProductListScreen(ProductListUiState.Error("err"), onRetry = { count++ }, onProductClick = {}) }
        }
        composeTestRule.onNodeWithTag("product_list_retry_button").performClick()
        assertThat(count).isEqualTo(1)
    }
}
```

### 7.4 LazyColumn Assertions

```kotlin
// WRONG: composed node count ≠ total list size; Robolectric bounds unreliable
composeTestRule.onAllNodesWithTag("product_list_item").assertCountEquals(100)

// CORRECT: assert total via Lane 1 state
assertThat((viewModel.uiState.value as UiState.Success).products).hasSize(100)

// CORRECT: assert non-empty
composeTestRule.waitUntil(timeoutMillis = 3_000) {
    composeTestRule.onAllNodesWithTag("product_list_item").fetchSemanticsNodes().isNotEmpty()
}

// CORRECT: assert a specific index can be scrolled to
composeTestRule.onNodeWithTag("product_list_container").performScrollToIndex(99)
composeTestRule.onNodeWithTag("product_list_item_99").assertIsDisplayed()
```

### 7.5 Custom Non-Empty Assertion Helper

```kotlin
// WRONG: does not compile — assertCountEquals takes Int, not Matcher
onAllNodesWithTag("result_item").assertCountEquals(greaterThan(0))

// CORRECT: custom extension in sharedTestUtils source set
fun SemanticsNodeInteractionCollection.assertCountGreaterThan(min: Int) {
    val count = fetchSemanticsNodes().size
    assert(count > min) { "Expected more than $min nodes but found $count" }
}
```

### 7.6 Saved Instance State Restoration

```kotlin
@Test
fun `email field survives configuration change via rememberSaveable`() {
    val restorationTester = StateRestorationTester(composeTestRule)
    restorationTester.setContent { MyAppTheme { UserRegistrationForm() } }
    composeTestRule.onNodeWithContentDescription("Email field").performTextInput("test@example.com")
    restorationTester.emulateSavedInstanceStateRestore()
    composeTestRule.onNodeWithContentDescription("Email field").assertTextContains("test@example.com")
}
```

`StateRestorationTester` simulates `onSaveInstanceState` / `onRestoreInstanceState`. It does not simulate process death. For real lifecycle recreation, use `ActivityScenario.recreate()` in Lane 3.

### 7.7 Visual Snapshot Testing

Generate snapshots only for: design system leaf components, complex screen composables with more than two distinct visual states, states with meaningful visual difference, and high-risk UI surfaces (payment, onboarding, legal).

```kotlin
class ProductCardSnapshotTest {
    @get:Rule val paparazzi = Paparazzi(deviceConfig = DeviceConfig.PIXEL_6)

    @Test fun `light mode default`() {
        paparazzi.snapshot { MyAppTheme { ProductCard(product = sampleProduct(), onAddToCart = {}) } }
    }

    @Test fun `dark mode default`() {
        paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(nightMode = NightMode.NIGHT))
        paparazzi.snapshot { MyAppTheme(darkTheme = true) { ProductCard(product = sampleProduct(), onAddToCart = {}) } }
    }
}
```

**ARIA variant matrix mandate:** For every screen where `snapshotRequired = true`, ARIA must generate a Paparazzi test for every entry in `configurationVariants` and `localeVariants` declared in the manifest. The full matrix must be covered — not just light and dark mode. Missing a variant means RTL text truncation, large-font clipping, or locale-specific layout breaks go undetected until production.

```kotlin
// ARIA generates one test method per combination
// manifest: configurationVariants: ["darkMode", "fontScale200", "rtl"]
//           localeVariants: ["de_DE", "ar_SA"]

class ProductCardSnapshotTest {
    @get:Rule val paparazzi = Paparazzi(deviceConfig = DeviceConfig.PIXEL_6)

    @Test fun `light_default`() { paparazzi.snapshot { MyAppTheme { ProductCard(...) } } }
    @Test fun `dark_mode`()     { paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(nightMode = NightMode.NIGHT)); paparazzi.snapshot { MyAppTheme(darkTheme = true) { ProductCard(...) } } }
    @Test fun `font_scale_200`(){ paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(fontScale = 2.0f)); paparazzi.snapshot { MyAppTheme { ProductCard(...) } } }
    @Test fun `rtl_layout`()    { paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(layoutDirection = LayoutDirection.RTL)); paparazzi.snapshot { MyAppTheme { CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) { ProductCard(...) } } } }
    @Test fun `locale_de_DE`()  { paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(locale = "de")); paparazzi.snapshot { MyAppTheme { ProductCard(...) } } }
    @Test fun `locale_ar_SA`()  { paparazzi.unsafeUpdateConfig(DeviceConfig.PIXEL_6.copy(locale = "ar")); paparazzi.snapshot { MyAppTheme { CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) { ProductCard(...) } } } }
}
```

ARIA must fail with a `MISSING_SNAPSHOT_VARIANT` generation error if any declared variant has no corresponding Paparazzi test after generation.

**Visual gate by `snapshotStability`:**

| Value | Gate Behaviour |
|---|---|
| `stable` | 0–0.1% auto-approve; 0.1–0.5% QA review; > 0.5% auto-block |
| `new` | All deltas require explicit QA approval; percentage gates do not apply |
| `theme_migration` | All deltas require explicit QA approval; percentage gates do not apply |
| `experimental` | Non-blocking; tracked and reported; no approval gate |

---

## 8. Lane 3 — Device Interaction

Lane 3 is **selective by default**. ARIA generates Lane 3 tests only for screens whose manifest declares at least one true `deviceRisk` entry.

### 8.1 Accessibility Setup

For pure Compose screens, use `androidx.compose.ui:ui-test-junit4-accessibility` and `enableAccessibilityChecks()`. For state-level scans with no interaction, call `onRoot().tryPerformAccessibilityChecks()`.

**Hilt + `createAndroidComposeRule` ordering.** `createAndroidComposeRule<SomeActivity>()` launches the target Activity as part of the `@Rule` setup phase — before `@Before` executes. If `hiltRule.inject()` runs in `@Before`, the Activity is already started before dependencies are wired into the graph. Any `hiltViewModel()` call inside the composable may receive unwired stubs or throw a `NullPointerException`.

The correct pattern for all Lane 3 tests using Hilt is to launch a bare `ComponentActivity` and call `setContent {}` manually inside the test body, after injection:

```kotlin
// WRONG: MainActivity launches before hiltRule.inject() runs in @Before
@get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
@get:Rule(order = 1) val composeTestRule = createAndroidComposeRule<MainActivity>()

// CORRECT: ComponentActivity is hollow — no setContent until test body runs after inject()
@get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
@get:Rule(order = 1) val composeTestRule = createAndroidComposeRule<ComponentActivity>()

@Before fun setup() {
    hiltRule.inject()  // inject() runs before any setContent call
}
```

```kotlin
@get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
@get:Rule(order = 1) val composeTestRule = createAndroidComposeRule<ComponentActivity>()

@Before fun setup() { hiltRule.inject() }

@Test @Tag("accessibility")
fun `product list success state passes accessibility checks`() {
    composeTestRule.enableAccessibilityChecks()
    // setContent called AFTER injection — DI graph is fully wired
    composeTestRule.setContent {
        MyAppTheme {
            ProductListScreen(
                state = ProductListUiState.Success(sampleProducts()),
                onRetry = {}, onProductClick = {}
            )
        }
    }
    composeTestRule.waitForIdle()
    composeTestRule.onRoot().tryPerformAccessibilityChecks()
}
```

ARIA must use `createAndroidComposeRule<ComponentActivity>()` in all Lane 3 test classes that inject via Hilt. `createAndroidComposeRule<MainActivity>()` is only valid in tests that do not use Hilt injection and require real Activity lifecycle (e.g., deep link resolution tests using `ActivityScenario.launch()` directly).

Additional semantic assertions (separate from accessibility checks):

```kotlin
composeTestRule.onAllNodes(hasClickAction()).assertAll(hasContentDescription() or hasText())
```

**Meaningful image assertions — manifest-driven with expected text:**

```kotlin
// WRONG: empty string is a vacuous oracle — any non-null contentDescription passes
composeTestRule.onNodeWithTag("product_image").assertContentDescriptionContains("")

// CORRECT: expected text sourced from manifest accessibilityProfile.meaningfulImages
composeTestRule.onNodeWithTag("product_image").assertContentDescriptionContains("Product image")
// For locale-variable strings, resolve the string resource at test time:
composeTestRule.onNodeWithTag("product_image")
    .assertContentDescriptionContains(context.getString(R.string.product_image_description))
```

Decorative images (`contentDescription = null`) must not appear in any `assertContentDescriptionContains` assertion.

### 8.2 Network Interception — MockWebServer

Lane 3 uses real Hilt wiring. Network calls must be intercepted via `MockWebServer` (or an `OkHttp` `Interceptor`) injected through the `@TestInstallIn` module to drive Error and Empty states. Do not use device airplane mode — toggling airplane mode via `UiAutomator` is flaky and affects all network operations on the device, not just the app under test.

```kotlin
// TestNetworkModule.kt
@TestInstallIn(components = [SingletonComponent::class], replaces = [NetworkModule::class])
@Module
object TestNetworkModule {

    private val mockWebServer = MockWebServer()

    @Provides @Singleton
    fun provideMockWebServer(): MockWebServer = mockWebServer

    @Provides @Singleton
    fun provideOkHttpClient(): OkHttpClient = OkHttpClient.Builder().build()

    @Provides @Singleton
    fun provideRetrofit(client: OkHttpClient, server: MockWebServer): Retrofit =
        Retrofit.Builder()
            .baseUrl(server.url("/"))
            .addConverterFactory(GsonConverterFactory.create())
            .client(client)
            .build()
}
```

```kotlin
// Lane 3 test using MockWebServer
@HiltAndroidTest
class ProductListScreenNetworkTest {

    @get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
    @get:Rule(order = 1) val composeTestRule = createAndroidComposeRule<MainActivity>()

    @Inject lateinit var mockWebServer: MockWebServer

    @Before fun setup() { hiltRule.inject() }

    @Test
    fun `network error drives Error state and shows retry button`() {
        mockWebServer.enqueue(MockResponse().setResponseCode(503))

        composeTestRule.setContent { MyAppTheme { ProductListRoute() } }
        composeTestRule.waitForIdle()

        composeTestRule.onNodeWithTag("product_list_retry_button").assertIsDisplayed()
        composeTestRule.onNodeWithTag("product_list_container").assertDoesNotExist()
    }

    @Test
    fun `empty product list from server drives Empty state`() {
        mockWebServer.enqueue(MockResponse().setBody("""{"products": []}""").setResponseCode(200))

        composeTestRule.setContent { MyAppTheme { ProductListRoute() } }
        composeTestRule.waitForIdle()

        composeTestRule.onNodeWithTag("product_list_empty_state").assertIsDisplayed()
    }
}
```

### 8.3 Navigation and Deep Links

```kotlin
@Test fun `back press from detail returns to list`() {
    composeTestRule.setContent { val nav = rememberNavController(); MyAppNavHost(nav) }
    composeTestRule.onAllNodesWithTag("product_list_item")[0].performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("product_detail_screen").assertExists()
    Espresso.pressBack(); composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("product_list_container").assertExists()
}

@Test fun `deep link does not leave empty back stack`() {
    ActivityScenario.launch<MainActivity>(
        Intent(ACTION_VIEW, "myapp://product/ABC-123".toUri(),
               InstrumentationRegistry.getInstrumentation().targetContext, MainActivity::class.java)
    ).use {
        composeTestRule.waitForIdle()
        composeTestRule.onNodeWithText("ABC-123").assertIsDisplayed()
        Espresso.pressBack()
        composeTestRule.onNodeWithTag("home_screen").assertExists()
    }
}
```

### 8.4 IME Interaction

IME and window inset assertions belong in Lane 3, not Lane 2.

```kotlin
@Test fun `submit button remains visible and enabled when soft keyboard appears`() {
    composeTestRule.setContent { MyAppTheme { CheckoutFormScreen() } }
    composeTestRule.onNodeWithContentDescription("Email field").performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("checkout_submit_button").assertIsDisplayed()
    composeTestRule.onNodeWithTag("checkout_submit_button").assertIsEnabled()
}
```

### 8.5 Permissions

```kotlin
@get:Rule(order = 0) val hiltRule = HiltAndroidRule(this)
@get:Rule(order = 1) val permissionRule = GrantPermissionRule.grant(Manifest.permission.ACCESS_FINE_LOCATION)

@Test fun `location permission granted enables map controls`() {
    composeTestRule.setContent { MyAppTheme { LocationFeatureRoute() } }
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("location_my_location_button").assertIsEnabled()
}
```

### 8.6 Lifecycle Recreation

```kotlin
@Test fun `form state survives rotation`() {
    val scenario = ActivityScenario.launch(MainActivity::class.java)
    composeTestRule.onNodeWithContentDescription("Name field").performTextInput("Muthu")
    scenario.recreate()
    composeTestRule.onNodeWithContentDescription("Name field").assertTextContains("Muthu")
}
```

### 8.7 Animation Clock Control

```kotlin
@Test fun `animated visibility completes before assertion`() {
    composeTestRule.mainClock.autoAdvance = false
    composeTestRule.setContent { MyAppTheme { ProductDetailScreen(showDetails = true) } }
    composeTestRule.onNodeWithText("Show Details").performClick()
    composeTestRule.mainClock.advanceTimeBy(300)
    composeTestRule.onNodeWithText("Product Details").assertIsDisplayed()
}
```

### 8.8 Locale and Configuration

```kotlin
@Test fun `price renders in EUR format for de_DE locale`() {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    // Create a new Configuration copy — do not mutate the existing object
    val euroConfig = Configuration(context.resources.configuration).apply {
        setLocale(Locale("de", "DE"))
    }
    val euroContext = context.createConfigurationContext(euroConfig)

    composeTestRule.setContent {
        CompositionLocalProvider(LocalContext provides euroContext) {
            MyAppTheme { PriceLabel(amount = 9.99, currency = "EUR") }
        }
    }
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithText("9,99 €").assertIsDisplayed()
}
```

### 8.9 Predictive Back

Generated only when: `deviceRisk.requiresPredictiveBack = true` AND screen has custom `BackHandler` AND `businessCriticality = "release_blocking"` AND target API ≥ 35. Tests validate destination correctness, not animation semantics.

### 8.10 Offline Smoke Test

```kotlin
@Test @Tag("offline")
fun `product list shows cached data and offline banner without network`() {
    // Network intercepted via MockWebServer — no responses enqueued = connection refused
    composeTestRule.setContent { MyAppTheme { ProductListRoute() } }
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("product_list_offline_banner").assertIsDisplayed()
}
```

One smoke test per screen declaring `requiresOfflineSmoke = true`. Full offline logic coverage is in Lane 1.

---

## 9. Lane 4 — Release Confidence

### 9.1 Journey Tests

```kotlin
@Test fun `purchase journey from list to order confirmation`() {
    composeTestRule.setContent { MyApp() }
    composeTestRule.onAllNodesWithTag("product_list_item")[0].performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("product_detail_add_to_cart_button").performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("cart_checkout_button").performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("checkout_place_order_button").performClick()
    composeTestRule.waitForIdle()
    composeTestRule.onNodeWithTag("order_confirmation_screen").assertIsDisplayed()
    composeTestRule.onNodeWithTag("order_confirmation_order_id").assertIsDisplayed()
}
```

### 9.2 Macrobenchmark — Dedicated Module

```kotlin
// :macrobenchmark/src/androidTest
@RunWith(AndroidJUnit4::class)
class ProductListStartupBenchmark {
    @get:Rule val benchmarkRule = MacrobenchmarkRule()

    @Test fun startupToProductListVisible() = benchmarkRule.measureRepeated(
        packageName   = "com.myapp",
        metrics       = listOf(StartupTimingMetric(), FrameTimingMetric()),
        iterations    = 5,
        startupMode   = StartupMode.COLD
    ) {
        pressHome(); startActivityAndWait()
        device.wait(Until.hasObject(By.res("product_list_container")), 5_000)
    }
}
```

`testTagsAsResourceId = true` must be applied on a root ancestor composable in the app for `By.res()` to resolve Compose test tags.

### 9.3 Baseline Profiles — Automated Generation

```kotlin
@RunWith(AndroidJUnit4::class)
class ProductAppBaselineProfileGenerator {
    @get:Rule val rule = BaselineProfileRule()

    @Test fun generate() = rule.collect(packageName = "com.myapp") {
        pressHome(); startActivityAndWait()
        device.wait(Until.hasObject(By.res("product_list_container")), 5_000)
    }
}
```

**Freshness automation:** Baseline Profile generation runs automatically on a weekly schedule against the `release` branch via CI. If the generated `.prof` file differs from the committed baseline by more than a configured threshold, the CI pipeline opens a bot PR with the updated profile and links it to the Macrobenchmark comparison report. Profile staleness is therefore detected and surfaced automatically rather than tracked manually in a release checklist.

```yaml
# .github/workflows/baseline-profile.yml
on:
  schedule:
    - cron: '0 2 * * 1'  # Weekly, Monday 02:00
  push:
    branches: [release/**]

jobs:
  generate-profile:
    steps:
      - run: ./gradlew :macrobenchmark:generateBaselineProfile
      - uses: peter-evans/create-pull-request@v5
        with:
          title: "chore: update Baseline Profile (automated)"
          branch: "automated/baseline-profile-update"
```

### 9.4 Performance Gates — Baseline-Relative

```
P90 startup regression > 10% vs baseline  → automatic P2 Jira ticket
P90 startup regression > 20% vs baseline  → release promotion blocker
Frame timing jank regression > 10%        → P2 Jira ticket
Frame timing jank regression > 20%        → release promotion review
```

Advisory absolute thresholds are recorded in the Macrobenchmark baseline file as anomaly signals only, not gates.

---

## 10. Flakiness Management

### 10.1 Root Cause Classification

| Category | Cause | Mitigation |
|---|---|---|
| Compose animation timing | Assertion before Compose-internal transition completes | `mainClock.autoAdvance = false` + `advanceTimeBy(durationMs)` |
| System animation | OS-level transitions not suppressed | `animationsDisabled = true` in `testOptions` |
| Async data race | Assertion before `StateFlow` reaches composable | `waitForIdle()` after every state-triggering action |
| Debounced operation | `waitForIdle()` resolves before debounce fires | Register `IdlingResource` tied to debounce completion |
| LazyList node count | `onAllNodesWithTag` returns only composed nodes | Assert total count in Lane 1; assert visibility in Lanes 2/3 |
| Process state bleed | Singleton/DB state persists between test methods | Orchestrator `clearPackageData = true` (per invocation) |
| JVM static state leak | Dispatcher/fake/shadow state shared in same JVM fork | Reset all mutable state in `@Before`/`@After`; no companion singletons in fakes |
| Dispatcher timing | `viewModelScope` on `Dispatchers.Main` differs in test | Inject `CoroutineDispatcher` via constructor; replace with `TestDispatcher` |
| `LaunchedEffect` re-trigger | Effect does not fire on same key recomposition | One `setContent` call per test method |
| ModalBottomSheet partial reveal | Sheet "displayed" at intermediate animation offset | `waitUntil` with position threshold or explicit clock advance |
| Room off-main-thread write | Background Room write completes after Compose idle | Custom `IdlingResource` wired to Room transaction queue (see 10.3) |
| Infrastructure flakiness | Emulator boot failure, UiAutomator timeout, FTL noise | Infrastructure retry policy (see 10.4), separate from quarantine |

`Thread.sleep()` and `delay()` in test bodies are unconditionally prohibited.

### 10.2 `waitUntil` Timeout Tiers

Standard timeout tiers prevent ad-hoc timeouts and hanging CI jobs. A test requiring more than 5 seconds of `waitUntil` time is a testability smell — the underlying operation is too slow or the synchronisation mechanism is wrong.

| Tier | Timeout | Use Cases |
|---|---|---|
| Fast UI transition | `1_000` ms | Animation completion, visibility toggle, simple state change |
| Network / data load | `3_000` ms | Repository fetch, Room query, `StateFlow` propagation |
| Animation / debounce | `5_000` ms | Debounced search, complex shared element transition, slow loading indicator |
| Smell threshold | > `5_000` ms | Testability smell — `SLOW_WAITUNTIL` emitted by ARIA; investigate the root cause |

ARIA must not generate a `waitUntil` call without a timeout. ARIA must classify the timeout tier based on the operation type in the oracle and use the standard value.

### 10.3 Room Off-Main-Thread Write — IdlingResource

Compose's `ComposeTestRule` auto-integrates with Espresso's `IdlingResource`, but custom background threads writing to Room are invisible to the framework. If Lane 2 or Lane 3 tests fail with race conditions where data is written to Room off the main thread, a custom `IdlingResource` must be wired to the Room transaction queue.

```kotlin
class RoomTransactionIdlingResource(private val database: AppDatabase) : IdlingResource {
    private var callback: IdlingResource.ResourceCallback? = null

    override fun getName() = "RoomTransactionIdlingResource"

    override fun isIdleNow(): Boolean {
        val idle = !database.inTransaction()
        if (idle) callback?.onTransitionToIdle()
        return idle
    }

    override fun registerIdleTransitionCallback(callback: IdlingResource.ResourceCallback) {
        this.callback = callback
    }
}

// Register in test setup
@Before fun setup() {
    IdlingRegistry.getInstance().register(RoomTransactionIdlingResource(database))
}

@After fun tearDown() {
    IdlingRegistry.getInstance().unregister(roomIdlingResource)
}
```

ARIA emits a `ROOM_RACE_CONDITION_RISK` testability smell for screens whose manifest declares `networkDependency = true` and whose `FakeRepository` uses a real Room database rather than an in-memory list.

### 10.4 Infrastructure Retry Policy

Emulator boot failures, UiAutomator timeouts, and Firebase Test Lab infrastructure noise are not code flakiness. They must not trigger the quarantine policy. Lane 3 and Lane 4 tests are automatically retried up to 2 times on failure before the result is classified.

```yaml
# Firebase Test Lab — retry configuration
gcloud firebase test android run \
  --num-flaky-test-attempts=2 \
  ...
```

Classification rules:
- Test passes on retry 1 or 2 → counted as a pass; infrastructure retry metric incremented
- Test fails on all retries → final failure, subject to quarantine classification (Section 10.5)
- More than 20% of Lane 3 tests require a retry in a single CI run → CI infrastructure flagged as unstable; creates a P2 infrastructure Jira ticket separate from any code-level flakiness tickets

This separation ensures that infrastructure instability does not inflate the code flakiness metric and that code flakiness does not mask infrastructure degradation.

### 10.5 Quarantine Policy

A test is quarantined when it fails on the **final retry** in 2 of 10 CI runs without a code change.

1. Tag `@Ignore("FLAKY-{jira-id}")` immediately
2. Move to `connectedFlakyCandidateAndroidTest` Gradle task — excluded from all merge gates
3. Assign P2 in Jira, 5-business-day SLA for root cause resolution
4. If unresolved in 5 days: screen flagged in manifest as quality risk; manual QA sign-off required for next release containing that screen

### 10.6 Flaky Rate Visibility

Track and publish per sprint: quarantine queue size per lane, flaky rate per test method (30-day rolling), infrastructure retry rate (separate from code flakiness), mean time from quarantine to resolution, tests promoted from quarantine vs remaining open past SLA.

---

## 11. ARIA AI Generation Contract

### 11.1 Lane Selection Rules

```
LANE_1 when:
  target has no Android runtime import
  target is ViewModel, reducer, use case, validator, or DTO mapper
  can be constructed via constructor with fakes, SavedStateHandle, and TestDispatcher

LANE_2 when:
  target is @Composable accepting state + callbacks (state-hoisted)
  no real permission, NavHost, real IME, or lifecycle callback required
  assertions do not depend on pixel-bound visibility or window insets

LANE_3 when:
  manifest.deviceRisk has at least one true field
  OR target requires NavHost, back press, IME, permission, ActivityScenario, or real lifecycle

LANE_4 when:
  target spans two or more screens or measures startup/frame/scroll timing
  OR validates a journey requiring release-build confidence
```

### 11.2 Screen Manifest Contract

```json
{
  "screen": "ProductListScreen",
  "route": "ProductListRoute",
  "viewModel": "ProductListViewModel",
  "uiStates": ["Loading", "Success", "Empty", "Error", "CachedSuccess", "OfflineError"],
  "userActions": ["retry", "openDetail", "pullToRefresh", "search"],
  "navigationRoutes": {
    "entry": "productList",
    "exits": ["productDetail/{id}", "search"]
  },
  "selectors": {
    "productListContainer": "product_list_container",
    "productListItem":      "product_list_item",
    "retryButton":          "product_list_retry_button",
    "emptyState":           "product_list_empty_state",
    "offlineBanner":        "product_list_offline_banner"
  },
  "testDataFactory": "ProductTestData",
  "fakeRepository":  "FakeProductRepository",
  "diModule":        "ProductModule",
  "testDiModule":    "TestProductModule",
  "accessibilityProfile": {
    "meaningfulImages": {
      "product_image":  "Product image",
      "profile_avatar": "User profile picture"
    },
    "decorativeImages": ["background_pattern", "divider_icon"]
  },
  "localeVariants":         ["de_DE", "ar_SA"],
  "configurationVariants":  ["darkMode", "fontScale200", "rtl"],
  "snapshotRequired":       true,
  "snapshotStability":      "stable",
  "deviceRisk": {
    "requiresNavHost":            true,
    "requiresIme":                false,
    "requiresPermission":         false,
    "requiresActivityRecreation": true,
    "requiresDeepLink":           true,
    "requiresPredictiveBack":     false,
    "requiresOfflineSmoke":       true
  },
  "riskLevel":              "high",
  "businessCriticality":    "release_blocking",
  "owner":                  "mobile-checkout-team",
  "changedFeatureGate":     true,
  "criticalJourneys":       ["purchase", "refund"],
  "dataSensitivity":        "pii",
  "networkDependency":      true,
  "offlineSupported":       true,
  "knownFlakyAreas":        ["animation"],
  "minimumLaneRequired":    "Lane2",
  "maximumLaneAllowedInPR": "Lane3Smoke",
  "testPlacement": {
    "lane1":           "app/src/test/java",
    "lane2":           "app/src/test/java",
    "lane3":           "app/src/androidTest/java",
    "lane4Journey":    "app/src/androidTest/java",
    "lane4Benchmark":  "macrobenchmark/src/androidTest/java",
    "sharedTestUtils": "app/src/testFixtures/java"
  }
}
```

**Missing manifest fallback:** If ARIA encounters a screen with no manifest during the DISCOVER phase, it applies the following defaults and halts Lane 3 and Lane 4 generation:

```json
{
  "minimumLaneRequired":    "Lane1",
  "maximumLaneAllowedInPR": "Lane2",
  "changedFeatureGate":     false
}
```

ARIA emits a `MISSING_MANIFEST` testability smell with `ariaAction: "block_lane3_until_manifest_created"`. Lane 1 and Lane 2 generation proceeds with heuristic selector discovery, which is flagged as lower confidence in the generated test output.

### 11.3 Oracle Fingerprint — Duplicate Detection

The fingerprint includes locale and configVariant to prevent treating locale-specific tests as duplicates of each other.

```
{screen}|{uiState}|{action}|{positiveAssertion}|{negativeAssertion}|{sourceOfTruth}|{locale}|{configVariant}
```

Examples:

```
ProductListScreen|Error|tapRetry|product_list_container_visible|retry_button_absent|ProductListUiState.Success|default|default
ProductListScreen|Success|render|product_list_container_visible|offline_banner_absent|ProductListUiState.Success|de_DE|default
ProductListScreen|Success|render|product_list_container_visible|offline_banner_absent|ProductListUiState.Success|de_DE|darkMode
```

The `de_DE` + `default` config test and the `de_DE` + `darkMode` config test have different fingerprints and are both generated. The `de_DE` + `default` test and the `en_US` + `default` test have different fingerprints and are both generated. Only exact fingerprint matches are suppressed.

`locale` defaults to `"default"` (no locale override). `configVariant` defaults to `"default"` (no config override). Both are required fields in the fingerprint even when set to `"default"`.

### 11.4 Test Oracle Contract

```kotlin
/**
 * GIVEN:  FakeProductRepository throws IOException
 * WHEN:   ProductListScreen(state=Error) rendered; user taps product_list_retry_button
 * THEN:   product_list_container tag exists and is displayed
 * AND:    product_list_retry_button does not exist
 * SOURCE: ProductListUiState.Success with non-empty products list
 * LOCALE: default
 * CONFIG: default
 */
@Test
fun `error state retry resolves to success state`() { ... }
```

A test with only a positive assertion and no corresponding negative assertion is a partial oracle and is rejected by the acceptance gate.

### 11.5 Mutation Verification — Tiered Cost Model

**Tier 1 — PR Generation (cheap, mandatory):**
Generated test must fail at least one of: replace composable content with `Box {}`, remove click callback, or remove success content branch. Failure to fail any of these = rejected, regenerate with stricter oracle.

**Tier 2 — Nightly (full set):**
```
Mutation 1: Replace target composable content with Box {}
Mutation 2: Remove the primary success content from the rendered branch
Mutation 3: Remove the error or empty state branch entirely
Mutation 4: Invert enabled/disabled state of the primary interactive element
Mutation 5: Remove the click or action callback (replace with {})
Mutation 6: Change the navigation route target to a wrong destination
```
Any Tier 1 miss found in Tier 2 creates a `MUTATION-MISS` Jira ticket.

**Tier 3 — Suite Promotion (evidence stored):**
Mutation evidence report (which mutations ran, which failed, on which commit) is stored and linked in the PR description before a generated test is permanently merged.

### 11.6 Existing Test Inspection

Before generating:
1. Scan `src/test/` and `src/androidTest/` for tests targeting the same screen
2. Compute oracle fingerprints (including locale and configVariant) from existing tests; skip on match
3. Identify existing selector names; flag discrepancies against manifest `selectors`
4. Identify existing fakes, helpers, extension functions; reuse, do not regenerate
5. Flag ViewModel-coupled composables in existing `setContent {}` as testability smells

### 11.7 Testability Smell Output

```json
{
  "screen": "ProductListScreen",
  "testabilitySmells": [
    {
      "type": "VIEWMODEL_COUPLED_COMPOSABLE",
      "severity": "medium",
      "detail": "ProductListScreen accepts ProductListViewModel directly",
      "recommendation": "Split into ProductListRoute and ProductListScreen",
      "ariaAction": "generate_with_warning"
    },
    {
      "type": "CONSTRUCTOR_REQUIRES_HILT_IN_LANE1",
      "severity": "high",
      "detail": "ProductUseCaseImpl cannot be constructed without DI graph",
      "recommendation": "Extract constructor parameters to allow direct construction",
      "ariaAction": "block_lane1_generation_until_resolved"
    },
    {
      "type": "MISSING_MANIFEST",
      "severity": "high",
      "detail": "No manifest found for CheckoutScreen",
      "recommendation": "Create manifest at app/src/test/resources/manifests/CheckoutScreen.json",
      "ariaAction": "block_lane3_until_manifest_created"
    },
    {
      "type": "NO_CUSTOM_THEME_DETECTED",
      "severity": "low",
      "detail": "No AppTheme composable detected; falling back to MaterialTheme",
      "recommendation": "Verify MaterialTheme fallback is intentional for this project",
      "ariaAction": "generate_with_warning"
    },
    {
      "type": "ROOM_RACE_CONDITION_RISK",
      "severity": "medium",
      "detail": "FakeProductRepository uses real Room database; background write race likely",
      "recommendation": "Replace with in-memory list fake or add RoomTransactionIdlingResource",
      "ariaAction": "generate_with_warning"
    },
    {
      "type": "SLOW_WAITUNTIL",
      "severity": "medium",
      "detail": "Generated test requires waitUntil > 5000ms for search debounce",
      "recommendation": "Inject debounce delay as a constructor parameter; use TestCoroutineScheduler",
      "ariaAction": "generate_with_warning"
    }
  ]
}
```

`ariaAction` values:
- `generate_with_warning` — proceed; include smell in PR annotation
- `block_lane1_generation_until_resolved` — Lane 1 cannot be generated
- `block_lane3_until_manifest_created` — Lane 3 and Lane 4 halted; Lane 1/2 proceed with heuristic selectors
- `block_lane3_generation_until_resolved` — Lane 3 halted; Lane 1/2 proceed normally

### 11.8 Selector Policy and Tag Naming Convention

**Automation selectors** (ARIA-generated interaction and structural navigation):
Priority: `testTag` → `contentDescription` → visible text
Rationale: `testTag` is locale-stable. Use visible text selectors only when the text itself is the business assertion.

**Accessibility assertions** (semantic tree validation):
Priority: `contentDescription` → `text` → `role`
Rationale: `testTag` is not exposed to assistive technology.

**Tag naming convention:** All `testTag` values in the manifest must follow `snake_case` composed of the screen name prefix + element name, matching the composable function name and element purpose.

```
{screen_name}_{element_role}
{screen_name}_{sub_component}_{element_role}

Examples:
product_list_container         ← ProductListScreen root container
product_list_item              ← item in the list
product_list_retry_button      ← retry CTA
product_list_empty_state       ← empty state composable
product_detail_add_to_cart_button
checkout_submit_button
order_confirmation_order_id
```

Tags must be unique across the application. The manifest `selectors` map is the source of truth for all tags. ARIA must reject a manifest where any selector value matches a selector from a different screen manifest.

### 11.9 Generated Test Review Checklist

Before merging a generated test:
- Oracle is complete (Given/When/Then/And/Source/Locale/Config)
- Selector strategy matches policy (testTag for automation, semantic for accessibility)
- No `Thread.sleep()` or `delay()` in test body
- `waitForIdle()` present after every state-triggering action
- `waitUntil` timeout uses standard tier value (Section 10.2)
- Project theme composable used in every `setContent {}` block
- Mutation gate Tier 1 evidence confirmed
- Test is assigned to the correct lane, tagged correctly, and placed in the correct source set per `testPlacement`
- No duplicate oracle fingerprint in the existing suite
- `owner` from manifest assigned in PR review

---

## 12. CI/CD Pipeline and Quality Gates

### 12.1 Three Execution Modes

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MODE 1 — FAST PR GATE                                            (< 90s)     │
│ Lane 1: Logic & State (JUnit 5 JVM)                                          │
│ Lane 2: Compose Screen/Component (Robolectric + Paparazzi)                   │
│ GATE: Lane 1 = 100% pass                                                     │
│       Lane 2 = 100% pass, excluding explicitly quarantined tests             │
│       snapshotStability=stable: 0–0.1% auto-approve, 0.1–0.5% QA review,    │
│       >0.5% auto-block                                                       │
│       snapshotStability=new/theme_migration: explicit QA approval required   │
├──────────────────────────────────────────────────────────────────────────────┤
│ MODE 2 — SELECTIVE DEVICE GATE                                   (< 600s)    │
│ Lane 3: Device Interaction — changedFeatureGate=true or deviceRisk ≥1 true   │
│ Infrastructure retry: up to 2 automatic retries per test before quarantine   │
│ GATE (smoke/changed): 100% pass on final retry — hard block                  │
│ GATE (expanded): ≥ 95% pass — non-blocking, Jira-tracked                     │
│ >20% retry rate: CI infrastructure flagged as unstable — P2 Jira             │
├──────────────────────────────────────────────────────────────────────────────┤
│ MODE 3 — POST-MERGE RELEASE GATE           (async, trunk, real device)       │
│ Mode 3a: Lane 4 journey tests (instrumented, Orchestrator, real device)      │
│ Mode 3b: Lane 4 performance (:macrobenchmark, BenchmarkRunner, no Orchestr.) │
│ Mode 3c: Baseline Profile generation (weekly + release branch trigger)       │
│ GATE: Does not block feature PR merge                                        │
│       3a failure → P1 Jira, blocks release branch promotion                 │
│       3b regression > 20% vs baseline → release promotion blocker           │
│       3b regression 10–20% → P2 Jira, triaged before release cut            │
│       3c delta above threshold → bot PR with updated .prof file              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Quality Metrics by Lane

| Lane | Primary Gate Metric | Supporting Metrics |
|---|---|---|
| Lane 1 | 100% pass; 100% sealed state coverage | Line ≥ 90%, Branch ≥ 85% |
| Lane 2 | 100% pass; all `uiStates` rendered | Snapshot baseline stability by `snapshotStability` |
| Lane 3 smoke | 100% pass on final retry for changed/risk screens | Accessibility pass rate; retry rate |
| Lane 3 expanded | ≥ 95% pass (non-blocking) | Navigation route coverage; flaky rate |
| Lane 4 journeys | 100% declared `criticalJourneys` executed | Failure severity classification |
| Lane 4 perf | P90 regression < 10% vs baseline | Profile freshness (automated) |
| Cross-lane | Flaky rate < 2% (30-day rolling) | Quarantine queue ≤ 5 open items; infrastructure retry rate < 5% |

---

## 13. Android Concerns — Coverage Table

| Concern | Primary Lane | Requirement |
|---|---|---|
| ViewModel / use case logic | 1 | Constructor injection + fakes; no Hilt; `@ParameterizedTest` for matrix cases |
| `SavedStateHandle` | 1 | Direct `SavedStateHandle(mapOf(...))` construction; missing-argument edge case required |
| DTO/API mapping | 1 | `@ParameterizedTest` for nullable fields, enum fallbacks; date round-trips |
| Offline — logic | 1 | All offline/cache state transitions via fake repo |
| Robolectric limitations | 2 | `assertIsDisplayed()` = semantic only; IME/insets deferred to Lane 3; use `AppTheme` |
| Hilt DI wiring | 3 | `@TestInstallIn` module; `@HiltAndroidTest` in Lane 3 only |
| Network interception | 3 | `MockWebServer` via `TestNetworkModule`; no airplane mode toggling |
| Offline — rendering | 2 | Offline banner and CachedSuccess composable rendering |
| Offline — runtime wiring | 3 | One smoke test per `requiresOfflineSmoke = true` screen |
| IME / window insets | 3 | All IME-dependent layout assertions; Robolectric does not simulate insets |
| Locale / currency / dates | 2, 3 | Manifest `localeVariants`; new `Configuration(...)` copy; fingerprint includes locale |
| Permission grant/deny | 3 | One grant test + one deny/rationale test per permission type |
| Configuration change | 3 | `ActivityScenario.recreate()` for screens with user-editable state |
| Predictive back | 3 | Conditional: `requiresPredictiveBack=true` + API 35+ + critical/regressed |
| Visual snapshots | 2 | Scoped per Section 7.7; gate by `snapshotStability`; use `AppTheme` wrapper |
| Accessibility per state | 3 | `tryPerformAccessibilityChecks()` per major screen state; manifest-driven image assertions |
| Macrobenchmark / profiles | 4 | Dedicated `:macrobenchmark` module; automated weekly profile freshness |
| Failure capture | 3, 4 | Screenshot/video on failure; artifact linked in ARIA ANALYSE report |
| Room race condition | 2, 3 | `RoomTransactionIdlingResource` when Room used in fake; ARIA emits smell |
| `waitUntil` timeouts | All | Standard tier values; > 5s = `SLOW_WAITUNTIL` testability smell |
| Infrastructure retry | 3, 4 | Up to 2 retries before quarantine; > 20% retry rate = infrastructure P2 |
| Flaky test visibility | All | Published per sprint; code flakiness vs infrastructure retry tracked separately |
| Generated test ownership | All | `owner` from manifest assigned in PR review |
| Testability smells | All | Machine-readable ARIA output; `ariaAction` drives generation decision |
| Source-set placement | All | `testPlacement` in manifest; ARIA does not infer placement from class name |

---

*Review triggers: Compose major version upgrade, ARIA phase loop changes, new screen registered in NavGraph, Lane 3 pass rate below 90% for three consecutive CI runs, flaky rate exceeding 2% on 30-day rolling average, or infrastructure retry rate exceeding 5% for two consecutive weeks.*