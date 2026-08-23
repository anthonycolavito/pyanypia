"""Runs the instrumented oracle over generated case sweeps -> goldens.

Usage: python3 run_oracle.py <sweep> [...]

Reads  cases/<sweep>/cases.pia
Writes goldens/<sweep>.jsonl   (one JSON object per case, in input order,
                                with the manifest's case_id joined in)
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

ORACLE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ORACLE))


def ensure_built() -> None:
    binary = ORACLE / "bin" / "anypiab-json"
    if not binary.exists():
        subprocess.run(
            ["make", "-C", str(ORACLE / "build"), "all"], check=True,
            capture_output=True,
        )


def run_sweep(name: str, alt: int = 2) -> None:
    ensure_built()
    casedir = ORACLE / "cases" / name
    suffix = "" if alt == 2 else f"_alt{alt}"
    workdir = ORACLE / "work" / f"run-{name}{suffix}"
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(casedir / f"cases{suffix}.pia", workdir / "cases.pia")
    proc = subprocess.run(
        [str(ORACLE / "bin" / "anypiab-json")], input="cases\n",
        text=True, cwd=workdir, capture_output=True,
    )
    if not (workdir / "output.jsonl").exists():
        raise RuntimeError(
            f"oracle produced no output for {name}: {proc.stderr[:500]}"
        )
    manifest = [
        json.loads(line) for line in open(casedir / "manifest.jsonl")
    ]
    results = [
        json.loads(line) for line in open(workdir / "output.jsonl")
    ]
    if len(results) != len(manifest):
        print(
            f"WARNING {name}: {len(manifest)} cases but "
            f"{len(results)} oracle results"
        )
    outpath = ORACLE / "goldens" / f"{name}{suffix}.jsonl"
    with open(outpath, "w") as f:
        # not strict: a case the oracle rejected outright still needs its
        # manifest row, and the length mismatch is reported above
        for spec, res in zip(manifest, results, strict=False):
            res["case_id"] = spec["case_id"]
            f.write(json.dumps(res) + "\n")
    n_err = sum(1 for r in results if "error" in r)
    print(f"{name}{suffix}: {len(results)} results ({n_err} errors) -> {outpath}")


PRESENT_LAW = "present_law"


def _run_cases(workdir: pathlib.Path, casedir: pathlib.Path,
               lawchg: str | None) -> tuple[list[dict], str]:
    """Runs the case file in a workdir, with `lawchg` written beside it
    when a reform is being applied. Returns (results, stderr)."""
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(casedir / "cases.pia", workdir / "cases.pia")
    lawchg_path = workdir / "lawchg.dat"
    if lawchg is None:
        lawchg_path.unlink(missing_ok=True)
    else:
        lawchg_path.write_text(lawchg)
    out = workdir / "output.jsonl"
    out.unlink(missing_ok=True)
    proc = subprocess.run(
        [str(ORACLE / "bin" / "anypiab-json")], input="cases\n",
        text=True, cwd=workdir, capture_output=True,
    )
    if not out.exists():
        raise RuntimeError(f"oracle produced no output: {proc.stderr[:500]}")
    return [json.loads(line) for line in open(out)], proc.stderr


def run_reform_sweep(name: str = "reform_v1") -> None:
    """Runs every reform variant over the sweep's cases, plus a
    present-law baseline, into one golden file.

    Two things are checked here rather than in the test, because both
    would otherwise show up as a suite that passes while proving
    nothing: that the calculator actually read each lawchg.dat, and that
    every variant moved at least one case off its present-law answer.
    """
    import reform_specs

    ensure_built()
    casedir = ORACLE / "cases" / name
    manifest = [json.loads(line) for line in open(casedir / "manifest.jsonl")]

    def key(row: dict) -> tuple:
        """Everything the differential test compares. A variant that only
        moves a method that never wins still has to be matched, so the
        per-method values belong here and not just the payable amount."""
        return (row.get("high_pia"), row.get("high_mfb"),
                row.get("high_method"), row.get("rounded_benefit"),
                row.get("support_pia"), row.get("pifc"), row.get("error"),
                tuple(sorted((m["method"], m["applicable"], m["ame"],
                              m["pia"], m["mfb"])
                             for m in row.get("methods", []))),
                tuple(sorted((s["bic"], s["rounded_benefit"])
                             for s in row.get("secondaries", []))))

    baseline, _ = _run_cases(
        ORACLE / "work" / f"run-{name}-baseline", casedir, None
    )
    if len(baseline) != len(manifest):
        raise RuntimeError(
            f"{name} baseline: {len(manifest)} cases, {len(baseline)} results"
        )

    rows: list[dict] = []
    for spec, res in zip(manifest, baseline, strict=True):
        rows.append({**res, "variant": PRESENT_LAW,
                     "case_id": f"{PRESENT_LAW}::{spec['case_id']}"})

    for variant in reform_specs.VARIANTS:
        results, stderr = _run_cases(
            ORACLE / "work" / f"run-{name}-{variant.name}", casedir,
            variant.lawchg(),
        )
        if "lawchg.dat applied" not in stderr:
            raise RuntimeError(
                f"{variant.name}: the oracle did not read lawchg.dat, so "
                f"these would be present-law answers under a reform's name"
            )
        if len(results) != len(manifest):
            raise RuntimeError(
                f"{variant.name}: {len(manifest)} cases, "
                f"{len(results)} results"
            )
        moved = sum(
            1 for b, r in zip(baseline, results, strict=True)
            if key(b) != key(r)
        )
        if moved == 0:
            raise RuntimeError(
                f"{variant.name} changed no case; the sweep would assert "
                f"nothing about it"
            )
        for spec, res in zip(manifest, results, strict=True):
            rows.append({**res, "variant": variant.name,
                         "case_id": f"{variant.name}::{spec['case_id']}"})
        print(f"  {variant.name}: {moved}/{len(results)} cases moved")

    outpath = ORACLE / "goldens" / f"{name}.jsonl"
    with open(outpath, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    n_err = sum(1 for r in rows if "error" in r)
    print(f"{name}: {len(rows)} rows ({n_err} errors) -> {outpath}")


if __name__ == "__main__":
    # a name may carry an alternative, as in "retire_v1@3"
    for arg in sys.argv[1:] or ["retire_v1"]:
        nm, _, alt_str = arg.partition("@")
        if nm.startswith("reform"):
            run_reform_sweep(nm)
        else:
            run_sweep(nm, int(alt_str) if alt_str else 2)
