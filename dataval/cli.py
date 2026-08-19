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


@app.command()
def migrate_wiertsema(
    apply: Annotated[bool, typer.Option(help="Execute the migration (default is dry-run)")] = False,
    output_dir: Annotated[Optional[Path], typer.Option(help="Override wiertsema output directory")] = None,
):
    """Migrate wiertsema output folders to stable-key naming."""
    from .migrate_wiertsema import run_migration

    repo_root = find_repo_root()
    wiertsema_dir = output_dir or (repo_root / "output_data" / "wiertsema")
    if not wiertsema_dir.is_absolute():
        wiertsema_dir = repo_root / wiertsema_dir
    validation_dir = repo_root / "validation_data" / "wiertsema"

    report = run_migration(wiertsema_dir, apply=apply, validation_dir=validation_dir)
    print(report)


@app.command()
def build_object_data(
    dataset: Annotated[Optional[str], typer.Option(help="Limit to 'fugro' or 'wiertsema'. Omit for both.")] = None,
    origin: Annotated[Optional[str], typer.Option(help="Process only this project folder. Omit for all.")] = None,
):
    """Derive OBJECT_DATA.csv per project folder from the only_csv filenames."""
    from .object_data import write_object_data

    repo_root = find_repo_root()
    datasets = [dataset.lower()] if dataset else ["fugro", "wiertsema"]

    for name in datasets:
        root = resolve_dataset_root(name, repo_root)
        if not root.is_dir():
            continue
        for project in sorted(p for p in root.iterdir() if p.is_dir()):
            if origin and project.name != origin:
                continue
            if not (project / "only_csv").is_dir():
                continue
            df, out_path = write_object_data(project, name)
            review = int(df["needs_review"].sum()) if not df.empty else 0
            missing = int(df["bottom_filter"].isna().sum()) if not df.empty else 0
            print(
                f"{name}/{project.name}: {len(df)} series "
                f"({missing} without bottom_filter, {review} need review) -> {out_path}"
            )


@app.command()
def autoflag(
    dataset: Annotated[Optional[str], typer.Option(help="Limit to 'fugro' or 'wiertsema'. Omit for both.")] = None,
    origin: Annotated[Optional[str], typer.Option(help="Process only this project folder. Omit for all.")] = None,
    apply: Annotated[bool, typer.Option(help="Write afgekeurd flags (default is a read-only dry run)")] = False,
    respect_manual: Annotated[bool, typer.Option(help="Never flag a row already marked gecontroleerd")] = True,
    stitch_boundary: Annotated[bool, typer.Option(help="Apply rule A across sensor stitch boundaries too")] = False,
    apply_rule_a: Annotated[bool, typer.Option(help="Also write afgekeurd for rule A (default: report only)")] = False,
    report: Annotated[Optional[Path], typer.Option(help="Write the per-series report to this CSV")] = None,
    rule_a_report: Annotated[Optional[Path], typer.Option(help="Write rule A candidate rows to this CSV")] = None,
):
    """Auto-flag implausible readings as afgekeurd (rule A: drop; rule B: filter bottom).

    Rule B is applied; rule A is report-only unless --apply-rule-a is given,
    because against the human-validated project it disagreed with the reviewer
    on most of its hits.
    """
    import pandas as pd

    from .autoflag import flag_origin, summarize

    repo_root = find_repo_root()
    base_data_dir = repo_root / "output_data"
    store_dir = repo_root / "validation_data"
    datasets = [dataset.lower()] if dataset else ["fugro", "wiertsema"]

    all_results = []
    review_sink: list = []
    for name in datasets:
        root = resolve_dataset_root(name, repo_root)
        if not root.is_dir():
            continue
        for project in sorted(p for p in root.iterdir() if p.is_dir()):
            if origin and project.name != origin:
                continue
            if not (project / "only_csv").is_dir():
                continue
            results = flag_origin(
                base_data_dir=base_data_dir,
                store_dir=store_dir,
                vendor=name,
                origin=project.name,
                dry_run=not apply,
                respect_manual=respect_manual,
                skip_stitch_boundary=not stitch_boundary,
                apply_rule_a=apply_rule_a,
                review_sink=review_sink,
            )
            all_results.extend(results)
            df = summarize(results)
            verb = "would flag" if not apply else "flagged"
            print(
                f"{name}/{project.name}: {verb} {int(df.newly_flagged.sum())} rows"
                f"  (rule_b={int(df.rule_b.sum())}, "
                f"rule_a reported={int(df.rule_a_reported.sum())})"
            )

    summary = summarize(all_results)
    if not summary.empty:
        mode = "DRY RUN - nothing written" if not apply else "APPLIED"
        print(
            f"\n{mode}. series={len(summary)} rows={int(summary.n_rows.sum())} "
            f"rule_a={int(summary.rule_a.sum())} rule_b={int(summary.rule_b.sum())} "
            f"newly_flagged={int(summary.newly_flagged.sum())} "
            f"kept_manual={int(summary.protected_manual.sum())}"
        )
    if report:
        report_path = report if report.is_absolute() else repo_root / report
        summary.to_csv(report_path, index=False, encoding="utf-8-sig")
        print(f"report -> {report_path}")

    if review_sink and not apply_rule_a:
        path = rule_a_report or (repo_root / "output_data" / "rule_a_review.csv")
        if not path.is_absolute():
            path = repo_root / path
        pd.DataFrame(review_sink).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"rule A candidates (not flagged): {len(review_sink)} rows -> {path}")


if __name__ == "__main__":
    app()
