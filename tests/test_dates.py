from datetime import date

import pytest

from pyanypia.dates import Age, MonthYear
from pyanypia.errors import PiaError


class TestMonthYear:
    def test_ordering(self) -> None:
        assert MonthYear(1982, 6) > MonthYear(1982, 5)
        assert MonthYear(1983, 1) > MonthYear(1982, 12)
        assert MonthYear(1982, 6) == MonthYear(1982, 6)
        assert MonthYear(1981, 12) < MonthYear(1982, 6)

    def test_add_months(self) -> None:
        assert MonthYear(2026, 12).add_months(1) == MonthYear(2027, 1)
        assert MonthYear(2026, 1).add_months(-1) == MonthYear(2025, 12)
        assert MonthYear(2026, 3).add_months(25) == MonthYear(2028, 4)

    def test_months_between(self) -> None:
        assert MonthYear(2027, 3).months_since(MonthYear(2027, 1)) == 2
        assert MonthYear(2027, 1).months_since(MonthYear(2026, 11)) == 2

    def test_validation(self) -> None:
        with pytest.raises(PiaError):
            MonthYear(2026, 13)
        with pytest.raises(PiaError):
            MonthYear(2026, 0)

    def test_from_date(self) -> None:
        assert MonthYear.from_date(date(1960, 3, 15)) == MonthYear(1960, 3)


class TestAge:
    def test_ordering_and_months(self) -> None:
        assert Age(66, 10) < Age(67, 0)
        assert Age(66, 10).to_months() == 66 * 12 + 10
        assert Age(62, 0) == Age(62, 0)

    def test_subtraction_is_months(self) -> None:
        # Age::operator- returns signed months difference
        assert Age(67, 0) - Age(66, 10) == 2
        assert Age(62, 1) - Age(65, 0) == -35
