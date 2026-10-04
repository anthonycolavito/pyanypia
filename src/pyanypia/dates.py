"""Month arithmetic. SSA counts ages from the day before birth."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_int, check


def adjusted_birth(
    birth_year: ArrayLike, birth_month: ArrayLike, birth_day: ArrayLike = 15
) -> tuple[np.ndarray, np.ndarray]:
    """(year, month) of the day before birth. Only a birth on the 1st moves
    it, into the previous month: such a person attains each age a month early."""
    by, bm, bd = np.broadcast_arrays(as_int("birth_year", birth_year),
                                     as_int("birth_month", birth_month),
                                     as_int("birth_day", birth_day))
    check("birth_month", (bm < 1) | (bm > 12), "must be 1-12")
    check("birth_day", (bd < 1) | (bd > 31), "must be 1-31")
    first = bd == 1
    m = np.where(first, bm - 1, bm)
    y = np.where(first & (m == 0), by - 1, by)
    return y, np.where(m == 0, 12, m)


def month_index(year: ArrayLike, month: ArrayLike) -> np.ndarray:
    """Months since January of year 0, so month differences are subtractions."""
    return np.asarray(12 * np.asarray(year) + np.asarray(month) - 1)


def from_month_index(i: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(i)
    return a // 12, a % 12 + 1


def cola_year(year: ArrayLike, month: ArrayLike) -> np.ndarray:
    """Year of the latest benefit increase in effect in (year, month).
    Increases take effect in December from 1983, and in June 1974-1982."""
    y, m = np.asarray(year), np.asarray(month)
    beninc = np.where(y >= 1983, 12, 6)
    return np.asarray(np.where(m < beninc, y - 1, y))
