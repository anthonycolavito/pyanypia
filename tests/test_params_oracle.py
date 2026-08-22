"""Differential tests: Params vs the compiled oracle's paramdump, for
every year 1937-2105 and every alternative, at the dump's precision."""

import pytest

from pyanypia.dates import MonthYear
from pyanypia.params import present_law, retire_age
from tests.oracle_util import load_params

ALTS = (1, 2, 3)


def f2(x: float) -> str:
    return f"{x:.2f}"


def f6(x: float) -> str:
    return f"{x:.6f}"


@pytest.fixture(scope="module", params=ALTS)
def alt_pair(request):  # type: ignore[no-untyped-def]
    alt = request.param
    return present_law(alt), load_params(alt)


class TestAnnualSeries:
    def test_fq(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            if row["fq"] is not None:
                assert f2(p.fq[int(y)]) == f2(row["fq"]), f"fq[{y}]"

    def test_fqinc(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            if row["fqinc"] is not None and int(y) >= 1938:
                assert f6(p.fqinc[int(y)]) == f6(row["fqinc"]), f"fqinc[{y}]"

    def test_cpiinc(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            if row["cpiinc"] is not None:
                assert f6(p.cpiinc[int(y)]) == f6(row["cpiinc"]), f"cpiinc[{y}]"

    def test_bases(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            yr = int(y)
            for key, series in (
                ("base_oasdi", p.base_oasdi),
                ("base_77", p.base_77),
                ("base_hi", p.base_hi),
            ):
                if row[key] is not None:
                    assert f2(series[yr]) == f2(row[key]), f"{key}[{y}]"

    def test_qc_amt(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            if row["qc_amt"] is not None:
                assert f2(p.qc_amt[int(y)]) == f2(row["qc_amt"]), f"qc[{y}]"

    def test_yoc_amt_specmin(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            if row["yoc_amt_specmin"] is not None and int(y) >= 1951:
                assert f2(p.yoc_amt_specmin[int(y)]) == f2(
                    row["yoc_amt_specmin"]
                ), f"yoc[{y}]"

    def test_bend_points(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["years"].items():
            yr = int(y)
            if row.get("bp_pia") and row["bp_pia"][0] is not None:
                got = p.bend_points_pia(yr)
                assert (f2(got[0]), f2(got[1])) == (
                    f2(row["bp_pia"][0]), f2(row["bp_pia"][1])
                ), f"bp_pia[{y}]"
            if row.get("bp_mfb") and row["bp_mfb"][0] is not None:
                gm = p.bend_points_mfb(yr)
                assert tuple(map(f2, gm)) == tuple(
                    map(f2, row["bp_mfb"])
                ), f"bp_mfb[{y}]"


class TestAges:
    def test_nra_and_dib_max_and_credit(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        _, dump = alt_pair
        for y, row in dump["elig_years"].items():
            yr = int(y)
            if row["nra"] is not None:
                nra = retire_age.full_ret_age(yr)
                assert [nra.years, nra.months] == row["nra"], f"nra[{y}]"
            if row["max_dib_age"] is not None:
                mda = retire_age.max_dib_age(yr)
                assert [mda.years, mda.months] == row["max_dib_age"], (
                    f"max_dib_age[{y}]"
                )
            if row["ret_credit"] is not None:
                assert f6(retire_age.ret_credit(yr)) == f6(row["ret_credit"])

    def test_factor_ar(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        _, dump = alt_pair
        for m, v in enumerate(dump["factor_ar"]):
            if v is not None:
                assert f"{retire_age.factor_ar(m):.8f}" == f"{v:.8f}", f"m={m}"


class TestSpecialMinimum:
    def test_spec_min_pia_december(self, alt_pair) -> None:  # type: ignore[no-untyped-def]
        p, dump = alt_pair
        for y, row in dump["spec_min_pia"].items():
            yr = int(y)
            for yoc in range(1, 21):
                v = row[yoc - 1]
                if v is None:
                    continue
                got = p.get_spec_min_pia(MonthYear(yr, 12), yoc)
                assert f2(got) == f2(v), f"spec_min[{y}][yoc {yoc}]"
