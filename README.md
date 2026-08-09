# Water Research Copilot

Water Research Copilot is a Databricks AI capstone project for water-treatment and water-quality professionals. It helps users discover research papers from OpenAlex, build learning goals, generate structured reading plans, save papers into collections, and track progress with an AI agent backed by semantic search.

## Why OpenAlex

OpenAlex is a strong fit for this project because it is free, comprehensive, well-documented, and does not require an API key. It also supports a polite pool via `mailto`, which this project includes on every request.

## Architecture Diagram

```text
OpenAlex API
   |
   v
research_broker.py ---> ingest_papers.py (Spark ETL) ---> Lakebase tables
                                                     |
                                                     v
                                           embed_papers.py -> pgvector embeddings
                                                     |
                 +-----------------------------------+-------------------+
                 |                                                       |
                 v                                                       v
      research_mcp_server.py (7 tools over SSE)                dashboard/app.py
                 |
                 v
            agent/agent.py
```

## Project Structure

```text
water-research-copilot/
├── README.md
├── app.yaml
├── requirements.txt
├── .gitignore
├── mcp_server/
│   ├── research_mcp_server.py
│   ├── research_broker.py
│   ├── lakebase.py
│   ├── app.yaml
│   └── requirements.txt
├── dashboard/
│   ├── app.py
│   ├── templates/index.html
│   ├── app.yaml
│   └── requirements.txt
├── pipeline/
│   ├── ingest_papers.py
│   ├── embed_papers.py
│   └── schema.sql
├── agent/
│   ├── agent.py
│   └── SYSTEM_PROMPT.md
└── docs/
    └── ARCHITECTURE.md
```

## Schema Overview

Lakebase stores:
- users
- learning_goals
- papers
- authors
- paper_authors
- collections
- collection_papers
- reading_progress
- paper_embeddings

`pipeline/schema.sql` also enables the `vector` extension and creates an HNSW index for cosine similarity search.

## MCP Tools

1. `search_research(query, limit=10)`
   - Search OpenAlex for relevant water-quality papers.
2. `get_paper_details(paper_id)`
   - Return full normalized paper metadata.
3. `semantic_search(query, limit=5)`
   - Retrieve semantically similar papers from pgvector embeddings.
4. `save_to_collection(paper_id, collection_name, user_email)`
   - Save a paper into a user collection.
5. `create_reading_plan(topic, user_email, max_papers=5)`
   - Create a learning goal and reading-progress seed list.
6. `update_reading_status(paper_id, status, user_email, notes="")`
   - Update progress state and notes.
7. `get_reading_list(user_email)`
   - Return the user reading list with statuses and collections.

## Pipeline Flow

1. **Ingest**
   ```bash
   python pipeline/ingest_papers.py
   ```
   - Starts a Spark job with `SparkSession.builder.appName("WaterResearchIngest")`
   - Fetches water-quality papers from OpenAlex
   - Parses JSON with Spark DataFrames
   - Reconstructs abstracts and writes papers/authors to Lakebase

2. **Embed**
   ```bash
   python pipeline/embed_papers.py
   ```
   - Reads papers without embeddings
   - Chunks abstracts with overlap
   - Embeds chunks using `all-MiniLM-L6-v2`
   - Writes pgvector rows into `paper_embeddings`

3. **Search and interact**
   - Run the MCP server for AI tools
   - Run the dashboard for the user interface

## Lakebase Configuration

Set these environment variables directly, or store them in a Databricks secret scope and map them via `DATABRICKS_SECRET_SCOPE`:

- `LAKEBASE_HOST`
- `LAKEBASE_PORT` (optional, defaults to `5432`)
- `LAKEBASE_DB` (optional, defaults to `postgres`)
- `LAKEBASE_USER`
- `LAKEBASE_PASSWORD`
- `LAKEBASE_SSLMODE` (optional, defaults to `require`)

Optional secret-key overrides:
- `LAKEBASE_HOST_SECRET_KEY`
- `LAKEBASE_PORT_SECRET_KEY`
- `LAKEBASE_DB_SECRET_KEY`
- `LAKEBASE_USER_SECRET_KEY`
- `LAKEBASE_PASSWORD_SECRET_KEY`
- `LAKEBASE_SSLMODE_SECRET_KEY`

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the MCP server:

```bash
cd mcp_server
python research_mcp_server.py
```

Start the dashboard in another shell:

```bash
cd dashboard
python app.py
```

## Databricks Deployment

### App 1: MCP server
- Root app config: `app.yaml`
- Entrypoint: `mcp_server/research_mcp_server.py`
- Transport: SSE

### App 2: Dashboard
- App config: `dashboard/app.yaml`
- Entrypoint: `dashboard/app.py`

## Agent Configuration

`agent/agent.py` defines an Agent Bricks-style configuration object that:
- uses the documented system prompt
- registers the research MCP server over SSE
- supports read and write workflows through the tool layer

## Recommendation Logic

Recommendations blend three signals:
- lexical relevance from OpenAlex search results
- semantic similarity from abstract embeddings in pgvector
- ranking heuristics based on citation count and recency

Reading plans sort papers to surface high-impact, relevant, and newer works first.

## System Prompt and Guardrails

See `agent/SYSTEM_PROMPT.md`.

Key rules:
- always use tools for real paper data
- never fabricate findings
- cite title, authors, and year when discussing papers
- explain recommendations based on relevance, citations, and recency
- admit uncertainty instead of guessing

## Notes

- All HTTP calls to OpenAlex live in `mcp_server/research_broker.py`.
- The AI agent reads from and writes to Lakebase through the MCP tools.
- The dashboard supports search, collections, reading-list status updates, and goal generation.
