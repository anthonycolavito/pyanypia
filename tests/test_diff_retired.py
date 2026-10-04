"""retired_worker against the archived engine, case by case, to the cent."""

import numpy as np
import pytest

from pyanypia import Policy, retired_worker
from tests.cases import as_matrix, column, retired_cases
from tests.engine import run_retired

SUPPORTED = {"WAGE_IND", "SPEC_MIN"}


def _sweep(n: int, alt: int, seed: int) -> None:
    cases = retired_cases(np.random.default_rng(seed), n)
    m, first = as_matrix(cases)
    ours = retired_worker(
        m, column(cases, lambda c: c.birth[0]), column(cases, lambda c: c.birth[1]),
        column(cases, lambda c: c.claim_age), first_year=first,
        birth_day=column(cases, lambda c: c.birth[2]),
        benefit_age=column(cases, lambda c: c.benefit_age), policy=Policy.current_law(alt))
    excluded, bad = 0, []
    for i, c in enumerate(cases):
        r = run_retired(c, alt)
        if r.method not in SUPPORTED:
            excluded += 1
            continue
        got = (ours.aime[i], ours.pia[i], ours.mfb[i], ours.factor[i], ours.benefit[i],
               bool(ours.insured[i]))
        want = (r.aime, r.pia, r.mfb, r.reduction_factor, r.monthly_benefit, r.insured)
        if got != want:
            bad.append((i, c.birth, c.claim_age, c.benefit_age, got, want))
    assert not bad, f"{len(bad)} mismatches; first: {bad[:3]}"
    assert excluded <= 0.05 * n, f"{excluded} of {n} cases excluded"


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_retired_vs_engine(alt):
    _sweep(400, alt, seed=100 + alt)


@pytest.mark.slow
def test_retired_vs_engine_large():
    _sweep(6000, 2, seed=7)


def test_vectorized_equals_scalar():
    cases = retired_cases(np.random.default_rng(3), 60)
    m, first = as_matrix(cases)
    by, bm, bd = (column(cases, lambda c, k=k: c.birth[k]) for k in range(3))
    claim = column(cases, lambda c: c.claim_age)
    whole = retired_worker(m, by, bm, claim, first_year=first, birth_day=bd)
    for i in range(60):
        one = retired_worker(m[i], int(by[i]), int(bm[i]), int(claim[i]), first_year=first,
                             birth_day=int(bd[i]))
        assert (one.aime, one.pia, one.mfb, one.benefit) == (
            whole.aime[i], whole.pia[i], whole.mfb[i], whole.benefit[i])
