import re
from pathlib import Path

import pandas as pd

from ._utils import sanitize_for_filename


def process_fugro_csv(
    input_file: Path,
    output_dir: Path,
    dayfirst: bool = True,
    drop_all_nan: bool = True,
) -> list[Path]:
    input_path = Path(input_file)
    origin_stem = input_path.stem
    out_dir = output_dir / origin_stem / "only_csv"
    out_dir.mkdir(parents=True, exist_ok=True)

    skiprows = 0
    try:
        with open(input_path, "r", encoding="utf-8-sig", errors="replace") as f:
            first_line = f.readline().strip()
            if "Vista Data Vision" in first_line:
                skiprows = 5
                print(f"Detected Vista Data Vision file -> skipping {skiprows} header rows")
    except Exception:
        pass

    df = pd.read_csv(
        input_path,
        sep=",",
        header=0,
        dtype="object",
        encoding="utf-8-sig",
        engine="python",
        skiprows=skiprows,
    )

    first_col = str(df.columns[0]).replace("﻿", "").strip()
    if first_col.lower() != "time":
        df.rename(columns={df.columns[0]: "Time"}, inplace=True)

    time_raw = df["Time"].astype(str)
    dt_iso = pd.to_datetime(time_raw, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    dt_dayfirst = pd.to_datetime(time_raw, dayfirst=dayfirst, errors="coerce")

    if dt_iso.notna().sum() >= dt_dayfirst.notna().sum():
        df["Time"] = dt_iso
    else:
        df["Time"] = dt_dayfirst

    df = df.dropna(subset=["Time"]).set_index("Time")

    written: list[Path] = []
    seen_names: dict[str, int] = {}

    for col in df.columns:
        ser = pd.to_numeric(df[col], errors="coerce")
        if drop_all_nan and ser.notna().sum() == 0:
            continue

        base_name = sanitize_for_filename(col)
        count = seen_names.get(base_name, 0)
        out_name = base_name if count == 0 else f"{base_name}_{count}"
        seen_names[base_name] = count + 1

        out_df = pd.DataFrame({"head": ser})
        out_path = out_dir / f"{out_name}.csv"
        out_df.to_csv(out_path, index=True, index_label="Time")
        print(f"Saved {out_path} ({ser.notna().sum()} rows)")
        written.append(out_path)

    print(f"Done. Saved {len(written)} series to {out_dir}")
    return written


def convert_fugro_batch(
    input_dir: Path,
    output_dir: Path,
    file_index: int | None = None,
    dayfirst: bool = True,
    drop_all_nan: bool = True,
) -> list[Path]:
    files = sorted(input_dir.glob("*.csv"))
    if not files:
        print(f"No CSV files found in {input_dir}")
        return []

    print(f"Found {len(files)} CSV file(s) in {input_dir.name}:")
    for i, f in enumerate(files):
        print(f"  {i}: {f.name}")

    if file_index is not None:
        if file_index < 0 or file_index >= len(files):
            raise ValueError(f"file_index {file_index} out of range (0-{len(files)-1})")
        files = [files[file_index]]

    all_written: list[Path] = []
    for f in files:
        print(f"\nProcessing: {f.name}")
        written = process_fugro_csv(f, output_dir, dayfirst=dayfirst, drop_all_nan=drop_all_nan)
        all_written.extend(written)

    print(f"\nTotal: {len(all_written)} series files written.")
    return all_written
