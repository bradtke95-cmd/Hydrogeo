import pandas as pd
import os
from pathlib import Path
import re

# Define the folder path
csamt_folder = Path(__file__).parent / "CSAMT"

# Get all CSV files in the CSAMT folder
csv_files = sorted(csamt_folder.glob("*_csamt_2d_inv_model_final.csv"))

print(f"Found {len(csv_files)} CSV files to process...")

def extract_index(col_name):
    """Extract the index number from column names like 'Elev_trim[0]'"""
    match = re.search(r'\[(\d+)\]', col_name)
    return int(match.group(1)) if match else None

for csv_file in csv_files:
    print(f"\nProcessing: {csv_file.name}")
    
    # Read the CSV file
    df = pd.read_csv(csv_file)
    
    # Identify columns
    elev_cols = sorted([col for col in df.columns if col.startswith("Elev_trim")], 
                       key=lambda x: extract_index(x))
    res_cols = sorted([col for col in df.columns if col.startswith("Res_trim")], 
                      key=lambda x: extract_index(x))
    preserve_cols = [col for col in df.columns if col not in elev_cols and col not in res_cols]
    
    # Create a list to hold all the reformatted rows
    reformatted_rows = []
    
    # Process each row
    for idx, row in df.iterrows():
        # Get the values that should be preserved
        preserve_values = row[preserve_cols].to_dict()
        
        # Get all Elev_trim and Res_trim values for this row
        elev_values = [row[col] for col in elev_cols]
        res_values = [row[col] for col in res_cols]
        
        # Pair up Elev and Res values and create new rows
        for elev_val, res_val in zip(elev_values, res_values):
            new_row = preserve_values.copy()
            new_row['Elev_trim'] = elev_val
            new_row['Res_trim'] = res_val
            reformatted_rows.append(new_row)
    
    # Create a new dataframe from the reformatted rows
    result = pd.DataFrame(reformatted_rows)
    
    # Reorder columns to have preserve_cols first, then Elev_trim, then Res_trim
    final_order = preserve_cols + ['Elev_trim', 'Res_trim']
    result = result[final_order]
    
    # Save the reformatted file (overwrite or save with new name)
    output_path = csv_file.parent / f"{csv_file.stem}_reformatted.csv"
    result.to_csv(output_path, index=False)
    
    print(f"  ✓ Saved to: {output_path.name}")
    print(f"  Original shape: {df.shape} → Reformatted shape: {result.shape}")

print("\n✓ All files processed successfully!")
