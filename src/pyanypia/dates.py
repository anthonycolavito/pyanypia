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
        return self.year * 12 + (self.month - 1)

    def add_months(self, months: int) -> MonthYear:
        t = self.index() + months
        return MonthYear(t // 12, t % 12 + 1)

    def months_since(self, other: MonthYear) -> int:
        return self.index() - other.index()

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


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
