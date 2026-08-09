from __future__ import annotations

from pathlib import Path

SYSTEM_PROMPT = Path(__file__).with_name("SYSTEM_PROMPT.md").read_text()

AGENT_CONFIG = {
    "name": "water-research-copilot-agent",
    "description": "AI research copilot for water quality literature discovery and reading-plan management.",
    "system_prompt": SYSTEM_PROMPT,
    "mcp_servers": [
        {
            "name": "water-research-mcp",
            "transport": "sse",
            "url": "http://127.0.0.1:8000/sse",
        }
    ],
}


if __name__ == "__main__":
    print(AGENT_CONFIG)
