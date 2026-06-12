"""
convert_geology_logs.py

1. Read every geology hole sheet from "Big Sandy Geology Files ALL 2019.xlsx".
2. Write a new individual CSV (3-row-header format) for each hole not already
   present as a CSV file in NTEC_Drilling/.
3. Load every individual CSV and stack into all_geology_logs.csv (flat format).
"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "NTEC_Drilling"
XL_FILE  = DATA_DIR / "Big Sandy Geology Files ALL 2019.xlsx"
OUT_FILE = DATA_DIR / "all_geology_logs.csv"

SKIP_SHEETS = {"Codes", "Blank"}
SKIP_STEMS  = {"all_geology_logs", "Collars_fence"}

COLS = [
    "Hole_id", "From", "To", "Wthr",
    "Rock 1", "Rock 2", "Grain_size", "Colour",
    "CaCO3 %", "Acid", "Clay Type", "Remarks",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_log(path: Path) -> pd.DataFrame:
    """Read a hole-log CSV with the standard 3-row header structure."""
    raw = pd.read_csv(path, header=None, dtype=str)
    raw.columns = raw.iloc[2]          # row 3 → column names
    df = raw.iloc[3:].copy()           # data starts at row 4
    # Drop EOH markers and any row without a numeric From value
    df = df[pd.to_numeric(df["From"], errors="coerce").notna()].copy()
    df["From"] = df["From"].astype(float)
    df["To"]   = df["To"].astype(float)
    keep = [c for c in COLS if c in df.columns]
    return df[keep].reset_index(drop=True)


def write_individual_csv(sheet_name: str, df_raw: pd.DataFrame, out_path: Path) -> None:
    """Write a sheet's raw data (3-row header + data rows) as a CSV.

    Strips trailing all-empty rows that Excel sometimes appends.
    """
    # Find last row with at least one non-null value past the header rows
    last_data = 3  # minimum: keep at least the header block
    for i in range(len(df_raw) - 1, 2, -1):
        if df_raw.iloc[i].notna().any():
            last_data = i
            break
    trimmed = df_raw.iloc[: last_data + 1]
    trimmed.to_csv(out_path, index=False, header=False)


# ---------------------------------------------------------------------------
# 1. Discover existing individual CSV files
# ---------------------------------------------------------------------------
existing = {p.stem for p in DATA_DIR.glob("*.csv") if p.stem not in SKIP_STEMS}
print(f"Existing individual CSVs ({len(existing)}): {sorted(existing)}\n")

# ---------------------------------------------------------------------------
# 2. Read Excel and write new individual CSVs
# ---------------------------------------------------------------------------
xl = pd.ExcelFile(XL_FILE)
written, skipped = [], []

for sheet in xl.sheet_names:
    if sheet in SKIP_SHEETS:
        continue
    if sheet in existing:
        skipped.append(sheet)
        print(f"  SKIP  {sheet} – CSV already exists (duplicate)")
        continue

    df_raw = pd.read_excel(XL_FILE, sheet_name=sheet, header=None, dtype=str)

    # Verify there are actual data rows beyond the 3-row header
    data_rows = df_raw.iloc[3:]
    has_data = data_rows.apply(lambda r: r.notna().any(), axis=1).any()
    if not has_data:
        print(f"  SKIP  {sheet} – no data rows")
        continue

    out_path = DATA_DIR / f"{sheet}.csv"
    write_individual_csv(sheet, df_raw, out_path)
    written.append(sheet)
    existing.add(sheet)   # so the stacker picks it up below
    print(f"  WROTE {out_path.name}")

print(f"\nNew CSVs written : {len(written)}")
print(f"Duplicates skipped: {len(skipped)} — {sorted(skipped)}")

# ---------------------------------------------------------------------------
# 3. Stack ALL individual CSVs into one flat file
# ---------------------------------------------------------------------------
all_csv_paths = sorted(
    (p for p in DATA_DIR.glob("*.csv") if p.stem not in SKIP_STEMS),
    key=lambda p: p.stem,
)

frames, load_errors = [], []
for csv_path in all_csv_paths:
    try:
        df = load_log(csv_path)
        if df.empty:
            print(f"  WARN  {csv_path.name} — loaded 0 rows, skipping")
            continue
        # Pad any missing standard columns with empty string
        for col in COLS:
            if col not in df.columns:
                df[col] = ""
        frames.append(df[COLS])
        print(f"  LOAD  {csv_path.name}: {len(df)} intervals")
    except Exception as exc:
        load_errors.append(csv_path.name)
        print(f"  ERROR {csv_path.name}: {exc}")

if not frames:
    raise RuntimeError("No data loaded – check CSV formats.")

stacked = pd.concat(frames, ignore_index=True)
stacked.to_csv(OUT_FILE, index=False)

print(f"\n{'='*55}")
print(f"Holes stacked : {len(frames)}")
print(f"Total intervals: {len(stacked)}")
print(f"Output         : {OUT_FILE}")
if load_errors:
    print(f"Load errors    : {load_errors}")
