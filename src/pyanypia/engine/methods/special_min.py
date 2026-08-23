"""Special minimum method (SpecMin.cpp).

From January 1979 the special minimum is a table of PIAs by years of
coverage, carried forward by benefit increases. Before then it was a flat
dollar amount per year of coverage, whose MFB came from the old-law PIA
table.
"""

from __future__ import annotations

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import Applicable, MethodState, MethodType
from pyanypia.engine.methods.old_pia import OldPia
from pyanypia.params import retire_age

SPEC_MIN_MAX_YEARS = 20


def is_applicable(ctx: CalcContext) -> bool:
    assert ctx.worker.benefit_date is not None
    return (
        not ctx.worker.benefit_date < retire_age.AMEND722
        and not ctx.worker.totalize
    )


def spec_min_amount(at: MonthYear) -> float:
    """PiaParams::specMinAmountCalPL — amount per year of coverage."""
    if at < retire_age.AMEND722:
        return 0.00
    if at < retire_age.AMEND741:
        return 8.50
    if at < retire_age.AMEND772:
        return 9.00
    return 11.50


def calculate(ctx: CalcContext) -> MethodState:
    """SpecMin::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.SPEC_MIN, applicable=Applicable.APPLICABLE)
    m.years_total = base.spec_min_years_total_cal(ctx, m, for_spec_min=True)
    amount = spec_min_amount(w.benefit_date)
    excess_years = min(max(m.years_total - 10, 0), SPEC_MIN_MAX_YEARS)
    benefit_date = w.benefit_date
    i1 = benefit_date.year
    year_cpi = (
        i1 if benefit_date.month >= ctx.params.month_beninc(i1) else i1 - 1
    )
    m.year_ben = m.year_ent = year_cpi
    if benefit_date < retire_age.AMEND772:
        # PIA is the dollar amount times years of coverage; the MFB comes
        # from the old-law PIA table at the equivalent AME
        m.year_first = 1975
        m.pia_elig[m.year_first] = float(excess_years) * amount
        m.pia_ent = m.pia_elig[m.year_first]
        m.ame = OldPia(ctx, m).mfb_old_cal(False)
        return m
    m.year_first = 1978
    m.year_elig = 1979
    jan1979 = retire_age.AMEND772
    m.pia_elig[m.year_first] = ctx.params.get_spec_min_pia(
        jan1979, excess_years
    )
    m.mfb_elig[m.year_first] = ctx.params.get_spec_min_mfb(
        jan1979, excess_years
    )
    for i2 in range(m.year_elig, i1):
        m.pia_elig[i2] = ctx.params.get_spec_min_pia(
            MonthYear(i2, 12), excess_years
        )
        m.mfb_elig[i2] = ctx.params.get_spec_min_mfb(
            MonthYear(i2, 12), excess_years
        )
    m.pia_elig[i1] = ctx.params.get_spec_min_pia(benefit_date, excess_years)
    m.mfb_elig[i1] = ctx.params.get_spec_min_mfb(benefit_date, excess_years)
    m.pia_ent = m.pia_elig[i1]
    m.mfb_ent = m.mfb_elig[i1]
    return m
