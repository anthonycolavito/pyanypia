"""Minimal .pia case-file writer for oracle test-case generation.

Field layouts follow oracle/vendor/oactobjs32/piadata/piaread.cpp exactly:
  01  ssn(9) sex(1) dob mmddyyyy(8)
  02  death date mmddyyyy(8)
  03  benefit type(1) entitlement mmyyyy(6)
  04  benefit date mmyyyy(6)
  06  first(4) last(4) years of earnings (the full record)
  07  backward projection: type(1) percent(6) first entered year(4)
  08  forward projection: type(1) percent(6) last entered year(4)
  11  military service: 12 chars per period, mmyyyy start + mmyyyy end
  20  earnings type per entered year, one digit each
  09  disability period 1 (DisabPeriod.parseString layout)
  10  disability period 2 (the earlier period, same layout)
  12  noncovered pension amount(10) [start mmyyyy(6)]
  13  totalization indicator (1 digit, nonzero = totalization case)
  22+ OASDI earnings, 10 per line, 11 chars each, %11.2f
  40  assumptions: istart(4) ialtbi(1) ialtaw(1) ibasch(1)
  69+ family members: bic(2) dob(8) entitlement mmyyyy(6) [onset(8) if W]
  95  summary quarters of coverage: qctottd(3) 1937-77, qctot51td(3) 1951-77
  96  annual quarters of coverage: one digit per year, first year to 1977
  97  child-care years: one digit per year of earnings, 1 = child in care
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FamilyMemberSpec:
    bic: str  # 2 chars, e.g. "B ", "C1", "D ", "W "
    dob: tuple[int, int, int]  # (year, month, day)
    ent: tuple[int, int]  # (year, month)
    onset: tuple[int, int, int] | None = None  # for W (disabled widow)


@dataclass
class CaseSpec:
    case_id: str
    ssn: str  # 9 digits
    sex: int  # 0 male, 1 female
    dob: tuple[int, int, int]  # (year, month, day)
    joasdi: int  # 1 old-age, 2 survivor, 3 disability, 4 statement
    ent: tuple[int, int] | None  # (year, month); ignored for survivor
    bendate: tuple[int, int] | None = None  # (year, month)
    death: tuple[int, int, int] | None = None
    earnings: dict[int, float] = field(default_factory=dict)
    onset: tuple[int, int, int] | None = None  # disability onset
    waitper: tuple[int, int] | None = None  # first month of waiting period
    prior_ent: tuple[int, int] | None = None  # disab prior entitlement
    cessation: tuple[int, int] | None = None
    cessation_pia: float = 0.0
    cessation_mfb: float = 0.0
    # second (earlier) period of disability, written on line 10
    onset2: tuple[int, int, int] | None = None
    waitper2: tuple[int, int] | None = None
    prior_ent2: tuple[int, int] | None = None
    cessation2: tuple[int, int] | None = None
    cessation2_pia: float = 0.0
    cessation2_mfb: float = 0.0
    childcare_years: list[int] = field(default_factory=list)
    pubpen: float | None = None
    pubpen_date: tuple[int, int] | None = None
    totalize: bool = False
    # full span of the record (line 06) when projection widens it beyond
    # the entered years; earnings rows 22+ always cover the entered span
    earnings_span: tuple[int, int] | None = None
    proj_back: int = 0
    perc_back: float = 0.0
    proj_fwrd: int = 0
    perc_fwrd: float = 0.0
    earn_types: dict[int, int] = field(default_factory=dict)
    military: list[tuple[tuple[int, int], tuple[int, int]]] = field(
        default_factory=list
    )
    family: list[FamilyMemberSpec] = field(default_factory=list)
    # summary quarters of coverage (line 95). qctottd covers 1937-1977 and
    # qctot51td covers 1951-1977, so their difference is the pre-1951 total
    # that OldStart::isApplicable keys on. Batch anypiab never derives these
    # from pre-1951 earnings, so old-start cases must state them.
    qctottd: int | None = None
    qctot51td: int = 0
    # annual quarters of coverage (line 96), one entry per year from the
    # first year of earnings through 1977. Supplying these instead of the
    # line-95 lump is what totalization needs, because relEarnPositionCal
    # reads the per-year array.
    qcs_by_year: dict[int, int] | None = None
    istart: int = 2026
    ialtbi: int = 2
    ialtaw: int = 2
    ibasch: int = 1

    def to_worker(self):  # type: ignore[no-untyped-def]
        """The pyanypia Worker this case describes."""
        from datetime import date as _date

        from pyanypia import (
            BenefitType,
            DisabilityPeriod,
            FamilyMember,
            MonthYear,
            Worker,
        )
        from pyanypia.worker import EarningsProjection, MilitaryService

        def moyr(v):  # type: ignore[no-untyped-def]
            return MonthYear(*v) if v else None

        periods = []
        if self.onset is not None:
            prior = self.prior_ent
            if prior is None and self.joasdi == 3:
                prior = self.ent
            periods.append(DisabilityPeriod(
                onset=_date(*self.onset),
                first_entitlement=moyr(prior),
                waiting_period_start=moyr(self.waitper),
                cessation=moyr(self.cessation),
                cessation_pia=self.cessation_pia,
                cessation_mfb=self.cessation_mfb,
            ))
        if self.onset2 is not None:
            periods.append(DisabilityPeriod(
                onset=_date(*self.onset2),
                first_entitlement=moyr(self.prior_ent2),
                waiting_period_start=moyr(self.waitper2),
                cessation=moyr(self.cessation2),
                cessation_pia=self.cessation2_pia,
                cessation_mfb=self.cessation2_mfb,
            ))
        entered = sorted(self.earnings)
        projection = None
        if self.proj_back or self.proj_fwrd or self.earn_types:
            projection = EarningsProjection(
                proj_back=self.proj_back,
                perc_back=self.perc_back,
                first_year=entered[0] if entered else 0,
                proj_fwrd=self.proj_fwrd,
                perc_fwrd=self.perc_fwrd,
                last_year=entered[-1] if entered else 0,
                earn_types=dict(self.earn_types),
            )
        span = self.earnings_span
        if span is None and entered:
            span = (entered[0], entered[-1])
        return Worker(
            dob=_date(*self.dob),
            sex=self.sex,
            benefit_type=BenefitType(self.joasdi),
            earnings=dict(self.earnings),
            earnings_span=span,
            projection=projection,
            military_service=tuple(
                MilitaryService(MonthYear(*s), MonthYear(*e))
                for s, e in self.military
            ),
            entitlement=moyr(self.ent),
            benefit_date=moyr(self.bendate),
            death_date=_date(*self.death) if self.death else None,
            qcs_by_year=dict(self.qcs_by_year or {}),
            childcare_years=frozenset(self.childcare_years),
            qc_total_to_date=self.qctottd or 0,
            qc_total_51_to_date=self.qctot51td,
            disability_periods=tuple(periods),
            noncovered_pension=self.pubpen or 0.0,
            noncovered_pension_date=moyr(self.pubpen_date),
            totalize=self.totalize,
            family=tuple(
                FamilyMember(
                    bic=f.bic,
                    dob=_date(*f.dob),
                    entitlement=MonthYear(*f.ent),
                    disability_onset=_date(*f.onset) if f.onset else None,
                )
                for f in self.family
            ),
        )

    def to_pia(self) -> str:
        """Renders the case with the package's own .pia writer, so the
        oracle inputs and the shipped writer cannot drift apart."""
        from pyanypia.io import PiaCase, write_case
        from pyanypia.io.pia_file import AssumptionSpec

        if self.earnings:
            years = sorted(self.earnings)
            if set(years) != set(range(years[0], years[-1] + 1)):
                raise ValueError("earnings years must be contiguous (use 0.0)")
        return write_case(PiaCase(
            worker=self.to_worker(),
            assumptions=AssumptionSpec(
                istart=self.istart, ialtbi=self.ialtbi,
                ialtaw=self.ialtaw, ibasch=self.ibasch,
            ),
            ssn=self.ssn,
        ))
