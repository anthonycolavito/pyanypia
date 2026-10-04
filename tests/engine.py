"""Runs test cases through the archived engine (anypia_engine)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import anypia_engine as eng
from anypia_engine.params import present_law

from tests.cases import Case, adjusted_birth_index

QC50 = 50.0


def qc_lumps(earn: dict[int, float]) -> int:
    """Pre-1978 QCs under the library's annual rule, for the engine's summary field."""
    return sum(min(4, math.floor(v / QC50)) for y, v in earn.items() if 1951 <= y <= 1977)


def month(index: int) -> eng.MonthYear:
    return eng.MonthYear(index // 12, index % 12 + 1)


def run_retired(case: Case, alt: int = 2, **worker_kw: Any) -> eng.Results:
    kb = adjusted_birth_index(case.birth)
    lump = qc_lumps(case.earnings)
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.OLD_AGE,
        earnings=case.earnings, entitlement=month(kb + case.claim_age),
        benefit_date=month(kb + case.benefit_age),
        qc_total_to_date=lump, qc_total_51_to_date=lump, **worker_kw,
    )
    return eng.compute(w, params=present_law(alt))
