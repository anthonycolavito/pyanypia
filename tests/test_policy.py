import json
import pathlib

import numpy as np
import pytest
from anypia_engine.dates import MonthYear
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW, Policy
from pyanypia._years import FIRST_YEAR, LAST_YEAR

DATA = pathlib.Path(__file__).parent / "data"


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_series_match_engine(alt):
    pol, eng = Policy.current_law(alt), present_law(alt)
    for name, ours, theirs, first in (
        ("awi", pol.awi, eng.fq, 1937),
        ("taxmax", pol.taxmax, eng.base_oasdi, 1937),
        ("base77", pol.base77, eng.base_77, 1937),
        ("qc_amount", pol.qc_amount, eng.qc_amt, 1937),
        ("yoc_specmin", pol.yoc_specmin, eng.yoc_amt_specmin, 1951),
        ("yoc_wep", pol.yoc_wep, eng.yoc_amt_windfall, 1951),
        ("cola", pol.cola, eng.cpiinc, 1951),
    ):
        for y in range(first, LAST_YEAR + 1):
            assert ours[y - FIRST_YEAR] == theirs[y], (name, y)


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_against_cpp_parameter_goldens(alt):
    g = json.loads((DATA / f"params_alt{alt}.json").read_text())
    pol = Policy.current_law(alt)
    for ys, row in g["years"].items():
        y = int(ys) - FIRST_YEAR
        assert pol.awi[y] == row["fq"], ys
        assert pol.taxmax[y] == row["base_oasdi"], ys
        assert pol.qc_amount[y] == row["qc_amt"], ys


@pytest.mark.parametrize("alt", [1, 3])
def test_spec_min_table_matches_engine(alt):
    pol, eng = Policy.current_law(alt), present_law(alt)
    pia, mfb, pia01, mfb01 = pol.spec_min_tables
    for yoc in range(1, 21):
        for y in range(1979, LAST_YEAR + 1):
            assert pia[yoc - 1, y - FIRST_YEAR] == eng.get_spec_min_pia(MonthYear(y, 12), yoc)
            assert mfb[yoc - 1, y - FIRST_YEAR] == eng.get_spec_min_mfb(MonthYear(y, 12), yoc)
        assert pia01[yoc - 1] == eng.get_spec_min_pia(MonthYear(2001, 9), yoc)
        assert mfb01[yoc - 1] == eng.get_spec_min_mfb(MonthYear(2001, 9), yoc)


def test_nra_and_drc_by_eligibility_year():
    assert CURRENT_LAW.nra[1999 - FIRST_YEAR] == 780
    assert CURRENT_LAW.nra[2002 - FIRST_YEAR] == 786
    assert CURRENT_LAW.nra[2022 - FIRST_YEAR] == 804
    assert CURRENT_LAW.drc_rate_by_elig[2030 - FIRST_YEAR] == 2.0 / 300.0


def test_awi_growth_flows_into_taxmax():
    higher = CURRENT_LAW.replace(
        awi_growth={y: g + 1.0 for y, g in CURRENT_LAW.awi_growth.items()})
    i = 2040 - FIRST_YEAR
    assert higher.awi[i] > CURRENT_LAW.awi[i]
    assert higher.taxmax[i] > CURRENT_LAW.taxmax[i]
    assert higher.awi[2024 - FIRST_YEAR] == CURRENT_LAW.awi[2024 - FIRST_YEAR]


def test_with_series_overrides_one_year_only():
    p = CURRENT_LAW.with_series("taxmax", {2030: 250000.0})
    assert p.taxmax[2030 - FIRST_YEAR] == 250000.0
    assert p.taxmax[2031 - FIRST_YEAR] == CURRENT_LAW.taxmax[2031 - FIRST_YEAR]
    assert CURRENT_LAW.taxmax[2030 - FIRST_YEAR] != 250000.0


def test_derived_arrays_are_read_only():
    with pytest.raises(ValueError):
        CURRENT_LAW.awi[0] = 1.0


def test_validation():
    with pytest.raises(ValueError, match="pia_pct"):
        CURRENT_LAW.replace(pia_pct=(0.9, 0.32))
    with pytest.raises(ValueError, match="unknown series"):
        CURRENT_LAW.with_series("bogus", {2030: 1.0})
    with pytest.raises(ValueError, match="alt"):
        Policy.current_law(4)


def test_current_law_defaults():
    assert CURRENT_LAW.wep_enabled is False and CURRENT_LAW.gpo_enabled is False
    assert CURRENT_LAW.pia_pct == (0.90, 0.32, 0.15)
    assert np.isnan(CURRENT_LAW.yoc_specmin[1950 - FIRST_YEAR])
