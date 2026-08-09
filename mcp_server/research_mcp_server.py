from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

from lakebase import ensure_schema, run_query, run_write, run_write_returning, upsert_paper
from research_broker import get_paper, search_papers

mcp = FastMCP("water-research-copilot")
_MODEL: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _ensure_user(email: str) -> dict[str, Any]:
    user = run_write_returning(
        """
        INSERT INTO users (email, display_name)
        VALUES (%s, %s)
        ON CONFLICT (email) DO UPDATE SET display_name = COALESCE(users.display_name, EXCLUDED.display_name)
        RETURNING user_id, email, display_name
        """,
        (email, email.split("@")[0]),
    )
    if user:
        return user
    rows = run_query("SELECT user_id, email, display_name FROM users WHERE email = %s", (email,))
    return rows[0]


def _ensure_collection(user_id: int, collection_name: str) -> dict[str, Any]:
    collection = run_write_returning(
        """
        INSERT INTO collections (user_id, name, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, name) DO UPDATE SET name = EXCLUDED.name
        RETURNING collection_id, name
        """,
        (user_id, collection_name, f"Saved papers for {collection_name}"),
    )
    if collection:
        return collection
    rows = run_query(
        "SELECT collection_id, name FROM collections WHERE user_id = %s AND name = %s",
        (user_id, collection_name),
    )
    return rows[0]


@mcp.tool()
def search_research(query: str, limit: int = 10) -> dict:
    """Search for water quality research papers.

    Args:
        query: Natural-language topic, keyword phrase, or question to search in OpenAlex.
        limit: Maximum number of papers to return, capped by the upstream API.

    Returns:
        A dictionary with the search query, result count, and normalized paper records including
        paper id, title, abstract, year, DOI, citation count, concepts, open-access flag, and authors.
    """
    papers = search_papers(query, limit=limit)
    return {"query": query, "count": len(papers), "papers": papers}


@mcp.tool()
def get_paper_details(paper_id: str) -> dict:
    """Get detailed metadata for a specific paper.

    Args:
        paper_id: OpenAlex work identifier such as W123456789 or a full OpenAlex URL.

    Returns:
        A dictionary containing a normalized paper record with title, reconstructed abstract,
        authors, concepts, DOI, year, citation count, and raw OpenAlex metadata.
    """
    paper = get_paper(paper_id)
    return {"paper": paper}


@mcp.tool()
def semantic_search(query: str, limit: int = 5) -> dict:
    """Find conceptually similar papers using embedded abstracts in pgvector.

    Args:
        query: Conceptual query such as a treatment method, contaminant, or research question.
        limit: Maximum number of semantic matches to return.

    Returns:
        A dictionary containing the original query, match count, and ranked papers with similarity
        scores derived from cosine distance over stored abstract embeddings.
    """
    model = get_embedding_model()
    vector = model.encode(query).tolist()
    vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
    rows = run_query(
        """
        SELECT
            p.paper_id,
            p.title,
            p.abstract,
            p.publication_year,
            p.doi,
            p.cited_by_count,
            p.is_open_access,
            p.concepts,
            MIN(pe.embedding <=> %s::vector) AS distance
        FROM paper_embeddings pe
        JOIN papers p ON p.paper_id = pe.paper_id
        GROUP BY p.paper_id, p.title, p.abstract, p.publication_year, p.doi, p.cited_by_count, p.is_open_access, p.concepts
        ORDER BY distance ASC
        LIMIT %s
        """,
        (vector_literal, limit),
    )
    for row in rows:
        row["similarity"] = round(1 - float(row.pop("distance")), 4)
    return {"query": query, "count": len(rows), "papers": rows}


@mcp.tool()
def save_to_collection(paper_id: str, collection_name: str, user_email: str) -> dict:
    """Save a paper into a user's named collection.

    Args:
        paper_id: OpenAlex work identifier for the paper to save.
        collection_name: User-facing collection name, for example Favorites or DBP Studies.
        user_email: Email address used to identify the user in Lakebase.

    Returns:
        A dictionary describing the saved paper, the target collection, and whether the write
        succeeded. The paper is upserted into the database before it is linked to the collection.
    """
    user = _ensure_user(user_email)
    paper = get_paper(paper_id)
    upsert_paper(paper)
    collection = _ensure_collection(user["user_id"], collection_name)
    run_write(
        """
        INSERT INTO collection_papers (collection_id, paper_id)
        VALUES (%s, %s)
        ON CONFLICT (collection_id, paper_id) DO NOTHING
        """,
        (collection["collection_id"], paper["paper_id"]),
    )
    return {
        "success": True,
        "collection": collection,
        "user": user_email,
        "paper": {"paper_id": paper["paper_id"], "title": paper["title"]},
    }


@mcp.tool()
def create_reading_plan(topic: str, user_email: str, max_papers: int = 5) -> dict:
    """Create a structured reading plan for a topic and seed progress tracking.

    Args:
        topic: Water-quality research topic the user wants to study.
        user_email: Email address used to identify or create the user record.
        max_papers: Maximum number of papers to include in the generated plan.

    Returns:
        A dictionary containing the created learning goal, selected papers, and suggested reading
        sequence. The tool writes the learning goal and reading-progress rows to the database.
    """
    user = _ensure_user(user_email)
    papers = search_papers(topic, limit=max_papers)
    for paper in papers:
        upsert_paper(paper)

    goal = run_write_returning(
        """
        INSERT INTO learning_goals (user_id, title, description)
        VALUES (%s, %s, %s)
        RETURNING goal_id, title, description, created_at
        """,
        (
            user["user_id"],
            f"Study plan: {topic}",
            f"Structured reading plan focused on {topic}, ordered for relevance, impact, and recency.",
        ),
    )

    plan_items = []
    for index, paper in enumerate(sorted(papers, key=lambda p: (p.get("cited_by_count", 0), p.get("year") or 0), reverse=True), start=1):
        run_write(
            """
            INSERT INTO reading_progress (user_id, paper_id, status, notes)
            VALUES (%s, %s, 'not_started', %s)
            ON CONFLICT (user_id, paper_id) DO NOTHING
            """,
            (user["user_id"], paper["paper_id"], f"Reading plan for topic: {topic}"),
        )
        plan_items.append(
            {
                "step": index,
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "year": paper.get("year"),
                "cited_by_count": paper.get("cited_by_count", 0),
                "why": "High relevance based on topic search, citation impact, and publication recency.",
            }
        )

    return {"success": True, "goal": goal, "user": user_email, "plan": plan_items}


@mcp.tool()
def update_reading_status(paper_id: str, status: str, user_email: str, notes: str = "") -> dict:
    """Update a user's reading-progress status for a paper.

    Args:
        paper_id: OpenAlex work identifier for the paper whose progress is being updated.
        status: Reading state, expected to be one of not_started, reading, or completed.
        user_email: Email address used to identify the user record.
        notes: Optional free-form notes about takeaways, blockers, or next actions.

    Returns:
        A dictionary confirming the new reading state and the associated paper id for the user.
        The tool writes the updated status and notes into Lakebase.
    """
    if status not in {"not_started", "reading", "completed"}:
        raise ValueError("status must be one of: not_started, reading, completed")

    user = _ensure_user(user_email)
    run_write(
        """
        INSERT INTO reading_progress (user_id, paper_id, status, notes, updated_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (user_id, paper_id) DO UPDATE SET
            status = EXCLUDED.status,
            notes = EXCLUDED.notes,
            updated_at = now()
        """,
        (user["user_id"], paper_id, status, notes),
    )
    return {"success": True, "user": user_email, "paper_id": paper_id, "status": status, "notes": notes}


@mcp.tool()
def get_reading_list(user_email: str) -> dict:
    """Return a user's saved and in-progress reading list.

    Args:
        user_email: Email address used to identify the user in Lakebase.

    Returns:
        A dictionary with the user email, item count, and reading-list entries including paper
        metadata, collection names, status, notes, and last update timestamps.
    """
    rows = run_query(
        """
        SELECT
            p.paper_id,
            p.title,
            p.publication_year,
            p.cited_by_count,
            p.abstract,
            rp.status,
            rp.notes,
            rp.updated_at,
            array_remove(array_agg(DISTINCT c.name), NULL) AS collections
        FROM users u
        LEFT JOIN reading_progress rp ON rp.user_id = u.user_id
        LEFT JOIN papers p ON p.paper_id = rp.paper_id
        LEFT JOIN collection_papers cp ON cp.paper_id = p.paper_id
        LEFT JOIN collections c ON c.collection_id = cp.collection_id AND c.user_id = u.user_id
        WHERE u.email = %s
        GROUP BY p.paper_id, p.title, p.publication_year, p.cited_by_count, p.abstract, rp.status, rp.notes, rp.updated_at
        ORDER BY rp.updated_at DESC NULLS LAST
        """,
        (user_email,),
    )
    items = [row for row in rows if row.get("paper_id")]
    return {"user": user_email, "count": len(items), "items": items}


if __name__ == "__main__":
    ensure_schema()
    mcp.run(transport="sse")
