# Data Validation Pipeline

Groundwater data validation pipeline for Fugro and Wiertsema datasets.

## Current status

- The pipeline is notebook-driven.
- There is no single Python CLI entrypoint yet.
- You can run all stages from the command line by executing the notebooks in order.

## Requirements

- Python 3.12+
- Poetry
- A Jupyter-capable environment (for `jupyter nbconvert` execution)

## Install

```powershell
poetry install
```

Install notebook execution tools inside the Poetry environment:

```powershell
poetry run pip install jupyter nbconvert
```

Optional check:

```powershell
poetry run python -m jupyter --version
```

## Run from CLI (PowerShell)

Run these commands from the repository root.

1. Build/refresh stage-1 CSVs from raw inputs

```powershell
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/1_raw_csv_fugro.ipynb --inplace
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/1_raw_csv_wiertsema.ipynb --inplace
```

2. Build metadata table

```powershell
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/1a_metadata_builder.ipynb --inplace
```

3. Add KNMI stressors and create KNMI-enriched CSVs

```powershell
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/1b_raw_fugro_wiertsema_knmi_csv_creator.ipynb --inplace
```

4. Run validation (v1-v4 + approved handling)

```powershell
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/2_data_validation_batch_mark_outliers.ipynb --inplace
```

5. Generate plots and reports

```powershell
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/4_data_validation_graph_and_csv_generator.ipynb --inplace
poetry run python -m jupyter nbconvert --to notebook --execute notebooks/5_data_validation_report_generator.ipynb --inplace
```

## Dataset selection

Some notebooks include a selection variable (for example `dataset_choice` or `folder_choice`) set in a code cell.

Before running from CLI, set those variables in the notebook source to either:

- `fugro`
- `wiertsema`

Then run the notebook command above.

## Output structure

Outputs are organized per dataset and origin file:

- `output_data/fugro/<origin>/only_csv`
- `output_data/fugro/<origin>/knmi`
- `output_data/fugro/<origin>/validated`
- `output_data/fugro/<origin>/figures`
- `output_data/wiertsema/<origin>/only_csv`
- `output_data/wiertsema/<origin>/knmi`
- `output_data/wiertsema/<origin>/validated`
- `output_data/wiertsema/<origin>/figures`

## Notes on approvals

`notebooks/2_data_validation_batch_mark_outliers.ipynb` writes an `approved` column:

- default value is `1`
- existing manual `approved = 0` values are preserved by matching `Time` when regenerating
