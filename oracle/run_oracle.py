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


def ensure_built() -> None:
    binary = ORACLE / "bin" / "anypiab-json"
    if not binary.exists():
        subprocess.run(
            ["make", "-C", str(ORACLE / "build"), "all"], check=True,
            capture_output=True,
        )


def run_sweep(name: str) -> None:
    ensure_built()
    casedir = ORACLE / "cases" / name
    workdir = ORACLE / "work" / f"run-{name}"
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(casedir / "cases.pia", workdir / "cases.pia")
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
    outpath = ORACLE / "goldens" / f"{name}.jsonl"
    with open(outpath, "w") as f:
        # not strict: a case the oracle rejected outright still needs its
        # manifest row, and the length mismatch is reported above
        for spec, res in zip(manifest, results, strict=False):
            res["case_id"] = spec["case_id"]
            f.write(json.dumps(res) + "\n")
    n_err = sum(1 for r in results if "error" in r)
    print(f"{name}: {len(results)} results ({n_err} errors) -> {outpath}")


if __name__ == "__main__":
    for nm in sys.argv[1:] or ["retire_v1"]:
        run_sweep(nm)
