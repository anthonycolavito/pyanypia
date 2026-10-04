import numpy as np
from anypia_engine import rounding as eng

from pyanypia import rounding


def test_round_benefit_matches_engine_across_eras(rng):
    amounts = rng.uniform(0, 5000, 4000)
    amounts[:200] = np.round(amounts[:200], 1) + 0.0005  # near the dime boundary
    for year in (1970, 1975, 1981, 1982, 2000, 2030):
        got = rounding.round_benefit(amounts, year)
        want = [eng.round_benefit(float(a), year) for a in amounts]
        assert got.tolist() == want


def test_round_benefit_per_element_years():
    got = rounding.round_benefit(np.array([100.04, 100.04]), np.array([1981, 1982]))
    assert got.tolist() == [eng.round_benefit(100.04, 1981), eng.round_benefit(100.04, 1982)]


def test_apply_cola_matches_engine(rng):
    amounts = rng.uniform(0, 5000, 2000)
    for pct, year in ((2.5, 2026), (11.2, 1980), (0.0, 2010)):
        got = rounding.apply_cola(amounts, pct, year)
        assert got.tolist() == [eng.apply_cola(float(a), pct, year) for a in amounts]


def test_round_wage_and_floor_dollar():
    assert rounding.round_wage(np.array([2.344, 2.346])).tolist() == [2.34, 2.35]
    assert rounding.floor_dollar(np.array([1234.9, 7.0])).tolist() == [1234.0, 7.0]
