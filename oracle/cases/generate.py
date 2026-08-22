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

from pia_writer import CaseSpec  # noqa: E402

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
        else:
            raise ValueError(kind)
        out[y] = round(min(amt, BASE[y]), 2)
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
    for i, by in enumerate(birth_years):
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


SWEEPS = {
    "retire_v1": retire_v1,
    "dib_v1": dib_v1,
    "surv_v1": surv_v1,
    "fam_v1": fam_v1,
}


def write_sweep(name: str) -> int:
    cases = SWEEPS[name]()
    outdir = pathlib.Path(__file__).resolve().parent / name
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "cases.pia", "w") as f:
        for c in cases:
            f.write(c.to_pia())
    with open(outdir / "manifest.jsonl", "w") as f:
        for c in cases:
            f.write(json.dumps(dataclasses.asdict(c)) + "\n")
    print(f"{name}: {len(cases)} cases")
    return len(cases)


if __name__ == "__main__":
    names = sys.argv[1:] or ["retire_v1"]
    if names == ["all"]:
        names = list(SWEEPS)
    for nm in names:
        write_sweep(nm)
