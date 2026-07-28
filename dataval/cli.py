from pathlib import Path
from typing import Annotated, Optional

import typer

from ._utils import find_repo_root, resolve_dataset_root

app = typer.Typer(
    name="dataval",
    help="Groundwater data validation CLI for Fugro and Wiertsema datasets.",
    no_args_is_help=True,
)


@app.command()
def convert_fugro(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing raw Fugro CSV files")] = Path("input_data/Fugro"),
    output_dir: Annotated[Optional[Path], typer.Option(help="Output directory")] = None,
    file_index: Annotated[Optional[int], typer.Option("--file-index", "-f", help="Process only the file at this index (0-based). Omit to process all.")] = None,
    dayfirst: Annotated[bool, typer.Option(help="Parse dates as day-first (European format)")] = True,
    drop_all_nan: Annotated[bool, typer.Option(help="Skip columns that are entirely NaN")] = True,
):
    """Convert raw Fugro CSV files into per-sensor CSV files."""
    from .convert_fugro import convert_fugro_batch

    repo_root = find_repo_root()
    input_path = repo_root / input_dir if not input_dir.is_absolute() else input_dir
    out_path = (repo_root / (output_dir or Path("output_data/fugro"))) if not (output_dir and output_dir.is_absolute()) else output_dir

    convert_fugro_batch(input_path, out_path, file_index=file_index, dayfirst=dayfirst, drop_all_nan=drop_all_nan)


@app.command()
def convert_wiertsema(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing raw Wiertsema Excel files")] = Path("input_data/Wiertsema"),
    output_dir: Annotated[Optional[Path], typer.Option(help="Output directory")] = None,
    file_index: Annotated[Optional[int], typer.Option("--file-index", "-f", help="Process only the file at this index (0-based). Omit to process all.")] = None,
):
    """Convert raw Wiertsema Excel files into per-sensor CSV files."""
    from .convert_wiertsema import convert_wiertsema_batch

    repo_root = find_repo_root()
    input_path = repo_root / input_dir if not input_dir.is_absolute() else input_dir
    out_path = (repo_root / (output_dir or Path("output_data/wiertsema"))) if not (output_dir and output_dir.is_absolute()) else output_dir

    convert_wiertsema_batch(input_path, out_path, file_index=file_index)


@app.command()
def validate(
    dataset: Annotated[str, typer.Argument(help="Dataset to validate: 'fugro' or 'wiertsema'")],
    origin: Annotated[Optional[str], typer.Option(help="Process only this origin subdirectory. Omit for all.")] = None,
    knmi_hourly: Annotated[Path, typer.Option(help="Path to KNMI hourly CSV")] = Path("input_stressors/knmi_249_berkhout_hourly.csv"),
    max_up: Annotated[float, typer.Option(help="Max allowed upward step change (m)")] = 0.3,
    max_down: Annotated[float, typer.Option(help="Max allowed downward step change (m, negative)")] = -0.05,
    const_steps: Annotated[int, typer.Option(help="Min consecutive hours for constant-head flag")] = 96,
    band_upper: Annotated[float, typer.Option(help="Band width above hmin for constant-head detection (m)")] = 0.15,
    save_validated: Annotated[bool, typer.Option(help="Save validated CSVs to <origin>/validated/")] = True,
):
    """Run validation flags (v2/v3/v4) and generate Plotly HTML plots."""
    from .validate import validate_dataset

    repo_root = find_repo_root()
    dataset_root = resolve_dataset_root(dataset, repo_root)
    knmi_path = repo_root / knmi_hourly if not knmi_hourly.is_absolute() else knmi_hourly

    validate_dataset(
        dataset_root, knmi_path,
        origin=origin, max_up=max_up, max_down=max_down,
        const_steps=const_steps, band_upper=band_upper,
        save_validated=save_validated,
    )


@app.command()
def plot(
    dataset: Annotated[str, typer.Argument(help="Dataset to plot: 'fugro' or 'wiertsema'")],
    origin: Annotated[Optional[str], typer.Option(help="Plot only this origin subdirectory. Omit for all.")] = None,
):
    """Re-generate Plotly HTML plots from already-validated CSV files."""
    from .plot import plot_validated_dataset

    repo_root = find_repo_root()
    dataset_root = resolve_dataset_root(dataset, repo_root)
    plot_validated_dataset(dataset_root, origin=origin)


@app.command()
def report(
    dataset: Annotated[str, typer.Argument(help="Dataset to report on: 'fugro' or 'wiertsema'")],
    output_file: Annotated[Optional[Path], typer.Option(help="Output Excel file path")] = None,
):
    """Generate an Excel validation report summarizing quality metrics."""
    from .report import generate_report

    repo_root = find_repo_root()
    dataset_root = resolve_dataset_root(dataset, repo_root)

    if output_file is None:
        output_file = repo_root / "output_data" / f"validation_report_{dataset.lower()}.xlsx"
    elif not output_file.is_absolute():
        output_file = repo_root / output_file

    generate_report(dataset_root, output_file)


if __name__ == "__main__":
    app()
