from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2.extras import RealDictCursor

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "pipeline" / "schema.sql"


def _secret(scope: str, key: str) -> str | None:
    try:
        client = WorkspaceClient()
        return client.secrets.get_secret(scope=scope, key=key).value
    except Exception:
        return None


def _from_env_or_secret(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    scope = os.getenv("DATABRICKS_SECRET_SCOPE")
    secret_key = os.getenv(f"{name}_SECRET_KEY", name.lower())
    if scope:
        secret_value = _secret(scope, secret_key)
        if secret_value:
            return secret_value

    return default


def get_connection():
    host = _from_env_or_secret("LAKEBASE_HOST")
    port = int(_from_env_or_secret("LAKEBASE_PORT", "5432") or "5432")
    dbname = _from_env_or_secret("LAKEBASE_DB", "postgres")
    user = _from_env_or_secret("LAKEBASE_USER")
    password = _from_env_or_secret("LAKEBASE_PASSWORD")
    sslmode = _from_env_or_secret("LAKEBASE_SSLMODE", "require")

    if not all([host, dbname, user, password]):
        raise RuntimeError(
            "Missing Lakebase connection settings. Set LAKEBASE_HOST/DB/USER/PASSWORD or map them through DATABRICKS_SECRET_SCOPE."
        )

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode=sslmode,
        cursor_factory=RealDictCursor,
    )


def run_query(sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def run_write(sql: str, params: Iterable[Any] | None = None) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rowcount = cur.rowcount
        conn.commit()
    return rowcount


def run_write_returning(sql: str, params: Iterable[Any] | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def ensure_schema() -> None:
    schema_sql = SCHEMA_PATH.read_text()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()


def upsert_paper(paper: dict[str, Any]) -> None:
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
