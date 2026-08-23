"""Transitional guarantee, 1977 Act (TransGuar.cpp).

For people eligible in 1979-1983 the 1977 Act guarantees no less than the
December 1978 PIA table applied to earnings before the eligibility year.
"""

from __future__ import annotations

from datetime import date

from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import (
    PERC_MFB,
    Applicable,
    MethodState,
    MethodType,
)
from pyanypia.engine.methods.old_pia import OldPia
from pyanypia.params import retire_age
from pyanypia.worker import BenefitType

YEAR51 = 1951
YEAR79 = 1979
TRANS_PERIOD = 5  # transitional guarantee applies for eligibility 1979-1983


def is_applicable(ctx: CalcContext) -> bool:
    """TransGuar::isApplicable."""
    w = ctx.worker
    if ctx.elig_date is None:
        return False
    if not (
        ctx.elig_year >= YEAR79
        and ctx.elig_date.year < YEAR79 + TRANS_PERIOD
        and ctx.ioasdi != BenefitType.DISABILITY
        and not w.totalize
        and w.ibegin < YEAR79
    ):
        return False
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        try:
            age62 = date(ctx.kbirth.year + 62, ctx.kbirth.month, ctx.kbirth.day)
        except ValueError:  # 29 February birthday-eve
            age62 = date(ctx.kbirth.year + 62, ctx.kbirth.month, 28)
        if w.death_date < age62:
            return False
    return True


def calculate(ctx: CalcContext) -> MethodState:
    """TransGuar::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.TRANS_GUAR, applicable=Applicable.APPLICABLE)
    earnings = ctx.earn_oasdi_limited
    # earnings only through the year before eligibility
    year2 = max(ctx.ibegin_all, YEAR51)
    for year1 in range(year2, ctx.elig_year):
        if not ctx.freeze_years.is_freeze_year(year1):
            m.earn_indexed[year1] = earnings.get(year1, 0.0)
    year3 = ctx.elig_year - 1
    year4 = ctx.elig_year
    n = ctx.comp_period_new.n
    base.order_earnings(m, year2, year3, n)
    base.total_earn_cal(m, year2, year3, n)
    # December 1978 PIA, frozen at eligibility
    m.year_first = year3
    m.year_elig = year4
    table = OldPia(ctx, m)
    table.cpi_base(retire_age.AMEND771, True, m.ame, False)
    m.pia_ent = table.piasub
    m.mfb_ent = table.mfbsub
    m.pia_elig[year3] = m.pia_ent
    # MFB comes from the wage-indexed formula, not the old table
    bend_mfb = ctx.params.bend_points_mfb(year4)
    portion_pia_elig = base.set_portion_pia_elig(m.pia_elig[year3], bend_mfb)
    m.mfb_elig[year3] = base.mfb_cal(portion_pia_elig, PERC_MFB, year3)
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas(ctx, m.pia_elig, year4, w.benefit_date)
    m.mfb_ent = base.apply_colas(ctx, m.mfb_elig, year4, w.benefit_date)
    return m
