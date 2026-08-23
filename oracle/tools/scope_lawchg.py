"""Which law changes actually move batch anypiab's output?

Task 23.3 asks which of the calculator's change types need porting. The
answer is not in the source -- several classes compute a changed value
that the batch path then never asks for -- so this measures it: switch
each one on over the reform_v1 cases and count how many answers move.

    python3 oracle/tools/scope_lawchg.py

Parameters are the smallest valid set each type's read() accepts; the
point is whether the type reaches the output at all, not what it does.

It runs over reform_v1 and special_v1 together, because a type can only
move a case that gives it something to work on -- the child-care changes
are inert against every case that names no child-care years, which would
read as the calculator ignoring them.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ORACLE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORACLE))

import lawchg_writer as lcw  # noqa: E402

SPAN = (1990, 2100)

# name -> the Change to switch on. Extras and lines are each type's own
# read() format; see the LawChange<name>.cpp of the same name.
CANDIDATES: dict[str, lcw.Change] = {
    # the four already ported, as positive controls
    "NRACHANGE": lcw.nra_change(1, *SPAN),
    "COLACHANGE": lcw.cola_change(-1.0, *SPAN, phase_type=1),
    "DIDROP5": lcw.di_dropout_five(*SPAN),
    # the subset task 23.3 names
    "AGE65COMP": lcw.Change("AGE65COMP", 1, *SPAN, extras=["1"]),
    "ALLEARN": lcw.Change("ALLEARN", 1, *SPAN),
    "CHILDCARECREDIT": lcw.Change(
        "CHILDCARECREDIT", 1, *SPAN, extras=["0.5", "6", "3", "0"]),
    "CHILDCAREDROPOUT": lcw.Change(
        "CHILDCAREDROPOUT", 1, *SPAN, extras=["0.5", "6", "3"]),
    "DECLINEPERC": lcw.Change(
        "DECLINEPERC", 1, *SPAN, extras=["88", "30", "14"]),
    "NEWSPECMIN": lcw.Change("NEWSPECMIN", 1, *SPAN, lines=["50.00"]),
    "TAXBENCHG": lcw.Change("TAXBENCHG", 1, *SPAN),
    "PSAACCT": lcw.Change(
        "PSAACCT", 1, *SPAN,
        # percToSpouse unisex intRate contribDist taxAnnuity annuityToDib
        # toSpouseOnDeath annuityOffset contribStartAge lumpSumPerc
        # numContribBps lumpSumAtFra buysAnnuity annuityType rebalance
        extras=["0.5", "0", "3.0", "0", "0", "0", "0", "0", "22", "0.0",
                "0", "0", "1", "0", "0"],
        lines=[
            # per investment (bonds, stocks): mean stddev adminFee mngmtFee
            "3.0 0.0 0.0 0.0 7.0 0.0 0.0 0.0",
            # contribution rates: year rate
            "1990 2.0",
        ],
    ),
    "NEWFORMULA": lcw.new_formula(
        percentages={y: [90.0, 32.0, 15.0] for y in range(2020, 2031)},
        num_bp=2,
        bend_points={y: [1000.0, 6000.0] for y in range(2020, 2031)},
        start_year=2020, end_year=2030,
    ),
}


def key(row: dict) -> tuple:
    """Everything the differential test compares. A change that only adds
    an applicable method still has to be ported, so the per-method values
    belong in here and not just the winning ones."""
    return (row.get("high_pia"), row.get("high_mfb"), row.get("high_method"),
            row.get("rounded_benefit"), row.get("support_pia"),
            row.get("pifc"), row.get("error"),
            tuple(sorted((m["method"], m["applicable"], m["ame"], m["pia"],
                          m["mfb"]) for m in row.get("methods", []))),
            tuple(sorted((s["bic"], s["rounded_benefit"])
                         for s in row.get("secondaries", []))))


SWEEPS = ("reform_v1", "special_v1")


def run(name: str, lawchg: str | None) -> list[dict] | str:
    wd = ORACLE / "work" / f"scope-{name}"
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "cases.pia").write_text("".join(
        (ORACLE / "cases" / s / "cases.pia").read_text() for s in SWEEPS
    ))
    path = wd / "lawchg.dat"
    if lawchg is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(lawchg)
    (wd / "output.jsonl").unlink(missing_ok=True)
    proc = subprocess.run(
        [str(ORACLE / "bin" / "anypiab-json")], input="cases\n",
        text=True, cwd=wd, capture_output=True,
    )
    if not (wd / "output.jsonl").exists():
        return proc.stderr.strip().splitlines()[-1] if proc.stderr else "no output"
    rows = [json.loads(line) for line in open(wd / "output.jsonl")]
    if lawchg is not None and "lawchg.dat applied" not in proc.stderr:
        return "lawchg.dat not read"
    return rows


def main() -> int:
    base = run("baseline", None)
    if isinstance(base, str):
        print(f"baseline failed: {base}")
        return 1
    print(f"{len(base)} cases\n")
    print(f"{'change type':18} {'moved':>7}   verdict")
    print("-" * 52)
    for name, change in CANDIDATES.items():
        got = run(name, lcw.write_lawchg([change], title=f"scope {name}"))
        if isinstance(got, str):
            print(f"{name:18} {'-':>7}   could not run: {got[:40]}")
            continue
        moved = sum(1 for b, r in zip(base, got, strict=False) if key(b) != key(r))
        verdict = "reaches the output" if moved else "never reaches the output"
        print(f"{name:18} {moved:>4}/{len(base):<3}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
