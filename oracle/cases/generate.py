"""Oracle test-case generator.

Produces, per sweep: cases/<sweep>/cases.pia (one big anypiab input file)
and cases/<sweep>/manifest.jsonl (one JSON line per case describing it).

Earnings patterns are defined relative to the AWI (fq) series from
goldens/params_alt2.json so cases stay meaningful across eras.

Usage: python3 generate.py <sweep> [...]   (or 'all')
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

ORACLE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORACLE))

from pia_writer import CaseSpec, FamilyMemberSpec  # noqa: E402

PARAMS = json.load(open(ORACLE / "goldens" / "params_alt2.json"))
AWI = {int(y): v["fq"] for y, v in PARAMS["years"].items() if v["fq"] is not None}
BASE = {
    int(y): v["base_oasdi"]
    for y, v in PARAMS["years"].items()
    if v["base_oasdi"] is not None
}
NRA = {
    int(y): tuple(v["nra"])
    for y, v in PARAMS["elig_years"].items()
    if v["nra"] is not None
}


def attain_month(dob: tuple[int, int, int], years: int, months: int = 0
                 ) -> tuple[int, int]:
    """Month in which age (years,months) is attained, using SSA's
    attain-on-day-before-birthday rule: born on the 1st attains in the
    prior month."""
    by, bm, bd = dob
    m = (by + years) * 12 + (bm - 1) + months
    if bd == 1:
        m -= 1
    return m // 12, m % 12 + 1


def add_months(ym: tuple[int, int], months: int) -> tuple[int, int]:
    y, m = ym
    t = y * 12 + (m - 1) + months
    return t // 12, t % 12 + 1


def earliest_oab(dob: tuple[int, int, int]) -> tuple[int, int]:
    """Earliest old-age entitlement: age 62, or age 62 and 1 month for
    anyone born after 2 September 1919 (1981 amendments; see
    PiaParams::earlyAgeOabCal)."""
    kbirth = (dob[0], dob[1], dob[2] - 1)
    extra = 1 if kbirth > (1919, 9, 2) else 0
    return attain_month(dob, 62, extra)


def summary_qcs(earn: dict[int, float]) -> tuple[int, int]:
    """(qctottd, qctot51td) for line 95: four quarters for each year with
    earnings, capped at the 1937-77 and 1951-77 maxima. Batch anypiab
    never derives pre-1978 quarters from earnings, so any case whose work
    history reaches back that far has to state them."""
    pre51 = min(56, 4 * sum(1 for y, v in earn.items() if y < 1951 and v > 0))
    p5177 = min(
        108, 4 * sum(1 for y, v in earn.items() if 1951 <= y <= 1977 and v > 0)
    )
    return pre51 + p5177, p5177


def earnings_pattern(kind: str, dob_year: int, last_year: int
                     ) -> dict[int, float]:
    """Annual OASDI earnings from age 22 (or pattern-specific) through
    last_year, in nominal dollars linked to the AWI."""
    age22 = dob_year + 22
    first = age22
    out: dict[int, float] = {}
    for y in range(first, last_year + 1):
        if y not in AWI:
            continue
        age = y - dob_year
        awi = AWI[y]
        if kind == "steady":
            amt = awi
        elif kind == "max":
            amt = BASE[y]
        elif kind == "half":
            amt = 0.5 * awi
        elif kind == "sporadic":
            amt = awi if (y // 3) % 2 == 0 else 0.0
        elif kind == "late_start":
            amt = 1.2 * awi if age >= 40 else 0.0
        elif kind == "early_quit":
            amt = 1.2 * awi if age <= 45 else 0.0
        elif kind == "declining":
            frac = max(0.3, 1.5 - 0.02 * (age - 25))
            amt = frac * awi
        elif kind == "supermax":
            # deliberately above the taxable maximum, so that a reform
            # moving the base moves the earnings that count
            amt = 2.5 * awi
        else:
            raise ValueError(kind)
        cap = amt if kind == "supermax" else min(amt, BASE[y])
        out[y] = round(cap, 2)
    # trim leading/trailing zeros but keep interior zeros (contiguity)
    years = [y for y in sorted(out) if out[y] > 0.0]
    if not years:
        return {}
    return {y: out[y] for y in range(years[0], years[-1] + 1)}


def retire_v1() -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    birth_years = [1937, 1943, 1950, 1955, 1957, 1960, 1965, 1975, 1990]
    patterns = ["steady", "max", "half", "sporadic", "late_start",
                "early_quit", "declining"]
    n = 0
    for by in birth_years:
        days = [15]
        if by == 1957:
            days = [1, 2, 15]
        for day in days:
            dob = (by, 3, day)
            elig_year = by + 62
            nra_y, nra_m = NRA.get(elig_year, (67, 0))
            for pat in patterns:
                # entitlement ages: earliest (62+1mo eff.), NRA, 70
                # earliest = first month throughout which age 62 is
                # attained: attainment month +1, except born on the 2nd
                # (attains on the 1st of the month).
                ent_ages = [
                    ("earliest",
                     add_months(attain_month(dob, 62), 0 if day == 2 else 1)),
                    ("nra", attain_month(dob, nra_y, nra_m)),
                    ("70", attain_month(dob, 70)),
                ]
                for age_label, ent in ent_ages:
                    for ben_label, bendate in (
                        ("ent", ent),
                        ("+1y", add_months(ent, 12)),
                    ):
                        n += 1
                        ssn = f"9{n:08d}"
                        earn = earnings_pattern(pat, by, ent[0] - 1)
                        if not earn:
                            continue
                        cases.append(CaseSpec(
                            case_id=(f"r1-{by}d{day}-{pat}-{age_label}"
                                     f"-{ben_label}"),
                            ssn=ssn, sex=n % 2, dob=dob, joasdi=1,
                            ent=ent, bendate=bendate, earnings=earn,
                        ))
    return cases


def dib_v1() -> list[CaseSpec]:
    """Disability sweep: single current period of disability, no prior
    entitlements, eligibility (onset) 1984+."""
    cases: list[CaseSpec] = []
    birth_years = [1955, 1960, 1965, 1970, 1975, 1980, 1985, 1990, 1995]
    patterns = ["steady", "max", "half", "sporadic", "late_start",
                "declining"]
    onset_ages = [30, 45, 58]
    n = 10000
    for by in birth_years:
        for pat in patterns:
            for oa in onset_ages:
                onset_year = by + oa
                if onset_year < 1984 or onset_year > 2024:
                    continue
                onset = (onset_year, 6, 15)
                waitper = (onset_year, 7)
                ent = (onset_year, 12)
                for ben_label, bendate in (
                    ("ent", ent),
                    ("+1y", add_months(ent, 12)),
                ):
                    earn = earnings_pattern(pat, by, onset_year)
                    if not earn:
                        continue
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"d1-{by}-{pat}-o{oa}-{ben_label}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=(by, 3, 15),
                        joasdi=3, ent=ent, bendate=bendate, earnings=earn,
                        onset=onset, waitper=waitper,
                    ))
    return cases


def surv_v1() -> list[CaseSpec]:
    """Survivor sweep: deaths before/after 62, widow(er)s aged and
    disabled, young families, divorced widows."""
    from pia_writer import FamilyMemberSpec

    cases: list[CaseSpec] = []
    birth_years = [1950, 1960, 1970, 1985]
    death_ages = [35, 45, 55, 61, 65, 70]
    patterns = ["steady", "max", "half"]
    n = 20000
    for by in birth_years:
        for da in death_ages:
            dy = by + da
            if dy < 1985 or dy > 2025:
                continue
            death = (dy, 8, 20)
            for pat in patterns:
                earn = earnings_pattern(pat, by, dy)
                if not earn:
                    continue
                death_my = (dy, 8)
                # family configurations
                configs: list[tuple[str, list[FamilyMemberSpec]]] = []
                # aged widow, born 3 years after worker, ent at 60+1m
                wby = by + 3
                w60 = ((wby + 60) * 12 + (5 - 1) + 1)
                w60_ym = (w60 // 12, w60 % 12 + 1)
                went = max(w60_ym, death_my)
                configs.append(("agedwid", [
                    FamilyMemberSpec("D ", (wby, 6, 10), went),
                ]))
                # disabled widow at 52, onset 1 year before ent
                w52 = ((wby + 52) * 12 + (5 - 1) + 1)
                w52_ym = (w52 // 12, w52 % 12 + 1)
                went2 = max(w52_ym, death_my)
                onset_w = (went2[0] - 1, went2[1], 5)
                configs.append(("diswid", [
                    FamilyMemberSpec("W ", (wby, 6, 10), went2, onset_w),
                ]))
                # young mother + 2 children at death
                cby = dy - 6
                configs.append(("young", [
                    FamilyMemberSpec("E ", (by + 4, 2, 25), death_my),
                    FamilyMemberSpec("C1", (cby, 4, 1), death_my),
                    FamilyMemberSpec("C2", (cby - 3, 9, 9), death_my),
                ]))
                # child only
                configs.append(("child", [
                    FamilyMemberSpec("C1", (cby, 4, 1), death_my),
                ]))
                # aged widow + ineligible divorced widow
                configs.append(("divwid", [
                    FamilyMemberSpec("D ", (wby, 6, 10), went),
                    FamilyMemberSpec("D6", (wby - 2, 3, 4), went),
                ]))
                for label, fam in configs:
                    ents = [f.ent for f in fam]
                    latest = max(ents)
                    for ben_label, bendate in (
                        ("ent", latest), ("+1y", add_months(latest, 12)),
                    ):
                        # widow ents must be valid vs benefit date ages
                        n += 1
                        cases.append(CaseSpec(
                            case_id=(f"s1-{by}-d{da}-{pat}-{label}"
                                     f"-{ben_label}"),
                            ssn=f"9{n:08d}", sex=n % 2, dob=(by, 3, 15),
                            joasdi=2, ent=None, bendate=bendate,
                            death=death, earnings=earn, family=fam,
                        ))
    return cases


def fam_v1() -> list[CaseSpec]:
    """Life cases with auxiliaries: OAB + aged spouse / young family."""
    from pia_writer import FamilyMemberSpec

    cases: list[CaseSpec] = []
    n = 30000
    for by in [1955, 1960, 1963]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        for pat in ["steady", "max", "half"]:
            earn = earnings_pattern(pat, by, ent[0] - 1)
            if not earn:
                continue
            sby = by + 2
            s62 = ((sby + 62) * 12 + (7 - 1) + 1)
            spouse_ent = max((s62 // 12, s62 % 12 + 1), ent)
            s65 = ((sby + 65) * 12 + (7 - 1))
            spouse_ent65 = max((s65 // 12, s65 % 12 + 1), ent)
            cby = ent[0] - 8
            configs = [
                ("spouse62", [FamilyMemberSpec("B ", (sby, 7, 20),
                                               spouse_ent)]),
                ("spouse65", [FamilyMemberSpec("B ", (sby, 7, 20),
                                               spouse_ent65)]),
                ("youngfam", [
                    FamilyMemberSpec("B2", (by + 20, 1, 15), ent),
                    FamilyMemberSpec("C1", (cby, 4, 1), ent),
                    FamilyMemberSpec("C2", (cby + 2, 9, 9), ent),
                ]),
                ("kids", [
                    FamilyMemberSpec("C1", (cby, 4, 1), ent),
                    FamilyMemberSpec("C2", (cby + 2, 9, 9), ent),
                ]),
            ]
            for label, fam in configs:
                latest = max([f.ent for f in fam] + [ent])
                for ben_label, bendate in (
                    ("ent", latest), ("+1y", add_months(latest, 12)),
                ):
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"f1-{by}-{pat}-{label}-{ben_label}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                        ent=ent, bendate=bendate, earnings=earn,
                        family=fam,
                    ))
    return cases


def hist_v1() -> list[CaseSpec]:
    """Historical cohorts: pre-1951 earnings driving the old-start method,
    pre-1979 eligibility driving the PIA table, and 1979-1983 eligibility
    driving the transitional guarantee.

    Old-start needs at least one pre-1951 QC, so every case here starts
    earning in 1937 (the first year of the AWI series).
    """
    from pia_writer import FamilyMemberSpec

    cases: list[CaseSpec] = []
    patterns = ["steady", "max", "half", "sporadic", "declining"]
    n = 40000

    # Old-start / PIA-table cohorts: entitlement at 62, 65 and 68.
    for by in [1900, 1905, 1910, 1915, 1918, 1922, 1925, 1928]:
        dob = (by, 3, 15)
        for pat in patterns:
            for age_label, age in (("62", 62), ("65", 65), ("68", 68)):
                ent = earliest_oab(dob) if age == 62 else attain_month(dob, age)
                if ent[0] < 1940:
                    continue
                earn = earnings_pattern(pat, by, ent[0] - 1)
                if not earn or min(earn) > 1950:
                    continue
                qct, qc51 = summary_qcs(earn)
                for ben_label, bendate in (
                    ("ent", ent), ("+5y", add_months(ent, 60)),
                ):
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"h1-{by}-{pat}-e{age_label}-{ben_label}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                        ent=ent, bendate=bendate, earnings=earn,
                        qctottd=qct, qctot51td=qc51,
                    ))

    # Transitional guarantee: eligibility (age 62) in 1979-1983, which is
    # births 1917-1921, entitled at 62 or at NRA 65.
    for by in [1917, 1918, 1919, 1920, 1921]:
        dob = (by, 3, 15)
        for pat in patterns:
            for age_label, age in (("62", 62), ("65", 65), ("70", 70)):
                ent = earliest_oab(dob) if age == 62 else attain_month(dob, age)
                earn = earnings_pattern(pat, by, ent[0] - 1)
                if not earn:
                    continue
                qct, qc51 = summary_qcs(earn)
                for ben_label, bendate in (
                    ("ent", ent), ("+5y", add_months(ent, 60)),
                ):
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"h1t-{by}-{pat}-e{age_label}-{ben_label}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                        ent=ent, bendate=bendate, earnings=earn,
                        qctottd=qct, qctot51td=qc51,
                    ))

    # Survivor and disability variants of the same eras, so the historical
    # methods are exercised outside the old-age path too.
    for by in [1905, 1912, 1918]:
        dob = (by, 3, 15)
        for pat in ["steady", "half"]:
            for da in (58, 66):
                dy = by + da
                if dy < 1940:
                    continue
                earn = earnings_pattern(pat, by, dy)
                if not earn or min(earn) > 1950:
                    continue
                qct, qc51 = summary_qcs(earn)
                death = (dy, 8, 20)
                wby = by + 3
                w60 = ((wby + 60) * 12 + (5 - 1) + 1)
                went = max((w60 // 12, w60 % 12 + 1), (dy, 8))
                fam = [FamilyMemberSpec("D ", (wby, 6, 10), went)]
                for ben_label, bendate in (
                    ("ent", went), ("+5y", add_months(went, 60)),
                ):
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"h1s-{by}-{pat}-d{da}-{ben_label}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=2,
                        ent=None, bendate=bendate, death=death,
                        earnings=earn, family=fam,
                        qctottd=qct, qctot51td=qc51,
                    ))
    cases.extend(_old_start_pifc_cases(19000))
    return cases


def _old_start_pifc_cases(n: int) -> list[CaseSpec]:
    """Old-start winners whose PIA formula code is not the default.

    Pifc::pifcCal returns 'O' for the 1977 old-start on the frozen 1978
    table and '8' for the 1990 variant, where every other old-start
    winner gets 'B'. Nothing in the sweeps distinguished them, so the
    port returned 'B' for all of them and stayed penny-exact. Birth from
    1916 with eligibility after 1978 is what selects OS1977_79; the
    earlier cohorts here are controls that must keep giving 'B'.
    """
    cases: list[CaseSpec] = []
    for by in (1913, 1915, 1917, 1920):
        for ent_year, ben_year in ((1979, 1979), (1980, 1992), (1985, 1995)):
            if ent_year < by + 62:
                continue  # not yet 62, which the calculator refuses
            for pre51 in (18000.0, 30000.0):
                n += 1
                # heavy pre-1951 earnings and thin ones after, so the
                # old-start method is the one that wins
                earn = {y: round(pre51 / 13, 2) for y in range(1937, 1951)}
                earn.update({
                    y: 900.0 for y in range(1951, min(ent_year, 1978))
                })
                cases.append(CaseSpec(
                    case_id=f"h1os-{by}-{ent_year}-{ben_year}-{int(pre51)}",
                    ssn=f"9{n:08d}", sex=0, dob=(by, 3, 15), joasdi=1,
                    ent=(ent_year, 6), bendate=(ben_year, 6), earnings=earn,
                    qctottd=40, qctot51td=20,
                ))
    return cases


def special_v1() -> list[CaseSpec]:
    """The methods the other sweeps never reach: the disability guarantee
    (every conversion variant), the child-care dropout method, and long
    low-earning careers where the special minimum can win."""
    cases: list[CaseSpec] = []
    n = 50000

    # --- disability guarantee -------------------------------------------
    # Each row is a prior period of disability that ceased, followed by a
    # later entitlement. The variants cover DibGuar's five conversion
    # types: whether the new entitlement is before or after January 1996,
    # whether benefits were continuous within 12 months, and whether the
    # prior eligibility was before 1979.
    dg = [
        # (label, birth, onset, dib_ent, cessation, later_kind, gap_months)
        ("pre96-pre79", 1928, (1975, 6, 15), (1975, 12), (1985, 6), "oab", 1),
        ("pre96-post78", 1928, (1980, 6, 15), (1980, 12), (1985, 6), "oab", 1),
        ("pre96-gap", 1928, (1980, 6, 15), (1980, 12), (1985, 6), "oab", 48),
        ("post95-oab", 1950, (1995, 6, 15), (1995, 12), (2005, 6), "oab", 1),
        ("post95-oab-old", 1950, (1978, 6, 15), (1978, 12), (2005, 6),
         "oab", 1),
        ("post95-surv", 1950, (1995, 6, 15), (1995, 12), (2005, 6), "surv", 1),
    ]
    for label, by, onset, dib_ent, cess, kind, gap in dg:
        dob = (by, 3, 15)
        for pat in ["steady", "half"]:
            earn = earnings_pattern(pat, by, onset[0] - 1)
            if not earn:
                continue
            if kind == "oab":
                ent = max(add_months(cess, gap), earliest_oab(dob))
                fam: list = []
                joasdi, death = 1, None
            else:
                ent = add_months(cess, gap)
                death = (ent[0], ent[1], 20)
                wby = by + 3
                w60 = ((wby + 60) * 12 + (5 - 1) + 1)
                went = max((w60 // 12, w60 % 12 + 1), (ent[0], ent[1]))
                fam = [FamilyMemberSpec("D ", (wby, 6, 10), went)]
                ent = went
                joasdi = 2
            for ben_label, bendate in (
                ("ent", ent), ("+1y", add_months(ent, 12)),
            ):
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1dg-{label}-{pat}-{ben_label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=joasdi,
                    ent=None if joasdi == 2 else ent, bendate=bendate,
                    death=death, earnings=earn, family=fam,
                    onset=onset, waitper=add_months(onset[:2], 1),
                    prior_ent=dib_ent, cessation=cess,
                    cessation_pia=900.00, cessation_mfb=1350.00,
                ))

    # --- child-care dropout years ---------------------------------------
    # The extra dropout is only available when the ordinary dropout has
    # not already used up all three, which means a short working life:
    # a worker disabled young.
    for by in [1980, 1985, 1990]:
        for onset_age in (26, 29, 32):
            onset_year = by + onset_age
            if onset_year > 2024:
                continue
            dob = (by, 3, 15)
            first = by + 22
            # earn in every year but the last three, which are child-care
            # years with no earnings at all
            earn = {}
            care = []
            for y in range(first, onset_year):
                if y >= onset_year - 3:
                    earn[y] = 0.0
                    care.append(y)
                else:
                    earn[y] = round(AWI.get(y, 0.0), 2)
            if len(earn) < 4 or not care:
                continue
            onset = (onset_year, 6, 15)
            ent = (onset_year, 12)
            for ben_label, bendate in (
                ("ent", ent), ("+1y", add_months(ent, 12)),
            ):
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1cc-{by}-o{onset_age}-{ben_label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=3,
                    ent=ent, bendate=bendate, earnings=earn,
                    onset=onset, waitper=(onset_year, 7),
                    childcare_years=care,
                ))

    # --- long low-earning careers (special minimum) ----------------------
    for by in [1940, 1950, 1955]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        for frac_label, frac in (("q", 0.25), ("t", 0.33), ("h", 0.5)):
            earn = {
                y: round(frac * AWI[y], 2)
                for y in range(by + 22, ent[0])
                if y in AWI
            }
            if not earn:
                continue
            for ben_label, bendate in (
                ("ent", ent), ("+1y", add_months(ent, 12)),
            ):
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1sm-{by}-{frac_label}-{ben_label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                    ent=ent, bendate=bendate, earnings=earn,
                ))
    return cases


def total_v1() -> list[CaseSpec]:
    """Totalization cases: too few US quarters to compute a PIA from
    directly, so the PIA is built from an artificial earnings record and
    then pro-rated by the share of the computation period covered."""
    cases: list[CaseSpec] = []
    n = 60000
    for by in [1940, 1950, 1955, 1960]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        # a short stretch of US work at various levels, then nothing
        for span_label, start_age, span in (
            ("short", 30, 3), ("mid", 35, 6), ("long", 25, 9),
        ):
            for frac_label, frac in (("h", 0.5), ("s", 1.0)):
                first = by + start_age
                earn = {
                    y: round(frac * AWI[y], 2)
                    for y in range(first, first + span)
                    if y in AWI
                }
                if len(earn) < span:
                    continue
                # relEarnPositionCal reads the per-year quarter array,
                # so a totalization case needs annual quarters rather
                # than the line-95 lump
                qcs = {y: 4 for y, v in earn.items() if v > 0 and y <= 1977}
                for age_label, ent in (
                    ("62", earliest_oab(dob)),
                    ("nra", attain_month(dob, nra_y, nra_m)),
                ):
                    for ben_label, bendate in (
                        ("ent", ent), ("+1y", add_months(ent, 12)),
                    ):
                        n += 1
                        cases.append(CaseSpec(
                            case_id=(f"t1-{by}-{span_label}-{frac_label}"
                                     f"-e{age_label}-{ben_label}"),
                            ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                            ent=ent, bendate=bendate, earnings=earn,
                            totalize=True,
                            qcs_by_year=qcs if qcs else None,
                        ))
    return cases


def proj_v1() -> list[CaseSpec]:
    """Earnings that are projected rather than entered year by year, the
    steady earnings types (maximum/high/average/low), and military
    service wage credits."""
    cases: list[CaseSpec] = []
    n = 70000

    # backward and forward projection from a short entered stretch
    for by in [1940, 1955, 1960, 1975]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        span = (by + 22, ent[0] - 1)
        if span[0] < 1937 or span[1] > 2100:
            continue
        mid = (span[0] + span[1]) // 2
        entered = {y: round(AWI[y], 2) for y in range(mid - 2, mid + 3)
                   if y in AWI}
        if len(entered) < 5:
            continue
        for label, pb, pcb, pf, pcf in (
            ("awi", 1, 0.0, 1, 0.0),
            ("awi-plus", 1, 1.50, 1, 2.00),
            ("const", 2, 3.00, 2, 4.00),
            ("fwrd-only", 0, 0.0, 1, 0.0),
            ("back-only", 1, 0.0, 0, 0.0),
        ):
            # with no backward projection the record starts where the
            # entered earnings do
            lo = span[0] if pb else min(entered)
            hi = span[1] if pf else max(entered)
            qct, qc51 = summary_qcs({y: 1.0 for y in range(lo, hi + 1)})
            n += 1
            cases.append(CaseSpec(
                case_id=f"p1-{by}-{label}",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=ent, earnings=entered,
                earnings_span=(lo, hi),
                proj_back=pb, perc_back=pcb, proj_fwrd=pf, perc_fwrd=pcf,
                qctottd=qct if lo <= 1977 else None, qctot51td=qc51,
            ))

    # steady earnings types across a whole career
    for by in [1950, 1960, 1970]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        lo, hi = by + 22, ent[0] - 1
        years = [y for y in range(lo, hi + 1) if y in AWI]
        if not years:
            continue
        for label, code in (("max", 1), ("high", 2), ("avg", 3), ("low", 4)):
            earn = {y: 0.0 for y in years}
            types = {y: code for y in years}
            qct, qc51 = summary_qcs({y: 1.0 for y in years})
            n += 1
            cases.append(CaseSpec(
                case_id=f"p1t-{by}-{label}",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=ent, earnings=earn, earn_types=types,
                qctottd=qct if years[0] <= 1977 else None, qctot51td=qc51,
            ))

    # military service wage credits, in each of the three credit eras
    for by, periods, label in (
        (1925, [((1944, 6), (1946, 8))], "ww2"),
        (1930, [((1951, 3), (1954, 11))], "korea"),
        (1945, [((1966, 1), (1969, 6))], "vietnam"),
        (1955, [((1979, 1), (1982, 12))], "post78"),
        (1930, [((1948, 1), (1949, 12)), ((1952, 4), (1955, 9))], "two"),
    ):
        dob = (by, 3, 15)
        ent = attain_month(dob, 65)
        earn = earnings_pattern("half", by, ent[0] - 1)
        if not earn:
            continue
        qct, qc51 = summary_qcs(earn)
        for ben_label, bendate in (("ent", ent), ("+5y", add_months(ent, 60))):
            n += 1
            cases.append(CaseSpec(
                case_id=f"p1m-{label}-{ben_label}",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=bendate, earnings=earn,
                military=periods, qctottd=qct, qctot51td=qc51,
            ))
    return cases


def pebs_v1() -> list[CaseSpec]:
    """Social Security Statement cases.

    Restricted to workers already at full retirement age, because batch
    anypiab cannot compute a Statement below that: it runs a disability
    estimate whose pebsSetup never sets the waiting-period date, while
    freezeYearsCal reads it, so the freeze period inverts and the quarter
    arithmetic underflows.
    """
    cases: list[CaseSpec] = []
    n = 80000
    istart = 2026
    for by in [1935, 1940, 1945, 1950, 1953, 1955, 1958]:
        dob = (by, 3, 15)
        for pat in ["steady", "max", "half", "sporadic", "declining"]:
            earn = earnings_pattern(pat, by, istart - 1)
            if not earn:
                continue
            qct, qc51 = summary_qcs(earn)
            for month in (1, 6, 11):
                for age_plan in (0, 62, 65, 70):
                    n += 1
                    cases.append(CaseSpec(
                        case_id=f"b1-{by}-{pat}-m{month}-a{age_plan}",
                        ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=4,
                        ent=(istart, month), bendate=(istart, month),
                        earnings=earn,
                        pebs_month=month, pebs_age_plan=age_plan,
                        qctottd=qct if min(earn) <= 1977 else None,
                        qctot51td=qc51,
                        ialtbi=5, ialtaw=5,
                    ))
    return cases


def reform_v1() -> list[CaseSpec]:
    """The cases every reform variant is run over.

    Picked so each supported change bites somewhere: cohorts either side
    of every step in the retirement-age schedule, entitlement at 62 and
    at 70 so a raised age changes both the reduction and the credit, max
    earners for the wage base, disability onsets before and after 2010
    for the dropout rule, and auxiliaries because a changed retirement
    age moves their reduction factors too.
    """
    from pia_writer import FamilyMemberSpec

    cases: list[CaseSpec] = []
    n = 60000

    # --- retirement, across the whole retirement-age schedule ---------
    for by in [1935, 1940, 1943, 1950, 1955, 1957, 1960, 1965, 1975,
               1985, 1995]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        for pat in ["steady", "max", "half", "supermax"]:
            for label, ent in [
                ("earliest", add_months(attain_month(dob, 62), 1)),
                ("nra", attain_month(dob, nra_y, nra_m)),
                ("70", attain_month(dob, 70)),
            ]:
                earn = earnings_pattern(pat, by, ent[0] - 1)
                if not earn:
                    continue
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1-{by}-{pat}-{label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                    ent=ent, bendate=ent, earnings=earn,
                ))

    # --- disability, entitlements either side of 2010 -----------------
    for by in [1955, 1960, 1970, 1980, 1990]:
        for pat in ["steady", "supermax"]:
            for oa in [30, 45, 58]:
                onset_year = by + oa
                if onset_year < 1990 or onset_year > 2024:
                    continue
                earn = earnings_pattern(pat, by, onset_year)
                if not earn:
                    continue
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1d-{by}-{pat}-o{oa}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=(by, 3, 15),
                    joasdi=3, ent=(onset_year, 12),
                    bendate=(onset_year, 12), earnings=earn,
                    onset=(onset_year, 6, 15), waitper=(onset_year, 7),
                ))

    # --- an aged spouse, whose reduction a raised age changes ---------
    for by in [1950, 1955, 1960]:
        dob = (by, 3, 15)
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        for pat in ["steady", "max"]:
            earn = earnings_pattern(pat, by, ent[0] - 1)
            if not earn:
                continue
            sby = by + 2
            s62 = (sby + 62) * 12 + (7 - 1) + 1
            spouse_ent = max((s62 // 12, s62 % 12 + 1), ent)
            n += 1
            cases.append(CaseSpec(
                case_id=f"x1f-{by}-{pat}-spouse62",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=max(spouse_ent, ent), earnings=earn,
                family=[FamilyMemberSpec("B ", (sby, 7, 20), spouse_ent)],
            ))

    # --- child-care years with low, not zero, earnings ----------------
    # Disability cases, because a full career already spends all three
    # dropout years on the ordinary ones and leaves nothing for child
    # care. Present law drops only a year with no earnings at all, so the
    # child-care years here sit either side of the shares a reform names.
    for by in [1960, 1970, 1980]:
        dob = (by, 3, 15)
        for onset_age in [30, 38]:
            onset_year = by + onset_age
            if onset_year < 1990 or onset_year > 2024:
                continue
            for frac_label, frac in (("lo", 0.2), ("mid", 0.4)):
                earn: dict[int, float] = {}
                care: list[int] = []
                for y in range(by + 22, onset_year):
                    if y not in AWI:
                        continue
                    if y >= onset_year - 3:
                        earn[y] = round(frac * AWI[y], 2)
                        care.append(y)
                    else:
                        earn[y] = round(min(AWI[y], BASE[y]), 2)
                if len(earn) < 4 or not care:
                    continue
                n += 1
                cases.append(CaseSpec(
                    case_id=f"x1cc-{by}-o{onset_age}-{frac_label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=3,
                    ent=(onset_year, 12), bendate=(onset_year, 12),
                    earnings=earn, onset=(onset_year, 6, 15),
                    waitper=(onset_year, 7), childcare_years=care,
                ))

    # --- an aged widow, for the survivor reduction factors ------------
    for by in [1950, 1960]:
        for pat in ["steady", "max"]:
            dy = by + 61
            earn = earnings_pattern(pat, by, dy)
            if not earn:
                continue
            death_my = (dy, 8)
            wby = by + 3
            w60 = (wby + 60) * 12 + (5 - 1) + 1
            went = max((w60 // 12, w60 % 12 + 1), death_my)
            n += 1
            cases.append(CaseSpec(
                case_id=f"x1s-{by}-{pat}-agedwid",
                ssn=f"9{n:08d}", sex=n % 2, dob=(by, 3, 15),
                joasdi=2, ent=None, bendate=went,
                death=(dy, 8, 20), earnings=earn,
                family=[FamilyMemberSpec("D ", (wby, 6, 10), went)],
            ))

    return cases


def freeze_v1() -> list[CaseSpec]:
    """Cases where the disability freeze actually bites, and cases with
    two of them.

    The non-freeze computation answers "what if the freeze had not
    applied", so the only cases that can tell it apart from the ordinary
    one are those with earnings inside a freeze window. No other sweep
    has any, and none has a second period of disability either, which is
    how a defect in exactly that branch survived every suite.
    """
    cases: list[CaseSpec] = []
    n = 70000

    def career(first: int, last: int) -> dict[int, float]:
        return {
            y: round(min(AWI[y], BASE[y]), 2)
            for y in range(first, last + 1) if y in AWI
        }

    # --- a current disability, still earning after onset ---------------
    for by in [1955, 1965, 1975]:
        dob = (by, 3, 15)
        for onset_age in [40, 50]:
            onset_year = by + onset_age
            if not 1990 <= onset_year <= 2015:
                continue
            earn = career(by + 22, min(onset_year + 8, 2025))
            if len(earn) < 4:
                continue
            ent = (onset_year, 12)
            for ben_label, months in (("ent", 0), ("+2y", 24)):
                n += 1
                cases.append(CaseSpec(
                    case_id=f"z1-{by}-o{onset_age}-{ben_label}",
                    ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=3,
                    ent=ent, bendate=add_months(ent, months), earnings=earn,
                    onset=(onset_year, 6, 15), waitper=(onset_year, 7),
                ))

    # --- a period that ceased, then old age, earning throughout --------
    # The cessation amounts vary because DisabPeriod stores them as a C
    # float: 900.00 and 1350.00 are exact in single precision and so
    # cannot show a port that keeps full double precision, whereas
    # 2048.40 and 3072.60 are not.
    for by in [1950, 1958]:
        dob = (by, 3, 15)
        onset_year = by + 45
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        earn = career(by + 22, ent[0] - 1)
        if len(earn) < 4:
            continue
        for amt_label, cpia, cmfb in (
            ("exact", 900.00, 1350.00),
            ("inexact", 2048.40, 3072.60),
        ):
            n += 1
            cases.append(CaseSpec(
                case_id=f"z1c-{by}-ceased-{amt_label}",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=ent, earnings=earn,
                onset=(onset_year, 6, 15), waitper=(onset_year, 7),
                prior_ent=(onset_year, 12), cessation=(onset_year + 6, 6),
                cessation_pia=cpia, cessation_mfb=cmfb,
            ))

    # --- two periods of disability (valdi == 2) ------------------------
    for by in [1950, 1960]:
        dob = (by, 3, 15)
        early, late = by + 32, by + 48
        nra_y, nra_m = NRA.get(by + 62, (67, 0))
        ent = attain_month(dob, nra_y, nra_m)
        earn = career(by + 22, ent[0] - 1)
        if len(earn) < 4:
            continue
        for gap_label, late_cess_years in (("short", 5), ("long", 8)):
            n += 1
            cases.append(CaseSpec(
                case_id=f"z1t-{by}-two-{gap_label}",
                ssn=f"9{n:08d}", sex=n % 2, dob=dob, joasdi=1,
                ent=ent, bendate=ent, earnings=earn,
                # line 09 is the later period, line 10 the earlier one
                onset=(late, 6, 15), waitper=(late, 7),
                prior_ent=(late, 12),
                cessation=(late + late_cess_years, 6),
                cessation_pia=2048.40, cessation_mfb=3072.60,
                onset2=(early, 6, 15), waitper2=(early, 7),
                prior_ent2=(early, 12), cessation2=(early + 4, 6),
                cessation2_pia=900.00, cessation2_mfb=1350.00,
            ))
    return cases


SWEEPS = {
    "retire_v1": retire_v1,
    "dib_v1": dib_v1,
    "surv_v1": surv_v1,
    "fam_v1": fam_v1,
    "hist_v1": hist_v1,
    "special_v1": special_v1,
    "total_v1": total_v1,
    "proj_v1": proj_v1,
    "pebs_v1": pebs_v1,
    "reform_v1": reform_v1,
    "freeze_v1": freeze_v1,
}


ALTERNATIVES = (1, 2, 3)


def _write_atomically(path: pathlib.Path, text: str) -> None:
    """Write via a temporary file and rename.

    Writing in place truncates before the first byte is produced, so a
    failure part way through -- pyanypia not importable, say -- leaves a
    committed fixture empty and the repository dirty. Nothing should be
    able to corrupt a golden input by being run wrong.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_sweep(name: str) -> int:
    """Writes the sweep's manifest and one case file per Trustees
    alternative. The cases themselves are identical; only the assumption
    indicators on line 40 differ, so the same record is costed under all
    three sets of projections."""
    cases = SWEEPS[name]()
    outdir = pathlib.Path(__file__).resolve().parent / name
    outdir.mkdir(parents=True, exist_ok=True)
    # Statement cases carry their own assumption indicator and
    # UserAssumptions::pebsasmCheck refuses a Trustees alternative for
    # them, so they are costed under one set of assumptions only.
    takes_alts = all(c.ialtbi in ALTERNATIVES for c in cases)
    for alt in ALTERNATIVES if takes_alts else (2,):
        filename = "cases.pia" if alt == 2 else f"cases_alt{alt}.pia"
        _write_atomically(outdir / filename, "".join(
            (
                dataclasses.replace(c, ialtbi=alt, ialtaw=alt)
                if takes_alts else c
            ).to_pia()
            for c in cases
        ))
    _write_atomically(outdir / "manifest.jsonl", "".join(
        json.dumps(dataclasses.asdict(c)) + "\n" for c in cases
    ))
    print(f"{name}: {len(cases)} cases")
    return len(cases)


if __name__ == "__main__":
    names = sys.argv[1:] or ["retire_v1"]
    if names == ["all"]:
        names = list(SWEEPS)
    for nm in names:
        write_sweep(nm)
