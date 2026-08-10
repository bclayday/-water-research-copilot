"""
Unified entry point for Water Research Copilot.

Uses DATABRICKS_APP_NAME (auto-set by Databricks) to determine which server to run:
  - App name contains 'dashboard' → Flask web UI
  - Otherwise → FastMCP server
"""

import os
import importlib.util
import sys
from pathlib import Path

APP_NAME = os.getenv("DATABRICKS_APP_NAME", "")
IS_DASHBOARD = "dashboard" in APP_NAME.lower()

if IS_DASHBOARD:
    here = Path(__file__).resolve().parent
    dashboard_dir = here / "dashboard"
    os.chdir(dashboard_dir)

    # Add mcp_server to path so dashboard can import shared modules
    mcp_dir = here / "mcp_server"
    sys.path.insert(0, str(mcp_dir))
    sys.path.insert(0, str(dashboard_dir))

    # Load dashboard/app.py explicitly (not root app.py)
    spec = importlib.util.spec_from_file_location("dashboard_app", dashboard_dir / "app.py")
    dashboard_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard_module)

    flask_app = dashboard_module.app
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
else:
    from mcp_server.research_mcp_server import mcp
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
