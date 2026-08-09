from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

ROOT_DIR = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT_DIR / "mcp_server"
sys.path.append(str(MCP_DIR))

from lakebase import run_query  # noqa: E402
from research_broker import search_papers  # noqa: E402
from research_mcp_server import create_reading_plan, get_reading_list, save_to_collection, update_reading_status  # noqa: E402

app = Flask(__name__)
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "researcher@example.com")


@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "water quality monitoring")
    user_email = request.args.get("user_email", DEFAULT_USER_EMAIL)
    active_tab = request.args.get("tab", "search")

    try:
        search_results = {"papers": search_papers(query, limit=10), "query": query}
    except Exception as exc:
        search_results = {"papers": [], "query": query, "error": str(exc)}

    try:
        reading_list = get_reading_list(user_email)
    except Exception as exc:
        reading_list = {"items": [], "error": str(exc)}

    try:
        collections = run_query(
            """
            SELECT c.name, COUNT(cp.paper_id) AS paper_count
            FROM users u
            JOIN collections c ON c.user_id = u.user_id
            LEFT JOIN collection_papers cp ON cp.collection_id = c.collection_id
            WHERE u.email = %s
            GROUP BY c.name
            ORDER BY c.name
            """,
            (user_email,),
        )
    except Exception:
        collections = []

    try:
        goals = run_query(
            """
            SELECT lg.goal_id, lg.title, lg.description, lg.created_at
            FROM users u
            JOIN learning_goals lg ON lg.user_id = u.user_id
            WHERE u.email = %s
            ORDER BY lg.created_at DESC
            """,
            (user_email,),
        )
    except Exception:
        goals = []

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
    save_to_collection(
        paper_id=request.form["paper_id"],
        collection_name=request.form.get("collection_name", "Saved Papers"),
        user_email=request.form.get("user_email", DEFAULT_USER_EMAIL),
    )
    return redirect(url_for("index", q=request.form.get("query", ""), user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="search"))


@app.route("/plan", methods=["POST"])
def create_plan():
    create_reading_plan(
        topic=request.form["topic"],
        user_email=request.form.get("user_email", DEFAULT_USER_EMAIL),
        max_papers=int(request.form.get("max_papers", 5)),
    )
    return redirect(url_for("index", q=request.form.get("topic", ""), user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="goals"))


@app.route("/status", methods=["POST"])
def update_status():
    update_reading_status(
        paper_id=request.form["paper_id"],
        status=request.form["status"],
        user_email=request.form.get("user_email", DEFAULT_USER_EMAIL),
        notes=request.form.get("notes", ""),
    )
    return redirect(url_for("index", q=request.form.get("query", ""), user_email=request.form.get("user_email", DEFAULT_USER_EMAIL), tab="reading-list"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8001")), debug=True)
