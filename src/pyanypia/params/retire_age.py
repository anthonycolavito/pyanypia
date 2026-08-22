"""Retirement ages, reduction/credit factors, and related age rules.

Transliterated from the present-law (PL) functions in piaparms.cpp:
fullRetAgeCalPL, fullRetAgeCalDIPL, retCredit, factorArCalPL,
factorArAgedSpouseCalPL, maxDibAgePL, earlyAgeOabCalPL, earlyAgeWidCal,
earlyAgeDisWidCal, months/factor functions, deemedQcReqCal, ribLimCalPL,
specMinAmountCalPL, plus the monthBeninc table from initdata().
"""

from __future__ import annotations

from datetime import date

from pyanypia.dates import Age, MonthYear
from pyanypia.rounding import round_benefit

# Amendment effective dates (PiaParams constants).
AMEND50 = MonthYear(1950, 9)
AMEND52 = MonthYear(1952, 9)
AMEND54 = MonthYear(1954, 9)
AMEND56 = MonthYear(1956, 11)
AMEND561 = date(1891, 11, 2)  # female age-62 boundary birthdate
AMEND562 = date(1889, 11, 2)
AMEND58 = MonthYear(1959, 1)
AMEND61 = MonthYear(1961, 8)
AMEND611 = date(1892, 8, 2)  # male age-62 boundary birthdate
AMEND612 = date(1890, 8, 2)
AMEND651 = MonthYear(1965, 1)
AMEND652 = MonthYear(1965, 9)
AMEND653 = MonthYear(1966, 1)
AMEND671 = MonthYear(1968, 1)
AMEND672 = MonthYear(1968, 2)
AMEND69 = MonthYear(1970, 1)
AMEND70 = MonthYear(1971, 1)
AMEND721 = MonthYear(1972, 9)
AMEND722 = MonthYear(1973, 1)
AMEND741 = MonthYear(1974, 3)
AMEND742 = MonthYear(1974, 6)
AMEND771 = MonthYear(1978, 12)
AMEND772 = MonthYear(1979, 1)
AMEND80 = MonthYear(1980, 7)
AMEND811 = date(1919, 9, 2)  # age-62-and-1-month boundary birthdate
AMEND812 = date(1916, 9, 2)
AMEND813 = MonthYear(1981, 9)
AMEND82 = MonthYear(1982, 6)
AMEND83 = MonthYear(1984, 1)
AMEND88 = MonthYear(1989, 1)
AMEND90 = MonthYear(1992, 6)
AMEND01 = MonthYear(2001, 7)

AGE_50 = Age(50)
AGE_60 = Age(60)
AGE_62 = Age(62)
AGE_62_1 = Age(62, 1)
AGE_65 = Age(65)
AGE_67 = Age(67)
AGE_70 = Age(70)
AGE_72 = Age(72)
AGE_199 = Age(199)

MAX_MONTHS_AR_62_65 = 36
AR_MONTHLY_OAB_62_65 = 5.0 / 900.0
AR_MONTHLY_SPOUSE_62_65 = 25.0 / 3600.0
AR_MONTHLY_65_67 = 5.0 / 1200.0
AR_FACTOR_WID_285 = 0.285

FACTOR_50 = 0.50
FACTOR_75 = 0.75
FACTOR_825 = 0.825
FACTOR_150 = 1.50
FACTOR_175 = 1.75


def month_beninc(year: int) -> int:
    """Month of the benefit increase for a year (0 if none).
    From PiaParams::initdata."""
    special = {1952: 9, 1954: 9, 1956: 11, 1959: 1, 1961: 8, 1965: 1,
               1968: 2, 1970: 1, 1971: 1, 1972: 9}
    if year in special:
        return special[year]
    if 1974 <= year <= 1982:
        return 6
    if year >= 1983:
        return 12
    return 0


def full_ret_age(elig_year: int) -> Age:
    """NRA by year of attaining age 62 (60 for widow(er)s)."""
    if elig_year < 2000:
        return AGE_65
    if elig_year < 2005:
        return Age(65, 2 * (elig_year - 1999))
    if elig_year < 2017:
        return Age(66)
    if elig_year < 2022:
        return Age(66, 2 * (elig_year - 2016))
    return AGE_67


def full_ret_age_di(elig_year: int, current_year: int) -> Age:
    """NRA for benefit calculations involving a disability freeze."""
    return AGE_65 if current_year < 2000 else full_ret_age(elig_year)


def ret_credit(elig_year: int) -> float:
    """Monthly delayed retirement credit rate."""
    if elig_year < 1979:
        return 1.0 / 1200.0
    if elig_year < 1987:
        return 1.0 / 400.0
    if elig_year < 2005:
        return float((elig_year - 1985) // 2) / 2400.0 + 1.0 / 400.0
    return 2.0 / 300.0


def max_dib_age(year: int) -> Age:
    """Maximum DI beneficiary age at end of a year."""
    if year < 2003:
        return AGE_65
    if year < 2008:
        return Age(65, 2 * (year - 2002))
    if year < 2021:
        return Age(66)
    if year < 2026:
        return Age(66, 2 * (year - 2020))
    return AGE_67


def early_age_oab(sex: int, kbirth: date) -> Age:
    """Earliest retirement age for an OAB or aged spouse; kbirth is the
    birthdate adjusted to the previous day. sex: 0 male, 1 female."""
    if sex == 0:
        if AMEND611 < kbirth:
            return AGE_62_1 if (AMEND811 < kbirth and kbirth.day != 1) else AGE_62
        elif AMEND612 < kbirth <= AMEND611:
            # age on 8/1961
            return _age_between(kbirth, AMEND61)
        else:
            return AGE_65
    else:
        if AMEND561 < kbirth:
            return AGE_62_1 if (AMEND811 < kbirth and kbirth.day != 1) else AGE_62
        elif AMEND562 < kbirth <= AMEND561:
            return _age_between(kbirth, AMEND56)
        else:
            return AGE_65


def _age_between(birth: date, when: MonthYear) -> Age:
    """DateMoyr - date: age attained at `when` by someone born `birth`."""
    months = (when.year - birth.year) * 12 + (when.month - birth.month)
    return Age(months // 12, months % 12)


def early_age_widow(benefit_date: MonthYear) -> Age:
    if benefit_date < AMEND56:
        return AGE_65
    if benefit_date < AMEND652:
        return AGE_62
    return AGE_60


def early_age_dis_widow(benefit_date: MonthYear) -> Age:
    return AGE_199 if benefit_date < AMEND672 else AGE_50


def months_ar(age: Age, full_ret: Age) -> int:
    return full_ret - age


def factor_ar(months_ardri: int) -> float:
    """Reduction factor for OAB or DIB: 5/9% for 36 months, 5/12% beyond."""
    if months_ardri <= MAX_MONTHS_AR_62_65:
        return 1.0 - float(months_ardri) * AR_MONTHLY_OAB_62_65
    excess = months_ardri - MAX_MONTHS_AR_62_65
    return (1.0 - float(MAX_MONTHS_AR_62_65) * AR_MONTHLY_OAB_62_65
            - float(excess) * AR_MONTHLY_65_67)


def factor_ar_aged_spouse(months_ardri: int) -> float:
    """Reduction factor for wife/husband: 25/36% then 5/12%."""
    if months_ardri < 0:
        return 0.0
    if months_ardri <= MAX_MONTHS_AR_62_65:
        return 1.0 - float(months_ardri) * AR_MONTHLY_SPOUSE_62_65
    excess = months_ardri - MAX_MONTHS_AR_62_65
    return (1.0 - float(MAX_MONTHS_AR_62_65) * AR_MONTHLY_SPOUSE_62_65
            - float(excess) * AR_MONTHLY_65_67)


def months_dri(
    full_ret_date: MonthYear,
    elig_year: int,
    dobadj: date,
    ent_date: MonthYear,
    benefit_date: MonthYear,
    full_ins_date: MonthYear,
) -> int:
    """Months of delayed retirement credit for an OAB
    (PiaParams::monthsDriCal)."""
    i3 = max(full_ret_date.index(), full_ins_date.index())
    i1 = max(i3, 0)
    dob_my = MonthYear(dobadj.year, dobadj.month)
    if elig_year <= 1975:
        i4 = dob_my.add_months(72 * 12).index()
        if elig_year >= 1974:
            i4 = min(i4, AMEND83.index())
    else:
        i4 = dob_my.add_months(70 * 12).index()
    i5 = ent_date.index()
    i6 = max(i3, MonthYear(ent_date.year, 1).index())
    i7 = benefit_date.index()
    if i4 <= i5:
        i2 = i4
    elif i4 <= i7 or benefit_date.year > ent_date.year:
        i2 = i5
    else:
        i2 = i6
    if ent_date < AMEND722:
        i2 = 0
    return max(i2 - i1, 0)


def factor_dri(months_ardri: int, elig_year: int) -> float:
    return 1.0 + float(months_ardri) * ret_credit(elig_year)


def months_ar_dis_widow(
    age: Age, benefit_date: MonthYear, full_ret: Age
) -> int:
    return (AGE_65 - age) if benefit_date < AMEND83 else (full_ret - AGE_60)


def factor_ar_dis_widow(months_ardri: int, ent_date: MonthYear) -> float:
    if ent_date < AMEND722:
        return 0.69167 - float(months_ardri - 60) * 43.0 / 19800.0
    if ent_date < AMEND83:
        return 0.715 - float(months_ardri - 60) * 43.0 / 24000.0
    return 0.715


def months_ar_widow(age: Age, benefit_date: MonthYear, full_ret: Age) -> int:
    if benefit_date < AMEND61:
        return 0
    if benefit_date < AMEND722:
        return (AGE_62 - age) if age < AGE_62 else 0
    return (full_ret - age) if age < full_ret else 0


def months_ar_aged_spouse(
    age: Age, benefit_date: MonthYear, full_ret: Age
) -> int:
    if benefit_date < AMEND56:
        return 0
    return (full_ret - age) if age < full_ret else 0


def factor_ar_widow(
    months_ardri: int, age: Age, benefit_date: MonthYear, full_ret: Age
) -> float:
    if benefit_date < AMEND722:
        return 1.0
    if not (age < full_ret):
        return 1.0
    max_months = full_ret - AGE_60
    ratio = float(months_ardri) / float(max_months)
    return 1.0 - ratio * AR_FACTOR_WID_285


def factor_aged_widow(
    months_ardri: int, age: Age, benefit_date: MonthYear
) -> float:
    if benefit_date < AMEND61:
        return FACTOR_75
    if benefit_date < AMEND722:
        if age.years >= 62:
            return FACTOR_825
        return FACTOR_825 - float(months_ardri) * 5.0 / 900.0
    return 1.0


def factor_dis_widow(benefit_date: MonthYear) -> float:
    return FACTOR_825 if benefit_date < AMEND722 else 1.0


def months_ar_di(oab_ent: MonthYear | None, oab_cess: MonthYear | None) -> int:
    """Months of prior-OAB reduction carried into a DIB."""
    if oab_ent is None or oab_cess is None:
        return 0
    return oab_cess.months_since(oab_ent)


def child_age_for_mf(benefit_date: MonthYear, is_disabled: bool) -> Age:
    if is_disabled:
        return AGE_199
    return Age(18) if benefit_date < AMEND813 else Age(16)


def max_child_age(
    benefit_date: MonthYear, is_disabled: bool, is_student: bool
) -> Age:
    if benefit_date < AMEND652:
        return Age(18)
    if not is_disabled:
        if is_student:
            return Age(22) if benefit_date < AMEND813 else Age(19)
        return Age(18)
    return AGE_199


def lump_sum() -> float:
    return 255.0


def deemed_qc_req(year: int) -> int:
    """QCs required for deemed insured status, by adjusted birth year
    (-1 if ineligible)."""
    if year < 1924:
        return 6
    if year < 1925:
        return 8
    if year < 1926:
        return 12
    if year < 1927:
        return 16
    if year < 1929:
        return 20
    return -1


def rib_lim(
    widow_ben: float, oab_pia: float, oab_ben: float, benefit_date: MonthYear
) -> float:
    """Widow(er) benefit limited by RIB-LIM (deceased was an OAB)."""
    if benefit_date < AMEND722:
        return widow_ben
    pia825 = round_benefit(FACTOR_825 * oab_pia, benefit_date.year)
    return min(widow_ben, max(pia825, oab_ben))


def spec_min_amount(at: MonthYear) -> float:
    """Amount per year of coverage in the special minimum."""
    if at < AMEND722:
        return 0.0
    if at < AMEND741:
        return 8.50
    if at < AMEND772:
        return 9.00
    return 11.50
