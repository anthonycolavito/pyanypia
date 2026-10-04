"""Projection formulas for derived policy series (scalar, run once per Policy).

Transliterated from anypia_engine's params/projection.py (avgwg.cpp,
wbgenrl.cpp, qcamt.cpp, piaparms.cpp). Operation order and rounding are
copied exactly; do not simplify the arithmetic.
"""

from __future__ import annotations

import math

YEAR79 = 1979
AUTO_YEAR = 1978  # first year of earnings-indexed QC amounts
MAXEARN = 99999999.0
SPEC_MIN_MAX_YEARS = 20  # usable years of coverage in excess of 10


def round_wage(value: float) -> float:
    return math.floor(value * 100.0 + 0.5) / 100.0


def round_benefit(amount: float, year: int) -> float:
    if year >= 1982:
        return math.floor(10.0 * amount + 0.0005) / 10.0
    q = 0.009 if year >= 1973 else 0.499
    x100 = math.fmod(amount * 100.0, 10.0)
    if x100 < q:
        return amount - x100 / 100.0
    return amount + (0.10 - x100 / 100.0)


def apply_cola(amount: float, percent: float, year: int) -> float:
    amount *= 1.0 + percent / 100.0
    return round_benefit(amount, year)


def project_fq(fq: dict[int, float], fqinc: dict[int, float], first: int, last: int) -> None:
    """AverageWage::project — chains the AWI forward by percentage increases."""
    for y in range(first, last + 1):
        fq[y] = round_wage(fq[y - 1] * (fqinc[y] / 100.0 + 1.0))


def project_base(
    base: dict[int, float],
    fq: dict[int, float],
    cpi: dict[int, float],
    wage_base_ind: int,
    first: int,
    last: int,
) -> None:
    """WageBaseGeneral::project. wage_base_ind: 0 = OASDI, 2 = old-law (1977)."""
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
    fq: dict[int, float], last: int, base: float = 250.0
) -> dict[int, float]:
    """Qcamt: $50 through 1977, then indexed from `base` in 1978."""
    out: dict[int, float] = {y: 50.0 for y in range(1937, AUTO_YEAR)}
    out[AUTO_YEAR] = base
    for y in range(AUTO_YEAR, last + 1):
        factor = fq[y - 2] / fq[AUTO_YEAR - 2]
        k = int((factor * base + 4.99) / 10.0)
        out[y] = float(k) * 10.0
        # QC amount never decreases
        if out[y] < out[y - 1]:
            out[y] = out[y - 1]
    return out


def project_special_min(
    cpiinc: dict[int, float], last_year: int, amount: float
) -> tuple[list[dict[int, float]], list[dict[int, float]], list[float], list[float]]:
    """PiaParamsLC::projectSpecMin from January 1979: (pia tables, mfb tables,
    Aug-2001 pias, Aug-2001 mfbs), indexed by years-of-coverage-minus-11."""
    pia_tables: list[dict[int, float]] = [{} for _ in range(SPEC_MIN_MAX_YEARS)]
    mfb_tables: list[dict[int, float]] = [{} for _ in range(SPEC_MIN_MAX_YEARS)]
    pia_2001: list[float] = []
    mfb_2001: list[float] = []

    def cola(amt: float, year: int) -> float:
        return apply_cola(amt, cpiinc[year], year)

    def cola_mfb(mfb: float, year: int, pia: float) -> float:
        return max(apply_cola(mfb, cpiinc[year], year), round_benefit(1.5 * pia, year))

    for num_years in range(SPEC_MIN_MAX_YEARS):
        pia = (num_years + 1) * amount
        mfb = round_benefit(1.5 * pia, YEAR79)
        da_pia, da_mfb = pia_tables[num_years], mfb_tables[num_years]
        da_pia[1978], da_mfb[1978] = pia, mfb
        for year in range(YEAR79, min(2000, last_year) + 1):
            pia = cola(pia, year)
            da_pia[year] = pia
            mfb = cola_mfb(mfb, year, pia)
            da_mfb[year] = mfb
        # recalculate December 1999 with the extra 0.1 percent
        pia1999 = apply_cola(da_pia[1998], cpiinc[1999] + 0.1, 1999)
        mfb1999 = max(
            apply_cola(da_mfb[1998], cpiinc[1999] + 0.1, 1999),
            round_benefit(1.5 * pia1999, 1999),
        )
        # December 2000 values, effective August 2001. The MFB is floored
        # against the uncorrected `pia`, as the C++ does.
        pia1999 = cola(pia1999, 2000)
        pia_2001.append(pia1999)
        mfb1999 = cola_mfb(mfb1999, 2000, pia)
        mfb_2001.append(mfb1999)
        # December 2001
        pia = cola(pia1999, 2001)
        da_pia[2001] = pia
        mfb = cola_mfb(mfb1999, 2001, pia)
        da_mfb[2001] = mfb
        for year in range(2002, last_year + 1):
            pia = cola(pia, year)
            da_pia[year] = pia
            mfb = cola_mfb(mfb, year, pia)
            da_mfb[year] = mfb
    return pia_tables, mfb_tables, pia_2001, mfb_2001
