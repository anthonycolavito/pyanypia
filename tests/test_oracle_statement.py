"""Social Security Statement estimates, penny-exact against the oracle."""

from __future__ import annotations

import pytest

from pyanypia.engine.statement import StatementType, calculate_statement
from tests.oracle_util import load_sweep, worker_from_spec

SWEEP = load_sweep("pebs_v1")

FIELDS = [
    ("oab_early", StatementType.OAB_EARLY, "benefit"),
    ("oab_full", StatementType.OAB_FULL, "benefit"),
    ("oab_delayed", StatementType.OAB_DELAYED, "benefit"),
    ("surv_benefit", StatementType.SURVIVOR, "benefit"),
    ("surv_pia", StatementType.SURVIVOR, "pia"),
    ("surv_mfb", StatementType.SURVIVOR, "mfb"),
    ("disab_pia", StatementType.DISABILITY, "pia"),
    ("disab_mfb", StatementType.DISABILITY, "mfb"),
]


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected", SWEEP, ids=[s["case_id"] for s, _ in SWEEP]
)
def test_statement_case(spec: dict, expected: dict) -> None:
    assert "error" not in expected, "oracle rejected this case"
    want = expected["pebs"]
    r = calculate_statement(
        worker_from_spec(spec),
        month_now=spec["pebs_month"],
        age_plan=spec["pebs_age_plan"],
        istart=spec["istart"],
        alt=spec["ialtbi"],
    )
    assert r.age_now.years == want["age_now_years"], "age now (years)"
    assert r.age_now.months == want["age_now_months"], "age now (months)"
    assert r.quarters_of_coverage == want["qc_total"], "quarters of coverage"
    for key, kind, attr in FIELDS:
        assert getattr(r.estimates[kind], attr) == want[key], key
