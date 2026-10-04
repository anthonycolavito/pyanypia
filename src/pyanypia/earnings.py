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


def _accumulate(qc: np.ndarray, first: int, q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """QCs earned from quarter q1 through q2 (quarter index 4*year + 0..3).
    A year's QCs count in any of its quarters, up to the quarters of it in the
    range (QcArray::accumulate)."""
    n, width = qc.shape
    rows = np.arange(n)
    cum = np.concatenate([np.zeros((n, 1), dtype=np.int64), np.cumsum(qc, axis=1)], axis=1)

    def year_qcs(y: np.ndarray) -> np.ndarray:
        j = y - first
        inside = (j >= 0) & (j < width)
        return np.where(inside, qc[rows, np.clip(j, 0, width - 1)], 0)

    def years_between(ya: np.ndarray, yb: np.ndarray) -> np.ndarray:
        ja, jb = np.clip(ya - first, 0, width), np.clip(yb - first + 1, 0, width)
        return np.where(jb > ja, cum[rows, jb] - cum[rows, ja], 0)

    y1, k1 = np.divmod(q1, 4)
    y2, k2 = np.divmod(q2, 4)
    spanning = (np.minimum(year_qcs(y1), 4 - k1) + years_between(y1 + 1, y2 - 1)
                + np.minimum(year_qcs(y2), k2 + 1))
    within = np.minimum(k2 - k1 + 1, year_qcs(y1))
    return np.asarray(np.where(q1 > q2, 0, np.where(y1 == y2, within, spanning)))


NO_FREEZE = 10_000  # a freeze start year later than any data


def _fully_insured_at(
    m: np.ndarray, qc: np.ndarray, first: int, kb_year: np.ndarray, through_q: np.ndarray,
    freeze_from: np.ndarray,
) -> np.ndarray:
    """PiaCal::fins1Cal's fully insured test as of quarter `through_q`: a QC
    for each year elapsed after 21 and before 62, less years of disability
    from `freeze_from`, at least 6 and at most 40."""
    lump = np.minimum((_pre1951_total(m, first) / 400.0).astype(np.int64), 56)
    total = lump + _accumulate(qc, first, np.full(through_q.shape, 4 * 1951), through_q)
    e2 = np.minimum(through_q // 4, kb_year + 61)
    e1 = np.maximum(kb_year + 21, 1950)
    frozen = np.where(freeze_from <= e2, e2 - np.maximum(freeze_from, e1 + 1) + 1, 0)
    return np.asarray(total >= np.minimum(40, np.maximum(6, e2 - e1 - frozen)))


def fully_insured(
    earnings: Earnings, birth_year: ArrayLike, birth_month: ArrayLike, *,
    through_year: ArrayLike, through_month: ArrayLike = 12, first_year: int | None = None,
    birth_day: ArrayLike = 15, policy: Policy = CURRENT_LAW,
) -> Any:
    """Whether the worker is fully insured in (through_year, through_month):
    a quarter of coverage for each year elapsed after 21 and before 62 (at
    least 6, at most 40), counting QCs through that month's quarter."""
    m, first, single = as_earnings(earnings, first_year)
    rows = m.shape[0]
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    q = 4 * _rows(through_year, "through_year", rows) + (
        _rows(through_month, "through_month", rows) - 1) // 3
    ok = _fully_insured_at(m, _qcs(m, first, policy), first, np.broadcast_to(ky, (rows,)), q,
                           np.full(rows, NO_FREEZE))
    return _result(ok, single)


def _age21_quarter(ky: np.ndarray, km: np.ndarray) -> np.ndarray:
    """The quarter after the one of the adjusted birth date, 21 years on."""
    return np.asarray(4 * (ky + 21) + (km - 1) // 3 + 1)


def _twenty_of_forty(
    qc: np.ndarray, first: int, d2: np.ndarray, age21: np.ndarray, special: bool
) -> tuple[np.ndarray, np.ndarray]:
    """(QCs in at least half the quarters of the window ending d2, window
    start). The window is 40 quarters; with `special`, a worker whose window
    reaches back before 21 uses the quarters since 21, at least 12
    (PiaData::qcDisReqCal, qcDiSpec)."""
    d1 = d2 - 39
    if special:
        d1 = np.where(d1 < age21, np.where(d2 - age21 < 11, d2 - 11, age21), d1)
    return np.asarray(_accumulate(qc, first, d1, d2) >= (d2 - d1 + 1) // 2), np.asarray(d1)


def _disability_insured_at(
    m: np.ndarray, qc: np.ndarray, first: int, ky: np.ndarray, km: np.ndarray,
    window_from: np.ndarray, window_to: np.ndarray, entitlement_q: np.ndarray,
    freeze_from: np.ndarray,
) -> np.ndarray:
    """PiaCal::disInsCal: fully insured at entitlement, and 20 QCs in a
    40-quarter window ending in some quarter from `window_to` back to
    `window_from` (the onset quarter); then the same with the special window
    for young workers."""
    age21 = _age21_quarter(ky, km)
    ok = np.zeros(m.shape[0], dtype=bool)
    trials = window_to - window_from
    for i in range(int(trials.max(initial=0)), -1, -1):
        hit, _ = _twenty_of_forty(qc, first, window_from + i, age21, special=False)
        ok |= (i <= trials) & hit
    young = ~ok & (window_from - 39 < age21)
    for i in range(int(trials.max(initial=0)) + 1):
        hit, _ = _twenty_of_forty(qc, first, window_from + i, age21, special=True)
        ok |= young & (i <= trials) & hit
    return np.asarray(ok & _fully_insured_at(m, qc, first, ky, entitlement_q, freeze_from))


def disability_insured(
    earnings: Earnings, birth_year: ArrayLike, birth_month: ArrayLike, onset_year: ArrayLike,
    onset_month: ArrayLike, *, first_year: int | None = None, birth_day: ArrayLike = 15,
    onset_day: ArrayLike = 15, entitlement: tuple[ArrayLike, ArrayLike] | None = None,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """Whether a worker disabled at onset is insured for disability benefits:
    fully insured, and 20 quarters of coverage in the 40 ending with onset
    (fewer for workers disabled before 31). `entitlement` is (year, month),
    defaulting to the end of the five-month waiting period."""
    m, first, single = as_earnings(earnings, first_year)
    rows = m.shape[0]
    oy, om = _rows(onset_year, "onset_year", rows), _rows(onset_month, "onset_month", rows)
    od = _rows(onset_day, "onset_day", rows)
    waiting = 12 * oy + om - 1 + np.where(od == 1, 0, 1)
    if entitlement is None:
        ent = waiting + 5
    else:
        ent = 12 * _rows(entitlement[0], "entitlement_year", rows) + _rows(
            entitlement[1], "entitlement_month", rows) - 1
        waiting = ent - 5
    ky, km = (np.broadcast_to(a, (rows,)) for a in adjusted_birth(birth_year, birth_month,
                                                                   birth_day))
    ok = _disability_insured_at(m, _qcs(m, first, policy), first, ky, km,
                                (12 * oy + om - 1) // 3, waiting // 3, ent // 3, oy)
    return _result(ok, single)


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
