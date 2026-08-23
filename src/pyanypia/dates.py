"""Month/year and age types, from datemoyr.h and age.h.

``MonthYear`` mirrors DateMoyr (a month precision date, months 1-12);
``Age`` mirrors Age (years + months, with subtraction yielding months).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import total_ordering

from pyanypia.errors import PIA_IDS_DATEMONTH, PiaError


@total_ordering
@dataclass(frozen=True, slots=True)
class MonthYear:
    """A (year, month) date, ordered chronologically."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise PiaError(PIA_IDS_DATEMONTH, f"bad month {self.month}")

    @classmethod
    def from_date(cls, d: date) -> MonthYear:
        return cls(d.year, d.month)

    @classmethod
    def from_string(cls, s: str) -> MonthYear:
        """Parses 'YYYY-MM' or 'MM/YYYY'."""
        if "-" in s:
            y, m = s.split("-")
            return cls(int(y), int(m))
        m, y = s.split("/")
        return cls(int(y), int(m))

    def __lt__(self, other: MonthYear) -> bool:
        return (self.year, self.month) < (other.year, other.month)

    def index(self) -> int:
        """DateMoyr::index — months since January 1971, so earlier months
        are negative. The delayed-retirement-credit window is defined
        against this origin, so it is not an arbitrary one."""
        return 12 * (self.year - 1971) + (self.month - 1)

    def add_months(self, months: int) -> MonthYear:
        t = self.index() + months
        return MonthYear(1971 + t // 12, t % 12 + 1)

    def months_since(self, other: MonthYear) -> int:
        return self.index() - other.index()

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@total_ordering
@dataclass(frozen=True, slots=True)
class QtrYear:
    """A (quarter, year) date; quarters run 0-3 (from qtryear.h)."""

    quarter: int
    year: int

    @classmethod
    def from_date(cls, d: date) -> QtrYear:
        return cls((d.month - 1) // 3, d.year)

    @classmethod
    def from_month_year(cls, my: MonthYear) -> QtrYear:
        return cls((my.month - 1) // 3, my.year)

    def __lt__(self, other: QtrYear) -> bool:
        return (self.year, self.quarter) < (other.year, other.quarter)

    def index(self) -> int:
        return self.year * 4 + self.quarter

    def add(self, quarters: int) -> QtrYear:
        t = self.index() + quarters
        return QtrYear(t % 4, t // 4)

    def subtract(self, quarters: int) -> QtrYear:
        return self.add(-quarters)

    def diff(self, other: QtrYear) -> int:
        """other - self in quarters (QtrYear::diff(a1, a2) = a2 - a1)."""
        return other.index() - self.index()

    def to_month_year(self) -> MonthYear:
        return MonthYear(self.year, 3 * self.quarter + 1)


@total_ordering
@dataclass(frozen=True, slots=True)
class Age:
    """An age in whole years and months (0-11)."""

    years: int
    months: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.months <= 11:
            raise PiaError(PIA_IDS_DATEMONTH, f"bad age months {self.months}")

    def __lt__(self, other: Age) -> bool:
        return (self.years, self.months) < (other.years, other.months)

    def to_months(self) -> int:
        return self.months + 12 * self.years

    def __sub__(self, other: Age) -> int:
        return self.to_months() - other.to_months()

    def __str__(self) -> str:
        return f"{self.years}y{self.months}m"
