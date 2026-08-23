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

    def to_pia(self) -> str:
        lines: list[str] = []
        by, bm, bd = self.dob
        lines.append(f"01{self.ssn}{self.sex}{bm:02d}{bd:02d}{by:04d}")
        if self.death is not None:
            dy, dm, dd = self.death
            lines.append(f"02{dm:02d}{dd:02d}{dy:04d}")
        ey, em = self.ent if self.ent is not None else (0, 0)
        if self.joasdi == 2:
            # survivor: entitlement on line 03 is ignored; still emit type
            lines.append(f"03{self.joasdi}{em:02d}{ey:04d}")
        else:
            lines.append(f"03{self.joasdi}{em:02d}{ey:04d}")
        if self.bendate is not None:
            yy, mm = self.bendate
            lines.append(f"04{mm:02d}{yy:04d}")
        if self.onset is not None:
            lines.append("09" + _disab_period(self))
        if self.onset2 is not None:
            lines.append("10" + _disab_period2(self))
        if self.totalize:
            lines.append("131")
        if self.pubpen is not None:
            s = f"12{self.pubpen:10.2f}"
            if self.pubpen_date is not None:
                py, pm = self.pubpen_date
                s += f"{pm:02d}{py:04d}"
            lines.append(s)
        if self.earnings:
            years = sorted(self.earnings)
            first, last = years[0], years[-1]
            if set(years) != set(range(first, last + 1)):
                raise ValueError("earnings years must be contiguous (use 0.0)")
            ib, ie = self.earnings_span or (first, last)
            lines.append(f"06{ib:04d}{ie:04d}")
            # 07/08 must follow 06, which resets the entered span
            if self.proj_back:
                lines.append(f"07{self.proj_back}{self.perc_back:6.2f}{first:4d}")
            if self.proj_fwrd:
                lines.append(f"08{self.proj_fwrd}{self.perc_fwrd:6.2f}{last:4d}")
            if self.military:
                periods = "".join(
                    f"{sm:02d}{sy:04d}{em:02d}{ey:04d}"
                    for (sy, sm), (ey, em) in self.military
                )
                lines.append(f"11{periods}")
            if self.earn_types:
                digits = "".join(
                    str(self.earn_types.get(y, 0))
                    for y in range(first, last + 1)
                )
                lines.append(f"20{digits}")
            for block, start in enumerate(range(first, last + 1, 10)):
                chunk = range(start, min(start + 10, last + 1))
                row = "".join(f"{self.earnings[y]:11.2f}" for y in chunk)
                lines.append(f"{22 + block:02d}{row}")
        lines.append(
            f"40{self.istart:04d}{self.ialtbi}{self.ialtaw}{self.ibasch}"
        )
        if self.qctottd is not None:
            lines.append(f"95{self.qctottd:3d}{self.qctot51td:3d}")
        if self.earnings:
            years = sorted(self.earnings)
            ib, ie = self.earnings_span or (years[0], years[-1])
            if self.qcs_by_year is not None and ib <= min(ie, 1977):
                digits = "".join(
                    str(min(4, self.qcs_by_year.get(y, 0)))
                    for y in range(ib, min(ie, 1977) + 1)
                )
                lines.append(f"96{digits}")
            if self.childcare_years:
                bits = "".join(
                    "1" if y in self.childcare_years else "0"
                    for y in range(ib, ie + 1)
                )
                lines.append(f"97{bits}")
        for i, fam in enumerate(self.family):
            fy, fm, fd = fam.dob
            ey2, em2 = fam.ent
            s = f"{69 + i:02d}{fam.bic:<2s}{fm:02d}{fd:02d}{fy:04d}{em2:02d}{ey2:04d}"
            if fam.onset is not None:
                oy, om, od = fam.onset
                s += f"{om:02d}{od:02d}{oy:04d}"
            lines.append(s)
        return "\n".join(lines) + "\n"


def _disab_period(spec: CaseSpec) -> str:
    """Line 09 layout per DisabPeriod::parseString: onset mmddyyyy,
    prior entitlement mmyyyy, waiting period mmyyyy, then (for non-DI or
    ceased) cessation mmyyyy + pia + mfb."""
    oy, om, od = spec.onset  # type: ignore[misc]
    s = f"{om:02d}{od:02d}{oy:04d}"
    # for a current DIB, the period's entitlement is the DIB's own
    # entitlement date (piawrite writes it; piaread checks it)
    prior = spec.prior_ent
    if prior is None and spec.joasdi == 3:
        prior = spec.ent
    if prior is not None:
        pey, pem = prior
        s += f"{pem:02d}{pey:04d}"
    else:
        s += "000000"
    if spec.waitper is not None:
        wy, wm = spec.waitper
        s += f"{wm:02d}{wy:04d}"
    else:
        s += "000000"
    if spec.cessation is not None:
        cy, cm = spec.cessation
        s += f"{cm:02d}{cy:04d}{spec.cessation_pia:10.2f}{spec.cessation_mfb:10.2f}"
    return s


def _disab_period2(spec: CaseSpec) -> str:
    """Line 10: the earlier of two periods of disability. It has always
    ceased, so cessation date, PIA and MFB are always present."""
    oy, om, od = spec.onset2  # type: ignore[misc]
    s = f"{om:02d}{od:02d}{oy:04d}"
    if spec.prior_ent2 is not None:
        pey, pem = spec.prior_ent2
        s += f"{pem:02d}{pey:04d}"
    else:
        s += "000000"
    if spec.waitper2 is not None:
        wy, wm = spec.waitper2
        s += f"{wm:02d}{wy:04d}"
    else:
        s += "000000"
    if spec.cessation2 is not None:
        cy, cm = spec.cessation2
        s += (
            f"{cm:02d}{cy:04d}{spec.cessation2_pia:10.2f}"
            f"{spec.cessation2_mfb:10.2f}"
        )
    return s
