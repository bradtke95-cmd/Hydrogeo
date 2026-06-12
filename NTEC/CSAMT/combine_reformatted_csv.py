import pandas as pd
from pathlib import Path

# Define the folder path
csamt_folder = Path(__file__).parent / "CSAMT"

# Get all reformatted CSV files in the CSAMT folder
reformatted_files = sorted(csamt_folder.glob("*_reformatted.csv"))

print(f"Found {len(reformatted_files)} reformatted CSV files to combine...")

# Read and concatenate all files
all_dataframes = []
for csv_file in reformatted_files:
    print(f"  Reading: {csv_file.name}")
    df = pd.read_csv(csv_file)
    all_dataframes.append(df)

# Combine all dataframes
combined_df = pd.concat(all_dataframes, ignore_index=True)

print(f"\nCombined shape before filtering: {combined_df.shape}")

# Remove rows where both Elev_trim and Res_trim are NaN or empty
combined_df_filtered = combined_df.dropna(subset=['Elev_trim', 'Res_trim'], how='any')

print(f"Combined shape after filtering: {combined_df_filtered.shape}")
print(f"Rows removed: {combined_df.shape[0] - combined_df_filtered.shape[0]}")

# Save the combined file
output_path = csamt_folder / "CSAMT_combined_reformatted.csv"
combined_df_filtered.to_csv(output_path, index=False)

print(f"\n✓ Combined file saved to: {output_path.name}")
print(f"Total rows in combined file: {combined_df_filtered.shape[0]}")
