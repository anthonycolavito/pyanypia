"""A tour of pyanypia, runnable end to end.

    python docs/examples/tour.py

Every snippet in the README appears here, so the documentation cannot
drift away from what the package does (tests/test_examples.py runs it).
"""

from __future__ import annotations

from datetime import date

import pyanypia as pia


def basic_retirement() -> None:
    print("=" * 68)
    print("A retirement benefit")
    print("=" * 68)
    worker = pia.Worker(
        dob=date(1960, 3, 15),
        sex=pia.Sex.FEMALE,
        benefit_type=pia.BenefitType.OLD_AGE,
        earnings={year: 52_000.0 for year in range(1985, 2026)},
        entitlement=pia.MonthYear(2027, 4),
    )
    r = pia.compute(worker)
    print(f"AIME {r.aime:,.0f}   PIA ${r.pia:,.2f}   benefit ${r.mba:,.2f}")
    print()
    print(r.detail())
    print()


def claiming_ages() -> None:
    print("=" * 68)
    print("The same earnings record claimed at different ages")
    print("=" * 68)
    earnings = {year: 52_000.0 for year in range(1985, 2026)}
    for label, ent in (
        ("age 62 and 1 month", pia.MonthYear(2022, 4)),
        ("full retirement age", pia.MonthYear(2027, 4)),
        ("age 70", pia.MonthYear(2030, 3)),
    ):
        worker = pia.Worker(
            dob=date(1960, 3, 15),
            sex=pia.Sex.FEMALE,
            benefit_type=pia.BenefitType.OLD_AGE,
            earnings={y: v for y, v in earnings.items() if y < ent.year},
            entitlement=ent,
        )
        r = pia.compute(worker)
        months = r.months_reduction_or_credit
        print(
            f"{label:22} benefit ${r.mba:8,.2f}   "
            f"PIA ${r.pia:8,.2f}   {months} months adjustment"
        )
    print()


def family_benefits() -> None:
    print("=" * 68)
    print("A family: worker, spouse, and a child")
    print("=" * 68)
    worker = pia.Worker(
        dob=date(1958, 6, 2),
        sex=pia.Sex.MALE,
        benefit_type=pia.BenefitType.OLD_AGE,
        earnings={year: 70_000.0 for year in range(1980, 2024)},
        entitlement=pia.MonthYear(2024, 7),
        family=[
            pia.FamilyMember(
                bic="B", dob=date(1960, 4, 9),
                entitlement=pia.MonthYear(2024, 7),
            ),
            pia.FamilyMember(
                bic="C1", dob=date(2008, 2, 1),
                entitlement=pia.MonthYear(2024, 7),
            ),
        ],
    )
    r = pia.compute(worker)
    print(f"worker  ${r.mba:8,.2f}   (PIA ${r.pia:,.2f})")
    for member in r.family:
        print(f"{member.bic:7} ${member.rounded_benefit:8,.2f}")
    print(f"family maximum ${r.mfb:,.2f}")
    print()


def statement() -> None:
    print("=" * 68)
    print("A Social Security Statement")
    print("=" * 68)
    worker = pia.Worker(
        dob=date(1955, 5, 20),
        sex=pia.Sex.MALE,
        benefit_type=pia.BenefitType.STATEMENT,
        earnings={year: 60_000.0 for year in range(1980, 2026)},
        entitlement=pia.MonthYear(2026, 6),
    )
    s = pia.calculate_statement(worker, month_now=6, age_plan=65)
    print(s.detail())
    print()


def batch() -> None:
    print("=" * 68)
    print("Many workers at once")
    print("=" * 68)
    from pyanypia.batch import compute_many

    workers = [
        pia.Worker(
            dob=date(1960, 3, 15),
            sex=i % 2,
            benefit_type=pia.BenefitType.OLD_AGE,
            earnings={y: 30_000.0 + 2_000.0 * i for y in range(1985, 2026)},
            entitlement=pia.MonthYear(2027, 4),
        )
        for i in range(8)
    ]
    for i, r in enumerate(compute_many(workers, processes=1)):
        print(f"worker {i}: PIA ${r.pia:8,.2f}   benefit ${r.mba:8,.2f}")
    print()


def pia_files() -> None:
    print("=" * 68)
    print("Reading and writing .pia case files")
    print("=" * 68)
    from pyanypia.io import PiaCase, read_pia, write_pia

    worker = pia.Worker(
        dob=date(1960, 3, 15),
        sex=pia.Sex.FEMALE,
        benefit_type=pia.BenefitType.OLD_AGE,
        earnings={year: 52_000.0 for year in range(2015, 2026)},
        entitlement=pia.MonthYear(2027, 4),
    )
    text = write_pia([PiaCase(worker=worker, ssn="123456789")])
    print(text, end="")
    back = read_pia(text)
    print(f"read back {len(back)} case; PIA ${pia.compute(back[0].worker).pia:,.2f}")
    print()


def main() -> None:
    basic_retirement()
    claiming_ages()
    family_benefits()
    statement()
    batch()
    pia_files()


if __name__ == "__main__":
    main()
