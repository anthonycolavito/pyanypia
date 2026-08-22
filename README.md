# pyanypia

A pure-Python port of the calculation engine inside the Social Security
Administration's **Detailed Calculator (AnyPIA)**, 2026 Trustees Report
version — Social Security benefit calculations you can run, inspect, batch,
and modify in Python.

**Status: under construction.** Progress and fidelity guarantees are tracked
below as phases land.

## What it does

- Computes retirement, disability, survivor, and family benefits from a
  worker's earnings record: AIME, PIA under every applicable computation
  method, family maximum, reductions/credits, monthly benefit.
- **Penny-exact by construction**: the port is differentially tested against
  the official C++ calculator, compiled from SSA's published source (vendored
  in `oracle/`), across generated case suites. If pyanypia prints it, the
  intent is that AnyPIA prints the same cents.
- Reads and writes official `.pia` case files.
- Policy reforms (LawChange equivalents) as declarative Python objects, for
  baseline-vs-reform analysis.

## Install

```bash
pip install git+https://github.com/anthonycolavito/pyanypia
```

## Quick look (API under construction)

```python
import pyanypia as pia

w = pia.Worker(dob="1960-03-15", sex="F", earnings={1982: 14_000.0, 2025: 61_000.0})
r = pia.compute(w, benefit_date="2027-01")
r.pia, r.mba, r.aime, r.method
```

## Not an official SSA product

pyanypia is derived from SSA/OACT's public-domain Detailed Calculator source
but is **not** an official Social Security Administration product and is not
endorsed by SSA. Amounts are research estimates — consult SSA for official
benefit determinations.
