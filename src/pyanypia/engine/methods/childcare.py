"""Child-care dropout year method (ChildCareCalc.cpp).

A disabled worker (or a retired one converting from disability) may drop
additional years in which they had a child in care and no earnings, on top
of the ordinary dropout years, up to three in total.
"""

from __future__ import annotations

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base, wage_indexed
from pyanypia.engine.methods.base import (
    PERC_MFB,
    PERC_PIA,
    Applicable,
    MethodState,
    MethodType,
)
from pyanypia.params import retire_age
from pyanypia.worker import BenefitType

YEAR50 = 1950
YEAR51 = 1951
YEAR79 = 1979
MAX_CHILDCARE_DROPOUT_YEARS = 3
# present law allows no earnings at all in a child-care dropout year
CHILDCARE_DROPOUT_AMOUNT = 0.0


def is_applicable(ctx: CalcContext) -> bool:
    """ChildCareCalc::isApplicable."""
    w = ctx.worker
    if not (
        ctx.elig_year >= YEAR79
        and w.iend > YEAR50
        and not w.totalize
        and w.childcare_years
    ):
        return False
    if ctx.ioasdi == BenefitType.OLD_AGE and w.valdi > 0:
        dp = w.disability_periods[0]
        if dp.first_entitlement is None or dp.cessation is None:
            return False
        age61 = MonthYear(w.dob.year + 61, w.dob.month)
        return (
            not dp.first_entitlement < retire_age.AMEND80
            and not dp.cessation < age61
        )
    if ctx.ioasdi == BenefitType.DISABILITY:
        return (
            w.entitlement is not None
            and not w.entitlement < retire_age.AMEND80
        )
    return False


def calculate(ctx: CalcContext) -> MethodState:
    """ChildCareCalc::calculate — the wage-indexed method over a
    computation period shortened by the child-care dropout years."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.CHILD_CARE, applicable=Applicable.APPLICABLE)
    yr1 = max(ctx.ibegin_all, YEAR51)
    yr2 = ctx.earn_year
    wage_indexed.index_earnings(
        ctx, m, yr1, ctx.elig_year - 2, yr2, ctx.earn_oasdi_limited
    )
    i3 = ctx.comp_period_new.n
    base.order_earnings(m, yr1, yr2, i3)
    adjusted_n = i3 - _dropout_cal(ctx, m)
    base.total_earn_cal(m, yr1, yr2, adjusted_n)
    yr5 = ctx.elig_year
    yr4 = yr5 - 1
    bend_pia = ctx.params.bend_points_pia(yr5)
    portion_aime = wage_indexed.set_portion_aime(m.ame, bend_pia)
    m.year_first = yr4
    m.year_elig = yr5
    m.pia_elig[yr4] = wage_indexed.aimepia_cal(portion_aime, PERC_PIA, yr4)
    if base.wep_app(ctx):
        wage_indexed.windfall_cal(ctx, m, portion_aime)
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas(ctx, m.pia_elig, yr5, w.benefit_date)
    bend_mfb = ctx.params.bend_points_mfb(yr5)
    portion_pia_elig = base.set_portion_pia_elig(m.pia_elig[yr4], bend_mfb)
    m.mfb_elig[yr4] = base.mfb_cal(portion_pia_elig, PERC_MFB, yr4)
    m.mfb_ent = base.apply_colas(ctx, m.mfb_elig, yr5, w.benefit_date)
    return m


def _drop_max(ctx: CalcContext) -> int:
    """ChildCareCalc::childCareDropMaxCal — the total of ordinary and
    child-care dropout years is capped at three, and at least two
    computation years must remain."""
    i1 = ctx.comp_period_new.n_drop
    if i1 < MAX_CHILDCARE_DROPOUT_YEARS:
        return min(
            MAX_CHILDCARE_DROPOUT_YEARS - i1, ctx.comp_period_new.n - 2
        )
    return 0


def _dropout_cal(ctx: CalcContext, m: MethodState) -> int:
    """ChildCareCalc::childCareDropoutCal — marks dropped years with -1 in
    `iorder`, so they fall out of the AIME total."""
    drop_max = _drop_max(ctx)
    if drop_max <= 0:
        return 0
    amount = CHILDCARE_DROPOUT_AMOUNT + 0.01
    w = ctx.worker
    earn50 = max(ctx.ibegin_all, YEAR51)
    years = range(earn50, ctx.earn_year + 1)

    def is_empty(yr: int) -> bool:
        return ctx.earn_oasdi_limited.get(yr, 0.0) <= amount

    drop = 0
    for yr in years:
        if (
            m.iorder.get(yr, 0) == 1
            and yr in w.childcare_years
            and is_empty(yr)
        ):
            m.iorder[yr] = -1
            drop += 1
            if drop >= drop_max:
                break
    if drop >= drop_max:
        return drop
    # a selected empty year without a child in care can be swapped out for
    # an unselected empty year with one, freeing another dropout
    count1 = [
        yr for yr in years
        if m.iorder.get(yr, 0) == 1
        and yr not in w.childcare_years
        and is_empty(yr)
    ]
    if not count1:
        return drop
    count2 = [
        yr for yr in years
        if m.iorder.get(yr, 0) == 0
        and yr in w.childcare_years
        and is_empty(yr)
    ]
    if not count2:
        return drop
    numswap = min(len(count1), len(count2), drop_max - drop)
    for i1 in range(numswap):
        m.iorder[count1[i1]] = 0
        m.iorder[count2[i1]] = -1
        drop += 1
    return drop
