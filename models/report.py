"""QE report models — structured output of scan / enforce runs."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LaneCoverageReport(BaseModel):
    """Coverage data for a single test lane."""

    lane: str
    required: bool
    threshold: float
    actual: float
    status: str = Field(
        ...,
        pattern=r"^(OK|BREACH|NOT_MEASURED)$",
        description="OK if actual >= threshold, BREACH if below, NOT_MEASURED if no data",
    )
    files_missing: List[str] = Field(default_factory=list)


class ViolationReport(BaseModel):
    """A single rule violation found during enforcement."""

    file: str
    rule: str
    severity: str = Field(
        ...,
        pattern=r"^(error|warning)$",
        description="Violation severity: error or warning",
    )
    line: int
    detail: str


class QEReport(BaseModel):
    """Top-level quality-engineering report emitted by the enforce step."""

    generated_at: datetime
    strategy_id: str
    strategy_version: str
    repo_path: str
    enforce_passed: Optional[bool] = None
    files_analysed: int
    test_files_found: int
    coverage: List[LaneCoverageReport] = Field(default_factory=list)
    violations: List[ViolationReport] = Field(default_factory=list)
    test_plans: List[Dict] = Field(default_factory=list)
    smells: List[Dict] = Field(default_factory=list)
    blockers: List[Dict] = Field(default_factory=list)
    warnings: List[Dict] = Field(default_factory=list)
