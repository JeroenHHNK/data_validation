import contextlib
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from functions.validation_functions import (
    flag_constant_head_runs,
    flag_statistical_outliers,
    flag_unrealistic_step_change,
    remove_duplicate_and_fill_missing,
)

from ._utils import get_series_base, group_sensor_files

HEAD_COLORS = [
    ("black", "rgba(0, 0, 0, 0.12)"),
    ("#555555", "rgba(85, 85, 85, 0.12)"),
    ("#8B4513", "rgba(139, 69, 19, 0.12)"),
    ("#2F4F4F", "rgba(47, 79, 79, 0.12)"),
    ("#6B4226", "rgba(107, 66, 38, 0.12)"),
]


def load_and_validate(
    csv_path: Path,
    max_up: float = 0.3,
    max_down: float = -0.05,
    const_steps: int = 96,
    band_upper: float = 0.15,
) -> pd.DataFrame | None:
    df = pd.read_csv(
        csv_path, index_col=0, parse_dates=True,
        encoding="utf-8-sig", encoding_errors="replace",
    )
    if "head" not in df.columns:
        if df.shape[1] >= 1:
            df.columns = ["head"] + list(df.columns[1:])
        else:
            return None

    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()].sort_index()
    df.index.name = "Time"

    with contextlib.redirect_stdout(io.StringIO()):
        df, _ = remove_duplicate_and_fill_missing(df)
        df, _ = flag_unrealistic_step_change(df, max_up=max_up, max_down=max_down)
        if "dH" in df.columns:
            df = df.drop(columns=["dH"])
        df, _ = flag_constant_head_runs(df, min_run_steps=const_steps, band_upper_m=band_upper)
        df, _ = flag_statistical_outliers(df)

    return df


def create_series_plot(
    series_name: str,
    sensor_dfs: list[tuple[str, pd.DataFrame]],
    prec: pd.Series,
    evap: pd.Series,
    recharge: pd.Series,
) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        shared_xaxes=True,
        vertical_spacing=0.06,
    )

    for i, (label, df) in enumerate(sensor_dfs):
        line_color, fill_color = HEAD_COLORS[i % len(HEAD_COLORS)]
        raw_col = "head_raw" if "head_raw" in df.columns else "head"

        fig.add_trace(go.Scatter(
            x=df.index, y=df[raw_col],
            mode="lines", name=label,
            line=dict(color=line_color, width=1.5),
            fill="tozeroy", fillcolor=fill_color,
        ), row=1, col=1)

        for vcol, color, symbol, flag_name in [
            ("v2", "red", "circle-open", "Step change"),
            ("v3", "tomato", "diamond-open", "Constant head"),
            ("v4", "firebrick", "square-open", "IQR"),
        ]:
            if vcol in df.columns:
                mask = df[vcol].notna()
                if mask.any():
                    fig.add_trace(go.Scatter(
                        x=df.index[mask], y=df.loc[mask, vcol],
                        mode="markers", name=f"{flag_name} ({label})",
                        marker=dict(color=color, size=6, symbol=symbol),
                    ), row=1, col=1)

    all_times = pd.DatetimeIndex([])
    for _, df in sensor_dfs:
        all_times = all_times.union(df.index)
    if len(all_times) == 0:
        return fig
    t_min, t_max = all_times.min(), all_times.max()

    raw_parts = []
    for _, df in sensor_dfs:
        col = "head_raw" if "head_raw" in df.columns else "head"
        raw_parts.append(df[col].dropna())
    for vcol in ("v2", "v3", "v4"):
        for _, df in sensor_dfs:
            if vcol in df.columns:
                raw_parts.append(df[vcol].dropna())
    all_vals = pd.concat(raw_parts)
    if not all_vals.empty:
        y_min, y_max = float(all_vals.min()), float(all_vals.max())
        pad = (y_max - y_min) * 0.08 if y_max > y_min else 0.5
        fig.update_yaxes(range=[y_min - pad, y_max + pad], row=1, col=1)

    p = prec[(prec.index >= t_min) & (prec.index <= t_max)]
    e = evap[(evap.index >= t_min) & (evap.index <= t_max)]
    r = recharge[(recharge.index >= t_min) & (recharge.index <= t_max)]

    if len(p) > 0:
        fig.add_trace(go.Scatter(
            x=p.index, y=p.values, name="Precipitation",
            fill="tozeroy", line=dict(color="steelblue", width=0.5),
            fillcolor="rgba(30, 100, 200, 0.4)",
        ), row=2, col=1)

    if len(e) > 0:
        fig.add_trace(go.Scatter(
            x=e.index, y=-e.values, name="Evapotranspiration",
            fill="tozeroy", line=dict(color="darkorange", width=0.5),
            fillcolor="rgba(255, 140, 0, 0.4)",
        ), row=2, col=1)

    if len(r) > 0:
        fig.add_trace(go.Scatter(
            x=r.index, y=r.values, mode="lines", name="Recharge (P-E)",
            line=dict(color="purple", width=1.5),
        ), row=2, col=1)

    fig.update_layout(
        title=dict(text=series_name, x=0.5),
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.10, x=0.5, xanchor="center"),
        height=750,
        margin=dict(t=100),
    )
    fig.update_yaxes(title_text="Head [m NAP]", row=1, col=1)
    fig.update_yaxes(title_text="P / E / Recharge [mm]", row=2, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)

    return fig


def _load_knmi_stressors(knmi_hourly_path: Path):
    df_knmi = pd.read_csv(
        knmi_hourly_path, index_col=0, parse_dates=True,
        encoding="utf-8-sig", encoding_errors="replace",
    )
    prec = pd.to_numeric(df_knmi["precipitation_mm"], errors="coerce").dropna()
    evap = pd.to_numeric(df_knmi["makkink_mm"], errors="coerce").dropna()
    recharge = prec.subtract(evap, fill_value=0).dropna()
    return prec, evap, recharge


def validate_dataset(
    dataset_root: Path,
    knmi_hourly: Path,
    origin: str | None = None,
    max_up: float = 0.3,
    max_down: float = -0.05,
    const_steps: int = 96,
    band_upper: float = 0.15,
    save_validated: bool = True,
) -> int:
    if not dataset_root.exists():
        print(f"Dataset root does not exist: {dataset_root}")
        return 0

    prec, evap, recharge = _load_knmi_stressors(knmi_hourly)
    print(f"KNMI stressors loaded: {len(prec)} precipitation, {len(evap)} evaporation values")

    if origin:
        all_origins = [dataset_root / origin]
    else:
        all_origins = sorted([d for d in dataset_root.iterdir() if d.is_dir()])

    total_plots = 0

    for origin_dir in all_origins:
        csv_dir = origin_dir / "only_csv"
        if not csv_dir.exists():
            continue

        csv_files = sorted(csv_dir.glob("*.csv"))
        if not csv_files:
            continue

        fig_dir = origin_dir / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)

        if save_validated:
            val_dir = origin_dir / "validated"
            val_dir.mkdir(parents=True, exist_ok=True)

        groups = group_sensor_files(csv_files)
        print(f"\nOrigin: {origin_dir.name} ({len(groups)} series, {len(csv_files)} files)")

        for base_name, file_list in sorted(groups.items()):
            sensor_dfs: list[tuple[str, pd.DataFrame]] = []

            for f in file_list:
                match = re.search(r"_sensor_(\d+)$", f.stem)
                label = f"Sensor {match.group(1)}" if match else "Head"

                df = load_and_validate(
                    f, max_up=max_up, max_down=max_down,
                    const_steps=const_steps, band_upper=band_upper,
                )
                if df is None:
                    continue

                raw_col = "head_raw" if "head_raw" in df.columns else "head"
                if df[raw_col].notna().any():
                    sensor_dfs.append((label, df))

                if save_validated:
                    val_path = val_dir / f.name
                    df.to_csv(val_path, index=True, index_label="Time")

            if not sensor_dfs:
                print(f"  {base_name}: no valid data, skipping")
                continue

            fig = create_series_plot(base_name, sensor_dfs, prec, evap, recharge)
            html_path = fig_dir / f"{base_name}.html"
            fig.write_html(str(html_path))
            total_plots += 1
            print(f"  {base_name}: {len(sensor_dfs)} sensor(s) -> {html_path.name}")

    print(f"\nDone. Generated {total_plots} HTML plots.")
    return total_plots
