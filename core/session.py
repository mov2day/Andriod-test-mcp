"""In-memory session state for a single QE-MCP run.

Stores scan results, test plans, validation results, and enforce
outcome so that MCP tool calls within a session can share state
without a database.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class Session:
    """Lightweight in-memory state container for one QE session."""

    def __init__(self) -> None:
        self.active_strategy_id: Optional[str] = None
        self.scan_results: Dict[str, Any] = {}
        self.test_plans: Dict[str, Any] = {}          # keyed by plan_id
        self.validation_results: List[Dict[str, Any]] = []
        self.enforce_result: Optional[Dict[str, Any]] = None
        self._stale: bool = False

    # -- mutators -----------------------------------------------------------

    def store_scan(self, results: Dict[str, Any]) -> None:
        """Store scan / classification results."""
        self.scan_results = results

    def store_plan(self, plan: Dict[str, Any]) -> None:
        """Store a test plan, keyed by its ``plan_id``."""
        plan_id = plan.get("plan_id")
        if plan_id is None:
            raise ValueError("Plan dict must contain a 'plan_id' key")
        self.test_plans[plan_id] = plan

    def store_validation(self, result: Dict[str, Any]) -> None:
        """Append a validation result."""
        self.validation_results.append(result)

    def store_enforce(self, result: Dict[str, Any]) -> None:
        """Store the enforcement outcome."""
        self.enforce_result = result

    # -- accessors ----------------------------------------------------------

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored plan by ID, or ``None``."""
        return self.test_plans.get(plan_id)

    # -- lifecycle ----------------------------------------------------------

    def reset(self) -> None:
        """Clear all session state."""
        self.active_strategy_id = None
        self.scan_results = {}
        self.test_plans = {}
        self.validation_results = []
        self.enforce_result = None
        self._stale = False

    def mark_stale(self) -> None:
        """Mark the session scan as stale (files have changed on disk)."""
        self._stale = True

    @property
    def is_stale(self) -> bool:
        """True if source files changed since last scan."""
        return self._stale

