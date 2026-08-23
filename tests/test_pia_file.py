""".pia reader/writer: every generated sweep must parse into the same
Worker the generator described, and re-writing must produce a file the
reader reads back identically."""

from __future__ import annotations

import pathlib

import pytest

from pyanypia.io import read_pia, write_pia
from tests.oracle_util import ORACLE, load_sweep, worker_from_spec

SWEEPS = [
    "retire_v1", "dib_v1", "surv_v1", "fam_v1",
    "hist_v1", "special_v1", "total_v1", "proj_v1",
]


def _cases(sweep: str) -> list:
    path = ORACLE / "cases" / sweep / "cases.pia"
    return read_pia(path.read_text())


@pytest.mark.parametrize("sweep", SWEEPS)
def test_reads_every_case_in_sweep(sweep: str) -> None:
    specs = load_sweep(sweep)
    cases = _cases(sweep)
    assert len(cases) == len(specs), "one record per generated case"


@pytest.mark.parametrize("sweep", SWEEPS)
def test_parsed_worker_matches_generator(sweep: str) -> None:
    """The Worker the reader builds must equal the one the test harness
    builds from the generator's own spec."""
    specs = load_sweep(sweep)
    cases = _cases(sweep)
    for (spec, _), case in zip(specs, cases, strict=True):
        want = worker_from_spec(spec)
        got = case.worker
        cid = spec["case_id"]
        assert got.dob == want.dob, cid
        assert got.sex == want.sex, cid
        assert got.benefit_type == want.benefit_type, cid
        assert got.entitlement == want.entitlement, cid
        assert got.benefit_date == want.benefit_date, cid
        assert got.death_date == want.death_date, cid
        assert got.ibegin == want.ibegin, cid
        assert got.iend == want.iend, cid
        assert got.totalize == want.totalize, cid
        assert got.childcare_years == want.childcare_years, cid
        assert got.qc_total_to_date == want.qc_total_to_date, cid
        assert got.qc_total_51_to_date == want.qc_total_51_to_date, cid
        assert got.qcs_by_year == want.qcs_by_year, cid
        assert got.military_service == want.military_service, cid
        assert len(got.family) == len(want.family), cid
        for g, e in zip(got.family, want.family, strict=True):
            assert (g.bic, g.dob, g.entitlement) == (
                e.bic, e.dob, e.entitlement
            ), cid
        assert len(got.disability_periods) == len(want.disability_periods), cid
        for g, e in zip(
            got.disability_periods, want.disability_periods, strict=True
        ):
            assert g == e, cid
        for year, amount in want.earnings.items():
            assert got.earnings[year] == pytest.approx(amount, abs=0.005), (
                f"{cid} earnings {year}"
            )


@pytest.mark.parametrize("sweep", SWEEPS)
def test_round_trip_is_stable(sweep: str) -> None:
    """Writing what was read, then reading again, must reproduce the same
    records: the writer emits every field the reader consumes."""
    cases = _cases(sweep)
    again = read_pia(write_pia(cases))
    assert len(again) == len(cases)
    for a, b in zip(cases, again, strict=True):
        assert a.worker == b.worker


@pytest.mark.oracle
@pytest.mark.parametrize("sweep", SWEEPS)
def test_round_trip_computes_identically(sweep: str) -> None:
    """A case read from file, written back, and read again computes the
    same benefit — the round trip loses nothing the engine uses."""
    from pyanypia import compute

    specs = load_sweep(sweep)
    cases = _cases(sweep)
    again = read_pia(write_pia(cases))
    for (spec, expected), case in zip(specs, again, strict=True):
        if "error" in expected:
            continue
        r = compute(case.worker)
        assert f"{r.pia:.2f}" == f"{expected['high_pia']:.2f}", (
            spec["case_id"]
        )
        assert f"{r.monthly_benefit:.2f}" == (
            f"{expected['rounded_benefit']:.2f}"
        ), spec["case_id"]


@pytest.mark.oracle_smoke
@pytest.mark.parametrize("sweep", SWEEPS)
def test_oracle_reads_what_we_write(sweep: str, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The strongest statement of writer fidelity: hand the official
    calculator a file this package produced and it must reach the same
    answers it reached on the generator's own file."""
    import json
    import subprocess

    binary = ORACLE / "bin" / "anypiab-json"
    if not binary.exists():
        pytest.skip("oracle not built")
    cases = _cases(sweep)
    (tmp_path / "cases.pia").write_text(write_pia(cases))
    subprocess.run(
        [str(binary)], input="cases\n", text=True, cwd=tmp_path,
        capture_output=True, check=False,
    )
    out = tmp_path / "output.jsonl"
    assert out.exists(), "oracle produced no output"
    got = [json.loads(line) for line in open(out)]
    want = [
        json.loads(line)
        for line in open(ORACLE / "goldens" / f"{sweep}.jsonl")
    ]
    assert len(got) == len(want)
    for g, e in zip(got, want, strict=True):
        for key in (
            "high_pia", "high_mfb", "rounded_benefit", "unrounded_benefit",
            "fins", "pifc", "elig_year", "months_ardri",
        ):
            assert g.get(key) == e.get(key), f"{e['case_id']}: {key}"


def test_reads_the_smoke_case() -> None:
    path = pathlib.Path(ORACLE / "cases" / "smoke" / "retire01.pia")
    cases = read_pia(path.read_text())
    assert len(cases) == 1
    w = cases[0].worker
    assert w.dob.year == 1960
    assert w.benefit_type == 1
