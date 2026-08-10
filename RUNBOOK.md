# RUNBOOK

## Overview

This repo supports two modes from the same root entrypoint:

- **Dashboard mode**: Flask UI for live USGS monitoring plus OpenAlex search
- **MCP mode**: FastMCP research server for agent tools

Mode is selected by `DATABRICKS_APP_NAME`:

- contains `dashboard` -> Flask dashboard
- anything else -> MCP server

## Local setup

### 1. Dashboard mode

Install the minimal root dependencies:

```bash
pip install -r requirements.txt
DATABRICKS_APP_NAME=water-dashboard python app.py
```

Open `http://localhost:8000`.

### 2. MCP mode

Install MCP dependencies:

```bash
pip install -r mcp_server/requirements.txt
export LAKEBASE_URL=postgres://...
python app.py
```

Optional env vars:

- `DATABRICKS_APP_PORT` or `PORT`
- `LAKEBASE_URL`
- `LAKEBASE_URL_B64`
- `OPENALEX_MAILTO`
- `MIN_PUBLICATION_YEAR`

## Pipeline jobs

### USGS ingestion

```bash
python pipeline/ingest_usgs.py
```

What it does:

- retries 429/5xx calls with exponential backoff
- stores a Bronze raw JSON snapshot in `raw_readings`
- parses Silver readings into `water_readings`
- skips duplicate `(site_id, parameter_code, reading_time)` rows
- writes anomalies into `water_anomalies`

### OpenAlex ingestion

```bash
python pipeline/ingest_papers.py
```

What it does:

- retries transient OpenAlex errors
- pages with OpenAlex cursors
- limits ingestion to recent papers (`publication_year >= 2021` by default)
- upserts paper and author metadata into Lakebase

### Embeddings

```bash
python pipeline/embed_papers.py
```

What it does:

- chunks abstracts
- writes pgvector embeddings with server-side `%s::vector` binding
- logs inserted chunk counts per paper

## Schema and SQL

- Base tables: `pipeline/schema.sql`
- Medallion views: `sql/01_medallion_pipeline.sql`

Water monitoring medallion flow:

- **Bronze**: `raw_readings`
- **Silver**: `stg_readings`
- **Gold**: `mart_station_health`, `anomaly_flags`

## Databricks Apps deployment

### Dashboard app

Use the root config:

- `app.yaml` -> `python app.py`
- `requirements.txt` -> Flask + Requests only
- App name should include `dashboard`

### MCP app

Use the same root entrypoint `python app.py`, but install MCP dependencies instead:

```bash
pip install -r mcp_server/requirements.txt
```

Set an app name that does **not** include `dashboard`.

## Quick verification

```bash
python3 -m py_compile app.py
```
