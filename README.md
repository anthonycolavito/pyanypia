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
family_worker = pia.Worker(
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
r = pia.compute(family_worker)
for member in r.family:
    print(member.bic, f"${member.rounded_benefit:,.2f}")
```

### A Statement

A Statement case is its own benefit type, and it takes no entitlement --
the estimates are what the worker would get at each age:

```python
statement_worker = pia.Worker(
    dob=date(1975, 5, 20),
    sex=pia.Sex.MALE,
    benefit_type=pia.BenefitType.STATEMENT,
    earnings={year: 60_000.0 for year in range(1998, 2026)},
)
s = pia.calculate_statement(statement_worker, month_now=6, age_plan=65)
print(s.detail())
```

### Many workers at once

```python
from pyanypia.batch import compute_many, compute_frame

if __name__ == "__main__":                       # required: see below
    results = compute_many(workers)              # uses every CPU
    frame = compute_frame(df, earnings="earn")   # pandas extra
```

`compute_many` returns results in input order, and the answers do not depend
on how the work was split across processes.

The guard is not decoration. Work is parallelised with the "spawn" start
method, so each child re-imports the calling module; without a
`__main__` guard the child calls `compute_many` again, and so does its
child. Pass `processes=1` to stay in this process and avoid the question
entirely.

### `.pia` interoperability

The calculator's own case-file format reads and writes:

```python
from pyanypia.io import read_pia_file, write_pia
from pyanypia.params import params_for

cases = read_pia_file("cases.pia")
# a case file carries its own assumptions on line 40; honour them rather
# than silently costing every case under the intermediate alternative
results = [
    pia.compute(c.worker,
                params=params_for(c.assumptions.ialtbi, c.assumptions.ialtaw))
    for c in cases
]
with open("out.pia", "w") as f:
    f.write(write_pia(cases))
```

Files written by pyanypia are read identically by the official calculator —
that equivalence is a test, run over every case in the suites below.

## Reforms

`compare()` computes a worker under present law and under a reform, and
reports the difference:

```python
from pyanypia.law import Reform, NraChange

reform = Reform(nra=NraChange(1990, 2100, variant=1))  # hold the FRA at 65
print(pia.compare(worker, reform).detail())
```
```
PIA         3399.90 ->    3399.90  (+0.00)
benefit     3399.00 ->    3898.00  (+499.00, +14.7%)
```

The PIA is untouched and the benefit is not: this worker claims at 67 and
1 month, which present law reduces nothing and credits nothing, but which
is fifteen months of delayed retirement credit once the full retirement
age is 65.

Nine changes are supported, each mapped to the LawChange class it ports
and each validated against the oracle over the `reform_v1` sweep:

| `Reform` field | LawChange | What it does |
|---|---|---|
| `nra` | `NRACHANGE` | Full retirement age: held at 65, the 66-to-67 plateau removed, or rising after 2011 — with the reduction slopes past 67 and 69 that come with it |
| `cola` | `COLACHANGE` | Benefit increases shifted by a percentage point over a span |
| `wage_base` | `WAGEBASECHG` | Ad hoc contribution and benefit bases, after which projection resumes off the last of them |
| `di_dropout_five` | `DIDROP5` | A flat five dropout years in place of the one-for-five rule |
| `new_formula` | `NEWFORMULA` | A replacement benefit formula: one to four bend points with their own percentages, indexed off wages past the span |
| `declining_perc` | `DECLINEPERC` | The formula percentages falling year by year, compounding, over one or more intervals |
| `special_min` | `NEWSPECMIN` | A new special-minimum amount per year of coverage, restarting the indexed table where it begins |
| `comp_point` | `AGE65COMP` | The computation point moving from age 62 towards 65, phased in |
| `childcare_dropout` | `CHILDCAREDROPOUT` | Child-care dropout years for everyone, more of them, and counting years under a share of the average wage rather than only empty ones |

Anything else raises rather than returning a present-law answer under a
reform's name — see [Limitations](#limitations) for why the list is short.

## Fidelity

The differential suites, all penny-exact against the compiled oracle -- 9,176 cases in total:

| Suite | Cases | What it covers |
|---|---:|---|
| `retire_v1` | 462 | Modern retirement across cohorts, earnings patterns, claim ages |
| `surv_v1` | 450 | Survivors: aged and disabled widow(er)s, young families, children |
| `pebs_v1` | 420 | Social Security Statement estimates |
| `hist_v1` | 414 | Old-start, PIA-table and transitional-guarantee cohorts, 1900–1928 |
| `dib_v1` | 176 | Disability, freeze and non-freeze computations |
| `total_v1` | 96 | Totalization, pro-rated PIAs |
| `fam_v1` | 72 | Retirement with spouses and children |
| `special_v1` | 60 | Disability guarantee, child-care dropout years |
| `proj_v1` | 42 | Projected earnings, steady earnings types, military credits |
| `freeze_v1` | 16 | Earnings inside a disability freeze window; two periods of disability |
| `reform_v1` | 3,440 | 172 cases under present law and nineteen reform variants |
| alternatives I and III | 3,544 | the eight sweeps above other than the Statement, reform and freeze suites, re-costed under the low-cost and high-cost projections |

Each case is compared field by field: insured status, eligibility year, the
AIME/PIA/MFB of every applicable method, the winning method, the family
maximum, the reduction or credit months, each family member's benefit, and
the payable amount.

To rebuild and re-verify from source:

```bash
make -C oracle/build all             # needs clang++ and Boost headers
python oracle/cases/generate.py all
python oracle/run_oracle.py retire_v1 dib_v1 surv_v1 fam_v1 \
    hist_v1 special_v1 total_v1 proj_v1 pebs_v1 reform_v1
# and the same cases under the other two Trustees alternatives
python oracle/run_oracle.py retire_v1@1 retire_v1@3   # ... and so on
pytest
```

## Limitations

- **Most policy reforms are out of scope.** Of the calculator's forty
  LawChange types, batch `anypiab` visibly honours only some; the nine
  listed under [Reforms](#reforms) are ported and validated, and
  `Reform` rejects anything else rather than quietly returning present-law
  answers under a reform's name. Which ones matter was measured rather
  than assumed — `oracle/tools/scope_lawchg.py` switches each type on over
  220 cases and counts how many answers move. `ALLEARN` is consulted
  nowhere outside its own class; `TAXBENCHG` and `PSAACCT` reach only
  output anypiab does not print; `CHILDCARECREDIT` is consulted but moved
  no case tried. Two more are worth naming. A reformed
  aged-spouse factor (`WIFEFACTOR`) never reaches the answer, because
  `PiaCal` asks for `factorAgedSpouseCalPL()`, the present-law factor. And
  the bend-point reforms (`BPFRACWAGE`, `BPMINCONST`) cannot be computed
  at all: `PiaParamsLC` builds the bend-point wage series in its
  constructor, which runs before `AnypiabDoc` calls `setHistFqinc()`, so
  `setFqBppia()` reads a benefit-increase series of all zeros and nothing
  recomputes it afterwards. Every eligibility year from the change onward
  is left with the bend points of the year before it began, whatever
  proportion was requested — asking for the full wage rate, which should
  reproduce present law exactly, moves a 2005 eligibility from $1,500.10
  to $1,137.80 — and where the span ends early the projection past it
  divides zero by zero and returns NaN. The official `anypiabdoc.cpp`
  constructs `PiaParamsAny` in the same order, so this is the calculator's
  behaviour rather than an artefact of how we drive it. Since there is no
  answer to check against, pyanypia does not offer one.
- **Railroad earnings** are not credited. A `.pia` file containing them
  is refused rather than read with the railroad component dropped.
- **The Statement's disability estimate is unavailable below full
  retirement age.** `PiaCalAny::pebsSetup` builds the disability scenario
  with an onset date and no waiting-period date, and the freeze
  calculation then requires one — so the official calculator cannot
  produce this estimate either, and there is no answer to check against.
  pyanypia returns the retirement and survivor estimates, which are
  unaffected, and records the disability one in
  `StatementResults.unavailable` with the reason; reading
  `disability_pia` raises rather than returning a number. Above full
  retirement age the calculator asks for no disability estimate and the
  question does not arise, which is why the 420-case Statement suite is
  penny-exact.
- The windfall elimination provision follows present law, under which it is
  repealed for benefits payable January 2024 and later.

## Not an official SSA product

pyanypia is derived from SSA/OACT's public-domain Detailed Calculator source
(17 U.S.C. §105) but is **not** an official Social Security Administration
product and is not endorsed by SSA. Amounts are research estimates — consult
SSA for official benefit determinations.

Licensed MIT; see `LICENSE` for the attribution notice that travels with the
derived work.
