"""Earnings attribution and capping (PiaData::earnProjection etc.).

Railroad and military-service credits are attributed here when present
(ported as needed by the sweeps that exercise them).
"""

from __future__ import annotations

from pyanypia.engine.context import CalcContext
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
