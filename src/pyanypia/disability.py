"""Disability-specific pieces: the 1980-amendments family maximum and the
child-care dropout years (PiaMethod::diMax, ChildCareCalc)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_earnings, as_float, as_int, out
from pyanypia.earnings import Earnings, _capped, _indexed, _window, select_top
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import round_benefit

MAX_DROPOUT_YEARS = 3  # ordinary and child-care dropout years together


def di_family_max(
    pia_elig: ArrayLike, aime: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> Any:
    """Disability family maximum at eligibility: 85% of the AIME, but not
    less than the PIA nor more than 150% of it. Carry it forward with
    `apply_colas`; it is never less than the PIA payable."""
    p, a, e = np.broadcast_arrays(as_float("pia_elig", pia_elig), as_float("aime", aime),
                                  as_int("elig_year", elig_year))
    year = e - 1
    mfb85 = round_benefit(0.85 * a, year)
    mfb150 = round_benefit(1.5 * p, year)
    return out(np.where(mfb85 > mfb150, mfb150, np.where(mfb85 < p, p, mfb85)))


def childcare_aime(
    earnings: Earnings, elig_year: ArrayLike, comp_years: ArrayLike,
    ordinary_dropout: ArrayLike, childcare: ArrayLike, *, first_year: int | None = None,
    last_year: ArrayLike | None = None, through_year: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """AIME with extra dropout years for years with a child under 3 in care
    and no earnings, up to three dropout years in all
    (ChildCareCalc::childCareDropoutCal).

    `childcare` is a boolean array shaped like the earnings. Earnings after
    `last_year` are ignored (for a disabled worker, the years after onset),
    while the dropout candidates run through `through_year` (the year before
    the benefit month; default `last_year`).
    """
    m, first, single = as_earnings(earnings, first_year)
    rows, width = m.shape
    elig = np.broadcast_to(as_int("elig_year", elig_year), (rows,))
    n = np.broadcast_to(as_int("comp_years", comp_years), (rows,))
    drop0 = np.broadcast_to(as_int("ordinary_dropout", ordinary_dropout), (rows,))
    cc = np.broadcast_to(np.asarray(childcare, dtype=bool).reshape(-1, width), m.shape)
    years = np.arange(first, first + width)
    last = None if last_year is None else np.broadcast_to(as_int("last_year", last_year), (rows,))
    if through_year is not None:
        through = np.broadcast_to(as_int("through_year", through_year), (rows,))
    else:
        through = np.full(rows, years[-1]) if last is None else last
    in_range = (years[None, :] >= max(first, 1951)) & (years[None, :] <= through[:, None])
    x = _indexed(_window(m, first, last), first, elig, policy)
    # years outside the computation range can be neither chosen nor dropped
    sel = (select_top(np.where(in_range, x, -1.0), n) & in_range).astype(np.int8)
    empty = (_capped(m, first, policy) <= 0.01) & in_range
    drop_max = np.where(drop0 < MAX_DROPOUT_YEARS,
                        np.minimum(MAX_DROPOUT_YEARS - drop0, n - 2), 0)
    drops = np.zeros(rows, dtype=np.int64)
    for i in np.flatnonzero(drop_max > 0):
        row = sel[i]  # 1 chosen, 0 not, -1 dropped
        for j in np.flatnonzero((row == 1) & cc[i] & empty[i]):
            row[j] = -1
            drops[i] += 1
            if drops[i] >= drop_max[i]:
                break
        if drops[i] < drop_max[i]:
            # a chosen empty year without a child in care can be swapped for
            # an unchosen empty year with one, freeing another dropout
            out1 = np.flatnonzero((row == 1) & ~cc[i] & empty[i])
            in2 = np.flatnonzero((row == 0) & cc[i] & empty[i])
            for k in range(min(len(out1), len(in2), int(drop_max[i] - drops[i]))):
                row[out1[k]] = 0
                row[in2[k]] = -1
                drops[i] += 1
    total = np.zeros(rows)
    for j in range(width):
        total = total + np.where(sel[:, j] == 1, x[:, j], 0.0)
    result = np.floor(total / ((n - drops).astype(float) * 12.0))
    return out(result[0]) if single else result
