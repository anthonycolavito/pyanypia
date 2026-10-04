"""Seeded random workers for differential sweeps against anypia_engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from pyanypia import CURRENT_LAW
from pyanypia._years import FIRST_YEAR

AWI, TAXMAX, YOC = CURRENT_LAW.awi, CURRENT_LAW.taxmax, CURRENT_LAW.yoc_specmin
KINDS = ("steady", "max", "low", "gappy", "short", "minimum")


@dataclass
class Case:
    birth: tuple[int, int, int]
    earnings: dict[int, float]
    claim_age: int = 0  # months from adjusted birth to entitlement
    benefit_age: int = 0  # months from adjusted birth to the benefit month
    extra: dict[str, object] = field(default_factory=dict)


def _cents(x: float) -> float:
    return math.floor(x * 100.0 + 0.5) / 100.0


def adjusted_birth_index(birth: tuple[int, int, int]) -> int:
    """Month index (12*year + month - 1) of the day before birth."""
    y, m, d = birth
    idx = 12 * y + m - 1
    return idx - 1 if d == 1 else idx


def career(rng: np.random.Generator, birth_year: int, last_year: int) -> dict[int, float]:
    """{year: earnings} from the first working year through last_year,
    zero years included, so the engine sees the same span."""
    kind = str(rng.choice(KINDS))
    start = max(birth_year + 22 + int(rng.integers(0, 6)), 1951)
    work_end = last_year
    if kind == "short":
        work_end = start + int(rng.integers(6, 16))
    rel = {"steady": rng.uniform(0.3, 2.5), "max": 3.0, "low": rng.uniform(0.08, 0.35),
           "gappy": rng.uniform(0.3, 2.0), "short": rng.uniform(0.5, 1.5),
           "minimum": 0.0}[kind]
    out: dict[int, float] = {}
    for y in range(start, max(last_year, start) + 1):
        if kind == "max":
            wage = 1.2 * TAXMAX[y - FIRST_YEAR]
        elif kind == "minimum":  # just over a special-minimum year of coverage
            wage = YOC[y - FIRST_YEAR] * rng.uniform(1.0, 1.25)
        else:
            wage = rel * AWI[y - FIRST_YEAR] * rng.uniform(0.85, 1.15)
        zero = (kind == "gappy" and rng.random() < 0.3) or y > work_end or y > last_year
        out[y] = 0.0 if zero else _cents(wage)
    return out


def retired_cases(rng: np.random.Generator, n: int) -> list[Case]:
    cases = []
    for _ in range(n):
        birth = (int(rng.integers(1925, 2001)), int(rng.integers(1, 13)),
                 int(rng.choice([1, 2, 15, 28])))
        earliest = 744 if birth[2] == 2 else 745
        claim = int(rng.integers(earliest, 845))
        benefit = claim + int(rng.choice([0, 0, 7, 12, 30]))
        ben_year = (adjusted_birth_index(birth) + benefit) // 12
        cases.append(Case(birth, career(rng, birth[0], ben_year - 1), claim, benefit))
    return cases


def as_matrix(cases: list[Case]) -> tuple[np.ndarray, int]:
    first = min(min(c.earnings) for c in cases)
    last = max(max(c.earnings) for c in cases)
    m = np.zeros((len(cases), last - first + 1))
    for i, c in enumerate(cases):
        for y, v in c.earnings.items():
            m[i, y - first] = v
    return m, first


def column(cases: list[Case], f) -> np.ndarray:  # type: ignore[no-untyped-def]
    return np.array([f(c) for c in cases])


def disabled_cases(
    rng: np.random.Generator, n: int, childcare: bool = False
) -> list[Case]:
    cases: list[Case] = []
    while len(cases) < n:
        by, bm = int(rng.integers(1935, 2000)), int(rng.integers(1, 13))
        oy = by + int(rng.integers(24, 61))
        if not 1985 <= oy <= 2060:
            continue
        om, od = int(rng.integers(1, 13)), int(rng.choice([1, 5, 15, 28]))
        waiting = 12 * oy + om - 1 + (0 if od == 1 else 1)
        ent = waiting + 5
        if ent >= 12 * (by + 62) + bm - 1:  # past 62: keep to pure disability cases
            continue
        ben = ent + int(rng.choice([0, 0, 12]))
        earn = career(rng, by, oy)
        extra: dict[str, object] = {"onset": (oy, om, od), "waiting": waiting, "ent": ent,
                                    "ben": ben}
        if childcare:
            yrs = [y for y in earn if rng.random() < 0.3]
            for y in yrs:
                earn[y] = 0.0
            extra["childcare"] = frozenset(yrs)
        cases.append(Case((by, bm, 15), earn, extra=extra))
    return cases


def life_family_cases(rng: np.random.Generator, n: int) -> list[Case]:
    """Retired workers with an aged spouse, or a young spouse and children.
    `extra["family"]` holds (bic, birth, entitlement month index)."""
    cases = []
    for _ in range(n):
        by = int(rng.integers(1930, 1996))
        birth = (by, 3, 15)
        kb = adjusted_birth_index(birth)
        claim = int(rng.integers(745, 841))
        w_ent = kb + claim
        members: list[tuple[str, tuple[int, int, int], int]] = []
        if rng.random() < 0.5:
            sbirth = (by + int(rng.integers(-4, 6)), 7, int(rng.choice([2, 20])))
            s_claim = int(rng.integers(744 if sbirth[2] == 2 else 745, 830))
            members.append(("B ", sbirth, max(adjusted_birth_index(sbirth) + s_claim, w_ent)))
        else:
            cby = w_ent // 12 - int(rng.integers(3, 16))
            if rng.random() < 0.6:
                members.append(("B2", (by + 15, 1, 15), w_ent))
            members.append(("C1", (cby, 4, 10), w_ent))
            if rng.random() < 0.5:
                members.append(("C2", (cby + 2, 9, 9), w_ent))
        ben = max(e for _, _, e in members) + int(rng.choice([0, 12]))
        cases.append(Case(birth, career(rng, by, ben // 12 - 1), claim, ben - kb,
                          extra={"family": members}))
    return cases


def survivor_cases(rng: np.random.Generator, n: int) -> list[Case]:
    cases: list[Case] = []
    while len(cases) < n:
        by = int(rng.integers(1930, 1996))
        dy = by + int(rng.integers(30, 80))
        if not 1986 <= dy <= 2070:
            continue
        death = (dy, int(rng.integers(1, 13)), 20)
        death_idx = 12 * dy + death[1] - 1
        wbirth = (by + int(rng.integers(-3, 6)), 6, 10)
        wkb = adjusted_birth_index(wbirth)
        kind = str(rng.choice(["widow", "disabled_widow", "young_family", "child"]))
        members: list[tuple[str, tuple[int, int, int], int]] = []
        if kind == "widow":
            members.append(("D ", wbirth, max(wkb + int(rng.integers(720, 830)), death_idx)))
        elif kind == "disabled_widow":
            ent = max(wkb + int(rng.integers(600, 716)), death_idx)
            if ent - wkb >= 720:
                continue
            members.append(("W ", wbirth, ent))
        else:
            cby = dy - int(rng.integers(2, 16))
            if kind == "young_family":
                members.append(("E ", (by + 3, 2, 25), death_idx))
                members.append(("C2", (cby - 2, 9, 9), death_idx))
            members.append(("C1", (cby, 4, 10), death_idx))
        ben = max(e for _, _, e in members) + int(rng.choice([0, 12]))
        if ben // 12 > 2105:
            continue
        cases.append(Case((by, 3, 15), career(rng, by, dy),
                          extra={"family": members, "death": death, "ben": ben}))
    return cases
