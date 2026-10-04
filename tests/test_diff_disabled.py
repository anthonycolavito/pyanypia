"""disabled_worker against the archived engine, to the cent."""

import numpy as np
import pytest

from pyanypia import Policy, disabled_worker
from tests.cases import as_matrix, column, disabled_cases
from tests.engine import run_disabled

SUPPORTED = {"WAGE_IND", "SPEC_MIN", "CHILD_CARE", " "}  # " ": every PIA is zero


def _ours(cases, alt=2):
    m, first = as_matrix(cases)
    cc = np.zeros_like(m, dtype=bool)
    for i, c in enumerate(cases):
        for y in c.extra.get("childcare", ()):
            cc[i, y - first] = True
    onset = lambda k: column(cases, lambda c: c.extra["onset"][k])  # noqa: E731
    ent = column(cases, lambda c: c.extra["ent"])
    ben = column(cases, lambda c: c.extra["ben"])
    return disabled_worker(
        m, column(cases, lambda c: c.birth[0]), column(cases, lambda c: c.birth[1]),
        onset(0), onset(1), first_year=first, onset_day=onset(2),
        entitlement=(ent // 12, ent % 12 + 1), benefit=(ben // 12, ben % 12 + 1),
        childcare=cc if cc.any() else None, policy=Policy.current_law(alt))


def _sweep(cases, alt=2):
    ours = _ours(cases, alt)
    bad, excluded, methods = [], 0, set()
    for i, c in enumerate(cases):
        r = run_disabled(c, alt)
        methods.add(r.method)
        # a special-minimum winner takes its family maximum from the method
        # with the highest AIME, which can be the (unmodelled) non-freeze one
        out_of_scope = r.method == "SPEC_MIN" and "WAGE_IND_NON_FREEZE" in r.methods
        if r.method not in SUPPORTED or out_of_scope:
            excluded += 1
            continue
        got = (ours.aime[i], ours.pia[i], ours.mfb[i], ours.benefit[i])
        want = (r.methods[r.method].aime if r.method in ("WAGE_IND", "CHILD_CARE") else r.aime,
                r.pia, r.mfb, r.monthly_benefit)
        if got != want:
            bad.append((i, c.birth, c.extra, got, want))
    assert not bad, f"{len(bad)} mismatches; first: {bad[:2]}"
    assert excluded <= 0.05 * len(cases), (excluded, methods)
    return methods


@pytest.mark.parametrize("alt", [1, 2, 3])
def test_disabled_vs_engine(alt):
    _sweep(disabled_cases(np.random.default_rng(200 + alt), 400), alt)


def test_childcare_vs_engine():
    methods = _sweep(disabled_cases(np.random.default_rng(9), 600, childcare=True))
    assert "CHILD_CARE" in methods


def test_default_entitlement_follows_waiting_period():
    b = disabled_worker({y: 50000.0 for y in range(2000, 2021)}, 1975, 3, 2020, 6)
    assert b.elig_year == 2020


@pytest.mark.slow
def test_disabled_vs_engine_large():
    _sweep(disabled_cases(np.random.default_rng(11), 5000))


def test_disabled_vectorized_equals_scalar():
    cases = disabled_cases(np.random.default_rng(12), 40, childcare=True)
    whole = _ours(cases)
    for i, c in enumerate(cases):
        one = _ours([c])
        assert (one.pia[0], one.mfb[0], one.benefit[0]) == (
            whole.pia[i], whole.mfb[i], whole.benefit[i])
