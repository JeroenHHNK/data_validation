import math

import pytest

from dataval.object_data import (
    midpoint_from_f_token,
    parse_fugro_filename,
    parse_wiertsema_filename,
)


# --------------------------------------------------------------------------
# Fugro
# --------------------------------------------------------------------------

def test_fugro_worked_example_without_cross_section():
    p = parse_fugro_filename("NL-260484-FB-FLB5040_HB18PB01_-2.2_-3.2_m_NAP_avg")
    assert p.name_timeseries == "NL-260484-FB-FLB5040_HB18PB01"
    assert p.bottom_filter == pytest.approx(-3.2)
    assert p.cross_sec_location is None


def test_fugro_worked_example_with_cross_section():
    p = parse_fugro_filename("NL-253677-FB-FLB5073_HB-SS060_BIT_PB1_-4.7_-5.7_m_NAP_avg")
    assert p.name_timeseries == "NL-253677-FB-FLB5073_HB-SS060_BIT_PB1"
    assert p.bottom_filter == pytest.approx(-5.7)
    assert p.cross_sec_location == "BIT"


def test_fugro_plain_m_nap_suffix_without_avg():
    p = parse_fugro_filename("NL-241417-ET-19111903_HB29-PB1_-0.54_-1.54_m_NAP")
    assert p.name_timeseries == "NL-241417-ET-19111903_HB29-PB1"
    assert p.bottom_filter == pytest.approx(-1.54)


def test_fugro_positive_filter_pair_takes_the_deeper_value():
    p = parse_fugro_filename("NL-241417-ET-19092315_B18-PB1_1.53_0.53_m_NAP")
    assert p.name_timeseries == "NL-241417-ET-19092315_B18-PB1"
    assert p.bottom_filter == pytest.approx(0.53)
    assert p.top_filter == pytest.approx(1.53)


def test_fugro_kr_token_is_matched_whole():
    p = parse_fugro_filename("NL-253677-FB-FLB5207_HB-WM044_KR_PB1_-3.2_-4.2_m_NAP_avg")
    assert p.cross_sec_location == "KR"
    assert p.cross_sec_known


def test_fugro_unknown_code_is_kept_as_text_and_flagged():
    p = parse_fugro_filename("NL-253677-FB-LB1112_HB-SS077_BITA_PB1_-3.1_-4.1_m_NAP_avg")
    assert p.cross_sec_location == "BITA"
    assert not p.cross_sec_known


def test_fugro_waterstand_has_no_filter_and_is_not_nap():
    p = parse_fugro_filename("NL-241417-ET-19121810_Waterstand_cmH2O")
    assert p.is_nap is False
    assert p.bottom_filter is None
    assert p.name_timeseries == "NL-241417-ET-19121810_Waterstand_cmH2O"


# --------------------------------------------------------------------------
# Wiertsema
# --------------------------------------------------------------------------

def test_wiertsema_worked_example():
    p = parse_wiertsema_filename("86349-1 MB049PB01 B_BE0377+32_BIKR_GMW_PB1_F-252")
    assert p.name_timeseries == "86349-1 MB049PB01 B_BE0377+32_BIKR_GMW_PB1"
    assert p.bottom_filter == pytest.approx(-3.02)
    assert p.cross_sec_location == "BIKR"


@pytest.mark.parametrize(
    "token,midpoint",
    [
        ("252", -2.52),     # centimetres, integer
        ("188", -1.88),     # centimetres, shallowest real value
        ("2096", -20.96),   # centimetres, deepest real value
        ("398.5", -3.985),  # centimetres with a decimal
        ("6.10", -6.10),    # metres
        ("19.95", -19.95),  # metres, deepest real value
        ("2.76", -2.76),    # metres, shallowest real value
    ],
)
def test_f_token_unit_disambiguation(token, midpoint):
    assert midpoint_from_f_token(token) == pytest.approx(midpoint)


def test_wiertsema_decimal_metre_token():
    p = parse_wiertsema_filename("87074-1 HB001PB01 HB_PU0013+0_BIT_GMW_PB1_F-6.10")
    assert p.bottom_filter == pytest.approx(-6.60)
    assert p.cross_sec_location == "BIT"


def test_wiertsema_sensor_suffix_is_stripped_before_parsing():
    p = parse_wiertsema_filename(
        "83034-1 HB001PB01 BE0049+00_BUKR_GMW_PB1_F-229_sensor_2"
    )
    assert p.name_timeseries == "83034-1 HB001PB01 BE0049+00_BUKR_GMW_PB1"
    assert p.sensor == 2
    assert p.bottom_filter == pytest.approx(-2.79)


def test_wiertsema_sensors_of_one_well_share_a_name_timeseries():
    a = parse_wiertsema_filename("83034-1 HB002PB01 BE0049+00_BIKR_GMW_PB1_F-227_sensor_1")
    b = parse_wiertsema_filename("83034-1 HB002PB01 BE0049+00_BIKR_GMW_PB1_F-227_sensor_3")
    assert a.name_timeseries == b.name_timeseries
    assert a.bottom_filter == b.bottom_filter


def test_wiertsema_missing_f_token_yields_nan_filter():
    p = parse_wiertsema_filename("84507-2 HB203PB01 PB_HB_DP 170+10 m_BIT")
    assert p.bottom_filter is None
    assert p.cross_sec_location == "BIT"


def test_wiertsema_bare_stem_has_no_filter_and_no_code():
    p = parse_wiertsema_filename("86349-1 HB006PB01")
    assert p.bottom_filter is None
    assert p.cross_sec_location is None


def test_wiertsema_multi_token_unknown_code_is_preserved():
    p = parse_wiertsema_filename("83034-1 HB003PB01 BE0049+00_INST_B_GMW_PB1_F-365")
    assert p.cross_sec_location == "INST_B"
    assert not p.cross_sec_known


def test_wiertsema_transposed_code_is_flagged_not_silently_accepted():
    p = parse_wiertsema_filename("83034-1 HB020PB01 BE0341+40_BIRK_GMW_PB1_F-350")
    assert p.cross_sec_location == "BIRK"
    assert not p.cross_sec_known


def test_wiertsema_bib_is_a_known_code():
    p = parse_wiertsema_filename("86349-1 HB007PB01 HB_BE0092+15_BIB_GMW_PB1_F-450")
    assert p.cross_sec_location == "BIB"
    assert p.cross_sec_known
    assert p.bottom_filter == pytest.approx(-5.00)


def test_wiertsema_trailing_code_without_gmw():
    p = parse_wiertsema_filename("84507-1 HB006PB01 PB_HB_DP 172_KR_sensor_1")
    assert p.cross_sec_location == "KR"
    assert p.cross_sec_known
    assert math.isnan(p.bottom_filter) if p.bottom_filter is not None else True


def test_fugro_copy_export_still_yields_the_filter_pair():
    p = parse_fugro_filename(
        "NL-253677-FB-LB1603_HB-SS059_BIT_PB1_-4.3_-5.3_-_Copy_2_m_NAP_avg"
    )
    assert p.name_timeseries == "NL-253677-FB-LB1603_HB-SS059_BIT_PB1"
    assert p.bottom_filter == pytest.approx(-5.3)
    assert p.cross_sec_location == "BIT"
    assert any("Copy" in n for n in p.notes)
