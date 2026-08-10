# Architecture Overview

## System diagram

```text
                    +-----------------------+
                    |  USGS NWIS API        |
                    |  OpenAlex API         |
                    +-----------+-----------+
                                |
                +---------------+----------------+
                |                                |
                v                                v
      +--------------------+           +--------------------+
      | ingest_usgs.py     |           | ingest_papers.py   |
      | Spark pipeline     |           | Spark pipeline     |
      +---------+----------+           +---------+----------+
                |                                |
                +---------------+----------------+
                                v
                      +--------------------+
                      | Lakebase / Postgres |
                      | research + water    |
                      +-----+----------+----+
                            |          |
                            |          +--------------------+
                            |                               |
                            v                               v
                 +-------------------+          +----------------------+
                 | Flask dashboard   |          | FastMCP server       |
                 | live + research   |          | research tools       |
                 +-------------------+          +----------------------+
                            |                               |
                            v                               v
                 +-------------------+          +----------------------+
                 | Human viewer      |          | Agent Bricks / AI    |
                 +-------------------+          +----------------------+
```

## Design notes

### Unified app entrypoint

`app.py` is dual-purpose:
- dashboard mode when `DATABRICKS_APP_NAME` contains `dashboard`
- MCP mode for everything else

### Medallion architecture for water monitoring

- **Bronze**: raw USGS JSON snapshots in `raw_readings`
- **Silver**: normalized reading records in `stg_readings`
- **Gold**: station health scoring in `mart_station_health`

### Research architecture

- OpenAlex provides paper metadata and abstract reconstruction input.
- Lakebase stores papers, authors, goals, collections, and progress.
- Offline embedding generation writes pgvector rows into `paper_embeddings`.
- FastMCP exposes retrieval and workflow tools to an agent.

### Why keep MCP server files unchanged

The existing `mcp_server/research_mcp_server.py`, `research_broker.py`, and `lakebase.py` were already working. Preserving them reduces regression risk while still meeting the capstone structure requirements.

## Operational flow

### Live monitoring
1. Dashboard requests USGS instant values directly for current display.
2. Batch ingestion job stores the same feed historically in Lakebase.
3. Anomaly logic writes alert rows to `water_anomalies`.
4. SQL marts summarize current station health.

### Research workflow
1. User searches literature in dashboard or through MCP.
2. OpenAlex results are normalized and optionally stored.
3. Offline embeddings enable semantic search over abstract chunks.
4. Agent tools let users save, organize, and track papers.
