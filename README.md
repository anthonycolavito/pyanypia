# pyanypia

The Social Security benefit formula as Python functions: AIME, PIA, the
family maximum, COLAs, claiming-age reductions and credits, the special
minimum, spouse and survivor benefits. Every function takes NumPy arrays,
so the same call that answers "what would this worker get?" also runs a
microsimulation over a million workers.

The arithmetic is SSA's own. Each result is checked, to the cent, against
the full port of SSA's Detailed Calculator (AnyPIA, 2026 Trustees Report).

> **Looking for the full calculator?** Versions up to 0.2.0 of this package
> were a complete port of AnyPIA, with `Worker`, `compute`, Statements and
> `.pia` files. It now lives on as
> [anypia-engine](https://github.com/anthonycolavito/anypia-engine), and is
> the oracle this library is tested against.

## Install

```bash
pip install git+https://github.com/anthonycolavito/pyanypia
```

Python 3.11 or newer, with NumPy. `pip install "pyanypia[pandas] @ git+..."`
adds `Benefit.to_frame()`.

## Quickstart

```python
from pyanypia import CURRENT_LAW, Auxiliary, family_benefits, retired_worker

# A worker born 15 June 1964 who earned the national average wage every
# year from 22 to 66, claiming at 62 and 1 month, at the normal retirement
# age (67), and at 70. Ages are in months; the PIA includes COLAs to the
# claim month, so it is higher for a later claim.
earnings = {year: float(CURRENT_LAW.awi[year - 1937]) for year in range(1986, 2031)}
for months in (62 * 12 + 1, 67 * 12, 70 * 12):
    b = retired_worker(earnings, 1964, 6, months)
    print(f"claim at {months // 12}y{months % 12}m: AIME {b.aime:,.0f}  "
          f"PIA ${b.pia:,.2f}  benefit ${b.benefit:,.0f}/month")

# The same worker at 67 with the middle bracket cut from 32% to 30%.
reform = CURRENT_LAW.replace(pia_pct=(0.90, 0.30, 0.15))
b = retired_worker(earnings, 1964, 6, 67 * 12, policy=reform)
print(f"reform PIA ${b.pia:,.2f}")

# A spouse born March 1966 who claims at 64, in the month the worker claims at 67.
b = retired_worker(earnings, 1964, 6, 67 * 12)
spouse = Auxiliary("spouse", 1966, 3, claim_age=64 * 12 + 3)
fam = family_benefits(b.pia, b.mfb, [spouse], benefit_year=2031, benefit_month=6)
print(f"spouse benefit ${fam.benefit[0]:,.0f}/month")
```

```
claim at 62y1m: AIME 5,825  PIA $2,609.80  benefit $1,837/month
claim at 67y0m: AIME 5,968  PIA $2,998.50  benefit $2,998/month
claim at 70y0m: AIME 5,968  PIA $3,219.40  benefit $3,992/month
reform PIA $2,892.80
spouse benefit $1,155/month
```

This is `docs/examples/hypotheticals.py`, which the test suite runs.

## The building blocks

The one-call functions at the bottom of this table chain the others. Each
of those is usable alone.

| Function | What it gives |
|---|---|
| `eligibility_year` | year of attaining 62, or of disability onset or death if earlier |
| `computation_years` | elapsed years less dropout years (5, or 1 per 5 for disability) |
| `indexed_earnings`, `capped_earnings` | earnings capped at the taxable maximum and wage-indexed |
| `aime` | average indexed monthly earnings over the highest computation years |
| `bend_points`, `pia` | the PIA formula at eligibility |
| `family_max`, `di_family_max` | the maximum family benefit at eligibility |
| `apply_colas` | carries a PIA or maximum from eligibility to a benefit month |
| `normal_retirement_age`, `earliest_claim_age` | in months |
| `benefit_factor`, `early_reduction_factor`, `delayed_credit_factor` | the multiplier for claiming early or late |
| `monthly_benefit` | factor × PIA, rounded as SSA rounds it |
| `quarters_of_coverage`, `fully_insured`, `disability_insured` | insured status |
| `years_of_coverage`, `special_minimum_pia` | the special minimum |
| `childcare_aime` | the AIME with child-care dropout years |
| `family_benefits`, `Auxiliary` | spouse, child and survivor benefits under the family maximum |
| `widow_guarantee_pia` | the re-indexed widow(er)'s guarantee |
| `wep_pia`, `gpo_offset` | the repealed WEP and GPO, off by default |
| `retired_worker`, `disabled_worker`, `deceased_worker` | the whole chain in one call |

## Conventions

- **One worker or many.** Pass scalars and a `{year: amount}` dict of
  earnings, and you get scalars back. Pass arrays with one entry per worker
  and an `(n, years)` earnings matrix with `first_year=`, and you get
  arrays back. Inputs broadcast, so a single birth month can apply to every
  worker.
- **Ages are whole months**, counted from the month of the day before
  birth. That is how SSA counts: someone born 15 March 1964 is 62 (744
  months) in March 2026. Someone born on the 1st attains each age in the
  month before their birthday month, which `birth_day=1` handles.
- **Benefits are for a month.** The convenience functions compute the
  benefit for the claim month unless you pass a later `benefit_age` (or
  `benefit=(year, month)`), and they ignore earnings from the benefit year
  on.
- **Errors are loud.** Bad input raises `ValueError`, naming the field, how
  many rows are wrong and the first one. Nothing is silently clipped except
  earnings above the taxable maximum, which the law ignores.

## Policy and reforms

Every function takes `policy=`, defaulting to `CURRENT_LAW`: present law
under the 2026 Trustees Report intermediate assumptions.
`Policy.current_law(1)` and `Policy.current_law(3)` give the low- and
high-cost alternatives.

A `Policy` holds the primitive inputs: the AWI history and projected
growth, COLAs, taxable-maximum history, the 1979 bend points, the PIA and
family-maximum percentages, reduction and delayed-credit rates, and so on.
`replace` changes them, and everything derived from them follows:

```python
faster_wages = CURRENT_LAW.replace(
    awi_growth={y: g + 0.5 for y, g in CURRENT_LAW.awi_growth.items()})
four_brackets = CURRENT_LAW.replace(
    pia_bend_base=(180.0, 1085.0, 2000.0), pia_pct=(0.90, 0.32, 0.15, 0.05))
```

To pin a derived value directly, use `with_series`, for example
`CURRENT_LAW.with_series("taxmax", {2030: 250_000.0})`. Pinned values are
final: later years are not re-projected from them.

## Microsimulation

```python
b = retired_worker(earnings, birth_year, 6, claim_age, first_year=1980)
```

With 100,000 synthetic workers and 66 years of earnings each, this call
takes about 2 seconds on a laptop (`docs/examples/microsim.py`). The work
is NumPy throughout, with Python loops only over years, never over people.

## What is exact, and what is not covered

Results match AnyPIA to the cent for wage-indexed computations with
eligibility in 1979 or later: retirement, disability (with the child-care
dropout years and the non-freeze computation), and survivor benefits
(with the re-indexed widow(er)'s guarantee), plus the special minimum and
the WEP.

Not covered:

- the pre-1979 computation methods: old-start, the PIA table, the
  transitional guarantee and the frozen minimum
- totalization, and the disability guarantee after a prior period of
  disability
- divorced spouses, and the retirement earnings test
- **pre-1978 quarters of coverage**, which are approximated: SSA counted
  calendar-quarter wages, while this library applies the annual rule with
  the $50 amount
- **the GPO**, which follows the statute, because AnyPIA has none

The Social Security Fairness Act repealed the WEP and GPO for benefits
after December 2023, so `CURRENT_LAW` applies neither.
`CURRENT_LAW.replace(wep_enabled=True)` turns the WEP back on for
historical or counterfactual work.

## How it is tested

The test suite generates thousands of random workers (retired, disabled,
survivors, families, low earners, short careers, maximum earners), runs
each through this library and through
[anypia-engine](https://github.com/anthonycolavito/anypia-engine), and
requires every PIA, family maximum, factor and benefit to agree exactly.
The engine itself agrees to the cent with SSA's C++ calculator. Policy
parameters are also checked against values extracted from that C++.

```bash
pip install -e ".[dev,pandas]"
pytest            # the fast suite
pytest -m slow    # the large sweeps, about 17,000 more cases
```

## License

MIT. pyanypia is not an official Social Security Administration product;
see `LICENSE`.
