"""Agent registration example for the Water Quality Intelligence Platform."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class MCPServerConfig:
    name: str
    transport: str
    url: str


@dataclass
class AgentConfig:
    name: str
    description: str
    system_prompt_path: str
    model: str
    mcp_servers: list[MCPServerConfig]


DEFAULT_MCP_URL = os.getenv("WATER_RESEARCH_MCP_URL", "https://your-mcp-app.databricksapps.com/sse")

AGENT_CONFIG = AgentConfig(
    name="water-quality-intelligence-agent",
    description=(
        "Research copilot for water quality, treatment, watershed monitoring, "
        "and environmental sensing. Uses MCP tools for literature search, semantic retrieval, "
        "paper saving, and reading-plan tracking."
    ),
    system_prompt_path="agent/SYSTEM_PROMPT.md",
    model=os.getenv("AGENT_MODEL", "gpt-4.1-mini"),
    mcp_servers=[
        MCPServerConfig(
            name="water-research-copilot",
            transport="sse",
            url=DEFAULT_MCP_URL,
        )
    ],
)


if __name__ == "__main__":
    print(asdict(AGENT_CONFIG))
