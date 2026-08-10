from __future__ import annotations

import os
from datetime import datetime
from typing import Any

APP_NAME = os.getenv("DATABRICKS_APP_NAME", "")
IS_DASHBOARD = "dashboard" in APP_NAME.lower()
PORT = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))

USGS_URL = (
    "https://waterservices.usgs.gov/nwis/iv/?format=json"
    "&sites=02334430,02334480,02388985,02389150,02394682"
    "&parameterCd=00010,00400,63680,00300,00060,00095&siteStatus=all"
)

STATION_META: dict[str, dict[str, Any]] = {
    "02394682": {
        "name": "Richland Creek at Old Dallas Rd",
        "location": "Dallas, GA",
        "coords": (76, 74),
        "lat": 33.9286,
        "lon": -84.8409,
    },
    "02334430": {
        "name": "Chattahoochee River at Buford Dam",
        "location": "Buford, GA",
        "coords": (73, 30),
        "lat": 34.1576,
        "lon": -84.0713,
    },
    "02388985": {
        "name": "Russell Creek near Dawsonville",
        "location": "Dawsonville, GA",
        "coords": (62, 24),
        "lat": 34.3937,
        "lon": -84.1191,
    },
    "02389150": {
        "name": "Etowah River at GA 9",
        "location": "Dawsonville, GA",
        "coords": (58, 29),
        "lat": 34.4215,
        "lon": -84.1184,
    },
    "02334480": {
        "name": "Richland Creek at Suwanee Dam Rd",
        "location": "Buford, GA",
        "coords": (78, 35),
        "lat": 34.1228,
        "lon": -84.0062,
    },
}

PARAM_META = {
    "00010": ("water_temp_f", "Water Temp", "°F"),
    "00400": ("ph", "pH", "pH"),
    "63680": ("turbidity", "Turbidity", "FNU"),
    "00300": ("dissolved_oxygen", "Dissolved Oxygen", "mg/L"),
    "00060": ("flow", "Flow", "cfs"),
    "00095": ("conductance", "Conductance", "µS/cm"),
}

OPENALEX_URL = "https://api.openalex.org/works"
MAILTO = "brucect20@gmail.com"


def c_to_f(value: float | None) -> float | None:
    if value is None:
        return None
    return round((value * 9 / 5) + 32, 1)


def to_float(value: Any) -> float | None:
    try:
        if value in (None, "", "NaN"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def severity_for_metric(metric: str, value: float | None) -> str:
    if value is None:
        return "unknown"
    if metric == "ph":
        if value < 6.5 or value > 8.5:
            return "danger"
        if value < 6.8 or value > 8.0:
            return "warning"
        return "normal"
    if metric == "turbidity":
        if value > 10:
            return "danger"
        if value > 5:
            return "warning"
        return "normal"
    if metric == "dissolved_oxygen":
        if value < 4:
            return "danger"
        if value < 5:
            return "warning"
        return "normal"
    return "normal"


def overall_status(station: dict[str, Any]) -> str:
    severities = [
        severity_for_metric("ph", station.get("ph")),
        severity_for_metric("turbidity", station.get("turbidity")),
        severity_for_metric("dissolved_oxygen", station.get("dissolved_oxygen")),
    ]
    if "danger" in severities:
        return "danger"
    if "warning" in severities:
        return "warning"
    if "normal" in severities:
        return "normal"
    return "unknown"


def format_value(value: float | None, unit: str) -> str:
    if value is None:
        return "--"
    digits = 1 if abs(value) < 1000 else 0
    return f"{value:.{digits}f} {unit}".strip()


def fetch_usgs_data() -> tuple[list[dict[str, Any]], str | None, str | None]:
    import requests

    stations = {
        site_id: {
            "site_id": site_id,
            **meta,
            "water_temp_f": None,
            "ph": None,
            "turbidity": None,
            "dissolved_oxygen": None,
            "flow": None,
            "conductance": None,
            "last_updated": None,
        }
        for site_id, meta in STATION_META.items()
    }

    try:
        response = requests.get(USGS_URL, timeout=20)
        response.raise_for_status()
        payload = response.json()
        series = payload.get("value", {}).get("timeSeries", [])
        for item in series:
            variable = item.get("variable", {})
            code = (variable.get("variableCode") or [{}])[0].get("value")
            source = item.get("sourceInfo", {})
            site_id = (source.get("siteCode") or [{}])[0].get("value")
            values = item.get("values") or []
            latest = None
            for bucket in values:
                readings = bucket.get("value") or []
                if readings:
                    latest = readings[-1]
            if not latest or site_id not in stations or code not in PARAM_META:
                continue

            field_name, _, _ = PARAM_META[code]
            reading_value = to_float(latest.get("value"))
            if code == "00010":
                reading_value = c_to_f(reading_value)
            stations[site_id][field_name] = reading_value
            stations[site_id]["last_updated"] = latest.get("dateTime") or stations[site_id]["last_updated"]

        station_list = []
        max_updated = None
        for station in stations.values():
            station["status"] = overall_status(station)
            station["ph_status"] = severity_for_metric("ph", station.get("ph"))
            station["turbidity_status"] = severity_for_metric("turbidity", station.get("turbidity"))
            station["dissolved_oxygen_status"] = severity_for_metric("dissolved_oxygen", station.get("dissolved_oxygen"))
            iso = station.get("last_updated")
            if iso:
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    station["last_updated_display"] = dt.strftime("%Y-%m-%d %H:%M UTC")
                    if max_updated is None or dt > max_updated:
                        max_updated = dt
                except ValueError:
                    station["last_updated_display"] = iso
            else:
                station["last_updated_display"] = "Unavailable"
            station_list.append(station)

        station_list.sort(key=lambda s: (s["status"], s["name"]))
        return station_list, max_updated.strftime("%Y-%m-%d %H:%M UTC") if max_updated else None, None
    except Exception as exc:  # noqa: BLE001
        return list(stations.values()), None, f"USGS feed unavailable: {exc}"


def reconstruct_abstract(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in inverted.items():
        for index in indexes:
            positions[index] = token
    return " ".join(token for _, token in sorted(positions.items())).strip()


def search_openalex(query: str, limit: int = 10) -> tuple[list[dict[str, Any]], str | None]:
    import requests

    try:
        response = requests.get(
            OPENALEX_URL,
            params={"search": query, "per-page": min(limit, 10), "mailto": MAILTO},
            timeout=20,
        )
        response.raise_for_status()
        results = []
        for work in response.json().get("results", []):
            authors = [
                authorship.get("author", {}).get("display_name")
                for authorship in work.get("authorships", [])[:5]
                if authorship.get("author", {}).get("display_name")
            ]
            doi = work.get("doi")
            results.append(
                {
                    "title": work.get("title") or "Untitled paper",
                    "authors": authors,
                    "year": work.get("publication_year"),
                    "citations": work.get("cited_by_count", 0),
                    "abstract": reconstruct_abstract(work),
                    "doi": doi,
                    "doi_link": doi if doi and doi.startswith("http") else (f"https://doi.org/{doi}" if doi else None),
                    "paper_id": (work.get("id") or "").split("/")[-1],
                }
            )
        return results, None
    except Exception as exc:  # noqa: BLE001
        return [], f"OpenAlex search failed: {exc}"


if IS_DASHBOARD:
    from flask import Flask, render_template_string, request

    app = Flask(__name__)

    TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Water Quality Intelligence Platform</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    :root {
      --bg: #07111b;
      --panel: #0d1b2a;
      --border: #1d3b58;
      --text: #e8f2fb;
      --muted: #9bb4cb;
      --blue: #33b5e5;
      --blue-2: #5fd0ff;
      --green: #22c55e;
      --yellow: #f59e0b;
      --red: #ef4444;
      --shadow: rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #0b2133 0%, var(--bg) 52%);
      color: var(--text);
    }
    .shell { max-width: 1400px; margin: 0 auto; padding: 24px; }
    .hero {
      padding: 28px;
      border: 1px solid var(--border);
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(19,54,88,.95), rgba(9,23,39,.95));
      box-shadow: 0 18px 40px var(--shadow);
      margin-bottom: 20px;
    }
    .hero h1 { margin: 0 0 10px; font-size: clamp(2rem, 3vw, 3rem); }
    .hero p { margin: 0; color: var(--muted); max-width: 860px; line-height: 1.55; }
    .tabs { display: flex; gap: 10px; margin: 18px 0 22px; flex-wrap: wrap; }
    .tab {
      text-decoration: none; color: var(--muted); padding: 12px 18px; border-radius: 999px;
      border: 1px solid var(--border); background: rgba(13,27,42,.9); font-weight: 700;
    }
    .tab.active { color: #06131f; background: linear-gradient(135deg, var(--blue-2), var(--blue)); border-color: transparent; }
    .grid { display: grid; gap: 18px; }
    .monitor-grid { grid-template-columns: 1.1fr .9fr; align-items: start; }
    .panel {
      background: rgba(13, 27, 42, 0.94);
      border: 1px solid var(--border);
      border-radius: 22px;
      padding: 20px;
      box-shadow: 0 16px 30px var(--shadow);
    }
    .panel h2, .panel h3 { margin-top: 0; }
    .subtle { color: var(--muted); }
    .meta-row { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; }
    .chip { padding: 8px 12px; border-radius: 999px; background: rgba(51,181,229,.12); color: var(--blue-2); border: 1px solid rgba(95,208,255,.18); font-size: .92rem; }
    .legend { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }
    .legend span { display: inline-flex; gap: 8px; align-items: center; color: var(--muted); }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .dot.normal, .status.normal { background: var(--green); }
    .dot.warning, .status.warning { background: var(--yellow); }
    .dot.danger, .status.danger { background: var(--red); }
    .dot.unknown, .status.unknown { background: #64748b; }
    .ga-map {
      position: relative; min-height: 480px; overflow: hidden;
      border-radius: 18px; border: 1px solid var(--border);
      box-shadow: 0 12px 28px var(--shadow);
    }
    #topoMap { width: 100%; height: 480px; border-radius: 18px; }
    .leaflet-popup-content-wrapper { background: #0d1b2a; color: var(--text); border: 1px solid var(--border); border-radius: 12px; }
    .leaflet-popup-tip { background: #0d1b2a; }
    .popup-station { font-size: .9rem; }
    .popup-station h4 { margin: 0 0 6px; color: var(--blue-2); }
    .popup-metric { display: flex; justify-content: space-between; gap: 12px; padding: 2px 0; }
    .popup-metric label { color: var(--muted); }
    .popup-status { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: .75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 6px; }
    .popup-status.normal { background: rgba(34,197,94,.2); color: #86efac; }
    .popup-status.warning { background: rgba(245,158,11,.2); color: #fcd34d; }
    .popup-status.danger { background: rgba(239,68,68,.2); color: #fca5a5; }
    .popup-status.unknown { background: rgba(100,116,139,.2); color: #cbd5e1; }
    .marker {
      position: absolute; transform: translate(-50%, -50%);
      width: 18px; height: 18px; border-radius: 50%; border: 3px solid white;
      box-shadow: 0 0 0 6px rgba(255,255,255,.06);
    }
    .marker-label {
      position: absolute; transform: translate(-50%, 16px); min-width: 160px; text-align: center;
      font-size: .8rem; color: var(--text); pointer-events: none;
    }
    .station-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .station-card {
      border-radius: 18px; padding: 18px; border: 1px solid rgba(255,255,255,.05);
      background: linear-gradient(180deg, rgba(15,28,44,.95), rgba(8,18,30,.95));
    }
    .station-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
    .status-pill {
      padding: 8px 12px; border-radius: 999px; color: white; font-size: .82rem; font-weight: 800; text-transform: uppercase;
    }
    .status-pill.normal { background: rgba(34,197,94,.18); color: #86efac; }
    .status-pill.warning { background: rgba(245,158,11,.18); color: #fcd34d; }
    .status-pill.danger { background: rgba(239,68,68,.18); color: #fca5a5; }
    .status-pill.unknown { background: rgba(100,116,139,.18); color: #cbd5e1; }
    .metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 14px; }
    .metric {
      border: 1px solid rgba(255,255,255,.05); border-radius: 14px; padding: 12px;
      background: rgba(255,255,255,.02);
    }
    .metric label { display: block; color: var(--muted); font-size: .82rem; margin-bottom: 6px; }
    .metric strong { font-size: 1rem; }
    .metric.normal { border-color: rgba(34,197,94,.35); }
    .metric.warning { border-color: rgba(245,158,11,.45); }
    .metric.danger { border-color: rgba(239,68,68,.45); }
    .metric.unknown { border-color: rgba(100,116,139,.35); }
    .search-bar { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
    .search-bar input {
      flex: 1 1 420px; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--border);
      background: #091724; color: var(--text); font-size: 1rem;
    }
    .search-bar button {
      padding: 14px 18px; border-radius: 14px; border: 0; cursor: pointer; font-weight: 800;
      background: linear-gradient(135deg, var(--blue-2), var(--blue)); color: #04131d;
    }
    .paper-list { display: grid; gap: 16px; }
    .paper-card {
      border-radius: 18px; padding: 18px; border: 1px solid rgba(255,255,255,.06);
      background: linear-gradient(180deg, rgba(14,29,45,.96), rgba(8,17,28,.96));
    }
    .paper-card h3 { margin: 0 0 10px; }
    .paper-meta { color: var(--muted); margin-bottom: 10px; font-size: .95rem; }
    .paper-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .badge { border-radius: 999px; padding: 7px 10px; font-size: .8rem; color: var(--blue-2); background: rgba(51,181,229,.12); border: 1px solid rgba(95,208,255,.16); }
    a.paper-link { color: var(--blue-2); text-decoration: none; font-weight: 700; }
    .notice, .error { padding: 14px 16px; border-radius: 14px; margin-bottom: 16px; }
    .notice { background: rgba(51,181,229,.10); color: #bfe9ff; border: 1px solid rgba(95,208,255,.18); }
    .error { background: rgba(239,68,68,.12); color: #fecaca; border: 1px solid rgba(239,68,68,.22); }
    @media (max-width: 980px) {
      .monitor-grid { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 640px) {
      .shell { padding: 16px; }
      .hero, .panel, .station-card, .paper-card { border-radius: 18px; }
      .metrics { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>💧 Water Quality Intelligence Platform</h1>
      <p>Real-time Georgia surface water intelligence plus an AI-assisted research workspace powered by USGS NWIS and OpenAlex.</p>
      <div class="meta-row">
        <span class="chip">5 Georgia monitoring stations</span>
        <span class="chip">6 live water quality parameters</span>
        <span class="chip">Research search + semantic pipeline</span>
      </div>
    </section>

    <nav class="tabs">
      <a class="tab {{ 'active' if active_tab == 'monitoring' else '' }}" href="/?tab=monitoring">Live Monitoring</a>
      <a class="tab {{ 'active' if active_tab == 'research' else '' }}" href="/?tab=research{% if query %}&q={{ query|urlencode }}{% endif %}">Research Papers</a>
    </nav>

    {% if active_tab == 'monitoring' %}
      {% if monitor_error %}<div class="error">{{ monitor_error }}</div>{% endif %}
      <div class="grid monitor-grid">
        <section class="panel">
          <h2>Georgia Station Health Map</h2>
          <p class="subtle">Color-coded site status based on pH, turbidity, and dissolved oxygen thresholds.</p>
          <div class="legend">
            <span><i class="dot normal"></i> Normal</span>
            <span><i class="dot warning"></i> Warning</span>
            <span><i class="dot danger"></i> Danger</span>
            <span><i class="dot unknown"></i> Missing data</span>
          </div>
          <div class="ga-map" style="margin-top:16px;">
            <div id="topoMap"></div>
          </div>
        </section>

        <section class="panel">
          <h2>Monitoring Summary</h2>
          <p class="subtle">Last updated: {{ last_updated or 'Unavailable' }}</p>
          <div class="meta-row">
            <span class="chip">Data from USGS NWIS</span>
            <span class="chip">Updates every 15-30 minutes</span>
          </div>
          <div style="margin-top:18px; display:grid; gap:12px;">
            {% for station in stations %}
              <div style="display:flex; justify-content:space-between; gap:12px; padding:14px; border-radius:14px; background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.05);">
                <div>
                  <strong>{{ station.name }}</strong>
                  <div class="subtle">{{ station.location }}</div>
                </div>
                <span class="status-pill {{ station.status }}">{{ station.status }}</span>
              </div>
            {% endfor %}
          </div>
        </section>
      </div>

      <section class="panel" style="margin-top:18px;">
        <h2>Live Station Cards</h2>
        <div class="station-grid">
          {% for station in stations %}
            <article class="station-card">
              <div class="station-head">
                <div>
                  <h3 style="margin:0 0 6px;">{{ station.name }}</h3>
                  <div class="subtle">{{ station.location }}</div>
                </div>
                <span class="status-pill {{ station.status }}">{{ station.status }}</span>
              </div>
              <div class="metrics">
                <div class="metric normal">
                  <label>Water Temp</label>
                  <strong>{{ format_value(station.water_temp_f, '°F') }}</strong>
                </div>
                <div class="metric {{ station.ph_status }}">
                  <label>pH</label>
                  <strong>{{ format_value(station.ph, '') }}</strong>
                </div>
                <div class="metric {{ station.turbidity_status }}">
                  <label>Turbidity</label>
                  <strong>{{ format_value(station.turbidity, 'FNU') }}</strong>
                </div>
                <div class="metric {{ station.dissolved_oxygen_status }}">
                  <label>Dissolved Oxygen</label>
                  <strong>{{ format_value(station.dissolved_oxygen, 'mg/L') }}</strong>
                </div>
                <div class="metric normal">
                  <label>Flow</label>
                  <strong>{{ format_value(station.flow, 'cfs') }}</strong>
                </div>
                <div class="metric normal">
                  <label>Conductance</label>
                  <strong>{{ format_value(station.conductance, 'µS/cm') }}</strong>
                </div>
              </div>
              <div class="subtle" style="margin-top:14px;">Last updated: {{ station.last_updated_display }}</div>
            </article>
          {% endfor %}
        </div>
      </section>
    {% else %}
      <section class="panel">
        <h2>OpenAlex Research Search</h2>
        <p class="subtle">Search papers on water quality, treatment, contaminants, watershed management, and monitoring science.</p>
        <form method="GET" class="search-bar">
          <input type="hidden" name="tab" value="research" />
          <input type="text" name="q" value="{{ query }}" placeholder="Try: drinking water contamination, watershed monitoring, PFAS treatment" />
          <button type="submit">Search Papers</button>
        </form>
        <div class="notice">AI research side supports paper search now, with Lakebase saving, semantic embeddings, and MCP tools defined in the project backend.</div>
        {% if research_error %}<div class="error">{{ research_error }}</div>{% endif %}
        <div class="paper-list">
          {% for paper in papers %}
            <article class="paper-card">
              <h3>{{ paper.title }}</h3>
              <div class="paper-meta">{{ paper.authors|join(', ') if paper.authors else 'Unknown authors' }}{% if paper.year %} • {{ paper.year }}{% endif %}</div>
              <div class="paper-badges">
                <span class="badge">Citations: {{ paper.citations }}</span>
                {% if paper.paper_id %}<span class="badge">OpenAlex: {{ paper.paper_id }}</span>{% endif %}
              </div>
              <div class="subtle" style="line-height:1.6;">{{ (paper.abstract[:420] ~ ('...' if paper.abstract|length > 420 else '')) if paper.abstract else 'No abstract preview available.' }}</div>
              {% if paper.doi_link %}
                <div style="margin-top:14px;"><a class="paper-link" href="{{ paper.doi_link }}" target="_blank" rel="noopener noreferrer">Open DOI ↗</a></div>
              {% endif %}
            </article>
          {% endfor %}
          {% if not papers and not research_error %}
            <div class="notice">No results yet. Run a search to explore recent literature.</div>
          {% endif %}
        </div>
      </section>
    {% endif %}
  </div>
  {% if active_tab == 'monitoring' %}
  <script>
    (function() {
      const stations = {{ stations | tojson | safe }};
      const statusColors = { normal: '#22c55e', warning: '#f59e0b', danger: '#ef4444', unknown: '#64748b' };

      const map = L.map('topoMap', { scrollWheelZoom: false }).setView([34.25, -84.3], 9);

      // OpenTopoMap — real topographic tiles with terrain, contour lines, elevation
      L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        maxZoom: 17,
        attribution: '© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors'
      }).addTo(map);

      stations.forEach(function(s) {
        const color = statusColors[s.status] || '#64748b';
        const icon = L.divIcon({
          className: 'custom-marker',
          html: '<div style="width:20px;height:20px;border-radius:50%;background:' + color + ';border:3px solid white;box-shadow:0 0 8px rgba(0,0,0,.5);"></div>',
          iconSize: [20, 20],
          iconAnchor: [10, 10]
        });

        const popup = '<div class="popup-station">' +
          '<span class="popup-status ' + s.status + '">' + s.status + '</span>' +
          '<h4>' + s.name + '</h4>' +
          '<div style="color:#9bb4cb;font-size:.8rem;margin-bottom:6px;">' + s.location + '</div>' +
          '<div class="popup-metric"><label>Water Temp</label><span>' + (s.water_temp_f != null ? s.water_temp_f + ' °F' : '--') + '</span></div>' +
          '<div class="popup-metric"><label>pH</label><span>' + (s.ph != null ? s.ph : '--') + '</span></div>' +
          '<div class="popup-metric"><label>Turbidity</label><span>' + (s.turbidity != null ? s.turbidity + ' FNU' : '--') + '</span></div>' +
          '<div class="popup-metric"><label>Dissolved O₂</label><span>' + (s.dissolved_oxygen != null ? s.dissolved_oxygen + ' mg/L' : '--') + '</span></div>' +
          '<div class="popup-metric"><label>Flow</label><span>' + (s.flow != null ? s.flow + ' cfs' : '--') + '</span></div>' +
          '<div class="popup-metric"><label>Conductance</label><span>' + (s.conductance != null ? s.conductance + ' µS/cm' : '--') + '</span></div>' +
          '<div style="margin-top:6px;color:#7a8da8;font-size:.75rem;">Updated: ' + (s.last_updated_display || 'N/A') + '</div>' +
          '</div>';

        L.marker([s.lat, s.lon], { icon: icon }).addTo(map).bindPopup(popup);
      });
    })();
  </script>
  {% endif %}
</body>
</html>
    """

    @app.route("/", methods=["GET"])
    def index() -> str:
        active_tab = request.args.get("tab", "monitoring")
        if active_tab not in {"monitoring", "research"}:
            active_tab = "monitoring"
        stations, last_updated, monitor_error = fetch_usgs_data()
        query = request.args.get("q", "water quality monitoring")
        papers, research_error = search_openalex(query, limit=10) if active_tab == "research" else ([], None)
        return render_template_string(
            TEMPLATE,
            active_tab=active_tab,
            stations=stations,
            last_updated=last_updated,
            monitor_error=monitor_error,
            query=query,
            papers=papers,
            research_error=research_error,
            format_value=format_value,
        )

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=PORT, debug=False)
else:
    import sys
    from pathlib import Path

    MCP_DIR = Path(__file__).resolve().parent / "mcp_server"
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))

    from mcp_server.research_mcp_server import ensure_schema, mcp

    if __name__ == "__main__":
        ensure_schema()
        mcp.run(transport="sse", host="0.0.0.0", port=PORT)
