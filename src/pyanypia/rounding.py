"""SSA rounding primitives, transliterated from BenefitAmount.cpp.

Every constant (0.0005, 0.009, 0.499, ...) and operation order is copied
from the C++ so results match the official calculator bit-for-bit on IEEE
doubles. Do not "clean up" the arithmetic.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyanypia.dates import MonthYear

AMEND73_YEAR = 1973  # margin for dime rounding changed 0.005 -> 0.0001
AMEND82_YEAR = 1982  # dime rounding changed from up to down
AMEND2000_YEAR = 2000  # statement rounding changed $5 -> $1
AMEND82 = (1982, 6)  # June 1982: benefits truncated to lower dollar


def round_benefit(amount: float, year: int) -> float:
    """Rounds a PIA or MFB to the appropriate multiple of $0.10.

    ``year`` is the year of benefit increase, or the year prior to the year
    of a wage-indexed formula. June 1982 and later increases round down;
    earlier increases round up (with a half-cent rule through 1972).
    """
    if year >= AMEND82_YEAR:
        return math.floor(10.0 * amount + 0.0005) / 10.0
    q = 0.009 if year >= AMEND73_YEAR else 0.499
    x100 = math.fmod(amount * 100.0, 10.0)
    if x100 < q:
        return amount - x100 / 100.0
    return amount + (0.10 - x100 / 100.0)


def unround_benefit(amount: float, year: int) -> float:
    """Inverse of :func:`round_benefit` (used to back out COLAs)."""
    if year > AMEND82_YEAR:
        return math.floor(10.0 * amount + 0.999) / 10.0
    q = 9.99 if year >= AMEND73_YEAR else 9.501
    x100 = 10.0 - math.fmod(amount * 100.0, 10.0)
    if x100 > q:
        return amount + x100 / 100.0
    return amount + x100 / 100.0 - 0.10


def apply_cola(amount: float, percent: float, year: int) -> float:
    """Applies a benefit increase and rounds per the year's rule."""
    amount *= 1.0 + percent / 100.0
    return round_benefit(amount, year)


def unapply_cola(amount: float, percent: float, year: int) -> float:
    """Removes a benefit increase and unrounds per the year's rule."""
    amount *= 100.0 / (100.0 + percent)
    return unround_benefit(amount, year)


def round_to_dollar(amount: float, ben_date: MonthYear) -> float:
    """Truncates a benefit to a whole dollar for June 1982 and later."""
    if (ben_date.year, ben_date.month) >= AMEND82:
        return math.floor(amount)
    return amount


def round_statement(amount: float, year: int) -> int:
    """Social Security Statement rounding: down to $5 before 2000, to $1
    in 2000 and later."""
    if year < AMEND2000_YEAR:
        return 5 * int((amount + 0.01) / 5.0)
    return int(amount + 0.01)
