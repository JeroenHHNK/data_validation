"""Stitch multi-sensor series and auto-flag implausible readings as afgekeurd.

Two rules, and only these two; anything matching neither is left untouched:

Rule A  a drop of >= ``DROP_THRESHOLD_M`` within a single hourly interval.
Rule B  a value at or below ``bottom_filter + FILTER_MARGIN_M`` -- at/below the
        filter bottom is physically impossible, and the 10 cm above it is
        unreliable. Skipped entirely where ``bottom_filter`` is NaN.

Stitching concatenates the physical sensor files of one ``name_timeseries``
into a chronological series and trims overlaps (the newest sensor wins). No
offset correction is applied: discontinuities are left as they are. Because a
step at a sensor changeover is usually recalibration rather than bad data,
Rule A is not applied to the interval spanning a stitch boundary; those
intervals are reported for manual review instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from dashboard import validation_store
from dataval.object_data import load_object_data

#: Rule A: a fall of at least this many metres in one hourly step. Raised from
#: 0.07 after benchmarking against the human-validated project.
DROP_THRESHOLD_M = 0.10

#: Rule B: readings within this margin above the filter bottom are unreliable.
FILTER_MARGIN_M = 0.10

#: Origins whose validation store is manually curated and must never be
#: rewritten by this pipeline.
PROTECTED_ORIGINS: set[tuple[str, str]] = {
    (
        "fugro",
        "4423-241417_PB_HHW_01-01-2023 00_00_00_29-06-2026 00_00_00_Uur_20260629115503",
    ),
}

_SENSOR_RE = re.compile(r"_sensor_(\d+)$")


def is_protected(vendor: str, origin: str) -> bool:
    return (vendor.lower(), origin) in PROTECTED_ORIGINS


@dataclass
class SeriesResult:
    """Outcome of flagging one logical timeseries."""

    vendor: str
    origin: str
    name_timeseries: str
    bottom_filter: float | None
    n_rows: int = 0
    n_sensors: int = 0
    rule_a: int = 0
    rule_b: int = 0
    both: int = 0
    rule_a_reported: int = 0
    newly_flagged: int = 0
    already_flagged: int = 0
    protected_manual: int = 0
    boundary_skipped: int = 0
    skipped_reason: str = ""
    notes: list[str] = field(default_factory=list)


def _sensor_order(stem: str) -> tuple[int, str]:
    """Sort key putting sensors in ascending sensor number (oldest first)."""
    m = _SENSOR_RE.search(stem)
    return (int(m.group(1)) if m else 0, stem)


def stitch_group(files: list[Path], round_freq: str = "1h") -> pd.DataFrame:
    """Concatenate sensor files into one chronological, overlap-free series.

    Returns a frame of ``timestamp, raw_data, source`` sorted by time, with at
    most one row per timestamp. Where sensors overlap the newest one wins; no
    offset correction is applied.
    """
    frames = []
    for path in sorted(files, key=lambda p: _sensor_order(p.stem)):
        raw = pd.read_csv(path, encoding="utf-8-sig", encoding_errors="replace")
        norm = validation_store.normalize_raw(raw, round_freq=round_freq)
        norm["source"] = path.stem
        norm["_order"] = _sensor_order(path.stem)[0]
        frames.append(norm)

    if not frames:
        return pd.DataFrame(columns=["timestamp", "raw_data", "source"])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["raw_data"])
    # Newest sensor wins any overlapping timestamp.
    combined = combined.sort_values(["timestamp", "_order"])
    combined = combined.drop_duplicates(subset="timestamp", keep="last")
    combined = combined.drop(columns="_order").sort_values("timestamp")
    return combined.reset_index(drop=True)


def compute_flags(
    stitched: pd.DataFrame,
    bottom_filter: float | None,
    drop_threshold: float = DROP_THRESHOLD_M,
    margin: float = FILTER_MARGIN_M,
    skip_stitch_boundary: bool = True,
    round_freq: str = "1h",
) -> pd.DataFrame:
    """Add ``rule_a``/``rule_b``/``at_boundary`` boolean columns to *stitched*."""
    df = stitched.copy()
    if df.empty:
        df["rule_a"] = []
        df["rule_b"] = []
        df["at_boundary"] = []
        return df

    step = pd.Timedelta(round_freq)
    delta_t = df["timestamp"].diff()
    delta_v = df["raw_data"].diff()

    # A drop only counts when the previous reading really is one interval back;
    # across a data gap "within one hourly interval" is not meaningful.
    contiguous = delta_t.eq(step)
    df["at_boundary"] = df["source"].ne(df["source"].shift()) & df["source"].shift().notna()

    rule_a = contiguous & (delta_v <= -abs(drop_threshold))
    if skip_stitch_boundary:
        rule_a &= ~df["at_boundary"]
    df["rule_a"] = rule_a.fillna(False)

    if bottom_filter is None or pd.isna(bottom_filter):
        df["rule_b"] = False
    else:
        df["rule_b"] = df["raw_data"] <= (float(bottom_filter) + margin)

    return df


def _note_for(row, apply_rule_a: bool = False) -> str:
    parts = []
    if apply_rule_a and row["rule_a"]:
        parts.append(f"auto: drop >= {DROP_THRESHOLD_M:.2f} m in 1 h")
    if row["rule_b"]:
        parts.append(f"auto: <= bottom_filter + {FILTER_MARGIN_M:.2f} m")
    return "; ".join(parts)


def flag_series(
    vendor: str,
    origin: str,
    name_timeseries: str,
    files: list[Path],
    bottom_filter: float | None,
    store_dir: Path,
    dry_run: bool = True,
    respect_manual: bool = True,
    skip_stitch_boundary: bool = True,
    apply_rule_a: bool = False,
    review_sink: list | None = None,
    round_freq: str = "1h",
) -> SeriesResult:
    """Flag one logical timeseries, writing into the per-sensor stores.

    With ``dry_run`` nothing is written; the returned counts describe what
    would change. Existing values are never cleared -- the only write is
    setting ``afgekeurd`` to 1 on matching rows.

    Rule A is report-only unless ``apply_rule_a`` is set: benchmarked against
    the human-validated data it disagreed with the reviewer on most of its
    hits, so by default those rows are collected in *review_sink* instead of
    being rejected.
    """
    result = SeriesResult(
        vendor=vendor,
        origin=origin,
        name_timeseries=name_timeseries,
        bottom_filter=bottom_filter,
        n_sensors=len(files),
    )

    if is_protected(vendor, origin):
        result.skipped_reason = "protected origin; left untouched"
        return result

    stitched = stitch_group(files, round_freq=round_freq)
    result.n_rows = len(stitched)
    if stitched.empty:
        result.skipped_reason = "no usable data"
        return result

    flags = compute_flags(
        stitched,
        bottom_filter,
        skip_stitch_boundary=skip_stitch_boundary,
        round_freq=round_freq,
    )
    result.rule_a = int(flags["rule_a"].sum())
    result.rule_b = int(flags["rule_b"].sum())
    result.both = int((flags["rule_a"] & flags["rule_b"]).sum())
    result.boundary_skipped = int(flags["at_boundary"].sum())

    # Rule A rows go to the review report whether or not they are applied.
    reported = flags[flags["rule_a"]]
    result.rule_a_reported = len(reported)
    if review_sink is not None and not reported.empty:
        for ts, row in reported.set_index("timestamp").iterrows():
            review_sink.append({
                "vendor": vendor,
                "origin": origin,
                "name_timeseries": name_timeseries,
                "source_file": row["source"],
                "timestamp": ts,
                "raw_data": row["raw_data"],
                "bottom_filter": bottom_filter,
                "also_rule_b": bool(row["rule_b"]),
                "rule": "A: drop >= %.2f m in 1 h" % DROP_THRESHOLD_M,
            })

    write_mask = flags["rule_b"] | (flags["rule_a"] if apply_rule_a else False)
    hits = flags[write_mask]
    if hits.empty:
        return result

    for source, group in hits.groupby("source"):
        store_path = store_dir / vendor / origin / f"{source}.csv"
        raw_path = _raw_path_for(files, source)
        store = validation_store.load(store_path)
        if store.empty and raw_path is not None:
            raw = pd.read_csv(raw_path, encoding="utf-8-sig", encoding_errors="replace")
            store = validation_store.merge_new_raw(store, raw, round_freq=round_freq)

        idx = store.set_index("timestamp")
        targets = group.set_index("timestamp")
        common = idx.index.intersection(targets.index)
        if common.empty:
            continue

        manual = idx.loc[common, "gecontroleerd"] == 1
        already = idx.loc[common, "afgekeurd"] == 1

        to_set = common
        if respect_manual:
            # A human decision on this row outranks the rule.
            result.protected_manual += int(manual.sum())
            to_set = common[~manual.values]
        result.already_flagged += int(already.sum())
        to_set = to_set.difference(idx.index[idx["afgekeurd"] == 1])
        result.newly_flagged += len(to_set)

        if dry_run or len(to_set) == 0:
            continue

        idx.loc[to_set, "afgekeurd"] = 1
        for ts in to_set:
            note = _note_for(targets.loc[ts], apply_rule_a=apply_rule_a)
            existing = str(idx.at[ts, "note"] or "")
            if note and note not in existing:
                idx.at[ts, "note"] = f"{existing}; {note}".strip("; ")

        validation_store.save(store_path, idx.reset_index())

    return result


def _raw_path_for(files: list[Path], stem: str) -> Path | None:
    for p in files:
        if p.stem == stem:
            return p
    return None


def flag_origin(
    base_data_dir: Path,
    store_dir: Path,
    vendor: str,
    origin: str,
    dry_run: bool = True,
    respect_manual: bool = True,
    skip_stitch_boundary: bool = True,
    apply_rule_a: bool = False,
    review_sink: list | None = None,
    round_freq: str = "1h",
) -> list[SeriesResult]:
    """Flag every series in one project folder, driven by its OBJECT_DATA.csv."""
    project_dir = base_data_dir / vendor / origin
    obj = load_object_data(project_dir)
    if obj is None:
        raise FileNotFoundError(
            f"OBJECT_DATA.csv missing for {vendor}/{origin}; build it first"
        )

    only_csv = project_dir / "only_csv"
    results = []
    for _, row in obj.iterrows():
        name = str(row["name_timeseries"])
        bottom = pd.to_numeric(row.get("bottom_filter"), errors="coerce")
        bottom = None if pd.isna(bottom) else float(bottom)

        stems = [s for s in str(row.get("source_files", "")).split(";") if s]
        files = [only_csv / f"{s}.csv" for s in stems]
        files = [p for p in files if p.exists()]

        is_nap = row.get("is_nap", True)
        if is_nap is False or str(is_nap).lower() == "false":
            results.append(
                SeriesResult(
                    vendor=vendor, origin=origin, name_timeseries=name,
                    bottom_filter=bottom, n_sensors=len(files),
                    skipped_reason="not an m NAP series; rules do not apply",
                )
            )
            continue

        results.append(
            flag_series(
                vendor=vendor,
                origin=origin,
                name_timeseries=name,
                files=files,
                bottom_filter=bottom,
                store_dir=store_dir,
                dry_run=dry_run,
                respect_manual=respect_manual,
                skip_stitch_boundary=skip_stitch_boundary,
                apply_rule_a=apply_rule_a,
                review_sink=review_sink,
                round_freq=round_freq,
            )
        )
    return results


def summarize(results: list[SeriesResult]) -> pd.DataFrame:
    """Turn per-series results into a report frame."""
    return pd.DataFrame([r.__dict__ for r in results])
