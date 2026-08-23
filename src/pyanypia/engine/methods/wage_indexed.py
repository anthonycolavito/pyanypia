"""Wage-indexed (1977 Act) method — WageIndGeneral.cpp + WageInd.cpp."""

from __future__ import annotations

import math

from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import (
    PERC_MFB,
    PERC_PIA,
    WINDFALL_YEARS,
    Applicable,
    MethodState,
    MethodType,
    WindfallType,
)
from pyanypia.rounding import round_benefit


def is_applicable(ctx: CalcContext) -> bool:
    return ctx.elig_year > 1978 and (
        ctx.worker.iend > 1950 or ctx.worker.totalize
    )


def index_earnings(
    ctx: CalcContext,
    m: MethodState,
    year1: int,
    year2: int,
    year3: int,
    earnings: dict[int, float],
) -> None:
    """WageIndGeneral::indexEarnings — index through year2 (eligYear-2),
    use nominal earnings after; freeze years excluded."""
    avg_wage = ctx.params.fq
    index_year_avg_wage = avg_wage[year2]
    for year in range(year1, year2 + 1):
        if not ctx.freeze_years.is_freeze_year(year):
            m.earn_multiplied[year] = (
                index_year_avg_wage * earnings.get(year, 0.0)
            )
            temp = m.earn_multiplied[year] / avg_wage[year]
            m.earn_indexed[year] = math.floor(temp * 100.0 + 0.5) / 100.0
        else:
            m.earn_multiplied[year] = 0.0
            m.earn_indexed[year] = 0.0
    for year in range(year2, year3 + 1):
        if not ctx.freeze_years.is_freeze_year(year):
            m.earn_multiplied[year] = 0.0
            m.earn_indexed[year] = earnings.get(year, 0.0)
        else:
            m.earn_multiplied[year] = 0.0
            m.earn_indexed[year] = 0.0


def set_portion_aime(
    ame: float, bend_pia: tuple[float, float]
) -> tuple[float, float, float]:
    return (
        min(ame, bend_pia[0]),
        max(0.0, min(ame - bend_pia[0], bend_pia[1] - bend_pia[0])),
        max(ame - bend_pia[1], 0.0),
    )


def aimepia_cal(
    portion_aime: tuple[float, ...], perc_pia: tuple[float, ...], year: int
) -> float:
    total = 0.0
    for perc, portion in zip(perc_pia, portion_aime, strict=True):
        total += perc * portion
    return round_benefit(total, year)


def deconvert_ame(
    ctx: CalcContext,
    piasub: float,
    bend_pia: tuple[float, float],
    perc_pia: tuple[float, ...],
) -> float:
    """WageIndGeneral::deconvertAme — the AIME that would produce `piasub`
    under the present-law two-bend-point formula. A totalization case
    reports this rather than the AIME of the artificial record, since the
    PIA it must correspond to has been pro-rated."""
    temp1 = (perc_pia[0] - perc_pia[1]) * bend_pia[0]
    temp2 = (perc_pia[1] - perc_pia[2]) * bend_pia[1]
    if piasub < perc_pia[0] * bend_pia[0]:
        rv = piasub / perc_pia[0]
    elif piasub < temp1 + perc_pia[1] * bend_pia[1]:
        rv = (piasub - temp1) / perc_pia[1]
    else:
        rv = (piasub - temp1 - temp2) / perc_pia[2]
    return math.ceil(rv) if ctx.elig_year > 1982 else math.floor(rv)


def windfall_perc(
    elig_year: int, benefit_year: int, spec_min_tot: int
) -> tuple[float, ...]:
    """PercPia::setWindfallPerc — modified first PIA percentage."""
    percs = list(PERC_PIA)
    if elig_year < 1985 or spec_min_tot >= WINDFALL_YEARS:
        return tuple(percs)
    rv = (
        percs[0] - 0.5
        if elig_year > 1989
        else percs[0] - 0.10 * float(elig_year - 1985)
    )
    annual_pct = 0.05 if benefit_year >= 1989 else 0.10
    total_pct = annual_pct * float(WINDFALL_YEARS - spec_min_tot)
    if percs[0] - total_pct > rv:
        rv = percs[0] - total_pct
    if rv < 0.0:
        rv = 0.0
    percs[0] = rv
    return tuple(percs)


def windfall_cal(
    ctx: CalcContext, m: MethodState, portion_aime: tuple[float, ...]
) -> None:
    """WageIndGeneral::windfallCal."""
    assert ctx.worker.benefit_date is not None
    m.years_total = base.spec_min_years_total_cal(ctx, m, for_spec_min=False)
    if m.years_total >= WINDFALL_YEARS:
        m.windfall = WindfallType.HAS30YEARS
        return
    perc_wind = windfall_perc(
        ctx.elig_year, ctx.worker.benefit_date.year, m.years_total
    )
    m.pia_windfall = m.pia_elig[m.year_first]
    elig_year = ctx.elig_year - 1
    halfpension = round_benefit(
        0.5 * base.get_pubpen_app(ctx), elig_year
    )
    piaelt = m.pia_elig[m.year_first] - halfpension
    m.pia_elig[m.year_first] = piaelt
    test = aimepia_cal(portion_aime, perc_wind, elig_year)
    if test > piaelt:
        m.windfall = WindfallType.REDUCEDPERC
        m.pia_elig[m.year_first] = test
    else:
        m.windfall = WindfallType.ONEHALFPENSION
        m.pia_elig[m.year_first] = piaelt


def calculate(ctx: CalcContext, *, non_freeze: bool = False) -> MethodState:
    """WageInd::calculate / WageIndNonFreeze::calculate (same algorithm;
    the non-freeze variant uses the non-freeze eligibility year and
    computation period)."""
    assert ctx.worker.benefit_date is not None
    mtype = (
        MethodType.WAGE_IND_NON_FREEZE if non_freeze else MethodType.WAGE_IND
    )
    m = MethodState(mtype, applicable=Applicable.APPLICABLE)
    earnings = ctx.method_earnings()
    year1 = ctx.earn50(with_totalization=True)
    year2 = ctx.earn_year
    year5 = ctx.elig_year_non_freeze if non_freeze else ctx.elig_year
    index_earnings(ctx, m, year1, year5 - 2, year2, earnings)
    n = (
        ctx.comp_period_new_non_freeze.n if non_freeze
        else ctx.comp_period_new.n
    )
    base.order_earnings(m, year1, year2, n)
    base.total_earn_cal(m, year1, year2, n)
    bend_pia = ctx.params.bend_points_pia(year5)
    portion_aime = set_portion_aime(m.ame, bend_pia)
    perc_pia = PERC_PIA
    year4 = year5 - 1
    m.year_first = year4
    m.year_elig = year5
    m.pia_elig[year4] = aimepia_cal(portion_aime, perc_pia, year4)
    if base.wep_app(ctx):
        windfall_cal(ctx, m, portion_aime)
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas(
        ctx, m.pia_elig, year5, ctx.worker.benefit_date
    )
    bend_mfb = ctx.params.bend_points_mfb(year5)
    if ctx.worker.totalize:
        base.prorate(ctx, m)
        m.ame_total = m.ame
        m.ame = deconvert_ame(ctx, m.pia_elig[year4], bend_pia, perc_pia)
    portion_pia_elig = base.set_portion_pia_elig(m.pia_elig[year4], bend_mfb)
    m.mfb_elig[year4] = base.mfb_cal(portion_pia_elig, PERC_MFB, year4)
    m.mfb_ent = base.apply_colas(
        ctx, m.mfb_elig, year5, ctx.worker.benefit_date
    )
    return m


def calculate_reindexed_widow(
    ctx: CalcContext, widow_elig_year: int
) -> MethodState:
    """ReindWid::calculate — widow(er) guarantee PIA (no MFB)."""
    assert ctx.worker.benefit_date is not None
    assert ctx.elig_date is not None
    m = MethodState(MethodType.REIND_WID, applicable=Applicable.APPLICABLE)
    elig_year = min(
        max(ctx.elig_date.year, widow_elig_year), ctx.kbirth.year + 62
    )
    earnings = ctx.earn_oasdi_limited
    year1 = max(ctx.ibegin_all, 1951)
    year2 = ctx.earn_year
    index_earnings(ctx, m, year1, elig_year - 2, year2, earnings)
    n = ctx.comp_period_new.n
    base.order_earnings(m, year1, year2, n)
    base.total_earn_cal(m, year1, year2, n)
    bend_pia = ctx.params.bend_points_pia(elig_year)
    portion_aime = set_portion_aime(m.ame, bend_pia)
    m.year_first = elig_year - 1
    m.year_elig = elig_year
    m.pia_ent = aimepia_cal(portion_aime, PERC_PIA, elig_year - 1)
    m.pia_elig[m.year_first] = m.pia_ent
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas(
        ctx, m.pia_elig, elig_year, ctx.worker.benefit_date
    )
    return m
