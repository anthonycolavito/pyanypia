"""Immutable results of a benefit calculation."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyanypia.dates import Age
from pyanypia.engine.compute import METHOD_NAME
from pyanypia.engine.context import CalcContext


@dataclass(frozen=True)
class MethodResult:
    """One PIA method's outcome."""

    method: str
    applicable: int
    ame: float
    pia: float
    mfb: float
    years_of_coverage: int = 0

    @property
    def aime(self) -> float:
        return self.ame


@dataclass(frozen=True)
class FamilyMemberResult:
    """One family member's benefit."""

    bic: str
    benefit_factor: float
    months_reduction: int
    full_benefit: float  # PIA x factor, before family max
    after_max: float  # after family-maximum reduction
    rounded_benefit: float  # payable
    pifc: str


@dataclass(frozen=True)
class Results:
    """Everything computed for a worker."""

    benefit_type: int
    fully_insured_code: str  # OACT code '1'..'7'
    insured: bool
    disability_insured: bool
    elig_year: int
    aime: float
    pia: float  # highest PIA
    mfb: float  # corresponding family maximum
    monthly_benefit: float  # rounded, payable
    unrounded_benefit: float
    support_pia: float
    months_reduction_or_credit: int
    reduction_factor: float
    age_at_benefit: Age | None
    method: str  # selected method name
    pifc: str
    methods: dict[str, MethodResult] = field(default_factory=dict)
    family: tuple[FamilyMemberResult, ...] = ()

    # convenient aliases
    @property
    def mba(self) -> float:
        return self.monthly_benefit

    def detail(self) -> str:
        lines = [
            f"insured: {self.fully_insured_code} "
            f"({'fully insured' if self.insured else 'NOT fully insured'})",
            f"eligibility year: {self.elig_year}",
            f"AIME: {self.aime:.0f}",
        ]
        for name, m in self.methods.items():
            mark = " *" if name == self.method else ""
            lines.append(
                f"  {name}: PIA {m.pia:.2f}  MFB {m.mfb:.2f}{mark}"
            )
        lines.append(
            f"PIA {self.pia:.2f}, MFB {self.mfb:.2f}, "
            f"benefit {self.monthly_benefit:.2f}"
            f" at age {self.age_at_benefit}"
        )
        return "\n".join(lines)


def results_from_context(ctx: CalcContext) -> Results:
    methods = getattr(ctx, "methods", [])
    by_name = {}
    aime = 0.0
    for m in methods:
        name = METHOD_NAME[int(m.method)]
        by_name[name] = MethodResult(
            method=name,
            applicable=int(m.applicable),
            ame=m.ame,
            pia=m.pia_ent,
            mfb=m.mfb_ent,
            years_of_coverage=m.years_total,
        )
        if name == "WAGE_IND":
            aime = m.ame
    from pyanypia.engine.insured import is_disability_insured

    fam_results = tuple(
        FamilyMemberResult(
            bic=s.member.bic.strip(),
            benefit_factor=s.benefit_factor,
            months_reduction=s.months_ardri,
            full_benefit=s.full_benefit,
            after_max=s.benefit,
            rounded_benefit=s.rounded_benefit,
            pifc=s.pifc,
        )
        for s in getattr(ctx, "secondaries", [])
    )
    return Results(
        benefit_type=ctx.ioasdi,
        fully_insured_code=ctx.fins_code2,
        insured=ctx.fins_code2 not in ("4", "5", "6", "7"),
        disability_insured=is_disability_insured(ctx.dis_ins_code),
        elig_year=ctx.elig_year,
        aime=aime,
        pia=ctx.high_pia,
        mfb=ctx.high_mfb,
        monthly_benefit=ctx.rounded_benefit,
        unrounded_benefit=ctx.unrounded_benefit,
        support_pia=ctx.support_pia,
        months_reduction_or_credit=ctx.months_ardri,
        reduction_factor=ctx.arf,
        age_at_benefit=ctx.age_ben,
        method=METHOD_NAME.get(ctx.iappn, " "),
        pifc=ctx.pifc,
        methods=by_name,
        family=fam_results,
    )
