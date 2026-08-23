"""pyanypia: pure-Python port of SSA's AnyPIA Detailed Calculator (2026 TR)."""

from __future__ import annotations

from dataclasses import dataclass

from pyanypia.dates import Age, MonthYear
from pyanypia.engine.statement import (
    StatementEstimate,
    StatementResults,
    StatementType,
    calculate_statement,
)
from pyanypia.law import Law, Reform
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
    "Comparison",
    "DisabilityPeriod",
    "FamilyMember",
    "Law",
    "MethodResult",
    "MonthYear",
    "Params",
    "Reform",
    "Results",
    "Sex",
    "StatementEstimate",
    "StatementResults",
    "StatementType",
    "Worker",
    "calculate_statement",
    "compare",
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


@dataclass(frozen=True)
class Comparison:
    """One worker's benefit under present law and under a reform."""

    baseline: Results
    reformed: Results

    @property
    def pia_change(self) -> float:
        return self.reformed.pia - self.baseline.pia

    @property
    def benefit_change(self) -> float:
        return self.reformed.monthly_benefit - self.baseline.monthly_benefit

    @property
    def benefit_change_percent(self) -> float:
        base = self.baseline.monthly_benefit
        return 100.0 * self.benefit_change / base if base else 0.0

    def detail(self) -> str:
        return "\n".join([
            f"PIA      {self.baseline.pia:10.2f} -> "
            f"{self.reformed.pia:10.2f}  ({self.pia_change:+.2f})",
            f"benefit  {self.baseline.monthly_benefit:10.2f} -> "
            f"{self.reformed.monthly_benefit:10.2f}  "
            f"({self.benefit_change:+.2f}, "
            f"{self.benefit_change_percent:+.1f}%)",
        ])


def compare(
    worker: Worker,
    reform: Reform | None = None,
    *,
    alt: int = 2,
) -> Comparison:
    """Computes a worker under present law and under ``reform``.

    ``reform=None`` compares present law with itself, which is a way of
    asking for a baseline in the same shape as a comparison.
    """
    from pyanypia.law import reformed_params

    baseline = compute(worker, alt=alt)
    if reform is None:
        return Comparison(baseline=baseline, reformed=baseline)
    if not isinstance(reform, Reform):
        raise TypeError(
            f"reform must be a pyanypia.law.Reform, not "
            f"{type(reform).__name__}"
        )
    reformed = compute(worker, params=reformed_params(reform, alt=alt))
    return Comparison(baseline=baseline, reformed=reformed)
