"""Frozen minimum, 1977 Act (FrozMin.cpp).

The 1977 Act froze the old minimum PIA at its December 1978 level of $122
for anyone eligible in 1979-1981; benefit increases apply from the earlier
of the year of entitlement and the year of age 65.
"""

from __future__ import annotations

from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import base
from pyanypia.engine.methods.base import Applicable, MethodState, MethodType
from pyanypia.worker import BenefitType

FROZ_MIN_PIA = 122.0
FROZ_MIN_MFB = 183.0


def is_applicable(ctx: CalcContext) -> bool:
    """FrozMin::isApplicable."""
    return 1978 < ctx.elig_year < 1982 and not ctx.worker.totalize


def calculate(ctx: CalcContext) -> MethodState:
    """FrozMin::calculate."""
    w = ctx.worker
    assert w.benefit_date is not None
    m = MethodState(MethodType.FROZ_MIN, applicable=Applicable.APPLICABLE)
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        year = w.death_date.year
    else:
        assert w.entitlement is not None
        year = w.entitlement.year
    m.year_elig = min(year, ctx.kbirth.year + 65)
    m.year_first = m.year_elig - 1
    m.pia_elig[m.year_first] = FROZ_MIN_PIA
    m.mfb_elig[m.year_first] = FROZ_MIN_MFB
    base.set_year_cpi(ctx, m)
    m.pia_ent = base.apply_colas_elig(
        ctx, m.pia_elig, m.year_elig, w.benefit_date, ctx.elig_year
    )
    m.mfb_ent = base.apply_colas_elig(
        ctx, m.mfb_elig, m.year_elig, w.benefit_date, ctx.elig_year
    )
    return m
