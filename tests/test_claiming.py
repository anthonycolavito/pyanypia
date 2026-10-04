from datetime import date, timedelta

import numpy as np
import pytest
from anypia_engine.dates import MonthYear
from anypia_engine.params import retire_age as ra

from pyanypia import claiming, dates


def test_adjusted_birth_first_of_month():
    y, m = dates.adjusted_birth(np.array([1960, 1960, 1960]), np.array([1, 3, 3]),
                                np.array([1, 1, 2]))
    assert y.tolist() == [1959, 1960, 1960] and m.tolist() == [12, 2, 3]


def test_cola_year():
    assert dates.cola_year(np.array([2026, 2026, 1980, 1980]),
                           np.array([11, 12, 5, 6])).tolist() == [2025, 2026, 1979, 1980]


def test_eligibility_year():
    assert claiming.eligibility_year(1960, 1, birth_day=1) == 2021
    assert claiming.eligibility_year(1960, 1) == 2022
    assert claiming.eligibility_year(1960, 6, onset_year=2005) == 2005
    assert claiming.eligibility_year(1960, 6, death_year=2030) == 2022


def test_nra_matches_engine():
    for by in range(1930, 2001):
        assert claiming.normal_retirement_age(by, 6) == ra.full_ret_age(by + 62).to_months(), by


def test_earliest_claim_age():
    assert claiming.earliest_claim_age(np.array([1, 2, 3, 15])).tolist() == [745, 744, 745, 745]


def test_factors_match_engine():
    months = np.arange(0, 61)
    assert claiming.early_reduction_factor(months).tolist() == [
        ra.factor_ar(int(m)) for m in months]
    assert claiming.spouse_reduction_factor(months).tolist() == [
        ra.factor_ar_aged_spouse(int(m)) for m in months]
    for elig in (1980, 1990, 2003, 2030):
        assert claiming.delayed_credit_factor(months, elig).tolist() == [
            ra.factor_dri(int(m), elig) for m in months]


def _engine_drc_months(dob: date, claim_age: int, benefit_age: int) -> int:
    kb = dob - timedelta(days=1)
    kb_my = MonthYear(kb.year, kb.month)
    nra = ra.full_ret_age(kb.year + 62)
    fra = kb_my.add_months(nra.to_months())
    return ra.months_dri(fra, kb.year + 62, kb, kb_my.add_months(claim_age),
                         kb_my.add_months(benefit_age), fra)


@pytest.mark.parametrize("dob", [date(1955, 3, 15), date(1960, 1, 1), date(1964, 12, 2)])
def test_drc_months_match_engine(dob):
    nra = claiming.normal_retirement_age(dob.year, dob.month, birth_day=dob.day)
    for claim in range(780, 861):
        for extra in (0, 5, 14):
            ar, drc = claiming.adjustment_months(dob.year, dob.month, claim, birth_day=dob.day,
                                                 benefit_age=claim + extra)
            if claim >= nra:
                assert ar == 0
                assert drc == _engine_drc_months(dob, claim, claim + extra), (claim, extra)
            else:
                assert (ar, drc) == (nra - claim, 0)


def test_benefit_factor_early_and_late():
    f = claiming.benefit_factor(np.array([1960, 1960]), np.array([6, 6]), np.array([745, 840]))
    assert f[0] == ra.factor_ar(804 - 745)
    assert f[1] == ra.factor_dri(36, 2022)  # age 70: every credit counts at once


def test_claim_before_earliest_age_raises():
    with pytest.raises(ValueError, match="claim_age: before the earliest"):
        claiming.benefit_factor(1960, 6, 744)


def test_monthly_benefit_rounds_then_floors():
    assert claiming.monthly_benefit(1234.5, 0.7, 2030, 6) == 864.0  # 864.15 -> 864.1 -> 864
