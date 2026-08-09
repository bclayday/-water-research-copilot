# Water Research Copilot Architecture

## Components

1. **OpenAlex broker (`mcp_server/research_broker.py`)**
   - Centralizes all HTTP traffic to OpenAlex
   - Reconstructs abstracts from inverted-index payloads
   - Normalizes work metadata for downstream use

2. **Lakebase data layer (`mcp_server/lakebase.py`)**
   - Pulls credentials from Databricks secrets or environment variables
   - Creates schema on boot
   - Provides query and write helpers for the MCP server and dashboard

3. **MCP server (`mcp_server/research_mcp_server.py`)**
   - Exposes seven research tools over SSE
   - Reads from OpenAlex and Lakebase
   - Writes collections, goals, and reading-progress updates back to Lakebase
   - Uses pgvector + sentence-transformers for semantic search

4. **Spark ingest pipeline (`pipeline/ingest_papers.py`)**
   - Pulls water-quality papers from OpenAlex
   - Uses Spark DataFrames to parse JSON and transform metadata
   - Loads papers, authors, and authorship edges into Lakebase

5. **Embedding pipeline (`pipeline/embed_papers.py`)**
   - Reads papers without embeddings
   - Chunks abstracts into overlapping passages
   - Stores 384-dimensional vectors in pgvector for semantic retrieval

6. **Dashboard (`dashboard/app.py`)**
   - Flask UI for searching papers, saving collections, generating goals, and tracking reading status
   - Reuses the same broker and MCP tool logic so app and agent stay aligned

7. **Agent config (`agent/agent.py`)**
   - Provides an Agent Bricks-style configuration object
   - Points to the SSE MCP server and uses the documented system prompt

## Data Flow

OpenAlex API -> Spark ingest -> Lakebase papers/authors -> embedding job -> pgvector index -> MCP tools / dashboard / agent

## Why this design

- Single broker keeps third-party API logic isolated.
- Lakebase helpers keep schema and connectivity consistent.
- Spark satisfies structured ETL requirements.
- pgvector enables AI-powered retrieval over unstructured abstracts.
- MCP tools provide a clean contract for both dashboard actions and agent automation.
