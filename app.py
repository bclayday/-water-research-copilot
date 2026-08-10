"""
Unified entry point for Water Research Copilot apps.

Uses APP_MODE env var to determine which server to run:
  - APP_MODE=dashboard → Flask web UI
  - APP_MODE=mcp (or unset) → FastMCP server
"""

import os

APP_MODE = os.getenv("APP_MODE", "mcp")

if APP_MODE == "dashboard":
    import sys
    from pathlib import Path
    # Add dashboard dir to path so we can import app.py (Flask)
    dashboard_dir = Path(__file__).resolve().parent / "dashboard"
    sys.path.insert(0, str(dashboard_dir))
    os.chdir(dashboard_dir)

    from app import app  # noqa: E402
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
else:
    from mcp_server.research_mcp_server import mcp
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
