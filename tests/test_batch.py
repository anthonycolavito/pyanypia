"""Batch computation: order, determinism, and the DataFrame helpers."""

from __future__ import annotations

from datetime import date

import pytest

from pyanypia import BenefitType, MonthYear, Worker, compute
from pyanypia.batch import compute_iter, compute_many

AWI_ISH = {y: 20000.0 + 900.0 * (y - 1980) for y in range(1980, 2026)}


def make_workers(n: int) -> list[Worker]:
    """n workers spanning a range of birth years and earnings levels."""
    out = []
    for i in range(n):
        by = 1955 + (i % 12)
        level = 0.4 + 0.06 * (i % 15)
        earn = {
            y: round(level * AWI_ISH[y], 2)
            for y in range(by + 22, by + 62)
            if y in AWI_ISH
        }
        out.append(Worker(
            dob=date(by, 3, 15),
            sex=i % 2,
            benefit_type=BenefitType.OLD_AGE,
            earnings=earn,
            entitlement=MonthYear(by + 67, 3),
            benefit_date=MonthYear(by + 67, 3),
        ))
    return out


def test_empty_batch() -> None:
    assert compute_many([]) == []


def test_matches_single_computation() -> None:
    workers = make_workers(25)
    got = compute_many(workers, processes=1)
    assert [r.pia for r in got] == [compute(w).pia for w in workers]


def test_results_are_in_input_order() -> None:
    workers = make_workers(40)
    got = compute_many(workers, processes=1)
    assert len(got) == len(workers)
    for w, r in zip(workers, got, strict=True):
        assert r.elig_year == w.dob.year + 62


def test_streaming_matches_batch() -> None:
    workers = make_workers(30)
    assert [r.pia for r in compute_iter(workers)] == [
        r.pia for r in compute_many(workers, processes=1)
    ]


@pytest.mark.slow
def test_thousand_workers_deterministic_across_processes() -> None:
    """The same 1,000 workers must give the same answers whether computed
    in one process or many, and in the same order."""
    workers = make_workers(1000)
    serial = compute_many(workers, processes=1)
    parallel = compute_many(workers, processes=4, chunksize=37)
    assert len(serial) == len(parallel) == 1000
    for a, b in zip(serial, parallel, strict=True):
        assert (a.pia, a.mfb, a.monthly_benefit) == (
            b.pia, b.mfb, b.monthly_benefit
        )
        assert a.method == b.method


def test_wide_frame_round_trip() -> None:
    pd = pytest.importorskip("pandas", reason="pandas extra not installed")

    from pyanypia.batch import compute_frame

    workers = make_workers(6)
    rows = []
    for w in workers:
        row: dict = {
            "dob": w.dob,
            "sex": w.sex,
            "benefit_type": int(w.benefit_type),
            "entitlement": w.entitlement,
            "benefit_date": w.benefit_date,
        }
        row.update({f"earn{y}": v for y, v in w.earnings.items()})
        rows.append(row)
    df = pd.DataFrame(rows)
    out = compute_frame(df, earnings="earn", processes=1)
    assert list(out.index) == list(df.index)
    assert [round(v, 2) for v in out["pia"]] == [
        round(compute(w).pia, 2) for w in workers
    ]


def test_long_frame_round_trip() -> None:
    pd = pytest.importorskip("pandas", reason="pandas extra not installed")

    from pyanypia.batch import compute_frame

    workers = make_workers(4)
    rows = []
    for i, w in enumerate(workers):
        for year, amount in w.earnings.items():
            rows.append({
                "person": i,
                "dob": w.dob,
                "sex": w.sex,
                "benefit_type": int(w.benefit_type),
                "entitlement": w.entitlement,
                "benefit_date": w.benefit_date,
                "year": year,
                "earnings": amount,
            })
    df = pd.DataFrame(rows)
    out = compute_frame(
        df, year_column="year", amount_column="earnings",
        id_column="person", processes=1,
    )
    assert len(out) == len(workers)
    assert [round(v, 2) for v in out["pia"]] == [
        round(compute(w).pia, 2) for w in workers
    ]
