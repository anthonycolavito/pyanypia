"""Projection formulas for law parameters.

Transliterated from avgwg.cpp, awinc.cpp, wbgenrl.cpp, bendpia.cpp,
bendmfb.cpp, qcamt.cpp and piaparms.cpp (updateYocAmountSpecMin,
PiaParamsLC::projectSpecMin). Operation order and rounding are copied
exactly; do not simplify the arithmetic.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pyanypia.rounding import apply_cola as _ba_apply_cola
from pyanypia.rounding import round_benefit

YEAR37 = 1937
YEAR51 = 1951
YEAR79 = 1979
AUTO_YEAR = 1978  # first year of automatic (earnings-based) QC amounts
MAXEARN = 99999999.0
SPEC_MIN_MAX_YEARS = 20  # usable years of coverage in excess of 10


def round_wage(value: float) -> float:
    """AverageWage::round — earnings amounts round to 2 decimals."""
    return math.floor(value * 100.0 + 0.5) / 100.0


def hist_fqinc(fq: dict[int, float], first: int, last: int) -> dict[int, float]:
    """Awinc::project from average wages: percent increases."""
    out: dict[int, float] = {}
    for y in range(first, last + 1):
        if fq[y - 1] > 1.0:
            out[y] = 100.0 * (fq[y] / fq[y - 1] - 1.0)
    return out


def project_fq(
    fq: dict[int, float], fqinc: dict[int, float], first: int, last: int
) -> None:
    """AverageWage::project — chains fq forward from first..last using
    percentage increases, rounding to cents each year (in place)."""
    for y in range(first, last + 1):
        fq[y] = round_wage(fq[y - 1] * (fqinc[y] / 100.0 + 1.0))


def project_base_after_ad_hoc(
    base: dict[int, float],
    fq: dict[int, float],
    cpi: dict[int, float],
    last_ad_hoc: int,
    last: int,
) -> None:
    """WageBaseGeneral::projectLC — the years after an ad hoc wage-base
    window.

    Each one indexes off the last ad hoc base and the wage ratio to two
    years before it, rather than chaining off the year before, so the
    rounding to a multiple of $300 is applied once against the anchor
    instead of accumulating.
    """
    anchor = base[last_ad_hoc]
    for yr in range(last_ad_hoc + 1, last + 1):
        if cpi.get(yr - 1, 0.0) < 0.1:
            # no benefit increase: base equals the last one set
            base[yr] = base[yr - 1]
            continue
        factor = fq[yr - 2] / fq[last_ad_hoc - 2]
        baseun = anchor * factor
        # rounded to a multiple of $300, and never a decrease
        base[yr] = max(300.0 * math.floor(baseun / 300.0 + 0.5), base[yr - 1])


def project_base(
    base: dict[int, float],
    fq: dict[int, float],
    cpi: dict[int, float],
    wage_base_ind: int,
    first: int,
    last: int,
) -> None:
    """WageBaseGeneral::project — projects a wage-base series in place.

    wage_base_ind: 0 = present-law OASDI, 2 = old-law (1977), 3 = HI.
    """
    defcomp = 0.0149249
    y = first
    while y <= last:
        iflag = 0
        while cpi.get(y + iflag - 1, 0.0) < 0.1:
            # no benefit increase: base frozen at previously set level
            base[y + iflag] = base[y - 1]
            iflag += 1
            if y + iflag > last:
                return
        i3 = y + iflag
        baseun = base[y - 1]
        if i3 < 1995:
            for i2 in range(0, iflag + 1):
                yr = y + i2
                if wage_base_ind != 1 and 1989 < yr < 1993:
                    if yr == 1990:
                        factor = fq[yr - 2] / fq[yr - 3] + 0.02
                    elif yr == 1991:
                        factor = (fq[yr - 2] + 0.02 * fq[yr - 3]) / (
                            fq[yr - 3] + 0.02 * fq[yr - 4]
                        )
                    else:
                        factor = (fq[yr - 2] * (1.0 + defcomp)) / (
                            fq[yr - 3] + 0.02 * fq[yr - 4]
                        )
                else:
                    factor = fq[yr - 2] / fq[yr - 3]
                baseun = (baseun + 0.001) * factor
        else:
            factor = fq[i3 - 2] / fq[1992]
            if wage_base_ind == 2:
                baseun = 45000.0 * factor
            else:
                baseun = 60600.0 * factor if wage_base_ind < 2 else MAXEARN
        if wage_base_ind != 2 and YEAR79 <= i3 < 1982:
            # ad hoc increases 1979-81
            base[i3] = {1979: 22900.0, 1980: 25900.0}.get(i3, 29700.0)
        else:
            base[i3] = 300.0 * math.floor(baseun / 300.0 + 0.5)
        if base[i3] < base[i3 - 1]:
            base[i3] = base[i3 - 1]
        y = i3 + 1


def project_qc_amounts(
    fq: dict[int, float], first: int, last: int
) -> dict[int, float]:
    """Qcamt: $50 through 1977, then indexed from $250 (1978), rounded to
    the nearest-ish $10 per the exact C++ expression."""
    out: dict[int, float] = {y: 50.0 for y in range(YEAR37, AUTO_YEAR)}
    out[AUTO_YEAR] = 250.0
    for y in range(max(AUTO_YEAR, first), last + 1):
        factor = fq[y - 2] / fq[AUTO_YEAR - 2]
        k = int((factor * 250.0 + 4.99) / 10.0)
        out[y] = float(k) * 10.0
        # QC amount never decreases
        if out[y] < out[y - 1]:
            out[y] = out[y - 1]
    return out


BP_PIA_1979 = (180.0, 1085.0)
BP_MFB_1979 = (230.0, 332.0, 433.0)


def bend_points_pia(elig_year: int, fq_bppia: dict[int, float]
                    ) -> tuple[float, float]:
    """BendPia::project — PIA formula bend points for an eligibility year."""
    temp = fq_bppia[elig_year - 2] / fq_bppia[1977]
    return (
        math.floor(BP_PIA_1979[0] * temp + 0.5),
        math.floor(BP_PIA_1979[1] * temp + 0.5),
    )


def bend_points_mfb(elig_year: int, fq: dict[int, float]
                    ) -> tuple[float, float, float]:
    """BendMfb::project — MFB formula bend points for an eligibility year."""
    temp = fq[elig_year - 2] / fq[1977]
    return (
        math.floor(BP_MFB_1979[0] * temp + 0.5),
        math.floor(BP_MFB_1979[1] * temp + 0.5),
        math.floor(BP_MFB_1979[2] * temp + 0.5),
    )


def yoc_amounts_special_min(
    base77: dict[int, float], last: int
) -> tuple[dict[int, float], dict[int, float]]:
    """PiaParams::updateYocAmountSpecMin — amounts of earnings required for
    a year of coverage: (windfall series, special-minimum series)."""
    windfall = {y: 0.25 * base77[y] for y in range(YEAR51, last + 1)}
    specmin = {
        y: (0.25 if y < 1991 else 0.15) * base77[y]
        for y in range(YEAR51, last + 1)
    }
    return windfall, specmin


def project_special_min(
    cpiinc: dict[int, float],
    last_year: int,
    *,
    amount_at: Callable[[int], float] | None = None,
    split_year: int | None = None,
) -> tuple[
    list[dict[int, float]], list[dict[int, float]],
    list[float], list[float], list[float], list[float],
]:
    """PiaParamsLC::projectCpiinc and projectSpecMin: returns (pia tables,
    mfb tables, Aug-2001 pias, Aug-2001 mfbs, changed-year pias,
    changed-year mfbs), each indexed by years-of-coverage-minus-11 (0..19).

    A reform setting a new amount per year of coverage restarts the table
    at its first year instead of carrying the old one forward, so the
    projection runs in two ranges. The amounts for the first year of the
    change are kept aside: they are what applies in the months of that
    year before its benefit increase.
    """
    amount_of = amount_at if amount_at is not None else (lambda _year: 11.50)
    if split_year is not None and split_year <= 2002:
        raise ValueError(
            f"special-minimum change from {split_year}: the calculator "
            f"recalculates 1999-2001 from table entries the first range "
            f"would not have written, so a change before 2003 has no "
            f"well-defined answer to match"
        )

    pia_tables: list[dict[int, float]] = [
        {} for _ in range(SPEC_MIN_MAX_YEARS)
    ]
    mfb_tables: list[dict[int, float]] = [
        {} for _ in range(SPEC_MIN_MAX_YEARS)
    ]
    pia_2001: list[float] = []
    mfb_2001: list[float] = []
    pia_extra: list[float] = [0.0] * SPEC_MIN_MAX_YEARS
    mfb_extra: list[float] = [0.0] * SPEC_MIN_MAX_YEARS

    def apply_cola(amt: float, year: int) -> float:
        return _ba_apply_cola(amt, cpiinc[year], year)

    def apply_cola_mfb(mfb: float, year: int, pia: float) -> float:
        rv = _ba_apply_cola(mfb, cpiinc[year], year)
        mfbt = round_benefit(1.5 * pia, year)
        return max(rv, mfbt)

    def project_range(base_year: int, last: int) -> None:
        amount_per_year = amount_of(base_year)  # specMinAmountCal(Jan base)
        for num_years in range(SPEC_MIN_MAX_YEARS):
            pia = (num_years + 1) * amount_per_year
            mfb = round_benefit(1.5 * pia, base_year)
            da_pia = pia_tables[num_years]
            da_mfb = mfb_tables[num_years]
            if base_year == YEAR79:
                da_pia[1978] = pia
                da_mfb[1978] = mfb
                for year in range(YEAR79, min(2000, last) + 1):
                    pia = apply_cola(pia, year)
                    da_pia[year] = pia
                    mfb = apply_cola_mfb(mfb, year, pia)
                    da_mfb[year] = mfb
                # recalculate December 1999 with the extra 0.1 percent
                pia1999 = _ba_apply_cola(da_pia[1998], cpiinc[1999] + 0.1, 1999)
                mfb1999 = max(
                    _ba_apply_cola(da_mfb[1998], cpiinc[1999] + 0.1, 1999),
                    round_benefit(1.5 * pia1999, 1999),
                )
                # December 2000 values, effective August 2001
                pia1999 = apply_cola(pia1999, 2000)
                pia_2001.append(pia1999)
                mfb1999 = apply_cola_mfb(mfb1999, 2000, pia)
                mfb_2001.append(mfb1999)
                # December 2001
                pia = apply_cola(pia1999, 2001)
                da_pia[2001] = pia
                mfb = apply_cola_mfb(mfb1999, 2001, pia)
                da_mfb[2001] = mfb
            else:
                # the changed amount, before that year's benefit increase
                pia_extra[num_years] = pia
                mfb_extra[num_years] = mfb
            for year in range(max(2002, base_year), last + 1):
                pia = apply_cola(pia, year)
                da_pia[year] = pia
                mfb = apply_cola_mfb(mfb, year, pia)
                da_mfb[year] = mfb

    if split_year is None:
        project_range(YEAR79, last_year)
    else:
        project_range(YEAR79, split_year - 1)
        project_range(split_year, last_year)
    return pia_tables, mfb_tables, pia_2001, mfb_2001, pia_extra, mfb_extra
