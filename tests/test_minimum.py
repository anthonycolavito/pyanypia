import numpy as np
import pytest
from anypia_engine.dates import MonthYear
from anypia_engine.params import present_law

from pyanypia import retired_worker, special_minimum_pia
from tests.cases import Case
from tests.engine import run_retired

ENG = present_law(2)


@pytest.mark.parametrize("ym", [(1985, 6), (1999, 12), (2001, 7), (2001, 8), (2001, 12),
                                (2026, 11), (2026, 12), (2070, 3)])
def test_table_lookup_matches_engine(ym):
    yoc = np.arange(0, 36)
    pia, mfb = special_minimum_pia(yoc, *ym)
    for y, p, f in zip(yoc, pia, mfb, strict=True):
        excess = min(max(int(y) - 10, 0), 20)
        assert p == ENG.get_spec_min_pia(MonthYear(*ym), excess)
        assert f == ENG.get_spec_min_mfb(MonthYear(*ym), excess)


@pytest.mark.parametrize("claim", [62 * 12 + 1, 66 * 12, 70 * 12])
def test_low_earner_gets_special_minimum(claim):
    earn = {y: round(float(ENG.yoc_amt_specmin[y]) * 1.01, 2) for y in range(1952, 1992)}
    case = Case((1930, 5, 15), earn, claim_age=claim, benefit_age=claim)
    r = run_retired(case)
    ours = retired_worker(earn, 1930, 5, claim)
    assert r.method == "SPEC_MIN" and ours.method == "special_minimum"
    assert (ours.pia, ours.mfb, ours.benefit) == (r.pia, r.mfb, r.monthly_benefit)
