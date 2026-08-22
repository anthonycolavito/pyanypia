"""Data checks, reduction/credit application, and benefit computation
(PiaCal::dataCheck, ardriCal, piaCal1, piaCal2, setPifc)."""

from __future__ import annotations

from pyanypia.dates import MonthYear
from pyanypia.engine import insured
from pyanypia.engine.context import CalcContext
from pyanypia.engine.methods.base import (
    MethodState,
    MethodType,
    WindfallType,
)
from pyanypia.errors import PiaError
from pyanypia.params import retire_age
from pyanypia.rounding import round_benefit, round_to_dollar
from pyanypia.worker import BenefitType

# resource ids for entitlement-age errors (Resource.h)
PIA_IDS_ARDRI1 = 61288
PIA_IDS_ARDRI2 = 61289
PIA_IDS_ARDRI7 = 61294
PIA_IDS_ARDRI8 = 61295
PIA_IDS_ARDRI9 = 61296

JAN_1937 = MonthYear(1937, 1)


def month_year_of(kbirth_year: int, kbirth_month: int) -> MonthYear:
    return MonthYear(kbirth_year, kbirth_month)


def add_age(my: MonthYear, years: int, months: int) -> MonthYear:
    return my.add_months(years * 12 + months)


def data_check(ctx: CalcContext, ent_date: MonthYear) -> None:
    """PiaCal::dataCheck — validation and preliminary calculations."""
    w = ctx.worker
    if w.benefit_type not in (
        BenefitType.OLD_AGE, BenefitType.SURVIVOR, BenefitType.DISABILITY,
        BenefitType.STATEMENT,
    ):
        raise PiaError(0, "bad benefit type")
    kbirth_my = MonthYear(ctx.kbirth.year, ctx.kbirth.month)
    ctx.full_ret_age = retire_age.full_ret_age(ctx.kbirth.year + 62)
    ctx.full_ret_date = add_age(
        kbirth_my, ctx.full_ret_age.years, ctx.full_ret_age.months
    )
    if ctx.full_ret_date < JAN_1937:
        ctx.full_ret_date = JAN_1937
    if ctx.ioasdi == BenefitType.OLD_AGE:
        ctx.early_ret_age = retire_age.early_age_oab(w.sex, ctx.kbirth)
    if ctx.ioasdi != BenefitType.SURVIVOR:
        assert w.entitlement is not None and w.benefit_date is not None
        months_ent = w.entitlement.index() - kbirth_my.index()
        from pyanypia.dates import Age

        ctx.age_ent = Age(months_ent // 12, months_ent % 12)
        months_ben = w.benefit_date.index() - kbirth_my.index()
        ctx.age_ben = Age(months_ben // 12, months_ben % 12)
    insured.elig_year_cal(ctx)
    if ctx.ioasdi != BenefitType.SURVIVOR:
        age_ent_check(ctx)
    insured.nelapsed_cal(ctx, ctx.comp_period_new, ent_date)
    insured.nelapsed_non_freeze_cal(
        ctx, ctx.comp_period_new_non_freeze, ent_date
    )


def age_ent_check(ctx: CalcContext) -> None:
    """PiaCal::ageEntCheck."""
    assert ctx.age_ent is not None
    if ctx.age_ent.years <= 0:
        raise PiaError(PIA_IDS_ARDRI1, "impossible age at entitlement")
    if ctx.ioasdi == BenefitType.OLD_AGE:
        assert ctx.early_ret_age is not None
        if ctx.age_ent < ctx.early_ret_age:
            raise PiaError(
                PIA_IDS_ARDRI2, "entitlement before earliest retirement age"
            )
    if ctx.ioasdi == BenefitType.DISABILITY:
        assert ctx.worker.entitlement is not None
        if ctx.worker.entitlement.year <= 1959:
            if ctx.worker.entitlement.year < 1957:
                raise PiaError(PIA_IDS_ARDRI7, "DIB entitlement before 1957")
            if ctx.age_ent.years < 50:
                raise PiaError(PIA_IDS_ARDRI8, "DIB under age 50 before 1960")
            return
        assert ctx.full_ret_age is not None
        if not ctx.age_ent < ctx.full_ret_age:
            raise PiaError(PIA_IDS_ARDRI9, "DIB after full retirement age")


def freeze_years_cal(ctx: CalcContext, ent_date: MonthYear) -> None:
    """PiaData::freezeYearsCal."""
    w = ctx.worker
    fra_di = retire_age.full_ret_age_di(ctx.kbirth.year + 62, ent_date.year)
    fy = ctx.freeze_years
    fy.clear()
    if w.valdi > 0:
        d0 = w.disability_periods[0]
        fy.year1 = (
            d0.onset.year
            if (d0.onset.month == 1 and d0.onset.day == 1)
            else d0.onset.year + 1
        )
        if ctx.ioasdi == BenefitType.DISABILITY:
            year1 = ctx.kbirth.year + fra_di.years - 1
            if fra_di.months + ctx.kbirth.month > 12:
                year1 += 1
            assert d0.waiting_period_start is not None
            year2 = d0.waiting_period_start.year + fra_di.years - 63
            if fra_di.months + d0.waiting_period_start.month > 12:
                year2 += 1
            assert w.benefit_date is not None
            fy.year2 = min(w.benefit_date.year - 1, min(year2, year1))
        else:
            assert d0.cessation is not None
            fy.year2 = (
                d0.cessation.year
                if d0.cessation.month == 12
                else d0.cessation.year - 1
            )
    if w.valdi > 1:
        d1 = w.disability_periods[1]
        fy.year3 = (
            d1.onset.year
            if (d1.onset.month == 1 and d1.onset.day == 1)
            else d1.onset.year + 1
        )
        assert d1.cessation is not None
        fy.year4 = (
            d1.cessation.year
            if d1.cessation.month == 12
            else d1.cessation.year - 1
        )


def ardri_cal(ctx: CalcContext) -> None:
    """PiaCal::ardriCal — months of reduction or delayed credit."""
    if ctx.ioasdi == BenefitType.OLD_AGE:
        assert ctx.age_ent is not None and ctx.full_ret_age is not None
        if ctx.age_ent < ctx.full_ret_age:
            ctx.months_ardri = retire_age.months_ar(
                ctx.age_ent, ctx.full_ret_age
            )
            ctx.arf = retire_age.factor_ar(ctx.months_ardri)
        else:
            months_dri_cal(ctx)
    if ctx.ioasdi == BenefitType.DISABILITY:
        ctx.months_ardri = retire_age.months_ar_di(
            ctx.worker.oab_entitlement, ctx.worker.oab_cessation
        )
        ctx.arf = retire_age.factor_ar(ctx.months_ardri)


def months_dri_cal(ctx: CalcContext) -> None:
    """PiaCal::monthsDriCal — delayed retirement credit months."""
    w = ctx.worker
    assert ctx.full_ret_date is not None
    assert w.entitlement is not None and w.benefit_date is not None
    elig_year = ctx.elig_date.year if ctx.elig_date is not None else 0
    ctx.full_ins_date = insured.full_ins_date_cal(ctx)
    ctx.months_ardri = retire_age.months_dri(
        ctx.full_ret_date, elig_year, ctx.kbirth, w.entitlement,
        w.benefit_date, ctx.full_ins_date,
    )
    ctx.arf = retire_age.factor_dri(ctx.months_ardri, elig_year)


def set_high_pia(ctx: CalcContext, methods: list[MethodState]) -> None:
    ctx.iappn = -1
    for m in methods:
        if ctx.high_pia < m.pia_ent:
            ctx.high_pia = m.pia_ent
            ctx.iappn = int(m.method)
            ctx.high_method = m  # type: ignore[attr-defined]
    for m in methods:
        if ctx.iappn == int(m.method):
            m.applicable = 2  # HIGH_PIA
            break
    set_pifc(ctx, methods)


def set_support_pia(ctx: CalcContext, methods: list[MethodState]) -> None:
    """PiaCal::setSupportPia — DRC cannot apply to a special minimum PIA."""
    assert ctx.full_ret_age is not None
    if (
        ctx.age_ent is not None
        and ctx.full_ret_age < ctx.age_ent
        and ctx.iappn == int(MethodType.SPEC_MIN)
    ):
        support: MethodState | None = None
        for m in methods:
            if (
                ctx.support_pia < m.pia_ent
                and m.method != MethodType.SPEC_MIN
            ):
                ctx.support_pia = m.pia_ent
                ctx.iapps = int(m.method)
                support = m
        if support is not None:
            support.applicable = 3  # SUPPORT_PIA


def set_high_mfb(ctx: CalcContext, methods: list[MethodState]) -> None:
    if ctx.iappn > -1:
        if ctx.iappn == int(MethodType.REIND_WID):
            for m in methods:
                if m.method == MethodType.WAGE_IND:
                    ctx.high_mfb = m.mfb_ent
                    return
        high = getattr(ctx, "high_method", None)
        if high is not None:
            ctx.high_mfb = high.mfb_ent


def set_arf_app(ctx: CalcContext, methods: list[MethodState]) -> None:
    for m in methods:
        if m.method == MethodType.SPEC_MIN:
            if m.pia_ent < ctx.unrounded_benefit:
                ctx.arf_app = 1  # SUPPORT_BEN
            else:
                ctx.unrounded_benefit = m.pia_ent
                ctx.arf_app = 2  # SPEC_MIN_BEN
            return


def set_pifc(ctx: CalcContext, methods: list[MethodState]) -> None:
    """Pifc::pifcCal."""
    if ctx.worker.totalize:
        ctx.pifc = "K"
        return
    windfall = WindfallType.NOWINDFALLELIM
    for m in methods:
        if m.method == MethodType.WAGE_IND:
            windfall = WindfallType(m.windfall)
    if ctx.iappn == int(MethodType.WAGE_IND_NON_FREEZE):
        windfall = WindfallType.NOWINDFALLELIM
        for m in methods:
            if m.method == MethodType.WAGE_IND_NON_FREEZE:
                windfall = WindfallType(m.windfall)
    appnum = ctx.iappn
    if appnum == int(MethodType.OLD_START):
        ctx.pifc = "B"  # OS1990/OS1977_79 variants come with old-start port
    elif appnum == int(MethodType.PIA_TABLE):
        ctx.pifc = "7" if ctx.amend90 else "B"
    elif appnum == int(MethodType.WAGE_IND):
        ctx.pifc = "5" if int(windfall) > 0 else "L"
    elif appnum == int(MethodType.TRANS_GUAR):
        ctx.pifc = "N"
    elif appnum == int(MethodType.SPEC_MIN):
        ctx.pifc = "C"
    elif appnum == int(MethodType.REIND_WID):
        ctx.pifc = "W"
    elif appnum == int(MethodType.FROZ_MIN):
        ctx.pifc = "M"
    elif appnum == int(MethodType.CHILD_CARE):
        ctx.pifc = "Y"
    elif appnum == int(MethodType.DIB_GUAR):
        ctx.pifc = "S"
    elif appnum == int(MethodType.WAGE_IND_NON_FREEZE):
        ctx.pifc = "5" if int(windfall) > 0 else "L"
    else:
        ctx.pifc = " "


def pia_cal2(ctx: CalcContext, methods: list[MethodState]) -> None:
    """PiaCal::piaCal2 — benefit payable for the primary."""
    w = ctx.worker
    assert w.benefit_date is not None
    i1 = w.benefit_date.year
    if i1 >= 1951 and w.benefit_date.month < ctx.params.month_beninc(i1):
        i1 -= 1
    if ctx.ioasdi != BenefitType.SURVIVOR:
        ardri_cal(ctx)
        if ctx.iapps >= 0:
            ctx.unrounded_benefit = round_benefit(
                ctx.arf * ctx.support_pia, i1
            )
            set_arf_app(ctx, methods)
        else:
            assert w.entitlement is not None
            if w.entitlement < retire_age.AMEND50:
                ctx.unrounded_benefit = ctx.high_pia
            else:
                ctx.unrounded_benefit = round_benefit(
                    ctx.arf * ctx.high_pia, i1
                )
        ctx.rounded_benefit = round_to_dollar(
            ctx.unrounded_benefit, w.benefit_date
        )
