"""Earnings-side computations: capping, wage indexing, computation years,
AIME, and quarters and years of coverage (WageIndGeneral, PiaMethod, PiaCal).

Earnings are a `{year: amount}` dict or a 1-D array for one worker, or an
(n, Y) array for many, with column j holding year `first_year + j`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_earnings, as_int, check, out
from pyanypia._years import at
from pyanypia.dates import adjusted_birth
from pyanypia.policy import CURRENT_LAW, Policy

Earnings = Mapping[int, float] | ArrayLike


def _years(first: int, width: int) -> np.ndarray:
    return np.arange(first, first + width)


def _rows(x: ArrayLike, name: str, n: int) -> np.ndarray:
    return np.broadcast_to(as_int(name, x), (n,))


def _result(x: np.ndarray, single: bool) -> Any:
    return out(x[0]) if single else x


def _capped(m: np.ndarray, first: int, policy: Policy) -> np.ndarray:
    cap = at(policy.taxmax, _years(first, m.shape[1]), "taxmax")
    return np.asarray(np.minimum(m, cap[None, :]))


def _indexed(m: np.ndarray, first: int, elig: np.ndarray, policy: Policy) -> np.ndarray:
    """Capped earnings indexed to elig-2, nominal from elig-2 on, zero before 1951."""
    years = _years(first, m.shape[1])
    capped = _capped(m, first, policy)
    awi_idx = at(policy.awi, elig - 2, "awi")[:, None]
    awi_y = at(policy.awi, years, "awi")[None, :]
    indexed = np.floor(awi_idx * capped / awi_y * 100.0 + 0.5) / 100.0
    x = np.where(years[None, :] < (elig - 2)[:, None], indexed, capped)
    return np.asarray(np.where(years[None, :] >= 1951, x, 0.0))


def _window(m: np.ndarray, first: int, last: np.ndarray | None) -> np.ndarray:
    """Zeroes earnings after each row's last year."""
    if last is None:
        return m
    years = _years(first, m.shape[1])
    return np.asarray(np.where(years[None, :] <= last[:, None], m, 0.0))


def capped_earnings(
    earnings: Earnings, *, first_year: int | None = None, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    """Earnings limited to each year's taxable maximum."""
    m, first, single = as_earnings(earnings, first_year)
    capped = _capped(m, first, policy)
    return capped[0] if single else capped


def indexed_earnings(
    earnings: Earnings, elig_year: ArrayLike, *, first_year: int | None = None,
    policy: Policy = CURRENT_LAW,
) -> np.ndarray:
    """Capped earnings indexed to the average wage two years before
    eligibility; later years enter at face value, years before 1951 as zero."""
    m, first, single = as_earnings(earnings, first_year)
    x = _indexed(m, first, _rows(elig_year, "elig_year", m.shape[0]), policy)
    return x[0] if single else x


def select_top(x: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Mask of each row's `n` highest values. Equal values go to the later
    year, as sorting (value, year) pairs does in PiaMethod::orderEarnings."""
    order = np.argsort(x, axis=1, kind="stable")
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.broadcast_to(np.arange(x.shape[1]), x.shape), axis=1)
    return np.asarray(rank >= (x.shape[1] - n)[:, None])


def sum_by_year(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Row sums of the masked values, added in year order like the C++ loop.
    (np.sum's pairwise summation can differ in the last bit.)"""
    total = np.zeros(x.shape[0])
    for j in range(x.shape[1]):
        total = total + np.where(mask[:, j], x[:, j], 0.0)
    return total


def aime(
    earnings: Earnings, elig_year: ArrayLike, comp_years: ArrayLike, *,
    first_year: int | None = None, last_year: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """Average indexed monthly earnings over the `comp_years` highest years.

    Earnings are capped at the taxable maximum and indexed to the average
    wage two years before `elig_year`. Years after `last_year` (default: all)
    are ignored, as a benefit computed for a given month ignores later
    earnings. The result is truncated to the dollar.
    """
    m, first, single = as_earnings(earnings, first_year)
    rows = m.shape[0]
    elig = _rows(elig_year, "elig_year", rows)
    n = _rows(comp_years, "comp_years", rows)
    check("comp_years", n < 1, "must be at least 1")
    last = None if last_year is None else _rows(last_year, "last_year", rows)
    x = _indexed(_window(m, first, last), first, elig, policy)
    total = sum_by_year(x, select_top(x, n))
    return _result(np.floor(total / (n.astype(float) * 12.0)), single)


def elapsed_years(
    birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    birth_day: ArrayLike = 15, death_year: ArrayLike | None = None,
) -> np.ndarray:
    """Years after the year of attaining 21 (or after 1950) and before
    eligibility, or before death if earlier; at least 2 (PiaCal::nElapsedCal)."""
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e2 = as_int("elig_year", elig_year) - 1
    if death_year is not None:
        e2 = np.minimum(e2, as_int("death_year", death_year) - 1)
    e1 = np.maximum(ky + 21, 1950)
    return np.asarray(np.maximum(e2 - e1, 2))


def computation_years(
    birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    birth_day: ArrayLike = 15, disabled: ArrayLike = False,
    death_year: ArrayLike | None = None,
) -> Any:
    """Elapsed years less dropout years: 5, or for a disabled worker one per
    five elapsed years up to 5; never fewer than 2 (PiaCal::nCal)."""
    elapsed = elapsed_years(birth_year, birth_month, elig_year, birth_day=birth_day,
                            death_year=death_year)
    drop = np.where(np.asarray(disabled, dtype=bool), np.minimum(elapsed // 5, 5), 5)
    return out(np.maximum(elapsed - drop, 2))


def _qcs(m: np.ndarray, first: int, policy: Policy) -> np.ndarray:
    amt = at(policy.qc_amount, _years(first, m.shape[1]), "qc_amount")
    return np.asarray(np.minimum(4, np.floor(m / amt[None, :])), dtype=np.int64)


def quarters_of_coverage(
    earnings: Earnings, *, first_year: int | None = None, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    """Annual quarters of coverage, min(4, earnings // QC amount), on
    uncapped earnings. Before 1978 SSA counted calendar-quarter wages; this
    annual rule with the $50 amount is an approximation there."""
    m, first, single = as_earnings(earnings, first_year)
    q = _qcs(m, first, policy)
    return q[0] if single else q


def _pre1951_total(m: np.ndarray, first: int) -> np.ndarray:
    years = _years(first, m.shape[1])
    return np.asarray(np.minimum(np.where(years[None, :] < 1951, m, 0.0).sum(axis=1), 42000.0))


def fully_insured(
    earnings: Earnings, birth_year: ArrayLike, birth_month: ArrayLike, elig_year: ArrayLike, *,
    through_year: ArrayLike, first_year: int | None = None, birth_day: ArrayLike = 15,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """Whether the worker has a quarter of coverage for each elapsed year
    (at least 6, at most 40) by the end of `through_year`."""
    m, first, single = as_earnings(earnings, first_year)
    rows = m.shape[0]
    through = _rows(through_year, "through_year", rows)
    years = _years(first, m.shape[1])
    lump = np.minimum((_pre1951_total(m, first) / 400.0).astype(np.int64), 56)
    keep = (years[None, :] >= 1951) & (years[None, :] <= through[:, None])
    total = lump + np.where(keep, _qcs(m, first, policy), 0).sum(axis=1)
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e2 = np.minimum(through, as_int("elig_year", elig_year) - 1)
    e1 = np.maximum(ky + 21, 1950)
    required = np.minimum(40, np.maximum(6, e2 - e1))
    return _result(np.asarray(total >= required), single)


def years_of_coverage(
    earnings: Earnings, *, last_year: ArrayLike, first_year: int | None = None,
    kind: Literal["special_minimum", "wep"] = "special_minimum",
    policy: Policy = CURRENT_LAW,
) -> Any:
    """Years of coverage for the special minimum or the WEP, through
    `last_year`, on uncapped earnings (PiaMethod::specMinYearsCal). Earnings
    before 1951 count one year per $900, up to 14."""
    m, first, single = as_earnings(earnings, first_year)
    last = _rows(last_year, "last_year", m.shape[0])
    years = _years(first, m.shape[1])
    series = policy.yoc_specmin if kind == "special_minimum" else policy.yoc_wep
    pre_years = np.minimum(14, np.floor(_pre1951_total(m, first) / 900.0)).astype(np.int64)
    post = years >= 1951
    amt = np.full(years.shape, np.inf)
    amt[post] = at(series, years[post], "years_of_coverage")
    hit = (m > amt[None, :] - 0.009) & (years[None, :] <= last[:, None])
    return _result(pre_years + hit.sum(axis=1), single)
