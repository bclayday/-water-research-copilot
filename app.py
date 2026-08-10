"""
Unified entry point for Water Research Copilot.

Uses DATABRICKS_APP_NAME (auto-set by Databricks) to determine which server to run:
  - App name contains 'dashboard' → Flask web UI
  - Otherwise → FastMCP server
"""

import os

APP_NAME = os.getenv("DATABRICKS_APP_NAME", "")
IS_DASHBOARD = "dashboard" in APP_NAME.lower()

if IS_DASHBOARD:
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    dashboard_dir = here / "dashboard"
    sys.path.insert(0, str(dashboard_dir))
    os.chdir(dashboard_dir)

    from app import app  # noqa: E402
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
else:
    from mcp_server.research_mcp_server import mcp
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
