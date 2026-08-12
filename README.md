# Data Validation Pipeline

Groundwater data validation toolkit for Fugro and Wiertsema datasets. Compares groundwater head timeseries against KNMI precipitation and evaporation data, applies quality flags, and generates interactive HTML plots and Excel reports. Ships with a `dataval` **CLI** for the automated pipeline and a **Streamlit dashboard** for manual point-by-point review.

## Requirements

- Python 3.12+
- Poetry (or pip)

## Installation

```powershell
# Clone the repository and install
poetry install

# Or with pip (editable mode)
pip install -e .
```

After installation the `dataval` command is available in the virtual environment:

```powershell
poetry run dataval --help
```

## CLI Commands

### 1. Convert raw Fugro CSVs to per-sensor files

```powershell
# Convert all files
dataval convert-fugro input_data/Fugro/

# Convert a specific file by index
dataval convert-fugro input_data/Fugro/ --file-index 3

# Custom output directory
dataval convert-fugro input_data/Fugro/ --output-dir output_data/fugro/
```

**Options:**
- `--file-index`, `-f`: Process only the file at this 0-based index (omit for all)
- `--output-dir`: Output directory (default: `output_data/fugro/`)
- `--dayfirst / --no-dayfirst`: Parse dates as European day-first format (default: `--dayfirst`)
- `--drop-all-nan / --keep-all-nan`: Skip columns that are entirely NaN (default: `--drop-all-nan`)

### 2. Convert raw Wiertsema Excel files to per-sensor files

```powershell
# Convert all workbooks
dataval convert-wiertsema input_data/Wiertsema/

# Convert a specific file by index
dataval convert-wiertsema input_data/Wiertsema/ --file-index 0
```

**Options:**
- `--file-index`, `-f`: Process only the file at this 0-based index (omit for all)
- `--output-dir`: Output directory (default: `output_data/wiertsema/`)

### 3. Validate groundwater data

Runs validation flags and generates interactive Plotly HTML plots with precipitation/evaporation overlays.

```powershell
# Validate all Wiertsema series
dataval validate wiertsema

# Validate all Fugro series
dataval validate fugro

# Validate a specific origin subfolder
dataval validate wiertsema --origin Beemster_86349_1_deel_1

# Custom thresholds
dataval validate wiertsema --max-up 0.5 --max-down -0.1 --const-steps 48 --band-upper 0.20
```

**Options:**
- `--origin`: Process only this origin subdirectory (omit for all)
- `--knmi-hourly`: Path to KNMI hourly CSV (default: `input_stressors/knmi_249_berkhout_hourly.csv`)
- `--max-up`: Max allowed upward step change in meters (default: 0.3)
- `--max-down`: Max allowed downward step change in meters (default: -0.05)
- `--const-steps`: Min consecutive hours for constant-head flag (default: 96)
- `--band-upper`: Band width above hmin for constant-head detection in meters (default: 0.15)
- `--save-validated / --no-save-validated`: Save validated CSVs to `<origin>/validated/` (default: enabled)

**Validation flags applied:**
- **v2**: Unrealistic step change (jumps exceeding `max-up` or `max-down`)
- **v3**: Constant head runs (values in bottom band for >= `const-steps` consecutive hours)
- **v4**: Statistical outliers (IQR / Tukey method)

### 4. Re-plot validated data

Re-generates HTML plots from already-validated CSV files (uses `plot_groundwater_with_flags` from the functions package).

```powershell
dataval plot wiertsema
dataval plot fugro --origin some_origin_folder
```

### 5. Generate validation report

Creates an Excel report summarizing quality metrics per validated series.

```powershell
dataval report wiertsema
dataval report fugro --output-file custom_report.xlsx
```

## Manual Validation Dashboard (Streamlit)

An interactive browser app for point-by-point human review of a series. Reviewers
mark each observation as reviewed (`gecontroleerd`) or rejected (`afgekeurd`) and add
a short note. Validation state is stored per series and **survives re-imports of new
raw data** — already-reviewed points are never overwritten.

### Launch

```powershell
# From the repository root, inside the virtual environment:
poetry run streamlit run streamlit_app.py --server.port 8502


# Killing or checking a zombie server if it exists when the app crashes
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*streamlit*" } | Select-Object ProcessId, CommandLine

# Or directly with the venv executable:
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

The app opens in your browser (default http://localhost:8501).

### Using the app

1. In the sidebar, pick **Vendor** → **Origin** → **Series**, then click **Load series**
   (a `✓` next to a series name means a saved validation store already exists).
2. Review points in the table: toggle **Gecontroleerd** / **Afgekeurd** and add a
   **Note** (max 30 characters). The plot updates with color-coded status:
   - **GRAY** = unreviewed
   - **GREEN** = reviewed (`gecontroleerd = 1`)
   - **RED** = rejected (`afgekeurd = 1`)
   - Automatic v2/v3/v4 flags (if a `validated/` file exists) are shown as open marker
     hints to guide review.
3. Use **Show only unreviewed** and **Mark all visible as reviewed** to speed up review
   of large series.
4. Click **Import new raw data** (sidebar) to fold a fresh raw export into the store —
   reviewed rows keep their status, notes, and values; new timestamps are appended as
   unreviewed.
5. Click **Save to CSV** to persist changes to
   `output_data/{vendor}/<origin>/dashboard/<series>.csv`.

### Store schema

Each series' validation store (`output_data/{vendor}/<origin>/dashboard/<series>.csv`)
has columns: `timestamp`, `raw_data`, `gecontroleerd` (0/1), `afgekeurd` (0/1),
`note` (≤30 chars). Raw timestamps are rounded to the hour to give a stable merge key.

App behaviour is configurable via [`config/settings.yaml`](config/settings.yaml)
(`base_data_dir`, `notes_max_len`, `round_freq`); sensible defaults apply if the file
is absent.

## Workflow

A typical workflow from raw data to validated outputs:

```powershell
# Step 0: Download KNMI data (notebook — run manually)
#   notebooks/0_knmi_data_pull.ipynb
#   notebooks/0b_knmi_raw_txt_converter.ipynb

# Step 1: Convert raw vendor files to per-sensor CSVs
dataval convert-fugro input_data/Fugro/
dataval convert-wiertsema input_data/Wiertsema/

# Step 2: Validate and generate plots
dataval validate fugro
dataval validate wiertsema

# Step 3: Generate Excel reports
dataval report fugro
dataval report wiertsema

# Step 4 (optional): Manual point-by-point review in the browser
streamlit run streamlit_app.py
```

## Directory Structure

```
input_data/
  Fugro/              # Raw Fugro CSV files
  Wiertsema/          # Raw Wiertsema Excel files
input_stressors/      # KNMI precipitation/evaporation data
output_data/
  fugro/
    <origin>/
      only_csv/       # Per-sensor CSVs (from convert-fugro)
      validated/      # Validated CSVs with flags (from validate)
      figures/        # Interactive HTML plots
      dashboard/      # Manual validation stores (from the Streamlit app)
  wiertsema/
    <origin>/
      only_csv/       # Per-sensor CSVs (from convert-wiertsema)
      validated/      # Validated CSVs with flags (from validate)
      figures/        # Interactive HTML plots
      dashboard/      # Manual validation stores (from the Streamlit app)
  validation_report_fugro.xlsx
  validation_report_wiertsema.xlsx
notebooks/
  0_knmi_data_pull.ipynb          # KNMI API data download (manual)
  0b_knmi_raw_txt_converter.ipynb # KNMI raw txt to CSV (manual)
config/
  settings.yaml                   # Dashboard configuration
functions/                        # Reusable validation and plotting modules
dataval/                          # CLI package
dashboard/                        # Streamlit dashboard package
streamlit_app.py                  # Streamlit dashboard entry point
```

## Notebooks

Two notebooks are kept for manual KNMI data retrieval:

- **`0_knmi_data_pull.ipynb`** — Downloads daily KNMI data via API, computes Makkink evapotranspiration
- **`0b_knmi_raw_txt_converter.ipynb`** — Converts raw KNMI hourly `.txt` downloads to clean CSV

These are run interactively before the CLI pipeline.

## Troubleshooting

- **`dataval` command not found**: Make sure you installed the project (`pip install -e .` or `poetry install`) and are running inside the virtual environment.
- **KNMI hourly file not found**: Run notebooks `0_knmi_data_pull.ipynb` and `0b_knmi_raw_txt_converter.ipynb` first to generate the stressor data.
- **No validated CSV files for `plot` or `report`**: Run `dataval validate` first with `--save-validated` (enabled by default).
- **Empty output from `convert-wiertsema`**: Ensure the Excel files contain sheets with "Waterniveau" or "Grondwaterstand" columns containing "m NAP".
- **`streamlit` command not found**: Install the project (`pip install -e .` or `poetry install`) — `streamlit` is a declared dependency. Then run inside the virtual environment.
- **Dashboard shows no series**: The app reads from `output_data/{vendor}/<origin>/only_csv/`. Run `dataval convert-fugro` / `convert-wiertsema` first to generate those files.
- **Editor feels slow on a large series**: Keep **Show only unreviewed** on and lower the **Max rows in editor** value; the plot always shows all points regardless.
