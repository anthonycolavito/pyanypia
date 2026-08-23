# pyanypia

A pure-Python port of the calculation engine inside the Social Security
Administration's **Detailed Calculator (AnyPIA)**, 2026 Trustees Report
version — Social Security benefit calculations you can run, inspect, batch,
and script in Python.

Every number is checked against the official calculator. SSA publishes the
Detailed Calculator's C++ source; `oracle/` vendors it unmodified, builds it,
and runs it over generated case suites. The Python engine must reproduce
those answers to the cent — not only the final benefit, but the AIME and the
PIA under each computation method, so a divergence localises to one
computation rather than to "somewhere in the port".

## Install

```bash
pip install git+https://github.com/anthonycolavito/pyanypia
```

Python 3.11 or newer. The runtime has no dependencies; `pip install
"pyanypia[pandas]"` adds the DataFrame helpers.

## Quickstart

```python
from datetime import date
import pyanypia as pia

worker = pia.Worker(
    dob=date(1960, 3, 15),
    sex=pia.Sex.FEMALE,
    benefit_type=pia.BenefitType.OLD_AGE,
    earnings={year: 52_000.0 for year in range(1985, 2026)},
    entitlement=pia.MonthYear(2027, 4),
)

r = pia.compute(worker)
print(f"AIME {r.aime:,.0f}   PIA ${r.pia:,.2f}   benefit ${r.mba:,.2f}")
print(r.detail())
```

`detail()` shows every method that applied and which one won:

```
insured: 1 (fully insured)
eligibility year: 2022
AIME: 7719
  WAGE_IND: PIA 3399.90  MFB 5951.50 *
  SPEC_MIN: PIA 1154.00  MFB 1733.10
PIA 3399.90, MFB 5951.50, benefit 3399.00 at age 67y1m
```

Every snippet here is in `docs/examples/tour.py`, which the test suite runs.

## What it computes

- **Retirement, disability, and survivor benefits**, plus benefits for
  spouses, children, and widow(er)s, with the family maximum distributed
  among them.
- **Every PIA computation method** the calculator knows: wage-indexed
  (with the windfall elimination provision), old-start, the pre-1977 PIA
  table, transitional guarantee, special minimum, frozen minimum, child-care
  dropout years, the disability guarantee, the re-indexed widow(er)
  guarantee, and the non-freeze parallel computation — then picks the
  highest, as the law requires.
- **Totalization** for workers with too few US quarters to qualify on their
  own.
- **Social Security Statement estimates** — retirement at 70, at full
  retirement age and at the earliest age, plus survivor and disability
  estimates.
- **Earnings projection**: a partial earnings record extended backward and
  forward by the average wage index or a flat rate, plus military service
  wage credits.

### Family benefits

```python
worker = pia.Worker(
    dob=date(1958, 6, 2),
    sex=pia.Sex.MALE,
    benefit_type=pia.BenefitType.OLD_AGE,
    earnings={year: 70_000.0 for year in range(1980, 2024)},
    entitlement=pia.MonthYear(2024, 7),
    family=[
        pia.FamilyMember(bic="B", dob=date(1960, 4, 9),
                         entitlement=pia.MonthYear(2024, 7)),
        pia.FamilyMember(bic="C1", dob=date(2008, 2, 1),
                         entitlement=pia.MonthYear(2024, 7)),
    ],
)
r = pia.compute(worker)
for member in r.family:
    print(member.bic, f"${member.rounded_benefit:,.2f}")
```

### A Statement

```python
s = pia.calculate_statement(worker, month_now=6, age_plan=65)
print(s.detail())
```

### Many workers at once

```python
from pyanypia.batch import compute_many, compute_frame

results = compute_many(workers)              # uses every CPU
frame = compute_frame(df, earnings="earn")   # pandas extra
```

`compute_many` returns results in input order, and the answers do not depend
on how the work was split across processes.

### `.pia` interoperability

The calculator's own case-file format reads and writes:

```python
from pyanypia.io import read_pia_file, write_pia

cases = read_pia_file("cases.pia")
results = [pia.compute(c.worker) for c in cases]
open("out.pia", "w").write(write_pia(cases))
```

Files written by pyanypia are read identically by the official calculator —
that equivalence is a test, run over every case in the suites below.

## Fidelity

The differential suites, all penny-exact against the compiled oracle:

| Suite | Cases | What it covers |
|---|---:|---|
| `retire_v1` | 462 | Modern retirement across cohorts, earnings patterns, claim ages |
| `surv_v1` | 432 | Survivors: aged and disabled widow(er)s, young families, children |
| `pebs_v1` | 420 | Social Security Statement estimates |
| `hist_v1` | 414 | Old-start, PIA-table and transitional-guarantee cohorts, 1900–1928 |
| `dib_v1` | 176 | Disability, freeze and non-freeze computations |
| `total_v1` | 96 | Totalization, pro-rated PIAs |
| `fam_v1` | 72 | Retirement with spouses and children |
| `special_v1` | 60 | Disability guarantee, child-care dropout years |
| `proj_v1` | 42 | Projected earnings, steady earnings types, military credits |

Each case is compared field by field: insured status, eligibility year, the
AIME/PIA/MFB of every applicable method, the winning method, the family
maximum, the reduction or credit months, each family member's benefit, and
the payable amount.

To rebuild and re-verify from source:

```bash
make -C oracle/build all             # needs clang++ and Boost headers
python oracle/cases/generate.py all
python oracle/run_oracle.py retire_v1 dib_v1 surv_v1 fam_v1 \
    hist_v1 special_v1 total_v1 proj_v1 pebs_v1
pytest
```

## Limitations

- **Policy reforms** (the calculator's LawChange machinery) are not
  implemented yet. `compare()` refuses a reform rather than ignoring it.
- **Railroad earnings** are not credited. A `.pia` file containing them
  is refused rather than read with the railroad component dropped.
- **Statement estimates below full retirement age** cannot be checked
  against the oracle. Batch anypiab cannot compute them: its disability
  estimate is set up without a waiting-period date, which the freeze
  calculation then reads. The engine computes them; nothing here proves
  them.
- The windfall elimination provision follows present law, under which it is
  repealed for benefits payable January 2024 and later.

## Not an official SSA product

pyanypia is derived from SSA/OACT's public-domain Detailed Calculator source
(17 U.S.C. §105) but is **not** an official Social Security Administration
product and is not endorsed by SSA. Amounts are research estimates — consult
SSA for official benefit determinations.

Licensed MIT; see `LICENSE` for the attribution notice that travels with the
derived work.
