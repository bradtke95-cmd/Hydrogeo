"""Split each sheet of an Excel workbook into separate CSV files in Misc."""

from pathlib import Path
import argparse

import pandas as pd

OUTPUT_DIR = Path(r"C:\Projects_L\BR_LG_Git\Hydrogeo\Misc")
DEFAULT_INPUT_FILE = OUTPUT_DIR / "Big Sandy Geology Files All 2018.xlsx"


def sanitize_sheet_name(name: str) -> str:
    """Convert sheet name to a safe filename."""
    invalid_chars = '<>:"/\\|?*'
    safe = ''.join('_' if ch in invalid_chars else ch for ch in name)
    return safe.strip().replace(' ', '_') or 'sheet'


def split_excel(input_file: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    workbook = pd.read_excel(input_file, sheet_name=None)
    if not workbook:
        raise ValueError(f'No sheets found in workbook: {input_file}')

    for sheet_name, df in workbook.items():
        csv_name = sanitize_sheet_name(sheet_name) + '.csv'
        csv_path = OUTPUT_DIR / csv_name
        df.to_csv(csv_path, index=False)
        print(f'Wrote {csv_path}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Split each worksheet of an Excel workbook into individual CSV files.'
    )
    parser.add_argument(
        'input_file',
        type=Path,
        nargs='?',
        default=DEFAULT_INPUT_FILE,
        help='Path to the input Excel workbook (.xls or .xlsx). Defaults to the attached workbook in Misc.'
    )
    args = parser.parse_args()

    if not args.input_file.exists():
        raise FileNotFoundError(f'Input file does not exist: {args.input_file}')

    print(f'Using input workbook: {args.input_file}')
    split_excel(args.input_file)


if __name__ == '__main__':
    main()
