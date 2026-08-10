from __future__ import annotations

import os
from typing import Iterable

import psycopg2
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def main() -> None:
    conn = psycopg2.connect(os.environ["LAKEBASE_URL"], sslmode="require")
    model = SentenceTransformer(MODEL_NAME)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.paper_id, p.abstract
            FROM papers p
            LEFT JOIN paper_embeddings pe ON pe.paper_id = p.paper_id
            WHERE COALESCE(p.abstract, '') <> ''
            GROUP BY p.paper_id, p.abstract
            HAVING COUNT(pe.embedding_id) = 0
            ORDER BY p.publication_year DESC NULLS LAST
            """
        )
        papers = cur.fetchall()

    inserted = 0
    with conn.cursor() as cur:
        for paper_id, abstract in papers:
            for chunk_index, chunk in enumerate(chunk_text(abstract)):
                embedding = model.encode(chunk).tolist()
                cur.execute(
                    """
                    INSERT INTO paper_embeddings (paper_id, chunk_index, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (paper_id, chunk_index) DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        embedding = EXCLUDED.embedding
                    """,
                    (paper_id, chunk_index, chunk, vector_literal(embedding)),
                )
                inserted += 1
    conn.commit()
    conn.close()
    print({"embedding_chunks_written": inserted})


if __name__ == "__main__":
    main()
