"""Every sweep costed under Trustees alternatives I and III.

Alternative II is the intermediate set the other differential suites use.
These run the same cases under the low-cost and high-cost projections,
which move every wage, benefit increase, wage base and bend point that
gets projected -- so they exercise the projection machinery rather than
the historical series the alternatives share.

The Statement sweep is absent on purpose: its cases carry PEBS_ASSUM on
line 40 and UserAssumptions::pebsasmCheck refuses a Trustees alternative
for them, so a Statement case exists under one set of assumptions only.
"""

import pytest

from pyanypia import compute
from tests.oracle_util import (
    assert_case_matches,
    assert_rejects_like_oracle,
    load_sweep,
    worker_from_spec,
)

SWEEPS = (
    "retire_v1", "dib_v1", "surv_v1", "fam_v1", "hist_v1",
    "special_v1", "total_v1", "proj_v1",
)
ALTERNATIVES = (1, 3)

CASES = [
    (spec, expected, alt)
    for alt in ALTERNATIVES
    for sweep in SWEEPS
    for spec, expected in load_sweep(sweep, alt)
]
IDS = [
    f"alt{alt}-{spec['case_id']}" for spec, _, alt in CASES
]


@pytest.mark.oracle
@pytest.mark.parametrize("spec,expected,alt", CASES, ids=IDS)
def test_case(spec: dict, expected: dict, alt: int) -> None:
    if "error" in expected:
        assert_rejects_like_oracle(spec, expected, alt)
        return
    r = compute(worker_from_spec(spec), alt=alt)
    assert_case_matches(r, expected)
