import numpy as np
import pytest
from anypia_engine.engine.methods.wage_indexed import windfall_perc

from pyanypia import CURRENT_LAW, gpo_offset, retired_worker, wep_pia
from pyanypia.wep import _windfall_first_pct
from tests.cases import adjusted_birth_index, retired_cases
from tests.engine import run_retired

WEP = CURRENT_LAW.replace(wep_enabled=True)


def test_windfall_percentage_matches_engine():
    for elig in range(1979, 2030):
        for ben in (elig, elig + 3):
            yoc = np.arange(0, 35)
            got = _windfall_first_pct(np.full(35, elig), np.full(35, ben), yoc, 0.9)
            assert got.tolist() == [windfall_perc(elig, ben, int(y))[0] for y in yoc]


@pytest.mark.parametrize("seed", [42, 43])
def test_retired_with_pension_vs_engine(seed):
    rng = np.random.default_rng(seed)
    bad, n = [], 0
    for c in retired_cases(rng, 1500):
        ben_year = (adjusted_birth_index(c.birth) + c.benefit_age) // 12
        if ben_year >= 2024 or c.birth[0] + 62 <= 1986:
            continue
        pension = round(float(rng.uniform(200, 3000)), 2)
        r = run_retired(c, noncovered_pension=pension)
        if r.method not in {"WAGE_IND", "SPEC_MIN"}:
            continue
        n += 1
        ours = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age,
                              birth_day=c.birth[2], benefit_age=c.benefit_age,
                              noncovered_pension=pension, policy=WEP)
        got = (ours.pia, ours.mfb, ours.benefit)
        want = (r.pia, r.mfb, r.monthly_benefit)
        if got != want:
            bad.append((c, got, want))
    assert n > 100 and not bad, bad[:2]


def test_wep_lowers_pia_and_is_off_by_default():
    earn = {y: 20000.0 for y in range(1990, 2010)}  # 20 years: partly exempt
    on = retired_worker(earn, 1955, 6, 800, noncovered_pension=2000.0, policy=WEP)
    off = retired_worker(earn, 1955, 6, 800, noncovered_pension=2000.0)
    assert on.pia < off.pia
    assert off.pia == retired_worker(earn, 1955, 6, 800).pia


def test_wep_pia_floor_and_exemption():
    regular = wep_pia(2000.0, 2010, 30, 5000.0, benefit_year=2011)
    assert regular == wep_pia(2000.0, 2010, 10, 0.0, benefit_year=2011)
    small_pension = wep_pia(2000.0, 2010, 10, 100.0, benefit_year=2011)
    assert small_pension == regular - 50.0  # half the pension is the most it takes


def test_gpo_offset():
    assert gpo_offset(1000.0, 900.0) == 400.0
    assert gpo_offset(np.array([500.0, 1000.0]), np.array([1500.0, 0.0])).tolist() == [
        0.0, 1000.0]
    assert gpo_offset(1000.5, 0.0) == 1000.0
