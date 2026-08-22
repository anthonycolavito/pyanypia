"""Special minimum method (SpecMin.cpp), post-1978 benefit dates."""

from __future__ import annotations

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import Applicable, MethodState, MethodType
from pyanypia.errors import PiaError
from pyanypia.params import retire_age


def is_applicable(ctx: CalcContext) -> bool:
    assert ctx.worker.benefit_date is not None
    return (
        not ctx.worker.benefit_date < retire_age.AMEND722
        and not ctx.worker.totalize
    )


def calculate(ctx: CalcContext) -> MethodState:
    """SpecMin::calculate (1979-and-later branch; the pre-1979 branch
    needs the old-law PIA table, ported with the PIA-table method)."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.SPEC_MIN, applicable=Applicable.APPLICABLE)
    m.years_total = base.spec_min_years_total_cal(ctx, m, for_spec_min=True)
    excess_years = min(max(m.years_total - 10, 0), 20)
    benefit_date = w.benefit_date
    i1 = benefit_date.year
    year_cpi = (
        i1 if benefit_date.month >= ctx.params.month_beninc(i1) else i1 - 1
    )
    m.year_ben = m.year_ent = year_cpi
    if benefit_date < retire_age.AMEND772:
        raise PiaError(
            0, "pre-1979 special minimum needs the old-law PIA table"
        )
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
