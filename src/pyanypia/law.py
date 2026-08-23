"""Policy reforms, as declarative objects (LawChange / PiaParamsLC).

A `Reform` names the changes from present law; `Law` pairs it with an
assumption set and produces the parameters the engine computes against.
Nothing about the engine changes — a reform reaches it the same way the
C++ does, by supplying a parameter set that answers differently.

Each change carries the years it applies to and whether it takes effect
for new eligibles only or for everyone (LawChange::isEffective).

Only the changes listed here are supported. Passing an unsupported one is
an error rather than a silent no-op, because a reform that is quietly
ignored produces present-law answers under a reform's name.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from pyanypia.dates import Age
from pyanypia.params import PERC_PIA, Params, projection, retire_age
from pyanypia.params.assumptions import Assumptions

# LawChange::phaseType
FOR_NEW_ELIGIBLES = 0
FOR_EVERYONE = 1

# LawChangeNRACHANGE
NRA_AGE_AR_CHANGE = Age(69, 0)
NRA_AR_MONTHLY_67_69 = 3.0 / 800.0
NRA_AR_MONTHLY_69_PLUS = 1.0 / 300.0

MAX_MONTHS_AR_62_67 = retire_age.AGE_67 - retire_age.AGE_62
MAX_MONTHS_AR_62_65 = retire_age.AGE_65 - retire_age.AGE_62
MAX_MONTHS_AR_65_67 = retire_age.AGE_67 - retire_age.AGE_65


@dataclass(frozen=True)
class Change:
    """One change from present law, over a span of years."""

    start_year: int
    end_year: int
    phase_type: int = FOR_NEW_ELIGIBLES

    def is_effective(self, elig_year: int, benefit_year: int) -> bool:
        """LawChange::isEffective — a change for new eligibles keys on the
        eligibility year, one for everyone on the benefit year."""
        year = elig_year if self.phase_type == FOR_NEW_ELIGIBLES else benefit_year
        return self.start_year <= year <= self.end_year


@dataclass(frozen=True)
class NraChange(Change):
    """Change the full retirement age.

    `variant` 1 holds it at 65; 2 removes the plateau between 66 and 67;
    3 also raises it after 2011. Variants 2 and 3 additionally reduce
    benefits beyond age 67 at 3/8 of a percent a month, and beyond 69 at
    1/3 of a percent.
    """

    variant: int = 1


@dataclass(frozen=True)
class ColaChange(Change):
    """Add `adjustment` percentage points to each benefit increase in the
    span — negative to trim them."""

    adjustment: float = 0.0


@dataclass(frozen=True)
class BendPointFraction(Change):
    """Grow the PIA bend points at `proportion` of the wage rate rather
    than the full rate (LawChangeBPFRACWAGE).

    Defined but not supported -- see `Reform` for why.
    """

    proportion: float = 1.0


@dataclass(frozen=True)
class BendPointMinusConstant(Change):
    """Grow the PIA bend points at the wage rate less `constant`
    percentage points (LawChangeBPMINCONST).

    Defined but not supported -- see `Reform` for why.
    """

    constant: float = 0.0


@dataclass(frozen=True)
class DiDropoutFive(Change):
    """Give every computation five dropout years rather than the
    one-for-five disability rule (LawChangeDIDROP5)."""


@dataclass(frozen=True)
class DecliningPercentages(Change):
    """The benefit formula percentages falling year by year
    (LawChangeDECLINEPERC).

    `factors` are the percentage cuts applied to each of the three
    formula percentages in every year of the span, compounding: 1.0 takes
    a hundredth off what the year before had. `later` opens further
    intervals, each with its own factors, from the year it names.
    """

    factors: tuple[float, float, float] = (0.0, 0.0, 0.0)
    later: tuple[tuple[int, tuple[float, float, float]], ...] = ()


@dataclass(frozen=True)
class ChildCareDropout(Change):
    """Widen the child-care dropout years (LawChangeCHILDCAREDROPOUT).

    The method becomes applicable to everyone in the span, up to
    `max_years` dropout years are allowed counting the ordinary ones, and
    a year counts as child-care if its earnings are at or under
    `fq_ratio` of the average wage rather than zero.

    The change also carries a maximum age of child, which the batch path
    never reads -- nothing in the calculation calls getMaxChildcareAge(),
    because the child-care years come in on the case itself.
    """

    fq_ratio: float = 0.0
    max_years: int = 3


@dataclass(frozen=True)
class Age65ComputationPoint(Change):
    """Move the computation point from age 62 towards 65, so that more
    years count towards the elapsed years (LawChangeAGE65COMP).

    `years` is how far it ends up moving, one to three; `step` phases it
    in, a year at a time every `step` years of eligibility.
    """

    years: int = 1
    step: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.years <= 3:
            raise ValueError(f"years must be 1 to 3, not {self.years}")
        if self.step < 1:
            raise ValueError(f"step must be at least 1, not {self.step}")


@dataclass(frozen=True)
class SpecialMinimum(Change):
    """Replace the special minimum's amount per year of coverage
    (LawChangeNEWSPECMIN).

    The change also offers a different maximum number of usable years,
    which is not modelled: `SpecMin` caps the years it uses at
    `specMinMaxYearsPL()`, the present-law maximum, so a raised one only
    ever sizes a table whose extra rows nothing reads.
    """

    amount: float = 0.0


@dataclass(frozen=True)
class WageBaseChange(Change):
    """Replace the OASDI contribution and benefit base for the years in
    the span; automatic projection resumes after them."""

    bases: dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [
            y for y in range(self.start_year, self.end_year + 1)
            if y not in self.bases
        ]
        if missing:
            raise ValueError(f"wage base missing for years {missing}")


@dataclass(frozen=True)
class Reform:
    """A set of changes from present law.

    The two bend-point changes are defined above but rejected here. The
    calculator cannot compute them: `PiaParamsLC` builds the bend-point
    wage series in its constructor, which runs before `AnypiabDoc` calls
    `setHistFqinc()`, so `setFqBppia()` reads a benefit-increase series of
    all zeros and nothing recomputes it afterwards. Every eligibility year
    from the change onward is left with the bend points of the year before
    it began, whatever proportion was asked for, and where the span ends
    early the projection past it divides zero by zero. Since there is no
    answer to check against, pyanypia does not offer one.
    """

    nra: NraChange | None = None
    cola: ColaChange | None = None
    wage_base: WageBaseChange | None = None
    special_min: SpecialMinimum | None = None
    comp_point: Age65ComputationPoint | None = None
    childcare_dropout: ChildCareDropout | None = None
    declining_perc: DecliningPercentages | None = None
    bend_point_fraction: BendPointFraction | None = None
    bend_point_minus: BendPointMinusConstant | None = None
    di_dropout_five: DiDropoutFive | None = None

    def __post_init__(self) -> None:
        unsupported = [
            name for name in ("bend_point_fraction", "bend_point_minus")
            if getattr(self, name) is not None
        ]
        if unsupported:
            raise ValueError(
                f"{', '.join(unsupported)}: bend-point reforms are not "
                f"supported, because the calculator computes them from a "
                f"wage series it builds before it knows any wages -- the "
                f"proportion asked for makes no difference to its answer, "
                f"and past a closed span it returns NaN. See Reform's "
                f"docstring."
            )

    def __bool__(self) -> bool:
        return any(
            getattr(self, f.name) is not None
            for f in dataclasses.fields(self)
        )


class ReformedParams(Params):
    """Present-law parameters with a reform applied (PiaParamsLC)."""

    def __init__(self, assumptions: Assumptions, reform: Reform) -> None:
        self.reform = reform
        self._declining_perc: dict[int, tuple[float, ...]] | None = None
        super().__init__(assumptions)
        if reform.declining_perc is not None:
            self._declining_perc = self._build_declining_perc()

    def _build_declining_perc(self) -> dict[int, tuple[float, ...]]:
        """LawChangeDECLINEPERC::percPiaCal and PiaParamsLC::projectPerc.

        Each interval compounds its cuts onto where the one before left
        off, and the last percentages reached carry forward unchanged.
        """
        change = self.reform.declining_perc
        assert change is not None
        intervals = [(change.start_year, change.factors), *change.later]
        out: dict[int, tuple[float, ...]] = {}
        current = list(PERC_PIA)
        last_overall = min(self.maxyear, change.end_year)
        for i, (start, factors) in enumerate(intervals):
            end = (
                last_overall if i == len(intervals) - 1
                else min(self.maxyear, intervals[i + 1][0] - 1)
            )
            for year in range(start, end + 1):
                current = [
                    c * (1.0 - f / 100.0)
                    for c, f in zip(current, factors, strict=True)
                ]
                out[year] = tuple(current)
        for year in range(last_overall + 1, self.maxyear + 1):
            out[year] = tuple(current)
        return out

    def perc_pia(self, elig_year: int) -> tuple[float, ...]:
        """PiaParams::percPiaCal off the changed percentages."""
        if self._declining_perc is None:
            return super().perc_pia(elig_year)
        return self._declining_perc.get(
            elig_year, super().perc_pia(elig_year)
        )

    # ---- construction-time hooks ----

    def adjust_cpiinc(self) -> None:
        cola = self.reform.cola
        if cola is None:
            return
        last = min(self.maxyear, cola.end_year)
        for year in range(cola.start_year, last + 1):
            if year in self.cpiinc:
                self.cpiinc[year] += cola.adjustment

    def project_bases(self) -> None:
        """WageBaseLC::project — project up to the ad hoc window, drop the
        ad hoc bases in over whatever was there, then project past them
        off the last of them rather than chaining."""
        change = self.reform.wage_base
        if change is None:
            super().project_bases()
            return
        projection.project_base(
            self.base_oasdi, self.fq, self.cpiinc, 0,
            self.istart + 1, change.start_year - 1,
        )
        for year in range(change.start_year, change.end_year + 1):
            self.base_oasdi[year] = change.bases[year]
        projection.project_base_after_ad_hoc(
            self.base_oasdi, self.fq, self.cpiinc,
            change.end_year, self.maxyear,
        )
        # only the OASDI series has an ad hoc change here; ind 2 and 3,
        # which also move the 1977-law bases, are not supported
        projection.project_base(
            self.base_77, self.fq, self.cpiinc, 2,
            self.istart + 1, self.maxyear,
        )
        projection.project_base(
            self.base_hi, self.fq, self.cpiinc, 3,
            self.istart + 1, self.maxyear,
        )

    # ---- parameters the engine asks for ----

    def full_ret_age(self, elig_year: int) -> Age:
        """PiaParamsLC::fullRetAgeCal."""
        nra = self.reform.nra
        if nra is None:
            return super().full_ret_age(elig_year)
        if nra.variant == 1:
            return retire_age.AGE_65
        if elig_year < 2000:
            return retire_age.AGE_65
        if elig_year < 2005:
            return Age(65, 2 * (elig_year - 1999))
        if elig_year < 2006:
            return Age(66, 0)
        if elig_year < 2011:
            return Age(66, 2 * (elig_year - 2005))
        if nra.variant == 2:
            return retire_age.AGE_67
        # variant 3 keeps rising: one month per two years
        months = (elig_year - 2011) // 2
        return Age(67 + months // 12, months % 12)

    def full_ret_age_di(self, elig_year: int, current_year: int) -> Age:
        """PiaParamsLC::fullRetAgeCalDI — a change does not reach benefit
        calculations until 2006."""
        if self.reform.nra is not None and current_year > 2005:
            return self.full_ret_age(elig_year)
        return super().full_ret_age_di(elig_year, current_year)

    def max_dib_age(self, year: int) -> Age:
        """PiaParamsLC::maxDibAge."""
        nra = self.reform.nra
        if nra is None:
            return super().max_dib_age(year)
        if nra.variant == 1:
            return retire_age.AGE_65
        if year < 2003:
            return retire_age.AGE_65
        if year < 2008:
            return Age(65, 2 * (year - 2002))
        if year < 2010:
            return Age(66, 0)
        if year < 2015:
            return Age(66, 2 * (year - 2009))
        if nra.variant == 2:
            return retire_age.AGE_67
        years = 67 + (year - 2015) // 25
        year25 = 2016 + (years - 67) * 25
        return Age(years, max(0, (year - year25) // 2))

    def factor_ar(self, months_ardri: int) -> float:
        """PiaParamsLC::factorArCal."""
        if self.reform.nra is None or months_ardri <= MAX_MONTHS_AR_62_67:
            return super().factor_ar(months_ardri)
        return _reduction_beyond_67(
            months_ardri, retire_age.AR_MONTHLY_OAB_62_65
        )

    def factor_ar_aged_spouse(self, months_ardri: int) -> float:
        """PiaParamsLC::factorArAgedSpouseCal."""
        if self.reform.nra is None or months_ardri <= MAX_MONTHS_AR_62_67:
            return super().factor_ar_aged_spouse(months_ardri)
        return _reduction_beyond_67(
            months_ardri, retire_age.AR_MONTHLY_SPOUSE_62_65
        )

    def max_childcare_dropout_years(
        self, elig_year: int, benefit_year: int
    ) -> int:
        """PiaParamsLC::getMaxChildcareDropoutYears."""
        change = self.reform.childcare_dropout
        if change is not None and change.is_effective(elig_year, benefit_year):
            return change.max_years
        return super().max_childcare_dropout_years(elig_year, benefit_year)

    def childcare_dropout_amount(
        self, elig_year: int, benefit_year: int
    ) -> float:
        """PiaParamsLC::getChildcareDropoutAmount — a share of the average
        wage in the benefit year."""
        change = self.reform.childcare_dropout
        if change is not None and change.is_effective(elig_year, benefit_year):
            return change.fq_ratio * self.fq[benefit_year]
        return super().childcare_dropout_amount(elig_year, benefit_year)

    def childcare_always_applicable(
        self, elig_year: int, benefit_year: int
    ) -> bool:
        change = self.reform.childcare_dropout
        return change is not None and change.is_effective(
            elig_year, benefit_year
        )

    def comp_point_shift(self, elig_year: int, benefit_year: int) -> int:
        """PiaCalLC::nelapsed2Cal — the phase-in, capped at the change's
        own number of years."""
        change = self.reform.comp_point
        if change is None or not change.is_effective(elig_year, benefit_year):
            return 0
        return min(
            _trunc_div(elig_year - change.start_year, change.step) + 1,
            change.years,
        )

    def spec_min_amount(self, year: int) -> float:
        """PiaParamsLC::specMinAmountCal — the new amount applies from its
        first year on, keyed on the year alone rather than on
        isEffective."""
        change = self.reform.special_min
        if change is not None and year >= change.start_year:
            return change.amount
        return super().spec_min_amount(year)

    def spec_min_split_year(self) -> int | None:
        change = self.reform.special_min
        return None if change is None else change.start_year

    def n_drop_override(self, ent_year: int, elig_year: int) -> int | None:
        """PiaCalLC::nCal — a flat five dropout years."""
        change = self.reform.di_dropout_five
        if change is None:
            return None
        if ent_year >= change.start_year and elig_year >= change.start_year - 2:
            return 5
        return None


def _trunc_div(numerator: int, denominator: int) -> int:
    """C++ integer division, which truncates towards zero where Python
    floors. They differ only for a negative numerator, which a change
    effective for everyone rather than for new eligibles can produce."""
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def _reduction_beyond_67(months_ardri: int, monthly_62_65: float) -> float:
    """The reduction factor once a raised full retirement age pushes the
    reduction past 60 months: 3/8 of a percent a month to age 69, then
    1/3 of a percent."""
    max_months_lc = NRA_AGE_AR_CHANGE - retire_age.AGE_62
    base = (
        1.0
        - float(MAX_MONTHS_AR_62_65) * monthly_62_65
        - float(MAX_MONTHS_AR_65_67) * retire_age.AR_MONTHLY_65_67
    )
    if months_ardri <= max_months_lc:
        excess = months_ardri - MAX_MONTHS_AR_62_67
        return base - float(excess) * NRA_AR_MONTHLY_67_69
    excess = months_ardri - max_months_lc
    months_67_69 = max_months_lc - MAX_MONTHS_AR_62_67
    return (
        base
        - float(months_67_69) * NRA_AR_MONTHLY_67_69
        - float(excess) * NRA_AR_MONTHLY_69_PLUS
    )


class Law:
    """An assumption set plus a reform, producing engine parameters."""

    def __init__(self, params: Params, reform: Reform | None = None) -> None:
        self.params = params
        self.reform = reform or Reform()

    @classmethod
    def present_law(cls, alt: int = 2) -> Law:
        from pyanypia.params import present_law as _present_law

        return cls(_present_law(alt))

    def apply(self, reform: Reform, *, alt: int = 2) -> Law:
        """This law with `reform` applied."""
        return Law(
            ReformedParams(Assumptions.tr_alternative(alt), reform), reform
        )


def reformed_params(reform: Reform, *, alt: int = 2) -> Params:
    """Present-law parameters under `alt` with `reform` applied."""
    return ReformedParams(Assumptions.tr_alternative(alt), reform)


__all__ = [
    "FOR_EVERYONE",
    "FOR_NEW_ELIGIBLES",
    "Age65ComputationPoint",
    "BendPointFraction",
    "ChildCareDropout",
    "BendPointMinusConstant",
    "Change",
    "ColaChange",
    "DecliningPercentages",
    "DiDropoutFive",
    "Law",
    "NraChange",
    "Reform",
    "ReformedParams",
    "SpecialMinimum",
    "WageBaseChange",
    "reformed_params",
]
