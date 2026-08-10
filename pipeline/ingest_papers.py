from __future__ import annotations

import json
import os
import time
from typing import Any

import psycopg2
import requests
from pyspark.sql import Row, SparkSession

OPENALEX_URL = "https://api.openalex.org/works"
MAILTO = os.getenv("OPENALEX_MAILTO", "brucect20@gmail.com")
MIN_PUBLICATION_YEAR = int(os.getenv("MIN_PUBLICATION_YEAR", "2021"))
TOPICS = [
    "water quality monitoring",
    "drinking water treatment",
    "PFAS water remediation",
    "watershed management",
    "turbidity dissolved oxygen stream health",
]


def reconstruct_abstract(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in inverted.items():
        for index in indexes:
            positions[index] = token
    return " ".join(token for _, token in sorted(positions.items())).strip()


def retry_get(url: str, params: dict[str, Any] | None = None, max_retries: int = 3, timeout: int = 30) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            is_retryable = status_code == 429 or (status_code is not None and status_code >= 500)
            if attempt >= max_retries or not is_retryable:
                raise
            time.sleep(2**attempt)

    if last_error:
        raise last_error
    raise RuntimeError("retry_get failed without an exception")


def fetch_topic(topic: str, per_page: int = 25, max_pages: int = 3) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    for _ in range(max_pages):
        response = retry_get(
            OPENALEX_URL,
            params={
                "search": topic,
                "per-page": per_page,
                "cursor": cursor,
                "filter": f"publication_year:>{MIN_PUBLICATION_YEAR - 1}",
                "mailto": MAILTO,
            },
        )
        response.raise_for_status()
        payload = response.json()
        page_results = payload.get("results", [])
        if not page_results:
            break
        results.extend(page_results)
        next_cursor = (payload.get("meta") or {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor
    return results


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(os.environ["LAKEBASE_URL"], sslmode="require")


def main() -> None:
    spark = SparkSession.builder.appName("OpenAlexPaperIngest").getOrCreate()
    rows: list[Row] = []

    for topic in TOPICS:
        for work in fetch_topic(topic):
            authorships = work.get("authorships", [])
            authors = []
            for idx, authorship in enumerate(authorships, start=1):
                author = authorship.get("author") or {}
                institutions = authorship.get("institutions") or []
                authors.append(
                    {
                        "author_id": (author.get("id") or "").split("/")[-1] or None,
                        "display_name": author.get("display_name", "Unknown author"),
                        "orcid": author.get("orcid"),
                        "institution": institutions[0].get("display_name") if institutions else None,
                        "position": idx,
                    }
                )

            rows.append(
                Row(
                    paper_id=(work.get("id") or "").split("/")[-1],
                    title=work.get("title") or "Untitled paper",
                    abstract=reconstruct_abstract(work),
                    publication_year=work.get("publication_year"),
                    doi=work.get("doi"),
                    cited_by_count=work.get("cited_by_count", 0),
                    is_open_access=bool((work.get("open_access") or {}).get("is_oa")),
                    concepts=[c.get("display_name") for c in work.get("concepts", []) if c.get("display_name")],
                    raw_json=json.dumps(work),
                    authors=authors,
                )
            )

    df = spark.createDataFrame(rows).dropDuplicates(["paper_id"])
    records = [row.asDict(recursive=True) for row in df.collect()]

    conn = get_connection()
    with conn.cursor() as cur:
        for paper in records:
            cur.execute(
                """
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
                """,
                (
                    paper["paper_id"],
                    paper["title"],
                    paper["abstract"],
                    paper["publication_year"],
                    paper["doi"],
                    paper["cited_by_count"],
                    paper["is_open_access"],
                    paper["concepts"],
                    paper["raw_json"],
                ),
            )
            for author in paper["authors"]:
                if not author["author_id"]:
                    continue
                cur.execute(
                    """
                    INSERT INTO authors (author_id, display_name, orcid, institution, raw_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (author_id) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        orcid = EXCLUDED.orcid,
                        institution = EXCLUDED.institution,
                        raw_json = EXCLUDED.raw_json
                    """,
                    (
                        author["author_id"],
                        author["display_name"],
                        author["orcid"],
                        author["institution"],
                        json.dumps(author),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO paper_authors (paper_id, author_id, author_position)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (paper_id, author_id) DO UPDATE SET
                        author_position = EXCLUDED.author_position
                    """,
                    (paper["paper_id"], author["author_id"], author["position"]),
                )
    conn.commit()
    conn.close()
    spark.stop()
    print(json.dumps({"papers_ingested": len(records)}))


if __name__ == "__main__":
    main()
