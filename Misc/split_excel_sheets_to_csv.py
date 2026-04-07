"""Split each sheet of an Excel workbook into separate CSV files."""

import argparse
from pathlib import Path

import pandas as pd


def sanitize_sheet_name(name: str) -> str:
    """Convert sheet name to a safe filename."""
    invalid_chars = '<>:"/\\|?*'
    safe = ''.join('_' if ch in invalid_chars else ch for ch in name)
    return safe.strip().replace(' ', '_') or 'sheet'


def split_excel(input_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook = pd.read_excel(input_path, sheet_name=None)

    if not workbook:
        raise ValueError(f'No sheets found in workbook: {input_path}')

    for sheet_name, df in workbook.items():
        safe_name = sanitize_sheet_name(sheet_name)
        csv_path = output_dir / f"{safe_name}.csv"
        df.to_csv(csv_path, index=False)
        print(f'Wrote {csv_path}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Export each sheet of an Excel workbook as a separate CSV file.'
    )
    parser.add_argument(
        'input_file',
        type=Path,
        help='Path to the input Excel workbook (.xls or .xlsx).'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('csv_output'),
        help='Directory to write CSV files into. Defaults to ./csv_output.'
    )
    args = parser.parse_args()

    if not args.input_file.exists():
        raise FileNotFoundError(f'Input file does not exist: {args.input_file}')

    split_excel(args.input_file, args.output_dir)


if __name__ == '__main__':
    main()
