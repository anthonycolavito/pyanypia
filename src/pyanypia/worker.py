"""Immutable worker/family input model (from WorkerDataGeneral/WorkerData).

A Worker carries the same semantic inputs a .pia case file does; validation
beyond type checks happens in the engine (mirroring PiaCal::dataCheck), so
that pyanypia rejects exactly the cases the oracle rejects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

from pyanypia.dates import MonthYear


class BenefitType(enum.IntEnum):
    """WorkerDataGeneral::ben_type."""

    NO_BEN = 0
    OLD_AGE = 1
    SURVIVOR = 2
    DISABILITY = 3
    STATEMENT = 4  # PEBS_CALC


class Sex(enum.IntEnum):
    MALE = 0
    FEMALE = 1


def _as_date(v: date | str) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(v)


def _as_month_year(v: MonthYear | str | None) -> MonthYear | None:
    if v is None or isinstance(v, MonthYear):
        return v
    return MonthYear.from_string(v)


@dataclass(frozen=True)
class DisabilityPeriod:
    """One period of disability (DisabPeriod)."""

    onset: date
    first_entitlement: MonthYear | None = None
    waiting_period_start: MonthYear | None = None
    cessation: MonthYear | None = None
    cessation_pia: float = 0.0
    cessation_mfb: float = 0.0


class EarnProjType(enum.IntEnum):
    """EarnProject::earn_proj_type."""

    NO_PROJ = 0
    AVGWAGE_PROJ = 1  # follows the average-wage increase, plus a percentage
    CONSTANT_PROJ = 2  # a flat percentage each year


class EarnType(enum.IntEnum):
    """EarnProject::earn_type — how one year's earnings are supplied."""

    ENTERED = 0
    MAXIMUM = 1
    HIGH = 2
    AVERAGE = 3
    LOW = 4
    OLDLAW_MAXIMUM = 5
    CHILDCARE_YEAR = 6


@dataclass(frozen=True)
class EarningsProjection:
    """EarnProject — how the years outside the entered span are filled in.

    `first_year`/`last_year` bound the entered earnings; the worker's own
    `earnings_span` bounds the full record. Years before the entered span
    are projected backward and years after it forward.
    """

    proj_back: int = EarnProjType.NO_PROJ
    perc_back: float = 0.0
    first_year: int = 0
    proj_fwrd: int = EarnProjType.NO_PROJ
    perc_fwrd: float = 0.0
    last_year: int = 0
    earn_types: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MilitaryService:
    """One period of military service (MilServDates)."""

    start: MonthYear
    end: MonthYear

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _as_month_year(self.start))
        object.__setattr__(self, "end", _as_month_year(self.end))


@dataclass(frozen=True)
class FamilyMember:
    """A dependent or survivor (Secondary input side)."""

    bic: str  # 2-char beneficiary identification code, e.g. "B", "C1", "D"
    dob: date
    entitlement: MonthYear
    disability_onset: date | None = None  # for disabled widow(er)s ('W')

    def __post_init__(self) -> None:
        object.__setattr__(self, "dob", _as_date(self.dob))
        object.__setattr__(
            self, "entitlement", _as_month_year(self.entitlement)
        )
        bic = self.bic.strip().upper()
        object.__setattr__(self, "bic", (bic + " ")[:2])


@dataclass(frozen=True)
class Worker:
    """A worker's inputs for a benefit calculation."""

    dob: date
    sex: int  # Sex.MALE / Sex.FEMALE
    benefit_type: int  # BenefitType
    earnings: dict[int, float] = field(default_factory=dict)  # OASDI by year
    # full span of the earnings record (.pia line 06). Wider than the keys
    # of `earnings` when projection fills in the surrounding years.
    earnings_span: tuple[int, int] | None = None
    projection: EarningsProjection | None = None
    military_service: tuple[MilitaryService, ...] = ()
    entitlement: MonthYear | None = None  # primary entitlement (not survivor)
    benefit_date: MonthYear | None = None
    death_date: date | None = None
    earnings_hi: dict[int, float] = field(default_factory=dict)  # excess HI
    qcs_by_year: dict[int, int] = field(default_factory=dict)  # annual QCs
    childcare_years: frozenset[int] = frozenset()  # years with child in care
    qc_total_to_date: int = 0  # lump QCs 1937 through 1977 (qctd)
    qc_total_51_to_date: int = 0  # lump QCs 1951 through 1977 (qc51td)
    disability_periods: tuple[DisabilityPeriod, ...] = ()
    noncovered_pension: float = 0.0
    noncovered_pension_date: MonthYear | None = None
    reservist_pension: float | None = None
    totalize: bool = False
    blind: bool = False
    deemed_insured: bool = False
    oab_entitlement: MonthYear | None = None  # prior OAB before DIB
    oab_cessation: MonthYear | None = None
    family: tuple[FamilyMember, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dob", _as_date(self.dob))
        object.__setattr__(
            self, "entitlement", _as_month_year(self.entitlement)
        )
        object.__setattr__(
            self, "benefit_date", _as_month_year(self.benefit_date)
        )
        if self.death_date is not None:
            object.__setattr__(self, "death_date", _as_date(self.death_date))
        if self.benefit_date is None and self.entitlement is not None:
            object.__setattr__(self, "benefit_date", self.entitlement)
        elif (
            self.benefit_date is None
            and self.benefit_type == BenefitType.SURVIVOR
            and self.family
        ):
            # A survivor case has no entitlement of its own -- the
            # worker is dead -- so the benefit date comes from the first
            # family member, the same rule the engine uses to pick the
            # entitlement date for one.
            object.__setattr__(
                self, "benefit_date", self.family[0].entitlement
            )
        if isinstance(self.family, list):
            object.__setattr__(self, "family", tuple(self.family))
        if isinstance(self.disability_periods, list):
            object.__setattr__(
                self, "disability_periods", tuple(self.disability_periods)
            )
        if isinstance(self.military_service, list):
            object.__setattr__(
                self, "military_service", tuple(self.military_service)
            )
        if not isinstance(self.childcare_years, frozenset):
            object.__setattr__(
                self, "childcare_years", frozenset(self.childcare_years)
            )
        self._check_summary_qcs()

    def _check_summary_qcs(self) -> None:
        """WorkerDataGeneral::qctdCheck2 — reconciles the lump quarters of
        coverage with the span of entered earnings, so that the pre-1951
        total (qctd - qc51td) cannot contradict it."""
        qctd, qc51td = self.qc_total_to_date, self.qc_total_51_to_date
        if self.ibegin > 1950:
            qc51td = qctd
        if self.iend < 1951:
            qc51td = 0
        if self.ibegin > 1977:
            qctd = qc51td = 0
        object.__setattr__(self, "qc_total_to_date", qctd)
        object.__setattr__(self, "qc_total_51_to_date", qc51td)

    # --- derived helpers (WorkerDataGeneral accessors) ---

    @property
    def ibegin(self) -> int:
        if self.earnings_span is not None:
            return self.earnings_span[0]
        return min(self.earnings) if self.earnings else 0

    @property
    def iend(self) -> int:
        if self.earnings_span is not None:
            return self.earnings_span[1]
        return max(self.earnings) if self.earnings else 0

    @property
    def has_earnings(self) -> bool:
        return bool(self.earnings) or self.earnings_span is not None

    @property
    def valdi(self) -> int:
        return len(self.disability_periods)

    def is_primary(self) -> bool:
        return self.benefit_type in (
            BenefitType.OLD_AGE, BenefitType.DISABILITY
        )

    def earn_oasdi(self, year: int) -> float:
        return self.earnings.get(year, 0.0)
