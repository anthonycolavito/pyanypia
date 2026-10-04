"""Benefits for spouses, children and survivors under the family maximum
(PiaCal::ardriAuxCal, applyMfb, piaCal3).

Not covered: divorced spouses, who are paid outside the maximum.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check
from pyanypia._years import at
from pyanypia.claiming import earliest_claim_age, spouse_reduction_factor
from pyanypia.dates import adjusted_birth, cola_year
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import floor_dollar, round_benefit

#: benefit rate as a share of the worker's PIA
LIFE_RATES = {"spouse": 0.5, "spouse_with_child": 0.5, "child": 0.5}
SURVIVOR_RATES = {"child": 0.75, "parent_with_child": 0.75, "widow": 1.0,
                  "disabled_widow": 1.0}
REDUCIBLE = frozenset({"spouse", "widow", "disabled_widow"})
DISABLED_WIDOW_FACTOR = 0.715
WIDOW_MAX_REDUCTION = 0.285


@dataclass(frozen=True)
class Auxiliary:
    """One spouse, child or survivor; every field but `kind` may be an array
    over the n families.

    kind: "spouse" (aged spouse), "spouse_with_child" (caring for the
    worker's child, never reduced), "child", and for survivors "widow",
    "disabled_widow" and "parent_with_child". `claim_age` is months from the
    beneficiary's adjusted birth month to entitlement; it matters only for
    the reduced kinds. `present=False` leaves a family without this member.
    `guarantee_pia` is a widow(er)'s re-indexed guarantee PIA at the benefit
    month (`widow_guarantee_pia`); the higher of it and the worker's PIA is
    the base of their benefit.
    """

    kind: str
    birth_year: ArrayLike = 1960
    birth_month: ArrayLike = 1
    claim_age: ArrayLike = 0
    birth_day: ArrayLike = 15
    present: ArrayLike = True
    guarantee_pia: ArrayLike | None = None


@dataclass(frozen=True)
class FamilyBenefits:
    """Each field has shape (k, n): one row per auxiliary, in the order given."""

    full: Any  # rate x PIA, before the family maximum
    after_max: Any  # after the family maximum
    reduction_factor: Any  # age reduction (1.0 when none)
    benefit: Any  # payable, whole dollars


def _reduction(aux: Auxiliary, shape: tuple[int, ...], policy: Policy) -> np.ndarray:
    claim = np.broadcast_to(as_int("claim_age", aux.claim_age), shape)
    present = np.broadcast_to(np.asarray(aux.present, dtype=bool), shape)
    if aux.kind not in REDUCIBLE:
        return np.ones(shape)
    if aux.kind == "disabled_widow":
        check("claim_age", present & ((claim < 600) | (claim >= 720)),
              "a disabled widow(er) claims at 50-59")
        return np.full(shape, DISABLED_WIDOW_FACTOR)
    ky, _ = adjusted_birth(aux.birth_year, aux.birth_month, aux.birth_day)
    ky = np.broadcast_to(ky, shape)
    if aux.kind == "spouse":
        earliest = np.broadcast_to(np.asarray(earliest_claim_age(aux.birth_day)), shape)
        check("claim_age", present & (claim < earliest),
              "a spouse claims before the earliest retirement age")
        nra = at(policy.nra, ky + 62, "nra").astype(np.int64)
        return spouse_reduction_factor(np.maximum(nra - claim, 0), policy=policy)
    check("claim_age", present & (claim < 720), "a widow(er) claims before 60")
    # a widow(er)'s NRA is the worker's schedule shifted two years
    nra = at(policy.nra, ky + 60, "nra").astype(np.int64)
    months = np.maximum(nra - claim, 0).astype(float)
    return np.asarray(1.0 - (months / (nra - 720).astype(float)) * WIDOW_MAX_REDUCTION)


def family_benefits(
    worker_pia: ArrayLike, worker_mfb: ArrayLike, auxiliaries: Sequence[Auxiliary], *,
    benefit_year: ArrayLike, benefit_month: ArrayLike = 12, survivor: bool = False,
    policy: Policy = CURRENT_LAW,
) -> FamilyBenefits:
    """Benefits for a worker's family in a benefit month, from the worker's
    PIA and family maximum at that month (`retired_worker`, `disabled_worker`
    or, with `survivor=True`, `deceased_worker`).

    Each member's full benefit is a share of the PIA; if together they exceed
    what the family maximum leaves (all of it for survivors, the excess over
    the worker's PIA otherwise), all are cut in proportion; then spouses and
    widow(er)s are reduced for age.
    """
    rates = SURVIVOR_RATES if survivor else LIFE_RATES
    pia, mfb, by, bm = np.broadcast_arrays(
        as_float("worker_pia", worker_pia), as_float("worker_mfb", worker_mfb),
        as_int("benefit_year", benefit_year), as_int("benefit_month", benefit_month))
    shape = pia.shape
    cy = cola_year(by, bm)
    fulls, factors = [], []
    for aux in auxiliaries:
        if aux.kind not in rates:
            raise ValueError(
                f"kind: {aux.kind!r} is not a {'survivor' if survivor else 'life'} "
                f"beneficiary; expected one of {sorted(rates)}")
        present = np.broadcast_to(np.asarray(aux.present, dtype=bool), shape)
        base = pia
        if aux.guarantee_pia is not None:
            guarantee = np.broadcast_to(as_float("guarantee_pia", aux.guarantee_pia), shape)
            base = np.where(guarantee > pia, guarantee, pia)
        fulls.append(np.where(present, round_benefit(base * rates[aux.kind], cy), 0.0))
        factors.append(_reduction(aux, shape, policy))
    total = np.zeros(shape)
    for f in fulls:
        total = total + f
    available = mfb if survivor else mfb - pia
    ratio = np.divide(available, total, out=np.ones(shape), where=total > 0.0)
    ratio = np.clip(ratio, 0.0, 1.0)
    after, paid = [], []
    for aux, full, arf in zip(auxiliaries, fulls, factors, strict=True):
        a = round_benefit(ratio * full, cy)
        reduced = round_benefit(arf * a, cy) if aux.kind in REDUCIBLE else a
        after.append(a)
        paid.append(floor_dollar(reduced))
    return FamilyBenefits(full=np.array(fulls), after_max=np.array(after),
                          reduction_factor=np.array(factors), benefit=np.array(paid))
