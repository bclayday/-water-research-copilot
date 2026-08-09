from __future__ import annotations

import json
import os
from typing import Any

import psycopg2
import requests
from pyspark.sql import SparkSession, functions as F, types as T
from psycopg2.extras import execute_values

OPENALEX_URL = "https://api.openalex.org/works"
MAILTO = "brucect20@gmail.com"
SEARCH_TERMS = [
    "water quality monitoring",
    "drinking water treatment",
    "wastewater surveillance",
    "microbial water quality",
    "disinfection byproducts water",
]


def fetch_openalex_pages() -> list[dict[str, Any]]:
    works: list[dict[str, Any]] = []
    for term in SEARCH_TERMS:
        response = requests.get(
            OPENALEX_URL,
            params={"search": term, "per-page": 25, "mailto": MAILTO},
            timeout=30,
        )
        response.raise_for_status()
        works.extend(response.json().get("results", []))
    return works


def get_connection():
    return psycopg2.connect(
        host=os.environ["LAKEBASE_HOST"],
        port=os.getenv("LAKEBASE_PORT", "5432"),
        dbname=os.getenv("LAKEBASE_DB", "postgres"),
        user=os.environ["LAKEBASE_USER"],
        password=os.environ["LAKEBASE_PASSWORD"],
        sslmode=os.getenv("LAKEBASE_SSLMODE", "require"),
    )


def write_tables(papers: list[tuple], authors: list[tuple], paper_authors: list[tuple]) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO papers (
                    paper_id, title, abstract, publication_year, doi,
                    cited_by_count, is_open_access, concepts, raw_json
                ) VALUES %s
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
                papers,
            )
            execute_values(
                cur,
                """
                INSERT INTO authors (author_id, name, institution, orcid)
                VALUES %s
                ON CONFLICT (author_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    institution = EXCLUDED.institution,
                    orcid = EXCLUDED.orcid
                """,
                authors,
            )
            execute_values(
                cur,
                """
                INSERT INTO paper_authors (paper_id, author_id, author_position)
                VALUES %s
                ON CONFLICT (paper_id, author_id) DO UPDATE SET
                    author_position = EXCLUDED.author_position
                """,
                paper_authors,
            )
        conn.commit()


def main() -> None:
    spark = SparkSession.builder.appName("WaterResearchIngest").getOrCreate()
    raw_payload = fetch_openalex_pages()
    raw_rdd = spark.sparkContext.parallelize([json.dumps(item) for item in raw_payload])
    df = spark.read.json(raw_rdd)

    abstract_schema = T.MapType(T.StringType(), T.ArrayType(T.LongType()))

    @F.udf(returnType=T.StringType())
    def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str:
        if not inverted:
            return ""
        positions: dict[int, str] = {}
        for token, indexes in inverted.items():
            for idx in indexes:
                positions[idx] = token
        return " ".join(word for _, word in sorted(positions.items()))

    @F.udf(returnType=T.ArrayType(T.StringType()))
    def concept_names(concepts: list[dict[str, Any]] | None) -> list[str]:
        return [item.get("display_name") for item in concepts or [] if item.get("display_name")]

    transformed = (
        df.withColumn("paper_id", F.element_at(F.split(F.col("id"), "/"), -1))
        .withColumn("abstract", reconstruct_abstract(F.col("abstract_inverted_index").cast(abstract_schema)))
        .withColumn("concept_names", concept_names(F.col("concepts")))
        .withColumn("is_open_access", F.coalesce(F.col("open_access.is_oa"), F.lit(False)))
        .select(
            "paper_id",
            F.col("title"),
            "abstract",
            F.col("publication_year"),
            F.col("doi"),
            F.col("cited_by_count"),
            "is_open_access",
            F.col("concept_names"),
            F.to_json(F.struct("*")).alias("raw_json"),
            "authorships",
        )
        .dropDuplicates(["paper_id"])
    )

    rows = transformed.collect()

    paper_rows = [
        (
            row["paper_id"],
            row["title"],
            row["abstract"],
            row["publication_year"],
            row["doi"],
            row["cited_by_count"],
            row["is_open_access"],
            row["concept_names"],
            row["raw_json"],
        )
        for row in rows
    ]

    author_rows: dict[str, tuple] = {}
    paper_author_rows: list[tuple] = []
    for row in rows:
        for index, authorship in enumerate(row["authorships"] or []):
            author = authorship.get("author") or {}
            author_id = (author.get("id") or "").split("/")[-1]
            if not author_id:
                continue
            institutions = authorship.get("institutions") or []
            institution = institutions[0].get("display_name") if institutions else None
            author_rows[author_id] = (
                author_id,
                author.get("display_name", "Unknown author"),
                institution,
                author.get("orcid"),
            )
            paper_author_rows.append((row["paper_id"], author_id, index))

    write_tables(paper_rows, list(author_rows.values()), paper_author_rows)
    spark.stop()


if __name__ == "__main__":
    main()
