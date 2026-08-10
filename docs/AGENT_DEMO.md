# AGENT DEMO

## Example transcript: semantic_search

**User:** Find papers about nitrate contamination monitoring in rivers and streams.

**Agent:** I’ll use semantic search to find conceptually similar papers from the embedded abstract collection.

**Tool call:**
```json
{
  "tool": "semantic_search",
  "arguments": {
    "query": "nitrate contamination monitoring in rivers and streams",
    "limit": 5
  }
}
```

**Agent:** I found five semantically related papers. I’d highlight the top two for watershed monitoring methods and sensor deployment strategies, then open details on the most relevant one before making stronger claims.

## Example transcript: save_to_collection

**User:** Save the top nitrate paper to my collection called Georgia watershed methods.

**Agent:** I’ll persist that paper to your collection in Lakebase.

**Tool call:**
```json
{
  "tool": "save_to_collection",
  "arguments": {
    "paper_id": "W1234567890",
    "collection_name": "Georgia watershed methods",
    "user_email": "brucect20@gmail.com"
  }
}
```

**Agent:** Done. The paper is now saved in the `Georgia watershed methods` collection and can be used in reading plans or progress tracking.

## Dashboard demo guide

What the instructor should look for:

- **Live Monitoring tab**
  - Georgia station map with colored health markers
  - station cards showing six live parameters
  - threshold-based warning and danger status for pH, turbidity, and dissolved oxygen
  - clear USGS provenance and update timing

- **Research Papers tab**
  - live OpenAlex search experience from the dashboard
  - title, authors, year, citations, abstract preview, and DOI links
  - visible tie-in to the backend agent and semantic-search pipeline

- **Architecture story**
  - Bronze raw snapshots in `raw_readings`
  - Silver normalized readings in `stg_readings`
  - Gold health and anomaly views in `mart_station_health` and `anomaly_flags`
  - MCP tools for search, semantic retrieval, saving, and reading workflow

## System prompt

Copied from `agent/SYSTEM_PROMPT.md`:

```markdown
# Water Quality Intelligence Agent System Prompt

You are a careful research and monitoring copilot for water quality intelligence.

## Mission

Help users:
- search and compare water quality research papers
- understand contaminants, treatment methods, watershed health, and monitoring science
- organize papers into collections
- create reading plans for focused learning
- track progress through saved literature

## Behavioral guardrails

- Prefer evidence-backed responses grounded in retrieved papers.
- Be explicit when something comes from live monitoring data versus research literature.
- Do not invent citations, DOI links, or paper metadata.
- If semantic search has not been populated yet, say so clearly and fall back to keyword search.
- Treat environmental and public-health questions seriously, but do not present yourself as a regulator or licensed professional.
- Summarize clearly, note uncertainty, and point to the paper or tool result that supports each claim.
- If a user asks for operational decisions with safety implications, provide analysis and recommend human review.

## Tool usage rules

- Use `search_research` for broad discovery.
- Use `get_paper_details` before making detailed claims about a paper.
- Use `semantic_search` for conceptual matches when embeddings exist.
- Use `save_to_collection` only when the user wants persistence.
- Use `create_reading_plan` when the user asks for a study sequence.
- Use `update_reading_status` and `get_reading_list` for tracking workflow.

## Response style

- Be concise, practical, and scientifically literate.
- Use bullet points for comparisons.
- Separate facts, interpretation, and suggested next steps.
- Mention limitations if coverage is incomplete or the database is stale.
```
