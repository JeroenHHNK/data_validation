Implement 4 sequential groundwater head timeseries validation functions in Python.
Each function receives a pandas DataFrame with at minimum a DatetimeIndex and a column
named `head` (float, units: meters). Functions are applied in order; each one operates
on the `head` column as modified by the previous step (NaN where already flagged).
Each function stores the original (pre-flag) value in a dedicated column (v1–v4) before
setting flagged rows to NaN in `head`.

---

## Shared input assumptions

- The DataFrame index is a DatetimeIndex with hourly frequency.
- `head` values are in meters (e.g. meters above NAP datum).
- `hmin` is derived from the filename: parse the relevant numeric substring from the
  filename string and convert it to a Python float. The exact regex/parsing pattern
  depends on the filename convention of the target dataset — implement a helper
  `parse_hmin_from_filename(filename: str) -> float` that the caller can adapt.
- `hmax` is a fixed constant set manually in the calling code (e.g. `hmax = 1.5`).
  It does NOT come from the filename.

---

## V1 — Physical bounds

Flag any measurement that falls outside the physically plausible range for the sensor.

```python
def flag_physical_bounds(df, hmin: float, hmax: float, col_out: str = "v1"):
    """
    Flags head values outside [hmin, hmax].
    hmin: parsed from filename (sensor bottom depth).
    hmax: manually configured upper bound (e.g. surface level).
    Stores original flagged values in col_out, sets head to NaN.
    """
```

Logic:
- `mask = df["head"].notna() & ~df["head"].between(hmin, hmax)`
- Store: `df[col_out] = df.loc[mask, "head"]`
- Remove: `df.loc[mask, "head"] = np.nan`

---

## V2 — Unrealistic step change

Flag any hourly step that is physically implausible for a groundwater sensor.

```python
def flag_unrealistic_step_change(df, max_up: float = 0.30, max_down: float = -0.05,
                                  col_out: str = "v2"):
    """
    Flags rows where the 1-step difference in head exceeds thresholds.
    max_up   = +0.30 m/hour  (upward jump limit)
    max_down = -0.05 m/hour  (downward jump limit; negative = drop)
    Stores original flagged values in col_out, sets head to NaN.
    """
```

Logic:
- `dH = df["head"].diff()`
- `mask = (dH > max_up) | (dH < max_down)`
- Store: `df[col_out] = df.loc[mask, "head"]`
- Remove: `df.loc[mask, "head"] = np.nan`
- Do NOT keep `dH` in the output DataFrame.

---

## V3 — Dry period (near-sensor-bottom values)

Flag any measurement that is within 20 cm above the sensor bottom (hmin). These
readings occur during dry periods (droogstand) when the water table is at or near
the sensor bottom, making measurements unreliable.

```python
def flag_dry_period(df, hmin: float, band: float = 0.20, col_out: str = "v3"):
    """
    Flags head values where head <= hmin + band.
    hmin: parsed from filename (sensor bottom depth).
    band: margin above hmin to flag (default 0.20 m).
    Stores original flagged values in col_out, sets head to NaN.
    """
```

Logic:
- `mask = df["head"].notna() & (df["head"] <= hmin + band)`
- Store: `df[col_out] = df.loc[mask, "head"]`
- Remove: `df.loc[mask, "head"] = np.nan`

Note: This check is purely threshold-based — no sliding window or flatness detection
is needed. Any value in this range is considered unreliable by definition.

---

## V4 — Statistical outliers (Tukey / IQR method)

Flag values that are statistical outliers using the classical boxplot rule.

```python
def flag_statistical_outliers(df, iqr_factor: float = 1.5, col_out: str = "v4"):
    """
    Flags head values outside Q1 - factor*IQR and Q3 + factor*IQR.
    Requires at least 4 non-NaN values. Skips if insufficient data.
    Stores original flagged values in col_out, sets head to NaN.
    """
```

Logic:
- Compute on non-NaN values: `Q1, Q3 = np.percentile(valid, [25, 75])`
- `IQR = Q3 - Q1`
- `lower = Q1 - iqr_factor * IQR`, `upper = Q3 + iqr_factor * IQR`
- `mask = df["head"].notna() & ((df["head"] < lower) | (df["head"] > upper))`
- Store: `df[col_out] = df.loc[mask, "head"]`
- Remove: `df.loc[mask, "head"] = np.nan`

---

## Pipeline wrapper

```python
def validate_timeseries(df, hmin: float, hmax: float) -> pd.DataFrame:
    """
    Runs all 4 validation steps in order on a copy of df.
    Returns DataFrame with original `head` progressively cleaned,
    and columns v1–v4 containing the flagged original values.
    """
    df = df.copy()
    df = flag_physical_bounds(df, hmin, hmax)
    df = flag_unrealistic_step_change(df)
    df = flag_dry_period(df, hmin)
    df = flag_statistical_outliers(df)
    return df
```

---

## hmin parsing helper (adapt to your filename convention)

```python
import re

def parse_hmin_from_filename(filename: str) -> float:
    """
    Extract the sensor bottom depth from the filename as a float.
    Adapt the regex to match the naming convention of the target dataset.

    Example conventions:
      Fugro:      'WELL_-2.50_m_NAP_avg.csv'  → regex r'_([+-]?\d+(?:\.\d+)?)_m_NAP'
      Wiertsema:  'WELL_F-250.xlsx'            → regex r'_F(-?\d+(?:\.\d+)?)'
                  then divide cm value by 100 to get meters if needed.
    """
    match = re.search(r'YOUR_PATTERN_HERE', filename)
    if match is None:
        raise ValueError(f"Could not parse hmin from filename: {filename}")
    return float(match.group(1))
```

---

## Output format

The returned DataFrame must contain:

| column | description |
|--------|-------------|
| `head` | validated head (NaN where any flag was applied) |
| `v1`   | original values flagged by physical bounds |
| `v2`   | original values flagged by unrealistic step change |
| `v3`   | original values flagged by dry period threshold |
| `v4`   | original values flagged by statistical outlier |

Columns v1–v4 are NaN for non-flagged rows. A row can only appear in one vX column
(the first validation that caught it), because `head` is set to NaN before the next
check runs.

---

## Verification checklist

After implementing, verify:
1. Call `validate_timeseries(df, hmin, hmax)` on a sample series.
2. Confirm `v1`–`v4` columns are present and contain original float values only where flagged.
3. Confirm `head` is NaN at every row where any vX is non-NaN.
4. Confirm no row has more than one vX column populated.
