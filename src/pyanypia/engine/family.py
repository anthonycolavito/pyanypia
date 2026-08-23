"""Family (auxiliary and survivor) benefits: Secondary factors,
age reductions, family-maximum distribution (PiaCal aux logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from pyanypia.dates import Age, MonthYear
from pyanypia.engine.context import CalcContext
from pyanypia.errors import PiaError
from pyanypia.params import retire_age
from pyanypia.rounding import round_benefit, round_to_dollar
from pyanypia.worker import BenefitType, FamilyMember

PIA_IDS_ARDRI4 = 61291
PIA_IDS_ARDRI5 = 61292
PIA_IDS_ARDRI6 = 61293
PIA_IDS_ARDRI10 = 61297
PIA_IDS_JSURV = 61305
PIA_IDS_BENDATE6 = 61236
PIA_IDS_SECONDARY = 61340
PIA_IDS_DEATH1 = 61237  # birth after death etc.
PIA_IDS_DEATH3 = 61239  # family entitlement before death

SURVIVOR_BICS = frozenset("CDEFW")


@dataclass
class SecondaryState:
    """One family member's benefit computation (Secondary)."""

    member: FamilyMember
    kbirth: date = field(init=False)
    kbirth_my: MonthYear = field(init=False)
    age_ent: Age | None = None
    full_ret_age: Age | None = None
    early_ret_age: Age | None = None
    elig_year: int = 0
    benefit_factor: float = 0.0
    months_ardri: int = 0
    arf: float = 0.0
    full_benefit: float = 0.0
    benefit: float = 0.0  # after family max
    reduced_benefit: float = 0.0
    rounded_benefit: float = 0.0
    pifc: str = " "

    def __post_init__(self) -> None:
        from datetime import timedelta

        self.kbirth = self.member.dob - timedelta(days=1)
        self.kbirth_my = MonthYear(self.kbirth.year, self.kbirth.month)

    @property
    def major_bic(self) -> str:
        c = self.member.bic[0]
        return "U" if c == "T" else c

    @property
    def minor_bic(self) -> str:
        return self.member.bic[1] if len(self.member.bic) > 1 else " "

    def is_reducible(self) -> bool:
        return (
            self.major_bic in ("D", "W", "A")
            or (self.major_bic == "B" and self.minor_bic != "2")
        )

    def is_widow(self) -> bool:
        return self.major_bic in ("D", "W")

    def is_young_spouse(self) -> bool:
        return self.major_bic == "B" and self.minor_bic == "2"

    def eligible_for_max(self) -> bool:
        return self.minor_bic != "6"

    def check_bic(self) -> None:
        if self.major_bic == " ":
            raise PiaError(PIA_IDS_SECONDARY, "missing bic")


def data_check_aux(
    ctx: CalcContext, secondaries: list[SecondaryState]
) -> None:
    """PiaCal::dataCheckAux."""
    w = ctx.worker
    assert w.benefit_date is not None
    for s in secondaries:
        if s.major_bic == " ":
            break
        if w.benefit_date < s.member.entitlement:
            raise PiaError(PIA_IDS_BENDATE6, "family ent after benefit date")
    if ctx.ioasdi == BenefitType.SURVIVOR:
        assert w.death_date is not None
        if w.death_date < w.dob:
            raise PiaError(PIA_IDS_DEATH1, "death before birth")
        death_my = MonthYear.from_date(w.death_date)
        for s in secondaries:
            if s.major_bic == " ":
                break
            if s.major_bic not in SURVIVOR_BICS:
                raise PiaError(PIA_IDS_JSURV, f"bad survivor bic {s.major_bic}")
            if s.member.entitlement < death_my:
                raise PiaError(PIA_IDS_DEATH3, "survivor ent before death")
    for s in secondaries:
        s.check_bic()
        if s.is_reducible():
            months = s.member.entitlement.index() - s.kbirth_my.index()
            s.age_ent = Age(months // 12, months % 12)
            if s.major_bic == "W":
                onset = s.member.disability_onset
                if onset is None or onset < s.member.dob:
                    raise PiaError(61306, "widow onset missing/before birth")
                if s.member.entitlement < MonthYear.from_date(onset):
                    raise PiaError(61307, "widow onset after entitlement")
    # widow eligibility years
    set_elig_year_widow(secondaries)
    # benefit factors and reductions
    for s in secondaries:
        if s.major_bic == " ":
            break
        ardri_aux_cal(ctx, s)


def set_elig_year_widow(secondaries: list[SecondaryState]) -> None:
    """PiaCal::setEligYearWidow / eligYearWidowCal."""
    for s in secondaries:
        if s.is_widow():
            kb = s.kbirth_my.year
            if s.major_bic == "W":
                onset = s.member.disability_onset
                assert onset is not None
                s.elig_year = max(onset.year, kb + 50)
            else:
                s.elig_year = kb + 60


def ardri_aux_cal(ctx: CalcContext, s: SecondaryState) -> None:
    """PiaCal::ardriAuxCal."""
    w = ctx.worker
    assert w.benefit_date is not None
    ben_date = w.benefit_date
    if ctx.ioasdi in (BenefitType.OLD_AGE, BenefitType.DISABILITY):
        if s.major_bic == "B" and not s.is_young_spouse():
            s.early_ret_age = ctx.params.early_age_oab(0, s.kbirth)
            assert s.age_ent is not None
            if s.age_ent < s.early_ret_age:
                raise PiaError(PIA_IDS_ARDRI10, "aged spouse too young")
            s.full_ret_age = ctx.params.full_ret_age(s.kbirth_my.year + 62)
            s.months_ardri = retire_age.months_ar_aged_spouse(
                s.age_ent, ben_date, s.full_ret_age
            )
            s.benefit_factor = retire_age.FACTOR_50
            s.arf = ctx.params.factor_ar_aged_spouse(s.months_ardri)
            return
        if s.major_bic in ("B", "C"):
            s.months_ardri = 0
            s.benefit_factor = retire_age.FACTOR_50
            return
        raise PiaError(PIA_IDS_JSURV, "invalid life auxiliary bic")
    # survivors
    if s.major_bic in ("C", "E"):
        s.months_ardri = 0
        s.benefit_factor = retire_age.FACTOR_75
        return
    if s.major_bic == "W":
        s.early_ret_age = retire_age.early_age_dis_widow(ben_date)
        assert s.age_ent is not None
        if s.age_ent < s.early_ret_age:
            raise PiaError(PIA_IDS_ARDRI4, "disabled widow too young")
        if not s.age_ent < retire_age.early_age_widow(ben_date):
            raise PiaError(PIA_IDS_ARDRI5, "disabled widow too old")
        s.full_ret_age = ctx.params.full_ret_age(s.kbirth_my.year + 60)
        s.months_ardri = retire_age.months_ar_dis_widow(
            s.age_ent, ben_date, s.full_ret_age
        )
        s.benefit_factor = ctx.params.factor_dis_widow(ben_date)
        s.arf = retire_age.factor_ar_dis_widow(
            s.months_ardri, s.member.entitlement
        )
        return
    if s.major_bic == "D":
        s.early_ret_age = retire_age.early_age_widow(ben_date)
        assert s.age_ent is not None
        if s.age_ent < s.early_ret_age:
            raise PiaError(PIA_IDS_ARDRI6, "aged widow too young")
        s.full_ret_age = ctx.params.full_ret_age(s.kbirth_my.year + 60)
        s.months_ardri = retire_age.months_ar_widow(
            s.age_ent, ben_date, s.full_ret_age
        )
        s.benefit_factor = ctx.params.factor_aged_widow(
            s.months_ardri, s.age_ent, ben_date
        )
        s.arf = retire_age.factor_ar_widow(
            s.months_ardri, s.age_ent, ben_date, s.full_ret_age
        )
        return
    raise PiaError(PIA_IDS_JSURV, "invalid survivor bic")


def apply_mfb(
    secondaries: list[SecondaryState], ratio: float, year: int
) -> None:
    """PiaCal::applyMfb."""
    if ratio > 1.0:
        ratio = 1.0
    if ratio < 0.0:
        ratio = 0.0
    for s in secondaries:
        if s.eligible_for_max():
            s.benefit = round_benefit(ratio * s.full_benefit, year)
        else:
            s.benefit = s.full_benefit


def pia_cal3(
    ctx: CalcContext,
    secondaries: list[SecondaryState],
    widow_pias: dict[int, float],
) -> None:
    """PiaCal::piaCal3 — family benefits with maximum and reductions.

    ``widow_pias`` maps secondary index -> re-indexed widow(er) PIA for
    widows where that method applies.
    """
    w = ctx.worker
    assert w.benefit_date is not None
    i1 = w.benefit_date.year
    if i1 >= 1951 and w.benefit_date.month < ctx.params.month_beninc(i1):
        i1 -= 1
    for s in secondaries:
        s.pifc = ctx.pifc
        s.full_benefit = round_benefit(
            ctx.high_pia * s.benefit_factor, i1
        )
    for idx, wid_pia in widow_pias.items():
        if ctx.high_pia < wid_pia:
            s = secondaries[idx]
            s.pifc = "W"
            s.full_benefit = round_benefit(wid_pia * s.benefit_factor, i1)
    total_full = sum(
        s.full_benefit for s in secondaries if s.eligible_for_max()
    )
    if ctx.ioasdi == BenefitType.SURVIVOR:
        ratio = ctx.high_mfb / total_full if total_full > 0.0 else 1.0
    else:
        ratio = (
            (ctx.high_mfb - ctx.high_pia) / total_full
            if total_full > 0.0 else 1.0
        )
    apply_mfb(secondaries, ratio, i1)
    for s in secondaries:
        if s.is_reducible():
            s.reduced_benefit = round_benefit(s.arf * s.benefit, i1)
        else:
            s.reduced_benefit = s.benefit
        s.rounded_benefit = round_to_dollar(
            s.reduced_benefit, w.benefit_date
        )
