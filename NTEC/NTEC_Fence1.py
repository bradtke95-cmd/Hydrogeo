import json
import pandas as pd
import numpy as np
import base64

# Load collars
collars = pd.read_csv("Collars_fence.csv")

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
    # Take first component before "/" or space
    code = str(lith_str).split("/")[0].split()[0].upper()[:2]
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

# Lith intervals
for _, r in data.iterrows():
    code = extract_rock_code(r.Lith)
    traces.append({
        "type": "scatter",
        "mode": "lines",
        "x": [r.X, r.X],
        "y": [r.Bot, r.Top],
        "line": {"width": 10, "color": colors.get(code, "#ffffff")},
        "hoverinfo": "text",
        "text": f"{r.Hole_id}<br>{r.Lith}<br>{r.From}-{r.To} m",
        "showlegend": False,
    })

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

html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
<div id="section" style="width:100%;height:650px;"></div>
<script>
Plotly.newPlot("section", {json.dumps(traces)}, {{
  title: "Interactive Borehole Fence – Looking North",
  xaxis: {{title: "Distance along section (looking north)"}},
  yaxis: {{title: "Elevation (m)"}},
  hovermode: "closest",
  legend: {{orientation:"h", x:0.5, xanchor:"center", y:-0.25}}
}});
</script>
</body>
</html>
"""

with open("borehole_cross_section_north_labeled.html", "w") as f:
    f.write(html)

# Generate data URL
data_url = "data:text/html;base64," + base64.b64encode(html.encode()).decode()
print("✅ Data URL created. Copy and paste into your browser address bar:\n")
print(data_url)