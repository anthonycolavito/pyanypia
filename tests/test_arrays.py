import numpy as np
import pytest

from pyanypia import _arrays, _years


def test_as_earnings_from_dict_fills_gaps():
    m, first, single = _arrays.as_earnings({2000: 10.0, 2002: 30.0}, None)
    assert first == 2000 and single
    assert m.tolist() == [[10.0, 0.0, 30.0]]


def test_as_earnings_matrix_requires_first_year():
    with pytest.raises(ValueError, match="first_year"):
        _arrays.as_earnings(np.zeros((2, 3)), None)


def test_negative_earnings_report_rows():
    e = np.zeros((5, 3))
    e[3, 1] = -1.0
    e[4, 0] = -2.0
    with pytest.raises(ValueError, match=r"earnings: negative in 2 row\(s\); first at row 3"):
        _arrays.as_earnings(e, 2000)


def test_earnings_years_must_be_in_range():
    with pytest.raises(ValueError, match="1937-2105"):
        _arrays.as_earnings(np.zeros(5), 2104)


def test_year_lookup_out_of_range():
    series = _years.to_array({y: float(y) for y in range(1937, 2106)})
    assert _years.at(series, np.array([1937, 2105]), "awi").tolist() == [1937.0, 2105.0]
    with pytest.raises(ValueError, match="awi: year outside 1937-2105"):
        _years.at(series, 2106, "awi")


def test_year_lookup_missing_value():
    series = _years.to_array({2000: 1.0})
    with pytest.raises(ValueError, match="cola: no value for year 1999"):
        _years.at(series, 1999, "cola")


def test_as_int_rejects_fractional():
    assert _arrays.as_int("claim_age", 744.0).dtype.kind == "i"
    with pytest.raises(ValueError, match="claim_age: must be whole numbers"):
        _arrays.as_int("claim_age", 744.5)


def test_out_scalarizes():
    assert _arrays.out(np.array(3.0)) == 3.0 and isinstance(_arrays.out(np.array(3.0)), float)
    assert isinstance(_arrays.out(np.array([3.0])), np.ndarray)
