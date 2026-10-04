"""The PIA and family-maximum formulas, and benefit increases (COLAs)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from pyanypia._arrays import as_float, as_int, check, out
from pyanypia._years import FIRST_YEAR, at
from pyanypia.dates import cola_year
from pyanypia.policy import CURRENT_LAW, Policy
from pyanypia.rounding import apply_cola, round_benefit

AWI_BASE_YEAR = 1977  # the 1979 bend points are defined against the 1977 AWI


def _index_bend(base: tuple[float, ...], elig: np.ndarray, policy: Policy) -> np.ndarray:
    temp = at(policy.awi, elig - 2, "awi") / policy.awi[AWI_BASE_YEAR - FIRST_YEAR]
    return np.stack([np.floor(b * temp + 0.5) for b in base], axis=-1)


def bend_points(elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    """PIA formula bend points for an eligibility year, shape (..., k)."""
    return _index_bend(policy.pia_bend_base, as_int("elig_year", elig_year), policy)


def family_max_bend_points(elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW) -> np.ndarray:
    """Family-maximum formula bend points for an eligibility year, shape (..., 3)."""
    return _index_bend(policy.mfb_bend_base, as_int("elig_year", elig_year), policy)


def _bracket_sum(x: np.ndarray, bp: np.ndarray, pct: tuple[Any, ...]) -> np.ndarray:
    """sum(pct[i] * portion[i]) accumulated left to right, as the C++ does."""
    k = bp.shape[-1]
    parts = [np.minimum(x, bp[..., 0])]
    for i in range(k - 1):
        parts.append(np.maximum(0.0, np.minimum(x - bp[..., i], bp[..., i + 1] - bp[..., i])))
    parts.append(np.maximum(x - bp[..., k - 1], 0.0))
    total = np.zeros(np.shape(parts[0]))
    for p, part in zip(pct, parts, strict=True):
        total = total + p * part
    return total


def pia(
    aime: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW,
    pct: tuple[float, ...] | ArrayLike | None = None,
) -> Any:
    """Primary insurance amount at eligibility, before COLAs. `pct` replaces
    the policy's formula percentages, either as a tuple or as a per-row
    (..., k+1) array (the WEP uses this)."""
    a = as_float("aime", aime)
    check("aime", a < 0, "negative")
    a, e = np.broadcast_arrays(a, as_int("elig_year", elig_year))
    bp = bend_points(e, policy=policy)
    percents = policy.pia_pct if pct is None else pct
    if isinstance(percents, tuple):
        total = _bracket_sum(a, bp, percents)
    else:
        arr = np.asarray(percents, dtype=float)
        total = _bracket_sum(a, bp, tuple(arr[..., i] for i in range(arr.shape[-1])))
    return out(round_benefit(total, e - 1))


def family_max(
    pia_elig: ArrayLike, elig_year: ArrayLike, *, policy: Policy = CURRENT_LAW
) -> Any:
    """Maximum family benefit at eligibility, before COLAs, for retirement
    and survivor cases. Disability uses `di_family_max`."""
    p, e = np.broadcast_arrays(as_float("pia_elig", pia_elig), as_int("elig_year", elig_year))
    bp = family_max_bend_points(e, policy=policy)
    return out(round_benefit(_bracket_sum(p, bp, policy.mfb_pct), e - 1))


def apply_colas(
    amount: ArrayLike, elig_year: ArrayLike, benefit_year: ArrayLike,
    benefit_month: ArrayLike = 12, *, policy: Policy = CURRENT_LAW,
) -> Any:
    """Carries a PIA or family maximum from eligibility to a benefit month,
    applying each benefit increase from the eligibility year on
    (PiaMethod::applyColas). The December 1999 increase is 0.1 point higher
    for benefits from July 2001, as the 2000 correction provided."""
    a, e, by, bm = np.broadcast_arrays(
        as_float("amount", amount), as_int("elig_year", elig_year),
        as_int("benefit_year", benefit_year), as_int("benefit_month", benefit_month))
    cy = cola_year(by, bm)
    from_jul2001 = (by > 2001) | ((by == 2001) & (bm >= 7))
    result = a.astype(float)
    if result.size == 0:
        return out(result)
    for y in range(int(e.min()), int(cy.max()) + 1):
        active = (e <= y) & (y <= cy)
        if not active.any():
            continue
        pct = at(policy.cola, y, "cola") + np.where((y == 1999) & from_jul2001, 0.1, 0.0)
        result = np.where(active, apply_cola(result, pct, y), result)
    return out(result)
