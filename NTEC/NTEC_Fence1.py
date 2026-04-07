import json
import pandas as pd
import numpy as np
from pyproj import Transformer

# Load collars
collars = pd.read_csv("Collars_fence.csv")

# Convert UTM to lat/lng (assuming UTM Zone 12N)
from pyproj import Transformer
transformer = Transformer.from_crs("EPSG:32612", "EPSG:4326", always_xy=True)

def utm_to_latlon(easting, northing):
    lon, lat = transformer.transform(easting, northing)
    return lat, lon

# Add lat/lng to collars
collars['lat'], collars['lon'] = zip(*collars.apply(lambda row: utm_to_latlon(row['Easting'], row['Northing']), axis=1))

def load_log(fname):
    raw = pd.read_csv(fname, header=None)
    raw.columns = raw.iloc[2]
    df = raw.iloc[3:].copy()
    df = df[pd.to_numeric(df["From"], errors="coerce").notna()]
    df["From"] = df["From"].astype(float)
    df["To"] = df["To"].astype(float)
    df["Lith"] = df["Rock 1"].astype(str)
    return df[["Hole_id", "From", "To", "Lith"]]

def extract_rock_code(lith_str):
    """Extract primary rock type code from lithology string."""
    if pd.isna(lith_str) or lith_str == "nan":
        return ""
    
    upper_lith = str(lith_str).upper()
    
    # Special handling for tuff variants
    if "TUFF" in upper_lith:
        return "T"
    
    # Take first component before "/"
    first_part = str(lith_str).split("/")[0].strip()
    if not first_part:
        return ""
    
    # Take first word, uppercase, 2 chars max
    code = first_part.split()[0].upper()[:2]
    return code

logs = pd.concat([
    load_log("DDH5.csv"),
    load_log("DDH6.csv"),
    load_log("DDH7.csv"),
    load_log("DHQ1.csv"),
    load_log("DHQ18.csv"),
    load_log("DHQ25.csv"),
    load_log("DHQ26.csv"),
])

# PCA fence – flipped to look north
Xc = collars.Easting - collars.Easting.mean()
Yc = collars.Northing - collars.Northing.mean()
_, _, Vt = np.linalg.svd(np.c_[Xc, Yc], full_matrices=False)
d = Vt[0]
collars["dist"] = -(Xc * d[0] + Yc * d[1])

# Merge & elevations
data = logs.merge(collars, left_on="Hole_id", right_on="Hole ID")
data["Top"] = data["Elevation_meters"] - data["From"]
data["Bot"] = data["Elevation_meters"] - data["To"]
data["X"] = data["dist"] / 50.0

colors = {
    "CO": "#d9c6b0",
    "CY": "#bfa58a",
    "LS": "#cfd8dc",
    "CC": "#cfd8dc",
    "SS": "#f1c27d",
    "T":  "#c97b63",
    "B":  "#555555",
}

labels = {
    "CO": "Colluvium",
    "CY": "Clay",
    "LS": "Limestone / Calcrete",
    "SS": "Sandstone",
    "T":  "Tuff",
    "B":  "Basalt",
}

traces = []
hole_traces = {}  # Group traces by hole_id

# Lith intervals
for _, r in data.iterrows():
    code = extract_rock_code(r.Lith)
    hole_id = r.Hole_id
    if hole_id not in hole_traces:
        hole_traces[hole_id] = []
    
    hole_traces[hole_id].append({
        "type": "scatter",
        "mode": "lines",
        "x": [r.X, r.X],
        "y": [r.Bot, r.Top],
        "line": {"width": 10, "color": colors.get(code, "#ffffff")},
        "hoverinfo": "text",
        "text": f"{r.Hole_id}<br>{r.Lith}<br>{r.From}-{r.To} m",
        "showlegend": False,
        "visible": True,
    })

# Convert hole_traces to flat list for Plotly
for hole_id, hole_data in hole_traces.items():
    traces.extend(hole_data)

# Hole labels at collar
for _, r in collars.iterrows():
    traces.append({
        "type": "scatter",
        "mode": "text",
        "x": [r.dist / 50.0],
        "y": [r.Elevation_meters],
        "text": [r["Hole ID"]],
        "hoverinfo": "skip",
        "showlegend": False,
    })

# Legend
for k, v in labels.items():
    traces.append({
        "type": "scatter",
        "x": [None],
        "y": [None],
        "mode": "lines",
        "line": {"width": 10, "color": colors[k]},
        "name": v,
    })

# Prepare collar data for JavaScript
collar_data = []
for _, r in collars.iterrows():
    collar_data.append({
        "id": r["Hole ID"],
        "lat": r["lat"],
        "lon": r["lon"],
        "elevation": r["Elevation_meters"]
    })

# Calculate trace indices for each hole
hole_trace_indices = {}
current_index = 0
for hole_id, hole_data in hole_traces.items():
    hole_trace_indices[hole_id] = list(range(current_index, current_index + len(hole_data)))
    current_index += len(hole_data)

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
    body {{
        margin: 0;
        padding: 20px;
        font-family: Arial, sans-serif;
    }}
    .container {{
        display: flex;
        height: calc(100vh - 40px);
    }}
    #map {{
        width: 50%;
        height: 100%;
        margin-right: 10px;
    }}
    #section {{
        width: 50%;
        height: 100%;
    }}
    .hole-marker {{
        background-color: #3388ff;
        border: 2px solid white;
        border-radius: 50%;
        box-shadow: 0 0 5px rgba(0,0,0,0.3);
    }}
    .hole-marker.active {{
        background-color: #ff3388;
        border-color: #cc0066;
    }}
</style>
</head>
<body>
<div class="container">
    <div id="map"></div>
    <div id="section"></div>
</div>
<script>
const collarData = {json.dumps(collar_data)};
const holeTraceIndices = {json.dumps(hole_trace_indices)};
let activeHoles = new Set(Object.keys(holeTraceIndices)); // All holes start visible

// Initialize map
const map = L.map('map').setView([collarData[0].lat, collarData[0].lon], 13);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors'
}}).addTo(map);

// Add markers
const markers = {{}};
collarData.forEach(collar => {{
    const marker = L.marker([collar.lat, collar.lon])
        .addTo(map)
        .bindPopup(`<b>${{collar.id}}</b><br>Elevation: ${{collar.elevation}}m`)
        .on('click', function() {{
            toggleHole(collar.id);
        }});
    
    // Style the marker
    const icon = marker.getIcon();
    icon.options.className = 'hole-marker';
    marker.setIcon(icon);
    
    markers[collar.id] = marker;
    updateMarkerStyle(collar.id);
}});

// Fit map to show all markers
const group = new L.featureGroup(Object.values(markers));
map.fitBounds(group.getBounds().pad(0.1));

function updateMarkerStyle(holeId) {{
    const marker = markers[holeId];
    const isActive = activeHoles.has(holeId);
    
    // Update marker appearance
    const icon = marker.getIcon();
    if (isActive) {{
        icon.options.className = 'hole-marker active';
    }} else {{
        icon.options.className = 'hole-marker';
    }}
    marker.setIcon(icon);
}}

function toggleHole(holeId) {{
    if (activeHoles.has(holeId)) {{
        activeHoles.delete(holeId);
    }} else {{
        activeHoles.add(holeId);
    }}
    
    updateMarkerStyle(holeId);
    updatePlotVisibility();
}}

function updatePlotVisibility() {{
    const visibility = [];
    Object.keys(holeTraceIndices).forEach(holeId => {{
        const indices = holeTraceIndices[holeId];
        const isVisible = activeHoles.has(holeId);
        indices.forEach(() => visibility.push(isVisible));
    }});
    
    // Add visibility for hole labels and legend (always visible)
    const numHoleLabels = collarData.length;
    const numLegendItems = {len(labels)};
    for (let i = 0; i < numHoleLabels + numLegendItems; i++) {{
        visibility.push(true);
    }}
    
    Plotly.update('section', {{visible: visibility}});
}}

Plotly.newPlot("section", {json.dumps(traces)}, {{
  title: "Interactive Borehole Fence – Looking North",
  xaxis: {{title: "Distance along section (looking north)"}},
  yaxis: {{title: "Elevation (m)"}},
  hovermode: "closest",
  legend: {{orientation:"h", x:0.5, xanchor:"center", y:-0.25}},
  updatemenus: [{{
    type: 'dropdown',
    direction: 'down',
    x: 0.5,
    xanchor: 'center',
    y: 1.1,
    yanchor: 'top',
    buttons: [{{
      label: 'Hide Cofer Hot Springs Marker',
      method: 'relayout',
      args: [{{
        shapes: [],
        annotations: []
      }}]
    }}, {{
      label: 'Show Cofer Hot Springs Marker',
      method: 'relayout',
      args: [{{
        shapes: [{{
          type: 'line',
          x0: 0,
          x1: 1,
          y0: 603,
          y1: 603,
          xref: 'paper',
          yref: 'y',
          line: {{color: 'blue', width: 2, dash: 'dash'}}
        }}],
        annotations: [{{
          x: 0.5,
          y: 607,
          xref: 'paper',
          yref: 'y',
          text: 'Cofer Hot Springs Elevation',
          showarrow: false,
          font: {{size: 12, color: 'black'}}
        }}]
      }}]
    }}]
  }}],
  shapes: [{{
    type: 'line',
    x0: 0,
    x1: 1,
    y0: 603,
    y1: 603,
    xref: 'paper',
    yref: 'y',
    line: {{
      color: 'blue',
      width: 2,
      dash: 'dash'
    }}
  }}],
  annotations: [{{
    x: 0.5,
    y: 607,
    xref: 'paper',
    yref: 'y',
    text: 'Cofer Hot Springs Elevation',
    showarrow: false,
    font: {{size: 12, color: 'black'}}
  }}]
}});
</script>
</body>
</html>
"""

with open("borehole_cross_section_north_labeled.html", "w") as f:
    f.write(html)

print("🌐 View at: http://localhost:8000/borehole_cross_section_north_labeled.html")