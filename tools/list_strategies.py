# tools/list_strategies.py — List all registered strategies
from typing import Dict, Any
from core.session import Session
from strategy.registry import StrategyRegistry


def handle_list_strategies(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """List all registered strategy IDs and metadata from the manifest."""
    strategies = registry.list_strategies()
    return {"strategies": strategies}
