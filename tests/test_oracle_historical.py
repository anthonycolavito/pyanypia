"""Historical cohorts: old-start, PIA-table, transitional guarantee and
frozen minimum, penny-exact against the oracle."""

import pytest

from pyanypia import compute
from tests.oracle_util import assert_case_matches, load_sweep, worker_from_spec

SWEEP = load_sweep("hist_v1")


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected", SWEEP, ids=[s["case_id"] for s, _ in SWEEP]
)
def test_historical_case(spec: dict, expected: dict) -> None:
    assert "error" not in expected, "oracle rejected this case"
    r = compute(worker_from_spec(spec))
    assert_case_matches(r, expected)
