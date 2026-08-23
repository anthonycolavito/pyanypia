"""Earnings attribution and capping (PiaData::earnProjection etc.).

Railroad and military-service credits are attributed here when present
(ported as needed by the sweeps that exercise them).
"""

from __future__ import annotations

import math

from pyanypia.engine.context import CalcContext
from pyanypia.errors import PIA_IDS_QCTOT0, PIA_IDS_RELERNPOS, PiaError
from pyanypia.worker import BenefitType

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


def earn_projection(ctx: CalcContext) -> None:
    """Attributes earnings (PiaData::earnProjection): entered OASDI
    earnings; railroad/military additions land here when ported."""
    w = ctx.worker
    ctx.earn_oasdi = {}
    ctx.earn_hi = {}
    ctx.ibegin_all = w.ibegin
    ctx.iend_all = w.iend
    if w.has_earnings:
        for yr in range(ctx.ibegin_all, ctx.iend_all + 1):
            ctx.earn_oasdi[yr] = w.earn_oasdi(yr)


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
