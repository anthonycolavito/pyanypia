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
    "MethodResult",
    "MonthYear",
    "Params",
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
    reform: object | None = None,
    *,
    alt: int = 2,
) -> Comparison:
    """Computes a worker under present law and under ``reform``.

    The declarative reform layer lands with the LawChange port; until
    then this refuses a reform rather than silently ignoring it.
    """
    if reform is not None:
        raise NotImplementedError(
            "the reform layer is not available yet; compare() currently "
            "only accepts reform=None"
        )
    baseline = compute(worker, alt=alt)
    return Comparison(baseline=baseline, reformed=baseline)
