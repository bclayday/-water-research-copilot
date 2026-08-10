"""
Unified entry point for Water Research Copilot.

Uses DATABRICKS_APP_NAME to determine which server to run.
"""

import os
import sys
from pathlib import Path

APP_NAME = os.getenv("DATABRICKS_APP_NAME", "")
IS_DASHBOARD = "dashboard" in APP_NAME.lower()

HERE = Path(__file__).resolve().parent

if IS_DASHBOARD:
    # Run Flask dashboard
    import requests
    from flask import Flask, render_template_string, request, redirect, url_for

    app = Flask(__name__, template_folder=str(HERE / "dashboard" / "templates"))
    DEFAULT_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "researcher@example.com")

    OPENALEX_BASE = "https://api.openalex.org"
    MAILTO = "brucect20@gmail.com"

    HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Water Research Copilot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0a0e1a; color: #e0e6f0; min-height: 100vh; }
        .header { background: linear-gradient(135deg, #0d1b2a, #1b4965);
                  padding: 2rem; text-align: center; }
        .header h1 { font-size: 1.8rem; color: #5fa8d3; }
        .header p { color: #7a8da8; margin-top: 0.5rem; }
        .container { max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }
        .search-bar { display: flex; gap: 0.5rem; margin-bottom: 2rem; }
        .search-bar input { flex: 1; padding: 0.75rem; border-radius: 8px;
                           border: 1px solid #2a3a5c; background: #111827; color: #e0e6f0; font-size: 1rem; }
        .search-bar button { padding: 0.75rem 1.5rem; border-radius: 8px;
                            border: none; background: #1b4965; color: #fff; cursor: pointer; font-size: 1rem; }
        .search-bar button:hover { background: #2b6975; }
        .paper-card { background: #111827; border-radius: 12px; padding: 1.5rem;
                      margin-bottom: 1rem; border: 1px solid #1e293b; }
        .paper-card h3 { color: #5fa8d3; margin-bottom: 0.5rem; }
        .paper-meta { color: #7a8da8; font-size: 0.85rem; margin-bottom: 0.5rem; }
        .paper-abstract { color: #a0aec0; font-size: 0.9rem; line-height: 1.5; }
        .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px;
                font-size: 0.75rem; margin-right: 0.3rem; }
        .badge-cite { background: #1e3a5f; color: #5fa8d3; }
        .badge-year { background: #1e3a2f; color: #53c99a; }
        .badge-oa { background: #3a1e1e; color: #e85a5a; }
        .error { color: #e85a5a; padding: 1rem; background: #1a1015; border-radius: 8px;
                margin-bottom: 1rem; border: 1px solid #3a1e1e; }
        .tabs { display: flex; gap: 0.5rem; margin-bottom: 2rem; }
        .tab { padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer;
               background: #111827; border: 1px solid #1e293b; color: #7a8da8; }
        .tab.active { background: #1b4965; color: #fff; }
        .empty { text-align: center; color: #7a8da8; padding: 3rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>💧 Water Research Copilot</h1>
        <p>Discover water quality research papers powered by OpenAlex</p>
    </div>
    <div class="container">
        <div class="search-bar">
            <form method="GET" action="/" style="flex:1; display:flex; gap:0.5rem;">
                <input type="text" name="q" value="{{ query }}" placeholder="Search water quality research...">
                <button type="submit">Search</button>
            </form>
        </div>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        {% if papers %}
            {% for paper in papers %}
            <div class="paper-card">
                <h3>{{ paper.title }}</h3>
                <div class="paper-meta">
                    {{ paper.authors|join(', ') if paper.authors else 'Unknown' }} · {{ paper.year or 'N/A' }}
                </div>
                <div style="margin: 0.5rem 0;">
                    {% if paper.cited_by_count %}<span class="badge badge-cite">Cited: {{ paper.cited_by_count }}</span>{% endif %}
                    {% if paper.year %}<span class="badge badge-year">{{ paper.year }}</span>{% endif %}
                    {% if paper.is_open_access %}<span class="badge badge-oa">Open Access</span>{% endif %}
                </div>
                {% if paper.abstract %}
                <p class="paper-abstract">{{ paper.abstract[:300] }}{% if paper.abstract|length > 300 %}...{% endif %}</p>
                {% endif %}
                {% if paper.doi %}
                <p style="margin-top:0.5rem;"><a href="https://doi.org/{{ paper.doi }}" target="_blank" style="color:#5fa8d3;">Read paper →</a></p>
                {% endif %}
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">No papers found. Try a different search term.</div>
        {% endif %}
    </div>
</body>
</html>
    """

    def search_openalex(query, limit=10):
        """Search OpenAlex for water quality papers."""
        try:
            resp = requests.get(
                f"{OPENALEX_BASE}/works",
                params={"search": query, "per_page": limit, "mailto": MAILTO},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for work in data.get("results", []):
                # Reconstruct abstract from inverted index
                abstract = ""
                idx = work.get("abstract_inverted_index")
                if idx:
                    word_positions = []
                    for word, positions in idx.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = " ".join(w for _, w in word_positions)

                # Get author names
                authors = []
                for a in work.get("authorships", [])[:5]:
                    name = a.get("author", {}).get("display_name")
                    if name:
                        authors.append(name)

                oa = work.get("open_access", {})
                results.append({
                    "paper_id": work.get("id", "").split("/")[-1],
                    "title": work.get("title", "Untitled"),
                    "abstract": abstract[:500],
                    "year": work.get("publication_year"),
                    "doi": work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
                    "cited_by_count": work.get("cited_by_count", 0),
                    "is_open_access": oa.get("is_oa", False),
                    "authors": authors,
                })
            return results
        except Exception as e:
            return []

    @app.route("/", methods=["GET"])
    def index():
        query = request.args.get("q", "water quality monitoring")
        papers = search_openalex(query, limit=10)
        return render_template_string(HTML_TEMPLATE, query=query, papers=papers, error=None)

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
else:
    # Run MCP server
    from mcp_server.research_mcp_server import mcp
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
