"""
MCP Server entry point — runs the FastMCP weather/prediction server.
"""

import os

from mcp_server.research_mcp_server import mcp

if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
