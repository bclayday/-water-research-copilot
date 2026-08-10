"""
Entry point that detects whether we're the dashboard or MCP server
based on which app.yaml / directory we're running from.

If 'dashboard/templates/' exists in current dir → run Flask dashboard.
Otherwise → run MCP server.
"""

import os
from pathlib import Path

cwd = Path(os.getcwd())

if (cwd / "templates" / "index.html").exists():
    # We're in the dashboard/ directory — run Flask
    from app import app
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
else:
    # We're at repo root — run MCP server
    from mcp_server.research_mcp_server import mcp
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
