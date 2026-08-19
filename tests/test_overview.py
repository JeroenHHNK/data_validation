import pandas as pd
import pytest

from dashboard.overview import TOTAL_LABEL, append_total_row


def _summary():
    return pd.DataFrame([
        {"vendor": "fugro", "folder": "a", "amount_of_rows": 100,
         "reviewed_rows": 50, "rejected_rows": 10, "series_count": 2,
         "gecontroleerd_%": 50.0, "afgekeurd_%": 10.0},
        {"vendor": "wiertsema", "folder": "b", "amount_of_rows": 300,
         "reviewed_rows": 30, "rejected_rows": 90, "series_count": 4,
         "gecontroleerd_%": 10.0, "afgekeurd_%": 30.0},
    ])


def test_total_row_sums_both_vendors():
    out = append_total_row(_summary())
    total = out.iloc[-1]
    assert total["vendor"] == TOTAL_LABEL
    assert total["amount_of_rows"] == 400
    assert total["reviewed_rows"] == 80
    assert total["rejected_rows"] == 100
    assert total["series_count"] == 6


def test_total_percentages_come_from_the_summed_absolutes():
    total = append_total_row(_summary()).iloc[-1]
    # 80/400 and 100/400 -- not the mean of 50/10 and 10/30.
    assert total["gecontroleerd_%"] == pytest.approx(20.0)
    assert total["afgekeurd_%"] == pytest.approx(25.0)


def test_per_folder_rows_are_preserved():
    out = append_total_row(_summary())
    assert len(out) == 3
    assert out.iloc[0]["folder"] == "a"
    assert out.iloc[1]["folder"] == "b"


def test_appending_twice_does_not_double_count():
    once = append_total_row(_summary())
    twice = append_total_row(once)
    assert len(twice) == 3
    assert twice.iloc[-1]["amount_of_rows"] == 400


def test_empty_summary_is_returned_unchanged():
    empty = pd.DataFrame()
    assert append_total_row(empty).empty


def test_zero_rows_does_not_divide_by_zero():
    df = pd.DataFrame([
        {"vendor": "fugro", "folder": "a", "amount_of_rows": 0,
         "reviewed_rows": 0, "rejected_rows": 0, "series_count": 1,
         "gecontroleerd_%": 0.0, "afgekeurd_%": 0.0},
    ])
    total = append_total_row(df).iloc[-1]
    assert total["gecontroleerd_%"] == 0.0
    assert total["afgekeurd_%"] == 0.0
