"""Differential tests: fam_v1 sweep, penny-exact (incl. error parity)."""

import pytest

from pyanypia import compute
from tests.oracle_util import (
    assert_case_matches,
    assert_rejects_like_oracle,
    load_sweep,
    worker_from_spec,
)

SWEEP = load_sweep("fam_v1")


@pytest.mark.oracle
@pytest.mark.parametrize(
    "spec,expected", SWEEP, ids=[s["case_id"] for s, _ in SWEEP]
)
def test_case(spec: dict, expected: dict) -> None:
    if "error" in expected:
        assert_rejects_like_oracle(spec, expected)
        return
    r = compute(worker_from_spec(spec))
    assert_case_matches(r, expected)
