"""Differential tests: freeze_v1 — earnings inside a freeze window, and
cases with two periods of disability.

The non-freeze computation answers what the benefit would be had the
disability freeze not applied, so it can only be told apart from the
ordinary computation by a case with earnings inside a freeze window.
Until this sweep there were none, and none with a second period of
disability either -- so WAGE_IND_NON_FREEZE could apply the freeze
filter it exists to omit and every suite still passed.
"""

import pytest

from pyanypia import compute
from tests.oracle_util import (
    assert_case_matches,
    assert_rejects_like_oracle,
    load_sweep,
    worker_from_spec,
)

SWEEP = load_sweep("freeze_v1")


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
