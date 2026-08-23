"""Disability guarantee (DibGuar.cpp).

A worker whose disability ceased and who later becomes entitled again —
to old-age, to survivor benefits, or to a second period of disability —
is guaranteed no less than the PIA in force when the prior disability
ceased, carried forward by benefit increases.
"""

from __future__ import annotations

import enum

from pyanypia.dates import MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import (
    PERC_MFB,
    Applicable,
    MethodState,
    MethodType,
)
from pyanypia.params import retire_age
from pyanypia.worker import BenefitType, Worker

DEC1995 = MonthYear(1995, 12)


class ConvertedMfbType(enum.IntEnum):
    """DibGuar::ConvertedMfbType — how the cessation MFB is carried over."""

    POST1995_NOCHANGE = 0
    POST1995_DECONVERTED = 1
    PRE1996_PRE1979_LAST12 = 2
    PRE1996_POST1978_LAST12 = 3
    PRE1996_NOTLAST12 = 4


def is_applicable(ctx: CalcContext) -> bool:
    """DibGuar::isApplicable."""
    w = ctx.worker
    return ctx.elig_year > 1978 and (
        w.valdi > 1
        or (
            w.valdi > 0
            and ctx.ioasdi in (BenefitType.OLD_AGE, BenefitType.SURVIVOR)
        )
    )


def earliest_ent_date(w: Worker) -> MonthYear:
    """WorkerDataGeneral::getEarliestEntDate."""
    if w.valdi > 1:
        first = w.disability_periods[w.valdi - 1].first_entitlement
        assert first is not None
        return first
    if (
        w.benefit_type in (BenefitType.OLD_AGE, BenefitType.SURVIVOR)
        and w.valdi == 1
    ):
        first = w.disability_periods[0].first_entitlement
        assert first is not None
        return first
    assert w.entitlement is not None
    return w.entitlement


def calculate(ctx: CalcContext) -> MethodState:
    """DibGuar::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.DIB_GUAR, applicable=Applicable.APPLICABLE)
    # a disability case guarantees against the *prior* period; anything
    # else guarantees against the most recent one
    which = 1 if ctx.ioasdi == BenefitType.DISABILITY else 0
    dp = w.disability_periods[which]
    assert dp.cessation is not None
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        ent_death = MonthYear.from_date(w.death_date)
    else:
        assert w.entitlement is not None
        ent_death = w.entitlement
    # benefit increases start at the prior cessation if benefits were
    # continuous within a year, otherwise at the new entitlement
    colas_apply = ent_death.months_since(dp.cessation) < 13
    date_cpi = dp.cessation if colas_apply else ent_death
    year = date_cpi.year
    m.year_elig = (
        year if date_cpi.month <= ctx.params.month_beninc(year) else year + 1
    )
    m.year_first = m.year_elig - 1
    m.pia_elig[m.year_first] = dp.cessation_pia
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas_elig(
        ctx, m.pia_elig, m.year_elig, w.benefit_date, ctx.elig_year
    )
    di_max_applies = (
        dp.onset.year > 1978
        and not earliest_ent_date(w) < retire_age.AMEND80
    )
    prior_elig_year = dp.onset.year
    kind = _converted_mfb_type(
        ctx, ent_death, colas_apply, di_max_applies, prior_elig_year
    )
    m.mfb_elig[m.year_first] = _cessation_mfb(ctx, m, dp, kind, prior_elig_year)
    m.mfb_ent = base.apply_colas_elig(
        ctx, m.mfb_elig, m.year_elig, w.benefit_date, ctx.elig_year
    )
    return m


def _converted_mfb_type(
    ctx: CalcContext,
    ent_death: MonthYear,
    colas_apply: bool,
    di_max_applies: bool,
    prior_elig_year: int,
) -> ConvertedMfbType:
    """DibGuar::convertedMfbTypeCal."""
    if ent_death > DEC1995:
        if di_max_applies and ctx.ioasdi != BenefitType.DISABILITY:
            # new benefit is OASI and the disability maximum applied, so
            # the MFB must be deconverted to the prior eligibility year
            return ConvertedMfbType.POST1995_DECONVERTED
        return ConvertedMfbType.POST1995_NOCHANGE
    if colas_apply:
        return (
            ConvertedMfbType.PRE1996_PRE1979_LAST12 if prior_elig_year < 1979
            else ConvertedMfbType.PRE1996_POST1978_LAST12
        )
    return ConvertedMfbType.PRE1996_NOTLAST12


def _cessation_mfb(
    ctx: CalcContext,
    m: MethodState,
    dp: object,
    kind: ConvertedMfbType,
    prior_elig_year: int,
) -> float:
    """DibGuar::cessationMfbCal."""
    from pyanypia.worker import DisabilityPeriod

    assert isinstance(dp, DisabilityPeriod)
    assert dp.cessation is not None
    if kind == ConvertedMfbType.POST1995_NOCHANGE:
        return dp.cessation_mfb
    if kind == ConvertedMfbType.POST1995_DECONVERTED:
        num_years = dp.cessation.year - prior_elig_year
        raw_pia = ctx.params.deconvert_pia(
            prior_elig_year, num_years, dp.cessation_pia, dp.cessation
        )
        bend_mfb = ctx.params.bend_points_mfb(prior_elig_year)
        portion = base.set_portion_pia_elig(raw_pia, bend_mfb)
        m.mfb_elig[prior_elig_year - 1] = base.mfb_cal(
            portion, PERC_MFB, prior_elig_year - 1
        )
        return base.apply_colas(
            ctx, m.mfb_elig, prior_elig_year, dp.cessation.month_before()
        )
    # pre-1996 entitlement: rebuild the MFB from the cessation PIA
    bend_mfb = ctx.params.bend_points_mfb(ctx.elig_year)
    portion = base.set_portion_pia_elig(dp.cessation_pia, bend_mfb)
    return base.mfb_cal(portion, PERC_MFB, ctx.elig_year - 1)
