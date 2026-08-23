"""The documented examples must keep working."""

from __future__ import annotations

import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOUR = ROOT / "docs" / "examples" / "tour.py"


def test_tour_runs(capsys) -> None:  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(TOUR.parent))
    try:
        runpy.run_path(str(TOUR), run_name="__main__")
    finally:
        sys.path.remove(str(TOUR.parent))
    out = capsys.readouterr().out
    # each section printed something substantive
    for marker in (
        "A retirement benefit",
        "The same earnings record claimed at different ages",
        "A family: worker, spouse, and a child",
        "A Social Security Statement",
        "Many workers at once",
        "Reading and writing .pia case files",
    ):
        assert marker in out
    assert "PIA $" in out


def test_readme_quotes_real_output() -> None:
    """The detail() block in the README must match what the package
    actually prints for the README's own worker."""
    from datetime import date

    import pyanypia as pia

    worker = pia.Worker(
        dob=date(1960, 3, 15),
        sex=pia.Sex.FEMALE,
        benefit_type=pia.BenefitType.OLD_AGE,
        earnings={year: 52_000.0 for year in range(1985, 2026)},
        entitlement=pia.MonthYear(2027, 4),
    )
    detail = pia.compute(worker).detail()
    readme = (ROOT / "README.md").read_text()
    for line in detail.splitlines():
        assert line.strip() in readme, f"README is stale: {line!r}"
