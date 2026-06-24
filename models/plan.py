"""QE test-plan models — structured test case and plan definitions."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """A single test case within a test plan."""

    id: str
    name: str
    lane: str
    priority: str
    method_under_test: str
    given: str
    when: str
    then: str
    expected_state: Optional[Dict] = None
    oracle_fields_required: List[str] = Field(default_factory=list)
    mutation_sensitive: bool = False


class TestPlan(BaseModel):
    """A test plan covering one source file, produced by the plan step."""

    plan_id: str
    strategy_id: str
    source_file: str
    classification: Dict
    test_cases: List[TestCase] = Field(default_factory=list)
    coverage_targets: Dict[str, int] = Field(default_factory=dict)
    generation_brief_ready: bool = False
