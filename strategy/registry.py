"""Strategy registry — loads, validates, and manages strategy plug-ins.

The registry reads ``strategies.yaml`` and dynamically imports strategy
modules on demand.  A loaded strategy is validated against the base
contract before it becomes available.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from strategy.base import BaseStrategy


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class StrategyLoadError(Exception):
    """Raised when a strategy cannot be loaded or fails contract validation."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class StrategyRegistry:
    """Discovers, loads, and validates strategy plug-ins."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        if manifest_path is None:
            # Default: strategies.yaml next to the project root
            manifest_path = Path(__file__).resolve().parent.parent / "strategies.yaml"
        self._manifest_path = Path(manifest_path)
        self._manifest: Dict[str, Any] = self._read_manifest()
        self._strategies: Dict[str, BaseStrategy] = {}
        self._active_id: Optional[str] = None

    # -- public API ---------------------------------------------------------

    def load(self, strategy_id: str) -> BaseStrategy:
        """Load a strategy by *strategy_id*, validate its contract, and set it active.

        Raises :class:`StrategyLoadError` on any failure.
        """
        entry = self._manifest.get("strategies", {}).get(strategy_id)
        if entry is None:
            raise StrategyLoadError(f"Strategy '{strategy_id}' not found in manifest")

        if not entry.get("enabled", False):
            raise StrategyLoadError(f"Strategy '{strategy_id}' is disabled in manifest")

        module_path = self._manifest_path.parent / entry["module_path"]
        if not module_path.exists():
            raise StrategyLoadError(
                f"Module file not found for strategy '{strategy_id}': {module_path}"
            )

        class_name: str = entry["class_name"]
        strategy = self._import_strategy(strategy_id, module_path, class_name)
        self._validate_contract(strategy, strategy_id)
        self._validate_classify_is_pure(strategy, strategy_id)

        self._strategies[strategy_id] = strategy
        self._active_id = strategy_id
        return strategy

    def active(self) -> BaseStrategy:
        """Return the currently active strategy.

        Raises :class:`StrategyLoadError` if no strategy has been loaded yet.
        """
        if self._active_id is None or self._active_id not in self._strategies:
            raise StrategyLoadError("No active strategy — call load() first")
        return self._strategies[self._active_id]

    def list_strategies(self) -> List[Dict[str, Any]]:
        """Return summary dicts for every strategy declared in the manifest."""
        results: List[Dict[str, Any]] = []
        for sid, entry in self._manifest.get("strategies", {}).items():
            info: Dict[str, Any] = {
                "id": sid,
                "enabled": entry.get("enabled", False),
            }
            # If the strategy is already loaded, include richer metadata.
            if sid in self._strategies:
                s = self._strategies[sid]
                info.update(
                    {
                        "name": s.name,
                        "version": s.version,
                        "language": s.target_language,
                    }
                )
            results.append(info)
        return results

    # -- internal helpers ---------------------------------------------------

    def _read_manifest(self) -> Dict[str, Any]:
        """Parse the YAML manifest file.

        Supports both list-format and dict-format under the 'strategies' key.
        List entries are keyed by their 'id' field.
        """
        if not self._manifest_path.exists():
            raise StrategyLoadError(f"Manifest not found: {self._manifest_path}")
        with open(self._manifest_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict) or "strategies" not in data:
            raise StrategyLoadError("Invalid manifest: missing 'strategies' key")

        # Normalise list format → dict keyed by id
        raw = data["strategies"]
        if isinstance(raw, list):
            by_id: Dict[str, Any] = {}
            for entry in raw:
                sid = entry.get("id")
                if sid:
                    by_id[sid] = entry
            data["strategies"] = by_id

        return data

    @staticmethod
    def _import_strategy(
        strategy_id: str,
        module_path: Path,
        class_name: str,
    ) -> BaseStrategy:
        """Dynamically import a module and instantiate the strategy class."""
        module_name = f"strategy.plugins.{strategy_id}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise StrategyLoadError(
                f"Cannot create module spec for '{strategy_id}' from {module_path}"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise StrategyLoadError(
                f"Failed to execute module for '{strategy_id}': {exc}"
            ) from exc

        klass = getattr(module, class_name, None)
        if klass is None:
            raise StrategyLoadError(
                f"Class '{class_name}' not found in module for '{strategy_id}'"
            )

        try:
            instance = klass()
        except Exception as exc:
            raise StrategyLoadError(
                f"Failed to instantiate '{class_name}' for '{strategy_id}': {exc}"
            ) from exc

        if not isinstance(instance, BaseStrategy):
            raise StrategyLoadError(
                f"'{class_name}' does not inherit from BaseStrategy"
            )
        return instance

    @staticmethod
    def _validate_contract(strategy: BaseStrategy, strategy_id: str) -> None:
        """Assert that the loaded strategy satisfies the minimal contract."""
        if not isinstance(strategy.id, str) or not strategy.id:
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' contract violation: 'id' must be a non-empty str"
            )

        if not isinstance(strategy.target_language, str) or not strategy.target_language:
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' contract violation: "
                "'target_language' must be a non-empty str"
            )

        lanes = strategy.get_test_lanes()
        if not lanes:
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' contract violation: "
                "get_test_lanes() must return at least one lane"
            )

        if not any(lane.required for lane in lanes):
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' contract violation: "
                "at least one lane must be required"
            )

    @staticmethod
    def _validate_classify_is_pure(
        strategy: BaseStrategy,
        strategy_id: str,
        timeout_seconds: float = 2.0,
    ) -> None:
        """Run classify_source_file with a trivial input and verify it returns
        within *timeout_seconds* without side-effects (best-effort check).
        """
        result_box: List[Any] = []
        error_box: List[Exception] = []

        def _run() -> None:
            try:
                result = strategy.classify_source_file("<test>", "# empty")
                result_box.append(result)
            except Exception as exc:  # noqa: BLE001
                error_box.append(exc)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout_seconds)

        if t.is_alive():
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' classify_source_file() did not complete "
                f"within {timeout_seconds}s — potential side-effect or blocking call"
            )

        if error_box:
            raise StrategyLoadError(
                f"Strategy '{strategy_id}' classify_source_file() raised an error "
                f"during purity check: {error_box[0]}"
            )
