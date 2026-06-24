# tools/router.py — Tool dispatch router
from typing import Callable, Dict, Any

from core.session import Session
from strategy.registry import StrategyRegistry
from core.logger import get_logger

logger = get_logger("tools.router")

# Type alias for tool handlers
ToolHandler = Callable[[Dict[str, Any], Session, StrategyRegistry], Dict[str, Any]]


class ToolRouter:
    """
    Maps MCP tool name strings to handler functions.
    Each handler receives (arguments, session, registry) and returns a dict.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler_fn: ToolHandler) -> None:
        """Register a handler for a given tool name."""
        self._handlers[tool_name] = handler_fn
        logger.debug(f"Registered tool handler: {tool_name}")

    def dispatch(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session: Session,
        registry: StrategyRegistry,
    ) -> Dict[str, Any]:
        """Look up and call the handler for the given tool name."""
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(self._handlers.keys())}")
        logger.info(f"Dispatching tool: {tool_name}")
        try:
            return handler(arguments, session, registry)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e), "detail": f"Tool '{tool_name}' raised {type(e).__name__}"}

    @property
    def registered_tools(self) -> list:
        return list(self._handlers.keys())
