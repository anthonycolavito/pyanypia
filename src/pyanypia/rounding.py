"""SSA rounding rules, vectorized. Transliterated from BenefitAmount.cpp.

Constants and operation order are copied from the C++ so results match the
official calculator bit-for-bit on IEEE doubles. Do not "clean up" the
arithmetic.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

AMEND73_YEAR = 1973  # margin for rounding up changed 0.005 -> 0.0001
AMEND82_YEAR = 1982  # dime rounding changed from up to down


def round_benefit(amount: ArrayLike, year: ArrayLike) -> np.ndarray:
    """Rounds a PIA or MFB to a multiple of $0.10: down from 1982, up before
    (with a half-cent margin through 1972). `year` is the benefit-increase
    year, or the year before a wage-indexed formula's eligibility year."""
    a = np.asarray(amount, dtype=float)
    y = np.asarray(year)
    down = np.floor(10.0 * a + 0.0005) / 10.0
    q = np.where(y >= AMEND73_YEAR, 0.009, 0.499)
    x100 = np.fmod(a * 100.0, 10.0)
    up = np.where(x100 < q, a - x100 / 100.0, a + (0.10 - x100 / 100.0))
    return np.asarray(np.where(y >= AMEND82_YEAR, down, up))


def round_wage(value: ArrayLike) -> np.ndarray:
    """Earnings and average wages round to the cent."""
    return np.asarray(np.floor(np.asarray(value, dtype=float) * 100.0 + 0.5) / 100.0)


def apply_cola(amount: ArrayLike, percent: ArrayLike, year: ArrayLike) -> np.ndarray:
    a = np.asarray(amount, dtype=float) * (1.0 + np.asarray(percent, dtype=float) / 100.0)
    return round_benefit(a, year)


def floor_dollar(amount: ArrayLike) -> np.ndarray:
    """Benefits from June 1982 are paid in whole dollars, rounded down."""
    return np.asarray(np.floor(np.asarray(amount, dtype=float)))
