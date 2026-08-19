import pandas as pd
import pytest

from dataval.autoflag import (
    DROP_THRESHOLD_M,
    FILTER_MARGIN_M,
    compute_flags,
    is_protected,
    stitch_group,
)


def _write(tmp_path, name, timestamps, values):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"Time": timestamps, "head": values}).to_csv(path, index=False)
    return path


def _hours(start, n):
    return pd.date_range(start, periods=n, freq="1h")


def _stitched(timestamps, values, source="s"):
    return pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        "raw_data": values,
        "source": source,
    })


# --------------------------------------------------------------------------
# Stitching
# --------------------------------------------------------------------------

def test_stitch_concatenates_sensors_chronologically(tmp_path):
    a = _write(tmp_path, "w_sensor_1", _hours("2024-01-01 00:00", 3), [-1.0, -1.1, -1.2])
    b = _write(tmp_path, "w_sensor_2", _hours("2024-01-01 03:00", 3), [-1.3, -1.4, -1.5])
    out = stitch_group([a, b])
    assert len(out) == 6
    assert out["timestamp"].is_monotonic_increasing
    assert out["raw_data"].tolist() == [-1.0, -1.1, -1.2, -1.3, -1.4, -1.5]


def test_stitch_trims_overlap_with_newest_sensor_winning(tmp_path):
    a = _write(tmp_path, "w_sensor_1", _hours("2024-01-01 00:00", 4), [-1.0, -1.1, -1.2, -1.3])
    b = _write(tmp_path, "w_sensor_2", _hours("2024-01-01 02:00", 4), [-2.2, -2.3, -2.4, -2.5])
    out = stitch_group([a, b])
    assert out["timestamp"].is_unique
    assert len(out) == 6
    # The two overlapping hours take sensor_2's values, not sensor_1's.
    assert out.loc[out.timestamp == pd.Timestamp("2024-01-01 02:00"), "raw_data"].item() == -2.2
    assert out.loc[out.timestamp == pd.Timestamp("2024-01-01 03:00"), "raw_data"].item() == -2.3


def test_stitch_applies_no_offset_correction(tmp_path):
    a = _write(tmp_path, "w_sensor_1", _hours("2024-01-01 00:00", 2), [-1.0, -1.0])
    b = _write(tmp_path, "w_sensor_2", _hours("2024-01-01 02:00", 2), [-3.0, -3.0])
    out = stitch_group([a, b])
    # The 2 m discontinuity is left exactly as it is.
    assert out["raw_data"].tolist() == [-1.0, -1.0, -3.0, -3.0]


# --------------------------------------------------------------------------
# Rule A
# --------------------------------------------------------------------------

def test_rule_a_flags_a_drop_at_the_threshold():
    df = _stitched(_hours("2024-01-01 00:00", 3), [-1.00, -1.10, -1.10])
    out = compute_flags(df, bottom_filter=None)
    assert out["rule_a"].tolist() == [False, True, False]


def test_rule_a_ignores_a_drop_just_under_the_threshold():
    df = _stitched(_hours("2024-01-01 00:00", 2), [-1.00, -1.099])
    assert not compute_flags(df, bottom_filter=None)["rule_a"].any()


def test_rule_a_ignores_rises():
    df = _stitched(_hours("2024-01-01 00:00", 2), [-1.50, -1.00])
    assert not compute_flags(df, bottom_filter=None)["rule_a"].any()


def test_rule_a_does_not_fire_across_a_data_gap():
    ts = [pd.Timestamp("2024-01-01 00:00"), pd.Timestamp("2024-01-05 00:00")]
    df = _stitched(ts, [-1.00, -1.90])
    assert not compute_flags(df, bottom_filter=None)["rule_a"].any()


def test_rule_a_skips_the_stitch_boundary_by_default():
    df = _stitched(_hours("2024-01-01 00:00", 4), [-1.00, -1.01, -1.50, -1.51])
    df["source"] = ["s1", "s1", "s2", "s2"]
    out = compute_flags(df, bottom_filter=None)
    assert out["at_boundary"].tolist() == [False, False, True, False]
    assert not out["rule_a"].any()


def test_rule_a_can_be_applied_across_the_boundary_on_request():
    df = _stitched(_hours("2024-01-01 00:00", 4), [-1.00, -1.01, -1.50, -1.51])
    df["source"] = ["s1", "s1", "s2", "s2"]
    out = compute_flags(df, bottom_filter=None, skip_stitch_boundary=False)
    assert out["rule_a"].tolist() == [False, False, True, False]


# --------------------------------------------------------------------------
# Rule B
# --------------------------------------------------------------------------

def test_rule_b_uses_the_ten_centimetre_margin():
    # bottom_filter -1.00 -> everything at or below -0.90 is flagged.
    df = _stitched(_hours("2024-01-01 00:00", 4), [-0.89, -0.90, -0.95, -1.20])
    out = compute_flags(df, bottom_filter=-1.00)
    assert out["rule_b"].tolist() == [False, True, True, True]


def test_rule_b_is_skipped_when_bottom_filter_is_missing():
    df = _stitched(_hours("2024-01-01 00:00", 3), [-9.0, -9.0, -9.0])
    assert not compute_flags(df, bottom_filter=None)["rule_b"].any()
    assert not compute_flags(df, bottom_filter=float("nan"))["rule_b"].any()


def test_rules_are_independent():
    df = _stitched(_hours("2024-01-01 00:00", 2), [-0.50, -1.50])
    out = compute_flags(df, bottom_filter=-1.00)
    # The second row is both a >=10 cm drop and below the filter margin.
    assert out["rule_a"].tolist() == [False, True]
    assert out["rule_b"].tolist() == [False, True]


def test_empty_series_produces_empty_flags():
    out = compute_flags(pd.DataFrame(columns=["timestamp", "raw_data", "source"]), -1.0)
    assert out.empty


# --------------------------------------------------------------------------
# Protection
# --------------------------------------------------------------------------

def test_manually_validated_fugro_origin_is_protected():
    assert is_protected(
        "fugro",
        "4423-241417_PB_HHW_01-01-2023 00_00_00_29-06-2026 00_00_00_Uur_20260629115503",
    )
    assert not is_protected("wiertsema", "86349-1")


def test_thresholds_match_the_specification():
    assert DROP_THRESHOLD_M == pytest.approx(0.10)
    assert FILTER_MARGIN_M == pytest.approx(0.10)
