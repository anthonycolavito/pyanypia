"""Social Security Statement estimates (Pebs, PiaCalAny's PEBS paths).

A Statement is not one calculation but five: retirement at 70, at full
retirement age and at the earliest possible age, a survivor estimate, and
a disability estimate. Each runs the whole engine over the same earnings
record with the entitlement, benefit date and last year of earnings moved
to suit that scenario, so this module drives the engine five times rather
than reimplementing anything.

Estimates are whole dollars (rounded down to $5 before 2000). When a
scenario does not apply — a delayed-retirement estimate for someone
already past 70, a disability estimate for someone past full retirement
age — the C++ leaves the previous scenario's inputs in place and reports
its answer again, and so does this.

Batch anypiab can only compute a Statement for a worker already at full
retirement age. Below that it runs a disability estimate, and pebsSetup
leaves the period's waiting-period date unset while freezeYearsCal reads
it, so the freeze period comes out inverted and the quarter arithmetic
underflows. These estimates are validated against the oracle for every
case the oracle can compute.
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from datetime import date, timedelta

from pyanypia.dates import Age, MonthYear
from pyanypia.errors import PiaError
from pyanypia.params import Params, params_for, present_law, retire_age
from pyanypia.results import Results, results_from_context
from pyanypia.worker import (
    BenefitType,
    DisabilityPeriod,
    EarningsProjection,
    EarnProjType,
    Worker,
)

AMEND2000_YEAR = 2000
AGE70 = Age(70, 0)
FLAT_ASSUMPTIONS = 5


class StatementType(enum.IntEnum):
    """Pebs::pebes_type, in the order the calculation runs them."""

    OAB_DELAYED = 0
    OAB_FULL = 1
    OAB_EARLY = 2
    SURVIVOR = 3
    DISABILITY = 4


@dataclass(frozen=True)
class StatementEstimate:
    """One scenario's estimate, in whole dollars."""

    kind: StatementType
    pia: int
    mfb: int
    benefit: int


@dataclass(frozen=True)
class StatementResults:
    """A worker's Social Security Statement estimates."""

    age_now: Age
    full_retirement_age: Age
    quarters_of_coverage: int
    estimates: dict[StatementType, StatementEstimate]
    #: Estimates the calculator cannot produce, and why. Reading one
    #: through its property raises rather than returning a number.
    unavailable: dict[StatementType, str] = field(default_factory=dict)

    @property
    def retirement_early(self) -> int:
        return self.estimates[StatementType.OAB_EARLY].benefit

    @property
    def retirement_full(self) -> int:
        return self.estimates[StatementType.OAB_FULL].benefit

    @property
    def retirement_delayed(self) -> int:
        return self.estimates[StatementType.OAB_DELAYED].benefit

    @property
    def survivor_benefit(self) -> int:
        return self.estimates[StatementType.SURVIVOR].benefit

    @property
    def disability_pia(self) -> int:
        if StatementType.DISABILITY in self.unavailable:
            raise PiaError(
                0, self.unavailable[StatementType.DISABILITY]
            )
        return self.estimates[StatementType.DISABILITY].pia

    def detail(self) -> str:
        return "\n".join([
            f"age now: {self.age_now}",
            f"full retirement age: {self.full_retirement_age}",
            f"quarters of coverage: {self.quarters_of_coverage}",
            f"retirement at 70:  ${self.retirement_delayed}",
            f"retirement at FRA: ${self.retirement_full}",
            f"retirement early:  ${self.retirement_early}",
            f"survivor benefit:  ${self.survivor_benefit}",
            (
                "disability PIA:    unavailable "
                "(the calculator cannot compute one below full "
                "retirement age)"
                if StatementType.DISABILITY in self.unavailable
                else f"disability PIA:    ${self.disability_pia}"
            ),
        ])


def round5(amount: float, year: int) -> int:
    """BenefitAmount::round5 — Statement amounts are whole dollars from
    2000, and multiples of $5 before that."""
    if year < AMEND2000_YEAR:
        return 5 * int((amount + 0.01) / 5.0)
    return int(amount + 0.01)


def _age_at(kbirth: date, when: MonthYear) -> Age:
    """DateMoyr::operator- — age attained at `when`."""
    months = (when.year - kbirth.year) * 12 + (when.month - kbirth.month)
    return Age(months // 12, months % 12)


def _at_age(kbirth: date, age: Age) -> MonthYear:
    """The month in which `age` is attained."""
    return MonthYear(kbirth.year, kbirth.month).add_months(
        age.years * 12 + age.months
    )


def _pebs_earnings(worker: Worker, istart: int) -> Worker:
    """EarnProject::setPebsData plus WorkerDataGeneral::setPebsData.

    Entered earnings carry flat through the year after the Statement
    year and are projected forward with the average wage after that; any
    disability or death on the record is dropped.
    """
    entered = sorted(worker.earnings)
    earnings = dict(worker.earnings)
    last_year = istart + 1
    if entered and last_year > entered[-1]:
        last_earn = earnings[entered[-1]]
        for year in range(entered[-1] + 1, last_year + 1):
            earnings[year] = last_earn
    projection = EarningsProjection(
        proj_back=EarnProjType.NO_PROJ,
        first_year=worker.ibegin,
        proj_fwrd=EarnProjType.AVGWAGE_PROJ,
        last_year=last_year,
    )
    return dataclasses.replace(
        worker,
        earnings=earnings,
        earnings_span=(worker.ibegin, max(worker.iend, last_year)),
        projection=projection,
        disability_periods=(),
        death_date=None,
    )


def _plan(
    kbirth: date, istart: int, month_now: int, age_plan: int
) -> tuple[Age, int, int, int]:
    """PiaCalAny::pebsOabCal — which scenarios apply."""
    age_now = _age_at(kbirth, MonthYear(istart, month_now))
    full_ret_age = retire_age.full_ret_age(kbirth.year + 62)
    if not age_now < full_ret_age:
        # already at full retirement age: no disability estimate, and a
        # delayed-retirement estimate only while not yet 70
        pebs_dib = 0
        pebs_oab = 2 if age_now < AGE70 else 1
    else:
        pebs_dib = 1
        pebs_oab = 2 if full_ret_age < Age(age_plan, 0) else 3
    age_plan2 = max(age_plan if age_plan > 0 else 62, age_now.years)
    return age_now, pebs_oab, pebs_dib, age_plan2


def _setup(
    kind: StatementType,
    base: Worker,
    istart: int,
    month_now: int,
    age_plan: int,
    age_plan2: int,
    age_now: Age,
    pebs_oab: int,
    pebs_dib: int,
) -> Worker | None:
    """PiaCalAny::pebsSetup — the inputs for one scenario, or None when it
    does not apply."""
    kbirth = base.dob - timedelta(days=1)
    now = MonthYear(istart, month_now)

    def oab(age: Age, iend: int | None = None) -> Worker:
        ent = _at_age(kbirth, age)
        return dataclasses.replace(
            base,
            benefit_type=BenefitType.OLD_AGE,
            entitlement=ent,
            benefit_date=ent,
            earnings_span=(
                base.ibegin, ent.year - 1 if iend is None else iend
            ),
        )

    if kind == StatementType.OAB_DELAYED:
        return oab(max(AGE70, age_now))
    if kind == StatementType.OAB_FULL:
        if pebs_oab < 2:
            return None
        full = retire_age.full_ret_age(kbirth.year + 62)
        return oab(max(full, age_now))
    if kind == StatementType.OAB_EARLY:
        if pebs_oab < 3:
            return None
        early = retire_age.early_age_oab(base.sex, kbirth)
        age = early if early.years >= age_plan else Age(age_plan, 0)
        age = max(age, age_now)
        # earnings stop in the planned retirement year, but never before
        # the year prior to the Statement
        iend = base.iend
        if age.years > age_plan2:
            iend = kbirth.year + age_plan2 - 1
        return oab(age, max(iend, istart - 1))
    if kind == StatementType.SURVIVOR:
        return dataclasses.replace(
            base,
            benefit_type=BenefitType.SURVIVOR,
            entitlement=now,
            benefit_date=now,
            death_date=date(now.year, now.month, 1),
            earnings_span=(base.ibegin, istart),
        )
    if pebs_dib < 1:
        return None
    return dataclasses.replace(
        base,
        benefit_type=BenefitType.DISABILITY,
        entitlement=now,
        benefit_date=now,
        death_date=None,
        disability_periods=(
            DisabilityPeriod(onset=date(now.year, now.month, 1)),
        ),
        earnings_span=(base.ibegin, istart - 1),
    )


def calculate_statement(
    worker: Worker,
    *,
    month_now: int,
    age_plan: int = 0,
    istart: int | None = None,
    params: Params | None = None,
    alt: int = FLAT_ASSUMPTIONS,
) -> StatementResults:
    """A worker's Statement estimates.

    ``month_now`` is the month the Statement is prepared in and ``istart``
    its year (defaulting to the parameter set's current year). ``age_plan``
    is the age the worker plans to retire at, or 0 for none. Statements
    use flat assumptions, so ``alt`` defaults to 5.
    """
    if params is None:
        params = (
            present_law(alt) if alt in (1, 2, 3) else params_for(alt, alt)
        )
    if istart is None:
        istart = params.istart
    kbirth = worker.dob - timedelta(days=1)
    base = _pebs_earnings(worker, istart)
    age_now, pebs_oab, pebs_dib, age_plan2 = _plan(
        kbirth, istart, month_now, age_plan
    )
    estimates: dict[StatementType, StatementEstimate] = {}
    unavailable: dict[StatementType, str] = {}
    current = base
    qc_total = 0
    for kind in StatementType:
        if kind is StatementType.DISABILITY and pebs_dib >= 1:
            # PiaCalAny::pebsSetup builds the disability scenario with an
            # onset date and no waiting-period date, and the freeze
            # calculation then reads one. The official calculator has the
            # same gap, so there is no answer to match and none is
            # invented; the other estimates are unaffected.
            unavailable[kind] = (
                "the calculator cannot produce a disability estimate for "
                "a worker below full retirement age: PiaCalAny::pebsSetup "
                "leaves the waiting-period date unset and the freeze "
                "calculation requires it"
            )
            continue
        nxt = _setup(
            kind, base, istart, month_now, age_plan, age_plan2,
            age_now, pebs_oab, pebs_dib,
        )
        if nxt is not None:
            current = nxt
        result, qcs = _run(current, params)
        if kind == StatementType.OAB_DELAYED:
            qc_total = min(40, qcs)
        pia = round5(result.pia, istart)
        mfb = round5(result.mfb, istart)
        benefit = (
            round5(0.75 * pia, istart) if kind == StatementType.SURVIVOR
            else round5(result.unrounded_benefit, istart)
        )
        estimates[kind] = StatementEstimate(kind, pia, mfb, benefit)
    return StatementResults(
        age_now=age_now,
        full_retirement_age=retire_age.full_ret_age(kbirth.year + 62),
        quarters_of_coverage=qc_total,
        estimates=estimates,
        unavailable=unavailable,
    )


def _run(worker: Worker, params: Params) -> tuple[Results, int]:
    from pyanypia.engine.compute import calculate

    ctx = calculate(worker, params, ent_date=worker.entitlement)
    return results_from_context(ctx), ctx.qc_total
