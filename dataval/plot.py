from pathlib import Path

import pandas as pd

from functions.plot_functions import plot_groundwater_with_flags


EVAP_ALIASES = ["Evapotranspiration", "evaporation", "ET", "Evapo"]
PREC_ALIASES = ["Precipitation", "precipitation", "Rain", "P"]


def plot_validated_dataset(
    dataset_root: Path,
    origin: str | None = None,
) -> int:
    if not dataset_root.exists():
        print(f"Dataset root does not exist: {dataset_root}")
        return 0

    if origin:
        all_origins = [dataset_root / origin]
    else:
        all_origins = sorted([d for d in dataset_root.iterdir() if d.is_dir()])

    total_plots = 0

    for origin_dir in all_origins:
        val_dir = origin_dir / "validated"
        if not val_dir.exists():
            continue

        csv_files = sorted(val_dir.glob("*.csv"))
        if not csv_files:
            continue

        fig_dir = origin_dir / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nOrigin: {origin_dir.name} ({len(csv_files)} validated files)")

        for csv_file in csv_files:
            try:
                df = pd.read_csv(
                    csv_file, index_col=0, parse_dates=[0],
                    date_format="mixed",
                    encoding="utf-8-sig", encoding_errors="replace",
                ).reset_index()

                df[df.columns[1:]] = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")

                evap_col = next((c for c in EVAP_ALIASES if c in df.columns), None)
                prec_col = next((c for c in PREC_ALIASES if c in df.columns), None)

                fig = plot_groundwater_with_flags(df, evap_col=evap_col, prec_col=prec_col)

                output_file = fig_dir / f"{csv_file.stem}.html"
                fig.write_html(str(output_file))
                total_plots += 1
                print(f"  {csv_file.stem} -> {output_file.name}")

            except Exception as e:
                print(f"  [ERR] {csv_file.name}: {e}")

    print(f"\nDone. Generated {total_plots} HTML plots.")
    return total_plots
