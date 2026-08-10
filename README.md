# Water Quality Intelligence Platform

A combined Databricks capstone that joins two product surfaces in one repo:

1. **Live Monitoring**: real-time Georgia water sensor monitoring using USGS NWIS, anomaly detection, and a medallion-style Lakebase pipeline.
2. **AI Research Agent**: OpenAlex-powered paper search, Lakebase storage, semantic search over abstracts, and an MCP server for an agent to search, save, and track papers.

## Architecture at a glance

- **Root Databricks App entrypoint**: `app.py`
  - If `DATABRICKS_APP_NAME` contains `dashboard`, it launches the Flask dashboard.
  - Otherwise it launches the FastMCP research server.
- **Dashboard**: live monitoring tab + research paper search tab.
- **MCP Server**: preserved working implementation in `mcp_server/`.
- **Lakebase**: stores research objects and water monitoring records.
- **Pipelines**:
  - `pipeline/ingest_usgs.py` for USGS real-time ingestion and anomaly detection.
  - `pipeline/ingest_papers.py` for OpenAlex ingestion.
  - `pipeline/embed_papers.py` for offline semantic embeddings.
- **SQL medallion layer**: `sql/01_medallion_pipeline.sql`
- **Agent configuration**: `agent/`

## Repo structure

```text
water-research-copilot/
├── app.py
├── app.yaml
├── requirements.txt
├── .gitignore
├── README.md
├── mcp_server/
│   ├── research_mcp_server.py
│   ├── research_broker.py
│   ├── lakebase.py
│   ├── app.yaml
│   └── requirements.txt
├── pipeline/
│   ├── schema.sql
│   ├── ingest_usgs.py
│   ├── ingest_papers.py
│   └── embed_papers.py
├── agent/
│   ├── agent.py
│   └── SYSTEM_PROMPT.md
├── sql/
│   └── 01_medallion_pipeline.sql
└── docs/
    └── ARCHITECTURE.md
```

## Dashboard features

### Live Monitoring tab

Uses the public USGS NWIS instant values endpoint:

- Stations:
  - `02394682` Richland Creek at Old Dallas Rd, Dallas, GA
  - `02334430` Chattahoochee River at Buford Dam, Buford, GA
  - `02388985` Russell Creek near Dawsonville, GA
  - `02389150` Etowah River at GA 9, Dawsonville, GA
  - `02334480` Richland Creek at Suwanee Dam Rd, Buford, GA
- Parameters:
  - `00010` water temperature, converted from °C to °F
  - `00400` pH
  - `63680` turbidity
  - `00300` dissolved oxygen
  - `00060` flow/discharge
  - `00095` specific conductance

Thresholds used in dashboard and ingestion anomaly logic:

- **pH**
  - red: `< 6.5` or `> 8.5`
  - yellow: `6.5-6.8` or `8.0-8.5`
  - green: otherwise
- **Turbidity**
  - red: `> 10 FNU`
  - yellow: `> 5 FNU`
  - green: otherwise
- **Dissolved oxygen**
  - red: `< 4 mg/L`
  - yellow: `< 5 mg/L`
  - green: otherwise

The dashboard renders:
- a header, tabs, and dark theme UI
- a Georgia station map panel with colored markers
- station cards with all six measurements
- last updated timestamp
- USGS update note

### Research Papers tab

Uses OpenAlex search directly from the Flask app for quick interactive discovery:
- search box
- title
- authors
- publication year
- citation count
- abstract preview
- DOI link

## Databricks app behavior

The root app uses:

```python
DATABRICKS_APP_NAME
```

Rules:
- If the app name includes `dashboard`, Flask mode runs.
- Otherwise MCP mode runs.

This allows one repo to back two deployment targets using the same root entrypoint.

## Requirements

### Root `requirements.txt`

Kept minimal for Databricks Apps:

```txt
flask==3.0.3
requests==2.31.0
```

### `mcp_server/requirements.txt`

```txt
fastmcp>=2.10.6
requests==2.32.3
psycopg2-binary==2.9.9
databricks-sdk>=0.57.0
```

Note: PySpark and sentence-transformers are intentionally excluded from root app dependencies. Those are used only in jobs, notebooks, or offline processing.

## Database schema

`pipeline/schema.sql` contains:
- research tables for users, papers, authors, goals, collections, reading progress, and embeddings
- water tables for stations, readings, and anomaly events
- `vector` extension enablement for semantic search

## Pipeline overview

### 1) USGS ingest

`pipeline/ingest_usgs.py`
- creates a Spark session
- fetches the USGS real-time feed
- parses and explodes time series in Spark
- inserts readings into `water_readings`
- upserts reference station data into `water_stations`
- detects threshold-based anomalies and writes `water_anomalies`

### 2) OpenAlex paper ingest

`pipeline/ingest_papers.py`
- creates a Spark session
- queries OpenAlex for configurable water research topics
- normalizes records
- writes paper metadata into the existing research schema

### 3) Offline embedding generation

`pipeline/embed_papers.py`
- reads papers lacking embeddings
- chunks abstracts
- embeds text with `sentence-transformers/all-MiniLM-L6-v2`
- writes vectors into `paper_embeddings`

## Agent and MCP layer

The MCP server in `mcp_server/research_mcp_server.py` is preserved and provides tools for:
- paper search
- paper details
- semantic search
- save to collection
- create reading plan
- update reading status
- get reading list

The `agent/` folder documents how to register the MCP server inside Databricks Agent Bricks or another compatible agent runtime.

## Deploying

### Dashboard app

Set the Databricks app name so it contains `dashboard`, then deploy with root `app.py`.

### MCP app

Set a non-dashboard app name, install `mcp_server/requirements.txt`, and run the same root entrypoint or the dedicated `mcp_server/app.yaml`.

### Lakebase configuration

The preserved `mcp_server/lakebase.py` looks for:
1. `LAKEBASE_URL`
2. Databricks secret scope `database`, key `lakebase-url`
3. `LAKEBASE_URL_B64`

## Local verification

```bash
python3 -m py_compile app.py
```

Optional manual run:

```bash
DATABRICKS_APP_NAME=water-dashboard python3 app.py
```

## Capstone coverage

This repo now demonstrates all required pillars:

1. **Spark pipeline**: USGS and OpenAlex ingestion scripts
2. **Third-party API**: USGS NWIS + OpenAlex
3. **Unstructured data**: paper abstracts + vector embeddings
4. **Databricks App**: Flask dashboard
5. **AI Agent**: MCP tools + agent configuration

## Notes

- The root dashboard is dependency-light for Databricks Apps.
- The research backend remains intact to avoid breaking a known-good MCP implementation.
- The semantic search path depends on `paper_embeddings` being populated offline.
