"""MILESTONE test: every reform_v1 golden must match penny-exact.

Each case is computed twice over -- once per reform variant, plus a
present-law block that re-checks the baseline the variants are measured
against.
"""

import pytest

from pyanypia import compute
from tests.oracle_util import (
    assert_case_matches,
    load_reform_sweep,
    reform_params,
    worker_from_spec,
)

SWEEP = load_reform_sweep("reform_v1")


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected,variant", SWEEP, ids=[e["case_id"] for _, e, _ in SWEEP]
)
def test_reform_case(spec: dict, expected: dict, variant: str) -> None:
    assert "error" not in expected, "oracle rejected this case"
    r = compute(worker_from_spec(spec), params=reform_params(variant))
    assert_case_matches(r, expected)
