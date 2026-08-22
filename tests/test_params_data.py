"""Verifies the generated historical data module against known SSA values
and against the oracle paramdump."""

from pyanypia.params import _data2026 as d
from tests.oracle_util import load_params


def hist(series: tuple[float, ...], first: int, year: int) -> float:
    return series[year - first]


class TestKnownValues:
    def test_awi(self) -> None:
        assert hist(d.FQ, d.FQ_FIRST, 1937) == 1137.96
        assert hist(d.FQ, d.FQ_FIRST, 1976) == 9226.48
        assert hist(d.FQ, d.FQ_FIRST, 2024) == 69846.57

    def test_bases(self) -> None:
        assert hist(d.BASE_OASDI, d.BASE_OASDI_FIRST, 1937) == 3000.0
        assert hist(d.BASE_OASDI, d.BASE_OASDI_FIRST, 2025) == 176100.0
        assert hist(d.BASE_OASDI, d.BASE_OASDI_FIRST, 2026) == 184500.0
        # old-law base diverges from OASDI base after 1978
        assert hist(d.BASE_77, d.BASE_77_FIRST, 2026) < 184500.0

    def test_colas(self) -> None:
        assert hist(d.CPIINC, d.CPIINC_FIRST, 1975) == 8.0
        assert hist(d.CPIINC, d.CPIINC_FIRST, 1980) == 14.3
        assert hist(d.CPIINC, d.CPIINC_FIRST, 2023) == 3.2
        assert hist(d.CPIINC, d.CPIINC_FIRST, 2025) == 2.8

    def test_qc_amounts(self) -> None:
        assert hist(d.QC_AMT, d.QC_AMT_FIRST, 1978) == 250.0
        assert hist(d.QC_AMT, d.QC_AMT_FIRST, 2026) % 10 == 0


class TestMatchesParamdump:
    def test_all_historical_series_match_alt2(self) -> None:
        dump = load_params(2)["years"]
        ranges = {
            "fq": (d.FQ, d.FQ_FIRST, 2024),
            "cpiinc": (d.CPIINC, d.CPIINC_FIRST, 2025),
            "base_oasdi": (d.BASE_OASDI, d.BASE_OASDI_FIRST, 2026),
            "base_77": (d.BASE_77, d.BASE_77_FIRST, 2026),
            "base_hi": (d.BASE_HI, d.BASE_HI_FIRST, 2026),
            "qc_amt": (d.QC_AMT, d.QC_AMT_FIRST, 2026),
            "yoc_amt_specmin": (
                d.YOC_AMT_SPECMIN, d.YOC_AMT_SPECMIN_FIRST, 2026,
            ),
        }
        for key, (series, first, last) in ranges.items():
            for year in range(first, last + 1):
                assert series[year - first] == dump[str(year)][key], (
                    f"{key}[{year}]"
                )
