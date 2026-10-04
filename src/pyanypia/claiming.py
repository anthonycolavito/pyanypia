"""Retirement ages and the reduction or credit for claiming early or late
(PiaParams retirement-age functions and PiaCal::ardriCal).

Ages are whole months from the adjusted birth month (see
`dates.adjusted_birth`) to the month in question.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check, out
from pyanypia._years import at
from pyanypia.dates import adjusted_birth, cola_year, month_index
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit


def eligibility_year(
    birth_year: ArrayLike, birth_month: ArrayLike, *, birth_day: ArrayLike = 15,
    onset_year: ArrayLike | None = None, death_year: ArrayLike | None = None,
) -> Any:
    """Year of attaining 62, or of disability onset or death if earlier."""
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    e = ky + 62
    if death_year is not None:
        e = np.minimum(e, as_int("death_year", death_year))
    if onset_year is not None:
        e = np.minimum(e, as_int("onset_year", onset_year))
    return out(e)


def normal_retirement_age(
    birth_year: ArrayLike, birth_month: ArrayLike, *, birth_day: ArrayLike = 15,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """Normal (full) retirement age, in months."""
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    return out(at(policy.nra, ky + 62, "nra").astype(np.int64))


def earliest_claim_age(birth_day: ArrayLike = 15) -> Any:
    """Earliest retirement claim, in months from the adjusted birth month:
    62 and 1 month, except 62 for those born on the 2nd, who are 62 for the
    whole of their birthday month (PiaParams::earlyAgeOabCalPL). Someone born
    on the 1st is also 62 all month, but their adjusted birth month is the
    month before, so they too count 62 and 1 month from it."""
    bd = as_int("birth_day", birth_day)
    return out(np.where(bd == 2, 744, 745))


def early_reduction_factor(months: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    """Retired-worker reduction: 5/9 of 1% a month for 36 months, 5/12 after."""
    m = as_int("months", months).astype(float)
    n1 = float(policy.ar_months_first)
    first = 1.0 - m * policy.ar_rate_first
    later = 1.0 - n1 * policy.ar_rate_first - (m - n1) * policy.ar_rate_later
    return np.asarray(np.where(m <= n1, first, later))


def spouse_reduction_factor(months: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    """Spouse reduction: 25/36 of 1% a month for 36 months, 5/12 after."""
    m = as_int("months", months).astype(float)
    n1 = float(policy.ar_months_first)
    first = 1.0 - m * policy.spouse_ar_rate_first
    later = 1.0 - n1 * policy.spouse_ar_rate_first - (m - n1) * policy.ar_rate_later
    return np.asarray(np.where(m < 0, 0.0, np.where(m <= n1, first, later)))


def delayed_credit_factor(
    months: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> np.ndarray:
    m = as_int("months", months).astype(float)
    rate = at(policy.drc_rate_by_elig, as_int("elig_year", elig_year), "drc_rate")
    return np.asarray(1.0 + m * rate)


def adjustment_months(
    birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    birth_day: ArrayLike = 15, benefit_age: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> tuple[np.ndarray, np.ndarray]:
    """(months of early reduction, months of delayed credit) for a retired worker.

    Delayed credits earned in the year of entitlement are credited the
    following January (PiaParams::monthsDriCal), so a benefit paid in the
    entitlement year counts only the credits through the prior December,
    unless the worker has reached 70.
    """
    ky, km = adjusted_birth(birth_year, birth_month, birth_day)
    claim = as_int("claim_age", claim_age)
    ben_age = claim if benefit_age is None else as_int("benefit_age", benefit_age)
    ky, km, claim, ben_age, bd = np.broadcast_arrays(
        ky, km, claim, ben_age, as_int("birth_day", birth_day))
    check("claim_age", claim < np.asarray(earliest_claim_age(bd)),
          "before the earliest retirement age")
    check("benefit_age", ben_age < claim, "before claim_age")
    nra = at(policy.nra, ky + 62, "nra").astype(np.int64)
    kb = month_index(ky, km)
    ent, ben = kb + claim, kb + ben_age
    fra = kb + nra
    age70 = kb + 70 * 12
    jan_ent = 12 * (ent // 12)
    credited_to = np.where(
        age70 <= ent, age70,
        np.where((age70 <= ben) | (ben // 12 > ent // 12), ent, np.maximum(fra, jan_ent)))
    late = claim >= nra
    ar = np.where(late, 0, nra - claim)
    drc = np.where(late, np.maximum(credited_to - fra, 0), 0)
    return ar, drc


def benefit_factor(
    birth_year: ArrayLike, birth_month: ArrayLike, claim_age: ArrayLike, *,
    birth_day: ArrayLike = 15, benefit_age: ArrayLike | None = None,
    policy: Policy = CURRENT_LAW,
) -> Any:
    """The multiplier on the PIA for a retired worker claiming at `claim_age`,
    for the benefit paid at `benefit_age` (default: the claim month)."""
    ar, drc = adjustment_months(birth_year, birth_month, claim_age, birth_day=birth_day,
                                benefit_age=benefit_age, policy=policy)
    ky, _ = adjusted_birth(birth_year, birth_month, birth_day)
    elig = np.broadcast_to(ky + 62, ar.shape)
    f = np.where(ar > 0, early_reduction_factor(ar, policy=policy),
                 delayed_credit_factor(drc, elig, policy=policy))
    return out(f)


def monthly_benefit(
    pia: ArrayLike, factor: ArrayLike, benefit_year: ArrayLike, benefit_month: ArrayLike = 12
) -> Any:
    """factor x PIA, rounded down to the dime, then paid in whole dollars."""
    cy = cola_year(as_int("benefit_year", benefit_year), as_int("benefit_month", benefit_month))
    unrounded = round_benefit(as_float("factor", factor) * as_float("pia", pia), cy)
    return out(floor_dollar(unrounded))
