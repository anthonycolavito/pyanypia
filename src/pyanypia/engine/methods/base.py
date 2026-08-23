"""Shared PIA-method machinery (PiaMethod base class port)."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.rounding import round_benefit
from pyanypia.worker import BenefitType

YEAR37 = 1937
YEAR50 = 1950
YEAR51 = 1951
YEAR79 = 1979


class MethodType(enum.IntEnum):
    """PiaMethod::pia_type."""

    OLD_START = 0
    PIA_TABLE = 1
    WAGE_IND = 2
    TRANS_GUAR = 3
    SPEC_MIN = 4
    REIND_WID = 5
    FROZ_MIN = 6
    CHILD_CARE = 7
    DIB_GUAR = 8
    WAGE_IND_NON_FREEZE = 9
    NO_PIA_TYPE = 10


METHOD_NAMES = {
    MethodType.OLD_START: "OLD_START",
    MethodType.PIA_TABLE: "PIA_TABLE",
    MethodType.WAGE_IND: "WAGE_IND",
    MethodType.TRANS_GUAR: "TRANS_GUAR",
    MethodType.SPEC_MIN: "SPEC_MIN",
    MethodType.REIND_WID: "REIND_WID",
    MethodType.FROZ_MIN: "FROZ_MIN",
    MethodType.CHILD_CARE: "CHILD_CARE",
    MethodType.DIB_GUAR: "DIB_GUAR",
    MethodType.WAGE_IND_NON_FREEZE: "WAGE_IND_NON_FREEZE",
}


class Applicable(enum.IntEnum):
    """PiaMethod::app_type."""

    NOT_APPLICABLE = 0
    APPLICABLE = 1
    HIGH_PIA = 2
    SUPPORT_PIA = 3


class WindfallType(enum.IntEnum):
    """PiaMethod::WindfallElimType."""

    NOWINDFALLELIM = 0
    HAS30YEARS = 1
    ONEHALFPENSION = 2
    REDUCEDPERC = 3


@dataclass
class MethodState:
    """Computation state of one method (PiaMethod fields)."""

    method: MethodType
    applicable: int = Applicable.NOT_APPLICABLE
    ame: float = 0.0
    ftearn: float = 0.0
    pia_ent: float = 0.0
    mfb_ent: float = 0.0
    pia_elig: dict[int, float] = field(default_factory=dict)
    mfb_elig: dict[int, float] = field(default_factory=dict)
    earn_indexed: dict[int, float] = field(default_factory=dict)
    earn_multiplied: dict[int, float] = field(default_factory=dict)
    iorder: dict[int, int] = field(default_factory=dict)
    year_first: int = 0  # yearCpi[FIRST_YEAR]
    year_elig: int = 0  # yearCpi[YEAR_ELIG]
    year_ben: int = 0  # yearCpi[YEAR_BEN]
    year_ent: int = 0  # yearCpi[YEAR_ENT]
    year_table: int = 0  # yearCpi[YEAR_TABLE]
    windfall: int = WindfallType.NOWINDFALLELIM
    years_total: int = 0  # YOC for special min / WEP
    pia_windfall: float = 0.0
    cap: float = 0.0
    ind_cap: int = 0
    pia_elig_total: float = 0.0  # PIA at eligibility before totalization
    pia_total: float = 0.0  # PIA at entitlement before totalization
    ame_total: float = 0.0  # AME before totalization


def set_year_cpi(ctx: CalcContext, m: MethodState) -> None:
    """PiaMethod::setYearCpi."""
    assert ctx.worker.benefit_date is not None
    year = ctx.worker.benefit_date.year
    m.year_ben = (
        year - 1
        if ctx.worker.benefit_date.month < ctx.params.month_beninc(year)
        else year
    )
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert ctx.worker.death_date is not None
        d = MonthYear.from_date(ctx.worker.death_date)
    else:
        assert ctx.worker.entitlement is not None
        d = ctx.worker.entitlement
    m.year_ent = (
        d.year - 1 if d.month < ctx.params.month_beninc(d.year) else d.year
    )


def apply_colas_elig(
    ctx: CalcContext,
    pia77: dict[int, float],
    year1: int,
    date2: MonthYear,
    catchup_year: int,
) -> float:
    """PiaMethod::applyColasElig — chains benefit increases from year1
    through the increase preceding date2."""
    if year1 < YEAR79:
        return pia77[year1]
    year2 = date2.year
    year3 = (
        year2 - 1 if date2.month < ctx.params.month_beninc(year2) else year2
    )
    for year in range(year1, year3 + 1):
        if ctx.params.is_applicable_cola99(year, date2):
            pia77[year] = ctx.params.apply_cola99(pia77[year - 1])
        else:
            pia77[year] = ctx.params.apply_cola(
                pia77[year - 1], year, catchup_year
            )
    return pia77[year3]


def apply_colas(
    ctx: CalcContext, pia77: dict[int, float], year1: int, date2: MonthYear
) -> float:
    return apply_colas_elig(ctx, pia77, year1, date2, year1)


def prorate(ctx: CalcContext, m: MethodState) -> None:
    """PiaMethod::prorate — a totalization PIA is pro-rated by the share of
    the computation period actually covered by US quarters."""
    assert ctx.worker.benefit_date is not None
    m.pia_elig_total = m.pia_elig.get(m.year_first, 0.0)
    m.pia_total = m.pia_ent
    factor = ctx.qc_total_rel / float(4 * ctx.comp_period_new.n)
    m.pia_ent = round_benefit(factor * m.pia_ent, m.year_ben)
    num_years = m.year_ben - m.year_first
    m.pia_elig[m.year_first] = ctx.params.deconvert_pia(
        ctx.elig_year, num_years, m.pia_ent, ctx.worker.benefit_date
    )


def order_earnings(m: MethodState, first: int, last: int, number: int) -> None:
    """Selects the highest `number` years (PiaMethod::orderEarnings).
    Ties break by year ascending, like the C++ sort of (earning, year)."""
    numtosort = last - first + 1
    if numtosort <= 0:
        return
    wearn = sorted(
        (m.earn_indexed.get(first + i, 0.0), first + i)
        for i in range(numtosort)
    )
    for _, year in wearn[max(numtosort - number, 0):]:
        m.iorder[year] = 1


def total_earn_cal(m: MethodState, first: int, last: int, number: int) -> None:
    """AME/AIME from ordered earnings (PiaMethod::totalEarnCal)."""
    tearn = 0.0
    for yr in range(first, last + 1):
        if m.iorder.get(yr, 0) == 1:
            tearn += m.earn_indexed.get(yr, 0.0)
    m.ftearn = tearn
    m.ame = math.floor(tearn / (float(number) * 12.0))


def set_portion_pia_elig(
    piasub: float, bend_mfb: tuple[float, float, float]
) -> tuple[float, float, float, float]:
    """Portions of the PIA in each MFB-formula interval."""
    return (
        min(piasub, bend_mfb[0]),
        max(0.0, min(piasub - bend_mfb[0], bend_mfb[1] - bend_mfb[0])),
        max(0.0, min(piasub - bend_mfb[1], bend_mfb[2] - bend_mfb[1])),
        max(piasub - bend_mfb[2], 0.0),
    )


PERC_PIA = (0.90, 0.32, 0.15)
PERC_MFB = (1.5, 2.72, 1.34, 1.75)
WINDFALL_YEARS = 30


def mfb_cal(
    portion_pia_elig: tuple[float, float, float, float],
    perc_mfb: tuple[float, float, float, float],
    year: int,
) -> float:
    total = 0.0
    for perc, portion in zip(perc_mfb, portion_pia_elig, strict=True):
        total += perc * portion
    return round_benefit(total, year)


def spec_min_years_cal(
    pre1951: float,
    earnings: dict[int, float],
    year: int,
    yoc_amount: dict[int, float],
    iorder: dict[int, int] | None = None,
) -> int:
    """Years of coverage for special minimum / WEP."""
    totyears = min(14, int(math.floor(pre1951 / 900.0)))
    if iorder is not None:
        iorder[YEAR50] = totyears
    for year1 in range(YEAR51, year + 1):
        if earnings.get(year1, 0.0) > yoc_amount[year1] - 0.009:
            if iorder is not None:
                iorder[year1] = 1
            totyears += 1
    return totyears


def spec_min_years_total_cal(
    ctx: CalcContext, m: MethodState, for_spec_min: bool
) -> int:
    """PiaMethod::specMinYearsTotalCal."""
    pre1951 = ctx.get_earn_total50()
    year = min(ctx.worker.iend, ctx.earn_year)
    if for_spec_min:
        return spec_min_years_cal(
            pre1951, ctx.earn_oasdi, year, ctx.params.yoc_amt_specmin,
            m.iorder,
        )
    return spec_min_years_cal(
        pre1951, ctx.earn_oasdi, year, ctx.params.yoc_amt_windfall
    )


def wep_app(ctx: CalcContext) -> bool:
    """Whether the windfall elimination provision applies (repealed for
    benefits January 2024 or later by the Social Security Fairness Act)."""
    w = ctx.worker
    assert w.benefit_date is not None
    amend118_273 = MonthYear(2024, 1)
    pubpen_date = w.noncovered_pension_date
    if (
        ctx.elig_year > 1985
        and ctx.ioasdi != BenefitType.SURVIVOR
        and (pubpen_date is None or not w.benefit_date < pubpen_date)
        and w.benefit_date < amend118_273
    ):
        pubpen = get_pubpen_app(ctx)
        return pubpen > 0.0 and (
            pubpen_date is None or pubpen_date.year > 1985
        )
    return False


def get_pubpen_app(ctx: CalcContext) -> float:
    """Applicable noncovered pension (PiaData::getPubpenApp)."""
    w = ctx.worker
    assert w.benefit_date is not None
    if w.reservist_pension is not None and w.benefit_date.year > 1994:
        return w.reservist_pension
    return w.noncovered_pension
