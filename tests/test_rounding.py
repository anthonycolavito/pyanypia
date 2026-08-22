"""Unit tests for SSA rounding primitives, derived from BenefitAmount.cpp.

Money comparisons use cents() — 2-decimal formatting — which is the
precision level the oracle goldens carry. The underlying doubles may be
values like 100.10000000000001; the C++ produces the identical doubles
(same IEEE-754 operations in the same order), so cent-level equality is
the meaningful contract.
"""

import math

from pyanypia import rounding
from pyanypia.dates import MonthYear


def cents(x: float) -> str:
    return f"{x:.2f}"


class TestRoundBenefit:
    def test_1982_and_later_rounds_down_to_dime(self) -> None:
        assert rounding.round_benefit(100.05, 1983) == 100.0
        assert rounding.round_benefit(2734.99, 2024) == 2734.9
        assert rounding.round_benefit(2734.90, 2024) == 2734.9

    def test_1973_to_1981_rounds_up_to_dime(self) -> None:
        # q = 0.009: anything not already a dime multiple rounds UP
        assert cents(rounding.round_benefit(100.01, 1975)) == "100.10"
        assert cents(rounding.round_benefit(100.0, 1975)) == "100.00"
        # float repr: 100.05*100 = 10004.999..., fmod -> 4.999... >= q -> up
        assert cents(rounding.round_benefit(100.05, 1975)) == "100.10"

    def test_pre_1973_half_cent_rule(self) -> None:
        # q = 0.499: less than half a cent above a dime rounds down
        assert cents(rounding.round_benefit(100.004, 1970)) == "100.00"
        assert cents(rounding.round_benefit(100.005, 1970)) == "100.10"

    def test_matches_cpp_expression_exactly(self) -> None:
        # transliteration check on a grid of values (bit-exact)
        for c in range(0, 1000, 7):
            amt = c / 100.0 + 0.001 * (c % 3)
            got = rounding.round_benefit(amt, 1990)
            assert got == math.floor(10.0 * amt + 0.0005) / 10.0


class TestUnround:
    def test_post_1982_rounds_up(self) -> None:
        assert rounding.unround_benefit(100.0, 1983) == 100.0
        assert cents(rounding.unround_benefit(100.01, 1983)) == "100.10"

    def test_pre_1973_rounds_down(self) -> None:
        # 0.4 cents below the dime: 10-fmod = 0.4, not > 9.501 -> down
        assert cents(rounding.unround_benefit(100.096, 1970)) == "100.00"
        # exactly on a dime stays (10 - 0 = 10 > 9.501 -> up by 0.10? no:
        # fmod(10000,10)=0 -> x100=10 > q -> amount += 0.10... the C++
        # treats an exact dime as 10 cents below the next dime and adds a
        # dime. Transliterated faithfully:
        assert cents(rounding.unround_benefit(100.0, 1970)) == "100.10"


class TestCola:
    def test_apply_cola_modern(self) -> None:
        assert rounding.apply_cola(1000.0, 2.5, 2024) == 1025.0
        # 3.2% on 1234.50 -> 1274.004 -> dime down 1274.00
        assert cents(rounding.apply_cola(1234.5, 3.2, 2023)) == "1274.00"

    def test_apply_cola_1975(self) -> None:
        # 8.0% on 123.40 -> 133.272 -> up to dime 133.30
        assert cents(rounding.apply_cola(123.4, 8.0, 1975)) == "133.30"

    def test_unapply_cola_inverts(self) -> None:
        up = rounding.apply_cola(1000.0, 2.5, 2024)
        assert cents(rounding.unapply_cola(up, 2.5, 2024)) == "1000.00"


class TestDollarRounding:
    def test_floor_to_dollar_june_1982_on(self) -> None:
        assert rounding.round_to_dollar(2704.5, MonthYear(1983, 1)) == 2704.0
        assert rounding.round_to_dollar(2704.5, MonthYear(1982, 6)) == 2704.0

    def test_no_rounding_before_june_1982(self) -> None:
        assert rounding.round_to_dollar(270.5, MonthYear(1982, 5)) == 270.5
        assert rounding.round_to_dollar(270.5, MonthYear(1975, 12)) == 270.5


class TestStatementRounding:
    def test_pre_2000_five_dollars(self) -> None:
        assert rounding.round_statement(1234.56, 1999) == 1230
        # +0.01 pushes 1239.99 to (float) 1240.0 -> next $5 multiple;
        # the C++ does the identical thing.
        assert rounding.round_statement(1239.99, 1999) == 1240

    def test_2000_on_one_dollar(self) -> None:
        assert rounding.round_statement(1234.56, 2000) == 1234
