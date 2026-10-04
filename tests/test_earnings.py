import math

import numpy as np
import pytest
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW
from pyanypia import earnings as E
from pyanypia._years import FIRST_YEAR

ENG = present_law(2)


def _engine_aime(earn: dict[int, float], elig: int, n: int, last: int) -> float:
    """A direct transliteration of WageIndGeneral::indexEarnings +
    PiaMethod::orderEarnings + totalEarnCal, independent of the vectorized code."""
    idx = elig - 2
    first = max(min(earn), 1951)
    ind = {}
    for y in range(first, last + 1):
        e = min(earn.get(y, 0.0), ENG.base_oasdi[y])
        if y < idx:
            ind[y] = math.floor(ENG.fq[idx] * e / ENG.fq[y] * 100.0 + 0.5) / 100.0
        else:
            ind[y] = e
    order = sorted((v, y) for y, v in ind.items())
    chosen = {y for _, y in order[max(len(order) - n, 0):]}
    total = 0.0
    for y in range(first, last + 1):
        if y in chosen:
            total += ind[y]
    return math.floor(total / (n * 12.0))


def test_aime_matches_reference(rng):
    for _ in range(300):
        by = int(rng.integers(1940, 2000))
        start = by + 22 + int(rng.integers(0, 8))
        last = by + 62 + int(rng.integers(-5, 6))
        earn = {y: math.floor(rng.uniform(0, 2.2) * ENG.fq[y] * 100 + 0.5) / 100
                for y in range(start, last + 1)}
        for y in rng.choice(list(earn), size=len(earn) // 4, replace=False):
            earn[int(y)] = 0.0
        elig = by + 62
        assert E.aime(earn, elig, 35, last_year=last) == _engine_aime(earn, elig, 35, last)


def test_aime_vectorized_equals_rows(rng):
    m = rng.uniform(0, 150000, size=(50, 45))
    elig = rng.integers(2020, 2040, size=50)
    whole = E.aime(m, elig, 35, first_year=1980, last_year=2024)
    rows = [E.aime(m[i], int(elig[i]), 35, first_year=1980, last_year=2024) for i in range(50)]
    assert whole.tolist() == rows


def test_tied_earnings():
    earn = {y: 1000.0 for y in range(1990, 2030)}
    assert E.aime(earn, 2030, 35, last_year=2029) == _engine_aime(earn, 2030, 35, 2029)


def test_computation_years():
    assert E.computation_years(1960, 6, 2022) == 35
    assert E.computation_years(1990, 6, 2020, disabled=True) == 7   # elapsed 8, drop 1
    assert E.computation_years(1997, 6, 2020, disabled=True) == 2   # floor of 2
    assert E.computation_years(1980, 6, 2010, death_year=2010) == 3  # elapsed 8 - 5


def test_quarters_and_insured():
    assert E.quarters_of_coverage({2020: 1e6, 2021: 0.0, 2022: 3620.0}).tolist() == [4, 0, 2]
    earn = {y: 50000.0 for y in range(1990, 2000)}       # 40 QCs
    assert E.fully_insured(earn, 1960, 6, through_year=2021)
    earn39 = dict(earn)
    earn39[1999] = float(CURRENT_LAW.qc_amount[1999 - FIRST_YEAR] * 3)  # 39 QCs
    assert not E.fully_insured(earn39, 1960, 6, through_year=2021)


def test_years_of_coverage():
    amt = CURRENT_LAW.yoc_specmin
    earn = {2000: float(amt[2000 - FIRST_YEAR]), 2001: float(amt[2001 - FIRST_YEAR]) - 1}
    assert E.years_of_coverage(earn, last_year=2001) == 1
    assert E.years_of_coverage(earn, last_year=1999) == 0


def test_validation_messages():
    with pytest.raises(ValueError, match="comp_years: must be at least 1"):
        E.aime({2000: 1.0}, 2030, 0)
    with pytest.raises(ValueError, match="earnings: negative"):
        E.aime({2000: -1.0}, 2030, 35)


def test_indexed_earnings_shape_and_cap():
    x = E.indexed_earnings(np.array([[1e7, 1e7]]), 2030, first_year=2027)
    cap = CURRENT_LAW.taxmax[2027 - FIRST_YEAR]
    assert x.shape == (1, 2) and x[0, 1] == CURRENT_LAW.taxmax[2028 - FIRST_YEAR]
    assert x[0, 0] == math.floor(CURRENT_LAW.awi[2028 - FIRST_YEAR] * cap
                                 / CURRENT_LAW.awi[2027 - FIRST_YEAR] * 100 + 0.5) / 100
