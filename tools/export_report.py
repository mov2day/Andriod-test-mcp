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
    """Convert markdown content to a styled HTML report.

    Uses a basic built-in renderer (headings, lists, code blocks, bold,
    paragraphs) — no external dependency required.
    """
    import re as _re
    from html import escape

    lines = markdown_content.split("\n")
    html_parts: list[str] = []
    in_code_block = False
    in_list = False

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                html_parts.append("</code></pre>")
                in_code_block = False
            else:
                lang = line.strip().removeprefix("```").strip()
                html_parts.append(f'<pre><code class="language-{escape(lang)}">' if lang else "<pre><code>")
                in_code_block = True
            continue
        if in_code_block:
            html_parts.append(escape(line))
            continue

        stripped = line.strip()

        # Close open list if we're not on a list item
        if in_list and not stripped.startswith("- ") and not stripped.startswith("* "):
            html_parts.append("</ul>")
            in_list = False

        # Headings
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(level, 6)
            text = escape(stripped.lstrip("# ").strip())
            html_parts.append(f"<h{level}>{text}</h{level}>")
            continue

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item_text = escape(stripped[2:].strip())
            # Bold markers
            item_text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item_text)
            html_parts.append(f"<li>{item_text}</li>")
            continue

        # Empty line
        if not stripped:
            continue

        # Paragraph — apply inline formatting
        text = escape(stripped)
        text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = _re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        html_parts.append(f"<p>{text}</p>")

    if in_list:
        html_parts.append("</ul>")
    if in_code_block:
        html_parts.append("</code></pre>")

    body = "\n".join(html_parts)
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
  h1, h2, h3, h4 {{ color: #f0f6fc; margin-top: 24px; }}
  h1 {{ border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
  pre {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;
  }}
  code {{
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
  }}
  p code {{
    background: rgba(110,118,129,0.2);
    padding: 2px 6px;
    border-radius: 3px;
  }}
  ul {{ padding-left: 24px; }}
  li {{ margin: 4px 0; }}
  strong {{ color: #f0f6fc; }}
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
{body}
</body>
</html>"""
