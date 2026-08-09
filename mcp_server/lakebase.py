"""
Lakebase connection helpers.

Connects to Databricks Lakebase PostgreSQL using a connection URL stored
in the Databricks secret scope 'database' under key 'lakebase-url'.
The URL is base64-encoded (matching the pattern from Day 1 assignments).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, parse_qs

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2.extras import RealDictCursor

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "pipeline" / "schema.sql"


def _get_lakebase_url() -> str:
    """
    Retrieve the Lakebase connection URL.

    Priority:
      1. LAKEBASE_URL env var (already a full postgres:// connection string)
      2. Databricks secret scope 'database' key 'lakebase-url'
      3. LAKEBASE_URL_B64 env var (base64-encoded connection string)
    """
    # 1. Direct env var
    url = os.getenv("LAKEBASE_URL")
    if url:
        return url

    # 2. Databricks secret
    try:
        client = WorkspaceClient()
        secret_val = client.secrets.get_secret(scope="database", key="lakebase-url").value
        if secret_val:
            # Try base64 decode first (Day 1 pattern)
            try:
                decoded = base64.b64decode(secret_val).decode("utf-8")
                if decoded.startswith("postgres"):
                    return decoded
            except Exception:
                pass
            # Otherwise use raw value
            if secret_val.startswith("postgres"):
                return secret_val
    except Exception:
        pass

    # 3. Base64 env var fallback
    b64 = os.getenv("LAKEBASE_URL_B64")
    if b64:
        return base64.b64decode(b64).decode("utf-8")

    raise RuntimeError(
        "Could not find Lakebase URL. Set LAKEBASE_URL env var or store it "
        "in Databricks secret scope 'database' key 'lakebase-url'."
    )


def get_connection():
    """Get a psycopg2 connection to Lakebase."""
    url = _get_lakebase_url()
    parsed = urlparse(url)

    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        sslmode="require",
        cursor_factory=RealDictCursor,
    )
    return conn


def run_query(sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    """Execute a SELECT query and return rows as list of dicts."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def run_write(sql: str, params: Iterable[Any] | None = None) -> int:
    """Execute an INSERT/UPDATE/DELETE and return rowcount."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rowcount = cur.rowcount
        conn.commit()
    return rowcount


def run_write_returning(sql: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
    """Execute an INSERT ... RETURNING and return the row as a dict."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def ensure_schema() -> None:
    """Create all tables if they don't exist."""
    schema_sql = SCHEMA_PATH.read_text()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Split on semicolons and execute each statement
            statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
            for stmt in statements:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    # Ignore "already exists" errors
                    if "already exists" not in str(e):
                        print(f"Schema warning: {e}")
        conn.commit()


def upsert_paper(paper: dict[str, Any]) -> None:
    """Insert or update a paper in the papers table."""
    sql = """
    INSERT INTO papers (
        paper_id, title, abstract, publication_year, doi,
        cited_by_count, is_open_access, concepts, raw_json
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
    ON CONFLICT (paper_id) DO UPDATE SET
        title = EXCLUDED.title,
        abstract = EXCLUDED.abstract,
        publication_year = EXCLUDED.publication_year,
        doi = EXCLUDED.doi,
        cited_by_count = EXCLUDED.cited_by_count,
        is_open_access = EXCLUDED.is_open_access,
        concepts = EXCLUDED.concepts,
        raw_json = EXCLUDED.raw_json,
        ingested_at = now()
    """
    run_write(
        sql,
        (
            paper["paper_id"],
            paper["title"],
            paper.get("abstract"),
            paper.get("year"),
            paper.get("doi"),
            paper.get("cited_by_count", 0),
            paper.get("is_open_access", False),
            paper.get("concepts", []),
            json.dumps(paper.get("raw_json", {})),
        ),
    )
