"""
Water Research Copilot — Dashboard App (Flask).

Serves a dark-themed UI for searching water quality research papers,
managing collections, tracking reading progress, and creating reading plans.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

# Add mcp_server to path for shared imports
ROOT_DIR = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT_DIR / "mcp_server"
sys.path.append(str(MCP_DIR))

app = Flask(__name__)
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "researcher@example.com")


def _safe_search(query: str, limit: int = 10) -> dict:
    try:
        from research_broker import search_papers
        papers = search_papers(query, limit=limit)
        return {"papers": papers, "query": query}
    except Exception as exc:
        return {"papers": [], "query": query, "error": str(exc)}


def _safe_reading_list(user_email: str) -> dict:
    try:
        import lakebase
        lakebase.ensure_schema()
        rows = lakebase.run_query(
            """SELECT p.paper_id, p.title, p.abstract, p.publication_year,
                      p.cited_by_count, rp.status, rp.notes
            FROM reading_progress rp
            JOIN papers p ON p.paper_id = rp.paper_id
            JOIN users u ON u.user_id = rp.user_id
            WHERE u.email = %s
            ORDER BY rp.updated_at DESC""",
            (user_email,),
        )
        return {"items": rows}
    except Exception as exc:
        return {"items": [], "error": str(exc)}


def _safe_collections(user_email: str) -> list:
    try:
        import lakebase
        lakebase.ensure_schema()
        return lakebase.run_query(
            """SELECT c.name, COUNT(cp.paper_id) AS paper_count
            FROM users u
            JOIN collections c ON c.user_id = u.user_id
            LEFT JOIN collection_papers cp ON cp.collection_id = c.collection_id
            WHERE u.email = %s
            GROUP BY c.name ORDER BY c.name""",
            (user_email,),
        )
    except Exception:
        return []


def _safe_goals(user_email: str) -> list:
    try:
        import lakebase
        lakebase.ensure_schema()
        return lakebase.run_query(
            """SELECT lg.goal_id, lg.title, lg.description, lg.created_at
            FROM users u
            JOIN learning_goals lg ON lg.user_id = u.user_id
            WHERE u.email = %s ORDER BY lg.created_at DESC""",
            (user_email,),
        )
    except Exception:
        return []


@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "water quality monitoring")
    user_email = request.args.get("user_email", DEFAULT_USER_EMAIL)
    active_tab = request.args.get("tab", "search")

    search_results = _safe_search(query, limit=10)
    reading_list = _safe_reading_list(user_email)
    collections = _safe_collections(user_email)
    goals = _safe_goals(user_email)

    return render_template(
        "index.html",
        query=query,
        user_email=user_email,
        active_tab=active_tab,
        search_results=search_results,
        reading_list=reading_list,
        collections=collections,
        goals=goals,
    )


@app.route("/save", methods=["POST"])
def save_paper():
    try:
        import lakebase
        lakebase.ensure_schema()
        paper_id = request.form["paper_id"]
        collection_name = request.form.get("collection_name", "Saved Papers")
        user_email = request.form.get("user_email", DEFAULT_USER_EMAIL)

        lakebase.run_write(
            "INSERT INTO users (email, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_email, user_email.split("@")[0]),
        )
        user = lakebase.run_query("SELECT user_id FROM users WHERE email = %s", (user_email,))
        if user:
            lakebase.run_write(
                "INSERT INTO collections (user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user[0]["user_id"], collection_name),
            )
            col = lakebase.run_query(
                "SELECT collection_id FROM collections WHERE user_id = %s AND name = %s",
                (user[0]["user_id"], collection_name),
            )
            if col:
                lakebase.run_write(
                    "INSERT INTO collection_papers (collection_id, paper_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (col[0]["collection_id"], paper_id),
                )
    except Exception:
        pass
    return redirect(url_for("index", q=request.form.get("query", ""),
                            user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="search"))


@app.route("/status", methods=["POST"])
def update_status():
    try:
        import lakebase
        lakebase.ensure_schema()
        paper_id = request.form["paper_id"]
        status = request.form["status"]
        user_email = request.form.get("user_email", DEFAULT_USER_EMAIL)
        notes = request.form.get("notes", "")

        user = lakebase.run_query("SELECT user_id FROM users WHERE email = %s", (user_email,))
        if user:
            lakebase.run_write(
                """INSERT INTO reading_progress (user_id, paper_id, status, notes, updated_at)
                   VALUES (%s, %s, %s, %s, now())
                   ON CONFLICT (user_id, paper_id) DO UPDATE SET status = EXCLUDED.status,
                   notes = EXCLUDED.notes, updated_at = now()""",
                (user[0]["user_id"], paper_id, status, notes),
            )
    except Exception:
        pass
    return redirect(url_for("index", q=request.form.get("query", ""),
                            user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="reading-list"))


@app.route("/plan", methods=["POST"])
def create_plan():
    try:
        import lakebase
        from research_broker import search_papers
        lakebase.ensure_schema()

        topic = request.form["topic"]
        user_email = request.form.get("user_email", DEFAULT_USER_EMAIL)
        max_papers = int(request.form.get("max_papers", 5))

        lakebase.run_write(
            "INSERT INTO users (email, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_email, user_email.split("@")[0]),
        )
        user = lakebase.run_query("SELECT user_id FROM users WHERE email = %s", (user_email,))
        if user:
            user_id = user[0]["user_id"]
            lakebase.run_write(
                "INSERT INTO learning_goals (user_id, title, description) VALUES (%s, %s, %s)",
                (user_id, f"Reading plan: {topic}", topic),
            )
            papers = search_papers(topic, limit=max_papers)
            for p in papers:
                lakebase.upsert_paper(p)
                lakebase.run_write(
                    "INSERT INTO reading_progress (user_id, paper_id, status) VALUES (%s, %s, 'not_started') ON CONFLICT DO NOTHING",
                    (user_id, p["paper_id"]),
                )
    except Exception:
        pass
    return redirect(url_for("index", q=request.form.get("topic", ""),
                            user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="goals"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
