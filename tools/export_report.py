# tools/export_report.py — V2: Write report to disk in JSON/Markdown/HTML
from typing import Dict, Any
from pathlib import Path
from datetime import datetime, timezone

from core.session import Session
from strategy.registry import StrategyRegistry
from tools.get_report import handle_get_report
from core.logger import get_logger

logger = get_logger("tools.export_report")


def handle_export_report(
    arguments: Dict[str, Any],
    session: Session,
    registry: StrategyRegistry,
) -> Dict[str, Any]:
    """Write report to disk in JSON, Markdown, or HTML format."""
    fmt = arguments.get("format", "json")
    output_path = arguments.get("output_path", "")

    if not output_path:
        return {"error": "output_path is required"}

    # Generate the report content
    if fmt in ("json", "markdown"):
        report_result = handle_get_report({"format": fmt}, session, registry)
        if "error" in report_result:
            return report_result
        content = report_result["report"]
    elif fmt == "html":
        # Generate markdown first, then wrap in HTML
        report_result = handle_get_report({"format": "markdown"}, session, registry)
        if "error" in report_result:
            return report_result
        md_content = report_result["report"]
        content = _wrap_html(md_content)
    else:
        return {"error": f"Unsupported format: {fmt}. Use 'json', 'markdown', or 'html'."}

    # Write to disk
    out = Path(output_path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json" and isinstance(content, dict):
            import json
            out.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
        else:
            out.write_text(str(content), encoding="utf-8")
    except Exception as e:
        return {"error": f"Failed to write report: {e}"}

    logger.info(f"Report exported to {output_path} ({fmt})")
    return {"exported": True, "path": str(out.resolve()), "format": fmt}


def _wrap_html(markdown_content: str) -> str:
    """Wrap markdown content in a basic HTML template with pre-formatted text."""
    # Simple HTML wrapper — no external markdown-to-html dependency
    escaped = (
        markdown_content
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QE-MCP Report</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    max-width: 960px;
    margin: 40px auto;
    padding: 0 20px;
    background: #0d1117;
    color: #e6edf3;
    line-height: 1.6;
  }}
  pre {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
  }}
  th, td {{
    border: 1px solid #30363d;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{ background: #161b22; }}
</style>
</head>
<body>
<pre>{escaped}</pre>
</body>
</html>"""
