"""Windfall elimination provision and government pension offset.

The Social Security Fairness Act repealed both for benefits payable after
December 2023. They are here for historical and counterfactual work:
`retired_worker` applies the WEP only when `Policy.wep_enabled` is set.
The WEP follows AnyPIA (WageIndGeneral::windfallCal). AnyPIA has no GPO,
so `gpo_offset` follows the statute (42 USC 402(k)(5)) and is checked
against hand arithmetic only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, out
from pyanypia.formula import pia
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit

WINDFALL_YEARS = 30  # years of substantial earnings that exempt a worker


def _windfall_first_pct(
    elig: np.ndarray, benefit_year: np.ndarray, yoc: np.ndarray, p0: float
) -> np.ndarray:
    """PercPia::setWindfallPerc: the first formula percentage under the WEP,
    phased in for 1986-89 eligibility and phased out from 20 years of
    substantial earnings."""
    rv = np.where(elig > 1989, p0 - 0.5, p0 - 0.10 * (elig - 1985).astype(float))
    annual = np.where(benefit_year >= 1989, 0.05, 0.10)
    floor_pct = p0 - annual * (WINDFALL_YEARS - yoc).astype(float)
    rv = np.where(floor_pct > rv, floor_pct, rv)
    rv = np.where(rv < 0.0, 0.0, rv)
    return np.asarray(np.where((elig < 1985) | (yoc >= WINDFALL_YEARS), p0, rv))


def wep_pia(
    aime: ArrayLike, elig_year: ArrayLike, years_of_coverage: ArrayLike, pension: ArrayLike, *,
    benefit_year: ArrayLike, policy: Policy = CURRENT_LAW,
) -> Any:
    """PIA at eligibility after the windfall elimination provision: the
    higher of the PIA with a reduced first percentage and the regular PIA
    less half the monthly noncovered pension. Count `years_of_coverage`
    with `years_of_coverage(..., kind="wep")`."""
    a, e, yoc, pen, by = np.broadcast_arrays(
        as_float("aime", aime), as_int("elig_year", elig_year),
        as_int("years_of_coverage", years_of_coverage), as_float("pension", pension),
        as_int("benefit_year", benefit_year))
    first_pct = _windfall_first_pct(e, by, yoc, policy.pia_pct[0])
    pct = np.stack([first_pct] + [np.full(first_pct.shape, p) for p in policy.pia_pct[1:]],
                   axis=-1)
    regular = np.asarray(pia(a, e, policy=policy))
    reduced = np.asarray(pia(a, e, policy=policy, pct=pct))
    floor_pia = regular - round_benefit(0.5 * pen, e - 1)
    wep = np.where(reduced > floor_pia, reduced, floor_pia)
    applies = (e > 1985) & (pen > 0.0) & (yoc < WINDFALL_YEARS)
    return out(np.where(applies, wep, regular))


def gpo_offset(
    benefit: ArrayLike, pension: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> Any:
    """A spouse's or widow(er)'s benefit after the government pension offset:
    reduced by two-thirds of the monthly noncovered government pension
    (`policy.gpo_fraction`), not below zero, in whole dollars."""
    b, p = np.broadcast_arrays(as_float("benefit", benefit), as_float("pension", pension))
    return out(floor_dollar(np.maximum(b - policy.gpo_fraction * p, 0.0)))
