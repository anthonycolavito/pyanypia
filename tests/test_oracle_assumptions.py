"""Differential tests: assum_v1 — the assumption codes that are not
Trustees alternatives.

Code 6, the old Statement assumptions, projects no wage growth and
instead scales the amounts by a percent for every year of eligibility
past the current one. Codes 4 and 5 do not, and are here as controls.
Every other sweep uses 1, 2 or 3, so this adjustment went unexercised.
"""

import pytest

from pyanypia import compute
from pyanypia.params import params_for
from tests.oracle_util import (
    assert_case_matches,
    assert_rejects_like_oracle,
    load_sweep,
    worker_from_spec,
)

SWEEP = load_sweep("assum_v1")


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected", SWEEP, ids=[s["case_id"] for s, _ in SWEEP]
)
def test_case(spec: dict, expected: dict) -> None:
    if "error" in expected:
        assert_rejects_like_oracle(spec, expected)
        return
    params = params_for(spec["ialtbi"], spec["ialtaw"])
    r = compute(worker_from_spec(spec), params=params)
    assert_case_matches(r, expected)
