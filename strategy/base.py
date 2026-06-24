"""Base strategy ABC and supporting dataclasses for QE-MCP.

Every pluggable test-generation strategy inherits from BaseStrategy and
implements its abstract interface.  The dataclasses here define the
vocabulary shared across all strategies.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestLaneType(Enum):
    """Categories of test lanes that a strategy can mandate."""

    UNIT = "unit"
    INTEGRATION = "integration"
    CONTRACT = "contract"
    E2E = "e2e"
    PERFORMANCE = "performance"


# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------

@dataclass
class TestLane:
    """Describes a single test lane (e.g. unit, integration)."""

    lane_type: TestLaneType
    required: bool
    file_glob: str
    coverage_threshold: float
    max_allowed_skips: int = 0


@dataclass
class NamingConvention:
    """File and method naming patterns expected by the strategy."""

    test_file_pattern: str
    test_method_pattern: str


@dataclass
class BehavioralSpec:
    """Defines what constitutes a meaningful assertion for a source class type."""

    source_class_type: str
    required_spec_fields: List[str]
    required_assertions_min: int = 1
    mutation_sensitive: bool = False


@dataclass
class SourceClassification:
    """Result of analysing a single source file."""

    class_type: str
    complexity_score: float
    testability_issues: List[str]
    required_lanes: List[TestLaneType]
    ast_metrics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base strategy
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    """Contract that every QE strategy plug-in must satisfy."""

    # -- identity properties ------------------------------------------------

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique strategy identifier (e.g. ``python_pytest_v1``)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string of the strategy."""
        ...

    @property
    @abstractmethod
    def target_language(self) -> str:
        """Programming language this strategy targets (e.g. ``python``)."""
        ...

    @property
    @abstractmethod
    def target_framework(self) -> str:
        """Test framework this strategy targets (e.g. ``pytest``)."""
        ...

    # -- abstract methods ---------------------------------------------------

    @abstractmethod
    def get_test_lanes(self) -> List[TestLane]:
        """Return the test lanes defined by this strategy."""
        ...

    @abstractmethod
    def get_naming_conventions(self) -> List[NamingConvention]:
        """Return naming conventions for test files and methods."""
        ...

    @abstractmethod
    def get_behavioral_specs(self) -> List[BehavioralSpec]:
        """Return spec rules for assertion quality enforcement."""
        ...

    @abstractmethod
    def classify_source_file(
        self,
        file_path: str,
        content: str,
    ) -> SourceClassification:
        """Classify a source file and produce its test-relevant metadata."""
        ...

    @abstractmethod
    def build_generation_brief(
        self,
        classification: SourceClassification,
        user_context: Dict[str, Any],
        file_path: str,
        test_plan: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Build a generation brief suitable for an LLM test-writer."""
        ...

    @abstractmethod
    def validate_generated_test(
        self,
        test_content: str,
        source_classification: SourceClassification,
    ) -> Dict[str, Any]:
        """Validate that generated test content meets strategy rules.

        Returns a dict with at least ``valid: bool`` and ``issues: List[str]``.
        """
        ...
