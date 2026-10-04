# pyanypia formula library — design

Date: 2026-10-04
Status: approved in conversation; awaiting spec review

## Why

pyanypia v0.2.0 ported the whole of SSA's Detailed Calculator (AnyPIA): a
13,000-line engine driven by a `Worker -> compute()` pipeline. What is
actually wanted is the *benefit formula* — standalone functions to run
hypothetical examples and, eventually, to power a microsimulation. In the
engine the formula math is spread across methods that all take a
`CalcContext`, so it cannot be called piecemeal or over many people at
once.

## Decisions

| Question | Decision |
|---|---|
| What happens to the full engine | Split: moves to a new repo `anthonycolavito/anypia-engine` with full history; `pyanypia` becomes the formula library |
| Scope | Core retired-worker chain, family/auxiliary benefits, disability, special minimum, overridable policy parameters |
| Many people | NumPy arrays; every function broadcasts over people; scalars still work |
| Fidelity | Penny-exact with AnyPIA's rounding, tested against the archived engine |
| WEP/GPO | Included as optional functions, off by default (repealed by the Social Security Fairness Act for benefits payable after Dec 2023) |

## Repo split

1. Create `anthonycolavito/anypia-engine` (public) and push the current
   `main` there with full history. Tag `v0.2.0` there and create the
   release (this finishes the engine's outstanding task 24.3).
2. Engine README gains a pointer to the formula library; the engine is
   otherwise frozen.
3. In `pyanypia`, the rewrite happens on branch `formula-library` and
   merges to `main` as v0.3.0. The old engine stays in `pyanypia`'s
   history. README and CHANGELOG explain the change.
4. Creating the repo and pushing tags are confirmed with the user at the
   moment they run.

## Scope

**In:** wage indexing, computation years and dropout years (including
disability dropout and child-care dropout), AIME, bend points, the PIA
formula with dime rounding, COLAs, normal retirement age, early-reduction
and delayed-retirement factors, quarters of coverage and fully insured
status, family maximum (retirement/survivor and disability), auxiliary
benefit rates and reductions (spouse, child, widow(er), disabled
widow(er)), distribution of the family maximum among auxiliaries,
special minimum PIA, WEP PIA and GPO offset (optional).

**Out:** old-start method, pre-1977 PIA table, transitional guarantee,
frozen minimum, disability guarantee, re-indexed widow(er) guarantee,
non-freeze parallel computation, totalization, Statement estimates,
earnings projection, `.pia` file I/O, the multiprocessing batch layer,
the `Law`/`Reform` machinery, and the C++ oracle. These either apply
almost only to people eligible before 1979 or are SSA workflow, not
formula. The README states the library is exact for wage-indexed
computations with eligibility in 1979 or later.

## Calling conventions

- **People are arrays.** Birth date is `birth_year`, `birth_month`,
  `birth_day` (day defaults to 15, so the 1st/2nd-of-month attainment
  rules apply only when asked for). Ages are integer months
  (`claim_age=62*12+6`). Each is a scalar or a 1-D array of length n;
  all inputs broadcast together.
- **Earnings** are an `(n, Y)` array with `first_year=`; column j is
  year `first_year + j`. A single worker may pass a 1-D array or a
  `{year: amount}` dict, converted internally. Earnings above the
  taxable maximum are capped by the functions, as AnyPIA does.
- **Policy** is the final keyword argument everywhere,
  `policy=CURRENT_LAW` (2026 Trustees Report, intermediate). Outputs are
  NumPy arrays (0-d for all-scalar input, returned as Python floats).

## Policy

A frozen dataclass of *primitive* inputs:

- historical AWI levels and projected AWI growth rates
- historical COLAs and projected COLAs
- historical taxable maximum (projected values are derived)
- 1979 PIA bend-point base amounts (180, 1085) and their AWI base year
- PIA percentages (0.90, 0.32, 0.15), allowing more brackets
- MFB bend-point bases and percentages (1.50, 2.72, 1.34, 1.75)
- NRA schedule, early-reduction rates (5/9% then 5/12% per month),
  delayed-credit schedule by birth cohort
- quarter-of-coverage base amount, special-minimum amount per year of
  coverage, WEP parameters, `wep_enabled=False`, `gpo_enabled=False`

Derived series (projected AWI, bend points, MFB bend points, taxable
maximum, quarter-of-coverage amounts, special-minimum table) are computed
from the primitives with AnyPIA's operation order and rounding, and
cached per instance. `policy.replace(**changes)` returns a new policy, so
a change to AWI growth or the PIA percentages flows through every derived
series. Any derived series can also be overridden directly.
`Policy.current_law(alt=1|2|3)` loads the three Trustees alternatives;
`CURRENT_LAW` is alternative 2.

## Modules and functions

```
src/pyanypia/
  __init__.py      flat public namespace
  policy.py        Policy, CURRENT_LAW, derived-series builders
  _data2026.py     2026 Trustees Report data (carried over)
  rounding.py      AnyPIA rounding rules (carried over)
  _arrays.py       input coercion, broadcasting, validation
  earnings.py      indexed_earnings, computation_years, aime,
                   quarters_of_coverage, fully_insured
  formula.py       bend_points, pia, apply_colas
  claiming.py      normal_retirement_age, early_reduction_factor,
                   delayed_credit_factor, monthly_benefit
  family.py        family_max, di_family_max, aux_benefit,
                   distribute_family_max
  disability.py    disability dropout years, DI AIME helpers
  minimum.py       special_minimum_pia
  wep.py           wep_pia, gpo_offset
  convenience.py   retired_worker, disabled_worker, survivor
```

Representative signatures:

```python
aime(earnings, birth_year, *, first_year, elig_year=None, dropout=None, policy=...)
pia(aime, elig_year, *, policy=...)
apply_colas(pia, elig_year, to_year, *, policy=...)
monthly_benefit(pia, birth_year, birth_month, claim_age, *, birth_day=15, policy=...)
family_max(pia, elig_year, *, disabled=False, aime=None, policy=...)
retired_worker(earnings, birth_year, birth_month, claim_age, *, first_year, policy=...)
```

The convenience functions return a small result object whose fields
(`aime`, `pia`, `nra`, `factor`, `benefit`, ...) are arrays, with
`.to_frame()` when pandas is installed.

Implementation reuses the engine's validated arithmetic (rounding,
projection, retirement-age tables), rewritten to operate on arrays
instead of a `CalcContext`.

## Errors

Invalid input raises `ValueError` naming the field: years outside the
policy's data range (1937–2105), negative earnings, retirement claim age
below 62, mismatched array shapes. Vectorized calls validate the whole
input first and report the count of bad rows and the first bad index.
No silent clipping beyond the statutory taxable-maximum cap.

## Dependencies

Runtime: `numpy`. Optional: `pandas` for `.to_frame()`. Test-only: the
archived engine, installed from
`git+https://github.com/anthonycolavito/anypia-engine@v0.2.0`.

## Testing

1. **Differential vs the engine.** Generated workers (retired, disabled,
   survivor; birth cohorts with eligibility 1979+; varied earnings shapes
   including zeros, partial careers and above-max earnings; claim ages
   62–70) run through both. AIME, PIA, monthly benefit and family maximum
   must match to the cent. Cases where the engine's winning method is one
   this library omits are excluded and counted, and the count is asserted
   small so exclusions cannot silently grow.
2. **Vectorized equals scalar.** Every differential batch is also run one
   row at a time; results must be identical.
3. **Published tables.** Bend points, MFB bend points, NRA schedule,
   quarter-of-coverage amounts and special-minimum amounts match SSA's
   published values for historical years.
4. **Policy overrides.** Changing `pia_pct`, AWI growth or bend-point
   bases moves results the way hand arithmetic says.

## Release

v0.3.0. CHANGELOG records that the engine moved to `anypia-engine` and
that the `Worker`/`compute` API is gone. README rewritten around the
function API, with a hypotheticals example and a microsimulation
example (100k synthetic workers).
