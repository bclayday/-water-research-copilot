from __future__ import annotations

import os
from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MODEL_NAME = "all-MiniLM-L6-v2"


def get_connection():
    return psycopg2.connect(
        host=os.environ["LAKEBASE_HOST"],
        port=os.getenv("LAKEBASE_PORT", "5432"),
        dbname=os.getenv("LAKEBASE_DB", "postgres"),
        user=os.environ["LAKEBASE_USER"],
        password=os.environ["LAKEBASE_PASSWORD"],
        sslmode=os.getenv("LAKEBASE_SSLMODE", "require"),
    )


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def fetch_unembedded_papers(limit: int = 250) -> list[tuple[str, str]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.paper_id, p.abstract
                FROM papers p
                LEFT JOIN paper_embeddings pe ON pe.paper_id = p.paper_id
                WHERE pe.paper_id IS NULL
                  AND COALESCE(p.abstract, '') <> ''
                ORDER BY p.ingested_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def build_rows(records: Iterable[tuple[str, str]], model: SentenceTransformer) -> list[tuple]:
    rows: list[tuple] = []
    for paper_id, abstract in records:
        chunks = chunk_text(abstract)
        if not chunks:
            continue
        vectors = model.encode(chunks)
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector.tolist()) + "]"
            rows.append((paper_id, index, chunk, vector_literal, MODEL_NAME))
    return rows


def insert_embeddings(rows: list[tuple]) -> int:
    if not rows:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO paper_embeddings (paper_id, chunk_index, chunk_text, embedding, model_name)
                VALUES %s
                """,
                rows,
                template="(%s, %s, %s, %s::vector, %s)",
            )
        conn.commit()
    return len(rows)


def main() -> None:
    model = SentenceTransformer(MODEL_NAME)
    records = fetch_unembedded_papers()
    rows = build_rows(records, model)
    inserted = insert_embeddings(rows)
    print(f"Inserted {inserted} embedding rows")


if __name__ == "__main__":
    main()
