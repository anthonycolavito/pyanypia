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


SWEEPS = {"retire_v1": retire_v1, "dib_v1": dib_v1}


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
