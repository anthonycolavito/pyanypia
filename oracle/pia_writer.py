"""Minimal .pia case-file writer for oracle test-case generation.

Field layouts follow oracle/vendor/oactobjs32/piadata/piaread.cpp exactly:
  01  ssn(9) sex(1) dob mmddyyyy(8)
  02  death date mmddyyyy(8)
  03  benefit type(1) entitlement mmyyyy(6)
  04  benefit date mmyyyy(6)
  06  first(4) last(4) years of earnings
  09  disability period 1 (DisabPeriod.parseString layout)
  12  noncovered pension amount(10) [start mmyyyy(6)]
  22+ OASDI earnings, 10 per line, 11 chars each, %11.2f
  40  assumptions: istart(4) ialtbi(1) ialtaw(1) ibasch(1)
  69+ family members: bic(2) dob(8) entitlement mmyyyy(6) [onset(8) if W]
  95  summary quarters of coverage: qctottd(3) 1937-77, qctot51td(3) 1951-77
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
    pubpen: float | None = None
    pubpen_date: tuple[int, int] | None = None
    family: list[FamilyMemberSpec] = field(default_factory=list)
    # summary quarters of coverage (line 95). qctottd covers 1937-1977 and
    # qctot51td covers 1951-1977, so their difference is the pre-1951 total
    # that OldStart::isApplicable keys on. Batch anypiab never derives these
    # from pre-1951 earnings, so old-start cases must state them.
    qctottd: int | None = None
    qctot51td: int = 0
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
        if self.pubpen is not None:
            s = f"12{self.pubpen:10.2f}"
            if self.pubpen_date is not None:
                py, pm = self.pubpen_date
                s += f"{pm:02d}{py:04d}"
            lines.append(s)
        if self.earnings:
            years = sorted(self.earnings)
            ib, ie = years[0], years[-1]
            if set(years) != set(range(ib, ie + 1)):
                raise ValueError("earnings years must be contiguous (use 0.0)")
            lines.append(f"06{ib:04d}{ie:04d}")
            for block, start in enumerate(range(ib, ie + 1, 10)):
                chunk = range(start, min(start + 10, ie + 1))
                row = "".join(f"{self.earnings[y]:11.2f}" for y in chunk)
                lines.append(f"{22 + block:02d}{row}")
        lines.append(
            f"40{self.istart:04d}{self.ialtbi}{self.ialtaw}{self.ibasch}"
        )
        if self.qctottd is not None:
            lines.append(f"95{self.qctottd:3d}{self.qctot51td:3d}")
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
