"""The year axis every policy series is stored on."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import check

FIRST_YEAR = 1937
LAST_YEAR = 2105
N_YEARS = LAST_YEAR - FIRST_YEAR + 1


def to_array(values: Mapping[int, float]) -> np.ndarray:
    """A year-indexed float array, NaN where `values` has no entry."""
    arr = np.full(N_YEARS, np.nan)
    for year, v in values.items():
        if not FIRST_YEAR <= year <= LAST_YEAR:
            raise ValueError(f"year {year} outside {FIRST_YEAR}-{LAST_YEAR}")
        arr[year - FIRST_YEAR] = v
    return arr


def at(series: np.ndarray, years: ArrayLike, name: str) -> np.ndarray:
    """`series[years]`, refusing years outside the data or without a value."""
    y = np.asarray(years)
    check(name, (y < FIRST_YEAR) | (y > LAST_YEAR), f"year outside {FIRST_YEAR}-{LAST_YEAR}")
    vals = np.asarray(series[y - FIRST_YEAR])
    missing = np.isnan(vals)
    if missing.any():
        first = int(np.broadcast_to(y, missing.shape)[missing].ravel()[0])
        raise ValueError(f"{name}: no value for year {first}")
    return vals
