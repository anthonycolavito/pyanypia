"""New-start calculation, pre-1977 Act (PiaTable.cpp)."""

from __future__ import annotations

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import Applicable, MethodState, MethodType
from pyanypia.engine.methods.old_pia import OldPia
from pyanypia.params import retire_age
from pyanypia.worker import BenefitType

YEAR37 = 1937
YEAR51 = 1951
YEAR79 = 1979


def is_applicable(ctx: CalcContext) -> bool:
    """PiaTable::isApplicable."""
    w = ctx.worker
    assert w.benefit_date is not None
    if not (ctx.elig_year < YEAR79 and not w.benefit_date < retire_age.AMEND52):
        return False
    if ctx.ioasdi != BenefitType.SURVIVOR:
        return True
    assert w.death_date is not None
    return not MonthYear.from_date(w.death_date) < retire_age.AMEND52


def calculate(ctx: CalcContext) -> MethodState:
    """PiaTable::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.PIA_TABLE, applicable=Applicable.APPLICABLE)
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        when = MonthYear.from_date(w.death_date)
    else:
        assert w.entitlement is not None
        when = w.entitlement
    i1 = when.year
    m.year_ent = (
        i1 if i1 < YEAR51
        else i1 if when.month >= ctx.params.month_beninc(i1) else i1 - 1
    )
    i1 = w.benefit_date.year
    m.year_ben = (
        i1 if w.benefit_date.month >= ctx.params.month_beninc(i1) else i1 - 1
    )
    m.year_first = 1975
    earnings = ctx.earn_oasdi_limited
    year1 = max(ctx.ibegin_all, YEAR51)
    year2 = ctx.earn_year
    for yr in range(year1, year2 + 1):
        if not ctx.freeze_years.is_freeze_year(yr):
            m.earn_indexed[yr] = earnings.get(yr, 0.0)
    n = ctx.comp_period_new.n
    base.order_earnings(m, year1, year2, n)
    base.total_earn_cal(m, year1, year2, n)
    table = OldPia(ctx, m)
    if w.benefit_date < retire_age.AMEND742:
        table.old_pia_cal()
    else:
        table.cpi_base(w.benefit_date, False, m.ame, True)
    m.pia_ent = table.piasub
    m.mfb_ent = table.mfbsub
    return m
