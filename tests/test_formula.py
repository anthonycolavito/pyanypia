import json
import pathlib

import numpy as np
from anypia_engine.dates import MonthYear
from anypia_engine.engine.methods import base as mbase
from anypia_engine.engine.methods import wage_indexed as wi
from anypia_engine.params import present_law

from pyanypia import CURRENT_LAW, formula

ENG = present_law(2)
G = json.loads((pathlib.Path(__file__).parent / "data" / "params_alt2.json").read_text())


def test_bend_points_match_cpp_goldens():
    for ys, row in G["years"].items():
        y = int(ys)
        if y < 1979:
            continue
        assert formula.bend_points(y).tolist() == row["bp_pia"], y
        assert formula.family_max_bend_points(y).tolist() == row["bp_mfb"], y


def test_pia_matches_engine(rng):
    aimes = np.floor(rng.uniform(0, 15000, 3000))
    eligs = rng.integers(1979, 2090, 3000)
    got = formula.pia(aimes, eligs)
    for a, e, g in zip(aimes, eligs, got, strict=True):
        portions = wi.set_portion_aime(float(a), ENG.bend_points_pia(int(e)))
        assert g == wi.aimepia_cal(portions, ENG.perc_pia(int(e)), int(e) - 1)


def test_family_max_matches_engine(rng):
    pias = np.round(rng.uniform(0, 5000, 2000), 1)
    eligs = rng.integers(1979, 2090, 2000)
    got = formula.family_max(pias, eligs)
    for p, e, g in zip(pias, eligs, got, strict=True):
        portions = mbase.set_portion_pia_elig(float(p), ENG.bend_points_mfb(int(e)))
        assert g == mbase.mfb_cal(portions, mbase.PERC_MFB, int(e) - 1)


def _engine_colas(amount: float, elig: int, ben: MonthYear) -> float:
    pia77 = {elig - 1: amount}
    year3 = ben.year - 1 if ben.month < ENG.month_beninc(ben.year) else ben.year
    for y in range(elig, year3 + 1):
        if ENG.is_applicable_cola99(y, ben):
            pia77[y] = ENG.apply_cola99(pia77[y - 1])
        else:
            pia77[y] = ENG.apply_cola(pia77[y - 1], y, elig)
    return pia77[year3] if elig <= year3 else amount


def test_apply_colas_matches_engine(rng):
    for _ in range(1500):
        elig = int(rng.integers(1979, 2060))
        by = int(rng.integers(elig, min(elig + 30, 2105) + 1))
        bm = int(rng.integers(1, 13))
        amt = float(np.round(rng.uniform(100, 4000), 1))
        got = formula.apply_colas(amt, elig, by, bm)
        assert got == _engine_colas(amt, elig, MonthYear(by, bm)), (elig, by, bm)


def test_apply_colas_vectorized_equals_scalar(rng):
    elig = rng.integers(1979, 2060, 300)
    by = elig + rng.integers(0, 30, 300)
    bm = rng.integers(1, 13, 300)
    amt = np.round(rng.uniform(100, 4000, 300), 1)
    whole = formula.apply_colas(amt, elig, by, bm)
    assert whole.tolist() == [formula.apply_colas(float(a), int(e), int(y), int(m))
                              for a, e, y, m in zip(amt, elig, by, bm, strict=True)]


def test_more_brackets_via_policy():
    p = CURRENT_LAW.replace(pia_bend_base=(180.0, 1085.0, 2000.0),
                            pia_pct=(0.9, 0.32, 0.15, 0.05))
    assert formula.bend_points(2030, policy=p).shape == (3,)
    assert formula.pia(20000.0, 2030, policy=p) < formula.pia(20000.0, 2030)
