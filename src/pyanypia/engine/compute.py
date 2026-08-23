"""Top-level calculation orchestration, mirroring the anypiab driver flow:
dataCheck -> calculate1 -> calculate2 (earnings, QCs, insured status,
methods) -> piaCal1 -> piaCal2."""

from __future__ import annotations

from datetime import date

from pyanypia.dates import MonthYear
from pyanypia.engine import benefit, earnings, insured
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods import (
    frozen_min,
    old_start,
    pia_table,
    special_min,
    trans_guar,
    wage_indexed,
)
from pyanypia.engine.methods.base import MethodState, MethodType
from pyanypia.params import Params, retire_age
from pyanypia.worker import BenefitType, Worker


class NotYetPorted(NotImplementedError):
    """A case reached a computation method not yet ported."""


def calculate(worker: Worker, params: Params) -> CalcContext:
    from pyanypia.engine import family as fam

    ctx = CalcContext(worker=worker, params=params)
    if worker.benefit_type == BenefitType.SURVIVOR:
        if not worker.family:
            raise NotYetPorted("survivor case needs family members")
        ent_date = worker.family[0].entitlement
    else:
        assert worker.entitlement is not None
        ent_date = worker.entitlement
    secondaries = [fam.SecondaryState(fm) for fm in worker.family]
    ctx.secondaries = secondaries  # type: ignore[attr-defined]
    benefit.data_check(ctx, ent_date)
    fam.data_check_aux(ctx, secondaries)
    # calculate2 (PiaCalAny): attribute earnings, then QCs/insured status
    earnings.earn_projection(ctx)
    earnings.earn_hi_cal(ctx)
    earnings.earn_limit(ctx)
    ctx.early_ret_age = retire_age.early_age_oab(worker.sex, ctx.kbirth)
    _qc_cal(ctx)
    # PiaCal::calculate2
    earnings.earn_total50_cal0(ctx)
    benefit.freeze_years_cal(ctx, ent_date)
    earnings.earn_year_cal(ctx)
    insured.n_cal(ctx, ctx.comp_period_new, ent_date)
    insured.n_non_freeze_cal(ctx, ctx.comp_period_new_non_freeze, ent_date)
    # piaCal: run applicable methods
    methods = _run_methods(ctx, ent_date)
    ctx.methods = methods  # type: ignore[attr-defined]
    benefit.set_high_pia(ctx, methods)
    benefit.set_support_pia(ctx, methods)
    benefit.apply_di_max(ctx, methods)
    benefit.set_high_mfb(ctx, methods)
    benefit.pia_cal2(ctx, methods)
    # re-indexed widow(er) guarantee, then family benefits
    widow_pias: dict[int, float] = {}
    widow_methods: list[MethodState] = []
    for i, s in enumerate(secondaries):
        if s.is_widow() and _reind_wid_applicable(ctx, s):
            wm = wage_indexed.calculate_reindexed_widow(ctx, s.elig_year)
            widow_methods.append(wm)
            widow_pias[i] = wm.pia_ent
    ctx.widow_methods = widow_methods  # type: ignore[attr-defined]
    if secondaries:
        fam.pia_cal3(ctx, secondaries, widow_pias)
    return ctx


def _reind_wid_applicable(
    ctx: CalcContext, s: object
) -> bool:
    """ReindWid::isApplicable."""
    from pyanypia.engine.family import SecondaryState

    assert isinstance(s, SecondaryState)
    w = ctx.worker
    if w.death_date is None:
        return False
    from datetime import date as _date

    try:
        age62 = _date(ctx.kbirth.year + 62, ctx.kbirth.month, ctx.kbirth.day)
    except ValueError:  # Feb 29 birthday-eve
        age62 = _date(ctx.kbirth.year + 62, ctx.kbirth.month, 28)
    if not (
        ctx.elig_year > 1978
        and w.iend > 1950
        and s.is_widow()
        and w.death_date < age62
        and not w.totalize
    ):
        return False
    year = (
        s.member.entitlement.year if s.major_bic == "W" else s.elig_year
    )
    return year > 1984 or w.death_date.year >= 1985


def _qc_cal(ctx: CalcContext) -> None:
    """PiaCal::qcCal — QCs and insured status codes."""
    w = ctx.worker
    earnings.earn_total50_cal0(ctx)
    ctx.qc3750_simp = insured.qc3750_simp_cal(ctx.earn_total50)
    insured.qc_cal(ctx)
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        when = w.death_date
        iswas = (
            2
            if (w.death_date.year > 62 + w.dob.year or w.valdi > 0)
            else 0
        )
    else:
        assert w.entitlement is not None
        when = date(w.entitlement.year, w.entitlement.month, 1)
        iswas = 1
    ctx.fins_code = insured.ins_cal_full(ctx, when, iswas)
    ctx.fins_code2 = insured.fins2_cal(ctx, ctx.fins_code)
    ctx.fins_non_freeze_code = insured.ins_non_freeze_cal_full(
        ctx, when, iswas
    )
    ctx.fins_non_freeze_code2 = insured.fins_non_freeze2_cal(
        ctx, ctx.fins_non_freeze_code
    )
    if ctx.ioasdi == BenefitType.DISABILITY:
        assert w.entitlement is not None
        ctx.dis_ins_code = insured.dis_ins_cal(ctx, w.entitlement, 1)
        ctx.dis_ins_non_freeze_code = insured.dis_ins_non_freeze_cal(
            ctx, w.entitlement, 1
        )


def _run_methods(ctx: CalcContext, ent_date: MonthYear) -> list[MethodState]:
    """PiaCalLC::piaCal — instantiate and run applicable methods, in the
    C++ order (ties in high-PIA selection go to the earlier method)."""
    w = ctx.worker
    assert w.benefit_date is not None
    ctx.high_pia = 0.0
    ctx.high_mfb = 0.0
    ctx.support_pia = 0.0
    ctx.iapps = ctx.iappn = -1
    _set_amend90(ctx, ent_date)
    methods: list[MethodState] = []
    # gates for methods not yet ported are loud, never silently wrong
    if w.totalize:
        raise NotYetPorted("totalization lands in phase 5")
    if old_start.is_applicable(ctx):
        insured.nelapsed_cal(ctx, ctx.comp_period_old, ent_date)
        insured.n_cal(ctx, ctx.comp_period_old, ent_date)
        methods.append(old_start.calculate(ctx, ent_date))
    if pia_table.is_applicable(ctx):
        methods.append(pia_table.calculate(ctx))
    if wage_indexed.is_applicable(ctx):
        methods.append(wage_indexed.calculate(ctx))
    if trans_guar.is_applicable(ctx):
        methods.append(trans_guar.calculate(ctx))
    if special_min.is_applicable(ctx):
        methods.append(special_min.calculate(ctx))
    if frozen_min.is_applicable(ctx):
        methods.append(frozen_min.calculate(ctx))
    if ctx.elig_year > 1978 and (
        w.valdi > 1
        or (
            w.valdi > 0
            and ctx.ioasdi in (BenefitType.OLD_AGE, BenefitType.SURVIVOR)
        )
    ):
        raise NotYetPorted("DIB guarantee lands with dib_v2")
    if _non_freeze_applicable(ctx):
        methods.append(wage_indexed.calculate(ctx, non_freeze=True))
    return methods


def _non_freeze_applicable(ctx: CalcContext) -> bool:
    """WageIndNonFreeze::isApplicable."""
    from pyanypia.engine import insured as ins

    w = ctx.worker
    if ctx.ioasdi == BenefitType.DISABILITY:
        if not ins.is_disability_insured(ctx.dis_ins_non_freeze_code):
            return False
    elif ctx.ioasdi == BenefitType.OLD_AGE:
        if (
            not ins.is_fully_insured(ctx.fins_non_freeze_code)
            or w.valdi == 0
        ):
            return False
    else:
        if (
            not (
                ins.is_fully_insured(ctx.fins_non_freeze_code)
                or ins.is_currently_insured(ctx.fins_non_freeze_code)
            )
            or w.valdi == 0
        ):
            return False
    if w.valdi > 0:
        wp = w.disability_periods[0].waiting_period_start
        wp_year = wp.year if wp is not None else 0
    else:
        wp_year = 0
    ely_temp = min(wp_year, ctx.kbirth.year + 62)
    return ely_temp > 1978 and (w.iend > 1950 or w.totalize)


def _set_amend90(ctx: CalcContext, ent_date: MonthYear) -> None:
    b1 = not ent_date < retire_age.AMEND90
    w = ctx.worker
    b2 = w.valdi == 0 or (
        w.disability_periods[0].cessation is not None
        and w.disability_periods[0].cessation < ent_date
    )
    ctx.amend90 = b1 and b2


METHOD_NAME = {int(t): n for t, n in (
    (MethodType.OLD_START, "OLD_START"),
    (MethodType.PIA_TABLE, "PIA_TABLE"),
    (MethodType.WAGE_IND, "WAGE_IND"),
    (MethodType.TRANS_GUAR, "TRANS_GUAR"),
    (MethodType.SPEC_MIN, "SPEC_MIN"),
    (MethodType.REIND_WID, "REIND_WID"),
    (MethodType.FROZ_MIN, "FROZ_MIN"),
    (MethodType.CHILD_CARE, "CHILD_CARE"),
    (MethodType.DIB_GUAR, "DIB_GUAR"),
    (MethodType.WAGE_IND_NON_FREEZE, "WAGE_IND_NON_FREEZE"),
)}
