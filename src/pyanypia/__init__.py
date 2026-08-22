"""pyanypia: pure-Python port of SSA's AnyPIA Detailed Calculator (2026 TR)."""

from __future__ import annotations

from pyanypia.dates import Age, MonthYear
from pyanypia.params import Params, present_law
from pyanypia.results import MethodResult, Results, results_from_context
from pyanypia.worker import (
    BenefitType,
    DisabilityPeriod,
    FamilyMember,
    Sex,
    Worker,
)

__version__ = "0.1.0.dev0"

__all__ = [
    "Age",
    "BenefitType",
    "DisabilityPeriod",
    "FamilyMember",
    "MethodResult",
    "MonthYear",
    "Params",
    "Results",
    "Sex",
    "Worker",
    "compute",
    "present_law",
]


def compute(
    worker: Worker,
    *,
    params: Params | None = None,
    alt: int = 2,
) -> Results:
    """Computes a worker's benefit under present law.

    ``params`` defaults to present law under Trustees Report alternative
    ``alt`` (2 = intermediate).
    """
    from pyanypia.engine.compute import calculate

    if params is None:
        params = present_law(alt)
    ctx = calculate(worker, params)
    return results_from_context(ctx)
