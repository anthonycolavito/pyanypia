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
    insured: Any  # fully insured by the end of the year before the benefit month

    def to_frame(self) -> Any:
        """The results as a pandas DataFrame, one row per worker."""
        import pandas as pd

        return pd.DataFrame({f.name: np.atleast_1d(getattr(self, f.name)) for f in fields(self)})


def _benefit(single: bool, **cols: np.ndarray) -> Benefit:
    if single:
        return Benefit(**{k: np.asarray(v).ravel()[0].item() for k, v in cols.items()})
    return Benefit(**cols)


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

    factor = np.asarray(claiming.benefit_factor(by, bm, claim, birth_day=bd,
                                                benefit_age=ben_age, policy=policy))
    nra = np.asarray(claiming.normal_retirement_age(by, bm, birth_day=bd, policy=policy))
    insured = np.atleast_1d(_earn.fully_insured(m, by, bm, elig, through_year=last_year,
                                                first_year=first, birth_day=bd, policy=policy))
    # Delayed credits run from the later of NRA and the date fully insured
    # status is reached (PiaCal::monthsDriCal), so an uninsured worker earns none.
    factor = np.where(~insured & (claim >= nra), 1.0, factor)
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
