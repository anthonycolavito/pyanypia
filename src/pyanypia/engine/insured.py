"""Quarters of coverage and insured status (piacal.cpp / piadata.cpp).

Function-for-function port of the QC and insured-status logic:
eligYearCal1/2/3, qcCal, qcTotalCal, qcReqCal, qcReqPermCal,
qcCurrentCal, fins1Cal, fins2Cal, didropCal, deemedInsCal, nelapsed/nCal.
"""

from __future__ import annotations

import math
from datetime import date

from pyanypia.dates import MonthYear, QtrYear
from pyanypia.engine.context import CalcContext, CompPeriod, FreezeYears
from pyanypia.params import retire_age
from pyanypia.worker import BenefitType, Worker

YEAR37 = 1937
YEAR50 = 1950
YEAR51 = 1951

# InsCode::InsCodeType characters (inscode.h)
NOQCS = "0"
FULLANDCURRENT = "1"
CURRENTNOTFULL = "2"
FULLNOTCURRENT = "3"
UNINSURED = "4"
PERMANDCURRENT = "5"
PERMNOTCURRENT = "6"
TRANSITIONAL = "7"
TOTALIZED = "8"
DEEMED = "9"
PRIMARYDEATH = "C"
NONPRIMARYDEATH = "D"

FULLY_INSURED_CODES = frozenset("1356" + DEEMED + PRIMARYDEATH)
CURRENTLY_INSURED_CODES = frozenset("125" + PRIMARYDEATH)
TOTAL_INSURED_CODES = frozenset(TOTALIZED)


def is_fully_insured(code: str) -> bool:
    return code in FULLY_INSURED_CODES


def is_currently_insured(code: str) -> bool:
    return code in CURRENTLY_INSURED_CODES


def qc3750_simp_cal(earn3750: float) -> int:
    return min(int(earn3750 / 400.0), 56)


def elig_year_cal1(ctx: CalcContext, jind7: int = 0) -> MonthYear:
    """Date of eligibility before considering disability."""
    birth_year = ctx.kbirth.year
    elig = MonthYear(birth_year + 62 + jind7, ctx.kbirth.month)
    if ctx.worker.sex == 0:  # male
        if 1909 < birth_year < 1914:
            elig = MonthYear(1975, 12)
        if birth_year < 1910:
            elig = MonthYear(birth_year + 65, elig.month)
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert ctx.worker.death_date is not None
        death = MonthYear.from_date(ctx.worker.death_date)
        if death < elig:
            elig = death
    return elig


def elig_year_cal2(ctx: CalcContext, elig_year: int) -> int:
    """Year of eligibility after considering disability."""
    rv = elig_year
    w = ctx.worker
    if w.valdi > 0:
        d0 = w.disability_periods[0]
        if w.valdi < 2:
            onset_year = d0.onset.year
        else:
            d1 = w.disability_periods[1]
            months = (
                _months_between_cess_and_date(d1.cessation, d0.onset)
            )
            onset_year = d0.onset.year if months > 12 else (
                w.disability_periods[1].onset.year
            )
        if ctx.ioasdi != BenefitType.DISABILITY:
            assert ctx.elig_date is not None
            if d0.cessation is not None:
                cess_months = ctx.elig_date.index() - d0.cessation.index()
            else:
                cess_months = 0  # no cessation: treated as 0 months
            if cess_months < 13 and onset_year < rv:
                rv = onset_year
        if ctx.ioasdi == BenefitType.DISABILITY and rv > onset_year:
            rv = onset_year
    return rv


def _months_between_cess_and_date(
    cessation: MonthYear | None, onset: date
) -> int:
    """DateMoyr::getMonths(date): months from cessation to onset date."""
    if cessation is None:
        return 0
    return MonthYear.from_date(onset).index() - cessation.index()


def elig_year_cal3(ctx: CalcContext, elig_year: int) -> int:
    """Year of eligibility for non-freeze computations."""
    rv = elig_year
    w = ctx.worker
    if ctx.ioasdi == BenefitType.DISABILITY:
        wp = w.disability_periods[0].waiting_period_start
        if wp is not None and wp.year < rv:
            rv = wp.year
    return rv


def elig_year_cal(ctx: CalcContext) -> None:
    ctx.elig_date = elig_year_cal1(ctx)
    ctx.elig_year = elig_year_cal2(ctx, ctx.elig_date.year)
    ctx.elig_year_non_freeze = elig_year_cal3(ctx, ctx.elig_date.year)


def didrop_cal(
    worker: Worker, elapsed1: int, elapsed2: int, frzyrs: FreezeYears
) -> int:
    """Years to drop from the elapsed period due to disability."""
    rv = 0
    frzyrs.clear()
    if worker.valdi == 0:
        return rv
    d0 = worker.disability_periods[0]
    onset_year = d0.onset.year
    cess_year = d0.cessation.year if d0.cessation is not None else 0
    if onset_year <= elapsed2:
        frzyrs.year1 = max(onset_year, elapsed1 + 1)
        frzyrs.year2 = (
            cess_year if onset_year <= cess_year <= elapsed2 else elapsed2
        )
        rv = frzyrs.year2 - frzyrs.year1 + 1
    if worker.valdi == 2:
        d1 = worker.disability_periods[1]
        onset1 = d1.onset.year
        cess1 = d1.cessation.year if d1.cessation is not None else 0
        if onset1 <= elapsed2 and (
            frzyrs.year1 == 0 or onset1 < frzyrs.year1
        ):
            frzyrs.year3 = max(onset1, elapsed1 + 1)
            frzyrs.year4 = (
                cess1 if onset1 <= cess1 <= elapsed2 else elapsed2
            )
            if frzyrs.year1 > 0 and frzyrs.year4 >= frzyrs.year1:
                frzyrs.year4 = frzyrs.year1 - 1
            rv += frzyrs.year4 - frzyrs.year3 + 1
    return rv


def qc_cal(ctx: CalcContext) -> None:
    """PiaData::qcCal — annual quarters of coverage."""
    w = ctx.worker
    qc_lump_year = 1977
    ctx.qcov = {}
    i2 = max(qc_lump_year, 1950)
    # early years: entered annual QCs (military/railroad handled later)
    for yr in range(YEAR37, i2 + 1):
        qctemp = w.qcs_by_year.get(yr, 0)
        if qctemp:
            ctx.qcov[yr] = min(4, qctemp)
    for yr in range(i2 + 1, ctx.iend_all + 1):
        amt = ctx.params.qc_amt[yr]
        qctemp = min(4, int(math.floor(ctx.earn_oasdi.get(yr, 0.0) / amt)))
        ctx.qcov[yr] = qctemp


def qc_total_cal(ctx: CalcContext, qtr_year: QtrYear) -> None:
    """PiaData::qcTotalCal."""
    w = ctx.worker
    ctx.qc3750_simp = qc3750_simp_cal(ctx.earn_total50)
    ctx.qc_total50 = (
        w.qc_total_to_date - w.qc_total_51_to_date + ctx.qc3750_ms
    )
    i1 = max(ctx.qc_total50, ctx.qc3750_simp)
    if w.qcs_by_year:
        ctx.qc_total51 = ctx.qcov_accumulate(
            QtrYear(0, YEAR51), qtr_year, 0
        )
    else:
        # military quarters 1951-56 add to the lump, then annual quarters
        # take over from 1978
        ctx.qc_total51 = w.qc_total_51_to_date + sum(
            ctx.qcov_mil_serv.get(y, 0) for y in range(1951, 1957)
        )
        ctx.qc_total51 = ctx.qcov_accumulate(
            QtrYear(0, 1978), qtr_year, ctx.qc_total51
        )
    ctx.qc_total = i1 + ctx.qc_total51


def qc_total_non_freeze_cal(ctx: CalcContext, qtr_year: QtrYear) -> None:
    w = ctx.worker
    i1 = max(ctx.qc_total50, ctx.qc3750_simp)
    if w.qcs_by_year:
        ctx.qc_total51_non_freeze = ctx.qcov_accumulate(
            QtrYear(0, YEAR51), qtr_year, 0
        )
    else:
        ctx.qc_total51_non_freeze = w.qc_total_51_to_date
        ctx.qc_total51_non_freeze = ctx.qcov_accumulate(
            QtrYear(0, 1978), qtr_year, ctx.qc_total51_non_freeze
        )
    ctx.qc_total_non_freeze = i1 + ctx.qc_total51_non_freeze


def qc_req_cal(ctx: CalcContext, year: int) -> int:
    """Required QCs for fully insured status at end of year."""
    ctx.elig_date = elig_year_cal1(ctx)
    elapsed2 = min(year, ctx.elig_date.year - 1)
    elapsed1 = max(ctx.kbirth.year + 21, 1950)
    di_years = didrop_cal(
        ctx.worker, elapsed1, elapsed2, ctx.partial_freeze_years
    )
    return min(40, max(6, elapsed2 - elapsed1 - di_years))


def qc_req_non_freeze_cal(ctx: CalcContext, year: int) -> int:
    ctx.elig_date = elig_year_cal1(ctx)
    elapsed2 = min(year, ctx.elig_date.year - 1)
    elapsed1 = max(ctx.kbirth.year + 21, 1950)
    di_years = 0
    if ctx.ioasdi == BenefitType.DISABILITY:
        di_years = didrop_non_freeze_cal(ctx.worker, elapsed1, elapsed2)
    return min(40, max(6, elapsed2 - elapsed1 - di_years))


def didrop_non_freeze_cal(
    worker: Worker, elapsed1: int, elapsed2: int
) -> int:
    rv = 0
    if worker.valdi == 0:
        return rv
    wp = worker.disability_periods[0].waiting_period_start
    wait_year = wp.year if wp is not None else 0
    if wait_year <= elapsed2:
        year1 = max(wait_year, elapsed1 + 1)
        rv = elapsed2 - year1 + 1
    return rv


def qc_req_perm_cal(ctx: CalcContext) -> int:
    elap1 = max(ctx.kbirth.year + 21, 1950)
    ctx.elig_date = elig_year_cal1(ctx)
    elap2 = ctx.elig_date.year - 1
    didropout = 0
    if ctx.worker.valdi:
        didropout = didrop_cal(ctx.worker, elap1, elap2, FreezeYears())
    return min(40, max(6, elap2 - elap1 - didropout))


def qc_req_perm_non_freeze_cal(ctx: CalcContext) -> int:
    elap1 = max(ctx.kbirth.year + 21, 1950)
    ctx.elig_date = elig_year_cal1(ctx)
    elap2 = ctx.elig_date.year - 1
    di_years = 0
    if ctx.ioasdi == BenefitType.DISABILITY:
        di_years = didrop_non_freeze_cal(ctx.worker, elap1, elap2)
    return min(40, max(6, elap2 - elap1 - di_years))


def qc_current_cal(ctx: CalcContext, qtr_year: QtrYear) -> int:
    """QCs earned in the 13-quarter period for currently insured status."""
    start = qtr_year.subtract(12)
    if start < QtrYear(0, YEAR37):
        start = QtrYear(0, YEAR37)
    return ctx.qcov_accumulate(start, qtr_year, 0)


def deemed_ins_cal(ctx: CalcContext, qtr_year: QtrYear) -> bool:
    ctx.deemed_qc_req = retire_age.deemed_qc_req(ctx.kbirth.year)
    if ctx.deemed_qc_req < 0:
        return False
    tot = ctx.qcov_accumulate(QtrYear(0, 1984), qtr_year, 0)
    return tot >= ctx.deemed_qc_req


def fins1_cal(ctx: CalcContext, qtr_year: QtrYear, iswas_primary: int) -> str:
    """Insured status decision tree (PiaCal::fins1Cal)."""
    w = ctx.worker
    if ctx.qc_total < ctx.qc_req:
        if iswas_primary > 0 and w.totalize:
            return TOTALIZED
        if w.deemed_insured and qtr_year.year > 1983:
            if deemed_ins_cal(ctx, qtr_year):
                return DEEMED
        if ctx.qc_total == 0:
            return NOQCS
        if ctx.qc_current > 5:
            return CURRENTNOTFULL
        if ctx.qc_total > 2 and ctx.qc_total + (
            1887 if w.sex == 0 else 1890
        ) > ctx.kbirth.year:
            return TRANSITIONAL
        return UNINSURED
    if ctx.qc_total < ctx.qc_req_perm:
        return FULLANDCURRENT if ctx.qc_current > 5 else FULLNOTCURRENT
    return PERMANDCURRENT if ctx.qc_current > 5 else PERMNOTCURRENT


def fins_non_freeze1_cal(
    ctx: CalcContext, qtr_year: QtrYear, iswas_primary: int
) -> str:
    w = ctx.worker
    if ctx.qc_total_non_freeze < ctx.qc_req_non_freeze:
        if iswas_primary > 0 and w.totalize:
            return TOTALIZED
        if w.deemed_insured and qtr_year.year > 1983:
            if deemed_ins_cal(ctx, qtr_year):
                return DEEMED
        if ctx.qc_total_non_freeze == 0:
            return NOQCS
        if ctx.qc_current_non_freeze > 5:
            return CURRENTNOTFULL
        if ctx.qc_total_non_freeze > 2 and ctx.qc_total_non_freeze + (
            1887 if w.sex == 0 else 1890
        ) > ctx.kbirth.year:
            return TRANSITIONAL
        return UNINSURED
    if ctx.qc_total_non_freeze < ctx.qc_req_perm_non_freeze:
        return (
            FULLANDCURRENT if ctx.qc_current_non_freeze > 5
            else FULLNOTCURRENT
        )
    return (
        PERMANDCURRENT if ctx.qc_current_non_freeze > 5 else PERMNOTCURRENT
    )


def fins2_cal(ctx: CalcContext, code: str) -> str:
    """OACT summary insured code '1'..'7' (PiaCal::fins2Cal)."""
    if ctx.ioasdi == BenefitType.SURVIVOR:
        if is_fully_insured(code):
            return "1"
        return "2" if is_currently_insured(code) else "5"
    if ctx.worker.totalize:
        if ctx.qc_total < 6:
            return "6"
        return "7" if is_fully_insured(code) else "3"
    return "1" if is_fully_insured(code) else "4"


def fins_non_freeze2_cal(ctx: CalcContext, code: str) -> str:
    if ctx.ioasdi == BenefitType.SURVIVOR:
        if is_fully_insured(code):
            return "1"
        return "2" if is_currently_insured(code) else "5"
    if ctx.worker.totalize:
        if ctx.qc_total_non_freeze < 6:
            return "6"
        return "7" if is_fully_insured(code) else "3"
    return "1" if is_fully_insured(code) else "4"


def ins_cal_full(ctx: CalcContext, when: date, iswas_primary: int) -> str:
    """PiaCal::insCal(dateModyyr, isWasPrimary)."""
    qtr_year = QtrYear.from_date(when)
    qc_total_cal(ctx, qtr_year)
    ctx.qc_req = qc_req_cal(ctx, qtr_year.year)
    ctx.qc_req_perm = qc_req_perm_cal(ctx)
    ctx.qc_current = qc_current_cal(ctx, qtr_year)
    return fins1_cal(ctx, qtr_year, iswas_primary)


def ins_non_freeze_cal_full(
    ctx: CalcContext, when: date, iswas_primary: int
) -> str:
    qtr_year = QtrYear.from_date(when)
    qc_total_non_freeze_cal(ctx, qtr_year)
    ctx.qc_req_non_freeze = qc_req_non_freeze_cal(ctx, qtr_year.year)
    ctx.qc_req_perm_non_freeze = qc_req_perm_non_freeze_cal(ctx)
    ctx.qc_current_non_freeze = qc_current_cal(ctx, qtr_year)
    return fins_non_freeze1_cal(ctx, qtr_year, iswas_primary)


def full_ins_date_cal(ctx: CalcContext) -> MonthYear:
    """Date fully insured status first attained at/after NRA
    (PiaCal::fullInsDateCal)."""
    assert ctx.full_ret_date is not None
    assert ctx.worker.benefit_date is not None
    qtr_year = QtrYear.from_month_year(ctx.full_ret_date)
    while True:
        qc_total_cal(ctx, qtr_year)
        ctx.qc_req = qc_req_cal(ctx, qtr_year.year)
        ctx.qc_req_perm = qc_req_perm_cal(ctx)
        ctx.qc_current = qc_current_cal(ctx, qtr_year)
        code = fins1_cal(ctx, qtr_year, 1)
        if is_fully_insured(code) or code in TOTAL_INSURED_CODES:
            return qtr_year.to_month_year()
        qtr_year = qtr_year.add(1)
        if not qtr_year.to_month_year() < ctx.worker.benefit_date:
            return qtr_year.to_month_year()


# ---- elapsed years / computation period ----


def nelapsed2_cal(ctx: CalcContext, ent_date: MonthYear) -> int:
    elap2 = (
        1960
        if (
            ent_date.year > 1960 and ctx.elig_year < 1961
            and ctx.worker.valdi == 0
        )
        else ctx.elig_year - 1
    )
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert ctx.worker.death_date is not None
        elap2 = min(elap2, ctx.worker.death_date.year - 1)
    return elap2


def nelapsed_cal_from2(
    ctx: CalcContext, comp: CompPeriod, elapsed2: int
) -> None:
    elapsed1 = max(ctx.kbirth.year + 21, comp.base_year)
    comp.n_elapsed = elapsed2 - elapsed1
    comp.di_years = didrop_cal(
        ctx.worker, elapsed1, elapsed2, ctx.partial_freeze_years
    )
    if comp.di_years > 0:
        comp.n_elapsed -= comp.di_years
    if comp.n_elapsed < 2:
        comp.n_elapsed = 2


def nelapsed_cal(ctx: CalcContext, comp: CompPeriod, ent: MonthYear) -> None:
    nelapsed_cal_from2(ctx, comp, nelapsed2_cal(ctx, ent))


def nelapsed2_non_freeze_cal(ctx: CalcContext, ent_date: MonthYear) -> int:
    elap2 = (
        1960
        if (
            ent_date.year > 1960 and ctx.elig_year_non_freeze < 1961
            and ctx.worker.valdi == 0
        )
        else ctx.elig_year_non_freeze - 1
    )
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert ctx.worker.death_date is not None
        elap2 = min(elap2, ctx.worker.death_date.year - 1)
    return elap2


def nelapsed_non_freeze_cal(
    ctx: CalcContext, comp: CompPeriod, ent: MonthYear
) -> None:
    elapsed2 = nelapsed2_non_freeze_cal(ctx, ent)
    elapsed1 = max(ctx.kbirth.year + 21, comp.base_year)
    comp.n_elapsed = elapsed2 - elapsed1
    comp.di_years = 0
    if comp.n_elapsed < 2:
        comp.n_elapsed = 2


def ndrop_cal(ctx: CalcContext, ent_date: MonthYear) -> int:
    """Dropout years before considering 1-for-5 (PiaCal::nDropCal)."""
    w = ctx.worker
    ndrop = 5
    if ent_date < retire_age.AMEND90:
        if ctx.ioasdi == BenefitType.SURVIVOR:
            if w.valdi > 0:
                onset = MonthYear.from_date(w.disability_periods[0].onset)
                ndrop = 5 if not onset < retire_age.AMEND54 else 0
            else:
                assert w.death_date is not None
                death = MonthYear.from_date(w.death_date)
                ndrop = 5 if not death < retire_age.AMEND54 else 0
        else:
            if w.valdi > 0:
                onset = MonthYear.from_date(w.disability_periods[0].onset)
                ndrop = 5 if not onset < retire_age.AMEND54 else 0
            else:
                assert w.entitlement is not None
                ndrop = 5 if not w.entitlement < retire_age.AMEND54 else 0
    return ndrop


def n_cal(ctx: CalcContext, comp: CompPeriod, ent_date: MonthYear) -> None:
    """Computation years and dropout years (PiaCalLC::nCal, present law)."""
    w = ctx.worker
    comp.n_drop = ndrop_cal(ctx, ent_date)
    d0 = w.disability_periods[0] if w.valdi > 0 else None
    oa_dib_rule = (
        ctx.ioasdi == BenefitType.OLD_AGE
        and w.valdi > 0
        and d0 is not None
        and d0.first_entitlement is not None
        and not d0.first_entitlement < retire_age.AMEND80
        and d0.cessation is not None
        and not d0.cessation < MonthYear(w.dob.year + 61, w.dob.month)
    )
    di_rule = (
        ctx.ioasdi == BenefitType.DISABILITY
        and w.entitlement is not None
        and not w.entitlement < retire_age.AMEND80
    )
    if oa_dib_rule or di_rule:
        comp.n_drop = min(comp.n_elapsed // 5, 5)
    comp.n = comp.n_elapsed - comp.n_drop
    if comp.n < 2:
        comp.n = 2
        comp.n_drop = comp.n_elapsed - comp.n
    if (
        ctx.ioasdi == BenefitType.OLD_AGE
        and w.entitlement is not None
        and w.entitlement.year < 1958
        and comp.base_year == YEAR50
    ):
        comp.n = ctx.elig_year - 1953
        if comp.n < 2:
            comp.n = 2
            comp.n_drop = comp.n_elapsed - comp.n


def ndrop_non_freeze_cal(ctx: CalcContext, ent_date: MonthYear) -> int:
    w = ctx.worker
    ndrop = 5
    if ent_date < retire_age.AMEND90:
        if ctx.ioasdi == BenefitType.SURVIVOR:
            assert w.death_date is not None
            death = MonthYear.from_date(w.death_date)
            ndrop = 5 if not death < retire_age.AMEND54 else 0
        elif ctx.ioasdi == BenefitType.OLD_AGE:
            assert w.entitlement is not None
            ndrop = 5 if not w.entitlement < retire_age.AMEND54 else 0
        else:
            ndrop = 5
    return ndrop


def n_non_freeze_cal(
    ctx: CalcContext, comp: CompPeriod, ent_date: MonthYear
) -> None:
    w = ctx.worker
    comp.n_drop = ndrop_non_freeze_cal(ctx, ent_date)
    if (
        ctx.ioasdi == BenefitType.DISABILITY
        and w.entitlement is not None
        and not w.entitlement < retire_age.AMEND80
    ):
        comp.n_drop = min(comp.n_elapsed // 5, 5)
    comp.n = comp.n_elapsed - comp.n_drop
    if comp.n < 2:
        comp.n = 2
        comp.n_drop = comp.n_elapsed - comp.n
    if (
        ctx.ioasdi == BenefitType.OLD_AGE
        and w.entitlement is not None
        and w.entitlement.year < 1958
        and comp.base_year == YEAR50
    ):
        comp.n = ctx.elig_year - 1953
        if comp.n < 2:
            comp.n = 2
            comp.n_drop = comp.n_elapsed - comp.n


# ---- disability insured status (PiaData::qcDis* + PiaCal::disInsCal) ----

# DisInsCode::DisInsCodeType characters
DIS_NOQCS = "0"
DIS_FULLAND2040 = "1"
DIS_FULLANDSPECIAL = "2"
DIS_FULLANDDIB = "3"
DIS_FULLANDBLIND = "4"
DIS_NOTFULLNOT2040 = "5"
DIS_NOTFULLHAS2040 = "6"
DIS_FULLNOT2040 = "7"
DIS_PRIMARYDEATH = "8"
DIS_NONPRIMARYDEATH = "9"
DIS_TOTALIZED = "T"

DIS_INSURED_CODES = frozenset("1234")


def is_disability_insured(code: str) -> bool:
    return code in DIS_INSURED_CODES


def _qtr_of_age21(ctx: CalcContext) -> QtrYear:
    q = QtrYear.from_date(ctx.kbirth)
    return QtrYear((q.quarter + 1) % 4, q.year + 21 + (q.quarter + 1) // 4)


def qc_dis_req2_cal(ctx: CalcContext, date_moyr: MonthYear) -> None:
    """Elapsed quarters after disability cessation (qcDisReq2Cal)."""
    w = ctx.worker
    d0 = w.disability_periods[0] if w.valdi > 0 else None
    cess = d0.cessation if d0 is not None else None
    date3 = QtrYear.from_month_year(cess) if cess is not None else None
    date4 = QtrYear.from_month_year(date_moyr)
    if w.valdi == 0 or cess is None or not (date3 < date4):  # type: ignore[operator]
        ctx.qc_dis_qtr2 = 0
        ctx.qc_dis_date3 = None
        ctx.qc_dis_date4 = None
        return
    assert date3 is not None
    date3 = date3.add(1)
    qtr2 = date3.diff(date4) + 1
    if qtr2 > 40:
        date3 = date4.subtract(39)
        qtr2 = 40
    ctx.qc_dis_date3 = date3
    ctx.qc_dis_date4 = date4
    ctx.qc_dis_qtr2 = qtr2


def _qc_di_spec(ctx: CalcContext, qcdiqtrt: int, period: int) -> None:
    """Special insured test period start (qcDiSpec)."""
    if period == 0:
        d2 = ctx.qc_dis_date2
    else:
        d2 = ctx.qc_dis_date6
    d1 = _qtr_of_age21(ctx)
    tempqcs = 12 - qcdiqtrt
    if tempqcs <= 0:
        if period == 0:
            ctx.qc_dis_date1 = None
            ctx.qc_dis_date2 = None
        else:
            ctx.qc_dis_date5 = None
            ctx.qc_dis_date6 = None
        return
    assert d2 is not None
    if d1.diff(d2) < tempqcs - 1:
        d1 = d2.subtract(tempqcs - 1)
    if period == 0:
        ctx.qc_dis_date1 = d1
    else:
        ctx.qc_dis_date5 = d1


def qc_dis_req_cal(
    ctx: CalcContext,
    date_moyr: MonthYear,
    trial: int,
    dospecial: bool,
    dofreeze: bool,
) -> None:
    """Required QCs for DI insured status (qcDisReqCal)."""
    w = ctx.worker
    if w.valdi > 0:
        d2 = QtrYear.from_date(w.disability_periods[0].onset).add(trial)
    else:
        d2 = QtrYear.from_month_year(date_moyr)
    ctx.qc_dis_date2 = d2
    age21 = _qtr_of_age21(ctx)
    if ctx.qc_dis_qtr2 == 40:
        ctx.qc_dis_qtr = 40
        ctx.qc_dis_date1 = None
        ctx.qc_dis_date2 = None
    else:
        d1 = d2.subtract(39 - ctx.qc_dis_qtr2)
        ctx.qc_dis_date1 = d1
        if dospecial and d1 < age21:
            _qc_di_spec(ctx, ctx.qc_dis_qtr2, 0)
        if ctx.qc_dis_date1 is None:
            ctx.qc_dis_qtr = ctx.qc_dis_qtr2
        else:
            d1 = ctx.qc_dis_date1
            if d1.year < YEAR37:
                d1 = QtrYear(0, YEAR37)
                ctx.qc_dis_date1 = d1
            assert ctx.qc_dis_date2 is not None
            ctx.qc_dis_qtr = (
                d1.diff(ctx.qc_dis_date2) + 1 + ctx.qc_dis_qtr2
            )
    # consider period before prior disability
    d1cur = ctx.qc_dis_date1
    prior_cess = (
        w.disability_periods[1].cessation if w.valdi >= 2 else None
    )
    if (
        w.valdi < 2
        or d1cur is None
        or prior_cess is None
        or not (d1cur < QtrYear.from_month_year(prior_cess))
    ):
        ctx.qc_dis_date5 = None
        ctx.qc_dis_date6 = None
    else:
        d1 = QtrYear.from_month_year(prior_cess)
        assert ctx.qc_dis_date2 is not None
        d2b = ctx.qc_dis_date2
        tempqcs = (
            4 - d1.quarter if d1.year < d2b.year
            else d2b.quarter - d1.quarter
        )
        if ctx.qcov.get(d1.year, 0) < tempqcs:
            d1 = d1.add(1)
        if d1 > d2b:
            ctx.qc_dis_date1 = None
            ctx.qc_dis_date2 = None
            ctx.qc_dis_qtr = ctx.qc_dis_qtr2
        else:
            ctx.qc_dis_date1 = d1
            ctx.qc_dis_qtr = d1.diff(d2b) + 1 + ctx.qc_dis_qtr2
        d1p = w.disability_periods[1]
        if dofreeze:
            d6 = QtrYear.from_date(d1p.onset)
        else:
            assert d1p.waiting_period_start is not None
            d6 = QtrYear.from_month_year(d1p.waiting_period_start)
        if ctx.qcov.get(d6.year, 0) <= d6.quarter:
            d6 = d6.subtract(1)
        ctx.qc_dis_date6 = d6
        d5 = d6.subtract(39 - ctx.qc_dis_qtr)
        ctx.qc_dis_date5 = d5
        if dospecial and d5 < age21:
            _qc_di_spec(ctx, ctx.qc_dis_qtr, 1)
        if ctx.qc_dis_date5 is not None:
            d5 = ctx.qc_dis_date5
            if d5.year < YEAR37:
                d5 = QtrYear(0, YEAR37)
                ctx.qc_dis_date5 = d5
            ctx.qc_dis_qtr += d5.diff(ctx.qc_dis_date6) + 1
    ctx.qc_dis_years = (ctx.qc_dis_qtr + 2) // 4
    ctx.qc_dis_req = ctx.qc_dis_qtr // 2


def qc_dis_cal(ctx: CalcContext) -> None:
    """Earned QCs in the disability insured period (qcDisCal)."""
    total = 0
    if ctx.qc_dis_date1 is not None and ctx.qc_dis_date2 is not None:
        total = ctx.qcov_accumulate(ctx.qc_dis_date1, ctx.qc_dis_date2, total)
    if ctx.qc_dis_date3 is not None and ctx.qc_dis_date4 is not None:
        total = ctx.qcov_accumulate(ctx.qc_dis_date3, ctx.qc_dis_date4, total)
    if ctx.qc_dis_date5 is not None and ctx.qc_dis_date6 is not None:
        total = ctx.qcov_accumulate(ctx.qc_dis_date5, ctx.qc_dis_date6, total)
    ctx.qc_total_dis = total


def qc_dis_req_non_freeze_cal(
    ctx: CalcContext, date_moyr: MonthYear, dospecial: bool
) -> None:
    """qcDisReqNonFreezeCal."""
    w = ctx.worker
    if w.valdi > 0:
        wp = w.disability_periods[0].waiting_period_start
        assert wp is not None
        d2 = QtrYear.from_month_year(wp)
    else:
        d2 = QtrYear.from_month_year(date_moyr)
    ctx.qc_dis_date_nf2 = d2
    age21 = _qtr_of_age21(ctx)
    d1 = d2.subtract(39)
    ctx.qc_dis_date_nf1 = d1
    if dospecial and d1 < age21:
        # qcDiSpecNonFreeze with qcdiqtrt=0: 12-QC window
        d1 = age21
        if age21.diff(d2) < 11:
            d1 = d2.subtract(11)
        ctx.qc_dis_date_nf1 = d1
    if d1.year < YEAR37:
        d1 = QtrYear(0, YEAR37)
        ctx.qc_dis_date_nf1 = d1
    ctx.qc_dis_qtr_nf = d1.diff(d2) + 1
    ctx.qc_dis_req_nf = ctx.qc_dis_qtr_nf // 2


def qc_dis_non_freeze_cal(ctx: CalcContext) -> None:
    total = 0
    if ctx.qc_dis_date_nf1 is not None and ctx.qc_dis_date_nf2 is not None:
        total = ctx.qcov_accumulate(
            ctx.qc_dis_date_nf1, ctx.qc_dis_date_nf2, total
        )
    ctx.qc_total_dis_nf = total


def dis_ins_cal(
    ctx: CalcContext, date_moyr: MonthYear, iswas_primary: int
) -> str:
    """Disability insured status code (PiaCal::disInsCal)."""
    w = ctx.worker
    if w.death_date is not None and not (
        date_moyr < MonthYear.from_date(w.death_date).add_months(1)
    ):
        return (
            DIS_PRIMARYDEATH if iswas_primary == 2 else DIS_NONPRIMARYDEATH
        )
    if ctx.qc_total == 0:
        return DIS_NOQCS
    age21 = _qtr_of_age21(ctx)
    trial = 0
    d0 = w.disability_periods[0] if w.valdi > 0 else None
    qc_dis_req2_cal(ctx, date_moyr)
    if (
        ctx.qc_dis_qtr2 < 40
        and w.valdi > 0
        and d0 is not None
        and d0.waiting_period_start is not None
    ):
        wp = d0.waiting_period_start
        trial = (
            4 * (wp.year - d0.onset.year)
            + (wp.month + 2) // 3
            - (d0.onset.month + 2) // 3
        )
    for i in range(trial, -1, -1):
        qc_dis_req_cal(ctx, date_moyr, i, False, False)
        qc_dis_cal(ctx)
        if ctx.qc_total_dis >= ctx.qc_dis_req:
            break
    if ctx.qc_total_dis < ctx.qc_dis_req and (
        (
            ctx.qc_dis_date5 is not None
            and ctx.qc_dis_date5 < age21
        )
        or (ctx.qc_dis_date5 is None and ctx.qc_dis_date1 is not None
            and ctx.qc_dis_date1 < age21)
    ):
        for i in range(0, trial + 1):
            qc_dis_req_cal(ctx, date_moyr, i, True, False)
            qc_dis_cal(ctx)
            if ctx.qc_total_dis >= ctx.qc_dis_req:
                break
    if ctx.qc_total_dis < ctx.qc_dis_req and ctx.qc_dis_date5 is not None:
        for i in range(trial, -1, -1):
            qc_dis_req_cal(ctx, date_moyr, i, False, True)
            qc_dis_cal(ctx)
            if ctx.qc_total_dis >= ctx.qc_dis_req:
                break
    if (
        ctx.qc_total_dis < ctx.qc_dis_req
        and ctx.qc_dis_date5 is not None
        and ctx.qc_dis_date5 < age21
    ):
        for i in range(0, trial + 1):
            qc_dis_req_cal(ctx, date_moyr, i, True, True)
            qc_dis_cal(ctx)
            if ctx.qc_total_dis >= ctx.qc_dis_req:
                break
    if ctx.qc_total < ctx.qc_req:
        if iswas_primary == 1 and w.totalize:
            return DIS_TOTALIZED
        if ctx.qc_total_dis < ctx.qc_dis_req:
            return DIS_NOTFULLNOT2040
        return DIS_NOTFULLHAS2040
    if ctx.qc_total_dis < ctx.qc_dis_req:
        if iswas_primary == 1 and w.totalize:
            return DIS_TOTALIZED
        if w.blind:
            return DIS_FULLANDBLIND
        return DIS_FULLNOT2040
    if iswas_primary == 1:
        return DIS_FULLANDDIB
    if ctx.qc_dis_qtr == 40:
        return DIS_FULLAND2040
    return DIS_FULLANDSPECIAL


def dis_ins_non_freeze_cal(
    ctx: CalcContext, date_moyr: MonthYear, iswas_primary: int
) -> str:
    """disInsNonFreezeCal."""
    w = ctx.worker
    if w.death_date is not None and not (
        date_moyr < MonthYear.from_date(w.death_date).add_months(1)
    ):
        return (
            DIS_PRIMARYDEATH if iswas_primary == 2 else DIS_NONPRIMARYDEATH
        )
    if ctx.qc_total == 0:
        return DIS_NOQCS
    age21 = _qtr_of_age21(ctx)
    qc_dis_req_non_freeze_cal(ctx, date_moyr, False)
    qc_dis_non_freeze_cal(ctx)
    if ctx.qc_total_dis_nf < ctx.qc_dis_req_nf and (
        ctx.qc_dis_date_nf1 is not None and ctx.qc_dis_date_nf1 < age21
    ):
        qc_dis_req_non_freeze_cal(ctx, date_moyr, True)
        qc_dis_non_freeze_cal(ctx)
    if ctx.qc_total_non_freeze < ctx.qc_req_non_freeze:
        if iswas_primary == 1 and w.totalize:
            return DIS_TOTALIZED
        if ctx.qc_total_dis_nf < ctx.qc_dis_req_nf:
            return DIS_NOTFULLNOT2040
        return DIS_NOTFULLHAS2040
    if ctx.qc_total_dis_nf < ctx.qc_dis_req_nf:
        if iswas_primary == 1 and w.totalize:
            return DIS_TOTALIZED
        if w.blind:
            return DIS_FULLANDBLIND
        return DIS_FULLNOT2040
    if iswas_primary == 1:
        return DIS_FULLANDDIB
    if ctx.qc_dis_qtr_nf == 40:
        return DIS_FULLAND2040
    return DIS_FULLANDSPECIAL
