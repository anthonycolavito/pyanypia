"""Earnings attribution and capping (PiaData::earnProjection etc.).

Railroad and military-service credits are attributed here when present
(ported as needed by the sweeps that exercise them).
"""

from __future__ import annotations

import math

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.errors import PIA_IDS_QCTOT0, PIA_IDS_RELERNPOS, PiaError
from pyanypia.worker import (
    BenefitType,
    EarnProjType,
    EarnType,
    MilitaryService,
)

YEAR37 = 1937


def earn_total50_cal0(ctx: CalcContext) -> None:
    """Sum of regular pre-1951 earnings, capped at 42000."""
    if ctx.ibegin_all < 1937 or ctx.ibegin_all > 1950:
        ctx.earn_total50 = 0.0
    else:
        total = 0.0
        for y in range(ctx.ibegin_all, 1951):
            total += ctx.earn_oasdi.get(y, 0.0)
        ctx.earn_total50 = min(total, 42000.0)


def earn_year_cal(ctx: CalcContext) -> None:
    """Last year of allowable earnings."""
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert ctx.worker.death_date is not None
        ctx.earn_year = ctx.worker.death_date.year
    else:
        assert ctx.worker.benefit_date is not None
        ctx.earn_year = ctx.worker.benefit_date.year - 1


MAXEARN = 9999999.99
DEC1950 = MonthYear(1950, 12)
MS_AMT_PER_MONTH_37_56 = 160.0
MS_AMT_PER_QTR_57_77 = 300.0
MS_AMT_PER_YEAR_78_01 = 1200.0


def _round_earn(wage: float) -> float:
    """AverageWage::round — earnings to the cent."""
    return math.floor(wage * 100.0 + 0.5) / 100.0


def steady_earnings(ctx: CalcContext) -> dict[int, float]:
    """PiaCalAny::earnProSteady — resolves the non-entered earnings types
    into amounts before any projection runs."""
    w = ctx.worker
    p = ctx.params
    out = dict(w.earnings)
    proj = w.projection
    if proj is None or not proj.earn_types:
        return out
    for yr in range(w.ibegin, w.iend + 1):
        kind = proj.earn_types.get(yr, EarnType.ENTERED)
        if kind == EarnType.MAXIMUM:
            # a bit over the base, so that projecting from it in other
            # years still lands on the base
            out[yr] = 3000.0 if yr < 1951 else 1.2 * p.base_oasdi[yr]
        elif kind == EarnType.HIGH:
            out[yr] = min(1.60 * p.get_fq(yr), MAXEARN)
        elif kind == EarnType.AVERAGE:
            out[yr] = min(p.get_fq(yr), MAXEARN)
        elif kind == EarnType.LOW:
            out[yr] = min(0.45 * p.get_fq(yr), MAXEARN)
    return out


def project_earnings(ctx: CalcContext) -> dict[int, float]:
    """EarnProject::project — extends the entered earnings backward and
    forward across the full span of the record."""
    w = ctx.worker
    p = ctx.params
    earnpebs = steady_earnings(ctx)
    proj = w.projection
    if proj is None:
        return earnpebs
    first = proj.first_year or w.ibegin
    last = proj.last_year or w.iend
    out = {yr: earnpebs.get(yr, 0.0) for yr in range(first, last + 1)}
    if proj.proj_back != EarnProjType.NO_PROJ:
        for yr in range(first - 1, w.ibegin - 1, -1):
            base_perc = (
                0.0 if proj.proj_back == EarnProjType.CONSTANT_PROJ
                else p.fqinc[yr + 1]
            )
            factor = 1.0 + (base_perc + proj.perc_back) / 100.0
            amount = _round_earn(out[yr + 1] / factor)
            out[yr] = MAXEARN if amount > MAXEARN else amount
    if proj.proj_fwrd != EarnProjType.NO_PROJ:
        for yr in range(last + 1, w.iend + 1):
            base_perc = (
                0.0 if proj.proj_fwrd == EarnProjType.CONSTANT_PROJ
                else p.fqinc[yr]
            )
            factor = 1.0 + (base_perc + proj.perc_fwrd) / 100.0
            amount = _round_earn(out[yr - 1] * factor)
            out[yr] = MAXEARN if amount > MAXEARN else amount
    return out


def _ms_earn3750(period: MilitaryService) -> float:
    """MilServDates::getEarn3750 — pre-1951 wage credits."""
    if period.start <= DEC1950 and period.start <= period.end:
        last = period.end if period.end <= DEC1950 else DEC1950
        months = last.months_since(period.start) + 1
        return months * MS_AMT_PER_MONTH_37_56
    return 0.0


def _ms_period_earn(period: MilitaryService, year: int) -> float:
    """MilServDates::getEarn — wage credits for one year."""
    if not (period.start.year <= year <= period.end.year):
        return 0.0
    if year > 1977:
        # after 1977 credits track earnings, which are not available here,
        # so the maximum is granted
        return MS_AMT_PER_YEAR_78_01
    firstmonth = 1 if period.start.year < year else period.start.month
    lastmonth = 12 if period.end.year > year else period.end.month
    if year > 1956:
        firstqtr = (firstmonth + 2) // 3
        lastqtr = (lastmonth + 2) // 3
        return (lastqtr - firstqtr + 1) * MS_AMT_PER_QTR_57_77
    return (lastmonth - firstmonth + 1) * MS_AMT_PER_MONTH_37_56


def ms_earn(ctx: CalcContext, year: int) -> float:
    """MilServDatesVec::getEarn, capped to avoid double-counting."""
    total = sum(
        _ms_period_earn(period, year) for period in ctx.worker.military_service
    )
    return min(total, 1200.0 if year > 1956 else 1920.0)


def _ms_period_qc3750(period: MilitaryService) -> int:
    """MilServDates::getQc3750."""
    if period.start > DEC1950:
        return 0
    last = period.end if period.end <= DEC1950 else DEC1950
    firstqc = 4 * period.start.year + (period.start.month - 1) // 3
    lastqc = 4 * last.year + (last.month - 1) // 3
    return lastqc - firstqc + 1


def _ms_period_qcov(period: MilitaryService, year: int) -> int:
    """MilServDates::getQcov."""
    if not (period.start.year <= year <= period.end.year):
        return 0
    firstqc = 0 if period.start.year < year else (period.start.month - 1) // 3
    lastqc = 3 if period.end.year > year else (period.end.month - 1) // 3
    return lastqc - firstqc + 1


def update_mil_serv(ctx: CalcContext) -> None:
    """PiaData::updateMilServ — military quarters and wage credits."""
    ms = ctx.worker.military_service
    ctx.qc3750_ms = sum(_ms_period_qc3750(period) for period in ms)
    ctx.qcov_mil_serv = {
        year: min(4, sum(_ms_period_qcov(period, year) for period in ms))
        for year in range(1951, 1957)
    }
    ctx.earn3750_ms = sum(_ms_earn3750(period) for period in ms)


def earn_projection(ctx: CalcContext) -> None:
    """PiaData::earnProjection — entered and projected OASDI earnings,
    then military wage credits."""
    w = ctx.worker
    ctx.earn_oasdi = {}
    ctx.earn_hi = {}
    ctx.ibegin_all = w.ibegin
    ctx.iend_all = w.iend
    if w.has_earnings:
        projected = project_earnings(ctx)
        for yr in range(ctx.ibegin_all, ctx.iend_all + 1):
            ctx.earn_oasdi[yr] = projected.get(yr, 0.0)
    update_mil_serv(ctx)
    if not w.military_service:
        return
    if ctx.earn3750_ms > 0.0:
        ctx.ibegin_all = min(ctx.ibegin_all, 1950)
        ctx.iend_all = max(ctx.iend_all, 1950)
        ctx.earn_oasdi[1950] = (
            ctx.earn_oasdi.get(1950, 0.0) + ctx.earn3750_ms
        )
    last_year = max(period.end.year for period in w.military_service)
    if last_year >= 1951:
        first_year = min(period.start.year for period in w.military_service)
        if first_year < ctx.ibegin_all or ctx.ibegin_all == 0:
            ctx.ibegin_all = first_year
        ctx.iend_all = max(ctx.iend_all, last_year)
        for yr in range(first_year, last_year + 1):
            credit = ms_earn(ctx, yr) if yr >= 1951 else 0.0
            ctx.earn_oasdi[yr] = ctx.earn_oasdi.get(yr, 0.0) + credit


def earn_hi_cal(ctx: CalcContext) -> None:
    """HI earnings = OASDI earnings + excess HI earnings."""
    w = ctx.worker
    ctx.earn_hi = {}
    if w.has_earnings:
        for yr in range(w.ibegin, w.iend + 1):
            ctx.earn_hi[yr] = (
                ctx.earn_oasdi.get(yr, 0.0) + w.earnings_hi.get(yr, 0.0)
            )


def earn_limit(ctx: CalcContext) -> None:
    """Caps attributed earnings at the wage bases
    (WageBaseGeneral::earnLimit)."""
    ctx.earn_oasdi_limited = {
        yr: min(v, ctx.params.base_oasdi[yr])
        for yr, v in ctx.earn_oasdi.items()
    }
    ctx.earn_hi_limited = {
        yr: min(v, ctx.params.base_hi[yr]) for yr, v in ctx.earn_hi.items()
    }


def set_ibegin_iend_total(ctx: CalcContext) -> None:
    """PiaData::setIbeginTotal / setIendTotal."""
    w = ctx.worker
    ctx.ibegin_total = max(ctx.kbirth.year + 22, YEAR37)
    if w.has_earnings and ctx.ibegin_total > w.ibegin:
        ctx.ibegin_total = w.ibegin
    ctx.iend_total = min(max(ctx.elig_year, w.iend), ctx.earn_year)


def rel_earn_position_cal(ctx: CalcContext) -> float:
    """PiaCal::relEarnPositionCal.

    A totalization case has too few US quarters to compute a PIA from, so
    an artificial full earnings record is built: the worker's average
    earnings relative to the AWI in the years they did work is applied
    across every year from age 22 to eligibility.
    """
    w = ctx.worker
    p = ctx.params
    set_ibegin_iend_total(ctx)
    if ctx.ibegin_total < YEAR37:
        raise PiaError(PIA_IDS_RELERNPOS, "first year of earnings too early")
    # Totalization uses an AWI year that can lag the ones already known.
    awi_year = ctx.elig_year - 2
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        awi_year = w.death_date.year - 2
    else:
        assert w.entitlement is not None and w.benefit_date is not None
        if w.entitlement.year > ctx.elig_year:
            awi_year = w.entitlement.year - 2
        # a recomputation after entitlement moves it again
        if w.benefit_date.year > w.entitlement.year:
            for yr in range(
                w.entitlement.year,
                min(w.benefit_date.year - 1, ctx.iend_total) + 1,
            ):
                if ctx.earn_oasdi.get(yr, 0.0) > 0.005:
                    awi_year = yr - 1
    reptot = 0.0
    qc_total_rel = 0
    ctx.rel_earn_position = {}
    for yr in range(ctx.ibegin_total, ctx.iend_total + 1):
        qcs = ctx.qcov.get(yr, 0)
        if qcs <= 0:
            ctx.rel_earn_position[yr] = 0.0
            continue
        qc_total_rel += qcs
        # wage base proportioned to the quarters actually covered
        test = float(qcs) * p.base_oasdi[yr] / 4.0
        earnstt = (
            0.0 if (yr < w.ibegin or yr > w.iend)
            else ctx.earn_oasdi.get(yr, 0.0)
        )
        temprep = min(earnstt, test) / p.get_fq(min(yr, awi_year))
        ctx.rel_earn_position[yr] = (
            math.floor(temprep * 10000000.0 + 0.5) / 10000000.0
        )
        reptot += ctx.rel_earn_position[yr]
    ctx.qc_total_rel = qc_total_rel
    rv = (
        math.floor(40000000.0 * reptot / float(qc_total_rel) + 0.5)
        / 10000000.0
    )
    temp = ctx.elig_year
    if (
        ctx.ioasdi == BenefitType.SURVIVOR
        and w.death_date is not None
        and w.death_date.year == ctx.elig_year
    ):
        temp = ctx.elig_year + 1
    birth_year = ctx.kbirth.year
    for yr in range(ctx.ibegin_total, ctx.iend_total + 1):
        # every year from age 22 to eligibility, plus any other year with
        # at least one quarter of coverage
        earnstt = 0.0
        if (
            (yr < birth_year + 22 or yr >= temp) and ctx.qcov.get(yr, 0) > 0
        ) or (birth_year + 21 < yr < temp):
            earnstt = rv * p.get_fq(min(yr, awi_year))
        if w.death_date is not None and yr == w.death_date.year:
            qtr = (w.death_date.month + 2) // 3
            earnstt *= qtr / 4.0
        ctx.earn_totalized[yr] = math.floor(100.0 * earnstt + 0.5) / 100.0
    return rv


def earn_total50_cal1(ctx: CalcContext) -> None:
    """PiaData::earnTotal50Cal1 — pre-1951 total of the totalized record."""
    if ctx.ibegin_total < 1937 or ctx.ibegin_total > 1950:
        ctx.earn_total50_totalized = 0.0
    else:
        total = sum(
            ctx.earn_totalized.get(y, 0.0)
            for y in range(ctx.ibegin_total, 1951)
        )
        ctx.earn_total50_totalized = min(total, 42000.0)


def totalize_cal(ctx: CalcContext) -> None:
    """The totalization block of PiaCal::calculate2."""
    if ctx.qc_total == 0:
        raise PiaError(PIA_IDS_QCTOT0, "no quarters of coverage")
    ctx.rel_earn_position_average = rel_earn_position_cal(ctx)
    earn_total50_cal1(ctx)
    ctx.earn_totalized_limited = {
        yr: min(v, ctx.params.base_oasdi[yr])
        for yr, v in ctx.earn_totalized.items()
    }
