"""One-call benefit computations that chain the formula functions."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia import claiming, formula
from pyanypia import earnings as _earn
from pyanypia._arrays import as_earnings, as_int
from pyanypia.dates import adjusted_birth, cola_year, from_month_index, month_index
from pyanypia.minimum import special_minimum_pia
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit


@dataclass(frozen=True)
class Benefit:
    """Per-worker results: arrays for many workers, scalars for one."""

    elig_year: Any
    aime: Any
    pia_elig: Any  # wage-indexed PIA at eligibility, before COLAs
    pia: Any  # PIA at the benefit month (the higher of the methods)
    mfb: Any  # maximum family benefit at the benefit month
    nra: Any  # normal retirement age, months
    factor: Any  # reduction or delayed-credit factor (1.0 when none)
    benefit: Any  # monthly benefit payable, whole dollars
    method: Any  # "wage_indexed" or "special_minimum"
    insured: Any  # fully insured (retired) / insured for disability (disabled)

    def to_frame(self) -> Any:
        """The results as a pandas DataFrame, one row per worker."""
        import pandas as pd

        return pd.DataFrame({f.name: np.atleast_1d(getattr(self, f.name)) for f in fields(self)})


def _benefit(single: bool, **cols: np.ndarray) -> Benefit:
    if single:
        return Benefit(**{k: np.asarray(v).ravel()[0].item() for k, v in cols.items()})
    return Benefit(**cols)


def _quarter(month_idx: np.ndarray) -> np.ndarray:
    """Quarter index (4*year + 0..3) of a month index (12*year + month - 1)."""
    return np.asarray(month_idx // 3)


def _pick(arrays: list[np.ndarray], idx: np.ndarray) -> np.ndarray:
    """Per row, the element of arrays[idx[row]]."""
    return np.asarray(np.choose(idx, arrays))


def _rows(x: ArrayLike, name: str, n: int) -> np.ndarray:
    return np.broadcast_to(as_int(name, x), (n,))


def _special_minimum(
    m: np.ndarray, first: int, last_year: np.ndarray, ben_y: np.ndarray, ben_m: np.ndarray,
    policy: Policy,
) -> tuple[np.ndarray, np.ndarray]:
    yoc = np.asarray(_earn.years_of_coverage(m, first_year=first, last_year=last_year,
                                             policy=policy))
    pia, mfb = special_minimum_pia(yoc, ben_y, ben_m, policy=policy)
    return np.asarray(pia), np.asarray(mfb)


def _apply_wep(
    pia_elig: np.ndarray, *, aime: np.ndarray, elig: np.ndarray, m: np.ndarray, first: int,
    last_year: np.ndarray, ben_y: np.ndarray, pension: ArrayLike, policy: Policy,
) -> np.ndarray:
    """Windfall elimination, when the policy enables it."""
    pen = np.broadcast_to(np.asarray(pension, dtype=float), pia_elig.shape)
    if not policy.wep_enabled or not (pen > 0).any():
        return pia_elig
    from pyanypia.wep import wep_pia

    yoc = np.asarray(_earn.years_of_coverage(m, first_year=first, last_year=last_year,
                                             kind="wep", policy=policy))
    return np.asarray(wep_pia(aime, elig, yoc, pen, benefit_year=ben_y, policy=policy))


def retired_worker(
    earnings: Any, birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    first_year: int | None = None, birth_day: ArrayLike = 15,
    benefit_age: ArrayLike | None = None, noncovered_pension: ArrayLike = 0.0,
    policy: Policy = CURRENT_LAW,
) -> Benefit:
    """A retired worker's benefit for the month at `benefit_age` (default:
    the entitlement month, `claim_age`).

    Ages are months from the adjusted birth month (`adjusted_birth`), so a
    worker born 15 March 1964 is 744 months old in March 2026. Earnings in
    and after the benefit year are ignored. The higher of the wage-indexed
    and special-minimum PIAs is used; delayed credits never apply to a
    special minimum. `noncovered_pension` matters only when
    `policy.wep_enabled`.

    A worker who is not fully insured is entitled to nothing; `insured`
    flags that, and the amounts are what AnyPIA reports regardless (with
    no delayed credits, which start only once fully insured).
    """
    m, first, single = as_earnings(earnings, first_year)
    n = m.shape[0]
    by, bm, bd = (_rows(birth_year, "birth_year", n), _rows(birth_month, "birth_month", n),
                  _rows(birth_day, "birth_day", n))
    claim = _rows(claim_age, "claim_age", n)
    ben_age = claim if benefit_age is None else _rows(benefit_age, "benefit_age", n)
    ky, km = adjusted_birth(by, bm, bd)
    ben_y, ben_m = from_month_index(month_index(ky, km) + ben_age)
    last_year = ben_y - 1
    elig = ky + 62

    comp = np.asarray(_earn.computation_years(by, bm, elig, birth_day=bd))
    aime = np.asarray(_earn.aime(m, elig, comp, first_year=first, last_year=last_year,
                                 policy=policy))
    pia_elig = np.asarray(formula.pia(aime, elig, policy=policy))
    pia_elig = _apply_wep(pia_elig, aime=aime, elig=elig, m=m, first=first,
                          last_year=last_year, ben_y=ben_y, pension=noncovered_pension,
                          policy=policy)
    mfb_elig = np.asarray(formula.family_max(pia_elig, elig, policy=policy))
    wage_pia = np.asarray(formula.apply_colas(pia_elig, elig, ben_y, ben_m, policy=policy))
    wage_mfb = np.asarray(formula.apply_colas(mfb_elig, elig, ben_y, ben_m, policy=policy))
    sm_pia, sm_mfb = _special_minimum(m, first, last_year, ben_y, ben_m, policy)

    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    kb = month_index(ky, km)
    ent, ben = kb + claim, kb + ben_age
    qc = _earn._qcs(m, first, policy)
    no_freeze = np.full(n, _earn.NO_FREEZE)
    insured = _earn._fully_insured_at(m, qc, first, ky, _quarter(ent), no_freeze)
    # Delayed credits run from the first quarter, from the one NRA falls in,
    # in which the worker is fully insured (PiaCal::fullInsDateCal); never,
    # if that is not before the benefit month.
    fra_q = _quarter(kb + nra)
    credits_from = np.full(n, np.iinfo(np.int64).max // 2)
    for k in range(int(max((_quarter(ben) - fra_q).max(initial=0), 0)) + 1):
        q = fra_q + k
        start = 3 * q  # month index of the quarter's first month
        found = (credits_from > ben) & ((k == 0) | (start < ben))
        hit = found & _earn._fully_insured_at(m, qc, first, ky, q, no_freeze)
        credits_from = np.where(hit, start, credits_from)
    factor = np.asarray(claiming.benefit_factor(by, bm, claim, birth_day=bd,
                                                benefit_age=ben_age, policy=policy,
                                                _credits_from=credits_from))
    cy = cola_year(ben_y, ben_m)
    # PiaCal::setHighPia / setSupportPia / piaCal2: the higher PIA wins (ties
    # to the wage-indexed method). Delayed credits never apply to a special
    # minimum, so a worker past NRA gets the larger of the credited
    # wage-indexed benefit and the uncredited special minimum.
    sm_wins = sm_pia > wage_pia
    pia = np.where(sm_wins, sm_pia, wage_pia)
    mfb = np.where(sm_wins, sm_mfb, wage_mfb)
    support = sm_wins & (claim > nra)
    unrounded = np.where(support,
                         np.maximum(round_benefit(factor * wage_pia, cy), sm_pia),
                         round_benefit(factor * pia, cy))
    return _benefit(
        single, elig_year=elig, aime=aime, pia_elig=pia_elig, pia=pia, mfb=mfb, nra=nra,
        factor=np.broadcast_to(factor, (n,)), benefit=floor_dollar(unrounded),
        method=np.where(sm_wins, "special_minimum", "wage_indexed"),
        insured=insured)


def disabled_worker(
    earnings: Any, birth_year: ArrayLike, birth_month: ArrayLike, onset_year: ArrayLike,
    onset_month: ArrayLike, *, first_year: int | None = None, birth_day: ArrayLike = 15,
    onset_day: ArrayLike = 15, entitlement: tuple[ArrayLike, ArrayLike] | None = None,
    benefit: tuple[ArrayLike, ArrayLike] | None = None, childcare: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> Benefit:
    """A disabled worker's benefit, with no prior retirement benefit.

    `entitlement` and `benefit` are (year, month) pairs. Entitlement defaults
    to the end of the five-month waiting period, which starts with the first
    full month of disability; the benefit month defaults to entitlement.
    Earnings after the onset year are ignored (they fall in the disability
    freeze). `childcare` flags years with a child under 3 in care, shaped
    like the earnings, for the child-care dropout years.

    `insured` is disability insured status (see `disability_insured`); a
    worker who is not insured is entitled to nothing, but the amounts are
    what AnyPIA reports regardless.

    Three computations compete, as in AnyPIA, and the highest PIA wins: the
    ordinary one; the child-care dropout one; and the "non-freeze" one, which
    takes the waiting period's first year as the eligibility year and counts
    every year's earnings through the year before the benefit month. The
    last applies only if the worker is also insured as of the waiting period
    without the disability freeze.
    """
    from pyanypia import disability
    from pyanypia._arrays import check

    m, first, single = as_earnings(earnings, first_year)
    n = m.shape[0]
    by, bm, bd = (_rows(birth_year, "birth_year", n), _rows(birth_month, "birth_month", n),
                  _rows(birth_day, "birth_day", n))
    oy, om, od = (_rows(onset_year, "onset_year", n), _rows(onset_month, "onset_month", n),
                  _rows(onset_day, "onset_day", n))
    if entitlement is None:
        waiting = month_index(oy, om) + np.where(od == 1, 0, 1)
        ey, em = from_month_index(waiting + 5)
    else:
        ey = _rows(entitlement[0], "entitlement_year", n)
        em = _rows(entitlement[1], "entitlement_month", n)
        waiting = month_index(ey, em) - 5
    if benefit is None:
        ben_y, ben_m = ey, em
    else:
        ben_y, ben_m = _rows(benefit[0], "benefit_year", n), _rows(benefit[1], "benefit_month", n)
    check("entitlement", month_index(ey, em) < month_index(1980, 7), "before July 1980")
    check("benefit", month_index(ben_y, ben_m) < month_index(ey, em), "before entitlement")
    ky, km = adjusted_birth(by, bm, bd)
    through = ben_y - 1

    def wage_indexed(elig: np.ndarray, last: np.ndarray) -> tuple[np.ndarray, ...]:
        comp = np.asarray(_earn.computation_years(by, bm, elig, birth_day=bd, disabled=True))
        aime = np.asarray(_earn.aime(m, elig, comp, first_year=first, last_year=last,
                                     policy=policy))
        return comp, aime, np.asarray(formula.pia(aime, elig, policy=policy))

    # the ordinary computation: earnings after onset fall in the freeze
    elig = np.minimum(ky + 62, oy)
    jan1 = (om == 1) & (od == 1)
    last_year = np.minimum(through, np.where(jan1, oy - 1, oy))
    comp, aime, pia_elig = wage_indexed(elig, last_year)
    # (eligibility year, aime, pia at eligibility) per method, in AnyPIA's order
    methods = [(elig, aime, pia_elig)]
    if childcare is not None:
        elapsed = _earn.elapsed_years(by, bm, elig, birth_day=bd)
        cc_aime = np.asarray(disability.childcare_aime(
            m, elig, comp, elapsed - comp, childcare, first_year=first, last_year=last_year,
            through_year=through, policy=policy))
        methods.append((elig, cc_aime, np.asarray(formula.pia(cc_aime, elig, policy=policy))))
    elig_nf = np.minimum(ky + 62, waiting // 12)
    _, aime_nf, pia_nf = wage_indexed(elig_nf, through)
    # insured without the freeze, as of the waiting period (disInsNonFreezeCal);
    # otherwise the computation does not apply (a zero PIA never wins)
    qc = _earn._qcs(m, first, policy)
    age21 = _earn._age21_quarter(ky, km)
    wait_q, ent_q = _quarter(waiting), _quarter(month_index(ey, em))
    nf_ok, d1 = _earn._twenty_of_forty(qc, first, wait_q, age21, special=False)
    nf_young, _ = _earn._twenty_of_forty(qc, first, wait_q, age21, special=True)
    nf_ok = (nf_ok | ((d1 < age21) & nf_young)) & _earn._fully_insured_at(
        m, qc, first, ky, ent_q, waiting // 12)
    methods.append((elig_nf, np.where(nf_ok, aime_nf, 0.0), np.where(nf_ok, pia_nf, 0.0)))
    insured = _earn._disability_insured_at(
        m, qc, first, ky, km, _quarter(month_index(oy, om)), wait_q, ent_q, oy)

    pias = [np.asarray(formula.apply_colas(p, e, ben_y, ben_m, policy=policy))
            for e, _, p in methods]
    yoc = np.asarray(_earn.years_of_coverage(m, first_year=first, last_year=through,
                                             policy=policy))
    sm_pia = np.asarray(special_minimum_pia(yoc, ben_y, ben_m, policy=policy)[0])
    # the highest PIA wins, ties to the earlier method; the special minimum
    # ranks after the ordinary computation and before the others
    high = pias[0]
    winner = np.zeros(n, dtype=np.int64)
    sm_wins = sm_pia > high
    high = np.where(sm_wins, sm_pia, high)
    for k in range(1, len(methods)):
        better = pias[k] > high
        high = np.where(better, pias[k], high)
        winner = np.where(better, k, winner)
        sm_wins = sm_wins & ~better
    # PiaCal::piaCal1: each method's DI maximum, never below the highest PIA;
    # a special-minimum winner takes the one of the method with the highest AIME
    mfbs = [np.maximum(np.asarray(formula.apply_colas(
        disability.di_family_max(p, a, e, policy=policy), e, ben_y, ben_m, policy=policy)),
        high) for e, a, p in methods]
    top_aime, top = methods[0][1], np.zeros(n, dtype=np.int64)
    for k in range(1, len(methods)):
        higher = methods[k][1] > top_aime
        top_aime = np.where(higher, methods[k][1], top_aime)
        top = np.where(higher, k, top)
    mfb = np.where(sm_wins, _pick(mfbs, top), _pick(mfbs, winner))
    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    unrounded = round_benefit(1.0 * high, cola_year(ben_y, ben_m))
    return _benefit(
        single, elig_year=_pick([e for e, _, _ in methods], winner),
        aime=_pick([a for _, a, _ in methods], winner),
        pia_elig=_pick([p for _, _, p in methods], winner), pia=high, mfb=mfb, nra=nra,
        factor=np.ones(n), benefit=floor_dollar(unrounded),
        method=np.where(sm_wins, "special_minimum", "wage_indexed"),
        insured=insured)
