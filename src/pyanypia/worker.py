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
    entitlement: MonthYear | None = None  # primary entitlement (not survivor)
    benefit_date: MonthYear | None = None
    death_date: date | None = None
    earnings_hi: dict[int, float] = field(default_factory=dict)  # excess HI
    qcs_by_year: dict[int, int] = field(default_factory=dict)  # annual QCs
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
        if isinstance(self.family, list):
            object.__setattr__(self, "family", tuple(self.family))
        if isinstance(self.disability_periods, list):
            object.__setattr__(
                self, "disability_periods", tuple(self.disability_periods)
            )

    # --- derived helpers (WorkerDataGeneral accessors) ---

    @property
    def ibegin(self) -> int:
        return min(self.earnings) if self.earnings else 0

    @property
    def iend(self) -> int:
        return max(self.earnings) if self.earnings else 0

    @property
    def has_earnings(self) -> bool:
        return bool(self.earnings)

    @property
    def valdi(self) -> int:
        return len(self.disability_periods)

    def is_primary(self) -> bool:
        return self.benefit_type in (
            BenefitType.OLD_AGE, BenefitType.DISABILITY
        )

    def earn_oasdi(self, year: int) -> float:
        return self.earnings.get(year, 0.0)
