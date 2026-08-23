"""Reader and writer for SSA's ``.pia`` case files (piaread.cpp,
piareadAny.cpp, piawrite.cpp, piawriteAny.cpp).

A ``.pia`` file is a sequence of records, each opening with a type-01 line
and running to the next one. Every line begins with a two-digit type; the
rest is fixed-width, and a line's meaning often depends on lines that came
before it (the earnings rows are indexed from the span line 06 sets, which
lines 07 and 08 then narrow).

Anything the calculator does not consume — the worker's name and address,
the assumption titles — is carried through unchanged so a file can be read
and written back without losing it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from pyanypia.dates import MonthYear
from pyanypia.errors import PiaError
from pyanypia.worker import (
    BenefitType,
    DisabilityPeriod,
    EarningsProjection,
    FamilyMember,
    MilitaryService,
    Worker,
)

PIA_IDS_READERR = 62012
EARN_WIDTH = 11
LINE_WIDTH = 2


@dataclass(frozen=True)
class AssumptionSpec:
    """Lines 40-68: which assumption set to use, plus any user-supplied
    paths. ``ialtbi``/``ialtaw`` of 1-3 select a Trustees Report
    alternative; 4 means the paths given here are used instead."""

    istart: int = 0
    ialtbi: int = 2
    ialtaw: int = 2
    ibasch: int = 1
    biproj: dict[int, float] = field(default_factory=dict)
    awincproj: dict[int, float] = field(default_factory=dict)
    catchup: dict[tuple[int, int], float] = field(default_factory=dict)
    base_oasdi: dict[int, float] = field(default_factory=dict)
    base_77: dict[int, float] = field(default_factory=dict)
    title_bi: str = ""
    title_aw: str = ""


@dataclass(frozen=True)
class PiaCase:
    """One record from a ``.pia`` file."""

    worker: Worker
    assumptions: AssumptionSpec = field(default_factory=AssumptionSpec)
    ssn: str = ""
    name: str = ""
    address: tuple[str, ...] = ()
    # line 05: the month the Statement is prepared in and the age the
    # worker plans to retire at (0 for none)
    statement_month: int = 0
    statement_age_plan: int = 0


# ---------------------------------------------------------------- reading


def _int(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        # atoi() stops at the first non-digit rather than failing
        digits = ""
        for ch in s.lstrip():
            if ch.isdigit() or (ch == "-" and not digits):
                digits += ch
            else:
                break
        return int(digits) if digits.lstrip("-") else 0


def _float(s: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _month_year(s: str) -> MonthYear:
    """mmyyyy."""
    if len(s) < 6:
        raise PiaError(PIA_IDS_READERR, f"bad month/year {s!r}")
    return MonthYear(_int(s[2:6]), _int(s[0:2]))


def _date(s: str) -> date:
    """mmddyyyy."""
    if len(s) < 8:
        raise PiaError(PIA_IDS_READERR, f"bad date {s!r}")
    return date(_int(s[4:8]), _int(s[0:2]), _int(s[2:4]))


class _Record:
    """Mutable accumulator for one record, materialised into a PiaCase
    once the record ends."""

    def __init__(self) -> None:
        self.ssn = ""
        self.sex = 0
        self.dob: date | None = None
        self.death: date | None = None
        self.joasdi = 0
        self.entitlement: MonthYear | None = None
        self.benefit_date: MonthYear | None = None
        self.ibegin = 0
        self.iend = 0
        # the entered span, which lines 07/08 narrow within [ibegin, iend]
        self.first_entered = 0
        self.last_entered = 0
        self.proj_back = 0
        self.perc_back = 0.0
        self.proj_fwrd = 0
        self.perc_fwrd = 0.0
        self.earnings: dict[int, float] = {}
        self.earnings_hi: dict[int, float] = {}
        self.earn_types: dict[int, int] = {}
        self.tax_types: dict[int, int] = {}
        self.disability: list[DisabilityPeriod | None] = [None, None]
        self.military: list[MilitaryService] = []
        self.pubpen = 0.0
        self.pubpen_date: MonthYear | None = None
        self.reservist_pension: float | None = None
        self.totalize = False
        self.blind = False
        self.deemed = False
        self.oab_ent: MonthYear | None = None
        self.oab_cess: MonthYear | None = None
        self.name = ""
        self.address = ["", "", ""]
        self.family: list[FamilyMember] = []
        self.qctottd = 0
        self.qctot51td = 0
        self.qcs_by_year: dict[int, int] = {}
        self.childcare_years: list[int] = []
        self.assumptions = AssumptionSpec()
        self.istart2 = 0
        self.has_railroad = False
        self.statement_month = 0
        self.statement_age_plan = 0

    def worker(self) -> Worker:
        if self.dob is None:
            raise PiaError(PIA_IDS_READERR, "record has no type-01 line")
        periods = tuple(p for p in self.disability if p is not None)
        projection = None
        if self.proj_back or self.proj_fwrd or self.earn_types:
            projection = EarningsProjection(
                proj_back=self.proj_back,
                perc_back=self.perc_back,
                first_year=self.first_entered,
                proj_fwrd=self.proj_fwrd,
                perc_fwrd=self.perc_fwrd,
                last_year=self.last_entered,
                earn_types=dict(self.earn_types),
            )
        span = (self.ibegin, self.iend) if self.ibegin else None
        return Worker(
            dob=self.dob,
            sex=self.sex,
            benefit_type=BenefitType(self.joasdi),
            earnings=dict(self.earnings),
            earnings_span=span,
            projection=projection,
            military_service=tuple(self.military),
            entitlement=self.entitlement,
            benefit_date=self.benefit_date,
            death_date=self.death,
            earnings_hi=dict(self.earnings_hi),
            qcs_by_year=dict(self.qcs_by_year),
            childcare_years=frozenset(self.childcare_years),
            qc_total_to_date=self.qctottd,
            qc_total_51_to_date=self.qctot51td,
            disability_periods=periods,
            noncovered_pension=self.pubpen,
            noncovered_pension_date=self.pubpen_date,
            reservist_pension=self.reservist_pension,
            totalize=self.totalize,
            blind=self.blind,
            deemed_insured=self.deemed,
            oab_entitlement=self.oab_ent,
            oab_cessation=self.oab_cess,
            family=tuple(self.family),
        )

    def case(self) -> PiaCase:
        return PiaCase(
            worker=self.worker(),
            assumptions=self.assumptions,
            ssn=self.ssn,
            name=self.name,
            address=tuple(a for a in self.address if a),
            statement_month=self.statement_month,
            statement_age_plan=self.statement_age_plan,
        )


def _parse_line(rec: _Record, kind: int, body: str) -> None:
    """Applies one line to the record under construction."""
    if kind == 1:
        rec.ssn = body[0:9]
        rec.sex = _int(body[9:10])
        rec.dob = _date(body[10:18])
    elif kind == 2:
        rec.death = _date(body[0:8])
    elif kind == 3:
        rec.joasdi = _int(body[0:1])
        # a survivor case has no entitlement of its own
        if rec.joasdi != int(BenefitType.SURVIVOR):
            rec.entitlement = _month_year(body[1:7])
            rec.benefit_date = rec.entitlement
    elif kind == 4:
        rec.benefit_date = _month_year(body[0:6])
    elif kind == 5:
        rec.statement_month = _int(body[0:2])
        rec.statement_age_plan = _int(body[2:4])
    elif kind == 6:
        rec.ibegin = _int(body[0:4])
        rec.iend = _int(body[4:8])
        rec.first_entered, rec.last_entered = rec.ibegin, rec.iend
    elif kind == 7:
        rec.proj_back = _int(body[0:1])
        rec.perc_back = _float(body[1:7])
        rec.first_entered = _int(body[7:11])
    elif kind == 8:
        rec.proj_fwrd = _int(body[0:1])
        rec.perc_fwrd = _float(body[1:7])
        rec.last_entered = _int(body[7:11])
    elif kind in (9, 10):
        rec.disability[kind - 9] = _disab_period(body)
    elif kind == 11:
        rec.military = [
            MilitaryService(
                _month_year(body[12 * i:12 * i + 6]),
                _month_year(body[12 * i + 6:12 * i + 12]),
            )
            for i in range(len(body) // 12)
        ]
    elif kind == 12:
        rec.pubpen = _float(body[0:10])
        if len(body.rstrip()) >= 16:
            rec.pubpen_date = _month_year(body[10:16])
    elif kind == 13:
        rec.totalize = _int(body[0:1]) > 0
    elif kind == 14:
        rec.blind = _int(body[0:1]) > 0
    elif kind == 15:
        rec.deemed = _int(body[0:1]) > 0
    elif kind == 16:
        rec.name = body.rstrip()
    elif 17 <= kind <= 19:
        rec.address[kind - 17] = body.rstrip()
    elif kind == 20:
        for i, yr in enumerate(range(rec.first_entered, rec.last_entered + 1)):
            if i < len(body):
                rec.earn_types[yr] = _int(body[i:i + 1])
    elif kind == 21:
        for i, yr in enumerate(range(rec.ibegin, rec.iend + 1)):
            if i < len(body):
                rec.tax_types[yr] = _int(body[i:i + 1])
    elif 22 <= kind <= 29:
        first = rec.first_entered + 10 * (kind - 22)
        for i, yr in enumerate(range(first, min(first + 9, rec.last_entered) + 1)):
            rec.earnings[yr] = _float(body[EARN_WIDTH * i:EARN_WIDTH * (i + 1)])
    elif 30 <= kind <= 37:
        first = max(rec.ibegin, 1983) + 10 * (kind - 30)
        for i, yr in enumerate(range(first, min(first + 9, rec.iend) + 1)):
            rec.earnings_hi[yr] = _float(
                body[EARN_WIDTH * i:EARN_WIDTH * (i + 1)]
            )
    elif kind == 38:
        rec.reservist_pension = _float(body[0:10])
    elif kind == 39:
        rec.oab_ent = _month_year(body[0:6])
        rec.oab_cess = _month_year(body[6:12])
    elif kind == 40:
        rec.istart2 = _int(body[0:4])
        rec.assumptions = _replace_assumptions(
            rec,
            istart=rec.istart2,
            ialtbi=_int(body[4:5]),
            ialtaw=_int(body[5:6]),
            ibasch=_int(body[6:7]),
        )
    elif 41 <= kind <= 44:
        first = rec.istart2 + 20 * (kind - 41)
        last = min(first + 19, _ben_year(rec))
        vals = {
            yr: _float(body[4 * i:4 * (i + 1)])
            for i, yr in enumerate(range(first, last + 1))
        }
        rec.assumptions.biproj.update(vals)
    elif 45 <= kind <= 54:
        # eight catch-up increases per line, for one eligibility year
        cstart = rec.istart2
        elig = cstart + (kind - 45)
        for i in range(8):
            val = _float(body[4 + 4 * i:8 + 4 * i])
            if val:
                rec.assumptions.catchup[(elig, cstart + 2 + i)] = val
    elif kind == 55:
        rec.assumptions = _replace_assumptions(rec, title_bi=body.rstrip())
    elif 56 <= kind <= 59:
        first = rec.istart2 - 1 + 20 * (kind - 56)
        last = min(first + 19, _ben_year(rec))
        vals = {
            yr: _float(body[6 * i:6 * (i + 1)])
            for i, yr in enumerate(range(first, last + 1))
        }
        rec.assumptions.awincproj.update(vals)
    elif kind == 60:
        rec.assumptions = _replace_assumptions(rec, title_aw=body.rstrip())
    elif 61 <= kind <= 68:
        first = rec.istart2 + 1 + 20 * ((kind - 61) % 4)
        last = min(first + 19, _ben_year(rec))
        target = (
            rec.assumptions.base_oasdi if kind <= 64
            else rec.assumptions.base_77
        )
        for i, yr in enumerate(range(first, last + 1)):
            target[yr] = _float(body[EARN_WIDTH * i:EARN_WIDTH * (i + 1)])
    elif 69 <= kind <= 83:
        rec.family.append(_family_member(body))
    elif 84 <= kind <= 94:
        # railroad earnings; read so the file round-trips, but the engine
        # refuses a case that carries them
        rec.has_railroad = True
    elif kind == 95:
        rec.qctottd = _int(body[0:3])
        rec.qctot51td = _int(body[3:6])
    elif kind == 96:
        for i, yr in enumerate(range(rec.ibegin, min(rec.iend, 1977) + 1)):
            if i < len(body):
                rec.qcs_by_year[yr] = _int(body[i:i + 1])
    elif kind == 97:
        for i, yr in enumerate(range(rec.ibegin, rec.iend + 1)):
            if i < len(body) and body[i] == "1":
                rec.childcare_years.append(yr)
    else:
        raise PiaError(PIA_IDS_READERR, f"unknown line type {kind}")


def _ben_year(rec: _Record) -> int:
    return rec.benefit_date.year if rec.benefit_date else rec.istart2 + 19


def _replace_assumptions(rec: _Record, **kwargs: object) -> AssumptionSpec:
    a = rec.assumptions
    return AssumptionSpec(
        istart=kwargs.get("istart", a.istart),  # type: ignore[arg-type]
        ialtbi=kwargs.get("ialtbi", a.ialtbi),  # type: ignore[arg-type]
        ialtaw=kwargs.get("ialtaw", a.ialtaw),  # type: ignore[arg-type]
        ibasch=kwargs.get("ibasch", a.ibasch),  # type: ignore[arg-type]
        biproj=a.biproj,
        awincproj=a.awincproj,
        catchup=a.catchup,
        base_oasdi=a.base_oasdi,
        base_77=a.base_77,
        title_bi=kwargs.get("title_bi", a.title_bi),  # type: ignore[arg-type]
        title_aw=kwargs.get("title_aw", a.title_aw),  # type: ignore[arg-type]
    )


def _disab_period(body: str) -> DisabilityPeriod:
    """DisabPeriod::parseString."""
    onset = _date(body[0:8])
    ent = body[8:14]
    wait = body[14:20]
    cess = body[20:26] if len(body.rstrip()) >= 26 else ""
    return DisabilityPeriod(
        onset=onset,
        first_entitlement=_month_year(ent) if _int(ent[2:6]) else None,
        waiting_period_start=_month_year(wait) if _int(wait[2:6]) else None,
        cessation=_month_year(cess) if cess and _int(cess[2:6]) else None,
        cessation_pia=_float(body[26:36]) if len(body) >= 36 else 0.0,
        cessation_mfb=_float(body[36:46]) if len(body) >= 46 else 0.0,
    )


def _family_member(body: str) -> FamilyMember:
    bic = body[0:2]
    dob = _date(body[2:10])
    ent = _month_year(body[10:16])
    onset = None
    if bic.strip().upper()[:1] == "W" and len(body.rstrip()) >= 24:
        onset = _date(body[16:24])
    return FamilyMember(bic=bic, dob=dob, entitlement=ent,
                        disability_onset=onset)


def read_pia(text: str) -> list[PiaCase]:
    """Parses the contents of a ``.pia`` file into its records."""
    cases: list[PiaCase] = []
    rec: _Record | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        kind = _int(line[:LINE_WIDTH])
        body = line[LINE_WIDTH:]
        if kind == 1:
            if rec is not None:
                cases.append(rec.case())
            rec = _Record()
        if rec is None:
            raise PiaError(
                PIA_IDS_READERR,
                f"line {lineno}: type {kind} before any type-01 line",
            )
        try:
            _parse_line(rec, kind, body)
        except PiaError:
            raise
        except (ValueError, IndexError) as exc:
            raise PiaError(
                PIA_IDS_READERR, f"line {lineno}: {exc}"
            ) from exc
    if rec is not None:
        cases.append(rec.case())
    return cases


def read_pia_file(path: str | os.PathLike[str]) -> list[PiaCase]:
    """Reads a ``.pia`` file from disk."""
    with open(path, encoding="latin-1") as f:
        return read_pia(f.read())


# ---------------------------------------------------------------- writing


def _fmt_moyr(d: MonthYear) -> str:
    return f"{d.month:02d}{d.year:04d}"


def _fmt_date(d: date) -> str:
    return f"{d.month:02d}{d.day:02d}{d.year:04d}"


def write_case(case: PiaCase) -> str:
    """Renders one record in ``.pia`` form, in the line order piawrite
    uses. Only fields the calculator consumes are emitted, plus the name
    and address if the record carries them."""
    w = case.worker
    a = case.assumptions
    out: list[str] = []
    ssn = (case.ssn or "000000000")[:9]
    out.append(f"01{ssn}{w.sex}{_fmt_date(w.dob)}")
    if w.death_date is not None:
        out.append(f"02{_fmt_date(w.death_date)}")
    if case.statement_month:
        out.append(
            f"05{case.statement_month:02d}{case.statement_age_plan:02d}"
        )
    # a survivor case carries no entitlement of its own; the reader skips
    # this field for that benefit type, so zeros are what belongs here
    ent = _fmt_moyr(w.entitlement) if w.entitlement is not None else "000000"
    out.append(f"03{int(w.benefit_type)}{ent}")
    if w.benefit_date is not None:
        out.append(f"04{_fmt_moyr(w.benefit_date)}")
    for i, period in enumerate(w.disability_periods[:2]):
        out.append(f"{9 + i:02d}{_write_disab(period)}")
    if w.military_service:
        periods = "".join(
            _fmt_moyr(p.start) + _fmt_moyr(p.end) for p in w.military_service
        )
        out.append(f"11{periods}")
    if w.noncovered_pension:
        line = f"12{w.noncovered_pension:10.2f}"
        if w.noncovered_pension_date is not None:
            line += _fmt_moyr(w.noncovered_pension_date)
        out.append(line)
    if w.totalize:
        out.append("131")
    if w.blind:
        out.append("141")
    if w.deemed_insured:
        out.append("151")
    if case.name:
        out.append(f"16{case.name}")
    for i, addr in enumerate(case.address[:3]):
        out.append(f"{17 + i:02d}{addr}")
    if w.has_earnings:
        out.extend(_write_earnings(w))
    if w.reservist_pension is not None:
        out.append(f"38{w.reservist_pension:10.2f}")
    if w.oab_entitlement is not None and w.oab_cessation is not None:
        out.append(
            f"39{_fmt_moyr(w.oab_entitlement)}{_fmt_moyr(w.oab_cessation)}"
        )
    out.append(f"40{a.istart:04d}{a.ialtbi}{a.ialtaw}{a.ibasch}")
    if a.title_bi:
        out.append(f"55{a.title_bi}")
    if a.title_aw:
        out.append(f"60{a.title_aw}")
    for i, member in enumerate(w.family):
        line = (
            f"{69 + i:02d}{member.bic:<2s}{_fmt_date(member.dob)}"
            f"{_fmt_moyr(member.entitlement)}"
        )
        if member.disability_onset is not None:
            line += _fmt_date(member.disability_onset)
        out.append(line)
    if w.qc_total_to_date:
        out.append(f"95{w.qc_total_to_date:3d}{w.qc_total_51_to_date:3d}")
    if w.qcs_by_year:
        last = min(w.iend, 1977)
        if w.ibegin <= last:
            digits = "".join(
                str(min(4, w.qcs_by_year.get(y, 0)))
                for y in range(w.ibegin, last + 1)
            )
            out.append(f"96{digits}")
    if w.childcare_years:
        bits = "".join(
            "1" if y in w.childcare_years else "0"
            for y in range(w.ibegin, w.iend + 1)
        )
        out.append(f"97{bits}")
    return "\n".join(out) + "\n"


def _write_disab(period: DisabilityPeriod) -> str:
    s = _fmt_date(period.onset)
    s += (
        _fmt_moyr(period.first_entitlement)
        if period.first_entitlement is not None else "000000"
    )
    s += (
        _fmt_moyr(period.waiting_period_start)
        if period.waiting_period_start is not None else "000000"
    )
    if period.cessation is not None:
        s += _fmt_moyr(period.cessation)
        s += f"{period.cessation_pia:10.2f}{period.cessation_mfb:10.2f}"
    return s


def _write_earnings(w: Worker) -> list[str]:
    out: list[str] = []
    entered = sorted(w.earnings)
    first = entered[0] if entered else w.ibegin
    last = entered[-1] if entered else w.iend
    out.append(f"06{w.ibegin:04d}{w.iend:04d}")
    proj = w.projection
    if proj is not None:
        if proj.proj_back:
            out.append(f"07{proj.proj_back}{proj.perc_back:6.2f}{first:4d}")
        if proj.proj_fwrd:
            out.append(f"08{proj.proj_fwrd}{proj.perc_fwrd:6.2f}{last:4d}")
        if proj.earn_types and any(proj.earn_types.values()):
            digits = "".join(
                str(proj.earn_types.get(y, 0)) for y in range(first, last + 1)
            )
            out.append(f"20{digits}")
    for block, start in enumerate(range(first, last + 1, 10)):
        chunk = range(start, min(start + 10, last + 1))
        row = "".join(f"{w.earnings.get(y, 0.0):11.2f}" for y in chunk)
        out.append(f"{22 + block:02d}{row}")
    if w.earnings_hi:
        hi_first = max(w.ibegin, 1983)
        for block, start in enumerate(range(hi_first, w.iend + 1, 10)):
            chunk = range(start, min(start + 10, w.iend + 1))
            row = "".join(f"{w.earnings_hi.get(y, 0.0):11.2f}" for y in chunk)
            out.append(f"{30 + block:02d}{row}")
    return out


def write_pia(cases: list[PiaCase]) -> str:
    """Renders a whole ``.pia`` file."""
    return "".join(write_case(c) for c in cases)
