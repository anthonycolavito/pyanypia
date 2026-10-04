"""family_benefits and deceased_worker against the archived engine."""

import numpy as np
import pytest

from pyanypia import (
    Auxiliary,
    deceased_worker,
    family_benefits,
    retired_worker,
    widow_guarantee_pia,
)
from tests.cases import adjusted_birth_index, life_family_cases, survivor_cases
from tests.engine import run_life_family, run_survivor

KIND = {"B": "spouse", "B2": "spouse_with_child", "C1": "child", "C2": "child",
        "D": "widow", "W": "disabled_widow", "E": "parent_with_child"}


def _aux(case, survivor=False):
    out = []
    for bic, birth, ent in case.extra["family"]:
        kind = KIND[bic.strip()]
        guarantee = None
        if survivor and kind in ("widow", "disabled_widow"):
            dy, dm, dd = case.extra["death"]
            ben = case.extra["ben"]
            disabled = kind == "disabled_widow"
            guarantee = widow_guarantee_pia(
                case.earnings, case.birth[0], case.birth[1], dy, dm, death_day=dd,
                birth_day=case.birth[2], widow_birth_year=birth[0],
                widow_birth_month=birth[1], widow_birth_day=birth[2],
                disabled_onset_year=(ent - 12) // 12 if disabled else None,
                entitlement_year=ent // 12 if disabled else None,
                benefit=(ben // 12, ben % 12 + 1))
        out.append(Auxiliary(kind, birth[0], birth[1], birth_day=birth[2],
                             claim_age=ent - adjusted_birth_index(birth),
                             guarantee_pia=guarantee))
    return out


def _paid(fam):
    return [float(x) for x in np.ravel(fam.benefit)]


@pytest.mark.parametrize("seed,n", [(1, 200), (2, 200), (3, 200),
                                    pytest.param(21, 3000, marks=pytest.mark.slow)])
def test_life_families_vs_engine(seed, n):
    bad, count = [], 0
    for c in life_family_cases(np.random.default_rng(seed), n):
        r = run_life_family(c)
        if r.method not in {"WAGE_IND", "SPEC_MIN"}:
            continue
        count += 1
        w = retired_worker(c.earnings, c.birth[0], c.birth[1], c.claim_age,
                           benefit_age=c.benefit_age)
        ben = adjusted_birth_index(c.birth) + c.benefit_age
        fam = family_benefits(w.pia, w.mfb, _aux(c), benefit_year=ben // 12,
                              benefit_month=ben % 12 + 1)
        want = [f.rounded_benefit for f in r.family]
        if _paid(fam) != want:
            bad.append((c, _paid(fam), want))
    assert count >= 0.95 * n and not bad, bad[:2]


@pytest.mark.parametrize("seed,n", [(4, 300), (5, 300), (6, 300),
                                    pytest.param(22, 3000, marks=pytest.mark.slow)])
def test_survivors_vs_engine(seed, n):
    bad, excluded = [], 0
    cases = survivor_cases(np.random.default_rng(seed), n)
    for c in cases:
        r = run_survivor(c)
        if r.method not in {"WAGE_IND", "SPEC_MIN"}:
            excluded += 1
            continue
        ben = c.extra["ben"]
        d = deceased_worker(c.earnings, c.birth[0], c.birth[1], c.extra["death"][0],
                            birth_day=c.birth[2], benefit=(ben // 12, ben % 12 + 1))
        fam = family_benefits(d.pia, d.mfb, _aux(c, survivor=True), benefit_year=ben // 12,
                              benefit_month=ben % 12 + 1, survivor=True)
        got = (d.pia, d.mfb, _paid(fam))
        want = (r.pia, r.mfb, [f.rounded_benefit for f in r.family])
        if got != want:
            bad.append((c, got, want))
    assert not bad, bad[:2]
    assert excluded <= 0.05 * len(cases), excluded


def test_family_maximum_binds():
    fam = family_benefits(2000.0, 3500.0, [Auxiliary("child")] * 4, benefit_year=2030)
    assert fam.after_max.sum() <= 1500.0 and fam.full.sum() == 4000.0


def test_absent_members_get_nothing():
    fam = family_benefits(np.array([2000.0, 2000.0]), np.array([3500.0, 3500.0]),
                          [Auxiliary("child", present=np.array([True, False]))],
                          benefit_year=2030)
    assert fam.benefit.tolist() == [[1000.0, 0.0]]


def test_wrong_kind_raises():
    with pytest.raises(ValueError, match="not a life beneficiary"):
        family_benefits(1000.0, 1500.0, [Auxiliary("widow")], benefit_year=2030)
