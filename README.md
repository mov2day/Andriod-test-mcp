# QE-MCP: Quality Enforcement Model Context Protocol Server

QE-MCP is a Python-based MCP (Model Context Protocol) server that enforces configurable Quality Assurance automation strategies. It acts as an intelligent bridge between AI coding agents and your codebase, ensuring that generated tests adhere to strict, repository-specific architectural and testing standards.

## Overview

Unlike standard code generation, QE-MCP doesn't just write tests—it enforces a **prescriptive strategy**. By utilizing strategy plugins (like `python_pytest_v1` or `android_compose_v1`), it guides AI agents to:
1. **Analyze** source code based on specific heuristics.
2. **Determine** exactly what tests need to be written (test lanes, coverage thresholds).
3. **Generate** prescriptive test plans using Given/When/Then oracles.
4. **Validate** the generated test code against naming conventions, architectural boundaries, and minimum assertion counts.
5. **Enforce** quality gates before code can be accepted.

## Features

### V1 Core Tools
*   **`list_strategies` & `load_strategy`**: Manage active testing strategies.
*   **`analyse_repo`**: Scans the repository, pairs source files with test files, computes coverage gaps, and produces an AI-ready prompt for deep semantic analysis.
*   **`generate_test_plan`**: Creates a prescriptive `TC-001..N` test plan for a specific file based on the strategy's oracle rules.
*   **`get_generation_brief`**: Assembles a comprehensive, strategy-specific prompt that instructs an AI agent exactly how to write the tests.
*   **`validate_tests`**: Runs a 7-layer validation (Syntax, Naming, Oracle completeness, Assertions, Lane compliance, bare assert checks, and skip limits) on generated tests.
*   **`enforce`**: A hard quality gate that runs analysis and validation, failing if coverage thresholds or architectural rules are breached.
*   **`get_report`**: Generates a detailed JSON or Markdown session report.

### V2 Extension Tools
*   **`analyse_dependencies`**: Computes import graphs and module coupling scores (currently optimized for Python).
*   **`diff_coverage`**: PR-scoped gap analysis using `git diff` to only enforce coverage on changed files.
*   **`export_report`**: Exports the quality report to disk as JSON, Markdown, or HTML.
*   **`watch_repo`**: Uses `watchdog` to monitor file changes and mark session states as stale.

## Built-in Strategies

1.  **`python_pytest_v1`**: A Python-based strategy enforcing `pytest` best practices. It uses AST parsing to classify services, repositories, and utilities, enforcing strict oracle fields based on the component type.
2.  **`android_compose_v1`**: A highly advanced strategy for Android Compose projects. It enforces a 4-lane testing model (Unit, Integration, Contract, E2E) and classifies Kotlin files (ViewModels, Composables, Navigation) using heuristics, flagging testability smells like coupled ViewModels or infinite animations.

## Getting Started

### Prerequisites
*   Python 3.11+
*   An MCP-compatible client or AI Agent framework

### Installation

1.  Clone the repository:
    ```bash
    git clone <repository_url>
    cd Andriod-test-mcp
    ```

2.  Install dependencies:
    ```bash
    pip install mcp pydantic pyyaml
    # For V2 file watching features:
    pip install watchdog
    ```

### Running the Server

Start the MCP server using standard I/O transport:
```bash
python server.py
```
This allows your MCP client to connect to it as a standard local MCP server.

## How to Use with an AI Agent

1.  **Initialize**: The agent calls `load_strategy` with the appropriate strategy (e.g., `android_compose_v1`).
2.  **Analyze**: The agent calls `analyse_repo` to find gaps in the codebase.
3.  **Plan**: For a file missing tests, the agent calls `generate_test_plan` providing behavioral context.
4.  **Brief**: The agent gets instructions via `get_generation_brief`.
5.  **Generate**: The agent writes the test code based on the brief.
6.  **Validate**: The agent uses `validate_tests` to ensure the generated code passes all strategy rules.
7.  **Enforce**: Finally, `enforce` is called to ensure the entire repository meets the defined quality gates.

## Developing Custom Strategies

You can create custom strategies by inheriting from `BaseStrategy` in `strategy/base.py` and implementing the required abstract methods (`classify_source_file`, `validate_generated_test`, etc.). Register your new strategy in the `strategies.yaml` manifest.

---
*Built with [FastMCP](https://github.com/jlowin/fastmcp)*
