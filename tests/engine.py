"""Runs test cases through the archived engine (anypia_engine)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import anypia_engine as eng
from anypia_engine.params import present_law

from tests.cases import Case, adjusted_birth_index

QC50 = 50.0


def early_qcs(earn: dict[int, float]) -> dict[int, int]:
    """Pre-1978 QCs under the library's annual rule. The engine computes QCs
    from earnings only from 1978; given these year by year it also counts
    them inside quarter windows (a summary lump it would not)."""
    return {y: min(4, math.floor(v / QC50)) for y, v in earn.items() if 1951 <= y <= 1977}


def month(index: int) -> eng.MonthYear:
    return eng.MonthYear(index // 12, index % 12 + 1)


def run_retired(case: Case, alt: int = 2, **worker_kw: Any) -> eng.Results:
    kb = adjusted_birth_index(case.birth)
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.OLD_AGE,
        earnings=case.earnings, entitlement=month(kb + case.claim_age),
        benefit_date=month(kb + case.benefit_age),
        qcs_by_year=early_qcs(case.earnings), **worker_kw,
    )
    return eng.compute(w, params=present_law(alt))


def run_disabled(case: Case, alt: int = 2) -> eng.Results:
    ex = case.extra
    oy, om, od = ex["onset"]  # type: ignore[misc]
    ent = month(ex["ent"])  # type: ignore[arg-type]
    w = eng.Worker(
        dob=date(*case.birth), sex=eng.Sex.MALE, benefit_type=eng.BenefitType.DISABILITY,
        earnings=case.earnings, entitlement=ent, benefit_date=month(ex["ben"]),  # type: ignore[arg-type]
        disability_periods=(eng.DisabilityPeriod(
            onset=date(oy, om, od), first_entitlement=ent,
            waiting_period_start=month(ex["waiting"])),),  # type: ignore[arg-type]
        childcare_years=ex.get("childcare", frozenset()),  # type: ignore[arg-type]
        qcs_by_year=early_qcs(case.earnings),
    )
    return eng.compute(w, params=present_law(alt))
