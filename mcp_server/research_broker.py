from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.openalex.org"
MAILTO = "brucect20@gmail.com"
DEFAULT_TIMEOUT = 30


class OpenAlexError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {"mailto": MAILTO, **(params or {})}
    response = requests.get(f"{BASE_URL}{path}", params=merged, timeout=DEFAULT_TIMEOUT)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500]
        raise OpenAlexError(f"OpenAlex request failed: {exc}. Response: {detail}") from exc
    return response.json()


def get_paper_abstract(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not inverted:
        return ""

    positions: dict[int, str] = {}
    for token, indexes in inverted.items():
        for index in indexes:
            positions[index] = token
    return " ".join(token for _, token in sorted(positions.items())).strip()


def _normalize_work(work: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for authorship in work.get("authorships", []):
        author = authorship.get("author") or {}
        institutions = authorship.get("institutions") or []
        authors.append(
            {
                "author_id": (author.get("id") or "").split("/")[-1] or None,
                "name": author.get("display_name", "Unknown author"),
                "institution": institutions[0].get("display_name") if institutions else None,
                "orcid": author.get("orcid"),
            }
        )

    concepts = [concept.get("display_name") for concept in work.get("concepts", []) if concept.get("display_name")]
    open_access = bool((work.get("open_access") or {}).get("is_oa"))
    work_id = work.get("id", "").split("/")[-1]

    return {
        "paper_id": work_id,
        "title": work.get("title") or "Untitled paper",
        "abstract": get_paper_abstract(work),
        "year": work.get("publication_year"),
        "doi": work.get("doi"),
        "cited_by_count": work.get("cited_by_count", 0),
        "authors": authors,
        "concepts": concepts,
        "is_open_access": open_access,
        "raw_json": work,
    }


def search_papers(query: str, limit: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"search": query, "per-page": min(limit, 50)}
    if filters:
        params["filter"] = ",".join(f"{key}:{value}" for key, value in filters.items())
    payload = _get("/works", params=params)
    return [_normalize_work(work) for work in payload.get("results", [])]


def get_paper(paper_id: str) -> dict[str, Any]:
    paper_id = paper_id.replace("https://openalex.org/", "")
    return _normalize_work(_get(f"/works/{paper_id}"))


def fetch_by_topic(topic: str, limit: int = 20) -> list[dict[str, Any]]:
    filters = {"default.search": topic}
    return search_papers(query=topic, limit=limit, filters=filters)
