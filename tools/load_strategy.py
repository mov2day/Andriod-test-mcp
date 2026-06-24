# tools/load_strategy.py — Validate contract and activate a strategy plugin
from typing import Dict, Any
from core.session import Session
from strategy.registry import StrategyRegistry, StrategyLoadError
from core.logger import get_logger

logger = get_logger("tools.load_strategy")


def handle_load_strategy(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """Validate contract and activate a strategy plugin."""
    strategy_id = arguments.get("strategy_id", "")
    if not strategy_id:
        return {"error": "strategy_id is required", "detail": "Provide a valid strategy_id"}

    try:
        strategy = registry.load(strategy_id)
        session.active_strategy_id = strategy_id
        logger.info(f"Strategy loaded: {strategy_id}")
        return {
            "loaded": True,
            "strategy_meta": {
                "id": strategy.id,
                "name": strategy.name,
                "version": strategy.version,
                "language": strategy.target_language,
                "framework": strategy.target_framework,
            },
        }
    except StrategyLoadError as e:
        logger.error(f"Strategy load failed: {e}")
        return {"loaded": False, "error": str(e)}
