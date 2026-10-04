"""Input coercion and validation shared by every public function."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import ArrayLike


def check(name: str, bad: ArrayLike, what: str) -> None:
    """Raises if any element of `bad` is true, naming the count and first row."""
    b = np.asarray(bad)
    if not b.any():
        return
    if b.ndim == 0:
        raise ValueError(f"{name}: {what}")
    rows = b.reshape(b.shape[0], -1).any(axis=1)
    idx = np.flatnonzero(rows)
    raise ValueError(f"{name}: {what} in {len(idx)} row(s); first at row {idx[0]}")


def as_float(name: str, x: ArrayLike) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    check(name, ~np.isfinite(a), "must be finite")
    return a


def as_int(name: str, x: ArrayLike) -> np.ndarray:
    a = np.asarray(x)
    if a.dtype.kind in "iu":
        return a.astype(np.int64)
    if a.dtype.kind == "b":
        raise ValueError(f"{name}: must be whole numbers, not booleans")
    f = np.asarray(a, dtype=float)
    check(name, ~np.isfinite(f) | (f != np.floor(f)), "must be whole numbers")
    return f.astype(np.int64)


def as_earnings(
    earnings: Mapping[int, float] | ArrayLike, first_year: int | None
) -> tuple[np.ndarray, int, bool]:
    """Returns (matrix (n, Y), first_year, single).

    A `{year: amount}` dict or a 1-D array is one worker (`single=True`);
    a 2-D array is one row per worker and needs `first_year`.
    """
    from pyanypia._years import FIRST_YEAR, LAST_YEAR

    if isinstance(earnings, Mapping):
        if not earnings:
            raise ValueError("earnings: empty")
        lo, hi = min(earnings), max(earnings)
        row = np.zeros(hi - lo + 1)
        for year, v in earnings.items():
            row[year - lo] = v
        m, first, single = row[None, :], lo, True
    else:
        a = np.asarray(earnings, dtype=float)
        if first_year is None:
            raise ValueError("first_year: required when earnings is an array")
        if a.ndim == 1:
            m, single = a[None, :], True
        elif a.ndim == 2:
            m, single = a, False
        else:
            raise ValueError(f"earnings: must be 1-D or 2-D, got {a.ndim}-D")
        first = int(first_year)
    check("earnings", ~np.isfinite(m), "not finite")
    check("earnings", m < 0, "negative")
    if first < FIRST_YEAR or first + m.shape[1] - 1 > LAST_YEAR:
        raise ValueError(f"earnings: years must lie within {FIRST_YEAR}-{LAST_YEAR}")
    return m, first, single


def out(x: Any) -> Any:
    """0-d arrays come back as Python scalars; everything else unchanged."""
    a = np.asarray(x)
    return a.item() if a.ndim == 0 else a
