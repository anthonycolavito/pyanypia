"""The special minimum PIA (SpecMin.cpp): a table by years of coverage over
10, carried forward by COLAs from $11.50 a year in January 1979."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_int, out
from pyanypia._years import FIRST_YEAR
from pyanypia.policy import CURRENT_LAW, Policy


def special_minimum_pia(
    years_of_coverage: ArrayLike, benefit_year: ArrayLike, benefit_month: ArrayLike = 12, *,
    policy: Policy = CURRENT_LAW,
) -> tuple[Any, Any]:
    """(PIA, family maximum) under the special minimum for a benefit month
    from 1979. Zero for 10 or fewer years of coverage; 30 years or more get
    the top amount. Count the years with `years_of_coverage`."""
    yoc, by, bm = np.broadcast_arrays(as_int("years_of_coverage", years_of_coverage),
                                      as_int("benefit_year", benefit_year),
                                      as_int("benefit_month", benefit_month))
    pia_t, mfb_t, pia01, mfb01 = policy.spec_min_tables
    excess = np.clip(yoc - 10, 0, 20)
    before_increase = bm < np.where(by >= 1983, 12, 6)
    # August-November 2001 pay the December 2000 amounts with the 1999 correction
    aug2001 = before_increase & (by == 2001) & (bm >= 8)
    year = np.where(before_increase, by - 1, by)
    row = np.maximum(excess - 1, 0)
    col = np.clip(year - FIRST_YEAR, 0, pia_t.shape[1] - 1)
    pia = np.where(aug2001, pia01[row], pia_t[row, col])
    mfb = np.where(aug2001, mfb01[row], mfb_t[row, col])
    has = excess > 0
    return out(np.where(has, pia, 0.0)), out(np.where(has, mfb, 0.0))
