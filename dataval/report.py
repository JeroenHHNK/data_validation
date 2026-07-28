from pathlib import Path

import pandas as pd


def generate_report(dataset_root: Path, output_file: Path) -> pd.DataFrame:
    csv_files = sorted(dataset_root.glob("*/validated/*.csv"))
    if not csv_files:
        print(f"No validated CSV files found under {dataset_root}")
        return pd.DataFrame()

    print(f"Found {len(csv_files)} validated CSV files\n")

    report_data: list[dict] = []

    for i, csv_file in enumerate(csv_files, start=1):
        source_origin_stem = csv_file.parent.parent.name
        try:
            print(f"[{i}/{len(csv_files)}] {csv_file.name} (origin={source_origin_stem})")

            df = pd.read_csv(
                csv_file, index_col=0, parse_dates=True,
                encoding="utf-8-sig", encoding_errors="replace",
            )
            df["head"] = pd.to_numeric(df["head"], errors="coerce")
            head_series = df["head"].dropna()

            if len(head_series) == 0:
                print("  No valid head data")
                continue

            first_entry = head_series.index[0]
            last_entry = head_series.index[-1]
            num_entries = len(head_series)
            time_span_days = (last_entry - first_entry).days
            possible_entries = (time_span_days * 24) + 1
            completeness_pct = (num_entries / possible_entries * 100) if possible_entries > 0 else 0

            time_diffs = head_series.index.to_series().diff().dt.total_seconds() / 3600
            largest_gap_hours = time_diffs.max() if len(time_diffs) > 1 else 0

            lowest_value = head_series.min()
            highest_value = head_series.max()

            head_diff = head_series.diff().abs()
            largest_jump = head_diff.max() if len(head_diff) > 1 else 0

            filter_counts = {}
            for col in ["v1", "v2", "v3", "v4"]:
                filter_counts[col] = df[col].notna().sum() if col in df.columns else 0

            report_data.append({
                "Source Origin": source_origin_stem,
                "Filename": csv_file.stem,
                "First Entry": first_entry,
                "Last Entry": last_entry,
                "Number of Entries": num_entries,
                "Completeness (%)": round(completeness_pct, 2),
                "Length (days)": time_span_days,
                "Largest Gap (hours)": round(largest_gap_hours, 2),
                "Lowest Value (m)": round(lowest_value, 4),
                "Highest Value (m)": round(highest_value, 4),
                "Largest Jump (m)": round(largest_jump, 4),
                "Filtered by v1 (count)": filter_counts["v1"],
                "Filtered by v2 (count)": filter_counts["v2"],
                "Filtered by v3 (count)": filter_counts["v3"],
                "Filtered by v4 (count)": filter_counts["v4"],
            })

        except Exception as e:
            print(f"  [ERR] {csv_file.name}: {e}")

    report_df = pd.DataFrame(report_data)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    report_df.to_excel(output_file, index=False, sheet_name="Validation Report")
    print(f"\nReport saved to: {output_file}")

    return report_df
