import json
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

DATA_DIR     = Path(__file__).parent / "NTEC_Drilling"
LOGS_FILE    = DATA_DIR / "all_geology_logs.csv"
COLLARS_FILE = DATA_DIR / "Collars_fence.csv"
OUT_FILE     = DATA_DIR / "borehole_cross_section_north_labeled.html"

transformer = Transformer.from_crs("EPSG:32612", "EPSG:4326", always_xy=True)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def utm_to_latlon(easting, northing):
    lon, lat = transformer.transform(easting, northing)
    return lat, lon


def extract_rock_code(lith_str):
    """Return 1-2 char primary rock-type code from a lithology string."""
    if pd.isna(lith_str) or lith_str == "nan":
        return ""
    upper = str(lith_str).upper()
    if "TUFF" in upper:
        return "T"
    first_part = str(lith_str).split("/")[0].strip()
    return first_part.split()[0].upper()[:2] if first_part else ""


# Deduplicate collars (keep first entry per hole) and persist the clean file
collars = pd.read_csv(COLLARS_FILE)
n_before = len(collars)
collars = collars.drop_duplicates(subset=["Hole ID"], keep="first").reset_index(drop=True)
if len(collars) < n_before:
    collars.to_csv(COLLARS_FILE, index=False)
    print(f"Collars: removed {n_before - len(collars)} duplicate(s), saved {COLLARS_FILE.name}")

collars["lat"], collars["lon"] = zip(
    *collars.apply(lambda r: utm_to_latlon(r["Easting"], r["Northing"]), axis=1)
)

logs = pd.read_csv(LOGS_FILE).rename(columns={"Rock 1": "Lith"})

# ---------------------------------------------------------------------------
# PCA fence axis – flipped to look north
# ---------------------------------------------------------------------------

Xc = collars.Easting - collars.Easting.mean()
Yc = collars.Northing - collars.Northing.mean()
_, _, Vt = np.linalg.svd(np.c_[Xc, Yc], full_matrices=False)
d = Vt[0]
proj = Xc * d[0] + Yc * d[1]

# Optimal perpendicular view:
#  - N-S-trending fence → orient so northernmost holes are on the right
#  - E-W-trending fence → orient so easternmost holes are on the right
if abs(d[1]) >= abs(d[0]):            # fence trends more N-S
    if np.corrcoef(proj, Yc)[0, 1] < 0:
        d = -d
else:                                  # fence trends more E-W
    if np.corrcoef(proj, Xc)[0, 1] < 0:
        d = -d

collars["dist"] = Xc * d[0] + Yc * d[1]

# Right-hand viewer position: standing 90° clockwise from the d direction
# (i.e., to the right when walking along positive dist), looking inward.
def _cardinal16(az):
    names = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
             'S','SSW','SW','WSW','W','WNW','NW','NNW']
    return names[int((float(az) + 11.25) / 22.5) % 16]

_d_az  = float(np.degrees(np.arctan2(d[0], d[1])) % 360)
_vw_az = (_d_az + 90.0) % 360          # viewer azimuth (right-hand convention)
SECTION_TITLE = (
    f"Borehole Fence  |  View from {_cardinal16(_vw_az)}"
    f"  (section strikes {_cardinal16(_d_az)}-{_cardinal16((_d_az+180)%360)})"
)
SECTION_XAXIS = (
    f"← {_cardinal16((_d_az+180)%360)}"
    f"  ·  {_cardinal16(_d_az)} →"
)

data = logs.merge(collars, left_on="Hole_id", right_on="Hole ID")
data["Top"] = data["Elevation_meters"] - data["From"]
data["Bot"] = data["Elevation_meters"] - data["To"]
data["X"] = data["dist"] / 50.0

# ---------------------------------------------------------------------------
# Colour / label maps
# ---------------------------------------------------------------------------

COLORS = {
    "CO": "#d9c6b0",
    "CY": "#bfa58a",
    "LS": "#cfd8dc",
    "CC": "#cfd8dc",
    "SS": "#f1c27d",
    "T":  "#c97b63",
    "B":  "#555555",
}

LABELS = {
    "CO": "Colluvium",
    "CY": "Clay",
    "LS": "Limestone / Calcrete",
    "SS": "Sandstone",
    "T":  "Tuff",
    "B":  "Basalt",
}

# ---------------------------------------------------------------------------
# Build Plotly traces
# ---------------------------------------------------------------------------

hole_traces: dict[str, list] = {}

for _, r in data.iterrows():
    code = extract_rock_code(r.Lith)
    hole_id = r.Hole_id
    hole_traces.setdefault(hole_id, []).append({
        "type": "scatter",
        "mode": "lines",
        "x": [r.X, r.X],
        "y": [r.Bot, r.Top],
        "line": {"width": 10, "color": COLORS.get(code, "#ffffff")},
        "hoverinfo": "text",
        "text": f"{r.Hole_id}<br>{r.Lith}<br>{r.From}-{r.To} m",
        "showlegend": False,
        "visible": False,
    })

traces = []
for hole_data in hole_traces.values():
    traces.extend(hole_data)

# Hole collar labels
for _, r in collars.iterrows():
    traces.append({
        "type": "scatter",
        "mode": "text",
        "x": [r.dist / 50.0],
        "y": [r.Elevation_meters],
        "text": [r["Hole ID"]],
        "hoverinfo": "skip",
        "showlegend": False,
        "visible": False,
    })

# Legend entries
for k, v in LABELS.items():
    traces.append({
        "type": "scatter",
        "x": [None],
        "y": [None],
        "mode": "lines",
        "line": {"width": 10, "color": COLORS[k]},
        "name": v,
    })

# ---------------------------------------------------------------------------
# Data for JavaScript
# ---------------------------------------------------------------------------

collar_data = [
    {"id": r["Hole ID"], "lat": r["lat"], "lon": r["lon"], "elevation": r["Elevation_meters"]}
    for _, r in collars.iterrows()
]

hole_trace_indices: dict[str, list[int]] = {}
idx = 0
for hole_id, hole_data in hole_traces.items():
    hole_trace_indices[hole_id] = list(range(idx, idx + len(hole_data)))
    idx += len(hole_data)

# Per-hole interval data for JS interpolation (surface-first, elevation coords)
hole_intervals_data: dict[str, list] = {}
hole_dist_data: dict[str, float] = {}
for hole_id, group in data.groupby("Hole_id"):
    intervals = []
    for _, r in group.sort_values("Top", ascending=False).iterrows():
        code = extract_rock_code(str(r.Lith))
        if code:
            intervals.append({
                "code": code,
                "top": round(float(r.Top), 2),
                "bot": round(float(r.Bot), 2),
            })
    hole_intervals_data[hole_id] = intervals
    hole_dist_data[hole_id] = round(float(group["X"].iloc[0]), 4)

# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body {{ margin: 0; padding: 10px 20px; font-family: Arial, sans-serif; }}
  .toolbar {{ margin-bottom: 8px; }}
  .toolbar button {{
    padding: 5px 14px; margin-right: 6px; font-size: 13px;
    border: 1px solid #aaa; border-radius: 4px;
    background: #f5f5f5; cursor: pointer;
  }}
  .toolbar button:hover {{ background: #e0e0e0; }}
  .container {{ display: flex; height: calc(100vh - 60px); }}
  #map {{ width: 50%; height: 100%; margin-right: 10px; }}
  #section {{ width: 50%; height: 100%; }}
  .hole-marker {{
    width: 0; height: 0;
    border-left: 5pt solid transparent;
    border-right: 5pt solid transparent;
    border-top: 10pt solid #3388ff;
    cursor: pointer;
    filter: drop-shadow(0 0 3pt rgba(0,0,0,0.3));
  }}
  .hole-marker.active {{ border-top-color: #ff3388; }}
</style>
</head>
<body>
<div class="toolbar">
  <button onclick="deselectAll()">Deselect All</button>
  <button id="fillBtn" onclick="toggleFill()">Disable Fill</button>
</div>
<div class="container">
  <div id="map"></div>
  <div id="section"></div>
</div>
<script>
const collarData = {json.dumps(collar_data)};
const holeTraceIndices = {json.dumps(hole_trace_indices)};
const COLORS_JS = {json.dumps(COLORS)};
const holeIntervals = {json.dumps(hole_intervals_data)};
const holeDist = {json.dumps(hole_dist_data)};
const baseTraces = {json.dumps(traces)};
let activeHoles = new Set(); // All holes start hidden; user selects
let fillEnabled = true;

const map = L.map('map').setView([collarData[0].lat, collarData[0].lon], 13);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap contributors'
}}).addTo(map);

const markers = {{}};
collarData.forEach(collar => {{
  const marker = L.marker([collar.lat, collar.lon], {{
    icon: L.divIcon({{ className: 'hole-marker', html: '', iconSize: [10, 20], iconAnchor: [5, 0] }})
  }})
    .addTo(map)
    .bindPopup(`<b>${{collar.id}}</b><br>Elevation: ${{collar.elevation}}m`)
    .on('click', () => toggleHole(collar.id));
  markers[collar.id] = marker;
  updateMarkerStyle(collar.id);
}});

const group = new L.featureGroup(Object.values(markers));
map.fitBounds(group.getBounds().pad(0.1));

function updateMarkerStyle(holeId) {{
  const isActive = activeHoles.has(holeId);
  markers[holeId].setIcon(L.divIcon({{
    className: isActive ? 'hole-marker active' : 'hole-marker',
    html: '', iconSize: [10, 20], iconAnchor: [5, 0]
  }}));
}}

function toggleHole(holeId) {{
  activeHoles.has(holeId) ? activeHoles.delete(holeId) : activeHoles.add(holeId);
  updateMarkerStyle(holeId);
  updatePlot();
}}

function toggleFill() {{
  fillEnabled = !fillEnabled;
  document.getElementById('fillBtn').textContent = fillEnabled ? 'Disable Fill' : 'Enable Fill';
  updatePlot();
}}

function deselectAll() {{
  activeHoles.clear();
  Object.keys(markers).forEach(updateMarkerStyle);
  updatePlot();
}}

// ── interpolation helpers ────────────────────────────────────────────────────

function getRockAt(intervals, elev) {{
  for (const iv of intervals) {{
    if (iv.bot <= elev && elev <= iv.top) return iv.code;
  }}
  return null;
}}

function filledPoly(xs, ys, code) {{
  return {{
    type: 'scatter', mode: 'lines', x: xs, y: ys,
    fill: 'toself',
    fillcolor: COLORS_JS[code] || '#dddddd',
    line: {{ width: 0.5, color: 'rgba(60,60,60,0.3)' }},
    hoverinfo: 'skip', showlegend: false,
  }};
}}

function computeInterpTraces(sortedHoles) {{
  if (!fillEnabled) return [];
  const out = [];
  for (let h = 0; h < sortedHoles.length - 1; h++) {{
    const hA = sortedHoles[h], hB = sortedHoles[h + 1];
    const x1 = holeDist[hA], x2 = holeDist[hB], xMid = (x1 + x2) / 2;
    const intA = holeIntervals[hA] || [], intB = holeIntervals[hB] || [];
    if (!intA.length || !intB.length) continue;

    // Elevation extent of each log
    const topA = Math.max(...intA.map(v => v.top));
    const botA = Math.min(...intA.map(v => v.bot));
    const topB = Math.max(...intB.map(v => v.top));
    const botB = Math.min(...intB.map(v => v.bot));
    const dA = topA - botA, dB = topB - botB;
    if (dA <= 0 || dB <= 0) continue;

    // Collect fraction-space boundaries from both logs (0 = surface, 1 = TD)
    const fracs = new Set([0, 1]);
    intA.forEach(iv => {{
      fracs.add((topA - iv.top) / dA);
      fracs.add((topA - iv.bot) / dA);
    }});
    intB.forEach(iv => {{
      fracs.add((topB - iv.top) / dB);
      fracs.add((topB - iv.bot) / dB);
    }});
    const sf = [...fracs].sort((a, b) => a - b);

    for (let i = 0; i < sf.length - 1; i++) {{
      const f1 = sf[i], f2 = sf[i + 1], fM = (f1 + f2) / 2;
      // Real elevations at the top and bottom of this fraction strip
      const eA1 = topA - f1 * dA, eA2 = topA - f2 * dA;
      const eB1 = topB - f1 * dB, eB2 = topB - f2 * dB;
      const cA = getRockAt(intA, topA - fM * dA);
      const cB = getRockAt(intB, topB - fM * dB);
      if (!cA && !cB) continue;

      if (!cA || !cB || cA === cB) {{
        // Same rock type (or one side absent) – single quadrilateral
        out.push(filledPoly([x1, x1, x2, x2, x1], [eA2, eA1, eB1, eB2, eA2], cA || cB));
      }} else {{
        // Different rock types – split at horizontal midpoint so units don't overlap
        const eM1 = (eA1 + eB1) / 2, eM2 = (eA2 + eB2) / 2;
        out.push(filledPoly([x1,   x1,   xMid, xMid, x1  ], [eA2, eA1, eM1, eM2, eA2], cA));
        out.push(filledPoly([xMid, xMid, x2,   x2,   xMid], [eM2, eM1, eB1, eB2, eM2], cB));
      }}
    }}
  }}
  return out;
}}

// ── full plot update (visibility + interpolation) ────────────────────────────

function buildUpdatedBase() {{
  const result = baseTraces.map(t => Object.assign({{}}, t));
  // Lith interval traces
  Object.entries(holeTraceIndices).forEach(([hId, idxs]) => {{
    const vis = activeHoles.has(hId);
    idxs.forEach(i => {{ result[i].visible = vis; }});
  }});
  // Collar label traces
  const nLith = Object.values(holeTraceIndices).reduce((s, a) => s + a.length, 0);
  collarData.forEach((c, j) => {{ result[nLith + j].visible = activeHoles.has(c.id); }});
  // Legend entries stay visible (already set in baseTraces)
  return result;
}}

function updatePlot() {{
  const sorted = [...activeHoles]
    .filter(h => holeDist[h] !== undefined)
    .sort((a, b) => holeDist[a] - holeDist[b]);
  const interp = computeInterpTraces(sorted);
  const updated = buildUpdatedBase();
  // Preserve current zoom level across react calls
  const gd = document.getElementById('section');
  const xl = gd.layout;
  const rl = Object.assign({{}}, layout);
  if (xl && xl.xaxis && xl.xaxis.range) {{
    rl.xaxis = Object.assign({{}}, layout.xaxis, {{range: xl.xaxis.range, autorange: false}});
    rl.yaxis = Object.assign({{}}, layout.yaxis, {{range: xl.yaxis.range, autorange: false}});
  }}
  // interp polygons drawn first (behind borehole log lines)
  Plotly.react('section', [...interp, ...updated], rl);
}}

const layout = {{
  title: '{SECTION_TITLE}',
  xaxis: {{title: '{SECTION_XAXIS}'}},
  yaxis: {{title: 'Elevation (m)'}},
  hovermode: 'closest',
  legend: {{orientation: 'h', x: 0.5, xanchor: 'center', y: -0.25}},
  updatemenus: [{{
    type: 'dropdown', direction: 'down',
    x: 0.5, xanchor: 'center', y: 1.1, yanchor: 'top',
    buttons: [
      {{
        label: 'Hide Cofer Hot Springs Marker',
        method: 'relayout',
        args: [{{shapes: [], annotations: []}}]
      }},
      {{
        label: 'Show Cofer Hot Springs Marker',
        method: 'relayout',
        args: [{{
          shapes: [{{
            type: 'line', x0: 0, x1: 1, y0: 603, y1: 603,
            xref: 'paper', yref: 'y',
            line: {{color: 'blue', width: 2, dash: 'dash'}}
          }}],
          annotations: [{{
            x: 0.5, y: 607, xref: 'paper', yref: 'y',
            text: 'Cofer Hot Springs Elevation',
            showarrow: false, font: {{size: 12, color: 'black'}}
          }}]
        }}]
      }}
    ]
  }}],
  shapes: [{{
    type: 'line', x0: 0, x1: 1, y0: 603, y1: 603,
    xref: 'paper', yref: 'y',
    line: {{color: 'blue', width: 2, dash: 'dash'}}
  }}],
  annotations: [{{
    x: 0.5, y: 607, xref: 'paper', yref: 'y',
    text: 'Cofer Hot Springs Elevation',
    showarrow: false, font: {{size: 12, color: 'black'}}
  }}]
}};
Plotly.newPlot('section', baseTraces, layout);
</script>
</body>
</html>
"""

OUT_FILE.write_text(html, encoding="utf-8")
print(f"Saved: {OUT_FILE}")
webbrowser.open(OUT_FILE.as_uri())
