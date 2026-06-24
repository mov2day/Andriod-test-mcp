# tools/watch_repo.py — V2: File-change triggered re-analysis
import threading
from typing import Dict, Any
from pathlib import Path

from core.session import Session
from strategy.registry import StrategyRegistry
from core.logger import get_logger

logger = get_logger("tools.watch_repo")

# Module-level state for the watcher
_watcher_active = False
_watcher_lock = threading.Lock()


def handle_watch_repo(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """
    Start file-change monitoring for the repository.
    Since MCP tools are request-response, this tool sets up a background
    watcher that marks the session as stale when source files change.
    The invoking agent should re-run analyse_repo when notified.
    """
    global _watcher_active

    repo_path = arguments.get("repo_path", "")
    strategy_id = arguments.get("strategy_id", "")
    action = arguments.get("action", "start")  # "start" or "stop"

    if not repo_path:
        return {"error": "repo_path is required"}

    repo = Path(repo_path)
    if not repo.exists():
        return {"error": f"Path does not exist: {repo_path}"}

    if action == "stop":
        with _watcher_lock:
            _watcher_active = False
        logger.info("File watcher stopped")
        return {"watching": False, "message": "File watcher stopped."}

    # Try to use watchdog if available
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _ChangeHandler(FileSystemEventHandler):
            def __init__(self, sess: Session, lang: str):
                self._session = sess
                self._extensions = {
                    "python": {".py"},
                    "kotlin": {".kt", ".kts"},
                    "typescript": {".ts", ".tsx"},
                }.get(lang, {".py"})

            def on_modified(self, event):
                if event.is_directory:
                    return
                if Path(event.src_path).suffix in self._extensions:
                    self._session.mark_stale()
                    logger.info(f"File changed: {event.src_path} — session marked stale")

            def on_created(self, event):
                self.on_modified(event)

            def on_deleted(self, event):
                self.on_modified(event)

        try:
            strategy = registry.active()
            lang = strategy.target_language
        except Exception:
            lang = "python"

        handler = _ChangeHandler(session, lang)
        observer = Observer()
        observer.schedule(handler, str(repo), recursive=True)
        observer.daemon = True
        observer.start()

        with _watcher_lock:
            _watcher_active = True

        logger.info(f"File watcher started for {repo_path}")
        return {
            "watching": True,
            "repo_path": str(repo),
            "strategy_id": strategy_id,
            "message": (
                "File watcher active (watchdog). Source file changes will mark "
                "the session as stale. Re-run analyse_repo to refresh."
            ),
        }

    except ImportError:
        # Watchdog not installed — provide polling-based fallback info
        logger.warning("watchdog not installed. Install with: pip install qe-mcp[v2]")
        return {
            "watching": False,
            "message": (
                "watchdog package not installed. Install with: pip install qe-mcp[v2]\n"
                "Without watchdog, re-run analyse_repo manually after file changes."
            ),
        }
