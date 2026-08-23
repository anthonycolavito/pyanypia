"""Old-start calculation (oldstart.cpp).

For workers with earnings before 1951 the PIA may be computed from a
primary insurance benefit (PIB) based on average monthly wage since 1936,
converted to a PIA through whichever conversion table the law in force at
entitlement provides. Which of the eight old-start methods applies depends
on the entitlement date, the eligibility year and the birth year.
"""

from __future__ import annotations

import enum
import math

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import (
    PERC_MFB,
    Applicable,
    MethodState,
    MethodType,
)
from pyanypia.engine.methods.old_pia import OldPia
from pyanypia.params import _data2026 as d
from pyanypia.params import retire_age
from pyanypia.rounding import round_benefit
from pyanypia.worker import BenefitType

YEAR37 = 1937
YEAR51 = 1951
INC_PER_YEAR = 0.01
AMT_PER_INC_YEAR = 1650.0
BEND_OS = (0, 50, 250)
PERC_OS = (0.40, 0.10)


class OldStartType(enum.IntEnum):
    """OldStart::OldStartType."""

    OS1939 = 0
    OS1950 = 1
    OS1958 = 2
    OS1965 = 3
    OS1967 = 4
    OS1977_78 = 5
    OS1977_79 = 6
    OS1990 = 7


def is_applicable(ctx: CalcContext) -> bool:
    """OldStart::isApplicable — needs pre-1951 quarters of coverage."""
    if ctx.qc_total50 < 1:
        return False
    year = ctx.kbirth.year
    return year < 1929 or (year < 1951 and ctx.qc_total51 < 6)


def method_os_cal(ctx: CalcContext, ent_date: MonthYear) -> OldStartType:
    """OldStart::methodOsCal."""
    amend90 = ctx.amend90
    if ent_date < retire_age.AMEND50:
        return OldStartType.OS1939
    if ent_date < retire_age.AMEND58:
        return OldStartType.OS1950
    if ent_date < retire_age.AMEND653:
        return OldStartType.OS1958
    if ctx.elig_year < 1966:
        return OldStartType.OS1990 if amend90 else OldStartType.OS1958
    if ent_date < retire_age.AMEND671:
        return OldStartType.OS1965
    if ctx.elig_year < 1968 and ctx.ioasdi == BenefitType.SURVIVOR:
        return OldStartType.OS1990 if amend90 else OldStartType.OS1965
    if ctx.kbirth.year < 1916 or ctx.elig_year < 1978:
        if ctx.kbirth.year < 1916:
            return OldStartType.OS1990 if amend90 else OldStartType.OS1967
        return OldStartType.OS1990 if amend90 else OldStartType.OS1965
    return (
        OldStartType.OS1977_78 if ctx.elig_year == 1978
        else OldStartType.OS1977_79
    )


def _assign(m: MethodState, value: float, year1: int, year2: int) -> None:
    """DoubleAnnual::assign of one value over a year range."""
    for year in range(year1, year2 + 1):
        m.earn_indexed[year] = value


def impute_earnings(
    ctx: CalcContext, m: MethodState, method_os: OldStartType
) -> int:
    """OldStart::imputeEarnings — spreads the pre-1951 earnings total over
    years. Returns the divisor used. The pre-1965 methods instead use the
    actual yearly amounts."""
    earnings = ctx.earn_oasdi_limited
    if method_os in (
        OldStartType.OS1939, OldStartType.OS1950,
        OldStartType.OS1958, OldStartType.OS1965,
    ):
        for year in range(YEAR37, 1951):
            m.earn_indexed[year] = earnings.get(year, 0.0)
        return 0
    _assign(m, 0.0, YEAR37, 1950)
    w = ctx.worker
    if method_os == OldStartType.OS1967:
        # the 1967 old-start allocates over 9 years, up to $3000 each
        divisor_os = 9
        i2, i3 = 1942, 1950
    else:
        i3 = 1950
        if ctx.ioasdi == BenefitType.SURVIVOR:
            assert w.death_date is not None
            i3 = min(i3, w.death_date.year - 1)
        if w.valdi == 1:
            i3 = min(i3, ctx.freeze_years.year1 - 1)
        if w.valdi == 2:
            i3 = min(i3, ctx.freeze_years.year3 - 1)
        i3 = max(i3, YEAR37)
        year21 = ctx.kbirth.year + 21
        i2 = min(i3, max(YEAR37, min(year21, 1950)))
        divisor_os = i3 - i2 + 1
    baset = ctx.params.base_oasdi[YEAR37]
    earn_total50 = ctx.get_earn_total50()
    if earn_total50 > baset * float(divisor_os):
        if w.dob.year > YEAR37:
            # assign backwards in wage-base increments, stopping at birth
            i6 = int(math.floor(earn_total50 + 0.001) / baset)
            birthyear = w.dob.year
            if i6 > i3 - birthyear + 1:
                _assign(m, baset, birthyear, i3)
            else:
                _assign(m, baset, i3 - i6 + 1, i3)
                m.earn_indexed[i3 - i6] = earn_total50 - baset * i6
        else:
            i5 = (
                14 if earn_total50 > 14.0 * baset
                else int(math.floor(earn_total50 + 0.001) / baset)
            )
            divisor_os = min(i5, i3 - 1936)
            i2 = max(YEAR37, i3 - divisor_os)
            _assign(m, baset, i2 + 1, i3)
            m.earn_indexed[i2] = (
                earn_total50 - math.floor(earn_total50 / baset) * baset
            )
    else:
        _assign(m, earn_total50 / float(divisor_os), i2, i3)
    return divisor_os


def increment_cal(ctx: CalcContext, method_os: OldStartType) -> int:
    """OldStart::incrementCal — increment years, each worth 1% of the PIB."""
    if method_os in (
        OldStartType.OS1939, OldStartType.OS1950,
        OldStartType.OS1958, OldStartType.OS1965,
    ):
        return sum(
            1 for year in range(YEAR37, 1951)
            if ctx.earn_oasdi_limited.get(year, 0.0) >= 200.0
        )
    if method_os == OldStartType.OS1967:
        return 14
    return min(
        14, max(4, int(ctx.get_earn_total50() / AMT_PER_INC_YEAR))
    )


def calculate(ctx: CalcContext, ent_date: MonthYear) -> MethodState:
    """OldStart::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.OLD_START, applicable=Applicable.APPLICABLE)
    method_os = method_os_cal(ctx, ent_date)
    impute_earnings(ctx, m, method_os)
    yr2 = ctx.earn_year
    # a 1977 old-start on the frozen December 1978 table ignores earnings
    # in the year of eligibility and later
    if method_os == OldStartType.OS1977_79 and yr2 >= ctx.elig_year:
        yr2 = ctx.elig_year - 1
    for yr in range(YEAR51, yr2 + 1):
        if not ctx.freeze_years.is_freeze_year(yr):
            m.earn_indexed[yr] = ctx.earn_oasdi_limited.get(yr, 0.0)
    n = ctx.comp_period_old.n
    base.order_earnings(m, YEAR37, yr2, n)
    base.total_earn_cal(m, YEAR37, yr2, n)
    ame_os = int(m.ame)
    portion_ame = (
        float(min(ame_os, BEND_OS[1])),
        max(float(min(BEND_OS[2] - BEND_OS[1], ame_os - BEND_OS[1])), 0.0),
    )
    table = OldPia(ctx, m)
    table.piasub = sum(
        perc * portion for perc, portion in zip(PERC_OS, portion_ame, strict=True)
    )
    pib = table.piasub
    incyrs = increment_cal(ctx, method_os)
    pib_inc = pib * (1.0 + INC_PER_YEAR * float(incyrs))

    if method_os == OldStartType.OS1939 and w.benefit_date < retire_age.AMEND50:
        _old_start39(m, ame_os, pib_inc)
        return m
    if w.benefit_date < retire_age.AMEND58 and method_os in (
        OldStartType.OS1939, OldStartType.OS1950
    ):
        m.year_first = 1950
        _old_start50(ctx, m, table, pib_inc)
        return m

    # convert the PIB through the 1958 conversion table; the lowest usable
    # entry depends on which table the benefit date falls under
    if w.benefit_date < retire_age.AMEND61:
        i3 = 0
    elif w.benefit_date < retire_age.AMEND672:
        i3 = 7
    else:
        i3 = 11 if w.benefit_date < retire_age.AMEND69 else 12
    while pib_inc > d.PIB58_PIB[i3] and i3 < 62:
        i3 += 1
    m.ame = float(d.PIB58_AME[i3])

    if method_os == OldStartType.OS1977_79:
        # extend below the minimum if eligible in 1982 or later
        if i3 == 0 and ctx.elig_year > 1981:
            m.ame = math.floor(pib_inc * 76.0 / 16.20 + 0.999)
        m.year_first = ctx.elig_year - 1
        m.year_elig = ctx.elig_year
        table.cpi_base(retire_age.AMEND771, True, m.ame, False)
        m.pia_elig[m.year_first] = table.piasub
        if base.wep_app(ctx):
            _windfall(ctx, m)
        base.set_year_cpi(ctx, m)
        m.pia_ent = base.apply_colas(
            ctx, m.pia_elig, ctx.elig_year, w.benefit_date
        )
        bend_mfb = ctx.params.bend_points_mfb(ctx.elig_year)
        portion_pia_elig = base.set_portion_pia_elig(
            m.pia_elig[m.year_first], bend_mfb
        )
        m.mfb_elig[m.year_first] = base.mfb_cal(
            portion_pia_elig, PERC_MFB, ctx.elig_year - 1
        )
        m.mfb_ent = base.apply_colas(
            ctx, m.mfb_elig, ctx.elig_year, w.benefit_date
        )
        return m

    if w.benefit_date < retire_age.AMEND742:
        table.old_pia_cal()
    else:
        i4 = ent_date.year
        m.year_ent = (
            i4 if i4 < YEAR51
            else i4 if ent_date.month >= ctx.params.month_beninc(i4) else i4 - 1
        )
        i4 = w.benefit_date.year
        m.year_ben = (
            i4 if w.benefit_date.month >= ctx.params.month_beninc(i4)
            else i4 - 1
        )
        m.year_first = 1975
        table.cpi_base(w.benefit_date, False, m.ame, False)
    m.pia_ent = table.piasub
    m.mfb_ent = table.mfbsub
    return m


def _windfall(ctx: CalcContext, m: MethodState) -> None:
    """The windfall elimination provision as the old-start applies it: the
    reduction is capped at half the PIA rather than recomputed from a
    modified formula."""
    piaelt = m.pia_elig[m.year_first]
    halfpiaelt = round_benefit(0.5 * piaelt, ctx.elig_year - 1)
    m.pia_windfall = piaelt
    test = round_benefit(0.5 * ctx.worker.noncovered_pension, ctx.elig_year - 1)
    m.pia_elig[m.year_first] = (
        halfpiaelt if halfpiaelt < test else piaelt - test
    )
    m.pia_ent = m.pia_elig[m.year_first]


def _old_start39(m: MethodState, ame_os: int, pib_inc: float) -> None:
    """OldStart::oldStart39Cal — the PIB is the PIA, with a $10 minimum."""
    m.pia_ent = max(10.0, pib_inc)
    mfbsub = 0.8 * float(ame_os)
    mfbsub = min(mfbsub, 85.0)
    mfbsub = min(mfbsub, 2.0 * m.pia_ent)
    m.mfb_ent = max(mfbsub, 20.0)


def _old_start50(
    ctx: CalcContext, m: MethodState, table: OldPia, pib_inc: float
) -> None:
    """OldStart::oldStart50Cal — the 1950 conversion table, then the 1952
    and 1954 Acts' increases on top of it."""
    w = ctx.worker
    assert w.benefit_date is not None
    i1 = 0
    while pib_inc > d.PIB50_PIB[i1] + 0.005 and i1 < 485:
        i1 += 1
    # PIAs in the conversion table start at $20, rising $0.10 per interval
    m.pia_ent = 20.00 + float(i1) / 10.0
    m.pia_elig[m.year_first] = m.pia_ent
    m.mfb_elig[m.year_first] = d.PIB50_MFB[i1]
    if w.benefit_date < retire_age.AMEND52:
        m.mfb_ent = m.mfb_elig[m.year_first]
        return
    # the 1952 increase is the greater of $5 or 12.5%
    test = ctx.params.apply_cola(m.pia_ent, 1952)
    table.piasub = max(test, m.pia_ent + 5.0)
    m.pia_ent = table.piasub
    if w.benefit_date < retire_age.AMEND54:
        m.mfb_ent = d.PIB52_MFB[i1]
        i2 = 0
        while m.pia_ent - 0.005 > d.PIB52_AME[i2]:
            i2 += 1
        m.ame = float(45 + i2)
        return
    if i1 < 329:
        table.piasub = m.pia_ent + 5.0
        m.pia_ent = table.piasub
    else:
        m.pia_ent = d.PIB54_PIA[i1 - 329]
    m.mfb_ent = d.PIB54_MFB[i1]
    i2 = 0
    while m.pia_ent - 0.005 > d.PIB54_AME[i2]:
        i2 += 1
    m.ame = float(55 + i2)
